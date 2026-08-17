#!/usr/bin/env bash
# Keep the jira_qa RAG corpus fresh so newly created/updated tickets are searchable.
# The corpus was observed stale (last_sync days behind), which means recent
# escalations are invisible to search_jira_history. Run this on a schedule.
#
# Cron (daily 02:30, on the VM):
#   30 2 * * *  /root/aem-guides-dataset-studio/scripts/scheduled_reindex.sh >> /var/log/jira-qa-reindex.log 2>&1
#
# Or a systemd timer (preferred): a jira-qa-reindex.service (Type=oneshot running
# this script) + jira-qa-reindex.timer (OnCalendar=*-*-* 02:30:00).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
LIMIT="${REINDEX_LIMIT:-300}"

echo "[$(date -Is)] jira_qa incremental reindex starting (limit=$LIMIT)"
OVERALL_EXIT=0
if "$PYTHON_BIN" scripts/repair_jira_rag_on_vm.py --incremental --limit "$LIMIT"; then
  echo "[$(date -Is)] jira_qa incremental reindex succeeded; current status:"
else
  REINDEX_EXIT=$?
  OVERALL_EXIT="$REINDEX_EXIT"
  echo "[$(date -Is)] ERROR: jira_qa incremental reindex failed (exit_code=$REINDEX_EXIT); current status:" >&2
fi
"$PYTHON_BIN" scripts/repair_jira_rag_on_vm.py --check || true

set +e
PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/evidence_graph_admin.py enabled >/dev/null 2>&1
GRAPH_ENABLED_EXIT=$?
set -e
if [[ "$GRAPH_ENABLED_EXIT" -eq 0 ]]; then
  echo "[$(date -Is)] evidence graph incremental synchronization starting"
  if PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/evidence_graph_admin.py sync \
      --max-events "${EVIDENCE_GRAPH_SYNC_MAX_EVENTS:-500}" \
      --max-retries "${EVIDENCE_GRAPH_SYNC_MAX_RETRIES:-5}" \
      --batch-size "${EVIDENCE_GRAPH_BATCH_SIZE:-500}"; then
    echo "[$(date -Is)] evidence graph incremental synchronization succeeded"
  else
    GRAPH_EXIT=$?
    OVERALL_EXIT="$GRAPH_EXIT"
    echo "[$(date -Is)] ERROR: evidence graph synchronization failed (exit_code=$GRAPH_EXIT)" >&2
  fi
elif [[ "$GRAPH_ENABLED_EXIT" -ne 3 ]]; then
  OVERALL_EXIT="$GRAPH_ENABLED_EXIT"
  echo "[$(date -Is)] ERROR: could not determine evidence graph enablement (exit_code=$GRAPH_ENABLED_EXIT)" >&2
fi

if [[ "$OVERALL_EXIT" -eq 0 ]]; then
  echo "[$(date -Is)] scheduled reindex completed successfully"
else
  echo "[$(date -Is)] ERROR: scheduled reindex failed; success was not reported" >&2
fi
exit "$OVERALL_EXIT"
