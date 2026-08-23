cat > ~/aem-guides-dataset-studio/backend/ingest_citations_datasource_git_docstate.py << 'PYEOF'
"""Curated ingestion: Citations, Data Sources/Content Snippet/Topic Generators,
Git Connector, and Document States - 4 official Experience League pages, kept as
4 independent canonical documents per the task's requirement.

Text grounded in the live pages (fetched and parsed this run, main-descendants-
scoped extraction). Notable finding: the request spec's "Citation Unique ID,
immutable" claim and "Auto Sync cannot be disabled" claim could NOT be verified
against the actual page content (no such fields/sections exist on either page as
fetched) - both are deliberately left out rather than fabricated.
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

CITATIONS_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                  "user-guide/author-content/work-with-editor/web-editor-apply-citations")
DATASOURCE_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                   "user-guide/author-content/work-with-editor/web-editor-content-snippet")
GITCONNECTOR_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                     "user-guide/author-content/work-with-editor/web-editor-git-connector")
DOCSTATES_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                  "user-guide/author-content/work-with-editor/web-editor-document-states")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "citations-datasource-git-docstate-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES", "domain": "EDITOR_AUTHORING", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: Citations ----
    {
        "chunk_id": "citations_add_identifier_style_01",
        "url": CITATIONS_URL, "canonical_url": CITATIONS_URL, "source_title": "Add and manage citations in your content",
        "capability": "CITATION_MANAGEMENT", "heading_path": "Add citations | Change citation style",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["SEARCH_BY_OPTIONS_VARY_BY_SOURCE_TYPE", "STYLE_CONTROLLED_BY_ADMIN_SETTINGS"],
        "text": (
            "Adding a citation: from the Citations panel (left panel icon), choose 'New citation' to open "
            "the Add Citation dialog. Fields vary by source type (Book, Website, Journal). Identifier-based "
            "lookup varies by source type too: Book supports searching by ISBN or DOI; Website supports DOI; "
            "Journal supports DOI or PubMed ID, or 'Any field' (searches across Title/Journal title/Author/"
            "Year/Volume/Number/Pages, returning the closest match); a 'Parse citation' option can parse a "
            "supported AMA citation and auto-populate fields. Entering an identifier auto-populates the "
            "other citation fields. Citation style (documented examples exist but are not treated as a fixed "
            "eternal list here) is configured by the system administrator via the Citations dropdown in the "
            "General tab of Settings, and determines how citations render in the preview pane and in Native "
            "PDF output."
        ),
    },
    {
        "chunk_id": "citations_import_02",
        "url": CITATIONS_URL, "canonical_url": CITATIONS_URL, "source_title": "Add and manage citations in your content",
        "capability": "CITATION_MANAGEMENT", "heading_path": "Import citations",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["IMPORT_DEDUPES_BY_UNIQUE_AND_NOT_ALREADY_PRESENT", "IMPORT_LIMITED_TO_BOOK_JOURNAL_WEBSITE"],
        "text": (
            "Citations can be imported from a .bib file (a BibTeX Bibliographical Database file) via the "
            "Citations panel's Import option. AEM Guides imports ONLY citations that are unique and not "
            "already present (the exact internal matching key - e.g. metadata comparison vs an identifier - "
            "is not stated by this page and should not be assumed). Import currently supports citations from "
            "Book, Journal, or Website sources only - other source types are not documented as supported for "
            "import."
        ),
    },
    # ---- SOURCE-2: Data sources / generators ----
    {
        "chunk_id": "datasource_snippet_generator_options_03",
        "url": DATASOURCE_URL, "canonical_url": DATASOURCE_URL, "source_title": "Use data from your data source",
        "capability": "CONTENT_SNIPPET_GENERATOR", "heading_path": "Insert a content snippet from your data source | Options for a content snippet generator",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["INSERT_ONLY_WHILE_EDITING_TOPIC", "DUPLICATE_ADDS_DEFAULT_SUFFIX"],
        "text": (
            "Right-clicking a content snippet generator opens Options: Preview (opens a pane showing a "
            "fraction of how the data would render in output); Insert (inserts the selected content snippet "
            "into the topic currently open for editing - the inserted data remains editable as a snippet; "
            "the Insert option appears ONLY while a topic is being edited, not otherwise); Edit (modify and "
            "save the generator's own configuration); Delete (removes the generator itself); Duplicate "
            "(creates a copy with a default suffix, documented example 'generator_1' - not an eternal exact "
            "naming algorithm)."
        ),
    },
    {
        "chunk_id": "datasource_topic_generator_options_04",
        "url": DATASOURCE_URL, "canonical_url": DATASOURCE_URL, "source_title": "Use data from your data source",
        "capability": "TOPIC_GENERATOR", "heading_path": "Create a topic using the topic generator | Options for a topic generator",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "LIFECYCLE",
        "relations": ["GENERATE_DISABLED_WHILE_RUNNING", "VIEW_LOG_ENABLED_AFTER_GENERATION", "EXISTING_TOPIC_OVERWRITE_OR_NEW_VERSION"],
        "text": (
            "Right-clicking a topic generator opens Options: 'Generate' generates topics for that generator "
            "(also usable to update existing topics by re-fetching from the data source) - while generation "
            "is running, this option is DISABLED and a loader is shown; if the target topic file already "
            "exists, you can choose to overwrite the data or save it as a new version (two distinct, not "
            "merged, outcomes). 'View Log' opens the content generation log in a new tab (shows errors, "
            "warnings, information, exceptions) - this option is only ENABLED once content has actually been "
            "generated for that generator. This generation log is a different artifact from output-"
            "generation logs, Git import logs, or Health Check reports."
        ),
    },
    # ---- SOURCE-3: Git Connector ----
    {
        "chunk_id": "gitconnector_key_features_05",
        "url": GITCONNECTOR_URL, "canonical_url": GITCONNECTOR_URL, "source_title": "Import content using Git connector",
        "capability": "GIT_CONNECTOR", "heading_path": "Key features",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["RESYNC_PRESERVES_GUID_FOR_CROSS_REFERENCES", "INCREMENTAL_SYNC_TRACKS_LAST_COMMIT"],
        "text": (
            "Git Connector pulls content from any Git repository (public or private) into AEM Guides. "
            "Content ingestion: can filter by source-folder path to ingest a single subdirectory instead of "
            "the whole repo; uses a gitignore-aware rule engine to skip files matched by .gitignore or "
            "custom exclusion rules (excluded files are not import failures); PRESERVES GUIDs ON RE-SYNC "
            "specifically to keep existing DITA cross-references intact after an update - a real, documented "
            "invariant, not assumed. Incremental (delta) sync: tracks the last-synced commit and, on "
            "subsequent syncs, fetches only files added/modified/deleted since then (not a full re-import); "
            "produces a delta report listing every changed file and its change type before import; fetch "
            "time stays consistent regardless of repository size (see the separate performance-benchmarks "
            "data, which is scoped to a documented full non-incremental bulk-import benchmark on Cloud "
            "Service - not a universal SLA)."
        ),
    },
    {
        "chunk_id": "gitconnector_pipeline_06",
        "url": GITCONNECTOR_URL, "canonical_url": GITCONNECTOR_URL, "source_title": "Import content using Git connector",
        "capability": "GIT_CONNECTOR", "heading_path": "How Git Connector works",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["FOUR_STAGE_PIPELINE"],
        "text": (
            "Git Connector moves content through four documented stages: (1) Crawl and sync - a crawler "
            "connects to the configured Git repository/profile and syncs content into the connector on "
            "demand; (2) Ingest and detect conflicts - incoming files are hashed against existing AEM "
            "Guides content; files with no conflicting changes move through automatically, conflicting ones "
            "are flagged for manual resolution; (3) Persist - resolved content is processed and saved into "
            "AEM alongside other content; (4) AEM Guides workflow - once persisted, the content is available "
            "for authoring, review, translation, and publishing like any other AEM Guides content. This is "
            "the documented product architecture, not a claim about internal class/service ordering beyond "
            "these four stages."
        ),
    },
    {
        "chunk_id": "gitconnector_manage_content_07",
        "url": GITCONNECTOR_URL, "canonical_url": GITCONNECTOR_URL, "source_title": "Import content using Git connector",
        "capability": "GIT_CONNECTOR", "heading_path": "Manage Git-imported content",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["DELETE_IMPORTER_DOES_NOT_DOCUMENT_CONTENT_DELETION"],
        "text": (
            "Managing imported content offers: Preview (with a Refetch option if the source has updates, or "
            "a link to conflict resolution if merging is required); Delete (removes an importer that's no "
            "longer needed - the page describes removing the IMPORTER, not the already-imported AEM content; "
            "whether deleting the importer also deletes previously-imported content is NOT established by "
            "this page and should be treated as unknown, not assumed either way); Rename (renames the "
            "importer for identification); View log (import operation details); View Report (a downloadable "
            "Bulk import report with total imported files, successful imports, and failed imports counts - "
            "distinct from the delta-sync change report - plus a 'Retry failed imports' action for files "
            "that failed)."
        ),
    },
    {
        "chunk_id": "gitconnector_threeway_merge_08",
        "url": GITCONNECTOR_URL, "canonical_url": GITCONNECTOR_URL, "source_title": "Import content using Git connector",
        "capability": "GIT_CONNECTOR", "heading_path": "Review and resolve content conflicts",
        "record_type": "STATE_MACHINE", "content_type": "WORKFLOW",
        "relations": ["THREE_WAY_MERGE_PANE_IDENTITY", "RESULT_INITIALIZED_FROM_AEM_CONTENT"],
        "text": (
            "Re-fetching (via Bulk importer > Refetch) surfaces differences as conflicts; conflicting/"
            "non-conflicting changes are distinguished - a 'Merge required' tab lists only the files with "
            "actual conflicts (clean, non-conflicting updates do not require this manual merge step). For a "
            "conflicting file, a three-way merge view shows: LEFT pane (AEM) = current AEM repository "
            "content; RIGHT pane (GIT) = incoming content from the remote Git repository; MIDDLE pane "
            "(Result) = the merge editor, INITIALIZED FROM the AEM content, where the final merged result is "
            "produced. This is a different merge mechanism from any generic Editor file-merge feature - it "
            "is specific to Git Connector conflict resolution."
        ),
    },
    # ---- SOURCE-4: Document states ----
    {
        "chunk_id": "docstates_profile_and_multidoc_09",
        "url": DOCSTATES_URL, "canonical_url": DOCSTATES_URL, "source_title": "Document state",
        "capability": "DOCUMENT_LIFECYCLE", "heading_path": "Types of document states",
        "record_type": "STATE_MACHINE", "content_type": "BEHAVIOR",
        "relations": ["STATES_ARE_PROFILE_DRIVEN_NOT_FIXED", "MULTI_DOCUMENT_USES_COMMON_ALLOWED_STATES"],
        "text": (
            "A document's available states (documented examples: Draft, In-Review, Reviewed, Ready to "
            "Publish - not a universal fixed list) are defined by its Document State profile, which also "
            "defines allowed transitions; a document has exactly one current state at a time. States are set "
            "manually or automatically per the profile (e.g. a profile might set new documents to Draft, and "
            "move a document to In-Review automatically when a review task starts). For MULTIPLE selected "
            "documents, the allowed target state is the COMMON (intersected) state allowed across ALL "
            "selected documents, not the union. Worked example from the source: given ordered states Draft, "
            "In-Review, Reviewed, Ready to Publish, if one.dita is in Draft and two.dita is in Reviewed, "
            "selecting both together only allows changing to 'Ready to Publish' (the only state both "
            "documents can individually transition to)."
        ),
    },
    {
        "chunk_id": "docstates_assets_ui_admin_10",
        "url": DOCSTATES_URL, "canonical_url": DOCSTATES_URL, "source_title": "Document state",
        "capability": "DOCUMENT_LIFECYCLE", "heading_path": "Change document state from the Assets UI",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["ADMIN_CAN_SET_ANY_STATE_REGULAR_USERS_LIMITED"],
        "text": (
            "From Assets UI: select one or more documents, select Properties in the main toolbar, choose a "
            "new state from the Document State dropdown (limited to states the profile's State Transition "
            "section allows), then Save & Close. Administrators are documented as an exception: they can "
            "view ALL document states and change a document to ANY possible state, not just the "
            "profile-restricted transitions a regular user sees. The Assets UI card view separately displays "
            "a document's current state alongside its creation date and size (a display surface, distinct "
            "from the editing surface)."
        ),
    },
    {
        "chunk_id": "docstates_ddlc_approval_11",
        "url": DOCSTATES_URL, "canonical_url": DOCSTATES_URL, "source_title": "Document state",
        "capability": "DOCUMENT_LIFECYCLE", "heading_path": "Use document states in DDLC",
        "record_type": "STATE_MACHINE", "content_type": "LIFECYCLE",
        "relations": ["APPROVAL_CREATES_VERSION_AND_READ_ONLY", "START_NEW_RELEASE_RETURNS_TO_DRAFT"],
        "text": (
            "Document states help control DDLC (document development lifecycle) editability - e.g. allowing "
            "edits in Draft/In-Review but preventing further changes once reviewed and ready to publish. The "
            "'Mark Approved' feature (from the Editor) is used once a document reaches its ready-to-publish "
            "or penultimate state: marking it approved CREATES A NEW VERSION of the document AND makes it "
            "READ-ONLY; the approved document can then be used for publishing or to create a baseline. To "
            "resume editing, an author uses 'Start New Release' on an approved document, which CHANGES THE "
            "DOCUMENT STATE BACK TO DRAFT and makes it editable again for the next release cycle. This "
            "approval/release lifecycle is a distinct operation from an ordinary manual state change (which "
            "just relabels the state without the version-creation/read-only/re-editable side effects)."
        ),
    },
]


def build_full_records() -> list[dict]:
    out = []
    for r in RECORDS:
        content = r["text"]
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        rec = {**COMMON, **{k: v for k, v in r.items() if k != "text"}, "id": r["chunk_id"],
               "content": content, "checksum": checksum, "title": r["source_title"]}
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
PYEOF
cd ~/aem-guides-dataset-studio/backend && python3 ingest_citations_datasource_git_docstate.py
