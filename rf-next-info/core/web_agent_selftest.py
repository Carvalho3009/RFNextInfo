"""Autoteste inteiramente local do Agent Windows em modo shadow."""

from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

from core.web_agent import AgentOutbox
from core.web_agent_runtime import WebAgentOfflineRuntime


class OfflineAgentSelfTestError(RuntimeError):
    """O contrato local do Agent nao passou por uma verificacao deterministica."""


def _event(
    kind: str,
    offset: int,
    data: dict,
    *,
    flow: str,
    opcode: int,
) -> dict:
    return {
        "source": "memory://offline-self-test",
        "flow": flow,
        "stream_offset": offset,
        "bundle_seq": 0,
        "ts_ns": 1_700_000_000_000_000_000 + offset,
        "opcode": opcode,
        "type": kind,
        "data": data,
    }


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OfflineAgentSelfTestError(message)


def run_offline_agent_self_test(
    state_dir: Path,
    installation_id: str,
    *,
    version: str = "offline-self-test",
) -> dict[str, object]:
    """Simula dois clientes e duas sessoes sem URL ou objeto de transporte."""
    state_dir = Path(state_dir)
    runtime = WebAgentOfflineRuntime.create(
        state_dir,
        installation_id,
        version=version,
        max_outbox_events=128,
        max_outbox_bytes=2 * 1024 * 1024,
        max_queue_events=64,
    )
    session_a = "offline-session-a"
    session_b = "offline-session-b"
    flow_a = "10.0.0.1:51001 -> 10.0.0.2:12020"
    flow_b = "10.0.0.1:51002 -> 10.0.0.2:12020"
    try:
        runtime.start_session(session_a)
        _require(runtime.submit(_event(
            "world_info_prefix", 1,
            {"fields": {
                "character_uid": 101,
                "character_name": "Cliente A",
                "level": 60,
            }},
            flow=flow_a, opcode=0x0106,
        )), "identidade do primeiro cliente rejeitada")
        _require(runtime.submit(_event(
            "update_exp", 2,
            {"level": 60, "exp": 1000, "gain_exp": 100},
            flow=flow_a, opcode=0x0307,
        )), "EXP do primeiro cliente rejeitada")
        _require(runtime.submit(_event(
            "world_info_prefix", 3,
            {"fields": {
                "character_uid": 202,
                "character_name": "Cliente B",
                "level": 61,
            }},
            flow=flow_b, opcode=0x0106,
        )), "identidade do segundo cliente rejeitada")
        _require(runtime.submit(_event(
            "realm_contribution_update", 4,
            {"contribution_total": 500},
            flow=flow_b, opcode=0x0307,
        )), "contribuicao do segundo cliente rejeitada")
        _require(not runtime.submit(_event(
            "world_info_prefix", 5, {}, flow=flow_a, opcode=0x0101,
        )), "opcode sensivel foi aceito")
        runtime.pause_session(session_a)

        runtime.start_session(session_a, resumed=True)
        _require(runtime.submit(_event(
            "update_exp", 6,
            {"level": 60, "exp": 1200, "gain_exp": 200},
            flow=flow_a, opcode=0x0307,
        )), "evento apos retomada rejeitado")
        runtime.finish_session(session_a, reason="finalized")

        runtime.start_session(session_b)
        _require(runtime.submit(_event(
            "world_info_prefix", 7,
            {"fields": {
                "character_uid": 303,
                "character_name": "Cliente C",
                "level": 62,
            }},
            flow=flow_a, opcode=0x0106,
        )), "identidade da segunda sessao rejeitada")
        runtime.finish_session(session_b, reason="abandoned")
        runtime.bridge.wait_until_idle()
        health_before_close = runtime.health()
    finally:
        runtime.close()

    outbox = AgentOutbox(
        state_dir / "web-agent-outbox.sqlite3",
        installation_id,
        max_events=128,
        max_bytes=2 * 1024 * 1024,
    )
    try:
        rows = outbox.conn.execute(
            "SELECT document FROM outbox_events ORDER BY sequence"
        ).fetchall()
        events = [json.loads(bytes(row[0]).decode("utf-8")) for row in rows]
        serialized = json.dumps(events, ensure_ascii=False).lower()
        lifecycle = [
            event["payload"]["state"]
            for event in events
            if event["type"] == "session.lifecycle"
        ]
        session_refs = {event["session_ref"] for event in events}
        client_refs = {
            event["client_ref"] for event in events if event["client_ref"]
        }
        expected_lifecycle = [
            "started", "paused", "resumed", "finished", "started", "abandoned"
        ]
        _require(
            lifecycle == expected_lifecycle,
            f"ciclo de sessoes fora de ordem: {lifecycle!r}",
        )
        _require(len(session_refs) == 2, "sessoes nao foram isoladas")
        _require(len(client_refs) >= 3, "clientes nao foram isolados")
        _require(session_a not in serialized and session_b not in serialized,
                 "identificador local de sessao vazou")
        _require("0x0101" not in serialized, "opcode sensivel persistido")
        _require(health_before_close.get("mode") == "offline",
                 "runtime nao estava em modo offline")
        _require("delivery" not in health_before_close,
                 "componente de entrega criado no modo offline")
        metrics = outbox.metrics()
        return {
            "ok": True,
            "mode": "offline",
            "network_used": False,
            "events": metrics["events"],
            "session_lifecycle_events": len(lifecycle),
            "isolated_sessions": len(session_refs),
            "isolated_clients": len(client_refs),
            "outbox_bytes": metrics["bytes"],
            "queue_errors": health_before_close["capture_bridge"]["errors"],
            "checked_at_ns": time.time_ns(),
        }
    finally:
        outbox.close()


def run_offline_agent_stress_test(
    state_dir: Path,
    installation_id: str,
    *,
    sessions: int = 3,
    clients: int = 4,
    events_per_client: int = 50,
    version: str = "offline-stress-test",
) -> dict[str, object]:
    """Exercita volume local limitado sem criar qualquer componente de rede."""
    sessions = int(sessions)
    clients = int(clients)
    events_per_client = int(events_per_client)
    if not 1 <= sessions <= 100:
        raise ValueError("sessions fora do limite de teste")
    if not 1 <= clients <= 32:
        raise ValueError("clients fora do limite de teste")
    if not 1 <= events_per_client <= 10_000:
        raise ValueError("events_per_client fora do limite de teste")
    expected_events = sessions * (2 + clients * (1 + events_per_client))
    if expected_events > 250_000:
        raise ValueError("teste excede o limite total de eventos")

    state_dir = Path(state_dir)
    tracemalloc.start()
    started_at = time.perf_counter()
    runtime: WebAgentOfflineRuntime | None = None
    try:
        runtime = WebAgentOfflineRuntime.create(
            state_dir,
            installation_id,
            version=version,
            max_outbox_events=expected_events + 8,
            max_outbox_bytes=max(2 * 1024 * 1024, expected_events * 2048),
            max_queue_events=max(256, min(4096, expected_events + 8)),
        )
        offset = 0
        for session_index in range(sessions):
            session_id = f"offline-stress-session-{session_index}"
            runtime.start_session(session_id)
            for client_index in range(clients):
                flow = (
                    f"10.0.{session_index}.1:{51000 + client_index} -> "
                    "10.0.0.2:12020"
                )
                offset += 1
                _require(runtime.submit(_event(
                    "world_info_prefix", offset,
                    {"fields": {
                        "character_uid": 10_000 + client_index,
                        "character_name": f"Cliente {client_index}",
                        "level": 60 + client_index,
                    }},
                    flow=flow, opcode=0x0106,
                )), "identidade rejeitada no teste de pressao")
                for event_index in range(events_per_client):
                    offset += 1
                    _require(runtime.submit(_event(
                        "update_exp", offset,
                        {
                            "level": 60 + client_index,
                            "exp": event_index * 100,
                            "gain_exp": 100,
                        },
                        flow=flow, opcode=0x0307,
                    )), "evento rejeitado no teste de pressao")
            runtime.finish_session(session_id, reason="finalized")
        runtime.bridge.wait_until_idle()
        health = runtime.health()
        _require(
            int(health["capture_bridge"]["errors"]) == 0,
            "fila registrou erro no teste de pressao",
        )
        _require(
            int(health["capture_bridge"]["dropped"]) == 0,
            "fila descartou evento no teste de pressao",
        )
    finally:
        try:
            if runtime is not None:
                runtime.close()
        finally:
            _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
            tracemalloc.stop()

    outbox = AgentOutbox(
        state_dir / "web-agent-outbox.sqlite3",
        installation_id,
        max_events=expected_events + 8,
        max_bytes=max(2 * 1024 * 1024, expected_events * 2048),
    )
    try:
        metrics = outbox.metrics()
        _require(
            int(metrics["events"]) == expected_events,
            "quantidade persistida diverge do volume submetido",
        )
        elapsed = max(0.000001, time.perf_counter() - started_at)
        return {
            "ok": True,
            "mode": "offline",
            "network_used": False,
            "sessions": sessions,
            "clients": clients,
            "events": metrics["events"],
            "outbox_bytes": metrics["bytes"],
            "peak_traced_memory_bytes": peak_bytes,
            "elapsed_seconds": round(elapsed, 6),
            "events_per_second": round(expected_events / elapsed, 2),
            "queue_errors": 0,
            "queue_dropped": 0,
        }
    finally:
        outbox.close()
