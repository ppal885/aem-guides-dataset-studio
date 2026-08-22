cat > ~/aem-guides-dataset-studio/backend/ingest_aemsites_config_and_profiles.py << 'PYEOF'
"""Curated ingestion: DITA element mapping, HTML tag overlay, output filename
sanitization, and global/folder-level profiles - 4 official Experience League pages.

Text grounded in the live pages (fetched and parsed this run). Folder Profiles is
ingested as ONE canonical document with heading-scoped section records for its
three aliased anchors (apply-preset-changes, conditional-attributes, xml-editor)
plus base sections - not four duplicate full-document embeddings.
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

RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "aemsites-config-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

ELEMENTMAPPING_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                      "install-conf-guide/output-gen-config/conf-aem-sites-output/customize-dita-element-mapping-aem-components")
HTMLOVERLAY_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                    "install-conf-guide/output-gen-config/conf-aem-sites-output/overlay-html-tags-aem-sites-on-prem")
FILENAME_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                "install-conf-guide/output-gen-config/conf-aem-sites-output/conf-file-names-valid-regx-aem-site-output")
PROFILES_CANONICAL_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                           "install-conf-guide/global-folder-profiles/conf-profiles")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE",
    "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES",
    "domain": "CONFIGURATION",
    "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: DITA element mapping ----
    {
        "chunk_id": "aemsites_elementmapping_lookup_order_01",
        "url": ELEMENTMAPPING_URL, "canonical_url": ELEMENTMAPPING_URL,
        "source_title": "Customize DITA element mapping with AEM components",
        "capability": "DITA_ELEMENT_COMPONENT_MAPPING", "heading_path": "elementmapping.xml structure",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["ELEMENT_NAME_MATCH_PRECEDES_CLASS_MATCH"],
        "text": (
            "DITA elements in AEM Guides are mapped to AEM components via elementmapping.xml, used in "
            "workflows such as publishing and review. Lookup order: every DITA element is first searched "
            "for a component mapping based on the element NAME. If no name match is found, a match on the "
            "DITA CLASS is done instead (e.g. a <task> element with no direct mapping falls back to the "
            "<topic> class mapping because task is inherited from topic). Element-name matching precedes "
            "class-based fallback matching - not the reverse."
        ),
    },
    {
        "chunk_id": "aemsites_elementmapping_composite_standalone_02",
        "url": ELEMENTMAPPING_URL, "canonical_url": ELEMENTMAPPING_URL,
        "source_title": "Customize DITA element mapping with AEM components",
        "capability": "DITA_ELEMENT_COMPONENT_MAPPING", "heading_path": "elementmapping.xml structure | DITA element schema",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["COMPOSITE_CONTINUES_CHILD_PROCESSING", "STANDALONE_STOPS_CHILD_PROCESSING"],
        "text": (
            "Once an element has a component mapping, its <type> value determines child-element processing: "
            "COMPOSITE means element-to-component mapping continues for child elements as well; STANDALONE "
            "means child elements of the current element are NOT mapped further - the component for that "
            "element is responsible for rendering all its child content itself. The elementmapping.xml schema "
            "also defines: <attributeprop> (serializes a DITA attribute's value to an AEM node property), "
            "<textprop> (serializes the element's text content to a node property), <xmlprop> (serializes the "
            "ENTIRE XML markup of the element to a node property, for custom rendering), <xpath> (an "
            "additional matching condition), <target> (placement context, e.g. head|para), <wrapelement> and "
            "<wrapclass> (the Wrapper component's generated enclosing HTML tag and class, used for simple "
            "container-only DITA constructs instead of writing a dedicated component), and <skip> "
            "(true|false, excludes an element from mapping/processing). textprop and xmlprop are distinct: "
            "one captures rendered text, the other captures full markup for the consuming component to "
            "re-render."
        ),
    },
    {
        "chunk_id": "aemsites_elementmapping_path_resolution_03",
        "url": ELEMENTMAPPING_URL, "canonical_url": ELEMENTMAPPING_URL,
        "source_title": "Customize DITA element mapping with AEM components",
        "capability": "DITA_ELEMENT_COMPONENT_MAPPING", "heading_path": "elementmapping.xml structure | attributemap",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["ISPATH_TRUE_TRIGGERS_PATH_RESOLUTION", "REL_SOURCE_DIFFERS_FROM_REL_TARGET"],
        "text": (
            "In an <attributemap> entry, setting ispath=\"true\" on an attribute mapping (e.g. href to "
            "fileReference) makes output generation resolve that value as a path before storing it, rather "
            "than copying it as-is. HOW it resolves is controlled by the rel attribute: rel=\"source\" "
            "resolves the value relative to the DITA source file currently being processed; rel=\"target\" "
            "resolves the value relative to the root publish location. These are genuinely different base "
            "paths, not interchangeable. If ispath is not specified at all, the value is copied as-is with "
            "no pre-processing/resolution, leaving resolution to the consuming component."
        ),
    },
    {
        "chunk_id": "aemsites_elementmapping_customization_lifecycle_04",
        "url": ELEMENTMAPPING_URL, "canonical_url": ELEMENTMAPPING_URL,
        "source_title": "Customize DITA element mapping with AEM components",
        "capability": "DITA_ELEMENT_COMPONENT_MAPPING", "heading_path": "elementmapping.xml structure | Additional notes",
        "record_type": "CONFIGURATION_LIMITATION", "content_type": "LIMITATION",
        "relations": ["CUSTOMIZATION_SHOULD_USE_NEW_FILE_NOT_EDIT_DEFAULT", "PARTIAL_MAPPING_OVERRIDE_SUPPORTED"],
        "text": (
            "The default elementmapping.xml is accessed via /libs/fmdita/config/elementmapping.xml (On-"
            "Premise CRXDE Lite) or the package manager (Cloud Service). Adobe recommends NOT editing the "
            "default file directly to override mappings - instead create a new mapping XML file, preferably "
            "under a custom apps folder, and it does not need to replicate the entire default file: only the "
            "overridden mappings need to be defined in it (partial override is supported). Separately, large "
            "serialized property content is not kept as a String JCR property: when content exceeds a "
            "threshold (default 512 bytes), the property type is changed to binary. This threshold is "
            "configurable via the Configuration Manager (com.adobe.fmdita.config.ConfigManager), the 'Save "
            "as Binary Threshold' setting - a current configurable default, not a fixed architectural limit."
        ),
    },
    # ---- SOURCE-2: HTML tag overlay ----
    {
        "chunk_id": "aemsites_htmloverlay_workflow_01",
        "url": HTMLOVERLAY_URL, "canonical_url": HTMLOVERLAY_URL,
        "source_title": "Overlay HTML tags in AEM Sites output for On-Premise",
        "capability": "HTML_TAG_SECURITY_OVERLAY", "heading_path": "Overlay HTML tags in AEM Sites output for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["DEFAULT_XSS_CONFIG_IN_LIBS", "CUSTOM_OVERLAY_IN_APPS", "DISTINCT_FROM_ELEMENT_MAPPING"],
        "text": (
            "On-Premise AEM Sites output (core-components-mapped, generated via the AEM Sites preset) "
            "supports adding/customizing accepted HTML tags and attributes (for example video and image-map "
            "tags) by overlaying the XSS-protection config.xml file. The default configuration lives at "
            "/libs/fmdita/cq/xssprotection/config.xml. To customize it: create an overlay node of the "
            "xssprotection folder under /apps, then edit the config at /apps/fmdita/config/config.xml (never "
            "the /libs default directly) and update the tag/attribute entries for videos and images there. "
            "This is a DIFFERENT configuration surface from elementmapping.xml: elementmapping.xml decides "
            "which AEM component a DITA element maps to; this XSS-overlay config.xml decides which HTML "
            "tags/attributes the generated output is allowed to contain. A question about which component a "
            "DITA element maps to should not be answered from this XSS-overlay evidence, and a question "
            "about which HTML tags/attributes are permitted should not be answered from elementmapping.xml."
        ),
    },
    # ---- SOURCE-3: filename sanitization ----
    {
        "chunk_id": "aemsites_filename_sanitization_01",
        "url": FILENAME_URL, "canonical_url": FILENAME_URL,
        "source_title": "Configure valid file names for AEM Site output",
        "capability": "AEM_SITES_OUTPUT_FILENAME_SANITIZATION", "heading_path": "Configure valid file names for AEM Site output",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["DISALLOWED_CHAR_REPLACED_WITH_UNDERSCORE"],
        "text": (
            "AEM Guides can be configured with a list of valid file-name characters for AEM Site OUTPUT "
            "specifically (a separate capability from DITA source-topic filename validation, generated-"
            "artifact fallback naming, or URL slug generation for other outputs). Characters not allowed in "
            "a URL (documented examples: ' < > ` @ $) are automatically converted to an underscore \"_\" when "
            "found while generating AEM Site output filenames. Configured via the same 'Configuration "
            "overrides' mechanism for both Cloud Service and On-Premise setups, with: PID/config class "
            "com.adobe.fmdita.common.SanitizeNodeNameImpl, property key aemsite.DisallowedFileNameChars, "
            "whose value lists the characters to replace with an underscore in generated AEM Site output "
            "filenames. Note: the source page presents Cloud and On-Premise as tabs under one shared "
            "Configuration-overrides procedure using the same PID/property - it does not document a "
            "separately-named On-Premise-only bundle/setting distinct from this PID, contrary to an initial "
            "assumption that they use different identifiers."
        ),
    },
    # ---- SOURCE-4: Folder Profiles (ONE canonical document, section-scoped) ----
    {
        "chunk_id": "aemsites_profiles_overview_01",
        "url": PROFILES_CANONICAL_URL, "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "capability": "GLOBAL_AND_FOLDER_LEVEL_PROFILES", "heading_path": "Configure global or folder-level profiles",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "OVERVIEW",
        "relations": [],
        "text": (
            "Different groups/products in an enterprise may need different authoring templates, output "
            "presets, conditional-attribute profiles, and Editor configurations. AEM Guides lets you "
            "configure these at an enterprise (global) level and/or at a folder level, so authors only see "
            "templates/profiles relevant to their group instead of everything configured globally. Folders "
            "configured within a folder-level profile share access to the templates/output presets defined "
            "in that profile."
        ),
    },
    {
        "chunk_id": "aemsites_profiles_override_vs_merge_02",
        "url": PROFILES_CANONICAL_URL, "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "capability": "GLOBAL_AND_FOLDER_LEVEL_PROFILES", "heading_path": "Configure global or folder-level profiles | Configure global profile",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["FOLDER_OVERRIDES_GLOBAL_FOR_TEMPLATES_PRESETS_EDITOR", "CONDITIONAL_ATTRIBUTES_MERGE_NOT_OVERRIDE"],
        "text": (
            "A folder-level profile OVERRIDES the settings configured in the global profile for templates, "
            "output presets, and XML Editor settings: if a folder has a folder-level profile, it shows only "
            "that folder profile's templates/output presets/Editor settings, not the global profile's. "
            "CONDITIONAL ATTRIBUTES ARE THE EXCEPTION: this override rule does NOT apply to them - "
            "folder-level conditional attributes are MERGED with the globally-defined conditional attributes, "
            "not replaced by them. This is the single most important distinction on this page: override "
            "semantics apply to templates/presets/Editor config, merge semantics apply to conditional "
            "attributes - they must not be treated as the same inheritance rule."
        ),
    },
    {
        "chunk_id": "aemsites_profiles_templates_03",
        "url": PROFILES_CANONICAL_URL, "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "canonical_document_note": PROFILES_CANONICAL_URL, "section_anchor": "id1889D0IL0Y4",
        "capability": "PROFILE_CONFIGURATION", "heading_path": "Configure global or folder-level profiles | Configure templates",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": [],
        "text": (
            "Out-of-the-box topic templates available for a profile: Glossary, Reference Topic, Concept, "
            "Task, Troubleshooting, Blank, and DITAVAL. Any existing template (including OOTB ones) can be "
            "used as a base to create a new custom template. The Blank DITA template specifically contains "
            "no predefined structure or elements, unlike the other OOTB templates."
        ),
    },
    {
        "chunk_id": "aemsites_profiles_apply_preset_changes_04",
        "url": PROFILES_CANONICAL_URL + "#id18AGD0K0OHS", "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "section_anchor": "id18AGD0K0OHS", "section_aliases": [PROFILES_CANONICAL_URL + "#id18AGD0K0OHS"],
        "capability": "APPLY_PROFILE_PRESET_CHANGES_TO_EXISTING_MAPS", "heading_path": "Configure global or folder-level profiles | Apply preset changes",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["OVERWRITE_ON_RISKS_BASELINE_AND_CONDITIONAL_PRESET_LOSS", "OVERWRITE_OFF_PRESERVES_EXISTING_MAPS"],
        "text": (
            "Updating a profile's output presets does not automatically change existing DITA maps - you must "
            "explicitly click 'Apply Preset Changes' in the main toolbar to propagate updated presets to "
            "existing maps. In the Apply Preset Changes dialog: selecting 'Overwrite Existing Preset' means "
            "any updates you made to the existing output presets will overwrite the preset settings on ALL "
            "existing DITA maps using that preset - but doing so will ALSO result in the loss of any existing "
            "conditional-preset and baseline information associated with those maps (a real, documented "
            "destructive side effect, not a minor note). NOT selecting 'Overwrite Existing Preset' means "
            "updates to existing presets do not impact existing maps' current preset settings, while newly "
            "added presets ARE still made available to existing maps. This apply operation is explicit, not "
            "a continuous background sync."
        ),
    },
    {
        "chunk_id": "aemsites_profiles_conditional_attributes_05",
        "url": PROFILES_CANONICAL_URL + "#id1889D0I305Z", "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "section_anchor": "id1889D0I305Z", "section_aliases": [PROFILES_CANONICAL_URL + "#id1889D0I305Z"],
        "capability": "CONDITIONAL_ATTRIBUTE_CONFIGURATION", "heading_path": "Configure global or folder-level profiles | Configure conditional attributes",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["NAME_ONLY_SAVEABLE_BUT_NOT_USABLE_AS_CONDITION"],
        "text": (
            "Conditional attributes are configured (Guides > Folder Profiles > a profile tile > Conditional "
            "Attributes tab) with a Name, a Value, and a Label. A profile CAN be saved with only the "
            "attribute Name populated - Value and Label are not mandatory to save. However, an attribute "
            "without a Value is not documented as usable as an actual filtering condition; Value and Label "
            "are needed for the attribute to function as a condition and to have a label shown in applicable "
            "UI. Configuration can be done in the Global Profile or a folder-level profile."
        ),
    },
    {
        "chunk_id": "aemsites_profiles_xml_editor_06",
        "url": PROFILES_CANONICAL_URL + "#id2065G300O5Z", "canonical_url": PROFILES_CANONICAL_URL,
        "source_title": "Configure global or folder-level profiles",
        "section_anchor": "id2065G300O5Z", "section_aliases": [PROFILES_CANONICAL_URL + "#id2065G300O5Z"],
        "capability": "XML_EDITOR_CONFIGURATION", "heading_path": "Configure global or folder-level profiles | Configure and customize the XML Editor",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["CLOUD_USES_JSON_EXTENSION_WORKFLOW"],
        "text": (
            "The XML Editor Configuration tab lets an administrator control which Editor features are "
            "exposed to authors and change the Editor's look-and-feel, configured per Cloud Service or "
            "On-Premise setup (documented as separate tabs/procedures). For Cloud Service: administrators "
            "create JSON extensions reflecting changes made in ui_config.json, uploadable independently at "
            "the folder-profile level; when a change is made to the XML Editor Configuration (e.g. updating "
            "a button), the system identifies the difference and the 'Convert UI Config to JSON' button "
            "generates the corresponding extension. This is documented as an XML Editor UI Configuration "
            "capability distinct from XML Editor page-layout/CSS and from snippets/version-label "
            "configuration, which are separate configuration families on the same page."
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
cd ~/aem-guides-dataset-studio/backend && python ingest_aemsites_config_and_profiles.py
