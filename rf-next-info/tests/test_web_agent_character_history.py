from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.web_agent_character_history import AgentCharacterHistory


KEY = b"0123456789abcdef0123456789abcdef"


class AgentCharacterHistoryTest(unittest.TestCase):
    def _history(self, folder: str) -> AgentCharacterHistory:
        return AgentCharacterHistory(
            Path(folder) / "characters.dat", "install-test", KEY
        )

    @staticmethod
    def _direct(
        history: AgentCharacterHistory,
        connection: str,
        character_uid: int,
        *,
        level: int = 66,
        exp: int = 1_000,
        rover: int = 4_300_017,
        items: tuple[int, ...] = (11, 22, 33),
    ) -> None:
        history.observe(connection, "world_info_prefix", {"fields": {
            "character_uid": character_uid,
            "character_name": f"Personagem {character_uid}",
            "level": level,
            "biosuit_item_index": 2_075_041,
        }}, 1_000_000_000)
        history.observe(connection, "update_exp", {
            "level": level, "exp": exp,
        }, 1_100_000_000)
        history.observe(connection, "change_rover_response", {"fields": {
            "result": 0, "rover_item_index": rover,
        }}, 1_200_000_000)
        history.observe(connection, "inventory_snapshot", {
            "container": "inventory",
            "items": [{"item_uid": item_uid} for item_uid in items],
        }, 1_300_000_000)

    def test_persists_only_public_profile_and_hmac_item_fingerprints(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "conexao-a", 123)
            history.close()

            protected = (Path(folder) / "characters.dat").read_bytes()
            self.assertNotIn(b"Personagem 123", protected)
            self.assertNotIn(b'"item_uid":11', protected)

            restored = self._history(folder)
            profile = restored.profile(123)
            self.assertIsNotNone(profile)
            self.assertEqual(profile.name, "Personagem 123")
            self.assertEqual(profile.level, 66)
            self.assertEqual(profile.total_exp, 1_000)
            self.assertEqual(len(profile.item_fingerprints), 3)
            restored.close()

    def test_recovers_unique_character_from_inventory_and_progression(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "antiga", 123)
            history.release("antiga")

            self.assertIsNone(history.observe(
                "nova", "update_exp", {"level": 66, "exp": 1_500},
                2_000_000_000,
            ))
            decision = history.observe(
                "nova", "inventory_delta", {
                    "container": "inventory",
                    "items": [
                        {"item_uid": 11}, {"item_uid": 22}, {"item_uid": 33},
                    ],
                }, 2_100_000_000,
            )

            self.assertIsNotNone(decision)
            self.assertEqual(decision.character_uid, 123)
            self.assertEqual(decision.source, "history-signals")
            self.assertGreaterEqual(decision.score, 80)
            history.close()

    def test_does_not_guess_when_two_profiles_have_the_same_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "antiga-a", 123)
            history.release("antiga-a")
            self._direct(history, "antiga-b", 456)
            history.release("antiga-b")

            history.observe(
                "nova", "update_exp", {"level": 66, "exp": 1_500},
                2_000_000_000,
            )
            decision = history.observe(
                "nova", "inventory_delta", {
                    "container": "inventory",
                    "items": [
                        {"item_uid": 11}, {"item_uid": 22}, {"item_uid": 33},
                    ],
                }, 2_100_000_000,
            )

            self.assertIsNone(decision)
            self.assertGreaterEqual(history.metrics()["ambiguous_matches"], 1)
            history.close()

    def test_correlates_known_uid_after_own_rover_change_without_relogin(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "antiga", 123)
            history.release("antiga")

            history.observe("nova", "change_rover_response", {"fields": {
                "result": 0, "rover_item_index": 4_300_017,
            }}, 2_000_000_000)
            decision = history.observe("nova", "player_equip_update", {"fields": {
                "character_uid": 123,
                "rover_item_index": 4_300_017,
            }}, 2_100_000_000)

            self.assertIsNotNone(decision)
            self.assertEqual(decision.character_uid, 123)
            self.assertEqual(decision.source, "history-correlated-uid")
            history.close()

    def test_one_character_cannot_bind_to_two_live_connections(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "antiga", 123)
            history.release("antiga")

            for connection in ("cliente-a", "cliente-b"):
                history.observe(connection, "update_exp", {
                    "level": 66, "exp": 1_500,
                }, 2_000_000_000)
                decision = history.observe(connection, "inventory_delta", {
                    "container": "inventory",
                    "items": [
                        {"item_uid": 11}, {"item_uid": 22}, {"item_uid": 33},
                    ],
                }, 2_100_000_000)
                if connection == "cliente-a":
                    self.assertIsNotNone(decision)
                else:
                    self.assertIsNone(decision)
            history.close()

    def test_remote_profiles_without_confirmed_name_are_ignored_and_pruned(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            changed = history.merge_remote_profiles([
                {
                    "character_uid": 123,
                    "name": "Personagem confirmado",
                    "level": 66,
                },
                {
                    "character_uid": 456,
                    "name": "",
                    "rover_item_index": 4_100_000,
                },
            ])

            self.assertEqual(changed, 1)
            self.assertIsNotNone(history.profile(123))
            self.assertIsNone(history.profile(456))
            self.assertEqual(history.metrics()["remote_profiles"], 1)
            history.close()

    def test_direct_identity_requires_name_and_cannot_change_on_live_connection(self):
        with tempfile.TemporaryDirectory() as folder:
            history = self._history(folder)
            self._direct(history, "cliente", 123)

            unnamed = history.observe("outra", "world_info_prefix", {"fields": {
                "result": 0,
                "character_uid": 456,
                "character_name": "",
                "level": 66,
            }}, 2_000_000_000)
            conflicting = history.observe("cliente", "world_info_prefix", {"fields": {
                "result": 0,
                "character_uid": 789,
                "character_name": "Outro personagem",
                "level": 66,
            }}, 2_100_000_000)

            self.assertIsNone(unnamed)
            self.assertEqual(conflicting.character_uid, 123)
            self.assertIsNone(history.profile(456))
            self.assertIsNone(history.profile(789))
            self.assertEqual(history.metrics()["invalid_direct_events"], 1)
            self.assertEqual(history.metrics()["conflicting_direct_uids"], 1)
            history.close()


if __name__ == "__main__":
    unittest.main()
