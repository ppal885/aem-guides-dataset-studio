"""Curated RAG ingestion: content management + upload + file management + asset
processing + non-UUID->UUID migration (4.3 / 4.6 runbooks) + on-prem->cloud CTT +
compatibility/benchmark matrix + DITA-OT specialization + user/group security.

Grounded from the Experience League AEM Guides docs (11 sources). Curated -- one
chunk per distinct, retrievable capability. Version-specific distinctions are kept
SEPARATE on purpose (do NOT merge 4.3.x and 4.6.x runbooks; NON_UUID_TO_UUID !=
ON_PREM_TO_CLOUD; benchmark != SLA; group != ACL; DITA profile != Folder Profile).

Run from backend/ so `import app...` resolves:
    cd backend && python ingest_content_migration_ditaot_security.py
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.services.embedding_service import embed_texts  # noqa: E402
from app.services import vector_store_service as vss  # noqa: E402

MANIFEST_PATH = Path("storage/aem_guides_doc_chunks.json")
PARSER_VERSION = "curated-2026-09-01-migration-ditaot-security-v1"
RETRIEVED_AT = "2026-09-01"

BASE = "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"

COMMON = {
    "source_type": "EXPERIENCE_LEAGUE",
    "authority": "AEM_GUIDES_DOC",
    "product": "AEM_GUIDES",
    "retrieved_at": RETRIEVED_AT,
    "parser_version": PARSER_VERSION,
}

RECORDS = [
    # ---- SOURCE 1/2: manage content + upload ------------------------------
    {
        "chunk_id": "guides-managecontent-overview",
        "url": BASE + "user-guide/appendix/manage-content/authoring",
        "source_title": "Manage content (authoring)",
        "capability": "content_management",
        "heading_path": ["Manage content"],
        "record_type": "capability_overview",
        "content_type": "concept",
        "relations": ["upload_existing_files", "file_management", "asset_processing"],
        "text": (
            "AEM Guides content management covers authoring, uploading existing files, "
            "file/folder operations (copy, move, drag-and-drop), and asset processing. "
            "DITA content lives in the DAM (/content/dam); publishing and DITA resources "
            "also use /var/dxml. In a UUID-based repository every DITA asset carries a UUID "
            "that identity- and reference-tracking depend on, so copy/move/upload behavior "
            "differs between human-readable and UUID-pattern filenames."
        ),
    },
    {
        "chunk_id": "guides-upload-existing-files",
        "url": BASE + "user-guide/appendix/manage-content/authoring-upload-existing-files",
        "source_title": "Upload existing files",
        "capability": "content_upload",
        "heading_path": ["Manage content", "Upload existing files"],
        "record_type": "task",
        "content_type": "task",
        "relations": ["file_management", "asset_processing", "create_new_version_on_upload"],
        "text": (
            "Users upload existing DITA topics, maps, images, and other assets into the AEM "
            "Guides repository. On upload of an already-existing file, options such as "
            "Overwrite Existing File(s) and Keep Both File(s) govern whether a new UUID is "
            "assigned. Optional admin features 'Create New Version for Uploaded File' and "
            "'Overwrite Checked out File on Upload' change upload outcomes and must be "
            "enabled by an administrator."
        ),
    },
    # ---- SOURCE 3: file management copy/move UUID matrix -------------------
    {
        "chunk_id": "guides-filemgmt-copy-humanreadable",
        "url": BASE + "user-guide/appendix/manage-content/authoring-file-management",
        "source_title": "File management",
        "capability": "file_copy_uuid",
        "heading_path": ["File management", "Copy", "Human-readable filenames"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["file_move", "upload_existing_files", "uuid_identity"],
        "text": (
            "Copy of a file with a human-readable filename: if no same-name file exists in the "
            "destination, a new copy is created with the same name and a NEW UUID is assigned. "
            "If a same-name file already exists, a new copy is created with a numeric suffix "
            "(like filename0.extension) and a new UUID. For folders of human-readable files, "
            "the copied folder is suffixed (foldername0), files get new UUIDs, and file names "
            "are unchanged."
        ),
    },
    {
        "chunk_id": "guides-filemgmt-copy-uuidpattern",
        "url": BASE + "user-guide/appendix/manage-content/authoring-file-management",
        "source_title": "File management",
        "capability": "file_copy_uuid",
        "heading_path": ["File management", "Copy", "UUID-pattern filenames"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["file_move", "uuid_identity"],
        "text": (
            "Copy of a file whose filename is based on a UUID pattern: a new copy is always "
            "created with a NEW UUID, and the file name is set to the new UUID (the name "
            "changes because the name mirrors the UUID). For folders of UUID-pattern files, a "
            "new copy of the folder is created (suffixed when a same-name folder exists, same "
            "name otherwise), every file gets a new UUID, and file names change to match the "
            "new UUIDs."
        ),
    },
    {
        "chunk_id": "guides-filemgmt-dragdrop-overwrite-keepboth",
        "url": BASE + "user-guide/appendix/manage-content/authoring-file-management",
        "source_title": "File management",
        "capability": "file_dragdrop",
        "heading_path": ["File management", "Drag-and-drop"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["file_copy_uuid", "checkout_lock", "create_new_version_on_upload"],
        "text": (
            "Drag-and-drop at the SAME location offers Overwrite Existing File(s) or Keep Both "
            "File(s). Overwrite replaces the current working version at the original location "
            "and does NOT create or change the UUID; Keep Both creates a suffixed copy "
            "(filename0.extension) with a new UUID. If the existing file is checked out for "
            "edits by another user, overwrite on upload FAILS with an error unless the admin "
            "'Overwrite Checked out File on Upload' feature is enabled. Drag-and-drop at a "
            "DIFFERENT location assigns a new UUID (same file name); the 'Move File(s) to New "
            "Location' option overwrites the target while preserving references to and from "
            "the file."
        ),
    },
    {
        "chunk_id": "guides-filemgmt-bulk-move-tool",
        "url": BASE + "user-guide/appendix/manage-content/authoring-file-management",
        "source_title": "File management",
        "capability": "bulk_move_tool",
        "heading_path": ["File management", "Bulk Move Tool"],
        "record_type": "capability_overview",
        "content_type": "concept",
        "relations": ["reference_integrity", "asset_processing"],
        "text": (
            "The Bulk Move Tool lets an administrator move a folder with a large number of "
            "files from one repository location to another in batches, and it auto-handles "
            "(maintains) references to and from the files being moved. The batch size is "
            "tunable so bulk moves do not hamper concurrent authoring and publishing."
        ),
    },
    # ---- SOURCE 4: asset processing state machine -------------------------
    {
        "chunk_id": "guides-asset-processing-overview",
        "url": BASE + "user-guide/appendix/manage-content/asset-processor",
        "source_title": "Asset processing (Bulk Processor)",
        "capability": "asset_processing",
        "heading_path": ["Asset processing"],
        "record_type": "capability_overview",
        "content_type": "concept",
        "relations": ["bulk_processor", "publishing", "report_generation"],
        "text": (
            "Guides asset processing (via the Bulk Processor tile under Tools > Guides) "
            "reprocesses user-specific assets that failed initial processing or were never "
            "triggered, at folder level. The system auto-triggers asset processing for "
            "/content/dam every 15 minutes, picking up assets newly added or left unprocessed "
            "in the last 15-minute interval. Selective folder-level processing avoids "
            "unnecessary computation and speeds critical operations such as publishing and "
            "report generation; large datasets should be processed off-peak."
        ),
    },
    {
        "chunk_id": "guides-asset-processing-newprocess-dialog",
        "url": BASE + "user-guide/appendix/manage-content/asset-processor",
        "source_title": "Asset processing (Bulk Processor)",
        "capability": "asset_processing",
        "heading_path": ["Asset processing", "New process"],
        "record_type": "task",
        "content_type": "task",
        "relations": ["asset_type_filter", "concurrency_guard"],
        "text": (
            "New Process in the Bulk Processor takes: Feature Type (Asset processing), folders "
            "and files to process, optional sub-folders to ignore, Asset Type (DITA Topic, "
            "DITA Map, Markdown, HTML/CSS, DITAVAL, or other files - only the selected type is "
            "processed), and optional Created after/Created before date filters. Concurrency "
            "guard: if a process is already running for a folder, you cannot start a new "
            "process for the same folder until the current task completes."
        ),
    },
    {
        "chunk_id": "guides-asset-processing-task-options",
        "url": BASE + "user-guide/appendix/manage-content/asset-processor",
        "source_title": "Asset processing (Bulk Processor)",
        "capability": "asset_processing",
        "heading_path": ["Asset processing", "Task options"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["view_logs", "execution_id"],
        "text": (
            "Bulk Processor lists only the last five migrations. Hovering an Execution ID "
            "exposes: Restart (restart a previously successful task), Resume (resume a "
            "cancelled or failed task), Cancel (cancel an in-progress task), and View logs. "
            "For in-progress tasks the log shows detailed processing info including estimated "
            "time remaining and asset status; the log list displays up to the latest 500 "
            "entries and the full log can be downloaded. Status values are In progress, "
            "Completed, or Cancelled."
        ),
    },
    # ---- SOURCE 7: compatibility matrix + benchmark -----------------------
    {
        "chunk_id": "guides-nonuuid-uuid-compat-matrix",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/uuid-non-uuid",
        "source_title": "non-UUID to UUID: compatibility matrix",
        "capability": "nonuuid_to_uuid_routing",
        "heading_path": ["Migrate non-UUID to UUID", "Compatibility matrix"],
        "record_type": "routing_rule",
        "content_type": "reference",
        "relations": ["migration_4_3", "migration_4_6"],
        "text": (
            "You migrate non-UUID content to UUID based on your CURRENT Guides version; a "
            "compatibility matrix determines the correct migration path. Two documented "
            "runbook routes: 4.3.1 non-UUID -> 4.3.2 UUID, and 4.6.0 Service Pack 4 non-UUID "
            "-> 4.6.1 UUID. Pick the runbook that matches your source version; do not mix the "
            "two package sets."
        ),
    },
    {
        "chunk_id": "guides-nonuuid-uuid-benchmark",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/uuid-non-uuid",
        "source_title": "non-UUID to UUID: migration time estimation",
        "capability": "migration_benchmark",
        "heading_path": ["Migrate non-UUID to UUID", "Migration time estimation"],
        "record_type": "benchmark",
        "content_type": "reference",
        "relations": ["nonuuid_to_uuid_routing"],
        "text": (
            "Migration time estimate (benchmark, NOT a contractual SLA): the migration utility "
            "processes assets at an average rate of ~50 ms per asset. The published time table "
            "assumes a system configured with 64 vCPUs, 128 GB RAM, and SSD-backed storage. "
            "Memory requirements may increase for larger repositories or assets with many "
            "renditions or high-resolution binaries."
        ),
    },
    # ---- SOURCE 8: 4.3.1 -> 4.3.2 runbook (KEEP SEPARATE) -----------------
    {
        "chunk_id": "guides-migration-431-to-432-packages",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-4-3",
        "source_title": "4.3.1 non-UUID to 4.3.2 UUID migration",
        "capability": "migration_4_3",
        "heading_path": ["Migrate non-UUID to UUID", "4.3.1 to 4.3.2"],
        "record_type": "runbook",
        "content_type": "task",
        "relations": ["nonuuid_to_uuid_routing", "migration_infra_readiness"],
        "text": (
            "4.3.1 non-UUID -> 4.3.2 UUID runbook. Versions before 4.3.1 must first upgrade to "
            "4.3.1; versions later than 4.3.1 are NOT supported for this migration. Packages "
            "(from Adobe Software Distribution): UUID build com.adobe.fmdita-6.5-uuid-"
            "4.3.2.1977.zip; pre-migration package com.adobe.guides.pre-uuid-migration-"
            "1.2.27.zip (installed over 4.3.1); uuid migration upgrade package "
            "com.adobe.guides.uuid-upgrade-1.2.110.zip. Administrator permission is required. "
            "Fix files with errors before migrating; re-run the compatibility check after "
            "fixing. Configure Validations (select map + preset) captures pre-migration output "
            "so post-migration output can be validated, including baselines and versions."
        ),
    },
    {
        "chunk_id": "guides-migration-infra-readiness",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-4-3",
        "source_title": "non-UUID to UUID migration: infrastructure readiness",
        "capability": "migration_infra_readiness",
        "heading_path": ["Migrate non-UUID to UUID", "Infrastructure readiness"],
        "record_type": "prerequisite",
        "content_type": "reference",
        "relations": ["migration_4_3", "migration_4_6", "migration_benchmark"],
        "text": (
            "Infrastructure readiness for non-UUID->UUID migration: upsize the author instance "
            "CPU and memory for bulk activity - roughly double the current allocation (example: "
            "8 vCPU / 24 GB heap -> double). Overall disk and temporary disk (crx-quickstart) "
            "should have a buffer of ~10x current consumption; reclaim space with compaction "
            "afterward, and run Offline Tar compaction before starting. Ensure no indexing or "
            "system maintenance is scheduled during the migration window."
        ),
    },
    # ---- SOURCE 9: 4.6.0 SP4 -> 4.6.1 runbook (KEEP SEPARATE) -------------
    {
        "chunk_id": "guides-migration-46sp4-to-461-packages",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-uuid-4-6",
        "source_title": "4.6.0 SP4 non-UUID to 4.6.1 UUID migration",
        "capability": "migration_4_6",
        "heading_path": ["Migrate non-UUID to UUID", "4.6.0 SP4 to 4.6.1"],
        "record_type": "runbook",
        "content_type": "task",
        "relations": ["nonuuid_to_uuid_routing", "migration_infra_readiness", "dita_asset_backup"],
        "text": (
            "4.6.0 Service Pack 4 non-UUID -> 4.6.1 UUID runbook. Versions before 4.6.0 SP4 "
            "must first upgrade to 4.6.0 SP4; a Service Pack released AFTER 4.6.0 SP4 must be "
            "uninstalled to revert to 4.6.0 SP4 before migrating. Packages (from Adobe "
            "Software Distribution): UUID build com.adobe.fmdita.feature-uuid-4.6.1.5886.zip; "
            "pre-migration package com.adobe.guides.pre-uuid-migration-2.0.zip; uuid migration "
            "upgrade package com.adobe.guides.uuid-upgrade-2.0.zip. Run the migration UI at "
            "http://<server-name>/libs/fmdita/clientlibs/xmleditor_uuid_upgrade/page.html and "
            "choose System upgrade. Migrate all data at once (batching is handled internally); "
            "only non-DITA files not used by any DITA asset can be skipped."
        ),
    },
    {
        "chunk_id": "guides-migration-dita-asset-backup",
        "url": BASE + "install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-uuid-4-6",
        "source_title": "non-UUID to UUID migration: DITA asset backup",
        "capability": "dita_asset_backup",
        "heading_path": ["Migrate non-UUID to UUID", "Enable DITA asset backup"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["migration_4_6"],
        "text": (
            "'Enable DITA asset backup' during the 4.6 migration creates a per-file backup "
            "under /content/uuid-upgrade used to roll back a file whose migration errors. The "
            "backup is deleted once a file migrates successfully, but enabling backup slows "
            "the overall migration."
        ),
    },
    # ---- SOURCE 6: on-prem/AMS -> cloud via CTT (KEEP SEPARATE) -----------
    {
        "chunk_id": "guides-onprem-to-cloud-ctt-overview",
        "url": BASE + "install-conf-guide/migrate-content-cs/migrate-on-premise-content-cloud",
        "source_title": "Migrate on-premise content to cloud (CTT)",
        "capability": "onprem_to_cloud",
        "heading_path": ["Migrate to cloud", "Content Transfer Tool"],
        "record_type": "capability_overview",
        "content_type": "concept",
        "relations": ["ctt_migration_set", "cloud_limits"],
        "text": (
            "On-prem/AMS -> AEMaaCS migration uses Adobe's Content Transfer Tool (CTT), which "
            "transfers existing content AND principals (users/groups) automatically. This is a "
            "DIFFERENT workflow from non-UUID->UUID migration. In the Cloud Acceleration "
            "Manager you Create migration set, then Copy extraction key; on the on-prem "
            "instance (Tools > Operations > Content Migration > Content Transfer) you create a "
            "migration set and paste the extraction key to connect source and target and "
            "verify the key's validity. Enable 'Include versions' to migrate file versions."
        ),
    },
    {
        "chunk_id": "guides-onprem-to-cloud-ctt-paths",
        "url": BASE + "install-conf-guide/migrate-content-cs/migrate-on-premise-content-cloud",
        "source_title": "Migrate on-premise content to cloud (CTT paths)",
        "capability": "ctt_migration_set",
        "heading_path": ["Migrate to cloud", "Migration set paths"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["onprem_to_cloud", "cloud_limits"],
        "text": (
            "CTT migration-set path rules for Guides: /content/dam and /var/dxml MUST be "
            "migrated for Experience Manager Guides content. Restricted paths while creating a "
            "migration set: /apps, /libs, /home, /etc (some /etc paths are selectable). NOTE: "
            "an extraction key is a per-migration-set secret - it is NOT stored in this "
            "corpus; obtain it live from the Cloud Acceleration Manager."
        ),
    },
    {
        "chunk_id": "guides-cloud-repository-limits",
        "url": BASE + "install-conf-guide/migrate-content-cs/migrate-on-premise-content-cloud",
        "source_title": "AEMaaCS repository limits",
        "capability": "cloud_limits",
        "heading_path": ["Migrate to cloud", "Limits"],
        "record_type": "constraint",
        "content_type": "reference",
        "relations": ["onprem_to_cloud"],
        "text": (
            "AEMaaCS repository limits relevant to Guides migration: up to 20 TB repository "
            "size is supported, and the length of a JCR node name must be less than 150 bytes. "
            "Content that violates these limits must be remediated before/at migration."
        ),
    },
    # ---- SOURCE 10: DITA-OT specialization (DITA profile != Folder Profile)
    {
        "chunk_id": "guides-ditaot-custom-plugin-overview",
        "url": BASE + "install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "source_title": "DITA-OT configuration and custom plug-ins",
        "capability": "ditaot_custom_plugin",
        "heading_path": ["DITA-OT Configuration"],
        "record_type": "capability_overview",
        "content_type": "concept",
        "relations": ["ditaot_profile_properties", "ditaot_mathml", "ditaot_upload_repo"],
        "text": (
            "AEM Guides can import and use custom DITA-OT plug-ins for publishing. DITA-OT is "
            "the Java-based open-source toolkit that processes DITA maps/topics. A "
            "pre-configured DITA-OT Profile ships by default; you can create custom profiles "
            "with custom templates and plug-ins. NOTE: this DITA-OT 'Profile' is a publishing "
            "processing profile and is NOT the same as a Folder Profile (content access / "
            "folder-scoped configuration). Two ways to use a custom plug-in: upload it into "
            "the AEM repository, or keep it on the server and point a Profile at its location."
        ),
    },
    {
        "chunk_id": "guides-ditaot-mathml-fop",
        "url": BASE + "install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "source_title": "DITA-OT MathML rendering",
        "capability": "ditaot_mathml",
        "heading_path": ["DITA-OT Configuration", "MathML"],
        "record_type": "constraint",
        "content_type": "reference",
        "relations": ["ditaot_custom_plugin"],
        "text": (
            "The default DITA-OT package bundled with AEM Guides uses the Apache FOP XSL-FO "
            "processor, which does NOT render MathML equations. To publish content containing "
            "MathML you must integrate a MathML rendering engine plug-in for Apache FOP, or "
            "use a different XSL-FO processor."
        ),
    },
    {
        "chunk_id": "guides-ditaot-upload-repo-rules",
        "url": BASE + "install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "source_title": "DITA-OT upload rules",
        "capability": "ditaot_upload_repo",
        "heading_path": ["DITA-OT Configuration", "Upload custom plug-in"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["ditaot_custom_plugin", "ditaot_profile_properties"],
        "text": (
            "Uploading a custom DITA-OT plug-in: run the DITA-OT integrator on Mac/Linux (file "
            "separators differ from Windows; a plug-in integrated on Mac/Linux works on both). "
            "Re-zip keeping the same name DITA-OT.ZIP and folder structure (must contain a "
            "'DITA-OT' folder). The ZIP must be mimeType nt:file; upload it via a WebDAV tool "
            "or code deployment (NOT AEM's Package Manager, because it is an archive, not a "
            "content package). Do not overwrite the default DITA-OT package; upload the custom "
            "package under /var/dxml/dita_resources/dita-ot. Cloud Manager pipeline deployment "
            "is also supported."
        ),
    },
    {
        "chunk_id": "guides-ditaot-profile-properties",
        "url": BASE + "install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "source_title": "DITA-OT profile properties",
        "capability": "ditaot_profile_properties",
        "heading_path": ["DITA-OT Configuration", "Profile properties"],
        "record_type": "reference",
        "content_type": "reference",
        "relations": ["ditaot_custom_plugin", "ditaot_timeout"],
        "text": (
            "Custom DITA-OT profile properties include: Profile Name; Reuse Output (skip "
            "re-extracting the DITA-OT package); Profile Extract Path (disk path where DITA-OT "
            "is kept); Assigned Path (repository paths the profile applies to, multiple "
            "allowed); DITA-OT PDF Arguments (for all custom profiles specify -lib "
            "plugins/org.dita.pdf2.fop/lib/); DITA-OT AEM Arguments; DITA-OT Library Paths; "
            "DITA-OT Build XML; DITA-OT Ant Script Folder; DITA-OT Environment Variables "
            "(defaults ANT_OPTS, ANT_HOME, PATH, CLASSPATH; reuse via ${...}); Overwrite "
            "DITA-OT Output (keep selected); AEM DITA-OT Zip Path; DITA-OT Plug-in Path; "
            "Integrate Catalogs and Add System ID Catalog for custom DTD/XSD; DITA-OT "
            "Temporary Path (default <AEM-Install>/crx-quickstart/profiles/ditamaps - do NOT "
            "change). Installer env vars DITAOT_DIR and DITAMAP_DIR expose the DITA-OT and map "
            "extraction paths."
        ),
    },
    {
        "chunk_id": "guides-ditaot-timeout",
        "url": BASE + "install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "source_title": "DITA-OT timeout",
        "capability": "ditaot_timeout",
        "heading_path": ["DITA-OT Configuration", "DITA-OT Timeout"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["ditaot_profile_properties"],
        "text": (
            "DITA-OT Timeout is the time (in seconds) AEM Guides waits for a response from the "
            "DITA-OT plug-in. If no response arrives in that time, AEM Guides TERMINATES the "
            "publishing task and flags it as failed, with failure details in the output "
            "generation log. Default value: 300 seconds (5 minutes)."
        ),
    },
    # ---- SOURCE 11: user/group security (group != ACL) --------------------
    {
        "chunk_id": "guides-security-oob-groups",
        "url": BASE + "install-conf-guide/user-group-sec-cs/user-admin-sec",
        "source_title": "User management: out-of-the-box groups",
        "capability": "user_groups",
        "heading_path": ["User Management", "Groups created by AEM Guides"],
        "record_type": "reference",
        "content_type": "reference",
        "relations": ["group_permissions_matrix", "translation_review_prereq", "publisher_acls"],
        "text": (
            "AEM Guides ships three out-of-the-box user groups: Authors, Reviewers, and "
            "Publishers. Capability depends on group membership - e.g. only a Publisher can "
            "publish; an Author can create topics; a Reviewer can only review. A user group is "
            "a role bucket; it is DISTINCT from JCR path ACLs (read/write permissions on "
            "folders), which are granted separately."
        ),
    },
    {
        "chunk_id": "guides-security-group-permission-matrix",
        "url": BASE + "install-conf-guide/user-group-sec-cs/user-admin-sec",
        "source_title": "User management: task/group permission matrix",
        "capability": "group_permissions_matrix",
        "heading_path": ["User Management", "Task vs group matrix"],
        "record_type": "reference",
        "content_type": "reference",
        "relations": ["user_groups"],
        "text": (
            "Task-to-group matrix (Authors / Reviewers / Publishers). Authors AND Publishers "
            "can: create DITA topic/map, map collections, create review task, key resolution, "
            "check-out/check-in, edit/move/copy/delete/share topic, edit topic properties. "
            "Reviewers can review a topic (all three groups can change document state). In the "
            "DITA map console: only Publishers generate output, edit/duplicate/create/delete "
            "output presets, create/edit/duplicate/remove baselines, and create/edit condition "
            "presets; Authors and Publishers can view generated output, create/edit topic "
            "review tasks, and view Reports. Only Publishers create/edit document state "
            "profiles."
        ),
    },
    {
        "chunk_id": "guides-security-translation-review-prereq",
        "url": BASE + "install-conf-guide/user-group-sec-cs/user-admin-sec",
        "source_title": "User management: translation/review prerequisites",
        "capability": "translation_review_prereq",
        "heading_path": ["User Management", "Additional notes on user groups"],
        "record_type": "prerequisite",
        "content_type": "reference",
        "relations": ["user_groups", "publisher_acls"],
        "text": (
            "Group prerequisites for workflows: to START a translation or review workflow a "
            "user must belong to BOTH the Publishers and projects-administrators groups. Users "
            "need read, create, delete, and modify permissions on the source AND target "
            "language folders. To let project members see teammates / create tasks or "
            "workflows, they need read access on /home/users and /home/groups (e.g. via the "
            "projects-users group). Reviewers can access/add review comments only while the "
            "review task is open."
        ),
    },
    {
        "chunk_id": "guides-security-publisher-default-acls",
        "url": BASE + "install-conf-guide/user-group-sec-cs/user-admin-sec",
        "source_title": "User management: default publisher ACLs",
        "capability": "publisher_acls",
        "heading_path": ["User Management", "Publisher default permissions"],
        "record_type": "behavior_rule",
        "content_type": "reference",
        "relations": ["user_groups", "translation_review_prereq"],
        "text": (
            "By default Publishers get Read+Write on these DAM paths: /content/fmdita, "
            "/var/dxml, /content/dam/fmdita-outputs, and /content/output/sites. If you publish "
            "to any location other than these defaults, you must grant explicit read and write "
            "permissions to the publisher on that location. (Group membership alone does not "
            "grant path ACLs outside the defaults.)"
        ),
    },
    # ---- SOURCE 5: expert session (SUPPORTING only) -----------------------
    {
        "chunk_id": "guides-expertsession-nonuuid-to-uuid",
        "url": BASE + "knowledge-base/expert-session/migration-non-uuid-to-uuid",
        "source_title": "Expert session: migrate non-UUID to UUID",
        "capability": "expert_session_supporting",
        "heading_path": ["Expert session", "non-UUID to UUID"],
        "record_type": "supporting_reference",
        "content_type": "concept",
        "relations": ["nonuuid_to_uuid_routing", "migration_4_3", "migration_4_6"],
        "text": (
            "Expert session (Sep 26, 2024) on migrating AEM Guides content from a non-UUID to "
            "a UUID setup: covered benefits of UUID, readiness prerequisites, running the "
            "non-uuid->uuid migration, troubleshooting, and post-migration validation. This is "
            "SUPPORTING context (a session summary), not the authoritative runbook - defer to "
            "the version-specific 4.3.x/4.6.x migration articles for exact steps and packages."
        ),
    },
]


def build_full_records():
    out = []
    for rec in RECORDS:
        text = rec["text"].strip()
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        merged = {**COMMON, **rec}
        merged["canonical_url"] = rec["url"]
        merged["checksum"] = checksum
        merged["id"] = rec["chunk_id"]
        merged["content"] = text
        merged["title"] = rec["source_title"]
        merged["text"] = text
        out.append(merged)
    return out


def upsert_manifest(records):
    existing = []
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            existing = json.load(fh)
    by_id = {r.get("id") or r.get("chunk_id"): r for r in existing if isinstance(r, dict)}
    added = 0
    updated = 0
    for rec in records:
        key = rec["id"]
        if key in by_id:
            updated += 1
        else:
            added += 1
        by_id[key] = rec
    merged = list(by_id.values())
    tmp = MANIFEST_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for chunk in json.JSONEncoder(indent=2).iterencode(merged):
            fh.write(chunk)
    os.replace(tmp, MANIFEST_PATH)
    print(f"[manifest] added={added} updated={updated} total={len(merged)}")


def upsert_chroma(records):
    texts = [r["content"] for r in records]
    ids = [r["id"] for r in records]
    embeddings = embed_texts(texts)
    metadatas = []
    for r in records:
        md = {}
        for k, v in r.items():
            if k in ("content", "text"):
                continue
            if isinstance(v, list):
                md[k] = "|".join(str(x) for x in v)
            elif isinstance(v, (str, int, float, bool)) or v is None:
                md[k] = v
            else:
                md[k] = str(v)
        metadatas.append(md)
    vss.add_documents(
        vss.CHROMA_COLLECTION_AEM_GUIDES,
        ids=ids,
        documents=texts,
        metadatas=metadatas,
        embeddings=[e.tolist() for e in embeddings],
    )
    count = vss.get_collection_count(vss.CHROMA_COLLECTION_AEM_GUIDES)
    print(f"[chroma] upserted={len(ids)} collection_total={count}")


def main():
    records = build_full_records()
    print(f"[ingest] built {len(records)} curated records "
          f"(retrieved_at={RETRIEVED_AT}, parser={PARSER_VERSION})")
    upsert_manifest(records)
    upsert_chroma(records)
    print("[ingest] done.")


if __name__ == "__main__":
    main()
