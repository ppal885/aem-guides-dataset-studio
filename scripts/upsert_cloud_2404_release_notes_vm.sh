#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
SCOPE="https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/release-notes/cloud-release-notes/2024-releases/2404-release"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

scrape_and_index() {
  local slug="$1"
  local key="$2"
  local state_dir="tmp/rag-2404-$key"
  local raw_output="tmp/cloud-2404-$key-behavior-chunks.json"
  local enriched_output="tmp/cloud-2404-$key-enriched-behavior-chunks.json"

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
    --output "$raw_output"

  "$PYTHON_BIN" scripts/enrich_experienceleague_behavior_chunks.py \
    --corpus-root "$state_dir/topics" \
    --output "$enriched_output"
}

upsert_chunks() {
  local input="$1"
  shift

  bash scripts/upsert_vm_rag_backend.sh \
    --input "$input" \
    --batch-size 16 \
    --service "$SERVICE_NAME" \
    --backend-url "$BACKEND_URL" \
    --public-url "$PUBLIC_URL" \
    "$@"
}

scrape_and_index "whats-new-2024-04-0" "whats-new"
scrape_and_index "fixed-issues-2024-04-0" "fixed"
scrape_and_index "upgrade-instructions-2024-04-0" "upgrade"

upsert_chunks "tmp/cloud-2404-whats-new-behavior-chunks.json" --no-restart
upsert_chunks "tmp/cloud-2404-whats-new-enriched-behavior-chunks.json" --no-restart
upsert_chunks "tmp/cloud-2404-fixed-behavior-chunks.json" --no-restart
upsert_chunks "tmp/cloud-2404-fixed-enriched-behavior-chunks.json" --no-restart
upsert_chunks "tmp/cloud-2404-upgrade-behavior-chunks.json" --no-restart
upsert_chunks "tmp/cloud-2404-upgrade-enriched-behavior-chunks.json"
