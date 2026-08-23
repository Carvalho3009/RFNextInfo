"""Runtime independente de captura em memória do RF QOL Agent Windows."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.connections import connected_processes
from core.ingest import DEFAULT_PORTS
from core.live_stream import LiveEventStream
from core.pktmon_realtime import RealtimeCapture
from core.web_agent_service import WindowsAgentLocalService


MIN_AGENT_MEMORY_MB = 256
DEFAULT_AGENT_MEMORY_MB = 1024
MAX_AGENT_MEMORY_MB = 8192


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

    def __init__(self, max_clients: int = 64) -> None:
        self.max_clients = max(1, int(max_clients))
        self._clients: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def observe(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if event_type == "session.lifecycle" and payload.get("state") == "started":
            with self._lock:
                self._clients.clear()
            return
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
        with self._lock:
            self._clients.pop(client_ref, None)
            self._clients[client_ref] = item
            while len(self._clients) > self.max_clients:
                self._clients.pop(next(iter(self._clients)))

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._clients.values()]


class StandaloneWindowsAgentRuntime:
    """Captura Pktmon -> decode -> outbox/API, sem processadores do Desktop."""

    def __init__(
        self,
        service: WindowsAgentLocalService,
        registry: AgentClientRegistry,
        *,
        memory_budget_mb: int = DEFAULT_AGENT_MEMORY_MB,
        ports: tuple[int, ...] = DEFAULT_PORTS,
        capture_factory: Callable[..., RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
    ) -> None:
        self.service = service
        self.registry = registry
        self.ports = tuple(dict.fromkeys(int(port) for port in ports))
        if not self.ports or any(not 1 <= port <= 65535 for port in self.ports):
            raise ValueError("Portas do Agent invalidas")
        self.capture_factory = capture_factory
        self.process_reader = process_reader
        self.memory_limits = agent_memory_limits(memory_budget_mb)
        self.live_events = self._new_event_stream()
        self.live_capture: RealtimeCapture | None = None
        self.session_id: str | None = None
        self.started_at_ns: int | None = None
        self.last_error = ""
        self._known_pids: tuple[int, ...] = ()
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def create_offline(
        cls,
        state_dir: Path,
        installation_id: str,
        *,
        version: str,
        memory_budget_mb: int = DEFAULT_AGENT_MEMORY_MB,
        local_api_port: int = 17621,
        capture_factory: Callable[..., RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
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
        capture_factory: Callable[..., RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
        **service_options: Any,
    ) -> "StandaloneWindowsAgentRuntime":
        limits = agent_memory_limits(memory_budget_mb)
        registry = AgentClientRegistry()
        service = WindowsAgentLocalService.create_online(
            Path(state_dir),
            installation_id,
            server_url,
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
        )

    @property
    def active(self) -> bool:
        return self.live_capture is not None

    def _new_event_stream(self) -> LiveEventStream:
        limits = self.memory_limits
        return LiveEventStream(
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
            capture_ports.extend(int(port) for port in local_ports)
            capture_ports.extend(int(port) for port in remote_ports)
        return tuple(sorted(pids)), tuple(dict.fromkeys(capture_ports))

    def start_local_api(self) -> int:
        port = self.service.start_local_api()
        self.service.start_delivery()
        return port

    def start_capture(self) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                raise RuntimeError("Agent ja encerrado")
            if self.active:
                return self.health()
            processes = self.detected_processes()
            pids, capture_ports = self._capture_routes(processes, self.ports)
            if not pids:
                raise RuntimeError("Abra um cliente PC e entre no jogo")
            session_id = f"agent-{time.time_ns()}-{uuid.uuid4().hex[:12]}"
            self.last_error = ""
            self.live_events.clear()
            self.live_events.start()
            self.service.start_session(session_id)
            live = self.capture_factory(None, capture_ports)
            if hasattr(live, "set_packet_sink"):
                live.set_packet_sink(self.live_events.feed)
            try:
                live.start()
            except Exception as error:
                self.live_events.stop()
                self.service.finish_session(session_id, reason="capture_start_failed")
                self.service.runtime.bridge.wait_until_idle()
                self.last_error = f"{type(error).__name__}: {error}"[:240]
                raise
            self.live_capture = live
            self.session_id = session_id
            self.started_at_ns = time.time_ns()
            self._known_pids = pids
            return self.health()

    def refresh_routes(self) -> dict[str, Any]:
        with self._lock:
            processes = self.detected_processes()
            pids, capture_ports = self._capture_routes(processes, self.ports)
            if self.live_capture and capture_ports:
                self.live_capture.add_ports(capture_ports)
            self._known_pids = pids
            return {
                "client_processes": len(pids),
                "client_pids": list(pids),
                "no_clients": not pids,
            }

    def stop_capture(self, *, reason: str = "paused") -> dict[str, Any]:
        with self._lock:
            live, self.live_capture = self.live_capture, None
            session_id, self.session_id = self.session_id, None
            failures = []
            if live is not None:
                try:
                    live.stop()
                except Exception as error:
                    failures.append(f"capture: {type(error).__name__}")
            self.live_events.stop()
            self.service.runtime.bridge.wait_until_idle()
            if session_id:
                try:
                    if reason == "paused":
                        self.service.pause_session(session_id, reason=reason)
                    else:
                        self.service.finish_session(session_id, reason=reason)
                    self.service.runtime.bridge.wait_until_idle()
                except Exception as error:
                    failures.append(f"session: {type(error).__name__}")
            self.started_at_ns = None
            self._known_pids = ()
            if failures:
                self.last_error = "; ".join(failures)
            return {"active": False, "failures": failures}

    def configure_memory_budget(self, value: object) -> bool:
        limits = agent_memory_limits(value)
        with self._lock:
            if self.active:
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
            stream = self.live_events.metrics()
            uptime_seconds = (
                max(0.0, (time.time_ns() - self.started_at_ns) / 1_000_000_000)
                if self.started_at_ns else 0.0
            )
            capture_metrics = {
                name: int(getattr(capture, name, 0) or 0)
                for name in (
                    "received_packets", "filtered_packets", "duplicate_packets",
                    "missed_write", "missed_read", "sink_errors",
                )
            }
            return {
                "state": "capturing" if capture else "idle",
                "active": capture is not None,
                "client_processes": len(self._known_pids),
                "clients": self.registry.snapshot(),
                "uptime_seconds": round(uptime_seconds, 3),
                "memory_budget_mb": self.memory_limits["budget_mb"],
                "capture": capture_metrics,
                "decoder": stream,
                "local_api": service_health.get("local_api", {}),
                "outbox": service_health.get("outbox", {}),
                "server": {
                    "mode": service_health.get("mode", "offline"),
                    "state": service_health.get("state", "offline_shadow"),
                    "delivery": service_health.get("delivery", {}),
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
