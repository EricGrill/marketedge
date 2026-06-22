"""Create state tables and audit trail.

Revision ID: 0001_state_and_audit
Revises:
Create Date: 2026-06-22
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0001_state_and_audit"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portfolio_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bankroll", sa.Float(), nullable=True),
        sa.Column("available_cash", sa.Float(), nullable=True),
        sa.Column("total_exposure", sa.Float(), nullable=True),
        sa.Column("open_positions_count", sa.Integer(), nullable=True),
        sa.Column("mtd_pnl", sa.Float(), nullable=True),
        sa.Column("ytd_pnl", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("peak_bankroll", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "schema_migrations",
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("applied_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("version"),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=False),
        sa.Column("event_title", sa.String(length=500), nullable=True),
        sa.Column("side", sa.String(length=10), nullable=True),
        sa.Column("entry_price", sa.Float(), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=True),
        sa.Column("model_probability", sa.Float(), nullable=True),
        sa.Column("market_probability", sa.Float(), nullable=True),
        sa.Column("edge_at_entry", sa.Float(), nullable=True),
        sa.Column("iy_annualized", sa.Float(), nullable=True),
        sa.Column("las_at_entry", sa.Float(), nullable=True),
        sa.Column("kelly_fraction", sa.Float(), nullable=True),
        sa.Column("weather_event_type", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("forecast_cycle", sa.DateTime(), nullable=True),
        sa.Column("resolution_date", sa.DateTime(), nullable=True),
        sa.Column("correlated_group", sa.String(length=50), nullable=True),
        sa.Column("position_pct_of_bankroll", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("realized_pnl", sa.Float(), nullable=True),
        sa.Column("settlement_fee", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "weather_forecasts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=50), nullable=True),
        sa.Column("forecast_cycle", sa.DateTime(), nullable=True),
        sa.Column("ecmwf_prob", sa.Float(), nullable=True),
        sa.Column("gefs_prob", sa.Float(), nullable=True),
        sa.Column("analog_prob", sa.Float(), nullable=True),
        sa.Column("microclimate_prob", sa.Float(), nullable=True),
        sa.Column("nws_delta", sa.Float(), nullable=True),
        sa.Column("blended_probability", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("market_ticker", sa.String(length=50), nullable=True),
        sa.Column("market_price", sa.Float(), nullable=True),
        sa.Column("market_timestamp", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "market_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=True),
        sa.Column("bid", sa.Float(), nullable=True),
        sa.Column("ask", sa.Float(), nullable=True),
        sa.Column("last_price", sa.Float(), nullable=True),
        sa.Column("volume_24h", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("yes_ask", sa.Float(), nullable=True),
        sa.Column("yes_bid", sa.Float(), nullable=True),
        sa.Column("no_ask", sa.Float(), nullable=True),
        sa.Column("no_bid", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("subject", sa.String(length=120), nullable=False),
        sa.Column("ticker", sa.String(length=50), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("position_id", sa.Integer(), nullable=True),
        sa.Column("trade_type", sa.String(length=20), nullable=True),
        sa.Column("side", sa.String(length=10), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_positions_ticker", "positions", ["ticker"], unique=False)
    op.create_index(
        "ix_weather_forecasts_location", "weather_forecasts", ["location"], unique=False
    )
    op.create_index(
        "ix_weather_forecasts_forecast_cycle",
        "weather_forecasts",
        ["forecast_cycle"],
        unique=False,
    )
    op.create_index(
        "ix_market_snapshots_ticker", "market_snapshots", ["ticker"], unique=False
    )
    op.create_index(
        "ix_market_snapshots_timestamp",
        "market_snapshots",
        ["timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_audit_events_event_type", "audit_events", ["event_type"], unique=False
    )
    op.create_index(
        "ix_audit_events_subject", "audit_events", ["subject"], unique=False
    )
    op.create_index("ix_audit_events_ticker", "audit_events", ["ticker"], unique=False)
    op.create_index(
        "ix_audit_events_created_at", "audit_events", ["created_at"], unique=False
    )

    schema_migrations = sa.table(
        "schema_migrations",
        sa.column("version", sa.String()),
        sa.column("description", sa.String()),
        sa.column("applied_at", sa.DateTime()),
    )
    op.bulk_insert(
        schema_migrations,
        [
            {
                "version": "0001_state_and_audit",
                "description": (
                    "Create state tables, schema migration ledger, and audit event log."
                ),
                "applied_at": datetime.now(timezone.utc).replace(tzinfo=None),
            }
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_ticker", table_name="audit_events")
    op.drop_index("ix_audit_events_subject", table_name="audit_events")
    op.drop_index("ix_audit_events_event_type", table_name="audit_events")
    op.drop_index("ix_market_snapshots_timestamp", table_name="market_snapshots")
    op.drop_index("ix_market_snapshots_ticker", table_name="market_snapshots")
    op.drop_index("ix_weather_forecasts_forecast_cycle", table_name="weather_forecasts")
    op.drop_index("ix_weather_forecasts_location", table_name="weather_forecasts")
    op.drop_index("ix_positions_ticker", table_name="positions")
    op.drop_table("trades")
    op.drop_table("audit_events")
    op.drop_table("market_snapshots")
    op.drop_table("weather_forecasts")
    op.drop_table("positions")
    op.drop_table("schema_migrations")
    op.drop_table("portfolio_state")
