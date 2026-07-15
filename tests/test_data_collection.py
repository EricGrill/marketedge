import pytest

from src.data_collection import collect_market_snapshots, snapshot_from_market
from src.state import StateManager


class FakeClient:
    def __init__(self, market=None, orderbook=None):
        self.market = market or {}
        self.orderbook = orderbook or {}

    async def get_market(self, ticker):
        return {"market": {**self.market, "ticker": ticker}}

    async def get_market_orderbook(self, ticker, depth=10):
        return {"orderbook": self.orderbook}


class EmptyScanner:
    async def scan_weather_markets(self, limit=100):
        return []


@pytest.mark.asyncio
async def test_collect_market_snapshots_writes_explicit_ticker(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))
    client = FakeClient(
        market={
            "title": "NYC Daily High above 88.5F",
            "volume": 1200,
            "open_interest": 400,
        },
        orderbook={"yes_bid": 39, "yes_ask": 41, "no_bid": 59, "no_ask": 61},
    )

    result = await collect_market_snapshots(
        state,
        client,
        tickers=["HIGHNY-TEST-B88.5"],
    )
    snapshots = await state.get_latest_market_snapshots()

    assert result.written == 1
    assert snapshots[0].ticker == "HIGHNY-TEST-B88.5"
    assert snapshots[0].title == "NYC Daily High above 88.5F"
    assert snapshots[0].source == "kalshi"


@pytest.mark.asyncio
async def test_collect_market_snapshots_reports_empty_scanner(tmp_path):
    state = StateManager(str(tmp_path / "state.db"))

    result = await collect_market_snapshots(
        state,
        FakeClient(),
        weather_scan=True,
        scanner=EmptyScanner(),
    )

    assert result.attempted == 0
    assert result.written == 0
    assert result.errors == ["no markets returned"]


@pytest.mark.asyncio
async def test_snapshot_from_market_rejects_malformed_payload():
    with pytest.raises(ValueError, match="missing YES bid/ask quotes"):
        await snapshot_from_market(
            FakeClient(orderbook={}),
            {"ticker": "BAD", "title": "Generic event"},
        )
