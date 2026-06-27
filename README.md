<div align="center">

# 🌦️ Market Edge

### A local-first prediction-market quant workbench

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-3776ab.svg?style=flat-square)](https://python.org)
[![SQLite](https://img.shields.io/badge/storage-SQLite-003b57.svg?style=flat-square)](https://sqlite.org)
[![Status](https://img.shields.io/badge/status-experimental-orange.svg?style=flat-square)](#safety-first)

Rank model-vs-market mispricings. Run offline backtests. Track paper trades. Score forecast calibration. Operate with dry-run safety gates first.

[Quick Start](#quick-start) · [Features](#what-it-does) · [CLI](#cli) · [Dashboard](#web-dashboard) · [Safety](#safety-first) · [Contributing](CONTRIBUTING.md)

</div>

---

## What is this?

**Market Edge** is an experimental, research-first workbench for prediction-market quant analysis. It helps you:

- **Screen** event markets for edge, liquidity, risk, and confidence.
- **Size** positions with Kelly and fractional-Kelly logic.
- **Backtest** trade ledgers offline and emit dashboard-ready metrics.
- **Paper-trade** locally with an append-only JSONL ledger.
- **Calibrate** forecast probabilities against settled outcomes.
- **Blend** multi-source weather inputs into model probabilities.
- **Audit** every decision, intent, and result in local SQLite.

The current implementation focuses on **Kalshi weather markets**. The math, state, execution, and research primitives are written so the system can expand to other event-market categories later.

> **Status:** experimental and research-first. Live trading is gated behind multiple safety checks and is **off by default**. See [Safety First](#safety-first) before considering live use.

---

## ✨ What It Does

| Capability | What You Get |
|------------|--------------|
| **Opportunity Ranking** | Batch-score candidate markets by fee-adjusted edge, EV, spread, liquidity, confidence, and Kelly sizing. |
| **Offline Backtesting** | Replay CSV trade ledgers with execution realism, drawdown, Sharpe-like score, and net P&L. |
| **Paper Trading** | Record no-account buy/sell/selltle events locally before risking capital. |
| **Calibration Scoring** | Compare forecast probabilities to actual outcomes and surface over/under-confidence. |
| **Execution Modeling** | Simulate order-book fills, partial fills, slippage, and effective average price. |
| **Experiment Tracking** | Create, compare, and attach artifacts to research experiment runs. |
| **Local Dashboard** | Static web dashboard + Textual TUI, no API credentials required. |
| **Audit Trail** | SQLite-backed audit events for decisions, intents, refusals, and results. |

---

## 🚀 Quick Start

Clone the repo and set up a Python 3.12 environment:

```bash
git clone https://github.com/EricGrill/marketedge.git
cd marketedge
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt
```

No API key is needed for local workflows. To use API-backed commands, copy the config template:

```bash
cp .env.example .env
```

> Keep `KALSHI_SANDBOX=true` unless you are intentionally working against a live environment.

Initialize local state and run a readiness check:

```bash
python -m src.cli db init
python -m src.cli doctor
```

Launch the TUI dashboard:

```bash
python -m src.cli dashboard
```

Or start the static web dashboard:

```bash
python -m http.server 4173 -d web
# open http://localhost:4173
```

---

## 🖥️ CLI

The Click CLI is the main operator interface:

```bash
python -m src.cli --help
```

| Command | Purpose |
|---------|---------|
| `doctor` | Local setup and readiness checks. |
| `db` | Initialize SQLite, inspect migrations, view/append audit events. |
| `dashboard` | Launch the Textual TUI. |
| `dashboard-data` | Export dashboard-ready JSON from local state. |
| `analyze` | Inspect one ticker/model-probability opportunity. |
| `opportunities` | Rank offline candidates by edge, liquidity, risk, and confidence. |
| `trade` | Run the weather strategy loop (dry-run by default). |
| `positions` / `portfolio` | Inspect local SQLite state. |
| `backtest` | Replay a CSV trade ledger and optionally write dashboard JSON. |
| `experiments` | Create, list, show, compare, and attach artifacts to experiment records. |
| `paper` | Record local no-account paper orders, positions, and settlements. |
| `weather` | Fetch and blend weather forecast inputs. |
| `formulas` | Display implemented quant formula references. |

If the virtual environment is not activated, use `.venv/bin/python -m src.cli` instead of `python -m src.cli`.

---

## 🌐 Web Dashboard

The web dashboard is a static, no-account UI under `web/`. It runs without Kalshi credentials or a backend:

```bash
python -m http.server 4173 -d web
```

Then open `http://localhost:4173`.

The dashboard ships with built-in sample data and hydrates from local artifacts when present:

- `web/data/backtest-summary.json` — generated by `backtest --json-out`.
- `web/data/dashboard.json` — generated by `dashboard-data`.

`web/data/dashboard.json` can include market snapshots, portfolio state, open positions, paper-trading state, and backtest metrics. It is a generated local artifact and is ignored by git.

---

## 📊 TUI

Launch the Textual dashboard from the CLI:

```bash
python -m src.cli dashboard
```

It shows local portfolio state, open positions, recent signals, scanner controls, risk metrics, and settings. The scanner/settings controls are still a scaffold; the durable research workflows currently live in the CLI and local data files.

---

## 🏗️ Architecture

```text
marketedge/
├── CLAUDE.md              # Agent/project handoff guidance
├── README.md              # Operator and contributor documentation
├── requirements.txt       # Python dependencies
├── .env.example           # Local config template
├── src/
│   ├── cli.py             # Click CLI entry point
│   ├── dashboard.py       # Dashboard JSON payload builder
│   ├── doctor.py          # Local readiness checks
│   ├── opportunities.py   # Ranked opportunity scanner
│   ├── paper.py           # Append-only paper trading ledger
│   ├── backtesting.py     # Offline replay and backtest metrics
│   ├── calibration.py     # Forecast calibration scoring
│   ├── config.py          # Environment-driven configuration
│   ├── execution.py       # Fill/slippage/queue execution modeling
│   ├── experiments.py     # Local experiment registry and comparison
│   ├── formulas.py        # Quant engine and screening math
│   ├── orders.py          # Append-only order lifecycle ledger
│   ├── safety.py          # Live-trading safety gate (fails closed)
│   ├── settlements.py     # Offline settlement outcome resolver
│   ├── state.py           # SQLite state manager and SQLAlchemy models
│   ├── logging_config.py  # Central logging configuration
│   ├── utils.py           # Shared UTC datetime/timestamp helpers
│   ├── api/client.py      # Kalshi REST/WebSocket client and weather scanner
│   ├── strategies/weather.py
│   ├── tui/app.py         # Textual dashboard
│   └── weather/data.py    # Weather data fetchers and model blend inputs
├── tests/                 # Regression tests for CLI, state, math, ledgers, and artifacts
└── web/
    ├── index.html
    ├── app.js
    ├── styles.css
    └── data/backtest-summary.json
```

---

## 🔧 Core Workflows

### Initialize Local State

```bash
python -m src.cli db init --db-path data/kalshi_quant.db
python -m src.cli db migrations --db-path data/kalshi_quant.db
python -m src.cli db audit --db-path data/kalshi_quant.db
```

The default storage path is `MARKETEDGE_DB_PATH` when set, otherwise `data/kalshi_quant.db`. First-run initialization creates the SQLite schema, records the active schema version in `schema_migrations`, and ensures an empty portfolio row exists. The repository also includes an Alembic initial migration under `migrations/` for reproducible schema setup outside the app startup path.

Manual audit events can be appended for research or dry-run decisions:

```bash
python -m src.cli db audit-record \
  --event-type decision \
  --subject weather-screen \
  --ticker RAIN-NYC-TEST \
  --payload action=pass \
  --payload edge=0.12
```

### Check Local Readiness

```bash
python -m src.cli doctor
python -m src.cli doctor --strict
```

`doctor` checks Python/runtime modules, `.env`, Kalshi credential presence without printing secrets, sandbox mode, local SQLite storage, and dashboard artifact presence. `--strict` treats warnings as failures.

### Generate Dashboard Data

```bash
python -m src.cli dashboard-data \
  --out web/data/dashboard.json \
  --paper-ledger data/paper-ledger.jsonl \
  --backtest-summary web/data/backtest-summary.json
```

The web dashboard will use `web/data/dashboard.json` when present and fall back to built-in sample data when it is missing.

### Analyze One Market

```bash
python -m src.cli analyze \
  --ticker RAIN-NYC-2026-05-15 \
  --model-prob 0.65 \
  --side yes
```

The current `analyze` command uses placeholder bid/ask values. Use `opportunities` for batch offline ranking from explicit candidate data.

### Rank Opportunity Candidates

```bash
python -m src.cli opportunities path/to/candidates.csv \
  --bankroll 10000 \
  --json-out web/data/opportunities.json
```

Candidate CSV/JSON/JSONL rows require:

- `ticker`
- `model_probability`
- `yes_bid`
- `yes_ask`

Optional fields include `title`, `no_bid`, `no_ask`, `confidence`, `volume`, `open_interest`, and `resolution_date`.

Results include rank, YES/NO side, action, score, fee-adjusted edge, expected value, sizing hint, annualized yield, risk of ruin, confidence, and reason codes such as `EDGE_OK`, `SPREAD_TOO_WIDE`, and `LOW_CONFIDENCE`.

### Run An Offline Backtest

```bash
python -m src.cli backtest path/to/trades.csv --bankroll 10000

python -m src.cli backtest path/to/trades.csv \
  --bankroll 10000 \
  --json-out web/data/backtest-summary.json
```

Required trade CSV columns:

- `timestamp`
- `ticker`
- `side`
- `entry_price`
- `exit_price`
- `quantity`
- `model_probability`

Optional columns include `confidence`, `entry_fee`, and `exit_fee`.

### Load Settlements And Score Calibration

Settlement CSV/JSONL rows require `ticker`, `settled_at`, and `winning_side`.
`yes_settlement_price`, `settlement_value`, or `settlement_price` may be
provided explicitly; otherwise the resolver derives `100` for YES winners and
`0` for NO winners.

Forecast CSV/JSONL rows require `timestamp`, `ticker`, and `model_probability`.
Optional `strategy`, `market_category`, and `event_type` fields produce grouped
calibration summaries.

### Apply Execution Realism

```python
from src.execution import ExecutionModel, ExecutionOrder, OrderBookLevel, OrderBookSnapshot

book = OrderBookSnapshot(
    asks=[OrderBookLevel(price=40, quantity=100), OrderBookLevel(price=41, quantity=100)]
)
execution = ExecutionModel().fill(
    ExecutionOrder(action="buy", contract_side="yes", quantity=120),
    book,
)
executed_trade = ExecutionModel().apply_to_backtest_trade(trade, execution)
```

Execution metadata is carried into backtest trade results so summaries can show requested quantity, filled quantity, unfilled quantity, and effective average entry price.

### Track And Compare Experiments

```bash
python -m src.cli experiments create \
  --strategy wx-meanrev \
  --param edge=0.04 \
  --data-ref data/snapshots/wx.jsonl \
  --artifact web/data/backtest-summary.json \
  --model-version v1

python -m src.cli experiments list
python -m src.cli experiments show <run-id>
python -m src.cli experiments compare <run-id-a> <run-id-b>
python -m src.cli experiments add-artifact <run-id> path/to/artifact.json
```

Experiment records are append-only JSONL in `data/experiments.jsonl` by default.
Comparison loads referenced JSON artifacts when present and reports metric deltas such as return, net P&L, Sharpe-like score, drawdown, and average edge.

### Record Paper Trades

```bash
python -m src.cli paper order \
  --ticker HIGHNY-26JUN18-B88.5 \
  --side yes \
  --action buy \
  --quantity 10 \
  --price 40

python -m src.cli paper positions
python -m src.cli paper settle --ticker HIGHNY-26JUN18-B88.5 --winning-side yes
```

Paper ledger events are append-only JSONL in `data/paper-ledger.jsonl` by default. They are local dry-run records and do not call the Kalshi API.

### Fetch Weather Data

```bash
python -m src.cli weather \
  --lat 40.71 \
  --lon -74.01 \
  --event-type rain \
  --threshold 1.0
```

The weather implementation currently blends NWS-style, Open-Meteo-style, analog, microclimate, and NWS delta inputs.

---

## 🧮 Quant And Risk Features

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

The codebase also includes max position percentage, max correlated exposure, spread-based size reduction, and auto-close concepts. These are research/risk primitives, not sufficient production live-trading controls by themselves.

---

## 🛡️ Safety First

Before live use, Market Edge still needs durable production controls:

- Explicit live-trading enablement.
- Global kill switch.
- Pre-order risk limit enforcement.
- Daily loss and notional exposure limits.
- Strategy and execution integration that writes audit events for every signal, refusal, intent, and result.

Local readiness controls already include remote CI, operator diagnostics, configurable SQLite storage, Alembic schema initialization, an application schema ledger, and an audit event table with CLI inspection/append commands.

The live-trading path **fails closed by default**. Running `trade --live` requires the global kill switch disengaged, `MARKETEDGE_ALLOW_LIVE=true`, both Kalshi credentials present, and an explicit `--confirm-live` confirmation; any missing gate exits before a live client is created. Dry run is always the default.

Use local, no-account, analysis, backtest, and dry-run workflows. Do not treat this repository as production live-trading software until live-trading safety gates, kill switches, pre-order risk checks, audit-trail integrations, and operator confirmations are fully merged and verified.

Planned production-readiness and research enhancements are tracked publicly on the [GitHub issues](https://github.com/EricGrill/marketedge/issues) board.

---

## ⚙️ Configuration

`.env.example` documents supported local variables:

```env
KALSHI_API_KEY=your_api_key_here
KALSHI_API_SECRET=your_api_secret_here
KALSHI_SANDBOX=true

# Optional URL overrides
KALSHI_BASE_URL=https://api.elections.kalshi.com
KALSHI_WS_URL=wss://api.elections.kalshi.com/ws/v2

# Optional local SQLite path
MARKETEDGE_DB_PATH=data/kalshi_quant.db
```

Local generated state is intentionally not committed:

- `data/*.db`, `data/*.sqlite`, `data/*.sqlite3`
- `data/*.jsonl`
- `web/data/dashboard.json`
- `.env`, `.env.local`, `*.env`

---

## ✅ Verification

Run the local verification gate before claiming completion:

```bash
.venv/bin/python -m black --check src tests && .venv/bin/python -m flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503 && .venv/bin/python -m pytest tests/ -q && node --check web/app.js
```

Current local proof on this branch:

- Black passes for `src` and `tests`.
- flake8 passes for `src` and `tests`.
- pytest passes with CLI, dashboard, doctor, opportunities, paper ledger, formula, settlement, calibration, execution, experiment, backtesting, and SQLite state coverage.
- `node --check web/app.js` passes.

Known warning noise currently comes from existing `datetime.utcnow()` usage and SQLAlchemy legacy APIs. Warnings are not currently fatal.

---

## 🤝 Development Workflow

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contributor guide. In short, use a clearly named feature branch off `main`:

```bash
git checkout main
git pull
git checkout -b feature/short-description
```

Before opening a pull request, run the verification gate and include:

- A concise explanation of the change.
- Verification commands and results.
- Known gaps or follow-up work.

The pull request template includes a no-secrets / no-generated-data checklist — please complete it.

### Refresh And Audit Dependencies

Direct dependencies live in `requirements.txt`; `constraints.txt` pins the full resolved tree. To refresh after changing a dependency, recreate a clean environment, reinstall, run the gate, then regenerate the lock:

```bash
python -m pip freeze | grep -viE '^-e |marketedge' > constraints.txt
```

Audit installed dependencies for known vulnerabilities (also run weekly in CI):

```bash
uvx pip-audit --strict
```

---

## 📄 License

Market Edge is released under the [MIT License](LICENSE).

---

## 🔐 Security And Open-Source Readiness

Do not commit real API keys or trading credentials. Use `.env` for local secrets; it is git-ignored.

To report a vulnerability, follow the [security policy](SECURITY.md) and use a private channel — do not open a public issue.

Before publishing or re-publishing, run the [pre-public release checklist](docs/pre-public-checklist.md), which verifies that no secrets, databases, ledgers, `.omx/` state, or generated dashboard payloads are tracked or present in git history. A scripted version is available:

```bash
./scripts/pre_public_audit.sh
```

---

## Repository And Docs

- GitHub: [EricGrill/marketedge](https://github.com/EricGrill/marketedge)
- Primary branch: `main`
- License: [MIT](LICENSE)
- Security policy: [SECURITY.md](SECURITY.md)
- Contributor guide: [CONTRIBUTING.md](CONTRIBUTING.md)
- Agent handoff file: [CLAUDE.md](CLAUDE.md)
- Main user/operator documentation: [README.md](README.md)

`CLAUDE.md` contains short project guidance for Claude and other coding agents: the product safety posture, common commands, generated-file rules, and verification gate. Keep it aligned with this README when changing the app surface.
