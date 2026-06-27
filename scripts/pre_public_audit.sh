#!/usr/bin/env bash
#
# Pre-public exposure audit for Market Edge.
#
# Runs the same checks used to decide whether the repository is safe to switch
# from private to public. It is read-only: it inspects tracked files, ignored
# files, git history, and scans for secret-like patterns and local artifacts.
# It never modifies the repository.
#
# Usage:  ./scripts/pre_public_audit.sh
# Exit code is non-zero if any check finds a likely exposure.

set -uo pipefail

cd "$(git rev-parse --show-toplevel)" || {
  echo "Not inside a git repository." >&2
  exit 2
}

status=0
section() { printf '\n=== %s ===\n' "$1"; }
fail() {
  status=1
  printf 'FAIL: %s\n' "$1"
}
ok() { printf 'OK:   %s\n' "$1"; }

# 1. Tracked files that must never be committed.
section "Tracked sensitive files"
tracked_bad=$(git ls-files | grep -ivE '(^|/)\.env\.example$' | grep -iE \
  '(^|/)\.env($|\.)|\.env\.local$|\.(db|sqlite|sqlite3)$|\.jsonl$|(^|/)\.omx/|\.pem$|\.key$|(^|/)data/.*\.(db|jsonl)$|web/data/dashboard\.json$' \
  || true)
if [ -n "$tracked_bad" ]; then
  fail "tracked files look like secrets or local artifacts:"
  printf '%s\n' "$tracked_bad"
else
  ok "no tracked .env / db / jsonl / .omx / key / generated-dashboard files"
fi

# 2. Untracked-but-not-ignored files (would be swept in by 'git add -A').
section "Untracked, non-ignored files"
untracked=$(git ls-files --others --exclude-standard)
if [ -n "$untracked" ]; then
  printf 'NOTE: untracked files present (review before committing):\n%s\n' "$untracked"
else
  ok "no untracked, non-ignored files"
fi

# 3. Secret-like patterns in tracked content.
section "Secret pattern scan (tracked content)"
secret_hits=$(git grep -nIaE \
  'AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----|xox[baprs]-[0-9A-Za-z-]+|gh[porus]_[0-9A-Za-z]{20,}|(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{12,}' \
  -- . ':(exclude).env.example' ':(exclude)scripts/pre_public_audit.sh' \
  ':(exclude)docs/pre-public-checklist.md' 2>/dev/null || true)
if [ -n "$secret_hits" ]; then
  fail "possible secrets in tracked content:"
  printf '%s\n' "$secret_hits"
else
  ok "no secret-like assignments in tracked content"
fi

# 4. Git history scan for ever-committed sensitive blobs.
section "Git history scan (all commits)"
history_bad=$(git log --all --pretty=format: --name-only --diff-filter=A \
  | sort -u | grep -ivE '(^|/)\.env\.example$' | grep -iE \
  '(^|/)\.env($|\.)|\.(db|sqlite|sqlite3)$|\.jsonl$|(^|/)\.omx/|\.pem$|\.key$' \
  || true)
if [ -n "$history_bad" ]; then
  fail "sensitive files appear in git history (a working-tree fix is not enough):"
  printf '%s\n' "$history_bad"
else
  ok "no .env / db / jsonl / .omx / key files in git history"
fi

# 5. Local artifacts that must be ignored and absent from tracking.
section "Local artifact tracking"
for pattern in 'data/.*\.db' 'data/.*\.jsonl' 'web/data/dashboard\.json' '\.omx/' '\.venv/'; do
  hit=$(git ls-files | grep -E "$pattern" || true)
  if [ -n "$hit" ]; then
    fail "artifact matching /$pattern/ is tracked:"
    printf '%s\n' "$hit"
  fi
done
[ "$status" -eq 0 ] && ok "no local databases, ledgers, caches, or venvs tracked"

# 6. Required public-release files are present.
section "Required public files"
for f in LICENSE SECURITY.md CONTRIBUTING.md README.md; do
  if [ -f "$f" ]; then ok "$f present"; else fail "$f missing"; fi
done

printf '\n'
if [ "$status" -eq 0 ]; then
  echo "RESULT: clean — no exposures detected by this audit."
else
  echo "RESULT: issues found — resolve the FAIL lines above before going public."
fi
exit "$status"
