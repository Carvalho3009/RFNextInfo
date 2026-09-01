from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.remote_subsessions import RemoteSubsessionController


def command(action: str, command_id: str, reference: str = "a" * 32):
    return {
        "command_id": command_id,
        "subsession_ref": reference,
        "action": action,
        "character_uid": 123456,
        "name": "Spot norte",
        "map_name": "Crag Mine",
        "spot_name": "Entrada",
        "mobs": ["Crawler"],
    }


class RemoteSubsessionControllerTest(unittest.TestCase):
    def test_accumulates_confirmed_metrics_and_queues_one_report(self):
        with tempfile.TemporaryDirectory() as folder:
            reports = []
            controller = RemoteSubsessionController(
                Path(folder) / "state.json",
                lambda: [{
                    "client_ref": "client-a", "character_uid": 123456,
                    "name": "Farmador", "level": 66,
                }],
            )
            controller.set_submitter(
                lambda session_id, report: reports.append((session_id, report)) or True
            )
            started = controller.apply_commands(
                [command("start", "1" * 32)],
                session_id="capture-session", capture_active=True,
            )
            self.assertEqual(started[0]["status"], "applied")

            events = (
                ("character.exp_changed", {
                    "gained_exp": 100, "gained_exp_percent": 0.2, "level": 66,
                }),
                ("character.exp_changed", {
                    "gained_exp": 250, "gained_exp_percent": 0.3, "level": 67,
                }),
                ("character.contribution_changed", {"contribution_total": 100}),
                ("character.contribution_changed", {"contribution_total": 130}),
                ("character.drop_received", {"credits_gained": 500}),
                ("combat.entity_died", {
                    "combat_domain": "pve", "killer_is_client": True,
                }),
                ("combat.entity_died", {
                    "combat_domain": "pve", "killer_is_client": False,
                }),
            )
            for event_type, payload in events:
                controller.observe({
                    "type": event_type, "client_ref": "client-a", "payload": payload,
                })

            progress = controller.progress_updates()
            self.assertEqual(len(progress), 1)
            self.assertEqual(progress[0]["subsession_ref"], "a" * 32)
            self.assertEqual(progress[0]["level"], 67)
            self.assertEqual(progress[0]["gained_exp"], 350)
            self.assertAlmostEqual(progress[0]["gained_exp_percent"], 0.5)
            self.assertEqual(progress[0]["gained_contribution"], 30)
            self.assertEqual(progress[0]["gained_credits"], 500)
            self.assertEqual(progress[0]["kill_count"], 1)

            stopped = controller.apply_commands(
                [command("stop", "2" * 32)],
                session_id="capture-session", capture_active=True,
            )
            self.assertEqual(stopped[0]["status"], "applied")
            self.assertEqual(len(reports), 1)
            self.assertEqual(controller.progress_updates(), [])
            session_id, report = reports[0]
            self.assertEqual(session_id, "capture-session")
            self.assertEqual(report["control_ref"], "a" * 32)
            self.assertEqual(report["exp_total"], 350)
            self.assertAlmostEqual(report["exp_total_percent"], 0.5)
            self.assertEqual(report["summary"]["contribution"], 30)
            self.assertEqual(report["summary"]["credits"], 500)
            self.assertEqual(report["kill_count"], 1)
            self.assertEqual(report["summary"]["level"], 67)

            duplicate = controller.apply_commands(
                [command("stop", "2" * 32)],
                session_id="capture-session", capture_active=True,
            )
            self.assertEqual(duplicate[0]["status"], "applied")
            self.assertEqual(len(reports), 1)

    def test_start_requires_active_capture_and_observed_character(self):
        with tempfile.TemporaryDirectory() as folder:
            controller = RemoteSubsessionController(
                Path(folder) / "state.json", lambda: []
            )
            inactive = controller.apply_commands(
                [command("start", "3" * 32)],
                session_id=None, capture_active=False,
            )
            self.assertEqual(inactive[0]["error_code"], "capture_not_active")
            missing = controller.apply_commands(
                [command("start", "4" * 32)],
                session_id="capture-session", capture_active=True,
            )
            self.assertEqual(missing[0]["error_code"], "character_not_observed")

    def test_pending_results_survive_restart_until_acknowledged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            first = RemoteSubsessionController(path, lambda: [])
            first.apply_commands(
                [command("start", "5" * 32)], session_id=None,
                capture_active=False,
            )
            second = RemoteSubsessionController(path, lambda: [])
            pending = second.pending_results()
            self.assertEqual([item["command_id"] for item in pending], ["5" * 32])
            second.acknowledge_results(pending)
            self.assertEqual(second.pending_results(), [])


if __name__ == "__main__":
    unittest.main()
