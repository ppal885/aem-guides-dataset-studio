#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/backend/.venv/bin/python}"
SERVICE_NAME="${SERVICE_NAME:-aem-backend.service}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: Python executable not found: $PYTHON_BIN" >&2
  exit 1
fi

count_dita_spec() {
  PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" - <<'PY'
from app.services.vector_store_service import CHROMA_COLLECTION_DITA_SPEC, get_collection_count
print(get_collection_count(CHROMA_COLLECTION_DITA_SPEC))
PY
}

echo "dita_spec_count_before=$(count_dita_spec)"
PYTHONPATH="$ROOT_DIR/backend" "$PYTHON_BIN" scripts/upsert_dita_spec_gap_chunks.py --batch-size 16
echo "dita_spec_count_after=$(count_dita_spec)"

sudo systemctl restart "$SERVICE_NAME"
sleep 5
sudo systemctl --no-pager --full status "$SERVICE_NAME" | sed -n '1,16p'
