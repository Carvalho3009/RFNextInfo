"""Recortes de Farm comandados pelo site e calculados só com eventos sanitizados."""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


STATE_SCHEMA = "rf-qol.remote-subsessions-state/v1"
MAX_HANDLED_COMMANDS = 256


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _iso_ns(value: object) -> int | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1_000_000_000)
    except (TypeError, ValueError, OverflowError):
        return None


class RemoteSubsessionController:
    """Mantém limites de medição passivos sem armazenar pacotes ou segredos."""

    def __init__(
        self,
        state_path: Path,
        clients_provider: Callable[[], list[dict[str, Any]]],
    ) -> None:
        self.state_path = Path(state_path)
        self.clients_provider = clients_provider
        self._submitter: Callable[[str, dict[str, Any]], bool] | None = None
        self._lock = threading.RLock()
        self._active: dict[str, dict[str, Any]] = {}
        self._handled: dict[str, dict[str, Any]] = {}
        self._pending_results: list[dict[str, Any]] = []
        self._latest_contribution: dict[str, int] = {}
        self._last_save_monotonic = 0.0
        self._load()

    def set_submitter(
        self, submitter: Callable[[str, dict[str, Any]], bool]
    ) -> None:
        self._submitter = submitter

    def _load(self) -> None:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(value, dict) or value.get("schema") != STATE_SCHEMA:
            return
        active = value.get("active")
        handled = value.get("handled")
        pending = value.get("pending_results")
        if isinstance(active, dict):
            self._active = {
                str(key): dict(item)
                for key, item in active.items()
                if isinstance(item, dict)
            }
        if isinstance(handled, dict):
            self._handled = {
                str(key): dict(item)
                for key, item in list(handled.items())[-MAX_HANDLED_COMMANDS:]
                if isinstance(item, dict)
            }
        if isinstance(pending, list):
            self._pending_results = [
                dict(item) for item in pending[-MAX_HANDLED_COMMANDS:]
                if isinstance(item, dict)
            ]

    def _save(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_save_monotonic < 2.0:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "schema": STATE_SCHEMA,
            "active": self._active,
            "handled": self._handled,
            "pending_results": self._pending_results,
        }
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, self.state_path)
        self._last_save_monotonic = now

    def pending_results(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(item) for item in self._pending_results]

    def progress_updates(self) -> list[dict[str, Any]]:
        """Retorna uma fotografia sanitizada dos recortes ainda ativos."""
        now_ns = time.time_ns()
        with self._lock:
            return [{
                "subsession_ref": str(item["control_ref"]),
                "occurred_at": _utc_now(),
                "duration_seconds": max(
                    0, (now_ns - int(item["started_ns"])) // 1_000_000_000
                ),
                "level": item.get("level"),
                "gained_exp": int(item["gained_exp"]),
                "gained_exp_percent": float(item["gained_exp_percent"]),
                "gained_contribution": int(item["gained_contribution"]),
                "gained_credits": int(item["gained_credits"]),
                "kill_count": int(item["kill_count"]),
            } for item in self._active.values()]

    def acknowledge_results(self, results: list[dict[str, Any]]) -> None:
        command_ids = {
            str(item.get("command_id")) for item in results
            if isinstance(item, dict)
        }
        if not command_ids:
            return
        with self._lock:
            self._pending_results = [
                item for item in self._pending_results
                if str(item.get("command_id")) not in command_ids
            ]
            self._save(force=True)

    def _result(self, command_id: str, status: str, error: str | None = None) -> dict[str, Any]:
        return {
            "command_id": command_id,
            "status": status,
            "occurred_at": _utc_now(),
            "error_code": error,
        }

    def _remember_result(self, result: dict[str, Any]) -> None:
        command_id = str(result["command_id"])
        self._handled.pop(command_id, None)
        self._handled[command_id] = dict(result)
        while len(self._handled) > MAX_HANDLED_COMMANDS:
            self._handled.pop(next(iter(self._handled)))
        if not any(
            item.get("command_id") == command_id for item in self._pending_results
        ):
            self._pending_results.append(dict(result))
        self._pending_results = self._pending_results[-MAX_HANDLED_COMMANDS:]

    @staticmethod
    def _metadata(command: dict[str, Any]) -> dict[str, Any]:
        mobs: list[str] = []
        for raw in command.get("mobs") if isinstance(command.get("mobs"), list) else []:
            mob = str(raw).strip()[:96]
            if mob and mob not in mobs:
                mobs.append(mob)
        return {
            "name": str(command.get("name") or "Subsessão").strip()[:120],
            "map_name": str(command.get("map_name") or "").strip()[:120],
            "spot_name": str(command.get("spot_name") or "").strip()[:120],
            "mobs": mobs[:32],
        }

    def _client_for_uid(self, character_uid: int) -> dict[str, Any] | None:
        for item in self.clients_provider():
            try:
                if int(item.get("character_uid")) == character_uid:
                    return dict(item)
            except (TypeError, ValueError, OverflowError):
                continue
        return None

    def apply_commands(
        self, commands: list[dict[str, Any]], *, session_id: str | None,
        capture_active: bool,
    ) -> list[dict[str, Any]]:
        applied: list[dict[str, Any]] = []
        with self._lock:
            for command in commands:
                command_id = str(command.get("command_id") or "")
                reference = str(command.get("subsession_ref") or "")
                action = str(command.get("action") or "")
                previous = self._handled.get(command_id)
                if previous is not None:
                    self._remember_result(previous)
                    applied.append(dict(previous))
                    continue
                if action == "start":
                    result = self._start(
                        command, reference, session_id, capture_active
                    )
                elif action == "update":
                    active = self._active.get(reference)
                    if active is None:
                        result = self._result(
                            command_id, "failed", "subsession_not_active"
                        )
                    else:
                        active.update(self._metadata(command))
                        result = self._result(command_id, "applied")
                elif action == "stop":
                    result = self._stop(reference, command_id)
                else:
                    result = self._result(command_id, "failed", "invalid_action")
                self._remember_result(result)
                applied.append(dict(result))
            self._save(force=True)
        return applied

    def _start(
        self, command: dict[str, Any], reference: str, session_id: str | None,
        capture_active: bool,
    ) -> dict[str, Any]:
        command_id = str(command["command_id"])
        if not capture_active or not session_id:
            return self._result(command_id, "failed", "capture_not_active")
        character_uid = int(command["character_uid"])
        client = self._client_for_uid(character_uid)
        if client is None or not client.get("client_ref"):
            return self._result(command_id, "failed", "character_not_observed")
        if any(
            int(item.get("character_uid") or 0) == character_uid
            for item in self._active.values()
        ):
            return self._result(command_id, "failed", "character_already_active")
        client_ref = str(client["client_ref"])
        contribution = self._latest_contribution.get(client_ref)
        self._active[reference] = {
            "control_ref": reference,
            "session_id": str(session_id),
            "character_uid": character_uid,
            "client_ref": client_ref,
            "level": client.get("level"),
            "started_ns": time.time_ns(),
            "gained_exp": 0,
            "gained_exp_percent": 0.0,
            "gained_credits": 0,
            "gained_contribution": 0,
            "contribution_last": contribution,
            "kill_count": 0,
            **self._metadata(command),
        }
        return self._result(command_id, "applied")

    def _report(self, item: dict[str, Any], ended_ns: int) -> dict[str, Any]:
        started_ns = int(item["started_ns"])
        return {
            "source_subsession_id": item["control_ref"],
            "control_ref": item["control_ref"],
            "character_uid": int(item["character_uid"]),
            "name": item["name"],
            "started_ns": started_ns,
            "ended_ns": max(started_ns, ended_ns),
            "duration_seconds": max(1, (ended_ns - started_ns) // 1_000_000_000),
            "map_name": item["map_name"],
            "spot_name": item["spot_name"],
            "mobs": list(item["mobs"]),
            "exp_total": int(item["gained_exp"]),
            "exp_total_percent": float(item["gained_exp_percent"]),
            "kill_count": int(item["kill_count"]),
            "summary": {
                "level": item.get("level"),
                "credits": int(item["gained_credits"]),
                "contribution": int(item["gained_contribution"]),
            },
        }

    def _stop(self, reference: str, command_id: str) -> dict[str, Any]:
        item = self._active.get(reference)
        if item is None:
            return self._result(command_id, "failed", "subsession_not_active")
        if self._submitter is None:
            return self._result(command_id, "failed", "reporter_unavailable")
        try:
            self._submitter(
                str(item["session_id"]), self._report(item, time.time_ns())
            )
        except Exception:
            return self._result(command_id, "failed", "report_queue_failed")
        self._active.pop(reference, None)
        return self._result(command_id, "applied")

    def finish_all(self, session_id: str | None) -> int:
        if self._submitter is None:
            return 0
        ended_ns = time.time_ns()
        completed = 0
        with self._lock:
            for reference, item in list(self._active.items()):
                if session_id and str(item.get("session_id")) != str(session_id):
                    continue
                try:
                    self._submitter(
                        str(item["session_id"]), self._report(item, ended_ns)
                    )
                except Exception:
                    continue
                self._active.pop(reference, None)
                completed += 1
            self._save(force=True)
        return completed

    def observe(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("type") or "")
        payload = event.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        client_ref = str(event.get("client_ref") or "")
        if event_type == "character.contribution_changed" and client_ref:
            total = payload.get("contribution_total")
            if type(total) is int and total >= 0:
                self._latest_contribution[client_ref] = total
        occurred_ns = _iso_ns(event.get("occurred_at"))
        with self._lock:
            changed = False
            for item in self._active.values():
                if client_ref != item.get("client_ref"):
                    continue
                if occurred_ns is not None and occurred_ns < int(item["started_ns"]):
                    continue
                if event_type == "character.observed":
                    if payload.get("level") is not None:
                        item["level"] = int(payload["level"])
                        changed = True
                elif event_type == "character.exp_changed":
                    gained = payload.get("gained_exp")
                    percent = payload.get("gained_exp_percent")
                    if type(gained) is int and gained > 0:
                        item["gained_exp"] += gained
                        changed = True
                    if type(percent) in {int, float} and float(percent) > 0:
                        item["gained_exp_percent"] += float(percent)
                        changed = True
                    if payload.get("level") is not None:
                        item["level"] = int(payload["level"])
                elif event_type == "character.drop_received":
                    credits = payload.get("credits_gained")
                    if type(credits) is int and credits > 0:
                        item["gained_credits"] += credits
                        changed = True
                elif event_type == "character.contribution_changed":
                    total = payload.get("contribution_total")
                    if type(total) is int and total >= 0:
                        previous = item.get("contribution_last")
                        if type(previous) is int and total > previous:
                            item["gained_contribution"] += total - previous
                        item["contribution_last"] = total
                        changed = True
                elif (
                    event_type == "combat.entity_died"
                    and payload.get("combat_domain") == "pve"
                    and payload.get("killer_is_client") is True
                ):
                    item["kill_count"] += 1
                    changed = True
            if changed:
                self._save()

    def health(self) -> dict[str, int]:
        with self._lock:
            return {
                "active": len(self._active),
                "pending_results": len(self._pending_results),
            }
