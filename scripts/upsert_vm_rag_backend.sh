#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="aem-backend.service"
PUBLIC_URL="http://10.42.46.78:4502"
BACKEND_URL="http://127.0.0.1:8001"
INPUT_PATH="backend/storage/aem_guides_enriched_behavior_chunks.json"
BATCH_SIZE="16"
MIN_EXPECTED="1000"
RESTART_SERVICE="1"
RELOAD_NGINX="0"
DRY_RUN="0"
RESTART_ONLY="0"
STORAGE_PATH_OVERRIDE=""
PYTHONPATH_OVERRIDE=""

usage() {
  cat <<'EOF'
Usage:
  bash scripts/upsert_vm_rag_backend.sh [options]

Options:
  --service NAME          systemd service to restart; default: aem-backend.service
  --input PATH            behavior chunks JSON; default: backend/storage/aem_guides_enriched_behavior_chunks.json
  --batch-size N          Chroma upsert batch size; default: 16
  --min-expected N        fail if final aem_guides count is below this; default: 1000
  --public-url URL        nginx/public URL; default: http://10.42.46.78:4502
  --backend-url URL       direct backend URL; default: http://127.0.0.1:8001
  --storage-path PATH     override STORAGE_PATH for the upsert; default: live service STORAGE_PATH
  --pythonpath VALUE      override PYTHONPATH for the upsert; default: live service PYTHONPATH or backend
  --no-restart            upsert only, do not restart systemd service
  --restart-only          skip upsert and only restart/verify service
  --reload-nginx          run nginx -t and reload nginx after service restart
  --dry-run               show resolved paths/counts but do not upsert/restart

What it does:
  - Uses backend/.venv/bin/python when available.
  - Uses the live systemd service STORAGE_PATH by default, so Chroma writes to the same DB that HTTP reads.
  - Restarts the systemd backend service so HTTP RAG sees the updated Chroma collection.
  - Verifies counts through direct backend and public nginx URL.

Example:
  cd /root/aem-guides-dataset-studio
  bash scripts/upsert_vm_rag_backend.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE_NAME="${2:-}"
      [[ -n "$SERVICE_NAME" ]] || { echo "ERROR: --service requires a value" >&2; exit 2; }
      shift 2
      ;;
    --input)
      INPUT_PATH="${2:-}"
      [[ -n "$INPUT_PATH" ]] || { echo "ERROR: --input requires a path" >&2; exit 2; }
      shift 2
      ;;
    --batch-size)
      BATCH_SIZE="${2:-}"
      [[ "$BATCH_SIZE" =~ ^[0-9]+$ ]] || { echo "ERROR: --batch-size requires an integer" >&2; exit 2; }
      shift 2
      ;;
    --min-expected)
      MIN_EXPECTED="${2:-}"
      [[ "$MIN_EXPECTED" =~ ^[0-9]+$ ]] || { echo "ERROR: --min-expected requires an integer" >&2; exit 2; }
      shift 2
      ;;
    --public-url)
      PUBLIC_URL="${2:-}"
      [[ -n "$PUBLIC_URL" ]] || { echo "ERROR: --public-url requires a value" >&2; exit 2; }
      shift 2
      ;;
    --backend-url)
      BACKEND_URL="${2:-}"
      [[ -n "$BACKEND_URL" ]] || { echo "ERROR: --backend-url requires a value" >&2; exit 2; }
      shift 2
      ;;
    --storage-path)
      STORAGE_PATH_OVERRIDE="${2:-}"
      [[ -n "$STORAGE_PATH_OVERRIDE" ]] || { echo "ERROR: --storage-path requires a value" >&2; exit 2; }
      shift 2
      ;;
    --pythonpath)
      PYTHONPATH_OVERRIDE="${2:-}"
      [[ -n "$PYTHONPATH_OVERRIDE" ]] || { echo "ERROR: --pythonpath requires a value" >&2; exit 2; }
      shift 2
      ;;
    --no-restart)
      RESTART_SERVICE="0"
      shift
      ;;
    --restart-only)
      RESTART_ONLY="1"
      shift
      ;;
    --reload-nginx)
      RELOAD_NGINX="1"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

section() {
  echo
  echo "==== $* ===="
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

service_env_value() {
  local name="$1"
  local pid="${2:-}"
  if [[ -z "$pid" || "$pid" == "0" || ! -r "/proc/$pid/environ" ]]; then
    return 0
  fi
  tr '\0' '\n' < "/proc/$pid/environ" 2>/dev/null | sed -n "s/^${name}=//p" | head -1
}

extract_aem_count() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); print((data.get("aem_guides") or {}).get("chunk_count", ""))'
}

http_count() {
  local url="$1"
  local raw
  raw="$(curl -fsS "$url/api/v1/ai/rag-status" 2>/dev/null || true)"
  if [[ -z "$raw" ]]; then
    echo ""
    return 0
  fi
  printf '%s' "$raw" | extract_aem_count
}

wait_http_count() {
  local url="$1"
  local attempts="${2:-24}"
  local delay_seconds="${3:-5}"
  local count=""

  for ((attempt = 1; attempt <= attempts; attempt++)); do
    count="$(http_count "$url")"
    if [[ -n "$count" ]]; then
      printf '%s' "$count"
      return 0
    fi
    echo "Waiting for RAG status at $url (attempt $attempt/$attempts)..." >&2
    sleep "$delay_seconds"
  done

  return 1
}

if [[ ! -f "$INPUT_PATH" && "$RESTART_ONLY" != "1" ]]; then
  fail "input JSON not found: $INPUT_PATH"
fi

if [[ -x backend/.venv/bin/python ]]; then
  PYTHON_BIN="$ROOT_DIR/backend/.venv/bin/python"
  VENV_DIR="$ROOT_DIR/backend/.venv"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  PYTHON_BIN="${VIRTUAL_ENV}/bin/python"
  VENV_DIR="$VIRTUAL_ENV"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
  VENV_DIR=""
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
  VENV_DIR=""
else
  fail "python not found"
fi

SERVICE_PID="$(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || true)"
SERVICE_STORAGE_PATH="$(service_env_value STORAGE_PATH "$SERVICE_PID")"
SERVICE_PYTHONPATH="$(service_env_value PYTHONPATH "$SERVICE_PID")"
SERVICE_VIRTUAL_ENV="$(service_env_value VIRTUAL_ENV "$SERVICE_PID")"
EFFECTIVE_STORAGE_PATH="${STORAGE_PATH_OVERRIDE:-${SERVICE_STORAGE_PATH:-${STORAGE_PATH:-}}}"
EFFECTIVE_PYTHONPATH="${PYTHONPATH_OVERRIDE:-${SERVICE_PYTHONPATH:-backend}}"
if [[ -n "$SERVICE_VIRTUAL_ENV" && -x "$SERVICE_VIRTUAL_ENV/bin/python" ]]; then
  PYTHON_BIN="$SERVICE_VIRTUAL_ENV/bin/python"
  VENV_DIR="$SERVICE_VIRTUAL_ENV"
fi

run_backend_python() {
  local -a env_args
  env_args=("PATH=${VENV_DIR:+$VENV_DIR/bin:}$PATH" "PYTHONPATH=$EFFECTIVE_PYTHONPATH")
  if [[ -n "$VENV_DIR" ]]; then
    env_args+=("VIRTUAL_ENV=$VENV_DIR")
  fi
  if [[ -n "$EFFECTIVE_STORAGE_PATH" ]]; then
    env_args+=("STORAGE_PATH=$EFFECTIVE_STORAGE_PATH")
  fi
  env "${env_args[@]}" "$PYTHON_BIN" "$@"
}

section "resolved runtime"
echo "root_dir=$ROOT_DIR"
echo "service=$SERVICE_NAME"
echo "service_pid=${SERVICE_PID:-}"
echo "python=$PYTHON_BIN"
echo "venv=$VENV_DIR"
echo "service_storage_path=${SERVICE_STORAGE_PATH:-}"
echo "effective_storage_path=${EFFECTIVE_STORAGE_PATH:-<backend default>}"
echo "effective_pythonpath=$EFFECTIVE_PYTHONPATH"
echo "input=$INPUT_PATH"
echo "batch_size=$BATCH_SIZE"
echo "public_url=$PUBLIC_URL"
echo "backend_url=$BACKEND_URL"

section "service before"
systemctl status "$SERVICE_NAME" --no-pager -l || true
PID="$SERVICE_PID"
echo "MainPID=${PID:-}"
if [[ -n "${PID:-}" && "$PID" != "0" && -d "/proc/$PID" ]]; then
  echo "service_cwd=$(readlink -f "/proc/$PID/cwd" 2>/dev/null || true)"
  echo "service_cmd=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)"
  echo "service_env:"
  tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | grep -E 'STORAGE_PATH|PYTHONPATH|VIRTUAL_ENV|CHROMA|AEM_STUDIO' || true
fi

section "counts before"
run_backend_python - <<'PY'
from __future__ import annotations
import os

from app.storage import get_storage
from app.services.vector_store_service import CHROMA_COLLECTION_AEM_GUIDES, _get_chroma_path, get_collection_count, is_chroma_available

print("STORAGE_PATH:", os.getenv("STORAGE_PATH"))
print("storage_base:", get_storage().base_path)
print("chroma_path:", _get_chroma_path())
print("chroma_available:", is_chroma_available())
print("python_count:", get_collection_count(CHROMA_COLLECTION_AEM_GUIDES))
PY
DIRECT_BEFORE="$(http_count "$BACKEND_URL")"
PUBLIC_BEFORE="$(http_count "$PUBLIC_URL")"
echo "direct_http_count=${DIRECT_BEFORE:-unavailable}"
echo "public_http_count=${PUBLIC_BEFORE:-unavailable}"

if [[ "$DRY_RUN" == "1" ]]; then
  section "dry run complete"
  exit 0
fi

if [[ "$RESTART_ONLY" != "1" ]]; then
  section "upsert"
  run_backend_python -u scripts/upsert_behavior_chunks_json.py \
    --input "$INPUT_PATH" \
    --batch-size "$BATCH_SIZE"
fi

section "count after upsert before restart"
run_backend_python - <<'PY'
from app.services.vector_store_service import CHROMA_COLLECTION_AEM_GUIDES, get_collection_count

print("python_count:", get_collection_count(CHROMA_COLLECTION_AEM_GUIDES))
PY

if [[ "$RESTART_SERVICE" == "1" ]]; then
  section "restart service"
  systemctl restart "$SERVICE_NAME"
  sleep 2
  systemctl status "$SERVICE_NAME" --no-pager -l || true
fi

if [[ "$RELOAD_NGINX" == "1" ]]; then
  section "reload nginx"
  nginx -t
  systemctl reload nginx
fi

section "verify HTTP counts"
DIRECT_AFTER="$(wait_http_count "$BACKEND_URL" 24 5 || true)"
PUBLIC_AFTER="$(wait_http_count "$PUBLIC_URL" 24 5 || true)"
echo "direct_http_count=${DIRECT_AFTER:-unavailable}"
echo "public_http_count=${PUBLIC_AFTER:-unavailable}"

if [[ -z "$DIRECT_AFTER" ]]; then
  fail "direct backend RAG status unavailable: $BACKEND_URL/api/v1/ai/rag-status"
fi
if (( DIRECT_AFTER < MIN_EXPECTED )); then
  fail "direct backend aem_guides count $DIRECT_AFTER is below --min-expected $MIN_EXPECTED"
fi
if [[ -z "$PUBLIC_AFTER" ]]; then
  fail "public/nginx RAG status unavailable: $PUBLIC_URL/api/v1/ai/rag-status"
fi
if (( PUBLIC_AFTER < MIN_EXPECTED )); then
  fail "public/nginx aem_guides count $PUBLIC_AFTER is below --min-expected $MIN_EXPECTED"
fi
if [[ "$DIRECT_AFTER" != "$PUBLIC_AFTER" ]]; then
  echo "WARN: direct backend count ($DIRECT_AFTER) differs from public/nginx count ($PUBLIC_AFTER). Consider: nginx -t && systemctl reload nginx" >&2
fi

section "done"
echo "AEM Guides RAG count is healthy. direct=$DIRECT_AFTER public=$PUBLIC_AFTER"
