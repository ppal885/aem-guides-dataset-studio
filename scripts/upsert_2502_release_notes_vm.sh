#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
SCOPE="https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/release-notes/cloud-release-notes/2025-releases/2502-release"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

scrape_and_index() {
  local slug="$1"
  local state_dir="tmp/rag-2502-$slug"
  local output="tmp/rag-2502-$slug-chunks.json"

  "$PYTHON_BIN" scripts/scrape_experienceleague_to_dita.py \
    --reset \
    --state-dir "$state_dir" \
    --scope-prefix "$SCOPE" \
    --seed-url "$SCOPE/$slug" \
    --limit 1 \
    --batch-size 1 \
    --delay 0

  "$PYTHON_BIN" scripts/index_dita_behavior_corpus.py \
    --corpus-root "$state_dir" \
    --output "$output"
}

scrape_and_index "whats-new-2025-02-0"
scrape_and_index "fixed-issues-2025-02-0"

bash scripts/upsert_vm_rag_backend.sh \
  --input tmp/rag-2502-whats-new-2025-02-0-chunks.json \
  --batch-size 16 \
  --service "$SERVICE_NAME" \
  --backend-url "$BACKEND_URL" \
  --public-url "$PUBLIC_URL" \
  --no-restart

bash scripts/upsert_vm_rag_backend.sh \
  --input tmp/rag-2502-fixed-issues-2025-02-0-chunks.json \
  --batch-size 16 \
  --service "$SERVICE_NAME" \
  --backend-url "$BACKEND_URL" \
  --public-url "$PUBLIC_URL"
