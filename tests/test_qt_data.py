import tempfile
import unittest
from pathlib import Path

from app.ui_qt.data import ReadOnlySnapshotReader, load_license_status


class QtReadOnlyDataTest(unittest.TestCase):
    def test_missing_state_is_empty_and_never_exposes_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = ReadOnlySnapshotReader(root / "missing.sqlite3").load()
            license_status = load_license_status(root / "local", root / "machine")

        self.assertIsNone(snapshot["session_id"])
        self.assertEqual(snapshot["characters"], [])
        self.assertFalse(license_status["active"])
        self.assertNotIn("lease", license_status)
        self.assertNotIn("public_key", license_status)


if __name__ == "__main__":
    unittest.main()
