import base64
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.license import LicenseClient, verify_lease
from app.main import _capture_summary
from app.updater import UPDATE_SIGNATURE_CONTEXT, verify_manifest


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class AppLogicTest(unittest.TestCase):
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
            client._json = Mock(side_effect=urllib.error.HTTPError(
                "https://license", 401, "revogada", {}, None
            ))
            allowed, _ = client.refresh_if_due("1.0.0")
            self.assertFalse(allowed)
            client.state["installation_id"] = "outra-instalacao"
            with self.assertRaises(ValueError):
                client.claims()


if __name__ == "__main__":
    unittest.main()
