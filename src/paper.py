"""Append-only paper trading ledger for no-account dry runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List
from uuid import uuid4


class PaperLedgerError(ValueError):
    """Raised when a paper-trading event is invalid."""


@dataclass(frozen=True)
class PaperEvent:
    """One append-only paper trading event."""

    event_id: str
    event_type: str
    timestamp: datetime
    ticker: str
    side: str
    action: str = ""
    quantity: int = 0
    price: float = 0.0
    fee: float = 0.0
    winning_side: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "ticker": self.ticker,
            "side": self.side,
            "action": self.action,
            "quantity": self.quantity,
            "price": self.price,
            "fee": self.fee,
            "winning_side": self.winning_side,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "PaperEvent":
        return cls(
            event_id=str(payload["event_id"]),
            event_type=str(payload["event_type"]),
            timestamp=_parse_timestamp(str(payload["timestamp"])),
            ticker=str(payload["ticker"]),
            side=str(payload.get("side") or "").lower(),
            action=str(payload.get("action") or "").lower(),
            quantity=int(payload.get("quantity") or 0),
            price=float(payload.get("price") or 0.0),
            fee=float(payload.get("fee") or 0.0),
            winning_side=str(payload.get("winning_side") or "").lower(),
            note=str(payload.get("note") or ""),
        )


@dataclass(frozen=True)
class PaperPosition:
    """Computed open position from ledger events."""

    ticker: str
    side: str
    quantity: int
    average_price: float
    cost_basis: float
    realized_pnl: float
    fees: float

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "side": self.side,
            "quantity": self.quantity,
            "average_price": self.average_price,
            "cost_basis": self.cost_basis,
            "realized_pnl": self.realized_pnl,
            "fees": self.fees,
        }


@dataclass
class _PositionAccumulator:
    quantity: int = 0
    cost_basis: float = 0.0
    realized_pnl: float = 0.0
    fees: float = 0.0


class PaperTradingLedger:
    """Read and write local dry-run orders without exchange credentials."""

    def __init__(self, path: str | Path = "data/paper-ledger.jsonl"):
        self.path = Path(path)

    def record_order(
        self,
        ticker: str,
        side: str,
        action: str,
        quantity: int,
        price: float,
        fee: float = 0.0,
        note: str = "",
        timestamp: datetime | None = None,
    ) -> PaperEvent:
        side = side.lower()
        action = action.lower()
        _validate_side(side)
        _validate_action(action)
        _validate_quantity(quantity)
        _validate_price(price)
        if fee < 0:
            raise PaperLedgerError("fee cannot be negative")
        if action == "sell":
            current = self.positions().get((ticker, side))
            if not current or current.quantity < quantity:
                raise PaperLedgerError("cannot sell more contracts than are open")

        event = PaperEvent(
            event_id=_event_id("ord"),
            event_type="order",
            timestamp=timestamp or _now(),
            ticker=ticker,
            side=side,
            action=action,
            quantity=quantity,
            price=price,
            fee=fee,
            note=note,
        )
        self.append(event)
        return event

    def settle(
        self,
        ticker: str,
        winning_side: str,
        note: str = "",
        timestamp: datetime | None = None,
    ) -> PaperEvent:
        winning_side = winning_side.lower()
        _validate_side(winning_side)
        event = PaperEvent(
            event_id=_event_id("set"),
            event_type="settlement",
            timestamp=timestamp or _now(),
            ticker=ticker,
            side=winning_side,
            winning_side=winning_side,
            note=note,
        )
        self.append(event)
        return event

    def append(self, event: PaperEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            json.dump(event.to_dict(), handle, sort_keys=True)
            handle.write("\n")

    def events(self) -> List[PaperEvent]:
        if not self.path.exists():
            return []
        events: List[PaperEvent] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    events.append(PaperEvent.from_dict(json.loads(line)))
                except (KeyError, TypeError, json.JSONDecodeError) as exc:
                    raise PaperLedgerError(
                        f"invalid paper ledger event on line {line_number}"
                    ) from exc
        return events

    def positions(self) -> Dict[tuple[str, str], PaperPosition]:
        accumulators = _accumulate(self.events())
        positions: Dict[tuple[str, str], PaperPosition] = {}
        for key, acc in accumulators.items():
            if acc.quantity <= 0:
                continue
            average_price = acc.cost_basis / acc.quantity * 100.0
            positions[key] = PaperPosition(
                ticker=key[0],
                side=key[1],
                quantity=acc.quantity,
                average_price=average_price,
                cost_basis=acc.cost_basis,
                realized_pnl=acc.realized_pnl,
                fees=acc.fees,
            )
        return positions

    def summary(self) -> dict:
        events = self.events()
        accumulators = _accumulate(events)
        open_positions = [position.to_dict() for position in self.positions().values()]
        realized_pnl = sum(acc.realized_pnl for acc in accumulators.values())
        fees = sum(acc.fees for acc in accumulators.values())
        return {
            "event_count": len(events),
            "open_positions": open_positions,
            "realized_pnl": realized_pnl,
            "fees": fees,
        }


def _accumulate(
    events: Iterable[PaperEvent],
) -> Dict[tuple[str, str], _PositionAccumulator]:
    accumulators: Dict[tuple[str, str], _PositionAccumulator] = {}
    for event in events:
        if event.event_type == "order":
            key = (event.ticker, event.side)
            acc = accumulators.setdefault(key, _PositionAccumulator())
            acc.fees += event.fee
            if event.action == "buy":
                acc.quantity += event.quantity
                acc.cost_basis += event.price * event.quantity / 100.0
                acc.realized_pnl -= event.fee
            elif event.action == "sell":
                if event.quantity > acc.quantity:
                    raise PaperLedgerError("ledger contains sell above open quantity")
                avg_cost = acc.cost_basis / acc.quantity if acc.quantity else 0.0
                proceeds = event.price * event.quantity / 100.0
                acc.realized_pnl += proceeds - (avg_cost * event.quantity) - event.fee
                acc.cost_basis -= avg_cost * event.quantity
                acc.quantity -= event.quantity
        elif event.event_type == "settlement":
            for key, acc in list(accumulators.items()):
                if key[0] != event.ticker or acc.quantity <= 0:
                    continue
                settlement_price = 100.0 if key[1] == event.winning_side else 0.0
                proceeds = settlement_price * acc.quantity / 100.0
                acc.realized_pnl += proceeds - acc.cost_basis
                acc.cost_basis = 0.0
                acc.quantity = 0
    return accumulators


def _validate_side(side: str) -> None:
    if side not in {"yes", "no"}:
        raise PaperLedgerError("side must be 'yes' or 'no'")


def _validate_action(action: str) -> None:
    if action not in {"buy", "sell"}:
        raise PaperLedgerError("action must be 'buy' or 'sell'")


def _validate_quantity(quantity: int) -> None:
    if quantity <= 0:
        raise PaperLedgerError("quantity must be positive")


def _validate_price(price: float) -> None:
    if not 0 <= price <= 100:
        raise PaperLedgerError("price must be between 0 and 100 cents")


def _event_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
