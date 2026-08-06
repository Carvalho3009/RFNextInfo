import importlib.util
import logging
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest import mock


@unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 não instalado")
class QtPreviewSmokeTest(unittest.TestCase):
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
            "characters": [{
                "uid": "1", "client_key": "client:a",
                "summary": {"market_events": 2},
            }],
            "collection_type_counts": {},
        }
        window._set_send_controls()
        self.assertTrue(window.send_buttons[("market", -1)].isEnabled())
        self.assertFalse(window.send_buttons[("codex", 0)].isEnabled())
        self.assertFalse(window.send_buttons[("memory_chips", 0)].isEnabled())
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
            "Ativar licença", "Verificar atualização", "Enviar log técnico",
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
            started = time.time_ns() - 6 * 60 * 1_000_000_000
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
            window._rotate_auto_subsessions()
            store = CaptureStore(database, readonly=True)
            entries = store.subsessions("session-1")
            store.close()
            self.assertEqual(len(entries), 2)
            self.assertEqual(sum(item["ended_ns"] is not None for item in entries), 1)
            self.assertEqual(sum(item["ended_ns"] is None for item in entries), 1)
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

    def test_offscreen_window_uses_minimum_supported_size(self):
        from app.ui_qt.main import STYLE
        from app.ui_qt.smoke import run_smoke

        result = run_smoke()

        self.assertEqual(result["platform"], "offscreen")
        self.assertEqual((result["width"], result["height"]), (1180, 664))
        self.assertEqual((result["minimum_width"], result["minimum_height"]), (1180, 664))
        self.assertEqual(result["title"], "RF NEXT QOL — 2.1.8")
        self.assertEqual(result["page_count"], 5)
        self.assertEqual(result["active_page"], 1)
        self.assertEqual(result["navigation"], [
            "Visão geral", "Envios", "Subsessões", "Configurações",
            "Tutorial",
        ])
        self.assertFalse(result["frameless"])
        self.assertEqual(result["overview_groups"], 5)
        self.assertEqual(result["overview_metrics"], 18)
        widget_rule = STYLE.split("QWidget {", 1)[1].split("}", 1)[0]
        self.assertNotIn("background", widget_rule)

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


if __name__ == "__main__":
    unittest.main()
