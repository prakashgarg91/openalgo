#!/bin/bash
# SessionStart hook for Claude Code cloud sessions: installs what the tests and
# linters need. Synchronous on purpose, so nothing races the first command.
# Idempotent and non-interactive; does nothing outside a cloud session.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Python: the project is managed with uv. Sync explicitly (a bare `uv run` can sit
# on a first-time dependency download). --frozen installs exactly what uv.lock says
# and never rewrites it, so the working tree stays clean. This also installs the
# dev group (pytest, ruff).
if ! command -v uv >/dev/null 2>&1; then
  pip install --quiet uv
fi
uv sync --frozen

# Frontend: only needed for lint, typecheck and vitest. `npm ci` follows
# package-lock.json exactly and never edits it; skipped once node_modules exists,
# which is what the cached container state gives later sessions.
if [ -f frontend/package.json ] && [ ! -d frontend/node_modules ]; then
  (cd frontend && npm ci --no-audit --no-fund)
fi

# Let later commands use the project's tools without `uv run`.
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$PWD/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi
