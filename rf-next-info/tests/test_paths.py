import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.paths as paths


class RuntimePathsTest(unittest.TestCase):
    def test_runtime_layout_is_clean_and_does_not_migrate_old_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            install = root / "install"
            legacy_user = root / "legacy-user"
            legacy_machine = root / "legacy-machine"
            legacy_user.mkdir()
            legacy_machine.mkdir()
            (legacy_user / "preferences.json").write_text(
                '{"capture_directory":"D:/Capturas"}', encoding="utf-8"
            )
            (legacy_user / "license.dat").write_bytes(b"protected-license")
            (legacy_machine / "site-profile.dat").write_bytes(b"protected-token")

            state = install / "data"
            database = install / "database"
            logs = install / "logs"
            cache = install / "cache"
            updates = install / "updates"
            machine = install / "machine-data"
            captures = install / "Capturas"
            with (
                patch.object(paths, "STATE_DIR", state),
                patch.object(paths, "MACHINE_STATE_DIR", machine),
                patch.object(paths, "DATABASE_DIR", database),
                patch.object(paths, "LOG_DIR", logs),
                patch.object(paths, "CACHE_DIR", cache),
                patch.object(paths, "UPDATES_DIR", updates),
                patch.object(paths, "CAPTURE_DIR", captures),
                patch.object(paths, "PREFERENCES_PATH", state / "preferences.json"),
                patch.object(paths, "DB_PATH", database / "capture.sqlite3"),
                patch.object(
                    paths,
                    "RUNTIME_DIRS",
                    (state, machine, database, logs, cache, updates, captures),
                ),
            ):
                migrated = paths.ensure_runtime_layout()

            self.assertEqual(migrated, ())
            self.assertTrue(all(path.is_dir() for path in (
                state, machine, database, logs, cache, updates, captures
            )))
            self.assertFalse((state / "preferences.json").exists())
            self.assertFalse((machine / "license.dat").exists())
            self.assertTrue((legacy_user / "preferences.json").exists())
            self.assertTrue((legacy_user / "license.dat").exists())
            self.assertTrue((legacy_machine / "site-profile.dat").exists())

    def test_installers_keep_machine_trust_state_outside_user_appdata(self):
        root = Path(__file__).resolve().parents[1]
        installer_text = "\n".join(
            (root / "packaging" / name).read_text(encoding="utf-8")
            for name in ("installer.iss", "installer.nsi")
        ).lower()
        self.assertIn("{commonappdata}\\karvalho\\rf qol", installer_text)
        self.assertIn("setshellvarcontext all", installer_text)
        self.assertIn("$appdata\\karvalho\\rf qol", installer_text)
        self.assertNotIn(
            'name: "{app}\\updates"; permissions: users-modify', installer_text
        )
        self.assertIn("{app}\\logs\\install.log", installer_text)
        self.assertIn("$instdir\\logs\\install.log", installer_text)

    def test_nsis_installer_has_isolated_non_admin_smoke_mode(self):
        root = Path(__file__).resolve().parents[1]
        installer = (root / "packaging" / "installer.nsi").read_text(
            encoding="utf-8"
        ).lower()
        smoke = (root / "packaging" / "test-installer.ps1").read_text(
            encoding="utf-8"
        ).lower()
        self.assertIn("dev_smoke", installer)
        self.assertIn("requestexecutionlevel user", installer)
        self.assertIn("/ddev_smoke", smoke)
        self.assertIn("self_test=0", smoke)
        self.assertIn("uninstall.exe", smoke)
        self.assertIn("execshellwait", installer)
        self.assertIn("self-test.ok", installer)

    def test_nsis_installer_requires_terms_acceptance(self):
        root = Path(__file__).resolve().parents[1]
        installer = (root / "packaging" / "installer.nsi").read_text(
            encoding="utf-8"
        )
        terms = (root / "docs" / "TERMOS-DE-USO-RF-QOL-1.0.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("MUI_LICENSEPAGE_CHECKBOX", installer)
        self.assertIn("Li e aceito os Termos de Uso", installer)
        self.assertIn("MUI_PAGE_LICENSE", installer)
        self.assertIn("TERMOS-DE-USO-RF-QOL-1.0.txt", installer)
        self.assertIn("Versão dos Termos: 1.0", terms)
        self.assertIn("Contato: carvalho@tuta.com", terms)

    def test_release_build_supports_manual_hash_and_future_signed_bundle(self):
        root = Path(__file__).resolve().parents[1]
        build = (root / "packaging" / "build.ps1").read_text(
            encoding="utf-8"
        )
        for field in (
            "from app.main import VERSION",
            "from app.main import RELEASE_SEQUENCE",
            "from app.updater import UPDATE_MODE",
            "SHA256SUMS.txt",
            "update_mode = $UpdateMode",
            "$UpdateMode -eq 'automatic'",
            "RFQOL_ROLLBACK_INSTALLER",
            "RFQOL_ROLLBACK_VERSION",
            "RFQOL_ROLLBACK_SEQUENCE",
            "rollback-manifest.json",
            "rollback_manifest_sha256",
            "Release posterior à inicial exige o bundle completo de rollback.",
        ):
            self.assertIn(field, build)


if __name__ == "__main__":
    unittest.main()
