import pytest

from src.state import StateManager
from src.tui.app import KalshiQuantApp, MarketScannerWidget


@pytest.mark.asyncio
async def test_tui_launches_and_runs_refresh_without_crashing(tmp_path):
    # Regression for the "TUI crashes on launch" report, which had two causes:
    #   1. reactive watchers firing during compose before their child Labels
    #      existed (NoMatches), and
    #   2. a `_auto_refresh` method shadowed by Textual's reserved instance
    #      attribute of the same name (calling None).
    # run_test() re-raises any exception from compose/on_mount on exit, so
    # completing the block is the assertion that neither regression is present.
    state = StateManager(str(tmp_path / "state.db"))
    await state.list_schema_migrations()

    app = KalshiQuantApp(state_manager=state)
    async with app.run_test() as pilot:
        await pilot.pause()
        # Drive an explicit refresh to exercise the widget-update path too.
        await app._refresh_dashboard()


@pytest.mark.asyncio
async def test_tui_scanner_runs_local_snapshot_scan_and_updates_signals(tmp_path):
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
        }
    )

    app = KalshiQuantApp(state_manager=state)
    async with app.run_test() as pilot:
        app.query_one("#min-edge").value = "0"
        app.query_one("#min-iy").value = "0"
        app.start_scanner()
        await pilot.pause()

        scanner = app.query_one("#scanner", MarketScannerWidget)
        assert scanner.scanning is False
        assert app._signals_history
        assert app._signals_history[0]["ticker"] == "HIGHNY-TEST-B88.5"


@pytest.mark.asyncio
async def test_tui_settings_validation_stages_runtime_values(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    app = KalshiQuantApp(state_manager=state)
    async with app.run_test():
        app.query_one("#min-edge-input").value = "4"
        app.query_one("#min-iy-input").value = "25"

        app.save_settings()

        assert app._scanner_settings["min_edge"] == 0.04
        assert app._scanner_settings["min_iy"] == 0.25


@pytest.mark.asyncio
async def test_tui_stop_cancels_active_scan(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    app = KalshiQuantApp(state_manager=state)
    async with app.run_test():
        app.query_one("#min-edge").value = "0"
        app.query_one("#min-iy").value = "0"
        app.start_scanner()
        app.stop_scanner()

        assert app.query_one("#scanner", MarketScannerWidget).scanning is False
