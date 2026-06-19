import pytest

from src.paper import PaperLedgerError, PaperTradingLedger


def test_paper_ledger_tracks_buy_sell_and_settlement(tmp_path):
    ledger = PaperTradingLedger(tmp_path / "paper.jsonl")

    ledger.record_order("RAIN-NYC-TEST", "yes", "buy", quantity=10, price=40, fee=0.10)
    position = ledger.positions()[("RAIN-NYC-TEST", "yes")]
    assert position.quantity == 10
    assert position.average_price == 40
    assert position.cost_basis == 4

    ledger.record_order("RAIN-NYC-TEST", "yes", "sell", quantity=4, price=55, fee=0.05)
    position = ledger.positions()[("RAIN-NYC-TEST", "yes")]
    assert position.quantity == 6
    assert position.realized_pnl == pytest.approx(0.45)

    ledger.settle("RAIN-NYC-TEST", "yes")
    summary = ledger.summary()

    assert summary["open_positions"] == []
    assert summary["event_count"] == 3
    assert summary["fees"] == pytest.approx(0.15)
    assert summary["realized_pnl"] == pytest.approx(4.05)


def test_paper_ledger_rejects_selling_more_than_open(tmp_path):
    ledger = PaperTradingLedger(tmp_path / "paper.jsonl")
    ledger.record_order("RAIN-NYC-TEST", "yes", "buy", quantity=2, price=40)

    with pytest.raises(PaperLedgerError, match="cannot sell more"):
        ledger.record_order("RAIN-NYC-TEST", "yes", "sell", quantity=3, price=45)
