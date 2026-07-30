#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="aem-backend.service"
PUBLIC_URL="http://10.42.46.78:4502"
BACKEND_URL="http://127.0.0.1:8001"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/diagnose_vm_rag_backend.sh [--service aem-backend.service] [--public-url http://10.42.46.78:4502] [--backend-url http://127.0.0.1:8001]

What it does:
  - Shows the systemd backend process, command, cwd, and relevant env vars.
  - Shows nginx proxy_pass entries and listeners for ports 4502/8001.
  - Compares Chroma counts from the current shell, backend/.venv, direct backend URL, and public nginx URL.
  - Does not modify files, services, nginx, or Chroma.

Example:
  cd /root/aem-guides-dataset-studio
  bash scripts/diagnose_vm_rag_backend.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --service)
      SERVICE_NAME="${2:-}"
      [[ -n "$SERVICE_NAME" ]] || { echo "ERROR: --service requires a value" >&2; exit 2; }
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

json_count() {
  python3 - "$1" <<'PY'
from __future__ import annotations
import json
import sys

try:
    data = json.loads(sys.argv[1])
except Exception as exc:
    print(f"JSON_PARSE_ERROR: {exc}")
    raise SystemExit(0)

for key in ("aem_guides", "dita_spec", "dita_ot_github", "jira_qa", "learned_qa"):
    value = ((data.get(key) or {}).get("chunk_count"))
    if value is not None:
        print(f"{key}.chunk_count={value}")
PY
}

python_probe() {
  "$1" - <<'PY'
from __future__ import annotations
import os
import sys

from app.storage import get_storage
from app.services.vector_store_service import (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_OT_GITHUB,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_JIRA_QA,
    CHROMA_COLLECTION_LEARNED_QA,
    _get_chroma_path,
    get_collection_count,
    is_chroma_available,
)

print("python:", sys.executable)
print("cwd:", os.getcwd())
print("VIRTUAL_ENV:", os.getenv("VIRTUAL_ENV"))
print("PYTHONPATH:", os.getenv("PYTHONPATH"))
print("STORAGE_PATH:", os.getenv("STORAGE_PATH"))
print("storage_base:", get_storage().base_path)
print("chroma_path:", _get_chroma_path())
print("chroma_available:", is_chroma_available())
for collection in (
    CHROMA_COLLECTION_AEM_GUIDES,
    CHROMA_COLLECTION_DITA_SPEC,
    CHROMA_COLLECTION_DITA_OT_GITHUB,
    CHROMA_COLLECTION_JIRA_QA,
    CHROMA_COLLECTION_LEARNED_QA,
):
    print(f"{collection}.count:", get_collection_count(collection))
PY
}

section "repo"
echo "root_dir=$ROOT_DIR"
echo "pwd=$(pwd)"
if [[ -d .git ]]; then
  git rev-parse --short HEAD 2>/dev/null || true
  git status --short --branch 2>/dev/null | head -40 || true
fi

section "ports"
ss -ltnp 2>/dev/null | grep -E ':(4502|8001)\b' || true

section "nginx proxy_pass"
grep -R "proxy_pass" -n /etc/nginx/sites-enabled /etc/nginx/conf.d /etc/nginx/nginx.conf 2>/dev/null || true

section "systemd service: $SERVICE_NAME"
systemctl status "$SERVICE_NAME" --no-pager -l || true
PID="$(systemctl show -p MainPID --value "$SERVICE_NAME" 2>/dev/null || true)"
echo "MainPID=${PID:-}"
if [[ -n "${PID:-}" && "$PID" != "0" && -d "/proc/$PID" ]]; then
  echo "service_cwd=$(readlink -f "/proc/$PID/cwd" 2>/dev/null || true)"
  echo "service_cmd=$(tr '\0' ' ' < "/proc/$PID/cmdline" 2>/dev/null || true)"
  echo "service_env:"
  tr '\0' '\n' < "/proc/$PID/environ" 2>/dev/null | grep -E 'STORAGE_PATH|PYTHONPATH|VIRTUAL_ENV|CHROMA|AEM_STUDIO' || true
fi

section "current shell python probe"
if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
  VIRTUAL_ENV="$VIRTUAL_ENV" PATH="$VIRTUAL_ENV/bin:$PATH" PYTHONPATH=backend python_probe "$VIRTUAL_ENV/bin/python"
else
  echo "No VIRTUAL_ENV active in current shell."
fi

section "backend/.venv python probe"
if [[ -x "$ROOT_DIR/backend/.venv/bin/python" ]]; then
  VIRTUAL_ENV="$ROOT_DIR/backend/.venv" PATH="$ROOT_DIR/backend/.venv/bin:$PATH" PYTHONPATH=backend python_probe "$ROOT_DIR/backend/.venv/bin/python"
else
  echo "backend/.venv/bin/python not found."
fi

section "HTTP direct backend: $BACKEND_URL"
DIRECT_JSON="$(curl -fsS "$BACKEND_URL/api/v1/ai/rag-status" 2>/dev/null || true)"
if [[ -n "$DIRECT_JSON" ]]; then
  json_count "$DIRECT_JSON"
else
  echo "No response from $BACKEND_URL/api/v1/ai/rag-status"
fi

section "HTTP public/nginx: $PUBLIC_URL"
PUBLIC_JSON="$(curl -fsS "$PUBLIC_URL/api/v1/ai/rag-status" 2>/dev/null || true)"
if [[ -n "$PUBLIC_JSON" ]]; then
  json_count "$PUBLIC_JSON"
else
  echo "No response from $PUBLIC_URL/api/v1/ai/rag-status"
fi

section "summary hints"
echo "If backend/.venv count is low, run scripts/upsert_vm_rag_backend.sh to upsert with the same venv/storage used by the service."
echo "If backend/.venv count is high but HTTP count is low, run scripts/upsert_vm_rag_backend.sh --restart-only."
echo "If direct backend and public URL differ, reload nginx with: nginx -t && systemctl reload nginx"
