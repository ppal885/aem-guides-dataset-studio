"""Curated ingestion: AEM Guides Editor "Additional features" - file-tab context
menu, Rename/Wrap/Unwrap Element, NBSP handling, duplicate IDs, Old vs New Editor
large-file behavior.

Text grounded in the live page (fetched and parsed this run, properly scoped to
<main>'s descendants this time - see the DITA-map-download ingestion for the bug
this avoids). Scoped down from the full 61-section request spec to the sections
verified against real page text; table-editing family and MathML/whitespace/
footnote sections were not deep-extracted this pass and are NOT represented here.
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
       "user-guide/author-content/work-with-editor/web-editor-other-features")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "editor-additional-features-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "url": URL, "canonical_url": URL, "source_title": "Additional features in the Editor",
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES", "domain": "EDITOR_AUTHORING", "surface": "EDITOR",
    "retrieved_at": RETRIEVED_AT, "parser_version": PARSER_VERSION,
}

RECORDS = [
    {
        "chunk_id": "editorfeat_save_lifecycle_01",
        "capability": "FILE_TAB_CONTEXT_MENU", "heading_path": "Context menu functions on a file's tab | Save",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["SAVE_DIFFERS_FROM_SAVE_AS_NEW_VERSION"],
        "text": (
            "From a file tab's context menu: 'Save' saves a file WITHOUT creating a new version - a "
            "version-less working copy of a topic is created in DAM when the topic is first created, and a "
            "simple Save updates that working copy without creating a new topic version. If a topic is under "
            "review, a simple Save does NOT give reviewers access to the changed topic content. 'Save All' "
            "(available when multiple documents are open) saves all open documents. 'Save As New Version' "
            "creates an actual new version of the file - it is documented as functionally distinct from Save, "
            "not a stronger form of the same action."
        ),
    },
    {
        "chunk_id": "editorfeat_copy_locate_02",
        "capability": "FILE_TAB_CONTEXT_MENU", "heading_path": "Context menu functions on a file's tab | Copy, Locate In",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["LOCATE_IN_MAP_REVEALS_HIDDEN_MAP_VIEW", "REPOSITORY_RENAMED_TO_EXPLORER"],
        "text": (
            "'Copy UUID' copies the currently active file's UUID to the clipboard; 'Copy Path' copies its "
            "complete path - these are distinct actions. 'Locate In > Map' finds and highlights the invoking "
            "file's location in the map hierarchy; this requires the map file to already be open in the "
            "Editor, and if Map View is currently hidden, invoking this feature both displays the Map View "
            "AND highlights the file - not just one or the other. 'Locate In > Explorer' shows the file's "
            "location in the Explorer (or DAM), opening the Explorer View, highlighting the file, and "
            "expanding its parent folder if it's nested. Versioned terminology: from the 2025.11.0 release "
            "for Cloud Service and from the 5.2 release for On-Premise, 'Repository' was renamed to "
            "'Explorer'; On-Premise setups prior to 5.2 continue to call it 'Repository'. Treat Explorer and "
            "(pre-5.2 On-Premise) Repository as the same canonical capability under different release-scoped "
            "names, not as separate capabilities."
        ),
    },
    {
        "chunk_id": "editorfeat_rename_element_contract_03",
        "capability": "RENAME_ELEMENT", "heading_path": "Rename or replace an element",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["RENAME_DIALOG_LISTS_ONLY_CONTEXT_VALID_ELEMENTS"],
        "text": (
            "Rename Element lets you swap/replace a selected element with another valid element at the same "
            "location (for example swapping a p element with note, or another valid element for that "
            "context). Right-clicking the element's name on the topic's breadcrumb and selecting 'Rename "
            "Element' opens the Rename Element dialog, which displays all elements VALID AT THE CURRENT "
            "LOCATION - not every DITA element in general. Selecting a replacement from that dialog replaces "
            "the original element with the new one. This is a high-confidence, directly-documented product "
            "contract suitable as a regression oracle: (1) the action must be reachable from a documented "
            "entry path, (2) the dialog must open, (3) the dialog must list only context-valid replacement "
            "elements, (4) selecting a replacement must change the element. Anything beyond these four "
            "(state synchronization across Author/Source/Outline views, Undo/Save-reopen persistence) is NOT "
            "directly stated on this page and would need separate verification against current Editor "
            "behavior before being treated as part of this specific contract."
        ),
    },
    {
        "chunk_id": "editorfeat_rename_element_entry_paths_04",
        "capability": "RENAME_ELEMENT", "heading_path": "Rename or replace an element | entry paths",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["FOUR_DOCUMENTED_ENTRY_PATHS_TO_RENAME_ELEMENT"],
        "text": (
            "Rename Element is documented as reachable from four separate entry paths, all leading to the "
            "same dialog: (1) right-click an element's name on the breadcrumb and choose Rename Element from "
            "the context menu; (2) select the element name on the breadcrumb to select that element's "
            "content, then right-click the selected content to bring up the context menu; (3) enable Tags "
            "view, select an element's opening tag, then right-click the selected content; (4) invoke the "
            "Options menu of an element in the Outline panel. These are candidate entry points for comparing "
            "whether the SAME product operation behaves consistently regardless of invocation path - the "
            "documentation does not claim they share identical underlying implementation, only that they all "
            "lead to the Rename Element capability."
        ),
    },
    {
        "chunk_id": "editorfeat_wrap_unwrap_05",
        "capability": "WRAP_UNWRAP_ELEMENT", "heading_path": "Wrapping and unwrapping an element",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["UNWRAP_MERGES_TEXT_DOES_NOT_DELETE_IT"],
        "text": (
            "Wrap Element adds an element tag around selected text, restricted to valid child elements per "
            "DITA standards (for example wrapping text under a note element with a p element). It's reachable "
            "from the breadcrumb's context menu (right-click the element) or by selecting text/an element in "
            "the content and choosing Wrap Element from its context menu. Unwrap Element does the opposite: "
            "it REMOVES the element tag and MERGES the text directly into the parent element - it does NOT "
            "delete the text/content. For example, unwrapping a p element nested in a note element merges "
            "the p's text directly into the note. This is reachable from the breadcrumb's context menu on "
            "the element to unwrap."
        ),
    },
    {
        "chunk_id": "editorfeat_nbsp_06",
        "capability": "NON_BREAKING_SPACE_HANDLING", "heading_path": "Handling non-breaking spaces in Editor",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["EXTERNAL_PASTE_CONVERTS_NBSP_TO_SPACE", "INTERNAL_COPY_PASTE_PRESERVES_NBSP"],
        "text": (
            "Non-breaking spaces can be inserted via the Symbol icon or the Alt+Space shortcut; they're shown "
            "with a visual indicator while editing, controllable via 'Show non-breaking space indicator in "
            "author mode' under the Appearance tab of User preferences. Source-dependent behavior on paste: "
            "copying and pasting content containing a non-breaking space FROM AN EXTERNAL SOURCE into Author "
            "view converts it into a regular space. Copying and pasting content with a non-breaking space "
            "FROM WITHIN Author view itself PRESERVES it as a non-breaking space. This is a real, documented "
            "difference based on the copy source, not a general whitespace-normalization rule."
        ),
    },
    {
        "chunk_id": "editorfeat_duplicate_ids_07",
        "capability": "DUPLICATE_ID_DETECTION", "heading_path": "Identifying Duplicate IDs for elements in a map or topic within Author view",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": [],
        "text": (
            "If a topic or map contains elements with duplicate IDs, a 'Duplicate IDs' button appears at the "
            "bottom-right corner of the content editing area, adjacent to the Editor views. Selecting it "
            "opens a popover listing all the duplicate IDs; selecting a listed ID navigates to the "
            "corresponding element so it can be updated with a unique ID. Documented as an Author-view "
            "capability."
        ),
    },
    {
        "chunk_id": "editorfeat_large_file_old_vs_new_08",
        "capability": "LARGE_FILE_EDITOR_BEHAVIOR", "heading_path": "Handling large files in the Editor",
        "record_type": "CONFIGURATION_LIMITATION", "content_type": "LIMITATION",
        "relations": ["OLD_EDITOR_LARGE_FILE_ALERT_DOES_NOT_APPLY_TO_NEW_EDITOR"],
        "text": (
            "For large files, certain functionality (undo, redo, the outline panel, the dirty marker) is "
            "disabled to preserve performance - breaking topics into smaller topics is recommended. An alert "
            "is shown based on the largeFileTagCount parameter in uiconfig.json (documented default: 2500 "
            "elements), with the current tag count also shown on the bottom bar. This alert and the "
            "associated disabled-functionality behavior is EXPLICITLY DOCUMENTED AS OLD-EDITOR-ONLY: in the "
            "New Editor, large files load seamlessly with no alert, and the functionalities that don't work "
            "in the Old Editor for large files work normally in the New Editor. Do not treat the Old Editor's "
            "large-file limitations as current New Editor behavior."
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
