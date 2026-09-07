"""Compatibilidade Windows 10: Pktmon/ETW em memória, sem ETL/PCAP."""

from __future__ import annotations

import ctypes as ct
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

from core.capture import _pktmon_state
from core.pktmon_realtime import (
    FILETIME_UNIX_EPOCH, RealtimeCapture, _matches_tcp_port,
    _normalized_timestamp_ns,
)


class _Header(ct.Structure):
    _fields_ = [
        ("size", ct.c_uint16), ("header_type", ct.c_uint16),
        ("flags", ct.c_uint16), ("property", ct.c_uint16),
        ("thread", ct.c_uint32), ("process", ct.c_uint32),
        ("timestamp", ct.c_int64), ("provider", ct.c_ubyte * 16),
        ("event_id", ct.c_uint16), ("version", ct.c_ubyte),
        ("channel", ct.c_ubyte), ("level", ct.c_ubyte), ("opcode", ct.c_ubyte),
        ("task", ct.c_uint16), ("keywords", ct.c_uint64),
        ("processor_time", ct.c_uint64), ("activity", ct.c_ubyte * 16),
    ]


class _Record(ct.Structure):
    _fields_ = [
        ("header", _Header), ("buffer_context", ct.c_uint32),
        ("extended_count", ct.c_uint16), ("data_length", ct.c_uint16),
        ("extended", ct.c_void_p), ("data", ct.c_void_p), ("context", ct.c_void_p),
    ]


_Callback = getattr(ct, "WINFUNCTYPE", ct.CFUNCTYPE)(None, ct.POINTER(_Record))


class _Logfile(ct.Structure):
    # ponytail: somente x64, como o instalador; blocos de saída não utilizados
    # seguem EVENT_TRACE/TRACE_LOGFILE_HEADER do SDK 10.0.19041 (88/280 bytes).
    _fields_ = [
        ("file_name", ct.c_wchar_p), ("logger_name", ct.c_wchar_p),
        ("current_time", ct.c_int64), ("buffers_read", ct.c_uint32),
        ("mode", ct.c_uint32), ("current_event", ct.c_uint64 * 11),
        ("header", ct.c_uint64 * 35), ("buffer_callback", ct.c_void_p),
        ("buffer_size", ct.c_uint32), ("filled", ct.c_uint32),
        ("events_lost", ct.c_uint32), ("callback", _Callback),
        ("is_kernel", ct.c_uint32), ("context", ct.c_void_p),
    ]


class _Property(ct.Structure):
    _fields_ = [("name", ct.c_uint64), ("index", ct.c_uint32), ("reserved", ct.c_uint32)]


PROVIDER = uuid.UUID("4d4f80d9-c8bd-4d73-bb5b-19c90402c5ac").bytes_le
INVALID_TRACE = 2**64 - 1


class PktmonEtwCapture(RealtimeCapture):
    backend = "pktmon-etw"

    def __init__(self, target, ports, packet_sink=None):
        if target is not None:
            raise ValueError("A captura de compatibilidade não grava pacotes em disco.")
        super().__init__(None, ports, packet_sink)
        self._process = None
        self._consumer = None
        self._trace = INVALID_TRACE
        self._etw = None
        self._filters: list[str] = []
        self._prefix = f"RFCompanion-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self._stopping = threading.Event()
        self._record_callback = _Callback(self._on_record)
        self.last_error = ""
        self.property_errors = 0
        self._pktmon = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "pktmon.exe")

    def _command(self, *args):
        result = subprocess.run(
            [self._pktmon, *args], capture_output=True, text=True,
            errors="replace", timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode:
            # Nunca incorporar saída da captura em mensagens/diagnósticos.
            raise RuntimeError(f"Pktmon: comando {args[0]} falhou ({result.returncode}).")
        return result.stdout

    def _bind_etw(self):
        if os.name != "nt" or ct.sizeof(ct.c_void_p) != 8:
            raise RuntimeError("A compatibilidade Pktmon/ETW exige Windows x64.")
        if not Path(self._pktmon).is_file():
            raise RuntimeError("Pktmon não encontrado. É necessário Windows 10 22H2 ou posterior.")
        self._etw = ct.WinDLL("advapi32.dll", use_last_error=True)
        self._etw.OpenTraceW.argtypes = [ct.POINTER(_Logfile)]
        self._etw.OpenTraceW.restype = ct.c_uint64
        self._etw.ProcessTrace.argtypes = [ct.POINTER(ct.c_uint64), ct.c_uint32, ct.c_void_p, ct.c_void_p]
        self._etw.ProcessTrace.restype = ct.c_uint32
        self._etw.CloseTrace.argtypes = [ct.c_uint64]
        self._etw.CloseTrace.restype = ct.c_uint32
        self._tdh = ct.WinDLL("tdh.dll")
        self._tdh.TdhGetPropertySize.argtypes = [ct.POINTER(_Record), ct.c_uint32, ct.c_void_p, ct.c_uint32, ct.POINTER(_Property), ct.POINTER(ct.c_uint32)]
        self._tdh.TdhGetPropertySize.restype = ct.c_uint32
        self._tdh.TdhGetProperty.argtypes = [ct.POINTER(_Record), ct.c_uint32, ct.c_void_p, ct.c_uint32, ct.POINTER(_Property), ct.c_uint32, ct.c_void_p]
        self._tdh.TdhGetProperty.restype = ct.c_uint32

    def _property_bytes(self, record, name):
        text = ct.create_unicode_buffer(name)
        descriptor = _Property(ct.addressof(text), 0xFFFFFFFF, 0)
        size = ct.c_uint32()
        result = self._tdh.TdhGetPropertySize(record, 0, None, 1, ct.byref(descriptor), ct.byref(size))
        if result or not 0 < size.value <= 65535:
            raise ValueError("Propriedade ETW ausente ou fora do limite")
        buffer = ct.create_string_buffer(size.value)
        if self._tdh.TdhGetProperty(record, 0, None, 1, ct.byref(descriptor), size, buffer):
            raise ValueError("Propriedade ETW inválida")
        return buffer.raw

    def _on_record(self, pointer):
        try:
            record = pointer.contents
            if bytes(record.header.provider) != PROVIDER or record.header.event_id not in (160, 170):
                return
            self.received_packets += 1
            packet = self._property_bytes(pointer, "Payload")
            original = int.from_bytes(self._property_bytes(pointer, "OriginalPayloadSize"), "little")
            if not 14 <= len(packet) <= 65535 or original != len(packet):
                self.property_errors += 1
                return
            if not _matches_tcp_port(packet[:96], self._port_set):
                self.filtered_packets += 1
                return
            stamp = _normalized_timestamp_ns((record.header.timestamp - FILETIME_UNIX_EPOCH) * 100)
            self.packets += 1
            self.bytes += len(packet)
            if self.packet_sink is not None:
                try:
                    self.packet_sink(stamp, packet)
                except Exception:
                    self.sink_errors += 1
        except Exception:
            self.property_errors += 1

    def _consume(self):
        handle = ct.c_uint64(self._trace)
        try:
            result = self._etw.ProcessTrace(ct.byref(handle), 1, None, None)
        except Exception:
            result = "erro nativo"
        if not self._stopping.is_set():
            self.last_error = f"O stream Pktmon/ETW encerrou ({result}). Reinicie a captura."
            self._active = False

    def _open_trace(self):
        self._logfile = _Logfile(logger_name="PktMon", mode=0x10000100, callback=self._record_callback)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError("Pktmon não iniciou em tempo real. Verifique privilégios de administrador e a versão do Windows.")
            # OpenTrace pode devolver um handle antes de a sessão existir.
            # Não iniciar ProcessTrace até o controlador confirmar a captura.
            if _pktmon_state(self._command("status")) is not True:
                self._stopping.wait(0.1)
                continue
            handle = self._etw.OpenTraceW(ct.byref(self._logfile))
            if handle != INVALID_TRACE:
                self._trace = handle
                return
            error = ct.get_last_error()
            if error not in (2, 4201):
                raise OSError(error, "Não foi possível abrir o stream ETW do Pktmon")
            self._stopping.wait(0.05)
        raise RuntimeError("O stream ETW do Pktmon não ficou disponível.")

    def start(self):
        if self._active or self._process is not None:
            raise RuntimeError("Captura já está ativa")
        self._bind_etw()
        if _pktmon_state(self._command("status")) is not False:
            raise RuntimeError("Pktmon ocupado ou estado desconhecido. Nenhuma captura existente foi alterada.")
        self._stopping.clear()
        self.last_error = ""
        try:
            self._add_filters(self.ports)
            self._process = subprocess.Popen(
                [self._pktmon, "start", "--capture", "--comp", "nics", "--pkt-size", "0",
                 "--flags", "0x10", "--log-mode", "real-time"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self._open_trace()
            if self._process.poll() is not None:
                raise RuntimeError("O processo Pktmon encerrou durante a inicialização.")
            self._active = True
            self._consumer = threading.Thread(target=self._consume, daemon=True)
            self._consumer.start()
        except Exception:
            self.stop()
            raise

    def _add_filters(self, ports):
        for port in ports:
            name = f"{self._prefix}-{port}"
            self._command("filter", "add", name, "-t", "TCP", "-p", str(port))
            self._filters.append(name)

    def add_ports(self, ports):
        # O runtime recria os filtros kernel quando a nova rota estabiliza.
        # Nao alterar filtros do Pktmon enquanto a captura esta em andamento.
        added = super().add_ports(ports)
        self.ports = tuple(sorted(self._port_set))
        return added

    def stop(self):
        self._stopping.set()
        self._active = False
        failures = []
        if self._process is not None and self._process.poll() is None:
            try:
                self._command("stop")
                self._process.wait(timeout=5)
            except Exception:
                failures.append("Não foi possível encerrar o processo Pktmon normalmente.")
                self._process.terminate()
        if self._trace != INVALID_TRACE:
            self._etw.CloseTrace(self._trace)
            self._trace = INVALID_TRACE
        if self._consumer is not None:
            self._consumer.join(timeout=5)
            if self._consumer.is_alive():
                failures.append("O consumidor ETW ainda está encerrando.")
            else:
                self._consumer = None
        for name in list(self._filters):
            try:
                self._command("filter", "remove", name)
                self._filters.remove(name)
            except Exception:
                failures.append("Não foi possível remover um filtro do Companion.")
        self._process = None
        if failures:
            raise RuntimeError(" ".join(failures))


def agent_capture(target, ports):
    """Seleciona pela capacidade da DLL; não mascara falhas de permissão/start."""
    native = RealtimeCapture(target, ports)
    try:
        native._bind()
    except (AttributeError, OSError, RuntimeError):
        return PktmonEtwCapture(target, ports)
    return native
