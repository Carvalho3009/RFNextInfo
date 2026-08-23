from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 não instalado")
class AgentWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app.agent_main import create_application

        cls.app = create_application(["agent-window-test"])

    def _runtime(self):
        runtime = mock.MagicMock()
        runtime.active = False
        runtime.pairing_credentials.return_value = {
            "base_url": "http://127.0.0.1:17621",
            "token": "token-local",
            "authorization": "Bearer",
            "domains": ["boss", "pvp"],
        }
        return runtime

    def test_window_is_agent_only_and_defaults_to_manual_capture(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            preferences = Path(folder) / "preferences.json"
            window = AgentWindow(
                self._runtime(),
                preferences_path=preferences,
                start_worker=False,
            )
            try:
                self.assertIn("RF QOL Agent", window.windowTitle())
                self.assertFalse(window.auto_capture.isChecked())
                self.assertFalse(window.startup.isChecked())
                self.assertEqual(window.memory_limit.currentData(), 1024)
                visible_text = " ".join(
                    label.text() for label in window.findChildren(type(window.state_label))
                )
                self.assertNotIn("Visão geral", visible_text)
                self.assertNotIn("Banco PvE", visible_text)
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_health_renders_multiple_clients_without_exposing_raw_routes(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            try:
                window._render_health({
                    "active": True,
                    "client_processes": 2,
                    "clients": [
                        {"name": "Alice", "level": 66, "client_ref": "opaque-a"},
                        {"name": "Bob", "level": 67, "client_ref": "opaque-b"},
                    ],
                    "memory_budget_mb": 1024,
                    "outbox": {"events": 12, "bytes": 4096},
                    "capture": {"received_packets": 1234},
                    "decoder": {"decoded_events": 56},
                    "local_api": {"active": True, "port": 17621},
                })

                self.assertEqual(window.state_label.text(), "Capturando")
                self.assertEqual(window.clients_value.text(), "2 clientes")
                self.assertEqual(window.clients_list.count(), 2)
                self.assertIn("Alice", window.clients_list.item(0).text())
                self.assertNotIn("opaque-a", window.clients_list.item(0).text())
                self.assertTrue(window.stop_button.isEnabled())
                self.assertFalse(window.start_button.isEnabled())
                self.assertEqual(
                    window.server_value.text(), "Modo local · envio desativado"
                )
                self.assertEqual(
                    window.traffic_value.text(), "1.234 pacotes · 56 eventos"
                )
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_server_registration_state_is_readable(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            try:
                window._render_health({
                    "server": {
                        "mode": "online",
                        "state": "registration_pending",
                    }
                })
                self.assertEqual(
                    window.server_value.text(),
                    "Cadastro enviado · aguardando liberação",
                )
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_dark_theme_sets_readable_foreground_for_every_control_family(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            try:
                style = " ".join(window.styleSheet().lower().split())
                self.assertIn("qwidget { color: #f4f2eb", style)
                self.assertIn("qlabel#title { color: #ffffff", style)
                self.assertIn("qpushbutton:disabled { color: #71838c", style)
                self.assertIn("qlabel#statusvalue { color: #f4f2eb", style)
                self.assertEqual(
                    window.start_button.objectName(), "primaryButton"
                )
                self.assertGreaterEqual(window.clients_list.height(), 70)
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_preferences_and_pairing_are_explicit_user_actions(self):
        from PySide6 import QtWidgets
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            preferences = Path(folder) / "preferences.json"
            window = AgentWindow(
                self._runtime(),
                preferences_path=preferences,
                start_worker=False,
            )
            try:
                window.auto_capture.setChecked(True)
                stored = json.loads(preferences.read_text(encoding="utf-8"))
                self.assertTrue(stored["auto_capture"])
                window._copy_pairing()
                clipboard = QtWidgets.QApplication.clipboard().text()
                self.assertIn("token-local", clipboard)
                self.assertIn("127.0.0.1", clipboard)
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_poll_does_not_accumulate_while_previous_poll_is_pending(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            calls: list[bool] = []
            window.backend = mock.MagicMock()
            window.poll_requested.connect(calls.append)
            try:
                window._request_poll()
                window._request_poll()
                self.assertEqual(calls, [False])

                window._render_health({})
                window._request_poll()
                self.assertEqual(calls, [False, False])
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_close_without_system_tray_requests_clean_shutdown(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            event = mock.MagicMock()
            window.tray.hide()
            try:
                with mock.patch.object(window, "_exit_agent") as exit_agent:
                    window.closeEvent(event)
                    self.app.processEvents()
                    exit_agent.assert_called_once_with()
                event.ignore.assert_called_once_with()
                event.accept.assert_not_called()
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_backend_poll_refreshes_idle_client_routes(self):
        from app.agent_main import AgentBackend

        runtime = self._runtime()
        runtime.refresh_routes.return_value = {
            "client_processes": 2,
            "no_clients": False,
        }
        runtime.health.return_value = {"active": False, "client_processes": 2}
        backend = AgentBackend(runtime)
        received: list[dict] = []
        backend.health_ready.connect(received.append)

        backend.poll(False)

        runtime.refresh_routes.assert_called_once_with()
        runtime.start_capture.assert_not_called()
        self.assertEqual(received[-1]["client_processes"], 2)

    def test_deferred_memory_limit_is_applied_after_capture_stops(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            requested: list[int] = []
            window.backend = mock.MagicMock()
            window.memory_requested.connect(requested.append)
            try:
                window.memory_limit.setCurrentIndex(
                    window.memory_limit.findData(2048)
                )
                self.assertEqual(window._pending_memory_mb, 2048)

                window._command_finished("memory", {"applied": False})
                window._command_finished("stop", {})
                self.assertEqual(requested, [2048, 2048])

                window._command_finished("memory", {"applied": True})
                self.assertIsNone(window._pending_memory_mb)
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_self_test_does_not_create_runtime_or_capture(self):
        from app import agent_main

        preferences = {
            "schema": 1,
            "installation_id": "9f81db93-57df-4cab-a2e6-6ef20a8bfa9d",
            "start_with_windows": False,
            "auto_capture": False,
            "memory_limit_mb": 1024,
            "storage_limit_mb": 512,
            "local_api_port": 17621,
        }
        with (
            mock.patch.object(agent_main, "ensure_agent_layout") as ensure_layout,
            mock.patch.object(
                agent_main, "load_agent_preferences", return_value=preferences
            ) as load_preferences,
            mock.patch.object(
                agent_main, "save_agent_preferences", return_value=preferences
            ) as save_preferences,
            mock.patch.object(
                agent_main.StandaloneWindowsAgentRuntime, "create_offline"
            ) as create_runtime,
        ):
            result = agent_main.main(["--self-test"])
            ensure_layout.assert_not_called()
            load_preferences.assert_not_called()
            save_preferences.assert_not_called()

        self.assertEqual(result, 0)
        create_runtime.assert_not_called()

    def test_runtime_uses_only_the_dedicated_agent_server_when_configured(self):
        from app import agent_main

        preferences = {
            "installation_id": "9f81db93-57df-4cab-a2e6-6ef20a8bfa9d",
            "memory_limit_mb": 1024,
            "storage_limit_mb": 512,
            "local_api_port": 17621,
        }
        sentinel = object()
        with (
            mock.patch.object(agent_main, "AGENT_RUNTIME_DIR", Path("agent-state")),
            mock.patch.object(
                agent_main, "AGENT_SERVER", "https://qol.example.test"
            ),
            mock.patch.object(
                agent_main.StandaloneWindowsAgentRuntime,
                "create_online",
                return_value=sentinel,
            ) as online,
            mock.patch.object(
                agent_main.StandaloneWindowsAgentRuntime, "create_offline"
            ) as offline,
        ):
            self.assertIs(agent_main._create_runtime(preferences), sentinel)

        online.assert_called_once()
        self.assertEqual(online.call_args.args[2], "https://qol.example.test")
        offline.assert_not_called()


if __name__ == "__main__":
    unittest.main()
