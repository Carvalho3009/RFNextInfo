"""Decodificação efêmera de pacotes RF NEXT diretamente da memória."""

from __future__ import annotations

import queue
import socket
import struct
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from core.ingest import DEFAULT_PORTS, SENSITIVE_OPCODE, _safe_parse
from core import rfnext_frame_decode as decoder


MAX_FRAME_BYTES = 1024 * 1024
MAX_FLOW_BUFFER_BYTES = 4 * 1024 * 1024


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

    def __init__(self, max_events: int = 20_000) -> None:
        self._items: queue.SimpleQueue[tuple[int, bytes] | None] = queue.SimpleQueue()
        self._events: deque[dict[str, Any]] = deque(maxlen=max_events)
        self._lock = threading.Lock()
        self._decoder = LiveEventDecoder()
        self._thread: threading.Thread | None = None
        self.decode_errors = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def feed(self, timestamp_ns: int, packet: bytes) -> None:
        self._items.put((timestamp_ns, packet))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._events)

    def clear(self) -> None:
        with self._lock:
            self._events.clear()

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
            if events:
                with self._lock:
                    self._events.extend(events)
