"""
🌙 Moon Dev — live driver: load SMA Ribbon 20/40 into an already-open TV tab.

Skips the Page.reload step (which drops the CDP websocket on Electron webviews)
and just pastes the Pine script into whatever editor state is current.
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

SCRIPT_PATH = Path(__file__).parent / "examples" / "moon_dev_sma_ribbon_20_40.pine"
SHOT_PATH   = Path(__file__).parent / "moon_dev_sma_ribbon_shot.png"


def main() -> int:
    code = SCRIPT_PATH.read_text()
    print(f"🌙 Moon Dev: loaded {len(code)} bytes from {SCRIPT_PATH.name}")

    with open_tv_client() as cdp:
        print("🌙 Moon Dev: connected to TradingView tab")

        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            if not _open_pine_editor(cdp):
                print("❌ could not open Pine editor")
                return 1
        print("🌙 Moon Dev: Pine editor open")

        _focus_pine_textarea(cdp)
        _select_all_and_delete(cdp)
        time.sleep(0.3)
        _paste_text(cdp, code)
        time.sleep(1.2)
        print("🌙 Moon Dev: script pasted into editor")

        clicked = cdp.eval_js("""
        (() => {
          for (const t of ['Add to chart', 'Update on chart', 'Save script']) {
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
        time.sleep(4.5)

        errs = _read_pine_errors(cdp)
        if errs:
            print("⚠️  compile errors:")
            for e in errs[:10]:
                print(f"   - {e}")
        else:
            print("✅ Moon Dev: compile clean, indicator is on the chart")

        shot = cdp.screenshot(SHOT_PATH)
        print(f"📸 Moon Dev: screenshot saved → {shot}")
        return 0 if not errs else 2


if __name__ == "__main__":
    sys.exit(main())
