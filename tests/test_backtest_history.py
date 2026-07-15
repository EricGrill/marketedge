# marketedge/tests/test_backtest_history.py
"""Closing the research loop: persisted forecasts -> backtest (CHA-2244).

These tests cover trades_from_forecasts, which synthesizes backtestable trades
from stored forecast calls joined to settlement outcomes, and the end-to-end
path from SQLite state through the BacktestEngine.
"""

from datetime import datetime

import pytest

from src.backtesting import BacktestEngine, trades_from_forecasts
from src.settlements import SettlementOutcome, SettlementResolver
from src.state import StateManager


def _resolver():
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


class _Row:
    def __init__(self, ticker, blended, market_price):
        self.market_ticker = ticker
        self.blended_probability = blended
        self.market_price = market_price
        self.confidence = 0.8
        self.market_timestamp = datetime(2026, 6, 18, 12, 0)


def test_forecast_yes_call_that_wins_is_a_winning_trade():
    # blended >= 0.5 -> YES call; entry at market price, exit at 100 (yes won).
    trades = trades_from_forecasts([_Row("RAIN-YES", 0.8, 40)], _resolver())
    assert len(trades) == 1
    trade = trades[0]
    assert trade.side == "yes"
    assert trade.entry_price == 40
    assert trade.exit_price == 100  # yes settled true
    assert trade.model_probability == pytest.approx(0.8)


def test_forecast_no_call_prices_and_exits_on_no_side():
    # blended < 0.5 -> NO call; entry at 100 - market_price, exit at 100 (no won).
    trades = trades_from_forecasts([_Row("RAIN-NO", 0.2, 40)], _resolver())
    trade = trades[0]
    assert trade.side == "no"
    assert trade.entry_price == 60  # 100 - 40
    assert trade.exit_price == 100  # no settled true
    assert trade.model_probability == pytest.approx(0.8)  # 1 - blended


def test_unsettled_or_incomplete_forecasts_are_skipped():
    rows = [
        _Row("UNKNOWN", 0.8, 40),  # not settled
        _Row("RAIN-YES", None, 40),  # missing blended prob
        _Row("RAIN-YES", 0.8, None),  # missing market price
    ]
    assert trades_from_forecasts(rows, _resolver()) == []


@pytest.mark.asyncio
async def test_backtest_history_end_to_end(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    for ticker, blended in [("RAIN-YES", 0.8), ("RAIN-NO", 0.2)]:
        await state.add_weather_forecast(
            {
                "location": "NYC",
                "event_type": "rain",
                "forecast_cycle": datetime(2026, 6, 18, 12, 0),
                "ecmwf_prob": blended,
                "gefs_prob": blended,
                "analog_prob": blended,
                "microclimate_prob": blended,
                "nws_delta": blended,
                "blended_probability": blended,
                "confidence": 0.8,
                "market_ticker": ticker,
                "market_price": 40,
                "market_timestamp": datetime(2026, 6, 18, 12, 0),
                "strategy": "weather",
                "model_version": "weather-heuristic-v1",
                "market_category": "weather",
                "source_metadata": {"sources": ["fixture"]},
                "feature_metadata": {"threshold": 1.0},
            }
        )

    forecasts = await state.get_weather_forecasts()
    trades = trades_from_forecasts(forecasts, _resolver())
    summary = BacktestEngine().run(trades, initial_bankroll=1000.0)

    # Both calls were correct (yes won on RAIN-YES, no won on RAIN-NO).
    assert summary.total_trades == 2
    assert summary.win_rate == pytest.approx(1.0)
    assert summary.net_pnl > 0
