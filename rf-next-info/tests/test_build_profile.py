from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import build_profile
from app.license import LEASE_PUBLIC_KEYS, LicenseClient
from app.site_profile import SiteProfileClient


class BetaBuildProfileTest(unittest.TestCase):
    def test_profile_is_isolated_and_distributable(self):
        build_profile.validate_build_profile()
        build_profile.validate_build_profile(release=True)
        self.assertEqual(build_profile.PROFILE_NAME, "beta")
        self.assertEqual(build_profile.PROFILE_LABEL, "Beta")
        self.assertEqual(build_profile.PRODUCT_NAME, "RF Next Companion")
        self.assertEqual(build_profile.APP_VERSION, "2.0.0-beta.34")
        self.assertEqual(build_profile.RELEASE_SEQUENCE, 44)
        self.assertEqual(
            build_profile.LICENSE_SERVER, "https://rflicenca.karvalho.dev.br"
        )
        self.assertEqual(
            build_profile.SITE_SERVER, "https://rfnext.karvalho.dev.br"
        )
        self.assertEqual(
            build_profile.AGENT_SERVER, "https://apirf.karvalho.dev.br"
        )
        self.assertEqual(build_profile.AGENT_TRANSPORT_VERSION, "2.0.0-beta.6")
        self.assertEqual(build_profile.AGENT_UPDATE_CHANNEL, "beta")
        self.assertIn("download/rf-qol-agent-beta", build_profile.AGENT_UPDATE_FEED)
        self.assertEqual(
            set(build_profile.AGENT_UPDATE_PUBLIC_KEYS), {"update-agent-2026-08"}
        )
        self.assertNotEqual(build_profile.AGENT_SERVER, build_profile.SITE_SERVER)
        self.assertEqual(
            build_profile.SITE_FEATURES,
            {
                "character", "market", "codex", "memory_chips", "inventory",
                "subsession", "export", "observations", "pve-observations",
                "exp-ranking", "auction-bank", "pvp-sync",
            },
        )
        self.assertEqual(build_profile.MACHINE_STATE_NAME, "RF QOL Beta")
        self.assertEqual(build_profile.INSTANCE_SERVER_NAME, "RFQOL.Beta.App")
        with patch.object(build_profile, "PROFILE_NAME", "production"):
            with self.assertRaisesRegex(RuntimeError, "produção inconsistente"):
                build_profile.validate_build_profile(release=True)

    def test_license_client_uses_beta_key_and_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(Path(directory), version=build_profile.APP_VERSION)
            self.assertEqual(client.server, build_profile.LICENSE_SERVER)
            self.assertEqual(
                client.trusted_public_keys["lease-v3-beta-2026-08"],
                build_profile.LEASE_V3_PUBLIC_KEYS["lease-v3-beta-2026-08"],
            )
        self.assertIn("lease-2026-01", LEASE_PUBLIC_KEYS)
        self.assertIn("lease-v3-beta-2026-08", LEASE_PUBLIC_KEYS)

    def test_beta_opens_the_authorized_site_operations(self):
        with tempfile.TemporaryDirectory() as directory:
            client = SiteProfileClient(
                Path(directory),
                server=build_profile.SITE_SERVER,
                version=build_profile.APP_VERSION,
                features=build_profile.SITE_FEATURES,
            )
            with patch.object(
                client, "_request", return_value={"profile": "carvalho"}
            ):
                client.connect("carvalho", "t" * 32)
            with patch.object(
                client, "_request", return_value={"receipt": "market-1"}
            ) as request:
                result = client.upload_live(
                    "market",
                    {"metadata": {"profile": "carvalho"}, "rows": []},
                    "a" * 64,
                )
            self.assertEqual(result["receipt"], "market-1")
            self.assertTrue(request.call_args.args[0].endswith("/api/import/market"))
            with patch.object(
                client, "_request", return_value={"received_exp_rank": 1}
            ) as request:
                result = client.upload_exp_rank(
                    {"metadata": {}, "exp_rank": {"records": [{"rank": 1}]}},
                    "e" * 64,
                )
            self.assertEqual(result["received_exp_rank"], 1)
            self.assertTrue(request.call_args.args[0].endswith("/api/import/exp-rank"))
            with patch.object(
                client, "_request", return_value={"received_listings": 2}
            ) as request:
                result = client.upload_auction_bank(
                    {"metadata": {}, "listings": [{}, {}], "transactions": []},
                    "b" * 64,
                )
            self.assertEqual(result["received_listings"], 2)
            self.assertTrue(
                request.call_args.args[0].endswith("/api/import/auction-bank")
            )
            for feature in build_profile.SITE_FEATURES:
                self.assertTrue(client.allows(feature))

    def test_beta_build_emits_an_isolated_installer(self):
        build = (
            Path(__file__).resolve().parents[1] / "packaging" / "build.ps1"
        ).read_text(encoding="utf-8")
        agent_spec = (
            Path(__file__).resolve().parents[1]
            / "packaging" / "RFQOLAgent.spec"
        ).read_text(encoding="utf-8")
        installer = (
            Path(__file__).resolve().parents[1] / "packaging" / "installer.nsi"
        ).read_text(encoding="utf-8")
        self.assertIn("[switch]$Installer", build)
        self.assertIn("/DBETA_PROFILE", build)
        self.assertIn("RF QOL Setup $Version Beta.exe", build)
        self.assertIn("/DAPP_FILE_VERSION=$FileVersion", build)
        self.assertIn("validate_build_profile(release=True)", build)
        self.assertIn("build_profile = $BuildProfile", build)
        self.assertIn('"level_curve.json"', agent_spec)
        self.assertIn('"rf-next-companion.png"', agent_spec)
        self.assertIn('name="RF Next Companion"', agent_spec)
        self.assertIn('"icuuc.dll", "icudt78.dll"', agent_spec)
        self.assertIn('!define APP_REGKEY "Software\\Karvalho\\RFQOLBeta"', installer)
        self.assertIn('!define APP_INSTALLDIR "$PROGRAMFILES64\\Karvalho\\RF QOL Beta"', installer)
        self.assertIn('!define APP_SHORTCUT_NAME "RF QOL 2.0 Beta"', installer)


if __name__ == "__main__":
    unittest.main()
