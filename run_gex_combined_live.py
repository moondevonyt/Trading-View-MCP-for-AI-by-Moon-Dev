"""
Moon Dev driver: push the combined GEX Stack to live TV.

Uses Page.reload to guarantee a clean Pine editor template, then pastes the
combined script and clicks Add to chart. The reload drops the CDP socket on
Electron webviews, so we re-establish the connection if needed.
"""
from __future__ import annotations
import sys, time
from pathlib import Path

from tradingview_mcp.cdp_client import open_tv_client
from tradingview_mcp.tools.pine import (
    _focus_pine_textarea, _open_pine_editor, _paste_text,
    _read_pine_errors, _select_all_and_delete,
)
from tradingview_mcp.tools._helpers import wait_for_selector
from tradingview_mcp import tv_selectors as S

SCRIPT = Path(__file__).parent / "examples" / "moon_dev_gex_combined.pine"
SHOT   = Path(__file__).parent / "moon_dev_gex_stack_shot.png"


def _wait_ready(cdp, hold: float = 3.0, limit: float = 20.0) -> None:
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
    code = SCRIPT.read_text()
    print(f"Moon Dev: loaded {len(code)} bytes")

    with open_tv_client() as cdp:
        print("Moon Dev: connected to TV tab")

        # Reload to get clean Pine editor template
        try:
            cdp.send("Page.reload", {"ignoreCache": False})
            _wait_ready(cdp, hold=3.5)
        except Exception as e:
            print(f"reload threw (expected on Electron): {e}")
            time.sleep(4.0)

    # Reconnect after reload
    print("Moon Dev: reconnecting after reload...")
    time.sleep(2.0)
    with open_tv_client() as cdp:
        print("Moon Dev: reconnected")

        if not _open_pine_editor(cdp):
            print("ERROR: Pine editor not reachable")
            return 1
        print("Moon Dev: Pine editor open with clean template")

        _focus_pine_textarea(cdp)
        _select_all_and_delete(cdp)
        time.sleep(0.4)
        _paste_text(cdp, code)
        time.sleep(2.0)
        print("Moon Dev: combined script pasted")

        clicked = cdp.eval_js("""
        (() => {
          for (const t of ['Add to chart', 'Update on chart', 'Save script']) {
            const b = document.querySelector('button[title=' + JSON.stringify(t) + ']');
            if (b && !b.disabled) { b.click(); return t; }
          }
          return null;
        })()
        """)
        print(f"Moon Dev: clicked '{clicked}'")
        time.sleep(7)

        legend = cdp.eval_js("""
        (() => {
          const items = document.querySelectorAll('[data-name="legend-source-item"]');
          return Array.from(items).map(it => (it.textContent||'').trim().slice(0, 80));
        })()
        """) or []
        print(f"Legend ({len(legend)}):")
        for l in legend:
            print(f"  - {l}")

        errs = _read_pine_errors(cdp)
        if errs:
            print(f"\nRecent errors:")
            for e in errs[-5:]:
                print(f"  - {e}")

        shot = cdp.screenshot(SHOT)
        print(f"\nScreenshot: {shot}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
