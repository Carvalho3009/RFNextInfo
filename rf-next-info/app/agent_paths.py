"""Layout de dados exclusivo do RF QOL Agent."""

from __future__ import annotations

import os
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
AGENT_ASSETS_DIR = SOURCE_ROOT / "assets"
INSTALL_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else SOURCE_ROOT
)
AGENT_STATE_DIR = (
    Path(os.environ["LOCALAPPDATA"]) / "Karvalho" / "RF QOL Agent"
    if os.getenv("LOCALAPPDATA")
    else INSTALL_DIR / "user-data" / "agent"
)
AGENT_RUNTIME_DIR = AGENT_STATE_DIR / "runtime"
AGENT_LOG_DIR = AGENT_STATE_DIR / "logs"
AGENT_DIAGNOSTIC_DIR = AGENT_STATE_DIR / "diagnostics"
AGENT_PREFERENCES_PATH = AGENT_STATE_DIR / "preferences.json"
AGENT_LOG_PATH = AGENT_LOG_DIR / "rf-qol-agent.log"


def ensure_agent_layout() -> tuple[Path, ...]:
    directories = (
        AGENT_STATE_DIR,
        AGENT_RUNTIME_DIR,
        AGENT_LOG_DIR,
        AGENT_DIAGNOSTIC_DIR,
    )
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return directories
