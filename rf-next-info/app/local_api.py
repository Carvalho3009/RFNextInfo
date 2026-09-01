"""API de saída local, autenticada e somente leitura."""

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

from app.protected_state import protect, unprotect


LOCAL_API_SCHEMA_VERSION = 1
LOCAL_API_MAX_RESPONSE_BYTES = 256 * 1024
LOCAL_API_DEFAULT_PORT = 17620
LOCAL_API_MAX_CONCURRENT_REQUESTS = 4
LOCAL_API_MAX_REQUESTS_PER_SECOND = 20
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{32,128}")


def _number(value: object, *, minimum: float, maximum: float) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if minimum <= number <= maximum else None


def _integer(value: object, *, minimum: int, maximum: int) -> int | None:
    if not isinstance(value, (int, float)):
        return None
    number = int(value)
    return number if minimum <= number <= maximum else None


def _position(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    result = {
        axis: _number(value.get(axis), minimum=-1_000_000_000, maximum=1_000_000_000)
        for axis in ("x", "y", "z")
    }
    return result if all(item is not None for item in result.values()) else None


def sanitize_map_snapshot(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    clients = []
    for raw in source.get("clients") or []:
        if not isinstance(raw, dict):
            continue
        client_key = str(raw.get("client_key") or "")
        if not re.fullmatch(r"client:[a-g]", client_key):
            continue
        nearby = []
        nearby_source = raw.get("nearby_players")
        nearby_source = nearby_source if isinstance(nearby_source, list) else []
        for player in nearby_source[:500]:
            if not isinstance(player, dict):
                continue
            player_position = _position(player.get("position"))
            if player_position is None:
                continue
            nearby.append({
                "name": str(player.get("name") or "Não identificado").strip()[:80],
                "guild_name": str(player.get("guild_name") or "").strip()[:80],
                "position": player_position,
                "distance": _number(
                    player.get("distance"), minimum=0, maximum=1_000_000_000
                ),
                "observed_at_ns": _integer(
                    player.get("observed_at_ns"), minimum=0, maximum=2**63 - 1
                ),
                "age_seconds": _number(
                    player.get("age_seconds"), minimum=0, maximum=86_400
                ),
                "confidence": "confirmed",
            })
        map_index = _integer(raw.get("map_index"), minimum=0, maximum=2**32 - 1)
        teleporting = raw.get("teleporting")
        region_index = _integer(
            raw.get("region_index"), minimum=0, maximum=2**32 - 1
        )
        clients.append({
            "client_key": client_key,
            "map_enabled": raw.get("map_enabled") is True,
            "reason": str(raw.get("reason") or "unavailable")[:40],
            "character_name": str(raw.get("character_name") or "").strip()[:80],
            "map_index": map_index,
            "map_name": str(raw.get("map_name") or "").strip()[:80] or None,
            "map_source": (
                str(raw.get("map_source"))
                if raw.get("map_source") in {
                    "automatic", "manual_fallback", "unresolved"
                }
                else "unresolved"
            ),
            "position": _position(raw.get("position")),
            "region_index": region_index,
            "region_name": str(raw.get("region_name") or "").strip()[:160] or None,
            "region_center": _position(raw.get("region_center")),
            "region_confidence": (
                str(raw.get("region_confidence"))
                if raw.get("region_confidence") in {
                    "nearest-official-center", "map-index-floor", "manual-fallback"
                }
                else None
            ),
            "observed_at_ns": _integer(
                raw.get("observed_at_ns"), minimum=0, maximum=2**63 - 1
            ),
            "age_seconds": _number(
                raw.get("age_seconds"), minimum=0, maximum=86_400
            ),
            "stale": raw.get("stale") is True,
            "teleporting": teleporting if isinstance(teleporting, bool) else None,
            "confidence": (
                "confirmed" if raw.get("confidence") == "confirmed" else "unavailable"
            ),
            "nearby_players": nearby,
        })
    active_count = sum(1 for client in clients if client["map_enabled"])
    limited_count = sum(
        1 for client in clients if client["reason"] == "capacity_limit"
    )
    return {
        "schema_version": LOCAL_API_SCHEMA_VERSION,
        "map_catalog_version": str(source.get("catalog_version") or "")[:40] or None,
        "game_data_language": (
            "en" if source.get("language") == "en" else "pt"
        ),
        "available": source.get("available") is not False,
        "reason": str(source.get("reason") or "")[:40] or None,
        "capacity": 2,
        "active_count": min(2, active_count),
        "detected_count": len(clients),
        "limited_count": limited_count,
        "clients": clients[:7],
    }


def sanitize_status_snapshot(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    availability_values = {"available", "offline", "unknown"}
    activity_values = {"idle", "farm", "pvp", "boss", "unknown"}
    display_values = {"teleporting", "pvp", "farm", "idle"}
    clients = []
    for raw in source.get("clients") or []:
        if not isinstance(raw, dict):
            continue
        client_key = str(raw.get("client_key") or "")
        if not re.fullmatch(r"client:[a-g]", client_key):
            continue
        signals = raw.get("signals") if isinstance(raw.get("signals"), dict) else {}
        evidence = raw.get("evidence") if isinstance(raw.get("evidence"), dict) else {}
        availability = str(raw.get("availability") or "unknown")
        activity = str(raw.get("activity") or "unknown")
        display_status = str(raw.get("display_status") or "idle")
        clients.append({
            "client_key": client_key,
            "availability": availability if availability in availability_values else "unknown",
            "activity": activity if activity in activity_values else "unknown",
            "active_activities": [
                value for value in raw.get("active_activities") or []
                if value in activity_values and value != "unknown"
            ][:4],
            "display_status": (
                display_status if display_status in display_values else "idle"
            ),
            "signals": {
                key: signals.get(key) if isinstance(signals.get(key), bool) else None
                for key in (
                    "threat", "under_attack", "low_hp", "boss_nearby", "teleporting"
                )
            },
            "evidence": {
                key: _number(evidence.get(key), minimum=0, maximum=86_400)
                for key in (
                    "exp_gain_age_seconds", "pve_age_seconds",
                    "pvp_age_seconds", "map_age_seconds",
                )
            },
        })
    modes = source.get("enabled_modes") if isinstance(source.get("enabled_modes"), list) else []
    return {
        "schema_version": _integer(
            source.get("schema_version"), minimum=1, maximum=100
        ) or LOCAL_API_SCHEMA_VERSION,
        "generated_at_ns": _integer(
            source.get("generated_at_ns"), minimum=0, maximum=2**63 - 1
        ),
        "enabled_modes": [value for value in modes if value in {"pve", "pvp", "boss"}],
        "clients": clients[:7],
    }


def sanitize_health_snapshot(value: object) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    process = source.get("process") if isinstance(source.get("process"), dict) else {}
    capture = source.get("capture") if isinstance(source.get("capture"), dict) else {}
    checkpoint = (
        source.get("checkpoint")
        if isinstance(source.get("checkpoint"), dict) else {}
    )
    stream = source.get("stream") if isinstance(source.get("stream"), dict) else {}
    capture_state = str(capture.get("state") or "idle")
    checkpoint_reason = str(checkpoint.get("reason") or "")
    integer_metrics = (
        "queue_depth", "queue_limit", "queue_bytes", "queue_byte_limit",
        "processed_packets", "decoded_events", "dropped_events",
        "dropped_packets", "retained_events", "event_limit",
        "write_queue_depth", "write_queue_limit", "write_queue_bytes",
        "write_queue_byte_limit", "dropped_write_packets",
        "dropped_write_bytes",
    )
    return {
        "schema_version": LOCAL_API_SCHEMA_VERSION,
        "generated_at_ns": _integer(
            source.get("generated_at_ns"), minimum=0, maximum=2**63 - 1
        ),
        "process": {
            "version": str(process.get("version") or "").strip()[:32] or None,
            "memory_bytes": _integer(
                process.get("memory_bytes"), minimum=0, maximum=2**63 - 1
            ),
            "memory_budget_bytes": _integer(
                process.get("memory_budget_bytes"), minimum=0, maximum=2**63 - 1
            ),
            "memory_pressure": (
                process.get("memory_pressure")
                if isinstance(process.get("memory_pressure"), bool) else None
            ),
        },
        "capture": {
            "state": capture_state
            if capture_state in {"idle", "active", "paused", "pending"}
            else "idle",
            "session_available": capture.get("session_available") is True,
        },
        "checkpoint": {
            "available": checkpoint.get("available") is True,
            "reason": checkpoint_reason
            if checkpoint_reason in {"interval", "paused", "finalized"}
            else None,
            "age_seconds": _number(
                checkpoint.get("age_seconds"), minimum=0, maximum=31_536_000
            ),
        },
        "stream": {
            "available": stream.get("available") is True,
            "worker_alive": (
                stream.get("worker_alive")
                if isinstance(stream.get("worker_alive"), bool) else None
            ),
            "lag_seconds": _number(
                stream.get("lag_seconds"), minimum=0, maximum=86_400
            ),
            **{
                key: _integer(stream.get(key), minimum=0, maximum=2**63 - 1)
                for key in integer_metrics
            },
        },
    }


class LocalApiTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def load_or_create(self) -> str:
        try:
            payload = json.loads(unprotect(self.path.read_bytes()))
            if not isinstance(payload, dict):
                raise ValueError("Estado da API local inválido")
            token = str(payload.get("token") or "")
            if payload.get("schema_version") == 1 and TOKEN_PATTERN.fullmatch(token):
                return token
        except (OSError, ValueError, TypeError, AttributeError):
            pass
        token = secrets.token_urlsafe(32)
        encoded = protect(json.dumps({
            "schema_version": 1,
            "token": token,
        }, separators=(",", ":")).encode())
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


class LocalOutputApi:
    def __init__(
        self,
        map_provider: Callable[[], object],
        token: str,
        *,
        status_provider: Callable[[], object] | None = None,
        health_provider: Callable[[], object] | None = None,
        host: str = "127.0.0.1",
        port: int = LOCAL_API_DEFAULT_PORT,
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("A API local só pode escutar em 127.0.0.1")
        if not TOKEN_PATTERN.fullmatch(token):
            raise ValueError("Token da API local inválido")
        if not 0 <= int(port) <= 65535:
            raise ValueError("Porta da API local inválida")
        self.map_provider = map_provider
        self.status_provider = status_provider or (lambda: {})
        self.health_provider = health_provider or (lambda: {})
        self.token = token
        self.host = host
        self.port = int(port)
        self.server: _LoopbackServer | None = None
        self.thread: threading.Thread | None = None
        self._request_slots = threading.BoundedSemaphore(
            LOCAL_API_MAX_CONCURRENT_REQUESTS
        )
        self._rate_lock = threading.Lock()
        self._request_times: deque[float] = deque()

    def _admit_request(self) -> bool:
        now = time.monotonic()
        with self._rate_lock:
            while self._request_times and self._request_times[0] <= now - 1:
                self._request_times.popleft()
            if len(self._request_times) >= LOCAL_API_MAX_REQUESTS_PER_SECOND:
                return False
            self._request_times.append(now)
            return True

    @property
    def active(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

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
                    self._send(429, {"error": "Muitas conexões locais simultâneas."})
                    return
                try:
                    if not owner._admit_request():
                        self._send(429, {"error": "Limite da API local atingido."})
                        return
                    expected = f"Bearer {owner.token}"
                    supplied = self.headers.get("Authorization") or ""
                    if not hmac.compare_digest(supplied, expected):
                        self._send(401, {"error": "Token local inválido."})
                        return
                    if self.path == "/api/v1/health":
                        snapshot = sanitize_map_snapshot(owner.map_provider())
                        status_snapshot = sanitize_status_snapshot(
                            owner.status_provider()
                        )
                        health = sanitize_health_snapshot(owner.health_provider())
                        self._send(200, {
                            **health,
                            "ok": True,
                            "map_available": snapshot["available"],
                            "map_clients": snapshot["active_count"],
                            "status_clients": len(status_snapshot["clients"]),
                        })
                        return
                    if self.path == "/api/v1/map":
                        self._send(200, sanitize_map_snapshot(owner.map_provider()))
                        return
                    if self.path == "/api/v1/status":
                        self._send(
                            200, sanitize_status_snapshot(owner.status_provider())
                        )
                        return
                    self._send(404, {"error": "Rota local não encontrada."})
                except Exception:
                    self._send(503, {"error": "Snapshot local indisponível."})
                finally:
                    owner._request_slots.release()

        self.server = _LoopbackServer((self.host, self.port), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="rfqol-local-api",
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
