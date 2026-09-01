#!/usr/bin/env bash
# Targeted Experience League crawl refresh for the thin feature-map sections
# (Review, Authoring web-editor, Publishing gaps) so the pending feature-map
# feature URLs become retrievable, then auto-confirm + merge them.
#
# MUST run on the VM (or any box with: internet to Experience League, the
# embedding model, and the local aem_guides Chroma). It cannot run from a
# session without internet - it fetches live EL pages.
#
# Reuses the existing pipeline:
#   scrape_experienceleague_to_dita.py  ->  experienceleague-dita-corpus/topics
#   enrich_experienceleague_behavior_chunks.py --upsert-chroma  ->  CHROMA_COLLECTION_AEM_GUIDES
#   confirm_and_merge_feature_urls.py --apply  ->  data/aem_feature_map.json
#
# Idempotent: --resume shares crawl state (no re-fetch); Chroma upsert refreshes.
#
# Usage:
#   bash scripts/vm_ingest_review_authoring_publishing_gaps.sh            # crawl + upsert + confirm-merge (dry run)
#   APPLY=1 bash scripts/vm_ingest_review_authoring_publishing_gaps.sh    # also write the merged feature-map
#   LIMIT=150 bash scripts/vm_ingest_review_authoring_publishing_gaps.sh  # per-section page cap
set -euo pipefail

cd "$(dirname "$0")/.."
PY="${PYTHON:-python}"
STATE_DIR="${STATE_DIR:-experienceleague-dita-corpus}"
CORPUS_ROOT="${CORPUS_ROOT:-experienceleague-dita-corpus/topics}"
LIMIT="${LIMIT:-200}"
G="https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide"

# Thin sections to (re)crawl. Each entry is "scope-prefix|seed-url" - the crawl
# stays within scope-prefix. Verify a path on the live site if a section returns
# nothing (EL slugs occasionally change; e.g. review-collaborate vs review-collab,
# and EDS/GitHub publishing may be a newer section).
SECTIONS=(
  "$G/review-collaborate/|$G/review-collaborate/"
  "$G/author-content/|$G/author-content/"
  "$G/map-management-publishing/generate-output/work-with-baseline/|$G/map-management-publishing/generate-output/work-with-baseline/"
  "$G/map-management-publishing/generate-output/aem-site/|$G/map-management-publishing/generate-output/aem-site/"
  "$G/map-management-publishing/publish-eds/|$G/map-management-publishing/publish-eds/"
)

echo "== 1. Crawl thin sections into $CORPUS_ROOT (limit $LIMIT/section) =="
first=1
for entry in "${SECTIONS[@]}"; do
  scope="${entry%%|*}"; seed="${entry##*|}"
  resume_flag="--resume"; [ "$first" = "1" ] && resume_flag=""   # first run seeds fresh state
  echo "-- section: $seed"
  "$PY" scripts/scrape_experienceleague_to_dita.py \
      --state-dir "$STATE_DIR" \
      --scope-prefix "$scope" \
      --seed-url "$seed" \
      --limit "$LIMIT" $resume_flag \
    || echo "   (section crawl reported an issue; continuing - verify the URL on the live site)"
  first=0
done

echo "== 2. Enrich + upsert the refreshed corpus into aem_guides Chroma =="
"$PY" scripts/enrich_experienceleague_behavior_chunks.py \
    --corpus-root "$CORPUS_ROOT" \
    --upsert-chroma

echo "== 3. Auto-confirm EL URLs for pending features and merge =="
CONFIRM_ARGS=""
[ "${APPLY:-0}" = "1" ] && CONFIRM_ARGS="--apply"
# --scratch-dir defaults to the session scratchpad holding the *_surface_draft.json files;
# override with SCRATCH_DIR=/path if the drafts live elsewhere.
if [ -n "${SCRATCH_DIR:-}" ]; then CONFIRM_ARGS="$CONFIRM_ARGS --scratch-dir $SCRATCH_DIR"; fi
"$PY" scripts/confirm_and_merge_feature_urls.py $CONFIRM_ARGS

echo "== Done. If --apply merged new features: sync copies+globals, bump the feature-map"
echo "   surface-count self-test if a new surface (e.g. REVIEW) was added, run self-tests, commit. =="
