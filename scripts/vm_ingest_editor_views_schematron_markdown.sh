cat > ~/aem-guides-dataset-studio/backend/ingest_editor_views_schematron_markdown.py << 'PYEOF'
"""Curated ingestion: Editor views for DITA topics, Schematron support, and
Markdown authoring - 3 official Experience League pages, kept as 3 independent
canonical documents per the task's requirement.

Text grounded in the live pages (fetched and parsed this run, main-descendants-
scoped extraction). Scoped down from the full 62-section request spec - Author
view's own capability inventory was not deep-extracted (avoided fabricating it),
Source-view shortcut table and Markdown toolbar/right-panel/references were not
extracted this pass.
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

EDITORVIEWS_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                    "user-guide/author-content/work-with-editor/web-editor-views")
SCHEMATRON_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                   "user-guide/author-content/work-with-editor/support-schematron-file")
MARKDOWN_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                "user-guide/author-content/work-with-editor/web-editor-markdown-topic")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "editorviews-schematron-markdown-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES", "domain": "EDITOR_AUTHORING", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: Editor views ----
    {
        "chunk_id": "editorviews_source_smartcatalog_01",
        "url": EDITORVIEWS_URL, "canonical_url": EDITORVIEWS_URL, "source_title": "Editor views for topics",
        "capability": "DITA_SOURCE_VIEW", "heading_path": "Editor views for topics | Source",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["SMART_CATALOG_GOVERNED_BY_DITA_CONTEXT", "TAG_REPLACEMENT_SYNCS_CLOSING_TAG"],
        "text": (
            "Source view shows the underlying XML of a DITA topic for direct editing. Smart Catalog for "
            "elements: placing the cursor at the end of an element tag and typing '<' shows a list of all "
            "VALID XML elements insertable at that location (governed by DITA context/DTD, not an arbitrary "
            "list); selecting one and typing '>' auto-inserts the closing tag. Smart Catalog for attributes: "
            "placing the cursor inside an element tag and pressing Space shows valid attributes for that "
            "element; selecting one and typing '=' auto-inserts the value quotes. Direct tag replacement: "
            "changing an opening tag (e.g. p to note) automatically updates the matching closing tag; "
            "replacing with an INVALID element immediately shows a Validation Error. This direct XML editing "
            "in Source view is a different action channel from the Rename Element dialog - they may be "
            "compared as alternate paths to a similar outcome, but are not documented as the same mechanism."
        ),
    },
    {
        "chunk_id": "editorviews_side_by_side_02",
        "url": EDITORVIEWS_URL, "canonical_url": EDITORVIEWS_URL, "source_title": "Editor views for topics",
        "capability": "DITA_SIDE_BY_SIDE_VIEW", "heading_path": "Editor views for topics | Side-by-side",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["AUTHOR_TO_SOURCE_SELECTION_SYNC_DOCUMENTED"],
        "text": (
            "Side-by-side view displays the WYSIWYG Author view and the underlying XML Source view adjacent "
            "to each other, enabling parallel content and structural editing without switching views. Both "
            "are documented as synchronized in real time. The page explicitly documents the Author-to-Source "
            "direction: cursor position and selection in Author view are reflected at the corresponding "
            "location in Source view. The reverse direction (Source selection reflected back in Author) is "
            "NOT explicitly stated on this page and should be treated as a verification candidate, not an "
            "assumed-symmetric behavior. This DITA Side-by-side (Author+Source panels) is a different panel "
            "composition from Markdown's Side-by-side (Markdown-source+rendered-preview panels) - both are "
            "called 'Side-by-side' but are not the same capability."
        ),
    },
    {
        "chunk_id": "editorviews_preview_conditional_03",
        "url": EDITORVIEWS_URL, "canonical_url": EDITORVIEWS_URL, "source_title": "Editor views for topics",
        "capability": "DITA_PREVIEW_VIEW", "heading_path": "Editor views for topics | Preview | View content based on conditional filters",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["CONDITION_DESELECT_REMOVES_FROM_PREVIEW_ONLY"],
        "text": (
            "In Preview, if a topic/map uses conditions, they appear in a Filters panel. By default ALL "
            "conditions are selected and the entire content is displayed. Deselecting a condition removes "
            "content having that condition from the Preview view (not from the underlying document). "
            "Conditionalized content can also be highlighted (documented example shows a yellow background) "
            "rather than removed. This Preview-time condition filtering is a verification/representation "
            "surface only - it is documented separately from, and should not be assumed identical to, "
            "output-preset conditional filtering, DITAVAL processing, or condition-preset publishing "
            "behavior."
        ),
    },
    {
        "chunk_id": "editorviews_track_changes_preview_04",
        "url": EDITORVIEWS_URL, "canonical_url": EDITORVIEWS_URL, "source_title": "Editor views for topics",
        "capability": "DITA_PREVIEW_VIEW", "heading_path": "Editor views for topics | Preview | View the track changes markups",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["THREE_DISTINCT_TRACKING_PREVIEW_MODES"],
        "text": (
            "When previewing a document with track-changes markups, the right panel's Tracking options offer "
            "three distinct modes: 'No Markup' - all insertions and deletions are treated as ACCEPTED, "
            "showing a simple document view with no markup visible; 'Original' - all insertions are REJECTED "
            "and all deletions are RESTORED, showing the document as it was before track changes were "
            "enabled; 'Show Markup' - insertion/deletion markups are visibly shown. These are three separate, "
            "documented preview transformations, not variations of one mode."
        ),
    },
    {
        "chunk_id": "editorviews_export_pdf_05",
        "url": EDITORVIEWS_URL, "canonical_url": EDITORVIEWS_URL, "source_title": "Editor views for topics",
        "capability": "EXPORT_ACTIVE_TOPIC_AS_PDF", "heading_path": "Editor views for topics | Preview | Export a topic as PDF",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["USES_FOLDER_PROFILE_DITA_OT_CONFIG"],
        "text": (
            "Export as PDF lets an Author, Publisher, or Administrator generate a PDF of an individual "
            "topic, using the DITA-OT configuration saved at the folder-level profile - it generates the PDF "
            "of the currently ACTIVE WORKING COPY of the topic, using the configured DITA-OT transformation "
            "name and command-line arguments, resolving key and content references first, then allows saving "
            "the output locally. To use it: open the topic in Preview mode (the topic must be part of a map "
            "file), then select 'Download as PDF'. The browser's pop-up blocker must be disabled/allowed or "
            "the PDF will not download - this is an environment/browser precondition, not a documented "
            "product defect. This individual-topic export is distinct from the Native PDF output preset and "
            "from DITA-OT map-level PDF presets - it shares an output format (PDF) but not the same workflow "
            "or scope."
        ),
    },
    # ---- SOURCE-2: Schematron ----
    {
        "chunk_id": "schematron_import_validate_06",
        "url": SCHEMATRON_URL, "canonical_url": SCHEMATRON_URL, "source_title": "Support for Schematron files",
        "capability": "SCHEMATRON_VALIDATION", "heading_path": "Support for Schematron files | Validate a DITA topic or map with Schematron",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["INVALID_SCHEMATRON_ERRORS_IN_PANEL_NOT_ADDED"],
        "text": (
            "After importing Schematron files, they can be edited in the Editor and used to validate a DITA "
            "topic or map (example rules: a map must have a title, a description of a certain length, at "
            "least one topicref). Workflow: open a topic - a Schematron Validation panel appears on the "
            "right; select the Schematron icon to open the panel; use 'Add Schematron File'. If the "
            "Schematron file has no errors, it's added and listed; if it contains errors, an error message "
            "is shown for that file INSTEAD (documented as not treated as a valid rule source). A file can "
            "be removed from the panel via a cross icon (this removes it from the current validation "
            "context, not from the repository). Selecting 'Validate' runs the added Schematron files against "
            "the topic: a success message is shown if no rule is broken, otherwise a validation error is "
            "shown, and validation results depend on the role attribute (see severity levels)."
        ),
    },
    {
        "chunk_id": "schematron_severity_savegate_07",
        "url": SCHEMATRON_URL, "canonical_url": SCHEMATRON_URL, "source_title": "Support for Schematron files",
        "capability": "SCHEMATRON_VALIDATION", "heading_path": "Support for Schematron files | Understanding validation results and severity levels",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["ROLE_CASE_SENSITIVE", "MISSING_OR_UNSUPPORTED_ROLE_DEFAULTS_TO_ERROR", "SAVE_GATE_CONTROLLED_BY_WORKSPACE_SETTING"],
        "text": (
            "Schematron validation issues are categorized as Fatal, Error, Warn, or Info, each with a "
            "visible count in the Validation panel, determined by the CASE-SENSITIVE value of the Schematron "
            "rule's 'role' attribute (documented supported values: error, info, fatal, warn - e.g. "
            "<sch:assert role=\"error\" ...>, <sch:report role=\"info\" ...>). If the role attribute is "
            "missing OR an unsupported value is used, the issue is categorized as Error by default - this "
            "applies to existing Schematron files with no role attribute too, ALL of which are grouped under "
            "Error. Save gating is controlled by the Workspace setting 'Run validation check before saving "
            "the file': when ENABLED, the file cannot be saved until Fatal or Error level issues are "
            "resolved; when DISABLED, no pre-save validation runs and the file can be saved with Fatal/Error "
            "issues present. This is distinct from a manual 'Validate' action, which runs regardless of this "
            "setting."
        ),
    },
    # ---- SOURCE-3: Markdown ----
    {
        "chunk_id": "markdown_create_08",
        "url": MARKDOWN_URL, "canonical_url": MARKDOWN_URL, "source_title": "Author Markdown documents from the Editor",
        "capability": "MARKDOWN_AUTHORING", "heading_path": "Author Markdown documents from the Editor | Create a Markdown topic",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["UUID_FILENAME_SETTING_HIDES_NAME_FIELD", "REQUIRES_MARKDOWN_TEMPLATE_IN_FOLDER_PROFILE"],
        "text": (
            "To create a Markdown topic: in the Repository panel, choose Topic from the New/Options dropdown, "
            "then in the New topic dialog provide: Title (topic title); Name (auto-suggested from Title - "
            "NOT DISPLAYED if the administrator has enabled automatic UUID-based file names); Template "
            "(select 'Markdown' from the dropdown - the 'Topic' template type is selected by default, "
            "Markdown is a template choice within it, not a separate top-level New-File entity); Path "
            "(defaults to the currently-selected repository folder, but can be browsed/changed). Selecting "
            "Create opens the new Markdown topic for editing. On an upgraded environment, the Markdown "
            "template must be added to the active folder profile before it can be used - a missing template "
            "after upgrade is a folder-profile configuration issue to check first, not necessarily an Editor "
            "defect."
        ),
    },
    {
        "chunk_id": "markdown_views_09",
        "url": MARKDOWN_URL, "canonical_url": MARKDOWN_URL, "source_title": "Author Markdown documents from the Editor",
        "capability": "MARKDOWN_AUTHORING", "heading_path": "Author Markdown documents from the Editor | Source, Side-by-side, and Preview modes",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["MARKDOWN_HAS_NO_AUTHOR_VIEW", "PREVIEW_RETAINS_SAVE_LOCK_PROPERTIES_ACTIONS"],
        "text": (
            "Markdown authoring supports exactly three viewing modes: Source (raw markdown code view - save "
            "revision, insert headings/table/image, etc.), Side-by-side (a Source panel showing the raw "
            "markdown next to a Preview panel showing real-time rendered output - two DIFFERENT panels than "
            "DITA's Side-by-side, which pairs Author+XML-Source, not markdown-source+rendered-preview), and "
            "Preview (shows how the topic renders to an end viewer; ALL editing features are removed from "
            "the toolbar, but Save as new version, Lock/unlock, and the File properties panel remain "
            "accessible). There is NO documented 'Markdown Author view' - do not invent one; Author view is "
            "a DITA-topic-only concept."
        ),
    },
    {
        "chunk_id": "markdown_limitations_10",
        "url": MARKDOWN_URL, "canonical_url": MARKDOWN_URL, "source_title": "Author Markdown documents from the Editor",
        "capability": "MARKDOWN_AUTHORING", "heading_path": "Author Markdown documents from the Editor | Feature limitations",
        "record_type": "CONFIGURATION_LIMITATION", "content_type": "LIMITATION",
        "relations": ["FEATURES_NOT_APPLICABLE_TO_MARKDOWN_SCOPE_ONLY"],
        "text": (
            "Documented as currently NOT APPLICABLE for Markdown authoring specifically: Review, Merge, AI "
            "Assistant, and Track changes. This limitation is scoped to Markdown authoring only - it does "
            "not mean these features are removed from DITA topic authoring in general. This is a current, "
            "currentness-tracked documentation statement, not a permanent architectural limitation; a future "
            "documentation update could supersede it."
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
cd ~/aem-guides-dataset-studio/backend && python3 ingest_editor_views_schematron_markdown.py
