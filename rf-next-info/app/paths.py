from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
INSTALL_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else SOURCE_ROOT
)
SELF_TEST_LAYOUT = os.getenv("RFQOL_SELF_TEST") == "1"

STATE_DIR = INSTALL_DIR / "data"
MACHINE_STATE_DIR = (
    Path(os.environ["PROGRAMDATA"]) / "Karvalho" / "RF QOL"
    if (
        getattr(sys, "frozen", False)
        and not SELF_TEST_LAYOUT
        and os.getenv("PROGRAMDATA")
    )
    else INSTALL_DIR / "machine-data"
)
DATABASE_DIR = INSTALL_DIR / "database"
LOG_DIR = INSTALL_DIR / "logs"
CACHE_DIR = INSTALL_DIR / "cache"
UPDATES_DIR = MACHINE_STATE_DIR / "updates"
CAPTURE_DIR = INSTALL_DIR / "Capturas"

DB_PATH = DATABASE_DIR / "capture.sqlite3"
KNOWLEDGE_DB_PATH = DATABASE_DIR / "knowledge.sqlite3"
PREFERENCES_PATH = STATE_DIR / "preferences.json"
LOG_PATH = LOG_DIR / "rf-qol.log"
PREVIEW_DIR = CACHE_DIR / "preview"

RUNTIME_DIRS = (
    STATE_DIR,
    MACHINE_STATE_DIR,
    DATABASE_DIR,
    LOG_DIR,
    CACHE_DIR,
    UPDATES_DIR,
    CAPTURE_DIR,
)


def _harden_machine_directory(path: Path) -> None:
    if (
        os.name != "nt"
        or not getattr(sys, "frozen", False)
        or SELF_TEST_LAYOUT
    ):
        return
    result = subprocess.run(
        [
            "icacls.exe",
            str(path),
            "/inheritance:r",
            "/grant:r",
            "*S-1-5-18:(OI)(CI)F",
            "*S-1-5-32-544:(OI)(CI)F",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise OSError("Não foi possível proteger o estado de instalação")


def ensure_runtime_layout() -> tuple[Path, ...]:
    """Cria o layout novo sem importar dados ou licenças da linha anterior."""
    for directory in RUNTIME_DIRS:
        directory.mkdir(parents=True, exist_ok=True)
    _harden_machine_directory(MACHINE_STATE_DIR)
    return ()
