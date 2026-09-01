"""Projeção mínima e sanitizada de drops confirmados para alertas locais."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Mapping


NON_ITEM_REWARD_INDEXES = frozenset({1, 900, 1701})


def _integer(value: object, *, minimum: int = 0, maximum: int = 2**63 - 1) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if minimum <= result <= maximum else None


def _item_name(item_names: Mapping[object, object], item_index: int) -> str:
    value = item_names.get(str(item_index)) or item_names.get(item_index)
    return str(value or f"Item {item_index}").strip()[:120]


def confirmed_item_drop_alerts(
    events: Iterable[object],
    item_names: Mapping[object, object] | None = None,
) -> list[dict[str, Any]]:
    """Retorna um alerta por recompensa confirmada que contenha itens reais.

    EXP, créditos e contribuição usam índices reservados no mesmo evento e são
    removidos. IDs internos participam somente do hash de deduplicação.
    """
    names = item_names or {}
    alerts = []
    for raw in events:
        if not isinstance(raw, dict) or raw.get("type") != "drop_item_field":
            continue
        data = raw.get("data")
        if not isinstance(data, dict) or data.get("ret") != 0:
            continue
        aggregated: dict[int, dict[str, Any]] = {}
        identity_results = []
        for result in data.get("results") or []:
            if not isinstance(result, dict) or result.get("ret") != 0:
                continue
            item_index = _integer(
                result.get("item_index"), minimum=1, maximum=2**32 - 1
            )
            count = _integer(result.get("count"), minimum=1)
            if (
                item_index is None
                or count is None
                or item_index in NON_ITEM_REWARD_INDEXES
            ):
                continue
            identity_results.append({
                "item_index": item_index,
                "count": count,
                "item_id": _integer(result.get("item_id")),
                "action_code": _integer(
                    result.get("action_code"), maximum=2**16 - 1
                ),
            })
            current = aggregated.setdefault(item_index, {
                "item_index": item_index,
                "name": _item_name(names, item_index),
                "count": 0,
            })
            current["count"] += count
        if not aggregated:
            continue
        identity = {
            "client_key": str(raw.get("client_key") or ""),
            "ts_ns": _integer(raw.get("ts_ns")),
            "stream_offset": _integer(raw.get("stream_offset")),
            "bundle_seq": _integer(raw.get("bundle_seq"), maximum=2**16 - 1),
            "results": identity_results,
        }
        event_key = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:32]
        alerts.append({
            "event_key": event_key,
            "client_key": str(raw.get("client_key") or "")[:20],
            "character_name": str(raw.get("character_name") or "").strip()[:80],
            "observed_at_ns": _integer(raw.get("ts_ns")),
            "items": list(aggregated.values()),
            "confidence": "confirmed",
            "source": "server_reward_event",
        })
    return alerts


def aggregate_item_drops_by_client(
    candidates: Iterable[object],
) -> list[dict[str, Any]]:
    """Acumula itens idênticos sem misturar clientes ou personagens.

    Mantém somente totais e os limites temporais de cada grupo; assim o
    histórico exibido permanece limitado pela origem e não duplica eventos em
    memória.
    """
    grouped: dict[tuple[str, str, int], dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        client_key = str(candidate.get("client_key") or "")[:20]
        character_name = str(candidate.get("character_name") or "").strip()[:80]
        observed_at_ns = _integer(candidate.get("observed_at_ns")) or 0
        for item in candidate.get("items") or []:
            if not isinstance(item, dict):
                continue
            item_index = _integer(
                item.get("item_index"), minimum=1, maximum=2**32 - 1
            )
            count = _integer(item.get("count"), minimum=1)
            if item_index is None or count is None:
                continue
            key = (client_key, character_name, item_index)
            row = grouped.setdefault(key, {
                "client_key": client_key,
                "character_name": character_name,
                "item_index": item_index,
                "name": str(item.get("name") or f"Item {item_index}")[:120],
                "count": 0,
                "occurrences": 0,
                "first_observed_at_ns": observed_at_ns,
                "last_observed_at_ns": observed_at_ns,
            })
            row["count"] += count
            row["occurrences"] += 1
            positive_times = [
                value
                for value in (
                    int(row["first_observed_at_ns"] or 0), observed_at_ns
                )
                if value > 0
            ]
            row["first_observed_at_ns"] = min(positive_times, default=0)
            row["last_observed_at_ns"] = max(
                int(row["last_observed_at_ns"] or 0), observed_at_ns
            )
    return sorted(
        grouped.values(),
        key=lambda row: (
            -int(row["last_observed_at_ns"] or 0),
            str(row["client_key"]),
            int(row["item_index"]),
        ),
    )
