"""
🌙 Moon Dev's indicator tools.

TradingView's indicator ecosystem is huge — built-ins, community scripts,
invite-only. These tools target the common flow: open the Indicators dialog,
search by name, add the first match, optionally configure params, then read
back what's on the chart from the legend.
"""
from __future__ import annotations

import json
import time

from ..cdp_client import CDPClient
from .. import tv_selectors as S
from ._helpers import click_selector, focus_chart, press_escape, wait_for_selector, with_cdp


# ---------------------------------------------------------------------------
# helpers (not exposed as tools)
# ---------------------------------------------------------------------------

def _open_indicators_dialog(cdp: CDPClient) -> bool:
    # Try the button first, then keyboard shortcut.
    if click_selector(cdp, S.INDICATORS_DIALOG_OPEN_BUTTON):
        return wait_for_selector(cdp, S.INDICATORS_DIALOG_ROOT, timeout=4.0)
    # Fallback: "/" focuses symbol search on TV. Indicators shortcut is "Ctrl+I" on web.
    focus_chart(cdp)
    cdp.send("Input.dispatchKeyEvent", {
        "type": "keyDown", "key": "i", "modifiers": 2,  # 2 = Ctrl
    })
    cdp.send("Input.dispatchKeyEvent", {
        "type": "keyUp", "key": "i", "modifiers": 2,
    })
    return wait_for_selector(cdp, S.INDICATORS_DIALOG_ROOT, timeout=4.0)


def _close_dialog(cdp: CDPClient) -> None:
    press_escape(cdp)
    time.sleep(0.2)


def _read_legend(cdp: CDPClient) -> list[dict]:
    """Scrape the chart legend for currently attached studies and their values."""
    js = """
    (() => {
      const items = Array.from(document.querySelectorAll('[data-name="legend-source-item"]'));
      return items.map((el, idx) => {
        const titleEl = el.querySelector('[data-name="legend-source-title"]');
        const valueEls = Array.from(el.querySelectorAll('[class*="valueItem"]'));
        return {
          index: idx,
          title: titleEl ? titleEl.textContent.trim() : '',
          values: valueEls.map(v => v.textContent.trim()),
        };
      });
    })()
    """
    data = cdp.eval_js(js) or []
    return [d for d in data if isinstance(d, dict) and d.get("title")]


def _maybe_open_study_settings(cdp: CDPClient, params: dict) -> dict:
    """
    Fill numeric/text inputs in the study-dialog with the given keyword params.
    Input labels on TV are localized, so we match loosely by placeholder or
    label sibling text.
    """
    if not params:
        return {"params_applied": {}, "note": "no params to apply"}

    # Give TV a beat — the study dialog sometimes animates in.
    if not wait_for_selector(cdp, S.STUDY_SETTINGS_DIALOG, timeout=1.5):
        # Many built-ins auto-close their settings dialog; no-op is fine.
        return {"params_applied": {}, "note": "no settings dialog visible"}

    applied: dict = {}
    js_fill = """
    (keysAndValues) => {
      const dialog = document.querySelector('[data-name="study-dialog"]');
      if (!dialog) return {applied: {}, skipped: keysAndValues};
      const inputs = Array.from(dialog.querySelectorAll('input'));
      const applied = {};
      const skipped = {};
      for (const [key, val] of Object.entries(keysAndValues)) {
        const match = inputs.find(inp => {
          const label = (inp.closest('[class*="cell"]') || inp.parentElement || {}).textContent || '';
          const placeholder = inp.placeholder || '';
          return (label + ' ' + placeholder).toLowerCase().includes(String(key).toLowerCase());
        });
        if (match) {
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(match, String(val));
          match.dispatchEvent(new Event('input', {bubbles: true}));
          match.dispatchEvent(new Event('change', {bubbles: true}));
          applied[key] = val;
        } else {
          skipped[key] = val;
        }
      }
      return {applied, skipped};
    }
    """
    res = cdp.eval_js(f"({js_fill})({json.dumps(params)})") or {}
    applied = res.get("applied", {}) if isinstance(res, dict) else {}
    # Click OK to close the dialog.
    click_selector(cdp, S.STUDY_SETTINGS_OK)
    time.sleep(0.3)
    return {"params_applied": applied, "params_skipped": (res or {}).get("skipped", {})}


# ---------------------------------------------------------------------------
# tool registration
# ---------------------------------------------------------------------------

def register(mcp) -> None:

    @mcp.tool()
    @with_cdp("tv_add_indicator")
    def tv_add_indicator(cdp: CDPClient, name: str, params: dict | None = None) -> dict:
        """
        🌙 Add an indicator by name (e.g. "RSI", "MACD", "Volume").
        Optional `params` is a dict of parameter name → value (e.g. {"length": 14}).
        """
        if not name:
            return {"status": "error", "error": "indicator name required"}
        params = params or {}

        if not _open_indicators_dialog(cdp):
            return {"status": "error", "error": "could not open Indicators dialog"}

        # Type the search term.
        cdp.eval_js(f"""
        (() => {{
          const inp = document.querySelector({json.dumps(S.INDICATORS_DIALOG_SEARCH)});
          if (!inp) return false;
          inp.focus();
          const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
          setter.call(inp, {json.dumps(name)});
          inp.dispatchEvent(new Event('input', {{bubbles: true}}));
          return true;
        }})()
        """)
        time.sleep(0.5)

        # Click the first result.
        clicked = click_selector(cdp, S.INDICATORS_DIALOG_RESULT, nth=0)
        if not clicked:
            _close_dialog(cdp)
            return {"status": "error", "error": f"no indicator found matching {name!r}"}

        time.sleep(0.4)
        _close_dialog(cdp)

        # If the user passed params, try to open the indicator's settings and fill them.
        params_info: dict = {}
        if params:
            legend = _read_legend(cdp)
            if legend:
                # Double-click the most recently added legend row to open its settings.
                last_idx = len(legend) - 1
                cdp.eval_js(f"""
                (() => {{
                  const items = document.querySelectorAll('[data-name="legend-source-item"]');
                  const el = items[{last_idx}];
                  if (!el) return false;
                  const ev = new MouseEvent('dblclick', {{bubbles:true, cancelable:true}});
                  el.dispatchEvent(ev);
                  return true;
                }})()
                """)
                time.sleep(0.6)
                params_info = _maybe_open_study_settings(cdp, params)

        return {
            "status": "ok",
            "indicator": name,
            "active_legend": _read_legend(cdp),
            **params_info,
        }

    @mcp.tool()
    @with_cdp("tv_remove_indicator")
    def tv_remove_indicator(cdp: CDPClient, name_or_index: str | int) -> dict:
        """🌙 Remove a specific indicator by name (case-insensitive substring) or zero-based index."""
        legend = _read_legend(cdp)
        if not legend:
            return {"status": "ok", "removed": None, "note": "legend empty"}

        target_idx: int | None = None
        if isinstance(name_or_index, int):
            target_idx = name_or_index if 0 <= name_or_index < len(legend) else None
        else:
            needle = str(name_or_index).lower()
            for item in legend:
                if needle in item["title"].lower():
                    target_idx = item["index"]
                    break

        if target_idx is None:
            return {"status": "error", "error": f"no legend match for {name_or_index!r}", "legend": legend}

        # Hover the legend row so action buttons appear, then click delete.
        ok = cdp.eval_js(f"""
        (() => {{
          const items = document.querySelectorAll('[data-name="legend-source-item"]');
          const el = items[{target_idx}];
          if (!el) return false;
          el.dispatchEvent(new MouseEvent('mouseover', {{bubbles:true}}));
          const del = el.querySelector('[data-name="legend-action-panel"] [data-name="delete"]');
          if (del) {{ del.click(); return true; }}
          // Fallback: right-click → "Remove <name>"
          return false;
        }})()
        """)
        time.sleep(0.3)
        return {"status": "ok", "removed_index": target_idx, "clicked": bool(ok), "legend": _read_legend(cdp)}

    @mcp.tool()
    @with_cdp("tv_remove_all_indicators")
    def tv_remove_all_indicators(cdp: CDPClient) -> dict:
        """🌙 Remove every attached indicator/study from the chart."""
        legend = _read_legend(cdp)
        removed: list[str] = []
        # Iterate in reverse so indices stay valid as rows disappear.
        for item in sorted(legend, key=lambda x: -x["index"]):
            idx = item["index"]
            cdp.eval_js(f"""
            (() => {{
              const items = document.querySelectorAll('[data-name="legend-source-item"]');
              const el = items[{idx}];
              if (!el) return false;
              el.dispatchEvent(new MouseEvent('mouseover', {{bubbles:true}}));
              const del = el.querySelector('[data-name="legend-action-panel"] [data-name="delete"]');
              if (del) {{ del.click(); return true; }}
              return false;
            }})()
            """)
            time.sleep(0.2)
            removed.append(item["title"])
        return {"status": "ok", "removed": removed, "legend": _read_legend(cdp)}

    @mcp.tool()
    @with_cdp("tv_list_indicators")
    def tv_list_indicators(cdp: CDPClient) -> dict:
        """🌙 Return the list of currently attached indicators and their displayed values."""
        return {"status": "ok", "legend": _read_legend(cdp)}

    @mcp.tool()
    @with_cdp("tv_read_indicator_value")
    def tv_read_indicator_value(cdp: CDPClient, name: str) -> dict:
        """🌙 Read the current numeric value(s) of an indicator by name substring (e.g. "RSI")."""
        needle = (name or "").lower()
        if not needle:
            return {"status": "error", "error": "name required"}
        for item in _read_legend(cdp):
            if needle in item["title"].lower():
                return {"status": "ok", "name": item["title"], "values": item["values"]}
        return {"status": "error", "error": f"indicator {name!r} not on chart", "legend": _read_legend(cdp)}
