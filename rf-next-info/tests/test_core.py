import ctypes
import json
import os
import sqlite3
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import core.rfnext_frame_decode as rfnext_decoder
from core.capture import PktmonCapture, _pktmon_running, _pktmon_state
from core.pktmon_realtime import (
    RealtimeCapture,
    _normalized_timestamp_ns,
    _DataSourceList,
    _data_source_pointers,
    _matches_tcp_port,
    split_pcap_by_ports,
)
from core.connections import (
    agent_processes,
    clients_for_executable,
    connected_processes,
    emulator_processes,
    ports_for_executable,
)
from core.combat_monitor import summarize_combat
from core.auction_sales import (
    auction_sales_snapshot,
    auction_transaction_history,
    undercut_warning,
)
from core.drop_alerts import (
    aggregate_item_drops_by_client,
    confirmed_item_drop_alerts,
)
from core.ingest import _decode_stream_resync, _pcapng_to_pcap, _safe_parse
from core.live_stream import LiveEventDecoder, LiveEventStream
from core.map_state import (
    MAP_CATALOG,
    MAP_PREVIEW_CATALOG,
    MapModule,
    apply_manual_map_fallbacks,
    map_name,
    map_region,
)
from core.knowledge import KnowledgeStore
from core.rfnext_frame_decode import (
    APPEAR_PLAYER_PREFIX,
    APPEAR_PLAYER_STATE,
    APPEAR_PLAYER_TAIL_SIZE,
    HEADER_SIZE,
    parse_guild_relation_payload,
    parse_exp_rank_payload,
    parse_inventory_payload,
    parse_marked_gameplay_payload,
    parse_observation_payload,
    parse_player_stat_payload,
    pcap_tcp_streams,
)
from core.store import CaptureStore, exp_rank_level_progress


class CoreTest(unittest.TestCase):
    @staticmethod
    def _decoder_frame(opcode: int, payload: bytes) -> bytes:
        frame = bytearray(HEADER_SIZE + len(payload))
        frame[4:6] = opcode.to_bytes(2, "little")
        frame[6:] = payload
        return bytes(frame)

    def test_latest_decoder_extracts_combat_power_from_player_and_lobby_stats(self):
        player_payload = bytearray(786)
        struct.pack_into("<Q", player_payload, 772, 987_654)
        player = parse_player_stat_payload(
            self._decoder_frame(0x0401, bytes(player_payload)), 12010
        )
        self.assertEqual(player["type"], "player_stat")
        self.assertEqual(player["fields"]["combat_power"], 987_654)

        lobby_payload = bytearray(762)
        struct.pack_into("<Q", lobby_payload, 752, 123_456)
        lobby = parse_player_stat_payload(
            self._decoder_frame(0x0423, bytes(lobby_payload)), 12010
        )
        self.assertEqual(lobby["type"], "lobby_stat")
        self.assertEqual(lobby["fields"]["combat_power"], 123_456)
        self.assertIsNone(parse_player_stat_payload(
            self._decoder_frame(0x0401, bytes(player_payload)), 12020
        ))

    def test_ingest_keeps_27_stackable_snapshot_distinct_from_player_stat(self):
        items = [
            struct.pack(
                "<H6sIQBQ",
                slot,
                (slot + 1).to_bytes(6, "little"),
                158_003 + slot,
                slot + 1,
                0,
                0,
            )
            for slot in range(27)
        ]
        inventory = self._decoder_frame(
            0x0401, struct.pack("<BH", 1, len(items)) + b"".join(items)
        )
        player_stat = self._decoder_frame(0x0401, bytes(786))
        ambiguous_stat = bytearray(786)
        ambiguous_stat[1:3] = (27).to_bytes(2, "little")
        for slot in range(27):
            record_offset = 3 + slot * 29
            struct.pack_into("<I", ambiguous_stat, record_offset + 8, 1)
            struct.pack_into("<Q", ambiguous_stat, record_offset + 12, 2**40)

        parsed_inventory = _safe_parse(
            rfnext_decoder, inventory, 12010,
        )
        parsed_player = _safe_parse(
            rfnext_decoder, player_stat, 12010,
        )
        parsed_ambiguous_stat = _safe_parse(
            rfnext_decoder,
            self._decoder_frame(0x0401, bytes(ambiguous_stat)),
            12010,
        )

        self.assertEqual(len(inventory) - HEADER_SIZE, 786)
        self.assertEqual(parsed_inventory["type"], "inventory_snapshot")
        self.assertEqual(parsed_inventory["item_kind"], "stackable")
        self.assertEqual(parsed_inventory["item_count"], 27)
        self.assertEqual(parsed_player["type"], "player_stat")
        self.assertEqual(parsed_ambiguous_stat["type"], "player_stat")

    def test_pktmon_timestamp_normalizer_rejects_invalid_filetime_values(self):
        now_ns = 1_800_000_000_000_000_000

        self.assertEqual(
            _normalized_timestamp_ns(1_700_000_000_000_000_000, now_ns),
            1_700_000_000_000_000_000,
        )
        self.assertEqual(_normalized_timestamp_ns(-(2**80), now_ns), now_ns)
        self.assertEqual(_normalized_timestamp_ns(2**80, now_ns), now_ns)
        self.assertEqual(_normalized_timestamp_ns("invalido", now_ns), now_ns)

    def test_server_chat_loot_announcements_decode_single_and_list(self):
        def record(
            uid: int, name: str, item_index: int, count: int, kind: int = 2
        ) -> bytes:
            encoded_name = name.encode("utf-16le")
            tail = bytearray(65)
            tail[21] = kind
            tail[27] = 1
            struct.pack_into("<I", tail, 37, item_index)
            struct.pack_into("<I", tail, 41, count)
            return (
                struct.pack("<QH", uid, len(name))
                + encoded_name
                + bytes(tail)
            )

        single = parse_observation_payload(
            self._decoder_frame(0x0E09, record(11, "Alice", 1000444, 1))
        )
        listed = parse_observation_payload(
            self._decoder_frame(
                0x0E0A,
                struct.pack("<H", 2)
                + record(13, "Carol", 1000156, 1, kind=3)
                + record(12, "Bob", 1000323, 2),
            )
        )

        self.assertEqual(single["type"], "loot_announcement")
        self.assertEqual(single["announcements"], [{
            "character_uid": 11,
            "player_name": "Alice",
            "item_index": 1000444,
            "count": 1,
            "message_kind": 2,
        }])
        self.assertEqual(
            [(row["player_name"], row["item_index"], row["count"])
             for row in listed["announcements"]],
            [("Bob", 1000323, 2)],
        )
        self.assertIsNone(parse_observation_payload(
            self._decoder_frame(
                0x0E0A,
                struct.pack("<H", 1)
                + record(13, "Carol", 1000156, 1, kind=3),
            )
        ))

    def test_latest_marked_decoder_movement_disappear_teleport_and_equipment(self):
        movement_payload = bytes.fromhex(
            "00014436bc5e4373cd53440000000003d1c143d699a343fe2c8341360d4d13000000"
        )
        movement = parse_marked_gameplay_payload(
            self._decoder_frame(0x0301, movement_payload), 12010
        )
        self.assertEqual(movement["type"], "move_player_request")
        self.assertTrue(movement["fields"]["moving_flag"])
        self.assertAlmostEqual(movement["fields"]["position"][0], 387.633, places=3)
        movement_update = parse_marked_gameplay_payload(
            self._decoder_frame(
                0x0302, struct.pack("<I", 268_525_523) + movement_payload[:-2]
            ),
            12010,
        )
        self.assertEqual(movement_update["fields"]["entity_uid"], 268_525_523)

        exit_room = parse_marked_gameplay_payload(
            self._decoder_frame(
                0x0204, bytes.fromhex("993d194205a95955d600001000")
            ),
            12010,
        )
        self.assertEqual(exit_room["type"], "exit_room_result")
        self.assertEqual(exit_room["fields"]["entity_uid"], 268_435_670)

        disappear = parse_marked_gameplay_payload(
            self._decoder_frame(0x030A, struct.pack("<HIB", 1, 268_435_670, 2)),
            12010,
        )
        self.assertEqual(disappear["fields"]["entity_uids"], [268_435_670])
        self.assertEqual(disappear["fields"]["units"][0]["reason"], "random_teleport")
        from core import rfnext_frame_decode as decoder
        self.assertEqual(
            _safe_parse(
                decoder,
                self._decoder_frame(0x030A, struct.pack("<HIB", 1, 268_435_670, 2)),
                12010,
            )["type"],
            "disappear_unit_list",
        )
        self.assertIsNone(
            parse_marked_gameplay_payload(
                self._decoder_frame(0x030A, struct.pack("<H", 1)), 12010
            )
        )

        warp_payload = bytes.fromhex("d35f01103fff9743c4daba43819581410000b20400000000")
        warp = parse_marked_gameplay_payload(
            self._decoder_frame(0x040A, warp_payload), 12010
        )
        self.assertEqual(warp["type"], "warp_player")
        self.assertEqual(warp["fields"]["map_index_candidate"], 1202)
        self.assertEqual(
            warp["fields"]["map_index_candidate_status"],
            "refuted-not-map-index",
        )
        for opcode, payload, event_type in (
            (0x0408, bytes.fromhex("5d020000"), "request_teleport"),
            (0x0409, bytes.fromhex("00005d020000"), "request_teleport_result"),
            (0x040B, b"", "end_warp_player"),
        ):
            with self.subTest(opcode=opcode):
                parsed = parse_marked_gameplay_payload(
                    self._decoder_frame(opcode, payload), 12010
                )
                self.assertEqual(parsed["type"], event_type)
                if opcode != 0x040B:
                    self.assertEqual(parsed["fields"]["map_index"], 605)

        logical_teleports = (
            (
                0x0324,
                bytes.fromhex(
                    "07000000870300000000000001000000000000005a02000000"
                    "9004864242f49c43afaa84410000000000000000000000000000000000000000000000000000"
                ),
                "teleport_request",
                "requested_position",
            ),
            (
                0x0325,
                bytes.fromhex(
                    "000007000000870300000000000001000000000000005a02000000"
                    "9004864242f49c433af8844100000000"
                ),
                "teleport_response",
                "resolved_position",
            ),
        )
        for opcode, payload, event_type, position_field in logical_teleports:
            parsed = parse_marked_gameplay_payload(
                self._decoder_frame(opcode, payload), 12020
            )
            self.assertEqual(parsed["type"], event_type)
            self.assertEqual(parsed["fields"]["map_index"], 602)
            self.assertEqual(parsed["fields"]["teleport_kind"], "random")
            self.assertEqual(len(parsed["fields"][position_field]), 3)

        equip = parse_marked_gameplay_payload(
            self._decoder_frame(
                0x0501, struct.pack("<HBQ", 1, 7, 0x01D038EA22F80002)
            ),
            12020,
        )
        self.assertEqual(equip["fields"]["equipment_part"], "ear_cuffs")
        equip_response = parse_marked_gameplay_payload(
            self._decoder_frame(
                0x0502,
                struct.pack("<HHHBQ", 0, 225, 1, 1, 0x01D038EB29400014),
            ),
            12020,
        )
        self.assertEqual(equip_response["fields"]["result"], 0)
        self.assertEqual(equip_response["fields"]["equipment_part"], "weapon")

    def test_latest_decoder_reads_exp_rank_and_ingest_routes_it(self):
        name, guild = "Carvalho", "BLOOD"
        record = (
            struct.pack(
                "<QQIIIIQ",
                6_150_132_606_160_036_456,
                28_502_264_098,
                102,
                101,
                1,
                44_594_176,
                6_150_132_606_160_036_456,
            )
            + struct.pack("<H", len(name))
            + name.encode("utf-16le")
            + struct.pack("<QI", 8_975_062_754_656_233_889, 142_633)
            + struct.pack("<H", len(guild))
            + guild.encode("utf-16le")
            + bytes.fromhex("84000457")
        )
        frame = self._decoder_frame(0x1A02, struct.pack("<H", 1) + record)
        parsed = parse_exp_rank_payload(frame, 12020)
        self.assertEqual(parsed["records"][0]["rank"], 102)
        self.assertEqual(parsed["records"][0]["guild_name"], "BLOOD")
        from core import rfnext_frame_decode as decoder
        self.assertEqual(_safe_parse(decoder, frame, 12020)["type"], "exp_rank_list")
        self.assertIsNone(parse_exp_rank_payload(frame, 12010))

    def test_disappear_event_removes_player_from_live_state_immediately(self):
        stream = LiveEventStream()
        flow = "127.0.0.1:12010 -> 127.0.0.1:50000"
        stream._remember([
            {
                "flow": flow,
                "ts_ns": 1,
                "type": "appear_player_list",
                "data": {"units": [{"uid": 20, "character_uid": 222, "name": "Rival"}]},
            },
            {
                "flow": flow,
                "ts_ns": 2,
                "type": "disappear_unit_list",
                "data": {"fields": {"entity_uids": [20]}},
            },
        ])

        self.assertNotIn(
            20,
            {
                int(unit["uid"])
                for event in stream.snapshot()
                if event.get("type") == "appear_player_list"
                for unit in (event.get("data") or {}).get("units") or []
            },
        )

    def test_pvp_nearby_appearance_expires_after_ten_seconds_without_disappear(self):
        events = [{
            "ts_ns": 1_000_000_000,
            "type": "appear_player_list",
            "data": {"units": [{
                "uid": 20, "character_uid": 222, "name": "Rival",
            }]},
        }]

        visible = summarize_combat(
            events, "111", modes=("pvp",), now_ns=11_000_000_000
        )
        expired = summarize_combat(
            events, "111", modes=("pvp",), now_ns=11_000_000_001
        )

        self.assertEqual([row["name"] for row in visible["nearby_players"]], ["Rival"])
        self.assertEqual(expired["nearby_players"], [])

    def test_map_module_tracks_local_and_nearby_positions_without_uids(self):
        flow = "10.0.0.1:12010 -> 127.0.0.1:50000"
        events = [{
            "flow": flow,
            "ts_ns": 1_000_000_000,
            "type": "world_info_prefix",
            "data": {"fields": {
                "character_uid": 987_654_321,
                "character_name": "Local",
            }},
        }, {
            "flow": flow,
            "ts_ns": 2_000_000_000,
            "type": "appear_player_list",
            "data": {"units": [{
                "uid": 10,
                "character_uid": 987_654_321,
                "name": "Local",
                "position_x": 9.0,
                "position_y": 0.0,
                "position_z": 0.0,
            }, {
                "uid": 246_813_579,
                "character_uid": 222,
                "name": "Vizinho",
                "guild_name": "Guilda",
                "position_x": 12.0,
                "position_y": 4.0,
                "position_z": 0.0,
            }]},
        }, {
            "flow": flow,
            "ts_ns": 3_000_000_000,
            "type": "move_player_request",
            "data": {"fields": {"position": [10.0, 0.0, 0.0]}},
        }, {
            "flow": flow,
            "ts_ns": 4_000_000_000,
            "type": "move_player_update",
            "data": {"fields": {
                "entity_uid": 246_813_579,
                "position": [13.0, 4.0, 0.0],
            }},
        }, {
            "flow": flow,
            "ts_ns": 4_500_000_000,
            "type": "teleport_response",
            "data": {"fields": {
                "result": 0,
                "map_index": 602,
                "resolved_position": [19.0, 0.0, 0.0],
            }},
        }, {
            "flow": flow,
            "ts_ns": 5_000_000_000,
            "type": "warp_player",
            "data": {"fields": {
                "entity_uid": 10,
                "position": [20.0, 0.0, 0.0],
                "map_index_candidate": 1202,
                "map_index_candidate_status": "refuted-not-map-index",
            }},
        }]

        snapshot = MapModule().snapshot(
            events, ((50000,),), now_ns=5_000_000_000
        )

        client = snapshot["clients"][0]
        self.assertEqual(client["map_index"], 602)
        self.assertEqual(client["map_name"], "Base Secreta Nemesis")
        self.assertEqual(client["region_name"], "2F")
        self.assertEqual(client["region_confidence"], "map-index-floor")
        self.assertEqual(client["position"], {"x": 20.0, "y": 0.0, "z": 0.0})
        self.assertEqual(client["nearby_players"][0]["name"], "Vizinho")
        self.assertEqual(client["nearby_players"][0]["distance"], 8.062)
        public = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("987654321", public)
        self.assertNotIn("246813579", public)
        self.assertNotIn("entity_uid", public)
        self.assertNotIn("character_uid", public)

        english = MapModule(language="en").snapshot(
            events, ((50000,),), now_ns=5_000_000_000
        )
        self.assertEqual(english["clients"][0]["map_name"], "Secret Nemesis Base")
        self.assertEqual(english["clients"][0]["region_name"], "2F")

    def test_map_module_expires_unfinished_teleport_and_movement_clears_it(self):
        flow = "10.0.0.1:12010 -> 127.0.0.1:50000"
        teleport = {
            "flow": flow,
            "ts_ns": 1_000_000_000,
            "type": "request_teleport",
            "data": {"fields": {"map_index": 643}},
        }
        expired = MapModule().snapshot(
            [teleport], ((50000,),), now_ns=11_000_000_001
        )["clients"][0]
        self.assertFalse(expired["teleporting"])

        moved = MapModule().snapshot(
            [teleport, {
                "flow": flow,
                "ts_ns": 2_000_000_000,
                "type": "move_player_request",
                "data": {"fields": {"position": [1.0, 2.0, 3.0]}},
            }],
            ((50000,),),
            now_ns=2_000_000_000,
        )["clients"][0]
        self.assertFalse(moved["teleporting"])

    def test_map_catalog_is_versioned_complete_and_has_safe_fallback(self):
        self.assertEqual(len(MAP_CATALOG), 508)
        self.assertEqual(map_name(101, "pt"), "Mundo Novus")
        self.assertEqual(map_name(101, "en"), "Novus World")
        self.assertEqual(map_name(638, "en"), "Android Junkyard")
        self.assertEqual(map_region(638, None, "en")["region_name"], "8F")
        self.assertEqual(map_name(4_294_967_294, "pt"), "Mapa #4294967294")

    def test_map_preview_catalog_covers_requested_maps_and_novus_regions(self):
        requested = {
            101, 103,
            751, 752, 754, 755,
            *range(635, 641), *range(4211, 4215),
            601, 602, 605, 606, 607,
            *range(611, 627), 4625, 4645, 4665, 4685,
            610, 630, 4603,
            642, 643, 644, 4504, 4554,
        }

        self.assertEqual(set(MAP_PREVIEW_CATALOG), requested)
        self.assertEqual(
            sum(len(item.get("regions") or []) for item in MAP_PREVIEW_CATALOG.values()),
            100,
        )
        high_orbit = map_region(
            643,
            {"x": 1182.8017578125, "y": 683.6202392578125, "z": 0.0},
            "pt",
        )
        self.assertEqual(high_orbit["region_index"], 591001)
        self.assertEqual(high_orbit["region_name"], "Doca A-04")
        self.assertEqual(MAP_PREVIEW_CATALOG[635]["asset_source_map_index"], 631)
        self.assertEqual(MAP_PREVIEW_CATALOG[4645]["asset_source_map_index"], 4625)
        self.assertEqual(
            MAP_PREVIEW_CATALOG[635]["evidence"],
            "shared-level-layout-static-coordinate-match",
        )

        position = {"x": -478_707.281, "y": 89_840.0, "z": 0.0}
        portuguese = map_region(101, position, "pt")
        english = map_region(101, position, "en")
        self.assertEqual(portuguese["region_name"], "Colônia Saura")
        self.assertEqual(english["region_name"], "Saura Colony")
        self.assertEqual(
            portuguese["region_confidence"], "nearest-official-center"
        )
        self.assertEqual(portuguese["region_center"], position)

    def test_manual_map_is_only_a_fallback_for_unresolved_automatic_name(self):
        snapshot = {
            "clients": [{
                "client_key": "client:a",
                "map_index": 4_294_967_294,
                "map_name": "Mapa #4294967294",
            }, {
                "client_key": "client:b",
                "map_index": 602,
                "map_name": "Base Secreta Nemesis 2º Andar",
            }]
        }
        configured = {
            "client:a": {"map_name": "Mapa informado", "map_index": 639},
            "client:b": {"map_name": "Não deve substituir"},
        }

        applied = apply_manual_map_fallbacks(snapshot, configured)

        self.assertEqual(applied["clients"][0]["map_name"], "Mapa informado")
        self.assertEqual(applied["clients"][0]["map_source"], "manual_fallback")
        self.assertEqual(applied["clients"][0]["map_index"], 639)
        self.assertEqual(
            applied["clients"][0]["automatic_map_name"], "Mapa #4294967294"
        )
        self.assertEqual(
            applied["clients"][1]["map_name"], "Base Secreta Nemesis 2º Andar"
        )
        self.assertEqual(applied["clients"][1]["map_source"], "automatic")
        restored = apply_manual_map_fallbacks(applied, {})
        self.assertEqual(restored["clients"][0]["map_name"], "Mapa #4294967294")
        self.assertEqual(restored["clients"][0]["map_index"], 4_294_967_294)

    def test_map_module_limits_two_clients_and_releases_missing_route(self):
        module = MapModule()
        flows = [
            f"10.0.0.1:12010 -> 127.0.0.1:{port}"
            for port in (50000, 50001, 50002)
        ]
        events = [{
            "flow": flow,
            "ts_ns": index + 1,
            "type": "move_player_request",
            "data": {"fields": {"position": [index, 0, 0]}},
        } for index, flow in enumerate(flows)]

        first = module.snapshot(events, ((50000,), (50001,), (50002,)))

        self.assertEqual(first["active_count"], 2)
        self.assertEqual(first["limited_count"], 1)
        self.assertEqual(
            [(row["client_key"], row["map_enabled"]) for row in first["clients"]],
            [("client:a", True), ("client:b", True), ("client:c", False)],
        )
        self.assertIsNone(first["clients"][2]["position"])

        second = module.snapshot(events, ((), (50001,), (50002,)))

        self.assertEqual(
            [(row["client_key"], row["map_enabled"]) for row in second["clients"]],
            [("client:b", True), ("client:c", True)],
        )

    def test_live_stream_retains_latest_map_event_and_removes_disappearance(self):
        stream = LiveEventStream()
        flow = "10.0.0.1:12010 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow,
            "ts_ns": 1,
            "type": "appear_player_list",
            "data": {"units": [{"uid": 20, "character_uid": 222, "name": "Rival"}]},
        }, {
            "flow": flow,
            "ts_ns": 2,
            "type": "move_player_update",
            "data": {"fields": {"entity_uid": 20, "position": [1, 2, 3]}},
        }])

        self.assertTrue(any(
            event.get("type") == "move_player_update" for event in stream.snapshot()
        ))
        self.assertEqual(stream.metrics()["map_events"], 1)

        stream._remember([{
            "flow": flow,
            "ts_ns": 3,
            "type": "disappear_unit_list",
            "data": {"fields": {"entity_uids": [20]}},
        }])

        self.assertFalse(any(
            event.get("type") in {"appear_player_list", "move_player_update"}
            for event in stream.snapshot()
        ))
        self.assertEqual(stream.metrics()["map_events"], 0)

    def test_live_stream_retains_teleport_result_for_automatic_map(self):
        stream = LiveEventStream()
        flow = "10.0.0.1:12020 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow,
            "ts_ns": 1,
            "type": "teleport_request",
            "data": {"fields": {"map_index": 602}},
        }, {
            "flow": flow,
            "ts_ns": 2,
            "type": "teleport_response",
            "data": {"fields": {
                "result": 0,
                "map_index": 602,
                "resolved_position": [19.0, 0.0, 0.0],
            }},
        }])

        snapshot = MapModule().snapshot(
            stream.snapshot(), ((50000,),), now_ns=2
        )

        self.assertEqual(stream.metrics()["map_events"], 2)
        self.assertEqual(snapshot["clients"][0]["map_index"], 602)
        self.assertEqual(
            snapshot["clients"][0]["map_name"],
            "Base Secreta Nemesis",
        )
        self.assertEqual(snapshot["clients"][0]["region_name"], "2F")
        self.assertEqual(
            snapshot["clients"][0]["position"],
            {"x": 19.0, "y": 0.0, "z": 0.0},
        )

    def test_guild_relation_decode_enriches_pvp_without_overwriting_manual(self):
        guild_name = "Guilda Rival".encode("utf-16le")
        representative = "Líder".encode("utf-16le")
        payload = (
            struct.pack("<HQHQH", 0, 100, 1, 200, len("Guilda Rival"))
            + guild_name
            + struct.pack("<BHBBH", 0, 0, 0, 0, len("Líder"))
            + representative
            + struct.pack("<H", 0)
        )
        frame = bytearray(HEADER_SIZE + len(payload))
        frame[4:6] = (0x0D3F).to_bytes(2, "little")
        frame[6:] = payload
        relation = parse_guild_relation_payload(frame)
        self.assertEqual(relation["relation"], "enemy")
        self.assertEqual(relation["guilds"][0]["guild_name"], "Guilda Rival")
        from core import rfnext_frame_decode as decoder
        self.assertEqual(
            _safe_parse(decoder, bytes(frame), 12020)["type"],
            "enemy_guild_list",
        )

        tail = bytearray(APPEAR_PLAYER_TAIL_SIZE - APPEAR_PLAYER_STATE.size)
        struct.pack_into("<Q", tail, 43, 200)
        player_name = "Rival"
        player_payload = (
            struct.pack("<H", 1)
            + APPEAR_PLAYER_PREFIX.pack(222, 0, 1, 0, 2, 0, len(player_name))
            + player_name.encode("utf-16le")
            + APPEAR_PLAYER_STATE.pack(20, 2, 1000, 900, 100, 100, 0, 0.0, 0.0, 0.0)
            + tail
        )
        player_frame = bytearray(HEADER_SIZE + len(player_payload))
        player_frame[4:6] = (0x0305).to_bytes(2, "little")
        player_frame[6:] = player_payload
        player = parse_observation_payload(player_frame)["units"][0]
        self.assertEqual(player["guild_id"], 200)

        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([
                    {"type": relation["type"], "data": relation},
                    {"type": "appear_player_list", "data": {"units": [player]}},
                ])
                observed = store.characters()[0]
                current_relation = [{
                    "nearby_players": [{
                        "character_uid": "222", "pvp_status": "ally"
                    }],
                    "bosses": [],
                }]
                store.enrich_combat_monitors(current_relation)
                store.update_pvp_identity(
                    222, guild_name="Guilda manual", status="neutral"
                )
                store.observe_events([
                    {"type": relation["type"], "data": relation},
                ])
                manual = store.characters()[0]
                manual_relation = [{
                    "nearby_players": [{
                        "character_uid": "222", "pvp_status": "enemy"
                    }],
                    "bosses": [],
                }]
                store.enrich_combat_monitors(manual_relation)
            finally:
                store.close()
        self.assertEqual(
            (observed["guild_name"], observed["pvp_status"], observed["pvp_status_source"]),
            ("Guilda Rival", "enemy", "observed"),
        )
        self.assertEqual(
            (manual["guild_name"], manual["pvp_status"], manual["pvp_status_source"]),
            ("Guilda manual", "neutral", "manual"),
        )
        self.assertEqual(current_relation[0]["nearby_players"][0]["pvp_status"], "ally")
        self.assertEqual(manual_relation[0]["nearby_players"][0]["pvp_status"], "neutral")

    def test_guild_relation_reaches_live_and_combat_snapshots(self):
        relation = {
            "type": "enemy_guild_list",
            "relation": "enemy",
            "guilds": [{"guild_id": 200, "guild_name": "Guilda Rival"}],
        }
        events = [
            {"ts_ns": 9_000_000_000, "type": "enemy_guild_list", "data": relation},
            {
                "ts_ns": 10_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 111, "uid": 10, "name": "Local", "guild_id": 100, "max_hp": 1000, "current_hp": 1000},
                    {"character_uid": 222, "uid": 20, "name": "Rival", "guild_id": 200, "max_hp": 1000, "current_hp": 1000},
                ]},
            },
        ]
        monitor = summarize_combat(events, "111", now_ns=10_000_000_000)
        self.assertEqual(
            (monitor["nearby_players"][0]["guild_name"], monitor["nearby_players"][0]["pvp_status"]),
            ("Guilda Rival", "enemy"),
        )
        stream = LiveEventStream()
        stream._remember([{
            "flow": "flow", "type": "enemy_guild_list", "data": relation,
        }])
        self.assertIn("enemy_guild_list", [item["type"] for item in stream.snapshot()])

    def test_inventory_decoder_and_store_apply_snapshot_and_delta(self):
        def frame(opcode: int, payload: bytes) -> bytes:
            value = bytearray(6 + len(payload))
            value[4:6] = opcode.to_bytes(2, "little")
            value[6:] = payload
            return bytes(value)

        item = struct.pack(
            "<H6sIQBQ", 7, bytes.fromhex("010203040506"), 270062, 12, 0, 0
        )
        snapshot = parse_inventory_payload(frame(0x0401, struct.pack("<BH", 1, 1) + item))
        second = struct.pack(
            "<H6sIQBQ", 7, bytes.fromhex("111213141516"), 270063, 4, 0, 0
        )
        snapshot["items"].append(
            parse_inventory_payload(
                frame(0x0401, struct.pack("<BH", 1, 1) + second)
            )["items"][0]
        )
        delta = parse_inventory_payload(
            frame(
                0x0402,
                struct.pack("<H", 0x011B)
                + struct.pack(
                    "<H6sIQBQ",
                    7,
                    bytes.fromhex("010203040506"),
                    270062,
                    25,
                    0,
                    0,
                ),
            )
        )
        self.assertEqual(snapshot["items"][0]["count"], 12)
        self.assertEqual(delta["item"]["count"], 25)

        with tempfile.TemporaryDirectory() as directory:
            store = CaptureStore(Path(directory) / "capture.sqlite3")
            try:
                for offset, data in enumerate((snapshot, delta), 1):
                    store.conn.execute(
                        """INSERT INTO events(
                           session_id,source,flow,stream_offset,bundle_seq,ts_ns,
                           opcode,type,character_uid,data_json
                           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "session",
                            "memory",
                            "flow",
                            offset,
                            0,
                            offset,
                            0x0400 + offset,
                            data["type"],
                            "101",
                            json.dumps(data),
                        ),
                    )
                current = store.inventory_items("session", "101")
            finally:
                store.close()
        self.assertEqual(len(current), 2)
        self.assertEqual(
            {item["item_index"]: item["count"] for item in current},
            {270062: 25, 270063: 4},
        )

    def test_safe_parse_keeps_only_sanitized_character_list_from_login(self):
        class Decoder:
            class DecodeError(Exception):
                pass

            parse_exchange_payload = staticmethod(lambda _decoded: None)
            parse_collection_payload = staticmethod(lambda _decoded: None)
            parse_observation_payload = staticmethod(lambda _decoded: None)
            parse_marked_gameplay_payload = staticmethod(
                lambda _decoded, _port: None
            )
            parse_job1_payload = staticmethod(lambda _decoded: None)

            @staticmethod
            def parse_login_session_payload(_decoded, _port):
                return {
                    "type": "ans_all_character_infos",
                    "confidence": "teste",
                    "fields": {"characters": [{
                        "character_uid": 123,
                        "level": 68,
                        "name": "Carvalho",
                        "world_id": 1,
                        "guild_name": "Karvalho",
                        "reserved_hex": "segredo",
                        "timestamp_a_ms": 999,
                        "f60": 888,
                    }]},
                }

        parsed = _safe_parse(Decoder, b"login", 12000)

        self.assertEqual(parsed["type"], "ans_all_character_infos")
        self.assertEqual(parsed["fields"]["character_count"], 1)
        character = parsed["fields"]["characters"][0]
        self.assertEqual(
            set(character),
            {"character_uid", "level", "name", "world_id", "guild_name"},
        )
        self.assertNotIn("segredo", json.dumps(parsed))

    def test_knowledge_store_persists_only_decoded_identity_and_mob_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                result = store.observe_events([
                    {
                        "opcode": 0x0101,
                        "type": "account_login_request",
                        "data": {"fields": {"character_uid": 999, "name": "segredo"}},
                    },
                    {
                        "opcode": 0x010D,
                        "type": "ans_all_character_infos",
                        "data": {"fields": {"characters": [{
                            "character_uid": 123,
                            "name": "Carvalho",
                            "level": 68,
                            "guild_name": "Karvalho",
                        }]}},
                    },
                    {
                        "opcode": 0x0302,
                        "type": "appear_monster_list",
                        "data": {"units": [{
                            "uid": 77,
                            "npc_index": 305208,
                            "name": "Boss",
                            "level": 70,
                            "max_hp": 1_000_000,
                        }]},
                    },
                ], location="Android Junkyard")
                payload = store.pending_payload()
            finally:
                store.close()
            self.assertEqual(result, {"characters": 1, "mobs": 1})
            self.assertEqual(payload["characters"][0]["character_uid"], "123")
            self.assertTrue(payload["characters"][0]["guild_presence_known"])
            self.assertFalse(payload["characters"][0]["pvp_status_presence_known"])
            self.assertEqual(payload["mobs"][0]["location"], "Android Junkyard")
            self.assertNotIn("segredo", json.dumps(payload, ensure_ascii=False))

    def test_knowledge_store_serializes_unknown_mob_hp_as_null(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([{
                    "type": "appear_monster_list",
                    "data": {"units": [{"npc_index": 305208, "max_hp": 0}]},
                }])
                payload = store.pending_payload()
            finally:
                store.close()
        self.assertIsNone(payload["mobs"][0]["max_hp"])

    def test_pvp_quarantine_promotes_only_after_a_second_session(self):
        event = {
            "type": "appear_player_list",
            "data": {"units": [{"character_uid": 123, "name": "Neutro"}]},
        }
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([event], session_id="session-a")
                quarantined = store.characters(curation_state="quarantine")
                pending_before = store.pending_payload()["characters"]
                store.observe_events([event], session_id="session-b")
                final = store.characters(curation_state="final")
                pending_after = store.pending_payload()["characters"]
            finally:
                store.close()

        self.assertEqual(quarantined[0]["session_count"], 1)
        self.assertEqual(pending_before, [])
        self.assertEqual(final[0]["session_count"], 2)
        self.assertEqual(len(pending_after), 1)

    def test_pvp_bank_indexes_curation_and_status_queries(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                index = store.conn.execute(
                    """SELECT sql FROM sqlite_master
                       WHERE type='index'
                         AND name='idx_character_curation_status_name'"""
                ).fetchone()
            finally:
                store.close()

        self.assertIsNotNone(index)
        self.assertIn("curation_state", index[0])
        self.assertIn("pvp_status", index[0])

    def test_known_mob_is_not_requeued_until_confirmed_data_changes(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                monitor = {"nearby_monsters": [{
                    "npc_index": 305208,
                    "name": "Boss",
                    "level": 70,
                    "max_hp": 1_000_000,
                    "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                }]}
                first = store.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                payload = store.pending_payload()
                store.mark_uploaded(payload)
                repeated = store.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                unchanged = store.pending_payload()
                monitor["nearby_monsters"][0]["max_hp"] = 1_100_000
                divergent = store.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                after_divergence = store.pending_payload()
                candidates = store.mob_hp_candidates(305208)
            finally:
                store.close()
        self.assertEqual(first["mobs"], 1)
        self.assertEqual(repeated["mobs"], 0)
        self.assertEqual(unchanged["mobs"], [])
        self.assertEqual(divergent["mobs"], 0)
        self.assertEqual(after_divergence["mobs"], [])
        self.assertEqual(candidates[0]["max_hp"], 1_100_000)
        self.assertEqual(candidates[0]["review_state"], "pending")

    def test_mob_bank_keeps_multiple_confirmed_locations(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                base = {
                    "npc_index": 305208,
                    "name": "Boss",
                    "max_hp": 1_000_000,
                }
                for position in (
                    {"x": 10.0, "y": 20.0, "z": 30.0},
                    {"x": 40.0, "y": 50.0, "z": 60.0},
                    {"x": 10.4, "y": 20.4, "z": 30.4},
                ):
                    store.observe_combat(
                        [{"nearby_monsters": [{**base, "position": position}]}],
                        location={"map_index": 9, "map_name": "Abismo"},
                    )
                locations = store.mob_locations(305208)
            finally:
                store.close()
        self.assertEqual(len(locations), 2)
        self.assertEqual({row["map_index"] for row in locations}, {9})
        self.assertEqual(
            {(row["position_x"], row["position_y"], row["position_z"]) for row in locations},
            {(10.0, 20.0, 30.0), (40.0, 50.0, 60.0)},
        )

    def test_pve_delta_marks_only_explicit_ack_and_does_not_resend_known_mob(self):
        contract_item = {
            "kind": "mob", "npc_index": 305209,
            "protocol_version": "1.29.8", "name": "Boss", "level": 70,
            "max_hp": 1_000_000,
            "first_seen_at": "2026-08-11T10:00:00+00:00",
            "last_seen_at": "2026-08-11T10:01:00+00:00",
        }
        self.assertEqual(
            KnowledgeStore._pve_observation_id(contract_item),
            "6b062a3571aad565d6cc4a62ca1232d7805fc29ffaa6a25ef5c89608bd1bf788",
        )
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                monitor = {"nearby_monsters": [{
                    "npc_index": 305208,
                    "name": "Boss",
                    "level": 70,
                    "max_hp": 1_000_000,
                    "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                }]}
                location = {"map_index": 9, "map_name": "Abismo"}
                store.observe_combat([monitor], location=location)
                first = store.pending_pve_delta()
                self.assertEqual(
                    {item["kind"] for item in first["observations"]},
                    {"mob", "location"},
                )
                one = first["observations"][0]
                partial = store.mark_pve_ack(first, {
                    "schema": "rf-qol.pve-observations.ack",
                    "schema_version": 1,
                    "acks": [{
                        "observation_id": one["observation_id"],
                        "status": "accepted",
                    }],
                })
                self.assertEqual(partial, {
                    "acknowledged": 1, "conflicts": 0, "missing": 1,
                })
                remaining = store.pending_pve_delta()
                self.assertEqual(len(remaining["observations"]), 1)
                store.mark_pve_ack(remaining, {
                    "schema": "rf-qol.pve-observations.ack",
                    "schema_version": 1,
                    "acks": [{
                        "observation_id": remaining["observations"][0]["observation_id"],
                        "status": "known",
                    }],
                })
                store.observe_combat([monitor], location=location)
                self.assertEqual(store.pending_pve_delta()["observations"], [])

                monitor["nearby_monsters"][0]["max_hp"] = 1_100_000
                store.observe_combat([monitor], location=location)
                conflict = store.pending_pve_delta()
                self.assertEqual(
                    [item["kind"] for item in conflict["observations"]],
                    ["hp_candidate"],
                )
                result = store.mark_pve_ack(conflict, {
                    "schema": "rf-qol.pve-observations.ack",
                    "schema_version": 1,
                    "acks": [{
                        "observation_id": conflict["observations"][0]["observation_id"],
                        "status": "conflict",
                    }],
                })
            finally:
                store.close()
        self.assertEqual(result["conflicts"], 1)

    def test_pve_delivery_columns_migrate_additively(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "knowledge.sqlite3"
            connection = sqlite3.connect(path)
            connection.executescript("""
                CREATE TABLE mob_location_observations (
                    npc_index INTEGER NOT NULL, protocol_version TEXT NOT NULL,
                    location_key TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
                    map_index INTEGER, position_x REAL, position_y REAL,
                    position_z REAL, first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY(npc_index,protocol_version,location_key)
                );
                CREATE TABLE mob_hp_candidates (
                    npc_index INTEGER NOT NULL, protocol_version TEXT NOT NULL,
                    max_hp INTEGER NOT NULL, first_seen_at TEXT NOT NULL,
                    review_state TEXT NOT NULL DEFAULT 'pending',
                    PRIMARY KEY(npc_index,protocol_version,max_hp)
                );
            """)
            connection.close()
            store = KnowledgeStore(path)
            try:
                location_columns = {
                    row["name"] for row in store.conn.execute(
                        "PRAGMA table_info(mob_location_observations)"
                    )
                }
                candidate_columns = {
                    row["name"] for row in store.conn.execute(
                        "PRAGMA table_info(mob_hp_candidates)"
                    )
                }
            finally:
                store.close()
        self.assertIn("upload_state", location_columns)
        self.assertTrue({"last_seen_at", "upload_state"}.issubset(candidate_columns))

    def test_mob_bank_summary_counts_locations_and_pending_hp_reviews(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                monitor = {"nearby_monsters": [{
                    "npc_index": 305208,
                    "name": "Boss",
                    "level": 70,
                    "max_hp": 1_000_000,
                    "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                }]}
                store.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                monitor["nearby_monsters"][0].update({
                    "max_hp": 1_100_000,
                    "position": {"x": 40.0, "y": 50.0, "z": 60.0},
                })
                store.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                row = store.mobs()[0]
            finally:
                store.close()
        self.assertEqual(row["npc_index"], 305208)
        self.assertEqual(row["max_hp"], 1_000_000)
        self.assertEqual(row["location_count"], 2)
        self.assertEqual(row["hp_candidate_count"], 1)

    def test_knowledge_store_merges_newer_character_identity_from_site(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                merged = store.merge_remote_characters([{
                    "character_uid": "123",
                    "name": "Carvalho",
                    "level": 70,
                    "guild_id": "55",
                    "guild_name": "Karvalho",
                    "protocol_version": "1.28.5",
                    "first_seen_at": "2026-08-10T10:00:00+00:00",
                    "last_seen_at": "2026-08-11T10:00:00+00:00",
                }])
                monitors = [{"bosses": [{"top_damage_players": [{
                    "character_uid": "123", "name": "",
                    "damage": 900, "dps_hp": 90.0,
                }]}]}]
                enriched = store.enrich_combat_monitors(monitors)
                row = store.conn.execute(
                    "SELECT * FROM character_observations WHERE character_uid='123'"
                ).fetchone()
            finally:
                store.close()
            self.assertEqual(merged, 1)
            self.assertEqual(row["name"], "Carvalho")
            self.assertEqual(row["guild_name"], "Karvalho")
            self.assertEqual(row["upload_state"], "sent")
            self.assertEqual(enriched, 1)
            self.assertEqual(
                monitors[0]["bosses"][0]["top_damage_players"][0]["name"],
                "Carvalho",
            )
            self.assertEqual(
                monitors[0]["bosses"][0]["top_damage_guilds"],
                [{"name": "Karvalho", "damage": 900, "dps_hp": 90.0}],
            )

    def test_final_site_bank_replaces_pending_manual_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [{"character_uid": 123, "name": "Rival", "uid": 1}]},
                }])
                store.update_pvp_identity(123, guild_name="Proposta", status="enemy")
                payload = store.pending_payload()
                store.merge_remote_characters([{
                    "character_uid": "123",
                    "name": "Rival Final",
                    "biosuit_item_index": 2075041,
                    "rover_item_index": 4000000,
                    "guild_name": "Guilda Final",
                    "guild_source": "manual",
                    "guild_updated_at": "2026-08-12T12:00:00+00:00",
                    "pvp_status": "ally",
                    "pvp_status_updated_at": "2026-08-12T12:00:00+00:00",
                    "protocol_version": "1.29.8",
                    "first_seen_at": "2026-08-10T10:00:00+00:00",
                    "last_seen_at": "2026-08-12T12:00:00+00:00",
                }])
                final = store.characters()[0]
            finally:
                store.close()
            self.assertTrue(payload["characters"][0]["guild_presence_known"])
            self.assertTrue(payload["characters"][0]["pvp_status_presence_known"])
            self.assertEqual(
                (final["name"], final["guild_name"], final["pvp_status"]),
                ("Rival Final", "Guilda Final", "ally"),
            )
            self.assertEqual(final["biosuit_item_index"], 2075041)
            self.assertEqual(final["rover_item_index"], 4000000)

    def test_pvp_bank_persists_manual_status_and_allows_observed_guild_edit(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [
                        {"character_uid": 123, "name": "Sem Guilda", "uid": 1},
                        {
                            "character_uid": 456,
                            "name": "Com Guilda",
                            "guild_name": "Observada",
                            "uid": 2,
                        },
                    ]},
                }])
                manual = store.update_pvp_identity(
                    123, guild_name="Manual", status="enemy"
                )
                observed = store.update_pvp_identity(
                    456, guild_name="Substituída", status="ignored"
                )
                visible = store.characters()
                all_rows = store.characters(include_ignored=True)
                payload = store.pending_payload()
                monitors = [{
                    "pvp": {"character_uid": "123", "name": "Sem Guilda"},
                    "nearby_players": [
                        {"character_uid": "123", "name": "Sem Guilda"},
                        {"character_uid": "456", "name": "Com Guilda"},
                    ],
                    "bosses": [],
                }]
                store.enrich_combat_monitors(monitors)
            finally:
                store.close()
            self.assertEqual(
                (manual["guild_name"], manual["guild_source"], manual["pvp_status"]),
                ("Manual", "manual", "enemy"),
            )
            self.assertEqual(observed["guild_name"], "Substituída")
            self.assertEqual(observed["guild_source"], "manual")
            self.assertEqual(observed["pvp_status"], "ignored")
            self.assertEqual([row["character_uid"] for row in visible], ["123"])
            self.assertEqual(len(all_rows), 2)
            self.assertIn("456", [row["character_uid"] for row in payload["characters"]])
            self.assertEqual(payload["schema_version"], 2)
            self.assertEqual(monitors[0]["pvp"]["pvp_status"], "enemy")
            self.assertEqual(
                [item["pvp_status"] for item in monitors[0]["nearby_players"]],
                ["enemy", "ignored"],
            )

    def test_pvp_bank_rejects_invalid_manual_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                store.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [{
                        "character_uid": 123, "name": "Pessoa", "uid": 1,
                    }]},
                }])
                with self.assertRaisesRegex(ValueError, "status PvP"):
                    store.update_pvp_identity(123, guild_name="", status="qualquer")
            finally:
                store.close()

    def test_known_pvp_identity_is_not_requeued_without_material_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                event = {
                    "type": "appear_player_list",
                    "data": {"units": [{
                        "character_uid": 123,
                        "name": "Rival",
                        "level": 70,
                        "guild_name": "Guilda",
                    }]},
                }
                store.observe_events([event])
                store.mark_uploaded(store.pending_payload())
                store.observe_events([event])
                unchanged = store.pending_payload()
                event["data"]["units"][0]["level"] = 71
                store.observe_events([event])
                changed = store.pending_payload()
            finally:
                store.close()
        self.assertEqual(unchanged["characters"], [])
        self.assertEqual(changed["characters"][0]["level"], 71)

    def test_completed_market_signature_changes_only_on_completed_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")
            try:
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                       ts_ns,opcode,type,character_uid,data_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("s", "memory", "flow", 0, 0, 1, 0x1D02, "market", None,
                     json.dumps({"ret": 0, "is_end": False, "exchange_server_type": 0})),
                )
                self.assertEqual(store.completed_market_signature("s"), "")
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                       ts_ns,opcode,type,character_uid,data_json) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("s", "memory", "flow", 1, 0, 2, 0x1D02, "market", None,
                     json.dumps({"ret": 0, "is_end": True, "exchange_server_type": 2})),
                )
                signature = store.completed_market_signature("s")
                self.assertRegex(signature, r"^[a-f0-9]{64}$")
                self.assertEqual(store.completed_market_signature("s"), signature)
            finally:
                store.close()

    def test_live_decoder_reads_combat_event_without_creating_capture_file(self):
        payload = struct.pack("<IQQQIIIB", 77, 800, 1000, 0, 10, 20, 0, 0)
        frame = bytearray(6 + len(payload))
        frame[1:3] = len(frame).to_bytes(2, "little")
        frame[4:6] = (0x0311).to_bytes(2, "little")
        frame[6:] = payload
        tcp = struct.pack("!HHIIH", 12020, 50000, 100, 0, 0x5018) + b"\0" * 6 + frame
        ip = bytearray(20)
        ip[0] = 0x45
        ip[2:4] = (20 + len(tcp)).to_bytes(2, "big")
        ip[8] = 64
        ip[9] = 6
        ip[12:16] = bytes((10, 0, 0, 1))
        ip[16:20] = bytes((10, 0, 0, 2))
        packet = b"\0" * 12 + b"\x08\x00" + bytes(ip) + tcp

        events = LiveEventDecoder().feed(123_000_000_000, packet)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["source"], "memory://pktmon-live")
        self.assertEqual(events[0]["type"], "restore_hp_fp")
        self.assertEqual(events[0]["data"]["current_hp"], 800)
        self.assertEqual(events[0]["data"]["max_hp"], 1000)

    def test_live_decoder_applies_collection_catalog(self):
        payload = (
            struct.pack("<BBH", 1, 1, 1)
            + struct.pack("<IB10Q", 1015, 1, 1, 1, *([0] * 8))
        )
        frame = bytearray(6 + len(payload))
        frame[1:3] = len(frame).to_bytes(2, "little")
        frame[4:6] = (0x0419).to_bytes(2, "little")
        frame[6:] = payload
        tcp = (
            struct.pack("!HHIIH", 12020, 50000, 100, 0, 0x5018)
            + b"\0" * 6 + frame
        )
        ip = bytearray(20)
        ip[0] = 0x45
        ip[2:4] = (20 + len(tcp)).to_bytes(2, "big")
        ip[8] = 64
        ip[9] = 6
        ip[12:16] = bytes((10, 0, 0, 1))
        ip[16:20] = bytes((10, 0, 0, 2))
        packet = b"\0" * 12 + b"\x08\x00" + bytes(ip) + tcp

        events = LiveEventDecoder().feed(123_000_000_000, packet)

        self.assertEqual(len(events), 1)
        record = events[0]["data"]["records"][0]
        self.assertEqual(record["completed_slots"], [0])
        self.assertEqual(record["incomplete_slots"], [1])
        self.assertIs(record["collection_complete"], False)

    def test_live_decoder_correlates_equipment_only_within_same_logical_client(self):
        equipped_uid = bytes.fromhex("a0250838d001")
        player_name = "Carvalho"
        player_prefix = (
            struct.pack("<QH", 7, len(player_name))
            + player_name.encode("utf-16le")
            + struct.pack("<H", 66)
            + bytes(36)
            + struct.pack("<Q", 3753)
        )
        appearance_payload = bytearray(player_prefix[:26] + bytes(1042))
        struct.pack_into("<Q", appearance_payload, 26 + 38, 3753)
        refs_offset = len(appearance_payload) - 203
        struct.pack_into("<I", appearance_payload, refs_offset - 10, 2_075_041)
        struct.pack_into("<I", appearance_payload, refs_offset - 5, 4_400_008)
        struct.pack_into("<H", appearance_payload, refs_offset, 15)
        appearance_payload[refs_offset + 2:refs_offset + 8] = equipped_uid
        profile_item = (
            struct.pack("<H", 15)
            + equipped_uid
            + struct.pack("<IQBH", 1_002_279, 1, 1, 8)
            + struct.pack("<HIIH", 2, 161_049, 160_948, 0)
            + struct.pack("<BQ", 0, 0)
        )
        profile_payload = struct.pack("<BH", 1, 1) + profile_item

        def wire_frame(opcode: int, payload: bytes) -> bytes:
            value = bytearray(HEADER_SIZE + len(payload))
            value[1:3] = len(value).to_bytes(2, "little")
            value[4:6] = opcode.to_bytes(2, "little")
            value[6:] = payload
            return bytes(value)

        def packet(frame: bytes, sequence: int, client_port: int) -> bytes:
            tcp = (
                struct.pack(
                    "!HHIIH", 12020, client_port, sequence, 0, 0x5018
                )
                + b"\0" * 6
                + frame
            )
            ip = bytearray(20)
            ip[0] = 0x45
            ip[2:4] = (20 + len(tcp)).to_bytes(2, "big")
            ip[8] = 64
            ip[9] = 6
            ip[12:16] = bytes((10, 0, 0, 1))
            ip[16:20] = bytes((10, 0, 0, 2))
            return b"\0" * 12 + b"\x08\x00" + bytes(ip) + tcp

        appearance = wire_frame(0x0305, bytes(appearance_payload))
        profile = wire_frame(0x0403, profile_payload)
        live = LiveEventDecoder()
        live.set_connection_aliases({
            50000: "client-a", 50001: "client-b", 50002: "client-a",
        })
        appeared = live.feed(1, packet(appearance, 100, 50000))
        unrelated = live.feed(2, packet(profile, 100, 50001))
        correlated = live.feed(
            3, packet(profile, 100 + len(appearance), 50000)
        )
        correlated_other_route = live.feed(4, packet(profile, 100, 50002))

        self.assertEqual(appeared[0]["type"], "appear_player_prefix")
        self.assertNotIn(
            "active_equipment", unrelated[0]["data"]["fields"]
        )
        active = correlated[0]["data"]["fields"]["active_equipment"]
        self.assertEqual(active["character_uid"], 7)
        self.assertTrue(active["complete"])
        self.assertEqual(
            active["slots"][0]["item"]["item_index"], 1_002_279
        )
        self.assertEqual(
            correlated_other_route[0]["data"]["fields"]["active_equipment"]
            ["slots"][0]["item"]["item_index"],
            1_002_279,
        )

    def test_live_decoder_reads_exitlag_loopback_transport(self):
        payload = struct.pack("<IQQQIIIB", 77, 800, 1000, 0, 10, 20, 0, 0)
        frame = bytearray(6 + len(payload))
        frame[1:3] = len(frame).to_bytes(2, "little")
        frame[4:6] = (0x0311).to_bytes(2, "little")
        frame[6:] = payload
        tcp = struct.pack("!HHIIH", 50100, 30851, 100, 0, 0x5018) + b"\0" * 6 + frame
        ip = bytearray(20)
        ip[0] = 0x45
        ip[2:4] = (20 + len(tcp)).to_bytes(2, "big")
        ip[8] = 64
        ip[9] = 6
        ip[12:16] = bytes((127, 0, 0, 1))
        ip[16:20] = bytes((127, 0, 0, 1))
        packet = b"\0" * 12 + b"\x08\x00" + bytes(ip) + tcp

        events = LiveEventDecoder(transport_ports=(50100,)).feed(
            123_000_000_000, packet
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["type"], "restore_hp_fp")

    def test_combat_monitor_separates_pve_and_confirmed_pvp(self):
        events = [
            {
                "ts_ns": 10_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 111, "uid": 10, "name": "Local", "max_hp": 1000, "current_hp": 1000},
                    {"character_uid": 222, "uid": 20, "name": "Rival", "max_hp": 1000, "current_hp": 1000},
                ]},
            },
            {
                "ts_ns": 10_000_000_000,
                "type": "appear_monster_list",
                "data": {"units": [
                    {"uid": 30, "npc_index": 305208, "max_hp": 2000, "current_hp": 2000},
                ]},
            },
            {
                "ts_ns": 16_000_000_000,
                "type": "use_normal_skill_result",
                "data": {"caster_uid": 10, "caster_final_hp": 1000, "effect_results": [
                    {"uid": 30, "hp_damage": 500, "shield_damage": 0, "final_hp": 1500},
                ]},
            },
            {
                "ts_ns": 18_000_000_000,
                "type": "use_skill_result",
                "data": {"ret": 0, "caster_uid": 10, "caster_final_hp": 1000, "effect_results": [
                    {"uid": 20, "hp_damage": 200, "shield_damage": 50, "final_hp": 800},
                ]},
            },
            {
                "ts_ns": 19_000_000_000,
                "type": "use_skill_result",
                "data": {"ret": 1, "caster_uid": 10, "caster_final_hp": 1000, "effect_results": [
                    {"uid": 20, "hp_damage": 900, "shield_damage": 0, "final_hp": 1},
                ]},
            },
        ]
        result = summarize_combat(
            events, "111", {305208: "Guardião"}, now_ns=20_000_000_000
        )
        self.assertEqual(result["local_combat_uid"], 10)
        self.assertEqual(result["pve"]["name"], "Guardião")
        self.assertEqual(result["pve"]["current_hp"], 1500)
        self.assertEqual(result["pvp"]["name"], "Rival")
        self.assertEqual(result["pvp"]["hp_percent"], 80.0)
        self.assertEqual(result["pvp"]["dps_hp"], 20.0)
        self.assertEqual(result["pvp_activity"]["direction"], "saída")

    def test_combat_activity_requires_exp_gain_and_actual_pvp_damage(self):
        second = 1_000_000_000
        base = [{
            "ts_ns": second,
            "type": "appear_player_list",
            "data": {"units": [
                {"character_uid": 111, "uid": 10, "name": "Local"},
                {"character_uid": 222, "uid": 20, "name": "Rival"},
            ]},
        }, {
            "ts_ns": 2 * second,
            "type": "select_target_request",
            "data": {"target_uid": 20},
        }, {
            "ts_ns": 3 * second,
            "type": "update_exp",
            "data": {"fields": {"gain_exp": 250}},
        }]

        selected = summarize_combat(base, "111", now_ns=4 * second)
        self.assertIsNone(selected["pvp_activity"])
        self.assertEqual(selected["exp_gain"]["amount"], 250)
        rewarded = summarize_combat(base[:2] + [{
            "ts_ns": 3 * second,
            "type": "drop_item_field",
            "data": {"results": [{"item_index": 900, "count": 75}]},
        }], "111", now_ns=4 * second)
        self.assertEqual(rewarded["exp_gain"]["amount"], 75)
        damaged = summarize_combat(base + [{
            "ts_ns": 4 * second,
            "type": "use_skill_result",
            "data": {
                "ret": 0,
                "caster_uid": 20,
                "effect_results": [{"uid": 10, "hp_damage": 30, "final_hp": 970}],
            },
        }], "111", now_ns=5 * second)
        self.assertEqual(damaged["pvp_activity"]["direction"], "entrada")

    def test_pve_activity_requires_local_damage_or_confirmed_kill(self):
        second = 1_000_000_000
        base = [{
            "ts_ns": second,
            "type": "appear_player_list",
            "data": {"units": [{"character_uid": 111, "uid": 10, "name": "Local"}]},
        }, {
            "ts_ns": 2 * second,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 100, "max_hp": 1000, "current_hp": 1000,
            }]},
        }]

        rewarded = summarize_combat(base + [{
            "ts_ns": 3 * second,
            "type": "update_exp",
            "data": {"fields": {"gain_exp": 250}},
        }], "111", {100: "Mob"}, now_ns=4 * second)
        self.assertIsNone(rewarded["pve_activity"])

        damaged = summarize_combat(base + [{
            "ts_ns": 3 * second,
            "type": "use_skill_result",
            "data": {
                "ret": 0,
                "caster_uid": 10,
                "effect_results": [{"uid": 30, "hp_damage": 100, "final_hp": 900}],
            },
        }], "111", {100: "Mob"}, now_ns=4 * second)
        self.assertEqual(damaged["pve_activity"]["kind"], "damage")
        self.assertEqual(damaged["pve_activity"]["target_uid"], 30)

        killed = summarize_combat(base + [{
            "ts_ns": 3 * second,
            "type": "dying_unit",
            "data": {"uid": 30, "killer_uid": 10},
        }], "111", {100: "Mob"}, now_ns=4 * second)
        self.assertEqual(killed["pve_activity"]["kind"], "kill")

    def test_combat_monitor_uses_confirmed_main_target_and_named_npcs_only(self):
        events = [
            {
                "ts_ns": 1_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 111, "uid": 10, "name": "Local"},
                ]},
            },
            {
                "ts_ns": 1_000_000_000,
                "type": "appear_monster_list",
                "data": {"units": [
                    {"uid": 30, "npc_index": 100, "max_hp": 1000, "current_hp": 1000},
                    {"uid": 31, "npc_index": 999, "max_hp": 1000, "current_hp": 1000},
                ]},
            },
            {
                "ts_ns": 2_000_000_000,
                "type": "use_skill_result",
                "data": {
                    "ret": 0,
                    "caster_uid": 10,
                    "main_target_uid": 30,
                    "effect_results": [
                        {"uid": 30, "hp_damage": 100, "final_hp": 900},
                        {"uid": 31, "hp_damage": 200, "final_hp": 800},
                    ],
                },
            },
        ]

        result = summarize_combat(
            events, "111", {100: "Alvo definido"}, now_ns=3_000_000_000
        )

        self.assertEqual(result["pve"]["uid"], 30)
        self.assertEqual(result["pve"]["name"], "Alvo definido")
        self.assertEqual(
            [(item["npc_index"], item["name"]) for item in result["nearby_monsters"]],
            [(100, "Alvo definido")],
        )

    def test_target_request_drives_monitor_without_local_appearance(self):
        events = [
            {
                "ts_ns": 1_000_000_000,
                "type": "appear_monster_list",
                "data": {"units": [
                    {"uid": 30, "npc_index": 100, "max_hp": 1000, "current_hp": 900},
                ]},
            },
            {
                "ts_ns": 2_000_000_000,
                "type": "select_target_request",
                "data": {"target_uid": 30},
            },
        ]

        result = summarize_combat(
            events, "111", {100: "Alvo selecionado"}, now_ns=3_000_000_000
        )

        self.assertIsNone(result["local_combat_uid"])
        self.assertEqual(result["pve"]["uid"], 30)
        self.assertEqual(result["pve"]["name"], "Alvo selecionado")

    def test_observation_decoder_reads_outgoing_target_requests(self):
        target_frame = bytearray(10)
        target_frame[4:6] = (0x0609).to_bytes(2, "little")
        target_frame[6:] = struct.pack("<I", 0x34031FBA)
        target = parse_observation_payload(bytes(target_frame))
        self.assertEqual(target["type"], "select_target_request")
        self.assertEqual(target["target_uid"], 0x34031FBA)

        skill_frame = bytearray(18)
        skill_frame[4:6] = (0x0601).to_bytes(2, "little")
        skill_frame[6:] = struct.pack("<III", 1_080_024, 629, 0x34031FBA)
        skill = parse_observation_payload(bytes(skill_frame))
        self.assertEqual(skill["type"], "use_skill_request")
        self.assertEqual(skill["target_uid"], 0x34031FBA)

    def test_combat_monitor_reclassifies_reused_combat_uid(self):
        events = [
            {"ts_ns": 1, "type": "appear_player_list", "data": {"units": [
                {"character_uid": 111, "uid": 10, "name": "Local", "max_hp": 100, "current_hp": 100},
            ]}},
            {"ts_ns": 2, "type": "appear_monster_list", "data": {"units": [
                {"uid": 30, "npc_index": 5, "max_hp": 100, "current_hp": 100},
            ]}},
            {"ts_ns": 3, "type": "dying_unit", "data": {"uid": 30, "killer_uid": 10}},
            {"ts_ns": 4, "type": "appear_player_list", "data": {"units": [
                {"character_uid": 222, "uid": 30, "name": "Rival", "max_hp": 200, "current_hp": 200},
            ]}},
            {"ts_ns": 5, "type": "use_normal_skill_result", "data": {
                "ret": 0, "caster_uid": 10, "caster_final_hp": 100,
                "effect_results": [{"uid": 30, "hp_damage": 20, "final_hp": 180}],
            }},
        ]
        result = summarize_combat(events, "111", now_ns=5)
        self.assertIsNone(result["pve"])
        self.assertEqual(result["pvp"]["name"], "Rival")

    def test_pvp_nearby_requires_confirmed_identity_and_deduplicates_character(self):
        events = [
            {
                "ts_ns": 1_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 111, "uid": 10, "name": "Local"},
                    {"character_uid": 222, "uid": 20, "name": "Rival antigo"},
                    {"uid": 30, "name": "Registro incompleto"},
                ]},
            },
            {
                "ts_ns": 2_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 222, "uid": 21, "name": "Rival atual"},
                    {"character_uid": 333, "uid": 31, "name": "Vizinho"},
                ]},
            },
        ]

        result = summarize_combat(events, "111", now_ns=3_000_000_000)

        self.assertEqual(
            [(item["character_uid"], item["name"]) for item in result["nearby_players"]],
            [(222, "Rival atual"), (333, "Vizinho")],
        )
        expired = summarize_combat(events, "111", now_ns=18_000_000_000)
        self.assertEqual(expired["nearby_players"], [])

    def test_pvp_nearby_presence_is_not_refreshed_by_reused_combat_uid(self):
        second = 1_000_000_000
        events = [
            {
                "ts_ns": second,
                "type": "appear_player_list",
                "data": {"units": [
                    {"character_uid": 111, "uid": 10, "name": "Local"},
                    {"character_uid": 222, "uid": 20, "name": "Mapa anterior"},
                ]},
            },
            {
                "ts_ns": 61 * second,
                "type": "restore_hp_fp",
                "data": {"uid": 20, "current_hp": 100, "max_hp": 100},
            },
        ]

        result = summarize_combat(events, "111", now_ns=62 * second)

        self.assertEqual(result["nearby_players"], [])

    def test_combat_monitor_lists_only_catalogued_live_bosses(self):
        events = [
            {"ts_ns": 1_000_000_000, "type": "appear_monster_list", "data": {"units": [
                {"uid": 30, "npc_index": 375100, "max_hp": 500_000_000, "current_hp": 500_000_000},
                {"uid": 31, "npc_index": 999, "max_hp": 900_000_000, "current_hp": 900_000_000},
            ]}},
            {"ts_ns": 2_000_000_000, "type": "use_skill_result", "data": {
                "ret": 0, "caster_uid": 77,
                "effect_results": [{"uid": 30, "hp_damage": 1_000, "final_hp": 499_999_000}],
            }},
        ]
        events.insert(0, {
            "ts_ns": 500_000_000,
            "type": "appear_player_list",
            "data": {"units": [{
                "character_uid": 222,
                "uid": 77,
                "name": "Aliado",
                "guild_id": 55,
                "guild_name": "Karvalho",
                "group_id": 9,
                "max_hp": 100,
                "current_hp": 100,
            }]},
        })
        catalog = {375100: {"name": "Xenogeyser", "level": 70, "npc_subtype": 106}}
        result = summarize_combat(events, "111", boss_catalog=catalog, now_ns=3_000_000_000)
        self.assertEqual(len(result["bosses"]), 1)
        self.assertEqual(result["bosses"][0]["name"], "Xenogeyser")
        self.assertEqual(result["bosses"][0]["current_hp"], 499_999_000)
        self.assertEqual(result["bosses"][0]["level"], 70)
        self.assertEqual(result["bosses"][0]["dps_hp"], 1000.0)
        self.assertEqual(result["bosses"][0]["eta_seconds"], 499999.0)
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["damage"], 1000
        )
        self.assertEqual(result["bosses"][0]["total_damage"], 1000)
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["dps_hp"], 1000.0
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["calculation"],
            "encounter_total",
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["guild_name"],
            "Karvalho",
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["character_uid"],
            222,
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_players"][0]["guild_id"],
            55,
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_guilds"],
            [{
                "name": "Karvalho", "guild_id": "55",
                "damage": 1000, "dps_hp": 1000.0,
                "elapsed_seconds": 1.0,
                "calculation": "encounter_total",
            }],
        )
        self.assertEqual(
            result["bosses"][0]["top_damage_groups"],
            [{
                "name": "9", "damage": 1000, "dps_hp": 1000.0,
                "elapsed_seconds": 1.0,
                "calculation": "encounter_total",
            }],
        )

        events.append({"ts_ns": 4_000_000_000, "type": "dying_unit", "data": {"uid": 30}})
        self.assertEqual(
            summarize_combat(events, "111", boss_catalog=catalog, now_ns=4_000_000_000)["bosses"],
            [],
        )
        self.assertEqual(
            summarize_combat(
                events[:-1], "111", boss_catalog=catalog, now_ns=20_000_000_000
            )["bosses"],
            [],
        )

    def test_farm_activity_infers_local_caster_when_response_number_is_not_request_sequence(self):
        events = [{
            "ts_ns": 500_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 5, "max_hp": 1000, "current_hp": 1000,
            }]},
        }, {
            "ts_ns": 1_000_000_000,
            "type": "use_skill_request",
            "data": {
                "skill_index": 9, "request_sequence_raw": 77, "target_uid": 30,
            },
        }, {
            "ts_ns": 1_100_000_000,
            "type": "use_skill_result",
            "data": {
                "ret": 0, "response_number": 0, "caster_uid": 10,
                "skill_index": 9, "main_target_uid": 30,
                "effect_results": [{
                    "uid": 30, "hp_damage": 250, "final_hp": 750,
                }],
            },
        }]

        result = summarize_combat(
            events, "111", {5: "Mob"}, now_ns=2_000_000_000
        )

        self.assertEqual(result["local_combat_uid"], 10)
        self.assertEqual(result["pve_activity"]["kind"], "damage")
        self.assertEqual(result["pve_activity"]["target_uid"], 30)

    def test_live_boss_disappears_from_proximity_but_total_survives_reappearance(self):
        stream = LiveEventStream(
            boss_indexes={375100}, max_boss_events=2,
            boss_event_seconds=3600,
        )
        flow = "10.0.0.1:12010 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow, "ts_ns": 100_000_000,
            "type": "appear_player_list",
            "data": {"units": [{
                "uid": 77, "character_uid": 222, "name": "Aliado",
                "guild_id": 55, "guild_name": "Karvalho",
            }]},
        }, {
            "flow": flow, "ts_ns": 200_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 375100,
                "max_hp": 10_000, "current_hp": 10_000,
            }]},
        }])
        for second, damage in enumerate((100, 200, 300), 1):
            stream._remember([{
                "flow": flow, "ts_ns": second * 1_000_000_000,
                "type": "use_skill_result",
                "data": {
                    "ret": 0, "caster_uid": 77,
                    "effect_results": [{
                        "uid": 30, "hp_damage": damage,
                        "final_hp": 10_000 - sum((100, 200, 300)[:second]),
                    }],
                },
            }])
        stream._remember([{
            "flow": flow, "ts_ns": 3_100_000_000,
            "type": "disappear_unit_list",
            "data": {"fields": {"entity_uids": [30]}},
        }])

        snapshot = stream.snapshot()
        totals = [item for item in snapshot if item.get("type") == "boss_damage_total"]
        self.assertEqual(totals[0]["data"]["damage"], 600)
        self.assertEqual(stream.metrics()["boss_events"], 2)
        self.assertEqual(stream.metrics()["boss_anchors"], 0)
        monitor = summarize_combat(
            snapshot, "111",
            boss_catalog={375100: {"name": "Boss"}},
            now_ns=4_000_000_000,
        )
        self.assertEqual(monitor["bosses"], [])

        stream._remember([{
            "flow": flow, "ts_ns": 4_100_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 375100,
                "max_hp": 10_000, "current_hp": 9_400,
            }]},
        }])
        monitor = summarize_combat(
            stream.snapshot(), "111",
            boss_catalog={375100: {"name": "Boss"}},
            now_ns=4_200_000_000,
        )
        self.assertEqual(
            monitor["bosses"][0]["top_damage_players"][0]["damage"], 600
        )
        self.assertEqual(
            monitor["bosses"][0]["top_damage_guilds"][0]["name"], "Karvalho"
        )

    def test_boss_death_after_disappearance_releases_retained_encounter(self):
        stream = LiveEventStream(boss_indexes={375100})
        flow = "10.0.0.1:12010 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow, "ts_ns": 1_000_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 375100,
                "max_hp": 10_000, "current_hp": 10_000,
            }]},
        }, {
            "flow": flow, "ts_ns": 2_000_000_000,
            "type": "use_skill_result",
            "data": {
                "ret": 0, "caster_uid": 77,
                "effect_results": [{
                    "uid": 30, "hp_damage": 100, "final_hp": 9_900,
                }],
            },
        }, {
            "flow": flow, "ts_ns": 3_000_000_000,
            "type": "disappear_unit_list",
            "data": {"fields": {"entity_uids": [30]}},
        }])
        self.assertEqual(stream.metrics()["boss_anchors"], 0)
        self.assertEqual(stream.metrics()["boss_damage_buckets"], 1)

        stream._remember([{
            "flow": flow, "ts_ns": 4_000_000_000,
            "type": "dying_unit",
            "data": {"uid": 30, "killer_uid": 99},
        }])

        self.assertEqual(stream.metrics()["boss_anchors"], 0)
        self.assertEqual(stream.metrics()["boss_damage_buckets"], 0)

    def test_guild_dps_survives_knowledge_enrichment_without_summing_player_rates(self):
        now_ns = 10_000_000_000
        units = [{"uid": 10, "character_uid": 111, "name": "Local"}]
        events = [{
            "ts_ns": 100_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{
                "uid": 30, "npc_index": 375100,
                "max_hp": 10_000, "current_hp": 10_000,
            }]},
        }]
        for index, seconds_ago in enumerate((9, 8, 7, 6, 5, 2), 1):
            units.append({
                "uid": 100 + index,
                "character_uid": 1_000 + index,
                "name": f"A{index}",
                "guild_id": 1,
                "guild_name": "Guild A",
            })
            events.append({
                "ts_ns": now_ns - seconds_ago * 1_000_000_000,
                "type": "use_skill_result",
                "data": {
                    "ret": 0,
                    "caster_uid": 100 + index,
                    "effect_results": [{
                        "uid": 30, "hp_damage": 300,
                        "final_hp": 10_000 - index * 300,
                    }],
                },
            })
        units.append({
            "uid": 200, "character_uid": 2_000, "name": "B1",
            "guild_id": 2, "guild_name": "Guild B",
        })
        events.insert(0, {
            "ts_ns": 50_000_000,
            "type": "appear_player_list",
            "data": {"units": units},
        })
        events.append({
            "ts_ns": now_ns - 1_000_000_000,
            "type": "use_skill_result",
            "data": {
                "ret": 0,
                "caster_uid": 200,
                "effect_results": [{
                    "uid": 30, "hp_damage": 300, "final_hp": 7_900,
                }],
            },
        })
        monitor = summarize_combat(
            events,
            "111",
            boss_catalog={375100: {"name": "Boss"}},
            now_ns=now_ns,
        )
        with tempfile.TemporaryDirectory() as directory:
            store = KnowledgeStore(Path(directory) / "knowledge.sqlite3")
            try:
                store.enrich_combat_monitors([monitor])
            finally:
                store.close()

        guilds = monitor["bosses"][0]["top_damage_guilds"]
        self.assertEqual(
            [(row["name"], row["damage"], row["dps_hp"]) for row in guilds],
            [("Guild A", 1800, 200.0), ("Guild B", 300, 300.0)],
        )

    def test_auction_sales_projection_is_sanitized_and_tracks_lifecycle(self):
        item = {
            "id": 987654321,
            "index": 270062,
            "count": 3,
            "enchant_level": 7,
            "talic_indices": [1, 2],
            "item_options": [{"option_index": 9, "value": 10}],
        }
        sale = {
            "exchange_index": 444,
            "account_id": 111,
            "pc_id": 222,
            "item_info": item,
            "registed_time": 10,
            "expired_time": 20,
            "selling_time": 0,
            "selling_price": 1500,
            "settlement_price": 0,
        }
        events = [
            {"ts_ns": 1, "data": {
                "message": "FL2C_ans_exchange_for_my_sales_list_Message",
                "ret": 0,
                "exchange_server_type": 2,
                "my_sales_list": [sale],
            }},
            {"ts_ns": 2, "data": {
                "message": "FL2C_notify_exchange_item_sell_Message",
                "exchange_server_type": 2,
                "exchange_indices": [444],
            }},
            {"ts_ns": 3, "data": {
                "message": "FL2C_respond_settlement_of_exchange_Message",
                "ret": 0,
                "exchange_server_type": 2,
                "exchange_index_list": [444],
                "respond_settlement_infos": [{"exchange_index": 444, "selling_price": 4500}],
            }},
        ]

        rows = auction_sales_snapshot(
            events, secret=b"0123456789abcdef", item_names={270062: "Arma"}
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "settled")
        self.assertEqual(rows[0]["price_per_unit"], 1500)
        self.assertEqual(rows[0]["quantity"], 3)
        self.assertEqual(rows[0]["item_name"], "Arma")
        serialized = json.dumps(rows[0])
        for forbidden in ("444", "987654321", "account_id", "pc_id", "talic"):
            self.assertNotIn(forbidden, serialized)

    def test_auction_projection_ignores_errors_and_warns_without_blocking(self):
        failed = {"data": {
            "message": "FL2C_respond_to_registration_of_sale_item_on_exchange_Message",
            "ret": 9,
            "exchange_server_type": 1,
            "exchange_item_info": {
                "exchange_index": 5,
                "item_info": {"index": 10, "count": 1, "enchant_level": 0},
                "selling_price": 90,
            },
        }}
        self.assertEqual(
            auction_sales_snapshot([failed], secret=b"0123456789abcdef"), []
        )
        active = [
            {"status": "active", "server_type": 1, "item_index": 10,
             "enchant_level": 4, "price_per_unit": 100},
            {"status": "sold", "server_type": 1, "item_index": 10,
             "enchant_level": 4, "price_per_unit": 80},
        ]
        warning = undercut_warning(
            {"server_type": 1, "item_index": 10, "enchant_level": 4,
             "price_per_unit": 90},
            active,
        )
        self.assertEqual(warning, {
            "warning": True,
            "lowest_active_price": 100,
            "difference": 10,
        })

    def test_auction_history_separates_confirmed_purchase_from_unknown_type(self):
        entry = {
            "exchange_index": 123,
            "item_info": {"index": 77, "count": 2, "enchant_level": 4},
            "selling_price": 900,
        }
        rows = auction_transaction_history(
            [
                {"ts_ns": 1, "data": {
                    "message": "FL2C_respond_to_purchase_item_on_exchange_Message",
                    "ret": 0,
                    "exchange_server_type": 2,
                    "purchase_results": [{"ret": 0, "exchange_info": entry}],
                }},
                {"ts_ns": 2, "data": {
                    "message": "FL2C_ans_exchange_for_my_transaction_history_Message",
                    "ret": 0,
                    "exchange_server_type": 2,
                    "my_transaction_history": [{
                        "exchange_type": 3,
                        "exchange_item_info": {**entry, "exchange_index": 124},
                    }],
                }},
            ],
            secret=b"0123456789abcdef",
        )

        self.assertEqual(
            {row["transaction_type"] for row in rows},
            {"bought", "unclassified"},
        )
        unknown = next(
            row for row in rows if row["transaction_type"] == "unclassified"
        )
        self.assertEqual(unknown["exchange_type_raw"], 3)
        serialized = json.dumps(rows)
        self.assertNotIn('"exchange_index"', serialized)

    def test_store_reads_auction_events_only_for_selected_character(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")
            try:
                message = "FL2C_ans_exchange_for_my_sales_list_Message"
                for offset, character_uid in enumerate(("one", "two")):
                    store.conn.execute(
                        """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                           ts_ns,opcode,type,character_uid,data_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("s", "memory", "flow", offset, 0, offset + 1, 0x1D07,
                         message, character_uid, json.dumps({"message": message})),
                    )
                selected = store.auction_sale_events("s", "one")
            finally:
                store.close()
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["ts_ns"], 1)

    def test_exp_rank_snapshot_merges_pages_and_excludes_profile_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")
            try:
                for offset, uid, rank in ((1, 101, 1), (2, 202, 2)):
                    store.conn.execute(
                        """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                           ts_ns,opcode,type,character_uid,data_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "s", "memory", "flow", offset, 0, offset * 100,
                            0x1A02, "exp_rank_list", None,
                            json.dumps({
                                "field_decode": "captura-layout-exato",
                                "records": [{
                                    "character_uid": uid,
                                    "character_uid_repeat": uid,
                                    "character_name": f"Jogador {uid}",
                                    "guild_name": "Guilda",
                                    "guild_mark_hex": "84000457",
                                    "profile_uid_raw": 999,
                                    "profile_value_raw": 123,
                                    "total_exp": 1000 - rank,
                                    "rank": rank,
                                    "previous_rank": rank + 1,
                                    "scope_id_raw": 1,
                                    "ranking_cycle_raw": 44,
                                }],
                            }),
                        ),
                    )
                snapshot = store.exp_rank_snapshot("s")
                self.assertEqual([item["rank"] for item in snapshot["records"]], [1, 2])
                self.assertEqual(snapshot["snapshot_key"], "1:44")
                self.assertEqual(snapshot["completeness"], "partial")
                self.assertEqual(snapshot["record_count"], 2)
                self.assertEqual(snapshot["observed_positions"], [1, 2])
                self.assertEqual(snapshot["missing_positions"][:2], [3, 4])
                self.assertEqual(snapshot["conflict_count"], 0)
                self.assertRegex(snapshot["signature"], r"^[a-f0-9]{64}$")
                self.assertNotIn("profile_uid_raw", snapshot["records"][0])
                first_signature = snapshot["signature"]
                store.conn.execute("UPDATE events SET ts_ns=999")
                self.assertEqual(
                    store.exp_rank_snapshot("s")["signature"], first_signature
                )
            finally:
                store.close()

    def test_exp_rank_level_and_percent_are_derived_from_total_exp_curve(self):
        self.assertEqual(exp_rank_level_progress(0), (1, 0.0))
        self.assertEqual(exp_rank_level_progress(19), (1, 95.0))
        self.assertEqual(exp_rank_level_progress(20), (2, 0.0))
        self.assertEqual(exp_rank_level_progress(35), (2, 50.0))
        self.assertEqual(exp_rank_level_progress(-1), (None, None))

    def test_exp_rank_history_calculates_gain_between_captures(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")

            def insert(offset: int, ts_ns: int, total_exp: int) -> None:
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,
                       bundle_seq,ts_ns,opcode,type,character_uid,data_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "s", "memory", "flow", offset, 0, ts_ns, 0x1A02,
                        "exp_rank_list", None,
                        json.dumps({
                            "field_decode": "captura-layout-exato",
                            "records": [{
                                "character_uid": 101,
                                "character_uid_repeat": 101,
                                "character_name": "Jogador",
                                "guild_name": "Guilda",
                                "guild_mark_hex": "84000457",
                                "total_exp": total_exp,
                                "rank": 1,
                                "previous_rank": 1,
                                "scope_id_raw": 1,
                                "ranking_cycle_raw": 44,
                            }],
                        }),
                    ),
                )
                store._remember_exp_rank_capture("s")

            try:
                insert(1, 1_000_000_000, 1000)
                insert(2, 3_601_000_000_000, 1200)
                history = store.exp_rank_history("s")
            finally:
                store.close()

        self.assertEqual(len(history), 2)
        latest = history[0]["records"][0]
        self.assertEqual(latest["gained_exp"], 200)
        self.assertEqual(latest["exp_per_hour"], 200.0)
        previous_level, previous_percent = exp_rank_level_progress(1000)
        current_level, current_percent = exp_rank_level_progress(1200)
        expected_percent = round(
            (current_level - previous_level) * 100
            + current_percent - previous_percent,
            6,
        )
        self.assertEqual(latest["gained_percent"], expected_percent)
        self.assertEqual(latest["exp_percent_per_hour"], expected_percent)

    def test_exp_rank_history_ignores_identical_checks_inside_one_hour(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")

            def remember(offset: int, captured_at_ns: int) -> None:
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,
                       bundle_seq,ts_ns,opcode,type,character_uid,data_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "s", "memory", "flow", offset, 0, captured_at_ns,
                        0x1A02, "exp_rank_list", None,
                        json.dumps({
                            "field_decode": "captura-layout-exato",
                            "records": [{
                                "character_uid": 101,
                                "character_uid_repeat": 101,
                                "character_name": "Jogador",
                                "guild_name": "Guilda",
                                "guild_mark_hex": "84000457",
                                "total_exp": 1000,
                                "rank": 1,
                                "previous_rank": 1,
                                "scope_id_raw": 1,
                                "ranking_cycle_raw": 44,
                            }],
                        }),
                    ),
                )
                store._remember_exp_rank_capture("s")

            try:
                remember(1, 1_000_000_000)
                remember(2, 30 * 60 * 1_000_000_000)
                self.assertEqual(
                    store.conn.execute(
                        "SELECT COUNT(*) FROM exp_rank_captures"
                    ).fetchone()[0],
                    1,
                )
                remember(3, 61 * 60 * 1_000_000_000)
                history = store.exp_rank_history("s")
            finally:
                store.close()

        self.assertEqual(len(history), 2)
        self.assertEqual(
            [capture["captured_at_ns"] for capture in history],
            [61 * 60 * 1_000_000_000, 1_000_000_000],
        )

    def test_exp_rank_snapshot_is_complete_only_for_unique_top_100(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")
            records = [{
                "character_uid": 10_000 + rank,
                "character_uid_repeat": 10_000 + rank,
                "character_name": f"Jogador {rank}",
                "guild_name": f"Guilda {rank % 4}",
                "guild_mark_hex": "84000457",
                "total_exp": 1_000_000 - rank,
                "rank": rank,
                "previous_rank": rank,
                "scope_id_raw": 7,
                "ranking_cycle_raw": 55,
            } for rank in range(1, 101)]
            try:
                for offset, ts_ns in ((1, 1_000), (2, 2_000)):
                    store.conn.execute(
                        """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                           ts_ns,opcode,type,character_uid,data_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "s", "memory", f"flow-{offset}", offset, 0, ts_ns,
                            0x1A02, "exp_rank_list", None,
                            json.dumps({
                                "field_decode": "captura-layout-exato",
                                "records": records,
                            }),
                        ),
                    )
                    snapshot = store.exp_rank_snapshot("s")
                    if offset == 1:
                        first_signature = snapshot["signature"]

                self.assertEqual(snapshot["completeness"], "complete")
                self.assertEqual(snapshot["record_count"], 100)
                self.assertEqual(snapshot["missing_positions"], [])
                self.assertEqual(snapshot["conflict_count"], 0)
                self.assertEqual(snapshot["source_pages"], 2)
                self.assertEqual(snapshot["signature"], first_signature)
            finally:
                store.close()

    def test_exp_rank_snapshot_does_not_mix_old_or_conflicting_positions(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")

            def insert(offset, ts_ns, records):
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                       ts_ns,opcode,type,character_uid,data_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "s", "memory", "flow", offset, 0, ts_ns,
                        0x1A02, "exp_rank_list", None,
                        json.dumps({
                            "field_decode": "captura-layout-exato",
                            "records": records,
                        }),
                    ),
                )

            def record(uid, rank, scope=1, cycle=44):
                return {
                    "character_uid": uid,
                    "character_uid_repeat": uid,
                    "character_name": f"Jogador {uid}",
                    "guild_name": "Guilda",
                    "guild_mark_hex": "84000457",
                    "total_exp": 1_000 - rank,
                    "rank": rank,
                    "previous_rank": rank,
                    "scope_id_raw": scope,
                    "ranking_cycle_raw": cycle,
                }

            try:
                insert(1, 1, [record(100 + rank, rank) for rank in range(1, 101)])
                insert(2, 2, [record(999, 1, scope=2)])
                insert(
                    3,
                    15 * 60 * 1_000_000_000 + 2,
                    [record(501, 1), record(501, 2)],
                )

                snapshot = store.exp_rank_snapshot("s")

                self.assertEqual(snapshot["scope_id"], 1)
                self.assertEqual(snapshot["observed_positions"], [1, 2])
                self.assertEqual(snapshot["record_count"], 2)
                self.assertEqual(snapshot["completeness"], "partial")
                self.assertEqual(snapshot["conflict_count"], 1)
            finally:
                store.close()

    def test_pvp_target_is_cleared_after_three_seconds_without_confirmation(self):
        events = [
            {
                "ts_ns": 500_000_000,
                "type": "appear_player_list",
                "data": {"units": [
                    {"uid": 10, "character_uid": 111, "name": "Local"},
                    {"uid": 20, "character_uid": 222, "name": "Rival"},
                ]},
            },
            {
                "ts_ns": 1_000_000_000,
                "type": "use_skill_result",
                "data": {
                    "ret": 0,
                    "caster_uid": 10,
                    "main_target_uid": 20,
                    "effect_results": [
                        {"uid": 20, "hp_damage": 10, "final_hp": 90}
                    ],
                },
            },
        ]
        recent = summarize_combat(events, "111", now_ns=3_900_000_000)
        expired = summarize_combat(events, "111", now_ns=4_100_000_000)
        self.assertEqual(recent["pvp"]["name"], "Rival")
        self.assertIsNone(expired["pvp"])

    def test_live_stream_prunes_old_remote_players_and_keeps_local_player(self):
        stream = LiveEventStream()
        now_ns = time.time_ns()
        flow = "10.0.0.1:12020 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow,
            "ts_ns": now_ns - 20_000_000_000,
            "type": "world_info_prefix",
            "data": {"fields": {"character_uid": 111}},
        }, {
            "flow": flow,
            "ts_ns": now_ns - 20_000_000_000,
            "type": "appear_player_list",
            "data": {"units": [
                {"uid": 10, "character_uid": 111, "name": "Local"},
                {"uid": 20, "character_uid": 222, "name": "Antigo"},
            ]},
        }, {
            "flow": flow,
            "ts_ns": now_ns,
            "type": "appear_player_list",
            "data": {"units": [
                {"uid": 30, "character_uid": 333, "name": "Novo"},
            ]},
        }, {
            "flow": flow,
            "ts_ns": now_ns,
            "type": "select_target_request",
            "data": {"target_uid": 40},
        }, {
            "flow": flow,
            "ts_ns": now_ns - 20_000_000_000,
            "type": "appear_player_list",
            "data": {"units": [
                {"uid": 40, "character_uid": 444, "name": "Alvo ativo"},
            ]},
        }])
        stream.last_received_ns = now_ns

        events = stream.snapshot()
        players = [
            unit
            for event in events
            if event.get("type") == "appear_player_list"
            for unit in (event.get("data") or {}).get("units") or []
        ]

        self.assertEqual(
            {int(player["character_uid"]) for player in players},
            {111, 333, 444},
        )

    def test_live_stream_prunes_expired_combat_events_even_when_flows_are_out_of_order(self):
        stream = LiveEventStream()
        now_ns = time.time_ns()
        stream._remember([
            {
                "flow": "new",
                "ts_ns": now_ns,
                "type": "select_target_request",
                "data": {"target_uid": 20},
            },
            {
                "flow": "old",
                "ts_ns": now_ns - 60_000_000_000,
                "type": "select_target_request",
                "data": {"target_uid": 30},
            },
        ])
        stream.last_received_ns = now_ns

        events = stream.snapshot()

        self.assertEqual(
            [event["data"]["target_uid"] for event in events],
            [20],
        )

    def test_live_stream_prunes_expired_boss_anchor_and_events(self):
        stream = LiveEventStream(boss_indexes={375100}, boss_event_seconds=1)
        now_ns = time.time_ns()
        flow = "127.0.0.1:12020 -> 127.0.0.1:50000"
        stream._remember([{
            "flow": flow,
            "ts_ns": now_ns - 3_000_000_000,
            "type": "appear_monster_list",
            "data": {"units": [{"uid": 30, "npc_index": 375100}]},
        }, {
            "flow": flow,
            "ts_ns": now_ns - 2_000_000_000,
            "type": "use_skill_result",
            "data": {
                "ret": 0, "caster_uid": 10,
                "effect_results": [{"uid": 30, "hp_damage": 1}],
            },
        }])
        stream.last_received_ns = now_ns

        stream.snapshot()

        self.assertEqual(stream.metrics()["boss_anchors"], 0)
        self.assertEqual(stream.metrics()["boss_events"], 0)

    def test_live_stream_stop_finishes_old_worker_before_restart(self):
        class SlowDecoder:
            def feed(self, *_args):
                time.sleep(0.1)
                return []

        stream = LiveEventStream()
        stream._decoder = SlowDecoder()
        stream.start()
        old_worker = stream._thread
        for index in range(50):
            stream.feed(index, b"packet")
        time.sleep(0.02)

        stream.stop()

        self.assertIsNotNone(old_worker)
        self.assertFalse(old_worker.is_alive())
        stream.start()
        self.assertIsNot(stream._thread, old_worker)
        stream.stop()

    def test_live_stream_bounds_pending_packets_before_decode(self):
        stream = LiveEventStream(max_pending_packets=2)
        stream.feed(1, b"first")
        stream.feed(2, b"second")
        stream.feed(3, b"third")

        metrics = stream.metrics()

        self.assertEqual(metrics["queue_depth"], 2)
        self.assertEqual(metrics["dropped_packets"], 1)

    def test_live_stream_bounds_pending_packet_bytes_before_decode(self):
        stream = LiveEventStream(
            max_pending_packets=10,
            max_pending_packet_bytes=10,
        )
        stream.feed(1, b"123456")
        stream.feed(2, b"abcdef")

        metrics = stream.metrics()

        self.assertEqual(metrics["queue_depth"], 1)
        self.assertEqual(metrics["queue_bytes"], 6)
        self.assertEqual(metrics["dropped_packets"], 1)

    def test_live_stream_clear_preserves_custom_memory_limits(self):
        stream = LiveEventStream(
            max_events=5000,
            max_entity_anchors=1024,
            max_pending_packets=2048,
            max_pending_packet_bytes=8 * 1024**2,
            max_boss_events=1024,
            max_flows=16,
            max_pending_segments_per_flow=64,
            max_pending_bytes_per_flow=1024**2,
            max_flow_buffer_bytes=1024**2,
        )

        stream.clear()
        metrics = stream.metrics()

        self.assertEqual(metrics["queue_limit"], 2048)
        self.assertEqual(metrics["queue_byte_limit"], 8 * 1024**2)
        self.assertEqual(metrics["event_limit"], 5000)
        self.assertEqual(metrics["entity_anchor_limit"], 1024)
        self.assertEqual(metrics["boss_event_limit"], 1024)
        self.assertEqual(metrics["flow_limit"], 16)
        self.assertEqual(metrics["pending_tcp_segments_per_flow_limit"], 64)
        self.assertEqual(metrics["pending_tcp_bytes_per_flow_limit"], 1024**2)
        self.assertEqual(metrics["flow_buffer_byte_limit"], 1024**2)

    def test_live_stream_compacts_old_events_under_memory_pressure(self):
        stream = LiveEventStream(max_events=5000, max_boss_events=1024)
        stream._events.extend(
            {"ts_ns": index, "type": "drop_item_field", "data": {}}
            for index in range(4000)
        )

        compacted = stream.compact(0.5)
        metrics = stream.metrics()

        self.assertEqual(compacted["events"], 2500)
        self.assertEqual(metrics["event_limit"], 2500)
        self.assertEqual(metrics["memory_compactions"], 1)
        self.assertEqual(stream.snapshot()[0]["ts_ns"], 1500)

    def test_drop_alert_projection_filters_non_items_and_internal_ids(self):
        event = {
            "ts_ns": 123,
            "stream_offset": 45,
            "bundle_seq": 0,
            "type": "drop_item_field",
            "client_key": "client:a",
            "character_name": "Alice",
            "data": {
                "ret": 0,
                "results": [
                    {"ret": 0, "item_index": 900, "count": 100},
                    {"ret": 0, "item_index": 1, "count": 50},
                    {"ret": 0, "item_index": 1701, "count": 7},
                    {"ret": 0, "item_index": 270062, "count": 2,
                     "item_id": 987654321, "action_code": 1000},
                    {"ret": 0, "item_index": 270062, "count": 1,
                     "item_id": 987654322, "action_code": 1000},
                    {"ret": 9, "item_index": 270063, "count": 1},
                ],
            },
        }

        alerts = confirmed_item_drop_alerts(
            [event], {"270062": "Talica rara"}
        )

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["character_name"], "Alice")
        self.assertEqual(alerts[0]["source"], "server_reward_event")
        self.assertEqual(alerts[0]["items"], [{
            "item_index": 270062,
            "name": "Talica rara",
            "count": 3,
        }])
        serialized = json.dumps(alerts[0])
        self.assertNotIn("987654321", serialized)
        self.assertNotIn("item_id", serialized)
        self.assertEqual(
            confirmed_item_drop_alerts([{**event, "data": {**event["data"], "ret": 5}}]),
            [],
        )

    def test_identical_drops_accumulate_only_inside_the_same_client(self):
        candidates = [
            {
                "client_key": "client:a", "character_name": "Alice",
                "observed_at_ns": 10,
                "items": [{"item_index": 7, "name": "Item", "count": 2}],
            },
            {
                "client_key": "client:a", "character_name": "Alice",
                "observed_at_ns": 20,
                "items": [{"item_index": 7, "name": "Item", "count": 3}],
            },
            {
                "client_key": "client:b", "character_name": "Bob",
                "observed_at_ns": 30,
                "items": [{"item_index": 7, "name": "Item", "count": 9}],
            },
        ]

        rows = aggregate_item_drops_by_client(candidates)

        self.assertEqual(len(rows), 2)
        by_client = {row["client_key"]: row for row in rows}
        self.assertEqual(by_client["client:a"]["count"], 5)
        self.assertEqual(by_client["client:a"]["occurrences"], 2)
        self.assertEqual(by_client["client:a"]["first_observed_at_ns"], 10)
        self.assertEqual(by_client["client:a"]["last_observed_at_ns"], 20)
        self.assertEqual(by_client["client:b"]["count"], 9)

    def test_live_stream_retains_confirmed_drop_for_realtime_alert(self):
        stream = LiveEventStream()
        event = {
            "flow": "127.0.0.1:12020 -> 127.0.0.1:50000",
            "ts_ns": 1_000_000_000,
            "type": "drop_item_field",
            "data": {"ret": 0, "results": [{
                "ret": 0, "item_index": 270062, "count": 1,
            }]},
        }

        stream._remember([event])

        self.assertIn(event, stream.snapshot())

    def test_live_stream_retains_chat_loot_announcement_for_history(self):
        stream = LiveEventStream()
        event = {
            "flow": "127.0.0.1:12020 -> 127.0.0.1:50000",
            "ts_ns": 1_000_000_000,
            "type": "loot_announcement",
            "data": {"announcements": [{
                "player_name": "Rival", "item_index": 1000444, "count": 1,
            }]},
        }

        stream._remember([event])

        self.assertIn(event, stream.snapshot())

    def test_store_returns_only_recent_drop_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = CaptureStore(Path(temporary) / "capture.sqlite3")
            try:
                for offset, ts_ns, kind in (
                    (1, 1_000_000_000, "drop_item_field"),
                    (2, 150_000_000_000, "drop_item_field"),
                    (3, 200_000_000_000, "update_exp"),
                ):
                    store.conn.execute(
                        """INSERT INTO events(session_id,source,flow,stream_offset,
                           bundle_seq,ts_ns,opcode,type,character_uid,data_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        ("s", "memory", "flow", offset, 0, ts_ns, 0x040A,
                         kind, "uid", json.dumps({"ret": 0, "results": []})),
                    )
                events = store.recent_drop_events("s", recent_seconds=60)
            finally:
                store.close()

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["stream_offset"], 2)
        self.assertNotIn("flow", events[0])

    def test_live_decoder_bounds_old_tcp_flows(self):
        decoder = LiveEventDecoder(max_flows=2)
        packets = [
            ("flow-1", 12020, 1, b"a"),
            ("flow-2", 12020, 1, b"b"),
            ("flow-3", 12020, 1, b"c"),
        ]
        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ):
            for timestamp in range(3):
                decoder.feed(timestamp, b"packet")

        self.assertEqual(decoder.flow_count, 2)
        self.assertNotIn("flow-1", decoder._flows)

    def test_live_decoder_groups_events_by_process_without_merging_tcp_sequences(self):
        decoder = LiveEventDecoder(max_flows=4)
        decoder.set_connection_aliases({50001: "process:77", 50002: "process:77"})
        packets = [
            ("10.0.0.1:50001 -> 10.0.0.2:12020", 12020, 100, b"a"),
            ("10.0.0.1:50002 -> 10.0.0.2:12010", 12010, 900, b"b"),
        ]
        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ) as decode:
            decoder.feed(1, b"packet")
            decoder.feed(2, b"packet")

        self.assertEqual(decoder.flow_count, 2)
        self.assertEqual(
            [call.args[1] for call in decode.call_args_list],
            ["client-route:process:77", "client-route:process:77"],
        )
        self.assertEqual(
            {state.next_sequence for state in decoder._flows.values()},
            {101, 901},
        )

    def test_live_decoder_keeps_flow_identity_when_route_alias_arrives_late(self):
        decoder = LiveEventDecoder(max_flows=2)
        flow = "10.0.0.1:50001 -> 10.0.0.2:12020"
        packets = [
            (flow, 12020, 100, b"a"),
            (flow, 12020, 101, b"b"),
        ]
        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ) as decode:
            decoder.feed(1, b"packet")
            decoder.set_connection_aliases({50001: "process:77"})
            decoder.feed(2, b"packet")

        self.assertEqual(
            [call.args[1] for call in decode.call_args_list],
            [flow, flow],
        )

    def test_live_decoder_resolves_new_route_before_fixing_flow_identity(self):
        decoder = LiveEventDecoder(max_flows=2)
        resolver = Mock(return_value={50001: "process:77"})
        decoder.set_connection_alias_resolver(resolver)
        flow = "10.0.0.1:50001 -> 10.0.0.2:12020"
        packets = [
            (flow, 12020, 100, b"a"),
            (flow, 12020, 101, b"b"),
        ]
        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ) as decode:
            decoder.feed(1, b"packet")
            decoder.feed(2, b"packet")

        resolver.assert_called_once_with()
        self.assertEqual(
            [call.args[1] for call in decode.call_args_list],
            ["client-route:process:77", "client-route:process:77"],
        )
        self.assertEqual(decoder.alias_resolution_attempts, 1)
        self.assertEqual(decoder.alias_resolution_hits, 1)
        self.assertEqual(decoder.alias_resolution_errors, 0)

    def test_live_decoder_alias_resolver_failure_keeps_capture_running(self):
        decoder = LiveEventDecoder(max_flows=2)
        decoder.set_connection_alias_resolver(
            Mock(side_effect=OSError("rota indisponivel"))
        )
        flow = "10.0.0.1:50001 -> 10.0.0.2:12020"
        with patch(
            "core.live_stream._tcp_payload",
            return_value=(flow, 12020, 100, b"a"),
        ), patch.object(decoder, "_decode_available", return_value=[]) as decode:
            decoder.feed(1, b"packet")

        self.assertEqual(decode.call_args.args[1], flow)
        self.assertEqual(decoder.alias_resolution_errors, 1)

    def test_live_decoder_bounds_out_of_order_tcp_segments_and_bytes(self):
        decoder = LiveEventDecoder(
            max_pending_segments=3,
            max_pending_bytes=12,
        )
        packets = [
            ("flow", 12020, sequence, b"data")
            for sequence in (0, 10, 20, 30, 40, 50)
        ]
        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ):
            for timestamp in range(len(packets)):
                decoder.feed(timestamp, b"packet")

        self.assertLessEqual(decoder.pending_segment_count, 3)
        self.assertLessEqual(decoder.pending_bytes, 12)

    def test_live_decoder_recovers_only_stalled_tcp_flow_after_gap_timeout(self):
        decoder = LiveEventDecoder(gap_recovery_seconds=5)
        packets = [
            ("flow-a", 12020, 100, b"head"),
            ("flow-b", 12020, 500, b"safe"),
            ("flow-a", 12020, 108, b"next"),
            ("flow-a", 12020, 112, b"tail"),
        ]
        timestamps = (1, 2, 1_000_000_000, 6_100_000_000)

        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ):
            for timestamp in timestamps:
                decoder.feed(timestamp, b"packet")

        stalled = decoder._flows["flow-a"]
        untouched = decoder._flows["flow-b"]
        self.assertEqual(decoder.gap_recoveries, 1)
        self.assertEqual(decoder.recovered_gap_bytes, 4)
        self.assertEqual(decoder.discarded_partial_bytes, 4)
        self.assertEqual(decoder.last_gap_recovery_ns, 6_100_000_000)
        self.assertEqual(stalled.next_sequence, 116)
        self.assertEqual(bytes(stalled.buffer), b"nexttail")
        self.assertFalse(stalled.pending)
        self.assertEqual(bytes(untouched.buffer), b"safe")

    def test_live_decoder_accepts_late_missing_segment_without_recovery(self):
        decoder = LiveEventDecoder(gap_recovery_seconds=5)
        packets = [
            ("flow", 12020, 100, b"head"),
            ("flow", 12020, 108, b"tail"),
            ("flow", 12020, 104, b"miss"),
        ]

        with patch("core.live_stream._tcp_payload", side_effect=packets), patch.object(
            decoder, "_decode_available", return_value=[]
        ):
            decoder.feed(1, b"packet")
            decoder.feed(1_000_000_000, b"packet")
            decoder.feed(7_000_000_000, b"packet")

        state = decoder._flows["flow"]
        self.assertEqual(decoder.gap_recoveries, 0)
        self.assertEqual(state.next_sequence, 112)
        self.assertEqual(bytes(state.buffer), b"headmisstail")
        self.assertFalse(state.pending)

    def test_knowledge_store_pages_and_filters_large_pvp_bank(self):
        with tempfile.TemporaryDirectory() as temporary:
            knowledge = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                knowledge.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [
                        {
                            "character_uid": 1000 + index,
                            "name": f"Jogador {index:03d}",
                        }
                        for index in range(300)
                    ]},
                }])

                page = knowledge.characters(limit=250)
                filtered = knowledge.characters(query="Jogador 299", limit=250)
                total = knowledge.character_count()
            finally:
                knowledge.close()

        self.assertEqual(len(page), 250)
        self.assertEqual(total, 300)
        self.assertEqual(
            [row["character_uid"] for row in filtered], ["1299"]
        )

    def test_live_stream_never_evicts_active_boss_under_parallel_event_load(self):
        stream = LiveEventStream(max_events=3, boss_indexes={375100})
        flow = "127.0.0.1:12020 -> 127.0.0.1:50000"
        stream._remember([
            {
                "flow": flow,
                "ts_ns": 1_000_000_000,
                "type": "world_info_prefix",
                "data": {"fields": {"character_uid": "111"}},
            },
            {
                "flow": flow,
                "ts_ns": 2_000_000_000,
                "type": "appear_player_list",
                "data": {"units": [{"character_uid": 111, "uid": 10, "name": "Local"}]},
            },
            {
                "flow": flow,
                "ts_ns": 3_000_000_000,
                "type": "appear_monster_list",
                "data": {"units": [{
                    "uid": 30,
                    "npc_index": 375100,
                    "max_hp": 500_000_000,
                    "current_hp": 500_000_000,
                }]},
            },
        ])
        stream._remember([
            {
                "flow": flow,
                "ts_ns": 4_000_000_000 + index,
                "type": "unparsed",
                "data": {},
            }
            for index in range(30_000)
        ])
        stream._remember([{
            "flow": flow,
            "ts_ns": 4_500_000_000,
            "type": "world_info_prefix",
            "data": {"fields": {"character_uid": "111"}},
        }])
        stream._remember([
            {
                "flow": flow,
                "ts_ns": 5_000_000_000 + index,
                "type": "use_skill_result",
                "data": {
                    "ret": 0,
                    "caster_uid": 99,
                    "effect_results": [{"uid": 999, "hp_damage": 1, "final_hp": 99}],
                },
            }
            for index in range(10)
        ])
        stream._remember([{
            "flow": flow,
            "ts_ns": 6_000_000_000,
            "type": "use_skill_result",
            "data": {
                "ret": 0,
                "caster_uid": 10,
                "effect_results": [{
                    "uid": 30,
                    "hp_damage": 1_000_000,
                    "final_hp": 499_000_000,
                }],
            },
        }, {
            "flow": flow,
            "ts_ns": 6_500_000_000,
            "opcode": 0x031D,
            "type": "unparsed",
            "data": {},
        }])

        events = stream.snapshot()
        result = summarize_combat(
            events,
            "111",
            boss_catalog={
                375100: {"name": "Xenogeyser", "level": 70, "npc_subtype": 106}
            },
            now_ns=7_000_000_000,
        )

        self.assertEqual(result["bosses"][0]["name"], "Xenogeyser")
        self.assertEqual(result["bosses"][0]["current_hp"], 499_000_000)
        self.assertFalse(any(
            event.get("type") == "unparsed" and event.get("opcode") != 0x031D
            for event in events
        ))
        self.assertEqual(stream.metrics()["ignored_events"], 30_000)
        self.assertEqual(stream.metrics()["boss_anchors"], 1)
        self.assertEqual(stream.metrics()["boss_events"], 2)
        self.assertEqual(stream.metrics()["dropped_events"], 7)

        stream._remember([{
            "flow": flow,
            "ts_ns": 8_000_000_000,
            "type": "dying_unit",
            "data": {"uid": 30, "killer_uid": 10},
        }])
        death_result = summarize_combat(
            stream.snapshot(),
            "111",
            boss_catalog={375100: {"name": "Xenogeyser"}},
            now_ns=8_000_000_000,
        )
        self.assertEqual(death_result["bosses"], [])
        self.assertEqual(death_result["pve_activity"]["kind"], "kill")

    def test_live_stream_accelerated_soak_bounds_every_resident_collection(self):
        stream = LiveEventStream(
            max_events=64,
            boss_indexes={375100},
            max_entity_anchors=32,
            boss_event_seconds=1_000_000,
            max_boss_events=16,
        )
        for batch in range(50):
            events = []
            for offset in range(100):
                index = batch * 100 + offset
                flow = f"flow-{index}"
                uid = 100_000 + index
                ts_ns = 1_000_000_000 + index
                events.extend((
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "type": "world_info_prefix",
                        "data": {"fields": {"character_uid": str(uid)}},
                    },
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "type": "enemy_guild_list",
                        "data": {"guilds": []},
                    },
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "type": "appear_monster_list",
                        "data": {"units": [{
                            "uid": uid,
                            "npc_index": 375100,
                        }]},
                    },
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "type": "move_player_update",
                        "data": {"fields": {"entity_uid": uid}},
                    },
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "opcode": 0x031D,
                        "type": "unparsed",
                        "data": {},
                    },
                    {
                        "flow": flow,
                        "ts_ns": ts_ns,
                        "type": "select_target_request",
                        "data": {"target_uid": uid + 10_000_000},
                    },
                ))
            stream._remember(events)

        metrics = stream.metrics()

        self.assertEqual(metrics["identity_contexts"], 64)
        self.assertLessEqual(metrics["guild_contexts"], 128)
        self.assertLessEqual(metrics["boss_anchors"], 32)
        self.assertLessEqual(metrics["map_events"], 64)
        self.assertEqual(metrics["boss_events"], 16)
        self.assertEqual(metrics["retained_events"], 64)

    def test_combat_event_reader_keeps_identity_outside_recent_window(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "combat.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(Path(folder) / "state.sqlite3")
            events = [{
                "flow": "flow", "stream_offset": 1, "bundle_seq": 0,
                "ts_ns": 1, "opcode": 0x0305, "type": "appear_player_list",
                "data": {"units": [{"character_uid": 111, "uid": 10}]},
            }, {
                "flow": "flow", "stream_offset": 2, "bundle_seq": 0,
                "ts_ns": 2, "opcode": 0x0307, "type": "appear_monster_list",
                "data": {"units": [{"uid": 30, "npc_index": 5}]},
            }]
            events.extend({
                "flow": "flow", "stream_offset": index, "bundle_seq": 0,
                "ts_ns": 100_000_000_000 + index, "opcode": 0x0602,
                "type": "use_skill_result", "data": {
                    "caster_uid": 10,
                    "effect_results": [{"uid": 30, "hp_damage": 1, "final_hp": 50}],
                },
            } for index in range(3, 1003))
            with store.conn:
                store.conn.executemany(
                    """INSERT INTO events
                       (source,flow,stream_offset,bundle_seq,ts_ns,opcode,type,
                        character_uid,data_json,session_id)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    [
                        (
                            str(source), event["flow"], event["stream_offset"],
                            event["bundle_seq"], event["ts_ns"], event["opcode"],
                            event["type"], "111", json.dumps(event["data"]),
                            "session",
                        )
                        for event in events
                    ],
                )
            result = store.combat_events("session", "111")
            store.close()
            self.assertEqual(result[0]["type"], "appear_player_list")
            self.assertEqual(result[1]["type"], "appear_monster_list")
            self.assertEqual(result[-1]["type"], "use_skill_result")
            self.assertEqual(
                summarize_combat(result, "111", {5: "Mob definido"})["pve"]["uid"],
                30,
            )

    def test_capture_heartbeat_timeout_is_one_minute(self):
        capture = PktmonCapture(Path("capture-test"), runner=lambda *_a, **_k: None)
        self.assertEqual(capture._heartbeat_timeout_seconds, 60)

    def test_ui_event_batch_is_incremental_and_readonly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.sqlite3"
            store = CaptureStore(path)
            with store.conn:
                for index in range(2):
                    store.conn.execute(
                        """INSERT INTO events
                           (source,flow,stream_offset,bundle_seq,ts_ns,opcode,
                            type,character_uid,data_json,session_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "source",
                            "flow",
                            index,
                            0,
                            index + 1,
                            0x0307,
                            "update_exp",
                            "uid-1",
                            json.dumps({"fields": {"level": 1, "exp": index}}),
                            "session-1",
                        ),
                    )
            readonly = CaptureStore(path, readonly=True)
            first, cursor = readonly.ui_event_batch("session-1", "uid-1")
            second, same_cursor = readonly.ui_event_batch(
                "session-1", "uid-1", after_id=cursor
            )
            self.assertEqual(len(first), 2)
            self.assertEqual(second, [])
            self.assertEqual(same_cursor, cursor)
            with self.assertRaises(sqlite3.OperationalError):
                readonly.conn.execute("DELETE FROM events")
            readonly.close()
            store.close()

    def test_subsession_intervals_use_event_time_without_overlap(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CaptureStore(Path(folder) / "state.sqlite3")

            def add_event(offset: int, timestamp: int) -> None:
                with store.conn:
                    store.conn.execute(
                        """INSERT INTO events
                           (source,flow,stream_offset,bundle_seq,ts_ns,opcode,
                            type,character_uid,data_json,session_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (
                            "source", "flow", offset, 0, timestamp, 0x0307,
                            "update_exp", "uid-1", "{}", "session-1",
                        ),
                    )

            add_event(1, 199)
            add_event(2, 200)
            first = store.interval_envelope("session-1", "uid-1", 100, 200)
            second = store.interval_envelope("session-1", "uid-1", 200, 300)
            self.assertEqual([event["ts_ns"] for event in first["events"]], [199])
            self.assertEqual([event["ts_ns"] for event in second["events"]], [200])

            add_event(3, 150)
            refreshed = store.interval_envelope("session-1", "uid-1", 100, 200)
            self.assertEqual(
                [event["ts_ns"] for event in refreshed["events"]],
                [150, 199],
            )
            store.close()

    def test_capture_heartbeat_is_atomic_and_removed_on_stop(self):
        class Runner:
            running = True

            def __call__(self, args, **_kwargs):
                if args[1] == "stop":
                    self.running = False
                running = self.running

                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = (
                        "Packet Monitor is running."
                        if running
                        else "Packet Monitor is not running."
                    )

                return Result()

        with tempfile.TemporaryDirectory() as tmp:
            capture = PktmonCapture(Path(tmp), runner=Runner())
            capture._active = True
            capture._start_watchdog()
            self.assertTrue(capture._heartbeat_path.is_file())
            self.assertEqual(
                json.loads(capture._heartbeat_path.read_text())["pid"], os.getpid()
            )
            capture._active = False
            capture.heartbeat()
            self.assertTrue(capture._heartbeat_path.is_file())
            capture.stop()
            self.assertFalse(capture._heartbeat_path.exists())
    def test_clear_session_removes_raw_and_decoded_state_only_for_target(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            first = root / "first.pcap"
            second = root / "second.pcap"
            first.write_bytes(b"raw")
            second.write_bytes(b"keep")
            store = CaptureStore(root / "state.sqlite3")
            store.add_events(first, [], "discard")
            store.add_events(second, [], "keep")
            store.add_capture_window("discard", "market", 100, 200)
            store.start_subsession(
                "sub-discard",
                "discard",
                "Farm",
                started_ns=300,
            )

            store.clear_session("discard")

            self.assertEqual(store.session_sources("discard"), [])
            self.assertEqual(store.capture_windows("discard"), [])
            self.assertEqual(store.subsessions("discard"), [])
            self.assertEqual(store.session_sources("keep"), [second])
            store.start_subsession(
                "sub-next",
                "keep",
                "Farm seguinte",
                started_ns=400,
            )
            self.assertEqual(store.subsessions("keep")[0]["sequence"], 2)
            store.close()

    def test_subsession_can_be_renamed_and_deleted_without_events(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CaptureStore(Path(folder) / "capture.sqlite3")
            store.start_subsession("sub-1", "session", "Antes", started_ns=1)
            store.rename_subsession("sub-1", "Depois")
            subsession = store.subsessions("session")[0]
            self.assertEqual(subsession["name"], "Depois")
            self.assertEqual(subsession["mau_state"], "pending_evidence")
            self.assertEqual(subsession["launcher_state"], "pending_evidence")
            self.assertEqual(subsession["exp_potion_state"], "pending_evidence")
            self.assertEqual(store.delete_subsessions(("sub-1",)), 1)
            self.assertEqual(store.subsessions("session"), [])
            store.close()

    def test_subsession_edit_preserves_selected_client(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CaptureStore(Path(folder) / "capture.sqlite3")
            store.start_subsession(
                "sub-1",
                "session",
                "Antes",
                client_key="client:a",
                started_ns=1,
            )
            store.update_subsession(
                "sub-1",
                name="Depois",
                character_uid="202",
                client_key="client:b",
                location="Mapa > Spot",
                map_name="Mapa",
                spot_name="Spot",
                mobs=["Mob"],
                mob_levels={"Mob": 10},
                duration_minutes=30,
                auto_context=True,
            )
            saved = store.subsessions("session")[0]
            self.assertEqual(
                (saved["name"], saved["client_key"], saved["character_uid"]),
                ("Depois", "client:b", "202"),
            )
            self.assertTrue(saved["auto_context"])
            self.assertEqual(saved["context_source"], "manual")
            self.assertEqual(saved["context_confidence"], "confirmed")
            store.close()

    def test_session_checkpoint_is_idempotent_and_promotes_reason(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "session.pcap"
            source.write_bytes(b"raw")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(source, [], "session")
                store.checkpoint_session("session", reason="interval")
                store.checkpoint_session("session", reason="paused")
                checkpoints = store.session_checkpoints("session")
            finally:
                store.close()

        self.assertEqual(len(checkpoints), 1)
        self.assertEqual(checkpoints[0]["reason"], "paused")

    def test_auto_subsession_context_only_fills_new_confirmed_values(self):
        with tempfile.TemporaryDirectory() as folder:
            store = CaptureStore(Path(folder) / "capture.sqlite3")
            store.start_subsession(
                "sub-1", "session", "Automática",
                client_key="client:a", auto_context=True, started_ns=1,
            )
            changed = store.update_auto_subsession_context(
                "session", "client:a",
                map_name="Mapa #9", mobs=[],
            )
            refined = store.update_auto_subsession_context(
                "session", "client:a",
                map_name="Abismo", spot_name="Câmara",
                mobs=["Boss"], mob_levels={"Boss": 70},
                context_source="proximity", context_confidence="stable",
                context_observation_count=3,
                context_first_seen_ns=10, context_updated_ns=20,
            )
            repeated = store.update_auto_subsession_context(
                "session", "client:a",
                map_name="Outro", spot_name="Outro spot",
                mobs=["Boss"], mob_levels={"Boss": 70},
            )
            saved = store.subsessions("session")[0]
            store.close()
        self.assertTrue(changed)
        self.assertTrue(refined)
        self.assertFalse(repeated)
        self.assertEqual((saved["map_name"], saved["spot_name"]), ("Abismo", "Câmara"))
        self.assertEqual(saved["mobs"], ["Boss"])
        self.assertEqual(saved["context_source"], "proximity")
        self.assertEqual(saved["context_confidence"], "stable")
        self.assertEqual(saved["context_observation_count"], 3)
        self.assertEqual(saved["context_first_seen_ns"], 10)
        self.assertEqual(saved["context_updated_ns"], 20)

    def test_auto_subsession_inference_requires_unique_catalog_spot(self):
        from core.subsession_context import infer_subsession_context

        monitor = {"nearby_monsters": [
            {"name": "Mob A", "level": 10, "stale": False},
            {"name": "Mob B", "level": 11, "stale": False},
        ]}
        catalog = {
            "Mapa 1": {
                "Spot único": {"Mob A": (10,), "Mob B": (11,)},
                "Outro": {"Mob A": (10,)},
            },
            "Mapa 2": {"Comum": {"Mob A": (10,)}},
        }
        inferred = infer_subsession_context(monitor, "", catalog)
        ambiguous = infer_subsession_context(
            {"nearby_monsters": [monitor["nearby_monsters"][0]]}, "", catalog
        )
        self.assertEqual(
            (inferred["map_name"], inferred["spot_name"]),
            ("Mapa 1", "Spot único"),
        )
        self.assertEqual((ambiguous["map_name"], ambiguous["spot_name"]), ("", ""))

        fixed_region = infer_subsession_context(
            monitor,
            {"map_name": "Android Junkyard", "region_name": "8F"},
            {"Android Junkyard": {"8F": {"Mob A": (10,), "Mob B": (11,)}}},
        )
        self.assertEqual(
            (fixed_region["map_name"], fixed_region["spot_name"]),
            ("Android Junkyard", "8F"),
        )

    def test_auto_subsession_context_requires_stable_repeated_observations(self):
        from core.subsession_context import SubsessionContextStabilizer

        stabilizer = SubsessionContextStabilizer(
            min_observations=3, min_stable_seconds=5
        )
        context = {
            "map_name": "Abismo",
            "spot_name": "Câmara",
            "mobs": ["Boss"],
            "mob_levels": {"Boss": 70},
        }
        self.assertIsNone(
            stabilizer.observe("client:a", context, now_ns=1_000_000_000)
        )
        self.assertIsNone(
            stabilizer.observe("client:a", context, now_ns=3_000_000_000)
        )
        stable = stabilizer.observe(
            "client:a", context, now_ns=6_000_000_000
        )
        self.assertEqual(stable["context_confidence"], "stable")
        self.assertEqual(stable["context_observation_count"], 3)
        self.assertEqual(stable["context_first_seen_ns"], 1_000_000_000)

    def test_auto_subsession_context_resets_when_spot_oscillates(self):
        from core.subsession_context import SubsessionContextStabilizer

        stabilizer = SubsessionContextStabilizer(
            min_observations=2, min_stable_seconds=0
        )
        first = {"map_name": "Mapa", "spot_name": "A", "mobs": ["Mob"]}
        second = {"map_name": "Mapa", "spot_name": "B", "mobs": ["Mob"]}
        self.assertIsNone(stabilizer.observe("client:a", first, now_ns=1))
        self.assertIsNone(stabilizer.observe("client:a", second, now_ns=2))
        stable = stabilizer.observe("client:a", second, now_ns=3)
        self.assertEqual(stable["spot_name"], "B")
        self.assertEqual(stable["context_observation_count"], 2)

    def test_auto_subsession_context_ignores_transient_mob(self):
        from core.subsession_context import SubsessionContextStabilizer

        stabilizer = SubsessionContextStabilizer(
            min_observations=3, min_stable_seconds=0
        )
        first = {
            "map_name": "Mapa",
            "spot_name": "Spot",
            "mobs": ["Residente", "De passagem"],
            "mob_levels": {"Residente": 10, "De passagem": 20},
        }
        repeated = {
            "map_name": "Mapa",
            "spot_name": "Spot",
            "mobs": ["Residente"],
            "mob_levels": {"Residente": 10},
        }
        self.assertIsNone(stabilizer.observe("client:a", first, now_ns=1))
        self.assertIsNone(stabilizer.observe("client:a", repeated, now_ns=2))
        stable = stabilizer.observe("client:a", repeated, now_ns=3)
        self.assertEqual(stable["mobs"], ["Residente"])
        self.assertEqual(stable["mob_levels"], {"Residente": 10})

    def test_program_status_keeps_concurrent_signals_and_presentation_priority(self):
        from core.program_status import build_program_status

        status = build_program_status(
            [{
                "client_key": "client:a",
                "local_combat_uid": 10,
                "local": {"hp_percent": 20.0},
                "pve_activity": {
                    "observed_at_ns": 99, "kind": "damage", "target_uid": 30,
                },
                "pvp_activity": {
                    "last_seen_ns": 99, "direction": "entrada"
                },
                "nearby_players": [{"pvp_status": "enemy", "stale": False}],
                "bosses": [{"age_seconds": 2.0, "stale": False}],
            }],
            {"clients": [{
                "client_key": "client:a", "observed_at_ns": 10,
                "age_seconds": 0.5, "teleporting": True, "stale": False,
            }]},
            ("pve", "pvp", "boss"),
            low_hp_percent=30,
            now_ns=100,
        )
        client = status["clients"][0]
        self.assertEqual(client["availability"], "available")
        self.assertEqual(client["activity"], "pvp")
        self.assertEqual(client["active_activities"], ["farm", "pvp", "boss"])
        self.assertEqual(client["display_status"], "teleporting")
        self.assertEqual(
            client["signals"],
            {
                "threat": True,
                "under_attack": True,
                "low_hp": True,
                "boss_nearby": True,
                "teleporting": True,
            },
        )

    def test_program_status_uses_unknown_when_monitor_dimension_is_disabled(self):
        from core.program_status import build_program_status

        client = build_program_status(
            [{"client_key": "client:a", "local_combat_uid": 10}],
            {},
            (),
            now_ns=100,
        )["clients"][0]
        self.assertEqual(client["activity"], "idle")
        self.assertIsNone(client["signals"]["threat"])
        self.assertIsNone(client["signals"]["under_attack"])

    def test_program_status_farm_requires_pve_activity_and_expires_after_thirty_seconds(self):
        from core.program_status import build_program_status

        monitor = [{
            "client_key": "client:a",
            "pve_activity": {
                "observed_at_ns": 1_000_000_000,
                "kind": "damage",
                "target_uid": 30,
            },
        }]
        recent = build_program_status(
            monitor, {}, ("pve",), now_ns=31_000_000_000
        )["clients"][0]
        expired = build_program_status(
            monitor, {}, ("pve",), now_ns=31_000_000_001
        )["clients"][0]
        self.assertEqual(recent["display_status"], "farm")
        self.assertEqual(expired["display_status"], "idle")

        exp_only = build_program_status(
            [{
                "client_key": "client:a",
                "exp_gain": {"observed_at_ns": 31_000_000_000, "amount": 10},
            }],
            {},
            ("pve",),
            now_ns=31_000_000_000,
        )["clients"][0]
        self.assertEqual(exp_only["display_status"], "idle")

    def test_automatic_subsession_end_uses_only_confirmed_events_after_start(self):
        from core.subsession_context import automatic_subsession_end

        started = 10_000_000_000
        base = {
            "started_ns": started,
            "end_on_teleport": True,
            "end_on_death": True,
            "end_after_no_kill": True,
        }
        self.assertEqual(
            automatic_subsession_end(
                base,
                {"pve_kill": {"observed_at_ns": started + 5_000_000_000}},
                {"teleporting": True, "teleport_observed_at_ns": started - 1},
                now_ns=started + 36_000_000_000,
            ),
            (started + 35_000_000_000, "30 s sem kill"),
        )
        self.assertEqual(
            automatic_subsession_end(
                base,
                {"local_death": {"observed_at_ns": started + 8_000_000_000}},
                {"teleporting": True, "teleport_observed_at_ns": started + 12_000_000_000},
                now_ns=started + 20_000_000_000,
            ),
            (started + 8_000_000_000, "morte"),
        )
        self.assertEqual(
            automatic_subsession_end(
                {**base, "end_on_death": False, "end_after_no_kill": False},
                {},
                {"teleporting": True, "teleport_observed_at_ns": started + 12_000_000_000},
                now_ns=started + 20_000_000_000,
            ),
            (started + 12_000_000_000, "teleporte"),
        )

    def test_exp_rank_guild_enriches_boss_player_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = KnowledgeStore(Path(temporary) / "knowledge.sqlite3")
            try:
                self.assertEqual(store.observe_exp_rank_records([{
                    "character_uid": 222,
                    "name": "Jogador Blood",
                    "level": 80,
                    "guild_name": "Blood",
                }], session_id="session-blood"), 1)
                monitors = [{
                    "nearby_players": [],
                    "bosses": [{"top_damage_players": [{
                        "character_uid": "222", "damage": 5000,
                    }]}],
                }]
                store.enrich_combat_monitors(monitors)
            finally:
                store.close()

        player = monitors[0]["bosses"][0]["top_damage_players"][0]
        self.assertEqual(player["guild_name"], "Blood")
        self.assertEqual(
            monitors[0]["bosses"][0]["top_damage_guilds"][0]["name"],
            "Blood",
        )

    def test_capture_windows_and_subsessions_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "capture.sqlite3"
            store = CaptureStore(path)
            store.add_capture_window(
                "session", "market", 100, 200, "uid-1"
            )
            self.assertEqual(
                store.pending_capture_uploads("session"),
                [
                    {
                        "mode": "market",
                        "started_ns": 100,
                        "ended_ns": 200,
                        "character_uid": "uid-1",
                    }
                ],
            )
            store.set_capture_upload_state(
                "session", "market", 100, "sent"
            )
            store.start_subsession(
                "sub-1",
                "session",
                "Farm da manhã",
                character_uid="uid-1",
                location="Abismo > Câmara 3",
                map_name="Abismo",
                spot_name="Câmara 3",
                mobs=["Bellato", "Accretia"],
                mob_levels={"Bellato": 65, "Accretia": "60-67"},
                started_ns=300,
            )
            store.end_subsession("sub-1", 900)
            store.close()

            store = CaptureStore(path)
            self.assertEqual(
                store.capture_windows("session"),
                [{"mode": "market", "started_ns": 100, "ended_ns": 200}],
            )
            self.assertEqual(store.pending_capture_uploads("session"), [])
            self.assertEqual(
                store.subsessions("session")[0],
                {
                    "id": "sub-1",
                    "character_uid": "uid-1",
                    "client_key": "",
                    "name": "Farm da manhã",
                    "location": "Abismo > Câmara 3",
                    "map_name": "Abismo",
                    "spot_name": "Câmara 3",
                    "mobs": ["Bellato", "Accretia"],
                    "mob_levels": {"Accretia": "60-67", "Bellato": 65},
                    "auto_context": False,
                    "context_source": "manual",
                    "context_confidence": "confirmed",
                    "context_observation_count": 0,
                    "context_first_seen_ns": None,
                    "context_updated_ns": 300,
                    "duration_minutes": 0,
                    "end_on_teleport": False,
                    "end_on_death": False,
                    "end_after_no_kill": False,
                    "mau_state": "pending_evidence",
                    "launcher_state": "pending_evidence",
                    "exp_potion_state": "pending_evidence",
                    "started_ns": 300,
                    "ended_ns": 900,
                    "sequence": 1,
                    "upload_state": "pending",
                    "uploaded_at": None,
                },
            )
            store.set_subsession_upload_state("sub-1", "sent")
            store.start_subsession(
                "sub-2",
                "session-2",
                "Farm da tarde",
                started_ns=1000,
            )
            self.assertEqual(store.subsessions("session-2")[0]["sequence"], 2)
            store.close()

            store = CaptureStore(path)
            self.assertEqual(
                store.subsessions("session")[0]["upload_state"], "sent"
            )
            self.assertIsNotNone(
                store.subsessions("session")[0]["uploaded_at"]
            )
            self.assertEqual(store.subsessions("session-2")[0]["sequence"], 2)
            store.close()

    def test_store_can_remove_preview_sources_before_final_ingest(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "preview.pcap"
            source.write_bytes(b"preview")
            store = CaptureStore(Path(temp) / "state.sqlite3")
            store.add_events(source, [], "session-1")

            store.remove_sources((source,))

            self.assertEqual(store.session_sources("session-1"), [])
            store.close()

    def test_realtime_data_source_pointer_list_uses_windows_alignment(self):
        buffer = ctypes.create_string_buffer(
            _DataSourceList.first.offset + 2 * ctypes.sizeof(ctypes.c_void_p)
        )
        ctypes.c_uint32.from_buffer(buffer).value = 2
        ctypes.c_void_p.from_buffer(
            buffer, _DataSourceList.first.offset
        ).value = 0x1234
        ctypes.c_void_p.from_buffer(
            buffer,
            _DataSourceList.first.offset + ctypes.sizeof(ctypes.c_void_p),
        ).value = 0x5678

        self.assertEqual(_data_source_pointers(buffer), (0x1234, 0x5678))

    def test_realtime_filter_keeps_only_configured_rf_tcp_ports(self):
        packet = bytearray(54)
        packet[12:14] = b"\x08\x00"
        packet[14] = 0x45
        packet[23] = 6
        packet[34:38] = struct.pack("!HH", 53000, 12010)

        self.assertTrue(_matches_tcp_port(bytes(packet), {12010}))
        self.assertFalse(_matches_tcp_port(bytes(packet), {443}))

    def test_realtime_filter_accepts_new_ports_without_restart(self):
        capture = RealtimeCapture(Path("live.pcap"), (12020,))

        self.assertEqual(capture.add_ports((12020, 53000)), 1)
        self.assertEqual(capture.add_ports((53000,)), 0)
        self.assertEqual(capture._port_set, {12020, 53000})

    def test_realtime_capture_bounds_writer_queue_packets_and_bytes(self):
        capture = RealtimeCapture(
            Path("live.pcap"),
            (12020,),
            max_write_queue_packets=3,
            max_write_queue_bytes=10,
        )

        self.assertTrue(capture._enqueue_write_packet(1, b"123456"))
        self.assertFalse(capture._enqueue_write_packet(2, b"abcdef"))
        self.assertTrue(capture._enqueue_write_packet(3, b"7890"))
        self.assertFalse(capture._enqueue_write_packet(4, b"x"))

        self.assertEqual(capture.write_queue_depth, 2)
        self.assertEqual(capture.write_queue_bytes, 10)
        self.assertEqual(capture.dropped_write_packets, 2)
        self.assertEqual(capture.dropped_write_bytes, 7)

    def test_realtime_pcap_is_split_by_client_local_port(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "all.pcap"
            packet_a = bytearray(54)
            packet_a[12:14] = b"\x08\x00"
            packet_a[14] = 0x45
            packet_a[23] = 6
            packet_a[34:38] = struct.pack("!HH", 50100, 12010)
            packet_b = bytearray(packet_a)
            packet_b[34:38] = struct.pack("!HH", 50200, 12010)
            source.write_bytes(
                struct.pack("<IHHIIII", 0xA1B23C4D, 2, 4, 0, 0, 0xFFFF, 1)
                + struct.pack("<IIII", 1, 0, len(packet_a), len(packet_a))
                + packet_a
                + struct.pack("<IIII", 2, 0, len(packet_b), len(packet_b))
                + packet_b
            )
            first = Path(folder) / "client-a.pcap"
            second = Path(folder) / "client-b.pcap"

            kept = split_pcap_by_ports(
                source, [(first, (50100,)), (second, (50200,))]
            )

            self.assertEqual(kept, [first, second])
            self.assertEqual(first.stat().st_size, 24 + 16 + len(packet_a))
            self.assertEqual(second.stat().st_size, 24 + 16 + len(packet_b))

    def test_realtime_capture_writes_decoder_compatible_pcap(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "live.pcap"
            capture = RealtimeCapture(target, (12010,))
            writer = threading.Thread(target=capture._write_pcap)
            writer.start()
            capture._items.put((10**30, b"\x00" * 14))
            capture._items.put(None)
            writer.join(timeout=2)

            self.assertFalse(writer.is_alive())
            self.assertEqual(capture.packets, 1)
            self.assertEqual(struct.unpack("<I", target.read_bytes()[:4])[0], 0xA1B23C4D)
            packet_seconds = struct.unpack(
                "<I", target.read_bytes()[24:28]
            )[0]
            self.assertGreater(packet_seconds, 946_684_800)

    def test_realtime_checkpoint_flushes_complete_records(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "live.pcap"
            capture = RealtimeCapture(target, (12020,))
            writer = threading.Thread(target=capture._write_pcap)
            capture._writer = writer
            writer.start()
            capture._items.put((1_700_000_000_000_000_000, b"\x00" * 14))

            self.assertEqual(capture.checkpoint(), target)
            with capture.readable():
                self.assertEqual(target.stat().st_size, 24 + 16 + 14)

            capture._items.put(None)
            writer.join(timeout=2)
            self.assertFalse(writer.is_alive())

    def test_realtime_rotation_closes_one_pcap_and_continues_in_next(self):
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "live-1.pcap"
            second = Path(temp) / "live-2.pcap"
            capture = RealtimeCapture(first, (12020,))
            writer = threading.Thread(target=capture._write_pcap)
            capture._writer = writer
            writer.start()
            capture._items.put(
                (1_700_000_000_000_000_000, b"\x00" * 14)
            )

            self.assertEqual(capture.rotate(second), first)
            capture._items.put(
                (1_700_000_001_000_000_000, b"\x01" * 14)
            )
            capture.checkpoint()
            capture._items.put(None)
            writer.join(timeout=2)

            self.assertFalse(writer.is_alive())
            self.assertEqual(first.stat().st_size, 24 + 16 + 14)
            self.assertEqual(second.stat().st_size, 24 + 16 + 14)
            self.assertEqual(capture.target, second)

    def test_store_migrates_existing_capture_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.sqlite"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE events(
                 id INTEGER PRIMARY KEY, source TEXT NOT NULL, flow TEXT NOT NULL,
                 stream_offset INTEGER NOT NULL, bundle_seq INTEGER NOT NULL,
                 ts_ns INTEGER, opcode INTEGER NOT NULL, type TEXT NOT NULL,
                 character_uid TEXT, data_json TEXT NOT NULL
                );
                CREATE TABLE captures(
                 source TEXT PRIMARY KEY, size INTEGER NOT NULL,
                 mtime_ns INTEGER NOT NULL, imported_at TEXT NOT NULL,
                 events_added INTEGER NOT NULL
                );
                CREATE TABLE capture_windows(
                 id INTEGER PRIMARY KEY, session_id TEXT NOT NULL,
                 mode TEXT NOT NULL, started_ns INTEGER NOT NULL,
                 ended_ns INTEGER NOT NULL,
                 UNIQUE(session_id, mode, started_ns)
                );
                """
            )
            conn.close()
            store = CaptureStore(path)
            try:
                columns = {
                    row[1]
                    for row in store.conn.execute("PRAGMA table_info(captures)")
                }
                self.assertIn("session_id", columns)
                self.assertIn("ingestion_key", columns)
                window_columns = {
                    row[1]
                    for row in store.conn.execute(
                        "PRAGMA table_info(capture_windows)"
                    )
                }
                self.assertTrue(
                    {"character_uid", "upload_state", "uploaded_at"}
                    <= window_columns
                )
            finally:
                store.close()

    def test_collection_catalog_is_applied_during_parse(self):
        class Decoder:
            class DecodeError(Exception):
                pass

            @staticmethod
            def parse_exchange_payload(_decoded):
                return None

            @staticmethod
            def parse_collection_payload(_decoded):
                return {
                    "type": "collection_snapshot_chunk",
                    "records": [{"collection_index": 1001, "slot_values": [1]}],
                }

            @staticmethod
            def add_collection_catalog(collection, slots):
                collection["records"][0]["completed_slots"] = [0] if slots else []

        parsed = _safe_parse(Decoder, b"snapshot", 12020, {(1001, 0): {}})
        self.assertEqual(parsed["records"][0]["completed_slots"], [0])

        def fail_catalog(_collection, _slots):
            raise ValueError("catálogo")

        Decoder.add_collection_catalog = staticmethod(fail_catalog)
        self.assertIsNotNone(_safe_parse(Decoder, b"snapshot", 12020, {(1001, 0): {}}))

    def test_malformed_payload_does_not_abort_capture(self):
        class Decoder:
            class DecodeError(Exception):
                pass

            @staticmethod
            def parse_exchange_payload(_decoded):
                raise struct.error("quadro vazio")

        self.assertIsNone(_safe_parse(Decoder, b"", 12020))

    def test_pktmon_status_does_not_confuse_not_running(self):
        self.assertFalse(_pktmon_running("Packet Monitor is not running."))
        self.assertFalse(_pktmon_running("O Monitor de Pacotes não está em execução."))
        self.assertTrue(_pktmon_running("Packet Monitor is running."))
        self.assertTrue(_pktmon_running("Packet Monitor status: Active"))
        self.assertTrue(_pktmon_running("O Monitor de Pacotes está ativo."))
        self.assertTrue(_pktmon_running(
            "Dados Coletados: Contadores de pacotes, captura de pacotes "
            "Filtros de Pacote: 1 RFQOL1 TCP 12000"
        ))
        self.assertIsNone(_pktmon_state("resposta ainda não disponível"))

    def test_unknown_pktmon_status_keeps_capture_active_and_is_logged(self):
        class Runner:
            def __call__(self, _args, **_kwargs):
                class Result:
                    returncode = 0
                    stdout = ""
                    stderr = "resposta ainda não disponível"

                return Result()

        with tempfile.TemporaryDirectory() as tmp:
            capture = PktmonCapture(Path(tmp), runner=Runner())
            capture._active = True
            with self.assertLogs("rfqol", level="WARNING") as logged:
                status = capture.status()
                capture.status()
            self.assertTrue(status.active)
            self.assertEqual(len(logged.output), 1)
            self.assertIn("capture_status_unknown", "\n".join(logged.output))

    def test_pktmon_command_decodes_utf8_output(self):
        class Runner:
            kwargs = {}

            def __call__(self, _args, **kwargs):
                self.kwargs = kwargs

                class Result:
                    returncode = 0
                    stdout = "O Monitor de Pacotes não está em execução."
                    stderr = ""

                return Result()

        runner = Runner()
        capture = PktmonCapture(Path("capture-test"), runner=runner)
        self.assertFalse(capture.system_running())
        self.assertEqual(runner.kwargs["encoding"], "utf-8")
        self.assertEqual(runner.kwargs["errors"], "replace")

    def test_watchdog_receives_heartbeat_values_through_environment(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "core.capture.subprocess.Popen"
        ) as popen:
            capture = PktmonCapture(Path(tmp), runner=lambda *_a, **_k: None)
            capture._watchdog_enabled = True
            capture._start_watchdog()

        command = popen.call_args.args[0]
        environment = popen.call_args.kwargs["env"]
        self.assertEqual(command[-2], "-Command")
        self.assertNotIn("param(", command[-1])
        self.assertEqual(
            environment["RFNEXT_HEARTBEAT_PATH"], str(capture._heartbeat_path)
        )
        self.assertEqual(
            environment["RFNEXT_HEARTBEAT_TOKEN"], capture._heartbeat_token
        )
        self.assertEqual(environment["RFNEXT_HEARTBEAT_TIMEOUT"], "60")
        self.assertEqual(environment["RFNEXT_HEARTBEAT_PARENT_PID"], str(os.getpid()))

    def test_pktmon_watcher_requires_three_stopped_confirmations(self):
        class Runner:
            checks = 0

            def __call__(self, args, **_kwargs):
                class Result:
                    returncode = 0
                    stdout = "Packet Monitor is not running."
                    stderr = ""

                if args[1] == "status":
                    self.checks += 1
                return Result()

        with tempfile.TemporaryDirectory() as tmp:
            runner = Runner()
            capture = PktmonCapture(Path(tmp), runner=runner, poll_seconds=0)
            capture._active = True
            with self.assertLogs("rfqol", level="WARNING") as logged:
                capture._watch_disk()
            self.assertEqual(runner.checks, 3)
            self.assertFalse(capture.active)
            self.assertIn("capture_interrupted", "\n".join(logged.output))

    def test_connections_are_grouped_by_executable(self):
        paths = {
            10: r"C:\Games\ProjectRF.exe",
            11: r"C:\Games\ProjectRF.exe",
            12: r"C:\Browser\browser.exe",
        }
        rows = [
            (10, 50100, 9000),
            (10, 50101, 9001),
            (11, 50200, 9000),
            (12, 50300, 443),
        ]
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", side_effect=paths.get
        ):
            processes = connected_processes()
            local_ports, remote_ports, clients = ports_for_executable(paths[10])
        self.assertEqual(len(processes), 1)
        self.assertEqual(local_ports, (50100, 50101, 50200))
        self.assertEqual(remote_ports, (9000, 9001))
        self.assertEqual(clients, 2)
        self.assertEqual(ports_for_executable(paths[12]), ((), (), 0))

    def test_connections_can_exclude_non_rf_remote_ports(self):
        game = r"C:\Games\ProjectRF.exe"
        rows = [(10, 50100, 12020), (10, 50101, 443)]
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", return_value=game
        ):
            local_ports, remote_ports, clients = ports_for_executable(
                game, (12000, 12010, 12020, 12040)
            )
            routes = clients_for_executable(
                game, (12000, 12010, 12020, 12040)
            )
        self.assertEqual(
            (local_ports, remote_ports, clients),
            ((50100, 50101), (12020,), 1),
        )
        self.assertEqual(routes[0]["local_ports"], (50100, 50101))
        self.assertEqual(routes[0]["remote_ports"], (12020,))

    def test_exitlag_secondary_route_stays_scoped_to_the_game_pid(self):
        game = r"C:\Games\ProjectRF.exe"
        exitlag = r"C:\Program Files\ExitLag\ExitLagPmService.exe"
        rows = [
            (10, 50101, 9001),
            (20, 50200, 443),
        ]
        paths = {10: game, 20: exitlag}
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", side_effect=paths.get
        ):
            processes = connected_processes((12020,))
            routes = clients_for_executable(game, (12020,))

        self.assertEqual(next(iter(processes.values()))[1], {50101})
        self.assertEqual(next(iter(processes.values()))[2], set())
        self.assertEqual(routes[0]["local_ports"], (50101,))
        self.assertEqual(routes[0]["remote_ports"], ())
        self.assertNotIn(50200, routes[0]["local_ports"])

    def test_agent_routes_include_exitlag_relay_but_ignore_https(self):
        game = r"C:\Games\ProjectRF.exe"
        rows = [
            (10, 50100, 30851),
            (10, 50101, 443),
            (10, 50102, 12020),
        ]
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", return_value=game
        ):
            processes = agent_processes((12000, 12010, 12020, 12040))

        pids, local_ports, remote_ports = next(iter(processes.values()))
        self.assertEqual(pids, {10})
        self.assertEqual(local_ports, {50100, 50102})
        self.assertEqual(remote_ports, {12020})

    def test_pc_and_bluestacks_connections_are_discovered_separately(self):
        paths = {
            10: r"C:\Games\ProjectRF.exe",
            20: r"C:\Program Files\BlueStacks_nxt\HD-Player.exe",
            30: r"C:\Browser\browser.exe",
        }
        rows = [
            (10, 50100, 12020),
            (20, 57001, 12020),
            (30, 58001, 12020),
        ]
        with patch("core.connections._tcp_rows", return_value=rows), patch(
            "core.connections._process_path", side_effect=paths.get
        ):
            pc = connected_processes((12020,))
            emulators = emulator_processes((12020,))
        self.assertEqual(next(iter(pc.values()))[0], {10})
        self.assertEqual(next(iter(emulators.values()))[0], {20})
        self.assertNotIn(30, next(iter(pc.values()))[0])
        self.assertNotIn(30, next(iter(emulators.values()))[0])

    def test_seventh_route_is_stored_as_emulator_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "emulator-five.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:57005",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0307,
                        "type": "update_exp",
                        "data": {"fields": {"gain_exp": 10}},
                    }],
                    "session",
                    client_ports=(
                        (50001,), (50002,), (57001,), (57002,),
                        (57003,), (57004,), (57005,),
                    ),
                )
                owner = store.conn.execute(
                    "SELECT character_uid FROM events WHERE session_id='session'"
                ).fetchone()[0]
            finally:
                store.close()
        self.assertEqual(owner, "client:g")

    def test_unidentified_flows_are_matched_to_closest_exp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "exp.etl"
            raw.write_bytes(b"capture")
            db = CaptureStore(root / "state.sqlite")
            try:
                need = 3_908_016_337
                events = []
                for index, (flow, percent) in enumerate(
                    (("flow-high", 80), ("flow-low", 10)), 1
                ):
                    events.extend(
                        [
                            {
                                "flow": flow,
                                "stream_offset": index,
                                "bundle_seq": 0,
                                "ts_ns": index,
                                "opcode": 0x0417,
                                "type": "update_exp",
                                "data": {
                                    "fields": {
                                        "level": 67,
                                        "exp": need * percent // 100,
                                    }
                                },
                            },
                            {
                                "flow": flow,
                                "stream_offset": index + 10,
                                "bundle_seq": 0,
                                "ts_ns": index + 10,
                                "opcode": 0x040A,
                                "type": "drop_item_field",
                                "data": {"fields": {"item_id": index}},
                            },
                        ]
                    )
                events.append(
                    {
                        "flow": "flow-unknown",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "ts_ns": 100,
                        "opcode": 0x040A,
                        "type": "drop_item_field",
                        "data": {"fields": {"item_id": 99}},
                    }
                )
                db.add_events(raw, events, "session-exp")
                matches = db.assign_unidentified_by_exp(
                    "session-exp", [("Alice", 75.0), ("Bob", 12.0)]
                )
                self.assertEqual(
                    [
                        (item["name"], round(item["observed_percent"]))
                        for item in matches
                    ],
                    [("Alice", 80), ("Bob", 10)],
                )
                self.assertEqual(
                    [
                        (item["uid"], item["name"])
                        for item in db.session_profiles("session-exp")
                    ],
                    [("exp:1", ""), ("exp:2", "")],
                )
                self.assertEqual(
                    len(
                        db.session_envelope(
                            "session-exp", character_uid="exp:1"
                        )["events"]
                    ),
                    2,
                )
                self.assertEqual(
                    len(
                        db.session_envelope(
                            "session-exp", only_unassigned=True
                        )["events"]
                    ),
                    1,
                )
            finally:
                db.close()

    def test_unidentified_flow_is_assigned_to_existing_uid_by_exp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "exp.etl"
            raw.write_bytes(b"capture")
            db = CaptureStore(root / "state.sqlite")
            try:
                need = 3_908_016_337
                events = []
                for index, (flow, percent) in enumerate(
                    (("closest", 60), ("other", 10)), 1
                ):
                    events.extend(
                        [
                            {
                                "flow": flow,
                                "stream_offset": index,
                                "bundle_seq": 0,
                                "ts_ns": index,
                                "opcode": 0x0417,
                                "type": "update_exp",
                                "data": {
                                    "fields": {
                                        "level": 68,
                                        "exp": need * percent // 100,
                                    }
                                },
                            },
                            {
                                "flow": flow,
                                "stream_offset": index + 10,
                                "bundle_seq": 0,
                                "ts_ns": index + 10,
                                "opcode": 0x040A,
                                "type": "drop_item_field",
                                "data": {"fields": {"item_id": index}},
                            },
                        ]
                    )
                db.add_events(raw, events, "session-exp")
                match = db.assign_unidentified_to_uid_by_exp(
                    "session-exp", "101", 59.5
                )
                self.assertEqual(match["uid"], "101")
                self.assertEqual(
                    len(
                        db.session_envelope(
                            "session-exp", character_uid="101"
                        )["events"]
                    ),
                    2,
                )
                self.assertEqual(
                    db.session_stats("session-exp")["unassigned"], 2
                )
            finally:
                db.close()

    def test_pktmon_uses_discovered_and_reconnected_ports(self):
        class Runner:
            running = False

            def __init__(self):
                self.calls = []
                self.start_attempts = 0

            def __call__(self, args, **_kwargs):
                self.calls.append(args)
                if args[1] == "start":
                    self.start_attempts += 1
                    if self.start_attempts == 1:
                        class Busy:
                            returncode = 1
                            stderr = "O Monitor de Pacotes já foi iniciado."
                            stdout = ""

                        return Busy()
                    self.running = True
                elif args[1] == "stop":
                    self.running = False

                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = ""

                result = Result()
                if args[1] == "status":
                    result.stdout = (
                        "Packet Monitor is running."
                        if self.running
                        else "Packet Monitor is not running."
                    )
                return result

        with tempfile.TemporaryDirectory() as tmp, patch(
            "core.capture.shutil.which", return_value="pktmon"
        ):
            runner = Runner()
            capture = PktmonCapture(
                Path(tmp), runner=runner, poll_seconds=60
            )
            capture.start_for_ports("session-001", (50100, 50200))
            self.assertEqual(capture.add_ports((50200, 50300)), 1)
            capture.stop()
        filters = [
            call
            for call in runner.calls
            if call[1:3] == ["filter", "add"]
        ]
        self.assertEqual(
            [call[-1] for call in filters],
            [
                "12000",
                "12010",
                "12020",
                "12040",
                "50100",
                "50200",
                "12000",
                "12010",
                "12020",
                "12040",
                "50100",
                "50200",
                "50300",
            ],
        )
        self.assertEqual(runner.start_attempts, 2)

    def test_pktmon_orphan_is_attached_stopped_and_preserved(self):
        class Runner:
            def __init__(self):
                self.running = True
                self.calls = []

            def __call__(self, args, **_kwargs):
                self.calls.append(args)
                command = args[1]
                if command == "stop":
                    self.running = False

                class Result:
                    returncode = 0
                    stderr = ""
                    stdout = (
                        "Packet Monitor is running."
                        if self.running
                        else "Packet Monitor is not running."
                    )

                return Result()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "rfnext-20260728-010203-0011.etl"
            raw.write_bytes(b"captura preservada")
            runner = Runner()
            capture = PktmonCapture(root, runner=runner, poll_seconds=0.01)
            attached = capture.attach("rfnext-20260728-010203-001")
            self.assertTrue(attached.active)
            self.assertEqual(attached.files, (raw,))
            stopped = capture.stop()
            self.assertFalse(stopped.active)
            self.assertEqual(stopped.files, (raw,))
            self.assertTrue(raw.is_file())
            self.assertIn(["pktmon", "stop"], runner.calls)

    def test_pktmon_arguments_and_safe_export(self):
        calls = []

        class Result:
            returncode = 0
            stderr = ""
            stdout = "Stopped"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = PktmonCapture(root, segment_mb=64, runner=lambda args, **kwargs: calls.append(args) or Result())
            self.assertEqual(capture.ports, (12000, 12010, 12020, 12040))
            capture._command("start", "--capture")
            self.assertEqual(calls[0][:2], ["pktmon", "start"])

            raw = root / "segment.etl"
            raw.write_bytes(b"raw")
            db = CaptureStore(root / "state.sqlite")
            try:
                events = [
                    {
                        "flow": "10.0.0.1:50000 -> 10.0.0.2:12020", "stream_offset": 1,
                        "bundle_seq": 0, "ts_ns": 1, "opcode": 0x0101, "type": "forbidden",
                        "data": {"token": "must-not-survive"},
                    },
                    {
                        "flow": "10.0.0.2:12020 -> 10.0.0.1:50000", "stream_offset": 2,
                        "bundle_seq": 0, "ts_ns": 2, "opcode": 0x040A, "type": "drop_item_field",
                        "data": {"type": "drop_item_field", "ticket": "remove"},
                    },
                ]
                self.assertEqual(db.add_events(raw, events), 1)
                exported = db.export(root, "self-test")
                envelope = json.loads(exported.json_path.read_text(encoding="utf-8"))
                self.assertEqual(envelope["summary"]["kills_estimated_by_reward"], 1)
                self.assertIsNone(envelope["metadata"]["installation_id"])
                self.assertIsNone(envelope["metadata"]["license_lease"])
                self.assertNotIn("ticket", envelope["events"][0]["data"])
                self.assertNotIn("0x0101", [event["opcode"] for event in envelope["events"]])
                db.clear_exported()
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
                self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM captures").fetchone()[0], 0)
            finally:
                db.close()

    def test_capture_segments_are_ordered_by_write_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            capture = PktmonCapture(root, runner=lambda *_a, **_k: None)
            capture._prefix = root / "rfnext-test.etl"
            older = root / "rfnext-test10.etl"
            active = root / "rfnext-test2.etl"
            older.write_bytes(b"old")
            active.write_bytes(b"active")
            os.utime(older, ns=(1, 1))
            os.utime(active, ns=(2, 2))

            self.assertEqual(capture.segment_files(), (older, active))

    def test_minimal_pcapng_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shb = struct.pack("<IIIHHqI", 0x0A0D0D0A, 28, 0x1A2B3C4D, 1, 0, -1, 28)
            idb = struct.pack("<IIHHII", 1, 20, 1, 0, 65535, 20)
            packet = b"\0" * 60
            body = struct.pack("<IIIII", 0, 0, 1, len(packet), len(packet)) + packet
            epb_len = 12 + len(body)
            epb = struct.pack("<II", 6, epb_len) + body + struct.pack("<I", epb_len)
            source, target = root / "in.pcapng", root / "out.pcap"
            source.write_bytes(shb + idb + epb)
            _pcapng_to_pcap(source, target)
            self.assertEqual(target.read_bytes()[:4], b"\x4d\x3c\xb2\xa1")

    def test_sessions_characters_diagnostics_and_exp_percent_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.etl"
            second = root / "second.etl"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            db = CaptureStore(root / "state.sqlite")
            try:
                db.add_events(
                    first,
                    [
                        {
                            "flow": "private-flow-a",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "ts_ns": 1,
                            "opcode": 0x0400,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 101,
                                    "character_name": "Alice",
                                    "level": 66,
                                    "exp": 1_230_793_758,
                                }
                            },
                        },
                        {
                            "flow": "private-flow-a",
                            "stream_offset": 2,
                            "bundle_seq": 0,
                            "ts_ns": 2,
                            "opcode": 0x7777,
                            "type": "unparsed",
                            "data": {
                                "port": 12020,
                                "decoded_size": 40,
                                "confidence": "unparsed_no_payload",
                            },
                        },
                    ],
                    "session-a",
                )
                db.add_events(
                    second,
                    [
                        {
                            "flow": "private-flow-b",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "ts_ns": 3,
                            "opcode": 0x0400,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 202,
                                    "character_name": "Bob",
                                }
                            },
                        }
                    ],
                    "session-b",
                )
                self.assertEqual(
                    db.session_profiles("session-a"),
                    [{"uid": "101", "name": "Alice"}],
                )
                exported = db.export(
                    root,
                    "Profile-Alice-20260728-001",
                    session_id="session-a",
                    character_uid="101",
                    include_unassigned=True,
                    context={
                        "profile": "Profile",
                        "character_name": "Alice",
                        "installation_id": "install-1",
                        "license_lease": "lease-1",
                        "codex_marks": {"1001": [1, 3]},
                    },
                )
                envelope = json.loads(exported.json_path.read_text(encoding="utf-8"))
                self.assertEqual(len(envelope["events"]), 1)
                self.assertEqual(
                    envelope["events"][0]["data"]["fields"]["exp_percent"],
                    39.68,
                )
                header, row = exported.csv_path.read_text(
                    encoding="utf-8-sig"
                ).splitlines()[:2]
                self.assertIn("license_lease", header)
                self.assertIn("codex_marks", header)
                self.assertIn("Profile", row)
                self.assertIn("install-1", row)
                self.assertIn("lease-1", row)
                self.assertIn('""1001"":[1,3]', row)
                diagnostic = db.export_diagnostics(
                    root, "Profile-diagnostico-20260728-001", "session-a"
                )
                self.assertIsNotNone(diagnostic)
                raw = diagnostic.read_text(encoding="utf-8")
                self.assertNotIn("private-flow", raw)
                self.assertNotIn("Alice", raw)
                db.clear_exported("session-a")
                self.assertEqual(db.latest_session(), "session-b")
                self.assertEqual(db.session_stats("session-b")["recognized"], 1)
            finally:
                db.close()

    def test_client_ports_separate_events_and_only_world_info_binds_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first, second = root / "first.pcap", root / "second.pcap"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            routes = ((50001,), (50002,))
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    first,
                    [
                        {
                            "flow": "127.0.0.1:50001 -> 10.0.0.1:12020",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0305,
                            "type": "appear_player_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 999,
                                    "character_name": "Outro jogador",
                                }
                            },
                        },
                        {
                            "flow": "127.0.0.1:50002 -> 10.0.0.1:12020",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"gain_exp": 10}},
                        },
                    ],
                    "session",
                    client_ports=routes,
                )
                store.add_events(
                    second,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 101,
                                    "character_name": "Alice",
                                }
                            },
                        },
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50002",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 202,
                                    "character_name": "Bob",
                                }
                            },
                        },
                    ],
                    "session",
                    client_ports=routes,
                )
                self.assertEqual(
                    store.session_profiles("session"),
                    [
                        {
                            "uid": "101",
                            "name": "Alice",
                            "client_key": "client:a",
                        },
                        {
                            "uid": "202",
                            "name": "Bob",
                            "client_key": "client:b",
                        },
                    ],
                )
                uids = {
                    row[0]
                    for row in store.conn.execute(
                        "SELECT DISTINCT character_uid FROM events"
                    )
                }
                self.assertEqual(uids, {"101", "202"})
            finally:
                store.close()

    def test_confirmed_uid_history_survives_session_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "identity.pcap"
            source.write_bytes(b"identity")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                            "biosuit_item_index": 2075041,
                        }},
                    }],
                    "old-session",
                    client_ports=((50001,),),
                )
                self.assertEqual(
                    store.character_history()[0]["uid"],
                    "101",
                )
                store.clear_exported("old-session")
                history = store.character_history()
                self.assertEqual(
                    (
                        history[0]["uid"],
                        history[0]["name"],
                        history[0]["biosuit_item_index"],
                    ),
                    ("101", "Alice", 2075041),
                )
            finally:
                store.close()

    def test_confirmed_history_uses_only_own_entry_rover(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "entry.pcap"
            source.write_bytes(b"entry")
            store = CaptureStore(root / "state.sqlite3")
            try:
                flow = "10.0.0.1:12020 -> 127.0.0.1:50001"
                events = [
                    {
                        "flow": flow,
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "ts_ns": 1,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                            "biosuit_item_index": 2075041,
                        }},
                    },
                    {
                        "flow": flow, "stream_offset": 2, "bundle_seq": 1,
                        "ts_ns": 2, "opcode": 0x0202, "type": "unparsed",
                        "data": {},
                    },
                    {
                        "flow": flow, "stream_offset": 3, "bundle_seq": 2,
                        "ts_ns": 2, "opcode": 0x0323, "type": "unparsed",
                        "data": {},
                    },
                    {
                        "flow": flow,
                        "stream_offset": 4,
                        "bundle_seq": 3,
                        "ts_ns": 2,
                        "opcode": 0x0305,
                        "type": "appear_player_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                            "biosuit_item_index": 2075041,
                            "rover_item_index": 4000000,
                        }},
                    },
                    {
                        "flow": flow,
                        "stream_offset": 5,
                        "bundle_seq": 4,
                        "ts_ns": 3,
                        "opcode": 0x0305,
                        "type": "appear_player_prefix",
                        "data": {"fields": {
                            "character_uid": 999,
                            "character_name": "Nearby",
                            "rover_item_index": 4400011,
                        }},
                    },
                ]
                store.add_events(
                    source,
                    events,
                    "session",
                    client_ports=((50001,),),
                )
                history = store.character_history()[0]
                self.assertEqual(history["biosuit_item_index"], 2075041)
                self.assertEqual(history["rover_item_index"], 4000000)
                refreshed = root / "refreshed.pcap"
                refreshed.write_bytes(b"refreshed")
                store.add_events(
                    refreshed,
                    [
                        {
                            "flow": flow, "stream_offset": 1, "bundle_seq": 0,
                            "opcode": 0x0106, "type": "world_info_prefix",
                            "data": {"fields": {
                                "character_uid": 101,
                                "character_name": "Alice",
                                "biosuit_item_index": 2085031,
                            }},
                        },
                        {
                            "flow": flow, "stream_offset": 2, "bundle_seq": 1,
                            "opcode": 0x0305, "type": "appear_player_prefix",
                            "data": {"fields": {
                                "character_uid": 101,
                                "character_name": "Alice",
                                "rover_item_index": 4400008,
                            }},
                        },
                    ],
                    "new-session",
                    client_ports=((50001,),),
                )
                history = store.character_history()[0]
                self.assertEqual(history["biosuit_item_index"], 2085031)
                self.assertEqual(history["rover_item_index"], 4400008)
            finally:
                store.close()

    def test_historical_uid_routes_client_until_canonical_identity_arrives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity = root / "identity.pcap"
            exp = root / "exp.pcap"
            canonical = root / "canonical.pcap"
            identity.write_bytes(b"identity")
            exp.write_bytes(b"exp")
            canonical.write_bytes(b"canonical")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    identity,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                        }},
                    }],
                    "old-session",
                    client_ports=((50001,),),
                )
                store.select_client_uid("new-session", "client:a", "101")
                with self.assertRaisesRegex(ValueError, "outro cliente"):
                    store.select_client_uid("new-session", "client:b", "101")
                store.add_events(
                    exp,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0307,
                        "type": "update_exp",
                        "data": {"fields": {"gain_exp": 10}},
                    }],
                    "new-session",
                    client_ports=((50001,),),
                )
                self.assertEqual(
                    store.conn.execute(
                        "SELECT character_uid FROM events WHERE session_id='new-session'"
                    ).fetchone()[0],
                    "101",
                )
                store.add_events(
                    canonical,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 202,
                            "character_name": "Bob",
                        }},
                    }],
                    "new-session",
                    client_ports=((50001,),),
                )
                self.assertEqual(
                    {
                        row[0] for row in store.conn.execute(
                            "SELECT DISTINCT character_uid FROM events "
                            "WHERE session_id='new-session'"
                        )
                    },
                    {"202"},
                )
                self.assertEqual(
                    store.client_bindings("new-session")[0]["source"],
                    "canonical",
                )
            finally:
                store.close()

    def test_historical_levels_realign_swapped_physical_client_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history_source = root / "history.pcap"
            initial_source = root / "initial.pcap"
            evidence_source = root / "evidence.pcap"
            later_source = root / "later.pcap"
            for source in (
                history_source, initial_source, evidence_source, later_source
            ):
                source.write_bytes(source.stem.encode("ascii"))
            routes = ((50001,), (50002,))
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    history_source,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {"fields": {
                                "character_uid": 101,
                                "character_name": "Duffita",
                                "level": 69,
                            }},
                        },
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50002",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {"fields": {
                                "character_uid": 202,
                                "character_name": "Xadão",
                                "level": 61,
                            }},
                        },
                    ],
                    "old-session",
                    client_ports=routes,
                )
                store.select_client_uid("new-session", "client:a", "101")
                store.select_client_uid("new-session", "client:b", "202")

                store.add_events(
                    initial_source,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"gain_exp": 72_204}},
                        },
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50002",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"gain_exp": 414_810}},
                        },
                    ],
                    "new-session",
                    client_ports=routes,
                )
                store.add_events(
                    evidence_source,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"level": 61, "gain_exp": 1}},
                        },
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50002",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"level": 69, "gain_exp": 1}},
                        },
                    ],
                    "new-session",
                    client_ports=routes,
                )
                store.select_client_uid("new-session", "client:a", "101")
                store.select_client_uid("new-session", "client:b", "202")
                store.add_events(
                    later_source,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50001",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x2407,
                            "type": "realm_contribution_update",
                            "data": {"fields": {"contribution_total": 17_710}},
                        },
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50002",
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x2407,
                            "type": "realm_contribution_update",
                            "data": {"fields": {"contribution_total": 129_206}},
                        },
                    ],
                    "new-session",
                    client_ports=routes,
                )

                owners = [
                    tuple(row)
                    for row in store.conn.execute(
                        """SELECT flow,character_uid,type FROM events
                           WHERE session_id='new-session' ORDER BY id"""
                    )
                ]
                self.assertTrue(all(
                    uid == ("202" if ":50001" in flow else "101")
                    for flow, uid, _kind in owners
                ))
                self.assertEqual(
                    store.conn.execute(
                        """SELECT physical_client_key,logical_client_key
                           FROM client_route_slots WHERE session_id='new-session'
                           ORDER BY physical_client_key"""
                    ).fetchall(),
                    [("client:a", "client:b"), ("client:b", "client:a")],
                )
                self.assertEqual(
                    {
                        item["uid"]: item["level"]
                        for item in store.character_history()
                    },
                    {"101": 69, "202": 61},
                )
            finally:
                store.close()

    def test_marked_entry_bundle_binds_appear_player_to_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "entry.pcap"
            source.write_bytes(b"entry")
            store = CaptureStore(root / "state.sqlite3")
            try:
                timestamp = 1_000_000_000
                store.add_capture_window(
                    "session", "character", timestamp - 1, timestamp + 1
                )
                flow = "10.0.0.1:12020 -> 127.0.0.1:63175"
                store.add_events(
                    source,
                    [
                        {
                            "flow": flow,
                            "stream_offset": index,
                            "bundle_seq": index,
                            "ts_ns": timestamp,
                            "opcode": opcode,
                            "type": event_type,
                            "data": data,
                        }
                        for index, (opcode, event_type, data) in enumerate(
                            (
                                (0x0202, "unparsed", {}),
                                (0x0323, "unparsed", {}),
                                (
                                    0x0305,
                                    "appear_player_prefix",
                                    {
                                        "fields": {
                                            "character_uid": 101,
                                            "character_name": "Alice",
                                            "level": 67,
                                        }
                                    },
                                ),
                            )
                        )
                    ],
                    "session",
                    client_ports=((63175,), (63188,)),
                )
                self.assertEqual(
                    store.session_profiles("session"),
                    [
                        {
                            "uid": "101",
                            "name": "Alice",
                            "client_key": "client:a",
                        }
                    ],
                )
            finally:
                store.close()

    def test_single_client_canonical_identity_survives_unknown_rotated_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "rotated.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    source,
                    [
                        {
                            "flow": (
                                "10.0.0.1:12020 -> "
                                "192.168.1.1:45843"
                            ),
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 101,
                                    "character_name": "Alice",
                                }
                            },
                        }
                    ],
                    "session",
                    client_ports=((10874, 10910, 12352),),
                )
                self.assertEqual(
                    store.session_profiles("session"),
                    [
                        {
                            "uid": "101",
                            "name": "Alice",
                            "client_key": "client:a",
                        }
                    ],
                )
                self.assertEqual(
                    store.conn.execute(
                        """SELECT character_uid,binding_source
                           FROM client_bindings WHERE session_id=?""",
                        ("session",),
                    ).fetchone(),
                    ("101", "canonical"),
                )
            finally:
                store.close()

    def test_two_unrouted_canonical_identities_get_distinct_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "two-clients.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    source,
                    [
                        {
                            "flow": (
                                f"10.0.0.1:12020 -> 192.168.1.1:{port}"
                            ),
                            "stream_offset": index,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": uid,
                                    "character_name": name,
                                }
                            },
                        }
                        for index, (port, uid, name) in enumerate(
                            (
                                (48759, 101, "Alice"),
                                (26864, 202, "Bob"),
                            ),
                            1,
                        )
                    ],
                    "session",
                    client_ports=((12650, 25431),),
                )
                self.assertEqual(
                    store.session_profiles("session"),
                    [
                        {
                            "uid": "101",
                            "name": "Alice",
                            "client_key": "client:a",
                        },
                        {
                            "uid": "202",
                            "name": "Bob",
                            "client_key": "client:b",
                        },
                    ],
                )
            finally:
                store.close()

    def test_ambiguous_marked_entry_does_not_bind_any_appearance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "ambiguous.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                timestamp = 1_000_000_000
                flow = "10.0.0.1:12020 -> 127.0.0.1:63175"
                store.add_capture_window(
                    "session", "character", timestamp - 1, timestamp + 1
                )
                events = [
                    {
                        "flow": flow,
                        "stream_offset": index,
                        "bundle_seq": index,
                        "ts_ns": timestamp,
                        "opcode": opcode,
                        "type": event_type,
                        "data": data,
                    }
                    for index, (opcode, event_type, data) in enumerate(
                        (
                            (0x0202, "unparsed", {}),
                            (0x0323, "unparsed", {}),
                            (
                                0x0305,
                                "appear_player_prefix",
                                {
                                    "fields": {
                                        "character_uid": 101,
                                        "character_name": "Alice",
                                    }
                                },
                            ),
                            (
                                0x0305,
                                "appear_player_prefix",
                                {
                                    "fields": {
                                        "character_uid": 202,
                                        "character_name": "Bob",
                                    }
                                },
                            ),
                        )
                    )
                ]
                store.add_events(
                    source,
                    events,
                    "session",
                    client_ports=((63175,),),
                )
                count = store.conn.execute(
                    "SELECT COUNT(*) FROM client_bindings"
                ).fetchone()[0]
                self.assertEqual(count, 0)
            finally:
                store.close()

    def test_heuristic_identity_never_overwrites_canonical_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            canonical = root / "canonical.pcap"
            heuristic = root / "heuristic.pcap"
            canonical.write_bytes(b"canonical")
            heuristic.write_bytes(b"heuristic")
            store = CaptureStore(root / "state.sqlite3")
            try:
                flow = "10.0.0.1:12020 -> 127.0.0.1:63175"
                store.add_events(
                    canonical,
                    [
                        {
                            "flow": flow,
                            "stream_offset": 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_uid": 101,
                                    "character_name": "Alice",
                                }
                            },
                        }
                    ],
                    "session",
                    client_ports=((63175,),),
                )
                timestamp = 1_000_000_000
                store.add_capture_window(
                    "session", "character", timestamp - 1, timestamp + 1
                )
                store.add_events(
                    heuristic,
                    [
                        {
                            "flow": flow,
                            "stream_offset": index,
                            "bundle_seq": index,
                            "ts_ns": timestamp,
                            "opcode": opcode,
                            "type": event_type,
                            "data": data,
                        }
                        for index, (opcode, event_type, data) in enumerate(
                            (
                                (0x0202, "unparsed", {}),
                                (0x0323, "unparsed", {}),
                                (
                                    0x0305,
                                    "appear_player_prefix",
                                    {
                                        "fields": {
                                            "character_uid": 202,
                                            "character_name": "Bob",
                                        }
                                    },
                                ),
                            )
                        )
                    ],
                    "session",
                    client_ports=((63175,),),
                )
                self.assertEqual(
                    store.conn.execute(
                        """SELECT character_uid,character_name,binding_source
                           FROM client_bindings WHERE session_id=?""",
                        ("session",),
                    ).fetchone(),
                    ("101", "Alice", "canonical"),
                )
            finally:
                store.close()

    def test_final_etl_keeps_events_from_old_and_current_client_ports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "rotating-ports.etl"
            raw.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                events = [
                    {
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:60470",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0307,
                        "type": "update_exp",
                        "data": {
                            "fields": {
                                "level": 61,
                                "exp": 100,
                                "gain_exp": 10,
                            }
                        },
                    },
                    {
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:60470",
                        "stream_offset": 2,
                        "bundle_seq": 0,
                        "opcode": 0x040A,
                        "type": "drop_item_field",
                        "data": {"results": [{"item_index": 1, "count": 2}]},
                    },
                    {
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:63175",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0400,
                        "type": "collection_snapshot_chunk",
                        "data": {"records": []},
                    },
                    {
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:63188",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0400,
                        "type": "collection_snapshot_chunk",
                        "data": {"records": []},
                    },
                ]
                store.add_events(
                    raw,
                    events,
                    "session",
                    client_ports=((60470, 63175), (63188,)),
                )
                owners = store.conn.execute(
                    """SELECT character_uid,type FROM events
                       ORDER BY stream_offset,type"""
                ).fetchall()
                self.assertIn(("client:a", "update_exp"), owners)
                self.assertIn(("client:a", "drop_item_field"), owners)
                self.assertIn(("client:b", "collection_snapshot_chunk"), owners)
            finally:
                store.close()

    def test_new_client_route_repairs_earlier_unassigned_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            identity, farm, refresh = (
                root / "identity.pcap",
                root / "farm.pcap",
                root / "refresh.pcap",
            )
            identity.write_bytes(b"identity")
            farm.write_bytes(b"farm")
            refresh.write_bytes(b"refresh")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    identity,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                        }},
                    }],
                    "session",
                    client_ports=((50000,),),
                )
                store.add_events(
                    farm,
                    [{
                        "flow": "10.0.0.1:12010 -> 127.0.0.1:50001",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0307,
                        "type": "update_exp",
                        "data": {"fields": {"gain_exp": 10}},
                    }],
                    "session",
                    client_ports=((50000,),),
                )
                self.assertEqual(store.session_stats("session")["unassigned"], 1)
                store.add_events(
                    refresh,
                    [{
                        "flow": "10.0.0.1:12010 -> 127.0.0.1:50001",
                        "stream_offset": 2,
                        "bundle_seq": 0,
                        "opcode": 0x0307,
                        "type": "update_exp",
                        "data": {"fields": {"gain_exp": 10}},
                    }],
                    "session",
                    client_ports=((50000, 50001),),
                )
                self.assertEqual(store.session_stats("session")["unassigned"], 0)
            finally:
                store.close()

    def test_collection_type_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "collections.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": index,
                        "bundle_seq": 0,
                        "opcode": 0x0419,
                        "type": "collection_snapshot_chunk",
                        "data": {"collection_type": kind, "records": []},
                    } for index, kind in enumerate((1, 1, 2), 1)],
                    "session",
                )
                self.assertEqual(store.collection_type_counts("session"), {1: 2, 2: 1})
            finally:
                store.close()

    def test_two_rotated_flows_keep_exp_contribution_and_rewards_per_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            history = root / "history.pcap"
            rotated = root / "rotated.pcap"
            history.write_bytes(b"history")
            rotated.write_bytes(b"rotated")
            store = CaptureStore(root / "state.sqlite3")
            try:
                store.add_events(
                    history,
                    [
                        {
                            "flow": f"10.0.0.1:12020 -> 127.0.0.1:{port}",
                            "stream_offset": index,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {"fields": {
                                "character_uid": uid,
                                "character_name": name,
                            }},
                        }
                        for index, (port, uid, name) in enumerate(
                            ((50001, 101, "Alice"), (50002, 202, "Bob")), 1
                        )
                    ],
                    "old-session",
                    client_ports=((50001,), (50002,)),
                )
                store.select_client_uid("session", "client:a", "101")
                store.select_client_uid("session", "client:b", "202")
                flows = {
                    "101": "10.0.0.1:12020 -> 127.0.0.1:35108",
                    "202": "10.0.0.1:12020 -> 127.0.0.1:25162",
                }
                events = []
                for uid, name in (("101", "Alice"), ("202", "Bob")):
                    flow = flows[uid]
                    events.extend((
                        {
                            "flow": flow,
                            "stream_offset": len(events) + 1,
                            "bundle_seq": 0,
                            "opcode": 0x0106,
                            "type": "world_info_prefix",
                            "data": {"fields": {
                                "character_uid": int(uid),
                                "character_name": name,
                            }},
                        },
                        {
                            "flow": "127.0.0.1:" + flow.rsplit(":", 1)[1]
                            + " -> 10.0.0.1:12020",
                            "stream_offset": len(events) + 2,
                            "bundle_seq": 0,
                            "opcode": 0x0307,
                            "type": "update_exp",
                            "data": {"fields": {"gain_exp": int(uid)}},
                        },
                        {
                            "flow": flow,
                            "stream_offset": len(events) + 3,
                            "bundle_seq": 0,
                            "opcode": 0x2407,
                            "type": "realm_contribution_update",
                            "data": {"fields": {"contribution_total": int(uid)}},
                        },
                        {
                            "flow": flow,
                            "stream_offset": len(events) + 4,
                            "bundle_seq": 0,
                            "opcode": 0x040A,
                            "type": "drop_item_field",
                            "data": {"results": [{
                                "item_index": 900,
                                "count": 10,
                                "action_code": 1006,
                            }]},
                        },
                    ))
                store.add_events(
                    rotated,
                    events,
                    "session",
                    client_ports=((47852,), (52743,)),
                )

                owners = store.conn.execute(
                    """SELECT character_uid,type FROM events
                       WHERE session_id='session' ORDER BY id"""
                ).fetchall()
                self.assertEqual(
                    owners,
                    [
                        (uid, kind)
                        for uid in ("101", "202")
                        for kind in (
                            "world_info_prefix",
                            "update_exp",
                            "realm_contribution_update",
                            "drop_item_field",
                        )
                    ],
                )
                for uid in ("101", "202"):
                    envelope = store._envelope(
                        f"capture-{uid}", "session", character_uid=uid
                    )
                    self.assertEqual(
                        envelope["summary"]["kills_estimated_by_reward"], 1
                    )
                    self.assertEqual(
                        {event["type"] for event in envelope["events"]},
                        {
                            "world_info_prefix",
                            "update_exp",
                            "realm_contribution_update",
                            "drop_item_field",
                        },
                    )
            finally:
                store.close()

    def test_upgrade_repairs_only_unassigned_events_on_confirmed_same_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "state.sqlite3"
            store = CaptureStore(database)
            try:
                with store.conn:
                    store.conn.execute(
                        "DELETE FROM store_state WHERE key='canonical_flow_repair_v1'"
                    )
                    rows = (
                        (
                            "source", "10.0.0.1:12020 -> 127.0.0.1:35108",
                            1, 0, 1, 0x0106, "world_info_prefix", "101",
                            '{"fields":{"character_uid":101}}', "session",
                        ),
                        (
                            "source", "127.0.0.1:35108 -> 10.0.0.1:12020",
                            2, 0, 2, 0x0307, "update_exp", None,
                            '{"fields":{"gain_exp":10}}', "session",
                        ),
                        (
                            "source", "127.0.0.1:49999 -> 10.0.0.1:12020",
                            3, 0, 3, 0x0307, "update_exp", None,
                            '{"fields":{"gain_exp":20}}', "session",
                        ),
                    )
                    store.conn.executemany(
                        """INSERT INTO events
                           (source,flow,stream_offset,bundle_seq,ts_ns,opcode,
                            type,character_uid,data_json,session_id)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        rows,
                    )
            finally:
                store.close()

            reopened = CaptureStore(database)
            try:
                self.assertEqual(
                    reopened.conn.execute(
                        """SELECT character_uid FROM events
                           WHERE type='update_exp' ORDER BY id"""
                    ).fetchall(),
                    [("101",), (None,)],
                )
                self.assertEqual(
                    reopened.conn.execute(
                        """SELECT value FROM store_state
                           WHERE key='canonical_flow_repair_v1'"""
                    ).fetchone()[0],
                    1,
                )
            finally:
                reopened.close()

    def test_live_ingest_ignores_flow_outside_detected_pc_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "three-clients.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite3")
            try:
                events = [
                    {
                        "flow": f"10.0.0.1:12020 -> 127.0.0.1:{port}",
                        "stream_offset": index,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": uid,
                            "character_name": name,
                        }},
                    }
                    for index, (port, uid, name) in enumerate((
                        (50001, 101, "Alice"),
                        (50002, 202, "Bob"),
                        (57003, 303, "BlueStacks"),
                    ), 1)
                ]

                added = store.add_events(
                    source,
                    events,
                    "session",
                    client_ports=((50001,), (50002,)),
                    restrict_to_clients=True,
                )

                self.assertEqual(added, 2)
                self.assertEqual(
                    store.session_profiles("session"),
                    [
                        {"uid": "101", "name": "Alice", "client_key": "client:a"},
                        {"uid": "202", "name": "Bob", "client_key": "client:b"},
                    ],
                )
                self.assertEqual(
                    store.conn.execute(
                        "SELECT COUNT(*) FROM events WHERE flow LIKE '%:57003'"
                    ).fetchone()[0],
                    0,
                )
            finally:
                store.close()

    def test_latest_collection_snapshot_survives_a_new_capture_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_source = root / "old.pcap"
            current_source = root / "current.pcap"
            old_source.write_bytes(b"old")
            current_source.write_bytes(b"current")
            store = CaptureStore(root / "state.sqlite3")
            try:
                with store.conn:
                    store.conn.executemany(
                        """INSERT INTO client_bindings
                           (session_id,client_key,character_uid,character_name,binding_source)
                           VALUES(?,?,?,?,?)""",
                        [
                            ("old", "client:a", "101", "Alice", "manual"),
                            ("current", "client:a", "101", "Alice", "manual"),
                        ],
                    )
                store.add_events(
                    old_source,
                    [
                        {
                            "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                            "stream_offset": index,
                            "bundle_seq": 0,
                            "ts_ns": 100 + index,
                            "opcode": 0x0419,
                            "type": "collection_snapshot_chunk",
                            "data": {
                                "collection_type": kind,
                                "is_end": is_end,
                                "records": records,
                            },
                        }
                        for index, kind, is_end, records in (
                            (1, 1, False, [{"collection_index": 1001, "collection_type": 1, "completed_slots": [0]}]),
                            (2, 1, True, []),
                            (3, 2, True, [{"collection_index": 2001, "collection_type": 2, "completed_slots": [1]}]),
                        )
                    ],
                    "old",
                    client_ports=((50000,),),
                )
                store.add_events(
                    current_source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "ts_ns": 200,
                        "opcode": 0x0418,
                        "type": "collection_add_response",
                        "data": {
                            "collection_type": 1,
                            "collection_index": 1001,
                            "slot_index": 1,
                            "result_code": 0,
                            "item_complete": True,
                        },
                    }],
                    "current",
                    client_ports=((50000,),),
                )

                envelope = store.latest_collection_envelope("101")

                self.assertEqual(envelope["collection_type_counts"], {1: 3, 2: 1})
                self.assertEqual(
                    [event["type"] for event in envelope["events"]],
                    [
                        "collection_snapshot_chunk",
                        "collection_snapshot_chunk",
                        "collection_snapshot_chunk",
                        "collection_add_response",
                    ],
                )
            finally:
                store.close()

    def test_invalid_ipv4_total_length_does_not_abort_following_packet(self):
        ethernet = b"\0" * 12 + b"\x08\x00"

        def ipv4_tcp(total_length, payload=b""):
            ip = bytearray(20)
            ip[0] = 0x45
            struct.pack_into("!H", ip, 2, total_length)
            ip[9] = 6
            ip[12:20] = b"\x0a\x00\x00\x01\x0a\x00\x00\x02"
            tcp = struct.pack("!HHIIH", 50000, 12020, 1, 0, 0x5000) + b"\0" * 6
            return ethernet + bytes(ip) + tcp + payload

        malformed = ipv4_tcp(0)
        valid = ipv4_tcp(20 + 20 + 3, b"abc")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "offload.pcap"
            header = struct.pack("<IHHIIII", 0xA1B23C4D, 2, 4, 0, 0, 65535, 1)
            records = b"".join(
                struct.pack("<IIII", 1, index, len(packet), len(packet)) + packet
                for index, packet in enumerate((malformed, valid))
            )
            source.write_bytes(header + records)
            streams = pcap_tcp_streams(source, 12020)
            self.assertEqual([stream for _, stream, _ in streams], [b"abc"])

    def test_pktmon_packet_count_uses_json_counters(self):
        class Result:
            returncode = 0
            stderr = ""
            stdout = json.dumps(
                {
                    "components": [
                        {"edges": [{"packets": 7}, {"packets": 3}]},
                        {"packet_count": 2},
                    ]
                }
            )

        capture = PktmonCapture(Path("."), runner=lambda *_a, **_k: Result())
        self.assertEqual(capture.packet_count(), 12)

    def test_decoder_resync_requires_three_consecutive_frames(self):
        class Decoder:
            class DecodeError(Exception):
                pass

            @staticmethod
            def decode_stream(_stream):
                raise Decoder.DecodeError("gap")

            @staticmethod
            def frame_length_from_wire(header):
                return int.from_bytes(header[1:3], "little")

            @staticmethod
            def decode_frame(frame):
                if len(frame) != 6:
                    raise Decoder.DecodeError("invalid")
                return frame, {"wire_length": len(frame), "opcode": 1}

        frame = b"\x00\x06\x00\x00\x01\x00"
        recovered = _decode_stream_resync(
            Decoder, b"\xff\xff\xff\xff" + frame * 3
        )
        self.assertEqual(
            [info["stream_offset"] for _, info in recovered],
            [4, 10, 16],
        )

    def test_ingest_rebuilds_events_when_decoder_identity_changes(self):
        event_old = {
            "flow": "flow",
            "stream_offset": 1,
            "bundle_seq": 0,
            "ts_ns": 1,
            "opcode": 0x7777,
            "type": "unparsed",
            "data": {"confidence": "old"},
        }
        event_new = {
            **event_old,
            "type": "decoded",
            "data": {"confidence": "new"},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "capture.pcap"
            raw.write_bytes(b"capture")
            store = CaptureStore(root / "state.sqlite")
            try:
                with patch(
                    "core.store.decoder_identity", return_value="decoder-a"
                ), patch(
                    "core.store.decoded_events", return_value=iter([event_old])
                ):
                    self.assertEqual(store.ingest(raw, session_id="s"), 1)
                    self.assertEqual(store.ingest(raw, session_id="s"), 0)
                with patch(
                    "core.store.decoder_identity", return_value="decoder-b"
                ), patch(
                    "core.store.decoded_events", return_value=iter([event_new])
                ):
                    self.assertEqual(store.ingest(raw, session_id="s"), 1)
                rows = store.conn.execute(
                    "SELECT type,data_json FROM events WHERE source=?",
                    (str(raw),),
                ).fetchall()
                self.assertEqual(
                    rows,
                    [("decoded", '{"confidence": "new"}')],
                )
            finally:
                store.close()

    def test_append_only_ingest_keeps_tcp_context_and_adds_only_new_events(self):
        event_one = {
            "flow": "10.0.0.1:12020 -> 10.0.0.2:50000",
            "stream_offset": 0,
            "bundle_seq": 0,
            "ts_ns": 1,
            "opcode": 0x0106,
            "type": "world_info_prefix",
            "data": {"fields": {"character_uid": 1, "character_name": "A"}},
        }
        event_two = {
            **event_one,
            "stream_offset": 10,
            "opcode": 0x0307,
            "type": "update_exp",
            "data": {"level": 67, "exp": 123},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "live.pcap"
            raw.write_bytes(b"partial")
            store = CaptureStore(root / "state.sqlite")
            try:
                with patch(
                    "core.store.decoder_identity", return_value="decoder"
                ), patch(
                    "core.store.decoded_events", return_value=iter(())
                ):
                    self.assertEqual(
                        store.ingest(raw, session_id="s", append_only=True),
                        0,
                    )
                with raw.open("ab") as output:
                    output.write(b"-frame-one")
                with patch(
                    "core.store.decoder_identity", return_value="decoder"
                ), patch(
                    "core.store.decoded_events",
                    return_value=iter((event_one,)),
                ):
                    self.assertEqual(
                        store.ingest(raw, session_id="s", append_only=True),
                        1,
                    )
                with raw.open("ab") as output:
                    output.write(b"-frame-two")
                with patch(
                    "core.store.decoder_identity", return_value="decoder"
                ), patch(
                    "core.store.decoded_events",
                    return_value=iter((event_one, event_two)),
                ):
                    self.assertEqual(
                        store.ingest(raw, session_id="s", append_only=True),
                        1,
                    )
                self.assertEqual(
                    store.conn.execute(
                        "SELECT COUNT(*) FROM events WHERE source=?",
                        (str(raw),),
                    ).fetchone()[0],
                    2,
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
