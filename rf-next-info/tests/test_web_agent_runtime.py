from __future__ import annotations

import base64
import gzip
import hashlib
import json
import tempfile
import time
import unittest
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.web_agent import AgentOutbox, WebEventProjector
from core.web_agent_identity import (
    REGISTRATION_SIGNATURE_CONTEXT,
    SIGNATURE_CONTEXT,
    AgentIdentityStore,
)
from core.web_agent_runtime import (
    WebAgentOfflineRuntime,
    WebAgentRuntime,
    create_offline_web_agent_if_enabled,
    create_web_agent_if_enabled,
)
from core.web_agent_selftest import (
    run_offline_agent_self_test,
    run_offline_agent_stress_test,
)
from core.web_agent_transport import (
    AgentBatchTransport,
    AgentDeliveryWorker,
    InvalidTransportResponse,
    PermanentTransportError,
    TemporaryTransportError,
)


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _event(offset: int, kind: str = "update_exp") -> dict:
    data = (
        {"fields": {
            "character_uid": 123456,
            "character_name": "Personagem",
            "level": 66,
        }}
        if kind == "world_info_prefix"
        else {"level": 66, "exp": offset * 100, "gain_exp": 100}
    )
    return {
        "source": "memory://test",
        "flow": "10.0.0.2:12020 -> 10.0.0.1:50000",
        "stream_offset": offset,
        "bundle_seq": 0,
        "ts_ns": 1_700_000_000_000_000_000 + offset,
        "opcode": 0x0106 if kind == "world_info_prefix" else 0x0307,
        "type": kind,
        "data": data,
    }


class AgentIdentityStoreTest(unittest.TestCase):
    def test_identity_is_stable_signed_and_never_plaintext_on_disk(self):
        installation_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as folder:
            store = AgentIdentityStore(Path(folder))
            identity = store.load_or_create(installation_id)
            restored = store.load_or_create(installation_id)

            self.assertEqual(identity.key_id, restored.key_id)
            self.assertEqual(identity.pseudonym_key, restored.pseudonym_key)
            registration = identity.registration()
            self.assertEqual(registration["installation_id"], installation_id)
            self.assertNotIn("private", json.dumps(registration).lower())
            proof = registration.pop("proof")
            Ed25519PublicKey.from_public_bytes(
                _unb64(identity.public_key_b64url)
            ).verify(
                _unb64(proof),
                REGISTRATION_SIGNATURE_CONTEXT + json.dumps(
                    registration, sort_keys=True, separators=(",", ":")
                ).encode(),
            )
            signature = _unb64(identity.sign(b"lote"))
            Ed25519PublicKey.from_public_bytes(
                _unb64(identity.public_key_b64url)
            ).verify(signature, SIGNATURE_CONTEXT + b"lote")

            encrypted = store.path.read_bytes()
            self.assertNotIn(identity._private_key.private_bytes_raw(), encrypted)
            self.assertNotIn(identity.pseudonym_key, encrypted)

    def test_backup_recovers_primary_but_double_corruption_never_rotates_key(self):
        installation_id = str(uuid.uuid4())
        with tempfile.TemporaryDirectory() as folder:
            store = AgentIdentityStore(Path(folder))
            original = store.load_or_create(installation_id)
            store.path.write_bytes(b"corrompido")
            recovered = store.load_or_create(installation_id)
            self.assertEqual(recovered.key_id, original.key_id)

            store.path.write_bytes(b"corrompido")
            store.backup_path.write_bytes(b"corrompido")
            with self.assertRaisesRegex(OSError, "corrompida"):
                store.load_or_create(installation_id)

    def test_identity_cannot_be_silently_reused_by_another_installation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = AgentIdentityStore(Path(folder))
            store.load_or_create(str(uuid.uuid4()))
            with self.assertRaisesRegex(OSError, "outra instalacao"):
                store.load_or_create(str(uuid.uuid4()))


class AgentTransportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.installation_id = str(uuid.uuid4())
        self.identity = AgentIdentityStore(self.root).load_or_create(
            self.installation_id
        )
        self.outbox = AgentOutbox(
            self.root / "outbox.sqlite3", self.installation_id
        )
        self.projector = WebEventProjector(
            self.installation_id,
            self.identity.pseudonym_key,
            decoder_version="test",
        )

    def tearDown(self) -> None:
        try:
            self.outbox.close()
        except Exception:
            pass
        self.folder.cleanup()

    def enqueue(self, count: int = 1) -> None:
        self.outbox.enqueue(self.projector.project(
            _event(1, "world_info_prefix"), "sessao-1"
        ))
        for offset in range(2, count + 1):
            self.outbox.enqueue(self.projector.project(
                _event(offset), "sessao-1"
            ))

    @staticmethod
    def accepted_sender(request, _timeout, _limit):
        if request.full_url.endswith("/api/qol/v1/installations/register"):
            registration = json.loads(bytes(request.data))
            response = {
                "installation_id": registration["installation_id"],
                "status": "active",
                "duplicate": False,
                "server_time": "2026-08-22T12:00:00Z",
            }
            return 202, {"Content-Type": "application/json"}, json.dumps(response).encode()
        body = bytes(request.data)
        if request.get_header("Content-encoding") == "gzip":
            body = gzip.decompress(body)
        batch = json.loads(body)
        response = {
            "batch_id": batch["batch_id"],
            "accepted": True,
            "accepted_through_sequence": batch["last_sequence"],
            "duplicate": False,
            "rejected_events": [],
            "server_time": "2026-08-22T12:00:00Z",
        }
        return 200, {"Content-Type": "application/json"}, json.dumps(response).encode()

    def test_https_request_is_signed_and_contains_no_bearer_or_lease(self):
        captured: list[urllib.request.Request] = []

        def sender(request, timeout, limit):
            captured.append(request)
            return self.accepted_sender(request, timeout, limit)

        self.enqueue(3)
        batch = self.outbox.next_batch()
        transport = AgentBatchTransport(
            "https://qol.example.test/base",
            self.identity,
            version="2.0.0-web",
            sender=sender,
        )
        receipt = transport.send(batch)
        request = captured[0]
        body = bytes(request.data)
        if request.get_header("Content-encoding") == "gzip":
            body = gzip.decompress(body)
        body_hash = hashlib.sha256(body).hexdigest()
        signed = "\n".join((
            "POST",
            "/base/api/qol/v1/ingest/batches",
            request.get_header("Idempotency-key"),
            request.get_header("X-rfqol-timestamp"),
            request.get_header("X-rfqol-nonce"),
            body_hash,
        )).encode()
        Ed25519PublicKey.from_public_bytes(
            _unb64(self.identity.public_key_b64url)
        ).verify(
            _unb64(request.get_header("X-rfqol-signature")),
            SIGNATURE_CONTEXT + signed,
        )

        headers = json.dumps(dict(request.header_items())).lower()
        self.assertEqual(request.full_url, "https://qol.example.test/base/api/qol/v1/ingest/batches")
        self.assertEqual(request.get_header("X-rfqol-body-sha256"), body_hash)
        self.assertNotIn("authorization", headers)
        self.assertNotIn("bearer", headers)
        self.assertNotIn("lease", headers)
        self.assertEqual(receipt.accepted_through_sequence, batch["last_sequence"])

    def test_transport_rejects_non_https_and_inconsistent_receipt(self):
        for invalid_url in (
            "http://qol.example.test",
            "https://usuario:senha@qol.example.test",
            "https://qol.example.test?token=segredo",
        ):
            with self.subTest(url=invalid_url), self.assertRaisesRegex(
                ValueError, "HTTPS"
            ):
                AgentBatchTransport(
                    invalid_url, self.identity, version="test"
                )
        self.enqueue()
        batch = self.outbox.next_batch()

        def wrong_sender(_request, _timeout, _limit):
            response = {
                "batch_id": "0" * 64,
                "accepted": True,
                "accepted_through_sequence": batch["last_sequence"],
                "duplicate": False,
                "rejected_events": [],
                "server_time": "2026-08-22T12:00:00Z",
            }
            return 200, {}, json.dumps(response).encode()

        transport = AgentBatchTransport(
            "https://qol.example.test", self.identity,
            version="test", sender=wrong_sender,
        )
        with self.assertRaises(InvalidTransportResponse):
            transport.send(batch)
        self.assertEqual(self.outbox.metrics()["events"], 1)

    def test_delivery_acknowledges_partial_prefix_and_audits_rejection(self):
        self.enqueue(2)

        def partial_sender(request, _timeout, _limit):
            if request.full_url.endswith("/api/qol/v1/installations/register"):
                registration = json.loads(bytes(request.data))
                return 200, {}, json.dumps({
                    "installation_id": registration["installation_id"],
                    "status": "active",
                    "duplicate": True,
                    "server_time": "2026-08-22T12:00:00Z",
                }).encode()
            body = bytes(request.data)
            if request.get_header("Content-encoding") == "gzip":
                body = gzip.decompress(body)
            batch = json.loads(body)
            response = {
                "batch_id": batch["batch_id"],
                "accepted": True,
                "accepted_through_sequence": batch["first_sequence"],
                "duplicate": False,
                "rejected_events": [{
                    "event_id": batch["events"][1]["event_id"],
                    "code": "unsupported_event",
                }],
                "server_time": "2026-08-22T12:00:00Z",
            }
            return 200, {}, json.dumps(response).encode()

        transport = AgentBatchTransport(
            "https://qol.example.test", self.identity,
            version="test", sender=partial_sender,
        )
        worker = AgentDeliveryWorker(self.outbox, transport)
        self.assertTrue(worker.send_once())
        self.assertEqual(self.outbox.metrics()["events"], 0)
        self.assertEqual(worker.metrics()["sent_events"], 1)
        self.assertEqual(
            self.outbox.conn.execute(
                "SELECT reason FROM outbox_rejections"
            ).fetchone()[0],
            "server_schema_rejection",
        )

    def test_temporary_and_permanent_failures_never_delete_outbox(self):
        self.enqueue()

        def temporary(*_args):
            raise TemporaryTransportError("offline")

        first = AgentDeliveryWorker(
            self.outbox,
            AgentBatchTransport(
                "https://qol.example.test", self.identity,
                version="test", sender=temporary,
            ),
            jitter=lambda: 0.5,
        )
        self.assertFalse(first.send_once())
        self.assertEqual(first.metrics()["state"], "backoff")
        self.assertEqual(self.outbox.metrics()["events"], 1)

        def permanent(*_args):
            raise PermanentTransportError("revoked")

        second = AgentDeliveryWorker(
            self.outbox,
            AgentBatchTransport(
                "https://qol.example.test", self.identity,
                version="test", sender=permanent,
            ),
        )
        self.assertFalse(second.send_once())
        self.assertEqual(second.metrics()["state"], "blocked")
        self.assertEqual(second.metrics()["last_error_code"], "registration_required")
        self.assertEqual(self.outbox.metrics()["events"], 1)

    def test_unexpected_local_failure_blocks_worker_without_losing_event(self):
        self.enqueue()
        transport = AgentBatchTransport(
            "https://qol.example.test", self.identity,
            version="test", sender=self.accepted_sender,
        )
        worker = AgentDeliveryWorker(self.outbox, transport)
        with mock.patch.object(
            self.outbox, "acknowledge", side_effect=RuntimeError("falha local")
        ):
            self.assertFalse(worker.send_once())
        self.assertEqual(worker.metrics()["state"], "blocked")
        self.assertEqual(worker.metrics()["last_error_code"], "local_delivery_error")
        self.assertEqual(self.outbox.metrics()["events"], 1)

    def test_registration_is_automatic_and_pending_never_sends_events(self):
        self.enqueue()
        calls: list[str] = []

        def pending_sender(request, _timeout, _limit):
            calls.append(request.full_url)
            registration = json.loads(bytes(request.data))
            return 202, {}, json.dumps({
                "installation_id": registration["installation_id"],
                "status": "pending",
                "duplicate": False,
                "server_time": "2026-08-22T12:00:00Z",
            }).encode()

        worker = AgentDeliveryWorker(
            self.outbox,
            AgentBatchTransport(
                "https://qol.example.test",
                self.identity,
                version="test",
                sender=pending_sender,
            ),
        )

        self.assertFalse(worker.send_once())
        self.assertEqual(worker.metrics()["state"], "registration_pending")
        self.assertEqual(worker.metrics()["last_error_code"], "registration_pending")
        self.assertEqual(self.outbox.metrics()["events"], 1)
        self.assertEqual(calls, [
            "https://qol.example.test/api/qol/v1/installations/register"
        ])


class WebAgentRuntimeTest(unittest.TestCase):
    def test_disabled_factory_creates_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "nao-criar"
            runtime = create_web_agent_if_enabled(
                False,
                root,
                str(uuid.uuid4()),
                "https://qol.example.test",
                version="test",
            )
            self.assertIsNone(runtime)
            self.assertFalse(root.exists())

    def test_enabled_runtime_is_created_idle_with_sanitized_health(self):
        calls = 0

        def sender(*_args):
            nonlocal calls
            calls += 1
            raise AssertionError("transporte nao deveria iniciar na construcao")

        with tempfile.TemporaryDirectory() as folder:
            runtime = WebAgentRuntime.create(
                Path(folder),
                str(uuid.uuid4()),
                "https://qol.example.test",
                version="test",
                transport_sender=sender,
            )
            health = runtime.health()
            self.assertEqual(health["state"], "ready")
            self.assertFalse(health["delivery"]["worker_alive"])
            self.assertEqual(calls, 0)
            serialized = json.dumps(health).lower()
            self.assertNotIn("private", serialized)
            self.assertNotIn("public_key", serialized)
            self.assertNotIn("https://", serialized)
            runtime.close()

    def test_offline_runtime_creates_no_delivery_and_never_uses_network(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("rede nao permitida no modo offline"),
        ) as urlopen:
            runtime = create_offline_web_agent_if_enabled(
                True,
                Path(folder),
                str(uuid.uuid4()),
                version="test",
            )
            self.assertIsInstance(runtime, WebAgentOfflineRuntime)
            self.assertFalse(hasattr(runtime, "delivery"))
            runtime.start_session("sessao-1")
            self.assertTrue(runtime.submit(_event(1, "world_info_prefix")))
            runtime.pause_session("sessao-1")
            runtime.start_session("sessao-1", resumed=True)
            runtime.finish_session("sessao-1")
            runtime.bridge.wait_until_idle()
            health = runtime.health()
            self.assertEqual(health["state"], "offline_shadow")
            self.assertEqual(health["mode"], "offline")
            self.assertNotIn("delivery", health)
            runtime.close()
            urlopen.assert_not_called()

    def test_offline_self_test_covers_multiple_clients_and_sessions(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("autoteste tentou usar rede"),
        ) as urlopen:
            result = run_offline_agent_self_test(
                Path(folder), str(uuid.uuid4()), version="test"
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["network_used"])
            self.assertEqual(result["isolated_sessions"], 2)
            self.assertGreaterEqual(result["isolated_clients"], 3)
            self.assertEqual(result["session_lifecycle_events"], 6)
            self.assertEqual(result["queue_errors"], 0)
            urlopen.assert_not_called()

    def test_offline_stress_test_stays_bounded_and_uses_no_network(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch(
            "urllib.request.urlopen",
            side_effect=AssertionError("teste de pressao tentou usar rede"),
        ) as urlopen:
            result = run_offline_agent_stress_test(
                Path(folder),
                str(uuid.uuid4()),
                sessions=3,
                clients=4,
                events_per_client=40,
                version="test",
            )

            self.assertTrue(result["ok"])
            self.assertFalse(result["network_used"])
            self.assertEqual(result["events"], 498)
            self.assertEqual(result["queue_errors"], 0)
            self.assertEqual(result["queue_dropped"], 0)
            self.assertLess(result["peak_traced_memory_bytes"], 64 * 1024 * 1024)
            self.assertGreater(result["events_per_second"], 0)
            urlopen.assert_not_called()

    def test_opt_in_runtime_delivers_outside_capture_queue(self):
        calls = 0

        def sender(request, _timeout, _limit):
            nonlocal calls
            calls += 1
            if request.full_url.endswith("/api/qol/v1/installations/register"):
                registration = json.loads(bytes(request.data))
                return 202, {}, json.dumps({
                    "installation_id": registration["installation_id"],
                    "status": "active",
                    "duplicate": False,
                    "server_time": "2026-08-22T12:00:00Z",
                }).encode()
            body = bytes(request.data)
            if request.get_header("Content-encoding") == "gzip":
                body = gzip.decompress(body)
            batch = json.loads(body)
            response = {
                "batch_id": batch["batch_id"],
                "accepted": True,
                "accepted_through_sequence": batch["last_sequence"],
                "duplicate": False,
                "rejected_events": [],
                "server_time": "2026-08-22T12:00:00Z",
            }
            return 200, {}, json.dumps(response).encode()

        with tempfile.TemporaryDirectory() as folder:
            runtime = WebAgentRuntime.create(
                Path(folder), str(uuid.uuid4()),
                "https://qol.example.test", version="test",
                transport_sender=sender,
            )
            runtime.start_session("sessao-1")
            self.assertTrue(runtime.submit(_event(1, "world_info_prefix")))
            self.assertTrue(runtime.submit(_event(2)))
            runtime.bridge.wait_until_idle()
            runtime.delivery.notify()
            deadline = time.monotonic() + 2
            while (
                runtime.bridge.outbox.metrics()["events"]
                and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            health = runtime.health()
            self.assertEqual(health["outbox"]["events"], 0)
            self.assertEqual(health["state"], "online")
            self.assertGreaterEqual(calls, 1)
            runtime.finish_session("sessao-1")
            runtime.close()


if __name__ == "__main__":
    unittest.main()
