from datetime import datetime, timedelta

import pytest

from src.backtesting import BacktestEngine, BacktestTradeInput, load_trades_csv


def test_backtest_replays_trades_into_metrics():
    start = datetime(2026, 6, 18, 14, 0)
    trades = [
        BacktestTradeInput(
            timestamp=start,
            ticker="HIGHNY-26JUN18-B88.5",
            side="yes",
            entry_price=40,
            exit_price=100,
            quantity=10,
            model_probability=0.62,
            confidence=0.80,
            entry_fee=0.30,
            exit_fee=0.20,
        ),
        BacktestTradeInput(
            timestamp=start + timedelta(minutes=5),
            ticker="RAINMIA-26JUN18-YES",
            side="no",
            entry_price=35,
            exit_price=0,
            quantity=20,
            model_probability=0.40,
            confidence=0.60,
            entry_fee=0.40,
            exit_fee=0.30,
        ),
    ]

    summary = BacktestEngine().run(trades, initial_bankroll=1_000)

    assert summary.total_trades == 2
    assert summary.wins == 1
    assert summary.losses == 1
    assert summary.win_rate == 0.5
    assert summary.gross_pnl == pytest.approx(-1.0)
    assert summary.total_fees == pytest.approx(1.2)
    assert summary.net_pnl == pytest.approx(-2.2)
    assert summary.ending_bankroll == pytest.approx(997.8)
    assert summary.return_pct == pytest.approx(-0.0022)
    assert summary.profit_factor == pytest.approx(5.5 / 7.7)
    assert summary.average_edge == pytest.approx((0.62 - 0.40 + 0.40 - 0.35) / 2)
    assert summary.average_confidence == pytest.approx(0.70)
    assert summary.max_drawdown == pytest.approx(7.7 / 1005.5)
    assert len(summary.equity_curve) == 2
    assert summary.equity_curve[-1].equity == pytest.approx(997.8)


def test_backtest_empty_input_returns_neutral_summary():
    summary = BacktestEngine().run([], initial_bankroll=5_000)

    assert summary.total_trades == 0
    assert summary.wins == 0
    assert summary.losses == 0
    assert summary.win_rate == 0
    assert summary.net_pnl == 0
    assert summary.ending_bankroll == 5_000
    assert summary.max_drawdown == 0
    assert summary.profit_factor == 0
    assert summary.equity_curve == []


def test_backtest_validates_trade_bounds():
    bad_trade = BacktestTradeInput(
        timestamp=datetime(2026, 6, 18, 14, 0),
        ticker="BAD",
        side="yes",
        entry_price=101,
        exit_price=0,
        quantity=1,
        model_probability=0.50,
    )

    with pytest.raises(ValueError, match="entry_price"):
        BacktestEngine().run([bad_trade], initial_bankroll=1_000)


def test_load_trades_csv_parses_required_and_optional_fields(tmp_path):
    csv_path = tmp_path / "trades.csv"
    csv_path.write_text(
        "\n".join(
            [
                "timestamp,ticker,side,entry_price,exit_price,quantity,"
                "model_probability,confidence,entry_fee,exit_fee,region",
                "2026-06-18T14:00:00,HIGHNY-26JUN18-B88.5,yes,40,100,"
                "10,0.62,0.8,0.3,0.2,NYC",
            ]
        )
    )

    trades = load_trades_csv(csv_path)

    assert len(trades) == 1
    assert trades[0].ticker == "HIGHNY-26JUN18-B88.5"
    assert trades[0].quantity == 10
    assert trades[0].entry_fee == 0.3
    assert trades[0].metadata == {"region": "NYC"}
