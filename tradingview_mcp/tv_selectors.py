"""
🌙 Moon Dev's TradingView DOM selector registry.

This is the brittle layer. When TradingView ships a UI update and something
breaks, 90% of the time the fix lives in this file alone. Every CSS selector
or data-name attribute Claude uses to poke at TV's chart is funneled here.

SELECTORS_VERIFIED_ON: 2026-04-22
"""

# --- Top bar / symbol search -------------------------------------------------
# The top-left symbol button and its search overlay.
SYMBOL_BUTTON = '[data-name="legend-source-title"]'
SYMBOL_SEARCH_INPUT = 'input[data-role="search"][class*="search"]'
SYMBOL_SEARCH_ITEM = '[data-name="symbol-search-items-dialog"] [class*="item"]'
SYMBOL_DIALOG_ROOT = '[data-name="symbol-search-items-dialog"]'

# --- Timeframe buttons --------------------------------------------------------
# TV exposes each timeframe button with a data-value attribute.
TIMEFRAME_BUTTON = '[data-name="date-ranges-tabs"] button'
TIMEFRAME_MENU_TRIGGER = '[data-name="go-to-date"]'
TIMEFRAME_DROPDOWN_ITEM = '[data-name="menu-inner"] [data-value="{tf}"]'
# Fallback: the native timeframe selector in the header toolbar.
HEADER_TIMEFRAME_BUTTONS = '#header-toolbar-intervals button'

# --- Indicators dialog --------------------------------------------------------
INDICATORS_DIALOG_OPEN_BUTTON = '[data-name="open-indicators-dialog"]'
INDICATORS_DIALOG_ROOT = '[data-name="indicators-dialog"]'
INDICATORS_DIALOG_SEARCH = '[data-name="indicators-dialog"] input'
INDICATORS_DIALOG_RESULT = '[data-name="indicators-dialog"] [data-role="list-item"]'
INDICATORS_DIALOG_CLOSE = '[data-name="indicators-dialog"] [data-name="close"]'

# --- Chart legend (currently attached studies) --------------------------------
# 🚨 VERIFIED DEAD 2026-08-29: TradingView removed the legend data-name attrs.
# Both of these now match ZERO nodes on a chart that visibly has studies.
# Use LEGEND_STUDY_TITLE_V2 below. Kept here so nobody "fixes" it back.
LEGEND_ROOT = '[data-name="legend-source-item"]'
LEGEND_STUDY_TITLE = '[data-name="legend-source-item"] [data-name="legend-source-title"]'
# The live legend is hashed CSS modules (sources-quatTGAC / titlesWrapper-quatTGAC).
# The hash changes every TV deploy, so match the stable prefix only.
LEGEND_SOURCES_V2 = '[class*="sources-"]'
LEGEND_STUDY_TITLE_V2 = '[class*="sources-"] [class*="titlesWrapper"]'
LEGEND_STUDY_VALUE = '[data-name="legend-source-item"] [class*="valueItem"]'
LEGEND_DELETE_BUTTON = '[data-name="legend-source-item"] [data-name="legend-action-panel"] [data-name="delete"]'

# --- Right-click context menu ------------------------------------------------
CONTEXT_MENU = '[data-name="context-menu"]'
CONTEXT_MENU_ITEM = '[data-name="context-menu"] [data-name="menu-inner"] [role="menuitem"]'
CONTEXT_REMOVE_ALL_INDICATORS = '[data-name="remove-studies"]'

# --- Pine Editor -------------------------------------------------------------
# TV web (2026): the Pine Editor lives in the bottom panel and opens via the
# Pine dialog button on the right-hand toolbar.
PINE_EDITOR_TAB_BUTTON = '[data-name="pine-dialog-button"]'
PINE_EDITOR_ROOT = '[data-name="pine-editor"], [class*="pineEditorContainer"]'
# TV uses a Monaco-ish editor; textarea is hidden but focusable.
PINE_EDITOR_TEXTAREA = '.monaco-editor textarea'
PINE_EDITOR_SAVE_BUTTON = 'button[title="Save script"], button[class*="saveButton"]'
PINE_EDITOR_ADD_TO_CHART_BUTTON = 'button[title="Add to chart"], [data-name="pine-editor-add-to-chart-button"]'
PINE_EDITOR_ERROR_TOOLTIP = '[data-name="pine-editor-console"] [class*="error"]'

# --- Strategy Tester ---------------------------------------------------------
STRATEGY_TESTER_TAB = '[data-name="backtesting"]'
STRATEGY_TESTER_ROOT = '[data-name="backtesting-content-wrapper"]'
STRATEGY_TESTER_OVERVIEW_TAB = '[data-name="performance-summary"]'
STRATEGY_TESTER_METRIC_ROW = '[data-name="performance-summary"] [data-name*="row"]'
STRATEGY_TESTER_NET_PROFIT = '[data-name="net-profit"]'
STRATEGY_TESTER_MAX_DRAWDOWN = '[data-name="max-drawdown"]'
STRATEGY_TESTER_WIN_RATE = '[data-name="percent-profitable"]'
STRATEGY_TESTER_PROFIT_FACTOR = '[data-name="profit-factor"]'
STRATEGY_TESTER_TOTAL_TRADES = '[data-name="total-trades"]'

# --- Settings dialogs (for indicator params) ---------------------------------
STUDY_SETTINGS_DIALOG = '[data-name="study-dialog"]'
STUDY_SETTINGS_INPUTS_TAB = '[data-name="inputs-tab"]'
STUDY_SETTINGS_INPUT_FIELD = '[data-name="study-dialog"] input'
STUDY_SETTINGS_OK = '[data-name="study-dialog"] [data-name="submit-button"]'

# --- Login state --------------------------------------------------------------
LOGIN_SIGNED_OUT = '[data-name="header-user-menu-sign-in"]'
LOGIN_USER_MENU = '[data-name="header-user-menu-button"]'
