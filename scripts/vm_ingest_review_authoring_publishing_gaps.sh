#!/usr/bin/env bash
# Targeted Experience League crawl refresh for feature-map source discovery.
#
# MUST run on the VM (or another host with internet access to Experience League,
# the embedding model, and the local aem_guides Chroma collection). This script
# fetches live documentation and intentionally does not invent or substitute URLs.
#
# Pipeline:
#   scrape_experienceleague_to_dita.py
#   enrich_experienceleague_behavior_chunks.py --upsert-chroma
#   confirm_and_merge_feature_urls.py [--apply]
#
# Each seed has an isolated, resumable state directory. The directory name is
# derived from the section key, scope, and seed URL. Consequently:
#   * every seed is enqueued on its first run;
#   * a changed seed starts a new state instead of inheriting an unrelated queue;
#   * unfinished queues resume independently;
#   * the pre-existing shared queue/manifest under STATE_DIR is never deleted or
#     rewritten by this targeted crawl.
#
# Usage:
#   bash scripts/vm_ingest_review_authoring_publishing_gaps.sh
#   APPLY=1 LIMIT=500 PYTHON=python3 bash scripts/vm_ingest_review_authoring_publishing_gaps.sh
set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python}"
STATE_DIR="${STATE_DIR:-experienceleague-dita-corpus}"
CORPUS_ROOT="${CORPUS_ROOT:-experienceleague-dita-corpus/topics}"
SECTION_STATE_ROOT="${SECTION_STATE_ROOT:-$STATE_DIR/feature-map-targeted-sections}"
LIMIT="${LIMIT:-200}"
ENRICH_MAX_CHUNKS="${ENRICH_MAX_CHUNKS:-0}"
HTTP_CONNECT_TIMEOUT="${HTTP_CONNECT_TIMEOUT:-15}"
HTTP_MAX_TIME="${HTTP_MAX_TIME:-60}"

DOCS="https://experienceleague.adobe.com/en/docs/experience-manager-guides"
UG="$DOCS/using/user-guide"
ICG="$DOCS/using/install-conf-guide"
KB="$DOCS/using/knowledge-base/kb-articles"

case "$LIMIT" in
  ''|*[!0-9]*) echo "ERROR: LIMIT must be a positive integer (received: $LIMIT)" >&2; exit 2 ;;
esac
if [ "$LIMIT" -le 0 ]; then
  echo "ERROR: LIMIT must be greater than zero" >&2
  exit 2
fi
case "$ENRICH_MAX_CHUNKS" in
  ''|*[!0-9]*) echo "ERROR: ENRICH_MAX_CHUNKS must be a non-negative integer" >&2; exit 2 ;;
esac

command -v "$PY" >/dev/null 2>&1 || {
  echo "ERROR: Python executable is unavailable: $PY" >&2
  exit 2
}
command -v curl >/dev/null 2>&1 || {
  echo "ERROR: curl is required for the live HTTP preflight" >&2
  exit 2
}

# Entries are "stable-key|scope-prefix|verified-leaf-seed". Directory-only
# Experience League URLs commonly return 404, so each seed is a real topic page.
# The runtime preflight below requires a final HTTP 200 before any crawl starts.
SECTIONS=(
  "review_overview|$UG/review/|$UG/review/review"
  "authoring_overview|$UG/author-content/|$UG/author-content/authoring-content-xml-doc"
  "authoring_editor_left_panel|$UG/author-content/work-with-editor/|$UG/author-content/work-with-editor/editor-interface-features/web-editor-left-panel"
  "authoring_editor_interface|$UG/author-content/work-with-editor/|$UG/author-content/work-with-editor/editor-interface-features/intro-editor-interface"
  "authoring_editor_toolbar|$UG/author-content/work-with-editor/|$UG/author-content/work-with-editor/editor-interface-features/web-editor-toolbar"
  "authoring_content_reuse|$KB/authoring/webeditor/|$KB/authoring/webeditor/content-reusability-in-aem-guides"
  "authoring_file_management|$UG/appendix/manage-content/|$UG/appendix/manage-content/authoring-upload-existing-files"
  "publishing_aem_sites|$UG/map-management-publishing/output-gen/output-presets-aemg/aem-sites/|$UG/map-management-publishing/output-gen/output-presets-aemg/aem-sites/generate-output-aem-site-web-editor"
  "publishing_eds|$KB/publishing/|$KB/publishing/configure-eds"
  "baseline_create_edit|$UG/map-management-publishing/output-gen/work-with-baseline/|$UG/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline"
  "baseline_publish|$UG/map-management-publishing/output-gen/work-with-baseline/|$UG/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing"
  "baseline_v2|$UG/map-management-publishing/output-gen/work-with-baseline/|$UG/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2"
  "baseline_migration|$UG/map-management-publishing/output-gen/work-with-baseline/|$UG/map-management-publishing/output-gen/work-with-baseline/new-baseline-migration-faq"
  "baseline_translation|$UG/map-management-publishing/translate-content/|$UG/map-management-publishing/translate-content/translate-documents-web-editor"
  "editor_oxygen_desktop|$UG/author-content/author-using-desktop-tools/|$UG/author-content/author-using-desktop-tools/author-desktop-tools"
  "editor_oxygen_configuration|$ICG/editor-configs/editor-cloud-settings/|$ICG/editor-configs/editor-cloud-settings/conf-edit-in-oxygen"
  "security_permissions|$ICG/user-group-sec-cs/|$ICG/user-group-sec-cs/user-admin-sec"
)

seed_fingerprint() {
  "$PY" - "$1" "$2" <<'PY'
import hashlib
import sys

payload = "\0".join(sys.argv[1:]).encode("utf-8")
print(hashlib.sha256(payload).hexdigest()[:12])
PY
}

state_tracks_seed() {
  "$PY" - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

state_dir = Path(sys.argv[1])
seed = sys.argv[2].rstrip("/")

def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback
    except (OSError, ValueError, TypeError):
        return fallback

manifest = read_json(state_dir / "manifest.json", {})
pending = read_json(state_dir / "queue.json", {}).get("pending", [])
known = [str(value).rstrip("/") for value in list(manifest) + list(pending)]
raise SystemExit(0 if seed in known else 1)
PY
}

seed_is_in_manifest() {
  "$PY" - "$1" "$2" <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1]) / "manifest.json"
seed = sys.argv[2].rstrip("/")
try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
known = {str(value).rstrip("/") for value in manifest}
raise SystemExit(0 if seed in known else 1)
PY
}

echo "== 0. Verify every Experience League leaf seed =="
preflight_failures=0
for entry in "${SECTIONS[@]}"; do
  IFS='|' read -r key scope seed <<< "$entry"
  status="$(curl --silent --show-error --location \
    --output /dev/null --write-out '%{http_code}' \
    --connect-timeout "$HTTP_CONNECT_TIMEOUT" --max-time "$HTTP_MAX_TIME" \
    --retry 2 --retry-delay 1 \
    --user-agent 'AEMGuidesDatasetStudio/1.0' \
    "$seed" || true)"
  if [ "$status" = "200" ]; then
    echo "HTTP 200  $key  $seed"
  else
    echo "ERROR: HTTP ${status:-request-failed}  $key  $seed" >&2
    preflight_failures=$((preflight_failures + 1))
  fi
done
if [ "$preflight_failures" -ne 0 ]; then
  echo "ERROR: $preflight_failures seed preflight(s) failed; no crawl was started." >&2
  echo "Find the current leaf page in the Experience League Guides navigation and update the seed; do not guess a replacement." >&2
  exit 1
fi

if [ -f "$STATE_DIR/queue.json" ] || [ -f "$STATE_DIR/manifest.json" ]; then
  echo "Preserving existing shared crawl state under $STATE_DIR; targeted states use $SECTION_STATE_ROOT"
fi

echo "== 1. Crawl targeted sections (limit $LIMIT/section) =="
section_corpus_roots=()
crawl_failures=()
for entry in "${SECTIONS[@]}"; do
  IFS='|' read -r key scope seed <<< "$entry"
  fingerprint="$(seed_fingerprint "$scope" "$seed")"
  state_base="$SECTION_STATE_ROOT/${key}-${fingerprint}"
  section_state="$state_base"

  # A failed fetch can consume the seed from a queue without adding it to the
  # manifest. Preserve that state for diagnosis and use a new retry directory.
  retry=0
  while [ -e "$section_state" ] && ! state_tracks_seed "$section_state" "$seed"; do
    retry=$((retry + 1))
    section_state="${state_base}-retry${retry}"
  done

  resume_args=()
  if [ -f "$section_state/queue.json" ] || [ -f "$section_state/manifest.json" ]; then
    resume_args=(--resume)
  fi

  echo "-- $key: $seed"
  if ! "$PY" scripts/scrape_experienceleague_to_dita.py \
      --state-dir "$section_state" \
      --scope-prefix "$scope" \
      --seed-url "$seed" \
      --limit "$LIMIT" \
      "${resume_args[@]}"; then
    echo "ERROR: crawl command failed for $key; state preserved at $section_state" >&2
    crawl_failures+=("$key")
    continue
  fi

  if ! seed_is_in_manifest "$section_state" "$seed"; then
    echo "ERROR: $key completed without recording its seed in manifest.json" >&2
    crawl_failures+=("$key")
    continue
  fi

  if [ ! -d "$section_state/topics" ] || \
      [ -z "$(find "$section_state/topics" -type f -name '*.dita' -print -quit)" ]; then
    echo "ERROR: $key recorded its seed but produced no DITA topic under $section_state/topics" >&2
    crawl_failures+=("$key")
    continue
  fi

  section_corpus_roots+=("$section_state/topics")
done

if [ "${#crawl_failures[@]}" -ne 0 ]; then
  echo "ERROR: targeted crawl failed for: ${crawl_failures[*]}" >&2
  echo "No Chroma upsert or feature-map merge was attempted; rerun to resume successful states and retry failed seeds." >&2
  exit 1
fi

echo "== 2. Enrich + upsert refreshed topics into aem_guides Chroma =="
corpus_args=()
if [ -d "$CORPUS_ROOT" ]; then
  corpus_args+=(--corpus-root "$CORPUS_ROOT")
fi
for corpus_root in "${section_corpus_roots[@]}"; do
  corpus_args+=(--corpus-root "$corpus_root")
done
if [ "${#corpus_args[@]}" -eq 0 ]; then
  echo "ERROR: no DITA corpus roots are available for enrichment" >&2
  exit 1
fi
"$PY" scripts/enrich_experienceleague_behavior_chunks.py \
  "${corpus_args[@]}" \
  --max-chunks "$ENRICH_MAX_CHUNKS" \
  --upsert-chroma

echo "== 3. Discover URL candidates and merge explicitly Human-approved sources =="
confirm_args=()
[ "${APPLY:-0}" = "1" ] && confirm_args+=(--apply)
# Override only when drafts intentionally live outside scripts/feature_map_drafts.
[ -n "${SCRATCH_DIR:-}" ] && confirm_args+=(--scratch-dir "$SCRATCH_DIR")
"$PY" scripts/confirm_and_merge_feature_urls.py "${confirm_args[@]}"

echo "== Done =="
echo "If APPLY=1 merged Human-approved features, sync skill copies/globals, update the surface-count"
echo "self-test to the actual merged count, run all self-tests and the hardcoding audit, then commit."
