"""Estado consolidado e limitado dos encontros de Boss expostos localmente."""

from __future__ import annotations

import csv
import json
import threading
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


LOCAL_BOSS_ENCOUNTERS_SCHEMA = "rf-qol.local-boss-encounters/v1"
MAX_BOSS_CLIENTS = 64
MAX_BOSSES_PER_CLIENT = 32
MAX_PLAYERS_PER_CLIENT = 2048
MAX_PLAYERS_PER_BOSS = 512


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _utc(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    current = (value or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current.isoformat(timespec="milliseconds").replace("+00:00", "Z")


@lru_cache(maxsize=1)
def _boss_catalog() -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    try:
        with Path(__file__).with_name("boss_catalog.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            for row in csv.DictReader(source):
                npc_index = int(row.get("npc_index") or 0)
                if not npc_index:
                    continue
                name = str(row.get("name_ptbr") or row.get("name_en") or "").strip()
                result[npc_index] = {
                    "name": "" if name == "..." else name[:96],
                    "level": _integer(row.get("level")),
                }
    except (OSError, TypeError, ValueError, csv.Error):
        return {}
    return result


class AgentBossEncounterState:
    """Projeta eventos locais em retratos estáveis para o bot de Discord."""

    def __init__(self) -> None:
        self._clients: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._processed_events = 0
        self._uploaded: dict[str, tuple[str, int]] = {}

    @staticmethod
    def _new_client(client_ref: str, session_ref: str) -> dict[str, Any]:
        return {
            "client_ref": client_ref,
            "session_ref": session_ref,
            "observer_uid": None,
            "observer_name": "",
            "players": {},
            "guilds": {},
            "bosses": {},
        }

    def _client(self, event: dict[str, Any]) -> dict[str, Any]:
        client_ref = str(
            event.get("client_ref") or event.get("session_ref") or "agent"
        )[:64]
        session_ref = str(event.get("session_ref") or "")[:64]
        state = self._clients.get(client_ref)
        if state is None or (
            state.get("session_ref")
            and session_ref
            and state["session_ref"] != session_ref
        ):
            state = self._new_client(client_ref, session_ref)
            self._clients[client_ref] = state
        elif session_ref:
            state["session_ref"] = session_ref
        while len(self._clients) > MAX_BOSS_CLIENTS:
            self._clients.pop(next(iter(self._clients)))
        return state

    def observe(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            return
        kind = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        occurred_at = _utc(event.get("occurred_at"))
        with self._lock:
            self._processed_events += 1
            if kind == "session.lifecycle" and not event.get("client_ref"):
                if payload.get("state") in {"finished", "abandoned"}:
                    self._clients.clear()
                return
            state = self._client(event)
            if kind == "session.lifecycle":
                if payload.get("state") in {"finished", "abandoned"}:
                    self._clients.pop(state["client_ref"], None)
            elif kind == "character.observed":
                uid = _integer(payload.get("character_uid"))
                if uid is not None and uid > 0:
                    state["observer_uid"] = uid
                if payload.get("name"):
                    state["observer_name"] = str(payload["name"])[:96]
            elif kind == "world.players_appeared":
                self._players_appeared(state, payload)
            elif kind == "world.guilds_observed":
                self._guilds_observed(state, payload)
            elif kind == "world.monsters_appeared":
                self._monsters_appeared(state, payload, occurred_at)
            elif kind == "boss.position_observed":
                self._boss_position(state, payload, occurred_at)
            elif kind == "combat.resources_changed":
                self._resources(state, payload, occurred_at)
            elif kind in {"combat.skill_resolved", "combat.normal_attack_resolved"}:
                self._damage(state, payload, occurred_at)
            elif kind == "world.entities_disappeared":
                for entity_ref in payload.get("entity_refs") or []:
                    state["bosses"].pop(str(entity_ref), None)
                    state["players"].pop(str(entity_ref), None)
            elif kind == "combat.entity_died":
                state["bosses"].pop(str(payload.get("entity_ref") or ""), None)
            elif kind == "boss.result_observed":
                boss_ref = str(payload.get("boss_ref") or "")
                if boss_ref:
                    state["bosses"].pop(boss_ref, None)
                elif len(state["bosses"]) == 1:
                    state["bosses"].clear()

    @staticmethod
    def _players_appeared(state: dict[str, Any], payload: dict[str, Any]) -> None:
        for row in payload.get("entities") or []:
            if not isinstance(row, dict):
                continue
            entity_ref = str(row.get("entity_ref") or "")
            if not entity_ref:
                continue
            previous = state["players"].get(entity_ref) or {}
            guild_id = str(row.get("guild_id") or previous.get("guild_id") or "")[:64]
            character_uid = _integer(
                row.get("character_uid") or previous.get("character_uid")
            )
            state["players"][entity_ref] = {
                "character_uid": (
                    character_uid
                    if character_uid and 0 < character_uid <= 2**64 - 1
                    else None
                ),
                "name": str(row.get("name") or previous.get("name") or "")[:96],
                "guild_id": guild_id,
                "guild_name": str(
                    row.get("guild_name")
                    or state["guilds"].get(guild_id)
                    or previous.get("guild_name")
                    or ""
                )[:96],
            }
        protected = {
            player_ref
            for boss in state["bosses"].values()
            for player_ref in boss["damage_by_player"]
        }
        removable = [key for key in state["players"] if key not in protected]
        while len(state["players"]) > MAX_PLAYERS_PER_CLIENT and removable:
            state["players"].pop(removable.pop(0), None)

    @staticmethod
    def _guilds_observed(state: dict[str, Any], payload: dict[str, Any]) -> None:
        for row in payload.get("guilds") or []:
            if not isinstance(row, dict):
                continue
            guild_id = str(row.get("guild_id") or "")[:64]
            guild_name = str(row.get("guild_name") or "")[:96]
            if guild_id and guild_name:
                state["guilds"][guild_id] = guild_name
        for player in state["players"].values():
            guild_id = str(player.get("guild_id") or "")
            if guild_id in state["guilds"]:
                player["guild_name"] = state["guilds"][guild_id]

    @staticmethod
    def _ensure_boss(
        state: dict[str, Any],
        boss_ref: str,
        npc_index: int | None,
        occurred_at: datetime,
        *,
        current_hp: int | None = None,
        max_hp: int | None = None,
    ) -> dict[str, Any] | None:
        if not boss_ref:
            return None
        boss = state["bosses"].get(boss_ref)
        if boss is not None and npc_index and boss.get("npc_index") not in {None, npc_index}:
            state["bosses"].pop(boss_ref, None)
            boss = None
        if boss is None:
            while len(state["bosses"]) >= MAX_BOSSES_PER_CLIENT:
                state["bosses"].pop(next(iter(state["bosses"])))
            boss = {
                "encounter_ref": boss_ref,
                "npc_index": npc_index,
                "current_hp": current_hp,
                "max_hp": max_hp if max_hp and max_hp > 0 else None,
                "started_at": occurred_at,
                "updated_at": occurred_at,
                "damage_by_player": {},
            }
            state["bosses"][boss_ref] = boss
        else:
            boss["updated_at"] = max(boss["updated_at"], occurred_at)
            if npc_index is not None:
                boss["npc_index"] = npc_index
            if current_hp is not None:
                boss["current_hp"] = max(0, current_hp)
            if max_hp is not None and max_hp > 0:
                boss["max_hp"] = max_hp
        return boss

    def _monsters_appeared(
        self, state: dict[str, Any], payload: dict[str, Any], occurred_at: datetime
    ) -> None:
        catalog = _boss_catalog()
        for row in payload.get("entities") or []:
            if not isinstance(row, dict):
                continue
            npc_index = _integer(row.get("npc_index"))
            if npc_index not in catalog:
                continue
            self._ensure_boss(
                state,
                str(row.get("entity_ref") or ""),
                npc_index,
                occurred_at,
                current_hp=_integer(row.get("current_hp")),
                max_hp=_integer(row.get("max_hp")),
            )

    def _boss_position(
        self, state: dict[str, Any], payload: dict[str, Any], occurred_at: datetime
    ) -> None:
        npc_index = _integer(payload.get("npc_index"))
        if npc_index is not None and npc_index not in _boss_catalog():
            return
        self._ensure_boss(
            state,
            str(payload.get("boss_ref") or ""),
            npc_index,
            occurred_at,
        )

    @staticmethod
    def _resources(
        state: dict[str, Any], payload: dict[str, Any], occurred_at: datetime
    ) -> None:
        boss = state["bosses"].get(str(payload.get("entity_ref") or ""))
        if boss is None:
            return
        current_hp = _integer(payload.get("current_hp"))
        max_hp = _integer(payload.get("max_hp"))
        if current_hp is not None:
            boss["current_hp"] = max(0, current_hp)
        if max_hp is not None and max_hp > 0:
            boss["max_hp"] = max_hp
        boss["updated_at"] = max(boss["updated_at"], occurred_at)

    @staticmethod
    def _damage(
        state: dict[str, Any], payload: dict[str, Any], occurred_at: datetime
    ) -> None:
        if payload.get("result") not in {None, 0}:
            return
        caster_ref = str(payload.get("caster_ref") or "")
        if not caster_ref:
            return
        for effect in payload.get("effects") or []:
            if not isinstance(effect, dict):
                continue
            boss = state["bosses"].get(str(effect.get("entity_ref") or ""))
            damage = _integer(effect.get("hp_damage"))
            if boss is None or damage is None or damage <= 0:
                continue
            counters = boss["damage_by_player"]
            if caster_ref not in counters and len(counters) >= MAX_PLAYERS_PER_BOSS:
                continue
            counters[caster_ref] = int(counters.get(caster_ref) or 0) + damage
            final_hp = _integer(effect.get("final_hp"))
            if final_hp is not None:
                boss["current_hp"] = max(0, final_hp)
            boss["updated_at"] = max(boss["updated_at"], occurred_at)

    def _encounters(self, *, transport: bool) -> list[dict[str, Any]]:
        encounters = []
        catalog = _boss_catalog()
        for state in self._clients.values():
            for boss in state["bosses"].values():
                npc_index = _integer(boss.get("npc_index"))
                metadata = catalog.get(npc_index or 0) or {}
                current_hp = _integer(boss.get("current_hp"))
                max_hp = _integer(boss.get("max_hp"))
                hp_percent = (
                    round(max(0.0, min(100.0, current_hp * 100 / max_hp)), 3)
                    if current_hp is not None and max_hp and max_hp > 0
                    else None
                )
                players = []
                for player_ref, damage in boss["damage_by_player"].items():
                    profile = state["players"].get(player_ref) or {}
                    guild_id = _integer(profile.get("guild_id"))
                    guild_name = str(profile.get("guild_name") or "")[:96] or None
                    player = {
                        "name": str(profile.get("name") or "Desconhecido")[:96],
                        "uid": profile.get("character_uid"),
                        # ``guild`` permanece como alias para consumidores anteriores.
                        "guild": guild_name,
                        "guild_id": guild_id,
                        "guild_name": guild_name,
                        "damage": max(0, int(damage or 0)),
                    }
                    if transport:
                        player["_player_ref"] = player_ref
                    players.append(player)
                players.sort(key=lambda row: (-row["damage"], row["name"].casefold()))
                encounter = {
                    "encounter_ref": boss["encounter_ref"],
                    "client_ref": state["client_ref"],
                    "observer": {
                        "name": state["observer_name"] or None,
                        "uid": state["observer_uid"],
                    },
                    "boss": {
                        "npc_index": npc_index,
                        "name": metadata.get("name")
                        or (f"Boss #{npc_index}" if npc_index else "Boss confirmado"),
                        "level": metadata.get("level"),
                        "current_hp": current_hp,
                        "max_hp": max_hp,
                        "hp_percent": hp_percent,
                    },
                    "players": players,
                    "damage_total": sum(row["damage"] for row in players),
                    "started_at": _iso(boss["started_at"]),
                    "updated_at": _iso(boss["updated_at"]),
                }
                if transport:
                    encounter["_session_ref"] = state["session_ref"]
                encounters.append(encounter)
        encounters.sort(key=lambda row: (row["client_ref"], row["encounter_ref"]))
        return encounters

    @staticmethod
    def _upload_identity(encounter: dict[str, Any]) -> tuple[str, str]:
        key = "|".join((
            str(encounter.get("client_ref") or ""),
            str(encounter.get("encounter_ref") or ""),
            str(encounter.get("started_at") or ""),
        ))
        fingerprint = json.dumps(
            encounter, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return key, fingerprint

    def upload_candidates(
        self, *, now_ns: int | None = None, min_interval_ns: int = 1_000_000_000,
    ) -> list[dict[str, Any]]:
        """Retorna apenas fotografias alteradas, no máximo uma por segundo/encontro."""
        current_ns = int(now_ns if now_ns is not None else time.time_ns())
        interval = max(0, int(min_interval_ns))
        with self._lock:
            encounters = self._encounters(transport=True)
            active_keys = {self._upload_identity(row)[0] for row in encounters}
            self._uploaded = {
                key: value for key, value in self._uploaded.items()
                if key in active_keys
            }
            result = []
            for encounter in encounters:
                key, fingerprint = self._upload_identity(encounter)
                previous = self._uploaded.get(key)
                if previous is not None and previous[0] == fingerprint:
                    continue
                if previous is not None and 0 <= current_ns - previous[1] < interval:
                    continue
                result.append(encounter)
            return result

    def mark_uploaded(
        self, encounter: dict[str, Any], *, now_ns: int | None = None,
    ) -> None:
        key, fingerprint = self._upload_identity(encounter)
        with self._lock:
            self._uploaded[key] = (
                fingerprint,
                int(now_ns if now_ns is not None else time.time_ns()),
            )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            encounters = self._encounters(transport=False)
            return {
                "schema": LOCAL_BOSS_ENCOUNTERS_SCHEMA,
                "generated_at": _iso(),
                "encounter_count": len(encounters),
                "encounters": encounters,
                "processed_events": self._processed_events,
            }
