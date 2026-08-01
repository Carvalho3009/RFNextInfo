import ctypes
import json
import os
import sqlite3
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from core.capture import PktmonCapture, _pktmon_running
from core.pktmon_realtime import (
    RealtimeCapture,
    _DataSourceList,
    _data_source_pointers,
    _matches_tcp_port,
    split_pcap_by_ports,
)
from core.connections import (
    clients_for_executable,
    connected_processes,
    ports_for_executable,
)
from core.ingest import _decode_stream_resync, _pcapng_to_pcap, _safe_parse
from core.rfnext_frame_decode import pcap_tcp_streams
from core.store import CaptureStore


class CoreTest(unittest.TestCase):
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
            self.assertEqual(store.subsessions("session")[0]["name"], "Depois")
            self.assertEqual(store.delete_subsessions(("sub-1",)), 1)
            self.assertEqual(store.subsessions("session"), [])
            store.close()

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
                    "name": "Farm da manhã",
                    "location": "Abismo > Câmara 3",
                    "map_name": "Abismo",
                    "spot_name": "Câmara 3",
                    "mobs": ["Bellato", "Accretia"],
                    "mob_levels": {"Accretia": "60-67", "Bellato": 65},
                    "duration_minutes": 0,
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
        self.assertEqual((local_ports, remote_ports, clients), ((50100,), (12020,), 1))
        self.assertEqual(routes[0]["local_ports"], (50100,))

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
