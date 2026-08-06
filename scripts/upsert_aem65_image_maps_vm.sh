#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:8001}"
PUBLIC_URL="${PUBLIC_URL:-http://10.42.46.78:4502}"
SCOPE="https://experienceleague.adobe.com/en/docs/experience-manager-65/content/assets/using"
SOURCE_URL="$SCOPE/image-maps"
STATE_DIR="tmp/rag-aem65-image-maps"
OUTPUT="tmp/rag-aem65-image-maps-chunks.json"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" scripts/scrape_experienceleague_to_dita.py \
  --reset \
  --state-dir "$STATE_DIR" \
  --scope-prefix "$SCOPE" \
  --seed-url "$SOURCE_URL" \
  --limit 1 \
  --batch-size 1 \
  --delay 0

"$PYTHON_BIN" scripts/index_dita_behavior_corpus.py \
  --corpus-root "$STATE_DIR" \
  --output "$OUTPUT"

bash scripts/upsert_vm_rag_backend.sh \
  --input "$OUTPUT" \
  --batch-size 16 \
  --service "$SERVICE_NAME" \
  --backend-url "$BACKEND_URL" \
  --public-url "$PUBLIC_URL"
