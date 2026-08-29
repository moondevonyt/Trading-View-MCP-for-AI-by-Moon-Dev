"""
🌙 Moon Dev's end-to-end proof for the TradingView MCP.

Drives the REAL registered MCP tools (not private helpers) to:
  1. validate the Pine offline through pine-facade  (no browser)
  2. point the chart at an intraday symbol
  3. write the script into the Pine Editor
  4. add it to the chart
  5. screenshot the result

Run:
    TV_MCP_CDP_PORT=9333 python tests/test_vwap_star_live.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tradingview_mcp.cdp_client import find_tradingview_tab, CDPClient  # noqa: E402
from tradingview_mcp.chrome_launcher import CDP_PORT  # noqa: E402
from tradingview_mcp.server import build_server  # noqa: E402

PINE = Path(__file__).resolve().parents[1] / "examples" / "moon_dev_vwap_triangle_volume_star.pine"
SHOT_DIR = Path(os.environ.get("MD_SHOT_DIR", "."))
SYMBOL = os.environ.get("MD_SYMBOL", "NASDAQ:AAPL")
INTERVAL = os.environ.get("MD_INTERVAL", "5")


def step(n: str) -> None:
    print(f"\n{'=' * 62}\n🌙 {n}\n{'=' * 62}")


async def call(mcp, name: str, **kwargs):
    """Invoke a registered MCP tool and return its decoded result."""
    res = await mcp.call_tool(name, kwargs)
    # FastMCP returns (content_blocks, raw) or just content blocks depending on version.
    payload = res[1] if isinstance(res, tuple) and len(res) > 1 else res
    if isinstance(payload, list) and payload and hasattr(payload[0], "text"):
        payload = json.loads(payload[0].text)
    if isinstance(payload, dict) and "result" in payload and len(payload) == 1:
        payload = payload["result"]
    return payload


async def main() -> int:
    code = PINE.read_text()
    mcp = build_server()
    names = sorted(t.name for t in await mcp.list_tools())
    print(f"🌙 Moon Dev MCP exposes {len(names)} tools: {', '.join(names)}")

    # ---- 1. offline compile check ------------------------------------------
    step("STEP 1 — compile-check the Pine WITHOUT a browser")
    t0 = time.time()
    res = await call(mcp, "tv_validate_pine_script", code=code)
    print(f"took {(time.time() - t0) * 1000:.0f} ms -> valid={res.get('valid')}")
    if not res.get("valid"):
        print(res.get("annotated"))
        return 1

    # ---- 2. point the chart at an intraday symbol ---------------------------
    step(f"STEP 2 — load {SYMBOL} on the {INTERVAL}m chart")
    tab = find_tradingview_tab(port=CDP_PORT)
    cdp = CDPClient(tab.ws_url, timeout=30.0)
    cdp.connect()
    url = f"https://www.tradingview.com/chart/?symbol={SYMBOL.replace(':', '%3A')}&interval={INTERVAL}"
    cdp.send("Page.navigate", {"url": url})
    deadline = time.time() + 30
    while time.time() < deadline and cdp.eval_js("document.readyState") != "complete":
        time.sleep(0.5)
    time.sleep(6)  # TV's chart JS keeps working after readyState
    print("symbol on chart:", cdp.eval_js(
        "(document.querySelector('[data-name=\"legend-source-title\"]')||{}).textContent"))

    # ---- 3. write the script ------------------------------------------------
    step("STEP 3 — write the Pine into the editor")
    t0 = time.time()
    res = await call(mcp, "tv_write_pine_script", code=code)
    print(f"took {time.time() - t0:.1f}s -> {res}")
    if res.get("status") != "ok":
        cdp.screenshot(SHOT_DIR / "md_fail_write.png")
        return 1

    # ---- 4. add to chart ----------------------------------------------------
    step("STEP 4 — add it to the chart")
    t0 = time.time()
    res = await call(mcp, "tv_compile_pine_script")
    print(f"took {time.time() - t0:.1f}s")
    print("compile errors:", res.get("compile_errors"))
    print("chart legend  :", res.get("legend"))

    # TV shows either the full title or the shorttitle in the legend depending
    # on how the study was added, so accept both. 🌙
    mounted = any(("MD VWAP" in t) or ("Moon Dev VWAP" in t)
                  for t in (res.get("legend") or []))
    print(f"\n🌙 SCRIPT MOUNTED ON CHART: {mounted}")

    # ---- 5. screenshot ------------------------------------------------------
    step("STEP 5 — screenshot the chart")
    time.sleep(3)
    shot = cdp.screenshot(SHOT_DIR / "md_vwap_star_chart.png")
    print("saved:", shot)
    cdp.close()
    return 0 if mounted else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
