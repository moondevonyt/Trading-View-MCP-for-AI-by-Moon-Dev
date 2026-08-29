"""
🌙 Moon Dev — one-shot driver: load the Rainbow Wave 20/40 Pine script into
the live TradingView tab, compile it, and take a screenshot.

Reuses the existing CDP client + pine helpers from the MCP package so the
logic stays identical to what Claude would do via the MCP tools.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from tradingview_mcp.cdp_client import open_tv_client
from tradingview_mcp.tools.pine import (
    _focus_pine_textarea,
    _open_pine_editor,
    _paste_text,
    _read_pine_errors,
    _select_all_and_delete,
)
from tradingview_mcp.tools._helpers import wait_for_selector
from tradingview_mcp import tv_selectors as S

SCRIPT_PATH = Path(__file__).parent / "examples" / "moon_dev_rainbow_wave_20_40.pine"
SHOT_PATH   = Path(__file__).parent / "moon_dev_rainbow_wave_shot.png"
CHART_URL   = "https://www.tradingview.com/chart/"


def _wait_ready(cdp, hold: float = 2.5, limit: float = 20.0) -> None:
    """Wait for document.readyState == 'complete', then hold for TV JS to settle."""
    deadline = time.time() + limit
    while time.time() < deadline:
        try:
            if cdp.eval_js("document.readyState") == "complete":
                break
        except Exception:
            pass
        time.sleep(0.4)
    time.sleep(hold)


def main() -> int:
    code = SCRIPT_PATH.read_text()
    print(f"🌙 Moon Dev: loaded {len(code)} bytes from {SCRIPT_PATH.name}")

    with open_tv_client() as cdp:
        print("🌙 Moon Dev: connected to TradingView tab")

        url = cdp.eval_js("location.href") or ""
        on_chart = "/chart" in url

        if not on_chart:
            # Fresh navigation already gives us a clean Pine template — no reload needed.
            print(f"🌙 Moon Dev: current URL is {url!r}, navigating to {CHART_URL}")
            cdp.send("Page.navigate", {"url": CHART_URL})
            _wait_ready(cdp, hold=3.5)
        else:
            # Already on chart — reload to get a clean Pine template.
            print("🌙 Moon Dev: on /chart/, reloading for clean Pine template")
            cdp.send("Page.reload", {"ignoreCache": False})
            _wait_ready(cdp, hold=2.5)

        if not _open_pine_editor(cdp):
            print("❌ Pine editor not reachable")
            return 1
        print("🌙 Moon Dev: Pine editor open")

        _focus_pine_textarea(cdp)
        _select_all_and_delete(cdp)
        time.sleep(0.2)
        _paste_text(cdp, code)
        time.sleep(1.0)
        print("🌙 Moon Dev: Rainbow Wave script pasted into editor")

        # Click Add/Update to chart
        clicked = cdp.eval_js("""
        (() => {
          for (const t of ['Add to chart', 'Update on chart']) {
            const b = document.querySelector('button[title=' + JSON.stringify(t) + ']');
            if (b && !b.disabled) { b.click(); return t; }
          }
          return null;
        })()
        """)
        if not clicked:
            print("❌ no Add/Update button found")
            return 1
        print(f"🌙 Moon Dev: clicked '{clicked}' — compiling…")
        time.sleep(4.0)

        errs = _read_pine_errors(cdp)
        if errs:
            print("⚠️  compile errors:")
            for e in errs[:10]:
                print(f"   - {e}")
        else:
            print("✅ Moon Dev: compile clean, Rainbow Wave is on the chart 🌈")

        shot = cdp.screenshot(SHOT_PATH)
        print(f"📸 Moon Dev: screenshot saved → {shot}")
        return 0 if not errs else 2


if __name__ == "__main__":
    sys.exit(main())
