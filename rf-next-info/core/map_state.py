"""Estado espacial sanitizado construído sobre os eventos já decodificados."""

from __future__ import annotations

import math
import json
import re
from pathlib import Path
from typing import Any, Iterable


MAP_SCHEMA_VERSION = 1
MAP_CLIENT_LIMIT = 2
MAP_NEARBY_STALE_SECONDS = 15
MAP_LOCAL_STALE_SECONDS = 30
MAP_TELEPORT_STALE_SECONDS = 10
MAP_CATALOG_PATH = Path(__file__).with_name("map_catalog.json")
MAP_PREVIEW_CATALOG_PATH = Path(__file__).with_name("map_previews.json")
CLIENT_KEYS = tuple(f"client:{chr(97 + index)}" for index in range(7))


def _load_map_catalog(path: Path = MAP_CATALOG_PATH) -> tuple[str, dict[int, dict[str, str]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or not isinstance(payload.get("entries"), dict):
            raise ValueError("catálogo de mapas incompatível")
        entries = {
            int(map_index): {
                "key": str(item.get("key") or "")[:80],
                "pt": str(item.get("pt") or "")[:160],
                "en": str(item.get("en") or "")[:160],
            }
            for map_index, item in payload["entries"].items()
            if isinstance(item, dict) and str(map_index).isdigit()
        }
        return str(payload.get("source_version") or "unknown")[:40], entries
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "unavailable", {}


MAP_CATALOG_VERSION, MAP_CATALOG = _load_map_catalog()


def _load_map_previews(
    path: Path = MAP_PREVIEW_CATALOG_PATH,
) -> tuple[str, dict[int, dict[str, Any]]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1 or not isinstance(payload.get("maps"), dict):
            raise ValueError("catálogo espacial incompatível")
        maps = {
            int(map_index): dict(item)
            for map_index, item in payload["maps"].items()
            if str(map_index).isdigit() and isinstance(item, dict)
        }
        return str(payload.get("source_version") or "unknown")[:40], maps
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return "unavailable", {}


MAP_PREVIEW_CATALOG_VERSION, MAP_PREVIEW_CATALOG = _load_map_previews()


def map_name(map_index: object, language: object = "pt") -> str:
    if isinstance(map_index, bool) or not isinstance(map_index, (int, float)):
        return ""
    index = int(map_index)
    preview = MAP_PREVIEW_CATALOG.get(index) or {}
    primary, secondary = (
        ("en", "pt") if str(language).casefold() == "en" else ("pt", "en")
    )
    display_name = str(
        preview.get(f"display_{primary}")
        or preview.get(f"display_{secondary}")
        or ""
    ).strip()
    if display_name:
        return display_name[:160]
    entry = MAP_CATALOG.get(index)
    if not entry:
        return f"Mapa #{index}"
    return entry.get(primary) or entry.get(secondary) or f"Mapa #{index}"


def map_region(
    map_index: object,
    position: object,
    language: object = "pt",
) -> dict[str, Any] | None:
    """Resolve região fixa do MapIndex ou a mais próxima por centro oficial."""
    if isinstance(map_index, bool) or not isinstance(map_index, (int, float)):
        return None
    index = int(map_index)
    entry = MAP_PREVIEW_CATALOG.get(index) or {}
    primary, secondary = (
        ("en", "pt") if str(language).casefold() == "en" else ("pt", "en")
    )
    fixed = entry.get("fixed_region")
    if isinstance(fixed, dict):
        fixed_name = str(fixed.get(primary) or fixed.get(secondary) or "").strip()
        if fixed_name:
            return {
                "region_index": index,
                "region_name": fixed_name[:160],
                "region_center": None,
                "region_confidence": "map-index-floor",
            }
    if not isinstance(position, dict):
        return None
    x, y = position.get("x"), position.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    transform = entry.get("live_position_transform")
    if isinstance(transform, dict):
        try:
            x = float(x) * float(transform.get("scale_x") or 1.0) + float(
                transform.get("offset_x") or 0.0
            )
            y = float(y) * float(transform.get("scale_y") or 1.0) + float(
                transform.get("offset_y") or 0.0
            )
        except (TypeError, ValueError):
            return None
    regions = [
        item for item in entry.get("regions") or []
        if isinstance(item, dict) and isinstance(item.get("center"), dict)
    ]
    if not regions:
        return None
    region = min(
        regions,
        key=lambda item: (
            float(item["center"].get("x") or 0) - float(x)
        ) ** 2 + (
            float(item["center"].get("y") or 0) - float(y)
        ) ** 2,
    )
    center = region["center"]
    return {
        "region_index": int(region.get("region_index") or 0) or None,
        "region_name": str(region.get(primary) or region.get(secondary) or "")[:160] or None,
        "region_center": {
            axis: round(float(center.get(axis) or 0), 3)
            for axis in ("x", "y", "z")
        },
        "region_confidence": "nearest-official-center",
    }


def apply_manual_map_fallbacks(
    snapshot: object, fallbacks: object
) -> dict[str, Any]:
    """Aplica nomes manuais somente quando o catálogo automático não resolve."""
    result = dict(snapshot) if isinstance(snapshot, dict) else {}
    configured = fallbacks if isinstance(fallbacks, dict) else {}
    clients = []
    for raw in result.get("clients") or []:
        if not isinstance(raw, dict):
            continue
        client = dict(raw)
        client_key = str(client.get("client_key") or "")
        was_manual = client.get("map_source") == "manual_fallback"
        automatic_value = (
            client.get("automatic_map_name")
            if was_manual
            else client.get("map_name")
        )
        automatic_map_index = (
            client.get("automatic_map_index")
            if was_manual
            else client.get("map_index")
        )
        automatic_region = {
            field: (
                client.get(f"automatic_{field}")
                if was_manual else client.get(field)
            )
            for field in (
                "region_index", "region_name", "region_center", "region_confidence"
            )
        }
        automatic_name = str(automatic_value or "").strip()
        client["map_name"] = automatic_name or None
        client["map_index"] = automatic_map_index
        client.pop("automatic_map_name", None)
        client.pop("automatic_map_index", None)
        client.pop("manual_map_name", None)
        for field, value in automatic_region.items():
            client[field] = value
            client.pop(f"automatic_{field}", None)
        client["map_source"] = "automatic" if automatic_name else "unresolved"

        fallback = configured.get(client_key)
        manual_name = str(
            (fallback or {}).get("map_name") if isinstance(fallback, dict) else ""
        ).strip()[:160]
        manual_region = str(
            (fallback or {}).get("region_name") if isinstance(fallback, dict) else ""
        ).strip()[:160]
        try:
            manual_map_index = int(
                (fallback or {}).get("map_index")
                if isinstance(fallback, dict) else 0
            )
        except (TypeError, ValueError):
            manual_map_index = 0
        automatic_resolved = bool(
            automatic_name and not automatic_name.casefold().startswith("mapa #")
        )
        if manual_name and not automatic_resolved:
            client["automatic_map_name"] = automatic_name or None
            client["automatic_map_index"] = automatic_map_index
            client["manual_map_name"] = manual_name
            client["map_name"] = manual_name
            if manual_map_index > 0:
                client["map_index"] = manual_map_index
            client["map_source"] = "manual_fallback"
            if manual_region:
                for field in (
                    "region_index", "region_name", "region_center", "region_confidence"
                ):
                    client[f"automatic_{field}"] = automatic_region[field]
                client["region_index"] = None
                client["region_name"] = manual_region
                client["region_center"] = None
                client["region_confidence"] = "manual-fallback"
        clients.append(client)
    result["clients"] = clients
    return result


def _position(value: object) -> dict[str, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        return None
    try:
        coordinates = tuple(float(item) for item in value)
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) and abs(item) <= 1_000_000_000 for item in coordinates):
        return None
    return {
        "x": round(coordinates[0], 3),
        "y": round(coordinates[1], 3),
        "z": round(coordinates[2], 3),
    }


def _unit_position(unit: dict[str, Any]) -> dict[str, float] | None:
    return _position(
        [unit.get("position_x"), unit.get("position_y"), unit.get("position_z")]
    )


def _event_ports(event: dict[str, Any]) -> set[int]:
    return {
        int(value)
        for value in re.findall(r":(\d+)(?:\s|$)", str(event.get("flow") or ""))
    }


def _age_seconds(reference_ns: int, observed_ns: int) -> float:
    return round(max(0, reference_ns - observed_ns) / 1_000_000_000, 3)


def _distance(first: dict[str, float], second: dict[str, float]) -> float:
    return round(math.sqrt(sum((first[key] - second[key]) ** 2 for key in ("x", "y", "z"))), 3)


def _client_snapshot(
    client_key: str,
    events: Iterable[dict[str, Any]],
    *,
    now_ns: int | None = None,
    language: str = "pt",
) -> dict[str, Any]:
    ordered = sorted(
        enumerate(events),
        key=lambda item: (int(item[1].get("ts_ns") or 0), item[0]),
    )
    reference_ns = int(now_ns or 0) or max(
        (int(event.get("ts_ns") or 0) for _index, event in ordered),
        default=0,
    )
    character_uid = ""
    character_name = ""
    local_entity_uid: int | None = None
    local_position: dict[str, float] | None = None
    local_observed_ns = 0
    map_index: int | None = None
    map_observed_ns = 0
    teleporting: bool | None = None
    teleport_observed_ns = 0
    players: dict[int, dict[str, Any]] = {}

    for _index, event in ordered:
        kind = str(event.get("type") or "")
        data = event.get("data") or {}
        fields = data.get("fields") or {}
        observed_ns = int(event.get("ts_ns") or 0)
        if kind == "world_info_prefix":
            value = fields.get("character_uid")
            if value is not None:
                character_uid = str(value)
            character_name = str(fields.get("character_name") or character_name).strip()[:80]
            continue
        if kind == "appear_player_list":
            for raw in data.get("units") or []:
                if not isinstance(raw, dict):
                    continue
                uid = raw.get("uid")
                if not isinstance(uid, (int, float)) or int(uid) <= 0:
                    continue
                uid = int(uid)
                unit_character_uid = str(raw.get("character_uid") or "")
                entry = {
                    "name": str(raw.get("name") or "").strip()[:80],
                    "guild_name": str(raw.get("guild_name") or "").strip()[:80],
                    "character_uid": unit_character_uid,
                    "position": _unit_position(raw),
                    "observed_at_ns": observed_ns,
                }
                if character_uid and unit_character_uid == character_uid:
                    local_entity_uid = uid
                    character_name = entry["name"] or character_name
                    if entry["position"] is not None and observed_ns >= local_observed_ns:
                        local_position = entry["position"]
                        local_observed_ns = observed_ns
                    players.pop(uid, None)
                else:
                    players[uid] = entry
            continue
        if kind == "move_player_request":
            position = _position(fields.get("position"))
            if position is not None and observed_ns >= local_observed_ns:
                local_position = position
                local_observed_ns = observed_ns
            if teleporting is True:
                teleporting = False
            continue
        if kind == "move_player_update":
            uid = fields.get("entity_uid")
            position = _position(fields.get("position"))
            if not isinstance(uid, (int, float)) or position is None:
                continue
            uid = int(uid)
            if uid == local_entity_uid and observed_ns >= local_observed_ns:
                local_position = position
                local_observed_ns = observed_ns
            elif uid in players and observed_ns >= int(players[uid]["observed_at_ns"]):
                players[uid]["position"] = position
                players[uid]["observed_at_ns"] = observed_ns
            continue
        if kind in {"request_teleport", "teleport_request"}:
            teleporting = True
            teleport_observed_ns = observed_ns
            continue
        if kind in {"request_teleport_result", "teleport_response"}:
            result = fields.get("result")
            if not isinstance(result, (int, float)) or int(result) != 0:
                teleporting = False
                teleport_observed_ns = observed_ns
                continue
            value = fields.get("map_index")
            if isinstance(value, (int, float)) and 0 <= int(value) < 2**32:
                map_index = int(value)
                map_observed_ns = observed_ns
            position = _position(fields.get("resolved_position"))
            if position is not None and observed_ns >= local_observed_ns:
                local_position = position
                local_observed_ns = observed_ns
            teleporting = True
            teleport_observed_ns = observed_ns
            continue
        if kind == "warp_player":
            uid = fields.get("entity_uid")
            position = _position(fields.get("position"))
            if not isinstance(uid, (int, float)):
                continue
            uid = int(uid)
            if uid == local_entity_uid:
                if position is not None and observed_ns >= local_observed_ns:
                    local_position = position
                    local_observed_ns = observed_ns
                teleporting = True
                teleport_observed_ns = observed_ns
            elif uid in players and position is not None:
                players[uid]["position"] = position
                players[uid]["observed_at_ns"] = observed_ns
            continue
        if kind == "end_warp_player":
            teleporting = False
            teleport_observed_ns = observed_ns
            continue
        if kind == "disappear_unit_list":
            for uid in fields.get("entity_uids") or []:
                if isinstance(uid, (int, float)):
                    players.pop(int(uid), None)

    if character_uid:
        for uid, player in tuple(players.items()):
            if player.get("character_uid") == character_uid:
                local_entity_uid = uid
                character_name = str(player.get("name") or character_name)
                if player.get("position") is not None:
                    local_position = player["position"]
                    local_observed_ns = int(player.get("observed_at_ns") or 0)
                players.pop(uid, None)

    nearby = []
    for player in players.values():
        position = player.get("position")
        observed_ns = int(player.get("observed_at_ns") or 0)
        if position is None or not observed_ns:
            continue
        age = _age_seconds(reference_ns, observed_ns)
        if reference_ns and age > MAP_NEARBY_STALE_SECONDS:
            continue
        nearby.append({
            "name": str(player.get("name") or "Não identificado"),
            "guild_name": str(player.get("guild_name") or ""),
            "position": position,
            "distance": _distance(local_position, position) if local_position else None,
            "observed_at_ns": observed_ns,
            "age_seconds": age,
            "confidence": "confirmed",
        })
    nearby.sort(key=lambda item: (
        item["distance"] is None,
        float(item["distance"] or 0),
        str(item["name"]).casefold(),
    ))

    observed_at_ns = max(local_observed_ns, map_observed_ns)
    local_age = _age_seconds(reference_ns, local_observed_ns) if local_observed_ns else None
    if (
        teleporting is True
        and teleport_observed_ns
        and reference_ns - teleport_observed_ns
        > MAP_TELEPORT_STALE_SECONDS * 1_000_000_000
    ):
        teleporting = False
    region = map_region(map_index, local_position, language) or {}
    return {
        "client_key": client_key,
        "map_enabled": True,
        "reason": "active" if observed_at_ns else "awaiting_data",
        "character_name": character_name,
        "map_index": map_index,
        "map_name": map_name(map_index, language) if map_index is not None else None,
        "map_source": "automatic" if map_index is not None else "unresolved",
        "position": local_position,
        "region_index": region.get("region_index"),
        "region_name": region.get("region_name"),
        "region_center": region.get("region_center"),
        "region_confidence": region.get("region_confidence"),
        "observed_at_ns": observed_at_ns or None,
        "age_seconds": local_age,
        "stale": bool(local_age is not None and local_age > MAP_LOCAL_STALE_SECONDS),
        "teleporting": teleporting,
        "teleport_observed_at_ns": teleport_observed_ns or None,
        "confidence": "confirmed" if observed_at_ns else "unavailable",
        "nearby_players": nearby,
    }


class MapModule:
    """Mantém duas vagas espaciais estáveis e produz snapshots públicos."""

    def __init__(self, capacity: int = MAP_CLIENT_LIMIT, language: str = "pt") -> None:
        self.capacity = max(1, min(MAP_CLIENT_LIMIT, int(capacity)))
        self.language = "en" if str(language).casefold() == "en" else "pt"
        self._admitted: list[str] = []

    def set_language(self, language: object) -> None:
        self.language = "en" if str(language).casefold() == "en" else "pt"

    def reset(self) -> None:
        self._admitted.clear()

    def snapshot(
        self,
        events: Iterable[dict[str, Any]],
        client_ports: Iterable[Iterable[int]],
        *,
        now_ns: int | None = None,
    ) -> dict[str, Any]:
        events = list(events)
        groups = [tuple(int(port) for port in ports) for ports in client_ports]
        active = [CLIENT_KEYS[index] for index, ports in enumerate(groups[:7]) if ports]
        self._admitted = [key for key in self._admitted if key in active]
        for key in active:
            if key not in self._admitted and len(self._admitted) < self.capacity:
                self._admitted.append(key)

        clients = []
        for index, ports in enumerate(groups[:7]):
            if not ports:
                continue
            client_key = CLIENT_KEYS[index]
            if client_key not in self._admitted:
                clients.append({
                    "client_key": client_key,
                    "map_enabled": False,
                    "reason": "capacity_limit",
                    "character_name": "",
                    "map_index": None,
                    "map_name": None,
                    "map_source": "unresolved",
                    "position": None,
                    "region_index": None,
                    "region_name": None,
                    "region_center": None,
                    "region_confidence": None,
                    "observed_at_ns": None,
                    "age_seconds": None,
                    "stale": False,
                    "teleporting": None,
                    "confidence": "unavailable",
                    "nearby_players": [],
                })
                continue
            routed = [event for event in events if _event_ports(event).intersection(ports)]
            clients.append(_client_snapshot(
                client_key,
                routed,
                now_ns=now_ns,
                language=self.language,
            ))

        return {
            "schema_version": MAP_SCHEMA_VERSION,
            "catalog_version": MAP_CATALOG_VERSION,
            "language": self.language,
            "capacity": self.capacity,
            "active_count": len(self._admitted),
            "detected_count": len(active),
            "limited_count": max(0, len(active) - len(self._admitted)),
            "clients": clients,
        }
