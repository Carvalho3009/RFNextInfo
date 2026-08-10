"""SQLite incremental e exportação sanitizada, sem rede."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ingest import (
    DEFAULT_PORTS,
    SENSITIVE_OPCODE,
    decoded_events,
    decoder_identity,
)

SCHEMA_VERSION = 1
MAX_EXPORT_BYTES = 512 * 1024 * 1024
SENSITIVE_KEYS = ("token", "ticket", "password", "secret", "authorization", "jwt")


def _level_curve() -> dict[int, int]:
    path = Path(__file__).with_name("level_curve.json")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return {
            int(row["level"]): int(row["need_exp"])
            for row in data["level_curve"]
        }
    except (OSError, ValueError, KeyError, TypeError):
        return {}


LEVEL_CURVE = _level_curve()

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, source TEXT NOT NULL, flow TEXT NOT NULL,
 stream_offset INTEGER NOT NULL, bundle_seq INTEGER NOT NULL,
 ts_ns INTEGER, opcode INTEGER NOT NULL, type TEXT NOT NULL,
 character_uid TEXT, data_json TEXT NOT NULL,
 session_id TEXT NOT NULL DEFAULT 'legacy',
 UNIQUE(source, flow, stream_offset, bundle_seq)
);
CREATE TABLE IF NOT EXISTS captures(
 source TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
 imported_at TEXT NOT NULL, events_added INTEGER NOT NULL,
 session_id TEXT NOT NULL DEFAULT 'legacy',
 ingestion_key TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS capture_windows(
 id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, mode TEXT NOT NULL,
 started_ns INTEGER NOT NULL, ended_ns INTEGER NOT NULL,
 character_uid TEXT, upload_state TEXT NOT NULL DEFAULT 'pending',
 uploaded_at TEXT,
 UNIQUE(session_id, mode, started_ns)
);
CREATE TABLE IF NOT EXISTS subsessions(
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL, character_uid TEXT,
 client_key TEXT NOT NULL DEFAULT '',
 name TEXT NOT NULL, location TEXT NOT NULL DEFAULT '',
 map_name TEXT NOT NULL DEFAULT '', spot_name TEXT NOT NULL DEFAULT '',
 mobs_json TEXT NOT NULL DEFAULT '[]',
 mob_levels_json TEXT NOT NULL DEFAULT '{}',
 duration_minutes INTEGER NOT NULL DEFAULT 0,
 started_ns INTEGER NOT NULL, ended_ns INTEGER,
 sequence INTEGER, upload_state TEXT NOT NULL DEFAULT 'pending',
 uploaded_at TEXT
);
CREATE TABLE IF NOT EXISTS client_bindings(
 session_id TEXT NOT NULL, client_key TEXT NOT NULL,
 character_uid TEXT NOT NULL, character_name TEXT NOT NULL DEFAULT '',
 binding_source TEXT NOT NULL DEFAULT 'canonical',
 PRIMARY KEY(session_id, client_key)
);
CREATE TABLE IF NOT EXISTS character_history(
 character_uid TEXT PRIMARY KEY,
 character_name TEXT NOT NULL DEFAULT '',
 last_seen_at TEXT NOT NULL,
 last_session_id TEXT NOT NULL DEFAULT '',
 last_client_key TEXT NOT NULL DEFAULT '',
 level INTEGER,
 biosuit_item_index INTEGER,
 rover_item_index INTEGER
);
CREATE TABLE IF NOT EXISTS client_route_slots(
 session_id TEXT NOT NULL,
 physical_client_key TEXT NOT NULL,
 logical_client_key TEXT NOT NULL,
 evidence TEXT NOT NULL DEFAULT '',
 PRIMARY KEY(session_id, physical_client_key)
);
CREATE TABLE IF NOT EXISTS store_state(
 key TEXT PRIMARY KEY, value INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class ExportResult:
    json_path: Path
    csv_path: Path
    json_bytes: int
    csv_bytes: int
    sha256: str
    raw_bytes: int


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _sanitize(item)
            for key, item in value.items()
            if not any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS)
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def _character_uid(
    event: dict[str, Any], entry_identity: bool = False
) -> str | None:
    if event.get("type") != "world_info_prefix" and not (
        entry_identity and event.get("type") == "appear_player_prefix"
    ):
        return None
    fields = event["data"].get("fields") or {}
    uid = fields.get("character_uid")
    return str(uid) if uid is not None else None


def _client_key(
    flow: str, client_ports: tuple[tuple[int, ...], ...]
) -> str | None:
    match = re.search(r":(\d+)\s*->.*:(\d+)\s*$", flow)
    if not match:
        return None
    endpoints = {int(match.group(1)), int(match.group(2))}
    for index, ports in enumerate(client_ports[:2]):
        if endpoints.intersection(ports):
            return f"client:{chr(97 + index)}"
    return None


def _event_level(event: dict[str, Any]) -> int | None:
    if event.get("type") not in {"world_info_prefix", "update_exp"}:
        return None
    fields = (event.get("data") or {}).get("fields") or {}
    level = fields.get("level")
    return level if isinstance(level, int) and 1 <= level <= 999 else None


def _add_exp_percent(data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
    level, exp = fields.get("level"), fields.get("exp")
    if isinstance(level, int) and isinstance(exp, (int, float)):
        required = LEVEL_CURVE.get(level + 1)
        if required:
            fields["exp_percent"] = round(
                max(0.0, min(100.0, float(exp) * 100 / required)),
                2,
            )
    return data


class CaptureStore:
    def __init__(self, path: Path, *, readonly: bool = False) -> None:
        self.path = Path(path)
        if readonly:
            self.conn = sqlite3.connect(
                f"file:{self.path.as_posix()}?mode=ro", uri=True
            )
            self.conn.execute("PRAGMA query_only=ON")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        with self.conn:
            for table in ("events", "captures"):
                columns = {
                    row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")
                }
                if "session_id" not in columns:
                    self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy'"
                    )
                if table == "captures" and "ingestion_key" not in columns:
                    self.conn.execute(
                        "ALTER TABLE captures ADD COLUMN "
                        "ingestion_key TEXT NOT NULL DEFAULT ''"
                    )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_session "
                "ON events(session_id, character_uid, id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_captures_session "
                "ON captures(session_id, imported_at)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_windows_session "
                "ON capture_windows(session_id, started_ns)"
            )
            window_columns = {
                row[1]
                for row in self.conn.execute(
                    "PRAGMA table_info(capture_windows)"
                )
            }
            for column, definition in (
                ("character_uid", "TEXT"),
                ("upload_state", "TEXT NOT NULL DEFAULT 'pending'"),
                ("uploaded_at", "TEXT"),
            ):
                if column not in window_columns:
                    self.conn.execute(
                        f"ALTER TABLE capture_windows ADD COLUMN "
                        f"{column} {definition}"
                    )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_subsessions_session "
                "ON subsessions(session_id, character_uid, started_ns)"
            )
            subsession_columns = {
                row[1]
                for row in self.conn.execute(
                    "PRAGMA table_info(subsessions)"
                )
            }
            if "duration_minutes" not in subsession_columns:
                self.conn.execute(
                    "ALTER TABLE subsessions ADD COLUMN "
                    "duration_minutes INTEGER NOT NULL DEFAULT 0"
                )
            for column, definition in (
                ("client_key", "TEXT NOT NULL DEFAULT ''"),
                ("map_name", "TEXT NOT NULL DEFAULT ''"),
                ("spot_name", "TEXT NOT NULL DEFAULT ''"),
                ("sequence", "INTEGER"),
                ("upload_state", "TEXT NOT NULL DEFAULT 'pending'"),
                ("uploaded_at", "TEXT"),
            ):
                if column not in subsession_columns:
                    self.conn.execute(
                        f"ALTER TABLE subsessions ADD COLUMN "
                        f"{column} {definition}"
                    )
            sequence = int(
                self.conn.execute(
                    "SELECT COALESCE(MAX(sequence),0) FROM subsessions"
                ).fetchone()[0]
            )
            for (identifier,) in self.conn.execute(
                """SELECT id FROM subsessions WHERE sequence IS NULL
                   ORDER BY started_ns,id"""
            ):
                sequence += 1
                self.conn.execute(
                    "UPDATE subsessions SET sequence=? WHERE id=?",
                    (sequence, identifier),
                )
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_subsessions_sequence "
                "ON subsessions(sequence)"
            )
            self.conn.execute(
                """INSERT OR IGNORE INTO store_state(key,value)
                   VALUES('subsession_sequence',0)"""
            )
            self.conn.execute(
                """INSERT OR IGNORE INTO store_state(key,value)
                   VALUES('event_revision',0)"""
            )

            self.conn.execute(
                """UPDATE store_state
                   SET value=MAX(
                       value,
                       (SELECT COALESCE(MAX(sequence),0) FROM subsessions)
                   )
                   WHERE key='subsession_sequence'"""
            )
            binding_columns = {
                row[1]
                for row in self.conn.execute(
                    "PRAGMA table_info(client_bindings)"
                )
            }
            if "binding_source" not in binding_columns:
                self.conn.execute(
                    "ALTER TABLE client_bindings ADD COLUMN "
                    "binding_source TEXT NOT NULL DEFAULT 'canonical'"
                )
            history_columns = {
                row[1]
                for row in self.conn.execute(
                    "PRAGMA table_info(character_history)"
                )
            }
            for column in ("level", "biosuit_item_index", "rover_item_index"):
                if column not in history_columns:
                    self.conn.execute(
                        f"ALTER TABLE character_history ADD COLUMN {column} INTEGER"
                    )
            known_uids: set[str] = set()
            for uid, name, session_id, client_key, last_seen_at in self.conn.execute(
                """SELECT bindings.character_uid,bindings.character_name,
                          bindings.session_id,bindings.client_key,
                          COALESCE(MAX(captures.imported_at),'1970-01-01T00:00:00+00:00')
                   FROM client_bindings AS bindings
                   LEFT JOIN captures ON captures.session_id=bindings.session_id
                   WHERE bindings.binding_source='canonical'
                   GROUP BY bindings.character_uid,bindings.character_name,
                            bindings.session_id,bindings.client_key
                   ORDER BY MAX(captures.imported_at) DESC"""
            ):
                if uid in known_uids:
                    continue
                known_uids.add(uid)
                self.conn.execute(
                    """INSERT OR IGNORE INTO character_history
                       (character_uid,character_name,last_seen_at,
                        last_session_id,last_client_key)
                       VALUES(?,?,?,?,?)""",
                    (uid, name, last_seen_at, session_id, client_key),
                )
            for uid, last_session_id in self.conn.execute(
                """SELECT character_uid,last_session_id FROM character_history
                   WHERE level IS NULL AND last_session_id!=''"""
            ).fetchall():
                rows = self.conn.execute(
                    """SELECT data_json FROM events
                       WHERE session_id=? AND character_uid=?
                       AND type IN ('world_info_prefix','update_exp')
                       ORDER BY id DESC LIMIT 64""",
                    (last_session_id, uid),
                ).fetchall()
                level = None
                for (raw,) in rows:
                    fields = json.loads(raw).get("fields") or {}
                    if isinstance(fields.get("level"), int):
                        level = fields["level"]
                        break
                if level is not None:
                    self.conn.execute(
                        "UPDATE character_history SET level=? WHERE character_uid=?",
                        (level, uid),
                    )

    def _bump_event_revision(self) -> None:
        self.conn.execute(
            "UPDATE store_state SET value=value+1 WHERE key='event_revision'"
        )

    def event_revision(self) -> int:
        row = self.conn.execute(
            "SELECT value FROM store_state WHERE key='event_revision'"
        ).fetchone()
        return int(row[0]) if row else 0

    def close(self) -> None:
        self.conn.close()

    def add_events(
        self,
        source: Path,
        events: Iterable[dict[str, Any]],
        session_id: str = "legacy",
        ingestion_key: str = "",
        client_ports: tuple[tuple[int, ...], ...] = (),
        append_only: bool = False,
        restrict_to_clients: bool = False,
    ) -> int:
        if not session_id or len(session_id) > 128:
            raise ValueError("session_id inválido")
        source = Path(source)
        stat = source.stat()
        existing = self.conn.execute(
            """SELECT size,mtime_ns,session_id,ingestion_key,events_added
               FROM captures WHERE source=?""",
            (str(source),),
        ).fetchone()
        if existing and tuple(existing[:4]) == (
            stat.st_size,
            stat.st_mtime_ns,
            session_id,
            ingestion_key,
        ):
            return 0
        growing_source = bool(
            append_only
            and existing
            and existing[2] == session_id
            and existing[3] == ingestion_key
            and stat.st_size > existing[0]
        )

        raw_events = [
            event
            for event in events
            if event.get("opcode") != SENSITIVE_OPCODE
            and (
                not restrict_to_clients
                or _client_key(event.get("flow", ""), client_ports) is not None
            )
        ]
        binding_rows = self.conn.execute(
            """SELECT client_key,character_uid,binding_source
               FROM client_bindings WHERE session_id=?""",
            (session_id,),
        ).fetchall()
        manual_bindings = {
            client_key: uid
            for client_key, uid, source_name in binding_rows
            if source_name == "manual"
        }
        route_slots = {
            physical: logical
            for physical, logical in self.conn.execute(
                """SELECT physical_client_key,logical_client_key
                   FROM client_route_slots WHERE session_id=?""",
                (session_id,),
            )
        }
        inferred_routes: dict[str, tuple[str, str]] = {}
        if len(manual_bindings) == 2 and len(route_slots) < 2:
            logical_by_uid = {uid: key for key, uid in manual_bindings.items()}
            for event in raw_events:
                physical = _client_key(event["flow"], client_ports)
                if not (
                    physical
                    and event.get("type") == "world_info_prefix"
                    and re.match(r"^\S+:12020\s*->", event["flow"])
                ):
                    continue
                uid = _character_uid(event)
                logical = logical_by_uid.get(uid or "")
                if logical:
                    inferred_routes[physical] = (logical, "canonical_uid")

            history_levels = {
                key: level
                for key, uid in manual_bindings.items()
                for (level,) in self.conn.execute(
                    "SELECT level FROM character_history WHERE character_uid=?",
                    (uid,),
                )
                if isinstance(level, int)
            }
            observed_levels: dict[str, int] = {}
            for event in raw_events:
                physical = _client_key(event["flow"], client_ports)
                level = _event_level(event)
                if physical and level is not None:
                    observed_levels[physical] = level
            for physical, level in observed_levels.items():
                matches = [
                    logical
                    for logical, known_level in history_levels.items()
                    if known_level == level
                ]
                if len(matches) == 1:
                    inferred_routes.setdefault(
                        physical, (matches[0], "historical_level")
                    )

            combined = {
                **route_slots,
                **{
                    physical: logical
                    for physical, (logical, _evidence) in inferred_routes.items()
                },
            }
            if len(set(combined.values())) != len(combined):
                inferred_routes.clear()
            elif len(combined) == 1:
                physical, logical = next(iter(combined.items()))
                if physical != logical:
                    other_physical = (
                        "client:b" if physical == "client:a" else "client:a"
                    )
                    other_logical = (
                        "client:b" if logical == "client:a" else "client:a"
                    )
                    inferred_routes.setdefault(
                        other_physical, (other_logical, "two_client_inference")
                    )
        logical_routes = {
            **route_slots,
            **{
                physical: logical
                for physical, (logical, _evidence) in inferred_routes.items()
            },
        }
        uid_routes = {
            character_uid: client_key
            for client_key, character_uid in self.conn.execute(
                """SELECT client_key,character_uid FROM client_bindings
                   WHERE session_id=?""",
                (session_id,),
            )
        }
        reserved_routes = set(uid_routes.values())
        for event in raw_events:
            physical_key = _client_key(event["flow"], client_ports)
            client_key = logical_routes.get(physical_key, physical_key)
            if not (
                client_key
                and event.get("type") == "world_info_prefix"
                and re.match(r"^\S+:12020\s*->", event["flow"])
            ):
                continue
            uid = _character_uid(event)
            if uid:
                uid_routes[uid] = client_key
                reserved_routes.add(client_key)
        character_windows = self.conn.execute(
            """SELECT started_ns,ended_ns FROM capture_windows
               WHERE session_id=? AND mode='character'""",
            (session_id,),
        ).fetchall()
        entry_markers: dict[tuple[str, int], set[int]] = {}
        entry_appearances: dict[tuple[str, int], int] = {}
        for event in raw_events:
            ts_ns = event.get("ts_ns")
            if (
                isinstance(ts_ns, int)
                and any(start <= ts_ns <= end for start, end in character_windows)
            ):
                key = (event["flow"], ts_ns)
                if event.get("opcode") in {0x0202, 0x0323}:
                    entry_markers.setdefault(key, set()).add(
                        int(event["opcode"])
                    )
                if event.get("type") == "appear_player_prefix":
                    entry_appearances[key] = entry_appearances.get(key, 0) + 1
        entry_identities = {
            key for key, markers in entry_markers.items()
            if markers == {0x0202, 0x0323}
            and entry_appearances.get(key) == 1
        }
        prepared: list[
            tuple[
                dict[str, Any],
                dict[str, Any],
                str | None,
                str | None,
                str | None,
            ]
        ] = []
        flow_uids: dict[str, set[str]] = {}
        for event in raw_events:
            clean = _sanitize(event["data"])
            physical_key = _client_key(event["flow"], client_ports)
            client_key = logical_routes.get(physical_key, physical_key)
            canonical_identity = (
                event.get("type") == "world_info_prefix"
                and bool(re.match(r"^\S+:12020\s*->", event["flow"]))
            )
            identity_event = {**event, "data": clean}
            canonical_uid = (
                _character_uid(identity_event) if canonical_identity else None
            )
            if canonical_uid and not client_key:
                client_key = uid_routes.get(canonical_uid)
                if not client_key:
                    client_key = next(
                        (
                            key
                            for key in ("client:a", "client:b")
                            if key not in reserved_routes
                        ),
                        None,
                    )
                    if client_key:
                        uid_routes[canonical_uid] = client_key
                        reserved_routes.add(client_key)
            entry_identity = (
                bool(client_key)
                and event.get("type") == "appear_player_prefix"
                and (event["flow"], event.get("ts_ns")) in entry_identities
                and bool(re.match(r"^\S+:12020\s*->", event["flow"]))
            )
            uid = canonical_uid or _character_uid(identity_event, entry_identity)
            binding_source = (
                "canonical"
                if uid and canonical_identity
                else "heuristic"
                if uid and entry_identity
                else None
            )
            if uid and not client_key:
                flow_uids.setdefault(event["flow"], set()).add(uid)
            prepared.append(
                (event, clean, uid, client_key, binding_source)
            )
        stable_flow_uid = {
            flow: next(iter(uids))
            for flow, uids in flow_uids.items()
            if len(uids) == 1
        }

        added = 0
        rewritten = False
        with self.conn:
            if inferred_routes:
                self.conn.executemany(
                    """INSERT INTO client_route_slots
                       (session_id,physical_client_key,logical_client_key,evidence)
                       VALUES(?,?,?,?)
                       ON CONFLICT(session_id,physical_client_key) DO UPDATE SET
                       logical_client_key=excluded.logical_client_key,
                       evidence=excluded.evidence""",
                    [
                        (session_id, physical, logical, evidence)
                        for physical, (logical, evidence) in inferred_routes.items()
                    ],
                )
                uid_remap = {
                    manual_bindings[physical]: manual_bindings[logical]
                    for physical, (logical, _evidence) in inferred_routes.items()
                    if physical in manual_bindings
                    and logical in manual_bindings
                    and physical != logical
                }
                if uid_remap:
                    clauses = " ".join(
                        "WHEN character_uid=? THEN ?" for _ in uid_remap
                    )
                    parameters = list(
                        itertools.chain.from_iterable(uid_remap.items())
                    )
                    parameters.extend((session_id, *uid_remap.keys()))
                    updated = self.conn.execute(
                        f"""UPDATE events SET character_uid=CASE {clauses}
                            ELSE character_uid END
                            WHERE session_id=? AND character_uid IN
                            ({','.join('?' for _ in uid_remap)})""",
                        parameters,
                    )
                    rewritten = rewritten or bool(updated.rowcount)
            bindings = {
                client_key: (character_uid, binding_source)
                for client_key, character_uid, binding_source
                in self.conn.execute(
                    """SELECT client_key,character_uid,binding_source
                       FROM client_bindings
                       WHERE session_id=?""",
                    (session_id,),
                )
            }
            for identity_source in ("canonical", "heuristic"):
                for event, clean, uid, client_key, binding_source in prepared:
                    if not (
                        uid
                        and client_key
                        and binding_source == identity_source
                    ):
                        continue
                    current = bindings.get(client_key)
                    if identity_source == "heuristic" and current:
                        continue
                    fields = clean.get("fields") or {}
                    name = str(fields.get("character_name") or "")
                    bindings[client_key] = (uid, identity_source)
                    self.conn.execute(
                        """INSERT INTO client_bindings
                           (session_id,client_key,character_uid,
                            character_name,binding_source)
                           VALUES(?,?,?,?,?)
                           ON CONFLICT(session_id,client_key) DO UPDATE SET
                           character_uid=excluded.character_uid,
                           character_name=excluded.character_name,
                           binding_source=excluded.binding_source""",
                        (
                            session_id,
                            client_key,
                            uid,
                            name,
                            identity_source,
                        ),
                    )
                    if (
                        identity_source == "canonical"
                        and current
                        and current[1] == "manual"
                        and current[0] != uid
                    ):
                        self.conn.execute(
                            """UPDATE events SET character_uid=?
                               WHERE session_id=? AND character_uid=?""",
                            (uid, session_id, current[0]),
                        )
                    if identity_source == "canonical":
                        self.conn.execute(
                            """INSERT INTO character_history
                               (character_uid,character_name,last_seen_at,
                                last_session_id,last_client_key,level)
                               VALUES(?,?,?,?,?,?)
                               ON CONFLICT(character_uid) DO UPDATE SET
                               character_name=CASE
                                   WHEN excluded.character_name!=''
                                   THEN excluded.character_name
                                   ELSE character_history.character_name END,
                               last_seen_at=excluded.last_seen_at,
                               last_session_id=excluded.last_session_id,
                               last_client_key=excluded.last_client_key,
                               level=COALESCE(excluded.level,character_history.level)""",
                            (
                                uid,
                                name,
                                datetime.now(timezone.utc).isoformat(),
                                session_id,
                                client_key,
                                fields.get("level")
                                if isinstance(fields.get("level"), int)
                                else None,
                            ),
                        )
                    updated = self.conn.execute(
                        """UPDATE events SET character_uid=?
                           WHERE session_id=? AND character_uid=?""",
                        (uid, session_id, client_key),
                    )
                    rewritten = rewritten or bool(updated.rowcount)
            # O histórico de equipamento só aceita o world_info canônico ou a
            # aparência de entrada vinculada ao mesmo UID. Aparições de
            # personagens próximos nunca passam por este caminho.
            for event, clean, uid, client_key, binding_source in prepared:
                binding = bindings.get(client_key) if client_key else None
                if not binding or binding[1] != "canonical":
                    continue
                fields = clean.get("fields") or {}
                observed_uid = fields.get("character_uid")
                own_world_info = (
                    event.get("type") == "world_info_prefix"
                    and binding_source == "canonical"
                    and uid == binding[0]
                )
                own_appearance = (
                    event.get("type") == "appear_player_prefix"
                    and observed_uid is not None
                    and str(observed_uid) == binding[0]
                )
                if not (own_world_info or own_appearance):
                    continue
                biosuit = fields.get("biosuit_item_index")
                rover = fields.get("rover_item_index")
                biosuit = biosuit if isinstance(biosuit, int) else None
                rover = rover if isinstance(rover, int) else None
                if biosuit is None and rover is None:
                    continue
                self.conn.execute(
                    """UPDATE character_history SET
                       biosuit_item_index=COALESCE(?,biosuit_item_index),
                       rover_item_index=COALESCE(?,rover_item_index)
                       WHERE character_uid=?""",
                    (biosuit, rover, binding[0]),
                )
            if existing and not growing_source:
                self.conn.execute(
                    "DELETE FROM events WHERE source=?", (str(source),)
                )
                rewritten = True
            for event, clean, uid, client_key, _binding_source in prepared:
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO events
                    (source,flow,stream_offset,bundle_seq,ts_ns,opcode,type,
                     character_uid,data_json,session_id)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        str(source),
                        event["flow"],
                        event["stream_offset"],
                        event["bundle_seq"],
                        event.get("ts_ns"),
                        event["opcode"],
                        event["type"],
                        (
                            bindings.get(
                                client_key, (client_key, None)
                            )[0]
                            if client_key
                            else uid or stable_flow_uid.get(event["flow"])
                        ),
                        json.dumps(clean, ensure_ascii=False, sort_keys=True),
                        session_id,
                    ),
                )
                added += cursor.rowcount
            for (flow,) in self.conn.execute(
                """SELECT DISTINCT flow FROM events
                   WHERE session_id=? AND character_uid IS NULL
                   AND type!='unparsed'""",
                (session_id,),
            ):
                physical_key = _client_key(flow, client_ports)
                client_key = logical_routes.get(physical_key, physical_key)
                binding = bindings.get(client_key) if client_key else None
                if not binding:
                    continue
                updated = self.conn.execute(
                    """UPDATE events SET character_uid=?
                       WHERE session_id=? AND flow=?
                       AND character_uid IS NULL AND type!='unparsed'""",
                    (binding[0], session_id, flow),
                )
                rewritten = rewritten or bool(updated.rowcount)
            self.conn.execute(
                """INSERT INTO captures
                (source,size,mtime_ns,imported_at,events_added,session_id,
                 ingestion_key)
                VALUES(?,?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET
                size=excluded.size,mtime_ns=excluded.mtime_ns,
                imported_at=excluded.imported_at,
                events_added=excluded.events_added,
                session_id=excluded.session_id,
                ingestion_key=excluded.ingestion_key""",
                (
                    str(source),
                    stat.st_size,
                    stat.st_mtime_ns,
                    datetime.now(timezone.utc).isoformat(),
                    (int(existing[4]) if growing_source else 0) + added,
                    session_id,
                    ingestion_key,
                ),
            )
            if rewritten:
                self._bump_event_revision()
        return added

    def ingest(
        self,
        source: Path,
        *,
        session_id: str = "legacy",
        decoder_path: Path | None = None,
        ports: tuple[int, ...] = DEFAULT_PORTS,
        client_ports: tuple[tuple[int, ...], ...] = (),
        append_only: bool = False,
        restrict_to_clients: bool = False,
    ) -> int:
        ports = tuple(dict.fromkeys(ports or DEFAULT_PORTS))
        client_ports = tuple(tuple(dict.fromkeys(group)) for group in client_ports)
        ingestion_key = (
            decoder_identity(decoder_path, ports)
            + "|clients="
            + ";".join(",".join(map(str, group)) for group in client_ports)
            + f"|trusted_clients={int(restrict_to_clients)}"
        )
        return self.add_events(
            source,
            decoded_events(source, decoder_path=decoder_path, ports=ports),
            session_id,
            ingestion_key,
            client_ports,
            append_only,
            restrict_to_clients,
        )

    def clear_exported(self, session_id: str | None = None) -> None:
        with self.conn:
            if session_id is None:
                self.conn.execute("DELETE FROM events")
                self.conn.execute("DELETE FROM captures")
                self.conn.execute("DELETE FROM client_bindings")
                self.conn.execute("DELETE FROM client_route_slots")
            else:
                self.conn.execute(
                    "DELETE FROM events WHERE session_id=?", (session_id,)
                )
                self.conn.execute(
                    "DELETE FROM captures WHERE session_id=?", (session_id,)
                )
                self.conn.execute(
                    "DELETE FROM client_bindings WHERE session_id=?",
                    (session_id,),
                )
                self.conn.execute(
                    "DELETE FROM client_route_slots WHERE session_id=?",
                    (session_id,),
                )
            self._bump_event_revision()

    def clear_session(self, session_id: str) -> None:
        with self.conn:
            for table in (
                "capture_windows",
                "subsessions",
                "client_bindings",
                "client_route_slots",
                "events",
                "captures",
            ):
                self.conn.execute(
                    f"DELETE FROM {table} WHERE session_id=?", (session_id,)
                )
            self._bump_event_revision()

    def remove_sources(self, sources: Iterable[Path]) -> None:
        values = [(str(Path(source)),) for source in sources]
        if not values:
            return
        with self.conn:
            self.conn.executemany("DELETE FROM events WHERE source=?", values)
            self.conn.executemany("DELETE FROM captures WHERE source=?", values)
            self._bump_event_revision()

    def latest_session(self) -> str | None:
        row = self.conn.execute(
            "SELECT session_id FROM captures ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def character_history(self) -> list[dict[str, Any]]:
        return [
            {
                "uid": uid,
                "name": name,
                "last_seen_at": last_seen_at,
                "last_session_id": last_session_id,
                "last_client_key": last_client_key,
                "level": level,
                "biosuit_item_index": biosuit_item_index,
                "rover_item_index": rover_item_index,
            }
            for (
                uid,
                name,
                last_seen_at,
                last_session_id,
                last_client_key,
                level,
                biosuit_item_index,
                rover_item_index,
            )
            in self.conn.execute(
                """SELECT character_uid,character_name,last_seen_at,
                          last_session_id,last_client_key,level,
                          biosuit_item_index,rover_item_index
                   FROM character_history
                   ORDER BY last_seen_at DESC,character_name,character_uid"""
            )
        ]

    def client_bindings(self, session_id: str) -> list[dict[str, str]]:
        return [
            {
                "client_key": client_key,
                "uid": uid,
                "name": name,
                "source": source,
            }
            for client_key, uid, name, source in self.conn.execute(
                """SELECT client_key,character_uid,character_name,binding_source
                   FROM client_bindings WHERE session_id=? ORDER BY client_key""",
                (session_id,),
            )
        ]

    def select_client_uid(
        self,
        session_id: str,
        client_key: str,
        character_uid: str | None,
    ) -> None:
        if not session_id or client_key not in {"client:a", "client:b"}:
            raise ValueError("Sessão ou cliente inválido")
        with self.conn:
            current = self.conn.execute(
                """SELECT character_uid,binding_source FROM client_bindings
                   WHERE session_id=? AND client_key=?""",
                (session_id, client_key),
            ).fetchone()
            if character_uid is None:
                if current and current[1] == "manual":
                    self.conn.execute(
                        "DELETE FROM client_bindings WHERE session_id=? AND client_key=?",
                        (session_id, client_key),
                    )
                    self.conn.execute(
                        "DELETE FROM client_route_slots WHERE session_id=?",
                        (session_id,),
                    )
                return
            uid = str(character_uid).strip()
            history = self.conn.execute(
                """SELECT character_name FROM character_history
                   WHERE character_uid=?""",
                (uid,),
            ).fetchone()
            if not history:
                raise ValueError("UID não existe no histórico confirmado")
            duplicate = self.conn.execute(
                """SELECT client_key FROM client_bindings
                   WHERE session_id=? AND character_uid=? AND client_key!=?""",
                (session_id, uid, client_key),
            ).fetchone()
            if duplicate:
                raise ValueError("O UID já está vinculado ao outro cliente")
            if current and current[1] == "canonical" and current[0] != uid:
                raise ValueError(
                    "O jogo já confirmou outro UID para este cliente nesta sessão"
                )
            if current and current[1] == "canonical":
                return
            if not current or current[0] != uid:
                self.conn.execute(
                    "DELETE FROM client_route_slots WHERE session_id=?",
                    (session_id,),
                )
            self.conn.execute(
                """INSERT INTO client_bindings
                   (session_id,client_key,character_uid,character_name,binding_source)
                   VALUES(?,?,?,?, 'manual')
                   ON CONFLICT(session_id,client_key) DO UPDATE SET
                   character_uid=excluded.character_uid,
                   character_name=excluded.character_name,
                   binding_source='manual'""",
                (session_id, client_key, uid, history[0]),
            )
            self.conn.execute(
                """UPDATE events SET character_uid=?
                   WHERE session_id=? AND character_uid=?""",
                (uid, session_id, client_key),
            )

    def session_profiles(self, session_id: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            """WITH uids AS (
                   SELECT DISTINCT character_uid AS uid FROM events
                   WHERE session_id=? AND character_uid IS NOT NULL
                   AND type!='unparsed'
               ), latest_world AS (
                   SELECT character_uid AS uid,MAX(id) AS event_id FROM events
                   WHERE session_id=? AND character_uid IS NOT NULL
                   AND type='world_info_prefix' GROUP BY character_uid
               )
               SELECT uids.uid,events.data_json FROM uids
               LEFT JOIN latest_world ON latest_world.uid=uids.uid
               LEFT JOIN events ON events.id=latest_world.event_id
               ORDER BY uids.uid""",
            (session_id, session_id),
        ).fetchall()
        profiles: dict[str, str] = {}
        for uid, raw in rows:
            data = json.loads(raw) if raw else {}
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
            profiles[uid] = str(
                fields.get("character_name") or fields.get("character") or ""
            ).strip()
        bindings = self.conn.execute(
            """SELECT client_key,character_uid,character_name
               FROM client_bindings WHERE session_id=? ORDER BY client_key""",
            (session_id,),
        ).fetchall()
        client_keys = {uid: key for key, uid, _name in bindings}
        for _key, uid, name in bindings:
            if name:
                profiles[uid] = name
        result = []
        for uid, name in profiles.items():
            client_key = client_keys.get(uid)
            if uid.startswith("client:"):
                client_key = uid
            item = {"uid": uid, "name": name}
            if client_key:
                item["client_key"] = client_key
            result.append(item)
        return sorted(
            result,
            key=lambda item: (
                item.get("client_key", "client:z"),
                item["uid"],
            ),
        )

    def unidentified_exp_flows(
        self, session_id: str
    ) -> list[dict[str, str | float]]:
        rows = self.conn.execute(
            """SELECT flow,data_json FROM events
               WHERE session_id=? AND character_uid IS NULL
               AND type='update_exp' ORDER BY id""",
            (session_id,),
        ).fetchall()
        latest: dict[str, float] = {}
        for flow, raw in rows:
            data = _add_exp_percent(json.loads(raw))
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
            value = fields.get("exp_percent")
            if isinstance(value, (int, float)):
                latest[flow] = float(value)
        return [
            {"flow": flow, "exp_percent": value}
            for flow, value in latest.items()
        ]

    def assign_unidentified_by_exp(
        self, session_id: str, targets: list[tuple[str, float]]
    ) -> list[dict[str, str | float]]:
        flows = self.unidentified_exp_flows(session_id)
        if not targets or len(flows) < len(targets) or len(targets) > 2:
            return []
        best = min(
            itertools.permutations(flows, len(targets)),
            key=lambda ordered: sum(
                abs(float(flow["exp_percent"]) - target)
                for flow, (_, target) in zip(ordered, targets)
            ),
        )
        matches = []
        with self.conn:
            for index, ((name, target), flow) in enumerate(
                zip(targets, best), 1
            ):
                uid = f"exp:{index}"
                self.conn.execute(
                    """UPDATE events SET character_uid=?
                       WHERE session_id=? AND flow=?
                       AND character_uid IS NULL AND type!='unparsed'""",
                    (uid, session_id, flow["flow"]),
                )
                matches.append(
                    {
                        "uid": uid,
                        "name": name,
                        "target_percent": target,
                        "observed_percent": float(flow["exp_percent"]),
                    }
                )
            self._bump_event_revision()
        return matches

    def assign_unidentified_to_uid_by_exp(
        self, session_id: str, uid: str, target: float
    ) -> dict[str, str | float] | None:
        flows = self.unidentified_exp_flows(session_id)
        if not uid or not flows:
            return None
        flow = min(
            flows,
            key=lambda item: abs(float(item["exp_percent"]) - target),
        )
        with self.conn:
            self.conn.execute(
                """UPDATE events SET character_uid=?
                   WHERE session_id=? AND flow=?
                   AND character_uid IS NULL AND type!='unparsed'""",
                (uid, session_id, flow["flow"]),
            )
            self._bump_event_revision()
        return {
            "uid": uid,
            "target_percent": target,
            "observed_percent": float(flow["exp_percent"]),
        }

    def session_stats(self, session_id: str) -> dict[str, int | None]:
        recognized, unknown, unassigned, started, ended = self.conn.execute(
            """SELECT SUM(type!='unparsed'), SUM(type='unparsed'),
               SUM(type!='unparsed' AND character_uid IS NULL), MIN(ts_ns), MAX(ts_ns)
               FROM events WHERE session_id=?""",
            (session_id,),
        ).fetchone()
        raw_bytes = self.conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM captures WHERE session_id=?",
            (session_id,),
        ).fetchone()[0]
        return {
            "recognized": int(recognized or 0),
            "unknown": int(unknown or 0),
            "unassigned": int(unassigned or 0),
            "started_ns": started,
            "ended_ns": ended,
            "raw_bytes": int(raw_bytes or 0),
        }

    def session_sources(self, session_id: str) -> list[Path]:
        return [
            Path(row[0])
            for row in self.conn.execute(
                "SELECT source FROM captures WHERE session_id=?", (session_id,)
            )
        ]

    def add_capture_window(
        self,
        session_id: str,
        mode: str,
        started_ns: int,
        ended_ns: int,
        character_uid: str | None = None,
    ) -> None:
        if (
            not session_id
            or mode not in {"character", "market", "codex", "memory_chips"}
            or started_ns <= 0
            or ended_ns <= started_ns
        ):
            raise ValueError("janela de captura inválida")
        with self.conn:
            self.conn.execute(
                """INSERT OR IGNORE INTO capture_windows
                   (session_id,mode,started_ns,ended_ns,character_uid)
                   VALUES(?,?,?,?,?)""",
                (
                    session_id,
                    mode,
                    started_ns,
                    ended_ns,
                    character_uid,
                ),
            )

    def pending_capture_uploads(self, session_id: str) -> list[dict[str, Any]]:
        return [
            {
                "mode": mode,
                "started_ns": started_ns,
                "ended_ns": ended_ns,
                "character_uid": character_uid,
            }
            for mode, started_ns, ended_ns, character_uid in self.conn.execute(
                """SELECT mode,started_ns,ended_ns,character_uid
                   FROM capture_windows
                   WHERE session_id=? AND upload_state='pending'
                     AND mode IN ('market','codex','memory_chips')
                   ORDER BY started_ns""",
                (session_id,),
            )
        ]

    def set_capture_upload_state(
        self,
        session_id: str,
        mode: str,
        started_ns: int,
        state: str,
    ) -> None:
        if state not in {"pending", "sent", "empty"}:
            raise ValueError("estado de envio inválido")
        uploaded_at = (
            datetime.now(timezone.utc).isoformat()
            if state in {"sent", "empty"}
            else None
        )
        with self.conn:
            self.conn.execute(
                """UPDATE capture_windows
                   SET upload_state=?,uploaded_at=?
                   WHERE session_id=? AND mode=? AND started_ns=?""",
                (state, uploaded_at, session_id, mode, started_ns),
            )

    def completed_market_signature(self, session_id: str) -> str:
        completed: dict[int, int] = {}
        for event_id, data_json in self.conn.execute(
            """SELECT id,data_json FROM events
               WHERE session_id=? AND opcode=? ORDER BY id""",
            (session_id, 0x1D02),
        ):
            try:
                data = json.loads(data_json)
            except (TypeError, ValueError):
                continue
            if data.get("ret") in (None, 0) and data.get("is_end") is True:
                completed[int(data.get("exchange_server_type") or 0)] = int(event_id)
        if not completed:
            return ""
        canonical = json.dumps(sorted(completed.items()), separators=(",", ":"))
        return hashlib.sha256(f"{session_id}:{canonical}".encode()).hexdigest()

    def capture_windows(self, session_id: str) -> list[dict[str, Any]]:
        return [
            {
                "mode": mode,
                "started_ns": started_ns,
                "ended_ns": ended_ns,
            }
            for mode, started_ns, ended_ns in self.conn.execute(
                """SELECT mode,started_ns,ended_ns FROM capture_windows
                   WHERE session_id=? ORDER BY started_ns""",
                (session_id,),
            )
        ]

    def start_subsession(
        self,
        subsession_id: str,
        session_id: str,
        name: str,
        *,
        character_uid: str | None = None,
        client_key: str = "",
        location: str = "",
        map_name: str = "",
        spot_name: str = "",
        mobs: list[str] | None = None,
        mob_levels: dict[str, int | str] | None = None,
        duration_minutes: int = 0,
        started_ns: int,
    ) -> None:
        name, location = name.strip(), location.strip()
        client_key = client_key.strip().casefold()
        if client_key not in {"", "client:a", "client:b"}:
            raise ValueError("cliente da subsessão inválido")
        map_name, spot_name = map_name.strip(), spot_name.strip()
        mobs = [str(mob).strip() for mob in (mobs or []) if str(mob).strip()]
        normalized_levels: dict[str, int | str] = {}
        for mob, level in (mob_levels or {}).items():
            mob = str(mob).strip()
            text = str(level).strip()
            match = re.fullmatch(r"(\d{1,3})(?:-(\d{1,3}))?", text)
            if not mob or not match:
                continue
            first = int(match.group(1))
            last = int(match.group(2) or first)
            if 1 <= first <= last <= 999:
                normalized_levels[mob] = (
                    first if first == last else f"{first}-{last}"
                )
        mob_levels = normalized_levels
        if (
            not subsession_id
            or not session_id
            or not name
            or started_ns <= 0
            or not 0 <= duration_minutes <= 1440
        ):
            raise ValueError("subsessão inválida")
        with self.conn:
            owner_column = "client_key" if client_key else "character_uid"
            owner = client_key if client_key else character_uid
            active = self.conn.execute(
                f"""SELECT 1 FROM subsessions WHERE session_id=?
                   AND {owner_column} IS ? AND ended_ns IS NULL""",
                (session_id, owner),
            ).fetchone()
            if active:
                raise ValueError("já existe uma subsessão ativa")
            sequence = int(
                self.conn.execute(
                    """SELECT value+1 FROM store_state
                       WHERE key='subsession_sequence'"""
                ).fetchone()[0]
            )
            self.conn.execute(
                """UPDATE store_state SET value=?
                   WHERE key='subsession_sequence'""",
                (sequence,),
            )
            self.conn.execute(
                """INSERT INTO subsessions
                   (id,session_id,character_uid,client_key,name,location,map_name,
                     spot_name,mobs_json,mob_levels_json,duration_minutes,
                     started_ns,sequence)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    subsession_id,
                    session_id,
                    character_uid,
                    client_key,
                    name,
                    location,
                    map_name,
                    spot_name,
                    json.dumps(mobs, ensure_ascii=False),
                    json.dumps(mob_levels, ensure_ascii=False, sort_keys=True),
                    duration_minutes,
                    started_ns,
                    sequence,
                ),
            )

    def end_subsession(self, subsession_id: str, ended_ns: int) -> None:
        with self.conn:
            row = self.conn.execute(
                "SELECT started_ns,ended_ns FROM subsessions WHERE id=?",
                (subsession_id,),
            ).fetchone()
            if not row:
                raise ValueError("subsessão não encontrada")
            if row[1] is not None:
                return
            if ended_ns <= row[0]:
                raise ValueError("fim da subsessão inválido")
            self.conn.execute(
                "UPDATE subsessions SET ended_ns=? WHERE id=?",
                (ended_ns, subsession_id),
            )

    def rename_subsession(self, subsession_id: str, name: str) -> None:
        name = name.strip()
        if not subsession_id or not name:
            raise ValueError("informe um nome para a subsessão")
        with self.conn:
            if not self.conn.execute(
                "UPDATE subsessions SET name=? WHERE id=?",
                (name, subsession_id),
            ).rowcount:
                raise ValueError("subsessão não encontrada")

    def update_subsession(
        self,
        subsession_id: str,
        *,
        name: str,
        character_uid: str | None,
        client_key: str,
        location: str,
        map_name: str,
        spot_name: str,
        mobs: list[str],
        mob_levels: dict[str, int | str],
        duration_minutes: int,
    ) -> None:
        name = name.strip()
        client_key = client_key.strip().casefold()
        if (
            not subsession_id
            or not name
            or client_key not in {"client:a", "client:b"}
            or not 0 <= duration_minutes <= 1440
        ):
            raise ValueError("subsessão inválida")
        with self.conn:
            if not self.conn.execute(
                """UPDATE subsessions SET character_uid=?,client_key=?,name=?,
                   location=?,map_name=?,spot_name=?,mobs_json=?,
                   mob_levels_json=?,duration_minutes=?,upload_state='pending',
                   uploaded_at=NULL WHERE id=?""",
                (
                    character_uid,
                    client_key,
                    name,
                    location.strip(),
                    map_name.strip(),
                    spot_name.strip(),
                    json.dumps(mobs, ensure_ascii=False),
                    json.dumps(mob_levels, ensure_ascii=False, sort_keys=True),
                    duration_minutes,
                    subsession_id,
                ),
            ).rowcount:
                raise ValueError("subsessão não encontrada")

    def delete_subsessions(self, subsession_ids: Iterable[str]) -> int:
        identifiers = tuple(dict.fromkeys(value for value in subsession_ids if value))
        if not identifiers:
            return 0
        placeholders = ",".join("?" for _ in identifiers)
        with self.conn:
            return self.conn.execute(
                f"DELETE FROM subsessions WHERE id IN ({placeholders})",
                identifiers,
            ).rowcount

    def subsessions(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """SELECT id,character_uid,client_key,name,location,map_name,spot_name,
                      mobs_json,mob_levels_json,duration_minutes,started_ns,
                      ended_ns,sequence,upload_state,uploaded_at
               FROM subsessions WHERE session_id=? ORDER BY started_ns DESC""",
            (session_id,),
        )
        return [
            {
                "id": identifier,
                "character_uid": character_uid,
                "client_key": client_key,
                "name": name,
                "location": location,
                "map_name": map_name,
                "spot_name": spot_name,
                "mobs": json.loads(mobs),
                "mob_levels": json.loads(mob_levels),
                "duration_minutes": duration_minutes,
                "started_ns": started_ns,
                "ended_ns": ended_ns,
                "sequence": sequence,
                "upload_state": upload_state,
                "uploaded_at": uploaded_at,
            }
            for (
                identifier,
                character_uid,
                client_key,
                name,
                location,
                map_name,
                spot_name,
                mobs,
                mob_levels,
                duration_minutes,
                started_ns,
                ended_ns,
                sequence,
                upload_state,
                uploaded_at,
            ) in rows
        ]

    def set_subsession_upload_state(
        self, subsession_id: str, state: str
    ) -> None:
        if state not in {"pending", "sent", "failed"}:
            raise ValueError("estado de envio inválido")
        uploaded_at = (
            datetime.now(timezone.utc).isoformat() if state == "sent" else None
        )
        with self.conn:
            self.conn.execute(
                """UPDATE subsessions SET upload_state=?,uploaded_at=?
                   WHERE id=?""",
                (state, uploaded_at, subsession_id),
            )

    def max_event_id(self, session_id: str) -> int:
        return int(
            self.conn.execute(
                "SELECT COALESCE(MAX(id),0) FROM events WHERE session_id=?",
                (session_id,),
            ).fetchone()[0]
        )

    def collection_type_counts(self, session_id: str) -> dict[int, int]:
        counts: dict[int, int] = {}
        for (raw,) in self.conn.execute(
            """SELECT data_json FROM events
               WHERE session_id=? AND type IN (
                   'collection_snapshot_chunk','collection_add_request',
                   'collection_add_response'
               )""",
            (session_id,),
        ):
            try:
                kind = int(json.loads(raw).get("collection_type") or 0)
            except (TypeError, ValueError):
                continue
            if kind:
                counts[kind] = counts.get(kind, 0) + 1
        return counts

    def latest_collection_envelope(self, character_uid: str) -> dict[str, Any]:
        """Último snapshot completo do personagem mais deltas posteriores."""
        sessions = [
            row[0]
            for row in self.conn.execute(
                """SELECT bindings.session_id
                   FROM client_bindings AS bindings
                   LEFT JOIN captures ON captures.session_id=bindings.session_id
                   WHERE bindings.character_uid=?
                   GROUP BY bindings.session_id
                   ORDER BY COALESCE(MAX(captures.mtime_ns),0) DESC""",
                (str(character_uid),),
            )
        ]
        snapshots: dict[int, list[tuple[int, dict[str, Any]]]] = {}
        deltas: dict[int, list[tuple[int, dict[str, Any]]]] = {1: [], 2: []}
        for session_id in sessions:
            pending: dict[int, tuple[str, list[tuple[int, dict[str, Any]]]]] = {}
            rows = self.conn.execute(
                """SELECT id,source,ts_ns,opcode,type,character_uid,data_json
                   FROM events WHERE session_id=? AND character_uid=?
                   AND type IN ('collection_snapshot_chunk','collection_add_response')
                   ORDER BY id DESC""",
                (session_id, str(character_uid)),
            )
            for event_id, source, ts_ns, opcode, kind, uid, raw in rows:
                data = json.loads(raw)
                collection_type = int(data.get("collection_type") or 0)
                if collection_type not in (1, 2) or collection_type in snapshots:
                    continue
                event = {
                    "ts_ns": ts_ns,
                    "opcode": f"0x{opcode:04x}",
                    "type": kind,
                    "character_uid": uid,
                    "data": data,
                }
                if kind == "collection_add_response":
                    deltas[collection_type].append((event_id, event))
                    continue
                current = pending.get(collection_type)
                if current is None:
                    if data.get("is_end") is True:
                        pending[collection_type] = (source, [(event_id, event)])
                    continue
                if source != current[0] or data.get("is_end") is True:
                    snapshots[collection_type] = list(reversed(current[1]))
                    pending.pop(collection_type)
                else:
                    current[1].append((event_id, event))
            for collection_type, (_source, events) in pending.items():
                snapshots.setdefault(collection_type, list(reversed(events)))
            if len(snapshots) == 2:
                break

        selected: list[tuple[int, dict[str, Any]]] = []
        counts: dict[int, int] = {}
        for collection_type, events in snapshots.items():
            baseline_id = events[-1][0]
            current = events + [
                item for item in deltas[collection_type] if item[0] > baseline_id
            ]
            selected.extend(current)
            counts[collection_type] = len(current)
        return {
            "events": [event for _event_id, event in sorted(selected)],
            "collection_type_counts": counts,
        }

    def session_stats_after(self, session_id: str, after_id: int) -> dict[str, int | None]:
        recognized, unknown, unassigned, started, ended, last_id = self.conn.execute(
            """SELECT SUM(type!='unparsed'),SUM(type='unparsed'),
                      SUM(type!='unparsed' AND character_uid IS NULL),
                      MIN(ts_ns),MAX(ts_ns),MAX(id)
               FROM events WHERE session_id=? AND id>?""",
            (session_id, after_id),
        ).fetchone()
        raw_bytes = self.conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM captures WHERE session_id=?",
            (session_id,),
        ).fetchone()[0]
        return {
            "recognized": int(recognized or 0),
            "unknown": int(unknown or 0),
            "unassigned": int(unassigned or 0),
            "started_ns": started,
            "ended_ns": ended,
            "last_id": int(last_id or after_id),
            "raw_bytes": int(raw_bytes or 0),
        }

    def ui_event_batch(
        self,
        session_id: str,
        character_uid: str | None,
        *,
        after_id: int = 0,
        include_unassigned: bool = False,
        only_unassigned: bool = False,
        started_ns: int | None = None,
        ended_ns: int | None = None,
        limit: int = 5000,
    ) -> tuple[list[dict[str, Any]], int]:
        where = ["session_id=?", "type!='unparsed'", "id>?"]
        values: list[Any] = [session_id, after_id]
        if only_unassigned:
            where.append("character_uid IS NULL")
        elif character_uid is not None:
            where.append(
                "(character_uid=? OR character_uid IS NULL)"
                if include_unassigned
                else "character_uid=?"
            )
            values.append(character_uid)
        if started_ns is not None:
            where.append("ts_ns>=?")
            values.append(started_ns)
        if ended_ns is not None:
            where.append("ts_ns<?")
            values.append(ended_ns)
        values.append(max(1, min(50000, int(limit))))
        rows = self.conn.execute(
            f"""SELECT id,ts_ns,opcode,type,character_uid,data_json FROM events
                WHERE {' AND '.join(where)} ORDER BY id LIMIT ?""",
            values,
        ).fetchall()
        return (
            [
                {
                    "ts_ns": ts_ns,
                    "opcode": f"0x{opcode:04x}",
                    "type": kind,
                    "character_uid": uid,
                    "data": _add_exp_percent(json.loads(data)),
                }
                for _id, ts_ns, opcode, kind, uid, data in rows
            ],
            max((int(row[0]) for row in rows), default=after_id),
        )

    def combat_events(
        self,
        session_id: str,
        character_uid: str,
        *,
        recent_seconds: int = 60,
    ) -> list[dict[str, Any]]:
        """Eventos confirmados e recentes para os monitores PvE/PvP."""
        kinds = (
            "appear_player_list",
            "appear_monster_list",
            "restore_hp_fp",
            "dying_unit",
            "select_target_request",
            "use_skill_request",
            "use_skill_result",
            "use_normal_skill_result",
        )
        placeholders = ",".join("?" for _ in kinds)
        # ponytail: 20 mil eventos cobrem muito mais que a janela observada de
        # 60 s; criar um índice dedicado se o tráfego real ultrapassar esse teto.
        rows = self.conn.execute(
            f"""SELECT id,ts_ns,type,data_json FROM events
                INDEXED BY idx_events_session
                WHERE session_id=? AND character_uid=?
                AND type IN ({placeholders})
                ORDER BY id DESC LIMIT 20000""",
            (session_id, character_uid, *kinds),
        ).fetchall()
        if not rows:
            return []
        cutoff = int(rows[0][1] or 0) - max(10, int(recent_seconds)) * 1_000_000_000
        recent = [row for row in rows if int(row[1] or 0) >= cutoff]
        appearances = [
            row for row in rows
            if row[2] in {"appear_player_list", "appear_monster_list"}
        ]

        def contains_local(row: tuple[Any, ...]) -> bool:
            try:
                return any(
                    str(unit.get("character_uid")) == str(character_uid)
                    for unit in (json.loads(row[3]).get("units") or [])
                )
            except (TypeError, ValueError):
                return False

        identity = next(
            (
                row for row in rows
                if row[2] == "appear_player_list" and contains_local(row)
            ),
            None,
        )
        unique = {
            int(row[0]): row
            for row in (*([identity] if identity else []), *appearances, *recent)
        }
        return [
            {
                "ts_ns": ts_ns,
                "type": kind,
                "data": json.loads(data),
            }
            for _id, ts_ns, kind, data in sorted(unique.values(), key=lambda row: row[0])
        ]

    def session_envelope(
        self,
        session_id: str,
        character_uid: str | None = None,
        include_unassigned: bool = False,
        only_unassigned: bool = False,
    ) -> dict[str, Any]:
        return self._envelope(
            session_id,
            session_id,
            character_uid,
            include_unassigned,
            only_unassigned,
        )

    def interval_envelope(
        self,
        session_id: str,
        character_uid: str | None,
        started_ns: int,
        ended_ns: int,
    ) -> dict[str, Any]:
        return self._envelope(
            session_id,
            session_id,
            character_uid,
            False,
            False,
            started_ns,
            ended_ns,
        )

    def _envelope(
        self,
        capture_id: str,
        session_id: str,
        character_uid: str | None = None,
        include_unassigned: bool = False,
        only_unassigned: bool = False,
        started_ns: int | None = None,
        ended_ns: int | None = None,
    ) -> dict[str, Any]:
        where = ["session_id=?", "type!='unparsed'"]
        values: list[Any] = [session_id]
        if only_unassigned:
            where.append("character_uid IS NULL")
        elif character_uid is not None:
            where.append(
                "(character_uid=? OR character_uid IS NULL)"
                if include_unassigned
                else "character_uid=?"
            )
            values.append(character_uid)
        if started_ns is not None:
            where.append("ts_ns>=?")
            values.append(started_ns)
        if ended_ns is not None:
            where.append("ts_ns<?")
            values.append(ended_ns)
        rows = self.conn.execute(
            f"""SELECT ts_ns,opcode,type,character_uid,data_json FROM events
                WHERE {' AND '.join(where)}
                ORDER BY COALESCE(ts_ns,0),id""",
            values,
        ).fetchall()
        events = [
            {
                "ts_ns": ts_ns,
                "opcode": f"0x{opcode:04x}",
                "type": kind,
                "character_uid": uid,
                "data": _add_exp_percent(json.loads(data)),
            }
            for ts_ns, opcode, kind, uid, data in rows
        ]
        kills = sum(event["type"] == "drop_item_field" for event in events)
        raw_bytes = self.conn.execute(
            "SELECT COALESCE(SUM(size),0) FROM captures WHERE session_id=?",
            (session_id,),
        ).fetchone()[0]
        return {
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id,
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "session_id": session_id,
                "installation_id": None,
                "license_lease": None,
                "raw_bytes": raw_bytes,
                "privacy": "sem payload 0x0101, token ou ticket de sessão",
                "capture_windows": self.capture_windows(session_id),
                "subsessions": self.subsessions(session_id),
            },
            "summary": {
                "recognized_events": len(events),
                "kills_estimated_by_reward": kills,
                "kills_semantics": (
                    "proxy: quantidade de eventos de recompensa 0x040A; "
                    "não é kill confirmada"
                ),
            },
            "events": events,
        }

    def export(
        self,
        target_dir: Path,
        capture_id: str,
        *,
        session_id: str = "legacy",
        character_uid: str | None = None,
        include_unassigned: bool = False,
        only_unassigned: bool = False,
        context: dict[str, Any] | None = None,
    ) -> ExportResult:
        if not capture_id or len(capture_id) > 128:
            raise ValueError("capture_id inválido")
        envelope = self._envelope(
            capture_id,
            session_id,
            character_uid,
            include_unassigned,
            only_unassigned,
        )
        if context:
            envelope["metadata"].update(_sanitize(context))
        payload = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        if len(payload) > MAX_EXPORT_BYTES:
            raise ValueError("exportação excede o limite de 512 MiB")
        if envelope["schema_version"] != SCHEMA_VERSION or not isinstance(
            envelope["events"], list
        ):
            raise ValueError("envelope de exportação inválido")
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        json_path = target_dir / f"{capture_id}.json"
        csv_path = target_dir / f"{capture_id}.csv"
        temporary = json_path.with_suffix(".json.tmp")
        temporary.write_bytes(payload)
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, json_path)
        with csv_path.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.DictWriter(
                output,
                fieldnames=(
                    "profile",
                    "character_name",
                    "identification_status",
                    "requires_site_review",
                    "installation_id",
                    "license_lease",
                    "codex_marks",
                    "capture_windows",
                    "subsessions",
                    "session_id",
                    "ts_ns",
                    "character_uid",
                    "type",
                    "level",
                    "exp",
                    "gain_exp",
                    "gain_credit",
                    "contribution_total",
                    "exp_percent",
                    "loot",
                    "confidence",
                ),
            )
            writer.writeheader()
            for index, event in enumerate(envelope["events"] or [None]):
                data = event["data"] if event else {}
                fields = data.get("fields") or data
                writer.writerow(
                    {
                        "profile": envelope["metadata"].get("profile"),
                        "character_name": envelope["metadata"].get(
                            "character_name"
                        ),
                        "identification_status": envelope["metadata"].get(
                            "identification_status"
                        ),
                        "requires_site_review": envelope["metadata"].get(
                            "requires_site_review", False
                        ),
                        "installation_id": (
                            envelope["metadata"].get("installation_id")
                            if index == 0
                            else None
                        ),
                        "license_lease": (
                            envelope["metadata"].get("license_lease")
                            if index == 0
                            else None
                        ),
                        "codex_marks": (
                            json.dumps(
                                envelope["metadata"].get("codex_marks") or {},
                                separators=(",", ":"),
                            )
                            if index == 0
                            else None
                        ),
                        "capture_windows": (
                            json.dumps(
                                envelope["metadata"].get("capture_windows") or [],
                                separators=(",", ":"),
                            )
                            if index == 0
                            else None
                        ),
                        "subsessions": (
                            json.dumps(
                                envelope["metadata"].get("subsessions") or [],
                                ensure_ascii=False,
                                separators=(",", ":"),
                            )
                            if index == 0
                            else None
                        ),
                        "session_id": session_id,
                        "ts_ns": event["ts_ns"] if event else None,
                        "character_uid": (
                            event["character_uid"] if event else character_uid
                        ),
                        "type": event["type"] if event else None,
                        "level": fields.get("level"),
                        "exp": fields.get("exp"),
                        "gain_exp": fields.get("gain_exp"),
                        "gain_credit": (
                            fields.get("gain_credit")
                            or fields.get("credit_gain")
                            or fields.get("credits")
                        ),
                        "contribution_total": fields.get(
                            "contribution_total"
                        ),
                        "exp_percent": fields.get("exp_percent"),
                        "loot": json.dumps(
                            data.get("results") or [],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        "confidence": data.get("confidence"),
                    }
                )
        return ExportResult(
            json_path,
            csv_path,
            json_path.stat().st_size,
            csv_path.stat().st_size,
            hashlib.sha256(payload).hexdigest(),
            envelope["metadata"]["raw_bytes"],
        )

    def export_diagnostics(
        self,
        target_dir: Path,
        capture_id: str,
        session_id: str,
        logs: list[str] | None = None,
    ) -> Path | None:
        rows = self.conn.execute(
            """SELECT ts_ns,opcode,data_json FROM events
               WHERE session_id=? AND type='unparsed'
               ORDER BY COALESCE(ts_ns,0),id""",
            (session_id,),
        ).fetchall()
        logs = logs or []
        if not rows and not logs:
            return None
        payload = {
            "schema_version": 2,
            "session_ref": hashlib.sha256(session_id.encode()).hexdigest()[:16],
            "privacy": (
                "sem payload, IP, flow, personagem, UID, licença, chave, "
                "token ou ticket"
            ),
            "events": [
                {
                    "ts_ns": ts_ns,
                    "opcode": f"0x{opcode:04x}",
                    "details": json.loads(data),
                }
                for ts_ns, opcode, data in rows
            ],
            "logs": logs,
        }
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{capture_id}-nao-decodificados.json"
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
        return path
