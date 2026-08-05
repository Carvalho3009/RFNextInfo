from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.license import LicenseClient, verify_lease
from app.main import (
    App as StableApp,
    CLASS_ICON_FILES,
    DB_PATH,
    MACHINE_STATE_DIR,
    PREFERENCES_PATH,
    RARITY_COLORS,
    STATE_DIR,
)
from core.store import CaptureStore


class ReadOnlySnapshotReader:
    _character_exports = StableApp._character_exports
    _load_info_snapshot = StableApp._load_info_snapshot

    def __init__(self, database_path: Path = DB_PATH) -> None:
        self.database_path = Path(database_path)
        self.current_session: str | None = None
        self._last_session_stats = {
            "recognized": 0,
            "unknown": 0,
            "unassigned": 0,
            "raw_bytes": 0,
        }
        self._info_worker_cache: dict[str, Any] = {}

    def load(self, language: str = "pt") -> dict[str, Any]:
        if not self.database_path.exists():
            return self._empty()
        database = CaptureStore(self.database_path, readonly=True)
        try:
            self.current_session = database.latest_session()
            snapshot = self._load_info_snapshot(
                database,
                self.current_session,
                "en" if language == "en" else "pt",
            )
            snapshot["capture_windows"] = (
                database.capture_windows(self.current_session)
                if self.current_session else []
            )
            snapshot["collection_type_counts"] = (
                database.collection_type_counts(self.current_session)
                if self.current_session else {}
            )
            return snapshot
        finally:
            database.close()

    def _empty(self) -> dict[str, Any]:
        return {
            "session_id": None,
            "stats": dict(self._last_session_stats),
            "profiles": [],
            "characters": [],
            "subsessions": [],
            "subsession_summaries": {},
            "capture_windows": [],
            "collection_type_counts": {},
        }


def load_preferences(path: Path = PREFERENCES_PATH) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save_preferences(
    updates: dict[str, Any], path: Path = PREFERENCES_PATH
) -> dict[str, Any]:
    preferences = load_preferences(path)
    preferences.update(updates)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(preferences, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    os.replace(temporary, path)
    return preferences


def load_farm_catalog(language: str = "pt") -> dict[str, dict[str, dict[str, tuple[int, ...]]]]:
    root = Path(__file__).resolve().parents[2]
    path = root / "core" / ("catalogo_en.csv" if language == "en" else "catalogo.csv")
    catalog: dict[str, dict[str, dict[str, set[int]]]] = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                map_name = str(row.get("mapa") or row.get("map_name_ptbr") or "").strip()
                spot_name = str(row.get("spot_andar") or row.get("spot_name_ptbr") or "").strip()
                mob = str(row.get("mob_name") or row.get("mob_name_ptbr") or "").strip()
                level = int(row.get("mob_level") or 0)
                if map_name and spot_name and mob and 1 <= level <= 999:
                    catalog.setdefault(map_name, {}).setdefault(spot_name, {}).setdefault(mob, set()).add(level)
    except (OSError, TypeError, ValueError, csv.Error):
        return {}
    return {
        map_name: {
            spot_name: {
                mob: tuple(sorted(levels))
                for mob, levels in sorted(mobs.items(), key=lambda item: item[0].casefold())
            }
            for spot_name, mobs in sorted(spots.items(), key=lambda item: item[0].casefold())
        }
        for map_name, spots in sorted(catalog.items(), key=lambda item: item[0].casefold())
    }


def load_license_status(
    state_dir: Path = STATE_DIR,
    machine_state_dir: Path = MACHINE_STATE_DIR,
) -> dict[str, Any]:
    candidates = (
        ("principal", Path(state_dir) / "license.dat"),
        ("backup", Path(state_dir) / "license.backup.dat"),
        ("máquina", Path(machine_state_dir) / "license.dat"),
        ("backup da máquina", Path(machine_state_dir) / "license.backup.dat"),
    )
    for source, path in candidates:
        state = LicenseClient._read_protected(path)
        if not state or not state.get("lease") or not state.get("public_key"):
            continue
        try:
            claims = verify_lease(state["lease"], state["public_key"])
            valid_until = _utc(claims["valid_until"])
            next_check = _utc(claims["next_check_at"])
            now = datetime.now(timezone.utc)
            if now > valid_until:
                return _license_result(False, "Prazo offline encerrado", source, claims)
            if now >= next_check:
                return _license_result(True, "Validação online pendente", source, claims)
            return _license_result(True, "Licença válida", source, claims)
        except (KeyError, TypeError, ValueError):
            return {
                "active": False,
                "message": "Comprovante local inválido",
                "source": source,
                "valid_until": None,
                "next_check_at": None,
            }
    return {
        "active": False,
        "message": "Licença ainda não ativada",
        "source": "nenhuma",
        "valid_until": None,
        "next_check_at": None,
    }


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _license_result(
    active: bool, message: str, source: str, claims: dict[str, Any]
) -> dict[str, Any]:
    return {
        "active": active,
        "message": message,
        "source": source,
        "valid_until": claims.get("valid_until"),
        "next_check_at": claims.get("next_check_at"),
    }
