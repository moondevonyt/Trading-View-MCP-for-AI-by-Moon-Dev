"""
🌙 Moon Dev's chart-control tools.

Covers symbol, timeframe, current state, and screenshots. Uses a mix of
URL navigation (for symbol/interval — most robust) and keyboard shortcuts
(for timeframe-on-existing-chart — slick when it works).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

from ..cdp_client import CDPClient
from ._helpers import focus_chart, press_escape, with_cdp


def _current_chart_state(cdp: CDPClient) -> dict[str, str]:
    """Scrape symbol + interval from the page title and URL. TV encodes both."""
    js = """
    (() => {
      const title = document.title || '';
      const href = location.href || '';
      return { title: title, href: href };
    })()
    """
    data = cdp.eval_js(js) or {}
    title = str(data.get("title", ""))
    href = str(data.get("href", ""))
    symbol, interval = "", ""
    # "NVDA, 5 — TradingView" or "BTCUSD · 1H Chart" — many variants. Best-effort.
    if " — " in title:
        head = title.split(" — ", 1)[0]
        parts = [p.strip() for p in head.replace("·", ",").split(",")]
        if parts:
            symbol = parts[0]
            if len(parts) >= 2:
                interval = parts[1]
    # Fallback: parse ?symbol=&interval= from URL.
    from urllib.parse import urlparse, parse_qs
    qs = parse_qs(urlparse(href).query)
    symbol = symbol or (qs.get("symbol", [""])[0])
    interval = interval or (qs.get("interval", [""])[0])
    return {"symbol": symbol, "interval": interval, "url": href}


def register(mcp) -> None:
    """Register chart tools on the given FastMCP instance."""

    @mcp.tool()
    @with_cdp("tv_set_symbol")
    def tv_set_symbol(cdp: CDPClient, symbol: str) -> dict:
        """
        🌙 Switch the active chart to a symbol. Supports exchange-prefixed
        symbols like COINBASE:BTCUSD or NASDAQ:NVDA (recommended — unambiguous).

        Strategy: navigate to the chart URL with ?symbol= query param. This
        is the most reliable method and survives TV UI changes.
        """
        if not symbol or not isinstance(symbol, str):
            return {"status": "error", "error": "symbol must be a non-empty string"}

        # Navigate via JS so we keep the same tab. Page.navigate also works.
        js = f"""
        (() => {{
          const s = {json.dumps(symbol)};
          const base = 'https://www.tradingview.com/chart/';
          const url = new URL(location.href.startsWith(base) ? location.href : base);
          url.pathname = '/chart/';
          url.searchParams.set('symbol', s);
          location.href = url.toString();
          return true;
        }})()
        """
        cdp.eval_js(js)
        # Give TV a moment to load.
        time.sleep(1.2)
        state = _current_chart_state(cdp)
        return {"status": "ok", "symbol": symbol, "state": state}

    @mcp.tool()
    @with_cdp("tv_set_timeframe")
    def tv_set_timeframe(cdp: CDPClient, timeframe: str) -> dict:
        """
        🌙 Set the chart timeframe. Accepts TV-native codes: "1","5","15","60",
        "240" (minutes) or "D","W","M" (daily/weekly/monthly).

        Strategy: TV's "type-to-change-interval" shortcut. Focus the chart,
        type the code, press Enter. Fallback: header toolbar click.
        """
        tf = (timeframe or "").strip()
        if not tf:
            return {"status": "error", "error": "timeframe required"}

        focus_chart(cdp)
        time.sleep(0.2)
        # Clear any open overlay first.
        press_escape(cdp)
        time.sleep(0.15)
        # Type the timeframe code.
        cdp.type_text(tf)
        time.sleep(0.25)
        cdp.press_key("Enter")
        time.sleep(0.8)

        state = _current_chart_state(cdp)
        return {"status": "ok", "timeframe": tf, "state": state}

    @mcp.tool()
    @with_cdp("tv_get_current_symbol")
    def tv_get_current_symbol(cdp: CDPClient) -> dict:
        """🌙 Return the symbol, timeframe, and URL of the currently displayed chart."""
        state = _current_chart_state(cdp)
        return {"status": "ok", **state}

    @mcp.tool()
    @with_cdp("tv_screenshot")
    def tv_screenshot(cdp: CDPClient, path: str = "") -> dict:
        """
        🌙 Capture a PNG of the current chart. Default save dir lives next to the
        dedicated Chrome profile so screenshots are easy to find.
        """
        if not path:
            default_dir = Path(os.path.expanduser("~/.tradingview_mcp_chrome/screenshots"))
            default_dir.mkdir(parents=True, exist_ok=True)
            path = str(default_dir / f"tv_{int(time.time())}.png")
        saved = cdp.screenshot(path)
        return {"status": "ok", "path": saved}
