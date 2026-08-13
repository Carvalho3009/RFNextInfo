import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from app.ui_qt.operations import (
    CaptureEngine,
    ExportEngine,
    GlobalHotkeys,
    MonitorEngine,
    SiteUploadEngine,
    _site_loot_rows,
)
from app.ui_qt.data import ReadOnlySnapshotReader
from core.capture import CaptureStatus
from core.knowledge import KnowledgeStore
from core.store import CaptureStore


class _FakeCapture:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.active = False
        self.heartbeats = 0
        self.files = ()
        self.added_ports = []

    def start_for_ports(self, prefix: str, _ports: tuple[int, ...]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{prefix}-001.etl"
        path.write_bytes(b"etl")
        self.files = (path,)
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


class CaptureEngineTest(unittest.TestCase):
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

    def test_tier_one_rejects_second_emulator_before_capture_starts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
            )

            with self.assertRaisesRegex(PermissionError, "1 emuladores"):
                engine.start()
            self.assertFalse(list(root.glob("*.etl")))

    def test_tier_one_rejects_second_emulator_before_monitor_starts(self):
        monitor = MonitorEngine(
            _TierOneLicense(),
            live_factory=_MemoryLive,
            process_reader=lambda _ports: {},
            emulator_reader=lambda _ports: {
                r"C:\BlueStacks\HD-Player.exe": (
                    {30, 40}, {57001, 57002}, {12020}
                )
            },
        )

        with self.assertRaisesRegex(PermissionError, "1 emuladores"):
            monitor.start(("monitor-pve",))
        self.assertFalse(monitor.active)

    def test_tier_one_ignores_later_excess_without_stopping_capture(self):
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

            with self.assertRaisesRegex(PermissionError, "1 emuladores"):
                engine.preview_live()
            self.assertTrue(engine.active)
            self.assertNotIn(57002, engine.capture.added_ports)
            engine.stop_without_reading()

    def test_capture_rejects_more_than_five_emulators(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
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
            )

            with self.assertRaisesRegex(PermissionError, "5 emuladores"):
                engine.start()

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

    def test_live_read_refreshes_rotated_client_ports(self):
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
            self.assertIn(50001, engine.capture.added_ports)

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
            "data": {"units": [{"character_uid": 123, "name": "Local"}]},
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
        self.assertEqual(sent["sent_mobs"], 0)
        self.assertEqual(site.uploaded[0]["mobs"], [])
        self.assertEqual(len(pending_mobs), 1)
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
