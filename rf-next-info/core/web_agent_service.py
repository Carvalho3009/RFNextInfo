"""Composição do Agent Windows com API local opcional para monitores externos."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from core.web_agent_local_api import (
    LOCAL_API_DEFAULT_FEED_BYTES,
    LOCAL_API_DEFAULT_PORT,
    AgentLocalApiTokenStore,
    AgentLocalMonitorApi,
    AgentMonitorFeed,
)
from core.web_agent_runtime import WebAgentOfflineRuntime


class WindowsAgentLocalService:
    """Une runtime, feed e API loopback sem adicionar funções do Desktop."""

    def __init__(
        self,
        runtime: WebAgentOfflineRuntime,
        feed: AgentMonitorFeed,
        api: AgentLocalMonitorApi,
        token: str,
    ) -> None:
        self.runtime = runtime
        self.feed = feed
        self.api = api
        self._token = token
        self._session_id: str | None = None
        self._closed = False

    @classmethod
    def create_offline(
        cls,
        state_dir: Path,
        installation_id: str,
        *,
        version: str,
        local_api_port: int = LOCAL_API_DEFAULT_PORT,
        max_monitor_events: int = 10_000,
        max_monitor_bytes: int = LOCAL_API_DEFAULT_FEED_BYTES,
        event_observer: Callable[[dict], object] | None = None,
        **runtime_options,
    ) -> "WindowsAgentLocalService":
        state_dir = Path(state_dir)
        feed = AgentMonitorFeed(
            max_events=max_monitor_events,
            max_bytes=max_monitor_bytes,
        )
        def observe(event: dict) -> None:
            feed.add(event)
            if event_observer is not None:
                event_observer(event)

        runtime = WebAgentOfflineRuntime.create(
            state_dir,
            installation_id,
            version=version,
            event_observer=observe,
            **runtime_options,
        )
        try:
            token = AgentLocalApiTokenStore(
                state_dir / "local-monitor-api.dat"
            ).load_or_create()
            api = AgentLocalMonitorApi(
                feed,
                token,
                health_provider=runtime.health,
                port=local_api_port,
            )
        except Exception:
            runtime.close()
            raise
        return cls(runtime, feed, api, token)

    def start_local_api(self) -> int:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        return self.api.start()

    def pairing_credentials(self) -> dict[str, object]:
        """Credencial explícita para o usuário copiar ao programa autorizado."""
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        port = (
            int(self.api.server.server_port)
            if self.api.server is not None else self.api.port
        )
        return {
            "base_url": f"http://127.0.0.1:{port}",
            "token": self._token,
            "authorization": "Bearer",
            "domains": ["boss", "pvp"],
        }

    def start_session(self, session_id: str, *, resumed: bool = False) -> None:
        self.runtime.start_session(session_id, resumed=resumed)
        self._session_id = str(session_id)

    def pause_session(self, session_id: str, *, reason: str = "paused") -> None:
        self.runtime.pause_session(session_id, reason=reason)
        if self._session_id == str(session_id):
            self._session_id = None

    def finish_session(self, session_id: str, *, reason: str = "finished") -> None:
        self.runtime.finish_session(session_id, reason=reason)
        if self._session_id == str(session_id):
            self._session_id = None

    def submit(self, event: dict) -> bool:
        return self.runtime.submit(event)

    def health(self) -> dict[str, object]:
        health = dict(self.runtime.health())
        health["local_api"] = {
            "active": self.api.active,
            "host": "127.0.0.1",
            "port": (
                int(self.api.server.server_port)
                if self.api.server is not None else self.api.port
            ),
            "domains": ["boss", "pvp"],
            "feed": self.feed.metrics(),
        }
        return health

    def close(self) -> None:
        if self._closed:
            return
        self.api.stop()
        if self._session_id:
            self.runtime.finish_session(self._session_id, reason="abandoned")
            self._session_id = None
        self.runtime.close()
        self._token = ""
        self._closed = True
