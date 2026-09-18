#!/usr/bin/env bash
# Thin wrapper — prefers the installed CLI, falls back to the project venv.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if command -v ouro-spe >/dev/null 2>&1; then
  exec ouro-spe setup "$@"
fi
if [[ -x "$ROOT/.venv/bin/ouro-spe" ]]; then
  exec "$ROOT/.venv/bin/ouro-spe" setup "$@"
fi
echo "ouro-spe not found. From the project root run:" >&2
echo "  python3 -m venv .venv && .venv/bin/pip install -e ." >&2
echo "  .venv/bin/ouro-spe setup" >&2
exit 1
