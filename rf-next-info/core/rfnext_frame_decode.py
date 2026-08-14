#!/usr/bin/env python3
"""Decode RF Online NEXT application frames recovered from libUnreal.so 1.28.5."""

from __future__ import annotations

import argparse
import base64
import binascii
import collections
import csv
import hashlib
import json
import socket
import struct
import sys
from pathlib import Path
from typing import Any


MAX_FRAME = 0xFFFF
HEADER_SIZE = 6
APPEAR_PLAYER_PREFIX = struct.Struct("<QBIBIBH")
APPEAR_PLAYER_STATE = struct.Struct("<IBQQIIBfff")
APPEAR_PLAYER_TAIL_SIZE = 162
APPEAR_UNIT = struct.Struct("<IIQIQQfffBfBfffBIIQ")
RESTORE_HP_FP = struct.Struct("<IQQQIIIB")
DROP_RESULT = struct.Struct("<HIqqqH")
USE_SKILL_PREFIX = struct.Struct("<HBIIIBffffffIfffqIIH")
SKILL_EFFECT_RESULT = struct.Struct("<IffffffBqqqIIBI")
NORMAL_SKILL_PREFIX = struct.Struct("<HBIfffIIIBqH")
NORMAL_SKILL_EFFECT_RESULT = struct.Struct("<IfffBqqqBI")
STACKABLE_INVENTORY_ITEM = struct.Struct("<H6sIQBQ")
USE_SKILL_REQUEST = struct.Struct("<III")
SELECT_TARGET_REQUEST = struct.Struct("<I")
ACTION_CODES = {
    960: "ACTION_CODE_KILLED_NPC",
    1000: "ACTION_CODE_FIELDDROP",
    1001: "ACTION_CODE_MODE_REWARD",
    1002: "ACTION_CODE_FIRST_HIT_REWARD",
    1003: "ACTION_CODE_LAST_HIT_REWARD",
    1004: "ACTION_CODE_FIELDDROP_TEST",
    1005: "ACTION_CODE_EXP_BY_FINISH_SKILL",
    1006: "ACTION_CODE_EXP_BY_FINISH_ONEKILL",
}
REALMS = {
    13: "REALM_MONSTER",
    14: "REALM_NEUTRAL",
    15: "REALM_ALIEN",
}
FIELD_MONSTER_FLAG_BITS = {
    0: "FIELD_MONSTER_FLAG_ACTIVATING",
    1: "FIELD_MONSTER_FLAG_ACTIVATE",
    2: "FIELD_MONSTER_FLAG_REGEN",
    3: "FIELD_MONSTER_FLAG_COMBAT",
    4: "FIELD_MONSTER_FLAG_ALIVE",
    5: "FIELD_MONSTER_FLAG_SKILL_EFFECT",
}
DISAPPEAR_REASONS = {
    1: "death",
    2: "random_teleport",
}


# ---------------------------------------------------------------------------
# Job 1: decodificador dirigido por tabela (opcodes recuperados do libUnreal.so)
# ---------------------------------------------------------------------------
# LAYOUTS e RECORD_FMT sao construidos no import a partir de:
#   - job1_pending_layouts.json  (cabecalho/corpo: fmt struct do wire, size, fields)
#   - job1_all_opcodes.csv       (direcao FL2C/FG2C/... por classe)
#   - RECORD_FMT_DOC abaixo: struct do REGISTRO de cada lista, transcrito da coluna
#     "Registro de lista" de RFNext-Job1-Protocolo-Layouts.md (artefato Job 1).
# Nada aqui e inventado: fmt/size vem do JSON; o registro vem do doc; o CONTADOR
# nao esta confirmado no binario, entao a contagem da lista e derivada por
# comprimento (rem % record_size == 0) e cruzada com o 1o campo do cabecalho.
# Confianca marcada em cada saida.

# opcode_int -> (record_fmt, record_size). Fonte: RFNext-Job1-Protocolo-Layouts.md.
RECORD_FMT_DOC: dict[int, str] = {
    0x031C: "<IIIIIQQBB",   # notify_boss_status_list      -> boss_status (38 B)
    0x0331: "<IIIIBB",      # notify_random_boss_status_list (18 B)
    0x0C05: "<IQQQIB",      # noti_worldboss_result        (33 B)
    0x0C0A: "<IQQQIB",      # ans_worldboss_top_players    (33 B)
    0x0C14: "<QBIHQ",       # party_dungeon_result         (23 B)
    0x0534: "<IBQQBBI",     # restore_schedule_list        (27 B)
    0x1816: "<IIIIIQQBB",   # ans_event_mother_ship_status_list (38 B)
    0x2301: "<IBBBBBBBBBBBBBBBB",  # exploration_map_complete_info (20 B)
}

LAYOUTS: dict[int, dict[str, Any]] = {}


def _job1_candidate_paths(filename: str) -> list[Path]:
    here = Path(__file__).resolve().parent
    return [
        here / filename,
        here / "job1" / filename,
        here / "job1" / "job1" / filename,
        here.parent.parent
        / "rf-next"
        / "analysis"
        / "1.28.5"
        / "job1"
        / filename,
    ]


def _load_directions() -> dict[str, str]:
    for path in _job1_candidate_paths("job1_all_opcodes.csv"):
        if not path.exists():
            continue
        directions: dict[str, str] = {}
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    name = (row.get("class") or "").strip()
                    direction = (row.get("direction") or "").strip()
                    if name:
                        directions[name] = direction
            return directions
        except (OSError, csv.Error):
            return {}
    return {}


def _load_layouts() -> dict[int, dict[str, Any]]:
    """Constroi a tabela LAYOUTS no import. Robusta a arquivo ausente (tabela vazia)."""
    layouts: dict[int, dict[str, Any]] = {}
    json_path = next((p for p in _job1_candidate_paths("job1_pending_layouts.json") if p.exists()), None)
    if json_path is None:
        return layouts
    try:
        groups = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return layouts
    directions = _load_directions()
    for items in groups.values():
        for item in items:
            opcode = item.get("opcode")
            fmt = item.get("fmt")
            size = item.get("size")
            name = item.get("name")
            if opcode is None or fmt is None or size is None:
                continue
            try:
                opcode_int = int(opcode, 16) if isinstance(opcode, str) else int(opcode)
            except (TypeError, ValueError):
                continue
            # valida struct e casamento fmt<->size (sinal forte de layout correto)
            try:
                if struct.calcsize(fmt) != size:
                    continue
            except struct.error:
                continue
            fields = item.get("fields") or []
            record_fmt = RECORD_FMT_DOC.get(opcode_int)
            try:
                record_size = struct.calcsize(record_fmt) if record_fmt else None
            except struct.error:
                record_fmt, record_size = None, None
            layouts[opcode_int] = {
                "name": name,
                "fmt": fmt,
                "size": size,
                "fields": fields,
                "direction": directions.get(name),
                "record_fmt": record_fmt,
                "record_size": record_size,
            }
    return layouts


try:
    LAYOUTS = _load_layouts()
except Exception:  # nunca deixar o import falhar por causa do Job 1
    LAYOUTS = {}


def _name_header_fields(entry: dict[str, Any], values: tuple) -> dict[str, Any]:
    """Nomeia cada campo do cabecalho por indice + offset da struct (ex. f0@0x8)."""
    fields = entry.get("fields") or []
    named: dict[str, Any] = {}
    for index, value in enumerate(values):
        if index < len(fields):
            offset = fields[index][0]
            key = f"f{index}@{offset}"
        else:
            key = f"f{index}"
        named[key] = value
    return named


def parse_job1_payload(decoded: bytes) -> dict[str, Any] | None:
    """Decoder de fallback dirigido pela tabela LAYOUTS (opcodes do Job 1).

    Retorna None se o opcode nao estiver na tabela ou o tamanho nao casar
    (deixa o frame bruto). Casamento de tamanho == sinal forte de layout correto.
    """
    opcode = int.from_bytes(decoded[4:6], "little")
    entry = LAYOUTS.get(opcode)
    if entry is None:
        return None
    payload = decoded[HEADER_SIZE:]
    fmt = entry["fmt"]
    size = entry["size"]
    hex_opcode = f"0x{opcode:04x}"

    # Corpo exato: mensagem simples (ou lista vazia = so cabecalho).
    if len(payload) == size:
        result: dict[str, Any] = {
            "type": entry["name"],
            "opcode": hex_opcode,
            "direction": entry.get("direction"),
            "confidence": "layout-job1",
            "fields": _name_header_fields(entry, struct.unpack(fmt, payload)),
        }
        if entry.get("record_fmt"):
            result["records"] = []
            result["list"] = "vazia"
        return result

    # Lista: cabecalho (size) + N registros. Registro vem do doc (RECORD_FMT_DOC).
    record_fmt = entry.get("record_fmt")
    record_size = entry.get("record_size")
    if record_fmt and record_size and len(payload) > size:
        result = {
            "type": entry["name"],
            "opcode": hex_opcode,
            "direction": entry.get("direction"),
            "size_layout": size,
            "size_wire": len(payload),
        }
        remainder = len(payload) - size
        if remainder % record_size == 0:
            # cabecalho do JSON + N registros do doc casam byte-a-byte com o wire:
            # sinal forte de framing correto -> decodifica registros.
            header_values = struct.unpack(fmt, payload[:size])
            count = remainder // record_size
            records = [
                {
                    f"r{j}": v
                    for j, v in enumerate(
                        struct.unpack(
                            record_fmt,
                            payload[size + i * record_size : size + (i + 1) * record_size],
                        )
                    )
                }
                for i in range(count)
            ]
            result["fields"] = _name_header_fields(entry, header_values)
            result["records"] = records
            result["count_derived"] = count
            # 1o campo do cabecalho e o candidato a contador (convencao RF, nao confirmado)
            result["count_header_f0"] = header_values[0] if header_values else None
            result["confidence"] = "layout-job1-list"
            result["record_fmt"] = record_fmt
            result["list_note"] = "registro do doc; contagem por comprimento (contador nao confirmado)"
        else:
            # (len - size) nao divide pelo registro: o framing do wire nao bate com
            # o layout estatico (size do Job1 e a struct C++, nao necessariamente o
            # wire). Nao afirmamos valores de campo aqui; so sinalizamos presenca +
            # divergencia para o orquestrador. NAO inventamos header/registro.
            result["confidence"] = "layout-job1-size-mismatch"
            result["list"] = "registro_pendente"
            result["list_note"] = (
                "wire nao casa com header_size + N*record_size; layout Job1 provavelmente "
                "e a struct C++, nao o framing do wire (confirmar em captura)"
            )
        return result

    return None


class DecodeError(ValueError):
    pass


def frame_length_from_wire(header: bytes) -> int:
    if len(header) < 3:
        raise DecodeError("truncated frame header")
    if not header[0] & 0x80:
        return int.from_bytes(header[1:3], "little")
    state = header[0] ^ 0xEF
    length_lo = header[1] ^ state
    state = header[1] ^ 0xEF
    length_hi = header[2] ^ state
    return length_lo | (length_hi << 8)


def remove_rolling_xor(frame: bytes) -> bytes:
    data = bytearray(frame)
    if not data or not data[0] & 0x80:
        return bytes(data)
    state = data[0] ^ 0xEF
    for index in range(1, len(data)):
        cipher = data[index]
        data[index] = cipher ^ state
        state = cipher ^ ((-0x11 * index) & 0xFF)
    data[0] &= 0x7F
    return bytes(data)


def apply_rolling_xor(frame: bytes, seed: int = 0x15) -> bytes:
    """Inverse used only by the self-test; seed is the wire header low 6 bits."""
    if not 0 <= seed <= 0x3F:
        raise ValueError("seed must fit in 6 bits")
    data = bytearray(frame)
    data[0] = 0x80 | seed
    state = data[0] ^ 0xEF
    for index in range(1, len(data)):
        plain = data[index]
        data[index] = plain ^ state
        state = data[index] ^ ((-0x11 * index) & 0xFF)
    return bytes(data)


def lz4_block_decompress(source: bytes, capacity: int = MAX_FRAME - HEADER_SIZE) -> bytes:
    output = bytearray()
    cursor = 0

    def extended_length(initial: int) -> int:
        nonlocal cursor
        length = initial
        if initial != 0x0F:
            return length
        while True:
            if cursor >= len(source):
                raise DecodeError("truncated LZ4 length")
            value = source[cursor]
            cursor += 1
            length += value
            if value != 0xFF:
                return length

    while cursor < len(source):
        token = source[cursor]
        cursor += 1
        literal_length = extended_length(token >> 4)
        literal_end = cursor + literal_length
        if literal_end > len(source):
            raise DecodeError("truncated LZ4 literals")
        if len(output) + literal_length > capacity:
            raise DecodeError("LZ4 output exceeds frame capacity")
        output.extend(source[cursor:literal_end])
        cursor = literal_end
        if cursor == len(source):
            break
        if cursor + 2 > len(source):
            raise DecodeError("truncated LZ4 match offset")
        offset = source[cursor] | (source[cursor + 1] << 8)
        cursor += 2
        if offset == 0 or offset > len(output):
            raise DecodeError("invalid LZ4 match offset")
        match_length = extended_length(token & 0x0F) + 4
        if len(output) + match_length > capacity:
            raise DecodeError("LZ4 output exceeds frame capacity")
        match_cursor = len(output) - offset
        for _ in range(match_length):
            output.append(output[match_cursor])
            match_cursor += 1
    return bytes(output)


def decode_frame(wire_frame: bytes) -> tuple[bytes, dict[str, int | bool]]:
    if len(wire_frame) < HEADER_SIZE:
        raise DecodeError("frame shorter than 6-byte header")
    declared_length = frame_length_from_wire(wire_frame[:3])
    if declared_length != len(wire_frame):
        raise DecodeError(
            f"declared length {declared_length} differs from supplied length {len(wire_frame)}"
        )
    was_obfuscated = bool(wire_frame[0] & 0x80)
    decoded = bytearray(remove_rolling_xor(wire_frame))
    was_compressed = bool(decoded[0] & 0x40)
    if was_compressed:
        body = lz4_block_decompress(bytes(decoded[HEADER_SIZE:]))
        decoded = decoded[:HEADER_SIZE] + body
        decoded[0] &= 0xBF
        decoded[1:3] = len(decoded).to_bytes(2, "little")
    opcode = int.from_bytes(decoded[4:6], "little")
    info: dict[str, int | bool] = {
        "wire_length": len(wire_frame),
        "decoded_length": len(decoded),
        "obfuscated": was_obfuscated,
        "compressed": was_compressed,
        "sequence": decoded[3],
        "opcode": opcode,
        "opcode_group": opcode >> 8,
        "opcode_id": opcode & 0xFF,
        "payload_length": len(decoded) - HEADER_SIZE,
    }
    return bytes(decoded), info


LOGIN_SESSION_MESSAGES = {
    0x0101: ("ask_connection", "FC2A_ask_connection_Message", "FC2A", True),
    0x0102: ("ans_connection", "FA2C_ans_connection_Message", "FA2C", True),
    0x0103: ("ask_ping", "FC2A_ask_ping_Message", "FC2A", False),
    0x0104: ("ans_ping", "FA2C_ans_ping_Message", "FA2C", False),
    0x0105: ("ask_world_info", "FC2A_ask_world_info_Message", "FC2A", False),
    0x0106: ("ans_world_info", "FA2C_ans_world_info_Message", "FA2C", False),
    0x0107: ("ask_enter_game", "FC2A_ask_enter_game_Message", "FC2A", True),
    0x0108: ("ans_enter_game", "FA2C_ans_enter_game_Message", "FA2C", True),
    0x010B: ("game_sequence", "FA2C_game_sequence_Message", "FA2C", False),
    0x010C: (
        "ask_all_character_infos",
        "FC2A_ask_all_character_infos_Message",
        "FC2A",
        True,
    ),
    0x010D: (
        "ans_all_character_infos",
        "FA2C_ans_all_character_infos_Message",
        "FA2C",
        True,
    ),
}


def _read_utf16le_u16(payload: bytes, cursor: int, field: str) -> tuple[str, int]:
    if cursor + 2 > len(payload):
        raise DecodeError(f"truncated {field} length at payload offset {cursor}")
    length = struct.unpack_from("<H", payload, cursor)[0]
    cursor += 2
    end = cursor + length * 2
    if end > len(payload):
        raise DecodeError(f"truncated {field} with {length} UTF-16 characters")
    try:
        return payload[cursor:end].decode("utf-16le"), end
    except UnicodeDecodeError as exc:
        raise DecodeError(f"invalid UTF-16 in {field}") from exc


def _decode_jwt_without_verification(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise DecodeError("auth token is not a three-part JWT")

    def decode_part(value: str) -> Any:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return json.loads(raw)

    return {
        "header": decode_part(parts[0]),
        "claims": decode_part(parts[1]),
        "verified": False,
    }


def parse_login_session_payload(decoded: bytes, port: int) -> dict[str, Any] | None:
    """Decode observed account/session fields; never copies opaque raw payload."""
    if port != 12000 or len(decoded) < HEADER_SIZE:
        return None
    opcode = int.from_bytes(decoded[4:6], "little")
    entry = LOGIN_SESSION_MESSAGES.get(opcode)
    if entry is None:
        return None
    type_name, message, direction, sensitive = entry
    result: dict[str, Any] = {
        "type": type_name,
        "opcode": f"0x{opcode:04x}",
        "message": message,
        "direction": direction,
        "confidence": "catalogo-estatico+4-capturas-1.28.5",
        "payload_length": len(decoded) - HEADER_SIZE,
        "sensitive_payload": sensitive,
    }
    payload = decoded[HEADER_SIZE:]
    try:
        if opcode == 0x0101:
            cursor = 0
            account_id, cursor = _read_utf16le_u16(payload, cursor, "account_id")
            (connection_mode,) = struct.unpack_from("<H", payload, cursor)
            cursor += 2
            country_code, cursor = _read_utf16le_u16(payload, cursor, "country_code")
            device_json, cursor = _read_utf16le_u16(payload, cursor, "device_info")
            auth_jwt, cursor = _read_utf16le_u16(payload, cursor, "auth_jwt")
            auth_host, cursor = _read_utf16le_u16(payload, cursor, "auth_host")
            session_key, cursor = _read_utf16le_u16(payload, cursor, "session_key")
            joined_country, cursor = _read_utf16le_u16(
                payload, cursor, "joined_country_code"
            )
            tail_flag, tail_value, tail_reserved = struct.unpack_from(
                "<BIH", payload, cursor
            )
            cursor += 7
            mac_address, cursor = _read_utf16le_u16(payload, cursor, "mac_address")
            if cursor != len(payload):
                raise DecodeError(f"0x0101 has {len(payload) - cursor} trailing bytes")
            result["fields"] = {
                "account_id": account_id,
                "connection_mode": connection_mode,
                "country_code": country_code,
                "device_info": json.loads(device_json),
                # Claims are decoded for analysis, but the signed bearer token and
                # signature stay out of JSON output.
                "auth_jwt": _decode_jwt_without_verification(auth_jwt),
                "auth_jwt_length": len(auth_jwt),
                "auth_host": auth_host,
                "session_key_present": bool(session_key),
                "session_key_length": len(session_key),
                "joined_country_code": joined_country,
                "tail_flag": tail_flag,
                "tail_value": tail_value,
                "tail_reserved": tail_reserved,
                "mac_address": mac_address,
            }
        elif opcode == 0x0102 and len(payload) == 79:
            country_code, cursor = _read_utf16le_u16(payload, 36, "country_code")
            joined_country, cursor = _read_utf16le_u16(
                payload, cursor, "joined_country_code"
            )
            result["fields"] = {
                "result_code@0": struct.unpack_from("<H", payload, 0)[0],
                "server_time_ms@2": struct.unpack_from("<Q", payload, 2)[0],
                "heartbeat_interval_ms@10": struct.unpack_from("<I", payload, 10)[0],
                "f14_16_hex": payload[14:17].hex(),
                "timestamp_b_ms@17": struct.unpack_from("<Q", payload, 17)[0],
                "f25@25": payload[25],
                "f26_35_hex": payload[26:36].hex(),
                "country_code@36": country_code,
                "joined_country_code@42": joined_country,
                "tail_hex@48": payload[cursor:].hex(),
            }
        elif opcode == 0x0107 and len(payload) == 2:
            result["fields"] = {"world_id": struct.unpack("<H", payload)[0]}
        elif opcode == 0x0108:
            if len(payload) < 20:
                raise DecodeError("0x0108 payload is too short")
            ret, world_id, f4, f6, f14 = struct.unpack_from("<HHHQH", payload, 0)
            game_server_host, cursor = _read_utf16le_u16(
                payload, 16, "game_server_host"
            )
            (game_server_port,) = struct.unpack_from("<H", payload, cursor)
            cursor += 2
            if cursor != len(payload):
                raise DecodeError(f"0x0108 has {len(payload) - cursor} trailing bytes")
            result["fields"] = {
                "result_code@0": ret,
                "world_id@2": world_id,
                "f4@4": f4,
                "f6@6": f6,
                "f14@14": f14,
                "game_server_host": game_server_host,
                "game_server_port": game_server_port,
            }
        elif opcode == 0x010C:
            account_id, cursor = _read_utf16le_u16(payload, 0, "account_id")
            if cursor != len(payload):
                raise DecodeError(f"0x010c has {len(payload) - cursor} trailing bytes")
            result["fields"] = {"account_id": account_id}
        elif opcode == 0x010D:
            (character_count,) = struct.unpack_from("<H", payload, 0)
            cursor = 2
            characters = []
            for _ in range(character_count):
                character_uid, level = struct.unpack_from("<QH", payload, cursor)
                cursor += 10
                name, cursor = _read_utf16le_u16(payload, cursor, "character_name")
                (world_id,) = struct.unpack_from("<H", payload, cursor)
                cursor += 2
                reserved = payload[cursor : cursor + 12]
                cursor += 12
                timestamp_a, timestamp_b, f60 = struct.unpack_from(
                    "<QQQ", payload, cursor
                )
                cursor += 24
                guild_name, cursor = _read_utf16le_u16(
                    payload, cursor, "guild_name"
                )
                f80, f82 = struct.unpack_from("<HH", payload, cursor)
                cursor += 4
                characters.append(
                    {
                        "character_uid": character_uid,
                        "level": level,
                        "name": name,
                        "world_id": world_id,
                        "reserved_hex": reserved.hex(),
                        "timestamp_a_ms": timestamp_a,
                        "timestamp_b_ms": timestamp_b,
                        "f60": f60,
                        "guild_name": guild_name,
                        "f80": f80,
                        "f82": f82,
                    }
                )
            if cursor != len(payload):
                raise DecodeError(f"0x010d has {len(payload) - cursor} trailing bytes")
            result["fields"] = {
                "character_count": character_count,
                "characters": characters,
            }
    except (DecodeError, ValueError, struct.error, binascii.Error) as exc:
        result["field_decode"] = "layout-mismatch"
        result["field_decode_error"] = str(exc)
    if "fields" in result:
        result["field_decode"] = "captura-4x-layout-exato"
    return result


SALVAGE_ITEM = struct.Struct("<QIQ")
EQUIPMENT_PART_NAMES = (
    "weapon",
    "neck_guard",
    "chest_guard",
    "lower_guard",
    "arm_guards",
    "leg_guards",
    "ear_cuffs",
    "necklace",
    "bangles",
    "ring",
    "dimension_cube",
    "psionic_capsule",
    "quantum_disk",
    "hyper_sensor",
    "drive",
    "circlet",
    "stargazer",
    "deflector",
)


def parse_marked_gameplay_payload(decoded: bytes, port: int) -> dict[str, Any] | None:
    """Layouts fechados pela captura marcada de 2026-07-26."""
    if len(decoded) < HEADER_SIZE:
        return None
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]

    if port == 12010:
        if opcode == 0x0204 and len(payload) == 13:
            character_uid, entity_uid, result_raw = struct.unpack("<QIB", payload)
            return {
                "type": "exit_room_result",
                "message": "FG2C_ans_exitroom_Message",
                "direction": "FG2C",
                "confidence": "alto-layout-exato-captura-marcada-2026-08-14",
                "fields": {
                    "character_uid": character_uid,
                    "entity_uid": entity_uid,
                    "result_raw": result_raw,
                },
            }
        if opcode in (0x0301, 0x0302):
            expected_size = 34 if opcode == 0x0301 else 36
            if len(payload) != expected_size:
                return None
            offset = 0 if opcode == 0x0301 else 4
            fields = {
                "state_a_raw": payload[offset],
                "state_b_raw": payload[offset + 1],
                "movement_flags_raw": payload[offset + 2],
                "moving_flag": bool(payload[offset + 2] & 0x40),
                "movement_vector": list(struct.unpack_from("<fff", payload, offset + 3)),
                "position": list(struct.unpack_from("<fff", payload, offset + 15)),
                "client_tick_raw": struct.unpack_from("<I", payload, offset + 27)[0],
                "reserved_tail_hex": payload[offset + 31:].hex(),
            }
            if opcode == 0x0302:
                fields["entity_uid"] = struct.unpack_from("<I", payload)[0]
            return {
                "type": "move_player_request" if opcode == 0x0301 else "move_player_update",
                "message": (
                    "FC2G_ask_move_player_Message"
                    if opcode == 0x0301
                    else "FG2C_ans_move_player_Message"
                ),
                "direction": "FC2G" if opcode == 0x0301 else "FG2C",
                "confidence": "alto-518-movimentos-captura-marcada-2026-08-14",
                "fields": fields,
            }
        if opcode == 0x030A and len(payload) >= 2:
            count = struct.unpack_from("<H", payload)[0]
            if len(payload) != 2 + count * 5:
                return None
            units = []
            for index in range(count):
                reason_raw = payload[2 + index * 5 + 4]
                unit = {
                    "entity_uid": struct.unpack_from("<I", payload, 2 + index * 5)[0],
                    "reason_raw": reason_raw,
                }
                if reason_raw in DISAPPEAR_REASONS:
                    unit["reason"] = DISAPPEAR_REASONS[reason_raw]
                    unit["reason_confidence"] = "alto-captura-marcada-2026-08-14"
                units.append(unit)
            return {
                "type": "disappear_unit_list",
                "message": "FG2C_disappear_unit_list_Message",
                "direction": "FG2C",
                "confidence": "alto-layout-exato-388-frames+5-saidas-uid-alvo",
                "fields": {
                    "count": count,
                    "units": units,
                    "entity_uids": [unit["entity_uid"] for unit in units],
                    "visibility_event": "disappear",
                },
            }
        if opcode == 0x0408 and len(payload) == 4:
            return {
                "type": "request_teleport",
                "message": "FC2G_ask_request_teleport_Message",
                "direction": "FC2G",
                "confidence": "alto-7-ciclos-2-marcados",
                "fields": {"teleport_index": struct.unpack("<I", payload)[0]},
            }
        if opcode == 0x0409 and len(payload) == 6:
            result, teleport_index = struct.unpack("<HI", payload)
            return {
                "type": "request_teleport_result",
                "message": "FG2C_ans_request_teleport_Message",
                "direction": "FG2C",
                "confidence": "alto-7-ciclos-2-marcados",
                "fields": {"result": result, "teleport_index": teleport_index},
            }
        if opcode == 0x040A and len(payload) == 24:
            entity_uid, x, y, z, f16_u16_raw, map_index_candidate, f22_u16_raw = (
                struct.unpack("<IfffHIH", payload)
            )
            return {
                "type": "warp_player",
                "message": "FG2C_warp_player_Message",
                "direction": "FG2C",
                "confidence": "alto-9-warps-7-locais-2-entidade-proxima",
                "fields": {
                    "entity_uid": entity_uid,
                    "position": [x, y, z],
                    "f16_u16_raw": f16_u16_raw,
                    "map_index_candidate": map_index_candidate,
                    "f22_u16_raw": f22_u16_raw,
                },
            }
        if opcode == 0x040B and not payload:
            return {
                "type": "end_warp_player",
                "message": "FC2G_end_warp_player_Message",
                "direction": "FC2G",
                "confidence": "alto-7-ciclos-2-marcados",
                "fields": {},
            }
        if opcode == 0x0407 and len(payload) == 75:
            return {
                "type": "player_equip_update",
                "message": "FG2C_update_player_equip_info_Message",
                "direction": "FG2C",
                "confidence": "alto-7-trocas-marcadas-2-personagens",
                "fields": {
                    "character_uid": struct.unpack_from("<Q", payload, 0)[0],
                    "rover_item_index": struct.unpack_from("<I", payload, 18)[0],
                },
            }
        return None
    if port != 12020:
        return None

    if opcode == 0x0501 and len(payload) == 11:
        preset_raw, equipment_slot, item_uid = struct.unpack("<HBQ", payload)
        return {
            "type": "change_equip_slot_request",
            "message": "FC2L_ask_change_equip_slot_Message",
            "direction": "FC2L",
            "confidence": "alto-4-mudancas-marcadas-2-slots",
            "fields": {
                "preset_raw": preset_raw,
                "equipment_slot": equipment_slot,
                "equipment_part": (
                    EQUIPMENT_PART_NAMES[equipment_slot - 1]
                    if 1 <= equipment_slot <= len(EQUIPMENT_PART_NAMES)
                    else None
                ),
                "item_uid": item_uid,
            },
        }
    if opcode == 0x0502 and len(payload) == 15:
        result, f2_u16_raw, preset_raw, equipment_slot, item_uid = struct.unpack(
            "<HHHBQ", payload
        )
        return {
            "type": "change_equip_slot_response",
            "message": "FL2C_ans_change_equip_slot_Message",
            "direction": "FL2C",
            "confidence": "alto-4-mudancas-marcadas-2-slots",
            "fields": {
                "result": result,
                "f2_u16_raw": f2_u16_raw,
                "preset_raw": preset_raw,
                "equipment_slot": equipment_slot,
                "equipment_part": (
                    EQUIPMENT_PART_NAMES[equipment_slot - 1]
                    if 1 <= equipment_slot <= len(EQUIPMENT_PART_NAMES)
                    else None
                ),
                "item_uid": item_uid,
            },
        }

    if opcode == 0x1303 and len(payload) == 4:
        return {
            "type": "change_biosuit_request",
            "message": "FC2L_ask_change_biosuit_Message",
            "direction": "FC2L",
            "confidence": "alto-3-trocas-marcadas-1-personagem",
            "fields": {
                "biosuit_item_index": struct.unpack("<I", payload)[0],
            },
        }
    if opcode == 0x1304 and len(payload) == 15:
        result, biosuit_item_index, f6_u64_raw, f14_u8_raw = struct.unpack(
            "<HIQB", payload
        )
        return {
            "type": "change_biosuit_response",
            "message": "FL2C_ans_change_biosuit_Message",
            "direction": "FL2C",
            "confidence": "alto-3-trocas-marcadas-1-personagem",
            "fields": {
                "result": result,
                "biosuit_item_index": biosuit_item_index,
                "f6_u64_raw": f6_u64_raw,
                "f14_u8_raw": f14_u8_raw,
            },
        }

    if opcode == 0x1402 and len(payload) == 4:
        return {
            "type": "change_rover_request",
            "message": "FC2L_ask_change_rover_Message",
            "direction": "FC2L",
            "confidence": "alto-7-trocas-marcadas-2-personagens",
            "fields": {
                "rover_item_index": struct.unpack("<I", payload)[0],
            },
        }
    if opcode == 0x1403 and len(payload) == 7:
        result, rover_item_index, trailing_state_raw = struct.unpack(
            "<HIB", payload
        )
        return {
            "type": "change_rover_response",
            "message": "FL2C_ans_change_rover_Message",
            "direction": "FL2C",
            "confidence": "alto-7-trocas-marcadas-2-personagens",
            "fields": {
                "result": result,
                "rover_item_index": rover_item_index,
                "trailing_state_raw": trailing_state_raw,
            },
        }

    if opcode == 0x0106 and len(payload) >= 16:
        result, f2, character_uid, level, name_length = struct.unpack_from(
            "<HHQHH", payload
        )
        name_end = 16 + name_length * 2
        if name_end > len(payload):
            return None
        try:
            character_name = payload[16:name_end].decode("utf-16le")
        except UnicodeDecodeError:
            return None
        biosuit_item_index = (
            struct.unpack_from("<I", payload, name_end + 1)[0]
            if name_end + 5 <= len(payload)
            else None
        )
        return {
            "type": "world_info_prefix",
            "message": "FA2C_ans_world_info_Message",
            "confidence": "alto-prefixo-2-sessoes",
            "fields": {
                "result": result,
                "f2": f2,
                "character_uid": character_uid,
                "level": level,
                "character_name": character_name,
                "biosuit_item_index": biosuit_item_index,
                "remaining_payload_length": len(payload) - name_end,
            },
        }

    if opcode == 0x0305 and len(payload) >= 10:
        character_uid, name_length = struct.unpack_from("<QH", payload)
        name_end = 10 + name_length * 2
        if name_end + 46 > len(payload):
            return None
        try:
            character_name = payload[10:name_end].decode("utf-16le")
        except UnicodeDecodeError:
            return None
        equipment_fields = {}
        equipment_tail = len(payload) - name_end - 46
        if equipment_tail in (988, 996):
            refs_offset = len(payload) - 195 - (equipment_tail - 988)
            biosuit_offset = refs_offset - 10
            equipment_prefix = payload[biosuit_offset + 4:refs_offset]
            equipment_refs = []
            for equip_part_type, equip_part in enumerate(EQUIPMENT_PART_NAMES, 1):
                ref_offset = refs_offset + (equip_part_type - 1) * 8
                inventory_slot = struct.unpack_from("<H", payload, ref_offset)[0]
                item_uid_raw = payload[ref_offset + 2:ref_offset + 8]
                equipment_refs.append(
                    {
                        "equip_part_type": equip_part_type,
                        "equip_part": equip_part,
                        "inventory_slot": inventory_slot,
                        "item_uid": int.from_bytes(item_uid_raw, "little"),
                        "item_uid_hex": item_uid_raw.hex(),
                    }
                )
            equipment_fields = {
                "biosuit_item_index": struct.unpack_from("<I", payload, biosuit_offset)[0],
                "rover_item_index": struct.unpack_from("<I", equipment_prefix, 1)[0],
                "equipment_prefix_raw": equipment_prefix.hex(),
                "equipment_refs": equipment_refs,
                "equipment_suffix_raw": payload[refs_offset + 144:].hex(),
            }
        return {
            "type": "appear_player_prefix",
            "message": "FG2C_appear_player_list_Message",
            "confidence": "alto-prefixo-2-sessoes",
            "fields": {
                "character_uid": character_uid,
                "character_name": character_name,
                "level": struct.unpack_from("<H", payload, name_end)[0],
                "diamonds": struct.unpack_from("<Q", payload, name_end + 38)[0],
                "remaining_payload_length": len(payload) - name_end - 46,
                **equipment_fields,
            },
        }

    if opcode == 0x0403:
        return _parse_player_profile_payload(payload)

    if opcode in (0x0413, 0x0414):
        cursor = 2 if opcode == 0x0413 else 4
        if len(payload) < cursor:
            return None
        result = None if opcode == 0x0413 else int.from_bytes(payload[:2], "little")
        count = int.from_bytes(payload[cursor - 2:cursor], "little")
        if len(payload) != cursor + count * SALVAGE_ITEM.size:
            return None
        items = [
            dict(
                zip(
                    ("item_uid", "item_index", "count"),
                    SALVAGE_ITEM.unpack_from(payload, cursor + i * SALVAGE_ITEM.size),
                )
            )
            for i in range(count)
        ]
        return {
            "type": "salvage_items_request" if opcode == 0x0413 else "salvage_items_response",
            "confidence": "alto-4-lotes-177-itens",
            "result": result,
            "items": items,
        }

    if opcode == 0x2801 and len(payload) == 5:
        stage_id, flag = struct.unpack("<IB", payload)
        return {
            "type": "sweep_scion_training_request",
            "message": "FC2L_ask_sweep_scion_training_Message",
            "confidence": "alto-2-acoes-marcadas",
            "stage_id": stage_id,
            "flag": flag,
        }
    if opcode == 0x2407 and len(payload) == 33:
        return {
            "type": "realm_contribution_update",
            "message": "FL2C_ans_realm_id_card_update_contribution_Message",
            "confidence": "alto-ground-truth-2-fluxos",
            "contribution_total": int.from_bytes(payload[7:15], "little", signed=True),
        }
    return None


def _read_struct(
    data: bytes, cursor: int, fmt: str, context: str
) -> tuple[tuple[Any, ...], int]:
    size = struct.calcsize(fmt)
    end = cursor + size
    if end > len(data):
        raise DecodeError(
            f"truncated {context} at payload offset {cursor}: need {size} bytes"
        )
    return struct.unpack_from(fmt, data, cursor), end


def _parse_item_info(payload: bytes, cursor: int) -> tuple[dict[str, Any], int]:
    fixed, cursor = _read_struct(payload, cursor, "<QIQBH", "m_ItemInfo prefix")
    item_id, item_index, count, locked_raw, enchant_level = fixed

    (talic_count,), cursor = _read_struct(payload, cursor, "<H", "m_TalicIndex count")
    talic_bytes = talic_count * 4
    if cursor + talic_bytes > len(payload):
        raise DecodeError(f"truncated m_TalicIndex vector with {talic_count} entries")
    talic_indices = list(struct.unpack_from(f"<{talic_count}I", payload, cursor))
    cursor += talic_bytes

    (option_count,), cursor = _read_struct(payload, cursor, "<H", "m_ItemOptions count")
    option_bytes = option_count * 9
    if cursor + option_bytes > len(payload):
        raise DecodeError(f"truncated m_ItemOptions vector with {option_count} entries")
    item_options = []
    for _ in range(option_count):
        values, cursor = _read_struct(payload, cursor, "<IfB", "m_ItemOptions entry")
        item_options.append(
            {
                "option_index": values[0],
                "value": values[1],
                "change_lock": bool(values[2]),
            }
        )

    suffix, cursor = _read_struct(payload, cursor, "<BQ", "m_ItemInfo suffix")
    is_broken_raw, expire_time = suffix
    return {
        "id": item_id,
        "index": item_index,
        "count": count,
        "lock": bool(locked_raw),
        "enchant_level": enchant_level,
        "talic_indices": talic_indices,
        "item_options": item_options,
        "is_broken": bool(is_broken_raw),
        "expire_time": expire_time,
    }, cursor


def _parse_compact_profile_item(payload: bytes, cursor: int) -> tuple[dict[str, Any], int]:
    (inventory_slot,), cursor = _read_struct(
        payload, cursor, "<H", "profile inventory slot"
    )
    uid_end = cursor + 6
    if uid_end > len(payload):
        raise DecodeError(f"truncated profile item UID at payload offset {cursor}")
    item_uid_raw = payload[cursor:uid_end]
    cursor = uid_end

    fixed, cursor = _read_struct(payload, cursor, "<IQBH", "profile item prefix")
    item_index, count, locked_raw, enchant_level = fixed
    (talic_count,), cursor = _read_struct(payload, cursor, "<H", "profile talic count")
    talic_bytes = talic_count * 4
    if cursor + talic_bytes > len(payload):
        raise DecodeError(f"truncated profile talic vector with {talic_count} entries")
    talic_indices = list(struct.unpack_from(f"<{talic_count}I", payload, cursor))
    cursor += talic_bytes

    (option_count,), cursor = _read_struct(payload, cursor, "<H", "profile option count")
    item_options = []
    for _ in range(option_count):
        values, cursor = _read_struct(payload, cursor, "<IfB", "profile option entry")
        item_options.append(
            {
                "option_index": values[0],
                "value": values[1],
                "change_lock": bool(values[2]),
            }
        )
    suffix, cursor = _read_struct(payload, cursor, "<BQ", "profile item suffix")
    return {
        "inventory_slot": inventory_slot,
        "item_uid": int.from_bytes(item_uid_raw, "little"),
        "item_uid_hex": item_uid_raw.hex(),
        "item_index": item_index,
        "count": count,
        "lock": bool(locked_raw),
        "enchant_level": enchant_level,
        "talic_indices": talic_indices,
        "item_options": item_options,
        "is_broken": bool(suffix[0]),
        "expire_time": suffix[1],
    }, cursor


def _parse_stackable_inventory_item(
    payload: bytes, cursor: int
) -> tuple[dict[str, Any], int]:
    values, cursor = _read_struct(
        payload,
        cursor,
        STACKABLE_INVENTORY_ITEM.format,
        "stackable inventory item",
    )
    slot_raw, item_uid_raw, item_index, count, locked_raw, expire_time = values
    return {
        "inventory_slot": slot_raw,
        "item_uid": int.from_bytes(item_uid_raw, "little"),
        "item_uid_hex": item_uid_raw.hex(),
        "item_index": item_index,
        "count": count,
        "lock": bool(locked_raw),
        "expire_time": expire_time,
    }, cursor


def parse_inventory_payload(decoded: bytes) -> dict[str, Any] | None:
    """Decodifica snapshots e deltas confirmados do inventário e armazém."""
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
    snapshots = {
        0x0401: ("inventory", "stackable"),
        0x0403: ("inventory", "equipment"),
        0x1F05: ("warehouse", "equipment"),
        0x1F06: ("warehouse", "stackable"),
    }
    deltas = {
        0x0402: ("inventory", "stackable"),
        0x0404: ("inventory", "equipment"),
        0x1F07: ("warehouse", "equipment"),
        0x1F08: ("warehouse", "stackable"),
    }
    if opcode in snapshots:
        if len(payload) < 3:
            return None
        container, item_kind = snapshots[opcode]
        header_raw, item_count = struct.unpack_from("<BH", payload)
        cursor = 3
        items = []
        parser = (
            _parse_stackable_inventory_item
            if item_kind == "stackable"
            else _parse_compact_profile_item
        )
        try:
            for _ in range(item_count):
                item, cursor = parser(payload, cursor)
                items.append(item)
        except (DecodeError, struct.error):
            return None
        if cursor != len(payload):
            return None
        return {
            "type": "inventory_snapshot",
            "confidence": "alto-layout-exato-captura-marcada-20260811",
            "container": container,
            "item_kind": item_kind,
            "header_raw": header_raw,
            "item_count": item_count,
            "items": items,
        }
    if opcode in deltas:
        if len(payload) < 2:
            return None
        container, item_kind = deltas[opcode]
        update_group_raw = struct.unpack_from("<H", payload)[0]
        parser = (
            _parse_stackable_inventory_item
            if item_kind == "stackable"
            else _parse_compact_profile_item
        )
        try:
            item, cursor = parser(payload, 2)
        except (DecodeError, struct.error):
            return None
        if cursor != len(payload):
            return None
        return {
            "type": "inventory_delta",
            "confidence": "alto-layout-exato-captura-marcada-20260811",
            "container": container,
            "item_kind": item_kind,
            "update_group_raw": update_group_raw,
            "item": item,
        }
    return None


def parse_guild_relation_payload(decoded: bytes) -> dict[str, Any] | None:
    """Decodifica as listas de guildas inimigas e aliadas recebidas do jogo."""
    if len(decoded) < HEADER_SIZE:
        return None
    opcode = int.from_bytes(decoded[4:6], "little")
    messages = {
        0x0D3F: ("enemy_guild_list", "FL2C_ans_enemy_guild_list_Message", "enemy"),
        0x0D4D: ("amity_guild_list", "FL2C_ans_amity_guild_list_Message", "amity"),
    }
    if opcode not in messages:
        return None
    payload = decoded[HEADER_SIZE:]
    if len(payload) < 12:
        return None
    result_code, owner_guild_id, guild_count = struct.unpack_from("<HQH", payload)
    cursor = 12
    guilds = []
    try:
        for _ in range(guild_count):
            (guild_id,), cursor = _read_struct(payload, cursor, "<Q", "guild ID")
            guild_name, cursor = _read_utf16le_u16(payload, cursor, "guild name")
            raw, cursor = _read_struct(payload, cursor, "<BHBB", "guild raw fields")
            representative_name_raw, cursor = _read_utf16le_u16(
                payload, cursor, "guild representative name"
            )
            (tail_u16_raw,), cursor = _read_struct(payload, cursor, "<H", "guild tail")
            guilds.append({
                "guild_id": guild_id,
                "guild_name": guild_name,
                "f0_u8_raw": raw[0],
                "f1_u16_raw": raw[1],
                "f3_u8_raw": raw[2],
                "f4_u8_raw": raw[3],
                "representative_name_raw": representative_name_raw,
                "tail_u16_raw": tail_u16_raw,
            })
    except (DecodeError, UnicodeDecodeError, struct.error):
        return None
    if cursor != len(payload):
        return None
    event_type, message, relation = messages[opcode]
    return {
        "type": event_type,
        "message": message,
        "direction": "FL2C",
        "confidence": "alto-layout-exato-6-listas-44-registros",
        "relation": relation,
        "result_code": result_code,
        "owner_guild_id": owner_guild_id,
        "guild_count": guild_count,
        "guilds": guilds,
    }


def _parse_player_profile_payload(payload: bytes) -> dict[str, Any] | None:
    if len(payload) < 3:
        return None
    f0_u8_raw, item_count = struct.unpack_from("<BH", payload)
    cursor = 3
    items = []
    try:
        for _ in range(item_count):
            item, cursor = _parse_compact_profile_item(payload, cursor)
            items.append(item)
    except (DecodeError, struct.error):
        return None
    if cursor != len(payload):
        return None
    return {
        "type": "player_profile_info",
        "message": "FG2C_ans_player_profile_info_Message",
        "direction": "FG2C",
        "confidence": "alto-layout-exato-2-sessoes-ground-truth",
        "fields": {
            "f0_u8_raw": f0_u8_raw,
            "item_count": item_count,
            "items": items,
        },
    }


def add_profile_item_names(profile: dict[str, Any], names: dict[int, str]) -> None:
    for item in profile.get("fields", {}).get("items", []):
        name = names.get(item["item_index"])
        if name:
            item["item_name_ptbr"] = name


def correlate_active_equipment(
    profile: dict[str, Any], appearances: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    profile_items = profile.get("fields", {}).get("items", [])
    by_uid = {item["item_uid"]: item for item in profile_items if item["item_uid"]}
    candidates = []
    for appearance in appearances:
        refs = appearance.get("fields", {}).get("equipment_refs", [])
        selected = [ref for ref in refs if ref["item_uid"]]
        matched = sum(ref["item_uid"] in by_uid for ref in selected)
        if matched:
            candidates.append((matched, len(selected), appearance, refs))
    if not candidates:
        return None
    matched, selected_count, appearance, refs = max(candidates, key=lambda item: item[0])
    slots = []
    for ref in refs:
        slot = dict(ref)
        item = by_uid.get(ref["item_uid"])
        slot["empty"] = ref["item_uid"] == 0
        slot["resolved"] = item is not None
        if item is not None:
            slot["item"] = item
        slots.append(slot)
    active = {
        "character_uid": appearance["fields"]["character_uid"],
        "character_name": appearance["fields"]["character_name"],
        "biosuit_item_index": appearance["fields"].get("biosuit_item_index"),
        "selected_item_count": selected_count,
        "matched_item_count": matched,
        "complete": matched == selected_count,
        "confidence": (
            "alto-uid-exato+ground-truth"
            if matched == selected_count
            else "medio-correlacao-parcial"
        ),
        "slots": slots,
    }
    return active, appearance


def _parse_detailed_exchange_info(payload: bytes, cursor: int) -> tuple[dict[str, Any], int]:
    ids, cursor = _read_struct(payload, cursor, "<QQQ", "detailed exchange IDs")
    item_info, cursor = _parse_item_info(payload, cursor)
    tail, cursor = _read_struct(payload, cursor, "<QQQQQB", "detailed exchange tail")
    return {
        "exchange_index": ids[0],
        "account_id": ids[1],
        "pc_id": ids[2],
        "item_info": item_info,
        "registed_time": tail[0],
        "expired_time": tail[1],
        "selling_time": tail[2],
        "selling_price": tail[3],
        "settlement_price": tail[4],
        "is_forc_expire": bool(tail[5]),
    }, cursor


def _parse_item_enchant_entries(
    payload: bytes, cursor: int, count: int, context: str
) -> tuple[list[dict[str, int]], int]:
    entries = []
    for _ in range(count):
        values, cursor = _read_struct(payload, cursor, "<IH", context)
        entries.append({"item_index": values[0], "enchant_level": values[1]})
    return entries, cursor


def parse_exchange_payload(decoded_frame: bytes) -> dict[str, Any] | None:
    """Parse Exchange messages confirmed by static analysis."""
    if len(decoded_frame) < HEADER_SIZE:
        raise DecodeError("decoded frame shorter than 6-byte header")
    opcode = int.from_bytes(decoded_frame[4:6], "little")
    payload = decoded_frame[HEADER_SIZE:]

    if opcode == 0x1D17:
        if len(payload) != 25:
            raise DecodeError(f"0x1d17 payload must be 25 bytes, got {len(payload)}")
        ret, item_index, enchant_level, weekly_average, last_price, server_type = (
            struct.unpack("<HIHddB", payload)
        )
        return {
            "message": "FL2C_ans_exchange_market_price_information_Message",
            "ret": ret,
            "market_price_info": {
                "item_index": item_index,
                "enchant_level": enchant_level,
                "weekly_average_selling_price": weekly_average,
                "last_price": last_price,
            },
            "exchange_server_type": server_type,
        }

    if opcode == 0x1D18:
        prefix, cursor = _read_struct(payload, 0, "<BH", "0x1d18 prefix")
        server_type, sold_count = prefix
        most_sold, cursor = _parse_item_enchant_entries(
            payload, cursor, sold_count, "0x1d18 most-sold entry"
        )
        (registration_count,), cursor = _read_struct(
            payload, cursor, "<H", "0x1d18 registration count"
        )
        most_registered, cursor = _parse_item_enchant_entries(
            payload, cursor, registration_count, "0x1d18 most-registered entry"
        )
        if cursor != len(payload):
            raise DecodeError(f"0x1d18 has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_recommended_item_on_exchange_Message",
            "exchange_server_type": server_type,
            "recommended_item_info": {
                "most_sold_in_one_week_item_info": most_sold,
                "most_registrations_in_one_week_item_info": most_registered,
            },
        }

    if opcode == 0x1D02:
        if len(payload) < 6:
            raise DecodeError(f"0x1d02 payload shorter than fixed prefix: {len(payload)}")
        ret, is_end_raw, server_type, count = struct.unpack_from("<HBBH", payload)
        expected = 6 + count * 26
        if len(payload) != expected:
            raise DecodeError(
                f"0x1d02 payload length {len(payload)} differs from "
                f"6 + {count} * 26 = {expected}"
            )
        entries = []
        for index in range(count):
            offset = 6 + index * 26
            item_index, enchant_level, lowest_price, highest_price, registered = (
                struct.unpack_from("<IHddI", payload, offset)
            )
            entries.append(
                {
                    "item_index": item_index,
                    "enchant_level": enchant_level,
                    "lowest_price": lowest_price,
                    "highest_price": highest_price,
                    "number_of_registered_items": registered,
                }
            )
        return {
            "message": "FL2C_respond_purchase_list_on_exchange_Message",
            "ret": ret,
            "is_end": bool(is_end_raw),
            "exchange_server_type": server_type,
            "exchange_item_simple_infos": entries,
        }

    if opcode == 0x1D04:
        prefix, cursor = _read_struct(payload, 0, "<HIBBH", "0x1d04 prefix")
        ret, item_index, is_end_raw, server_type, count = prefix
        entries = []
        for _ in range(count):
            entry, cursor = _parse_detailed_exchange_info(payload, cursor)
            entries.append(entry)
        if cursor != len(payload):
            raise DecodeError(
                f"0x1d04 has {len(payload) - cursor} trailing payload bytes after {count} entries"
            )
        return {
            "message": "FL2C_respond_detailed_list_of_purchase_on_exchange_Message",
            "ret": ret,
            "item_index": item_index,
            "is_end": bool(is_end_raw),
            "exchange_server_type": server_type,
            "detailed_list": entries,
        }

    if opcode in (0x1D07, 0x1D09):
        opcode_text = f"{opcode:#06x}"
        prefix, cursor = _read_struct(payload, 0, "<HBH", f"{opcode_text} prefix")
        ret, server_type, count = prefix
        entries = []
        for _ in range(count):
            entry, cursor = _parse_detailed_exchange_info(payload, cursor)
            entries.append(entry)
        if cursor != len(payload):
            raise DecodeError(f"{opcode_text} has {len(payload) - cursor} trailing payload bytes")
        is_sales = opcode == 0x1D07
        return {
            "message": (
                "FL2C_ans_exchange_for_my_sales_list_Message"
                if is_sales
                else "FL2C_ans_exchange_for_my_settlement_list_Message"
            ),
            "ret": ret,
            "exchange_server_type": server_type,
            "my_sales_list" if is_sales else "my_settlement_list": entries,
        }

    if opcode == 0x1D0B:
        prefix, cursor = _read_struct(payload, 0, "<HBH", "0x1d0b prefix")
        ret, server_type, history_count = prefix
        history = []
        for _ in range(history_count):
            (exchange_type,), cursor = _read_struct(
                payload, cursor, "<I", "0x1d0b history m_ExchangeType"
            )
            entry, cursor = _parse_detailed_exchange_info(payload, cursor)
            history.append({"exchange_type": exchange_type, "exchange_item_info": entry})
        (statistics_count,), cursor = _read_struct(
            payload, cursor, "<H", "0x1d0b m_MyTransactionStatistics count"
        )
        statistics = []
        for _ in range(statistics_count):
            values, cursor = _read_struct(payload, cursor, "<IQQQ", "0x1d0b statistics entry")
            statistics.append(
                {
                    "exchange_type": values[0],
                    "daily_time": values[1],
                    "sum_exchange_count": values[2],
                    "sum_exchange_price": values[3],
                }
            )
        if cursor != len(payload):
            raise DecodeError(f"0x1d0b has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_ans_exchange_for_my_transaction_history_Message",
            "ret": ret,
            "exchange_server_type": server_type,
            "my_transaction_history": history,
            "my_transaction_statistics": statistics,
        }

    if opcode in (0x1D0D, 0x1D11):
        opcode_text = f"{opcode:#06x}"
        prefix, cursor = _read_struct(payload, 0, "<HB", f"{opcode_text} prefix")
        entry, cursor = _parse_detailed_exchange_info(payload, cursor)
        if cursor != len(payload):
            raise DecodeError(f"{opcode_text} has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": (
                "FL2C_respond_to_registration_of_sale_item_on_exchange_Message"
                if opcode == 0x1D0D
                else "FL2C_respond_to_reregistration_of_sale_item_on_exchange_Message"
            ),
            "ret": prefix[0],
            "exchange_server_type": prefix[1],
            "exchange_item_info": entry,
        }

    if opcode == 0x1D0F:
        if len(payload) != 11:
            raise DecodeError(f"0x1d0f payload must be 11 bytes, got {len(payload)}")
        ret, server_type, exchange_index = struct.unpack("<HBQ", payload)
        return {
            "message": "FL2C_respond_to_cancellation_of_sale_item_on_exchange_Message",
            "ret": ret,
            "exchange_server_type": server_type,
            "exchange_index": exchange_index,
        }

    if opcode == 0x1D13:
        prefix, cursor = _read_struct(payload, 0, "<HBH", "0x1d13 prefix")
        ret, server_type, count = prefix
        entries = []
        for _ in range(count):
            (entry_ret,), cursor = _read_struct(payload, cursor, "<H", "0x1d13 entry m_Ret")
            entry, cursor = _parse_detailed_exchange_info(payload, cursor)
            entries.append({"ret": entry_ret, "exchange_info": entry})
        if cursor != len(payload):
            raise DecodeError(f"0x1d13 has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_respond_to_purchase_item_on_exchange_Message",
            "ret": ret,
            "exchange_server_type": server_type,
            "purchase_results": entries,
        }

    if opcode == 0x1D15:
        prefix, cursor = _read_struct(payload, 0, "<HBH", "0x1d15 prefix")
        ret, server_type, index_count = prefix
        exchange_indices = []
        for _ in range(index_count):
            (exchange_index,), cursor = _read_struct(
                payload, cursor, "<Q", "0x1d15 m_ExchangeIndexList entry"
            )
            exchange_indices.append(exchange_index)
        (result_count,), cursor = _read_struct(
            payload, cursor, "<H", "0x1d15 m_RespondSettlementInfos count"
        )
        results = []
        for _ in range(result_count):
            values, cursor = _read_struct(payload, cursor, "<QQ", "0x1d15 settlement entry")
            results.append({"exchange_index": values[0], "selling_price": values[1]})
        if cursor != len(payload):
            raise DecodeError(f"0x1d15 has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_respond_settlement_of_exchange_Message",
            "ret": ret,
            "exchange_server_type": server_type,
            "exchange_index_list": exchange_indices,
            "respond_settlement_infos": results,
        }

    if opcode == 0x1D1A:
        prefix, cursor = _read_struct(payload, 0, "<HBBH", "0x1d1a prefix")
        ret, is_end_raw, server_type, count = prefix
        bookmarks, cursor = _parse_item_enchant_entries(
            payload, cursor, count, "0x1d1a bookmark entry"
        )
        if cursor != len(payload):
            raise DecodeError(f"0x1d1a has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_bookmark_info_Message",
            "ret": ret,
            "is_end": bool(is_end_raw),
            "exchange_server_type": server_type,
            "bookmark_info_list": bookmarks,
        }

    if opcode == 0x1D1B:
        prefix, cursor = _read_struct(payload, 0, "<BH", "0x1d1b prefix")
        server_type, count = prefix
        exchange_indices = []
        for _ in range(count):
            (exchange_index,), cursor = _read_struct(
                payload, cursor, "<Q", "0x1d1b m_ExchangeIndex entry"
            )
            exchange_indices.append(exchange_index)
        if cursor != len(payload):
            raise DecodeError(f"0x1d1b has {len(payload) - cursor} trailing payload bytes")
        return {
            "message": "FL2C_notify_exchange_item_sell_Message",
            "exchange_server_type": server_type,
            "exchange_indices": exchange_indices,
        }

    return None


def decode_stream(stream: bytes) -> list[tuple[bytes, dict[str, int | bool]]]:
    frames: list[tuple[bytes, dict[str, int | bool]]] = []
    cursor = 0
    while cursor < len(stream):
        if len(stream) - cursor < HEADER_SIZE:
            raise DecodeError(f"trailing {len(stream) - cursor} bytes at stream offset {cursor}")
        length = frame_length_from_wire(stream[cursor : cursor + 3])
        if length < HEADER_SIZE or length > MAX_FRAME:
            raise DecodeError(f"invalid frame length {length} at stream offset {cursor}")
        end = cursor + length
        if end > len(stream):
            raise DecodeError(f"truncated frame at stream offset {cursor}: need {length} bytes")
        decoded, info = decode_frame(stream[cursor:end])
        info["stream_offset"] = cursor
        frames.append((decoded, info))
        cursor = end
    return frames


def expand_bundle(
    decoded: bytes, info: dict[str, int | bool]
) -> list[tuple[bytes, dict[str, int | bool]]]:
    frames = [(decoded, info)]
    if info["opcode"] != 0x010A or len(decoded) < HEADER_SIZE + 2:
        return frames
    size = int.from_bytes(decoded[HEADER_SIZE : HEADER_SIZE + 2], "little")
    payload = decoded[HEADER_SIZE + 2 :]
    if size != len(payload):
        return frames
    try:
        nested = decode_stream(payload)
    except DecodeError:
        return frames
    for nested_decoded, nested_info in nested:
        nested_info["bundled"] = True
        nested_info["parent_opcode"] = 0x010A
        if "pcap_time_ns" in info:
            nested_info["pcap_time_ns"] = info["pcap_time_ns"]
        frames.append((nested_decoded, nested_info))
    return frames


COLLECTION_ADD_REQUEST = struct.Struct("<IBBQB")
COLLECTION_ADD_RESPONSE_PREFIX = struct.Struct("<HBBIB")
COLLECTION_SLOT_VALUES = struct.Struct("<10Q")
COLLECTION_SNAPSHOT_HEADER = struct.Struct("<BBH")
COLLECTION_SNAPSHOT_RECORD = struct.Struct("<IB10Q")


def parse_collection_payload(decoded: bytes) -> dict[str, Any] | None:
    """Decode layouts closed by seven marked collection additions."""
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
    if opcode == 0x0417 and len(payload) == COLLECTION_ADD_REQUEST.size:
        collection_index, collection_type, slot_index, item_uid, f14 = (
            COLLECTION_ADD_REQUEST.unpack(payload)
        )
        return {
            "type": "collection_add_request",
            "opcode": "0x0417",
            "confidence": "alto-7-pares-marcados",
            "collection_index": collection_index,
            "collection_type": collection_type,
            "slot_index": slot_index,
            "item_uid": item_uid,
            "f14": f14,
        }
    if opcode == 0x0418 and len(payload) == 98:
        result_code, slot_index, collection_type, collection_index, f8 = (
            COLLECTION_ADD_RESPONSE_PREFIX.unpack_from(payload)
        )
        slot_values = list(COLLECTION_SLOT_VALUES.unpack_from(payload, 9))
        item_uid = struct.unpack_from("<Q", payload, 89)[0]
        return {
            "type": "collection_add_response",
            "opcode": "0x0418",
            "confidence": "alto-7-pares-marcados",
            "result_code": result_code,
            "collection_index": collection_index,
            "collection_type": collection_type,
            "slot_index": slot_index,
            "slot_values": slot_values,
            "updated_slot_value": (
                slot_values[slot_index] if slot_index < len(slot_values) else None
            ),
            "item_uid": item_uid,
            "f8": f8,
            "f97": payload[97],
        }
    if opcode == 0x0419 and len(payload) >= COLLECTION_SNAPSHOT_HEADER.size:
        is_end, collection_type, count = COLLECTION_SNAPSHOT_HEADER.unpack_from(payload)
        expected_size = COLLECTION_SNAPSHOT_HEADER.size + count * COLLECTION_SNAPSHOT_RECORD.size
        if is_end not in (0, 1) or len(payload) != expected_size:
            return None
        records = []
        cursor = COLLECTION_SNAPSHOT_HEADER.size
        for _ in range(count):
            values = COLLECTION_SNAPSHOT_RECORD.unpack_from(payload, cursor)
            records.append(
                {
                    "collection_index": values[0],
                    "collection_type": values[1],
                    "slot_values": list(values[2:]),
                }
            )
            cursor += COLLECTION_SNAPSHOT_RECORD.size
        return {
            "type": "collection_snapshot_chunk",
            "opcode": "0x0419",
            "confidence": "alto-sessao-completa+valores-0418",
            "is_end": bool(is_end),
            "collection_type": collection_type,
            "record_count": count,
            "slot_index_base": 0,
            "records": records,
        }
    return None


def parse_nmssw_payload(decoded: bytes) -> dict[str, Any] | None:
    """Decode the stable envelope of FL2C_nmssw_verify; proof bytes stay opaque."""
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
    if opcode != 0x0219 or len(payload) < 2:
        return None
    verify_length = struct.unpack_from("<H", payload)[0]
    blob = payload[2:]
    if verify_length != len(blob):
        return None
    result: dict[str, Any] = {
        "type": "nmssw_verify",
        "opcode": "0x0219",
        "message": "FL2C_nmssw_verify_Message",
        "direction": "FL2C",
        "confidence": "alto-catalogo-binario+captura",
        "verify_length": verify_length,
        "verify_sha256": hashlib.sha256(blob).hexdigest(),
    }
    if len(blob) >= 32:
        result["fields"] = {
            "f0_15_hex": blob[:16].hex(),
            "f16_u32": struct.unpack_from("<I", blob, 16)[0],
            "f20_u64": struct.unpack_from("<Q", blob, 20)[0],
            "f28_u32": struct.unpack_from("<I", blob, 28)[0],
        }
        build_end = blob.find(b"\0", 32, 96)
        if build_end != -1:
            try:
                build_string = blob[32:build_end].decode("ascii")
            except UnicodeDecodeError:
                build_string = ""
            if build_string and all(32 <= ord(char) < 127 for char in build_string):
                result["fields"]["client_build"] = build_string
                result["fields"]["opaque_tail_offset"] = build_end + 1
                result["fields"]["opaque_tail_length"] = len(blob) - build_end - 1
    return result


def parse_observation_payload(decoded: bytes) -> dict[str, Any] | None:
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
    if opcode == 0x0601 and len(payload) == USE_SKILL_REQUEST.size:
        skill_index, request_sequence_raw, target_uid = USE_SKILL_REQUEST.unpack(payload)
        return {
            "type": "use_skill_request",
            "direction": "client_to_game",
            "confidence": "alto-layout-exato+correlacao-0609-0602",
            "skill_index": skill_index,
            "request_sequence_raw": request_sequence_raw,
            "target_uid": target_uid,
        }
    if opcode == 0x0609 and len(payload) == SELECT_TARGET_REQUEST.size:
        (target_uid,) = SELECT_TARGET_REQUEST.unpack(payload)
        return {
            "type": "select_target_request",
            "direction": "client_to_game",
            "confidence": "alto-layout-exato+correlacao-0601",
            "target_uid": target_uid,
        }
    if opcode == 0x0305 and len(payload) >= 2:
        count = struct.unpack_from("<H", payload)[0]
        cursor = 2
        units = []
        for _ in range(count):
            if cursor + APPEAR_PLAYER_PREFIX.size > len(payload):
                return None
            values = APPEAR_PLAYER_PREFIX.unpack_from(payload, cursor)
            cursor += APPEAR_PLAYER_PREFIX.size
            name_end = cursor + values[-1] * 2
            record_end = name_end + APPEAR_PLAYER_TAIL_SIZE
            if record_end > len(payload):
                return None
            try:
                name = payload[cursor:name_end].decode("utf-16le")
            except UnicodeDecodeError:
                return None
            state = APPEAR_PLAYER_STATE.unpack_from(payload, name_end)
            state_end = name_end + APPEAR_PLAYER_STATE.size
            state_tail = payload[state_end:record_end]
            units.append(
                {
                    "character_uid": values[0],
                    "f8_raw": values[1],
                    "biosuit_item_index": values[2],
                    "f13_raw": values[3],
                    "rover_item_index": values[4],
                    "f18_raw": values[5],
                    "name": name,
                    "uid": state[0],
                    "realm_raw": state[1],
                    "max_hp": state[2],
                    "current_hp": state[3],
                    "max_fp": state[4],
                    "current_fp": state[5],
                    "f29_raw": state[6],
                    "position_x": state[7],
                    "position_y": state[8],
                    "position_z": state[9],
                    "guild_id": struct.unpack_from("<Q", state_tail, 43)[0],
                    "visibility_event": "enter_range",
                    "state_tail_hex": state_tail.hex(),
                }
            )
            cursor = record_end
        if cursor == len(payload):
            return {
                "type": "appear_player_list",
                "message": "FG2C_appear_player_list_Message",
                "direction": "FG2C",
                "confidence": "alto-layout-exato-3778-frames-7993-registros+guild-2316-correlacoes",
                "hostile_alert_rule": "local-if-guild-id-is-in-enemy-guild-list",
                "hostility_in_message": False,
                "units": units,
            }
    if opcode == 0x0307 and len(payload) == struct.calcsize("<HHHHqq"):
        values = struct.unpack("<HHHHqq", payload)
        return dict(
            type="update_exp",
            action_code=values[0],
            action_name=ACTION_CODES.get(values[0]),
            highest_level=values[1],
            before_level=values[2],
            level=values[3],
            exp=values[4],
            gain_exp=values[5],
        )
    if opcode == 0x0307 and len(payload) >= 2:
        count = int.from_bytes(payload[:2], "little")
        if len(payload) == 2 + count * APPEAR_UNIT.size:
            keys = (
                "uid", "summoner_uid", "summoner_pcid", "npc_index", "max_hp",
                "current_hp", "position_x", "position_y", "position_z", "direction",
                "speed", "realm", "patrol_x", "patrol_y", "patrol_z", "flag",
                "attack_speed_rate", "action_speed_rate", "guild_id",
            )
            units = [
                dict(zip(keys, APPEAR_UNIT.unpack_from(payload, 2 + index * APPEAR_UNIT.size)))
                for index in range(count)
            ]
            for unit in units:
                unit["realm_name"] = REALMS.get(unit["realm"])
                unit["flag_names"] = [
                    name
                    for bit, name in FIELD_MONSTER_FLAG_BITS.items()
                    if unit["flag"] & (1 << bit)
                ]
            return {"type": "appear_monster_list", "units": units}
    if opcode == 0x0316 and len(payload) == struct.calcsize("<IIB"):
        uid, killer_uid, reason = struct.unpack("<IIB", payload)
        return {"type": "dying_unit", "uid": uid, "killer_uid": killer_uid, "reason": reason}
    if opcode == 0x0311 and len(payload) == RESTORE_HP_FP.size:
        values = RESTORE_HP_FP.unpack(payload)
        return {
            "type": "restore_hp_fp",
            "message": "FG2C_restore_hp_fp_Message",
            "direction": "FG2C",
            "confidence": "alto-layout-exato-55380-frames+catalogo-binario",
            "uid": values[0],
            "current_hp": values[1],
            "max_hp": values[2],
            "hp_restore_raw": values[3],
            "current_fp": values[4],
            "max_fp": values[5],
            "fp_restore_raw": values[6],
            "state_raw": values[7],
        }
    if opcode == 0x0602 and len(payload) >= USE_SKILL_PREFIX.size:
        values = USE_SKILL_PREFIX.unpack_from(payload)
        count = values[-1]
        if len(payload) == USE_SKILL_PREFIX.size + count * SKILL_EFFECT_RESULT.size:
            result_keys = (
                "uid", "projectile_target_x", "projectile_target_y", "projectile_target_z",
                "target_x", "target_y", "target_z", "option_flag", "shield_damage",
                "hp_damage", "final_hp", "projectile_activate_time",
                "projectile_dest_time", "flag", "stiff_end_tick",
            )
            results = [
                dict(
                    zip(
                        result_keys,
                        SKILL_EFFECT_RESULT.unpack_from(
                            payload, USE_SKILL_PREFIX.size + index * SKILL_EFFECT_RESULT.size
                        ),
                    )
                )
                for index in range(count)
            ]
            return {
                "type": "use_skill_result",
                "ret": values[0],
                "response_number": values[1],
                "caster_uid": values[2],
                "skill_index": values[3],
                "use_skill_uniq_id": values[4],
                "detail_info_index": values[5],
                "caster_move_start": list(values[6:9]),
                "caster_move_end": list(values[9:12]),
                "main_target_uid": values[12],
                "main_target_pos": list(values[13:16]),
                "caster_final_hp": values[16],
                "caster_final_fp": values[17],
                "next_usable_skill_time": values[18],
                "effect_results": results,
            }
    if opcode == 0x060D and len(payload) >= NORMAL_SKILL_PREFIX.size:
        values = NORMAL_SKILL_PREFIX.unpack_from(payload)
        count = values[-1]
        if len(payload) == NORMAL_SKILL_PREFIX.size + count * NORMAL_SKILL_EFFECT_RESULT.size:
            result_keys = (
                "uid", "target_x", "target_y", "target_z", "option_flag",
                "shield_damage", "hp_damage", "final_hp", "flag", "stiff_end_tick",
            )
            results = [
                dict(
                    zip(
                        result_keys,
                        NORMAL_SKILL_EFFECT_RESULT.unpack_from(
                            payload,
                            NORMAL_SKILL_PREFIX.size
                            + index * NORMAL_SKILL_EFFECT_RESULT.size,
                        ),
                    )
                )
                for index in range(count)
            ]
            return {
                "type": "use_normal_skill_result",
                "ret": values[0],
                "response_number": values[1],
                "caster_uid": values[2],
                "caster_pos": list(values[3:6]),
                "skill_index": values[6],
                "use_skill_uniq_id": values[7],
                "main_target_uid": values[8],
                "direction": values[9],
                "caster_final_hp": values[10],
                "effect_results": results,
            }
    if opcode == 0x040A and len(payload) >= 4:
        ret, count = struct.unpack_from("<HH", payload)
        if len(payload) == 4 + count * DROP_RESULT.size:
            keys = ("ret", "item_index", "count", "item_id", "gain_total", "action_code")
            results = [
                dict(zip(keys, DROP_RESULT.unpack_from(payload, 4 + index * DROP_RESULT.size)))
                for index in range(count)
            ]
            for result in results:
                result["action_name"] = ACTION_CODES.get(result["action_code"])
            return {"type": "drop_item_field", "ret": ret, "results": results}
    return None


# ---------------------------------------------------------------------------
# trackA2: decoders INFERIDOS POR CAPTURA (nao por analise estatica do binario).
# Base: farm_00001_20260723072407.pcap (110k frames). Marcam confianca por campo.
# NUNCA sobrescrevem exchange/observation/job1 (plugados como ultimo fallback).
# ---------------------------------------------------------------------------

# 0x1e12 = FL2C_user_battlepass_mission_update_Message (catalogo Job1, opcode 7698).
# NAO e posicao de mob: em 47834 amostras o payload de 27B e quase-constante, com um
# contador u32 100% monotonico por (mission_uid, objective_index) e um flag de conclusao
# — comportamento de progresso de missao, sem trio de float32 de coordenada.
# fmt fecha exatamente 27B e valida sobre TODAS as 47834 amostras da captura rica.
BATTLEPASS_MISSION_UPDATE = struct.Struct("<HQIIIIB")  # 27 B


EVENT_MISSION_PROGRESS_UPDATE = struct.Struct("<HQIIQH")  # 28 B
EVENT_MISSION_REWARD_REQUEST = struct.Struct("<II")  # 8 B
EVENT_MISSION_REWARD_RESPONSE_PREFIX = struct.Struct("<HII")  # 10 de 42 B


def parse_event_mission_payload(decoded: bytes) -> dict[str, Any] | None:
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
    if opcode == 0x1E06 and len(payload) == EVENT_MISSION_PROGRESS_UPDATE.size:
        mission_index, character_uid, group, objective, f18, state = (
            EVENT_MISSION_PROGRESS_UPDATE.unpack(payload)
        )
        return {
            "type": "event_mission_progress_update",
            "opcode": "0x1e06",
            "message": "FL2C_event_mission_progress_update_Message",
            "direction": "FL2C",
            "confidence": "alto-layout-59756-amostras",
            "fmt": "<HQIIQH",
            "fields": {
                "mission_index@0": mission_index,
                "character_uid@2": character_uid,
                "event_mission_group@10": group,
                "objective_index@14": objective,
                "f18@18": f18,
                "state_raw@26": state,
            },
            "confidence_by_field": {
                "mission_index@0": "medio-alto (4502/4503 no catalogo local)",
                "character_uid@2": "alto (casa com 0x0106 nos dois personagens)",
                "event_mission_group@10": "alto (repete em 0x1e07/0x1e08)",
                "objective_index@14": "alto (repete em 0x1e07/0x1e08)",
                "f18@18": "nao-confirmado",
                "state_raw@26": "nao-confirmado (observados 0, 256 e 257)",
            },
        }
    if opcode == 0x1E07 and len(payload) == EVENT_MISSION_REWARD_REQUEST.size:
        group, objective = EVENT_MISSION_REWARD_REQUEST.unpack(payload)
        return {
            "type": "event_mission_reward_request",
            "opcode": "0x1e07",
            "message": "FC2L_ask_event_mission_reward_Message",
            "direction": "FC2L",
            "confidence": "alto-5-pares-capturados",
            "fields": {
                "event_mission_group@0": group,
                "objective_index@4": objective,
            },
        }
    if opcode == 0x1E08 and len(payload) == 42:
        result, group, objective = EVENT_MISSION_REWARD_RESPONSE_PREFIX.unpack_from(payload)
        return {
            "type": "event_mission_reward_response",
            "opcode": "0x1e08",
            "message": "FL2C_ans_event_mission_reward_Message",
            "direction": "FL2C",
            "confidence": "alto-prefixo-5-pares-capturados",
            "fields": {
                "result_code@0": result,
                "event_mission_group@2": group,
                "objective_index@6": objective,
                "reward_payload_hex@10": payload[10:].hex(),
            },
        }
    return None


def parse_1e12_payload(decoded: bytes) -> dict[str, Any] | None:
    opcode = int.from_bytes(decoded[4:6], "little")
    if opcode != 0x1E12:
        return None
    payload = decoded[HEADER_SIZE:]
    if len(payload) != BATTLEPASS_MISSION_UPDATE.size:
        return None
    (
        f0_const,
        mission_uid,
        f10_nearconst,
        objective_index,
        progress,
        f22_const,
        completed_raw,
    ) = BATTLEPASS_MISSION_UPDATE.unpack(payload)
    return {
        "type": "user_battlepass_mission_update",
        "opcode": "0x1e12",
        "message": "FL2C_user_battlepass_mission_update_Message",
        "direction": "FL2C",
        "confidence": "inferido-captura",
        "fmt": "<HQIIIIB",
        "fields": {
            "f0@0": f0_const,                 # const 4525 -> nao-confirmado
            "mission_uid@2": mission_uid,     # u64 id estavel -> medio/alto
            "f10@10": f10_nearconst,          # ~const (+1) -> nao-confirmado
            "objective_index@14": objective_index,  # inteiro pequeno -> alto
            "progress@18": progress,          # u32 monotonico por objetivo -> alto
            "f22@22": f22_const,              # const 0 -> nao-confirmado (target/reserv.)
            "completed@26": bool(completed_raw),    # flag 0/1 -> medio
        },
        "confidence_by_field": {
            "progress@18": "alto (100% monotonico por (mission_uid,objective) em 47834 amostras)",
            "objective_index@14": "alto (inteiro pequeno que particiona limpo o progresso)",
            "mission_uid@2": "medio-alto (u64 estavel, 2 valores distintos na captura)",
            "completed@26": "medio (bool; vira 1 raramente = missao concluida)",
            "f0@0": "nao-confirmado (const 4525; provavel pass/categoria)",
            "f10@10": "nao-confirmado (near-const; provavel timestamp/versao)",
            "f22@22": "nao-confirmado (const 0; provavel target/reservado)",
        },
        "signedness": "assumido unsigned; nao distinguivel so pela largura",
        "note": (
            "NAO e posicao de mob (hipotese refutada): payload quase-constante, sem "
            "float32 de coordenada; progress u32 e 100% monotonico por objetivo. "
            "opcode=battlepass mission update pelo catalogo Job1."
        ),
    }


# 0x2302 = FL2C_exploration_map_activate_Message (catalogo Job1, header estatico
# <HIIIIQ> = 26B). O wire aqui tem 80B: o corpo tem parte variavel (provavel lista
# de recompensa), entao NAO afirmamos layout. So ha 1 amostra na captura (baú unico,
# 13:31:14 UTC) -> confianca BAIXA. Entregamos hexdump + tokens reconheciveis.
EXPLORATION_ACTIVATE_HEADER = struct.Struct("<HIIIIQ")  # 26 B (layout estatico Job1)


def parse_2302_payload(decoded: bytes) -> dict[str, Any] | None:
    opcode = int.from_bytes(decoded[4:6], "little")
    if opcode != 0x2302:
        return None
    payload = decoded[HEADER_SIZE:]
    result: dict[str, Any] = {
        "type": "exploration_map_activate",
        "opcode": "0x2302",
        "message": "FL2C_exploration_map_activate_Message",
        "direction": "FL2C",
        "confidence": "baixa (1 amostra; corpo variavel nao confirmado)",
        "payload_len": len(payload),
        "payload_hex": payload.hex(),
    }
    # Header estatico Job1 (26B) como TENTATIVA; o restante fica como corpo bruto.
    if len(payload) >= EXPLORATION_ACTIVATE_HEADER.size:
        h = EXPLORATION_ACTIVATE_HEADER.unpack_from(payload, 0)
        result["header_job1_tentativo"] = {
            "fmt": "<HIIIIQ",
            "f0@0": h[0], "f1@2": h[1], "f2@6": h[2],
            "f3@10": h[3], "f4@14": h[4], "f5@18": h[5],
        }
        result["body_after_header_hex"] = payload[EXPLORATION_ACTIVATE_HEADER.size:].hex()
    result["note"] = (
        "header estatico Job1 (26B) NAO fecha o wire (80B): corpo tem parte variavel "
        "(provavel lista de recompensa). Layout NAO confirmado. "
        "RECOMENDACAO: captura MARCADA de bau com varias amostras p/ fixar header+registro."
    )
    return result


def _network_payload(frame: bytes, linktype: int) -> tuple[int | None, bytes]:
    if linktype == 1:
        if len(frame) < 14:
            return None, b""
        ethertype, cursor = struct.unpack_from("!H", frame, 12)[0], 14
    elif linktype == 113:
        if len(frame) < 16:
            return None, b""
        ethertype, cursor = struct.unpack_from("!H", frame, 14)[0], 16
    else:
        raise DecodeError(f"unsupported PCAP linktype {linktype}")
    while ethertype in (0x8100, 0x88A8, 0x9100):
        if len(frame) < cursor + 4:
            return None, b""
        ethertype = struct.unpack_from("!H", frame, cursor + 2)[0]
        cursor += 4
    return ethertype, frame[cursor:]


def _merge_tcp_segments(
    segments: list[tuple[int, bytes, int]],
) -> list[tuple[bytes, list[tuple[int, int]]]]:
    chunks: list[tuple[bytes, list[tuple[int, int]]]] = []
    current = bytearray()
    time_spans: list[tuple[int, int]] = []
    end: int | None = None
    for sequence, payload, timestamp_ns in sorted(segments, key=lambda entry: entry[0]):
        if end is None or sequence > end:
            if current:
                chunks.append((bytes(current), time_spans))
            current, end = bytearray(payload), sequence + len(payload)
            time_spans = [(len(current), timestamp_ns)]
        elif sequence + len(payload) > end:
            current.extend(payload[end - sequence :])
            end = sequence + len(payload)
            time_spans.append((len(current), timestamp_ns))
    if current:
        chunks.append((bytes(current), time_spans))
    return chunks


def pcap_tcp_streams(
    path: Path, port: int
) -> list[tuple[str, bytes, list[tuple[int, int]]]]:
    raw = path.read_bytes()
    formats = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000),
        b"\xa1\xb2\xc3\xd4": (">", 1_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1),
        b"\xa1\xb2\x3c\x4d": (">", 1),
    }
    if len(raw) < 24 or raw[:4] not in formats:
        raise DecodeError("unsupported or truncated PCAP")
    endian, fraction_to_ns = formats[raw[:4]]
    linktype = struct.unpack_from(endian + "IHHIIII", raw)[6]
    flows: dict[tuple[str, int, str, int], list[tuple[int, bytes, int]]] = (
        collections.defaultdict(list)
    )
    cursor = 24
    while cursor + 16 <= len(raw):
        timestamp_s, timestamp_fraction, captured_length, _ = struct.unpack_from(
            endian + "IIII", raw, cursor
        )
        timestamp_ns = timestamp_s * 1_000_000_000 + timestamp_fraction * fraction_to_ns
        cursor += 16
        frame = raw[cursor : cursor + captured_length]
        cursor += captured_length
        ethertype, network = _network_payload(frame, linktype)
        if ethertype != 0x0800 or len(network) < 20:
            continue
        ihl = (network[0] & 0x0F) * 4
        total_length = struct.unpack_from("!H", network, 2)[0]
        if network[9] != 6 or len(network) < ihl + 20 or total_length < ihl + 20:
            continue
        tcp = network[ihl : min(total_length, len(network))]
        source_port, destination_port, sequence, _, offset_flags = struct.unpack_from(
            "!HHIIH", tcp
        )
        header_length = (offset_flags >> 12) * 4
        payload = tcp[header_length:] if header_length >= 20 else b""
        if not payload or port not in (source_port, destination_port):
            continue
        source = socket.inet_ntoa(network[12:16])
        destination = socket.inet_ntoa(network[16:20])
        flows[(source, source_port, destination, destination_port)].append(
            (sequence, payload, timestamp_ns)
        )
    streams = []
    for flow, segments in flows.items():
        label = f"{flow[0]}:{flow[1]} -> {flow[2]}:{flow[3]}"
        streams.extend(
            (label, chunk, time_spans)
            for chunk, time_spans in _merge_tcp_segments(segments)
        )
    return streams


def load_item_names(path: Path | None) -> dict[int, str]:
    if path is None:
        return {}
    with path.open(encoding="utf-8-sig", newline="") as source:
        return {
            int(row["ItemIndex"]): row.get("NamePTBR", "")
            for row in csv.DictReader(source)
            if row.get("ItemIndex") and row.get("NamePTBR")
        }


def add_item_names(exchange: dict[str, Any], names: dict[int, str]) -> None:
    item_index = exchange.get("item_index")
    if item_index is None and "market_price_info" in exchange:
        item_index = exchange["market_price_info"].get("item_index")
    if item_index in names:
        exchange["item_name"] = names[item_index]
    for entry in exchange.get("exchange_item_simple_infos", []):
        if entry.get("item_index") in names:
            entry["item_name"] = names[entry["item_index"]]


def load_collection_slots(path: Path | None) -> dict[tuple[int, int], dict[str, Any]]:
    slots: dict[tuple[int, int], dict[str, Any]] = {}
    if path is None:
        return slots
    with path.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            key = (int(row["CollectionIndex"]), int(row["Slot"]) - 1)
            slot = slots.setdefault(
                key,
                {
                    "collection_name_ptbr": row.get("CollectionNamePTBR", ""),
                    "item_group": int(row["ItemGroup"]),
                    "item_name_ptbr": row.get("AcceptedItemNamePTBR", ""),
                    "required_quantity": int(row["RequiredQuantity"]),
                    "required_enchant_level": int(row["RequiredEnchantLevel"]),
                    "accepted_item_indexes": [],
                },
            )
            accepted = int(row["AcceptedItemIndex"])
            if accepted not in slot["accepted_item_indexes"]:
                slot["accepted_item_indexes"].append(accepted)
    return slots


def add_collection_catalog(
    collection: dict[str, Any],
    slots: dict[tuple[int, int], dict[str, Any]],
) -> None:
    if collection["type"] == "collection_snapshot_chunk":
        requirements_by_collection: dict[int, dict[int, dict[str, Any]]] = (
            collections.defaultdict(dict)
        )
        for (collection_index, slot_index), requirement in slots.items():
            requirements_by_collection[collection_index][slot_index] = requirement
        for record in collection["records"]:
            requirements = requirements_by_collection.get(record["collection_index"])
            if not requirements:
                record["catalog_known"] = False
                continue
            values = record["slot_values"]
            record["catalog_known"] = True
            record["collection_name_ptbr"] = next(iter(requirements.values()))[
                "collection_name_ptbr"
            ]
            record["completed_slots"] = [
                slot_index
                for slot_index, requirement in sorted(requirements.items())
                if slot_index < len(values)
                and values[slot_index] >= requirement["required_quantity"]
            ]
            record["incomplete_slots"] = [
                slot_index
                for slot_index, requirement in sorted(requirements.items())
                if slot_index >= len(values)
                or values[slot_index] < requirement["required_quantity"]
            ]
            record["collection_complete"] = not record["incomplete_slots"]
        return

    key = (collection["collection_index"], collection["slot_index"])
    catalog = slots.get(key)
    if catalog is not None:
        collection["catalog"] = catalog
    if collection["type"] != "collection_add_response":
        return
    requirements = {
        slot_index: slot
        for (collection_index, slot_index), slot in slots.items()
        if collection_index == collection["collection_index"]
    }
    if not requirements:
        return
    values = collection["slot_values"]
    collection["item_complete"] = (
        catalog is not None
        and collection["updated_slot_value"] >= catalog["required_quantity"]
    )
    collection["incomplete_slots"] = [
        slot_index
        for slot_index, slot in sorted(requirements.items())
        if slot_index >= len(values) or values[slot_index] < slot["required_quantity"]
    ]
    collection["collection_complete"] = not collection["incomplete_slots"]


def latest_market_rows(infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current: dict[int, list[dict[str, Any]]] = {}
    latest: dict[int, list[dict[str, Any]]] = {}
    for info in infos:
        exchange = info.get("exchange", {})
        if exchange.get("message") != "FL2C_respond_purchase_list_on_exchange_Message":
            continue
        if exchange.get("ret") != 0:
            raise DecodeError(f"market list returned error {exchange.get('ret')}")
        server_type = int(exchange.get("exchange_server_type", 0))
        current.setdefault(server_type, []).extend(exchange.get("exchange_item_simple_infos", []))
        if exchange.get("is_end"):
            latest[server_type] = current.pop(server_type)
    if not latest:
        raise DecodeError("no complete market list found; start capture before opening Market")

    rows: dict[tuple[int, int, int], dict[str, Any]] = {}
    for server_type, entries in latest.items():
        for entry in entries:
            key = (server_type, entry["item_index"], entry["enchant_level"])
            row = {
                "RowType": "summary",
                "ServerType": server_type,
                "ListingId": "",
                "Name": entry.get("item_name", ""),
                "ItemIndex": key[1],
                "Enhance": key[2],
                "PricePerUnit": entry["lowest_price"],
                "Qty": entry["number_of_registered_items"],
                "HighestPrice": entry["highest_price"],
            }
            if key in rows and rows[key] != row:
                raise DecodeError(f"conflicting duplicate market row {key}")
            rows[key] = row
    if not rows:
        raise DecodeError("complete market list is empty")
    return [rows[key] for key in sorted(rows)]


def latest_market_offer_rows(infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    partial: dict[tuple[int, int], list[dict[str, Any]]] = {}
    latest: dict[tuple[int, int], tuple[str, list[dict[str, Any]]]] = {}
    for info in infos:
        exchange = info.get("exchange", {})
        if exchange.get("message") != "FL2C_respond_detailed_list_of_purchase_on_exchange_Message":
            continue
        if exchange.get("ret") != 0:
            raise DecodeError(f"detailed market list returned error {exchange.get('ret')}")
        key = (int(exchange.get("exchange_server_type", 0)), exchange["item_index"])
        partial.setdefault(key, []).extend(exchange.get("detailed_list", []))
        if exchange.get("is_end"):
            latest[key] = (exchange.get("item_name", ""), partial.pop(key))

    rows = []
    for (server_type, item_index), (item_name, entries) in latest.items():
        for entry in entries:
            item = entry["item_info"]
            if item["index"] != item_index:
                raise DecodeError(
                    f"detailed market item mismatch: requested {item_index}, received {item['index']}"
                )
            rows.append({
                "RowType": "offer",
                "ServerType": server_type,
                "ListingId": entry["exchange_index"],
                "Name": item_name,
                "ItemIndex": item_index,
                "Enhance": item["enchant_level"],
                "PricePerUnit": entry["selling_price"],
                "Qty": item["count"],
                "HighestPrice": entry["selling_price"],
            })
    return rows


def write_market_csv(path: Path, infos: list[dict[str, Any]]) -> int:
    rows = latest_market_rows(infos) + latest_market_offer_rows(infos)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)
    return len(rows)


def self_test() -> None:
    assert _network_payload(b"\0" * 12 + b"\x08\x00IP", 1) == (0x0800, b"IP")
    assert _network_payload(b"\0" * 14 + b"\x08\x00IP", 113) == (0x0800, b"IP")
    assert _merge_tcp_segments(
        [(10, b"abc", 1), (13, b"def", 2), (12, b"cde", 3)]
    ) == [(b"abcdef", [(3, 1), (5, 3), (6, 2)])]
    payload = b"market-test"
    plain = bytearray(HEADER_SIZE + len(payload))
    plain[1:3] = len(plain).to_bytes(2, "little")
    plain[3] = 7
    plain[4:6] = (0x1D17).to_bytes(2, "little")
    plain[6:] = payload
    wire = apply_rolling_xor(bytes(plain), 0x2A)
    decoded, info = decode_frame(wire)
    expected = bytearray(plain)
    expected[0] = 0x2A  # the low six bits retain the random seed
    assert decoded == bytes(expected)
    assert info["opcode"] == 0x1D17
    # One LZ4 literal-only sequence containing "abc".
    assert lz4_block_decompress(b"\x30abc") == b"abc"
    compressed = bytearray(b"\x40\x00\x00\x08\x02\x1d\x30abc")
    compressed[1:3] = len(compressed).to_bytes(2, "little")
    expanded, compressed_info = decode_frame(bytes(compressed))
    assert expanded[0] & 0x40 == 0
    assert expanded[6:] == b"abc"
    assert int.from_bytes(expanded[1:3], "little") == len(expanded)
    assert compressed_info["compressed"] is True
    assert len(decode_stream(wire + bytes(compressed))) == 2
    exp_frame = bytearray(HEADER_SIZE + 24)
    exp_frame[1:3] = len(exp_frame).to_bytes(2, "little")
    exp_frame[4:6] = (0x0307).to_bytes(2, "little")
    exp_frame[6:] = struct.pack("<HHHHqq", 1001, 65, 65, 65, 9000, 123)
    parsed_exp = parse_observation_payload(exp_frame)
    assert parsed_exp["gain_exp"] == 123
    assert parsed_exp["action_name"] == "ACTION_CODE_MODE_REWARD"
    unit = APPEAR_UNIT.pack(1, 0, 0, 305208, 32560, 32560, *(0.0,) * 3, 0, 1.0, 13, *(0.0,) * 3, 22, 100, 100, 0)
    appear_frame = bytearray(HEADER_SIZE + 2 + len(unit))
    appear_frame[4:6] = (0x0307).to_bytes(2, "little")
    appear_frame[6:] = struct.pack("<H", 1) + unit
    parsed_unit = parse_observation_payload(appear_frame)["units"][0]
    assert parsed_unit["npc_index"] == 305208
    assert parsed_unit["realm_name"] == "REALM_MONSTER"
    assert parsed_unit["flag_names"] == [
        "FIELD_MONSTER_FLAG_ACTIVATE",
        "FIELD_MONSTER_FLAG_REGEN",
        "FIELD_MONSTER_FLAG_ALIVE",
    ]
    player_name = "Carvalho"
    player_state = APPEAR_PLAYER_STATE.pack(
        77, 2, 1000, 750, 200, 150, 0, 1.0, 2.0, 3.0
    )
    player_tail = bytearray(APPEAR_PLAYER_TAIL_SIZE - APPEAR_PLAYER_STATE.size)
    struct.pack_into("<Q", player_tail, 43, 612_606_160_000_006)
    player_payload = (
        struct.pack("<H", 1)
        + APPEAR_PLAYER_PREFIX.pack(
            123456, 0, 2075041, 0, 900001, 0, len(player_name)
        )
        + player_name.encode("utf-16le")
        + player_state
        + player_tail
    )
    player_frame = bytearray(HEADER_SIZE + len(player_payload))
    player_frame[4:6] = (0x0305).to_bytes(2, "little")
    player_frame[6:] = player_payload
    parsed_player = parse_observation_payload(player_frame)["units"][0]
    assert parsed_player["character_uid"] == 123456
    assert parsed_player["uid"] == 77
    assert parsed_player["current_hp"] == 750
    assert parsed_player["guild_id"] == 612_606_160_000_006
    guild_name = "McDonalds".encode("utf-16le")
    representative_name = "monkeybones".encode("utf-16le")
    guild_payload = (
        struct.pack("<HQHQH", 0, 612_606_160_000_006, 1, 612_606_160_000_043, 9)
        + guild_name
        + struct.pack("<BHBBH", 8, 137, 5, 86, 11)
        + representative_name
        + struct.pack("<H", 5013)
    )
    guild_frame = bytearray(HEADER_SIZE + len(guild_payload))
    guild_frame[4:6] = (0x0D3F).to_bytes(2, "little")
    guild_frame[6:] = guild_payload
    guild_list = parse_guild_relation_payload(guild_frame)
    assert guild_list["guilds"][0]["guild_name"] == "McDonalds"
    restore_frame = bytearray(HEADER_SIZE + RESTORE_HP_FP.size)
    restore_frame[4:6] = (0x0311).to_bytes(2, "little")
    restore_frame[6:] = RESTORE_HP_FP.pack(77, 800, 1000, 50, 160, 200, 10, 1)
    parsed_restore = parse_observation_payload(restore_frame)
    assert parsed_restore["current_hp"] == 800
    assert parsed_restore["max_hp"] == 1000
    drop_frame = bytearray(HEADER_SIZE + 4 + DROP_RESULT.size)
    drop_frame[4:6] = (0x040A).to_bytes(2, "little")
    drop_frame[6:] = struct.pack("<HH", 0, 1) + DROP_RESULT.pack(0, 275000, 1, 2, 3, 1001)
    assert parse_observation_payload(drop_frame)["results"][0]["item_index"] == 275000
    effect = SKILL_EFFECT_RESULT.pack(6, *(0.0,) * 6, 0, 0, 123, 456, 0, 0, 0, 0)
    skill_payload = USE_SKILL_PREFIX.pack(
        0, 1, 2, 3, 4, 5, *(0.0,) * 6, 6, *(0.0,) * 3, 100, 20, 30, 1
    ) + effect
    skill_frame = bytearray(HEADER_SIZE + len(skill_payload))
    skill_frame[4:6] = (0x0602).to_bytes(2, "little")
    skill_frame[6:] = skill_payload
    skill_result = parse_observation_payload(skill_frame)
    assert skill_result["caster_uid"] == 2
    assert skill_result["effect_results"][0]["hp_damage"] == 123
    assert skill_result["effect_results"][0]["final_hp"] == 456
    normal_effect = NORMAL_SKILL_EFFECT_RESULT.pack(
        7, *(0.0,) * 3, 0, 0, 321, 654, 0, 0
    )
    normal_payload = NORMAL_SKILL_PREFIX.pack(
        0, 1, 2, *(0.0,) * 3, 3, 4, 7, 0, 100, 1
    ) + normal_effect
    normal_frame = bytearray(HEADER_SIZE + len(normal_payload))
    normal_frame[4:6] = (0x060D).to_bytes(2, "little")
    normal_frame[6:] = normal_payload
    normal_result = parse_observation_payload(normal_frame)
    assert normal_result["main_target_uid"] == 7
    assert normal_result["effect_results"][0]["hp_damage"] == 321
    bundle = bytearray(HEADER_SIZE + 2 + len(exp_frame))
    bundle[4:6] = (0x010A).to_bytes(2, "little")
    bundle[6:] = struct.pack("<H", len(exp_frame)) + exp_frame
    assert len(expand_bundle(bundle, {"opcode": 0x010A})) == 2
    price_payload = struct.pack("<HIHddB", 0, 123456, 9, 1500.25, 1499.0, 2)
    price_frame = bytearray(HEADER_SIZE + len(price_payload))
    price_frame[1:3] = len(price_frame).to_bytes(2, "little")
    price_frame[4:6] = (0x1D17).to_bytes(2, "little")
    price_frame[6:] = price_payload
    price = parse_exchange_payload(bytes(price_frame))
    assert price is not None
    assert price["market_price_info"]["item_index"] == 123456
    assert price["market_price_info"]["enchant_level"] == 9
    assert price["market_price_info"]["weekly_average_selling_price"] == 1500.25
    recommended_payload = struct.pack("<BHIHHIH", 2, 1, 50, 5, 1, 51, 6)
    recommended_frame = bytearray(HEADER_SIZE + len(recommended_payload))
    recommended_frame[4:6] = (0x1D18).to_bytes(2, "little")
    recommended_frame[6:] = recommended_payload
    recommended = parse_exchange_payload(bytes(recommended_frame))
    assert recommended is not None
    assert recommended["recommended_item_info"]["most_sold_in_one_week_item_info"][0] == {
        "item_index": 50,
        "enchant_level": 5,
    }
    purchase_payload = struct.pack("<HBBH", 0, 1, 2, 1) + struct.pack(
        "<IHddI", 10, 11, 12.5, 13.75, 14
    )
    purchase_frame = bytearray(HEADER_SIZE + len(purchase_payload))
    purchase_frame[1:3] = len(purchase_frame).to_bytes(2, "little")
    purchase_frame[4:6] = (0x1D02).to_bytes(2, "little")
    purchase_frame[6:] = purchase_payload
    purchase = parse_exchange_payload(bytes(purchase_frame))
    assert purchase is not None
    assert purchase["is_end"] is True
    first_purchase = purchase["exchange_item_simple_infos"][0]
    assert first_purchase["lowest_price"] == 12.5
    assert first_purchase["highest_price"] == 13.75
    assert first_purchase["number_of_registered_items"] == 14
    item_info = (
        struct.pack("<QIQBH", 21, 22, 23, 1, 24)
        + struct.pack("<HII", 2, 25, 26)
        + struct.pack("<HIfB", 1, 27, 28.5, 1)
        + struct.pack("<BQ", 0, 29)
    )
    detail_entry = (
        struct.pack("<QQQ", 30, 31, 32)
        + item_info
        + struct.pack("<QQQQQB", 33, 34, 35, 36, 37, 1)
    )
    detail_payload = struct.pack("<HIBBH", 0, 22, 1, 2, 1) + detail_entry
    detail_frame = bytearray(HEADER_SIZE + len(detail_payload))
    detail_frame[1:3] = len(detail_frame).to_bytes(2, "little")
    detail_frame[4:6] = (0x1D04).to_bytes(2, "little")
    detail_frame[6:] = detail_payload
    detail = parse_exchange_payload(bytes(detail_frame))
    assert detail is not None
    first_detail = detail["detailed_list"][0]
    assert first_detail["selling_price"] == 36
    assert first_detail["item_info"]["talic_indices"] == [25, 26]
    assert first_detail["item_info"]["item_options"][0]["value"] == 28.5
    detail["item_name"] = "Item teste"
    offer = latest_market_offer_rows([{"exchange": detail}])[0]
    assert offer["PricePerUnit"] == 36 and offer["Qty"] == 23
    try:
        parse_exchange_payload(bytes(detail_frame[:-1]))
    except DecodeError:
        pass
    else:
        raise AssertionError("truncated 0x1d04 payload was accepted")
    sales_payload = struct.pack("<HBH", 0, 2, 1) + detail_entry
    sales_frame = bytearray(HEADER_SIZE + len(sales_payload))
    sales_frame[4:6] = (0x1D07).to_bytes(2, "little")
    sales_frame[6:] = sales_payload
    sales = parse_exchange_payload(bytes(sales_frame))
    assert sales is not None and sales["my_sales_list"][0]["selling_price"] == 36
    sales_frame[4:6] = (0x1D09).to_bytes(2, "little")
    settlements = parse_exchange_payload(bytes(sales_frame))
    assert settlements is not None
    assert settlements["my_settlement_list"][0]["settlement_price"] == 37
    history_payload = (
        struct.pack("<HBHI", 0, 2, 1, 3)
        + detail_entry
        + struct.pack("<HIQQQ", 1, 4, 5, 6, 7)
    )
    history_frame = bytearray(HEADER_SIZE + len(history_payload))
    history_frame[4:6] = (0x1D0B).to_bytes(2, "little")
    history_frame[6:] = history_payload
    history = parse_exchange_payload(bytes(history_frame))
    assert history is not None
    assert history["my_transaction_history"][0]["exchange_type"] == 3
    assert history["my_transaction_statistics"][0]["sum_exchange_price"] == 7
    reregistration_payload = struct.pack("<HB", 0, 2) + detail_entry
    reregistration_frame = bytearray(HEADER_SIZE + len(reregistration_payload))
    reregistration_frame[6:] = reregistration_payload
    reregistration_frame[4:6] = (0x1D0D).to_bytes(2, "little")
    registration = parse_exchange_payload(bytes(reregistration_frame))
    assert registration is not None
    assert registration["exchange_item_info"]["selling_price"] == 36
    reregistration_frame[4:6] = (0x1D11).to_bytes(2, "little")
    reregistration = parse_exchange_payload(bytes(reregistration_frame))
    assert reregistration is not None
    assert reregistration["exchange_item_info"]["selling_price"] == 36
    cancellation_payload = struct.pack("<HBQ", 0, 2, 39)
    cancellation_frame = bytearray(HEADER_SIZE + len(cancellation_payload))
    cancellation_frame[4:6] = (0x1D0F).to_bytes(2, "little")
    cancellation_frame[6:] = cancellation_payload
    cancellation = parse_exchange_payload(bytes(cancellation_frame))
    assert cancellation is not None and cancellation["exchange_index"] == 39
    purchase_result_payload = struct.pack("<HBHH", 0, 2, 1, 38) + detail_entry
    purchase_result_frame = bytearray(HEADER_SIZE + len(purchase_result_payload))
    purchase_result_frame[4:6] = (0x1D13).to_bytes(2, "little")
    purchase_result_frame[6:] = purchase_result_payload
    purchase_result = parse_exchange_payload(bytes(purchase_result_frame))
    assert purchase_result is not None
    assert purchase_result["purchase_results"][0]["ret"] == 38
    settlement_payload = struct.pack("<HBHQQHQQ", 0, 2, 2, 40, 41, 1, 42, 43)
    settlement_frame = bytearray(HEADER_SIZE + len(settlement_payload))
    settlement_frame[4:6] = (0x1D15).to_bytes(2, "little")
    settlement_frame[6:] = settlement_payload
    settlement = parse_exchange_payload(bytes(settlement_frame))
    assert settlement is not None
    assert settlement["exchange_index_list"] == [40, 41]
    assert settlement["respond_settlement_infos"][0]["selling_price"] == 43
    bookmark_payload = struct.pack("<HBBHIH", 0, 1, 2, 1, 52, 7)
    bookmark_frame = bytearray(HEADER_SIZE + len(bookmark_payload))
    bookmark_frame[4:6] = (0x1D1A).to_bytes(2, "little")
    bookmark_frame[6:] = bookmark_payload
    bookmark = parse_exchange_payload(bytes(bookmark_frame))
    assert bookmark is not None
    assert bookmark["bookmark_info_list"][0]["item_index"] == 52
    sold_payload = struct.pack("<BHQQ", 2, 2, 44, 45)
    sold_frame = bytearray(HEADER_SIZE + len(sold_payload))
    sold_frame[4:6] = (0x1D1B).to_bytes(2, "little")
    sold_frame[6:] = sold_payload
    sold = parse_exchange_payload(bytes(sold_frame))
    assert sold is not None and sold["exchange_indices"] == [44, 45]
    market_infos = [
        {"exchange": {"message": "FL2C_respond_purchase_list_on_exchange_Message", "ret": 0,
                      "is_end": False, "exchange_server_type": 0,
                      "exchange_item_simple_infos": [first_purchase]}},
        {"exchange": {"message": "FL2C_respond_purchase_list_on_exchange_Message", "ret": 0,
                      "is_end": True, "exchange_server_type": 1,
                      "exchange_item_simple_infos": [{**first_purchase, "item_index": 11}]}},
        {"exchange": {"message": "FL2C_respond_purchase_list_on_exchange_Message", "ret": 0,
                      "is_end": True, "exchange_server_type": 0,
                      "exchange_item_simple_infos": [{**first_purchase, "item_index": 12}]}},
    ]
    market_rows = latest_market_rows(market_infos)
    assert [(row["ServerType"], row["ItemIndex"]) for row in market_rows] == [
        (0, 10), (0, 12), (1, 11)
    ]
    assert market_rows[0]["PricePerUnit"] == 12.5 and market_rows[0]["Qty"] == 14
    # 0x1e06-0x1e08: progresso e recompensa de missao de evento.
    event_frame = bytearray(HEADER_SIZE + EVENT_MISSION_PROGRESS_UPDATE.size)
    event_frame[4:6] = (0x1E06).to_bytes(2, "little")
    event_frame[6:] = EVENT_MISSION_PROGRESS_UPDATE.pack(
        4502, 6150132606160031134, 40014310, 2, 4807, 0
    )
    event = parse_event_mission_payload(bytes(event_frame))
    assert event["fields"]["character_uid@2"] == 6150132606160031134
    assert event["fields"]["event_mission_group@10"] == 40014310
    reward_request = bytearray(HEADER_SIZE + EVENT_MISSION_REWARD_REQUEST.size)
    reward_request[4:6] = (0x1E07).to_bytes(2, "little")
    reward_request[6:] = EVENT_MISSION_REWARD_REQUEST.pack(40014310, 2)
    request = parse_event_mission_payload(bytes(reward_request))
    assert request["fields"]["objective_index@4"] == 2
    reward_response = bytearray(HEADER_SIZE + 42)
    reward_response[4:6] = (0x1E08).to_bytes(2, "little")
    reward_response[6:] = EVENT_MISSION_REWARD_RESPONSE_PREFIX.pack(
        0, 40014310, 2
    ) + bytes(32)
    response = parse_event_mission_payload(bytes(reward_response))
    assert response["fields"]["result_code@0"] == 0
    assert parse_event_mission_payload(bytes(reward_response[:-1])) is None
    # trackA2: 0x1e12 battlepass mission update (27B, layout validado em captura)
    mission_payload = BATTLEPASS_MISSION_UPDATE.pack(4525, 6150132606160031134, 400014454, 7, 38097, 0, 0)
    mission_frame = bytearray(HEADER_SIZE + len(mission_payload))
    mission_frame[4:6] = (0x1E12).to_bytes(2, "little")
    mission_frame[6:] = mission_payload
    mission = parse_1e12_payload(bytes(mission_frame))
    assert mission is not None
    assert mission["fields"]["progress@18"] == 38097
    assert mission["fields"]["objective_index@14"] == 7
    assert mission["fields"]["completed@26"] is False
    assert parse_1e12_payload(bytes(mission_frame[:-1])) is None  # 26B nao casa
    # trackA2: 0x2302 exploration activate (80B, best-effort com header tentativo)
    exploration_payload = bytes(80)
    exploration_frame = bytearray(HEADER_SIZE + len(exploration_payload))
    exploration_frame[4:6] = (0x2302).to_bytes(2, "little")
    exploration_frame[6:] = exploration_payload
    exploration = parse_2302_payload(bytes(exploration_frame))
    assert exploration is not None
    assert exploration["payload_len"] == 80
    assert "header_job1_tentativo" in exploration
    assert exploration["confidence"].startswith("baixa")
    # Login/session: rotula 12000, nunca inclui o payload sensivel na saida.
    secret = b"SELF_TEST_SECRET_MUST_NOT_LEAK"
    login_frame = bytearray(HEADER_SIZE + len(secret))
    login_frame[4:6] = (0x0101).to_bytes(2, "little")
    login_frame[6:] = secret
    login = parse_login_session_payload(bytes(login_frame), 12000)
    assert login is not None and login["type"] == "ask_connection"
    assert login["sensitive_payload"] is True
    assert secret.decode() not in json.dumps(login)
    assert parse_login_session_payload(bytes(login_frame), 12020) is None
    truncated_character = bytearray(HEADER_SIZE + 2)
    truncated_character[4:6] = (0x010D).to_bytes(2, "little")
    truncated_character[6:] = (1).to_bytes(2, "little")
    truncated = parse_login_session_payload(bytes(truncated_character), 12000)
    assert truncated is not None and truncated["field_decode"] == "layout-mismatch"
    world_payload = (
        struct.pack("<HHQHH", 0, 2, 7, 66, 8)
        + "Carvalho".encode("utf-16le")
        + b"\0"
        + struct.pack("<I", 2075041)
    )
    world_frame = bytearray(HEADER_SIZE + len(world_payload))
    world_frame[4:6] = (0x0106).to_bytes(2, "little")
    world_frame[6:] = world_payload
    world = parse_marked_gameplay_payload(bytes(world_frame), 12020)
    assert world["fields"]["character_name"] == "Carvalho"
    assert world["fields"]["biosuit_item_index"] == 2075041
    assert world["fields"]["level"] == 66
    biosuit_request_frame = bytearray(HEADER_SIZE + 4)
    biosuit_request_frame[4:6] = (0x1303).to_bytes(2, "little")
    biosuit_request_frame[6:] = struct.pack("<I", 2_055_041)
    biosuit_request = parse_marked_gameplay_payload(
        bytes(biosuit_request_frame), 12020
    )
    assert biosuit_request["fields"]["biosuit_item_index"] == 2_055_041
    biosuit_response_frame = bytearray(HEADER_SIZE + 15)
    biosuit_response_frame[4:6] = (0x1304).to_bytes(2, "little")
    biosuit_response_frame[6:] = struct.pack(
        "<HIQB", 0, 2_055_041, 457_063_468_049_408, 0
    )
    biosuit_response = parse_marked_gameplay_payload(
        bytes(biosuit_response_frame), 12020
    )
    assert biosuit_response["fields"] == {
        "result": 0,
        "biosuit_item_index": 2_055_041,
        "f6_u64_raw": 457_063_468_049_408,
        "f14_u8_raw": 0,
    }
    assert (
        parse_marked_gameplay_payload(bytes(biosuit_response_frame[:-1]), 12020)
        is None
    )
    player_payload = (
        struct.pack("<QH", 7, 8)
        + "Carvalho".encode("utf-16le")
        + struct.pack("<H", 66)
        + bytes(36)
        + struct.pack("<Q", 3753)
    )
    player_frame = bytearray(HEADER_SIZE + len(player_payload))
    player_frame[4:6] = (0x0305).to_bytes(2, "little")
    player_frame[6:] = player_payload
    player = parse_marked_gameplay_payload(bytes(player_frame), 12020)
    assert player["fields"]["diamonds"] == 3753
    equipped_uid = bytes.fromhex("a0250838d001")
    full_player_payload = bytearray(player_payload[:26] + bytes(1042))
    struct.pack_into("<Q", full_player_payload, 26 + 38, 3753)
    refs_offset = len(full_player_payload) - 203
    struct.pack_into("<I", full_player_payload, refs_offset - 10, 2_075_041)
    struct.pack_into("<I", full_player_payload, refs_offset - 5, 4_400_008)
    struct.pack_into("<H", full_player_payload, refs_offset, 15)
    full_player_payload[refs_offset + 2:refs_offset + 8] = equipped_uid
    full_player_frame = bytearray(HEADER_SIZE + len(full_player_payload))
    full_player_frame[4:6] = (0x0305).to_bytes(2, "little")
    full_player_frame[6:] = full_player_payload
    full_player = parse_marked_gameplay_payload(bytes(full_player_frame), 12020)
    assert full_player["fields"]["biosuit_item_index"] == 2_075_041
    assert full_player["fields"]["rover_item_index"] == 4_400_008
    assert full_player["fields"]["equipment_refs"][0]["item_uid_hex"] == equipped_uid.hex()
    legacy_player_payload = bytearray(player_payload[:26] + bytes(1034))
    legacy_refs_offset = len(legacy_player_payload) - 195
    legacy_player_payload[legacy_refs_offset + 2:legacy_refs_offset + 8] = equipped_uid
    legacy_player_frame = bytearray(HEADER_SIZE + len(legacy_player_payload))
    legacy_player_frame[4:6] = (0x0305).to_bytes(2, "little")
    legacy_player_frame[6:] = legacy_player_payload
    legacy_player = parse_marked_gameplay_payload(bytes(legacy_player_frame), 12020)
    assert legacy_player["fields"]["equipment_refs"][0]["item_uid_hex"] == equipped_uid.hex()
    profile_item = (
        struct.pack("<H", 15)
        + equipped_uid
        + struct.pack("<IQBH", 1_002_279, 1, 1, 8)
        + struct.pack("<HIIH", 2, 161_049, 160_948, 0)
        + struct.pack("<BQ", 0, 0)
    )
    profile_payload = struct.pack("<BH", 1, 1) + profile_item
    profile_frame = bytearray(HEADER_SIZE + len(profile_payload))
    profile_frame[4:6] = (0x0403).to_bytes(2, "little")
    profile_frame[6:] = profile_payload
    profile = parse_marked_gameplay_payload(bytes(profile_frame), 12020)
    assert profile["fields"]["items"][0]["item_index"] == 1_002_279
    assert profile["fields"]["items"][0]["enchant_level"] == 8
    correlated = correlate_active_equipment(profile, [full_player])
    assert correlated is not None
    active, _ = correlated
    assert active["complete"] is True
    assert active["slots"][0]["item"]["item_index"] == 1_002_279
    rover_request_frame = bytearray(HEADER_SIZE + 4)
    rover_request_frame[4:6] = (0x1402).to_bytes(2, "little")
    rover_request_frame[6:] = struct.pack("<I", 4_300_017)
    rover_request = parse_marked_gameplay_payload(
        bytes(rover_request_frame), 12020
    )
    assert rover_request["type"] == "change_rover_request"
    assert rover_request["fields"]["rover_item_index"] == 4_300_017
    assert (
        parse_marked_gameplay_payload(bytes(rover_request_frame), 12010)
        is None
    )
    rover_response_frame = bytearray(HEADER_SIZE + 7)
    rover_response_frame[4:6] = (0x1403).to_bytes(2, "little")
    rover_response_frame[6:] = struct.pack("<HIB", 0, 4_300_017, 0)
    rover_response = parse_marked_gameplay_payload(
        bytes(rover_response_frame), 12020
    )
    assert rover_response["type"] == "change_rover_response"
    assert rover_response["fields"] == {
        "result": 0,
        "rover_item_index": 4_300_017,
        "trailing_state_raw": 0,
    }
    assert (
        parse_marked_gameplay_payload(bytes(rover_response_frame[:-1]), 12020)
        is None
    )
    equip_payload = bytearray(75)
    struct.pack_into("<Q", equip_payload, 0, 6_150_132_606_160_031_134)
    struct.pack_into("<I", equip_payload, 18, 4_400_011)
    equip_frame = bytearray(HEADER_SIZE + len(equip_payload))
    equip_frame[4:6] = (0x0407).to_bytes(2, "little")
    equip_frame[6:] = equip_payload
    equip = parse_marked_gameplay_payload(bytes(equip_frame), 12010)
    assert equip["type"] == "player_equip_update"
    assert equip["fields"] == {
        "character_uid": 6_150_132_606_160_031_134,
        "rover_item_index": 4_400_011,
    }
    assert parse_marked_gameplay_payload(bytes(equip_frame), 12020) is None
    assert (
        parse_marked_gameplay_payload(bytes(equip_frame[:-1]), 12010) is None
    )
    salvage_payload = struct.pack("<H", 1) + SALVAGE_ITEM.pack(9, 1002416, 1)
    salvage_frame = bytearray(HEADER_SIZE + len(salvage_payload))
    salvage_frame[4:6] = (0x0413).to_bytes(2, "little")
    salvage_frame[6:] = salvage_payload
    salvage = parse_marked_gameplay_payload(bytes(salvage_frame), 12020)
    assert salvage["items"] == [{"item_uid": 9, "item_index": 1002416, "count": 1}]
    sweep_frame = bytearray(HEADER_SIZE + 5)
    sweep_frame[4:6] = (0x2801).to_bytes(2, "little")
    sweep_frame[6:] = struct.pack("<IB", 540, 0)
    assert parse_marked_gameplay_payload(bytes(sweep_frame), 12020)["stage_id"] == 540
    contribution_payload = bytearray(33)
    contribution_payload[7:15] = (56_094_529).to_bytes(8, "little", signed=True)
    contribution_frame = bytearray(HEADER_SIZE + len(contribution_payload))
    contribution_frame[4:6] = (0x2407).to_bytes(2, "little")
    contribution_frame[6:] = contribution_payload
    contribution = parse_marked_gameplay_payload(bytes(contribution_frame), 12020)
    assert contribution["contribution_total"] == 56_094_529
    collection_request_payload = bytes.fromhex(
        "e486010001010e00080e5c38d00100"
    )
    collection_request_frame = bytearray(HEADER_SIZE + len(collection_request_payload))
    collection_request_frame[4:6] = (0x0417).to_bytes(2, "little")
    collection_request_frame[6:] = collection_request_payload
    collection_request = parse_collection_payload(bytes(collection_request_frame))
    assert collection_request["collection_index"] == 100_068
    assert collection_request["slot_index"] == 1
    assert collection_request["item_uid"] == 130_666_357_217_296_398
    collection_response_payload = bytes.fromhex(
        "00000101e486010001"
        "00000000000000000100000000000000"
        + "0000000000000000" * 8
        + "0e00080e5c38d00100"
    )
    collection_response_frame = bytearray(HEADER_SIZE + len(collection_response_payload))
    collection_response_frame[4:6] = (0x0418).to_bytes(2, "little")
    collection_response_frame[6:] = collection_response_payload
    collection_response = parse_collection_payload(bytes(collection_response_frame))
    assert collection_response["updated_slot_value"] == 1
    assert collection_response["item_uid"] == collection_request["item_uid"]
    add_collection_catalog(
        collection_response,
        {
            (100_068, 0): {"required_quantity": 1},
            (100_068, 1): {"required_quantity": 1},
            (100_068, 2): {"required_quantity": 1},
        },
    )
    assert collection_response["item_complete"] is True
    assert collection_response["collection_complete"] is False
    assert collection_response["incomplete_slots"] == [0, 2]
    snapshot_payload = COLLECTION_SNAPSHOT_HEADER.pack(1, 1, 2) + b"".join(
        (
            COLLECTION_SNAPSHOT_RECORD.pack(100_068, 1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0),
            COLLECTION_SNAPSHOT_RECORD.pack(200_059, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0),
        )
    )
    snapshot_frame = bytearray(HEADER_SIZE + len(snapshot_payload))
    snapshot_frame[4:6] = (0x0419).to_bytes(2, "little")
    snapshot_frame[6:] = snapshot_payload
    snapshot = parse_collection_payload(bytes(snapshot_frame))
    assert snapshot["is_end"] is True and snapshot["record_count"] == 2
    assert snapshot["records"][1]["slot_values"][:4] == [1, 1, 1, 1]
    add_collection_catalog(
        snapshot,
        {
            (100_068, 0): {
                "collection_name_ptbr": "Teste",
                "required_quantity": 1,
            },
            (100_068, 1): {
                "collection_name_ptbr": "Teste",
                "required_quantity": 1,
            },
        },
    )
    assert snapshot["records"][0]["completed_slots"] == [1]
    assert snapshot["records"][0]["incomplete_slots"] == [0]
    assert snapshot["records"][1]["catalog_known"] is False
    verify_blob = (
        bytes.fromhex("423d2a73237e4a88b702e30ed58c51f7")
        + struct.pack("<IQI", 0x3320, 1, 0)
        + b"win x64 Nov 20 2025 17:27:11\0"
    ).ljust(512, b"\0")
    verify_payload = struct.pack("<H", len(verify_blob)) + verify_blob
    verify_frame = bytearray(HEADER_SIZE + len(verify_payload))
    verify_frame[4:6] = (0x0219).to_bytes(2, "little")
    verify_frame[6:] = verify_payload
    verify = parse_nmssw_payload(bytes(verify_frame))
    assert verify["verify_length"] == 512
    assert verify["fields"]["client_build"] == "win x64 Nov 20 2025 17:27:11"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="application stream or PCAP")
    parser.add_argument("--out-dir", type=Path, help="write each decoded frame as a .bin file")
    parser.add_argument("--output", type=Path, help="write JSON Lines instead of stdout")
    parser.add_argument("--pcap", action="store_true", help="reassemble TCP streams from a PCAP")
    parser.add_argument("--port", type=int, default=12020, help="TCP port used with --pcap")
    parser.add_argument("--exchange-only", action="store_true")
    parser.add_argument("--only-opcode", type=lambda value: int(value, 0), action="append")
    parser.add_argument("--items-csv", type=Path, help="CSV with ItemIndex and NamePTBR")
    parser.add_argument(
        "--collection-requirements-csv",
        type=Path,
        help="CSV exported as collection_requirements.csv",
    )
    parser.add_argument("--market-csv", type=Path, help="write the latest complete 0x1D02 list for the site")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("self-test: ok")
        return 0
    if args.input is None:
        parser.error("input is required unless --self-test is used")

    streams = (
        pcap_tcp_streams(args.input, args.port)
        if args.pcap
        else [("", args.input.read_bytes(), [])]
    )
    names = load_item_names(args.items_csv)
    collection_slots = load_collection_slots(args.collection_requirements_csv)
    appearances_by_flow: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
    infos = []
    index = 0
    for flow, stream, time_spans in streams:
        time_cursor = 0
        for outer_decoded, outer_info in decode_stream(stream):
            if time_spans:
                frame_end = outer_info["stream_offset"] + outer_info["wire_length"]
                while (
                    time_cursor + 1 < len(time_spans)
                    and time_spans[time_cursor][0] < frame_end
                ):
                    time_cursor += 1
                outer_info["pcap_time_ns"] = time_spans[time_cursor][1]
            for decoded, info in expand_bundle(outer_decoded, outer_info):
                parsed = parse_exchange_payload(decoded)
                if parsed is not None:
                    add_item_names(parsed, names)
                    info["exchange"] = parsed
                observation = parse_observation_payload(decoded)
                if observation is not None:
                    if observation["type"] == "drop_item_field":
                        for result in observation["results"]:
                            name = names.get(result["item_index"])
                            if name:
                                result["item_name_ptbr"] = name
                    info["observation"] = observation
                inventory = parse_inventory_payload(decoded)
                if inventory is not None:
                    for item in inventory.get("items", [inventory.get("item")]):
                        if item:
                            name = names.get(item["item_index"])
                            if name:
                                item["item_name_ptbr"] = name
                    info["inventory"] = inventory
                guild_relation = parse_guild_relation_payload(decoded)
                if guild_relation is not None:
                    info["guild_relation"] = guild_relation
                collection = parse_collection_payload(decoded)
                if collection is not None:
                    add_collection_catalog(collection, collection_slots)
                    info["collection"] = collection
                nmssw = parse_nmssw_payload(decoded)
                if nmssw is not None:
                    info["decoded"] = nmssw
                login_session = parse_login_session_payload(decoded, args.port)
                if (
                    parsed is None
                    and observation is None
                    and collection is None
                    and nmssw is None
                    and login_session is not None
                ):
                    info["decoded"] = login_session
                marked_gameplay = parse_marked_gameplay_payload(decoded, args.port)
                if marked_gameplay is not None:
                    flow_key = flow or f"port:{args.port}"
                    if marked_gameplay["type"] == "appear_player_prefix":
                        if marked_gameplay.get("fields", {}).get("equipment_refs"):
                            appearances_by_flow[flow_key].append(marked_gameplay)
                            appearances_by_flow[flow_key] = appearances_by_flow[flow_key][-64:]
                    elif marked_gameplay["type"] == "player_profile_info":
                        add_profile_item_names(marked_gameplay, names)
                        correlated = correlate_active_equipment(
                            marked_gameplay, appearances_by_flow[flow_key]
                        )
                        if correlated is not None:
                            active_equipment, appearance = correlated
                            marked_gameplay["fields"]["active_equipment"] = active_equipment
                            appearance["fields"]["active_equipment"] = active_equipment
                if (
                    parsed is None
                    and observation is None
                    and collection is None
                    and nmssw is None
                    and "decoded" not in info
                    and marked_gameplay is not None
                ):
                    info["decoded"] = marked_gameplay
                # Job 1 e fallback: so quando exchange e observacao nao casaram e o
                # opcode esta na tabela de layouts recuperada. Nunca sobrescreve nada.
                if (
                    parsed is None
                    and observation is None
                    and collection is None
                    and nmssw is None
                    and "decoded" not in info
                    and info["opcode"] in LAYOUTS
                ):
                    job1 = parse_job1_payload(decoded)
                    if job1 is not None:
                        info["decoded"] = job1
                # trackA2: decoders inferidos por captura. Ultimo
                # fallback: so quando nada casou e sem sobrescrever info["decoded"].
                if (
                    parsed is None
                    and observation is None
                    and collection is None
                    and nmssw is None
                    and "decoded" not in info
                ):
                    trackA2 = (
                        parse_event_mission_payload(decoded)
                        or parse_1e12_payload(decoded)
                        or parse_2302_payload(decoded)
                    )
                    if trackA2 is not None:
                        info["decoded"] = trackA2
                if args.exchange_only and parsed is None:
                    continue
                if args.only_opcode and info["opcode"] not in args.only_opcode:
                    continue
                if flow:
                    info["flow"] = flow
                if args.out_dir:
                    target = args.out_dir / f"frame-{index:04d}-opcode-{info['opcode']:04x}.bin"
                    target.write_bytes(decoded)
                    info["output"] = str(target)
                infos.append(info)
                index += 1
    if args.market_csv:
        write_market_csv(args.market_csv, infos)
    lines = [json.dumps(info, ensure_ascii=False, sort_keys=True) for info in infos]
    output = "\n".join(lines) + ("\n" if lines else "")
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DecodeError as exc:
        print(f"decode error: {exc}", file=sys.stderr)
        raise SystemExit(2)
