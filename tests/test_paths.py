import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app.paths as paths


class RuntimePathsTest(unittest.TestCase):
    def test_runtime_layout_is_install_local_and_migrates_without_deleting(self):
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
            captures = install / "Capturas"
            with (
                patch.object(paths, "STATE_DIR", state),
                patch.object(paths, "DATABASE_DIR", database),
                patch.object(paths, "LOG_DIR", logs),
                patch.object(paths, "CACHE_DIR", cache),
                patch.object(paths, "UPDATES_DIR", updates),
                patch.object(paths, "CAPTURE_DIR", captures),
                patch.object(paths, "PREFERENCES_PATH", state / "preferences.json"),
                patch.object(paths, "DB_PATH", database / "capture.sqlite3"),
                patch.object(paths, "LEGACY_USER_STATE_DIR", legacy_user),
                patch.object(paths, "LEGACY_MACHINE_STATE_DIR", legacy_machine),
                patch.object(
                    paths,
                    "RUNTIME_DIRS",
                    (state, database, logs, cache, updates, captures),
                ),
            ):
                migrated = paths.ensure_runtime_layout()

            self.assertIn(legacy_user / "preferences.json", migrated)
            self.assertEqual(
                (state / "preferences.json").read_bytes(),
                (legacy_user / "preferences.json").read_bytes(),
            )
            self.assertEqual(
                (state / "license.dat").read_bytes(),
                (legacy_user / "license.dat").read_bytes(),
            )
            self.assertTrue((legacy_user / "preferences.json").exists())
            self.assertTrue((legacy_user / "license.dat").exists())
            self.assertTrue((legacy_machine / "site-profile.dat").exists())

    def test_installers_do_not_write_app_state_to_appdata(self):
        root = Path(__file__).resolve().parents[1]
        installer_text = "\n".join(
            (root / "packaging" / name).read_text(encoding="utf-8")
            for name in ("installer.iss", "installer.nsi")
        ).lower()
        self.assertNotIn("commonappdata", installer_text)
        self.assertNotIn("$appdata", installer_text)
        self.assertIn("{app}\\logs\\install.log", installer_text)
        self.assertIn("$instdir\\logs\\install.log", installer_text)


if __name__ == "__main__":
    unittest.main()
