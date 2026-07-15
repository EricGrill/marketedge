import pytest

from src.risk_policy import OrderIntent, PreOrderRiskPolicy, RiskPolicyConfig
from src.state import StateManager


def _intent(**overrides):
    base = {
        "ticker": "RAIN-NYC-TEST",
        "side": "yes",
        "action": "buy",
        "quantity": 10,
        "limit_price": 40,
        "strategy_id": "weather",
        "region": "NYC",
        "event_type": "rain",
    }
    base.update(overrides)
    return OrderIntent(**base)


@pytest.mark.asyncio
async def test_risk_policy_allows_order_inside_limits(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))

    decision = await PreOrderRiskPolicy().evaluate(state, _intent())

    assert decision.allowed is True
    assert decision.reason_codes == ["APPROVED"]
    assert decision.projected_exposure == 4


@pytest.mark.asyncio
async def test_risk_policy_blocks_oversized_order(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))

    decision = await PreOrderRiskPolicy().evaluate(
        state,
        _intent(quantity=10_000, limit_price=40),
    )

    assert decision.allowed is False
    assert "MAX_POSITION_SIZE" in decision.reason_codes


@pytest.mark.asyncio
async def test_risk_policy_blocks_correlated_exposure(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    await state.add_position(
        {
            "ticker": "RAIN-NYC-OPEN",
            "event_title": "NYC rain",
            "side": "yes",
            "entry_price": 40.0,
            "quantity": 10_000,
            "status": "open",
            "model_probability": 0.6,
            "market_probability": 0.4,
            "edge_at_entry": 0.2,
            "iy_annualized": 1.0,
            "las_at_entry": 0.05,
            "kelly_fraction": 0.1,
            "weather_event_type": "rain",
            "location": "NYC",
            "position_pct_of_bankroll": 0.4,
        }
    )

    decision = await PreOrderRiskPolicy().evaluate(state, _intent())

    assert decision.allowed is False
    assert "MAX_CORRELATED_EXPOSURE" in decision.reason_codes


@pytest.mark.asyncio
async def test_risk_policy_blocks_daily_loss_and_total_notional(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    position_id = await state.add_position(
        {
            "ticker": "LOSS-TEST",
            "event_title": "loss",
            "side": "yes",
            "entry_price": 40.0,
            "quantity": 10_000,
            "status": "open",
            "model_probability": 0.6,
            "market_probability": 0.4,
            "edge_at_entry": 0.2,
            "iy_annualized": 1.0,
            "las_at_entry": 0.05,
            "kelly_fraction": 0.1,
            "weather_event_type": "rates",
            "location": "FED",
            "position_pct_of_bankroll": 0.4,
        }
    )
    await state.close_position(position_id, exit_price=0, pnl=-1_000)

    decision = await PreOrderRiskPolicy(
        RiskPolicyConfig(max_total_notional_pct=0.001)
    ).evaluate(state, _intent(quantity=100, limit_price=40))

    assert decision.allowed is False
    assert "MAX_DAILY_LOSS" in decision.reason_codes
    assert "MAX_TOTAL_NOTIONAL" in decision.reason_codes


@pytest.mark.asyncio
async def test_risk_policy_blocks_kill_switch(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))

    decision = await PreOrderRiskPolicy(RiskPolicyConfig(kill_switch=True)).evaluate(
        state,
        _intent(),
    )

    assert decision.allowed is False
    assert "KILL_SWITCH" in decision.reason_codes
