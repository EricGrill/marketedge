import pytest

from src.orders import OrderLedger, OrderState
from src.state import StateManager
from src.strategies.weather import TradeSignal, WeatherTradingStrategy


class FakeKalshiClient:
    def __init__(self, response):
        self.response = response
        self.orders = []

    async def place_order(self, **kwargs):
        self.orders.append(kwargs)
        return self.response


class EmptyWeatherScanner:
    async def scan_weather_markets(self, limit=100):
        return []


def _signal(quantity=5):
    return TradeSignal(
        ticker="RAIN-NYC-TEST",
        side="yes",
        action="buy",
        entry_price=40,
        quantity=quantity,
        model_probability=0.65,
        market_probability=0.40,
        edge=0.22,
        iy_annualized=1.1,
        kelly_fraction=0.05,
        confidence=0.8,
        reason="rain @ NYC: model=65.00%, market=40.00%",
        passes_screen=True,
    )


@pytest.mark.asyncio
async def test_strategy_rejects_failed_order_without_recording_position(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    strategy = WeatherTradingStrategy(
        state,
        FakeKalshiClient({"error": "venue rejected"}),
        order_ledger=ledger,
    )

    result = await strategy.execute_signal(_signal())
    order_id = ledger.events()[0].order_id
    record = ledger.get(order_id)

    assert result["success"] is False
    assert record.state == OrderState.REJECTED
    assert await state.get_open_positions() == []


@pytest.mark.asyncio
async def test_strategy_records_position_from_partial_fill_only(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    strategy = WeatherTradingStrategy(
        state,
        FakeKalshiClient(
            {
                "order": {
                    "status": "partially_filled",
                    "filled_quantity": 2,
                    "average_price": 42,
                }
            }
        ),
        order_ledger=ledger,
    )

    result = await strategy.execute_signal(_signal(quantity=5))
    position = await state.get_position(result["position_id"])

    assert result["success"] is True
    assert result["order_record"].state == OrderState.PARTIALLY_FILLED
    assert position.quantity == 2
    assert position.entry_price == 0.42
    assert position.position_pct_of_bankroll == pytest.approx(0.000084)


@pytest.mark.asyncio
async def test_strategy_keeps_open_order_without_position_when_unfilled(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    strategy = WeatherTradingStrategy(
        state,
        FakeKalshiClient({"order": {"status": "open"}}),
        order_ledger=ledger,
    )

    result = await strategy.execute_signal(_signal(quantity=5))
    order_id = ledger.events()[0].order_id

    assert result["success"] is True
    assert result["position_id"] is None
    assert ledger.get(order_id).state == OrderState.PENDING
    assert await state.get_open_positions() == []


@pytest.mark.asyncio
async def test_strategy_uses_dashboard_sample_markets_when_dry_run_scan_is_empty(
    tmp_path,
):
    state = StateManager(str(tmp_path / "state.db"))
    strategy = WeatherTradingStrategy(
        state,
        FakeKalshiClient({}),
        use_sample_markets_if_empty=True,
        execute_orders=False,
    )
    strategy.scanner = EmptyWeatherScanner()

    evaluated = []

    async def fake_evaluate(market, bankroll):
        evaluated.append(market)
        return None

    strategy._evaluate_market = fake_evaluate

    signals = await strategy.scan_and_evaluate()

    assert signals == []
    assert len(evaluated) == 9
    assert evaluated[0]["ticker"] == "HIGHNY-26JUN18-B88.5"
    assert evaluated[-1]["ticker"] == "HIGHBOS-26JUN18-B79.5"


@pytest.mark.asyncio
async def test_continuous_dry_run_logs_signals_without_executing_orders(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    strategy = WeatherTradingStrategy(
        state,
        FakeKalshiClient({"order": {"status": "filled"}}),
        execute_orders=False,
    )
    executed = []

    async def fake_scan():
        strategy.running = False
        return [_signal()]

    async def fake_execute(signal):
        executed.append(signal)

    async def fake_check_exits():
        return None

    strategy.scan_and_evaluate = fake_scan
    strategy.execute_signal = fake_execute
    strategy._check_exits = fake_check_exits

    await strategy.run_continuous(interval_seconds=0)

    assert executed == []

    events = await state.list_audit_events()
    event_types = {event.event_type for event in events}
    assert "risk_decision" in event_types
    assert "dry_run_order_review" in event_types


@pytest.mark.asyncio
async def test_strategy_blocks_order_before_venue_when_risk_policy_refuses(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    client = FakeKalshiClient({"order": {"status": "filled"}})
    strategy = WeatherTradingStrategy(state, client, order_ledger=ledger)

    result = await strategy.execute_signal(_signal(quantity=10_000))

    assert result["success"] is False
    assert result["error"] == "risk policy blocked order"
    assert client.orders == []
    assert ledger.events() == []

    events = await state.list_audit_events()
    assert {event.event_type for event in events} == {"order_intent", "risk_decision"}
