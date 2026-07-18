"""Model calibration scoring for offline prediction-market forecasts."""

from __future__ import annotations

import csv
import json
import math
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

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
        created_at = row.created_at
        ticker = row.market_ticker
        blended = row.blended_probability
        if created_at is None or ticker is None or blended is None:
            continue
        forecasts.append(
            ForecastInput(
                timestamp=created_at,
                ticker=ticker,
                model_probability=blended,
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


# ========== ENSEMBLE WEIGHT FITTING ==========
#
# The weather model blend weights (ecmwf/gefs/analog/microclimate/nws_delta) are
# configured by hand and forced to sum to 1.0. This layer *learns* them from
# realized outcomes: given per-source probabilities paired with settled results,
# fit the convex combination of sources that minimizes the Brier score. The
# result reports both the fitted weights and the improvement over the current
# baseline so an operator can review a proposed (dry-run) weight update.

# Maps blend source name -> the WeatherConfig attribute holding its weight.
SOURCE_WEIGHT_FIELDS = {
    "ecmwf": "ecmwf_weight",
    "gefs": "gefs_weight",
    "analog": "analog_weight",
    "microclimate": "microclimate_weight",
    "nws_delta": "nws_delta_weight",
}

# One training row: per-source probabilities (0-1) and the settled outcome (0/1).
WeightSample = Tuple[Mapping[str, float], int]


@dataclass(frozen=True)
class WeightFitResult:
    """Proposed ensemble weights fitted to realized outcomes."""

    source_names: List[str]
    fitted_weights: Dict[str, float]
    baseline_weights: Dict[str, float]
    fitted_brier: float
    baseline_brier: float
    sample_count: int

    @property
    def improved(self) -> bool:
        """True when the fitted weights beat the baseline by a meaningful margin."""
        return self.fitted_brier < self.baseline_brier - 1e-9

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_names": list(self.source_names),
            "fitted_weights": dict(self.fitted_weights),
            "baseline_weights": dict(self.baseline_weights),
            "fitted_brier": self.fitted_brier,
            "baseline_brier": self.baseline_brier,
            "sample_count": self.sample_count,
            "improved": self.improved,
        }


def weather_baseline_weights() -> Dict[str, float]:
    """Current configured blend weights, keyed by blend source name."""
    from src.config import weather_config

    return {
        name: float(getattr(weather_config, attr))
        for name, attr in SOURCE_WEIGHT_FIELDS.items()
    }


def _clean_simplex(vector: Sequence[float]) -> List[float]:
    """Clip negatives and renormalize so weights are non-negative and sum to 1."""
    clipped = [max(0.0, float(v)) for v in vector]
    total = sum(clipped)
    if total <= 0:
        n = len(clipped)
        return [1.0 / n] * n if n else []
    return [v / total for v in clipped]


def _normalize_weights(
    weights: Mapping[str, float], source_names: Sequence[str]
) -> List[float]:
    raw = [max(0.0, float(weights.get(name, 0.0))) for name in source_names]
    return _clean_simplex(raw)


def _mean_brier(
    weights: Sequence[float], vectors: Sequence[Tuple[List[float], int]]
) -> float:
    total = 0.0
    for probs, actual in vectors:
        blended = sum(w * p for w, p in zip(weights, probs))
        blended = min(1.0, max(0.0, blended))
        total += (blended - actual) ** 2
    return total / len(vectors)


def fit_ensemble_weights(
    samples: Sequence[WeightSample],
    source_names: Sequence[str],
    baseline_weights: Optional[Mapping[str, float]] = None,
) -> WeightFitResult:
    """Fit blend weights that minimize Brier score against realized outcomes.

    Args:
        samples: rows of (per-source probabilities, settled outcome 0/1).
        source_names: ordered blend sources to fit weights for.
        baseline_weights: weights to compare against (defaults to uniform).

    Returns a WeightFitResult with the fitted weights, the baseline, and the
    Brier score for each so callers can decide whether to adopt the update.
    """
    if not samples:
        raise ValueError("at least one sample is required to fit weights")
    names = list(source_names)
    if not names:
        raise ValueError("at least one source is required to fit weights")

    vectors: List[Tuple[List[float], int]] = [
        ([float(probs.get(name, 0.0)) for name in names], int(actual))
        for probs, actual in samples
    ]

    if baseline_weights is None:
        baseline_vec = [1.0 / len(names)] * len(names)
    else:
        baseline_vec = _normalize_weights(baseline_weights, names)

    from scipy.optimize import minimize

    result = minimize(
        lambda w: _mean_brier(w, vectors),
        x0=baseline_vec,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(names),
        constraints=[{"type": "eq", "fun": lambda w: sum(w) - 1.0}],
        options={"maxiter": 200, "ftol": 1e-9},
    )

    fitted_vec = _clean_simplex(list(result.x))
    # Keep whichever of {baseline, fitted} actually scores better — the optimizer
    # can land marginally worse after simplex cleanup on already-optimal inputs.
    if _mean_brier(fitted_vec, vectors) > _mean_brier(baseline_vec, vectors):
        fitted_vec = list(baseline_vec)

    return WeightFitResult(
        source_names=names,
        fitted_weights={name: round(w, 6) for name, w in zip(names, fitted_vec)},
        baseline_weights={name: round(w, 6) for name, w in zip(names, baseline_vec)},
        fitted_brier=round(_mean_brier(fitted_vec, vectors), 6),
        baseline_brier=round(_mean_brier(baseline_vec, vectors), 6),
        sample_count=len(samples),
    )


# Maps blend source name -> the WeatherForecast row attribute holding its prob.
FORECAST_PROB_FIELDS = {
    "ecmwf": "ecmwf_prob",
    "gefs": "gefs_prob",
    "analog": "analog_prob",
    "microclimate": "microclimate_prob",
    "nws_delta": "nws_delta",
}


def build_weight_samples(
    forecasts: Iterable[Any],
    resolver: SettlementResolver,
    source_names: Optional[Sequence[str]] = None,
) -> List[WeightSample]:
    """Join persisted weather forecasts to settlements into weight-fit samples.

    Each forecast row must expose per-source probability attributes and a
    ``market_ticker``. Forecasts whose ticker has no settled outcome are skipped.
    """
    names = list(source_names or FORECAST_PROB_FIELDS.keys())
    settled = set(resolver.tickers)
    samples: List[WeightSample] = []
    for forecast in forecasts:
        ticker = getattr(forecast, "market_ticker", None)
        if not ticker or ticker not in settled:
            continue
        outcome = resolver.require_outcome(ticker)
        probs = {}
        for name in names:
            attr = FORECAST_PROB_FIELDS.get(name, name)
            value = getattr(forecast, attr, None)
            probs[name] = float(value) if value is not None else 0.0
        actual = 1 if outcome.winning_side.lower() == "yes" else 0
        samples.append((probs, actual))
    return samples


async def fit_persisted_weights(
    state: StateManager,
    resolver: SettlementResolver,
    *,
    source_names: Optional[Sequence[str]] = None,
    strategy: str | None = None,
    market_category: str | None = None,
    limit: int = 1000,
) -> WeightFitResult:
    """Fit blend weights from stored forecasts joined to settlement outcomes."""
    forecasts = await state.get_weather_forecasts(
        strategy=strategy, market_category=market_category, limit=limit
    )
    names = list(source_names or FORECAST_PROB_FIELDS.keys())
    samples = build_weight_samples(forecasts, resolver, names)
    baseline_all = weather_baseline_weights()
    baseline = {name: baseline_all.get(name, 0.0) for name in names}
    return fit_ensemble_weights(samples, names, baseline)
