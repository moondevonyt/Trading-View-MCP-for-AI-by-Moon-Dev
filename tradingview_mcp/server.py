"""
🌙 Moon Dev's TradingView MCP Server — entry point.

Starts a stdio MCP server, registers chart / indicator / Pine Script tools,
and speaks Model Context Protocol to any client (Claude Desktop, Claude Code,
Cursor, Codex, etc.).

Run:
    python -m tradingview_mcp.server
"""
from __future__ import annotations

import sys

from mcp.server.fastmcp import FastMCP

from . import pine_facade
from .tools import chart, indicators, pine


def build_server() -> FastMCP:
    mcp = FastMCP(
        "tradingview",
        instructions=(
            "🌙 Moon Dev's TradingView control surface. "
            "Use these tools to set symbols, timeframes, add/remove indicators, "
            "write and compile Pine Script, and read backtest results from a "
            "live TradingView chart running in a dedicated Chrome profile."
        ),
    )
    chart.register(mcp)
    indicators.register(mcp)
    pine.register(mcp)
    pine_facade.register(mcp)  # 🌙 browser-free Pine compile check
    return mcp


def main() -> int:
    mcp = build_server()
    # FastMCP.run() defaults to stdio transport — exactly what Claude Desktop wants.
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
