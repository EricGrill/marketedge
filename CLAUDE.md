# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Market Edge is an experimental, research-first prediction-market quant research
and dry-run execution workbench. The current implementation starts with Kalshi
weather markets and local/offline workflows. Do not describe it as production
live-trading software.

## Primary Surfaces

- CLI: `python -m src.cli ...`
- Web dashboard: static files under `web/`, served with `python -m http.server 4173 -d web`
- TUI: `python -m src.cli dashboard`, implemented with Textual in `src/tui/app.py`
- Local state: SQLite through `src/state.py`, defaulting to `data/kalshi_quant.db`
  or `MARKETEDGE_DB_PATH` when set.

When the virtual environment is not activated, use `.venv/bin/python` and the
tooling in `.venv/bin/`. First-time setup: `pip install -e ".[dev]"` (Python
3.12+).

## Architecture

The system is a pipeline from data/inputs to a ranked, sized, audited decision.
Understanding it means reading a few files together:

- **`src/formulas.py` (`QuantEngine`) is the analytical core.** It is pure and
  stateless: `screen_opportunity(...)` composes edge (fee-adjusted vs. market),
  Kelly sizing, annualized yield (IY), liquidity spread (LAS), and risk-of-ruin
  into a single pass/fail screen, returning the dataclasses defined at the top of
  the file. `src/cli.py analyze` and the strategy both drive this same engine, so
  formula changes propagate everywhere. `src/cli.py formulas` prints the reference.
- **Two persistence layers, chosen by purpose.** Structured/queryable state
  (positions, portfolio, model outputs, schema-migration ledger, and the audit
  event log) lives in SQLite via `src/state.py` (`StateManager`, SQLAlchemy). All
  `StateManager` methods are `async` and callers wrap them in `asyncio.run(...)`.
  Append-only *event streams* — `src/orders.py` (order lifecycle), `src/paper.py`
  (no-account paper trades), `src/experiments.py` (run registry) — are JSONL files
  under `data/`, replayed to derive current state. Prefer the matching layer when
  adding features: relational/audited → SQLite; immutable event log → JSONL.
- **Datetimes are UTC-aware end to end.** Always mint time with
  `src/utils.py:utcnow()`, never `datetime.utcnow()`. `state.py`'s `UTCDateTime`
  column re-tags naive SQLite reads as UTC so comparisons against `utcnow()` are
  safe; breaking this invariant reintroduces subtle tz bugs.
- **Config is module-level dataclass singletons** in `src/config.py`
  (`kalshi_config`, `trading_config`, `weather_config`), populated from env at
  import. `KalshiConfig` forces the sandbox base URL unless `KALSHI_SANDBOX=false`.
  Weather model weights must sum to 1.0.
- **The weather strategy (`src/strategies/weather.py`) is the orchestrator.** It
  wires `WeatherModelEngine` (blends ECMWF/GEFS/analog/microclimate/NWS into a
  model probability), the `QuantEngine` screen, the Kalshi client
  (`src/api/client.py`), and the `OrderLedger`. `run_continuous(interval)` is the
  scan loop invoked by `cli trade`.
- **Live trading is one pure gate.** `src/safety.py:evaluate_live_trading_gate` is
  side-effect-free and returns the *first* unmet gate as an actionable reason; the
  CLI is the only place that reads the environment and translates a blocked
  decision into a non-zero exit. Test the gate directly, not through the CLI.
- **The web dashboard is fed, not live.** `cli dashboard-data` reads SQLite +
  JSONL ledgers and writes a static JSON payload under `web/data/`; the static
  `web/` app (`http.server`) renders it. There is no backend serving `web/`.

## Safety

- Keep default workflows dry-run, no-account, and local-first.
- Live trading fails closed in `src/safety.py`: it requires a disengaged kill
  switch, `MARKETEDGE_ALLOW_LIVE=true`, both Kalshi credentials, and
  `--confirm-live`. Do not weaken these gates.
- Do not add further live-trading behavior without risk checks, operator
  confirmation, and audit-trail integration.
- Do not commit `.env`, API credentials, local databases, JSONL ledgers, logs,
  or generated dashboard payloads. Before publishing, run
  `./scripts/pre_public_audit.sh` (see `docs/pre-public-checklist.md`).

## Common Commands

```bash
.venv/bin/python -m src.cli doctor
.venv/bin/python -m src.cli db init
.venv/bin/python -m src.cli db audit
.venv/bin/python -m src.cli dashboard-data
.venv/bin/python -m src.cli opportunities path/to/candidates.csv
.venv/bin/python -m src.cli experiments list
.venv/bin/python -m src.cli paper positions
```

## Verification

Run the local gate before claiming completion:

```bash
.venv/bin/python -m black --check src tests && .venv/bin/python -m flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503 && .venv/bin/python -m mypy src/ && .venv/bin/python -m pytest tests/ -q && node --check web/app.js
```

Run a single test or file during development:

```bash
.venv/bin/python -m pytest tests/test_formulas.py -q
.venv/bin/python -m pytest tests/test_safety.py::test_live_blocked_without_operator_confirmation -q
```

Known warning noise currently comes from existing `datetime.utcnow()` usage and
SQLAlchemy legacy APIs. Treat failures as blockers; warnings are not currently
fatal.
