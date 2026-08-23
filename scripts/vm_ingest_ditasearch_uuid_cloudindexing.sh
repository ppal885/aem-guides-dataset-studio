#!/usr/bin/env bash
# Paste this whole block into the VM terminal.
set -e
cd ~/aem-guides-dataset-studio/backend

cat > ingest_ditasearch_uuid_cloudindexing.py << 'PYEOF'
"""Curated ingestion: AEM Guides DITA/UUID Search Configuration + AEM Cloud
Service Content Search and Indexing - 2 official Experience League pages, kept
as 2 independent authority scopes (AEM Guides product contract vs AEM platform
contract) per the task's requirement. The 5 supplied Guides anchors are all
sections of ONE canonical document (conf-dita-search) - not 5 separate pages.

Text grounded in the live pages (fetched and parsed this run, main-descendants-
scoped extraction).

Notable findings deliberately flagged rather than silently normalized:
- The DITA-search page's UUID section literally reads "you will get the
  UUIS-based search filtering option" (typo: UUIS instead of UUID) even
  though the configured property is jcr:content/fmUuid and the section
  heading is "Add UUID-based search component". Preserved as a documented
  typo, not a separate capability.
- The exclude-temporary-paths section renders the default path with an
  escaped underscore in the raw HTML text (translation\\_output). The real
  repository path has a plain underscore: /content/dam/projects/
  translation_output. Both the raw literal and the normalized path are kept.
- Search-form predicate visibility, DITA serialization/metadata extraction,
  Oak/Lucene indexing, and user permission are modeled as four separate,
  non-inferable prerequisite layers per the source's own structure - a
  visible search field does not imply the underlying data is indexed or
  extracted, and vice versa.
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

DITASEARCH_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
                   "install-conf-guide/aem-asset-search/conf-dita-search")
CLOUDINDEXING_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/"
                      "content/operations/indexing")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "ditasearch-uuid-cloudindexing-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON_GUIDES = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_CONTRACT",
    "product": "AEM_GUIDES", "domain": "SEARCH_AND_DISCOVERY", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}
COMMON_PLATFORM = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PLATFORM_CONTRACT",
    "product": "AEM", "domain": "CLOUD_SERVICE_OPERATIONS", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: AEM Guides DITA / UUID search configuration ----
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_element_predicate_01",
        "url": DITASEARCH_URL + "#id192SF0F50HS", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_ASSET_SEARCH", "heading_path": "Configure search for AEM Assets UI | Add DITA Element search component in Assets UI",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["SEARCH_FORMS_ASSETS_ADMIN_SEARCH_RAIL", "DITA_ELEMENT_PREDICATE"],
        "text": (
            "To add DITA Element search to AEM Assets UI: log in as administrator, go to "
            "Tools > General > Search Forms, select the Assets Admin Search Rail, click Edit, "
            "in the Select Predicate tab scroll to the end of the list, drag-and-drop the DITA "
            "Element Predicate into the search form, then click Done. Once saved, the DITA "
            "Element search filtering option appears under the Filters option in Assets UI. "
            "This is a SEARCH-FORM-PREDICATE configuration - it controls which filter field a "
            "user CAN ACCESS. It does not by itself establish which DITA elements are "
            "searchable; that scope is controlled separately by the DITA serialization "
            "configuration (see ditasearch_serialization_purpose_05 and related chunks). A "
            "visible predicate does not imply the underlying data has been extracted/indexed, "
            "and extracted/indexed data does not imply the predicate is visible to a given user."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_uuid_predicate_02",
        "url": DITASEARCH_URL + "#id2034F04K05Z", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_ASSET_SEARCH", "heading_path": "Configure search for AEM Assets UI | Add UUID-based search component in Assets UI",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["PROPERTY_PREDICATE", "PROPERTY_jcr:content/fmUuid"],
        "text": (
            "To add UUID-based search to AEM Assets UI: log in as administrator, go to "
            "Tools > General > Search Forms, select the Assets Admin Search Rail, click Edit, "
            "in the Select Predicate tab choose Property Predicate and drag-and-drop it into "
            "the search form, then in the Settings tab set Field Label to UUID and Property "
            "Name to jcr:content/fmUuid, then click Done. This UUID search predicate is a "
            "distinct configuration object from Copy UUID, Share UUID Link, a DITA element ID, "
            "a repository node identifier, and a citation Unique ID - none of those are the "
            "same as this Assets-UI property-predicate search filter keyed on "
            "jcr:content/fmUuid."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_uuid_typo_warning_03",
        "url": DITASEARCH_URL + "#id2034F04K05Z", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_ASSET_SEARCH", "heading_path": "Configure search for AEM Assets UI | Add UUID-based search component in Assets UI",
        "record_type": "DATA_QUALITY_WARNING", "content_type": "DATA_QUALITY",
        "relations": ["RAW_SOURCE_LITERAL_UUIS-based", "NORMALIZED_UUID_BASED_SEARCH"],
        "text": (
            "DATA-QUALITY WARNING: the DITA-search documentation page is internally "
            "inconsistent about this feature's name. The section heading reads 'Add UUID-based "
            "search component', and the configured property is jcr:content/fmUuid, but the "
            "concluding sentence of that same section reads verbatim: 'When you access the "
            "Filters option in the Assets UI, you will get the UUIS-based search filtering "
            "option' - using the literal misspelling UUIS-based instead of UUID-based. "
            "RAW_SOURCE_LITERAL = 'UUIS-based'. NORMALIZED_SEMANTIC_CONCEPT = "
            "UUID_BASED_SEARCH. This is preserved as a documented typo (likely OCR/typo in the "
            "source), not as a separate 'UUIS' capability - do not create or search for a "
            "distinct UUIS feature."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_permissions_04",
        "url": DITASEARCH_URL + "#id192SF0G0RUI", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_ASSET_SEARCH", "heading_path": "Configure search for AEM Assets UI | Provide permissions to users",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["READ_PERMISSION_REQUIRED", "PATH_/conf/global/settings/dam/search"],
        "text": (
            "Authors and Publishers need explicit permission to access the configured DITA "
            "element/attribute or UUID search capabilities from Assets UI; without it, users "
            "cannot search DITA content by element/attribute values or UUID even if the "
            "predicates are configured. Steps: access the user/group permissions page, search "
            "for the target user or group (example: 'authors'), select it, open the Permissions "
            "tab, navigate to /conf/global/settings/dam/search, grant Read permission on that "
            "search folder, and click Save. This SEARCH_PERMISSION layer is distinct from "
            "general content-read permission elsewhere in the repository - it specifically "
            "gates access to the configured search UI capability, not the underlying DITA "
            "content or its indexed metadata. Absence of this permission does NOT remove the "
            "search metadata or indexes themselves - it only blocks the affected user's UI "
            "access to the search feature."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_serialization_purpose_05",
        "url": DITASEARCH_URL + "#id192SF0G10YK", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_SERIALIZATION", "heading_path": "Configure search for AEM Assets UI | Add custom elements or attributes in search",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["SERIALIZATION_UPSTREAM_OF_SEARCH", "SERIALIZATION_NOT_SAME_AS_OAK_INDEXING"],
        "text": (
            "For DITA search to work, DITA content requires preprocessing: this extracts "
            "selective content from individual DITA maps/topics so it can be indexed for "
            "faster searching. The source calls this preprocessing step Serialization. "
            "Serialization happens during content upload or can be run on-demand, and uses a "
            "configuration file to determine how much content from each DITA file is indexed. "
            "The default serialization config location is /libs/fmdita/config/"
            "serializationconfig.xml. Serialization is upstream of repository search - it "
            "produces the searchable metadata that an Oak/Lucene index later makes efficiently "
            "queryable. Serialization is NOT itself an Oak index definition; the two are "
            "separate layers (see cloudindexing_ownership_and_service_model_14 for the "
            "downstream indexing layer)."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_default_prolog_scope_06",
        "url": DITASEARCH_URL + "#id192SF0G10YK", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_SERIALIZATION", "heading_path": "Configure search for AEM Assets UI | Add custom elements or attributes in search",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["DEFAULT_SCOPE_PROLOG_ONLY"],
        "text": (
            "The default search serialization configuration allows searching only on elements "
            "and attributes WITHIN THE DITA PROLOG element. To search on other DITA elements or "
            "attributes (for example body content), the serialization configuration file must "
            "be customized. Do not assume all DITA body content is searchable by default - only "
            "the documented prolog scope is searchable out of the box."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_ruleset_attributeset_07",
        "url": DITASEARCH_URL + "#id192SF0G10YK", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_SERIALIZATION", "heading_path": "Configure search for AEM Assets UI | Add custom elements or attributes in search",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["ATTRIBUTE_SET", "RULE_SET", "XPATH", "TEXT_YES_NO", "ATTRIBUTESET_ALL_ATTRS"],
        "text": (
            "serializationconfig.xml has two primary sections: attribute set (contains the set "
            "of selected searchable attributes) and rule set (contains element-extraction rules "
            "and attribute-extraction rules) - a rule is never split from its referenced "
            "attribute set. Each rule has: xpath (the XPath query identifying which DITA "
            "elements/attributes to serialize - the default element rule retrieves all prolog "
            "elements, the default attribute rule retrieves all attributes of prolog elements); "
            "text (YES includes the selected element's text in the serialized/searchable data; "
            "NO does not serialize element text, and applicable attributes must instead be "
            "configured through attribute-set behavior); attributeset (references the "
            "applicable attribute-set ID by name; the documented special value all-attrs means "
            "serialize ALL applicable attributes for that rule - all-attrs is a documented "
            "keyword, not an ordinary attribute name to look up in the attribute-set list). "
            "Example rule set snippet from the source: a rule with xpath matching topic/topic "
            "and topic/prolog descendant leaf nodes, text=\"yes\", attributeset=\"all-attrs\"; "
            "a second rule with xpath matching the same prolog scope's attributes excluding the "
            "'class' attribute."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_dita_class_mapping_08",
        "url": DITASEARCH_URL + "#id192SF0G10YK", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_SERIALIZATION", "heading_path": "Configure search for AEM Assets UI | Add custom elements or attributes in search",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "REFERENCE",
        "relations": ["DITA_CLASS_TOPIC", "DITA_CLASS_TASK", "DITA_CLASS_CONCEPT", "DITA_CLASS_REFERENCE", "DITA_CLASS_MAP"],
        "text": (
            "A serialization rule's xpath contains the class name of the target DITA document "
            "type. The source documents these class-name mappings for building rules against "
            "other DITA document types: Topic = topic/topic; Task = topic/topic task/task; "
            "Concept = topic/topic concept/concept; Reference = topic/topic reference/reference; "
            "Map = map/map. This is the documented, source-supported set of DITA class contexts "
            "for serialization rules - it is not asserted to be an exhaustive list of every "
            "possible DITA specialization; DITA 1.3 specification evidence should be consulted "
            "separately when validating additional specialization classes not listed here."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_serialization_config_dita_serialization_flag_09",
        "url": DITASEARCH_URL + "#id192SF0GA0HT", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_METADATA_EXTRACTION", "heading_path": "Configure search for AEM Assets UI | Extract metadata from existing content",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["PID_com.adobe.fmdita.config.ConfigManager", "PROPERTY_dita.serialization"],
        "text": (
            "After changing the serialization configuration, extracting metadata from EXISTING "
            "DITA files requires two tasks: (1) enabling the metadata extraction option in the "
            "com.adobe.fmdita.config.ConfigManager bundle - configured via Configuration "
            "overrides with PID com.adobe.fmdita.config.ConfigManager, property key "
            "dita.serialization, type Boolean, documented default value: false; or on-prem, via "
            "the Web Console Configuration page at the documented configMgr URL, searching for "
            "the com.adobe.fmdita.config.ConfigManager bundle and selecting 'Enable DITA "
            "Metadata Extraction'; then (2) running the metadata extraction workflow itself "
            "(see ditasearch_extraction_workflow_11). Enabling the dita.serialization flag "
            "alone is NOT sufficient for existing content - the workflow must still be executed "
            "separately for that content to become searchable."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_configmgr_url_typo_warning_10",
        "url": DITASEARCH_URL + "#id192SF0GA0HT", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_METADATA_EXTRACTION", "heading_path": "Configure search for AEM Assets UI | Extract metadata from existing content",
        "record_type": "DATA_QUALITY_WARNING", "content_type": "DATA_QUALITY",
        "relations": ["RAW_SOURCE_LITERAL_TRAILING_CHARACTER"],
        "text": (
            "DATA-QUALITY WARNING: the On-Premise instructions for opening the Web Console "
            "Configuration page render the URL with an apparent stray trailing character "
            "immediately after 'configMgr' in the extracted source text (rendered as "
            "'http://<server name>:<port>/system/console/configMgr w' in one observed parse). "
            "RAW_SOURCE_LITERAL preserves this trailing artifact separately from "
            "NORMALIZED_SEMANTIC_LOCATION, which is the real, documented AEM Web Console "
            "Configuration Manager path: /system/console/configMgr. Do not include the stray "
            "trailing character in the normalized configuration URL used for any test step or "
            "acceptance criterion."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_extraction_workflow_11",
        "url": DITASEARCH_URL + "#id192SF0GA0HT", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_METADATA_EXTRACTION", "heading_path": "Configure search for AEM Assets UI | Extract metadata from existing content",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["TOOLS_GUIDES_DITA_METADATA_EXTRACTION", "SINGLE_FILE_SCOPE", "MULTI_FOLDER_SCOPE"],
        "text": (
            "The metadata extraction workflow is run via Tools > Guides > DITA Metadata "
            "Extraction, with two documented execution scopes: select a single file (extracts "
            "metadata for that selected file and its applicable dependencies) or select "
            "multiple folders (extracts content for all selected folders - multiple folders may "
            "be added to one serialization/extraction task). After selecting scope, Start > "
            "Confirm Metadata Extraction begins the extraction task. This extraction step is "
            "ONLY required for content that already existed in the AEM repository before the "
            "serialization config change - see ditasearch_existing_vs_new_content_lifecycle_12 "
            "for the temporal boundary that governs when this workflow is needed versus when "
            "extraction happens automatically."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_existing_vs_new_content_lifecycle_12",
        "url": DITASEARCH_URL + "#id192SF0GA0HT", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "DITA_METADATA_EXTRACTION", "heading_path": "Configure search for AEM Assets UI | Extract metadata from existing content",
        "record_type": "STATE_MACHINE", "content_type": "LIFECYCLE",
        "relations": ["EXISTING_CONTENT_REQUIRES_MANUAL_EXTRACTION", "NEW_OR_EDITED_CONTENT_AUTO_EXTRACTED"],
        "text": (
            "This is a first-class search-lifecycle state partition. When the search "
            "serialization configuration changes: EXISTING DITA content (already in the "
            "repository before the config change) requires the explicit metadata extraction "
            "workflow to be run before it becomes searchable under the new configuration. NEW "
            "or EDITED DITA content created/edited AFTER the config change has its metadata "
            "extracted AUTOMATICALLY - no manual workflow run is needed for that content. This "
            "is not a single unconditional re-extraction rule; the temporal boundary (before vs "
            "after the configuration change) determines which lifecycle branch applies to a "
            "given file."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_exclude_temp_paths_purpose_13",
        "url": DITASEARCH_URL + "#id197AHI0035Z", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "SEARCH_PATH_EXCLUSION", "heading_path": "Configure search for AEM Assets UI | Exclude temporary files from search results",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["DEFAULT_SCOPE_ENTIRE_REPOSITORY", "TRANSLATION_TEMP_FOLDER"],
        "text": (
            "By default, AEM Guides search runs against the entire AEM repository. During "
            "content translation workflows, unapproved files sit in a temporary folder location "
            "and would otherwise appear in search results. To prevent this, the temporary "
            "translation folder location must be added to a search-index exclude list. "
            "Excluding a path controls SEARCH/INDEX SCOPE only - it does NOT delete the "
            "excluded content, does NOT disable translation, and does NOT remove any ACL/"
            "permission on that path. An excluded path is a distinct concept from a deleted "
            "path or an ACL-denied path."
        ),
    },
    {
        "common": COMMON_GUIDES,
        "chunk_id": "ditasearch_exclude_temp_paths_config_and_typo_14",
        "url": DITASEARCH_URL + "#id197AHI0035Z", "canonical_url": DITASEARCH_URL,
        "source_title": "Configure search for AEM Assets UI",
        "capability": "SEARCH_PATH_EXCLUSION", "heading_path": "Configure search for AEM Assets UI | Exclude temporary files from search results",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["INDEX_damAssetLucene", "INDEX_lucene", "PROPERTY_excludedPaths"],
        "text": (
            "Excluding the temporary translation path uses the excludedPaths property (type "
            "String[]) on the applicable Oak index. Cloud Service: add excludedPaths to the "
            "custom damAssetLucene index configuration, following code/Cloud-Manager deployment "
            "governance - this is NOT permission to mutate a production index node directly. "
            "On-Premise: via CRXDE Lite, add excludedPaths directly on the "
            "/oak:index/damAssetLucene node, and separately on the /oak:index/lucene node - "
            "these are two distinct On-Premise index nodes, both documented as needing the "
            "property. The documented default excluded value is the repository path "
            "/content/dam/projects/translation_output. DATA-QUALITY WARNING: the raw extracted "
            "source HTML text renders this path with an escaped underscore, as "
            "'translation\\_output' - RAW_SOURCE_LITERAL preserves this escaped form, while "
            "NORMALIZED_REPOSITORY_PATH is the real path with a plain underscore: "
            "/content/dam/projects/translation_output. Do not treat the backslash as part of "
            "the actual repository path. Cloud and On-Premise excluded-path procedures are kept "
            "distinct - do not apply the On-Premise CRXDE steps to Cloud Service."
        ),
    },
    # ---- SOURCE-2: AEM Cloud Service content search and indexing ----
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_ownership_and_service_model_15",
        "url": CLOUDINDEXING_URL + "#changes-in-aem-as-a-cloud-service", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "CLOUD_INDEX_DEPLOYMENT_GOVERNANCE", "heading_path": "Content Search and Indexing | Changes in AEM as a Cloud Service",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["INSTANCE_CENTRIC_REPLACED_BY_SERVICE_MODEL", "ROLLING_DEPLOYMENT_TWO_INDEX_SETS"],
        "text": (
            "AEM as a Cloud Service moves from an instance-centric index-administration model "
            "(AEM 6.5 and earlier) to a service/deployment-based model driven by Cloud Manager "
            "CI/CD pipelines. Documented changes: customers no longer have Index Manager access "
            "on a single production AEM instance to debug/configure/maintain indexing (Index "
            "Manager remains usable only for local development and On-Premise deployments); "
            "index changes are specified before deployment rather than applied live, since "
            "unspecified/untested index changes can affect system stability and performance; "
            "index configuration changes are delivered as code/deployments like other content "
            "changes; with the rolling-deployment model, TWO index sets can coexist - one for "
            "the old application version, one for the new; customers see indexing-job "
            "completion on the Cloud Manager build page and get a notification once the new "
            "version is ready for traffic; production configuration changes and unspecified "
            "index changes break CI/CD policy. This platform-owned indexing model is the "
            "downstream layer AEM Guides search depends on but does not itself own or control."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_current_limitations_16",
        "url": CLOUDINDEXING_URL + "#current-limitations", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "CLOUD_INDEX_DEPLOYMENT_GOVERNANCE", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | Current Limitations",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["LUCENE_ONLY_CUSTOMER_CONFIG", "ELASTICSEARCH_NOT_CUSTOMER_CONFIGURABLE", "STANDARD_ANALYZERS_ONLY"],
        "text": (
            "Documented current limitations: index management is only supported for indexes of "
            "type lucene with compatVersion 2 - internally, other index implementations "
            "(for example Elasticsearch) might back some product indexes, and a query written "
            "against a Lucene-named index such as damAssetLucene might, on Cloud Service, "
            "actually run against an Elasticsearch-backed version of that same index; this "
            "internal substitution is invisible to the application user, though diagnostic "
            "tools such as the explain feature may report a different underlying index. "
            "Customers cannot and do not need to directly configure Elasticsearch indexes - "
            "this is an internal implementation detail, not a customer configuration surface. "
            "Only built-in (standard) analyzers are supported; custom analyzers are not "
            "supported. Indexing the contents of /oak:index itself is not currently supported. "
            "For operational stability, indexes should not grow excessively large; if total "
            "index size increases by more than 100% after custom indexes/adjustments in a dev "
            "environment, custom index definitions should be reviewed and adjusted - Cloud "
            "Service can prevent deployment of, or remove, indexes that would negatively affect "
            "system stability/performance. This size guidance is documented operational "
            "guidance, not a formal AEM Guides performance acceptance criterion."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_simplified_diff_index_17",
        "url": CLOUDINDEXING_URL + "#simplified-index-management-using-the-diff-index", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "SIMPLIFIED_INDEX_MANAGEMENT", "heading_path": "Content Search and Indexing | Simplified Index Management using the Diff Index",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["DIFF_INDEX_JSON", "MUST_INCLUDE_/content_NOT_/apps_OR_/libs"],
        "text": (
            "Simplified Index Management customizes most AEM indexes via one JSON diff file "
            "(a diff.index package) - no manual copying of definitions or explicit versioning "
            "is required; customizations are automatically merged with the latest OOTB index, "
            "and a new index version is created only when needed. It supports both customizing "
            "an existing OOTB index and adding a fully custom index. LIMITATION: not currently "
            "available for indexes that include /apps or /libs; it applies to indexes that have "
            "an includedPaths property, for example one scoped to /content. For indexes without "
            "an includedPaths property, or where includedPaths includes /apps or /libs, the "
            "documented alternative is to redesign the query or use Legacy Index Configuration "
            "instead (/content is a common example of a supported scope, not the only possible "
            "valid included path). Example documented procedure: create "
            "ui.apps/src/main/content/jcr_root/_oak_index/diff.index/ with a required "
            "placeholder .content.xml (type=lucene, includedPaths/queryPaths configured, "
            "async=async) plus a diff.json file defining the actual index customization - this "
            "customizes the damAssetLucene index and can introduce a fully custom index in the "
            "same step. DIFF_INDEX here is this JSON-file-based Oak index customization "
            "mechanism - a distinct concept from a generic source-code diff."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_legacy_index_18",
        "url": CLOUDINDEXING_URL + "#legacy-index-configurations", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "LEGACY_INDEX_CONFIGURATION", "heading_path": "Content Search and Indexing | Legacy Index Configurations",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["APPLIES_WHEN_/apps_/libs_OR_ROOT_SCOPE"],
        "text": (
            "Legacy Index Configuration mode is required for indexes that cannot be configured "
            "using Simplified Index Management - specifically indexes that cannot have an "
            "includedPaths property, or that need to cover /apps, /libs, or / (the repository "
            "root). Documented examples: cqPageLucene (if customization is needed, the "
            "documented recommendation is to migrate queries to cqPageContent instead, which "
            "has an includedPaths value of /content plus a tag); ntBaseLucene (best practice is "
            "to avoid changing it at all, instead creating a fully custom index with a distinct "
            "prefix, such as acme., scoped only to the required paths, per Simplified Index "
            "Management). Legacy mode is chosen based on whether an index CAN use includedPaths "
            "or must cover a broad root/apps/libs scope - not merely because an existing index "
            "happens to be old."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_index_naming_taxonomy_19",
        "url": CLOUDINDEXING_URL + "#index-names", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "INDEX_DEFINITION_VERSIONING", "heading_path": "Content Search and Indexing | Index Names",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "REFERENCE",
        "relations": ["OOTB_INDEX", "OOTB_CUSTOMIZATION_NAMING", "FULLY_CUSTOM_NAMING"],
        "text": (
            "Three index-definition categories, each with a documented naming pattern: (1) "
            "Out-of-the-box (OOTB) index - predefined AEM indexes, documented examples "
            "/oak:index/cqPageLucene-2 and /oak:index/damAssetLucene-8; (2) Customization of an "
            "OOTB index - append -custom-<number> to the OOTB index name, documented example "
            "/oak:index/damAssetLucene-8-custom-1 as a customization of "
            "/oak:index/damAssetLucene-8 (typically a copy of the OOTB index plus additional "
            "indexed properties); (3) Fully custom index - an entirely new index, also ending "
            "in -custom-<number>, with a distinguishing prefix to avoid naming conflicts, "
            "documented example /oak:index/acme.product-1-custom-2 with prefix 'acme.'. These "
            "example version numbers are illustrative documentation examples, not asserted "
            "current product-version numbers to be reused literally."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_dam_asset_index_guidance_20",
        "url": CLOUDINDEXING_URL + "#changes-to-out-of-the-box-indexes", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "OOTB_INDEX_EVOLUTION", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | Changes to Out-of-the-Box Indexes",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["OOTB_CHANGE_AUTO_MERGES_CUSTOMIZATION", "USE_LATEST_MERGED_BASELINE"],
        "text": (
            "When Adobe changes an OOTB index (for example damAssetLucene or cqPageLucene), a "
            "new versioned index (for example damAssetLucene-2 or cqPageLucene-2) is created; "
            "if the prior index version was already customized, that customization is "
            "AUTOMATICALLY MERGED with the OOTB changes into the new version - customers do not "
            "need to take action for the automatic merge itself. If further customization is "
            "needed later, the documented guidance is to use the LATEST (already-merged) "
            "version as the new customization baseline, not an older pre-merge definition - "
            "this matters especially in environments on different AEM release versions (e.g. "
            "dev on a newer release than stage/prod), where the applicable baseline can differ "
            "per environment. This is directly relevant to AEM Guides Assets search "
            "customization since damAssetLucene is the index most likely to need DITA/UUID "
            "property additions - platform guidance strongly discourages adding a competing new "
            "full-text index on dam:Asset instead of customizing the existing damAssetLucene "
            "index with the required additional properties."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_rolling_deployment_lifecycle_21",
        "url": CLOUDINDEXING_URL + "#what-are-rolling-deployments", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "ROLLING_INDEX_DEPLOYMENT", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | What are Rolling Deployments",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "LIFECYCLE",
        "relations": ["ZERO_DOWNTIME", "OLD_AND_NEW_VERSIONS_COEXIST"],
        "text": (
            "A rolling deployment allows zero-downtime upgrades with fast rollback: the OLD "
            "application version continues running at the same time as the NEW application "
            "version during the transition. Combined with the two-index-set model, the old "
            "application version keeps using its old index set while the new version's index "
            "is built/reindexed; only once the new index is ready does the new application "
            "version take traffic and start using the new index set. Index deployment is "
            "therefore never modeled as an instantaneous property update - it is a "
            "build/reindex-then-cutover lifecycle."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_reindexing_not_instant_22",
        "url": CLOUDINDEXING_URL + "#what-is-index-management", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "REINDEXING", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | What is Index Management",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "BEHAVIOR",
        "relations": ["REPOSITORY_SCAN_REQUIRED", "NOT_A_RUNTIME_REINDEX_FLAG"],
        "text": (
            "Index management covers adding, removing, and changing indexes. Changing an index "
            "DEFINITION is fast, but applying that change - called 'building an index', or for "
            "an existing index, 'reindexing' - requires time, because the repository must be "
            "scanned for the data to be indexed; it is NOT instantaneous. On Cloud Service, this "
            "reindex/build work happens through the deployment infrastructure before traffic "
            "switches to the new application/index version (see "
            "cloudindexing_rolling_deployment_lifecycle_21) - it is not a runtime `reindex=true` "
            "flag users set as a normal Cloud procedure. Reindexing (an Oak/Lucene index "
            "rebuild) is a distinct concept from DITA metadata extraction (an AEM Guides "
            "content-preprocessing workflow) - the two operate at different layers."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_versioning_change_undo_23",
        "url": CLOUDINDEXING_URL + "#changing-an-index", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "INDEX_DEFINITION_VERSIONING", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | Changing an Index / Undoing a Change",
        "record_type": "STATE_MACHINE", "content_type": "LIFECYCLE",
        "relations": ["NEW_VERSION_NOT_IN_PLACE_MUTATION", "UNDO_VIA_COPY_OF_PRIOR_VERSION"],
        "text": (
            "Changing an existing index means adding a NEW index with the changed definition, "
            "not mutating the old one in place - documented example: changing "
            "/oak:index/acme.product-1-custom-1 results in a new /oak:index/acme.product-1-"
            "custom-2; the old application version keeps using -custom-1 while the new "
            "application version uses -custom-2. Undoing a bad or unneeded change follows the "
            "same versioned pattern rather than restoring history in place: documented example, "
            "if damAssetLucene-8-custom-3 contains a mistake, you do not revert -custom-3 "
            "itself - you create a NEW index damAssetLucene-8-custom-4 that is a COPY of the "
            "prior good definition damAssetLucene-8-custom-2. This is a versioned rollback that "
            "preserves index-definition history, not a deletion of any past version."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_removal_and_gc_24",
        "url": CLOUDINDEXING_URL + "#removing-an-index", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "INDEX_REMOVAL", "heading_path": "Content Search and Indexing | Index Management using Rolling Deployments | Removing an Index",
        "record_type": "STATE_MACHINE", "content_type": "LIFECYCLE",
        "relations": ["OOTB_INDEX_CANNOT_BE_REMOVED", "SEVEN_DAY_GRACE_PERIOD_SUBJECT_TO_CHANGE"],
        "text": (
            "Removal only applies to customizations of OOTB indexes and to fully custom indexes "
            "- the ORIGINAL OOTB index itself CANNOT be removed, since AEM uses it directly. "
            "Because index definitions are treated as immutable once deployed, 'removing' a "
            "customization/fully-custom index means deploying a NEW version whose definition "
            "effectively simulates the removal (for a customization, this typically means "
            "reverting to the OOTB index's own definition as the 'new version', per the "
            "documented Undoing a Change pattern) - never direct repository deletion of the "
            "index node as the supported Cloud procedure. Once a new version is deployed, the "
            "prior version stops being used by queries but is NOT immediately deleted - it "
            "becomes eligible for a periodic cleanup/garbage-collection mechanism only after a "
            "grace period intended to allow recovery from mistakes. The source currently "
            "documents this grace period as 7 days from when the index was removed, but "
            "explicitly states this is SUBJECT TO CHANGE - store this as a DOCUMENTED_CURRENT "
            "value, not a fixed universal SLA."
        ),
    },
    {
        "common": COMMON_PLATFORM,
        "chunk_id": "cloudindexing_query_optimization_25",
        "url": CLOUDINDEXING_URL + "#index-query-optimizations", "canonical_url": CLOUDINDEXING_URL,
        "source_title": "Content Search and Indexing",
        "capability": "INDEX_AND_QUERY_OPTIMIZATION", "heading_path": "Content Search and Indexing | Index and Query Optimizations",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["QUERY_WITHOUT_INDEX_LOGS_WARNING"],
        "text": (
            "Apache Jackrabbit Oak provides flexible index configuration for efficient search "
            "queries; indexes are especially important for larger repositories. A query without "
            "a suitable backing index may read thousands of repository nodes, which is logged "
            "as a warning. Ensure all queries (including any DITA-Element or UUID predicate "
            "query relying on serialized/extracted metadata) are backed by an appropriate index. "
            "The source does not state exact performance thresholds - this is general "
            "operational guidance, not a numeric SLA to assert in an acceptance criterion."
        ),
    },
]


def build_full_records() -> list[dict]:
    out = []
    for r in RECORDS:
        content = r["text"]
        checksum = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        common = r["common"]
        rec = {**common, **{k: v for k, v in r.items() if k not in ("text", "common")}, "id": r["chunk_id"],
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

python3 ingest_ditasearch_uuid_cloudindexing.py
