import json

import pytest

from src.state import StateManager
from src.strategy_registry import StrategyConfigStore, StrategyManager, StrategyRegistry


@pytest.mark.asyncio
async def test_strategy_registry_lists_builtin_strategies():
    registry = StrategyRegistry()

    ids = [strategy.metadata.strategy_id for strategy in registry.list()]

    assert ids == [
        "calibration-ensemble",
        "catalyst-calendar",
        "liquidity-overlay",
        "relative-value",
        "weather",
    ]


def test_strategy_config_store_enables_and_disables(tmp_path):
    store = StrategyConfigStore(tmp_path / "config.json")

    store.set_enabled("weather", False)
    store.set_enabled("relative-value", True)

    payload = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert payload["weather"]["enabled"] is False
    assert (
        store.get_strategy_config("relative-value", {"enabled": False})["enabled"]
        is True
    )


@pytest.mark.asyncio
async def test_strategy_manager_persists_dry_run_record(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    await state.add_market_snapshot(
        {
            "ticker": "HIGHNY-TEST-B88.5",
            "title": "NYC Daily High above 88.5F",
            "bid": 39,
            "ask": 41,
            "last_price": 40,
            "volume_24h": 100,
            "open_interest": 100,
            "yes_bid": 39,
            "yes_ask": 41,
            "no_bid": 59,
            "no_ask": 61,
            "source": "fixture",
        }
    )

    result = await StrategyManager(
        state,
        config_store=StrategyConfigStore(tmp_path / "config.json"),
    ).run("weather")
    runs = await state.list_strategy_runs("weather")

    assert result["status"] == "completed"
    assert result["explanation"]["dry_run"] is True
    assert runs[0].strategy_id == "weather"
    assert runs[0].signal_count == 1


@pytest.mark.asyncio
async def test_strategy_manager_refuses_disabled_strategy(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    store = StrategyConfigStore(tmp_path / "config.json")
    store.set_enabled("weather", False)

    with pytest.raises(ValueError, match="strategy disabled"):
        await StrategyManager(state, config_store=store).run("weather")
