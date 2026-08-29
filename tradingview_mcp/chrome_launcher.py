"""
🌙 Moon Dev's dedicated Chrome launcher for TradingView MCP.

Launches a dedicated Chrome profile with remote debugging enabled. Separate
from the user's main Chrome so banking/email/exchange sessions are NOT exposed
to the debug port. Login to TradingView persists in the dedicated profile.

Usage:
    python -m tradingview_mcp.chrome_launcher
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

# --- config ------------------------------------------------------------------
CDP_PORT = int(os.environ.get("TV_MCP_CDP_PORT", "9222"))
PROFILE_DIR = Path(os.path.expanduser(
    os.environ.get("TV_MCP_CHROME_PROFILE_DIR", "~/.tradingview_mcp_chrome")
))
START_URL = os.environ.get("TV_MCP_START_URL", "https://www.tradingview.com/chart/")
CHROME_BINARY_OVERRIDE = os.environ.get("TV_MCP_CHROME_BINARY", "").strip()


def find_chrome_binary() -> str:
    """Locate a Chrome executable for the current OS. Moon Dev's default paths."""
    if CHROME_BINARY_OVERRIDE:
        return CHROME_BINARY_OVERRIDE

    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        candidates = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    elif system == "Linux":
        candidates = [
            shutil.which("google-chrome") or "",
            shutil.which("chromium") or "",
            shutil.which("chromium-browser") or "",
        ]
    elif system == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]

    for c in candidates:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError(
        "🌙 Moon Dev: could not find Chrome. Set TV_MCP_CHROME_BINARY in .env."
    )


def port_is_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.25)
        try:
            s.connect((host, port))
            return True
        except OSError:
            return False


def cdp_is_ready(port: int = CDP_PORT, timeout: float = 0.5) -> bool:
    """Check whether Chrome's DevTools HTTP endpoint is live."""
    try:
        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def cdp_browser_name(port: int = CDP_PORT, timeout: float = 0.5) -> str:
    """Return the `Browser` field from /json/version — lets us distinguish between
    standalone Chrome and the embedded Chromium inside Moon Dev Code App (Electron)."""
    try:
        r = requests.get(f"http://127.0.0.1:{port}/json/version", timeout=timeout)
        if r.status_code == 200:
            return r.json().get("Browser", "")
    except requests.RequestException:
        pass
    return ""


# Moon Dev: Opt-out flag. If set to "1", the MCP never spawns its own Chrome — it
# assumes an external host (Moon Dev Code App, external Chrome) already serves CDP.
TV_MCP_SKIP_LAUNCH = os.environ.get("TV_MCP_SKIP_CHROME_LAUNCH", "").strip() in ("1", "true", "yes")


def launch_chrome(wait_ready: bool = True, wait_seconds: float = 15.0) -> subprocess.Popen | None:
    """Launch the dedicated Chrome profile. Returns the Popen handle, or None if already running."""
    if cdp_is_ready():
        browser = cdp_browser_name()
        # Moon Dev: Electron reports its bundled Chromium as "Chrome/<ver>" in /json/version,
        # same as real Chrome. We just trust the CDP endpoint regardless — if it's the Moon
        # Dev Code App, the user has the Browser overlay open to tradingview.com; if it's
        # a standalone Chrome, they launched it manually. Either way we reuse it.
        print(f"🌙 Moon Dev: CDP endpoint live on port {CDP_PORT} ({browser or 'unknown'}) — reusing.")
        return None

    if TV_MCP_SKIP_LAUNCH:
        raise RuntimeError(
            f"🌙 Moon Dev: TV_MCP_SKIP_CHROME_LAUNCH is set but nothing is listening on "
            f"port {CDP_PORT}. Start Moon Dev Code App first (it exposes CDP on 9222) or "
            "open an external Chrome with --remote-debugging-port=9222."
        )

    if port_is_open(CDP_PORT):
        raise RuntimeError(
            f"🌙 Moon Dev: port {CDP_PORT} is bound but doesn't look like Chrome CDP. "
            "Pick a different TV_MCP_CDP_PORT in .env."
        )

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    chrome = find_chrome_binary()

    args = [
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        # bind CDP to localhost only (default, but explicit)
        "--remote-debugging-address=127.0.0.1",
        # Chrome 111+ blocks WebSocket connections to the debug port unless
        # the origin is explicitly allowed. We only listen on 127.0.0.1 so
        # the exposure is still local-only. 🌙
        "--remote-allow-origins=*",
        # a few quality-of-life flags for a dedicated profile window
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=TranslateUI",
        START_URL,
    ]

    print(f"🌙 Moon Dev: launching dedicated Chrome → profile at {PROFILE_DIR}")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    if wait_ready:
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if cdp_is_ready():
                print(f"🌙 Moon Dev: Chrome CDP ready on port {CDP_PORT}")
                return proc
            time.sleep(0.3)
        raise RuntimeError(
            f"🌙 Moon Dev: Chrome did not open CDP port {CDP_PORT} within {wait_seconds}s."
        )
    return proc


def main() -> int:
    launch_chrome()
    print(
        "🌙 Moon Dev: dedicated Chrome is running. "
        "Log into TradingView if you haven't already — the login persists.\n"
        f"   CDP endpoint: http://127.0.0.1:{CDP_PORT}\n"
        f"   Profile dir:  {PROFILE_DIR}\n"
        "Leave the window open. The MCP server will connect on demand."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
