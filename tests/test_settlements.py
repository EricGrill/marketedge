from datetime import datetime

import pytest

from src.backtesting import BacktestEngine, BacktestTradeInput
from src.settlements import (
    SettlementOutcome,
    SettlementResolver,
    SettlementValidationError,
    load_settlements_csv,
    load_settlements_jsonl,
)


def test_settlement_resolver_joins_trades_to_outcomes_by_ticker():
    trade = BacktestTradeInput(
        timestamp=datetime(2026, 6, 18, 14, 0),
        ticker="HIGHNY-26JUN18-B88.5",
        side="yes",
        entry_price=40,
        exit_price=0,
        quantity=10,
        model_probability=0.62,
    )
    resolver = SettlementResolver(
        [
            SettlementOutcome(
                ticker="HIGHNY-26JUN18-B88.5",
                settled_at=datetime(2026, 6, 18, 20, 0),
                winning_side="yes",
                yes_settlement_price=100,
                source="fixture",
            )
        ]
    )

    settled = resolver.settle_trades([trade])
    summary = BacktestEngine().run(settled, initial_bankroll=1_000)

    assert settled[0].exit_price == 100
    assert settled[0].metadata["winning_side"] == "yes"
    assert summary.net_pnl == pytest.approx(6.0)


def test_settlement_resolver_reports_missing_outcomes():
    trade = BacktestTradeInput(
        timestamp=datetime(2026, 6, 18, 14, 0),
        ticker="MISSING",
        side="yes",
        entry_price=40,
        exit_price=0,
        quantity=10,
        model_probability=0.62,
    )
    resolver = SettlementResolver([])

    report = resolver.validate_trades([trade])

    assert report.ok is False
    assert report.missing_tickers == ["MISSING"]
    with pytest.raises(SettlementValidationError, match="missing outcomes: MISSING"):
        report.raise_for_errors()
    with pytest.raises(SettlementValidationError, match="missing settlement outcome"):
        resolver.settle_trades([trade])


def test_settlement_resolver_rejects_duplicate_outcomes():
    outcome = SettlementOutcome(
        ticker="DUP",
        settled_at=datetime(2026, 6, 18, 20, 0),
        winning_side="no",
        yes_settlement_price=0,
    )

    with pytest.raises(
        SettlementValidationError, match="duplicate settlement outcomes"
    ):
        SettlementResolver([outcome, outcome])


def test_settlement_outcome_rejects_inconsistent_winner_and_price():
    with pytest.raises(SettlementValidationError, match="inconsistent settlement"):
        SettlementOutcome(
            ticker="BAD",
            settled_at=datetime(2026, 6, 18, 20, 0),
            winning_side="yes",
            yes_settlement_price=0,
        )


def test_load_settlements_jsonl_rejects_inconsistent_numeric_zero(tmp_path):
    path = tmp_path / "settlements.jsonl"
    path.write_text(
        '{"ticker":"BAD","settled_at":"2026-06-18T20:00:00",'
        '"winning_side":"yes","settlement_value":0}\n'
    )

    with pytest.raises(SettlementValidationError, match="inconsistent settlement"):
        load_settlements_jsonl(path)


def test_load_settlements_csv_parses_records_and_metadata(tmp_path):
    path = tmp_path / "settlements.csv"
    path.write_text(
        "\n".join(
            [
                "ticker,settled_at,winning_side,yes_settlement_price,source,region",
                "HIGHNY-26JUN18-B88.5,2026-06-18T20:00:00,yes,100,manual,NYC",
            ]
        )
    )

    outcomes = load_settlements_csv(path)

    assert outcomes[0].ticker == "HIGHNY-26JUN18-B88.5"
    assert outcomes[0].settlement_price_for("no") == 0
    assert outcomes[0].metadata == {"region": "NYC"}


def test_load_settlements_jsonl_parses_records(tmp_path):
    path = tmp_path / "settlements.jsonl"
    path.write_text(
        '{"ticker":"RAINMIA-26JUN18-YES","settled_at":"2026-06-18T20:00:00",'
        '"winning_side":"no","settlement_value":0,"source":"manual"}\n'
    )

    outcomes = load_settlements_jsonl(path)

    assert outcomes[0].ticker == "RAINMIA-26JUN18-YES"
    assert outcomes[0].settlement_price_for("no") == 100
