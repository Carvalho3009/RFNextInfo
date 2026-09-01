"""Persistência sanitizada de identidades e catálogo observado.

Somente campos já decodificados entram neste banco. Payloads e o opcode
sensível 0x0101 nunca são aceitos.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


PROTOCOL_VERSION = "1.28.5"
SENSITIVE_OPCODE = 0x0101
PVP_STATUSES = {"ally", "enemy", "neutral", "ignored"}
MOB_LOCATION_BUCKET_UNITS = 1.0
PVE_DELTA_SCHEMA = "rf-qol.pve-observations.delta"
PVE_ACK_SCHEMA = "rf-qol.pve-observations.ack"
PVE_SCHEMA_VERSION = 1
PVE_ACK_STATUSES = {"accepted", "known", "conflict"}


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
                upload_state TEXT NOT NULL DEFAULT 'pending',
                guild_source TEXT NOT NULL DEFAULT '',
                guild_updated_at TEXT NOT NULL DEFAULT '',
                pvp_status TEXT NOT NULL DEFAULT 'neutral',
                pvp_status_source TEXT NOT NULL DEFAULT '',
                pvp_status_updated_at TEXT NOT NULL DEFAULT '',
                observation_count INTEGER NOT NULL DEFAULT 0,
                session_count INTEGER NOT NULL DEFAULT 0,
                last_session_id TEXT NOT NULL DEFAULT '',
                curation_state TEXT NOT NULL DEFAULT 'quarantine'
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
            CREATE TABLE IF NOT EXISTS mob_location_observations (
                npc_index INTEGER NOT NULL,
                protocol_version TEXT NOT NULL,
                location_key TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                map_index INTEGER,
                position_x REAL,
                position_y REAL,
                position_z REAL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                upload_state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY (npc_index, protocol_version, location_key)
            );
            CREATE INDEX IF NOT EXISTS idx_mob_locations_npc
                ON mob_location_observations(npc_index, protocol_version);
            CREATE TABLE IF NOT EXISTS mob_hp_candidates (
                npc_index INTEGER NOT NULL,
                protocol_version TEXT NOT NULL,
                max_hp INTEGER NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL DEFAULT '',
                review_state TEXT NOT NULL DEFAULT 'pending',
                upload_state TEXT NOT NULL DEFAULT 'pending',
                PRIMARY KEY (npc_index, protocol_version, max_hp)
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
            "pvp_status_source": "TEXT NOT NULL DEFAULT ''",
            "pvp_status_updated_at": "TEXT NOT NULL DEFAULT ''",
            "observation_count": "INTEGER NOT NULL DEFAULT 0",
            "session_count": "INTEGER NOT NULL DEFAULT 0",
            "last_session_id": "TEXT NOT NULL DEFAULT ''",
            "curation_state": "TEXT NOT NULL DEFAULT 'quarantine'",
        }
        for name, definition in additions.items():
            if name not in columns:
                self.conn.execute(
                    f"ALTER TABLE character_observations ADD COLUMN {name} {definition}"
                )
        for table, additions in {
            "mob_location_observations": {
                "upload_state": "TEXT NOT NULL DEFAULT 'pending'",
            },
            "mob_hp_candidates": {
                "last_seen_at": "TEXT NOT NULL DEFAULT ''",
                "upload_state": "TEXT NOT NULL DEFAULT 'pending'",
            },
        }.items():
            columns = {
                row["name"]
                for row in self.conn.execute(f"PRAGMA table_info({table})")
            }
            for name, definition in additions.items():
                if name not in columns:
                    self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {definition}"
                    )
        self.conn.execute(
            """UPDATE mob_hp_candidates SET last_seen_at=first_seen_at
               WHERE last_seen_at=''"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_mob_location_upload
               ON mob_location_observations(upload_state,last_seen_at)"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_mob_hp_upload
               ON mob_hp_candidates(upload_state,last_seen_at)"""
        )
        self.conn.execute(
            """UPDATE character_observations SET
                 guild_source=CASE WHEN guild_name!='' THEN 'observed' ELSE '' END,
                 guild_updated_at=CASE WHEN guild_name!='' THEN last_seen_at ELSE '' END,
                 pvp_status_updated_at=first_seen_at
               WHERE pvp_status_updated_at=''"""
        )
        self.conn.execute(
            """UPDATE character_observations SET pvp_status_source='manual'
               WHERE pvp_status_source='' AND pvp_status!='neutral'"""
        )
        self.conn.execute(
            """UPDATE character_observations SET
                 observation_count=MAX(1,observation_count),
                 curation_state=CASE
                   WHEN upload_state='sent'
                     OR guild_source='manual'
                     OR pvp_status_source='manual'
                     OR guild_name!=''
                     OR pvp_status!='neutral'
                   THEN 'final' ELSE 'quarantine' END
               WHERE curation_state NOT IN ('final','quarantine')
                  OR observation_count<1
                  OR (curation_state='quarantine' AND (
                       upload_state='sent'
                       OR guild_source='manual'
                       OR pvp_status_source='manual'
                       OR guild_name!=''
                       OR pvp_status!='neutral'))"""
        )
        self.conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_character_curation_status_name
               ON character_observations(
                   curation_state,pvp_status,name COLLATE NOCASE
               )"""
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def _record_character_sighting(
        self, uid: str, seen_at: str, session_id: str
    ) -> None:
        session = _text(session_id, 128)
        self.conn.execute(
            """UPDATE character_observations SET
                 last_seen_at=?,
                 observation_count=observation_count+1,
                 session_count=session_count+CASE
                   WHEN ?!='' AND last_session_id!=? THEN 1 ELSE 0 END,
                 last_session_id=CASE WHEN ?!='' THEN ? ELSE last_session_id END,
                 curation_state=CASE
                   WHEN curation_state='final'
                     OR guild_source='manual'
                     OR pvp_status_source='manual'
                     OR guild_name!=''
                     OR pvp_status!='neutral'
                     OR session_count+CASE
                       WHEN ?!='' AND last_session_id!=? THEN 1 ELSE 0 END>=2
                   THEN 'final' ELSE 'quarantine' END
               WHERE character_uid=?""",
            (
                seen_at,
                session, session,
                session, session,
                session, session,
                uid,
            ),
        )

    def _character(
        self, item: dict[str, Any], seen_at: str, session_id: str = ""
    ) -> bool:
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
            (
                _text(item.get("pvp_status"), 12).casefold()
                if _text(item.get("pvp_status"), 12).casefold() in {"ally", "enemy"}
                else "neutral"
            ),
            (
                "observed"
                if _text(item.get("pvp_status"), 12).casefold() in {"ally", "enemy"}
                else ""
            ),
            seen_at,
            PROTOCOL_VERSION,
            seen_at,
            seen_at,
        )
        current = self.conn.execute(
            """SELECT name,level,biosuit_item_index,rover_item_index,
                      guild_id,guild_name,guild_source,pvp_status,
                      pvp_status_source,upload_state
               FROM character_observations WHERE character_uid=?""",
            (str(uid),),
        ).fetchone()
        if current is not None:
            changed = any((
                bool(values[1]) and values[1] != current["name"],
                values[2] is not None and values[2] != current["level"],
                values[3] is not None and values[3] != current["biosuit_item_index"],
                values[4] is not None and values[4] != current["rover_item_index"],
                values[5] is not None and values[5] != current["guild_id"],
                bool(values[6])
                and current["guild_source"] != "manual"
                and (
                    values[6] != current["guild_name"]
                    or current["guild_source"] != "observed"
                ),
                values[10] == "observed"
                and current["pvp_status_source"] != "manual"
                and (
                    values[9] != current["pvp_status"]
                    or current["pvp_status_source"] != "observed"
                ),
            ))
            if not changed:
                self._record_character_sighting(str(uid), seen_at, session_id)
                return True
        self.conn.execute(
            """INSERT INTO character_observations
               (character_uid,name,level,biosuit_item_index,rover_item_index,
                guild_id,guild_name,guild_source,guild_updated_at,
                pvp_status,pvp_status_source,pvp_status_updated_at,
                protocol_version,first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(character_uid) DO UPDATE SET
                 name=CASE WHEN excluded.name!='' THEN excluded.name ELSE name END,
                 level=COALESCE(excluded.level,level),
                 biosuit_item_index=COALESCE(excluded.biosuit_item_index,biosuit_item_index),
                 rover_item_index=COALESCE(excluded.rover_item_index,rover_item_index),
                 guild_id=COALESCE(excluded.guild_id,guild_id),
                 guild_name=CASE WHEN guild_source!='manual' AND excluded.guild_name!='' THEN excluded.guild_name ELSE guild_name END,
                 guild_source=CASE WHEN guild_source!='manual' AND excluded.guild_name!='' THEN 'observed' ELSE guild_source END,
                 guild_updated_at=CASE WHEN guild_source!='manual' AND excluded.guild_name!='' THEN excluded.guild_updated_at ELSE guild_updated_at END,
                 pvp_status=CASE WHEN pvp_status_source!='manual' AND excluded.pvp_status_source='observed' THEN excluded.pvp_status ELSE pvp_status END,
                 pvp_status_source=CASE WHEN pvp_status_source!='manual' AND excluded.pvp_status_source='observed' THEN 'observed' ELSE pvp_status_source END,
                 pvp_status_updated_at=CASE WHEN pvp_status_source!='manual' AND excluded.pvp_status_source='observed' THEN excluded.pvp_status_updated_at ELSE pvp_status_updated_at END,
                 last_seen_at=excluded.last_seen_at,upload_state='pending'""",
            values,
        )
        self._record_character_sighting(str(uid), seen_at, session_id)
        return True

    def _guild_relation(self, data: dict[str, Any], seen_at: str) -> None:
        relation = str(data.get("relation") or "")
        status = "enemy" if relation == "enemy" else "ally" if relation == "amity" else ""
        if not status:
            return
        for guild in data.get("guilds") or []:
            if not isinstance(guild, dict):
                continue
            guild_id = str(_integer(guild.get("guild_id")) or "")
            if not guild_id:
                continue
            guild_name = _text(guild.get("guild_name"), 80)
            self.conn.execute(
                """UPDATE character_observations SET
                     guild_name=CASE WHEN guild_source!='manual' AND ?!='' THEN ? ELSE guild_name END,
                     guild_source=CASE WHEN guild_source!='manual' AND ?!='' THEN 'observed' ELSE guild_source END,
                     guild_updated_at=CASE WHEN guild_source!='manual' AND ?!='' THEN ? ELSE guild_updated_at END,
                     pvp_status=CASE WHEN pvp_status_source!='manual' THEN ? ELSE pvp_status END,
                     pvp_status_source=CASE WHEN pvp_status_source!='manual' THEN 'observed' ELSE pvp_status_source END,
                     pvp_status_updated_at=CASE WHEN pvp_status_source!='manual' THEN ? ELSE pvp_status_updated_at END,
                     curation_state='final',
                     upload_state='pending'
                   WHERE guild_id=? AND (
                     (pvp_status_source!='manual' AND
                       (pvp_status!=? OR pvp_status_source!='observed'))
                     OR
                     (?!='' AND guild_source!='manual' AND
                       (guild_name!=? OR guild_source!='observed'))
                   )""",
                (
                    guild_name, guild_name,
                    guild_name,
                    guild_name, seen_at,
                    status, seen_at, guild_id,
                    status,
                    guild_name, guild_name,
                ),
            )

    @staticmethod
    def _mob_location(
        item: dict[str, Any], location: object
    ) -> dict[str, Any] | None:
        context = location if isinstance(location, dict) else {}
        label = _text(
            context.get("label")
            or context.get("map_name")
            or (location if isinstance(location, str) else item.get("location")),
            160,
        )
        map_index = _integer(context.get("map_index"))
        raw_position = item.get("position")
        if not isinstance(raw_position, dict):
            raw_position = context.get("position")
        position: dict[str, float] | None = None
        if isinstance(raw_position, dict):
            try:
                values = {
                    axis: round(float(raw_position.get(axis)), 3)
                    for axis in ("x", "y", "z")
                }
            except (TypeError, ValueError):
                values = {}
            if len(values) == 3 and all(
                math.isfinite(value) and abs(value) <= 1_000_000_000
                for value in values.values()
            ):
                position = values
        if map_index is None and not label and position is None:
            return None
        identity = {
            "map_index": map_index,
            "label": label.casefold(),
            "position_bucket": (
                {
                    axis: round(value / MOB_LOCATION_BUCKET_UNITS)
                    for axis, value in position.items()
                }
                if position else None
            ),
        }
        canonical = json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return {
            "key": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            "label": label,
            "map_index": map_index,
            "position": position,
        }

    def _remember_mob_location(
        self,
        npc: int,
        seen_at: str,
        item: dict[str, Any],
        location: object,
    ) -> tuple[bool, str]:
        observed = self._mob_location(item, location)
        if observed is None:
            return False, ""
        position = observed["position"] or {}
        inserted = self.conn.execute(
            """INSERT OR IGNORE INTO mob_location_observations
               (npc_index,protocol_version,location_key,label,map_index,
                position_x,position_y,position_z,first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                npc,
                PROTOCOL_VERSION,
                observed["key"],
                observed["label"],
                observed["map_index"],
                position.get("x"),
                position.get("y"),
                position.get("z"),
                seen_at,
                seen_at,
            ),
        ).rowcount > 0
        if not inserted:
            self.conn.execute(
                """UPDATE mob_location_observations SET last_seen_at=?
                   WHERE npc_index=? AND protocol_version=? AND location_key=?""",
                (seen_at, npc, PROTOCOL_VERSION, observed["key"]),
            )
        return inserted, str(observed["label"] or "")

    def _remember_mob_hp_candidate(
        self, npc: int, max_hp: int, seen_at: str
    ) -> bool:
        inserted = self.conn.execute(
            """INSERT OR IGNORE INTO mob_hp_candidates
               (npc_index,protocol_version,max_hp,first_seen_at,last_seen_at)
               VALUES(?,?,?,?,?)""",
            (npc, PROTOCOL_VERSION, max_hp, seen_at, seen_at),
        ).rowcount > 0
        if not inserted:
            self.conn.execute(
                """UPDATE mob_hp_candidates SET last_seen_at=?
                   WHERE npc_index=? AND protocol_version=? AND max_hp=?""",
                (seen_at, npc, PROTOCOL_VERSION, max_hp),
            )
        return inserted

    def _mob(self, item: dict[str, Any], seen_at: str, location: object) -> bool:
        npc = _integer(item.get("npc_index"))
        if npc is None or npc <= 0:
            return False
        max_hp = _integer(item.get("max_hp"))
        incoming = {
            "name": _text(item.get("name"), 100),
            "level": _integer(item.get("level")),
            "max_hp": max_hp if max_hp and max_hp > 0 else None,
        }
        current = self.conn.execute(
            """SELECT name,level,max_hp,location FROM mob_observations
               WHERE npc_index=? AND protocol_version=?""",
            (npc, PROTOCOL_VERSION),
        ).fetchone()
        new_location, location_label = self._remember_mob_location(
            npc, seen_at, item, location
        )
        if current is None:
            self.conn.execute(
                """INSERT INTO mob_observations
                   (npc_index,protocol_version,name,level,max_hp,location,
                    first_seen_at,last_seen_at) VALUES(?,?,?,?,?,?,?,?)""",
                (
                    npc,
                    PROTOCOL_VERSION,
                    incoming["name"],
                    incoming["level"],
                    incoming["max_hp"],
                    location_label,
                    seen_at,
                    seen_at,
                ),
            )
            return True
        canonical_hp = current["max_hp"]
        if (
            incoming["max_hp"] is not None
            and canonical_hp is not None
            and incoming["max_hp"] != canonical_hp
        ):
            self._remember_mob_hp_candidate(
                npc, int(incoming["max_hp"]), seen_at
            )
        changed = any(
            incoming[field] not in (None, "")
            and incoming[field] != current[field]
            for field in ("name", "level")
        ) or (incoming["max_hp"] is not None and canonical_hp is None)
        if not changed:
            self.conn.execute(
                """UPDATE mob_observations SET
                     location=CASE WHEN location='' AND ?!='' THEN ? ELSE location END,
                     last_seen_at=?
                   WHERE npc_index=? AND protocol_version=?""",
                (location_label, location_label, seen_at, npc, PROTOCOL_VERSION),
            )
            return new_location
        self.conn.execute(
            """UPDATE mob_observations SET
                 name=CASE WHEN ?!='' THEN ? ELSE name END,
                 level=COALESCE(?,level),
                 max_hp=CASE WHEN max_hp IS NULL THEN COALESCE(?,max_hp) ELSE max_hp END,
                 location=CASE WHEN ?!='' THEN ? ELSE location END,
                 last_seen_at=?,upload_state='pending'
               WHERE npc_index=? AND protocol_version=?""",
            (
                incoming["name"], incoming["name"],
                incoming["level"], incoming["max_hp"],
                location_label, location_label,
                seen_at, npc, PROTOCOL_VERSION,
            ),
        )
        return True

    def observe_events(
        self,
        events: Iterable[dict[str, Any]],
        *,
        location: object = "",
        session_id: str = "",
    ) -> dict[str, int]:
        characters = mobs = 0
        guild_relations: dict[str, tuple[str, str]] = {}
        seen_at = _now()
        for event in events:
            if _integer(event.get("opcode")) == SENSITIVE_OPCODE:
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else event
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
            kind = str(event.get("type") or data.get("type") or "")
            if kind in {"enemy_guild_list", "amity_guild_list"}:
                self._guild_relation(data, seen_at)
                status = "enemy" if kind == "enemy_guild_list" else "ally"
                for guild in data.get("guilds") or []:
                    if isinstance(guild, dict) and _integer(guild.get("guild_id")):
                        guild_relations[str(_integer(guild.get("guild_id")))] = (
                            _text(guild.get("guild_name"), 80), status
                        )
            elif kind in {"character_list", "ans_all_character_infos"}:
                for item in fields.get("characters") or []:
                    if isinstance(item, dict) and self._character(
                        item, seen_at, session_id
                    ):
                        characters += 1
            elif kind == "world_info_prefix":
                if self._character(fields, seen_at, session_id):
                    characters += 1
            elif kind == "exp_rank_list":
                for item in data.get("records") or []:
                    if isinstance(item, dict) and self._character(
                        item, seen_at, session_id
                    ):
                        characters += 1
            elif kind == "appear_player_list":
                for item in fields.get("units") or []:
                    if not isinstance(item, dict):
                        continue
                    relation = guild_relations.get(str(_integer(item.get("guild_id")) or ""))
                    if relation:
                        item = {
                            **item,
                            "guild_name": relation[0],
                            "pvp_status": relation[1],
                        }
                    if self._character(item, seen_at, session_id):
                        characters += 1
            elif kind == "appear_monster_list":
                for item in fields.get("units") or []:
                    if isinstance(item, dict) and self._mob(item, seen_at, location):
                        mobs += 1
        self.conn.commit()
        return {"characters": characters, "mobs": mobs}

    def observe_exp_rank_records(
        self,
        records: Iterable[dict[str, Any]],
        *,
        session_id: str = "",
    ) -> int:
        """Incorpora nomes de personagem e guilda confirmados pelo Top 100."""
        seen_at = _now()
        observed = sum(
            1
            for item in records
            if isinstance(item, dict)
            and self._character(item, seen_at, session_id)
        )
        self.conn.commit()
        return observed

    def observe_combat(
        self,
        monitors: Iterable[dict[str, Any]],
        *,
        location: object = "",
        session_id: str = "",
    ) -> dict[str, int]:
        characters = mobs = 0
        seen_at = _now()
        for monitor in monitors:
            for item in monitor.get("nearby_players") or []:
                if isinstance(item, dict) and self._character(
                    item, seen_at, session_id
                ):
                    characters += 1
            local = monitor.get("local")
            if isinstance(local, dict) and self._character(
                local, seen_at, session_id
            ):
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
                      pvp_status,pvp_status_source,pvp_status_updated_at,
                      protocol_version,first_seen_at,last_seen_at
               FROM character_observations
               WHERE upload_state='pending' AND curation_state='final'
               ORDER BY last_seen_at LIMIT ?""",
            (limit,),
        )]
        for item in characters:
            item["guild_presence_known"] = (
                item.get("guild_source") in {"manual", "observed"}
                or bool(item.get("guild_name"))
            )
            item["pvp_status_presence_known"] = (
                item.get("pvp_status_source") in {"manual", "observed"}
            )
        mobs = [dict(row) for row in self.conn.execute(
            """SELECT npc_index,name,level,
                      CASE WHEN max_hp>0 THEN max_hp END AS max_hp,
                      location,protocol_version,
                      first_seen_at,last_seen_at
               FROM mob_observations WHERE upload_state='pending'
               ORDER BY last_seen_at LIMIT ?""",
            (limit,),
        )]
        return {"schema_version": 2, "characters": characters, "mobs": mobs}

    @staticmethod
    def _pve_observation_id(item: dict[str, Any]) -> str:
        stable = {
            key: value
            for key, value in item.items()
            if key not in {"observation_id", "first_seen_at", "last_seen_at"}
        }
        canonical = json.dumps(
            stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _pve_record(cls, kind: str, row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
        source = dict(row)
        if kind == "mob":
            item = {
                "kind": kind,
                "npc_index": int(source["npc_index"]),
                "protocol_version": str(source["protocol_version"]),
                "name": str(source.get("name") or ""),
                "level": source.get("level"),
                "max_hp": source.get("max_hp"),
                "first_seen_at": str(source["first_seen_at"]),
                "last_seen_at": str(source["last_seen_at"]),
            }
        elif kind == "location":
            position = None
            if all(source.get(key) is not None for key in (
                "position_x", "position_y", "position_z"
            )):
                position = {
                    "x": float(source["position_x"]),
                    "y": float(source["position_y"]),
                    "z": float(source["position_z"]),
                }
            item = {
                "kind": kind,
                "npc_index": int(source["npc_index"]),
                "protocol_version": str(source["protocol_version"]),
                "location_key": str(source["location_key"]),
                "label": str(source.get("label") or ""),
                "map_index": source.get("map_index"),
                "position": position,
                "first_seen_at": str(source["first_seen_at"]),
                "last_seen_at": str(source["last_seen_at"]),
            }
        elif kind == "hp_candidate":
            item = {
                "kind": kind,
                "npc_index": int(source["npc_index"]),
                "protocol_version": str(source["protocol_version"]),
                "max_hp": int(source["max_hp"]),
                "first_seen_at": str(source["first_seen_at"]),
                "last_seen_at": str(source["last_seen_at"]),
            }
        else:
            raise ValueError("tipo de observação PvE inválido")
        item["observation_id"] = cls._pve_observation_id(item)
        return item

    def pending_pve_delta(self, limit: int = 500) -> dict[str, Any]:
        """Retorna somente mudanças PvE ainda não confirmadas pelo site."""
        remaining = max(1, min(500, int(limit)))
        observations: list[dict[str, Any]] = []
        queries = (
            (
                "mob",
                """SELECT npc_index,protocol_version,name,level,
                          CASE WHEN max_hp>0 THEN max_hp END AS max_hp,
                          first_seen_at,last_seen_at
                     FROM mob_observations WHERE upload_state='pending'
                     ORDER BY last_seen_at,npc_index LIMIT ?""",
            ),
            (
                "location",
                """SELECT npc_index,protocol_version,location_key,label,map_index,
                          position_x,position_y,position_z,first_seen_at,last_seen_at
                     FROM mob_location_observations WHERE upload_state='pending'
                     ORDER BY last_seen_at,npc_index,location_key LIMIT ?""",
            ),
            (
                "hp_candidate",
                """SELECT npc_index,protocol_version,max_hp,first_seen_at,last_seen_at
                     FROM mob_hp_candidates WHERE upload_state='pending'
                     ORDER BY last_seen_at,npc_index,max_hp LIMIT ?""",
            ),
        )
        for kind, query in queries:
            if remaining <= 0:
                break
            rows = self.conn.execute(query, (remaining,)).fetchall()
            observations.extend(self._pve_record(kind, row) for row in rows)
            remaining -= len(rows)
        return {
            "schema": PVE_DELTA_SCHEMA,
            "schema_version": PVE_SCHEMA_VERSION,
            "observations": observations,
        }

    def mark_pve_ack(
        self, delta: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, int]:
        """Confirma apenas registros explicitamente reconhecidos pelo site."""
        if (
            not isinstance(response, dict)
            or response.get("schema") != PVE_ACK_SCHEMA
            or response.get("schema_version") != PVE_SCHEMA_VERSION
            or not isinstance(response.get("acks"), list)
        ):
            raise ValueError("O site não confirmou o contrato do Banco PvE")
        requested = {
            str(item.get("observation_id") or ""): item
            for item in delta.get("observations") or []
            if isinstance(item, dict)
        }
        accepted: dict[str, str] = {}
        for raw in response["acks"]:
            if not isinstance(raw, dict):
                raise ValueError("Confirmação PvE inválida")
            identifier = str(raw.get("observation_id") or "")
            status = str(raw.get("status") or "")
            if identifier not in requested or status not in PVE_ACK_STATUSES:
                raise ValueError("Confirmação PvE inválida")
            accepted[identifier] = status

        marked = conflicts = 0
        for identifier, status in accepted.items():
            item = requested[identifier]
            kind = item["kind"]
            if kind == "mob":
                row = self.conn.execute(
                    """SELECT npc_index,protocol_version,name,level,max_hp,
                              first_seen_at,last_seen_at
                         FROM mob_observations
                        WHERE npc_index=? AND protocol_version=?""",
                    (item["npc_index"], item["protocol_version"]),
                ).fetchone()
                table, where, values = (
                    "mob_observations",
                    "npc_index=? AND protocol_version=?",
                    (item["npc_index"], item["protocol_version"]),
                )
            elif kind == "location":
                row = self.conn.execute(
                    """SELECT npc_index,protocol_version,location_key,label,map_index,
                              position_x,position_y,position_z,first_seen_at,last_seen_at
                         FROM mob_location_observations
                        WHERE npc_index=? AND protocol_version=? AND location_key=?""",
                    (item["npc_index"], item["protocol_version"], item["location_key"]),
                ).fetchone()
                table, where, values = (
                    "mob_location_observations",
                    "npc_index=? AND protocol_version=? AND location_key=?",
                    (item["npc_index"], item["protocol_version"], item["location_key"]),
                )
            else:
                row = self.conn.execute(
                    """SELECT npc_index,protocol_version,max_hp,first_seen_at,last_seen_at
                         FROM mob_hp_candidates
                        WHERE npc_index=? AND protocol_version=? AND max_hp=?""",
                    (item["npc_index"], item["protocol_version"], item["max_hp"]),
                ).fetchone()
                table, where, values = (
                    "mob_hp_candidates",
                    "npc_index=? AND protocol_version=? AND max_hp=?",
                    (item["npc_index"], item["protocol_version"], item["max_hp"]),
                )
            if row is None or self._pve_record(kind, row)["observation_id"] != identifier:
                continue
            self.conn.execute(
                f"UPDATE {table} SET upload_state='sent' WHERE {where}", values
            )
            marked += 1
            conflicts += int(status == "conflict")
        self.conn.commit()
        return {
            "acknowledged": marked,
            "conflicts": conflicts,
            "missing": max(0, len(requested) - marked),
        }

    def mob_locations(self, npc_index: object | None = None) -> list[dict[str, Any]]:
        npc = _integer(npc_index)
        where = "" if npc is None else "WHERE npc_index=?"
        values: tuple[object, ...] = () if npc is None else (npc,)
        return [
            dict(row)
            for row in self.conn.execute(
                f"""SELECT npc_index,protocol_version,label,map_index,
                           position_x,position_y,position_z,
                           first_seen_at,last_seen_at
                    FROM mob_location_observations {where}
                    ORDER BY npc_index,label,position_x,position_y,position_z""",
                values,
            )
        ]

    def mob_hp_candidates(self, npc_index: object | None = None) -> list[dict[str, Any]]:
        npc = _integer(npc_index)
        where = "" if npc is None else "WHERE npc_index=?"
        values: tuple[object, ...] = () if npc is None else (npc,)
        return [
            dict(row)
            for row in self.conn.execute(
                f"""SELECT npc_index,protocol_version,max_hp,first_seen_at,review_state
                    FROM mob_hp_candidates {where}
                    ORDER BY npc_index,max_hp""",
                values,
            )
        ]

    def mobs(self) -> list[dict[str, Any]]:
        """Resumo local do Banco PvE sem payloads ou identidades de jogador."""
        return [
            dict(row)
            for row in self.conn.execute(
                """SELECT mobs.npc_index,mobs.protocol_version,mobs.name,mobs.level,
                          CASE WHEN mobs.max_hp>0 THEN mobs.max_hp END AS max_hp,
                          mobs.last_seen_at,mobs.upload_state,
                          (SELECT COUNT(*) FROM mob_location_observations AS locations
                           WHERE locations.npc_index=mobs.npc_index
                             AND locations.protocol_version=mobs.protocol_version)
                              AS location_count,
                          (SELECT COUNT(*) FROM mob_hp_candidates AS candidates
                           WHERE candidates.npc_index=mobs.npc_index
                             AND candidates.protocol_version=mobs.protocol_version
                             AND candidates.review_state='pending')
                              AS hp_candidate_count
                   FROM mob_observations AS mobs
                   ORDER BY mobs.name COLLATE NOCASE,mobs.npc_index"""
            )
        ]

    def characters(
        self,
        *,
        include_ignored: bool = False,
        query: str = "",
        status: str = "",
        curation_state: str = "",
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        conditions: list[str] = []
        values: list[object] = []
        if not include_ignored:
            conditions.append("pvp_status!='ignored'")
        normalized_query = str(query or "").strip()
        if normalized_query:
            conditions.append(
                "(character_uid LIKE ? OR name LIKE ? OR guild_name LIKE ?)"
            )
            pattern = f"%{normalized_query}%"
            values.extend((pattern, pattern, pattern))
        normalized_status = str(status or "").strip().casefold()
        if normalized_status in PVP_STATUSES:
            conditions.append("pvp_status=?")
            values.append(normalized_status)
        normalized_curation = str(curation_state or "").strip().casefold()
        if normalized_curation in {"final", "quarantine"}:
            conditions.append("curation_state=?")
            values.append(normalized_curation)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        limit_sql = ""
        if limit is not None:
            limit_sql = " LIMIT ?"
            values.append(max(1, int(limit)))
        return [
            dict(row)
            for row in self.conn.execute(
                f"""SELECT character_uid,name,biosuit_item_index,rover_item_index,
                           guild_name,guild_source,pvp_status,pvp_status_source,
                           last_seen_at,upload_state,observation_count,
                           session_count,curation_state
                    FROM character_observations {where}
                    ORDER BY name COLLATE NOCASE,character_uid{limit_sql}""",
                values,
            )
        ]

    def character_count(
        self,
        *,
        include_ignored: bool = False,
        query: str = "",
        status: str = "",
        curation_state: str = "",
    ) -> int:
        conditions: list[str] = []
        values: list[object] = []
        if not include_ignored:
            conditions.append("pvp_status!='ignored'")
        normalized_query = str(query or "").strip()
        if normalized_query:
            conditions.append(
                "(character_uid LIKE ? OR name LIKE ? OR guild_name LIKE ?)"
            )
            pattern = f"%{normalized_query}%"
            values.extend((pattern, pattern, pattern))
        normalized_status = str(status or "").strip().casefold()
        if normalized_status in PVP_STATUSES:
            conditions.append("pvp_status=?")
            values.append(normalized_status)
        normalized_curation = str(curation_state or "").strip().casefold()
        if normalized_curation in {"final", "quarantine"}:
            conditions.append("curation_state=?")
            values.append(normalized_curation)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        row = self.conn.execute(
            f"SELECT COUNT(*) FROM character_observations {where}", values
        ).fetchone()
        return int(row[0] or 0)

    def character(
        self, character_uid: object, *, include_ignored: bool = True
    ) -> dict[str, Any] | None:
        uid = str(_integer(character_uid) or "")
        if not uid:
            return None
        ignored = "" if include_ignored else "AND pvp_status!='ignored'"
        row = self.conn.execute(
            f"""SELECT character_uid,name,biosuit_item_index,rover_item_index,
                       guild_name,guild_source,pvp_status,pvp_status_source,
                       last_seen_at,upload_state,observation_count,
                       session_count,curation_state
                FROM character_observations
                WHERE character_uid=? {ignored}""",
            (uid,),
        ).fetchone()
        return dict(row) if row is not None else None

    def update_pvp_identity(
        self, character_uid: object, *, guild_name: object, status: object
    ) -> dict[str, Any]:
        uid = str(_integer(character_uid) or "")
        normalized_status = _text(status, 12).casefold()
        guild = _text(guild_name, 80)
        if not uid or normalized_status not in PVP_STATUSES:
            raise ValueError("UID ou status PvP inválido.")
        current = self.conn.execute(
            """SELECT guild_name,guild_source,pvp_status FROM character_observations
               WHERE character_uid=?""",
            (uid,),
        ).fetchone()
        if current is None:
            raise ValueError("UID ainda não foi observado.")
        guild_changed = guild != str(current["guild_name"] or "")
        status_changed = normalized_status != str(current["pvp_status"] or "neutral")
        if not guild_changed and not status_changed:
            return dict(
                self.conn.execute(
                    "SELECT * FROM character_observations WHERE character_uid=?",
                    (uid,),
                ).fetchone()
            )
        updated_at = _now()
        self.conn.execute(
            """UPDATE character_observations SET
                 guild_name=CASE WHEN ? THEN ? ELSE guild_name END,
                 guild_source=CASE WHEN ? THEN 'manual' ELSE guild_source END,
                 guild_updated_at=CASE WHEN ? THEN ? ELSE guild_updated_at END,
                 pvp_status=CASE WHEN ? THEN ? ELSE pvp_status END,
                 pvp_status_source=CASE WHEN ? THEN 'manual' ELSE pvp_status_source END,
                 pvp_status_updated_at=CASE WHEN ? THEN ? ELSE pvp_status_updated_at END,
                 curation_state='final',
                 upload_state='pending'
               WHERE character_uid=?""",
            (
                guild_changed, guild,
                guild_changed,
                guild_changed, updated_at,
                status_changed, normalized_status,
                status_changed,
                status_changed, updated_at,
                uid,
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
        characters = [
            (str(item["character_uid"]), str(item.get("last_seen_at") or ""))
            for item in payload.get("characters") or []
        ]
        mobs = [
            (int(item["npc_index"]), str(item.get("last_seen_at") or ""))
            for item in payload.get("mobs") or []
        ]
        if characters:
            self.conn.executemany(
                """UPDATE character_observations SET upload_state='sent'
                   WHERE character_uid=? AND last_seen_at=?""",
                characters,
            )
        if mobs:
            self.conn.executemany(
                """UPDATE mob_observations SET upload_state='sent'
                   WHERE npc_index=? AND protocol_version=? AND last_seen_at=?""",
                ((npc, PROTOCOL_VERSION, seen_at) for npc, seen_at in mobs),
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
            status = _text(item.get("pvp_status"), 12).casefold() or "neutral"
            if status not in PVP_STATUSES:
                continue
            status_source = _text(item.get("pvp_status_source"), 12).casefold()
            if status_source not in {"", "manual", "observed"}:
                continue
            if not status_source and status != "neutral":
                status_source = "manual"
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
                status,
                status_source,
                _text(item.get("pvp_status_updated_at"), 40) or first_seen,
                _text(item.get("protocol_version"), 20) or PROTOCOL_VERSION,
                first_seen,
                last_seen,
            )
            self.conn.execute(
                """INSERT INTO character_observations
                   (character_uid,name,level,biosuit_item_index,rover_item_index,
                    guild_id,guild_name,guild_source,guild_updated_at,
                    pvp_status,pvp_status_source,pvp_status_updated_at,
                    protocol_version,first_seen_at,last_seen_at,
                    upload_state)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'sent')
                   ON CONFLICT(character_uid) DO UPDATE SET
                     name=excluded.name,
                     level=excluded.level,
                     biosuit_item_index=excluded.biosuit_item_index,
                     rover_item_index=excluded.rover_item_index,
                     guild_id=excluded.guild_id,
                     guild_name=excluded.guild_name,
                     guild_source=excluded.guild_source,
                     guild_updated_at=excluded.guild_updated_at,
                     pvp_status=excluded.pvp_status,
                     pvp_status_source=excluded.pvp_status_source,
                     pvp_status_updated_at=excluded.pvp_status_updated_at,
                     protocol_version=CASE WHEN excluded.last_seen_at>=last_seen_at THEN excluded.protocol_version ELSE protocol_version END,
                     first_seen_at=MIN(first_seen_at,excluded.first_seen_at),
                     last_seen_at=MAX(last_seen_at,excluded.last_seen_at),
                     upload_state=CASE WHEN excluded.last_seen_at>=last_seen_at THEN 'sent' ELSE upload_state END""",
                values,
            )
            self.conn.execute(
                """UPDATE character_observations SET curation_state='final'
                   WHERE character_uid=?""",
                (str(uid),),
            )
            merged += 1
        self.conn.commit()
        return merged

    def curation_summary(self) -> dict[str, int]:
        counts = {
            str(state): int(count)
            for state, count in self.conn.execute(
                """SELECT curation_state,COUNT(*)
                   FROM character_observations
                   WHERE pvp_status!='ignored'
                   GROUP BY curation_state"""
            )
        }
        return {
            "final": counts.get("final", 0),
            "quarantine": counts.get("quarantine", 0),
            "ignored": int(
                self.conn.execute(
                    """SELECT COUNT(*) FROM character_observations
                       WHERE pvp_status='ignored'"""
                ).fetchone()[0]
            ),
        }

    def enrich_combat_monitors(self, monitors: Iterable[dict[str, Any]]) -> int:
        known = {
            str(row["character_uid"]): dict(row)
            for row in self.conn.execute(
                """SELECT character_uid,name,level,biosuit_item_index,rover_item_index,
                          guild_id,guild_name,guild_source,pvp_status,pvp_status_source
                   FROM character_observations"""
            )
        }
        guild_names = {
            str(row.get("guild_id") or ""): str(row.get("guild_name") or "")
            for row in known.values()
            if row.get("guild_id") and row.get("guild_name")
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
                if (
                    identity.get("pvp_status") in PVP_STATUSES
                    and (
                        identity.get("pvp_status_source") == "manual"
                        or item.get("pvp_status") not in {"ally", "enemy"}
                    )
                    and (
                    item.get("pvp_status") != identity["pvp_status"]
                    )
                ):
                    item["pvp_status"] = identity["pvp_status"]
                    changed = True
                enriched += int(changed)
            for boss in monitor.get("bosses") or []:
                guilds = boss.get("top_damage_guilds")
                if guilds is None:
                    totals: dict[str, dict[str, Any]] = {}
                    for player in boss.get("top_damage_players") or []:
                        guild = str(
                            player.get("guild_name")
                            or player.get("guild_id")
                            or ""
                        ).strip()
                        if not guild:
                            continue
                        total = totals.setdefault(
                            guild,
                            {"name": guild, "damage": 0, "dps_hp": 0.0},
                        )
                        total["damage"] += int(player.get("damage") or 0)
                        total["dps_hp"] += float(player.get("dps_hp") or 0)
                    if totals:
                        guilds = boss["top_damage_guilds"] = sorted(
                            totals.values(),
                            key=lambda item: (
                                -int(item["damage"]),
                                -float(item["dps_hp"]),
                                item["name"],
                            ),
                        )
                for guild in guilds or []:
                    guild_id = str(guild.get("guild_id") or "").strip()
                    if guild_id and guild_names.get(guild_id):
                        guild["name"] = guild_names[guild_id]
        return enriched
