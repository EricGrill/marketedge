"""Durable market snapshot collection for local research workflows."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

from src.api.client import KalshiRestClient, WeatherMarketScanner
from src.market_adapters import normalize_market
from src.state import StateManager
from src.utils import utcnow


@dataclass(frozen=True)
class CollectionResult:
    """Summary of one bounded collection run."""

    attempted: int
    written: int
    errors: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempted": self.attempted,
            "written": self.written,
            "errors": self.errors,
        }


async def collect_market_snapshots(
    state: StateManager,
    client: KalshiRestClient,
    *,
    tickers: Iterable[str] | None = None,
    weather_scan: bool = False,
    scanner: WeatherMarketScanner | None = None,
    limit: int = 50,
    interval_seconds: float = 0.0,
    iterations: int = 1,
) -> CollectionResult:
    """Collect market snapshots from explicit tickers or a weather scan."""
    if iterations <= 0:
        raise ValueError("iterations must be positive")
    if interval_seconds < 0:
        raise ValueError("interval_seconds cannot be negative")

    attempted = 0
    written = 0
    errors: List[str] = []

    for iteration in range(iterations):
        markets = await _markets_for_iteration(
            client,
            tickers=list(tickers or []),
            weather_scan=weather_scan,
            scanner=scanner,
            limit=limit,
        )
        if not markets:
            errors.append("no markets returned")
        for market in markets:
            attempted += 1
            try:
                snapshot = await snapshot_from_market(client, market)
                await state.add_market_snapshot(snapshot)
                written += 1
            except Exception as exc:
                ticker = (
                    market.get("ticker") or market.get("market_ticker") or "unknown"
                )
                errors.append(f"{ticker}: {exc}")
        if iteration < iterations - 1:
            await asyncio.sleep(interval_seconds)

    return CollectionResult(attempted=attempted, written=written, errors=errors)


async def snapshot_from_market(
    client: KalshiRestClient, market: Dict[str, Any]
) -> Dict[str, Any]:
    """Build one StateManager market snapshot from raw market/orderbook payloads."""
    ticker = str(market.get("ticker") or market.get("market_ticker") or "")
    if not ticker:
        raise ValueError("ticker is required")

    orderbook = dict(market)
    if not _has_quotes(orderbook):
        response = await client.get_market_orderbook(ticker)
        orderbook = {
            **market,
            **_extract_orderbook(response),
        }
    normalized = normalize_market({**market, **orderbook})
    if not normalized:
        raise ValueError("unsupported market payload")

    yes_bid = _float(orderbook.get("yes_bid") or normalized.yes_bid)
    yes_ask = _float(orderbook.get("yes_ask") or normalized.yes_ask)
    if not yes_bid or not yes_ask:
        raise ValueError("missing YES bid/ask quotes")
    no_bid = _float(orderbook.get("no_bid") or normalized.no_bid)
    no_ask = _float(orderbook.get("no_ask") or normalized.no_ask)
    bid = _float(orderbook.get("bid") or yes_bid)
    ask = _float(orderbook.get("ask") or yes_ask)
    last_price = _float(orderbook.get("last_price") or orderbook.get("last"))

    return {
        "ticker": normalized.ticker,
        "title": normalized.title,
        "event_metadata": {
            "category": normalized.category,
            "event_type": normalized.event_type,
            "location": normalized.location,
            "region": normalized.region,
            "threshold": normalized.threshold,
            "relationship_group": normalized.relationship_group,
            "outcome_set": normalized.outcome_set,
            "metadata": normalized.metadata,
        },
        "source": normalized.source,
        "bid": bid,
        "ask": ask,
        "last_price": last_price,
        "volume_24h": _int(
            orderbook.get("volume") or orderbook.get("volume_24h") or normalized.volume
        ),
        "open_interest": _int(
            orderbook.get("open_interest") or normalized.open_interest
        ),
        "yes_ask": yes_ask,
        "yes_bid": yes_bid,
        "no_ask": no_ask,
        "no_bid": no_bid,
        "timestamp": utcnow(),
    }


async def fetch_market_quotes(client: KalshiRestClient, ticker: str) -> Dict[str, Any]:
    """Fetch one market and current orderbook for analyze/collection workflows."""
    market_response = await client.get_market(ticker)
    market = market_response.get("market", market_response)
    if market.get("error"):
        raise ValueError(f"market fetch failed: {market}")
    orderbook_response = await client.get_market_orderbook(ticker)
    orderbook = _extract_orderbook(orderbook_response)
    return {**market, **orderbook, "ticker": ticker}


async def _markets_for_iteration(
    client: KalshiRestClient,
    *,
    tickers: List[str],
    weather_scan: bool,
    scanner: WeatherMarketScanner | None,
    limit: int,
) -> List[Dict[str, Any]]:
    markets: List[Dict[str, Any]] = []
    if tickers:
        for ticker in tickers:
            response = await client.get_market(ticker)
            market = response.get("market", response)
            if not market.get("ticker"):
                market["ticker"] = ticker
            markets.append(market)
    if weather_scan:
        scanner = scanner or WeatherMarketScanner(client)
        markets.extend(await scanner.scan_weather_markets(limit=limit))
    return markets[:limit]


def _extract_orderbook(response: Dict[str, Any]) -> Dict[str, Any]:
    orderbook = response.get("orderbook", response)
    if not isinstance(orderbook, dict):
        return {}
    if _has_quotes(orderbook):
        return orderbook
    yes = orderbook.get("yes") or []
    no = orderbook.get("no") or []
    extracted: Dict[str, Any] = {}
    if yes:
        extracted["yes_bid"] = _level_price(yes, best_bid=True)
        extracted["yes_ask"] = _level_price(yes, best_bid=False)
    if no:
        extracted["no_bid"] = _level_price(no, best_bid=True)
        extracted["no_ask"] = _level_price(no, best_bid=False)
    return extracted


def _has_quotes(payload: Dict[str, Any]) -> bool:
    return bool(
        payload.get("yes_bid") is not None and payload.get("yes_ask") is not None
    )


def _level_price(levels: List[Any], *, best_bid: bool) -> float:
    prices = []
    for level in levels:
        if isinstance(level, dict):
            raw = level.get("price")
        elif isinstance(level, (list, tuple)) and level:
            raw = level[0]
        else:
            raw = None
        if raw is not None:
            prices.append(float(raw))
    if not prices:
        return 0.0
    return max(prices) if best_bid else min(prices)


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))
