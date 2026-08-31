import tempfile
import unittest
from pathlib import Path

from app.ui_qt.data import (
    _normalized_flow_key,
    ReadOnlySnapshotReader,
    load_license_status,
    route_live_drop_events,
    route_live_loot_announcements,
)
from core.store import CaptureStore


class FlowRoutingTest(unittest.TestCase):
    def test_exitlag_flow_identity_is_direction_independent(self):
        incoming = {
            "flow": "127.0.0.1:9001 -> 127.0.0.1:61001"
        }
        outgoing = {
            "flow": "127.0.0.1:61001 -> 127.0.0.1:9001"
        }
        self.assertEqual(
            _normalized_flow_key(incoming), _normalized_flow_key(outgoing)
        )


class _AllowedLicense:
    @staticmethod
    def require(_capability):
        return {"active": True}


class QtReadOnlyDataTest(unittest.TestCase):
    def test_latest_snapshot_isolates_three_sequential_capture_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            store = CaptureStore(database)
            try:
                for index, session_id in enumerate(("session-1", "session-2", "session-3")):
                    source = root / f"{session_id}.pcap"
                    source.write_bytes(session_id.encode("ascii"))
                    port = 50_000 + index
                    character_uid = 101 + index
                    events = [{
                        "flow": f"10.0.0.1:12020 -> 127.0.0.1:{port}",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "ts_ns": 1 + index,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": character_uid,
                            "character_name": f"Personagem {index + 1}",
                        }},
                    }]
                    if index < 2:
                        events.append({
                            "flow": f"10.0.0.1:12020 -> 127.0.0.1:{port}",
                            "stream_offset": 2,
                            "bundle_seq": 0,
                            "ts_ns": 2 + index,
                            "opcode": 0x040A,
                            "type": "drop_item_field",
                            "data": {"ret": 0, "results": [{
                                "ret": 0,
                                "item_index": 270_000 + index,
                                "count": index + 1,
                            }]},
                        })
                    store.add_events(
                        source, events, session_id, client_ports=((port,),)
                    )
                # O relógio do Windows pode atribuir o mesmo instante a
                # importações consecutivas. A última gravação ainda deve
                # representar a sessão corrente.
                with store.conn:
                    store.conn.execute(
                        "UPDATE captures SET imported_at=?",
                        ("2026-01-01T00:00:00+00:00",),
                    )
            finally:
                store.close()

            snapshot = ReadOnlySnapshotReader(
                database, _AllowedLicense()
            ).load()
            reopened = CaptureStore(database, readonly=True)
            try:
                old_drops = reopened.recent_drop_events("session-1")
                middle_drops = reopened.recent_drop_events("session-2")
            finally:
                reopened.close()

        self.assertEqual(snapshot["session_id"], "session-3")
        self.assertEqual(
            [(row["uid"], row["name"]) for row in snapshot["profiles"]],
            [("103", "Personagem 3")],
        )
        self.assertEqual(snapshot["drop_events"], [])
        self.assertEqual(old_drops[0]["data"]["results"][0]["item_index"], 270_000)
        self.assertEqual(middle_drops[0]["data"]["results"][0]["item_index"], 270_001)

    def test_live_drop_routing_assigns_client_without_exposing_flow(self):
        routed = route_live_drop_events(
            [{
                "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                "ts_ns": 1,
                "stream_offset": 2,
                "bundle_seq": 0,
                "type": "drop_item_field",
                "data": {"ret": 0, "results": []},
            }],
            ((50000,),),
            {"client:a": "Alice"},
        )

        self.assertEqual(len(routed), 1)
        self.assertEqual(routed[0]["client_key"], "client:a")
        self.assertEqual(routed[0]["character_name"], "Alice")
        self.assertNotIn("flow", routed[0])

    def test_live_chat_loot_routing_assigns_client_without_exposing_flow(self):
        routed = route_live_loot_announcements(
            [{
                "flow": "127.0.0.1:12020 -> 127.0.0.1:61001",
                "ts_ns": 1,
                "type": "loot_announcement",
                "data": {"announcements": [{
                    "player_name": "Rival", "item_index": 7, "count": 1,
                }]},
            }],
            ((61001,),),
        )

        self.assertEqual(routed[0]["client_key"], "client:a")
        self.assertNotIn("flow", routed[0])

    def test_missing_state_is_empty_and_never_exposes_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = ReadOnlySnapshotReader(
                root / "missing.sqlite3", _AllowedLicense()
            ).load()
            license_status = load_license_status(root / "local", root / "machine")

        self.assertIsNone(snapshot["session_id"])
        self.assertEqual(snapshot["characters"], [])
        self.assertEqual(snapshot["exp_rank"], {})
        self.assertEqual(snapshot["drop_events"], [])
        self.assertFalse(license_status["active"])
        self.assertNotIn("lease", license_status)
        self.assertNotIn("public_key", license_status)

    def test_snapshot_exposes_recent_drop_without_character_uid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "capture.pcap"
            source.write_bytes(b"capture")
            store = CaptureStore(root / "capture.sqlite3")
            try:
                store.add_events(source, [{
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 1,
                    "bundle_seq": 0,
                    "ts_ns": 1,
                    "opcode": 0x0106,
                    "type": "world_info_prefix",
                    "data": {"fields": {
                        "character_uid": 101,
                        "character_name": "Alice",
                    }},
                }, {
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 2,
                    "bundle_seq": 0,
                    "ts_ns": 2,
                    "opcode": 0x040A,
                    "type": "drop_item_field",
                    "data": {"ret": 0, "results": [{
                        "ret": 0, "item_index": 270062, "count": 1,
                    }]},
                }, {
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 3,
                    "bundle_seq": 0,
                    "ts_ns": 3,
                    "opcode": 0x0E09,
                    "type": "loot_announcement",
                    "data": {"announcements": [{
                        "player_name": "Bob",
                        "item_index": 1000444,
                        "count": 1,
                    }]},
                }, {
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 4,
                    "bundle_seq": 0,
                    "ts_ns": 200_000_000_002,
                    "opcode": 0x0307,
                    "type": "gain_exp",
                    "data": {"exp": 1},
                }], "session", client_ports=((50000,),))
            finally:
                store.close()

            snapshot = ReadOnlySnapshotReader(
                root / "capture.sqlite3", _AllowedLicense()
            ).load()

        self.assertEqual(len(snapshot["drop_events"]), 1)
        self.assertEqual(snapshot["drop_events"][0]["client_key"], "client:a")
        self.assertEqual(snapshot["drop_events"][0]["character_name"], "Alice")
        self.assertNotIn("character_uid", snapshot["drop_events"][0])
        self.assertEqual(len(snapshot["loot_announcements"]), 1)
        self.assertEqual(snapshot["loot_announcements"][0]["client_key"], "client:a")
        self.assertEqual(
            snapshot["loot_announcements"][0]["data"]["announcements"][0]["player_name"],
            "Bob",
        )
        self.assertNotIn("character_uid", snapshot["loot_announcements"][0])


if __name__ == "__main__":
    unittest.main()
