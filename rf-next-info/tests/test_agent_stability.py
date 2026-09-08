"""Regression checks from the beta.45 audit; all capture/network is synthetic."""
import sqlite3
import tempfile
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.agent_main import AgentWindow
from core.live_stream import LiveEventDecoder, LiveEventStream
from core.connections import agent_processes
from core.pktmon_etw import PktmonEtwCapture, INVALID_TRACE
from core.web_agent_authorization import AgentAuthorizationManager
from core.web_agent_transport import AgentDeliveryWorker
from core.windows_agent_capture import StandaloneWindowsAgentRuntime
from tests.test_equipment_delivery import equipment_frames, equipment_packet
from tests.test_windows_agent_capture import _FakeCapture


@contextmanager
def runtime_fixture(factory=_FakeCapture):
    routes = {"local": {51000, 51001}, "remote": {12020}}
    with tempfile.TemporaryDirectory() as folder:
        runtime = StandaloneWindowsAgentRuntime.create_offline(
            Path(folder), str(uuid.uuid4()), version="test", local_api_port=0,
            capture_factory=factory,
            process_reader=lambda *_: {"ProjectRF.exe": ({10, 11}, routes["local"] if not routes["remote"] else set(), routes["remote"])},
            route_alias_reader=lambda *_: {}, memory_reader=lambda: 0,
            route_change_confirmations=2, route_restart_cooldown_seconds=0,
        )
        try:
            yield runtime, routes
        finally:
            if runtime.live_capture:
                runtime.live_capture.fail_stop = False
            runtime.close()


def packet(frame=b"", sequence=100, port=50000, flags=0x18):
    raw = bytearray(equipment_packet(frame, sequence & 0xFFFFFFFF, port))
    raw[46:48] = (0x5000 | flags).to_bytes(2, "big")
    return bytes(raw)


class AgentStabilityTest(unittest.TestCase):
    def test_tcp_wrap_keeps_both_clients_decoding_and_ignores_duplicates(self):
        decoder = LiveEventDecoder()
        for port, uid in ((50000, 101), (50001, 202)):
            frame = equipment_frames(1004, character_uid=uid)[0]
            before = packet(frame, 2**32 - len(frame), port)
            self.assertEqual(len(decoder.feed(1, before)), 1)
            self.assertEqual(decoder.feed(2, before), [])
            for index in range(5):
                events = decoder.feed(3 + index, packet(frame, index * len(frame), port))
                self.assertEqual(events[0]["data"]["fields"]["character_uid"], uid)
            self.assertEqual(decoder.feed(10, before), [])
        self.assertEqual(decoder.flow_count, 2)

    def test_wrap_with_split_reordered_and_overlapping_segments(self):
        frame = equipment_frames(1004)[0]
        decoder = LiveEventDecoder()
        self.assertEqual(decoder.feed(1, packet(frame[:10], 2**32 - 10)), [])
        self.assertEqual(decoder.feed(2, packet(frame[20:], 10)), [])
        events = decoder.feed(3, packet(frame[5:24], 2**32 - 5))
        self.assertEqual(len(events), 1)
        self.assertEqual(decoder.pending_bytes, 0)
        self.assertEqual(decoder.gap_recoveries, 0)

    def test_new_syn_resets_only_reused_socket_and_retransmitted_syn_does_not(self):
        frame = equipment_frames(1004)[0]
        decoder = LiveEventDecoder()
        decoder.feed(1, packet(frame, 10000))
        decoder.feed(2, packet(frame, 20000, 50001))
        self.assertEqual(decoder.feed(3, packet(sequence=100, flags=0x02)), [])
        self.assertEqual(decoder.feed(4, packet(frame[:10], 101)), [])
        decoder.feed(5, packet(sequence=100, flags=0x02))
        self.assertEqual(len(decoder.feed(6, packet(frame[10:], 111))), 1)
        self.assertEqual(len(decoder.feed(7, packet(frame, 20000 + len(frame), 50001))), 1)

    def test_reset_and_fin_release_flow_without_resetting_other_client(self):
        frame = equipment_frames(1004)[0]
        for flag in (0x04, 0x01):
            decoder = LiveEventDecoder()
            decoder.feed(1, packet(frame, 10000))
            decoder.feed(2, packet(frame, 20000, 50001))
            decoder.feed(3, packet(sequence=10000 + len(frame), flags=flag))
            self.assertEqual(decoder.flow_count, 1 if flag == 0x04 else 2)
            decoder.feed(4, packet(sequence=100, flags=0x02))
            self.assertEqual(len(decoder.feed(4, packet(frame, 101))), 1)
            self.assertEqual(len(decoder.feed(5, packet(frame, 20000 + len(frame), 50001))), 1)

    def test_out_of_order_fin_drains_gap_and_deduplicates_last_frame(self):
        decoder = LiveEventDecoder()
        frame = equipment_frames(1004)[0]
        self.assertEqual(decoder.feed(1, packet(frame[:10], 100)), [])
        tail = packet(frame[20:], 120, flags=0x19)
        self.assertEqual(decoder.feed(2, tail), [])
        self.assertEqual(len(decoder.feed(3, packet(frame[10:20], 110))), 1)
        self.assertEqual(decoder.feed(4, tail), [])
        self.assertEqual(decoder.feed(5, packet(frame, 100, flags=0x19)), [])

    def test_capture_cleanup_failure_never_reports_active_or_double_counts(self):
        class StopFailure(_FakeCapture):
            fail_stop = False

            def stop(self):
                super().stop()
                if self.fail_stop:
                    raise RuntimeError("synthetic stop failure")

        with runtime_fixture(StopFailure) as (runtime, routes):
            routes["remote"] = set()
            runtime.start_capture()
            session_id = runtime.session_id
            previous = runtime.live_capture
            previous.packets = 7
            previous.fail_stop = True
            routes["local"] = {52000, 52001}
            runtime.refresh_routes()
            with self.assertRaises(RuntimeError):
                runtime.refresh_routes()
            self.assertFalse(runtime.active)
            self.assertEqual(runtime.health()["capture"]["packets"], 7)
            self.assertIn("pendente", runtime.last_error)
            self.assertIs(runtime.live_capture, previous)
            previous.fail_stop = False
            runtime.refresh_routes()
            self.assertTrue(runtime.active)
            self.assertEqual(runtime.session_id, session_id)
            self.assertEqual(runtime.health()["capture"]["packets"], 7)

    def test_hundreds_of_port_changes_are_bounded_for_two_clients(self):
        with runtime_fixture() as (runtime, routes):
            runtime.start_capture()
            original = runtime.live_capture
            session = runtime.session_id
            for index in range(200):
                routes["local"] = {51000 + index * 2, 51001 + index * 2}
                runtime.refresh_routes()
                runtime.refresh_routes()
            self.assertIs(runtime.live_capture, original)
            self.assertEqual(runtime.health()["capture"]["route_restarts"], 0)
            self.assertEqual(runtime.session_id, session)
            routes["remote"] = set()
            for index in range(40):
                routes["local"] = {54000 + index * 2, 54001 + index * 2}
                runtime.refresh_routes()
                runtime.refresh_routes()
                self.assertLessEqual(len(runtime._capture_ports), len(runtime.ports) + 2)

    def test_filter_limit_is_checked_before_stopping_existing_capture(self):
        with runtime_fixture() as (runtime, _):
            runtime.start_capture()
            original = runtime.live_capture
            original.max_filter_ports = 32
            with self.assertRaisesRegex(RuntimeError, "32"):
                runtime._restart_capture_for_routes(tuple(range(100, 133)))
            self.assertTrue(runtime.active)
            self.assertFalse(original.stopped)
        capture = PktmonEtwCapture(None, (12020,))
        with patch.object(capture, "_command") as command:
            with self.assertRaisesRegex(RuntimeError, "32"):
                capture._add_filters(tuple(range(100, 133)))
            command.assert_not_called()

    def test_mixed_direct_and_relay_clients_keep_both_routes(self):
        rows = [(10, 51000, 12020), (11, 51001, 9001), (11, 51002, 443)]
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", return_value=r"C:\RF\ProjectRF.exe"
        ):
            processes = agent_processes((12020,))
        pids, ports = StandaloneWindowsAgentRuntime._capture_routes(processes, (12020,))
        self.assertEqual(pids, (10, 11))
        self.assertEqual(ports, (12020, 51001))

    def test_cleanup_attempts_trace_and_filters_even_when_terminate_fails(self):
        capture = PktmonEtwCapture(None, (12020,))
        capture._process = Mock()
        capture._process.poll.return_value = None
        capture._process.terminate.side_effect = OSError("synthetic")
        capture._trace = 123
        capture._etw = Mock()
        capture._etw.CloseTrace.return_value = 0
        capture._filters = ["synthetic-owned"]
        def command(*args):
            if args == ("stop",):
                raise RuntimeError("synthetic")
            return b""
        with patch.object(capture, "_command", side_effect=command) as calls:
            with self.assertRaises(RuntimeError):
                capture.stop()
            capture._etw.CloseTrace.assert_called_once_with(123)
            self.assertEqual(capture._trace, INVALID_TRACE)
            self.assertEqual(capture._filters, [])
            self.assertIsNotNone(capture._process)
            calls.assert_any_call("filter", "remove", "synthetic-owned")

    def test_close_pending_retains_callback_until_consumer_exits(self):
        capture = PktmonEtwCapture(None, (12020,))
        capture._trace = 123
        capture._etw = Mock()
        capture._etw.CloseTrace.return_value = 7007
        consumer = Mock()
        consumer.is_alive.return_value = True
        capture._consumer = consumer
        with self.assertRaises(RuntimeError):
            capture.stop()
        self.assertEqual(capture._trace, INVALID_TRACE)
        self.assertIs(capture._consumer, consumer)
        consumer.is_alive.return_value = False
        capture.stop()
        self.assertIsNone(capture._consumer)
        capture._etw.CloseTrace.assert_called_once()

    def test_factory_start_failure_cleans_session_and_decoder(self):
        def fail(*_):
            raise RuntimeError("synthetic factory failure")
        with runtime_fixture(fail) as (runtime, _):
            with self.assertRaisesRegex(RuntimeError, "factory"):
                runtime.start_capture()
            self.assertFalse(runtime.live_events.metrics()["worker_alive"])
            self.assertFalse(runtime.service.runtime._session_active)
            self.assertIsNone(runtime.session_id)
            self.assertIn("factory", runtime.last_error)

    def test_failed_stop_keeps_session_for_retry_and_does_not_auto_restart(self):
        for target in ("decoder", "session"):
            with self.subTest(target=target), runtime_fixture() as (runtime, _):
                runtime.start_capture()
                session_id = runtime.session_id
                owner, method = (runtime.live_events, "stop") if target == "decoder" else (runtime.service, "pause_session")
                with patch.object(owner, method, side_effect=RuntimeError("synthetic")):
                    with self.assertRaises(RuntimeError):
                        runtime.stop_capture()
                self.assertEqual(runtime.session_id, session_id)
                self.assertTrue(runtime.health()["session_stopping"])
                self.assertFalse(runtime.refresh_routes()["capture_authorized"])
                self.assertIsNone(runtime.live_capture)
                with self.assertRaises(RuntimeError):
                    runtime.start_capture()
                runtime.stop_capture()
                self.assertIsNone(runtime.session_id)
                self.assertFalse(runtime.health()["session_stopping"])
                runtime.start_capture()
                self.assertNotEqual(runtime.session_id, session_id)

    def test_poll_error_is_visible_without_releasing_other_commands(self):
        window = SimpleNamespace(_poll_pending=True, message=Mock(), state_label=Mock(), _set_busy=Mock())
        AgentWindow._command_failed(window, "poll", "synthetic error")
        self.assertFalse(window._poll_pending)
        self.assertEqual(window._poll_error, "synthetic error")
        self.assertIn("desatualizada", window.message.setText.call_args.args[0])
        window._set_busy.assert_not_called()

    def test_stop_drains_accepted_packets_and_counts_late_input(self):
        stream = LiveEventStream()
        entered, release = Event(), Event()
        failures = []
        def decode(*_):
            entered.set()
            self.assertTrue(release.wait(5))
            return []
        def stop():
            try:
                stream.stop()
            except Exception as error:
                failures.append(error)
        with patch.object(stream._decoder, "feed", side_effect=decode):
            stream.start()
            stopper = None
            try:
                for index in range(3):
                    stream.feed(index, b"synthetic")
                self.assertTrue(entered.wait(2))
                stopper = Thread(target=stop)
                stopper.start()
                self.assertTrue(stream._worker_stop.wait(2))
                stream.feed(4, b"late")
            finally:
                release.set()
                if stopper:
                    stopper.join(5)
                stream.stop()
        self.assertEqual(failures, [])
        self.assertEqual(stream.processed_packets, 3)
        self.assertEqual(stream.dropped_packets, 1)

    def test_runtime_health_is_available_during_authorization_network_wait(self):
        with runtime_fixture() as (runtime, _):
            entered, release, completed = Event(), Event(), Event()
            def authorize():
                entered.set()
                self.assertTrue(release.wait(5))
                return True
            with patch.object(runtime.service, "refresh_authorization", side_effect=authorize):
                poll = Thread(target=runtime.refresh_routes)
                reader = Thread(target=lambda: (runtime.health(), completed.set()))
                try:
                    poll.start()
                    self.assertTrue(entered.wait(2))
                    reader.start()
                    self.assertTrue(completed.wait(1))
                finally:
                    release.set()
                    poll.join(5)
                    if reader.ident:
                        reader.join(5)

    def test_local_busy_is_retryable_but_corruption_stays_blocked(self):
        for error, blocked in ((sqlite3.OperationalError("database is locked"), False),
                               (sqlite3.DatabaseError("database disk image is malformed"), True)):
            outbox = Mock(installation_id="test")
            transport = SimpleNamespace(identity=SimpleNamespace(installation_id="test"))
            worker = AgentDeliveryWorker(outbox, transport)
            worker._registration_state = "active"
            outbox.pending_priorities.side_effect = error
            worker.send_once()
            self.assertEqual(worker._blocked, blocked)
            outbox.pending_priorities.side_effect = None
            outbox.pending_priorities.return_value = []
            outbox.next_batch.return_value = None
            worker.send_once()
            self.assertEqual(outbox.pending_priorities.call_count, 1 if blocked else 2)

    def test_authorization_manager_health_does_not_wait_for_http(self):
        entered, release, completed = Event(), Event(), Event()
        store = Mock()
        store.load.return_value = None
        def authorize():
            entered.set()
            release.wait(5)
            return SimpleNamespace(status="pending", username=None, pairing_code=None)
        manager = AgentAuthorizationManager(SimpleNamespace(authorize=authorize), store)
        writer = Thread(target=manager.refresh)
        reader = Thread(target=lambda: (manager.health(), completed.set()))
        try:
            writer.start()
            self.assertTrue(entered.wait(2))
            reader.start()
            self.assertTrue(completed.wait(1))
        finally:
            release.set()
            writer.join(5)
            if reader.ident:
                reader.join(5)
        self.assertFalse(manager.health()["authorized"])


if __name__ == "__main__":
    unittest.main()
