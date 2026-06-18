# Market Edge

Market Edge is a prediction-market quant research and execution workbench.
It is designed to help identify mispricings, arbitrage-like opportunities,
hedging opportunities, and risk-aware strategies across event markets.

The current implementation starts with Kalshi weather markets. The project is
intended to expand beyond weather into other event-market categories once the
core adapter, risk, persistence, and operations layers are production-ready.

## Status

Market Edge is currently **experimental and research-first**.

Use dry-run and analysis workflows only. Live trading is not production-ready
until the live-trading safety gates, kill switches, operator diagnostics, and
audit trail work are complete.

Known production-readiness gaps are tracked in Linear:

- [CHA-1040](https://linear.app/chainbytes/issue/CHA-1040/prod-001-restore-ci-and-release-verification-for-marketedge): restore CI and release verification.
- [CHA-1041](https://linear.app/chainbytes/issue/CHA-1041/prod-002-add-explicit-live-trading-safety-gates-and-kill-switches): add live-trading safety gates and kill switches.
- [CHA-1042](https://linear.app/chainbytes/issue/CHA-1042/prod-003-split-market-adapters-data-providers-and-strategies-into): split market adapters, data providers, and strategies into stable interfaces.
- [CHA-1043](https://linear.app/chainbytes/issue/CHA-1043/prod-004-harden-persistence-with-migrations-configurable-storage-and): harden persistence with migrations, configurable storage, and audit trails.
- [CHA-1044](https://linear.app/chainbytes/issue/CHA-1044/prod-005-add-api-resilience-observability-and-operator-diagnostics): add API resilience, observability, and operator diagnostics.
- [CHA-1045](https://linear.app/chainbytes/issue/CHA-1045/doc-001-create-a-production-grade-readme-for-market-edge): create a production-grade README.

## Repository

- GitHub: [EricGrill/marketedge](https://github.com/EricGrill/marketedge)
- Local development path: `/Users/eric/code/marketedge`
- Primary branch: `main`

## What It Does Today

Market Edge currently includes:

- A Click-based CLI for dashboard, analysis, strategy, portfolio, weather, and formula commands.
- A static web dashboard that can load generated backtest summaries without requiring market accounts.
- A Textual TUI dashboard scaffold.
- A Kalshi REST/WebSocket client and weather market scanner.
- Weather data fetchers and model-blending support.
- A quant formula engine for opportunity screening and sizing.
- An offline backtesting engine for settled prediction-market trade ledgers.
- Offline settlement outcome loading for CSV/JSONL market-result datasets.
- SQLite-backed state for positions, forecasts, market snapshots, and portfolio state.
- Initial regression tests for formulas, state persistence, settlement loading, backtesting, and CLI behavior.

## Current Architecture

```text
marketedge/
├── src/
│   ├── cli.py              # Click CLI entry point
│   ├── backtesting.py      # Offline replay and backtest metrics
│   ├── config.py           # Environment-driven configuration
│   ├── formulas.py         # Quant engine and screening math
│   ├── settlements.py      # Offline settlement outcome resolver
│   ├── state.py            # SQLite state manager and SQLAlchemy models
│   ├── api/
│   │   └── client.py       # Kalshi REST/WebSocket client and market scanner
│   ├── strategies/
│   │   └── weather.py      # Weather strategy pipeline
│   ├── tui/
│   │   └── app.py          # Textual dashboard
│   └── weather/
│       └── data.py         # Weather data fetchers and model blend inputs
├── tests/
│   ├── conftest.py
│   ├── test_backtesting.py
│   ├── test_cli.py
│   ├── test_formulas.py
│   ├── test_settlements.py
│   └── test_state.py
├── web/
│   ├── app.js              # Static dashboard interactions
│   ├── data/
│   │   └── backtest-summary.json
│   ├── index.html
│   └── styles.css
├── .env.example
├── .gitignore
├── README.md
└── requirements.txt
```

The next architectural step is to separate market adapters, data providers, and
strategies behind stable interfaces so non-weather event markets can be added
without rewriting core risk or execution logic.

## Quickstart

Clone the private repository:

```bash
git clone https://github.com/EricGrill/marketedge.git
cd marketedge
```

Create a Python environment and install dependencies:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install flake8
```

Create local configuration:

```bash
cp .env.example .env
```

Edit `.env` with Kalshi credentials before using API-backed commands.
Keep `KALSHI_SANDBOX=true` unless you are intentionally working with a live
environment.

## Configuration

`.env.example` documents the current variables:

```env
KALSHI_API_KEY=your_api_key_here
KALSHI_API_SECRET=your_api_secret_here
KALSHI_SANDBOX=true
```

Optional URL overrides are also supported:

```env
KALSHI_BASE_URL=https://api.elections.kalshi.com
KALSHI_WS_URL=wss://api.elections.kalshi.com/ws/v2
```

Database state currently defaults to `data/kalshi_quant.db`. Configurable
database paths and schema migrations are tracked in
[CHA-1043](https://linear.app/chainbytes/issue/CHA-1043/prod-004-harden-persistence-with-migrations-configurable-storage-and).

## Common Commands

Open the web dashboard:

```bash
python -m http.server 4173 -d web
```

Then visit `http://localhost:4173`.

Analyze a specific market opportunity:

```bash
python -m src.cli analyze \
  --ticker RAIN-NYC-2026-05-15 \
  --model-prob 0.65 \
  --side yes
```

Run the strategy loop in dry-run mode:

```bash
python -m src.cli trade --dry --interval 300
```

Run an offline backtest from a CSV trade ledger:

```bash
python -m src.cli backtest path/to/trades.csv --bankroll 10000
```

Generate the dashboard data file from the same ledger:

```bash
python -m src.cli backtest path/to/trades.csv \
  --bankroll 10000 \
  --json-out web/data/backtest-summary.json
```

Required CSV columns: `timestamp`, `ticker`, `side`, `entry_price`, `exit_price`,
`quantity`, and `model_probability`. Optional columns include `confidence`,
`entry_fee`, and `exit_fee`. When `web/data/backtest-summary.json` exists, the
web dashboard loads it into the backtest panel; otherwise the dashboard keeps
its static no-account sample metrics.

Load local settlement outcomes for resolved markets:

```python
from src.backtesting import BacktestEngine, load_trades_csv
from src.settlements import SettlementResolver, load_settlements_csv

trades = load_trades_csv("path/to/trades.csv")
outcomes = load_settlements_csv("path/to/settlements.csv")
settled_trades = SettlementResolver(outcomes).settle_trades(trades)
summary = BacktestEngine().run(settled_trades, initial_bankroll=10000)
```

Settlement CSV/JSONL rows require `ticker`, `settled_at`, and `winning_side`.
`yes_settlement_price`, `settlement_value`, or `settlement_price` may be
provided explicitly; otherwise the resolver derives `100` for YES winners and
`0` for NO winners. Duplicate, missing, and internally inconsistent settlement
rows raise `SettlementValidationError`.

Launch the TUI dashboard:

```bash
python -m src.cli dashboard
```

View portfolio state:

```bash
python -m src.cli portfolio
```

View open positions:

```bash
python -m src.cli positions
```

Fetch weather data:

```bash
python -m src.cli weather \
  --lat 40.71 \
  --lon -74.01 \
  --event-type rain \
  --threshold 1.0
```

Display implemented formulas:

```bash
python -m src.cli formulas
```

## Verification

Run the local verification gate:

```bash
black --check src tests
flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503
pytest tests/ -q
```

Current local proof:

- Black passes for `src` and `tests`.
- flake8 passes for `src` and `tests`.
- pytest passes with formula, settlement, backtesting, CLI, and SQLite state coverage.

Remote CI is not yet restored. GitHub rejected the initial workflow push because
the current token lacked `workflow` scope. CI restoration is tracked in
[CHA-1040](https://linear.app/chainbytes/issue/CHA-1040/prod-001-restore-ci-and-release-verification-for-marketedge).

## Quant Engine

`src/formulas.py` currently implements:

- Fee-adjusted edge.
- Kelly sizing with fractional Kelly.
- Annualized yield screening.
- Liquidity-adjusted spread analysis.
- Bayesian probability updates.
- Weather model probability blending.
- Risk of ruin estimation.
- Correlation exposure estimation.
- Full opportunity screening.

These formulas are intended to remain market-agnostic as the project expands
beyond weather.

## Data Sources

The weather implementation is built around:

- Kalshi market data and orderbook access.
- NWS-style weather forecast inputs.
- Open-Meteo-style ensemble forecast inputs.
- Analog and microclimate adjustments.

Provider failure handling, retries, and operator diagnostics are not yet
production-grade. That work is tracked in
[CHA-1044](https://linear.app/chainbytes/issue/CHA-1044/prod-005-add-api-resilience-observability-and-operator-diagnostics).

## Safety And Risk Controls

The codebase includes risk concepts such as:

- Max position percentage.
- Max correlated exposure.
- Fractional Kelly sizing.
- Spread-based size reduction.
- Risk-of-ruin thresholding.
- Auto-close logic near expiration.

These are not enough for production live trading. Before live use, Market Edge
needs:

- Explicit live-trading enablement.
- A global kill switch.
- Pre-order risk limit enforcement.
- Daily loss and notional exposure limits.
- Structured audit logs for every signal, refusal, intent, and result.

That work is tracked in
[CHA-1041](https://linear.app/chainbytes/issue/CHA-1041/prod-002-add-explicit-live-trading-safety-gates-and-kill-switches).

## Development Workflow

Use a branch per Linear issue:

```bash
git checkout main
git pull
git checkout -b codex/cha-1045-production-readme
```

Before opening a PR:

```bash
black --check src tests
flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503
pytest tests/ -q
```

Expected PRs should include:

- The Linear issue identifier.
- A concise explanation of the change.
- Verification commands and results.
- Any known gaps or follow-up issues.

## Open-Source Readiness

This repository is currently private. Before making it public:

- Select and add a license.
- Add a security policy.
- Confirm no secrets or private operational details are committed.
- Restore CI.
- Make the README clear that live trading is not production-ready.
- Decide whether Linear links should remain in public documentation or move to a public roadmap.

No license has been selected yet. Do not assume open-source rights until a
license file is added.

## Security

Do not commit real API keys or trading credentials. Use `.env` for local secrets.

There is not yet a formal vulnerability disclosure policy. Add one before any
public release.

## Production Readiness

Market Edge should not be represented as production-ready until these are done:

1. [CHA-1040](https://linear.app/chainbytes/issue/CHA-1040/prod-001-restore-ci-and-release-verification-for-marketedge): CI and release verification.
2. [CHA-1041](https://linear.app/chainbytes/issue/CHA-1041/prod-002-add-explicit-live-trading-safety-gates-and-kill-switches): live-trading safety gates.
3. [CHA-1042](https://linear.app/chainbytes/issue/CHA-1042/prod-003-split-market-adapters-data-providers-and-strategies-into): extensible interfaces.
4. [CHA-1043](https://linear.app/chainbytes/issue/CHA-1043/prod-004-harden-persistence-with-migrations-configurable-storage-and): migrations and audit trails.
5. [CHA-1044](https://linear.app/chainbytes/issue/CHA-1044/prod-005-add-api-resilience-observability-and-operator-diagnostics): resilience and diagnostics.

Until then, treat the project as a local research and dry-run system.
