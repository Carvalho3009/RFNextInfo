from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

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
        registry = AgentClientRegistry(max_clients=1)
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
        }])
        registry.observe({
            "type": "session.lifecycle", "payload": {"state": "started"}
        })
        self.assertEqual(registry.snapshot(), [])


class StandaloneWindowsAgentRuntimeTest(unittest.TestCase):
    def _runtime(self, folder: str, reader, **options):
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
                    runtime.service.runtime.bridge.metrics()["outbox_events"], 2
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


if __name__ == "__main__":
    unittest.main()
