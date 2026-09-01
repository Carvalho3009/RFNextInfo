"""Estado concorrente do programa derivado de snapshots já sanitizados."""

from __future__ import annotations

import time
from typing import Any, Iterable


STATUS_SCHEMA_VERSION = 2
CLIENT_KEYS = tuple(f"client:{chr(97 + index)}" for index in range(7))
FARM_WINDOW_SECONDS = 30
PVP_WINDOW_SECONDS = 3
BOSS_WINDOW_SECONDS = 15


def _fresh(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) and not value.get("stale") else {}


def _recent(value: object, now_ns: int, window_seconds: int) -> dict[str, Any]:
    item = dict(value) if isinstance(value, dict) else {}
    if not item:
        return {}
    observed_at_ns = item.get("observed_at_ns", item.get("last_seen_ns"))
    if isinstance(observed_at_ns, (int, float)) and observed_at_ns > 0:
        age = max(0.0, (now_ns - int(observed_at_ns)) / 1_000_000_000)
    else:
        age = item.get("age_seconds")
        if not isinstance(age, (int, float)):
            return {}
        age = max(0.0, float(age))
    if age > window_seconds:
        return {}
    item["age_seconds"] = round(age, 3)
    item["stale"] = False
    return item


def build_program_status(
    monitors: Iterable[dict[str, Any]],
    map_snapshot: object,
    enabled_modes: Iterable[str],
    *,
    low_hp_percent: int = 30,
    now_ns: int | None = None,
    client_keys: Iterable[str] | None = None,
) -> dict[str, Any]:
    reference_ns = int(now_ns if now_ns is not None else time.time_ns())
    monitor_by_client = {
        str(item.get("client_key") or ""): item
        for item in monitors
        if isinstance(item, dict) and item.get("client_key") in CLIENT_KEYS
    }
    map_source = map_snapshot if isinstance(map_snapshot, dict) else {}
    map_by_client = {
        str(item.get("client_key") or ""): item
        for item in map_source.get("clients") or []
        if isinstance(item, dict) and item.get("client_key") in CLIENT_KEYS
    }
    modes = {str(value) for value in enabled_modes} & {"pve", "pvp", "boss"}
    requested_keys = {
        str(key) for key in (client_keys or ()) if str(key) in CLIENT_KEYS
    }
    keys = [
        key for key in CLIENT_KEYS
        if key in requested_keys or key in monitor_by_client or key in map_by_client
    ]
    clients = []
    for client_key in keys:
        monitor = monitor_by_client.get(client_key, {})
        spatial = map_by_client.get(client_key, {})
        local_known = monitor.get("local_combat_uid") is not None
        map_known = bool(spatial.get("observed_at_ns")) and not spatial.get("stale")
        availability = "available" if local_known or map_known else "unknown"

        pve_activity = _recent(
            monitor.get("pve_activity"), reference_ns, FARM_WINDOW_SECONDS
        )
        pvp = _recent(
            monitor.get("pvp_activity"), reference_ns, PVP_WINDOW_SECONDS
        ) if "pvp" in modes else {}
        bosses = [
            item for item in monitor.get("bosses") or []
            if _recent(item, reference_ns, BOSS_WINDOW_SECONDS)
        ] if "boss" in modes else []
        activities = []
        if pve_activity:
            activities.append("farm")
        if pvp:
            activities.append("pvp")
        if bosses:
            activities.append("boss")
        if not activities:
            activities.append("idle")
        activity = next(
            (value for value in ("pvp", "farm", "boss", "idle") if value in activities),
            "idle",
        )

        if "pvp" in modes and local_known:
            nearby = [
                item for item in monitor.get("nearby_players") or []
                if isinstance(item, dict) and not item.get("stale")
            ]
            threat: bool | None = any(
                item.get("pvp_status") == "enemy" for item in nearby
            )
            under_attack: bool | None = bool(
                pvp and pvp.get("direction") == "entrada"
            )
        else:
            threat = under_attack = None
        boss_nearby: bool | None = bool(bosses) if "boss" in modes and local_known else None
        local = monitor.get("local") if isinstance(monitor.get("local"), dict) else {}
        hp_percent = local.get("hp_percent")
        low_hp: bool | None = (
            float(hp_percent) <= max(1, min(99, int(low_hp_percent)))
            if isinstance(hp_percent, (int, float))
            else None
        )
        teleporting = spatial.get("teleporting")
        if not isinstance(teleporting, bool):
            teleporting = None

        display_status = (
            "teleporting" if teleporting is True
            else "pvp" if pvp
            else "farm" if pve_activity
            else "idle"
        )
        clients.append({
            "client_key": client_key,
            "availability": availability,
            "activity": activity,
            "active_activities": activities,
            "display_status": display_status,
            "signals": {
                "threat": threat,
                "under_attack": under_attack,
                "low_hp": low_hp,
                "boss_nearby": boss_nearby,
                "teleporting": teleporting,
            },
            "evidence": {
                "pve_age_seconds": pve_activity.get("age_seconds"),
                "pvp_age_seconds": pvp.get("age_seconds"),
                "map_age_seconds": spatial.get("age_seconds"),
            },
        })
    return {
        "schema_version": STATUS_SCHEMA_VERSION,
        "generated_at_ns": reference_ns,
        "enabled_modes": sorted(modes),
        "clients": clients,
    }
