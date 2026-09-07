#!/usr/bin/env bash
# Regenerate the dashboard payload and publish it to the nginx webroot on the VM.
#
# Usage (run as a FILE, not by pasting the body into a shell):
#   bash scripts/uac_eval/deploy_dashboard.sh
#
# The nginx server on the VM serves /eval-dashboard/ from $WEBROOT (default
# /var/www/aem-studio/eval-dashboard), which is a DIFFERENT directory than this
# git checkout - so `git pull` alone does not update the live page. This script
# rebuilds dashboard_data.json from the saved judge_pipeline*.json and
# gate_effect_report*.json runs, then copies the page + data into $WEBROOT.
#
# Override the webroot if nginx serves from elsewhere:
#   WEBROOT=/some/other/dir bash scripts/uac_eval/deploy_dashboard.sh
set -euo pipefail

# Resolve this script's own directory so it works from any CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

WEBROOT="${WEBROOT:-/var/www/aem-studio/eval-dashboard}"
PYTHON="${PYTHON:-python3}"

if [ ! -d "$WEBROOT" ]; then
  echo "ERROR: webroot '$WEBROOT' does not exist. Set WEBROOT=<nginx dir> and retry." >&2
  echo "Find it with: sudo nginx -T 2>/dev/null | grep -nE 'root |alias |eval-dashboard'" >&2
  exit 1
fi

"$PYTHON" aggregate_runs.py
cp dashboard.html dashboard_data.json "$WEBROOT"/

runs="$("$PYTHON" -c 'import json;print(len(json.load(open("dashboard_data.json"))["runs"]))')"
ge="$(grep -c '"reduction"' dashboard_data.json || true)"
echo "Deployed to $WEBROOT: ${runs} judge-pipeline run(s), ${ge} gate_effect entr(y/ies)."
echo "Verify: curl -s http://localhost:4502/eval-dashboard/dashboard_data.json | grep -c gate_effect  (expect 1)"
echo "Then hard-refresh the browser (Ctrl+F5) to bypass the cached HTML."
