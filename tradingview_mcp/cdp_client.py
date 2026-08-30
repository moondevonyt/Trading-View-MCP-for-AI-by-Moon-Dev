"""
🌙 Moon Dev's Chrome DevTools Protocol client.

Minimal CDP client built on websocket-client. We don't need the full pychrome
surface — just:
  - discover the TradingView tab via /json
  - open a WebSocket to its debugger
  - run synchronous request/response over CDP
  - execute JS, take screenshots, dispatch key events, press Enter, etc.

Every method that touches TV returns a plain dict/str/bool so tools stay
JSON-serializable. No hidden magic.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websocket  # websocket-client

from .chrome_launcher import CDP_PORT, launch_chrome

TV_URL_MATCH = "tradingview.com"


class CDPError(RuntimeError):
    """Moon Dev: raised when a CDP call fails on the remote side."""


@dataclass
class CDPTab:
    id: str
    title: str
    url: str
    ws_url: str


class CDPClient:
    """One client per TradingView tab. Thread-safe for a single caller at a time."""

    def __init__(self, ws_url: str, timeout: float = 10.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: websocket.WebSocket | None = None
        self._msg_id = 0
        self._lock = threading.Lock()

    # ----- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        self._ws = websocket.create_connection(self.ws_url, timeout=self.timeout)
        # Enable the domains we use most. Input has no .enable method.
        for domain in ("Page", "Runtime", "DOM"):
            self.send(f"{domain}.enable")
        # 🌙 Moon Dev: About to drive this page, so give it real keyboard focus.
        # This is the choke point every script goes through — some build a client
        # straight from find_tradingview_tab() instead of open_tv_client().
        # No-op on a standalone Chrome. See the control-endpoint block below for
        # the two things that break without it (Pine Editor ignores keys, and
        # stray keys leak into whatever the host app has focused).
        focus_moondev_tab()

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    def __enter__(self) -> "CDPClient":
        self.connect()
        return self

    def __exit__(self, *a) -> None:
        self.close()

    # ----- raw protocol ------------------------------------------------------
    def send(self, method: str, params: dict | None = None) -> dict:
        """Send a CDP command synchronously and return the result dict."""
        if self._ws is None:
            self.connect()
        with self._lock:
            self._msg_id += 1
            msg_id = self._msg_id
            payload = {"id": msg_id, "method": method, "params": params or {}}
            assert self._ws is not None
            self._ws.send(json.dumps(payload))
            # Drain frames until we see our reply (ignore async events).
            deadline = time.time() + self.timeout
            while time.time() < deadline:
                raw = self._ws.recv()
                if not raw:
                    continue
                data = json.loads(raw)
                # 🚨 Moon Dev: TradingView registers a beforeunload handler, so
                # ANY reload/navigate pops Chrome's native "Leave site? Changes
                # you made may not be saved" dialog. That dialog BLOCKS the page
                # until a human clicks it, so Page.reload just hangs and every
                # write after it silently lands on the old buffer. Auto-accept
                # it here. Fire-and-forget: we must not wait for a reply while
                # we're already mid-drain.
                if data.get("method") == "Page.javascriptDialogOpening":
                    self._msg_id += 1
                    self._ws.send(json.dumps({
                        "id": self._msg_id,
                        "method": "Page.handleJavaScriptDialog",
                        "params": {"accept": True},
                    }))
                    continue
                if data.get("id") == msg_id:
                    if "error" in data:
                        raise CDPError(f"{method}: {data['error']}")
                    return data.get("result", {})
            raise CDPError(f"{method}: timeout waiting for reply")

    # ----- JS execution ------------------------------------------------------
    def eval_js(self, expression: str, await_promise: bool = True, return_by_value: bool = True) -> Any:
        """Run JS in the page context. Returns the JSON-decoded value."""
        res = self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": return_by_value,
                "userGesture": True,
            },
        )
        r = res.get("result", {})
        if res.get("exceptionDetails"):
            msg = res["exceptionDetails"].get("text") or str(res["exceptionDetails"])
            raise CDPError(f"JS exception: {msg}")
        # Runtime.evaluate wraps the value in {type, value} even with returnByValue.
        if "value" in r:
            return r["value"]
        return r

    # ----- convenience: screenshot ------------------------------------------
    def screenshot(self, path: str | Path) -> str:
        path = Path(os.path.expanduser(str(path)))
        path.parent.mkdir(parents=True, exist_ok=True)
        res = self.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        b64 = res.get("data", "")
        path.write_bytes(base64.b64decode(b64))
        return str(path)

    # ----- convenience: key events ------------------------------------------
    # 🚨 Moon Dev: a key event with ONLY {"type","key"} is ignored by Monaco.
    # Measured: bare Backspace left a 635-char buffer untouched; the same key
    # with code + virtual key codes cleared it to 0. Editors check the virtual
    # key code, not the `key` string, so every non-text key needs its number.
    _VKEYS = {
        "Backspace": 8, "Tab": 9, "Enter": 13, "Escape": 27, "Delete": 46,
        "ArrowLeft": 37, "ArrowUp": 38, "ArrowRight": 39, "ArrowDown": 40,
        "Home": 36, "End": 35, "PageUp": 33, "PageDown": 34,
    }

    def press_key(self, key: str) -> None:
        """
        Dispatch a real keydown+keyup via Input.dispatchKeyEvent.

        Uses `rawKeyDown` (not `keyDown`) because these are non-text keys —
        a `keyDown` carrying text would try to insert a character instead.
        """
        vk = self._VKEYS.get(key, 0)
        for evt in ("rawKeyDown", "keyUp"):
            self.send("Input.dispatchKeyEvent", {
                "type": evt, "key": key, "code": key,
                "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk,
            })

    def type_text(self, text: str) -> None:
        """Type unicode text as a sequence of char events (DOM-level, respects focus)."""
        for ch in text:
            self.send("Input.dispatchKeyEvent", {"type": "char", "text": ch})


# --- tab discovery -----------------------------------------------------------

def list_tabs(port: int = CDP_PORT, timeout: float = 3.0) -> list[CDPTab]:
    r = requests.get(f"http://127.0.0.1:{port}/json", timeout=timeout)
    r.raise_for_status()
    # Moon Dev: Accept "page" (standalone Chrome top-level tabs) AND "webview"
    # (Electron's <webview> tags — how the Moon Dev Code App exposes its browser
    # overlays). Also drop any target without a WS URL, they're not drivable.
    ALLOWED = {"page", "webview"}
    out: list[CDPTab] = []
    for entry in r.json():
        if entry.get("type") not in ALLOWED:
            continue
        ws_url = entry.get("webSocketDebuggerUrl", "")
        if not ws_url:
            continue
        out.append(CDPTab(
            id=entry.get("id", ""),
            title=entry.get("title", ""),
            url=entry.get("url", ""),
            ws_url=ws_url,
        ))
    return out


MCP_TAB_MARKER = "moondev_mcp=1"


# ============================================================================
# 🌙 Moon Dev Code App control endpoint (optional, ignored on plain Chrome)
#
# When the chart lives inside Moon Dev Code App, CDP alone is not enough. CDP
# can read and click a page, but it cannot give that page real KEYBOARD focus.
# Two things break without it:
#
#   1. TradingView's Pine Editor only accepts keys when the page truly has
#      focus. Without it, everything we "type" goes nowhere.
#   2. A key the page does not handle (our Escape, for one) gets handed back by
#      Chromium to the app hosting the page, and lands on whatever has focus
#      there. Measured Aug 30 2026: with a terminal focused, an Escape sent to
#      the chart arrived in that terminal as a raw \x1b. If a Claude Code
#      session is sitting in it, that reads as "the user pressed Escape" and
#      the run dies. Focusing the page first makes the leak stop dead.
#
# All of this is best-effort. On a standalone Chrome there is no endpoint, the
# call fails in under a second, and nothing changes.
# ============================================================================
MOONDEV_CTRL_ENV = "MOONDEV_CTRL"
MOONDEV_CTRL_DEFAULT = "http://127.0.0.1:8765"
MOONDEV_ENDPOINT_FILE = (
    Path.home() / "Library/Application Support/Moon Dev Code App/mcp-endpoint.json"
)

_moondev_ctrl_cache: Any = "unset"  # "unset" = not probed yet, None = not there


def moondev_control_url() -> str | None:
    """Base URL of the Code App's control endpoint, or None if it isn't running.

    Order: MOONDEV_CTRL env var, then the app's own endpoint file, then the
    default port. Probed once per process.
    """
    global _moondev_ctrl_cache
    if _moondev_ctrl_cache != "unset":
        return _moondev_ctrl_cache

    candidates: list[str] = []
    env = os.environ.get(MOONDEV_CTRL_ENV)
    if env:
        candidates.append(env.rstrip("/"))
    try:
        if MOONDEV_ENDPOINT_FILE.exists():
            info = json.loads(MOONDEV_ENDPOINT_FILE.read_text())
            if info.get("controlUrl"):
                candidates.append(str(info["controlUrl"]).rstrip("/"))
    except Exception:
        pass
    candidates.append(MOONDEV_CTRL_DEFAULT)

    for base in candidates:
        try:
            r = requests.get(f"{base}/mcp/health", timeout=1.5)
            if r.ok and r.json().get("app") == "Moon Dev Code App":
                print(f"🌙 Moon Dev: driving the Code App browser via {base}")
                _moondev_ctrl_cache = base
                return base
        except Exception:
            continue

    _moondev_ctrl_cache = None
    return None


def focus_moondev_tab() -> bool:
    """Give the Code App's MCP tab real keyboard focus. No-op on plain Chrome."""
    base = moondev_control_url()
    if not base:
        return False
    try:
        r = requests.post(f"{base}/mcp/tv/focus", timeout=5)
        return bool(r.ok and r.json().get("ok"))
    except Exception:
        return False


def find_tradingview_tab(port: int = CDP_PORT, url_match: str = TV_URL_MATCH) -> CDPTab:
    """Pick the tab whose URL contains tradingview.com. Raise if none found.

    Preference order:
      1. Tabs whose URL contains the MCP marker (opened via Moon Dev Code App's
         File → New TradingView Tab (for MCP) menu). This keeps the user's own
         TradingView tab untouched when they're working in the MCP.
      2. Tabs whose URL contains /chart/ (an actual chart view).
      3. Shortest URL (usually the newest / cleanest tab).
    """
    tabs = list_tabs(port)
    hits = [t for t in tabs if url_match in t.url]
    if not hits:
        urls = ", ".join(t.url for t in tabs) or "(none)"
        raise CDPError(
            f"🌙 Moon Dev: no TradingView tab found on CDP port {port}. "
            "If you're using Moon Dev Code App, either press ⌘⇧T (or use "
            "File → New TradingView Tab for MCP) to spawn a dedicated tab, "
            "or ⌘O to open any browser and navigate to tradingview.com. "
            f"Current tabs: {urls}"
        )
    # Moon Dev: Prefer MCP-marked tabs so the user's personal TV tab stays theirs
    marked = [t for t in hits if MCP_TAB_MARKER in t.url]
    if marked:
        hits = marked
    hits.sort(key=lambda t: ("/chart" not in t.url, len(t.url)))
    return hits[0]


def open_tv_client(port: int = CDP_PORT, ensure_chrome: bool = True) -> CDPClient:
    """
    Convenience constructor: make sure Chrome is running, find the TV tab, return a
    connected client. Callers should use this as a context manager.
    """
    # Moon Dev: If Moon Dev Code App is serving CDP on this port, that IS the
    # browser we want — do not spawn a second Chrome beside it.
    in_moondev_app = moondev_control_url() is not None
    if ensure_chrome and not in_moondev_app:
        launch_chrome()  # no-op if already running
    tab = find_tradingview_tab(port)
    # Moon Dev: the page gets real keyboard focus in CDPClient.connect(), so every
    # caller is covered, not just this one.
    return CDPClient(tab.ws_url)
