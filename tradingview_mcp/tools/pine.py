"""
🌙 Moon Dev's Pine Script + Strategy Tester tools.

Pine Editor uses a Monaco-style code editor. We focus the editor's textarea
and drive it with real key events rather than setting `.value` — Monaco
listens for keyboard input, not value mutations.

Strategy Tester results populate asynchronously after a backtest run, so
`tv_get_backtest_results` polls with a timeout rather than assuming instant.
"""
from __future__ import annotations

import json
import re
import platform
import time

from ..cdp_client import CDPClient
from .. import tv_selectors as S
from ._helpers import click_selector, wait_for_selector, with_cdp

# Monaco on macOS uses Cmd (Meta, CDP modifier bit 4). Windows/Linux: Ctrl (bit 2).
# CDP Input.dispatchKeyEvent modifiers are a bitmask: Alt=1, Ctrl=2, Meta=4, Shift=8.
_META_MOD = 4 if platform.system() == "Darwin" else 2


def _focus_pine_textarea(cdp: CDPClient) -> bool:
    """Click into Monaco's hidden textarea so subsequent key events land there."""
    js = """
    (() => {
      const ta = document.querySelector('.monaco-editor textarea');
      if (!ta) return false;
      ta.focus();
      return document.activeElement === ta;
    })()
    """
    return bool(cdp.eval_js(js))


def _open_pine_editor(cdp: CDPClient) -> bool:
    # Attempt to click the Pine Editor tab button in the bottom panel.
    clicked = click_selector(cdp, S.PINE_EDITOR_TAB_BUTTON)
    if not clicked:
        # Fallback: try the generic bottom-panel selector data-name.
        clicked = cdp.eval_js("""
        (() => {
          const btns = document.querySelectorAll('button, [role="tab"]');
          const hit = Array.from(btns).find(b => (b.textContent||'').toLowerCase().includes('pine editor'));
          if (hit) { hit.click(); return true; }
          return false;
        })()
        """)
    return bool(clicked) and wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=4.0)


def _buffer_is_empty(cdp: CDPClient) -> bool:
    """
    True when the Pine Editor buffer holds nothing.

    Monaco caps the hidden textarea mirror at ~200 chars so we cannot read a
    long script back, but an EMPTY buffer always mirrors as an empty string.
    Verifying emptiness is the one read that is always trustworthy. 🌙
    """
    return bool(cdp.eval_js("""
    (() => {
      const ta = document.querySelector('.monaco-editor textarea');
      if (!ta) return false;
      ta.focus();
      document.execCommand('selectAll');
      return ta.value.trim() === '';
    })()
    """))


def _select_all_and_delete(cdp: CDPClient, tries: int = 3) -> bool:
    """
    Empty the Pine Editor, and RETURN WHETHER IT WORKED.

    🚨 Moon Dev, this is the one that mounted a broken script. The old version
    fired Cmd+A as a CDP modifier bitmask and returned None. Monaco ignores
    that bitmask often enough that the select-all silently no-ops, the
    Backspace then deletes a single character, and the next paste APPENDS to
    whatever was already in the buffer. You end up with two scripts in one
    file and TradingView says:

        "Scripts must contain one declaration statement: `indicator()`,
         `strategy()` or `library()`. Your script has 2."

    So: try the key-event route AND document.execCommand('selectAll'), then
    prove the buffer is empty before returning True.
    """
    for _ in range(tries):
        cdp.eval_js("""
        (() => {
          const ta = document.querySelector('.monaco-editor textarea');
          if (ta) { ta.focus(); document.execCommand('selectAll'); }
          return !!ta;
        })()
        """)
        for evt in ("keyDown", "keyUp"):
            cdp.send("Input.dispatchKeyEvent", {
                "type": evt, "key": "a", "code": "KeyA",
                "modifiers": _META_MOD,
                "nativeVirtualKeyCode": 65, "windowsVirtualKeyCode": 65,
            })
        time.sleep(0.15)
        cdp.press_key("Backspace")
        time.sleep(0.35)
        if _buffer_is_empty(cdp):
            return True
    return False


def _paste_text(cdp: CDPClient, text: str) -> None:
    """
    Paste `text` into the focused Monaco editor via a synthetic ClipboardEvent.
    Monaco handles this natively and does NOT apply auto-indent (unlike typing
    each character through Input.insertText, which triggers the language mode's
    auto-format rules and turns flat `if` blocks into nested ones). 🌙
    """
    js = f"""
    (() => {{
      const payload = {json.dumps(text)};
      const ta = document.querySelector('.monaco-editor textarea');
      if (!ta) return false;
      ta.focus();
      const dt = new DataTransfer();
      dt.setData('text/plain', payload);
      const ev = new ClipboardEvent('paste', {{ clipboardData: dt, bubbles: true, cancelable: true }});
      ta.dispatchEvent(ev);
      return true;
    }})()
    """
    cdp.eval_js(js)


# Kept for backwards compat — older code may still call _insert_text.
def _insert_text(cdp: CDPClient, text: str) -> None:
    _paste_text(cdp, text)


def _set_via_monaco(cdp: CDPClient, code: str) -> bool:
    """
    Replace the buffer through Monaco's own model API and read it back to prove
    it took. Only works where the host exposes the `monaco` namespace on window.

    TradingView bundles Monaco as a module, so `window.monaco` is undefined
    there and this returns False. Kept because it's the cleanest route on any
    host that does expose it, and it costs one JS round trip to find out. 🌙
    """
    js = f"""
    (() => {{
      const payload = {json.dumps(code)};
      const m = window.monaco;
      if (!m || !m.editor) return 'no-monaco';
      let target = null;
      if (typeof m.editor.getEditors === 'function') {{
        target = m.editor.getEditors().find(e => e.getModel && e.getModel());
      }}
      if (target) {{
        const model = target.getModel();
        target.executeEdits('moondev', [{{ range: model.getFullModelRange(), text: payload }}]);
        target.pushUndoStop();
        return model.getValue() === payload ? 'ok' : 'mismatch';
      }}
      const models = (m.editor.getModels && m.editor.getModels()) || [];
      if (!models.length) return 'no-model';
      models[0].setValue(payload);
      return models[0].getValue() === payload ? 'ok' : 'mismatch';
    }})()
    """
    return cdp.eval_js(js) == "ok"


def _clear_and_paste(cdp: CDPClient, code: str) -> bool:
    """
    Clear the buffer, PROVE it's empty, then paste. No page reload.

    Moon Dev, this is the trick that kills the ~20s reload. The old code
    reloaded the tab on every write because it "couldn't verify a clear".
    Turns out you don't need to read the buffer back to verify a clear, you
    only need to verify it's EMPTY.

    Monaco mirrors the current selection into its hidden textarea for native
    copy/paste. That mirror is CAPPED (a 3.5 KB script reads back as ~200
    chars), so it is useless for checking a full write. But an empty buffer
    reads back as an empty string every time, and no cap applies to nothing.
    So: select-all, delete, confirm the mirror is empty, then paste into a
    buffer we know is clean.

    We paste via a ClipboardEvent rather than typing: Monaco applies the Pine
    language mode's auto-indent to typed characters and would nest flat `if`
    blocks.
    """
    if not _focus_pine_textarea(cdp):
        return False

    if not _select_all_and_delete(cdp):
        return False  # buffer would not clear — caller falls back to a reload

    _paste_text(cdp, code)
    time.sleep(0.8)
    _nudge_dirty(cdp)   # arm TV's Add/Update button — a paste alone won't
    return True


def _cursor_line(cdp: CDPClient) -> int:
    """
    Which line the caret is on, straight off the Pine Editor status bar.

    Monaco's hidden textarea caps its mirror at ~200 chars so we cannot read a
    3.5 KB script back to check a write. But the status bar reads "Line 63,
    Col 1", and after a paste the caret sits on the LAST pasted line. So the
    caret line is a cheap, exact proxy for "did the whole thing land". 🌙
    """
    js = """
    (() => {
      const b = Array.from(document.querySelectorAll('button,[role="button"]'))
        .find(x => (x.getAttribute('data-tooltip') || '') === 'Go to line/column');
      const m = b && (b.textContent || '').match(/Line\\s+(\\d+)/);
      return m ? parseInt(m[1], 10) : 0;
    })()
    """
    return int(cdp.eval_js(js) or 0)


def _write_landed(cdp: CDPClient, code: str) -> bool:
    """
    Prove the paste actually replaced the buffer.

    🚨 Moon Dev: without this the MCP will happily click "Add to chart" on
    TradingView's DEFAULT TEMPLATE and report success. We saw exactly that —
    the legend came back reading "My script" instead of our indicator, with
    zero errors anywhere.

    The check is a BAND, not a floor. An earlier version used `got >= expected`
    and passed while the old template was still sitting above our code, which
    is how we shipped a two-declaration file to the chart. Too many lines is
    just as broken as too few.
    """
    expected = len(code.rstrip().splitlines())
    got = _cursor_line(cdp)
    return abs(got - expected) <= 1


def _nudge_dirty(cdp: CDPClient) -> None:
    """
    Type one real character and delete it, to arm TradingView's Add/Update button.

    🚨 Moon Dev, this is the one that cost us. A synthetic ClipboardEvent DOES
    change Monaco's model (the code is visibly in the editor, correctly
    highlighted) but TradingView's own change tracking never sees it, so
    "Add to chart" / "Update on chart" stays `disabled` forever and the script
    silently never mounts. No error anywhere. Only a REAL CDP key event flips
    the dirty flag.

    Verified: button.disabled True -> False after a single space char. 🌙
    """
    cdp.send("Input.dispatchKeyEvent", {"type": "char", "text": " "})
    time.sleep(0.4)
    cdp.press_key("Backspace")
    time.sleep(0.4)


def _console_lines(cdp: CDPClient) -> list[str]:
    """
    Every raw line currently in the Pine console, oldest first.

    🚨 Moon Dev: the console is an APPEND-ONLY LOG. It keeps yesterday's errors
    forever. Reading it whole means a fixed script still reports the error that
    was fixed. Callers must snapshot this BEFORE clicking compile and only look
    at what got added after.
    """
    js = """
    (() => {
      const root = document.querySelector('[class*="consoleWrapper"]')
                || document.querySelector('[data-name="pine-editor-console"]')
                || document.querySelector('[class*="consoleWidget"]');
      if (!root) return [];
      return (root.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean);
    })()
    """
    return list(cdp.eval_js(js) or [])


def _errors_from(lines: list[str]) -> list[str]:
    """Keep only the console lines that describe a problem. 🌙"""
    benign = ("opened", "compiling", "compiled", "added to chart",
              "saved", "script saved", "updated on chart", "removed from chart")
    out, seen = [], set()
    for raw in lines:
        line = re.sub(r"^\s*\d{1,2}:\d{2}:\d{2}\s*(AM|PM)?\s*", "", raw, flags=re.I).strip()
        if not line or len(line) > 500 or line in seen:
            continue
        # TV writes these with trailing punctuation ("Compiled.", "Added to
        # chart."), so normalize before matching or every success reads as an
        # error. 🌙
        norm = line.lower().rstrip(". \t")
        if any(norm.endswith(b) for b in benign):
            continue
        seen.add(line)
        out.append(line)
    return out


def _read_pine_errors(cdp: CDPClient) -> list[str]:
    """
    Read compile errors out of the Pine Editor console ONLY.

    Moon Dev note: this used to also match `[class*="error"]` across the whole
    document, which hit any unrelated element on the page with "error" in a
    class name. That invented failures on scripts that compiled fine. We now
    stay inside the console container and take only rows the console itself
    marks as errors.
    """
    js = """
    (() => {
      const root = document.querySelector('[class*="consoleWrapper"]')
                || document.querySelector('[data-name="pine-editor-console"]')
                || document.querySelector('[class*="consoleWidget"]');
      if (!root) return [];
      // The console is a timestamped log. Everything that is NOT one of TV's
      // routine status lines is a problem worth reporting.
      const benign = /(opened|Compiling\\.\\.\\.|Compiled|Added to chart|Saved|Script saved)\\s*$/i;
      const seen = new Set(), out = [];
      for (const raw of (root.innerText || '').split('\\n')) {
        const line = raw.replace(/^\\s*\\d{1,2}:\\d{2}:\\d{2}\\s*(AM|PM)?\\s*/i, '').trim();
        if (!line || line.length > 500 || benign.test(line) || seen.has(line)) continue;
        seen.add(line);
        out.push(line);
      }
      return out;
    })()
    """
    res = cdp.eval_js(js)
    return list(res or [])


def _legend_titles(cdp: CDPClient) -> list[str]:
    """
    Titles of every study currently mounted on the chart.

    🚨 Moon Dev: TradingView REMOVED `data-name="legend-source-item"` and
    `data-name="legend-source-title"` from the chart legend. Both now return
    zero nodes, so the old reader reported an empty legend on a chart that
    plainly had studies on it. The legend is hashed CSS modules now
    (`sources-quatTGAC`, `titlesWrapper-quatTGAC`) and that hash changes on
    every TV deploy, so we match on the stable class PREFIX. We still try the
    old data-name route first in case it ever comes back.
    """
    js = """
    (() => {
      const grab = (sel) => Array.from(document.querySelectorAll(sel))
        .map(n => (n.innerText || n.textContent || '').trim().split('\\n')[0])
        .filter(Boolean);
      let out = grab('[data-name="legend-source-item"] [data-name="legend-source-title"]');
      if (!out.length) out = grab('[class*="sources-"] [class*="titlesWrapper"]');
      if (!out.length) out = grab('[class*="sourcesWrapper"] [class*="title"]');
      return Array.from(new Set(out));
    })()
    """
    return list(cdp.eval_js(js) or [])


def _read_strategy_metrics(cdp: CDPClient) -> dict:
    """Pull the Strategy Tester overview metrics. Returns whatever it can find."""
    js = """
    (() => {
      const root = document.querySelector('[data-name="backtesting-content-wrapper"]');
      if (!root) return null;
      const pick = (sel) => {
        const el = root.querySelector(sel);
        return el ? el.textContent.trim() : null;
      };
      return {
        net_profit: pick('[data-name="net-profit"]'),
        max_drawdown: pick('[data-name="max-drawdown"]'),
        win_rate: pick('[data-name="percent-profitable"]'),
        profit_factor: pick('[data-name="profit-factor"]'),
        total_trades: pick('[data-name="total-trades"]'),
        raw_text: root.textContent.trim().slice(0, 2000),
      };
    })()
    """
    return cdp.eval_js(js) or {}


def register(mcp) -> None:

    @mcp.tool()
    @with_cdp("tv_open_pine_editor")
    def tv_open_pine_editor(cdp: CDPClient) -> dict:
        """🌙 Open the Pine Editor panel at the bottom of the chart."""
        ok = _open_pine_editor(cdp)
        return {"status": "ok" if ok else "error",
                "opened": ok,
                **({} if ok else {"error": "could not open Pine Editor panel"})}

    @mcp.tool()
    @with_cdp("tv_write_pine_script")
    def tv_write_pine_script(cdp: CDPClient, code: str) -> dict:
        """
        🌙 Replace the Pine Editor contents with `code`. Opens the editor if needed.
        Does not compile — call tv_compile_pine_script next.
        """
        if not isinstance(code, str) or not code.strip():
            return {"status": "error", "error": "code must be a non-empty string"}

        if not wait_for_selector(cdp, S.PINE_EDITOR_TEXTAREA, timeout=0.5):
            if not _open_pine_editor(cdp):
                return {"status": "error", "error": "Pine Editor not reachable"}

        if not _focus_pine_textarea(cdp):
            return {"status": "error", "error": "could not focus Pine Editor textarea"}

        # Fastest path: Monaco's model API, verified with getValue().
        if _set_via_monaco(cdp, code):
            time.sleep(0.3)
            return {"status": "ok", "bytes_written": len(code), "path": "monaco"}

        # Fast path on TradingView: clear, prove empty, paste. No reload. 🌙
        # Two tries: TV sometimes steals focus right after the panel opens.
        for _ in range(2):
            if _clear_and_paste(cdp, code) and _write_landed(cdp, code):
                return {"status": "ok", "bytes_written": len(code),
                        "lines": _cursor_line(cdp), "path": "clear+paste"}
            time.sleep(0.5)

        # Slow path: couldn't prove the buffer was clean. Reload to a known
        # template state, then paste. The beforeunload "Leave site?" dialog is
        # auto-accepted in CDPClient.send, otherwise this would hang forever.
        cdp.send("Page.reload", {"ignoreCache": False})
        deadline = time.time() + 15.0
        while time.time() < deadline and cdp.eval_js("document.readyState") != "complete":
            time.sleep(0.4)
        time.sleep(2.5)  # TV's chart JS needs a moment after readyState
        if not _open_pine_editor(cdp):
            return {"status": "error", "error": "Pine Editor not reachable after reload"}

        # Same verified clear+paste, just on a freshly loaded page.
        if _clear_and_paste(cdp, code) and _write_landed(cdp, code):
            return {"status": "ok", "bytes_written": len(code),
                    "lines": _cursor_line(cdp), "path": "reload+clear+paste"}

        return {"status": "error",
                "error": "write did not land — the editor holds something other than this "
                         "script. Refusing to add-to-chart: that would mount the wrong code.",
                "cursor_line": _cursor_line(cdp),
                "expected_lines": len(code.rstrip().splitlines())}

    @mcp.tool()
    @with_cdp("tv_compile_pine_script")
    def tv_compile_pine_script(cdp: CDPClient, timeout_seconds: float = 12.0) -> dict:
        """🌙 Click Add-to-chart / Update-on-chart, wait for the study to mount,
        and return any compile errors plus the resulting chart legend."""
        # Snapshot BEFORE the click. The console is append-only, so anything
        # already in it belongs to a previous run and is not our error. 🌙
        console_mark = len(_console_lines(cdp))
        before_legend = set(_legend_titles(cdp))

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
            return {"status": "error", "error": "no Add/Update button found"}

        # Wait for the study to actually appear in the legend rather than
        # guessing with a flat sleep. A long script on deep history can take
        # well over 3.5s, and short ones are done in under one. 🌙
        deadline = time.time() + max(2.0, float(timeout_seconds))
        legend: list[str] = []
        while time.time() < deadline:
            time.sleep(0.4)
            legend = _legend_titles(cdp)
            if set(legend) - before_legend or _errors_from(_console_lines(cdp)[console_mark:]):
                break

        errs = _errors_from(_console_lines(cdp)[console_mark:])
        return {
            "status": "ok" if not errs else "error",
            "button": clicked,
            "compile_errors": errs,
            "legend": legend,
        }

    @mcp.tool()
    @with_cdp("tv_save_pine_script")
    def tv_save_pine_script(cdp: CDPClient, script_name: str = "") -> dict:
        """
        🌙 Save the current Pine script to your TradingView account so it stops
        being throwaway. Pass `script_name` to name it, or leave blank to keep
        whatever name the editor already has.
        """
        if script_name:
            renamed = cdp.eval_js(f"""
            (() => {{
              const el = document.querySelector('[data-name="scriptTitle"], [class*="scriptTitle"]');
              if (!el) return false;
              el.click();
              return true;
            }})()
            """)
            if renamed:
                time.sleep(0.6)
                cdp.eval_js(f"""
                (() => {{
                  const inp = document.querySelector('[data-name="script-name-input"], [data-name="dialog"] input');
                  if (!inp) return false;
                  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                  setter.call(inp, {json.dumps(script_name)});
                  inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                  return true;
                }})()
                """)
                time.sleep(0.3)
                cdp.press_key("Enter")
                time.sleep(0.8)

        # Cmd/Ctrl+S is what TV's own editor binds to Save. More stable than
        # chasing the Save button's title text across UI updates.
        for evt in ("keyDown", "keyUp"):
            cdp.send("Input.dispatchKeyEvent", {
                "type": evt, "key": "s", "code": "KeyS",
                "modifiers": _META_MOD,
                "nativeVirtualKeyCode": 83, "windowsVirtualKeyCode": 83,
            })
        time.sleep(2.0)
        errs = _read_pine_errors(cdp)
        return {"status": "ok" if not errs else "error",
                "saved_as": script_name or "(existing name)",
                "errors": errs}

    @mcp.tool()
    @with_cdp("tv_run_strategy_tester")
    def tv_run_strategy_tester(cdp: CDPClient) -> dict:
        """🌙 Open the Strategy Tester panel. TV runs the backtest automatically once the strategy is mounted."""
        clicked = click_selector(cdp, S.STRATEGY_TESTER_TAB)
        if not clicked:
            clicked = cdp.eval_js("""
            (() => {
              const tabs = document.querySelectorAll('button, [role="tab"]');
              const hit = Array.from(tabs).find(t => (t.textContent||'').toLowerCase().includes('strategy tester'));
              if (hit) { hit.click(); return true; }
              return false;
            })()
            """)
        ok = bool(clicked) and wait_for_selector(cdp, S.STRATEGY_TESTER_ROOT, timeout=4.0)
        return {"status": "ok" if ok else "error",
                "opened": ok,
                **({} if ok else {"error": "could not open Strategy Tester"})}

    @mcp.tool()
    @with_cdp("tv_get_backtest_results")
    def tv_get_backtest_results(cdp: CDPClient, timeout_seconds: float = 10.0) -> dict:
        """
        🌙 Poll the Strategy Tester Overview for metrics. Returns whichever metrics
        TV has populated by the timeout.
        """
        deadline = time.time() + max(1.0, float(timeout_seconds))
        last: dict = {}
        while time.time() < deadline:
            last = _read_strategy_metrics(cdp)
            # "populated enough" heuristic: at least net_profit has a value.
            if last and last.get("net_profit"):
                return {"status": "ok", "metrics": last}
            time.sleep(0.5)
        return {"status": "partial", "metrics": last, "note": "timed out waiting for full metrics"}
