# 🌙 TradingView MCP

Tell Claude a trading idea. Watch it appear on your TradingView chart.

This is a **Model Context Protocol server** that drives a real, logged-in TradingView
chart in Chrome. Claude writes the Pine Script, compile-checks it, pastes it into the
Pine Editor, adds it to the chart, and reads the result back. Under 3 seconds from
idea to chart.

There is **no official TradingView MCP**. TradingView's own AI product (AI Chart
Copilot) is a closed Chrome extension capped at 15 requests a day and it cannot run
your Pine. Every other TradingView MCP on GitHub reads market data over TradingView's
private HTTP API. None of them can put a custom script on a chart. This one can,
because it drives the actual page.

Built by **Moon Dev** 🌙

---

## How it works

```
Claude  <──MCP/stdio──>  tradingview_mcp  ──CDP──>  Chrome tab on tradingview.com
                                │
                                └──HTTPS──>  pine-facade.tradingview.com
                                             (compile-check, no browser)
```

Two channels, on purpose:

- **Chrome DevTools Protocol** for anything that has to touch the real chart.
- **A direct HTTPS call to TradingView's own Pine compiler** for validation. This
  means a script is proven to compile *before* the browser ever sees it, so the
  browser is where you look at an idea, not where you debug it.

The Chrome instance is a **dedicated profile**, separate from your everyday Chrome.
Running your main browser with remote debugging open would let any local process read
your logged-in sessions. This one only ever holds TradingView.

---

## Quick start

You need Python 3.10+, Chrome, and a TradingView account (free tier is fine).

### Step 1 — Install

```bash
cd tradingview_mcp
pip install -r requirements.txt
cp .env.example .env
```

You do not need to edit `.env`. The defaults work.

### Step 2 — Log into TradingView, one time

⚠️ **Close any other TradingView window or tab before this.** TradingView allows one
active session per account. A second one kicks the first with a "Session disconnected"
popup.

```bash
python -m tradingview_mcp.chrome_launcher
```

A **new Chrome window opens** on TradingView. This is a dedicated profile, separate
from your everyday Chrome, so your other logins are never exposed to the debug port.

👉 **Log into TradingView in that window, then leave it open.** The login persists, so
you only do this once.

You should see:

```
🌙 Moon Dev: launching dedicated Chrome → profile at /Users/you/.tradingview_mcp_chrome
🌙 Moon Dev: Chrome CDP ready on port 9222
```

### Step 3 — Put your first indicator on the chart

Leave that Chrome window open. Open a **second terminal**, `cd` into this folder
again, and run:

```bash
cd tradingview_mcp
python mount_pine.py examples/moon_dev_rainbow_ribbon_10_50.pine
```

```
🌙 Moon Dev — mounting moon_dev_rainbow_ribbon_10_50.pine (6247 bytes)
  1. compile-check (no browser)     290 ms   valid=True
  2. write into editor              2.2 s    clear+paste, 121 lines
  3. add to chart                   0.0 s
  4. close editor panel             closed
  5. chart legend                   ['Vol', 'MA', 'MD RIBBON']
  6. screenshot                     moon_dev_chart.png

🌙 MOUNTED: True
```

**`MOUNTED: True` means it worked.** Look at the Chrome window: a 5-color moving
average ribbon is on your chart. There is also a `moon_dev_chart.png` screenshot in
the folder.

That's the whole loop. Any `.pine` file, one command.

### Step 4 — Hand the controls to Claude

Add this to your MCP config, using the **full path** to this folder:

- Claude Desktop: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Claude Code: `claude mcp add` or your project's `.mcp.json`

```json
{
  "mcpServers": {
    "tradingview": {
      "command": "python",
      "args": ["-m", "tradingview_mcp.server"],
      "cwd": "/full/path/to/tradingview_mcp"
    }
  }
}
```

Restart Claude, then check it connected:

> *"what tradingview tools do you have?"*

You should get back 16 tools starting with `tv_`. Now just describe what you want:

- *"put a 5 EMA ribbon on my chart, 10 through 50, each a different color"*
- *"mark every bar where volume is 3x the last bar"*
- *"open NVDA on the 5 minute chart and add an RSI"*

### If something goes wrong

| What you see | Fix |
|---|---|
| `port 9222 is bound but doesn't look like Chrome CDP` | Something else owns the port. Set `TV_MCP_CDP_PORT=9333` in `.env` and rerun step 2. |
| `no TradingView tab found` | The Chrome window from step 2 was closed. Rerun step 2. |
| `Pine Editor not reachable` | You are not logged in, or the window is too narrow. Log in and widen it. |
| `MOUNTED: False` | Read the `compile errors` line above it. It's the real reason. |
| "Session disconnected" popup | You have TradingView open somewhere else. Close it and click Connect. |

More in [`docs/troubleshooting.md`](docs/troubleshooting.md).

---

## Tools

**Pine Script**
| Tool | What it does |
|---|---|
| `tv_validate_pine_script` | Compile-check with **no browser**, ~300ms. Exact line and column on errors. Call this first, always. |
| `tv_write_pine_script` | Replace the editor buffer. Verifies the write landed before returning. |
| `tv_compile_pine_script` | Add/Update on chart. Waits for the study to appear, returns the legend. |
| `tv_save_pine_script` | Save the script to your TradingView account. |

**Chart**
| Tool | What it does |
|---|---|
| `tv_set_symbol` | `"COINBASE:BTCUSD"`, `"NASDAQ:NVDA"` |
| `tv_set_timeframe` | `"1"`, `"5"`, `"60"`, `"D"`, `"W"` |
| `tv_get_current_symbol` | Symbol, timeframe, URL |
| `tv_screenshot` | PNG of the chart |

**Indicators**
| Tool | What it does |
|---|---|
| `tv_add_indicator` | Add by name, optional params |
| `tv_remove_indicator` / `tv_remove_all_indicators` | Remove one or all |
| `tv_list_indicators` | What's currently attached |
| `tv_read_indicator_value` | Read an indicator's current value |

**Strategy Tester**
| Tool | What it does |
|---|---|
| `tv_run_strategy_tester` | Open the panel |
| `tv_get_backtest_results` | Net profit, drawdown, win rate, profit factor, trades |

⚠️ TradingView's Strategy Tester fills at bar close and the bar magnifier is off by
default. Use it to **see** an idea. Validate with a real backtester on real data.

---

## What we learned making this work

Everything below is measured, not guessed. Most of it cost real debugging time.

**Monaco ignores incomplete key events.** A key sent as `{"type":"keyDown","key":"Backspace"}`
does nothing at all. Measured: a bare Backspace left a 635-character buffer untouched;
the same key with `code` + `windowsVirtualKeyCode` + `nativeVirtualKeyCode` cleared it
to 0. Every non-text key needs its virtual key number.

**A synthetic paste is invisible to TradingView.** A `ClipboardEvent` changes Monaco's
model (your code sits there, correctly highlighted) but TradingView's own change
tracking never fires, so "Add to chart" stays `disabled` forever and nothing mounts.
No error anywhere. One real key event arms it.

**Synthetic `.click()` does not reach TradingView's handlers.** Selecting which pane an
indicator lands on needs `Input.dispatchMouseEvent` at real coordinates.

**A reload pops a native dialog that blocks everything.** TradingView registers a
`beforeunload` handler, so `Page.reload` opens Chrome's "Leave site?" prompt and the
page freezes until a human clicks. The client auto-accepts
`Page.javascriptDialogOpening` now.

**Verify writes, and verify them as a band.** Monaco caps its hidden textarea mirror at
about 200 characters, so you cannot read a long script back. But the caret line is
exact, and an *empty* buffer always mirrors as empty. Check emptiness before pasting,
and check the caret line after. Use `abs(got - expected) <= 1`, not `>=`. A floor check
passes while stale code is still sitting above yours, and you ship a file with two
`indicator()` declarations.

**The Pine console is an append-only log.** Read it whole and a fixed script reports the
error it already fixed. Snapshot the line count before compiling, read only what's new.

**TradingView removed the legend `data-name` attributes.** `[data-name="legend-source-item"]`
matches zero nodes on a chart that visibly has studies. The legend is hashed CSS modules
now (`sources-quatTGAC`, `titlesWrapper-quatTGAC`) and the hash changes every deploy, so
match the stable class prefix.

**One active TradingView session per account.** Opening TradingView anywhere else kicks
this one with a "Session disconnected" modal. Close your other TradingView windows.

---

## Known limits

**Electron `<webview>` hosts do not work yet.** The DOM is readable, the session is
live, and input events are accepted, but the Pine Editor never mounts and
`Page.captureScreenshot` hangs forever. Cause: the guest lays out at one size while
being painted into a much smaller surface, and a collapsed panel gives the webview
`0px × 0px`. If you are embedding this in an Electron app, you need to:

1. Give the webview a real size. TradingView needs roughly 1000px+ of width before it
   renders the Pine Editor at all.
2. Stop the guest laying out at a size it is not painted at.
3. Use Electron's `webContents.capturePage()` instead of CDP `Page.captureScreenshot`.
   A `<webview>` composites into the host's surface, so it has no frame of its own.
4. Call `webview.focus()` when the panel becomes active.

**The DOM layer is brittle by nature.** TradingView ships UI changes whenever it likes.
When something breaks, `tv_selectors.py` is the first place to look. Selectors verified
against TradingView as of the date in that file's header.

**Premium indicators need a paid plan.** The server reports the paywall error. It does
not try to work around anything.

---

## Layout

```
tradingview_mcp/
├── mount_pine.py              one-shot: .pine file -> live chart -> screenshot
├── tradingview_mcp/
│   ├── server.py              MCP entry point
│   ├── pine_facade.py         browser-free Pine compiler check
│   ├── cdp_client.py          Chrome DevTools Protocol client
│   ├── chrome_launcher.py     dedicated Chrome profile
│   ├── tv_selectors.py        DOM selectors — the brittle layer, all in one file
│   └── tools/                 chart.py · indicators.py · pine.py
├── examples/                  Pine scripts, all verified to compile
├── tests/
│   ├── test_smoke.py          no Chrome needed
│   ├── test_vwap_star_live.py end-to-end against a live chart
│   └── test_vwap_star_logic.py signal logic vs real OHLCV
└── docs/                      setup.md · troubleshooting.md
```

---

## Config

All optional, set in `.env`:

| Variable | Default | Notes |
|---|---|---|
| `TV_MCP_CDP_PORT` | `9222` | Change if the port is taken |
| `TV_MCP_CHROME_PROFILE_DIR` | `~/.tradingview_mcp_chrome` | Dedicated profile |
| `TV_MCP_START_URL` | TradingView chart | Where Chrome opens |
| `TV_MCP_CHROME_BINARY` | auto-detect | Chrome/Chromium/Brave path |
| `TV_MCP_SKIP_CHROME_LAUNCH` | unset | Reuse a CDP endpoint you already run |

---

## Before open-sourcing this

- [ ] Add a `LICENSE` (there isn't one yet)
- [ ] The demo `*_shot.png` files in the repo root show a real account's watchlist and
      positions. Review or replace them.
- [ ] `tests/test_vwap_star_logic.py` reads OHLCV from the parent trading-bots repo. It
      skips cleanly when that data is absent, but ship a sample CSV if you want it to
      run standalone.

---

## Not affiliated with TradingView

This drives the TradingView web app the way a person would. It does not bypass
paywalls, and it respects whatever your account can already do. Check TradingView's
Terms of Service for your use case.

Built by **Moon Dev** 🌙
