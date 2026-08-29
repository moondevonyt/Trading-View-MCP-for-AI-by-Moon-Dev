# 🌙 Troubleshooting — TradingView MCP

## "No TradingView tab found on CDP port"

The dedicated Chrome window is running but no tab is on tradingview.com. Open
a chart at `https://www.tradingview.com/chart/` in that window.

## "Chrome did not open CDP port 9222 within 15s"

- Is Chrome already running a non-dedicated instance? macOS Chrome sometimes
  refuses to start a second instance that shares the same profile. The
  launcher uses a dedicated profile dir, so this shouldn't happen — but if you
  see it, `pkill -f "Google Chrome"` and retry. (Only your dedicated instance
  will die since only it was launched from the launcher.)
- Is the binary path correct? Set `TV_MCP_CHROME_BINARY` in `.env`.

## "could not find Chrome"

Install Google Chrome, Chromium, or Brave, or set `TV_MCP_CHROME_BINARY` in
`.env` to the exact binary path.

## A tool returns `"status": "error"` with a selector error

TradingView updated its DOM. Open `tradingview_mcp/tv_selectors.py`, find the
selector in the error message, and update it. Update the
`SELECTORS_VERIFIED_ON` date comment at the top.

To debug: open the dedicated Chrome window, right-click the element that
should have been found, Inspect, and copy the new selector.

## Pine Editor text not inserted

Monaco editors are picky about focus. The tool calls `.focus()` on the hidden
textarea, but if another panel stole focus, it fails. Click the Pine Editor
panel manually once, then retry — subsequent calls should work.

## Strategy Tester returns `"status": "partial"` with nulls

Backtests can take 5–30 seconds on complex scripts. Call
`tv_get_backtest_results` with a longer `timeout_seconds` parameter:

```
tv_get_backtest_results(timeout_seconds=60)
```

## Indicator dialog opens but "no indicator found matching X"

- TV's fuzzy search ranks partial matches. "RSI" works, "RelativeStrength"
  might not. Use the display name as it appears in the Indicators dialog.
- Premium/invite-only scripts won't be in the public library.

## Claude Desktop doesn't see the MCP

- Restart Claude Desktop fully (Cmd+Q, reopen).
- Check `claude_desktop_config.json` is valid JSON.
- The `command` must be an absolute Python path that has `mcp` installed.
  Use `/opt/anaconda3/envs/tflow/bin/python` (Moon Dev's tflow env), not
  a shell alias.
