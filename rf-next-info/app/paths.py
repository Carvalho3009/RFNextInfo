from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", SOURCE_ROOT))
INSTALL_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else SOURCE_ROOT
)

STATE_DIR = INSTALL_DIR / "data"
MACHINE_STATE_DIR = STATE_DIR
DATABASE_DIR = INSTALL_DIR / "database"
LOG_DIR = INSTALL_DIR / "logs"
CACHE_DIR = INSTALL_DIR / "cache"
UPDATES_DIR = INSTALL_DIR / "updates"
CAPTURE_DIR = INSTALL_DIR / "Capturas"

DB_PATH = DATABASE_DIR / "capture.sqlite3"
KNOWLEDGE_DB_PATH = DATABASE_DIR / "knowledge.sqlite3"
PREFERENCES_PATH = STATE_DIR / "preferences.json"
LOG_PATH = LOG_DIR / "rfnext-info.log"
PREVIEW_DIR = CACHE_DIR / "preview"

LEGACY_USER_STATE_DIR = (
    Path(os.getenv("LOCALAPPDATA", Path.home())) / "Karvalho" / "RFNextInfo"
)
LEGACY_MACHINE_STATE_DIR = (
    Path(os.environ["PROGRAMDATA"]) / "Karvalho" / "RFNextInfo"
    if os.getenv("PROGRAMDATA")
    else LEGACY_USER_STATE_DIR / "machine"
)

RUNTIME_DIRS = (
    STATE_DIR,
    DATABASE_DIR,
    LOG_DIR,
    CACHE_DIR,
    UPDATES_DIR,
    CAPTURE_DIR,
)


def _same_file(left: Path, right: Path) -> bool:
    def digest(path: Path) -> str:
        value = hashlib.sha256()
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                value.update(chunk)
        return value.hexdigest()

    return left.stat().st_size == right.stat().st_size and digest(left) == digest(right)


def _copy_if_missing(source: Path, target: Path) -> bool:
    if target.exists() or not source.is_file():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.migration.tmp")
    shutil.copy2(source, temporary)
    if not _same_file(source, temporary):
        temporary.unlink(missing_ok=True)
        raise OSError(f"A migração de {source.name} não pôde ser validada")
    os.replace(temporary, target)
    return True


def ensure_runtime_layout() -> tuple[Path, ...]:
    """Prepare writable install-local storage and copy validated legacy state."""
    for directory in RUNTIME_DIRS:
        directory.mkdir(parents=True, exist_ok=True)

    migrated: list[Path] = []
    candidates = (
        (LEGACY_USER_STATE_DIR / "preferences.json", PREFERENCES_PATH),
        (LEGACY_USER_STATE_DIR / "capture.sqlite3", DB_PATH),
        (LEGACY_USER_STATE_DIR / "license.dat", STATE_DIR / "license.dat"),
        (
            LEGACY_USER_STATE_DIR / "license.backup.dat",
            STATE_DIR / "license.backup.dat",
        ),
        (LEGACY_USER_STATE_DIR / "site-profile.dat", STATE_DIR / "site-profile.dat"),
        (LEGACY_MACHINE_STATE_DIR / "license.dat", STATE_DIR / "license.dat"),
        (
            LEGACY_MACHINE_STATE_DIR / "license.backup.dat",
            STATE_DIR / "license.backup.dat",
        ),
    )
    for source, target in candidates:
        if _copy_if_missing(source, target):
            migrated.append(source)
    return tuple(migrated)
