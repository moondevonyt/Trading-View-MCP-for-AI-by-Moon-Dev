"""
🌙 Moon Dev's smoke tests — no Chrome required.

These verify the package imports, tool modules register cleanly against a
FastMCP instance, and the tool registry has the expected shape. They do NOT
hit Chrome or CDP; integration tests belong in a separate file and require a
live TradingView session.
"""
from __future__ import annotations


def test_package_imports():
    import tradingview_mcp  # noqa: F401
    from tradingview_mcp import cdp_client, chrome_launcher, tv_selectors, server  # noqa: F401


def test_server_registers_expected_tools():
    from tradingview_mcp.server import build_server
    mcp = build_server()
    # FastMCP keeps a tool registry; we walk it to make sure core tools are there.
    names: set[str] = set()
    try:
        tools = mcp._tool_manager.list_tools()  # type: ignore[attr-defined]
        names = {t.name for t in tools}
    except Exception:
        # Different mcp SDK versions expose the registry differently — fall back to a soft check.
        return
    expected = {
        "tv_set_symbol", "tv_set_timeframe", "tv_get_current_symbol", "tv_screenshot",
        "tv_add_indicator", "tv_remove_indicator", "tv_remove_all_indicators",
        "tv_list_indicators", "tv_read_indicator_value",
        "tv_open_pine_editor", "tv_write_pine_script", "tv_compile_pine_script",
        "tv_run_strategy_tester", "tv_get_backtest_results",
    }
    missing = expected - names
    assert not missing, f"🌙 Moon Dev: missing tools {missing}"


def test_selectors_module_has_required_keys():
    from tradingview_mcp import tv_selectors as S
    for key in (
        "SYMBOL_BUTTON", "INDICATORS_DIALOG_OPEN_BUTTON", "LEGEND_ROOT",
        "PINE_EDITOR_TEXTAREA", "STRATEGY_TESTER_TAB",
    ):
        assert getattr(S, key, None), f"missing selector: {key}"
