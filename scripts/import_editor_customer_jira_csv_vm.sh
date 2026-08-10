#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CSV_PATH="${1:-}"
MODE="${2:---apply}"
PROFILE="${3:-auto}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
MCP_URL="${MCP_URL:-http://10.42.46.78:4502/mcp}"
AUTH_TOKEN="${AUTH_TOKEN:-dev-bypass}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

if [[ -z "$CSV_PATH" || ! -f "$CSV_PATH" || "$MODE" != "--apply" && "$MODE" != "--dry-run" ]]; then
  echo "Usage: bash scripts/import_editor_customer_jira_csv_vm.sh /absolute/path/to/jira.csv [--dry-run|--apply] [auto|editor-new|native-pdf|customer-history]" >&2
  exit 2
fi
if [[ "$PROFILE" != "auto" && "$PROFILE" != "editor-new" && "$PROFILE" != "native-pdf" && "$PROFILE" != "customer-history" ]]; then
  echo "ERROR: unsupported import profile: $PROFILE" >&2
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
STORAGE_PATH_VALUE="${STORAGE_PATH_VALUE:-${STORAGE_PATH:-}}"
DATABASE_URL_VALUE="${DATABASE_URL_VALUE:-${DATABASE_URL:-}}"
if [[ -n "$STORAGE_PATH_VALUE" && "$STORAGE_PATH_VALUE" != /* && -n "$SERVICE_CWD" ]]; then
  STORAGE_PATH_VALUE="$SERVICE_CWD/$STORAGE_PATH_VALUE"
elif [[ -z "$STORAGE_PATH_VALUE" && -n "$SERVICE_CWD" ]]; then
  STORAGE_PATH_VALUE="$SERVICE_CWD/storage"
fi
if [[ -z "$DATABASE_URL_VALUE" && -n "$SERVICE_CWD" ]]; then
  DATABASE_URL_VALUE="sqlite:///$SERVICE_CWD/storage/app.db"
fi

echo "service=$SERVICE_NAME"
echo "service_pid=${SERVICE_PID:-}"
echo "service_cwd=${SERVICE_CWD:-}"
echo "csv=$(readlink -f "$CSV_PATH")"
echo "import_profile=$PROFILE"
echo "cohort_mode=Mixed (row-level cohorts)"
echo "mode=$MODE"

env_args=(
  "PYTHONPATH=$ROOT_DIR/backend"
  "EDITOR_CSV_PATH=$(readlink -f "$CSV_PATH")"
  "EDITOR_IMPORT_MODE=$MODE"
  "JIRA_IMPORT_PROFILE=$PROFILE"
)
if [[ -n "$STORAGE_PATH_VALUE" ]]; then
  env_args+=("STORAGE_PATH=$STORAGE_PATH_VALUE")
fi
if [[ -n "$DATABASE_URL_VALUE" ]]; then
  env_args+=("DATABASE_URL=$DATABASE_URL_VALUE")
fi
for name in EVIDENCE_GRAPH_ENABLED EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED; do
  value="$(service_env_value "$name" "$SERVICE_PID")"
  if [[ -n "$value" ]]; then
    env_args+=("$name=$value")
  fi
done

echo "==== component metadata schema v5 ===="
env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
  "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py \
  --dry-run --batch-size 500
if [[ "$MODE" == "--apply" ]]; then
  env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
    "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py \
    --apply --batch-size 500
  env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
    "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py \
    --dry-run --require-clean --batch-size 500
fi

env "${env_args[@]}" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

from app.db import jira_enrichment_models  # noqa: F401
from app.db.base import Base
from app.db.jira_enrichment_models import JiraEnrichedIssue
from app.db.migrations import run_migrations
from app.db.session import SessionLocal, engine
from app.services.jira_csv_import_service import (
    IMPORTER_VERSION,
    NATIVE_PDF_PROFILE_MIN_RATIO,
    classify_jira_import_profile,
    create_import_run,
    get_import_run,
    parse_jira_csv_bytes,
    preview_jira_csv_files,
    run_import,
)
from app.services.jira_enrichment_service import enrich_jira
from app.services.jira_learning_chunk_service import backfill_jira_learning_chunks
from app.services.jira_customer_profile_service import rebuild_customer_profiles
from app.services.vector_store_service import (
    CHROMA_COLLECTION_JIRA_QA,
    get_collection_count,
    get_documents_where,
)

MIXED = "Mixed (row-level cohorts)"
path = Path(os.environ["EDITOR_CSV_PATH"])
mode = os.environ["EDITOR_IMPORT_MODE"]
requested_profile = os.environ["JIRA_IMPORT_PROFILE"]
data = path.read_bytes()
parsed = parse_jira_csv_bytes(data, path.name)
assignment = {parsed.file_hash: MIXED}

components_by_key = {
    issue.issue_key: {
        str(component.get("name") or "")
        for component in issue.issue.get("fields", {}).get("components", [])
        if isinstance(component, dict) and str(component.get("name") or "")
    }
    for issue in parsed.issues
}
missing_editor = [
    issue.issue_key
    for issue in parsed.issues
    if "Editor" not in components_by_key[issue.issue_key]
]
missing_canonical_component = [
    issue.issue_key for issue in parsed.issues if not components_by_key[issue.issue_key]
]
missing_customer = [issue.issue_key for issue in parsed.issues if not issue.customer_cohorts]
enriched_by_key = {issue.issue_key: enrich_jira(issue.issue) for issue in parsed.issues}
new_editor_keys = [
    issue.issue_key
    for issue in parsed.issues
    if "new_editor" in enriched_by_key[issue.issue_key].affected_features
]
native_pdf_keys = [
    issue.issue_key
    for issue in parsed.issues
    if any(
        str(component).strip().casefold() in {"native pdf", "native-pdf", "native_pdf"}
        for component in issue.raw_components
    )
]
try:
    profile = classify_jira_import_profile(parsed, requested_profile)
except ValueError as exc:
    raise SystemExit(f"ERROR: {exc}") from exc

if missing_canonical_component:
    raise SystemExit(
        "ERROR: rows without a canonical component: " + ", ".join(missing_canonical_component)
    )
if profile == "editor-new":
    if missing_editor:
        raise SystemExit("ERROR: rows without canonical Editor component: " + ", ".join(missing_editor))
    if missing_customer:
        raise SystemExit("ERROR: rows without a deterministic customer cohort: " + ", ".join(missing_customer))
    if not new_editor_keys:
        raise SystemExit("ERROR: no explicit New Editor evidence was detected")
elif profile == "native-pdf":
    native_pdf_ratio = len(native_pdf_keys) / max(len(parsed.issues), 1)
    if native_pdf_ratio < NATIVE_PDF_PROFILE_MIN_RATIO:
        raise SystemExit(
            "ERROR: Native PDF evidence does not cover enough rows for the native-pdf profile: "
            f"{len(native_pdf_keys)}/{len(parsed.issues)}"
        )

if mode == "--dry-run":
    if parsed.rows_without_canonical_component or parsed.rows_with_noncanonical_component:
        raise SystemExit(
            "ERROR: component validation failed: "
            + json.dumps(
                {
                    "rows_without_canonical_component": parsed.rows_without_canonical_component,
                    "rows_with_noncanonical_component": parsed.rows_with_noncanonical_component,
                    "noncanonical_component_values": parsed.noncanonical_component_values,
                }
            )
        )
    print(
        "dry_run_verification="
        + json.dumps(
            {
                "valid": True,
                "importer_version": IMPORTER_VERSION,
                "profile": profile,
                "source_evidence_mode": parsed.source_evidence_mode,
                "jira_rows": len(parsed.issues),
                "editor_rows": len(parsed.issues) - len(missing_editor),
                "new_editor_rows": len(new_editor_keys),
                "native_pdf_rows": len(native_pdf_keys),
                "customer_associated_rows": len(parsed.issues) - len(missing_customer),
                "unattributed_customer_rows": len(missing_customer),
                "component_counts": parsed.component_counts,
                "ignored_component_values": parsed.ignored_component_values,
                "customer_profiles": sorted(
                    {customer for issue in parsed.issues for customer in issue.customer_cohorts},
                    key=str.casefold,
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    raise SystemExit(0)

Base.metadata.create_all(bind=engine)
run_migrations()
preview = preview_jira_csv_files([(path.name, data)], assignment)
print("preview=" + json.dumps(preview, ensure_ascii=False), flush=True)
if not preview.get("valid"):
    raise SystemExit("ERROR: preview validation failed: " + "; ".join(preview.get("validation_errors") or []))

before = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
print(f"jira_qa_before={before}", flush=True)
run_id, staged_paths = create_import_run(
    [(path.name, data)],
    created_by=f"vm-{profile}-customer-import",
    customer_assignments=assignment,
)
run_import(run_id, staged_paths)
result = get_import_run(run_id) or {}
print("import=" + json.dumps(result, ensure_ascii=False), flush=True)
if result.get("status") != "completed":
    raise SystemExit("ERROR: Jira CSV import did not complete successfully")

keys = [issue.issue_key for issue in parsed.issues]
learning = backfill_jira_learning_chunks(
    source_type="jira_csv",
    limit=max(1, len(keys)),
    jira_keys=keys,
)
print("learning=" + json.dumps(learning, ensure_ascii=False), flush=True)
if learning.get("error") or learning.get("failed_issues"):
    raise SystemExit("ERROR: Jira learned-behaviour backfill reported failures")

expected_customers = sorted(
    {customer for issue in parsed.issues for customer in issue.customer_cohorts},
    key=str.casefold,
)
db = SessionLocal()
try:
    rows = db.query(JiraEnrichedIssue).filter(JiraEnrichedIssue.jira_key.in_(keys)).all()
finally:
    db.close()
by_key = {row.jira_key: row for row in rows}
missing_sql = sorted(set(keys) - set(by_key))
if profile == "editor-new":
    wrong_component = sorted(
        key for key, row in by_key.items() if "Editor" not in set(row.components or [])
    )
else:
    wrong_component = sorted(
        key for key, row in by_key.items() if not set(row.components or [])
    )
expected_cohorts_by_key = {
    issue.issue_key: set(issue.customer_cohorts) for issue in parsed.issues
}
missing_sql_customer = sorted(
    key
    for key, expected in expected_cohorts_by_key.items()
    if expected and (key not in by_key or not expected.issubset(set(by_key[key].customer_cohorts or [])))
)
missing_feature = sorted(
    key
    for key in new_editor_keys
    if key not in by_key or "new_editor" not in set(by_key[key].affected_features or [])
) if profile == "editor-new" else []
missing_native_output = sorted(
    key
    for key in native_pdf_keys
    if key not in by_key or "Native PDF" not in set(by_key[key].affected_outputs or [])
) if profile == "native-pdf" else []
if missing_sql or wrong_component or missing_sql_customer or missing_feature or missing_native_output:
    raise SystemExit(
        "ERROR: SQL verification failed: "
        + json.dumps(
            {
                "missing_sql": missing_sql,
                "wrong_component": wrong_component,
                "missing_customer": missing_sql_customer,
                "missing_new_editor_feature": missing_feature,
                "missing_native_pdf_output": missing_native_output,
            }
        )
    )

missing_chroma = []
for key in keys:
    documents = get_documents_where(CHROMA_COLLECTION_JIRA_QA, {"jira_key": key}, limit=100)
    if profile == "editor-new":
        invalid = any(not row.get("metadata", {}).get("component_editor") for row in documents)
    else:
        invalid = any(
            not any(
                row.get("metadata", {}).get(field)
                for field in (
                    "component_editor",
                    "component_authoring",
                    "component_publishing",
                    "component_platform",
                    "component_schematron",
                    "component_integration",
                )
            )
            for row in documents
        )
    if not documents or invalid:
        missing_chroma.append(key)
if missing_chroma:
    raise SystemExit("ERROR: Chroma component membership verification failed: " + ", ".join(missing_chroma))

profile_rebuild = result.get("profile_rebuild", {})
profile_results = profile_rebuild.get("profiles", {})
if any(profile_results.get(customer, {}).get("status") != "completed" for customer in expected_customers):
    profile_rebuild = rebuild_customer_profiles(expected_customers)
    print("profile_rebuild=" + json.dumps(profile_rebuild, ensure_ascii=False), flush=True)
    profile_results = profile_rebuild.get("profiles", {})
missing_profiles = [
    customer
    for customer in expected_customers
    if profile_results.get(customer, {}).get("status") != "completed"
]
if missing_profiles:
    raise SystemExit("ERROR: customer profiles were not rebuilt: " + ", ".join(missing_profiles))

after = get_collection_count(CHROMA_COLLECTION_JIRA_QA)
print(
    "verification="
    + json.dumps(
        {
            "profile": profile,
            "source_evidence_mode": parsed.source_evidence_mode,
            "jira_rows": len(keys),
            "editor_rows": len(keys) - len(missing_editor),
            "new_editor_rows": len(new_editor_keys),
            "native_pdf_rows": len(native_pdf_keys),
            "customer_associated_rows": len(keys) - len(missing_customer),
            "unattributed_customer_rows": len(missing_customer),
            "component_counts": parsed.component_counts,
            "customer_profiles": expected_customers,
            "jira_qa_before": before,
            "jira_qa_after": after,
        },
        ensure_ascii=False,
    ),
    flush=True,
)
PY

if [[ "$MODE" == "--dry-run" ]]; then
  echo "Dry run passed; no SQL, Chroma, graph, or service state was changed."
  exit 0
fi

if PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/evidence_graph_admin.py enabled >/dev/null 2>&1; then
  PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/evidence_graph_admin.py sync --max-events 1000
else
  echo "evidence_graph_sync=skipped (disabled)"
fi

sudo systemctl restart "$SERVICE_NAME"

TMP_RESPONSE="$(mktemp)"
trap 'rm -f "$TMP_RESPONSE"' EXIT
for attempt in $(seq 1 24); do
  if curl -fsS \
    -H "Authorization: Bearer $AUTH_TOKEN" \
    -H "Content-Type: application/json" \
    --data '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
    "$MCP_URL" >"$TMP_RESPONSE"; then
    python3 - "$TMP_RESPONSE" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1], encoding="utf-8"))
tools = {item["name"] for item in payload.get("result", {}).get("tools", [])}
required = {"search_jira_history", "check_rag_status"}
missing = sorted(required - tools)
if missing:
    raise SystemExit(f"missing MCP tools: {missing}")
print("mcp_tools=ready")
PY
    echo "Customer Jira import completed."
    exit 0
  fi
  echo "Waiting for MCP through Nginx: $attempt/24"
  sleep 5
done

echo "ERROR: MCP did not become ready after restart: $MCP_URL" >&2
sudo systemctl status "$SERVICE_NAME" --no-pager -l || true
exit 1
