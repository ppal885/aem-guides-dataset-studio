set -e
cd ~/aem-guides-dataset-studio

echo "1) Saving VM's own local manifest aside (773MB, has the old duplication bug)..."
cp backend/storage/aem_guides_doc_chunks.json /tmp/vm_local_manifest.json

echo "2) Clearing the working-tree/staged state so pull isn't blocked..."
git restore --staged backend/storage/aem_guides_doc_chunks.json 2>/dev/null || true
git checkout -- backend/storage/aem_guides_doc_chunks.json

echo "3) Pulling main (fix + clean 56MB manifest)..."
git pull origin main

echo "4) Saving the freshly-pulled clean manifest aside too..."
cp backend/storage/aem_guides_doc_chunks.json /tmp/vm_remote_manifest.json

echo "5) Running the merge (dedupes VM's local copy, unions with remote by chunk_id)..."
cat > /tmp/vm_merge_manifests.py << 'PYEOF'
"""Merge the VM's own (bloated) manifest with the freshly-pulled clean one from origin/main.
Dedupes the VM's local copy the same way experience_league_index_service.py was fixed
(only chunk_index 0 per url keeps the full paragraphs/list_items/codeph/codeblocks/tables
arrays), then unions both record sets by chunk_id/id, preferring the remote (already-clean)
copy on any overlap. Writes the merged result over the real manifest path.
"""
import json
from pathlib import Path

LOCAL_PATH = Path("/tmp/vm_local_manifest.json")   # VM's own 773MB, pre-pull, has the bug
REMOTE_PATH = Path("/tmp/vm_remote_manifest.json")  # freshly pulled from origin/main, clean
TARGET_PATH = Path("backend/storage/aem_guides_doc_chunks.json")
FIELDS = ("paragraphs", "list_items", "codeph", "codeblocks", "tables")


def dedup(data: list[dict]) -> list[dict]:
    seen_urls: set[str] = set()
    for row in data:
        url = row.get("url") or ""
        chunk_index = row.get("chunk_index")
        is_first = chunk_index == 0 or (chunk_index is None and url not in seen_urls)
        if is_first:
            seen_urls.add(url)
            continue
        for f in FIELDS:
            if row.get(f):
                row[f] = []
    return data


local_data = json.loads(LOCAL_PATH.read_text(encoding="utf-8"))
remote_data = json.loads(REMOTE_PATH.read_text(encoding="utf-8"))
print(f"local (VM-only): {len(local_data)} records, {LOCAL_PATH.stat().st_size / 1e6:.1f} MB")
print(f"remote (origin/main): {len(remote_data)} records, {REMOTE_PATH.stat().st_size / 1e6:.1f} MB")

local_data = dedup(local_data)

by_key: dict[str, dict] = {}
for row in local_data:
    key = row.get("chunk_id") or row.get("id")
    by_key[key] = row
local_unique = len(by_key)

overlap = 0
for row in remote_data:
    key = row.get("chunk_id") or row.get("id")
    if key in by_key:
        overlap += 1
    by_key[key] = row  # remote (already-clean) wins on overlap

merged = list(by_key.values())
print(f"local unique keys: {local_unique}, overlap with remote: {overlap}, merged total: {len(merged)}")

tmp_path = TARGET_PATH.with_suffix(".json.tmp")
encoder = json.JSONEncoder(indent=2)
with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
    for piece in encoder.iterencode(merged):
        f.write(piece)
tmp_path.replace(TARGET_PATH)
print(f"wrote merged manifest: {TARGET_PATH.stat().st_size / 1e6:.1f} MB")
PYEOF
python /tmp/vm_merge_manifests.py

echo ""
echo "6) Review the merge output above, then run these to commit + push (not automatic):"
echo "   cd ~/aem-guides-dataset-studio"
echo "   git add backend/storage/aem_guides_doc_chunks.json"
echo "   git commit -m 'feat(rag): merge VM-only ingested content with origin/main manifest'"
echo "   git push origin main"
