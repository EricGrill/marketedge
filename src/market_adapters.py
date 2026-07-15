"""Normalize raw exchange market payloads into category-neutral candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Protocol

from src.formulas import REGION_BY_CITY
from src.utils import parse_timestamp

CITY_ALIASES = {
    "new york": "NYC",
    "nyc": "NYC",
    "los angeles": "LA",
    "lax": "LA",
    "la": "LA",
    "chicago": "CHI",
    "houston": "HOU",
    "phoenix": "PHX",
    "philadelphia": "PHI",
    "miami": "MIA",
    "boston": "BOS",
    "seattle": "SEA",
    "denver": "DEN",
    "austin": "AUS",
}

CITY_COORDINATES = {
    "NYC": (40.7128, -74.0060),
    "LA": (34.0522, -118.2437),
    "CHI": (41.8781, -87.6298),
    "HOU": (29.7604, -95.3698),
    "PHX": (33.4484, -112.0740),
    "PHI": (39.9526, -75.1652),
    "MIA": (25.7617, -80.1918),
    "BOS": (42.3601, -71.0589),
    "SEA": (47.6062, -122.3321),
    "DEN": (39.7392, -104.9903),
    "AUS": (30.2672, -97.7431),
}

WEATHER_KEYWORDS = {
    "rain",
    "precipitation",
    "precip",
    "temp",
    "temperature",
    "high",
    "low",
    "degree",
    "snow",
    "blizzard",
    "wind",
    "hurricane",
    "tornado",
}


class MarketAdapter(Protocol):
    """Adapter contract for converting exchange payloads to normalized markets."""

    category: str

    def supports(self, payload: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def normalize(self, payload: Dict[str, Any]) -> "NormalizedMarket | None":
        raise NotImplementedError


@dataclass(frozen=True)
class NormalizedMarket:
    """Category-neutral market candidate shared by scanners and strategies."""

    ticker: str
    title: str
    category: str
    event_type: str
    yes_bid: float = 0.0
    yes_ask: float = 0.0
    no_bid: float = 0.0
    no_ask: float = 0.0
    last_price: float = 0.0
    volume: int = 0
    open_interest: int = 0
    location: str = ""
    region: str = "unknown"
    threshold: float = 0.0
    resolution_date: datetime | None = None
    relationship_group: str = ""
    date_bucket: str = ""
    outcome_set: str = ""
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def coordinates(self) -> tuple[float, float]:
        return CITY_COORDINATES.get(self.location, (40.0, -100.0))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "title": self.title,
            "category": self.category,
            "event_type": self.event_type,
            "yes_bid": self.yes_bid,
            "yes_ask": self.yes_ask,
            "no_bid": self.no_bid,
            "no_ask": self.no_ask,
            "last_price": self.last_price,
            "volume": self.volume,
            "open_interest": self.open_interest,
            "location": self.location,
            "region": self.region,
            "threshold": self.threshold,
            "resolution_date": (
                self.resolution_date.isoformat() if self.resolution_date else None
            ),
            "relationship_group": self.relationship_group,
            "date_bucket": self.date_bucket,
            "outcome_set": self.outcome_set,
            "source": self.source,
            "metadata": self.metadata,
        }


class WeatherMarketAdapter:
    """Normalize Kalshi weather markets and isolate weather title parsing."""

    category = "weather"

    def supports(self, payload: Dict[str, Any]) -> bool:
        haystack = " ".join(
            str(payload.get(key) or "")
            for key in ("title", "event_title", "category", "event_category")
        ).lower()
        return any(keyword in haystack for keyword in WEATHER_KEYWORDS)

    def normalize(self, payload: Dict[str, Any]) -> NormalizedMarket | None:
        title = str(payload.get("title") or payload.get("event_title") or "")
        location, event_type, threshold = parse_weather_market_title(title)
        if not location or not event_type:
            return None

        ticker = str(payload.get("ticker") or payload.get("market_ticker") or "")
        resolution_date = parse_market_resolution_date(payload)
        date_bucket = (
            resolution_date.date().isoformat() if resolution_date else "unknown-date"
        )
        relationship_group = (
            str(payload.get("event_ticker") or payload.get("series_ticker") or "")
            or f"{location.lower()}-{event_type}-{date_bucket}"
        )

        return NormalizedMarket(
            ticker=ticker,
            title=title,
            category=self.category,
            event_type=event_type,
            yes_bid=_float(payload.get("yes_bid") or payload.get("bid")),
            yes_ask=_float(payload.get("yes_ask") or payload.get("ask")),
            no_bid=_float(payload.get("no_bid")),
            no_ask=_float(payload.get("no_ask")),
            last_price=_float(payload.get("last_price") or payload.get("last")),
            volume=_int(payload.get("volume") or payload.get("volume_24h")),
            open_interest=_int(payload.get("open_interest")),
            location=location,
            region=REGION_BY_CITY.get(location, "unknown"),
            threshold=threshold,
            resolution_date=resolution_date,
            relationship_group=relationship_group,
            date_bucket=date_bucket,
            outcome_set=str(payload.get("event_ticker") or relationship_group),
            source=str(payload.get("source") or "kalshi"),
            metadata={
                "raw_category": payload.get("category")
                or payload.get("event_category"),
                "series_ticker": payload.get("series_ticker"),
                "event_ticker": payload.get("event_ticker"),
            },
        )


class GenericMarketAdapter:
    """Fallback adapter for non-weather prediction-market payloads."""

    category = "generic"

    def supports(self, payload: Dict[str, Any]) -> bool:
        return bool(payload.get("ticker") or payload.get("market_ticker"))

    def normalize(self, payload: Dict[str, Any]) -> NormalizedMarket | None:
        ticker = str(payload.get("ticker") or payload.get("market_ticker") or "")
        if not ticker:
            return None
        title = str(payload.get("title") or payload.get("event_title") or ticker)
        category = str(
            payload.get("market_category")
            or payload.get("category")
            or payload.get("event_category")
            or self.category
        ).lower()
        event_type = str(payload.get("event_type") or category or "generic").lower()
        resolution_date = parse_market_resolution_date(payload)
        date_bucket = (
            resolution_date.date().isoformat() if resolution_date else "unknown-date"
        )
        group = str(
            payload.get("relationship_group")
            or payload.get("event_ticker")
            or payload.get("series_ticker")
            or f"{category}-{date_bucket}"
        )
        return NormalizedMarket(
            ticker=ticker,
            title=title,
            category=category,
            event_type=event_type,
            yes_bid=_float(payload.get("yes_bid") or payload.get("bid")),
            yes_ask=_float(payload.get("yes_ask") or payload.get("ask")),
            no_bid=_float(payload.get("no_bid")),
            no_ask=_float(payload.get("no_ask")),
            last_price=_float(payload.get("last_price") or payload.get("last")),
            volume=_int(payload.get("volume") or payload.get("volume_24h")),
            open_interest=_int(payload.get("open_interest")),
            location=str(payload.get("location") or ""),
            region=str(payload.get("region") or "unknown"),
            threshold=_float(payload.get("threshold")),
            resolution_date=resolution_date,
            relationship_group=group,
            date_bucket=date_bucket,
            outcome_set=str(payload.get("outcome_set") or group),
            source=str(payload.get("source") or "local"),
            metadata={key: value for key, value in payload.items() if key},
        )


def normalize_market(
    payload: Dict[str, Any],
    adapters: Iterable[MarketAdapter] | None = None,
) -> NormalizedMarket | None:
    """Normalize one raw market with the first supporting adapter."""
    for adapter in adapters or (WeatherMarketAdapter(), GenericMarketAdapter()):
        if adapter.supports(payload):
            normalized = adapter.normalize(payload)
            if normalized:
                return normalized
    return None


def parse_weather_market_title(title: str) -> tuple[str | None, str | None, float]:
    """Return location, event type, and threshold parsed from a weather title."""
    title_lower = title.lower()
    event_type = None
    if any(kw in title_lower for kw in ("rain", "precipitation", "precip")):
        event_type = "rain"
    elif any(kw in title_lower for kw in ("temp", "temperature", "high", "low")):
        event_type = "temp"
    elif any(kw in title_lower for kw in ("snow", "blizzard")):
        event_type = "snow"
    elif any(kw in title_lower for kw in ("wind", "hurricane", "tornado")):
        event_type = "wind"

    location = None
    for city_key, city_code in CITY_ALIASES.items():
        if city_key in title_lower:
            location = city_code
            break

    numbers = re.findall(r"\d+\.?\d*", title)
    threshold = float(numbers[0]) if numbers else 0.0
    return location, event_type, threshold


def parse_market_resolution_date(payload: Dict[str, Any]) -> datetime | None:
    for key in ("resolution_date", "close_date", "expiration_date", "settle_time"):
        value = payload.get(key)
        if value:
            try:
                parsed = parse_timestamp(str(value))
            except ValueError:
                continue
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc)
            return parsed.replace(tzinfo=timezone.utc)
    return None


def _float(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    return float(value)


def _int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(float(value))
