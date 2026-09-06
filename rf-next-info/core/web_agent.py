"""Base local do Agent Windows para a futura arquitetura web.

Este modulo nao transmite dados. Ele transforma eventos ja decodificados em um
contrato de lista positiva e os grava em uma outbox SQLite separada e limitada.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import math
import queue
import sqlite3
import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from core.rfnext_frame_decode import correlate_active_equipment
from core.store import LEVEL_CURVE, exp_rank_level_progress
from core.drop_alerts import NON_ITEM_REWARD_INDEXES
from core.web_agent_character_history import (
    AgentCharacterHistory,
    IdentityDecision,
)


DECODED_EVENT_SCHEMA = "rf-qol.decoded-event/v1"
INGEST_BATCH_SCHEMA = "rf-qol.ingest-batch/v1"
SENSITIVE_OPCODE = 0x0101
DEFAULT_OUTBOX_BYTES = 512 * 1024 * 1024
DEFAULT_OUTBOX_EVENTS = 2_000_000
MAX_EVENT_BYTES = 64 * 1024
MAX_BATCH_EVENTS = 250
# Reserva espaço para sequence, envelope e metadados do lote. O receptor aceita
# 512 KiB descompactados, mas o Agent mantém lotes bem abaixo desse teto.
MAX_BATCH_BYTES = 224 * 1024
MAX_REJECTION_RECORDS = 1000
MAX_REMOTE_STATE_CACHE = 256
COMMUNITY_DROP_DEDUP_SECONDS = 5.0
EXP_RANK_CAPTURE_WINDOW_NS = 15 * 60 * 1_000_000_000
MOVEMENT_MIN_INTERVAL_NS = 1_000_000_000
MOVEMENT_EVENT_TYPES = frozenset({"move_player_request", "move_player_update"})
MAP_CHANGE_SOURCE_EVENT_TYPES = frozenset({
    "request_teleport_result",
    "teleport_response",
})
IDENTITY_PENDING_MAX_AGE_NS = 10 * 60 * 1_000_000_000
IDENTITY_PENDING_MAX_BYTES = 32 * 1024 * 1024
PROCESSING_PRIORITY_BOSS = 0
PROCESSING_PRIORITY_NORMAL = 20
PROCESSING_PRIORITY_CONTROL = PROCESSING_PRIORITY_NORMAL
DELIVERY_PRIORITY_BULK = 100
DELIVERY_PRIORITY_REALTIME = 200
DELIVERY_PRIORITY_HIGH = 300
DELIVERY_PRIORITY_IMMEDIATE = 400
DELIVERY_PRIORITY_NAMES = {
    DELIVERY_PRIORITY_BULK: "bulk",
    DELIVERY_PRIORITY_REALTIME: "realtime",
    DELIVERY_PRIORITY_HIGH: "high",
    DELIVERY_PRIORITY_IMMEDIATE: "immediate",
}
IMMEDIATE_EVENT_TYPES = frozenset({
    "agent.heartbeat",
    "boss.encounter_snapshot",
    "character.observed",
})
HIGH_PRIORITY_EVENT_TYPES = frozenset({
    "community.exp_ranking_snapshot",
    "community.faction_ranking_snapshot",
    "community.market_observed",
    "market.personal_listing_observed",
    "market.personal_listings_snapshot",
    "market.personal_transaction_observed",
})
BULK_EVENT_TYPES = frozenset({
    "inventory.snapshot",
    "map.character_moved",
    "map.entity_moved",
    "progress.collection_snapshot",
    "progress.memory_chips_snapshot",
    "world.entities_disappeared",
    "world.monsters_appeared",
    "world.players_appeared",
})


def delivery_priority(
    event_type: object, payload: object = None,
) -> int:
    normalized = str(event_type or "")
    if normalized == "session.lifecycle":
        state = payload.get("state") if isinstance(payload, dict) else None
        return (
            DELIVERY_PRIORITY_IMMEDIATE
            if state in {"started", "resumed"}
            else DELIVERY_PRIORITY_REALTIME
        )
    if normalized in IMMEDIATE_EVENT_TYPES:
        return DELIVERY_PRIORITY_IMMEDIATE
    if normalized in HIGH_PRIORITY_EVENT_TYPES:
        return DELIVERY_PRIORITY_HIGH
    if normalized in BULK_EVENT_TYPES:
        return DELIVERY_PRIORITY_BULK
    return DELIVERY_PRIORITY_REALTIME


def delivery_priority_name(value: object) -> str:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        normalized = DELIVERY_PRIORITY_REALTIME
    return DELIVERY_PRIORITY_NAMES.get(normalized, "realtime")


def _community_item_names() -> dict[str, str]:
    try:
        value = json.loads(
            Path(__file__).with_name("item_names.json").read_text(encoding="utf-8-sig")
        )
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


COMMUNITY_ITEM_NAMES = _community_item_names()

EVENT_TYPES = {
    "world_info_prefix": "character.observed",
    "update_exp": "character.exp_changed",
    "realm_contribution_update": "character.contribution_changed",
    "drop_item_field": "character.drop_received",
    "loot_announcement": "world.drop_announced",
    "appear_player_list": "world.players_appeared",
    "appear_monster_list": "world.monsters_appeared",
    "enemy_guild_list": "world.guilds_observed",
    "amity_guild_list": "world.guilds_observed",
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
    "FG2C_notify_boss_status_list_Message": "boss.status_observed",
    "FG2C_worldboss_hp_sync_Message": "boss.hp_synced",
    "FG2C_worldboss_personal_contribution_update_Message": "boss.contribution_observed",
    "FG2C_noti_worldboss_result_Message": "boss.result_observed",
    "market": "community.market_observed",
    "FL2C_respond_purchase_list_on_exchange_Message": "community.market_observed",
    "FL2C_ans_exchange_for_my_sales_list_Message": "market.personal_listing_observed",
    "personal_market_listings_snapshot": "market.personal_listings_snapshot",
    "FL2C_ans_exchange_for_my_settlement_list_Message": "market.personal_transaction_observed",
    "FL2C_respond_to_registration_of_sale_item_on_exchange_Message": "market.personal_listing_observed",
    "FL2C_respond_to_reregistration_of_sale_item_on_exchange_Message": "market.personal_listing_observed",
    "FL2C_respond_to_cancellation_of_sale_item_on_exchange_Message": "market.personal_listing_observed",
    "FL2C_notify_exchange_item_sell_Message": "market.personal_transaction_observed",
    "FL2C_respond_settlement_of_exchange_Message": "market.personal_transaction_observed",
    "FL2C_ans_exchange_for_my_transaction_history_Message": "market.personal_transaction_observed",
    "FL2C_respond_to_purchase_item_on_exchange_Message": "market.personal_transaction_observed",
    "exp_rank_list": "community.exp_ranking_snapshot",
    "realm_contribution_rank_list": "community.faction_ranking_snapshot",
    "inventory_snapshot": "inventory.snapshot",
    "inventory_delta": "inventory.snapshot",
    "collection_snapshot_chunk": "progress.collection_snapshot",
    "collection_add_response": "progress.collection_snapshot",
    "player_equip_update": "character.observed",
    "change_rover_response": "character.observed",
    "change_biosuit_response": "character.observed",
    "player_stat": "character.observed",
    "lobby_stat": "character.observed",
    "player_profile_info": "character.observed",
}

# Eventos usados somente para correlacionar uma ação própria com o UID público
# já conhecido. Eles nunca são projetados nem enviados ao site.
IDENTITY_ONLY_EVENT_TYPES = frozenset({
    "appear_player_prefix",
    "change_equip_slot_request",
    "change_equip_slot_response",
    "change_rover_request",
    "change_biosuit_request",
})

# Eventos usados pelos monitores separados de PvP e Boss nunca atravessam a
# fronteira remota. Eles ainda são projetados e entregues ao observer da API
# local, que aplica sua própria lista positiva de domínios.
LOCAL_ONLY_EVENT_TYPES = frozenset({
    # Ataques, skills e recursos alimentam somente os monitores locais. O site
    # recebe a morte PvE já consolidada, EXP, contribuição, drops e snapshots;
    # enviar cada golpe criava volume sem qualquer consumidor remoto.
    "combat.resources_changed",
    "combat.skill_resolved",
    "combat.normal_attack_resolved",
    "boss.position_observed",
    "boss.status_observed",
    "boss.hp_synced",
    "boss.contribution_observed",
    "boss.result_observed",
    "world.guilds_observed",
})

# Dados privados ou ações do personagem local só atravessam a fronteira remota
# depois que o world_info_prefix confirmou um UID público para aquela conexão.
# Eventos comunitários e observações públicas continuam independentes desse
# vínculo; PvP e Boss permanecem disponíveis somente pela API local.
CHARACTER_CONFIRMED_EVENT_TYPES = frozenset({
    "character.observed",
    "character.exp_changed",
    "character.contribution_changed",
    "character.drop_received",
    "combat.entity_died",
    "combat.resources_changed",
    "combat.skill_resolved",
    "combat.normal_attack_resolved",
    "map.character_moved",
    "map.changed",
    "map.teleport_requested",
    "map.teleport_resolved",
    "map.teleport_finished",
    "inventory.snapshot",
    "progress.collection_snapshot",
    "progress.memory_chips_snapshot",
    "market.personal_listing_observed",
    "market.personal_listings_snapshot",
    "market.personal_transaction_observed",
})


def _decoded_combat_domain(event: dict[str, Any] | None) -> str:
    if not isinstance(event, dict):
        return ""
    data = event.get("data")
    data = data if isinstance(data, dict) else {}
    fields = data.get("fields")
    fields = fields if isinstance(fields, dict) else data
    return _text(
        data.get("_combat_domain") or fields.get("_combat_domain"), 16
    ) or ""


def processing_priority(event: dict[str, Any] | None) -> int:
    """Prioriza o monitor local de Boss sem mudar a politica de envio remoto."""
    if not isinstance(event, dict):
        return PROCESSING_PRIORITY_CONTROL
    if event.get("_agent_lifecycle") or event.get("_agent_cleanup"):
        return PROCESSING_PRIORITY_CONTROL
    kind = _text(event.get("type"), 96) or ""
    public_type = EVENT_TYPES.get(kind, "")
    data = event.get("data")
    data = data if isinstance(data, dict) else {}
    fields = data.get("fields")
    fields = fields if isinstance(fields, dict) else data
    if (
        public_type.startswith("boss.")
        or _decoded_combat_domain(event) == "boss"
        or bool(data.get("_contains_boss"))
        or bool(fields.get("_contains_boss"))
    ):
        return PROCESSING_PRIORITY_BOSS
    return PROCESSING_PRIORITY_NORMAL

SESSION_STATES = {"started", "resumed", "paused", "finished", "abandoned"}

_PAYLOAD_FIELDS = {
    "character.observed": {
        "character_uid", "name", "level", "biosuit_item_index", "rover_item_index",
        "power",
    },
    "character.exp_changed": {
        "action_code", "before_level", "level", "highest_level", "total_exp",
        "gained_exp", "gained_exp_percent", "level_percent",
    },
    "character.contribution_changed": {"contribution_total"},
    "character.drop_received": {
        "result", "items", "credits_gained", "credits_total",
    },
    "world.drop_announced": {"announcements"},
    "world.players_appeared": {"entities"},
    "world.monsters_appeared": {"entities"},
    "world.guilds_observed": {"relation", "guilds"},
    "world.entities_disappeared": {"entity_refs"},
    "combat.entity_died": {
        "entity_ref", "killer_ref", "reason", "combat_domain", "killer_is_client",
    },
    "combat.resources_changed": {
        "entity_ref", "current_hp", "max_hp", "current_fp", "max_fp",
        "combat_domain",
    },
    "combat.skill_resolved": {
        "result", "caster_ref", "target_ref", "skill_index", "caster_final_hp",
        "effects", "combat_domain",
    },
    "combat.normal_attack_resolved": {
        "result", "caster_ref", "target_ref", "skill_index", "caster_final_hp",
        "effects", "combat_domain",
    },
    "map.character_moved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.changed": {"previous_map_index", "map_index"},
    "map.entity_moved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_requested": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_resolved": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.entity_warped": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "map.teleport_finished": {"entity_ref", "map_index", "teleport_index", "server_region_index", "result", "position"},
    "boss.position_observed": {"boss_ref", "npc_index", "position", "result"},
    "boss.status_observed": {"values", "boss_records", "count"},
    "boss.hp_synced": {"values"},
    "boss.contribution_observed": {"values"},
    "boss.result_observed": {
        "boss_ref", "npc_index", "position", "result", "values", "boss_records",
        "count",
    },
    "boss.encounter_snapshot": {
        "encounter_id", "started_at", "observed_at", "npc_index", "boss_name",
        "boss_level", "current_hp", "max_hp", "players",
    },
    "session.lifecycle": {"state", "reason"},
    "farm.subsession_completed": {
        "source_ref", "control_ref", "character_uid", "name", "level", "started_at",
        "ended_at", "duration_seconds", "map_name", "spot_name", "mobs",
        "gained_exp", "gained_exp_percent", "gained_contribution",
        "gained_credits", "kill_count",
    },
    "agent.heartbeat": {"capture_state", "outbox_pending", "client_count"},
    "community.market_observed": {
        "server_type", "snapshot_ref", "chunk_index", "chunk_count", "market_rows",
    },
    "market.personal_listing_observed": {
        "listing_id", "server_type", "item_index", "name", "enhance",
        "quantity", "price_per_unit", "settlement_price", "registered_time",
        "expires_time", "selling_time", "status", "action",
    },
    "market.personal_listings_snapshot": {
        "snapshot_ref", "server_type", "record_count", "listing_ids",
    },
    "market.personal_transaction_observed": {
        "transaction_id", "listing_id", "server_type", "transaction_type",
        "exchange_type_code", "item_index", "name", "enhance", "quantity",
        "price_per_unit", "settlement_price", "registered_time", "expires_time",
        "selling_time", "status", "action",
    },
    "community.exp_ranking_snapshot": {
        "snapshot_ref", "top_limit", "record_count", "completeness",
        "conflict_count", "source_pages", "first_captured_at", "captured_at",
        "capture_span_ms", "ranking_records",
    },
    "community.faction_ranking_snapshot": {
        "snapshot_ref", "faction", "top_limit", "record_count", "completeness",
        "conflict_count", "source_pages", "first_captured_at", "captured_at",
        "capture_span_ms", "faction_ranking_records",
    },
    "inventory.snapshot": {
        "snapshot_ref", "character_uid", "chunk_index", "chunk_count",
        "complete", "item_kind", "inventory_items",
    },
    "progress.collection_snapshot": {
        "snapshot_ref", "character_uid", "chunk_index", "chunk_count",
        "complete", "collection_type", "collection_records",
    },
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
    "guilds": {"guild_id", "guild_name"},
    "effects": {"entity_ref", "shield_damage", "hp_damage", "final_hp"},
    "market_rows": {
        "item_index", "name", "enhance", "lowest_price", "highest_price",
        "quantity",
    },
    "ranking_records": {
        "rank", "previous_rank", "character_name", "guild_name", "total_exp",
        "level", "level_percent",
    },
    "faction_ranking_records": {
        "rank", "previous_rank", "character_name", "guild_name", "faction_points",
    },
    "boss_records": {"values"},
    "players": {
        "player_ref", "character_uid", "name", "guild_id", "guild_name",
        "damage_total",
    },
    "inventory_items": {
        "slot", "item_index", "name", "enhance", "quantity", "equipped", "bound",
    },
    "collection_records": {
        "collection_index", "completed_slots", "total_slots", "completed",
        "completed_slot_indexes", "missing_slot_indexes",
    },
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


def _direct_character_uid(fields: dict[str, Any]) -> int | None:
    """Aceita identidade direta somente com resposta válida e nome público."""
    result = _integer(fields.get("result"))
    if result not in {None, 0} or _text(fields.get("character_name"), 120) is None:
        return None
    return _character_uid(fields.get("character_uid"))


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
    try:
        value_utc = datetime.fromtimestamp(
            timestamp_ns / 1_000_000_000, tz=timezone.utc
        )
    except (OSError, OverflowError, ValueError):
        value_utc = datetime.now(timezone.utc)
    return value_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")


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
    if event_type == "farm.subsession_completed":
        mobs = payload.get("mobs")
        if (
            not isinstance(mobs, list)
            or len(mobs) > 32
            or any(not isinstance(mob, str) or not mob or len(mob) > 96 for mob in mobs)
        ):
            raise WebEventContractError("Lista de mobs da subsessao invalida")
        control_ref = payload.get("control_ref")
        if control_ref is not None and (
            not isinstance(control_ref, str)
            or len(control_ref) != 32
            or any(char not in "0123456789abcdef" for char in control_ref)
        ):
            raise WebEventContractError("Controle da subsessao invalido")
    if event_type == "map.changed":
        map_index = payload.get("map_index")
        previous_map_index = payload.get("previous_map_index")
        if (
            type(map_index) is not int
            or not 0 <= map_index <= 2**32 - 1
            or (
                previous_map_index is not None
                and (
                    type(previous_map_index) is not int
                    or not 0 <= previous_map_index <= 2**32 - 1
                    or previous_map_index == map_index
                )
            )
        ):
            raise WebEventContractError("Troca de mapa invalida")
    if event_type == "market.personal_listings_snapshot":
        listing_ids = payload.get("listing_ids")
        if (
            not isinstance(payload.get("snapshot_ref"), str)
            or len(payload["snapshot_ref"]) != 32
            or any(char not in "0123456789abcdef" for char in payload["snapshot_ref"])
            or type(payload.get("server_type")) is not int
            or not 0 <= payload["server_type"] <= 255
            or type(payload.get("record_count")) is not int
            or not isinstance(listing_ids, list)
            or not 0 <= payload["record_count"] <= 256
            or payload["record_count"] != len(listing_ids)
            or len(set(listing_ids)) != len(listing_ids)
            or any(
                not isinstance(value, str) or len(value) != 32
                or any(char not in "0123456789abcdef" for char in value)
                for value in listing_ids
            )
        ):
            raise WebEventContractError("Snapshot pessoal de Mercado invalido")
    if event_type in {
        "market.personal_listing_observed",
        "market.personal_transaction_observed",
    }:
        required = {
            "listing_id", "server_type", "item_index", "name", "enhance",
            "quantity", "price_per_unit", "status", "action",
        }
        if event_type == "market.personal_transaction_observed":
            required.update({"transaction_id", "transaction_type"})
        identifiers = [payload.get("listing_id")]
        if "transaction_id" in payload:
            identifiers.append(payload.get("transaction_id"))
        if (
            not required.issubset(payload)
            or any(
                not isinstance(value, str) or len(value) != 32
                or any(char not in "0123456789abcdef" for char in value)
                for value in identifiers
            )
            or type(payload.get("server_type")) is not int
            or not 0 <= payload["server_type"] <= 255
            or type(payload.get("item_index")) is not int
            or not 1 <= payload["item_index"] <= 2**31 - 1
            or type(payload.get("enhance")) is not int
            or not 0 <= payload["enhance"] <= 255
            or type(payload.get("quantity")) is not int
            or not 1 <= payload["quantity"] <= 2**31 - 1
            or type(payload.get("price_per_unit")) is not int
            or not 1 <= payload["price_per_unit"] <= 2**63 - 1
            or payload.get("status") not in {
                "active", "bought", "sold", "cancelled", "settled", "observed",
            }
            or payload.get("action") not in {
                "snapshot", "listed", "relisted", "purchased", "history",
                "sold", "cancelled", "settled",
            }
            or payload.get("transaction_type") not in {
                None, "bought", "sold", "unclassified",
            }
        ):
            raise WebEventContractError("Operacao pessoal de Mercado invalida")
        for name in {
            "settlement_price", "registered_time", "expires_time", "selling_time",
            "exchange_type_code",
        }:
            value = payload.get(name)
            if value is not None and (
                type(value) is not int or not 0 <= value <= 2**64 - 1
            ):
                raise WebEventContractError("Valor pessoal de Mercado invalido")
    if str(event_type).startswith("combat.") and payload.get("combat_domain") not in {
        "pve", "pvp", "boss", "unknown",
    }:
        raise WebEventContractError("Dominio de combate nao aprovado")
    if event_type == "boss.encounter_snapshot":
        required = _PAYLOAD_FIELDS["boss.encounter_snapshot"]
        players = payload.get("players")
        if (
            set(payload) != required
            or not isinstance(payload.get("encounter_id"), str)
            or len(payload["encounter_id"]) != 64
            or any(char not in "0123456789abcdef" for char in payload["encounter_id"])
            or not isinstance(players, list)
            or len(players) > 512
        ):
            raise WebEventContractError("Snapshot de Boss invalido")
    if event_type == "progress.collection_snapshot":
        collection_type = payload.get("collection_type")
        if collection_type is not None and (
            type(collection_type) is not int or not 0 <= collection_type <= 255
        ):
            raise WebEventContractError("Tipo de colecao invalido")
        for record in payload.get("collection_records") or []:
            completed_indexes = record.get("completed_slot_indexes")
            missing_indexes = record.get("missing_slot_indexes")
            if completed_indexes is None and missing_indexes is None:
                continue
            if not isinstance(completed_indexes, list) or not isinstance(
                missing_indexes, list
            ):
                raise WebEventContractError("Indices de colecao incompletos")
            if (
                len(completed_indexes) > 10
                or len(missing_indexes) > 10
                or any(type(value) is not int or not 0 <= value < 10
                       for value in completed_indexes + missing_indexes)
                or completed_indexes != sorted(set(completed_indexes))
                or missing_indexes != sorted(set(missing_indexes))
                or set(completed_indexes).intersection(missing_indexes)
                or len(completed_indexes) != record.get("completed_slots")
                or len(completed_indexes) + len(missing_indexes)
                != record.get("total_slots")
                or (not missing_indexes) != record.get("completed")
            ):
                raise WebEventContractError("Indices de colecao invalidos")
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
        character_history: AgentCharacterHistory | None = None,
    ) -> None:
        self.installation_id = _text(installation_id, 128)
        if not self.installation_id:
            raise ValueError("installation_id obrigatorio")
        if len(pseudonym_key) < 16:
            raise ValueError("pseudonym_key deve ter pelo menos 16 bytes")
        self._key = bytes(pseudonym_key)
        self.decoder_version = _text(decoder_version, 64) or "unknown"
        self.character_history = character_history
        self._flow_clients: dict[tuple[str, str], str] = {}
        self._connection_clients: dict[str, str] = {}
        self._movement_last_ns: dict[tuple[str, str, str, int], int] = {}
        self._ranking_contexts: dict[tuple[str, int, int], dict[str, Any]] = {}
        self._connection_character_uids: dict[str, int] = {}
        self._connection_confirmation_sources: dict[str, str] = {}
        self._connection_equipped_item_uids: dict[str, set[int]] = {}
        self._connection_equipped_slots: dict[str, dict[int, int]] = {}
        self._equipment_appearances_by_character: dict[int, dict[str, Any]] = {}
        self._connection_inventory_items: dict[
            str, dict[str, dict[int, dict[str, Any]]]
        ] = {}
        self._connection_inventory_complete: dict[str, set[str]] = {}
        self._connection_inventory_snapshot_refs: dict[
            tuple[str, str], tuple[str, bool]
        ] = {}
        self._connection_map_indexes: dict[str, int] = {}
        self._auction_listings: dict[tuple[str, int, int], dict[str, Any]] = {}
        self._character_sessions: dict[tuple[str, int], str] = {}
        self._collection_contexts: dict[
            tuple[str, int, int], dict[int, dict[str, Any]]
        ] = {}
        self._sent_ranking_signatures: dict[tuple[str, int, int], str] = {}
        self._ranking_diagnostics: Counter[str] = Counter()
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

    def _bind_character_locked(
        self, connection: str, character_uid: int, source: str,
    ) -> None:
        previous_uid = self._connection_character_uids.get(connection)
        if previous_uid is not None and previous_uid != character_uid:
            self._connection_equipped_item_uids.pop(connection, None)
            self._connection_equipped_slots.pop(connection, None)
            self._connection_inventory_items.pop(connection, None)
            self._connection_inventory_complete.pop(connection, None)
            for key in tuple(self._connection_inventory_snapshot_refs):
                if key[0] == connection:
                    self._connection_inventory_snapshot_refs.pop(key, None)
            scoped_suffix = (
                f":connection:{self._opaque('connection', connection, size=24)}"
            )
            for key in tuple(self._collection_contexts):
                if key[0].endswith(scoped_suffix):
                    self._collection_contexts.pop(key, None)
        self._connection_character_uids[connection] = character_uid
        self._connection_confirmation_sources[connection] = source

    def _identity(
        self, kind: str, session_id: str, flow: str, fields: dict[str, Any]
    ) -> str:
        connection = _connection_key(flow)
        key = (session_id, connection)
        with self._lock:
            client_ref = self._connection_clients.get(connection)
            if client_ref is None:
                # A referência nasce da conexão e nunca muda no meio da sessão.
                # O UID público, quando aparecer, é enviado em character.observed
                # e vincula esta referência sem reatribuir eventos anteriores.
                client_ref = self._opaque("client-connection", connection)
                self._connection_clients[connection] = client_ref
            if kind == "world_info_prefix":
                character_uid = _direct_character_uid(fields)
                current_uid = self._connection_character_uids.get(connection)
                current_source = self._connection_confirmation_sources.get(connection)
                if character_uid is not None and (
                    current_uid is None
                    or current_uid == character_uid
                    or current_source != "direct"
                ):
                    self._bind_character_locked(
                        connection,
                        character_uid,
                        _text(fields.get("_confirmation_source"), 32) or "direct",
                    )
            active_equipment = fields.get("active_equipment")
            active_character_uid = (
                _character_uid(active_equipment.get("character_uid"))
                if isinstance(active_equipment, dict) else None
            )
            if (
                isinstance(active_equipment, dict)
                and active_character_uid is not None
                and active_character_uid
                == self._connection_character_uids.get(connection)
            ):
                equipped_uids = {
                    uid for raw_slot in active_equipment.get("slots", [])
                    if isinstance(raw_slot, dict)
                    and isinstance(raw_slot.get("item"), dict)
                    and (uid := _integer(raw_slot["item"].get("item_uid")))
                }
                self._connection_equipped_item_uids[connection] = equipped_uids
                equipped_slots = {
                    slot: uid for raw_slot in active_equipment.get("slots", [])
                    if isinstance(raw_slot, dict)
                    and (slot := _integer(
                        raw_slot.get("equip_part_type")
                        or raw_slot.get("equipment_slot")
                    )) is not None
                    and isinstance(raw_slot.get("item"), dict)
                    and (uid := _integer(raw_slot["item"].get("item_uid")))
                }
                self._connection_equipped_slots[connection] = equipped_slots
            self._flow_clients[key] = client_ref
            while len(self._flow_clients) > 256:
                self._flow_clients.pop(next(iter(self._flow_clients)))
            while len(self._connection_clients) > 256:
                expired = next(iter(self._connection_clients))
                self._connection_clients.pop(expired)
                self._connection_character_uids.pop(expired, None)
                self._connection_confirmation_sources.pop(expired, None)
                self._connection_equipped_item_uids.pop(expired, None)
                self._connection_equipped_slots.pop(expired, None)
                self._connection_inventory_items.pop(expired, None)
                self._connection_inventory_complete.pop(expired, None)
                for inventory_key in tuple(self._connection_inventory_snapshot_refs):
                    if inventory_key[0] == expired:
                        self._connection_inventory_snapshot_refs.pop(
                            inventory_key, None
                        )
                self._connection_map_indexes.pop(expired, None)
                for auction_key in tuple(self._auction_listings):
                    if auction_key[0] == expired:
                        self._auction_listings.pop(auction_key, None)
            return client_ref

    def finish_session(
        self, session_id: str, *, preserve_connections: bool = False
    ) -> None:
        with self._lock:
            connections = {
                key[1] for key in self._flow_clients if key[0] == session_id
            }
            for key in tuple(self._flow_clients):
                if key[0] == session_id:
                    self._flow_clients.pop(key, None)
            if not preserve_connections:
                for connection in connections:
                    self._connection_clients.pop(connection, None)
                    self._connection_character_uids.pop(connection, None)
                    self._connection_confirmation_sources.pop(connection, None)
                    self._connection_equipped_item_uids.pop(connection, None)
                    self._connection_equipped_slots.pop(connection, None)
                    self._connection_inventory_items.pop(connection, None)
                    self._connection_inventory_complete.pop(connection, None)
                    for inventory_key in tuple(
                        self._connection_inventory_snapshot_refs
                    ):
                        if inventory_key[0] == connection:
                            self._connection_inventory_snapshot_refs.pop(
                                inventory_key, None
                            )
                    self._connection_map_indexes.pop(connection, None)
                    for auction_key in tuple(self._auction_listings):
                        if auction_key[0] == connection:
                            self._auction_listings.pop(auction_key, None)
                    if self.character_history is not None:
                        self.character_history.release(connection)
            for key in tuple(self._movement_last_ns):
                if key[0] == session_id:
                    self._movement_last_ns.pop(key, None)
            for key in tuple(self._ranking_contexts):
                if key[0] == session_id:
                    self._ranking_contexts.pop(key, None)
                    self._sent_ranking_signatures.pop(key, None)
            for key in tuple(self._collection_contexts):
                if key[0].startswith(f"{session_id}:connection:"):
                    self._collection_contexts.pop(key, None)

    def _movement_allowed(
        self,
        kind: str,
        session_id: str,
        connection: str,
        entity_uid: object,
        occurred_ns: int,
    ) -> bool:
        if kind not in MOVEMENT_EVENT_TYPES:
            return True
        key = (session_id, connection, kind, _integer(entity_uid, 0) or 0)
        with self._lock:
            previous = self._movement_last_ns.get(key)
            if (
                previous is not None
                and occurred_ns >= previous
                and occurred_ns - previous < MOVEMENT_MIN_INTERVAL_NS
            ):
                return False
            self._movement_last_ns[key] = occurred_ns
            while len(self._movement_last_ns) > 1024:
                self._movement_last_ns.pop(next(iter(self._movement_last_ns)))
            return True

    def session_ref(self, session_id: str) -> str:
        value = _text(session_id, 160)
        if not value:
            raise WebEventContractError("Sessao obrigatoria")
        return self._opaque("session", value, size=32)

    def connection_session_id(self, session_id: str, connection: str) -> str:
        value = _text(session_id, 160)
        if not value:
            raise WebEventContractError("Sessao obrigatoria")
        return f"{value}:connection:{self._opaque('connection', connection, size=24)}"

    def client_ref_for_connection(self, connection: str) -> str:
        with self._lock:
            client_ref = self._connection_clients.get(connection)
            if client_ref is None:
                client_ref = self._opaque("client-connection", connection)
                self._connection_clients[connection] = client_ref
            return client_ref

    def character_confirmed_for_connection(self, connection: str) -> bool:
        """Confirma por UID público direto ou perfil histórico inequívoco."""
        with self._lock:
            return connection in self._connection_character_uids

    def observe_identity_event(
        self, event: dict[str, Any],
    ) -> IdentityDecision | None:
        if not isinstance(event, dict):
            return None
        kind = _text(event.get("type"), 96) or ""
        data = event.get("data")
        data = data if isinstance(data, dict) else {}
        connection = _connection_key(str(event.get("flow") or ""))
        fields = self._fields(data)
        direct_uid = (
            _direct_character_uid(fields)
            if kind == "world_info_prefix" else None
        )
        if self.character_history is not None:
            decision = self.character_history.observe(
                connection,
                kind,
                data,
                _integer(event.get("ts_ns"), time.time_ns()) or time.time_ns(),
            )
        elif direct_uid is not None:
            decision = IdentityDecision(direct_uid, "direct", 100)
        else:
            decision = None
        if decision is not None:
            with self._lock:
                self._bind_character_locked(
                    connection, decision.character_uid, decision.source,
                )
        if kind == "appear_player_prefix":
            character_uid = _character_uid(fields.get("character_uid"))
            equipment_refs = fields.get("equipment_refs")
            if character_uid is not None and isinstance(equipment_refs, list):
                with self._lock:
                    self._equipment_appearances_by_character.pop(character_uid, None)
                    self._equipment_appearances_by_character[character_uid] = {
                        "fields": fields,
                    }
                    while len(self._equipment_appearances_by_character) > 256:
                        self._equipment_appearances_by_character.pop(
                            next(iter(self._equipment_appearances_by_character))
                        )
        if kind == "change_equip_slot_response":
            result = _integer(fields.get("result"), 0)
            equipment_slot = _integer(fields.get("equipment_slot"))
            item_uid = _integer(fields.get("item_uid"), 0)
            with self._lock:
                if (
                    connection in self._connection_character_uids
                    and result == 0 and equipment_slot is not None
                    and 1 <= equipment_slot <= 255 and item_uid is not None
                ):
                    slots = self._connection_equipped_slots.setdefault(
                        connection, {}
                    )
                    if item_uid:
                        slots[equipment_slot] = item_uid
                    else:
                        slots.pop(equipment_slot, None)
                    self._connection_equipped_item_uids[connection] = set(
                        slots.values()
                    )
        return decision

    def recovered_identity_event(
        self, session_id: str, connection: str, occurred_ns: int,
    ) -> dict[str, Any] | None:
        if self.character_history is None:
            return None
        decision = self.character_history.decision(connection)
        if decision is None or decision.source == "direct":
            return None
        profile = self.character_history.profile(decision.character_uid)
        if profile is None:
            return None
        payload = profile.public_payload()
        fields = dict(payload)
        fields["character_name"] = fields.pop("name", "")
        fields["_confirmation_source"] = decision.source
        return self.project({
            "source": "memory://identity-history",
            "flow": connection,
            "stream_offset": 0,
            "bundle_seq": 0,
            "ts_ns": int(occurred_ns or time.time_ns()),
            "opcode": 0,
            "type": "world_info_prefix",
            "data": {"fields": fields},
        }, session_id)

    def merge_remote_character_profiles(
        self, profiles: list[dict[str, Any]],
    ) -> int:
        if self.character_history is None:
            return 0
        return self.character_history.merge_remote_profiles(profiles)

    def project_lifecycle(
        self,
        session_id: str,
        state: str,
        *,
        reason: str | None = None,
        occurred_ns: int | None = None,
        client_ref: str | None = None,
        stream_key: str = "lifecycle",
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
            "stream_id": self._opaque("stream", f"{session_id}:{stream_key}", size=32),
            "occurred_at": _utc_from_ns(timestamp_ns),
            "client_ref": _text(client_ref, 64),
            "type": "session.lifecycle",
            "payload": payload,
            "evidence": {
                "confidence": "agent",
                "decoder_version": self.decoder_version,
            },
        }
        _validate_event_contract(result)
        return result

    def project_heartbeat(
        self,
        *,
        capture_state: str,
        outbox_pending: int,
        client_count: int,
        occurred_ns: int | None = None,
    ) -> dict[str, Any]:
        state = _text(capture_state, 16) or "error"
        if state not in {"starting", "active", "paused", "stopped", "error"}:
            raise WebEventContractError("Estado do Agent invalido")
        pending = max(0, min(1_000_000, _integer(outbox_pending, 0) or 0))
        clients = max(0, min(64, _integer(client_count, 0) or 0))
        timestamp_ns = max(0, _integer(occurred_ns, time.time_ns()) or 0)
        payload = {
            "capture_state": state,
            "outbox_pending": pending,
            "client_count": clients,
        }
        # O runtime limita a frequência. O instante exato impede que um Agent
        # reiniciado no mesmo minuto reutilize um event_id já confirmado.
        identity = {"time": timestamp_ns, "payload": payload}
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque("heartbeat", _canonical_json(identity).hex(), size=48),
            "installation_id": self.installation_id,
            "session_ref": self.session_ref("agent-presence"),
            "stream_id": self._opaque("stream", "agent-presence", size=32),
            "occurred_at": _utc_from_ns(timestamp_ns),
            "client_ref": None,
            "type": "agent.heartbeat",
            "payload": payload,
            "evidence": {"confidence": "agent", "decoder_version": self.decoder_version},
        }
        _validate_event_contract(result)
        return result

    def project_boss_encounter(self, encounter: dict[str, Any]) -> dict[str, Any]:
        """Consolida Boss para envio sem liberar golpes brutos ou referencias locais."""
        if not isinstance(encounter, dict) or not isinstance(encounter.get("boss"), dict):
            raise WebEventContractError("Encontro de Boss invalido")
        session_ref = _text(encounter.get("_session_ref"), 64) or ""
        client_ref = _text(encounter.get("client_ref"), 64) or ""
        encounter_ref = _text(encounter.get("encounter_ref"), 128) or ""
        started_at = _text(encounter.get("started_at"), 40) or ""
        observed_at = _text(encounter.get("updated_at"), 40) or ""
        if (
            len(session_ref) != 32
            or any(char not in "0123456789abcdef" for char in session_ref)
            or len(client_ref) != 32
            or any(char not in "0123456789abcdef" for char in client_ref)
            or not encounter_ref
        ):
            raise WebEventContractError("Identidade do encontro de Boss invalida")
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
            observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise WebEventContractError("Horario do encontro de Boss invalido") from error
        if not started_at.endswith("Z") or not observed_at.endswith("Z") or observed < started:
            raise WebEventContractError("Horario do encontro de Boss invalido")

        encounter_id = self._opaque(
            "boss-encounter",
            f"{client_ref}:{encounter_ref}:{started_at}",
            size=64,
        )
        players = []
        for row in encounter.get("players") or []:
            if not isinstance(row, dict):
                continue
            local_ref = _text(row.get("_player_ref"), 128)
            name = _text(row.get("name"), 96)
            damage = _integer(row.get("damage"), 0)
            if not local_ref or not name or damage is None or damage < 0:
                continue
            uid = _character_uid(row.get("uid"))
            guild_id = _integer(row.get("guild_id"))
            if guild_id is not None and not 0 < guild_id <= 2**64 - 1:
                guild_id = None
            players.append({
                "player_ref": self._opaque(
                    "boss-player", f"{encounter_id}:{local_ref}", size=32,
                ),
                "character_uid": uid,
                "name": name,
                "guild_id": guild_id,
                "guild_name": _text(row.get("guild_name"), 96),
                "damage_total": min(damage, 2**63 - 1),
            })
            if len(players) >= 512:
                break
        players.sort(key=lambda row: (
            -row["damage_total"], row["name"].casefold(), row["player_ref"],
        ))

        boss = encounter["boss"]
        maximum = _integer(boss.get("max_hp"))
        maximum = (
            min(maximum, 2**63 - 1)
            if maximum is not None and maximum > 0 else None
        )
        current = _integer(boss.get("current_hp"))
        current = min(max(0, current), 2**63 - 1) if current is not None else None
        if current is not None and maximum is not None:
            current = min(current, maximum)
        npc_index = _integer(boss.get("npc_index"))
        if npc_index is not None and not 0 <= npc_index <= 2**32 - 1:
            npc_index = None
        boss_level = _integer(boss.get("level"))
        if boss_level is not None and not 1 <= boss_level <= 999:
            boss_level = None
        payload = {
            "encounter_id": encounter_id,
            "started_at": started_at,
            "observed_at": observed_at,
            "npc_index": npc_index,
            "boss_name": _text(boss.get("name"), 96) or "Boss confirmado",
            "boss_level": boss_level,
            "current_hp": current,
            "max_hp": maximum,
            "players": players,
        }
        identity = _canonical_json({
            "encounter_id": encounter_id,
            "observed_at": observed_at,
            "payload": payload,
        })
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque("event", identity.hex(), size=48),
            "installation_id": self.installation_id,
            "session_ref": session_ref,
            "stream_id": self._opaque("stream", f"boss:{encounter_id}", size=32),
            "occurred_at": observed_at,
            "client_ref": client_ref,
            "type": "boss.encounter_snapshot",
            "payload": payload,
            "evidence": {
                "confidence": "agent",
                "decoder_version": self.decoder_version,
            },
        }
        _validate_event_contract(result)
        return result

    def project_subsession(
        self, session_id: str, report: dict[str, Any]
    ) -> dict[str, Any]:
        """Projeta uma subsessão encerrada e escolhida pelo usuário."""
        session_id = _text(session_id, 160) or ""
        character_uid = _character_uid(report.get("character_uid"))
        started_ns = _integer(report.get("started_ns"))
        ended_ns = _integer(report.get("ended_ns"))
        duration_seconds = _integer(report.get("duration_seconds"))
        source_value = _text(report.get("source_subsession_id"), 192)
        if (
            not session_id
            or character_uid is None
            or started_ns is None
            or ended_ns is None
            or ended_ns < started_ns
            or duration_seconds is None
            or not 1 <= duration_seconds <= 31_536_000
            or source_value is None
        ):
            raise WebEventContractError("Subsessao encerrada invalida")
        mobs = []
        for value in report.get("mobs") if isinstance(report.get("mobs"), list) else []:
            mob = _text(value, 96)
            if mob and mob not in mobs:
                mobs.append(mob)
            if len(mobs) == 32:
                break
        summary = report.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        payload = {
            key: value
            for key, value in {
                "source_ref": self._opaque("subsession", source_value, size=32),
                "control_ref": (
                    str(report.get("control_ref"))
                    if isinstance(report.get("control_ref"), str)
                    and len(str(report.get("control_ref"))) == 32
                    and all(
                        char in "0123456789abcdef"
                        for char in str(report.get("control_ref"))
                    ) else None
                ),
                "character_uid": character_uid,
                "name": _text(report.get("name"), 120) or "Subsessao",
                "level": _integer(summary.get("level")),
                "started_at": _utc_from_ns(started_ns),
                "ended_at": _utc_from_ns(ended_ns),
                "duration_seconds": duration_seconds,
                "map_name": _text(report.get("map_name"), 120) or "",
                "spot_name": _text(report.get("spot_name"), 120) or "",
                "mobs": mobs,
                "gained_exp": max(0, _integer(report.get("exp_total"), 0) or 0),
                "gained_exp_percent": _number(report.get("exp_total_percent")),
                "gained_contribution": (
                    max(0, _integer(summary.get("contribution")) or 0)
                    if _integer(summary.get("contribution")) is not None else None
                ),
                "gained_credits": max(0, _integer(summary.get("credits"), 0) or 0),
                "kill_count": max(
                    0,
                    _integer(
                        report.get("kill_count", report.get("mob_kills_estimated")),
                        0,
                    ) or 0,
                ),
            }.items()
            if value is not None
        }
        with self._lock:
            scoped_session_id = self._character_sessions.get(
                (session_id, character_uid), session_id
            )
        identity = {
            "session": session_id,
            "source_ref": payload["source_ref"],
            "ended_at": payload["ended_at"],
        }
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque(
                "event", _canonical_json(identity).hex(), size=48
            ),
            "installation_id": self.installation_id,
            "session_ref": self.session_ref(scoped_session_id),
            "stream_id": self._opaque(
                "stream", f"{scoped_session_id}:subsessions", size=32
            ),
            "occurred_at": payload["ended_at"],
            "client_ref": None,
            "type": "farm.subsession_completed",
            "payload": payload,
            "evidence": {
                "confidence": "derived",
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

    @staticmethod
    def _ordered_numeric_values(value: object, prefix: str) -> list[int]:
        if not isinstance(value, dict):
            return []
        pairs: list[tuple[int, int]] = []
        for key, raw in value.items():
            name = str(key)
            if not name.startswith(prefix):
                continue
            digits = "".join(character for character in name[len(prefix):] if character.isdigit())
            number = _integer(raw)
            if digits and number is not None:
                pairs.append((int(digits), number))
        return [number for _index, number in sorted(pairs)[:64]]

    def _market_payloads(
        self, data: dict[str, Any], session_id: str
    ) -> list[dict[str, Any]]:
        if data.get("message") not in {
            None, "FL2C_respond_purchase_list_on_exchange_Message",
        } or _integer(data.get("ret"), 0) != 0:
            return []
        server_type = _integer(data.get("exchange_server_type"), 0) or 0
        if not 0 <= server_type <= 255:
            return []
        market_rows = []
        for row in data.get("exchange_item_simple_infos") or []:
            if not isinstance(row, dict):
                continue
            item_index = _integer(row.get("item_index"))
            lowest = _integer(row.get("lowest_price"))
            highest = _integer(row.get("highest_price"), lowest)
            quantity = _integer(row.get("number_of_registered_items"))
            enhance = _integer(row.get("enchant_level"), 0)
            # O servidor do jogo usa 0 quando o maior preco nao esta
            # preenchido. A exportacao manual ja trata esse caso como o menor
            # preco conhecido; o envio automatico deve preservar a mesma linha
            # em vez de descartar um anuncio valido.
            if lowest is not None and highest is not None and highest < lowest:
                highest = lowest
            if (
                item_index is None or not 1 <= item_index <= 2**31 - 1
                or lowest is None or not 0 <= lowest <= 2**63 - 1
                or highest is None or not lowest <= highest <= 2**63 - 1
                or quantity is None or not 0 <= quantity <= 2**31 - 1
                or enhance is None or not 0 <= enhance <= 255
            ):
                continue
            market_rows.append({
                "item_index": item_index,
                "name": (
                    _text(row.get("item_name"), 120)
                    or _text(COMMUNITY_ITEM_NAMES.get(str(item_index)), 120)
                    or ""
                ),
                "enhance": enhance,
                "lowest_price": lowest,
                "highest_price": highest,
                "quantity": quantity,
            })
            if len(market_rows) >= 10_000:
                break
        if not market_rows:
            return []
        market_rows.sort(key=lambda item: (item["item_index"], item["enhance"]))
        snapshot_ref = self._opaque(
            "market-snapshot",
            f"{session_id}:{server_type}:"
            + hashlib.sha256(_canonical_json(market_rows)).hexdigest(),
        )
        chunks = [
            market_rows[index:index + 256]
            for index in range(0, len(market_rows), 256)
        ]
        return [{
            "server_type": server_type,
            "snapshot_ref": snapshot_ref,
            "chunk_index": index,
            "chunk_count": len(chunks),
            "market_rows": chunk,
        } for index, chunk in enumerate(chunks, start=1)]

    def _auction_entry_payload(
        self, server_type: int, entry: object,
    ) -> tuple[int, dict[str, Any]] | None:
        if not isinstance(entry, dict):
            return None
        exchange_index = _integer(entry.get("exchange_index"))
        item = entry.get("item_info")
        item = item if isinstance(item, dict) else {}
        item_index = _integer(item.get("index"))
        quantity = _integer(item.get("count"))
        price_per_unit = _integer(entry.get("selling_price"))
        enhance = _integer(item.get("enchant_level"), 0)
        if (
            exchange_index is None or not 1 <= exchange_index <= 2**64 - 1
            or item_index is None or not 1 <= item_index <= 2**31 - 1
            or quantity is None or not 1 <= quantity <= 2**31 - 1
            or price_per_unit is None or not 1 <= price_per_unit <= 2**63 - 1
            or enhance is None or not 0 <= enhance <= 255
        ):
            return None
        payload = {
            "listing_id": self._opaque(
                "auction-listing", f"{server_type}:{exchange_index}", size=32
            ),
            "server_type": server_type,
            "item_index": item_index,
            "name": (
                _text(item.get("name"), 120)
                or _text(COMMUNITY_ITEM_NAMES.get(str(item_index)), 120)
                or ""
            ),
            "enhance": enhance,
            "quantity": quantity,
            "price_per_unit": price_per_unit,
        }
        optional = {
            "settlement_price": _integer(entry.get("settlement_price")),
            "registered_time": _integer(entry.get("registed_time")),
            "expires_time": _integer(entry.get("expired_time")),
            "selling_time": _integer(entry.get("selling_time")),
        }
        for name, value in optional.items():
            if value is not None and 0 <= value <= 2**64 - 1:
                payload[name] = value
        return exchange_index, payload

    def _personal_market_payloads(
        self, data: dict[str, Any], connection: str,
    ) -> list[dict[str, Any]]:
        """Projeta ações próprias sem IDs internos de conta, item ou sessão."""
        message = _text(data.get("message"), 120) or ""
        server_type = _integer(data.get("exchange_server_type"))
        if server_type is None or not 0 <= server_type <= 255:
            return []
        if message != "FL2C_notify_exchange_item_sell_Message" and _integer(
            data.get("ret"), 0
        ) != 0:
            return []

        listings: list[tuple[int, dict[str, Any]]] = []
        transaction_type: str | None = None
        action = "observed"
        status = "active"
        exchange_type_codes: dict[int, int] = {}

        if message == "FL2C_ans_exchange_for_my_sales_list_Message":
            action = "snapshot"
            for entry in data.get("my_sales_list") or []:
                parsed = self._auction_entry_payload(server_type, entry)
                if parsed is not None:
                    listings.append(parsed)
        elif message == "FL2C_ans_exchange_for_my_settlement_list_Message":
            action, status, transaction_type = "snapshot", "sold", "sold"
            for entry in data.get("my_settlement_list") or []:
                parsed = self._auction_entry_payload(server_type, entry)
                if parsed is not None:
                    listings.append(parsed)
        elif message in {
            "FL2C_respond_to_registration_of_sale_item_on_exchange_Message",
            "FL2C_respond_to_reregistration_of_sale_item_on_exchange_Message",
        }:
            action = (
                "listed"
                if message == "FL2C_respond_to_registration_of_sale_item_on_exchange_Message"
                else "relisted"
            )
            parsed = self._auction_entry_payload(
                server_type, data.get("exchange_item_info")
            )
            if parsed is not None:
                listings.append(parsed)
        elif message == "FL2C_respond_to_purchase_item_on_exchange_Message":
            action, status, transaction_type = "purchased", "bought", "bought"
            for result in data.get("purchase_results") or []:
                if not isinstance(result, dict) or _integer(result.get("ret"), 0) != 0:
                    continue
                parsed = self._auction_entry_payload(
                    server_type, result.get("exchange_info")
                )
                if parsed is not None:
                    listings.append(parsed)
        elif message == "FL2C_ans_exchange_for_my_transaction_history_Message":
            action, status, transaction_type = "history", "observed", "unclassified"
            for history in data.get("my_transaction_history") or []:
                if not isinstance(history, dict):
                    continue
                parsed = self._auction_entry_payload(
                    server_type, history.get("exchange_item_info")
                )
                if parsed is None:
                    continue
                exchange_type = _integer(history.get("exchange_type"))
                if exchange_type is not None and 0 <= exchange_type <= 2**32 - 1:
                    exchange_type_codes[parsed[0]] = exchange_type
                listings.append(parsed)
        else:
            indices: list[int] = []
            settlement_prices: dict[int, int] = {}
            if message == "FL2C_respond_to_cancellation_of_sale_item_on_exchange_Message":
                action, status = "cancelled", "cancelled"
                value = _integer(data.get("exchange_index"))
                if value is not None:
                    indices.append(value)
            elif message == "FL2C_notify_exchange_item_sell_Message":
                action, status, transaction_type = "sold", "sold", "sold"
                indices.extend(
                    value for raw in data.get("exchange_indices") or []
                    if (value := _integer(raw)) is not None
                )
            elif message == "FL2C_respond_settlement_of_exchange_Message":
                action, status, transaction_type = "settled", "settled", "sold"
                indices.extend(
                    value for raw in data.get("exchange_index_list") or []
                    if (value := _integer(raw)) is not None
                )
                for result in data.get("respond_settlement_infos") or []:
                    if not isinstance(result, dict):
                        continue
                    value = _integer(result.get("exchange_index"))
                    price = _integer(result.get("selling_price"))
                    if value is not None:
                        indices.append(value)
                        if price is not None and 0 <= price <= 2**63 - 1:
                            settlement_prices[value] = price
            else:
                return []
            with self._lock:
                for exchange_index in dict.fromkeys(indices):
                    cached = self._auction_listings.get(
                        (connection, server_type, exchange_index)
                    )
                    if cached is None:
                        continue
                    payload = dict(cached)
                    if exchange_index in settlement_prices:
                        payload["settlement_price"] = settlement_prices[exchange_index]
                    listings.append((exchange_index, payload))

        projected: list[dict[str, Any]] = []
        with self._lock:
            for exchange_index, base in listings:
                cache_key = (connection, server_type, exchange_index)
                current = dict(self._auction_listings.get(cache_key) or {})
                current.update(base)
                current.update({"status": status, "action": action})
                self._auction_listings[cache_key] = current
                while len(self._auction_listings) > 20_000:
                    self._auction_listings.pop(next(iter(self._auction_listings)))
                payload = dict(current)
                if transaction_type is not None:
                    payload.update({
                        "transaction_id": self._opaque(
                            "auction-transaction",
                            f"{connection}:{server_type}:{exchange_index}:{transaction_type}",
                            size=32,
                        ),
                        "transaction_type": transaction_type,
                    })
                    exchange_type = exchange_type_codes.get(exchange_index)
                    if exchange_type is not None:
                        payload["exchange_type_code"] = exchange_type
                projected.append(payload)
        return projected

    def _personal_market_snapshot_payload(
        self, data: dict[str, Any], connection: str,
        listings: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Resume uma resposta completa de anúncios, inclusive quando vazia."""
        if (
            data.get("message") != "FL2C_ans_exchange_for_my_sales_list_Message"
            or _integer(data.get("ret"), 0) != 0
        ):
            return None
        server_type = _integer(data.get("exchange_server_type"))
        raw_listings = data.get("my_sales_list")
        if (
            server_type is None or not 0 <= server_type <= 255
            or not isinstance(raw_listings, list) or len(raw_listings) > 256
            or len(listings) != len(raw_listings)
        ):
            return None
        listing_ids = sorted(str(item["listing_id"]) for item in listings)
        signature = f"{connection}:{server_type}:{','.join(listing_ids)}"
        return {
            "snapshot_ref": self._opaque(
                "auction-listings-snapshot", signature, size=32,
            ),
            "server_type": server_type,
            "record_count": len(listing_ids),
            "listing_ids": listing_ids,
        }

    def _inventory_payloads(
        self, data: dict[str, Any], session_id: str, connection: str
    ) -> list[dict[str, Any]]:
        character_uid = self._connection_character_uids.get(connection)
        item_kind = _text(data.get("item_kind"), 24)
        if (
            character_uid is None or data.get("container") != "inventory"
            or item_kind not in {"equipment", "stackable"}
        ):
            return []
        equipped_item_uids = self._connection_equipped_item_uids.get(
            connection, set()
        )
        raw_items = (
            data.get("items") if isinstance(data.get("items"), list)
            else [data.get("item")] if isinstance(data.get("item"), dict)
            else []
        )
        incoming: dict[int, dict[str, Any]] = {}
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            slot = _integer(raw.get("inventory_slot"))
            item_index = _integer(raw.get("item_index") or raw.get("index"))
            quantity = _integer(raw.get("count"), 0)
            enhance = _integer(raw.get("enchant_level"), 0)
            item_uid = _integer(raw.get("item_uid"))
            if (
                slot is None or not 0 <= slot <= 100_000
                or item_index is None or not 1 <= item_index <= 2**31 - 1
                or quantity is None or not 0 <= quantity <= 2**31 - 1
                or enhance is None or not 0 <= enhance <= 255
            ):
                continue
            incoming[slot] = {
                "slot": slot,
                "item_index": item_index,
                "name": _text(COMMUNITY_ITEM_NAMES.get(str(item_index)), 120) or "",
                "enhance": enhance,
                "quantity": quantity,
                "equipped": bool(item_uid and item_uid in equipped_item_uids),
                "bound": bool(raw.get("lock")),
                "_item_uid": item_uid,
            }

        state_by_kind = self._connection_inventory_items.setdefault(connection, {})
        complete_kinds = self._connection_inventory_complete.setdefault(connection, set())
        is_delta = data.get("type") == "inventory_delta"
        if is_delta:
            if not incoming:
                return []
            state = state_by_kind.setdefault(item_kind, {})
            for slot, item in incoming.items():
                if item["quantity"] <= 0:
                    state.pop(slot, None)
                else:
                    state[slot] = item
        else:
            state_by_kind[item_kind] = {
                slot: item for slot, item in incoming.items()
                if item["quantity"] > 0
            }
            complete_kinds.add(item_kind)

        state = state_by_kind.get(item_kind, {})
        if len(state) > 10_000:
            state_by_kind[item_kind] = dict(sorted(state.items())[:10_000])
            state = state_by_kind[item_kind]
        inventory_items = []
        for item in state.values():
            item_uid = _integer(item.get("_item_uid"))
            inventory_items.append({
                key: value for key, value in {
                    **item,
                    "equipped": bool(item_uid and item_uid in equipped_item_uids),
                }.items() if not key.startswith("_")
            })
        if not inventory_items and is_delta and item_kind not in complete_kinds:
            return []
        inventory_items.sort(key=lambda item: item["slot"])
        identity = {
            "character_uid": character_uid,
            "container": data.get("container"),
            "item_kind": item_kind,
            "items": inventory_items,
        }
        snapshot_ref = self._opaque(
            "inventory-snapshot", hashlib.sha256(_canonical_json(identity)).hexdigest()
        )
        complete = item_kind in complete_kinds
        state_key = (connection, item_kind)
        state_signature = (snapshot_ref, complete)
        if self._connection_inventory_snapshot_refs.get(state_key) == state_signature:
            return []
        self._connection_inventory_snapshot_refs[state_key] = state_signature
        chunks = ([
            inventory_items[index:index + 256]
            for index in range(0, len(inventory_items), 256)
        ] or [[]])
        return [{
            "snapshot_ref": snapshot_ref,
            "character_uid": character_uid,
            "chunk_index": index,
            "chunk_count": len(chunks),
            "complete": complete,
            "item_kind": item_kind,
            "inventory_items": chunk,
        } for index, chunk in enumerate(chunks, start=1)]

    def invalidate_inventory_projection(self, event: dict[str, Any]) -> None:
        """Permite reenviar um snapshot cuja entrega falhou entre chunks."""
        kind = _text(event.get("type"), 96) if isinstance(event, dict) else None
        data = event.get("data") if isinstance(event, dict) else None
        if not isinstance(data, dict):
            return
        if kind == "player_profile_info":
            item_kind = "equipment"
        elif kind in {"inventory_snapshot", "inventory_delta"}:
            item_kind = _text(data.get("item_kind"), 24)
        else:
            return
        if item_kind not in {"equipment", "stackable"}:
            return
        connection = _connection_key(str(event.get("flow") or ""))
        with self._lock:
            self._connection_inventory_snapshot_refs.pop(
                (connection, item_kind), None
            )

    def _collection_update_payloads(
        self, data: dict[str, Any], session_id: str, connection: str
    ) -> list[dict[str, Any]]:
        character_uid = self._connection_character_uids.get(connection)
        collection_index = _integer(data.get("collection_index"))
        collection_type = _integer(data.get("collection_type"))
        slots = data.get("slot_values")
        if (
            character_uid is None or _integer(data.get("result_code"), 0) != 0
            or collection_index is None or collection_index <= 0
            or collection_type is None or not 0 <= collection_type <= 255
            or not isinstance(slots, list) or not slots
        ):
            return []
        records = [{
            "collection_index": collection_index,
            **self._collection_progress(data),
        }]
        snapshot_ref = self._opaque(
            "collection-update",
            hashlib.sha256(_canonical_json({
                "character_uid": character_uid, "records": records,
            })).hexdigest(),
        )
        return [{
            "snapshot_ref": snapshot_ref,
            "character_uid": character_uid,
            "chunk_index": 1,
            "chunk_count": 1,
            "complete": False,
            "collection_type": collection_type,
            "collection_records": records,
        }]

    def _collection_payloads(
        self, data: dict[str, Any], session_id: str, connection: str
    ) -> list[dict[str, Any]]:
        character_uid = self._connection_character_uids.get(connection)
        collection_type = _integer(data.get("collection_type"))
        if character_uid is None or collection_type is None:
            return []
        key = (session_id, character_uid, collection_type)
        context = self._collection_contexts.setdefault(key, {})
        for raw in data.get("records") if isinstance(data.get("records"), list) else []:
            if not isinstance(raw, dict):
                continue
            collection_index = _integer(raw.get("collection_index"))
            slots = raw.get("slot_values")
            if (
                collection_index is None or collection_index <= 0
                or not isinstance(slots, list) or not slots
            ):
                continue
            context[collection_index] = {
                "collection_index": collection_index,
                **self._collection_progress(raw),
            }
        if not data.get("is_end") or not context:
            return []
        records = [context[index] for index in sorted(context)]
        self._collection_contexts.pop(key, None)
        snapshot_ref = self._opaque(
            "collection-snapshot",
            hashlib.sha256(_canonical_json({
                "character_uid": character_uid,
                "collection_type": collection_type,
                "records": records,
            })).hexdigest(),
        )
        chunks = [records[index:index + 256] for index in range(0, len(records), 256)]
        return [{
            "snapshot_ref": snapshot_ref,
            "character_uid": character_uid,
            "chunk_index": index,
            "chunk_count": len(chunks),
            "complete": True,
            "collection_type": collection_type,
            "collection_records": chunk,
        } for index, chunk in enumerate(chunks, start=1)]

    @staticmethod
    def _collection_progress(data: dict[str, Any]) -> dict[str, Any]:
        catalog_completed = data.get("completed_slots")
        catalog_incomplete = data.get("incomplete_slots")
        if isinstance(catalog_completed, list) and isinstance(catalog_incomplete, list):
            completed_indexes = {
                value for raw in catalog_completed
                if (value := _integer(raw)) is not None and value >= 0
            }
            incomplete_indexes = {
                value for raw in catalog_incomplete
                if (value := _integer(raw)) is not None and value >= 0
            }
            if not completed_indexes.intersection(incomplete_indexes):
                total_slots = len(completed_indexes) + len(incomplete_indexes)
                if total_slots:
                    completed_slots = len(completed_indexes)
                    return {
                        "completed_slots": completed_slots,
                        "total_slots": total_slots,
                        "completed": completed_slots == total_slots,
                        "completed_slot_indexes": sorted(completed_indexes),
                        "missing_slot_indexes": sorted(incomplete_indexes),
                    }
        slots = data.get("slot_values")
        slots = slots if isinstance(slots, list) else []
        completed_slots = sum(1 for value in slots if _integer(value, 0))
        return {
            "completed_slots": completed_slots,
            "total_slots": len(slots),
            "completed": completed_slots == len(slots),
        }

    def _payload(
        self, kind: str, data: dict[str, Any], session_id: str,
        occurred_ns: int | None = None, connection: str = "",
    ) -> dict[str, Any] | None:
        fields = self._fields(data)
        if kind == "world_info_prefix":
            observed_uid = _direct_character_uid(fields)
            confirmed_uid = self._connection_character_uids.get(connection)
            if observed_uid is None or observed_uid != confirmed_uid:
                return None
            return {
                key: value for key, value in {
                    "character_uid": confirmed_uid,
                    "name": _text(fields.get("character_name")),
                    "level": _integer(fields.get("level")),
                    "biosuit_item_index": _integer(fields.get("biosuit_item_index")),
                    "rover_item_index": _integer(fields.get("rover_item_index")),
                    "power": _integer(fields.get("power") or fields.get("combat_power")),
                }.items() if value is not None
            }
        if kind in {
            "player_equip_update", "change_rover_response", "change_biosuit_response",
            "player_stat", "lobby_stat",
        }:
            confirmed_uid = self._connection_character_uids.get(connection)
            observed_uid = _character_uid(fields.get("character_uid"))
            # player_equip_update is broadcast for every nearby player.  Its UID
            # may enrich the already-confirmed local character, but must never
            # establish or replace the identity attached to this TCP flow.
            if kind == "player_equip_update" and observed_uid != confirmed_uid:
                return None
            character_uid = confirmed_uid
            if character_uid is None or _integer(fields.get("result"), 0) != 0:
                return None
            return {
                key: value for key, value in {
                    "character_uid": character_uid,
                    "rover_item_index": _integer(fields.get("rover_item_index")),
                    "biosuit_item_index": _integer(fields.get("biosuit_item_index")),
                    "power": _integer(fields.get("combat_power") or fields.get("power")),
                }.items() if value is not None
            }
        if kind == "update_exp":
            level = _integer(data.get("level"))
            total_exp = _integer(data.get("exp"))
            gained_exp = _integer(data.get("gain_exp"))
            required = LEVEL_CURVE.get(level + 1) if level is not None else None
            return {
                key: value for key, value in {
                    "action_code": _integer(data.get("action_code")),
                    "before_level": _integer(data.get("before_level")),
                    "level": level,
                    "highest_level": _integer(data.get("highest_level")),
                    "total_exp": total_exp,
                    "gained_exp": gained_exp,
                    "gained_exp_percent": (
                        _number(gained_exp * 100 / required)
                        if required and gained_exp is not None else None
                    ),
                    "level_percent": (
                        _number(total_exp * 100 / required)
                        if required and total_exp is not None else None
                    ),
                }.items() if value is not None
            }
        if kind == "realm_contribution_update":
            value = data.get("contribution_total", fields.get("contribution_total"))
            return {"contribution_total": _integer(value, 0)}
        if kind == "drop_item_field":
            rows = []
            credits_gained = 0
            credits_total = None
            if _integer(data.get("ret"), 0) != 0:
                return None
            for row in data.get("results") if isinstance(data.get("results"), list) else []:
                if not isinstance(row, dict):
                    continue
                item_index = _integer(row.get("item_index"))
                count = _integer(row.get("count"))
                if (
                    _integer(row.get("ret"), 0) == 0
                    and item_index == 1
                    and count is not None
                    and count > 0
                ):
                    credits_gained += count
                    gain_total = _integer(row.get("gain_total"))
                    if gain_total is not None and gain_total >= 0:
                        credits_total = gain_total
                    continue
                if (
                    _integer(row.get("ret"), 0) != 0
                    or item_index is None
                    or item_index in NON_ITEM_REWARD_INDEXES
                    or count is None
                    or count <= 0
                ):
                    continue
                rows.append({
                    key: value for key, value in {
                        "result": _integer(row.get("ret")),
                        "item_index": item_index,
                        "count": count,
                        "action_code": _integer(row.get("action_code")),
                    }.items() if value is not None
                })
                if len(rows) >= 128:
                    break
            return {
                key: value for key, value in {
                    "result": _integer(data.get("ret"), 0),
                    "items": rows,
                    "credits_gained": credits_gained or None,
                    "credits_total": credits_total,
                }.items() if value is not None
            }
        if kind == "loot_announcement":
            rows = []
            for row in data.get("announcements") if isinstance(data.get("announcements"), list) else []:
                if not isinstance(row, dict):
                    continue
                message_kind = _integer(row.get("message_kind"))
                if message_kind not in {None, 2}:
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
            return {"announcements": rows} if rows else None
        if kind in {"appear_player_list", "appear_monster_list"}:
            return {
                "entities": self._project_units(
                    data.get("units"), session_id,
                    players=kind == "appear_player_list",
                )
            }
        if kind in {"enemy_guild_list", "amity_guild_list"}:
            guilds = []
            for row in data.get("guilds") if isinstance(data.get("guilds"), list) else []:
                if not isinstance(row, dict):
                    continue
                guild_id = _integer(row.get("guild_id"))
                guild_name = _text(row.get("guild_name"))
                if guild_id is None or not guild_name:
                    continue
                guilds.append({"guild_id": guild_id, "guild_name": guild_name})
                if len(guilds) >= 1024:
                    break
            return {
                "relation": "enemy" if kind == "enemy_guild_list" else "amity",
                "guilds": guilds,
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
                    "combat_domain": _text(data.get("_combat_domain"), 16) or "unknown",
                    "killer_is_client": (
                        bool(data.get("_killer_is_client"))
                        if "_killer_is_client" in data else None
                    ),
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
                    "combat_domain": _text(data.get("_combat_domain"), 16) or "unknown",
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
                    "combat_domain": _text(data.get("_combat_domain"), 16) or "unknown",
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
        if kind in {
            "FG2C_notify_boss_status_list_Message",
            "FG2C_worldboss_hp_sync_Message",
            "FG2C_worldboss_personal_contribution_update_Message",
            "FG2C_noti_worldboss_result_Message",
        }:
            values = self._ordered_numeric_values(fields, "f")
            boss_records = []
            for record in data.get("records") if isinstance(data.get("records"), list) else []:
                record_values = self._ordered_numeric_values(record, "r")
                if record_values:
                    boss_records.append({"values": record_values})
                if len(boss_records) >= 256:
                    break
            payload = {"values": values}
            if boss_records:
                payload["boss_records"] = boss_records
                payload["count"] = len(boss_records)
            return payload
        if kind in {
            "market", "FL2C_respond_purchase_list_on_exchange_Message",
        }:
            prepared = data.get("_agent_market_payload")
            if isinstance(prepared, dict):
                return prepared
            payloads = self._market_payloads(data, session_id)
            return payloads[0] if payloads else None
        if EVENT_TYPES.get(kind) in {
            "market.personal_listing_observed",
            "market.personal_transaction_observed",
        }:
            prepared = data.get("_agent_personal_market_payload")
            return prepared if isinstance(prepared, dict) else None
        if EVENT_TYPES.get(kind) == "market.personal_listings_snapshot":
            prepared = data.get("_agent_personal_market_snapshot_payload")
            return prepared if isinstance(prepared, dict) else None
        if kind == "exp_rank_list":
            return self._exp_ranking_payload(data, session_id, occurred_ns)
        if kind == "realm_contribution_rank_list":
            return self._faction_ranking_payload(data, occurred_ns)
        if kind in {"inventory_snapshot", "inventory_delta"}:
            prepared = data.get("_agent_inventory_payload")
            return prepared if isinstance(prepared, dict) else None
        if kind in {"collection_snapshot_chunk", "collection_add_response"}:
            prepared = data.get("_agent_collection_payload")
            return prepared if isinstance(prepared, dict) else None
        raise WebEventContractError(f"Tipo nao aprovado: {kind}")

    def _exp_ranking_payload(
        self, data: dict[str, Any], session_id: str, occurred_ns: int | None
    ) -> dict[str, Any] | None:
        if data.get("field_decode") != "captura-layout-exato":
            self._ranking_diagnostics["invalid_layout"] += 1
            return None
        raw_rows = data.get("records")
        if not isinstance(raw_rows, list) or not raw_rows:
            self._ranking_diagnostics["empty_page"] += 1
            return None
        first = next((row for row in raw_rows if isinstance(row, dict)), None)
        if first is None:
            self._ranking_diagnostics["empty_page"] += 1
            return None
        scope = _integer(first.get("scope_id_raw"))
        cycle = _integer(first.get("ranking_cycle_raw"))
        if scope is None or cycle is None:
            self._ranking_diagnostics["missing_scope_or_cycle"] += 1
            return None
        key = (session_id, scope, cycle)
        now_ns = _integer(occurred_ns, time.time_ns()) or time.time_ns()
        existing = self._ranking_contexts.get(key)
        if existing is not None and (
            now_ns < int(existing["first_ns"])
            or now_ns - int(existing["first_ns"]) > EXP_RANK_CAPTURE_WINDOW_NS
        ):
            self._ranking_contexts.pop(key, None)
            existing = None
        context = self._ranking_contexts.setdefault(key, {
            "records": {}, "uids": {}, "conflicts": set(),
            "first_ns": now_ns, "last_ns": now_ns, "pages": 0,
        })
        context["pages"] += 1
        context["last_ns"] = now_ns
        accepted_rows = 0
        invalid_rows = 0
        for raw in raw_rows:
            if not isinstance(raw, dict):
                invalid_rows += 1
                continue
            uid = _integer(raw.get("character_uid"))
            uid_repeat = _integer(raw.get("character_uid_repeat"))
            rank = _integer(raw.get("rank"))
            total_exp = _integer(raw.get("total_exp"))
            record_scope = _integer(raw.get("scope_id_raw"))
            record_cycle = _integer(raw.get("ranking_cycle_raw"))
            name = _text(raw.get("character_name"), 80)
            if (
                uid is None or not 1 <= uid <= 2**64 - 1 or uid != uid_repeat
                or rank is None or not 1 <= rank <= 100
                or total_exp is None or not 0 <= total_exp <= 2**63 - 1
                or (record_scope, record_cycle) != (scope, cycle)
                or not name
            ):
                invalid_rows += 1
                continue
            level, percent = exp_rank_level_progress(total_exp)
            if level is None or percent is None:
                invalid_rows += 1
                continue
            previous_rank = _integer(raw.get("previous_rank"), 0) or 0
            record = {
                "rank": rank,
                "previous_rank": previous_rank if 1 <= previous_rank <= 100 else 0,
                "character_name": name,
                "guild_name": _text(raw.get("guild_name"), 80) or "",
                "total_exp": total_exp,
                "level": level,
                "level_percent": percent,
            }
            previous = context["records"].get(rank)
            if previous is not None and previous != record:
                context["conflicts"].add(rank)
            other_rank = context["uids"].get(uid)
            if other_rank is not None and other_rank != rank:
                context["conflicts"].update((rank, other_rank))
            context["records"][rank] = record
            context["uids"][uid] = rank
            accepted_rows += 1
        if invalid_rows:
            self._ranking_diagnostics["invalid_rows"] += invalid_rows
        self._ranking_diagnostics["accepted_rows"] += accepted_rows
        if (
            set(context["records"]) != set(range(1, 101))
            or context["conflicts"]
        ):
            self._ranking_diagnostics[
                "conflicts" if context["conflicts"] else "incomplete_top100"
            ] += 1
            while len(self._ranking_contexts) > 8:
                oldest = next(iter(self._ranking_contexts))
                self._ranking_contexts.pop(oldest, None)
                self._sent_ranking_signatures.pop(oldest, None)
            return None
        records = [context["records"][rank] for rank in range(1, 101)]
        signature = hashlib.sha256(_canonical_json(records)).hexdigest()
        if self._sent_ranking_signatures.get(key) == signature:
            self._ranking_diagnostics["duplicate_snapshot"] += 1
            return None
        self._sent_ranking_signatures[key] = signature
        self._ranking_diagnostics["emitted_snapshots"] += 1
        return {
            "snapshot_ref": self._opaque(
                "exp-ranking-snapshot", f"{scope}:{cycle}:{signature}"
            ),
            "top_limit": 100,
            "record_count": 100,
            "completeness": "complete",
            "conflict_count": 0,
            "source_pages": min(100, int(context["pages"])),
            "first_captured_at": _utc_from_ns(context["first_ns"]),
            "captured_at": _utc_from_ns(context["last_ns"]),
            "capture_span_ms": min(
                60 * 60 * 1000,
                max(0, (context["last_ns"] - context["first_ns"]) // 1_000_000),
            ),
            "ranking_records": records,
        }

    def _faction_ranking_payload(
        self, data: dict[str, Any], occurred_ns: int | None
    ) -> dict[str, Any] | None:
        fields = self._fields(data)
        faction = (_text(fields.get("faction_name"), 40) or "").casefold()
        raw_rows = data.get("records")
        if (
            data.get("field_decode") != "captura-layout-exato"
            or _integer(fields.get("rank_variant_raw")) != 0
            or faction not in {"accretia", "bellato", "cora"}
            or not isinstance(raw_rows, list)
            or len(raw_rows) != 100
        ):
            return None
        records: dict[int, dict[str, Any]] = {}
        for raw in raw_rows:
            if not isinstance(raw, dict):
                return None
            rank = _integer(raw.get("rank"))
            name = _text(raw.get("character_name"), 80)
            points = _number(raw.get("contribution"))
            if (
                rank is None or not 1 <= rank <= 100 or rank in records
                or not name or points is None or not points.is_integer()
                or not 0 <= points <= 2**63 - 1
            ):
                return None
            records[rank] = {
                "rank": rank,
                "previous_rank": 0,
                "character_name": name,
                "guild_name": _text(raw.get("guild_name"), 80) or "",
                "faction_points": int(points),
            }
        if set(records) != set(range(1, 101)):
            return None
        ordered = [records[rank] for rank in range(1, 101)]
        captured_at = _utc_from_ns(occurred_ns)
        signature = hashlib.sha256(_canonical_json(ordered)).hexdigest()
        return {
            "snapshot_ref": self._opaque(
                "faction-ranking-snapshot", f"{faction}:{signature}"
            ),
            "faction": faction.capitalize(),
            "top_limit": 100,
            "record_count": 100,
            "completeness": "complete",
            "conflict_count": 0,
            "source_pages": 1,
            "first_captured_at": captured_at,
            "captured_at": captured_at,
            "capture_span_ms": 0,
            "faction_ranking_records": ordered,
        }

    def ranking_diagnostics(self) -> dict[str, int]:
        return {
            str(name): int(count)
            for name, count in self._ranking_diagnostics.most_common(32)
        }

    def project(
        self, event: dict[str, Any], session_id: str
    ) -> dict[str, Any] | None:
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
        scoped_session_id = self.connection_session_id(session_id, connection)
        with self._lock:
            character_uid = self._connection_character_uids.get(connection)
            if character_uid is not None:
                self._character_sessions[(session_id, character_uid)] = scoped_session_id
                while len(self._character_sessions) > 256:
                    self._character_sessions.pop(next(iter(self._character_sessions)))
        occurred_ns = _integer(event.get("ts_ns"), 0) or 0
        if not self._movement_allowed(
            kind,
            session_id,
            connection,
            fields.get("entity_uid") or fields.get("uid"),
            occurred_ns,
        ):
            return None
        payload = self._payload(
            kind, data, scoped_session_id, occurred_ns, connection
        )
        if payload is None:
            return None
        identity = {
            "session": session_id,
            "flow": flow,
            "offset": _integer(event.get("stream_offset"), 0),
            "bundle": _integer(event.get("bundle_seq"), 0),
            "time": occurred_ns,
            "kind": kind,
            "payload": payload,
        }
        result = {
            "schema": DECODED_EVENT_SCHEMA,
            "event_id": self._opaque("event", _canonical_json(identity).hex(), size=48),
            "installation_id": self.installation_id,
            "session_ref": self.session_ref(scoped_session_id),
            "stream_id": self._opaque(
                "stream", f"{scoped_session_id}:{connection}", size=32
            ),
            "occurred_at": _utc_from_ns(event.get("ts_ns")),
            "client_ref": client_ref,
            "type": public_type,
            "payload": payload,
            "evidence": {
                "confidence": (
                    "decoded-history"
                    if self._connection_confirmation_sources.get(connection, "direct")
                    != "direct" else "decoded"
                ),
                "decoder_version": self.decoder_version,
            },
        }
        _validate_event_contract(result)
        if len(_canonical_json(result)) > MAX_EVENT_BYTES:
            raise WebEventContractError("Evento excede o limite do contrato")
        return result

    def project_many(
        self, event: dict[str, Any], session_id: str
    ) -> list[dict[str, Any]]:
        kind = _text(event.get("type"), 96) if isinstance(event, dict) else None
        if kind == "player_profile_info":
            data = event.get("data")
            if not isinstance(data, dict):
                return []
            flow = str(event.get("flow") or "")
            fields = self._fields(data)
            connection = _connection_key(flow)
            confirmed_uid = self._connection_character_uids.get(connection)
            if confirmed_uid is not None and not isinstance(
                fields.get("active_equipment"), dict
            ):
                with self._lock:
                    appearance = self._equipment_appearances_by_character.get(
                        confirmed_uid
                    )
                correlated = correlate_active_equipment(
                    {"fields": fields}, [appearance] if appearance else []
                )
                if correlated is not None and correlated[0].get("complete") is True:
                    fields = {**fields, "active_equipment": correlated[0]}
            self._identity(kind, session_id, flow, fields)
            confirmed_uid = self._connection_character_uids.get(connection)
            active_equipment = fields.get("active_equipment")
            active_uid = (
                _character_uid(active_equipment.get("character_uid"))
                if isinstance(active_equipment, dict) else None
            )
            items = fields.get("items")
            if (
                confirmed_uid is None or active_uid != confirmed_uid
                or active_equipment.get("complete") is False
                or not isinstance(items, list) or not items
            ):
                return []
            payloads = self._inventory_payloads({
                "type": "inventory_snapshot",
                "container": "inventory",
                "item_kind": "equipment",
                "items": items,
            }, self.connection_session_id(session_id, connection), connection)
            projected_events = []
            for payload in payloads:
                snapshot_event = dict(event)
                snapshot_event["type"] = "inventory_snapshot"
                snapshot_event["data"] = {"_agent_inventory_payload": payload}
                projected = self.project(snapshot_event, session_id)
                if projected is not None:
                    projected_events.append(projected)
            return projected_events
        multi_types = {
            "market", "FL2C_respond_purchase_list_on_exchange_Message",
            "FL2C_ans_exchange_for_my_sales_list_Message",
            "FL2C_ans_exchange_for_my_settlement_list_Message",
            "FL2C_respond_to_registration_of_sale_item_on_exchange_Message",
            "FL2C_respond_to_reregistration_of_sale_item_on_exchange_Message",
            "FL2C_respond_to_cancellation_of_sale_item_on_exchange_Message",
            "FL2C_notify_exchange_item_sell_Message",
            "FL2C_respond_settlement_of_exchange_Message",
            "FL2C_ans_exchange_for_my_transaction_history_Message",
            "FL2C_respond_to_purchase_item_on_exchange_Message",
            "inventory_snapshot", "inventory_delta", "collection_snapshot_chunk",
            "collection_add_response",
        }
        if kind not in multi_types:
            projected = self.project(event, session_id)
            if projected is None:
                return []
            projected_events = [projected]
            map_change = self._project_map_change(
                kind or "", event, projected
            )
            if map_change is not None:
                projected_events.append(map_change)
            return projected_events
        data = event.get("data")
        if not isinstance(data, dict):
            return []
        connection = _connection_key(str(event.get("flow") or ""))
        scoped_session_id = self.connection_session_id(session_id, connection)
        if kind in {"market", "FL2C_respond_purchase_list_on_exchange_Message"}:
            payloads = self._market_payloads(data, scoped_session_id)
            prepared_key = "_agent_market_payload"
        elif EVENT_TYPES.get(kind or "") in {
            "market.personal_listing_observed",
            "market.personal_transaction_observed",
        }:
            payloads = self._personal_market_payloads(data, connection)
            prepared_key = "_agent_personal_market_payload"
        elif kind in {"inventory_snapshot", "inventory_delta"}:
            payloads = self._inventory_payloads(data, scoped_session_id, connection)
            prepared_key = "_agent_inventory_payload"
        elif kind == "collection_add_response":
            payloads = self._collection_update_payloads(
                data, scoped_session_id, connection
            )
            prepared_key = "_agent_collection_payload"
        else:
            payloads = self._collection_payloads(data, scoped_session_id, connection)
            prepared_key = "_agent_collection_payload"
        projected_events = []
        for payload in payloads:
            chunk_event = dict(event)
            chunk_event["data"] = {prepared_key: payload}
            projected = self.project(chunk_event, session_id)
            if projected is not None:
                projected_events.append(projected)
        if kind == "FL2C_ans_exchange_for_my_sales_list_Message":
            snapshot_payload = self._personal_market_snapshot_payload(
                data, connection, payloads,
            )
            if snapshot_payload is not None:
                snapshot_event = dict(event)
                snapshot_event["type"] = "personal_market_listings_snapshot"
                snapshot_event["data"] = {
                    "_agent_personal_market_snapshot_payload": snapshot_payload,
                }
                projected = self.project(snapshot_event, session_id)
                if projected is not None:
                    projected_events.append(projected)
        return projected_events

    def _project_map_change(
        self,
        kind: str,
        event: dict[str, Any],
        projected: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Deriva uma transição somente de um teleporte confirmado pelo servidor."""
        if (
            kind not in MAP_CHANGE_SOURCE_EVENT_TYPES
            or projected.get("type") != "map.teleport_resolved"
        ):
            return None
        source_payload = projected.get("payload")
        if not isinstance(source_payload, dict) or _integer(
            source_payload.get("result")
        ) != 0:
            return None
        map_index = _integer(source_payload.get("map_index"))
        if map_index is None or not 0 <= map_index <= 2**32 - 1:
            return None
        connection = _connection_key(str(event.get("flow") or ""))
        with self._lock:
            # Não crie estado remoto para uma conexão ainda sem personagem
            # confirmado. Se o evento estiver no buffer, o replay fará a
            # derivação depois que a identidade estiver disponível.
            if connection not in self._connection_character_uids:
                return None
            previous_map_index = self._connection_map_indexes.get(connection)
            if previous_map_index == map_index:
                return None
            self._connection_map_indexes[connection] = map_index
        payload = {"map_index": map_index}
        if previous_map_index is not None:
            payload["previous_map_index"] = previous_map_index
        identity = {
            "source_event_id": projected["event_id"],
            "previous_map_index": previous_map_index,
            "map_index": map_index,
        }
        result = {
            **projected,
            "event_id": self._opaque(
                "map-change", _canonical_json(identity).hex(), size=48
            ),
            "type": "map.changed",
            "payload": payload,
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
        self._issued_batches: dict[str, tuple[tuple[int, str], ...]] = {}
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS outbox_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                document BLOB NOT NULL,
                byte_size INTEGER NOT NULL,
                delivery_priority INTEGER NOT NULL DEFAULT 200,
                created_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox_rejections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                rejected_ns INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS outbox_inflight (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                batch_id TEXT NOT NULL,
                first_sequence INTEGER NOT NULL,
                last_sequence INTEGER NOT NULL,
                document BLOB NOT NULL,
                created_ns INTEGER NOT NULL
            );
        """)
        columns = {
            str(row[1])
            for row in self.conn.execute("PRAGMA table_info(outbox_events)")
        }
        if "delivery_priority" not in columns:
            with self.conn:
                self.conn.execute(
                    "ALTER TABLE outbox_events ADD COLUMN "
                    "delivery_priority INTEGER NOT NULL DEFAULT 200"
                )
                for event_type in _PAYLOAD_FIELDS:
                    self.conn.execute(
                        "UPDATE outbox_events SET delivery_priority=? "
                        "WHERE event_type=?",
                        (delivery_priority(event_type), event_type),
                    )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS outbox_priority_sequence "
            "ON outbox_events(delivery_priority DESC,sequence ASC)"
        )
        self._event_count = 0
        self._byte_count = 0
        self._refresh_counts()
        self._data_version = self._read_data_version()
        self.local_only_quarantined = 0

    def _read_data_version(self) -> int:
        row = self.conn.execute("PRAGMA data_version").fetchone()
        return int(row[0]) if row is not None else 0

    def _sync_external_changes(self) -> None:
        """Atualiza contadores somente quando outra conexão alterou a outbox."""
        data_version = self._read_data_version()
        if data_version == self._data_version:
            return
        self._refresh_counts()
        self._data_version = data_version

    def _refresh_counts(self) -> None:
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
            self._sync_external_changes()
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
                       (event_id,event_type,occurred_at,document,byte_size,
                        delivery_priority,created_ns)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        event_id, event_type, occurred_at, document, len(document),
                        delivery_priority(event_type, event.get("payload")),
                        time.time_ns(),
                    ),
                )
            self._event_count += 1
            self._byte_count += len(document)
            return True

    def quarantine_event_types(
        self, event_types: set[str] | frozenset[str], *, reason: str
    ) -> int:
        """Remove da entrega remota tipos agora locais e guarda só a auditoria."""
        normalized = tuple(sorted({
            _text(value, 128) for value in event_types if _text(value, 128)
        }))
        if not normalized:
            return 0
        placeholders = ",".join("?" for _value in normalized)
        safe_reason = _text(reason, 160) or "local_only_policy"
        with self._lock:
            self._sync_external_changes()
            count_row = self.conn.execute(
                f"SELECT COUNT(*),COALESCE(SUM(byte_size),0) "
                f"FROM outbox_events WHERE event_type IN ({placeholders})",
                normalized,
            ).fetchone()
            count, released = int(count_row[0]), int(count_row[1])
            if not count:
                return 0
            audit_rows = self.conn.execute(
                f"SELECT event_id FROM outbox_events "
                f"WHERE event_type IN ({placeholders}) "
                "ORDER BY sequence DESC LIMIT ?",
                (*normalized, MAX_REJECTION_RECORDS),
            ).fetchall()
            rejected_ns = time.time_ns()
            with self.conn:
                self.conn.executemany(
                    "INSERT INTO outbox_rejections(event_id,reason,rejected_ns) "
                    "VALUES(?,?,?)",
                    (
                        (str(row[0]), safe_reason, rejected_ns)
                        for row in audit_rows
                    ),
                )
                self.conn.execute(
                    f"DELETE FROM outbox_events "
                    f"WHERE event_type IN ({placeholders})",
                    normalized,
                )
                self.conn.execute("DELETE FROM outbox_inflight WHERE singleton=1")
                self.conn.execute(
                    """DELETE FROM outbox_rejections
                       WHERE id NOT IN (
                           SELECT id FROM outbox_rejections
                           ORDER BY id DESC LIMIT ?
                       )""",
                    (MAX_REJECTION_RECORDS,),
                )
            self._event_count = max(0, self._event_count - count)
            self._byte_count = max(0, self._byte_count - released)
            self.local_only_quarantined += count
            return count

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
        priority: int | None = None,
    ) -> dict[str, Any] | None:
        event_limit = max(1, min(MAX_BATCH_EVENTS, int(max_events)))
        byte_limit = max(1024, min(MAX_BATCH_BYTES, int(max_bytes)))
        with self._lock:
            inflight = self.conn.execute(
                "SELECT * FROM outbox_inflight WHERE singleton=1"
            ).fetchone()
            if inflight is not None:
                batch = json.loads(bytes(inflight["document"]).decode("utf-8"))
                issued = tuple(
                    (int(event["sequence"]), str(event["event_id"]))
                    for event in batch["events"]
                )
                self._issued_batches[str(batch["batch_id"])] = issued
                return batch
            if priority is None:
                priority_row = self.conn.execute(
                    "SELECT MAX(delivery_priority) FROM outbox_events"
                ).fetchone()
                if priority_row is None or priority_row[0] is None:
                    return None
                selected_priority = int(priority_row[0])
            else:
                selected_priority = int(priority)
            candidates = self.conn.execute(
                "SELECT * FROM outbox_events WHERE delivery_priority=? "
                "ORDER BY sequence LIMIT ?",
                (selected_priority, event_limit),
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
            issued = tuple(
                (int(row["sequence"]), str(row["event_id"]))
                for row in rows
            )
            batch = {
                "schema": INGEST_BATCH_SCHEMA,
                "batch_id": batch_id,
                "installation_id": self.installation_id,
                "sent_at": _utc_from_ns(time.time_ns()),
                "first_sequence": int(rows[0]["sequence"]),
                "last_sequence": int(rows[-1]["sequence"]),
                "events": events,
            }
            document = _canonical_json(batch)
            with self.conn:
                self.conn.execute(
                    """INSERT INTO outbox_inflight
                       (singleton,batch_id,first_sequence,last_sequence,document,created_ns)
                       VALUES(1,?,?,?,?,?)""",
                    (
                        batch_id,
                        int(rows[0]["sequence"]),
                        int(rows[-1]["sequence"]),
                        document,
                        time.time_ns(),
                    ),
                )
            self._issued_batches[batch_id] = issued
            return batch

    def acknowledge(self, batch_id: str, accepted_through_sequence: int) -> int:
        with self._lock:
            self._sync_external_changes()
            issued = self._issued_batches.get(str(batch_id))
            if issued is None:
                inflight = self.conn.execute(
                    "SELECT document FROM outbox_inflight WHERE singleton=1 AND batch_id=?",
                    (str(batch_id),),
                ).fetchone()
                if inflight is None:
                    raise WebEventContractError("ACK pertence a um lote nao emitido")
                batch = json.loads(bytes(inflight["document"]).decode("utf-8"))
                issued = tuple(
                    (int(event["sequence"]), str(event["event_id"]))
                    for event in batch["events"]
                )
            accepted = int(accepted_through_sequence)
            sequences = tuple(sequence for sequence, _event_id in issued)
            if accepted not in sequences:
                raise WebEventContractError("ACK fora dos limites do lote")
            accepted_index = sequences.index(accepted) + 1
            accepted_pairs = issued[:accepted_index]
            accepted_ids = tuple(event_id for _sequence, event_id in accepted_pairs)
            placeholders = ",".join("?" for _event_id in accepted_ids)
            rows = self.conn.execute(
                f"SELECT sequence,event_id,byte_size FROM outbox_events "
                f"WHERE event_id IN ({placeholders})",
                accepted_ids,
            ).fetchall()
            found = {
                str(row["event_id"]): (int(row["sequence"]), int(row["byte_size"]))
                for row in rows
            }
            if any(
                event_id not in found or found[event_id][0] != sequence
                for sequence, event_id in accepted_pairs
            ):
                raise WebEventContractError("ACK nao corresponde ao lote emitido")
            with self.conn:
                self.conn.execute(
                    f"DELETE FROM outbox_events WHERE event_id IN ({placeholders})",
                    accepted_ids,
                )
                self.conn.execute(
                    "DELETE FROM outbox_inflight WHERE singleton=1 AND batch_id=?",
                    (str(batch_id),),
                )
            self._issued_batches.pop(str(batch_id), None)
            self._event_count = max(0, self._event_count - len(accepted_ids))
            self._byte_count = max(
                0,
                self._byte_count - sum(byte_size for _sequence, byte_size in found.values()),
            )
            return len(accepted_ids)

    def pending_priorities(self) -> tuple[int, ...]:
        with self._lock:
            return tuple(
                int(row[0])
                for row in self.conn.execute(
                    "SELECT DISTINCT delivery_priority FROM outbox_events "
                    "ORDER BY delivery_priority DESC"
                )
            )

    def reject(self, event_id: str, reason: str) -> bool:
        safe_reason = _text(reason, 160) or "rejected"
        with self._lock:
            self._sync_external_changes()
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
                self.conn.execute("DELETE FROM outbox_inflight WHERE singleton=1")
                self.conn.execute(
                    """DELETE FROM outbox_rejections
                       WHERE id NOT IN (
                           SELECT id FROM outbox_rejections
                           ORDER BY id DESC LIMIT ?
                       )""",
                    (MAX_REJECTION_RECORDS,),
                )
            self._event_count = max(0, self._event_count - 1)
            self._byte_count = max(0, self._byte_count - int(row["byte_size"]))
            return True

    def metrics(self) -> dict[str, object]:
        with self._lock:
            self._sync_external_changes()
            row = self.conn.execute(
                """SELECT MIN(sequence),MAX(sequence),MIN(created_ns)
                   FROM outbox_events"""
            ).fetchone()
            oldest_ns = int(row[2]) if row[2] is not None else 0
            priority_counts = {
                name: 0 for name in DELIVERY_PRIORITY_NAMES.values()
            }
            priority_counts.update({
                delivery_priority_name(priority): int(count)
                for priority, count in self.conn.execute(
                    "SELECT delivery_priority,COUNT(*) FROM outbox_events "
                    "GROUP BY delivery_priority"
                )
            })
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
                "local_only_quarantined": self.local_only_quarantined,
                "priority_counts": priority_counts,
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
        delivery_notifier: Callable[[], object] | None = None,
    ) -> None:
        if projector.installation_id != outbox.installation_id:
            raise ValueError("Projector e outbox pertencem a instalacoes diferentes")
        self.projector = projector
        self.outbox = outbox
        self.event_observer = event_observer
        self.delivery_notifier = delivery_notifier
        self._queue: queue.PriorityQueue[
            tuple[int, int, str | None, dict[str, Any] | None]
        ] = queue.PriorityQueue(
            maxsize=max(1, int(max_queue_events))
        )
        self._queue_sequence = itertools.count()
        self._session_id: str | None = None
        self._session_initial_states: dict[str, str] = {}
        self._active_connections: dict[str, dict[str, str]] = {}
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._max_pending_identity_events = max(
            128, min(32_768, int(max_queue_events) * 4)
        )
        self._pending_identity_events: dict[
            tuple[str, str], deque[tuple[int, dict[str, Any], int]]
        ] = {}
        self._pending_identity_count = 0
        self._pending_identity_bytes = 0
        self.identity_buffered = 0
        self.identity_replayed = 0
        self.identity_expired = 0
        self.accepted = 0
        self.ignored = 0
        self.dropped = 0
        self.errors = 0
        self.observer_errors = 0
        self.projected = 0
        self.skipped = 0
        self.local_only = 0
        self.unconfirmed = 0
        self.enqueued = 0
        self.duplicates = 0
        self.accepted_by_type: Counter[str] = Counter()
        self.ignored_by_type: Counter[str] = Counter()
        self.projected_by_type: Counter[str] = Counter()
        self.skipped_by_type: Counter[str] = Counter()
        self.local_only_by_type: Counter[str] = Counter()
        self.unconfirmed_by_type: Counter[str] = Counter()
        self.errors_by_type: Counter[str] = Counter()
        self.last_errors_by_type: dict[str, str] = {}
        self.delivery_notify_errors = 0
        self._enqueued_rate_buckets: deque[tuple[int, int]] = deque()
        self._last_remote_states: dict[tuple[str, str, str], bytes] = {}
        self._recent_community_drops: dict[bytes, tuple[float, str]] = {}

    def set_delivery_notifier(
        self, notifier: Callable[[], object] | None,
    ) -> None:
        with self._metrics_lock:
            self.delivery_notifier = notifier

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        value = _text(session_id, 160)
        if not value:
            raise ValueError("session_id obrigatorio")
        with self._lock:
            self._session_id = value
            self._session_initial_states[value] = "resumed" if resumed else "started"
            if not self._thread or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(target=self._worker, daemon=True)
                self._thread.start()

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
            self._queue.put((
                PROCESSING_PRIORITY_CONTROL,
                next(self._queue_sequence),
                session_id,
                command,
            ), timeout=3)
        except queue.Full:
            self.dropped += 1
            raise RuntimeError("Fila do Agent cheia ao registrar ciclo da sessao")

    def _end_session(self, session_id: str, state: str, reason: str) -> None:
        with self._lock:
            if self._session_id == session_id:
                self._session_id = None
            # Limpar antes de uma eventual retomada; o worker antigo não pode
            # apagar o estado de uma nova captura com o mesmo session_id.
            self._session_initial_states.pop(session_id, None)
        self._put_control(session_id, state, reason)
        try:
            cleanup = {
                "_agent_cleanup": True,
                "preserve_connections": state == "paused",
            }
            self._queue.put((
                PROCESSING_PRIORITY_CONTROL,
                next(self._queue_sequence),
                session_id,
                cleanup,
            ), timeout=3)
        except queue.Full:
            self.dropped += 1
            raise RuntimeError("Fila do Agent cheia ao limpar contexto da sessao")

    def submit(self, event: dict[str, Any]) -> bool:
        kind = str(event.get("type") or "unknown")[:96]
        if (
            event.get("opcode") == SENSITIVE_OPCODE
            or event.get("type") not in EVENT_TYPES
            and event.get("type") not in IDENTITY_ONLY_EVENT_TYPES
        ):
            self.ignored += 1
            with self._metrics_lock:
                self.ignored_by_type[kind] += 1
            return False
        with self._lock:
            session_id = self._session_id
            session_state = (
                self._session_initial_states.get(session_id, "started")
                if session_id else "started"
            )
        if not session_id:
            self.ignored += 1
            with self._metrics_lock:
                self.ignored_by_type[kind] += 1
            return False
        try:
            queued_event = dict(event)
            queued_event["_agent_session_state"] = session_state
            self._queue.put_nowait((
                processing_priority(queued_event),
                next(self._queue_sequence),
                session_id,
                queued_event,
            ))
        except queue.Full:
            self.dropped += 1
            return False
        self.accepted += 1
        with self._metrics_lock:
            self.accepted_by_type[kind] += 1
        return True

    def submit_subsession(
        self, session_id: str, report: dict[str, Any]
    ) -> bool:
        projected = self.projector.project_subsession(session_id, report)
        self._observe(projected)
        queued = self.outbox.enqueue(projected)
        self._record_projected(projected["type"], queued)
        return queued

    def _worker(self) -> None:
        while not self._stop.is_set():
            item = self._queue.get()
            try:
                _priority, _sequence, session_id, event = item
                if session_id is None and event is None:
                    return
                if event is None:
                    self.projector.finish_session(session_id)
                elif event.get("_agent_cleanup"):
                    self._discard_pending_session(session_id)
                    self.projector.finish_session(
                        session_id,
                        preserve_connections=bool(
                            event.get("preserve_connections")
                        ),
                    )
                elif event.get("_agent_lifecycle"):
                    self._discard_pending_session(session_id)
                    connections = self._active_connections.pop(session_id, {})
                    for connection, scoped_session_id in connections.items():
                        projected = self.projector.project_lifecycle(
                            scoped_session_id,
                            str(event["_agent_lifecycle"]),
                            reason=event.get("reason"),
                            occurred_ns=_integer(event.get("occurred_ns")),
                            client_ref=self.projector.client_ref_for_connection(connection),
                            stream_key=connection,
                        )
                        self._observe(projected)
                        queued = self.outbox.enqueue(projected)
                        self._record_projected(projected["type"], queued)
                else:
                    kind = str(event.get("type") or "unknown")[:96]
                    connection = _connection_key(str(event.get("flow") or ""))
                    was_confirmed = self.projector.character_confirmed_for_connection(
                        connection
                    )
                    decision = self.projector.observe_identity_event(event)
                    confirmed = self.projector.character_confirmed_for_connection(
                        connection
                    )
                    became_confirmed = confirmed and not was_confirmed
                    if confirmed:
                        self._activate_connection(session_id, connection, event)
                    if became_confirmed and decision and decision.source != "direct":
                        recovered = self.projector.recovered_identity_event(
                            session_id,
                            connection,
                            _integer(event.get("ts_ns"), time.time_ns())
                            or time.time_ns(),
                        )
                        if recovered is not None:
                            self._observe(recovered)
                            queued = self.outbox.enqueue(recovered)
                            self._record_projected(recovered["type"], queued)
                        self._replay_pending(session_id, connection)
                    if kind in IDENTITY_ONLY_EVENT_TYPES:
                        continue
                    public_type = EVENT_TYPES.get(kind)
                    remote_requires_identity = (
                        public_type in CHARACTER_CONFIRMED_EVENT_TYPES
                        and public_type not in LOCAL_ONLY_EVENT_TYPES
                        and not (
                            str(public_type).startswith("combat.")
                            and _decoded_combat_domain(event) in {
                                "pvp", "boss", "unknown",
                            }
                        )
                    )
                    if not confirmed and remote_requires_identity:
                        self._buffer_identity_event(session_id, connection, event)
                    projected_events = self.projector.project_many(event, session_id)
                    if projected_events:
                        for projected in projected_events:
                            self._observe(projected)
                            self._route_projected(projected, confirmed=confirmed)
                    else:
                        self.skipped += 1
                        with self._metrics_lock:
                            self.skipped_by_type[kind] += 1
                        if not confirmed and remote_requires_identity:
                            self._record_unconfirmed(public_type or kind)
                    if became_confirmed and (not decision or decision.source == "direct"):
                        self._replay_pending(session_id, connection)
            except Exception as error:
                if isinstance(event, dict):
                    self.projector.invalidate_inventory_projection(event)
                self.errors += 1
                kind = (
                    str(event.get("type") or event.get("_agent_lifecycle") or "control")[:96]
                    if isinstance(event, dict) else "control"
                )
                with self._metrics_lock:
                    self.errors_by_type[kind] += 1
                    self.last_errors_by_type[kind] = (
                        f"{type(error).__name__}: {error}"
                    )[:240]
            finally:
                self._queue.task_done()

    def _activate_connection(
        self, session_id: str, connection: str, event: dict[str, Any],
    ) -> None:
        active = self._active_connections.setdefault(session_id, {})
        if connection in active:
            return
        scoped_session_id = self.projector.connection_session_id(
            session_id, connection
        )
        active[connection] = scoped_session_id
        lifecycle = self.projector.project_lifecycle(
            scoped_session_id,
            str(event.get("_agent_session_state") or "started"),
            occurred_ns=_integer(event.get("ts_ns"), time.time_ns()),
            client_ref=self.projector.client_ref_for_connection(connection),
            stream_key=connection,
        )
        self._observe(lifecycle)
        queued = self.outbox.enqueue(lifecycle)
        self._record_projected(lifecycle["type"], queued)

    def _route_projected(
        self, projected: dict[str, Any], *, confirmed: bool, observe: bool = True,
    ) -> None:
        is_non_pve_combat = (
            projected["type"].startswith("combat.")
            and projected["payload"].get("combat_domain") != "pve"
        )
        if projected["type"] in LOCAL_ONLY_EVENT_TYPES or is_non_pve_combat:
            self._record_local_only(projected["type"])
        elif (
            projected["type"] in CHARACTER_CONFIRMED_EVENT_TYPES
            and not confirmed
        ):
            self._record_unconfirmed(projected["type"])
        else:
            state_key: tuple[str, str, str] | None = None
            state_fingerprint: bytes | None = None
            if projected["type"] == "world.drop_announced":
                rows = projected.get("payload", {}).get("announcements") or []
                signature = hashlib.sha256(_canonical_json([{
                    key: row.get(key) for key in (
                        "character_uid", "player_name", "item_index", "count",
                    )
                } for row in rows if isinstance(row, dict)])).digest()
                now = time.monotonic()
                for key, (expires_at, _origin) in tuple(
                    self._recent_community_drops.items()
                ):
                    if expires_at < now:
                        self._recent_community_drops.pop(key, None)
                previous = self._recent_community_drops.get(signature)
                client_ref = str(projected.get("client_ref") or "")
                # ponytail: sem ID da mensagem do servidor, a janela curta
                # deduplica somente cópias entre clientes; o mesmo cliente pode
                # registrar anúncios idênticos legítimos.
                if previous is not None and previous[1] != client_ref:
                    self._record_projected(projected["type"], False)
                    return
                self._recent_community_drops[signature] = (
                    now + COMMUNITY_DROP_DEDUP_SECONDS, client_ref,
                )
                while len(self._recent_community_drops) > MAX_REMOTE_STATE_CACHE:
                    self._recent_community_drops.pop(
                        next(iter(self._recent_community_drops))
                    )
            if projected["type"] == "character.observed":
                state_key = (
                    str(projected.get("session_ref") or ""),
                    str(projected.get("client_ref") or ""),
                    str(projected["type"]),
                )
                state_fingerprint = hashlib.sha256(
                    _canonical_json(projected.get("payload") or {})
                ).digest()
                if self._last_remote_states.get(state_key) == state_fingerprint:
                    self._record_projected(projected["type"], False)
                    return
            queued = self.outbox.enqueue(projected)
            if state_key is not None and state_fingerprint is not None:
                self._last_remote_states.pop(state_key, None)
                self._last_remote_states[state_key] = state_fingerprint
                while len(self._last_remote_states) > MAX_REMOTE_STATE_CACHE:
                    self._last_remote_states.pop(next(iter(self._last_remote_states)))
            self._record_projected(projected["type"], queued)

    @staticmethod
    def _pending_event_size(event: dict[str, Any]) -> int:
        try:
            return min(MAX_EVENT_BYTES * 4, len(_canonical_json(event)))
        except (TypeError, ValueError, OverflowError):
            return 1024

    def _buffer_identity_event(
        self, session_id: str, connection: str, event: dict[str, Any],
    ) -> None:
        now_ns = _integer(event.get("ts_ns"), time.time_ns()) or time.time_ns()
        copied = dict(event)
        size = self._pending_event_size(copied)
        key = (session_id, connection)
        pending = self._pending_identity_events.setdefault(key, deque())
        pending.append((now_ns, copied, size))
        self._pending_identity_count += 1
        self._pending_identity_bytes += size
        self.identity_buffered += 1
        self._prune_pending(now_ns)

    def _prune_pending(self, now_ns: int) -> None:
        cutoff = max(0, int(now_ns) - IDENTITY_PENDING_MAX_AGE_NS)
        for key in tuple(self._pending_identity_events):
            pending = self._pending_identity_events[key]
            while pending and pending[0][0] < cutoff:
                _occurred_ns, _event, size = pending.popleft()
                self._pending_identity_count -= 1
                self._pending_identity_bytes -= size
                self.identity_expired += 1
            if not pending:
                self._pending_identity_events.pop(key, None)
        while (
            self._pending_identity_count > self._max_pending_identity_events
            or self._pending_identity_bytes > IDENTITY_PENDING_MAX_BYTES
        ):
            oldest_key = min(
                self._pending_identity_events,
                key=lambda item: self._pending_identity_events[item][0][0],
                default=None,
            )
            if oldest_key is None:
                break
            _occurred_ns, _event, size = self._pending_identity_events[oldest_key].popleft()
            self._pending_identity_count -= 1
            self._pending_identity_bytes -= size
            self.identity_expired += 1
            if not self._pending_identity_events[oldest_key]:
                self._pending_identity_events.pop(oldest_key, None)

    def _replay_pending(self, session_id: str, connection: str) -> None:
        pending = self._pending_identity_events.pop(
            (session_id, connection), deque()
        )
        while pending:
            _occurred_ns, event, size = pending.popleft()
            self._pending_identity_count -= 1
            self._pending_identity_bytes -= size
            try:
                for projected in self.projector.project_many(event, session_id):
                    self._route_projected(projected, confirmed=True, observe=False)
                    self.identity_replayed += 1
            except Exception as error:
                self.projector.invalidate_inventory_projection(event)
                self.errors += 1
                kind = str(event.get("type") or "identity_replay")[:96]
                with self._metrics_lock:
                    self.errors_by_type[kind] += 1
                    self.last_errors_by_type[kind] = (
                        f"{type(error).__name__}: {error}"
                    )[:240]

    def _discard_pending_session(self, session_id: str) -> None:
        for key in tuple(self._pending_identity_events):
            if key[0] != session_id:
                continue
            pending = self._pending_identity_events.pop(key)
            for _occurred_ns, _event, size in pending:
                self._pending_identity_count -= 1
                self._pending_identity_bytes -= size
                self.identity_expired += 1

    def _record_projected(self, event_type: str, queued: bool) -> None:
        self.projected += 1
        if queued:
            self.enqueued += 1
        else:
            self.duplicates += 1
        notifier = None
        with self._metrics_lock:
            self.projected_by_type[str(event_type)[:96]] += 1
            if queued:
                now_second = int(time.monotonic())
                if (
                    self._enqueued_rate_buckets
                    and self._enqueued_rate_buckets[-1][0] == now_second
                ):
                    second, count = self._enqueued_rate_buckets[-1]
                    self._enqueued_rate_buckets[-1] = (second, count + 1)
                else:
                    self._enqueued_rate_buckets.append((now_second, 1))
                while (
                    self._enqueued_rate_buckets
                    and self._enqueued_rate_buckets[0][0] < now_second - 59
                ):
                    self._enqueued_rate_buckets.popleft()
                notifier = self.delivery_notifier
        if notifier is not None:
            try:
                notifier()
            except Exception:
                with self._metrics_lock:
                    self.delivery_notify_errors += 1

    def record_direct_enqueue(self, event_type: str, queued: bool) -> None:
        """Registra eventos criados fora da fila do decoder, como heartbeat."""
        self._record_projected(event_type, queued)

    def _record_local_only(self, event_type: str) -> None:
        self.projected += 1
        self.local_only += 1
        normalized = str(event_type)[:96]
        with self._metrics_lock:
            self.projected_by_type[normalized] += 1
            self.local_only_by_type[normalized] += 1

    def _record_unconfirmed(self, event_type: str) -> None:
        """Mantém o evento na API local, sem criar pendência remota órfã."""
        self.projected += 1
        self.skipped += 1
        self.unconfirmed += 1
        normalized = str(event_type)[:96]
        with self._metrics_lock:
            self.projected_by_type[normalized] += 1
            self.skipped_by_type[normalized] += 1
            self.unconfirmed_by_type[normalized] += 1

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

    @staticmethod
    def _bounded_counts(values: Counter[str]) -> dict[str, int]:
        return {
            name: int(count)
            for name, count in values.most_common(64)
            if name
        }

    def metrics(self) -> dict[str, object]:
        with self._metrics_lock:
            now_second = int(time.monotonic())
            while (
                self._enqueued_rate_buckets
                and self._enqueued_rate_buckets[0][0] < now_second - 59
            ):
                self._enqueued_rate_buckets.popleft()
            by_type = {
                "accepted_by_type": self._bounded_counts(self.accepted_by_type),
                "ignored_by_type": self._bounded_counts(self.ignored_by_type),
                "projected_by_type": self._bounded_counts(self.projected_by_type),
                "skipped_by_type": self._bounded_counts(self.skipped_by_type),
                "local_only_by_type": self._bounded_counts(
                    self.local_only_by_type
                ),
                "unconfirmed_by_type": self._bounded_counts(
                    self.unconfirmed_by_type
                ),
                "errors_by_type": self._bounded_counts(self.errors_by_type),
                "last_errors_by_type": dict(self.last_errors_by_type),
                "ranking_diagnostics": self.projector.ranking_diagnostics(),
                "identity": {
                    **(
                        self.projector.character_history.metrics()
                        if self.projector.character_history is not None else {}
                    ),
                    "buffered_events": self._pending_identity_count,
                    "buffered_bytes": self._pending_identity_bytes,
                    "buffered_total": self.identity_buffered,
                    "replayed_total": self.identity_replayed,
                    "expired_total": self.identity_expired,
                },
            }
        return {
            "queue_depth": self._queue.qsize(),
            "queue_limit": self._queue.maxsize,
            "accepted": self.accepted,
            "ignored": self.ignored,
            "dropped": self.dropped,
            "errors": self.errors,
            "observer_errors": self.observer_errors,
            "delivery_notify_errors": self.delivery_notify_errors,
            "projected": self.projected,
            "skipped": self.skipped,
            "local_only": self.local_only,
            "unconfirmed": self.unconfirmed,
            "enqueued": self.enqueued,
            "duplicates": self.duplicates,
            "enqueued_events_last_minute": sum(
                count for _second, count in self._enqueued_rate_buckets
            ),
            "worker_alive": bool(self._thread and self._thread.is_alive()),
            **by_type,
            **{f"outbox_{key}": value for key, value in self.outbox.metrics().items()},
        }

    def close(self) -> None:
        self.wait_until_idle()
        self._stop.set()
        try:
            self._queue.put_nowait((
                PROCESSING_PRIORITY_BOSS,
                next(self._queue_sequence),
                None,
                None,
            ))
        except queue.Full:
            pass
        if self._thread:
            self._thread.join(timeout=3)
        if self.projector.character_history is not None:
            self.projector.character_history.close()
        self.outbox.close()
