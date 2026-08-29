# 🌙 Setup — TradingView MCP

## 1. Install

```bash
cd /Users/md/Dropbox/dev/github/moon-dev-trading-bots/bots/tradingview_mcp
conda activate tflow
pip install -r requirements.txt
```

## 2. Configure (optional)

```bash
cp .env.example .env
```

Defaults are fine for Moon Dev's setup. Tweak if:
- Port 9222 is already in use (set `TV_MCP_CDP_PORT`)
- You want the dedicated Chrome profile somewhere else (set `TV_MCP_CHROME_PROFILE_DIR`)
- Chrome isn't at `/Applications/Google Chrome.app/...` (set `TV_MCP_CHROME_BINARY`)

## 3. First launch (log into TradingView)

```bash
python -m tradingview_mcp.chrome_launcher
```

A dedicated Chrome window opens at `tradingview.com/chart/`. Log in with your
TV account — the login persists in the dedicated profile forever.

**Leave that window open** while the MCP server runs. You can minimize it or
put it on another desktop; it just needs to stay alive so the CDP port stays
up.

## 4. Sanity check the bridge

From a second terminal:

```bash
python -c "from tradingview_mcp.cdp_client import open_tv_client; \
with open_tv_client() as c: print(c.eval_js('document.title'))"
```

You should see the title of the TradingView chart tab. If you see a CDP error
with "no TradingView tab found", open a chart tab in the dedicated Chrome
window and retry.

## 5. Register the MCP with Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "/opt/anaconda3/envs/tflow/bin/python",
      "args": ["-m", "tradingview_mcp.server"],
      "cwd": "/Users/md/Dropbox/dev/github/moon-dev-trading-bots/bots/tradingview_mcp"
    }
  }
}
```

Restart Claude Desktop. Ask: *"what TradingView tools do you have?"* — Claude
should list `tv_set_symbol`, `tv_add_indicator`, `tv_write_pine_script`, etc.

## 6. Try it

Say to Claude:

> "Open COINBASE:BTCUSD on the 1-hour chart, add RSI length 14, and tell me
> the current value."

Claude should:
1. Call `tv_set_symbol("COINBASE:BTCUSD")`
2. Call `tv_set_timeframe("60")`
3. Call `tv_add_indicator("RSI", {"length": 14})`
4. Call `tv_read_indicator_value("RSI")`
5. Tell you the number.
