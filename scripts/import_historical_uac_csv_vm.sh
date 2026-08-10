#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CSV_PATH="${1:-}"
shift || true
MODE="dry-run"
OVERRIDES_PATH="$ROOT_DIR/backend/config/historical_uac_component_overrides_2026_08_09.json"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"

usage() {
  cat <<'EOF'
Usage: bash scripts/import_historical_uac_csv_vm.sh /absolute/path/to/jira.csv [options]

Options:
  --dry-run                 Normalize and audit only; this is the default.
  --apply                   Import Jira history and upsert deterministic UAC chunks.
  --overrides PATH          Component override manifest for ambiguous source rows.
  --service NAME            systemd service name.
  --public-url URL          Nginx public base URL.
  -h, --help                Show this help.
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
    --overrides)
      OVERRIDES_PATH="${2:-}"
      shift 2
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

if [[ -z "$CSV_PATH" || ! -f "$CSV_PATH" ]]; then
  usage >&2
  exit 2
fi
[[ -f "$OVERRIDES_PATH" ]] || { echo "ERROR: override manifest not found: $OVERRIDES_PATH" >&2; exit 1; }
[[ -x "$PYTHON_BIN" ]] || { echo "ERROR: Python executable not found: $PYTHON_BIN" >&2; exit 1; }

LOCK_FILE="${HISTORICAL_UAC_IMPORT_LOCK_FILE:-/tmp/aem-guides-historical-uac-import.lock}"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERROR: another historical UAC import is already running: $LOCK_FILE" >&2
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
echo "csv=$CSV_PATH"
echo "overrides=$OVERRIDES_PATH"

env_args=(
  "PYTHONPATH=backend"
  "HISTORICAL_UAC_CSV=$(readlink -f "$CSV_PATH")"
  "HISTORICAL_UAC_OVERRIDES=$(readlink -f "$OVERRIDES_PATH")"
  "HISTORICAL_UAC_MODE=$MODE"
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
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import distinct, func

from app.db import jira_enrichment_models  # noqa: F401
from app.db.base import Base
from app.db.jira_enrichment_models import JiraEnrichedIssue, JiraIssueChunk
from app.db.migrations import run_migrations
from app.db.session import SessionLocal, engine
from app.services.jira_csv_import_service import (
    MIXED_CUSTOMER_ASSIGNMENT,
    create_import_run,
    get_import_run,
    parse_jira_csv_bytes,
    preview_jira_csv_files,
    run_import,
)
from app.services.jira_historical_uac_import_service import (
    load_historical_uac_component_overrides,
    normalize_historical_uac_csv_bytes,
)
from app.services.jira_uac_analysis_service import (
    HISTORICAL_UAC_CHUNK_TYPES,
    analyze_historical_uac,
    extract_explicit_root_cause_evidence,
    extract_explicit_test_evidence,
    extract_release_scope_evidence,
    resolve_historical_uac_text,
)
from app.services.jira_uac_backfill_service import backfill_historical_uac_chunks
from app.services.vector_store_service import CHROMA_COLLECTION_JIRA_QA, get_collection_count


def source_uac_audit(parsed_file):
    counts = Counter()
    reuse_tiers = Counter()
    source_origins = Counter()
    for issue in parsed_file.issues:
        fields = issue.issue.get("fields") or {}
        comments = [comment.get("body_text", "") for comment in issue.comments]
        acceptance, source = resolve_historical_uac_text(
            acceptance_criteria=issue.acceptance_criteria,
            labels=fields.get("labels") or [],
            description=fields.get("description") or "",
            raw_text="",
            comment_documents=comments,
        )
        source_origins[source] += 1
        if not acceptance:
            counts["without_trusted_uac"] += 1
            continue
        root_cause, root_source = extract_explicit_root_cause_evidence(
            field_value=issue.root_cause,
            comment_documents=comments,
        )
        test_evidence, test_source = extract_explicit_test_evidence(
            field_value=issue.test_plan,
            comment_documents=comments,
        )
        release_scope, release_source = extract_release_scope_evidence(
            comment_documents=comments,
        )
        analysis = analyze_historical_uac(
            jira_key=issue.issue_key,
            acceptance_criteria=acceptance,
            status=str((fields.get("status") or {}).get("name") or ""),
            resolution=issue.resolution,
            labels=fields.get("labels") or [],
            root_cause=root_cause,
            test_evidence=test_evidence,
            root_cause_source=root_source,
            test_evidence_source=test_source,
            release_scope_evidence=release_scope,
            release_scope_source=release_source,
            acceptance_source=source,
        )
        if analysis is None:
            counts["without_trusted_uac"] += 1
            continue
        counts["with_trusted_uac"] += 1
        counts["contract_complete"] += int(analysis.contract_complete)
        counts["contract_incomplete"] += int(not analysis.contract_complete)
        counts["performance_matters"] += int(analysis.performance_matters)
        counts["performance_complete"] += int(analysis.performance_contract_complete)
        counts["closed_uac"] += int(analysis.issue_closed)
        counts["open_uac"] += int(not analysis.issue_closed)
        reuse_tiers[analysis.reuse_tier] += 1
    return {
        **dict(counts),
        "source_origins": dict(sorted(source_origins.items())),
        "reuse_tiers": dict(sorted(reuse_tiers.items())),
    }


def assert_expected_subset(label, actual, expected):
    mismatches = []
    for key, expected_value in expected.items():
        actual_value = actual.get(key)
        if isinstance(expected_value, dict):
            if not isinstance(actual_value, dict):
                mismatches.append(f"{key}: expected object, got {type(actual_value).__name__}")
                continue
            try:
                assert_expected_subset(f"{label}.{key}", actual_value, expected_value)
            except SystemExit as exc:
                mismatches.append(str(exc))
        elif actual_value != expected_value:
            mismatches.append(f"{key}: expected {expected_value!r}, got {actual_value!r}")
    if mismatches:
        raise SystemExit(f"ERROR: {label} drift: " + "; ".join(mismatches))


mode = os.environ["HISTORICAL_UAC_MODE"]
csv_path = Path(os.environ["HISTORICAL_UAC_CSV"])
override_path = Path(os.environ["HISTORICAL_UAC_OVERRIDES"])
manifest = json.loads(override_path.read_text(encoding="utf-8"))
source_data = csv_path.read_bytes()
source_hash = __import__("hashlib").sha256(source_data).hexdigest()
overrides = load_historical_uac_component_overrides(
    override_path,
    source_file_hash=source_hash,
)
normalized = normalize_historical_uac_csv_bytes(
    source_data,
    csv_path.name,
    component_overrides=overrides,
)
print("normalization=" + json.dumps(normalized.report, ensure_ascii=False, indent=2), flush=True)
if not normalized.report.get("valid"):
    raise SystemExit("ERROR: historical UAC normalization is incomplete")
assert_expected_subset(
    "normalization audit",
    normalized.report,
    manifest.get("expected_normalization") or {},
)

Base.metadata.create_all(bind=engine)
run_migrations()
print("database_schema=ready", flush=True)
parsed = parse_jira_csv_bytes(normalized.data, csv_path.name)
assignments = {parsed.file_hash: MIXED_CUSTOMER_ASSIGNMENT}
preview = preview_jira_csv_files(
    [(csv_path.name, normalized.data)],
    customer_assignments=assignments,
)
print("preview=" + json.dumps(preview, ensure_ascii=False, indent=2), flush=True)
if not preview.get("valid"):
    raise SystemExit("ERROR: normalized historical UAC import preview is invalid")
assert_expected_subset(
    "CSV preview audit",
    preview,
    manifest.get("expected_preview") or {},
)

source_audit = source_uac_audit(parsed)
print("source_uac_audit=" + json.dumps(source_audit, ensure_ascii=False, indent=2), flush=True)
assert_expected_subset(
    "historical UAC audit",
    source_audit,
    manifest.get("expected_uac_audit") or {},
)
if mode != "apply":
    raise SystemExit(0)

keys = [issue.issue_key for issue in parsed.issues]
parsed_by_key = {issue.issue_key: issue for issue in parsed.issues}
print("jira_qa_before=" + str(get_collection_count(CHROMA_COLLECTION_JIRA_QA)), flush=True)
run_id, paths = create_import_run(
    [(csv_path.name, normalized.data)],
    created_by="vm-historical-uac-import",
    customer_assignments=assignments,
)
run_import(run_id, paths)
result = get_import_run(run_id) or {}
print("import=" + json.dumps(result, ensure_ascii=False, indent=2), flush=True)
if result.get("status") != "completed":
    raise SystemExit("ERROR: historical UAC Jira import did not complete successfully")

uac_backfill = backfill_historical_uac_chunks(
    source_type="",
    limit=max(1000, len(keys) + 1),
    page_size=200,
    closed_only=False,
    dry_run=False,
    jira_keys=keys,
)
print("historical_uac=" + json.dumps(uac_backfill, ensure_ascii=False, indent=2), flush=True)
if not uac_backfill.get("valid"):
    raise SystemExit("ERROR: targeted historical UAC backfill was partial or failed")
if int(uac_backfill.get("issues_with_uac") or 0) < int(source_audit.get("with_trusted_uac") or 0):
    raise SystemExit("ERROR: fewer trusted UAC issues were indexed than the source audit found")

db = SessionLocal()
try:
    sql_issues = (
        db.query(JiraEnrichedIssue)
        .filter(JiraEnrichedIssue.jira_key.in_(keys))
        .all()
    )
    sql_issue_count = len(sql_issues)
    sql_uac_issue_count = (
        db.query(func.count(distinct(JiraIssueChunk.jira_key)))
        .filter(
            JiraIssueChunk.jira_key.in_(keys),
            JiraIssueChunk.chunk_type.in_(tuple(HISTORICAL_UAC_CHUNK_TYPES)),
        )
        .scalar()
        or 0
    )
finally:
    db.close()

customer_label_pollution = []
for row in sql_issues:
    parsed_issue = parsed_by_key[row.jira_key]
    trusted_tokens = {
        re.sub(r"[^a-z0-9]", "", value.casefold())
        for value in parsed_issue.customer_names + parsed_issue.customer_cohorts
    }
    label_tokens = {
        re.sub(r"[^a-z0-9]", "", str(label).casefold())
        for label in parsed_issue.issue.get("fields", {}).get("labels") or []
    }
    for customer in row.customer_names or []:
        token = re.sub(r"[^a-z0-9]", "", str(customer).casefold())
        if token in label_tokens and token not in trusted_tokens:
            customer_label_pollution.append(f"{row.jira_key}:{customer}")

verification = {
    "expected_issue_count": len(keys),
    "sql_issue_count": int(sql_issue_count),
    "source_trusted_uac_count": int(source_audit.get("with_trusted_uac") or 0),
    "sql_uac_issue_count": int(sql_uac_issue_count),
    "customer_label_pollution_count": len(customer_label_pollution),
    "customer_label_pollution_sample": customer_label_pollution[:20],
    "jira_qa_after": get_collection_count(CHROMA_COLLECTION_JIRA_QA),
}
print("verification=" + json.dumps(verification, ensure_ascii=False, indent=2), flush=True)
if int(sql_issue_count) != len(keys):
    raise SystemExit("ERROR: not every source Jira exists in SQL after import")
if int(sql_uac_issue_count) < int(source_audit.get("with_trusted_uac") or 0):
    raise SystemExit("ERROR: trusted UAC SQL chunk coverage is incomplete")
if customer_label_pollution:
    raise SystemExit("ERROR: generic Jira labels leaked into customer metadata")
PY

if [[ "$MODE" == "dry-run" ]]; then
  echo "Dry run complete. Re-run with --apply after reviewing the audit."
  exit 0
fi

systemctl restart "$SERVICE_NAME"
for attempt in $(seq 1 24); do
  if curl -fsS -H "Authorization: Bearer dev-bypass" "$PUBLIC_URL/mcp" >/tmp/aem-guides-mcp-historical-uac-check.json; then
    echo "Nginx MCP ready after restart."
    "$PYTHON_BIN" -m json.tool /tmp/aem-guides-mcp-historical-uac-check.json
    rm -f /tmp/aem-guides-mcp-historical-uac-check.json
    exit 0
  fi
  echo "Waiting for Nginx MCP: $attempt/24"
  sleep 5
done

echo "ERROR: Nginx MCP did not become ready after restart" >&2
systemctl status "$SERVICE_NAME" --no-pager -l || true
exit 1
