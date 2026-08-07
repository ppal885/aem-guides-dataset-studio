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
"$PYTHON_BIN" scripts/repair_jira_rag_on_vm.py --incremental --limit "$LIMIT"
echo "[$(date -Is)] reindex done; current status:"
"$PYTHON_BIN" scripts/repair_jira_rag_on_vm.py --check || true
