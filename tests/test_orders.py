from datetime import timedelta

import pytest

from src.orders import OrderLedger, OrderLedgerError, OrderState
from src.utils import utcnow


def test_order_ledger_tracks_full_and_partial_fills(tmp_path):
    ledger = OrderLedger(tmp_path / "orders.jsonl")

    partial = ledger.submit(
        "ord-1",
        ticker="RAIN-NYC-TEST",
        side="yes",
        action="buy",
        order_type="limit",
        requested_quantity=5,
        limit_price=40,
    )
    assert partial.state == OrderState.PENDING

    partial = ledger.record_fill("ord-1", quantity=2, price=40)
    assert partial.state == OrderState.PARTIALLY_FILLED
    assert partial.filled_quantity == 2
    assert partial.average_fill_price == 40

    filled = ledger.record_fill("ord-1", quantity=3, price=43)
    assert filled.state == OrderState.FILLED
    assert filled.filled_quantity == 5
    assert filled.average_fill_price == pytest.approx((2 * 40 + 3 * 43) / 5)


def test_order_ledger_rejects_invalid_transitions_and_overfills(tmp_path):
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    ledger.submit(
        "ord-1",
        ticker="RAIN-NYC-TEST",
        side="yes",
        action="buy",
        order_type="limit",
        requested_quantity=2,
        limit_price=40,
    )

    with pytest.raises(OrderLedgerError, match="exceeds requested"):
        ledger.record_fill("ord-1", quantity=3, price=40)

    record = ledger.reject("ord-1", "venue risk limit")
    assert record.state == OrderState.REJECTED

    with pytest.raises(OrderLedgerError, match="after rejected"):
        ledger.record_fill("ord-1", quantity=1, price=40)


def test_order_ledger_reconstructs_state_from_persistence(tmp_path):
    path = tmp_path / "orders.jsonl"
    ledger = OrderLedger(path)
    ledger.submit(
        "ord-1",
        ticker="RAIN-NYC-TEST",
        side="yes",
        action="buy",
        order_type="limit",
        requested_quantity=4,
        limit_price=40,
    )
    ledger.record_fill("ord-1", quantity=1, price=39)

    reopened = OrderLedger(path)
    record = reopened.get("ord-1")

    assert record.state == OrderState.PARTIALLY_FILLED
    assert record.filled_quantity == 1
    assert record.average_fill_price == 39


def test_order_ledger_reconciles_stale_open_orders(tmp_path):
    now = utcnow()
    ledger = OrderLedger(tmp_path / "orders.jsonl")
    ledger.submit(
        "stale",
        ticker="RAIN-NYC-TEST",
        side="yes",
        action="buy",
        order_type="limit",
        requested_quantity=4,
        limit_price=40,
        at=now - timedelta(seconds=10),
    )
    ledger.submit(
        "fresh",
        ticker="SNOW-BOS-TEST",
        side="no",
        action="buy",
        order_type="limit",
        requested_quantity=2,
        limit_price=25,
        at=now - timedelta(seconds=2),
    )

    expired = ledger.reconcile_timeouts(5, now=now)

    assert [record.order_id for record in expired] == ["stale"]
    assert ledger.get("stale").state == OrderState.EXPIRED
    assert ledger.get("fresh").state == OrderState.PENDING
