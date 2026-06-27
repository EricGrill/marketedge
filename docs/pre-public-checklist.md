# Pre-Public Release Checklist

Run this checklist before switching the repository from private to public, and
again any time the history or tracked files change materially. It exists so the
audit is repeatable without relying on chat history or memory.

A scripted version of the file/history/secret checks lives at
[`scripts/pre_public_audit.sh`](../scripts/pre_public_audit.sh):

```bash
./scripts/pre_public_audit.sh
```

It is read-only and exits non-zero if it finds a likely exposure.

## 1. Tracked files

- [ ] No `.env`, `.env.local`, or `*.env` files are tracked.
      `git ls-files | grep -iE '\.env'`
- [ ] No databases are tracked.
      `git ls-files | grep -iE '\.(db|sqlite|sqlite3)$'`
- [ ] No JSONL ledgers are tracked (paper ledger, order ledger, experiments).
      `git ls-files | grep -iE '\.jsonl$'`
- [ ] No `.omx/` state, logs, caches, or `.venv/` are tracked.
- [ ] No generated dashboard payload (`web/data/dashboard.json`) is tracked.

## 2. Untracked / ignored files

- [ ] `git status --porcelain` shows nothing you would not want made public.
- [ ] Ignored artifacts stay ignored — **never** `git add -f` a `.env`, database,
      JSONL ledger, `.omx/` file, cache, or generated dashboard payload.
      `git ls-files --others --exclude-standard` lists anything not yet ignored.

## 3. Secret scan

- [ ] No secret-like assignments in tracked content (API keys, tokens,
      passwords, private keys). The audit script runs a pattern scan; review any
      hits. Remember `.env.example` intentionally contains placeholder names.

## 4. Git history

- [ ] No sensitive file was ever committed and later deleted. A working-tree fix
      does **not** remove it from history.
      `git log --all --name-only --diff-filter=A | sort -u | grep -iE '\.env|\.(db|sqlite|jsonl)$|\.omx/|\.pem$|\.key$'`
- [ ] If a secret was ever committed, rotate it and rewrite history before going
      public; deletion in a later commit is not sufficient.

> Note: commit messages in this repository's history reference internal tracker
> IDs and local filesystem paths. These are not secrets, but they will be
> publicly visible. Decide whether that is acceptable or whether history should
> be rewritten before publishing.

## 5. Required public-release files

- [ ] [`LICENSE`](../LICENSE) present and named in the README.
- [ ] [`SECURITY.md`](../SECURITY.md) present with a private disclosure path.
- [ ] [`CONTRIBUTING.md`](../CONTRIBUTING.md) and a PR template present.
- [ ] README describes the project as experimental/research-first, with no
      "private repository" language or personal absolute paths.

## 6. Verification gate

- [ ] The full gate passes:

  ```bash
  .venv/bin/python -m black --check src tests \
    && .venv/bin/python -m flake8 src/ tests/ --max-line-length=120 --ignore=E501,W503 \
    && .venv/bin/python -m pytest tests/ -q \
    && node --check web/app.js
  ```

- [ ] `uvx pip-audit --strict` reports no known vulnerabilities.
- [ ] `uvx bandit -r src` reports no issues (only justified `# nosec` lines).

## 7. GitHub settings

Configured while still private:

- [x] Branch protection on `main` requiring the CI checks (`Python 3.10`,
      `Python 3.11`, `Python 3.12`), with force-pushes and deletions blocked.
- [x] Repository description and topics set; Wiki disabled.
- [x] Dependabot version/security updates enabled (`.github/dependabot.yml`).

Must be done immediately after flipping to public (these are free for public
repos but unavailable while the repo is private):

- [ ] Enable **secret scanning** and **push protection**
      (Settings → Code security, or
      `gh api -X PATCH repos/EricGrill/marketedge -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'`).

## 8. Flip to public

Only after every box above is checked:

```bash
gh repo edit EricGrill/marketedge --visibility public --accept-visibility-change-consequences
```

Then enable secret scanning/push protection (section 7) and confirm GitHub
detects the MIT license on the repository home page.
