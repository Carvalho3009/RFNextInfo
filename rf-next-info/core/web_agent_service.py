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
from core.web_agent_boss_api import AgentBossEncounterState
from core.web_agent_runtime import WebAgentOfflineRuntime, WebAgentRuntime


class WindowsAgentLocalService:
    """Une runtime, feed e API loopback sem adicionar funções do Desktop."""

    def __init__(
        self,
        runtime: WebAgentOfflineRuntime | WebAgentRuntime,
        feed: AgentMonitorFeed,
        boss_encounters: AgentBossEncounterState,
        api: AgentLocalMonitorApi,
        token: str,
    ) -> None:
        self.runtime = runtime
        self.feed = feed
        self.boss_encounters = boss_encounters
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
        boss_encounters = AgentBossEncounterState()
        def observe(event: dict) -> None:
            if feed.add(event):
                boss_encounters.observe(event)
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
                boss_provider=boss_encounters.snapshot,
                port=local_api_port,
            )
        except Exception:
            runtime.close()
            raise
        return cls(runtime, feed, boss_encounters, api, token)

    @classmethod
    def create_online(
        cls,
        state_dir: Path,
        installation_id: str,
        server_url: str,
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
        boss_encounters = AgentBossEncounterState()
        runtime_holder: list[WebAgentRuntime] = []

        def observe(event: dict) -> None:
            if feed.add(event):
                boss_encounters.observe(event)
                if runtime_holder:
                    for encounter in boss_encounters.upload_candidates():
                        runtime_holder[0].submit_boss_encounter(encounter)
                        boss_encounters.mark_uploaded(encounter)
            if event_observer is not None:
                event_observer(event)

        runtime = WebAgentRuntime.create(
            state_dir,
            installation_id,
            server_url,
            version=version,
            event_observer=observe,
            **runtime_options,
        )
        runtime_holder.append(runtime)
        try:
            token = AgentLocalApiTokenStore(
                state_dir / "local-monitor-api.dat"
            ).load_or_create()
            api = AgentLocalMonitorApi(
                feed,
                token,
                health_provider=runtime.health,
                boss_provider=boss_encounters.snapshot,
                port=local_api_port,
            )
        except Exception:
            runtime.close()
            raise
        return cls(runtime, feed, boss_encounters, api, token)

    def start_local_api(self) -> int:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        return self.api.start()

    def start_delivery(self) -> None:
        if self._closed:
            raise RuntimeError("Agent ja encerrado")
        self.runtime.start_delivery()

    def refresh_authorization(self, *, force: bool = False) -> bool:
        return self.runtime.refresh_authorization(force=force)

    def require_capture_authorization(self) -> None:
        self.runtime.require_capture_authorization()

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

    def submit_subsession(self, session_id: str, report: dict) -> bool:
        return self.runtime.submit_subsession(session_id, report)

    def sync_subsession_commands(
        self, results: list[dict[str, object]],
        progress: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        return self.runtime.sync_subsession_commands(results, progress)

    def sync_character_profiles(self) -> int:
        return self.runtime.sync_character_profiles()

    def heartbeat(self, capture_state: str, client_count: int) -> bool:
        return self.runtime.heartbeat(capture_state, client_count)

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
            "boss_encounters": self.boss_encounters.snapshot()["encounter_count"],
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
