from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

from app.license import LicenseClient
from app.main import (
    App as StableApp,
    CLASS_ICON_FILES,
    DB_PATH,
    MACHINE_STATE_DIR,
    PREFERENCES_PATH,
    RARITY_COLORS,
    STATE_DIR,
)
from core.combat_monitor import summarize_combat
from core.store import CaptureStore


def _event_matches_ports(
    event: dict[str, Any], ports: tuple[int, ...]
) -> bool:
    endpoints = {
        int(value)
        for value in re.findall(r":(\d+)(?:\s|$)", str(event.get("flow") or ""))
    }
    return bool(endpoints.intersection(ports))


class ReadOnlySnapshotReader:
    _character_exports = StableApp._character_exports
    _load_info_snapshot = StableApp._load_info_snapshot

    def __init__(self, database_path: Path, license_client) -> None:
        self.database_path = Path(database_path)
        self.license = license_client
        self.current_session: str | None = None
        self._last_session_stats = {
            "recognized": 0,
            "unknown": 0,
            "unassigned": 0,
            "raw_bytes": 0,
        }
        self._info_worker_cache: dict[str, Any] = {}

    def load(self, language: str = "pt") -> dict[str, Any]:
        self.license.require("leitura dos dados capturados")
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
            snapshot["character_history"] = database.character_history()
            snapshot["client_bindings"] = (
                database.client_bindings(self.current_session)
                if self.current_session else []
            )
            snapshot["combat_monitors"] = []
            if self.current_session:
                names = load_npc_names(language)
                bosses = load_boss_catalog(language)
                for profile in database.session_profiles(self.current_session):
                    monitor = summarize_combat(
                        database.combat_events(self.current_session, profile["uid"]),
                        profile["uid"],
                        names,
                        boss_catalog=bosses,
                    )
                    monitor.update(
                        {
                            "character_uid": profile["uid"],
                            "character_name": profile.get("name") or "",
                            "client_key": profile.get("client_key") or "",
                        }
                    )
                    snapshot["combat_monitors"].append(monitor)
            return snapshot
        finally:
            database.close()

    def load_combat(self, language: str = "pt") -> dict[str, Any]:
        """Lê somente os monitores sem reconstruir toda a sessão."""
        self.license.require("leitura dos monitores")
        if not self.database_path.exists():
            return {"session_id": None, "combat_monitors": []}
        database = CaptureStore(self.database_path, readonly=True)
        try:
            session_id = database.latest_session()
            monitors = []
            if session_id:
                names = load_npc_names(language)
                bosses = load_boss_catalog(language)
                for profile in database.session_profiles(session_id):
                    monitor = summarize_combat(
                        database.combat_events(session_id, profile["uid"]),
                        profile["uid"],
                        names,
                        boss_catalog=bosses,
                    )
                    monitor.update(
                        {
                            "character_uid": profile["uid"],
                            "character_name": profile.get("name") or "",
                            "client_key": profile.get("client_key") or "",
                        }
                    )
                    monitors.append(monitor)
            return {"session_id": session_id, "combat_monitors": monitors}
        finally:
            database.close()

    def load_live_combat(
        self,
        events: list[dict[str, Any]],
        client_ports: tuple[tuple[int, ...], ...],
        language: str = "pt",
    ) -> dict[str, Any]:
        """Resume eventos efêmeros do Pktmon sem gravá-los no banco."""
        self.license.require("leitura do monitor em tempo real")
        session_id = None
        profiles: list[dict[str, Any]] = []
        if self.database_path.exists():
            database = CaptureStore(self.database_path, readonly=True)
            try:
                session_id = database.latest_session()
                if session_id:
                    profiles = database.session_profiles(session_id)
            finally:
                database.close()
        names = load_npc_names(language)
        bosses = load_boss_catalog(language)
        identities: dict[str, dict[str, Any]] = {
            str(profile.get("client_key") or ""): profile
            for profile in profiles
            if profile.get("uid")
        }
        for index, ports in enumerate(client_ports[:2]):
            key = f"client:{chr(97 + index)}"
            if key in identities:
                continue
            routed = [event for event in events if _event_matches_ports(event, ports)]
            for event in reversed(routed):
                if event.get("type") != "world_info_prefix":
                    continue
                fields = (event.get("data") or {}).get("fields") or {}
                if fields.get("character_uid"):
                    identities[key] = {
                        "uid": str(fields["character_uid"]),
                        "name": str(fields.get("character_name") or ""),
                        "client_key": key,
                    }
                    break
        monitors = []
        for index, ports in enumerate(client_ports[:2]):
            key = f"client:{chr(97 + index)}"
            profile = identities.get(key)
            if not profile:
                continue
            routed = [event for event in events if _event_matches_ports(event, ports)]
            monitor = summarize_combat(
                routed,
                str(profile["uid"]),
                names,
                boss_catalog=bosses,
            )
            monitor.update(
                character_uid=str(profile["uid"]),
                character_name=str(profile.get("name") or ""),
                client_key=key,
            )
            monitors.append(monitor)
        return {"session_id": session_id, "combat_monitors": monitors}

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
            "combat_monitors": [],
            "character_history": [],
            "client_bindings": [],
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


def load_npc_names(language: str = "pt") -> dict[int, str]:
    root = Path(__file__).resolve().parents[2]
    path = root / "core" / ("catalogo_en.csv" if language == "en" else "catalogo.csv")
    names: dict[int, str] = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                identifier = int(row.get("npc_id") or 0)
                name = str(row.get("mob_name") or "").strip()
                if identifier and name:
                    names[identifier] = name
    except (OSError, TypeError, ValueError, csv.Error):
        return {}
    return names


def load_boss_catalog(language: str = "pt") -> dict[int, dict[str, Any]]:
    path = Path(__file__).resolve().parents[2] / "core" / "boss_catalog.csv"
    bosses: dict[int, dict[str, Any]] = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as source:
            for row in csv.DictReader(source):
                identifier = int(row.get("npc_index") or 0)
                primary = row.get("name_en") if language == "en" else row.get("name_ptbr")
                fallback = row.get("name_ptbr") if language == "en" else row.get("name_en")
                name = str(primary or fallback or "").strip()
                bosses[identifier] = {
                    "name": "" if name == "..." else name,
                    "level": int(row.get("level") or 0),
                    "npc_subtype": int(row.get("npc_subtype") or 0),
                }
    except (OSError, TypeError, ValueError, csv.Error):
        return {}
    return bosses


def load_license_status(
    state_dir: Path = STATE_DIR,
    machine_state_dir: Path = MACHINE_STATE_DIR,
) -> dict[str, Any]:
    del state_dir
    return LicenseClient(Path(machine_state_dir)).local_status()
