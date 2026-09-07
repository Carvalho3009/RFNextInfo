import ctypes as ct
import os
import struct
import unittest
from unittest.mock import Mock, patch
from core.live_stream import LiveEventDecoder

from core.pktmon_etw import (
    FILETIME_UNIX_EPOCH, PROVIDER, PktmonEtwCapture,
    _Header, _Logfile, _Record, agent_capture,
)


class PktmonEtwTest(unittest.TestCase):
    def test_sdk_x64_layout(self):
        self.assertEqual(ct.sizeof(_Header), 80)
        self.assertEqual(ct.sizeof(_Record), 112)
        self.assertEqual(ct.sizeof(_Logfile), 448)
        self.assertEqual(_Logfile.callback.offset, 424)

    def test_factory_preserves_streaming_and_falls_back_only_without_api(self):
        with patch("core.pktmon_etw.RealtimeCapture") as native:
            self.assertIs(agent_capture(None, (12020,)), native.return_value)
            native.return_value.start.assert_not_called()
            native.return_value._bind.side_effect = AttributeError("PacketMonitorInitialize")
            self.assertIsInstance(agent_capture(None, (12020,)), PktmonEtwCapture)

    def test_raw_file_target_is_rejected(self):
        with self.assertRaises(ValueError):
            PktmonEtwCapture("forbidden.pcap", (12020,))

    def test_payload_filter_timestamp_truncation_and_provider(self):
        sink = Mock()
        capture = PktmonEtwCapture(None, (12020,), sink)
        packet = bytearray(54)
        packet[12:14] = b"\x08\x00"
        packet[14] = 0x45
        packet[23] = 6
        packet[34:38] = struct.pack("!HH", 51000, 12020)
        record = _Record()
        record.header.provider[:] = PROVIDER
        record.header.event_id = 160
        record.header.timestamp = FILETIME_UNIX_EPOCH + 1_700_000_000 * 10_000_000
        values = {"Payload": bytes(packet), "OriginalPayloadSize": (54).to_bytes(2, "little")}
        with patch.object(capture, "_property_bytes", side_effect=lambda _p, name: values[name]):
            capture._on_record(ct.pointer(record))
            sink.assert_called_once_with(1_700_000_000_000_000_000, bytes(packet))
            values["OriginalPayloadSize"] = (60).to_bytes(2, "little")
            capture._on_record(ct.pointer(record))
            self.assertEqual(capture.property_errors, 1)
            values["OriginalPayloadSize"] = (54).to_bytes(2, "little")
            capture._port_set = {80}
            capture._on_record(ct.pointer(record))
            self.assertEqual(capture.filtered_packets, 1)
            record.header.provider[0] = 0
            capture._on_record(ct.pointer(record))
            self.assertEqual(capture.received_packets, 3)
            self.assertEqual(sink.call_count, 1)

    def test_existing_or_unknown_capture_is_not_touched(self):
        for status in ("Status: Active", "unknown"):
            capture = PktmonEtwCapture(None, (12020,))
            with patch.object(capture, "_bind_etw"), patch.object(capture, "_command", return_value=status) as command:
                with self.assertRaisesRegex(RuntimeError, "Nenhuma captura"):
                    capture.start()
                command.assert_called_once_with("status")

    def test_etw_packets_reach_same_decoder_with_two_isolated_clients(self):
        decoder = LiveEventDecoder()
        events = []
        capture = PktmonEtwCapture(None, (12020,),
            lambda stamp, packet: events.extend(decoder.feed(stamp, packet)))
        record = _Record()
        record.header.provider[:] = PROVIDER
        record.header.event_id = 160
        record.header.timestamp = FILETIME_UNIX_EPOCH + 1_700_000_000 * 10_000_000
        for uid, port in ((101, 50000), (202, 50001)):
            payload = struct.pack('<HHQHH', 0, 0, uid, 60, 1) + 'A'.encode('utf-16le')
            frame = struct.pack('<BH BH', 0, 6 + len(payload), 0, 0x0106) + payload
            tcp = struct.pack('!HHIIH', 12020, port, 100, 0, 0x5018) + b'\0' * 6 + frame
            ip = bytearray(20)
            ip[0], ip[9] = 0x45, 6
            ip[2:4] = (20 + len(tcp)).to_bytes(2, 'big')
            ip[12:20] = bytes((10, 0, 0, 1, 10, 0, 0, 2))
            packet = b'\0' * 12 + b'\x08\x00' + bytes(ip) + tcp
            properties = {'Payload': packet, 'OriginalPayloadSize': len(packet).to_bytes(2, 'little')}
            with patch.object(capture, '_property_bytes', side_effect=lambda _p, name: properties[name]):
                capture._on_record(ct.pointer(record))
        self.assertEqual([e['data']['fields']['character_uid'] for e in events], [101, 202])
        self.assertEqual(len({e['flow'] for e in events}), 2)
        self.assertEqual(capture.property_errors, 0)
        self.assertEqual(capture.sink_errors, 0)

    @unittest.skipUnless(os.name == "nt", "Windows")
    def test_start_stop_is_memory_only_and_cleans_only_owned_filters(self):
        capture = PktmonEtwCapture(None, (12020,))
        process = Mock()
        process.poll.return_value = None
        with patch.object(capture, "_bind_etw"), patch.object(capture, "_open_trace"), patch.object(
            capture, "_command", return_value="Not running",
        ) as command, patch("core.pktmon_etw.subprocess.Popen", return_value=process) as popen, patch(
            "core.pktmon_etw.threading.Thread",
        ) as thread:
            thread.return_value.is_alive.return_value = False
            capture.start()
            self.assertEqual(capture.add_ports((12010, 12010)), 1)
            self.assertEqual(len(capture._filters), 1)
            capture.stop()
            args, options = popen.call_args
            self.assertIn("real-time", args[0])
            self.assertNotIn("--file-name", args[0])
            self.assertEqual(options["stdout"], -3)  # DEVNULL: não grava saída bruta.
            removed = [call.args for call in command.call_args_list if call.args[:2] == ("filter", "remove")]
            self.assertEqual(len(removed), 1)
            self.assertTrue(all(len(args) == 3 and args[2].startswith(capture._prefix) for args in removed))

    def test_consumer_failure_is_reported_without_packet_contents(self):
        capture = PktmonEtwCapture(None, (12020,))
        capture._trace = 123
        capture._etw = Mock()
        capture._etw.ProcessTrace.return_value = 5
        capture._active = True
        capture._consume()
        self.assertFalse(capture._active)
        self.assertIn("(5)", capture.last_error)
        capture._active = True
        capture._etw.ProcessTrace.side_effect = OSError("PRIVATE_PACKET_CONTENT")
        capture._consume()
        self.assertFalse(capture._active)
        self.assertNotIn("PRIVATE", capture.last_error)

    def test_native_start_permission_error_does_not_switch_backend(self):
        with patch("core.pktmon_etw.RealtimeCapture") as native, patch(
            "core.pktmon_etw.PktmonEtwCapture",
        ) as fallback:
            native.return_value.start.side_effect = PermissionError("denied")
            capture = agent_capture(None, (12020,))
            with self.assertRaises(PermissionError):
                capture.start()
            fallback.assert_not_called()

    def test_partial_filter_failure_removes_only_successful_owned_filters(self):
        capture = PktmonEtwCapture(None, (12020, 12010))
        def command(*args):
            if args == ("status",):
                return "Not running"
            if args[:2] == ("filter", "add") and args[-1] == "12010":
                raise RuntimeError("failed")
        with patch.object(capture, "_bind_etw"), patch.object(capture, "_command", side_effect=command) as run:
            with self.assertRaises(RuntimeError):
                capture.start()
        removed = [c.args for c in run.call_args_list if c.args[:2] == ("filter", "remove")]
        self.assertEqual(removed, [("filter", "remove", f"{capture._prefix}-12020")])
        self.assertNotIn(("stop",), [c.args for c in run.call_args_list])

    def test_open_waits_for_controller_before_opening_etw(self):
        capture = PktmonEtwCapture(None, (12020,))
        capture._process = Mock()
        capture._process.poll.return_value = None
        capture._etw = Mock()
        capture._etw.OpenTraceW.return_value = 123
        with patch.object(capture, "_command", side_effect=["Not running", "Status: Active"]) as command:
            capture._open_trace()
        self.assertEqual(command.call_count, 2)
        capture._etw.OpenTraceW.assert_called_once()
        self.assertEqual(capture._trace, 123)
