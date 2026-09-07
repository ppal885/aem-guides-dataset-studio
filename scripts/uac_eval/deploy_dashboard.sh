#!/usr/bin/env bash
# Publish the eval dashboard to the nginx webroot on the VM.
#
# Usage (run as a FILE, not by pasting the body into a shell):
#   bash scripts/uac_eval/deploy_dashboard.sh
#
# IMPORTANT: by default this copies the COMMITTED dashboard.html and
# dashboard_data.json into $WEBROOT. It does NOT re-aggregate, because the
# per-run source files (judge_pipeline_*.json, gate_effect_report*.json) are
# local artifacts that do not live in the git checkout - re-aggregating on a
# box that lacks them would rebuild dashboard_data.json from only the few
# committed sample runs and wipe the real data. The committed dashboard_data.json
# is the source of truth for deployment; regenerate it where the runs live
# (see --aggregate) and commit it, then deploy.
#
# Flags / env:
#   --aggregate         Rebuild dashboard_data.json from local run files FIRST
#                       (only on a machine that actually has the run JSONs).
#   WEBROOT=<dir>       nginx served dir (default /var/www/aem-studio/eval-dashboard).
#   PYTHON=<bin>        python interpreter for --aggregate (default python3).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

WEBROOT="${WEBROOT:-/var/www/aem-studio/eval-dashboard}"
PYTHON="${PYTHON:-python3}"
AGGREGATE=0
for arg in "$@"; do
  case "$arg" in
    --aggregate) AGGREGATE=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -d "$WEBROOT" ]; then
  echo "ERROR: webroot '$WEBROOT' does not exist. Set WEBROOT=<nginx dir> and retry." >&2
  echo "Find it with: sudo nginx -T 2>/dev/null | grep -nE 'root |alias |eval-dashboard'" >&2
  exit 1
fi

if [ "$AGGREGATE" = "1" ]; then
  echo "Re-aggregating dashboard_data.json from local run files..."
  "$PYTHON" aggregate_runs.py
fi

if [ ! -f dashboard_data.json ]; then
  echo "ERROR: dashboard_data.json not found in $SCRIPT_DIR." >&2
  exit 1
fi

cp dashboard.html dashboard_data.json "$WEBROOT"/

runs="$("$PYTHON" -c 'import json;print(len(json.load(open("dashboard_data.json"))["runs"]))' 2>/dev/null || echo '?')"
ge="$(grep -c '"reduction"' dashboard_data.json || true)"
echo "Published to $WEBROOT: ${runs} judge-pipeline run(s), ${ge} gate_effect entr(y/ies)."
echo "Verify: curl -s http://localhost:4502/eval-dashboard/dashboard_data.json | grep -c gate_effect  (expect >= 1)"
echo "Then hard-refresh the browser (Ctrl+F5) to bypass the cached HTML."
