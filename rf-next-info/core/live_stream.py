"""Decodificação efêmera de pacotes RF NEXT diretamente da memória."""

from __future__ import annotations

import csv
import queue
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.ingest import DEFAULT_PORTS, SENSITIVE_OPCODE, _safe_parse
from core import rfnext_frame_decode as decoder
from core.combat_monitor import NEARBY_PLAYER_STALE_SECONDS


MAX_FRAME_BYTES = 1024 * 1024
MAX_FLOW_BUFFER_BYTES = 4 * 1024 * 1024
LIVE_PLAYER_ANCHOR_SECONDS = NEARBY_PLAYER_STALE_SECONDS
LIVE_COMBAT_EVENT_SECONDS = 20
COMBAT_EVENT_TYPES = frozenset({
    "restore_hp_fp",
    "dying_unit",
    "select_target_request",
    "use_skill_request",
    "use_skill_result",
    "use_normal_skill_result",
    "FG2C_ans_boss_position_Message",
    "FG2C_notify_boss_result_Message",
})
APPEARANCE_EVENT_TYPES = frozenset({"appear_player_list", "appear_monster_list"})
GUILD_RELATION_EVENT_TYPES = frozenset({"enemy_guild_list", "amity_guild_list"})
BOSS_EVENT_OPCODES = frozenset({0x031C, 0x031D, 0x031F, 0x0331, 0x0C05, 0x0C0A})


@lru_cache(maxsize=1)
def _boss_indexes() -> frozenset[int]:
    try:
        with Path(__file__).with_name("boss_catalog.csv").open(
            encoding="utf-8-sig", newline=""
        ) as source:
            return frozenset(
                int(row.get("npc_index") or 0)
                for row in csv.DictReader(source)
                if int(row.get("npc_index") or 0)
            )
    except (OSError, TypeError, ValueError, csv.Error):
        return frozenset()


@dataclass
class _FlowState:
    next_sequence: int | None = None
    stream_offset: int = 0
    buffer: bytearray = field(default_factory=bytearray)
    pending: dict[int, tuple[bytes, int]] = field(default_factory=dict)
    timestamp_ns: int = 0


def _tcp_payload(packet: bytes) -> tuple[str, int, int, bytes] | None:
    ethertype, network = decoder._network_payload(packet, 1)
    if ethertype != 0x0800 or len(network) < 40:
        return None
    ihl = (network[0] & 0x0F) * 4
    total_length = struct.unpack_from("!H", network, 2)[0]
    fragment = struct.unpack_from("!H", network, 6)[0]
    if (
        network[9] != 6
        or ihl < 20
        or total_length < ihl + 20
        or len(network) < total_length
        or fragment & 0x1FFF
    ):
        return None
    tcp = network[ihl:total_length]
    source_port, destination_port, sequence, _, offset_flags = struct.unpack_from(
        "!HHIIH", tcp
    )
    header_length = (offset_flags >> 12) * 4
    if header_length < 20 or len(tcp) < header_length:
        return None
    payload = tcp[header_length:]
    if not payload:
        return None
    server_port = next(
        (
            port
            for port in (source_port, destination_port)
            if port in DEFAULT_PORTS
        ),
        0,
    )
    if not server_port:
        return None
    source = socket.inet_ntoa(network[12:16])
    destination = socket.inet_ntoa(network[16:20])
    flow = f"{source}:{source_port} -> {destination}:{destination_port}"
    return flow, server_port, sequence, payload


class LiveEventDecoder:
    """Reagrupa TCP e entrega somente eventos já decodificados, sem arquivo bruto."""

    def __init__(self) -> None:
        self._flows: dict[str, _FlowState] = {}

    def feed(self, timestamp_ns: int, packet: bytes) -> list[dict[str, Any]]:
        parsed = _tcp_payload(packet)
        if parsed is None:
            return []
        flow, server_port, sequence, payload = parsed
        state = self._flows.setdefault(flow, _FlowState())
        self._append_segment(state, sequence, payload, timestamp_ns)
        return self._decode_available(state, flow, server_port)

    @staticmethod
    def _append_segment(
        state: _FlowState, sequence: int, payload: bytes, timestamp_ns: int
    ) -> None:
        if state.next_sequence is None:
            state.next_sequence = sequence
        expected = int(state.next_sequence)
        end = sequence + len(payload)
        if end <= expected:
            return
        if sequence <= expected:
            tail = payload[expected - sequence :]
            state.buffer.extend(tail)
            state.next_sequence = expected + len(tail)
            state.timestamp_ns = timestamp_ns
        else:
            state.pending.setdefault(sequence, (payload, timestamp_ns))
        while state.pending:
            next_sequence = min(state.pending)
            pending, pending_time = state.pending[next_sequence]
            expected = int(state.next_sequence)
            if next_sequence > expected:
                break
            state.pending.pop(next_sequence)
            end = next_sequence + len(pending)
            if end > expected:
                tail = pending[expected - next_sequence :]
                state.buffer.extend(tail)
                state.next_sequence = expected + len(tail)
                state.timestamp_ns = pending_time
        if len(state.buffer) > MAX_FLOW_BUFFER_BYTES:
            overflow = len(state.buffer) - MAX_FLOW_BUFFER_BYTES
            del state.buffer[:overflow]
            state.stream_offset += overflow

    @staticmethod
    def _decode_available(
        state: _FlowState, flow: str, server_port: int
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        while len(state.buffer) >= 6:
            try:
                length = int(decoder.frame_length_from_wire(state.buffer[:3]))
            except decoder.DecodeError:
                length = 0
            if length < 6 or length > MAX_FRAME_BYTES:
                del state.buffer[0]
                state.stream_offset += 1
                continue
            if len(state.buffer) < length:
                break
            wire = bytes(state.buffer[:length])
            try:
                outer, outer_info = decoder.decode_frame(wire)
            except decoder.DecodeError:
                del state.buffer[0]
                state.stream_offset += 1
                continue
            offset = state.stream_offset
            del state.buffer[:length]
            state.stream_offset += length
            outer_info["stream_offset"] = offset
            outer_info["pcap_time_ns"] = state.timestamp_ns
            for bundle_seq, (decoded, info) in enumerate(
                decoder.expand_bundle(outer, outer_info)
            ):
                opcode = int(info["opcode"])
                if opcode == SENSITIVE_OPCODE:
                    continue
                result = _safe_parse(decoder, decoded, server_port)
                if result is None:
                    continue
                events.append(
                    {
                        "source": "memory://pktmon-live",
                        "flow": flow,
                        "stream_offset": int(info.get("stream_offset", offset)),
                        "bundle_seq": bundle_seq,
                        "ts_ns": int(info.get("pcap_time_ns") or state.timestamp_ns),
                        "opcode": opcode,
                        "type": result.get("type") or result.get("message") or "decoded",
                        "data": result,
                    }
                )
        return events


class LiveEventStream:
    """Fila leve entre o callback nativo do Pktmon e o decoder em memória."""

    def __init__(
        self,
        max_events: int = 20_000,
        *,
        boss_indexes: frozenset[int] | set[int] | None = None,
        max_entity_anchors: int = 4096,
        boss_event_seconds: int = 120,
    ) -> None:
        self._items: queue.SimpleQueue[tuple[int, bytes] | None] = queue.SimpleQueue()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._anchors: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._boss_anchors: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._boss_events: deque[dict[str, Any]] = deque()
        self._identities: dict[str, dict[str, Any]] = {}
        self._guild_relations: dict[tuple[str, str], dict[str, Any]] = {}
        self._boss_indexes = frozenset(
            _boss_indexes() if boss_indexes is None else boss_indexes
        )
        self._max_entity_anchors = max(1, int(max_entity_anchors))
        self._boss_event_ns = max(1, int(boss_event_seconds)) * 1_000_000_000
        self._lock = threading.Lock()
        self._decoder = LiveEventDecoder()
        self._thread: threading.Thread | None = None
        self.decode_errors = 0
        self.processed_packets = 0
        self.decoded_events = 0
        self.ignored_events = 0
        self.dropped_events = 0
        self.last_received_ns = 0
        self.last_processed_ns = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def feed(self, timestamp_ns: int, packet: bytes) -> None:
        self.last_received_ns = max(self.last_received_ns, int(timestamp_ns))
        self._items.put((timestamp_ns, packet))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_stale_live_state()
            return [
                *self._identities.values(),
                *self._guild_relations.values(),
                *self._anchors.values(),
                *self._boss_anchors.values(),
                *self._events,
                *self._boss_events,
            ]

    def _prune_stale_live_state(self) -> None:
        """Descarta estado efêmero vencido sem perder a identidade local."""
        if self.last_received_ns < 1_500_000_000_000_000_000:
            return
        reference_ns = max(int(self.last_received_ns), time.time_ns())
        player_cutoff = reference_ns - LIVE_PLAYER_ANCHOR_SECONDS * 1_000_000_000
        combat_cutoff = reference_ns - LIVE_COMBAT_EVENT_SECONDS * 1_000_000_000
        local_character_uids = {
            str(fields["character_uid"])
            for event in self._identities.values()
            if (
                isinstance((fields := (event.get("data") or {}).get("fields")), dict)
                and fields.get("character_uid") is not None
            )
        }
        max_events = self._events.maxlen
        self._events = deque(
            (
                event
                for event in self._events
                if int(event.get("ts_ns") or 0) >= combat_cutoff
            ),
            maxlen=max_events,
        )
        active_player_uids: set[int] = set()
        for event in (*self._events, *self._boss_events):
            if int(event.get("ts_ns") or 0) < player_cutoff:
                continue
            data = event.get("data") or {}
            for name in ("uid", "caster_uid", "main_target_uid", "target_uid"):
                value = data.get(name)
                if isinstance(value, (int, float)):
                    active_player_uids.add(int(value))
            active_player_uids.update(
                int(value)
                for result in data.get("effect_results") or []
                if isinstance((value := result.get("uid")), (int, float))
            )
        for key, event in tuple(self._anchors.items()):
            if key[1] != "player" or int(event.get("ts_ns") or 0) >= player_cutoff:
                continue
            units = (event.get("data") or {}).get("units") or []
            character_uid = str((units[0] if units else {}).get("character_uid") or "")
            if (
                character_uid not in local_character_uids
                and key[2] not in active_player_uids
            ):
                self._anchors.pop(key, None)
    def metrics(self) -> dict[str, int | float | bool]:
        try:
            queued = self._items.qsize()
        except NotImplementedError:
            queued = -1
        lag = max(0, self.last_received_ns - self.last_processed_ns)
        with self._lock:
            retained = len(self._events)
            anchors = len(self._anchors)
            boss_events = len(self._boss_events)
            boss_anchors = len(self._boss_anchors)
        return {
            "worker_alive": bool(self._thread and self._thread.is_alive()),
            "queue_depth": queued,
            "lag_seconds": round(lag / 1_000_000_000, 3),
            "processed_packets": self.processed_packets,
            "decoded_events": self.decoded_events,
            "ignored_events": self.ignored_events,
            "dropped_events": self.dropped_events,
            "retained_events": retained,
            "entity_anchors": anchors,
            "boss_events": boss_events,
            "boss_anchors": boss_anchors,
            "decode_errors": self.decode_errors,
        }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._anchors.clear()
            self._boss_anchors.clear()
            self._boss_events.clear()
            self._identities.clear()
            self._guild_relations.clear()
        self._decoder = LiveEventDecoder()
        self.decode_errors = 0
        self.processed_packets = 0
        self.decoded_events = 0
        self.ignored_events = 0
        self.dropped_events = 0
        self.last_received_ns = 0
        self.last_processed_ns = 0

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread and thread.is_alive():
            self._items.put(None)
            thread.join(timeout=3)

    def _worker(self) -> None:
        while True:
            item = self._items.get()
            if item is None:
                return
            try:
                events = self._decoder.feed(*item)
            except Exception:
                self.decode_errors += 1
                continue
            finally:
                self.processed_packets += 1
                self.last_processed_ns = max(self.last_processed_ns, int(item[0]))
            if events:
                try:
                    self._remember(events)
                except Exception:
                    self.decode_errors += 1

    def _remember(self, events: list[dict[str, Any]]) -> None:
        with self._lock:
            for event in events:
                kind = str(event.get("type") or "")
                flow = str(event.get("flow") or "")
                self.decoded_events += 1
                if kind == "world_info_prefix":
                    self._identities[flow] = event
                    continue
                if kind in GUILD_RELATION_EVENT_TYPES:
                    self._guild_relations[(flow, kind)] = event
                    continue
                if kind in APPEARANCE_EVENT_TYPES:
                    entity_type = "player" if kind == "appear_player_list" else "monster"
                    opposite = "monster" if entity_type == "player" else "player"
                    for unit in (event.get("data") or {}).get("units") or []:
                        uid = unit.get("uid")
                        if not isinstance(uid, (int, float)):
                            continue
                        uid = int(uid)
                        self._anchors.pop((flow, opposite, uid), None)
                        self._boss_anchors.pop((flow, opposite, uid), None)
                        anchor = {
                            **event,
                            "data": {**(event.get("data") or {}), "units": [unit]},
                        }
                        npc_index = unit.get("npc_index")
                        target = (
                            self._boss_anchors
                            if entity_type == "monster"
                            and isinstance(npc_index, (int, float))
                            and int(npc_index) in self._boss_indexes
                            else self._anchors
                        )
                        key = (flow, entity_type, uid)
                        target.pop(key, None)
                        target[key] = anchor
                        if target is self._anchors and len(target) > self._max_entity_anchors:
                            target.pop(next(iter(target)))
                    continue
                if kind == "dying_unit":
                    uid = (event.get("data") or {}).get("uid")
                    if isinstance(uid, (int, float)):
                        self._anchors.pop((flow, "monster", int(uid)), None)
                        self._boss_anchors.pop((flow, "monster", int(uid)), None)
                if self._is_boss_event(event):
                    self._boss_events.append(event)
                    timestamp = int(event.get("ts_ns") or 0)
                    cutoff = timestamp - self._boss_event_ns
                    while (
                        cutoff > 0
                        and self._boss_events
                        and int(self._boss_events[0].get("ts_ns") or 0) < cutoff
                    ):
                        self._boss_events.popleft()
                    continue
                if kind not in COMBAT_EVENT_TYPES:
                    self.ignored_events += 1
                    continue
                if self._events.maxlen and len(self._events) == self._events.maxlen:
                    self.dropped_events += 1
                self._events.append(event)

    def _is_boss_event(self, event: dict[str, Any]) -> bool:
        if event.get("opcode") in BOSS_EVENT_OPCODES or event.get("type") in {
            "FG2C_ans_boss_position_Message",
            "FG2C_notify_boss_result_Message",
        }:
            return True
        boss_uids = {key[2] for key in self._boss_anchors}
        if not boss_uids:
            return False
        data = event.get("data") or {}
        related = {
            int(value)
            for name in (
                "uid",
                "caster_uid",
                "main_target_uid",
                "target_uid",
                "killer_uid",
            )
            if isinstance((value := data.get(name)), (int, float))
        }
        related.update(
            int(value)
            for result in data.get("effect_results") or []
            if isinstance((value := result.get("uid")), (int, float))
        )
        return bool(related.intersection(boss_uids))
