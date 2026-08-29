"""
Moon Dev driver: load all 3 GEX / 0DTE indicators onto the live TradingView tab.

Strategy:
  - Connect to the already-open TV tab (no reload, Electron drops the CDP socket).
  - For each .pine file:
        * focus Pine editor textarea
        * select-all + delete (clears current script text)
        * paste new code
        * click "Add to chart" (preferred), falling back to "Update on chart"
                 then "Save script"
        * wait for compile
  - After all three, take a screenshot.

If the button is "Update on chart" for indicator 2/3, TV would REPLACE indicator 1.
To avoid this we open a fresh Pine Editor tab between scripts using the "+" /
"Open" menu when present. If we can't open a new tab, we still try Add to chart
because each script's `indicator()` title differs, which usually flips TV back
to "Add to chart" mode.
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

EX = Path(__file__).parent / "examples"
SCRIPTS = [
    EX / "moon_dev_gex_walls_trap.pine",
    EX / "moon_dev_gex_regime_trap.pine",
    EX / "moon_dev_gex_sweep_cvd.pine",
]
SHOT_PATH = Path(__file__).parent / "moon_dev_gex_indicators_shot.png"


# JS that opens a new Pine Editor tab. TV exposes a "+" / "Open" / "New" button
# at the top of the Pine Editor panel. We try a few selectors / text matches.
NEW_TAB_JS = """
(() => {
  // 1) Direct "New" / plus button by aria-label
  const aria = document.querySelector('[aria-label="Open"], [aria-label="New"], [aria-label="Create new script"], button[title="Open"]');
  if (aria) { aria.click(); }

  // 2) Look for the "Open" dropdown near the Pine editor toolbar that has a
  //    "New" / "Open Pine Script" menu item. We click the toolbar Open btn
  //    and then click any "New" / "Create" menu item that appears.
  const all = document.querySelectorAll('button, [role="button"]');
  let openBtn = null;
  for (const b of all) {
    const t = (b.textContent || '').trim();
    if (t === 'Open' || t.startsWith('Open ')) {
      // Prefer ones inside the Pine editor panel
      if (b.closest('[data-name="pine-editor"]') || b.closest('[class*="pineEditorContainer"]') || b.closest('[class*="pine-editor"]')) {
        openBtn = b; break;
      }
      if (!openBtn) openBtn = b;
    }
  }
  if (openBtn) {
    openBtn.click();
    // Wait briefly, then click "New" item
    return new Promise(r => setTimeout(() => {
      const items = document.querySelectorAll('[role="menuitem"], [class*="menu"] [class*="item"]');
      for (const it of items) {
        const t = (it.textContent || '').trim().toLowerCase();
        if (t.startsWith('new ') || t === 'new default' || t === 'create new' || t.includes('new blank')) {
          it.click(); r(true); return;
        }
      }
      r(false);
    }, 400));
  }
  return false;
})()
"""


def _click_add_button(cdp) -> str | None:
    """Click Add-to-chart preferentially; fall back to Update / Save."""
    return cdp.eval_js(
        """
        (() => {
          // Prefer Add to chart; if absent, try Update on chart; finally Save script.
          for (const t of ['Add to chart', 'Update on chart', 'Save script']) {
            const b = document.querySelector('button[title=' + JSON.stringify(t) + ']');
            if (b && !b.disabled) { b.click(); return t; }
          }
          return null;
        })()
        """
    )


def _count_overlay_studies(cdp) -> int:
    """Count Pine studies on the chart legend (Moon Dev indicators contain 'Moon Dev')."""
    return cdp.eval_js(
        """
        (() => {
          const items = document.querySelectorAll('[data-name="legend-source-item"]');
          let n = 0;
          for (const it of items) {
            const t = (it.textContent || '');
            if (t.includes('Moon Dev')) n++;
          }
          return n;
        })()
        """
    ) or 0


def _push_one(cdp, path: Path, label: str) -> dict:
    code = path.read_text()
    print(f"Moon Dev: loaded {len(code)} bytes from {path.name}")

    _focus_pine_textarea(cdp)
    _select_all_and_delete(cdp)
    time.sleep(0.3)
    _paste_text(cdp, code)
    time.sleep(1.2)
    print(f"Moon Dev: pasted {label} into Pine editor")

    before = _count_overlay_studies(cdp)
    clicked = _click_add_button(cdp)
    if not clicked:
        return {"ok": False, "error": "no Add/Update/Save button found"}
    print(f"Moon Dev: clicked '{clicked}' — compiling…")
    time.sleep(5.0)

    errs = _read_pine_errors(cdp)
    after = _count_overlay_studies(cdp)
    return {
        "ok": not errs,
        "clicked": clicked,
        "errors": errs,
        "studies_before": before,
        "studies_after": after,
    }


def main() -> int:
    with open_tv_client() as cdp:
        print("Moon Dev: connected to TradingView tab")

        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            if not _open_pine_editor(cdp):
                print("ERROR: could not open Pine editor")
                return 1
        print("Moon Dev: Pine editor open")

        results = []
        for i, path in enumerate(SCRIPTS, start=1):
            label = f"indicator {i}/{len(SCRIPTS)} — {path.stem}"
            print(f"\n=== Moon Dev: pushing {label} ===")

            if i > 1:
                # Try to open a fresh Pine editor tab so each script becomes a
                # NEW chart study instead of overwriting the prior one.
                try:
                    opened = cdp.eval_js(NEW_TAB_JS)
                    if opened:
                        print("Moon Dev: opened new Pine editor tab")
                        time.sleep(1.2)
                        _focus_pine_textarea(cdp)
                except Exception as e:
                    print(f"Moon Dev: new-tab attempt failed (continuing): {e}")

            res = _push_one(cdp, path, label)
            results.append((path.name, res))
            if res["ok"]:
                print(f"OK Moon Dev: {path.stem} on chart "
                      f"(studies {res['studies_before']} -> {res['studies_after']})")
            else:
                print(f"WARN: {path.stem} reported issues: {res}")

        shot = cdp.screenshot(SHOT_PATH)
        print(f"\nMoon Dev: screenshot saved -> {shot}")

        print("\n=== SUMMARY ===")
        for name, res in results:
            status = "OK" if res["ok"] else "ERR"
            print(f" [{status}] {name}: clicked={res.get('clicked')} "
                  f"studies={res.get('studies_before')}->{res.get('studies_after')} "
                  f"errors={res.get('errors')[:1] if res.get('errors') else []}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
