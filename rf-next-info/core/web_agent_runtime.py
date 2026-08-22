"""Composicao opt-in do Agent Windows, sem ativacao implicita."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.web_agent import (
    DEFAULT_OUTBOX_BYTES,
    DEFAULT_OUTBOX_EVENTS,
    AgentOutbox,
    WebAgentBridge,
    WebEventProjector,
)
from core.web_agent_identity import AgentIdentity, AgentIdentityStore
from core.web_agent_transport import AgentBatchTransport, AgentDeliveryWorker


class WebAgentRuntime:
    """Une identidade, projecao, outbox e entrega somente quando habilitado."""

    def __init__(
        self,
        identity: AgentIdentity,
        bridge: WebAgentBridge,
        delivery: AgentDeliveryWorker,
    ) -> None:
        self.identity = identity
        self.bridge = bridge
        self.delivery = delivery
        self._session_active = False
        self._closed = False

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
        projector = WebEventProjector(
            identity.installation_id,
            identity.pseudonym_key,
            decoder_version=decoder_version or version,
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
        return cls(identity, bridge, delivery)

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.delivery.start()
        self.bridge.start_session(session_id, resumed=resumed)
        self._session_active = True

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
        state = (
            "storage_full" if outbox["full"] else
            "registration_required" if delivery["state"] == "blocked" else
            "delayed" if delivery["state"] == "backoff" else
            "online" if delivery["last_ack_at"] else
            "ready"
        )
        return {
            "enabled": True,
            "state": state,
            "session_active": self._session_active,
            "installation_id": self.identity.installation_id,
            "key_id": self.identity.key_id,
            "capture_bridge": bridge,
            "delivery": delivery,
            "outbox": outbox,
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
        projector = WebEventProjector(
            identity.installation_id,
            identity.pseudonym_key,
            decoder_version=decoder_version or version,
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

    def health(self) -> dict[str, object]:
        if self._closed:
            return {
                "enabled": True,
                "mode": "offline",
                "state": "closed",
                "session_active": False,
            }
        outbox = self.bridge.outbox.metrics()
        return {
            "enabled": True,
            "mode": "offline",
            "state": "storage_full" if outbox["full"] else "offline_shadow",
            "session_active": self._session_active,
            "installation_id": self.identity.installation_id,
            "key_id": self.identity.key_id,
            "capture_bridge": self.bridge.metrics(),
            "outbox": outbox,
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
