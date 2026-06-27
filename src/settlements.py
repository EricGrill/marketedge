"""Offline settlement outcome loading and trade resolution."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from src.backtesting import BacktestTradeInput
from src.utils import parse_timestamp


class SettlementValidationError(ValueError):
    """Raised when settlement rows are missing, duplicated, or inconsistent."""


@dataclass(frozen=True)
class SettlementOutcome:
    """Actual settled outcome for one prediction-market contract."""

    ticker: str
    settled_at: datetime
    winning_side: str
    yes_settlement_price: float
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        side = self.winning_side.lower()
        if side not in {"yes", "no"}:
            raise SettlementValidationError("winning_side must be 'yes' or 'no'")
        if not self.ticker:
            raise SettlementValidationError("ticker is required")
        if not 0 <= self.yes_settlement_price <= 100:
            raise SettlementValidationError(
                "yes_settlement_price must be between 0 and 100 cents"
            )
        expected_price = 100.0 if side == "yes" else 0.0
        if self.yes_settlement_price != expected_price:
            raise SettlementValidationError(
                f"inconsistent settlement for {self.ticker}: "
                f"{side} winner cannot have YES settlement "
                f"{self.yes_settlement_price:g}"
            )

    def settlement_price_for(self, side: str) -> float:
        """Return the payout in cents for a YES or NO position."""
        normalized_side = side.lower()
        if normalized_side == "yes":
            return self.yes_settlement_price
        if normalized_side == "no":
            return 100.0 - self.yes_settlement_price
        raise SettlementValidationError("trade side must be 'yes' or 'no'")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "settled_at": self.settled_at.isoformat(),
            "winning_side": self.winning_side.lower(),
            "yes_settlement_price": self.yes_settlement_price,
            "source": self.source,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class SettlementValidationReport:
    """Validation result for a trade ledger joined to settlement outcomes."""

    missing_tickers: List[str]
    duplicate_tickers: List[str]

    @property
    def ok(self) -> bool:
        return not self.missing_tickers and not self.duplicate_tickers

    def raise_for_errors(self) -> None:
        messages = []
        if self.missing_tickers:
            messages.append(f"missing outcomes: {', '.join(self.missing_tickers)}")
        if self.duplicate_tickers:
            messages.append(f"duplicate outcomes: {', '.join(self.duplicate_tickers)}")
        if messages:
            raise SettlementValidationError("; ".join(messages))


class SettlementResolver:
    """Resolve historical trades against loaded settlement outcomes."""

    def __init__(self, outcomes: Iterable[SettlementOutcome]):
        self._outcomes: Dict[str, SettlementOutcome] = {}
        self._duplicate_tickers: List[str] = []

        for outcome in outcomes:
            if outcome.ticker in self._outcomes:
                self._duplicate_tickers.append(outcome.ticker)
            else:
                self._outcomes[outcome.ticker] = outcome

        if self._duplicate_tickers:
            raise SettlementValidationError(
                f"duplicate settlement outcomes: {', '.join(self.duplicate_tickers)}"
            )

    @property
    def duplicate_tickers(self) -> List[str]:
        return sorted(set(self._duplicate_tickers))

    @property
    def tickers(self) -> List[str]:
        return sorted(self._outcomes)

    def require_outcome(self, ticker: str) -> SettlementOutcome:
        try:
            return self._outcomes[ticker]
        except KeyError as exc:
            raise SettlementValidationError(
                f"missing settlement outcome: {ticker}"
            ) from exc

    def validate_trades(
        self, trades: Iterable[BacktestTradeInput]
    ) -> SettlementValidationReport:
        missing = sorted(
            {trade.ticker for trade in trades if trade.ticker not in self._outcomes}
        )
        return SettlementValidationReport(
            missing_tickers=missing,
            duplicate_tickers=self.duplicate_tickers,
        )

    def settle_trades(
        self, trades: Iterable[BacktestTradeInput]
    ) -> List[BacktestTradeInput]:
        """Return trades with exit prices replaced by actual settlement payouts."""
        settled: List[BacktestTradeInput] = []
        for trade in trades:
            outcome = self.require_outcome(trade.ticker)
            settled.append(
                replace(
                    trade,
                    exit_price=outcome.settlement_price_for(trade.side),
                    metadata={
                        **trade.metadata,
                        "settled_at": outcome.settled_at.isoformat(),
                        "settlement_source": outcome.source,
                        "winning_side": outcome.winning_side.lower(),
                    },
                )
            )
        return settled


def load_settlements_csv(path: str | Path) -> List[SettlementOutcome]:
    """Load settlement outcomes from a CSV file."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [_outcome_from_mapping(row) for row in csv.DictReader(handle)]


def load_settlements_jsonl(path: str | Path) -> List[SettlementOutcome]:
    """Load settlement outcomes from newline-delimited JSON."""
    outcomes: List[SettlementOutcome] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SettlementValidationError(
                    f"invalid JSON on line {line_number}: {exc.msg}"
                ) from exc
            outcomes.append(_outcome_from_mapping(payload))
    return outcomes


def _outcome_from_mapping(row: Mapping[str, Any]) -> SettlementOutcome:
    ticker = str(row["ticker"]).strip()
    winning_side = str(row["winning_side"]).strip().lower()
    yes_price = _settlement_price(row, winning_side)
    known_fields = {
        "ticker",
        "settled_at",
        "settlement_time",
        "winning_side",
        "yes_settlement_price",
        "settlement_value",
        "settlement_price",
        "source",
    }

    return SettlementOutcome(
        ticker=ticker,
        settled_at=_parse_timestamp(
            str(row.get("settled_at") or row.get("settlement_time"))
        ),
        winning_side=winning_side,
        yes_settlement_price=yes_price,
        source=str(row.get("source") or ""),
        metadata={key: value for key, value in row.items() if key not in known_fields},
    )


def _settlement_price(row: Mapping[str, Any], winning_side: str) -> float:
    for key in ("yes_settlement_price", "settlement_value", "settlement_price"):
        raw = row.get(key)
        if raw not in (None, ""):
            return float(raw)
    return 100.0 if winning_side == "yes" else 0.0


def _parse_timestamp(value: str) -> datetime:
    if not value:
        raise SettlementValidationError("settled_at is required")
    return parse_timestamp(value)
