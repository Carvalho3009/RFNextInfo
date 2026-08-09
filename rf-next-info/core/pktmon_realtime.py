"""Streaming contínuo do Packet Monitor usando somente Pktmonapi.dll."""

from __future__ import annotations

import ctypes
from collections import deque
from contextlib import contextmanager
import queue
import struct
import threading
import time
from pathlib import Path
from typing import Callable

API_VERSION = 0x00010000
FILETIME_UNIX_EPOCH = 116_444_736_000_000_000
PKTMON_PAYLOAD_ETHERNET = 1
TCP_PROTOCOL = 6


class _IpAddress(ctypes.Union):
    _fields_ = [
        ("ipv4", ctypes.c_uint32),
        ("ipv4_bytes", ctypes.c_ubyte * 4),
        ("ipv6", ctypes.c_uint64 * 2),
        ("ipv6_bytes", ctypes.c_ubyte * 16),
    ]


class _ProtocolConstraint(ctypes.Structure):
    _fields_ = [
        ("name", ctypes.c_wchar * 256),
        ("present", ctypes.c_uint32),
        ("mac1", ctypes.c_ubyte * 6),
        ("mac2", ctypes.c_ubyte * 6),
        ("vlan_id", ctypes.c_uint16),
        ("ether_type", ctypes.c_uint16),
        ("dscp", ctypes.c_uint16),
        ("transport_protocol", ctypes.c_ubyte),
        ("ip1", _IpAddress),
        ("ip2", _IpAddress),
        ("prefix_length1", ctypes.c_ubyte),
        ("prefix_length2", ctypes.c_ubyte),
        ("port1", ctypes.c_uint16),
        ("port2", ctypes.c_uint16),
        ("tcp_flags", ctypes.c_ubyte),
        ("encap_type", ctypes.c_uint32),
        ("vxlan_port", ctypes.c_uint16),
        ("packets", ctypes.c_uint64),
        ("bytes", ctypes.c_uint64),
    ]


class _StreamDescriptor(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p),
        ("data_size", ctypes.c_uint32),
        ("metadata_offset", ctypes.c_uint32),
        ("packet_offset", ctypes.c_uint32),
        ("packet_length", ctypes.c_uint32),
        ("missed_write", ctypes.c_uint32),
        ("missed_read", ctypes.c_uint32),
    ]


class _StreamMetadata(ctypes.Structure):
    _fields_ = [
        ("packet_group_id", ctypes.c_uint64),
        ("packet_count", ctypes.c_uint16),
        ("appearance_count", ctypes.c_uint16),
        ("direction", ctypes.c_uint16),
        ("packet_type", ctypes.c_uint16),
        ("component_id", ctypes.c_uint16),
        ("edge_id", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16),
        ("drop_reason", ctypes.c_uint32),
        ("drop_location", ctypes.c_uint32),
        ("processor", ctypes.c_uint16),
        ("timestamp", ctypes.c_int64),
    ]


if hasattr(ctypes, "WINFUNCTYPE"):
    _DataCallback = ctypes.WINFUNCTYPE(
        None, ctypes.c_void_p, ctypes.POINTER(_StreamDescriptor)
    )
    _EventCallback = ctypes.WINFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
    )
else:  # pragma: no cover
    _DataCallback = ctypes.CFUNCTYPE(
        None, ctypes.c_void_p, ctypes.POINTER(_StreamDescriptor)
    )
    _EventCallback = ctypes.CFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int
    )


class _StreamConfiguration(ctypes.Structure):
    _fields_ = [
        ("context", ctypes.c_void_p),
        ("event_callback", _EventCallback),
        ("data_callback", _DataCallback),
        ("buffer_multiplier", ctypes.c_uint16),
        ("truncation_size", ctypes.c_uint16),
    ]


class _DataSourceList(ctypes.Structure):
    _fields_ = [("count", ctypes.c_uint32), ("first", ctypes.c_void_p)]


def _check(result: int, operation: str) -> None:
    if result:
        code = result & 0xFFFFFFFF
        raise OSError(code, f"{operation} falhou (HRESULT 0x{code:08X})")


def _data_source_pointers(buffer: ctypes.Array) -> tuple[int, ...]:
    base = ctypes.addressof(buffer)
    count = ctypes.c_uint32.from_address(base).value
    offset = _DataSourceList.first.offset
    step = ctypes.sizeof(ctypes.c_void_p)
    return tuple(
        ctypes.c_void_p.from_address(base + offset + index * step).value or 0
        for index in range(count)
    )


def _matches_tcp_port(packet: bytes, ports: set[int]) -> bool:
    if len(packet) < 14:
        return False
    ether_type = int.from_bytes(packet[12:14], "big")
    offset = 14
    while ether_type in (0x8100, 0x88A8):
        if len(packet) < offset + 4:
            return False
        ether_type = int.from_bytes(packet[offset + 2 : offset + 4], "big")
        offset += 4
    if ether_type == 0x0800:
        if len(packet) < offset + 20 or packet[offset + 9] != TCP_PROTOCOL:
            return False
        transport = offset + (packet[offset] & 0x0F) * 4
    elif ether_type == 0x86DD:
        if len(packet) < offset + 40 or packet[offset + 6] != TCP_PROTOCOL:
            return False
        transport = offset + 40
    else:
        return False
    if len(packet) < transport + 4:
        return False
    source, destination = struct.unpack("!HH", packet[transport : transport + 4])
    return source in ports or destination in ports


class RealtimeCapture:
    """Grava pacotes Ethernet filtrados em PCAP sem parar a captura."""

    def __init__(
        self,
        target: Path | None,
        ports: tuple[int, ...],
        packet_sink: Callable[[int, bytes], None] | None = None,
    ) -> None:
        if not ports or any(not 1 <= port <= 65535 for port in ports):
            raise ValueError("porta inválida")
        self.target = Path(target) if target is not None else None
        self.packet_sink = packet_sink
        self.sink_errors = 0
        self.ports = tuple(dict.fromkeys(ports))
        self._port_set = set(self.ports)
        self.packets = 0
        self.bytes = 0
        self.received_packets = 0
        self.filtered_packets = 0
        self.duplicate_packets = 0
        self.data_sources = 0
        self.missed_write = 0
        self.missed_read = 0
        self._recent_groups: deque[tuple[int, int]] = deque()
        self._recent_group_set: set[tuple[int, int]] = set()
        self._items: queue.SimpleQueue[
            tuple[int, bytes]
            | tuple[int, bytes, bool]
            | tuple[str, Path, threading.Event]
            | threading.Event
            | None
        ] = (
            queue.SimpleQueue()
        )
        self._writer: threading.Thread | None = None
        self._file_lock = threading.Lock()
        self._api = None
        self._handle = ctypes.c_void_p()
        self._session = ctypes.c_void_p()
        self._stream = ctypes.c_void_p()
        self._active = False
        self._writer_error: BaseException | None = None
        self._data_callback = _DataCallback(self._on_data)
        self._event_callback = _EventCallback(lambda *_: None)

    @staticmethod
    def available() -> bool:
        return hasattr(ctypes, "WinDLL") and Path(
            r"C:\Windows\System32\Pktmonapi.dll"
        ).is_file()

    def _bind(self) -> None:
        if not self.available():
            raise RuntimeError("Pktmonapi.dll não está disponível")
        api = ctypes.WinDLL("Pktmonapi.dll")
        definitions = {
            "PacketMonitorInitialize": (
                [
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.c_void_p),
                ],
                ctypes.c_long,
            ),
            "PacketMonitorCreateLiveSession": (
                [
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    ctypes.POINTER(ctypes.c_void_p),
                ],
                ctypes.c_long,
            ),
            "PacketMonitorAddCaptureConstraint": (
                [ctypes.c_void_p, ctypes.POINTER(_ProtocolConstraint)],
                ctypes.c_long,
            ),
            "PacketMonitorEnumDataSources": (
                [
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_ubyte,
                    ctypes.c_size_t,
                    ctypes.POINTER(ctypes.c_size_t),
                    ctypes.c_void_p,
                ],
                ctypes.c_long,
            ),
            "PacketMonitorAddSingleDataSourceToSession": (
                [ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_long,
            ),
            "PacketMonitorCreateRealtimeStream": (
                [
                    ctypes.c_void_p,
                    ctypes.POINTER(_StreamConfiguration),
                    ctypes.POINTER(ctypes.c_void_p),
                ],
                ctypes.c_long,
            ),
            "PacketMonitorAttachOutputToSession": (
                [ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_long,
            ),
            "PacketMonitorSetSessionActive": (
                [ctypes.c_void_p, ctypes.c_ubyte],
                ctypes.c_long,
            ),
            "PacketMonitorCloseRealtimeStream": ([ctypes.c_void_p], None),
            "PacketMonitorCloseSessionHandle": ([ctypes.c_void_p], None),
            "PacketMonitorUninitialize": ([ctypes.c_void_p], None),
        }
        for name, (argtypes, restype) in definitions.items():
            function = getattr(api, name)
            function.argtypes = argtypes
            function.restype = restype
        self._api = api

    def _add_network_interfaces(self) -> None:
        needed = ctypes.c_size_t()
        self._api.PacketMonitorEnumDataSources(
            self._handle, 1, 0, 0, ctypes.byref(needed), None
        )
        if needed.value < ctypes.sizeof(_DataSourceList):
            raise RuntimeError("Pktmon não retornou interfaces de rede")
        buffer = ctypes.create_string_buffer(needed.value)
        _check(
            self._api.PacketMonitorEnumDataSources(
                self._handle,
                1,
                0,
                needed.value,
                ctypes.byref(needed),
                buffer,
            ),
            "enumeração das interfaces",
        )
        sources = _data_source_pointers(buffer)
        if not sources or any(not source for source in sources):
            raise RuntimeError("lista de interfaces do Pktmon inválida")
        for source in sources:
            _check(
                self._api.PacketMonitorAddSingleDataSourceToSession(
                    self._session, source
                ),
                "seleção da interface",
            )
        self.data_sources = len(sources)

    def _add_port_constraint(self, port: int, *, source: bool) -> None:
        constraint = _ProtocolConstraint()
        constraint.name = f"RFQOL-{port}-{'src' if source else 'dst'}"
        constraint.transport_protocol = TCP_PROTOCOL
        constraint.present = (1 << 5) | (1 << (11 if source else 12))
        if source:
            constraint.port1 = port
        else:
            constraint.port2 = port
        _check(
            self._api.PacketMonitorAddCaptureConstraint(
                self._session, ctypes.byref(constraint)
            ),
            f"filtro TCP/{port}",
        )

    def start(self) -> None:
        if self._active:
            raise RuntimeError("captura já está ativa")
        if self.target is not None:
            self.target.parent.mkdir(parents=True, exist_ok=True)
        self._bind()
        try:
            _check(
                self._api.PacketMonitorInitialize(
                    API_VERSION, None, ctypes.byref(self._handle)
                ),
                "inicialização do Pktmon",
            )
            _check(
                self._api.PacketMonitorCreateLiveSession(
                    self._handle,
                    "RFQOL-Realtime",
                    ctypes.byref(self._session),
                ),
                "criação da sessão",
            )
            self._add_network_interfaces()
            for port in self.ports:
                self._add_port_constraint(port, source=True)
                self._add_port_constraint(port, source=False)
            config = _StreamConfiguration(
                None, self._event_callback, self._data_callback, 10, 2048
            )
            _check(
                self._api.PacketMonitorCreateRealtimeStream(
                    self._handle,
                    ctypes.byref(config),
                    ctypes.byref(self._stream),
                ),
                "criação do stream",
            )
            _check(
                self._api.PacketMonitorAttachOutputToSession(
                    self._session, self._stream
                ),
                "vínculo do stream",
            )
            if self.target is not None:
                self._writer = threading.Thread(
                    target=self._write_pcap, daemon=True
                )
                self._writer.start()
            _check(
                self._api.PacketMonitorSetSessionActive(self._session, 1),
                "ativação da sessão",
            )
            self._active = True
        except Exception:
            self.stop()
            raise

    def _on_data(
        self,
        _context: int,
        descriptor_pointer: ctypes.POINTER(_StreamDescriptor),
    ) -> None:
        descriptor = descriptor_pointer.contents
        self.received_packets += 1
        self.missed_write += descriptor.missed_write
        self.missed_read += descriptor.missed_read
        if (
            not descriptor.data
            or descriptor.packet_length < 14
            or descriptor.packet_offset + descriptor.packet_length
            > descriptor.data_size
            or descriptor.metadata_offset + ctypes.sizeof(_StreamMetadata)
            > descriptor.data_size
        ):
            return
        metadata = _StreamMetadata.from_address(
            descriptor.data + descriptor.metadata_offset
        )
        if metadata.packet_type != PKTMON_PAYLOAD_ETHERNET:
            return
        packet_address = descriptor.data + descriptor.packet_offset
        header = ctypes.string_at(
            packet_address, min(descriptor.packet_length, 96)
        )
        if not _matches_tcp_port(header, self._port_set):
            self.filtered_packets += 1
            return
        group = (metadata.processor, metadata.packet_group_id)
        if group in self._recent_group_set:
            self.duplicate_packets += 1
            return
        self._recent_groups.append(group)
        self._recent_group_set.add(group)
        if len(self._recent_groups) > 4096:
            self._recent_group_set.discard(self._recent_groups.popleft())
        packet = ctypes.string_at(
            packet_address,
            descriptor.packet_length,
        )
        timestamp_ns = (metadata.timestamp - FILETIME_UNIX_EPOCH) * 100
        self.packets += 1
        self.bytes += len(packet)
        if self.packet_sink is not None:
            try:
                self.packet_sink(timestamp_ns, packet)
            except Exception:
                self.sink_errors += 1
        if self.target is not None:
            self._items.put((timestamp_ns, packet, True))

    def set_packet_sink(
        self, packet_sink: Callable[[int, bytes], None] | None
    ) -> None:
        self.packet_sink = packet_sink

    def add_ports(self, ports: tuple[int, ...]) -> int:
        ports = tuple(
            port
            for port in dict.fromkeys(ports)
            if 1 <= port <= 65535 and port not in self._port_set
        )
        self._port_set.update(ports)
        return len(ports)

    def checkpoint(self, timeout: float = 5) -> Path:
        """Confirma que todos os pacotes anteriores já estão visíveis no PCAP."""
        if self.target is None:
            raise RuntimeError("stream em memória não possui arquivo de checkpoint")
        if not self._writer or not self._writer.is_alive():
            raise RuntimeError("captura em tempo real não está ativa")
        flushed = threading.Event()
        self._items.put(flushed)
        if not flushed.wait(timeout):
            raise RuntimeError("captura em tempo real não confirmou a leitura")
        if self._writer_error:
            raise RuntimeError("falha ao gravar o PCAP em tempo real")
        return self.target

    def rotate(self, target: Path, timeout: float = 5) -> Path:
        """Fecha o PCAP atual e continua a captura imediatamente em outro."""
        if not self._writer or not self._writer.is_alive():
            raise RuntimeError("captura em tempo real não está ativa")
        if self.target is None:
            raise RuntimeError("stream em memória não possui arquivo para rotacionar")
        previous = self.target
        rotated = threading.Event()
        self._items.put(("rotate", Path(target), rotated))
        if not rotated.wait(timeout):
            raise RuntimeError("captura em tempo real não confirmou a rotação")
        if self._writer_error:
            raise RuntimeError("falha ao rotacionar o PCAP em tempo real")
        return previous

    @contextmanager
    def readable(self):
        """Mantém o arquivo estável enquanto o decoder lê o checkpoint."""
        with self._file_lock:
            if self.target is None:
                raise RuntimeError("stream em memória não possui arquivo para leitura")
            yield self.target

    def _write_pcap(self) -> None:
        header = struct.pack(
            "<IHHIIII", 0xA1B23C4D, 2, 4, 0, 0, 0xFFFF, 1
        )
        output = None
        try:
            if self.target is None:
                raise RuntimeError("destino PCAP não definido")
            self.target.parent.mkdir(parents=True, exist_ok=True)
            output = self.target.open("wb")
            output.write(header)
            while True:
                item = self._items.get()
                if item is None:
                    break
                if isinstance(item, threading.Event):
                    with self._file_lock:
                        output.flush()
                    item.set()
                    continue
                if len(item) == 3 and item[0] == "rotate":
                    _, target, rotated = item
                    try:
                        with self._file_lock:
                            output.flush()
                            output.close()
                            target.parent.mkdir(parents=True, exist_ok=True)
                            output = target.open("wb")
                            output.write(header)
                            self.target = target
                    finally:
                        rotated.set()
                    continue
                if len(item) == 3:
                    timestamp_ns, packet, already_counted = item
                else:
                    timestamp_ns, packet = item
                    already_counted = False
                now_ns = time.time_ns()
                if not 946_684_800_000_000_000 <= timestamp_ns <= (
                    now_ns + 86_400_000_000_000
                ):
                    timestamp_ns = now_ns
                seconds, fraction = divmod(timestamp_ns, 1_000_000_000)
                record = (
                    struct.pack(
                        "<IIII",
                        seconds,
                        fraction,
                        len(packet),
                        len(packet),
                    )
                    + packet
                )
                with self._file_lock:
                    output.write(record)
                    if not already_counted:
                        self.packets += 1
                        self.bytes += len(packet)
        except BaseException as error:
            self._writer_error = error
        finally:
            if output and not output.closed:
                with self._file_lock:
                    output.flush()
                    output.close()

    def stop(self) -> None:
        if self._api and self._session and self._active:
            self._api.PacketMonitorSetSessionActive(self._session, 0)
        self._active = False
        if self._writer:
            self._items.put(None)
            self._writer.join(timeout=10)
            if self._writer.is_alive():
                self._writer_error = RuntimeError(
                    "a gravação não encerrou em 10 segundos"
                )
            self._writer = None
        if self._api and self._stream:
            self._api.PacketMonitorCloseRealtimeStream(self._stream)
            self._stream = ctypes.c_void_p()
        if self._api and self._session:
            self._api.PacketMonitorCloseSessionHandle(self._session)
            self._session = ctypes.c_void_p()
        if self._api and self._handle:
            self._api.PacketMonitorUninitialize(self._handle)
            self._handle = ctypes.c_void_p()
        if self._writer_error:
            error, self._writer_error = self._writer_error, None
            raise RuntimeError("falha ao gravar o PCAP em tempo real") from error

    def __enter__(self) -> "RealtimeCapture":
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()


def split_pcap_by_ports(
    source: Path, targets: list[tuple[Path, tuple[int, ...]]]
) -> list[Path]:
    """Separa um PCAP clássico pelas portas locais temporárias de cada cliente."""
    source = Path(source)
    with source.open("rb") as input_file:
        header = input_file.read(24)
        if len(header) != 24 or header[:4] not in {
            b"\x4d\x3c\xb2\xa1",
            b"\xd4\xc3\xb2\xa1",
        }:
            raise ValueError("PCAP em tempo real inválido")
        outputs = []
        try:
            for path, ports in targets:
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open("wb")
                handle.write(header)
                outputs.append((path, set(ports), handle, 0))
            while record := input_file.read(16):
                if len(record) != 16:
                    raise ValueError("registro PCAP incompleto")
                captured = struct.unpack("<IIII", record)[2]
                packet = input_file.read(captured)
                if len(packet) != captured:
                    raise ValueError("pacote PCAP incompleto")
                for index, (path, ports, handle, count) in enumerate(outputs):
                    if _matches_tcp_port(packet[:96], ports):
                        handle.write(record)
                        handle.write(packet)
                        outputs[index] = (path, ports, handle, count + 1)
        finally:
            for _path, _ports, handle, _count in outputs:
                handle.close()
    kept = []
    for path, _ports, _handle, count in outputs:
        if count:
            kept.append(path)
        else:
            path.unlink(missing_ok=True)
    return kept


def probe(target: Path, seconds: int = 30) -> dict[str, int | float | str]:
    capture = RealtimeCapture(target, (12000, 12010, 12020, 12040))
    started = time.monotonic()
    with capture:
        time.sleep(seconds)
    return {
        "file": str(target),
        "seconds": round(time.monotonic() - started, 3),
        "packets": capture.packets,
        "packet_bytes": capture.bytes,
        "received_packets": capture.received_packets,
        "filtered_packets": capture.filtered_packets,
        "duplicate_packets": capture.duplicate_packets,
        "data_sources": capture.data_sources,
        "missed_write": capture.missed_write,
        "missed_read": capture.missed_read,
    }
