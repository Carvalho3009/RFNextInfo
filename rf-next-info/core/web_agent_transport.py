"""Transporte HTTPS assinado, ativado apenas no perfil online do Agent."""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from core.web_agent import (
    DELIVERY_PRIORITY_BULK,
    DELIVERY_PRIORITY_HIGH,
    DELIVERY_PRIORITY_IMMEDIATE,
    DELIVERY_PRIORITY_REALTIME,
    AgentOutbox,
    INGEST_BATCH_SCHEMA,
    delivery_priority,
    delivery_priority_name,
)
from core.web_agent_identity import AgentIdentity


INGEST_PATH = "/api/qol/v1/ingest/batches"
REGISTRATION_PATH = "/api/qol/v1/installations/register"
AUTHORIZATION_PATH = "/api/qol/v1/installations/authorization"
SUBSESSION_SYNC_PATH = "/api/qol/v1/agent/subsessions/sync"
CHARACTER_SYNC_PATH = "/api/qol/v1/agent/characters/sync"
MAX_RESPONSE_BYTES = 64 * 1024
RETRYABLE_DELIVERY_CODES = frozenset({
    "batch_conflict", "body_too_large", "event_conflict",
})
DELIVERY_PRIORITY_SCHEDULE = (
    *((DELIVERY_PRIORITY_HIGH,) * 8),
    *((DELIVERY_PRIORITY_REALTIME,) * 4),
    DELIVERY_PRIORITY_BULK,
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AgentTransportError(RuntimeError):
    code = "transport_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = str(code)[:64]


class TemporaryTransportError(AgentTransportError):
    code = "temporarily_unavailable"


class PermanentTransportError(AgentTransportError):
    code = "registration_required"


class InvalidTransportResponse(AgentTransportError):
    code = "invalid_response"


@dataclass(frozen=True)
class DeliveryReceipt:
    batch_id: str
    accepted_through_sequence: int
    duplicate: bool
    rejected_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class RegistrationReceipt:
    installation_id: str
    status: str
    duplicate: bool
    server_time: str


@dataclass(frozen=True)
class AuthorizationReceipt:
    installation_id: str
    status: str
    username: str | None
    pairing_code: str | None
    server_time: str
    valid_for_seconds: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _validated_base_url(value: str) -> tuple[str, str]:
    parsed = urllib.parse.urlsplit(str(value).strip())
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("O Agent exige uma URL HTTPS sem credenciais ou consulta")
    base_path = parsed.path.rstrip("/")
    base = urllib.parse.urlunsplit(("https", parsed.netloc, base_path, "", ""))
    return base, f"{base_path}{INGEST_PATH}" or INGEST_PATH


def _default_sender(
    request: urllib.request.Request, timeout: float, response_limit: int
) -> tuple[int, Mapping[str, str], bytes]:
    try:
        opener = urllib.request.build_opener(_NoRedirect())
        with opener.open(request, timeout=timeout) as response:
            body = response.read(response_limit + 1)
            if len(body) > response_limit:
                raise InvalidTransportResponse("Resposta excede o limite")
            return int(response.status), dict(response.headers.items()), body
    except urllib.error.HTTPError as error:
        try:
            body = error.read(response_limit + 1)
        except OSError:
            body = b""
        server_code = f"http_{error.code}"
        if len(body) <= response_limit:
            try:
                value = json.loads(body)
                if (
                    isinstance(value, dict)
                    and isinstance(value.get("error"), str)
                    and 1 <= len(value["error"]) <= 64
                ):
                    server_code = value["error"]
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
        if error.code in {408, 425, 429} or 500 <= error.code <= 599:
            raise TemporaryTransportError(
                f"HTTP {error.code}", code=server_code
            ) from None
        raise PermanentTransportError(
            f"HTTP {error.code}", code=server_code
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise TemporaryTransportError(type(error).__name__) from None


class AgentBatchTransport:
    """Monta requests sem bearer token e valida o recibo antes de qualquer ACK."""

    def __init__(
        self,
        base_url: str,
        identity: AgentIdentity,
        *,
        version: str,
        timeout_seconds: float = 20.0,
        sender: Callable[
            [urllib.request.Request, float, int],
            tuple[int, Mapping[str, str], bytes],
        ] = _default_sender,
    ) -> None:
        self.base_url, self.request_path = _validated_base_url(base_url)
        self.url = self.base_url + INGEST_PATH
        self.registration_url = self.base_url + REGISTRATION_PATH
        self.authorization_url = self.base_url + AUTHORIZATION_PATH
        self.subsession_sync_url = self.base_url + SUBSESSION_SYNC_PATH
        self.character_sync_url = self.base_url + CHARACTER_SYNC_PATH
        base_path = urllib.parse.urlsplit(self.base_url).path.rstrip("/")
        self.subsession_request_path = f"{base_path}{SUBSESSION_SYNC_PATH}"
        self.character_request_path = f"{base_path}{CHARACTER_SYNC_PATH}"
        self.identity = identity
        self.user_agent = f"RFQOL-Agent/{str(version)[:64]}"
        self.timeout_seconds = max(1.0, min(30.0, float(timeout_seconds)))
        self._sender = sender

    def register(self) -> RegistrationReceipt:
        body = _canonical(self.identity.registration())
        request = urllib.request.Request(
            self.registration_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        status, _headers, response_body = self._sender(
            request, self.timeout_seconds, MAX_RESPONSE_BYTES
        )
        if not 200 <= int(status) <= 299:
            if status in {408, 425, 429} or status >= 500:
                raise TemporaryTransportError(f"HTTP {status}")
            raise PermanentTransportError(f"HTTP {status}")
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise InvalidTransportResponse("Resposta excede o limite")
        try:
            value = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTransportResponse("Resposta de registro invalida") from error
        required = {"installation_id", "status", "duplicate", "server_time"}
        if not isinstance(value, dict) or set(value) != required:
            raise InvalidTransportResponse("Schema de registro invalido")
        if value["installation_id"] != self.identity.installation_id:
            raise InvalidTransportResponse("Registro pertence a outra instalacao")
        if value["status"] not in {"pending", "active", "revoked"}:
            raise InvalidTransportResponse("Estado de registro invalido")
        if type(value["duplicate"]) is not bool:
            raise InvalidTransportResponse("Duplicidade de registro invalida")
        server_time = str(value["server_time"])
        if not server_time.endswith("Z") or len(server_time) > 40:
            raise InvalidTransportResponse("Horario do registro invalido")
        return RegistrationReceipt(
            installation_id=str(value["installation_id"]),
            status=str(value["status"]),
            duplicate=bool(value["duplicate"]),
            server_time=server_time,
        )

    def authorize(self) -> AuthorizationReceipt:
        body = _canonical(self.identity.registration())
        request = urllib.request.Request(
            self.authorization_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
            },
            method="POST",
        )
        status, _headers, response_body = self._sender(
            request, self.timeout_seconds, MAX_RESPONSE_BYTES
        )
        if not 200 <= int(status) <= 299:
            if status in {408, 425, 429} or status >= 500:
                raise TemporaryTransportError(f"HTTP {status}")
            raise PermanentTransportError(f"HTTP {status}")
        if len(response_body) > MAX_RESPONSE_BYTES:
            raise InvalidTransportResponse("Resposta excede o limite")
        try:
            value = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTransportResponse("Resposta de autorizacao invalida") from error
        required = {
            "installation_id", "status", "username", "pairing_code",
            "server_time", "valid_for_seconds",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise InvalidTransportResponse("Schema de autorizacao invalido")
        if value["installation_id"] != self.identity.installation_id:
            raise InvalidTransportResponse("Autorizacao pertence a outra instalacao")
        if value["status"] not in {"pending", "authorized", "revoked"}:
            raise InvalidTransportResponse("Estado de autorizacao invalido")
        username = value["username"]
        pairing_code = value["pairing_code"]
        if username is not None and (
            not isinstance(username, str) or not 1 <= len(username) <= 80
        ):
            raise InvalidTransportResponse("Usuario de autorizacao invalido")
        if pairing_code is not None and (
            not isinstance(pairing_code, str)
            or len(pairing_code) != 9
            or pairing_code[4] != "-"
            or not pairing_code.replace("-", "").isalnum()
        ):
            raise InvalidTransportResponse("Codigo de vinculacao invalido")
        valid_for = value["valid_for_seconds"]
        if type(valid_for) is not int or not 60 <= valid_for <= 24 * 60 * 60:
            raise InvalidTransportResponse("Validade de autorizacao invalida")
        server_time = str(value["server_time"])
        if not server_time.endswith("Z") or len(server_time) > 40:
            raise InvalidTransportResponse("Horario da autorizacao invalido")
        if value["status"] == "authorized" and not username:
            raise InvalidTransportResponse("Autorizacao sem usuario")
        if value["status"] != "pending" and pairing_code is not None:
            raise InvalidTransportResponse("Codigo fora do estado pendente")
        return AuthorizationReceipt(
            installation_id=str(value["installation_id"]),
            status=str(value["status"]),
            username=username,
            pairing_code=pairing_code,
            server_time=server_time,
            valid_for_seconds=valid_for,
        )

    def _request(self, batch: dict) -> urllib.request.Request:
        if (
            not isinstance(batch, dict)
            or batch.get("schema") != INGEST_BATCH_SCHEMA
            or batch.get("installation_id") != self.identity.installation_id
        ):
            raise ValueError("Lote nao pertence ao Agent")
        batch_id = str(batch.get("batch_id") or "")
        if len(batch_id) != 64 or any(char not in "0123456789abcdef" for char in batch_id):
            raise ValueError("batch_id invalido")
        body = _canonical(batch)
        body_sha256 = hashlib.sha256(body).hexdigest()
        timestamp = _utc_now()
        nonce = uuid.uuid4().hex
        signed = "\n".join((
            "POST",
            self.request_path,
            batch_id,
            timestamp,
            nonce,
            body_sha256,
        )).encode("utf-8")
        encoded = gzip.compress(body, compresslevel=6, mtime=0) if len(body) >= 1024 else body
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "Idempotency-Key": batch_id,
            "X-RFQOL-Installation-ID": self.identity.installation_id,
            "X-RFQOL-Key-ID": self.identity.key_id,
            "X-RFQOL-Timestamp": timestamp,
            "X-RFQOL-Nonce": nonce,
            "X-RFQOL-Body-SHA256": body_sha256,
            "X-RFQOL-Signature": self.identity.sign(signed),
        }
        if encoded is not body:
            headers["Content-Encoding"] = "gzip"
        return urllib.request.Request(
            self.url, data=encoded, headers=headers, method="POST"
        )

    @staticmethod
    def _receipt(batch: dict, status: int, body: bytes) -> DeliveryReceipt:
        if not 200 <= int(status) <= 299:
            if status in {408, 425, 429} or status >= 500:
                raise TemporaryTransportError(f"HTTP {status}")
            raise PermanentTransportError(f"HTTP {status}")
        if len(body) > MAX_RESPONSE_BYTES:
            raise InvalidTransportResponse("Resposta excede o limite")
        try:
            value = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTransportResponse("Resposta JSON invalida") from error
        required = {
            "batch_id", "accepted", "accepted_through_sequence", "duplicate",
            "rejected_events", "server_time",
        }
        if not isinstance(value, dict) or set(value) != required:
            raise InvalidTransportResponse("Schema de recibo invalido")
        if value["batch_id"] != batch["batch_id"] or value["accepted"] is not True:
            raise InvalidTransportResponse("Recibo nao confirma o lote")
        if type(value["duplicate"]) is not bool:
            raise InvalidTransportResponse("Marcador de duplicidade invalido")
        first = int(batch["first_sequence"])
        last = int(batch["last_sequence"])
        accepted = value["accepted_through_sequence"]
        if type(accepted) is not int or not first <= accepted <= last:
            raise InvalidTransportResponse("Sequencia confirmada invalida")
        events = batch.get("events")
        if not isinstance(events, list):
            raise InvalidTransportResponse("Lote sem eventos")
        by_id = {
            str(event.get("event_id")): int(event.get("sequence"))
            for event in events
            if isinstance(event, dict)
        }
        rejected_ids: list[str] = []
        rejected = value["rejected_events"]
        if not isinstance(rejected, list) or len(rejected) > len(events):
            raise InvalidTransportResponse("Rejeicoes invalidas")
        for item in rejected:
            if not isinstance(item, dict) or set(item) != {"event_id", "code"}:
                raise InvalidTransportResponse("Rejeicao fora do schema")
            event_id = str(item["event_id"])
            code = str(item["code"])
            if (
                event_id not in by_id
                or by_id[event_id] <= accepted
                or not 1 <= len(code) <= 64
            ):
                raise InvalidTransportResponse("Rejeicao inconsistente")
            rejected_ids.append(event_id)
        return DeliveryReceipt(
            batch_id=str(value["batch_id"]),
            accepted_through_sequence=accepted,
            duplicate=bool(value["duplicate"]),
            rejected_event_ids=tuple(dict.fromkeys(rejected_ids)),
        )

    def send(self, batch: dict) -> DeliveryReceipt:
        request = self._request(batch)
        status, _headers, body = self._sender(
            request, self.timeout_seconds, MAX_RESPONSE_BYTES
        )
        return self._receipt(batch, status, body)

    def sync_subsession_commands(
        self, results: list[dict[str, object]],
        progress: list[dict[str, object]] | None = None,
    ) -> list[dict[str, object]]:
        if not isinstance(results, list) or len(results) > 64:
            raise ValueError("Resultados de subsessao invalidos")
        progress = [] if progress is None else progress
        if not isinstance(progress, list) or len(progress) > 64:
            raise ValueError("Progresso de subsessao invalido")
        body = _canonical({
            "schema": "rf-qol.subsession-command-sync/v2",
            "results": results,
            "progress": progress,
        })
        body_sha256 = hashlib.sha256(body).hexdigest()
        timestamp = _utc_now()
        nonce = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        signed = "\n".join((
            "POST", self.subsession_request_path, request_id, timestamp, nonce,
            body_sha256,
        )).encode("utf-8")
        request = urllib.request.Request(
            self.subsession_sync_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
                "Idempotency-Key": request_id,
                "X-RFQOL-Installation-ID": self.identity.installation_id,
                "X-RFQOL-Key-ID": self.identity.key_id,
                "X-RFQOL-Timestamp": timestamp,
                "X-RFQOL-Nonce": nonce,
                "X-RFQOL-Body-SHA256": body_sha256,
                "X-RFQOL-Signature": self.identity.sign(signed),
            },
            method="POST",
        )
        status, _headers, response_body = self._sender(
            request, self.timeout_seconds, MAX_RESPONSE_BYTES
        )
        if not 200 <= int(status) <= 299:
            if status in {408, 425, 429} or status >= 500:
                raise TemporaryTransportError(f"HTTP {status}")
            raise PermanentTransportError(f"HTTP {status}")
        try:
            value = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTransportResponse(
                "Resposta de subsessoes invalida"
            ) from error
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "commands", "server_time"}
            or value.get("schema") != "rf-qol.subsession-commands/v1"
            or not isinstance(value.get("commands"), list)
            or len(value["commands"]) > 20
        ):
            raise InvalidTransportResponse("Schema de subsessoes invalido")
        server_time = value.get("server_time")
        if (
            not isinstance(server_time, str)
            or not server_time.endswith("Z")
            or len(server_time) > 40
        ):
            raise InvalidTransportResponse("Horario de subsessoes invalido")
        required = {
            "command_id", "subsession_ref", "action", "character_uid", "name",
            "map_name", "spot_name", "mobs",
        }
        commands: list[dict[str, object]] = []
        for raw in value["commands"]:
            if not isinstance(raw, dict) or set(raw) != required:
                raise InvalidTransportResponse("Comando de subsessao invalido")
            if (
                not isinstance(raw["command_id"], str)
                or len(raw["command_id"]) != 32
                or any(char not in "0123456789abcdef" for char in str(raw["command_id"]))
                or not isinstance(raw["subsession_ref"], str)
                or len(raw["subsession_ref"]) != 32
                or any(char not in "0123456789abcdef" for char in str(raw["subsession_ref"]))
                or raw["action"] not in {"start", "update", "stop"}
                or type(raw["character_uid"]) is not int
                or not 0 < raw["character_uid"] <= 2**64 - 1
                or not isinstance(raw["name"], str)
                or not 1 <= len(raw["name"]) <= 120
                or not isinstance(raw["map_name"], str)
                or len(raw["map_name"]) > 120
                or not isinstance(raw["spot_name"], str)
                or len(raw["spot_name"]) > 120
                or not isinstance(raw["mobs"], list)
                or len(raw["mobs"]) > 32
                or any(
                    not isinstance(mob, str) or not 1 <= len(mob) <= 96
                    for mob in raw["mobs"]
                )
            ):
                raise InvalidTransportResponse("Valores da subsessao invalidos")
            commands.append(dict(raw))
        return commands

    def sync_character_profiles(self) -> list[dict[str, object]]:
        """Baixa apenas personagens públicos já vinculados à instalação."""
        body = _canonical({"schema": "rf-qol.character-profile-sync/v1"})
        body_sha256 = hashlib.sha256(body).hexdigest()
        timestamp = _utc_now()
        nonce = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        signed = "\n".join((
            "POST", self.character_request_path, request_id, timestamp, nonce,
            body_sha256,
        )).encode("utf-8")
        request = urllib.request.Request(
            self.character_sync_url,
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": self.user_agent,
                "Idempotency-Key": request_id,
                "X-RFQOL-Installation-ID": self.identity.installation_id,
                "X-RFQOL-Key-ID": self.identity.key_id,
                "X-RFQOL-Timestamp": timestamp,
                "X-RFQOL-Nonce": nonce,
                "X-RFQOL-Body-SHA256": body_sha256,
                "X-RFQOL-Signature": self.identity.sign(signed),
            },
            method="POST",
        )
        status, _headers, response_body = self._sender(
            request, self.timeout_seconds, MAX_RESPONSE_BYTES
        )
        if not 200 <= int(status) <= 299:
            if status in {408, 425, 429} or status >= 500:
                raise TemporaryTransportError(f"HTTP {status}")
            raise PermanentTransportError(f"HTTP {status}")
        try:
            value = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InvalidTransportResponse(
                "Resposta de personagens invalida"
            ) from error
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "characters", "server_time"}
            or value.get("schema") != "rf-qol.character-profiles/v1"
            or not isinstance(value.get("characters"), list)
            or len(value["characters"]) > 128
        ):
            raise InvalidTransportResponse("Schema de personagens invalido")
        server_time = value.get("server_time")
        if (
            not isinstance(server_time, str)
            or not server_time.endswith("Z")
            or len(server_time) > 40
        ):
            raise InvalidTransportResponse("Horario de personagens invalido")
        required = {
            "character_uid", "name", "level", "total_exp",
            "biosuit_item_index", "rover_item_index", "power", "last_seen_at",
        }
        characters: list[dict[str, object]] = []
        for raw in value["characters"]:
            if not isinstance(raw, dict) or set(raw) != required:
                raise InvalidTransportResponse("Personagem fora do schema")
            uid = raw.get("character_uid")
            if type(uid) is not int or not 0 < uid <= 2**64 - 1:
                raise InvalidTransportResponse("UID de personagem invalido")
            if not isinstance(raw.get("name"), str) or len(raw["name"]) > 120:
                raise InvalidTransportResponse("Nome de personagem invalido")
            for field in (
                "level", "total_exp", "biosuit_item_index",
                "rover_item_index", "power",
            ):
                item = raw.get(field)
                if item is not None and (type(item) is not int or item < 0):
                    raise InvalidTransportResponse(
                        "Atributo de personagem invalido"
                    )
            last_seen_at = raw.get("last_seen_at")
            if (
                not isinstance(last_seen_at, str)
                or not last_seen_at.endswith("Z")
                or len(last_seen_at) > 40
            ):
                raise InvalidTransportResponse(
                    "Horario do personagem invalido"
                )
            characters.append(dict(raw))
        return characters


class AgentDeliveryWorker:
    """Confirma a outbox fora da captura e aplica backoff limitado."""

    def __init__(
        self,
        outbox: AgentOutbox,
        transport: AgentBatchTransport,
        *,
        flush_seconds: float = 1.0,
        max_backoff_seconds: float = 60.0,
        jitter: Callable[[], float] = random.random,
        registration_retry_seconds: float = 30.0,
        max_burst_batches: int = 8,
        burst_pause_seconds: float = 0.1,
        max_consecutive_immediate_batches: int = 4,
    ) -> None:
        if outbox.installation_id != transport.identity.installation_id:
            raise ValueError("Outbox e transporte pertencem a instalacoes diferentes")
        self.outbox = outbox
        self.transport = transport
        self.flush_seconds = max(0.1, min(10.0, float(flush_seconds)))
        self.max_backoff_seconds = max(
            self.flush_seconds, min(300.0, float(max_backoff_seconds))
        )
        self._jitter = jitter
        self.registration_retry_seconds = max(
            5.0, min(300.0, float(registration_retry_seconds))
        )
        self.max_burst_batches = max(1, min(32, int(max_burst_batches)))
        self.burst_pause_seconds = max(
            0.01, min(self.flush_seconds, float(burst_pause_seconds))
        )
        self.max_consecutive_immediate_batches = max(
            1, min(16, int(max_consecutive_immediate_batches))
        )
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._temporary_failures = 0
        self._blocked = False
        self._sending = False
        self._registration_state = "unknown"
        self.last_attempt_at: str | None = None
        self.last_ack_at: str | None = None
        self.last_error_code: str | None = None
        self.sent_batches = 0
        self.sent_events = 0
        self.temporary_errors = 0
        self.permanent_errors = 0
        self.sent_by_priority: Counter[str] = Counter()
        self.last_batch_priority: str | None = None
        self.burst_cycles = 0
        self.max_burst_observed = 0
        self._priority_cursor = 0
        self._consecutive_immediate_batches = 0
        self._sent_rate_buckets: deque[tuple[int, int, int]] = deque()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def _next_priority(self) -> int | None:
        available = set(self.outbox.pending_priorities())
        if not available:
            return None
        if (
            DELIVERY_PRIORITY_IMMEDIATE in available
            and self._consecutive_immediate_batches
            < self.max_consecutive_immediate_batches
        ):
            self._consecutive_immediate_batches += 1
            return DELIVERY_PRIORITY_IMMEDIATE
        for _attempt in range(len(DELIVERY_PRIORITY_SCHEDULE)):
            priority = DELIVERY_PRIORITY_SCHEDULE[self._priority_cursor]
            self._priority_cursor = (
                self._priority_cursor + 1
            ) % len(DELIVERY_PRIORITY_SCHEDULE)
            if priority in available:
                self._consecutive_immediate_batches = 0
                return priority
        if DELIVERY_PRIORITY_IMMEDIATE in available:
            # Se só houver eventos imediatos, continue drenando sem uma pausa
            # artificial. Havendo outras filas, elas receberam uma vez antes
            # deste fallback e não ficam permanentemente bloqueadas.
            self._consecutive_immediate_batches = min(
                self.max_consecutive_immediate_batches,
                self._consecutive_immediate_batches + 1,
            )
            return DELIVERY_PRIORITY_IMMEDIATE
        self._consecutive_immediate_batches = 0
        return max(available)

    def _record_sent_locked(self, accepted: int, priority: int) -> None:
        name = delivery_priority_name(priority)
        self.sent_by_priority[name] += accepted
        self.last_batch_priority = name
        now_second = int(time.monotonic())
        if (
            self._sent_rate_buckets
            and self._sent_rate_buckets[-1][0] == now_second
        ):
            second, batches, events = self._sent_rate_buckets[-1]
            self._sent_rate_buckets[-1] = (
                second, batches + 1, events + accepted,
            )
        else:
            self._sent_rate_buckets.append((now_second, 1, accepted))
        while (
            self._sent_rate_buckets
            and self._sent_rate_buckets[0][0] < now_second - 59
        ):
            self._sent_rate_buckets.popleft()

    def send_once(self) -> bool:
        with self._lock:
            if self._blocked:
                return False
            self._sending = True
            self.last_attempt_at = _utc_now()
        try:
            if self._registration_state != "active":
                registration = self.transport.register()
                with self._lock:
                    self._registration_state = registration.status
                if registration.status == "pending":
                    with self._lock:
                        self.last_error_code = "registration_pending"
                    return False
                if registration.status == "revoked":
                    with self._lock:
                        self.last_error_code = "registration_revoked"
                        self._blocked = True
                    return False
                with self._lock:
                    self.last_error_code = None
            selected_priority = self._next_priority()
            batch = self.outbox.next_batch(priority=selected_priority)
            if batch is None:
                return False
            batch_events = batch.get("events") or []
            batch_priority = delivery_priority(
                batch_events[0].get("type") if batch_events else None,
                batch_events[0].get("payload") if batch_events else None,
            )
            receipt = self.transport.send(batch)
            accepted = self.outbox.acknowledge(
                receipt.batch_id, receipt.accepted_through_sequence
            )
            for event_id in receipt.rejected_event_ids:
                self.outbox.reject(event_id, "server_schema_rejection")
            with self._lock:
                self.sent_batches += 1
                self.sent_events += accepted
                self.last_ack_at = _utc_now()
                self.last_error_code = None
                self._temporary_failures = 0
                self._record_sent_locked(accepted, batch_priority)
            return True
        except TemporaryTransportError as error:
            with self._lock:
                self.temporary_errors += 1
                self._temporary_failures += 1
                self.last_error_code = error.code
            return False
        except (PermanentTransportError, InvalidTransportResponse) as error:
            with self._lock:
                if error.code in RETRYABLE_DELIVERY_CODES:
                    # Um receptor antigo podia recusar sobreposição de lote.
                    # Após a atualização do servidor, a mesma tentativa deve
                    # se recuperar sem exigir reiniciar o Agent.
                    self.temporary_errors += 1
                    self._temporary_failures += 1
                    self.last_error_code = error.code
                    return False
                self.permanent_errors += 1
                self.last_error_code = error.code
                if self._registration_state == "active" and error.code in {
                    "installation_not_active", "registration_required",
                }:
                    self._registration_state = (
                        "pending"
                        if error.code == "installation_not_active"
                        else "unknown"
                    )
                else:
                    self._blocked = True
            return False
        except Exception:
            # Falha local inesperada nao pode encerrar silenciosamente a thread
            # nem remover eventos ainda nao confirmados.
            with self._lock:
                self.permanent_errors += 1
                self.last_error_code = "local_delivery_error"
                self._blocked = True
            return False
        finally:
            with self._lock:
                self._sending = False

    def _delay(self) -> float:
        with self._lock:
            failures = self._temporary_failures
            registration_state = self._registration_state
        if registration_state == "pending":
            return self.registration_retry_seconds
        if failures <= 0:
            return self.flush_seconds
        base = min(
            self.max_backoff_seconds,
            self.flush_seconds * (2 ** min(failures, 10)),
        )
        return min(self.max_backoff_seconds, base * (0.75 + 0.5 * self._jitter()))

    def _run(self) -> None:
        while not self._stop.is_set():
            burst = 0
            with self._lock:
                blocked = self._blocked
            while (
                not blocked
                and not self._stop.is_set()
                and burst < self.max_burst_batches
                and self.send_once()
            ):
                burst += 1
                with self._lock:
                    blocked = self._blocked
            remaining = int(self.outbox.metrics()["events"])
            with self._lock:
                blocked = self._blocked
                failures = self._temporary_failures
                if burst:
                    self.burst_cycles += 1
                    self.max_burst_observed = max(
                        self.max_burst_observed, burst
                    )
            if blocked:
                delay = self.max_backoff_seconds
            elif failures:
                delay = self._delay()
            elif remaining:
                delay = self.burst_pause_seconds
            else:
                delay = self.flush_seconds
            self._wake.wait(delay)
            self._wake.clear()

    def metrics(self) -> dict[str, object]:
        with self._lock:
            now_second = int(time.monotonic())
            while (
                self._sent_rate_buckets
                and self._sent_rate_buckets[0][0] < now_second - 59
            ):
                self._sent_rate_buckets.popleft()
            state = (
                "blocked" if self._blocked else
                "registration_pending" if self._registration_state == "pending" else
                "sending" if self._sending else
                "backoff" if self._temporary_failures else
                "idle"
            )
            return {
                "state": state,
                "worker_alive": bool(self._thread and self._thread.is_alive()),
                "last_attempt_at": self.last_attempt_at,
                "last_ack_at": self.last_ack_at,
                "last_error_code": self.last_error_code,
                "registration_state": self._registration_state,
                "sent_batches": self.sent_batches,
                "sent_events": self.sent_events,
                "temporary_errors": self.temporary_errors,
                "permanent_errors": self.permanent_errors,
                "retry_seconds": round(self._delay(), 3),
                "sent_batches_last_minute": sum(
                    batches
                    for _second, batches, _events in self._sent_rate_buckets
                ),
                "sent_events_last_minute": sum(
                    events
                    for _second, _batches, events in self._sent_rate_buckets
                ),
                "sent_by_priority": dict(self.sent_by_priority),
                "last_batch_priority": self.last_batch_priority,
                "max_burst_batches": self.max_burst_batches,
                "max_consecutive_immediate_batches": (
                    self.max_consecutive_immediate_batches
                ),
                "burst_pause_seconds": self.burst_pause_seconds,
                "burst_cycles": self.burst_cycles,
                "max_burst_observed": self.max_burst_observed,
            }

    def stop(self) -> bool:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=self.transport.timeout_seconds + 2)
        if not self._thread or not self._thread.is_alive():
            self._thread = None
        return self._thread is None
