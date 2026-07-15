from datetime import datetime, timedelta, timezone

import pytest

from src.execution import OrderBookLevel, OrderBookSnapshot
from src.strategies.advanced import (
    CalibrationWeightedEnsembleStrategy,
    CatalystCalendarStrategy,
    LiquidityMicrostructureOverlay,
    ProbabilitySource,
    RelativeValueStrategy,
    SourceCalibration,
    load_catalysts_csv,
)


def _market(**overrides):
    base = {
        "ticker": "HIGHNY-26JUN18-B88.5",
        "title": "NYC Daily High above 88.5F",
        "yes_bid": 39,
        "yes_ask": 40,
        "event_ticker": "HIGHNY-26JUN18",
        "close_date": "2026-06-18T20:00:00Z",
    }
    base.update(overrides)
    return base


def test_relative_value_flags_threshold_ladder_inversion():
    opportunities = RelativeValueStrategy().evaluate(
        [
            _market(ticker="LOW", title="NYC Daily High above 80.5F", yes_ask=40),
            _market(ticker="HIGH", title="NYC Daily High above 90.5F", yes_ask=50),
        ]
    )

    assert opportunities[0].reason_codes == ["THRESHOLD_LADDER_INVERSION"]
    assert opportunities[0].legs[0]["action"] == "buy_yes"


def test_relative_value_flags_mutually_exclusive_overround():
    opportunities = RelativeValueStrategy().evaluate(
        [
            _market(ticker="A", outcome_set="set-1", yes_ask=70),
            _market(ticker="B", outcome_set="set-1", yes_ask=60),
        ]
    )

    assert any(
        "MUTUALLY_EXCLUSIVE_OVERROUND" in item.reason_codes for item in opportunities
    )


def test_relative_value_flags_correlated_region_dislocation_and_noops_consistent():
    dislocated = RelativeValueStrategy().evaluate(
        [
            _market(ticker="NYC", title="NYC Daily High above 80.5F", yes_ask=30),
            _market(
                ticker="BOS",
                title="Boston Daily High above 80.5F",
                yes_ask=70,
                event_ticker="HIGHBOS-26JUN18",
            ),
        ]
    )
    consistent = RelativeValueStrategy().evaluate(
        [
            _market(ticker="LOW", title="NYC Daily High above 80.5F", yes_ask=50),
            _market(ticker="HIGH", title="NYC Daily High above 90.5F", yes_ask=40),
        ]
    )

    assert any(
        "CORRELATED_REGION_DISLOCATION" in item.reason_codes for item in dislocated
    )
    assert consistent == []


def test_catalyst_calendar_imports_and_tags_active_window(tmp_path):
    path = tmp_path / "calendar.csv"
    path.write_text(
        "\n".join(
            [
                "catalyst_id,event_type,affected_tickers,window_start,window_end,confidence,rationale",
                "nws-1,weather,NWS-MKT,2026-06-18T10:00:00Z,2026-06-18T12:00:00Z,0.8,NWS update",
            ]
        )
    )
    records = load_catalysts_csv(path)

    opportunities = CatalystCalendarStrategy(records).evaluate(
        [
            _market(
                ticker="NWS-MKT",
                title="NYC Daily High above 80.5F",
            )
        ],
        as_of=datetime(2026, 6, 18, 11, tzinfo=timezone.utc),
    )

    assert opportunities[0].metadata["catalyst"]["catalyst_id"] == "nws-1"
    assert opportunities[0].metadata["timing"] == "inside_window"


def test_catalyst_calendar_no_catalyst_fallback_is_empty():
    opportunities = CatalystCalendarStrategy([]).evaluate([_market()])

    assert opportunities == []


def test_calibration_weighted_ensemble_prefers_better_history():
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    result = CalibrationWeightedEnsembleStrategy().blend(
        [
            ProbabilitySource("good", "weather", now, 0.70, confidence=0.9),
            ProbabilitySource("bad", "weather", now, 0.30, confidence=0.9),
        ],
        [
            SourceCalibration("good", "weather", 0.08, 0.30, 0.02, 50, now),
            SourceCalibration("bad", "weather", 0.30, 0.90, 0.20, 50, now),
        ],
        as_of=now,
    )

    weights = {
        item["source_id"]: item["weight"] for item in result["source_contributions"]
    }
    assert weights["good"] > weights["bad"]
    assert result["blended_probability"] > 0.5
    assert "BRIER_UPWEIGHT" in result["reason_codes"]


def test_calibration_weighted_ensemble_sparse_history_is_conservative():
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    result = CalibrationWeightedEnsembleStrategy().blend(
        [
            ProbabilitySource("a", "weather", now, 0.90, confidence=1.0),
            ProbabilitySource("b", "weather", now, 0.10, confidence=1.0),
        ],
        [SourceCalibration("a", "weather", sample_count=1)],
        as_of=now,
    )

    assert result["blended_probability"] == pytest.approx(0.5)
    assert "SPARSE_HISTORY_FALLBACK" in result["reason_codes"]


def test_calibration_weighted_ensemble_applies_recency_weighting():
    now = datetime(2026, 6, 18, tzinfo=timezone.utc)
    result = CalibrationWeightedEnsembleStrategy().blend(
        [
            ProbabilitySource("fresh", "weather", now, 0.80),
            ProbabilitySource("stale", "weather", now, 0.20),
        ],
        [
            SourceCalibration("fresh", "weather", 0.10, 0.40, 0.05, 20, now),
            SourceCalibration(
                "stale",
                "weather",
                0.10,
                0.40,
                0.05,
                20,
                now - timedelta(days=90),
            ),
        ],
        as_of=now,
    )

    weights = {
        item["source_id"]: item["weight"] for item in result["source_contributions"]
    }
    assert weights["fresh"] > weights["stale"]
    assert "RECENCY_WEIGHTED" in result["reason_codes"]


def test_liquidity_overlay_recommends_skip_wait_maker_reduce_and_take():
    overlay = LiquidityMicrostructureOverlay()

    thin = overlay.evaluate(
        OrderBookSnapshot(asks=[OrderBookLevel(40, 10)], bids=[OrderBookLevel(39, 10)]),
        side="yes",
        action="buy",
        target_quantity=100,
    )
    wide = overlay.evaluate(
        OrderBookSnapshot(
            asks=[OrderBookLevel(50, 100)], bids=[OrderBookLevel(40, 100)]
        ),
        side="yes",
        action="buy",
        target_quantity=50,
    )
    stale = overlay.evaluate(
        OrderBookSnapshot(
            asks=[OrderBookLevel(40, 100)], bids=[OrderBookLevel(39, 100)]
        ),
        side="yes",
        action="buy",
        target_quantity=50,
        quote_time=datetime(2026, 6, 18, 10, tzinfo=timezone.utc),
        as_of=datetime(2026, 6, 18, 10, 5, tzinfo=timezone.utc),
    )
    partial = overlay.evaluate(
        OrderBookSnapshot(
            asks=[OrderBookLevel(40, 80)], bids=[OrderBookLevel(39, 100)]
        ),
        side="yes",
        action="buy",
        target_quantity=100,
    )
    adequate = overlay.evaluate(
        OrderBookSnapshot(
            asks=[OrderBookLevel(40, 200)], bids=[OrderBookLevel(39, 200)]
        ),
        side="yes",
        action="buy",
        target_quantity=100,
    )

    assert thin.action == "skip"
    assert wide.action == "maker_only"
    assert stale.action == "wait"
    assert partial.action == "reduce_size"
    assert adequate.action == "take_liquidity"
    assert adequate.reason_codes == ["LIQUIDITY_OK"]


def test_liquidity_overlay_exports_backtest_fill_adjustment():
    result = LiquidityMicrostructureOverlay().apply_to_backtest_fill(
        OrderBookSnapshot(
            asks=[OrderBookLevel(40, 80)], bids=[OrderBookLevel(39, 100)]
        ),
        quantity=100,
        entry_price=40,
    )

    assert result["filled_quantity"] == 80
    assert result["unfilled_quantity"] == 20
    assert result["effective_entry_price"] == 40
