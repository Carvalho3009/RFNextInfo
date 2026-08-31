from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from core.agent_updates import (
    UpdateCandidate,
    download_verified,
    fetch_latest,
    verify_manifest,
)
from tools import agent_update_key, sign_agent_update_manifest


KEY_ID = "update-agent-test"
DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/"
    "download/rf-qol-agent-test/RF-QOL-Agent-Setup-2.0.0-beta.22.exe"
)
FEED_URL = (
    "https://raw.githubusercontent.com/Carvalho3009/RFNextInfo/"
    "download/rf-qol-agent-beta/latest.json"
)


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class _Response:
    def __init__(self, payload: bytes, url: str, *, length: bool = True):
        self._stream = io.BytesIO(payload)
        self._url = url
        self.headers = {"Content-Length": str(len(payload))} if length else {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)

    def geturl(self) -> str:
        return self._url


class AgentUpdateTest(unittest.TestCase):
    def _signed_manifest(self, root: Path):
        installer = root / "RF-QOL-Agent-Setup-2.0.0-beta.22.exe"
        installer.write_bytes(b"agent-installer-content")
        private = Ed25519PrivateKey.generate()
        with mock.patch.object(
            sign_agent_update_manifest, "load_private_key", return_value=private
        ):
            manifest = sign_agent_update_manifest.create_manifest(
                installer,
                version="2.0.0-beta.22",
                release_sequence=32,
                key_id=KEY_ID,
                private_key=root / "unused-private-key",
                download_url=DOWNLOAD_URL,
                channel="beta",
                rollback_compatible_from=["2.0.0-beta.21"],
                now=datetime(2026, 8, 27, tzinfo=timezone.utc),
            )
        public = _b64(private.public_key().public_bytes_raw())
        return installer, manifest, {KEY_ID: public}

    def test_signed_manifest_is_verified_and_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            _installer, manifest, public = self._signed_manifest(Path(folder))
            verified = verify_manifest(
                manifest,
                public,
                channel="beta",
                now=datetime(2026, 8, 28, tzinfo=timezone.utc),
            )
            self.assertEqual(verified["release_sequence"], 32)
            tampered = dict(manifest, size=manifest["size"] + 1)
            with self.assertRaisesRegex(ValueError, "Manifesto"):
                verify_manifest(
                    tampered,
                    public,
                    channel="beta",
                    now=datetime(2026, 8, 28, tzinfo=timezone.utc),
                )

    def test_feed_ignores_current_sequence_and_accepts_newer(self):
        with tempfile.TemporaryDirectory() as folder:
            _installer, manifest, public = self._signed_manifest(Path(folder))
            raw = json.dumps(manifest).encode()
            opener = lambda _request, timeout: _Response(raw, FEED_URL)
            with mock.patch(
                "core.agent_updates.datetime",
                wraps=datetime,
            ) as clock:
                clock.now.return_value = datetime(2026, 8, 28, tzinfo=timezone.utc)
                self.assertIsNone(fetch_latest(
                    FEED_URL, public, channel="beta", current_sequence=32,
                    opener=opener,
                ))
                candidate = fetch_latest(
                    FEED_URL, public, channel="beta", current_sequence=31,
                    opener=opener,
                )
            self.assertEqual(candidate.release_sequence, 32)

    def test_download_is_atomic_and_hash_verified(self):
        with tempfile.TemporaryDirectory() as folder:
            installer, manifest, _public = self._signed_manifest(Path(folder))
            payload = installer.read_bytes()
            candidate = UpdateCandidate(
                version=manifest["version"],
                release_sequence=manifest["release_sequence"],
                installer=None,
                manifest=manifest,
            )
            output = Path(folder) / "downloads"
            downloaded = download_verified(
                candidate,
                output,
                opener=lambda _request, timeout: _Response(payload, DOWNLOAD_URL),
            )
            self.assertEqual(downloaded.installer.read_bytes(), payload)
            self.assertFalse(list(output.glob("*.part")))

    def test_update_key_file_requires_dpapi_and_matching_public_key(self):
        private = Ed25519PrivateKey.generate()
        protected = b"protected-private"
        record = {
            "schema": agent_update_key.KEY_SCHEMA,
            "key_id": KEY_ID,
            "protection": "windows-dpapi-current-user",
            "private_key": _b64(protected),
            "public_key": _b64(private.public_key().public_bytes_raw()),
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "key.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            with mock.patch.object(
                agent_update_key, "unprotect", return_value=private.private_bytes_raw()
            ):
                restored = agent_update_key.load_private_key(path)
            self.assertEqual(
                restored.public_key().public_bytes_raw(),
                private.public_key().public_bytes_raw(),
            )


if __name__ == "__main__":
    unittest.main()
