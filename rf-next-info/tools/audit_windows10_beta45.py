"""Offline fault probes for the beta.45 audit, not a product regression suite.

Run from rf-next-info: python -m tools.audit_windows10_beta45
Uses synthetic packets, temporary state and mocked native capture. No HTTP,
Pktmon command, UI interaction or real character data. A reproduced=True
means the defect was observed, NOT that the application passed validation.
"""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch
import json
import platform
import sqlite3
import uuid

from app.agent_main import AgentWindow
from core.live_stream import LiveEventDecoder, LiveEventStream
from core.pktmon_etw import PktmonEtwCapture
from core.web_agent_transport import AgentDeliveryWorker
from core.windows_agent_capture import StandaloneWindowsAgentRuntime
from tests.test_equipment_delivery import equipment_frames, equipment_packet
from tests.test_windows_agent_capture import _FakeCapture


@contextmanager
def offline(factory=_FakeCapture):
    routes = {"ports": {51000, 51001}}
    with TemporaryDirectory(prefix="rfqol-win10-audit-") as folder:
        runtime = StandaloneWindowsAgentRuntime.create_offline(
            Path(folder), str(uuid.uuid4()), version="audit-only",
            local_api_port=0, capture_factory=factory,
            process_reader=lambda *_: {"ProjectRF.exe": ({10, 11}, routes["ports"], {12020})},
            route_alias_reader=lambda *_: {}, memory_reader=lambda: 0,
            route_change_confirmations=2, route_restart_cooldown_seconds=0,
        )
        try:
            yield runtime, routes
        finally:
            if runtime.live_capture is not None:
                runtime.live_capture.fail_stop = False
            runtime.close()


def tcp_sequences():
    frame = equipment_frames(1004)[0]  # synthetic, public character identity only
    results = {}
    for name, start, next_seq, reconnect in (
        ("TCP_WRAP", 2**32 - len(frame), 0, False),
        ("TCP_RECONNECT", 10000, 101, True),
    ):
        decoder = LiveEventDecoder()
        first = decoder.feed(1, equipment_packet(frame, start, 50000))
        if reconnect:
            syn = bytearray(equipment_packet(b"", 100, 50000))
            syn[46:48] = (0x5002).to_bytes(2, "big")
            decoder.feed(2, bytes(syn))
        after = sum(len(decoder.feed(3 + i, equipment_packet(
            frame, next_seq + i * len(frame), 50000))) for i in range(5))
        fresh = LiveEventDecoder().feed(3, equipment_packet(frame, next_seq, 50000))
        # Another client continues: this fault is per TCP flow, not global.
        other = decoder.feed(9, equipment_packet(frame, 100, 50001))
        results[name] = {
            "reproduced": len(first) == 1 and after == 0 and len(fresh) == 1,
            "first_events": len(first), "events_next_five_valid_frames": after,
            "same_frame_fresh_decoder": len(fresh), "other_client_events": len(other),
            "reported_stalled_flows": decoder.stalled_flow_count,
        }
    return results


def route_stop_failure():
    class StopFailure(_FakeCapture):
        fail_stop = False

        def stop(self):
            super().stop()
            if self.fail_stop:
                raise RuntimeError("synthetic stop failure")

    with offline(StopFailure) as (runtime, routes):
        runtime.start_capture()
        previous = runtime.live_capture
        previous.packets = 7
        previous.fail_stop = True
        routes["ports"] = {52000, 51001}
        runtime.refresh_routes()
        error = None
        try:
            runtime.refresh_routes()
        except RuntimeError as exc:
            error = str(exc)
        health = runtime.health()
        return {"reproduced": bool(error) and previous.stopped and runtime.active,
                "old_capture_stopped": previous.stopped, "state": health["state"],
                "last_error": health["last_error"], "actual_packets": 7,
                "reported_packets": health["capture"]["packets"]}


def route_filter_limit():
    attempts = []

    class FilterLimit(_FakeCapture):
        def start(self):
            attempts.append(len(self.ports))
            if len(self.ports) > 32:  # documented native Pktmon global limit
                raise RuntimeError("synthetic native 32-filter limit")
            super().start()

    with offline(FilterLimit) as (runtime, routes):
        runtime.start_capture()
        for i in range(1, 39):
            routes["ports"] = {51000 + i * 2, 51001 + i * 2}
            runtime.refresh_routes()
            runtime.refresh_routes()
        active_ports = runtime._capture_ports
        failures = sum(count > 32 for count in attempts)
        return {"reproduced": failures > 1 and 51000 in active_ports,
                "modeled_limit": 32, "start_attempts": len(attempts),
                "failed_attempts": failures, "max_requested_ports": max(attempts),
                "initial_obsolete_port_retained": 51000 in active_ports,
                "remaining_filter_ports": len(active_ports),
                "runtime_active_after_fallback": runtime.active}


def cleanup_failure():
    capture = PktmonEtwCapture(None, (12020,))
    capture._process = Mock()
    capture._process.poll.return_value = None
    capture._process.terminate.side_effect = OSError("synthetic termination failure")
    capture._etw = Mock()
    capture._trace = 123
    capture._filters = ["synthetic-owned-filter"]
    with patch.object(capture, "_command", side_effect=RuntimeError("synthetic stop failure")) as command:
        try:
            capture.stop()
        except OSError:
            pass
        return {"reproduced": not capture._etw.CloseTrace.called and len(capture._filters) == 1,
                "close_trace_called": capture._etw.CloseTrace.called,
                "remaining_owned_filters": len(capture._filters),
                "mocked_commands": [call.args for call in command.call_args_list]}


def hidden_poll_error():
    window = SimpleNamespace(_poll_pending=True, message=Mock(), _set_busy=Mock())
    AgentWindow._command_failed(window, "poll", "synthetic capture stopped")
    return {"reproduced": not window.message.setText.called,
            "error_shown": window.message.setText.called,
            "poll_pending": window._poll_pending}


def queued_stop_loss():
    stream = LiveEventStream()
    entered, release = Event(), Event()

    def decode(*_):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("audit synchronization timed out")
        return []

    with patch.object(stream._decoder, "feed", side_effect=decode):
        stream.start()
        stopper = None
        try:
            for i in range(3):
                stream.feed(i, b"synthetic")
            assert entered.wait(2), "worker did not start"
            stopper = Thread(target=stream.stop)
            stopper.start()
            assert stream._worker_stop.wait(2), "stop not requested"
        finally:
            release.set()
            if stopper:
                stopper.join(5)
            stream.stop()
    return {"reproduced": stream.processed_packets == 1 and stream.dropped_packets == 0,
            "packets_submitted": 3, "packets_processed": stream.processed_packets,
            "reported_drops": stream.dropped_packets, "remaining_queue": stream._items.qsize()}


def health_lock_delay():
    with offline() as (runtime, _):
        entered, release, started, completed = Event(), Event(), Event(), Event()

        def slow_authorization():
            entered.set()
            if not release.wait(5):
                raise RuntimeError("audit synchronization timed out")
            return True

        def read_health():
            started.set()
            runtime.health()
            completed.set()

        with patch.object(runtime.service, "refresh_authorization", side_effect=slow_authorization):
            poll = Thread(target=runtime.refresh_routes)
            reader = Thread(target=read_health)
            try:
                poll.start()
                assert entered.wait(2)
                reader.start()
                assert started.wait(2)
                blocked = not completed.wait(0.1)
            finally:
                release.set()
                poll.join(5)
                if reader.ident:
                    reader.join(5)
        return {"reproduced": blocked and completed.is_set(),
                "runtime_health_waited_for_authorization": blocked,
                "recovered_after_authorization": completed.is_set()}


def factory_start_failure():
    def fail(*_):
        raise RuntimeError("synthetic capture factory failure")

    with offline(fail) as (runtime, _):
        try:
            runtime.start_capture()
        except RuntimeError:
            pass
        worker_alive = bool(runtime.live_events._thread and runtime.live_events._thread.is_alive())
        session_active = runtime.service.runtime._session_active
        return {"reproduced": worker_alive and session_active and runtime.session_id is None,
                "decoder_worker_alive": worker_alive,
                "service_session_active": session_active,
                "runtime_session_recorded": runtime.session_id is not None}


def transient_delivery_failure():
    outbox = Mock(installation_id="audit")
    transport = SimpleNamespace(identity=SimpleNamespace(installation_id="audit"))
    worker = AgentDeliveryWorker(outbox, transport)
    worker._registration_state = "active"
    outbox.pending_priorities.side_effect = sqlite3.OperationalError("database is locked")
    worker.send_once()
    outbox.pending_priorities.side_effect = None
    outbox.pending_priorities.return_value = []
    worker.send_once()
    return {"reproduced": worker._blocked and outbox.pending_priorities.call_count == 1,
            "state": worker.metrics()["state"], "error": worker.last_error_code,
            "database_retried_after_recovery": outbox.pending_priorities.call_count > 1}


def main():
    from app.build_profile import APP_VERSION
    if APP_VERSION != "2.0.0-beta.45":
        raise SystemExit("Historical beta.45 probes only; use tests.test_agent_stability on newer versions.")
    results = {
        **tcp_sequences(), "ROUTE_STOP_FAILURE": route_stop_failure(),
        "NATIVE_FILTER_LIMIT": route_filter_limit(), "CLEANUP_FAILURE": cleanup_failure(),
        "HIDDEN_POLL_ERROR": hidden_poll_error(), "QUEUED_STOP_LOSS": queued_stop_loss(),
        "HEALTH_LOCK_DELAY": health_lock_delay(), "FACTORY_START_FAILURE": factory_start_failure(),
        "TRANSIENT_DELIVERY_FAILURE": transient_delivery_failure(),
    }
    print(json.dumps({"audit_target": "2.0.0-beta.45", "host": platform.platform(),
                      "synthetic_only": True, "findings": results}, indent=2))
    assert all(result["reproduced"] for result in results.values()), "baseline changed: reassess findings"


if __name__ == "__main__":
    main()
