import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.capture import PktmonCapture, _pktmon_running
from core.connections import connected_processes, ports_for_executable
from core.ingest import _pcapng_to_pcap, _safe_parse
from core.rfnext_frame_decode import pcap_tcp_streams
from core.store import CaptureStore


class CoreTest(unittest.TestCase):
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
            ports, clients = ports_for_executable(paths[10])
        self.assertEqual(len(processes), 1)
        self.assertEqual(ports, (50100, 50101, 50200))
        self.assertEqual(clients, 2)
        self.assertEqual(ports_for_executable(paths[12]), ((), 0))

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
            ["50100", "50200", "50100", "50200", "50300"],
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
            self.assertEqual(capture.ports, (12000, 12020, 12040))
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
                                    "exp": 2_542_031_484,
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
                    context={"profile": "Profile", "character_name": "Alice"},
                )
                envelope = json.loads(exported.json_path.read_text(encoding="utf-8"))
                self.assertEqual(len(envelope["events"]), 1)
                self.assertAlmostEqual(
                    envelope["events"][0]["data"]["fields"]["exp_percent"],
                    12.57,
                    places=2,
                )
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


if __name__ == "__main__":
    unittest.main()
