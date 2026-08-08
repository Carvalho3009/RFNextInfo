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
            PROTOCOL_VERSION,
            seen_at,
            seen_at,
        )
        self.conn.execute(
            """INSERT INTO character_observations
               (character_uid,name,level,biosuit_item_index,rover_item_index,
                guild_id,guild_name,protocol_version,first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(character_uid) DO UPDATE SET
                 name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                 level=COALESCE(excluded.level,level),
                 biosuit_item_index=COALESCE(excluded.biosuit_item_index,biosuit_item_index),
                 rover_item_index=COALESCE(excluded.rover_item_index,rover_item_index),
                 guild_id=COALESCE(excluded.guild_id,guild_id),
                 guild_name=CASE WHEN excluded.guild_name!='' THEN excluded.guild_name ELSE guild_name END,
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
                      guild_id,guild_name,protocol_version,first_seen_at,last_seen_at
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
        return {"schema_version": 1, "characters": characters, "mobs": mobs}

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
