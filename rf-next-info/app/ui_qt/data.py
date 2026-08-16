from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from app.license import LicenseClient
from app.main import (
    App as StableApp,
    CLASS_ICON_FILES,
    DB_PATH,
    INVENTORY_CATEGORIES,
    ITEM_GRADES,
    MACHINE_STATE_DIR,
    PREFERENCES_PATH,
    RARITY_COLORS,
    STATE_DIR,
    game_data_language,
    inventory_category,
    item_names_for_language,
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


def _inventory_item_name(item_index: int, language: str) -> str:
    key = str(item_index)
    return str(
        item_names_for_language(language).get(key) or f"Item {item_index}"
    )


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
                game_data_language(language),
            )
            snapshot["capture_windows"] = (
                database.capture_windows(self.current_session)
                if self.current_session else []
            )
            snapshot["character_history"] = database.character_history()
            snapshot["client_bindings"] = (
                database.client_bindings(self.current_session)
                if self.current_session else []
            )
            collection_counts_by_uid = {
                str(character["uid"]): database.latest_collection_envelope(
                    str(character["uid"])
                )["collection_type_counts"]
                for character in snapshot.get("characters", [])
                if character.get("uid")
            }
            snapshot["collection_type_counts_by_uid"] = collection_counts_by_uid
            snapshot["collection_type_counts"] = {
                kind: sum(int(counts.get(kind) or 0) for counts in collection_counts_by_uid.values())
                for kind in (1, 2)
            }
            snapshot["inventories"] = {}
            if self.current_session:
                for profile in snapshot.get("profiles", []):
                    uid = str(profile.get("uid") or "")
                    if not uid:
                        continue
                    snapshot["inventories"][uid] = [
                        {
                            "item_index": int(item.get("item_index") or 0),
                            "name": _inventory_item_name(
                                int(item.get("item_index") or 0), language
                            ),
                            "quantity": int(item.get("count") or 0),
                            "kind": str(item.get("item_kind") or ""),
                            "category": inventory_category(
                                int(item.get("item_index") or 0),
                                str(item.get("item_kind") or ""),
                            ),
                            "slot": int(item.get("inventory_slot") or 0),
                            "refinement": int(item.get("enchant_level") or 0),
                            "locked": bool(item.get("lock")),
                            "expires_at": int(item.get("expire_time") or 0),
                            "rarity": int(
                                ITEM_GRADES.get(
                                    str(item.get("item_index") or 0), 0
                                )
                                or 0
                            ),
                            "observed_at_ns": item.get("observed_at_ns"),
                        }
                        for item in database.inventory_items(
                            self.current_session, uid
                        )
                    ]
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

    def load_combat(
        self, language: str = "pt", modes: Iterable[str] | None = None
    ) -> dict[str, Any]:
        """Lê somente os monitores sem reconstruir toda a sessão."""
        self.license.require("leitura dos monitores")
        if not self.database_path.exists():
            return {"session_id": None, "combat_monitors": []}
        database = CaptureStore(self.database_path, readonly=True)
        try:
            session_id = database.latest_session()
            monitors = []
            if session_id:
                active_modes = (
                    {"pve", "pvp", "boss"} if modes is None else set(modes)
                )
                names = load_npc_names(language) if "pve" in active_modes else {}
                bosses = load_boss_catalog(language) if "boss" in active_modes else {}
                for profile in database.session_profiles(session_id):
                    monitor = summarize_combat(
                        database.combat_events(session_id, profile["uid"]),
                        profile["uid"],
                        names,
                        boss_catalog=bosses,
                        modes=active_modes,
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
        modes: Iterable[str] | None = None,
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
        active_modes = {"pve", "pvp", "boss"} if modes is None else set(modes)
        names = load_npc_names(language) if "pve" in active_modes else {}
        bosses = load_boss_catalog(language) if "boss" in active_modes else {}
        identities: dict[str, dict[str, Any]] = {
            str(profile.get("client_key") or ""): profile
            for profile in profiles
            if profile.get("uid")
        }
        keys = [
            f"client:{chr(97 + index)}"
            for index in range(len(client_ports[:7]))
        ]
        uid_to_key = {
            str(profile.get("uid")): key
            for key, profile in identities.items()
            if key in keys and profile.get("uid")
        }
        port_matches = [
            tuple(
                index
                for index, ports in enumerate(client_ports[:7])
                if _event_matches_ports(event, ports)
            )
            for event in events
        ]
        flow_owners: dict[str, str] = {}
        routed_events: list[list[dict[str, Any]]] = [[] for _key in keys]
        associated_events = 0
        identity_associated_events = 0
        for event, matches in zip(events, port_matches):
            flow = str(event.get("flow") or "")
            if event.get("type") == "world_info_prefix":
                fields = (event.get("data") or {}).get("fields") or {}
                uid = str(fields.get("character_uid") or "")
                owner = uid_to_key.get(uid)
                if not owner and len(matches) == 1:
                    owner = keys[matches[0]]
                if owner:
                    identities[owner] = {
                        "uid": uid,
                        "name": str(fields.get("character_name") or ""),
                        "client_key": owner,
                    }
                    if flow:
                        flow_owners[flow] = owner
            owner = flow_owners.get(flow)
            if owner in keys:
                routed_events[keys.index(owner)].append(event)
                associated_events += 1
                identity_associated_events += 1
                continue
            if not matches:
                continue
            for index in matches:
                routed_events[index].append(event)
            associated_events += 1
        monitors = []
        for index, routed in enumerate(routed_events):
            key = f"client:{chr(97 + index)}"
            profile = identities.get(key)
            if not profile:
                has_target = any(
                    event.get("type")
                    in {"select_target_request", "use_skill_request"}
                    and (event.get("data") or {}).get("target_uid") is not None
                    for event in routed
                )
                if not has_target:
                    continue
                profile = {"uid": "", "name": "", "client_key": key}
            monitor = summarize_combat(
                routed,
                str(profile["uid"]),
                names,
                boss_catalog=bosses,
                modes=modes,
            )
            monitor.update(
                character_uid=str(profile["uid"]),
                character_name=str(profile.get("name") or ""),
                client_key=key,
            )
            monitors.append(monitor)
        return {
            "session_id": session_id,
            "combat_monitors": monitors,
            "routing_metrics": {
                "total_events": len(events),
                "associated_events": associated_events,
                "identity_associated_events": identity_associated_events,
                "identity_bound_flows": len(flow_owners),
                "unmatched_events": len(events) - associated_events,
            },
        }

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
            "collection_type_counts_by_uid": {},
            "inventories": {},
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
