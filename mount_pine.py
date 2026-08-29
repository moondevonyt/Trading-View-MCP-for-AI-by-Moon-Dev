"""
🌙 Moon Dev's one-shot "idea to chart" driver.

Takes a .pine file, compile-checks it with no browser, writes it into the Pine
Editor, adds it to the live chart, proves it mounted by reading the legend,
then closes the editor panel and screenshots the result.

    python mount_pine.py examples/moon_dev_rainbow_ribbon_10_50.pine
    python mount_pine.py <file.pine> --shot out.png --keep-editor

Env:
    TV_MCP_CDP_PORT   which Chrome to drive (default 9222)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tradingview_mcp.cdp_client import find_tradingview_tab, CDPClient  # noqa: E402
from tradingview_mcp.chrome_launcher import CDP_PORT  # noqa: E402
from tradingview_mcp.server import build_server  # noqa: E402

LEGEND_JS = """
(() => Array.from(document.querySelectorAll('[class*="sources-"] [class*="titlesWrapper"]'))
   .map(n => (n.innerText || '').trim().split('\\n')[0]).filter(Boolean))()
"""

CLOSE_EDITOR_JS = """
(() => {
  const hdr = Array.from(document.querySelectorAll('*')).find(
    e => (e.innerText || '').trim() === 'Pine Editor' && e.children.length === 0);
  if (!hdr) return 'no-header';
  let bar = hdr;
  for (let i = 0; i < 6 && bar.parentElement; i++) {
    bar = bar.parentElement;
    const btns = Array.from(bar.querySelectorAll('button,[role="button"]'));
    const x = btns.find(b => (b.getAttribute('aria-label') || b.getAttribute('title')) === 'Close');
    if (x) { x.click(); return 'closed'; }
  }
  return 'no-close';
})()
"""


async def call(mcp, name: str, **kw):
    res = await mcp.call_tool(name, kw)
    payload = res[1] if isinstance(res, tuple) and len(res) > 1 else res
    if isinstance(payload, list) and payload and hasattr(payload[0], "text"):
        payload = json.loads(payload[0].text)
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    return payload


async def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 2
    pine = Path(args[0])
    shot = Path(args[args.index("--shot") + 1]) if "--shot" in args else Path("moon_dev_chart.png")
    keep_editor = "--keep-editor" in args

    code = pine.read_text()
    mcp = build_server()

    print(f"🌙 Moon Dev — mounting {pine.name} ({len(code)} bytes)")

    t0 = time.time()
    v = await call(mcp, "tv_validate_pine_script", code=code)
    print(f"  1. compile-check (no browser)  {(time.time() - t0) * 1000:>6.0f} ms   valid={v.get('valid')}")
    if not v.get("valid"):
        print(v.get("annotated"))
        return 1

    t0 = time.time()
    w = await call(mcp, "tv_write_pine_script", code=code)
    print(f"  2. write into editor           {(time.time() - t0):>6.1f} s    {w.get('path')}, {w.get('lines')} lines")
    if w.get("status") != "ok":
        print("     FAILED:", w.get("error"))
        return 1

    t0 = time.time()
    c = await call(mcp, "tv_compile_pine_script")
    print(f"  3. add to chart                {(time.time() - t0):>6.1f} s")
    if c.get("compile_errors"):
        print("     compile errors:", c["compile_errors"])
        return 1

    tab = find_tradingview_tab(port=CDP_PORT)
    cdp = CDPClient(tab.ws_url, timeout=30.0)
    cdp.connect()

    if not keep_editor:
        print("  4. close editor panel          ", cdp.eval_js(CLOSE_EDITOR_JS))
        time.sleep(2.5)

    legend = cdp.eval_js(LEGEND_JS) or []
    print("  5. chart legend                ", legend)

    # 🚨 Moon Dev: Page.captureScreenshot HANGS FOREVER inside an Electron
    # <webview> (Moon Dev Code App on 9222) — the webview composites offscreen
    # so Chrome never produces a frame to capture. Everything else works there.
    # Pass --no-shot when driving the Code App.
    if "--no-shot" in args:
        print("  6. screenshot                   skipped (--no-shot)")
    else:
        cdp.screenshot(shot)
        print("  6. screenshot                  ", shot)
    cdp.close()

    # Prove it by name, not by "no error came back". 🌙
    want = "Moon Dev" if "Moon Dev" in code else pine.stem
    ok = any(("MD " in t) or ("Moon Dev" in t) for t in legend)
    print(f"\n🌙 MOUNTED: {ok}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
