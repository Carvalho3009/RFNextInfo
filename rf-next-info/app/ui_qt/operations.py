from __future__ import annotations

import re
import ctypes
import hashlib
import json
import logging
import os
import threading
import time
from ctypes import wintypes
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.main import (
    DEFAULT_PORTS,
    ITEM_NAMES,
    ITEM_NAMES_EN,
    VERSION,
    _capture_summary,
    _collection_marks,
    _market_rows,
    _merge_client_routes,
)
from core.capture import PktmonCapture
from core.connections import clients_for_executable, connected_processes
from core.pktmon_realtime import RealtimeCapture
from core.live_stream import LiveEventStream
from core.knowledge import KnowledgeStore
from core.store import CaptureStore


LOG = logging.getLogger("rfnextinfo")
LOG.addHandler(logging.NullHandler())

DEFAULT_GLOBAL_SHORTCUTS = {
    "character": "F1",
    "market": "F2",
    "codex": "F3",
    "memory_chips": "F4",
    "monitor_pve": "Ctrl+F5",
    "monitor_pvp": "Ctrl+F6",
    "monitor_boss": "Ctrl+F7",
}


def _site_loot_rows(raw: object) -> list[dict[str, object]]:
    """Normaliza o loot para o contrato numérico aceito pelo site."""
    result: list[dict[str, object]] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            item_index = int(item.get("itemIndex") or item.get("item_index") or 0)
            quantity = int(item.get("quantity") or item.get("count") or 0)
            rarity = int(item.get("grade") or 0)
        except (TypeError, ValueError):
            continue
        if item_index <= 0 or quantity <= 0 or rarity not in range(7):
            continue
        result.append(
            {
                "itemIndex": item_index,
                "name": str(item.get("name") or item.get("item") or f"Item {item_index}"),
                "quantity": quantity,
                "rarity": rarity,
            }
        )
    return result


class SiteUploadEngine:
    def __init__(self, database_path: Path, site_profile, license_client) -> None:
        self.database_path = Path(database_path)
        self.site_profile = site_profile
        self.license = license_client

    def _metadata(self, mode: str, character: str = "") -> dict[str, object]:
        return {
            "profile": self.site_profile.profile,
            "character_name": character,
            "installation_id": self.license.installation_id,
            "license_lease": self.license.lease,
            "app_version": VERSION,
            "capture_mode": mode,
            "captured_at": datetime.now().astimezone().isoformat(),
        }

    @staticmethod
    def _selected_character(snapshot: dict, client_index: int) -> dict:
        characters = [item for item in snapshot.get("characters", []) if item.get("uid")]
        key = f"client:{chr(97 + client_index)}"
        selected = next((item for item in characters if item.get("client_key") == key), None)
        if selected is None and len(characters) == 1:
            selected = characters[0]
        if selected is None:
            raise ValueError("O cliente selecionado ainda não possui personagem identificado")
        return selected

    def send_mode(
        self, mode: str, client_index: int, snapshot: dict, language: str
    ) -> dict[str, object]:
        if not self.site_profile.connected:
            raise ValueError("Valide o token do Profile antes de enviar")
        session_id = str(snapshot.get("session_id") or "")
        if not session_id:
            raise ValueError("Ainda não existe uma sessão para enviar")
        store = CaptureStore(self.database_path, readonly=True)
        try:
            metadata = self._metadata(mode)
            uid = ""
            if mode == "market":
                rows = _market_rows(
                    store.session_envelope(session_id, None, include_unassigned=True),
                    ITEM_NAMES_EN if language == "en" else ITEM_NAMES,
                )
                if not rows:
                    raise ValueError("Ainda não existem eventos de Mercado para enviar")
                payload = {"metadata": metadata, "rows": rows}
                target = "Mercado geral"
            else:
                selected = self._selected_character(snapshot, client_index)
                uid, character = str(selected["uid"]), str(selected["name"])
                envelope = store.session_envelope(
                    session_id,
                    uid,
                    bool(selected.get("include_unassigned")),
                    bool(selected.get("only_unassigned")),
                )
                summary, _marks = _capture_summary(
                    envelope,
                    uid,
                    character,
                    ITEM_NAMES_EN if language == "en" else ITEM_NAMES,
                )
                site_summary = {
                    **summary,
                    "loot": _site_loot_rows(summary.get("loot")),
                }
                metadata.update(character_name=character, marks_mode="merge")
                profile = {
                    "profile": self.site_profile.profile,
                    "name": character,
                    "character_uid": uid,
                }
                if mode == "character":
                    profile.update(
                        className=summary["character_class"],
                        loadout=summary["loadout"],
                    )
                else:
                    requested = {1} if mode == "codex" else {2}
                    marks, seen = _collection_marks(envelope, requested)
                    if not marks:
                        raise ValueError("Ainda não existem dados deste tipo para enviar")
                    profile.update(
                        marks=marks,
                        collection_types=sorted(requested.intersection(seen)),
                    )
                payload = {
                    "metadata": metadata,
                    "profiles": [profile],
                    "capture": site_summary if mode == "character" else {},
                    "loadout": summary["loadout"] if mode == "character" else {},
                    "subsession_reports": [],
                }
                target = f"Cliente {chr(65 + client_index)}"
        finally:
            store.close()
        stable = {**payload, "metadata": {k: v for k, v in metadata.items() if k != "captured_at"}}
        key = hashlib.sha256(json.dumps(
            {"session_id": session_id, "mode": mode, "payload": stable},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()).hexdigest()
        response = self.site_profile.upload_live(mode, payload, key)
        return {"target": target, "receipt": response.get("receipt", ""), "uid": uid}

    def send_subsessions(
        self, identifiers: list[str], snapshot: dict, language: str
    ) -> dict[str, object]:
        if not self.site_profile.connected:
            raise ValueError("Valide o token do Profile antes de enviar")
        session_id = str(snapshot.get("session_id") or "")
        if not session_id or not identifiers:
            raise ValueError("Selecione ao menos uma subsessão encerrada")
        store = CaptureStore(self.database_path)
        sent, failures = 0, []
        try:
            selected = {
                item["id"]: item
                for item in store.subsessions(session_id)
                if item["id"] in identifiers
            }
            if len(selected) != len(set(identifiers)):
                raise ValueError("Uma subsessão selecionada não foi encontrada")
            if any(not item.get("ended_ns") for item in selected.values()):
                raise ValueError("Encerre as subsessões selecionadas antes de enviar")
            characters = {
                item.get("client_key"): item
                for item in snapshot.get("characters", [])
                if item.get("uid") and item.get("client_key")
            }
            names = {
                str(item.get("uid")): str(item.get("name") or "")
                for item in snapshot.get("characters", [])
                if item.get("uid")
            }
            stored_names = {
                str(item.get("uid")): str(item.get("name") or "")
                for item in store.session_profiles(session_id)
                if item.get("uid")
            }
            for item in selected.values():
                character = characters.get(item.get("client_key"), {})
                uid = str(character.get("uid") or item.get("character_uid") or "")
                name = str(
                    character.get("name")
                    or names.get(uid)
                    or stored_names.get(uid)
                    or ""
                )
                if not uid or not name:
                    store.set_subsession_upload_state(item["id"], "failed")
                    LOG.error(
                        "subsession_upload_rejected sequence=%s client=%s "
                        "reason=character_not_identified",
                        item.get("sequence"), item.get("client_key"),
                    )
                    failures.append(f"{item['name']}: personagem não identificado")
                    continue
                ended_ns = int(item["ended_ns"])
                summary, _marks = _capture_summary(
                    store.interval_envelope(
                        session_id, uid, int(item["started_ns"]), ended_ns
                    ),
                    uid,
                    name,
                    ITEM_NAMES_EN if language == "en" else ITEM_NAMES,
                )
                site_summary = {
                    **summary,
                    "loot": _site_loot_rows(summary.get("loot")),
                }
                seconds = max(1, int((ended_ns - int(item["started_ns"])) / 1_000_000_000))
                hours = seconds / 3600
                gained_percent = summary.get("exp_gained_percent")
                report = {
                    **item,
                    "character_uid": uid,
                    "source_subsession_id": f"{self.license.installation_id}:{item['sequence']}",
                    "duration_seconds": seconds,
                    "mob_kills_estimated": int(summary.get("kills") or 0),
                    "exp_total": summary.get("exp_gained") or 0,
                    "exp_total_percent": gained_percent,
                    "exp_hour": round(float(summary.get("exp_gained") or 0) / hours),
                    "exp_hour_percent": (
                        float(gained_percent) / hours
                        if isinstance(gained_percent, (int, float))
                        else None
                    ),
                    "summary": site_summary,
                }
                metadata = self._metadata("subsession", name)
                metadata.update(
                    captured_at=datetime.fromtimestamp(
                        ended_ns / 1_000_000_000
                    ).astimezone().isoformat(),
                    marks_mode="merge",
                )
                payload = {
                    "metadata": metadata,
                    "profiles": [{
                        "profile": self.site_profile.profile,
                        "name": name,
                        "character_uid": uid,
                        "marks": {},
                    }],
                    "capture": site_summary,
                    "subsession_reports": [report],
                }
                key = hashlib.sha256(
                    f"{self.site_profile.profile}\0{self.license.installation_id}\0subsession\0{item['sequence']}".encode()
                ).hexdigest()
                try:
                    self.site_profile.upload_live("subsession", payload, key)
                    store.set_subsession_upload_state(item["id"], "sent")
                    sent += 1
                except Exception as error:
                    store.set_subsession_upload_state(item["id"], "failed")
                    LOG.exception(
                        "subsession_upload_failed sequence=%s client=%s",
                        item.get("sequence"), item.get("client_key"),
                    )
                    failures.append(f"{item['name']}: {error}")
        finally:
            store.close()
        return {"sent": sent, "failures": failures}

    def send_observations(
        self, session_id: str, knowledge_path: Path
    ) -> dict[str, object]:
        if not self.site_profile.connected:
            return {"skipped": True, "reason": "profile_not_connected"}
        capture = CaptureStore(self.database_path, readonly=True)
        knowledge = KnowledgeStore(knowledge_path)
        try:
            envelope = capture.session_envelope(
                session_id, None, include_unassigned=True
            )
            knowledge.observe_events(envelope.get("events") or [])
            payload = knowledge.pending_payload()
            if not payload["characters"] and not payload["mobs"]:
                return {"skipped": True, "reason": "no_pending_observations"}
            payload["metadata"] = {
                **self._metadata("observations"),
                "session_id": session_id,
                "privacy": "decoded-fields-only; no raw payload or opcode 0x0101",
            }
            stable = {
                "profile": self.site_profile.profile,
                "session_id": session_id,
                "characters": payload["characters"],
                "mobs": payload["mobs"],
            }
            key = hashlib.sha256(json.dumps(
                stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest()
            response = self.site_profile.upload_observations(payload, key)
            knowledge.mark_uploaded(payload)
            return response
        finally:
            knowledge.close()
            capture.close()


class ExportEngine:
    """Exporta o mesmo envelope da versão estável sem depender de Tk ou Qt."""

    def __init__(self, database_path: Path, license_client) -> None:
        self.database_path = Path(database_path)
        self.license = license_client

    @staticmethod
    def _targets(store: CaptureStore, session_id: str) -> list[dict[str, object]]:
        detected = store.session_profiles(session_id)
        stats = store.session_stats(session_id)
        if len(detected) > 2 or not detected:
            return [{
                "uid": None,
                "name": "Nao-identificado",
                "include_unassigned": True,
                "only_unassigned": False,
                "identification_status": "unresolved",
                "warning": "A captura não separou todos os personagens.",
            }]
        targets: list[dict[str, object]] = []
        for index, item in enumerate(detected):
            uid = str(item.get("uid") or "")
            targets.append({
                "uid": uid,
                "name": str(item.get("name") or f"Personagem-{index + 1}"),
                "include_unassigned": len(detected) == 1,
                "only_unassigned": False,
                "identification_status": (
                    "exp_matched" if uid.startswith("exp:") else
                    "client_routed" if uid.startswith("client:") else
                    "confirmed_uid"
                ),
                "warning": (
                    "Alguns eventos não têm identificação individual."
                    if len(detected) == 1 and int(stats["unassigned"] or 0)
                    else None
                ),
            })
        if len(detected) > 1 and int(stats["unassigned"] or 0):
            targets.append({
                "uid": None,
                "name": "Nao-atribuido",
                "include_unassigned": False,
                "only_unassigned": True,
                "identification_status": "unresolved",
                "warning": "Existem eventos sem personagem associado.",
            })
        return targets

    def _subsession_report(
        self,
        store: CaptureStore,
        session_id: str,
        subsession: dict,
        character_uid: str | None,
        item_names: dict[str, str],
    ) -> dict:
        ended_ns = int(subsession.get("ended_ns") or time.time_ns())
        started_ns = int(subsession["started_ns"])
        envelope = store.interval_envelope(
            session_id, character_uid, started_ns, ended_ns
        )
        summary, _ = _capture_summary(
            envelope, character_uid, item_names=item_names
        )
        seconds = max(1, int((ended_ns - started_ns) / 1_000_000_000))
        hours = seconds / 3600
        exp_percent = summary.get("exp_gained_percent")
        return {
            **subsession,
            "character_uid": character_uid,
            "source_subsession_id": (
                f"{self.license.installation_id}:{subsession['sequence']}"
            ),
            "ended_ns": ended_ns,
            "duration_seconds": seconds,
            "mob_kills_estimated": int(summary.get("kills") or 0),
            "exp_total": summary.get("exp_gained") or 0,
            "exp_total_percent": exp_percent,
            "exp_hour": round(float(summary.get("exp_gained") or 0) / hours),
            "exp_hour_percent": (
                float(exp_percent) / hours
                if isinstance(exp_percent, (int, float)) else None
            ),
            "summary": summary,
        }

    def export(
        self,
        session_id: str,
        target: Path,
        profile: str,
        language: str = "pt",
    ) -> dict[str, object]:
        if not session_id:
            raise ValueError("Nenhuma sessão capturada está disponível")
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        item_names = ITEM_NAMES_EN if language == "en" else ITEM_NAMES
        match = re.search(r"-(\d{8}-\d{6})-(\d+)$", session_id)
        stamp = match.group(1) if match else datetime.now().strftime("%Y%m%d-%H%M%S")
        counter = int(match.group(2)) if match else 0
        store = CaptureStore(self.database_path)
        try:
            results = []
            warnings: set[str] = set()
            for character in self._targets(store, session_id):
                if character.get("warning"):
                    warnings.add(str(character["warning"]))
                uid = character.get("uid")
                name = str(character["name"])
                capture_id = (
                    f"{_safe_name(profile, 'Profile')}-"
                    f"{_safe_name(name, 'Personagem')}-{stamp}-{counter:03d}"
                )
                envelope = store.session_envelope(
                    session_id,
                    uid,
                    bool(character["include_unassigned"]),
                    bool(character["only_unassigned"]),
                )
                summary, marks = _capture_summary(
                    envelope, str(uid or ""), name, item_names=item_names
                )
                _all_marks, collection_types = _collection_marks(envelope)
                reports = [
                    self._subsession_report(
                        store, session_id, subsession, uid, item_names
                    )
                    for subsession in store.subsessions(session_id)
                    if subsession.get("character_uid") in (None, uid)
                ]
                result = store.export(
                    target,
                    capture_id,
                    session_id=session_id,
                    character_uid=uid,
                    include_unassigned=bool(character["include_unassigned"]),
                    only_unassigned=bool(character["only_unassigned"]),
                    context={
                        "profile": profile,
                        "character_name": name,
                        "installation_id": self.license.installation_id,
                        "license_lease": self.license.lease,
                        "app_version": VERSION,
                        "session_counter": counter,
                        "identification_status": character["identification_status"],
                        "requires_site_review": bool(character.get("warning")),
                        "requested_characters": [],
                        "codex_marks": marks,
                        "subsession_reports": reports,
                    },
                )
                exported = json.loads(result.json_path.read_text(encoding="utf-8"))
                exported["capture"] = summary
                exported["profiles"] = [{
                    "profile": profile,
                    "name": name,
                    "character_uid": uid,
                    "className": summary.get("character_class"),
                    "loadout": summary.get("loadout") or {},
                    "marks": marks,
                    "collection_types": collection_types,
                }]
                temporary = result.json_path.with_suffix(".json.tmp")
                temporary.write_text(
                    json.dumps(exported, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                json.loads(temporary.read_text(encoding="utf-8"))
                os.replace(temporary, result.json_path)
                json_bytes = result.json_path.stat().st_size
                result = replace(
                    result,
                    json_bytes=json_bytes,
                    sha256=hashlib.sha256(result.json_path.read_bytes()).hexdigest(),
                )
                results.append(result)
            diagnostic = store.export_diagnostics(
                target,
                f"{_safe_name(profile, 'Profile')}-diagnostico-{stamp}-{counter:03d}",
                session_id,
            )
            raw_files = list(dict.fromkeys(store.session_sources(session_id)))
            total = sum(
                result.json_path.stat().st_size + result.csv_path.stat().st_size
                for result in results
            ) + (diagnostic.stat().st_size if diagnostic else 0)
            raw_bytes = sum(
                path.stat().st_size for path in raw_files if path.exists()
            )
            return {
                "results": results,
                "diagnostic": diagnostic,
                "warnings": sorted(warnings),
                "total_bytes": total,
                "raw_bytes": raw_bytes,
                "raw_files": raw_files,
                "session_id": session_id,
            }
        finally:
            store.close()


class GlobalHotkeys:
    def __init__(self, callback: Callable[[str], None]) -> None:
        self.callback = callback
        self.thread: threading.Thread | None = None
        self.thread_id = 0
        self.shortcuts: dict[str, str] = {}

    def start(self, shortcuts: dict[str, str] | None = None) -> None:
        if os.name != "nt" or (self.thread and self.thread.is_alive()):
            return
        self.shortcuts = dict(DEFAULT_GLOBAL_SHORTCUTS)
        self.shortcuts.update(shortcuts or {})
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    @staticmethod
    def parse_shortcut(shortcut: str) -> tuple[int, int] | None:
        parts = str(shortcut).upper().split("+")
        match = re.fullmatch(r"F([1-9]|1[0-2])", parts[-1])
        modifier_codes = {
            "ALT": 0x0001,
            "CTRL": 0x0002,
            "SHIFT": 0x0004,
            "WIN": 0x0008,
        }
        modifiers = 0x4000
        seen: set[str] = set()
        if not match:
            return None
        for modifier in parts[:-1]:
            if modifier not in modifier_codes or modifier in seen:
                return None
            seen.add(modifier)
            modifiers |= modifier_codes[modifier]
        return 0x6F + int(match.group(1)), modifiers

    @staticmethod
    def definitions(shortcuts: dict[str, str]) -> list[tuple[int, str, int, int]]:
        configured = dict(DEFAULT_GLOBAL_SHORTCUTS)
        configured.update(shortcuts)
        definitions = [
            (0x525101, "start", 0x77, 0x0002 | 0x4000),
            (0x525102, "stop", 0x78, 0x0002 | 0x4000),
            (0x525106, "overlay_pvp", 0x75, 0x0002 | 0x0004 | 0x4000),
            (0x525107, "overlay_boss", 0x76, 0x0002 | 0x0004 | 0x4000),
        ]
        for offset, (action, shortcut) in enumerate(configured.items(), 10):
            parsed = GlobalHotkeys.parse_shortcut(shortcut)
            if parsed:
                key, modifiers = parsed
                definitions.append(
                    (0x525100 + offset, action, key, modifiers)
                )
        return definitions

    def _worker(self) -> None:
        user32 = ctypes.windll.user32
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        self.thread_id = int(ctypes.windll.kernel32.GetCurrentThreadId())
        registered = {
            identifier: action
            for identifier, action, key, modifiers in self.definitions(self.shortcuts)
            if user32.RegisterHotKey(None, identifier, modifiers, key)
        }
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == 0x0312:
                    action = registered.get(int(message.wParam))
                    if action:
                        self.callback(action)
        finally:
            for identifier in registered:
                user32.UnregisterHotKey(None, identifier)

    def stop(self) -> None:
        if os.name == "nt" and self.thread and self.thread.is_alive():
            ctypes.windll.user32.PostThreadMessageW(
                self.thread_id, 0x0012, 0, 0
            )
            self.thread.join(timeout=1)
        self.thread = None
        self.thread_id = 0


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", value).strip("-")
    return cleaned or fallback


class MonitorEngine:
    """Stream Pktmon somente em memória, independente da captura histórica."""

    def __init__(
        self,
        *,
        live_factory: Callable[[Path | None, tuple[int, ...]], RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
        client_reader: Callable[..., list] = clients_for_executable,
    ) -> None:
        self.live_factory = live_factory
        self.process_reader = process_reader
        self.client_reader = client_reader
        self.live_capture: RealtimeCapture | None = None
        self.events = LiveEventStream()
        self.executable = ""
        self.client_ports: tuple[tuple[int, ...], ...] = ()
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self.live_capture is not None

    def start(self) -> dict[str, object]:
        with self._lock:
            if self.active:
                return self.snapshot()
            processes = self.process_reader(DEFAULT_PORTS)
            if not processes:
                raise RuntimeError("Abra um cliente ProjectRF e entre no jogo")
            executable, (pids, local_ports, remote_ports) = max(
                processes.items(), key=lambda item: len(item[1][0])
            )
            if len(pids) > 2:
                raise RuntimeError("Foram encontrados mais de dois clientes ProjectRF")
            routes = self.client_reader(executable, DEFAULT_PORTS)
            _pids, groups = _merge_client_routes([], [], routes)
            self.executable = executable
            self.client_ports = tuple(group for group in groups if group) or (
                tuple(sorted(local_ports)),
            )
            ports = tuple(
                dict.fromkeys((*DEFAULT_PORTS, *local_ports, *remote_ports))
            )
            self.events.clear()
            self.events.start()
            live = self.live_factory(None, ports)
            if hasattr(live, "set_packet_sink"):
                live.set_packet_sink(self.events.feed)
            try:
                live.start()
            except Exception:
                self.events.stop()
                raise
            self.live_capture = live
            return {
                "available": True,
                "active": True,
                "clients": len(pids),
                "client_ports": [list(group) for group in self.client_ports],
                "events": [],
            }

    def _refresh_routes(self) -> None:
        if not self.executable or not self.live_capture:
            return
        routes = self.client_reader(self.executable, DEFAULT_PORTS)
        _pids, groups = _merge_client_routes([], list(self.client_ports), routes)
        active_groups = tuple(group for group in groups if group)
        if active_groups:
            self.client_ports = active_groups
        ports = tuple(
            dict.fromkeys(
                port
                for route in routes
                for field in ("local_ports", "remote_ports")
                for port in route.get(field, ())
            )
        )
        if ports:
            self.live_capture.add_ports(ports)

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            if not self.live_capture:
                return {"available": False, "active": False, "events": []}
            self._refresh_routes()
            events = self.events.snapshot()
            return {
                "available": True,
                "active": True,
                "added": len(events),
                "events": events,
                "client_ports": [list(group) for group in self.client_ports],
            }

    def stop(self) -> None:
        with self._lock:
            live, self.live_capture = self.live_capture, None
            try:
                if live:
                    live.stop()
            finally:
                self.events.stop()


class CaptureEngine:
    """Ciclo de captura sem dependência da interface Tk ou Qt."""

    def __init__(
        self,
        capture_directory: Path,
        database_path: Path,
        *,
        profile: str = "Profile",
        session_counter: int = 0,
        capture_factory: Callable[[Path], PktmonCapture] = PktmonCapture,
        live_factory: Callable[[Path, tuple[int, ...]], RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
        client_reader: Callable[..., list] = clients_for_executable,
    ) -> None:
        self.capture_directory = Path(capture_directory)
        self.database_path = Path(database_path)
        self.profile = profile.strip() or "Profile"
        self.session_counter = int(session_counter)
        self.capture_factory = capture_factory
        self.live_factory = live_factory
        self.process_reader = process_reader
        self.client_reader = client_reader
        self.capture: PktmonCapture | None = None
        self.live_capture: RealtimeCapture | None = None
        self.current_session: str | None = None
        self.executable = ""
        self.client_pids: list[int] = []
        self.client_ports: tuple[tuple[int, ...], ...] = ()
        self.live_files: list[Path] = []
        self.pending_files: list[Path] = []
        self.capture_ports: tuple[int, ...] = ()
        self.live_index = 0
        self.capture_index = 0
        self.paused = False
        self.route_identity_trusted = True
        self.live_events = LiveEventStream()
        self._lock = threading.RLock()

    def restore(self, preferences: dict[str, object]) -> dict[str, object] | None:
        """Recupera uma captura pendente sem iniciar uma sessão nova."""
        if self.current_session or not preferences.get("capture_pending"):
            return None
        session_id = str(preferences.get("last_session") or "").strip()
        prefix = str(preferences.get("capture_prefix") or "").strip()
        if not session_id or not prefix:
            return None
        capture = self.capture_factory(self.capture_directory)
        files = tuple(self.capture_directory.glob(f"{prefix}*.etl"))
        if not files:
            return None
        ports = tuple(int(value) for value in preferences.get("capture_ports") or ())
        self.capture_ports = ports
        match = re.search(r"-(\d+)$", prefix)
        self.capture_index = int(match.group(1)) if match else 0
        status = capture.attach(prefix, ports)
        self.capture = capture
        self.current_session = session_id
        self.paused = not status.active
        self.pending_files = list(status.files)
        # Portas são transitórias; somente os PIDs preservam os slots A/B.
        self.client_ports = ()
        self.client_pids = [
            int(pid) for pid in preferences.get("capture_client_pids") or ()
        ][:2]
        self.route_identity_trusted = bool(self.client_pids)
        return {
            "session_id": session_id,
            "files": len(status.files),
            "active": status.active,
        }

    @property
    def active(self) -> bool:
        return self.live_capture is not None or bool(
            self.capture and self.capture.active
        )

    def _next_live_target(self) -> Path:
        self.live_index += 1
        directory = self.capture_directory / ".rfnext-preview"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{_safe_name(self.current_session or 'sessao', 'sessao')}-live-{self.live_index:04d}.pcap"

    def _next_capture_prefix(self) -> str:
        self.capture_index += 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        return (
            f"rfnext-{stamp}-{self.session_counter:03d}"
            f"-{self.capture_index:02d}"
        )

    def start(self) -> dict[str, object]:
        with self._lock:
            if self.active:
                raise RuntimeError("A captura já está ativa")
            resuming = self.paused and bool(self.current_session)
            processes = self.process_reader(DEFAULT_PORTS)
            if not processes:
                raise RuntimeError("Abra um cliente ProjectRF e entre no jogo")
            executable, (pids, local_ports, remote_ports) = max(
                processes.items(), key=lambda item: len(item[1][0])
            )
            if len(pids) > 2:
                raise RuntimeError("Foram encontrados mais de dois clientes ProjectRF")
            routes = self.client_reader(executable, DEFAULT_PORTS)
            self.executable = executable
            known_pids = list(self.client_pids)
            self.route_identity_trusted = bool(
                not resuming
                or known_pids and set(known_pids).intersection(pids)
            )
            if self.route_identity_trusted:
                self.client_pids, groups = _merge_client_routes(
                    known_pids if resuming else [],
                    [],
                    routes,
                )
                self.client_ports = tuple(groups) or (tuple(sorted(local_ports)),)
            else:
                self.client_pids = []
                self.client_ports = ()
            if not resuming:
                self.session_counter += 1
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                self.current_session = (
                    f"{_safe_name(self.profile, 'Profile')}-{stamp}-{self.session_counter:03d}"
                )
                self.live_index = 0
                self.capture_index = 0
                self.pending_files.clear()
            prefix = self._next_capture_prefix()
            ports = tuple(dict.fromkeys((*local_ports, *remote_ports)))
            self.capture_ports = ports
            capture = self.capture_factory(self.capture_directory)
            if capture.system_running():
                raise RuntimeError(
                    "Outra captura PktMon está ativa; encerre a versão estável ou aguarde o heartbeat"
                )
            capture.start_for_ports(prefix, ports)
            self.capture = capture
            self.live_capture = None
            live_error = None
            try:
                self.live_events.clear()
                self.live_events.start()
                live = self.live_factory(
                    self._next_live_target(),
                    tuple(dict.fromkeys((*DEFAULT_PORTS, *ports))),
                )
                if hasattr(live, "set_packet_sink"):
                    live.set_packet_sink(self.live_events.feed)
                live.start()
                self.live_capture = live
            except Exception as error:
                self.live_events.stop()
                self.live_capture = None
                LOG.exception("live_capture_start_failed")
                live_error = f"{type(error).__name__}: {error}"
            self.paused = False
            return {
                "session_id": self.current_session,
                "session_counter": self.session_counter,
                "capture_prefix": prefix,
                "capture_ports": list(ports),
                "capture_client_ports": [list(group) for group in self.client_ports],
                "capture_client_pids": list(self.client_pids),
                "clients": len(pids),
                "connections": len(local_ports),
                "live": self.live_capture is not None,
                "live_error": live_error,
            }

    def _refresh_routes(self) -> None:
        if not self.executable:
            return
        routes = self.client_reader(self.executable, DEFAULT_PORTS)
        active_pids = {int(route["pid"]) for route in routes}
        if (
            self.route_identity_trusted
            and self.client_pids
            and not active_pids.intersection(self.client_pids)
        ):
            self.route_identity_trusted = False
            self.client_pids = []
            self.client_ports = ()
        if self.route_identity_trusted:
            self.client_pids, groups = _merge_client_routes(
                self.client_pids, list(self.client_ports), routes
            )
            self.client_ports = tuple(groups)
        ports = tuple(
            dict.fromkeys(
                port
                for route in routes
                for field in ("local_ports", "remote_ports")
                for port in route.get(field, ())
            )
        )
        if ports and self.capture:
            self.capture.add_ports(ports)
            self.capture_ports = tuple(dict.fromkeys((*self.capture_ports, *ports)))
        if ports and self.live_capture:
            self.live_capture.add_ports(ports)

    def heartbeat(self) -> None:
        if self.capture:
            self.capture.heartbeat()

    def bytes_written(self) -> int:
        files = list(self.capture.segment_files()) if self.capture else []
        files.extend(self.live_files)
        if self.live_capture:
            files.append(self.live_capture.target)
        return sum(path.stat().st_size for path in dict.fromkeys(files) if path.exists())

    def read_live(self) -> dict[str, object]:
        with self._lock:
            if not self.current_session:
                return {"added": 0, "available": False}
            self._refresh_routes()
            if not self.live_capture:
                if not self.capture or not self.capture.active:
                    return {"added": 0, "available": False}
                completed = self.capture.stop().files
                prefix = self._next_capture_prefix()
                capture = self.capture_factory(self.capture_directory)
                capture.start_for_ports(prefix, self.capture_ports)
                self.capture = capture
                self.pending_files.extend(
                    path for path in completed if path not in self.pending_files
                )
                store = CaptureStore(self.database_path)
                try:
                    added = sum(
                        store.ingest(
                            path,
                            session_id=self.current_session,
                            ports=DEFAULT_PORTS,
                            client_ports=self.client_ports,
                        )
                        for path in completed
                        if path.exists()
                    )
                finally:
                    store.close()
                return {
                    "added": added,
                    "available": True,
                    "fallback": True,
                    "capture_prefix": prefix,
                    "capture_ports": list(self.capture_ports),
                }
            target = self.live_capture.rotate(self._next_live_target())
            if not target.exists() or target.stat().st_size <= 24:
                target.unlink(missing_ok=True)
                return {"added": 0, "available": True}
            self.live_files.append(target)
            store = CaptureStore(self.database_path)
            try:
                added = store.ingest(
                    target,
                    session_id=self.current_session,
                    ports=DEFAULT_PORTS,
                    client_ports=self.client_ports,
                    append_only=True,
                )
            finally:
                store.close()
            return {"added": added, "available": True, "bytes": target.stat().st_size}

    def preview_live(self) -> dict[str, object]:
        """Entrega eventos efêmeros já lidos da RAM, sem reler o PCAP."""
        with self._lock:
            if not self.current_session or not self.live_capture:
                return {"added": 0, "available": False, "fast": False}
            self._refresh_routes()
            events = self.live_events.snapshot()
            return {
                "added": len(events),
                "available": True,
                "fast": True,
                "events": events,
                "client_ports": [list(group) for group in self.client_ports],
            }

    def abandon(self) -> list[Path]:
        """Interrompe a captura e devolve os arquivos sem decodificá-los."""
        with self._lock:
            files = [*self.pending_files, *self.live_files]
            if self.live_capture:
                live, self.live_capture = self.live_capture, None
                live.stop()
                if live.target is not None:
                    files.append(live.target)
            self.live_events.stop()
            if self.capture:
                files.extend(self.capture.stop().files)
            self.capture = None
            self.live_files.clear()
            self.pending_files.clear()
            self.current_session = None
            self.paused = False
            return list(dict.fromkeys(path for path in files if path.exists()))

    def stop_without_reading(self) -> dict[str, object]:
        """Interrompe o Pktmon, preserva os arquivos e adia toda decodificação."""
        with self._lock:
            if not self.current_session:
                raise RuntimeError("Não existe sessão atual para encerrar")
            session_id = self.current_session
            if self.live_capture:
                live, self.live_capture = self.live_capture, None
                try:
                    live.stop()
                finally:
                    self.live_events.stop()
                    if live.target is not None and live.target.exists():
                        self.live_files.append(live.target)
            if self.capture:
                status, self.capture = self.capture.stop(), None
                self.pending_files.extend(status.files)
            self.paused = True
            files = list(
                dict.fromkeys(
                    path
                    for path in (*self.pending_files, *self.live_files)
                    if path.exists()
                )
            )
            return {
                "session_id": session_id,
                "files": files,
                "bytes": sum(path.stat().st_size for path in files),
                "paused": True,
                "decoded": False,
            }

    def stop(self, *, pause: bool = False) -> dict[str, object]:
        with self._lock:
            if not self.current_session:
                raise RuntimeError("Não existe sessão atual para encerrar")
            session_id = self.current_session
            if self.live_capture:
                live, self.live_capture = self.live_capture, None
                try:
                    live.stop()
                finally:
                    self.live_events.stop()
                    if live.target is not None and live.target.exists():
                        self.live_files.append(live.target)
            status = self.capture.stop() if self.capture else None
            files = tuple(dict.fromkeys((
                *self.pending_files,
                *(status.files if status else ()),
            )))
            failures: list[str] = []
            added = 0
            store = CaptureStore(self.database_path)
            try:
                live_files = [
                    path for path in self.live_files
                    if path.exists() and path.stat().st_size > 24
                ]
                sources = live_files or list(files)
                for path in sources:
                    try:
                        added += store.ingest(
                            path,
                            session_id=self.current_session,
                            ports=DEFAULT_PORTS,
                            client_ports=self.client_ports,
                            append_only=path in live_files,
                        )
                    except Exception as error:
                        LOG.exception(
                            "capture_ingest_failed session=%s source=%s",
                            self.current_session, path.name,
                        )
                        failures.append(f"{path.name}: {type(error).__name__}")
                if not failures and not pause:
                    now = time.time_ns()
                    for item in store.subsessions(self.current_session):
                        if item.get("ended_ns") is None:
                            store.end_subsession(item["id"], now)
            finally:
                store.close()
            if not failures:
                for path in self.live_files:
                    path.unlink(missing_ok=True)
                self.live_files.clear()
                self.pending_files.clear()
            self.paused = pause
            if not pause:
                self.current_session = None
            self.capture = None
            return {
                "session_id": session_id,
                "added": added,
                "failures": failures,
                "files": len(files),
                "paused": pause,
            }
