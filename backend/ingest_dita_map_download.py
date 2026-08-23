"""Curated ingestion: AEM Guides DITA map download workflows (Editor + Map
dashboard/console), packaging options, async queue lifecycle, Inbox retention.

Text grounded in the live page (fetched and parsed this run). Note: an initial
extraction attempt using find_all_next() without scoping to <main>'s descendants
picked up left-nav sidebar junk instead of real content - fixed before building
these chunks, so this file reflects the corrected, verified extraction.
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

URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
       "user-guide/author-content/map-editor/authoring-download-assets")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "ditamap-download-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "url": URL, "canonical_url": URL, "source_title": "Download files",
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES", "domain": "CONTENT_MANAGEMENT",
    "capability_family": "DOWNLOAD_ASSETS", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    {
        "chunk_id": "ditamapdl_editor_workflow_01",
        "capability": "DOWNLOAD_DITA_MAP_FROM_EDITOR", "heading_path": "Download a DITA map file from the Editor",
        "record_type": "DOCUMENTED_UI_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["EDITOR_DOWNLOAD_VARIANT_OF_DOWNLOAD_WITH_DEPENDENCIES"],
        "text": (
            "To download a DITA map file from the Editor: navigate to the DITA map, select it to open it "
            "in the Editor, then in the Map view select the Options icon and choose 'Download map' - this "
            "opens the Download Map dialog. In this dialog you can choose: 'Use baseline' (select a Baseline "
            "from a dropdown to download the map and its contents based on that specific Baseline); file "
            "hierarchy options 'Retain file hierarchy' (keeps the existing folder structure) or 'Flatten "
            "file hierarchy' (puts all referenced topics and media in a single folder); and, per hierarchy "
            "choice, file name options 'Use GUID file name' or 'Use actual file name'. You can also download "
            "without selecting any option, in which case the last persisted version of the referenced topics "
            "and media files is downloaded."
        ),
    },
    {
        "chunk_id": "ditamapdl_mapconsole_workflow_02",
        "capability": "DOWNLOAD_DITA_MAP_FROM_MAP_DASHBOARD_OR_CONSOLE",
        "heading_path": "Download a DITA map file from the Map dashboard",
        "canonical_surface": "DITA_MAP_CONSOLE", "source_labels": "Map dashboard|DITA map console",
        "record_type": "DOCUMENTED_UI_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["MAPCONSOLE_DOWNLOAD_VARIANT_OF_DOWNLOAD_WITH_DEPENDENCIES"],
        "text": (
            "The section heading on this page is 'Download a DITA map file from the Map dashboard', but the "
            "documented steps say to select the DITA map to open it in the 'DITA map console' - the source "
            "uses both terms for what appears to be the same surface; treat 'Map dashboard' and 'DITA map "
            "console' as source-documented aliases of one canonical surface, not confirmed-identical or "
            "confirmed-different without further evidence. Steps: in the Assets UI, navigate to the DITA "
            "map, select it to open it in DITA map console, select the Topics tab to view the map's topics, "
            "then in the main toolbar select 'Download Map' to open the Download Map dialog. There, select "
            "Download; documented options here are 'Use Baseline' and 'Flatten File Hierarchy' - this "
            "section does NOT explicitly document a 'Retain file hierarchy' option or GUID/actual filename "
            "options the way the Editor section does. You can also download without selecting any option, "
            "in which case the last persisted version of referenced topics and media is downloaded."
        ),
    },
    {
        "chunk_id": "ditamapdl_option_parity_03",
        "capability": "DOWNLOAD_DITA_MAP_WITH_DEPENDENCIES", "heading_path": "Editor vs Map dashboard option parity",
        "record_type": "CONFIGURATION_LIMITATION", "content_type": "LIMITATION",
        "relations": ["EDITOR_AND_MAPCONSOLE_OPTIONS_NOT_CONFIRMED_IDENTICAL"],
        "text": (
            "The Editor download workflow documents: Use baseline, Retain file hierarchy, Flatten file "
            "hierarchy, Use GUID file name, Use actual file name, and duplicate-filename suffix handling. "
            "The Map dashboard/DITA map console download workflow documents only: Use Baseline and Flatten "
            "File Hierarchy. An option documented for one surface but not mentioned for the other (for "
            "example Retain file hierarchy, or the GUID/actual filename choice, on the Map dashboard/console "
            "side) should be treated as NOT_ESTABLISHED_FOR_OTHER_SURFACE by this source - not as proven "
            "unsupported there. Do not assume the two download entry points have identical option sets or "
            "identical underlying implementation without further evidence."
        ),
    },
    {
        "chunk_id": "ditamapdl_duplicate_filename_04",
        "capability": "DOWNLOAD_DITA_MAP_FROM_EDITOR", "heading_path": "Download a DITA map file from the Editor | file name options",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["FILENAME_COLLISION_RESOLVED_BY_NUMERIC_SUFFIX"],
        "text": (
            "This behavior is documented specifically for the Editor download workflow with Flatten file "
            "hierarchy AND Use actual file name selected together: when downloaded files would collide "
            "(duplicate file names in the map), the duplicates are automatically resolved by appending "
            "numeric suffixes (_2, _3, and so on) to produce unique downloaded file names. This is scoped "
            "strictly to this combination (DITA map download + flattened hierarchy + actual file names) - it "
            "is a different mechanism from AEM Sites output filename sanitization (which replaces disallowed "
            "characters with underscores, not numeric suffixes for duplicates) and should not be generalized "
            "to other download or rename operations."
        ),
    },
    {
        "chunk_id": "ditamapdl_queue_notification_inbox_05",
        "capability": "DOWNLOAD_DITA_MAP_WITH_DEPENDENCIES", "heading_path": "Download a DITA map file from the Map dashboard | queue and notification",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "LIFECYCLE",
        "relations": ["DOWNLOAD_REQUEST_QUEUED_BEFORE_READY", "DOWNLOAD_LATER_USES_NOTIFICATION_INBOX"],
        "text": (
            "Selecting Download does not immediately return a file - the map download request is queued "
            "first. Once the map package is ready, a notification is generated; from that notification you "
            "can select 'Download' to download the map file immediately in .zip format, or 'Download Later' "
            "to download at a later time. If you choose Download Later, the download link is accessible from "
            "the Adobe Experience Manager notification Inbox - selecting the generated map notification there "
            "downloads the map in .zip format. By default, downloaded maps remain available in the AEM "
            "notification Inbox for five days - this is documented as a default retention period, not stated "
            "as a fixed, unchangeable, or universal SLA, and the source does not describe exact expiration/"
            "deletion mechanics after that period."
        ),
    },
    {
        "chunk_id": "ditamapdl_metadata_file_06",
        "capability": "DOWNLOAD_DITA_MAP_WITH_DEPENDENCIES", "heading_path": "Download a DITA map file from the Editor | downloaded content",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "EXAMPLE",
        "relations": ["METADATA_FILE_PRESENT_IN_BOTH_HIERARCHY_MODES"],
        "text": (
            "Once a map is downloaded, you can select it and use the 'Open' icon to open the downloaded "
            "content. To view the associated metadata of the downloaded map, open the file the documentation "
            "names literally as 'metdata.json' (this exact spelling is what the live page states verbatim - "
            "it may be a documentation typo for 'metadata.json' or may reflect the actual shipped filename; "
            "this has NOT been verified against current product/code evidence and should not be silently "
            "corrected). This file is documented as available for both file hierarchy options - Flatten file "
            "hierarchy and Retain file hierarchy."
        ),
    },
    {
        "chunk_id": "ditamapdl_no_option_default_07",
        "capability": "DOWNLOAD_DITA_MAP_WITH_DEPENDENCIES", "heading_path": "Default download behaviour (no options selected)",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["NO_OPTION_DOWNLOADS_LAST_PERSISTED_VERSION"],
        "text": (
            "Documented identically for both the Editor and the Map dashboard/DITA map console download "
            "workflows: you can download the map file without selecting any option (no Baseline, no "
            "hierarchy/filename choice). In that case, the LAST PERSISTED VERSION of the referenced topics "
            "and media files is downloaded. The source uses this exact phrase - do not substitute 'latest "
            "saved draft', 'latest repository revision', 'latest Baseline', or 'latest published version' as "
            "if they were confirmed equivalent; only 'last persisted version' is what this page states."
        ),
    },
]


def build_full_records() -> list[dict]:
    out = []
    for r in RECORDS:
        content = r["text"]
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        rec = {**COMMON, **{k: v for k, v in r.items() if k != "text"}, "id": r["chunk_id"],
               "content": content, "checksum": checksum, "title": COMMON["source_title"]}
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
    tmp_path = MANIFEST_PATH.with_suffix(".json.tmp")
    encoder = json.JSONEncoder(indent=2)
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for piece in encoder.iterencode(merged):
            f.write(piece)
    tmp_path.replace(MANIFEST_PATH)
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
        meta = {k: v for k, v in r.items() if k != "content"}
        for k, v in list(meta.items()):
            if isinstance(v, list):
                meta[k] = "|".join(v)
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
        print(" -", r["chunk_id"], "|", r["capability"])
