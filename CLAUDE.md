# CLAUDE.md

Project guidance for Claude and other coding agents working in this repository.

## Project

Market Edge is a private, experimental prediction-market quant research and
dry-run execution workbench. The current implementation starts with Kalshi
weather markets and local/offline workflows. Do not describe it as production
live-trading software.

## Primary Surfaces

- CLI: `python -m src.cli ...`
- Web dashboard: static files under `web/`, served with `python -m http.server 4173 -d web`
- TUI: `python -m src.cli dashboard`, implemented with Textual in `src/tui/app.py`
- Local state: SQLite through `src/state.py`, defaulting to `data/kalshi_quant.db`

When the virtual environment is not activated, use `.venv/bin/python` and the
tooling in `.venv/bin/`.

## Safety

- Keep default workflows dry-run, no-account, and local-first.
- Do not add live-trading behavior without explicit safety gates, risk checks,
  operator confirmation, and audit logging.
- Do not commit `.env`, API credentials, local databases, JSONL ledgers, logs,
  or generated dashboard payloads.

## Common Commands

```bash
.venv/bin/python -m src.cli doctor
.venv/bin/python -m src.cli dashboard-data
.venv/bin/python -m src.cli opportunities path/to/candidates.csv
.venv/bin/python -m src.cli experiments list
.venv/bin/python -m src.cli paper positions
```

## Verification

Run the local gate before claiming completion:

```bash
.venv/bin/black --check src tests
.venv/bin/flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503
.venv/bin/pytest tests/ -q
node --check web/app.js
```

Known warning noise currently comes from existing `datetime.utcnow()` usage and
SQLAlchemy legacy APIs. Treat failures as blockers; warnings are not currently
fatal.
