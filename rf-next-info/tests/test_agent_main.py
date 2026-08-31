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
                self.assertIn("RF Next Companion", window.windowTitle())
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
        from app.agent_main import (
            AgentWindow,
            _format_duration_seconds,
            _format_status_time,
        )

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
                        {
                            "name": "Alice", "level": 66,
                            "client_ref": "opaque-a",
                            "session_duration_seconds": 3661,
                        },
                        {
                            "name": "Bob", "level": 67,
                            "client_ref": "opaque-b",
                            "session_duration_seconds": 65,
                        },
                    ],
                    "memory_budget_mb": 1024,
                    "outbox": {"events": 12, "bytes": 4096},
                    "capture": {"received_packets": 1234},
                    "decoder": {
                        "processed_packets": 1234,
                        "decoded_events": 56,
                        "last_decoded_ns": 1_787_719_000_000_000_000,
                        "tcp_gap_recoveries": 2,
                        "stalled_tcp_flows": 0,
                    },
                    "local_api": {"active": True, "port": 17621},
                })

                self.assertEqual(window.state_label.text(), "Capturando")
                self.assertEqual(window.clients_value.text(), "2 clientes")
                self.assertEqual(window.clients_list.count(), 2)
                self.assertIn("Alice", window.clients_list.item(0).text())
                self.assertIn("sessão 01:01:01", window.clients_list.item(0).text())
                self.assertIn("sessão 00:01:05", window.clients_list.item(1).text())
                self.assertNotIn("opaque-a", window.clients_list.item(0).text())
                self.assertEqual(_format_duration_seconds(90061), "25:01:01")
                self.assertTrue(window.stop_button.isEnabled())
                self.assertFalse(window.start_button.isEnabled())
                self.assertEqual(
                    window.server_value.text(), "Modo local · envio desativado"
                )
                self.assertEqual(
                    window.traffic_value.text(), "1.234 pacotes úteis · 56 eventos"
                )
                self.assertEqual(
                    window.last_decode_value.text(),
                    _format_status_time(1_787_719_000_000_000_000),
                )
                self.assertIn(
                    "Fluxos TCP recuperados: 2",
                    window.last_decode_value.toolTip(),
                )
                self.assertEqual(window.last_ack_value.text(), "Envio desativado")
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
                        "delivery": {
                            "last_ack_at": "2026-08-26T04:40:01Z",
                        },
                    }
                })
                self.assertEqual(
                    window.server_value.text(),
                    "Cadastro enviado · aguardando liberação",
                )
                self.assertNotEqual(
                    window.last_ack_value.text(), "Nenhum lote confirmado"
                )
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_health_shows_real_generation_send_and_queue_rates_per_second(self):
        from app.agent_main import AgentWindow, _flow_rates

        self.assertEqual(
            _flow_rates((10.0, 100, 40, 60), (12.0, 120, 48, 72)),
            (10.0, 4.0, 6.0),
        )
        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            first = {
                "outbox": {"events": 60},
                "projection": {"enqueued": 100},
                "server": {"mode": "online", "delivery": {"sent_events": 40}},
            }
            second = {
                "outbox": {"events": 72},
                "projection": {"enqueued": 120},
                "server": {"mode": "online", "delivery": {"sent_events": 48}},
            }
            try:
                with mock.patch(
                    "app.agent_main.time.monotonic", side_effect=(10.0, 12.0)
                ):
                    window._render_health(first)
                    window._render_health(second)
                self.assertEqual(
                    window.flow_value.text(),
                    "Gerados 10,0/s · enviados 4,0/s · fila +6,0/s",
                )
                self.assertIn("enviados/s", window.flow_value.toolTip())
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
                self.assertIn("qmenu { color: #f4f2eb", style)
                self.assertIn("qmenu::item:selected { color: #ffffff", style)
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

    def test_ready_update_never_applies_without_visible_confirmation(self):
        from PySide6 import QtWidgets

        from app.agent_main import AgentWindow
        from core.agent_updates import UpdateCandidate

        with tempfile.TemporaryDirectory() as folder:
            installer = Path(folder) / "RF-QOL-Agent-Setup-2.0.0-beta.23.exe"
            installer.write_bytes(b"verified-installer")
            candidate = UpdateCandidate(
                version="2.0.0-beta.23",
                release_sequence=33,
                installer=installer,
                manifest={"sha256": "a" * 64},
            )
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            try:
                with mock.patch(
                    "app.agent_main.QtWidgets.QMessageBox.exec",
                    return_value=QtWidgets.QMessageBox.StandardButton.No,
                ), mock.patch.object(window, "_exit_agent") as exit_agent:
                    window._update_ready(candidate)
                self.assertIsNone(window._pending_update_installer)
                exit_agent.assert_not_called()

                with mock.patch(
                    "app.agent_main.QtWidgets.QMessageBox.exec",
                    return_value=QtWidgets.QMessageBox.StandardButton.Yes,
                ), mock.patch.object(window, "_exit_agent") as exit_agent:
                    window._update_ready(candidate)
                self.assertEqual(window._pending_update_installer, installer)
                exit_agent.assert_called_once_with()
            finally:
                window._exiting = True
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_update_confirmation_is_readable_and_uses_portuguese_actions(self):
        from PySide6 import QtWidgets

        from app.agent_main import _build_update_confirmation_dialog
        from core.agent_updates import UpdateCandidate

        candidate = UpdateCandidate(
            version="2.0.0-beta.30",
            release_sequence=40,
            installer=Path("update.exe"),
            manifest={"sha256": "95b2" * 16},
        )
        parent = QtWidgets.QWidget()
        dialog = _build_update_confirmation_dialog(parent, candidate)
        try:
            style = dialog.styleSheet().lower()
            self.assertIn("qmessagebox {", style)
            self.assertIn("background-color: #0d1c23", style)
            self.assertIn("qmessagebox qlabel", style)
            self.assertIn("qlabel#qt_msgbox_label", style)
            self.assertIn("color: #f4f2eb", style)
            self.assertEqual(
                dialog.button(QtWidgets.QMessageBox.StandardButton.Yes).text(),
                "Instalar agora",
            )
            self.assertEqual(
                dialog.button(QtWidgets.QMessageBox.StandardButton.No).text(),
                "Agora não",
            )
            self.assertIn("Deseja instalar agora?", dialog.text())
            self.assertNotIn("Yes", dialog.text())
        finally:
            dialog.close()
            parent.close()
            dialog.deleteLater()
            parent.deleteLater()
            self.app.processEvents()

    def test_health_shows_memory_and_site_account_binding(self):
        from app.agent_main import AgentWindow

        with tempfile.TemporaryDirectory() as folder:
            window = AgentWindow(
                self._runtime(),
                preferences_path=Path(folder) / "preferences.json",
                start_worker=False,
            )
            try:
                window._render_health({
                    "memory_budget_mb": 1024,
                    "memory": {"working_set_bytes": 192 * 1024 * 1024},
                    "server": {"authorization": {
                        "required": True,
                        "authorized": False,
                        "status": "pending",
                        "pairing_code": "ABCD-EFGH",
                    }},
                })
                self.assertEqual(window.memory_value.text(), "192 MiB / 1.024 MiB")
                self.assertIn("ABCD-EFGH", window.authorization_value.text())
                self.assertFalse(window.start_button.isEnabled())
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

    def test_self_test_rejects_missing_exp_level_curve(self):
        from app import agent_main

        with mock.patch.object(agent_main, "LEVEL_CURVE", {}):
            with self.assertRaisesRegex(RuntimeError, "Curva de EXP"):
                agent_main.main(["--self-test"])

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
        self.assertEqual(
            online.call_args.kwargs["version"], agent_main.AGENT_TRANSPORT_VERSION
        )
        self.assertEqual(
            online.call_args.kwargs["decoder_version"], agent_main.APP_VERSION
        )
        offline.assert_not_called()

    def test_second_agent_instance_is_rejected_and_notifies_the_first(self):
        import uuid

        from PySide6 import QtNetwork

        from app.agent_main import _claim_instance_server

        server_name = f"RFQOLAgent.test.{uuid.uuid4().hex}"
        server = _claim_instance_server(self.app, server_name)
        try:
            self.assertIsNotNone(server)
            self.assertIsNone(_claim_instance_server(self.app, server_name))
        finally:
            server.close()
            self.app._rfqol_agent_instance_lock.unlock()
            QtNetwork.QLocalServer.removeServer(server_name)


if __name__ == "__main__":
    unittest.main()
