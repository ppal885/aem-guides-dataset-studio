#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CSV_PATH="${1:-}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

if [[ -z "$CSV_PATH" || ! -f "$CSV_PATH" ]]; then
  echo "Usage: bash scripts/import_ey_jira_csv_vm.sh /absolute/path/to/jira.csv" >&2
  exit 2
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
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

echo "service=$SERVICE_NAME"
echo "service_pid=${SERVICE_PID:-}"
echo "service_cwd=${SERVICE_CWD:-}"
echo "storage_path=${STORAGE_PATH_VALUE:-<backend default>}"
echo "database_url=${DATABASE_URL_VALUE:+resolved}"
echo "csv=$CSV_PATH"

env_args=("PYTHONPATH=backend" "EY_CSV_PATH=$(readlink -f "$CSV_PATH")")
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
from pathlib import Path

from app.db.base import Base
from app.db.migrations import run_migrations
from app.db.session import engine
from app.db import jira_enrichment_models  # noqa: F401
from app.services.jira_csv_import_service import (
    create_import_run,
    get_import_run,
    parse_jira_csv_bytes,
    preview_jira_csv_files,
    run_import,
)
from app.services.jira_customer_profile_service import index_customer_jira_profile
from app.services.jira_learning_chunk_service import backfill_jira_learning_chunks
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count

path = Path(os.environ["EY_CSV_PATH"])
data = path.read_bytes()
parsed = parse_jira_csv_bytes(data, path.name)
non_ey = [
    issue.issue_key
    for issue in parsed.issues
    if "EY" not in {str(label).strip().upper() for label in issue.issue["fields"].get("labels", [])}
]
if non_ey:
    raise SystemExit("ERROR: CSV contains issues without the EY label: " + ", ".join(non_ey[:20]))

Base.metadata.create_all(bind=engine)
run_migrations()
print("database_schema=ready", flush=True)
preview = preview_jira_csv_files([(path.name, data)])
print("preview=" + json.dumps(preview, ensure_ascii=False), flush=True)
print("jira_qa_before=" + str(get_collection_count(CHROMA_COLLECTION_JIRA_QA)), flush=True)
run_id, paths = create_import_run([(path.name, data)], created_by="vm-ey-import")
run_import(run_id, paths)
result = get_import_run(run_id) or {}
print("import=" + json.dumps(result, ensure_ascii=False), flush=True)
if result.get("status") != "completed":
    raise SystemExit("ERROR: Jira CSV import did not complete successfully")

learning = backfill_jira_learning_chunks(source_type="jira_csv", limit=10_000)
print("learning=" + json.dumps(learning, ensure_ascii=False), flush=True)
if learning.get("error") or learning.get("failed_issues"):
    raise SystemExit("ERROR: Jira learned-behavior backfill reported failures")
profile = index_customer_jira_profile(
    customer="EY",
    source_file_hash=parsed.file_hash,
    required_label="EY",
)
print("customer_profile=" + json.dumps(profile, ensure_ascii=False), flush=True)
if not profile.get("indexed") or profile.get("chunks") != 4:
    raise SystemExit("ERROR: EY customer behavior profile was not indexed")
print("jira_qa_after=" + str(get_collection_count(CHROMA_COLLECTION_JIRA_QA)), flush=True)
PY

systemctl restart "$SERVICE_NAME"

for attempt in $(seq 1 24); do
  if curl -fsS "$BACKEND_URL/api/v1/ai/rag-status" >/dev/null; then
    echo "Backend ready after restart."
    curl -fsS "$BACKEND_URL/api/v1/ai/rag-status"
    echo
    curl -fsS "$PUBLIC_URL/api/v1/ai/rag-status"
    echo
    exit 0
  fi
  echo "Waiting for backend startup: $attempt/24"
  sleep 5
done

echo "ERROR: backend did not become ready after restart" >&2
systemctl status "$SERVICE_NAME" --no-pager -l || true
exit 1
