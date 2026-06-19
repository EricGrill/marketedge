import json

import pytest

from src.dashboard import build_dashboard_payload, write_dashboard_payload
from src.paper import PaperTradingLedger
from src.state import StateManager


@pytest.mark.asyncio
async def test_dashboard_payload_exports_state_and_paper_summary(tmp_path):
    state = StateManager(str(tmp_path / "marketedge.db"))
    await state.add_market_snapshot(
        {
            "ticker": "HIGHNY-TEST-B88.5",
            "bid": 39,
            "ask": 41,
            "last_price": 40,
            "volume_24h": 1200,
            "open_interest": 400,
            "yes_ask": 41,
            "yes_bid": 39,
            "no_ask": 61,
            "no_bid": 59,
        }
    )
    await state.add_position(
        {
            "ticker": "HIGHNY-TEST-B88.5",
            "event_title": "NYC high test",
            "side": "yes",
            "entry_price": 40.0,
            "quantity": 10,
            "status": "open",
            "model_probability": 0.75,
            "market_probability": 0.40,
            "edge_at_entry": 0.35,
            "iy_annualized": 1.1,
            "las_at_entry": 0.05,
            "kelly_fraction": 0.1,
            "position_pct_of_bankroll": 0.04,
        }
    )
    ledger = PaperTradingLedger(tmp_path / "paper.jsonl")
    ledger.record_order("RAIN-NYC-TEST", "yes", "buy", 5, 30)

    payload = await build_dashboard_payload(
        state,
        paper_ledger_path=tmp_path / "paper.jsonl",
    )
    output_path = write_dashboard_payload(payload, tmp_path / "dashboard.json")
    saved = json.loads(output_path.read_text(encoding="utf-8"))

    assert saved["markets"][0]["ticker"] == "HIGHNY-TEST-B88.5"
    assert saved["positions"][0]["ticker"] == "HIGHNY-TEST-B88.5"
    assert saved["paper"]["event_count"] == 1
    assert saved["account"]["bankroll"] == 10_000
