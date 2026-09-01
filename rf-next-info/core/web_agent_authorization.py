"""Autorizacao protegida do Agent vinculada ao usuario do site."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.protected_state import protect_for_current_user, unprotect
from core.web_agent_transport import (
    AgentBatchTransport,
    AgentTransportError,
    AuthorizationReceipt,
)


AUTHORIZATION_SCHEMA = "rf-qol.agent-authorization/v1"
MAX_OFFLINE_AUTHORIZATION = timedelta(hours=24)
DEFAULT_REFRESH_SECONDS = 30 * 60
PENDING_REFRESH_SECONDS = 5


def _utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Horario de autorizacao sem fuso")
    return parsed.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentAuthorizationStore:
    """Persiste a ultima autorizacao com a mesma protecao DPAPI da identidade."""

    def __init__(self, state_dir: Path, installation_id: str) -> None:
        self.path = Path(state_dir) / "agent-authorization.dat"
        self.installation_id = str(installation_id)

    def load(self) -> dict[str, str] | None:
        try:
            value = json.loads(unprotect(self.path.read_bytes()))
            required = {
                "schema", "installation_id", "username", "checked_at", "expires_at",
            }
            if not isinstance(value, dict) or set(value) != required:
                return None
            if (
                value["schema"] != AUTHORIZATION_SCHEMA
                or value["installation_id"] != self.installation_id
                or not isinstance(value["username"], str)
                or not 1 <= len(value["username"]) <= 80
            ):
                return None
            checked = _utc(value["checked_at"])
            expires = _utc(value["expires_at"])
            if expires <= checked or expires - checked > MAX_OFFLINE_AUTHORIZATION:
                return None
            return {key: str(item) for key, item in value.items()}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def save(self, *, username: str, checked_at: datetime, expires_at: datetime) -> None:
        checked_at = checked_at.astimezone(timezone.utc)
        expires_at = min(
            expires_at.astimezone(timezone.utc),
            checked_at + MAX_OFFLINE_AUTHORIZATION,
        )
        payload = {
            "schema": AUTHORIZATION_SCHEMA,
            "installation_id": self.installation_id,
            "username": str(username)[:80],
            "checked_at": checked_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "expires_at": expires_at.isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        protected = protect_for_current_user(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            description="RF QOL Agent authorization",
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_bytes(protected)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class AgentAuthorizationManager:
    """Revalida pelo site sem interromper uma autorizacao offline ainda valida."""

    def __init__(
        self,
        transport: AgentBatchTransport,
        store: AgentAuthorizationStore,
        *,
        refresh_seconds: int = DEFAULT_REFRESH_SECONDS,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self.transport = transport
        self.store = store
        self.refresh_seconds = max(60, min(6 * 60 * 60, int(refresh_seconds)))
        self.clock = clock
        self._cached = store.load()
        self._last_refresh_attempt: datetime | None = None
        self._status = "authorized" if self._cache_valid() else "validation_required"
        self._pairing_code: str | None = None
        self._last_error_code: str | None = None
        self._lock = threading.RLock()

    def _cache_valid(self) -> bool:
        if not self._cached:
            return False
        try:
            now = self.clock()
            checked = _utc(self._cached["checked_at"])
            return checked - timedelta(minutes=5) <= now < _utc(
                self._cached["expires_at"]
            )
        except (ValueError, KeyError):
            return False

    def refresh(self, *, force: bool = False) -> bool:
        with self._lock:
            now = self.clock()
            refresh_seconds = (
                PENDING_REFRESH_SECONDS
                if self._status in {"pending", "validation_required"}
                else self.refresh_seconds
            )
            if (
                not force
                and self._last_refresh_attempt is not None
                and (now - self._last_refresh_attempt).total_seconds() < refresh_seconds
            ):
                return self._cache_valid()
            self._last_refresh_attempt = now
            try:
                receipt = self.transport.authorize()
            except AgentTransportError as error:
                self._last_error_code = error.code
                if not self._cache_valid():
                    self._status = "validation_required"
                return self._cache_valid()
            self._apply(receipt)
            return self._cache_valid()

    def _apply(self, receipt: AuthorizationReceipt) -> None:
        self._pairing_code = receipt.pairing_code
        self._last_error_code = None
        if receipt.status == "authorized" and receipt.username:
            checked = _utc(receipt.server_time)
            expires = checked + timedelta(seconds=receipt.valid_for_seconds)
            self.store.save(
                username=receipt.username,
                checked_at=checked,
                expires_at=expires,
            )
            self._cached = self.store.load()
            self._status = "authorized"
            self._pairing_code = None
            return
        self.store.clear()
        self._cached = None
        self._status = receipt.status

    def require_capture(self) -> None:
        if self.refresh(force=not self._cache_valid()):
            return
        if self._status == "pending" and self._pairing_code:
            raise RuntimeError(
                f"Vincule este Agent no site com o codigo {self._pairing_code}"
            )
        if self._status == "revoked":
            raise RuntimeError("Este Agent foi desvinculado no site")
        raise RuntimeError("Conecte ao site para validar o Agent antes da captura")

    def health(self) -> dict[str, object]:
        with self._lock:
            valid = self._cache_valid()
            return {
                "required": True,
                "authorized": valid,
                "status": "authorized" if valid else self._status,
                "username": self._cached.get("username") if valid and self._cached else None,
                "expires_at": self._cached.get("expires_at") if valid and self._cached else None,
                "pairing_code": self._pairing_code,
                "last_error_code": self._last_error_code,
            }
