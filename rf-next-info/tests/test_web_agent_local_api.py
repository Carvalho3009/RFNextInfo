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
from core.web_agent_boss_api import (
    LOCAL_BOSS_ENCOUNTERS_SCHEMA,
    AgentBossEncounterState,
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


class AgentBossEncounterStateTest(unittest.TestCase):
    def test_snapshot_accumulates_damage_and_exposes_only_public_player_uid(self):
        state = AgentBossEncounterState()
        rows = [
            _public_event("1", "character.observed", {
                "character_uid": 100, "name": "Observador",
            }),
            _public_event("2", "world.players_appeared", {"entities": [
                {
                    "entity_ref": "player-a", "character_uid": 200,
                    "name": "Alice", "guild_id": 10,
                },
                {
                    "entity_ref": "player-b", "character_uid": 300,
                    "name": "Bob", "guild_id": 20,
                },
            ]}),
            _public_event("3", "world.guilds_observed", {"guilds": [
                {"guild_id": 10, "guild_name": "Blood"},
                {"guild_id": 20, "guild_name": "Nova"},
            ]}),
            _public_event("4", "world.monsters_appeared", {"entities": [{
                "entity_ref": "boss-a", "npc_index": 845,
                "current_hp": 1000, "max_hp": 1000,
            }]}),
            _public_event("5", "combat.skill_resolved", {
                "result": 0, "caster_ref": "player-a", "combat_domain": "boss",
                "effects": [{
                    "entity_ref": "boss-a", "hp_damage": 300, "final_hp": 700,
                }],
            }),
            _public_event("6", "combat.normal_attack_resolved", {
                "result": 0, "caster_ref": "player-a", "combat_domain": "boss",
                "effects": [{
                    "entity_ref": "boss-a", "hp_damage": 100, "final_hp": 600,
                }],
            }),
            _public_event("7", "combat.skill_resolved", {
                "result": 0, "caster_ref": "player-b", "combat_domain": "boss",
                "effects": [{
                    "entity_ref": "boss-a", "hp_damage": 200, "final_hp": 400,
                }],
            }),
        ]
        for row in rows:
            state.observe(row)

        payload = state.snapshot()
        encounter = payload["encounters"][0]

        self.assertEqual(payload["schema"], LOCAL_BOSS_ENCOUNTERS_SCHEMA)
        self.assertEqual(encounter["boss"]["name"], "Guardião Tyrant Origin")
        self.assertEqual(encounter["boss"]["current_hp"], 400)
        self.assertEqual(encounter["boss"]["hp_percent"], 40.0)
        self.assertEqual(encounter["damage_total"], 600)
        self.assertEqual(
            [(row["name"], row["uid"], row["guild_id"], row["guild_name"],
              row["guild"], row["damage"])
             for row in encounter["players"]],
            [
                ("Alice", 200, 10, "Blood", "Blood", 400),
                ("Bob", 300, 20, "Nova", "Nova", 200),
            ],
        )
        self.assertNotIn("session_ref", json.dumps(payload))
        self.assertNotIn("player-a", json.dumps(encounter["players"]))

        candidate = state.upload_candidates(now_ns=1_000_000_000)[0]
        self.assertEqual(candidate["_session_ref"], "session-ref")
        self.assertEqual(candidate["players"][0]["_player_ref"], "player-a")
        state.mark_uploaded(candidate, now_ns=1_000_000_000)
        self.assertEqual(state.upload_candidates(now_ns=2_000_000_000), [])

        state.observe(_public_event("8", "combat.skill_resolved", {
            "result": 0, "caster_ref": "player-a", "combat_domain": "boss",
            "effects": [{
                "entity_ref": "boss-a", "hp_damage": 50, "final_hp": 350,
            }],
        }))
        self.assertEqual(state.upload_candidates(now_ns=1_500_000_000), [])
        self.assertEqual(
            state.upload_candidates(now_ns=2_100_000_000)[0]["damage_total"], 650,
        )

    def test_encounters_are_isolated_per_client_and_removed_explicitly(self):
        state = AgentBossEncounterState()
        for client, boss_ref in (("client-a", "boss-a"), ("client-b", "boss-b")):
            row = _public_event(client, "boss.position_observed", {
                "boss_ref": boss_ref, "npc_index": 845,
            })
            row["client_ref"] = client
            state.observe(row)
        self.assertEqual(state.snapshot()["encounter_count"], 2)

        removed = _public_event("gone", "world.entities_disappeared", {
            "entity_refs": ["boss-a"],
        })
        removed["client_ref"] = "client-a"
        state.observe(removed)

        snapshot = state.snapshot()
        self.assertEqual(snapshot["encounter_count"], 1)
        self.assertEqual(snapshot["encounters"][0]["client_ref"], "client-b")

    def test_player_guild_association_is_isolated_per_client(self):
        state = AgentBossEncounterState()
        for client, guild_id, guild_name in (
            ("client-a", 10, "Blood"),
            ("client-b", 20, "Nova"),
        ):
            for event_type, payload in (
                ("world.players_appeared", {"entities": [{
                    "entity_ref": "same-player-ref",
                    "character_uid": 100 + guild_id,
                    "name": f"Player {client}",
                    "guild_id": guild_id,
                }]}),
                ("world.guilds_observed", {"guilds": [{
                    "guild_id": guild_id,
                    "guild_name": guild_name,
                }]}),
                ("boss.position_observed", {
                    "boss_ref": "same-boss-ref", "npc_index": 845,
                }),
                ("combat.skill_resolved", {
                    "result": 0,
                    "caster_ref": "same-player-ref",
                    "combat_domain": "boss",
                    "effects": [{
                        "entity_ref": "same-boss-ref",
                        "hp_damage": guild_id,
                    }],
                }),
            ):
                event = _public_event(client, event_type, payload)
                event["client_ref"] = client
                state.observe(event)

        encounters = {
            row["client_ref"]: row for row in state.snapshot()["encounters"]
        }
        self.assertEqual(
            encounters["client-a"]["players"][0]["guild_name"], "Blood"
        )
        self.assertEqual(
            encounters["client-b"]["players"][0]["guild_name"], "Nova"
        )
        self.assertEqual(
            encounters["client-a"]["players"][0]["guild_id"], 10
        )
        self.assertEqual(
            encounters["client-b"]["players"][0]["guild_id"], 20
        )

    def test_online_service_enqueues_consolidated_boss_without_publisher(self):
        with tempfile.TemporaryDirectory() as folder:
            service = WindowsAgentLocalService.create_online(
                Path(folder), str(uuid.uuid4()), "https://qol.example.test",
                version="test", local_api_port=0,
                transport_sender=lambda *_args: (_ for _ in ()).throw(
                    AssertionError("transporte nao deveria iniciar")
                ),
            )
            try:
                def event(identifier: str, event_type: str, payload: dict) -> dict:
                    value = _public_event(identifier, event_type, payload)
                    value["session_ref"] = "1" * 32
                    value["client_ref"] = "2" * 32
                    return value

                observer = service.runtime.bridge.event_observer
                observer(event("1", "world.players_appeared", {"entities": [{
                    "entity_ref": "player-a", "character_uid": 200,
                    "name": "Alice", "guild_id": 10, "guild_name": "Blood",
                }]}))
                with mock.patch(
                    "core.web_agent_boss_api.time.time_ns", return_value=1_000_000_000
                ):
                    observer(event("2", "boss.position_observed", {
                        "boss_ref": "boss-a", "npc_index": 845,
                    }))
                with mock.patch(
                    "core.web_agent_boss_api.time.time_ns", return_value=2_100_000_000
                ):
                    observer(event("3", "combat.skill_resolved", {
                        "result": 0, "caster_ref": "player-a",
                        "combat_domain": "boss", "effects": [{
                            "entity_ref": "boss-a", "hp_damage": 300,
                            "final_hp": 700,
                        }],
                    }))

                batches = []
                while batch := service.runtime.bridge.outbox.next_batch():
                    batches.extend(batch["events"])
                    service.runtime.bridge.outbox.acknowledge(
                        batch["batch_id"], batch["last_sequence"]
                    )
                snapshots = [
                    row for row in batches
                    if row["type"] == "boss.encounter_snapshot"
                ]
                self.assertEqual(len(snapshots), 2)
                self.assertEqual(
                    snapshots[-1]["payload"]["players"][0]["damage_total"], 300
                )
                self.assertEqual(
                    snapshots[-1]["payload"]["players"][0]["guild_name"], "Blood"
                )
            finally:
                service.close()


class AgentLocalMonitorApiTest(unittest.TestCase):
    def test_health_exposes_sanitized_decoder_types_and_projection(self):
        api = AgentLocalMonitorApi(
            AgentMonitorFeed(),
            "h" * 43,
            health_provider=lambda: {
                "state": "capturing",
                "projection": {
                    "accepted": 12,
                    "errors": 1,
                    "errors_by_type": {"market": 1},
                    "last_errors_by_type": {
                        "market": "WebEventContractError: snapshot inválido",
                    },
                },
                "decoder": {
                    "decoded_events": 20,
                    "last_decoded_ns": 1_787_719_000_000_000_000,
                    "stalled_tcp_flows": 1,
                    "tcp_gap_recoveries": 2,
                    "decoded_by_type": {
                        "FL2C_respond_purchase_list_on_exchange_Message": 3,
                    },
                    "event_sink_accepted_by_type": {
                        "FL2C_respond_purchase_list_on_exchange_Message": 3,
                    },
                },
                "server": {
                    "mode": "online",
                    "state": "online",
                    "delivery": {
                        "state": "idle",
                        "worker_alive": True,
                        "registration_state": "active",
                        "last_attempt_at": "2026-08-26T04:40:00Z",
                        "last_ack_at": "2026-08-26T04:40:01Z",
                        "sent_batches": 12,
                        "sent_events": 345,
                        "retry_seconds": 1.0,
                    },
                },
            },
            port=0,
        )

        health = api._health()

        self.assertEqual(health["capture_bridge"]["accepted"], 12)
        self.assertEqual(health["capture_bridge"]["errors_by_type"], {"market": 1})
        self.assertIn(
            "snapshot inválido",
            health["capture_bridge"]["last_errors_by_type"]["market"],
        )
        self.assertEqual(
            health["decoder"]["decoded_by_type"]
            ["FL2C_respond_purchase_list_on_exchange_Message"],
            3,
        )
        self.assertEqual(health["decoder"]["tcp_gap_recoveries"], 2)
        self.assertEqual(health["decoder"]["stalled_tcp_flows"], 1)
        self.assertEqual(health["server"], {
            "mode": "online", "state": "online",
        })
        self.assertEqual(health["delivery"]["state"], "idle")
        self.assertTrue(health["delivery"]["worker_alive"])
        self.assertEqual(health["delivery"]["sent_events"], 345)
        self.assertEqual(
            health["delivery"]["last_ack_at"], "2026-08-26T04:40:01Z"
        )
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
                bosses, _headers = _request(
                    port,
                    str(pairing["token"]),
                    "/api/agent/v1/boss/encounters",
                )
                self.assertEqual(bosses["schema"], LOCAL_BOSS_ENCOUNTERS_SCHEMA)
                self.assertEqual(bosses["encounter_count"], 1)
                self.assertEqual(bosses["encounters"][0]["boss"]["npc_index"], 845)
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
                    "enemy_guild_list", 3,
                    {"guilds": [{
                        "guild_id": 77,
                        "guild_name": "Blood",
                    }]},
                    opcode=0x0D3F,
                )))
                self.assertTrue(runtime.submit(_decoded(
                    "FG2C_ans_boss_position_Message", 4,
                    {"uid": 777, "npc_index": 845, "fields": {
                        "position_x": 1, "position_y": 2, "position_z": 3,
                    }},
                    opcode=0x031C,
                )))
                self.assertTrue(runtime.submit(_decoded(
                    "update_exp", 5,
                    {"level": 66, "exp": 1000, "gain_exp": 100},
                    opcode=0x0307,
                )))
                runtime.bridge.wait_until_idle()

                remote_batch = runtime.bridge.outbox.next_batch()
                remote_types = {
                    event["type"] for event in remote_batch["events"]
                }
                self.assertNotIn("boss.position_observed", remote_types)
                self.assertNotIn("combat.skill_resolved", remote_types)
                self.assertNotIn("world.guilds_observed", remote_types)

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
                self.assertIn("world.guilds_observed", pvp_types)
                self.assertNotIn("boss.position_observed", pvp_types)
                self.assertIn("boss.position_observed", boss_types)
                self.assertIn("world.guilds_observed", boss_types)
                self.assertIn("world.players_appeared", boss_types)
                self.assertNotIn("character.exp_changed", pvp_types | boss_types)
                self.assertEqual(capabilities["domains"], ["boss", "pvp"])
                self.assertEqual(
                    capabilities["snapshots"]["boss_encounters"],
                    {
                        "path": "/api/agent/v1/boss/encounters",
                        "schema": LOCAL_BOSS_ENCOUNTERS_SCHEMA,
                    },
                )
                self.assertIn(
                    "world.players_appeared",
                    capabilities["event_types"]["pvp"],
                )
                self.assertIn(
                    "boss.position_observed",
                    capabilities["event_types"]["boss"],
                )
                self.assertIn(
                    "world.players_appeared",
                    capabilities["event_types"]["boss"],
                )
                self.assertTrue(capabilities["read_only"])
                self.assertEqual(health["feed"]["events"], 5)
                self.assertIn("delivery", health)
                self.assertEqual(health["delivery"]["state"], "unavailable")
                self.assertEqual(
                    health["throughput"],
                    {
                        "enqueued_events_last_minute": 4,
                        "sent_events_last_minute": 0,
                        "outbox_growth_events_last_minute": 4,
                    },
                )
                serialized = json.dumps(
                    {"pvp": pvp, "boss": boss, "health": health},
                    ensure_ascii=False,
                )
                self.assertIn('"character_uid": 123456', serialized)
                self.assertIn('"character_uid": 999', serialized)
                self.assertIn('"guild_name": "Blood"', serialized)
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
                self.assertEqual(len({row["session_ref"] for row in observed}), 4)
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
