"""One-off curated ingestion: 'Generate output for a DITA map from the Map console'
section of https://experienceleague.adobe.com/.../generate-output-for-a-dita-map

Adds a handful of semantically-scoped, richly-tagged records to the EXISTING
aem_guides Chroma collection + JSON manifest (no new vector DB). Distinct from
the generic flat crawl of the same URL already in the manifest: uses an
anchored url (#generate-output-for-a-dita-map-from-the-map-console) as this
record set's identity so a future generic re-crawl of the plain URL cannot
wipe these curated chunks via the generic merge-by-url dedup.

Text below is verified against the live page (fetched and parsed this run),
not inferred from the task spec's workflow diagram.
"""
import hashlib
import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from dotenv import load_dotenv

load_dotenv("backend/.env" if Path("backend/.env").exists() else ".env")

from app.services.embedding_service import embed_texts
from app.services.vector_store_service import CHROMA_COLLECTION_AEM_GUIDES, add_documents, get_collection_count

PLAIN_URL = (
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
    "using/user-guide/map-management-publishing/output-gen/generate-output/"
    "generate-output-for-a-dita-map"
)
ANCHORED_URL = PLAIN_URL + "#generate-output-for-a-dita-map-from-the-map-console"
HEADING_PATH = ["Generate output", "Generate output for a DITA map from the Map console"]
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "mapconsole-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_url": ANCHORED_URL,
    "canonical_url": PLAIN_URL,
    "source_title": "Generate output for a DITA map from the Map console",
    "source_type": "EXPERIENCE_LEAGUE",
    "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES",
    "domain": "PUBLISHING",
    "capability": "OUTPUT_GENERATION",
    "sub_capability": "MAP_CONSOLE_OUTPUT_GENERATION",
    "surface": "MAP_CONSOLE",
    "workflow": "GENERATE_OUTPUT",
    "heading_path": "|".join(HEADING_PATH),
    "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    {
        "chunk_id": "mapconsole_generate_output_workflow_01",
        "record_type": "PUBLISHING_WORKFLOW",
        "content_type": "WORKFLOW",
        "relations": [
            "MAP_OPENS_IN_MAP_CONSOLE",
            "MAP_CONSOLE_LISTS_OUTPUT_PRESETS",
            "PRESET_SUPPORTS_GENERATE",
            "GENERATE_STARTS_OUTPUT_PROCESS",
        ],
        "entry_points": "FLOW_A:OPEN_PRESET->GENERATE_OUTPUT|FLOW_B:PRESET_CONTEXT_MENU->GENERATE",
        "text": (
            "To generate output for a DITA map from the Map console: open the map file in the "
            "Map console. The Map console displays the list of Output presets available to "
            "generate output. There are two documented ways to start generation from here: "
            "(1) open the preset you want to use and select 'Generate output' to start the "
            "generation process, or (2) hover over the preset and select 'Generate' from the "
            "preset context menu. These are two documented UI entry points for the same "
            "product operation - the documentation does not state they share identical "
            "implementation. Once output generation is complete, select 'View output' to view "
            "the generated output."
        ),
    },
    {
        "chunk_id": "mapconsole_generate_output_success_01",
        "record_type": "PUBLISHING_STATE",
        "content_type": "BEHAVIOR",
        "relations": ["SUCCESS_EXPOSES_VIEW_OUTPUT"],
        "text": (
            "What happens after Map console output generation succeeds: once output "
            "generation for a DITA map from the Map console completes successfully, a Success "
            "dialog box/notification is displayed (documented at the lower-right corner of the "
            "screen - a UI detail, not a fixed product contract) and the generated output "
            "becomes available for the user to open via 'View output'."
        ),
    },
    {
        "chunk_id": "mapconsole_generate_output_error_01",
        "record_type": "PUBLISHING_ERROR_FLOW",
        "content_type": "ERROR_HANDLING",
        "relations": ["FAILURE_EXPOSES_ERROR"],
        "text": (
            "If output generation for a DITA map from the Map console is not successful, an "
            "error message is displayed to the user."
        ),
    },
    {
        "chunk_id": "mapconsole_generate_output_diagnostic_01",
        "record_type": "PUBLISHING_DIAGNOSTIC",
        "content_type": "ERROR_HANDLING",
        "relations": ["FAILURE_HAS_VIEW_LOG_PATH"],
        "text": (
            "How to inspect a failed Map console publishing job: to view the error log after "
            "a failed Map console output generation, select 'Dismiss' on the error message, "
            "hover over the selected preset tab, and select 'View log' from the preset context "
            "menu. View Log is available in the preset context menu - that is the documented "
            "location for View log after a publishing failure."
        ),
    },
    {
        "chunk_id": "mapconsole_generate_output_ditaval_limitation_01",
        "record_type": "PUBLISHING_LIMITATION",
        "content_type": "LIMITATION",
        "relations": [
            "DITAVAL_FLAGGED_IMAGE_COPIED_TO_OUTPUT",
            "MULTIPLE_DITAVAL_REQUIRES_UNIQUE_FILENAMES",
        ],
        "text": (
            "If your map uses a DITAVAL file, any flagged images referenced in the DITAVAL "
            "file are copied to a location related to the published map in the output. Also, "
            "if you are using multiple DITAVAL files for filtering within the same map, ensure "
            "you use unique .ditaval file names to avoid duplicate filename issues during "
            "publishing. This is documented specifically for Map console DITA map output "
            "generation, not a general DITAVAL rule for unrelated workflows."
        ),
    },
]


def build_full_records() -> list[dict]:
    out = []
    for r in RECORDS:
        content = r["text"]
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        rec = {
            **COMMON,
            "id": r["chunk_id"],
            "chunk_id": r["chunk_id"],
            "url": ANCHORED_URL,
            "record_type": r["record_type"],
            "content_type": r["content_type"],
            "relations": r["relations"],
            "content": content,
            "checksum": checksum,
            "title": COMMON["source_title"],
        }
        if "entry_points" in r:
            rec["entry_points"] = r["entry_points"]
        out.append(rec)
    return out


def upsert_manifest(records: list[dict]) -> int:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = []
    new_ids = {r["chunk_id"] for r in records}
    kept = [row for row in existing if row.get("chunk_id") not in new_ids]
    merged = kept + records
    MANIFEST_PATH.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return len(merged)


def upsert_chroma(records: list[dict]) -> int:
    texts = [r["content"] for r in records]
    embeddings = embed_texts(texts)
    if embeddings is None:
        print("ERROR: embeddings unavailable")
        return 0
    ids = [r["chunk_id"] for r in records]
    metadatas = []
    for r in records:
        meta = {k: v for k, v in r.items() if k not in ("content",)}
        # Flatten list-valued fields to pipe-joined strings (Chroma metadata is scalar-only)
        if isinstance(meta.get("relations"), list):
            meta["relations"] = "|".join(meta["relations"])
        metadatas.append(meta)
    emb_list = [embeddings[i].tolist() for i in range(len(records))]
    ok = add_documents(CHROMA_COLLECTION_AEM_GUIDES, ids=ids, documents=texts, metadatas=metadatas, embeddings=emb_list)
    return len(records) if ok else 0


if __name__ == "__main__":
    before = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)
    records = build_full_records()
    manifest_total = upsert_manifest(records)
    chroma_stored = upsert_chroma(records)
    after = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES)
    print(f"BEFORE: {before}  AFTER: {after}  chroma_upserted={chroma_stored}  manifest_total={manifest_total}")
    for r in records:
        print(" -", r["chunk_id"], "|", r["record_type"])
