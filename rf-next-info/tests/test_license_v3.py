from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import license as license_module
from app.license import FEATURE_ORDER, LicenseClient, verify_lease


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


def signed_lease(
    private: Ed25519PrivateKey,
    *,
    version: int,
    key_id: str,
    installation_id: str,
    now: datetime,
    features: list[str],
) -> tuple[str, dict]:
    issued = now - timedelta(minutes=1)
    claims = {
        "v": version,
        "iss": "rflicenca.karvalho.dev.br",
        "product": "rf-qol",
        "aud": "rf-qol-windows",
        "key_id": key_id,
        "lease_id": str(uuid.uuid4()),
        "license_id": "license-test",
        "installation_id": installation_id,
        "issued_at": issued.isoformat(),
        "valid_until": (
            issued + (timedelta(days=7) if version == 3 else timedelta(hours=24))
        ).isoformat(),
        "entitlement_expires_at": (now + timedelta(days=30)).isoformat(),
        "features": features,
    }
    if version == 2:
        claims["next_check_at"] = (issued + timedelta(hours=6)).isoformat()
        claims["connection_limits"] = {"pc": 2, "emulators": 1}
    raw = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
    return f"{b64(raw)}.{b64(private.sign(raw))}", claims


class LicenseV3Test(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.installation_id = str(uuid.uuid4())
        self.v2_private = Ed25519PrivateKey.generate()
        self.v3_private = Ed25519PrivateKey.generate()
        self.public_keys = {
            "lease-v2-test": b64(self.v2_private.public_key().public_bytes_raw()),
            "lease-v3-test": b64(self.v3_private.public_key().public_bytes_raw()),
        }

    def test_release_gate_requires_a_definitive_v3_public_key(self):
        with patch.dict(
            license_module.LEASE_PUBLIC_KEYS,
            {"lease-2026-01": self.public_keys["lease-v2-test"]},
            clear=True,
        ):
            license_module.validate_release_configuration()
            with self.assertRaises(RuntimeError):
                license_module.validate_release_configuration(require_v3=True)
        with patch.dict(
            license_module.LEASE_PUBLIC_KEYS,
            {
                "lease-2026-01": self.public_keys["lease-v2-test"],
                "lease-v3-2026-01": self.public_keys["lease-v3-test"],
            },
            clear=True,
        ):
            license_module.validate_release_configuration(require_v3=True)

    def test_v3_contract_has_seven_day_window_and_no_legacy_claims(self):
        lease, claims = signed_lease(
            self.v3_private,
            version=3,
            key_id="lease-v3-test",
            installation_id=self.installation_id,
            now=self.now,
            features=list(FEATURE_ORDER),
        )
        verified = verify_lease(
            lease,
            self.public_keys,
            installation_id=self.installation_id,
            now=self.now,
        )
        self.assertEqual(verified, claims)
        self.assertNotIn("next_check_at", verified)
        self.assertNotIn("connection_limits", verified)

        for invalid in (
            dict(claims, next_check_at=claims["valid_until"]),
            dict(claims, connection_limits={"pc": 2, "emulators": 5}),
            dict(claims, features=["base", "unknown"]),
            dict(claims, features=["map", "base"]),
            dict(claims, features=["base", "base"]),
        ):
            raw = json.dumps(invalid, separators=(",", ":"), sort_keys=True).encode()
            with self.assertRaises(ValueError):
                verify_lease(
                    f"{b64(raw)}.{b64(self.v3_private.sign(raw))}",
                    self.public_keys,
                    now=self.now,
                )

        too_long = dict(claims)
        too_long["valid_until"] = (
            datetime.fromisoformat(claims["issued_at"]) + timedelta(days=7, seconds=1)
        ).isoformat()
        too_long["entitlement_expires_at"] = too_long["valid_until"]
        raw = json.dumps(too_long, separators=(",", ":"), sort_keys=True).encode()
        with self.assertRaises(ValueError):
            verify_lease(
                f"{b64(raw)}.{b64(self.v3_private.sign(raw))}",
                self.public_keys,
                now=self.now,
            )

    def test_startup_migrates_v2_to_v3_once_and_removes_quotas(self):
        legacy, _ = signed_lease(
            self.v2_private,
            version=2,
            key_id="lease-v2-test",
            installation_id=self.installation_id,
            now=self.now,
            features=["base", "monitor-pvp"],
        )
        renewed, renewed_claims = signed_lease(
            self.v3_private,
            version=3,
            key_id="lease-v3-test",
            installation_id=self.installation_id,
            now=self.now,
            features=list(FEATURE_ORDER),
        )
        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(
                Path(directory), trusted_public_keys=self.public_keys
            )
            client.state.update(
                installation_id=self.installation_id,
                lease=legacy,
            )
            client._save()
            client._json = Mock(return_value={"lease": renewed})

            allowed, _ = client.refresh_if_due("2.0.0")
            self.assertTrue(allowed)
            self.assertEqual(client.claims()["v"], 3)
            self.assertEqual(client.local_status()["connection_limits"], {})
            self.assertIsNone(client.local_status()["next_check_at"])
            self.assertEqual(client.local_status()["features"], list(FEATURE_ORDER))
            self.assertEqual(client.state["license_version"], 3)
            client._json.assert_called_once()
            path, payload = client._json.call_args.args
            self.assertEqual(path, "/api/v3/validate")
            self.assertEqual(payload["lease"], legacy)

            self.assertTrue(client.refresh_if_due("2.0.0")[0])
            client._json.assert_called_once()
            self.assertTrue(client.refresh_if_due("2.0.0", force=True)[0])
            self.assertEqual(client._json.call_count, 2)
            self.assertEqual(client.claims()["lease_id"], renewed_claims["lease_id"])

    def test_network_failure_preserves_signed_window_but_revocation_clears_it(self):
        lease, _ = signed_lease(
            self.v3_private,
            version=3,
            key_id="lease-v3-test",
            installation_id=self.installation_id,
            now=self.now,
            features=["base", "map"],
        )
        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(
                Path(directory), trusted_public_keys=self.public_keys
            )
            client.state.update(
                installation_id=self.installation_id,
                lease=lease,
            )
            client._save()
            client._json = Mock(side_effect=urllib.error.URLError("offline"))
            allowed, message = client.refresh_if_due("2.0.0")
            self.assertTrue(allowed)
            self.assertIn("prazo offline", message)
            self.assertEqual(client.lease, lease)

            client._json = Mock(
                side_effect=urllib.error.HTTPError(
                    "https://license", 403, "revogada", {}, None
                )
            )
            allowed, _ = client.refresh_if_due("2.0.0", force=True)
            self.assertFalse(allowed)
            self.assertIsNone(client.lease)
            self.assertEqual(client.license_state(), "REVOKED")


if __name__ == "__main__":
    unittest.main()
