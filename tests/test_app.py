import base64
import json
import logging
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.license import LicenseClient, _activation_error, verify_lease
from app.main import App, _capture_prefix, _capture_summary, _safe_error_code
from app.support_log import LOGGER_NAME, configure, recent_lines
from app.updater import UPDATE_SIGNATURE_CONTEXT, download_verified, verify_manifest


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class AppLogicTest(unittest.TestCase):
    def test_saved_license_check_updates_startup_ui(self):
        app = Mock()
        app._ingesting = False
        app._apply_license_status.side_effect = (
            lambda allowed, message: App._apply_license_status(
                app, allowed, message
            )
        )

        App._license_checked(app, (True, "Licença válida."), None)

        self.assertTrue(app.capture_allowed)
        app.license_state.configure.assert_called_with(
            text="Licença: Licença válida."
        )
        app.start_button.configure.assert_called_with(state="normal")

    def test_capture_uses_all_detected_ports_without_character_process_choice(self):
        app = Mock()
        app._refresh_license.return_value = (True, "Licença válida")
        app._decode_interval_seconds.return_value = 30
        app._ingesting = False
        app.capture.status.return_value.active = False
        app.profile.get.return_value = "Profile"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app._selected_game_path = r"C:\Games\ProjectRF.exe"
        app.prefs = {
            "session_counter": 2,
            "capture_pid_uids": {"10": "client:1"},
            "capture_port_uids": {"50100": "client:1"},
            "capture_character_names": {"client:1": "Alice"},
        }
        with patch(
            "app.main.ports_for_executable",
            return_value=((50100, 50200), (12010, 12020), 2),
        ), patch("app.main.RealtimeCapture"):
            App.start_capture(app)
        started_ports = app.capture.start_for_ports.call_args.args[1]
        self.assertEqual(started_ports, (50100, 50200, 12010, 12020))
        self.assertEqual(app._live_ports, started_ports)
        self.assertEqual(
            app.prefs["capture_decode_ports"],
            [12000, 12010, 12020, 12040],
        )
        self.assertNotIn("capture_pid_uids", app.prefs)
        self.assertNotIn("capture_port_uids", app.prefs)
        self.assertNotIn("capture_character_names", app.prefs)

    def test_empty_capture_is_safe_and_not_exportable(self):
        self.assertEqual(
            _safe_error_code(ValueError("PCAPNG sem pacotes utilizáveis")),
            "empty_capture",
        )
        app = Mock()
        app.current_session = "session-1"
        app.store.session_stats.return_value = {
            "recognized": 0,
            "unknown": 0,
        }
        self.assertFalse(App._session_has_data(app))
        app.store.session_stats.return_value["unknown"] = 1
        self.assertTrue(App._session_has_data(app))

    def test_stop_capture_is_idempotent_while_ingesting(self):
        app = Mock()
        app._ingesting = True
        App.stop_capture(app)
        app.capture.stop.assert_not_called()

    def test_empty_capture_stays_pending_for_reanalysis(self):
        class EmptyStore:
            def __init__(self, _path):
                pass

            def ingest(self, *_args, **_kwargs):
                raise ValueError("PCAPNG sem pacotes utilizáveis")

            def remove_sources(self, _sources):
                pass

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "empty.etl"
            raw.write_bytes(b"metadata")
            app = Mock()
            app._ingesting = False
            app.current_session = "session-1"
            app.capture.attached = True
            app.capture.stop.return_value.files = (raw,)
            app.prefs = {
                "capture_pending": True,
                "capture_decode_ports": [12010, 12020],
            }
            app.capture_allowed = True
            app._live_files = []
            app.auto_export.get.return_value = False
            app._ingest_lock = threading.Lock()
            app._ingest_files.side_effect = (
                lambda files, session_id, ports, **kwargs: App._ingest_files(
                    app, files, session_id, ports, **kwargs
                )
            )
            app._run.side_effect = lambda job, done: done(job(), None)
            with patch("app.main.CaptureStore", EmptyStore):
                App.stop_capture(app)
            self.assertTrue(app.prefs["capture_pending"])
            self.assertFalse(app._ingesting)
            self.assertIn(
                "arquivos preservados",
                app.capture_state.configure.call_args.kwargs["text"],
            )

    def test_live_decode_rotates_preview_without_stopping_primary_capture(self):
        app = Mock()
        app._ingesting = False
        app._live_ingesting = False
        app.current_session = "session-1"
        app._next_live_decode = 0
        app._decode_interval_seconds.return_value = 30
        app.prefs = {
            "capture_decode_ports": [12010, 12020],
            "capture_ports": [50100],
        }
        preview = Path("preview-1.pcap")
        app._live_capture = Mock()
        app._close_live_preview.return_value = preview
        app._open_live_preview.return_value = None
        app._run.side_effect = lambda job, done: done((4, [], 0), None)

        with patch.object(Path, "stat") as stat:
            stat.return_value.st_size = 100
            App._maybe_decode_live(app)

        files = app._run.call_args.args[0]()
        self.assertEqual(files, app._ingest_files.return_value)
        app._ingest_files.assert_called_with(
            (preview,), "session-1", (12010, 12020, 50100)
        )
        app.capture.stop.assert_not_called()
        self.assertFalse(app._live_ingesting)
        app._refresh_info.assert_called_once()

    @patch("app.main.messagebox.showwarning")
    def test_export_waits_for_complete_capture(self, warning):
        app = Mock()
        app.capture.status.return_value.active = True

        App.export(app)

        warning.assert_called_once()
        app.store.latest_session.assert_not_called()

    def test_two_names_without_uid_export_as_reviewable_combined_file(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {}
        app.store.session_profiles.return_value = []
        app.store.session_stats.return_value = {"unassigned": 10}
        exports = App._character_exports(app)
        self.assertEqual(len(exports), 1)
        self.assertEqual(exports[0]["uid"], None)
        self.assertEqual(exports[0]["identification_status"], "unresolved")
        self.assertIn("Nao-separado", exports[0]["name"])
        self.assertTrue(exports[0]["warning"])

    def test_old_process_ids_are_not_used_as_character_identity(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {
            "capture_character_names": {
                "client:1": "Alice",
                "client:2": "Bob",
            }
        }
        app.store.session_profiles.return_value = [
            {"uid": "client:1", "name": ""},
            {"uid": "client:2", "name": ""},
        ]
        app.store.session_stats.return_value = {"unassigned": 0}
        exports = App._character_exports(app, prompt_exp=True)
        self.assertEqual(len(exports), 1)
        self.assertEqual(exports[0]["identification_status"], "unresolved")
        self.assertIsNone(exports[0]["uid"])
        app.store.unidentified_exp_flows.assert_not_called()

    def test_export_matches_two_names_to_closest_exp(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {}
        app.store.session_profiles.side_effect = [
            [],
            [
                {"uid": "exp:1", "name": ""},
                {"uid": "exp:2", "name": ""},
            ],
        ]
        app.store.unidentified_exp_flows.return_value = [
            {"flow": "a", "exp_percent": 80.0},
            {"flow": "b", "exp_percent": 10.0},
        ]
        app.store.assign_unidentified_by_exp.return_value = [
            {"uid": "exp:1", "name": "Alice"},
            {"uid": "exp:2", "name": "Bob"},
        ]
        app.store.session_stats.return_value = {"unassigned": 0}
        with patch(
            "app.main.simpledialog.askfloat", side_effect=[75.0, 12.0]
        ):
            exports = App._character_exports(app, prompt_exp=True)
        app.store.assign_unidentified_by_exp.assert_called_once_with(
            "session-1", [("Alice", 75.0), ("Bob", 12.0)]
        )
        self.assertEqual(
            [(item["name"], item["identification_status"]) for item in exports],
            [("Alice", "exp_matched"), ("Bob", "exp_matched")],
        )

    def test_export_prompts_exp_for_unassigned_events_with_one_uid(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = ""
        app.prefs = {}
        app.store.session_profiles.return_value = [
            {"uid": "101", "name": "Alice"}
        ]
        app.store.unidentified_exp_flows.return_value = [
            {"flow": "missing", "exp_percent": 61.0}
        ]
        app.store.session_stats.return_value = {"unassigned": 0}
        with patch("app.main.simpledialog.askfloat", return_value=60.5):
            exports = App._character_exports(app, prompt_exp=True)
        app.store.assign_unidentified_to_uid_by_exp.assert_called_once_with(
            "session-1", "101", 60.5
        )
        self.assertIsNone(exports[0]["warning"])

    def test_update_launch_closes_current_app(self):
        app = Mock()
        app.capture.attached = False
        app.tray = None
        with patch("app.main.messagebox.askyesno", return_value=True), patch(
            "app.main.os.startfile"
        ) as launch:
            App._update_downloaded(app, Path("setup.exe"), None)
        launch.assert_called_once_with(Path("setup.exe"))
        app.store.close.assert_called_once()
        app.destroy.assert_called_once()

    def test_verified_download_reports_progress(self):
        private = Ed25519PrivateKey.generate()
        public = b64(private.public_key().public_bytes_raw())
        installer = b"instalador-verificado" * 100
        name = "RFNextInfo-Test-Progress.exe"
        manifest = {
            "version": "test",
            "file": name,
            "sha256": __import__("hashlib").sha256(installer).hexdigest(),
        }
        canonical = json.dumps(
            manifest, separators=(",", ":"), sort_keys=True
        ).encode()
        manifest["signature"] = b64(
            private.sign(UPDATE_SIGNATURE_CONTEXT + canonical)
        )

        class Response(BytesIO):
            def __init__(self, body: bytes):
                super().__init__(body)
                self.headers = {"Content-Length": str(len(body))}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        release = {
            "assets": [
                {
                    "name": "update-manifest.json",
                    "browser_download_url": "https://example/manifest",
                },
                {
                    "name": name,
                    "browser_download_url": "https://example/installer",
                },
            ]
        }
        progress = []
        target = Path(tempfile.gettempdir()) / name
        target.unlink(missing_ok=True)
        try:
            with patch.object(
                urllib.request,
                "urlopen",
                side_effect=[
                    Response(json.dumps(manifest).encode()),
                    Response(installer),
                ],
            ):
                self.assertEqual(
                    download_verified(
                        release,
                        public,
                        lambda phase, done, total: progress.append(
                            (phase, done, total)
                        ),
                    ),
                    target,
                )
            self.assertEqual(target.read_bytes(), installer)
            self.assertEqual(progress[0][0], "manifest")
            self.assertEqual(progress[-1], ("verify", len(installer), len(installer)))
        finally:
            target.unlink(missing_ok=True)

    def test_activation_diagnostics_and_local_format_check(self):
        error = urllib.error.HTTPError(
            "https://license", 403, "Forbidden", {"CF-Ray": "ray-test"}, BytesIO(
                b'{"detail":"licenca invalida"}'
            )
        )
        self.assertEqual(
            _activation_error(error), "licenca invalida (HTTP 403, CF-Ray ray-test)"
        )
        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(Path(directory), version="test")
            client._json = Mock()
            with self.assertRaisesRegex(ValueError, "Formato inválido"):
                client.activate("sem-hifens", "test")
            client._json.assert_not_called()

    def test_async_error_reaches_callback(self):
        completed = threading.Event()
        observed = []

        class Scheduler:
            def after(self, _delay, callback):
                callback()

        def fail():
            raise RuntimeError("falhou")

        App._run(Scheduler(), fail, lambda result, error: (
            observed.append((result, str(error))), completed.set()
        ))
        self.assertTrue(completed.wait(1))
        self.assertEqual(observed, [(None, "falhou")])
        self.assertEqual(
            _capture_prefix("Profile-20260728-010203-007"),
            "rfnext-20260728-010203-007",
        )

    def test_support_log_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rfnext-info.log"
            logger = configure(path, "test")
            try:
                logger.error(
                    "KRV-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA "
                    "carvalho@tuta.com 192.168.0.10 "
                    r"C:\Users\Carlos\Documents "
                    "123e4567-e89b-12d3-a456-426614174000"
                )
                try:
                    raise RuntimeError("PersonagemSecreto")
                except RuntimeError:
                    logger.exception("operation_failed")
                lines = "\n".join(recent_lines(path))
                self.assertRegex(
                    lines.splitlines()[0],
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} ",
                )
                self.assertNotIn("KRV-AAAAA", lines)
                self.assertNotIn("carvalho@tuta.com", lines)
                self.assertNotIn("192.168.0.10", lines)
                self.assertNotIn(r"C:\Users\Carlos", lines)
                self.assertNotIn("123e4567-e89b-12d3-a456-426614174000", lines)
                self.assertNotIn("PersonagemSecreto", lines)
                self.assertIn("<LICENCA>", lines)
            finally:
                for handler in list(logging.getLogger(LOGGER_NAME).handlers):
                    logging.getLogger(LOGGER_NAME).removeHandler(handler)
                    handler.close()

    def test_signed_lease_and_site_profile(self):
        private = Ed25519PrivateKey.generate()
        claims = {
            "v": 1,
            "iss": "rflicenca.karvalho.dev.br",
            "license_id": "license-1",
            "installation_id": "install-1",
            "issued_at": "2026-07-27T00:00:00Z",
            "license_starts_at": "2026-07-01T00:00:00Z",
            "license_expires_at": "2999-12-31T00:00:00Z",
            "next_check_at": "2000-01-01T00:00:00Z",
            "valid_until": "2999-01-01T00:00:00Z",
        }
        payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
        lease = f"{b64(payload)}.{b64(private.sign(payload))}"
        public = b64(private.public_key().public_bytes_raw())
        self.assertEqual(verify_lease(lease, public)["installation_id"], "install-1")

        summary, marks = _capture_summary({"events": [{
            "type": "collection_snapshot_chunk",
            "data": {
                "fields": {"character_name": "Carvalho", "level": 66, "exp": 12.5},
                "records": [{"collection_index": 1001, "completed_slots": [0, 2]}],
            },
        }]})
        self.assertEqual(summary["character"], "Carvalho")
        self.assertEqual(marks, {"1001": [1, 3]})

        manifest = {"version": "1.0.1", "file": "setup.exe", "sha256": "a" * 64}
        canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
        manifest["signature"] = b64(private.sign(UPDATE_SIGNATURE_CONTEXT + canonical))
        self.assertEqual(verify_manifest(manifest, public)["version"], "1.0.1")

        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(Path(directory))
            client.state.update(lease=lease, public_key=public, installation_id="install-1")
            client._save()
            remembered = LicenseClient(Path(directory))
            self.assertEqual(remembered.lease, lease)
            self.assertEqual(remembered.installation_id, "install-1")
            self.assertEqual(
                remembered.state["license_expires_at"],
                "2999-12-31T00:00:00Z",
            )
            self.assertNotIn(
                lease.encode(), (Path(directory) / "license.dat").read_bytes()
            )
            legacy = Path(directory) / "legacy-license.json"
            legacy.write_text(
                json.dumps(client.state), encoding="utf-8"
            )
            machine = LicenseClient(
                Path(directory) / "machine",
                legacy_paths=(legacy,),
            )
            self.assertEqual(machine.lease, lease)
            self.assertFalse(legacy.exists())
            protected = Path(directory) / "machine" / "license.dat"
            self.assertTrue(protected.is_file())
            local = LicenseClient(
                Path(directory) / "local",
                legacy_paths=(protected,),
            )
            self.assertEqual(local.lease, lease)
            self.assertEqual(local.load_status, "migrated")
            self.assertEqual(
                LicenseClient(Path(directory) / "local").lease,
                lease,
            )
            protected.write_bytes(
                protected.read_bytes()[:-1] + b"\0"
            )
            recovered = LicenseClient(Path(directory) / "machine")
            self.assertEqual(recovered.lease, lease)
            self.assertEqual(recovered.load_status, "backup")
            client._json = Mock(side_effect=urllib.error.HTTPError(
                "https://license", 401, "revogada", {}, None
            ))
            allowed, _ = client.refresh_if_due("1.0.0")
            self.assertFalse(allowed)
            client.state["installation_id"] = "outra-instalacao"
            with self.assertRaises(ValueError):
                client.claims()

            diagnostic = Path(directory) / "diagnostic.json"
            diagnostic.write_text(
                json.dumps(
                    {
                        "privacy": "sem payload",
                        "events": [{"opcode": "0x7777", "decoded_size": 12}],
                    }
                ),
                encoding="utf-8",
            )
            remembered._json = Mock(return_value={"receipt": "test-1"})
            self.assertEqual(
                remembered.upload_diagnostic(diagnostic, "1.0.0")["receipt"],
                "test-1",
            )


if __name__ == "__main__":
    unittest.main()
