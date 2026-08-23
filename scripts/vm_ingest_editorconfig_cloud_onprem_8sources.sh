#!/usr/bin/env bash
# Paste this whole block into the VM terminal.
set -e
cd ~/aem-guides-dataset-studio/backend

cat > ingest_editorconfig_cloud_onprem_8sources.py << 'PYEOF'
"""Curated ingestion: 8 official Experience League pages covering Cloud and
On-Premise AEM Guides Editor configuration - single-topic DITA-OT PDF,
translation entry point, pasted table mapping, health check presets (Cloud),
new editor enablement, special characters, check-in/check-out labels, and
query LimitReads (On-Premise). Kept as 8 independent canonical documents (none
is an anchor alias of another) with Cloud (sources 1-4) and On-Premise
(sources 5-8) deployment ownership kept distinct throughout.

Text grounded in the live pages (fetched and parsed this run). Notable
findings deliberately flagged rather than silently normalized:
- The pasted-tables page's default/configured table-format code blocks
  render "simpletable", "tgroup", and a third literal "trgoup" adjacent to
  each other in the raw extracted source - preserved as a likely
  documentation typo, not a separate table type. The specific claim that
  "merged rows/columns force tgroup regardless of the simpletable
  preference" could NOT be independently confirmed in this page's actual
  text as fetched and is marked NOT_ESTABLISHED rather than asserted.
- The check-in/check-out page's code snippet shows the existing dynamic
  title being replaced is literally "@checkOutBy" (not a plain "Lock"/
  "Check-in" default string) - preserved verbatim as source evidence.
- No source-title spelling irregularity was found on the fetched
  check-in/check-out page's actual H1 text; the request spec's "source
  title typo" claim could not be verified against the live page and is
  therefore NOT asserted here.
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

BASE_CLOUD = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/editor-configs/editor-cloud-settings"
BASE_ONPREM = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/editor-configs/editor-on-prem-settings"

PDF_URL = f"{BASE_CLOUD}/conf-pdf-generation-dita-ot"
TRANSLATION_URL = f"{BASE_CLOUD}/conf-translation-editor"
PASTED_TABLES_URL = f"{BASE_CLOUD}/conf-pasted-tables"
HEALTH_CHECK_URL = f"{BASE_CLOUD}/conf-health-check-preset"
NEW_EDITOR_URL = f"{BASE_ONPREM}/conf-new-editor-on-prem"
SPECIAL_CHARS_URL = f"{BASE_ONPREM}/conf-additional-special-characters"
CHECKIN_CHECKOUT_URL = f"{BASE_ONPREM}/conf-checkin-checkout-title"
LIMITREADS_URL = f"{BASE_ONPREM}/conf-query-limitreads"

RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "editorconfig-cloud-onprem-8sources-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_CONTRACT",
    "product": "AEM_GUIDES", "domain": "EDITOR_CONFIGURATION", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: Single-topic DITA-OT PDF (Cloud) ----
    {
        "chunk_id": "editorcfg_topic_pdf_native_vs_legacy_01",
        "url": PDF_URL, "canonical_url": PDF_URL,
        "source_title": "Configure single topic PDF generation for Cloud Service",
        "capability": "SINGLE_TOPIC_PDF_GENERATION", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure single topic PDF generation for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["NATIVE_PDF_CURRENT_DEFAULT", "LEGACY_DITA_OT_TOPIC_PDF_OPTIONAL", "TOPIC_PDF_VS_MAP_PDF"],
        "text": (
            "AEM Guides can generate a PDF for an individual topic or an entire map file, "
            "using either the Native PDF method or the DITA-OT method. Native PDF is the "
            "documented current default, generating a feature-rich PDF based on W3C CSS3 and "
            "CSS paged-media standards. The DITA-OT method is documented as used to generate a "
            "PDF output for a MAP from the Map dashboard - this is TOPIC_PREVIEW_DITA_OT_PDF vs "
            "MAP_DASHBOARD_DITA_OT_PDF vs NATIVE_PDF: three distinct source-content-scope / "
            "publishing-engine combinations that must not be merged just because all three "
            "produce a PDF. This page documents how to re-enable the OLDER (legacy) DITA-OT PDF "
            "generation option specifically from the topic PREVIEW mode - it is not the current "
            "default and is not the map-level DITA-OT PDF workflow."
        ),
    },
    {
        "chunk_id": "editorcfg_topic_pdf_config_chain_02",
        "url": PDF_URL, "canonical_url": PDF_URL,
        "source_title": "Configure single topic PDF generation for Cloud Service",
        "capability": "SINGLE_TOPIC_PDF_GENERATION", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure single topic PDF generation for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["GLOBAL_PROFILE_XML_EDITOR_CONFIG_UI_CONFIG_JSON", "FOLDER_PROFILE_SELECTION_REQUIRED"],
        "text": (
            "To enable the legacy DITA-OT topic-preview PDF action: log in as administrator, go "
            "to Tools > Guides > Folder Profiles, open the Global Profile tile, select the XML "
            "Editor Configuration tab, click Edit, then Download to get ui_config.json; locate "
            "the button block with icon 'filePDF', title 'Download as PDF', on-click "
            "'EDITOR_SAVE_AS_PDF' and replace it with a block using title 'Export as PDF', "
            "on-click 'DOWNLOAD_TOPIC_PDF', and a show condition of ['@isPreviewMode', "
            "'@isXmlMode']; save and upload the file. Critically, the documentation states this "
            "action then appears ONLY 'if you choose the same folder profile from User "
            "Preferences in the Editor' - i.e. FOLDER_PROFILE_SELECTION in User Preferences "
            "controls whether the configured PDF action becomes visible in a given user's topic "
            "preview, even after the configuration itself has been saved/uploaded. Saving the "
            "configuration is not by itself sufficient for UI visibility; the applicable profile "
            "must also be the one selected by the user."
        ),
    },
    {
        "chunk_id": "editorcfg_topic_pdf_button_config_snippets_03",
        "url": PDF_URL, "canonical_url": PDF_URL,
        "source_title": "Configure single topic PDF generation for Cloud Service",
        "capability": "SINGLE_TOPIC_PDF_GENERATION", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure single topic PDF generation for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["ACTION_EDITOR_SAVE_AS_PDF", "ACTION_DOWNLOAD_TOPIC_PDF"],
        "text": (
            "Exact source configuration snippets (ui_config.json button block), preserved as "
            "UI-configuration implementation evidence, not automatically a formal user-facing "
            "acceptance criterion. ORIGINAL/DEFAULT: {\"component\": \"button\", \"variant\": "
            "\"action\", \"quiet\": true, \"icon\": \"filePDF\", \"title\": \"Download as PDF\", "
            "\"on-click\": \"EDITOR_SAVE_AS_PDF\"}. REPLACEMENT (enables legacy DITA-OT topic "
            "PDF): {\"component\": \"button\", \"icon\": \"filePDF\", \"variant\": \"action\", "
            "\"quiet\": true, \"title\": \"Export as PDF\", \"on-click\": "
            "\"DOWNLOAD_TOPIC_PDF\", \"show\": [\"@isPreviewMode\", \"@isXmlMode\"]}. The "
            "show condition scopes the replacement button to preview mode and XML mode only."
        ),
    },
    # ---- SOURCE-2: Translation entry point (Cloud) ----
    {
        "chunk_id": "editorcfg_translation_manage_tab_default_04",
        "url": TRANSLATION_URL, "canonical_url": TRANSLATION_URL,
        "source_title": "Configure Translation feature in the Editor for Cloud Service",
        "capability": "EDITOR_TRANSLATION_ENTRY_POINT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure Translation feature in the Editor for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["MANAGE_TAB_DEFAULT_VISIBLE", "UI_ENTRY_POINT_NOT_BACKEND_CONTRACT"],
        "text": (
            "The Editor's Manage tab is the documented UI entry point used to translate content "
            "into multiple languages, and is AVAILABLE BY DEFAULT. This page documents the "
            "Manage-tab UI entry point only - it does not by itself establish the complete "
            "translation backend enablement contract (translation APIs, map-console translation "
            "availability, or existing translation project state are separate concerns not "
            "addressed here)."
        ),
    },
    {
        "chunk_id": "editorcfg_translation_hide_manage_tab_05",
        "url": TRANSLATION_URL, "canonical_url": TRANSLATION_URL,
        "source_title": "Configure Translation feature in the Editor for Cloud Service",
        "capability": "EDITOR_TRANSLATION_ENTRY_POINT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure Translation feature in the Editor for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["COMPONENT_TAB_ID_WORKFLOW_TITLE_MANAGE", "ACTION_APP_MODE_CHANGE"],
        "text": (
            "To hide the Manage tab: log in as administrator, go to Tools > Guides > Folder "
            "Profiles > Global Profile > XML Editor Configuration, click Edit, download "
            "ui_config.json, then REMOVE this exact block: {\"component\":\"tab\", "
            "\"id\":\"workflow\", \"title\":\"Manage\", \"on-click\":\"APP_MODE_CHANGE\", "
            "\"items\":[{\"component\":\"label\",\"label\":\"Manage\"}]}, then upload the "
            "updated file. The page's own concluding sentence after this procedure reads: 'Note "
            "that the Manage filter is no longer available' - using the term 'Manage filter' "
            "where the rest of the page consistently says 'Manage tab'. "
            "POTENTIAL_TERMINOLOGY_INCONSISTENCY: preserve both raw literals ('Manage tab' and "
            "'Manage filter') rather than silently normalizing one to the other; the canonical "
            "capability name used across this ingestion is MANAGE_TRANSLATION_ENTRY_POINT."
        ),
    },
    {
        "chunk_id": "editorcfg_translation_hiding_vs_disabling_06",
        "url": TRANSLATION_URL, "canonical_url": TRANSLATION_URL,
        "source_title": "Configure Translation feature in the Editor for Cloud Service",
        "capability": "EDITOR_TRANSLATION_ENTRY_POINT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure Translation feature in the Editor for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["UNDERLYING_CAPABILITY_STATE_NOT_ESTABLISHED"],
        "text": (
            "This is a mandatory distinction: the source establishes only that removing the "
            "documented ui_config.json tab block makes the Manage tab/filter UI ENTRY POINT NOT "
            "AVAILABLE. It does NOT establish that the translation backend, translation APIs, "
            "existing translation projects, or map-console translation are disabled or deleted "
            "as a result. UNDERLYING_TRANSLATION_CAPABILITY_STATE = NOT_ESTABLISHED by this "
            "page. Do not infer full feature disablement from this UI-visibility configuration "
            "alone; treat hiding the entry point as UI-scope only unless another source or code "
            "inspection establishes broader impact."
        ),
    },
    # ---- SOURCE-3: Pasted table transformation (Cloud) ----
    {
        "chunk_id": "editorcfg_pasted_table_default_simpletable_07",
        "url": PASTED_TABLES_URL, "canonical_url": PASTED_TABLES_URL,
        "source_title": "Configure display of pasted tables for Cloud Service",
        "capability": "PASTED_TABLE_TRANSFORMATION", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure display of pasted tables for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["SOURCE_MICROSOFT_WORD", "SOURCE_MICROSOFT_EXCEL", "DEFAULT_SIMPLETABLE"],
        "text": (
            "The Editor's secondary toolbar can insert a simple table at the current/next valid "
            "location, and separately a table copied from Microsoft Word or Microsoft Excel can "
            "be pasted directly into a topic file - pasted-table transformation is a distinct "
            "capability from inserting a new blank table via the toolbar, from general table "
            "editing after insertion, and from Markdown table insertion. By default, a copied "
            "table pasted into a topic is displayed as a DITA simpletable in the Editor. "
            "Administrators can change this default via the XML Editor Configuration setting so "
            "copied tables are instead displayed as tgroup (a normal DITA table structure)."
        ),
    },
    {
        "chunk_id": "editorcfg_pasted_table_tgroup_config_and_typo_08",
        "url": PASTED_TABLES_URL, "canonical_url": PASTED_TABLES_URL,
        "source_title": "Configure display of pasted tables for Cloud Service",
        "capability": "PASTED_TABLE_TRANSFORMATION", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Configure display of pasted tables for Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["htmlToDitaMapping.table", "DATA_QUALITY_trgoup_TYPO"],
        "text": (
            "To switch the default pasted-table format from simpletable to tgroup: go to Tools "
            "> Guides > Folder Profiles, select the target profile, open XML Editor "
            "Configuration, Edit, download ui_config.json, and update the htmlToDitaMapping "
            "setting to: \"htmlToDitaMapping\":{\"table\": {\"name\": \"tgroup\", \"wrapTag\": "
            "{\"dita\": \"table\", \"html\": \"div\"}}}, then save and upload. This "
            "htmlToDitaMapping.table configuration key family is scoped specifically to table "
            "mapping and must not be generalized to every HTML element mapping. DATA-QUALITY "
            "WARNING: the raw extracted source page shows the code literals 'simpletable', "
            "'tgroup', and a third literal 'trgoup' rendered adjacent to one another (appearing "
            "to be a caption/illustration artifact near the configuration code). "
            "RAW_SOURCE_LITERAL = 'trgoup'. NORMALIZED_SEMANTIC_CONCEPT = DITA_TGROUP_TABLE. "
            "This is preserved as a likely documentation typo, not as a separate table type - do "
            "not create or search for a distinct 'trgoup' table capability. NOTE: the claim that "
            "'merged rows/columns in the copied table force a normal-table/tgroup structure "
            "regardless of the configured simpletable preference' could NOT be independently "
            "confirmed in the actual fetched page text for this extraction pass and is marked "
            "NOT_ESTABLISHED rather than asserted as documented behavior."
        ),
    },
    # ---- SOURCE-4: Health Check presets (Cloud) ----
    {
        "chunk_id": "editorcfg_healthcheck_create_preset_09",
        "url": HEALTH_CHECK_URL + "#create-a-health-check-preset", "canonical_url": HEALTH_CHECK_URL,
        "source_title": "Create and manage health check presets",
        "capability": "HEALTH_CHECK_PRESET_MANAGEMENT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Create and manage health check presets | Create a health check preset",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["FOLDER_PROFILE_SCOPE", "CHECK_TYPES_BROKEN_LINKS_DUPLICATE_IDS_SCHEMATRON"],
        "text": (
            "To create a health check preset at the folder-profile level: go to Workspace "
            "Settings > Health check, in the Health check presets panel select New, in the New "
            "health check preset dialog add a preset name and select the checks to include - "
            "the documented current check types are Broken links, Duplicate IDs, and Schematron "
            "validations (a preset selects one or more of these; this list is documented as "
            "current, not asserted to be permanently fixed) - select Create, then select Save "
            "to persist the Workspace configuration. Create-in-dialog and the subsequent "
            "Workspace-Settings Save are two SEPARATE lifecycle steps (CREATE_PRESET_IN_UI_STATE "
            "then PERSIST_WORKSPACE_CONFIGURATION), not one merged action."
        ),
    },
    {
        "chunk_id": "editorcfg_healthcheck_consumers_10",
        "url": HEALTH_CHECK_URL + "#create-a-health-check-preset", "canonical_url": HEALTH_CHECK_URL,
        "source_title": "Create and manage health check presets",
        "capability": "HEALTH_CHECK_PRESET_MANAGEMENT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Create and manage health check presets | Create a health check preset",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["AUTHOR_MAP_VIEW_OPTIONS", "AUTHOR_HEALTH_CHECK_REPORT_PANEL", "PUBLISHER_OUTPUT_PRESET_TOGGLE"],
        "text": (
            "A created preset becomes available to two separate documented consumer workflows. "
            "AUTHOR: available in the Options menu of a map in Map view, and separately in the "
            "Health check report panel (alongside the Search panel), letting an Author run a "
            "health check on the selected map using a preset configured for their profile. "
            "PUBLISHER: the 'Run health check before output generation' toggle appears in the "
            "output preset panel, which a Publisher can enable/disable as needed. These are "
            "documented as separate product flows with no assumption of identical underlying "
            "execution/UI implementation between the Author and Publisher paths."
        ),
    },
    {
        "chunk_id": "editorcfg_healthcheck_nonblocking_11",
        "url": HEALTH_CHECK_URL + "#create-a-health-check-preset", "canonical_url": HEALTH_CHECK_URL,
        "source_title": "Create and manage health check presets",
        "capability": "HEALTH_CHECK_PRESET_MANAGEMENT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Create and manage health check presets | Create a health check preset",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["APPENDED_TO_PUBLISHING_LOGS", "DOES_NOT_BLOCK_OUTPUT_GENERATION"],
        "text": (
            "When the Publisher's pre-generation health check toggle is enabled, the health "
            "check report is APPENDED TO THE LOGS AT THE START of the publishing process, but "
            "the documentation explicitly states it 'does not block output generation' - health "
            "check issues are logged, not gating. This pre-publish, non-blocking Health Check is "
            "a DIFFERENT mechanism from Schematron pre-save validation, which may block a file "
            "save under applicable configuration - do not merge the two gates."
        ),
    },
    {
        "chunk_id": "editorcfg_healthcheck_management_actions_12",
        "url": HEALTH_CHECK_URL + "#manage-health-check-presets", "canonical_url": HEALTH_CHECK_URL,
        "source_title": "Create and manage health check presets",
        "capability": "HEALTH_CHECK_PRESET_MANAGEMENT", "deployment_model": "CLOUD_SERVICE",
        "heading_path": "Create and manage health check presets | Manage health check presets",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["EDIT", "DUPLICATE", "REMOVE", "REMOVE_DOES_NOT_ESTABLISH_FILE_DELETION"],
        "text": (
            "Once created, a preset appears in the Health check presets panel with three "
            "management actions: Edit (update the preset name, select/unselect checks, and "
            "add/remove attached Schematron files); Duplicate (creates a copy of the preset in "
            "the same list); Remove (removes the preset entry from the panel). After any of "
            "these, Select Save persists the change to the Workspace configuration. The "
            "documentation does not state that Remove deletes the underlying Schematron files "
            "from the repository - do not infer that behavior; Remove is documented only as "
            "removing the preset entry itself."
        ),
    },
    # ---- SOURCE-5: New Editor enablement (On-Premise) ----
    {
        "chunk_id": "editorcfg_new_editor_onprem_enablement_13",
        "url": NEW_EDITOR_URL, "canonical_url": NEW_EDITOR_URL,
        "source_title": "Configure New Editor for On-Premise",
        "capability": "NEW_EDITOR_ENABLEMENT", "deployment_model": "ON_PREMISE",
        "heading_path": "Configure New Editor for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["PID_com.adobe.fmdita.config.ConfigManager", "SETTING_enable.markup.editor"],
        "text": (
            "To enable the New Editor (documented alias in this On-Premise context: 'Editor "
            "2.0') on-prem: open the AEM Web Console Configuration page at "
            "http://<server name>:<port>/system/console/configMgr, search for and select the "
            "com.adobe.fmdita.config.ConfigManager bundle, enable the setting labeled 'Enable "
            "Editor 2.0' (internal key: enable.markup.editor), then select Save. This "
            "ConfigManager identity and setting key are exact source-documented values. NEW "
            "EDITOR / EDITOR 2.0 in this On-Premise configuration context are treated as "
            "aliases, not as separate capabilities, and not the same concept as general "
            "user-level Editor Settings or Workspace Settings elsewhere in the product - a "
            "disabled state here should not be read as a missing-feature regression, only as "
            "the documented default/off configuration."
        ),
    },
    # ---- SOURCE-6: Special characters (On-Premise) ----
    {
        "chunk_id": "editorcfg_special_chars_paths_14",
        "url": SPECIAL_CHARS_URL, "canonical_url": SPECIAL_CHARS_URL,
        "source_title": "How to configure additional special characters in Editor toolbar for On-Premise",
        "capability": "SPECIAL_CHARACTER_CONFIGURATION", "deployment_model": "ON_PREMISE",
        "heading_path": "How to configure additional special characters in Editor toolbar for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["APPS_symbols.json", "LIBS_symbols.json_DEFAULT_SOURCE_TO_COPY"],
        "text": (
            "The Editor toolbar has a built-in shortcut for inserting special characters; the "
            "available character list is configurable. To add more characters: log into AEM, "
            "open CRXDE Lite, create a symbols.json file at /apps/fmdita/xmleditor/ (the "
            "documented way to get a starting point is to copy the default file from "
            "/libs/fmdita/clientlibs/clientlibs/xmleditor/symbols.json), then add character "
            "definitions to the new /apps copy. Direct modification under /libs is not "
            "represented as the documented customization method - /apps is the customization "
            "location, /libs is the default source to copy from. These paths are On-Premise "
            "implementation configuration evidence, not formal author-facing acceptance "
            "criteria text on their own."
        ),
    },
    {
        "chunk_id": "editorcfg_special_chars_schema_15",
        "url": SPECIAL_CHARS_URL, "canonical_url": SPECIAL_CHARS_URL,
        "source_title": "How to configure additional special characters in Editor toolbar for On-Premise",
        "capability": "SPECIAL_CHARACTER_CONFIGURATION", "deployment_model": "ON_PREMISE",
        "heading_path": "How to configure additional special characters in Editor toolbar for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["SCHEMA_label_items_name_title", "NAME_FIELD_LABEL_MUST_NOT_CHANGE"],
        "text": (
            "symbols.json schema, per the documented example: a top-level object has 'label' "
            "(the category name shown in the Special Character dialog, example: 'Logical "
            "Symbols') and 'items' (an array of character definitions in that category). Each "
            "item has 'name' (the literal character/symbol value itself, for example the "
            "actual >= or <= glyph - the 'name' field LABEL must NOT be changed, per the "
            "documentation) and 'title' (the tooltip/description shown for that symbol, "
            "documented examples 'Greater-Than or Equal To' and 'Smaller-Than or Equal To'). "
            "Multiple character definitions can exist within one category, and adding a new "
            "top-level category block adds another category to the Special Character dialog. "
            "The documented example symbols are illustrative, not a complete fixed set. This "
            "capability is distinct from Quick Insert, an Insert Symbol menu, a non-breaking-"
            "space shortcut, or the Source view's Smart Catalog."
        ),
    },
    # ---- SOURCE-7: Check-in / Check-out icon titles (On-Premise) ----
    {
        "chunk_id": "editorcfg_checkin_checkout_label_config_16",
        "url": CHECKIN_CHECKOUT_URL, "canonical_url": CHECKIN_CHECKOUT_URL,
        "source_title": "Configure the title for Check in and Check out icons for On-Premise",
        "capability": "LOCK_ACTION_LABEL_CUSTOMIZATION", "deployment_model": "ON_PREMISE",
        "heading_path": "Configure the title for Check in and Check out icons for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["TOPBAR_TITLE_FIELD", "LABEL_ONLY_NOT_ACTION_SEMANTICS"],
        "text": (
            "AEM Guides lets you configure the title shown for the Check in / Check out icons "
            "in the Editor topbar: download ui_config.json via Tools > Guides > Folder Profiles "
            "> Global Profile > XML Editor Configuration > Edit > Download, then in the "
            "'topbar' section change the title values - documented exact source snippet: "
            "// Change title to \"Check out\" instead of \"Lock\" -> \"title\": \"Check out\"; "
            "and // Change title to \"Check in\" instead of \"@checkOutBy\" -> \"title\": "
            "\"Check in\" (note the second comment references the existing dynamic title "
            "literally as '@checkOutBy', not a plain static default string - preserved verbatim "
            "as source evidence). Save and upload the file. This is MANDATORY: the "
            "configuration changes only the USER-VISIBLE TITLE text - the source does not "
            "establish that the underlying lock/unlock or checkout/checkin OPERATION semantics, "
            "permissions, or persistence change as a result. Do not conclude that renaming "
            "'Lock' to 'Check out' changes permission, persistence, or checkout behavior; "
            "eligibility for the action remains governed by file-lock state and permissions, "
            "not by the label text. Historical automation relying on the old label text may "
            "need semantic selectors rather than exact-text matches after this configuration "
            "changes. No source-title spelling irregularity was found on the fetched page's "
            "actual heading text in this extraction pass."
        ),
    },
    # ---- SOURCE-8: Query LimitReads (On-Premise) ----
    {
        "chunk_id": "editorcfg_query_limitreads_17",
        "url": LIMITREADS_URL, "canonical_url": LIMITREADS_URL,
        "source_title": "Configure the number of LimitReads for a query for On-Premise",
        "capability": "QUERY_ENGINE_LIMITREADS_CONFIGURATION", "deployment_model": "ON_PREMISE",
        "heading_path": "Configure the number of LimitReads for a query for On-Premise",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["JMX_QueryEngineSettings_LimitReads", "AEM_PLATFORM_OWNED_GUIDES_CONSUMER"],
        "text": (
            "To increase the number of repository nodes a query may read at a time: open the "
            "AEM Web Console JMX page at http://<server name>:<port>/system/console/jmx, search "
            "for and click QueryEngineSettings, change the LimitReads attribute value, then "
            "click Save. The documentation states increasing this value 'helps you generate the "
            "report for larger DITA maps' - this is the sole documented AEM Guides benefit. "
            "OWNERSHIP: this JMX/query-engine setting belongs to the AEM platform's query "
            "engine layer, not to AEM Guides itself; AEM Guides is a downstream consumer "
            "benefiting from it for large-map report generation. No numeric recommendation, no "
            "unlimited-reads assumption, and no general system-performance-improvement claim is "
            "documented - treat this strictly as an environment/platform tuning operation, not "
            "an author-level Editor setting, and not a universal performance SLA. Distinct from "
            "search-result limits, pagination size, maximum-recent-files settings, RAG top-k "
            "retrieval limits, and broken-link-report result counts - none of those are the "
            "same configuration as this query-engine LimitReads attribute."
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
        print(" -", r["chunk_id"], "|", r["capability"], "|", r["deployment_model"])
PYEOF

python3 ingest_editorconfig_cloud_onprem_8sources.py
