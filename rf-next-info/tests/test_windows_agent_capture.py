from __future__ import annotations

import tempfile
import json
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from core.web_agent import AgentOutbox
from core.windows_agent_capture import (
    MAX_AGENT_MEMORY_MB,
    MIN_AGENT_MEMORY_MB,
    AgentClientRegistry,
    StandaloneWindowsAgentRuntime,
    agent_memory_limits,
)


class _FakeCapture:
    fail_start = False

    def __init__(self, target, ports):
        self.target = target
        self.ports = tuple(ports)
        self.packet_sink = None
        self.started = False
        self.stopped = False
        self.added_ports = []
        self.packets = 0
        self.received_packets = 0
        self.filtered_packets = 0
        self.duplicate_packets = 0
        self.missed_write = 0
        self.missed_read = 0
        self.sink_errors = 0

    def set_packet_sink(self, sink):
        self.packet_sink = sink

    def start(self):
        if self.fail_start:
            raise RuntimeError("falha simulada")
        self.started = True

    def add_ports(self, ports):
        self.added_ports.extend(ports)
        return len(tuple(ports))

    def stop(self):
        self.stopped = True


def _processes(*pids: int):
    return {
        r"C:\RF\ProjectRF.exe": (
            set(pids),
            {51000 + index for index, _pid in enumerate(pids)},
            {12020},
        )
    }


def _decoded_identity(uid: int, name: str, offset: int = 1) -> dict:
    return {
        "source": "memory://agent-capture-test",
        "flow": f"10.0.0.1:{51000 + uid} -> 10.0.0.2:12020",
        "stream_offset": offset,
        "bundle_seq": 0,
        "ts_ns": 1_700_000_000_000_000_000 + offset,
        "opcode": 0x0106,
        "type": "world_info_prefix",
        "data": {"fields": {
            "character_uid": uid,
            "character_name": name,
            "level": 66,
        }},
    }


class AgentMemoryLimitsTest(unittest.TestCase):
    def test_memory_budget_is_bounded_and_scales_all_live_queues(self):
        minimum = agent_memory_limits(1)
        default = agent_memory_limits(1024)
        maximum = agent_memory_limits(100_000)

        self.assertEqual(minimum["budget_mb"], MIN_AGENT_MEMORY_MB)
        self.assertEqual(default["budget_mb"], 1024)
        self.assertEqual(maximum["budget_mb"], MAX_AGENT_MEMORY_MB)
        self.assertLess(minimum["pending_packet_bytes"], default["pending_packet_bytes"])
        self.assertLess(default["pending_packet_bytes"], maximum["pending_packet_bytes"])
        self.assertLessEqual(maximum["monitor_feed_bytes"], 64 * 1024 * 1024)


class AgentClientRegistryTest(unittest.TestCase):
    def test_registry_keeps_only_projected_client_identity(self):
        now_ns = [10_000_000_000]
        registry = AgentClientRegistry(
            max_clients=1, clock_ns=lambda: now_ns[0]
        )
        registry.observe({
            "type": "character.observed",
            "client_ref": "client-a",
            "occurred_at": "2026-08-23T12:00:00Z",
            "payload": {"name": "Primeiro", "level": 60},
        })
        registry.observe({
            "type": "character.observed",
            "client_ref": "client-b",
            "occurred_at": "2026-08-23T12:00:01Z",
            "payload": {"name": "Segundo", "level": 61},
        })

        self.assertEqual(registry.snapshot(), [{
            "client_ref": "client-b",
            "name": "Segundo",
            "level": 61,
            "last_seen": "2026-08-23T12:00:01Z",
            "session_duration_seconds": 0,
        }])
        registry.clear()
        self.assertEqual(registry.snapshot(), [])

    def test_registry_tracks_each_client_session_duration_independently(self):
        now_ns = [100 * 1_000_000_000]
        registry = AgentClientRegistry(clock_ns=lambda: now_ns[0])
        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "occurred_at": "2026-08-23T12:00:00Z",
            "payload": {"name": "Alice", "level": 66},
        })
        now_ns[0] += 65 * 1_000_000_000
        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "occurred_at": "2026-08-23T12:01:05Z",
            "payload": {"name": "Alice", "level": 67},
        })
        registry.observe({
            "type": "character.observed", "client_ref": "client-b",
            "occurred_at": "2026-08-23T12:01:05Z",
            "payload": {"name": "Bob", "level": 64},
        })
        now_ns[0] += 60 * 1_000_000_000

        clients = registry.snapshot()

        self.assertEqual(clients[0]["session_duration_seconds"], 125)
        self.assertEqual(clients[1]["session_duration_seconds"], 60)
        self.assertEqual(clients[0]["level"], 67)

    def test_registry_keeps_name_when_same_character_gets_partial_update(self):
        registry = AgentClientRegistry()
        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "occurred_at": "2026-08-23T12:00:00Z",
            "payload": {
                "character_uid": 123456789, "name": "Alice", "level": 66,
            },
        })
        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "occurred_at": "2026-08-23T12:01:00Z",
            "payload": {"character_uid": 123456789, "power": 987654},
        })

        client = registry.snapshot()[0]

        self.assertEqual(client["name"], "Alice")
        self.assertEqual(client["level"], 66)
        self.assertEqual(client["character_uid"], 123456789)
        self.assertEqual(client["last_seen"], "2026-08-23T12:01:00Z")

        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "payload": {"character_uid": 987654321, "power": 123456},
        })
        client = registry.snapshot()[0]
        self.assertEqual(client["name"], "")
        self.assertIsNone(client["level"])
        self.assertEqual(client["character_uid"], 987654321)

    def test_per_client_lifecycle_does_not_clear_other_durations(self):
        now_ns = [10_000_000_000]
        registry = AgentClientRegistry(clock_ns=lambda: now_ns[0])
        registry.observe({
            "type": "character.observed", "client_ref": "client-a",
            "payload": {"name": "Alice"},
        })
        now_ns[0] += 30 * 1_000_000_000

        registry.observe({
            "type": "session.lifecycle", "client_ref": "client-b",
            "payload": {"state": "started"},
        })

        self.assertEqual(
            registry.snapshot()[0]["session_duration_seconds"], 30
        )

    def test_registry_removes_exact_client_without_affecting_another(self):
        registry = AgentClientRegistry()
        for client_ref, name in (
            ("client-old", "Personagem antigo"),
            ("client-a", "Alice"),
            ("client-b", "Bob"),
        ):
            registry.observe({
                "type": "character.observed",
                "client_ref": client_ref,
                "payload": {"name": name},
            })

        registry.remove("client-old")
        self.assertEqual(
            [item["name"] for item in registry.snapshot()],
            ["Alice", "Bob"],
        )
        registry.remove("client-b")
        registry.observe({
            "type": "character.observed", "client_ref": "client-b",
            "payload": {"name": "Bob"},
        })
        self.assertEqual([item["name"] for item in registry.snapshot()], ["Alice"])


class StandaloneWindowsAgentRuntimeTest(unittest.TestCase):
    def _runtime(self, folder: str, reader, **options):
        options.setdefault("route_alias_reader", lambda _ports: {})
        return StandaloneWindowsAgentRuntime.create_offline(
            Path(folder),
            str(uuid.uuid4()),
            version="test",
            local_api_port=0,
            capture_factory=_FakeCapture,
            process_reader=reader,
            **options,
        )

    def test_capture_cycle_is_memory_only_and_exports_sanitized_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(folder, lambda _ports: _processes(101, 202))
            try:
                port = runtime.start_local_api()
                started = runtime.start_capture()
                capture = runtime.live_capture

                self.assertTrue(started["active"])
                self.assertEqual(started["client_processes"], 2)
                self.assertIsNone(capture.target)
                self.assertIsNotNone(capture.packet_sink)
                self.assertGreater(port, 0)

                self.assertTrue(runtime.service.submit(
                    _decoded_identity(1, "Personagem A")
                ))
                runtime.service.runtime.bridge.wait_until_idle()
                clients = runtime.health()["clients"]
                self.assertEqual([item["name"] for item in clients], ["Personagem A"])
                serialized = str(runtime.health())
                self.assertNotIn("memory://agent-capture-test", serialized)
                self.assertNotIn("10.0.0.1", serialized)

                stopped = runtime.stop_capture(reason="paused")
                self.assertFalse(stopped["active"])
                self.assertTrue(capture.stopped)
                self.assertFalse(runtime.health()["active"])
                self.assertEqual(runtime.health()["clients"], [])
            finally:
                runtime.close()

            outbox = AgentOutbox(
                Path(folder) / "web-agent-outbox.sqlite3",
                runtime.service.runtime.identity.installation_id,
            )
            try:
                states = [
                    row[0]
                    for row in outbox.conn.execute(
                        "SELECT json_extract(document, '$.payload.state') "
                        "FROM outbox_events "
                        "WHERE json_extract(document, '$.type') = 'session.lifecycle' "
                        "ORDER BY sequence"
                    ).fetchall()
                ]
                self.assertEqual(states, ["started", "paused"])
            finally:
                outbox.close()

    def test_start_requires_a_detected_pc_client(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(folder, lambda _ports: {})
            try:
                with self.assertRaisesRegex(RuntimeError, "Abra um cliente PC"):
                    runtime.start_capture()
                self.assertFalse(runtime.health()["active"])
                self.assertEqual(runtime.service.runtime.bridge.metrics()["outbox_events"], 0)
            finally:
                runtime.close()

    def test_online_runtime_registers_without_starting_capture(self):
        calls = []

        def sender(request, _timeout, _limit):
            calls.append(request.full_url)
            registration = json.loads(bytes(request.data))
            return 202, {}, json.dumps({
                "installation_id": registration["installation_id"],
                "status": "pending",
                "duplicate": False,
                "server_time": "2026-08-23T12:00:00Z",
            }).encode()

        with tempfile.TemporaryDirectory() as folder:
            runtime = StandaloneWindowsAgentRuntime.create_online(
                Path(folder),
                str(uuid.uuid4()),
                "https://qol.example.test",
                version="test",
                local_api_port=0,
                transport_sender=sender,
                capture_factory=_FakeCapture,
                process_reader=lambda _ports: {},
            )
            try:
                runtime.start_local_api()
                deadline = time.monotonic() + 2
                while (
                    runtime.health()["server"]["state"] != "registration_pending"
                    and time.monotonic() < deadline
                ):
                    time.sleep(0.01)
                health = runtime.health()
                self.assertFalse(health["active"])
                self.assertEqual(health["server"]["mode"], "online")
                self.assertEqual(
                    health["server"]["state"], "registration_pending"
                )
                api_health = runtime.service.api._health()
                self.assertEqual(api_health["server"]["mode"], "online")
                self.assertEqual(
                    api_health["delivery"]["state"], "registration_pending"
                )
                self.assertTrue(api_health["delivery"]["worker_alive"])
                self.assertEqual(calls, [
                    "https://qol.example.test/api/qol/v1/installations/register"
                ])
            finally:
                runtime.close()

    def test_online_capture_is_blocked_until_site_link(self):
        def sender(request, _timeout, _limit):
            registration = json.loads(bytes(request.data))
            if request.full_url.endswith("/authorization"):
                return 200, {}, json.dumps({
                    "installation_id": registration["installation_id"],
                    "status": "pending",
                    "username": None,
                    "pairing_code": "ABCD-EFGH",
                    "server_time": "2026-08-24T12:00:00Z",
                    "valid_for_seconds": 86400,
                }).encode()
            return 202, {}, json.dumps({
                "installation_id": registration["installation_id"],
                "status": "pending",
                "duplicate": False,
                "server_time": "2026-08-24T12:00:00Z",
            }).encode()

        with tempfile.TemporaryDirectory() as folder:
            runtime = StandaloneWindowsAgentRuntime.create_online(
                Path(folder), str(uuid.uuid4()), "https://qol.example.test",
                version="test", local_api_port=0, transport_sender=sender,
                capture_factory=_FakeCapture,
                process_reader=lambda _ports: _processes(1),
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "ABCD-EFGH"):
                    runtime.start_capture()
                self.assertFalse(runtime.active)
                self.assertEqual(
                    runtime.health()["server"]["authorization"]["status"],
                    "pending",
                )
            finally:
                runtime.close()

    def test_capture_start_failure_closes_lifecycle_without_leaking_threads(self):
        class FailingCapture(_FakeCapture):
            fail_start = True

        with tempfile.TemporaryDirectory() as folder:
            runtime = StandaloneWindowsAgentRuntime.create_offline(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                local_api_port=0,
                capture_factory=FailingCapture,
                process_reader=lambda _ports: _processes(1),
            )
            try:
                with self.assertRaisesRegex(RuntimeError, "falha simulada"):
                    runtime.start_capture()
                self.assertFalse(runtime.active)
                self.assertIn("falha simulada", runtime.health()["last_error"])
                self.assertFalse(runtime.live_events.metrics()["worker_alive"])
                self.assertEqual(
                    runtime.service.runtime.bridge.metrics()["outbox_events"], 0
                )
            finally:
                runtime.close()

    def test_memory_budget_changes_only_while_idle_and_routes_refresh(self):
        current = {"value": _processes(10)}
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(folder, lambda _ports: current["value"])
            try:
                self.assertTrue(runtime.configure_memory_budget(512))
                self.assertEqual(runtime.health()["memory_budget_mb"], 512)
                self.assertEqual(
                    runtime.service.feed.metrics()["event_limit"],
                    agent_memory_limits(512)["events"],
                )
                self.assertEqual(
                    runtime.service.feed.metrics()["byte_limit"],
                    agent_memory_limits(512)["monitor_feed_bytes"],
                )
                runtime.start_capture()
                self.assertFalse(runtime.configure_memory_budget(2048))
                current["value"] = _processes(10, 20)
                refreshed = runtime.refresh_routes()
                self.assertEqual(refreshed["client_processes"], 2)
                self.assertTrue(runtime.live_capture.added_ports)
            finally:
                runtime.close()

    def test_route_refresh_preserves_live_instances_and_removes_only_exited_process(self):
        current = {"value": _processes(10, 20)}
        with tempfile.TemporaryDirectory() as folder:
            aliases = {51000: "process:10:100", 51001: "process:20:200"}
            runtime = self._runtime(
                folder, lambda _ports: current["value"],
                route_alias_reader=lambda _ports: dict(aliases),
            )
            try:
                runtime.start_capture()
                for uid, name, alias in ((1, "Alice", aliases[51000]), (2, "Bob", aliases[51001])):
                    runtime.service.submit({**_decoded_identity(uid, name), "flow": f"client-route:{alias}"})
                runtime.service.runtime.bridge.wait_until_idle()
                before = runtime.registry.snapshot()
                current["value"] = {}
                aliases.clear()
                for probe in (lambda pid: {10: 100, 20: 200}[pid], lambda pid: None):
                    with mock.patch("core.windows_agent_capture.process_started_at", side_effect=probe):
                        self.assertEqual(runtime.refresh_routes()["client_processes"], 2)
                    self.assertEqual([row["name"] for row in runtime.registry.snapshot()], ["Alice", "Bob"])
                    self.assertEqual([row["client_ref"] for row in runtime.registry.snapshot()], [row["client_ref"] for row in before])
                # PID 10 reutilizado: remover Alice, sem tocar no cliente 20.
                with mock.patch("core.windows_agent_capture.process_started_at", side_effect=lambda pid: {10: 101, 20: 200}[pid]):
                    runtime.refresh_routes()
                self.assertEqual(
                    [item["name"] for item in runtime.health()["clients"]],
                    ["Bob"],
                )
                with mock.patch("core.windows_agent_capture.process_started_at", return_value=0):
                    runtime.refresh_routes()
                self.assertEqual(runtime.registry.snapshot(), [])
            finally:
                runtime.close()

    def test_health_monitors_working_set_and_compacts_at_limit(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(
                folder,
                lambda _ports: {},
                memory_budget_mb=256,
                memory_reader=lambda: 300 * 1024 * 1024,
            )
            try:
                with mock.patch.object(runtime.live_events, "compact") as compact:
                    health = runtime.health()
                    self.assertTrue(health["memory"]["pressure"])
                    self.assertEqual(
                        health["memory"]["working_set_bytes"], 300 * 1024 * 1024
                    )
                    compact.assert_called_once_with(0.5)
            finally:
                runtime.close()

    def test_stable_exitlag_route_change_restarts_only_capture(self):
        current = {
            "value": {
                "projectrf.exe": ({10}, {51000}, set()),
            }
        }
        with tempfile.TemporaryDirectory() as folder:
            runtime = StandaloneWindowsAgentRuntime.create_offline(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                local_api_port=0,
                capture_factory=_FakeCapture,
                process_reader=lambda _ports: current["value"],
                route_change_confirmations=2,
                route_restart_cooldown_seconds=0,
            )
            try:
                runtime.start_capture()
                session_id = runtime.session_id
                first_capture = runtime.live_capture
                first_capture.received_packets = 7
                first_capture.packets = 3
                runtime.live_events.processed_packets = 5
                runtime.live_events.decoded_events = 2

                current["value"] = {
                    "projectrf.exe": ({10}, {52000}, set()),
                }
                first = runtime.refresh_routes()
                second = runtime.refresh_routes()

                self.assertFalse(first["capture_restarted"])
                self.assertTrue(second["capture_restarted"])
                self.assertTrue(first_capture.stopped)
                self.assertIsNot(runtime.live_capture, first_capture)
                self.assertIn(52000, runtime.live_capture.ports)
                self.assertEqual(runtime.session_id, session_id)
                self.assertEqual(runtime.health()["capture"]["route_restarts"], 1)
                self.assertEqual(runtime.health()["capture"]["received_packets"], 7)
                self.assertEqual(runtime.health()["capture"]["packets"], 3)
                self.assertTrue(runtime.live_events.metrics()["worker_alive"])
                self.assertEqual(runtime.live_events.metrics()["processed_packets"], 5)
                self.assertEqual(runtime.live_events.metrics()["decoded_events"], 2)
            finally:
                runtime.close()

    def test_failed_route_restart_restores_previous_capture(self):
        current = {
            "value": {"projectrf.exe": ({10}, {51000}, set())}
        }
        created = []

        def factory(target, ports):
            capture = _FakeCapture(target, ports)
            capture.fail_start = len(created) == 1
            created.append(capture)
            return capture

        with tempfile.TemporaryDirectory() as folder:
            runtime = StandaloneWindowsAgentRuntime.create_offline(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                local_api_port=0,
                capture_factory=factory,
                process_reader=lambda _ports: current["value"],
                route_change_confirmations=2,
                route_restart_cooldown_seconds=0,
            )
            try:
                runtime.start_capture()
                current["value"] = {
                    "projectrf.exe": ({10}, {52000}, set())
                }
                runtime.refresh_routes()
                result = runtime.refresh_routes()

                self.assertFalse(result["capture_restarted"])
                self.assertTrue(runtime.active)
                self.assertEqual(runtime.live_capture.ports, created[0].ports)
                self.assertIn("captura anterior restaurada", runtime.last_error)
                self.assertEqual(len(created), 3)
            finally:
                runtime.close()

    def test_local_health_exposes_capture_counters_without_packets(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(folder, lambda _ports: _processes(101))
            try:
                runtime.start_capture()
                runtime.live_capture.received_packets = 12
                runtime.live_capture.packets = 4
                runtime.live_capture.filtered_packets = 3
                runtime.live_capture.backend = "pktmon-etw"
                runtime.live_capture.property_errors = 2
                health = runtime.service.api._health()

                self.assertEqual(health["capture_state"], "capturing")
                self.assertTrue(health["session_active"])
                self.assertEqual(health["capture"]["received_packets"], 12)
                self.assertEqual(health["capture"]["packets"], 4)
                self.assertEqual(health["capture"]["filtered_packets"], 3)
                self.assertEqual(health["capture"]["backend"], "pktmon-etw")
                self.assertEqual(health["capture"]["property_errors"], 2)
                self.assertIn("decoded_events", health["decoder"])
                serialized = json.dumps(health).lower()
                self.assertNotIn("packet_bytes", serialized)
                self.assertNotIn('"source"', serialized)
                self.assertNotIn('"flow"', serialized)
            finally:
                runtime.close()

    def test_failed_etw_consumer_stops_reporting_active_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            runtime = self._runtime(folder, lambda _ports: _processes(101, 202))
            try:
                runtime.start_capture()
                failed = runtime.live_capture
                failed.last_error = "O stream Pktmon/ETW encerrou (5)."
                runtime.refresh_routes()
                self.assertFalse(runtime.active)
                self.assertTrue(failed.stopped)
                self.assertEqual(runtime.last_error, failed.last_error)
                self.assertFalse(runtime.health()["session_active"])
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()
