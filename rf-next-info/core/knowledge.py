"""Persistência sanitizada de identidades e catálogo observado.

Somente campos já decodificados entram neste banco. Payloads e o opcode
sensível 0x0101 nunca são aceitos.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROTOCOL_VERSION = "1.28.5"
SENSITIVE_OPCODE = 0x0101
PVP_STATUSES = {"ally", "enemy", "neutral"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value, 0) if isinstance(value, str) and value else (
            int(value) if value not in (None, "") else None
        )
    except (TypeError, ValueError):
        return None


def _text(value: Any, maximum: int = 120) -> str:
    return str(value or "").strip()[:maximum]


class KnowledgeStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS character_observations (
                character_uid TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                level INTEGER,
                biosuit_item_index INTEGER,
                rover_item_index INTEGER,
                guild_id TEXT,
                guild_name TEXT NOT NULL DEFAULT '',
                protocol_version TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                upload_state TEXT NOT NULL DEFAULT 'pending'
            );
            CREATE TABLE IF NOT EXISTS mob_observations (
                npc_index INTEGER NOT NULL,
                protocol_version TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                level INTEGER,
                max_hp INTEGER,
                location TEXT NOT NULL DEFAULT '',
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                upload_state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY (npc_index, protocol_version)
            );
            """
        )
        columns = {
            row["name"]
            for row in self.conn.execute(
                "PRAGMA table_info(character_observations)"
            )
        }
        additions = {
            "guild_source": "TEXT NOT NULL DEFAULT ''",
            "guild_updated_at": "TEXT NOT NULL DEFAULT ''",
            "pvp_status": "TEXT NOT NULL DEFAULT 'neutral'",
            "pvp_status_updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.conn.execute(
                    f"ALTER TABLE character_observations ADD COLUMN {name} {definition}"
                )
        self.conn.execute(
            """UPDATE character_observations SET
                 guild_source=CASE WHEN guild_name!='' THEN 'observed' ELSE '' END,
                 guild_updated_at=CASE WHEN guild_name!='' THEN last_seen_at ELSE '' END,
                 pvp_status_updated_at=first_seen_at
               WHERE pvp_status_updated_at=''"""
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _character(self, item: dict[str, Any], seen_at: str) -> bool:
        uid = _integer(item.get("character_uid"))
        if uid is None or uid <= 0:
            return False
        values = (
            str(uid),
            _text(item.get("name") or item.get("character_name"), 80),
            _integer(item.get("level")),
            _integer(item.get("biosuit_item_index")),
            _integer(item.get("rover_item_index")),
            _text(item.get("guild_id"), 40) or None,
            _text(item.get("guild_name"), 80),
            "observed" if _text(item.get("guild_name"), 80) else "",
            seen_at if _text(item.get("guild_name"), 80) else "",
            PROTOCOL_VERSION,
            seen_at,
            seen_at,
            seen_at,
        )
        self.conn.execute(
            """INSERT INTO character_observations
               (character_uid,name,level,biosuit_item_index,rover_item_index,
                guild_id,guild_name,guild_source,guild_updated_at,
                protocol_version,first_seen_at,last_seen_at,pvp_status_updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(character_uid) DO UPDATE SET
                 name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                 level=COALESCE(excluded.level,level),
                 biosuit_item_index=COALESCE(excluded.biosuit_item_index,biosuit_item_index),
                 rover_item_index=COALESCE(excluded.rover_item_index,rover_item_index),
                 guild_id=COALESCE(excluded.guild_id,guild_id),
                 guild_name=CASE WHEN excluded.guild_name!='' THEN excluded.guild_name ELSE guild_name END,
                 guild_source=CASE WHEN excluded.guild_name!='' THEN 'observed' ELSE guild_source END,
                 guild_updated_at=CASE WHEN excluded.guild_name!='' THEN excluded.guild_updated_at ELSE guild_updated_at END,
                 last_seen_at=excluded.last_seen_at,upload_state='pending'""",
            values,
        )
        return True

    def _mob(self, item: dict[str, Any], seen_at: str, location: str) -> bool:
        npc = _integer(item.get("npc_index"))
        if npc is None or npc <= 0:
            return False
        values = (
            npc,
            PROTOCOL_VERSION,
            _text(item.get("name"), 100),
            _integer(item.get("level")),
            _integer(item.get("max_hp")),
            _text(location or item.get("location"), 160),
            seen_at,
            seen_at,
        )
        self.conn.execute(
            """INSERT INTO mob_observations
               (npc_index,protocol_version,name,level,max_hp,location,
                first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(npc_index,protocol_version) DO UPDATE SET
                 name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                 level=COALESCE(excluded.level,level),
                 max_hp=CASE WHEN excluded.max_hp>0 THEN excluded.max_hp ELSE max_hp END,
                 location=CASE WHEN excluded.location!='' THEN excluded.location ELSE location END,
                 last_seen_at=excluded.last_seen_at,upload_state='pending'""",
            values,
        )
        return True

    def observe_events(
        self, events: Iterable[dict[str, Any]], *, location: str = ""
    ) -> dict[str, int]:
        characters = mobs = 0
        seen_at = _now()
        for event in events:
            if _integer(event.get("opcode")) == SENSITIVE_OPCODE:
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else event
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
            kind = str(event.get("type") or data.get("type") or "")
            if kind in {"character_list", "ans_all_character_infos"}:
                for item in fields.get("characters") or []:
                    if isinstance(item, dict) and self._character(item, seen_at):
                        characters += 1
            elif kind == "world_info_prefix":
                if self._character(fields, seen_at):
                    characters += 1
            elif kind == "appear_player_list":
                for item in fields.get("units") or []:
                    if isinstance(item, dict) and self._character(item, seen_at):
                        characters += 1
            elif kind == "appear_monster_list":
                for item in fields.get("units") or []:
                    if isinstance(item, dict) and self._mob(item, seen_at, location):
                        mobs += 1
        self.conn.commit()
        return {"characters": characters, "mobs": mobs}

    def observe_combat(
        self, monitors: Iterable[dict[str, Any]], *, location: str = ""
    ) -> dict[str, int]:
        characters = mobs = 0
        seen_at = _now()
        for monitor in monitors:
            for item in monitor.get("nearby_players") or []:
                if isinstance(item, dict) and self._character(item, seen_at):
                    characters += 1
            local = monitor.get("local")
            if isinstance(local, dict) and self._character(local, seen_at):
                characters += 1
            for item in [*(monitor.get("nearby_monsters") or []), *(monitor.get("bosses") or [])]:
                if isinstance(item, dict) and self._mob(item, seen_at, location):
                    mobs += 1
        self.conn.commit()
        return {"characters": characters, "mobs": mobs}

    def pending_payload(self, limit: int = 5000) -> dict[str, Any]:
        characters = [dict(row) for row in self.conn.execute(
            """SELECT character_uid,name,level,biosuit_item_index,rover_item_index,
                      guild_id,guild_name,guild_source,guild_updated_at,
                      pvp_status,pvp_status_updated_at,
                      protocol_version,first_seen_at,last_seen_at
               FROM character_observations WHERE upload_state='pending'
               ORDER BY last_seen_at LIMIT ?""",
            (limit,),
        )]
        mobs = [dict(row) for row in self.conn.execute(
            """SELECT npc_index,name,level,max_hp,location,protocol_version,
                      first_seen_at,last_seen_at
               FROM mob_observations WHERE upload_state='pending'
               ORDER BY last_seen_at LIMIT ?""",
            (limit,),
        )]
        return {"schema_version": 2, "characters": characters, "mobs": mobs}

    def characters(self) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT character_uid,name,guild_name,guild_source,pvp_status,
                          last_seen_at,upload_state
                   FROM character_observations
                   ORDER BY name COLLATE NOCASE,character_uid"""
            )
        ]

    def update_pvp_identity(
        self, character_uid: object, *, guild_name: object, status: object
    ) -> dict[str, Any]:
        uid = str(_integer(character_uid) or "")
        normalized_status = _text(status, 12).casefold()
        guild = _text(guild_name, 80)
        if not uid or normalized_status not in PVP_STATUSES:
            raise ValueError("UID ou status PvP inválido.")
        current = self.conn.execute(
            """SELECT guild_name,guild_source FROM character_observations
               WHERE character_uid=?""",
            (uid,),
        ).fetchone()
        if current is None:
            raise ValueError("UID ainda não foi observado.")
        if guild and current["guild_name"] and current["guild_source"] != "manual":
            guild = str(current["guild_name"])
        updated_at = _now()
        self.conn.execute(
            """UPDATE character_observations SET
                 guild_name=CASE WHEN ?!='' THEN ? ELSE guild_name END,
                 guild_source=CASE WHEN ?!='' AND guild_source!='observed'
                                   THEN 'manual' ELSE guild_source END,
                 guild_updated_at=CASE WHEN ?!='' AND guild_source!='observed'
                                       THEN ? ELSE guild_updated_at END,
                 pvp_status=?,pvp_status_updated_at=?,upload_state='pending'
               WHERE character_uid=?""",
            (
                guild, guild, guild, guild, updated_at,
                normalized_status, updated_at, uid,
            ),
        )
        self.conn.commit()
        return dict(
            self.conn.execute(
                "SELECT * FROM character_observations WHERE character_uid=?",
                (uid,),
            ).fetchone()
        )

    def mark_uploaded(self, payload: dict[str, Any]) -> None:
        character_ids = [str(item["character_uid"]) for item in payload.get("characters") or []]
        mob_ids = [int(item["npc_index"]) for item in payload.get("mobs") or []]
        if character_ids:
            self.conn.executemany(
                "UPDATE character_observations SET upload_state='sent' WHERE character_uid=?",
                ((value,) for value in character_ids),
            )
        if mob_ids:
            self.conn.executemany(
                """UPDATE mob_observations SET upload_state='sent'
                   WHERE npc_index=? AND protocol_version=?""",
                ((value, PROTOCOL_VERSION) for value in mob_ids),
            )
        self.conn.commit()

    def merge_remote_characters(self, characters: Iterable[dict[str, Any]]) -> int:
        """Mescla somente identidades sanitizadas devolvidas pelo site."""
        merged = 0
        for item in characters:
            if not isinstance(item, dict):
                continue
            uid = _integer(item.get("character_uid"))
            first_seen = _text(item.get("first_seen_at"), 40)
            last_seen = _text(item.get("last_seen_at"), 40)
            if uid is None or uid <= 0 or not first_seen or not last_seen:
                continue
            values = (
                str(uid),
                _text(item.get("name"), 80),
                _integer(item.get("level")),
                _integer(item.get("biosuit_item_index")),
                _integer(item.get("rover_item_index")),
                _text(item.get("guild_id"), 40) or None,
                _text(item.get("guild_name"), 80),
                _text(item.get("guild_source"), 12),
                _text(item.get("guild_updated_at"), 40),
                _text(item.get("pvp_status"), 12).casefold() or "neutral",
                _text(item.get("pvp_status_updated_at"), 40) or first_seen,
                _text(item.get("protocol_version"), 20) or PROTOCOL_VERSION,
                first_seen,
                last_seen,
            )
            self.conn.execute(
                """INSERT INTO character_observations
                   (character_uid,name,level,biosuit_item_index,rover_item_index,
                    guild_id,guild_name,guild_source,guild_updated_at,
                    pvp_status,pvp_status_updated_at,
                    protocol_version,first_seen_at,last_seen_at,
                    upload_state)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'sent')
                   ON CONFLICT(character_uid) DO UPDATE SET
                     name=CASE WHEN excluded.last_seen_at>=last_seen_at AND excluded.name!='' THEN excluded.name ELSE name END,
                     level=CASE WHEN excluded.last_seen_at>=last_seen_at THEN COALESCE(excluded.level,level) ELSE level END,
                     biosuit_item_index=CASE WHEN excluded.last_seen_at>=last_seen_at THEN COALESCE(excluded.biosuit_item_index,biosuit_item_index) ELSE biosuit_item_index END,
                     rover_item_index=CASE WHEN excluded.last_seen_at>=last_seen_at THEN COALESCE(excluded.rover_item_index,rover_item_index) ELSE rover_item_index END,
                     guild_id=CASE WHEN excluded.last_seen_at>=last_seen_at THEN COALESCE(excluded.guild_id,guild_id) ELSE guild_id END,
                     guild_name=CASE
                       WHEN excluded.guild_name='' THEN guild_name
                       WHEN excluded.guild_source='observed' THEN excluded.guild_name
                       WHEN guild_source='observed' THEN guild_name
                       WHEN excluded.guild_updated_at>=guild_updated_at THEN excluded.guild_name
                       ELSE guild_name END,
                     guild_source=CASE
                       WHEN excluded.guild_name='' THEN guild_source
                       WHEN excluded.guild_source='observed' THEN 'observed'
                       WHEN guild_source='observed' THEN guild_source
                       WHEN excluded.guild_updated_at>=guild_updated_at THEN excluded.guild_source
                       ELSE guild_source END,
                     guild_updated_at=MAX(guild_updated_at,excluded.guild_updated_at),
                     pvp_status=CASE WHEN excluded.pvp_status_updated_at>=pvp_status_updated_at THEN excluded.pvp_status ELSE pvp_status END,
                     pvp_status_updated_at=MAX(pvp_status_updated_at,excluded.pvp_status_updated_at),
                     protocol_version=CASE WHEN excluded.last_seen_at>=last_seen_at THEN excluded.protocol_version ELSE protocol_version END,
                     first_seen_at=MIN(first_seen_at,excluded.first_seen_at),
                     last_seen_at=MAX(last_seen_at,excluded.last_seen_at),
                     upload_state=CASE WHEN excluded.last_seen_at>=last_seen_at THEN 'sent' ELSE upload_state END""",
                values,
            )
            merged += 1
        self.conn.commit()
        return merged

    def enrich_combat_monitors(self, monitors: Iterable[dict[str, Any]]) -> int:
        known = {
            str(row["character_uid"]): dict(row)
            for row in self.conn.execute(
                """SELECT character_uid,name,level,biosuit_item_index,rover_item_index,
                          guild_id,guild_name,pvp_status
                   FROM character_observations"""
            )
        }
        enriched = 0
        for monitor in monitors:
            candidates = [
                monitor.get("local"),
                monitor.get("pvp"),
                *(monitor.get("nearby_players") or []),
            ]
            for boss in monitor.get("bosses") or []:
                candidates.extend(boss.get("top_damage_players") or [])
            for item in candidates:
                if not isinstance(item, dict):
                    continue
                identity = known.get(str(item.get("character_uid") or ""))
                if not identity:
                    continue
                changed = False
                for field in (
                    "name", "level", "biosuit_item_index", "rover_item_index",
                    "guild_id", "guild_name",
                ):
                    if item.get(field) in (None, "") and identity.get(field) not in (None, ""):
                        item[field] = identity[field]
                        changed = True
                if identity.get("pvp_status") in PVP_STATUSES and (
                    item.get("pvp_status") != identity["pvp_status"]
                ):
                    item["pvp_status"] = identity["pvp_status"]
                    changed = True
                enriched += int(changed)
            for boss in monitor.get("bosses") or []:
                totals: dict[str, dict[str, Any]] = {}
                for player in boss.get("top_damage_players") or []:
                    guild = str(
                        player.get("guild_name") or player.get("guild_id") or ""
                    ).strip()
                    if not guild:
                        continue
                    total = totals.setdefault(
                        guild, {"name": guild, "damage": 0, "dps_hp": 0.0}
                    )
                    total["damage"] += int(player.get("damage") or 0)
                    total["dps_hp"] += float(player.get("dps_hp") or 0)
                if totals:
                    boss["top_damage_guilds"] = sorted(
                        totals.values(),
                        key=lambda item: (-float(item["dps_hp"]), item["name"]),
                    )
        return enriched
