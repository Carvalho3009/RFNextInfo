import json
import struct
import tempfile
import unittest
from pathlib import Path

from core.capture import PktmonCapture, _pktmon_running
from core.ingest import _pcapng_to_pcap
from core.store import CaptureStore


class CoreTest(unittest.TestCase):
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
            self.assertEqual(capture.ports, (12000, 12020))
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


if __name__ == "__main__":
    unittest.main()
