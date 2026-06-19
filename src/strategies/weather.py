# marketedge/src/strategies/weather.py
"""Weather trading strategy for Kalshi prediction markets."""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from src.config import trading_config
from src.formulas import QuantEngine
from src.state import StateManager
from src.api.client import KalshiRestClient, WeatherMarketScanner
from src.weather.data import WeatherModelEngine


@dataclass
class TradeSignal:
    """Generated trade signal."""

    ticker: str
    side: str  # yes or no
    action: str  # buy or sell
    entry_price: float
    quantity: int
    model_probability: float
    market_probability: float
    edge: float
    iy_annualized: float
    kelly_fraction: float
    confidence: float
    reason: str
    passes_screen: bool


class WeatherTradingStrategy:
    """Main weather trading strategy engine."""

    def __init__(
        self,
        state_manager: StateManager,
        kalshi_client: KalshiRestClient,
        quant_engine: QuantEngine = None,
    ):
        self.state = state_manager
        self.kalshi = kalshi_client
        self.quant = quant_engine or QuantEngine()
        self.scanner = WeatherMarketScanner(kalshi_client)
        self.weather = WeatherModelEngine()
        self.running = False

    async def scan_and_evaluate(self) -> List[TradeSignal]:
        """Scan weather markets and evaluate opportunities."""
        signals = []

        # 1. Get portfolio state
        portfolio = await self.state.get_portfolio_state()
        bankroll = portfolio.bankroll if portfolio else trading_config.initial_bankroll

        # 2. Scan for weather markets
        print("[Strategy] Scanning weather markets...")
        weather_markets = await self.scanner.scan_weather_markets(limit=50)
        print(f"[Strategy] Found {len(weather_markets)} weather markets")

        for market in weather_markets:
            try:
                signal = await self._evaluate_market(market, bankroll)
                if signal:
                    signals.append(signal)
            except Exception as e:
                print(f"[Strategy] Error evaluating {market.get('ticker')}: {e}")
                continue

        return signals

    async def _evaluate_market(
        self, market: Dict, bankroll: float
    ) -> Optional[TradeSignal]:
        """Evaluate a single market for trading opportunity."""
        ticker = market.get("ticker")
        title = market.get("title", "")

        # Get orderbook
        orderbook_data = await self.kalshi.get_market_orderbook(ticker)
        orderbook = orderbook_data.get("orderbook", {})

        yes_bid = orderbook.get("yes_bid", 0)
        yes_ask = orderbook.get("yes_ask", 0)
        no_bid = orderbook.get("no_bid", 0)
        no_ask = orderbook.get("no_ask", 0)

        if not yes_ask or not yes_bid:
            return None

        # Parse location and event type from title
        location, event_type, threshold = self._parse_market_title(title)

        if not location or not event_type:
            return None

        # Get coordinates (simplified - would use geocoding API)
        lat, lon = self._get_coordinates(location)

        # Fetch weather forecast
        forecast = await self.weather.fetch_all_sources(
            location=location,
            lat=lat,
            lon=lon,
            event_type=event_type,
            threshold=threshold,
        )

        # Blend probabilities
        blended_prob, confidence = self.quant.blend_weather_probabilities(
            ecmwf=forecast.ecmwf_prob,
            gefs=forecast.gefs_prob,
            analog=forecast.analog_prob,
            microclimate=forecast.microclimate_prob,
            nws_delta=forecast.nws_delta,
            ensemble_spread=forecast.ensemble_spread,
        )

        # Get resolution date
        resolution_date = self._parse_resolution_date(market)

        # Screen opportunity
        screen = self.quant.screen_opportunity(
            model_prob=blended_prob,
            market_bid=yes_bid,
            market_ask=yes_ask,
            resolution_date=resolution_date,
            bankroll=bankroll,
            ensemble_spread=forecast.ensemble_spread,
            side="yes",
        )

        if not screen["passes_screen"]:
            # Try NO side
            no_screen = self.quant.screen_opportunity(
                model_prob=1 - blended_prob,
                market_bid=no_bid,
                market_ask=no_ask,
                resolution_date=resolution_date,
                bankroll=bankroll,
                ensemble_spread=forecast.ensemble_spread,
                side="no",
            )
            if no_screen["passes_screen"]:
                screen = no_screen
                side = "no"
                entry_price = no_ask
            else:
                return None
        else:
            side = "yes"
            entry_price = yes_ask

        # Calculate quantity
        kelly = screen["kelly"]
        quantity = int(kelly.recommended_bet_dollars / (entry_price / 100))
        quantity = max(1, quantity)

        # Check correlation limits
        correlated_exposure = await self._check_correlation_exposure(
            location, event_type, kelly.recommended_bet_dollars
        )

        if correlated_exposure > trading_config.max_correlated_pct:
            return None

        return TradeSignal(
            ticker=ticker,
            side=side,
            action="buy",
            entry_price=entry_price,
            quantity=quantity,
            model_probability=blended_prob,
            market_probability=screen["edge"].market_probability,
            edge=screen["edge"].fee_adjusted_edge,
            iy_annualized=screen["iy"].annualized_yield,
            kelly_fraction=kelly.recommended_fraction,
            confidence=confidence,
            reason=f"{event_type} @ {location}: model={blended_prob:.2%}, market={screen['edge'].market_probability:.2%}",
            passes_screen=True,
        )

    def _parse_market_title(self, title: str) -> tuple:
        """Parse location, event type, and threshold from market title."""
        title_lower = title.lower()

        # Event type detection
        event_type = None
        if any(kw in title_lower for kw in ["rain", "precipitation", "precip"]):
            event_type = "rain"
        elif any(
            kw in title_lower for kw in ["temp", "temperature", "high", "low", "degree"]
        ):
            event_type = "temp"
        elif any(kw in title_lower for kw in ["snow", "blizzard"]):
            event_type = "snow"
        elif any(kw in title_lower for kw in ["wind", "hurricane", "tornado"]):
            event_type = "wind"

        # Location detection (simplified)
        location = None
        cities = {
            "new york": "NYC",
            "nyc": "NYC",
            "los angeles": "LA",
            "la": "LA",
            "chicago": "CHI",
            "houston": "HOU",
            "phoenix": "PHX",
            "philadelphia": "PHI",
            "miami": "MIA",
            "boston": "BOS",
            "seattle": "SEA",
            "denver": "DEN",
        }

        for city_key, city_code in cities.items():
            if city_key in title_lower:
                location = city_code
                break

        # Threshold extraction (simplified)
        threshold = 0.0
        import re

        numbers = re.findall(r"\d+\.?\d*", title)
        if numbers:
            threshold = float(numbers[0])

        return location, event_type, threshold

    def _get_coordinates(self, location: str) -> tuple:
        """Get lat/lon for location code."""
        coords = {
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
        }
        return coords.get(location, (40.0, -100.0))

    def _parse_resolution_date(self, market: Dict) -> datetime:
        """Parse resolution date from market data."""
        close_date = market.get("close_date") or market.get("expiration_date")
        if close_date:
            try:
                return datetime.fromisoformat(close_date.replace("Z", "+00:00"))
            except ValueError:
                pass
        return datetime.utcnow() + timedelta(days=7)

    async def _check_correlation_exposure(
        self, location: str, event_type: str, new_size: float
    ) -> float:
        """Check correlation-weighted exposure."""
        open_positions = await self.state.get_open_positions()

        positions_data = []
        for pos in open_positions:
            positions_data.append(
                {
                    "ticker": pos.ticker,
                    "size": pos.entry_price * pos.quantity,
                    "region": pos.location,
                    "event_type": pos.weather_event_type,
                }
            )

        new_position = {
            "ticker": "NEW",
            "size": new_size,
            "region": location,
            "event_type": event_type,
        }

        return self.quant.correlation_exposure(positions_data, new_position)

    async def execute_signal(self, signal: TradeSignal) -> Dict[str, Any]:
        """Execute a trade signal."""
        print(
            f"[Strategy] EXECUTING: {signal.ticker} {signal.side} @ {signal.entry_price}¢ x{signal.quantity}"
        )

        # Place order
        order = await self.kalshi.place_order(
            ticker=signal.ticker,
            side=signal.side,
            action=signal.action,
            type="limit",
            count=signal.quantity,
            price=int(signal.entry_price),
            client_order_id=f"weather_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        )

        if order.get("error"):
            print(f"[Strategy] Order failed: {order}")
            return {"success": False, "error": order}

        # Record position in state
        position_data = {
            "ticker": signal.ticker,
            "event_title": signal.reason,
            "side": signal.side,
            "entry_price": signal.entry_price / 100,
            "quantity": signal.quantity,
            "status": "open",
            "model_probability": signal.model_probability,
            "market_probability": signal.market_probability,
            "edge_at_entry": signal.edge,
            "iy_annualized": signal.iy_annualized,
            "las_at_entry": 0.0,
            "kelly_fraction": signal.kelly_fraction,
            "weather_event_type": signal.reason.split(":")[0].split("@")[0].strip(),
            "location": (
                signal.reason.split("@")[1].split(":")[0].strip()
                if "@" in signal.reason
                else ""
            ),
            "forecast_cycle": datetime.utcnow(),
            "resolution_date": datetime.utcnow() + timedelta(days=7),
            "position_pct_of_bankroll": (signal.entry_price / 100 * signal.quantity)
            / trading_config.initial_bankroll,
        }

        position_id = await self.state.add_position(position_data)

        return {
            "success": True,
            "position_id": position_id,
            "order": order,
            "signal": signal,
        }

    async def run_continuous(self, interval_seconds: int = 300):
        """Run continuous scanning and trading loop."""
        self.running = True
        print(f"[Strategy] Starting continuous loop (interval: {interval_seconds}s)")

        while self.running:
            try:
                signals = await self.scan_and_evaluate()

                for signal in signals:
                    if signal.passes_screen:
                        await self.execute_signal(signal)

                # Check existing positions for exit signals
                await self._check_exits()

            except Exception as e:
                print(f"[Strategy] Loop error: {e}")

            await asyncio.sleep(interval_seconds)

    async def _check_exits(self):
        """Check open positions for exit conditions."""
        open_positions = await self.state.get_open_positions()

        for pos in open_positions:
            days_to_exp = (
                (pos.resolution_date - datetime.utcnow()).days
                if pos.resolution_date
                else 1
            )

            if days_to_exp <= 1:
                print(f"[Strategy] Closing {pos.ticker} before expiration")

    async def stop(self):
        """Stop the strategy."""
        self.running = False
        await self.weather.close()
