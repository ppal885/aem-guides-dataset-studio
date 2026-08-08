#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --dry-run
PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --batch-size 500
PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --dry-run

sudo systemctl restart "$SERVICE_NAME"
sleep 5
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,16p'
