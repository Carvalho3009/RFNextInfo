"""Inferência conservadora de contexto usando somente proximidade confirmada."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


CLIENT_KEYS = tuple(f"client:{chr(97 + index)}" for index in range(7))
DEFAULT_MIN_OBSERVATIONS = 3
DEFAULT_MIN_STABLE_SECONDS = 5.0
MAX_CONTEXT_MOBS = 64


@dataclass
class _ContextCandidate:
    key: tuple[str, str]
    map_name: str
    spot_name: str
    first_seen_ns: int
    last_seen_ns: int
    observations: int = 1
    mobs: list[str] = field(default_factory=list)
    mob_levels: dict[str, int | str] = field(default_factory=dict)
    mob_observations: dict[str, int] = field(default_factory=dict)


class SubsessionContextStabilizer:
    """Confirma contexto repetido antes de gravar uma inferência automática."""

    def __init__(
        self,
        *,
        min_observations: int = DEFAULT_MIN_OBSERVATIONS,
        min_stable_seconds: float = DEFAULT_MIN_STABLE_SECONDS,
    ) -> None:
        self.min_observations = max(2, int(min_observations))
        self.min_stable_ns = max(0, int(min_stable_seconds * 1_000_000_000))
        self._candidates: dict[str, _ContextCandidate] = {}

    def clear(self) -> None:
        self._candidates.clear()

    def discard(self, client_key: str) -> None:
        self._candidates.pop(client_key.strip().casefold(), None)

    def observe(
        self,
        client_key: str,
        context: dict[str, Any],
        *,
        now_ns: int,
    ) -> dict[str, Any] | None:
        client_key = client_key.strip().casefold()
        if client_key not in CLIENT_KEYS or now_ns <= 0:
            return None
        map_name = str(context.get("map_name") or "").strip()[:160]
        spot_name = str(context.get("spot_name") or "").strip()[:160]
        mobs = list(dict.fromkeys(
            str(mob).strip()[:160]
            for mob in (context.get("mobs") or [])
            if str(mob).strip()
        ))[:MAX_CONTEXT_MOBS]
        levels = {
            str(mob).strip()[:160]: level
            for mob, level in (context.get("mob_levels") or {}).items()
            if str(mob).strip() and level not in (None, "")
        }
        if not (map_name or spot_name or mobs):
            self.discard(client_key)
            return None

        key = (map_name.casefold(), spot_name.casefold())
        candidate = self._candidates.get(client_key)
        if (
            candidate is None
            or candidate.key != key
            or now_ns < candidate.last_seen_ns
        ):
            candidate = _ContextCandidate(
                key=key,
                map_name=map_name,
                spot_name=spot_name,
                first_seen_ns=now_ns,
                last_seen_ns=now_ns,
                mobs=mobs,
                mob_levels=levels,
                mob_observations={mob: 1 for mob in mobs},
            )
            self._candidates[client_key] = candidate
        else:
            candidate.last_seen_ns = now_ns
            candidate.observations += 1
            for mob in mobs:
                if mob not in candidate.mobs and len(candidate.mobs) < MAX_CONTEXT_MOBS:
                    candidate.mobs.append(mob)
                if mob in candidate.mobs:
                    candidate.mob_observations[mob] = (
                        candidate.mob_observations.get(mob, 0) + 1
                    )
            candidate.mob_levels.update(levels)

        if (
            candidate.observations < self.min_observations
            or now_ns - candidate.first_seen_ns < self.min_stable_ns
        ):
            return None
        confirmed_mobs = [
            mob for mob in candidate.mobs
            if candidate.mob_observations.get(mob, 0) >= self.min_observations
        ]
        return {
            "map_name": candidate.map_name,
            "spot_name": candidate.spot_name,
            "mobs": confirmed_mobs,
            "mob_levels": {
                mob: candidate.mob_levels[mob]
                for mob in confirmed_mobs if mob in candidate.mob_levels
            },
            "context_source": "proximity",
            "context_confidence": "stable",
            "context_observation_count": candidate.observations,
            "context_first_seen_ns": candidate.first_seen_ns,
            "context_updated_ns": candidate.last_seen_ns,
        }


def infer_subsession_context(
    monitor: dict[str, Any],
    location: object,
    farm_catalog: dict[str, dict[str, dict[str, tuple[int, ...]]]],
) -> dict[str, Any]:
    context = location if isinstance(location, dict) else {}
    map_hint = str(
        context.get("map_name")
        or context.get("label")
        or (location if isinstance(location, str) else "")
        or ""
    ).strip()
    region_hint = str(
        context.get("region_name") or context.get("spot_name") or ""
    ).strip()
    observed: dict[str, int | None] = {}
    candidates = [
        *(monitor.get("nearby_monsters") or []),
        monitor.get("pve"),
    ]
    for item in candidates:
        if not isinstance(item, dict) or item.get("dead") or item.get("stale"):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        level = item.get("level")
        observed[name] = int(level) if isinstance(level, (int, float)) else None

    normalized = {name.casefold() for name in observed}
    matches: list[tuple[str, str]] = []
    for map_name, spots in farm_catalog.items():
        if map_hint in farm_catalog and map_name != map_hint:
            continue
        for spot_name, mobs in spots.items():
            catalog_names = {name.casefold() for name in mobs}
            if normalized and normalized.issubset(catalog_names):
                matches.append((map_name, spot_name))

    inferred_map = map_hint
    inferred_spot = region_hint
    if region_hint:
        inferred_map = map_hint
    elif len(matches) == 1:
        inferred_map, inferred_spot = matches[0]
    elif map_hint in farm_catalog:
        inferred_map = map_hint

    return {
        "map_name": inferred_map,
        "spot_name": inferred_spot,
        "mobs": list(observed),
        "mob_levels": {
            name: level for name, level in observed.items() if level is not None
        },
    }


def automatic_subsession_end(
    subsession: dict[str, Any],
    monitor: dict[str, Any] | None,
    spatial: dict[str, Any] | None,
    *,
    now_ns: int,
    no_kill_seconds: int = 30,
) -> tuple[int, str] | None:
    """Retorna o primeiro limite automático confirmado após o início."""
    started_ns = int(subsession.get("started_ns") or 0)
    if started_ns <= 0 or now_ns <= started_ns:
        return None
    monitor = monitor or {}
    spatial = spatial or {}
    candidates: list[tuple[int, str]] = []

    if subsession.get("end_on_teleport") and spatial.get("teleporting") is True:
        observed = int(spatial.get("teleport_observed_at_ns") or 0)
        if started_ns < observed <= now_ns:
            candidates.append((observed, "teleporte"))

    if subsession.get("end_on_death"):
        death = monitor.get("local_death") or {}
        observed = int(death.get("observed_at_ns") or 0)
        if started_ns < observed <= now_ns:
            candidates.append((observed, "morte"))

    if subsession.get("end_after_no_kill"):
        kill = monitor.get("pve_kill") or {}
        observed = int(kill.get("observed_at_ns") or 0)
        last_kill = observed if observed > started_ns else started_ns
        boundary = last_kill + max(1, int(no_kill_seconds)) * 1_000_000_000
        if boundary <= now_ns:
            candidates.append((boundary, "30 s sem kill"))

    return min(candidates, default=None)
