import importlib.util
import logging
import os
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 não instalado")
class QtPreviewSmokeTest(unittest.TestCase):
    def test_signed_rollback_reverifies_backs_up_and_closes_qt_app(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import MainWindow

        window = mock.Mock()
        window.license_client.highest_release_sequence = 2
        window.capture_engine = None
        window.capture_busy = False
        window.database_path = Path("capture.sqlite3")
        installer = Path("RF QOL Setup 1.0.0.exe")
        with mock.patch("app.ui_qt.main.UPDATE_MODE", "automatic"), mock.patch(
            "app.ui_qt.main.cached_rollback", side_effect=(installer, installer)
        ) as cached, mock.patch(
            "app.ui_qt.main.backup_database"
        ) as backup, mock.patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), mock.patch(
            "app.ui_qt.main.subprocess.Popen"
        ) as launched:
            MainWindow._rollback(window)
        self.assertEqual(cached.call_count, 2)
        backup.assert_called_once()
        launched.assert_called_once()
        self.assertTrue(window.exit_requested)
        window.close.assert_called_once()

    def test_signed_rollback_keeps_qt_app_open_when_installer_cannot_start(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import MainWindow

        window = mock.Mock()
        window.license_client.highest_release_sequence = 2
        window.capture_engine = None
        window.capture_busy = False
        window.database_path = Path("capture.sqlite3")
        installer = Path("RF QOL Setup 1.0.0.exe")
        with mock.patch("app.ui_qt.main.UPDATE_MODE", "automatic"), mock.patch(
            "app.ui_qt.main.cached_rollback", side_effect=(installer, installer)
        ), mock.patch(
            "app.ui_qt.main.backup_database"
        ), mock.patch.object(
            QtWidgets.QMessageBox,
            "question",
            return_value=QtWidgets.QMessageBox.StandardButton.Yes,
        ), mock.patch.object(
            QtWidgets.QMessageBox, "critical"
        ) as critical, mock.patch(
            "app.ui_qt.main.subprocess.Popen", side_effect=OSError("falha simulada")
        ):
            MainWindow._rollback(window)
        critical.assert_called_once()
        window.close.assert_not_called()

    def test_discord_action_opens_exact_official_url(self):
        from app.ui_qt.main import DISCORD_URL, MainWindow

        with mock.patch("app.ui_qt.main.QtGui.QDesktopServices.openUrl") as opened:
            MainWindow._open_discord(None)
        self.assertEqual(DISCORD_URL, "https://discord.gg/D3hhdMgkj")
        self.assertEqual(opened.call_args.args[0].toString(), DISCORD_URL)

    def test_manual_update_ui_opens_discord_and_disables_rollback(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["manual-update-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        self.assertEqual(window.update_button.text(), "Abrir Discord para atualizações")
        self.assertFalse(window.update_channel.isEnabled())
        self.assertFalse(window.rollback_button.isEnabled())
        self.assertIn("automática desativada", window.update_status.text())
        window.exit_requested = True
        window.close()

    def test_sidebar_switches_between_pc_and_five_emulator_slots(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["client-categories-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        self.assertEqual(window.active_category, "pc")
        self.assertFalse(window.client_buttons[0].isHidden())
        self.assertFalse(window.client_buttons[1].isHidden())
        self.assertTrue(all(button.isHidden() for button in window.client_buttons[2:]))

        window.category_buttons["emulator"].click()

        self.assertEqual(window.active_category, "emulator")
        self.assertTrue(all(button.isHidden() for button in window.client_buttons[:2]))
        self.assertTrue(all(not button.isHidden() for button in window.client_buttons[2:]))
        pve_tabs = window.monitor_controls["pve"]["tabs"]
        self.assertTrue(all(not pve_tabs.isTabVisible(index) for index in range(2)))
        self.assertTrue(all(pve_tabs.isTabVisible(index) for index in range(2, 7)))
        window.exit_requested = True
        window.close()

    def test_send_shortcuts_are_absent_from_ui_and_settings(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from app.ui_qt.operations import DEFAULT_GLOBAL_SHORTCUTS

        create_application(["send-shortcuts-removed-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        self.assertEqual(
            set(DEFAULT_GLOBAL_SHORTCUTS),
            {"monitor_pve", "monitor_pvp", "monitor_boss"},
        )
        self.assertEqual(set(window.setting_shortcuts), set(DEFAULT_GLOBAL_SHORTCUTS))
        sends_page = window.page_stack.widget(1)
        labels = {
            label.text() for label in sends_page.findChildren(QtWidgets.QLabel)
        }
        self.assertTrue({"F1", "F2", "F3", "F4"}.isdisjoint(labels))
        window.close()

    @unittest.skipUnless(os.name == "nt", "Contador de RAM disponível no Windows")
    def test_process_memory_reader_returns_current_working_set(self):
        from app.ui_qt.main import _process_memory_bytes

        memory = _process_memory_bytes()

        self.assertIsInstance(memory, int)
        self.assertGreater(memory, 0)

    def test_3_0_controls_show_ram_shortcuts_and_transparent_overlay(self):
        from PySide6 import QtCore, QtGui
        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["three-zero-controls-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.license_client.require = mock.Mock(return_value={"active": True})
            window._apply_license({
                "active": True,
                "message": "Licença válida",
                "features": ["base", "monitor-pve", "monitor-pvp", "monitor-boss"],
            })
            with mock.patch("app.ui_qt.main._process_memory_bytes", return_value=64 * 1024**2):
                window._capture_tick()
            self.assertEqual(window.top_memory.text(), "RAM: 64,0 MiB")
            self.assertEqual(
                window.monitor_controls["pve"]["enabled"].text(),
                "Ligar monitor Cliente A  Ctrl+F5",
            )
            self.assertEqual(
                window.monitor_controls["pvp"]["enabled"].text(),
                "Ligar monitor Cliente A  Ctrl+F6",
            )
            self.assertIn("sem ler", window.stop_without_reading_button.text())
            window.snapshot = {"combat_monitors": [{
                "local": {},
                "nearby_players": [{
                    "uid": 20,
                    "character_uid": 222,
                    "name": "Rigarden",
                    "level": 70,
                    "hp_percent": 65.5,
                }],
                "pvp": {},
                "bosses": [{
                    "uid": 30,
                    "name": "Mecha Corruptor",
                    "current_hp": 750_000,
                    "max_hp": 1_000_000,
                    "hp_percent": 75.0,
                    "dps_hp": 25_000,
                    "eta_seconds": 30,
                }],
            }]}
            window._toggle_pvp_overlay(True)
            self.assertEqual(
                window.pvp_overlay_summary.text(),
                "Jogadores próximos: 1 · Hostis confirmados: 0",
            )
            self.assertEqual(window.pvp_overlay_rows.count(), 1)
            pvp_labels = window.pvp_overlay_rows.itemAt(0).widget().findChildren(
                window.pvp_overlay_summary.__class__
            )
            self.assertTrue(any("Rigarden" in label.text() for label in pvp_labels))
            self.assertTrue(any("Próximo" in label.text() for label in pvp_labels))
            window.snapshot["combat_monitors"][0]["pvp"] = {
                "uid": 21,
                "name": "Rival confirmado",
                "hp_percent": 50.0,
                "stale": False,
            }
            window._render_combat()
            self.assertEqual(
                window.pvp_overlay_summary.text(),
                "Jogadores próximos: 2 · Hostis confirmados: 1",
            )
            self.assertTrue(
                window.pvp_overlay.testAttribute(
                    QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
                )
            )
            self.assertTrue(
                window.pvp_overlay.windowFlags()
                & QtCore.Qt.WindowType.FramelessWindowHint
            )
            self.assertEqual(
                window.pvp_overlay.cursor().shape(),
                QtCore.Qt.CursorShape.SizeAllCursor,
            )
            position = (
                QtGui.QGuiApplication.primaryScreen().availableGeometry().topLeft()
                + QtCore.QPoint(40, 40)
            )
            window.pvp_overlay.mousePressEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                position=lambda: QtCore.QPointF(10, 10),
                accept=lambda: None,
            ))
            window.pvp_overlay.mouseMoveEvent(SimpleNamespace(
                buttons=lambda: QtCore.Qt.MouseButton.LeftButton,
                globalPosition=lambda: QtCore.QPointF(position + QtCore.QPoint(10, 10)),
                accept=lambda: None,
            ))
            window.pvp_overlay.mouseReleaseEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                accept=lambda: None,
            ))
            self.assertEqual(window.pvp_overlay.pos(), position)
            self.assertEqual(
                load_preferences(root / "preferences.json")["pvp_overlay_position"],
                [position.x(), position.y()],
            )
            window._toggle_pvp_overlay(False)
            window._toggle_pvp_overlay(True)
            self.assertEqual(window.pvp_overlay.pos(), position)
            window._toggle_pvp_overlay(False)

            window._toggle_boss_overlay(True)
            window._toggle_boss_dps_overlay(True)
            self.assertNotEqual(window.boss_overlay.pos(), window.boss_dps_overlay.pos())
            self.assertEqual(window.boss_overlay_name.text(), "Mecha Corruptor")
            self.assertEqual(window.boss_overlay_hp.text(), "HP 750.000 / 1.000.000")
            self.assertEqual(window.boss_overlay_progress.value(), 750)
            self.assertEqual(window.boss_dps_overlay_name.text(), "Mecha Corruptor")
            self.assertIn("25.000", window.boss_dps_overlay_rate.text())
            self.assertEqual(
                window.boss_overlay.cursor().shape(),
                QtCore.Qt.CursorShape.SizeAllCursor,
            )
            self.assertEqual(
                window.boss_dps_overlay.cursor().shape(),
                QtCore.Qt.CursorShape.SizeAllCursor,
            )
            window.snapshot["combat_monitors"][0]["bosses"][0]["current_hp"] = 500_000
            window.snapshot["combat_monitors"][0]["bosses"][0]["hp_percent"] = 50.0
            window._render_combat()
            self.assertEqual(window.boss_overlay_hp.text(), "HP 500.000 / 1.000.000")
            self.assertEqual(window.boss_overlay_progress.value(), 500)
            boss_position = position + QtCore.QPoint(80, 80)
            window.boss_overlay.mousePressEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                position=lambda: QtCore.QPointF(10, 10),
                accept=lambda: None,
            ))
            window.boss_overlay.mouseMoveEvent(SimpleNamespace(
                buttons=lambda: QtCore.Qt.MouseButton.LeftButton,
                globalPosition=lambda: QtCore.QPointF(
                    boss_position + QtCore.QPoint(10, 10)
                ),
                accept=lambda: None,
            ))
            window.boss_overlay.mouseReleaseEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                accept=lambda: None,
            ))
            self.assertEqual(window.boss_overlay.pos(), boss_position)
            self.assertEqual(
                load_preferences(root / "preferences.json")["boss_overlay_position"],
                [boss_position.x(), boss_position.y()],
            )
            boss_dps_position = boss_position + QtCore.QPoint(80, 80)
            window.boss_dps_overlay.mousePressEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                position=lambda: QtCore.QPointF(10, 10),
                accept=lambda: None,
            ))
            window.boss_dps_overlay.mouseMoveEvent(SimpleNamespace(
                buttons=lambda: QtCore.Qt.MouseButton.LeftButton,
                globalPosition=lambda: QtCore.QPointF(
                    boss_dps_position + QtCore.QPoint(10, 10)
                ),
                accept=lambda: None,
            ))
            window.boss_dps_overlay.mouseReleaseEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                accept=lambda: None,
            ))
            self.assertEqual(window.boss_dps_overlay.pos(), boss_dps_position)
            self.assertEqual(
                load_preferences(root / "preferences.json")["boss_dps_overlay_position"],
                [boss_dps_position.x(), boss_dps_position.y()],
            )
            window._toggle_boss_overlay(False)
            window._toggle_boss_dps_overlay(False)
            window._toggle_boss_overlay(True)
            window._toggle_boss_dps_overlay(True)
            self.assertEqual(window.boss_overlay.pos(), boss_position)
            self.assertEqual(window.boss_dps_overlay.pos(), boss_dps_position)
            self.assertEqual(window.boss_overlay_name.text(), "Mecha Corruptor")
            self.assertEqual(window.boss_dps_overlay_name.text(), "Mecha Corruptor")
            window._toggle_boss_overlay(False)
            window._toggle_boss_dps_overlay(False)
            window.close()

    def test_monitor_keybinds_and_auto_market_setting_are_persisted(self):
        from PySide6 import QtWidgets

        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["monitor-keybind-settings-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences_path = root / "preferences.json"
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences_path,
            )
            window.capture_timer.stop()
            window.setting_capture_directory.setText(str(root / "captures"))
            window.setting_shortcuts["monitor_pve"].setCurrentText("Alt+F10")
            window.setting_shortcuts["monitor_pvp"].setCurrentText("Shift+F11")
            window.setting_shortcuts["monitor_boss"].setCurrentText("Ctrl+F12")
            window.setting_auto_market.setChecked(False)

            with (
                mock.patch.object(QtWidgets.QMessageBox, "information"),
                mock.patch.object(window.global_hotkeys, "stop"),
                mock.patch.object(window.global_hotkeys, "start") as start_hotkeys,
            ):
                window._save_settings()

            saved = load_preferences(preferences_path)
            self.assertEqual(saved["shortcuts"]["monitor_pve"], "Alt+F10")
            self.assertEqual(saved["shortcuts"]["monitor_pvp"], "Shift+F11")
            self.assertEqual(saved["shortcuts"]["monitor_boss"], "Ctrl+F12")
            self.assertFalse(saved["auto_market_upload"])
            self.assertEqual(
                window.monitor_controls["pve"]["enabled"].text(),
                "Ligar monitor Cliente A  Alt+F10",
            )
            self.assertEqual(
                start_hotkeys.call_args.args[0]["monitor_boss"], "Ctrl+F12"
            )
            self.assertIn("Leilão/Mercado", window.setting_auto_market.text())
            window.controls_initialized = True
            window.capture_engine = SimpleNamespace(current_session="session")
            window.site_profile = SimpleNamespace(connected=True)
            with mock.patch.object(window, "_run_site_operation") as upload:
                window._maybe_auto_market_upload()
            upload.assert_not_called()
            window.capture_engine = None
            window.close()

    def test_pve_and_pvp_activation_is_independent_per_client_tab(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["monitor-client-tabs-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.license_client.require = mock.Mock(return_value={"active": True})
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base", "monitor-pve", "monitor-pvp"],
        })
        with mock.patch.object(window, "_resume_active_monitors"):
            pve = window.monitor_controls["pve"]
            pve["tabs"].setCurrentIndex(1)
            pve["enabled"].setChecked(True)

            self.assertEqual(
                window.monitor_client_enabled["pve"],
                [False, True, False, False, False, False, False],
            )
            self.assertTrue(window.monitor_enabled["pve"])
            self.assertIn("Cliente B", pve["enabled"].text())

            pve["tabs"].setCurrentIndex(0)
            self.assertFalse(pve["enabled"].isChecked())
            self.assertEqual(
                window.monitor_client_enabled["pve"],
                [False, True, False, False, False, False, False],
            )

            pvp = window.monitor_controls["pvp"]
            pvp["enabled"].setChecked(True)
            self.assertEqual(
                window.monitor_client_enabled["pvp"],
                [True, False, False, False, False, False, False],
            )
            self.assertTrue(window.monitor_enabled["pvp"])
        window.close()

    def test_monitor_page_requests_checkpoint_preview_without_rotation(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["combat-preview-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        calls = []
        window.capture_engine = SimpleNamespace(
            active=True,
            paused=False,
            current_session="session",
            heartbeat=lambda: None,
            preview_live=lambda: calls.append("preview") or {"available": True},
            read_live=lambda: calls.append("rotate") or {"available": True},
        )
        window._rotate_auto_subsessions = lambda: None
        window._stored_capture_bytes = lambda _path: 0
        window._run_capture_operation = lambda name, callback: calls.append(name) or callback()
        window.next_read_at = time.monotonic() + 30
        window.monitor_client_enabled["pve"][0] = True
        window.monitor_enabled["pve"] = True
        window.page_stack.setCurrentIndex(2)
        self.assertIn("preview", calls)
        self.assertNotIn("rotate", calls)
        window.monitor_next_due["pve"] = time.monotonic() + 4.2
        window._capture_tick()
        self.assertRegex(window.top_next_read.text(), r"monitor: [45] s")
        window.capture_engine = None
        window.close()

    def test_preview_result_accepts_numeric_file_count(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["combat-preview-result-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.capture_engine = SimpleNamespace(
            active=True, paused=False, current_session="session"
        )
        window._load_combat_data = lambda: None

        window._capture_operation_finished(
            "preview", {"available": True, "added": 1, "files": 1}, None
        )

        self.assertIn("1 evento(s)", window.top_last_read.text())
        window.capture_engine = None
        window.close()

    def test_boss_page_renders_multiple_bosses_for_the_routed_client(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import MainWindow, create_application

        create_application(["boss-card-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "character_name": "Carvalho",
            "bosses": [
                {"name": "Xenogeyser", "level": 86, "current_hp": 400, "max_hp": 500,
                 "hp_percent": 80.0, "age_seconds": 1.0, "stale": False,
                 "top_damage_players": [
                     {"name": f"Jogador {index}", "guild_name": "Karvalho",
                      "dps_hp": 1000 - index, "damage": 5000 - index}
                     for index in range(1, 7)
                 ],
                 "top_damage_guilds": [
                     {"name": "Karvalho", "dps_hp": 5990, "damage": 29990}
                 ]},
                {"name": "Executor", "level": 90, "current_hp": 300, "max_hp": 600,
                 "hp_percent": 50.0, "age_seconds": 2.0, "stale": False},
            ],
        }]}
        window._render_combat()

        layout = window.combat_widgets["boss"][0]["boss_layout"]
        self.assertEqual(layout.count(), 2)
        labels = [
            label.text()
            for index in range(layout.count())
            for label in layout.itemAt(index).widget().findChildren(QtWidgets.QLabel)
        ]
        self.assertTrue(any("Xenogeyser" in text for text in labels))
        self.assertTrue(any("Executor" in text for text in labels))
        self.assertTrue(any("DPS por jogador" in text for text in labels))
        self.assertTrue(any("Jogador 6 · Karvalho" in text for text in labels))
        self.assertTrue(any("DPS por guilda" in text for text in labels))
        cards = window.combat_page_layouts["boss"]["cards"]
        self.assertFalse(cards[0].isHidden())
        self.assertTrue(cards[1].isHidden())
        self.assertEqual(
            window.combat_page_layouts["boss"]["layout"].getItemPosition(
                window.combat_page_layouts["boss"]["layout"].indexOf(cards[0])
            ),
            (0, 0, 1, 2),
        )
        self.assertEqual(window.combat_widgets["boss"][1]["boss_layout"].count(), 0)
        window.close()

    def test_combat_cards_keep_their_height_and_scroll_instead_of_overlapping(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["combat-card-layout-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            entities = [
                {
                    "npc_index": index,
                    "name": f"Mob {index}",
                    "current_hp": 17_802 + index,
                    "hp_percent": 100.0,
                }
                for index in range(8)
            ]
            window.snapshot = {"combat_monitors": [{
                "client_key": "client:a",
                "character_name": "Carvalho",
                "nearby_monsters": entities,
                "nearby_players": [
                    {"name": f"Jogador {index}", "hp_percent": 100.0}
                    for index in range(8)
                ],
            }]}
            window.monitor_client_enabled["pve"][0] = True
            window.monitor_client_enabled["pvp"][0] = True
            window._render_combat()
            window.show()
            for mode, page_index in (("pve", 2), ("pvp", 3)):
                with self.subTest(mode=mode):
                    window.page_stack.setCurrentIndex(page_index)
                    app.processEvents()
                    layout = window.combat_widgets[mode][0]["nearby_layout"]
                    rows = [
                        layout.itemAt(index).widget()
                        for index in range(layout.count())
                    ]
                    self.assertTrue(
                        window.page_stack.currentWidget().findChild(
                            QtWidgets.QScrollArea
                        )
                    )
                    self.assertTrue(all(row.height() >= 64 for row in rows))
                    values = [
                        row.findChildren(QtWidgets.QLabel)[-1].text()
                        for row in rows
                    ]
                    if mode == "pve":
                        self.assertEqual(values[0], "17.802 HP")
                        self.assertTrue(all("%" not in value for value in values))
                    else:
                        self.assertTrue(all(value.endswith("%") for value in values))
                    self.assertTrue(
                        all(
                            current.geometry().bottom() < following.geometry().top()
                            for current, following in zip(rows, rows[1:])
                        )
                    )
            for mode in ("pve", "pvp"):
                page = window.combat_page_layouts[mode]
                self.assertEqual(
                    page["layout"].getItemPosition(
                        page["layout"].indexOf(page["cards"][0])
                    ),
                    (0, 0, 1, 2),
                )
                self.assertTrue(page["cards"][1].isHidden())
                tabs = window.monitor_controls[mode]["tabs"]
                self.assertEqual(tabs.count(), 7)
                tabs.setCurrentIndex(1)
                app.processEvents()
                self.assertTrue(page["cards"][0].isHidden())
                self.assertFalse(page["cards"][1].isHidden())
                self.assertEqual(
                    page["layout"].getItemPosition(
                        page["layout"].indexOf(page["cards"][1])
                    ),
                    (0, 0, 1, 2),
                )
                tabs.setCurrentIndex(0)
            window.showMaximized()
            app.processEvents()
            window._sync_responsive_layouts()
            for mode in ("pve", "pvp"):
                page = window.combat_page_layouts[mode]
                self.assertEqual(
                    page["layout"].getItemPosition(
                        page["layout"].indexOf(page["cards"][0])
                    ),
                    (0, 0, 1, 2),
                )
            window.showNormal()
            app.processEvents()
            window._sync_responsive_layouts()
            window.close()

    def test_live_refresh_preserves_unsaved_subsession_form(self):
        from PySide6 import QtCore, QtWidgets
        from app.ui_qt.main import MainWindow, create_application

        create_application(["subsession-draft-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window._ensure_capture_engine = lambda: SimpleNamespace(
                current_session="", active=False
            )
            payload = {
                "preferences": {"subsession_duration_minutes": 30},
                "license": {"active": False, "message": "Licença indisponível"},
                "snapshot": {"session_id": None, "subsessions": [], "stats": {}},
                "storage_bytes": 0,
            }
            window._apply_readonly_data(payload)
            window.subsession_duration.setValue(77)
            window.auto_subsession.setChecked(True)
            window.subsession_name.setText("Rascunho")
            window.subsession_map.blockSignals(True)
            window.subsession_map.clear()
            window.subsession_map.addItem("Mapa rascunho")
            window.subsession_map.blockSignals(False)
            window.subsession_spot.blockSignals(True)
            window.subsession_spot.clear()
            window.subsession_spot.addItem("Spot rascunho")
            window.subsession_spot.blockSignals(False)
            window.subsession_mobs.clear()
            mob = QtWidgets.QListWidgetItem("Mob rascunho")
            mob.setFlags(mob.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            mob.setCheckState(QtCore.Qt.CheckState.Checked)
            window.subsession_mobs.addItem(mob)

            window._apply_readonly_data(payload)

            self.assertEqual(window.subsession_duration.value(), 77)
            self.assertTrue(window.auto_subsession.isChecked())
            self.assertEqual(window.subsession_name.text(), "Rascunho")
            self.assertEqual(window.subsession_map.currentText(), "Mapa rascunho")
            self.assertEqual(window.subsession_spot.currentText(), "Spot rascunho")
            self.assertEqual(window.subsession_mobs.count(), 1)
            self.assertEqual(
                window.subsession_mobs.item(0).checkState(),
                QtCore.Qt.CheckState.Checked,
            )
            window.close()

    def test_message_boxes_use_dark_theme_and_portuguese_buttons(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import create_application

        app = create_application(["message-box-theme-test"])
        box = QtWidgets.QMessageBox(
            QtWidgets.QMessageBox.Icon.Question,
            "Descartar sessão anterior",
            "Mover os arquivos para a Lixeira?",
            QtWidgets.QMessageBox.StandardButton.Yes
            | QtWidgets.QMessageBox.StandardButton.No,
        )

        self.assertIn("QMessageBox { background: #081820; }", app.styleSheet())
        self.assertIn("QMenu { background: #081820;", app.styleSheet())
        self.assertEqual(
            box.button(QtWidgets.QMessageBox.StandardButton.Yes).text().replace("&", ""),
            "Sim",
        )
        self.assertEqual(
            box.button(QtWidgets.QMessageBox.StandardButton.No).text().replace("&", ""),
            "Não",
        )

    def test_send_buttons_require_data_for_their_own_type(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["send-availability-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.site_profile.state = {"profile": "Profile", "token": "token"}
        window.snapshot = {
            "session_id": "session",
            "characters": [
                {
                    "uid": "1", "client_key": "client:a",
                    "summary": {"market_events": 2},
                },
                {
                    "uid": "2", "client_key": "client:b",
                    "summary": {"market_events": 0},
                },
            ],
            "collection_type_counts": {1: 1, 2: 1},
            "collection_type_counts_by_uid": {"1": {1: 1}, "2": {2: 1}},
        }
        window.capture_engine = SimpleNamespace(active=True)
        window._set_send_controls()
        self.assertTrue(window.send_buttons[("market", -1)].isEnabled())
        self.assertTrue(window.send_buttons[("codex", 0)].isEnabled())
        self.assertFalse(window.send_buttons[("codex", 1)].isEnabled())
        self.assertFalse(window.send_buttons[("memory_chips", 0)].isEnabled())
        self.assertTrue(window.send_buttons[("memory_chips", 1)].isEnabled())
        window.capture_engine = None
        window.close()

    def test_send_during_capture_reads_current_segment_before_upload(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["send-live-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        calls = []
        window.site_profile.state = {"profile": "Profile", "token": "token"}
        window.capture_engine = SimpleNamespace(
            active=True,
            current_session="session",
            client_ports=((50000,),),
            read_live=lambda: calls.append("read"),
        )
        window.site_uploader = SimpleNamespace(
            send_mode=lambda _mode, _target, snapshot, _language:
            calls.append(snapshot["session_id"]) or {"target": "Cliente A"}
        )
        operation = {}
        window._run_site_operation = lambda _name, callback: operation.update(
            callback=callback
        )

        store = SimpleNamespace(
            session_sources=lambda _session: [],
            close=lambda: None,
        )
        with mock.patch(
            "app.ui_qt.main.ReadOnlySnapshotReader",
            return_value=SimpleNamespace(load=lambda _language: {"session_id": "fresh"}),
        ), mock.patch("app.ui_qt.main.CaptureStore", return_value=store):
            window._send_mode("character", 0)
            operation["callback"]()

        self.assertEqual(calls, ["read", "fresh"])
        window.capture_engine = None
        window.close()

    def test_auto_market_shows_progress_and_waits_after_failure(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["auto-market-progress-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.controls_initialized = True
        window.setting_auto_market.setChecked(True)
        window.capture_engine = SimpleNamespace(current_session="session")
        window.site_profile = SimpleNamespace(connected=True)
        window.preferences = {
            "auto_market_signatures": {},
            "item_name_language": "pt",
        }
        operations = []
        window._run_site_operation = lambda name, callback: operations.append(name)
        store = SimpleNamespace(
            completed_market_signature=lambda _session: "signature",
            close=lambda: None,
        )

        with mock.patch("app.ui_qt.main.CaptureStore", return_value=store):
            window._maybe_auto_market_upload()
            self.assertEqual(operations, ["auto_market"])
            self.assertEqual(
                window.send_status_labels["market"].text(),
                "Enviando Mercado automaticamente…",
            )
            window._site_operation_finished(
                "auto_market", None, ValueError("falha temporária")
            )
            self.assertIn(
                "Falha no envio automático",
                window.send_status_labels["market"].text(),
            )
            window._maybe_auto_market_upload()

        self.assertEqual(operations, ["auto_market"])
        window.capture_engine = None
        window.close()

    def test_beta_parity_actions_are_connected_and_fullscreen_shows_both_clients(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["parity-test"])
        window = MainWindow(load_data=False)
        buttons = {
            button.text(): button.isEnabled()
            for button in window.findChildren(QtWidgets.QPushButton)
        }
        for text in (
            "Ativar licença", "Abrir Discord para atualizações", "Enviar log técnico",
            "Salvar cópia do log", "Abrir pasta do log", "Exportar sessão",
        ):
            self.assertTrue(buttons[text], text)
        self.assertTrue(hasattr(window, "discard_previous"))
        window.showMaximized()
        app.processEvents()
        window._sync_overview_layout()
        self.assertTrue(window.overview_secondary.isVisible())
        self.assertEqual(len(window.secondary_metric_groups), 5)
        window.snapshot = {
            "session_id": "session",
            "profiles": [],
            "characters": [
                {"name": "A", "client_key": "client:a", "summary": {}},
                {"name": "B", "client_key": "client:b",
                 "summary": {"exp_percent": 17.42}},
            ],
            "subsessions": [],
            "stats": {},
        }
        window._render_overview()
        self.assertEqual(window.secondary_exp_progress.value(), 1742)
        self.assertTrue(all(
            primary.minimumHeight() == secondary.minimumHeight() > 0
            for primary, secondary in zip(
                window.primary_metric_groups, window.secondary_metric_groups
            )
        ))
        self.assertTrue(all(
            window.primary_metric_grid.getItemPosition(
                window.primary_metric_grid.indexOf(group)
            ) == (index, 0, 1, 2)
            for index, group in enumerate(window.primary_metric_groups)
        ))
        self.assertGreater(
            len(window.overview_secondary.findChildren(
                QtWidgets.QWidget, "metricDivider"
            )),
            0,
        )
        window.showNormal()
        app.processEvents()
        window._sync_overview_layout()
        self.assertFalse(window.overview_secondary.isVisible())
        self.assertGreater(window.primary_metrics.minimumHeight(), 0)
        self.assertTrue(all(
            window.primary_metric_grid.getItemPosition(
                window.primary_metric_grid.indexOf(group)
            ) == (index, 0, 1, 2)
            for index, group in enumerate(window.primary_metric_groups)
        ))
        window.close()

    def test_automatic_subsession_rotates_only_an_active_timed_entry(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["auto-subsession-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            preferences = root / "preferences.json"
            store = CaptureStore(database)
            started = 1_000_000_000
            interval = 5 * 60 * 1_000_000_000
            store.start_subsession(
                "sub-1", "session-1", "Farm",
                client_key="client:a", duration_minutes=5, started_ns=started,
            )
            store.close()
            window = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=preferences,
            )
            window.capture_timer.stop()
            window.capture_engine = SimpleNamespace(current_session="session-1")
            window.auto_subsession.setChecked(True)
            window.auto_subsession_minutes.setValue(5)
            window._load_readonly_data = lambda: None
            with mock.patch(
                "app.ui_qt.main.time.time_ns",
                return_value=started + 2 * interval + 1,
            ):
                window._rotate_auto_subsessions()
            store = CaptureStore(database, readonly=True)
            entries = store.subsessions("session-1")
            store.close()
            self.assertEqual(len(entries), 3)
            self.assertEqual(sum(item["ended_ns"] is not None for item in entries), 2)
            self.assertEqual(sum(item["ended_ns"] is None for item in entries), 1)
            ordered = sorted(entries, key=lambda item: item["started_ns"])
            self.assertEqual(
                [(item["started_ns"], item["ended_ns"]) for item in ordered],
                [
                    (started, started + interval),
                    (started + interval, started + 2 * interval),
                    (started + 2 * interval, None),
                ],
            )
            window.capture_engine = None
            window.close()

    def test_close_hides_active_capture_when_tray_preference_is_enabled(self):
        from PySide6 import QtGui

        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["tray-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.preferences = {"minimize_to_tray": True}
        window.capture_engine = SimpleNamespace(active=True, current_session="session")
        window._tray = object()
        window.show()
        app.processEvents()
        event = QtGui.QCloseEvent()
        window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertFalse(window.isVisible())
        window.capture_engine = None
        window.exit_requested = True
        window.close()

    def test_second_instance_is_rejected_and_notifies_the_first(self):
        import uuid

        from PySide6 import QtNetwork

        from app.ui_qt.main import _claim_instance_server, create_application

        app = create_application(["single-instance-test"])
        server_name = f"RFQOL.test.{uuid.uuid4().hex}"
        server = _claim_instance_server(app, server_name)
        try:
            self.assertIsNotNone(server)
            self.assertIsNone(_claim_instance_server(app, server_name))
        finally:
            server.close()
            app._rfnext_instance_lock.unlock()
            QtNetwork.QLocalServer.removeServer(server_name)

    def test_tray_menu_is_retained_and_removed_on_exit(self):
        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["tray-lifecycle-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        tray = window._tray
        if tray is None:
            self.skipTest("Área de notificação indisponível neste ambiente")
        actions = [action.text() for action in window.tray_menu.actions()]
        self.assertIn("Abrir RF QOL", actions)
        self.assertIn("Sair", actions)
        window.exit_requested = True
        window.close()
        app.processEvents()
        self.assertFalse(tray.isVisible())

    def test_offscreen_window_uses_minimum_supported_size(self):
        from app.ui_qt.main import STYLE
        from app.ui_qt.smoke import run_smoke

        result = run_smoke()

        self.assertEqual(result["platform"], "offscreen")
        self.assertEqual((result["width"], result["height"]), (1180, 664))
        self.assertEqual((result["minimum_width"], result["minimum_height"]), (1180, 664))
        self.assertEqual(result["title"], "RF QOL — 1.0.0")
        self.assertEqual(result["page_count"], 9)
        self.assertEqual(result["active_page"], 1)
        self.assertEqual(result["navigation"], [
            "Visão geral", "Envios", "Monitor PvE", "Monitor PvP",
            "Alertas", "Subsessões", "Configurações", "Tutorial",
        ])
        self.assertFalse(result["navigation_enabled"]["Monitor PvE"])
        self.assertFalse(result["navigation_enabled"]["Monitor PvP"])
        self.assertFalse(result["navigation_enabled"]["Boss"])
        self.assertFalse(result["frameless"])
        self.assertEqual(result["overview_groups"], 5)
        self.assertEqual(result["overview_metrics"], 18)
        widget_rule = STYLE.split("QWidget {", 1)[1].split("}", 1)[0]
        self.assertNotIn("background", widget_rule)

    def test_module_license_keeps_pvp_visible_and_hides_unlicensed_boss(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["module-license-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base", "monitor-pvp"],
        })

        self.assertFalse(window.nav_buttons[2].isHidden())
        self.assertFalse(window.nav_buttons[2].isEnabled())
        self.assertFalse(window.nav_buttons[3].isHidden())
        self.assertTrue(window.nav_buttons[3].isEnabled())
        self.assertTrue(window.nav_buttons[4].isHidden())
        self.assertFalse(window.monitor_controls["boss"]["overlay"].isEnabled())
        self.assertFalse(window.monitor_controls["boss"]["dps_overlay"].isEnabled())
        window.close()

    def test_f3_preferences_and_subsession_form_use_injected_files(self):
        from PySide6 import QtCore, QtGui, QtWidgets

        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import (
            ASSETS,
            SUBSESSION_COLUMNS,
            SUBSESSION_COLUMN_INDEX,
            MainWindow,
            create_application,
        )
        from core.store import CaptureStore

        create_application(["f3-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "capture.sqlite3"
            preferences_path = root / "preferences.json"
            store = CaptureStore(database_path)
            with store.conn:
                store.conn.execute(
                    """INSERT INTO captures
                       (source,size,mtime_ns,imported_at,events_added,session_id,ingestion_key)
                       VALUES(?,?,?,?,?,?,?)""",
                    ("test.pcap", 1, 1, "2026-08-04T00:00:00Z", 0, "session-f3", "test"),
                )
            store.close()

            window = MainWindow(
                load_data=False,
                database_path=database_path,
                preferences_path=preferences_path,
            )
            self.assertEqual(
                window.subsession_table.columnCount(), len(SUBSESSION_COLUMNS)
            )
            self.assertEqual(
                [
                    window.subsession_table.horizontalHeaderItem(index).text()
                    for index in range(len(SUBSESSION_COLUMNS))
                ],
                [label for _key, label, _width, _visible in SUBSESSION_COLUMNS],
            )
            self.assertNotIn("Diamantes", {
                action.text() for action in window.subsession_column_actions.values()
            })
            self.assertGreaterEqual(window.subsession_mobs.minimumHeight(), 300)
            self.assertEqual(window.subsession_filter_level_from.value(), 0)
            self.assertEqual(window.subsession_filter_level_to.value(), 0)
            self.assertEqual(window.subsession_filter_level_from.specialValueText(), "")
            self.assertEqual(window.subsession_filter_level_to.specialValueText(), "")
            self.assertEqual(window.subsession_filter_level_from.width(), 110)
            self.assertEqual(window.subsession_filter_level_to.width(), 110)
            form = window.subsession_form_layout
            client_row = form.getWidgetPosition(window.subsession_client)[0]
            observation_row = form.getWidgetPosition(window.subsession_name)[0]
            filter_row = form.getWidgetPosition(
                window.subsession_filter_level_from.parentWidget()
            )[0]
            mobs_row = form.getWidgetPosition(window.subsession_mobs)[0]
            self.assertEqual(observation_row, client_row + 1)
            self.assertLess(filter_row, mobs_row)
            self.assertTrue(window.subsession_level_from.isHidden())
            self.assertTrue(window.subsession_level_to.isHidden())
            self.assertFalse(hasattr(window, "setting_quick_durations"))
            reader = window.snapshot_reader
            window.data_load_running = True
            window._load_readonly_data()
            self.assertTrue(window.data_load_pending)
            self.assertIs(window.snapshot_reader, reader)
            window.data_load_running = False
            window.data_load_pending = False
            self.assertEqual(
                window.settings_grid.getItemPosition(
                    window.settings_grid.indexOf(window.settings_license_panel)
                )[0],
                0,
            )
            self.assertEqual(
                window.subsession_table.horizontalHeader().sectionResizeMode(1),
                QtWidgets.QHeaderView.ResizeMode.Interactive,
            )
            window.snapshot = {
                "session_id": "session-f3", "profiles": [], "characters": [],
                "subsessions": [], "subsession_summaries": {}, "stats": {},
            }
            window.preferences = {}
            window.farm_catalog = {
                "Mapa": {"Spot": {"Mob A": (10, 12), "Mob B": (20,)}}
            }
            window.subsession_map.clear()
            window.subsession_map.addItem("Mapa")
            window._subsession_map_changed("Mapa")
            self.assertEqual(window.subsession_mobs.count(), 2)
            self.assertEqual(window.subsession_mobs.item(0).text(), "Mob A · Nv. 10–12")
            self.assertEqual(window.subsession_mobs.item(1).text(), "Mob B · Nv. 20")
            window.subsession_mobs.item(0).setCheckState(QtCore.Qt.CheckState.Checked)
            self.assertEqual(window._selected_mobs(), ["Mob A"])
            window.subsession_name.setText("Teste F3")
            window._load_readonly_data = lambda: None
            window._save_subsession()

            store = CaptureStore(database_path, readonly=True)
            subsession = store.subsessions("session-f3")[0]
            self.assertEqual(subsession["name"], "Teste F3")
            self.assertEqual(subsession["mobs"], ["Mob A"])
            self.assertEqual(subsession["mob_levels"], {"Mob A": "10-12"})
            store.close()

            window.snapshot.update({
                "session_id": "session-f3", "subsessions": [subsession],
                "subsession_summaries": {},
            })
            window._render_subsessions()
            window.editing_subsession_id = subsession["id"]
            window.subsession_name.setText("Nome atualizado")
            window._save_subsession()
            self.assertTrue(
                window.subsession_table.item(0, 1).text().startswith("Nome atualizado")
            )
            store = CaptureStore(database_path, readonly=True)
            subsession = store.subsessions("session-f3")[0]
            store.close()

            subsession.update(started_ns=1_000_000_000, ended_ns=3_601_000_000_000)
            window.snapshot.update({
                "profiles": [{"uid": "uid-a", "name": "Carvalho", "client_key": "client:a"}],
                "characters": [{
                    "uid": "uid-a", "name": "Carvalho", "client_key": "client:a",
                    "summary": {"character_class": "Arbiter", "biosuit_grade": 4,
                                "rover_item_index": 4000000,
                                "rover_name": "Sirius", "rover_grade": 1},
                }],
                "subsessions": [subsession],
                "subsession_summaries": {subsession["id"]: {
                    "kills": 10, "finalizations": 2, "exp_gained": 1000,
                    "exp_gained_percent": 2.5, "credits": 5740,
                    "contribution": 60500,
                    "loot_by_rarity": {
                        "common": 4, "uncommon": 3, "rare": 2, "epic": 1,
                    },
                }},
            })
            window._render_subsessions()
            self.assertEqual(
                [
                    window.subsession_table.item(
                        0, SUBSESSION_COLUMN_INDEX[key]
                    ).text()
                    for key in (
                        "character", "time", "kills", "exp_total",
                        "exp_percent", "exp_hour", "exp_hour_percent",
                        "contribution",
                    )
                ],
                ["Carvalho", "01:00:00", "10", "1.000", "2,50%", "1.000", "2,50%", "60.500"],
            )
            self.assertEqual(
                window.subsession_table.item(
                    0, SUBSESSION_COLUMN_INDEX["finalizations"]
                ).text(),
                "2",
            )
            self.assertEqual(
                [
                    window.subsession_table.item(
                        0, SUBSESSION_COLUMN_INDEX[key]
                    ).text()
                    for key in (
                        "credits", "credits_hour", "contribution_hour",
                        "loot_total", "loot_common", "loot_uncommon",
                        "loot_rare", "loot_epic",
                    )
                ],
                ["5.740", "5.740", "60.500", "10", "4", "3", "2", "1"],
            )
            credits_column = SUBSESSION_COLUMN_INDEX["credits"]
            window.subsession_column_actions["credits"].setChecked(True)
            self.assertFalse(window.subsession_table.isColumnHidden(credits_column))
            header = window.subsession_table.horizontalHeader()
            header.moveSection(header.visualIndex(credits_column), 0)
            self.assertEqual(header.visualIndex(SUBSESSION_COLUMN_INDEX["select"]), 0)
            self.assertEqual(header.visualIndex(credits_column), 1)
            header.resizeSection(credits_column, 144)
            window._save_subsession_columns()
            saved_columns = load_preferences(preferences_path)["subsession_columns"]
            self.assertEqual(saved_columns["order"][:2], ["select", "credits"])
            self.assertIn("credits", saved_columns["visible"])
            self.assertEqual(saved_columns["widths"]["credits"], 144)
            window._reset_subsession_columns()
            self.assertTrue(window.subsession_table.isColumnHidden(credits_column))
            window._apply_subsession_columns(saved_columns)
            self.assertFalse(window.subsession_table.isColumnHidden(credits_column))
            self.assertEqual(header.visualIndex(credits_column), 1)
            self.assertTrue(window.subsession_table.item(0, 1).textAlignment() & QtCore.Qt.AlignmentFlag.AlignVCenter)
            window.subsession_table.horizontalHeader().resizeSection(1, 300)
            self.assertEqual(window.subsession_table.columnWidth(1), 300)
            window._autofit_subsession_column(1)
            self.assertGreater(window.subsession_table.columnWidth(1), 0)
            window._render_overview()
            self.assertFalse(window.character_icon.pixmap().isNull())
            self.assertFalse(window.rover_icon.pixmap().isNull())
            self.assertEqual(window.rover_icon.toolTip(), "Sirius")
            expected_rover = QtGui.QPixmap(str(
                ASSETS / "rover-icons" / "loadout-4000000.webp"
            )).scaled(
                window.rover_icon.width() - 4,
                window.rover_icon.height() - 4,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            self.assertEqual(
                window.rover_icon.pixmap().toImage(), expected_rover.toImage()
            )

            window.setting_capture_directory.setText(str(root / "captures"))
            window.setting_detailed_log.setChecked(True)
            with mock.patch.object(QtWidgets.QMessageBox, "information"):
                window._save_settings()
            saved_preferences = load_preferences(preferences_path)
            self.assertEqual(saved_preferences["capture_directory"], str(root / "captures"))
            self.assertTrue(saved_preferences["detailed_logging"])
            self.assertTrue(window.log.isEnabledFor(logging.DEBUG))
            window.preferences = saved_preferences
            window.setting_detailed_log.setChecked(False)
            window._load_settings_fields()
            self.assertTrue(window.setting_detailed_log.isChecked())
            window.close()

    def test_removed_subsession_is_dropped_from_selection_state(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["subsession-stale-selection-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.selected_subsessions = {"deleted-subsession"}
            window.snapshot = {
                "session_id": "session",
                "subsessions": [],
                "subsession_summaries": {},
                "profiles": [],
            }

            window._render_subsessions()

            self.assertEqual(window.selected_subsessions, set())
            self.assertEqual(
                window.send_selected_status.text(),
                "Nenhuma subsessão selecionada",
            )
            self.assertFalse(window.subsession_upload_button.isEnabled())
            window.selected_subsessions = {"deleted-subsession"}
            window._run_site_operation = mock.Mock()
            window._send_selected_subsessions()
            self.assertEqual(window.selected_subsessions, set())
            window._run_site_operation.assert_not_called()
            window.close()

    def test_subsession_level_filter_and_full_favorites(self):
        from PySide6 import QtCore, QtWidgets

        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["subsession-favorites-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences_path = root / "preferences.json"
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences_path,
            )
            window.capture_timer.stop()
            window.preferences = {}
            window.farm_catalog = {
                "Mapa": {"Spot": {"Mob A": (10, 12), "Mob B": (20,)}}
            }
            window.subsession_map.addItem("Mapa")
            window._subsession_map_changed("Mapa")

            window.subsession_filter_level_from.setValue(15)
            self.assertEqual(window.subsession_mobs.count(), 1)
            self.assertEqual(
                window.subsession_mobs.item(0).data(
                    QtCore.Qt.ItemDataRole.UserRole
                ),
                "Mob B",
            )
            window.subsession_filter_level_from.setValue(0)
            window.subsession_mobs.item(0).setCheckState(
                QtCore.Qt.CheckState.Checked
            )
            window.subsession_filter_level_from.setValue(15)
            self.assertEqual(window._selected_mobs(), ["Mob A"])

            window.subsession_client.setCurrentIndex(1)
            window.subsession_other_mob.setText("Mob extra")
            window.subsession_level_from.setValue(60)
            window.subsession_level_to.setValue(70)
            window.subsession_duration.setValue(45)
            window.subsession_name.setText("Farm favorito")
            window.auto_subsession.setChecked(True)
            window.auto_subsession_minutes.setValue(20)
            with mock.patch.object(
                QtWidgets.QInputDialog,
                "getText",
                return_value=("Favorito completo", True),
            ):
                window._save_subsession_favorite()

            saved = load_preferences(preferences_path)["subsession_favorites"]
            self.assertEqual(saved["Favorito completo"]["client"], 1)
            self.assertEqual(saved["Favorito completo"]["mobs"], ["Mob A"])
            self.assertEqual(saved["Favorito completo"]["filter_level_from"], 15)
            self.assertEqual(saved["Favorito completo"]["other_mob"], "Mob extra")
            self.assertEqual(saved["Favorito completo"]["duration"], 45)
            self.assertTrue(saved["Favorito completo"]["automatic"])

            window.subsession_client.setCurrentIndex(0)
            window.subsession_other_mob.clear()
            window.subsession_level_from.setValue(0)
            window.subsession_level_to.setValue(0)
            window.subsession_duration.setValue(0)
            window.subsession_name.clear()
            window.auto_subsession.setChecked(False)
            window.subsession_filter_level_from.setValue(0)
            window._toggle_all_mobs(False)
            window._load_subsession_favorite()

            self.assertEqual(window.subsession_client.currentIndex(), 1)
            self.assertEqual(window._selected_mobs(), ["Mob A"])
            self.assertEqual(window.subsession_filter_level_from.value(), 15)
            self.assertEqual(window.subsession_other_mob.text(), "Mob extra")
            self.assertEqual(window.subsession_level_from.value(), 60)
            self.assertEqual(window.subsession_level_to.value(), 70)
            self.assertEqual(window.subsession_duration.value(), 45)
            self.assertEqual(window.subsession_name.text(), "Farm favorito")
            self.assertTrue(window.auto_subsession.isChecked())
            self.assertEqual(window.auto_subsession_minutes.value(), 20)

            with mock.patch.object(
                QtWidgets.QMessageBox,
                "question",
                return_value=QtWidgets.QMessageBox.StandardButton.Yes,
            ):
                window._delete_subsession_favorite()
            self.assertEqual(
                load_preferences(preferences_path)["subsession_favorites"], {}
            )
            window.close()

    def test_uid_history_can_be_selected_independently_per_client(self):
        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["uid-history-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "capture.sqlite3"
            preferences_path = root / "preferences.json"
            store = CaptureStore(database_path)
            with store.conn:
                store.conn.execute(
                    """INSERT INTO character_history
                       (character_uid,character_name,last_seen_at,
                        last_session_id,last_client_key,
                        biosuit_item_index,rover_item_index)
                       VALUES('101','Alice','2026-08-08T12:00:00Z','old',
                              'client:a',2075041,4000000)"""
                )
            store.close()

            window = MainWindow(
                load_data=False,
                database_path=database_path,
                preferences_path=preferences_path,
            )
            window.capture_timer.stop()
            window.snapshot = {
                "session_id": "session",
                "character_history": [{
                    "uid": "101", "name": "Alice",
                    "last_seen_at": "2026-08-08T12:00:00Z",
                    "biosuit_item_index": 2075041,
                    "rover_item_index": 4000000,
                }],
                "client_bindings": [],
            }
            window._load_readonly_data = lambda: None
            window._set_client_uid_selection(0, "101")

            self.assertEqual(
                load_preferences(preferences_path)["client_uid_selections"],
                {"client:a": "101"},
            )
            self.assertEqual(window.client_uid_buttons[0].text(), "UID: Alice")
            window.snapshot["client_bindings"] = [{
                "client_key": "client:a", "uid": "101",
                "name": "Alice", "source": "manual",
            }]
            window._render_overview()
            self.assertEqual(window.character_name.text(), "Alice")
            self.assertIn("Arbiter", window.character_details.text())
            self.assertIn("Último estado conhecido", window.character_details.text())
            self.assertEqual(window.rover_name.text(), "Sirius")
            self.assertEqual(window.rover_icon.toolTip(), "Sirius")
            store = CaptureStore(database_path, readonly=True)
            columns = {
                row[1]
                for row in store.conn.execute("PRAGMA table_info(character_history)")
            }
            self.assertIn("biosuit_item_index", columns)
            self.assertIn("rover_item_index", columns)
            self.assertEqual(
                store.client_bindings("session")[0],
                {
                    "client_key": "client:a", "uid": "101",
                    "name": "Alice", "source": "manual",
                },
            )
            store.close()
            with self.assertRaisesRegex(ValueError, "outro cliente"):
                window._set_client_uid_selection(1, "101")

            window._set_client_uid_selection(0, None)
            self.assertEqual(
                load_preferences(preferences_path)["client_uid_selections"], {}
            )
            window.close()

    def test_uid_history_schema_is_created_before_first_read(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["uid-history-migration-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "capture.sqlite3"
            store = CaptureStore(database_path)
            with store.conn:
                store.conn.execute(
                    """INSERT INTO captures
                       (source,size,mtime_ns,imported_at,events_added,
                        session_id,ingestion_key)
                       VALUES('old.pcap',1,1,'2026-08-01T12:00:00+00:00',
                              0,'old','test')"""
                )
                store.conn.execute(
                    """INSERT INTO client_bindings
                       (session_id,client_key,character_uid,
                        character_name,binding_source)
                       VALUES('old','client:a','101','Alice','canonical')"""
                )
                store.conn.execute("DROP TABLE character_history")
            store.close()

            window = MainWindow(
                load_data=False,
                database_path=database_path,
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            store = CaptureStore(database_path, readonly=True)
            self.assertEqual(
                (store.character_history()[0]["uid"],
                 store.character_history()[0]["name"]),
                ("101", "Alice"),
            )
            store.close()
            window.close()


if __name__ == "__main__":
    unittest.main()
