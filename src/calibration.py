"""Model calibration scoring for offline prediction-market forecasts."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from src.settlements import SettlementResolver
from src.state import StateManager


@dataclass(frozen=True)
class ForecastInput:
    """One model probability emitted before a market settles."""

    timestamp: datetime
    ticker: str
    model_probability: float
    strategy: str = "default"
    market_category: str = "unknown"
    event_type: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalibrationBucket:
    """Observed calibration for a probability bucket."""

    lower: float
    upper: float
    count: int
    average_probability: float
    observed_rate: float
    absolute_error: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "count": self.count,
            "average_probability": self.average_probability,
            "observed_rate": self.observed_rate,
            "absolute_error": self.absolute_error,
        }


@dataclass(frozen=True)
class CalibrationGroupSummary:
    """Calibration score for a strategy/category/event slice."""

    strategy: str
    market_category: str
    event_type: str
    total_forecasts: int
    brier_score: float
    log_loss: float
    average_probability: float
    observed_rate: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy": self.strategy,
            "market_category": self.market_category,
            "event_type": self.event_type,
            "total_forecasts": self.total_forecasts,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "average_probability": self.average_probability,
            "observed_rate": self.observed_rate,
        }


@dataclass(frozen=True)
class CalibrationSummary:
    """Dashboard-ready calibration output."""

    total_forecasts: int
    brier_score: float
    log_loss: float
    average_probability: float
    observed_rate: float
    window_start: datetime | None
    window_end: datetime | None
    buckets: List[CalibrationBucket]
    groups: List[CalibrationGroupSummary]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_forecasts": self.total_forecasts,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "average_probability": self.average_probability,
            "observed_rate": self.observed_rate,
            "window_start": (
                self.window_start.isoformat() if self.window_start else None
            ),
            "window_end": self.window_end.isoformat() if self.window_end else None,
            "buckets": [bucket.to_dict() for bucket in self.buckets],
            "groups": [group.to_dict() for group in self.groups],
        }


class CalibrationScorer:
    """Score forecast probabilities against resolved settlement outcomes."""

    def __init__(self, bucket_size: float = 0.1, epsilon: float = 1e-15):
        if not 0 < bucket_size <= 1:
            raise ValueError("bucket_size must be between 0 and 1")
        self.bucket_size = bucket_size
        self.epsilon = epsilon

    def score(
        self,
        forecasts: Iterable[ForecastInput],
        settlements: SettlementResolver,
    ) -> CalibrationSummary:
        rows = sorted(forecasts, key=lambda forecast: forecast.timestamp)
        if not rows:
            return CalibrationSummary(
                total_forecasts=0,
                brier_score=0.0,
                log_loss=0.0,
                average_probability=0.0,
                observed_rate=0.0,
                window_start=None,
                window_end=None,
                buckets=[],
                groups=[],
            )

        scored = [
            (forecast, self._observed_yes(forecast, settlements)) for forecast in rows
        ]
        probability_actuals = [
            (forecast.model_probability, actual) for forecast, actual in scored
        ]

        return CalibrationSummary(
            total_forecasts=len(scored),
            brier_score=mean(
                [self._brier(prob, actual) for prob, actual in probability_actuals]
            ),
            log_loss=mean(
                [self._log_loss(prob, actual) for prob, actual in probability_actuals]
            ),
            average_probability=mean(
                [forecast.model_probability for forecast, _ in scored]
            ),
            observed_rate=mean([actual for _, actual in scored]),
            window_start=rows[0].timestamp,
            window_end=rows[-1].timestamp,
            buckets=self._buckets(scored),
            groups=self._groups(scored),
        )

    def _observed_yes(
        self, forecast: ForecastInput, settlements: SettlementResolver
    ) -> int:
        outcome = settlements.require_outcome(forecast.ticker)
        return 1 if outcome.winning_side.lower() == "yes" else 0

    def _brier(self, probability: float, actual: int) -> float:
        self._validate_probability(probability)
        return (probability - actual) ** 2

    def _log_loss(self, probability: float, actual: int) -> float:
        self._validate_probability(probability)
        clipped = min(max(probability, self.epsilon), 1 - self.epsilon)
        return -(actual * math.log(clipped) + (1 - actual) * math.log(1 - clipped))

    def _buckets(
        self, scored: List[Tuple[ForecastInput, int]]
    ) -> List[CalibrationBucket]:
        bucket_count = math.ceil(1 / self.bucket_size)
        buckets: List[CalibrationBucket] = []
        for index in range(bucket_count):
            lower = index * self.bucket_size
            upper = min((index + 1) * self.bucket_size, 1.0)
            rows = [
                (forecast, actual)
                for forecast, actual in scored
                if self._bucket_index(forecast.model_probability, bucket_count) == index
            ]
            if not rows:
                continue
            average_probability = mean(
                [forecast.model_probability for forecast, _ in rows]
            )
            observed_rate = mean([actual for _, actual in rows])
            buckets.append(
                CalibrationBucket(
                    lower=lower,
                    upper=upper,
                    count=len(rows),
                    average_probability=average_probability,
                    observed_rate=observed_rate,
                    absolute_error=abs(average_probability - observed_rate),
                )
            )
        return buckets

    def _groups(
        self, scored: List[Tuple[ForecastInput, int]]
    ) -> List[CalibrationGroupSummary]:
        grouped: Dict[Tuple[str, str, str], List[Tuple[ForecastInput, int]]] = {}
        for forecast, actual in scored:
            key = (forecast.strategy, forecast.market_category, forecast.event_type)
            grouped.setdefault(key, []).append((forecast, actual))

        summaries = []
        for (strategy, market_category, event_type), rows in sorted(grouped.items()):
            summaries.append(
                CalibrationGroupSummary(
                    strategy=strategy,
                    market_category=market_category,
                    event_type=event_type,
                    total_forecasts=len(rows),
                    brier_score=mean(
                        [
                            self._brier(forecast.model_probability, actual)
                            for forecast, actual in rows
                        ]
                    ),
                    log_loss=mean(
                        [
                            self._log_loss(forecast.model_probability, actual)
                            for forecast, actual in rows
                        ]
                    ),
                    average_probability=mean(
                        [forecast.model_probability for forecast, _ in rows]
                    ),
                    observed_rate=mean([actual for _, actual in rows]),
                )
            )
        return summaries

    def _bucket_index(self, probability: float, bucket_count: int) -> int:
        self._validate_probability(probability)
        return min(int(probability / self.bucket_size), bucket_count - 1)

    def _validate_probability(self, probability: float) -> None:
        if not 0 <= probability <= 1:
            raise ValueError("model_probability must be between 0 and 1")


def load_forecasts_csv(path: str | Path) -> List[ForecastInput]:
    """Load forecast probabilities from a CSV file."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [_forecast_from_mapping(row) for row in csv.DictReader(handle)]


def load_forecasts_jsonl(path: str | Path) -> List[ForecastInput]:
    """Load forecast probabilities from newline-delimited JSON."""
    forecasts: List[ForecastInput] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"invalid JSON on line {line_number}: {exc.msg}"
                ) from exc
            forecasts.append(_forecast_from_mapping(payload))
    return forecasts


async def load_persisted_forecasts(
    state: StateManager,
    *,
    strategy: str | None = None,
    market_category: str | None = None,
    limit: int = 1000,
) -> List[ForecastInput]:
    """Load forecasts persisted in SQLite into calibration input rows."""
    rows = await state.get_weather_forecasts(
        strategy=strategy,
        market_category=market_category,
        limit=limit,
    )
    forecasts: List[ForecastInput] = []
    for row in rows:
        forecasts.append(
            ForecastInput(
                timestamp=row.created_at,
                ticker=row.market_ticker,
                model_probability=row.blended_probability,
                strategy=row.strategy or "weather",
                market_category=row.market_category or "weather",
                event_type=row.event_type or "unknown",
                metadata={
                    "forecast_id": row.id,
                    "location": row.location,
                    "forecast_cycle": (
                        row.forecast_cycle.isoformat() if row.forecast_cycle else None
                    ),
                    "confidence": row.confidence,
                    "model_version": row.model_version,
                    "source_metadata": _json_dict(row.source_metadata_json),
                    "feature_metadata": _json_dict(row.feature_metadata_json),
                },
            )
        )
    return forecasts


async def score_persisted_forecasts(
    state: StateManager,
    settlements: SettlementResolver,
    *,
    strategy: str | None = None,
    market_category: str | None = None,
    limit: int = 1000,
) -> CalibrationSummary:
    """Join stored forecasts to settlement outcomes and score calibration."""
    forecasts = await load_persisted_forecasts(
        state,
        strategy=strategy,
        market_category=market_category,
        limit=limit,
    )
    return CalibrationScorer().score(forecasts, settlements)


def export_calibration_summary(summary: CalibrationSummary, path: str | Path) -> Path:
    """Write dashboard-ready calibration JSON."""
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary.to_dict(), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output


def _forecast_from_mapping(row: Mapping[str, Any]) -> ForecastInput:
    known_fields = {
        "timestamp",
        "ticker",
        "model_probability",
        "strategy",
        "market_category",
        "event_type",
    }
    return ForecastInput(
        timestamp=datetime.fromisoformat(str(row["timestamp"]).replace("Z", "+00:00")),
        ticker=str(row["ticker"]),
        model_probability=float(row["model_probability"]),
        strategy=str(row.get("strategy") or "default"),
        market_category=str(row.get("market_category") or "unknown"),
        event_type=str(row.get("event_type") or "unknown"),
        metadata={key: value for key, value in row.items() if key not in known_fields},
    )


def _json_dict(value: str | None) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
