"""Base local do Agent Windows para a futura arquitetura web.

Este modulo nao transmite dados. Ele transforma eventos ja decodificados em um
contrato de lista positiva e os grava em uma outbox SQLite separada e limitada.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import queue
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


DECODED_EVENT_SCHEMA = "rf-qol.decoded-event/v1"
INGEST_BATCH_SCHEMA = "rf-qol.ingest-batch/v1"
SENSITIVE_OPCODE = 0x0101
DEFAULT_OUTBOX_BYTES = 512 * 1024 * 1024
DEFAULT_OUTBOX_EVENTS = 2_000_000
MAX_EVENT_BYTES = 64 * 1024
MAX_BATCH_EVENTS = 250
MAX_BATCH_BYTES = 256 * 1024
MAX_REJECTION_RECORDS = 1000

EVENT_TYPES = {
    "world_info_prefix": "character.observed",
    "update_exp": "character.exp_changed",
    "realm_contribution_update": "character.contribution_changed",
    "drop_item_field": "character.drop_received",
    "loot_announcement": "world.drop_announced",
    "appear_player_list": "world.players_appeared",
    "appear_monster_list": "world.monsters_appeared",
    "disappear_unit_list": "world.entities_disappeared",
    "dying_unit": "combat.entity_died",
    "restore_hp_fp": "combat.resources_changed",
    "use_skill_result": "combat.skill_resolved",
    "use_normal_skill_result": "combat.normal_attack_resolved",
    "move_player_request": "map.character_moved",
    "move_player_update": "map.entity_moved",
    "request_teleport": "map.teleport_requested",
    "request_teleport_result": "map.teleport_resolved",
    "teleport_request": "map.teleport_requested",
    "teleport_response": "map.teleport_resolved",
    "warp_player": "map.entity_warped",
    "end_warp_player": "map.teleport_finished",
    "FG2C_ans_boss_position_Message": "boss.position_observed",
    "FG2C_notify_boss_result_Message": "boss.result_observed",
}

SESSION_STATES = {"started", "resumed", "paused", "finished", "abandoned"}

_PAYLOAD_FIELDS = {
    "character.observed": {
        "character_uid", "name", "level", "biosuit_item_index",
    },
    "character.exp_changed": {
        "action_code", "before_level", "level", "highest_level", "total_exp",
        "gained_exp",
    },
    "character.contribution_changed": {"contribution_total"},
    "character.drop_received": {"result", "items"},
    "world.drop_announced": {"announcements"},
    "world.players_appeared": {"entities"},
    "world.monsters_appeared": {"entities"},
    "world.entities_disappeared": {"entity_refs"},
    "combat.entity_died": {"entity_ref", "killer_ref", "reason"},
    "combat.resources_changed": {
        "entity_ref", "current_hp", "max_hp", "current_fp", "max_fp",
    },
    "combat.skill_resolved": {
        "result", "caster_ref", "target_ref", "skill_index", "caster_final_hp",
        "effects",
    },
    "combat.normal_attack_resolved": {
        "result", "caster_ref", "target_ref", "skill_index", "caster_final_hp",
        "effects",
    },
    "map.character_moved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.entity_moved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_requested": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_resolved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.entity_warped": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_finished": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "boss.position_observed": {"boss_ref", "npc_index", "position", "result"},
    "boss.result_observed": {"boss_ref", "npc_index", "position", "result"},
    "session.lifecycle": {"state", "reason"},
}
_NESTED_FIELDS = {
    "items": {"result", "item_index", "count", "gain_total", "action_code"},
    "announcements": {
        "character_uid", "player_ref", "player_name", "item_index", "count",
    },
    "entities": {
        "entity_ref", "position", "current_hp", "max_hp", "character_uid",
        "player_ref", "name", "level", "guild_id", "guild_name",
        "biosuit_item_index", "rover_item_index", "npc_index", "realm",
    },
    "effects": {"entity_ref", "shield_damage", "hp_damage", "final_hp"},
}

_FORBIDDEN_KEYS = {
    "account_id",
    "flow",
    "item_id",
    "opcode",
    "packet",
    "password",
    "pc_id",
    "port",
    "private_key",
    "secret",
    "source",
    "source_pcap",
    "ticket",
    "token",
    "session_uid",
    "login_uid",
    "auth_uid",
}


class WebEventContractError(ValueError):
    """Evento nao pode atravessar a fronteira local do Agent."""


class OutboxFullError(RuntimeError):
    """A outbox atingiu um limite configurado e preservou os registros atuais."""


def _integer(value: object, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _character_uid(value: object) -> int | None:
    """UID público e permanente do personagem; nunca UID de sessão/login."""
    result = _integer(value)
    return result if result is not None and 0 < result <= 2**64 - 1 else None


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return round(result, 6) if math.isfinite(result) else None


def _text(value: object, limit: int = 96) -> str | None:
    result = str(value or "").strip()
    return result[:limit] if result else None


def _position(value: object) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    result = [_number(item) for item in value[:3]]
    return result if all(item is not None for item in result) else None


def _position_from_fields(fields: dict[str, Any]) -> list[float] | None:
    direct = _position(fields.get("position"))
    if direct is not None:
        return direct
    values = [fields.get(f"position_{axis}") for axis in "xyz"]
    if all(value is not None for value in values):
        return _position(values)
    return None


def _utc_from_ns(value: object) -> str:
    timestamp_ns = max(0, _integer(value, 0) or 0)
    return (
        datetime.fromtimestamp(timestamp_ns / 1_000_000_000, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _connection_key(flow: str) -> str:
    """Une as duas direcoes do mesmo TCP sem expor os endpoints."""
    endpoints = [item.strip() for item in str(flow).split(" -> ", 1)]
    return " <-> ".join(sorted(endpoints)) if len(endpoints) == 2 else str(flow)


def _assert_safe_contract(value: object, *, root: bool = True) -> None:
    if isinstance(value, dict):
        for raw_key, item in value.items():
            key = str(raw_key).strip().lower()
            if (
                key in _FORBIDDEN_KEYS
                or key.endswith("_raw")
                or key.endswith("_hex")
                or (not root and key == "payload")
            ):
                raise WebEventContractError(f"Campo proibido no contrato: {key}")
            _assert_safe_contract(item, root=False)
    elif isinstance(value, list):
        for item in value:
            _assert_safe_contract(item, root=False)
    elif isinstance(value, float) and not math.isfinite(value):
        raise WebEventContractError("Numero nao finito no contrato")


def _validate_event_contract(event: dict[str, Any]) -> None:
    expected_root = {
        "schema", "event_id", "installation_id", "session_ref", "stream_id",
        "occurred_at", "client_ref", "type", "payload", "evidence",
    }
    if set(event) != expected_root:
        raise WebEventContractError("Campos externos ao schema de evento")
    event_type = event.get("type")
    if event_type not in _PAYLOAD_FIELDS:
        raise WebEventContractError("Tipo externo nao aprovado")
    payload = event.get("payload")
    evidence = event.get("evidence")
    if not isinstance(payload, dict) or not isinstance(evidence, dict):
        raise WebEventContractError("Payload ou evidencia invalidos")
    if not set(payload).issubset(_PAYLOAD_FIELDS[str(event_type)]):
        raise WebEventContractError("Campo de payload nao aprovado")
    if event_type == "session.lifecycle" and payload.get("state") not in SESSION_STATES:
        raise WebEventContractError("Estado de sessao nao aprovado")
    if set(evidence) != {"confidence", "decoder_version"}:
        raise WebEventContractError("Campo de evidencia nao aprovado")
    for name, allowed in _NESTED_FIELDS.items():
        rows = payload.get(name)
        if rows is None:
            continue
        if not isinstance(rows, list) or any(
            not isinstance(row, dict) or not set(row).issubset(allowed)
            for row in rows
        ):
            raise WebEventContractError(f"Estrutura de {name} invalida")
    _assert_safe_contract(event)


class WebEventProjector:
    """Projeta somente campos explicitamente aprovados para o futuro servidor."""

    def __init__(
        self,
        installation_id: str,
        pseudonym_key: bytes,
        *,
        decoder_version: str,
    ) -> None:
        self.installation_id = _text(installation_id, 128)
        if not self.installation_id:
            raise ValueError("installation_id obrigatorio")
        if len(pseudonym_key) < 16:
            raise ValueError("pseudonym_key deve ter pelo menos 16 bytes")
        self._key = bytes(pseudonym_key)
        self.decoder_version = _text(decoder_version, 64) or "unknown"
        self._flow_clients: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def _opaque(self, namespace: str, value: object, *, size: int = 32) -> str:
        digest = hmac.new(
            self._key,
            f"{namespace}:{value}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest[:size]

    def _entity_ref(self, session_id: str, value: object) -> str | None:
        uid = _integer(value)
        return self._opaque("entity", f"{session_id}:{uid}") if uid else None

    def _fields(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = data.get("fields")
        return fields if isinstance(fields, dict) else data

    def _identity(
        self, kind: str, session_id: str, flow: str, fields: dict[str, Any]
    ) -> str | None:
        key = (session_id, _connection_key(flow))
        with self._lock:
            if kind == "world_info_prefix":
                uid = _character_uid(fields.get("character_uid"))
                if uid:
                    self._flow_clients.pop(key, None)
                    self._flow_clients[key] = self._opaque("client", uid)
                    while len(self._flow_clients) > 256:
                        self._flow_clients.pop(next(iter(self._flow_clients)))
            return self._flow_clients.get(key)

    def finish_session(self, session_id: str) -> None:
        with self._lock:
            for key in tuple(self._flow_clients):
                if key[0] == session_id:
                    self._flow_clients.pop(key, None)

    def session_ref(self, session_id: str) -> str:
        value = _text(session_id, 160)
        if not value:
            raise WebEventContractError("Sessao obrigatoria")
        return self._opaque("session", value, size=32)

    def project_lifecycle(
        self,
        session_id: str,
        state: str,
        *,
        reason: str | None = None,
        occurred_ns: int | None = None,
    ) -> dict[str, Any]:
        """Cria um evento de controle sem expor o identificador local da sessao."""
        session_id = _text(session_id, 160) or ""
        normalized_state = _text(state, 32) or ""
        if not session_id:
            raise WebEventContractError("Sessao obrigatoria")
        if normalized_state not in SESSION_STATES:
            raise WebEventContractError("Estado de sessao nao aprovado")
        timestamp_ns = max(0, _integer(occurred_ns, time.time_ns()) or 0)
        payload = {"state": normalized_state}
        safe_reason = _text(reason, 96)
        if safe_reason:
            payload["reason"] = safe_reason
        session_ref = self.session_ref(session_id)
        identity = {
            "session": session_id,
            "state": normalized_state,
            "reason": safe_reason,
            "time": timestamp_ns,
        }
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque(
                "event", _canonical_json(identity).hex(), size=48
            ),
            "installation_id": self.installation_id,
            "session_ref": session_ref,
            "stream_id": self._opaque("stream", f"{session_id}:lifecycle", size=32),
            "occurred_at": _utc_from_ns(timestamp_ns),
            "client_ref": None,
            "type": "session.lifecycle",
            "payload": payload,
            "evidence": {
                "confidence": "agent",
                "decoder_version": self.decoder_version,
            },
        }
        _validate_event_contract(result)
        return result

    def _project_units(
        self,
        rows: object,
        session_id: str,
        *,
        players: bool,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            item: dict[str, Any] = {
                "entity_ref": self._entity_ref(session_id, row.get("uid")),
                "position": _position_from_fields(row),
                "current_hp": _integer(row.get("current_hp")),
                "max_hp": _integer(row.get("max_hp")),
            }
            if players:
                item.update({
                    "character_uid": _character_uid(row.get("character_uid")),
                    "player_ref": self._entity_ref(
                        session_id, row.get("character_uid")
                    ),
                    "name": _text(row.get("name") or row.get("character_name")),
                    "level": _integer(row.get("level")),
                    "guild_id": _integer(row.get("guild_id")),
                    "guild_name": _text(row.get("guild_name")),
                    "biosuit_item_index": _integer(row.get("biosuit_item_index")),
                    "rover_item_index": _integer(row.get("rover_item_index")),
                })
            else:
                item.update({
                    "npc_index": _integer(row.get("npc_index")),
                    "realm": _integer(row.get("realm")),
                })
            result.append({key: value for key, value in item.items() if value is not None})
            if len(result) >= 256:
                break
        return result

    def _project_effects(
        self, rows: object, session_id: str
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            item = {
                "entity_ref": self._entity_ref(session_id, row.get("uid")),
                "shield_damage": _integer(row.get("shield_damage")),
                "hp_damage": _integer(row.get("hp_damage")),
                "final_hp": _integer(row.get("final_hp")),
            }
            result.append({key: value for key, value in item.items() if value is not None})
            if len(result) >= 128:
                break
        return result

    def _payload(
        self, kind: str, data: dict[str, Any], session_id: str
    ) -> dict[str, Any]:
        fields = self._fields(data)
        if kind == "world_info_prefix":
            return {
                key: value for key, value in {
                    "character_uid": _character_uid(fields.get("character_uid")),
                    "name": _text(fields.get("character_name")),
                    "level": _integer(fields.get("level")),
                    "biosuit_item_index": _integer(fields.get("biosuit_item_index")),
                }.items() if value is not None
            }
        if kind == "update_exp":
            return {
                key: value for key, value in {
                    "action_code": _integer(data.get("action_code")),
                    "before_level": _integer(data.get("before_level")),
                    "level": _integer(data.get("level")),
                    "highest_level": _integer(data.get("highest_level")),
                    "total_exp": _integer(data.get("exp")),
                    "gained_exp": _integer(data.get("gain_exp")),
                }.items() if value is not None
            }
        if kind == "realm_contribution_update":
            value = data.get("contribution_total", fields.get("contribution_total"))
            return {"contribution_total": _integer(value, 0)}
        if kind == "drop_item_field":
            rows = []
            for row in data.get("results") if isinstance(data.get("results"), list) else []:
                if not isinstance(row, dict):
                    continue
                rows.append({
                    key: value for key, value in {
                        "result": _integer(row.get("ret")),
                        "item_index": _integer(row.get("item_index")),
                        "count": _integer(row.get("count")),
                        "gain_total": _integer(row.get("gain_total")),
                        "action_code": _integer(row.get("action_code")),
                    }.items() if value is not None
                })
                if len(rows) >= 128:
                    break
            return {"result": _integer(data.get("ret"), 0), "items": rows}
        if kind == "loot_announcement":
            rows = []
            for row in data.get("announcements") if isinstance(data.get("announcements"), list) else []:
                if not isinstance(row, dict):
                    continue
                rows.append({
                    key: value for key, value in {
                        "character_uid": _character_uid(
                            row.get("character_uid")
                        ),
                        "player_ref": self._entity_ref(
                            session_id, row.get("character_uid")
                        ),
                        "player_name": _text(row.get("player_name")),
                        "item_index": _integer(row.get("item_index")),
                        "count": _integer(row.get("count")),
                    }.items() if value is not None
                })
                if len(rows) >= 128:
                    break
            return {"announcements": rows}
        if kind in {"appear_player_list", "appear_monster_list"}:
            return {
                "entities": self._project_units(
                    data.get("units"), session_id,
                    players=kind == "appear_player_list",
                )
            }
        if kind == "disappear_unit_list":
            values = fields.get("entity_uids") or data.get("entity_uids") or []
            return {
                "entity_refs": [
                    ref for value in list(values)[:256]
                    if (ref := self._entity_ref(session_id, value))
                ]
            }
        if kind == "dying_unit":
            return {
                key: value for key, value in {
                    "entity_ref": self._entity_ref(session_id, data.get("uid")),
                    "killer_ref": self._entity_ref(session_id, data.get("killer_uid")),
                    "reason": _integer(data.get("reason")),
                }.items() if value is not None
            }
        if kind == "restore_hp_fp":
            return {
                key: value for key, value in {
                    "entity_ref": self._entity_ref(session_id, data.get("uid")),
                    "current_hp": _integer(data.get("current_hp")),
                    "max_hp": _integer(data.get("max_hp")),
                    "current_fp": _integer(data.get("current_fp")),
                    "max_fp": _integer(data.get("max_fp")),
                }.items() if value is not None
            }
        if kind in {"use_skill_result", "use_normal_skill_result"}:
            return {
                key: value for key, value in {
                    "result": _integer(data.get("ret")),
                    "caster_ref": self._entity_ref(session_id, data.get("caster_uid")),
                    "target_ref": self._entity_ref(session_id, data.get("main_target_uid")),
                    "skill_index": _integer(data.get("skill_index")),
                    "caster_final_hp": _integer(data.get("caster_final_hp")),
                    "effects": self._project_effects(data.get("effect_results"), session_id),
                }.items() if value is not None
            }
        if kind in {
            "move_player_request", "move_player_update", "request_teleport",
            "request_teleport_result", "teleport_request", "teleport_response",
            "warp_player", "end_warp_player",
        }:
            return {
                key: value for key, value in {
                    "entity_ref": self._entity_ref(
                        session_id, fields.get("entity_uid") or fields.get("uid")
                    ),
                    "map_index": _integer(
                        fields.get("destination_map_index", fields.get("map_index"))
                    ),
                    "teleport_index": _integer(fields.get("teleport_index")),
                    "server_region_index": _integer(fields.get("server_region_index")),
                    "result": _integer(fields.get("result")),
                    "position": (
                        _position(fields.get("resolved_position"))
                        or _position(fields.get("requested_position"))
                        or _position_from_fields(fields)
                    ),
                }.items() if value is not None
            }
        if kind in {
            "FG2C_ans_boss_position_Message",
            "FG2C_notify_boss_result_Message",
        }:
            return {
                key: value for key, value in {
                    "boss_ref": self._entity_ref(
                        session_id, data.get("uid") or fields.get("entity_uid")
                    ),
                    "npc_index": _integer(data.get("npc_index") or fields.get("npc_index")),
                    "position": _position_from_fields(fields),
                    "result": _integer(data.get("ret") or fields.get("result")),
                }.items() if value is not None
            }
        raise WebEventContractError(f"Tipo nao aprovado: {kind}")

    def project(self, event: dict[str, Any], session_id: str) -> dict[str, Any]:
        if not isinstance(event, dict):
            raise WebEventContractError("Evento interno invalido")
        opcode = _integer(event.get("opcode"))
        if opcode == SENSITIVE_OPCODE:
            raise WebEventContractError("Opcode sensivel nao pode sair do computador")
        kind = _text(event.get("type"), 96) or ""
        public_type = EVENT_TYPES.get(kind)
        if not public_type:
            raise WebEventContractError(f"Tipo nao aprovado: {kind}")
        session_id = _text(session_id, 160) or ""
        if not session_id:
            raise WebEventContractError("Sessao obrigatoria")
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
        flow = str(event.get("flow") or "")
        fields = self._fields(data)
        connection = _connection_key(flow)
        client_ref = self._identity(kind, session_id, flow, fields)
        payload = self._payload(kind, data, session_id)
        identity = {
            "session": session_id,
            "flow": flow,
            "offset": _integer(event.get("stream_offset"), 0),
            "bundle": _integer(event.get("bundle_seq"), 0),
            "time": _integer(event.get("ts_ns"), 0),
            "kind": kind,
            "payload": payload,
        }
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque("event", _canonical_json(identity).hex(), size=48),
            "installation_id": self.installation_id,
            "session_ref": self.session_ref(session_id),
            "stream_id": self._opaque(
                "stream", f"{session_id}:{connection}", size=32
            ),
            "occurred_at": _utc_from_ns(event.get("ts_ns")),
            "client_ref": client_ref,
            "type": public_type,
            "payload": payload,
            "evidence": {
                "confidence": "decoded",
                "decoder_version": self.decoder_version,
            },
        }
        _validate_event_contract(result)
        if len(_canonical_json(result)) > MAX_EVENT_BYTES:
            raise WebEventContractError("Evento excede o limite do contrato")
        return result


class AgentOutbox:
    """Fila duravel, deduplicada e limitada; so remove por ACK confirmado."""

    def __init__(
        self,
        path: Path,
        installation_id: str,
        *,
        max_bytes: int = DEFAULT_OUTBOX_BYTES,
        max_events: int = DEFAULT_OUTBOX_EVENTS,
        max_event_bytes: int = MAX_EVENT_BYTES,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.installation_id = _text(installation_id, 128) or ""
        if not self.installation_id:
            raise ValueError("installation_id obrigatorio")
        self.max_bytes = max(1, int(max_bytes))
        self.max_events = max(1, int(max_events))
        self.max_event_bytes = max(1024, int(max_event_bytes))
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA wal_autocheckpoint=256")
        self.conn.execute("PRAGMA journal_size_limit=16777216")
        self._issued_batches: dict[str, tuple[int, int, tuple[str, ...]]] = {}
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                document BLOB NOT NULL,
                byte_size INTEGER NOT NULL,
                created_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                rejected_ns INTEGER NOT NULL
            );
        """)
        row = self.conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(byte_size), 0) FROM outbox_events"
        ).fetchone()
        self._event_count, self._byte_count = int(row[0]), int(row[1])

    def enqueue(self, event: dict[str, Any]) -> bool:
        _validate_event_contract(event)
        if event.get("schema") != DECODED_EVENT_SCHEMA:
            raise WebEventContractError("Schema de evento invalido")
        if event.get("installation_id") != self.installation_id:
            raise WebEventContractError("Evento pertence a outra instalacao")
        event_id = _text(event.get("event_id"), 128)
        event_type = _text(event.get("type"), 128)
        occurred_at = _text(event.get("occurred_at"), 64)
        if not all((event_id, event_type, occurred_at)):
            raise WebEventContractError("Metadados obrigatorios ausentes")
        document = _canonical_json(event)
        if len(document) > self.max_event_bytes:
            raise WebEventContractError("Evento excede o limite da outbox")
        with self._lock:
            if self.conn.execute(
                "SELECT 1 FROM outbox_events WHERE event_id=?", (event_id,)
            ).fetchone():
                return False
            if (
                self._event_count + 1 > self.max_events
                or self._byte_count + len(document) > self.max_bytes
            ):
                raise OutboxFullError("Outbox cheia; eventos existentes preservados")
            with self.conn:
                self.conn.execute(
                    """INSERT INTO outbox_events
                       (event_id,event_type,occurred_at,document,byte_size,created_ns)
                       VALUES(?,?,?,?,?,?)""",
                    (event_id, event_type, occurred_at, document, len(document), time.time_ns()),
                )
            self._event_count += 1
            self._byte_count += len(document)
            return True

    def _batch_id(self, rows: list[sqlite3.Row]) -> str:
        identity = ",".join(f"{row['sequence']}:{row['event_id']}" for row in rows)
        return hashlib.sha256(
            f"{self.installation_id}:{identity}".encode("utf-8")
        ).hexdigest()

    def next_batch(
        self,
        *,
        max_events: int = MAX_BATCH_EVENTS,
        max_bytes: int = MAX_BATCH_BYTES,
    ) -> dict[str, Any] | None:
        event_limit = max(1, min(MAX_BATCH_EVENTS, int(max_events)))
        byte_limit = max(1024, min(MAX_BATCH_BYTES, int(max_bytes)))
        with self._lock:
            candidates = self.conn.execute(
                "SELECT * FROM outbox_events ORDER BY sequence LIMIT ?",
                (event_limit,),
            ).fetchall()
            rows: list[sqlite3.Row] = []
            size = 0
            for row in candidates:
                if rows and size + int(row["byte_size"]) > byte_limit:
                    break
                rows.append(row)
                size += int(row["byte_size"])
            if not rows:
                return None
            events = []
            for row in rows:
                event = json.loads(bytes(row["document"]).decode("utf-8"))
                event["sequence"] = int(row["sequence"])
                events.append(event)
            batch_id = self._batch_id(rows)
            self._issued_batches[batch_id] = (
                int(rows[0]["sequence"]),
                int(rows[-1]["sequence"]),
                tuple(str(row["event_id"]) for row in rows),
            )
            return {
                "schema": INGEST_BATCH_SCHEMA,
                "batch_id": batch_id,
                "installation_id": self.installation_id,
                "sent_at": _utc_from_ns(time.time_ns()),
                "first_sequence": int(rows[0]["sequence"]),
                "last_sequence": int(rows[-1]["sequence"]),
                "events": events,
            }

    def acknowledge(self, batch_id: str, accepted_through_sequence: int) -> int:
        with self._lock:
            issued = self._issued_batches.get(str(batch_id))
            if issued is None:
                raise WebEventContractError("ACK pertence a um lote nao emitido")
            first_sequence, last_sequence, event_ids = issued
            accepted = int(accepted_through_sequence)
            if not first_sequence <= accepted <= last_sequence:
                raise WebEventContractError("ACK fora dos limites do lote")
            rows = self.conn.execute(
                "SELECT * FROM outbox_events WHERE sequence BETWEEN ? AND ? ORDER BY sequence",
                (first_sequence, accepted),
            ).fetchall()
            expected_ids = event_ids[: accepted - first_sequence + 1]
            if (
                not rows
                or tuple(str(row["event_id"]) for row in rows) != expected_ids
                or self.conn.execute(
                    "SELECT MIN(sequence) FROM outbox_events"
                ).fetchone()[0] != first_sequence
            ):
                raise WebEventContractError("ACK nao corresponde ao inicio atual da outbox")
            released = sum(int(row["byte_size"]) for row in rows)
            with self.conn:
                self.conn.execute(
                    "DELETE FROM outbox_events WHERE sequence BETWEEN ? AND ?",
                    (first_sequence, accepted),
                )
            self._event_count -= len(rows)
            self._byte_count -= released
            self._issued_batches.pop(str(batch_id), None)
            return len(rows)

    def reject(self, event_id: str, reason: str) -> bool:
        safe_reason = _text(reason, 160) or "rejected"
        with self._lock:
            row = self.conn.execute(
                "SELECT byte_size FROM outbox_events WHERE event_id=?", (event_id,)
            ).fetchone()
            if row is None:
                return False
            with self.conn:
                self.conn.execute(
                    "INSERT INTO outbox_rejections(event_id,reason,rejected_ns) VALUES(?,?,?)",
                    (str(event_id), safe_reason, time.time_ns()),
                )
                self.conn.execute(
                    "DELETE FROM outbox_events WHERE event_id=?", (str(event_id),)
                )
                self.conn.execute(
                    """DELETE FROM outbox_rejections
                       WHERE id NOT IN (
                           SELECT id FROM outbox_rejections
                           ORDER BY id DESC LIMIT ?
                       )""",
                    (MAX_REJECTION_RECORDS,),
                )
            self._event_count -= 1
            self._byte_count -= int(row["byte_size"])
            return True

    def metrics(self) -> dict[str, int | bool]:
        with self._lock:
            row = self.conn.execute(
                """SELECT MIN(sequence),MAX(sequence),MIN(created_ns)
                   FROM outbox_events"""
            ).fetchone()
            oldest_ns = int(row[2]) if row[2] is not None else 0
            disk_bytes = sum(
                path.stat().st_size
                for path in (
                    self.path,
                    self.path.with_name(self.path.name + "-wal"),
                    self.path.with_name(self.path.name + "-shm"),
                )
                if path.exists()
            )
            return {
                "events": self._event_count,
                "bytes": self._byte_count,
                "disk_bytes": disk_bytes,
                "event_limit": self.max_events,
                "byte_limit": self.max_bytes,
                "oldest_sequence": int(row[0]) if row[0] is not None else 0,
                "newest_sequence": int(row[1]) if row[1] is not None else 0,
                "oldest_age_seconds": (
                    round(max(0, time.time_ns() - oldest_ns) / 1_000_000_000)
                    if oldest_ns else 0
                ),
                "full": (
                    self._event_count >= self.max_events
                    or self._byte_count >= self.max_bytes
                ),
            }

    def close(self) -> None:
        with self._lock:
            self.conn.close()


class WebAgentBridge:
    """Ponte nao bloqueante entre o decoder em memoria e a outbox local."""

    def __init__(
        self,
        projector: WebEventProjector,
        outbox: AgentOutbox,
        *,
        max_queue_events: int = 2048,
        event_observer: Callable[[dict[str, Any]], object] | None = None,
    ) -> None:
        if projector.installation_id != outbox.installation_id:
            raise ValueError("Projector e outbox pertencem a instalacoes diferentes")
        self.projector = projector
        self.outbox = outbox
        self.event_observer = event_observer
        self._queue: queue.Queue[
            tuple[str, dict[str, Any] | None] | None
        ] = queue.Queue(
            maxsize=max(1, int(max_queue_events))
        )
        self._session_id: str | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.accepted = 0
        self.ignored = 0
        self.dropped = 0
        self.errors = 0
        self.observer_errors = 0

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        value = _text(session_id, 160)
        if not value:
            raise ValueError("session_id obrigatorio")
        with self._lock:
            self._session_id = value
            if not self._thread or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

        self._put_control(value, "resumed" if resumed else "started")

    def pause_session(self, session_id: str, *, reason: str = "paused") -> None:
        self._end_session(session_id, "paused", reason)

    def finish_session(self, session_id: str, *, reason: str = "finished") -> None:
        state = "abandoned" if reason == "abandoned" else "finished"
        self._end_session(session_id, state, reason)

    def _put_control(self, session_id: str, state: str, reason: str | None = None) -> None:
        command = {
            "_agent_lifecycle": state,
            "reason": reason,
            "occurred_ns": time.time_ns(),
        }
        try:
            self._queue.put((session_id, command), timeout=3)
        except queue.Full:
            self.dropped += 1
            raise RuntimeError("Fila do Agent cheia ao registrar ciclo da sessao")

    def _end_session(self, session_id: str, state: str, reason: str) -> None:
        with self._lock:
            if self._session_id == session_id:
                self._session_id = None
        self._put_control(session_id, state, reason)
        try:
            self._queue.put((session_id, None), timeout=3)
        except queue.Full:
            self.dropped += 1
            raise RuntimeError("Fila do Agent cheia ao limpar contexto da sessao")

    def submit(self, event: dict[str, Any]) -> bool:
        if event.get("opcode") == SENSITIVE_OPCODE or event.get("type") not in EVENT_TYPES:
            self.ignored += 1
            return False
        with self._lock:
            session_id = self._session_id
        if not session_id:
            self.ignored += 1
            return False
        try:
            self._queue.put_nowait((session_id, event))
        except queue.Full:
            self.dropped += 1
            return False
        self.accepted += 1
        return True

    def _worker(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            try:
                if item is None:
                    return
                session_id, event = item
                if event is None:
                    self.projector.finish_session(session_id)
                elif event.get("_agent_lifecycle"):
                    projected = self.projector.project_lifecycle(
                        session_id,
                        str(event["_agent_lifecycle"]),
                        reason=event.get("reason"),
                        occurred_ns=_integer(event.get("occurred_ns")),
                    )
                    self._observe(projected)
                    self.outbox.enqueue(projected)
                else:
                    projected = self.projector.project(event, session_id)
                    self._observe(projected)
                    self.outbox.enqueue(projected)
            except Exception:
                self.errors += 1
            finally:
                self._queue.task_done()

    def _observe(self, event: dict[str, Any]) -> None:
        if self.event_observer is None:
            return
        try:
            self.event_observer(event)
        except Exception:
            # A API local e apenas consumidora; nunca pode interromper a outbox.
            self.observer_errors += 1

    def wait_until_idle(self) -> None:
        self._queue.join()

    def metrics(self) -> dict[str, int | bool]:
        return {
            "queue_depth": self._queue.qsize(),
            "queue_limit": self._queue.maxsize,
            "accepted": self.accepted,
            "ignored": self.ignored,
            "dropped": self.dropped,
            "errors": self.errors,
            "observer_errors": self.observer_errors,
            "worker_alive": bool(self._thread and self._thread.is_alive()),
            **{f"outbox_{key}": value for key, value in self.outbox.metrics().items()},
        }

    def close(self) -> None:
        self.wait_until_idle()
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=3)
        self.outbox.close()
