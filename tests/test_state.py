import pytest

from src.state import StateManager


@pytest.mark.asyncio
async def test_state_manager_initializes_and_tracks_position_exposure(tmp_path):
    state = StateManager(str(tmp_path / "kalshi_quant.db"))

    initial = await state.get_portfolio_state()
    assert initial.bankroll == 10_000
    assert initial.open_positions_count == 0

    position_id = await state.add_position(
        {
            "ticker": "RAIN-NYC-TEST",
            "event_title": "NYC rain test",
            "side": "yes",
            "entry_price": 25.0,
            "quantity": 10,
            "status": "open",
            "model_probability": 0.65,
            "market_probability": 0.25,
            "edge_at_entry": 0.40,
            "iy_annualized": 1.2,
            "las_at_entry": 0.08,
            "kelly_fraction": 0.10,
            "weather_event_type": "rain",
            "location": "NYC",
            "position_pct_of_bankroll": 0.025,
        }
    )

    open_positions = await state.get_open_positions()
    assert [pos.id for pos in open_positions] == [position_id]

    after_entry = await state.get_portfolio_state()
    assert after_entry.open_positions_count == 1
    assert after_entry.total_exposure == 250
    assert after_entry.available_cash == 9_750

    await state.close_position(position_id, exit_price=40.0, pnl=150.0, fee=4.5)

    after_close = await state.get_portfolio_state()
    assert after_close.open_positions_count == 0
    assert after_close.total_exposure == 0
    assert after_close.mtd_pnl == 150
