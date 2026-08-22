"""Autoteste inteiramente local do Agent Windows em modo shadow."""

from __future__ import annotations

import json
import time
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
