#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
MODE="${1:---apply}"

if [[ "$MODE" != "--apply" && "$MODE" != "--dry-run" ]]; then
  echo "Usage: bash scripts/migrate_jira_component_metadata_vm.sh [--dry-run|--apply]" >&2
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

env_args=("PYTHONPATH=$ROOT_DIR/backend")
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

echo "service=$SERVICE_NAME"
echo "service_pid=${SERVICE_PID:-}"
echo "service_cwd=${SERVICE_CWD:-}"
echo "storage_path=${STORAGE_PATH_VALUE:-default-unverified}"
echo "mode=$MODE"

env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
  "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --dry-run --batch-size 500
if [[ "$MODE" == "--dry-run" ]]; then
  exit 0
fi

env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
  "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --apply --batch-size 500
env "${env_args[@]}" EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false \
  "$PYTHON_BIN" scripts/migrate_jira_component_metadata.py --dry-run --require-clean --batch-size 500

sudo systemctl restart "$SERVICE_NAME"
sleep 5
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,16p'
