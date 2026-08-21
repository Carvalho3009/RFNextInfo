import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app.ui_qt.operations import (
    CaptureEngine,
    DEFAULT_MEMORY_BUDGET_MB,
    ExportEngine,
    GlobalHotkeys,
    MonitorEngine,
    SiteUploadEngine,
    _realtime_capture,
    memory_limits_for_budget,
    _site_loot_rows,
)
from app.ui_qt.data import ReadOnlySnapshotReader
from core.capture import CaptureStatus
from core.knowledge import KnowledgeStore
from core.pktmon_realtime import RealtimeCapture
from core.store import CaptureStore


class _FakeCapture:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.active = False
        self.heartbeats = 0
        self.files = ()
        self.added_ports = []
        self.started_ports = ()

    def start_for_ports(self, prefix: str, ports: tuple[int, ...]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{prefix}-001.etl"
        path.write_bytes(b"etl")
        self.files = (path,)
        self.started_ports = tuple(ports)
        self.active = True
        return path

    def system_running(self) -> bool:
        return False

    def add_ports(self, ports) -> int:
        self.added_ports.extend(ports)
        return len(tuple(ports))

    def attach(self, prefix, _ports=()):
        self.files = tuple(self.directory.glob(f"{prefix}*.etl"))
        self.active = self.system_running()
        return CaptureStatus(self.active, 3, 10**9, False, self.files)

    def heartbeat(self) -> None:
        self.heartbeats += 1

    def segment_files(self):
        return self.files

    def stop(self):
        self.active = False
        return CaptureStatus(False, 3, 10**9, False, self.files)


class _RunningCapture(_FakeCapture):
    def system_running(self) -> bool:
        return True


class _FakeLive:
    def __init__(self, target: Path, _ports: tuple[int, ...]) -> None:
        self.target = Path(target)

    def start(self) -> None:
        self.target.write_bytes(b"p" * 32)

    def add_ports(self, _ports) -> int:
        return 0

    def rotate(self, target: Path) -> Path:
        previous = self.target
        self.target = Path(target)
        self.target.write_bytes(b"p" * 32)
        return previous

    def stop(self) -> None:
        pass


class _BrokenLive(_FakeLive):
    def start(self) -> None:
        raise RuntimeError("Pktmonapi.dll não está disponível")


class _MemoryLive:
    def __init__(self, target, _ports) -> None:
        self.target = target
        self.sink = None
        self.active = False

    def set_packet_sink(self, sink) -> None:
        self.sink = sink

    def start(self) -> None:
        self.active = True

    def add_ports(self, _ports) -> int:
        return 0

    def stop(self) -> None:
        self.active = False


class _FakeStore:
    def __init__(self, _path: Path) -> None:
        pass

    def ingest(self, *_args, **_kwargs) -> int:
        return 1

    def remove_sources(self, _sources) -> None:
        pass

    def subsessions(self, _session):
        return []

    def checkpoint_session(self, session_id, *, reason="interval"):
        return {"session_id": session_id, "reason": reason}

    def close(self) -> None:
        pass


class _AllowedLicense:
    installation_id = "install-1"
    lease = "lease-1"

    @staticmethod
    def require(_capability, _feature="base"):
        return {
            "active": True,
            "connection_limits": {"pc": 2, "emulators": 5},
        }


class _TierOneLicense(_AllowedLicense):
    @staticmethod
    def require(_capability, _feature="base"):
        return {
            "active": True,
            "connection_limits": {"pc": 2, "emulators": 1},
        }


class _DeniedLicense:
    installation_id = "install-1"
    lease = None

    @staticmethod
    def require(_capability, _feature="base"):
        raise PermissionError("licença necessária")


class ReadOnlySnapshotReaderTest(unittest.TestCase):
    def test_live_reader_routes_each_client_only_once_and_limits_modes(self):
        events = [{
            "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
            "ts_ns": 1,
            "type": "world_info_prefix",
            "data": {"fields": {
                "character_uid": 202, "character_name": "Novo",
            }},
        }]
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.data._event_matches_ports", wraps=lambda event, ports: True
        ) as matches, mock.patch(
            "app.ui_qt.data.summarize_combat", return_value={}
        ) as summarize:
            result = ReadOnlySnapshotReader(
                Path(directory) / "missing.sqlite3", _AllowedLicense()
            ).load_live_combat(events, ((50000,),), modes=("pvp",))

        self.assertEqual(matches.call_count, len(events))
        self.assertEqual(summarize.call_args.kwargs["modes"], ("pvp",))
        self.assertEqual(result["combat_monitors"][0]["character_name"], "Novo")

    def test_live_identity_replaces_old_session_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            source = root / "old.pcap"
            source.write_bytes(b"old")
            store = CaptureStore(database)
            try:
                store.add_events(source, [{
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 1,
                    "bundle_seq": 0,
                    "opcode": 0x0106,
                    "type": "world_info_prefix",
                    "data": {"fields": {
                        "character_uid": 101,
                        "character_name": "Antigo",
                    }},
                }], "session", client_ports=((50000,),))
            finally:
                store.close()
            now_ns = time.time_ns()
            events = [{
                "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                "ts_ns": now_ns,
                "type": "world_info_prefix",
                "data": {"fields": {
                    "character_uid": 202,
                    "character_name": "Novo",
                }},
            }, {
                "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                "ts_ns": now_ns,
                "type": "appear_player_list",
                "data": {"units": [{
                    "uid": 20,
                    "character_uid": 202,
                    "name": "Novo",
                }]},
            }]

            result = ReadOnlySnapshotReader(
                database, _AllowedLicense()
            ).load_live_combat(events, ((50000,),))

            self.assertEqual(len(result["combat_monitors"]), 1)
            monitor = result["combat_monitors"][0]
            self.assertEqual(
                (monitor["character_uid"], monitor["character_name"]),
                ("202", "Novo"),
            )
            self.assertEqual(monitor["local_combat_uid"], 20)

    def test_live_reader_routes_exitlag_flow_by_confirmed_character_uid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            source = root / "profile.pcap"
            source.write_bytes(b"profile")
            store = CaptureStore(database)
            try:
                store.add_events(source, [{
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 1,
                    "bundle_seq": 0,
                    "opcode": 0x0106,
                    "type": "world_info_prefix",
                    "data": {"fields": {
                        "character_uid": 101,
                        "character_name": "Local",
                    }},
                }], "session", client_ports=((50000,),))
            finally:
                store.close()
            tunneled_flow = "127.0.0.1:61000 -> 127.0.0.1:9001"
            events = [{
                "flow": tunneled_flow,
                "ts_ns": time.time_ns(),
                "type": "world_info_prefix",
                "data": {"fields": {
                    "character_uid": 101,
                    "character_name": "Local",
                }},
            }, {
                "flow": tunneled_flow,
                "ts_ns": time.time_ns(),
                "type": "appear_player_list",
                "data": {"units": [{
                    "uid": 20,
                    "character_uid": 202,
                    "name": "Inimigo",
                    "pvp_status": "enemy",
                }]},
            }]

            result = ReadOnlySnapshotReader(
                database, _AllowedLicense()
            ).load_live_combat(events, ((50000,),), modes=("pvp",))

        self.assertEqual(len(result["combat_monitors"]), 1)
        self.assertEqual(result["combat_monitors"][0]["client_key"], "client:a")
        self.assertEqual(result["routing_metrics"], {
            "total_events": 2,
            "associated_events": 2,
            "identity_associated_events": 2,
            "identity_bound_flows": 1,
            "unmatched_events": 0,
        })

    def test_live_reader_routes_single_client_boss_across_rotated_game_port(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            source = root / "profile.pcap"
            source.write_bytes(b"profile")
            store = CaptureStore(database)
            try:
                store.add_events(source, [{
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 1,
                    "bundle_seq": 0,
                    "opcode": 0x0106,
                    "type": "world_info_prefix",
                    "data": {"fields": {
                        "character_uid": 101,
                        "character_name": "Local",
                    }},
                }], "session", client_ports=((50000,),))
            finally:
                store.close()
            now_ns = time.time_ns()
            events = [{
                "flow": "10.0.0.1:12020 -> 127.0.0.1:17330",
                "ts_ns": now_ns,
                "type": "world_info_prefix",
                "data": {"fields": {
                    "character_uid": 101,
                    "character_name": "Local",
                }},
            }, {
                "flow": "10.0.0.1:12010 -> 127.0.0.1:17346",
                "ts_ns": now_ns,
                "type": "appear_monster_list",
                "data": {"units": [{
                    "uid": 30,
                    "npc_index": 375100,
                    "max_hp": 500_000_000,
                    "current_hp": 500_000_000,
                }]},
            }]

            result = ReadOnlySnapshotReader(
                database, _AllowedLicense()
            ).load_live_combat(events, ((50000,),), modes=("boss",))

        self.assertEqual(len(result["combat_monitors"]), 1)
        self.assertEqual(
            result["combat_monitors"][0]["bosses"][0]["name"],
            "Xenogeyser",
        )
        self.assertEqual(result["routing_metrics"]["associated_events"], 2)
        self.assertEqual(result["routing_metrics"]["unmatched_events"], 0)
        self.assertEqual(
            result["routing_metrics"]["single_client_fallback_events"], 1
        )

    def test_live_reader_does_not_mix_uid_bound_exitlag_flows(self):
        profiles = [
            {"uid": "101", "name": "A", "client_key": "client:a"},
            {"uid": "202", "name": "B", "client_key": "client:b"},
        ]
        flow = "127.0.0.1:61001 -> 127.0.0.1:9001"
        events = [{
            "flow": flow,
            "type": "world_info_prefix",
            "data": {"fields": {
                "character_uid": 202,
                "character_name": "B",
            }},
        }, {
            "flow": flow,
            "type": "appear_player_list",
            "data": {"units": [{"character_uid": 303, "name": "Alvo"}]},
        }]
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "capture.sqlite3"
            store = CaptureStore(database)
            store.close()
            with mock.patch.object(
                CaptureStore, "latest_session", return_value="session"
            ), mock.patch.object(
                CaptureStore, "session_profiles", return_value=profiles
            ), mock.patch(
                "app.ui_qt.data.summarize_combat", side_effect=({}, {})
            ) as summarize:
                result = ReadOnlySnapshotReader(
                    database, _AllowedLicense()
                ).load_live_combat(
                    events, ((50000,), (50001,)), modes=("pvp",)
                )

        self.assertEqual(summarize.call_count, 2)
        routed_a = summarize.call_args_list[0].args[0]
        routed_b = summarize.call_args_list[1].args[0]
        self.assertEqual(routed_a, [])
        self.assertEqual(routed_b, events)
        self.assertEqual(
            [row["client_key"] for row in result["combat_monitors"]],
            ["client:a", "client:b"],
        )


class CaptureEngineTest(unittest.TestCase):
    def test_memory_budget_scales_resident_limits_but_not_above_safe_defaults(self):
        low = memory_limits_for_budget(256)
        standard = memory_limits_for_budget(DEFAULT_MEMORY_BUDGET_MB)
        high = memory_limits_for_budget(2048)

        self.assertLess(low["pending_packets"], standard["pending_packets"])
        self.assertLess(low["events"], standard["events"])
        self.assertLess(low["pvp_rows"], standard["pvp_rows"])
        self.assertEqual(high["pending_packets"], standard["pending_packets"])
        self.assertEqual(high["events"], standard["events"])
        self.assertEqual(high["pressure_bytes"], 2048 * 1024**2)
        self.assertEqual(memory_limits_for_budget(300)["budget_mb"], 256)
        self.assertEqual(memory_limits_for_budget(350)["budget_mb"], 384)
        self.assertEqual(memory_limits_for_budget(9999)["budget_mb"], 2048)

        monitor = MonitorEngine(_AllowedLicense(), memory_budget_mb=256)
        metrics = monitor.events.metrics()
        self.assertEqual(monitor.memory_budget_mb, 256)
        self.assertEqual(metrics["queue_limit"], low["pending_packets"])
        self.assertEqual(metrics["event_limit"], low["events"])
        self.assertEqual(metrics["flow_limit"], low["flows"])

        writer = _realtime_capture(
            RealtimeCapture,
            Path("memory-budget.pcap"),
            (12020,),
            low,
        )
        self.assertEqual(writer.write_queue_limit, low["pending_packets"])
        self.assertEqual(
            writer.write_queue_byte_limit,
            low["pending_packet_bytes"],
        )

        active_monitor = MonitorEngine(_AllowedLicense())
        active_monitor.live_capture = _MemoryLive(None, ())
        previous_events = active_monitor.events
        self.assertFalse(active_monitor.configure_memory_budget(256))
        self.assertEqual(
            active_monitor.memory_budget_mb,
            DEFAULT_MEMORY_BUDGET_MB,
        )
        active_monitor.stop()
        self.assertEqual(active_monitor.memory_budget_mb, 256)
        self.assertIsNot(active_monitor.events, previous_events)
        self.assertEqual(
            active_monitor.events.metrics()["event_limit"],
            low["events"],
        )

    def test_denied_license_cannot_start_capture_or_monitor(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _DeniedLicense(),
                capture_factory=_FakeCapture,
            )
            monitor = MonitorEngine(
                _DeniedLicense(), live_factory=_MemoryLive
            )
            with self.assertRaises(PermissionError):
                capture.start()
            with self.assertRaises(PermissionError):
                monitor.start(("monitor-pve",))
            self.assertFalse(list(root.glob("*.etl")))

    def test_multiple_same_family_clients_require_distinct_routes(self):
        processes = lambda _ports: {
            "ProjectRF.exe": ({10, 20}, {50000, 50001}, {12020})
        }
        monitor = MonitorEngine(
            _AllowedLicense(),
            live_factory=_MemoryLive,
            process_reader=processes,
            client_reader=lambda *_args: [],
        )
        with self.assertRaisesRegex(RuntimeError, "separar.*clientes PC"):
            monitor.start(("monitor-pvp",))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            capture = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                process_reader=processes,
                client_reader=lambda *_args: [],
            )
            with self.assertRaisesRegex(RuntimeError, "separar.*clientes PC"):
                capture.start()
            self.assertFalse(list(root.glob("*.etl")))

    def test_stop_without_reading_preserves_raw_files_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    "ProjectRF.exe": ((101,), (50000,), (12020,))
                },
                client_reader=lambda *_args: [
                    {"pid": 101, "local_ports": (50000,), "remote_ports": (12020,)}
                ],
            )
            started = engine.start()

            result = engine.stop_without_reading()

            self.assertEqual(result["session_id"], started["session_id"])
            self.assertFalse(result["decoded"])
            self.assertTrue(result["paused"])
            self.assertTrue(result["files"])
            self.assertTrue(all(path.exists() for path in result["files"]))
            self.assertEqual(engine.current_session, started["session_id"])
            self.assertTrue(engine.paused)

    def test_independent_monitor_uses_memory_only_stream(self):
        monitor = MonitorEngine(
            _AllowedLicense(),
            live_factory=_MemoryLive,
            process_reader=lambda _ports: {
                "ProjectRF.exe": ((101,), (50000,), (12020,))
            },
            client_reader=lambda _exe, _ports: [
                {
                    "pid": 101,
                    "local_ports": (50000,),
                    "remote_ports": (12020,),
                }
            ],
        )

        started = monitor.start(("monitor-pve",))

        self.assertTrue(started["active"])
        self.assertIsNone(monitor.live_capture.target)
        self.assertIsNotNone(monitor.live_capture.sink)
        self.assertEqual(
            monitor.snapshot(("monitor-pve",))["client_ports"], [[50000]]
        )
        monitor.stop()
        self.assertFalse(monitor.active)

    def test_pc_and_emulators_keep_separate_fixed_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def routes(executable, _ports):
                if "HD-Player" in executable:
                    return [
                        {"pid": 30, "local_ports": (57001,), "remote_ports": (12020,)},
                        {"pid": 40, "local_ports": (57002,), "remote_ports": (12020,)},
                    ]
                return [
                    {"pid": 10, "local_ports": (50000,), "remote_ports": (12020,)}
                ]

            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\Games\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                emulator_reader=lambda _ports: {
                    r"C:\BlueStacks\HD-Player.exe": (
                        {30, 40}, {57001, 57002}, {12020}
                    )
                },
                client_reader=routes,
            )

            started = engine.start()

            self.assertEqual(started["pc_clients"], 1)
            self.assertEqual(started["emulators"], 2)
            self.assertEqual(
                started["capture_client_ports"],
                [[50000], [], [57001], [57002]],
            )
            self.assertEqual(engine.client_pids, [10, 30, 40])
            engine.stop_without_reading()

    def test_legacy_tier_does_not_limit_second_emulator_for_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = [
                {"pid": 30, "local_ports": (57001,), "remote_ports": (12020,)},
                {"pid": 40, "local_ports": (57002,), "remote_ports": (12020,)},
            ]
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _TierOneLicense(),
                capture_factory=_FakeCapture,
                process_reader=lambda _ports: {},
                emulator_reader=lambda _ports: {
                    r"C:\BlueStacks\HD-Player.exe": (
                        {30, 40}, {57001, 57002}, {12020}
                    )
                },
                client_reader=lambda *_args: routes,
            )

            started = engine.start()
            self.assertEqual(started["emulators"], 2)
            engine.stop_without_reading()

    def test_legacy_tier_does_not_limit_second_emulator_for_monitor(self):
        routes = [
            {"pid": 30, "local_ports": (57001,), "remote_ports": (12020,)},
            {"pid": 40, "local_ports": (57002,), "remote_ports": (12020,)},
        ]
        monitor = MonitorEngine(
            _TierOneLicense(),
            live_factory=_MemoryLive,
            process_reader=lambda _ports: {},
            emulator_reader=lambda _ports: {
                r"C:\BlueStacks\HD-Player.exe": (
                    {30, 40}, {57001, 57002}, {12020}
                )
            },
            client_reader=lambda *_args: routes,
        )

        started = monitor.start(("monitor-pve",))
        self.assertEqual(started["emulators"], 2)
        monitor.stop()

    def test_legacy_tier_accepts_later_client_without_stopping_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = [{
                "pid": 30,
                "local_ports": (57001,),
                "remote_ports": (12020,),
            }]
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _TierOneLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {},
                emulator_reader=lambda _ports: {
                    r"C:\BlueStacks\HD-Player.exe": (
                        {int(route["pid"]) for route in routes},
                        {
                            int(route["local_ports"][0])
                            for route in routes
                        },
                        {12020},
                    )
                },
                client_reader=lambda *_args: list(routes),
            )
            engine.start()
            routes.append({
                "pid": 40,
                "local_ports": (57002,),
                "remote_ports": (12020,),
            })

            engine.preview_live()
            self.assertTrue(engine.active)
            self.assertEqual(
                engine.client_ports,
                ((), (), (57001,), (57002,)),
            )
            self.assertNotIn(57002, engine.capture.added_ports)
            engine.stop_without_reading()

    def test_capture_accepts_more_than_five_emulators_without_license_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            routes = [
                {
                    "pid": pid,
                    "local_ports": (57000 + pid,),
                    "remote_ports": (12020,),
                }
                for pid in range(1, 7)
            ]
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                process_reader=lambda _ports: {},
                emulator_reader=lambda _ports: {
                    r"C:\BlueStacks\HD-Player.exe": (
                        set(range(1, 7)), set(range(57001, 57007)), {12020}
                    )
                },
                client_reader=lambda *_args: routes,
            )

            started = engine.start()
            self.assertEqual(started["emulators"], 6)
            engine.stop_without_reading()

    def test_restore_pending_capture_keeps_the_same_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfnext-20260805-120000-001-01-001.etl").write_bytes(b"etl")
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
            )

            restored = engine.restore({
                "capture_pending": True,
                "last_session": "Profile-20260805-120000-001",
                "capture_prefix": "rfnext-20260805-120000-001-01",
                "capture_ports": [12020],
                "capture_client_ports": [[50000]],
            })

            self.assertEqual(restored["session_id"], "Profile-20260805-120000-001")
            self.assertEqual(engine.current_session, "Profile-20260805-120000-001")
            self.assertEqual(engine.client_ports, ())

    def test_resume_preserves_uid_slots_without_retaining_old_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfnext-20260805-120000-001-01-001.etl").write_bytes(b"etl")
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10, 20}, {51000, 51001}, {12020})
                },
                client_reader=lambda *_args: [
                    {"pid": 10, "local_ports": (51000,), "remote_ports": (12020,)},
                    {"pid": 20, "local_ports": (51001,), "remote_ports": (12020,)},
                ],
            )
            engine.restore({
                "capture_pending": True,
                "last_session": "Profile-20260805-120000-001",
                "capture_prefix": "rfnext-20260805-120000-001-01",
                "capture_ports": [12020],
                "capture_client_ports": [[50000], [50001]],
                "capture_client_pids": [10, 20],
            })

            started = engine.start()

            self.assertEqual(started["session_id"], "Profile-20260805-120000-001")
            self.assertEqual(engine.client_pids, [10, 20])
            self.assertEqual(engine.client_ports, ((51000,), (51001,)))
            self.assertNotIn(50000, started["capture_client_ports"][0])

    def test_resume_with_restarted_clients_does_not_guess_uid_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "rfnext-20260805-120000-001-01-001.etl").write_bytes(b"etl")
            engine = CaptureEngine(
                root,
                root / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({30, 40}, {52000, 52001}, {12020})
                },
                client_reader=lambda *_args: [
                    {"pid": 30, "local_ports": (52000,), "remote_ports": (12020,)},
                    {"pid": 40, "local_ports": (52001,), "remote_ports": (12020,)},
                ],
            )
            engine.restore({
                "capture_pending": True,
                "last_session": "Profile-20260805-120000-001",
                "capture_prefix": "rfnext-20260805-120000-001-01",
                "capture_ports": [12020],
                "capture_client_ports": [[50000], [50001]],
                "capture_client_pids": [10, 20],
            })

            started = engine.start()

            self.assertEqual(started["capture_client_ports"], [])
            self.assertEqual(started["capture_client_pids"], [])

    def test_send_hotkeys_are_ignored_and_monitor_hotkeys_remain_global(self):
        definitions = GlobalHotkeys.definitions({
            "character": "F5", "market": "F6",
            "codex": "F7", "memory_chips": "F10",
            "monitor_pve": "Alt+F10",
            "monitor_pvp": "Shift+F11",
            "monitor_boss": "Ctrl+F12",
        })
        actions = {action: (key, modifiers) for _, action, key, modifiers in definitions}
        self.assertNotIn("character", actions)
        self.assertNotIn("market", actions)
        self.assertNotIn("codex", actions)
        self.assertNotIn("memory_chips", actions)
        self.assertEqual(actions["start"], (0x77, 0x4002))
        self.assertEqual(actions["monitor_pve"], (0x79, 0x4001))
        self.assertEqual(actions["monitor_pvp"], (0x7A, 0x4004))
        self.assertEqual(actions["monitor_boss"], (0x7B, 0x4002))
        self.assertEqual(actions["overlay_pvp"], (0x75, 0x4006))
        self.assertEqual(actions["overlay_boss"], (0x76, 0x4006))
        self.assertIsNone(GlobalHotkeys.parse_shortcut("Ctrl+X"))
        self.assertIsNone(GlobalHotkeys.parse_shortcut("Ctrl+Ctrl+F5"))

    def test_site_loot_rows_use_numeric_contract_and_drop_empty_items(self):
        self.assertEqual(
            _site_loot_rows(
                [
                    {
                        "item_index": 42,
                        "item": "Loot teste",
                        "count": 2,
                        "grade": 4,
                        "rarity": "Épico",
                    },
                    {"item_index": 99, "count": 0, "grade": 1},
                ]
            ),
            [
                {
                    "itemIndex": 42,
                    "name": "Loot teste",
                    "quantity": 2,
                    "rarity": 4,
                }
            ],
        )

    def test_live_read_refreshes_routes_without_accumulating_ephemeral_filters(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", _FakeStore
        ):
            calls = iter((
                [{"pid": 10, "local_ports": (50000,), "remote_ports": (12020,)}],
                [{"pid": 10, "local_ports": (50001,), "remote_ports": (12020,)}],
            ))
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: next(calls),
            )

            engine.start()
            engine.read_live()
            self.assertEqual(engine.client_ports, ((50000, 50001),))
            self.assertNotIn(50000, engine.capture.started_ports)
            self.assertNotIn(50001, engine.capture.added_ports)
            self.assertIn(12020, engine.capture.started_ports)

    def test_restarted_client_rebuilds_routes_instead_of_disabling_session(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", _FakeStore
        ):
            calls = iter((
                [{"pid": 10, "local_ports": (50000,), "remote_ports": (12020,)}],
                [{"pid": 20, "local_ports": (51000,), "remote_ports": (12020,)}],
            ))
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: next(calls),
            )

            engine.start()
            engine.read_live()

            self.assertTrue(engine.route_identity_trusted)
            self.assertEqual(engine.client_pids, [20])
            self.assertEqual(engine.client_ports, ((51000,),))

    def test_opening_emulator_does_not_discard_temporarily_idle_pc_routes(self):
        with tempfile.TemporaryDirectory() as directory:
            emulator_active = False

            def emulator_reader(_ports):
                return (
                    {
                        r"C:\BlueStacks\HD-Player.exe": (
                            {30}, {57000}, {12020}
                        )
                    }
                    if emulator_active
                    else {}
                )

            def routes(executable, _ports):
                if "HD-Player" in executable:
                    return [{
                        "pid": 30,
                        "local_ports": (57000,),
                        "remote_ports": (12020,),
                    }]
                return [] if emulator_active else [{
                    "pid": 10,
                    "local_ports": (50000,),
                    "remote_ports": (12020,),
                }]

            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                emulator_reader=emulator_reader,
                client_reader=routes,
            )
            engine.start()
            emulator_active = True

            engine.preview_live()

            self.assertTrue(engine.route_identity_trusted)
            self.assertEqual(
                engine.client_ports, ((50000,), (), (57000,))
            )
            self.assertEqual(engine.client_pids, [10, 30])

    def test_does_not_replace_an_existing_pktmon_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_RunningCapture,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: [
                    {"pid": 10, "local_ports": (50000,), "remote_ports": (12020,)}
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "Outra captura PktMon"):
                engine.start()
            self.assertFalse(list(Path(directory).glob("*.etl")))

    def test_start_read_pause_resume_and_stop(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", _FakeStore
        ):
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                profile="Teste",
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10, 20}, {50000, 50001}, {12020})
                },
                client_reader=lambda *_args: [
                    {"pid": 10, "local_ports": (50000,), "remote_ports": (12020,)},
                    {"pid": 20, "local_ports": (50001,), "remote_ports": (12020,)},
                ],
            )

            started = engine.start()
            session = started["session_id"]
            self.assertEqual(started["clients"], 2)
            self.assertTrue(started["live"])
            engine.capture.active = False
            self.assertTrue(engine.active)
            engine.capture.active = True
            engine.heartbeat()
            self.assertEqual(engine.capture.heartbeats, 1)
            self.assertEqual(engine.read_live()["added"], 1)

            self.assertTrue(engine.stop(pause=True)["paused"])
            self.assertEqual(engine.current_session, session)
            self.assertEqual(engine.start()["session_id"], session)
            self.assertFalse(engine.stop()["paused"])
            self.assertIsNone(engine.current_session)

    def test_start_new_finalizes_paused_session_without_deleting_it(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", _FakeStore
        ):
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                profile="Teste",
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: [{
                    "pid": 10, "local_ports": (50000,), "remote_ports": (12020,),
                }],
            )

            first = engine.start()["session_id"]
            engine.stop(pause=True)
            second = engine.start_new()

            self.assertEqual(second["previous_session"], first)
            self.assertNotEqual(second["session_id"], first)
            self.assertFalse(second["resumed"])
            self.assertEqual(engine.current_session, second["session_id"])
            engine.stop_without_reading()

    def test_falls_back_to_rotating_etl_when_realtime_api_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", _FakeStore
        ):
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_BrokenLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: [{
                    "pid": 10, "local_ports": (50000,),
                    "remote_ports": (12020,),
                }],
            )

            started = engine.start()
            result = engine.read_live()

            self.assertFalse(started["live"])
            self.assertIn("Pktmonapi.dll", started["live_error"])
            self.assertTrue(result["available"])
            self.assertTrue(result["fallback"])
            self.assertEqual(result["added"], 1)
            self.assertTrue(engine.capture.active)
            self.assertNotEqual(result["capture_prefix"], started["capture_prefix"])

    def test_stop_preserves_live_events_instead_of_replacing_them_with_etl(self):
        ingested = []

        class Store(_FakeStore):
            def ingest(self, path, **kwargs):
                ingested.append((Path(path).suffix, kwargs.get("append_only")))
                return 1

        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", Store
        ):
            engine = CaptureEngine(
                Path(directory),
                Path(directory) / "capture.sqlite3",
                _AllowedLicense(),
                capture_factory=_FakeCapture,
                live_factory=_FakeLive,
                process_reader=lambda _ports: {
                    r"C:\ProjectRF.exe": ({10}, {50000}, {12020})
                },
                client_reader=lambda *_args: [{
                    "pid": 10, "local_ports": (50000,),
                    "remote_ports": (12020,),
                }],
            )
            engine.start()
            engine.read_live()
            engine.stop()

        self.assertTrue(ingested)
        self.assertEqual({suffix for suffix, _ in ingested}, {".pcap"})
        self.assertTrue(all(append_only for _, append_only in ingested))


class SiteUploadEngineTest(unittest.TestCase):
    def test_auction_bank_send_is_sanitized_and_idempotent(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_auction_bank(self, payload, key):
                self.uploaded = (payload, key)
                return {"receipt": "auction-1"}

        event = {"ts_ns": 1, "data": {
            "message": "FL2C_ans_exchange_for_my_sales_list_Message",
            "ret": 0,
            "exchange_server_type": 2,
            "my_sales_list": [{
                "exchange_index": 444,
                "account_id": 111,
                "pc_id": 222,
                "item_info": {
                    "index": 270062, "count": 3, "enchant_level": 7,
                    "talic_indices": [1, 2],
                },
                "registed_time": 10,
                "expired_time": 20,
                "selling_time": 0,
                "selling_price": 1500,
                "settlement_price": 0,
            }],
        }}
        store = mock.Mock()
        store.session_profiles.return_value = [{"uid": "101"}]
        store.auction_events_for_character.return_value = [event]
        site = Site()
        with mock.patch("app.ui_qt.operations.CaptureStore", return_value=store):
            result = SiteUploadEngine(
                Path("capture.sqlite3"), site, _AllowedLicense()
            ).send_auction_bank("session", "pt")

        payload, key = site.uploaded
        self.assertEqual(result, {
            "listings": 1, "transactions": 0,
            "receipt": "auction-1", "duplicate": False,
        })
        self.assertRegex(key, r"^[a-f0-9]{64}$")
        serialized = json.dumps(payload)
        for forbidden in ("account_id", "pc_id", "exchange_index", "444"):
            self.assertNotIn(forbidden, serialized)

    def test_exp_rank_send_requires_server_confirmation(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_exp_rank(self, payload, key):
                self.uploaded = (payload, key)
                return {"received_exp_rank": 1}

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        ranking = {
            "schema_version": 1,
            "scope_id": 1,
            "ranking_cycle": 44,
            "captured_at_ns": 123,
            "completeness": "complete",
            "records": [{
                "character_uid": "101",
                "character_name": "Alice",
                "guild_name": "Guilda",
                "guild_mark_hex": "84000457",
                "total_exp": 999,
                "rank": 1,
                "previous_rank": 2,
            }],
            "snapshot_key": "1:44",
            "signature": "a" * 64,
        }
        store = mock.Mock()
        store.exp_rank_snapshot.return_value = ranking
        site = Site()
        with mock.patch("app.ui_qt.operations.CaptureStore", return_value=store):
            engine = SiteUploadEngine(Path("capture.sqlite3"), site, License())
            result = engine.send_exp_rank("session")
            self.assertEqual(result["records"], 1)
            self.assertEqual(site.uploaded[0]["exp_rank"]["records"][0]["rank"], 1)
            self.assertNotIn("signature", site.uploaded[0]["exp_rank"])
            store.exp_rank_snapshot.return_value = {
                **ranking,
                "completeness": "partial",
            }
            with self.assertRaisesRegex(ValueError, "ainda está parcial"):
                engine.send_exp_rank("session")
            store.exp_rank_snapshot.return_value = ranking
            site.upload_exp_rank = lambda _payload, _key: {"ok": True}
            with self.assertRaisesRegex(ValueError, "contrato do ranking"):
                engine.send_exp_rank("session")

    def test_pvp_send_and_receive_are_independent(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_observations(self, payload, key):
                self.uploaded = (payload, key)
                return {"characters": [{
                    "character_uid": "123",
                    "name": "Não mesclar no envio",
                    "pvp_status": "enemy",
                    "first_seen_at": "2026-08-12T10:00:00+00:00",
                    "last_seen_at": "2026-08-12T10:00:00+00:00",
                }]}

            def upload_pve_observations(self, payload, key):
                self.uploaded_pve = (payload, key)
                return {
                    "schema": "rf-qol.pve-observations.ack",
                    "schema_version": 1,
                    "acks": [
                        {
                            "observation_id": item["observation_id"],
                            "status": "accepted",
                        }
                        for item in payload["observations"]
                    ],
                }

            def download_observations(self):
                self.downloaded = True
                return {
                    "revision": 7,
                    "characters": [{
                        "character_uid": "123",
                        "name": "Banco Final",
                        "pvp_status": "ally",
                        "first_seen_at": "2026-08-12T10:00:00+00:00",
                        "last_seen_at": "2026-08-12T11:00:00+00:00",
                    }],
                }

        event = {
            "type": "appear_player_list",
            "data": {"units": [{
                "character_uid": 123,
                "name": "Local",
                "pvp_status": "enemy",
            }]},
        }
        mob_event = {
            "type": "appear_monster_list",
            "data": {"units": [{"npc_index": 305208, "max_hp": 0}]},
        }
        capture = mock.Mock()
        capture.session_envelope.return_value = {"events": [event, mob_event]}
        site = Site()
        with tempfile.TemporaryDirectory() as directory, mock.patch(
            "app.ui_qt.operations.CaptureStore", return_value=capture
        ):
            knowledge_path = Path(directory) / "knowledge.sqlite3"
            engine = SiteUploadEngine(Path("capture.sqlite3"), site, _AllowedLicense())
            sent = engine.send_observations("session", knowledge_path)
            knowledge = KnowledgeStore(knowledge_path)
            try:
                after_send = knowledge.characters()[0]
                pending_mobs = knowledge.pending_payload()["mobs"]
            finally:
                knowledge.close()
            received = engine.receive_observations(knowledge_path)
            knowledge = KnowledgeStore(knowledge_path)
            try:
                after_receive = knowledge.characters()[0]
            finally:
                knowledge.close()

        self.assertEqual(sent["sent_characters"], 1)
        self.assertEqual(sent["sent_mobs"], 1)
        self.assertEqual(site.uploaded[0]["mobs"], [])
        self.assertEqual(pending_mobs, [])
        self.assertEqual(after_send["name"], "Local")
        self.assertEqual(after_send["upload_state"], "sent")
        self.assertEqual(received["synced_characters"], 1)
        self.assertEqual(after_receive["name"], "Banco Final")
        self.assertEqual(after_receive["pvp_status"], "ally")
        self.assertTrue(site.downloaded)

    def test_inventory_send_contains_only_the_selected_character(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_live(self, mode, payload, key):
                self.sent = (mode, payload, key)
                return {"receipt": "inventory-ok"}

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        site = Site()
        store = mock.Mock()
        snapshot = {
            "session_id": "session",
            "characters": [
                {"uid": "101", "name": "Alice", "client_key": "client:a"},
                {"uid": "202", "name": "Bob", "client_key": "client:b"},
            ],
            "inventories": {
                "101": [{
                    "item_index": 270062,
                    "name": "Material",
                    "quantity": 25,
                    "kind": "stackable",
                    "category": "materials",
                    "slot": 7,
                }],
                "202": [{
                    "item_index": 270063,
                    "name": "Outro cliente",
                    "quantity": 1,
                    "kind": "stackable",
                    "category": "other",
                    "slot": 7,
                }],
            },
        }
        with mock.patch("app.ui_qt.operations.CaptureStore", return_value=store):
            result = SiteUploadEngine(
                Path("capture.sqlite3"), site, License()
            ).send_mode("inventory", 0, snapshot, "pt")

        mode, payload, _key = site.sent
        self.assertEqual((mode, result["receipt"]), ("inventory", "inventory-ok"))
        self.assertEqual(payload["profiles"][0]["character_uid"], "101")
        self.assertEqual(
            [item["name"] for item in payload["capture"]["inventory"]],
            ["Material"],
        )

    def test_send_all_keeps_the_selected_client_and_available_domains(self):
        class Site:
            connected = True
            profile = "Profile"

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        engine = SiteUploadEngine(Path("capture.sqlite3"), Site(), License())
        snapshot = {
            "session_id": "session",
            "characters": [
                {"uid": "101", "name": "Alice", "client_key": "client:a"},
                {"uid": "202", "name": "Bob", "client_key": "client:b"},
            ],
            "inventories": {
                "101": [{
                    "item_index": 270062, "quantity": 1, "kind": "stackable"
                }],
                "202": [{
                    "item_index": 270063, "quantity": 1, "kind": "stackable"
                }],
            },
            "collection_type_counts_by_uid": {"101": {1: 1, 2: 1}},
        }
        sent = []
        with mock.patch.object(
            engine,
            "send_mode",
            side_effect=lambda mode, client, _snapshot, _language: (
                sent.append((mode, client))
                or {"target": "Cliente A", "receipt": mode}
            ),
        ):
            result = engine.send_all(0, snapshot, "pt")

        self.assertEqual(
            sent,
            [("character", 0), ("inventory", 0), ("codex", 0), ("memory_chips", 0)],
        )
        self.assertEqual(result["uid"], "101")

    def test_codex_send_reuses_the_latest_complete_snapshot(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_live(self, mode, payload, key):
                self.sent = (mode, payload, key)
                return {"receipt": "ok"}

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        store = mock.Mock()
        store.latest_collection_envelope.return_value = {
            "events": [{
                "type": "collection_snapshot_chunk",
                "data": {
                    "collection_type": 1,
                    "records": [{
                        "collection_index": 1001,
                        "collection_type": 1,
                        "completed_slots": [0],
                    }],
                },
            }]
        }
        site = Site()
        with mock.patch("app.ui_qt.operations.CaptureStore", return_value=store):
            result = SiteUploadEngine(Path("capture.sqlite3"), site, License()).send_mode(
                "codex",
                0,
                {
                    "session_id": "current",
                    "characters": [{
                        "uid": "101",
                        "name": "Alice",
                        "client_key": "client:a",
                    }],
                },
                "pt",
            )

        self.assertEqual(result["receipt"], "ok")
        self.assertEqual(site.sent[1]["profiles"][0]["marks"], {"1001": [1]})
        store.latest_collection_envelope.assert_called_once_with("101")

    def test_character_send_uses_saved_profile_and_canonical_payload(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_live(self, mode, payload, key):
                self.sent = (mode, payload, key)
                return {"receipt": "ok"}

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "capture.pcap"
            source.write_bytes(b"capture")
            database = root / "capture.sqlite3"
            store = CaptureStore(database)
            try:
                store.add_events(
                    source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                            "level": 68,
                        }},
                    }, {
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": 2,
                        "bundle_seq": 0,
                        "opcode": 0x0106,
                        "type": "player_profile_info",
                        "character_uid": "101",
                        "data": {"fields": {"active_equipment": {"slots": [{
                            "equip_part_type": 1,
                            "resolved": True,
                            "item": {"item_index": 1000078, "enchant_level": 7},
                        }]}}},
                    }],
                    "session",
                    client_ports=((50000,),),
                )
            finally:
                store.close()
            site = Site()
            result = SiteUploadEngine(database, site, License()).send_mode(
                "character",
                0,
                {
                    "session_id": "session",
                    "characters": [{
                        "uid": "101",
                        "name": "Alice",
                        "client_key": "client:a",
                        "include_unassigned": False,
                        "only_unassigned": False,
                    }],
                    "inventories": {"101": [{
                        "item_index": 270062,
                        "name": "Material",
                        "quantity": 25,
                        "kind": "stackable",
                        "slot": 7,
                        "refinement": 0,
                        "locked": False,
                        "expires_at": 0,
                        "item_uid_hex": "não-enviar",
                    }]},
                },
                "pt",
            )
            mode, payload, key = site.sent
            self.assertEqual((mode, result["receipt"]), ("character", "ok"))
            self.assertEqual(payload["profiles"][0]["character_uid"], "101")
            self.assertEqual(payload["profiles"][0]["loadout"]["equipment"], [
                {"item_index": 1000078, "slot": 1, "refinement": 7}
            ])
            self.assertEqual(payload["metadata"]["installation_id"], "install-1")
            self.assertEqual(payload["capture"]["inventory"], [{
                "item_index": 270062,
                "name": "Material",
                "quantity": 25,
                "kind": "stackable",
                "category": "other",
                "slot": 7,
                "refinement": 0,
                "locked": False,
                "expires_at": 0,
            }])
            self.assertNotIn("item_uid_hex", json.dumps(payload))
            self.assertEqual(len(key), 64)

    def test_subsession_send_recovers_character_from_saved_session(self):
        class Site:
            connected = True
            profile = "Profile"

            def upload_live(self, mode, payload, key):
                self.sent = (mode, payload, key)
                return {"receipt": "ok"}

        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started_ns = 1_780_000_000_000_000_000
            source = root / "capture.pcap"
            source.write_bytes(b"capture")
            database = root / "capture.sqlite3"
            store = CaptureStore(database)
            try:
                store.add_events(
                    source,
                    [{
                        "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                        "stream_offset": 1,
                        "bundle_seq": 0,
                        "ts_ns": started_ns + 100,
                        "opcode": 0x0106,
                        "type": "world_info_prefix",
                        "data": {"fields": {
                            "character_uid": 101,
                            "character_name": "Alice",
                            "level": 68,
                        }},
                    }],
                    "session",
                    client_ports=((50000,),),
                )
                store.start_subsession(
                    "sub-1",
                    "session",
                    "Farm",
                    character_uid="101",
                    client_key="client:a",
                    mobs=["Mob"],
                    mob_levels={"Mob": 68},
                    started_ns=started_ns,
                )
                store.end_subsession("sub-1", started_ns + 1_000_000_000)
            finally:
                store.close()

            site = Site()
            result = SiteUploadEngine(database, site, License()).send_subsessions(
                ["sub-1"], {"session_id": "session", "characters": []}, "pt"
            )

            self.assertEqual(result, {"sent": 1, "failures": []})
            self.assertEqual(site.sent[1]["profiles"][0]["name"], "Alice")
            store = CaptureStore(database, readonly=True)
            try:
                self.assertEqual(store.subsessions("session")[0]["upload_state"], "sent")
            finally:
                store.close()


class ExportEngineTest(unittest.TestCase):
    def test_denied_license_fails_before_creating_export_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "out"
            with self.assertRaises(PermissionError):
                ExportEngine(
                    root / "capture.sqlite3", _DeniedLicense()
                ).export("session", target, "Profile")
            self.assertFalse(target.exists())

    def test_export_writes_detected_equipment_to_json(self):
        class License(_AllowedLicense):
            installation_id = "install-1"
            lease = "lease-1"

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "capture.pcap"
            source.write_bytes(b"capture")
            database = root / "capture.sqlite3"
            store = CaptureStore(database)
            try:
                store.add_events(source, [{
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 1,
                    "bundle_seq": 0,
                    "opcode": 0x0106,
                    "type": "world_info_prefix",
                    "data": {"fields": {
                        "character_uid": 101,
                        "character_name": "Alice",
                        "level": 68,
                    }},
                }, {
                    "flow": "10.0.0.1:12020 -> 127.0.0.1:50000",
                    "stream_offset": 2,
                    "bundle_seq": 0,
                    "opcode": 0x0106,
                    "type": "player_profile_info",
                    "character_uid": "101",
                    "data": {"fields": {"active_equipment": {"slots": [{
                        "equip_part_type": 1,
                        "resolved": True,
                        "item": {"item_index": 1000078, "enchant_level": 7},
                    }]}}},
                }], "session", client_ports=((50000,),))
            finally:
                store.close()

            exported = ExportEngine(database, License()).export(
                "session", root / "out", "Profile", "pt"
            )
            result = exported["results"][0]
            payload = json.loads(result.json_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["profiles"][0]["loadout"]["equipment"], [
                {"item_index": 1000078, "slot": 1, "refinement": 7}
            ])
            self.assertEqual(
                result.sha256,
                hashlib.sha256(result.json_path.read_bytes()).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
