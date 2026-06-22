# marketedge/src/state.py
"""Stateful server with SQLite backend for positions, trades, and model outputs."""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from enum import Enum

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    Float,
    String,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

Base = declarative_base()

SCHEMA_VERSION = "0001_state_and_audit"
SCHEMA_DESCRIPTION = (
    "Create state tables, schema migration ledger, and audit event log."
)


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    PENDING = "pending"


class TradeSide(str, Enum):
    YES = "yes"
    NO = "no"


# ========== DATABASE MODELS ==========


class Position(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(50), nullable=False, index=True)
    event_title = Column(String(500))
    side = Column(String(10))
    entry_price = Column(Float)
    exit_price = Column(Float, nullable=True)
    quantity = Column(Integer)
    status = Column(String(20), default="open")

    # Model data
    model_probability = Column(Float)
    market_probability = Column(Float)
    edge_at_entry = Column(Float)
    iy_annualized = Column(Float)
    las_at_entry = Column(Float)
    kelly_fraction = Column(Float)

    # Weather specifics
    weather_event_type = Column(String(50))  # rain, temp, wind, snow
    location = Column(String(100))
    forecast_cycle = Column(DateTime)
    resolution_date = Column(DateTime)

    # Risk
    correlated_group = Column(String(50), nullable=True)
    position_pct_of_bankroll = Column(Float)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)

    # P&L
    realized_pnl = Column(Float, nullable=True)
    settlement_fee = Column(Float, nullable=True)

    trades = relationship(
        "Trade", back_populates="position", cascade="all, delete-orphan"
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    position_id = Column(Integer, ForeignKey("positions.id"))
    trade_type = Column(String(20))  # entry, exit, partial
    side = Column(String(10))
    price = Column(Float)
    quantity = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)

    position = relationship("Position", back_populates="trades")


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"

    id = Column(Integer, primary_key=True)
    location = Column(String(100), index=True)
    event_type = Column(String(50))
    forecast_cycle = Column(DateTime, index=True)

    # Raw model outputs
    ecmwf_prob = Column(Float)
    gefs_prob = Column(Float)
    analog_prob = Column(Float)
    microclimate_prob = Column(Float)
    nws_delta = Column(Float)

    # Blended
    blended_probability = Column(Float)
    confidence = Column(Float)  # 0-1 based on ensemble spread

    # Market snapshot
    market_ticker = Column(String(50))
    market_price = Column(Float, nullable=True)
    market_timestamp = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True)
    ticker = Column(String(50), index=True)
    bid = Column(Float)
    ask = Column(Float)
    last_price = Column(Float)
    volume_24h = Column(Integer)
    open_interest = Column(Integer)
    yes_ask = Column(Float)
    yes_bid = Column(Float)
    no_ask = Column(Float)
    no_bid = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class PortfolioState(Base):
    __tablename__ = "portfolio_state"

    id = Column(Integer, primary_key=True)
    bankroll = Column(Float, default=10000.0)
    available_cash = Column(Float, default=10000.0)
    total_exposure = Column(Float, default=0.0)
    open_positions_count = Column(Integer, default=0)
    mtd_pnl = Column(Float, default=0.0)
    ytd_pnl = Column(Float, default=0.0)
    max_drawdown = Column(Float, default=0.0)
    peak_bankroll = Column(Float, default=10000.0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version = Column(String(64), primary_key=True)
    description = Column(String(255), nullable=False)
    applied_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True)
    event_type = Column(String(80), nullable=False, index=True)
    subject = Column(String(120), nullable=False, index=True)
    ticker = Column(String(50), nullable=True, index=True)
    payload_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)


# ========== STATE MANAGER ==========


class StateManager:
    """Thread-safe state manager with async SQLite backend."""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.getenv(
            "MARKETEDGE_DB_PATH", "data/kalshi_quant.db"
        )
        db_parent = os.path.dirname(self.db_path)
        if db_parent:
            os.makedirs(db_parent, exist_ok=True)
        self.engine = create_engine(f"sqlite:///{self.db_path}")
        self.Session = sessionmaker(bind=self.engine)
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self):
        Base.metadata.create_all(self.engine)
        with self.Session() as session:
            if (
                not session.query(SchemaMigration)
                .filter_by(version=SCHEMA_VERSION)
                .first()
            ):
                session.add(
                    SchemaMigration(
                        version=SCHEMA_VERSION,
                        description=SCHEMA_DESCRIPTION,
                    )
                )
            if not session.query(PortfolioState).first():
                session.add(PortfolioState())
            session.commit()

    async def list_schema_migrations(self) -> List[SchemaMigration]:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(SchemaMigration)
                    .order_by(SchemaMigration.applied_at.asc())
                    .all()
                )

    async def record_audit_event(
        self,
        event_type: str,
        subject: str,
        ticker: str | None = None,
        payload: Dict[str, Any] | None = None,
    ) -> int:
        async with self._lock:
            with self.Session() as session:
                event = AuditEvent(
                    event_type=event_type,
                    subject=subject,
                    ticker=ticker,
                    payload_json=json.dumps(payload or {}, sort_keys=True),
                )
                session.add(event)
                session.commit()
                return event.id

    async def list_audit_events(self, limit: int = 100) -> List[AuditEvent]:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(AuditEvent)
                    .order_by(AuditEvent.created_at.desc())
                    .limit(limit)
                    .all()
                )

    async def add_position(self, position_data: Dict[str, Any]) -> int:
        async with self._lock:
            with self.Session() as session:
                pos = Position(**position_data)
                session.add(pos)
                session.commit()
                pos_id = pos.id
                self._update_portfolio_state(session)
                return pos_id

    async def close_position(
        self, position_id: int, exit_price: float, pnl: float, fee: float = 0
    ):
        async with self._lock:
            with self.Session() as session:
                pos = session.query(Position).get(position_id)
                if pos:
                    pos.status = "closed"
                    pos.exit_price = exit_price
                    pos.realized_pnl = pnl
                    pos.settlement_fee = fee
                    pos.closed_at = datetime.utcnow()
                    session.commit()
                    self._update_portfolio_state(session)

    async def get_open_positions(self) -> List[Position]:
        async with self._lock:
            with self.Session() as session:
                return session.query(Position).filter_by(status="open").all()

    async def get_positions_by_correlation_group(self, group: str) -> List[Position]:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(Position)
                    .filter_by(correlated_group=group, status="open")
                    .all()
                )

    async def add_weather_forecast(self, forecast_data: Dict[str, Any]) -> int:
        async with self._lock:
            with self.Session() as session:
                fc = WeatherForecast(**forecast_data)
                session.add(fc)
                session.commit()
                return fc.id

    async def get_latest_forecast(self, ticker: str) -> Optional[WeatherForecast]:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(WeatherForecast)
                    .filter_by(market_ticker=ticker)
                    .order_by(WeatherForecast.created_at.desc())
                    .first()
                )

    async def add_market_snapshot(self, snapshot: Dict[str, Any]):
        async with self._lock:
            with self.Session() as session:
                snap = MarketSnapshot(**snapshot)
                session.add(snap)
                session.commit()

    async def get_latest_market_snapshots(
        self, limit: int = 100
    ) -> List[MarketSnapshot]:
        async with self._lock:
            with self.Session() as session:
                snapshots = (
                    session.query(MarketSnapshot)
                    .order_by(MarketSnapshot.timestamp.desc())
                    .limit(limit * 3)
                    .all()
                )
                latest_by_ticker: Dict[str, MarketSnapshot] = {}
                for snapshot in snapshots:
                    if snapshot.ticker not in latest_by_ticker:
                        latest_by_ticker[snapshot.ticker] = snapshot
                    if len(latest_by_ticker) >= limit:
                        break
                return list(latest_by_ticker.values())

    async def get_portfolio_state(self) -> PortfolioState:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(PortfolioState)
                    .order_by(PortfolioState.updated_at.desc())
                    .first()
                )

    def _update_portfolio_state(self, session):
        """Recalculate portfolio aggregates."""
        open_pos = session.query(Position).filter_by(status="open").all()

        total_exposure = sum(p.entry_price * p.quantity for p in open_pos)
        open_count = len(open_pos)

        # P&L calc
        closed_pos = session.query(Position).filter_by(status="closed").all()
        mtd_pnl = sum(
            p.realized_pnl or 0
            for p in closed_pos
            if p.closed_at and p.closed_at > datetime.utcnow() - timedelta(days=30)
        )

        portfolio = session.query(PortfolioState).first()
        portfolio.available_cash = portfolio.bankroll - total_exposure
        portfolio.total_exposure = total_exposure
        portfolio.open_positions_count = open_count
        portfolio.mtd_pnl = mtd_pnl
        portfolio.updated_at = datetime.utcnow()
        session.commit()

    async def get_all_positions(self, limit: int = 100) -> List[Position]:
        async with self._lock:
            with self.Session() as session:
                return (
                    session.query(Position)
                    .order_by(Position.created_at.desc())
                    .limit(limit)
                    .all()
                )

    async def get_position(self, position_id: int) -> Optional[Position]:
        async with self._lock:
            with self.Session() as session:
                return session.query(Position).get(position_id)
