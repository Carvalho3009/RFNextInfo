from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from unittest import mock

from core.web_agent_local_api import (
    AgentLocalApiTokenStore,
    AgentLocalMonitorApi,
    AgentMonitorFeed,
)
from core.web_agent_runtime import WebAgentOfflineRuntime
from core.web_agent_service import WindowsAgentLocalService


def _public_event(event_id: str, event_type: str, payload: dict | None = None) -> dict:
    return {
        "event_id": event_id,
        "session_ref": "session-ref",
        "stream_id": "stream-ref",
        "occurred_at": "2026-08-22T12:00:00.000Z",
        "client_ref": "client-ref",
        "type": event_type,
        "payload": payload or {},
        "evidence": {"confidence": "decoded", "decoder_version": "test"},
    }


def _decoded(kind: str, offset: int, data: dict, *, opcode: int) -> dict:
    return {
        "source": "memory://local-api-test",
        "flow": "10.0.0.1:51000 -> 10.0.0.2:12020",
        "stream_offset": offset,
        "bundle_seq": 0,
        "ts_ns": 1_700_000_000_000_000_000 + offset,
        "opcode": opcode,
        "type": kind,
        "data": data,
    }


def _request(port: int, token: str, path: str) -> tuple[dict, dict]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return json.load(response), dict(response.headers)


class AgentMonitorFeedTest(unittest.TestCase):
    def test_feed_filters_domains_deduplicates_and_bounds_history(self):
        feed = AgentMonitorFeed(max_events=2)
        self.assertTrue(feed.add(_public_event("1", "world.players_appeared")))
        self.assertFalse(feed.add(_public_event("1", "world.players_appeared")))
        self.assertFalse(feed.add(_public_event("ignored", "character.exp_changed")))
        self.assertTrue(feed.add(_public_event("2", "boss.position_observed")))
        self.assertTrue(feed.add(_public_event("3", "combat.skill_resolved")))

        pvp = feed.read(after=0, domains={"pvp"})
        boss = feed.read(after=0, domains={"boss"})

        self.assertEqual(
            [event["type"] for event in pvp["events"]],
            ["combat.skill_resolved"],
        )
        self.assertEqual(
            [event["type"] for event in boss["events"]],
            ["boss.position_observed", "combat.skill_resolved"],
        )
        self.assertEqual(feed.metrics()["events"], 2)
        self.assertEqual(feed.metrics()["duplicates"], 1)
        self.assertEqual(feed.metrics()["ignored"], 1)

    def test_feed_marks_cursor_loss_after_bounded_history_expires(self):
        feed = AgentMonitorFeed(max_events=2)
        for index in range(1, 5):
            self.assertTrue(feed.add(_public_event(
                str(index), "combat.skill_resolved"
            )))

        result = feed.read(after=0, domains={"pvp"})
        stale = feed.read(after=1, domains={"boss"})

        self.assertEqual([row["cursor"] for row in result["events"]], [3, 4])
        self.assertTrue(stale["reset_required"])
        self.assertEqual(stale["oldest_cursor"], 3)

    def test_feed_is_also_bounded_by_bytes(self):
        sample = _public_event(
            "sample", "boss.position_observed", {"padding": "x" * 300}
        )
        one_event_bytes = len(json.dumps(
            sample, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8"))
        feed = AgentMonitorFeed(max_events=100, max_bytes=one_event_bytes + 50)

        self.assertTrue(feed.add(sample))
        self.assertTrue(feed.add({**sample, "event_id": "sample-2"}))

        metrics = feed.metrics()
        self.assertEqual(metrics["events"], 1)
        self.assertLessEqual(metrics["bytes"], metrics["byte_limit"])

    def test_feed_limits_can_be_reduced_while_agent_is_idle(self):
        feed = AgentMonitorFeed(max_events=4, max_bytes=4096)
        for index in range(4):
            self.assertTrue(feed.add(_public_event(
                str(index), "combat.skill_resolved", {"value": "x" * 200}
            )))

        feed.configure_limits(max_events=2, max_bytes=1024)

        metrics = feed.metrics()
        self.assertLessEqual(metrics["events"], 2)
        self.assertLessEqual(metrics["bytes"], 1024)
        self.assertEqual(metrics["event_limit"], 2)
        self.assertEqual(metrics["byte_limit"], 1024)

    def test_long_poll_wakes_when_matching_event_arrives(self):
        feed = AgentMonitorFeed()

        def publish() -> None:
            time.sleep(0.05)
            feed.add(_public_event("boss-1", "boss.position_observed"))

        publisher = threading.Thread(target=publish)
        publisher.start()
        started = time.monotonic()
        result = feed.read(
            after=0, domains={"boss"}, wait_seconds=0.5
        )
        elapsed = time.monotonic() - started
        publisher.join(timeout=1)

        self.assertEqual(len(result["events"]), 1)
        self.assertGreaterEqual(elapsed, 0.03)
        self.assertLess(elapsed, 0.5)


class AgentLocalMonitorApiTest(unittest.TestCase):
    def test_agent_service_composes_runtime_api_and_explicit_pairing(self):
        with tempfile.TemporaryDirectory() as folder:
            service = WindowsAgentLocalService.create_offline(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                local_api_port=0,
            )
            try:
                port = service.start_local_api()
                pairing = service.pairing_credentials()
                self.assertEqual(pairing["base_url"], f"http://127.0.0.1:{port}")
                self.assertEqual(pairing["domains"], ["boss", "pvp"])
                self.assertNotIn(pairing["token"], json.dumps(service.health()))

                service.start_session("sessao-service")
                self.assertTrue(service.submit(_decoded(
                    "FG2C_ans_boss_position_Message", 1,
                    {"uid": 777, "npc_index": 845},
                    opcode=0x031C,
                )))
                service.runtime.bridge.wait_until_idle()
                events, _headers = _request(
                    port,
                    str(pairing["token"]),
                    "/api/agent/v1/monitor/events?domains=boss",
                )
                self.assertIn(
                    "boss.position_observed",
                    {event["type"] for event in events["events"]},
                )
            finally:
                service.close()

    def test_api_exposes_sanitized_boss_and_pvp_events_only_on_loopback(self):
        token = "t" * 43
        feed = AgentMonitorFeed(max_events=100)
        with tempfile.TemporaryDirectory() as folder:
            runtime = WebAgentOfflineRuntime.create(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                event_observer=feed.add,
            )
            api = AgentLocalMonitorApi(
                feed, token, health_provider=runtime.health, port=0
            )
            port = api.start()
            try:
                runtime.start_session("sessao-local")
                self.assertTrue(runtime.submit(_decoded(
                    "world_info_prefix", 1,
                    {"fields": {
                        "character_uid": 123456,
                        "character_name": "Personagem",
                        "level": 66,
                    }},
                    opcode=0x0106,
                )))
                self.assertTrue(runtime.submit(_decoded(
                    "appear_player_list", 2,
                    {"units": [{
                        "uid": 888,
                        "character_uid": 999,
                        "name": "Jogador próximo",
                        "level": 67,
                        "current_hp": 1000,
                        "max_hp": 1000,
                    }]},
                    opcode=0x0305,
                )))
                self.assertTrue(runtime.submit(_decoded(
                    "FG2C_ans_boss_position_Message", 3,
                    {"uid": 777, "npc_index": 845, "fields": {
                        "position_x": 1, "position_y": 2, "position_z": 3,
                    }},
                    opcode=0x031C,
                )))
                self.assertTrue(runtime.submit(_decoded(
                    "update_exp", 4,
                    {"level": 66, "exp": 1000, "gain_exp": 100},
                    opcode=0x0307,
                )))
                runtime.bridge.wait_until_idle()

                with self.assertRaises(urllib.error.HTTPError) as denied:
                    urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/agent/v1/health",
                        timeout=2,
                    )
                self.assertEqual(denied.exception.code, 401)

                pvp, headers = _request(
                    port, token,
                    "/api/agent/v1/monitor/events?domains=pvp&after=0",
                )
                boss, _headers = _request(
                    port, token,
                    "/api/agent/v1/monitor/events?domains=boss&after=0",
                )
                health, _headers = _request(
                    port, token, "/api/agent/v1/health"
                )
                capabilities, _headers = _request(
                    port, token, "/api/agent/v1/capabilities"
                )

                pvp_types = {event["type"] for event in pvp["events"]}
                boss_types = {event["type"] for event in boss["events"]}
                self.assertIn("world.players_appeared", pvp_types)
                self.assertNotIn("boss.position_observed", pvp_types)
                self.assertIn("boss.position_observed", boss_types)
                self.assertNotIn("world.players_appeared", boss_types)
                self.assertNotIn("character.exp_changed", pvp_types | boss_types)
                self.assertEqual(capabilities["domains"], ["boss", "pvp"])
                self.assertIn(
                    "world.players_appeared",
                    capabilities["event_types"]["pvp"],
                )
                self.assertIn(
                    "boss.position_observed",
                    capabilities["event_types"]["boss"],
                )
                self.assertTrue(capabilities["read_only"])
                self.assertEqual(health["feed"]["events"], 4)
                serialized = json.dumps(
                    {"pvp": pvp, "boss": boss, "health": health},
                    ensure_ascii=False,
                )
                self.assertIn('"character_uid": 123456', serialized)
                self.assertIn('"character_uid": 999', serialized)
                for forbidden in (
                    "sessao-local", "installation_id", "key_id",
                    "memory://", "10.0.0.1", '"opcode"',
                ):
                    self.assertNotIn(forbidden, serialized)
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertNotIn("Access-Control-Allow-Origin", headers)

                with self.assertRaises(urllib.error.HTTPError) as invalid_domain:
                    _request(
                        port, token,
                        "/api/agent/v1/monitor/events?domains=pve",
                    )
                self.assertEqual(invalid_domain.exception.code, 400)
            finally:
                api.stop()
                runtime.close()

    def test_api_keeps_clients_and_sessions_separate(self):
        token = "m" * 43
        feed = AgentMonitorFeed(max_events=100)
        with tempfile.TemporaryDirectory() as folder:
            runtime = WebAgentOfflineRuntime.create(
                Path(folder),
                str(uuid.uuid4()),
                version="test",
                event_observer=feed.add,
            )
            api = AgentLocalMonitorApi(feed, token, port=0)
            port = api.start()
            try:
                offset = 0
                for session_id in ("sessao-a", "sessao-b"):
                    runtime.start_session(session_id)
                    for client_index in (1, 2):
                        offset += 1
                        event = _decoded(
                            "world_info_prefix",
                            offset,
                            {"fields": {
                                "character_uid": client_index,
                                "character_name": f"Cliente {client_index}",
                                "level": 60,
                            }},
                            opcode=0x0106,
                        )
                        event["flow"] = (
                            f"10.0.0.1:{51000 + client_index} -> "
                            "10.0.0.2:12020"
                        )
                        self.assertTrue(runtime.submit(event))
                        offset += 1
                        combat = _decoded(
                            "use_normal_skill_result",
                            offset,
                            {
                                "caster_uid": client_index,
                                "main_target_uid": 900 + client_index,
                                "effect_results": [{
                                    "uid": 900 + client_index,
                                    "hp_damage": 10,
                                    "final_hp": 90,
                                }],
                            },
                            opcode=0x0702,
                        )
                        combat["flow"] = event["flow"]
                        self.assertTrue(runtime.submit(combat))
                    runtime.finish_session(session_id)
                runtime.bridge.wait_until_idle()

                payload, _headers = _request(
                    port,
                    token,
                    "/api/agent/v1/monitor/events?domains=pvp&after=0",
                )
                observed = [
                    row for row in payload["events"]
                    if row["type"] == "character.observed"
                ]
                combat = [
                    row for row in payload["events"]
                    if row["type"] == "combat.normal_attack_resolved"
                ]
                self.assertEqual(len({row["session_ref"] for row in observed}), 2)
                self.assertEqual(len({row["client_ref"] for row in observed}), 2)
                self.assertEqual(len(combat), 4)
                for row in combat:
                    self.assertIsNotNone(row["client_ref"])
            finally:
                api.stop()
                runtime.close()

    def test_api_rejects_non_loopback_bind(self):
        with self.assertRaisesRegex(ValueError, "127.0.0.1"):
            AgentLocalMonitorApi(
                AgentMonitorFeed(), "t" * 43, host="0.0.0.0"
            )

    def test_token_store_protects_and_rotates_current_user_secret(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch(
            "core.web_agent_local_api.protect_for_current_user",
            side_effect=lambda value, **_kwargs: value[::-1],
        ) as protected, mock.patch(
            "core.web_agent_local_api.unprotect",
            side_effect=lambda value: value[::-1],
        ):
            store = AgentLocalApiTokenStore(Path(folder) / "agent-api.bin")
            first = store.load_or_create()
            second = store.load_or_create()
            encrypted = store.path.read_bytes()
            rotated = store.rotate()

            self.assertEqual(first, second)
            self.assertNotEqual(first, rotated)
            self.assertNotIn(first.encode(), encrypted)
            self.assertEqual(protected.call_count, 2)


if __name__ == "__main__":
    unittest.main()
