from datetime import datetime, timedelta, timezone

from src.formulas import QuantEngine


def _position(**overrides):
    base = {
        "ticker": "RAIN-NYC-TEST",
        "side": "yes",
        "entry_price": 40.0,
        "quantity": 10,
        "model_probability": 0.65,
        "city": "NYC",
        "region": "northeast",
        "event_type": "rain",
        "resolution_date": datetime.now(timezone.utc) + timedelta(days=7),
        "correlation_group": "nyc-rain-week",
    }
    base.update(overrides)
    return base


def test_risk_summary_keeps_independent_positions_unflagged():
    summary = QuantEngine().summarize_correlated_risk(
        [
            _position(ticker="RAIN-NYC-TEST", city="NYC", event_type="rain"),
            _position(
                ticker="TEMP-SEA-TEST",
                city="SEA",
                region="west",
                event_type="temperature",
                correlation_group="sea-temp-week",
            ),
        ],
        bankroll=10_000,
    )

    assert summary["position_count"] == 2
    assert summary["total_exposure"] == 8.0
    assert summary["overexposed_clusters"] == []
    assert summary["hedge_candidates"] == []


def test_risk_summary_flags_same_region_concentration():
    summary = QuantEngine().summarize_correlated_risk(
        [
            _position(ticker="RAIN-NYC-TEST", city="NYC", quantity=5_000),
            _position(
                ticker="RAIN-BOS-TEST",
                city="BOS",
                quantity=5_000,
                correlation_group="bos-rain-week",
            ),
        ],
        bankroll=10_000,
    )

    northeast = summary["groups"]["region"][0]
    assert northeast["key"] == "northeast"
    assert northeast["exposure"] == 4000.0
    assert northeast["exposure_pct_of_bankroll"] == 0.4
    assert northeast["overexposed"] is True
    assert "over_correlated_exposure_limit" in northeast["reason_codes"]


def test_risk_summary_flags_same_event_type_concentration():
    summary = QuantEngine().summarize_correlated_risk(
        [
            _position(ticker="RAIN-NYC-TEST", city="NYC", quantity=4_000),
            _position(
                ticker="RAIN-SEA-TEST",
                city="SEA",
                region="west",
                quantity=4_000,
                correlation_group="sea-rain-week",
            ),
        ],
        bankroll=10_000,
    )

    rain = summary["groups"]["event_type"][0]
    assert rain["key"] == "rain"
    assert rain["exposure"] == 3200.0
    assert rain["overexposed"] is True
    assert rain["position_count"] == 2


def test_risk_summary_surfaces_inverse_position_hedges():
    resolution_date = datetime.now(timezone.utc) + timedelta(days=7)

    summary = QuantEngine().summarize_correlated_risk(
        [
            _position(
                ticker="RAIN-NYC-YES",
                side="yes",
                quantity=100,
                resolution_date=resolution_date,
            ),
            _position(
                ticker="RAIN-NYC-NO",
                side="no",
                quantity=80,
                resolution_date=resolution_date,
            ),
        ],
        bankroll=10_000,
    )

    assert summary["hedge_candidates"] == [
        {
            "long_ticker": "RAIN-NYC-YES",
            "short_ticker": "RAIN-NYC-NO",
            "shared_group": "nyc-rain-week",
            "hedged_exposure": 32.0,
            "reason_codes": ["inverse_position", "shared_risk_bucket"],
        }
    ]
