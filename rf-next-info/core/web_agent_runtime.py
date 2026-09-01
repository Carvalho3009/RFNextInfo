"""Composicao opt-in do Agent Windows, sem ativacao implicita."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from core.web_agent import (
    DEFAULT_OUTBOX_BYTES,
    DEFAULT_OUTBOX_EVENTS,
    AgentOutbox,
    LOCAL_ONLY_EVENT_TYPES,
    WebAgentBridge,
    WebEventProjector,
)
from core.web_agent_identity import AgentIdentity, AgentIdentityStore
from core.web_agent_authorization import AgentAuthorizationManager, AgentAuthorizationStore
from core.web_agent_character_history import AgentCharacterHistory
from core.web_agent_transport import AgentBatchTransport, AgentDeliveryWorker


class WebAgentRuntime:
    """Une identidade, projecao, outbox e entrega somente quando habilitado."""

    def __init__(
        self,
        identity: AgentIdentity,
        bridge: WebAgentBridge,
        delivery: AgentDeliveryWorker,
        authorization: AgentAuthorizationManager,
    ) -> None:
        self.identity = identity
        self.bridge = bridge
        self.delivery = delivery
        self.authorization = authorization
        self._session_active = False
        self._closed = False
        self._heartbeat_lock = threading.Lock()
        self._last_heartbeat_signature: tuple[int, str, int] | None = None

    @classmethod
    def create(
        cls,
        state_dir: Path,
        installation_id: str,
        server_url: str,
        *,
        version: str,
        decoder_version: str | None = None,
        max_outbox_bytes: int = DEFAULT_OUTBOX_BYTES,
        max_outbox_events: int = DEFAULT_OUTBOX_EVENTS,
        max_queue_events: int = 2048,
        transport_sender=None,
        event_observer: Callable[[dict], object] | None = None,
    ) -> "WebAgentRuntime":
        state_dir = Path(state_dir)
        identity = AgentIdentityStore(state_dir).load_or_create(installation_id)
        outbox = AgentOutbox(
            state_dir / "web-agent-outbox.sqlite3",
            identity.installation_id,
            max_bytes=max_outbox_bytes,
            max_events=max_outbox_events,
        )
        outbox.quarantine_event_types(
            LOCAL_ONLY_EVENT_TYPES, reason="local_only_policy"
        )
        projector = WebEventProjector(
            identity.installation_id,
            identity.pseudonym_key,
            decoder_version=decoder_version or version,
            character_history=AgentCharacterHistory(
                state_dir / "agent-character-history.dat",
                identity.installation_id,
                identity.pseudonym_key,
            ),
        )
        bridge = WebAgentBridge(
            projector,
            outbox,
            max_queue_events=max_queue_events,
            event_observer=event_observer,
        )
        transport_options = {}
        if transport_sender is not None:
            transport_options["sender"] = transport_sender
        transport = AgentBatchTransport(
            server_url, identity, version=version, **transport_options
        )
        delivery = AgentDeliveryWorker(outbox, transport)
        bridge.set_delivery_notifier(delivery.notify)
        authorization = AgentAuthorizationManager(
            transport,
            AgentAuthorizationStore(state_dir, identity.installation_id),
        )
        return cls(identity, bridge, delivery, authorization)

    def refresh_authorization(self, *, force: bool = False) -> bool:
        return self.authorization.refresh(force=force)

    def require_capture_authorization(self) -> None:
        self.authorization.require_capture()

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.start_delivery()
        self.bridge.start_session(session_id, resumed=resumed)
        self._session_active = True

    def start_delivery(self) -> None:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.delivery.start()

    def pause_session(self, session_id: str, *, reason: str = "paused") -> None:
        if self._closed:
            return
        self.bridge.pause_session(session_id, reason=reason)
        self.delivery.notify()
        self._session_active = False

    def finish_session(self, session_id: str, *, reason: str = "finished") -> None:
        if self._closed:
            return
        self.bridge.finish_session(session_id, reason=reason)
        self.delivery.notify()
        self._session_active = False

    def submit(self, event: dict) -> bool:
        if self._closed:
            return False
        # O flush periodico agrupa eventos por ate um segundo e evita um request
        # por pacote; a fila da captura continua sendo nao bloqueante.
        return self.bridge.submit(event)

    def submit_subsession(self, session_id: str, report: dict) -> bool:
        if self._closed:
            return False
        queued = self.bridge.submit_subsession(session_id, report)
        self.delivery.notify()
        return queued

    def submit_boss_encounter(self, encounter: dict) -> bool:
        if self._closed:
            return False
        event = self.bridge.projector.project_boss_encounter(encounter)
        queued = self.bridge.outbox.enqueue(event)
        self.bridge.record_direct_enqueue(event["type"], queued)
        self.delivery.notify()
        return queued

    def sync_subsession_commands(
        self, results: list[dict[str, object]],
        progress: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        if self._closed:
            return []
        return self.delivery.transport.sync_subsession_commands(results, progress)

    def sync_character_profiles(self) -> int:
        if self._closed:
            return 0
        profiles = self.delivery.transport.sync_character_profiles()
        return self.bridge.projector.merge_remote_character_profiles(profiles)

    def heartbeat(self, capture_state: str, client_count: int) -> bool:
        if self._closed:
            return False
        now_ns = time.time_ns()
        signature = (
            now_ns // 60_000_000_000,
            str(capture_state),
            int(client_count),
        )
        with self._heartbeat_lock:
            if signature == self._last_heartbeat_signature:
                return False
            event = self.bridge.projector.project_heartbeat(
                capture_state=capture_state,
                outbox_pending=int(self.bridge.outbox.metrics()["events"]),
                client_count=client_count,
                occurred_ns=now_ns,
            )
            queued = self.bridge.outbox.enqueue(event)
            self.bridge.record_direct_enqueue(event["type"], queued)
            self._last_heartbeat_signature = signature
        return queued

    def registration(self) -> dict[str, str]:
        return self.identity.registration()

    def health(self) -> dict[str, object]:
        if self._closed:
            return {
                "enabled": True,
                "state": "closed",
                "session_active": False,
            }
        bridge = self.bridge.metrics()
        delivery = self.delivery.metrics()
        outbox = self.bridge.outbox.metrics()
        enqueued_last_minute = int(
            bridge.get("enqueued_events_last_minute") or 0
        )
        sent_last_minute = int(delivery.get("sent_events_last_minute") or 0)
        state = (
            "storage_full" if outbox["full"] else
            "registration_pending" if delivery["state"] == "registration_pending" else
            "registration_required" if delivery["state"] == "blocked" else
            "delayed" if delivery["state"] == "backoff" else
            "online" if delivery["last_ack_at"] else
            "ready"
        )
        return {
            "enabled": True,
            "mode": "online",
            "state": state,
            "session_active": self._session_active,
            "installation_id": self.identity.installation_id,
            "key_id": self.identity.key_id,
            "capture_bridge": bridge,
            "delivery": delivery,
            "outbox": outbox,
            "throughput": {
                "enqueued_events_last_minute": enqueued_last_minute,
                "sent_events_last_minute": sent_last_minute,
                "outbox_growth_events_last_minute": (
                    enqueued_last_minute - sent_last_minute
                ),
            },
            "authorization": self.authorization.health(),
        }

    def close(self) -> None:
        if self._closed:
            return
        self.bridge.wait_until_idle()
        self.delivery.notify()
        if not self.delivery.stop():
            raise RuntimeError("Entrega do Agent ainda esta encerrando")
        self.bridge.close()
        self._session_active = False
        self._closed = True


class WebAgentOfflineRuntime:
    """Agent em shadow local: projeta e persiste, mas nao cria transporte."""

    def __init__(self, identity: AgentIdentity, bridge: WebAgentBridge) -> None:
        self.identity = identity
        self.bridge = bridge
        self._session_active = False
        self._closed = False
        self._heartbeat_lock = threading.Lock()
        self._last_heartbeat_signature: tuple[int, str, int] | None = None

    @classmethod
    def create(
        cls,
        state_dir: Path,
        installation_id: str,
        *,
        version: str,
        decoder_version: str | None = None,
        max_outbox_bytes: int = DEFAULT_OUTBOX_BYTES,
        max_outbox_events: int = DEFAULT_OUTBOX_EVENTS,
        max_queue_events: int = 2048,
        event_observer: Callable[[dict], object] | None = None,
    ) -> "WebAgentOfflineRuntime":
        state_dir = Path(state_dir)
        identity = AgentIdentityStore(state_dir).load_or_create(installation_id)
        outbox = AgentOutbox(
            state_dir / "web-agent-outbox.sqlite3",
            identity.installation_id,
            max_bytes=max_outbox_bytes,
            max_events=max_outbox_events,
        )
        outbox.quarantine_event_types(
            LOCAL_ONLY_EVENT_TYPES, reason="local_only_policy"
        )
        projector = WebEventProjector(
            identity.installation_id,
            identity.pseudonym_key,
            decoder_version=decoder_version or version,
            character_history=AgentCharacterHistory(
                state_dir / "agent-character-history.dat",
                identity.installation_id,
                identity.pseudonym_key,
            ),
        )
        bridge = WebAgentBridge(
            projector,
            outbox,
            max_queue_events=max_queue_events,
            event_observer=event_observer,
        )
        return cls(identity, bridge)

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.bridge.start_session(session_id, resumed=resumed)
        self._session_active = True

    def refresh_authorization(self, *, force: bool = False) -> bool:
        return True

    def require_capture_authorization(self) -> None:
        return None

    def start_delivery(self) -> None:
        """Mantém uma interface comum sem criar rede no modo offline."""
        if self._closed:
            raise RuntimeError("Agent ja encerrado")

    def pause_session(self, session_id: str, *, reason: str = "paused") -> None:
        if self._closed:
            return
        self.bridge.pause_session(session_id, reason=reason)
        self._session_active = False

    def finish_session(self, session_id: str, *, reason: str = "finished") -> None:
        if self._closed:
            return
        self.bridge.finish_session(session_id, reason=reason)
        self._session_active = False

    def submit(self, event: dict) -> bool:
        return False if self._closed else self.bridge.submit(event)

    def submit_subsession(self, session_id: str, report: dict) -> bool:
        return False if self._closed else self.bridge.submit_subsession(
            session_id, report
        )

    def submit_boss_encounter(self, encounter: dict) -> bool:
        return False

    def sync_subsession_commands(
        self, results: list[dict[str, object]],
        progress: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        return []

    def sync_character_profiles(self) -> int:
        return 0

    def heartbeat(self, capture_state: str, client_count: int) -> bool:
        if self._closed:
            return False
        now_ns = time.time_ns()
        signature = (
            now_ns // 60_000_000_000,
            str(capture_state),
            int(client_count),
        )
        with self._heartbeat_lock:
            if signature == self._last_heartbeat_signature:
                return False
            event = self.bridge.projector.project_heartbeat(
                capture_state=capture_state,
                outbox_pending=int(self.bridge.outbox.metrics()["events"]),
                client_count=client_count,
                occurred_ns=now_ns,
            )
            queued = self.bridge.outbox.enqueue(event)
            self.bridge.record_direct_enqueue(event["type"], queued)
            self._last_heartbeat_signature = signature
            return queued

    def health(self) -> dict[str, object]:
        if self._closed:
            return {
                "enabled": True,
                "mode": "offline",
                "state": "closed",
                "session_active": False,
            }
        outbox = self.bridge.outbox.metrics()
        bridge = self.bridge.metrics()
        enqueued_last_minute = int(
            bridge.get("enqueued_events_last_minute") or 0
        )
        return {
            "enabled": True,
            "mode": "offline",
            "state": "storage_full" if outbox["full"] else "offline_shadow",
            "session_active": self._session_active,
            "installation_id": self.identity.installation_id,
            "key_id": self.identity.key_id,
            "capture_bridge": bridge,
            "outbox": outbox,
            "throughput": {
                "enqueued_events_last_minute": enqueued_last_minute,
                "sent_events_last_minute": 0,
                "outbox_growth_events_last_minute": enqueued_last_minute,
            },
            "authorization": {
                "required": False,
                "authorized": True,
                "status": "offline",
            },
        }

    def close(self) -> None:
        if self._closed:
            return
        self.bridge.close()
        self._session_active = False
        self._closed = True


def create_web_agent_if_enabled(
    enabled: bool,
    state_dir: Path,
    installation_id: str,
    server_url: str,
    *,
    version: str,
    **options,
) -> WebAgentRuntime | None:
    """O caminho desabilitado nao cria chaves, pastas, banco ou threads."""
    if not enabled:
        return None
    return WebAgentRuntime.create(
        state_dir,
        installation_id,
        server_url,
        version=version,
        **options,
    )


def create_offline_web_agent_if_enabled(
    enabled: bool,
    state_dir: Path,
    installation_id: str,
    *,
    version: str,
    **options,
) -> WebAgentOfflineRuntime | None:
    """Ativa o shadow local sem URL, sender, thread de entrega ou rede."""
    if not enabled:
        return None
    return WebAgentOfflineRuntime.create(
        state_dir,
        installation_id,
        version=version,
        **options,
    )
