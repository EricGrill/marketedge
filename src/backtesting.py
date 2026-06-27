"""Offline backtesting primitives for prediction-market strategies."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Dict, Iterable, List

from src.utils import parse_timestamp


def _json_safe_float(value: float) -> float | None:
    if math.isfinite(value):
        return value
    return None


@dataclass(frozen=True)
class BacktestTradeInput:
    """Trade replay input for one prediction-market contract."""

    timestamp: datetime
    ticker: str
    side: str
    entry_price: float
    exit_price: float
    quantity: int
    model_probability: float
    confidence: float = 1.0
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestTradeResult:
    """Computed ledger row for one replayed trade."""

    timestamp: datetime
    ticker: str
    side: str
    entry_price: float
    exit_price: float
    quantity: int
    model_probability: float
    confidence: float
    market_probability: float
    edge: float
    entry_cost: float
    exit_value: float
    gross_pnl: float
    fees: float
    net_pnl: float
    return_on_risk: float
    won: bool
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EquityPoint:
    """Equity state after one trade is applied."""

    timestamp: datetime
    equity: float
    trade_pnl: float
    drawdown_pct: float


@dataclass(frozen=True)
class BacktestSummary:
    """Aggregate result for a replayed strategy."""

    initial_bankroll: float
    ending_bankroll: float
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    gross_pnl: float
    total_fees: float
    net_pnl: float
    return_pct: float
    max_drawdown: float
    profit_factor: float
    average_edge: float
    average_confidence: float
    sharpe_like: float
    trades: List[BacktestTradeResult]
    equity_curve: List[EquityPoint]

    def to_dict(self) -> Dict[str, Any]:
        """Return a dashboard/JSON-friendly summary."""
        return {
            "initial_bankroll": self.initial_bankroll,
            "ending_bankroll": self.ending_bankroll,
            "total_trades": self.total_trades,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": self.win_rate,
            "gross_pnl": self.gross_pnl,
            "total_fees": self.total_fees,
            "net_pnl": self.net_pnl,
            "return_pct": self.return_pct,
            "max_drawdown": self.max_drawdown,
            "profit_factor": _json_safe_float(self.profit_factor),
            "average_edge": self.average_edge,
            "average_confidence": self.average_confidence,
            "sharpe_like": _json_safe_float(self.sharpe_like),
            "trades": [
                {
                    "timestamp": trade.timestamp.isoformat(),
                    "ticker": trade.ticker,
                    "side": trade.side,
                    "entry_price": trade.entry_price,
                    "exit_price": trade.exit_price,
                    "quantity": trade.quantity,
                    "model_probability": trade.model_probability,
                    "confidence": trade.confidence,
                    "market_probability": trade.market_probability,
                    "edge": trade.edge,
                    "entry_cost": trade.entry_cost,
                    "exit_value": trade.exit_value,
                    "gross_pnl": trade.gross_pnl,
                    "fees": trade.fees,
                    "net_pnl": trade.net_pnl,
                    "return_on_risk": trade.return_on_risk,
                    "won": trade.won,
                    "metadata": trade.metadata,
                }
                for trade in self.trades
            ],
            "equity_curve": [
                {
                    "timestamp": point.timestamp.isoformat(),
                    "equity": point.equity,
                    "trade_pnl": point.trade_pnl,
                    "drawdown_pct": point.drawdown_pct,
                }
                for point in self.equity_curve
            ],
        }


class BacktestEngine:
    """Replay settled prediction-market trades into auditable metrics."""

    def run(
        self, trades: Iterable[BacktestTradeInput], initial_bankroll: float
    ) -> BacktestSummary:
        """Replay trades in timestamp order and return aggregate metrics."""
        ordered = sorted(trades, key=lambda trade: trade.timestamp)
        if initial_bankroll <= 0:
            raise ValueError("initial_bankroll must be positive")

        ledger: List[BacktestTradeResult] = []
        equity_curve: List[EquityPoint] = []
        equity = initial_bankroll
        peak_equity = initial_bankroll

        for trade in ordered:
            result = self._settle_trade(trade)
            ledger.append(result)

            equity += result.net_pnl
            peak_equity = max(peak_equity, equity)
            drawdown = 0.0
            if peak_equity > 0:
                drawdown = (peak_equity - equity) / peak_equity
            equity_curve.append(
                EquityPoint(
                    timestamp=result.timestamp,
                    equity=equity,
                    trade_pnl=result.net_pnl,
                    drawdown_pct=drawdown,
                )
            )

        return self._summarize(initial_bankroll, equity, ledger, equity_curve)

    def _settle_trade(self, trade: BacktestTradeInput) -> BacktestTradeResult:
        self._validate_trade(trade)

        market_probability = trade.entry_price / 100.0
        edge = trade.model_probability - market_probability
        entry_cost = trade.entry_price * trade.quantity / 100.0
        exit_value = trade.exit_price * trade.quantity / 100.0
        gross_pnl = exit_value - entry_cost
        fees = trade.entry_fee + trade.exit_fee
        net_pnl = gross_pnl - fees
        return_on_risk = net_pnl / entry_cost if entry_cost > 0 else 0.0

        return BacktestTradeResult(
            timestamp=trade.timestamp,
            ticker=trade.ticker,
            side=trade.side.lower(),
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            model_probability=trade.model_probability,
            confidence=trade.confidence,
            market_probability=market_probability,
            edge=edge,
            entry_cost=entry_cost,
            exit_value=exit_value,
            gross_pnl=gross_pnl,
            fees=fees,
            net_pnl=net_pnl,
            return_on_risk=return_on_risk,
            won=net_pnl > 0,
            metadata=trade.metadata,
        )

    def _summarize(
        self,
        initial_bankroll: float,
        ending_bankroll: float,
        ledger: List[BacktestTradeResult],
        equity_curve: List[EquityPoint],
    ) -> BacktestSummary:
        wins = sum(1 for trade in ledger if trade.net_pnl > 0)
        losses = sum(1 for trade in ledger if trade.net_pnl <= 0)
        gains = sum(trade.net_pnl for trade in ledger if trade.net_pnl > 0)
        losses_abs = abs(sum(trade.net_pnl for trade in ledger if trade.net_pnl < 0))
        total_fees = sum(trade.fees for trade in ledger)
        gross_pnl = sum(trade.gross_pnl for trade in ledger)
        net_pnl = ending_bankroll - initial_bankroll
        trade_returns = [trade.return_on_risk for trade in ledger]

        profit_factor = 0.0
        if losses_abs > 0:
            profit_factor = gains / losses_abs
        elif gains > 0:
            profit_factor = math.inf

        sharpe_like = 0.0
        if len(trade_returns) > 1:
            volatility = pstdev(trade_returns)
            if volatility > 0:
                sharpe_like = (
                    mean(trade_returns) / volatility * math.sqrt(len(trade_returns))
                )

        return BacktestSummary(
            initial_bankroll=initial_bankroll,
            ending_bankroll=ending_bankroll,
            total_trades=len(ledger),
            wins=wins,
            losses=losses,
            win_rate=wins / len(ledger) if ledger else 0.0,
            gross_pnl=gross_pnl,
            total_fees=total_fees,
            net_pnl=net_pnl,
            return_pct=net_pnl / initial_bankroll,
            max_drawdown=max(
                (point.drawdown_pct for point in equity_curve), default=0.0
            ),
            profit_factor=profit_factor,
            average_edge=mean([trade.edge for trade in ledger]) if ledger else 0.0,
            average_confidence=(
                mean([trade.confidence for trade in ledger]) if ledger else 0.0
            ),
            sharpe_like=sharpe_like,
            trades=ledger,
            equity_curve=equity_curve,
        )

    def _validate_trade(self, trade: BacktestTradeInput) -> None:
        if trade.side.lower() not in {"yes", "no"}:
            raise ValueError("side must be 'yes' or 'no'")
        if not 0 <= trade.entry_price <= 100:
            raise ValueError("entry_price must be between 0 and 100 cents")
        if not 0 <= trade.exit_price <= 100:
            raise ValueError("exit_price must be between 0 and 100 cents")
        if trade.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not 0 <= trade.model_probability <= 1:
            raise ValueError("model_probability must be between 0 and 1")
        if not 0 <= trade.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if trade.entry_fee < 0 or trade.exit_fee < 0:
            raise ValueError("fees cannot be negative")


def load_trades_csv(path: str | Path) -> List[BacktestTradeInput]:
    """Load backtest trades from a CSV file."""
    trades: List[BacktestTradeInput] = []
    with Path(path).open(newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            trades.append(
                BacktestTradeInput(
                    timestamp=_parse_timestamp(row["timestamp"]),
                    ticker=row["ticker"],
                    side=row["side"],
                    entry_price=float(row["entry_price"]),
                    exit_price=float(row["exit_price"]),
                    quantity=int(row["quantity"]),
                    model_probability=float(row["model_probability"]),
                    confidence=float(row.get("confidence") or 1.0),
                    entry_fee=float(row.get("entry_fee") or 0.0),
                    exit_fee=float(row.get("exit_fee") or 0.0),
                    metadata={
                        key: value
                        for key, value in row.items()
                        if key
                        not in {
                            "timestamp",
                            "ticker",
                            "side",
                            "entry_price",
                            "exit_price",
                            "quantity",
                            "model_probability",
                            "confidence",
                            "entry_fee",
                            "exit_fee",
                        }
                    },
                )
            )
    return trades


def _parse_timestamp(value: str) -> datetime:
    return parse_timestamp(value)
