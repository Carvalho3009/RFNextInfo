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
from app.main import App, _capture_prefix, _capture_summary
from app.support_log import LOGGER_NAME, configure, recent_lines
from app.updater import UPDATE_SIGNATURE_CONTEXT, download_verified, verify_manifest


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class AppLogicTest(unittest.TestCase):
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
            machine = LicenseClient(
                Path(directory) / "machine",
                legacy_paths=(Path(directory) / "license.json",),
            )
            self.assertEqual(machine.lease, lease)
            self.assertTrue((Path(directory) / "machine" / "license.json").is_file())
            (Path(directory) / "machine" / "license.json").write_text(
                "{corrompido", encoding="utf-8"
            )
            recovered = LicenseClient(Path(directory) / "machine")
            self.assertEqual(recovered.lease, lease)
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
