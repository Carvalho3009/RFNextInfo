"""Decodificação efêmera de pacotes RF NEXT diretamente da memória."""

from __future__ import annotations

import csv
import queue
import socket
import struct
import threading
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from core.ingest import DEFAULT_PORTS, SENSITIVE_OPCODE, _safe_parse
from core import rfnext_frame_decode as decoder
from core.combat_monitor import NEARBY_PLAYER_STALE_SECONDS


MAX_FRAME_BYTES = 1024 * 1024
MAX_FLOW_BUFFER_BYTES = 4 * 1024 * 1024
MAX_LIVE_FLOWS = 64
MAX_PENDING_PACKETS = 8192
MAX_PENDING_PACKET_BYTES = 32 * 1024 * 1024
MAX_PENDING_SEGMENTS_PER_FLOW = 256
MAX_PENDING_BYTES_PER_FLOW = 2 * 1024 * 1024
TCP_GAP_RECOVERY_SECONDS = 5
MAX_BOSS_EVENTS = 4096
MAX_BOSS_DAMAGE_BUCKETS = 2048
BOSS_ENCOUNTER_RETENTION_SECONDS = 6 * 60 * 60
LIVE_PLAYER_ANCHOR_SECONDS = NEARBY_PLAYER_STALE_SECONDS
LIVE_COMBAT_EVENT_SECONDS = 30
COMBAT_EVENT_TYPES = frozenset({
    "drop_item_field",
    "loot_announcement",
    "restore_hp_fp",
    "dying_unit",
    "select_target_request",
    "use_skill_request",
    "use_skill_result",
    "use_normal_skill_result",
    "FG2C_ans_boss_position_Message",
    "FG2C_notify_boss_result_Message",
    "FG2C_notify_boss_status_list_Message",
    "FG2C_worldboss_hp_sync_Message",
    "FG2C_worldboss_personal_contribution_update_Message",
    "FG2C_noti_worldboss_result_Message",
})
APPEARANCE_EVENT_TYPES = frozenset({"appear_player_list", "appear_monster_list"})
GUILD_RELATION_EVENT_TYPES = frozenset({"enemy_guild_list", "amity_guild_list"})
MAP_EVENT_TYPES = frozenset({
    "move_player_request",
    "move_player_update",
    "request_teleport",
    "request_teleport_result",
    "teleport_request",
    "teleport_response",
    "warp_player",
    "end_warp_player",
})
BOSS_EVENT_OPCODES = frozenset({
    0x031C, 0x031D, 0x031F, 0x0331, 0x0C05, 0x0C07, 0x0C08, 0x0C0A,
})


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


@lru_cache(maxsize=1)
def _collection_slots() -> dict[tuple[int, int], dict[str, Any]]:
    catalog = Path(__file__).with_name("collection_requirements.csv")
    try:
        return decoder.load_collection_slots(catalog if catalog.is_file() else None)
    except (OSError, TypeError, ValueError, csv.Error):
        return {}


@dataclass
class _FlowState:
    event_flow: str = ""
    next_sequence: int | None = None
    stream_offset: int = 0
    buffer: bytearray = field(default_factory=bytearray)
    pending: dict[int, tuple[bytes, int]] = field(default_factory=dict)
    pending_bytes: int = 0
    timestamp_ns: int = 0
    gap_started_ns: int | None = None
    equipment_appearances: deque[dict[str, Any]] = field(
        default_factory=lambda: deque(maxlen=64)
    )


def _tcp_payload(
    packet: bytes,
    transport_ports: tuple[int, ...] = DEFAULT_PORTS,
) -> tuple[str, int, int, bytes] | None:
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
    accepted_ports = tuple(int(port) for port in transport_ports)
    server_port = next(
        (port for port in (source_port, destination_port) if port in DEFAULT_PORTS),
        0,
    )
    transport_port = server_port or next(
        (
            port
            for port in (source_port, destination_port)
            if port in accepted_ports
        ),
        0,
    )
    if not transport_port:
        return None
    # ExitLag substitui a porta oficial por uma conexao loopback efemera. O
    # zero faz o parser tentar os contratos conhecidos sem tratar a porta
    # local como se fosse uma porta oficial do servidor.
    source = socket.inet_ntoa(network[12:16])
    destination = socket.inet_ntoa(network[16:20])
    flow = f"{source}:{source_port} -> {destination}:{destination_port}"
    return flow, server_port, sequence, payload


class LiveEventDecoder:
    """Reagrupa TCP e entrega somente eventos já decodificados, sem arquivo bruto."""

    def __init__(
        self,
        max_flows: int = MAX_LIVE_FLOWS,
        *,
        transport_ports: tuple[int, ...] = DEFAULT_PORTS,
        max_pending_segments: int = MAX_PENDING_SEGMENTS_PER_FLOW,
        max_pending_bytes: int = MAX_PENDING_BYTES_PER_FLOW,
        max_flow_buffer_bytes: int = MAX_FLOW_BUFFER_BYTES,
        gap_recovery_seconds: float = TCP_GAP_RECOVERY_SECONDS,
    ) -> None:
        self._flows: dict[str, _FlowState] = {}
        self._max_flows = max(1, int(max_flows))
        self._max_pending_segments = max(1, int(max_pending_segments))
        self._max_pending_bytes = max(1, int(max_pending_bytes))
        self._max_flow_buffer_bytes = max(MAX_FRAME_BYTES, int(max_flow_buffer_bytes))
        self._gap_recovery_ns = max(
            100_000_000, int(float(gap_recovery_seconds) * 1_000_000_000)
        )
        self._transport_ports = tuple(
            dict.fromkeys(int(port) for port in transport_ports if int(port) > 0)
        )
        self._collection_slots = _collection_slots()
        self._connection_aliases: dict[int, str] = {}
        self._connection_alias_resolver: Callable[[], dict[int, str]] | None = None
        self.alias_resolution_attempts = 0
        self.alias_resolution_hits = 0
        self.alias_resolution_errors = 0
        self.gap_recoveries = 0
        self.recovered_gap_bytes = 0
        self.discarded_partial_bytes = 0
        self.last_gap_recovery_ns = 0

    def set_transport_ports(self, ports: tuple[int, ...]) -> None:
        self._transport_ports = tuple(
            dict.fromkeys(int(port) for port in ports if int(port) > 0)
        )

    def set_connection_aliases(self, aliases: dict[int, str]) -> None:
        self._connection_aliases = {
            int(port): str(alias)[:96]
            for port, alias in dict(aliases).items()
            if 0 < int(port) <= 65535 and str(alias)
        }

    def set_connection_alias_resolver(
        self, resolver: Callable[[], dict[int, str]] | None,
    ) -> None:
        self._connection_alias_resolver = resolver

    def _connection_alias(self, flow: str) -> str:
        ports: list[int] = []
        for endpoint in str(flow).split(" -> ", 1):
            try:
                port = int(endpoint.rsplit(":", 1)[1])
            except (IndexError, TypeError, ValueError):
                continue
            ports.append(port)
            alias = self._connection_aliases.get(port)
            if alias:
                return f"client-route:{alias}"
        # Uma rota TCP nova pode surgir entre duas leituras periódicas do
        # Windows. Resolva-a no primeiro pacote, antes de fixar event_flow;
        # assim as conexões 12010/12020 do mesmo cliente não viram personagens
        # distintos durante teleporte ou reconexão.
        resolver = self._connection_alias_resolver
        if ports and resolver is not None:
            self.alias_resolution_attempts += 1
            try:
                aliases = resolver()
                resolved = {
                    int(port): str(alias)[:96]
                    for port, alias in dict(aliases).items()
                    if 0 < int(port) <= 65535 and str(alias)
                }
            except Exception:
                self.alias_resolution_errors += 1
            else:
                self._connection_aliases.update(resolved)
                for port in ports:
                    alias = self._connection_aliases.get(port)
                    if alias:
                        self.alias_resolution_hits += 1
                        return f"client-route:{alias}"
        return flow

    @property
    def flow_count(self) -> int:
        return len(self._flows)

    @property
    def pending_segment_count(self) -> int:
        return sum(len(state.pending) for state in self._flows.values())

    @property
    def pending_bytes(self) -> int:
        return sum(state.pending_bytes for state in self._flows.values())

    @property
    def stalled_flow_count(self) -> int:
        return sum(
            1 for state in self._flows.values()
            if state.gap_started_ns is not None and state.pending
        )

    def compact(self, fraction: float = 0.5) -> dict[str, int]:
        """Reduz contextos antigos sem interromper o fluxo TCP mais recente."""
        fraction = max(0.1, min(1.0, float(fraction)))
        flow_limit = max(1, round(self._max_flows * fraction))
        while len(self._flows) > flow_limit:
            self._flows.pop(next(iter(self._flows)))
        pending_limit = max(1, round(self._max_pending_segments * fraction))
        byte_limit = max(MAX_FRAME_BYTES, round(self._max_pending_bytes * fraction))
        for state in self._flows.values():
            while len(state.pending) > pending_limit or state.pending_bytes > byte_limit:
                if not state.pending:
                    break
                farthest = max(state.pending)
                removed, _timestamp = state.pending.pop(farthest)
                state.pending_bytes = max(0, state.pending_bytes - len(removed))
            if len(state.buffer) > byte_limit:
                overflow = len(state.buffer) - byte_limit
                del state.buffer[:overflow]
                state.stream_offset += overflow
        return {
            "flows": len(self._flows),
            "pending_segments": self.pending_segment_count,
            "pending_bytes": self.pending_bytes,
        }

    def feed(self, timestamp_ns: int, packet: bytes) -> list[dict[str, Any]]:
        parsed = _tcp_payload(packet, self._transport_ports)
        if parsed is None:
            return []
        flow, server_port, sequence, payload = parsed
        # Cada socket TCP conserva seu próprio espaço de sequência. O alias do
        # processo serve apenas como identidade lógica nos eventos decodificados;
        # usá-lo como chave do reagrupador misturaria as conexões 12010/12020.
        state = self._flows.pop(flow, None)
        if state is None:
            while len(self._flows) >= self._max_flows:
                self._flows.pop(next(iter(self._flows)))
            # A relação porta -> processo pode aparecer depois dos primeiros
            # pacotes. Fixar a identidade lógica na criação evita que o mesmo
            # socket troque de client_ref no meio da sessão e perca métricas de
            # subsessão já vinculadas ao personagem.
            state = _FlowState(event_flow=self._connection_alias(flow))
        self._flows[flow] = state
        self._append_segment(state, sequence, payload, timestamp_ns)
        return self._decode_available(state, state.event_flow or flow, server_port)

    def _recover_gap(self, state: _FlowState, timestamp_ns: int) -> None:
        """Descarta apenas o prefixo incompleto do fluxo TCP bloqueado."""
        if not state.pending or state.next_sequence is None:
            state.gap_started_ns = None
            return
        next_sequence = min(state.pending)
        expected = int(state.next_sequence)
        if next_sequence <= expected:
            state.gap_started_ns = None
            return
        partial_bytes = len(state.buffer)
        missing_bytes = next_sequence - expected
        state.buffer.clear()
        state.stream_offset += partial_bytes + missing_bytes
        state.next_sequence = next_sequence
        state.gap_started_ns = None
        self.gap_recoveries += 1
        self.recovered_gap_bytes += missing_bytes
        self.discarded_partial_bytes += partial_bytes
        self.last_gap_recovery_ns = max(
            self.last_gap_recovery_ns, int(timestamp_ns)
        )

    def _append_segment(
        self, state: _FlowState, sequence: int, payload: bytes, timestamp_ns: int
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
            if sequence - expected > self._max_flow_buffer_bytes:
                state.buffer.clear()
                state.pending.clear()
                state.pending_bytes = 0
                state.next_sequence = sequence
                state.buffer.extend(payload)
                state.next_sequence = sequence + len(payload)
                state.timestamp_ns = timestamp_ns
                state.gap_started_ns = None
            elif sequence not in state.pending:
                state.pending[sequence] = (payload, timestamp_ns)
                state.pending_bytes += len(payload)
                if state.gap_started_ns is None:
                    state.gap_started_ns = int(timestamp_ns)
                while (
                    len(state.pending) > self._max_pending_segments
                    or state.pending_bytes > self._max_pending_bytes
                ):
                    farthest = max(state.pending)
                    removed, _removed_time = state.pending.pop(farthest)
                    state.pending_bytes = max(
                        0, state.pending_bytes - len(removed)
                    )
                if (
                    state.pending
                    and state.gap_started_ns is not None
                    and int(timestamp_ns) - state.gap_started_ns
                    >= self._gap_recovery_ns
                ):
                    self._recover_gap(state, timestamp_ns)
        while state.pending:
            next_sequence = min(state.pending)
            pending, pending_time = state.pending[next_sequence]
            expected = int(state.next_sequence)
            if next_sequence > expected:
                break
            state.pending.pop(next_sequence)
            state.pending_bytes = max(0, state.pending_bytes - len(pending))
            end = next_sequence + len(pending)
            if end > expected:
                tail = pending[expected - next_sequence :]
                state.buffer.extend(tail)
                state.next_sequence = expected + len(tail)
                state.timestamp_ns = pending_time
        if state.pending:
            state.gap_started_ns = min(
                pending_time for _pending, pending_time in state.pending.values()
            )
        else:
            state.gap_started_ns = None
        if len(state.buffer) > self._max_flow_buffer_bytes:
            overflow = len(state.buffer) - self._max_flow_buffer_bytes
            del state.buffer[:overflow]
            state.stream_offset += overflow

    def _decode_available(
        self,
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
                candidate_ports = (
                    (server_port,)
                    if server_port
                    else (12020, 12010, 12000, 12040)
                )
                result = next(
                    (
                        parsed
                        for candidate_port in candidate_ports
                        if (parsed := _safe_parse(
                            decoder, decoded, candidate_port,
                            self._collection_slots,
                        )) is not None
                    ),
                    None,
                )
                if result is None:
                    continue
                if (
                    result.get("type") == "appear_player_prefix"
                    and result.get("fields", {}).get("equipment_refs")
                ):
                    state.equipment_appearances.append(result)
                elif result.get("type") == "player_profile_info":
                    correlated = decoder.correlate_active_equipment(
                        result, list(state.equipment_appearances)
                    )
                    if correlated is not None:
                        active_equipment, _appearance = correlated
                        result["fields"]["active_equipment"] = active_equipment
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
        boss_event_seconds: int = BOSS_ENCOUNTER_RETENTION_SECONDS,
        max_pending_packets: int = MAX_PENDING_PACKETS,
        max_pending_packet_bytes: int = MAX_PENDING_PACKET_BYTES,
        max_boss_events: int = MAX_BOSS_EVENTS,
        max_flows: int = MAX_LIVE_FLOWS,
        max_pending_segments_per_flow: int = MAX_PENDING_SEGMENTS_PER_FLOW,
        max_pending_bytes_per_flow: int = MAX_PENDING_BYTES_PER_FLOW,
        max_flow_buffer_bytes: int = MAX_FLOW_BUFFER_BYTES,
        tcp_gap_recovery_seconds: float = TCP_GAP_RECOVERY_SECONDS,
        event_sink: Callable[[dict[str, Any]], bool] | None = None,
        transport_ports: tuple[int, ...] = DEFAULT_PORTS,
    ) -> None:
        self._max_pending_packets = max(1, int(max_pending_packets))
        self._max_pending_packet_bytes = max(1, int(max_pending_packet_bytes))
        self._items: queue.Queue[tuple[int, bytes] | None] = queue.Queue(
            maxsize=self._max_pending_packets
        )
        self._queued_packet_bytes = 0
        self._queue_lock = threading.Lock()
        self._events: deque[dict[str, Any]] = deque(
            maxlen=max(1, int(max_events))
        )
        self._anchors: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._boss_anchors: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._boss_events: deque[dict[str, Any]] = deque(
            maxlen=max(1, int(max_boss_events))
        )
        self._boss_damage_totals: dict[
            tuple[str, int, int], dict[str, Any]
        ] = {}
        self._identities: dict[str, dict[str, Any]] = {}
        self._guild_relations: dict[tuple[str, str], dict[str, Any]] = {}
        self._map_events: dict[tuple[str, str, int], dict[str, Any]] = {}
        self._boss_indexes = frozenset(
            _boss_indexes() if boss_indexes is None else boss_indexes
        )
        self._max_entity_anchors = max(1, int(max_entity_anchors))
        self._max_flow_contexts = max(1, int(max_flows))
        self._decoder_kwargs = {
            "max_flows": self._max_flow_contexts,
            "max_pending_segments": max(1, int(max_pending_segments_per_flow)),
            "max_pending_bytes": max(1, int(max_pending_bytes_per_flow)),
            "max_flow_buffer_bytes": max(
                MAX_FRAME_BYTES, int(max_flow_buffer_bytes)
            ),
            "gap_recovery_seconds": max(
                0.1, float(tcp_gap_recovery_seconds)
            ),
            "transport_ports": tuple(transport_ports),
        }
        self._boss_event_ns = max(1, int(boss_event_seconds)) * 1_000_000_000
        self._lock = threading.Lock()
        self._metrics_lock = threading.Lock()
        self._decoder = LiveEventDecoder(**self._decoder_kwargs)
        self._connection_alias_resolver: Callable[
            [], dict[int, str]
        ] | None = None
        self._event_sink = event_sink
        self._thread: threading.Thread | None = None
        self._worker_stop = threading.Event()
        self.decode_errors = 0
        self.processed_packets = 0
        self.decoded_events = 0
        self.ignored_events = 0
        self.dropped_events = 0
        self.dropped_packets = 0
        self.event_sink_accepted = 0
        self.event_sink_rejected = 0
        self.event_sink_errors = 0
        self.decoded_by_type: Counter[str] = Counter()
        self.event_sink_accepted_by_type: Counter[str] = Counter()
        self.event_sink_rejected_by_type: Counter[str] = Counter()
        self.event_sink_errors_by_type: Counter[str] = Counter()
        self.memory_compactions = 0
        self.last_received_ns = 0
        self.last_processed_ns = 0
        self.last_decoded_ns = 0

    def set_transport_ports(self, ports: tuple[int, ...]) -> None:
        normalized = tuple(
            dict.fromkeys(int(port) for port in ports if int(port) > 0)
        )
        self._decoder_kwargs["transport_ports"] = normalized
        self._decoder.set_transport_ports(normalized)

    def set_connection_aliases(self, aliases: dict[int, str]) -> None:
        self._decoder.set_connection_aliases(aliases)

    def set_connection_alias_resolver(
        self, resolver: Callable[[], dict[int, str]] | None,
    ) -> None:
        self._connection_alias_resolver = resolver
        self._decoder.set_connection_alias_resolver(resolver)

    def set_event_sink(
        self, sink: Callable[[dict[str, Any]], bool] | None
    ) -> None:
        self._event_sink = sink

    def start(self) -> None:
        if self._thread:
            if self._thread.is_alive():
                if self._worker_stop.is_set():
                    raise RuntimeError("O stream anterior ainda está encerrando")
                return
            self._thread = None
            self._items = queue.Queue(maxsize=self._max_pending_packets)
            with self._queue_lock:
                self._queued_packet_bytes = 0
        self._worker_stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def feed(self, timestamp_ns: int, packet: bytes) -> None:
        self.last_received_ns = max(self.last_received_ns, int(timestamp_ns))
        packet_bytes = len(packet)
        with self._queue_lock:
            if self._queued_packet_bytes + packet_bytes > self._max_pending_packet_bytes:
                self.dropped_packets += 1
                return
            self._queued_packet_bytes += packet_bytes
        try:
            self._items.put_nowait((timestamp_ns, packet))
        except queue.Full:
            with self._queue_lock:
                self._queued_packet_bytes = max(
                    0, self._queued_packet_bytes - packet_bytes
                )
            self.dropped_packets += 1

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            self._prune_stale_live_state()
            return [
                *self._identities.values(),
                *self._guild_relations.values(),
                *self._anchors.values(),
                *self._boss_anchors.values(),
                *self._map_events.values(),
                *self._events,
                *self._boss_events,
                *self._boss_damage_events(),
            ]

    def _boss_damage_events(self) -> list[dict[str, Any]]:
        return [
            {
                "flow": flow,
                "ts_ns": int(bucket["last_seen_ns"]),
                "type": "boss_damage_total",
                "data": {
                    "target_uid": target_uid,
                    "caster_uid": caster_uid,
                    "damage": int(bucket["damage"]),
                    "first_seen_ns": int(bucket["first_seen_ns"]),
                    "last_seen_ns": int(bucket["last_seen_ns"]),
                    "player": dict(bucket.get("player") or {}),
                },
            }
            for (flow, target_uid, caster_uid), bucket
            in self._boss_damage_totals.items()
        ]

    def _prune_stale_live_state(self) -> None:
        """Descarta estado efêmero vencido sem perder a identidade local."""
        if self.last_received_ns < 1_500_000_000_000_000_000:
            return
        reference_ns = max(int(self.last_received_ns), time.time_ns())
        player_cutoff = reference_ns - LIVE_PLAYER_ANCHOR_SECONDS * 1_000_000_000
        combat_cutoff = reference_ns - LIVE_COMBAT_EVENT_SECONDS * 1_000_000_000
        boss_cutoff = reference_ns - self._boss_event_ns
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
        self._boss_events = deque(
            (
                event
                for event in self._boss_events
                if int(event.get("ts_ns") or 0) >= boss_cutoff
            ),
            maxlen=self._boss_events.maxlen,
        )
        active_boss_uids = {
            uid for event in self._boss_events for uid in self._related_uids(event)
        }
        for key, event in tuple(self._boss_anchors.items()):
            if (
                int(event.get("ts_ns") or 0) < boss_cutoff
                and key[2] not in active_boss_uids
            ):
                self._boss_anchors.pop(key, None)
        for key, bucket in tuple(self._boss_damage_totals.items()):
            if int(bucket.get("last_seen_ns") or 0) < boss_cutoff:
                self._boss_damage_totals.pop(key, None)
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
    @staticmethod
    def _bounded_counts(values: Counter[str]) -> dict[str, int]:
        return {
            name: int(count)
            for name, count in values.most_common(64)
            if name
        }

    def metrics(self) -> dict[str, object]:
        try:
            queued = self._items.qsize()
        except NotImplementedError:
            queued = -1
        with self._queue_lock:
            queued_bytes = self._queued_packet_bytes
        lag = max(0, self.last_received_ns - self.last_processed_ns)
        with self._lock:
            retained = len(self._events)
            anchors = len(self._anchors)
            boss_events = len(self._boss_events)
            boss_anchors = len(self._boss_anchors)
            boss_damage_buckets = len(self._boss_damage_totals)
            map_events = len(self._map_events)
            identity_contexts = len(self._identities)
            guild_contexts = len(self._guild_relations)
        with self._metrics_lock:
            decoded_by_type = self._bounded_counts(self.decoded_by_type)
            sink_accepted_by_type = self._bounded_counts(
                self.event_sink_accepted_by_type
            )
            sink_rejected_by_type = self._bounded_counts(
                self.event_sink_rejected_by_type
            )
            sink_errors_by_type = self._bounded_counts(
                self.event_sink_errors_by_type
            )
        return {
            "worker_alive": bool(self._thread and self._thread.is_alive()),
            "queue_depth": queued,
            "queue_limit": self._max_pending_packets,
            "queue_bytes": queued_bytes,
            "queue_byte_limit": self._max_pending_packet_bytes,
            "lag_seconds": round(lag / 1_000_000_000, 3),
            "processed_packets": self.processed_packets,
            "decoded_events": self.decoded_events,
            "ignored_events": self.ignored_events,
            "dropped_events": self.dropped_events,
            "dropped_packets": self.dropped_packets,
            "event_sink_accepted": self.event_sink_accepted,
            "event_sink_rejected": self.event_sink_rejected,
            "event_sink_errors": self.event_sink_errors,
            "decoded_by_type": decoded_by_type,
            "event_sink_accepted_by_type": sink_accepted_by_type,
            "event_sink_rejected_by_type": sink_rejected_by_type,
            "event_sink_errors_by_type": sink_errors_by_type,
            "retained_events": retained,
            "event_limit": int(self._events.maxlen or 0),
            "entity_anchors": anchors,
            "entity_anchor_limit": self._max_entity_anchors,
            "boss_events": boss_events,
            "boss_event_limit": int(self._boss_events.maxlen or 0),
            "boss_anchors": boss_anchors,
            "boss_damage_buckets": boss_damage_buckets,
            "map_events": map_events,
            "identity_contexts": identity_contexts,
            "guild_contexts": guild_contexts,
            "decode_errors": self.decode_errors,
            "memory_compactions": self.memory_compactions,
            "flow_count": int(getattr(self._decoder, "flow_count", 0)),
            "flow_limit": self._max_flow_contexts,
            "pending_tcp_segments": int(
                getattr(self._decoder, "pending_segment_count", 0)
            ),
            "pending_tcp_segments_per_flow_limit": int(
                self._decoder_kwargs["max_pending_segments"]
            ),
            "pending_tcp_bytes": int(getattr(self._decoder, "pending_bytes", 0)),
            "pending_tcp_bytes_per_flow_limit": int(
                self._decoder_kwargs["max_pending_bytes"]
            ),
            "flow_buffer_byte_limit": int(
                self._decoder_kwargs["max_flow_buffer_bytes"]
            ),
            "stalled_tcp_flows": int(
                getattr(self._decoder, "stalled_flow_count", 0)
            ),
            "tcp_gap_recoveries": int(
                getattr(self._decoder, "gap_recoveries", 0)
            ),
            "tcp_recovered_gap_bytes": int(
                getattr(self._decoder, "recovered_gap_bytes", 0)
            ),
            "tcp_discarded_partial_bytes": int(
                getattr(self._decoder, "discarded_partial_bytes", 0)
            ),
            "last_gap_recovery_ns": int(
                getattr(self._decoder, "last_gap_recovery_ns", 0)
            ),
            "alias_resolution_attempts": int(
                getattr(self._decoder, "alias_resolution_attempts", 0)
            ),
            "alias_resolution_hits": int(
                getattr(self._decoder, "alias_resolution_hits", 0)
            ),
            "alias_resolution_errors": int(
                getattr(self._decoder, "alias_resolution_errors", 0)
            ),
            "last_decoded_ns": int(self.last_decoded_ns),
        }

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._anchors.clear()
            self._boss_anchors.clear()
            self._boss_events.clear()
            self._boss_damage_totals.clear()
            self._identities.clear()
            self._guild_relations.clear()
            self._map_events.clear()
        self._decoder = LiveEventDecoder(**self._decoder_kwargs)
        self._decoder.set_connection_alias_resolver(
            self._connection_alias_resolver
        )
        self.decode_errors = 0
        self.processed_packets = 0
        self.decoded_events = 0
        self.ignored_events = 0
        self.dropped_events = 0
        self.dropped_packets = 0
        self.event_sink_accepted = 0
        self.event_sink_rejected = 0
        self.event_sink_errors = 0
        with self._metrics_lock:
            self.decoded_by_type.clear()
            self.event_sink_accepted_by_type.clear()
            self.event_sink_rejected_by_type.clear()
            self.event_sink_errors_by_type.clear()
        self.memory_compactions = 0
        self.last_received_ns = 0
        self.last_processed_ns = 0
        self.last_decoded_ns = 0

    def compact(self, fraction: float = 0.5) -> dict[str, int]:
        """Descarta somente estado efêmero antigo sob pressão de memória."""
        fraction = max(0.1, min(1.0, float(fraction)))
        with self._lock:
            self._prune_stale_live_state()

            def shrink(values: deque[dict[str, Any]], minimum: int) -> deque[dict[str, Any]]:
                current_limit = int(values.maxlen or minimum)
                limit = max(
                    min(minimum, current_limit),
                    round(current_limit * fraction),
                )
                return deque(list(values)[-limit:], maxlen=limit)

            self._events = shrink(self._events, 1000)
            self._boss_events = shrink(self._boss_events, 256)
            anchor_limit = max(256, round(self._max_entity_anchors * fraction))
            for mapping in (self._anchors, self._boss_anchors):
                while len(mapping) > anchor_limit:
                    mapping.pop(next(iter(mapping)))
            map_limit = max(256, anchor_limit * 2)
            while len(self._map_events) > map_limit:
                self._map_events.pop(next(iter(self._map_events)))
            while len(self._boss_damage_totals) > MAX_BOSS_DAMAGE_BUCKETS:
                self._boss_damage_totals.pop(next(iter(self._boss_damage_totals)))
            decoder = self._decoder.compact(fraction)
            self.memory_compactions += 1
            return {
                "events": len(self._events),
                "boss_events": len(self._boss_events),
                "anchors": len(self._anchors) + len(self._boss_anchors),
                **decoder,
            }

    def stop(self) -> None:
        thread = self._thread
        if thread and thread.is_alive():
            self._worker_stop.set()
            try:
                self._items.put_nowait(None)
            except queue.Full:
                pass
            thread.join(timeout=3)
        if not thread or not thread.is_alive():
            self._thread = None
            self._items = queue.Queue(maxsize=self._max_pending_packets)
            with self._queue_lock:
                self._queued_packet_bytes = 0

    def _worker(self) -> None:
        while True:
            item = self._items.get()
            if item is not None:
                with self._queue_lock:
                    self._queued_packet_bytes = max(
                        0, self._queued_packet_bytes - len(item[1])
                    )
            if item is None or self._worker_stop.is_set():
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
                self._dispatch_events(events)

    def _dispatch_events(self, events: list[dict[str, Any]]) -> None:
        """Entrega opcional fora do estado local; falhas nunca param a captura."""
        sink = self._event_sink
        if sink is None:
            return
        accepted_by_type: Counter[str] = Counter()
        rejected_by_type: Counter[str] = Counter()
        errors_by_type: Counter[str] = Counter()
        for event in events:
            kind = str(event.get("type") or "unknown")[:96]
            try:
                accepted = sink(event)
            except Exception:
                self.event_sink_errors += 1
                errors_by_type[kind] += 1
                continue
            if accepted:
                self.event_sink_accepted += 1
                accepted_by_type[kind] += 1
            else:
                self.event_sink_rejected += 1
                rejected_by_type[kind] += 1
        with self._metrics_lock:
            self.event_sink_accepted_by_type.update(accepted_by_type)
            self.event_sink_rejected_by_type.update(rejected_by_type)
            self.event_sink_errors_by_type.update(errors_by_type)

    def _remember(self, events: list[dict[str, Any]]) -> None:
        self.last_decoded_ns = max(
            self.last_decoded_ns,
            max(int(event.get("ts_ns") or 0) for event in events),
        )
        decoded_by_type = Counter(
            str(event.get("type") or "unknown")[:96] for event in events
        )
        with self._metrics_lock:
            self.decoded_by_type.update(decoded_by_type)
        with self._lock:
            for event in events:
                kind = str(event.get("type") or "")
                flow = str(event.get("flow") or "")
                self.decoded_events += 1
                if kind == "world_info_prefix":
                    self._identities.pop(flow, None)
                    self._identities[flow] = event
                    while len(self._identities) > self._max_flow_contexts:
                        self._identities.pop(next(iter(self._identities)))
                    continue
                if kind in GUILD_RELATION_EVENT_TYPES:
                    relation_key = (flow, kind)
                    self._guild_relations.pop(relation_key, None)
                    self._guild_relations[relation_key] = event
                    while len(self._guild_relations) > self._max_flow_contexts * 2:
                        self._guild_relations.pop(next(iter(self._guild_relations)))
                    continue
                if kind in APPEARANCE_EVENT_TYPES:
                    entity_type = "player" if kind == "appear_player_list" else "monster"
                    opposite = "monster" if entity_type == "player" else "player"
                    contains_boss = False
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
                        if target is self._boss_anchors:
                            contains_boss = True
                        key = (flow, entity_type, uid)
                        target.pop(key, None)
                        target[key] = anchor
                        if len(target) > self._max_entity_anchors:
                            target.pop(next(iter(target)))
                    if contains_boss:
                        event["data"] = {
                            **(event.get("data") or {}),
                            "_contains_boss": True,
                        }
                    continue
                if kind == "disappear_unit_list":
                    fields = (event.get("data") or {}).get("fields") or {}
                    contains_boss = False
                    for uid in fields.get("entity_uids") or []:
                        if not isinstance(uid, (int, float)):
                            continue
                        uid = int(uid)
                        contains_boss = contains_boss or (
                            (flow, "monster", uid) in self._boss_anchors
                        )
                        self._anchors.pop((flow, "player", uid), None)
                        self._anchors.pop((flow, "monster", uid), None)
                        self._boss_anchors.pop((flow, "player", uid), None)
                        # Saída de proximidade encerra a presença visual do
                        # Boss imediatamente. O acumulado de dano permanece
                        # separado e pode ser retomado se o mesmo UID reaparecer.
                        self._boss_anchors.pop((flow, "monster", uid), None)
                        self._map_events.pop((flow, "entity", uid), None)
                        self._map_events.pop((flow, "warp", uid), None)
                    if contains_boss:
                        event["data"] = {
                            **(event.get("data") or {}),
                            "_contains_boss": True,
                        }
                    continue
                if kind in MAP_EVENT_TYPES:
                    fields = (event.get("data") or {}).get("fields") or {}
                    uid = fields.get("entity_uid")
                    if kind == "move_player_request":
                        key = (flow, "local", 0)
                    elif kind == "move_player_update" and isinstance(uid, (int, float)):
                        key = (flow, "entity", int(uid))
                    elif kind == "warp_player" and isinstance(uid, (int, float)):
                        key = (flow, "warp", int(uid))
                    elif kind == "end_warp_player":
                        key = (flow, "warp_end", 0)
                    elif kind in {"request_teleport", "teleport_request"}:
                        key = (flow, "teleport_request", 0)
                    elif kind in {"request_teleport_result", "teleport_response"}:
                        key = (flow, "teleport_result", 0)
                    else:
                        self.ignored_events += 1
                        continue
                    self._map_events.pop(key, None)
                    self._map_events[key] = event
                    while len(self._map_events) > self._max_entity_anchors * 2:
                        self._map_events.pop(next(iter(self._map_events)))
                    continue
                if kind == "dying_unit":
                    self._enrich_combat_context(event, flow)
                    uid = (event.get("data") or {}).get("uid")
                    if isinstance(uid, (int, float)):
                        uid = int(uid)
                        monster_key = (flow, "monster", uid)
                        if (
                            monster_key in self._anchors
                            or monster_key in self._boss_anchors
                        ):
                            event["data"] = {
                                **(event.get("data") or {}),
                                "_known_entity_kind": "monster",
                                "_combat_domain": (
                                    "boss" if monster_key in self._boss_anchors else "pve"
                                ),
                            }
                        self._anchors.pop(monster_key, None)
                        self._boss_anchors.pop(monster_key, None)
                if self._is_boss_event(event):
                    self._accumulate_boss_damage(event)
                    if (
                        self._boss_events.maxlen
                        and len(self._boss_events) == self._boss_events.maxlen
                    ):
                        self.dropped_events += 1
                    self._boss_events.append(event)
                    timestamp = int(event.get("ts_ns") or 0)
                    cutoff = timestamp - self._boss_event_ns
                    if cutoff > 0:
                        self._boss_events = deque(
                            (
                                item
                                for item in self._boss_events
                                if int(item.get("ts_ns") or 0) >= cutoff
                            ),
                            maxlen=self._boss_events.maxlen,
                        )
                    if kind == "dying_unit" and isinstance(
                        (dead_uid := (event.get("data") or {}).get("uid")),
                        (int, float),
                    ):
                        self._forget_boss_damage(flow, int(dead_uid))
                    continue
                # A morte já foi enriquecida antes de remover a âncora do
                # monstro. Reclassificá-la aqui perderia essa evidência e
                # transformaria uma morte PvE em domínio desconhecido.
                if kind in COMBAT_EVENT_TYPES and kind != "dying_unit":
                    self._enrich_combat_context(event, flow)
                if kind not in COMBAT_EVENT_TYPES:
                    self.ignored_events += 1
                    continue
                if self._events.maxlen and len(self._events) == self._events.maxlen:
                    self.dropped_events += 1
                self._events.append(event)

    def _local_combat_uids(self, flow: str) -> set[int]:
        identity = self._identities.get(flow)
        identity_fields = ((identity or {}).get("data") or {}).get("fields") or {}
        character_uid = identity_fields.get("character_uid")
        if character_uid is None:
            return set()
        local_uids: set[int] = set()
        for (anchor_flow, entity_kind, entity_uid), anchor in self._anchors.items():
            if anchor_flow != flow or entity_kind != "player":
                continue
            units = (anchor.get("data") or {}).get("units") or []
            if any(
                unit.get("character_uid") is not None
                and str(unit.get("character_uid")) == str(character_uid)
                for unit in units
                if isinstance(unit, dict)
            ):
                local_uids.add(int(entity_uid))
        return local_uids

    def _enrich_combat_context(self, event: dict[str, Any], flow: str) -> None:
        data = event.get("data")
        if not isinstance(data, dict):
            data = {}
            event["data"] = data
        related = self._related_uids(event)
        boss_uids = {
            key[2] for key in self._boss_anchors
            if key[0] == flow and key[1] == "monster"
        }
        monster_uids = {
            key[2] for key in self._anchors
            if key[0] == flow and key[1] == "monster"
        }
        player_uids = {
            key[2] for key in self._anchors
            if key[0] == flow and key[1] == "player"
        }
        if related.intersection(boss_uids) or event.get("opcode") in BOSS_EVENT_OPCODES:
            domain = "boss"
        elif related.intersection(monster_uids):
            domain = "pve"
        elif related.intersection(player_uids):
            domain = "pvp"
        else:
            domain = "unknown"
        data["_combat_domain"] = domain

        killer_uid = data.get("killer_uid")
        if isinstance(killer_uid, (int, float)):
            local_uids = self._local_combat_uids(flow)
            if local_uids:
                data["_killer_is_client"] = int(killer_uid) in local_uids

    def _accumulate_boss_damage(self, event: dict[str, Any]) -> None:
        if event.get("type") not in {"use_skill_result", "use_normal_skill_result"}:
            return
        data = event.get("data") or {}
        if data.get("ret") not in (None, 0):
            return
        caster_uid = data.get("caster_uid")
        if not isinstance(caster_uid, (int, float)):
            return
        caster_uid = int(caster_uid)
        flow = str(event.get("flow") or "")
        boss_uids = {
            key[2]
            for key in self._boss_anchors
            if key[0] == flow and key[1] == "monster"
        }
        if not boss_uids:
            return
        timestamp = int(event.get("ts_ns") or 0)
        player = self._boss_damage_player(flow, caster_uid)
        for result in data.get("effect_results") or []:
            target_uid = result.get("uid")
            damage = result.get("hp_damage")
            if (
                not isinstance(target_uid, (int, float))
                or int(target_uid) not in boss_uids
                or not isinstance(damage, (int, float))
                or int(damage) <= 0
            ):
                continue
            key = (flow, int(target_uid), caster_uid)
            bucket = self._boss_damage_totals.get(key)
            if bucket is None:
                bucket = {
                    "damage": 0,
                    "first_seen_ns": timestamp,
                    "last_seen_ns": timestamp,
                    "player": player,
                }
                self._boss_damage_totals[key] = bucket
            bucket["damage"] = int(bucket["damage"]) + int(damage)
            bucket["last_seen_ns"] = max(int(bucket["last_seen_ns"]), timestamp)
            if player:
                bucket["player"] = player
        while len(self._boss_damage_totals) > MAX_BOSS_DAMAGE_BUCKETS:
            self._boss_damage_totals.pop(next(iter(self._boss_damage_totals)))

    def _boss_damage_player(self, flow: str, uid: int) -> dict[str, Any]:
        event = self._anchors.get((flow, "player", uid))
        units = (event.get("data") or {}).get("units") or [] if event else []
        unit = units[0] if units and isinstance(units[0], dict) else {}
        return {
            key: unit.get(key)
            for key in (
                "character_uid", "name", "guild_id", "guild_name",
                "group_id", "party_id",
            )
            if unit.get(key) not in (None, "")
        }

    def _forget_boss_damage(self, flow: str, target_uid: int) -> None:
        for key in tuple(self._boss_damage_totals):
            if key[0] == flow and key[1] == target_uid:
                self._boss_damage_totals.pop(key, None)

    def _is_boss_event(self, event: dict[str, Any]) -> bool:
        if event.get("opcode") in BOSS_EVENT_OPCODES or event.get("type") in {
            "FG2C_ans_boss_position_Message",
            "FG2C_notify_boss_result_Message",
            "FG2C_notify_boss_status_list_Message",
            "FG2C_worldboss_hp_sync_Message",
            "FG2C_worldboss_personal_contribution_update_Message",
            "FG2C_noti_worldboss_result_Message",
        }:
            return True
        data = event.get("data") or {}
        flow = str(event.get("flow") or "")
        uid = data.get("uid")
        if (
            event.get("type") == "dying_unit"
            and isinstance(uid, (int, float))
            and any(
                key[0] == flow and key[1] == int(uid)
                for key in self._boss_damage_totals
            )
        ):
            # A morte pode chegar depois do evento de saída de proximidade,
            # quando a âncora visual já foi liberada.
            return True
        if data.get("_known_entity_kind") == "monster":
            if isinstance(uid, (int, float)) and any(
                key[0] == flow and key[1] == int(uid)
                for key in self._boss_damage_totals
            ):
                return True
        boss_uids = {
            key[2] for key in self._boss_anchors if key[0] == flow
        }
        if not boss_uids:
            return False
        return bool(self._related_uids(event).intersection(boss_uids))

    @staticmethod
    def _related_uids(event: dict[str, Any]) -> set[int]:
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
        return related
