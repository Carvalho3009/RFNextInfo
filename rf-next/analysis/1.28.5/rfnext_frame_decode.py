#!/usr/bin/env python3
"""Decode RF Online NEXT application frames recovered from libUnreal.so 1.28.5."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import socket
import struct
import sys
from pathlib import Path
from typing import Any


MAX_FRAME = 0xFFFF
HEADER_SIZE = 6
APPEAR_UNIT = struct.Struct("<IIQIQQfffBfBfffBIIQ")
DROP_RESULT = struct.Struct("<HIqqqH")
USE_SKILL_PREFIX = struct.Struct("<HBIIIBffffffIfffqIIH")
SKILL_EFFECT_RESULT = struct.Struct("<IffffffBqqqIIBI")
NORMAL_SKILL_PREFIX = struct.Struct("<HBIfffIIIBqH")
NORMAL_SKILL_EFFECT_RESULT = struct.Struct("<IfffBqqqBI")
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


def parse_observation_payload(decoded: bytes) -> dict[str, Any] | None:
    opcode = int.from_bytes(decoded[4:6], "little")
    payload = decoded[HEADER_SIZE:]
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
        if network[9] != 6 or len(network) < ihl + 20:
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


def latest_market_rows(infos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    current: list[dict[str, Any]] = []
    latest: list[dict[str, Any]] | None = None
    for info in infos:
        exchange = info.get("exchange", {})
        if exchange.get("message") != "FL2C_respond_purchase_list_on_exchange_Message":
            continue
        if exchange.get("ret") != 0:
            raise DecodeError(f"market list returned error {exchange.get('ret')}")
        current.extend(exchange.get("exchange_item_simple_infos", []))
        if exchange.get("is_end"):
            latest, current = current, []
    if latest is None:
        raise DecodeError("no complete market list found; start capture before opening Market")

    rows: dict[tuple[int, int], dict[str, Any]] = {}
    for entry in latest:
        key = (entry["item_index"], entry["enchant_level"])
        row = {
            "Name": entry.get("item_name", ""),
            "ItemIndex": key[0],
            "Enhance": key[1],
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


def write_market_csv(path: Path, infos: list[dict[str, Any]]) -> int:
    rows = latest_market_rows(infos)
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
                      "is_end": False, "exchange_item_simple_infos": [first_purchase]}},
        {"exchange": {"message": "FL2C_respond_purchase_list_on_exchange_Message", "ret": 0,
                      "is_end": True, "exchange_item_simple_infos": [{**first_purchase, "item_index": 11}]}},
    ]
    market_rows = latest_market_rows(market_infos)
    assert [row["ItemIndex"] for row in market_rows] == [10, 11]
    assert market_rows[0]["PricePerUnit"] == 12.5 and market_rows[0]["Qty"] == 14


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="application stream or PCAP")
    parser.add_argument("--out-dir", type=Path, help="write each decoded frame as a .bin file")
    parser.add_argument("--output", type=Path, help="write JSON Lines instead of stdout")
    parser.add_argument("--pcap", action="store_true", help="reassemble TCP streams from a PCAP")
    parser.add_argument("--port", type=int, default=12020, help="TCP port used with --pcap")
    parser.add_argument("--exchange-only", action="store_true")
    parser.add_argument("--items-csv", type=Path, help="CSV with ItemIndex and NamePTBR")
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
                if args.exchange_only and parsed is None:
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
