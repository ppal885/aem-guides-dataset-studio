#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
OUTPUT="${1:-$ROOT_DIR/tmp/jira-corpus-audit.json}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/audit_jira_corpus.py --output "$OUTPUT"
echo "audit_report=$OUTPUT"
