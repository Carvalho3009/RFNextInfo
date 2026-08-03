import base64
import ast
import json
import logging
import inspect
import struct
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.license import LicenseClient, _activation_error, verify_lease
from app.main import (
    App,
    FARM_CATALOG,
    FARM_CATALOG_EN,
    LEVEL_CURVE,
    _capture_prefix,
    _capture_summary,
    _collection_marks,
    _configured_capture_dir,
    _market_rows,
    _merge_client_routes,
    _safe_error_code,
    _session_elapsed,
)
from app.site_profile import SiteProfileClient
from app.support_log import LOGGER_NAME, configure, recent_lines
from app.updater import UPDATE_SIGNATURE_CONTEXT, download_verified, verify_manifest
import app.main as main_module


def b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode()


class AppLogicTest(unittest.TestCase):
    def test_incremental_summary_matches_full_summary(self):
        events = [
            {
                "type": "update_exp",
                "character_uid": "uid-1",
                "data": {"fields": {"level": 10, "exp": 100, "gain_exp": 25}},
            },
            {
                "type": "drop_item_field",
                "character_uid": "uid-1",
                "data": {
                    "results": [
                        {"item_index": 900, "count": 40},
                        {"item_index": 1, "count": 12},
                    ]
                },
            },
            {
                "type": "update_exp",
                "character_uid": "uid-1",
                "data": {"fields": {"level": 10, "exp": 140, "gain_exp": 40}},
            },
        ]
        full, full_marks = _capture_summary({"events": events}, "uid-1")
        _first, _marks, state = _capture_summary(
            {"events": events[:1]},
            "uid-1",
            _state={"loot_limit": 100},
            _return_state=True,
        )
        incremental, incremental_marks, _state = _capture_summary(
            {"events": events[1:]},
            "uid-1",
            _state=state,
            _return_state=True,
        )
        self.assertEqual(incremental, full)
        self.assertEqual(incremental_marks, full_marks)

    def test_stale_info_result_is_discarded(self):
        app = Mock()
        app._info_refresh_running = True
        app._info_refresh_pending = False
        app._info_refresh_generation = 2

        App._info_refresh_finished(app, 1, {"session_id": "old"}, None)

        app._apply_info_snapshot.assert_not_called()
        app._start_info_refresh.assert_called_once()

    def test_poll_never_scans_event_store(self):
        source = inspect.getsource(App._poll)
        self.assertNotIn("self.store.", source)
        self.assertNotIn("capture.status()", source)
        self.assertNotIn("packet_count()", source)

    def test_configured_capture_dir_uses_saved_absolute_path(self):
        with tempfile.TemporaryDirectory() as folder:
            preferences = Path(folder) / "preferences.json"
            target = Path(folder) / "capturas"
            preferences.write_text(
                json.dumps({"capture_directory": str(target)}),
                encoding="utf-8",
            )

            self.assertEqual(_configured_capture_dir(preferences), target)

    def test_choose_capture_directory_persists_and_rebuilds_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "capturas"
            app = Mock()
            app.capture_dir = Path(folder)
            app.prefs = {}
            app._capture_is_active.return_value = False

            with patch(
                "app.main.filedialog.askdirectory", return_value=str(target)
            ), patch("app.main.PktmonCapture") as capture:
                App._choose_capture_directory(app)

            self.assertEqual(app.capture_dir, target.resolve())
            capture.assert_called_once_with(target.resolve())
            app._save_preferences.assert_called_once()
            app.capture_directory_state.configure.assert_called_once_with(
                text=str(target.resolve())
            )

    def test_scroll_ignores_native_combobox_popup(self):
        canvas = Mock()
        app = Mock(
            _page_canvases=[canvas],
            _active_page_index=0,
        )
        app.winfo_containing.side_effect = KeyError("combobox popdown")
        event = Mock(x_root=1, y_root=1, delta=120, state=0)

        self.assertIsNone(App._scroll_active_page(app, event))
        canvas.yview_scroll.assert_not_called()

    def test_main_has_every_uppercase_global_it_uses(self):
        tree = ast.parse(Path(main_module.__file__).read_text(encoding="utf-8"))
        used = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id.isupper()
            and len(node.id) == 1
        }
        self.assertEqual(
            {name for name in used if not hasattr(main_module, name)},
            set(),
        )

    def test_site_profile_token_is_protected_and_reused_for_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = json.dumps(
                {"profile": "CarvalhoRF", "ok": True}
            ).encode()
            with patch(
                "app.site_profile.protect",
                side_effect=lambda value: bytes(byte ^ 0xA5 for byte in value),
            ), patch(
                "app.site_profile.unprotect",
                side_effect=lambda value: bytes(byte ^ 0xA5 for byte in value),
            ), patch(
                "app.site_profile.urllib.request.urlopen", return_value=response
            ) as urlopen:
                client = SiteProfileClient(Path(folder))
                client.connect("CarvalhoRF", "token-" + "a" * 32)
                capture = Path(folder) / "capture.json"
                capture.write_text(
                    json.dumps(
                        {
                            "metadata": {},
                            "profiles": [],
                            "capture": {},
                        }
                    ),
                    encoding="utf-8",
                )
                client = SiteProfileClient(Path(folder))
                client.upload(capture, "capture-1")
                client.upload_live("market", {"rows": []}, "a" * 64)
                client.upload_live(
                    "memory_chips",
                    {"profiles": []},
                    "b" * 64,
                )
                client.upload_live(
                    "character",
                    {"profiles": []},
                    "c" * 64,
                )
                client.upload_live(
                    "subsession",
                    {"profiles": []},
                    "d" * 64,
                )

            self.assertEqual(urlopen.call_count, 6)
            self.assertTrue(client.connected)
            requests = [call.args[0] for call in urlopen.call_args_list]
            self.assertTrue(
                any(
                    request.full_url.endswith("/api/import/market")
                    for request in requests
                )
            )
            self.assertTrue(
                requests[-1].full_url.endswith("/api/import/farm-session")
            )
            self.assertEqual(
                {
                    request.get_header("Authorization")
                    for request in requests
                },
                {"Bearer token-" + "a" * 32},
            )
            self.assertNotIn(
                ("token-" + "a" * 32).encode(),
                (Path(folder) / "site-profile.dat").read_bytes(),
            )

    def test_site_profile_reports_access_page_instead_of_json(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"<html>login</html>"
        with tempfile.TemporaryDirectory() as folder, patch(
            "app.site_profile.urllib.request.urlopen", return_value=response
        ):
            client = SiteProfileClient(Path(folder))
            with self.assertRaisesRegex(ValueError, "página de acesso"):
                client.connect("CarvalhoRF", "token-" + "a" * 32)

    def test_quick_capture_accepts_app_live_session(self):
        app = Mock()
        app.current_session = "Profile-20260729-120000-001"
        app._live_capture = object()
        app.capture.status.return_value.active = False

        self.assertTrue(App._capture_is_active(app))

    def test_quick_capture_uses_configured_duration(self):
        app = Mock()
        app.quick_mode_labels = {"market": Mock()}
        app._active_quick_mode = None
        app._capture_is_active.return_value = True
        app._quick_capture_duration.return_value = 45

        App.quick_capture(app, "market")

        app.quick_mode_labels["market"].configure.assert_called_once_with(
            text="Capturando · 45 s"
        )
        app.after.assert_called_once()

    def test_send_button_uses_existing_session_instead_of_timed_capture(self):
        app = Mock()
        app.quick_mode_labels = {"market": Mock()}
        app._send_uploading = False
        app._pending_send_mode = None
        app.site_profile.connected = True
        app.current_session = "Profile-20260729-120000-001"
        app._capture_is_active.return_value = False

        App.send_mode_now(app, "market")

        app._send_mode_snapshot.assert_called_once_with("market")
        app.after.assert_not_called()

    def test_character_send_includes_detected_equipment(self):
        app = Mock()
        app.current_session = "Profile-20260730-120000-001"
        app.site_profile.profile = "CarvalhoRF"
        app.site_profile.upload_live.return_value = {"receipt": "ok"}
        app.license.installation_id = "installation"
        app.license.lease = {"valid": True}
        app.active_character_uid = "101"
        app._active_client_index = 0
        app._character_exports.return_value = [
            {
                "uid": "101",
                "name": "Carvalho",
                "client_key": "client:a",
                "include_unassigned": False,
                "only_unassigned": False,
            }
        ]
        app.store.session_envelope.return_value = {
            "events": [
                {
                    "type": "player_profile_info",
                    "character_uid": "101",
                    "data": {
                        "fields": {
                            "active_equipment": {
                                "slots": [
                                    {
                                        "equip_part_type": 1,
                                        "resolved": True,
                                        "item": {
                                            "item_index": 1000078,
                                            "enchant_level": 7,
                                        },
                                    }
                                ]
                            }
                        }
                    },
                }
            ]
        }
        app.quick_mode_labels = {"character": Mock()}
        app.queue_mode_times = {"character": Mock()}
        app._capture_summary_for_language.side_effect = _capture_summary
        app._run.side_effect = lambda job, done: done(job(), None)

        App._send_mode_snapshot(app, "character", 0)

        payload = app.site_profile.upload_live.call_args.args[1]
        equipment = [
            {"item_index": 1000078, "slot": 1, "refinement": 7}
        ]
        self.assertEqual(
            payload["profiles"][0]["loadout"]["equipment"], equipment
        )
        self.assertEqual(payload["loadout"]["equipment"], equipment)

    def test_client_tab_switch_does_not_ask_for_name(self):
        app = Mock()
        app._current_profiles = []
        with patch("app.main.simpledialog.askstring") as ask:
            App._select_character(app, 1)
        ask.assert_not_called()
        self.assertEqual(app._active_client_index, 1)
        self.assertIsNone(app.active_character_uid)

    def test_client_label_keeps_manual_alias_separate_from_captured_name(self):
        app = Mock()
        app.character1.get.return_value = "Farm principal"
        profiles = [
            {
                "uid": "101",
                "name": "FernanTorres",
                "client_key": "client:a",
            }
        ]

        self.assertEqual(
            App._client_display_name(app, 0, profiles),
            "Farm principal · FernanTorres",
        )

    def test_summary_calculates_missing_exp_and_own_diamonds(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "update_exp",
                        "data": {
                            "fields": {
                                "level": 67,
                                "exp": 100,
                                "gain_exp": 50,
                            }
                        },
                    },
                    {
                        "type": "appear_player_prefix",
                        "data": {
                            "fields": {
                                "character_uid": 101,
                                "character_name": "Alice",
                                "diamonds": 3753,
                            }
                        },
                    },
                ]
            },
            "101",
            "Alice",
        )
        self.assertGreater(summary["exp_missing"], 0)
        self.assertEqual(summary["diamonds"], 3753)

    def test_summary_calculates_total_exp_percent_by_event_level(self):
        required = LEVEL_CURVE[68]
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "update_exp",
                        "data": {
                            "fields": {
                                "level": 67,
                                "gain_exp": required / 10,
                            }
                        },
                    }
                ]
            }
        )
        self.assertAlmostEqual(summary["exp_gained_percent"], 10.0)

    def test_reward_packets_drive_farm_totals_without_bonus_duplication(self):
        events = []
        contribution_total = 100_000_000
        for index in range(257):
            contribution_total += 6_050
            events.extend(
                [
                    {
                        "type": "drop_item_field",
                        "data": {
                            "results": [
                                {
                                    "item_index": 900,
                                    "count": (
                                        265_840 if index < 9 else 26_584
                                    ),
                                    "action_code": (
                                        1006 if index < 9 else 1001
                                    ),
                                },
                                {"item_index": 1, "count": 574},
                                {"item_index": 1701, "count": 6_050},
                            ]
                        },
                    },
                    {
                        "type": "update_exp",
                        "data": {
                            "action_code": 1006 if index < 9 else 1001,
                            "gain_exp": 265_840 if index < 9 else 26_584,
                            "level": 67,
                        },
                    },
                    {
                        "type": "realm_contribution_update",
                        "data": {"contribution_total": contribution_total},
                    },
                ]
            )

        summary, _ = _capture_summary({"events": events})

        self.assertEqual(summary["kills"], 257)
        self.assertEqual(summary["exp_gained"], 6_832_088)
        self.assertEqual(summary["credits"], 147_518)
        self.assertEqual(summary["contribution"], 1_554_850)
        self.assertEqual(summary["finalizations"], 9)
        self.assertEqual(
            round(summary["contribution"] / (23 / 60)),
            4_056_130,
        )
        self.assertEqual(summary["loot"], [])

    def test_loot_is_grouped_by_item_rarity(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "drop_item_field",
                        "data": {
                            "results": [
                                {"item_index": 149158, "count": 2},
                                {"item_index": 149159, "count": 3},
                                {"item_index": 149160, "count": 4},
                                {"item_index": 154058, "count": 5},
                            ]
                        },
                    }
                ]
            }
        )

        self.assertEqual(
            summary["loot_by_rarity"],
            {
                "common": 2,
                "uncommon": 3,
                "rare": 4,
                "epic": 5,
            },
        )
        self.assertEqual(
            [item["rarity"] for item in summary["loot"]],
            ["Comum", "Incomum", "Raro", "Épico"],
        )
        self.assertEqual(summary["kills"], 0)

    def test_farm_catalog_links_map_spot_mob_and_level(self):
        self.assertEqual(len(FARM_CATALOG), 25)
        self.assertEqual(
            sum(len(spots) for spots in FARM_CATALOG.values()), 281
        )
        self.assertEqual(
            FARM_CATALOG["Cidade Arruinada da Babilônia"]["Área 4"][
                "Arremessador Carmesim"
            ],
            (98,),
        )
        self.assertEqual(
            FARM_CATALOG_EN["Ruined City of Babylon"]["Area 4"][
                "Crimson Thrower"
            ],
            (98,),
        )

    def test_subsession_map_and_spot_filter_the_next_choices(self):
        app = Mock()
        app.subsession_map.get.return_value = (
            "Cidade Arruinada da Babilônia"
        )
        app.subsession_spot.get.return_value = "Área 4"
        app._selected_farm_catalog.return_value = FARM_CATALOG

        App._subsession_map_changed(app, preferred_spot="Área 4")

        expected_spots = tuple(
            sorted(
                FARM_CATALOG["Cidade Arruinada da Babilônia"],
                key=str.casefold,
            )
        )
        app.subsession_spot.configure.assert_called_once_with(
            values=expected_spots
        )
        app.subsession_spot.set.assert_called_once_with("Área 4")

        app._subsession_spot_changed = App._subsession_spot_changed.__get__(app)
        app._subsession_spot_changed()
        app._set_subsession_mob_choices.assert_called_once_with(
            FARM_CATALOG["Cidade Arruinada da Babilônia"]["Área 4"]
        )

    def test_retained_capture_recovers_character_uid(self):
        app = Mock()
        app.current_session = "profile-20260731-001"
        app.prefs = {"capture_decode_ports": [12010]}
        app.store.session_profiles.side_effect = [[], [{"uid": "123"}]]
        app._ingest_files.return_value = (3, [], 0)
        app._run.side_effect = lambda job, done: done(job(), None)

        App._recover_pending_character_uid(app, (Path("retained.etl"),))

        app._ingest_files.assert_called_once_with(
            (Path("retained.etl"),),
            "profile-20260731-001",
            (12000, 12010, 12020, 12040),
            append_only=True,
        )
        app.capture_state.configure.assert_called_once()
        app._refresh_info.assert_called_once()

    def test_subsession_form_toggle_hides_and_restores_form(self):
        app = Mock()
        app._subsession_form_visible = True

        App._toggle_subsession_form(app)
        self.assertFalse(app._subsession_form_visible)
        app.subsession_form.pack_forget.assert_called_once()
        app.subsession_form_toggle.configure.assert_called_once_with(text="▶")

        App._toggle_subsession_form(app)
        self.assertTrue(app._subsession_form_visible)
        app.subsession_form.pack.assert_called_once_with(
            side="left",
            before=app.subsession_history,
            fill="y",
            padx=(0, 8),
        )

    def test_english_language_updates_map_and_spot_choices(self):
        app = Mock()
        app.item_name_language.get.return_value = "pt"
        app.subsession_map.get.return_value = (
            "Cidade Arruinada da Babilônia"
        )
        app.subsession_spot.get.return_value = "Área 4"

        App._item_language_changed(app, "English")

        app.item_name_language.set.assert_called_once_with("en")
        app._refresh_farm_choices.assert_called_once_with(
            "Ruined City of Babylon", "Area 4"
        )

    def test_market_window_builds_site_rows(self):
        rows = _market_rows(
            {
                "events": [
                    {
                        "data": {
                            "message": (
                                "FL2C_respond_purchase_list_on_exchange_Message"
                            ),
                            "ret": 0,
                            "is_end": True,
                            "exchange_item_simple_infos": [
                                {
                                    "item_index": 1000150,
                                    "enchant_level": 7,
                                    "lowest_price": 100,
                                    "highest_price": 200,
                                    "number_of_registered_items": 3,
                                }
                            ],
                        }
                    }
                ]
            },
            {"1000150": "English market item"},
        )
        self.assertEqual(rows[0]["ItemIndex"], 1000150)
        self.assertEqual(rows[0]["Name"], "English market item")
        self.assertEqual(rows[0]["PricePerUnit"], 100)

    def test_summary_resolves_biosuit_name_and_class(self):
        for item_index, name, class_name in (
            (2075041, "Revenant Caelum", "Arbiter"),
            (2085031, "Destilador Terminator", "Demolisher"),
        ):
            summary, _ = _capture_summary(
                {
                    "events": [
                        {
                            "type": "world_info_prefix",
                            "data": {
                                "fields": {
                                    "character_name": "Teste",
                                    "level": 67,
                                    "biosuit_item_index": item_index,
                                }
                            },
                        }
                    ]
                }
            )
            self.assertEqual(summary["biosuit_name"], name)
            self.assertEqual(summary["character_class"], class_name)
            self.assertEqual(summary["biosuit_grade"], 5)

    def test_summary_exports_correlated_equipment_and_collection_types(self):
        envelope = {
            "events": [
                {
                    "type": "player_profile_info",
                    "data": {
                        "fields": {
                            "active_equipment": {
                                "slots": [
                                    {
                                        "equip_part_type": 1,
                                        "resolved": True,
                                        "item": {
                                            "item_index": 1000078,
                                            "enchant_level": 7,
                                        },
                                    },
                                    {
                                        "equip_part_type": 2,
                                        "resolved": False,
                                    },
                                ]
                            }
                        }
                    },
                },
                {
                    "type": "collection_snapshot_chunk",
                    "data": {
                        "collection_type": 1,
                        "records": [
                            {
                                "collection_index": 1001,
                                "collection_type": 1,
                                "completed_slots": [0],
                            }
                        ],
                    },
                },
                {
                    "type": "collection_snapshot_chunk",
                    "data": {
                        "collection_type": 2,
                        "records": [
                            {
                                "collection_index": 2001,
                                "collection_type": 2,
                                "completed_slots": [1],
                            }
                        ],
                    },
                },
            ]
        }

        summary, marks = _capture_summary(envelope)
        codex, types = _collection_marks(envelope, {1})
        memory, _ = _collection_marks(envelope, {2})

        self.assertEqual(
            summary["loadout"]["equipment"],
            [{"item_index": 1000078, "slot": 1, "refinement": 7}],
        )
        self.assertEqual(marks, {"1001": [1], "2001": [2]})
        self.assertEqual(codex, {"1001": [1]})
        self.assertEqual(memory, {"2001": [2]})
        self.assertEqual(types, [1, 2])

    def test_summary_changes_class_only_after_confirmed_biosuit_response(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "world_info_prefix",
                        "data": {"fields": {"biosuit_item_index": 2075041}},
                    },
                    {
                        "type": "change_biosuit_request",
                        "data": {"fields": {"biosuit_item_index": 2085031}},
                    },
                    {
                        "type": "change_biosuit_response",
                        "data": {
                            "fields": {
                                "result": 1,
                                "biosuit_item_index": 2085031,
                            }
                        },
                    },
                    {
                        "type": "change_biosuit_response",
                        "data": {
                            "fields": {
                                "result": 0,
                                "biosuit_item_index": 2085031,
                            }
                        },
                    },
                ]
            }
        )

        self.assertEqual(summary["biosuit_item_index"], 2085031)
        self.assertEqual(summary["biosuit_name"], "Destilador Terminator")
        self.assertEqual(summary["character_class"], "Demolisher")

    def test_summary_uses_only_confirmed_rover_state(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "change_rover_request",
                        "data": {"fields": {"rover_item_index": 4300017}},
                    },
                    {
                        "type": "change_rover_response",
                        "data": {
                            "fields": {
                                "result": 1,
                                "rover_item_index": 4400011,
                            }
                        },
                    },
                    {
                        "type": "player_equip_update",
                        "data": {
                            "fields": {
                                "character_uid": 7,
                                "rover_item_index": 4000002,
                            }
                        },
                    },
                ]
            }
        )

        self.assertEqual(summary["rover_item_index"], 4000002)
        self.assertEqual(summary["rover_name"], "Arcturus")
        self.assertEqual(summary["rover_grade"], 1)

    def test_summary_never_uses_nearby_characters_rover(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "player_equip_update",
                        "character_uid": "202",
                        "data": {
                            "fields": {
                                "character_uid": "202",
                                "rover_item_index": 4400011,
                            }
                        },
                    },
                    {
                        "type": "player_equip_update",
                        "character_uid": "101",
                        "data": {
                            "fields": {
                                "character_uid": "101",
                                "rover_item_index": 4000002,
                            }
                        },
                    },
                ]
            },
            character_uid="101",
        )

        self.assertEqual(summary["rover_item_index"], 4000002)
        self.assertEqual(summary["rover_name"], "Arcturus")

    def test_summary_uses_rover_confirmed_in_own_entry(self):
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "appear_player_prefix",
                        "data": {
                            "fields": {
                                "character_uid": 101,
                                "character_name": "Carvalho",
                                "rover_item_index": 4400008,
                            }
                        },
                    }
                ]
            },
            "101",
            "Carvalho",
        )

        self.assertEqual(summary["rover_item_index"], 4400008)
        self.assertEqual(summary["rover_name"], "Leo")
        self.assertEqual(summary["rover_grade"], 5)

    def test_stopped_session_does_not_keep_counting(self):
        now = datetime(2026, 7, 29, 12, 30, 0)
        session = "Profile-20260729-120000-001"

        self.assertEqual(_session_elapsed(session, False, now), 0)
        self.assertEqual(_session_elapsed(session, True, now), 1800)

    def test_start_button_processes_recovered_capture_first(self):
        app = Mock()
        app._refresh_license.return_value = (True, "Licença válida")
        app._ingesting = False
        app.discard_previous.get.return_value = False
        app.prefs = {"capture_pending": True}
        app.capture.status.return_value.active = False
        app.capture.segment_files.return_value = (Path("segment.etl"),)

        App.start_capture(app)

        app.stop_capture.assert_called_once()
        self.assertTrue(app._start_after_ingest)

    def test_discard_previous_removes_undecoded_file_and_pending_state(self):
        with tempfile.TemporaryDirectory() as folder:
            raw = Path(folder) / "pending.etl"
            raw.write_bytes(b"undecoded")
            app = Mock()
            app.capture_dir = Path(folder)
            app.current_session = "Profile-20260729-120000-001"
            app.capture.segment_files.return_value = (raw,)
            app.capture.status.return_value.active = False
            app.store.session_sources.return_value = []
            app._live_files = []
            app.prefs = {
                "capture_pending": True,
                "last_session": app.current_session,
            }
            app._paused = False
            app._paused_at = None
            with patch(
                "app.main.messagebox.askyesno", return_value=True
            ), patch("app.main._recycle", return_value=True) as recycle:
                self.assertTrue(App._discard_previous_capture(app))

            recycle.assert_called_once_with([raw])
            app.store.clear_session.assert_called_once_with(
                "Profile-20260729-120000-001"
            )
            self.assertIsNone(app.current_session)
            self.assertFalse(app.prefs["capture_pending"])
            self.assertNotIn("last_session", app.prefs)

    def test_discard_stale_session_without_files_does_not_query_pktmon(self):
        app = Mock()
        app.capture_dir = Path("missing-capture-dir")
        app.current_session = "Profile-20260729-120000-001"
        app._live_files = []
        app.capture.segment_files.return_value = ()
        app.store.session_sources.return_value = []
        app.prefs = {
            "capture_pending": False,
            "last_session": app.current_session,
        }
        app._paused = False
        app._paused_at = None
        old_capture = app.capture

        with patch("app.main.messagebox.askyesno") as confirmation:
            self.assertTrue(App._discard_previous_capture(app))

        confirmation.assert_not_called()
        old_capture.status.assert_not_called()
        app.store.clear_session.assert_called_once_with(
            "Profile-20260729-120000-001"
        )

    def test_specific_subsession_duration_ends_without_creating_another(self):
        app = Mock()
        app.current_session = "session-1"
        app.active_character_uid = "uid-1"
        app.auto_subsession.get.return_value = False
        app.store.subsessions.return_value = [
            {
                "id": "sub-1",
                "character_uid": "uid-1",
                "started_ns": 1_000_000_000,
                "duration_minutes": 1,
                "ended_ns": None,
            }
        ]
        with patch(
            "app.main.time.time_ns", return_value=61_000_000_001
        ):
            App._rotate_auto_subsession(app)
        app.store.end_subsession.assert_called_once_with(
            "sub-1", 61_000_000_001
        )
        app.store.start_subsession.assert_not_called()

    def test_expired_subsession_starts_next_when_auto_enabled(self):
        app = Mock()
        app.current_session = "session-1"
        app.auto_subsession.get.return_value = True
        app.auto_subsession_minutes.get.return_value = 10
        app.store.subsessions.return_value = [
            {
                "id": "sub-1",
                "character_uid": "uid-1",
                "name": "Farm",
                "location": "Mapa > Spot",
                "map_name": "Mapa",
                "spot_name": "Spot",
                "mobs": ["Mob"],
                "mob_levels": {"Mob": 60},
                "started_ns": 1_000_000_000,
                "duration_minutes": 5,
                "ended_ns": None,
            },
            {
                "id": "sub-2",
                "character_uid": "uid-2",
                "name": "Farm B",
                "location": "Mapa > Spot",
                "map_name": "Mapa",
                "spot_name": "Spot",
                "mobs": ["Mob"],
                "mob_levels": {"Mob": 60},
                "started_ns": 1_000_000_000,
                "duration_minutes": 5,
                "ended_ns": None,
            },
        ]

        with patch(
            "app.main.time.time_ns", return_value=301_000_000_001
        ):
            App._rotate_auto_subsession(app)

        self.assertEqual(
            [call.args for call in app.store.end_subsession.call_args_list],
            [
                ("sub-1", 301_000_000_001),
                ("sub-2", 301_000_000_001),
            ],
        )
        self.assertEqual(app.store.start_subsession.call_count, 2)
        self.assertTrue(
            all(
                call.kwargs["duration_minutes"] == 10
                for call in app.store.start_subsession.call_args_list
            )
        )

    def test_auto_subsession_does_not_resume_after_manual_end(self):
        app = Mock()
        app.current_session = "session-1"
        app.auto_subsession.get.return_value = True
        app.auto_subsession_minutes.get.return_value = 10
        app.store.subsessions.return_value = [
            {
                "id": "sub-1",
                "character_uid": "uid-1",
                "name": "Farm",
                "location": "Mapa > Spot",
                "map_name": "Mapa",
                "spot_name": "Spot",
                "mobs": ["Mob"],
                "mob_levels": {"Mob": 60},
                "started_ns": 1,
                "duration_minutes": 5,
                "ended_ns": 2,
            }
        ]

        with patch("app.main.time.time_ns", return_value=10**18):
            App._rotate_auto_subsession(app)

        app.store.start_subsession.assert_not_called()

    def test_zero_subsession_duration_waits_for_manual_end(self):
        app = Mock()
        app.current_session = "session-1"
        app.active_character_uid = "uid-1"
        app.auto_subsession.get.return_value = True
        app.auto_subsession_minutes.get.return_value = 10
        app.store.subsessions.return_value = [
            {
                "id": "sub-1",
                "character_uid": "uid-1",
                "started_ns": 1,
                "duration_minutes": 0,
                "ended_ns": None,
            }
        ]

        with patch("app.main.time.time_ns", return_value=10**18):
            App._rotate_auto_subsession(app)

        app.store.end_subsession.assert_not_called()
        app.store.start_subsession.assert_not_called()

    def test_saved_license_check_updates_startup_ui(self):
        app = Mock()
        app._ingesting = False
        app._apply_license_status.side_effect = (
            lambda allowed, message: App._apply_license_status(
                app, allowed, message
            )
        )

        App._license_checked(app, (True, "Licença válida."), None)

        self.assertTrue(app.capture_allowed)
        app.top_license.configure.assert_called_with(
            text="• Licença válida.",
            style="TopbarOk.TLabel",
        )
        app.start_button.configure.assert_called_with(state="normal")

    def test_capture_uses_all_detected_ports_without_character_process_choice(self):
        app = Mock()
        app._refresh_license.return_value = (True, "Licença válida")
        app._decode_interval_seconds.return_value = 30
        app._ingesting = False
        app.capture.status.return_value.active = False
        app.profile.get.return_value = "Profile"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app._selected_game_path = r"C:\Games\ProjectRF.exe"
        app.prefs = {
            "session_counter": 2,
            "capture_pid_uids": {"10": "client:1"},
            "capture_port_uids": {"50100": "client:1"},
            "capture_character_names": {"client:1": "Alice"},
        }
        with patch(
            "app.main.ports_for_executable",
            return_value=((50100, 50200), (12010, 12020), 2),
        ), patch(
            "app.main.clients_for_executable",
            return_value=[
                {
                    "pid": 10,
                    "local_ports": (50100,),
                    "remote_ports": (12010,),
                },
                {
                    "pid": 20,
                    "local_ports": (50200,),
                    "remote_ports": (12020,),
                },
            ],
        ), patch("app.main.RealtimeCapture"):
            App.start_capture(app)
        started_ports = app.capture.start_for_ports.call_args.args[1]
        self.assertEqual(started_ports, (50100, 50200, 12010, 12020))
        self.assertEqual(
            app._live_ports,
            (12000, 12010, 12020, 12040, 50100, 50200),
        )
        self.assertEqual(
            app.prefs["capture_decode_ports"],
            [12000, 12010, 12020, 12040],
        )
        self.assertNotIn("capture_pid_uids", app.prefs)
        self.assertNotIn("capture_port_uids", app.prefs)
        self.assertNotIn("capture_character_names", app.prefs)
        self.assertEqual(app._client_ports, [(50100,), (50200,)])

    def test_live_reconnection_updates_each_client_port_group(self):
        app = Mock()
        app._selected_game_path = r"C:\Games\ProjectRF.exe"
        app._last_game_signature = None
        app._client_ports = [(50100,), (50200,)]
        app._client_pids = [10, 20]
        app._live_ports = (50100, 50200, 12020)
        app.prefs = {
            "capture_ports": [50100, 50200, 12020],
            "capture_decode_ports": [12020],
        }
        app.capture.add_ports.return_value = 1
        App._apply_active_game_connections(
            app,
            (
                (50100, 50101, 50200),
                (12020,),
                2,
                [
                {
                    "pid": 10,
                    "local_ports": (50100, 50101),
                    "remote_ports": (12020,),
                },
                {
                    "pid": 20,
                    "local_ports": (50200,),
                    "remote_ports": (12020,),
                },
                ],
            ),
        )
        self.assertEqual(app._client_ports, [(50100, 50101), (50200,)])
        self.assertEqual(
            app.prefs["capture_client_ports"],
            [[50100, 50101], [50200]],
        )
        app._live_capture.add_ports.assert_called_once_with(
            (50100, 50101, 50200, 12020)
        )

    def test_client_route_history_survives_port_rotation(self):
        pids, ports = _merge_client_routes(
            [10, 20],
            [(60470, 63175), (63188,)],
            [
                {
                    "pid": 10,
                    "local_ports": (10874, 63175),
                    "remote_ports": (443, 12020),
                },
                {
                    "pid": 20,
                    "local_ports": (12506, 63188),
                    "remote_ports": (12010, 12020),
                },
            ],
        )
        self.assertEqual(pids, [10, 20])
        self.assertEqual(ports[0], (10874, 60470, 63175))
        self.assertEqual(ports[1], (12506, 63188))

    def test_restarted_client_keeps_its_route_history(self):
        pids, ports = _merge_client_routes(
            [10, 20],
            [(60470,), (63188,)],
            [
                {
                    "pid": 30,
                    "local_ports": (63175,),
                    "remote_ports": (12020,),
                },
                {
                    "pid": 20,
                    "local_ports": (63188,),
                    "remote_ports": (12020,),
                },
            ],
        )
        self.assertEqual(pids, [30, 20])
        self.assertEqual(ports, [(60470, 63175), (63188,)])

    def test_empty_capture_is_safe_and_not_exportable(self):
        self.assertEqual(
            _safe_error_code(ValueError("PCAPNG sem pacotes utilizáveis")),
            "empty_capture",
        )
        app = Mock()
        app.current_session = "session-1"
        app.store.session_stats.return_value = {
            "recognized": 0,
            "unknown": 0,
        }
        self.assertFalse(App._session_has_data(app))
        app.store.session_stats.return_value["unknown"] = 1
        self.assertTrue(App._session_has_data(app))

    def test_stop_capture_is_idempotent_while_ingesting(self):
        app = Mock()
        app._ingesting = True
        App.stop_capture(app)
        app.capture.stop.assert_not_called()

    def test_empty_capture_is_not_a_blocking_failure(self):
        class EmptyStore:
            def __init__(self, _path):
                pass

            def ingest(self, *_args, **_kwargs):
                raise ValueError("PCAPNG sem pacotes utilizáveis")

            def remove_sources(self, _sources):
                pass

            def close(self):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "empty.etl"
            raw.write_bytes(b"metadata")
            app = Mock()
            app._ingesting = False
            app.current_session = "session-1"
            app.capture.attached = True
            app.capture.stop.return_value.files = (raw,)
            app.prefs = {
                "capture_pending": True,
                "capture_decode_ports": [12010, 12020],
            }
            app.capture_allowed = True
            app._live_files = []
            app.auto_export.get.return_value = False
            app._ingest_lock = threading.Lock()
            app._ingest_files.side_effect = (
                lambda files, session_id, ports, **kwargs: App._ingest_files(
                    app, files, session_id, ports, **kwargs
                )
            )
            app._run.side_effect = lambda job, done: done(job(), None)
            with patch("app.main.CaptureStore", EmptyStore):
                App.stop_capture(app)
            self.assertFalse(app.prefs["capture_pending"])
            self.assertFalse(app._ingesting)
            self.assertIn(
                "sem pacotes utilizáveis",
                app.capture_state.configure.call_args.kwargs["text"],
            )

    def test_successful_segment_wins_over_empty_residual(self):
        with tempfile.TemporaryDirectory() as tmp:
            main = Path(tmp) / "capture-1.etl"
            residual = Path(tmp) / "capture-2.etl"
            main.write_bytes(b"packets")
            residual.write_bytes(b"metadata")
            app = Mock()
            app._ingesting = False
            app.current_session = "session-1"
            app.capture.attached = True
            app.capture.stop.return_value.files = (main, residual)
            app.prefs = {
                "capture_pending": True,
                "capture_decode_ports": [12010, 12020],
            }
            app.capture_allowed = True
            app._live_files = []
            app.auto_export.get.return_value = False
            app._ingest_files.return_value = (3396, [], 1)
            app._run.side_effect = lambda job, done: done(job(), None)

            App.stop_capture(app)

            self.assertFalse(app.prefs["capture_pending"])
            text = app.capture_state.configure.call_args.kwargs["text"]
            self.assertIn("3396 eventos novos", text)
            self.assertIn("1 segmento(s) vazio(s)", text)

    def test_failed_pending_reanalysis_does_not_restart_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "capture.etl"
            raw.write_bytes(b"broken")
            app = Mock()
            app._ingesting = False
            app.current_session = "session-1"
            app.capture.attached = True
            app.capture.stop.return_value.files = (raw,)
            app.prefs = {
                "capture_pending": True,
                "capture_decode_ports": [12010, 12020],
            }
            app.capture_allowed = True
            app._live_files = []
            app._start_after_ingest = True
            app.auto_export.get.return_value = False
            app._ingest_files.return_value = (0, ["capture.etl: erro"], 0)
            app._run.side_effect = lambda job, done: done(job(), None)

            App.stop_capture(app)

            self.assertTrue(app.prefs["capture_pending"])
            app.after.assert_not_called()

    def test_live_preview_without_known_route_preserves_raw_pcap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "preview.pcap"
            raw.write_bytes(
                struct.pack(
                    "<IHHIIII",
                    0xA1B23C4D,
                    2,
                    4,
                    0,
                    0,
                    0xFFFF,
                    1,
                )
            )
            capture = Mock()
            capture.target = raw
            capture.packets = 0
            capture.received_packets = 0
            capture.filtered_packets = 0
            capture.missed_write = 0
            capture.missed_read = 0
            app = Mock()
            app._live_capture = capture
            app._client_ports = [(50100,)]
            app._live_files = []
            app._live_index = 1
            app.current_session = "session-1"

            with patch("app.main.CAPTURE_DIR", root):
                files = App._close_live_preview(app)

            self.assertEqual(files, (raw,))
            self.assertTrue(raw.exists())

    def test_live_decode_rotates_preview_before_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp) / "preview.pcap"
            next_preview = Path(tmp) / "next.pcap"
            preview.write_bytes(b"P" * 100)
            app = Mock()
            app._ingesting = False
            app._live_ingesting = False
            app._stop_after_live_ingest = False
            app._exit_after_live_ingest = False
            app._adaptive_live_interval = 180
            app.current_session = "session-1"
            app._next_live_decode = 0
            app._decode_interval_seconds.return_value = 30
            app.prefs = {
                "capture_decode_ports": [12010, 12020],
                "capture_ports": [50100],
            }
            app._live_files = []
            app._live_capture = Mock()
            app._next_live_target.return_value = next_preview
            app._live_capture.rotate.return_value = preview
            app._ingest_files.return_value = (4, [], 0)
            app._run.side_effect = (
                lambda job, done: done(job(), None)
            )

            App._maybe_decode_live(app)

            app._live_capture.rotate.assert_called_once_with(next_preview)
            self.assertEqual(app._live_files, [preview])
            app._ingest_files.assert_called_once_with(
                (preview,),
                "session-1",
                (12000, 12010, 12020, 12040),
                append_only=True,
            )
            app.capture.stop.assert_not_called()
            self.assertFalse(app._live_ingesting)
            app._refresh_info.assert_called_once()
            app._upload_pending_quick_captures.assert_called_once()
            self.assertLessEqual(
                app._next_live_decode - time.monotonic(),
                31,
            )

    def test_capture_summary_can_use_official_english_item_names(self):
        self.assertEqual(main_module.ITEM_NAMES_EN["1"], "Credit")
        summary, _ = _capture_summary(
            {
                "events": [
                    {
                        "type": "drop_item_field",
                        "data": {
                            "results": [
                                {"item_index": 123, "count": 2}
                            ]
                        },
                    }
                ]
            },
            item_names={"123": "English item"},
        )

        self.assertEqual(summary["loot"][0]["item"], "English item")

    @patch("app.main.messagebox.showwarning")
    def test_export_waits_for_complete_capture(self, warning):
        app = Mock()
        app.capture.status.return_value.active = True

        App.export(app)

        warning.assert_called_once()
        app.store.latest_session.assert_not_called()

    def test_two_names_without_uid_export_as_reviewable_combined_file(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {}
        app.store.session_profiles.return_value = []
        app.store.session_stats.return_value = {"unassigned": 10}
        exports = App._character_exports(app)
        self.assertEqual(len(exports), 1)
        self.assertEqual(exports[0]["uid"], None)
        self.assertEqual(exports[0]["identification_status"], "unresolved")
        self.assertEqual(exports[0]["name"], "Nao-identificado")
        self.assertEqual(exports[0]["requested_characters"], [])
        self.assertTrue(exports[0]["warning"])

    def test_automatic_client_routes_export_separately(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {}
        app.store.session_profiles.return_value = [
            {"uid": "client:a", "name": "FernanTorres"},
            {"uid": "client:b", "name": "Carvalho"},
        ]
        app.store.session_stats.return_value = {"unassigned": 0}
        exports = App._character_exports(app, prompt_exp=True)
        self.assertEqual(
            [item["name"] for item in exports],
            ["FernanTorres", "Carvalho"],
        )
        self.assertTrue(
            all(item["identification_status"] == "client_routed" for item in exports)
        )
        app.store.unidentified_exp_flows.assert_not_called()

    def test_manual_aliases_do_not_identify_exported_characters(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = "Bob"
        app.prefs = {}
        app.store.session_profiles.return_value = []
        app.store.session_stats.return_value = {"unassigned": 0}
        with patch("app.main.simpledialog.askfloat") as ask:
            exports = App._character_exports(app, prompt_exp=True)
        ask.assert_not_called()
        app.store.assign_unidentified_by_exp.assert_not_called()
        self.assertEqual(exports[0]["name"], "Nao-identificado")

    def test_export_prompts_exp_for_unassigned_events_with_one_uid(self):
        app = Mock()
        app.current_session = "session-1"
        app.character1.get.return_value = "Alice"
        app.character2.get.return_value = ""
        app.prefs = {}
        app.store.session_profiles.return_value = [
            {"uid": "101", "name": "Alice"}
        ]
        app.store.unidentified_exp_flows.return_value = [
            {"flow": "missing", "exp_percent": 61.0}
        ]
        app.store.session_stats.return_value = {"unassigned": 0}
        with patch("app.main.simpledialog.askfloat", return_value=60.5):
            exports = App._character_exports(app, prompt_exp=True)
        app.store.assign_unidentified_to_uid_by_exp.assert_called_once_with(
            "session-1", "101", 60.5
        )
        self.assertIsNone(exports[0]["warning"])

    def test_update_launch_closes_current_app(self):
        app = Mock()
        app.capture.attached = False
        app.tray = None
        with patch("app.main.messagebox.askyesno", return_value=True), patch(
            "app.main.os.startfile"
        ) as launch:
            App._update_downloaded(app, Path("setup.exe"), None)
        launch.assert_called_once_with(Path("setup.exe"))
        app.store.close.assert_called_once()
        app.destroy.assert_called_once()

    def test_verified_download_reports_progress(self):
        private = Ed25519PrivateKey.generate()
        public = b64(private.public_key().public_bytes_raw())
        installer = b"instalador-verificado" * 100
        name = "RFNextInfo-Test-Progress.exe"
        manifest = {
            "version": "test",
            "file": name,
            "sha256": __import__("hashlib").sha256(installer).hexdigest(),
        }
        canonical = json.dumps(
            manifest, separators=(",", ":"), sort_keys=True
        ).encode()
        manifest["signature"] = b64(
            private.sign(UPDATE_SIGNATURE_CONTEXT + canonical)
        )

        class Response(BytesIO):
            def __init__(self, body: bytes):
                super().__init__(body)
                self.headers = {"Content-Length": str(len(body))}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                self.close()

        release = {
            "assets": [
                {
                    "name": "update-manifest.json",
                    "browser_download_url": "https://example/manifest",
                },
                {
                    "name": name,
                    "browser_download_url": "https://example/installer",
                },
            ]
        }
        progress = []
        target = Path(tempfile.gettempdir()) / name
        target.unlink(missing_ok=True)
        try:
            with patch.object(
                urllib.request,
                "urlopen",
                side_effect=[
                    Response(json.dumps(manifest).encode()),
                    Response(installer),
                ],
            ):
                self.assertEqual(
                    download_verified(
                        release,
                        public,
                        lambda phase, done, total: progress.append(
                            (phase, done, total)
                        ),
                    ),
                    target,
                )
            self.assertEqual(target.read_bytes(), installer)
            self.assertEqual(progress[0][0], "manifest")
            self.assertEqual(progress[-1], ("verify", len(installer), len(installer)))
        finally:
            target.unlink(missing_ok=True)

    def test_activation_diagnostics_and_local_format_check(self):
        error = urllib.error.HTTPError(
            "https://license", 403, "Forbidden", {"CF-Ray": "ray-test"}, BytesIO(
                b'{"detail":"licenca invalida"}'
            )
        )
        self.assertEqual(
            _activation_error(error), "licenca invalida (HTTP 403, CF-Ray ray-test)"
        )
        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(Path(directory), version="test")
            client._json = Mock()
            with self.assertRaisesRegex(ValueError, "Formato inválido"):
                client.activate("sem-hifens", "test")
            client._json.assert_not_called()

    def test_async_error_reaches_callback(self):
        completed = threading.Event()
        observed = []

        class Scheduler:
            def after(self, _delay, callback):
                callback()

        def fail():
            raise RuntimeError("falhou")

        App._run(Scheduler(), fail, lambda result, error: (
            observed.append((result, str(error))), completed.set()
        ))
        self.assertTrue(completed.wait(1))
        self.assertEqual(observed, [(None, "falhou")])
        self.assertEqual(
            _capture_prefix("Profile-20260728-010203-007"),
            "rfnext-20260728-010203-007",
        )

    def test_support_log_is_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rfnext-info.log"
            logger = configure(path, "test")
            try:
                logger.error(
                    "KRV-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAAAA "
                    "carvalho@tuta.com 192.168.0.10 "
                    r"C:\Users\Carlos\Documents "
                    "123e4567-e89b-12d3-a456-426614174000"
                )
                try:
                    raise RuntimeError("PersonagemSecreto")
                except RuntimeError:
                    logger.exception("operation_failed")
                lines = "\n".join(recent_lines(path))
                self.assertRegex(
                    lines.splitlines()[0],
                    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{4} ",
                )
                self.assertNotIn("KRV-AAAAA", lines)
                self.assertNotIn("carvalho@tuta.com", lines)
                self.assertNotIn("192.168.0.10", lines)
                self.assertNotIn(r"C:\Users\Carlos", lines)
                self.assertNotIn("123e4567-e89b-12d3-a456-426614174000", lines)
                self.assertNotIn("PersonagemSecreto", lines)
                self.assertIn("<LICENCA>", lines)
            finally:
                for handler in list(logging.getLogger(LOGGER_NAME).handlers):
                    logging.getLogger(LOGGER_NAME).removeHandler(handler)
                    handler.close()

    def test_signed_lease_and_site_profile(self):
        private = Ed25519PrivateKey.generate()
        claims = {
            "v": 1,
            "iss": "rflicenca.karvalho.dev.br",
            "license_id": "license-1",
            "installation_id": "install-1",
            "issued_at": "2026-07-27T00:00:00Z",
            "license_starts_at": "2026-07-01T00:00:00Z",
            "license_expires_at": "2999-12-31T00:00:00Z",
            "next_check_at": "2000-01-01T00:00:00Z",
            "valid_until": "2999-01-01T00:00:00Z",
        }
        payload = json.dumps(claims, separators=(",", ":"), sort_keys=True).encode()
        lease = f"{b64(payload)}.{b64(private.sign(payload))}"
        public = b64(private.public_key().public_bytes_raw())
        self.assertEqual(verify_lease(lease, public)["installation_id"], "install-1")

        summary, marks = _capture_summary({"events": [{
            "type": "collection_snapshot_chunk",
            "data": {
                "fields": {"character_name": "Carvalho", "level": 66, "exp": 12.5},
                "records": [{"collection_index": 1001, "completed_slots": [0, 2]}],
            },
        }]})
        self.assertEqual(summary["character"], "Carvalho")
        self.assertEqual(marks, {"1001": [1, 3]})

        manifest = {"version": "1.0.1", "file": "setup.exe", "sha256": "a" * 64}
        canonical = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode()
        manifest["signature"] = b64(private.sign(UPDATE_SIGNATURE_CONTEXT + canonical))
        self.assertEqual(verify_manifest(manifest, public)["version"], "1.0.1")

        with tempfile.TemporaryDirectory() as directory:
            client = LicenseClient(Path(directory))
            client.state.update(lease=lease, public_key=public, installation_id="install-1")
            client._save()
            remembered = LicenseClient(Path(directory))
            self.assertEqual(remembered.lease, lease)
            self.assertEqual(remembered.installation_id, "install-1")
            self.assertEqual(
                remembered.state["license_expires_at"],
                "2999-12-31T00:00:00Z",
            )
            self.assertNotIn(
                lease.encode(), (Path(directory) / "license.dat").read_bytes()
            )
            legacy = Path(directory) / "legacy-license.json"
            legacy.write_text(
                json.dumps(client.state), encoding="utf-8"
            )
            machine = LicenseClient(
                Path(directory) / "machine",
                legacy_paths=(legacy,),
            )
            self.assertEqual(machine.lease, lease)
            self.assertFalse(legacy.exists())
            protected = Path(directory) / "machine" / "license.dat"
            self.assertTrue(protected.is_file())
            local = LicenseClient(
                Path(directory) / "local",
                legacy_paths=(protected,),
            )
            self.assertEqual(local.lease, lease)
            self.assertEqual(local.load_status, "migrated")
            self.assertEqual(
                LicenseClient(Path(directory) / "local").lease,
                lease,
            )
            protected.write_bytes(
                protected.read_bytes()[:-1] + b"\0"
            )
            recovered = LicenseClient(Path(directory) / "machine")
            self.assertEqual(recovered.lease, lease)
            self.assertEqual(recovered.load_status, "backup")
            client._json = Mock(side_effect=urllib.error.HTTPError(
                "https://license", 401, "revogada", {}, None
            ))
            allowed, _ = client.refresh_if_due("1.0.0")
            self.assertFalse(allowed)
            client.state["installation_id"] = "outra-instalacao"
            with self.assertRaises(ValueError):
                client.claims()

            diagnostic = Path(directory) / "diagnostic.json"
            diagnostic.write_text(
                json.dumps(
                    {
                        "privacy": "sem payload",
                        "events": [{"opcode": "0x7777", "decoded_size": 12}],
                    }
                ),
                encoding="utf-8",
            )
            remembered._json = Mock(return_value={"receipt": "test-1"})
            self.assertEqual(
                remembered.upload_diagnostic(diagnostic, "1.0.0")["receipt"],
                "test-1",
            )


if __name__ == "__main__":
    unittest.main()
