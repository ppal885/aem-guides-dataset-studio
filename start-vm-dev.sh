#!/usr/bin/env bash
# Start AEM Guides Dataset Studio on a Linux VM without Docker.
# Usage:
#   bash start-vm-dev.sh
#   bash start-vm-dev.sh --backend-port 8000 --frontend-port 5173
#   bash start-vm-dev.sh --kill-ports
#   bash start-vm-dev.sh --stop

set -euo pipefail

BACKEND_PORT="8001"
FRONTEND_PORT="5173"
HOST="0.0.0.0"
STOP_ONLY="false"
SKIP_INSTALL="false"
KILL_PORTS="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --backend-port)
      BACKEND_PORT="${2:-}"
      shift 2
      ;;
    --frontend-port)
      FRONTEND_PORT="${2:-}"
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
      sed -n '1,40p' "$0"
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
FRONTEND_DIR="$ROOT_DIR/frontend"
LOG_DIR="$ROOT_DIR/logs"
PID_DIR="$ROOT_DIR/.run"
BACKEND_LOG="$LOG_DIR/backend-vm-dev.log"
FRONTEND_LOG="$LOG_DIR/frontend-vm-dev.log"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

mkdir -p "$LOG_DIR" "$PID_DIR"

info() { printf '\033[0;34m[INFO]\033[0m %s\n' "$*"; }
ok() { printf '\033[0;32m[OK]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[WARN]\033[0m %s\n' "$*"; }
fail() { printf '\033[0;31m[ERROR]\033[0m %s\n' "$*" >&2; }

command_exists() {
  command -v "$1" >/dev/null 2>&1
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
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      info "Stopping $label (pid $pid)"
      kill "$pid" 2>/dev/null || true
      sleep 2
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

stop_services() {
  stop_pid_file "$FRONTEND_PID_FILE" "frontend"
  stop_pid_file "$BACKEND_PID_FILE" "backend"

  for port in "$FRONTEND_PORT" "$BACKEND_PORT"; do
    local pids
    pids="$(port_pids "$port")"
    if [[ -n "$pids" ]]; then
      if [[ "$KILL_PORTS" == "true" ]]; then
        warn "Killing process(es) on port $port: $pids"
        kill $pids 2>/dev/null || true
        sleep 2
        kill -9 $pids 2>/dev/null || true
        if ! wait_for_port_free "$port" 8; then
          fail "Port $port is still busy after kill attempt: $(port_pids "$port")"
          echo "Run manually:"
          echo "  sudo lsof -i :$port"
          echo "  sudo kill -9 \$(sudo lsof -ti :$port)"
          exit 1
        fi
      else
        warn "Port $port is still used by: $pids"
        warn "If these are old app processes, rerun with: bash start-vm-dev.sh --kill-ports"
      fi
    fi
  done
}

if [[ "$STOP_ONLY" == "true" ]]; then
  stop_services
  ok "Stop requested."
  exit 0
fi

[[ -d "$BACKEND_DIR" ]] || { fail "Backend directory not found: $BACKEND_DIR"; exit 1; }
[[ -d "$FRONTEND_DIR" ]] || { fail "Frontend directory not found: $FRONTEND_DIR"; exit 1; }

if ! command_exists python3; then
  fail "python3 not found. Install it first: sudo apt install -y python3 python3-venv python3-pip"
  exit 1
fi

if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3)"
  fail "Python venv support is missing for python${PYTHON_VERSION}."
  echo "Run this on Ubuntu/Debian, then rerun the script:"
  echo "  sudo apt update"
  echo "  sudo apt install -y python${PYTHON_VERSION}-venv python3-pip"
  echo ""
  echo "If that package is unavailable, try:"
  echo "  sudo apt install -y python3-venv python3-pip"
  exit 1
fi

if ! command_exists npm; then
  fail "npm not found. Install Node.js 20+ first, then rerun this script."
  echo "Example:"
  echo "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
  echo "  sudo apt install -y nodejs"
  exit 1
fi

NODE_MAJOR="$(node -v 2>/dev/null | sed -E 's/^v([0-9]+).*/\1/' || echo 0)"
if [[ "${NODE_MAJOR:-0}" -lt 18 ]]; then
  fail "Node.js 18+ is required. Current: $(node -v 2>/dev/null || echo missing)"
  echo "Recommended: install Node.js 20 LTS."
  exit 1
fi

stop_services

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
  if [[ -n "$(port_pids "$port")" ]]; then
    fail "Port $port is still busy: $(port_pids "$port")"
    echo "Rerun with:"
    echo "  bash start-vm-dev.sh --kill-ports"
    exit 1
  fi
done

if [[ "$SKIP_INSTALL" != "true" ]]; then
  if [[ ! -d "$BACKEND_DIR/.venv" ]]; then
    info "Creating backend virtual environment"
    if ! python3 -m venv "$BACKEND_DIR/.venv"; then
      PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo 3)"
      fail "Could not create backend virtual environment."
      echo "Install venv support, remove the partial venv, then rerun:"
      echo "  sudo apt update"
      echo "  sudo apt install -y python${PYTHON_VERSION}-venv python3-pip"
      echo "  rm -rf backend/.venv"
      echo "  bash start-vm-dev.sh --kill-ports"
      exit 1
    fi
  fi

  info "Installing backend dependencies"
  "$BACKEND_DIR/.venv/bin/python" -m pip install --upgrade pip
  "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    info "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install)
  fi
fi

cat > "$FRONTEND_DIR/.env" <<EOF
VITE_PROXY_TARGET=http://127.0.0.1:${BACKEND_PORT}
EOF

info "Starting backend on http://127.0.0.1:${BACKEND_PORT}"
(
  cd "$BACKEND_DIR"
  export PYTHONUNBUFFERED=1
  nohup "$BACKEND_DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$BACKEND_LOG" 2>&1 &
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
  echo "Backend log:"
  tail -80 "$BACKEND_LOG" || true
  exit 1
fi
ok "Backend is healthy"

info "Starting frontend on http://${HOST}:${FRONTEND_PORT}"
(
  cd "$FRONTEND_DIR"
  nohup npm run dev -- --host "$HOST" --port "$FRONTEND_PORT" > "$FRONTEND_LOG" 2>&1 &
  echo $! > "$FRONTEND_PID_FILE"
)

FRONTEND_OK="false"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${FRONTEND_PORT}" >/dev/null 2>&1; then
    FRONTEND_OK="true"
    break
  fi
  sleep 1
done

if [[ "$FRONTEND_OK" != "true" ]]; then
  fail "Frontend did not become reachable."
  echo "Frontend log:"
  tail -80 "$FRONTEND_LOG" || true
  exit 1
fi

VM_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
ok "Frontend is reachable"
echo ""
echo "AEM Guides Dataset Studio is running:"
echo "  Frontend : http://${VM_IP:-localhost}:${FRONTEND_PORT}"
echo "  Backend  : http://${VM_IP:-localhost}:${BACKEND_PORT}/health"
echo "  API docs : http://${VM_IP:-localhost}:${BACKEND_PORT}/docs"
echo ""
echo "Logs:"
echo "  Backend  : $BACKEND_LOG"
echo "  Frontend : $FRONTEND_LOG"
echo ""
echo "Stop:"
echo "  bash start-vm-dev.sh --stop"
