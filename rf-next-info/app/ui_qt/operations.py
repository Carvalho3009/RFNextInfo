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
from typing import Callable, Protocol

from app.main import (
    DEFAULT_PORTS,
    VERSION,
    _capture_summary,
    _collection_marks,
    _market_rows,
    _merge_client_routes,
    game_data_language,
    item_names_for_language,
)
from core.capture import PktmonCapture
from core.auction_sales import auction_sales_snapshot, auction_transaction_history
from core.connections import (
    clients_for_executable,
    connected_processes,
    emulator_processes,
)
from core.pktmon_realtime import RealtimeCapture
from core.live_stream import LiveEventStream
from core.map_state import MapModule
from core.knowledge import KnowledgeStore
from core.store import CaptureStore


LOG = logging.getLogger("rfqol")
LOG.addHandler(logging.NullHandler())


class WebAgentSink(Protocol):
    def start_session(self, session_id: str, *, resumed: bool = False) -> None: ...
    def pause_session(self, session_id: str, *, reason: str = "paused") -> None: ...
    def finish_session(self, session_id: str, *, reason: str = "finished") -> None: ...
    def submit(self, event: dict[str, object]) -> bool: ...


DEFAULT_GLOBAL_SHORTCUTS = {
    "monitor_pve": "Ctrl+F5",
    "monitor_pvp": "Ctrl+F6",
    "monitor_boss": "Ctrl+F7",
}
MIN_MEMORY_BUDGET_MB = 256
DEFAULT_MEMORY_BUDGET_MB = 768
MAX_MEMORY_BUDGET_MB = 2048
MEMORY_BUDGET_STEP_MB = 128


def memory_limits_for_budget(value: object) -> dict[str, int]:
    try:
        budget_mb = int(value)
    except (TypeError, ValueError):
        budget_mb = DEFAULT_MEMORY_BUDGET_MB
    budget_mb = max(MIN_MEMORY_BUDGET_MB, min(MAX_MEMORY_BUDGET_MB, budget_mb))
    budget_mb = MIN_MEMORY_BUDGET_MB + (
        (budget_mb - MIN_MEMORY_BUDGET_MB + MEMORY_BUDGET_STEP_MB // 2)
        // MEMORY_BUDGET_STEP_MB
        * MEMORY_BUDGET_STEP_MB
    )
    scale = min(1.0, budget_mb / DEFAULT_MEMORY_BUDGET_MB)

    def scaled(default: int, minimum: int, step: int = 1) -> int:
        result = max(minimum, int(round(default * scale / step)) * step)
        return min(default, result)

    mib = 1024 * 1024
    return {
        "budget_mb": budget_mb,
        "pressure_bytes": budget_mb * mib,
        "pending_packets": scaled(8192, 2048, 256),
        "pending_packet_bytes": scaled(32, 8) * mib,
        "events": scaled(20_000, 5_000, 1_000),
        "entity_anchors": scaled(4096, 1024, 256),
        "boss_events": scaled(4096, 1024, 256),
        "flows": scaled(64, 16, 8),
        "pending_segments_per_flow": scaled(256, 64, 32),
        "pending_bytes_per_flow": scaled(2, 1) * mib,
        "flow_buffer_bytes": scaled(4, 1) * mib,
        "pvp_rows": scaled(250, 75, 25),
        "inventory_icons": scaled(256, 64, 32),
        "alert_cooldowns": scaled(2048, 512, 128),
        "seen_drop_events": scaled(4096, 1024, 256),
        "character_history": scaled(5000, 1000, 500),
    }


def _live_stream(
    limits: dict[str, int],
    event_sink: Callable[[dict[str, object]], bool] | None = None,
) -> LiveEventStream:
    return LiveEventStream(
        max_events=limits["events"],
        max_entity_anchors=limits["entity_anchors"],
        max_pending_packets=limits["pending_packets"],
        max_pending_packet_bytes=limits["pending_packet_bytes"],
        max_boss_events=limits["boss_events"],
        max_flows=limits["flows"],
        max_pending_segments_per_flow=limits["pending_segments_per_flow"],
        max_pending_bytes_per_flow=limits["pending_bytes_per_flow"],
        max_flow_buffer_bytes=limits["flow_buffer_bytes"],
        event_sink=event_sink,
    )


def _realtime_capture(factory, target, ports, limits: dict[str, int]):
    if factory is RealtimeCapture:
        return factory(
            target,
            ports,
            max_write_queue_packets=limits["pending_packets"],
            max_write_queue_bytes=limits["pending_packet_bytes"],
        )
    return factory(target, ports)


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

    @staticmethod
    def _inventory_rows(snapshot: dict, uid: str) -> list[dict[str, object]]:
        rows = []
        for item in dict(snapshot.get("inventories") or {}).get(uid, []):
            if int(item.get("item_index") or 0) <= 0 or int(item.get("quantity") or 0) <= 0:
                continue
            row = {
                key: item.get(key)
                for key in (
                    "item_index",
                    "name",
                    "quantity",
                    "kind",
                    "category",
                    "slot",
                    "refinement",
                    "locked",
                    "expires_at",
                )
            }
            row["category"] = str(
                item.get("category")
                or ("equipment" if item.get("kind") == "equipment" else "other")
            )
            if item.get("category_source") == "manual":
                row["category_source"] = "manual"
            rows.append(row)
        return rows

    def send_mode(
        self, mode: str, client_index: int, snapshot: dict, language: str
    ) -> dict[str, object]:
        self.license.require("envio ao site")
        if not self.site_profile.connected:
            raise ValueError("Valide o token do Profile antes de enviar")
        session_id = str(snapshot.get("session_id") or "")
        if not session_id:
            raise ValueError("Ainda não existe uma sessão para enviar")
        store = CaptureStore(self.database_path, readonly=True)
        try:
            language = game_data_language(language)
            item_names = item_names_for_language(language)
            metadata = self._metadata(mode)
            uid = ""
            if mode == "market":
                rows = _market_rows(
                    store.session_envelope(session_id, None, include_unassigned=True),
                    item_names,
                )
                if not rows:
                    raise ValueError("Ainda não existem eventos de Mercado para enviar")
                payload = {"metadata": metadata, "rows": rows}
                target = "Mercado geral"
            else:
                selected = self._selected_character(snapshot, client_index)
                uid, character = str(selected["uid"]), str(selected["name"])
                if mode == "character":
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
                        item_names,
                        game_language=language,
                    )
                elif mode in {"codex", "memory_chips"}:
                    envelope = store.latest_collection_envelope(uid)
                    summary = {}
                elif mode == "inventory":
                    envelope = {}
                    summary = {}
                else:
                    raise ValueError("Tipo de envio inválido")
                site_summary = {
                    **summary,
                    "loot": _site_loot_rows(summary.get("loot")),
                }
                if mode in {"character", "inventory"}:
                    site_summary["inventory_schema_version"] = 1
                    site_summary["inventory"] = self._inventory_rows(snapshot, uid)
                    if mode == "inventory" and not site_summary["inventory"]:
                        raise ValueError("Ainda não existem itens de inventário para enviar")
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
                elif mode in {"codex", "memory_chips"}:
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
                    "capture": site_summary if mode in {"character", "inventory"} else {},
                    "loadout": summary["loadout"] if mode == "character" else {},
                    "subsession_reports": [],
                }
                target = (
                    f"Cliente {chr(65 + client_index)}"
                    if client_index < 2
                    else f"Emulador {client_index - 1}"
                )
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

    def send_all(
        self, client_index: int, snapshot: dict, language: str
    ) -> dict[str, object]:
        selected = self._selected_character(snapshot, client_index)
        uid = str(selected["uid"])
        modes = ["character"]
        if self._inventory_rows(snapshot, uid):
            modes.append("inventory")
        counts = dict(
            dict(snapshot.get("collection_type_counts_by_uid") or {}).get(uid) or {}
        )
        if counts.get(1):
            modes.append("codex")
        if counts.get(2):
            modes.append("memory_chips")
        results = [
            self.send_mode(mode, client_index, snapshot, language)
            for mode in modes
        ]
        return {
            "target": results[0]["target"],
            "uid": uid,
            "modes": modes,
            "receipts": [item.get("receipt", "") for item in results],
        }

    def send_subsessions(
        self, identifiers: list[str], snapshot: dict, language: str
    ) -> dict[str, object]:
        self.license.require("envio de subsessões")
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
                    item_names_for_language(language),
                    game_language=game_data_language(language),
                )
                site_summary = {
                    **summary,
                    "loot": _site_loot_rows(summary.get("loot")),
                }
                seconds = max(1, int((ended_ns - int(item["started_ns"])) / 1_000_000_000))
                hours = seconds / 3600
                gained_percent = summary.get("exp_gained_percent")
                report = {
                    **{
                        key: value
                        for key, value in item.items()
                        if key != "auto_context"
                    },
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
        pvp_allowed = pve_allowed = False
        try:
            self.license.require("envio do Banco PvP", "monitor-pvp")
            pvp_allowed = True
        except PermissionError:
            pass
        try:
            self.license.require("envio do Banco PvE", "monitor-pve")
            pve_allowed = True
        except PermissionError:
            pass
        if not pvp_allowed and not pve_allowed:
            raise PermissionError(
                "Sua licença não permite enviar os Bancos PvP ou PvE."
            )
        if not self.site_profile.connected:
            return {"skipped": True, "reason": "profile_not_connected"}
        capture = CaptureStore(self.database_path, readonly=True)
        knowledge = KnowledgeStore(knowledge_path)
        try:
            envelope = capture.session_envelope(
                session_id, None, include_unassigned=True
            )
            knowledge.observe_events(
                envelope.get("events") or [], session_id=session_id
            )
            payload = knowledge.pending_payload()
            payload["mobs"] = []
            payload["metadata"] = {
                **self._metadata("observations"),
                "session_id": session_id,
                "privacy": "decoded-fields-only; no raw payload or opcode 0x0101",
            }
            pvp_response: dict[str, object] = {"skipped": True}
            if pvp_allowed and payload["characters"]:
                stable = {
                    "profile": self.site_profile.profile,
                    "session_id": session_id,
                    "characters": payload["characters"],
                }
                key = hashlib.sha256(json.dumps(
                    stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                ).encode()).hexdigest()
                pvp_response = self.site_profile.upload_observations(payload, key)
                knowledge.mark_uploaded(payload)

            delta = knowledge.pending_pve_delta() if pve_allowed else {"observations": []}
            pve_result = {"acknowledged": 0, "conflicts": 0, "missing": 0}
            if delta["observations"]:
                delta["metadata"] = {
                    **self._metadata("pve_observations"),
                    "session_id": session_id,
                    "privacy": "decoded-fields-only; no raw payload or opcode 0x0101",
                }
                pve_key = hashlib.sha256(json.dumps(
                    {
                        "profile": self.site_profile.profile,
                        "observations": delta["observations"],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()).hexdigest()
                pve_response = self.site_profile.upload_pve_observations(
                    delta, pve_key
                )
                pve_result = knowledge.mark_pve_ack(delta, pve_response)
                if pve_result["missing"]:
                    raise ValueError(
                        "O site confirmou apenas parte do Banco PvE; "
                        "os registros restantes serão reenviados."
                    )
            return {
                **pvp_response,
                "skipped": not payload["characters"] and not pve_result["acknowledged"],
                "sent_characters": len(payload["characters"]),
                "sent_mobs": pve_result["acknowledged"],
                "pve_conflicts": pve_result["conflicts"],
            }
        finally:
            knowledge.close()
            capture.close()

    def send_exp_rank(self, session_id: str) -> dict[str, object]:
        self.license.require("envio do ranking de EXP", "exp-ranking")
        if not self.site_profile.connected:
            raise ValueError("Valide o token do Profile antes de enviar")
        capture = CaptureStore(self.database_path, readonly=True)
        try:
            ranking = capture.exp_rank_snapshot(session_id)
        finally:
            capture.close()
        records = list(ranking.get("records") or [])
        if not records:
            raise ValueError("Ainda não existem dados de ranking de EXP para enviar")
        if ranking.get("completeness") != "complete":
            raise ValueError(
                "O Top 100 de EXP ainda está parcial; percorra todas as posições "
                "no jogo antes do envio"
            )
        payload = {
            "metadata": {
                **self._metadata("exp_rank"),
                "session_id": session_id,
                "privacy": "decoded-fields-only; no raw payload or opcode 0x0101",
            },
            "exp_rank": {
                key: value
                for key, value in ranking.items()
                if key not in {"signature", "snapshot_key"}
            },
        }
        key = hashlib.sha256(
            f"{self.site_profile.profile}\0exp-rank\0{ranking['signature']}".encode()
        ).hexdigest()
        response = self.site_profile.upload_exp_rank(payload, key)
        received = response.get("received_exp_rank")
        if not isinstance(received, int) or received != len(records):
            raise ValueError(
                "O site ainda não confirmou o contrato do ranking de EXP. "
                "O envio será tentado novamente automaticamente."
            )
        return {
            "records": received,
            "signature": ranking["signature"],
            "snapshot_key": ranking["snapshot_key"],
            "duplicate": bool(response.get("duplicate")),
        }

    def send_auction_bank(self, session_id: str, language: str) -> dict[str, object]:
        self.license.require("envio do Banco de Leilão")
        if not self.site_profile.connected:
            raise ValueError("Valide o token do Profile antes de enviar")
        if not session_id:
            raise ValueError("Ainda não existe uma sessão para enviar")
        store = CaptureStore(self.database_path, readonly=True)
        try:
            events: list[dict[str, object]] = []
            for profile in store.session_profiles(session_id):
                uid = str(profile.get("uid") or "")
                if uid:
                    events.extend(store.auction_events_for_character(session_id, uid))
        finally:
            store.close()
        secret = hashlib.sha256(
            f"rf-qol.auction-bank/v1:{self.license.installation_id}".encode()
        ).digest()
        names = {
            int(key): value
            for key, value in item_names_for_language(language).items()
            if str(key).isdigit()
        }
        listings = auction_sales_snapshot(events, secret=secret, item_names=names)
        transactions = auction_transaction_history(
            events, secret=secret, item_names=names
        )
        if not listings and not transactions:
            raise ValueError("Ainda não existem registros confirmados do leilão")
        payload = {
            "metadata": {
                **self._metadata("auction_bank"),
                "session_id": session_id,
                "schema_version": 1,
                "privacy": "decoded-fields-only; no account, character or exchange ids",
            },
            "listings": listings,
            "transactions": transactions,
        }
        stable = {**payload, "metadata": {
            key: value for key, value in payload["metadata"].items()
            if key != "captured_at"
        }}
        idempotency_key = hashlib.sha256(json.dumps(
            stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()).hexdigest()
        response = self.site_profile.upload_auction_bank(payload, idempotency_key)
        return {
            "listings": len(listings),
            "transactions": len(transactions),
            "receipt": response.get("receipt", ""),
            "duplicate": bool(response.get("duplicate")),
        }

    def receive_observations(self, knowledge_path: Path) -> dict[str, object]:
        self.license.require("recebimento do Banco PvP", "monitor-pvp")
        if not self.site_profile.connected:
            raise ValueError("Conecte o token do Profile antes de receber")
        response = self.site_profile.download_observations()
        knowledge = KnowledgeStore(knowledge_path)
        try:
            response["synced_characters"] = knowledge.merge_remote_characters(
                response.get("characters") or []
            )
            return response
        finally:
            knowledge.close()


class ExportEngine:
    """Exporta o mesmo envelope da versão estável sem depender de Tk ou Qt."""

    def __init__(self, database_path: Path, license_client) -> None:
        self.database_path = Path(database_path)
        self.license = license_client

    @staticmethod
    def _targets(store: CaptureStore, session_id: str) -> list[dict[str, object]]:
        detected = store.session_profiles(session_id)
        stats = store.session_stats(session_id)
        if len(detected) > 7 or not detected:
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
        language: str,
    ) -> dict:
        ended_ns = int(subsession.get("ended_ns") or time.time_ns())
        started_ns = int(subsession["started_ns"])
        envelope = store.interval_envelope(
            session_id, character_uid, started_ns, ended_ns
        )
        summary, _ = _capture_summary(
            envelope,
            character_uid,
            item_names=item_names,
            game_language=language,
        )
        seconds = max(1, int((ended_ns - started_ns) / 1_000_000_000))
        hours = seconds / 3600
        exp_percent = summary.get("exp_gained_percent")
        return {
            **{
                key: value
                for key, value in subsession.items()
                if key != "auto_context"
            },
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
        self.license.require("exportação")
        if not session_id:
            raise ValueError("Nenhuma sessão capturada está disponível")
        target = Path(target)
        target.mkdir(parents=True, exist_ok=True)
        language = game_data_language(language)
        item_names = item_names_for_language(language)
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
                    envelope,
                    str(uid or ""),
                    name,
                    item_names=item_names,
                    game_language=language,
                )
                _all_marks, collection_types = _collection_marks(envelope)
                reports = [
                    self._subsession_report(
                        store,
                        session_id,
                        subsession,
                        uid,
                        item_names,
                        language,
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
        self.shortcuts.update({
            action: shortcut
            for action, shortcut in (shortcuts or {}).items()
            if action in DEFAULT_GLOBAL_SHORTCUTS
        })
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
        configured.update({
            action: shortcut
            for action, shortcut in shortcuts.items()
            if action in DEFAULT_GLOBAL_SHORTCUTS
        })
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


def _route_groups(
    groups: Iterable[Iterable[int]], size: int
) -> tuple[tuple[int, ...], ...]:
    normalized: list[tuple[int, ...]] = []
    for group in groups:
        ports = tuple(group)
        if ports:
            normalized.append(ports)
    return tuple(normalized[:size])


def _combined_route_groups(
    pc_groups: Iterable[Iterable[int]],
    emulator_groups: Iterable[Iterable[int]],
) -> tuple[tuple[int, ...], ...]:
    pc = _route_groups(pc_groups, 2)
    emulators = _route_groups(emulator_groups, 5)
    if emulators:
        pc = pc + ((),) * (2 - len(pc))
    return (*pc, *emulators)


def _stable_capture_ports(
    routes: Iterable[dict[str, object]],
) -> tuple[int, ...]:
    """Retém somente portas remotas estáveis para os filtros de captura.

    As portas locais são efêmeras e continuam sendo usadas para separar os
    clientes, mas não precisam virar filtros do PktMon: os quatro ports RF
    padrão e as portas remotas já cobrem ambos os sentidos da conexão.
    """
    return tuple(dict.fromkeys(
        int(port)
        for route in routes
        for port in route.get("remote_ports", ())
        if 1 <= int(port) <= 65535
    ))


def _require_distinct_client_routes(
    routes: Iterable[dict[str, object]], pids: Iterable[int], label: str
) -> None:
    active = {int(pid) for pid in pids}
    routed = {
        int(route["pid"])
        for route in routes
        if route.get("pid") is not None and route.get("local_ports")
    }
    if len(active) > 1 and not active.issubset(routed):
        raise RuntimeError(
            f"Não foi possível separar as conexões dos clientes {label}. "
            "Feche os clientes extras ou tente novamente."
        )


def _enforce_connection_limits(
    claims: dict[str, object], pc_clients: int, emulators: int
) -> dict[str, int]:
    del claims
    return {"pc": max(0, int(pc_clients)), "emulators": max(0, int(emulators))}


class MonitorEngine:
    """Stream Pktmon somente em memória, independente da captura histórica."""

    def __init__(
        self,
        license_client,
        *,
        live_factory: Callable[[Path | None, tuple[int, ...]], RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
        emulator_reader: Callable[..., dict] | None = None,
        client_reader: Callable[..., list] = clients_for_executable,
        memory_budget_mb: int = DEFAULT_MEMORY_BUDGET_MB,
        game_language: str = "pt",
    ) -> None:
        self.license = license_client
        self.live_factory = live_factory
        self.process_reader = process_reader
        self.emulator_reader = emulator_reader or (
            emulator_processes
            if process_reader is connected_processes
            else lambda _ports: {}
        )
        self.client_reader = client_reader
        self.live_capture: RealtimeCapture | None = None
        self.memory_limits = memory_limits_for_budget(memory_budget_mb)
        self.memory_budget_mb = self.memory_limits["budget_mb"]
        self._pending_memory_limits: dict[str, int] | None = None
        self.events = _live_stream(self.memory_limits)
        self.map_module = MapModule(language=game_language)
        self.executable = ""
        self.emulator_executable = ""
        self.pc_client_ports: tuple[tuple[int, ...], ...] = ()
        self.emulator_client_ports: tuple[tuple[int, ...], ...] = ()
        self.client_ports: tuple[tuple[int, ...], ...] = ()
        self._lock = threading.RLock()

    @property
    def active(self) -> bool:
        return self.live_capture is not None

    def _apply_memory_limits(self, limits: dict[str, int]) -> None:
        self.events.stop()
        self.memory_limits = limits
        self.memory_budget_mb = limits["budget_mb"]
        self.events = _live_stream(limits)
        self._pending_memory_limits = None

    def _apply_pending_memory_limits(self) -> None:
        if self._pending_memory_limits is not None:
            self._apply_memory_limits(self._pending_memory_limits)

    def configure_memory_budget(self, value: object) -> bool:
        """Aplica agora quando o stream está ocioso ou agenda para a parada."""
        limits = memory_limits_for_budget(value)
        with self._lock:
            if self.active:
                self._pending_memory_limits = limits
                return False
            self._apply_memory_limits(limits)
            return True

    def relieve_memory_pressure(self) -> dict[str, int]:
        with self._lock:
            return self.events.compact(0.5)

    def _authorize(self, features) -> tuple[str, ...]:
        requested = tuple(dict.fromkeys(features))
        allowed = {"monitor-pve", "monitor-pvp", "monitor-boss"}
        if not requested or not set(requested).issubset(allowed):
            raise PermissionError("Módulo de monitor inválido")
        for feature in requested:
            self.license.require("monitor em tempo real", feature)
        return requested

    def start(self, features) -> dict[str, object]:
        features = self._authorize(features)
        claims = self.license.require("limites de conexão", features[0])
        with self._lock:
            if self.active:
                return self.snapshot(features)
            self._apply_pending_memory_limits()
            processes = self.process_reader(DEFAULT_PORTS)
            emulators = self.emulator_reader(DEFAULT_PORTS)
            if not processes and not emulators:
                raise RuntimeError("Abra um cliente PC ou emulador e entre no jogo")
            executable, (pids, local_ports, remote_ports) = max(
                processes.items(), key=lambda item: len(item[1][0])
            ) if processes else ("", (set(), set(), set()))
            emulator_executable, (emulator_pids, emulator_local, emulator_remote) = max(
                emulators.items(), key=lambda item: len(item[1][0])
            ) if emulators else ("", (set(), set(), set()))
            _enforce_connection_limits(claims, len(pids), len(emulator_pids))
            routes = self.client_reader(executable, DEFAULT_PORTS) if executable else []
            emulator_routes = (
                self.client_reader(emulator_executable, DEFAULT_PORTS)
                if emulator_executable else []
            )
            _require_distinct_client_routes(routes, pids, "PC")
            _require_distinct_client_routes(
                emulator_routes, emulator_pids, "emuladores"
            )
            _pids, groups = _merge_client_routes([], [], routes)
            _emulator_pids, emulator_groups = _merge_client_routes(
                [], [], emulator_routes, 5
            )
            self.executable = executable
            self.emulator_executable = emulator_executable
            self.pc_client_ports = _route_groups(groups, 2) or (
                (tuple(sorted(local_ports)),) if local_ports else ()
            )
            self.emulator_client_ports = _route_groups(emulator_groups, 5) or (
                (tuple(sorted(emulator_local)),) if emulator_local else ()
            )
            self.client_ports = _combined_route_groups(
                self.pc_client_ports, self.emulator_client_ports
            )
            ports = tuple(dict.fromkeys((
                *DEFAULT_PORTS,
                *_stable_capture_ports((*routes, *emulator_routes)),
            )))
            self.events.clear()
            self.map_module.reset()
            self.events.start()
            live = _realtime_capture(
                self.live_factory, None, ports, self.memory_limits
            )
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
                "clients": len(pids) + len(emulator_pids),
                "pc_clients": len(pids),
                "emulators": len(emulator_pids),
                "client_ports": [list(group) for group in self.client_ports],
                "map": self.map_module.snapshot([], self.client_ports),
                "events": [],
            }

    def _refresh_routes(self) -> None:
        if not self.live_capture:
            return
        if not self.executable:
            processes = self.process_reader(DEFAULT_PORTS)
            if processes:
                self.executable, _details = max(
                    processes.items(), key=lambda item: len(item[1][0])
                )
        if not self.emulator_executable:
            emulators = self.emulator_reader(DEFAULT_PORTS)
            if emulators:
                self.emulator_executable, _details = max(
                    emulators.items(), key=lambda item: len(item[1][0])
                )
        routes = self.client_reader(self.executable, DEFAULT_PORTS) if self.executable else []
        emulator_routes = (
            self.client_reader(self.emulator_executable, DEFAULT_PORTS)
            if self.emulator_executable else []
        )
        claims = self.license.require("limites de conexão")
        _enforce_connection_limits(
            claims,
            len({int(route["pid"]) for route in routes}),
            len({int(route["pid"]) for route in emulator_routes}),
        )
        _pids, groups = _merge_client_routes([], list(self.pc_client_ports), routes)
        _emulator_pids, emulator_groups = _merge_client_routes(
            [], list(self.emulator_client_ports), emulator_routes, 5
        )
        self.pc_client_ports = _route_groups(groups, 2)
        self.emulator_client_ports = _route_groups(emulator_groups, 5)
        self.client_ports = _combined_route_groups(
            self.pc_client_ports, self.emulator_client_ports
        )
        ports = tuple(
            dict.fromkeys(
                port
                for route in (*routes, *emulator_routes)
                for field in ("local_ports", "remote_ports")
                for port in route.get(field, ())
            )
        )
        if ports:
            self.live_capture.add_ports(ports)

    def snapshot(self, features) -> dict[str, object]:
        self._authorize(features)
        with self._lock:
            if not self.live_capture:
                return {"available": False, "active": False, "events": []}
            self._refresh_routes()
            self.events.start()
            events = self.events.snapshot()
            return {
                "available": True,
                "active": True,
                "added": len(events),
                "events": events,
                "client_ports": [list(group) for group in self.client_ports],
                "map": self.map_module.snapshot(
                    events,
                    self.client_ports,
                    now_ns=time.time_ns(),
                ),
                "monitor_metrics": self._monitor_metrics(),
            }

    def _monitor_metrics(self) -> dict[str, object]:
        metrics = dict(self.events.metrics())
        metrics["memory_budget_mb"] = self.memory_budget_mb
        live = self.live_capture
        if live:
            for name in (
                "received_packets",
                "filtered_packets",
                "duplicate_packets",
                "missed_write",
                "missed_read",
                "write_queue_depth",
                "write_queue_limit",
                "write_queue_bytes",
                "write_queue_byte_limit",
                "dropped_write_packets",
                "dropped_write_bytes",
            ):
                metrics[name] = int(getattr(live, name, 0) or 0)
        return metrics

    def stop(self) -> None:
        with self._lock:
            live, self.live_capture = self.live_capture, None
            try:
                if live:
                    live.stop()
            finally:
                self.events.stop()
                self._apply_pending_memory_limits()


class CaptureEngine:
    """Ciclo de captura sem dependência da interface Tk ou Qt."""

    def __init__(
        self,
        capture_directory: Path,
        database_path: Path,
        license_client,
        *,
        profile: str = "Profile",
        session_counter: int = 0,
        capture_factory: Callable[[Path], PktmonCapture] = PktmonCapture,
        live_factory: Callable[[Path, tuple[int, ...]], RealtimeCapture] = RealtimeCapture,
        process_reader: Callable[..., dict] = connected_processes,
        emulator_reader: Callable[..., dict] | None = None,
        client_reader: Callable[..., list] = clients_for_executable,
        memory_budget_mb: int = DEFAULT_MEMORY_BUDGET_MB,
        game_language: str = "pt",
        web_agent: WebAgentSink | None = None,
    ) -> None:
        self.capture_directory = Path(capture_directory)
        self.database_path = Path(database_path)
        self.license = license_client
        self.profile = profile.strip() or "Profile"
        self.session_counter = int(session_counter)
        self.capture_factory = capture_factory
        self.live_factory = live_factory
        self.process_reader = process_reader
        self.emulator_reader = emulator_reader or (
            emulator_processes
            if process_reader is connected_processes
            else lambda _ports: {}
        )
        self.client_reader = client_reader
        self.capture: PktmonCapture | None = None
        self.live_capture: RealtimeCapture | None = None
        self.current_session: str | None = None
        self.executable = ""
        self.emulator_executable = ""
        self.pc_client_pids: list[int] = []
        self.emulator_client_pids: list[int] = []
        self.pc_client_ports: tuple[tuple[int, ...], ...] = ()
        self.emulator_client_ports: tuple[tuple[int, ...], ...] = ()
        self.client_pids: list[int] = []
        self.client_ports: tuple[tuple[int, ...], ...] = ()
        self.live_files: list[Path] = []
        self.pending_files: list[Path] = []
        self.capture_ports: tuple[int, ...] = ()
        self.live_index = 0
        self.capture_index = 0
        self.paused = False
        self.route_identity_trusted = True
        self.memory_limits = memory_limits_for_budget(memory_budget_mb)
        self.memory_budget_mb = self.memory_limits["budget_mb"]
        self._pending_memory_limits: dict[str, int] | None = None
        self.web_agent = web_agent
        self.live_events = _live_stream(
            self.memory_limits,
            self.web_agent.submit if self.web_agent is not None else None,
        )
        self.map_module = MapModule(language=game_language)
        self._lock = threading.RLock()

    def _sync_client_routes(self) -> None:
        self.pc_client_ports = _route_groups(self.pc_client_ports, 2)
        self.emulator_client_ports = _route_groups(self.emulator_client_ports, 5)
        self.client_pids = [*self.pc_client_pids, *self.emulator_client_pids]
        self.client_ports = _combined_route_groups(
            self.pc_client_ports, self.emulator_client_ports
        )

    def restore(self, preferences: dict[str, object]) -> dict[str, object] | None:
        """Recupera uma captura pendente sem iniciar uma sessão nova."""
        self.license.require("recuperação de captura")
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
        # Portas são transitórias; somente os PIDs preservam os sete slots.
        self.pc_client_ports = ()
        self.emulator_client_ports = ()
        self.pc_client_pids = [
            int(pid)
            for pid in (
                preferences.get("capture_pc_client_pids")
                or preferences.get("capture_client_pids")
                or ()
            )
        ][:2]
        self.emulator_client_pids = [
            int(pid)
            for pid in preferences.get("capture_emulator_client_pids") or ()
        ][:5]
        self._sync_client_routes()
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

    def web_agent_health(self) -> dict[str, object]:
        if self.web_agent is None:
            return {"enabled": False, "state": "disabled"}
        provider = getattr(self.web_agent, "health", None)
        if not callable(provider):
            return {"enabled": True, "state": "ready"}
        try:
            health = provider()
        except Exception:
            LOG.exception("web_agent_health_failed")
            return {
                "enabled": True,
                "state": "error",
                "last_error_code": "health_unavailable",
            }
        return health if isinstance(health, dict) else {
            "enabled": True,
            "state": "error",
            "last_error_code": "health_invalid",
        }

    def _apply_memory_limits(self, limits: dict[str, int]) -> None:
        self.live_events.stop()
        self.memory_limits = limits
        self.memory_budget_mb = limits["budget_mb"]
        self.live_events = _live_stream(
            limits,
            self.web_agent.submit if self.web_agent is not None else None,
        )
        self._pending_memory_limits = None

    def _apply_pending_memory_limits(self) -> None:
        if self._pending_memory_limits is not None:
            self._apply_memory_limits(self._pending_memory_limits)

    def configure_memory_budget(self, value: object) -> bool:
        """Aplica agora quando a captura está ociosa ou agenda para a parada."""
        limits = memory_limits_for_budget(value)
        with self._lock:
            if self.active:
                self._pending_memory_limits = limits
                return False
            self._apply_memory_limits(limits)
            return True

    def relieve_memory_pressure(self) -> dict[str, int]:
        with self._lock:
            return self.live_events.compact(0.5)

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
        claims = self.license.require("captura")
        with self._lock:
            if self.active:
                raise RuntimeError("A captura já está ativa")
            self._apply_pending_memory_limits()
            resuming = self.paused and bool(self.current_session)
            processes = self.process_reader(DEFAULT_PORTS)
            emulators = self.emulator_reader(DEFAULT_PORTS)
            if not processes and not emulators:
                raise RuntimeError("Abra um cliente PC ou emulador e entre no jogo")
            executable, (pids, local_ports, remote_ports) = max(
                processes.items(), key=lambda item: len(item[1][0])
            ) if processes else ("", (set(), set(), set()))
            emulator_executable, (emulator_pids, emulator_local, emulator_remote) = max(
                emulators.items(), key=lambda item: len(item[1][0])
            ) if emulators else ("", (set(), set(), set()))
            _enforce_connection_limits(claims, len(pids), len(emulator_pids))
            routes = self.client_reader(executable, DEFAULT_PORTS) if executable else []
            emulator_routes = (
                self.client_reader(emulator_executable, DEFAULT_PORTS)
                if emulator_executable else []
            )
            _require_distinct_client_routes(routes, pids, "PC")
            _require_distinct_client_routes(
                emulator_routes, emulator_pids, "emuladores"
            )
            self.executable = executable
            self.emulator_executable = emulator_executable
            known_pids = [*self.pc_client_pids, *self.emulator_client_pids]
            active_pids = {*pids, *emulator_pids}
            self.route_identity_trusted = bool(
                not resuming
                or known_pids and set(known_pids).intersection(active_pids)
                or routes
                or emulator_routes
            )
            if self.route_identity_trusted:
                self.pc_client_pids, groups = _merge_client_routes(
                    self.pc_client_pids if resuming else [], [],
                    routes,
                )
                self.emulator_client_pids, emulator_groups = _merge_client_routes(
                    self.emulator_client_pids if resuming else [], [],
                    emulator_routes,
                    5,
                )
                self.pc_client_ports = tuple(groups) or (
                    (tuple(sorted(local_ports)),) if local_ports else ()
                )
                self.emulator_client_ports = tuple(emulator_groups) or (
                    (tuple(sorted(emulator_local)),) if emulator_local else ()
                )
            else:
                self.pc_client_pids = []
                self.emulator_client_pids = []
                self.pc_client_ports = ()
                self.emulator_client_ports = ()
            self._sync_client_routes()
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
            ports = _stable_capture_ports((*routes, *emulator_routes))
            self.capture_ports = ports
            capture = self.capture_factory(self.capture_directory)
            if capture.system_running():
                raise RuntimeError(
                    "Outra captura PktMon já está ativa em outra sessão do RF QOL. "
                    "Encerre-a pelo programa que já está aberto antes de iniciar uma nova captura."
                )
            capture.start_for_ports(prefix, ports)
            self.capture = capture
            self.live_capture = None
            live_error = None
            web_agent_error = None
            if self.web_agent is not None:
                try:
                    self.web_agent.start_session(
                        str(self.current_session), resumed=resuming
                    )
                except Exception as error:
                    LOG.exception("web_agent_start_failed")
                    web_agent_error = f"{type(error).__name__}: {error}"
            try:
                self.live_events.clear()
                self.map_module.reset()
                self.live_events.start()
                live = _realtime_capture(
                    self.live_factory,
                    self._next_live_target(),
                    tuple(dict.fromkeys((*DEFAULT_PORTS, *ports))),
                    self.memory_limits,
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
                "capture_pc_client_pids": list(self.pc_client_pids),
                "capture_emulator_client_pids": list(self.emulator_client_pids),
                "clients": len(pids) + len(emulator_pids),
                "pc_clients": len(pids),
                "emulators": len(emulator_pids),
                "connections": len(local_ports) + len(emulator_local),
                "live": self.live_capture is not None,
                "live_error": live_error,
                "web_agent_active": bool(
                    self.web_agent is not None and web_agent_error is None
                ),
                "web_agent_error": web_agent_error,
                "web_agent_health": self.web_agent_health(),
                "resumed": resuming,
            }

    def start_new(self) -> dict[str, object]:
        """Finaliza a sessão recuperável atual e começa uma sessão independente."""
        with self._lock:
            previous_session = self.current_session
            if self.active:
                raise RuntimeError("Encerre ou pause a captura ativa antes de começar outra")
            if previous_session:
                finalized = self.stop(pause=False)
                failures = list(finalized.get("failures") or [])
                if failures:
                    raise RuntimeError(
                        "A sessão anterior não pôde ser finalizada; ela foi preservada para nova tentativa"
                    )
            result = self.start()
            result["previous_session"] = previous_session
            result["resumed"] = False
            return result

    def _refresh_routes(self) -> None:
        if not self.executable:
            processes = self.process_reader(DEFAULT_PORTS)
            if processes:
                self.executable, _details = max(
                    processes.items(), key=lambda item: len(item[1][0])
                )
        if not self.emulator_executable:
            emulators = self.emulator_reader(DEFAULT_PORTS)
            if emulators:
                self.emulator_executable, _details = max(
                    emulators.items(), key=lambda item: len(item[1][0])
                )
        routes = self.client_reader(self.executable, DEFAULT_PORTS) if self.executable else []
        emulator_routes = (
            self.client_reader(self.emulator_executable, DEFAULT_PORTS)
            if self.emulator_executable else []
        )
        claims = self.license.require("limites de conexão")
        _enforce_connection_limits(
            claims,
            len({int(route["pid"]) for route in routes}),
            len({int(route["pid"]) for route in emulator_routes}),
        )
        active_pc_pids = {int(route["pid"]) for route in routes}
        active_emulator_pids = {
            int(route["pid"]) for route in emulator_routes
        }
        pc_replaced = bool(
            self.pc_client_pids
            and active_pc_pids
            and active_pc_pids.isdisjoint(self.pc_client_pids)
        )
        emulator_replaced = bool(
            self.emulator_client_pids
            and active_emulator_pids
            and active_emulator_pids.isdisjoint(self.emulator_client_pids)
        )
        if self.route_identity_trusted and pc_replaced:
            self.pc_client_pids = []
            self.pc_client_ports = ()
        if self.route_identity_trusted and emulator_replaced:
            self.emulator_client_pids = []
            self.emulator_client_ports = ()
        # Ao retomar uma captura, PIDs e portas locais podem ter expirado. Uma
        # rota atual observada pelo processo do jogo recupera os slots físicos;
        # o CaptureStore confirma a identidade lógica pelo UID canônico antes
        # de atribuir definitivamente os eventos ao cliente.
        if not self.route_identity_trusted and (routes or emulator_routes):
            self.pc_client_pids = []
            self.emulator_client_pids = []
            self.pc_client_ports = ()
            self.emulator_client_ports = ()
            self.route_identity_trusted = True
        if self.route_identity_trusted:
            self.pc_client_pids, groups = _merge_client_routes(
                self.pc_client_pids, list(self.pc_client_ports), routes
            )
            self.emulator_client_pids, emulator_groups = _merge_client_routes(
                self.emulator_client_pids,
                list(self.emulator_client_ports),
                emulator_routes,
                5,
            )
            self.pc_client_ports = tuple(groups)
            self.emulator_client_ports = tuple(emulator_groups)
        self._sync_client_routes()
        ports = _stable_capture_ports((*routes, *emulator_routes))
        if ports and self.capture:
            self.capture.add_ports(ports)
            self.capture_ports = tuple(dict.fromkeys((*self.capture_ports, *ports)))
        if ports and self.live_capture:
            self.live_capture.add_ports(ports)

    def heartbeat(self) -> None:
        try:
            self.license.require("captura")
        except PermissionError:
            if self.active:
                self.stop_without_reading()
            raise
        if self.capture:
            self.capture.heartbeat()

    def bytes_written(self) -> int:
        files = list(self.capture.segment_files()) if self.capture else []
        files.extend(self.live_files)
        if self.live_capture:
            files.append(self.live_capture.target)
        return sum(path.stat().st_size for path in dict.fromkeys(files) if path.exists())

    def read_live(self) -> dict[str, object]:
        self.license.require("leitura de captura")
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
                            restrict_to_clients=any(self.client_ports),
                        )
                        for path in completed
                        if path.exists()
                    )
                    checkpoint = store.checkpoint_session(
                        self.current_session, reason="interval"
                    )
                finally:
                    store.close()
                return {
                    "added": added,
                    "available": True,
                    "fallback": True,
                    "capture_prefix": prefix,
                    "capture_ports": list(self.capture_ports),
                    "checkpoint": checkpoint,
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
                    restrict_to_clients=any(self.client_ports),
                )
                checkpoint = store.checkpoint_session(
                    self.current_session, reason="interval"
                )
            finally:
                store.close()
            return {
                "added": added,
                "available": True,
                "bytes": target.stat().st_size,
                "checkpoint": checkpoint,
            }

    def preview_live(self) -> dict[str, object]:
        """Entrega eventos efêmeros já lidos da RAM, sem reler o PCAP."""
        self.license.require("processamento de captura")
        with self._lock:
            if not self.current_session or not self.live_capture:
                return {"added": 0, "available": False, "fast": False}
            self._refresh_routes()
            self.live_events.start()
            events = self.live_events.snapshot()
            metrics = dict(self.live_events.metrics())
            metrics["memory_budget_mb"] = self.memory_budget_mb
            for name in (
                "received_packets",
                "filtered_packets",
                "duplicate_packets",
                "missed_write",
                "missed_read",
                "write_queue_depth",
                "write_queue_limit",
                "write_queue_bytes",
                "write_queue_byte_limit",
                "dropped_write_packets",
                "dropped_write_bytes",
            ):
                metrics[name] = int(getattr(self.live_capture, name, 0) or 0)
            return {
                "added": len(events),
                "available": True,
                "fast": True,
                "events": events,
                "client_ports": [list(group) for group in self.client_ports],
                "client_pids": list(self.client_pids),
                "pc_client_pids": list(self.pc_client_pids),
                "emulator_client_pids": list(self.emulator_client_pids),
                "map": self.map_module.snapshot(
                    events,
                    self.client_ports,
                    now_ns=time.time_ns(),
                ),
                "monitor_metrics": metrics,
                "web_agent_health": self.web_agent_health(),
            }

    def abandon(self) -> list[Path]:
        """Interrompe a captura e devolve os arquivos sem decodificá-los."""
        with self._lock:
            session_id = self.current_session
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
            if self.web_agent is not None and session_id:
                try:
                    self.web_agent.finish_session(session_id, reason="abandoned")
                except Exception:
                    LOG.exception("web_agent_finish_failed")
            self.paused = False
            self._apply_pending_memory_limits()
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
            if self.web_agent is not None:
                try:
                    self.web_agent.pause_session(
                        session_id, reason="capture_stopped_without_reading"
                    )
                except Exception:
                    LOG.exception("web_agent_pause_failed")
            self._apply_pending_memory_limits()
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
        self.license.require("processamento de captura")
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
                            restrict_to_clients=any(self.client_ports),
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
                if not failures:
                    store.checkpoint_session(
                        self.current_session,
                        reason="paused" if pause else "finalized",
                    )
            finally:
                store.close()
            if not failures:
                for path in self.live_files:
                    path.unlink(missing_ok=True)
                self.live_files.clear()
                self.pending_files.clear()
            self.paused = pause
            if not failures and self.web_agent is not None:
                try:
                    if pause:
                        self.web_agent.pause_session(session_id, reason="paused")
                    else:
                        self.web_agent.finish_session(session_id, reason="finalized")
                except Exception:
                    LOG.exception("web_agent_session_transition_failed")
            if not pause and not failures:
                self.current_session = None
            self.capture = None
            self._apply_pending_memory_limits()
            return {
                "session_id": session_id,
                "added": added,
                "failures": failures,
                "files": len(files),
                "paused": pause,
            }
