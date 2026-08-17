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
    def test_pvp_database_is_hidden_and_sync_disabled(self):
        from app.ui_qt.main import MainWindow, PAGES, create_application

        create_application(["pvp-database-disabled-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        bank_index = next(
            index for index, (title, _description) in enumerate(PAGES)
            if title == "Banco PvP"
        )
        monitor_index = next(
            index for index, (title, _description) in enumerate(PAGES)
            if title == "Monitor PvP"
        )

        self.assertTrue(window.nav_buttons[bank_index].isHidden())
        self.assertFalse(window.nav_buttons[bank_index].isEnabled())
        self.assertFalse(window.nav_buttons[monitor_index].isHidden())
        window.license_client.require = mock.Mock(return_value={"active": True})
        window._apply_license({
            "active": True,
            "message": "Licença válida",
            "features": ["base", "monitor-pvp"],
            "connection_limits": {"pc": 2, "emulators": 1},
        })
        with mock.patch.object(window, "_resume_active_monitors"):
            window.monitor_controls["pvp"]["enabled"].setChecked(True)
        self.assertTrue(window.monitor_enabled["pvp"])
        window.pending_observation_session = "session"
        with mock.patch.object(window, "_run_site_operation") as run_site:
            window._maybe_sync_observations(time.monotonic(), force=True)
        run_site.assert_not_called()
        self.assertEqual(window.pending_observation_session, "")
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
                mock.patch.object(window, "_render_pvp_database") as render_database,
                mock.patch.object(window, "_evaluate_alerts"),
                mock.patch.object(window, "_finish_combat_load"),
            ):
                window._apply_combat_data({
                    "session_id": "session",
                    "combat_monitors": [],
                })

            render_combat.assert_called_once_with()
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
            self.assertEqual(window.client_buttons[0].text(), "Cliente A")
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
            "Enviar Cliente A - Alice",
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
            self.assertEqual(window.pvp_database_table.rowCount(), 1)
            self.assertEqual(window.pvp_database_table.columnCount(), 7)
            self.assertTrue(
                window.pvp_database_table.item(0, 0).flags()
                & QtCore.Qt.ItemFlag.ItemIsUserCheckable
            )
            self.assertEqual(window.pvp_database_table.item(0, 3).text(), "Arbiter")
            self.assertEqual(window.pvp_database_table.item(0, 4).text(), "Sirius")
            guild = window.pvp_database_table.cellWidget(0, 5)
            status = window.pvp_database_table.cellWidget(0, 6)
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
            window._render_combat()
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem A",
            )
            self.assertEqual(target_overlay.rows.count(), 1)
            pvp_labels = target_overlay.rows.itemAt(0).widget().findChildren(
                target_overlay.summary.__class__
            )
            self.assertTrue(any("Rival confirmado" in label.text() for label in pvp_labels))
            self.assertFalse(any("Rigarden" in label.text() for label in pvp_labels))
            window.snapshot["combat_monitors"][0]["character_name"] = ""
            window._render_combat()
            self.assertEqual(
                target_overlay.summary.text(),
                "Alvo atual · Personagem não vinculado",
            )
            self.assertEqual(target_overlay.rows.count(), 1)
            window.snapshot["combat_monitors"][0]["character_name"] = "Personagem A"
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

    def test_pve_is_per_client_and_pvp_keeps_only_one_active_route(self):
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
            pvp["tabs"].setCurrentIndex(1)
            pvp["enabled"].setChecked(True)
            self.assertEqual(
                window.monitor_client_enabled["pvp"],
                [False, True, False, False, False, False, False],
            )
            self.assertTrue(window.monitor_enabled["pvp"])
            pvp["tabs"].setCurrentIndex(0)
            self.assertFalse(pvp["enabled"].isChecked())
        window.close()

    def test_pvp_alerts_only_use_the_active_route(self):
        from app.ui_qt.main import MainWindow, create_application

        create_application(["monitor-exclusive-pvp-alert-test"])
        window = MainWindow(load_data=False)
        window.capture_timer.stop()
        window.monitor_client_enabled["pvp"][1] = True
        monitors = [
            {
                "client_key": "client:a",
                "nearby_players": [{"name": "Rota A", "guild_name": "Guilda A"}],
                "pvp": {"direction": "entrada", "name": "Atacante A"},
                "bosses": [{"uid": "boss-a", "name": "Boss A"}],
            },
            {
                "client_key": "client:b",
                "nearby_players": [{"name": "Rota B", "guild_name": "Guilda B"}],
                "pvp": {"direction": "entrada", "name": "Atacante B"},
            },
        ]
        alerts = {
            "characters_enabled": True,
            "characters": "Rota A, Rota B",
            "guilds_enabled": True,
            "guilds": "Guilda A, Guilda B",
            "pvp_hit": True,
            "boss_detected": True,
            "low_hp": False,
        }
        with (
            mock.patch.object(window, "_alert_preferences", return_value=alerts),
            mock.patch.object(window, "_fire_alert") as fire_alert,
        ):
            window._evaluate_alerts(monitors)

        fired_keys = [call.args[0] for call in fire_alert.call_args_list]
        self.assertIn("character:rota b", fired_keys)
        self.assertIn("guild:guilda b", fired_keys)
        self.assertIn("pvp_hit", fired_keys)
        self.assertIn("boss:boss-a", fired_keys)
        self.assertNotIn("character:rota a", fired_keys)
        self.assertNotIn("guild:guilda a", fired_keys)
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
            window.preferences = {"auto_exp_rank_signatures": {}}
            operations = []
            window._run_site_operation = lambda name, callback: operations.append(name)
            store = SimpleNamespace(
                exp_rank_snapshot=lambda _session: {
                    "snapshot_key": "1:44",
                    "signature": "a" * 64,
                    "completeness": "complete",
                    "records": [{"rank": 1}],
                },
                close=lambda: None,
            )
            with mock.patch("app.ui_qt.main.CaptureStore", return_value=store):
                window._maybe_auto_exp_rank_upload()
                self.assertEqual(operations, ["auto_exp_rank"])
                window._site_operation_finished(
                    "auto_exp_rank", {"records": 1}, None
                )
                window._maybe_auto_exp_rank_upload()
                self.assertEqual(operations, ["auto_exp_rank"])
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
        self.assertEqual(result["title"], "RF QOL — 1.0.10")
        self.assertEqual(result["page_count"], 11)
        self.assertEqual(result["active_page"], 1)
        self.assertEqual(result["navigation"], [
            "Visão geral", "Envios", "Monitor PvE", "Monitor PvP",
            "Banco PvP", "Alertas", "Subsessões", "Configurações", "Tutorial",
            "Inventário",
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
            "connection_limits": {"pc": 2, "emulators": 1},
        })

        self.assertFalse(window.nav_buttons[2].isHidden())
        self.assertFalse(window.nav_buttons[2].isEnabled())
        self.assertFalse(window.nav_buttons[3].isHidden())
        self.assertTrue(window.nav_buttons[3].isEnabled())
        self.assertTrue(window.nav_buttons[5].isHidden())
        self.assertFalse(window.monitor_controls["boss"]["overlay"].isEnabled())
        self.assertFalse(window.monitor_controls["boss"]["dps_overlay"].isEnabled())
        window._select_category("emulator")
        self.assertTrue(window.client_buttons[2].isEnabled())
        self.assertTrue(all(not button.isEnabled() for button in window.client_buttons[3:]))
        pvp_tabs = window.monitor_controls["pvp"]["tabs"]
        self.assertTrue(pvp_tabs.isTabEnabled(2))
        self.assertTrue(all(not pvp_tabs.isTabEnabled(index) for index in range(3, 7)))
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
