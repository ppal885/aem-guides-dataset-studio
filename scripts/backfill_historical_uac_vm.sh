#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="dry-run"
SOURCE_TYPE="jira_csv"
LIMIT="100000"
PAGE_SIZE="200"
CLOSED_ONLY="true"
REFRESH_LEARNING="true"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

usage() {
  cat <<'EOF'
Usage: bash scripts/backfill_historical_uac_vm.sh [options]

Options:
  --dry-run               Audit only; this is the default.
  --apply                 Upsert deterministic UAC chunks and refresh learning chunks.
  --source-type VALUE     Jira source type (default: jira_csv; empty means all).
  --limit NUMBER          Maximum UAC issues to analyze (default: 100000).
  --page-size NUMBER      SQL scan page size (default: 200).
  --all-statuses          Include unresolved/open Jira issues as candidate evidence.
  --no-learning-refresh   Do not rebuild historical learning chunks after apply.
  --service NAME          systemd service name.
  --public-url URL        Nginx public base URL.
  -h, --help              Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      MODE="dry-run"
      shift
      ;;
    --apply)
      MODE="apply"
      shift
      ;;
    --source-type)
      SOURCE_TYPE="${2:-}"
      shift 2
      ;;
    --limit)
      LIMIT="${2:-}"
      shift 2
      ;;
    --page-size)
      PAGE_SIZE="${2:-}"
      shift 2
      ;;
    --all-statuses)
      CLOSED_ONLY="false"
      shift
      ;;
    --no-learning-refresh)
      REFRESH_LEARNING="false"
      shift
      ;;
    --service)
      SERVICE_NAME="${2:-}"
      shift 2
      ;;
    --public-url)
      PUBLIC_URL="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "$LIMIT" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --limit must be a positive integer" >&2; exit 2; }
[[ "$PAGE_SIZE" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --page-size must be a positive integer" >&2; exit 2; }
[[ -x "$PYTHON_BIN" ]] || { echo "ERROR: Python executable not found: $PYTHON_BIN" >&2; exit 1; }

LOCK_FILE="${UAC_BACKFILL_LOCK_FILE:-/tmp/aem-guides-historical-uac-backfill.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: another historical UAC backfill is already running: $LOCK_FILE" >&2
  exit 1
fi

service_env_value() {
  local name="$1"
  local pid="$2"
  if [[ -n "$pid" && "$pid" != "0" && -r "/proc/$pid/environ" ]]; then
    tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n "s/^${name}=//p" | head -1
  fi
}

SERVICE_PID="$(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || true)"
SERVICE_CWD="$(readlink -f "/proc/${SERVICE_PID:-0}/cwd" 2>/dev/null || true)"
STORAGE_PATH_VALUE="$(service_env_value STORAGE_PATH "$SERVICE_PID")"
DATABASE_URL_VALUE="$(service_env_value DATABASE_URL "$SERVICE_PID")"
if [[ -z "$DATABASE_URL_VALUE" && -n "$SERVICE_CWD" ]]; then
  DATABASE_URL_VALUE="sqlite:///$SERVICE_CWD/storage/app.db"
fi

echo "mode=$MODE"
echo "service=$SERVICE_NAME"
echo "service_pid=${SERVICE_PID:-}"
echo "service_cwd=${SERVICE_CWD:-}"
echo "database_url=${DATABASE_URL_VALUE:+resolved}"
echo "storage_path=${STORAGE_PATH_VALUE:-<backend default>}"
echo "source_type=${SOURCE_TYPE:-<all>}"
echo "closed_only=$CLOSED_ONLY"
echo "limit=$LIMIT"
echo "page_size=$PAGE_SIZE"

env_args=(
  "PYTHONPATH=backend"
  "UAC_BACKFILL_MODE=$MODE"
  "UAC_SOURCE_TYPE=$SOURCE_TYPE"
  "UAC_LIMIT=$LIMIT"
  "UAC_PAGE_SIZE=$PAGE_SIZE"
  "UAC_CLOSED_ONLY=$CLOSED_ONLY"
  "UAC_REFRESH_LEARNING=$REFRESH_LEARNING"
)
if [[ -n "$STORAGE_PATH_VALUE" ]]; then
  env_args+=("STORAGE_PATH=$STORAGE_PATH_VALUE")
fi
if [[ -n "$DATABASE_URL_VALUE" ]]; then
  env_args+=("DATABASE_URL=$DATABASE_URL_VALUE")
fi

env "${env_args[@]}" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os

from app.db import jira_enrichment_models  # noqa: F401
from app.db.base import Base
from app.db.migrations import run_migrations
from app.db.session import engine
from app.services.jira_learning_chunk_service import backfill_jira_learning_chunks
from app.services.jira_uac_backfill_service import backfill_historical_uac_chunks
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count

mode = os.environ["UAC_BACKFILL_MODE"]
source_type = os.environ.get("UAC_SOURCE_TYPE", "").strip()
limit = int(os.environ["UAC_LIMIT"])
page_size = int(os.environ["UAC_PAGE_SIZE"])
closed_only = os.environ.get("UAC_CLOSED_ONLY", "true").lower() == "true"
refresh_learning = os.environ.get("UAC_REFRESH_LEARNING", "true").lower() == "true"

Base.metadata.create_all(bind=engine)
run_migrations()
print("database_schema=ready", flush=True)
print("jira_qa_before=" + str(get_collection_count(CHROMA_COLLECTION_JIRA_QA)), flush=True)
result = backfill_historical_uac_chunks(
    source_type=source_type,
    limit=limit,
    page_size=page_size,
    closed_only=closed_only,
    dry_run=mode != "apply",
)
print("historical_uac=" + json.dumps(result, ensure_ascii=False, indent=2), flush=True)
if not result.get("valid"):
    raise SystemExit("ERROR: historical UAC scan/backfill was partial or failed")
if mode == "apply" and refresh_learning:
    learning = backfill_jira_learning_chunks(source_type=source_type, limit=min(limit, 100000))
    print("learning_refresh=" + json.dumps(learning, ensure_ascii=False, indent=2), flush=True)
    if learning.get("error") or learning.get("failed_issues"):
        raise SystemExit("ERROR: historical learning refresh failed")
print("jira_qa_after=" + str(get_collection_count(CHROMA_COLLECTION_JIRA_QA)), flush=True)
PY

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete. Re-run with --apply after reviewing the audit."
  exit 0
fi

systemctl restart "$SERVICE_NAME"
for attempt in $(seq 1 24); do
  if curl -fsS -H "Authorization: Bearer dev-bypass" "$PUBLIC_URL/mcp" >/tmp/aem-guides-mcp-uac-check.json; then
    echo "Nginx MCP ready after restart."
    "$PYTHON_BIN" -m json.tool /tmp/aem-guides-mcp-uac-check.json
    rm -f /tmp/aem-guides-mcp-uac-check.json
    exit 0
  fi
  echo "Waiting for Nginx MCP: $attempt/24"
  sleep 5
done

echo "ERROR: Nginx MCP did not become ready after restart" >&2
systemctl status "$SERVICE_NAME" --no-pager -l || true
exit 1
