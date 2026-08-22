"""API loopback do Agent para consumidores locais de Boss e PvP."""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from app.protected_state import protect_for_current_user, unprotect


LOCAL_MONITOR_SCHEMA = "rf-qol.local-monitor-events/v1"
LOCAL_CAPABILITIES_SCHEMA = "rf-qol.local-monitor-capabilities/v1"
LOCAL_HEALTH_SCHEMA = "rf-qol.local-agent-health/v1"
LOCAL_API_DEFAULT_PORT = 17621
LOCAL_API_MAX_RESPONSE_BYTES = 256 * 1024
LOCAL_API_MAX_CONCURRENT_REQUESTS = 4
LOCAL_API_MAX_REQUESTS_PER_SECOND = 20
LOCAL_API_MAX_EVENTS = 250
LOCAL_API_MAX_WAIT_MS = 1000
LOCAL_API_DEFAULT_FEED_BYTES = 16 * 1024 * 1024
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}")

_COMMON_TYPES = {
    "character.observed",
    "session.lifecycle",
}
_COMBAT_TYPES = {
    "combat.entity_died",
    "combat.resources_changed",
    "combat.skill_resolved",
    "combat.normal_attack_resolved",
    "world.entities_disappeared",
}
_PVP_TYPES = _COMMON_TYPES | _COMBAT_TYPES | {
    "world.players_appeared",
}
_BOSS_TYPES = _COMMON_TYPES | _COMBAT_TYPES | {
    "boss.position_observed",
    "boss.result_observed",
    "world.monsters_appeared",
}
MONITOR_DOMAINS = frozenset({"pvp", "boss"})
MONITOR_EVENT_TYPES = {
    "pvp": tuple(sorted(_PVP_TYPES)),
    "boss": tuple(sorted(_BOSS_TYPES)),
}


def _integer(
    value: object, *, minimum: int, maximum: int, default: int
) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if minimum <= number <= maximum else default


def _event_domains(event_type: object) -> tuple[str, ...]:
    value = str(event_type or "")
    domains = []
    if value in _PVP_TYPES:
        domains.append("pvp")
    if value in _BOSS_TYPES:
        domains.append("boss")
    return tuple(domains)


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    """Remove metadados de entrega que o consumidor local nao precisa."""
    return {
        "event_id": str(event.get("event_id") or "")[:128],
        "session_ref": str(event.get("session_ref") or "")[:64],
        "stream_id": str(event.get("stream_id") or "")[:64],
        "occurred_at": str(event.get("occurred_at") or "")[:64],
        "client_ref": (
            str(event.get("client_ref"))[:64]
            if event.get("client_ref") is not None else None
        ),
        "type": str(event.get("type") or "")[:96],
        "payload": json.loads(json.dumps(
            event.get("payload") if isinstance(event.get("payload"), dict) else {},
            ensure_ascii=False,
        )),
        "evidence": json.loads(json.dumps(
            event.get("evidence") if isinstance(event.get("evidence"), dict) else {},
            ensure_ascii=False,
        )),
    }


class AgentMonitorFeed:
    """Ring buffer independente da outbox remota, com cursor monotônico."""

    def __init__(
        self,
        max_events: int = 10_000,
        max_bytes: int = LOCAL_API_DEFAULT_FEED_BYTES,
    ) -> None:
        self.max_events = max(1, int(max_events))
        self.max_bytes = max(1024, int(max_bytes))
        self._events: deque[
            tuple[int, tuple[str, ...], dict[str, Any], int]
        ] = deque()
        self._event_ids: deque[str] = deque()
        self._known_ids: set[str] = set()
        self._bytes = 0
        self._cursor = 0
        self._condition = threading.Condition()
        self.accepted = 0
        self.ignored = 0
        self.duplicates = 0
        self.oversized = 0

    def add(self, event: dict[str, Any]) -> bool:
        domains = _event_domains(event.get("type"))
        if not domains:
            with self._condition:
                self.ignored += 1
            return False
        public = _public_event(event)
        event_id = public["event_id"]
        if not event_id:
            with self._condition:
                self.ignored += 1
            return False
        event_bytes = len(json.dumps(
            public, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"))
        if event_bytes > self.max_bytes:
            with self._condition:
                self.oversized += 1
            return False
        with self._condition:
            if event_id in self._known_ids:
                self.duplicates += 1
                return False
            self._cursor += 1
            self._events.append((self._cursor, domains, public, event_bytes))
            self._event_ids.append(event_id)
            self._known_ids.add(event_id)
            self._bytes += event_bytes
            while len(self._events) > self.max_events or self._bytes > self.max_bytes:
                _cursor, _domains, _event, expired_bytes = self._events.popleft()
                self._bytes = max(0, self._bytes - expired_bytes)
                expired_id = self._event_ids.popleft()
                self._known_ids.discard(expired_id)
            self.accepted += 1
            self._condition.notify_all()
            return True

    def read(
        self,
        *,
        after: int = 0,
        domains: set[str] | frozenset[str] = MONITOR_DOMAINS,
        limit: int = LOCAL_API_MAX_EVENTS,
        wait_seconds: float = 0.0,
    ) -> dict[str, Any]:
        requested = frozenset(str(value) for value in domains)
        if not requested or not requested.issubset(MONITOR_DOMAINS):
            raise ValueError("Dominio local invalido")
        after = max(0, int(after))
        limit = max(1, min(LOCAL_API_MAX_EVENTS, int(limit)))
        wait_seconds = max(0.0, min(LOCAL_API_MAX_WAIT_MS / 1000, wait_seconds))

        def available() -> bool:
            return any(
                cursor > after and requested.intersection(event_domains)
                for cursor, event_domains, _event, _event_bytes in self._events
            )

        with self._condition:
            if wait_seconds and not available():
                self._condition.wait_for(available, timeout=wait_seconds)
            oldest_cursor = self._events[0][0] if self._events else self._cursor + 1
            reset_required = bool(after and after < oldest_cursor - 1)
            rows = []
            next_cursor = after
            for cursor, event_domains, event, _event_bytes in self._events:
                if cursor <= after or not requested.intersection(event_domains):
                    continue
                rows.append({
                    "cursor": cursor,
                    "domains": list(event_domains),
                    **event,
                })
                next_cursor = cursor
                if len(rows) >= limit:
                    break
            return {
                "schema": LOCAL_MONITOR_SCHEMA,
                "domains": sorted(requested),
                "after": after,
                "next_cursor": next_cursor,
                "latest_cursor": self._cursor,
                "oldest_cursor": oldest_cursor,
                "reset_required": reset_required,
                "events": rows,
            }

    def metrics(self) -> dict[str, int]:
        with self._condition:
            return {
                "events": len(self._events),
                "event_limit": self.max_events,
                "bytes": self._bytes,
                "byte_limit": self.max_bytes,
                "latest_cursor": self._cursor,
                "accepted": self.accepted,
                "ignored": self.ignored,
                "duplicates": self.duplicates,
                "oversized": self.oversized,
            }


class AgentLocalApiTokenStore:
    """Token da API protegido para o usuário Windows atual."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load_or_create(self) -> str:
        try:
            payload = json.loads(unprotect(self.path.read_bytes()))
            token = str(payload.get("token") or "") if isinstance(payload, dict) else ""
            if payload.get("schema") == 1 and TOKEN_PATTERN.fullmatch(token):
                return token
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        token = secrets.token_urlsafe(32)
        encoded = protect_for_current_user(
            json.dumps(
                {"schema": 1, "token": token}, separators=(",", ":")
            ).encode(),
            description="RF QOL Agent API local",
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encoded)
        os.replace(temporary, self.path)
        return token

    def rotate(self) -> str:
        self.path.unlink(missing_ok=True)
        return self.load_or_create()


class _LoopbackServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 8


class AgentLocalMonitorApi:
    """HTTP read-only, sem CORS, comandos ou bind em rede local."""

    def __init__(
        self,
        feed: AgentMonitorFeed,
        token: str,
        *,
        health_provider: Callable[[], object] | None = None,
        host: str = "127.0.0.1",
        port: int = LOCAL_API_DEFAULT_PORT,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("A API do Agent so pode escutar em 127.0.0.1")
        if not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("Token local invalido")
        if not 0 <= int(port) <= 65535:
            raise ValueError("Porta local invalida")
        self.feed = feed
        self.token = token
        self.health_provider = health_provider or (lambda: {})
        self.host = host
        self.port = int(port)
        self.server: _LoopbackServer | None = None
        self.thread: threading.Thread | None = None
        self._request_slots = threading.BoundedSemaphore(
            LOCAL_API_MAX_CONCURRENT_REQUESTS
        )
        self._rate_lock = threading.Lock()
        self._request_times: deque[float] = deque()

    @property
    def active(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def _admit_request(self) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            while self._request_times and self._request_times[0] <= now - 1:
                self._request_times.popleft()
            if len(self._request_times) >= LOCAL_API_MAX_REQUESTS_PER_SECOND:
                return False
            self._request_times.append(now)
            return True

    def _health(self) -> dict[str, Any]:
        source = self.health_provider()
        source = source if isinstance(source, dict) else {}
        outbox = source.get("outbox") if isinstance(source.get("outbox"), dict) else {}
        bridge = (
            source.get("capture_bridge")
            if isinstance(source.get("capture_bridge"), dict) else {}
        )
        return {
            "schema": LOCAL_HEALTH_SCHEMA,
            "ok": True,
            "mode": "local",
            "capture_state": str(source.get("state") or "unknown")[:32],
            "session_active": source.get("session_active") is True,
            "feed": self.feed.metrics(),
            "outbox": {
                "events": _integer(
                    outbox.get("events"), minimum=0, maximum=2**63 - 1, default=0
                ),
                "bytes": _integer(
                    outbox.get("bytes"), minimum=0, maximum=2**63 - 1, default=0
                ),
                "full": outbox.get("full") is True,
            },
            "capture_bridge": {
                key: _integer(
                    bridge.get(key), minimum=0, maximum=2**63 - 1, default=0
                )
                for key in (
                    "queue_depth", "queue_limit", "accepted", "ignored",
                    "dropped", "errors", "observer_errors",
                )
            },
        }

    def start(self) -> int:
        if self.active and self.server:
            return int(self.server.server_port)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, _format: str, *_args: object) -> None:
                return

            def _send(self, status: int, payload: object) -> None:
                encoded = json.dumps(
                    payload, ensure_ascii=False, separators=(",", ":")
                ).encode()
                if len(encoded) > LOCAL_API_MAX_RESPONSE_BYTES:
                    status = 503
                    encoded = b'{"error":"Resposta local excedeu o limite seguro."}'
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(encoded)

            def do_GET(self) -> None:
                if not owner._request_slots.acquire(blocking=False):
                    self._send(429, {"error": "Muitas conexoes locais."})
                    return
                try:
                    if not owner._admit_request():
                        self._send(429, {"error": "Limite local atingido."})
                        return
                    supplied = self.headers.get("Authorization") or ""
                    if not hmac.compare_digest(supplied, f"Bearer {owner.token}"):
                        self._send(401, {"error": "Token local invalido."})
                        return
                    parsed = urlsplit(self.path)
                    if parsed.path == "/api/agent/v1/health":
                        self._send(200, owner._health())
                        return
                    if parsed.path == "/api/agent/v1/capabilities":
                        self._send(200, {
                            "schema": LOCAL_CAPABILITIES_SCHEMA,
                            "domains": sorted(MONITOR_DOMAINS),
                            "event_types": MONITOR_EVENT_TYPES,
                            "delivery": "long-poll",
                            "max_events": LOCAL_API_MAX_EVENTS,
                            "max_wait_ms": LOCAL_API_MAX_WAIT_MS,
                            "read_only": True,
                        })
                        return
                    if parsed.path == "/api/agent/v1/monitor/events":
                        query = parse_qs(parsed.query, keep_blank_values=True)
                        unknown = set(query) - {"after", "domains", "limit", "wait_ms"}
                        if unknown:
                            self._send(400, {"error": "Parametro local invalido."})
                            return
                        raw_domains = ",".join(query.get("domains") or ["pvp,boss"])
                        domains = {
                            value.strip() for value in raw_domains.split(",")
                            if value.strip()
                        }
                        if not domains or not domains.issubset(MONITOR_DOMAINS):
                            self._send(400, {"error": "Dominio local invalido."})
                            return
                        after = _integer(
                            (query.get("after") or [0])[0],
                            minimum=0, maximum=2**63 - 1, default=0,
                        )
                        limit = _integer(
                            (query.get("limit") or [LOCAL_API_MAX_EVENTS])[0],
                            minimum=1, maximum=LOCAL_API_MAX_EVENTS,
                            default=LOCAL_API_MAX_EVENTS,
                        )
                        wait_ms = _integer(
                            (query.get("wait_ms") or [0])[0],
                            minimum=0, maximum=LOCAL_API_MAX_WAIT_MS, default=0,
                        )
                        self._send(200, owner.feed.read(
                            after=after,
                            domains=domains,
                            limit=limit,
                            wait_seconds=wait_ms / 1000,
                        ))
                        return
                    self._send(404, {"error": "Rota local nao encontrada."})
                except Exception:
                    self._send(503, {"error": "API local indisponivel."})
                finally:
                    owner._request_slots.release()

        self.server = _LoopbackServer((self.host, self.port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="rfqol-agent-local-api",
            daemon=True,
        )
        self.thread.start()
        return int(self.server.server_port)

    def stop(self) -> None:
        server, self.server = self.server, None
        thread, self.thread = self.thread, None
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2)
