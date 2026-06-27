# Contributing to Market Edge

Thanks for your interest in Market Edge. This is an **experimental,
research-first** prediction-market quant workbench. Default workflows are local,
no-account, and dry-run. Contributions that keep that posture intact are very
welcome.

By participating you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ground Rules

- **Keep defaults safe.** Do not weaken the dry-run, no-account, local-first
  defaults. Live-trading behavior must stay behind the explicit safety gates
  (kill switch, `MARKETEDGE_ALLOW_LIVE`, credentials, and `--confirm-live`).
- **Never commit secrets or local data.** No `.env`, API keys, trading
  credentials, local databases, JSONL ledgers, `.omx/` state, logs, or
  generated dashboard payloads. These are git-ignored — keep them that way.
- **Security issues go private.** See [SECURITY.md](SECURITY.md). Do not file a
  public issue for a vulnerability.

## Development Setup

```bash
git clone https://github.com/EricGrill/marketedge.git
cd marketedge

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt -c constraints.txt
```

Copy the example environment file when you need API-backed commands. Keep
`KALSHI_SANDBOX=true` unless you are intentionally working against a live
environment:

```bash
cp .env.example .env
```

## Verification Gate

Run the full gate before opening a pull request. CI runs the same checks on
Python 3.10, 3.11, and 3.12:

```bash
.venv/bin/python -m black --check src tests \
  && .venv/bin/python -m flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503 \
  && .venv/bin/python -m pytest tests/ -q \
  && node --check web/app.js
```

New behavior should ship with tests. Bug fixes should ship with a regression
test that fails before the fix.

## Branch and Pull Request Flow

1. Create a feature branch off `main`:

   ```bash
   git checkout main && git pull
   git checkout -b feature/short-description
   ```

2. Make focused commits with clear messages.
3. Run the verification gate.
4. Open a pull request against `main`. The
   [pull request template](.github/PULL_REQUEST_TEMPLATE.md) includes a
   no-secrets / no-generated-data checklist — please complete it.

## Reporting Bugs and Requesting Features

Use [GitHub Issues](https://github.com/EricGrill/marketedge/issues). Templates
are provided for bug reports and feature requests. Do not include secrets,
credentials, or private account data in an issue.

## License

By contributing, you agree that your contributions will be licensed under the
[MIT License](LICENSE) that covers this project.
