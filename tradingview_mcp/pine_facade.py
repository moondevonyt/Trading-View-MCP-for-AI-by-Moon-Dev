"""
🌙 Moon Dev's Pine Script compile checker — no browser, no chart, no login.

TradingView's own Pine compiler is reachable over plain HTTP at
`pine-facade.tradingview.com/pine-facade/translate_light/`. It takes Pine
source and hands back STRUCTURED errors with exact line and column, which is
worlds better than scraping error text out of the Pine Editor console.

Why this matters: it lets us fix a script BEFORE touching the browser. The
chart becomes the place we LOOK at an idea, not the place we debug it.

Shape of the reply:
    clean  -> {"success": true, "result": {"functions2": [], ...}}   (no errors2 key)
    broken -> {"success": true, "result": {"errors2": [
                  {"message": "Undeclared identifier 'clse'",
                   "start": {"line": 3, "column": 13},
                   "end":   {"line": 3, "column": 16}}]}}

The endpoint 403s without browser-ish headers, so we always send them.
"""
from __future__ import annotations

import requests

TRANSLATE_URL = "https://pine-facade.tradingview.com/pine-facade/translate_light/"

# Moon Dev: pine-facade sits behind nginx that rejects bare API clients.
# Origin + Referer + a real UA is the whole handshake. No cookie needed.
_HEADERS = {
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


def validate_pine(code: str, timeout: float = 25.0) -> dict:
    """
    Compile-check `code` against TradingView's real Pine compiler.

    Returns:
        {"status": "ok", "valid": True,  "errors": []}
        {"status": "ok", "valid": False, "errors": [{line, column, message}, ...],
         "annotated": "  3 | plot(ta.sma(clse, 20))   <-- Undeclared identifier"}
    """
    if not isinstance(code, str) or not code.strip():
        return {"status": "error", "error": "code must be a non-empty string"}

    resp = requests.post(TRANSLATE_URL, headers=_HEADERS, data={"source": code}, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("success"):
        return {"status": "error", "error": f"pine-facade rejected the request: {payload}"}

    raw_errors = (payload.get("result") or {}).get("errors2") or []
    errors = [
        {
            "line": (e.get("start") or {}).get("line"),
            "column": (e.get("start") or {}).get("column"),
            "message": e.get("message", ""),
        }
        for e in raw_errors
    ]

    out = {"status": "ok", "valid": not errors, "errors": errors}
    if errors:
        out["annotated"] = annotate(code, errors)
    return out


def annotate(code: str, errors: list[dict]) -> str:
    """Show the offending source lines with the compiler's complaint attached. 🌙"""
    lines = code.splitlines()
    chunks = []
    for err in errors:
        ln = err.get("line")
        src = lines[ln - 1] if isinstance(ln, int) and 1 <= ln <= len(lines) else "?"
        chunks.append(f"{ln:>4} | {src}\n     |  ^-- {err.get('message', '')}")
    return "\n".join(chunks)


def register(mcp) -> None:
    """Register the browser-free validator as an MCP tool. 🌙"""

    @mcp.tool()
    def tv_validate_pine_script(code: str) -> dict:
        """
        🌙 Compile-check Pine Script WITHOUT opening a chart. Fast (~200ms).
        Returns exact line/column errors. Always call this before
        tv_write_pine_script so the browser only ever sees working code.
        """
        try:
            return validate_pine(code)
        except Exception as exc:
            return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
