#!/usr/bin/env bash
# Start the UAC backend and static evaluation dashboard on a Linux VM without Docker.
# Usage:
#   bash start-vm-dev.sh
#   bash start-vm-dev.sh --backend-port 8001 --dashboard-port 8765
#   bash start-vm-dev.sh --host 0.0.0.0  # explicitly share dev ports on the LAN
#   bash start-vm-dev.sh --kill-ports
#   bash start-vm-dev.sh --stop

set -Eeuo pipefail

# Development defaults avoid the production Nginx listener on 4502.
BACKEND_PORT="8010"
DASHBOARD_PORT="8765"
HOST="127.0.0.1"
STOP_ONLY="false"
SKIP_INSTALL="false"
KILL_PORTS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      BACKEND_PORT="${2:-}"
      shift 2
      ;;
    --dashboard-port)
      DASHBOARD_PORT="${2:-}"
      shift 2
      ;;
    --host)
      HOST="${2:-}"
      shift 2
      ;;
    --stop)
      STOP_ONLY="true"
      shift
      ;;
    --skip-install)
      SKIP_INSTALL="true"
      shift
      ;;
    --kill-ports)
      KILL_PORTS="true"
      shift
      ;;
    -h|--help)
      sed -n '1,45p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
DASHBOARD_SOURCE_DIR="$ROOT_DIR/scripts/uac_eval"
DASHBOARD_SNAPSHOT="$DASHBOARD_SOURCE_DIR/dashboard_data.json"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.run-local"
DASHBOARD_SITE_PATH_FILE="$PID_DIR/dashboard-site.path"
TEMP_ROOT="${TMPDIR:-/tmp}"
BACKEND_LOG="$LOG_DIR/backend-vm-dev.log"
DASHBOARD_LOG="$LOG_DIR/dashboard-vm-dev.log"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
DASHBOARD_PID_FILE="$PID_DIR/dashboard.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

if [[ ! -d "$TEMP_ROOT" ]]; then
  echo "Temporary directory does not exist: $TEMP_ROOT" >&2
  exit 1
fi
TEMP_ROOT="$(cd "$TEMP_ROOT" && pwd -P)"

info() { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
ok() { printf '\033[0;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; }

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

python_is_supported() {
  local candidate="$1"
  "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    >/dev/null 2>&1
}

select_supported_python() {
  local candidate
  for candidate in "$@"; do
    if [[ "$candidate" == */* ]]; then
      [[ -x "$candidate" ]] || continue
    elif ! command_exists "$candidate"; then
      continue
    fi
    if python_is_supported "$candidate"; then
      command -v "$candidate"
      return 0
    fi
  done
  return 1
}

validate_port() {
  local value="$1"
  local label="$2"
  if [[ ! "$value" =~ ^[0-9]+$ ]] || (( value < 1 || value > 65535 )); then
    fail "$label must be an integer from 1 through 65535: $value"
    exit 1
  fi
}

validate_host() {
  if [[ -z "$HOST" || ! "$HOST" =~ ^[A-Za-z0-9:._-]+$ ]]; then
    fail "Invalid bind host: $HOST"
    exit 1
  fi
}

port_pids() {
  local port="$1"
  if command_exists lsof; then
    lsof -ti TCP:"$port" 2>/dev/null || true
  elif command_exists fuser; then
    fuser "$port"/tcp 2>/dev/null || true
  fi
}

wait_for_port_free() {
  local port="$1"
  local attempts="${2:-10}"
  for _ in $(seq 1 "$attempts"); do
    if [[ -z "$(port_pids "$port")" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

stop_pid_file() {
  local file="$1"
  local label="$2"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      info "Stopping $label (pid $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f -- "$file"
  fi
}

safe_dashboard_site() {
  local candidate="$1"
  [[ -n "$candidate" \
    && "$candidate" == "$TEMP_ROOT"/aem-guides-dashboard-site-* \
    && -d "$candidate" \
    && ! -L "$candidate" ]]
}

cleanup_dashboard_site() {
  local site=""
  if [[ -f "$DASHBOARD_SITE_PATH_FILE" ]]; then
    site="$(cat "$DASHBOARD_SITE_PATH_FILE" 2>/dev/null || true)"
  fi
  if [[ -n "$site" ]]; then
    if safe_dashboard_site "$site"; then
      rm -rf -- "$site"
    else
      warn "Refusing to remove untrusted dashboard staging path: $site"
    fi
  fi
  rm -f -- "$DASHBOARD_SITE_PATH_FILE"
}

cleanup_failed_start() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then
    cleanup_dashboard_site
  fi
  exit "$status"
}

trap cleanup_failed_start EXIT

stop_services() {
  stop_pid_file "$DASHBOARD_PID_FILE" "dashboard"
  stop_pid_file "$BACKEND_PID_FILE" "backend"
  cleanup_dashboard_site

  for port in "$DASHBOARD_PORT" "$BACKEND_PORT"; do
    local pids
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
      if [[ "$KILL_PORTS" == "true" ]]; then
        warn "Killing process(es) on port $port: $pids"
        # port_pids returns numeric process IDs only.
        kill $pids 2>/dev/null || true
        sleep 2
        kill -9 $pids 2>/dev/null || true
        if ! wait_for_port_free "$port" 8; then
          fail "Port $port is still busy after kill attempt: $(port_pids "$port")"
          exit 1
        fi
      else
        warn "Port $port is still used by: $pids"
        warn "If these are old app processes, rerun with --kill-ports."
      fi
    fi
  done
}

validate_port "$BACKEND_PORT" "Backend port"
validate_port "$DASHBOARD_PORT" "Dashboard port"
validate_host

if [[ "$STOP_ONLY" == "true" ]]; then
  stop_services
  ok "Stop requested."
  exit 0
fi

[[ -d "$BACKEND_DIR" ]] || { fail "Backend directory not found: $BACKEND_DIR"; exit 1; }
[[ -f "$DASHBOARD_SOURCE_DIR/dashboard.html" ]] || { fail "Dashboard HTML not found"; exit 1; }
[[ -f "$DASHBOARD_SOURCE_DIR/aggregate_runs.py" ]] || { fail "Dashboard aggregator not found"; exit 1; }

if ! command_exists curl; then
  fail "curl not found. Install curl before running this script."
  exit 1
fi

BACKEND_PYTHON="$(select_supported_python \
  "$BACKEND_DIR/.venv/bin/python" \
  "$BACKEND_DIR/venv/bin/python" \
  "$BACKEND_DIR/.venv312/bin/python" || true)"
CREATED_VENV="false"

if [[ -z "$BACKEND_PYTHON" ]]; then
  BASE_PYTHON="$(select_supported_python \
    python3.11 python3.12 python3.13 python3.14 python3 python || true)"
  if [[ -z "$BASE_PYTHON" ]]; then
    fail "Python 3.11 or newer was not found. Install Python 3.11+ with venv and pip support first."
    exit 1
  fi

  VENV_DIR=""
  for candidate_dir in "$BACKEND_DIR/.venv" "$BACKEND_DIR/venv" "$BACKEND_DIR/.venv312"; do
    if [[ ! -e "$candidate_dir" ]]; then
      VENV_DIR="$candidate_dir"
      break
    fi
  done
  if [[ -z "$VENV_DIR" ]]; then
    fail "Existing backend virtual environments are incompatible with Python 3.11+."
    echo "Move or remove one incompatible environment after reviewing it, then rerun."
    exit 1
  fi

  info "Creating a Python 3.11+ backend virtual environment at $VENV_DIR"
  if ! "$BASE_PYTHON" -m venv "$VENV_DIR"; then
    PYTHON_VERSION="$("$BASE_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3.11)"
    fail "Could not create the backend virtual environment."
    echo "Install python${PYTHON_VERSION}-venv and python3-pip, then rerun."
    exit 1
  fi
  BACKEND_PYTHON="$VENV_DIR/bin/python"
  CREATED_VENV="true"
fi

if ! python_is_supported "$BACKEND_PYTHON"; then
  fail "Selected backend Python is older than 3.11: $BACKEND_PYTHON"
  exit 1
fi
info "Using backend Python: $BACKEND_PYTHON"

stop_services

for port in "$BACKEND_PORT" "$DASHBOARD_PORT"; do
  if [[ -n "$(port_pids "$port")" ]]; then
    fail "Port $port is still busy: $(port_pids "$port")"
    echo "Rerun with: bash start-vm-dev.sh --kill-ports"
    exit 1
  fi
done

if [[ "$SKIP_INSTALL" != "true" || "$CREATED_VENV" == "true" ]]; then
  if [[ "$SKIP_INSTALL" == "true" && "$CREATED_VENV" == "true" ]]; then
    warn "A new virtual environment needs dependencies; ignoring --skip-install for this first run."
  fi
  info "Installing backend dependencies"
  "$BACKEND_PYTHON" -m pip install --upgrade pip
  "$BACKEND_PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt"
fi

info "Aggregating dashboard data"
DASHBOARD_SITE_DIR="$(mktemp -d "$TEMP_ROOT/aem-guides-dashboard-site-XXXXXXXX")"
if ! safe_dashboard_site "$DASHBOARD_SITE_DIR"; then
  fail "Dashboard staging directory failed safety validation: $DASHBOARD_SITE_DIR"
  exit 1
fi
printf '%s\n' "$DASHBOARD_SITE_DIR" > "$DASHBOARD_SITE_PATH_FILE"
cp -p -- "$DASHBOARD_SOURCE_DIR/aggregate_runs.py" "$DASHBOARD_SITE_DIR/aggregate_runs.py"
cp -p -- "$DASHBOARD_SOURCE_DIR/dashboard.html" "$DASHBOARD_SITE_DIR/index.html"
shopt -s nullglob
DASHBOARD_RUN_INPUTS=("$DASHBOARD_SOURCE_DIR"/judge_pipeline*.json)
shopt -u nullglob
for source in "${DASHBOARD_RUN_INPUTS[@]}"; do
  [[ -f "$source" && ! -L "$source" ]] || continue
  cp -p -- "$source" "$DASHBOARD_SITE_DIR/${source##*/}"
done
"$BACKEND_PYTHON" "$DASHBOARD_SITE_DIR/aggregate_runs.py"
[[ -f "$DASHBOARD_SITE_DIR/dashboard_data.json" ]] || { fail "Dashboard data was not generated"; exit 1; }
"$BACKEND_PYTHON" - "$DASHBOARD_SITE_DIR/dashboard_data.json" "$DASHBOARD_SNAPSHOT" <<'PY'
import json
import shutil
import sys
from pathlib import Path

generated_path = Path(sys.argv[1])
snapshot_path = Path(sys.argv[2])

def run_ids(path: Path, label: str) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    runs = payload.get("runs")
    if not isinstance(runs, list):
        raise SystemExit(f"{label} dashboard data must contain a runs list")
    values = []
    for row in runs:
        if not isinstance(row, dict) or not isinstance(row.get("run_id"), str):
            raise SystemExit(f"{label} dashboard data has an invalid run_id")
        values.append(row["run_id"])
    if len(values) != len(set(values)):
        raise SystemExit(f"{label} dashboard data contains duplicate run IDs")
    return set(values)

generated_ids = run_ids(generated_path, "Generated")
if snapshot_path.is_file():
    snapshot_ids = run_ids(snapshot_path, "Checked-in")
    if generated_ids < snapshot_ids:
        print(
            "WARNING: eligible run inputs are a strict subset of checked-in dashboard "
            f"history; retaining {len(snapshot_ids)} runs instead of {len(generated_ids)}.",
            file=sys.stderr,
        )
        shutil.copy2(snapshot_path, generated_path)
    else:
        missing_ids = snapshot_ids - generated_ids
        if missing_ids:
            raise SystemExit(
                "isolated aggregation would drop checked-in dashboard history while "
                f"changing the run set; missing IDs: {sorted(missing_ids)}"
            )
PY
rm -f -- "$DASHBOARD_SITE_DIR/aggregate_runs.py"
for source in "${DASHBOARD_RUN_INPUTS[@]}"; do
  rm -f -- "$DASHBOARD_SITE_DIR/${source##*/}"
done
if [[ "$(find "$DASHBOARD_SITE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" != $'dashboard_data.json\nindex.html' ]]; then
  fail "Dashboard staging directory contains unexpected files"
  exit 1
fi
chmod 0644 "$DASHBOARD_SITE_DIR/index.html" "$DASHBOARD_SITE_DIR/dashboard_data.json"

info "Starting backend on http://127.0.0.1:${BACKEND_PORT}"
(
  cd "$BACKEND_DIR"
  export PYTHONUNBUFFERED=1
  nohup "$BACKEND_PYTHON" -m uvicorn app.main:app --host "$HOST" --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
  echo $! > "$BACKEND_PID_FILE"
)

info "Waiting for backend health"
BACKEND_OK="false"
for _ in $(seq 1 45); do
  if curl -fsS "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then
    BACKEND_OK="true"
    break
  fi
  sleep 1
done

if [[ "$BACKEND_OK" != "true" ]]; then
  fail "Backend did not become healthy."
  tail -80 "$BACKEND_LOG" || true
  exit 1
fi
ok "Backend is healthy"

info "Starting static dashboard on http://${HOST}:${DASHBOARD_PORT}"
nohup "$BACKEND_PYTHON" -m http.server "$DASHBOARD_PORT" --bind "$HOST" --directory "$DASHBOARD_SITE_DIR" > "$DASHBOARD_LOG" 2>&1 &
echo $! > "$DASHBOARD_PID_FILE"

DASHBOARD_OK="false"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${DASHBOARD_PORT}/" | grep -q "UAC Eval Observability"; then
    DASHBOARD_OK="true"
    break
  fi
  sleep 1
done

if [[ "$DASHBOARD_OK" != "true" ]]; then
  fail "Dashboard did not become reachable."
  tail -80 "$DASHBOARD_LOG" || true
  exit 1
fi

if [[ "$HOST" == "0.0.0.0" || "$HOST" == "::" ]]; then
  ACCESS_HOST="$(hostname -I 2>/dev/null | awk '{print $1}')"
else
  ACCESS_HOST="$HOST"
fi
ok "Dashboard is reachable"
echo ""
echo "AEM Guides UAC development services are running:"
echo "  Dashboard: http://${ACCESS_HOST:-localhost}:${DASHBOARD_PORT}/"
echo "  Backend  : http://${ACCESS_HOST:-localhost}:${BACKEND_PORT}/health"
echo "  API docs : http://${ACCESS_HOST:-localhost}:${BACKEND_PORT}/docs"
echo ""
echo "Logs:"
echo "  Backend  : $BACKEND_LOG"
echo "  Dashboard: $DASHBOARD_LOG"
echo ""
echo "Stop: bash start-vm-dev.sh --stop"
