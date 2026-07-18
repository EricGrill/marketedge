# marketedge/tests/test_weight_fitting.py
"""Tests for learned ensemble weights (CHA-2243).

The blend weights should be fit from realized outcomes, not hand-set. These
tests assert that a mis-weighted ensemble is corrected toward the source that
actually predicts, that the fit never scores worse than its baseline, and that
the output stays a valid convex combination.
"""

from datetime import datetime

import pytest

from src.calibration import (
    SOURCE_WEIGHT_FIELDS,
    build_weight_samples,
    fit_ensemble_weights,
    fit_persisted_weights,
    weather_baseline_weights,
)
from src.settlements import SettlementOutcome, SettlementResolver
from src.state import StateManager


def _outcome_samples(n=40):
    """Alternating settled outcomes with a 'good' and a 'bad' source.

    'good' tracks the outcome (0.9 when it happens, 0.1 when it doesn't);
    'bad' is anti-correlated. A Brier-minimizing fit should favor 'good'.
    """
    samples = []
    for i in range(n):
        actual = i % 2
        good = 0.9 if actual == 1 else 0.1
        bad = 0.1 if actual == 1 else 0.9
        samples.append(({"good": good, "bad": bad}, actual))
    return samples


def test_fit_shifts_weight_to_the_predictive_source():
    samples = _outcome_samples()
    baseline = {"good": 0.5, "bad": 0.5}
    result = fit_ensemble_weights(samples, ["good", "bad"], baseline)

    assert result.fitted_weights["good"] > result.fitted_weights["bad"]
    assert result.fitted_weights["good"] > baseline["good"]
    assert result.improved is True
    assert result.fitted_brier < result.baseline_brier


def test_fitted_weights_form_a_valid_simplex():
    result = fit_ensemble_weights(_outcome_samples(), ["good", "bad"])
    weights = result.fitted_weights.values()
    assert all(w >= 0 for w in weights)
    assert sum(weights) == pytest.approx(1.0, abs=1e-6)


def test_fit_never_scores_worse_than_baseline():
    # A baseline that already backs the good source entirely.
    samples = _outcome_samples()
    result = fit_ensemble_weights(samples, ["good", "bad"], {"good": 1.0, "bad": 0.0})
    assert result.fitted_brier <= result.baseline_brier + 1e-9


def test_fit_requires_samples():
    with pytest.raises(ValueError):
        fit_ensemble_weights([], ["good", "bad"])


def test_fit_requires_sources():
    with pytest.raises(ValueError):
        fit_ensemble_weights(_outcome_samples(), [])


def test_baseline_defaults_to_uniform():
    result = fit_ensemble_weights(_outcome_samples(), ["good", "bad"])
    assert result.baseline_weights == {"good": 0.5, "bad": 0.5}


def test_weather_baseline_weights_match_config_and_sum_to_one():
    weights = weather_baseline_weights()
    assert set(weights) == set(SOURCE_WEIGHT_FIELDS)
    assert sum(weights.values()) == pytest.approx(1.0)


# ========== persisted end-to-end ==========


def _settlements():
    return SettlementResolver(
        [
            SettlementOutcome(
                ticker="RAIN-YES",
                settled_at=datetime(2026, 6, 18, 20, 0),
                winning_side="yes",
                yes_settlement_price=100,
            ),
            SettlementOutcome(
                ticker="RAIN-NO",
                settled_at=datetime(2026, 6, 18, 20, 0),
                winning_side="no",
                yes_settlement_price=0,
            ),
        ]
    )


def _forecast(ticker, ecmwf, gefs):
    return {
        "location": "NYC",
        "event_type": "rain",
        "forecast_cycle": datetime(2026, 6, 18, 12, 0),
        "ecmwf_prob": ecmwf,
        "gefs_prob": gefs,
        "analog_prob": 0.5,
        "microclimate_prob": 0.5,
        "nws_delta": 0.5,
        "blended_probability": 0.5,
        "confidence": 0.8,
        "market_ticker": ticker,
        "market_price": 50,
        "strategy": "weather",
        "model_version": "weather-heuristic-v1",
        "market_category": "weather",
        "source_metadata": {"sources": ["fixture"]},
        "feature_metadata": {"threshold": 1.0},
    }


@pytest.mark.asyncio
async def test_build_samples_skips_unsettled_forecasts():
    class Row:
        def __init__(self, ticker):
            self.market_ticker = ticker
            self.ecmwf_prob = 0.6
            self.gefs_prob = 0.4

    samples = build_weight_samples(
        [Row("RAIN-YES"), Row("UNSETTLED")], _settlements(), ["ecmwf", "gefs"]
    )
    assert len(samples) == 1
    probs, actual = samples[0]
    assert actual == 1  # RAIN-YES settled yes
    assert probs == {"ecmwf": 0.6, "gefs": 0.4}


@pytest.mark.asyncio
async def test_fit_persisted_weights_end_to_end(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    # ecmwf tracks the outcome; gefs is anti-correlated.
    await state.add_weather_forecast(_forecast("RAIN-YES", ecmwf=0.9, gefs=0.1))
    await state.add_weather_forecast(_forecast("RAIN-NO", ecmwf=0.1, gefs=0.9))

    result = await fit_persisted_weights(state, _settlements())
    assert result.sample_count == 2
    assert result.fitted_weights["ecmwf"] > result.fitted_weights["gefs"]
    assert result.fitted_brier <= result.baseline_brier + 1e-9
