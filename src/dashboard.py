"""Generate dashboard-ready JSON from local Market Edge state."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from src.formulas import QuantEngine, REGION_BY_CITY
from src.paper import PaperTradingLedger
from src.state import StateManager


async def build_dashboard_payload(
    state: StateManager,
    paper_ledger_path: str | Path | None = None,
    backtest_summary_path: str | Path | None = None,
) -> Dict[str, Any]:
    """Build one JSON payload consumed by the static dashboard."""
    portfolio = await state.get_portfolio_state()
    positions = await state.get_open_positions()
    position_payloads = [_position_payload(position) for position in positions]
    snapshots = await state.get_latest_market_snapshots()

    payload: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "account": _portfolio_payload(portfolio),
        "markets": [_market_payload(snapshot) for snapshot in snapshots],
        "positions": position_payloads,
        "risk": QuantEngine().summarize_correlated_risk(
            position_payloads,
            bankroll=portfolio.bankroll if portfolio else 0,
        ),
    }

    if paper_ledger_path:
        ledger = PaperTradingLedger(paper_ledger_path)
        payload["paper"] = ledger.summary()
    if backtest_summary_path:
        path = Path(backtest_summary_path)
        if path.exists():
            payload["backtest"] = json.loads(path.read_text(encoding="utf-8"))
    return payload


def write_dashboard_payload(payload: Dict[str, Any], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def _portfolio_payload(portfolio) -> Dict[str, Any]:
    if not portfolio:
        return {}
    return {
        "bankroll": portfolio.bankroll,
        "available_cash": portfolio.available_cash,
        "total_exposure": portfolio.total_exposure,
        "open_positions_count": portfolio.open_positions_count,
        "mtd_pnl": portfolio.mtd_pnl,
        "ytd_pnl": portfolio.ytd_pnl,
        "max_drawdown": portfolio.max_drawdown,
        "updated_at": (
            portfolio.updated_at.isoformat() if portfolio.updated_at else None
        ),
    }


def _market_payload(snapshot) -> Dict[str, Any]:
    return {
        "id": snapshot.ticker,
        "ticker": snapshot.ticker,
        "title": snapshot.ticker,
        "city": _city_from_ticker(snapshot.ticker),
        "bracket": snapshot.ticker.split("-")[-1],
        "last": snapshot.last_price,
        "bid": snapshot.bid,
        "ask": snapshot.ask,
        "yes_bid": snapshot.yes_bid,
        "yes_ask": snapshot.yes_ask,
        "no_bid": snapshot.no_bid,
        "no_ask": snapshot.no_ask,
        "volume": snapshot.volume_24h,
        "open_interest": snapshot.open_interest,
        "timestamp": snapshot.timestamp.isoformat() if snapshot.timestamp else None,
        "source": "state",
    }


def _position_payload(position) -> Dict[str, Any]:
    return {
        "id": position.id,
        "ticker": position.ticker,
        "title": position.event_title,
        "side": position.side,
        "entry_price": position.entry_price,
        "exit_price": position.exit_price,
        "quantity": position.quantity,
        "status": position.status,
        "edge_at_entry": position.edge_at_entry,
        "iy_annualized": position.iy_annualized,
        "location": position.location,
        "city": position.location,
        "region": _region_from_location(position.location),
        "weather_event_type": position.weather_event_type,
        "event_type": position.weather_event_type,
        "resolution_date": (
            position.resolution_date.isoformat() if position.resolution_date else None
        ),
        "correlated_group": position.correlated_group,
        "correlation_group": position.correlated_group,
        "model_probability": position.model_probability,
        "market_probability": position.market_probability,
        "created_at": position.created_at.isoformat() if position.created_at else None,
        "realized_pnl": position.realized_pnl,
    }


def _city_from_ticker(ticker: str) -> str:
    upper = ticker.upper()
    known = ["NYC", "CHI", "MIA", "LAX", "DEN", "AUS", "BOS", "SEA", "HOU", "PHX"]
    for city in known:
        if city in upper:
            return city
    return "MKT"


def _region_from_location(location: str | None) -> str:
    city = (location or "").upper()
    return REGION_BY_CITY.get(city, "unknown")
