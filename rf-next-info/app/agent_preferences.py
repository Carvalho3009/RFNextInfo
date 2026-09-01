"""Preferências isoladas do executável RF Next Companion."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from core.windows_agent_capture import (
    DEFAULT_AGENT_MEMORY_MB,
    MAX_AGENT_MEMORY_MB,
    MIN_AGENT_MEMORY_MB,
)


AGENT_STARTUP_VALUE = "RF Next Companion"
LEGACY_AGENT_STARTUP_VALUE = "RF QOL Agent"
AGENT_STARTUP_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_AGENT_STORAGE_MB = 512
MIN_AGENT_STORAGE_MB = 128
MAX_AGENT_STORAGE_MB = 32 * 1024


def _bounded_integer(value: object, minimum: int, maximum: int, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(maximum, number))


def normalize_agent_preferences(raw: object) -> dict[str, Any]:
    source = dict(raw) if isinstance(raw, dict) else {}
    installation_id = str(source.get("installation_id") or "")
    try:
        installation_id = str(uuid.UUID(installation_id))
    except (ValueError, TypeError, AttributeError):
        installation_id = str(uuid.uuid4())
    return {
        "schema": 1,
        "installation_id": installation_id,
        "start_with_windows": source.get("start_with_windows") is True,
        "auto_capture": source.get("auto_capture") is True,
        "memory_limit_mb": _bounded_integer(
            source.get("memory_limit_mb"),
            MIN_AGENT_MEMORY_MB,
            MAX_AGENT_MEMORY_MB,
            DEFAULT_AGENT_MEMORY_MB,
        ),
        "storage_limit_mb": _bounded_integer(
            source.get("storage_limit_mb"),
            MIN_AGENT_STORAGE_MB,
            MAX_AGENT_STORAGE_MB,
            DEFAULT_AGENT_STORAGE_MB,
        ),
        "local_api_port": _bounded_integer(
            source.get("local_api_port"), 1024, 65535, 17621
        ),
    }


def load_agent_preferences(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        raw = {}
    return normalize_agent_preferences(raw)


def save_agent_preferences(path: Path, preferences: object) -> dict[str, Any]:
    path = Path(path)
    normalized = normalize_agent_preferences(preferences)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return normalized


def agent_startup_command() -> str:
    if getattr(sys, "frozen", False):
        arguments = [str(Path(sys.executable).resolve()), "--background"]
    else:
        arguments = [
            str(Path(sys.executable).resolve()),
            "-m",
            "app.agent_main",
            "--background",
        ]
    return subprocess.list2cmdline(arguments)


def configure_agent_startup(enabled: bool) -> None:
    if os.name != "nt":
        raise RuntimeError("Inicializacao automatica disponivel somente no Windows")
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, AGENT_STARTUP_KEY) as key:
        try:
            winreg.DeleteValue(key, LEGACY_AGENT_STARTUP_VALUE)
        except FileNotFoundError:
            pass
        if enabled:
            winreg.SetValueEx(
                key,
                AGENT_STARTUP_VALUE,
                0,
                winreg.REG_SZ,
                agent_startup_command(),
            )
        else:
            try:
                winreg.DeleteValue(key, AGENT_STARTUP_VALUE)
            except FileNotFoundError:
                pass
