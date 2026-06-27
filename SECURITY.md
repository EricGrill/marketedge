# Security Policy

Market Edge is **experimental, research-first software**. It is not production
live-trading software. Default workflows are local, no-account, and dry-run.
Please read this policy before reporting an issue or opening a pull request.

## Supported Versions

This project is pre-1.0 and moves on the `main` branch. Only the latest commit
on `main` is supported. Security fixes are applied there; there are no
backported release branches.

| Version            | Supported          |
| ------------------ | ------------------ |
| `main` (latest)    | :white_check_mark: |
| older commits/tags | :x:                |

## Reporting a Vulnerability

Please report security issues **privately** — do not open a public issue for a
vulnerability.

1. **Preferred:** use GitHub's private vulnerability reporting on this
   repository (the **Security** tab → **Report a vulnerability**). This opens a
   private advisory visible only to maintainers.
2. **Fallback:** email **hitsnorth@gmail.com** with the details.

Please include:

- A description of the issue and its impact.
- Steps to reproduce, or a minimal proof of concept.
- Affected files, commands, or configuration.

We aim to acknowledge a report within **7 days** and to provide a remediation
plan or status update within **30 days**. Timelines are best-effort for a
research project.

## Do Not Include Secrets or Account Data

When reporting an issue, opening a pull request, or attaching logs:

- **Never** include real API keys, trading credentials, or session tokens.
  Keep secrets in a local `.env` file, which is git-ignored.
- **Never** include funded-account data, private order history, or private
  market data.
- **Never** attach local databases, JSONL ledgers, `.omx/` state, or generated
  dashboard payloads — these are local artifacts and are git-ignored for a
  reason.

If you believe you have accidentally committed or transmitted a secret, rotate
it immediately and notify us through one of the private channels above.

## Scope

In scope:

- The Python package under `src/`, the CLI, and the static web dashboard under
  `web/`.
- Handling of credentials, local state, and the live-trading safety gates.

Out of scope:

- Vulnerabilities in third-party dependencies (report those upstream; we track
  them via the dependency audit workflow).
- Any use of the software for real live trading, which is explicitly not
  supported and gated behind multiple opt-in controls.
