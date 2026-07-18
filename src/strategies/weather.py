# marketedge/src/strategies/weather.py
"""Weather trading strategy for Kalshi prediction markets."""

import asyncio
import copy
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, cast
from dataclasses import dataclass

from src.config import trading_config
from src.formulas import QuantEngine
from src.market_adapters import (
    CITY_COORDINATES,
    WeatherMarketAdapter,
    parse_weather_market_title,
)
from src.orders import OrderLedger
from src.risk_policy import OrderIntent, PreOrderRiskPolicy, RiskDecision
from src.state import StateManager
from src.api.client import KalshiRestClient, WeatherMarketScanner
from src.weather.data import WeatherModelEngine
from src.utils import parse_timestamp, utcnow

logger = logging.getLogger(__name__)


SAMPLE_DASHBOARD_WEATHER_MARKETS: List[Dict[str, Any]] = [
    {
        "ticker": "HIGHNY-26JUN18-B88.5",
        "title": "NYC Daily High above 88.5F",
        "yes_bid": 23,
        "yes_ask": 25,
        "no_bid": 75,
        "no_ask": 77,
        "volume": 142000,
        "open_interest": 142000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHNY-26JUN18-B90.5",
        "title": "NYC Daily High above 90.5F",
        "yes_bid": 30,
        "yes_ask": 32,
        "no_bid": 68,
        "no_ask": 70,
        "volume": 118000,
        "open_interest": 118000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHNY-26JUN18-B86.5",
        "title": "NYC Daily High above 86.5F",
        "yes_bid": 15,
        "yes_ask": 17,
        "no_bid": 83,
        "no_ask": 85,
        "volume": 74000,
        "open_interest": 74000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHCHI-26JUN18-B84.5",
        "title": "Chicago Daily High above 84.5F",
        "yes_bid": 37,
        "yes_ask": 39,
        "no_bid": 61,
        "no_ask": 63,
        "volume": 96000,
        "open_interest": 96000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "RAINMIA-26JUN18-YES",
        "title": "Miami Rain Today",
        "yes_bid": 70,
        "yes_ask": 72,
        "no_bid": 28,
        "no_ask": 30,
        "volume": 63000,
        "open_interest": 63000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHLA-26JUN18-B75.5",
        "title": "Los Angeles Daily High above 75.5F",
        "yes_bid": 51,
        "yes_ask": 53,
        "no_bid": 47,
        "no_ask": 49,
        "volume": 58000,
        "open_interest": 58000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHDEN-26JUN18-B71.5",
        "title": "Denver Daily High above 71.5F",
        "yes_bid": 28,
        "yes_ask": 30,
        "no_bid": 70,
        "no_ask": 72,
        "volume": 47000,
        "open_interest": 47000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HEATAUS-26JUN18-YES",
        "title": "Austin High at least 100F",
        "yes_bid": 63,
        "yes_ask": 65,
        "no_bid": 35,
        "no_ask": 37,
        "volume": 81000,
        "open_interest": 81000,
        "source": "dashboard-sample",
    },
    {
        "ticker": "HIGHBOS-26JUN18-B79.5",
        "title": "Boston Daily High above 79.5F",
        "yes_bid": 43,
        "yes_ask": 45,
        "no_bid": 55,
        "no_ask": 57,
        "volume": 39000,
        "open_interest": 39000,
        "source": "dashboard-sample",
    },
]


def dashboard_sample_weather_markets() -> List[Dict[str, Any]]:
    """Return dashboard sample markets in Kalshi-like scanner shape."""
    return copy.deepcopy(SAMPLE_DASHBOARD_WEATHER_MARKETS)


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
    event_type: str = ""
    location: str = ""
    region: str = ""
    correlation_group: str = ""
    resolution_date: datetime | None = None
    source_metadata: Optional[Dict[str, Any]] = None


class WeatherTradingStrategy:
    """Main weather trading strategy engine."""

    def __init__(
        self,
        state_manager: StateManager,
        kalshi_client: KalshiRestClient,
        quant_engine: Optional[QuantEngine] = None,
        order_ledger: OrderLedger | None = None,
        use_sample_markets_if_empty: bool = False,
        execute_orders: bool = True,
        risk_policy: PreOrderRiskPolicy | None = None,
        strategy_id: str = "weather",
    ):
        self.state = state_manager
        self.kalshi = kalshi_client
        self.quant = quant_engine or QuantEngine()
        self.order_ledger = order_ledger or OrderLedger()
        self.risk_policy = risk_policy or PreOrderRiskPolicy(quant_engine=self.quant)
        self.strategy_id = strategy_id
        self.scanner = WeatherMarketScanner(kalshi_client)
        self.weather = WeatherModelEngine()
        self.market_adapter = WeatherMarketAdapter()
        self.use_sample_markets_if_empty = use_sample_markets_if_empty
        self.execute_orders = execute_orders
        self.running = False

    async def scan_and_evaluate(self) -> List[TradeSignal]:
        """Scan weather markets and evaluate opportunities."""
        signals = []

        # 1. Get portfolio state
        portfolio = await self.state.get_portfolio_state()
        # PortfolioState is a SQLAlchemy model; bankroll reads as Column[Any].
        bankroll = (
            cast(float, portfolio.bankroll)
            if portfolio
            else trading_config.initial_bankroll
        )

        # 2. Scan for weather markets
        logger.info("Scanning weather markets...")
        weather_markets = await self.scanner.scan_weather_markets(limit=50)
        if not weather_markets and self.use_sample_markets_if_empty:
            weather_markets = dashboard_sample_weather_markets()
            logger.info(
                "Using dashboard sample markets for dry-run evaluation because live scan returned none"
            )
        logger.info("Found %d weather markets", len(weather_markets))

        for market in weather_markets:
            try:
                signal = await self._evaluate_market(market, bankroll)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.warning("Error evaluating %s: %s", market.get("ticker"), e)
                continue

        return signals

    async def _evaluate_market(
        self, market: Dict, bankroll: float
    ) -> Optional[TradeSignal]:
        """Evaluate a single market for trading opportunity."""
        ticker = str(market.get("ticker") or "")
        title = market.get("title", "")

        # Sample dry-run markets carry top-level quotes so they do not need a
        # live orderbook request. Live/scanned markets still use Kalshi data.
        if all(key in market for key in ("yes_bid", "yes_ask", "no_bid", "no_ask")):
            orderbook = market
        else:
            orderbook_data = await self.kalshi.get_market_orderbook(ticker)
            orderbook = orderbook_data.get("orderbook", {})

        yes_bid = orderbook.get("yes_bid", 0)
        yes_ask = orderbook.get("yes_ask", 0)
        no_bid = orderbook.get("no_bid", 0)
        no_ask = orderbook.get("no_ask", 0)

        if not yes_ask or not yes_bid:
            await self._record_signal_audit(
                "signal_refused",
                ticker,
                {"reason_codes": ["MISSING_QUOTES"], "market": market},
            )
            return None

        normalized = self.market_adapter.normalize({**market, **orderbook})
        if not normalized:
            await self._record_signal_audit(
                "signal_refused",
                ticker,
                {"reason_codes": ["UNSUPPORTED_WEATHER_MARKET"], "title": title},
            )
            return None
        location = normalized.location
        event_type = normalized.event_type
        threshold = normalized.threshold

        lat, lon = normalized.coordinates

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
        await self.state.add_weather_forecast(
            {
                "location": location,
                "event_type": event_type,
                "forecast_cycle": forecast.forecast_cycle,
                "ecmwf_prob": forecast.ecmwf_prob,
                "gefs_prob": forecast.gefs_prob,
                "analog_prob": forecast.analog_prob,
                "microclimate_prob": forecast.microclimate_prob,
                "nws_delta": forecast.nws_delta,
                "blended_probability": blended_prob,
                "confidence": confidence,
                "market_ticker": ticker,
                "market_price": yes_ask,
                "market_timestamp": utcnow(),
                "strategy": self.strategy_id,
                "model_version": "weather-heuristic-v1",
                "market_category": normalized.category,
                "source_metadata": {
                    "sources": forecast.sources,
                    "source": normalized.source,
                },
                "feature_metadata": {
                    "threshold": threshold,
                    "ensemble_spread": forecast.ensemble_spread,
                    "event_type": event_type,
                    "location": location,
                },
                "forecast_cycle_id": forecast.forecast_cycle.isoformat(),
            }
        )

        # Get resolution date
        resolution_date = normalized.resolution_date or self._parse_resolution_date(
            market
        )

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
                await self._record_signal_audit(
                    "signal_refused",
                    ticker,
                    {
                        "reason_codes": ["SCREEN_FAILED"],
                        "yes_passed": False,
                        "no_passed": False,
                        "model_probability": blended_prob,
                        "market_probability": screen["edge"].market_probability,
                    },
                )
                return None
        else:
            side = "yes"
            entry_price = yes_ask

        # Calculate quantity
        kelly = screen["kelly"]
        quantity = int(kelly.recommended_bet_dollars / (entry_price / 100))
        quantity = max(1, quantity)

        signal = TradeSignal(
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
            event_type=event_type,
            location=location,
            region=normalized.region,
            correlation_group=normalized.relationship_group,
            resolution_date=resolution_date,
            source_metadata=normalized.to_dict(),
        )
        await self._record_signal_audit(
            "signal_generated",
            ticker,
            {
                "side": side,
                "quantity": quantity,
                "entry_price": entry_price,
                "edge": signal.edge,
                "passes_screen": True,
            },
        )
        return signal

    def _parse_market_title(self, title: str) -> tuple:
        """Parse location, event type, and threshold from market title."""
        return parse_weather_market_title(title)

    def _get_coordinates(self, location: str) -> tuple:
        """Get lat/lon for location code."""
        return CITY_COORDINATES.get(location, (40.0, -100.0))

    def _parse_resolution_date(self, market: Dict) -> datetime:
        """Parse resolution date from market data."""
        close_date = market.get("close_date") or market.get("expiration_date")
        if close_date:
            try:
                return parse_timestamp(close_date)
            except ValueError:
                pass
        return utcnow() + timedelta(days=7)

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
                    "size": (pos.entry_price or 0.0) * (pos.quantity or 0),
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
        logger.info(
            "EXECUTING: %s %s @ %s¢ x%d",
            signal.ticker,
            signal.side,
            signal.entry_price,
            signal.quantity,
        )
        client_order_id = f"weather_{utcnow().strftime('%Y%m%d%H%M%S')}"
        risk_decision = await self.evaluate_signal_risk(signal, dry_run=False)
        if not risk_decision.allowed:
            return {
                "success": False,
                "error": "risk policy blocked order",
                "risk_decision": risk_decision,
                "signal": signal,
            }

        order_record = self.order_ledger.submit(
            order_id=client_order_id,
            ticker=signal.ticker,
            side=signal.side,
            action=signal.action,
            order_type="limit",
            requested_quantity=signal.quantity,
            limit_price=int(signal.entry_price),
        )
        await self._record_signal_audit(
            "order_attempt",
            signal.ticker,
            {
                "client_order_id": client_order_id,
                "risk_decision": risk_decision.to_dict(),
            },
        )

        # Place order
        try:
            order = await self.kalshi.place_order(
                ticker=signal.ticker,
                side=signal.side,
                action=signal.action,
                type="limit",
                count=signal.quantity,
                price=int(signal.entry_price),
                client_order_id=client_order_id,
            )
        except Exception as exc:
            order_record = self.order_ledger.reject(
                client_order_id, reason=f"place_order failed: {exc}"
            )
            await self._record_signal_audit(
                "order_rejected",
                signal.ticker,
                {"client_order_id": client_order_id, "reason": str(exc)},
            )
            logger.exception("Order placement failed")
            return {"success": False, "error": str(exc), "order_record": order_record}

        if order.get("error"):
            order_record = self.order_ledger.reject(client_order_id, reason=str(order))
            await self._record_signal_audit(
                "order_rejected",
                signal.ticker,
                {"client_order_id": client_order_id, "reason": order},
            )
            logger.error("Order failed: %s", order)
            return {"success": False, "error": order, "order_record": order_record}

        rejection_reason = self._order_rejection_reason(order)
        if rejection_reason:
            order_record = self.order_ledger.reject(
                client_order_id, reason=rejection_reason
            )
            await self._record_signal_audit(
                "order_rejected",
                signal.ticker,
                {"client_order_id": client_order_id, "reason": rejection_reason},
            )
            logger.error("Order rejected: %s", rejection_reason)
            return {
                "success": False,
                "error": rejection_reason,
                "order": order,
                "order_record": order_record,
            }

        filled_quantity, average_fill_price = self._extract_fill(
            order,
            requested_quantity=signal.quantity,
            fallback_price=signal.entry_price,
        )
        if filled_quantity > 0:
            order_record = self.order_ledger.record_fill(
                client_order_id,
                quantity=filled_quantity,
                price=average_fill_price,
            )
            await self._record_signal_audit(
                "order_filled",
                signal.ticker,
                {
                    "client_order_id": client_order_id,
                    "filled_quantity": filled_quantity,
                    "average_fill_price": average_fill_price,
                },
            )
        else:
            logger.info("Order %s accepted with no immediate fill", client_order_id)
            return {
                "success": True,
                "position_id": None,
                "order": order,
                "order_record": order_record,
                "signal": signal,
            }

        # Record position in state
        position_data = {
            "ticker": signal.ticker,
            "event_title": signal.reason,
            "side": signal.side,
            "entry_price": average_fill_price / 100,
            "quantity": filled_quantity,
            "status": "open",
            "model_probability": signal.model_probability,
            "market_probability": signal.market_probability,
            "edge_at_entry": signal.edge,
            "iy_annualized": signal.iy_annualized,
            "las_at_entry": 0.0,
            "kelly_fraction": signal.kelly_fraction,
            "weather_event_type": signal.reason.split(":")[0].split("@")[0].strip(),
            "location": signal.location,
            "forecast_cycle": utcnow(),
            "resolution_date": signal.resolution_date or utcnow() + timedelta(days=7),
            "correlated_group": signal.correlation_group,
            "position_pct_of_bankroll": (average_fill_price / 100 * filled_quantity)
            / trading_config.initial_bankroll,
        }

        position_id = await self.state.add_position(position_data)

        return {
            "success": True,
            "position_id": position_id,
            "order": order,
            "order_record": order_record,
            "signal": signal,
        }

    async def run_continuous(self, interval_seconds: int = 300):
        """Run continuous scanning and trading loop."""
        self.running = True
        logger.info("Starting continuous loop (interval: %ds)", interval_seconds)

        while self.running:
            try:
                signals = await self.scan_and_evaluate()

                for signal in signals:
                    if signal.passes_screen:
                        if self.execute_orders:
                            await self.execute_signal(signal)
                        else:
                            await self.evaluate_signal_risk(signal, dry_run=True)
                            logger.info(
                                "DRY RUN signal: %s %s @ %s¢ x%d (%s)",
                                signal.ticker,
                                signal.side,
                                signal.entry_price,
                                signal.quantity,
                                signal.reason,
                            )

                # Check existing positions for exit signals
                await self._check_exits()
                expired_orders = self.order_ledger.reconcile_timeouts(
                    trading_config.order_ttl_seconds
                )
                if expired_orders:
                    logger.warning("Expired %d stale orders", len(expired_orders))

            except Exception:
                logger.exception("Loop error")

            await asyncio.sleep(interval_seconds)

    async def _check_exits(self):
        """Check open positions for exit conditions."""
        open_positions = await self.state.get_open_positions()

        for pos in open_positions:
            days_to_exp = (
                (pos.resolution_date - utcnow()).days if pos.resolution_date else 1
            )

            if days_to_exp <= 1:
                logger.info("Closing %s before expiration", pos.ticker)

    async def stop(self):
        """Stop the strategy."""
        self.running = False
        await self.weather.close()

    async def evaluate_signal_risk(
        self, signal: TradeSignal, *, dry_run: bool
    ) -> RiskDecision:
        """Evaluate and audit a signal before any live order placement."""
        intent = OrderIntent(
            ticker=signal.ticker,
            side=signal.side,
            action=signal.action,
            quantity=signal.quantity,
            limit_price=signal.entry_price,
            strategy_id=self.strategy_id,
            correlation_group=signal.correlation_group,
            region=signal.location or signal.region,
            event_type=signal.event_type or "weather",
            metadata={
                "dry_run": dry_run,
                "edge": signal.edge,
                "confidence": signal.confidence,
            },
        )
        await self._record_signal_audit(
            "order_intent",
            signal.ticker,
            {"dry_run": dry_run, "intent": intent.to_dict()},
        )
        decision = await self.risk_policy.evaluate(self.state, intent)
        await self._record_signal_audit(
            "risk_decision",
            signal.ticker,
            {"dry_run": dry_run, **decision.to_dict()},
        )
        if dry_run:
            await self._record_signal_audit(
                "dry_run_order_review",
                signal.ticker,
                {"risk_decision": decision.to_dict()},
            )
        return decision

    async def _record_signal_audit(
        self, event_type: str, ticker: str | None, payload: Dict[str, Any]
    ) -> None:
        await self.state.record_audit_event(
            event_type=event_type,
            subject=self.strategy_id,
            ticker=ticker,
            payload=payload,
        )

    def _extract_fill(
        self,
        order_response: Dict[str, Any],
        requested_quantity: int,
        fallback_price: float,
    ) -> tuple[int, float]:
        """Return immediate filled quantity and average fill price in cents."""
        payloads = self._order_payloads(order_response)
        fills = self._first_list(payloads, ("fills", "executions"))
        if fills:
            filled_quantity = 0
            notional = 0.0
            for fill in fills:
                if not isinstance(fill, dict):
                    continue
                quantity = self._first_int([fill], ("quantity", "count", "qty"))
                price = self._first_float(
                    [fill], ("price", "fill_price", "average_price", "avg_price")
                )
                if quantity and price is not None:
                    filled_quantity += quantity
                    notional += quantity * price
            if filled_quantity:
                return filled_quantity, notional / filled_quantity

        resolved = self._first_int(
            payloads,
            (
                "filled_quantity",
                "filled_count",
                "fill_count",
                "executed_quantity",
                "executed_count",
            ),
        )
        status = self._order_status(order_response)
        if resolved is None:
            if status in {"open", "pending", "resting", "working"}:
                resolved = 0
            elif status in {"partially_filled", "partial_fill"}:
                resolved = 0
            else:
                resolved = requested_quantity

        filled_quantity = max(0, min(resolved, requested_quantity))
        average_fill_price = self._first_float(
            payloads, ("average_price", "avg_price", "fill_price", "price")
        )
        if average_fill_price is None:
            average_fill_price = fallback_price
        return filled_quantity, average_fill_price

    def _order_rejection_reason(self, order_response: Dict[str, Any]) -> str:
        status = self._order_status(order_response)
        if status not in {"rejected", "cancelled", "canceled", "expired"}:
            return ""
        payloads = self._order_payloads(order_response)
        for payload in payloads:
            for key in ("reason", "message", "detail", "error"):
                if payload.get(key):
                    return str(payload[key])
        return f"order status is {status}"

    def _order_status(self, order_response: Dict[str, Any]) -> str:
        for payload in self._order_payloads(order_response):
            status = payload.get("status") or payload.get("state")
            if status:
                return str(status).lower()
        return ""

    def _order_payloads(self, order_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        payloads = [order_response]
        nested = order_response.get("order")
        if isinstance(nested, dict):
            payloads.insert(0, nested)
        return payloads

    def _first_list(
        self, payloads: List[Dict[str, Any]], keys: tuple[str, ...]
    ) -> list | None:
        for payload in payloads:
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return None

    def _first_int(
        self, payloads: List[Dict[str, Any]], keys: tuple[str, ...]
    ) -> int | None:
        for payload in payloads:
            for key in keys:
                value = payload.get(key)
                if value is not None:
                    return int(value)
        return None

    def _first_float(
        self, payloads: List[Dict[str, Any]], keys: tuple[str, ...]
    ) -> float | None:
        for payload in payloads:
            for key in keys:
                value = payload.get(key)
                if value is not None:
                    return float(value)
        return None
