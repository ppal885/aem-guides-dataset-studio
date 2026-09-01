#!/usr/bin/env bash
# VM paste-script: ingest the content-management / migration / DITA-OT / security
# corpus (28 curated chunks) into the VM's AEM Guides ChromaDB + manifest.
#
# Prereqs on the VM:
#   - repo pulled to latest main (git pull) so backend/ingest_content_migration_ditaot_security.py exists
#   - backend venv active, backend/.env present (ANTHROPIC_API_KEY etc.)
#
# Usage:  bash scripts/vm_ingest_migration_ditaot_security.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT/backend"

echo "[vm-ingest] repo=$REPO_ROOT"
echo "[vm-ingest] pulling latest main..."
git -C "$REPO_ROOT" pull --ff-only || echo "[vm-ingest] WARN: git pull skipped/failed; continuing with local copy"

echo "[vm-ingest] running curated ingestion (28 chunks)..."
python ingest_content_migration_ditaot_security.py

echo "[vm-ingest] done. Validate a probe:"
python - <<'PY'
from dotenv import load_dotenv; load_dotenv()
from app.services import vector_store_service as vss
from app.services.embedding_service import embed_texts
e = embed_texts(["DITA-OT timeout default seconds publishing task terminated"])[0].tolist()
r = vss.query_collection(vss.CHROMA_COLLECTION_AEM_GUIDES, e, k=1)
top = r[0] if r else {}
print("probe top1 id:", top.get("id") or top.get("metadata", {}).get("id"))
print("collection total:", vss.get_collection_count(vss.CHROMA_COLLECTION_AEM_GUIDES))
PY
