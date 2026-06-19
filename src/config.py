# marketedge/src/config.py
"""Configuration management with environment variables."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass
class KalshiConfig:
    """Kalshi API configuration."""

    api_key: str = field(default_factory=lambda: os.getenv("KALSHI_API_KEY", ""))
    api_secret: str = field(default_factory=lambda: os.getenv("KALSHI_API_SECRET", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "KALSHI_BASE_URL", "https://api.elections.kalshi.com"
        )
    )
    ws_url: str = field(
        default_factory=lambda: os.getenv(
            "KALSHI_WS_URL", "wss://api.elections.kalshi.com/ws/v2"
        )
    )
    sandbox: bool = field(
        default_factory=lambda: os.getenv("KALSHI_SANDBOX", "true").lower() == "true"
    )

    def __post_init__(self):
        if self.sandbox:
            self.base_url = "https://demo-api.kalshi.co"
            self.ws_url = "wss://demo-api.kalshi.co/ws/v2"


@dataclass
class TradingConfig:
    """Trading parameters and risk limits."""

    # Kelly sizing
    kelly_fraction: float = 0.25  # 1/4 Kelly
    max_position_pct: float = 0.20  # Max 20% in single event
    max_correlated_pct: float = 0.30  # Max 30% in correlated group

    # Edge thresholds
    min_edge_pct: float = 0.03  # 3% minimum edge
    min_iy_annualized: float = 0.50  # 50% annualized yield
    max_las: float = 0.10  # Max liquidity spread

    # Fees
    settlement_fee_pct: float = 0.03  # 3% on winners

    # Risk of ruin target
    max_ror_monthly: float = 0.01  # 1% monthly

    # Portfolio
    initial_bankroll: float = 10000.0
    max_open_positions: int = 20


@dataclass
class WeatherConfig:
    """Weather data sources and model weights."""

    # API endpoints
    nws_api: str = "https://api.weather.gov"
    openmeteo_api: str = "https://api.open-meteo.com"

    # Model weights (must sum to 1.0)
    ecmwf_weight: float = 0.30
    gefs_weight: float = 0.25
    analog_weight: float = 0.20
    microclimate_weight: float = 0.15
    nws_delta_weight: float = 0.10

    # Update cycle (hours)
    forecast_cycle_hours: int = 6
    execution_window_minutes: int = 10

    # Geographic correlation radius (miles)
    correlation_radius_miles: float = 150.0


# Global instances
kalshi_config = KalshiConfig()
trading_config = TradingConfig()
weather_config = WeatherConfig()
