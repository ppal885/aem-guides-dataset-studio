"""Curated ingestion: Conditional Attributes + Condition Presets + Global/Folder
Profile Output Presets + Output Variables + DITA-OT Metadata + Old/New Map
Collection output generation - 7 official Experience League pages, kept as 7
independent canonical documents.

Text grounded in the live pages (fetched and parsed this run, main-descendants-
scoped extraction). Notable findings preserved rather than normalized:
- The condition-preset page has a Map console section AND a Map dashboard section
  with DIFFERENT default-action semantics and DIFFERENT duplicate-name defaults
  (_1 vs _Duplicate); the page also mixes "Map dashboard"/"DITA map console"
  terminology and contains a "Seledt" typo. Kept distinct, not merged.
- The variables page renders ${path_after_langfolder} with escaped underscores in
  the example; the canonical variable name has a plain underscore.
- The command-line root-map-metadata deprecation section (Guides 2502) was NOT
  separately extracted this pass and is intentionally left out rather than
  asserted from memory.
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

B = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/"
U_CONDPRESETS = B + "conditional-content/generate-output-use-condition-presets"
U_CONDPROF = B + "conditional-content/generate-output-conditional-attribute-profiling"
U_OUTPRESETS = B + "web-editor-manage-output-presets"
U_VARIABLES = B + "generate-output-use-variables"
U_DITAOT = B + "pass-metadata-dita-ot"
U_MAPCOLL_OLD = B + "generate-output-use-map-collection-output-generation"
U_MAPCOLL_NEW = B + "generate-output-use-new-map-collection-output-generation"

RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "condpresets-outputgen-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_CONTRACT",
    "product": "AEM_GUIDES", "domain": "MAP_MANAGEMENT_AND_PUBLISHING",
    "retrieved_at": RETRIEVED_AT, "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-2: Conditional attribute profiling ----
    {"chunk_id": "condprof_scope_01", "url": U_CONDPROF, "canonical_url": U_CONDPROF,
     "source_title": "Conditional attribute profiling", "capability": "CONDITIONAL_ATTRIBUTE_PROFILING",
     "heading_path": "Conditional attribute profiling", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["GLOBAL_SCOPE", "FOLDER_SCOPE", "DEFINED_VIA_FOLDER_PROFILES"],
     "text": ("Conditional attributes let you tag DITA content so publishing can include or exclude it (for "
              "example Windows vs Mac content). They are defined at the global level or the folder level: "
              "globally defined conditions are visible across ALL projects, while folder-specific conditions "
              "are visible ONLY in projects created within the specified folder. They are configured via the "
              "Adobe Experience Manager logo > Tools > Guides > Folder Profiles tile > select a Folder Profile "
              "> Conditional Attributes tab > Edit > Add. Note: the global profile CANNOT be edited from this "
              "Folder Profile flow (the source establishes only that this documented flow cannot edit it - it "
              "does not say the global profile has no conditions).")},
    {"chunk_id": "condprof_value_label_02", "url": U_CONDPROF, "canonical_url": U_CONDPROF,
     "source_title": "Conditional attribute profiling", "capability": "CONDITIONAL_ATTRIBUTE_PROFILING",
     "heading_path": "Conditional attribute profiling | Name, Value, Label",
     "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["NAME_VALUE_LABEL", "EDITOR_SHOWS_VALUE", "PUBLISHER_SHOWS_LABEL", "NAME_ONLY_NOT_USABLE"],
     "text": ("A conditional attribute has a Name, a Value, and a Label. You CAN save a profile with only the "
              "attribute Name - but the attribute can only be USED once it has a Value specified. If you specify "
              "BOTH a Value and a Label: the Web Editor shows only the VALUE of the attribute, while the LABEL is "
              "shown to the publishing administrator at the time of creating a condition preset (documented "
              "example: attribute 'platform', value 'unix', label 'Red Hat Linux'). One attribute may have "
              "multiple value/label pairs (add more via the + icon). After saving, an author can view the "
              "attribute's values in the Properties tab in the Editor. Value and Label are distinct - do not use "
              "the label as the stored DITA attribute value.")},

    # ---- SOURCE-1: Condition presets (Map console vs Map dashboard) ----
    {"chunk_id": "condpresets_purpose_03", "url": U_CONDPRESETS, "canonical_url": U_CONDPRESETS,
     "source_title": "Use condition presets", "capability": "CONDITION_PRESET_MANAGEMENT",
     "heading_path": "Use condition presets", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["TWO_SURFACES_MAP_CONSOLE_AND_MAP_DASHBOARD", "CONSUMED_BY_OUTPUT_PRESET"],
     "text": ("A condition preset specifies what happens to a conditional attribute in the final output (for "
              "example include version 1.0 and exclude version 2.0). Condition presets can be created in two "
              "ways: from the Map console, and from the Map dashboard. These are two DISTINCT surfaces with "
              "different behavior (see the separate chunks). A saved condition preset is later selected inside an "
              "Output preset to generate the conditional output - condition preset creation is separate from "
              "output preset creation.")},
    {"chunk_id": "condpresets_mapconsole_create_04", "url": U_CONDPRESETS + "#condition-presets-from-the-map-console",
     "canonical_url": U_CONDPRESETS, "source_title": "Use condition presets",
     "capability": "MAP_CONSOLE_CONDITION_PRESET", "heading_path": "Use condition presets | Condition presets from the map console | Create",
     "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
     "relations": ["NAME_VALIDATION", "HYPHEN_UNDERSCORE_ALLOWED"],
     "text": ("Map console condition preset creation: open the DITA map in Map console > Condition presets (left) "
              "> + icon > New condition preset dialog > enter a unique name > Create. Name validation: you get an "
              "error if the name is empty, contains an invalid character, or equals an existing condition preset "
              "name. A hyphen '-' or underscore '_' is allowed as a separator (the complete valid-character "
              "pattern is not established by the source).")},
    {"chunk_id": "condpresets_mapconsole_attrs_05", "url": U_CONDPRESETS + "#condition-presets-from-the-map-console",
     "canonical_url": U_CONDPRESETS, "source_title": "Use condition presets",
     "capability": "MAP_CONSOLE_CONDITION_PRESET", "heading_path": "Use condition presets | Condition presets from the map console | Add attributes",
     "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["ATTRIBUTES_FROM_MAP_REFERENCES", "DEFAULT_ACTION_INCLUDE", "ACTIONS_INCLUDE_EXCLUDE_PASSTHROUGH_FLAG"],
     "text": ("In the Map console preset editor, the Attributes panel shows all the attributes added to any "
              "references present in the map (this is the map's used conditions - not necessarily every profile "
              "conditional attribute). The right panel shows only the conditions already added to the selected "
              "preset. You add conditions by: selecting one or more attributes (adds all their values), selecting "
              "one or more attribute values, dragging an attribute/value pair to the center, or Select all; then "
              "Add moves the items to the right panel. By default the action for a newly added attribute is "
              "Include. The available actions are Include, Exclude, Passthrough, and Flag, changeable per row or "
              "in bulk. Formal DITA processing semantics of these actions come from DITAVAL/conditional-"
              "processing, not this page.")},
    {"chunk_id": "condpresets_mapconsole_dup_delete_06", "url": U_CONDPRESETS + "#condition-presets-from-the-map-console",
     "canonical_url": U_CONDPRESETS, "source_title": "Use condition presets",
     "capability": "MAP_CONSOLE_CONDITION_PRESET", "heading_path": "Use condition presets | Condition presets from the map console | Rename/Duplicate/Delete",
     "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["MAP_CONSOLE_DUPLICATE_DEFAULT_NAME_UNDERSCORE_1"],
     "text": ("Map console preset management (hover a preset > Options): Rename changes the preset name; Duplicate "
              "opens a dialog whose documented default name is '<selected condition preset name>_1' (editable); "
              "Delete removes the selected preset. The '_1' default belongs to the Map CONSOLE surface. Behavior "
              "for output presets that already reference a renamed/deleted condition preset is not established by "
              "the source.")},
    {"chunk_id": "condpresets_mapdashboard_07", "url": U_CONDPRESETS + "#condition-presets-from-the-map-dashboard",
     "canonical_url": U_CONDPRESETS, "source_title": "Use condition presets",
     "capability": "MAP_DASHBOARD_CONDITION_PRESET", "heading_path": "Use condition presets | Condition presets from the Map dashboard",
     "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["DASHBOARD_DEFAULT_ACTION_APPLIES_TO_ALL", "MAP_DASHBOARD_COPY_DEFAULT_NAME_UNDERSCORE_DUPLICATE", "TERMINOLOGY_INCONSISTENCY"],
     "text": ("The Map DASHBOARD condition-preset flow is DIFFERENT from the Map console. Create > Name Condition "
              "> 'Set default action to' (Include / Exclude / Passthrough / Flag). Crucially, on the Map "
              "dashboard the selected default action applies to ALL conditional attributes whether or not they "
              "were added to the preset - documented example: with 15 condition attributes and 4 added, choosing "
              "Exclude as default applies Exclude to all 15. This is NOT the Map console behavior (where added "
              "rules default to Include and only added rules are affected). The Map dashboard copy action's "
              "documented default name is '<selected condition preset name>_Duplicate' (note: different from the "
              "Map console's '_1'). DATA-QUALITY: the page mixes 'Map dashboard' and 'DITA map console' "
              "terminology within these steps, and contains the typo 'Seledt' - preserved, not corrected.")},

    # ---- SOURCE-3: Global/Folder Profile output presets ----
    {"chunk_id": "outpresets_role_propagation_08", "url": U_OUTPRESETS, "canonical_url": U_OUTPRESETS,
     "source_title": "Manage Global and Folder Profile output presets", "capability": "PROFILE_LEVEL_OUTPUT_PRESET",
     "heading_path": "Manage Global and Folder Profile output presets", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
     "relations": ["FOLDER_ADMIN_ONLY", "ADD_TO_FOLDER_PROFILE", "PROPAGATES_TO_RELATED_MAPS", "MAP_INDEPENDENT"],
     "text": ("Global and Folder Profile output presets are available ONLY to folder-level administrative users. "
              "Create one by opening the DITA map (Edit Topics) > Open in map console > Output presets tab > + > "
              "enter Type, Name, Target (for Knowledgebase) > select the 'Add to folder profile' check box > Add. "
              "The preset then appears under the Output presets tab of ALL related maps, marked with a "
              "folder-profile icon. A profile-level preset is INDEPENDENT of any individual map, so map-specific "
              "configurations are NOT present in it - do not assume all preset fields are identical between a "
              "map-specific preset and a profile-level preset.")},
    {"chunk_id": "outpresets_ops_defaultpdf_09", "url": U_OUTPRESETS, "canonical_url": U_OUTPRESETS,
     "source_title": "Manage Global and Folder Profile output presets", "capability": "PROFILE_LEVEL_OUTPUT_PRESET",
     "heading_path": "Manage Global and Folder Profile output presets | Options", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["OPERATIONS", "DEFAULT_PDF_DRIVES_DOWNLOAD_AS_PDF"],
     "text": ("Options-menu operations on a profile-level output preset: Generate output, View output, View log, "
              "Rename, Duplicate, Delete, and Default PDF. Default PDF sets an existing PDF preset as THE default "
              "PDF preset - it is then used by the 'Download as PDF' option for a map. Default PDF is distinct "
              "from ordinary preset enablement. Note: the documented deletion propagation is that deleting a "
              "profile-level preset removes it from the Output preset lists of all related maps; the source does "
              "not state that previously generated outputs or logs are deleted.")},

    # ---- SOURCE-4: Output variables ----
    {"chunk_id": "variables_overview_10", "url": U_VARIABLES, "canonical_url": U_VARIABLES,
     "source_title": "Use variables in output paths and file names", "capability": "OUTPUT_VARIABLE_RESOLUTION",
     "heading_path": "Use variables for Destination Path/Site path/Site Name/File Name", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "REFERENCE",
     "relations": ["TARGET_FIELDS_DESTINATION_SITE_SITENAME_PDFNAME", "SINGLE_OR_COMBINATION"],
     "text": ("When generating AEM Sites or PDF output you can use variables to define the Destination Path, Site "
              "path, AEM Site Name, or PDF File Name. A single variable or a combination of variables may define "
              "a target field's value. Not every variable is valid in every target field (see the restriction "
              "chunk).")},
    {"chunk_id": "variables_matrix_11", "url": U_VARIABLES, "canonical_url": U_VARIABLES,
     "source_title": "Use variables in output paths and file names", "capability": "OUTPUT_VARIABLE_RESOLUTION",
     "heading_path": "Use variables ... | Variable table", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "REFERENCE",
     "relations": ["MAP_FILENAME", "MAP_TITLE", "PRESET_NAME", "LANGUAGE_CODE", "SYSTEM_DATE", "SYSTEM_TIME", "MAP_METADATA"],
     "text": ("Out-of-the-box output variables and their source values: ${map_filename} = the DITA map file name; "
              "${map_title} = the DITA map title; ${preset_name} = the output preset name; ${language_code} = the "
              "language folder in the map's path (documented example resolves to 'en'); ${system_date} = the "
              "current SERVER date; ${system_time} = the current SERVER time (server time, not client/browser "
              "time); ${<map_metadata_property>} such as ${dc:title} = a property under the map/bookmap "
              "jcr:content metadata. The source does not define a fallback when a title or metadata property is "
              "missing - do not invent one. Example formats are examples, not immutable contracts.")},
    {"chunk_id": "variables_restrictions_12", "url": U_VARIABLES, "canonical_url": U_VARIABLES,
     "source_title": "Use variables in output paths and file names", "capability": "OUTPUT_VARIABLE_RESOLUTION",
     "heading_path": "Use variables ... | Restrictions", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "REFERENCE",
     "relations": ["MAP_PARENTPATH_RESTRICTED", "PATH_AFTER_LANGFOLDER_RESTRICTED", "ESCAPED_UNDERSCORE_DATA_QUALITY"],
     "text": ("Two variables carry an explicit documented restriction: ${map_parentpath} (the complete parent path "
              "of the map) CANNOT be used to specify the AEM Site Name or the PDF File Name; and "
              "${path_after_langfolder} (the map path after the language folder) also CANNOT be used to specify "
              "the AEM Site Name or the PDF File Name. DATA-QUALITY: the source renders "
              "${path_after_langfolder} with escaped underscores in its example (path\\_after\\_langfolder); the "
              "canonical variable name has plain underscores: path_after_langfolder. Variable substitution and "
              "final output-path validation are separate concerns - the source does not establish sanitization "
              "of spaces or unsupported characters (for example ${preset_name} may contain spaces).")},

    # ---- SOURCE-5: DITA-OT metadata ----
    {"chunk_id": "ditaot_flow_13", "url": U_DITAOT, "canonical_url": U_DITAOT,
     "source_title": "Pass on the metadata to the output using DITA-OT", "capability": "DITA_OT_OUTPUT_METADATA",
     "heading_path": "Pass metadata using DITA-OT", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
     "relations": ["OUTPUT_TYPES_AEM_PDF_HTML5_EPUB_CUSTOM", "MAP_CONSOLE_SAVE_VS_MAP_DASHBOARD_DONE", "ONLY_SELECTED_PASSED"],
     "text": ("You can pass metadata to AEM, PDF, HTML5, EPUB, and Custom outputs using DITA-OT publishing - the "
              "output preset must be created using the DITA-OT option. Two surfaces: Map console (open the map in "
              "Map console > open the DITA-OT output preset > File properties dropdown > select properties > Save "
              "> Generate output) and Map dashboard / Assets UI (select the map > Edit output preset > select "
              "DITA-OT > Properties dropdown > select properties > Done > Generate output). Only the SELECTED "
              "metadata properties are passed to the DITA-OT output; unselected properties are not passed. Map "
              "console 'Save' and Map dashboard 'Done' are distinct persistence actions - do not merge them.")},
    {"chunk_id": "ditaot_defaults_metadatalist_14", "url": U_DITAOT, "canonical_url": U_DITAOT,
     "source_title": "Pass on the metadata to the output using DITA-OT", "capability": "DITA_OT_OUTPUT_METADATA",
     "heading_path": "Pass metadata using DITA-OT | Default properties and metadataList", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
     "relations": ["DEFAULT_PROPERTIES", "METADATALIST_LIBS_PATH", "METADATALIST_APPS_OVERLAY", "CUSTOM_PROPERTY_DEPENDENCY"],
     "text": ("The File properties dropdown lists both default and custom properties. The four DEFAULT properties "
              "are dc:description, dc:language, dc:title, and docstate, picked from the metadataList file at "
              "/libs/fmdita/config/metadataList. This file can be overlaid at /apps/fmdita/config/metadataList "
              "(customize under apps, not libs). These four are not the only supported properties. To pass a "
              "CUSTOM property it must have its value defined, be available in the metadata list, and be selected "
              "in the preset. Note: 'docstate' as a metadata property is not the same as the Document State "
              "lifecycle without additional evidence.")},

    # ---- SOURCE-6: Legacy Map Collection ----
    {"chunk_id": "mapcoll_old_create_16", "url": U_MAPCOLL_OLD, "canonical_url": U_MAPCOLL_OLD,
     "source_title": "Use Map Collection for output generation", "capability": "LEGACY_MAP_COLLECTION",
     "heading_path": "Use Map Collection for output generation | Create and add maps", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
     "relations": ["AUTO_ADDS_PRESETS_AND_LOCALES", "NEW_PRESET_DISABLED_BY_DEFAULT", "ENABLE_INDIVIDUAL_ALL_FOLDERPROFILE"],
     "text": ("Legacy Map Collection: from AEM Guides Home (or Assets UI) > Map Collections > Create > Collection "
              "Title > open collection > Edit > Add Maps. When a DITA map is added, ALL presets and locales "
              "associated with that map are added AUTOMATICALLY; the user then enables/disables desired outputs. "
              "Any NEW preset is DISABLED by default in the collection. Enablement paths: enable an individual "
              "preset, Enable All presets for a map, or enable all folder-profile presets for a map. Adding a map "
              "does not by itself enable all its associated presets. (This automatic preset/locale association is "
              "specific to the Legacy collection - the New Map Collection instead uses an explicit Fetch presets "
              "action.)")},
    {"chunk_id": "mapcoll_old_delete_cancel_17", "url": U_MAPCOLL_OLD, "canonical_url": U_MAPCOLL_OLD,
     "source_title": "Use Map Collection for output generation", "capability": "LEGACY_MAP_COLLECTION",
     "heading_path": "Use Map Collection for output generation | Delete/Remove/Cancel", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["REMOVE_MAP_NOT_DELETE_ASSET", "CANCEL_VIA_OUTPUTS_TAB"],
     "text": ("Delete a map collection: select it on the Map Collection page > Delete. Remove a map from a "
              "collection: open the collection in Edit mode > select the map > Remove From Collection - this also "
              "removes any presets or locales associated with that map FROM THE COLLECTION, but does NOT delete "
              "the underlying DITA map asset. Cancel an output task: open the collection's Outputs tab > the "
              "publish task > Cancel This Job icon (same idea as cancelling from the map console or Publish "
              "Dashboard).")},

    # ---- SOURCE-7: New Map Collection ----
    {"chunk_id": "mapcoll_new_consolidation_18", "url": U_MAPCOLL_NEW, "canonical_url": U_MAPCOLL_NEW,
     "source_title": "Use New map collection for output generation", "capability": "NEW_MAP_COLLECTION",
     "heading_path": "Use New map collection for output generation", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["CONSOLIDATES_OLD_COLLECTION_AND_BULK_PUBLISHING", "RELEASE_ENABLEMENT_GATED", "SEPARATE_GENERATE_AND_PUBLISH"],
     "text": ("The New map collection consolidates functionality previously spread across the OLD map collection "
              "and BULK PUBLISHING into a single unified interface: once enabled you manage maps, presets, "
              "generation history, publishing history, metadata, and collection membership from one place. It is "
              "a newer, deployment/release/enablement-gated capability (verify the applicable Cloud release and "
              "Customer Success enablement before treating a missing New map collection UI as a regression). It "
              "is NOT an alias of the Legacy Map Collection, and its existence does not by itself mean the Legacy "
              "collection is removed or deprecated.")},
    {"chunk_id": "mapcoll_new_history_translations_19", "url": U_MAPCOLL_NEW, "canonical_url": U_MAPCOLL_NEW,
     "source_title": "Use New map collection for output generation", "capability": "NEW_MAP_COLLECTION",
     "heading_path": "Use New map collection ... | History and translations", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["GENERATED_HISTORY_VS_PUBLISHED_HISTORY", "TRANSLATIONS_TOGGLE", "DEFAULT_LANGUAGE_FALLBACK"],
     "text": ("The New map collection tracks generation and publishing SEPARATELY: hovering the collection title "
              "exposes 'Generate history' (Generated history tab - maps with generated outputs) and 'Publish "
              "history' (Published history tab - maps with published output), plus Rename. When adding maps, "
              "enabling the 'Select available translations' toggle automatically adds all available translation "
              "copies of each map; if a map has NO translation copies, the DEFAULT LANGUAGE is added/displayed. "
              "Generated history and Published history are distinct - do not merge Last generated with Last "
              "published. (This translations toggle is distinct from the Legacy collection's automatic locale "
              "association.)")},
    {"chunk_id": "mapcoll_new_fetchpresets_20", "url": U_MAPCOLL_NEW, "canonical_url": U_MAPCOLL_NEW,
     "source_title": "Use New map collection for output generation", "capability": "NEW_MAP_COLLECTION",
     "heading_path": "Use New map collection ... | Fetch presets", "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
     "relations": ["FETCH_PRESETS", "FOLDER_PROFILE_PRESETS_COMMON", "OTHER_PRESETS_PER_MAP"],
     "text": ("In the New map collection you must explicitly FETCH presets: select the required maps (or all) > "
              "Fetch presets > it retrieves the available presets for the selected maps, grouped as 'Folder "
              "profile presets' and 'Other presets'. Folder profile presets are COMMON to all the selected maps; "
              "Other presets are SPECIFIC to individual maps (the associated map is shown next to each toggle). "
              "You can Enable all presets or Enable all folder profile presets, and use a Filter (preset types, "
              "map status). Do not assume all map-specific presets are identical across maps.")},

    # ---- Cross-capability semantic distinctions (retrieval anchor) ----
    {"chunk_id": "outputgen_semantic_distinctions_21", "url": U_CONDPRESETS, "canonical_url": U_CONDPRESETS,
     "source_title": "Conditional publishing - semantic distinctions", "capability": "SEMANTIC_DISAMBIGUATION",
     "heading_path": "Conditional publishing | Semantic distinctions", "record_type": "REFERENCE", "content_type": "REFERENCE",
     "relations": ["DISAMBIGUATION"],
     "text": ("Key distinctions across AEM Guides conditional publishing and output generation (do not conflate): "
              "a Conditional Attribute (defined in a Folder/Global Profile) is NOT a Condition Preset (assigns "
              "actions to conditions) is NOT an Output Preset (defines a publish output) is NOT a DITAVAL file. A "
              "condition Value is not its Label. A Global-profile condition is not a Folder-profile condition. A "
              "map-specific output preset is not a profile-level output preset. Default PDF is not any PDF "
              "preset. An output Variable (path/name substitution) is not DITA-OT metadata passthrough, and "
              "DITA-OT metadata is not Native-PDF metadata. The Legacy Map Collection is not the New Map "
              "Collection; Generated history is not Published history; Generate is not Publish to; and (in the "
              "New collection status model) Finished-with-errors is a distinct state from Failed.")},
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
    with open(tmp_path, "w", encoding="utf-8", newline="\n") as f:
        for piece in json.JSONEncoder(indent=2).iterencode(merged):
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
