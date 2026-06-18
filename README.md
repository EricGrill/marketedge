# MarketEdge

A stateful CLI + TUI application for quantitative prediction-market research, opportunity screening, and risk-aware strategy execution. The current implementation starts with weather markets on Kalshi, but the project is intended to expand across event-market categories.

## Architecture

```
kalshi_weather_quant/
├── src/
│   ├── cli.py              # Click CLI entry point
│   ├── config.py           # Configuration & env vars
│   ├── state.py            # SQLite state manager (positions, forecasts, snapshots)
│   ├── formulas.py         # Quant engine (Kelly, IY, LAS, Bayesian, RoR)
│   ├── api/
│   │   └── client.py       # Kalshi REST + WebSocket client, weather market scanner
│   ├── weather/
│   │   └── data.py         # NWS + Open-Meteo fetchers, model blending, analog matching
│   ├── strategies/
│   │   └── weather.py      # Main trading strategy (scan -> evaluate -> execute)
│   └── tui/
│       └── app.py          # Textual TUI dashboard
├── data/                   # SQLite database
├── requirements.txt
└── .env.example
```

## Installation

```bash
cd kalshi_weather_quant
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Kalshi API credentials
```

## CLI Commands

```bash
# Launch TUI dashboard
python -m src.cli dashboard

# Analyze a specific market
python -m src.cli analyze --ticker RAIN-NYC-2026-05-15 --model-prob 0.65 --side yes

# Run trading strategy (dry run)
python -m src.cli trade --dry --interval 300

# Live trading (requires API key)
python -m src.cli trade --live --interval 300

# View positions
python -m src.cli positions

# View portfolio
python -m src.cli portfolio

# Fetch weather data
python -m src.cli weather --lat 40.71 --lon -74.01 --event-type rain --threshold 1.0

# Display formulas
python -m src.cli formulas
```

## Quant Formulas Implemented

1. **Fee-Adjusted Edge**: `p_model / (1 + 0.03 * p_model)` — accounts for Kalshi's 3% settlement fee
2. **Kelly Criterion**: `(p*(b+1) - 1) / b` with 1/4 fractional Kelly
3. **Annualized Yield (IY)**: `(1 / price)^(365 / days) - 1` for opportunity screening
4. **Liquidity Spread (LAS)**: `(Ask - Bid) / Mid` with size reduction rules
5. **Bayesian Update**: Continuous forecast blending as NWS/ECMWF cycles update
6. **Weather Model Blend**: `0.30*ECMWF + 0.25*GEFS + 0.20*Analog + 0.15*Micro + 0.10*NWS_delta`
7. **Risk of Ruin**: `((1-edge)/(1+edge))^(bankroll/bet_size)`
8. **Portfolio Correlation**: Geographic and event-type correlation exposure limits

## Weather Data Sources

- **NWS API**: Official US probabilistic forecasts (PoP, gridpoint data)
- **Open-Meteo**: Free ensemble forecasts (ECMWF, GFS, ICON models)
- **Analog Years**: Historical pattern matching (ENSO, NAO, PDO phases)
- **Microclimate**: Urban heat island, elevation, proximity adjustments

## State Management

All data persists in SQLite:
- `positions`: Open/closed trades with model metadata
- `weather_forecasts`: Blended model outputs per forecast cycle
- `market_snapshots`: Orderbook history for backtesting
- `portfolio_state`: Bankroll, exposure, P&L, drawdown tracking

## Risk Controls

- Max 20% bankroll in single position
- Max 30% in correlated group (same region/event type)
- 1/4 Kelly sizing with confidence adjustment
- LAS-based size reduction (skip if spread > 15%)
- Auto-close within 1 day of expiration to avoid settlement fees
- Monthly RoR target < 1%

## TUI Dashboard

Hotkeys:
- `q` — Quit
- `r` — Refresh data
- `s` — Trigger market scan

Widgets:
- Portfolio summary (bankroll, exposure, P&L)
- Risk metrics (RoR, max drawdown, VaR)
- Open positions table
- Recent signals log
- Market scanner controls
- Settings panel
