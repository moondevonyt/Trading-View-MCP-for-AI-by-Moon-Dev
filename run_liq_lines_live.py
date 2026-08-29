"""
🌙 Moon Dev — Liquidation Lines indicator for TradingView.

Pulls the top 50 longs + 50 shorts per symbol from api.moondev.com, picks the
10 positions on each side with the smallest distance-to-liq %, and generates a
Pine v6 indicator that draws a horizontal line at each liq price labelled with
position size + leverage. Then pushes the Pine script into the TradingView tab
via the MCP's CDP bridge.

Usage:
    python run_liq_lines_live.py            # BTC (default)
    python run_liq_lines_live.py ETH
    python run_liq_lines_live.py FART       # maps to FARTCOIN on Hyperliquid

Supported: BTC, ETH, SOL, HYPE, FART (FARTCOIN)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from tradingview_mcp.cdp_client import open_tv_client
from tradingview_mcp.tools._helpers import wait_for_selector
from tradingview_mcp.tools.pine import _open_pine_editor
from tradingview_mcp import tv_selectors as S

# --- config ------------------------------------------------------------------
API_BASE   = "https://api.moondev.com"
POSITIONS  = "/api/positions/all_crypto.json"
API_KEY    = os.environ.get("MOONDEV_API_KEY", "").strip()
TOP_N      = 10

# User-facing symbol → Hyperliquid coin key
SYMBOL_MAP = {
    "BTC":  "BTC",
    "ETH":  "ETH",
    "SOL":  "SOL",
    "HYPE": "HYPE",
    "FART": "FARTCOIN",
}

SHOT_PATH = Path(__file__).parent / "moon_dev_liq_lines_shot.png"

# TradingView ticker per user-facing symbol. BTC/ETH/SOL use Coinbase spot;
# HYPE + FARTCOIN live on Hyperliquid perps — HYPE has a reliable TV feed,
# FARTCOIN does not (user was warned in CLAUDE.md to avoid synthetic fills).
TV_TICKER = {
    "BTC":  "COINBASE:BTCUSD",
    "ETH":  "COINBASE:ETHUSD",
    "SOL":  "COINBASE:SOLUSD",
    "HYPE": "KRAKEN:HYPEUSD",       # 🌙 only TV-listed HYPE/USD spot pair
    "FART": "MEXC:FARTCOINUSDT",    # 🌙 BYBIT also lists; MEXC has more depth
}


def fetch_positions(coin: str) -> tuple[list[dict], list[dict], float]:
    """Return (longs, shorts, current_price) for `coin`."""
    if not API_KEY:
        raise RuntimeError("🌙 Moon Dev: MOONDEV_API_KEY missing from .env")
    r = requests.get(API_BASE + POSITIONS, headers={"X-API-Key": API_KEY}, timeout=30)
    r.raise_for_status()
    data = r.json()
    node = data.get("symbols", {}).get(coin)
    if not node:
        raise RuntimeError(f"🌙 Moon Dev: {coin} not in positions feed")
    longs  = node.get("longs", []) or []
    shorts = node.get("shorts", []) or []
    cur_px = longs[0]["current_price"] if longs else (shorts[0]["current_price"] if shorts else 0.0)
    return longs, shorts, cur_px


def _fmt_value(v: float) -> str:
    """$604,501 → '$604k', $1,250,000 → '$1.25M'."""
    if v >= 1_000_000: return f"${v/1_000_000:.2f}M"
    if v >= 1_000:     return f"${v/1_000:.0f}k"
    return f"${v:.0f}"


def pick_closest(positions: list[dict], n: int) -> list[dict]:
    """Smallest distance-to-liq first, trimmed to n."""
    valid = [p for p in positions if p.get("liq_price") and p.get("distance_pct") is not None]
    return sorted(valid, key=lambda p: p["distance_pct"])[:n]


def generate_pine(display_symbol: str, longs: list[dict], shorts: list[dict], cur_px: float) -> str:
    """Build the Pine v6 indicator source."""
    L = pick_closest(longs,  TOP_N)
    S = pick_closest(shorts, TOP_N)

    # Pine v6 `array.from(...)` takes varargs of one type, so we emit two
    # parallel arrays per side (prices + labels) and index them together.
    def _prices(items: list[dict]) -> str:
        return ", ".join(f"{float(p['liq_price']):.6f}" for p in items) or "0.0"

    def _labels(items: list[dict]) -> str:
        parts = []
        for i, p in enumerate(items, 1):
            val  = _fmt_value(float(p.get("value", 0)))
            lev  = p.get("leverage", 0)
            dist = p.get("distance_pct", 0)
            addr = (p.get("address") or "")[:6]
            parts.append(f'"#{i}  {val}  {lev:g}x  {dist:.2f}%  {addr}"')
        return ", ".join(parts) or '"no data"'

    long_prices  = _prices(L)
    long_labels  = _labels(L)
    short_prices = _prices(S)
    short_labels = _labels(S)

    # Pine v6. Lines drawn once on the last bar, extended right. Fun neon palette.
    return f'''//@version=6
// 🌙 Moon Dev's Liquidation Heatlines — {display_symbol}
// Top {TOP_N} closest-to-liquidation longs (red) + shorts (green) from the
// Hyperliquid top-50 feed at api.moondev.com. Regenerate to refresh.
indicator("🌙 Moon Dev Liq Lines — {display_symbol}", shorttitle="🌙 Liq {display_symbol}", overlay=true, max_lines_count=50, max_labels_count=60)

// --- INPUTS ----------------------------------------------------------------
extendBars = input.int(120, "Extend Lines (bars)", 10, 500)
lineWidth  = input.int(4,   "Line Width",          1,   8)
showLabels = input.bool(true, "Show Labels")
labelSize  = input.string("normal", "Label Size", options=["tiny","small","normal","large"])

// --- PALETTE (Moon Dev cosmic) --------------------------------------------
cLongHot  = color.rgb(255,  64,  64)  // danger red — longs liquidated here
cLongWarm = color.rgb(255, 140,  40)  // amber
cShortHot = color.rgb(0,   230, 118)  // neon green — shorts liquidated here
cShortWarm= color.rgb(64,  224, 208)  // cyan
cLabelBg  = color.new(color.rgb(10, 10, 25), 15)

// --- DATA ------------------------------------------------------------------
// Parallel arrays per side — Pine's array.from() is varargs-of-one-type so
// we split price + label arrays and index them together. 🌙
var float[]  longPrices  = array.from({long_prices})
var string[] longLabels  = array.from({long_labels})
var float[]  shortPrices = array.from({short_prices})
var string[] shortLabels = array.from({short_labels})

labelSz = labelSize == "tiny"   ? size.tiny :
          labelSize == "small"  ? size.small :
          labelSize == "normal" ? size.normal : size.large

// --- DRAW ------------------------------------------------------------------
// One-shot on the last bar. Re-draws each tick so labels track `bar_index`.
var line[]  drawnLines  = array.new<line>()
var label[] drawnLabels = array.new<label>()

if barstate.islast
    // Clear old artifacts so we don't pile up on each tick
    for ln in drawnLines
        line.delete(ln)
    array.clear(drawnLines)
    for lb in drawnLabels
        label.delete(lb)
    array.clear(drawnLabels)

    x1 = bar_index - 400
    x2 = bar_index + extendBars

    // Longs — top 3 get extra-bold hot red, rest stay fully opaque warm
    for i = 0 to array.size(longPrices) - 1
        p   = array.get(longPrices, i)
        txt = array.get(longLabels, i)
        col = i < 3 ? cLongHot : cLongWarm
        w   = i < 3 ? lineWidth + 1 : lineWidth  // top 3 thicker still
        array.push(drawnLines, line.new(x1, p, x2, p, color=col, width=w, style=line.style_solid))
        if showLabels
            array.push(drawnLabels, label.new(x2, p, "🔴 L" + str.tostring(i+1) + "  " + txt, style=label.style_label_left, color=cLabelBg, textcolor=col, size=labelSz, tooltip="Long liquidation — price drops here and these get wiped"))

    // Shorts
    for i = 0 to array.size(shortPrices) - 1
        p   = array.get(shortPrices, i)
        txt = array.get(shortLabels, i)
        col = i < 3 ? cShortHot : cShortWarm
        w   = i < 3 ? lineWidth + 1 : lineWidth
        array.push(drawnLines, line.new(x1, p, x2, p, color=col, width=w, style=line.style_solid))
        if showLabels
            array.push(drawnLabels, label.new(x2, p, "🟢 S" + str.tostring(i+1) + "  " + txt, style=label.style_label_left, color=cLabelBg, textcolor=col, size=labelSz, tooltip="Short liquidation — price rises here and these get squeezed"))

// --- HEADER LABEL ----------------------------------------------------------
if barstate.islast
    hdr = "🌙 Moon Dev Liq Lines — {display_symbol}  |  top {TOP_N}/side  |  data: api.moondev.com"
    array.push(drawnLabels, label.new(bar_index, high * 1.002, hdr, style=label.style_label_down, color=color.new(color.rgb(170, 120, 255), 10), textcolor=color.white, size=size.small))
'''


# --- CDP push (reuses the clear-and-paste flow from the SMA ribbon loader) --

def _mouse_click_center(cdp) -> None:
    c = cdp.eval_js("""(() => {const ed = document.querySelector('.monaco-editor.pine-editor-monaco'); const r = ed.getBoundingClientRect(); return {x:r.left+r.width/2, y:r.top+r.height/2};})()""")
    for mtype in ("mousePressed", "mouseReleased"):
        cdp.send("Input.dispatchMouseEvent", {"type": mtype, "x": int(c["x"]), "y": int(c["y"]), "button": "left", "clickCount": 1, "buttons": 1})


def _cmd_key(cdp, key: str, code: str, kc: int) -> None:
    cdp.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code, "modifiers": 4, "windowsVirtualKeyCode": kc})
    cdp.send("Input.dispatchKeyEvent", {"type": "keyUp",   "key": key, "code": code, "modifiers": 4, "windowsVirtualKeyCode": kc})


def _lines_content(cdp) -> str:
    return cdp.eval_js("""(() => {
        const root = document.querySelector('.monaco-editor.pine-editor-monaco');
        if (!root) return '';
        return Array.from(root.querySelectorAll('.view-line')).map(l => l.textContent).join('\\n');
    })()""") or ""


def _ensure_symbol(cdp, ticker: str) -> None:
    """Switch the chart to `ticker` via TV's own widget API.
    `window.TradingViewApi._activeChartWidgetWV.value().setSymbol(ticker)` is
    the same call TV's UI makes when the user picks a symbol — works inside
    saved layouts, no URL navigation, no flaky modal typing. 🌙 Moon Dev
    """
    want = ticker.split(":")[-1].upper().replace("USD","")
    cur_title = (cdp.eval_js("document.title") or "").upper()
    if want and cur_title.startswith(want):
        return
    payload = json.dumps(ticker)
    res = cdp.eval_js(f"""(() => {{
        try {{
            const api = window.TradingViewApi;
            if (!api || !api._activeChartWidgetWV) return 'no-api';
            const w = api._activeChartWidgetWV.value();
            if (!w || typeof w.setSymbol !== 'function') return 'no-setSymbol';
            w.setSymbol({payload});
            return 'ok';
        }} catch(e) {{ return 'exc:' + e.message; }}
    }})()""")
    if res != "ok":
        raise RuntimeError(f"🌙 Moon Dev: setSymbol failed → {res!r}")
    # Wait up to 10s for the chart to repaint with the new symbol (title flips)
    for _ in range(20):
        time.sleep(0.5)
        t = (cdp.eval_js("document.title") or "").upper()
        if want and t.startswith(want):
            break
    time.sleep(1.5)  # settle indicator pane / scale


def push_to_tv(pine_code: str, ticker: str | None = None) -> dict:
    """Paste `pine_code` into Pine editor and click Add/Update. Returns status dict."""
    with open_tv_client() as cdp:
        if ticker:
            _ensure_symbol(cdp, ticker)

        # Dismiss any stray Save/Cancel modal
        cdp.eval_js("""(() => {for (const b of document.querySelectorAll('button')) if ((b.textContent||'').trim()==='Cancel') b.click(); })()""")
        time.sleep(0.3)

        # Make sure the Pine editor panel is open before we touch it
        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            _open_pine_editor(cdp)
            time.sleep(1.0)

        # 🌙 Moon Dev: grab the Monaco editor instance via React fiber walk and
        # atomically replace the whole model with `executeEdits`. TV doesn't
        # expose `window.monaco` so we find the editor by scanning the fiber
        # tree for an object with getValue/setValue/getModel/executeEdits.
        # This fires onDidChangeModelContent exactly once, which TV listens
        # for to mark the script dirty → enables the Add/Update button.
        _mouse_click_center(cdp)
        time.sleep(0.2)
        payload = json.dumps(pine_code)
        result = cdp.eval_js(f"""(() => {{
            try {{
                let el = document.querySelector('.monaco-editor.pine-editor-monaco');
                if (!el) return 'no-host';
                let fkey = null, up = el, hops = 0;
                while (up && !fkey && hops < 20) {{
                    fkey = Object.keys(up).find(k => k.startsWith('__reactFiber$'));
                    if (!fkey) {{ up = up.parentElement; hops++; }}
                }}
                if (!fkey) return 'no-fiber';
                const visited = new WeakSet();
                function scan(obj, depth) {{
                    if (!obj || typeof obj !== 'object' || visited.has(obj) || depth > 5) return null;
                    try {{ visited.add(obj); }} catch(e) {{ return null; }}
                    for (const k in obj) {{
                        let v; try {{ v = obj[k]; }} catch(e) {{ continue; }}
                        if (v && typeof v === 'object') {{
                            try {{
                                if (typeof v.setValue === 'function' && typeof v.getValue === 'function' && typeof v.getModel === 'function' && typeof v.executeEdits === 'function') {{
                                    return v;
                                }}
                            }} catch(e) {{}}
                            const f = scan(v, depth+1);
                            if (f) return f;
                        }}
                    }}
                    return null;
                }}
                let fiber = up[fkey], editor = null, fhops = 0;
                while (fiber && !editor && fhops < 100) {{
                    try {{
                        if (fiber.stateNode) editor = scan(fiber.stateNode, 0);
                        if (!editor && fiber.memoizedProps) editor = scan(fiber.memoizedProps, 0);
                    }} catch(e) {{}}
                    fiber = fiber.return; fhops++;
                }}
                if (!editor) return 'no-editor';
                editor.focus();
                // setValue replaces the entire model atomically and fires
                // onDidChangeModelContent — simpler + more reliable than
                // executeEdits (which choked on range.toString in this build).
                editor.setValue({payload});
                return 'ok:setValue';
            }} catch(e) {{
                return 'exc:' + (e && e.message ? e.message : String(e));
            }}
        }})()""")
        if not result or not result.startswith("ok"):
            raise RuntimeError(f"🌙 Moon Dev: editor replace failed → {result!r}")
        time.sleep(2.0)

        # Click Add to chart / Update on chart
        clicked = cdp.eval_js("""(() => {
          for (const t of ['Add to chart', 'Update on chart']) {
            const b = document.querySelector('button[title=' + JSON.stringify(t) + ']');
            if (b && !b.disabled) { b.click(); return t; }
          }
          return null;
        })()""")
        time.sleep(5)

        errs = cdp.eval_js("""(() => {
            const root = document.querySelector('[data-name="pine-editor-console"]');
            if (!root) return [];
            return Array.from(root.querySelectorAll('*')).map(n => (n.textContent||'').trim()).filter(t => t && t.length < 400 && /error/i.test(t));
        })()""") or []

        cdp.screenshot(SHOT_PATH)
        return {"button": clicked, "errors": errs[:5], "shot": str(SHOT_PATH)}


def main() -> int:
    user_sym = (sys.argv[1].upper() if len(sys.argv) > 1 else "BTC")
    if user_sym not in SYMBOL_MAP:
        print(f"❌ unsupported symbol {user_sym}. Supported: {list(SYMBOL_MAP)}")
        return 1
    coin = SYMBOL_MAP[user_sym]

    print(f"🌙 Moon Dev: fetching positions for {user_sym} (Hyperliquid coin: {coin})")
    longs, shorts, cur_px = fetch_positions(coin)
    L = pick_closest(longs, TOP_N)
    S = pick_closest(shorts, TOP_N)
    print(f"   top {TOP_N} closest long liqs:  {[round(p['liq_price'], 4) for p in L]}")
    print(f"   top {TOP_N} closest short liqs: {[round(p['liq_price'], 4) for p in S]}")
    print(f"   current_price (last tick):     {cur_px}")

    pine = generate_pine(user_sym, longs, shorts, cur_px)
    out_file = Path(__file__).parent / "examples" / f"moon_dev_liq_lines_{user_sym.lower()}.pine"
    out_file.write_text(pine)
    print(f"📝 Moon Dev: wrote {out_file.name} ({len(pine)} bytes)")

    print("🌙 Moon Dev: pushing to TradingView via MCP…")
    res = push_to_tv(pine, ticker=TV_TICKER.get(user_sym))
    print(f"   button clicked: {res['button']}")
    if res["errors"]:
        print("   ⚠️  compile errors:")
        for e in res["errors"]:
            print(f"     - {e}")
        return 2
    print(f"✅ Moon Dev: indicator live. Screenshot → {res['shot']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
