"""SQLite incremental e exportação sanitizada, sem rede."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .ingest import SENSITIVE_OPCODE, decoded_events

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
 session_id TEXT NOT NULL DEFAULT 'legacy'
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


def _character_uid(event: dict[str, Any]) -> str | None:
    fields = event["data"].get("fields") or {}
    uid = fields.get("character_uid")
    return str(uid) if uid is not None else None


def _add_exp_percent(data: dict[str, Any]) -> dict[str, Any]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
    level, exp = fields.get("level"), fields.get("exp")
    if isinstance(level, int) and isinstance(exp, (int, float)):
        start, end = LEVEL_CURVE.get(level), LEVEL_CURVE.get(level + 1)
        if start is not None and end is not None and end > start:
            fields["exp_percent"] = round(
                max(0.0, min(100.0, (float(exp) - start) * 100 / (end - start))),
                2,
            )
    return data


class CaptureStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
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
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_session "
                "ON events(session_id, character_uid, id)"
            )
            self.conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_captures_session "
                "ON captures(session_id, imported_at)"
            )

    def close(self) -> None:
        self.conn.close()

    def add_events(
        self,
        source: Path,
        events: Iterable[dict[str, Any]],
        session_id: str = "legacy",
    ) -> int:
        if not session_id or len(session_id) > 128:
            raise ValueError("session_id inválido")
        source = Path(source)
        stat = source.stat()
        existing = self.conn.execute(
            "SELECT size, mtime_ns, session_id FROM captures WHERE source=?",
            (str(source),),
        ).fetchone()
        if existing == (stat.st_size, stat.st_mtime_ns, session_id):
            return 0

        prepared: list[tuple[dict[str, Any], dict[str, Any], str | None]] = []
        flow_uids: dict[str, set[str]] = {}
        for event in events:
            if event.get("opcode") == SENSITIVE_OPCODE:
                continue
            clean = _sanitize(event["data"])
            uid = _character_uid({**event, "data": clean})
            if uid:
                flow_uids.setdefault(event["flow"], set()).add(uid)
            prepared.append((event, clean, uid))
        stable_flow_uid = {
            flow: next(iter(uids))
            for flow, uids in flow_uids.items()
            if len(uids) == 1
        }

        added = 0
        with self.conn:
            for event, clean, uid in prepared:
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
                        uid or stable_flow_uid.get(event["flow"]),
                        json.dumps(clean, ensure_ascii=False, sort_keys=True),
                        session_id,
                    ),
                )
                added += cursor.rowcount
            self.conn.execute(
                """INSERT INTO captures
                (source,size,mtime_ns,imported_at,events_added,session_id)
                VALUES(?,?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET
                size=excluded.size,mtime_ns=excluded.mtime_ns,
                imported_at=excluded.imported_at,
                events_added=excluded.events_added,
                session_id=excluded.session_id""",
                (
                    str(source),
                    stat.st_size,
                    stat.st_mtime_ns,
                    datetime.now(timezone.utc).isoformat(),
                    added,
                    session_id,
                ),
            )
        return added

    def ingest(
        self,
        source: Path,
        *,
        session_id: str = "legacy",
        decoder_path: Path | None = None,
    ) -> int:
        return self.add_events(
            source,
            decoded_events(source, decoder_path=decoder_path),
            session_id,
        )

    def clear_exported(self, session_id: str | None = None) -> None:
        with self.conn:
            if session_id is None:
                self.conn.execute("DELETE FROM events")
                self.conn.execute("DELETE FROM captures")
            else:
                self.conn.execute(
                    "DELETE FROM events WHERE session_id=?", (session_id,)
                )
                self.conn.execute(
                    "DELETE FROM captures WHERE session_id=?", (session_id,)
                )

    def latest_session(self) -> str | None:
        row = self.conn.execute(
            "SELECT session_id FROM captures ORDER BY imported_at DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else None

    def session_profiles(self, session_id: str) -> list[dict[str, str]]:
        rows = self.conn.execute(
            """SELECT character_uid,data_json FROM events
               WHERE session_id=? AND character_uid IS NOT NULL
               AND type!='unparsed' ORDER BY id""",
            (session_id,),
        ).fetchall()
        profiles: dict[str, str] = {}
        for uid, raw in rows:
            data = json.loads(raw)
            fields = data.get("fields") if isinstance(data.get("fields"), dict) else data
            name = str(
                fields.get("character_name") or fields.get("character") or ""
            ).strip()
            profiles.setdefault(uid, name)
            if name:
                profiles[uid] = name
        return [{"uid": uid, "name": name} for uid, name in profiles.items()]

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

    def session_envelope(
        self,
        session_id: str,
        character_uid: str | None = None,
        include_unassigned: bool = False,
    ) -> dict[str, Any]:
        return self._envelope(
            session_id,
            session_id,
            character_uid,
            include_unassigned,
        )

    def _envelope(
        self,
        capture_id: str,
        session_id: str,
        character_uid: str | None = None,
        include_unassigned: bool = False,
    ) -> dict[str, Any]:
        where = ["session_id=?", "type!='unparsed'"]
        values: list[Any] = [session_id]
        if character_uid is not None:
            where.append(
                "(character_uid=? OR character_uid IS NULL)"
                if include_unassigned
                else "character_uid=?"
            )
            values.append(character_uid)
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
        context: dict[str, Any] | None = None,
    ) -> ExportResult:
        if not capture_id or len(capture_id) > 128:
            raise ValueError("capture_id inválido")
        envelope = self._envelope(
            capture_id, session_id, character_uid, include_unassigned
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
                    "session_id",
                    "ts_ns",
                    "character_uid",
                    "type",
                    "level",
                    "exp",
                    "gain_exp",
                    "exp_percent",
                    "confidence",
                ),
            )
            writer.writeheader()
            for event in envelope["events"]:
                data = event["data"]
                fields = data.get("fields") or data
                writer.writerow(
                    {
                        "profile": envelope["metadata"].get("profile"),
                        "character_name": envelope["metadata"].get(
                            "character_name"
                        ),
                        "session_id": session_id,
                        "ts_ns": event["ts_ns"],
                        "character_uid": event["character_uid"],
                        "type": event["type"],
                        "level": fields.get("level"),
                        "exp": fields.get("exp"),
                        "gain_exp": fields.get("gain_exp"),
                        "exp_percent": fields.get("exp_percent"),
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
    ) -> Path | None:
        rows = self.conn.execute(
            """SELECT ts_ns,opcode,data_json FROM events
               WHERE session_id=? AND type='unparsed'
               ORDER BY COALESCE(ts_ns,0),id""",
            (session_id,),
        ).fetchall()
        if not rows:
            return None
        payload = {
            "schema_version": 1,
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
