#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
SCOPE="https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/release-info/release-notes/on-prem-release-notes/500-release"
SLUGS=(
  "whats-new-5-0-0"
  "fixed-issues-5-0-0"
  "upgrade-instructions-5-0-0"
)

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

for slug in "${SLUGS[@]}"; do
  state_dir="tmp/rag-onprem-500-$slug"
  raw_output="tmp/onprem-500-$slug-behavior-chunks.json"
  enriched_output="tmp/onprem-500-$slug-enriched-behavior-chunks.json"

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
done

INPUTS=()
for slug in "${SLUGS[@]}"; do
  INPUTS+=(
    "tmp/onprem-500-$slug-behavior-chunks.json"
    "tmp/onprem-500-$slug-enriched-behavior-chunks.json"
  )
done

last_index=$((${#INPUTS[@]} - 1))
for index in "${!INPUTS[@]}"; do
  args=(
    --input "${INPUTS[$index]}"
    --batch-size 16
    --service "$SERVICE_NAME"
    --backend-url "$BACKEND_URL"
    --public-url "$PUBLIC_URL"
  )
  if [[ "$index" -lt "$last_index" ]]; then
    args+=(--no-restart)
  fi
  bash scripts/upsert_vm_rag_backend.sh "${args[@]}"
done
