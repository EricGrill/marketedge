# marketedge/tests/test_formulas_extended.py
"""Extended coverage for QuantEngine (CHA-2242).

The core quant engine drives every screen; these tests pin down the math of
each public method — edge, Kelly sizing, annualized yield, liquidity spread,
overround, Bayesian update, model blend, risk-of-ruin, and correlation
exposure — including degenerate inputs and monotonicity invariants.
"""

from datetime import timedelta

import pytest

from src.config import trading_config, weather_config
from src.formulas import QuantEngine
from src.utils import utcnow


@pytest.fixture
def engine():
    return QuantEngine()


# ========== calculate_edge ==========


def test_edge_raw_edge_is_model_minus_market_prob(engine):
    edge = engine.calculate_edge(model_probability=0.65, market_price=50, side="yes")
    assert edge.market_probability == pytest.approx(0.50)
    assert edge.raw_edge == pytest.approx(0.15)


def test_edge_fee_adjusted_breakeven_formula(engine):
    edge = engine.calculate_edge(model_probability=0.50, market_price=40, side="yes")
    # breakeven = p / (1 + fee * p)
    expected = 0.50 / (1 + trading_config.settlement_fee_pct * 0.50)
    assert edge.fee_adjusted_breakeven == pytest.approx(expected)


def test_edge_no_side_inverts_both_probabilities(engine):
    edge = engine.calculate_edge(model_probability=0.65, market_price=30, side="no")
    # market_prob -> 1 - 0.30 = 0.70 ; model_prob -> 1 - 0.65 = 0.35
    assert edge.market_probability == pytest.approx(0.70)
    assert edge.model_probability == pytest.approx(0.35)
    assert edge.raw_edge == pytest.approx(-0.35)


def test_edge_positive_expected_value_when_model_beats_price(engine):
    edge = engine.calculate_edge(model_probability=0.60, market_price=50, side="yes")
    # ev = p*(1-price)*(1-fee) - (1-p)*price
    expected_ev = 0.60 * 0.50 * (1 - trading_config.settlement_fee_pct) - 0.40 * 0.50
    assert edge.expected_value == pytest.approx(expected_ev)
    assert edge.expected_value > 0


def test_edge_not_tradeable_when_ev_negative(engine):
    # Model far below the market price -> negative EV, not tradeable.
    edge = engine.calculate_edge(model_probability=0.20, market_price=80, side="yes")
    assert edge.expected_value < 0
    assert edge.is_tradeable is False


# ========== kelly_sizing ==========


def test_kelly_full_fraction_matches_formula(engine):
    edge = engine.calculate_edge(model_probability=0.60, market_price=50, side="yes")
    kelly = engine.kelly_sizing(edge, bankroll=1000.0, confidence=1.0)
    # b = 1/0.5 - 1 = 1.0 ; f* = (0.6*2 - 1)/1 = 0.20
    assert kelly.full_kelly_fraction == pytest.approx(0.20)
    # fractional = full * kelly_fraction
    assert kelly.fractional_kelly_fraction == pytest.approx(
        0.20 * trading_config.kelly_fraction
    )
    assert kelly.recommended_bet_dollars == pytest.approx(
        1000.0 * 0.20 * trading_config.kelly_fraction
    )


def test_kelly_caps_at_max_position_size(engine):
    # Huge modelled edge would size past the cap; recommended dollars must clamp.
    edge = engine.calculate_edge(model_probability=0.99, market_price=5, side="yes")
    kelly = engine.kelly_sizing(edge, bankroll=1000.0, confidence=1.0)
    max_position = 1000.0 * trading_config.max_position_pct
    assert kelly.max_position_size == pytest.approx(max_position)
    assert kelly.recommended_bet_dollars <= max_position + 1e-9


def test_kelly_zero_when_no_favorable_odds(engine):
    # market_price = 100 -> market_prob = 1.0 -> b <= 0 -> full kelly 0.
    edge = engine.calculate_edge(model_probability=0.60, market_price=100, side="yes")
    kelly = engine.kelly_sizing(edge, bankroll=1000.0)
    assert kelly.full_kelly_fraction == 0.0
    assert kelly.recommended_bet_dollars == 0.0


def test_kelly_confidence_scales_size_and_sets_flag(engine):
    edge = engine.calculate_edge(model_probability=0.60, market_price=50, side="yes")
    full = engine.kelly_sizing(edge, bankroll=1000.0, confidence=1.0)
    half = engine.kelly_sizing(edge, bankroll=1000.0, confidence=0.5)
    assert half.recommended_bet_dollars == pytest.approx(
        full.recommended_bet_dollars * 0.5
    )
    assert half.confidence_adjusted is True
    assert full.confidence_adjusted is False


def test_kelly_las_reduction_shrinks_size(engine):
    edge = engine.calculate_edge(model_probability=0.60, market_price=50, side="yes")
    las = engine.calculate_las(bid=47, ask=53)  # ratio 0.12 -> reduction 0.50
    assert las.recommended_size_reduction == pytest.approx(0.50)
    reduced = engine.kelly_sizing(edge, bankroll=1000.0, confidence=1.0, las_result=las)
    full = engine.kelly_sizing(edge, bankroll=1000.0, confidence=1.0)
    assert reduced.recommended_bet_dollars == pytest.approx(
        full.recommended_bet_dollars * 0.50
    )


# ========== calculate_iy ==========


def test_iy_doubling_price_over_one_year(engine):
    now = utcnow()
    iy = engine.calculate_iy(
        entry_price=50, resolution_date=now + timedelta(days=365), current_date=now
    )
    # (1/0.5)^(365/365) - 1 = 1.0
    assert iy.annualized_yield == pytest.approx(1.0)
    assert iy.is_above_threshold is True


def test_iy_expensive_contract_below_threshold(engine):
    now = utcnow()
    iy = engine.calculate_iy(
        entry_price=90, resolution_date=now + timedelta(days=365), current_date=now
    )
    # (1/0.9)^1 - 1 ~= 0.111 < 0.50 threshold
    assert iy.annualized_yield == pytest.approx(1 / 0.9 - 1)
    assert iy.is_above_threshold is False


def test_iy_nonpositive_horizon_is_clamped(engine):
    now = utcnow()
    iy = engine.calculate_iy(
        entry_price=50, resolution_date=now - timedelta(days=5), current_date=now
    )
    assert iy.days_to_resolution == pytest.approx(0.1)


# ========== calculate_las ==========


@pytest.mark.parametrize(
    "bid,ask,expected_reduction,expected_liquid",
    [
        (49, 51, 0.0, True),  # ratio 0.04  -> full size, liquid
        (48.5, 51.5, 0.25, True),  # ratio 0.06  -> quarter cut, liquid
        (47, 53, 0.50, False),  # ratio 0.12  -> half cut, illiquid
        (40, 60, 1.0, False),  # ratio 0.40  -> skip, illiquid
    ],
)
def test_las_tiers(engine, bid, ask, expected_reduction, expected_liquid):
    las = engine.calculate_las(bid=bid, ask=ask)
    assert las.recommended_size_reduction == pytest.approx(expected_reduction)
    assert las.is_liquid is expected_liquid


def test_las_guards_zero_mid(engine):
    las = engine.calculate_las(bid=0, ask=0)
    assert las.mid == pytest.approx(0.01)


# ========== calculate_overround ==========


def test_overround_positive_with_vig(engine):
    assert engine.calculate_overround([60, 50]) == pytest.approx(0.10)


def test_overround_negative_signals_arbitrage(engine):
    assert engine.calculate_overround([40, 40]) == pytest.approx(-0.20)


# ========== bayesian_update ==========


def test_bayesian_neutral_evidence_keeps_prior(engine):
    assert engine.bayesian_update(0.5, 0.5) == pytest.approx(0.5)


def test_bayesian_stronger_likelihood_raises_posterior(engine):
    low = engine.bayesian_update(0.5, 0.55)
    high = engine.bayesian_update(0.5, 0.80)
    assert high > low > 0.5


def test_bayesian_output_is_bounded(engine):
    assert engine.bayesian_update(0.99, 0.99) <= 0.99
    assert engine.bayesian_update(0.01, 0.01) >= 0.01


# ========== blend_weather_probabilities ==========


def test_blend_uniform_inputs_equal_weighted_value(engine):
    blended, _ = engine.blend_weather_probabilities(0.8, 0.8, 0.8, 0.8, 0.8)
    # weights sum to 1.0, so a uniform 0.8 blends to 0.8
    assert blended == pytest.approx(0.8)


def test_blend_confidence_inverse_to_spread(engine):
    _, tight = engine.blend_weather_probabilities(
        0.6, 0.6, 0.6, 0.6, 0.6, ensemble_spread=0.0
    )
    _, wide = engine.blend_weather_probabilities(
        0.6, 0.6, 0.6, 0.6, 0.6, ensemble_spread=0.5
    )
    assert tight == pytest.approx(1.0)
    assert wide == pytest.approx(0.1)


def test_blend_uses_configured_weights(engine):
    blended, _ = engine.blend_weather_probabilities(1.0, 0.0, 0.0, 0.0, 0.0)
    assert blended == pytest.approx(weather_config.ecmwf_weight)


# ========== calculate_ror ==========


def test_ror_is_one_without_edge(engine):
    assert engine.calculate_ror(edge=0.0, bet_size_fraction=0.05, bankroll=1000) == 1.0
    assert engine.calculate_ror(edge=-0.1, bet_size_fraction=0.05, bankroll=1000) == 1.0


def test_ror_is_one_with_nonpositive_bet_or_bankroll(engine):
    assert engine.calculate_ror(edge=0.1, bet_size_fraction=0.0, bankroll=1000) == 1.0
    assert engine.calculate_ror(edge=0.1, bet_size_fraction=0.05, bankroll=0) == 1.0


def test_ror_decreases_with_smaller_bet_fraction(engine):
    aggressive = engine.calculate_ror(edge=0.1, bet_size_fraction=0.20, bankroll=1000)
    conservative = engine.calculate_ror(edge=0.1, bet_size_fraction=0.05, bankroll=1000)
    assert 0.0 < conservative < aggressive < 1.0


# ========== correlation_exposure ==========


def test_correlation_weights_same_region_highest(engine):
    positions = [{"size": 100, "region": "northeast", "event_type": "rain"}]
    same_region = engine.correlation_exposure(
        positions, {"size": 100, "region": "northeast", "event_type": "temp"}
    )
    same_event = engine.correlation_exposure(
        [{"size": 100, "region": "west", "event_type": "rain"}],
        {"size": 100, "region": "northeast", "event_type": "rain"},
    )
    unrelated = engine.correlation_exposure(
        [{"size": 100, "region": "west", "event_type": "wind"}],
        {"size": 100, "region": "northeast", "event_type": "rain"},
    )
    assert same_region > same_event > unrelated


def test_correlation_exposure_new_position_against_empty_book(engine):
    # No existing book: the new position is 100% of total exposure.
    assert engine.correlation_exposure([], {"size": 100, "region": "northeast"}) == 1.0


def test_correlation_exposure_zero_total_is_zero(engine):
    # No exposure anywhere -> guarded to 0.0 rather than dividing by zero.
    assert engine.correlation_exposure([], {"size": 0, "region": "northeast"}) == 0.0


# ========== screen_opportunity ==========


def test_screen_returns_all_component_analyses(engine):
    now = utcnow()
    result = engine.screen_opportunity(
        model_prob=0.60,
        market_bid=48,
        market_ask=52,
        resolution_date=now + timedelta(days=30),
        bankroll=1000.0,
    )
    assert set(result) >= {
        "edge",
        "las",
        "iy",
        "kelly",
        "ror",
        "passes_screen",
        "recommended_action",
        "entry_price",
        "side",
    }
    # yes side enters at the ask
    assert result["entry_price"] == 52
    assert result["recommended_action"] == (
        "ENTER" if result["passes_screen"] else "PASS"
    )


def test_screen_no_side_prices_off_the_bid(engine):
    now = utcnow()
    result = engine.screen_opportunity(
        model_prob=0.60,
        market_bid=48,
        market_ask=52,
        resolution_date=now + timedelta(days=30),
        bankroll=1000.0,
        side="no",
    )
    assert result["entry_price"] == 100 - 48
