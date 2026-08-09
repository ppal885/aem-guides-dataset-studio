#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSV_PATH="${1:-}"
PROFILE="${2:-auto}"
MODE="${3:---apply}"

if [[ -z "$CSV_PATH" ]]; then
  echo "Usage: bash scripts/import_customer_jira_csv_vm.sh /absolute/path/to/jira.csv [auto|editor-new|native-pdf|customer-history] [--dry-run|--apply]" >&2
  exit 2
fi

exec bash "$ROOT_DIR/scripts/import_editor_customer_jira_csv_vm.sh" \
  "$CSV_PATH" "$MODE" "$PROFILE"
