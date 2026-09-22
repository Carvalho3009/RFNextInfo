"""Runtime independente de captura em memória do RF QOL Agent Windows."""

from __future__ import annotations

import ctypes
import os
import threading
import time
import uuid
from ctypes import wintypes
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.connections import agent_connection_aliases, agent_processes, process_started_at
from core.ingest import DEFAULT_PORTS
from core.live_stream import LiveEventStream
from core.pktmon_realtime import RealtimeCapture
from core.pktmon_etw import agent_capture
from core.remote_subsessions import RemoteSubsessionController
from core.web_agent_service import WindowsAgentLocalService
from core.web_agent_transport import AgentTransportError


MIN_AGENT_MEMORY_MB = 256
DEFAULT_AGENT_MEMORY_MB = 1024
MAX_AGENT_MEMORY_MB = 8192
CAPTURE_METRIC_NAMES = (
    "packets", "received_packets", "filtered_packets", "duplicate_packets",
    "missed_write", "missed_read", "sink_errors",
)
MEMORY_PRESSURE_COOLDOWN_SECONDS = 60.0


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = (
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    )


def process_memory_bytes() -> int | None:
    """Lê o working set atual sem adicionar uma dependência externa."""
    if os.name != "nt":
        return None
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    success = psapi.GetProcessMemoryInfo(
        kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb
    )
    return int(counters.WorkingSetSize) if success else None


def agent_memory_limits(value: object) -> dict[str, int]:
    """Traduz o teto escolhido em limites simultâneos de filas e estado vivo."""
    try:
        budget_mb = int(value)
    except (TypeError, ValueError, OverflowError):
        budget_mb = DEFAULT_AGENT_MEMORY_MB
    budget_mb = max(MIN_AGENT_MEMORY_MB, min(MAX_AGENT_MEMORY_MB, budget_mb))
    scale = max(0.25, min(4.0, budget_mb / DEFAULT_AGENT_MEMORY_MB))
    mib = 1024 * 1024

    def scaled(default: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, round(default * scale)))

    return {
        "budget_mb": budget_mb,
        "pending_packets": scaled(4096, 1024, 16_384),
        "pending_packet_bytes": scaled(16, 4, 64) * mib,
        "events": scaled(5000, 1000, 20_000),
        "entity_anchors": scaled(2048, 512, 8192),
        "boss_events": scaled(2048, 512, 8192),
        "flows": scaled(64, 16, 256),
        "pending_segments_per_flow": scaled(256, 64, 1024),
        "pending_bytes_per_flow": scaled(2, 1, 8) * mib,
        "flow_buffer_bytes": scaled(4, 1, 16) * mib,
        "monitor_feed_bytes": scaled(16, 4, 64) * mib,
        "bridge_queue_events": scaled(2048, 512, 8192),
    }


class AgentClientRegistry:
    """Resumo mínimo e limitado dos personagens reconhecidos pelo Agent."""

    def __init__(
        self,
        max_clients: int = 64,
        *,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self.max_clients = max(1, int(max_clients))
        self._clock_ns = clock_ns
        self._clients: dict[str, dict[str, Any]] = {}
        self._retired_clients: dict[str, None] = {}
        self._session_started_ns: dict[str, int] = {}
        self._lock = threading.Lock()

    def observe(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event_type != "character.observed":
            return
        client_ref = str(event.get("client_ref") or "")
        if not client_ref:
            return
        item = {
            "client_ref": client_ref[:64],
            "name": str(payload.get("name") or "")[:96],
            "level": (
                int(payload["level"])
                if isinstance(payload.get("level"), (int, float)) else None
            ),
            "last_seen": str(event.get("occurred_at") or "")[:64],
        }
        if isinstance(payload.get("character_uid"), (int, float)):
            item["character_uid"] = int(payload["character_uid"])
        with self._lock:
            if client_ref in self._retired_clients:
                return
            previous = self._clients.get(client_ref)
            if previous and item.get("character_uid") != previous.get("character_uid"):
                self._session_started_ns.pop(client_ref, None)
            same_character = previous is not None and (
                item.get("character_uid") == previous.get("character_uid")
            )
            if same_character:
                if not item["name"]:
                    item["name"] = previous.get("name", "")
                if item["level"] is None:
                    item["level"] = previous.get("level")
            self._session_started_ns.setdefault(
                client_ref, max(0, int(self._clock_ns()))
            )
            self._clients.pop(client_ref, None)
            self._clients[client_ref] = item
            while len(self._clients) > self.max_clients:
                expired = next(iter(self._clients))
                self._clients.pop(expired)
                self._session_started_ns.pop(expired, None)

    def snapshot(self) -> list[dict[str, Any]]:
        now_ns = max(0, int(self._clock_ns()))
        with self._lock:
            return [
                {
                    **item,
                    "session_duration_seconds": max(
                        0,
                        (now_ns - self._session_started_ns.get(client_ref, now_ns))
                        // 1_000_000_000,
                    ),
                }
                for client_ref, item in self._clients.items()
            ]

    def clear(self) -> None:
        with self._lock:
            self._clients.clear()
            self._session_started_ns.clear()
            self._retired_clients.clear()

    def remove(self, client_ref: str) -> None:
        with self._lock:
            # Eventos já na fila não podem recolocar um processo encerrado na tela.
            self._retired_clients[client_ref] = None
            while len(self._retired_clients) > 256:
                self._retired_clients.pop(next(iter(self._retired_clients)))
            self._clients.pop(client_ref, None)
            self._session_started_ns.pop(client_ref, None)


class StandaloneWindowsAgentRuntime:
    """Captura Pktmon -> decode -> outbox/API, sem processadores do Desktop."""

    def __init__(
        self,
        service: WindowsAgentLocalService,
        registry: AgentClientRegistry,
        *,
        remote_subsessions: RemoteSubsessionController | None = None,
        memory_budget_mb: int = DEFAULT_AGENT_MEMORY_MB,
        ports: tuple[int, ...] = DEFAULT_PORTS,
        capture_factory: Callable[..., RealtimeCapture] = agent_capture,
        process_reader: Callable[..., dict] = agent_processes,
        route_alias_reader: Callable[..., dict[int, str]] = agent_connection_aliases,
        route_change_confirmations: int = 2,
        route_restart_cooldown_seconds: float = 4.0,
        memory_reader: Callable[[], int | None] = process_memory_bytes,
    ) -> None:
        self.service = service
        self.registry = registry
        self.remote_subsessions = remote_subsessions
        self.ports = tuple(dict.fromkeys(int(port) for port in ports))
        if not self.ports or any(not 1 <= port <= 65535 for port in self.ports):
            raise ValueError("Portas do Agent invalidas")
        self.capture_factory = capture_factory
        self.process_reader = process_reader
        self.route_alias_reader = route_alias_reader
        self.route_change_confirmations = max(
            1, min(5, int(route_change_confirmations))
        )
        self.route_restart_cooldown_seconds = max(
            0.0, min(30.0, float(route_restart_cooldown_seconds))
        )
        self.memory_reader = memory_reader
        self.memory_limits = agent_memory_limits(memory_budget_mb)
        self._process_bindings: dict[str, str] = {}
        self._process_bindings_lock = threading.Lock()
        self.live_events = self._new_event_stream()
        self.live_capture: RealtimeCapture | None = None
        self._capture_stopping = False
        self._session_stopping = False
        self.session_id: str | None = None
        self.started_at_ns: int | None = None
        self.last_error = ""
        self.remote_last_error = ""
        self._last_remote_sync = 0.0
        self.character_sync_last_error = ""
        self._last_character_sync = 0.0
        self._last_character_sync_attempt = 0.0
        self._character_sync_changes = 0
        self._known_pids: tuple[int, ...] = ()
        self._capture_ports: tuple[int, ...] = ()
        self._pending_capture_ports: tuple[int, ...] = ()
        self._pending_route_observations = 0
        self._last_capture_restart = 0.0
        self._capture_totals = {name: 0 for name in CAPTURE_METRIC_NAMES}
        self._capture_restarts = 0
        self._memory_peak_bytes = 0
        self._memory_compactions = 0
        self._last_memory_compaction = 0.0
        self._closed = False
        self._lock = threading.RLock()
        # A API local passa a informar também a captura real, e não apenas o
        # bridge de eventos. O token continua obrigatório e nenhum pacote é exposto.
        self.service.api.health_provider = self.health

    @classmethod
    def create_offline(
        cls,
        state_dir: Path,
        installation_id: str,
        *,
        version: str,
        memory_budget_mb: int = DEFAULT_AGENT_MEMORY_MB,
        local_api_port: int = 17621,
        capture_factory: Callable[..., RealtimeCapture] = agent_capture,
        process_reader: Callable[..., dict] = agent_processes,
        route_alias_reader: Callable[..., dict[int, str]] = agent_connection_aliases,
        route_change_confirmations: int = 2,
        route_restart_cooldown_seconds: float = 4.0,
        memory_reader: Callable[[], int | None] = process_memory_bytes,
        **service_options: Any,
    ) -> "StandaloneWindowsAgentRuntime":
        limits = agent_memory_limits(memory_budget_mb)
        registry = AgentClientRegistry()
        service = WindowsAgentLocalService.create_offline(
            Path(state_dir),
            installation_id,
            version=version,
            local_api_port=local_api_port,
            max_monitor_events=limits["events"],
            max_monitor_bytes=limits["monitor_feed_bytes"],
            max_queue_events=limits["bridge_queue_events"],
            event_observer=registry.observe,
            **service_options,
        )
        return cls(
            service,
            registry,
            memory_budget_mb=memory_budget_mb,
            capture_factory=capture_factory,
            process_reader=process_reader,
            route_alias_reader=route_alias_reader,
            route_change_confirmations=route_change_confirmations,
            route_restart_cooldown_seconds=route_restart_cooldown_seconds,
            memory_reader=memory_reader,
        )

    @classmethod
    def create_online(
        cls,
        state_dir: Path,
        installation_id: str,
        server_url: str,
        *,
        version: str,
        memory_budget_mb: int = DEFAULT_AGENT_MEMORY_MB,
        local_api_port: int = 17621,
        capture_factory: Callable[..., RealtimeCapture] = agent_capture,
        process_reader: Callable[..., dict] = agent_processes,
        route_alias_reader: Callable[..., dict[int, str]] = agent_connection_aliases,
        route_change_confirmations: int = 2,
        route_restart_cooldown_seconds: float = 4.0,
        memory_reader: Callable[[], int | None] = process_memory_bytes,
        **service_options: Any,
    ) -> "StandaloneWindowsAgentRuntime":
        limits = agent_memory_limits(memory_budget_mb)
        registry = AgentClientRegistry()
        remote_subsessions = RemoteSubsessionController(
            Path(state_dir) / "remote-subsessions.json", registry.snapshot
        )

        def observe(event: dict[str, Any]) -> None:
            registry.observe(event)
            remote_subsessions.observe(event)

        service = WindowsAgentLocalService.create_online(
            Path(state_dir),
            installation_id,
            server_url,
            version=version,
            local_api_port=local_api_port,
            max_monitor_events=limits["events"],
            max_monitor_bytes=limits["monitor_feed_bytes"],
            max_queue_events=limits["bridge_queue_events"],
            event_observer=observe,
            **service_options,
        )
        remote_subsessions.set_submitter(service.submit_subsession)
        return cls(
            service,
            registry,
            remote_subsessions=remote_subsessions,
            memory_budget_mb=memory_budget_mb,
            capture_factory=capture_factory,
            process_reader=process_reader,
            route_alias_reader=route_alias_reader,
            route_change_confirmations=route_change_confirmations,
            route_restart_cooldown_seconds=route_restart_cooldown_seconds,
            memory_reader=memory_reader,
        )

    @property
    def active(self) -> bool:
        capture = self.live_capture
        return bool(capture is not None and not self._capture_stopping and not self._session_stopping
                    and not getattr(capture, "last_error", "")
                    and getattr(capture, "is_active", getattr(
                        capture, "_active", not getattr(capture, "stopped", False))))

    def _new_event_stream(self) -> LiveEventStream:
        limits = self.memory_limits
        stream = LiveEventStream(
            max_events=limits["events"],
            max_entity_anchors=limits["entity_anchors"],
            max_pending_packets=limits["pending_packets"],
            max_pending_packet_bytes=limits["pending_packet_bytes"],
            max_boss_events=limits["boss_events"],
            max_flows=limits["flows"],
            max_pending_segments_per_flow=limits["pending_segments_per_flow"],
            max_pending_bytes_per_flow=limits["pending_bytes_per_flow"],
            max_flow_buffer_bytes=limits["flow_buffer_bytes"],
            event_sink=self.service.submit,
        )
        stream.set_connection_alias_resolver(
            self._read_process_aliases
        )
        return stream

    def _read_process_aliases(self) -> dict[int, str]:
        aliases = self.route_alias_reader(self.ports)
        projector = self.service.runtime.bridge.projector
        with self._process_bindings_lock:
            for alias in set(aliases.values()):
                parts = alias.split(":")
                if len(parts) == 3 and parts[0] == "process" and all(
                    part.isdigit() and int(part) > 0 for part in parts[1:]
                ):
                    self._process_bindings[alias] = projector.client_ref_for_connection(
                        f"client-route:{alias}"
                    )
        return aliases

    def _reconcile_process_bindings(self) -> set[int]:
        retained_pids = set()
        with self._process_bindings_lock:
            for alias, client_ref in list(self._process_bindings.items()):
                _, pid, started = alias.split(":")
                current = process_started_at(int(pid))
                if current is None or current == int(started):
                    retained_pids.add(int(pid))
                else:
                    self.registry.remove(client_ref)
                    history = self.service.runtime.bridge.projector.character_history
                    if history is not None:
                        history.release(f"client-route:{alias}")
                    self._process_bindings.pop(alias)
        return retained_pids

    def detected_processes(self) -> dict[str, tuple[set[int], set[int], set[int]]]:
        result = self.process_reader(self.ports)
        return dict(result) if isinstance(result, dict) else {}

    @staticmethod
    def _capture_routes(
        processes: dict[str, tuple[set[int], set[int], set[int]]],
        base_ports: tuple[int, ...],
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        pids: set[int] = set()
        capture_ports = list(base_ports)
        for raw in processes.values():
            if not isinstance(raw, (tuple, list)) or len(raw) < 3:
                continue
            process_pids, local_ports, remote_ports = raw[:3]
            pids.update(int(pid) for pid in process_pids)
            # agent_processes returns relay-only local ports, including when
            # another client of the same executable uses a direct connection.
            capture_ports.extend(int(port) for port in local_ports)
            capture_ports.extend(int(port) for port in remote_ports)
        return tuple(sorted(pids)), tuple(sorted(set(capture_ports)))

    def start_local_api(self) -> int:
        port = self.service.start_local_api()
        self.service.start_delivery()
        self._sync_character_profiles(force=True)
        return port

    def _sync_character_profiles(self, *, force: bool = False) -> bool:
        """Atualiza o histórico sem interromper o Agent se o site falhar."""
        authorization = self.service.runtime.health().get("authorization", {})
        if (
            isinstance(authorization, dict)
            and authorization.get("required")
            and not authorization.get("authorized")
        ):
            return False
        now = time.monotonic()
        if not force:
            if self._last_character_sync and now - self._last_character_sync < 30 * 60:
                return False
            if now - self._last_character_sync_attempt < 60:
                return False
        self._last_character_sync_attempt = now
        try:
            changed = int(self.service.sync_character_profiles())
        except Exception as error:
            self.character_sync_last_error = (
                f"{type(error).__name__}: {error}"
            )[:240]
            return False
        self._last_character_sync = now
        self._character_sync_changes += max(0, changed)
        self.character_sync_last_error = ""
        return True

    def start_capture(self) -> dict[str, Any]:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.service.require_capture_authorization()
        with self._lock:
            if self._closed:
                raise RuntimeError("Agent ja encerrado")
            if self.active:
                return self.health()
            if self._session_stopping:
                raise RuntimeError("A sessão ainda está encerrando; tente pausá-la novamente.")
            if self.live_capture is not None:
                self._stop_backend()
            if self.session_id is not None:
                # Recover capture only; do not mint another session per client.
                self._start_backend(self._capture_ports or self.ports)
                return self.health()
            processes = self.detected_processes()
            pids, capture_ports = self._capture_routes(processes, self.ports)
            if not pids:
                raise RuntimeError("Abra um cliente PC e entre no jogo")
            session_id = f"agent-{time.time_ns()}-{uuid.uuid4().hex[:12]}"
            self.last_error = ""
            self._capture_totals = {
                name: 0 for name in CAPTURE_METRIC_NAMES
            }
            self._capture_restarts = 0
            self.registry.clear()
            self.live_events.clear()
            self.live_events.set_transport_ports(capture_ports)
            self.live_events.set_connection_aliases(
                self._read_process_aliases()
            )
            try:
                self.live_events.start()
                self.session_id = session_id
                self.service.start_session(session_id)
                self._start_backend(capture_ports)
            except Exception as error:
                try:
                    self.live_events.stop()
                    self.service.finish_session(session_id, reason="capture_start_failed")
                    self.service.runtime.bridge.wait_until_idle()
                    self.session_id = None
                except Exception as cleanup_error:
                    self._session_stopping = True
                    error.add_note(f"Limpeza de início pendente: {type(cleanup_error).__name__}")
                self.last_error = f"{type(error).__name__}: {error}"[:240]
                raise
            self._capture_ports = capture_ports
            self._pending_capture_ports = ()
            self._pending_route_observations = 0
            self._last_capture_restart = time.monotonic()
            self.session_id = session_id
            self.started_at_ns = time.time_ns()
            self._known_pids = pids
            if hasattr(self.service, "heartbeat"):
                self.service.heartbeat("active", len(pids))
            return self.health()

    def _accumulate_capture_metrics(self, capture: object) -> None:
        for name in CAPTURE_METRIC_NAMES:
            self._capture_totals[name] += int(
                getattr(capture, name, 0) or 0
            )

    def _stop_backend(self) -> None:
        capture = self.live_capture
        if capture is None:
            return
        self._capture_stopping = True
        try:
            capture.stop()
        except Exception as error:
            self.last_error = f"Encerramento da captura pendente: {type(error).__name__}: {error}"[:240]
            raise
        # Consolidate once, after all callbacks have stopped. Retain ownership
        # and unaggregated counters if cleanup is incomplete.
        self._accumulate_capture_metrics(capture)
        self.live_capture = None
        self._capture_stopping = False

    def _start_backend(self, ports: tuple[int, ...]) -> None:
        if self.live_capture is not None:
            raise RuntimeError("A captura anterior ainda precisa ser encerrada.")
        capture = self.capture_factory(None, ports)
        self.live_capture = capture
        self._capture_stopping = False
        try:
            self.live_events.set_transport_ports(ports)
            capture.set_packet_sink(self.live_events.feed)
            capture.start()
        except Exception as error:
            try:
                self._stop_backend()
            except Exception as cleanup_error:
                error.add_note(f"Limpeza do capturador pendente: {type(cleanup_error).__name__}")
            raise
        self._capture_ports = ports
        self.last_error = ""

    def _restart_capture_for_routes(
        self, capture_ports: tuple[int, ...]
    ) -> bool:
        previous = self.live_capture
        previous_ports = self._capture_ports
        if not capture_ports:
            return False
        limit = getattr(previous, "max_filter_ports", None)
        if limit is not None and len(capture_ports) > limit:
            self.last_error = f"As rotas excedem o limite de {limit} filtros; captura atual preservada."
            raise RuntimeError(self.last_error)
        self._stop_backend()
        try:
            self._start_backend(capture_ports)
        except Exception as route_error:
            if self.live_capture is not None:
                raise  # Cleanup pending: never start a second native consumer.
            try:
                self._start_backend(previous_ports or self.ports)
            except Exception as fallback_error:
                self.last_error = (
                    "Falha ao atualizar rotas e restaurar captura: "
                    f"{type(route_error).__name__}; "
                    f"{type(fallback_error).__name__}"
                )[:240]
                raise RuntimeError(self.last_error) from fallback_error
            self._capture_ports = previous_ports
            self.last_error = (
                "Não foi possível aplicar as novas rotas; captura anterior restaurada: "
                f"{type(route_error).__name__}: {route_error}"
            )[:240]
            return False

        self._capture_ports = capture_ports
        self._capture_restarts += 1
        self.last_error = ""
        return True

    def refresh_routes(self) -> dict[str, Any]:
        # Network I/O must not hold the lock used by local health and controls.
        authorized = self.service.refresh_authorization()
        if authorized:
            self._sync_character_profiles()
        with self._lock:
            if self._closed:
                return {"no_clients": True, "capture_authorized": False}
            if self.session_id is not None and not authorized:
                self.stop_capture(reason="authorization_expired")
            processes = self.detected_processes()
            self.live_events.set_connection_aliases(
                self._read_process_aliases()
            )
            pids, capture_ports = self._capture_routes(processes, self.ports)
            restarted = False
            if authorized and self.session_id is not None and not self._session_stopping and not self.active:
                if time.monotonic() - self._last_capture_restart >= self.route_restart_cooldown_seconds:
                    self._last_capture_restart = time.monotonic()
                    restarted = self._restart_capture_for_routes(capture_ports)
            if self.active and capture_ports:
                # Keep only the current generation of routes. A transient
                # disappearance does not justify a restart; a new stable route does.
                desired_ports = capture_ports
                # add_ports amplia o filtro defensivo em memória, mas uma
                # sessão Pktmon ativa não recebe novos filtros kernel. Quando
                # a rota permanece estável por duas leituras, recriamos apenas
                # a captura e mantemos a mesma sessão/outbox.
                if set(desired_ports).issubset(self._capture_ports):
                    self._pending_capture_ports = ()
                    self._pending_route_observations = 0
                else:
                    if desired_ports == self._pending_capture_ports:
                        self._pending_route_observations += 1
                    else:
                        self._pending_capture_ports = desired_ports
                        self._pending_route_observations = 1
                    cooldown_elapsed = (
                        time.monotonic() - self._last_capture_restart
                        >= self.route_restart_cooldown_seconds
                    )
                    if (
                        self._pending_route_observations
                        >= self.route_change_confirmations
                        and cooldown_elapsed
                    ):
                        self._last_capture_restart = time.monotonic()
                        restarted = self._restart_capture_for_routes(
                            desired_ports
                        )
                        self._last_capture_restart = time.monotonic()
                        self._pending_capture_ports = ()
                        self._pending_route_observations = 0
            pids = tuple(sorted(set(pids) | self._reconcile_process_bindings()))
            self._known_pids = pids
            if hasattr(self.service, "heartbeat"):
                try:
                    self.service.heartbeat(
                        "active" if self.active else "stopped",
                        len(pids),
                    )
                except Exception as error:
                    self.last_error = f"Heartbeat: {type(error).__name__}: {error}"[:240]
            result = {
                "client_processes": len(pids),
                "client_pids": list(pids),
                "no_clients": not pids,
                "capture_restarted": restarted,
                "capture_port_count": len(self._capture_ports),
                "capture_authorized": authorized and not self._session_stopping,
            }
        result["remote_subsession_commands"] = self._sync_remote_subsessions()
        return result

    def _sync_remote_subsessions(self) -> int:
        controller = self.remote_subsessions
        now = time.monotonic()
        if controller is None or now - self._last_remote_sync < 5.0:
            return 0
        self._last_remote_sync = now
        results = controller.pending_results()
        progress = controller.progress_updates()
        try:
            commands = self.service.sync_subsession_commands(results, progress)
            controller.acknowledge_results(results)
            if any(command.get("action") == "stop" for command in commands):
                self.service.runtime.bridge.wait_until_idle()
            with self._lock:
                if not self._closed:
                    controller.apply_commands(
                        commands, session_id=self.session_id, capture_active=self.active,
                    )
            self.remote_last_error = ""
            return len(commands)
        except AgentTransportError as error:
            self.remote_last_error = str(error.code)[:64]
        except Exception as error:
            self.remote_last_error = type(error).__name__[:64]
        return 0

    def stop_capture(self, *, reason: str = "paused") -> dict[str, Any]:
        with self._lock:
            live = self.live_capture
            session_id = self.session_id
            self._session_stopping = True
            failures = []
            if live is not None:
                try:
                    self._stop_backend()
                except Exception as error:
                    # Keep session, callbacks and resource ownership for retry.
                    raise RuntimeError(self.last_error) from error
            self.live_events.stop()
            self.service.runtime.bridge.wait_until_idle()
            if self.remote_subsessions is not None:
                self.remote_subsessions.finish_all(session_id)
            if session_id:
                try:
                    if reason == "paused":
                        self.service.pause_session(session_id, reason=reason)
                    else:
                        self.service.finish_session(session_id, reason=reason)
                    self.service.runtime.bridge.wait_until_idle()
                except Exception as error:
                    self.last_error = f"Encerramento da sessão pendente: {type(error).__name__}"
                    raise RuntimeError(self.last_error) from error
            self.started_at_ns = None
            self.session_id = None
            self._session_stopping = False
            self._known_pids = ()
            self._capture_ports = ()
            self._pending_capture_ports = ()
            self._pending_route_observations = 0
            self.registry.clear()
            if reason != "paused":
                with self._process_bindings_lock:
                    self._process_bindings.clear()
            if hasattr(self.service, "heartbeat"):
                try:
                    self.service.heartbeat("stopped", 0)
                except Exception as error:
                    failures.append(f"heartbeat: {type(error).__name__}")
            if failures:
                self.last_error = "; ".join(failures)
            return {"active": False, "failures": failures}

    def configure_memory_budget(self, value: object) -> bool:
        limits = agent_memory_limits(value)
        with self._lock:
            if self.live_capture is not None or self.session_id is not None:
                return False
            self.live_events.stop()
            self.memory_limits = limits
            self.service.feed.configure_limits(
                max_events=limits["events"],
                max_bytes=limits["monitor_feed_bytes"]
            )
            self.live_events = self._new_event_stream()
            return True

    def pairing_credentials(self) -> dict[str, object]:
        return self.service.pairing_credentials()

    def health(self) -> dict[str, Any]:
        with self._lock:
            service_health = self.service.health()
            capture = self.live_capture
            active = self.active
            stream = self.live_events.metrics()
            uptime_seconds = (
                max(0.0, (time.time_ns() - self.started_at_ns) / 1_000_000_000)
                if self.started_at_ns else 0.0
            )
            capture_metrics = {
                name: self._capture_totals[name]
                + int(getattr(capture, name, 0) or 0)
                for name in CAPTURE_METRIC_NAMES
            }
            capture_metrics["route_restarts"] = self._capture_restarts
            capture_metrics["port_count"] = len(self._capture_ports)
            capture_metrics["backend"] = getattr(capture, "backend", "pktmon-streaming") if capture else None
            capture_metrics["backend_error"] = getattr(capture, "last_error", "") or None
            capture_metrics["property_errors"] = int(getattr(capture, "property_errors", 0))
            capture_metrics["last_packet_ns"] = int(getattr(capture, "last_packet_ns", 0))
            capture_metrics["native_loss_counters_available"] = bool(capture and capture_metrics["backend"] != "pktmon-etw")
            capture_metrics["cleanup_pending"] = self._capture_stopping
            memory_bytes = self.memory_reader()
            if memory_bytes is not None:
                memory_bytes = max(0, int(memory_bytes))
                self._memory_peak_bytes = max(self._memory_peak_bytes, memory_bytes)
                pressure_bytes = self.memory_limits["budget_mb"] * 1024 * 1024
                if (
                    memory_bytes >= pressure_bytes
                    and time.monotonic() - self._last_memory_compaction
                    >= MEMORY_PRESSURE_COOLDOWN_SECONDS
                ):
                    self.live_events.compact(0.5)
                    self._memory_compactions += 1
                    self._last_memory_compaction = time.monotonic()
            else:
                pressure_bytes = self.memory_limits["budget_mb"] * 1024 * 1024
            return {
                "state": "capturing" if active else "attention" if self.session_id or self._capture_stopping else "idle",
                "active": active,
                "sampled_at_ns": time.time_ns(),
                "session_active": self.session_id is not None,
                "session_stopping": self._session_stopping,
                "client_processes": len(self._known_pids),
                "clients": self.registry.snapshot(),
                "uptime_seconds": round(uptime_seconds, 3),
                "memory_budget_mb": self.memory_limits["budget_mb"],
                "memory": {
                    "working_set_bytes": memory_bytes,
                    "peak_working_set_bytes": self._memory_peak_bytes,
                    "limit_bytes": pressure_bytes,
                    "pressure": bool(
                        memory_bytes is not None and memory_bytes >= pressure_bytes
                    ),
                    "compactions": self._memory_compactions,
                },
                "capture": capture_metrics,
                "decoder": stream,
                "projection": service_health.get("capture_bridge", {}),
                "local_api": service_health.get("local_api", {}),
                "outbox": service_health.get("outbox", {}),
                "throughput": service_health.get("throughput", {}),
                "server": {
                    "mode": service_health.get("mode", "offline"),
                    "state": service_health.get("state", "offline_shadow"),
                    "delivery": service_health.get("delivery", {}),
                    "authorization": service_health.get("authorization", {}),
                },
                "remote_subsessions": (
                    {
                        **self.remote_subsessions.health(),
                        "last_error": self.remote_last_error or None,
                    }
                    if self.remote_subsessions is not None else {
                        "active": 0,
                        "pending_results": 0,
                        "last_error": None,
                    }
                ),
                "character_sync": {
                    "automatic": True,
                    "interval_seconds": 30 * 60,
                    "last_success_monotonic": self._last_character_sync,
                    "profiles_changed": self._character_sync_changes,
                    "last_error": self.character_sync_last_error or None,
                },
                "last_error": self.last_error,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
        self.stop_capture(reason="abandoned")
        self.service.close()
        with self._lock:
            self._closed = True
