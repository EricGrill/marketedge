"""Additional local-first strategy engines and execution overlays."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from src.execution import OrderBookSnapshot
from src.market_adapters import NormalizedMarket, normalize_market
from src.utils import ensure_utc, parse_timestamp, utcnow


@dataclass(frozen=True)
class StrategyOpportunity:
    """Common strategy opportunity payload for CLI/dashboard artifacts."""

    strategy_id: str
    ticker: str
    action: str
    edge: float
    confidence: float
    reason_codes: List[str]
    legs: List[Dict[str, Any]] = field(default_factory=list)
    worst_case_loss: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "ticker": self.ticker,
            "action": self.action,
            "edge": self.edge,
            "confidence": self.confidence,
            "reason_codes": self.reason_codes,
            "legs": self.legs,
            "worst_case_loss": self.worst_case_loss,
            "metadata": self.metadata,
        }


class RelativeValueStrategy:
    """Find threshold-ladder, mutually exclusive, and correlated-pricing gaps."""

    strategy_id = "relative-value"

    def __init__(self, tolerance: float = 0.02):
        self.tolerance = tolerance

    def evaluate(
        self, markets: Iterable[NormalizedMarket | Mapping[str, Any]]
    ) -> List[StrategyOpportunity]:
        candidates = [_as_market(market) for market in markets]
        normalized = [market for market in candidates if market is not None]
        return [
            *self._threshold_ladders(normalized),
            *self._mutually_exclusive_sets(normalized),
            *self._correlated_regions(normalized),
        ]

    def _threshold_ladders(
        self, markets: List[NormalizedMarket]
    ) -> List[StrategyOpportunity]:
        grouped: Dict[tuple[str, str, str], List[NormalizedMarket]] = {}
        for market in markets:
            if market.threshold <= 0:
                continue
            key = (market.relationship_group, market.event_type, market.date_bucket)
            grouped.setdefault(key, []).append(market)

        opportunities: List[StrategyOpportunity] = []
        for rows in grouped.values():
            ladder = sorted(rows, key=lambda market: market.threshold)
            for lower, upper in zip(ladder, ladder[1:]):
                lower_prob = _implied_yes(lower)
                upper_prob = _implied_yes(upper)
                if upper_prob <= lower_prob + self.tolerance:
                    continue
                edge = upper_prob - lower_prob
                opportunities.append(
                    StrategyOpportunity(
                        strategy_id=self.strategy_id,
                        ticker=f"{lower.ticker}/{upper.ticker}",
                        action="paired_ladder",
                        edge=edge,
                        confidence=min(0.95, 0.5 + edge),
                        worst_case_loss=_notional(lower) + _notional(upper),
                        reason_codes=["THRESHOLD_LADDER_INVERSION"],
                        legs=[
                            _leg(lower, "buy_yes"),
                            _leg(upper, "sell_yes"),
                        ],
                        metadata={
                            "lower_threshold": lower.threshold,
                            "upper_threshold": upper.threshold,
                        },
                    )
                )
        return opportunities

    def _mutually_exclusive_sets(
        self, markets: List[NormalizedMarket]
    ) -> List[StrategyOpportunity]:
        grouped: Dict[str, List[NormalizedMarket]] = {}
        for market in markets:
            if market.outcome_set:
                grouped.setdefault(market.outcome_set, []).append(market)

        opportunities: List[StrategyOpportunity] = []
        for outcome_set, rows in grouped.items():
            if len(rows) < 2:
                continue
            probability_sum = sum(_implied_yes(row) for row in rows)
            if probability_sum <= 1.0 + self.tolerance:
                continue
            edge = probability_sum - 1.0
            opportunities.append(
                StrategyOpportunity(
                    strategy_id=self.strategy_id,
                    ticker=outcome_set,
                    action="basket_short_overround",
                    edge=edge,
                    confidence=min(0.95, 0.45 + edge),
                    worst_case_loss=sum(_notional(row) for row in rows),
                    reason_codes=["MUTUALLY_EXCLUSIVE_OVERROUND"],
                    legs=[_leg(row, "sell_yes") for row in rows],
                    metadata={"probability_sum": probability_sum},
                )
            )
        return opportunities

    def _correlated_regions(
        self, markets: List[NormalizedMarket]
    ) -> List[StrategyOpportunity]:
        grouped: Dict[tuple[str, str], List[NormalizedMarket]] = {}
        for market in markets:
            key = (market.event_type, market.date_bucket)
            grouped.setdefault(key, []).append(market)

        opportunities: List[StrategyOpportunity] = []
        for rows in grouped.values():
            if len(rows) < 2:
                continue
            probabilities = [_implied_yes(row) for row in rows]
            spread = max(probabilities) - min(probabilities)
            if spread <= 0.20:
                continue
            rich = rows[probabilities.index(max(probabilities))]
            cheap = rows[probabilities.index(min(probabilities))]
            opportunities.append(
                StrategyOpportunity(
                    strategy_id=self.strategy_id,
                    ticker=f"{cheap.ticker}/{rich.ticker}",
                    action="regional_pair",
                    edge=spread,
                    confidence=min(0.9, 0.4 + spread),
                    worst_case_loss=_notional(cheap) + _notional(rich),
                    reason_codes=["CORRELATED_REGION_DISLOCATION"],
                    legs=[_leg(cheap, "buy_yes"), _leg(rich, "sell_yes")],
                    metadata={
                        "cheap_region": cheap.region,
                        "rich_region": rich.region,
                        "hedge_exposure": min(_notional(cheap), _notional(rich)),
                    },
                )
            )
        return opportunities


@dataclass(frozen=True)
class CatalystRecord:
    """Calendar catalyst that affects one or more market tickers."""

    catalyst_id: str
    event_type: str
    affected_tickers: List[str]
    window_start: datetime
    window_end: datetime
    source: str = ""
    confidence: float = 1.0
    rationale: str = ""

    def active_for(self, ticker: str, as_of: datetime) -> bool:
        current = ensure_utc(as_of)
        return ticker in self.affected_tickers and ensure_utc(
            self.window_start
        ) <= current <= ensure_utc(self.window_end)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "catalyst_id": self.catalyst_id,
            "event_type": self.event_type,
            "affected_tickers": self.affected_tickers,
            "window_start": ensure_utc(self.window_start).isoformat(),
            "window_end": ensure_utc(self.window_end).isoformat(),
            "source": self.source,
            "confidence": self.confidence,
            "rationale": self.rationale,
        }


class CatalystCalendarStrategy:
    """Filter and tag candidates that are inside catalyst windows."""

    strategy_id = "catalyst-calendar"

    def __init__(self, records: Iterable[CatalystRecord] | None = None):
        self.records = list(records or [])

    def evaluate(
        self,
        candidates: Iterable[NormalizedMarket | Mapping[str, Any]],
        as_of: datetime | None = None,
    ) -> List[StrategyOpportunity]:
        current = as_of or utcnow()
        opportunities: List[StrategyOpportunity] = []
        for candidate in candidates:
            market = _as_market(candidate)
            if not market:
                continue
            matches = [
                record
                for record in self.records
                if record.active_for(market.ticker, current)
            ]
            if not matches:
                continue
            catalyst = max(matches, key=lambda record: record.confidence)
            opportunities.append(
                StrategyOpportunity(
                    strategy_id=self.strategy_id,
                    ticker=market.ticker,
                    action="watch_catalyst",
                    edge=0.0,
                    confidence=catalyst.confidence,
                    reason_codes=["CATALYST_WINDOW_ACTIVE"],
                    legs=[_leg(market, "watch")],
                    metadata={
                        "catalyst": catalyst.to_dict(),
                        "timing": "inside_window",
                        "rationale": catalyst.rationale,
                    },
                )
            )
        return opportunities


@dataclass(frozen=True)
class ProbabilitySource:
    """One probability source emitted by a model or feature pipeline."""

    source_id: str
    category: str
    timestamp: datetime
    probability: float
    confidence: float = 1.0
    feature_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceCalibration:
    """Historical calibration quality for one probability source."""

    source_id: str
    category: str = "unknown"
    brier_score: float = 0.25
    log_loss: float = 0.69
    bucket_error: float = 0.10
    sample_count: int = 0
    updated_at: datetime | None = None


class CalibrationWeightedEnsembleStrategy:
    """Blend sources using observed calibration quality and recency."""

    strategy_id = "calibration-ensemble"

    def __init__(self, sparse_sample_threshold: int = 5):
        self.sparse_sample_threshold = sparse_sample_threshold

    def blend(
        self,
        sources: Iterable[ProbabilitySource],
        calibration: Iterable[SourceCalibration] | None = None,
        as_of: datetime | None = None,
    ) -> Dict[str, Any]:
        rows = list(sources)
        if not rows:
            raise ValueError("at least one probability source is required")
        by_source = {metric.source_id: metric for metric in calibration or []}
        current = as_of or utcnow()

        raw_weights = []
        contributions: List[Dict[str, Any]] = []
        for source in rows:
            metric = by_source.get(source.source_id)
            weight, reasons = self._weight_for(source, metric, current)
            raw_weights.append(weight)
            contributions.append(
                {
                    "source_id": source.source_id,
                    "probability": source.probability,
                    "confidence": source.confidence,
                    "raw_weight": weight,
                    "reason_codes": reasons,
                    "calibration": metric_to_dict(metric),
                }
            )

        total = sum(raw_weights) or 1.0
        normalized_weights = [weight / total for weight in raw_weights]
        blended = sum(
            source.probability * weight
            for source, weight in zip(rows, normalized_weights)
        )
        confidence = sum(
            source.confidence * weight
            for source, weight in zip(rows, normalized_weights)
        )
        for contribution, weight in zip(contributions, normalized_weights):
            contribution["weight"] = weight
            contribution["weighted_probability"] = contribution["probability"] * weight

        return {
            "strategy_id": self.strategy_id,
            "blended_probability": blended,
            "confidence": confidence,
            "source_contributions": contributions,
            "reason_codes": sorted(
                {reason for item in contributions for reason in item["reason_codes"]}
            ),
        }

    def _weight_for(
        self,
        source: ProbabilitySource,
        metric: SourceCalibration | None,
        as_of: datetime,
    ) -> tuple[float, List[str]]:
        reasons: List[str] = []
        if metric is None or metric.sample_count < self.sparse_sample_threshold:
            reasons.append("SPARSE_HISTORY_FALLBACK")
            return max(0.05, source.confidence * 0.5), reasons

        quality = 1.0 / (
            0.01 + metric.brier_score + metric.log_loss + metric.bucket_error
        )
        recency = 1.0
        if metric.updated_at:
            age_days = max(
                (ensure_utc(as_of) - ensure_utc(metric.updated_at)).days,
                0,
            )
            recency = math.exp(-age_days / 30.0)
            reasons.append("RECENCY_WEIGHTED")
        if metric.brier_score <= 0.15:
            reasons.append("BRIER_UPWEIGHT")
        else:
            reasons.append("BRIER_DOWNWEIGHT")
        if metric.log_loss <= 0.45:
            reasons.append("LOGLOSS_UPWEIGHT")
        else:
            reasons.append("LOGLOSS_DOWNWEIGHT")
        return max(0.01, quality * recency * source.confidence), reasons


@dataclass(frozen=True)
class LiquidityOverlayConfig:
    """Thresholds for execution-quality recommendations."""

    max_spread: float = 5.0
    min_depth: int = 50
    stale_after_seconds: int = 120
    max_slippage: float = 2.0
    partial_fill_ratio: float = 0.75


@dataclass(frozen=True)
class LiquidityRecommendation:
    """Execution overlay output before an order intent proceeds."""

    action: str
    adjusted_quantity: int
    limit_price: float | None
    metrics: Dict[str, Any]
    reason_codes: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "adjusted_quantity": self.adjusted_quantity,
            "limit_price": self.limit_price,
            "metrics": self.metrics,
            "reason_codes": self.reason_codes,
        }


class LiquidityMicrostructureOverlay:
    """Recommend execution behavior from spread, depth, staleness, and slippage."""

    strategy_id = "liquidity-overlay"

    def __init__(self, config: LiquidityOverlayConfig | None = None):
        self.config = config or LiquidityOverlayConfig()

    def evaluate(
        self,
        book: OrderBookSnapshot,
        *,
        side: str,
        action: str,
        target_quantity: int,
        quote_time: datetime | None = None,
        as_of: datetime | None = None,
    ) -> LiquidityRecommendation:
        levels = sorted(book.asks, key=lambda level: level.price)
        if action.lower() == "sell":
            levels = sorted(book.bids, key=lambda level: level.price, reverse=True)
        best_bid = max((level.price for level in book.bids), default=0.0)
        best_ask = min((level.price for level in book.asks), default=0.0)
        spread = best_ask - best_bid if best_bid and best_ask else 100.0
        depth = sum(level.quantity for level in levels)
        avg_price, filled = _depth_weighted_price(levels, target_quantity)
        slippage = abs(avg_price - levels[0].price) if levels and filled else 100.0
        quote_age = _quote_age_seconds(quote_time, as_of)

        reasons: List[str] = []
        recommendation = "take_liquidity"
        adjusted_quantity = target_quantity
        limit_price = avg_price if avg_price else None

        if quote_age is not None and quote_age > self.config.stale_after_seconds:
            reasons.append("STALE_QUOTE")
            recommendation = "wait"
        if spread > self.config.max_spread:
            reasons.append("WIDE_SPREAD")
            recommendation = "maker_only"
        if depth < self.config.min_depth:
            reasons.append("THIN_BOOK")
            recommendation = "skip"
        elif filled < target_quantity:
            fill_ratio = filled / target_quantity if target_quantity else 0.0
            reasons.append("PARTIAL_FILL_RISK")
            if fill_ratio >= self.config.partial_fill_ratio:
                recommendation = "reduce_size"
                adjusted_quantity = filled
            else:
                recommendation = "skip"
        if slippage > self.config.max_slippage:
            reasons.append("SLIPPAGE_TOO_HIGH")
            if recommendation == "take_liquidity":
                recommendation = "maker_only"

        if not reasons:
            reasons.append("LIQUIDITY_OK")
            recommendation = "take_liquidity"

        return LiquidityRecommendation(
            action=recommendation,
            adjusted_quantity=adjusted_quantity,
            limit_price=limit_price,
            metrics={
                "side": side,
                "spread": spread,
                "depth": depth,
                "depth_weighted_average_price": avg_price,
                "filled_at_target": filled,
                "expected_slippage": slippage,
                "quote_age_seconds": quote_age,
                "recent_volume": book.recent_volume,
            },
            reason_codes=reasons,
        )

    def apply_to_backtest_fill(
        self,
        book: OrderBookSnapshot,
        *,
        quantity: int,
        entry_price: float,
    ) -> Dict[str, Any]:
        recommendation = self.evaluate(
            book,
            side="yes",
            action="buy",
            target_quantity=quantity,
        )
        effective_price = recommendation.limit_price or entry_price
        filled_quantity = (
            0
            if recommendation.action in {"skip", "wait"}
            else recommendation.adjusted_quantity
        )
        return {
            "filled_quantity": filled_quantity,
            "unfilled_quantity": quantity - filled_quantity,
            "effective_entry_price": effective_price,
            "overlay": recommendation.to_dict(),
        }


def load_catalysts_csv(path: str | Path) -> List[CatalystRecord]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [_catalyst_from_mapping(row) for row in csv.DictReader(handle)]


def load_catalysts_jsonl(path: str | Path) -> List[CatalystRecord]:
    records: List[CatalystRecord] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(_catalyst_from_mapping(json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON on line {line_number}: {exc.msg}"
                ) from exc
    return records


def export_strategy_opportunities(
    opportunities: Iterable[StrategyOpportunity], path: str | Path
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([item.to_dict() for item in opportunities], indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def metric_to_dict(metric: SourceCalibration | None) -> Dict[str, Any] | None:
    if metric is None:
        return None
    return {
        "source_id": metric.source_id,
        "category": metric.category,
        "brier_score": metric.brier_score,
        "log_loss": metric.log_loss,
        "bucket_error": metric.bucket_error,
        "sample_count": metric.sample_count,
        "updated_at": metric.updated_at.isoformat() if metric.updated_at else None,
    }


def _as_market(value: NormalizedMarket | Mapping[str, Any]) -> NormalizedMarket | None:
    if isinstance(value, NormalizedMarket):
        return value
    return normalize_market(dict(value))


def _implied_yes(market: NormalizedMarket) -> float:
    price = market.yes_ask or market.last_price or market.yes_bid
    return price / 100.0


def _notional(market: NormalizedMarket) -> float:
    price = market.yes_ask or market.last_price or market.yes_bid
    return price / 100.0


def _leg(market: NormalizedMarket, action: str) -> Dict[str, Any]:
    return {
        "ticker": market.ticker,
        "action": action,
        "price": market.yes_ask or market.last_price or market.yes_bid,
        "threshold": market.threshold,
        "region": market.region,
        "event_type": market.event_type,
    }


def _depth_weighted_price(levels, quantity: int) -> tuple[float, int]:
    remaining = quantity
    filled = 0
    notional = 0.0
    for level in levels:
        if remaining <= 0:
            break
        take = min(remaining, level.quantity)
        filled += take
        notional += take * level.price
        remaining -= take
    if not filled:
        return 0.0, 0
    return notional / filled, filled


def _quote_age_seconds(
    quote_time: datetime | None, as_of: datetime | None
) -> float | None:
    if quote_time is None:
        return None
    return (ensure_utc(as_of or utcnow()) - ensure_utc(quote_time)).total_seconds()


def _catalyst_from_mapping(row: Mapping[str, Any]) -> CatalystRecord:
    tickers = row.get("affected_tickers") or row.get("tickers") or row.get("ticker")
    if isinstance(tickers, str):
        affected = [item.strip() for item in tickers.replace(";", ",").split(",")]
    elif isinstance(tickers, (list, tuple, set)):
        affected = [str(item) for item in tickers]
    else:
        affected = []
    return CatalystRecord(
        catalyst_id=str(row.get("catalyst_id") or row.get("id")),
        event_type=str(row.get("event_type") or row.get("type") or "catalyst"),
        affected_tickers=[ticker for ticker in affected if ticker],
        window_start=parse_timestamp(str(row["window_start"])),
        window_end=parse_timestamp(str(row["window_end"])),
        source=str(row.get("source") or ""),
        confidence=float(row.get("confidence") or 1.0),
        rationale=str(row.get("rationale") or ""),
    )
