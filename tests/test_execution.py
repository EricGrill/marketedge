from datetime import datetime

import pytest

from src.backtesting import BacktestEngine, BacktestTradeInput
from src.execution import (
    ExecutionAssumptions,
    ExecutionModel,
    ExecutionModelError,
    ExecutionOrder,
    OrderBookLevel,
    OrderBookSnapshot,
)


def test_execution_crosses_spread_and_computes_average_fill_price():
    book = OrderBookSnapshot(
        asks=[
            OrderBookLevel(price=40, quantity=100),
            OrderBookLevel(price=41, quantity=100),
        ]
    )

    result = ExecutionModel().fill(
        ExecutionOrder(action="buy", contract_side="yes", quantity=120),
        book,
    )

    assert result.fully_filled is True
    assert result.filled_quantity == 120
    assert result.unfilled_quantity == 0
    assert result.average_price == pytest.approx((40 * 100 + 41 * 20) / 120)


def test_execution_supports_partial_fill_when_depth_is_insufficient():
    book = OrderBookSnapshot(
        asks=[
            OrderBookLevel(price=40, quantity=100),
            OrderBookLevel(price=41, quantity=50),
        ]
    )

    result = ExecutionModel().fill(
        ExecutionOrder(action="buy", contract_side="yes", quantity=300),
        book,
    )

    assert result.fully_filled is False
    assert result.filled_quantity == 150
    assert result.unfilled_quantity == 150


def test_execution_sells_against_bid_depth():
    book = OrderBookSnapshot(
        bids=[
            OrderBookLevel(price=39, quantity=50),
            OrderBookLevel(price=38, quantity=100),
        ]
    )

    result = ExecutionModel().fill(
        ExecutionOrder(action="sell", contract_side="yes", quantity=120),
        book,
    )

    assert result.filled_quantity == 120
    assert result.average_price == pytest.approx((39 * 50 + 38 * 70) / 120)


def test_execution_returns_no_fill_when_limit_is_not_marketable():
    book = OrderBookSnapshot(asks=[OrderBookLevel(price=40, quantity=100)])

    result = ExecutionModel().fill(
        ExecutionOrder(
            action="buy",
            contract_side="yes",
            quantity=50,
            limit_price=39,
        ),
        book,
    )

    assert result.filled is False
    assert result.filled_quantity == 0
    assert result.average_price == 0


def test_execution_applies_queue_and_slippage_assumptions():
    book = OrderBookSnapshot(
        asks=[OrderBookLevel(price=50, quantity=100)],
        recent_volume=80,
    )
    model = ExecutionModel(
        ExecutionAssumptions(
            slippage_bps=100,
            queue_ahead_fraction=0.25,
            max_volume_participation=0.5,
        )
    )

    result = model.fill(
        ExecutionOrder(action="buy", contract_side="yes", quantity=100),
        book,
    )

    assert result.filled_quantity == 40
    assert result.unfilled_quantity == 60
    assert result.average_price == pytest.approx(50.5)


def test_execution_result_can_feed_backtest_with_effective_fill_metadata():
    trade = BacktestTradeInput(
        timestamp=datetime(2026, 6, 18, 14, 0),
        ticker="HIGHNY-26JUN18-B88.5",
        side="yes",
        entry_price=40,
        exit_price=100,
        quantity=120,
        model_probability=0.62,
    )
    book = OrderBookSnapshot(
        asks=[
            OrderBookLevel(price=40, quantity=100),
            OrderBookLevel(price=41, quantity=100),
        ]
    )
    model = ExecutionModel()
    execution = model.fill(
        ExecutionOrder(action="buy", contract_side="yes", quantity=120),
        book,
    )

    executed_trade = model.apply_to_backtest_trade(trade, execution)
    summary = BacktestEngine().run([executed_trade], initial_bankroll=1_000)

    assert executed_trade.quantity == 120
    assert executed_trade.entry_price == pytest.approx((40 * 100 + 41 * 20) / 120)
    assert summary.trades[0].metadata["requested_quantity"] == 120
    assert summary.trades[0].metadata["filled_quantity"] == 120
    assert summary.to_dict()["trades"][0]["metadata"][
        "effective_entry_price"
    ] == pytest.approx((40 * 100 + 41 * 20) / 120)


def test_unfilled_execution_cannot_feed_backtest():
    trade = BacktestTradeInput(
        timestamp=datetime(2026, 6, 18, 14, 0),
        ticker="HIGHNY-26JUN18-B88.5",
        side="yes",
        entry_price=40,
        exit_price=100,
        quantity=120,
        model_probability=0.62,
    )
    result = ExecutionModel().fill(
        ExecutionOrder(action="buy", contract_side="yes", quantity=120),
        OrderBookSnapshot(),
    )

    with pytest.raises(ExecutionModelError, match="unfilled execution"):
        ExecutionModel().apply_to_backtest_trade(trade, result)
