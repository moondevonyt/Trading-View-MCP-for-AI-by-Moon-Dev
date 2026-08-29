"""
Moon Dev driver: push the minimal GEX (Traps + Sweeps only) script into the
live TradingView Pine editor. Mirrors run_gex_combined_v2's atomic select-all +
paste so Monaco replaces the editor contents in one shot.
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path

from tradingview_mcp.cdp_client import open_tv_client
from tradingview_mcp.tools.pine import _open_pine_editor, _read_pine_errors
from tradingview_mcp.tools._helpers import wait_for_selector
from tradingview_mcp import tv_selectors as S

SCRIPT = Path(__file__).parent / "examples" / "moon_dev_gex_minimal.pine"
SHOT   = Path(__file__).parent / "moon_dev_gex_minimal_shot.png"


def main() -> int:
    code = SCRIPT.read_text()
    print(f"Moon Dev: loaded {len(code)} bytes of minimal GEX script")

    cdp = open_tv_client()
    cdp.connect()
    print("Moon Dev: connected to TradingView tab")
    try:
        # Make sure Pine Editor panel is open AND its Monaco textarea has
        # finished mounting before we attempt the atomic select-all + paste.
        # The panel can open in ~100ms but Monaco often takes a few seconds
        # to lazy-load on a cold panel.
        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            print("Moon Dev: opening Pine editor panel...")
            _open_pine_editor(cdp)
        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=15.0, poll=0.25):
            print("ERROR: Monaco textarea did not appear within 15s")
            cdp.screenshot(SHOT)
            return 1
        print("Moon Dev: Monaco textarea ready")
        time.sleep(0.8)  # let Monaco settle once the element exists

        # Atomic Ctrl/Cmd+A then paste, all in one JS block so Monaco doesn't
        # race against our state changes. 🌙
        replace_js = r"""
        (() => {
          const payload = __PAYLOAD__;
          const ta = document.querySelector('.monaco-editor textarea');
          if (!ta) return {ok: false, why: 'no textarea'};
          ta.focus();
          ta.click();
          const isMac = navigator.platform.toLowerCase().includes('mac');
          const keyEv = new KeyboardEvent('keydown', {
            key: 'a', code: 'KeyA', keyCode: 65, which: 65,
            ctrlKey: !isMac, metaKey: isMac,
            bubbles: true, cancelable: true
          });
          ta.dispatchEvent(keyEv);
          return new Promise(r => setTimeout(() => {
            const dt = new DataTransfer();
            dt.setData('text/plain', payload);
            const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true });
            ta.dispatchEvent(ev);
            r({ok: true});
          }, 250));
        })()
        """.replace("__PAYLOAD__", json.dumps(code))

        res = cdp.eval_js(replace_js)
        print(f"Moon Dev: paste step -> {res}")
        time.sleep(2.5)

        cursor = cdp.eval_js(r"""
        (() => {
          const all = document.querySelectorAll('button, span, div');
          for (const e of all) {
            const t = (e.textContent||'').trim();
            if (/^Line\s+\d+,\s*Col\s+\d+$/.test(t)) return t;
          }
          return '';
        })()
        """)
        print(f"Moon Dev: cursor -> {cursor}")

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
        print(f"\nLegend ({len(legend)}):")
        for l in legend:
            print(f"  - {l}")

        errs = _read_pine_errors(cdp)
        if errs:
            print("\nMoon Dev: recent errors:")
            for e in errs[-5:]:
                print(f"  - {e}")
        else:
            print("\nMoon Dev: no compile errors")

        shot = cdp.screenshot(SHOT)
        print(f"\nMoon Dev: screenshot -> {shot}")
    finally:
        cdp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
