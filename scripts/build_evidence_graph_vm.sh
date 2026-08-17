#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi
if [[ "${1:-}" != "--dry-run" && "${1:-}" != "--apply" ]]; then
  echo "Usage: bash scripts/build_evidence_graph_vm.sh --dry-run|--apply [--batch-size 500] [--sources jira,docs,dita]" >&2
  exit 2
fi

PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/evidence_graph_admin.py build "$@"
