"""Append-only order lifecycle ledger for strategy execution."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List

from src.utils import ensure_utc, parse_timestamp, utcnow


class OrderLedgerError(ValueError):
    """Raised when an order lifecycle event is invalid."""


class OrderState(str, Enum):
    PENDING = "pending"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


TERMINAL_STATES = {
    OrderState.FILLED,
    OrderState.CANCELLED,
    OrderState.REJECTED,
    OrderState.EXPIRED,
}


@dataclass(frozen=True)
class OrderEvent:
    """One append-only lifecycle event for a venue order."""

    order_id: str
    event_type: str
    quantity: int
    price: float | None
    timestamp: datetime
    detail: str = ""
    ticker: str = ""
    side: str = ""
    action: str = ""
    order_type: str = ""
    limit_price: float | None = None

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "event_type": self.event_type,
            "quantity": self.quantity,
            "price": self.price,
            "timestamp": ensure_utc(self.timestamp).isoformat(),
            "detail": self.detail,
            "ticker": self.ticker,
            "side": self.side,
            "action": self.action,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "OrderEvent":
        return cls(
            order_id=str(payload["order_id"]),
            event_type=str(payload["event_type"]).lower(),
            quantity=int(payload.get("quantity") or 0),
            price=(
                None
                if payload.get("price") is None
                else float(payload.get("price") or 0.0)
            ),
            timestamp=parse_timestamp(str(payload["timestamp"])),
            detail=str(payload.get("detail") or ""),
            ticker=str(payload.get("ticker") or ""),
            side=str(payload.get("side") or "").lower(),
            action=str(payload.get("action") or "").lower(),
            order_type=str(payload.get("order_type") or "").lower(),
            limit_price=(
                None
                if payload.get("limit_price") is None
                else float(payload.get("limit_price") or 0.0)
            ),
        )


@dataclass(frozen=True)
class OrderRecord:
    """Folded current view of an order event stream."""

    order_id: str
    ticker: str
    side: str
    action: str
    order_type: str
    limit_price: float | None
    requested_quantity: int
    filled_quantity: int
    average_fill_price: float | None
    state: OrderState
    created_at: datetime
    updated_at: datetime
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "ticker": self.ticker,
            "side": self.side,
            "action": self.action,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "average_fill_price": self.average_fill_price,
            "state": self.state.value,
            "created_at": ensure_utc(self.created_at).isoformat(),
            "updated_at": ensure_utc(self.updated_at).isoformat(),
            "reason": self.reason,
        }


def apply_event(record: OrderRecord | None, event: OrderEvent) -> OrderRecord:
    """Apply one event to an optional current record and return the next record."""
    event_type = event.event_type.lower()
    if event_type == "submitted":
        if record is not None:
            raise OrderLedgerError("order has already been submitted")
        _validate_submitted_event(event)
        return OrderRecord(
            order_id=event.order_id,
            ticker=event.ticker,
            side=event.side,
            action=event.action,
            order_type=event.order_type,
            limit_price=event.limit_price,
            requested_quantity=event.quantity,
            filled_quantity=0,
            average_fill_price=None,
            state=OrderState.PENDING,
            created_at=ensure_utc(event.timestamp),
            updated_at=ensure_utc(event.timestamp),
        )

    if record is None:
        raise OrderLedgerError("order must be submitted before lifecycle events")
    if record.state in TERMINAL_STATES:
        raise OrderLedgerError(f"cannot apply {event_type} after {record.state.value}")

    if event_type == "fill":
        return _apply_fill(record, event)
    if event_type == "rejected":
        _require_state(record, {OrderState.PENDING}, event_type)
        return _terminal_record(record, event, OrderState.REJECTED)
    if event_type == "cancelled":
        _require_state(
            record,
            {OrderState.PENDING, OrderState.PARTIALLY_FILLED},
            event_type,
        )
        return _terminal_record(record, event, OrderState.CANCELLED)
    if event_type == "expired":
        _require_state(
            record,
            {OrderState.PENDING, OrderState.PARTIALLY_FILLED},
            event_type,
        )
        return _terminal_record(record, event, OrderState.EXPIRED)

    raise OrderLedgerError(f"unsupported order event type: {event_type}")


class OrderLedger:
    """Read and write local order lifecycle events."""

    def __init__(self, path: str | Path = "data/orders.jsonl"):
        self.path = Path(path)

    def submit(
        self,
        order_id: str,
        ticker: str,
        side: str,
        action: str,
        order_type: str,
        requested_quantity: int,
        limit_price: float | None = None,
        *,
        at=None,
    ) -> OrderRecord:
        event = OrderEvent(
            order_id=order_id,
            event_type="submitted",
            quantity=requested_quantity,
            price=None,
            timestamp=at or utcnow(),
            ticker=ticker,
            side=side.lower(),
            action=action.lower(),
            order_type=order_type.lower(),
            limit_price=limit_price,
        )
        apply_event(self.get(order_id), event)
        self.append(event)
        return self.get_or_raise(order_id)

    def record_fill(
        self,
        order_id: str,
        quantity: int,
        price: float,
        *,
        at=None,
    ) -> OrderRecord:
        return self._append_and_get(
            OrderEvent(
                order_id=order_id,
                event_type="fill",
                quantity=quantity,
                price=price,
                timestamp=at or utcnow(),
            )
        )

    def reject(self, order_id: str, reason: str = "", *, at=None) -> OrderRecord:
        return self._terminal(order_id, "rejected", reason, at=at)

    def cancel(self, order_id: str, reason: str = "", *, at=None) -> OrderRecord:
        return self._terminal(order_id, "cancelled", reason, at=at)

    def expire(self, order_id: str, reason: str = "", *, at=None) -> OrderRecord:
        return self._terminal(order_id, "expired", reason, at=at)

    def append(self, event: OrderEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(event.to_dict(), handle, sort_keys=True)
            handle.write("\n")

    def events(self) -> List[OrderEvent]:
        if not self.path.exists():
            return []
        events: List[OrderEvent] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(OrderEvent.from_dict(json.loads(line)))
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise OrderLedgerError(
                        f"invalid order ledger event on line {line_number}"
                    ) from exc
        return events

    def get(self, order_id: str) -> OrderRecord | None:
        records = self._fold()
        return records.get(order_id)

    def get_or_raise(self, order_id: str) -> OrderRecord:
        record = self.get(order_id)
        if record is None:
            raise OrderLedgerError("order not found")
        return record

    def open_orders(self) -> List[OrderRecord]:
        return [
            record
            for record in self._fold().values()
            if record.state not in TERMINAL_STATES
        ]

    def reconcile_timeouts(self, ttl_seconds: int, *, now=None) -> List[OrderRecord]:
        if ttl_seconds < 0:
            raise OrderLedgerError("ttl_seconds cannot be negative")
        current = ensure_utc(now or utcnow())
        expired: List[OrderRecord] = []
        for record in self.open_orders():
            age_seconds = (current - ensure_utc(record.created_at)).total_seconds()
            if age_seconds >= ttl_seconds:
                expired.append(
                    self.expire(
                        record.order_id,
                        reason=f"expired after {ttl_seconds}s",
                        at=current,
                    )
                )
        return expired

    def _append_and_get(self, event: OrderEvent) -> OrderRecord:
        next_record = apply_event(self.get(event.order_id), event)
        self.append(event)
        return next_record

    def _terminal(self, order_id: str, event_type: str, reason: str, *, at=None):
        return self._append_and_get(
            OrderEvent(
                order_id=order_id,
                event_type=event_type,
                quantity=0,
                price=None,
                timestamp=at or utcnow(),
                detail=reason,
            )
        )

    def _fold(self) -> dict[str, OrderRecord]:
        records: dict[str, OrderRecord] = {}
        for event in self.events():
            records[event.order_id] = apply_event(records.get(event.order_id), event)
        return records


def _apply_fill(record: OrderRecord, event: OrderEvent) -> OrderRecord:
    _require_state(record, {OrderState.PENDING, OrderState.PARTIALLY_FILLED}, "fill")
    if event.quantity <= 0:
        raise OrderLedgerError("fill quantity must be positive")
    if event.price is None or not 0 <= event.price <= 100:
        raise OrderLedgerError("fill price must be between 0 and 100 cents")

    filled_quantity = record.filled_quantity + event.quantity
    if filled_quantity > record.requested_quantity:
        raise OrderLedgerError("fill quantity exceeds requested quantity")

    previous_notional = (record.average_fill_price or 0.0) * record.filled_quantity
    average_fill_price = (
        previous_notional + event.price * event.quantity
    ) / filled_quantity
    state = (
        OrderState.FILLED
        if filled_quantity == record.requested_quantity
        else OrderState.PARTIALLY_FILLED
    )
    return replace(
        record,
        filled_quantity=filled_quantity,
        average_fill_price=average_fill_price,
        state=state,
        updated_at=ensure_utc(event.timestamp),
    )


def _terminal_record(
    record: OrderRecord, event: OrderEvent, state: OrderState
) -> OrderRecord:
    if event.quantity:
        raise OrderLedgerError(f"{event.event_type} event quantity must be zero")
    return replace(
        record,
        state=state,
        updated_at=ensure_utc(event.timestamp),
        reason=event.detail,
    )


def _require_state(
    record: OrderRecord, allowed: set[OrderState], event_type: str
) -> None:
    if record.state not in allowed:
        allowed_names = ", ".join(sorted(state.value for state in allowed))
        raise OrderLedgerError(
            f"cannot apply {event_type} to {record.state.value}; expected {allowed_names}"
        )


def _validate_submitted_event(event: OrderEvent) -> None:
    if not event.order_id:
        raise OrderLedgerError("order_id is required")
    if not event.ticker:
        raise OrderLedgerError("ticker is required")
    if event.side not in {"yes", "no"}:
        raise OrderLedgerError("side must be 'yes' or 'no'")
    if event.action not in {"buy", "sell"}:
        raise OrderLedgerError("action must be 'buy' or 'sell'")
    if event.order_type not in {"limit", "market"}:
        raise OrderLedgerError("order_type must be 'limit' or 'market'")
    if event.quantity <= 0:
        raise OrderLedgerError("requested quantity must be positive")
    if event.limit_price is not None and not 0 <= event.limit_price <= 100:
        raise OrderLedgerError("limit_price must be between 0 and 100 cents")
