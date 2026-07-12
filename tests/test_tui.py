import pytest

from src.state import StateManager
from src.tui.app import KalshiQuantApp


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
