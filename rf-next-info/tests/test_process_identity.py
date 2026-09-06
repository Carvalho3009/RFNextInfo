import os
import unittest
from unittest.mock import patch

from core.connections import agent_connection_aliases, process_started_at
from core.live_stream import LiveEventDecoder


class ProcessIdentityTest(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "API nativa Windows")
    def test_native_process_creation_is_stable(self):
        started = process_started_at(os.getpid())
        self.assertGreater(started, 0)
        self.assertEqual(started, process_started_at(os.getpid()))
        self.assertEqual(process_started_at(0), 0)

    def test_alias_uses_pid_and_creation_time_and_skips_unknown(self):
        with patch("core.connections._tcp_rows", return_value=[
            (10, 51000, 12020), (10, 51001, 12010), (20, 52000, 12020),
        ]), patch("core.connections._process_path", return_value=r"C:\RF\ProjectRF.exe"), patch(
            "core.connections.process_started_at", side_effect=lambda pid: 100 if pid == 10 else None,
        ) as probe:
            self.assertEqual(agent_connection_aliases(), {
                51000: "process:10:100", 51001: "process:10:100",
            })
            self.assertEqual(probe.call_count, 2)

    def test_reused_socket_starts_new_decoder_flow_only_for_new_process_instance(self):
        decoder = LiveEventDecoder(max_flows=4)
        flow = "10.0.0.1:51000 -> 10.0.0.2:12020"
        with patch("core.live_stream._tcp_payload", return_value=(flow, 12020, 100, b"a")), patch.object(
            decoder, "_decode_available", return_value=[],
        ) as decode:
            decoder.set_connection_aliases({51000: "process:10:100"})
            decoder.feed(1, b"packet")
            original = decoder._flows[flow]
            decoder.set_connection_aliases({})
            decoder.feed(2, b"packet")
            self.assertIs(decoder._flows[flow], original)
            decoder.set_connection_aliases({51000: "process:10:101"})
            decoder.feed(3, b"packet")
            self.assertIsNot(decoder._flows[flow], original)
            self.assertEqual(decode.call_args.args[1], "client-route:process:10:101")
