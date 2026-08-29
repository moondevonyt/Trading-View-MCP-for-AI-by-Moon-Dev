"""
🌙 Moon Dev's tool-call logger. JSON lines, one per call, so you can grep and
replay what Claude did to your chart.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_LOG_PATH_ENV = os.environ.get("TV_MCP_LOG_FILE", "").strip()
LOG_PATH = Path(os.path.expanduser(_LOG_PATH_ENV)) if _LOG_PATH_ENV else None


def log_call(tool: str, args: dict[str, Any], result: Any, duration_ms: float) -> None:
    if LOG_PATH is None:
        return
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": time.time(),
        "tool": tool,
        "args": args,
        "result": result,
        "duration_ms": round(duration_ms, 2),
        "emoji": "🌙",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
