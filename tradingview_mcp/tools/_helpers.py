"""
🌙 Moon Dev's shared helpers for MCP tool functions.

The `with_cdp` decorator keeps tool bodies focused on what to do, while
handling the CDP connection lifecycle, timing, logging, and surfacing errors
as structured dicts instead of throwing.
"""
from __future__ import annotations

import inspect
import json
import time
from functools import wraps
from typing import Any, Callable

from ..cdp_client import CDPClient, open_tv_client
from ..tool_log import log_call


def with_cdp(tool_name: str) -> Callable:
    """
    Decorator: inject a connected CDPClient as the first arg; log the call.

    Hides the `cdp` parameter from FastMCP's JSON schema generation so Claude
    only sees the user-facing arguments.
    """
    def decorator(fn: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
        sig = inspect.signature(fn)
        visible_params = list(sig.parameters.values())[1:]  # drop `cdp`
        new_sig = sig.replace(parameters=visible_params)
        visible_annotations = {
            k: v for k, v in getattr(fn, "__annotations__", {}).items() if k != "cdp"
        }

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            t0 = time.time()
            try:
                with open_tv_client() as cdp:
                    result = fn(cdp, *args, **kwargs)
            except Exception as exc:
                result = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
            log_call(tool_name, kwargs or dict(enumerate(args)), result, (time.time() - t0) * 1000)
            return result

        wrapper.__signature__ = new_sig  # type: ignore[attr-defined]
        wrapper.__annotations__ = visible_annotations
        return wrapper
    return decorator


def wait_for_selector(cdp: CDPClient, selector: str, timeout: float = 5.0, poll: float = 0.15) -> bool:
    """Poll document.querySelector until the element exists or timeout."""
    deadline = time.time() + timeout
    js = f"document.querySelector({json.dumps(selector)}) !== null"
    while time.time() < deadline:
        if cdp.eval_js(js):
            return True
        time.sleep(poll)
    return False


def click_selector(cdp: CDPClient, selector: str, *, nth: int = 0) -> bool:
    """Click the nth element matching a CSS selector. Returns True if clicked."""
    js = f"""
    (() => {{
      const els = document.querySelectorAll({json.dumps(selector)});
      const el = els[{nth}];
      if (!el) return false;
      el.scrollIntoView({{block: 'center'}});
      el.click();
      return true;
    }})()
    """
    return bool(cdp.eval_js(js))


def focus_chart(cdp: CDPClient) -> None:
    """Click the middle of the chart canvas so keyboard events land there."""
    js = """
    (() => {
      const c = document.querySelector('.chart-markup-table') || document.querySelector('canvas');
      if (!c) return false;
      const r = c.getBoundingClientRect();
      const x = r.left + r.width/2, y = r.top + r.height/2;
      const opts = {bubbles:true, cancelable:true, clientX:x, clientY:y, button:0};
      c.dispatchEvent(new MouseEvent('mousedown', opts));
      c.dispatchEvent(new MouseEvent('mouseup', opts));
      c.dispatchEvent(new MouseEvent('click', opts));
      return true;
    })()
    """
    cdp.eval_js(js)


def press_escape(cdp: CDPClient) -> None:
    cdp.press_key("Escape")
