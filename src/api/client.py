# marketedge/src/api/client.py
"""Kalshi API client with REST and WebSocket support."""

import json
import hmac
import hashlib
import base64
import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Tuple
from dataclasses import dataclass

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from src.config import kalshi_config
from src.utils import utcnow

logger = logging.getLogger(__name__)


@dataclass
class KalshiCredentials:
    api_key: str
    api_secret: str


class KalshiAuth:
    """HMAC-SHA256 authentication for Kalshi API."""

    def __init__(self, creds: KalshiCredentials):
        self.creds = creds

    def generate_signature(
        self, method: str, path: str, body: str = ""
    ) -> Tuple[str, str]:
        """Generate HMAC signature for request."""
        timestamp = str(int(utcnow().timestamp()))
        msg_string = timestamp + method.upper() + path + body

        signature = hmac.new(
            self.creds.api_secret.encode("utf-8"),
            msg_string.encode("utf-8"),
            hashlib.sha256,
        ).digest()

        return base64.b64encode(signature).decode("utf-8"), timestamp

    def get_headers(self, method: str, path: str, body: str = "") -> Dict[str, str]:
        """Get auth headers for request."""
        signature, timestamp = self.generate_signature(method, path, body)
        return {
            "KALSHI-ACCESS-KEY": self.creds.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }


def _decode_error_body(response: httpx.Response) -> Dict[str, Any]:
    """Best-effort read of an error response body.

    Kalshi normally returns JSON errors, but gateways, proxies and rate
    limiters return HTML or plain text. Parsing that with ``.json()`` raises
    ``JSONDecodeError`` — and because the parse happens *inside* an
    ``except`` block, the surrounding ``except Exception`` cannot catch it, so
    the whole request crashed the caller instead of returning an error dict.
    """
    if not response.content:
        return {}
    try:
        parsed = response.json()
    except ValueError:
        # Not JSON. Surface the raw text so the operator can still see what
        # the gateway said, truncated so an HTML error page stays readable.
        text = response.text.strip()
        if len(text) > _MAX_ERROR_BODY_CHARS:
            text = text[:_MAX_ERROR_BODY_CHARS] + "..."
        return {"message": text, "parse_error": "response body was not JSON"}
    # A JSON body is only useful as a dict; scalars/lists get wrapped so
    # callers can always treat `detail` as a mapping.
    return parsed if isinstance(parsed, dict) else {"message": parsed}


_MAX_ERROR_BODY_CHARS = 500


class KalshiRestClient:
    """REST API client for Kalshi."""

    def __init__(self, config=kalshi_config):
        self.config = config
        self.auth = KalshiAuth(KalshiCredentials(config.api_key, config.api_secret))
        self.client = httpx.AsyncClient(base_url=config.base_url, timeout=30.0)

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        body: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Make authenticated request."""
        body_str = json.dumps(body) if body else ""
        headers = self.auth.get_headers(method, path, body_str)

        try:
            if method.upper() == "GET":
                resp = await self.client.get(path, headers=headers, params=params)
            elif method.upper() == "POST":
                resp = await self.client.post(path, headers=headers, json=body)
            elif method.upper() == "DELETE":
                resp = await self.client.delete(path, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")

            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            return {
                "error": True,
                "status_code": e.response.status_code,
                "detail": _decode_error_body(e.response),
            }
        except Exception as e:
            return {"error": True, "detail": str(e)}

    # ===== MARKET DATA =====

    async def get_markets(
        self,
        status: str = "open",
        category: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> Dict:
        """Get list of markets."""
        params = {"status": status, "limit": limit}
        if category:
            params["category"] = category
        if cursor:
            params["cursor"] = cursor
        return await self._request("GET", "/trade-api/v2/markets", params=params)

    async def get_market(self, ticker: str) -> Dict:
        """Get specific market details."""
        return await self._request("GET", f"/trade-api/v2/markets/{ticker}")

    async def get_market_orderbook(self, ticker: str, depth: int = 10) -> Dict:
        """Get order book for a market."""
        params = {"depth": depth}
        return await self._request(
            "GET", f"/trade-api/v2/markets/{ticker}/orderbook", params=params
        )

    async def get_series(self, series_ticker: str) -> Dict:
        """Get series information."""
        return await self._request("GET", f"/trade-api/v2/series/{series_ticker}")

    async def get_events(
        self, status: str = "open", category: Optional[str] = None, limit: int = 100
    ) -> Dict:
        """Get events (groups of markets)."""
        params = {"status": status, "limit": limit}
        if category:
            params["category"] = category
        return await self._request("GET", "/trade-api/v2/events", params=params)

    async def get_event(self, event_ticker: str) -> Dict:
        """Get specific event."""
        return await self._request("GET", f"/trade-api/v2/events/{event_ticker}")

    # ===== TRADING =====

    async def place_order(
        self,
        ticker: str,
        side: str,  # yes or no
        action: str,  # buy or sell
        type: str,  # limit or market
        count: int,
        price: Optional[int] = None,  # In cents for limit orders
        client_order_id: Optional[str] = None,
    ) -> Dict:
        """Place an order."""
        body = {
            "ticker": ticker,
            "side": side,
            "action": action,
            "type": type,
            "count": count,
        }
        if price is not None:
            body["price"] = price
        if client_order_id:
            body["client_order_id"] = client_order_id
        return await self._request("POST", "/trade-api/v2/orders", body=body)

    async def cancel_order(self, order_id: str) -> Dict:
        """Cancel an order."""
        return await self._request("DELETE", f"/trade-api/v2/orders/{order_id}")

    async def get_orders(
        self,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> Dict:
        """Get your orders."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if ticker:
            params["ticker"] = ticker
        return await self._request("GET", "/trade-api/v2/orders", params=params)

    async def get_order(self, order_id: str) -> Dict:
        """Get specific order."""
        return await self._request("GET", f"/trade-api/v2/orders/{order_id}")

    # ===== ACCOUNT =====

    async def get_balance(self) -> Dict:
        """Get account balance."""
        return await self._request("GET", "/trade-api/v2/user/balance")

    async def get_positions(
        self,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> Dict:
        """Get positions."""
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if ticker:
            params["ticker"] = ticker
        return await self._request("GET", "/trade-api/v2/positions", params=params)

    async def get_fills(
        self,
        order_id: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 100,
    ) -> Dict:
        """Get fill history."""
        params: Dict[str, Any] = {"limit": limit}
        if order_id:
            params["order_id"] = order_id
        if ticker:
            params["ticker"] = ticker
        return await self._request("GET", "/trade-api/v2/fills", params=params)

    async def close(self):
        await self.client.aclose()


class KalshiWebSocketClient:
    """WebSocket client for real-time market data."""

    def __init__(self, config=kalshi_config):
        self.config = config
        self.auth = KalshiAuth(KalshiCredentials(config.api_key, config.api_secret))
        self.ws = None
        self.connected = False
        self.subscriptions = set()
        self.message_handlers: List[Callable] = []
        self._running = False

    async def connect(self):
        """Connect to WebSocket."""
        signature, timestamp = self.auth.generate_signature("GET", "/ws/v2")

        headers = {
            "KALSHI-ACCESS-KEY": self.auth.creds.api_key,
            "KALSHI-ACCESS-SIGNATURE": signature,
            "KALSHI-ACCESS-TIMESTAMP": timestamp,
        }

        try:
            self.ws = await websockets.connect(
                self.config.ws_url, extra_headers=headers
            )
            self.connected = True
            self._running = True
            logger.info("Connected to %s", self.config.ws_url)

            # Start message handler loop
            asyncio.create_task(self._message_loop())
            return True
        except Exception:
            logger.exception("Connection failed")
            return False

    async def _message_loop(self):
        """Handle incoming messages."""
        while self._running and self.ws:
            try:
                msg = await self.ws.recv()
                data = json.loads(msg)

                # Call all registered handlers
                for handler in self.message_handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            asyncio.create_task(handler(data))
                        else:
                            handler(data)
                    except Exception:
                        logger.exception("Handler error")

            except ConnectionClosed:
                logger.info("Connection closed")
                self.connected = False
                break
            except Exception:
                logger.exception("Message loop error")

    async def subscribe_orderbook(self, ticker: str):
        """Subscribe to orderbook updates."""
        if not self.connected:
            await self.connect()

        msg = {"type": "subscribe", "channel": "orderbook", "market_ticker": ticker}
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"orderbook:{ticker}")
        logger.info("Subscribed to orderbook: %s", ticker)

    async def subscribe_trades(self, ticker: str):
        """Subscribe to trade updates."""
        if not self.connected:
            await self.connect()

        msg = {"type": "subscribe", "channel": "trades", "market_ticker": ticker}
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"trades:{ticker}")
        logger.info("Subscribed to trades: %s", ticker)

    async def subscribe_ticker(self, ticker: str):
        """Subscribe to ticker updates."""
        if not self.connected:
            await self.connect()

        msg = {"type": "subscribe", "channel": "ticker", "market_ticker": ticker}
        await self.ws.send(json.dumps(msg))
        self.subscriptions.add(f"ticker:{ticker}")
        logger.info("Subscribed to ticker: %s", ticker)

    def add_handler(self, handler: Callable):
        """Add message handler."""
        self.message_handlers.append(handler)

    async def disconnect(self):
        """Disconnect WebSocket."""
        self._running = False
        if self.ws:
            await self.ws.close()
            self.ws = None
        self.connected = False
        logger.info("Disconnected")


# Weather-specific market scanner
class WeatherMarketScanner:
    """Scan Kalshi for weather-related markets."""

    WEATHER_KEYWORDS = [
        "rain",
        "snow",
        "temperature",
        "temp",
        "hurricane",
        "storm",
        "tornado",
        "wind",
        "precipitation",
        "drought",
        "flood",
        "weather",
        "climate",
        "season",
        "winter",
        "summer",
        "spring",
        "fall",
    ]

    def __init__(self, client: KalshiRestClient):
        self.client = client

    async def scan_weather_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Scan for weather markets."""
        weather_markets = []

        # Get events first (weather events are often grouped)
        events_resp = await self.client.get_events(status="open", limit=limit)
        events = events_resp.get("events", [])

        for event in events:
            title = event.get("title", "").lower()
            if any(kw in title for kw in self.WEATHER_KEYWORDS):
                # Get markets for this event
                event_ticker = event.get("ticker")
                if event_ticker:
                    event_detail = await self.client.get_event(event_ticker)
                    markets = event_detail.get("markets", [])
                    for market in markets:
                        market["event_title"] = event.get("title")
                        market["event_category"] = event.get("category")
                        weather_markets.append(market)

        # Also scan individual markets
        markets_resp = await self.client.get_markets(status="open", limit=limit)
        markets = markets_resp.get("markets", [])

        for market in markets:
            title = market.get("title", "").lower()
            if any(kw in title for kw in self.WEATHER_KEYWORDS):
                if market not in weather_markets:
                    weather_markets.append(market)

        return weather_markets

    async def get_market_with_orderbook(self, ticker: str) -> Dict[str, Any]:
        """Get market details + current orderbook."""
        market = await self.client.get_market(ticker)
        orderbook = await self.client.get_market_orderbook(ticker)

        return {
            "market": market,
            "orderbook": orderbook,
            "timestamp": utcnow().isoformat(),
        }
