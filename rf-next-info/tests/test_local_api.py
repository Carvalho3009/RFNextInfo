import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from app.local_api import (
    LOCAL_API_MAX_CONCURRENT_REQUESTS,
    LOCAL_API_MAX_REQUESTS_PER_SECOND,
    LocalApiTokenStore,
    LocalOutputApi,
    sanitize_status_snapshot,
)


class LocalOutputApiTest(unittest.TestCase):
    def test_status_projection_preserves_teleport_priority_and_pve_evidence(self):
        status = sanitize_status_snapshot({
            "schema_version": 2,
            "generated_at_ns": 123,
            "enabled_modes": ["pve", "pvp", "boss"],
            "clients": [{
                "client_key": "client:a",
                "availability": "available",
                "activity": "pvp",
                "active_activities": ["farm", "pvp", "boss"],
                "display_status": "teleporting",
                "signals": {"teleporting": True, "boss_nearby": True},
                "evidence": {"pve_age_seconds": 2.5, "pvp_age_seconds": 0.5},
            }],
        })

        self.assertEqual(status["schema_version"], 2)
        self.assertEqual(status["clients"][0]["display_status"], "teleporting")
        self.assertEqual(status["clients"][0]["evidence"]["pve_age_seconds"], 2.5)

    def test_loopback_api_requires_bearer_and_sanitizes_map(self):
        token = "t" * 43
        provider = lambda: {
            "capacity": 99,
            "catalog_version": "1.28.5",
            "language": "en",
            "clients": [{
                "client_key": "client:a",
                "map_enabled": True,
                "reason": "active",
                "character_name": "Local",
                "character_uid": "segredo-111",
                "entity_uid": 999888777,
                "map_index": 1202,
                "map_name": "Secret Nemesis Base 2F",
                "map_source": "manual_fallback",
                "position": {"x": 10, "y": 20, "z": 30},
                "region_index": 51001,
                "region_name": "Colônia Saura",
                "region_center": {"x": 11, "y": 22, "z": 0},
                "region_confidence": "map-index-floor",
                "observed_at_ns": 123,
                "age_seconds": 1.5,
                "confidence": "confirmed",
                "nearby_players": [{
                    "name": "Vizinho",
                    "guild_name": "Karvalho",
                    "character_uid": "segredo-222",
                    "entity_uid": 555444333,
                    "position": {"x": 13, "y": 24, "z": 30},
                    "distance": 5,
                    "observed_at_ns": 124,
                    "age_seconds": 1,
                }],
            }],
        }
        status_provider = lambda: {
            "generated_at_ns": 456,
            "enabled_modes": ["pvp"],
            "clients": [{
                "client_key": "client:a",
                "availability": "available",
                "activity": "pvp",
                "active_activities": ["pvp"],
                "display_status": "pvp",
                "character_uid": "segredo-status",
                "signals": {"under_attack": True, "threat": True},
                "evidence": {"pvp_age_seconds": 0.5},
            }],
        }
        health_provider = lambda: {
            "generated_at_ns": 789,
            "process": {
                "version": "2.0",
                "memory_bytes": 1024,
                "memory_budget_bytes": 2048,
                "memory_pressure": False,
                "private_path": "segredo-processo",
            },
            "capture": {
                "state": "active",
                "session_available": True,
                "session_id": "segredo-sessao",
            },
            "checkpoint": {
                "available": True,
                "reason": "interval",
                "age_seconds": 2.5,
            },
            "stream": {
                "available": True,
                "worker_alive": True,
                "queue_depth": 2,
                "queue_limit": 10,
                "dropped_packets": 1,
                "flow": "segredo-fluxo",
            },
        }
        api = LocalOutputApi(
            provider,
            token,
            status_provider=status_provider,
            health_provider=health_provider,
            port=0,
        )
        port = api.start()
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/v1/map", timeout=2
                )
            self.assertEqual(denied.exception.code, 401)

            request = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/map",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                payload = json.load(response)
                headers = dict(response.headers)

            self.assertEqual(payload["capacity"], 2)
            self.assertEqual(payload["map_catalog_version"], "1.28.5")
            self.assertEqual(payload["game_data_language"], "en")
            self.assertEqual(payload["clients"][0]["map_index"], 1202)
            self.assertEqual(
                payload["clients"][0]["map_name"], "Secret Nemesis Base 2F"
            )
            self.assertEqual(
                payload["clients"][0]["map_source"], "manual_fallback"
            )
            self.assertEqual(payload["clients"][0]["region_name"], "Colônia Saura")
            self.assertEqual(payload["clients"][0]["region_index"], 51001)
            self.assertEqual(
                payload["clients"][0]["region_confidence"], "map-index-floor"
            )
            self.assertEqual(
                payload["clients"][0]["region_center"],
                {"x": 11.0, "y": 22.0, "z": 0.0},
            )
            self.assertEqual(
                payload["clients"][0]["nearby_players"][0]["name"],
                "Vizinho",
            )
            encoded = json.dumps(payload, ensure_ascii=False)
            for secret in (
                "segredo-111", "segredo-222", "999888777", "555444333",
                "character_uid", "entity_uid",
            ):
                self.assertNotIn(secret, encoded)
            self.assertEqual(headers["Cache-Control"], "no-store")
            self.assertNotIn("Access-Control-Allow-Origin", headers)

            health = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/health",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(health, timeout=2) as response:
                health_payload = json.load(response)
                self.assertEqual(health_payload["map_clients"], 1)
                self.assertEqual(health_payload["status_clients"], 1)
                self.assertEqual(health_payload["process"]["memory_bytes"], 1024)
                self.assertEqual(health_payload["capture"]["state"], "active")
                self.assertEqual(health_payload["checkpoint"]["reason"], "interval")
                self.assertEqual(health_payload["stream"]["queue_depth"], 2)
            encoded_health = json.dumps(health_payload, ensure_ascii=False)
            for secret in (
                "segredo-processo", "segredo-sessao", "segredo-fluxo",
                "private_path", "session_id", '"flow"',
            ):
                self.assertNotIn(secret, encoded_health)

            status = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/v1/status",
                headers={"Authorization": f"Bearer {token}"},
            )
            with urllib.request.urlopen(status, timeout=2) as response:
                status_payload = json.load(response)
            self.assertEqual(status_payload["clients"][0]["display_status"], "pvp")
            self.assertTrue(status_payload["clients"][0]["signals"]["under_attack"])
            self.assertNotIn("segredo-status", json.dumps(status_payload))
        finally:
            api.stop()

    def test_api_rejects_non_loopback_bind(self):
        with self.assertRaisesRegex(ValueError, "127.0.0.1"):
            LocalOutputApi(lambda: {}, "t" * 43, host="0.0.0.0")

    def test_api_bounds_request_rate_and_concurrency(self):
        api = LocalOutputApi(lambda: {}, "t" * 43, port=0)
        with mock.patch("app.local_api.time.monotonic", return_value=100.0):
            admitted = [
                api._admit_request()
                for _ in range(LOCAL_API_MAX_REQUESTS_PER_SECOND)
            ]
            rejected = api._admit_request()
        with mock.patch("app.local_api.time.monotonic", return_value=101.1):
            admitted_after_window = api._admit_request()

        slots = [
            api._request_slots.acquire(blocking=False)
            for _ in range(LOCAL_API_MAX_CONCURRENT_REQUESTS + 1)
        ]
        for _ in range(LOCAL_API_MAX_CONCURRENT_REQUESTS):
            api._request_slots.release()

        self.assertTrue(all(admitted))
        self.assertFalse(rejected)
        self.assertTrue(admitted_after_window)
        self.assertEqual(
            slots,
            [True] * LOCAL_API_MAX_CONCURRENT_REQUESTS + [False],
        )

    def test_api_returns_429_when_rate_limit_is_reached(self):
        token = "t" * 43
        api = LocalOutputApi(lambda: {}, token, port=0)
        with mock.patch.object(api, "_admit_request", return_value=False):
            port = api.start()
            try:
                request = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/v1/health",
                    headers={"Authorization": f"Bearer {token}"},
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected:
                    urllib.request.urlopen(request, timeout=2)
                self.assertEqual(rejected.exception.code, 429)
            finally:
                api.stop()

    def test_token_store_protects_reuses_and_rotates_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "local-api.bin"
            protect = lambda value: value[::-1]
            unprotect = lambda value: value[::-1]
            with mock.patch("app.local_api.protect", side_effect=protect) as protected, mock.patch(
                "app.local_api.unprotect", side_effect=unprotect
            ):
                store = LocalApiTokenStore(path)
                first = store.load_or_create()
                second = store.load_or_create()
                encrypted = path.read_bytes()
                rotated = store.rotate()

                self.assertEqual(first, second)
                self.assertNotEqual(first, rotated)
                self.assertNotIn(first.encode(), encrypted)
                self.assertEqual(protected.call_count, 2)


if __name__ == "__main__":
    unittest.main()
