from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from app.agent_preferences import (
    AGENT_STARTUP_VALUE,
    agent_startup_command,
    configure_agent_startup,
    load_agent_preferences,
    normalize_agent_preferences,
    save_agent_preferences,
)


class AgentPreferencesTest(unittest.TestCase):
    def test_defaults_are_manual_and_do_not_start_with_windows(self):
        preferences = normalize_agent_preferences({})

        self.assertFalse(preferences["start_with_windows"])
        self.assertFalse(preferences["auto_capture"])
        self.assertEqual(preferences["memory_limit_mb"], 1024)
        self.assertEqual(preferences["storage_limit_mb"], 512)
        uuid.UUID(preferences["installation_id"])

    def test_values_are_normalized_and_saved_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            saved = save_agent_preferences(path, {
                "installation_id": str(uuid.uuid4()),
                "start_with_windows": True,
                "auto_capture": True,
                "memory_limit_mb": 100_000,
                "storage_limit_mb": 1,
                "local_api_port": 80,
                "desktop_preference": "nao copiar",
            })

            self.assertEqual(saved["memory_limit_mb"], 8192)
            self.assertEqual(saved["storage_limit_mb"], 128)
            self.assertEqual(saved["local_api_port"], 1024)
            self.assertNotIn("desktop_preference", saved)
            self.assertEqual(load_agent_preferences(path), saved)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), saved)

    def test_corrupt_file_recovers_with_new_safe_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "preferences.json"
            path.write_text("{invalido", encoding="utf-8")

            recovered = load_agent_preferences(path)

            self.assertEqual(recovered["schema"], 1)
            self.assertFalse(recovered["start_with_windows"])
            uuid.UUID(recovered["installation_id"])

    def test_startup_registry_value_is_created_and_removed(self):
        registry_key = mock.MagicMock()
        registry_context = mock.MagicMock()
        registry_context.__enter__.return_value = registry_key
        fake_winreg = mock.MagicMock(
            HKEY_CURRENT_USER=object(), REG_SZ=1
        )
        fake_winreg.CreateKey.return_value = registry_context

        with mock.patch.dict("sys.modules", {"winreg": fake_winreg}):
            configure_agent_startup(True)
            configure_agent_startup(False)

        fake_winreg.SetValueEx.assert_called_once()
        self.assertEqual(fake_winreg.SetValueEx.call_args.args[1], AGENT_STARTUP_VALUE)
        self.assertIn("--background", fake_winreg.SetValueEx.call_args.args[4])
        fake_winreg.DeleteValue.assert_called_once_with(
            registry_key, AGENT_STARTUP_VALUE
        )

    def test_development_startup_command_uses_agent_module(self):
        command = agent_startup_command()
        self.assertIn("app.agent_main", command)
        self.assertIn("--background", command)


if __name__ == "__main__":
    unittest.main()
