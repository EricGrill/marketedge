"""Rank prediction-market opportunities from model and market inputs."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from src.config import trading_config
from src.formulas import QuantEngine


@dataclass(frozen=True)
class OpportunityCandidate:
    """Market input required for offline opportunity ranking."""

    ticker: str
    model_probability: float
    yes_bid: float
    yes_ask: float
    title: str = ""
    no_bid: float | None = None
    no_ask: float | None = None
    confidence: float = 1.0
    volume: int = 0
    open_interest: int = 0
    resolution_date: datetime | None = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "OpportunityCandidate":
        return cls(
            ticker=str(payload["ticker"]),
            title=str(payload.get("title") or payload.get("event_title") or ""),
            model_probability=float(payload["model_probability"]),
            yes_bid=float(payload.get("yes_bid", payload.get("bid", 0.0))),
            yes_ask=float(payload.get("yes_ask", payload.get("ask", 0.0))),
            no_bid=_optional_float(payload.get("no_bid")),
            no_ask=_optional_float(payload.get("no_ask")),
            confidence=float(payload.get("confidence") or 1.0),
            volume=int(float(payload.get("volume") or payload.get("volume_24h") or 0)),
            open_interest=int(float(payload.get("open_interest") or 0)),
            resolution_date=_optional_datetime(
                payload.get("resolution_date")
                or payload.get("close_date")
                or payload.get("expiration_date")
            ),
        )


@dataclass(frozen=True)
class OpportunityResult:
    """Ranked opportunity output for CLI and dashboard use."""

    ticker: str
    title: str
    side: str
    action: str
    score: float
    entry_price: float
    market_probability: float
    model_probability: float
    fee_adjusted_edge: float
    expected_value: float
    recommended_bet_dollars: float
    annualized_yield: float
    liquidity_spread: float
    confidence: float
    risk_of_ruin: float
    reason_codes: List[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "title": self.title,
            "side": self.side,
            "action": self.action,
            "score": self.score,
            "entry_price": self.entry_price,
            "market_probability": self.market_probability,
            "model_probability": self.model_probability,
            "fee_adjusted_edge": self.fee_adjusted_edge,
            "expected_value": self.expected_value,
            "recommended_bet_dollars": self.recommended_bet_dollars,
            "annualized_yield": self.annualized_yield,
            "liquidity_spread": self.liquidity_spread,
            "confidence": self.confidence,
            "risk_of_ruin": self.risk_of_ruin,
            "reason_codes": self.reason_codes,
        }


class OpportunityScanner:
    """Rank YES and NO contract candidates with existing quant primitives."""

    def __init__(self, quant_engine: QuantEngine | None = None):
        self.quant = quant_engine or QuantEngine()

    def rank(
        self,
        candidates: Iterable[OpportunityCandidate],
        bankroll: float = trading_config.initial_bankroll,
    ) -> List[OpportunityResult]:
        results: List[OpportunityResult] = []
        for candidate in candidates:
            results.append(self._evaluate_side(candidate, "yes", bankroll))
            results.append(self._evaluate_side(candidate, "no", bankroll))
        return sorted(
            results,
            key=lambda result: (
                result.action.startswith("BUY"),
                result.score,
                result.fee_adjusted_edge,
            ),
            reverse=True,
        )

    def _evaluate_side(
        self, candidate: OpportunityCandidate, side: str, bankroll: float
    ) -> OpportunityResult:
        resolution = candidate.resolution_date or _default_resolution_date()
        bid, ask = _contract_book(candidate, side)
        contract_probability = (
            candidate.model_probability
            if side == "yes"
            else 1 - candidate.model_probability
        )

        edge = self.quant.calculate_edge(contract_probability, ask, side="yes")
        las = self.quant.calculate_las(bid, ask)
        iy = self.quant.calculate_iy(ask, resolution)
        kelly = self.quant.kelly_sizing(edge, bankroll, candidate.confidence, las)
        risk_edge = max(edge.raw_edge, edge.fee_adjusted_edge)
        risk_of_ruin = self.quant.calculate_ror(
            risk_edge, kelly.recommended_fraction, bankroll
        )

        reason_codes = _reason_codes(
            edge=edge,
            las=las,
            iy=iy,
            candidate=candidate,
            recommended_bet=kelly.recommended_bet_dollars,
            risk_of_ruin=risk_of_ruin,
        )
        action = _action_for(side, reason_codes, edge.fee_adjusted_edge)
        score = _score(
            edge=edge.raw_edge,
            expected_value=edge.expected_value,
            confidence=candidate.confidence,
            liquidity_spread=las.las_ratio,
            volume=candidate.volume,
            action=action,
        )

        return OpportunityResult(
            ticker=candidate.ticker,
            title=candidate.title,
            side=side,
            action=action,
            score=score,
            entry_price=ask,
            market_probability=edge.market_probability,
            model_probability=contract_probability,
            fee_adjusted_edge=edge.fee_adjusted_edge,
            expected_value=edge.expected_value,
            recommended_bet_dollars=kelly.recommended_bet_dollars,
            annualized_yield=iy.annualized_yield,
            liquidity_spread=las.las_ratio,
            confidence=candidate.confidence,
            risk_of_ruin=risk_of_ruin,
            reason_codes=reason_codes,
        )


def load_candidates(path: str | Path) -> List[OpportunityCandidate]:
    """Load scanner candidates from JSON, JSONL, or CSV."""
    source = Path(path)
    if source.suffix.lower() == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        rows = payload.get("markets", payload) if isinstance(payload, dict) else payload
        return [OpportunityCandidate.from_dict(row) for row in rows]
    if source.suffix.lower() == ".jsonl":
        return [
            OpportunityCandidate.from_dict(json.loads(line))
            for line in source.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    with source.open(newline="", encoding="utf-8") as handle:
        return [OpportunityCandidate.from_dict(row) for row in csv.DictReader(handle)]


def _contract_book(candidate: OpportunityCandidate, side: str) -> tuple[float, float]:
    if side == "yes":
        return candidate.yes_bid, candidate.yes_ask
    no_bid = (
        candidate.no_bid if candidate.no_bid is not None else 100 - candidate.yes_ask
    )
    no_ask = (
        candidate.no_ask if candidate.no_ask is not None else 100 - candidate.yes_bid
    )
    return no_bid, no_ask


def _reason_codes(
    edge,
    las,
    iy,
    candidate: OpportunityCandidate,
    recommended_bet: float,
    risk_of_ruin: float,
) -> List[str]:
    reasons: List[str] = []
    if edge.raw_edge > trading_config.min_edge_pct and edge.expected_value > 0:
        reasons.append("EDGE_OK")
    else:
        reasons.append("EDGE_TOO_SMALL")
    if las.is_liquid:
        reasons.append("SPREAD_OK")
    else:
        reasons.append("SPREAD_TOO_WIDE")
    if iy.is_above_threshold:
        reasons.append("YIELD_OK")
    else:
        reasons.append("YIELD_TOO_LOW")
    if candidate.confidence >= 0.5:
        reasons.append("CONFIDENCE_OK")
    else:
        reasons.append("LOW_CONFIDENCE")
    if recommended_bet > 0:
        reasons.append("SIZE_OK")
    else:
        reasons.append("NO_SIZE")
    if risk_of_ruin < trading_config.max_ror_monthly:
        reasons.append("ROR_OK")
    else:
        reasons.append("ROR_TOO_HIGH")
    if candidate.volume > 0 or candidate.open_interest > 0:
        reasons.append("LIQUIDITY_SEEN")
    else:
        reasons.append("NO_LIQUIDITY_CONTEXT")
    return reasons


def _action_for(side: str, reasons: List[str], fee_adjusted_edge: float) -> str:
    blockers = {
        "EDGE_TOO_SMALL",
        "SPREAD_TOO_WIDE",
        "YIELD_TOO_LOW",
        "LOW_CONFIDENCE",
        "NO_SIZE",
        "ROR_TOO_HIGH",
    }
    if not blockers.intersection(reasons):
        return "BUY_YES" if side == "yes" else "BUY_NO"
    if fee_adjusted_edge > 0:
        return "HOLD"
    return "PASS"


def _score(
    edge: float,
    expected_value: float,
    confidence: float,
    liquidity_spread: float,
    volume: int,
    action: str,
) -> float:
    action_bonus = (
        20.0 if action.startswith("BUY") else 5.0 if action == "HOLD" else 0.0
    )
    volume_bonus = min(volume / 100_000.0, 1.0) * 5.0
    return (
        action_bonus
        + edge * 100.0
        + expected_value * 25.0
        + confidence * 10.0
        + volume_bonus
        - liquidity_spread * 10.0
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    clean = str(value)
    if clean.endswith("Z"):
        clean = f"{clean[:-1]}+00:00"
    parsed = datetime.fromisoformat(clean)
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _default_resolution_date() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
