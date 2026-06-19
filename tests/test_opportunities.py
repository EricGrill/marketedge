from datetime import datetime, timedelta

from src.opportunities import OpportunityCandidate, OpportunityScanner


def test_opportunity_scanner_ranks_clear_buy_yes_first():
    candidate = OpportunityCandidate(
        ticker="HIGHNY-TEST-B88.5",
        title="NYC daily high test",
        model_probability=0.85,
        yes_bid=39,
        yes_ask=40,
        confidence=0.9,
        volume=100_000,
        resolution_date=datetime.utcnow() + timedelta(days=7),
    )

    results = OpportunityScanner().rank([candidate], bankroll=1_000)

    assert results[0].ticker == "HIGHNY-TEST-B88.5"
    assert results[0].action == "BUY_YES"
    assert "EDGE_OK" in results[0].reason_codes
    assert results[0].recommended_bet_dollars > 0


def test_opportunity_scanner_surfaces_low_confidence_and_wide_spread():
    candidate = OpportunityCandidate(
        ticker="RAINMIA-TEST",
        model_probability=0.75,
        yes_bid=20,
        yes_ask=70,
        confidence=0.3,
        resolution_date=datetime.utcnow() + timedelta(days=7),
    )

    results = OpportunityScanner().rank([candidate], bankroll=1_000)
    yes_result = next(result for result in results if result.side == "yes")

    assert yes_result.action in {"HOLD", "PASS"}
    assert "LOW_CONFIDENCE" in yes_result.reason_codes
    assert "SPREAD_TOO_WIDE" in yes_result.reason_codes
