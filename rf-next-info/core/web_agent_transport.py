"""Transporte HTTPS assinado do Agent; nao e iniciado automaticamente."""

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
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Mapping

from core.web_agent import AgentOutbox, INGEST_BATCH_SCHEMA
from core.web_agent_identity import AgentIdentity


INGEST_PATH = "/api/qol/v1/ingest/batches"
MAX_RESPONSE_BYTES = 64 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AgentTransportError(RuntimeError):
    code = "transport_error"


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
            error.read(response_limit + 1)
        except OSError:
            pass
        if error.code in {408, 425, 429} or 500 <= error.code <= 599:
            raise TemporaryTransportError(f"HTTP {error.code}") from None
        raise PermanentTransportError(f"HTTP {error.code}") from None
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
        timeout_seconds: float = 8.0,
        sender: Callable[
            [urllib.request.Request, float, int],
            tuple[int, Mapping[str, str], bytes],
        ] = _default_sender,
    ) -> None:
        self.base_url, self.request_path = _validated_base_url(base_url)
        self.url = self.base_url + INGEST_PATH
        self.identity = identity
        self.user_agent = f"RFQOL-Agent/{str(version)[:64]}"
        self.timeout_seconds = max(1.0, min(30.0, float(timeout_seconds)))
        self._sender = sender

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
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._temporary_failures = 0
        self._blocked = False
        self._sending = False
        self.last_attempt_at: str | None = None
        self.last_ack_at: str | None = None
        self.last_error_code: str | None = None
        self.sent_batches = 0
        self.sent_events = 0
        self.temporary_errors = 0
        self.permanent_errors = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._wake.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def send_once(self) -> bool:
        with self._lock:
            if self._blocked:
                return False
            self._sending = True
            self.last_attempt_at = _utc_now()
        try:
            batch = self.outbox.next_batch()
            if batch is None:
                return False
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
            return True
        except TemporaryTransportError as error:
            with self._lock:
                self.temporary_errors += 1
                self._temporary_failures += 1
                self.last_error_code = error.code
            return False
        except (PermanentTransportError, InvalidTransportResponse) as error:
            with self._lock:
                self.permanent_errors += 1
                self.last_error_code = error.code
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
        if failures <= 0:
            return self.flush_seconds
        base = min(
            self.max_backoff_seconds,
            self.flush_seconds * (2 ** min(failures, 10)),
        )
        return min(self.max_backoff_seconds, base * (0.75 + 0.5 * self._jitter()))

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                blocked = self._blocked
            if not blocked:
                self.send_once()
            self._wake.wait(self._delay() if not blocked else self.max_backoff_seconds)
            self._wake.clear()

    def metrics(self) -> dict[str, object]:
        with self._lock:
            state = (
                "blocked" if self._blocked else
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
                "sent_batches": self.sent_batches,
                "sent_events": self.sent_events,
                "temporary_errors": self.temporary_errors,
                "permanent_errors": self.permanent_errors,
                "retry_seconds": round(self._delay(), 3),
            }

    def stop(self) -> bool:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=self.transport.timeout_seconds + 2)
        if not self._thread or not self._thread.is_alive():
            self._thread = None
        return self._thread is None
