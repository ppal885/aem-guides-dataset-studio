#!/usr/bin/env bash
# Paste this whole block into the VM terminal. Writes the ingestion script
# directly into backend/ and runs it there (avoids the `import app` module-
# resolution issue seen when running from outside backend/).
set -e
cd ~/aem-guides-dataset-studio/backend

cat > ingest_outputgen_assetmicro_sitestemplate.py << 'PYEOF'
"""Curated ingestion: AEM Guides Output-Generation Configuration, AEM Assets Cloud
Asset Microservices, and AEM Sites Template Installation/Preset Setup - 3 official
Experience League pages, kept as 3 independent canonical documents per the task's
requirement.

Text grounded in the live pages (fetched and parsed this run, main-descendants-
scoped extraction). Notable findings deliberately flagged rather than silently
normalized: (1) the output-history-purge-period source table renders with the PID
and property key merged into one malformed cell - exact property key/defaults are
NOT_ESTABLISHED from this page alone; (2) the AEM Sites On-Premise publish-path
literal is documented inconsistently on the same page (once without a /content/
prefix, once with it) - flagged as a genuine unresolved documentation
inconsistency, not normalized to either value; (3) the Blended-Publishing
topicContentNode default example value and the rendition-mapping missing-rendition
fallback chain were not captured with enough confidence to assert as fact.
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

SOURCE1_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
               "install-conf-guide/output-gen-config/conf-output-generation")
SOURCE2_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/"
               "content/assets/asset-microservices-overview")
SOURCE3_URL = ("https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
               "install-conf-guide/output-gen-config/conf-aem-sites-output/"
               "download-install-aem-sites-templates")
RETRIEVED_AT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PARSER_VERSION = "outputgen-assetmicro-sitestemplate-curated-ingest/1.0"
MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE", "authority": "OFFICIAL_PRODUCT_DOCUMENTATION",
    "product": "AEM_GUIDES", "domain": "OUTPUT_GENERATION_CONFIGURATION", "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE-1: Output-generation configuration ----
    {
        "chunk_id": "outputgen_hide_baseline_tab_01",
        "url": SOURCE1_URL + "#id223MD0D0YRM", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Hide baseline tab",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["PID_com.adobe.fmdita.config.ConfigManager", "PROPERTY_hide.tabs.baseline"],
        "text": (
            "To hide the Baseline tab in the AEM Guides Output panel, configure the "
            "com.adobe.fmdita.config.ConfigManager PID with property key hide.tabs.baseline "
            "(Boolean, default value: true) via Configuration overrides. The documented "
            "procedure uses the same shared Configuration-overrides tabbed flow for both Cloud "
            "Service and On-Premise - no evidence was found of separate default values per "
            "deployment type. On-Premise also documents an alternative path: open the AEM Web "
            "Console Configuration page, search for the com.adobe.fmdita.config.ConfigManager "
            "bundle, select the Hide Baseline Tab option, and click Save."
        ),
    },
    {
        "chunk_id": "outputgen_base_output_location_02",
        "url": SOURCE1_URL + "#configure-base-output-location-for-publishing", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure base output location for publishing",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["PID_com.adobe.fmdita.config.ConfigManager", "PROPERTY_base.output.path"],
        "text": (
            "The default repository location where AEM Guides stores generated output is "
            "controlled by the com.adobe.fmdita.config.ConfigManager PID, property key "
            "base.output.path, default value /content/dam/fmdita-outputs. Change it via "
            "Configuration overrides, or on On-Premise via the Web Console Configuration page "
            "for the same bundle."
        ),
    },
    {
        "chunk_id": "outputgen_blended_publishing_03",
        "url": SOURCE1_URL + "#id1691I0V0MGR", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Blended publishing",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["PROPERTY_topicContentNode", "libs_apps_overlay_required"],
        "text": (
            "Blended publishing lets an AEM Site that already contains non-DITA content publish "
            "DITA content to a predefined location within that same site, without modifying any "
            "existing non-DITA content - the ditacontent node is reserved to store the DITA "
            "content. Configuring it requires two steps: (1) configure the site template "
            "properties, and (2) add matching nodes to the existing site. Template properties "
            "are sourced from /libs/fmdita/config/templates/default via Package Manager; the "
            "documentation explicitly instructs NOT to customize files directly under the libs "
            "node - create an overlay under apps and edit only the apps copy. One property added "
            "on the template is topicContentNode (String type). The exact documented default "
            "example value for topicContentNode (and any topicHeadNode equivalent) was NOT "
            "captured with confidence in this extraction pass and should be treated as "
            "NOT_ESTABLISHED rather than assumed."
        ),
    },
    {
        "chunk_id": "outputgen_metadata_via_dita_ot_04",
        "url": SOURCE1_URL + "#id191LF0U0TY4", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure custom metadata for DITA-OT output",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["METADATA_SCHEMA_FORM_DRIVES_MAP_PROPERTIES_PAGE", "THREE_ROLE_WORKFLOW"],
        "text": (
            "AEM Guides supports passing custom metadata into DITA-OT-generated output through a "
            "3-role workflow: (1) an administrator adds the required metadata field so it "
            "appears on the DITA map's Properties page - done via AEM Tools > Assets > Metadata "
            "Schemas, selecting the default form (the documentation explicitly states the DITA "
            "map Properties page reads from this same default Metadata Schema form) and editing "
            "it to add the custom field; (2) an administrator separately adds the same custom "
            "metadata key to the metadata list so it also shows up in the DITA map console; "
            "(3) a Publisher then sets the custom metadata value on the DITA map and generates "
            "output. The exact metadata-list configuration path (metadataList / metadata.xml) "
            "and any pass.metadata.args.cmd.line style command-line argument were not "
            "independently confirmed against the live page in this extraction pass and should "
            "not be asserted as exact property names without further verification."
        ),
    },
    {
        "chunk_id": "outputgen_mapconsole_clientlib_extension_05",
        "url": SOURCE1_URL + "#id188HC08M0CZ", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Customize the DITA map console",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["CLIENTLIB_CATEGORY_apps.fmdita.dashboard-extn"],
        "text": (
            "The DITA map console can be extended (for example, to add custom reports not "
            "shipped with AEM Guides) by creating an AEM Client Library (ClientLib) categorized "
            "under apps.fmdita.dashboard-extn. Whenever the map console loads, any functionality "
            "registered under this category is executed and loaded automatically - this is the "
            "sole documented extension mechanism for the map console UI."
        ),
    },
    {
        "chunk_id": "outputgen_rendition_mapping_06",
        "url": SOURCE1_URL + "#id177BF0G0VY4", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure image rendition mapping",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["renditionmap.xml", "ATTRIBUTE_outputName_overrides_per_preset"],
        "text": (
            "Image rendition selection for generated output is controlled by "
            "/libs/fmdita/config/renditionmap.xml, where the mimetype element specifies the "
            "source MIME type and the rendition output element specifies both the target output "
            "format and the rendition name (example: cq5dam.web.1280.1280.jpeg). Renditions can "
            "be specified per supported output format: AEMSITE, PDF, HTML5, EPUB, and CUSTOM. A "
            "preset-specific override is possible via the outputName attribute: when outputName "
            "is set to a specific preset title (documented example: ditahtml5), that preset uses "
            "a distinct configured image such as the thumbnail rendition "
            "cq5dam.thumbnail.319.319.png, whereas if outputName is not specified, all HTML5 "
            "outputs fall back to the larger default rendition cq5dam.web.1280.1280.jpeg. The "
            "exact fallback chain when a configured rendition is entirely missing from the "
            "repository was NOT fully captured in this extraction pass and should not be "
            "asserted as fact without direct re-verification against the live page."
        ),
    },
    {
        "chunk_id": "outputgen_history_purge_07",
        "url": SOURCE1_URL + "#id19AAI070V8Q", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure output history purge period",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["SOURCE_TABLE_EXTRACTION_REQUIRES_VALIDATION", "PURGE_IMPACTS_ALL_MAPS_REPO_WIDE"],
        "text": (
            "Output generation logs and history are stored at /var/dxml/metadata/outputHistory "
            "in the repository. AEM Guides lets you configure a retention period after which "
            "these logs, along with the output generation history, are deleted from the "
            "repository; the documentation explicitly states that configuring this purge "
            "feature impacts output generation history for ALL DITA maps in the repository (not "
            "scoped per-map). The configuration is applied via the com.adobe.fmdita.config."
            "ConfigManager PID and a purge-period style property key. DATA-QUALITY FLAG: the raw "
            "extracted source table around this configuration rendered with the PID and property "
            "key merged/concatenated into a single malformed cell rather than as clean separate "
            "PID/Property-Key/Property-Value columns - a known source-table-rendering artifact "
            "on this page. The exact property key, default day count, and any "
            "zero-disables-purge or purge-does-not-delete-generated-output invariants must be "
            "re-verified directly against the live page before being asserted as QA facts; do "
            "not treat the malformed cell text as an authoritative property name."
        ),
    },
    {
        "chunk_id": "outputgen_history_list_limit_08",
        "url": SOURCE1_URL + "#id1679JH0H0O2", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure output history list limit",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["PID_com.adobe.fmdita.config.ConfigManager", "PROPERTY_output.historylimit"],
        "text": (
            "The maximum number of generated outputs displayed in the Outputs tab for a DITA map "
            "is controlled via Configuration overrides on the com.adobe.fmdita.config."
            "ConfigManager PID, property key output.historylimit (Integer, default value: 25)."
        ),
    },
    {
        "chunk_id": "outputgen_generation_pool_size_09",
        "url": SOURCE1_URL + "#id176LB050VUI", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure output generation processing pool size (On-Premise)",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["BUNDLE_com.adobe.fmdita.publish.manager.PublishThreadManagerImpl", "PROPERTY_Generation_Pool_Size"],
        "text": (
            "The number of output-generation processes that run concurrently is controlled by "
            "the Generation Pool Size setting on the com.adobe.fmdita.publish.manager."
            "PublishThreadManagerImpl bundle. By default the pool size equals the number of "
            "processing cores available on the system plus one. Setting the value to 1 forces "
            "sequential publishing: the first publishing task runs to completion while any "
            "subsequent publishing task is held in a publishing queue rather than running "
            "concurrently."
        ),
    },
    {
        "chunk_id": "outputgen_fmps_config_10",
        "url": SOURCE1_URL + "#id1678G0Z0TN6", "canonical_url": SOURCE1_URL,
        "source_title": "Configure output generation",
        "capability": "OUTPUT_GENERATION_CONFIG", "heading_path": "Configure output generation | Configure FrameMaker Publishing Server (FMPS)",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["BUNDLE_com.adobe.fmdita.config.ConfigManager", "CREDENTIAL_FIELDS_MUST_BE_REDACTED"],
        "text": (
            "AEM Guides can generate output via an external FrameMaker Publishing Server (FMPS), "
            "configured through properties on the com.adobe.fmdita.config.ConfigManager bundle "
            "in the Web Console: FMPS Login Domain and FMPS URL differ by FMPS version (FMPS "
            "2020 expects an IP address such as 192.168.1.101 and a URL of the form "
            "http://<fmps_ip>:<port>; FMPS 2019 and earlier expect a domain name or IP plus a URL "
            "of the form http://<fmps_ip>:<port>/fmserver/v1/); FMPS Version records the "
            "documented version string (2020, or 2019/2017 for earlier); FMPS Timeout is "
            "optional and defaults to 300 seconds (5 minutes), after which AEM Guides terminates "
            "the publishing task and flags it failed; External AEM URL is the optional AEM "
            "endpoint FMPS uses to place generated output files back. FMPS Username, Password, "
            "and any AEM admin credential fields must never be captured as literal values in QA "
            "evidence or test data - they are represented only as SECRET_REQUIRED / "
            "REDACTED_FIELD placeholders."
        ),
    },
    # ---- SOURCE-2: AEM Assets Cloud asset microservices ----
    {
        "chunk_id": "assetmicro_architecture_11",
        "url": SOURCE2_URL + "#asset-microservices-architecture", "canonical_url": SOURCE2_URL,
        "source_title": "Asset microservices overview",
        "capability": "ASSET_MICROSERVICES", "heading_path": "Asset microservices overview | Asset microservices architecture",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["DIRECT_BINARY_ACCESS", "EXTERNALIZED_PROCESSING", "CUSTOM_WORKFLOW_POST_PROCESSING_OPTIONAL"],
        "text": (
            "Asset ingestion and processing via asset microservices follows this flow: (1) a "
            "client (web browser or Adobe Asset Link) sends an upload request to Experience "
            "Manager and uploads the binary directly to the binary cloud storage; (2) once the "
            "direct binary upload completes, the client notifies Experience Manager; (3) "
            "Experience Manager sends a processing request to asset microservices, whose "
            "contents depend on the processing-profile configuration specifying which "
            "renditions to generate; (4) the asset-microservices back end dispatches the request "
            "to one or more microservices, each of which accesses the original binary directly "
            "from the binary cloud store; (5) processing results (renditions) are stored back in "
            "the binary cloud storage; (6) Experience Manager is notified that processing is "
            "complete, along with direct pointers to the generated rendition binaries, which "
            "then become available on the uploaded asset. If configured, Experience Manager can "
            "additionally start a custom workflow model for post-processing - for example "
            "fetching data from an enterprise system and adding it to asset properties. Two key "
            "architectural principles: Direct binary access (assets transport to/from the Cloud "
            "Binary Store directly, minimizing network load and duplicate binary storage) and "
            "Externalized processing (processing runs outside the Experience Manager environment "
            "so its CPU/memory resources stay available for core DAM functionality)."
        ),
    },
    {
        "chunk_id": "assetmicro_direct_binary_upload_12",
        "url": SOURCE2_URL + "#asset-upload-with-direct-binary-access", "canonical_url": SOURCE2_URL,
        "source_title": "Asset microservices overview",
        "capability": "ASSET_MICROSERVICES", "heading_path": "Asset microservices overview | Asset upload with direct binary access",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "BEHAVIOR",
        "relations": ["OOTB_CLIENTS_SUPPORT_BY_DEFAULT", "CUSTOM_CLIENTS_VIA_HTTP_APIS"],
        "text": (
            "All in-product Experience Manager clients - the web upload interface, Adobe Asset "
            "Link, and the Experience Manager desktop app - support direct binary access upload "
            "by default. Custom upload tools can also use this by working directly against "
            "Experience Manager HTTP APIs, either calling them directly or by using/extending the "
            "documented open-source upload library and open-source command-line tool that "
            "already implement the upload protocol."
        ),
    },
    # ---- SOURCE-3: AEM Sites template install/preset setup ----
    {
        "chunk_id": "sitestemplate_prerequisites_13",
        "url": SOURCE3_URL + "#prerequisites", "canonical_url": SOURCE3_URL,
        "source_title": "Download and install AEM Sites templates",
        "capability": "AEM_SITES_TEMPLATE_SETUP", "heading_path": "Download and install AEM Sites templates | Prerequisites",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "CONFIGURATION",
        "relations": ["CLOUD_REQUIRES_GUIDES_2502_PLUS", "ONPREM_REQUIRES_AEM65_SP19_20_21_AND_GUIDES_4.6.0_PLUS"],
        "text": (
            "Prerequisites differ by deployment tab. Cloud Service: a running AEM as a Cloud "
            "Service instance with AEM Guides 2502 or later; required permissions are Cloud "
            "Manager access to deploy packages, access to the Git repository associated with the "
            "environment, and permission to create/modify presets in AEM Guides; required "
            "downloads from the Software Distribution Portal are the components package "
            "(guides-components.all-1.x.0.zip) and the sites template (aemg-docs-1.x.0.zip). "
            "On-Premise: a running AEM 6.5 instance with Service Pack 19, 20, or 21 and AEM "
            "Guides 4.6.0 or later; required permissions are Software Distribution Portal "
            "access, CRX Package Manager access to install packages, and permission to "
            "create/modify presets in AEM Guides."
        ),
    },
    {
        "chunk_id": "sitestemplate_package_installation_14",
        "url": SOURCE3_URL + "#package-installation", "canonical_url": SOURCE3_URL,
        "source_title": "Download and install AEM Sites templates",
        "capability": "AEM_SITES_TEMPLATE_SETUP", "heading_path": "Download and install AEM Sites templates | Package installation (Cloud Service)",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["REQUIRES_jcr_root_apps_fmdita_install_STRUCTURE"],
        "text": (
            "On Cloud Service, installing the components package (guides-components.all-1.x.x."
            "zip) requires: (1) cloning the Git repository - navigate to Repositories in Cloud "
            "Manager, select Access Repo Info to copy the git clone command, then clone locally "
            "using the provided (or generated) credentials; (2) adding the package to a Maven "
            "bundle - in the local clone, create a new Maven bundle or reuse an existing one, "
            "ensure the /jcr_root/apps/fmdita/install directory structure exists in the Maven "
            "project, and place the downloaded guides-components.all-1.x.x.zip file into that "
            "install folder (then commit/deploy through the standard Cloud Manager pipeline)."
        ),
    },
    {
        "chunk_id": "sitestemplate_import_and_create_site_15",
        "url": SOURCE3_URL + "#create-site-using-installed-templates-for-cloud-service", "canonical_url": SOURCE3_URL,
        "source_title": "Download and install AEM Sites templates",
        "capability": "AEM_SITES_TEMPLATE_SETUP", "heading_path": "Download and install AEM Sites templates | Create a site using the installed template (Cloud Service)",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["CREATE_FROM_TEMPLATE_FLOW"],
        "text": (
            "To create a site from the installed sites template on Cloud Service: import the "
            "sites template first - go to the AEM Sites console (servername/sites.html/content), "
            "select Create > Site from Template, and import aemg-docs-1.x.x.zip via the Import "
            "option; then select the template (AEMG Docs 1.x.x) and select Next; enter the Site "
            "Title and Site Name; then select Create."
        ),
    },
    {
        "chunk_id": "sitestemplate_create_preset_16",
        "url": SOURCE3_URL + "#create-aem-site-preset", "canonical_url": SOURCE3_URL,
        "source_title": "Download and install AEM Sites templates",
        "capability": "AEM_SITES_TEMPLATE_SETUP", "heading_path": "Download and install AEM Sites templates | Create an AEM Sites output preset",
        "record_type": "CONFIGURATION_BEHAVIOR", "content_type": "WORKFLOW",
        "relations": ["MUST_UNCHECK_USE_LEGACY_COMPONENT_MAPPING", "PUBLISH_PATH_ONPREM_DOCUMENTED_INCONSISTENTLY"],
        "text": (
            "To create an AEM Sites preset: open a DITA map in AEM Guides, navigate to the "
            "Output panel, select Create Preset, select type AEM Sites, enter a preset name, "
            "UNCHECK the 'Use legacy component mapping' setting, and select Add. Configuring the "
            "preset then offers two options: Option 1 (Site Dropdown) - select the previously "
            "created site (for example 'AEMG Docs Site'), after which Publish path and Topic "
            "page template auto-populate (Topic page template auto-sets to 'Topic Page' in both "
            "deployment types); Option 2 (Site Path) - set the Site path manually instead of "
            "using the dropdown, after which Topic page template still auto-sets to 'Topic "
            "Page'. DOCUMENTED PATH-LITERAL INCONSISTENCY: the Cloud Service publish path is "
            "given as /content/AEMG-Docs-Site/en/docs/product, while the On-Premise publish path "
            "is given in one place on the same page as the relative-looking "
            "aemg-docs/en/docs/product1 (no leading /content/ segment, and using 'product1' "
            "rather than 'product') and elsewhere on the same page as "
            "/content/aemg-docs/en/docs/product1 with the /content/ prefix restored. This is a "
            "genuine, unresolved documentation inconsistency, not a normalization choice made "
            "during ingestion - treat the exact On-Premise publish-path literal as "
            "NOT_ESTABLISHED and verify directly against a live On-Premise instance before "
            "asserting it in an acceptance criterion."
        ),
    },
    {
        "chunk_id": "sitestemplate_generate_site_17",
        "url": SOURCE3_URL + "#generate-aem-sites", "canonical_url": SOURCE3_URL,
        "source_title": "Download and install AEM Sites templates",
        "capability": "AEM_SITES_TEMPLATE_SETUP", "heading_path": "Download and install AEM Sites templates | Generate the AEM Site",
        "record_type": "PUBLISHING_WORKFLOW", "content_type": "WORKFLOW",
        "relations": ["DEFAULT_GENERATION_PATH_CHANGEABLE_VIA_NEW_PRODUCT_PAGE"],
        "text": (
            "With the AEM Sites preset configured, generating output for the corresponding DITA "
            "map produces the site at /content/AEMG-Docs-Site/en/docs/product (Cloud Service) or "
            "at the On-Premise path documented (subject to the same path-literal inconsistency "
            "noted for preset configuration - see sitestemplate_create_preset_16). To change the "
            "default generation path instead of using the OOTB location, create a new product "
            "page under the OOTB site structure: navigate to AEM Sites, go to AEMG Docs > "
            "English > Docs, select the Home page tile, select Next, enter a Title and Name for "
            "the new page, and select Create - subsequent generation then targets this new page "
            "location."
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

python3 ingest_outputgen_assetmicro_sitestemplate.py
