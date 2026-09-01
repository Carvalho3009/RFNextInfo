"""Projeção sanitizada das vendas próprias observadas no leilão."""

from __future__ import annotations

import base64
import hashlib
import hmac
from typing import Any, Iterable, Mapping


ACTIVE_LIST = "FL2C_ans_exchange_for_my_sales_list_Message"
SETTLEMENT_LIST = "FL2C_ans_exchange_for_my_settlement_list_Message"
REGISTERED = "FL2C_respond_to_registration_of_sale_item_on_exchange_Message"
REREGISTERED = "FL2C_respond_to_reregistration_of_sale_item_on_exchange_Message"
CANCELLED = "FL2C_respond_to_cancellation_of_sale_item_on_exchange_Message"
SOLD = "FL2C_notify_exchange_item_sell_Message"
SETTLED = "FL2C_respond_settlement_of_exchange_Message"
TRANSACTION_HISTORY = "FL2C_ans_exchange_for_my_transaction_history_Message"
PURCHASED = "FL2C_respond_to_purchase_item_on_exchange_Message"

AUCTION_EVENT_TYPES = (
    ACTIVE_LIST,
    SETTLEMENT_LIST,
    REGISTERED,
    REREGISTERED,
    CANCELLED,
    SOLD,
    SETTLED,
    TRANSACTION_HISTORY,
    PURCHASED,
)


def _integer(value: object, *, minimum: int = 0, maximum: int = 2**64 - 1) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if minimum <= result <= maximum else None


def _payload(event: object) -> tuple[dict[str, Any], int | None]:
    if not isinstance(event, dict):
        return {}, None
    nested = event.get("data")
    data = nested if isinstance(nested, dict) and nested.get("message") else event
    observed_at_ns = _integer(event.get("ts_ns"), maximum=2**63 - 1)
    return data, observed_at_ns


def _opaque_listing_id(secret: bytes, server_type: int, exchange_index: int) -> str:
    digest = hmac.new(
        secret,
        f"rf-qol.auction/v1:{server_type}:{exchange_index}".encode(),
        hashlib.sha256,
    ).digest()[:18]
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _entry_fields(entry: object) -> dict[str, int | None]:
    if not isinstance(entry, dict):
        return {}
    item = entry.get("item_info")
    item = item if isinstance(item, dict) else {}
    return {
        "exchange_index": _integer(entry.get("exchange_index"), minimum=1),
        "item_index": _integer(item.get("index"), minimum=1, maximum=2**32 - 1),
        "enchant_level": _integer(item.get("enchant_level"), maximum=2**16 - 1),
        "quantity": _integer(item.get("count"), minimum=1),
        "price_per_unit": _integer(entry.get("selling_price"), minimum=1),
        "settlement_price": _integer(entry.get("settlement_price"), minimum=0),
        "registered_time": _integer(entry.get("registed_time")),
        "expires_time": _integer(entry.get("expired_time")),
        "selling_time": _integer(entry.get("selling_time")),
    }


def auction_sales_snapshot(
    events: Iterable[object],
    *,
    secret: bytes | str,
    item_names: Mapping[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Reduz eventos confirmados e remove IDs de conta, personagem e item.

    ``secret`` deve ser uma chave local protegida. Ela mantém o identificador
    estável para idempotência sem expor ``exchange_index`` ao consumidor.
    """
    key = secret.encode() if isinstance(secret, str) else bytes(secret)
    if len(key) < 16:
        raise ValueError("A chave da projeção de leilão deve ter ao menos 16 bytes")
    rows: dict[tuple[int, int], dict[str, Any]] = {}

    def touch(
        server_type: int,
        exchange_index: int,
        status: str,
        message: str,
        observed_at_ns: int | None,
        entry: object = None,
    ) -> None:
        identity = (server_type, exchange_index)
        current = rows.setdefault(identity, {
            "server_type": server_type,
            "exchange_index": exchange_index,
            "status": status,
            "source": message,
            "observed_at_ns": observed_at_ns,
        })
        fields = _entry_fields(entry)
        for name, value in fields.items():
            if name != "exchange_index" and value is not None:
                current[name] = value
        current.update({
            "status": status,
            "source": message,
            "observed_at_ns": observed_at_ns,
        })

    for raw_event in events:
        data, observed_at_ns = _payload(raw_event)
        message = str(data.get("message") or "")
        server_type = _integer(
            data.get("exchange_server_type"), maximum=2**8 - 1
        )
        if message not in AUCTION_EVENT_TYPES or server_type is None:
            continue
        if message != SOLD and data.get("ret") != 0:
            continue

        if message in {ACTIVE_LIST, SETTLEMENT_LIST}:
            field = "my_sales_list" if message == ACTIVE_LIST else "my_settlement_list"
            status = "active" if message == ACTIVE_LIST else "sold"
            for entry in data.get(field) or []:
                fields = _entry_fields(entry)
                exchange_index = fields.get("exchange_index")
                if exchange_index is not None:
                    touch(server_type, exchange_index, status, message, observed_at_ns, entry)
        elif message in {REGISTERED, REREGISTERED}:
            entry = data.get("exchange_item_info")
            exchange_index = _entry_fields(entry).get("exchange_index")
            if exchange_index is not None:
                touch(server_type, exchange_index, "active", message, observed_at_ns, entry)
        elif message == CANCELLED:
            exchange_index = _integer(data.get("exchange_index"), minimum=1)
            if exchange_index is not None:
                touch(server_type, exchange_index, "cancelled", message, observed_at_ns)
        elif message == SOLD:
            for value in data.get("exchange_indices") or []:
                exchange_index = _integer(value, minimum=1)
                if exchange_index is not None:
                    touch(server_type, exchange_index, "sold", message, observed_at_ns)
        elif message == SETTLED:
            indices = list(data.get("exchange_index_list") or [])
            indices.extend(
                entry.get("exchange_index")
                for entry in data.get("respond_settlement_infos") or []
                if isinstance(entry, dict)
            )
            for value in indices:
                exchange_index = _integer(value, minimum=1)
                if exchange_index is not None:
                    touch(server_type, exchange_index, "settled", message, observed_at_ns)

    public = []
    for (server_type, exchange_index), row in sorted(rows.items()):
        item_index = row.get("item_index")
        if item_index is None or row.get("quantity") is None or row.get("price_per_unit") is None:
            continue
        public.append({
            "listing_id": _opaque_listing_id(key, server_type, exchange_index),
            "server_type": server_type,
            "item_index": item_index,
            "item_name": str((item_names or {}).get(item_index) or "")[:120] or None,
            "enchant_level": row.get("enchant_level"),
            "quantity": row.get("quantity"),
            "price_per_unit": row.get("price_per_unit"),
            "settlement_price": row.get("settlement_price"),
            "registered_time": row.get("registered_time"),
            "expires_time": row.get("expires_time"),
            "selling_time": row.get("selling_time"),
            "status": row["status"],
            "observed_at_ns": row.get("observed_at_ns"),
            "confidence": "confirmed",
        })
    return public


def auction_transaction_history(
    events: Iterable[object],
    *,
    secret: bytes | str,
    item_names: Mapping[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Projeta compras/vendas confirmadas e preserva tipo bruto desconhecido."""
    key = secret.encode() if isinstance(secret, str) else bytes(secret)
    if len(key) < 16:
        raise ValueError("A chave da projeção de leilão deve ter ao menos 16 bytes")
    raw_events = list(events)
    rows: dict[tuple[int, int, str], dict[str, Any]] = {}

    def add(
        server_type: int,
        entry: object,
        transaction_type: str,
        observed_at_ns: int | None,
        *,
        exchange_type_raw: int | None = None,
    ) -> None:
        fields = _entry_fields(entry)
        exchange_index = fields.get("exchange_index")
        item_index = fields.get("item_index")
        if exchange_index is None or item_index is None:
            return
        identity = (server_type, exchange_index, transaction_type)
        rows[identity] = {
            "listing_id": _opaque_listing_id(key, server_type, exchange_index),
            "server_type": server_type,
            "transaction_type": transaction_type,
            "exchange_type_raw": exchange_type_raw,
            "item_index": item_index,
            "item_name": str((item_names or {}).get(item_index) or "")[:120] or None,
            "enchant_level": fields.get("enchant_level"),
            "quantity": fields.get("quantity"),
            "price_per_unit": fields.get("price_per_unit"),
            "settlement_price": fields.get("settlement_price"),
            "observed_at_ns": observed_at_ns,
            "confidence": "confirmed",
        }

    for raw_event in raw_events:
        data, observed_at_ns = _payload(raw_event)
        message = str(data.get("message") or "")
        server_type = _integer(
            data.get("exchange_server_type"), maximum=2**8 - 1
        )
        if server_type is None or data.get("ret") != 0:
            continue
        if message == PURCHASED:
            for result in data.get("purchase_results") or []:
                if not isinstance(result, dict) or result.get("ret") != 0:
                    continue
                add(
                    server_type,
                    result.get("exchange_info"),
                    "bought",
                    observed_at_ns,
                )
        elif message == TRANSACTION_HISTORY:
            for history in data.get("my_transaction_history") or []:
                if not isinstance(history, dict):
                    continue
                exchange_type = _integer(
                    history.get("exchange_type"), maximum=2**32 - 1
                )
                add(
                    server_type,
                    history.get("exchange_item_info"),
                    "unclassified",
                    observed_at_ns,
                    exchange_type_raw=exchange_type,
                )

    for sale in auction_sales_snapshot(
        raw_events, secret=key, item_names=item_names
    ):
        if sale.get("status") not in {"sold", "settled"}:
            continue
        rows[(
            int(sale["server_type"]),
            hash(str(sale["listing_id"])),
            "sold",
        )] = {
            **sale,
            "transaction_type": "sold",
            "exchange_type_raw": None,
        }
    return sorted(
        rows.values(),
        key=lambda row: int(row.get("observed_at_ns") or 0),
        reverse=True,
    )


def undercut_warning(
    candidate: Mapping[str, object], active_rows: Iterable[Mapping[str, object]]
) -> dict[str, int | bool | None]:
    """Compara somente servidor, item e refino; nunca bloqueia a ação."""
    server_type = _integer(candidate.get("server_type"), maximum=2**8 - 1)
    item_index = _integer(candidate.get("item_index"), minimum=1, maximum=2**32 - 1)
    enchant = _integer(candidate.get("enchant_level"), maximum=2**16 - 1)
    price = _integer(candidate.get("price_per_unit"), minimum=1)
    if None in {server_type, item_index, enchant, price}:
        return {"warning": False, "lowest_active_price": None, "difference": None}
    comparable = []
    for row in active_rows:
        if row.get("status") != "active":
            continue
        if (
            _integer(row.get("server_type"), maximum=2**8 - 1) == server_type
            and _integer(row.get("item_index"), minimum=1, maximum=2**32 - 1) == item_index
            and _integer(row.get("enchant_level"), maximum=2**16 - 1) == enchant
        ):
            active_price = _integer(row.get("price_per_unit"), minimum=1)
            if active_price is not None:
                comparable.append(active_price)
    lowest = min(comparable, default=None)
    warning = lowest is not None and price < lowest
    return {
        "warning": warning,
        "lowest_active_price": lowest,
        "difference": lowest - price if warning else None,
    }
