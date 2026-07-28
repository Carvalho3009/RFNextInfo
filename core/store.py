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

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS events(
 id INTEGER PRIMARY KEY, source TEXT NOT NULL, flow TEXT NOT NULL,
 stream_offset INTEGER NOT NULL, bundle_seq INTEGER NOT NULL,
 ts_ns INTEGER, opcode INTEGER NOT NULL, type TEXT NOT NULL,
 character_uid TEXT, data_json TEXT NOT NULL,
 UNIQUE(source, flow, stream_offset, bundle_seq)
);
CREATE TABLE IF NOT EXISTS captures(
 source TEXT PRIMARY KEY, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
 imported_at TEXT NOT NULL, events_added INTEGER NOT NULL
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


class CaptureStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def add_events(self, source: Path, events: Iterable[dict[str, Any]]) -> int:
        source = Path(source)
        stat = source.stat()
        existing = self.conn.execute(
            "SELECT size, mtime_ns FROM captures WHERE source=?", (str(source),)
        ).fetchone()
        if existing == (stat.st_size, stat.st_mtime_ns):
            return 0
        added = 0
        with self.conn:
            for event in events:
                if event.get("opcode") == SENSITIVE_OPCODE:
                    continue
                clean = _sanitize(event["data"])
                cursor = self.conn.execute(
                    """INSERT OR IGNORE INTO events
                    (source,flow,stream_offset,bundle_seq,ts_ns,opcode,type,character_uid,data_json)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        str(source), event["flow"], event["stream_offset"], event["bundle_seq"],
                        event.get("ts_ns"), event["opcode"], event["type"],
                        _character_uid({**event, "data": clean}),
                        json.dumps(clean, ensure_ascii=False, sort_keys=True),
                    ),
                )
                added += cursor.rowcount
            self.conn.execute(
                """INSERT INTO captures(source,size,mtime_ns,imported_at,events_added)
                VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET
                size=excluded.size,mtime_ns=excluded.mtime_ns,
                imported_at=excluded.imported_at,events_added=excluded.events_added""",
                (str(source), stat.st_size, stat.st_mtime_ns, datetime.now(timezone.utc).isoformat(), added),
            )
        return added

    def ingest(self, source: Path, *, decoder_path: Path | None = None) -> int:
        return self.add_events(source, decoded_events(source, decoder_path=decoder_path))

    def _envelope(self, capture_id: str) -> dict[str, Any]:
        rows = self.conn.execute(
            "SELECT ts_ns,opcode,type,character_uid,data_json FROM events ORDER BY COALESCE(ts_ns,0),id"
        ).fetchall()
        events = [
            {
                "ts_ns": ts_ns, "opcode": f"0x{opcode:04x}", "type": kind,
                "character_uid": uid, "data": json.loads(data),
            }
            for ts_ns, opcode, kind, uid, data in rows
        ]
        kills = sum(event["type"] == "drop_item_field" for event in events)
        raw_bytes = self.conn.execute("SELECT COALESCE(SUM(size),0) FROM captures").fetchone()[0]
        return {
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id,
            "metadata": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "installation_id": None,
                "license_lease": None,
                "raw_bytes": raw_bytes,
                "privacy": "sem payload 0x0101, token ou ticket de sessão",
            },
            "summary": {
                "recognized_events": len(events),
                "kills_estimated_by_reward": kills,
                "kills_semantics": "proxy: quantidade de eventos de recompensa 0x040A; não é kill confirmada",
            },
            "events": events,
        }

    def export(self, target_dir: Path, capture_id: str) -> ExportResult:
        if not capture_id or len(capture_id) > 128:
            raise ValueError("capture_id inválido")
        envelope = self._envelope(capture_id)
        payload = json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")
        if len(payload) > MAX_EXPORT_BYTES:
            raise ValueError("exportação excede o limite de 512 MiB")
        if envelope["schema_version"] != 1 or not isinstance(envelope["events"], list):
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
                fieldnames=("ts_ns", "character_uid", "type", "level", "exp", "gain_exp", "confidence"),
            )
            writer.writeheader()
            for event in envelope["events"]:
                data = event["data"]
                fields = data.get("fields") or data
                writer.writerow({
                    "ts_ns": event["ts_ns"], "character_uid": event["character_uid"],
                    "type": event["type"], "level": fields.get("level"),
                    "exp": fields.get("exp"), "gain_exp": fields.get("gain_exp"),
                    "confidence": data.get("confidence"),
                })
        return ExportResult(
            json_path, csv_path, json_path.stat().st_size, csv_path.stat().st_size,
            hashlib.sha256(payload).hexdigest(), envelope["metadata"]["raw_bytes"],
        )
