from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.ui_qt.operations import CaptureEngine
from core.live_stream import LiveEventStream
from core.web_agent import (
    AgentOutbox,
    OutboxFullError,
    WebAgentBridge,
    WebEventContractError,
    WebEventProjector,
)


def decoded_event(
    kind: str,
    data: dict,
    *,
    offset: int = 1,
    flow: str = "10.0.0.1:50000 -> 10.0.0.2:12020",
    opcode: int = 0x0307,
) -> dict:
    return {
        "source": "captura-local.pcap",
        "flow": flow,
        "stream_offset": offset,
        "bundle_seq": 0,
        "ts_ns": 1_700_000_000_000_000_000 + offset,
        "opcode": opcode,
        "type": kind,
        "data": data,
    }


def assert_no_forbidden_keys(test: unittest.TestCase, value: object) -> None:
    forbidden = {
        "account_id", "auth_uid", "flow", "item_id", "login_uid", "opcode",
        "packet", "password", "pc_id", "port", "private_key", "secret",
        "session_uid", "source", "source_pcap", "ticket", "token",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            test.assertNotIn(normalized, forbidden)
            test.assertFalse(normalized.endswith("_raw"))
            test.assertFalse(normalized.endswith("_hex"))
            assert_no_forbidden_keys(test, item)
    elif isinstance(value, list):
        for item in value:
            assert_no_forbidden_keys(test, item)


class WebEventProjectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.projector = WebEventProjector(
            "install-publica", b"0123456789abcdef0123456789abcdef",
            decoder_version="2.0.0-beta.6",
        )

    def identity_event(self, *, offset: int = 1) -> dict:
        return decoded_event(
            "world_info_prefix",
            {"fields": {
                "character_uid": 123456789,
                "character_name": "Personagem",
                "level": 66,
                "biosuit_item_index": 7001,
                "opaque_tail_raw": "nao-pode-sair",
            }},
            offset=offset,
            opcode=0x0106,
        )

    def test_projects_identity_and_reuses_opaque_client_reference(self):
        identity = self.projector.project(self.identity_event(), "sessao-1")
        exp = self.projector.project(decoded_event(
            "update_exp",
            {
                "action_code": 1, "before_level": 66, "level": 66,
                "highest_level": 66, "exp": 123_000, "gain_exp": 4_500,
            },
            offset=2,
            flow="10.0.0.2:12020 -> 10.0.0.1:50000",
        ), "sessao-1")

        self.assertEqual(identity["type"], "character.observed")
        self.assertEqual(identity["payload"]["character_uid"], 123456789)
        self.assertEqual(identity["payload"]["name"], "Personagem")
        self.assertEqual(identity["client_ref"], exp["client_ref"])
        self.assertEqual(identity["stream_id"], exp["stream_id"])
        self.assertEqual(identity["session_ref"], exp["session_ref"])
        self.assertEqual(exp["payload"]["gained_exp"], 4_500)
        self.assertNotIn("sessao-1", json.dumps(identity))
        assert_no_forbidden_keys(self, identity)

    def test_exports_confirmed_character_uid_but_rejects_session_uid(self):
        identity = self.projector.project(self.identity_event(), "sessao-1")
        self.assertEqual(identity["payload"]["character_uid"], 123456789)

        unsafe = json.loads(json.dumps(identity))
        unsafe["payload"]["session_uid"] = 987654321
        with self.assertRaises(WebEventContractError):
            from core.web_agent import _validate_event_contract
            _validate_event_contract(unsafe)

    def test_player_appearance_exports_uid_for_site_directory_sync(self):
        projected = self.projector.project(decoded_event(
            "appear_player_list",
            {"units": [{
                "uid": 77,
                "character_uid": 987654321,
                "name": "Jogador",
                "level": 65,
                "guild_id": 44,
                "guild_name": "Blood",
                "position": [10, 20, 30],
            }]},
            opcode=0x0306,
        ), "sessao-1")

        player = projected["payload"]["entities"][0]
        self.assertEqual(player["character_uid"], 987654321)
        self.assertEqual(player["name"], "Jogador")
        self.assertEqual(player["guild_id"], 44)
        self.assertEqual(player["guild_name"], "Blood")
        self.assertNotEqual(player["player_ref"], "987654321")
        assert_no_forbidden_keys(self, projected)

    def test_event_without_confirmed_identity_is_not_claimed(self):
        event = decoded_event(
            "update_exp", {"exp": 10, "gain_exp": 10}, flow="outro-fluxo"
        )
        self.assertIsNone(self.projector.project(event, "sessao-1")["client_ref"])

    def test_finished_session_does_not_leak_identity_into_later_events(self):
        self.projector.project(self.identity_event(), "sessao-1")
        self.projector.finish_session("sessao-1")
        event = decoded_event("update_exp", {"exp": 10, "gain_exp": 10})
        self.assertIsNone(self.projector.project(event, "sessao-1")["client_ref"])

    def test_combat_replaces_every_uid_with_session_scoped_reference(self):
        projected = self.projector.project(decoded_event(
            "use_skill_result",
            {
                "ret": 0,
                "caster_uid": 101,
                "main_target_uid": 202,
                "skill_index": 55,
                "effect_results": [{
                    "uid": 202, "shield_damage": 1, "hp_damage": 900,
                    "final_hp": 100, "target_x": 1.5,
                }],
            },
            opcode=0x0602,
        ), "sessao-1")

        payload = projected["payload"]
        self.assertEqual(payload["target_ref"], payload["effects"][0]["entity_ref"])
        self.assertEqual(payload["effects"][0]["hp_damage"], 900)
        self.assertNotIn("uid", json.dumps(projected).lower())
        assert_no_forbidden_keys(self, projected)

    def test_sensitive_opcode_and_unknown_type_are_rejected(self):
        with self.assertRaises(WebEventContractError):
            self.projector.project(decoded_event(
                "world_info_prefix", {}, opcode=0x0101
            ), "sessao-1")
        with self.assertRaises(WebEventContractError):
            self.projector.project(decoded_event("unparsed", {}), "sessao-1")

    def test_event_id_is_deterministic_for_retries(self):
        event = self.identity_event()
        first = self.projector.project(event, "sessao-1")
        second = self.projector.project(event, "sessao-1")
        self.assertEqual(first["event_id"], second["event_id"])

    def test_lifecycle_uses_same_opaque_session_reference(self):
        started = self.projector.project_lifecycle(
            "sessao-1", "started", occurred_ns=100
        )
        finished = self.projector.project_lifecycle(
            "sessao-1", "finished", reason="finalized", occurred_ns=200
        )
        decoded = self.projector.project(self.identity_event(), "sessao-1")

        self.assertEqual(started["session_ref"], finished["session_ref"])
        self.assertEqual(started["session_ref"], decoded["session_ref"])
        self.assertEqual(started["payload"], {"state": "started"})
        self.assertEqual(
            finished["payload"], {"state": "finished", "reason": "finalized"}
        )
        self.assertNotIn("sessao-1", json.dumps([started, finished]))
        assert_no_forbidden_keys(self, started)

    def test_identity_context_is_bounded_for_long_running_agent(self):
        for index in range(300):
            event = self.identity_event(offset=index + 1)
            event["flow"] = f"10.0.0.1:{50000 + index} -> 10.0.0.2:12020"
            event["data"]["fields"]["character_uid"] = 1_000_000 + index
            self.projector.project(event, f"sessao-{index}")
        self.assertEqual(len(self.projector._flow_clients), 256)


class AgentOutboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "agent-outbox.sqlite3"
        self.projector = WebEventProjector(
            "install-publica", b"0123456789abcdef0123456789abcdef",
            decoder_version="test",
        )

    def tearDown(self) -> None:
        self.folder.cleanup()

    def event(self, offset: int) -> dict:
        return self.projector.project(decoded_event(
            "update_exp", {"exp": offset * 100, "gain_exp": 100}, offset=offset
        ), "sessao-1")

    def test_deduplicates_persists_and_supports_partial_ack(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=10)
        events = [self.event(index) for index in (1, 2, 3)]
        for event in events:
            self.assertTrue(outbox.enqueue(event))
        self.assertFalse(outbox.enqueue(events[0]))
        batch = outbox.next_batch()
        self.assertEqual([item["sequence"] for item in batch["events"]], [1, 2, 3])
        self.assertEqual(outbox.acknowledge(batch["batch_id"], 2), 2)
        self.assertEqual(outbox.metrics()["events"], 1)
        outbox.close()

        reopened = AgentOutbox(self.path, "install-publica", max_events=10)
        remaining = reopened.next_batch()
        self.assertEqual(remaining["events"][0]["event_id"], events[2]["event_id"])
        reopened.close()

    def test_full_limit_never_deletes_existing_event(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=1)
        outbox.enqueue(self.event(1))
        with self.assertRaises(OutboxFullError):
            outbox.enqueue(self.event(2))
        self.assertEqual(outbox.metrics()["events"], 1)
        outbox.close()

    def test_external_contract_with_secret_is_rejected(self):
        outbox = AgentOutbox(self.path, "install-publica")
        event = self.event(1)
        event["payload"]["token"] = "segredo"
        with self.assertRaises(WebEventContractError):
            outbox.enqueue(event)
        self.assertEqual(outbox.metrics()["events"], 0)
        outbox.close()

    def test_external_contract_cannot_add_an_innocent_but_unknown_field(self):
        outbox = AgentOutbox(self.path, "install-publica")
        event = self.event(1)
        event["payload"]["diagnostic_note"] = "nao pertence ao schema"
        with self.assertRaises(WebEventContractError):
            outbox.enqueue(event)
        self.assertEqual(outbox.metrics()["events"], 0)
        outbox.close()

    def test_rejection_is_audited_without_payload(self):
        outbox = AgentOutbox(self.path, "install-publica")
        event = self.event(1)
        outbox.enqueue(event)
        self.assertTrue(outbox.reject(event["event_id"], "schema nao suportado"))
        row = outbox.conn.execute(
            "SELECT event_id,reason FROM outbox_rejections"
        ).fetchone()
        self.assertEqual(tuple(row), (event["event_id"], "schema nao suportado"))
        self.assertEqual(outbox.metrics()["events"], 0)
        outbox.close()


class WebAgentBridgeTest(unittest.TestCase):
    def test_local_observer_remains_independent_when_outbox_is_full(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica", max_events=1
            )
            bridge = WebAgentBridge(
                projector, outbox, event_observer=observed.append
            )
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=1
            )))
            bridge.wait_until_idle()

            self.assertEqual(
                [event["type"] for event in observed],
                ["session.lifecycle", "character.exp_changed"],
            )
            self.assertEqual(bridge.metrics()["outbox_events"], 1)
            self.assertEqual(bridge.metrics()["errors"], 1)
            self.assertEqual(bridge.metrics()["observer_errors"], 0)
            bridge.close()

    def test_local_observer_failure_never_blocks_outbox(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica"
            )
            bridge = WebAgentBridge(
                projector,
                outbox,
                event_observer=lambda _event: (_ for _ in ()).throw(
                    RuntimeError("falha local simulada")
                ),
            )
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=1
            )))
            bridge.wait_until_idle()

            self.assertEqual(bridge.metrics()["outbox_events"], 2)
            self.assertEqual(bridge.metrics()["errors"], 0)
            self.assertEqual(bridge.metrics()["observer_errors"], 2)
            bridge.close()

    def test_bridge_is_nonblocking_and_isolates_outbox_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica", max_events=2
            )
            bridge = WebAgentBridge(projector, outbox, max_queue_events=8)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=1
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 200, "gain_exp": 100}, offset=2
            )))
            self.assertFalse(bridge.submit(decoded_event("unparsed", {}, offset=3)))
            bridge.wait_until_idle()
            metrics = bridge.metrics()
            self.assertEqual(metrics["outbox_events"], 2)
            self.assertEqual(metrics["errors"], 1)
            self.assertEqual(metrics["ignored"], 1)
            bridge.close()

    def test_live_stream_sink_failure_never_reaches_local_decoder_state(self):
        calls = 0

        def sink(_event: dict) -> bool:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("falha simulada")
            return calls == 3

        stream = LiveEventStream(event_sink=sink)
        stream._dispatch_events([{}, {}, {}])
        metrics = stream.metrics()
        self.assertEqual(metrics["event_sink_errors"], 1)
        self.assertEqual(metrics["event_sink_rejected"], 1)
        self.assertEqual(metrics["event_sink_accepted"], 1)

    def test_session_finish_marker_runs_after_queued_events(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica"
            )
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 1,
                }},
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=2
            )))
            bridge.finish_session("sessao-1")
            bridge.wait_until_idle()

            batch = outbox.next_batch()
            self.assertEqual(len(batch["events"]), 4)
            self.assertEqual(
                [event["payload"].get("state") for event in batch["events"]],
                ["started", None, None, "finished"],
            )
            self.assertIsNotNone(batch["events"][2]["client_ref"])
            self.assertEqual(projector._flow_clients, {})
            bridge.close()

    def test_capture_engine_opt_in_tracks_separate_sessions(self):
        class License:
            def require(self, *_args):
                return {}

        class Capture:
            def __init__(self, directory):
                self.directory = Path(directory)
                self.active = False

            def system_running(self):
                return False

            def start_for_ports(self, _prefix, _ports):
                self.active = True

            def stop(self):
                self.active = False
                return SimpleNamespace(files=())

        class Live:
            def __init__(self, target, _ports):
                self.target = target

            def set_packet_sink(self, sink):
                self.sink = sink

            def start(self):
                pass

            def stop(self):
                pass

        class Bridge:
            def __init__(self):
                self.started = []
                self.finished = []

            def submit(self, _event):
                return True

            def start_session(self, session_id, *, resumed=False):
                self.started.append((session_id, resumed))

            def pause_session(self, session_id, *, reason="paused"):
                self.finished.append((session_id, reason))

            def finish_session(self, session_id, *, reason="finished"):
                self.finished.append((session_id, reason))

        with tempfile.TemporaryDirectory() as folder:
            bridge = Bridge()
            engine = CaptureEngine(
                Path(folder), Path(folder) / "desktop.sqlite3", License(),
                capture_factory=Capture,
                live_factory=Live,
                process_reader=lambda _ports: {
                    "ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: [{
                    "pid": 10, "local_ports": (50000,), "remote_ports": (12020,),
                }],
                web_agent=bridge,
            )
            first_result = engine.start()
            first = first_result["session_id"]
            self.assertEqual(first_result["web_agent_health"]["state"], "ready")
            paused = engine.stop_without_reading()
            self.assertTrue(paused["paused"])
            resumed = engine.start()
            self.assertTrue(resumed["resumed"])
            self.assertEqual(resumed["session_id"], first)
            engine.abandon()
            second = engine.start()["session_id"]
            engine.abandon()

            self.assertNotEqual(first, second)
            self.assertEqual(
                bridge.started,
                [(first, False), (first, True), (second, False)],
            )
            self.assertEqual(
                bridge.finished,
                [
                    (first, "capture_stopped_without_reading"),
                    (first, "abandoned"),
                    (second, "abandoned"),
                ],
            )

    def test_capture_engine_keeps_web_agent_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = CaptureEngine(
                Path(folder), Path(folder) / "desktop.sqlite3", object()
            )
            self.assertIsNone(engine.web_agent)
            self.assertIsNone(engine.live_events._event_sink)
            self.assertEqual(
                engine.web_agent_health(),
                {"enabled": False, "state": "disabled"},
            )
            self.assertFalse((Path(folder) / "agent-outbox.sqlite3").exists())

    def test_capture_engine_close_releases_optional_agent(self):
        class Agent:
            def __init__(self):
                self.closed = False

            def submit(self, _event):
                return True

            def close(self):
                self.closed = True

        with tempfile.TemporaryDirectory() as folder:
            agent = Agent()
            engine = CaptureEngine(
                Path(folder), Path(folder) / "desktop.sqlite3", object(),
                web_agent=agent,
            )

            engine.close()

            self.assertTrue(agent.closed)
            self.assertIsNone(engine.web_agent)
            self.assertIsNone(engine.live_events._event_sink)


if __name__ == "__main__":
    unittest.main()
