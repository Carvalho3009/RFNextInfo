import importlib.util
import json
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
    def test_application_registers_bundled_fonts_only_once(self):
        from app.ui_qt import main

        with (
            mock.patch.object(main, "_FONTS_LOADED", False),
            mock.patch.object(
                main.QtGui.QFontDatabase,
                "addApplicationFont",
                return_value=1,
            ) as add_font,
        ):
            main._load_fonts()
            main._load_fonts()

        self.assertEqual(add_font.call_count, 2)

    def test_closed_window_releases_its_qt_object(self):
        import gc
        import weakref

        from PySide6 import QtCore
        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["window-release-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            reference = weakref.ref(window)

            window.close()
            del window
            QtCore.QCoreApplication.sendPostedEvents(
                None, QtCore.QEvent.Type.DeferredDelete
            )
            app.processEvents()
            gc.collect()

            self.assertIsNone(reference())

    def test_item_drop_alert_baselines_then_fires_once_for_new_event(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["item-drop-alert-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = root / "preferences.json"
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences,
            )
            window.capture_timer.stop()
            window.alert_item_drop.setChecked(True)
            first = {
                "ts_ns": 1,
                "stream_offset": 10,
                "bundle_seq": 0,
                "type": "drop_item_field",
                "client_key": "client:a",
                "character_name": "Alice",
                "data": {"ret": 0, "results": [{
                    "ret": 0, "item_index": 270062, "count": 1,
                }]},
            }
            second = {
                **first,
                "ts_ns": 2,
                "stream_offset": 20,
                "data": {"ret": 0, "results": [{
                    "ret": 0, "item_index": 270063, "count": 2,
                }]},
            }
            with mock.patch.object(window, "_fire_alert") as fire:
                window._evaluate_drop_alerts("session", [first])
                window._evaluate_drop_alerts("session", [first, second])
                window._evaluate_drop_alerts("session", [first, second])

            fire.assert_called_once()
            self.assertIn("Drop de Alice", fire.call_args.args[1])
            self.assertIn("x2", fire.call_args.args[1])
            self.assertTrue(window._alert_preferences()["item_drop"])
            window._save_alert_settings()
            window.close()

            reopened = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences,
            )
            reopened.capture_timer.stop()
            reopened._load_settings_fields()
            self.assertTrue(reopened.alert_item_drop.isChecked())
            self.assertEqual(
                set(reopened._alert_preferences()["drop_types"]),
                set(reopened.alert_drop_types),
            )
            reopened.close()

    def test_item_drop_alert_filters_item_type_in_addition_to_rarity(self):
        from app import main as app_main
        from app.ui_qt.main import MainWindow, create_application

        create_application(["item-drop-type-filter-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.alert_item_drop.setChecked(True)
            for category, option in window.alert_drop_types.items():
                option.setChecked(category == "weapon")

            def event(item_index: int, offset: int) -> dict:
                return {
                    "ts_ns": offset,
                    "stream_offset": offset,
                    "bundle_seq": 0,
                    "type": "drop_item_field",
                    "client_key": "client:a",
                    "data": {"ret": 0, "results": [{
                        "ret": 0, "item_index": item_index, "count": 1,
                    }]},
                }

            baseline = event(101, 1)
            skill = event(102, 2)
            weapon = event(103, 3)
            with (
                mock.patch.dict(
                    app_main.DROP_ALERT_CATEGORIES,
                    {"101": "weapon", "102": "skill", "103": "weapon"},
                    clear=False,
                ),
                mock.patch.object(window, "_fire_alert") as fire,
            ):
                window._evaluate_drop_alerts("session", [baseline])
                window._evaluate_drop_alerts("session", [baseline, skill])
                window._evaluate_drop_alerts(
                    "session", [baseline, skill, weapon]
                )

            fire.assert_called_once()
            self.assertIn("Item 103", fire.call_args.args[1])
            window.close()

    def test_combat_refresh_does_not_rebuild_the_pvp_database(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["combat-refresh-performance-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {"session_id": "session", "combat_monitors": []}
            with (
                mock.patch.object(window, "_render_combat") as render_combat,
                mock.patch.object(
                    window, "_render_overview_nearby_mobs"
                ) as render_overview_mobs,
                mock.patch.object(window, "_render_pvp_database") as render_database,
                mock.patch.object(window, "_evaluate_alerts"),
                mock.patch.object(window, "_finish_combat_load"),
            ):
                window._apply_combat_data({
                    "session_id": "session",
                    "combat_monitors": [],
                })

            render_combat.assert_called_once_with()
            render_overview_mobs.assert_called_once_with()
            render_database.assert_not_called()
            window.close()

    def test_game_catalogs_follow_portuguese_and_english_setting(self):
        from app.main import FARM_LABELS_PT_EN
        from app.ui_qt.data import load_boss_catalog, load_farm_catalog

        portuguese = load_farm_catalog("pt")
        english = load_farm_catalog("en")
        (map_pt, spot_pt), (map_en, spot_en) = next(
            iter(FARM_LABELS_PT_EN.items())
        )
        self.assertIn(spot_pt, portuguese[map_pt])
        self.assertIn(spot_en, english[map_en])
        self.assertEqual(
            load_boss_catalog("pt")[845]["name"],
            "Guardião Tyrant Origin",
        )
        self.assertEqual(
            load_boss_catalog("en")[845]["name"],
            "Origin the Tyrant Keeper",
        )

    def test_changing_game_data_language_keeps_farm_and_reloads_snapshot(self):
        from PySide6 import QtCore, QtWidgets

        from app.main import FARM_LABELS_PT_EN
        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["game-data-language-setting-test"])
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
            window.preferences = {"item_name_language": "pt"}
            window._refresh_farm_catalog()
            (map_pt, spot_pt), (map_en, spot_en) = next(
                (
                    pair
                    for pair in FARM_LABELS_PT_EN.items()
                    if pair[0][0] in window.farm_catalog
                    and pair[0][1] in window.farm_catalog[pair[0][0]]
                )
            )
            window.subsession_map.setCurrentText(map_pt)
            window.subsession_spot.setCurrentText(spot_pt)
            window.setting_language.setCurrentIndex(
                window.setting_language.findData("en")
            )
            window.capture_engine = SimpleNamespace(current_session="session")

            with (
                mock.patch.object(QtWidgets.QMessageBox, "information"),
                mock.patch.object(window, "_load_readonly_data") as reload_data,
            ):
                window._save_settings()

            saved = load_preferences(preferences_path)
            self.assertEqual(saved["item_name_language"], "en")
            self.assertEqual(saved["subsession_map"], map_en)
            self.assertEqual(saved["subsession_spot"], spot_en)
            self.assertEqual(window.subsession_map.currentText(), map_en)
            self.assertEqual(window.subsession_spot.currentText(), spot_en)
            reload_data.assert_called_once_with()
            window.capture_engine = None
            window.close()

    def test_memory_limit_is_saved_and_applied_to_new_engines(self):
        from PySide6 import QtWidgets

        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["memory-limit-setting-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences_path = root / "preferences.json"
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences_path,
            )
            window.capture_timer.stop()
            window._load_settings_fields()
            window.setting_capture_directory.setText(str(root / "captures"))
            window.setting_memory_limit.setValue(256)

            with (
                mock.patch.object(QtWidgets.QMessageBox, "information") as notice,
                mock.patch.object(window.global_hotkeys, "stop"),
                mock.patch.object(window.global_hotkeys, "start"),
            ):
                window._save_settings()

            self.assertEqual(load_preferences(preferences_path)["memory_limit_mb"], 256)
            self.assertEqual(window.memory_limits["budget_mb"], 256)
            self.assertEqual(window.capture_engine.memory_budget_mb, 256)
            self.assertEqual(window.snapshot_reader.character_history_limit, 1500)
            self.assertIn("2.816 pacotes", window.setting_memory_summary.text())
            self.assertIn("7.000 eventos", window.setting_memory_summary.text())
            self.assertEqual(notice.call_args.args[2], "Configurações salvas.")
            window.capture_engine = None
            window.close()

    def test_inventory_names_fall_back_to_english_when_pt_translation_is_missing(self):
        from app.ui_qt.data import _inventory_item_name

        expected = {
            270004: "Greater Metal Plate",
            270005: "Greater Abrasive",
            270006: "Greater Fiber Bundle",
            270007: "Greater Filament",
            270008: "Superior Metal Plate",
            270009: "Superior Abrasive",
            270010: "Superior Fiber Bundle",
            270011: "Superior Filament",
        }
        for offset in (0, 5000):
            self.assertEqual(
                {
                    item_index + offset: _inventory_item_name(
                        item_index + offset, "pt"
                    )
                    for item_index in expected
                },
                {item_index + offset: name for item_index, name in expected.items()},
            )

    def test_client_double_click_selects_uid_without_rename_controls(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["client-rename-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {
                "profiles": [{"client_key": "client:a", "name": "Personagem"}],
                "characters": [],
                "character_history": [{
                    "uid": "101",
                    "name": "Alice",
                    "last_seen_at": "2026-08-08T12:00:00Z",
                }],
            }
            with mock.patch(
                "app.ui_qt.main.QtWidgets.QInputDialog.getItem",
                return_value=("Alice · UID 101 · 2026-08-08 12:00", True),
            ):
                window.client_buttons[0].double_clicked.emit()
            self.assertFalse(hasattr(window, "client_uid_buttons"))
            self.assertEqual(
                window.preferences["client_uid_selections"],
                {"client:a": "101"},
            )
            self.assertEqual(window.client_buttons[0].text(), "Cliente 1")
            self.assertIn("Alice · UID 101", window.client_buttons[0].toolTip())
            window.close()

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

    def test_client_selector_asks_source_and_removes_only_the_visual_entry(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from app.ui_qt.data import load_preferences

        create_application(["client-categories-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            self.assertFalse(window.client_buttons[0].isHidden())
            self.assertTrue(all(button.isHidden() for button in window.client_buttons[1:]))

            with mock.patch(
                "app.ui_qt.main.QtWidgets.QInputDialog.getItem",
                return_value=("Emulador local", True),
            ) as choose_source:
                window.add_client_button.click()

            choose_source.assert_called_once()
            self.assertTrue(window.client_buttons[1].isHidden())
            self.assertFalse(window.client_buttons[2].isHidden())
            self.assertEqual(window.visible_client_count, 2)
            self.assertEqual(window.visible_client_slots, [0, 2])
            self.assertEqual(window.client_source.text(), "Emulador local")
            self.assertEqual(
                load_preferences(root / "preferences.json")["visible_client_count"],
                2,
            )
            self.assertEqual(
                load_preferences(root / "preferences.json")["visible_client_slots"],
                [0, 2],
            )
            with mock.patch(
                "app.ui_qt.main.QtWidgets.QMessageBox.information"
            ) as unavailable:
                window._add_client_slot("remote_api")
            unavailable.assert_called_once()
            self.assertEqual(window.visible_client_slots, [0, 2])

            with mock.patch(
                "app.ui_qt.main.QtWidgets.QMessageBox.question",
                return_value=QtWidgets.QMessageBox.StandardButton.Yes,
            ):
                window.remove_client_button.click()

            self.assertEqual(window.visible_client_slots, [0])
            self.assertEqual(window.visible_client_count, 1)
            self.assertFalse(window.client_buttons[0].isHidden())
            self.assertTrue(all(button.isHidden() for button in window.client_buttons[1:]))
            self.assertEqual(
                load_preferences(root / "preferences.json")["visible_client_slots"],
                [0],
            )
            window.exit_requested = True
            window.close()

    def test_inventory_page_follows_selected_client_and_shows_quantity(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["inventory-page-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {
                "profiles": [{
                    "uid": "101",
                    "name": "Alice",
                    "client_key": "client:a",
                }],
                "inventories": {"101": [{
                    "item_index": 270062,
                    "name": "Material de teste",
                    "quantity": 25,
                    "kind": "stackable",
                    "category": "materials",
                    "slot": 7,
                    "refinement": 0,
                    "rarity": 2,
                }]},
            }
            self.assertEqual(
                [
                    window.inventory_category_tabs.tabText(index)
                    for index in range(window.inventory_category_tabs.count())
                ],
                [
                    "Equipamentos",
                    "Consumíveis",
                    "Materiais",
                    "Talicas",
                    "Partes de Rover",
                    "Outros",
                ],
            )
            window.inventory_category_tabs.setCurrentIndex(2)
            window._render_inventory()
            self.assertEqual(window.inventory_table.rowCount(), 1)
            self.assertEqual(window.inventory_table.item(0, 0).text(), "Material de teste")
            self.assertEqual(window.inventory_table.item(0, 1).text(), "25")
            self.assertIn("Alice", window.inventory_status.text())
            self.assertIn("Materiais", window.inventory_status.text())
            window.inventory_category_tabs.setCurrentIndex(0)
            self.assertEqual(window.inventory_table.rowCount(), 0)
            window._set_inventory_category(270062, "other")
            window.inventory_category_tabs.setCurrentIndex(5)
            self.assertEqual(window.inventory_table.rowCount(), 1)
            self.assertEqual(
                window.preferences["inventory_category_overrides"]["270062"],
                "other",
            )
            window.close()

    def test_send_shortcuts_are_absent_from_ui_and_settings(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from app.ui_qt.operations import DEFAULT_GLOBAL_SHORTCUTS

        create_application(["send-shortcuts-removed-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.snapshot = {
            "profiles": [{
                "uid": "101", "name": "Alice", "client_key": "client:a"
            }]
        }
        window._refresh_client_labels()
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
        self.assertIn(("inventory", 0), window.send_buttons)
        self.assertIn(("all", 0), window.send_buttons)
        self.assertEqual(
            window.send_buttons[("inventory", 0)].text(),
            "Enviar Cliente 1 - Alice",
        )
        window.close()

    def test_pvp_database_edits_empty_guild_and_manual_status(self):
        from PySide6 import QtCore, QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from core.knowledge import KnowledgeStore

        create_application(["pvp-database-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            buttons = {
                button.text()
                for button in window.findChildren(QtWidgets.QPushButton)
            }
            self.assertIn("Enviar ao site", buttons)
            self.assertIn("Receber do site", buttons)
            self.assertIn("Atualizar", buttons)
            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                knowledge.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [{
                        "uid": 1,
                        "character_uid": 123,
                        "name": "Rival",
                        "biosuit_item_index": 2075041,
                        "rover_item_index": 4000000,
                    }]},
                }])
            finally:
                knowledge.close()
            window._render_pvp_database()
            self.assertEqual(window.pvp_database_table.rowCount(), 0)
            window.pvp_database_curation_filter.setCurrentIndex(
                window.pvp_database_curation_filter.findData("")
            )
            self.assertEqual(window.pvp_database_table.rowCount(), 1)
            self.assertEqual(window.pvp_database_table.columnCount(), 8)
            self.assertTrue(
                window.pvp_database_table.item(0, 0).flags()
                & QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            self.assertEqual(window.pvp_database_table.item(0, 3).text(), "Arbiter")
            self.assertEqual(window.pvp_database_table.item(0, 4).text(), "Sirius")
            guild = window.pvp_database_table.cellWidget(0, 6)
            status = window.pvp_database_table.cellWidget(0, 7)
            guild.setText("Guilda manual")
            status.setCurrentIndex(status.findData("enemy"))
            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                row = knowledge.characters()[0]
            finally:
                knowledge.close()
            self.assertEqual(row["guild_name"], "Guilda manual")
            self.assertEqual(row["guild_source"], "manual")
            self.assertEqual(row["pvp_status"], "enemy")
            self.assertFalse(guild.isReadOnly())
            window.pvp_sync_interval.setValue(7)
            self.assertEqual(window.preferences["pvp_sync_interval_minutes"], 7)
            status.setCurrentIndex(status.findData("ignored"))
            self.assertEqual(window.pvp_database_table.rowCount(), 0)
            window.close()

    def test_pvp_database_filters_batch_edit_and_persists_columns(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from core.knowledge import KnowledgeStore

        create_application(["pvp-database-batch-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = root / "preferences.json"
            database = root / "capture.sqlite3"
            window = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=preferences,
            )
            window.capture_timer.stop()
            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                knowledge.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [
                        {"character_uid": 101, "name": "Rival Um"},
                        {"character_uid": 102, "name": "Rival Dois"},
                        {"character_uid": 103, "name": "Vizinho"},
                    ]},
                }])
            finally:
                knowledge.close()
            window.pvp_database_curation_filter.setCurrentIndex(
                window.pvp_database_curation_filter.findData("")
            )
            window._render_pvp_database()
            window.pvp_database_filter.setText("Rival")
            window._select_visible_pvp_rows()
            self.assertEqual(len(window._checked_pvp_uids()), 2)
            window.pvp_batch_guild_enabled.setChecked(True)
            window.pvp_batch_guild.setText("Guilda em lote")
            window.pvp_batch_status.setCurrentIndex(
                window.pvp_batch_status.findData("enemy")
            )
            window._apply_pvp_batch_edit()

            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                rows = {
                    row["character_uid"]: row for row in knowledge.characters()
                }
            finally:
                knowledge.close()
            self.assertEqual(rows["101"]["guild_name"], "Guilda em lote")
            self.assertEqual(rows["102"]["pvp_status"], "enemy")
            self.assertEqual(rows["103"]["pvp_status"], "neutral")

            window.pvp_batch_guild_enabled.setChecked(False)
            window.pvp_batch_status.setCurrentIndex(
                window.pvp_batch_status.findData("ally")
            )
            window._apply_pvp_batch_edit()
            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                rows = {
                    row["character_uid"]: row for row in knowledge.characters()
                }
            finally:
                knowledge.close()
            self.assertEqual(rows["101"]["guild_name"], "Guilda em lote")
            self.assertEqual(rows["101"]["pvp_status"], "ally")
            self.assertEqual(rows["102"]["pvp_status"], "ally")
            self.assertEqual(rows["103"]["pvp_status"], "neutral")

            header = window.pvp_database_table.horizontalHeader()
            self.assertTrue(header.sectionsMovable())
            self.assertEqual(
                header.sectionResizeMode(1),
                QtWidgets.QHeaderView.ResizeMode.Interactive,
            )
            header.moveSection(header.visualIndex(1), 2)
            header.resizeSection(1, 222)
            window._save_pvp_header_state()
            expected_position = header.visualIndex(1)
            window.close()

            reopened = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=preferences,
            )
            reopened.capture_timer.stop()
            restored = reopened.pvp_database_table.horizontalHeader()
            self.assertEqual(restored.visualIndex(1), expected_position)
            self.assertEqual(restored.sectionSize(1), 222)
            reopened.close()

    def test_large_pvp_bank_and_inventory_icons_are_memory_bounded(self):
        from app.ui_qt.main import (
            MAX_INVENTORY_ICON_CACHE,
            PVP_DATABASE_ROW_LIMIT,
            MainWindow,
            create_application,
        )
        from core.knowledge import KnowledgeStore

        create_application(["bounded-ui-memory-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                knowledge.observe_events([{
                    "type": "appear_player_list",
                    "data": {"units": [
                        {
                            "character_uid": 1000 + index,
                            "name": f"Jogador {index:03d}",
                        }
                        for index in range(300)
                    ]},
                }])
            finally:
                knowledge.close()

            window.pvp_database_curation_filter.setCurrentIndex(
                window.pvp_database_curation_filter.findData("")
            )
            window._render_pvp_database()
            self.assertEqual(
                window.pvp_database_table.rowCount(), PVP_DATABASE_ROW_LIMIT
            )
            self.assertIn("250 de 300", window.pvp_database_status.text())
            window.pvp_database_filter.setText("Jogador 299")
            self.assertEqual(window.pvp_database_table.rowCount(), 1)
            self.assertEqual(
                window.pvp_database_table.item(0, 2).text(), "Jogador 299"
            )

            with mock.patch(
                "app.ui_qt.main.ITEM_ICON_ARCHIVE", root / "missing-icons.zip"
            ):
                for item_index in range(MAX_INVENTORY_ICON_CACHE + 50):
                    window._inventory_icon(item_index)
            self.assertEqual(
                len(window.inventory_icon_cache), MAX_INVENTORY_ICON_CACHE
            )
            self.assertNotIn(0, window.inventory_icon_cache)
            window.close()

    def test_hidden_pvp_bank_is_not_rebuilt_by_snapshot_refresh(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["lazy-pvp-bank-test"])
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
                "preferences": {},
                "license": {"active": False, "message": "Licença indisponível"},
                "snapshot": {"session_id": None, "subsessions": [], "stats": {}},
                "storage_bytes": 0,
            }

            with mock.patch.object(window, "_render_pvp_database") as render:
                window._apply_readonly_data(payload)

            render.assert_not_called()
            window.close()

    def test_banks_page_renders_pve_locations_and_own_auction_sales(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application
        from core.knowledge import KnowledgeStore
        from core.store import CaptureStore

        create_application(["banks-page-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "capture.sqlite3"
            window = MainWindow(
                load_data=False,
                database_path=database_path,
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            self.assertIsInstance(window.banks_tabs, QtWidgets.QTabWidget)
            self.assertEqual(
                [window.banks_tabs.tabText(index) for index in range(3)],
                ["PvP", "PvE", "Leilão"],
            )

            knowledge = KnowledgeStore(window.knowledge_path)
            try:
                monitor = {"nearby_monsters": [{
                    "npc_index": 305208,
                    "name": "Boss",
                    "level": 70,
                    "max_hp": 1_000_000,
                    "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                }]}
                knowledge.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
                monitor["nearby_monsters"][0]["max_hp"] = 1_100_000
                knowledge.observe_combat(
                    [monitor], location={"map_index": 9, "map_name": "Abismo"}
                )
            finally:
                knowledge.close()

            message = "FL2C_ans_exchange_for_my_sales_list_Message"
            store = CaptureStore(database_path)
            try:
                store.conn.execute(
                    """INSERT INTO events(session_id,source,flow,stream_offset,bundle_seq,
                       ts_ns,opcode,type,character_uid,data_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        "session", "memory", "flow", 1, 0,
                        1_750_000_000_000_000_000, 0x1D07, message, "101",
                        json.dumps({
                            "message": message,
                            "ret": 0,
                            "exchange_server_type": 2,
                            "my_sales_list": [{
                                "exchange_index": 444,
                                "item_info": {
                                    "index": 270062,
                                    "count": 3,
                                    "enchant_level": 7,
                                },
                                "selling_price": 1500,
                            }],
                        }),
                    ),
                )
                store.conn.commit()
            finally:
                store.close()

            window.snapshot = {
                "session_id": "session",
                "profiles": [{
                    "uid": "101", "name": "Alice", "client_key": "client:a"
                }],
            }
            window.license_features.add("monitor-pve")
            window._render_pve_database()
            window._render_auction_database()

            self.assertEqual(window.pve_database_table.rowCount(), 1)
            self.assertEqual(window.pve_database_table.item(0, 3).text(), "1.000.000")
            self.assertIn("Abismo", window.pve_database_table.item(0, 4).text())
            self.assertEqual(window.pve_database_table.item(0, 5).text(), "Revisar 1")
            self.assertEqual(window.auction_database_table.rowCount(), 1)
            self.assertEqual(window.auction_database_table.item(0, 1).text(), "+7")
            self.assertEqual(window.auction_database_table.item(0, 2).text(), "3")
            self.assertEqual(window.auction_database_table.item(0, 3).text(), "1.500")
            self.assertEqual(window.auction_database_table.item(0, 4).text(), "Ativo")
            self.assertNotIn("101", window.auction_database_status.text())
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
                "connection_limits": {"pc": 2, "emulators": 5},
            })
            with mock.patch("app.ui_qt.main._process_memory_bytes", return_value=64 * 1024**2):
                window._capture_tick()
            self.assertEqual(window.top_memory.text(), "RAM  64,0 MiB / 768 MiB")
            self.assertEqual(
                window.monitor_controls["pve"]["enabled"].text(),
                "Ligar monitor Cliente 1  Ctrl+F5",
            )
            self.assertEqual(
                window.monitor_controls["pvp"]["enabled"].text(),
                "Ligar monitor Cliente 1  Ctrl+F6",
            )
            self.assertIn("preserva os arquivos brutos", window.stop_without_reading_button.toolTip())
            capture_buttons = (
                (window.start_button, "captureStart", "#58c96b"),
                (window.pause_button, "capturePause", "#d4a64d"),
                (window.stop_button, "captureStop", "#ff6547"),
                (window.stop_without_reading_button, "captureStopRaw", "#ff6547"),
            )
            for button, object_name, expected_color in capture_buttons:
                self.assertEqual(button.objectName(), object_name)
                self.assertFalse(button.icon().isNull())
                image = button.icon().pixmap(
                    QtCore.QSize(20, 20), QtGui.QIcon.Mode.Normal
                ).toImage()
                colors = {
                    image.pixelColor(x, y).name()
                    for x in range(image.width())
                    for y in range(image.height())
                    if image.pixelColor(x, y).alpha()
                }
                self.assertIn(expected_color, colors)
            window.snapshot = {"combat_monitors": [{
                "client_key": "client:a",
                "character_name": "Personagem A",
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
            window.monitor_client_enabled["pvp"][0] = True
            window.monitor_client_enabled["pvp"][1] = True
            for kind in ("target", "hostile", "non_hostile"):
                window._toggle_pvp_overlay(True, kind)
            target_overlay = window.pvp_overlays["target"]
            hostile_overlay = window.pvp_overlays["hostile"]
            non_hostile_overlay = window.pvp_overlays["non_hostile"]
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem A · Nenhum",
            )
            self.assertEqual(target_overlay.width(), 300)
            self.assertIsNone(target_overlay.parent())
            target_overlay.hide()
            window._keep_overlays_visible()
            self.assertTrue(target_overlay.isVisible())
            self.assertEqual(target_overlay.rows.count(), 0)
            self.assertEqual(hostile_overlay.rows.count(), 0)
            self.assertEqual(non_hostile_overlay.rows.count(), 1)
            window.snapshot["combat_monitors"][0]["pvp"] = {
                "uid": 21,
                "name": "Rival confirmado",
                "hp_percent": 50.0,
                "age_seconds": 1.0,
                "stale": False,
            }
            window.snapshot["combat_monitors"][0]["local"] = {
                "current_hp": 800,
                "max_hp": 1000,
                "hp_percent": 80.0,
            }
            window._render_combat()
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem A",
            )
            self.assertEqual(target_overlay.rows.count(), 1)
            self.assertTrue(target_overlay.local_health.isVisible())
            self.assertEqual(target_overlay.local_health_progress.value(), 800)
            self.assertEqual(target_overlay.local_health_value.text(), "800 / 1.000")
            pvp_labels = target_overlay.rows.itemAt(0).widget().findChildren(
                target_overlay.summary.__class__
            )
            self.assertTrue(any("Rival confirmado" in label.text() for label in pvp_labels))
            self.assertFalse(any("Rigarden" in label.text() for label in pvp_labels))
            window.snapshot["combat_monitors"].append({
                "client_key": "client:b",
                "character_name": "Personagem B",
                "pvp": {
                    "uid": 22,
                    "name": "Alvo do cliente B",
                    "hp_percent": 75.0,
                    "age_seconds": 1.0,
                    "stale": False,
                },
                "nearby_players": [{"uid": 23, "name": "Não deve aparecer"}],
                "bosses": [],
            })
            window.monitor_controls["pvp"]["tabs"].setCurrentIndex(1)
            self.assertEqual(target_overlay.summary.text(), "Alvo atual · Personagem B")
            pvp_labels = target_overlay.rows.itemAt(0).widget().findChildren(
                target_overlay.summary.__class__
            )
            self.assertTrue(any("Alvo do cliente B" in label.text() for label in pvp_labels))
            self.assertFalse(any("Rival confirmado" in label.text() for label in pvp_labels))
            window.snapshot["combat_monitors"][1]["pvp"]["age_seconds"] = 3.1
            window._render_combat()
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem B · Nenhum",
            )
            self.assertEqual(target_overlay.rows.count(), 0)
            window.monitor_client_enabled["pvp"][1] = False
            window._render_combat()
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem B · Monitor desligado",
            )
            self.assertEqual(target_overlay.rows.count(), 0)
            self.assertTrue(
                target_overlay.testAttribute(
                    QtCore.Qt.WidgetAttribute.WA_TranslucentBackground
                )
            )
            self.assertTrue(
                target_overlay.windowFlags()
                & QtCore.Qt.WindowType.FramelessWindowHint
            )
            self.assertEqual(
                target_overlay.cursor().shape(),
                QtCore.Qt.CursorShape.SizeAllCursor,
            )
            position = (
                QtGui.QGuiApplication.primaryScreen().availableGeometry().topLeft()
                + QtCore.QPoint(40, 40)
            )
            target_overlay.mousePressEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                position=lambda: QtCore.QPointF(10, 10),
                accept=lambda: None,
            ))
            target_overlay.mouseMoveEvent(SimpleNamespace(
                buttons=lambda: QtCore.Qt.MouseButton.LeftButton,
                globalPosition=lambda: QtCore.QPointF(position + QtCore.QPoint(10, 10)),
                accept=lambda: None,
            ))
            target_overlay.mouseReleaseEvent(SimpleNamespace(
                button=lambda: QtCore.Qt.MouseButton.LeftButton,
                accept=lambda: None,
            ))
            self.assertEqual(target_overlay.pos(), position)
            self.assertEqual(
                load_preferences(root / "preferences.json")["pvp_overlay_target_position"],
                [position.x(), position.y()],
            )
            window._toggle_pvp_overlay(False, "target")
            window._toggle_pvp_overlay(True, "target")
            self.assertEqual(window.pvp_overlays["target"].pos(), position)
            for kind in ("target", "hostile", "non_hostile"):
                window._toggle_pvp_overlay(False, kind)

            window._toggle_boss_overlay(True)
            window._toggle_boss_dps_overlay(True)
            self.assertNotEqual(window.boss_overlay.pos(), window.boss_dps_overlay.pos())
            self.assertEqual(
                window.boss_overlay_name.text(), "Mecha Corruptor · Personagem A"
            )
            self.assertEqual(window.boss_overlay_hp.text(), "HP 750.000 / 1.000.000")
            self.assertEqual(window.boss_overlay_progress.value(), 750)
            self.assertEqual(
                window.boss_dps_overlay_name.text(), "Mecha Corruptor · Personagem A"
            )
            self.assertIn("25.000", window.boss_dps_overlay_rate.text())
            self.assertIn("Dano acumulado", window.boss_dps_overlay_rate.text())
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
            retained_boss = dict(
                window.snapshot["combat_monitors"][0]["bosses"][0]
            )
            window.snapshot["combat_monitors"][0]["bosses"].clear()
            window._render_combat()
            self.assertEqual(window.boss_overlay_name.text(), "Aguardando boss próximo")
            self.assertEqual(window.boss_overlay_hp.text(), "HP —")
            self.assertEqual(window.boss_overlay_progress.value(), 0)
            self.assertEqual(
                window.boss_dps_overlay_name.text(), "Aguardando boss próximo"
            )
            self.assertEqual(
                window.boss_dps_overlay_rate.text(),
                "DPS — · Dano acumulado — · Tempo restante —",
            )
            window.snapshot["combat_monitors"][0]["bosses"].append(retained_boss)
            window._render_combat()
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
            self.assertEqual(
                window.boss_overlay_name.text(), "Mecha Corruptor · Personagem A"
            )
            self.assertEqual(
                window.boss_dps_overlay_name.text(), "Mecha Corruptor · Personagem A"
            )
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
                "Ligar monitor Cliente 1  Alt+F10",
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
            "connection_limits": {"pc": 2, "emulators": 5},
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
            self.assertIn("Cliente 2", pve["enabled"].text())

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

    def test_boss_and_pvp_focus_are_independent_and_persisted(self):
        from app.ui_qt.data import load_preferences
        from app.ui_qt.main import MainWindow, create_application

        create_application(["monitor-focus-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            preferences = root / "preferences.json"
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences,
            )
            window.capture_timer.stop()
            window.setting_decode_interval.setValue(30)

            window.monitor_controls["pvp"]["focus"].setChecked(True)
            window.monitor_enabled["pvp"] = True
            self.assertEqual(window._general_read_interval_seconds(), 300)
            self.assertFalse(window.monitor_controls["boss"]["focus"].isChecked())

            window.monitor_enabled["pvp"] = False
            self.assertEqual(window._general_read_interval_seconds(), 30)
            self.assertEqual(
                load_preferences(preferences)["monitor_focus"],
                {"pvp": True, "boss": False},
            )
            window.close()

            reopened = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=preferences,
            )
            reopened.capture_timer.stop()
            reopened._load_settings_fields()
            self.assertTrue(reopened.monitor_controls["pvp"]["focus"].isChecked())
            self.assertFalse(reopened.monitor_controls["boss"]["focus"].isChecked())
            reopened.close()

    def test_pvp_accepts_half_second_interval_with_fast_internal_tick(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import MainWindow, create_application

        create_application(["pvp-half-second-interval-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        interval = window.monitor_controls["pvp"]["interval"]

        self.assertIsInstance(interval, QtWidgets.QDoubleSpinBox)
        self.assertEqual(interval.minimum(), 0.5)
        self.assertEqual(interval.singleStep(), 0.5)
        self.assertEqual(interval.value(), 1.0)
        self.assertEqual(window.capture_timer.interval(), 250)

        interval.setValue(0.5)
        self.assertEqual(interval.value(), 0.5)
        window.close()

    def test_capture_tick_waits_for_current_combat_processing(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pvp-no-overlap-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        now = time.monotonic()
        window.capture_engine = SimpleNamespace(
            active=True,
            paused=False,
            current_session="session",
            heartbeat=lambda: None,
            preview_live=lambda: {"available": True},
            read_live=lambda: {"available": True},
        )
        window.last_heartbeat_at = now
        window.last_storage_scan_at = now
        window.next_read_at = now + 30
        window.license_active = False
        window.license_features.discard("map")
        window.monitor_enabled["pvp"] = True
        window.monitor_next_due["pvp"] = 0.0
        window.combat_load_running = True
        window._rotate_auto_subsessions = mock.Mock()
        window._run_capture_operation = mock.Mock()

        window._capture_tick()

        window._run_capture_operation.assert_not_called()
        window.capture_engine = None
        window.close()

    def test_pvp_target_refreshes_faster_than_nearby_players(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pvp-nearby-throttle-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.monitor_client_enabled["pvp"][0] = True
        window.monitor_enabled["pvp"] = True
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "character_name": "Leitor",
            "pvp": {
                "name": "Alvo A", "current_hp": 90, "max_hp": 100,
                "hp_percent": 90.0, "age_seconds": 0.1, "stale": False,
            },
            "nearby_players": [{
                "character_uid": "2", "name": "Próximo A",
                "hp_percent": 100.0, "age_seconds": 0.1, "stale": False,
            }],
        }]}
        widgets = window.combat_widgets["pvp"][0]
        window.pvp_nearby_next_due = 0.0

        with (
            mock.patch.object(window, "_render_nearby", wraps=window._render_nearby) as render,
            mock.patch("app.ui_qt.main.time.monotonic", return_value=100.0),
        ):
            window._render_combat()
            self.assertEqual(window.pvp_nearby_next_due, 110.0)
            first_count = sum(
                call.args[0] is widgets and call.args[2] == "pvp"
                for call in render.call_args_list
            )
            window.snapshot["combat_monitors"][0]["pvp"]["name"] = "Alvo B"
            with mock.patch("app.ui_qt.main.time.monotonic", return_value=100.5):
                window._render_combat()
            second_count = sum(
                call.args[0] is widgets and call.args[2] == "pvp"
                for call in render.call_args_list
            )

        self.assertEqual(first_count, 1)
        self.assertEqual(second_count, 1)
        self.assertIn("Alvo B", widgets["target"].text())
        window.close()

    def test_pvp_target_is_above_nearby_players(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pvp-target-order-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        widgets = window.combat_widgets["pvp"][0]
        layout = window.combat_page_layouts["pvp"]["cards"][0].layout()

        self.assertLess(
            layout.indexOf(widgets["target"]),
            layout.indexOf(widgets["nearby_empty"].parentWidget()),
        )
        window.close()

    def test_pve_page_exposes_only_the_current_target(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pve-current-target-only-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        widgets = window.combat_widgets["pve"][0]

        self.assertIsNone(widgets["nearby_layout"])
        self.assertIsNone(widgets["nearby_empty"])
        window.close()

    def test_pve_shows_player_health_bar_above_current_target(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pve-player-health-order-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.monitor_client_enabled["pve"][0] = True
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "character_name": "Leitor",
            "local": {
                "current_hp": 750,
                "max_hp": 1000,
                "hp_percent": 75.0,
            },
            "pve": {
                "name": "Xenogeyser",
                "current_hp": 400,
                "max_hp": 500,
                "hp_percent": 80.0,
                "age_seconds": 0.1,
                "stale": False,
            },
        }]}

        window._render_combat()

        widgets = window.combat_widgets["pve"][0]
        layout = window.combat_page_layouts["pve"]["cards"][0].layout()
        self.assertLess(
            layout.indexOf(widgets["self_progress"]),
            layout.indexOf(widgets["progress"]),
        )
        self.assertEqual(widgets["self_progress"].value(), 750)
        self.assertEqual(widgets["progress"].value(), 800)
        self.assertEqual(widgets["self_health"].text(), "Sua vida: 750 / 1,000 · 75,00%")
        window.close()

    def test_program_status_badge_uses_actual_pvp_damage(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["program-status-badge-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.license_active = True
        window.license_features.add("map")
        window.monitor_enabled["pvp"] = True
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "local_combat_uid": 10,
            "pvp_activity": {
                "direction": "entrada", "last_seen_ns": time.time_ns(),
            },
            "nearby_players": [],
        }], "map": {"clients": [{
            "client_key": "client:a",
            "observed_at_ns": time.time_ns(),
            "teleporting": True,
            "stale": False,
        }]}}

        window._render_program_status()

        self.assertEqual(window.top_program_status.text(), "TELEPORTANDO")
        window.snapshot["map"]["clients"][0]["teleporting"] = False
        window._render_program_status()
        self.assertEqual(window.top_program_status.text(), "PVP")
        window.close()

    def test_program_status_samples_farm_without_opening_pve_monitor(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["program-status-independent-pve-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        now = time.monotonic()
        window.license_features.update(
            {"monitor-pve", "monitor-pvp", "monitor-boss"}
        )
        window.monitor_enabled = {"pve": False, "pvp": False, "boss": False}
        window.capture_engine = SimpleNamespace(
            active=True,
            paused=False,
            current_session="session",
            heartbeat=lambda: None,
            preview_live=lambda: {"available": True},
            read_live=lambda: {"available": True},
        )
        window.last_heartbeat_at = now
        window.last_storage_scan_at = now
        window.next_read_at = now + 30
        window.program_status_preview_next_due = 0.0
        window._rotate_auto_subsessions = mock.Mock()
        window._run_capture_operation = mock.Mock()

        self.assertEqual(
            window._combat_decode_modes(), ("pve", "pvp", "boss")
        )
        window._capture_tick()

        window._run_capture_operation.assert_called_once()
        self.assertEqual(
            window._run_capture_operation.call_args.args[0], "preview"
        )
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "local_combat_uid": 10,
            "pve_activity": {"last_seen_ns": time.time_ns()},
        }]}
        window._render_program_status()
        self.assertEqual(window.top_program_status.text(), "FARM")
        window.capture_engine = None
        window.close()

    def test_status_alerts_repeat_threat_but_not_state_transitions(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["program-status-alerts-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.alert_threat.setChecked(True)
        window.alert_farm_started.setChecked(True)
        window.alert_teleporting.setChecked(True)
        window.previous_program_status = {
            "client:a": {
                "activity": "idle",
                "signals": {"threat": False, "teleporting": False},
            }
        }
        snapshot = {"clients": [{
            "client_key": "client:a",
            "activity": "farm",
            "signals": {"threat": True, "teleporting": True},
        }]}

        with mock.patch.object(window, "_fire_alert") as fire:
            window._evaluate_status_alerts(snapshot)
            self.assertEqual(
                {call.args[0] for call in fire.call_args_list},
                {
                    "status-threat:client:a",
                    "status-farm:client:a",
                    "status-teleport:client:a",
                },
            )
            fire.reset_mock()
            window._evaluate_status_alerts(snapshot)
            fire.assert_called_once_with(
                "status-threat:client:a",
                "Ameaça em Cliente 1: inimigo confirmado próximo.",
            )
        window.close()

    def test_pvp_hostiles_expire_without_new_packets(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["pvp-hostile-expiry-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.license_client.require = mock.Mock(return_value={"active": True})
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base", "monitor-pvp"],
            "connection_limits": {"pc": 2, "emulators": 1},
        })
        observed_at = time.time_ns()
        window.monitor_client_enabled["pvp"][0] = True
        window.monitor_enabled["pvp"] = True
        window.snapshot = {"combat_monitors": [{
            "client_key": "client:a",
            "character_name": "Leitor",
            "pvp": {},
            "nearby_players": [{
                "character_uid": "2",
                "name": "Hostil antigo",
                "pvp_status": "enemy",
                "last_seen_ns": observed_at,
                "age_seconds": 0.0,
                "stale": False,
            }],
        }]}
        window._render_combat()
        window._toggle_pvp_overlay(True, "hostile")
        self.assertEqual(window.pvp_overlays["hostile"].rows.count(), 1)
        self.assertEqual(
            window.combat_widgets["pvp"][0]["nearby_layout"].count(), 1
        )

        window.pvp_nearby_next_due = 0.0
        with mock.patch(
            "app.ui_qt.main.time.time_ns",
            return_value=observed_at + 16_000_000_000,
        ):
            window._capture_tick()

        self.assertEqual(window.pvp_overlays["hostile"].rows.count(), 0)
        self.assertEqual(
            window.combat_widgets["pvp"][0]["nearby_layout"].count(), 0
        )
        self.assertEqual(
            window.combat_widgets["pvp"][0]["nearby_empty"].text(),
            "Nenhum registro recente.",
        )
        window._toggle_pvp_overlay(False, "hostile")
        window.close()

    def test_monitor_page_requests_checkpoint_preview_without_rotation(self):
        from app.ui_qt.main import MONITOR_PAGE_INDEX, MainWindow, create_application

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
        window.license_active = False
        window.license_features.discard("map")
        window.monitor_client_enabled["pve"][0] = True
        window.monitor_enabled["pve"] = True
        window.page_stack.setCurrentIndex(MONITOR_PAGE_INDEX)
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
        self.assertTrue(any("Dano por guilda" in text for text in labels))
        self.assertTrue(any(text == "Karvalho" for text in labels))
        self.assertTrue(any("Jogador 6" in text for text in labels))
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
        from app.ui_qt.main import MONITOR_PAGE_INDEX, MainWindow, create_application

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
            for mode, page_index in (("pvp", MONITOR_PAGE_INDEX),):
                with self.subTest(mode=mode):
                    window.page_stack.setCurrentIndex(page_index)
                    window.monitor_tabs.setCurrentIndex(1)
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
            self.assertEqual(window.subsession_name.text(), "Rascunho")
            self.assertEqual(window.subsession_map.currentText(), "Mapa rascunho")
            self.assertEqual(window.subsession_spot.currentText(), "Spot rascunho")
            self.assertEqual(window.subsession_mobs.count(), 1)
            self.assertEqual(
                window.subsession_mobs.item(0).checkState(),
                QtCore.Qt.CheckState.Checked,
            )
            window.close()

    def test_auto_context_subsession_can_start_without_manual_catalog_values(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["auto-context-subsession-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {"session_id": "session", "profiles": []}
            window._reload_snapshot = mock.Mock()
            window.subsession_auto_context.setChecked(True)

            with mock.patch.object(window, "_client_uid_for", return_value=None):
                window._save_subsession()

            store = CaptureStore(root / "capture.sqlite3")
            try:
                saved = store.subsessions("session")[0]
            finally:
                store.close()
            self.assertTrue(saved["auto_context"])
            self.assertEqual(saved["name"], "Subsessão automática")
            self.assertEqual((saved["map_name"], saved["spot_name"], saved["mobs"]), ("", "", []))
            window.close()

    def test_new_subsession_uses_active_capture_session_over_stale_snapshot(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["active-session-subsession-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {"session_id": "stale-session", "profiles": []}
            window.capture_engine = SimpleNamespace(current_session="active-session")
            window._reload_snapshot = mock.Mock()
            window.subsession_auto_context.setChecked(True)

            with mock.patch.object(window, "_client_uid_for", return_value=None):
                window._save_subsession()

            store = CaptureStore(root / "capture.sqlite3")
            try:
                self.assertEqual(len(store.subsessions("active-session")), 1)
                self.assertEqual(store.subsessions("stale-session"), [])
            finally:
                store.close()
            window.capture_engine = None
            window.close()

    def test_new_subsession_button_fills_current_location_and_nearby_mobs(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["subsession-fill-current-context-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.farm_catalog = {
                "Ferro-Velho de Androides": {
                    "8F": {"Mob A": (10,), "Mob B": (11,)}
                }
            }
            window.subsession_map.clear()
            window.subsession_map.addItem("Ferro-Velho de Androides")
            window._subsession_map_changed("Ferro-Velho de Androides")
            window.snapshot = {
                "map": {"clients": [{
                    "client_key": "client:a",
                    "map_enabled": True,
                    "map_index": 638,
                    "map_name": "Ferro-Velho de Androides",
                    "region_name": "8F",
                    "region_confidence": "map-index-floor",
                    "stale": False,
                }]},
                "combat_monitors": [{
                    "client_key": "client:a",
                    "nearby_monsters": [
                        {"name": "Mob A", "level": 10, "stale": False},
                        {"name": "Mob B", "level": 11, "stale": False},
                    ],
                }],
            }

            window.subsession_fill_context.click()

            self.assertEqual(
                window.subsession_map.currentText(), "Ferro-Velho de Androides"
            )
            self.assertEqual(window.subsession_spot.currentText(), "8F")
            self.assertEqual(window._selected_mobs(), ["Mob A", "Mob B"])
            self.assertEqual(window.subsession_other_mob.text(), "")
            self.assertIn("Preenchido com mapa, spot, 2 mob(s)", window.subsession_context_status.text())
            window.close()

    def test_subsession_history_shows_audited_automatic_context(self):
        from app.ui_qt.main import (
            SUBSESSION_COLUMN_INDEX,
            MainWindow,
            create_application,
        )
        from core.store import CaptureStore

        create_application(["audited-auto-context-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = CaptureStore(root / "capture.sqlite3")
            try:
                store.start_subsession(
                    "sub", "session", "Automática", client_key="client:a",
                    auto_context=True, started_ns=1,
                )
                store.update_auto_subsession_context(
                    "session", "client:a", map_name="Mapa", spot_name="Spot",
                    mobs=["Mob"], context_source="proximity",
                    context_confidence="stable", context_observation_count=4,
                    context_first_seen_ns=2, context_updated_ns=7,
                )
                saved = store.subsessions("session")
            finally:
                store.close()
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {
                "subsessions": saved,
                "subsession_summaries": {},
                "profiles": [],
            }
            window._render_subsessions()

            context = window.subsession_table.item(
                0, SUBSESSION_COLUMN_INDEX["context"]
            )
            self.assertEqual(context.text(), "Automático · 4 leituras")
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

        self.assertIn("QMessageBox { background: #0B1217; }", app.styleSheet())
        self.assertIn("QMenu { background: #0B1217;", app.styleSheet())
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
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base"],
            "connection_limits": {"pc": 2, "emulators": 1},
        })
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
        self.assertIn(
            "não existem dados",
            window.send_buttons[("codex", 1)].toolTip(),
        )
        window.capture_engine = None
        window.close()

    def test_drop_alert_requests_realtime_preview_without_combat_monitor(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["drop-alert-preview-test"])
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
        window._run_capture_operation = (
            lambda name, callback: calls.append(name) or callback()
        )
        window.next_read_at = time.monotonic() + 30
        window.drop_alert_next_due = 0.0
        window.alert_item_drop.setChecked(True)

        window._capture_tick()

        self.assertIn("preview", calls)
        self.assertNotIn("rotate", calls)
        self.assertIn("alerta:", window.top_next_read.text())
        window.capture_engine = None
        window.close()

    def test_map_requests_realtime_position_preview_without_monitors(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["map-realtime-preview-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        now = time.monotonic()
        calls = []
        window.capture_engine = SimpleNamespace(
            active=True,
            paused=False,
            current_session="session",
            heartbeat=lambda: None,
            preview_live=lambda: calls.append("preview") or {"available": True},
            read_live=lambda: calls.append("rotate") or {"available": True},
        )
        window.license_active = True
        window.license_features = {"map"}
        window.last_license_refresh_at = now
        window.last_heartbeat_at = now
        window.last_storage_scan_at = now
        window.next_read_at = now + 30
        window.map_preview_next_due = 0.0
        window._rotate_auto_subsessions = lambda: None
        window._run_capture_operation = (
            lambda name, callback: calls.append(name) or callback()
        )

        window._capture_tick()

        self.assertIn("preview", calls)
        self.assertNotIn("rotate", calls)
        self.assertIn("mapa:", window.top_next_read.text())
        window.capture_engine = None
        window.close()

    def test_send_during_capture_reads_current_segment_before_upload(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["send-live-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base"],
            "connection_limits": {"pc": 2, "emulators": 1},
        })
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

    def test_exp_rank_upload_is_automatic_and_deduplicated(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["auto-exp-rank-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.capture_engine = SimpleNamespace(current_session="session")
            window.site_profile = SimpleNamespace(connected=True)
            window.license_features.add("exp-ranking")
            window.preferences = {"auto_exp_rank_signatures": {}}
            operations = []
            window._run_site_operation = lambda name, callback: operations.append(name)
            completeness = {"value": "partial"}
            store = SimpleNamespace(
                exp_rank_snapshot=lambda _session: {
                    "snapshot_key": "1:44",
                    "signature": "a" * 64,
                    "completeness": completeness["value"],
                    "records": [{"rank": 1}],
                },
                close=lambda: None,
            )
            with mock.patch("app.ui_qt.main.CaptureStore", return_value=store):
                window._maybe_auto_exp_rank_upload()
                self.assertEqual(operations, [])
                completeness["value"] = "complete"
                window._maybe_auto_exp_rank_upload()
                self.assertEqual(operations, ["auto_exp_rank"])
                window._site_operation_finished(
                    "auto_exp_rank", {"records": 1}, None
                )
                window._maybe_auto_exp_rank_upload()
                self.assertEqual(operations, ["auto_exp_rank"])
            window.capture_engine = None
            window.close()

    def test_exp_rank_page_marks_partial_data_and_hides_internal_identifiers(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["exp-rank-page-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.license_features.add("exp-ranking")
        window.snapshot = {
            "exp_rank": {
                "record_count": 2,
                "completeness": "partial",
                "conflict_count": 0,
                "missing_positions": list(range(3, 101)),
                "captured_at_ns": 1_700_000_000_000_000_000,
                "records": [{
                    "character_uid": "88776655",
                    "character_name": "Alice",
                    "guild_name": "Karvalho",
                    "guild_mark_hex": "84000457",
                    "total_exp": 999_999,
                    "rank": 1,
                    "previous_rank": 2,
                }, {
                    "character_uid": "11223344",
                    "character_name": "Bruno",
                    "guild_name": "Outra",
                    "guild_mark_hex": "ffffffff",
                    "total_exp": 888_888,
                    "rank": 2,
                    "previous_rank": 2,
                }],
            }
        }

        window._render_exp_rank()

        self.assertEqual(window.exp_rank_table.rowCount(), 2)
        self.assertEqual(window.exp_rank_table.columnCount(), 6)
        self.assertEqual(
            [
                window.exp_rank_table.horizontalHeaderItem(column).text()
                for column in range(window.exp_rank_table.columnCount())
            ],
            [
                "Posição", "Variação", "Personagem", "Guilda",
                "Nível", "EXP total (%)",
            ],
        )
        self.assertFalse(window.exp_rank_table.alternatingRowColors())
        self.assertEqual(window.exp_rank_state.text(), "Captura parcial")
        visible = " ".join(
            window.exp_rank_table.item(row, column).text()
            for row in range(window.exp_rank_table.rowCount())
            for column in range(window.exp_rank_table.columnCount())
        )
        self.assertIn("Alice", visible)
        self.assertIn("Karvalho", visible)
        self.assertNotEqual(window.exp_rank_table.item(0, 4).text(), "—")
        self.assertIn("%", window.exp_rank_table.item(0, 5).text())
        self.assertNotIn("88776655", visible)
        self.assertNotIn("84000457", visible)
        window.exp_rank_search.setText("outra")
        self.assertEqual(window.exp_rank_table.rowCount(), 1)
        self.assertEqual(window.exp_rank_table.item(0, 2).text(), "Bruno")
        window.close()

    def test_exp_rank_csv_exports_active_filtered_table(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["exp-rank-csv-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.license_features.add("exp-ranking")
        window.snapshot = {
            "exp_rank": {
                "record_count": 2,
                "completeness": "partial",
                "records": [{
                    "character_uid": "88776655",
                    "character_name": "Alice",
                    "guild_name": "Karvalho",
                    "total_exp": 999_999,
                    "rank": 1,
                    "previous_rank": 2,
                }, {
                    "character_uid": "11223344",
                    "character_name": "Bruno",
                    "guild_name": "Outra",
                    "total_exp": 888_888,
                    "rank": 2,
                    "previous_rank": 2,
                }],
            },
            "exp_rank_history": [{
                "captured_at_ns": 1_700_000_000_000_000_000,
                "records": [{
                    "character_name": "Alice",
                    "guild_name": "Karvalho",
                    "rank": 1,
                    "level": 50,
                    "level_percent": 25.5,
                    "total_exp": 999_999,
                    "gained_exp": 10_000,
                    "gained_percent": 1.5,
                    "exp_per_hour": 20_000,
                    "exp_percent_per_hour": 3.0,
                }],
            }],
        }
        window._render_exp_rank()
        window.exp_rank_search.setText("Alice")

        with tempfile.TemporaryDirectory() as temporary:
            current_path = Path(temporary) / "ranking-atual.csv"
            self.assertEqual(window._export_exp_rank_csv(current_path), current_path)
            current_csv = current_path.read_text(encoding="utf-8-sig")
            self.assertTrue(current_csv.startswith(
                "Posição;Variação;Personagem;Guilda;Nível;EXP total (%)\n"
            ))
            self.assertIn("Alice", current_csv)
            self.assertNotIn("Bruno", current_csv)
            self.assertNotIn("88776655", current_csv)

            window.exp_rank_tabs.setCurrentIndex(1)
            history_path = Path(temporary) / "ranking-historico"
            expected_history_path = history_path.with_suffix(".csv")
            self.assertEqual(
                window._export_exp_rank_csv(history_path), expected_history_path
            )
            history_csv = expected_history_path.read_text(encoding="utf-8-sig")
            self.assertTrue(history_csv.startswith(
                "Captura;Posição;Personagem;Nível;EXP total (%);"
                "Ganho (%);EXP/h (%)\n"
            ))
            self.assertIn("Alice", history_csv)
            self.assertIn("20.000", history_csv)
        window.close()

    def test_map_page_renders_capacity_and_hides_internal_identifiers(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["map-page-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.snapshot = {"map": {
            "schema_version": 1,
            "capacity": 2,
            "active_count": 2,
            "limited_count": 1,
            "clients": [{
                "client_key": "client:a",
                "map_enabled": True,
                "reason": "active",
                "character_name": "Local",
                "map_index": 1202,
                "position": {"x": 10.0, "y": 20.0, "z": 30.0},
                "age_seconds": 1.5,
                "stale": False,
                "teleporting": False,
                "nearby_players": [{
                    "name": "Vizinho",
                    "guild_name": "Karvalho",
                    "position": {"x": 13.0, "y": 24.0, "z": 30.0},
                    "distance": 5.0,
                    "entity_uid": 88776655,
                    "character_uid": 11223344,
                }],
            }, {
                "client_key": "client:b",
                "map_enabled": True,
                "reason": "awaiting_data",
                "nearby_players": [],
            }, {
                "client_key": "client:c",
                "map_enabled": False,
                "reason": "capacity_limit",
                "nearby_players": [],
            }],
        }}

        window._render_map()

        self.assertEqual(window.map_capacity.text(), "2/2 vagas em uso · 1 limitado(s)")
        self.assertEqual(window.map_metric_labels["map"].text(), "Mapa #1202")
        self.assertEqual(window.map_players_table.rowCount(), 1)
        visible = " ".join(
            window.map_players_table.item(row, column).text()
            for row in range(window.map_players_table.rowCount())
            for column in range(window.map_players_table.columnCount())
        )
        self.assertIn("Vizinho", visible)
        self.assertNotIn("88776655", visible)
        self.assertNotIn("11223344", visible)
        self.assertIn("Vizinho", window.overview_nearby_names.text())
        self.assertEqual(
            window.overview_map_preview.players[0]["name"], "Vizinho"
        )
        self.assertEqual(window.map_page_preview.local_position["x"], 10.0)
        self.assertEqual(window.map_page_preview.players[0]["name"], "Vizinho")
        window.active_client = 2
        window._render_map()
        self.assertEqual(window.map_state.text(), "Limite do Mapa")
        self.assertEqual(window.map_players_table.rowCount(), 0)
        window.close()

    def test_manual_map_is_display_fallback_and_automatic_keeps_priority(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["manual-map-fallback-test"])
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(
                load_data=False,
                preferences_path=Path(folder) / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {"map": {
                "capacity": 2,
                "active_count": 1,
                "clients": [{
                    "client_key": "client:a",
                    "map_enabled": True,
                    "reason": "awaiting_data",
                    "map_index": 999_999,
                    "map_name": "Mapa #999999",
                    "nearby_players": [],
                }],
            }}

            with mock.patch.object(
                window,
                "_choose_manual_map_name",
                return_value="Mundo Novus",
            ):
                window._set_manual_map_fallback()

            client = window.snapshot["map"]["clients"][0]
            self.assertEqual(client["map_name"], "Mundo Novus")
            self.assertIn(client["map_index"], {101, 103})
            self.assertEqual(client["map_source"], "manual_fallback")
            self.assertIsNotNone(window.overview_map_preview._map_pixmap())
            self.assertIn("automático continua ativo", window.map_status.text())

            window.snapshot["map"]["clients"][0].update(
                map_index=602,
                map_name="Base Secreta Nemesis",
                region_name="2F",
                region_confidence="map-index-floor",
                map_source="automatic",
                reason="active",
            )
            window._render_map()
            self.assertEqual(
                window.map_metric_labels["map"].text(),
                "Base Secreta Nemesis",
            )
            self.assertEqual(window.overview_map_region.text(), "Região 2F")
            self.assertEqual(
                window.snapshot["map"]["clients"][0]["map_source"], "automatic"
            )
            window.close()

    def test_legacy_manual_android_map_resolves_packaged_preview_index(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["legacy-manual-map-preview-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.preferences["manual_map_fallbacks"] = {
            "client:a": {
                "map_name": "Ferro-Velho de Androides",
                "region_name": "9F",
            }
        }

        fallback = window._manual_map_fallbacks()["client:a"]
        self.assertEqual(fallback["map_index"], 639)
        window.snapshot = {"map": {"clients": [{
            "client_key": "client:a",
            "map_index": None,
            "map_name": None,
            "nearby_players": [],
        }]}}
        window._render_map()

        self.assertEqual(window.overview_map_preview.map_index, 639)
        self.assertIsNotNone(window.overview_map_preview._map_pixmap())
        window.close()

    def test_manual_map_catalog_groups_duplicate_albern_area_ids(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["manual-map-deduplication-test"])
        with tempfile.TemporaryDirectory() as folder:
            window = MainWindow(
                load_data=False,
                preferences_path=Path(folder) / "preferences.json",
            )
            window.capture_timer.stop()
            window.preferences["item_name_language"] = "en"
            with mock.patch.object(
                window, "_choose_manual_map_name", return_value=None
            ) as choose:
                window._set_manual_map_fallback()

            options = choose.call_args.args[0]
            albern = [
                option for option in options
                if option[1] == "Albern Crater Area 1"
            ]
            self.assertEqual(len(albern), 1)
            self.assertIn("#751/#754", albern[0][0])
            android_8f = [
                option for option in options
                if option[1] == "Android Junkyard · 8F"
            ]
            self.assertEqual(len(android_8f), 1)
            self.assertIn("#638", android_8f[0][0])
            window.close()

    def test_albern_754_preview_uses_packaged_map_and_player_names(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["albern-map-preview-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        preview = window.overview_map_preview
        preview.resize(420, 320)
        preview.set_snapshot(
            754,
            {"x": 909.0, "y": 573.0, "z": 0.0},
            [{
                "name": "Jogador próximo",
                "position": {"x": 1200.0, "y": 900.0, "z": 0.0},
            }],
        )

        self.assertIsNotNone(preview._map_pixmap())
        self.assertEqual(preview.players[0]["name"], "Jogador próximo")
        self.assertFalse(preview.grab().isNull())
        window.close()

    def test_overview_map_is_compact_and_map_page_keeps_navigation_controls(self):
        from PySide6 import QtCore
        from app.ui_qt.main import MAP_PREVIEW_ASSETS, MainWindow, create_application

        application = create_application(["map-navigation-controls-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        preview = window.overview_map_preview
        preview.resize(480, 320)
        metadata = MAP_PREVIEW_ASSETS[638]
        first_position = {
            "x": float(metadata["min_x"]) + float(metadata["span_x"]) * 0.35,
            "y": float(metadata["min_y"]) + float(metadata["span_y"]) * 0.45,
            "z": 0.0,
        }
        preview.set_snapshot("638", first_position, [])
        application.processEvents()

        self.assertEqual(preview.map_index, 638)
        self.assertEqual(preview.zoom_percent(), 100)
        self.assertFalse(preview.interactive)
        self.assertFalse(preview.follow_character)
        self.assertLessEqual(preview.maximumWidth(), 420)
        pixmap, metadata = preview._map_pixmap()
        target = preview._target_rect(preview._area(), pixmap, metadata)
        anchored_point = preview._project(first_position, target, metadata)
        self.assertIsNotNone(anchored_point)
        self.assertGreater(
            abs(anchored_point.x() - preview._area().center().x()),
            10.0,
        )
        preview.pan_by(QtCore.QPointF(35.0, 20.0))
        preview.zoom_in()
        self.assertFalse(preview.follow_character)
        self.assertEqual(preview.pan_offset, QtCore.QPointF())
        self.assertEqual(preview.zoom_percent(), 100)
        stable_target = preview._target_rect(preview._area(), pixmap, metadata)
        self.assertEqual(
            preview._project(first_position, stable_target, metadata),
            anchored_point,
        )

        second_position = dict(first_position)
        second_position["x"] += float(metadata["span_x"]) * 0.1
        page_preview = window.map_page_preview
        page_preview.resize(760, 420)
        page_preview.set_snapshot(638, second_position, [])
        window.map_page_zoom_in.click()
        page_preview.pan_by(QtCore.QPointF(35.0, 20.0))
        self.assertFalse(page_preview.follow_character)
        self.assertNotEqual(page_preview.pan_offset, QtCore.QPointF())
        window.map_page_focus.click()
        application.processEvents()
        self.assertTrue(page_preview.follow_character)
        self.assertEqual(page_preview.local_position["x"], second_position["x"])
        self.assertEqual(page_preview.zoom_percent(), 125)
        self.assertIn("125%", window.map_page_zoom.text())
        page_pixmap, page_metadata = page_preview._map_pixmap()
        page_target = page_preview._target_rect(
            page_preview._area(), page_pixmap, page_metadata
        )
        focused_point = page_preview._project(
            second_position, page_target, page_metadata
        )
        self.assertTrue(page_target.contains(focused_point))
        self.assertFalse(preview.grab().isNull())
        self.assertFalse(page_preview.grab().isNull())
        for map_index in (601, 602, 605, 606, 607):
            preview.set_snapshot(map_index, {}, [])
            self.assertIsNotNone(preview._map_pixmap())
        self.assertLessEqual(len(preview._map_pixmaps), 4)
        window.close()

    def test_high_orbit_preview_applies_live_map_calibration(self):
        from PySide6 import QtCore
        from app.ui_qt.main import MAP_PREVIEW_ASSETS, _MapPreview

        metadata = MAP_PREVIEW_ASSETS[643]
        target = QtCore.QRectF(0.0, 0.0, 192.0, 192.0)
        point = _MapPreview._project(
            {"x": 1182.8017578125, "y": 683.6202392578125},
            target,
            metadata,
        )

        self.assertIsNotNone(point)
        self.assertAlmostEqual(point.x(), 136.967, places=2)
        self.assertAlmostEqual(point.y(), 91.549, places=2)
        self.assertGreater(abs(point.x() - target.center().x()), 35.0)
        self.assertEqual(
            metadata["live_position_transform"]["scale_x"], 25.0
        )

    def test_general_summary_cards_are_compact_and_show_requested_totals(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["compact-general-summary-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.visible_client_slots = [0]
        window.capture_engine = None
        window.snapshot = {
            "session_id": "session",
            "stats": {"ended_ns": 3_601_000_000_000},
            "characters": [{
                "client_key": "client:a",
                "uid": "101",
                "name": "Carvalho",
                "summary": {
                    "recognized_at_ns": 1_000_000_000,
                    "character_class": "Arbiter",
                    "biosuit_name": "Destilador Terminator",
                    "biosuit_grade": 4,
                    "rover_item_index": 4_000_000,
                    "rover_name": "Sirius",
                    "rover_grade": 1,
                    "diamonds": 123,
                    "exp": 125_000_000,
                    "exp_percent": 42.5,
                    "exp_gained": 1_000,
                    "exp_gained_percent": 2.5,
                    "credits_total": 9_876_543,
                    "credits": 5_740,
                    "contribution": 60_500,
                },
            }],
        }

        window._render_general_summary()

        card = window.general_summary_cards[0]
        self.assertLessEqual(card["frame"].maximumWidth(), 560)
        self.assertEqual(card["character"].text(), "Carvalho")
        self.assertEqual(card["class_name"].text(), "Arbiter")
        self.assertEqual(card["biosuit_name"].text(), "Destilador Terminator")
        self.assertEqual(card["rover_name"].text(), "Sirius")
        self.assertEqual(card["diamonds"].text(), "123")
        self.assertEqual(
            card["exp_percent"].text(), "125.000.000 (42,50%)"
        )
        self.assertEqual(card["exp_progress"].value(), 4_250)
        self.assertEqual(card["values"]["duration"].text(), "01:00:00")
        self.assertEqual(
            card["values"]["session_exp"].text(), "1.000 (2,50%)"
        )
        self.assertEqual(
            card["values"]["credits"].text(),
            "Total 9.876.543 · Sessão +5.740",
        )
        self.assertEqual(
            card["values"]["contribution"].text(),
            "+60.500 · 60.500/h",
        )

        window.snapshot["characters"][0]["summary"]["contribution"] = 120_000
        window.snapshot["stats"]["ended_ns"] += 30_000_000_000
        window._render_general_summary()
        self.assertEqual(
            card["values"]["contribution"].text(),
            "+120.000 · 60.500/h",
        )
        window.snapshot["stats"]["ended_ns"] += 30_000_000_000
        window._render_general_summary()
        self.assertEqual(
            card["values"]["contribution"].text(),
            "+120.000 · 118.033/h",
        )
        window.close()

    def test_general_summary_restores_missing_rover_from_confirmed_history(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["general-summary-rover-history-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.visible_client_slots = [0]
        window.snapshot = {
            "session_id": "session",
            "stats": {},
            "characters": [{
                "client_key": "client:a",
                "uid": "101",
                "name": "Carvalho",
                "summary": {},
            }],
            "client_bindings": [{
                "client_key": "client:a",
                "uid": "101",
                "name": "Carvalho",
                "source": "canonical",
            }],
            "character_history": [{
                "uid": "101",
                "name": "Carvalho",
                "rover_item_index": 4_000_000,
            }],
        }

        window._render_general_summary()

        card = window.general_summary_cards[0]
        self.assertEqual(card["rover_name"].text(), "Sirius")
        self.assertEqual(card["rover_icon"].toolTip(), "Sirius")
        window.close()

    def test_all_program_tables_allow_resize_reorder_and_double_click_autofit(self):
        from PySide6 import QtWidgets
        from app.ui_qt.main import MainWindow, create_application

        create_application(["standard-table-columns-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        tables = window.page_stack.findChildren(QtWidgets.QTableWidget)
        self.assertGreaterEqual(len(tables), 10)
        for table in tables:
            header = table.horizontalHeader()
            self.assertTrue(header.sectionsMovable())
            for column in range(table.columnCount()):
                self.assertEqual(
                    header.sectionResizeMode(column),
                    QtWidgets.QHeaderView.ResizeMode.Interactive,
                )

        table = window.exp_rank_table
        table.setRowCount(1)
        table.setItem(0, 0, QtWidgets.QTableWidgetItem("Conteúdo muito longo para autofit"))
        table.setColumnWidth(0, 40)
        table.horizontalHeader().sectionDoubleClicked.emit(0)
        self.assertGreater(table.columnWidth(0), 40)
        window.close()

    def test_requested_map_previews_are_packaged_and_novus_regions_remain_available(self):
        from app.ui_qt.main import MAP_PREVIEW_ASSETS, MainWindow, create_application

        requested = {
            101, 103,
            751, 752, 754, 755,
            *range(635, 641), *range(4211, 4215),
            601, 602, 605, 606, 607,
            *range(611, 627), 4625, 4645, 4665, 4685,
            610, 630, 4603,
            642, 643, 644, 4504, 4554,
        }
        self.assertEqual(set(MAP_PREVIEW_ASSETS), requested)
        self.assertTrue(all(item["path"].is_file() for item in MAP_PREVIEW_ASSETS.values()))

        create_application(["novus-map-region-preview-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        preview = window.overview_map_preview
        preview.resize(420, 320)
        preview.set_snapshot(
            101,
            {"x": -478_707.281, "y": 89_840.0, "z": 0.0},
            [],
        )

        self.assertEqual(preview.current_region_name("pt"), "Colônia Saura")
        self.assertIsNotNone(preview._map_pixmap())
        self.assertFalse(preview.grab().isNull())
        window.close()

    def test_manual_map_dialog_opens_searchable_catalog_list(self):
        from app.ui_qt.main import _MapSelectionDialog, create_application

        application = create_application(["manual-map-list-test"])
        dialog = _MapSelectionDialog(
            [
                ("Mundo Novus · #101", "Mundo Novus"),
                ("Base Secreta Nemesis 2º Andar · #602", "Base Secreta Nemesis 2º Andar"),
            ],
            "",
        )
        self.assertEqual(dialog.map_list.count(), 2)
        dialog.search.setText("nemesis")
        application.processEvents()
        self.assertTrue(dialog.map_list.item(0).isHidden())
        self.assertFalse(dialog.map_list.item(1).isHidden())
        self.assertEqual(
            dialog.selected_map_name(), "Base Secreta Nemesis 2º Andar"
        )
        dialog.close()

    def test_overview_drops_use_item_icons_and_rarity_colors(self):
        from app.ui_qt import main as qt_main
        from app.ui_qt.main import MainWindow, create_application

        create_application(["overview-drop-rarity-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.snapshot = {"drop_events": [{
            "ts_ns": time.time_ns(),
            "stream_offset": 10,
            "bundle_seq": 0,
            "type": "drop_item_field",
            "client_key": "client:a",
            "data": {"ret": 0, "results": [{
                "ret": 0,
                "item_index": 42,
                "count": 2,
            }]},
        }]}
        with mock.patch.dict(qt_main.ITEM_GRADES, {"42": 4}, clear=False):
            window._render_overview_drops()

        marker, name, age = window.overview_drop_rows[0]
        self.assertFalse(marker.pixmap().isNull())
        self.assertIn("#b66cff", marker.styleSheet().casefold())
        self.assertIn("épico", marker.toolTip().casefold())
        self.assertIn("#b66cff", name.styleSheet().casefold())
        self.assertTrue(name.text().endswith("  x2"))
        self.assertEqual(age.text(), "0s")
        window.close()

    def test_overview_recent_drops_only_show_active_client(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["overview-drop-client-isolation-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        now_ns = time.time_ns()
        window.snapshot = {"drop_events": [{
            "ts_ns": now_ns - 1_000_000_000,
            "stream_offset": 10,
            "bundle_seq": 0,
            "type": "drop_item_field",
            "client_key": "client:a",
            "data": {"ret": 0, "results": [{
                "ret": 0, "item_index": 42, "count": 1,
            }]},
        }, {
            "ts_ns": now_ns,
            "stream_offset": 20,
            "bundle_seq": 0,
            "type": "drop_item_field",
            "client_key": "client:b",
            "data": {"ret": 0, "results": [{
                "ret": 0, "item_index": 43, "count": 1,
            }]},
        }]}

        window.active_client = 0
        window._render_overview_drops()
        client_a_text = window.overview_drop_rows[0][1].text()
        window.active_client = 1
        window._render_overview_drops()
        client_b_text = window.overview_drop_rows[0][1].text()

        self.assertNotEqual(client_a_text, client_b_text)
        self.assertNotEqual(client_a_text, "Aguardando drop")
        self.assertNotEqual(client_b_text, "Aguardando drop")
        window.close()

    def test_drops_page_lists_filters_and_paginates_confirmed_items(self):
        from app.ui_qt import main as qt_main
        from app.ui_qt.main import DROPS_PAGE_INDEX, MainWindow, create_application

        create_application(["drops-page-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        now_ns = time.time_ns()
        window.snapshot = {"drop_events": [{
            "ts_ns": now_ns - 2_000_000_000,
            "stream_offset": 10,
            "bundle_seq": 0,
            "type": "drop_item_field",
            "client_key": "client:a",
            "character_name": "Alice",
            "data": {"ret": 0, "results": [{
                "ret": 0, "item_index": 42, "count": 2,
            }, {
                "ret": 0, "item_index": 43, "count": 1,
            }]},
        }], "loot_announcements": [{
            "ts_ns": now_ns - 1_000_000_000,
            "client_key": "client:a",
            "data": {"announcements": [{
                "player_name": "Bob",
                "item_index": 42,
                "count": 3,
            }]},
        }, {
            "ts_ns": now_ns,
            "client_key": "client:b",
            "data": {"announcements": [{
                "player_name": "Bob",
                "item_index": 42,
                "count": 3,
            }]},
        }]}
        with mock.patch.dict(
            qt_main.ITEM_GRADES, {"42": 4, "43": 1}, clear=False
        ):
            window._render_drops()
            window._render_loot_announcements()

            self.assertEqual(window.drops_table.rowCount(), 2)
            self.assertIn("3 item(ns)", window.drops_summary.text())
            visible = " ".join(
                window.drops_table.item(row, column).text()
                for row in range(window.drops_table.rowCount())
                for column in range(window.drops_table.columnCount())
            )
            self.assertIn("Alice", visible)
            self.assertIn("Épico", visible)
            self.assertFalse(window.drops_table.item(0, 4).icon().isNull())
            self.assertEqual(window.loot_announcements_table.rowCount(), 1)
            announcement_text = " ".join(
                window.loot_announcements_table.item(0, column).text()
                for column in range(window.loot_announcements_table.columnCount())
            )
            self.assertIn("Bob", announcement_text)
            self.assertIn("Épico", announcement_text)
            self.assertIn("Cliente 1", announcement_text)
            self.assertIn("Cliente 2", announcement_text)
            self.assertFalse(
                window.loot_announcements_table.item(0, 3).icon().isNull()
            )
            window.drops_rarity_filter.setCurrentIndex(
                window.drops_rarity_filter.findData(4)
            )
            self.assertEqual(window.drops_table.rowCount(), 1)
            window.drops_search.setText("sem resultado")
            self.assertEqual(window.drops_table.rowCount(), 0)

        window._open_drops_page()
        self.assertEqual(window.page_stack.currentIndex(), DROPS_PAGE_INDEX)
        window.close()

    def test_local_api_setting_starts_loopback_service_only_with_license(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["local-api-setting-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.setting_local_api.setChecked(True)
        window.setting_local_api_port.setValue(17620)
        api = mock.Mock(active=True, port=17620)
        api.start.return_value = 17620
        token_store = mock.Mock()
        token_store.load_or_create.return_value = "t" * 43

        window.license_active = False
        window._sync_local_api()
        self.assertIn("licença válida", window.local_api_status.text())

        window.license_active = True
        with mock.patch(
            "app.ui_qt.main.LocalApiTokenStore", return_value=token_store
        ), mock.patch("app.ui_qt.main.LocalOutputApi", return_value=api) as api_class:
            window._sync_local_api()

        self.assertTrue(window.local_api_copy_token.isEnabled())
        self.assertIn("127.0.0.1:17620", window.local_api_status.text())
        api_class.assert_called_once()
        self.assertEqual(
            api_class.call_args.kwargs["health_provider"],
            window._health_api_snapshot,
        )
        window.setting_local_api.setChecked(False)
        window._sync_local_api()
        api.stop.assert_called_once()
        window.close()

    def test_health_api_snapshot_reports_memory_checkpoint_and_stream(self):
        from app.ui_qt import main

        main.create_application(["health-api-snapshot-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = main.MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.snapshot = {
                "session_id": "session-1",
                "session_checkpoints": [{
                    "checkpoint_ns": time.time_ns() - 2_000_000_000,
                    "reason": "interval",
                }],
            }
            window.capture_engine = SimpleNamespace(
                active=True,
                paused=False,
                current_session="session-1",
                live_events=SimpleNamespace(metrics=lambda: {
                    "worker_alive": True,
                    "queue_depth": 3,
                    "queue_limit": 64,
                    "flow_count": 99,
                }),
            )
            with mock.patch.object(
                main, "_process_memory_bytes", return_value=200 * 1024 * 1024
            ):
                health = window._health_api_snapshot()
                window._render_integration_health()

            self.assertEqual(health["capture"]["state"], "active")
            self.assertTrue(health["capture"]["session_available"])
            self.assertEqual(health["checkpoint"]["reason"], "interval")
            self.assertGreaterEqual(health["checkpoint"]["age_seconds"], 2)
            self.assertEqual(health["stream"]["queue_depth"], 3)
            self.assertEqual(health["stream"]["flow_count"], 99)
            self.assertEqual(
                health["process"]["memory_bytes"], 200 * 1024 * 1024
            )
            self.assertEqual(window.integration_health_labels["capture"].text(), "Ativa")
            self.assertIn("200,0 MiB", window.integration_health_labels["memory"].text())
            self.assertIn(
                "Salvamento periódico",
                window.integration_health_labels["checkpoint"].text(),
            )
            self.assertIn("Fila 3", window.integration_health_labels["stream"].text())
            window.capture_engine = None
            window.close()

    def test_integrations_share_the_settings_navigation_page(self):
        from app.ui_qt.main import (
            DROPS_PAGE_INDEX,
            SESSIONS_PAGE_INDEX,
            SETTINGS_PAGE_INDEX,
            SUBSESSIONS_PAGE_INDEX,
            MainWindow,
            create_application,
        )

        create_application(["consolidated-navigation-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()

        sessions_page = window.page_stack.widget(SESSIONS_PAGE_INDEX)
        subsessions_page = window.page_stack.widget(SUBSESSIONS_PAGE_INDEX)
        drops_page = window.page_stack.widget(DROPS_PAGE_INDEX)
        settings_page = window.page_stack.widget(SETTINGS_PAGE_INDEX)
        self.assertFalse(sessions_page.isAncestorOf(window.subsession_stack))
        self.assertTrue(subsessions_page.isAncestorOf(window.subsession_stack))
        self.assertTrue(drops_page.isAncestorOf(window.drops_table))
        self.assertTrue(settings_page.isAncestorOf(window.setting_profile))
        self.assertTrue(settings_page.isAncestorOf(window.setting_local_api))
        self.assertTrue(settings_page.isAncestorOf(window.setting_capture_directory))
        self.assertEqual(window.settings_sections.count(), 2)
        self.assertEqual(set(window.integration_health_labels), {
            "capture", "memory", "checkpoint", "stream",
        })
        window.close()

    def test_beta_parity_actions_are_connected_and_overview_uses_dashboard_cards(self):
        from PySide6 import QtWidgets

        from app.ui_qt.main import (
            DROPS_PAGE_INDEX,
            SUBSESSIONS_PAGE_INDEX,
            SUBSESSION_COLUMNS,
            MainWindow,
            create_application,
        )

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
        self.assertFalse(hasattr(window, "discard_previous"))
        self.assertTrue(hasattr(window, "continue_button"))
        window.showMaximized()
        app.processEvents()
        window._sync_overview_layout()
        self.assertEqual(len(window.overview_cards), 4)
        self.assertTrue(window.session_card.isVisible())
        self.assertTrue(window.subsession_card.isVisible())
        self.assertTrue(window.session_card.isAncestorOf(window.dashboard_status))
        self.assertTrue(window.session_card.isAncestorOf(window.character_icon))
        self.assertTrue(window.session_card.isAncestorOf(window.rover_icon))
        self.assertEqual(
            window.overview_grid.getItemPosition(
                window.overview_grid.indexOf(window.subsession_card)
            ),
            (0, 1, 1, 1),
        )
        self.assertEqual(window.overview_grid.indexOf(window.nearby_mobs_card), -1)
        self.assertEqual(window.overview_grid.indexOf(window.drops_card), -1)
        window.snapshot = {
            "session_id": "session",
            "profiles": [],
            "characters": [
                {"name": "A", "client_key": "client:a", "summary": {}},
                {"name": "B", "client_key": "client:b",
                 "summary": {"exp_percent": 17.42}},
            ],
            "subsessions": [{
                "id": "sub-1", "name": "Spot leste", "client_key": "client:a",
                "started_ns": time.time_ns() - 60_000_000_000,
                "ended_ns": None, "map_name": "Caverna Ether",
                "mobs": ["Aracnídeo Mutante"], "mob_levels": {"Aracnídeo Mutante": "67-69"},
            }],
            "subsession_summaries": {"sub-1": {"kills": 10, "exp_gained_percent": 0.2}},
            "stats": {},
        }
        window._render_overview()
        self.assertTrue(window.subsession_card.isVisible())
        self.assertTrue(window.session_card.isVisible())
        self.assertEqual(window.active_subsession.text(), "Spot leste")
        self.assertEqual(
            set(window.subsession_card_field_actions),
            {
                key
                for key, _label, _width, _visible
                in SUBSESSION_COLUMNS[1:]
            },
        )
        self.assertEqual(window.session_duration.text(), "00:00:00")
        self.assertEqual(window.overview_grid.indexOf(window.nearby_mobs_card), -1)
        self.assertEqual(
            window.overview_grid.getItemPosition(
                window.overview_grid.indexOf(window.map_card)
            ),
            (1, 0, 1, 1),
        )
        self.assertTrue(window.overview_map_preview.hasHeightForWidth())
        self.assertEqual(window.overview_map_preview.heightForWidth(480), 480)
        self.assertEqual(
            window.overview_grid.getItemPosition(
                window.overview_grid.indexOf(window.health_card)
            ),
            (1, 1, 1, 1),
        )
        window.view_subsession_button.click()
        self.assertEqual(window.page_stack.currentIndex(), SUBSESSIONS_PAGE_INDEX)
        window.page_stack.setCurrentIndex(0)
        window.view_drops_button.click()
        self.assertEqual(window.page_stack.currentIndex(), DROPS_PAGE_INDEX)
        window.close()

    def test_overview_does_not_render_nearby_mobs_card(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["overview-nearby-mobs-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.snapshot = {
            "session_id": "session",
            "stats": {},
            "combat_monitors": [{
                "client_key": "client:a",
                "nearby_monsters": [
                    {
                        "npc_index": 101,
                        "name": "Aracnídeo Mutante",
                        "level": 68,
                        "max_hp": 612_000,
                        "current_hp": 428_600,
                        "stale": False,
                    },
                    {
                        "npc_index": 101,
                        "name": "Aracnídeo Mutante",
                        "level": 68,
                        "max_hp": 612_000,
                        "current_hp": 100,
                        "stale": False,
                    },
                    {
                        "npc_index": 202,
                        "name": "Escorpião de Ether",
                        "level": 69,
                        "max_hp": 720_000,
                        "current_hp": 1,
                        "stale": False,
                    },
                    {
                        "npc_index": 303,
                        "name": "Antigo",
                        "level": 70,
                        "max_hp": 800_000,
                        "stale": True,
                    },
                ],
            }],
        }

        window._render_overview()

        self.assertEqual(window.overview_grid.indexOf(window.nearby_mobs_card), -1)
        self.assertTrue(window.nearby_mobs_card.isHidden())
        self.assertEqual(window.overview_mobs_table.rowCount(), 0)
        window.close()

    def test_combat_loader_uses_exp_rank_records_from_the_current_snapshot(self):
        from app.ui_qt import main
        from app.ui_qt.main import MainWindow, create_application

        class ImmediateThread:
            def __init__(self, *, target, daemon):
                self.target = target

            def start(self):
                self.target()

        create_application(["combat-loader-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            window = MainWindow(
                load_data=False,
                database_path=root / "capture.sqlite3",
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            records = [{"rank": 1, "name": "Personagem", "exp": 123}]
            window.snapshot = {
                "session_id": "session-1",
                "exp_rank": {"records": records},
                "map": {"clients": []},
                "subsessions": [],
            }
            loaded = []
            failed = []
            window.combat_loaded.connect(loaded.append)
            window.combat_failed.connect(failed.append)
            reader = mock.Mock()
            reader.load_combat.return_value = {
                "session_id": "session-1",
                "combat_monitors": [],
            }
            knowledge = mock.Mock()
            with (
                mock.patch.object(main, "ReadOnlySnapshotReader", return_value=reader),
                mock.patch.object(main, "KnowledgeStore", return_value=knowledge),
                mock.patch.object(main.threading, "Thread", ImmediateThread),
            ):
                window._load_combat_data()

            self.assertEqual(failed, [])
            self.assertEqual(len(loaded), 1)
            knowledge.observe_exp_rank_records.assert_called_once_with(
                records, session_id="session-1"
            )
            self.assertFalse(window.combat_load_running)
            window.close()

    def test_timed_subsession_creates_the_next_entry_when_enabled(self):
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
                auto_context=True, context_source="proximity",
                context_confidence="stable", context_observation_count=3,
                context_first_seen_ns=started - 5_000_000_000,
                context_updated_ns=started,
            )
            store.close()
            window = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=preferences,
            )
            window.capture_timer.stop()
            window.capture_engine = SimpleNamespace(current_session="session-1")
            window._load_readonly_data = lambda: None
            window.subsession_auto_next.setChecked(True)
            window.subsession_auto_minutes.setValue(10)
            with mock.patch(
                "app.ui_qt.main.time.time_ns",
                return_value=started + 2 * interval + 1,
            ):
                window._rotate_auto_subsessions()
            store = CaptureStore(database, readonly=True)
            entries = store.subsessions("session-1")
            store.close()
            self.assertEqual(len(entries), 2)
            self.assertEqual(sum(item["ended_ns"] is not None for item in entries), 1)
            self.assertEqual(sum(item["ended_ns"] is None for item in entries), 1)
            self.assertTrue(all(
                item["context_source"] == "proximity"
                and item["context_confidence"] == "stable"
                and item["context_observation_count"] == 3
                for item in entries
            ))
            ended = next(item for item in entries if item["ended_ns"] is not None)
            active = next(item for item in entries if item["ended_ns"] is None)
            self.assertEqual(
                (ended["started_ns"], ended["ended_ns"]),
                (started, started + interval),
            )
            self.assertEqual(active["started_ns"], started + interval)
            self.assertEqual(active["duration_minutes"], 10)
            window.capture_engine = None
            window.close()

    def test_timed_subsession_does_not_create_next_when_disabled(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["manual-subsession-timeout-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            store = CaptureStore(database)
            started = 1_000_000_000
            store.start_subsession(
                "sub-1", "session-1", "Farm",
                client_key="client:a", duration_minutes=5, started_ns=started,
            )
            store.close()
            window = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.capture_engine = SimpleNamespace(current_session="session-1")
            window._load_readonly_data = lambda: None
            window.subsession_auto_next.setChecked(False)
            with mock.patch(
                "app.ui_qt.main.time.time_ns",
                return_value=started + 5 * 60 * 1_000_000_000 + 1,
            ):
                window._rotate_auto_subsessions()
            store = CaptureStore(database, readonly=True)
            entries = store.subsessions("session-1")
            store.close()
            self.assertEqual(len(entries), 1)
            self.assertIsNotNone(entries[0]["ended_ns"])
            window.capture_engine = None
            window.close()

    def test_signal_ended_subsession_never_creates_the_next_entry(self):
        from app.ui_qt.main import MainWindow, create_application
        from core.store import CaptureStore

        create_application(["teleport-subsession-end-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "capture.sqlite3"
            started = 1_000_000_000
            teleport_at = started + 10 * 1_000_000_000
            store = CaptureStore(database)
            store.start_subsession(
                "sub-1", "session-1", "Farm",
                client_key="client:a", duration_minutes=60,
                end_on_teleport=True, started_ns=started,
            )
            store.close()
            window = MainWindow(
                load_data=False,
                database_path=database,
                preferences_path=root / "preferences.json",
            )
            window.capture_timer.stop()
            window.capture_engine = SimpleNamespace(current_session="session-1")
            window._load_readonly_data = lambda: None
            window.subsession_auto_next.setChecked(True)
            window.snapshot = {
                "combat_monitors": [],
                "map": {"clients": [{
                    "client_key": "client:a",
                    "teleporting": True,
                    "teleport_observed_at_ns": teleport_at,
                }]},
            }
            with mock.patch(
                "app.ui_qt.main.time.time_ns", return_value=teleport_at + 1
            ):
                window._rotate_auto_subsessions()
            store = CaptureStore(database, readonly=True)
            entries = store.subsessions("session-1")
            store.close()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["ended_ns"], teleport_at)
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
        from app.ui_qt.main import PROFILE_LABEL, STYLE, VERSION
        from app.ui_qt.smoke import run_smoke

        result = run_smoke()

        self.assertEqual(result["platform"], "offscreen")
        self.assertEqual((result["width"], result["height"]), (1180, 664))
        self.assertEqual((result["minimum_width"], result["minimum_height"]), (1180, 664))
        self.assertEqual(
            result["title"], f"RF QOL — {VERSION} ({PROFILE_LABEL})"
        )
        self.assertEqual(result["page_count"], 13)
        self.assertEqual(result["active_page"], 1)
        self.assertEqual(result["navigation"], [
            "Visão geral", "Resumo Geral", "Sessões", "Subsessões", "Monitoramento", "Bancos",
            "Ranking de EXP", "Mapa", "Drops", "Drops de jogadores", "Alertas",
            "Configurações",
            "Inventário",
        ])
        self.assertIsInstance(result["navigation_enabled"]["Monitoramento"], bool)
        self.assertFalse(result["frameless"])
        self.assertEqual(result["overview_groups"], 4)
        self.assertEqual(result["overview_metrics"], 18)
        widget_rule = STYLE.split("QWidget {", 1)[1].split("}", 1)[0]
        self.assertNotIn("background", widget_rule)

    def test_sidebar_scroll_content_keeps_dark_theme_between_and_below_buttons(self):
        from app.ui_qt.main import MainWindow, create_application

        app = create_application(["sidebar-dark-scroll-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.resize(1180, 1400)
        window.show()
        app.processEvents()

        content = window.sidebar_nav_content
        first = window.nav_buttons[0]
        second = window.nav_buttons[1]
        last = window.nav_buttons[-1]
        image = content.grab().toImage()
        between_buttons = (first.geometry().bottom() + second.geometry().top()) // 2
        below_buttons = min(image.height() - 2, last.geometry().bottom() + 20)
        samples = (
            (image.width() // 2, max(1, between_buttons)),
            (image.width() // 2, max(1, below_buttons)),
        )
        for x, y in samples:
            color = image.pixelColor(
                min(x, image.width() - 1), min(y, image.height() - 1)
            )
            self.assertLess(color.lightness(), 80, color.name())

        window.close()

    def test_module_license_keeps_pvp_visible_and_hides_unlicensed_boss(self):
        from app.ui_qt.main import MONITOR_PAGE_INDEX, MainWindow, create_application

        create_application(["module-license-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base", "monitor-pvp"],
        })

        self.assertFalse(window.nav_buttons[MONITOR_PAGE_INDEX].isHidden())
        self.assertTrue(window.nav_buttons[MONITOR_PAGE_INDEX].isEnabled())
        self.assertFalse(window.monitor_tabs.isTabEnabled(0))
        self.assertTrue(window.monitor_tabs.isTabEnabled(1))
        self.assertFalse(window.monitor_tabs.isTabVisible(2))
        self.assertFalse(window.monitor_controls["boss"]["overlay"].isEnabled())
        self.assertFalse(window.monitor_controls["boss"]["dps_overlay"].isEnabled())
        window._select_category("emulator")
        self.assertTrue(window.client_buttons[2].isEnabled())
        self.assertTrue(all(button.isEnabled() for button in window.client_buttons[3:]))
        pvp_tabs = window.monitor_controls["pvp"]["tabs"]
        self.assertTrue(pvp_tabs.isTabEnabled(2))
        self.assertTrue(all(pvp_tabs.isTabEnabled(index) for index in range(3, 7)))
        from app.ui_qt.main import EXP_RANK_PAGE_INDEX, MAP_PAGE_INDEX
        self.assertFalse(window.nav_buttons[EXP_RANK_PAGE_INDEX].isEnabled())
        self.assertFalse(window.nav_buttons[MAP_PAGE_INDEX].isEnabled())
        self.assertFalse(window.banks_tabs.isTabEnabled(1))
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
            self.assertEqual(
                window.subsession_fill_context.text(),
                "Buscar localização e mobs agora",
            )
            self.assertEqual(window.subsession_filter_level_from.value(), 0)
            self.assertEqual(window.subsession_filter_level_to.value(), 0)
            self.assertEqual(window.subsession_filter_level_from.specialValueText(), "")
            self.assertEqual(window.subsession_filter_level_to.specialValueText(), "")
            self.assertEqual(window.subsession_filter_level_from.width(), 110)
            self.assertEqual(window.subsession_filter_level_to.width(), 110)
            form = window.subsession_form_layout
            client_row = form.getWidgetPosition(window.subsession_client)[0]
            context_row = form.getWidgetPosition(
                window.subsession_fill_context.parentWidget()
            )[0]
            context_status_row = form.getWidgetPosition(
                window.subsession_context_status
            )[0]
            observation_row = form.getWidgetPosition(window.subsession_name)[0]
            filter_row = form.getWidgetPosition(
                window.subsession_filter_level_from.parentWidget()
            )[0]
            mobs_row = form.getWidgetPosition(window.subsession_mobs)[0]
            self.assertEqual(context_row, client_row + 1)
            self.assertEqual(context_status_row, context_row + 1)
            self.assertEqual(observation_row, context_status_row + 1)
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
                ["Carvalho", "01:00:00", "10", "1.000 (2,50%)", "2,50%", "1.000 (2,50%)", "2,50%", "60.500"],
            )
            self.assertTrue(
                window.subsession_table.isColumnHidden(
                    SUBSESSION_COLUMN_INDEX["exp_percent"]
                )
            )
            self.assertTrue(
                window.subsession_table.isColumnHidden(
                    SUBSESSION_COLUMN_INDEX["exp_hour_percent"]
                )
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
            self.assertTrue(window.setting_detailed_log.isChecked())
            self.assertFalse(window.setting_detailed_log.isEnabled())
            window.setting_detailed_log.setChecked(False)
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
            self.assertNotIn("automatic", saved["Favorito completo"])

            window.subsession_client.setCurrentIndex(0)
            window.subsession_other_mob.clear()
            window.subsession_level_from.setValue(0)
            window.subsession_level_to.setValue(0)
            window.subsession_duration.setValue(0)
            window.subsession_name.clear()
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
            self.assertIn("Alice · UID 101", window.client_buttons[0].toolTip())
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
