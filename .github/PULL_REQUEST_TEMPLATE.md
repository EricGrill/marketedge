# Pull Request

## Summary

<!-- What does this change do, and why? -->

## Related issue

<!-- Link a GitHub issue if applicable, e.g. Closes #123 -->

## Verification

<!-- Paste the commands you ran and their results. -->

```text
.venv/bin/python -m black --check src tests
.venv/bin/python -m flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503
.venv/bin/python -m pytest tests/ -q
node --check web/app.js
```

## Safety & hygiene checklist

- [ ] No secrets, API keys, or trading credentials are included in the diff.
- [ ] No local data is included: `.env`, databases (`*.db`/`*.sqlite`), JSONL
      ledgers, `.omx/` state, logs, or generated dashboard payloads
      (`web/data/dashboard.json`).
- [ ] Default workflows remain dry-run, no-account, and local-first; any
      live-trading path stays behind the existing safety gates.
- [ ] New behavior is covered by tests (and bug fixes include a regression test).
- [ ] The verification gate passes locally.

## Notes / follow-ups

<!-- Known gaps, follow-up work, or anything reviewers should focus on. -->
