"""
Moon Dev driver v2 - sync select-all + paste in one JS call so Monaco
replaces all content with the combined script atomically.
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path

from tradingview_mcp.cdp_client import open_tv_client
from tradingview_mcp.tools.pine import _open_pine_editor, _read_pine_errors
from tradingview_mcp.tools._helpers import wait_for_selector
from tradingview_mcp import tv_selectors as S

SCRIPT = Path(__file__).parent / "examples" / "moon_dev_gex_combined.pine"


def main() -> int:
    code = SCRIPT.read_text()
    print(f"Moon Dev: loaded {len(code)} bytes")

    cdp = open_tv_client()
    cdp.connect()
    print("Moon Dev: connected")
    try:
        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            _open_pine_editor(cdp)

        # 1. Get the Monaco textarea element
        # 2. Focus it
        # 3. Dispatch a synthetic Ctrl+A KeyboardEvent (Monaco listens for these directly)
        # 4. Wait micro
        # 5. Dispatch paste event with the full text
        # All in one JS block so Monaco doesn't race against our state.
        replace_js = r"""
        (() => {
          const payload = __PAYLOAD__;
          const ta = document.querySelector('.monaco-editor textarea');
          if (!ta) return {ok: false, why: 'no textarea'};
          ta.focus();
          const isMac = navigator.platform.toLowerCase().includes('mac');
          // First, click into the editor to ensure Monaco knows cursor is in the doc
          ta.click();
          // Now dispatch Ctrl/Meta+A
          const keyEv = new KeyboardEvent('keydown', {
            key: 'a', code: 'KeyA', keyCode: 65, which: 65,
            ctrlKey: !isMac, metaKey: isMac,
            bubbles: true, cancelable: true
          });
          ta.dispatchEvent(keyEv);
          // Wait one tick before paste so Monaco processes the selection
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
        print(f"replace step: {res}")
        time.sleep(2.5)

        # Verify cursor/line state
        info = cdp.eval_js(r"""
        (() => {
          const all = document.querySelectorAll('button, span, div');
          for (const e of all) {
            const t = (e.textContent||'').trim();
            if (/^Line\s+\d+,\s*Col\s+\d+$/.test(t)) return t;
          }
          return '';
        })()
        """)
        print(f"Cursor info: {info}")

        # Click Add to chart / Update on chart
        clicked = cdp.eval_js("""
        (() => {
          for (const t of ['Add to chart', 'Update on chart', 'Save script']) {
            const b = document.querySelector('button[title=' + JSON.stringify(t) + ']');
            if (b && !b.disabled) { b.click(); return t; }
          }
          return null;
        })()
        """)
        print(f"Clicked: {clicked}")
        time.sleep(7)

        legend = cdp.eval_js("""
        (() => {
          const items = document.querySelectorAll('[data-name="legend-source-item"]');
          return Array.from(items).map(it => (it.textContent||'').trim().slice(0,80));
        })()
        """) or []
        print(f"\nLegend ({len(legend)}):")
        for l in legend:
            print(f"  - {l}")

        errs = _read_pine_errors(cdp)
        if errs:
            print("\nRecent errors:")
            for e in errs[-3:]:
                print(f"  - {e}")
    finally:
        cdp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
