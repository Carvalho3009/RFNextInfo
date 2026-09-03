from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.ui_qt.operations import CaptureEngine
from core.live_stream import LiveEventStream
from core.web_agent import (
    DELIVERY_PRIORITY_HIGH,
    DELIVERY_PRIORITY_IMMEDIATE,
    DELIVERY_PRIORITY_REALTIME,
    PROCESSING_PRIORITY_BOSS,
    PROCESSING_PRIORITY_NORMAL,
    AgentOutbox,
    OutboxFullError,
    WebAgentBridge,
    WebEventContractError,
    WebEventProjector,
    _connection_key,
    _validate_event_contract,
    delivery_priority,
    processing_priority,
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


def drain_outbox(outbox: AgentOutbox) -> list[dict]:
    events: list[dict] = []
    while True:
        batch = outbox.next_batch()
        if batch is None:
            return events
        events.extend(batch["events"])
        outbox.acknowledge(batch["batch_id"], batch["last_sequence"])


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

    def test_consolidated_boss_snapshot_has_maximum_delivery_priority(self):
        event = self.projector.project_boss_encounter({
            "_session_ref": "1" * 32,
            "encounter_ref": "boss-local-ref",
            "client_ref": "2" * 32,
            "started_at": "2026-08-31T20:00:00.000Z",
            "updated_at": "2026-08-31T20:00:01.000Z",
            "boss": {
                "npc_index": 845, "name": "Guardião Tyrant Origin", "level": 80,
                "current_hp": 900, "max_hp": 1000,
            },
            "players": [{
                "_player_ref": "player-local-ref", "uid": 61500000000000001,
                "name": "Carlos", "guild_id": 10, "guild_name": "Blood",
                "damage": 100,
            }],
        })

        self.assertEqual(event["type"], "boss.encounter_snapshot")
        self.assertEqual(delivery_priority(event["type"]), DELIVERY_PRIORITY_IMMEDIATE)
        self.assertEqual(event["payload"]["players"][0]["guild_name"], "Blood")
        self.assertNotIn("encounter_ref", json.dumps(event))
        self.assertNotIn("player-local-ref", json.dumps(event))
        _validate_event_contract(event)

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
        self.assertAlmostEqual(
            exp["payload"]["gained_exp_percent"],
            4_500 * 100 / 3_101_600_268,
            places=6,
        )
        self.assertAlmostEqual(
            exp["payload"]["level_percent"],
            123_000 * 100 / 3_101_600_268,
            places=6,
        )
        self.assertNotIn("sessao-1", json.dumps(identity))
        assert_no_forbidden_keys(self, identity)

    def test_projects_selected_completed_subsession_as_parent_session_slice(self):
        identity = self.projector.project(self.identity_event(), "sessao-1")
        report = {
            "source_subsession_id": "install-1:7",
            "character_uid": "123456789",
            "name": "Spot norte",
            "map_name": "Crag Mine",
            "spot_name": "Entrada",
            "mobs": ["Crawler", "Crawler", "Flem"],
            "started_ns": 1_780_000_000_000_000_000,
            "ended_ns": 1_780_001_800_000_000_000,
            "duration_seconds": 1800,
            "mob_kills_estimated": 25,
            "exp_total": 9000,
            "exp_total_percent": 0.25,
            "summary": {
                "level": 66, "credits": 500_000, "contribution": 20,
            },
        }

        projected = self.projector.project_subsession("sessao-1", report)

        self.assertEqual(projected["type"], "farm.subsession_completed")
        self.assertEqual(projected["session_ref"], identity["session_ref"])
        self.assertEqual(projected["payload"]["mobs"], ["Crawler", "Flem"])
        self.assertEqual(projected["payload"]["gained_exp"], 9000)
        self.assertEqual(projected["payload"]["gained_exp_percent"], 0.25)
        self.assertEqual(projected["payload"]["gained_credits"], 500_000)
        self.assertEqual(projected["payload"]["gained_contribution"], 20)
        assert_no_forbidden_keys(self, projected)

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

    def test_event_without_confirmed_identity_gets_connection_scoped_reference(self):
        event = decoded_event(
            "update_exp", {"exp": 10, "gain_exp": 10}, flow="outro-fluxo"
        )
        first = self.projector.project(event, "sessao-1")
        second = self.projector.project(event, "sessao-1")
        other = self.projector.project(decoded_event(
            "update_exp", {"exp": 20, "gain_exp": 10}, flow="fluxo-distinto"
        ), "sessao-1")
        self.assertIsNotNone(first["client_ref"])
        self.assertEqual(first["client_ref"], second["client_ref"])
        self.assertNotEqual(first["client_ref"], other["client_ref"])

    def test_finished_session_does_not_leak_identity_into_later_events(self):
        first = self.projector.project(self.identity_event(), "sessao-1")
        self.projector.finish_session("sessao-1")
        event = decoded_event("update_exp", {"exp": 10, "gain_exp": 10})
        second = self.projector.project(event, "sessao-2")
        self.assertNotEqual(first["session_ref"], second["session_ref"])

    def test_paused_capture_reuses_confirmed_identity_on_same_connection(self):
        identity = self.projector.project(self.identity_event(), "sessao-1")
        self.projector.finish_session("sessao-1", preserve_connections=True)

        exp = self.projector.project(
            decoded_event("update_exp", {"exp": 20, "gain_exp": 10}),
            "sessao-2",
        )

        self.assertEqual(exp["client_ref"], identity["client_ref"])

    def test_continuous_movement_is_limited_without_delaying_teleport(self):
        first = decoded_event(
            "move_player_request", {"position": [1, 2, 3]}, opcode=0x0901
        )
        repeated = decoded_event(
            "move_player_request", {"position": [2, 3, 4]}, offset=2,
            opcode=0x0901,
        )
        after_interval = decoded_event(
            "move_player_request", {"position": [3, 4, 5]}, offset=3,
            opcode=0x0901,
        )
        after_interval["ts_ns"] = first["ts_ns"] + 1_000_000_000
        teleport = decoded_event(
            "request_teleport", {"position": [9, 8, 7]}, offset=4,
            opcode=0x0902,
        )
        nearby_a = decoded_event(
            "move_player_update", {"uid": 101, "position": [5, 5, 5]},
            offset=5, opcode=0x0903,
        )
        nearby_b = decoded_event(
            "move_player_update", {"uid": 202, "position": [6, 6, 6]},
            offset=6, opcode=0x0903,
        )

        self.assertIsNotNone(self.projector.project(first, "sessao-1"))
        self.assertIsNone(self.projector.project(repeated, "sessao-1"))
        self.assertIsNotNone(
            self.projector.project(after_interval, "sessao-1")
        )
        self.assertIsNotNone(self.projector.project(teleport, "sessao-1"))
        self.assertIsNotNone(self.projector.project(nearby_a, "sessao-1"))
        self.assertIsNotNone(self.projector.project(nearby_b, "sessao-1"))

    def test_map_changes_are_timestamped_and_deduplicated_per_connection(self):
        self.projector.project(self.identity_event(), "sessao-1")
        first = decoded_event(
            "request_teleport_result",
            {"result": 0, "map_index": 605, "teleport_index": 605},
            offset=2, opcode=0x0409,
        )
        repeated = decoded_event(
            "request_teleport_result",
            {"result": 0, "map_index": 605, "teleport_index": 605},
            offset=3, opcode=0x0409,
        )
        changed = decoded_event(
            "teleport_response",
            {"result": 0, "map_index": 602, "teleport_index": 7},
            offset=4, opcode=0x0325,
        )
        failed = decoded_event(
            "request_teleport_result",
            {"result": 1, "map_index": 603, "teleport_index": 603},
            offset=5, opcode=0x0409,
        )

        initial_events = self.projector.project_many(first, "sessao-1")
        repeated_events = self.projector.project_many(repeated, "sessao-1")
        changed_events = self.projector.project_many(changed, "sessao-1")
        failed_events = self.projector.project_many(failed, "sessao-1")

        self.assertEqual(
            [event["type"] for event in initial_events],
            ["map.teleport_resolved", "map.changed"],
        )
        self.assertEqual(initial_events[1]["payload"], {"map_index": 605})
        self.assertEqual(initial_events[1]["occurred_at"], initial_events[0]["occurred_at"])
        self.assertEqual(
            [event["type"] for event in repeated_events],
            ["map.teleport_resolved"],
        )
        self.assertEqual(changed_events[1]["payload"], {
            "previous_map_index": 605,
            "map_index": 602,
        })
        self.assertEqual(changed_events[1]["occurred_at"], changed_events[0]["occurred_at"])
        self.assertEqual(
            [event["type"] for event in failed_events],
            ["map.teleport_resolved"],
        )

    def test_map_change_waits_for_confirmed_character_before_creating_state(self):
        transition = decoded_event(
            "request_teleport_result",
            {"result": 0, "map_index": 605, "teleport_index": 605},
            offset=2, opcode=0x0409,
        )
        self.assertEqual(
            [event["type"] for event in self.projector.project_many(
                transition, "sessao-1"
            )],
            ["map.teleport_resolved"],
        )
        self.projector.project(self.identity_event(offset=3), "sessao-1")
        replayed = self.projector.project_many(transition, "sessao-1")
        self.assertEqual(
            [event["type"] for event in replayed],
            ["map.teleport_resolved", "map.changed"],
        )

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

    def test_loot_projection_rejects_upgrade_or_prime_messages(self):
        event = decoded_event("loot_announcement", {"announcements": [{
            "character_uid": 11,
            "player_name": "Alice",
            "item_index": 1000444,
            "count": 1,
            "message_kind": 3,
        }]}, opcode=0x0E09)

        self.assertIsNone(self.projector.project(event, "sessao-1"))
        event["data"]["announcements"].append({
            "character_uid": 12,
            "player_name": "Bob",
            "item_index": 1000323,
            "count": 2,
            "message_kind": 2,
        })
        projected = self.projector.project(event, "sessao-1")
        self.assertEqual(
            [row["player_name"] for row in projected["payload"]["announcements"]],
            ["Bob"],
        )

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

    def test_projects_sanitized_community_market_observation(self):
        projected = self.projector.project(decoded_event(
            "FL2C_respond_purchase_list_on_exchange_Message",
            {
                "message": "FL2C_respond_purchase_list_on_exchange_Message",
                "ret": 0,
                "is_end": False,
                "exchange_server_type": 2,
                "exchange_item_simple_infos": [{
                    "item_index": 1000150,
                    "enchant_level": 7,
                    "lowest_price": 100,
                    "highest_price": 150,
                    "number_of_registered_items": 3,
                }],
            },
            opcode=0x1D02,
        ), "sessao-1")

        self.assertIsNotNone(projected)
        self.assertEqual(projected["type"], "community.market_observed")
        self.assertEqual(projected["payload"]["server_type"], 2)
        self.assertEqual(projected["payload"]["market_rows"][0], {
            "item_index": 1000150,
            "name": "Machado Pallacia do Executor",
            "enhance": 7,
            "lowest_price": 100,
            "highest_price": 150,
            "quantity": 3,
        })
        assert_no_forbidden_keys(self, projected)

    def test_market_projection_falls_back_when_packet_timestamp_is_invalid(self):
        projected = self.projector.project(decoded_event(
            "FL2C_respond_purchase_list_on_exchange_Message",
            {
                "message": "FL2C_respond_purchase_list_on_exchange_Message",
                "ret": 0,
                "is_end": True,
                "exchange_server_type": 1,
                "exchange_item_simple_infos": [{
                    "item_index": 1000150,
                    "enchant_level": 0,
                    "lowest_price": 100,
                    "highest_price": 100,
                    "number_of_registered_items": 1,
                }],
            },
            opcode=0x1D02,
            offset=2**80,
        ), "sessao-1")

        self.assertIsNotNone(projected)
        self.assertTrue(projected["occurred_at"].endswith("Z"))

    def test_market_projection_keeps_row_when_highest_price_is_zero(self):
        projected = self.projector.project(decoded_event(
            "FL2C_respond_purchase_list_on_exchange_Message",
            {
                "message": "FL2C_respond_purchase_list_on_exchange_Message",
                "ret": 0,
                "is_end": True,
                "exchange_server_type": 0,
                "exchange_item_simple_infos": [{
                    "item_index": 1000134,
                    "enchant_level": 5,
                    "lowest_price": 2400,
                    "highest_price": 0,
                    "number_of_registered_items": 1,
                }],
            },
            opcode=0x1D02,
        ), "sessao-1")

        self.assertIsNotNone(projected)
        self.assertEqual(projected["type"], "community.market_observed")
        row = projected["payload"]["market_rows"][0]
        self.assertEqual(row["item_index"], 1000134)
        self.assertEqual(row["enhance"], 5)
        self.assertEqual(row["lowest_price"], 2400)
        self.assertEqual(row["highest_price"], 2400)
        self.assertEqual(row["quantity"], 1)
        self.assertTrue(row["name"])

    def test_projects_private_auction_actions_only_with_sanitized_fields(self):
        self.projector.observe_identity_event(self.identity_event())
        self.projector.project(self.identity_event(), "sessao-1")
        entry = {
            "exchange_index": 444,
            "account_id": 111,
            "pc_id": 222,
            "item_info": {
                "id": 987654321,
                "index": 270062,
                "count": 3,
                "enchant_level": 7,
                "item_options": [{"option_index": 9, "value": 10}],
            },
            "registed_time": 10,
            "expired_time": 20,
            "selling_time": 0,
            "selling_price": 1500,
            "settlement_price": 0,
        }
        listed = self.projector.project_many(decoded_event(
            "FL2C_ans_exchange_for_my_sales_list_Message",
            {
                "message": "FL2C_ans_exchange_for_my_sales_list_Message",
                "ret": 0,
                "exchange_server_type": 2,
                "my_sales_list": [entry],
            },
            offset=2,
            opcode=0x1D07,
        ), "sessao-1")
        sold = self.projector.project_many(decoded_event(
            "FL2C_notify_exchange_item_sell_Message",
            {
                "message": "FL2C_notify_exchange_item_sell_Message",
                "exchange_server_type": 2,
                "exchange_indices": [444],
            },
            offset=3,
            opcode=0x1D1B,
        ), "sessao-1")

        self.assertEqual(len(listed), 2)
        self.assertEqual(listed[0]["type"], "market.personal_listing_observed")
        self.assertEqual(listed[0]["payload"]["status"], "active")
        self.assertEqual(listed[1]["type"], "market.personal_listings_snapshot")
        self.assertEqual(listed[1]["payload"]["record_count"], 1)
        self.assertEqual(
            listed[1]["payload"]["listing_ids"],
            [listed[0]["payload"]["listing_id"]],
        )
        self.assertEqual(len(sold), 1)
        self.assertEqual(sold[0]["type"], "market.personal_transaction_observed")
        self.assertEqual(sold[0]["payload"]["transaction_type"], "sold")
        self.assertEqual(
            listed[0]["payload"]["listing_id"], sold[0]["payload"]["listing_id"]
        )
        self.assertEqual(
            delivery_priority(sold[0]["type"]), DELIVERY_PRIORITY_HIGH
        )
        serialized = json.dumps(listed + sold)
        for forbidden in (
            "444", "987654321", "account_id", "pc_id", "item_options",
        ):
            self.assertNotIn(forbidden, serialized)
        assert_no_forbidden_keys(self, listed + sold)

    def test_projects_empty_personal_sales_list_as_authoritative_snapshot(self):
        self.projector.observe_identity_event(self.identity_event())
        self.projector.project(self.identity_event(), "sessao-1")

        projected = self.projector.project_many(decoded_event(
            "FL2C_ans_exchange_for_my_sales_list_Message",
            {
                "message": "FL2C_ans_exchange_for_my_sales_list_Message",
                "ret": 0,
                "exchange_server_type": 1,
                "my_sales_list": [],
            },
            offset=4,
            opcode=0x1D07,
        ), "sessao-1")

        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["type"], "market.personal_listings_snapshot")
        self.assertEqual(projected[0]["payload"]["record_count"], 0)
        self.assertEqual(projected[0]["payload"]["listing_ids"], [])

    def test_market_snapshot_is_chunked_without_truncation(self):
        rows = [{
            "item_index": 100_000 + index,
            "item_name": f"Item {index}",
            "enchant_level": 0,
            "lowest_price": index + 1,
            "highest_price": index + 2,
            "number_of_registered_items": 1,
        } for index in range(600)]
        event = decoded_event("market", {
            "message": "FL2C_respond_purchase_list_on_exchange_Message",
            "ret": 0,
            "exchange_server_type": 1,
            "exchange_item_simple_infos": rows,
        }, opcode=0x1D02)

        projected = self.projector.project_many(event, "sessao-1")

        self.assertEqual(len(projected), 3)
        self.assertEqual(
            [item["payload"]["chunk_index"] for item in projected], [1, 2, 3]
        )
        self.assertEqual(
            {item["payload"]["chunk_count"] for item in projected}, {3}
        )
        self.assertEqual(
            len({item["payload"]["snapshot_ref"] for item in projected}), 1
        )
        self.assertEqual(sum(
            len(item["payload"]["market_rows"]) for item in projected
        ), 600)

    def test_inventory_and_collection_snapshots_use_confirmed_character(self):
        self.projector.project(self.identity_event(), "sessao-1")
        inventory = self.projector.project_many(decoded_event(
            "inventory_snapshot",
            {
                "container": "inventory", "item_kind": "stackable",
                "items": [{
                    "inventory_slot": 7, "item_index": 158003,
                    "count": 3, "enchant_level": 0, "lock": True,
                }],
            },
            offset=2,
        ), "sessao-1")
        first_collection = self.projector.project_many(decoded_event(
            "collection_snapshot_chunk",
            {
                "collection_type": 1, "is_end": False,
                "records": [{"collection_index": 500, "slot_values": [1, 0, 2]}],
            },
            offset=3,
        ), "sessao-1")
        final_collection = self.projector.project_many(decoded_event(
            "collection_snapshot_chunk",
            {
                "collection_type": 1, "is_end": True,
                "records": [{"collection_index": 501, "slot_values": [1, 2]}],
            },
            offset=4,
        ), "sessao-1")

        self.assertEqual(len(inventory), 1)
        self.assertEqual(inventory[0]["type"], "inventory.snapshot")
        self.assertEqual(inventory[0]["payload"]["character_uid"], 123456789)
        self.assertEqual(inventory[0]["payload"]["item_kind"], "stackable")
        self.assertEqual(inventory[0]["payload"]["inventory_items"][0]["quantity"], 3)
        self.assertEqual(first_collection, [])
        self.assertEqual(len(final_collection), 1)
        self.assertEqual(final_collection[0]["type"], "progress.collection_snapshot")
        self.assertEqual(len(final_collection[0]["payload"]["collection_records"]), 2)
        records = {
            row["collection_index"]: row
            for row in final_collection[0]["payload"]["collection_records"]
        }
        self.assertEqual(records[500], {
            "collection_index": 500,
            "completed_slots": 2,
            "total_slots": 3,
            "completed": False,
        })
        self.assertEqual(records[501], {
            "collection_index": 501,
            "completed_slots": 2,
            "total_slots": 2,
            "completed": True,
        })

    def test_collection_projection_prefers_catalog_progress(self):
        self.projector.project(self.identity_event(), "sessao-1")
        catalog_progress = {
            "collection_index": 1015,
            "collection_type": 1,
            "slot_values": [1, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            "catalog_known": True,
            "completed_slots": [0],
            "incomplete_slots": [1],
            "collection_complete": False,
            "item_uid": 987654321,
            "updated_slot_value": 123,
        }

        snapshot = self.projector.project_many(decoded_event(
            "collection_snapshot_chunk",
            {
                "collection_type": 1,
                "is_end": True,
                "records": [catalog_progress],
            },
            offset=2,
        ), "sessao-1")
        update = self.projector.project_many(decoded_event(
            "collection_add_response",
            {
                **catalog_progress,
                "result_code": 0,
                "slot_index": 1,
            },
            offset=3,
        ), "sessao-1")

        expected = {
            "collection_index": 1015,
            "completed_slots": 1,
            "total_slots": 2,
            "completed": False,
            "completed_slot_indexes": [0],
            "missing_slot_indexes": [1],
        }
        self.assertEqual(snapshot[0]["payload"]["collection_type"], 1)
        self.assertEqual(update[0]["payload"]["collection_type"], 1)
        self.assertEqual(snapshot[0]["payload"]["collection_records"], [expected])
        self.assertEqual(update[0]["payload"]["collection_records"], [expected])
        assert_no_forbidden_keys(self, snapshot[0])
        assert_no_forbidden_keys(self, update[0])
        serialized = json.dumps([snapshot, update], sort_keys=True)
        self.assertNotIn("item_uid", serialized)
        self.assertNotIn("slot_values", serialized)
        self.assertNotIn("updated_slot_value", serialized)

    def test_collection_projection_keeps_fallback_without_catalog(self):
        self.projector.project(self.identity_event(), "sessao-1")

        projected = self.projector.project_many(decoded_event(
            "collection_snapshot_chunk",
            {
                "collection_type": 1,
                "is_end": True,
                "records": [{
                    "collection_index": 500,
                    "slot_values": [1, 0, 2],
                }],
            },
            offset=2,
        ), "sessao-1")

        self.assertEqual(projected[0]["payload"]["collection_type"], 1)
        self.assertEqual(projected[0]["payload"]["collection_records"], [{
            "collection_index": 500,
            "completed_slots": 2,
            "total_slots": 3,
            "completed": False,
        }])
        self.assertNotIn(
            "completed_slot_indexes",
            projected[0]["payload"]["collection_records"][0],
        )
        self.assertNotIn(
            "missing_slot_indexes",
            projected[0]["payload"]["collection_records"][0],
        )

    def test_collection_chunks_are_isolated_by_client_and_character(self):
        flow_a = "10.0.0.1:50000 -> 10.0.0.2:12020"
        flow_b = "10.0.0.1:50001 -> 10.0.0.2:12020"

        def identity(flow: str, uid: int, offset: int) -> None:
            event = decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": uid,
                    "character_name": f"Personagem {uid}",
                    "level": 60,
                }},
                flow=flow,
                offset=offset,
                opcode=0x0106,
            )
            self.projector.observe_identity_event(event)
            self.projector.project(event, "sessao-1")

        def chunk(
            flow: str, collection_type: int, collection_index: int,
            offset: int, *, is_end: bool,
        ) -> list[dict]:
            return self.projector.project_many(decoded_event(
                "collection_snapshot_chunk",
                {
                    "collection_type": collection_type,
                    "is_end": is_end,
                    "records": [{
                        "collection_index": collection_index,
                        "slot_values": [1, 0],
                    }],
                },
                flow=flow,
                offset=offset,
            ), "sessao-1")

        identity(flow_a, 111, 1)
        identity(flow_b, 222, 2)
        self.assertEqual(chunk(flow_a, 1, 101, 3, is_end=False), [])
        self.assertEqual(chunk(flow_b, 1, 201, 4, is_end=False), [])
        completed_a = chunk(flow_a, 1, 102, 5, is_end=True)
        self.assertEqual(chunk(flow_a, 2, 111, 6, is_end=False), [])
        identity(flow_a, 333, 7)
        completed_c = chunk(flow_a, 2, 301, 8, is_end=True)
        completed_b = chunk(flow_b, 1, 202, 9, is_end=True)

        self.assertEqual([
            (
                events[0]["payload"]["character_uid"],
                events[0]["payload"]["collection_type"],
                [row["collection_index"] for row in
                 events[0]["payload"]["collection_records"]],
            )
            for events in (completed_a, completed_b, completed_c)
        ], [
            (111, 1, [101, 102]),
            (222, 1, [201, 202]),
            (333, 2, [301]),
        ])

    def test_collection_contract_rejects_malformed_slot_indexes(self):
        self.projector.project(self.identity_event(), "sessao-1")
        projected = self.projector.project_many(decoded_event(
            "collection_snapshot_chunk",
            {
                "collection_type": 1,
                "is_end": True,
                "records": [{
                    "collection_index": 1015,
                    "slot_values": [1, 0],
                    "completed_slots": [0],
                    "incomplete_slots": [1],
                }],
            },
            offset=2,
        ), "sessao-1")[0]
        projected["payload"]["collection_records"][0][
            "missing_slot_indexes"
        ] = [0, 1]

        with self.assertRaises(WebEventContractError):
            _validate_event_contract(projected)

    def test_correlated_profile_marks_matching_inventory_item_as_equipped(self):
        self.projector.project(self.identity_event(), "sessao-1")
        profile = decoded_event(
            "player_profile_info",
            {"fields": {"active_equipment": {
                "character_uid": 123456789,
                "slots": [{
                    "resolved": True,
                    "item": {"item_uid": 987654, "item_index": 1000078},
                }],
            }}},
            offset=2,
        )
        self.assertEqual(self.projector.project_many(profile, "sessao-1"), [])
        inventory = self.projector.project_many(decoded_event(
            "inventory_snapshot",
            {
                "container": "inventory", "item_kind": "equipment",
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }, {
                    "inventory_slot": 8, "item_uid": 123,
                    "item_index": 1000080, "count": 1,
                    "enchant_level": 0, "lock": False,
                }],
            },
            offset=3,
        ), "sessao-1")

        items = inventory[0]["payload"]["inventory_items"]
        self.assertTrue(items[0]["equipped"])
        self.assertFalse(items[1]["equipped"])

    def test_local_profile_emits_equipment_snapshot_with_exact_loadout(self):
        self.projector.project(self.identity_event(), "sessao-1")
        projected = self.projector.project_many(decoded_event(
            "player_profile_info",
            {"fields": {
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }, {
                    "inventory_slot": 8, "item_uid": 123,
                    "item_index": 1000080, "count": 1,
                    "enchant_level": 0, "lock": False,
                }],
                "active_equipment": {
                    "character_uid": 123456789,
                    "slots": [{
                        "resolved": True,
                        "item": {"item_uid": 987654, "item_index": 1000078},
                    }],
                },
            }},
            offset=2,
        ), "sessao-1")

        self.assertEqual(len(projected), 1)
        self.assertEqual(projected[0]["type"], "inventory.snapshot")
        self.assertEqual(projected[0]["payload"]["item_kind"], "equipment")
        self.assertEqual(
            [item["equipped"] for item in projected[0]["payload"]["inventory_items"]],
            [True, False],
        )

    def test_nearby_profile_cannot_mark_or_publish_local_equipment(self):
        self.projector.project(self.identity_event(), "sessao-1")
        nearby = self.projector.project_many(decoded_event(
            "player_profile_info",
            {"fields": {
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }],
                "active_equipment": {
                    "character_uid": 987654321,
                    "slots": [{
                        "resolved": True,
                        "item": {"item_uid": 987654, "item_index": 1000078},
                    }],
                },
            }},
            offset=2,
        ), "sessao-1")
        inventory = self.projector.project_many(decoded_event(
            "inventory_snapshot",
            {
                "container": "inventory", "item_kind": "equipment",
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }],
            },
            offset=3,
        ), "sessao-1")

        self.assertEqual(nearby, [])
        self.assertFalse(inventory[0]["payload"]["inventory_items"][0]["equipped"])

    def test_inventory_delta_rebuilds_complete_state_and_can_clear_kind(self):
        self.projector.project(self.identity_event(), "sessao-1")
        snapshot = self.projector.project_many(decoded_event(
            "inventory_snapshot",
            {
                "type": "inventory_snapshot",
                "container": "inventory", "item_kind": "stackable",
                "items": [{
                    "inventory_slot": 1, "item_uid": 10,
                    "item_index": 158003, "count": 3,
                    "enchant_level": 0, "lock": False,
                }, {
                    "inventory_slot": 2, "item_uid": 20,
                    "item_index": 158004, "count": 2,
                    "enchant_level": 0, "lock": False,
                }],
            }, offset=2,
        ), "sessao-1")
        updated = self.projector.project_many(decoded_event(
            "inventory_delta",
            {
                "type": "inventory_delta",
                "container": "inventory", "item_kind": "stackable",
                "item": {
                    "inventory_slot": 1, "item_uid": 10,
                    "item_index": 158003, "count": 5,
                    "enchant_level": 0, "lock": False,
                },
            }, offset=3,
        ), "sessao-1")
        removed = self.projector.project_many(decoded_event(
            "inventory_delta",
            {
                "type": "inventory_delta",
                "container": "inventory", "item_kind": "stackable",
                "item": {
                    "inventory_slot": 2, "item_uid": 20,
                    "item_index": 158004, "count": 0,
                    "enchant_level": 0, "lock": False,
                },
            }, offset=4,
        ), "sessao-1")
        cleared = self.projector.project_many(decoded_event(
            "inventory_delta",
            {
                "type": "inventory_delta",
                "container": "inventory", "item_kind": "stackable",
                "item": {
                    "inventory_slot": 1, "item_uid": 10,
                    "item_index": 158003, "count": 0,
                    "enchant_level": 0, "lock": False,
                },
            }, offset=5,
        ), "sessao-1")

        self.assertTrue(snapshot[0]["payload"]["complete"])
        self.assertEqual(
            {item["item_index"]: item["quantity"]
             for item in updated[0]["payload"]["inventory_items"]},
            {158003: 5, 158004: 2},
        )
        self.assertEqual(
            [item["item_index"] for item in removed[0]["payload"]["inventory_items"]],
            [158003],
        )
        self.assertTrue(cleared[0]["payload"]["complete"])
        self.assertEqual(cleared[0]["payload"]["inventory_items"], [])

    def test_inventory_state_is_isolated_between_clients(self):
        flow_a = "10.0.0.1:50000 -> 10.0.0.2:12020"
        flow_b = "10.0.0.1:50001 -> 10.0.0.2:12020"
        for offset, flow, uid, name in (
            (1, flow_a, 111, "A"), (2, flow_b, 222, "B"),
        ):
            self.projector.project(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": uid, "character_name": name, "level": 60,
                }}, offset=offset, flow=flow, opcode=0x0106,
            ), "sessao-1")
        projected = []
        for offset, flow, item_index in (
            (3, flow_a, 158003), (4, flow_b, 158004),
        ):
            projected.append(self.projector.project_many(decoded_event(
                "inventory_snapshot",
                {
                    "type": "inventory_snapshot",
                    "container": "inventory", "item_kind": "stackable",
                    "items": [{
                        "inventory_slot": 1, "item_uid": item_index,
                        "item_index": item_index, "count": 1,
                        "enchant_level": 0, "lock": False,
                    }],
                }, offset=offset, flow=flow,
            ), "sessao-1")[0])

        self.assertEqual(
            [(event["payload"]["character_uid"],
              event["payload"]["inventory_items"][0]["item_index"])
             for event in projected],
            [(111, 158003), (222, 158004)],
        )
        self.assertNotEqual(projected[0]["client_ref"], projected[1]["client_ref"])

    def test_character_change_clears_inventory_and_equipment_state(self):
        first_identity = self.identity_event()
        self.projector.observe_identity_event(first_identity)
        self.projector.project(first_identity, "sessao-1")
        self.projector.project_many(decoded_event(
            "player_profile_info",
            {"fields": {
                "items": [{
                    "inventory_slot": 7, "item_uid": 10,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }],
                "active_equipment": {
                    "character_uid": 123456789,
                    "slots": [{
                        "resolved": True,
                        "item": {"item_uid": 10, "item_index": 1000078},
                    }],
                },
            }},
            offset=2,
        ), "sessao-1")

        second_identity = decoded_event(
            "world_info_prefix",
            {"fields": {
                "character_uid": 987654321,
                "character_name": "Outro personagem",
                "level": 70,
            }},
            offset=3,
            opcode=0x0106,
        )
        self.projector.observe_identity_event(second_identity)
        self.projector.project(second_identity, "sessao-1")
        projected = self.projector.project_many(decoded_event(
            "inventory_delta",
            {
                "type": "inventory_delta",
                "container": "inventory", "item_kind": "equipment",
                "item": {
                    "inventory_slot": 8, "item_uid": 10,
                    "item_index": 1000080, "count": 1,
                    "enchant_level": 0, "lock": False,
                },
            },
            offset=4,
        ), "sessao-1")

        self.assertEqual(len(projected), 1)
        payload = projected[0]["payload"]
        self.assertEqual(payload["character_uid"], 987654321)
        self.assertFalse(payload["complete"])
        self.assertEqual(
            [item["item_index"] for item in payload["inventory_items"]],
            [1000080],
        )
        self.assertFalse(payload["inventory_items"][0]["equipped"])

    def test_successful_equipment_change_updates_next_inventory_projection(self):
        self.projector.project(self.identity_event(), "sessao-1")
        self.projector.project_many(decoded_event(
            "player_profile_info",
            {"fields": {
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }],
                "active_equipment": {
                    "character_uid": 123456789,
                    "slots": [{
                        "equip_part_type": 1,
                        "resolved": True,
                        "item": {"item_uid": 987654, "item_index": 1000078},
                    }],
                },
            }}, offset=2,
        ), "sessao-1")
        self.projector.observe_identity_event(decoded_event(
            "change_equip_slot_response",
            {"fields": {
                "result": 0, "equipment_slot": 1, "item_uid": 123,
            }}, offset=3, opcode=0x0502,
        ))
        projected = self.projector.project_many(decoded_event(
            "inventory_snapshot",
            {
                "type": "inventory_snapshot",
                "container": "inventory", "item_kind": "equipment",
                "items": [{
                    "inventory_slot": 7, "item_uid": 987654,
                    "item_index": 1000078, "count": 1,
                    "enchant_level": 6, "lock": False,
                }, {
                    "inventory_slot": 8, "item_uid": 123,
                    "item_index": 1000080, "count": 1,
                    "enchant_level": 0, "lock": False,
                }],
            }, offset=4,
        ), "sessao-1")

        equipped = {
            item["item_index"] for item in projected[0]["payload"]["inventory_items"]
            if item["equipped"]
        }
        self.assertEqual(equipped, {1000080})

    def test_identical_inventory_state_is_not_enqueued_again(self):
        self.projector.project(self.identity_event(), "sessao-1")
        data = {
            "type": "inventory_snapshot",
            "container": "inventory", "item_kind": "stackable",
            "items": [{
                "inventory_slot": 1, "item_uid": 10,
                "item_index": 158003, "count": 3,
                "enchant_level": 0, "lock": False,
            }],
        }
        first = self.projector.project_many(decoded_event(
            "inventory_snapshot", data, offset=2,
        ), "sessao-1")
        repeated = self.projector.project_many(decoded_event(
            "inventory_snapshot", data, offset=3,
        ), "sessao-1")

        self.assertEqual(len(first), 1)
        self.assertEqual(repeated, [])

    def test_projects_power_only_for_the_confirmed_connection(self):
        routed_flow = "client-route:process:1234"
        self.projector.project({
            **self.identity_event(), "flow": routed_flow,
        }, "sessao-1")
        projected = self.projector.project(decoded_event(
            "player_stat",
            {"fields": {"combat_power": 987_654}},
            offset=2,
            flow=routed_flow,
            opcode=0x0401,
        ), "sessao-1")

        self.assertEqual(projected["type"], "character.observed")
        self.assertEqual(projected["payload"], {
            "character_uid": 123456789,
            "power": 987_654,
        })
        assert_no_forbidden_keys(self, projected)

    def test_nearby_player_equipment_cannot_replace_confirmed_character(self):
        routed_flow = "client-route:process:1234"
        self.projector.project({
            **self.identity_event(), "flow": routed_flow,
        }, "sessao-1")

        nearby = self.projector.project(decoded_event(
            "player_equip_update",
            {"fields": {
                "character_uid": 987654321,
                "rover_item_index": 4_100_000,
            }},
            offset=2,
            flow=routed_flow,
            opcode=0x0407,
        ), "sessao-1")
        local = self.projector.project(decoded_event(
            "player_equip_update",
            {"fields": {
                "character_uid": 123456789,
                "rover_item_index": 4_300_000,
            }},
            offset=3,
            flow=routed_flow,
            opcode=0x0407,
        ), "sessao-1")

        self.assertIsNone(nearby)
        self.assertEqual(local["payload"], {
            "character_uid": 123456789,
            "rover_item_index": 4_300_000,
        })

    def test_nearby_player_equipment_cannot_establish_identity(self):
        projected = self.projector.project(decoded_event(
            "player_equip_update",
            {"fields": {
                "character_uid": 987654321,
                "rover_item_index": 4_100_000,
            }},
            opcode=0x0407,
        ), "sessao-1")

        self.assertIsNone(projected)

    def test_conflicting_direct_uid_cannot_replace_confirmed_connection(self):
        routed_flow = "client-route:process:1234"
        first = self.projector.project({
            **self.identity_event(), "flow": routed_flow,
        }, "sessao-1")
        conflicting = self.projector.project(decoded_event(
            "world_info_prefix",
            {"fields": {
                "result": 0,
                "character_uid": 987654321,
                "character_name": "Outro personagem",
                "level": 66,
            }},
            offset=2,
            flow=routed_flow,
            opcode=0x0106,
        ), "sessao-1")
        power = self.projector.project(decoded_event(
            "player_stat",
            {"fields": {"combat_power": 987_654}},
            offset=3,
            flow=routed_flow,
            opcode=0x0401,
        ), "sessao-1")

        self.assertEqual(first["payload"]["character_uid"], 123456789)
        self.assertIsNone(conflicting)
        self.assertEqual(power["payload"]["character_uid"], 123456789)

    def test_unnamed_world_info_cannot_establish_identity(self):
        flow = "client-route:process:1234"
        projected = self.projector.project(decoded_event(
            "world_info_prefix",
            {"fields": {
                "result": 0,
                "character_uid": 987654321,
                "character_name": "",
                "level": 66,
            }},
            flow=flow,
            opcode=0x0106,
        ), "sessao-1")

        self.assertIsNone(projected)
        self.assertFalse(self.projector.character_confirmed_for_connection(flow))

    def test_non_item_rewards_are_not_exported_as_drops(self):
        projected = self.projector.project(decoded_event(
            "drop_item_field",
            {"ret": 0, "results": [
                {"ret": 0, "item_index": 1, "count": 500_000, "gain_total": 9_000_000},
                {"ret": 0, "item_index": 900, "count": 250_000},
                {"ret": 0, "item_index": 1701, "count": 6000},
                {"ret": 0, "item_index": 158003, "count": 2},
            ]},
            opcode=0x040A,
        ), "sessao-1")

        self.assertEqual(projected["payload"]["items"], [{
            "result": 0, "item_index": 158003, "count": 2,
        }])
        self.assertEqual(projected["payload"]["credits_gained"], 500_000)
        self.assertEqual(projected["payload"]["credits_total"], 9_000_000)

    def test_exp_ranking_only_projects_complete_top100_once(self):
        projected = None
        for page in range(10):
            records = []
            for rank in range(page * 10 + 1, page * 10 + 11):
                records.append({
                    "character_uid": 10_000 + rank,
                    "character_uid_repeat": 10_000 + rank,
                    "character_name": f"Personagem {rank}",
                    "guild_name": "Guilda",
                    "guild_mark_hex": "84000457",
                    "profile_uid_raw": 999,
                    "profile_value_raw": 123,
                    "total_exp": 1_000_000 - rank,
                    "rank": rank,
                    "previous_rank": rank,
                    "scope_id_raw": 1,
                    "ranking_cycle_raw": 44,
                })
            result = self.projector.project(decoded_event(
                "exp_rank_list",
                {
                    "field_decode": "captura-layout-exato",
                    "records": records,
                },
                offset=page + 1,
                opcode=0x1A02,
            ), "sessao-1")
            if page < 9:
                self.assertIsNone(result)
            else:
                projected = result

        self.assertIsNotNone(projected)
        self.assertEqual(projected["type"], "community.exp_ranking_snapshot")
        payload = projected["payload"]
        self.assertEqual(payload["record_count"], 100)
        self.assertEqual(payload["completeness"], "complete")
        self.assertEqual(len(payload["ranking_records"]), 100)
        serialized = json.dumps(projected)
        for private in (
            "character_uid", "guild_mark", "profile_uid", "scope_id",
            "ranking_cycle",
        ):
            self.assertNotIn(private, serialized)
        assert_no_forbidden_keys(self, projected)

        duplicate = self.projector.project(decoded_event(
            "exp_rank_list",
            {
                "field_decode": "captura-layout-exato",
                "records": [{
                    "character_uid": 10_001,
                    "character_uid_repeat": 10_001,
                    "character_name": "Personagem 1",
                    "guild_name": "Guilda",
                    "total_exp": 999_999,
                    "rank": 1,
                    "previous_rank": 1,
                    "scope_id_raw": 1,
                    "ranking_cycle_raw": 44,
                }],
            },
            offset=11,
            opcode=0x1A02,
        ), "sessao-1")
        self.assertIsNone(duplicate)

    def test_faction_ranking_projects_only_complete_full_top100(self):
        records = [{
            "character_uid": 20_000 + rank,
            "character_name": f"Personagem {rank}",
            "biosuit_index": 5000,
            "guild_id": rank,
            "guild_name": "Guilda",
            "guild_mark_raw": 123,
            "rank": rank,
            "contribution": float(1_000_000 - rank),
        } for rank in range(1, 101)]
        event = decoded_event(
            "realm_contribution_rank_list",
            {
                "field_decode": "captura-layout-exato",
                "fields": {
                    "faction_name": "bellato",
                    "rank_variant_raw": 0,
                    "rank_variant_name": "full_list",
                },
                "record_count": 100,
                "records": records,
            },
            opcode=0x240B,
        )

        projected = self.projector.project(event, "sessao-1")

        self.assertEqual(projected["type"], "community.faction_ranking_snapshot")
        self.assertEqual(projected["payload"]["faction"], "Bellato")
        self.assertEqual(projected["payload"]["record_count"], 100)
        self.assertEqual(
            projected["payload"]["faction_ranking_records"][0],
            {
                "rank": 1,
                "previous_rank": 0,
                "character_name": "Personagem 1",
                "guild_name": "Guilda",
                "faction_points": 999_999,
            },
        )
        assert_no_forbidden_keys(self, projected)
        event["data"]["records"] = records[:-1]
        self.assertIsNone(self.projector.project(event, "sessao-1"))

    def test_lifecycle_uses_same_opaque_session_reference(self):
        connection = _connection_key(self.identity_event()["flow"])
        scoped = self.projector.connection_session_id("sessao-1", connection)
        started = self.projector.project_lifecycle(
            scoped, "started", occurred_ns=100
        )
        finished = self.projector.project_lifecycle(
            scoped, "finished", reason="finalized", occurred_ns=200
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

    def market_event(self, offset: int) -> dict:
        return self.projector.project(decoded_event(
            "market",
            {
                "ret": 0,
                "exchange_server_type": 1,
                "exchange_item_simple_infos": [{
                    "item_index": 1000150,
                    "enchant_level": 0,
                    "lowest_price": 100 + offset,
                    "highest_price": 100 + offset,
                    "number_of_registered_items": 1,
                }],
            },
            offset=offset,
            opcode=0x1D02,
        ), "sessao-1")

    def test_prioritizes_immediate_then_market_and_ranking_then_realtime(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=10)
        realtime = self.event(1)
        market = self.market_event(2)
        heartbeat = self.projector.project_heartbeat(
            capture_state="active",
            outbox_pending=2,
            client_count=1,
            occurred_ns=1_700_000_000_000_000_003,
        )
        for event in (realtime, market, heartbeat):
            self.assertTrue(outbox.enqueue(event))
        self.assertEqual(outbox.metrics()["priority_counts"], {
            "bulk": 0,
            "realtime": 1,
            "high": 1,
            "immediate": 1,
        })

        immediate_batch = outbox.next_batch()
        self.assertEqual(
            [event["event_id"] for event in immediate_batch["events"]],
            [heartbeat["event_id"]],
        )
        outbox.acknowledge(
            immediate_batch["batch_id"], immediate_batch["last_sequence"]
        )
        high_batch = outbox.next_batch()
        self.assertEqual(
            [event["event_id"] for event in high_batch["events"]],
            [market["event_id"]],
        )
        outbox.acknowledge(high_batch["batch_id"], high_batch["last_sequence"])
        realtime_batch = outbox.next_batch()
        self.assertEqual(
            [event["event_id"] for event in realtime_batch["events"]],
            [realtime["event_id"]],
        )
        self.assertEqual(
            delivery_priority("community.exp_ranking_snapshot"),
            DELIVERY_PRIORITY_HIGH,
        )
        self.assertEqual(
            delivery_priority("community.faction_ranking_snapshot"),
            DELIVERY_PRIORITY_HIGH,
        )
        self.assertEqual(
            delivery_priority("session.lifecycle", {"state": "started"}),
            DELIVERY_PRIORITY_IMMEDIATE,
        )
        self.assertEqual(
            delivery_priority("session.lifecycle", {"state": "finished"}),
            DELIVERY_PRIORITY_REALTIME,
        )
        outbox.close()

    def test_migrates_existing_fifo_outbox_without_losing_events(self):
        event = self.market_event(1)
        connection = sqlite3.connect(self.path)
        connection.execute(
            """CREATE TABLE outbox_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                document BLOB NOT NULL,
                byte_size INTEGER NOT NULL,
                created_ns INTEGER NOT NULL
            )"""
        )
        document = json.dumps(
            event, sort_keys=True, separators=(",", ":")
        ).encode()
        connection.execute(
            """INSERT INTO outbox_events
               (event_id,event_type,occurred_at,document,byte_size,created_ns)
               VALUES(?,?,?,?,?,?)""",
            (
                event["event_id"], event["type"], event["occurred_at"],
                document, len(document), 1,
            ),
        )
        connection.commit()
        connection.close()

        outbox = AgentOutbox(self.path, "install-publica", max_events=10)
        row = outbox.conn.execute(
            "SELECT event_id,delivery_priority FROM outbox_events"
        ).fetchone()
        self.assertEqual(str(row["event_id"]), event["event_id"])
        self.assertEqual(int(row["delivery_priority"]), DELIVERY_PRIORITY_HIGH)
        self.assertEqual(outbox.metrics()["events"], 1)
        outbox.close()

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

    def test_retry_keeps_exact_batch_after_new_events_arrive(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=10)
        outbox.enqueue(self.event(1))
        first = outbox.next_batch()
        outbox.enqueue(self.event(2))

        retry = outbox.next_batch()

        self.assertEqual(retry, first)
        self.assertEqual(retry["last_sequence"], 1)
        outbox.close()

    def test_retry_keeps_exact_batch_after_process_restart(self):
        first_process = AgentOutbox(self.path, "install-publica", max_events=10)
        first_process.enqueue(self.event(1))
        first = first_process.next_batch()
        first_process.close()

        second_process = AgentOutbox(self.path, "install-publica", max_events=10)
        second_process.enqueue(self.event(2))
        retry = second_process.next_batch()
        self.assertEqual(retry, first)
        self.assertEqual(
            second_process.acknowledge(first["batch_id"], first["last_sequence"]),
            1,
        )
        next_batch = second_process.next_batch()
        self.assertEqual(next_batch["first_sequence"], 2)
        second_process.close()

    def test_full_limit_never_deletes_existing_event(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=1)
        outbox.enqueue(self.event(1))
        with self.assertRaises(OutboxFullError):
            outbox.enqueue(self.event(2))
        self.assertEqual(outbox.metrics()["events"], 1)
        outbox.close()

    def test_metrics_remain_non_negative_with_two_process_connections(self):
        first = AgentOutbox(self.path, "install-publica", max_events=10)
        second = AgentOutbox(self.path, "install-publica", max_events=10)
        try:
            first.enqueue(self.event(1))
            second.enqueue(self.event(2))
            batch = second.next_batch()
            self.assertIsNotNone(batch)
            second.acknowledge(batch["batch_id"], batch["last_sequence"])
            self.assertEqual(first.metrics()["events"], 0)
            self.assertEqual(second.metrics()["events"], 0)
            self.assertGreaterEqual(first.metrics()["bytes"], 0)
        finally:
            first.close()
            second.close()

    def test_single_process_updates_counters_without_rescanning_the_outbox(self):
        outbox = AgentOutbox(self.path, "install-publica", max_events=10)
        try:
            with mock.patch.object(
                outbox, "_refresh_counts", wraps=outbox._refresh_counts
            ) as refresh:
                self.assertTrue(outbox.enqueue(self.event(1)))
                self.assertTrue(outbox.enqueue(self.event(2)))
                self.assertEqual(outbox.metrics()["events"], 2)
                batch = outbox.next_batch()
                self.assertEqual(
                    outbox.acknowledge(batch["batch_id"], batch["last_sequence"]),
                    2,
                )
                self.assertEqual(outbox.metrics()["events"], 0)
                refresh.assert_not_called()
        finally:
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

    def test_quarantines_pending_local_only_events_before_delivery(self):
        outbox = AgentOutbox(self.path, "install-publica")
        combat = self.projector.project(decoded_event(
            "use_skill_result",
            {
                "caster_uid": 10,
                "main_target_uid": 20,
                "effect_results": [{"uid": 20, "hp_damage": 100}],
            },
            opcode=0x0602,
        ), "sessao-1")
        exp = self.event(2)
        self.assertTrue(outbox.enqueue(combat))
        self.assertTrue(outbox.enqueue(exp))

        removed = outbox.quarantine_event_types(
            frozenset({"combat.skill_resolved", "boss.position_observed"}),
            reason="local_only_policy",
        )

        self.assertEqual(removed, 1)
        self.assertEqual(outbox.metrics()["local_only_quarantined"], 1)
        batch = outbox.next_batch()
        self.assertEqual(
            [event["type"] for event in batch["events"]],
            ["character.exp_changed"],
        )
        rejection = outbox.conn.execute(
            "SELECT event_id,reason FROM outbox_rejections"
        ).fetchone()
        self.assertEqual(tuple(rejection), (
            combat["event_id"], "local_only_policy",
        ))
        outbox.close()


class WebAgentBridgeTest(unittest.TestCase):
    def test_multichunk_inventory_can_retry_after_outbox_fills_mid_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            # Ciclo + identidade + primeiro chunk ocupam os tres lugares; o
            # segundo chunk falha e precisa liberar a supressao do snapshot.
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3",
                "install-publica",
                max_events=3,
            )
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            items = [{
                "inventory_slot": slot,
                "item_uid": slot + 1,
                "item_index": 158_003 + slot,
                "count": slot + 1,
                "enchant_level": 0,
                "lock": False,
            } for slot in range(257)]
            snapshot = {
                "type": "inventory_snapshot",
                "container": "inventory",
                "item_kind": "stackable",
                "items": items,
            }
            self.assertTrue(bridge.submit(decoded_event(
                "inventory_snapshot", snapshot, offset=2,
            )))
            bridge.wait_until_idle()

            first_attempt = drain_outbox(outbox)
            self.assertEqual(bridge.metrics()["errors_by_type"], {
                "inventory_snapshot": 1,
            })
            self.assertEqual(
                [event["payload"]["chunk_index"] for event in first_attempt
                 if event["type"] == "inventory.snapshot"],
                [1],
            )

            self.assertTrue(bridge.submit(decoded_event(
                "inventory_snapshot", snapshot, offset=3,
            )))
            bridge.wait_until_idle()
            retried = [
                event for event in drain_outbox(outbox)
                if event["type"] == "inventory.snapshot"
            ]

            self.assertEqual(
                [event["payload"]["chunk_index"] for event in retried],
                [1, 2],
            )
            self.assertEqual(
                {event["payload"]["chunk_count"] for event in retried},
                {2},
            )
            self.assertEqual(
                len({event["payload"]["snapshot_ref"] for event in retried}),
                1,
            )
            bridge.close()
            outbox.close()

    def test_server_loot_is_deduplicated_only_between_clients(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            announcement = {"announcements": [{
                "character_uid": 11,
                "player_name": "Alice",
                "item_index": 1000444,
                "count": 1,
                "message_kind": 2,
            }]}
            for offset, flow in (
                (1, "10.0.0.1:50000 -> 10.0.0.2:12020"),
                (2, "10.0.0.1:50001 -> 10.0.0.2:12020"),
                (3, "10.0.0.1:50000 -> 10.0.0.2:12020"),
            ):
                self.assertTrue(bridge.submit(decoded_event(
                    "loot_announcement", announcement,
                    offset=offset, flow=flow, opcode=0x0E09,
                )))
            bridge.wait_until_idle()

            events = [
                event for event in drain_outbox(outbox)
                if event["type"] == "world.drop_announced"
            ]
            self.assertEqual(len(events), 2)
            self.assertEqual(bridge.metrics()["duplicates"], 1)
            bridge.close()
            outbox.close()

    def test_boss_events_preempt_normal_agent_processing(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox, event_observer=observed.append)
            with mock.patch("core.web_agent.threading.Thread.start"):
                bridge.start_session("sessao-prioridade")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "FG2C_ans_boss_position_Message",
                {"uid": 30, "npc_index": 845},
                offset=2,
                opcode=0x031C,
            )))

            bridge.start_session("sessao-prioridade")
            bridge.wait_until_idle()

            self.assertEqual(
                [event["type"] for event in observed],
                [
                    "boss.position_observed",
                    "session.lifecycle",
                    "character.observed",
                ],
            )
            self.assertEqual(
                processing_priority(decoded_event(
                    "use_normal_skill_result",
                    {"_combat_domain": "boss"},
                )),
                PROCESSING_PRIORITY_BOSS,
            )
            self.assertEqual(
                processing_priority(decoded_event("update_exp", {"exp": 1})),
                PROCESSING_PRIORITY_NORMAL,
            )
            bridge.close()
            outbox.close()

    def test_boss_appearance_is_promoted_with_its_context(self):
        stream = LiveEventStream(boss_indexes={845})
        event = decoded_event(
            "appear_monster_list",
            {"units": [{"uid": 30, "npc_index": 845, "max_hp": 10_000}]},
        )

        stream._remember([event])

        self.assertTrue(event["data"]["_contains_boss"])
        self.assertEqual(processing_priority(event), PROCESSING_PRIORITY_BOSS)

    def test_personal_market_waits_for_confirmed_character_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            sale = decoded_event(
                "FL2C_ans_exchange_for_my_sales_list_Message",
                {
                    "message": "FL2C_ans_exchange_for_my_sales_list_Message",
                    "ret": 0,
                    "exchange_server_type": 2,
                    "my_sales_list": [{
                        "exchange_index": 444,
                        "item_info": {
                            "index": 270062, "count": 3, "enchant_level": 7,
                        },
                        "selling_price": 1500,
                    }],
                },
                offset=1,
                opcode=0x1D07,
            )
            self.assertTrue(bridge.submit(sale))
            bridge.wait_until_idle()
            self.assertIsNone(outbox.next_batch())
            self.assertEqual(bridge.metrics()["unconfirmed_by_type"], {
                "market.personal_listing_observed": 1,
                "market.personal_listings_snapshot": 1,
            })

            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=2,
                opcode=0x0106,
            )))
            bridge.wait_until_idle()
            events = drain_outbox(outbox)
            self.assertEqual(
                [event["type"] for event in events],
                [
                    "session.lifecycle", "character.observed",
                    "market.personal_listing_observed",
                    "market.personal_listings_snapshot",
                ],
            )
            bridge.close()

    def test_confirmed_map_change_reaches_outbox_after_identity_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "request_teleport_result",
                {"result": 0, "map_index": 605, "teleport_index": 605},
                offset=1, opcode=0x0409,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=2, opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "request_teleport_result",
                {"result": 0, "map_index": 602, "teleport_index": 602},
                offset=3, opcode=0x0409,
            )))
            bridge.wait_until_idle()

            changes = [
                event for event in drain_outbox(outbox)
                if event["type"] == "map.changed"
            ]
            self.assertEqual([event["payload"] for event in changes], [
                {"map_index": 605},
                {"previous_map_index": 605, "map_index": 602},
            ])
            self.assertEqual(len({event["client_ref"] for event in changes}), 1)
            self.assertEqual(len({event["session_ref"] for event in changes}), 1)
            bridge.close()

    def test_identical_character_state_is_enqueued_once_per_client_session(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            flow = "client-route:process:1234"
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                flow=flow,
                opcode=0x0106,
            )))
            for offset in (2, 3):
                self.assertTrue(bridge.submit(decoded_event(
                    "player_stat",
                    {"fields": {"combat_power": 987_654}},
                    offset=offset,
                    flow=flow,
                    opcode=0x0401,
                )))
            bridge.wait_until_idle()

            rows = outbox.conn.execute(
                "SELECT event_type,COUNT(*) FROM outbox_events "
                "GROUP BY event_type ORDER BY event_type"
            ).fetchall()
            self.assertEqual(dict(rows)["character.observed"], 2)
            self.assertEqual(bridge.metrics()["duplicates"], 1)
            bridge.close()

    def test_remote_enqueue_wakes_delivery_and_exposes_minute_rate(self):
        with tempfile.TemporaryDirectory() as folder:
            notifications = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica"
            )
            bridge = WebAgentBridge(
                projector, outbox,
                delivery_notifier=lambda: notifications.append(True),
            )
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                opcode=0x0106,
            )))
            bridge.wait_until_idle()

            metrics = bridge.metrics()
            self.assertEqual(len(notifications), 2)
            self.assertEqual(metrics["enqueued_events_last_minute"], 2)
            self.assertEqual(metrics["delivery_notify_errors"], 0)
            bridge.close()

    def test_current_boss_protocol_is_exposed_locally_and_never_queued(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox, event_observer=observed.append)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "FG2C_worldboss_hp_sync_Message",
                {"fields": {"f0@0": 7, "f1@4": 9000, "f2@12": 10000}},
                opcode=0x0C07,
            )))
            bridge.wait_until_idle()

            self.assertEqual(observed[-1]["type"], "boss.hp_synced")
            self.assertEqual(observed[-1]["payload"]["values"], [7, 9000, 10000])
            self.assertIsNone(outbox.next_batch())
            bridge.close()

    def test_only_confirmed_pve_combat_enters_remote_outbox(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            for offset, domain in enumerate(("pve", "pvp", "boss", "unknown"), start=2):
                self.assertTrue(bridge.submit(decoded_event(
                    "dying_unit",
                    {
                        "uid": 100 + offset, "killer_uid": 10,
                        "_combat_domain": domain, "_killer_is_client": True,
                    },
                    offset=offset,
                )))
            bridge.wait_until_idle()

            remote = drain_outbox(outbox)
            deaths = [event for event in remote if event["type"] == "combat.entity_died"]
            self.assertEqual(len(deaths), 1)
            self.assertEqual(deaths[0]["payload"]["combat_domain"], "pve")
            self.assertEqual(bridge.metrics()["local_only_by_type"], {
                "combat.entity_died": 3,
            })
            bridge.close()

    def test_live_stream_exports_local_mob_death_as_confirmed_pve_kill(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            stream = LiveEventStream(event_sink=bridge.submit, boss_indexes=set())
            flow = "10.0.0.2:12020 -> 10.0.0.1:50000"
            events = [
                decoded_event(
                    "world_info_prefix",
                    {"fields": {
                        "character_uid": 123,
                        "character_name": "Teste",
                        "level": 66,
                    }},
                    offset=1,
                    flow=flow,
                    opcode=0x0106,
                ),
                decoded_event(
                    "appear_player_list",
                    {"units": [{
                        "character_uid": 123,
                        "uid": 10,
                        "name": "Teste",
                    }]},
                    offset=2,
                    flow=flow,
                ),
                decoded_event(
                    "appear_monster_list",
                    {"units": [{
                        "uid": 30,
                        "npc_index": 100,
                        "max_hp": 1000,
                        "current_hp": 0,
                    }]},
                    offset=3,
                    flow=flow,
                ),
                decoded_event(
                    "dying_unit",
                    {"uid": 30, "killer_uid": 10, "reason": 0},
                    offset=4,
                    flow=flow,
                ),
            ]

            stream._remember(events)
            stream._dispatch_events(events)
            bridge.wait_until_idle()

            remote = drain_outbox(outbox)
            deaths = [
                event for event in remote
                if event["type"] == "combat.entity_died"
            ]
            self.assertEqual(len(deaths), 1)
            self.assertEqual(deaths[0]["payload"]["combat_domain"], "pve")
            self.assertIs(deaths[0]["payload"]["killer_is_client"], True)
            bridge.close()

    def test_live_stream_keeps_confirmed_pve_kills_separate_per_client(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox)
            bridge.start_session("sessao-1")
            stream = LiveEventStream(event_sink=bridge.submit, boss_indexes=set())
            client_events = []
            for index, (character_uid, combat_uid, monster_uid) in enumerate(
                ((123, 10, 30), (456, 20, 40)),
                start=1,
            ):
                flow = f"10.0.0.2:12020 -> 10.0.0.1:{50000 + index}"
                offset = index * 10
                client_events.extend((
                    decoded_event(
                        "world_info_prefix",
                        {"fields": {
                            "character_uid": character_uid,
                            "character_name": f"Teste {index}",
                            "level": 66,
                        }},
                        offset=offset + 1,
                        flow=flow,
                        opcode=0x0106,
                    ),
                    decoded_event(
                        "appear_player_list",
                        {"units": [{
                            "character_uid": character_uid,
                            "uid": combat_uid,
                            "name": f"Teste {index}",
                        }]},
                        offset=offset + 2,
                        flow=flow,
                    ),
                    decoded_event(
                        "appear_monster_list",
                        {"units": [{
                            "uid": monster_uid,
                            "npc_index": 100 + index,
                            "max_hp": 1000,
                            "current_hp": 0,
                        }]},
                        offset=offset + 3,
                        flow=flow,
                    ),
                    decoded_event(
                        "dying_unit",
                        {"uid": monster_uid, "killer_uid": combat_uid},
                        offset=offset + 4,
                        flow=flow,
                    ),
                ))

            stream._remember(client_events)
            stream._dispatch_events(client_events)
            bridge.wait_until_idle()

            deaths = [
                event for event in drain_outbox(outbox)
                if event["type"] == "combat.entity_died"
            ]
            self.assertEqual(len(deaths), 2)
            self.assertEqual(
                {event["payload"]["combat_domain"] for event in deaths},
                {"pve"},
            )
            self.assertTrue(all(
                event["payload"]["killer_is_client"] is True
                for event in deaths
            ))
            self.assertEqual(len({event["client_ref"] for event in deaths}), 2)
            self.assertEqual(len({event["session_ref"] for event in deaths}), 2)
            bridge.close()

    def test_two_connections_only_export_character_data_after_each_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(Path(folder) / "outbox.sqlite3", "install-publica")
            bridge = WebAgentBridge(projector, outbox, event_observer=observed.append)
            bridge.start_session("captura-1")
            flows = (
                "127.0.0.1:51001 -> 10.0.0.2:12020",
                "127.0.0.1:51002 -> 10.0.0.2:12020",
            )
            for offset, flow in enumerate(flows, start=1):
                self.assertTrue(bridge.submit(decoded_event(
                    "update_exp", {"exp": offset * 100, "gain_exp": 100},
                    offset=offset, flow=flow,
                )))
            bridge.wait_until_idle()

            self.assertIsNone(outbox.next_batch())
            self.assertEqual(
                [event["type"] for event in observed],
                ["character.exp_changed", "character.exp_changed"],
            )
            self.assertEqual(bridge.metrics()["unconfirmed_by_type"], {
                "character.exp_changed": 2,
            })

            for index, flow in enumerate(flows, start=1):
                self.assertTrue(bridge.submit(decoded_event(
                    "world_info_prefix",
                    {"fields": {
                        "character_uid": 100 + index,
                        "character_name": f"Personagem {index}",
                        "level": 66,
                    }},
                    offset=10 + index, flow=flow, opcode=0x0106,
                )))
                self.assertTrue(bridge.submit(decoded_event(
                    "update_exp", {"exp": index * 1000, "gain_exp": 100},
                    offset=20 + index, flow=flow,
                )))
            bridge.wait_until_idle()

            events = drain_outbox(outbox)
            exp_events = [event for event in events if event["type"] == "character.exp_changed"]
            lifecycles = [event for event in events if event["type"] == "session.lifecycle"]
            # Os dois eventos anteriores à confirmação são preservados e
            # reenviados após o UID público de cada conexão aparecer.
            self.assertEqual(len(exp_events), 4)
            self.assertEqual(len(lifecycles), 2)
            self.assertEqual(len({event["client_ref"] for event in exp_events}), 2)
            self.assertEqual(len({event["session_ref"] for event in exp_events}), 2)
            self.assertEqual(
                {event["session_ref"] for event in exp_events},
                {event["session_ref"] for event in lifecycles},
            )
            self.assertEqual(bridge.metrics()["identity"]["replayed_total"], 2)
            bridge.close()

    def test_combat_and_boss_are_observed_locally_but_never_queued(self):
        with tempfile.TemporaryDirectory() as folder:
            observed = []
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica"
            )
            bridge = WebAgentBridge(
                projector, outbox, event_observer=observed.append
            )
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "use_normal_skill_result",
                {
                    "caster_uid": 10,
                    "main_target_uid": 20,
                    "effect_results": [{"uid": 20, "hp_damage": 100}],
                    "_combat_domain": "pve",
                },
                offset=2,
                opcode=0x0702,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "FG2C_ans_boss_position_Message",
                {"uid": 30, "npc_index": 845},
                offset=3,
                opcode=0x031C,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=4
            )))
            bridge.wait_until_idle()

            self.assertEqual(
                [event["type"] for event in observed],
                [
                    "boss.position_observed",
                    "session.lifecycle",
                    "character.observed",
                    "combat.normal_attack_resolved",
                    "character.exp_changed",
                ],
            )
            events = drain_outbox(outbox)
            self.assertEqual(
                [event["type"] for event in events],
                [
                    "session.lifecycle", "character.observed",
                    "character.exp_changed",
                ],
            )
            metrics = bridge.metrics()
            self.assertEqual(metrics["local_only"], 2)
            self.assertEqual(metrics["local_only_by_type"], {
                "combat.normal_attack_resolved": 1,
                "boss.position_observed": 1,
            })
            bridge.close()

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
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=2
            )))
            bridge.wait_until_idle()

            self.assertEqual(
                [event["type"] for event in observed],
                [
                    "session.lifecycle", "character.observed",
                    "character.exp_changed",
                ],
            )
            self.assertEqual(bridge.metrics()["outbox_events"], 1)
            self.assertEqual(bridge.metrics()["errors"], 2)
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
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=2
            )))
            bridge.wait_until_idle()

            self.assertEqual(bridge.metrics()["outbox_events"], 3)
            self.assertEqual(bridge.metrics()["errors"], 0)
            self.assertEqual(bridge.metrics()["observer_errors"], 3)
            bridge.close()

    def test_bridge_is_nonblocking_and_isolates_outbox_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            projector = WebEventProjector(
                "install-publica", b"0123456789abcdef0123456789abcdef",
                decoder_version="test",
            )
            outbox = AgentOutbox(
                Path(folder) / "outbox.sqlite3", "install-publica", max_events=3
            )
            bridge = WebAgentBridge(projector, outbox, max_queue_events=8)
            bridge.start_session("sessao-1")
            self.assertTrue(bridge.submit(decoded_event(
                "world_info_prefix",
                {"fields": {
                    "character_uid": 123,
                    "character_name": "Teste",
                    "level": 66,
                }},
                offset=1,
                opcode=0x0106,
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 100, "gain_exp": 100}, offset=2
            )))
            self.assertTrue(bridge.submit(decoded_event(
                "update_exp", {"exp": 200, "gain_exp": 100}, offset=3
            )))
            self.assertFalse(bridge.submit(decoded_event("unparsed", {}, offset=4)))
            bridge.wait_until_idle()
            metrics = bridge.metrics()
            self.assertEqual(metrics["outbox_events"], 3)
            self.assertEqual(metrics["errors"], 1)
            self.assertEqual(metrics["ignored"], 1)
            self.assertEqual(metrics["accepted_by_type"], {
                "world_info_prefix": 1,
                "update_exp": 2,
            })
            self.assertEqual(metrics["ignored_by_type"], {"unparsed": 1})
            self.assertEqual(
                metrics["projected_by_type"],
                {
                    "session.lifecycle": 1,
                    "character.observed": 1,
                    "character.exp_changed": 1,
                },
            )
            self.assertEqual(metrics["errors_by_type"], {"update_exp": 1})
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
        self.assertEqual(metrics["event_sink_errors_by_type"], {"unknown": 1})
        self.assertEqual(metrics["event_sink_rejected_by_type"], {"unknown": 1})
        self.assertEqual(metrics["event_sink_accepted_by_type"], {"unknown": 1})

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

            events = drain_outbox(outbox)
            self.assertEqual(len(events), 4)
            self.assertEqual(
                [event["payload"].get("state") for event in events],
                ["started", None, None, "finished"],
            )
            self.assertIsNotNone(events[2]["client_ref"])
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
