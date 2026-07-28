import json
import struct
import tempfile
import unittest
from pathlib import Path

from core.capture import PktmonCapture, _pktmon_running
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
