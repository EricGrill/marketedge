from datetime import timedelta

import pytest

from src.formulas import MAX_ANNUALIZED_YIELD, QuantEngine
from src.utils import utcnow


def test_iy_caps_extreme_annualized_yield():
    # A cheap contract (30c) resolving in a week annualizes to an astronomically
    # large figure (regression: it once printed 1.8e29 %). It must be capped, not
    # overflow, while still clearing the yield threshold.
    engine = QuantEngine()

    result = engine.calculate_iy(
        entry_price=30.0, resolution_date=utcnow() + timedelta(days=7)
    )

    assert result.annualized_yield == MAX_ANNUALIZED_YIELD
    assert result.is_above_threshold is True


def test_las_marks_wide_spread_as_unliquid_and_skips_size():
    engine = QuantEngine()

    result = engine.calculate_las(bid=30, ask=70)

    assert result.mid == 50
    assert result.spread == 40
    assert result.las_ratio == pytest.approx(0.8)
    assert result.is_liquid is False
    assert result.recommended_size_reduction == 1.0


def test_weather_blend_uses_configured_weights_and_confidence():
    engine = QuantEngine()

    blended, confidence = engine.blend_weather_probabilities(
        ecmwf=0.70,
        gefs=0.60,
        analog=0.50,
        microclimate=0.40,
        nws_delta=0.30,
        ensemble_spread=0.10,
    )

    assert blended == pytest.approx(0.55)
    assert confidence == pytest.approx(0.80)


def test_screen_opportunity_handles_zero_recommended_size():
    engine = QuantEngine()

    screen = engine.screen_opportunity(
        model_prob=0.90,
        market_bid=30,
        market_ask=70,
        resolution_date=utcnow() + timedelta(days=7),
        bankroll=10_000,
    )

    assert screen["las"].recommended_size_reduction == 1.0
    assert screen["kelly"].recommended_fraction == 0
    assert screen["ror"] == 1.0
    assert screen["passes_screen"] is False
    assert screen["recommended_action"] == "PASS"
