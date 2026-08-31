"""Recuperação local e conservadora da identidade do personagem do Agent.

O histórico contém somente UIDs públicos de personagens já confirmados. UIDs de
itens são transformados em HMAC antes de serem persistidos e nenhum UID de
sessão/login é aceito por este módulo.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.protected_state import protect_for_current_user, unprotect


HISTORY_SCHEMA = "rf-qol.agent-character-history/v1"
MAX_PROFILES = 128
MAX_ITEM_FINGERPRINTS = 512
MAX_CONNECTIONS = 128
RECOVERY_SCORE = 80
RECOVERY_MARGIN = 25
CORRELATED_ACTION_NS = 5 * 1_000_000_000


def _integer(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _uid(value: object) -> int | None:
    result = _integer(value)
    return result if result is not None and 0 < result <= 2**64 - 1 else None


def _text(value: object, limit: int = 120) -> str:
    return str(value or "").strip()[:limit]


def _fields(data: dict[str, Any]) -> dict[str, Any]:
    value = data.get("fields")
    return value if isinstance(value, dict) else data


@dataclass
class CharacterProfile:
    character_uid: int
    name: str = ""
    level: int | None = None
    total_exp: int | None = None
    biosuit_item_index: int | None = None
    rover_item_index: int | None = None
    power: int | None = None
    item_fingerprints: set[str] = field(default_factory=set)
    last_confirmed_ns: int = 0
    confirmation_source: str = "direct"

    def public_payload(self) -> dict[str, Any]:
        return {
            key: value for key, value in {
                "character_uid": self.character_uid,
                "name": self.name or None,
                "level": self.level,
                "biosuit_item_index": self.biosuit_item_index,
                "rover_item_index": self.rover_item_index,
                "power": self.power,
            }.items() if value is not None
        }


@dataclass
class _Observation:
    level: int | None = None
    total_exp: int | None = None
    biosuit_item_index: int | None = None
    rover_item_index: int | None = None
    power: int | None = None
    item_fingerprints: set[str] = field(default_factory=set)
    correlated_uid: int | None = None
    correlated_until_ns: int = 0
    expected_rover_item_index: int | None = None


@dataclass(frozen=True)
class IdentityDecision:
    character_uid: int
    source: str
    score: int


class AgentCharacterHistory:
    """Histórico DPAPI e associações efêmeras por conexão TCP."""

    def __init__(
        self,
        path: Path,
        installation_id: str,
        fingerprint_key: bytes,
        *,
        clock_ns=time.time_ns,
    ) -> None:
        if len(fingerprint_key) < 16:
            raise ValueError("Chave do histórico inválida")
        self.path = Path(path)
        self.installation_id = _text(installation_id, 128)
        self._key = bytes(fingerprint_key)
        self._clock_ns = clock_ns
        self._profiles: dict[int, CharacterProfile] = {}
        self._observations: dict[str, _Observation] = {}
        self._bindings: dict[str, IdentityDecision] = {}
        self._dirty = False
        self._lock = threading.RLock()
        self.direct_confirmations = 0
        self.invalid_direct_events = 0
        self.conflicting_direct_uids = 0
        self.recovered_confirmations = 0
        self.ambiguous_matches = 0
        self.remote_profiles = 0
        self._load()

    def _fingerprint(self, item_uid: object) -> str | None:
        value = _uid(item_uid)
        if value is None:
            return None
        return hmac.new(
            self._key,
            f"inventory-item:{value}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()[:32]

    def _load(self) -> None:
        try:
            payload = json.loads(unprotect(self.path.read_bytes()))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != HISTORY_SCHEMA
            or payload.get("installation_id") != self.installation_id
            or not isinstance(payload.get("profiles"), list)
        ):
            return
        for raw in payload["profiles"][:MAX_PROFILES]:
            if not isinstance(raw, dict):
                continue
            character_uid = _uid(raw.get("character_uid"))
            if character_uid is None:
                continue
            confirmation_source = _text(raw.get("confirmation_source"), 32) or "direct"
            name = _text(raw.get("name"))
            if confirmation_source == "server" and not name:
                self._dirty = True
                continue
            fingerprints = raw.get("item_fingerprints")
            clean_fingerprints = {
                str(value)
                for value in fingerprints or []
                if isinstance(value, str)
                and len(value) == 32
                and all(char in "0123456789abcdef" for char in value)
            }
            self._profiles[character_uid] = CharacterProfile(
                character_uid=character_uid,
                name=name,
                level=_integer(raw.get("level")),
                total_exp=_integer(raw.get("total_exp")),
                biosuit_item_index=_integer(raw.get("biosuit_item_index")),
                rover_item_index=_integer(raw.get("rover_item_index")),
                power=_integer(raw.get("power")),
                item_fingerprints=set(list(clean_fingerprints)[:MAX_ITEM_FINGERPRINTS]),
                last_confirmed_ns=max(0, _integer(raw.get("last_confirmed_ns")) or 0),
                confirmation_source=confirmation_source,
            )

    def _save(self) -> None:
        if not self._dirty:
            return
        profiles = sorted(
            self._profiles.values(),
            key=lambda item: item.last_confirmed_ns,
            reverse=True,
        )[:MAX_PROFILES]
        payload = {
            "schema": HISTORY_SCHEMA,
            "installation_id": self.installation_id,
            "profiles": [{
                "character_uid": item.character_uid,
                "name": item.name,
                "level": item.level,
                "total_exp": item.total_exp,
                "biosuit_item_index": item.biosuit_item_index,
                "rover_item_index": item.rover_item_index,
                "power": item.power,
                "item_fingerprints": sorted(item.item_fingerprints),
                "last_confirmed_ns": item.last_confirmed_ns,
                "confirmation_source": item.confirmation_source,
            } for item in profiles],
        }
        encoded = protect_for_current_user(
            json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            description="RF QOL Agent character history",
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        temporary.write_bytes(encoded)
        os.chmod(temporary, 0o600)
        os.replace(temporary, self.path)
        self._dirty = False

    def _profile(self, character_uid: int) -> CharacterProfile:
        profile = self._profiles.get(character_uid)
        if profile is None:
            profile = CharacterProfile(character_uid=character_uid)
            self._profiles[character_uid] = profile
        return profile

    def merge_remote_profiles(self, values: list[dict[str, Any]]) -> int:
        """Importa somente personagens já vinculados a esta instalação no site."""
        changed = 0
        accepted = 0
        with self._lock:
            stale_server_profiles = [
                uid for uid, profile in self._profiles.items()
                if profile.confirmation_source == "server" and not profile.name
            ]
            for uid in stale_server_profiles:
                self._profiles.pop(uid, None)
                self._dirty = True
            for raw in values[:MAX_PROFILES]:
                if not isinstance(raw, dict):
                    continue
                character_uid = _uid(raw.get("character_uid"))
                name = _text(raw.get("character_name") or raw.get("name"))
                if character_uid is None or not name:
                    continue
                accepted += 1
                profile = self._profile(character_uid)
                before = profile.public_payload()
                self._merge_fields(profile, raw)
                profile.confirmation_source = (
                    profile.confirmation_source
                    if profile.last_confirmed_ns else "server"
                )
                if profile.public_payload() != before:
                    changed += 1
                    self._dirty = True
            self.remote_profiles = accepted
            self._trim_profiles()
            self._save()
        return changed

    @staticmethod
    def _merge_fields(profile: CharacterProfile, values: dict[str, Any]) -> None:
        name = _text(values.get("character_name") or values.get("name"))
        if name:
            profile.name = name
        for source, target in (
            ("level", "level"),
            ("exp", "total_exp"),
            ("total_exp", "total_exp"),
            ("biosuit_item_index", "biosuit_item_index"),
            ("rover_item_index", "rover_item_index"),
            ("combat_power", "power"),
            ("power", "power"),
        ):
            value = _integer(values.get(source))
            if value is not None and value >= 0:
                setattr(profile, target, value)

    def _item_fingerprints(self, data: dict[str, Any]) -> set[str]:
        raw_items = (
            data.get("items") if isinstance(data.get("items"), list)
            else [data.get("item")] if isinstance(data.get("item"), dict)
            else []
        )
        result: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            fingerprint = self._fingerprint(raw.get("item_uid"))
            if fingerprint:
                result.add(fingerprint)
        return result

    def _update_observation(
        self, observation: _Observation, kind: str, data: dict[str, Any], now_ns: int,
    ) -> None:
        fields = _fields(data)
        if kind == "update_exp":
            observation.level = _integer(data.get("level"))
            observation.total_exp = _integer(data.get("exp"))
        elif kind in {"player_stat", "lobby_stat"}:
            observation.power = _integer(fields.get("combat_power"))
        elif kind in {"change_biosuit_response", "world_info_prefix"}:
            if _integer(fields.get("result"),) in {None, 0}:
                observation.biosuit_item_index = _integer(
                    fields.get("biosuit_item_index")
                )
        elif kind == "change_rover_response":
            if _integer(fields.get("result")) in {None, 0}:
                observation.rover_item_index = _integer(
                    fields.get("rover_item_index")
                )
                observation.expected_rover_item_index = observation.rover_item_index
                observation.correlated_until_ns = now_ns + CORRELATED_ACTION_NS
        elif kind == "change_equip_slot_response":
            if _integer(fields.get("result")) in {None, 0}:
                observation.correlated_until_ns = now_ns + CORRELATED_ACTION_NS
        elif kind == "player_equip_update":
            rover = _integer(fields.get("rover_item_index"))
            if rover is not None:
                observation.rover_item_index = rover
            candidate_uid = _uid(fields.get("character_uid"))
            if (
                candidate_uid in self._profiles
                and observation.correlated_until_ns >= now_ns
                and (
                    observation.expected_rover_item_index is None
                    or rover == observation.expected_rover_item_index
                )
            ):
                observation.correlated_uid = candidate_uid
        if kind in {"inventory_snapshot", "inventory_delta"}:
            observation.item_fingerprints.update(self._item_fingerprints(data))
            if len(observation.item_fingerprints) > MAX_ITEM_FINGERPRINTS:
                observation.item_fingerprints = set(
                    sorted(observation.item_fingerprints)[-MAX_ITEM_FINGERPRINTS:]
                )

    def _score(
        self, observation: _Observation, profile: CharacterProfile,
    ) -> tuple[int, set[str]] | None:
        if observation.correlated_uid is not None:
            return (
                (100, {"correlated_uid"})
                if observation.correlated_uid == profile.character_uid else None
            )
        score = 0
        evidence: set[str] = set()
        if observation.level is not None and profile.level is not None:
            if observation.level < profile.level:
                return None
            if observation.level == profile.level:
                if (
                    observation.total_exp is not None
                    and profile.total_exp is not None
                    and observation.total_exp < profile.total_exp
                ):
                    return None
                if (
                    observation.total_exp is not None
                    and profile.total_exp is not None
                    and observation.total_exp == profile.total_exp
                ):
                    score += 60
                elif observation.total_exp is not None and profile.total_exp is not None:
                    score += 25
                else:
                    score += 10
            else:
                score += 20
            evidence.add("progression")
        overlap = len(observation.item_fingerprints & profile.item_fingerprints)
        if overlap >= 3:
            score += 70
            evidence.add("inventory")
        elif overlap == 2:
            score += 45
            evidence.add("inventory")
        elif overlap == 1:
            score += 20
            evidence.add("inventory")
        for observed, known, points in (
            (observation.biosuit_item_index, profile.biosuit_item_index, 10),
            (observation.rover_item_index, profile.rover_item_index, 10),
            (observation.power, profile.power, 10),
        ):
            if observed is not None and known is not None and observed == known:
                score += points
                evidence.add("equipment")
        return score, evidence

    def _recover(self, connection: str) -> IdentityDecision | None:
        observation = self._observations[connection]
        active_uids = {
            decision.character_uid
            for other, decision in self._bindings.items()
            if other != connection
        }
        candidates: list[tuple[int, int, set[str]]] = []
        for profile in self._profiles.values():
            if profile.character_uid in active_uids:
                continue
            scored = self._score(observation, profile)
            if scored is None:
                continue
            score, evidence = scored
            if "correlated_uid" in evidence or (
                score >= RECOVERY_SCORE and len(evidence) >= 2
            ):
                candidates.append((score, profile.character_uid, evidence))
        candidates.sort(reverse=True)
        if not candidates:
            return None
        best_score, best_uid, best_evidence = candidates[0]
        second_score = candidates[1][0] if len(candidates) > 1 else -1
        if second_score >= 0 and best_score - second_score < RECOVERY_MARGIN:
            self.ambiguous_matches += 1
            return None
        source = (
            "history-correlated-uid"
            if "correlated_uid" in best_evidence else "history-signals"
        )
        decision = IdentityDecision(best_uid, source, best_score)
        self._bindings[connection] = decision
        self.recovered_confirmations += 1
        profile = self._profiles[best_uid]
        profile.confirmation_source = source
        profile.last_confirmed_ns = max(profile.last_confirmed_ns, self._clock_ns())
        self._dirty = True
        self._save()
        return decision

    def observe(
        self, connection: str, kind: str, data: dict[str, Any], occurred_ns: int,
    ) -> IdentityDecision | None:
        connection = _text(connection, 240)
        if not connection:
            return None
        now_ns = max(0, int(occurred_ns or self._clock_ns()))
        fields = _fields(data)
        with self._lock:
            direct_uid = None
            if kind == "world_info_prefix":
                result = _integer(fields.get("result"))
                direct_uid = _uid(fields.get("character_uid"))
                if (
                    result not in {None, 0}
                    or not _text(fields.get("character_name"))
                ):
                    self.invalid_direct_events += 1
                    return self._bindings.get(connection)
            if direct_uid is not None:
                current = self._bindings.get(connection)
                if (
                    current is not None
                    and current.source == "direct"
                    and current.character_uid != direct_uid
                ):
                    self.conflicting_direct_uids += 1
                    return current
                decision = IdentityDecision(direct_uid, "direct", 100)
                self._bindings[connection] = decision
                profile = self._profile(direct_uid)
                self._merge_fields(profile, fields)
                profile.last_confirmed_ns = now_ns
                profile.confirmation_source = "direct"
                self.direct_confirmations += 1
                self._dirty = True
                self._save()
                return decision
            observation = self._observations.setdefault(connection, _Observation())
            self._update_observation(observation, kind, data, now_ns)
            decision = self._bindings.get(connection)
            if decision is None:
                decision = self._recover(connection)
            if decision is not None:
                profile = self._profile(decision.character_uid)
                before = profile.public_payload()
                self._merge_fields(profile, fields if kind != "update_exp" else data)
                fingerprints = self._item_fingerprints(data)
                if fingerprints:
                    profile.item_fingerprints.update(fingerprints)
                    if len(profile.item_fingerprints) > MAX_ITEM_FINGERPRINTS:
                        profile.item_fingerprints = set(
                            sorted(profile.item_fingerprints)[-MAX_ITEM_FINGERPRINTS:]
                        )
                if profile.public_payload() != before or fingerprints:
                    self._dirty = True
            self._trim_connections()
            return decision

    def decision(self, connection: str) -> IdentityDecision | None:
        with self._lock:
            return self._bindings.get(connection)

    def profile(self, character_uid: int) -> CharacterProfile | None:
        with self._lock:
            return self._profiles.get(int(character_uid))

    def release(self, connection: str) -> None:
        with self._lock:
            self._bindings.pop(connection, None)
            self._observations.pop(connection, None)

    def _trim_profiles(self) -> None:
        if len(self._profiles) <= MAX_PROFILES:
            return
        keep = sorted(
            self._profiles.values(),
            key=lambda item: item.last_confirmed_ns,
            reverse=True,
        )[:MAX_PROFILES]
        self._profiles = {item.character_uid: item for item in keep}

    def _trim_connections(self) -> None:
        while len(self._observations) > MAX_CONNECTIONS:
            expired = next(iter(self._observations))
            self.release(expired)

    def metrics(self) -> dict[str, int]:
        with self._lock:
            return {
                "known_profiles": len(self._profiles),
                "active_bindings": len(self._bindings),
                "pending_connections": max(
                    0, len(self._observations) - len(self._bindings)
                ),
                "direct_confirmations": self.direct_confirmations,
                "invalid_direct_events": self.invalid_direct_events,
                "conflicting_direct_uids": self.conflicting_direct_uids,
                "recovered_confirmations": self.recovered_confirmations,
                "ambiguous_matches": self.ambiguous_matches,
                "remote_profiles": self.remote_profiles,
            }

    def close(self) -> None:
        with self._lock:
            self._save()
