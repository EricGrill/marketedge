"""Execution realism helpers for offline prediction-market backtests."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import floor
from typing import Any, Dict, Iterable, List

from src.backtesting import BacktestTradeInput


class ExecutionModelError(ValueError):
    """Raised when an execution request or order book is invalid."""


@dataclass(frozen=True)
class OrderBookLevel:
    """Displayed quantity at one price level."""

    price: float
    quantity: int


@dataclass(frozen=True)
class OrderBookSnapshot:
    """Order book depth available for a contract."""

    bids: List[OrderBookLevel] = field(default_factory=list)
    asks: List[OrderBookLevel] = field(default_factory=list)
    recent_volume: int = 0


@dataclass(frozen=True)
class ExecutionAssumptions:
    """Conservative assumptions applied to displayed liquidity."""

    slippage_bps: float = 0.0
    queue_ahead_fraction: float = 0.0
    max_volume_participation: float = 1.0


@dataclass(frozen=True)
class ExecutionOrder:
    """Requested market action for one contract side."""

    action: str
    contract_side: str
    quantity: int
    limit_price: float | None = None


@dataclass(frozen=True)
class ExecutionFill:
    """Quantity filled at one effective price level."""

    price: float
    quantity: int

    def to_dict(self) -> Dict[str, Any]:
        return {"price": self.price, "quantity": self.quantity}


@dataclass(frozen=True)
class ExecutionResult:
    """Execution result including partial-fill detail."""

    action: str
    contract_side: str
    requested_quantity: int
    filled_quantity: int
    unfilled_quantity: int
    average_price: float
    gross_notional: float
    fills: List[ExecutionFill]

    @property
    def fully_filled(self) -> bool:
        return self.filled_quantity == self.requested_quantity

    @property
    def filled(self) -> bool:
        return self.filled_quantity > 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "contract_side": self.contract_side,
            "requested_quantity": self.requested_quantity,
            "filled_quantity": self.filled_quantity,
            "unfilled_quantity": self.unfilled_quantity,
            "average_price": self.average_price,
            "gross_notional": self.gross_notional,
            "fully_filled": self.fully_filled,
            "fills": [fill.to_dict() for fill in self.fills],
        }


class ExecutionModel:
    """Fill orders against displayed depth with slippage and queue assumptions."""

    def __init__(self, assumptions: ExecutionAssumptions | None = None):
        self.assumptions = assumptions or ExecutionAssumptions()
        self._validate_assumptions(self.assumptions)

    def fill(self, order: ExecutionOrder, book: OrderBookSnapshot) -> ExecutionResult:
        self._validate_order(order)
        levels = self._levels_for(order, book)
        remaining = order.quantity
        participation_remaining = self._participation_cap(book)
        fills: List[ExecutionFill] = []

        for level in levels:
            if remaining <= 0:
                break
            if not self._price_is_executable(order, level.price):
                continue
            available = self._available_quantity(level)
            if participation_remaining is not None:
                available = min(available, participation_remaining)
            if available <= 0:
                continue

            quantity = min(remaining, available)
            price = self._apply_slippage(order.action, level.price)
            fills.append(ExecutionFill(price=price, quantity=quantity))
            remaining -= quantity
            if participation_remaining is not None:
                participation_remaining -= quantity

        filled_quantity = sum(fill.quantity for fill in fills)
        gross_notional = sum(fill.price * fill.quantity / 100.0 for fill in fills)
        average_price = (
            sum(fill.price * fill.quantity for fill in fills) / filled_quantity
            if filled_quantity
            else 0.0
        )

        return ExecutionResult(
            action=order.action.lower(),
            contract_side=order.contract_side.lower(),
            requested_quantity=order.quantity,
            filled_quantity=filled_quantity,
            unfilled_quantity=order.quantity - filled_quantity,
            average_price=average_price,
            gross_notional=gross_notional,
            fills=fills,
        )

    def apply_to_backtest_trade(
        self, trade: BacktestTradeInput, execution: ExecutionResult
    ) -> BacktestTradeInput:
        """Return a backtest trade using filled quantity and effective entry."""
        if not execution.filled:
            raise ExecutionModelError("cannot backtest an unfilled execution")

        return replace(
            trade,
            entry_price=execution.average_price,
            quantity=execution.filled_quantity,
            metadata={
                **trade.metadata,
                "execution": execution.to_dict(),
                "requested_quantity": execution.requested_quantity,
                "filled_quantity": execution.filled_quantity,
                "unfilled_quantity": execution.unfilled_quantity,
                "effective_entry_price": execution.average_price,
            },
        )

    def _levels_for(
        self, order: ExecutionOrder, book: OrderBookSnapshot
    ) -> List[OrderBookLevel]:
        if order.action.lower() == "buy":
            return sorted(book.asks, key=lambda level: level.price)
        if order.action.lower() == "sell":
            return sorted(book.bids, key=lambda level: level.price, reverse=True)
        raise ExecutionModelError("action must be 'buy' or 'sell'")

    def _price_is_executable(self, order: ExecutionOrder, price: float) -> bool:
        if order.limit_price is None:
            return True
        if order.action.lower() == "buy":
            return price <= order.limit_price
        return price >= order.limit_price

    def _available_quantity(self, level: OrderBookLevel) -> int:
        self._validate_level(level)
        displayed_after_queue = floor(
            level.quantity * (1.0 - self.assumptions.queue_ahead_fraction)
        )
        return displayed_after_queue

    def _participation_cap(self, book: OrderBookSnapshot) -> int | None:
        if book.recent_volume <= 0:
            return None
        return floor(book.recent_volume * self.assumptions.max_volume_participation)

    def _apply_slippage(self, action: str, price: float) -> float:
        adjustment = price * self.assumptions.slippage_bps / 10_000.0
        if action.lower() == "buy":
            return min(price + adjustment, 100.0)
        return max(price - adjustment, 0.0)

    def _validate_order(self, order: ExecutionOrder) -> None:
        if order.quantity <= 0:
            raise ExecutionModelError("quantity must be positive")
        if order.contract_side.lower() not in {"yes", "no"}:
            raise ExecutionModelError("contract_side must be 'yes' or 'no'")
        if order.action.lower() not in {"buy", "sell"}:
            raise ExecutionModelError("action must be 'buy' or 'sell'")
        if order.limit_price is not None and not 0 <= order.limit_price <= 100:
            raise ExecutionModelError("limit_price must be between 0 and 100 cents")

    def _validate_level(self, level: OrderBookLevel) -> None:
        if not 0 <= level.price <= 100:
            raise ExecutionModelError(
                "book level price must be between 0 and 100 cents"
            )
        if level.quantity < 0:
            raise ExecutionModelError("book level quantity cannot be negative")

    def _validate_assumptions(self, assumptions: ExecutionAssumptions) -> None:
        if assumptions.slippage_bps < 0:
            raise ExecutionModelError("slippage_bps cannot be negative")
        if not 0 <= assumptions.queue_ahead_fraction < 1:
            raise ExecutionModelError("queue_ahead_fraction must be in [0, 1)")
        if not 0 <= assumptions.max_volume_participation <= 1:
            raise ExecutionModelError(
                "max_volume_participation must be between 0 and 1"
            )


def execute_trades(
    trades: Iterable[BacktestTradeInput],
    executions: Iterable[ExecutionResult],
) -> List[BacktestTradeInput]:
    """Apply precomputed execution results to a matching trade sequence."""
    model = ExecutionModel()
    return [
        model.apply_to_backtest_trade(trade, execution)
        for trade, execution in zip(trades, executions)
        if execution.filled
    ]
