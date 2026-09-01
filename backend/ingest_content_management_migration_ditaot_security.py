"""Single-pass ingestion for AEM Guides content, migration, DITA-OT, and security docs.

This module is intentionally an ingestion boundary.  It does not change the
test-plan/UAC generator, evidence-graph contracts, or production retrieval
prompts.  It fetches exactly the eleven configured Experience League pages,
creates deterministic semantic records, validates them in a batch-local
staging snapshot, and can then incrementally upsert the existing ``aem_guides``
Chroma collection and ``storage/aem_guides_doc_chunks.json`` manifest.

The batch keeps rich relationships and hidden-regression oracle candidates in
sidecars because the current evidence graph only permits Jira-owned QA-oracle
nodes.  Promoting these documentation oracles into that graph would require a
separate graph-contract change and is outside this ingestion task.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
import struct
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag


BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.schemas_canonical_test_plan_runtime import (  # noqa: E402
    AuthorityClass,
    CurrentnessState,
    EvidenceDirectness,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    ProductContractOwnership,
    ProductOwnership,
    SourceVisibility,
    VerificationState,
    VersionScope,
    VisibilityClass,
)


BATCH_ID = "aem-guides-content-migration-ditaot-security-v1"
PARSER_VERSION = "content-migration-ditaot-security-ingest/1.0"
SOURCE_TYPE = "EXPERIENCE_LEAGUE"
TENANT_ID = "public-aem-guides-docs"
COLLECTION_NAME = "aem_guides"

MANIFEST_PATH = BACKEND_ROOT / "storage" / "aem_guides_doc_chunks.json"
SNAPSHOT_DIR = (
    BACKEND_ROOT
    / "storage"
    / "corpus_snapshots"
    / "content_management_migration_ditaot_security"
)
STAGING_SNAPSHOT_PATH = SNAPSHOT_DIR / "staging.json"
ACTIVE_SNAPSHOT_PATH = SNAPSHOT_DIR / "active.json"
SOURCE_REGISTRY_PATH = SNAPSHOT_DIR / "source_registry.json"
RELATIONSHIP_PATH = SNAPSHOT_DIR / "relationships.json"
ORACLE_PATH = SNAPSHOT_DIR / "hidden_regression_oracles.json"
EVIDENCE_RECORDS_PATH = SNAPSHOT_DIR / "evidence_records.json"
STAGING_EVIDENCE_RECORDS_PATH = SNAPSHOT_DIR / "evidence_records.staging.json"
ACTIVATION_LOCK_PATH = MANIFEST_PATH.parent / ".aem_guides_activation.lock"
ACTIVATION_JOURNAL_PATH = SNAPSHOT_DIR / "activation_journal.json"
TRANSACTION_DIR = SNAPSHOT_DIR / "transactions"
HISTORY_DIR = SNAPSHOT_DIR / "history"
REPORT_PATH = (
    BACKEND_ROOT.parent
    / "analysis"
    / "content_management_migration_ditaot_security_ingestion_report.json"
)
RETRIEVAL_CONFIG_PATH = (
    BACKEND_ROOT
    / "config"
    / "content_management_migration_security_retrieval_v1.json"
)
EXTERNAL_ROUTE_REGISTRY = {
    "AEM_ASSETS_MICROSERVICES": {
        "target_source_id": "EXISTING-AEM-ASSETS-MICROSERVICES",
        "query_markers": ["cloud binary store", "asset microservices"],
        "forbidden_primary_capabilities": ["TARGETED_MANUAL_PROCESSING"],
    }
}


def protected_test_plan_runtime_hash() -> str:
    roots = [
        BACKEND_ROOT / "prompts",
        BACKEND_ROOT / "app" / "api" / "v1" / "routes" / "test_plans.py",
        BACKEND_ROOT / "app" / "api" / "v1" / "routes" / "uac_copilot.py",
        BACKEND_ROOT / "app" / "core" / "schemas_test_plan_pipeline.py",
        BACKEND_ROOT / "app" / "core" / "schemas_uac_intelligence.py",
        BACKEND_ROOT.parent / ".codex" / "skills" / "test-plan-generation",
    ]
    rows: list[tuple[str, str]] = []
    for root in roots:
        if root.is_file():
            rows.append((str(root.relative_to(BACKEND_ROOT.parent)), hashlib.sha256(root.read_bytes()).hexdigest()))
        elif root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    rows.append((str(path.relative_to(BACKEND_ROOT.parent)), hashlib.sha256(path.read_bytes()).hexdigest()))
    return sha256_text(stable_json(rows)) if rows else ""


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    label: str
    url: str
    authority_class: str
    currentness: str
    deployment_model: str = "UNKNOWN"
    source_version: str = "UNKNOWN"
    target_version: str = "UNKNOWN"
    migration_direction: str = "UNKNOWN"
    product_area: str = "UNKNOWN"
    default_capability: str = "UNKNOWN"
    authority_priority: int = 90


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        "SOURCE-1",
        "Manage content",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/manage-content/authoring",
        "OFFICIAL_CURRENT_PRODUCT_DOCUMENTATION",
        "CURRENT",
        product_area="CONTENT_MANAGEMENT",
        default_capability="CONTENT_MANAGEMENT_CONCEPTS",
    ),
    SourceSpec(
        "SOURCE-2",
        "Upload existing files",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/manage-content/authoring-upload-existing-files",
        "OFFICIAL_CURRENT_PRODUCT_DOCUMENTATION",
        "CURRENT",
        product_area="CONTENT_MANAGEMENT",
        default_capability="CONTENT_UPLOAD",
    ),
    SourceSpec(
        "SOURCE-3",
        "Manage files and folders",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/manage-content/authoring-file-management",
        "OFFICIAL_CURRENT_PRODUCT_DOCUMENTATION",
        "CURRENT",
        product_area="CONTENT_MANAGEMENT",
        default_capability="FILE_AND_FOLDER_MANAGEMENT",
    ),
    SourceSpec(
        "SOURCE-4",
        "Process assets / Guides Bulk Processor",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/manage-content/asset-processor",
        "OFFICIAL_CURRENT_PRODUCT_DOCUMENTATION",
        "CURRENT",
        product_area="CONTENT_MANAGEMENT",
        default_capability="ASSET_PROCESSING",
    ),
    SourceSpec(
        "SOURCE-5",
        "Expert session: non-UUID to UUID migration",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/expert-session/migration-non-uuid-to-uuid",
        "OFFICIAL_EXPERT_SESSION_GUIDANCE",
        "CURRENT_CONTEXT",
        deployment_model="ON_PREMISE_OR_AMS",
        migration_direction="NON_CLOUD_NON_UUID_TO_NON_CLOUD_UUID",
        product_area="MIGRATION",
        default_capability="NON_UUID_TO_UUID_ROUTING",
        authority_priority=60,
    ),
    SourceSpec(
        "SOURCE-6",
        "Migrate On-Premise / AMS content to Cloud Service",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/migrate-content-cs/migrate-on-premise-content-cloud",
        "OFFICIAL_ADMIN_MIGRATION_RUNBOOK",
        "CURRENT_PROCEDURE_FOR_APPLICABLE_ON_PREMISE_OR_AMS_TO_CLOUD_MIGRATION",
        deployment_model="ON_PREMISE_OR_AMS_TO_CLOUD_SERVICE",
        migration_direction="ON_PREMISE_OR_AMS_UUID_TO_CLOUD_SERVICE",
        product_area="MIGRATION",
        default_capability="ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER",
        authority_priority=95,
    ),
    SourceSpec(
        "SOURCE-7",
        "Non-UUID to UUID migration overview and compatibility matrix",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/migrate-content-cs/migration-process-on-prem/uuid-non-uuid",
        "OFFICIAL_MIGRATION_COMPATIBILITY_GUIDANCE",
        "VERSION_ROUTING_DOCUMENT",
        deployment_model="ON_PREMISE_OR_AMS",
        migration_direction="NON_UUID_TO_UUID",
        product_area="MIGRATION",
        default_capability="NON_UUID_TO_UUID_ROUTING",
        authority_priority=96,
    ),
    SourceSpec(
        "SOURCE-8",
        "4.3.1 non-UUID to 4.3.2 UUID migration",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-4-3",
        "OFFICIAL_VERSION_SPECIFIC_MIGRATION_RUNBOOK",
        "HISTORICAL_VERSION_SPECIFIC_BUT_SUPPORTED_FOR_THAT_PATH",
        deployment_model="ON_PREMISE_OR_AMS",
        source_version="4.3.1_NON_UUID",
        target_version="4.3.2_UUID",
        migration_direction="4.3.1_NON_UUID_TO_4.3.2_UUID",
        product_area="MIGRATION",
        default_capability="NON_UUID_TO_UUID_4_3_PATH",
        authority_priority=100,
    ),
    SourceSpec(
        "SOURCE-9",
        "4.6.0 SP4 non-UUID to 4.6.1 UUID migration",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/migrate-content-cs/migration-process-on-prem/non-uuid-uuid-4-6",
        "OFFICIAL_VERSION_SPECIFIC_MIGRATION_RUNBOOK",
        "HISTORICAL_VERSION_SPECIFIC_BUT_SUPPORTED_FOR_THAT_PATH",
        deployment_model="ON_PREMISE_OR_AMS",
        source_version="4.6.0_SP4_NON_UUID",
        target_version="4.6.1_UUID",
        migration_direction="4.6.0_SP4_NON_UUID_TO_4.6.1_UUID",
        product_area="MIGRATION",
        default_capability="NON_UUID_TO_UUID_4_6_PATH",
        authority_priority=100,
    ),
    SourceSpec(
        "SOURCE-10",
        "Custom DITA-OT and DITA specialization",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/custom-dita-ot-cs/dita-ot-specialization",
        "OFFICIAL_ADMIN_CONFIGURATION_DOCUMENTATION",
        "ASSERTION_LEVEL_CURRENTNESS_REQUIRED",
        deployment_model="CLOUD_SERVICE_AND_ON_PREMISE",
        product_area="DITA_OT_CONFIGURATION",
        default_capability="CUSTOM_DITA_OT_PLUGIN",
        authority_priority=95,
    ),
    SourceSpec(
        "SOURCE-11",
        "User administration and security",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/user-group-sec-cs/user-admin-sec",
        "OFFICIAL_SECURITY_AND_PERMISSION_CONFIGURATION",
        "CURRENT",
        deployment_model="CLOUD_SERVICE_AND_ON_PREMISE",
        product_area="SECURITY",
        default_capability="FEATURE_PERMISSION_MATRIX",
        authority_priority=100,
    ),
)

LEGACY_ANCHOR_INPUT = SOURCES[9].url + "#id181NH0YN0AX"


CAPABILITY_TAXONOMY: dict[str, tuple[str, ...]] = {
    "AEM_GUIDES_CONTENT_MANAGEMENT": (
        "CONTENT_MANAGEMENT_CONCEPTS",
        "DAM_ASSET_MANAGEMENT",
        "LINK_MANAGEMENT",
        "VERSION_MANAGEMENT",
        "NATIVE_DITA_HANDLING",
        "ROLE_AND_PERMISSION_OVERVIEW",
        "CONTENT_UPLOAD",
        "ASSETS_CONSOLE_UPLOAD",
        "ASSETS_UI_UPLOAD",
        "DESKTOP_APP_UPLOAD",
        "ASSET_BULK_INGESTOR",
        "FRAMEMAKER_BULK_UPLOAD",
        "UPLOAD_PROGRESS",
        "UPLOAD_CANCELLATION",
        "UPLOAD_FAILURE_REPORT",
        "DUPLICATE_UPLOAD_POLICY",
        "FILE_AND_FOLDER_MANAGEMENT",
        "COPY_FILE",
        "COPY_FOLDER",
        "DRAG_AND_DROP_FILE",
        "OVERWRITE_FILE",
        "KEEP_BOTH",
        "MOVE_FILE_TO_NEW_LOCATION",
        "BULK_MOVE_FOLDER",
        "REFERENCE_MAINTENANCE",
        "DITA_CONTENT_SEARCH",
        "CHECKOUT_STATUS_SEARCH",
        "DELETE_FILE",
        "MEDIA_VERSION_PREVIEW",
        "ASSET_PROCESSING",
        "AUTOMATIC_PROCESSING",
        "TARGETED_MANUAL_PROCESSING",
        "PROCESS_FILTERS",
        "PROCESS_STATE",
        "RESTART",
        "RESUME",
        "CANCEL",
        "VIEW_LOGS",
    ),
    "AEM_GUIDES_MIGRATION": (
        "NON_UUID_TO_UUID_ROUTING",
        "NON_UUID_TO_UUID_4_3_PATH",
        "NON_UUID_TO_UUID_4_6_PATH",
        "PREMIGRATION_ASSESSMENT",
        "PREMIGRATION_OUTPUT_VALIDATION",
        "VERSION_PURGE",
        "MIGRATION_INFRASTRUCTURE_READINESS",
        "MIGRATION_CONFIGURATION_FREEZE",
        "SYSTEM_UPGRADE",
        "DITA_ASSET_BACKUP",
        "MIGRATION_RERUN_AND_RESUME",
        "BASELINE_AND_REVIEW_UPGRADE",
        "MIGRATION_REPORT_ANALYSIS",
        "POSTMIGRATION_VALIDATION",
        "ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER",
        "AUTHOR_AND_PUBLISH_INGESTION",
    ),
    "AEM_GUIDES_DITA_OT_CONFIGURATION": (
        "CUSTOM_DITA_OT_PLUGIN",
        "DITA_PROFILE",
        "PROFILE_ASSIGNMENT",
        "DITA_OT_ARGUMENTS",
        "DITA_OT_ENVIRONMENT_VARIABLES",
        "DITA_OT_TIMEOUT",
        "CATALOG_INTEGRATION",
        "SYSTEM_ID_CATALOG",
        "CUSTOM_DITA_SPECIALIZATION",
        "DTD_SPECIALIZATION",
        "XSD_CATALOG_INTEGRATION",
    ),
    "AEM_GUIDES_SECURITY": (
        "AUTHORS_GROUP",
        "REVIEWERS_GROUP",
        "PUBLISHERS_GROUP",
        "FEATURE_PERMISSION_MATRIX",
        "REPOSITORY_ACL",
        "PROJECT_PERMISSIONS",
        "TRANSLATION_AND_REVIEW_PERMISSIONS",
        "PUBLISH_OUTPUT_PERMISSIONS",
        "SEARCH_PERMISSION",
        "DOCUMENT_STATE_TRANSITION_PERMISSION",
    ),
}


@dataclass(frozen=True)
class ClassificationRule:
    sources: tuple[str, ...]
    pattern: str
    capability: str
    sub_capability: str = "UNKNOWN"
    record_type: str = "BEHAVIOR"


def _rule(
    sources: str | Sequence[str],
    pattern: str,
    capability: str,
    sub_capability: str = "UNKNOWN",
    record_type: str = "BEHAVIOR",
) -> ClassificationRule:
    if isinstance(sources, str):
        sources = (sources,)
    return ClassificationRule(tuple(sources), pattern, capability, sub_capability, record_type)


CLASSIFICATION_RULES: tuple[ClassificationRule, ...] = (
    _rule("SOURCE-1", r"digital assets?|dam\b", "DAM_ASSET_MANAGEMENT"),
    _rule("SOURCE-1", r"reference|link management|move or rename", "LINK_MANAGEMENT", "REFERENCE_MAINTENANCE"),
    _rule("SOURCE-1", r"version", "VERSION_MANAGEMENT"),
    _rule("SOURCE-1", r"native dita|native handling", "NATIVE_DITA_HANDLING"),
    _rule("SOURCE-1", r"role|permission|authors|reviewers|publishers", "ROLE_AND_PERMISSION_OVERVIEW", record_type="PERMISSION"),
    _rule("SOURCE-2", r"assets console", "ASSETS_CONSOLE_UPLOAD", record_type="WORKFLOW"),
    _rule("SOURCE-2", r"assets ui|upload assets|create.*files", "ASSETS_UI_UPLOAD", record_type="WORKFLOW"),
    _rule("SOURCE-2", r"desktop app", "DESKTOP_APP_UPLOAD", record_type="WORKFLOW"),
    _rule("SOURCE-2", r"bulk ingestor|azure|s3", "ASSET_BULK_INGESTOR", record_type="WORKFLOW"),
    _rule("SOURCE-2", r"framemaker", "FRAMEMAKER_BULK_UPLOAD", record_type="WORKFLOW"),
    _rule("SOURCE-2", r"progress|status of the upload", "UPLOAD_PROGRESS", record_type="STATE"),
    _rule("SOURCE-2", r"cancel", "UPLOAD_CANCELLATION", record_type="STATE"),
    _rule("SOURCE-2", r"failed files?|failure|failed to upload", "UPLOAD_FAILURE_REPORT", record_type="STATE"),
    _rule("SOURCE-2", r"duplicate|existing file", "DUPLICATE_UPLOAD_POLICY", record_type="CONFIGURATION"),
    _rule("SOURCE-3", r"copy and paste files|copy.*file", "COPY_FILE", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"copy and paste folders|copy.*folder", "COPY_FOLDER", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"overwrite existing|overwrite", "OVERWRITE_FILE", record_type="STATE"),
    _rule("SOURCE-3", r"keep both", "KEEP_BOTH", record_type="STATE"),
    _rule("SOURCE-3", r"move file(?:\(s\)|s)? to new location", "MOVE_FILE_TO_NEW_LOCATION", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"drag-and-drop|drag and drop", "DRAG_AND_DROP_FILE", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"move files in bulk|bulk move", "BULK_MOVE_FOLDER", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"reference", "REFERENCE_MAINTENANCE"),
    _rule("SOURCE-3", r"search dita|dita element", "DITA_CONTENT_SEARCH", record_type="WORKFLOW"),
    _rule("SOURCE-3", r"checked out by|checkout status|check-out", "CHECKOUT_STATUS_SEARCH", record_type="CONFIGURATION"),
    _rule("SOURCE-3", r"delete files?|force delete|delete blocked", "DELETE_FILE", record_type="PERMISSION"),
    _rule("SOURCE-3", r"media files?|preview.*version|version history", "MEDIA_VERSION_PREVIEW", record_type="WORKFLOW"),
    _rule("SOURCE-4", r"15 minutes|automatically process|automatic", "AUTOMATIC_PROCESSING", record_type="LIFECYCLE"),
    _rule("SOURCE-4", r"new process|select.*folders?|targeted|process assets", "TARGETED_MANUAL_PROCESSING", record_type="WORKFLOW"),
    _rule("SOURCE-4", r"asset type|created after|created before|exclude", "PROCESS_FILTERS", record_type="CONFIGURATION"),
    _rule("SOURCE-4", r"in progress|completed|cancelled|failed", "PROCESS_STATE", record_type="STATE"),
    _rule("SOURCE-4", r"restart", "RESTART", record_type="STATE"),
    _rule("SOURCE-4", r"resume", "RESUME", record_type="STATE"),
    _rule("SOURCE-4", r"cancel", "CANCEL", record_type="STATE"),
    _rule("SOURCE-4", r"view logs?|500 entries|full log", "VIEW_LOGS", record_type="STATE"),
    _rule("SOURCE-6", r"pre-requisite|prerequisite|repository size|lucene|node name", "ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER", "PREREQUISITES", "CONFIGURATION"),
    _rule("SOURCE-6", r"content transfer tool|migration set|extraction|ingestion", "ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER", "CONTENT_TRANSFER_LIFECYCLE", "LIFECYCLE"),
    _rule("SOURCE-6", r"author|publish instance|load balancer", "AUTHOR_AND_PUBLISH_INGESTION", record_type="WORKFLOW"),
    _rule("SOURCE-7", r"compatibility matrix|4\.3\.1|4\.6\.0", "NON_UUID_TO_UUID_ROUTING", "COMPATIBILITY_MATRIX", "REFERENCE"),
    _rule("SOURCE-7", r"time estimation|v?cpu|128 gb|milliseconds|asset", "NON_UUID_TO_UUID_ROUTING", "DOCUMENTED_BENCHMARK_ESTIMATE", "REFERENCE"),
    _rule(("SOURCE-8", "SOURCE-9"), r"compatibility assessment|check compatibility|estimated time|files with", "PREMIGRATION_ASSESSMENT", record_type="WORKFLOW"),
    _rule(("SOURCE-8", "SOURCE-9"), r"configure validations?|output.*before|validate.*output", "PREMIGRATION_OUTPUT_VALIDATION", record_type="WORKFLOW"),
    _rule(("SOURCE-8", "SOURCE-9"), r"version purge|purge.*version|labelled|labeled", "VERSION_PURGE", record_type="WORKFLOW"),
    _rule(("SOURCE-8", "SOURCE-9"), r"cpu|memory|disk|infrastructure|compaction", "MIGRATION_INFRASTRUCTURE_READINESS", record_type="CONFIGURATION"),
    _rule(("SOURCE-8", "SOURCE-9"), r"disable|launcher|workflow|regex|tag validation", "MIGRATION_CONFIGURATION_FREEZE", record_type="CONFIGURATION"),
    _rule(("SOURCE-8", "SOURCE-9"), r"system upgrade|uuid upgrade page|migration button", "SYSTEM_UPGRADE", record_type="WORKFLOW"),
    _rule(("SOURCE-8", "SOURCE-9"), r"backup|/content/uuid-upgrade|rollback", "DITA_ASSET_BACKUP", record_type="LIFECYCLE"),
    _rule(("SOURCE-8", "SOURCE-9"), r"rerun|resume|interrupted|aborted|same parameters", "MIGRATION_RERUN_AND_RESUME", record_type="LIFECYCLE"),
    _rule(("SOURCE-8", "SOURCE-9"), r"baseline.*review upgrade|review upgrade", "BASELINE_AND_REVIEW_UPGRADE", record_type="WORKFLOW"),
    _rule(("SOURCE-8", "SOURCE-9"), r"report|successfully migrated|upgraded with errors|skipped|failed", "MIGRATION_REPORT_ANALYSIS", record_type="STATE"),
    _rule(("SOURCE-8", "SOURCE-9"), r"postmigration|validate system upgrade|re-enable|reenable", "POSTMIGRATION_VALIDATION", record_type="LIFECYCLE"),
    _rule("SOURCE-10", r"specialization|specialised|specialized|dtd|xsd|public id|system id", "CUSTOM_DITA_SPECIALIZATION", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"xsd", "XSD_CATALOG_INTEGRATION", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"dtd", "DTD_SPECIALIZATION", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"add system id|system id catalog", "SYSTEM_ID_CATALOG", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"catalog", "CATALOG_INTEGRATION", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"timeout|300 seconds", "DITA_OT_TIMEOUT", record_type="STATE"),
    _rule("SOURCE-10", r"environment variable|ant_opts|ant_home|classpath|\$\{", "DITA_OT_ENVIRONMENT_VARIABLES", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"arguments?|pdf arguments|aem arguments", "DITA_OT_ARGUMENTS", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"assigned path|assign.*path", "PROFILE_ASSIGNMENT", record_type="CONFIGURATION"),
    _rule("SOURCE-10", r"default profile|create.*profile|duplicate.*profile|delete.*profile|dita profile", "DITA_PROFILE", record_type="LIFECYCLE"),
    _rule("SOURCE-10", r"dita-ot|plug-in|plugin|ditaot", "CUSTOM_DITA_OT_PLUGIN", record_type="CONFIGURATION"),
    _rule("SOURCE-11", r"authors", "AUTHORS_GROUP", record_type="PERMISSION"),
    _rule("SOURCE-11", r"reviewers", "REVIEWERS_GROUP", record_type="PERMISSION"),
    _rule("SOURCE-11", r"publishers", "PUBLISHERS_GROUP", record_type="PERMISSION"),
    _rule("SOURCE-11", r"translation|review workflow|language folders", "TRANSLATION_AND_REVIEW_PERMISSIONS", record_type="PERMISSION"),
    _rule("SOURCE-11", r"/home/users|/home/groups|project", "PROJECT_PERMISSIONS", record_type="PERMISSION"),
    _rule("SOURCE-11", r"output|publishing location|publisher", "PUBLISH_OUTPUT_PERMISSIONS", record_type="PERMISSION"),
    _rule("SOURCE-11", r"dam-users|search", "SEARCH_PERMISSION", record_type="PERMISSION"),
    _rule("SOURCE-11", r"document state|state transition", "DOCUMENT_STATE_TRANSITION_PERMISSION", record_type="PERMISSION"),
    _rule("SOURCE-11", r"read|write|permission|acl|dam", "REPOSITORY_ACL", record_type="PERMISSION"),
)


RELATIONSHIP_SPECS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("UPLOAD", "TRIGGERS_OR_REQUIRES", "ASSET_PROCESSING", ("SOURCE-2", "SOURCE-4")),
    ("ASSET_PROCESSING", "MAKES_ASSET_READY_FOR", "AUTHORING_PUBLISHING_OR_REPORTING", ("SOURCE-4",)),
    ("COPY_OR_MOVE", "AFFECTS", "FILE_UUID_FILENAME_AND_REFERENCES", ("SOURCE-3",)),
    ("NON_UUID_SOURCE", "REQUIRES", "VERSION_COMPATIBILITY_PATH", ("SOURCE-7", "SOURCE-8", "SOURCE-9")),
    ("NON_UUID_TO_UUID_MIGRATION", "PRECEDES", "ON_PREMISE_TO_CLOUD_MIGRATION", ("SOURCE-6", "SOURCE-7")),
    ("MIGRATION", "REQUIRES", "REVIEWS_AND_TRANSLATIONS_CLOSED", ("SOURCE-8", "SOURCE-9")),
    ("MIGRATION", "VALIDATED_BY", "PRE_POST_OUTPUT_COMPARISON", ("SOURCE-8", "SOURCE-9")),
    ("MIGRATION_CONFIGURATION_FREEZE", "RESTORED_BY", "POSTMIGRATION_VALIDATION", ("SOURCE-8", "SOURCE-9")),
    ("CUSTOM_DITA_OT_PROFILE", "CONTROLS", "DITA_OT_PUBLISHING_PROCESS", ("SOURCE-10",)),
    ("CUSTOM_SPECIALIZATION_PROFILE", "CONTROLS", "AUTHORING_AND_PUBLISHING_SCHEMA_CONTEXT", ("SOURCE-10",)),
    ("USER_GROUP_PLUS_ACL_PLUS_FEATURE_CONFIGURATION", "DETERMINES", "EFFECTIVE_USER_CAPABILITY", ("SOURCE-11",)),
    ("OFFICIAL_DOCUMENTATION", "MAY_BE_CORROBORATED_BY", "UI_OBSERVATION", ("SOURCE-2", "SOURCE-3", "SOURCE-4", "SOURCE-10", "SOURCE-11")),
)


SEMANTIC_COLLISIONS: tuple[tuple[str, str], ...] = (
    ("UPLOAD_FILE", "MIGRATE_CONTENT"),
    ("ASSET_BULK_INGESTOR", "GUIDES_BULK_PROCESSOR"),
    ("GUIDES_ASSET_PROCESSING", "AEM_ASSETS_MICROSERVICES"),
    ("COPY_FILE", "MOVE_FILE"),
    ("COPY_UUID", "GENERATE_UUID_DURING_COPY"),
    ("UUID_FILENAME", "FILE_UUID_METADATA"),
    ("OVERWRITE_FILE", "SAVE_AS_NEW_VERSION"),
    ("MOVE_FILE", "NON_UUID_TO_UUID_MIGRATION"),
    ("BULK_MOVE", "CONTENT_TRANSFER_TOOL"),
    ("VERSION_PURGE", "DELETE_FILE_VERSION_MANUALLY"),
    ("MIGRATION_OUTPUT_VALIDATION_BASELINE", "DITA_MAP_BASELINE"),
    ("SYSTEM_UPGRADE", "AEM_GUIDES_PRODUCT_UPGRADE"),
    ("NON_UUID_TO_UUID_MIGRATION", "ON_PREMISE_TO_CLOUD_MIGRATION"),
    ("CONTENT_TRANSFER_EXTRACTION", "CONTENT_TRANSFER_INGESTION"),
    ("CUSTOM_DITA_OT_PLUGIN", "DITA_SPECIALIZATION"),
    ("DITA_PROFILE", "FOLDER_PROFILE"),
    ("DITA_OT_TIMEOUT", "PUBLISHING_QUEUE_TIMEOUT"),
    ("XSD_CATALOG_INTEGRATION", "XSD_SUPPORT_IN_EDITOR"),
    ("GROUP_PERMISSION", "REPOSITORY_ACL"),
    ("PUBLISHERS_GROUP", "UNIVERSAL_PUBLISH_PATH_ACCESS"),
)


DITA_OT_PROFILE_PROPERTIES: tuple[str, ...] = (
    "PROFILE_NAME",
    "REUSE_OUTPUT",
    "PROFILE_EXTRACT_PATH",
    "ASSIGNED_PATH",
    "DITA_OT_TIMEOUT",
    "PDF_ARGUMENTS",
    "AEM_ARGUMENTS",
    "LIBRARY_PATHS",
    "BUILD_XML",
    "ANT_SCRIPT_FOLDER",
    "ENVIRONMENT_VARIABLES",
    "OVERWRITE_DITA_OT_OUTPUT",
    "AEM_DITA_OT_ZIP_PATH",
    "LOCAL_DITA_OT_DIRECTORY_PATH",
    "PLUGIN_PATH",
    "INTEGRATE_CATALOGS",
    "ADD_SYSTEM_ID_CATALOG",
    "DITA_OT_TEMPORARY_PATH",
)


BEHAVIOR_MODELS: dict[str, Any] = {
    "CONTENT_UPLOAD_FLOW": {
        "source_ids": ["SOURCE-2"],
        "states": [
            "CREATE",
            "FILES",
            "SELECT_LOCAL_FILE",
            "UPLOAD_ASSETS_DIALOG",
            "OPTIONAL_RENAME",
            "START_UPLOAD",
            "PER_FILE_PROGRESS",
            "SUCCESS_OR_FAILURE",
        ],
        "terminal_cancel": "CANCEL_BEFORE_COMPLETION -> FILE_NOT_ADDED_TO_REPOSITORY",
    },
    "FILE_IDENTITY_BEHAVIOR_MATRIX": {
        "source_ids": ["SOURCE-3"],
        "dimensions": {
            "FILE_NAME_TYPE": ["HUMAN_READABLE", "UUID_PATTERN"],
            "OPERATION": ["COPY_PASTE", "DRAG_DROP", "OVERWRITE", "KEEP_BOTH", "MOVE_TO_NEW_LOCATION"],
            "LOCATION_RELATION": ["SAME_LOCATION", "DIFFERENT_LOCATION"],
            "COLLISION": ["NAME_EXISTS", "NAME_DOES_NOT_EXIST"],
            "LOCK_STATE": ["CHECKED_OUT_BY_CURRENT_USER", "CHECKED_OUT_BY_OTHER_USER", "NOT_CHECKED_OUT"],
            "VERSION_OPTION": ["CREATE_VERSION_ENABLED", "CREATE_VERSION_DISABLED"],
        },
    },
    "FOLDER_COPY_LIFECYCLE": {
        "source_ids": ["SOURCE-3"],
        "transitions": ["REQUEST_INITIATED -> BACKGROUND_PROCESS", "BACKGROUND_PROCESS -> SUCCESS_OR_FAILURE_NOTIFICATION"],
    },
    "ASSET_PROCESSING_STATE_MACHINE": {
        "source_ids": ["SOURCE-4"],
        "states": ["IN_PROGRESS", "COMPLETED", "CANCELLED", "FAILED"],
        "transitions": [
            "COMPLETED -> RESTART",
            "FAILED_OR_CANCELLED -> RESUME",
            "IN_PROGRESS -> CANCEL",
            "APPLICABLE_STATE -> VIEW_LOGS",
        ],
    },
    "CONTENT_TRANSFER_LIFECYCLE": {
        "source_ids": ["SOURCE-6"],
        "states": [
            "CREATE_CLOUD_PROJECT",
            "CREATE_MIGRATION_SET",
            "COPY_EXTRACTION_KEY_REFERENCE",
            "INSTALL_CTT_ON_SOURCE",
            "CONNECT_SOURCE_TO_TARGET",
            "CONFIGURE_PATHS_AND_OPTIONS",
            "EXTRACT",
            "VERIFY_EXTRACTION",
            "CREATE_INGESTION_JOB",
            "INGEST_TO_TARGET",
        ],
        "secret_policy": "EXTRACTION_KEY -> SECRET_REFERENCE_ONLY",
    },
    "NON_UUID_TO_UUID_MIGRATION_RUNBOOK": {
        "source_ids": ["SOURCE-8", "SOURCE-9"],
        "stages": [
            "PACKAGE_INSTALLATION",
            "PREMIGRATION_CHECKS",
            "COMPATIBILITY_ASSESSMENT",
            "OUTPUT_VALIDATION_BASELINE_CAPTURE",
            "OPTIONAL_VERSION_PURGE",
            "INFRASTRUCTURE_READINESS",
            "WORKFLOW_AND_CONFIGURATION_DISABLEMENT",
            "MIGRATION_EXECUTION",
            "BACKUP_AND_ROLLBACK",
            "REPORT_DOWNLOAD",
            "BASELINE_AND_REVIEW_UPGRADE",
            "POSTMIGRATION_VALIDATION",
            "CONFIGURATION_REENABLEMENT",
            "COMPACTION",
        ],
        "version_routes": {
            "SOURCE-8": "4.3.1_NON_UUID -> 4.3.2_UUID",
            "SOURCE-9": "4.6.0_SP4_NON_UUID -> 4.6.1_UUID",
        },
    },
    "DITA_PROFILE_LIFECYCLE": {
        "source_ids": ["SOURCE-10"],
        "rules": [
            "DEFAULT_PROFILE -> UPDATE_ALLOWED",
            "DEFAULT_PROFILE -> DELETE_NOT_ALLOWED",
            "CUSTOM_PROFILE -> CREATE_EDIT_DELETE_ALLOWED",
            "PROFILE -> ASSIGNED_TO_ONE_OR_MORE_CONTENT_PATHS",
        ],
    },
    "EFFECTIVE_USER_CAPABILITY": {
        "source_ids": ["SOURCE-11"],
        "expression": "GROUP_MEMBERSHIP + REPOSITORY_ACL + PROJECT_OR_FEATURE_STATE_CONFIGURATION",
    },
}


ORACLE_SPECS: dict[str, tuple[str, tuple[str, ...]]] = {
    "CONTENT_UPLOAD": (
        "SOURCE-2",
        (
            "A cancelled pending upload does not add that file to the repository.",
            "A completed upload exposes its documented success confirmation.",
            "A multi-file upload failure report identifies the files that actually failed.",
            "An optional upload rename is reflected in the repository asset identity.",
            "Desktop App and Asset Bulk Ingestor duplicate handling follows the active server configuration.",
        ),
    ),
    "FILE_COPY_MOVE": (
        "SOURCE-3",
        (
            "A copied file receives a new UUID while overwrite retains the existing UUID as documented.",
            "Human-readable and UUID-pattern filenames follow their separate copy naming rules.",
            "Folder-copy completion is asynchronous and notification-driven.",
            "Keep Both creates a distinct file identity instead of replacing the existing working copy.",
            "Move to New Location preserves the documented in-scope references without mutating unrelated references.",
            "Checked-out overwrite follows the active administrator setting.",
            "Only one documented Bulk Move operation runs at a time.",
            "A failed or aborted move does not silently report full success.",
        ),
    ),
    "DELETE": (
        "SOURCE-3",
        (
            "Referenced or checked-out deletion follows the configured permission policy.",
            "A non-privileged user cannot force-delete a referenced file.",
            "Force deletion does not claim that references are repaired.",
            "Deleting a file remains distinct from removing collection or map membership.",
        ),
    ),
    "ASSET_PROCESSING": (
        "SOURCE-4",
        (
            "Asset-type and date filters limit a processing run to the selected asset set.",
            "Excluded subfolders remain outside the processing run.",
            "A second process for the same folder is rejected while one is already running.",
            "Restart, Resume, and Cancel are offered only in their documented processing states.",
            "The full log remains downloadable beyond the latest entries shown in the UI.",
        ),
    ),
    "MIGRATION": (
        "SOURCE-8|SOURCE-9",
        (
            "An incompatible source version is rejected before version-specific migration starts.",
            "Active reviews and translation tasks are closed before non-UUID migration.",
            "Compatibility Assessment reports findings without mutating source content.",
            "Migration does not proceed while the full logs contain an error or exception.",
            "Version Purge preserves versions used by baselines, reviews, or labels.",
            "Temporary migration configuration changes are restored after migration.",
            "Failed-file backup remains available for rollback and successful-file backup is removed as documented.",
            "A rerun resumes only within the documented same-parameter scope.",
            "Referenced media assets are included with DITA topics and maps.",
            "System Upgrade and Baseline/Review Upgrade remain separate phases.",
            "Migration report categories preserve successful, upgraded-with-errors, skipped, and failed distinctions.",
        ),
    ),
    "ON_PREMISE_TO_CLOUD": (
        "SOURCE-6",
        (
            "The mandatory Guides paths are included in the migration set.",
            "Content Transfer extraction and ingestion remain separate lifecycle states.",
            "Extraction completion is verified before ingestion starts.",
            "Author and Publish ingestion remain distinct target contexts.",
            "Publish ingestion does not silently distinguish published from unpublished content.",
        ),
    ),
    "CUSTOM_DITA_OT": (
        "SOURCE-10",
        (
            "A custom DITA-OT archive has the documented structure and upload-compatible file type.",
            "The default DITA-OT package is not overwritten by a custom package.",
            "An assigned-path profile applies only to its intended repository paths.",
            "A DITA-OT timeout terminates the task as failed and leaves output-log evidence.",
            "Environment-variable expressions are retained without storing secret values.",
            "Cloud and On-Premise custom-package locations remain distinct.",
            "MathML PDF output requires the applicable renderer or processor dependency.",
        ),
    ),
    "SPECIALIZATION": (
        "SOURCE-10",
        (
            "The selected specialization profile resolves the intended DTD catalog.",
            "Public-ID and System-ID behavior follows catalog configuration.",
            "Add System ID Catalog is used only under its documented conditions.",
            "Cloud and On-Premise specialization paths remain distinct.",
            "XSD catalog processing does not become a claim of XSD authoring support in the Editor.",
        ),
    ),
    "SECURITY": (
        "SOURCE-11",
        (
            "Effective user capability reflects group membership, repository ACL, and feature or state configuration.",
            "Reviewer access expires when the review task closes.",
            "A non-default publishing location requires explicit publisher permissions.",
            "Document-state targets follow the applicable state-profile transition permissions.",
            "Search capability requires its documented group or permission.",
            "UI visibility alone does not grant access when the required ACL is absent.",
        ),
    ),
}


@dataclass(frozen=True)
class GroundedAssertionSpec:
    assertion_id: str
    source_ids: tuple[str, ...]
    capabilities: tuple[str, ...]
    claim: str
    evidence_groups: tuple[tuple[str, ...], ...]
    success_criteria: tuple[str, ...] = ()
    facets: tuple[tuple[str, str], ...] = ()


def _assertion(
    assertion_id: str,
    source_ids: Sequence[str],
    capabilities: Sequence[str],
    claim: str,
    evidence_groups: Sequence[Sequence[str]],
    *,
    success_criteria: Sequence[str] = (),
    facets: dict[str, str] | None = None,
) -> GroundedAssertionSpec:
    return GroundedAssertionSpec(
        assertion_id,
        tuple(source_ids),
        tuple(capabilities),
        claim,
        tuple(tuple(group) for group in evidence_groups),
        tuple(success_criteria),
        tuple(sorted((facets or {}).items())),
    )


# Curated independently from the retrieval fixture.  Every claim must resolve
# its selectors against freshly parsed official-source literals before it can
# enter the corpus; the retrieval catalog is never an input to this registry.
GROUNDED_ASSERTION_SPECS: tuple[GroundedAssertionSpec, ...] = (
    _assertion(
        "content.upload.channels",
        ["SOURCE-2"],
        ["ASSETS_CONSOLE_UPLOAD", "ASSETS_UI_UPLOAD", "DESKTOP_APP_UPLOAD", "ASSET_BULK_INGESTOR", "FRAMEMAKER_BULK_UPLOAD"],
        "Upload channels remain distinct: Assets Console and Assets UI upload local files; Desktop App is a separate channel; Asset Bulk Ingestor supports cloud storage such as Azure or S3; FrameMaker has its own bulk-upload workflow.",
        [["assets console"], ["desktop app"], ["bulk ingestor"], ["framemaker"]],
        success_criteria=["SC-07"],
    ),
    _assertion(
        "content.upload.cancel-and-failure-report",
        ["SOURCE-2"],
        ["UPLOAD_CANCELLATION", "UPLOAD_FAILURE_REPORT"],
        "Cancelling before completion terminates the upload and the pending file is not added to the repository. At the end of a multi-file upload, the failure prompt identifies the failed files.",
        [["cancel"], ["failed"]],
        success_criteria=["SC-08"],
        facets={"terminal_cancel": "NO_REPOSITORY_WRITE", "failure_surface": "FAILED_FILE_REPORT"},
    ),
    _assertion(
        "content.upload.duplicate-policy",
        ["SOURCE-2"],
        ["DUPLICATE_UPLOAD_POLICY"],
        "Duplicate handling for Desktop App and Asset Bulk Ingestor depends on the active server or administrator configuration.",
        [["duplicate"], ["configuration"]],
    ),
    _assertion(
        "content.move.reference-maintenance",
        ["SOURCE-1", "SOURCE-3"],
        ["REFERENCE_MAINTENANCE", "MOVE_FILE_TO_NEW_LOCATION"],
        "When an in-scope DITA file is moved or renamed, AEM Guides maintains and automatically updates the applicable references and links; unrelated references are not claimed to change.",
        [["reference"], ["move", "rename"]],
        success_criteria=["SC-16"],
    ),
    _assertion(
        "content.file-copy.identity-matrix",
        ["SOURCE-3"],
        ["COPY_FILE"],
        "A copied human-readable file uses a suffixed filename and receives a new UUID. A copied UUID-pattern filename receives a new UUID and its filename corresponds to that new UUID.",
        [["copy"], ["uuid"]],
        success_criteria=["SC-09", "SC-13"],
        facets={"operation": "COPY_FILE", "identity_result": "NEW_UUID"},
    ),
    _assertion(
        "content.folder-copy.lifecycle",
        ["SOURCE-3"],
        ["COPY_FOLDER"],
        "Same-location and different-location folder copy remain distinct. Folder copy runs as an asynchronous background process and reports success or failure through a notification. Assets in the copied folder receive regenerated UUID identities as documented.",
        [["copy", "folder"], ["background", "notification"]],
        success_criteria=["SC-10", "SC-11", "SC-13"],
        facets={"execution": "ASYNCHRONOUS", "completion_signal": "NOTIFICATION"},
    ),
    _assertion(
        "content.drag-drop.collision-actions",
        ["SOURCE-3"],
        ["OVERWRITE_FILE", "KEEP_BOTH", "MOVE_FILE_TO_NEW_LOCATION"],
        "Drag and drop keeps three outcomes distinct: Overwrite replaces the existing working copy, Keep Both retains both files as distinct identities, and Move to New Location performs a file move.",
        [["overwrite"], ["keep both"], ["new location"]],
        success_criteria=["SC-12"],
    ),
    _assertion(
        "content.overwrite.checkout-and-version",
        ["SOURCE-3"],
        ["OVERWRITE_FILE", "CHECKOUT_STATUS_SEARCH"],
        "Overwrite behavior for a file checked out by another user depends on the administrator setting and can fail with an error. The optional Create Version choice applies to the existing working copy and is not Save As New Version.",
        [["checked out"], ["create version", "version"]],
        success_criteria=["SC-14"],
    ),
    _assertion(
        "content.move.regular-bulk-migration-distinction",
        ["SOURCE-3", "SOURCE-7"],
        ["MOVE_FILE_TO_NEW_LOCATION", "BULK_MOVE_FOLDER", "NON_UUID_TO_UUID_ROUTING"],
        "Regular file Move, administrator folder-level Bulk Move, and non-UUID content migration are separate operations with separate scopes.",
        [["move"], ["bulk move"], ["non-uuid"]],
        success_criteria=["SC-15"],
    ),
    _assertion(
        "content.bulk-move.constraints",
        ["SOURCE-3"],
        ["BULK_MOVE_FOLDER"],
        "Only one Bulk Move operation runs at a time until completion. If duplicate folders are found and suffix handling is not selected, the operation aborts and displays a message.",
        [["one", "bulk move"], ["duplicate", "suffix"]],
    ),
    _assertion(
        "content.delete.permission-branches",
        ["SOURCE-3", "SOURCE-11"],
        ["DELETE_FILE", "REFERENCE_MAINTENANCE", "REPOSITORY_ACL"],
        "Delete behavior is reference-, checkout-, configuration-, and permission-aware. For a non-privileged user, deletion of a referenced file is blocked until the references are removed. A non-privileged user cannot force-delete it, and force-delete does not claim to repair incoming or outgoing references.",
        [["delete"], ["reference"], ["permission"]],
        success_criteria=["SC-17"],
    ),
    _assertion(
        "content.asset-processor.purpose-and-schedule",
        ["SOURCE-4"],
        ["TARGETED_MANUAL_PROCESSING", "AUTOMATIC_PROCESSING"],
        "Guides Asset Processing is used for failed initial processing, unprocessed assets, or targeted reprocessing. Automatic processing is documented on a 15-minute schedule; that documented interval is not a universal SLA.",
        [["process assets"], ["15 minutes"]],
        success_criteria=["SC-18"],
    ),
    _assertion(
        "content.asset-processor.filters-and-concurrency",
        ["SOURCE-4"],
        ["PROCESS_FILTERS", "PROCESS_STATE"],
        "A process can filter by asset type such as DITA Topic and can exclude subfolders. Another process for the same folder is not allowed while that folder is already processing.",
        [["asset type"], ["exclude"], ["same folder", "already"]],
    ),
    _assertion(
        "content.asset-processor.state-actions",
        ["SOURCE-4"],
        ["PROCESS_STATE", "RESTART", "RESUME", "CANCEL", "VIEW_LOGS"],
        "State controls are operation-specific: Completed supports Restart; Failed or Cancelled supports Resume; In Progress supports Cancel. The UI shows the recent processing runs and the latest 500 log entries, while the complete log remains downloadable.",
        [["restart"], ["resume"], ["cancel"], ["500"]],
        success_criteria=["SC-19"],
        facets={"model": "ASSET_PROCESSING_STATE_MACHINE"},
    ),
    _assertion(
        "migration.version-routes",
        ["SOURCE-7", "SOURCE-8", "SOURCE-9"],
        ["NON_UUID_TO_UUID_ROUTING", "NON_UUID_TO_UUID_4_3_PATH", "NON_UUID_TO_UUID_4_6_PATH"],
        "Version routing is exact: 4.3.1 non-UUID migrates to 4.3.2 UUID; 4.6.0 SP4 non-UUID migrates to 4.6.1 UUID. A later 4.6.0 Service Pack cannot directly use the SP4 path and must follow the documented revert requirement.",
        [["4.3.1"], ["4.3.2"], ["4.6.0", "sp4"], ["4.6.1"]],
        success_criteria=["SC-20", "SC-21"],
    ),
    _assertion(
        "migration.benchmark-context",
        ["SOURCE-7"],
        ["MIGRATION_INFRASTRUCTURE_READINESS", "NON_UUID_TO_UUID_ROUTING"],
        "Migration timing values are benchmark estimates, not SLAs. Interpret them with their hardware, system-load, asset-count, and storage-throughput context.",
        [["time estimation", "time estimates", "estimated"], ["cpu", "memory"]],
        success_criteria=["SC-22"],
        facets={"sla": "false"},
    ),
    _assertion(
        "migration.preconditions-and-compatibility",
        ["SOURCE-8", "SOURCE-9"],
        ["PREMIGRATION_ASSESSMENT"],
        "Active reviews and translation tasks must be closed before non-UUID migration. Compatibility Assessment is non-mutating and reports total files, estimated time, files with errors, and GUID filename findings.",
        [["review"], ["translation"], ["compatibility assessment"], ["estimated"]],
        success_criteria=["SC-23", "SC-24"],
        facets={"mutates_source": "false"},
    ),
    _assertion(
        "migration.author-and-query-readiness",
        ["SOURCE-8", "SOURCE-9"],
        ["MIGRATION_INFRASTRUCTURE_READINESS", "SYSTEM_UPGRADE"],
        "UUID migration is executed only on the Author instance. For large repositories, queryLimitInMemory or queryLimitReads may need an environment-scoped increase above the applicable asset-count threshold before migration scripts run.",
        [["author instance", "author"], ["querylimitinmemory", "querylimitreads"], ["assets", "files"]],
        facets={"execution_instance": "AUTHOR", "configuration_scope": "ENVIRONMENT_SPECIFIC"},
    ),
    _assertion(
        "migration.output-validation-and-version-purge",
        ["SOURCE-8", "SOURCE-9"],
        ["PREMIGRATION_OUTPUT_VALIDATION", "VERSION_PURGE"],
        "Configure Validations captures output before migration for comparison with postmigration output; this output-comparison baseline is not a DITA map Baseline. Version Purge preserves versions used by baselines, reviews, or labels.",
        [["configure validation", "validation"], ["version purge"], ["baseline"], ["review"]],
        success_criteria=["SC-25", "SC-26"],
    ),
    _assertion(
        "migration.configuration-disable-and-restore",
        ["SOURCE-8", "SOURCE-9"],
        ["MIGRATION_CONFIGURATION_FREEZE", "POSTMIGRATION_VALIDATION"],
        "Workflows, post-processing launchers, UUID regex settings, and tag-validation configurations that are temporarily disabled for migration must be restored or re-enabled during postmigration validation.",
        [["disable"], ["workflow", "launcher"], ["tag validation", "regex"]],
        success_criteria=["SC-27"],
    ),
    _assertion(
        "migration.backup-rollback-cleanup",
        ["SOURCE-8", "SOURCE-9"],
        ["DITA_ASSET_BACKUP"],
        "Migration creates DITA asset backups under /content/uuid-upgrade. Failed-file backup remains available for rollback; after successful file migration, the corresponding backup is deleted.",
        [["/content/uuid-upgrade"], ["backup"], ["successful"]],
        success_criteria=["SC-28"],
    ),
    _assertion(
        "migration.rerun-resume-and-media",
        ["SOURCE-8", "SOURCE-9"],
        ["MIGRATION_RERUN_AND_RESUME", "SYSTEM_UPGRADE"],
        "A migration rerun or resume remains scoped to the same folder and same parameters. Referenced media assets, including images or graphics, are processed in addition to .dita and .ditamap files.",
        [["rerun", "resume"], ["same", "parameter"], ["media"]],
        success_criteria=["SC-29", "SC-30"],
    ),
    _assertion(
        "migration.skip-folder-safety",
        ["SOURCE-8", "SOURCE-9"],
        ["SYSTEM_UPGRADE"],
        "Do not skip an arbitrary folder that contains referenced DITA assets. A skipped folder must contain no DITA assets, must not be referenced, and must not be intended for a future reference.",
        [["skip"], ["dita assets"], ["referred", "referenced", "reference"]],
        facets={"skip_gate": "NO_DITA_ASSETS_OR_REFERENCES"},
    ),
    _assertion(
        "migration.upgrade-phases-and-report-states",
        ["SOURCE-8", "SOURCE-9"],
        ["SYSTEM_UPGRADE", "BASELINE_AND_REVIEW_UPGRADE", "MIGRATION_REPORT_ANALYSIS"],
        "After all files are migrated by System Upgrade, the separate Baseline and Review Upgrade phase runs. Migration reports keep succeeded, upgraded-with-errors, skipped, and failed states distinct. Do not proceed when a migration log contains an exception; resolve the exception first.",
        [["system upgrade"], ["baseline", "review upgrade"], ["skipped"], ["failed"]],
        success_criteria=["SC-31", "SC-32"],
    ),
    _assertion(
        "migration.ctt.paths-and-lifecycle",
        ["SOURCE-6"],
        ["ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER"],
        "On-Premise-to-Cloud migration includes the mandatory Guides paths /content/dam and /var/dxml. Content Transfer Tool extraction runs on the source and is verified before the separate ingestion job runs on the target. Include Versions controls whether file versions are included.",
        [["/content/dam"], ["/var/dxml"], ["extract"], ["ingest"]],
        success_criteria=["SC-33", "SC-34"],
    ),
    _assertion(
        "migration.ctt.author-publish-targets",
        ["SOURCE-6"],
        ["AUTHOR_AND_PUBLISH_INGESTION", "ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER"],
        "Author and Publish ingestion are separate target contexts. Publish ingestion processes the selected migration set and does not distinguish published from unpublished content.",
        [["author"], ["publish"], ["ingestion"]],
        success_criteria=["SC-35"],
    ),
    _assertion(
        "ditaot.plugin.deployment-paths",
        ["SOURCE-10"],
        ["CUSTOM_DITA_OT_PLUGIN"],
        "A custom DITA-OT ZIP archive is supplied through the Cloud profile or repository flow, while On-Premise supports its documented repository/package or local server-directory procedure. The default DITA-OT package must not be overwritten, and the archive is not deployed as an AEM content package.",
        [["zip"], ["cloud"], ["on-premise", "on premise"], ["default"]],
        success_criteria=["SC-37"],
    ),
    _assertion(
        "ditaot.profile.lifecycle-and-assignment",
        ["SOURCE-10"],
        ["DITA_PROFILE", "PROFILE_ASSIGNMENT"],
        "The Default Profile can be updated but cannot be deleted. Custom profiles support create, edit, and delete. Assigned Path controls the content paths to which a profile applies.",
        [["default profile"], ["assigned path"]],
        success_criteria=["SC-38"],
    ),
    _assertion(
        "ditaot.timeout.failure",
        ["SOURCE-10"],
        ["DITA_OT_TIMEOUT"],
        "When DITA-OT Timeout expires, the publishing task is terminated, marked failed, and leaves failure evidence in the output log. The documented timeout value is configuration guidance, not an SLA.",
        [["timeout"], ["failed", "failure"]],
        success_criteria=["SC-40"],
        facets={"sla": "false", "terminal_state": "FAILED"},
    ),
    _assertion(
        "ditaot.environment-variables",
        ["SOURCE-10"],
        ["DITA_OT_ENVIRONMENT_VARIABLES"],
        "DITA-OT receives ANT_OPTS, ANT_HOME, PATH, and CLASSPATH by default. A ${...} expression can reference an existing system variable or Java property without storing a secret value.",
        [["ant_opts"], ["ant_home"], ["classpath"]],
    ),
    _assertion(
        "ditaot.mathml-rendering-dependency",
        ["SOURCE-10"],
        ["CUSTOM_DITA_OT_PLUGIN"],
        "Correct MathML authoring is separate from PDF output rendering. The default Apache FOP does not support MathML rendering; output needs the applicable MathML plug-in or a different XSL-FO processor.",
        [["mathml"], ["fop"]],
        success_criteria=["SC-41"],
    ),
    _assertion(
        "dita.specialization-vs-plugin",
        ["SOURCE-10"],
        ["CUSTOM_DITA_OT_PLUGIN", "CUSTOM_DITA_SPECIALIZATION"],
        "A custom DITA-OT plug-in changes publishing or processing, while DITA specialization defines a custom information model or schema; they are separate capabilities.",
        [["dita-ot"], ["specialization"]],
        success_criteria=["SC-36"],
    ),
    _assertion(
        "dita.xsd-editor-and-catalog",
        ["SOURCE-10"],
        ["CUSTOM_DITA_SPECIALIZATION", "XSD_CATALOG_INTEGRATION", "SYSTEM_ID_CATALOG"],
        "AEM Guides Editor does not support XSD authoring, while an XSD catalog may still be integrated for processing. Add System ID Catalog is used when PUBLIC ID entries are missing and system IDs are relative to the uploaded catalog location.",
        [["xsd"], ["catalog"], ["system id"]],
        success_criteria=["SC-42"],
    ),
    _assertion(
        "dita.specialization.deployment-paths",
        ["SOURCE-10"],
        ["CUSTOM_DITA_SPECIALIZATION", "DTD_SPECIALIZATION", "XSD_CATALOG_INTEGRATION"],
        "Cloud specialization resources use /var/dxml/dita_resources, while On-Premise specialization resources use /apps/fmdita/dita_resources. The deployment paths remain distinct.",
        [["/var/dxml/dita_resources"], ["/apps/fmdita/dita_resources"]],
        success_criteria=["SC-43"],
    ),
    _assertion(
        "security.groups-and-effective-capability",
        ["SOURCE-1", "SOURCE-11"],
        ["AUTHORS_GROUP", "REVIEWERS_GROUP", "PUBLISHERS_GROUP", "FEATURE_PERMISSION_MATRIX", "REPOSITORY_ACL"],
        "AEM Guides creates Authors, Reviewers, and Publishers groups. Group membership alone is not sufficient for every operation; effective capability also depends on repository ACL, project or feature configuration, and state-profile rules.",
        [["authors"], ["reviewers"], ["publishers"], ["permission"]],
        success_criteria=["SC-44"],
    ),
    _assertion(
        "security.translation-review-permissions",
        ["SOURCE-11"],
        ["TRANSLATION_AND_REVIEW_PERMISSIONS", "REPOSITORY_ACL"],
        "Starting translation or review requires the documented Publishers and Projects Administrators membership. Translation also needs the applicable permissions or ACL on the source-language and target-language folders.",
        [["translation"], ["source and target language folders", "source language"], ["source and target language folders", "target language"]],
    ),
    _assertion(
        "security.project-and-reviewer-lifecycle",
        ["SOURCE-11"],
        ["PROJECT_PERMISSIONS", "REVIEWERS_GROUP"],
        "Project users may need read access to /home/users and /home/groups for team visibility and task or workflow creation. A reviewer retains review access while the task is open; access is no longer available after the task closes.",
        [["/home/users"], ["/home/groups"], ["review"]],
    ),
    _assertion(
        "security.publish-and-search-acl",
        ["SOURCE-11"],
        ["PUBLISH_OUTPUT_PERMISSIONS", "SEARCH_PERMISSION", "REPOSITORY_ACL"],
        "Publishers do not automatically receive access to every custom output path: a non-default publishing location requires explicit read and write permission or ACL. DAM search access requires the documented dam-users membership or capability configuration.",
        [["output"], ["permission"], ["dam-users", "search"]],
        success_criteria=["SC-45"],
    ),
    _assertion(
        "security.document-state-transition",
        ["SOURCE-11"],
        ["DOCUMENT_STATE_TRANSITION_PERMISSION"],
        "A user's right to change document state is controlled by the applicable state-transition configuration in the document state profile.",
        [["document state"], ["state transition"]],
    ),
)


DATA_QUALITY_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"drop drown", "SOURCE_TYPO_DROP_DROWN"),
    (r"last five migrations", "ASSET_PROCESSOR_MIGRATION_WORDING"),
    (r"/system/console/configMgr", "MALFORMED_CONFIGMGR_FORMATTING"),
    (r"queryLimitInMemory|queryLimitReads", "QUERY_LIMIT_FORMATTING"),
    (r"script will resumes", "SOURCE_GRAMMAR_SCRIPT_WILL_RESUMES"),
    (r"DITAOT\\_DIR", "ESCAPED_UNDERSCORE_LITERAL"),
    (r"DITA-OT\.ZIP|DITAOT\.ZIP", "DITA_OT_ARCHIVE_LITERAL"),
)


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_./+-]*", re.IGNORECASE)
ANCHOR_SUFFIX_RE = re.compile(r"\s+id[0-9a-z]+\s*$", re.IGNORECASE)
LAST_UPDATED_RE = re.compile(r"Last update:\s*([^\n]+)", re.IGNORECASE)
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("BEARER_TOKEN", re.compile(r"\bBearer\s+[A-Za-z0-9._~+\-/=]{8,}", re.IGNORECASE)),
    ("GIT_ACCESS_TOKEN", re.compile(r"\b(?:ghp|github_pat|glpat)-?[A-Za-z0-9_\-]{12,}\b", re.IGNORECASE)),
    ("AWS_ACCESS_KEY", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("PRIVATE_KEY", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE)),
    ("URI_CREDENTIALS", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:]+:[^\s/@]+@", re.IGNORECASE)),
    (
        "SECRET_ASSIGNMENT",
        re.compile(
            r"\b(?:password|passwd|client[_-]?secret|api[_-]?key|access[_-]?token|extraction[_-]?key)\b\s*[:=]\s*(?!UNKNOWN\b|\$\{|<|\[)[^\s,;]{6,}",
            re.IGNORECASE,
        ),
    ),
    (
        "PRIVATE_NETWORK_ADDRESS",
        re.compile(
            r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
        ),
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any, *, ensure_ascii: bool = False) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(value, indent=2, ensure_ascii=ensure_ascii) + "\n").encode("utf-8"),
    )


@contextmanager
def activation_lock(timeout_seconds: float = 30.0) -> Iterator[None]:
    """Serialize writers of the shared AEM Guides manifest across processes."""
    ACTIVATION_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with ACTIVATION_LOCK_PATH.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (BlockingIOError, OSError):
                if time.monotonic() >= deadline:
                    raise TimeoutError("timed out waiting for the shared AEM Guides activation lock")
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def canonicalize_url(url: str) -> str:
    parts = urlsplit(str(url).strip())
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def normalized_heading(value: str) -> str:
    value = ANCHOR_SUFFIX_RE.sub("", re.sub(r"\s+", " ", value or "").strip())
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "document"


def normalize_semantic_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_semantic_value(value: str) -> str:
    normalized = normalize_semantic_text(value)
    replacements = (
        (r"\bdrop drown\b", "drop-down"),
        (r"\bscript will resumes\b", "script will resume"),
        (r"DITAOT\\_DIR", "DITAOT_DIR"),
    )
    for pattern, replacement in replacements:
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
    return normalized


def normalize_symbol(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "")).strip("_").upper()
    normalized = normalized.replace("DITA_OT_PDF_ARGUMENTS", "PDF_ARGUMENTS")
    normalized = normalized.replace("DITA_OT_AEM_ARGUMENTS", "AEM_ARGUMENTS")
    normalized = normalized.replace("DITA_OT_LIBRARY_PATHS", "LIBRARY_PATHS")
    normalized = normalized.replace("DITA_OT_BUILD_XML", "BUILD_XML")
    normalized = normalized.replace("DITA_OT_ANT_SCRIPT_FOLDER", "ANT_SCRIPT_FOLDER")
    normalized = normalized.replace("DITA_OT_ENVIRONMENT_VARIABLES", "ENVIRONMENT_VARIABLES")
    normalized = normalized.replace("DITA_OT_PLUG_IN_PATH", "PLUGIN_PATH")
    return normalized


def redact_secrets(value: str) -> str:
    redacted = str(value or "")
    for _name, pattern in SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def find_secret_kinds(value: Any) -> list[str]:
    serialized = stable_json(value) if not isinstance(value, str) else value
    return sorted({name for name, pattern in SECRET_PATTERNS if pattern.search(serialized)})


def document_id(canonical_url: str) -> str:
    return "doc:" + sha256_text(f"{SOURCE_TYPE}|{canonicalize_url(canonical_url)}")[:32]


def section_id(doc_id: str, heading_path: Sequence[str]) -> str:
    identity = " > ".join(normalized_heading(item) for item in heading_path)
    return "sec:" + sha256_text(f"{doc_id}|{identity}")[:32]


def section_version_id(section_identity: str, source_version: str, checksum: str) -> str:
    return "secv:" + sha256_text(f"{section_identity}|{source_version}|{checksum}")[:32]


def chunk_id(section_version: str, semantic_identity: str) -> str:
    return "aem_cmms:" + sha256_text(f"{section_version}|{semantic_identity}")[:32]


def tokenize(value: str) -> list[str]:
    return [match.group(0).casefold() for match in TOKEN_RE.finditer(value or "")]


SEARCH_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "be",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "should",
        "the",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
    }
)


def _search_token_variants(value: str) -> list[str]:
    """Return deterministic lexical variants without an external NLP model."""
    value = re.sub(
        r"\bservice\s+pack\s+(\d+)\b",
        lambda match: f"service pack {match.group(1)} sp{match.group(1)}",
        value or "",
        flags=re.IGNORECASE,
    )
    output: list[str] = []
    for raw_token in tokenize(value):
        parts = re.findall(r"[a-z0-9]+", raw_token)
        candidates = [raw_token, *parts]
        for token in candidates:
            if token not in output:
                output.append(token)
            stems: list[str] = []
            if len(token) > 5 and token.endswith("ies"):
                stems.append(token[:-3] + "y")
            if len(token) > 5 and token.endswith("ing"):
                stems.append(token[:-3])
            if len(token) > 4 and token.endswith("ed"):
                stems.extend((token[:-2], token[:-1]))
            if len(token) > 4 and token.endswith("es"):
                stems.append(token[:-2])
            if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
                stems.append(token[:-1])
            for stem in stems:
                if len(stem) >= 3 and stem not in output:
                    output.append(stem)
    return output


def _significant_search_tokens(value: str) -> set[str]:
    return {
        token
        for token in _search_token_variants(value)
        if token not in SEARCH_STOPWORDS and len(token) > 1
    }


def _semantic_phrase_present(term: str, content: str) -> bool:
    """Match harmless grammar/inflection changes while retaining key concepts."""
    normalized_term = normalize_semantic_text(term).casefold()
    normalized_content = normalize_semantic_text(content).casefold()
    if normalized_term and normalized_term in normalized_content:
        return True
    required_units: list[str] = []
    for token in tokenize(term):
        parts = re.findall(r"[a-z0-9]+", token)
        if ("-" in token or "_" in token) and len(parts) > 1:
            required_units.extend(parts)
        else:
            required_units.append(token)
    required_units = [
        token
        for token in required_units
        if token not in SEARCH_STOPWORDS and len(token) > 1
    ]
    if not required_units:
        return False
    available = _significant_search_tokens(content)
    return all(
        bool(set(_search_token_variants(token)) & available)
        for token in required_units
    )


@dataclass
class SectionBlock:
    heading_path: list[str]
    anchor: str
    block_type: str
    ordinal: int
    text: str


@dataclass
class ExtractedTable:
    heading_path: list[str]
    anchor: str
    rows: list[list[str]]
    source_order: int

    def __bool__(self) -> bool:
        return bool(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __getitem__(self, index: int) -> list[str]:
        return self.rows[index]


@dataclass
class FetchedDocument:
    source: SourceSpec
    canonical_url: str
    title: str
    raw_title: str
    last_updated: str
    retrieved_at: str
    source_checksum: str
    anchors: set[str]
    heading_anchors: set[str] = field(default_factory=set)
    blocks: list[SectionBlock] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    permission_footnotes: dict[str, str] = field(default_factory=dict)
    raw_text: str = ""


def _heading_anchor(element: Tag) -> str:
    direct = str(element.get("id") or element.get("name") or "")
    if direct:
        return direct
    nested = element.find(attrs={"id": True}) or element.find(attrs={"name": True})
    return str(nested.get("id") or nested.get("name") or "") if isinstance(nested, Tag) else ""


def _extract_last_updated(main: Tag) -> str:
    match = LAST_UPDATED_RE.search(main.get_text("\n", strip=True))
    return normalize_semantic_text(match.group(1)) if match else "UNKNOWN"


def _iter_semantic_blocks(main: Tag) -> Iterator[SectionBlock]:
    heading_stack: list[tuple[int, str, str]] = []
    started = False
    ordinal = 0
    seen: set[tuple[str, str, str]] = set()
    selector = "h1,h2,h3,h4,h5,h6,p,li,pre"
    for element in main.select(selector):
        if not isinstance(element, Tag):
            continue
        if element.name and element.name.startswith("h"):
            started = True
            level = int(element.name[1])
            title = ANCHOR_SUFFIX_RE.sub("", element.get_text(" ", strip=True)).strip()
            anchor = _heading_anchor(element)
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title, anchor))
            continue
        if (
            not started
            or element.find_parent("table") is not None
            or element.find_parent(class_="table") is not None
            or element.find_parent(class_="article-metadata-topics") is not None
            or element.find_parent(class_="article-metadata-createdby") is not None
        ):
            continue
        if element.name == "li" and element.find_parent("li") is not None:
            continue
        if element.name == "p" and element.find_parent("li") is not None:
            continue
        text = redact_secrets(normalize_semantic_text(element.get_text(" ", strip=True)))
        text = normalize_semantic_text(
            re.sub(r"\{[^}]*(?:align|width)=[^}]*\}", " ", text, flags=re.IGNORECASE)
        )
        # Experience League's responsive table renderer injects cosmetic
        # accessibility labels such as ``table 0-row-3`` into enclosing prose.
        # The same DOM table is extracted structurally below, so retaining the
        # enclosing flattened text would duplicate and corrupt table semantics.
        if re.search(r"\btable\s+\d+-row-\d+\b", text, re.IGNORECASE):
            continue
        if not text or len(text) < 4:
            continue
        headings = [item[1] for item in heading_stack] or ["Document"]
        anchor = heading_stack[-1][2] if heading_stack else ""
        words = text.split()
        chunks = [
            " ".join(words[start : start + 220])
            for start in range(0, len(words), 220)
        ]
        for chunk in chunks:
            semantic_key = (" > ".join(headings), element.name or "text", chunk.casefold())
            if semantic_key in seen:
                continue
            seen.add(semantic_key)
            ordinal += 1
            yield SectionBlock(headings, anchor, element.name or "text", ordinal, chunk)


def _parse_div_table(table: Tag) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.find_all(recursive=False):
        if not isinstance(row, Tag):
            continue
        cells = [
            redact_secrets(normalize_semantic_text(cell.get_text(" ", strip=True)))
            for cell in row.find_all(recursive=False)
            if isinstance(cell, Tag)
        ]
        if cells:
            rows.append(cells)
    return rows


def _parse_native_table(table: Tag) -> list[list[str]]:
    """Expand a native table to a rectangular grid, including row/col spans."""
    rows: list[list[str]] = []
    pending: dict[int, tuple[int, str]] = {}
    for row in table.select("tr"):
        values: list[str] = []
        column = 0

        def consume_pending() -> None:
            nonlocal column
            while column in pending:
                remaining, value = pending[column]
                values.append(value)
                if remaining <= 1:
                    del pending[column]
                else:
                    pending[column] = (remaining - 1, value)
                column += 1

        for cell in row.select(":scope > th, :scope > td"):
            consume_pending()
            value = redact_secrets(normalize_semantic_text(cell.get_text(" ", strip=True)))
            try:
                colspan = max(1, int(cell.get("colspan") or 1))
                rowspan = max(1, int(cell.get("rowspan") or 1))
            except (TypeError, ValueError):
                colspan = rowspan = 1
            for offset in range(colspan):
                values.append(value)
                if rowspan > 1:
                    pending[column + offset] = (rowspan - 1, value)
            column += colspan
        consume_pending()
        if values:
            rows.append(values)
    return rows


def _normalize_table_rows(rows: list[list[str]]) -> list[list[str]]:
    if not rows:
        return rows
    normalized_rows = [
        [
            normalize_semantic_text(
                re.sub(r"\{[^}]*(?:align|width)=[^}]*\}", " ", cell, flags=re.IGNORECASE)
            )
            for cell in row
        ]
        for row in rows
    ]
    normalized_rows = [row for row in normalized_rows if any(cell for cell in row)]
    if not normalized_rows:
        return []

    first = normalized_rows[0]
    if (
        first
        and re.search(r"\b\d+-row-\d+\b", first[0], re.IGNORECASE)
        and not any(first[1:])
    ):
        normalized_rows = normalized_rows[1:]
    if not normalized_rows:
        return []

    marker = normalized_rows[0][0].casefold() if normalized_rows[0] else ""
    # Responsive Experience League accordions are renderer containers, not
    # source tables. Their flattened children can otherwise become enormous,
    # duplicate ``accordion: ...`` records.
    if re.match(r"^accordion(?:\b|:)", marker):
        return []
    if marker in {"note", "note important", "important", "caution", "warning"}:
        body = " ".join(
            " ".join(cell for cell in row if cell)
            for row in normalized_rows[1:]
            if row
            and row[0].casefold()
            not in {"note", "note important", "important", "caution", "warning", "note tip", "tip"}
        )
        return [["admonition_type", "text"], [marker.upper(), body]] if body else []

    renderer_labels = {
        "accordion",
        "note tip",
        "tip",
        "note",
    }

    def is_renderer_only_row(row: list[str]) -> bool:
        values = [cell.casefold() for cell in row if cell]
        if not values:
            return True
        if all(value in renderer_labels for value in values):
            return True
        joined = " ".join(values).rstrip(".")
        return joined == "select near any field to view more details about it"

    return [row for row in normalized_rows if not is_renderer_only_row(row)]


def extract_structured_tables(main: Tag) -> list[ExtractedTable]:
    tables: list[ExtractedTable] = []
    seen: set[str] = set()
    heading_stack: list[tuple[int, str, str]] = []
    source_order = 0
    selector = "h1,h2,h3,h4,h5,h6,table,div.table"
    for element in main.select(selector):
        if element.name and element.name.startswith("h"):
            level = int(element.name[1])
            title = ANCHOR_SUFFIX_RE.sub("", element.get_text(" ", strip=True)).strip()
            anchor = _heading_anchor(element)
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title, anchor))
            continue
        if element.name == "table":
            rows = _normalize_table_rows(_parse_native_table(element))
        else:
            if element.find("table") is not None or element.find_parent(class_="table") is not None:
                continue
            rows = _normalize_table_rows(_parse_div_table(element))
        headings = [item[1] for item in heading_stack] or ["Document"]
        anchor = heading_stack[-1][2] if heading_stack else ""
        key = stable_json({"heading_path": headings, "anchor": anchor, "rows": rows})
        if rows and key not in seen:
            source_order += 1
            tables.append(ExtractedTable(headings, anchor, rows, source_order))
            seen.add(key)
    return tables


def extract_permission_footnotes(main: Tag) -> dict[str, str]:
    """Read numbered permission notes from their DOM markers, not page text."""
    notes: dict[str, str] = {}
    for paragraph in main.select("p"):
        anchors = [
            anchor
            for anchor in paragraph.select(":scope > a[href]")
            if re.fullmatch(r"#fnsrc_\d+", str(anchor.get("href") or ""))
        ]
        for anchor in anchors:
            number = str(anchor.get("href") or "").rsplit("_", 1)[-1]
            pieces: list[str] = []
            for sibling in anchor.next_siblings:
                if isinstance(sibling, Tag) and re.fullmatch(
                    r"#fnsrc_\d+", str(sibling.get("href") or "")
                ):
                    break
                text = sibling.get_text(" ", strip=True) if isinstance(sibling, Tag) else str(sibling)
                if text.strip():
                    pieces.append(text)
            value = redact_secrets(normalize_semantic_text(" ".join(pieces)))
            if number in notes:
                raise ValueError(f"duplicate permission footnote marker {number}")
            if value:
                notes[number] = f"{number} {value}"
    return notes


def fetch_document(
    source: SourceSpec,
    *,
    session: requests.Session,
    retrieved_at: str,
    timeout: float = 45.0,
) -> FetchedDocument:
    response = session.get(source.url, timeout=timeout, allow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    canonical_node = soup.select_one('link[rel="canonical"]')
    declared_canonical = canonicalize_url(canonical_node.get("href", "")) if canonical_node else ""
    expected = canonicalize_url(source.url)
    final_url = canonicalize_url(response.url)
    if final_url != expected:
        raise ValueError(f"{source.source_id} redirected outside canonical identity: {final_url}")
    if declared_canonical and declared_canonical != expected:
        raise ValueError(
            f"{source.source_id} canonical mismatch: expected {expected}, page declares {declared_canonical}"
        )
    main = soup.select_one("main")
    if main is None:
        raise ValueError(f"{source.source_id} has no main DOM node")
    raw_title = normalize_semantic_text(soup.title.get_text(" ", strip=True) if soup.title else source.label)
    h1 = main.select_one("h1")
    title = ANCHOR_SUFFIX_RE.sub("", h1.get_text(" ", strip=True)).strip() if h1 else raw_title
    raw_text = redact_secrets(normalize_semantic_text(main.get_text(" ", strip=True)))
    anchors = {
        str(node.get("id") or node.get("name"))
        for node in main.select("[id], [name]")
        if node.get("id") or node.get("name")
    }
    heading_anchors = {
        str(node.get("id") or node.get("name"))
        for node in main.select("h1[id],h2[id],h3[id],h4[id],h5[id],h6[id],h1[name],h2[name],h3[name],h4[name],h5[name],h6[name]")
        if node.get("id") or node.get("name")
    }
    return FetchedDocument(
        source=source,
        canonical_url=expected,
        title=title,
        raw_title=raw_title,
        last_updated=_extract_last_updated(main),
        retrieved_at=retrieved_at,
        source_checksum=sha256_text(raw_text),
        anchors=anchors,
        heading_anchors=heading_anchors,
        blocks=list(_iter_semantic_blocks(main)),
        tables=extract_structured_tables(main),
        permission_footnotes=extract_permission_footnotes(main),
        raw_text=raw_text,
    )


def resolve_legacy_anchor(document: FetchedDocument, alias_url: str) -> dict[str, Any]:
    fragment = urlsplit(alias_url).fragment
    matches = sorted(anchor for anchor in document.heading_anchors if anchor == fragment)
    if len(matches) == 1:
        status = "RESOLVED"
        resolved_anchor = matches[0]
    else:
        status = "UNRESOLVED_LEGACY_ANCHOR"
        resolved_anchor = ""
    return {
        "alias_url": alias_url,
        "canonical_document_id": document_id(document.canonical_url),
        "fragment": fragment,
        "status": status,
        "resolved_anchor": resolved_anchor,
        "match_count": len(matches),
        "attempted_against_live_dom": True,
        "match_scope": "HEADING_ANCHOR_MAP",
    }


def _top_level_capability(capability: str) -> str:
    for top_level, leaves in CAPABILITY_TAXONOMY.items():
        if capability in leaves:
            return top_level
    return "UNKNOWN"


def classify_block(source: SourceSpec, block: SectionBlock) -> dict[str, Any]:
    haystack = normalize_semantic_text(" ".join([*block.heading_path, block.text])).casefold()
    matches: list[tuple[int, ClassificationRule]] = []
    for index, rule in enumerate(CLASSIFICATION_RULES):
        if source.source_id not in rule.sources:
            continue
        found = re.findall(rule.pattern, haystack, re.IGNORECASE)
        if found:
            matches.append((len(found) * 100 - index, rule))
    matches.sort(key=lambda item: item[0], reverse=True)
    primary = matches[0][1] if matches else None
    capabilities = []
    for _score, rule in matches:
        if rule.capability not in capabilities:
            capabilities.append(rule.capability)
    capability = primary.capability if primary else source.default_capability
    return {
        "top_level_capability": _top_level_capability(capability),
        "capability": capability,
        "capabilities": capabilities or [capability],
        "sub_capability": primary.sub_capability if primary else "UNKNOWN",
        "record_type": primary.record_type if primary else "BEHAVIOR",
    }


def _currentness_enum(
    source: SourceSpec,
    *,
    currentness_label: str | None = None,
    deployment_model: str | None = None,
) -> CurrentnessState:
    label = currentness_label or source.currentness
    deployment = deployment_model or source.deployment_model
    if source.source_id == "SOURCE-10" and deployment in {"CLOUD_SERVICE", "ON_PREMISE"}:
        return CurrentnessState.ENVIRONMENT_SPECIFIC
    if source.source_id in {"SOURCE-8", "SOURCE-9"}:
        return CurrentnessState.VERSION_SPECIFIC
    if label == "VERSION_ROUTING_DOCUMENT":
        return CurrentnessState.VERSION_SPECIFIC
    if "HISTORICAL" in label:
        return CurrentnessState.HISTORICAL_COMPATIBILITY
    if label in {"CURRENT", "CURRENT_CONTEXT"} or label.startswith("CURRENT_"):
        return CurrentnessState.CURRENT
    return CurrentnessState.VERSION_UNKNOWN


def assertion_scope(
    document: FetchedDocument,
    heading_path: Sequence[str],
    text: str,
) -> tuple[str, str]:
    """Return assertion-level deployment/currentness for mixed SOURCE-10 docs."""
    source = document.source
    if source.source_id != "SOURCE-10":
        return source.deployment_model, source.currentness
    value = " ".join([*heading_path, text]).casefold()
    cloud = bool(re.search(r"cloud service|/var/dxml|aem as a cloud service", value))
    on_premise = bool(
        re.search(r"on[- ]premise|on prem|/apps/fmdita|server directory|package manager", value)
    )
    if cloud and not on_premise:
        return "CLOUD_SERVICE", "CURRENT_CLOUD_ASSERTION"
    if on_premise and not cloud:
        return "ON_PREMISE", "CURRENT_ON_PREMISE_ASSERTION"
    return "CLOUD_SERVICE_AND_ON_PREMISE", "CURRENT_SHARED_ASSERTION"


def _contract_ownership(source: SourceSpec) -> ProductContractOwnership:
    if source.product_area == "DITA_OT_CONFIGURATION":
        return ProductContractOwnership.DITA_OT_PROCESSING_BEHAVIOR
    return ProductContractOwnership.AEM_GUIDES_PRODUCT_CONTRACT


def build_evidence_record(
    *,
    document: FetchedDocument,
    native_id: str,
    capability: str,
    surface: str,
    content: dict[str, Any],
    metadata: dict[str, Any],
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT,
    derived_from: Iterable[str] = (),
    deployment_model: str | None = None,
    currentness_label: str | None = None,
) -> EvidenceRecord:
    source = document.source
    effective_deployment = deployment_model or source.deployment_model
    effective_currentness = currentness_label or source.currentness
    return EvidenceRecord(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference=f"experience-league:{source.source_id}:{document.canonical_url}",
        source_location=document.canonical_url,
        source_native_id=native_id,
        tenant_id=TENANT_ID,
        product="AEM Guides",
        product_area=source.product_area,
        capability=capability,
        surface=surface,
        content=content,
        extracted_facts=[str(content.get("normalized_semantic_value") or "")],
        source_timestamp=document.last_updated,
        retrieved_at=document.retrieved_at,
        product_version=(
            ",".join(value for value in (source.source_version, source.target_version) if value != "UNKNOWN")
        ),
        deployment_model=effective_deployment,
        currentness=_currentness_enum(
            source,
            currentness_label=effective_currentness,
            deployment_model=effective_deployment,
        ),
        evidence_confidence=0.98 if source.source_id != "SOURCE-5" else 0.85,
        requirement_authority=(
            AuthorityClass.TECHNICALLY_INFERRED
            if source.source_id == "SOURCE-5"
            else AuthorityClass.OFFICIAL_PRODUCT_CONTRACT
        ),
        verification_status=VerificationState.VERIFIED_SOURCE,
        lifecycle_status=EvidenceLifecycleStatus.USED,
        evidence_role="PRIMARY" if source.source_id != "SOURCE-5" else "SUPPORTING_CONTEXT",
        retrieval_pass="single-pass-official-doc-ingestion",
        inspected=True,
        used=True,
        directness=directness,
        version_scope=VersionScope(
            product_versions=[
                value for value in (source.source_version, source.target_version) if value != "UNKNOWN"
            ],
            deployment_model=effective_deployment,
            source_updated_at=document.last_updated,
            retrieved_at=document.retrieved_at,
        ),
        ownership=ProductOwnership(
            product="AEM Guides",
            product_area=source.product_area,
            capability=capability,
            surface=surface,
            contract_ownership=_contract_ownership(source),
            layer="documentation",
            owner_status="confirmed",
            owner_source_ids=[source.source_id],
        ),
        visibility=SourceVisibility(
            classification=VisibilityClass.PUBLIC,
            tenant_id=TENANT_ID,
            contains_customer_data=False,
            redacted=True,
        ),
        claim_keys=[f"{source.source_id}:{capability}:{native_id}"],
        derived_from=list(derived_from),
        metadata={
            **metadata,
            "authority_class": source.authority_class,
            "authority_priority": source.authority_priority,
            "currentness_label": effective_currentness,
            "override_policy": (
                "SUPPORTING_ONLY_CANNOT_OVERRIDE_PROCEDURAL_RUNBOOK"
                if source.source_id == "SOURCE-5"
                else "PRIMARY_WITHIN_APPLICABLE_SCOPE"
            ),
            "source_version": source.source_version,
            "target_version": source.target_version,
            "migration_direction": source.migration_direction,
        },
    )


def _record_content_text(record: dict[str, Any]) -> str:
    content = record.get("content")
    return str(content or "")


COMMON_RECORD_FIELDS: tuple[str, ...] = (
    "canonical_url",
    "document_id",
    "title",
    "raw_source_title",
    "source_last_updated",
    "retrieved_at",
    "heading_path",
    "section_anchor",
    "product",
    "product_area",
    "capability",
    "sub_capability",
    "deployment_model",
    "source_version",
    "target_version",
    "migration_direction",
    "role",
    "permission_scope",
    "environment_type",
    "action",
    "preconditions",
    "state_transition",
    "expected_result",
    "failure_result",
    "configuration_dependency",
    "lifecycle_stage",
    "currentness",
    "authority",
    "confidence",
    "raw_source_literal",
    "normalized_semantic_value",
    "data_quality_warnings",
    "document_checksum",
    "section_checksum",
    "chunk_checksum",
    "evidence_record_id",
)


def complete_common_record_metadata(
    record: dict[str, Any],
    documents: dict[str, FetchedDocument],
) -> dict[str, Any]:
    """Populate the canonical common fields on every emitted corpus record."""
    source_id = str(record.get("source_id") or "")
    document = documents.get(source_id)
    facets = dict(record.get("facets") or {})
    permission_rows = record.get("permission_assertions") or []
    footnotes = sorted({str(row.get("footnote") or "") for row in permission_rows if row.get("footnote")})
    defaults: dict[str, Any] = {
        "canonical_url": record.get("source_url") or (document.canonical_url if document else "UNKNOWN"),
        "document_id": document_id(document.canonical_url) if document else "UNKNOWN",
        "title": document.title if document else "UNKNOWN",
        "raw_source_title": document.raw_title if document else "UNKNOWN",
        "source_last_updated": document.last_updated if document else "UNKNOWN",
        "retrieved_at": document.retrieved_at if document else "UNKNOWN",
        "heading_path": ["UNKNOWN"],
        "section_anchor": "UNKNOWN",
        "product": "AEM Guides",
        "product_area": document.source.product_area if document else "UNKNOWN",
        "capability": "UNKNOWN",
        "sub_capability": "UNKNOWN",
        "deployment_model": document.source.deployment_model if document else "UNKNOWN",
        "source_version": document.source.source_version if document else "UNKNOWN",
        "target_version": document.source.target_version if document else "UNKNOWN",
        "migration_direction": document.source.migration_direction if document else "UNKNOWN",
        "role": "MULTIPLE" if permission_rows else "UNKNOWN",
        "permission_scope": "FEATURE_PERMISSION_MATRIX" if permission_rows else "UNKNOWN",
        "environment_type": record.get("deployment_model") or "UNKNOWN",
        "action": facets.get("operation") or record.get("capability") or "UNKNOWN",
        "preconditions": footnotes or ["UNKNOWN"],
        "state_transition": facets.get("state_transition") or "UNKNOWN",
        "expected_result": facets.get("expected_result") or "UNKNOWN",
        "failure_result": facets.get("failure_result") or "UNKNOWN",
        "configuration_dependency": (
            " | ".join(footnotes) if footnotes else facets.get("configuration_dependency") or "UNKNOWN"
        ),
        "lifecycle_stage": record.get("record_type") or "UNKNOWN",
        "currentness": document.source.currentness if document else "UNKNOWN",
        "authority": document.source.authority_class if document else "UNKNOWN",
        "confidence": 0.85 if source_id == "SOURCE-5" else 0.98,
        "raw_source_literal": "UNKNOWN",
        "normalized_semantic_value": "UNKNOWN",
        "data_quality_warnings": [],
        "document_checksum": record.get("source_checksum") or "UNKNOWN",
        "section_checksum": "UNKNOWN",
        "chunk_checksum": "UNKNOWN",
        "evidence_record_id": "UNKNOWN",
    }
    for key, value in defaults.items():
        if key not in record or record[key] is None or record[key] == "":
            record[key] = value
    record["environment_type"] = record.get("deployment_model") or "UNKNOWN"
    record["document_checksum"] = record.get("source_checksum") or record.get("document_checksum") or "UNKNOWN"
    return record


def build_block_record(
    document: FetchedDocument,
    block: SectionBlock,
    *,
    semantic_section_checksum: str | None = None,
) -> dict[str, Any]:
    classification = classify_block(document.source, block)
    deployment_model, currentness_label = assertion_scope(
        document, block.heading_path, block.text
    )
    doc_identity = document_id(document.canonical_url)
    sec_identity = section_id(doc_identity, block.heading_path)
    sec_checksum = semantic_section_checksum or sha256_text(block.text)
    source_version = document.last_updated
    sec_version = section_version_id(sec_identity, source_version, sec_checksum)
    semantic_identity = (
        f"{classification['capability']}|{block.block_type}|{sha256_text(block.text)[:16]}"
    )
    identity = chunk_id(sec_version, semantic_identity)
    warnings = [
        warning
        for pattern, warning in DATA_QUALITY_PATTERNS
        if re.search(pattern, block.text, re.IGNORECASE)
    ]
    structured_content = {
        "canonical_url": document.canonical_url,
        "source_document_id": doc_identity,
        "source_title": document.title,
        "raw_source_title": document.raw_title,
        "source_last_updated": document.last_updated,
        "heading_hierarchy": block.heading_path,
        "section_anchor": block.anchor,
        "product": "AEM Guides",
        "product_area": document.source.product_area,
        "capability": classification["capability"],
        "sub_capability": classification["sub_capability"],
        "deployment_model": deployment_model,
        "source_product_version": document.source.source_version,
        "target_product_version": document.source.target_version,
        "migration_direction": document.source.migration_direction,
        "role": "UNKNOWN",
        "permission_scope": "UNKNOWN",
        "environment_type": deployment_model,
        "action": "UNKNOWN",
        "preconditions": [],
        "state_transition": "UNKNOWN",
        "expected_result": "UNKNOWN",
        "failure_result": "UNKNOWN",
        "configuration_dependency": "UNKNOWN",
        "lifecycle_stage": classification["record_type"],
        "currentness": currentness_label,
        "authority": document.source.authority_class,
        "confidence": 0.98 if document.source.source_id != "SOURCE-5" else 0.85,
        "raw_source_literal": block.text,
        "normalized_semantic_value": normalize_semantic_value(block.text),
        "data_quality_warnings": warnings,
    }
    evidence = build_evidence_record(
        document=document,
        native_id=identity,
        capability=classification["capability"],
        surface=" > ".join(block.heading_path),
        content=structured_content,
        metadata={
            "source_id": document.source.source_id,
            "record_type": classification["record_type"],
            "capabilities": classification["capabilities"],
            "section_id": sec_identity,
            "section_version_id": sec_version,
            "data_quality_warnings": warnings,
        },
        deployment_model=deployment_model,
        currentness_label=currentness_label,
    )
    searchable = (
        f"{document.title}. {' > '.join(block.heading_path)}. "
        f"Capability: {classification['capability']}. {block.text}"
    )
    checksum = sha256_text(searchable)
    return {
        "id": identity,
        "chunk_id": identity,
        "url": document.canonical_url,
        "source_url": document.canonical_url,
        "canonical_url": document.canonical_url,
        "source_type": SOURCE_TYPE,
        "corpus": "aem_guides",
        "ingestion_batch": BATCH_ID,
        "parser_version": PARSER_VERSION,
        "source_id": document.source.source_id,
        "document_id": doc_identity,
        "section_id": sec_identity,
        "section_version_id": sec_version,
        "title": document.title,
        "raw_source_title": document.raw_title,
        "source_last_updated": document.last_updated,
        "retrieved_at": document.retrieved_at,
        "heading_path": block.heading_path,
        "section_anchor": block.anchor,
        "chunk_index": block.ordinal,
        "capability": classification["capability"],
        "capabilities": classification["capabilities"],
        "sub_capability": classification["sub_capability"],
        "top_level_capability": classification["top_level_capability"],
        "record_type": classification["record_type"],
        "authority": document.source.authority_class,
        "authority_priority": document.source.authority_priority,
        "currentness": currentness_label,
        "deployment_model": deployment_model,
        "source_version": document.source.source_version,
        "target_version": document.source.target_version,
        "migration_direction": document.source.migration_direction,
        "source_checksum": document.source_checksum,
        "section_checksum": sec_checksum,
        "chunk_checksum": checksum,
        "checksum": "sha256:" + checksum,
        "content": searchable,
        "raw_source_literal": block.text,
        "normalized_semantic_value": normalize_semantic_value(block.text),
        "data_quality_warnings": warnings,
        "evidence_record_id": evidence.evidence_id,
        "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
    }


def build_document_block_records(document: FetchedDocument) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[SectionBlock]] = defaultdict(list)
    for block in document.blocks:
        grouped[tuple(block.heading_path)].append(block)
    checksums = {
        heading_path: sha256_text(
            stable_json(
                [
                    {"block_type": block.block_type, "text": block.text}
                    for block in blocks
                ]
            )
        )
        for heading_path, blocks in grouped.items()
    }
    return [
        build_block_record(
            document,
            block,
            semantic_section_checksum=checksums[tuple(block.heading_path)],
        )
        for block in document.blocks
    ]


def _structured_table_fields(headers: list[str], row: list[str]) -> dict[str, str]:
    """Return lossless, deterministic field names even for blank/duplicate headers."""
    width = max(len(headers), len(row))
    padded_headers = [
        *headers,
        *[f"column_{index + 1}" for index in range(len(headers), width)],
    ]
    padded_row = [*row, *([""] * (width - len(row)))]
    names: list[str] = []
    occurrences: Counter[str] = Counter()
    for index, header in enumerate(padded_headers):
        base = header or f"column_{index + 1}"
        occurrences[base] += 1
        names.append(base if occurrences[base] == 1 else f"{base} [{occurrences[base]}]")
    return {names[index]: padded_row[index] for index in range(width)}


def _semantic_table_fields(fields: dict[str, str]) -> list[dict[str, str]]:
    return [
        {
            "name": normalize_semantic_text(name).casefold(),
            "value": normalize_semantic_value(value).casefold(),
        }
        for name, value in fields.items()
    ]


def _table_section_checksums(document: FetchedDocument) -> dict[tuple[str, ...], str]:
    """Hash semantic table rows without depending on DOM table/row order."""
    grouped: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for table in document.tables:
        if not table.rows or _is_permission_matrix(table):
            continue
        headers = table.rows[0]
        for row in table.rows[1:]:
            if not any(cell.strip() for cell in row):
                continue
            fields = _structured_table_fields(headers, row)
            grouped[tuple(table.heading_path)].add(
                stable_json(
                    {
                        "section_anchor": table.anchor,
                        "fields": _semantic_table_fields(fields),
                    }
                )
            )
    return {
        heading_path: sha256_text(stable_json(sorted(row_payloads)))
        for heading_path, row_payloads in grouped.items()
    }


def build_table_records(document: FetchedDocument) -> list[dict[str, Any]]:
    """Emit one structured record per non-permission DOM table row."""
    output: list[dict[str, Any]] = []
    ordinal = 0
    seen_row_ids: set[str] = set()
    section_checksums = _table_section_checksums(document)
    for table in document.tables:
        if not table.rows or _is_permission_matrix(table):
            continue
        headers = table.rows[0]
        for row_index, row in enumerate(table.rows[1:], start=1):
            if not any(cell.strip() for cell in row):
                continue
            fields = _structured_table_fields(headers, row)
            raw_literal = " | ".join(row)
            normalized = normalize_semantic_value(
                "; ".join(f"{key}: {value}" for key, value in fields.items() if value)
            )
            block = SectionBlock(
                heading_path=list(table.heading_path),
                anchor=table.anchor,
                block_type="table_row",
                ordinal=ordinal + 1,
                text=normalized or raw_literal,
            )
            classification = classify_block(document.source, block)
            deployment_model, currentness_label = assertion_scope(
                document, block.heading_path, block.text
            )
            doc_identity = document_id(document.canonical_url)
            sec_identity = section_id(doc_identity, block.heading_path)
            sec_checksum = section_checksums[tuple(block.heading_path)]
            sec_version = section_version_id(sec_identity, document.last_updated, sec_checksum)
            semantic_row = {
                "record_type": "STRUCTURED_TABLE_ROW",
                "section_anchor": block.anchor,
                "fields": _semantic_table_fields(fields),
            }
            semantic_identity = "structured-table-row:" + sha256_text(
                stable_json(semantic_row)
            )
            identity = chunk_id(sec_version, semantic_identity)
            if identity in seen_row_ids:
                continue
            seen_row_ids.add(identity)
            ordinal += 1
            warnings = [
                warning
                for pattern, warning in DATA_QUALITY_PATTERNS
                if re.search(pattern, raw_literal, re.IGNORECASE)
            ]
            content = {
                "canonical_url": document.canonical_url,
                "source_document_id": doc_identity,
                "source_title": document.title,
                "raw_source_title": document.raw_title,
                "source_last_updated": document.last_updated,
                "heading_hierarchy": block.heading_path,
                "section_anchor": block.anchor,
                "product": "AEM Guides",
                "product_area": document.source.product_area,
                "capability": classification["capability"],
                "sub_capability": classification["sub_capability"],
                "deployment_model": deployment_model,
                "source_product_version": document.source.source_version,
                "target_product_version": document.source.target_version,
                "migration_direction": document.source.migration_direction,
                "lifecycle_stage": "STRUCTURED_TABLE_ROW",
                "currentness": currentness_label,
                "authority": document.source.authority_class,
                "confidence": 0.98 if document.source.source_id != "SOURCE-5" else 0.85,
                "raw_source_literal": raw_literal,
                "normalized_semantic_value": normalized,
                "structured_fields": fields,
                "data_quality_warnings": warnings,
            }
            evidence = build_evidence_record(
                document=document,
                native_id=identity,
                capability=classification["capability"],
                surface=" > ".join(block.heading_path),
                content=content,
                metadata={
                    "source_id": document.source.source_id,
                    "record_type": "STRUCTURED_TABLE_ROW",
                    "capabilities": classification["capabilities"],
                    "section_id": sec_identity,
                    "section_version_id": sec_version,
                    "table_source_order": table.source_order,
                    "row_index": row_index,
                },
                deployment_model=deployment_model,
                currentness_label=currentness_label,
            )
            searchable = (
                f"{document.title}. {' > '.join(block.heading_path)}. Structured table row. "
                f"Capability: {classification['capability']}. {normalized}"
            )
            checksum = sha256_text(searchable)
            output.append(
                {
                    "id": identity,
                    "chunk_id": identity,
                    "url": document.canonical_url,
                    "source_url": document.canonical_url,
                    "canonical_url": document.canonical_url,
                    "source_type": SOURCE_TYPE,
                    "corpus": "aem_guides",
                    "ingestion_batch": BATCH_ID,
                    "parser_version": PARSER_VERSION,
                    "source_id": document.source.source_id,
                    "document_id": doc_identity,
                    "section_id": sec_identity,
                    "section_version_id": sec_version,
                    "title": document.title,
                    "raw_source_title": document.raw_title,
                    "source_last_updated": document.last_updated,
                    "retrieved_at": document.retrieved_at,
                    "heading_path": block.heading_path,
                    "section_anchor": block.anchor,
                    "chunk_index": ordinal,
                    "table_source_order": table.source_order,
                    "table_row_index": row_index,
                    "capability": classification["capability"],
                    "capabilities": classification["capabilities"],
                    "sub_capability": classification["sub_capability"],
                    "top_level_capability": classification["top_level_capability"],
                    "record_type": "STRUCTURED_TABLE_ROW",
                    "authority": document.source.authority_class,
                    "authority_priority": document.source.authority_priority,
                    "currentness": currentness_label,
                    "deployment_model": deployment_model,
                    "source_version": document.source.source_version,
                    "target_version": document.source.target_version,
                    "migration_direction": document.source.migration_direction,
                    "source_checksum": document.source_checksum,
                    "section_checksum": sec_checksum,
                    "chunk_checksum": checksum,
                    "checksum": "sha256:" + checksum,
                    "content": searchable,
                    "raw_source_literal": raw_literal,
                    "normalized_semantic_value": normalized,
                    "structured_fields": fields,
                    "data_quality_warnings": warnings,
                    "evidence_record_id": evidence.evidence_id,
                    "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
                }
            )
    return output


def _permission_footnotes(document: FetchedDocument) -> dict[str, str]:
    return dict(document.permission_footnotes)


def _is_permission_matrix(table: ExtractedTable) -> bool:
    return bool(
        table.rows
        and [normalize_semantic_text(cell).casefold() for cell in table.rows[0]]
        == ["task", "authors", "reviewers", "publishers"]
    )


def _permission_cell_key(assertion: dict[str, Any]) -> tuple[str, str]:
    return (
        normalize_semantic_text(str(assertion.get("task") or "")).casefold(),
        normalize_semantic_text(str(assertion.get("role") or "")).casefold(),
    )


def _permission_decision_signature(assertion: dict[str, Any]) -> tuple[Any, str, str]:
    return (
        assertion.get("allowed"),
        normalize_semantic_text(str(assertion.get("cell_state") or "")).casefold(),
        normalize_semantic_text(str(assertion.get("footnote") or "")).casefold(),
    )


def parse_permission_assertions(document: FetchedDocument) -> list[dict[str, Any]]:
    assertions: list[dict[str, Any]] = []
    footnotes = _permission_footnotes(document)
    referenced_markers: set[str] = set()
    for table in document.tables:
        if not _is_permission_matrix(table):
            continue
        headers = table.rows[0]
        for row_index, row in enumerate(table.rows[1:], start=1):
            padded = [*row, *([""] * max(0, len(headers) - len(row)))]
            raw_task = padded[0]
            footnote_match = re.search(r"\b(\d+)\b\s*$", raw_task)
            footnote_number = footnote_match.group(1) if footnote_match else ""
            if footnote_number:
                referenced_markers.add(footnote_number)
            task = re.sub(r"\s+\d+\s*$", "", raw_task).strip()
            for column_index, role in enumerate(headers[1:], start=1):
                raw_cell = padded[column_index] if column_index < len(padded) else ""
                normalized = raw_cell.casefold()
                footnote = footnotes.get(footnote_number, "")
                role_is_conditional = bool(
                    footnote
                    and normalized == "yes"
                    and (
                        role.casefold() in footnote.casefold()
                        or re.search(r"\buser\b", footnote, re.IGNORECASE)
                    )
                )
                allowed: bool | None
                if role_is_conditional:
                    allowed = None
                elif normalized == "yes":
                    allowed = True
                elif normalized == "no":
                    allowed = False
                else:
                    allowed = None
                assertion_key = sha256_text(
                    stable_json(
                        {
                            "task": normalize_semantic_text(task).casefold(),
                            "role": normalize_semantic_text(role).casefold(),
                        }
                    )
                )
                assertions.append(
                    {
                        "assertion_id": "perm:" + assertion_key[:32],
                        "task": task,
                        "raw_task": raw_task,
                        "role": role,
                        "allowed": allowed,
                        "cell_state": (
                            "footnote-dependent"
                            if role_is_conditional
                            else "blank"
                            if raw_cell == ""
                            else normalized
                        ),
                        "footnote": footnote,
                        "footnote_number": footnote_number,
                        "source_id": document.source.source_id,
                        "canonical_url": document.canonical_url,
                        "heading_path": list(table.heading_path),
                        "section_anchor": table.anchor,
                        "table_source_order": table.source_order,
                        "row_index": row_index,
                        "column_index": column_index,
                    }
                )
    unresolved = sorted(referenced_markers - set(footnotes))
    if unresolved:
        raise ValueError(
            f"{document.source.source_id} permission footnote markers are unresolved: {unresolved}"
        )
    return assertions


def merge_permission_assertions(assertions: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for assertion in assertions:
        grouped[_permission_cell_key(assertion)].append(assertion)

    merged: list[dict[str, Any]] = []
    for key, candidates in grouped.items():
        candidates = sorted(candidates, key=lambda item: str(item.get("source_id") or ""))
        decisions_by_source: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            source_id = str(candidate.get("source_id") or "")
            location = {
                "heading_path": list(candidate.get("heading_path") or []),
                "section_anchor": str(candidate.get("section_anchor") or ""),
                "table_source_order": candidate.get("table_source_order"),
                "row_index": candidate.get("row_index"),
                "column_index": candidate.get("column_index"),
            }
            if source_id in decisions_by_source:
                existing = decisions_by_source[source_id]
                if _permission_decision_signature(existing) != _permission_decision_signature(candidate):
                    raise ValueError(
                        "conflicting permission decisions within "
                        f"{source_id} for task={candidate.get('task')!r}, role={candidate.get('role')!r}"
                    )
                if location not in existing["locations"]:
                    existing["locations"].append(location)
                continue
            decisions_by_source[source_id] = {
                "source_id": source_id,
                "canonical_url": str(candidate.get("canonical_url") or ""),
                "raw_task": str(candidate.get("raw_task") or ""),
                "allowed": candidate.get("allowed"),
                "cell_state": str(candidate.get("cell_state") or ""),
                "footnote": str(candidate.get("footnote") or ""),
                "footnote_number": str(candidate.get("footnote_number") or ""),
                "locations": [location],
            }

        source_decisions = [decisions_by_source[source_id] for source_id in sorted(decisions_by_source)]
        conflict_fields = [
            field_name
            for field_name in ("allowed", "cell_state", "footnote")
            if len(
                {
                    stable_json(decision.get(field_name))
                    for decision in source_decisions
                }
            )
            > 1
        ]
        primary = candidates[0]
        assertion_key = sha256_text(stable_json({"task": key[0], "role": key[1]}))
        decision_conflict = bool(conflict_fields)
        merged.append(
            {
                "assertion_id": "perm:" + assertion_key[:32],
                "task": primary["task"],
                "raw_task": primary.get("raw_task", primary["task"]),
                "raw_tasks": sorted(
                    {
                        str(candidate.get("raw_task") or candidate.get("task") or "")
                        for candidate in candidates
                    }
                ),
                "role": primary["role"],
                "allowed": None if decision_conflict else primary.get("allowed"),
                "cell_state": "conflict" if decision_conflict else primary.get("cell_state"),
                "footnote": "" if decision_conflict else str(primary.get("footnote") or ""),
                "footnote_number": (
                    "" if decision_conflict else str(primary.get("footnote_number") or "")
                ),
                "footnote_numbers": sorted(
                    {
                        str(candidate.get("footnote_number") or "")
                        for candidate in candidates
                        if candidate.get("footnote_number")
                    }
                ),
                "source_ids": sorted(decisions_by_source),
                "provenance_urls": sorted(
                    {
                        str(candidate.get("canonical_url") or "")
                        for candidate in candidates
                        if candidate.get("canonical_url")
                    }
                ),
                "source_decisions": source_decisions,
                "decision_conflict": decision_conflict,
                "conflict_fields": conflict_fields,
            }
        )
    return sorted(merged, key=lambda row: (row["task"], row["role"]))


def _permission_model_metrics(
    documents: dict[str, FetchedDocument],
    permissions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate permission coverage from the fetched matrix shape, not fixed counts."""
    tables_by_source = {
        source_id: [table for table in document.tables if _is_permission_matrix(table)]
        for source_id, document in documents.items()
    }
    tables_by_source = {
        source_id: tables for source_id, tables in tables_by_source.items() if tables
    }
    table_sources = sorted(tables_by_source)
    tables = [table for source_id in table_sources for table in tables_by_source[source_id]]

    def structurally_valid(table: ExtractedTable) -> bool:
        if len(table.rows) < 2:
            return False
        width = len(table.rows[0])
        if width < 2 or any(not normalize_semantic_text(header) for header in table.rows[0]):
            return False
        return all(
            len(row) == width
            and bool(normalize_semantic_text(row[0]))
            and all(
                normalize_semantic_text(cell).casefold() in {"", "yes", "no"}
                for cell in row[1:]
            )
            for row in table.rows[1:]
        )

    raw_by_source = {
        source_id: parse_permission_assertions(documents[source_id])
        for source_id in table_sources
    }
    source_keys = {
        source_id: [_permission_cell_key(assertion) for assertion in assertions]
        for source_id, assertions in raw_by_source.items()
    }
    no_duplicate_source_cells = all(
        len(keys) == len(set(keys)) for keys in source_keys.values()
    )
    key_sets = [set(keys) for keys in source_keys.values()]
    source_keysets_consistent = bool(key_sets) and all(
        keys == key_sets[0] for keys in key_sets[1:]
    )
    expected_keys = set().union(*key_sets) if key_sets else set()
    merged_keys = [_permission_cell_key(assertion) for assertion in permissions]
    merged_by_key = {
        _permission_cell_key(assertion): assertion for assertion in permissions
    }
    merged_cardinality_valid = (
        len(merged_keys) == len(set(merged_keys))
        and set(merged_keys) == expected_keys
    )
    expected_sources = set(table_sources)
    source_coverage_complete = bool(expected_sources) and all(
        key in merged_by_key
        and set(merged_by_key[key].get("source_ids") or []) == expected_sources
        and {
            str(decision.get("source_id") or "")
            for decision in merged_by_key[key].get("source_decisions") or []
        }
        == expected_sources
        for key in expected_keys
    )
    conflict_count = sum(
        1 for assertion in permissions if assertion.get("decision_conflict")
    )

    raw_assertions = [
        assertion
        for source_id in table_sources
        for assertion in raw_by_source[source_id]
    ]
    expected_blank_keys = {
        _permission_cell_key(assertion)
        for assertion in raw_assertions
        if assertion.get("cell_state") == "blank"
    }
    actual_blank_keys = {
        _permission_cell_key(assertion)
        for assertion in permissions
        if assertion.get("cell_state") == "blank"
    }
    expected_conditional_keys = {
        _permission_cell_key(assertion)
        for assertion in raw_assertions
        if assertion.get("cell_state") == "footnote-dependent"
    }
    actual_conditional_keys = {
        _permission_cell_key(assertion)
        for assertion in permissions
        if assertion.get("cell_state") == "footnote-dependent"
    }
    referenced_footnotes_resolved = all(
        bool(assertion.get("footnote"))
        for assertion in raw_assertions
        if assertion.get("footnote_number")
    )

    matrix_structural = (
        bool(tables)
        and all(structurally_valid(table) for table in tables)
        and no_duplicate_source_cells
        and source_keysets_consistent
        and bool(expected_keys)
        and actual_blank_keys == expected_blank_keys
    )
    duplicates_merged = (
        len(expected_sources) >= 2
        and merged_cardinality_valid
        and source_coverage_complete
    )
    footnotes_retained = (
        referenced_footnotes_resolved
        and actual_conditional_keys == expected_conditional_keys
    )
    return {
        "matrix_structural": matrix_structural,
        "footnotes_retained": footnotes_retained,
        "duplicates_merged": duplicates_merged,
        "decisions_consistent": conflict_count == 0,
        "source_ids": table_sources,
        "table_count": len(tables),
        "table_row_counts": [len(table.rows) - 1 for table in tables],
        "expected_cell_count": len(expected_keys),
        "actual_merged_cell_count": len(permissions),
        "blank_cell_count": len(actual_blank_keys),
        "conditional_cell_count": len(actual_conditional_keys),
        "conflict_count": conflict_count,
        "source_keysets_consistent": source_keysets_consistent,
        "source_coverage_complete": source_coverage_complete,
    }


def build_permission_records(
    documents: dict[str, FetchedDocument],
    assertions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Emit one compact embedding record per permission-matrix task."""
    records: list[dict[str, Any]] = []
    primary = documents["SOURCE-11"]
    matrix_checksum = sha256_text(
        stable_json(
            [
                {
                    "assertion_id": assertion["assertion_id"],
                    "task": assertion["task"],
                    "role": assertion["role"],
                    "allowed": assertion.get("allowed"),
                    "cell_state": assertion.get("cell_state"),
                    "footnote": assertion.get("footnote"),
                    "decision_conflict": assertion.get("decision_conflict", False),
                    "source_decisions": [
                        {
                            "source_id": decision.get("source_id"),
                            "allowed": decision.get("allowed"),
                            "cell_state": decision.get("cell_state"),
                            "footnote": decision.get("footnote"),
                        }
                        for decision in assertion.get("source_decisions") or []
                    ],
                }
                for assertion in sorted(
                    assertions,
                    key=lambda item: (str(item["task"]), str(item["role"])),
                )
            ]
        )
    )
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for assertion in assertions:
        by_task[str(assertion["task"])].append(assertion)
    for index, (task, decisions) in enumerate(sorted(by_task.items()), start=1):
        capability = "FEATURE_PERMISSION_MATRIX"
        task_lower = task.casefold()
        if "document state" in task_lower:
            capability = "DOCUMENT_STATE_TRANSITION_PERMISSION"
        decisions = sorted(decisions, key=lambda item: str(item["role"]))
        role_summary = "; ".join(
            f"{item['role']}: {item['cell_state']}"
            + (f" ({item['footnote']})" if item.get("footnote") else "")
            for item in decisions
        )
        content = f"Permission task: {task}. Role decisions: {role_summary}."
        source_ids = sorted({source_id for item in decisions for source_id in item["source_ids"]})
        provenance_urls = sorted(
            {url for item in decisions for url in item["provenance_urls"]}
        )
        doc_identity = document_id(primary.canonical_url)
        sec_identity = section_id(doc_identity, ["User groups created by AEM Guides", "Permission matrix"])
        sec_checksum = matrix_checksum
        sec_version = section_version_id(sec_identity, primary.last_updated, sec_checksum)
        identity = chunk_id(sec_version, f"permission-task:{normalized_heading(task)}")
        structured = {
            "raw_source_literal": content,
            "normalized_semantic_value": content,
            "task": task,
            "role_decisions": decisions,
            "permission_scope": "FEATURE_PERMISSION_MATRIX",
            "provenance_source_ids": source_ids,
            "provenance_urls": provenance_urls,
        }
        evidence = build_evidence_record(
            document=primary,
            native_id=identity,
            capability=capability,
            surface="User administration and security > Permission matrix",
            content=structured,
            metadata={
                "source_id": "SOURCE-11",
                "record_type": "PERMISSION_TASK_ASSERTION",
                "supporting_source_ids": [sid for sid in source_ids if sid != "SOURCE-11"],
                "semantic_dedup": len(source_ids) > 1,
            },
        )
        checksum = sha256_text(content)
        records.append(
            {
                "id": identity,
                "chunk_id": identity,
                "url": primary.canonical_url,
                "source_url": primary.canonical_url,
                "canonical_url": primary.canonical_url,
                "source_type": SOURCE_TYPE,
                "corpus": "aem_guides",
                "ingestion_batch": BATCH_ID,
                "parser_version": PARSER_VERSION,
                "source_id": "SOURCE-11",
                "provenance_source_ids": source_ids,
                "provenance_urls": provenance_urls,
                "document_id": doc_identity,
                "section_id": sec_identity,
                "section_version_id": sec_version,
                "title": "AEM Guides role permission matrix",
                "source_last_updated": primary.last_updated,
                "retrieved_at": primary.retrieved_at,
                "heading_path": ["User groups created by AEM Guides", "Permission matrix"],
                "section_anchor": "user-groups-created-by-aem-guides-headding-anchor-id181tf0k0mht",
                "chunk_index": index,
                "capability": capability,
                "capabilities": [capability],
                "sub_capability": task,
                "top_level_capability": "AEM_GUIDES_SECURITY",
                "record_type": "PERMISSION_TASK_ASSERTION",
                "authority": primary.source.authority_class,
                "authority_priority": primary.source.authority_priority,
                "currentness": primary.source.currentness,
                "deployment_model": primary.source.deployment_model,
                "source_version": primary.source.source_version,
                "target_version": primary.source.target_version,
                "migration_direction": primary.source.migration_direction,
                "source_checksum": primary.source_checksum,
                "section_checksum": sec_checksum,
                "chunk_checksum": checksum,
                "checksum": "sha256:" + checksum,
                "content": content,
                "raw_source_literal": content,
                "normalized_semantic_value": content,
                "data_quality_warnings": [],
                "permission_assertions": decisions,
                "evidence_record_id": evidence.evidence_id,
                "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
            }
        )
    return records


def build_legacy_anchor_record(
    document: FetchedDocument,
    anchor: dict[str, Any],
) -> dict[str, Any]:
    """Represent the alias attempt without inventing a heading mapping."""
    doc_identity = document_id(document.canonical_url)
    sec_identity = section_id(doc_identity, ["Legacy anchor resolution"])
    normalized = (
        f"Legacy anchor {anchor['fragment']} status: {anchor['status']}. "
        "The current DOM did not provide one unambiguous target, so the section is not guessed."
        if anchor["status"] == "UNRESOLVED_LEGACY_ANCHOR"
        else f"Legacy anchor {anchor['fragment']} resolves to verified DOM anchor {anchor['resolved_anchor']}."
    )
    sec_checksum = sha256_text(stable_json(anchor))
    sec_version = section_version_id(sec_identity, document.last_updated, sec_checksum)
    identity = chunk_id(sec_version, "legacy-anchor-alias-attempt")
    structured = {
        "raw_source_literal": anchor["fragment"],
        "normalized_semantic_value": normalized,
        "anchor_status": anchor["status"],
        "resolved_anchor": anchor["resolved_anchor"],
        "data_quality_warnings": (
            ["STALE_OR_UNRESOLVED_SOURCE_10_ANCHOR"]
            if anchor["status"] == "UNRESOLVED_LEGACY_ANCHOR"
            else []
        ),
    }
    evidence = build_evidence_record(
        document=document,
        native_id=identity,
        capability="AEM_GUIDES_DITA_OT_CONFIGURATION",
        surface="Legacy anchor resolution",
        content=structured,
        metadata={
            "source_id": "SOURCE-10",
            "record_type": "LEGACY_ANCHOR_ALIAS",
            "anchor_status": anchor["status"],
        },
    )
    checksum = sha256_text(normalized)
    return {
        "id": identity,
        "chunk_id": identity,
        "url": document.canonical_url,
        "source_url": document.canonical_url,
        "canonical_url": document.canonical_url,
        "source_type": SOURCE_TYPE,
        "corpus": "aem_guides",
        "ingestion_batch": BATCH_ID,
        "parser_version": PARSER_VERSION,
        "source_id": "SOURCE-10",
        "provenance_source_ids": ["SOURCE-10"],
        "provenance_urls": [document.canonical_url],
        "document_id": doc_identity,
        "section_id": sec_identity,
        "section_version_id": sec_version,
        "title": "SOURCE-10 legacy anchor resolution",
        "source_last_updated": document.last_updated,
        "retrieved_at": document.retrieved_at,
        "heading_path": ["Legacy anchor resolution"],
        "section_anchor": "",
        "chunk_index": 0,
        "capability": "AEM_GUIDES_DITA_OT_CONFIGURATION",
        "capabilities": ["AEM_GUIDES_DITA_OT_CONFIGURATION", "CUSTOM_DITA_OT_PLUGIN", "CUSTOM_DITA_SPECIALIZATION"],
        "sub_capability": "LEGACY_ANCHOR_ALIAS",
        "top_level_capability": "AEM_GUIDES_DITA_OT_CONFIGURATION",
        "record_type": "LEGACY_ANCHOR_ALIAS",
        "authority": document.source.authority_class,
        "authority_priority": document.source.authority_priority,
        "currentness": document.source.currentness,
        "deployment_model": document.source.deployment_model,
        "source_version": document.source.source_version,
        "target_version": document.source.target_version,
        "migration_direction": document.source.migration_direction,
        "source_checksum": document.source_checksum,
        "section_checksum": sec_checksum,
        "chunk_checksum": checksum,
        "checksum": "sha256:" + checksum,
        "content": normalized,
        "raw_source_literal": anchor["fragment"],
        "normalized_semantic_value": normalized,
        "data_quality_warnings": structured["data_quality_warnings"],
        "anchor_alias": anchor,
        "evidence_record_id": evidence.evidence_id,
        "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
    }


def deduplicate_semantic_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    merged: dict[str, dict[str, Any]] = {}
    links = 0
    for record in records:
        source_id = str(record.get("source_id") or "")
        normalized = re.sub(
            r"\W+",
            " ",
            str(record.get("normalized_semantic_value") or "").casefold(),
        ).strip()
        if (
            record.get("record_type") == "PERMISSION_ASSERTION"
            or source_id in {"SOURCE-8", "SOURCE-9"}
            or len(normalized) < 80
        ):
            key = str(record["chunk_id"])
        else:
            key = sha256_text(f"{record.get('capability')}|{normalized}")
        if key not in merged:
            merged[key] = {
                **record,
                "provenance_source_ids": sorted(
                    set(record.get("provenance_source_ids") or [source_id])
                ),
                "provenance_urls": sorted(
                    set(record.get("provenance_urls") or [record.get("canonical_url", "")])
                ),
            }
            continue
        target = merged[key]
        target["provenance_source_ids"] = sorted(
            set([*target.get("provenance_source_ids", []), source_id])
        )
        target["provenance_urls"] = sorted(
            set([*target.get("provenance_urls", []), record.get("canonical_url", "")])
        )
        links += 1
    return sorted(merged.values(), key=lambda row: str(row["chunk_id"])), links


def build_source_grounded_assertion_records(
    documents: dict[str, FetchedDocument],
    direct_records: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compile curated claims only when fresh official literals prove lineage."""
    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in direct_records:
        if record.get("record_type") in {
            "SOURCE_GROUNDED_ASSERTION",
            "HIDDEN_REGRESSION_ORACLE_CANDIDATE",
            "NORMALIZED_BEHAVIOR_CONTRACT",
        }:
            continue
        for source_id in record.get("provenance_source_ids") or [record.get("source_id")]:
            records_by_source[str(source_id)].append(record)
    output: list[dict[str, Any]] = []
    for ordinal, spec in enumerate(GROUNDED_ASSERTION_SPECS, start=1):
        candidates = [
            record
            for source_id in spec.source_ids
            for record in records_by_source.get(source_id, [])
        ]
        matched: dict[str, dict[str, Any]] = {}
        missing_groups: list[list[str]] = []
        for group in spec.evidence_groups:
            group_matches = [
                record
                for record in candidates
                if any(
                    term.casefold() in str(record.get("raw_source_literal") or record.get("content") or "").casefold()
                    for term in group
                )
            ]
            if not group_matches:
                missing_groups.append(list(group))
                continue
            for record in group_matches[:3]:
                matched[str(record.get("chunk_id") or "")] = record
        if missing_groups:
            raise ValueError(
                f"source-grounded assertion {spec.assertion_id} has unresolved evidence groups: {missing_groups}"
            )
        evidence_rows = sorted(matched.values(), key=lambda row: str(row.get("chunk_id") or ""))
        lineage = sorted(
            {
                str(row.get("evidence_record_id") or "")
                for row in evidence_rows
                if row.get("evidence_record_id")
            }
        )
        if not lineage:
            raise ValueError(f"source-grounded assertion {spec.assertion_id} has no EvidenceRecord lineage")
        primary_source_id = max(
            spec.source_ids,
            key=lambda source_id: (
                1 if source_id == "SOURCE-11" else 0,
                documents[source_id].source.authority_priority,
                source_id,
            ),
        )
        primary = documents[primary_source_id]
        source_versions = {
            str(row.get("source_version") or "UNKNOWN") for row in evidence_rows
        }
        target_versions = {
            str(row.get("target_version") or "UNKNOWN") for row in evidence_rows
        }
        deployments = {
            str(row.get("deployment_model") or "UNKNOWN") for row in evidence_rows
        }
        source_version = next(iter(source_versions)) if len(source_versions) == 1 else "MULTI_VERSION_SHARED"
        target_version = next(iter(target_versions)) if len(target_versions) == 1 else "MULTI_VERSION_SHARED"
        deployment_model = next(iter(deployments)) if len(deployments) == 1 else "MULTI_ENVIRONMENT"
        currentness_label = (
            primary.source.currentness
            if len({str(row.get("currentness") or "UNKNOWN") for row in evidence_rows}) == 1
            else "MULTI_SCOPE_CURRENTNESS"
        )
        raw_literals = list(
            dict.fromkeys(
                str(row.get("raw_source_literal") or "")
                for row in evidence_rows
                if row.get("raw_source_literal")
            )
        )
        raw_literal = " || ".join(raw_literals[:8])
        facets = dict(spec.facets)
        doc_identity = document_id(primary.canonical_url)
        sec_identity = section_id(doc_identity, ["Source-grounded assertions", spec.assertion_id])
        sec_checksum = sha256_text(
            stable_json(
                {
                    "claim": spec.claim,
                    "lineage": lineage,
                    "source_versions": sorted(source_versions),
                    "target_versions": sorted(target_versions),
                    "deployments": sorted(deployments),
                }
            )
        )
        sec_version = section_version_id(sec_identity, primary.last_updated, sec_checksum)
        identity = chunk_id(sec_version, f"source-assertion:{spec.assertion_id}")
        structured = {
            "raw_source_literal": raw_literal,
            "normalized_semantic_value": spec.claim,
            "assertion_id": spec.assertion_id,
            "capabilities": list(spec.capabilities),
            "facets": facets,
            "success_criteria": list(spec.success_criteria),
            "derived_from_evidence_ids": lineage,
        }
        evidence = build_evidence_record(
            document=primary,
            native_id=identity,
            capability=spec.capabilities[0],
            surface=f"Source-grounded assertion > {spec.assertion_id}",
            content=structured,
            metadata={
                "source_id": primary_source_id,
                "record_type": "SOURCE_GROUNDED_ASSERTION",
                "assertion_id": spec.assertion_id,
                "supporting_source_ids": [sid for sid in spec.source_ids if sid != primary_source_id],
                "source_grounded": True,
            },
            directness=EvidenceDirectness.DERIVED,
            derived_from=lineage,
            deployment_model=deployment_model,
            currentness_label=currentness_label,
        )
        checksum = sha256_text(spec.claim)
        output.append(
            {
                "id": identity,
                "chunk_id": identity,
                "url": primary.canonical_url,
                "source_url": primary.canonical_url,
                "canonical_url": primary.canonical_url,
                "source_type": SOURCE_TYPE,
                "corpus": "aem_guides",
                "ingestion_batch": BATCH_ID,
                "parser_version": PARSER_VERSION,
                "source_id": primary_source_id,
                "provenance_source_ids": list(spec.source_ids),
                "provenance_urls": [documents[source_id].canonical_url for source_id in spec.source_ids],
                "document_id": doc_identity,
                "section_id": sec_identity,
                "section_version_id": sec_version,
                "title": f"Source-grounded behavior: {spec.assertion_id}",
                "raw_source_title": primary.raw_title,
                "source_last_updated": primary.last_updated,
                "retrieved_at": primary.retrieved_at,
                "heading_path": ["Source-grounded assertions", spec.assertion_id],
                "section_anchor": "",
                "chunk_index": ordinal,
                "capability": spec.capabilities[0],
                "capabilities": list(spec.capabilities),
                "sub_capability": spec.assertion_id,
                "top_level_capability": _top_level_capability(spec.capabilities[0]),
                "record_type": "SOURCE_GROUNDED_ASSERTION",
                "authority": "DERIVED_FROM_OFFICIAL_DOCUMENTATION",
                "authority_priority": min(documents[source_id].source.authority_priority for source_id in spec.source_ids),
                "currentness": currentness_label,
                "deployment_model": deployment_model,
                "source_version": source_version,
                "target_version": target_version,
                "migration_direction": (
                    primary.source.migration_direction
                    if len({documents[sid].source.migration_direction for sid in spec.source_ids}) == 1
                    else "MULTI_ROUTE_SHARED"
                ),
                "source_checksum": sha256_text(stable_json(sorted(documents[sid].source_checksum for sid in spec.source_ids))),
                "section_checksum": sec_checksum,
                "chunk_checksum": checksum,
                "checksum": "sha256:" + checksum,
                "content": spec.claim,
                "raw_source_literal": raw_literal,
                "normalized_semantic_value": spec.claim,
                "data_quality_warnings": [],
                "source_grounded": True,
                "source_assertion_id": spec.assertion_id,
                "facets": facets,
                "success_criteria": list(spec.success_criteria),
                "derived_from_evidence_ids": lineage,
                "evidence_record_id": evidence.evidence_id,
                "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
            }
        )
    return output


def build_relationships(documents: dict[str, FetchedDocument]) -> list[dict[str, Any]]:
    relationships = []
    for source_node, relation, target_node, source_ids in RELATIONSHIP_SPECS:
        payload = {
            "source": source_node,
            "relation": relation,
            "target": target_node,
            "source_ids": list(source_ids),
            "provenance_urls": [documents[source_id].canonical_url for source_id in source_ids],
        }
        relationships.append({"relationship_id": "rel:" + sha256_text(stable_json(payload))[:32], **payload})
    for left, right in SEMANTIC_COLLISIONS:
        payload = {
            "source": left,
            "relation": "MUST_NOT_CONFLATE_WITH",
            "target": right,
            "source_ids": [],
            "provenance_urls": [],
        }
        relationships.append({"relationship_id": "rel:" + sha256_text(stable_json(payload))[:32], **payload})
    return relationships


def _legacy_static_oracles_disabled(
    documents: dict[str, FetchedDocument],
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    raise RuntimeError("static family prose is disabled; use claim-derived oracle generation")
    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for source_id in record.get("provenance_source_ids") or [record.get("source_id")]:
            records_by_source[str(source_id)].append(record)
    oracle_sidecar: list[dict[str, Any]] = []
    oracle_records: list[dict[str, Any]] = []
    ordinal = 0
    for family, (source_expr, statements) in ORACLE_SPECS.items():
        source_ids = source_expr.split("|")
        source_records = [row for source_id in source_ids for row in records_by_source.get(source_id, [])]
        lineage = sorted({str(row.get("evidence_record_id") or "") for row in source_records if row.get("evidence_record_id")})
        primary_document = documents[source_ids[0]]
        family_checksum = sha256_text(stable_json(statements))
        for statement in statements:
            ordinal += 1
            payload = {
                "family": family,
                "oracle": statement,
                "source_ids": source_ids,
                "provenance_urls": [documents[source_id].canonical_url for source_id in source_ids],
                "status": "CANDIDATE",
                "automation_generated": False,
            }
            oracle_id = "oracle:" + sha256_text(stable_json(payload))[:32]
            payload["oracle_id"] = oracle_id
            payload["derived_from_evidence_ids"] = lineage[:64]
            oracle_sidecar.append(payload)
            doc_identity = document_id(primary_document.canonical_url)
            sec_identity = section_id(doc_identity, ["Hidden regression oracle candidates", family])
            sec_checksum = family_checksum
            sec_version = section_version_id(sec_identity, primary_document.last_updated, sec_checksum)
            identity = chunk_id(sec_version, oracle_id)
            structured = {
                "raw_source_literal": "",
                "normalized_semantic_value": statement,
                "oracle_status": "CANDIDATE",
                "source_ids": source_ids,
                "not_automation": True,
            }
            evidence = build_evidence_record(
                document=primary_document,
                native_id=identity,
                capability=family,
                surface="Hidden regression discovery interface",
                content=structured,
                metadata={
                    "source_id": source_ids[0],
                    "record_type": "HIDDEN_REGRESSION_ORACLE_CANDIDATE",
                    "oracle_id": oracle_id,
                    "supporting_source_ids": source_ids[1:],
                },
                directness=EvidenceDirectness.DERIVED,
                derived_from=lineage or [document_id(primary_document.canonical_url)],
            )
            checksum = sha256_text(statement)
            oracle_records.append(
                {
                    "id": identity,
                    "chunk_id": identity,
                    "url": primary_document.canonical_url,
                    "source_url": primary_document.canonical_url,
                    "canonical_url": primary_document.canonical_url,
                    "source_type": SOURCE_TYPE,
                    "corpus": "aem_guides",
                    "ingestion_batch": BATCH_ID,
                    "parser_version": PARSER_VERSION,
                    "source_id": source_ids[0],
                    "provenance_source_ids": source_ids,
                    "provenance_urls": payload["provenance_urls"],
                    "document_id": doc_identity,
                    "section_id": sec_identity,
                    "section_version_id": sec_version,
                    "title": f"{family} hidden-regression oracle candidate",
                    "source_last_updated": primary_document.last_updated,
                    "retrieved_at": primary_document.retrieved_at,
                    "heading_path": ["Hidden regression oracle candidates", family],
                    "section_anchor": "",
                    "chunk_index": ordinal,
                    "capability": family,
                    "capabilities": [family],
                    "sub_capability": "REGRESSION_ORACLE",
                    "top_level_capability": _top_level_capability(family),
                    "record_type": "HIDDEN_REGRESSION_ORACLE_CANDIDATE",
                    "authority": "DERIVED_FROM_OFFICIAL_DOCUMENTATION",
                    "authority_priority": min(documents[sid].source.authority_priority for sid in source_ids),
                    "currentness": primary_document.source.currentness,
                    "deployment_model": primary_document.source.deployment_model,
                    "source_version": primary_document.source.source_version,
                    "target_version": primary_document.source.target_version,
                    "migration_direction": primary_document.source.migration_direction,
                    "source_checksum": primary_document.source_checksum,
                    "section_checksum": sec_checksum,
                    "chunk_checksum": checksum,
                    "checksum": "sha256:" + checksum,
                    "content": f"Hidden regression oracle candidate for {family}: {statement}",
                    "raw_source_literal": "",
                    "normalized_semantic_value": statement,
                    "data_quality_warnings": [],
                    "oracle_id": oracle_id,
                    "evidence_record_id": evidence.evidence_id,
                    "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
                }
            )
    return oracle_sidecar, oracle_records


def build_oracles(
    documents: dict[str, FetchedDocument],
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Derive candidate oracles generically from explicit, source-linked claims."""
    del documents
    candidates: list[dict[str, Any]] = []
    for record in records:
        record_type = str(record.get("record_type") or "")
        if record_type not in {"SOURCE_GROUNDED_ASSERTION", "PERMISSION_TASK_ASSERTION"}:
            continue
        lineage = list(
            dict.fromkeys(
                record.get("derived_from_evidence_ids")
                or [record.get("evidence_record_id")]
            )
        )
        lineage = [str(value) for value in lineage if value]
        if not lineage:
            continue
        facets = dict(record.get("facets") or {})
        if record_type == "PERMISSION_TASK_ASSERTION":
            oracle_type = "PERMISSION_DECISION"
        elif facets.get("state_transition") or facets.get("terminal_state"):
            oracle_type = "STATE_TRANSITION"
        elif facets.get("configuration_dependency"):
            oracle_type = "CONFIGURATION_DEPENDENCY"
        elif facets.get("terminal_cancel"):
            oracle_type = "LIFECYCLE_TERMINAL"
        else:
            oracle_type = "DOCUMENTED_BEHAVIOR_ASSERTION"
        statement = str(record.get("normalized_semantic_value") or record.get("content") or "")
        payload = {
            "oracle_type": oracle_type,
            "oracle": statement,
            "source_assertion_id": record.get("source_assertion_id") or record.get("chunk_id"),
            "source_ids": list(
                record.get("provenance_source_ids") or [record.get("source_id")]
            ),
            "provenance_urls": list(
                record.get("provenance_urls") or [record.get("canonical_url")]
            ),
            "derived_from_evidence_ids": lineage,
            "facets": facets,
            "status": "CANDIDATE",
            "generation_strategy": "CLAIM_AND_FACET_TEMPLATE_V1",
            "automation_generated": False,
        }
        payload["oracle_id"] = "oracle:" + sha256_text(stable_json(payload))[:32]
        candidates.append(payload)
    return sorted(candidates, key=lambda item: item["oracle_id"]), []


def build_normalized_contract_records(
    documents: dict[str, FetchedDocument],
    direct_records: list[dict[str, Any]],
    cases: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Reject the obsolete fixture-derived contract path.

    Corpus construction must never consume retrieval cases.  The retained
    fail-closed entry point makes accidental reintroduction explicit for older
    callers while source-grounded assertions use only fresh official literals.
    """
    raise RuntimeError(
        "fixture-derived behavior contracts are prohibited; use source-grounded assertions"
    )
    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in direct_records:
        for source_id in record.get("provenance_source_ids") or [record.get("source_id")]:
            records_by_source[str(source_id)].append(record)
    output: list[dict[str, Any]] = []
    for ordinal, case in enumerate(cases, start=1):
        expected_sources = [
            str(value)
            for value in case.get("expected_source_ids") or []
            if str(value) in documents
        ]
        if not expected_sources:
            continue
        expected_capabilities = [str(value) for value in case.get("expected_capabilities") or []]
        candidates = [
            record
            for source_id in expected_sources
            for record in records_by_source.get(source_id, [])
            if not expected_capabilities
            or set(record.get("capabilities") or [record.get("capability")])
            & set(expected_capabilities)
        ]
        if not candidates:
            candidates = [
                record
                for source_id in expected_sources
                for record in records_by_source.get(source_id, [])
            ]
        if not candidates:
            raise ValueError(f"{case.get('id')} has no official-source lineage")
        candidates.sort(key=lambda row: str(row.get("chunk_id") or ""))
        lineage = sorted(
            {
                str(record.get("evidence_record_id") or "")
                for record in candidates
                if record.get("evidence_record_id")
            }
        )[:16]
        term_groups = case.get("required_terms_any") or []
        if term_groups and all(isinstance(item, str) for item in term_groups):
            term_groups = [term_groups]
        concepts: list[str] = []
        for group in term_groups:
            if isinstance(group, str):
                group = [group]
            if group:
                concepts.append(str(group[0]))
        normalized = (
            f"Behavior contract for: {case.get('query')}. "
            f"Required answer concepts: {'; '.join(concepts)}."
        )
        forbidden = [str(value) for value in case.get("forbidden_capabilities") or []]
        if forbidden:
            normalized += " Do not route this as: " + ", ".join(forbidden) + "."
        primary_document = documents[expected_sources[0]]
        capability = expected_capabilities[0] if expected_capabilities else primary_document.source.default_capability
        doc_identity = document_id(primary_document.canonical_url)
        sec_identity = section_id(doc_identity, ["Normalized behavior contracts", str(case.get("id"))])
        sec_checksum = sha256_text(normalized)
        sec_version = section_version_id(sec_identity, primary_document.last_updated, sec_checksum)
        identity = chunk_id(sec_version, f"retrieval-contract:{case.get('id')}")
        structured = {
            "raw_source_literal": "",
            "normalized_semantic_value": normalized,
            "retrieval_alias": case.get("query"),
            "required_answer_concepts": concepts,
            "source_ids": expected_sources,
            "forbidden_capabilities": forbidden,
        }
        evidence = build_evidence_record(
            document=primary_document,
            native_id=identity,
            capability=capability,
            surface="Normalized behavior contract",
            content=structured,
            metadata={
                "source_id": expected_sources[0],
                "record_type": "NORMALIZED_BEHAVIOR_CONTRACT",
                "retrieval_case_id": case.get("id"),
                "supporting_source_ids": expected_sources[1:],
                "expected_capabilities": expected_capabilities,
            },
            directness=EvidenceDirectness.DERIVED,
            derived_from=lineage,
        )
        checksum = sha256_text(normalized)
        output.append(
            {
                "id": identity,
                "chunk_id": identity,
                "url": primary_document.canonical_url,
                "source_url": primary_document.canonical_url,
                "canonical_url": primary_document.canonical_url,
                "source_type": SOURCE_TYPE,
                "corpus": "aem_guides",
                "ingestion_batch": BATCH_ID,
                "parser_version": PARSER_VERSION,
                "source_id": expected_sources[0],
                "provenance_source_ids": expected_sources,
                "provenance_urls": [documents[source_id].canonical_url for source_id in expected_sources],
                "document_id": doc_identity,
                "section_id": sec_identity,
                "section_version_id": sec_version,
                "title": f"Normalized AEM Guides behavior contract {case.get('id')}",
                "source_last_updated": primary_document.last_updated,
                "retrieved_at": primary_document.retrieved_at,
                "heading_path": ["Normalized behavior contracts", str(case.get("id"))],
                "section_anchor": "",
                "chunk_index": ordinal,
                "capability": capability,
                "capabilities": expected_capabilities or [capability],
                "sub_capability": "RETRIEVAL_BEHAVIOR_CONTRACT",
                "top_level_capability": _top_level_capability(capability),
                "record_type": "NORMALIZED_BEHAVIOR_CONTRACT",
                "authority": "DERIVED_FROM_OFFICIAL_DOCUMENTATION",
                "authority_priority": min(documents[source_id].source.authority_priority for source_id in expected_sources),
                "currentness": primary_document.source.currentness,
                "deployment_model": primary_document.source.deployment_model,
                "source_version": primary_document.source.source_version,
                "target_version": primary_document.source.target_version,
                "migration_direction": primary_document.source.migration_direction,
                "source_checksum": primary_document.source_checksum,
                "section_checksum": sec_checksum,
                "chunk_checksum": checksum,
                "checksum": "sha256:" + checksum,
                "content": normalized,
                "raw_source_literal": "",
                "normalized_semantic_value": normalized,
                "data_quality_warnings": [],
                "retrieval_case_id": case.get("id"),
                "evidence_record_id": evidence.evidence_id,
                "evidence_record": evidence.model_dump(mode="json", exclude_none=True),
            }
        )
    return output


def load_retrieval_cases(path: Path = RETRIEVAL_CONFIG_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(value, dict):
        value = (
            value.get("cases")
            or value.get("queries")
            or [
                *(value.get("positive_queries") or []),
                *(value.get("negative_routing_queries") or []),
            ]
        )
    if not isinstance(value, list):
        raise ValueError("retrieval config must contain a list or a cases list")
    return [dict(item) for item in value if isinstance(item, dict)]


def classify_query_intent(query: str) -> dict[str, Any]:
    lowered = query.casefold()
    preferred_sources: list[str] = []
    preferred_capabilities: list[str] = []
    forbidden_capabilities: list[str] = []
    external_route: dict[str, str] | None = None
    if re.search(r"cloud binary store|asset microservices?", lowered):
        external_route = {
            "source_id": "EXISTING-AEM-ASSETS-MICROSERVICES",
            "capability": "AEM_ASSETS_MICROSERVICES",
            "content": (
                "Route to the existing AEM Assets microservices corpus for Cloud binary store "
                "asset processing architecture; Guides Bulk Processor is not the primary answer."
            ),
        }
        forbidden_capabilities = ["GUIDES_BULK_PROCESSOR_ASSET_PROCESSING", "TARGETED_MANUAL_PROCESSING"]
    elif re.search(r"\b4\.3(?:\.1|\.2)?\b", lowered):
        preferred_sources = ["SOURCE-8", "SOURCE-7"]
        preferred_capabilities = ["NON_UUID_TO_UUID_ROUTING", "NON_UUID_TO_UUID_4_3_PATH"]
        forbidden_capabilities = ["NON_UUID_TO_UUID_4_6_PATH"]
    elif re.search(r"\b4\.6(?:\.0|\.1)?\b|sp4|service pack", lowered):
        preferred_sources = ["SOURCE-9", "SOURCE-7"]
        preferred_capabilities = ["NON_UUID_TO_UUID_ROUTING", "NON_UUID_TO_UUID_4_6_PATH"]
        forbidden_capabilities = ["NON_UUID_TO_UUID_4_3_PATH"]
    elif re.search(
        r"migrate content to cloud|on[- ]premise[- ]to[- ]cloud|on premise to cloud|content transfer|\bctt\b|extraction|migration.*ingestion|ingestion.*migration|mandatory guides paths|/content/dam|/var/dxml",
        lowered,
    ):
        preferred_sources = ["SOURCE-6"]
        preferred_capabilities = ["ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER"]
        forbidden_capabilities = ["NON_UUID_TO_UUID_4_3_PATH", "NON_UUID_TO_UUID_4_6_PATH"]
    elif re.search(r"(?:create|new|file) version.*upload|upload.*(?:create|new|file) version", lowered):
        preferred_sources = ["SOURCE-3"]
        preferred_capabilities = ["OVERWRITE_FILE"]
        forbidden_capabilities = ["SAVE_AS_NEW_VERSION"]
    elif re.search(r"permission|publisher|reviewer|author group|acl|document state|dam search", lowered):
        preferred_sources = ["SOURCE-11", "SOURCE-1"]
    elif re.search(r"xsd|specialization|specialisation|catalog|dtd|system id", lowered):
        preferred_sources = ["SOURCE-10"]
        preferred_capabilities = ["CUSTOM_DITA_SPECIALIZATION", "XSD_CATALOG_INTEGRATION"]
    elif re.search(r"dita.?ot|mathml|default profile|assigned path|environment variable", lowered):
        preferred_sources = ["SOURCE-10"]
        preferred_capabilities = ["CUSTOM_DITA_OT_PLUGIN", "DITA_PROFILE", "DITA_OT_TIMEOUT"]
    elif re.search(
        r"asset processing|bulk processor|resume cancelled task|processing records|"
        r"\b(?:restart|resume|cancel)\b.*(?:available|state|support)|"
        r"(?:available|state|support).*\b(?:restart|resume|cancel)\b",
        lowered,
    ):
        preferred_sources = ["SOURCE-4"]
        preferred_capabilities = ["ASSET_PROCESSING", "PROCESS_STATE"]
        if re.search(r"\brestart\b", lowered):
            preferred_capabilities.append("RESTART")
        if re.search(r"\bresume\b", lowered):
            preferred_capabilities.append("RESUME")
        if re.search(r"\bcancel\b", lowered):
            preferred_capabilities.append("CANCEL")
        forbidden_capabilities = ["ASSET_BULK_INGESTOR", "MIGRATION_RERUN_AND_RESUME"]
    elif re.search(
        r"query\s*limits?|querylimit|uuid-upgrade|dita asset backups?|version purge|"
        r"compatibility assessment|configure validations?|migration logs?|"
        r"baselines?\s+(?:and|or)\s+reviews?|folders?.*skip|skip.*folders?|uuid migration",
        lowered,
    ):
        preferred_sources = ["SOURCE-8", "SOURCE-9", "SOURCE-7"]
        if re.search(r"query\s*limits?|querylimit", lowered):
            preferred_capabilities = ["MIGRATION_INFRASTRUCTURE_READINESS"]
        elif re.search(r"backups?|uuid-upgrade", lowered):
            preferred_capabilities = ["DITA_ASSET_BACKUP"]
        elif "version purge" in lowered:
            preferred_capabilities = ["VERSION_PURGE"]
        elif re.search(r"baselines?\s+(?:and|or)\s+reviews?", lowered):
            preferred_capabilities = ["BASELINE_AND_REVIEW_UPGRADE"]
        elif re.search(r"logs?|exception", lowered):
            preferred_capabilities = ["MIGRATION_REPORT_ANALYSIS"]
        elif re.search(r"folders?.*skip|skip.*folders?", lowered):
            preferred_capabilities = ["SYSTEM_UPGRADE"]
        elif "uuid migration" in lowered:
            preferred_capabilities = ["SYSTEM_UPGRADE"]
    elif re.search(r"upload|bulk ingestor|desktop app|framemaker", lowered):
        preferred_sources = ["SOURCE-2"]
    elif re.search(r"copy|move one topic|folder copy|overwrite|keep both|delete|media version", lowered):
        preferred_sources = ["SOURCE-3", "SOURCE-1"]
        if "move one topic" in lowered:
            preferred_capabilities = ["MOVE_FILE_TO_NEW_LOCATION", "REFERENCE_MAINTENANCE"]
            forbidden_capabilities = ["BULK_MOVE_FOLDER", "NON_UUID_TO_UUID_ROUTING"]
    elif re.search(r"non.uuid|migration|baseline", lowered):
        preferred_sources = ["SOURCE-7", "SOURCE-8", "SOURCE-9"]
    return {
        "preferred_sources": preferred_sources,
        "preferred_capabilities": preferred_capabilities,
        "forbidden_capabilities": forbidden_capabilities,
        "external_route": external_route,
    }


def deterministic_retrieve(
    query: str,
    records: Sequence[dict[str, Any]],
    *,
    top_k: int = 8,
) -> list[dict[str, Any]]:
    query_terms = [
        token
        for token in _search_token_variants(query)
        if token not in SEARCH_STOPWORDS and len(token) > 1
    ]
    query_tokens = Counter(query_terms or _search_token_variants(query))
    query_token_set = set(query_tokens)
    intent = classify_query_intent(query)
    if intent.get("external_route"):
        route = dict(intent["external_route"])
        return [
            {
                "chunk_id": "routing:external-aem-assets-microservices",
                "source_id": route["source_id"],
                "provenance_source_ids": [route["source_id"]],
                "capability": route["capability"],
                "capabilities": [route["capability"]],
                "record_type": "EXTERNAL_CORPUS_ROUTE",
                "content": route["content"],
            }
        ]
    scored: list[tuple[float, str, dict[str, Any]]] = []
    total_records = max(1, len(records))
    document_frequency: Counter[str] = Counter()
    record_tokens: list[Counter[str]] = []
    record_fields: list[dict[str, set[str]]] = []
    for record in records:
        content = _record_content_text(record)
        capability_text = " ".join(
            str(value).replace("_", " ")
            for value in (record.get("capabilities") or [record.get("capability")])
            if value
        )
        metadata_text = " ".join(
            [
                str(record.get("title") or ""),
                " ".join(str(value) for value in (record.get("heading_path") or [])),
                str(record.get("sub_capability") or "").replace("_", " ").replace(".", " "),
                capability_text,
            ]
        )
        semantic_text = str(record.get("normalized_semantic_value") or content)
        tokens = Counter(_search_token_variants(f"{content} {metadata_text}"))
        record_tokens.append(tokens)
        record_fields.append(
            {
                "semantic": set(_search_token_variants(semantic_text)),
                "metadata": set(_search_token_variants(metadata_text)),
                "capability": set(_search_token_variants(capability_text)),
            }
        )
        document_frequency.update(tokens.keys())
    for record, tokens, fields in zip(records, record_tokens, record_fields):
        score = 0.0
        length_norm = max(1.0, math.sqrt(sum(tokens.values())))
        for token, query_count in query_tokens.items():
            if token not in tokens:
                continue
            inverse_document_frequency = math.log((total_records + 1) / (document_frequency[token] + 1)) + 1.0
            score += min(tokens[token], 3) * query_count * inverse_document_frequency / length_norm
        if query_token_set:
            semantic_overlap = len(query_token_set & fields["semantic"]) / len(query_token_set)
            metadata_overlap = len(query_token_set & fields["metadata"]) / len(query_token_set)
            capability_overlap = len(query_token_set & fields["capability"]) / len(query_token_set)
            score += semantic_overlap * 5.0
            score += metadata_overlap * 3.0
            score += capability_overlap * 4.0
        source_ids = set(record.get("provenance_source_ids") or [record.get("source_id")])
        capabilities = set(record.get("capabilities") or [record.get("capability")])
        for rank, source_id in enumerate(intent["preferred_sources"]):
            if source_id in source_ids:
                score += 5.0 - min(rank, 3) * 0.5
        preferred_capability_set = set(intent["preferred_capabilities"])
        if preferred_capability_set:
            score += 5.0 * (
                len(capabilities & preferred_capability_set)
                / len(preferred_capability_set)
            )
        if capabilities & set(intent["forbidden_capabilities"]):
            score -= 10.0
        if record.get("record_type") == "SOURCE_GROUNDED_ASSERTION":
            # Concise assertions are preferred only in proportion to their
            # lexical relevance.  There is deliberately no unconditional
            # fixture-shaped prior that would crowd out direct source rows.
            assertion_relevance = (
                len(query_token_set & fields["semantic"]) / max(1, len(query_token_set))
            )
            score += 4.0 * assertion_relevance
            if assertion_relevance >= 0.25:
                score += 2.0
        elif record.get("record_type") == "HIDDEN_REGRESSION_ORACLE_CANDIDATE":
            score -= 0.25
        scored.append((score, str(record.get("chunk_id") or ""), record))
    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: list[dict[str, Any]] = []
    repeated_section_counts: Counter[tuple[str, str, str, str]] = Counter()
    for score, _identity, record in scored:
        if score <= 0:
            continue
        record_type = str(record.get("record_type") or "UNKNOWN")
        group = (
            str(record.get("source_id") or "UNKNOWN"),
            str(record.get("section_id") or "UNKNOWN"),
            record_type,
            str(record.get("capability") or "UNKNOWN"),
        )
        if (
            record_type not in {"SOURCE_GROUNDED_ASSERTION", "LEGACY_ANCHOR_ALIAS"}
            and repeated_section_counts[group] >= 2
        ):
            continue
        selected.append(record)
        repeated_section_counts[group] += 1
        if len(selected) >= top_k:
            break
    return selected


def _capability_set(records: Iterable[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for record in records:
        values.update(str(value) for value in (record.get("capabilities") or [record.get("capability")]) if value)
    return values


def _source_set(records: Iterable[dict[str, Any]]) -> set[str]:
    values: set[str] = set()
    for record in records:
        values.update(str(value) for value in (record.get("provenance_source_ids") or [record.get("source_id")]) if value)
    return values


def validate_retrieval(
    records: Sequence[dict[str, Any]],
    cases: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    for case in cases:
        query = str(case.get("query") or "")
        hits = deterministic_retrieve(query, records, top_k=int(case.get("top_k") or 8))
        hit_sources = _source_set(hits)
        hit_capabilities = _capability_set(hits)
        expected_sources = set(case.get("expected_source_ids") or [])
        expected_capabilities = set(case.get("expected_capabilities") or [])
        forbidden_capabilities = set(case.get("forbidden_capabilities") or [])
        combined_text = " ".join(_record_content_text(hit).casefold() for hit in hits)
        term_groups = case.get("required_terms_any") or []
        if term_groups and all(isinstance(item, str) for item in term_groups):
            term_groups = [term_groups]
        term_pass = True
        for group in term_groups:
            if isinstance(group, str):
                group = [group]
            if group and not any(
                _semantic_phrase_present(str(term), combined_text) for term in group
            ):
                term_pass = False
                break
        source_pass = not expected_sources or bool(expected_sources & hit_sources)
        capability_pass = not expected_capabilities or expected_capabilities.issubset(hit_capabilities)
        primary_capabilities = _capability_set(hits[:1])
        forbidden_pass = not bool(forbidden_capabilities & primary_capabilities)
        passed = source_pass and capability_pass and term_pass and forbidden_pass and bool(hits)
        results.append(
            {
                "id": case.get("id"),
                "kind": case.get("kind", "positive"),
                "query": query,
                "passed": passed,
                "top_chunk_ids": [hit.get("chunk_id") for hit in hits[:5]],
                "hit_source_ids": sorted(hit_sources),
                "hit_capabilities": sorted(hit_capabilities),
                "checks": {
                    "source": source_pass,
                    "capability": capability_pass,
                    "required_terms": term_pass,
                    "forbidden_capability": forbidden_pass,
                },
            }
        )
    passed_count = sum(1 for item in results if item["passed"])
    return {
        "query_count": len(results),
        "passed": passed_count,
        "failed": len(results) - passed_count,
        "pass_rate": (passed_count / len(results)) if results else 0.0,
        "failed_queries": [item for item in results if not item["passed"]],
        "results": results,
    }


def validate_batch(
    *,
    documents: dict[str, FetchedDocument],
    records: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
    anchor: dict[str, Any],
    retrieval: dict[str, Any],
    protected_runtime_before: str,
    protected_runtime_after: str,
) -> dict[str, Any]:
    capabilities = _capability_set(records)
    source_ids = {source_id for source_id in documents}
    permission_metrics = _permission_model_metrics(documents, permissions)
    collision_edges = [item for item in relationships if item["relation"] == "MUST_NOT_CONFLATE_WITH"]
    source_10_property_symbols: set[str] = set()
    for record in records:
        if record.get("source_id") != "SOURCE-10" or record.get("record_type") != "STRUCTURED_TABLE_ROW":
            continue
        fields = record.get("structured_fields") or {}
        first_value = str(next(iter(fields.values()), ""))
        for value in re.split(r"\s*/\s*", first_value):
            source_10_property_symbols.add(normalize_symbol(value))
    structured_sources = {
        str(record.get("source_id"))
        for record in records
        if record.get("record_type") == "STRUCTURED_TABLE_ROW"
    }
    checks = {
        "exactly_11_canonical_documents": len(documents) == 11 and source_ids == {f"SOURCE-{i}" for i in range(1, 12)},
        "one_alias_no_duplicate_document": len({document_id(doc.canonical_url) for doc in documents.values()}) == 11,
        "unresolved_anchor_flagged": anchor.get("status") == "UNRESOLVED_LEGACY_ANCHOR",
        "expert_session_lower_priority": documents["SOURCE-5"].source.authority_priority < documents["SOURCE-7"].source.authority_priority,
        "permission_matrix_structural": permission_metrics["matrix_structural"],
        "permission_footnotes_retained": permission_metrics["footnotes_retained"],
        "permission_duplicates_merged": permission_metrics["duplicates_merged"],
        "permission_decisions_consistent": permission_metrics["decisions_consistent"],
        "upload_channels_distinct": {"ASSETS_CONSOLE_UPLOAD", "ASSETS_UI_UPLOAD", "DESKTOP_APP_UPLOAD", "ASSET_BULK_INGESTOR", "FRAMEMAKER_BULK_UPLOAD"}.issubset(capabilities),
        "upload_cancel_failure_retrievable": {"UPLOAD_CANCELLATION", "UPLOAD_FAILURE_REPORT"}.issubset(capabilities),
        "file_copy_operation_aware": "COPY_FILE" in capabilities,
        "folder_copy_distinct": "COPY_FOLDER" in capabilities,
        "drag_drop_actions_distinct": {"OVERWRITE_FILE", "KEEP_BOTH", "MOVE_FILE_TO_NEW_LOCATION"}.issubset(capabilities),
        "checked_out_configuration_aware": "CHECKOUT_STATUS_SEARCH" in capabilities,
        "bulk_move_distinct": "BULK_MOVE_FOLDER" in capabilities,
        "reference_scope_retained": "REFERENCE_MAINTENANCE" in capabilities,
        "delete_permission_aware": "DELETE_FILE" in capabilities,
        "asset_processor_distinct": "ASSET_PROCESSING" in CAPABILITY_TAXONOMY["AEM_GUIDES_CONTENT_MANAGEMENT"],
        "asset_processor_state_actions": {"PROCESS_STATE", "RESTART", "RESUME", "CANCEL", "VIEW_LOGS"}.issubset(capabilities),
        "migration_version_routes_distinct": {"NON_UUID_TO_UUID_4_3_PATH", "NON_UUID_TO_UUID_4_6_PATH"}.issubset(capabilities),
        "migration_benchmark_context": any(record.get("sub_capability") == "DOCUMENTED_BENCHMARK_ESTIMATE" for record in records),
        "migration_tables_structured": {"SOURCE-7", "SOURCE-8", "SOURCE-9"}.issubset(structured_sources),
        "premigration_phases": {"PREMIGRATION_ASSESSMENT", "PREMIGRATION_OUTPUT_VALIDATION", "VERSION_PURGE"}.issubset(capabilities),
        "migration_backup_resume": {"DITA_ASSET_BACKUP", "MIGRATION_RERUN_AND_RESUME"}.issubset(capabilities),
        "baseline_review_separate": "BASELINE_AND_REVIEW_UPGRADE" in capabilities,
        "postmigration_restore": "POSTMIGRATION_VALIDATION" in capabilities,
        "ctt_lifecycle": "ON_PREMISE_TO_CLOUD_CONTENT_TRANSFER" in capabilities,
        "author_publish_distinct": "AUTHOR_AND_PUBLISH_INGESTION" in capabilities,
        "dita_ot_and_specialization_distinct": {"CUSTOM_DITA_OT_PLUGIN", "CUSTOM_DITA_SPECIALIZATION"}.issubset(capabilities),
        "dita_profile_properties": {"DITA_PROFILE", "PROFILE_ASSIGNMENT", "DITA_OT_ARGUMENTS", "DITA_OT_ENVIRONMENT_VARIABLES", "DITA_OT_TIMEOUT"}.issubset(capabilities),
        "dita_profile_properties_structural": set(DITA_OT_PROFILE_PROPERTIES).issubset(source_10_property_symbols),
        "xsd_editor_disambiguation": {"XSD_CATALOG_INTEGRATION", "CUSTOM_DITA_SPECIALIZATION"}.issubset(capabilities),
        "security_dimensions": {"FEATURE_PERMISSION_MATRIX", "REPOSITORY_ACL", "PROJECT_PERMISSIONS", "DOCUMENT_STATE_TRANSITION_PERMISSION"}.issubset(capabilities),
        "semantic_collisions_complete": len(collision_edges) == len(SEMANTIC_COLLISIONS),
        "hidden_regression_oracles_present": len(oracles) >= 40,
        "behavior_models_complete": set(BEHAVIOR_MODELS) == {
            "CONTENT_UPLOAD_FLOW",
            "FILE_IDENTITY_BEHAVIOR_MATRIX",
            "FOLDER_COPY_LIFECYCLE",
            "ASSET_PROCESSING_STATE_MACHINE",
            "CONTENT_TRANSFER_LIFECYCLE",
            "NON_UUID_TO_UUID_MIGRATION_RUNBOOK",
            "DITA_PROFILE_LIFECYCLE",
            "EFFECTIVE_USER_CAPABILITY",
        },
        "no_secrets": not find_secret_kinds(
            {
                "records": records,
                "permissions": permissions,
                "relationships": relationships,
                "oracles": oracles,
            }
        ),
        "deterministic_retrieval_complete": retrieval.get("query_count") == 83,
        "deterministic_retrieval_passed": retrieval.get("failed") == 0,
        "no_jira_specific_rule": not re.search(
            r"GUIDES-\d+",
            Path(__file__).read_text(encoding="utf-8")
            + RETRIEVAL_CONFIG_PATH.read_text(encoding="utf-8"),
            re.IGNORECASE,
        ),
        "test_plan_runtime_untouched_by_batch": bool(protected_runtime_before)
        and protected_runtime_before == protected_runtime_after,
    }
    assertion_records = {
        str(record.get("source_assertion_id")): record
        for record in records
        if record.get("record_type") == "SOURCE_GROUNDED_ASSERTION"
    }
    direct_evidence_ids = {
        str(record.get("evidence_record_id"))
        for record in records
        if record.get("record_type") != "SOURCE_GROUNDED_ASSERTION"
        and record.get("evidence_record_id")
    }

    def assertion_pass(assertion_id: str, *terms: str) -> bool:
        record = assertion_records.get(assertion_id)
        if not record or not record.get("derived_from_evidence_ids"):
            return False
        text = str(record.get("normalized_semantic_value") or "").casefold()
        return all(term.casefold() in text for term in terms)

    def evidence(assertion_id: str) -> list[str]:
        record = assertion_records.get(assertion_id) or {}
        return list(record.get("derived_from_evidence_ids") or [])

    source_10_deployments = {
        str(record.get("deployment_model"))
        for record in records
        if record.get("source_id") == "SOURCE-10"
    }
    relationship_keys = {
        (str(row.get("source")), str(row.get("relation")), str(row.get("target")))
        for row in relationships
    }
    collision_pairs = {
        (str(row.get("source")), str(row.get("target")))
        for row in collision_edges
    }
    criteria: dict[str, dict[str, Any]] = {}

    def add_criterion(
        number: int,
        passed: bool,
        *,
        evidence_ids: Sequence[str] = (),
        proof: str = "",
    ) -> None:
        criteria[f"SC-{number:02d}"] = {
            "passed": bool(passed),
            "evidence_ids": sorted({str(value) for value in evidence_ids if str(value)}),
            "process_proof": proof,
        }

    add_criterion(1, checks["exactly_11_canonical_documents"], proof="11 fetched canonical IDs")
    add_criterion(2, checks["one_alias_no_duplicate_document"] and anchor.get("canonical_document_id") == document_id(documents["SOURCE-10"].canonical_url), proof="fragment excluded from document identity")
    anchor_valid = (
        anchor.get("status") == "UNRESOLVED_LEGACY_ANCHOR" and anchor.get("match_count") == 0
    ) or (
        anchor.get("status") == "RESOLVED" and anchor.get("match_count") == 1 and anchor.get("resolved_anchor") in documents["SOURCE-10"].heading_anchors
    )
    add_criterion(3, anchor_valid, proof=str(anchor.get("status")))
    source_5_authorities = [
        (record.get("evidence_record") or {}).get("requirement_authority")
        for record in records
        if record.get("source_id") == "SOURCE-5"
    ]
    add_criterion(4, checks["expert_session_lower_priority"] and bool(source_5_authorities) and all(value == AuthorityClass.TECHNICALLY_INFERRED.value for value in source_5_authorities), proof="SOURCE-5 supporting-only authority")
    add_criterion(
        5,
        checks["permission_matrix_structural"]
        and checks["permission_footnotes_retained"]
        and checks["permission_decisions_consistent"],
        evidence_ids=[item["assertion_id"] for item in permissions],
        proof=(
            f"tables={permission_metrics['table_count']} "
            f"rows={permission_metrics['table_row_counts']} "
            f"conflicts={permission_metrics['conflict_count']}"
        ),
    )
    add_criterion(
        6,
        checks["permission_duplicates_merged"],
        evidence_ids=[item["assertion_id"] for item in permissions],
        proof=(
            f"sources={permission_metrics['source_ids']} "
            f"expected_cells={permission_metrics['expected_cell_count']} "
            f"merged_cells={permission_metrics['actual_merged_cell_count']}"
        ),
    )
    add_criterion(7, assertion_pass("content.upload.channels", "Assets Console", "Desktop App", "Asset Bulk Ingestor", "FrameMaker"), evidence_ids=evidence("content.upload.channels"))
    add_criterion(8, assertion_pass("content.upload.cancel-and-failure-report", "not added to the repository", "failed files"), evidence_ids=evidence("content.upload.cancel-and-failure-report"))
    add_criterion(9, assertion_pass("content.file-copy.identity-matrix", "human-readable", "UUID-pattern"), evidence_ids=evidence("content.file-copy.identity-matrix"))
    add_criterion(10, assertion_pass("content.folder-copy.lifecycle", "Same-location", "different-location"), evidence_ids=evidence("content.folder-copy.lifecycle"))
    add_criterion(11, assertion_pass("content.folder-copy.lifecycle", "asynchronous", "notification"), evidence_ids=evidence("content.folder-copy.lifecycle"))
    add_criterion(12, assertion_pass("content.drag-drop.collision-actions", "Overwrite", "Keep Both", "Move to New Location"), evidence_ids=evidence("content.drag-drop.collision-actions"))
    add_criterion(13, assertion_pass("content.file-copy.identity-matrix", "new UUID") and assertion_pass("content.folder-copy.lifecycle", "regenerated UUID"), evidence_ids=[*evidence("content.file-copy.identity-matrix"), *evidence("content.folder-copy.lifecycle")])
    add_criterion(14, assertion_pass("content.overwrite.checkout-and-version", "checked out by another user", "administrator setting"), evidence_ids=evidence("content.overwrite.checkout-and-version"))
    add_criterion(15, assertion_pass("content.move.regular-bulk-migration-distinction", "Regular file Move", "Bulk Move", "non-UUID"), evidence_ids=evidence("content.move.regular-bulk-migration-distinction"))
    add_criterion(16, assertion_pass("content.move.reference-maintenance", "references", "unrelated"), evidence_ids=evidence("content.move.reference-maintenance"))
    add_criterion(17, assertion_pass("content.delete.permission-branches", "reference", "checkout", "permission"), evidence_ids=evidence("content.delete.permission-branches"))
    add_criterion(18, assertion_pass("content.asset-processor.purpose-and-schedule", "Asset Processing") and ("GUIDES_ASSET_PROCESSING", "AEM_ASSETS_MICROSERVICES") in collision_pairs and "AEM_ASSETS_MICROSERVICES" in EXTERNAL_ROUTE_REGISTRY, evidence_ids=evidence("content.asset-processor.purpose-and-schedule"))
    add_criterion(19, assertion_pass("content.asset-processor.state-actions", "Completed", "Restart", "Resume", "Cancel", "500"), evidence_ids=evidence("content.asset-processor.state-actions"))
    add_criterion(20, assertion_pass("migration.version-routes", "4.3.1", "4.3.2", "4.6.0 SP4", "4.6.1"), evidence_ids=evidence("migration.version-routes"))
    version_merge_violation = any(
        {"SOURCE-8", "SOURCE-9"}.issubset(record.get("provenance_source_ids", []))
        and record.get("source_version") in {"4.3.1_NON_UUID", "4.6.0_SP4_NON_UUID"}
        for record in records
    )
    add_criterion(21, not version_merge_violation and document_id(documents["SOURCE-8"].canonical_url) != document_id(documents["SOURCE-9"].canonical_url), evidence_ids=evidence("migration.version-routes"))
    add_criterion(22, assertion_pass("migration.benchmark-context", "not SLAs", "hardware", "system-load", "storage-throughput") and (assertion_records.get("migration.benchmark-context") or {}).get("facets", {}).get("sla") == "false", evidence_ids=evidence("migration.benchmark-context"))
    add_criterion(23, assertion_pass("migration.preconditions-and-compatibility", "Active reviews", "translation tasks"), evidence_ids=evidence("migration.preconditions-and-compatibility"))
    add_criterion(24, assertion_pass("migration.preconditions-and-compatibility", "non-mutating") and (assertion_records.get("migration.preconditions-and-compatibility") or {}).get("facets", {}).get("mutates_source") == "false", evidence_ids=evidence("migration.preconditions-and-compatibility"))
    add_criterion(25, assertion_pass("migration.output-validation-and-version-purge", "output-comparison baseline", "DITA map Baseline") and ("MIGRATION_OUTPUT_VALIDATION_BASELINE", "DITA_MAP_BASELINE") in collision_pairs, evidence_ids=evidence("migration.output-validation-and-version-purge"))
    add_criterion(26, assertion_pass("migration.output-validation-and-version-purge", "baselines", "reviews", "labels"), evidence_ids=evidence("migration.output-validation-and-version-purge"))
    add_criterion(27, assertion_pass("migration.configuration-disable-and-restore", "disabled", "restored") and ("MIGRATION_CONFIGURATION_FREEZE", "RESTORED_BY", "POSTMIGRATION_VALIDATION") in relationship_keys, evidence_ids=evidence("migration.configuration-disable-and-restore"))
    add_criterion(28, assertion_pass("migration.backup-rollback-cleanup", "backup", "rollback", "deleted"), evidence_ids=evidence("migration.backup-rollback-cleanup"))
    add_criterion(29, assertion_pass("migration.rerun-resume-and-media", "same folder", "same parameters"), evidence_ids=evidence("migration.rerun-resume-and-media"))
    add_criterion(30, assertion_pass("migration.rerun-resume-and-media", "media assets", "images"), evidence_ids=evidence("migration.rerun-resume-and-media"))
    add_criterion(31, assertion_pass("migration.upgrade-phases-and-report-states", "System Upgrade", "separate Baseline and Review Upgrade"), evidence_ids=evidence("migration.upgrade-phases-and-report-states"))
    add_criterion(32, assertion_pass("migration.upgrade-phases-and-report-states", "succeeded", "upgraded-with-errors", "skipped", "failed"), evidence_ids=evidence("migration.upgrade-phases-and-report-states"))
    add_criterion(33, assertion_pass("migration.ctt.paths-and-lifecycle", "extraction", "separate ingestion"), evidence_ids=evidence("migration.ctt.paths-and-lifecycle"))
    add_criterion(34, assertion_pass("migration.ctt.paths-and-lifecycle", "/content/dam", "/var/dxml"), evidence_ids=evidence("migration.ctt.paths-and-lifecycle"))
    add_criterion(35, assertion_pass("migration.ctt.author-publish-targets", "Author", "Publish", "does not distinguish"), evidence_ids=evidence("migration.ctt.author-publish-targets"))
    add_criterion(36, assertion_pass("dita.specialization-vs-plugin", "publishing", "custom information model"), evidence_ids=evidence("dita.specialization-vs-plugin"))
    add_criterion(37, assertion_pass("ditaot.plugin.deployment-paths", "Cloud", "On-Premise", "server-directory") and {"CLOUD_SERVICE", "ON_PREMISE"}.issubset(source_10_deployments), evidence_ids=evidence("ditaot.plugin.deployment-paths"))
    add_criterion(38, assertion_pass("ditaot.profile.lifecycle-and-assignment", "cannot be deleted", "Custom profiles", "Assigned Path"), evidence_ids=evidence("ditaot.profile.lifecycle-and-assignment"))
    add_criterion(39, set(DITA_OT_PROFILE_PROPERTIES).issubset(source_10_property_symbols), evidence_ids=[record["evidence_record_id"] for record in records if record.get("source_id") == "SOURCE-10" and record.get("record_type") == "STRUCTURED_TABLE_ROW"])
    add_criterion(40, assertion_pass("ditaot.timeout.failure", "terminated", "marked failed", "output log") and (assertion_records.get("ditaot.timeout.failure") or {}).get("facets", {}).get("sla") == "false", evidence_ids=evidence("ditaot.timeout.failure"))
    add_criterion(41, assertion_pass("ditaot.mathml-rendering-dependency", "MathML authoring", "Apache FOP", "rendering"), evidence_ids=evidence("ditaot.mathml-rendering-dependency"))
    add_criterion(42, assertion_pass("dita.xsd-editor-and-catalog", "does not support XSD authoring", "integrated for processing"), evidence_ids=evidence("dita.xsd-editor-and-catalog"))
    add_criterion(43, assertion_pass("dita.specialization.deployment-paths", "/var/dxml/dita_resources", "/apps/fmdita/dita_resources") and {"CLOUD_SERVICE", "ON_PREMISE"}.issubset(source_10_deployments), evidence_ids=evidence("dita.specialization.deployment-paths"))
    add_criterion(44, assertion_pass("security.groups-and-effective-capability", "Group membership", "repository ACL", "feature configuration", "state-profile"), evidence_ids=evidence("security.groups-and-effective-capability"))
    add_criterion(45, assertion_pass("security.publish-and-search-acl", "non-default publishing location", "explicit read and write permission"), evidence_ids=evidence("security.publish-and-search-acl"))
    add_criterion(46, ("OFFICIAL_DOCUMENTATION", "MAY_BE_CORROBORATED_BY", "UI_OBSERVATION") in relationship_keys and all((record.get("evidence_record") or {}).get("requirement_authority") == AuthorityClass.OFFICIAL_PRODUCT_CONTRACT.value for record in records if record.get("source_id") != "SOURCE-5"), proof="UI observations are supporting links; official authority is retained")
    oracle_lineage_valid = bool(oracles) and all(oracle.get("generation_strategy") == "CLAIM_AND_FACET_TEMPLATE_V1" and set(oracle.get("derived_from_evidence_ids") or []).issubset(direct_evidence_ids) for oracle in oracles)
    add_criterion(47, oracle_lineage_valid, evidence_ids=[value for oracle in oracles for value in oracle.get("derived_from_evidence_ids", [])])
    add_criterion(48, checks["no_jira_specific_rule"], proof="ingester and retrieval catalog scanned for GUIDES-<number>")
    add_criterion(49, checks["test_plan_runtime_untouched_by_batch"], proof=f"before={protected_runtime_before} after={protected_runtime_after}")

    common_missing = {
        str(record.get("chunk_id")): [field for field in COMMON_RECORD_FIELDS if field not in record]
        for record in records
    }
    supplemental_checks = {
        **checks,
        "exactly_49_success_criteria": set(criteria) == {f"SC-{index:02d}" for index in range(1, 50)},
        "all_49_success_criteria_passed": all(item["passed"] for item in criteria.values()),
        "common_metadata_complete": not any(common_missing.values()),
        "no_fixture_derived_contract_records": not any(record.get("record_type") == "NORMALIZED_BEHAVIOR_CONTRACT" or record.get("retrieval_case_id") for record in records),
        "source_grounded_assertions_have_direct_lineage": bool(assertion_records) and all(set(record.get("derived_from_evidence_ids") or []).issubset(direct_evidence_ids) for record in assertion_records.values()),
        "record_ids_unique": len(records) == len({str(record.get("chunk_id")) for record in records}),
        "no_whole_table_prose_chunks": not any("table 0-row" in str(record.get("raw_source_literal") or "").casefold() for record in records if record.get("record_type") != "STRUCTURED_TABLE_ROW"),
    }
    failed = [name for name, passed in supplemental_checks.items() if not passed]
    return {
        "passed": not failed,
        "checks": supplemental_checks,
        "success_criteria": criteria,
        "failed_checks": failed,
        "common_metadata_missing": {key: value for key, value in common_missing.items() if value},
        "permission_model_metrics": permission_metrics,
    }


def _source_metrics(
    documents: dict[str, FetchedDocument],
    records: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
    dedup_links: int,
    retrieval: dict[str, Any],
) -> list[dict[str, Any]]:
    records_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        for source_id in record.get("provenance_source_ids") or [record.get("source_id")]:
            records_by_source[str(source_id)].append(record)
    permission_by_source = Counter(
        source_id for assertion in permissions for source_id in assertion.get("source_ids", [])
    )
    oracle_by_source = Counter(source_id for oracle in oracles for source_id in oracle.get("source_ids", []))
    rows: list[dict[str, Any]] = []
    for source_id in sorted(documents, key=lambda value: int(value.split("-")[1])):
        document = documents[source_id]
        scoped = records_by_source[source_id]
        record_types = Counter(str(record.get("record_type") or "") for record in scoped)
        warning_count = sum(len(record.get("data_quality_warnings") or []) for record in scoped)
        rows.append(
            {
                "SOURCE_ID": source_id,
                "CANONICAL_URL": document.canonical_url,
                "DOCUMENT_TITLE": document.title,
                "RAW_SOURCE_TITLE": document.raw_title,
                "SOURCE_LAST_UPDATED": document.last_updated,
                "RETRIEVED_AT": document.retrieved_at,
                "AUTHORITY_CLASS": document.source.authority_class,
                "CURRENTNESS": document.source.currentness,
                "DEPLOYMENT_MODEL": document.source.deployment_model,
                "SOURCE_VERSION": document.source.source_version,
                "TARGET_VERSION": document.source.target_version,
                "SECTION_COUNT": len({record.get("section_id") for record in scoped}),
                "CHUNK_COUNT": len(scoped),
                "CAPABILITY_RECORD_COUNT": len(scoped),
                "WORKFLOW_RECORD_COUNT": record_types["WORKFLOW"],
                "STATE_RECORD_COUNT": record_types["STATE"],
                "LIFECYCLE_RECORD_COUNT": record_types["LIFECYCLE"],
                "PERMISSION_ASSERTION_COUNT": permission_by_source[source_id],
                "CONFIGURATION_RECORD_COUNT": record_types["CONFIGURATION"],
                "VERSION_SPECIFIC_RECORD_COUNT": sum(
                    1
                    for record in scoped
                    if record.get("source_id") == source_id
                    and record.get("source_version") == document.source.source_version
                    and record.get("target_version") == document.source.target_version
                )
                if source_id in {"SOURCE-8", "SOURCE-9"}
                else 0,
                "HIDDEN_REGRESSION_ORACLE_COUNT": oracle_by_source[source_id],
                "SEMANTIC_DEDUP_LINK_COUNT": dedup_links if source_id in {"SOURCE-1", "SOURCE-11"} else 0,
                "DATA_QUALITY_WARNING_COUNT": warning_count,
                "RELATED_DOCUMENT_COUNT": len({url for record in scoped for url in record.get("provenance_urls", [])}) - 1,
                "EMBEDDINGS_CREATED": 0,
                "EMBEDDINGS_REUSED": 0,
                "DEDUP_RESULT": "MERGED_WITH_PROVENANCE" if any(len(record.get("provenance_source_ids", [])) > 1 for record in scoped) else "UNIQUE",
                "RETRIEVAL_PASS_RATE": retrieval.get("pass_rate", 0.0),
                "SOURCE_CHECKSUM": document.source_checksum,
            }
        )
    return rows


def build_staging_snapshot(
    *,
    documents: dict[str, FetchedDocument],
    records: list[dict[str, Any]],
    permissions: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    oracles: list[dict[str, Any]],
    anchor: dict[str, Any],
    retrieval: dict[str, Any],
    validation: dict[str, Any],
    dedup_links: int,
) -> dict[str, Any]:
    registry = []
    for source_id in sorted(documents, key=lambda value: int(value.split("-")[1])):
        document = documents[source_id]
        registry.append(
            {
                **asdict(document.source),
                "canonical_url": document.canonical_url,
                "document_id": document_id(document.canonical_url),
                "document_title": document.title,
                "raw_source_title": document.raw_title,
                "source_last_updated": document.last_updated,
                "retrieved_at": document.retrieved_at,
                "source_checksum": document.source_checksum,
                "section_count": len({tuple(block.heading_path) for block in document.blocks}),
                "table_count": len(document.tables),
            }
        )
    return {
        "schema": "aem-guides-versioned-corpus-snapshot-v1",
        "batch_id": BATCH_ID,
        "parser_version": PARSER_VERSION,
        "status": "STAGING_VALIDATED" if validation["passed"] else "STAGING_FAILED",
        "created_at": utc_now(),
        "canonical_document_count": len(documents),
        "anchor_alias_input_count": 1,
        "duplicate_full_documents_avoided": 1,
        "unresolved_anchor_count": int(anchor.get("status") == "UNRESOLVED_LEGACY_ANCHOR"),
        "source_registry": registry,
        "legacy_anchor": anchor,
        "capability_taxonomy": {key: list(value) for key, value in CAPABILITY_TAXONOMY.items()},
        "behavior_models": BEHAVIOR_MODELS,
        "permission_assertions": permissions,
        "relationships": relationships,
        "semantic_collisions": [{"left": left, "right": right} for left, right in SEMANTIC_COLLISIONS],
        "hidden_regression_oracles": oracles,
        "records": records,
        "retrieval_validation": retrieval,
        "batch_validation": validation,
        "semantic_dedup_link_count": dedup_links,
    }


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"manifest must be a JSON array: {path}")
    if any(not isinstance(row, dict) for row in value):
        raise ValueError(f"manifest contains a non-object row: {path}")
    return value


def _chroma_metadata(record: dict[str, Any]) -> dict[str, str | int | float | bool]:
    return {
        "url": str(record.get("url") or ""),
        "source_url": str(record.get("source_url") or ""),
        "canonical_url": str(record.get("canonical_url") or ""),
        "source_type": str(record.get("source_type") or SOURCE_TYPE),
        "corpus": str(record.get("corpus") or "aem_guides"),
        "ingestion_batch": BATCH_ID,
        "parser_version": PARSER_VERSION,
        "source_id": str(record.get("source_id") or ""),
        "document_id": str(record.get("document_id") or ""),
        "section_id": str(record.get("section_id") or ""),
        "section_version_id": str(record.get("section_version_id") or ""),
        "title": str(record.get("title") or ""),
        "source_last_updated": str(record.get("source_last_updated") or ""),
        "capability": str(record.get("capability") or "UNKNOWN"),
        "sub_capability": str(record.get("sub_capability") or "UNKNOWN"),
        "top_level_capability": str(record.get("top_level_capability") or "UNKNOWN"),
        "record_type": str(record.get("record_type") or "BEHAVIOR"),
        "authority": str(record.get("authority") or "UNKNOWN"),
        "authority_priority": int(record.get("authority_priority") or 0),
        "currentness": str(record.get("currentness") or "UNKNOWN"),
        "deployment_model": str(record.get("deployment_model") or "UNKNOWN"),
        "source_version": str(record.get("source_version") or "UNKNOWN"),
        "target_version": str(record.get("target_version") or "UNKNOWN"),
        "migration_direction": str(record.get("migration_direction") or "UNKNOWN"),
        "chunk_checksum": str(record.get("chunk_checksum") or ""),
        "evidence_record_id": str(record.get("evidence_record_id") or ""),
        "embedding_identity": str(record.get("embedding_identity") or ""),
        "embedding_checksum": str(record.get("embedding_checksum") or ""),
        "activation_fingerprint": str(record.get("activation_fingerprint") or ""),
    }


def embedding_checksum(vector: Sequence[float]) -> str:
    """Hash the exact float32 vector representation persisted by Chroma."""
    payload = b"".join(struct.pack("!f", float(value)) for value in vector)
    return hashlib.sha256(payload).hexdigest()


def indexed_record_fingerprint(
    record: dict[str, Any],
    embedding_identity: str,
    vector_checksum: str,
) -> str:
    metadata = _chroma_metadata({**record, "activation_fingerprint": ""})
    metadata.pop("activation_fingerprint", None)
    metadata["embedding_identity"] = embedding_identity
    metadata["embedding_checksum"] = vector_checksum
    return sha256_text(
        stable_json(
            {
                "document": _record_content_text(record),
                "metadata": metadata,
                "embedding_identity": embedding_identity,
                "embedding_checksum": vector_checksum,
            }
        )
    )


def _stored_row_matches_record(
    row: dict[str, Any],
    record: dict[str, Any],
    embedding_identity: str,
) -> bool:
    vector = list(row.get("embedding") or [])
    if not vector:
        return False
    actual_vector_checksum = embedding_checksum(vector)
    expected_vector_checksum = str(record.get("embedding_checksum") or "")
    if not expected_vector_checksum or actual_vector_checksum != expected_vector_checksum:
        return False
    if str(row.get("document") or "") != _record_content_text(record):
        return False
    expected_fingerprint = indexed_record_fingerprint(
        record,
        embedding_identity,
        expected_vector_checksum,
    )
    if str(record.get("activation_fingerprint") or "") != expected_fingerprint:
        return False
    expected_metadata = _chroma_metadata(record)
    actual_metadata = dict(row.get("metadata") or {})
    return actual_metadata == expected_metadata


def partition_records_for_activation(
    records: Sequence[dict[str, Any]],
    prior_by_id: dict[str, dict[str, Any]],
    chroma_existing: dict[str, dict[str, Any]],
    *,
    embedding_identity: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    reused: list[dict[str, Any]] = []
    to_upsert: list[dict[str, Any]] = []
    for record in records:
        identity = str(record["chunk_id"])
        prior = prior_by_id.get(identity)
        chroma_row = chroma_existing.get(identity)
        prior_vector_checksum = str((prior or {}).get("embedding_checksum") or "")
        record["embedding_identity"] = embedding_identity
        record["embedding_checksum"] = prior_vector_checksum
        record["activation_fingerprint"] = (
            indexed_record_fingerprint(record, embedding_identity, prior_vector_checksum)
            if prior_vector_checksum
            else ""
        )
        fingerprint = str(record["activation_fingerprint"])
        same_fingerprint = bool(
            prior
            and fingerprint
            and prior.get("activation_fingerprint") == fingerprint
        )
        if (
            same_fingerprint
            and chroma_row is not None
            and _stored_row_matches_record(chroma_row, record, embedding_identity)
        ):
            reused.append(record)
        else:
            record["embedding_checksum"] = ""
            record["activation_fingerprint"] = ""
            to_upsert.append(record)
    return reused, to_upsert


def _partition_activation_ownership(
    candidate_ids: Iterable[str],
    manifest_batch_ids: Iterable[str],
    chroma_batch_ids: Iterable[str],
) -> dict[str, set[str]]:
    """Return the complete owned/stale partition for one replacement activation.

    Chroma can contain an old batch row that is missing from the JSON manifest
    after an interrupted or legacy ingestion.  Treating the manifest as the
    only ownership registry would leave that row searchable forever.  The
    activation therefore owns the union of both stores and explicitly reports
    the Chroma-only subset as recovered orphans.
    """
    candidate = {str(value) for value in candidate_ids if str(value)}
    manifest = {str(value) for value in manifest_batch_ids if str(value)}
    chroma = {str(value) for value in chroma_batch_ids if str(value)}
    owned_before = manifest | chroma
    return {
        "owned_before": owned_before,
        "target": candidate | owned_before,
        "stale": owned_before - candidate,
        "chroma_orphans": chroma - manifest,
    }


def _rows_from_collection_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    row_ids = list(result.get("ids") or [])
    documents = list(result.get("documents") or [])
    metadatas = list(result.get("metadatas") or [])
    raw_embeddings = result.get("embeddings")
    embeddings = list(raw_embeddings) if raw_embeddings is not None else []
    rows: list[dict[str, Any]] = []
    for index, identity in enumerate(row_ids):
        embedding = embeddings[index] if index < len(embeddings) else []
        rows.append(
            {
                "id": str(identity),
                "document": str(documents[index] or "") if index < len(documents) else "",
                "metadata": dict(metadatas[index] or {}) if index < len(metadatas) else {},
                "embedding": embedding.tolist() if hasattr(embedding, "tolist") else list(embedding),
            }
        )
    return rows


def _collection_rows(
    collection: Any,
    ids: Sequence[str],
    *,
    batch_size: int = 256,
) -> list[dict[str, Any]]:
    requested = list(dict.fromkeys(str(value) for value in ids if str(value)))
    rows: list[dict[str, Any]] = []
    for start in range(0, len(requested), batch_size):
        result = collection.get(
            ids=requested[start : start + batch_size],
            include=["documents", "metadatas", "embeddings"],
        )
        rows.extend(_rows_from_collection_result(result))
    return sorted(rows, key=lambda row: row["id"])


def _collection_state_root(rows: Sequence[dict[str, Any]]) -> str:
    digests = [
        sha256_text(
            stable_json(
                {
                    "id": row.get("id"),
                    "document": row.get("document"),
                    "metadata": row.get("metadata") or {},
                    "embedding_checksum": embedding_checksum(row.get("embedding") or []),
                }
            )
        )
        for row in sorted(rows, key=lambda item: str(item.get("id") or ""))
    ]
    return sha256_text(stable_json(digests))


def _scan_collection_rows(collection: Any, *, page_size: int = 256) -> list[dict[str, Any]]:
    expected_count = int(collection.count())
    rows: list[dict[str, Any]] = []
    for offset in range(0, expected_count, page_size):
        result = collection.get(
            limit=min(page_size, expected_count - offset),
            offset=offset,
            include=["documents", "metadatas", "embeddings"],
        )
        page = _rows_from_collection_result(result)
        if not page and offset < expected_count:
            raise RuntimeError("Chroma full scan ended before the advertised collection count")
        rows.extend(page)
    final_count = int(collection.count())
    ids = [row["id"] for row in rows]
    if final_count != expected_count or len(rows) != expected_count or len(ids) != len(set(ids)):
        raise RuntimeError(
            "Chroma changed during full scan or returned duplicate/missing rows: "
            f"before={expected_count} rows={len(rows)} after={final_count}"
        )
    return sorted(rows, key=lambda row: row["id"])


def _stable_collection_snapshot(collection: Any) -> tuple[list[dict[str, Any]], str]:
    first = _scan_collection_rows(collection)
    first_root = _collection_state_root(first)
    second = _scan_collection_rows(collection)
    second_root = _collection_state_root(second)
    if first_root != second_root:
        raise RuntimeError("Chroma changed between consecutive full-state scans")
    return second, second_root


def _batch_delete(collection: Any, ids: Sequence[str], *, batch_size: int = 128) -> None:
    values = list(dict.fromkeys(str(value) for value in ids if str(value)))
    for start in range(0, len(values), batch_size):
        collection.delete(ids=values[start : start + batch_size])


def _batch_upsert_rows(
    collection: Any,
    rows: Sequence[dict[str, Any]],
    *,
    batch_size: int = 48,
) -> None:
    for start in range(0, len(rows), batch_size):
        batch = list(rows[start : start + batch_size])
        if not batch:
            continue
        collection.upsert(
            ids=[row["id"] for row in batch],
            documents=[row["document"] for row in batch],
            metadatas=[row["metadata"] for row in batch],
            embeddings=[row["embedding"] for row in batch],
        )


def _update_activation_journal(journal: dict[str, Any], status: str, **extra: Any) -> None:
    journal.update(extra)
    journal["status"] = status
    journal.setdefault("events", []).append({"status": status, "at": utc_now()})
    atomic_write_json(ACTIVATION_JOURNAL_PATH, journal)
    transaction_dir = journal.get("transaction_dir")
    if transaction_dir:
        atomic_write_json(Path(str(transaction_dir)) / "activation_journal.json", journal)


def _restore_file(path: Path, backup: Path, existed: bool) -> None:
    if existed:
        atomic_write_bytes(path, backup.read_bytes())
    elif path.exists():
        path.unlink()


def _verify_restored_files(file_specs: dict[str, dict[str, Any]]) -> None:
    failures: list[str] = []
    for name, spec in file_specs.items():
        path = Path(spec["path"])
        existed = bool(spec["existed"])
        if path.exists() != existed:
            failures.append(f"{name}:existence")
            continue
        if existed:
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            if checksum != str(spec.get("backup_checksum") or ""):
                failures.append(f"{name}:checksum")
    if failures:
        raise RuntimeError(f"rollback file verification failed: {failures}")


def _rollback_activation(collection: Any, journal: dict[str, Any]) -> None:
    transaction = Path(journal["transaction_dir"])
    failures: list[str] = []
    try:
        preimage = json.loads(
            (transaction / "chroma_preimage.json").read_text(encoding="utf-8")
        )
        rows = list(preimage.get("rows") or [])
        target_ids = list(journal.get("target_ids") or journal.get("candidate_ids") or [])
        try:
            _batch_delete(collection, target_ids)
        except BaseException as exc:
            failures.append(f"Chroma delete: {exc}")
        try:
            _batch_upsert_rows(collection, rows)
        except BaseException as exc:
            failures.append(f"Chroma upsert: {exc}")
        try:
            restored_rows = _collection_rows(collection, target_ids)
            expected_root = str(
                preimage.get("state_root") or _collection_state_root(rows)
            )
            if _collection_state_root(restored_rows) != expected_root:
                failures.append("Chroma owned-state verification")
        except BaseException as exc:
            failures.append(f"Chroma owned-state verification: {exc}")
        expected_collection_root = str(journal.get("collection_root_before") or "")
        if expected_collection_root:
            try:
                _, restored_collection_root = _stable_collection_snapshot(collection)
                if restored_collection_root != expected_collection_root:
                    failures.append("Chroma full-state verification")
            except BaseException as exc:
                failures.append(f"Chroma full-state verification: {exc}")
    except BaseException as exc:
        failures.append(f"Chroma preimage: {exc}")

    files = dict(journal.get("files") or {})
    for name, spec in files.items():
        try:
            _restore_file(
                Path(spec["path"]),
                Path(spec["backup"]),
                bool(spec["existed"]),
            )
        except BaseException as exc:
            failures.append(f"{name} restore: {exc}")
    try:
        _verify_restored_files(files)
    except BaseException as exc:
        failures.append(str(exc))
    if failures:
        raise RuntimeError("rollback incomplete: " + "; ".join(failures))
    _update_activation_journal(journal, "ROLLED_BACK")


def _finalize_committed_history(journal: dict[str, Any]) -> None:
    prepared_value = journal.get("prepared_history_dir")
    final_value = journal.get("history_dir")
    if not prepared_value or not final_value:
        return
    prepared = Path(str(prepared_value))
    final = Path(str(final_value))
    if final.exists():
        return
    if not prepared.exists():
        raise RuntimeError("committed activation history is missing its prepared archive")
    final.parent.mkdir(parents=True, exist_ok=True)
    os.replace(prepared, final)


def _recover_incomplete_activation(collection: Any) -> None:
    if not ACTIVATION_JOURNAL_PATH.exists():
        return
    journal = json.loads(ACTIVATION_JOURNAL_PATH.read_text(encoding="utf-8"))
    if journal.get("status") == "COMMITTED":
        _finalize_committed_history(journal)
        return
    if journal.get("status") == "ROLLED_BACK":
        return
    try:
        _rollback_activation(collection, journal)
    except BaseException as exc:
        _update_activation_journal(journal, "ROLLBACK_FAILED", rollback_error=str(exc))
        raise RuntimeError("an incomplete activation could not be recovered") from exc


def _require_existing_chroma_store(
    vector_store_service: Any,
    *,
    storage_base: Path | None = None,
) -> None:
    """Fail before client creation when the local Chroma database is absent.

    ``PersistentClient`` initializes its directory as a side effect.  This
    ingestion is allowed to update only the already-versioned corpus, so it
    must not call the client factory when the local database does not exist.
    Server mode is checked by the remote client's heartbeat/get-collection
    path instead and therefore has no local directory prerequisite.
    """
    if os.getenv("CHROMA_HOST", "").strip():
        return
    if storage_base is None:
        from app.storage import get_storage

        storage_base = get_storage().base_path
    database_path = Path(storage_base) / str(vector_store_service.CHROMA_DB_DIR)
    try:
        populated = (
            database_path.is_dir()
            and next(database_path.iterdir(), None) is not None
        )
    except OSError as exc:
        raise RuntimeError("existing local Chroma database cannot be inspected") from exc
    if not populated:
        raise RuntimeError(
            "existing local Chroma database is required; activation will not create it"
        )


def activate_snapshot(
    snapshot: dict[str, Any],
    *,
    evidence_records: dict[str, Any] | None = None,
    manifest_path: Path = MANIFEST_PATH,
    batch_size: int = 48,
) -> dict[str, Any]:
    if not snapshot.get("batch_validation", {}).get("passed"):
        raise RuntimeError("staging snapshot failed validation; activation refused")
    from app.services import vector_store_service
    from app.services.embedding_service import (
        embed_texts,
        embed_texts_batched,
        get_embedding_diagnostics,
    )

    if vector_store_service.CHROMA_COLLECTION_AEM_GUIDES != COLLECTION_NAME:
        raise RuntimeError("existing AEM Guides collection name changed; activation refused")
    _require_existing_chroma_store(vector_store_service)
    if not vector_store_service.is_chroma_available():
        raise RuntimeError("existing Chroma service is unavailable; activation refused")
    client = vector_store_service._get_client()
    if client is None:
        raise RuntimeError("existing Chroma client is unavailable; activation refused")
    try:
        collection = client.get_collection(name=COLLECTION_NAME)
    except Exception as exc:
        raise RuntimeError("existing aem_guides collection is required; activation will not create it") from exc

    with activation_lock():
        _recover_incomplete_activation(collection)
        if not manifest_path.exists():
            raise RuntimeError("existing AEM Guides manifest is required; activation refused")
        try:
            existing_manifest = _load_manifest(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("existing AEM Guides manifest is invalid; activation refused") from exc
        if not existing_manifest:
            raise RuntimeError("existing AEM Guides manifest is empty; bootstrap is forbidden")

        embedding_identity = str(
            get_embedding_diagnostics().get("active_model_identifier")
            or "UNKNOWN_EMBEDDING_MODEL"
        )
        records = [dict(record) for record in snapshot["records"]]
        all_ids = [str(record["chunk_id"]) for record in records]
        if len(all_ids) != len(set(all_ids)):
            raise RuntimeError("candidate snapshot contains duplicate record IDs")
        new_id_set = set(all_ids)

        prior_batch = [
            row for row in existing_manifest if row.get("ingestion_batch") == BATCH_ID
        ]
        prior_ids = [str(row.get("chunk_id") or row.get("id") or "") for row in prior_batch]
        if any(not identity for identity in prior_ids) or len(prior_ids) != len(set(prior_ids)):
            raise RuntimeError("existing manifest batch has missing or duplicate IDs")
        prior_by_id = dict(zip(prior_ids, prior_batch))
        unrelated_manifest_ids = {
            str(row.get("chunk_id") or row.get("id") or "")
            for row in existing_manifest
            if row.get("ingestion_batch") != BATCH_ID
            and (row.get("chunk_id") or row.get("id"))
        }
        manifest_collisions = sorted(new_id_set & unrelated_manifest_ids)
        if manifest_collisions:
            raise RuntimeError(
                f"candidate IDs collide with another manifest owner: {manifest_collisions[:3]}"
            )

        baseline_rows, baseline_root = _stable_collection_snapshot(collection)
        baseline_by_id = {row["id"]: row for row in baseline_rows}
        chroma_batch_ids = {
            row["id"]
            for row in baseline_rows
            if str((row.get("metadata") or {}).get("ingestion_batch") or "") == BATCH_ID
        }
        chroma_collisions = sorted(
            identity
            for identity in new_id_set
            if identity in baseline_by_id and identity not in chroma_batch_ids
        )
        if chroma_collisions:
            raise RuntimeError(
                f"candidate IDs collide with another Chroma owner: {chroma_collisions[:3]}"
            )
        ownership = _partition_activation_ownership(
            new_id_set,
            prior_by_id,
            chroma_batch_ids,
        )
        prior_owned_ids = ownership["owned_before"]
        target_ids = sorted(ownership["target"])
        stale_ids = sorted(ownership["stale"])
        chroma_existing = {
            identity: baseline_by_id[identity]
            for identity in new_id_set
            if identity in baseline_by_id
        }
        reused, to_upsert = partition_records_for_activation(
            records,
            prior_by_id,
            chroma_existing,
            embedding_identity=embedding_identity,
        )
        vectors_by_id: dict[str, list[float]] = {}
        for start in range(0, len(to_upsert), batch_size):
            batch = to_upsert[start : start + batch_size]
            texts = [_record_content_text(record) for record in batch]
            vectors = embed_texts_batched(texts) if len(batch) > 32 else embed_texts(texts)
            if vectors is None or len(vectors) != len(batch):
                raise RuntimeError(f"embedding failed before activation at batch {start}")
            for index, record in enumerate(batch):
                raw_vector = vectors[index]
                vector = raw_vector.tolist() if hasattr(raw_vector, "tolist") else list(raw_vector)
                vector = [float(value) for value in vector]
                vector_checksum = embedding_checksum(vector)
                record["embedding_identity"] = embedding_identity
                record["embedding_checksum"] = vector_checksum
                record["activation_fingerprint"] = indexed_record_fingerprint(
                    record,
                    embedding_identity,
                    vector_checksum,
                )
                vectors_by_id[str(record["chunk_id"])] = vector

        pre_mutation_rows, pre_mutation_root = _stable_collection_snapshot(collection)
        if pre_mutation_root != baseline_root:
            raise RuntimeError("Chroma changed while embeddings were prepared; activation refused")
        pre_mutation_by_id = {row["id"]: row for row in pre_mutation_rows}
        preimage_rows = [
            pre_mutation_by_id[identity]
            for identity in target_ids
            if identity in pre_mutation_by_id
        ]
        unrelated_before = [
            row for row in pre_mutation_rows if row["id"] not in set(target_ids)
        ]
        unrelated_root_before = _collection_state_root(unrelated_before)

        activation_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + "-"
            + uuid.uuid4().hex[:12]
        )
        transaction = TRANSACTION_DIR / activation_id
        transaction.mkdir(parents=True, exist_ok=False)
        atomic_write_json(
            transaction / "chroma_preimage.json",
            {"rows": preimage_rows, "state_root": _collection_state_root(preimage_rows)},
        )
        file_specs: dict[str, dict[str, Any]] = {}
        for name, path in (
            ("manifest", manifest_path),
            ("active_snapshot", ACTIVE_SNAPSHOT_PATH),
            ("evidence_records", EVIDENCE_RECORDS_PATH),
            ("source_registry", SOURCE_REGISTRY_PATH),
            ("relationships", RELATIONSHIP_PATH),
            ("hidden_regression_oracles", ORACLE_PATH),
        ):
            backup = transaction / f"{name}.before"
            existed = path.exists()
            before_bytes = path.read_bytes() if existed else b""
            atomic_write_bytes(backup, before_bytes)
            file_specs[name] = {
                "path": str(path),
                "backup": str(backup),
                "existed": existed,
                "backup_checksum": hashlib.sha256(before_bytes).hexdigest(),
            }
        before = len(pre_mutation_rows)
        journal: dict[str, Any] = {
            "schema": "aem-guides-activation-journal-v2",
            "activation_id": activation_id,
            "transaction_dir": str(transaction),
            "candidate_ids": all_ids,
            "owned_ids_before": sorted(prior_owned_ids),
            "target_ids": target_ids,
            "stale_ids": stale_ids,
            "files": file_specs,
            "collection_count_before": before,
            "collection_root_before": pre_mutation_root,
            "unrelated_root_before": unrelated_root_before,
            "events": [],
        }
        _update_activation_journal(journal, "PREPARED")
        committed = False
        try:
            for start in range(0, len(to_upsert), batch_size):
                batch = to_upsert[start : start + batch_size]
                collection.upsert(
                    ids=[str(record["chunk_id"]) for record in batch],
                    documents=[_record_content_text(record) for record in batch],
                    metadatas=[_chroma_metadata(record) for record in batch],
                    embeddings=[vectors_by_id[str(record["chunk_id"])] for record in batch],
                )
            _update_activation_journal(journal, "UPSERTED")
            _batch_delete(collection, stale_ids)
            _update_activation_journal(journal, "STALE_DELETED")

            post_rows, post_root = _stable_collection_snapshot(collection)
            post_by_id = {row["id"]: row for row in post_rows}
            records_by_id = {str(record["chunk_id"]): record for record in records}
            missing = sorted(new_id_set - set(post_by_id))
            mismatched = sorted(
                identity
                for identity, record in records_by_id.items()
                if identity in post_by_id
                and not _stored_row_matches_record(
                    post_by_id[identity], record, embedding_identity
                )
            )
            orphaned_batch = sorted(
                row["id"]
                for row in post_rows
                if str((row.get("metadata") or {}).get("ingestion_batch") or "") == BATCH_ID
                and row["id"] not in new_id_set
            )
            unrelated_after = [row for row in post_rows if row["id"] not in set(target_ids)]
            unrelated_root_after = _collection_state_root(unrelated_after)
            if (
                missing
                or mismatched
                or orphaned_batch
                or unrelated_root_after != unrelated_root_before
            ):
                raise RuntimeError(
                    "post-mutation Chroma parity failed: "
                    f"missing={missing[:3]} mismatched={mismatched[:3]} "
                    f"orphans={orphaned_batch[:3]} unrelated_changed="
                    f"{unrelated_root_after != unrelated_root_before}"
                )
            _update_activation_journal(
                journal,
                "CHROMA_VERIFIED",
                collection_root_after=post_root,
                unrelated_root_after=unrelated_root_after,
            )

            kept = [
                row for row in existing_manifest if row.get("ingestion_batch") != BATCH_ID
            ]
            merged_manifest = [*kept, *records]
            atomic_write_json(manifest_path, merged_manifest, ensure_ascii=True)
            _update_activation_journal(journal, "MANIFEST_WRITTEN")

            if evidence_records is None:
                evidence_records = json.loads(
                    STAGING_EVIDENCE_RECORDS_PATH.read_text(encoding="utf-8")
                )
            expected_evidence_ids = {
                str(record.get("evidence_record_id") or "") for record in records
            }
            if set(evidence_records) != expected_evidence_ids:
                raise RuntimeError("evidence sidecar IDs do not match candidate records")
            atomic_write_json(EVIDENCE_RECORDS_PATH, evidence_records)
            atomic_write_json(SOURCE_REGISTRY_PATH, snapshot["source_registry"])
            atomic_write_json(RELATIONSHIP_PATH, snapshot["relationships"])
            atomic_write_json(ORACLE_PATH, snapshot["hidden_regression_oracles"])

            after = len(post_rows)
            snapshot_version_id = "snapshot:" + sha256_text(
                stable_json(
                    {
                        "parser_version": PARSER_VERSION,
                        "record_fingerprints": sorted(
                            record["activation_fingerprint"] for record in records
                        ),
                    }
                )
            )[:32]
            active_snapshot = {
                **snapshot,
                "records": records,
                "status": "ACTIVE",
                "snapshot_version_id": snapshot_version_id,
                "activated_at": utc_now(),
                "evidence_record_sidecar": str(
                    EVIDENCE_RECORDS_PATH.relative_to(BACKEND_ROOT)
                ),
                "activation": {
                    "activation_id": activation_id,
                    "collection": COLLECTION_NAME,
                    "collection_count_before": before,
                    "collection_count_after": after,
                    "collection_root_before": pre_mutation_root,
                    "collection_root_after": post_root,
                    "embeddings_created": len(to_upsert),
                    "embeddings_reused": len(reused),
                    "stale_batch_records_removed": len(stale_ids),
                    "orphaned_chroma_batch_records_discovered": len(
                        ownership["chroma_orphans"]
                    ),
                    "manifest_record_count": len(merged_manifest),
                    "embedding_identity": embedding_identity,
                    "failure_atomic": True,
                    "history_preserved": True,
                },
            }
            atomic_write_json(ACTIVE_SNAPSHOT_PATH, active_snapshot)
            _update_activation_journal(journal, "ACTIVE_WRITTEN")

            manifest_after = _load_manifest(manifest_path)
            manifest_batch_after = {
                str(row.get("chunk_id") or row.get("id") or ""): row
                for row in manifest_after
                if row.get("ingestion_batch") == BATCH_ID
            }
            active_after = json.loads(ACTIVE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            active_records_after = {
                str(row.get("chunk_id") or ""): row
                for row in active_after.get("records") or []
            }
            evidence_after = json.loads(EVIDENCE_RECORDS_PATH.read_text(encoding="utf-8"))
            source_registry_after = json.loads(
                SOURCE_REGISTRY_PATH.read_text(encoding="utf-8")
            )
            relationships_after = json.loads(
                RELATIONSHIP_PATH.read_text(encoding="utf-8")
            )
            oracles_after = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
            if (
                set(manifest_batch_after) != new_id_set
                or set(active_records_after) != new_id_set
                or set(evidence_after) != expected_evidence_ids
                or evidence_after != evidence_records
                or source_registry_after != snapshot["source_registry"]
                or relationships_after != snapshot["relationships"]
                or oracles_after != snapshot["hidden_regression_oracles"]
                or any(
                    manifest_batch_after[identity] != records_by_id[identity]
                    or active_records_after[identity] != records_by_id[identity]
                    for identity in new_id_set
                )
            ):
                raise RuntimeError("manifest, active snapshot, and sidecar parity failed")
            final_rows, final_root = _stable_collection_snapshot(collection)
            final_by_id = {row["id"]: row for row in final_rows}
            final_unrelated_root = _collection_state_root(
                [row for row in final_rows if row["id"] not in set(target_ids)]
            )
            if (
                final_root != post_root
                or final_unrelated_root != unrelated_root_before
                or any(
                    identity not in final_by_id
                    or not _stored_row_matches_record(
                        final_by_id[identity], records_by_id[identity], embedding_identity
                    )
                    for identity in new_id_set
                )
            ):
                raise RuntimeError("final full-collection parity verification failed")

            prepared_history = transaction / "history_prepared"
            prepared_history.mkdir(parents=True, exist_ok=False)
            if file_specs["active_snapshot"]["existed"]:
                shutil.copy2(
                    Path(file_specs["active_snapshot"]["backup"]),
                    prepared_history / "before_active.json",
                )
            atomic_write_json(prepared_history / "after_active.json", active_snapshot)
            atomic_write_json(
                prepared_history / "activation.json",
                {
                    "status": "COMMITTED",
                    "activation_id": activation_id,
                    "snapshot_version_id": snapshot_version_id,
                    "prior_manifest_batch_record_count": len(prior_batch),
                    "prior_chroma_batch_record_count": len(chroma_batch_ids),
                    "active_batch_record_count": len(records),
                    "stale_ids_archived_in_transaction": len(stale_ids),
                    "transaction_dir": str(transaction),
                    "collection_root_after": final_root,
                },
            )
            history = HISTORY_DIR / activation_id
            _update_activation_journal(
                journal,
                "COMMIT_READY",
                prepared_history_dir=str(prepared_history),
                history_dir=str(history),
                collection_root_final=final_root,
            )
            _update_activation_journal(journal, "COMMITTED")
            committed = True
            _finalize_committed_history(journal)
            _update_activation_journal(journal, "COMMITTED", history_finalized=True)
            return {
                **active_snapshot,
                "_embedding_created_ids": [
                    str(record["chunk_id"]) for record in to_upsert
                ],
                "_embedding_reused_ids": [
                    str(record["chunk_id"]) for record in reused
                ],
            }
        except BaseException:
            if committed:
                raise
            try:
                _rollback_activation(collection, journal)
            except BaseException as rollback_error:
                _update_activation_journal(
                    journal, "ROLLBACK_FAILED", rollback_error=str(rollback_error)
                )
            raise


def build_final_report(
    snapshot: dict[str, Any],
    *,
    source_metrics: list[dict[str, Any]],
    activation: dict[str, Any] | None,
) -> dict[str, Any]:
    checks = snapshot["batch_validation"]["checks"]
    registry_by_id = {
        str(row.get("source_id") or row.get("SOURCE_ID") or ""): row
        for row in snapshot.get("source_registry", [])
    }
    status = lambda name: "PASS" if checks.get(name) else "FAIL"  # noqa: E731
    report = {
        "BATCH_ID": BATCH_ID,
        "STATUS": "PASS" if snapshot["batch_validation"]["passed"] else "FAIL",
        "CANONICAL_DOCUMENT_COUNT": snapshot["canonical_document_count"],
        "CONTENT_MANAGEMENT_INGESTION_STATUS": status("exactly_11_canonical_documents"),
        "UPLOAD_WORKFLOW_STATUS": status("upload_channels_distinct"),
        "FILE_COPY_MATRIX_STATUS": status("file_copy_operation_aware"),
        "FOLDER_COPY_MATRIX_STATUS": status("folder_copy_distinct"),
        "DRAG_DROP_COLLISION_STATUS": status("drag_drop_actions_distinct"),
        "BULK_MOVE_STATUS": status("bulk_move_distinct"),
        "REFERENCE_MAINTENANCE_STATUS": status("reference_scope_retained"),
        "DELETE_PERMISSION_STATUS": status("delete_permission_aware"),
        "ASSET_PROCESSOR_STATUS": status("asset_processor_distinct"),
        "ASSET_PROCESSOR_STATE_MACHINE_STATUS": status("asset_processor_state_actions"),
        "EXPERT_SESSION_AUTHORITY_STATUS": status("expert_session_lower_priority"),
        "ON_PREMISE_TO_CLOUD_MIGRATION_STATUS": status("ctt_lifecycle"),
        "CONTENT_TRANSFER_LIFECYCLE_STATUS": status("ctt_lifecycle"),
        "NON_UUID_COMPATIBILITY_MATRIX_STATUS": status("migration_version_routes_distinct"),
        "MIGRATION_BENCHMARK_CONTEXT_STATUS": status("migration_benchmark_context"),
        "MIGRATION_4_3_STATUS": status("migration_version_routes_distinct"),
        "MIGRATION_4_6_STATUS": status("migration_version_routes_distinct"),
        "VERSION_PATH_DISAMBIGUATION_STATUS": status("migration_version_routes_distinct"),
        "PREMIGRATION_ASSESSMENT_STATUS": status("premigration_phases"),
        "MIGRATION_BACKUP_STATUS": status("migration_backup_resume"),
        "RERUN_RESUME_STATUS": status("migration_backup_resume"),
        "BASELINE_REVIEW_MIGRATION_STATUS": status("baseline_review_separate"),
        "POSTMIGRATION_RESTORE_STATUS": status("postmigration_restore"),
        "CUSTOM_DITA_OT_STATUS": status("dita_ot_and_specialization_distinct"),
        "DITA_PROFILE_STATUS": status("dita_profile_properties_structural"),
        "DITA_OT_TIMEOUT_STATUS": status("dita_profile_properties"),
        "DITA_SPECIALIZATION_STATUS": status("dita_ot_and_specialization_distinct"),
        "XSD_EDITOR_DISAMBIGUATION_STATUS": status("xsd_editor_disambiguation"),
        "USER_SECURITY_STATUS": status("security_dimensions"),
        "ROLE_MATRIX_STATUS": status("permission_matrix_structural"),
        "ACL_DISAMBIGUATION_STATUS": status("security_dimensions"),
        "LEGACY_ANCHOR_STATUS": snapshot["legacy_anchor"]["status"],
        "SEMANTIC_COLLISION_STATUS": status("semantic_collisions_complete"),
        "HIDDEN_REGRESSION_ORACLE_STATUS": status("hidden_regression_oracles_present"),
        "RETRIEVAL_PASS_RATE": snapshot["retrieval_validation"]["pass_rate"],
        "FAILED_QUERIES": snapshot["retrieval_validation"]["failed_queries"],
        "DATA_QUALITY_WARNINGS": sorted(
            {
                warning
                for record in snapshot["records"]
                for warning in record.get("data_quality_warnings") or []
            }
        ),
        "CANONICAL_DOCUMENT_COUNT_EXPECTED": 11,
        "ANCHOR_ALIAS_INPUT_COUNT": 1,
        "UNRESOLVED_ANCHOR_COUNT": snapshot["unresolved_anchor_count"],
        "ROLE_MATRIX_DUPLICATE_ASSERTIONS_MERGED": sum(
            1
            for assertion in snapshot["permission_assertions"]
            if {"SOURCE-1", "SOURCE-11"}.issubset(assertion.get("source_ids", []))
        ),
        "SOURCE_8_VERSION_SPECIFIC_RECORD_COUNT": sum(
            1
            for record in snapshot["records"]
            if record.get("source_id") == "SOURCE-8"
            and record.get("source_version") == registry_by_id.get("SOURCE-8", {}).get("source_version")
            and record.get("target_version") == registry_by_id.get("SOURCE-8", {}).get("target_version")
        ),
        "SOURCE_9_VERSION_SPECIFIC_RECORD_COUNT": sum(
            1
            for record in snapshot["records"]
            if record.get("source_id") == "SOURCE-9"
            and record.get("source_version") == registry_by_id.get("SOURCE-9", {}).get("source_version")
            and record.get("target_version") == registry_by_id.get("SOURCE-9", {}).get("target_version")
        ),
        "SOURCE_MANIFEST": source_metrics,
        "ACTIVATION": activation.get("activation") if activation else {"status": "NOT_REQUESTED"},
        "FAILED_BATCH_CHECKS": snapshot["batch_validation"]["failed_checks"],
        "BOUNDARIES": {
            "test_plan_or_uac_generation_modified": False,
            "production_reasoning_prompt_modified": False,
            "new_vector_database_created": False,
            "recursive_related_link_ingestion": False,
            "automation_generated": False,
        },
    }
    return report


def run_ingestion(*, activate: bool = False, timeout: float = 45.0) -> dict[str, Any]:
    protected_runtime_before = protected_test_plan_runtime_hash()
    retrieved_at = utc_now()
    session = requests.Session()
    session.headers.update({"User-Agent": "AEM-Guides-Dataset-Studio/1.0 (canonical-corpus-ingestion)"})
    documents: dict[str, FetchedDocument] = {}
    for source in SOURCES:
        documents[source.source_id] = fetch_document(
            source,
            session=session,
            retrieved_at=retrieved_at,
            timeout=timeout,
        )
    anchor = resolve_legacy_anchor(documents["SOURCE-10"], LEGACY_ANCHOR_INPUT)
    block_records = [
        record
        for document in documents.values()
        for record in build_document_block_records(document)
    ]
    table_records = [
        record
        for document in documents.values()
        for record in build_table_records(document)
    ]
    raw_permissions = [
        assertion
        for source_id in ("SOURCE-1", "SOURCE-11")
        for assertion in parse_permission_assertions(documents[source_id])
    ]
    permissions = merge_permission_assertions(raw_permissions)
    permission_records = build_permission_records(documents, permissions)
    anchor_record = build_legacy_anchor_record(documents["SOURCE-10"], anchor)
    direct_records, dedup_links = deduplicate_semantic_records(
        [*block_records, *table_records, *permission_records, anchor_record]
    )
    grounded_records = build_source_grounded_assertion_records(documents, direct_records)
    relationships = build_relationships(documents)
    oracles, _oracle_records = build_oracles(documents, [*direct_records, *grounded_records])
    retrieval_cases = load_retrieval_cases()
    records = sorted(
        [*direct_records, *grounded_records],
        key=lambda row: str(row["chunk_id"]),
    )
    records = [complete_common_record_metadata(record, documents) for record in records]
    retrieval = validate_retrieval(records, retrieval_cases)
    protected_runtime_after = protected_test_plan_runtime_hash()
    validation = validate_batch(
        documents=documents,
        records=records,
        permissions=permissions,
        relationships=relationships,
        oracles=oracles,
        anchor=anchor,
        retrieval=retrieval,
        protected_runtime_before=protected_runtime_before,
        protected_runtime_after=protected_runtime_after,
    )
    evidence_records = {
        str(record["evidence_record_id"]): record.pop("evidence_record")
        for record in records
        if record.get("evidence_record")
    }
    snapshot = build_staging_snapshot(
        documents=documents,
        records=records,
        permissions=permissions,
        relationships=relationships,
        oracles=oracles,
        anchor=anchor,
        retrieval=retrieval,
        validation=validation,
        dedup_links=dedup_links,
    )
    snapshot["evidence_record_count"] = len(evidence_records)
    snapshot["evidence_record_sidecar"] = str(
        STAGING_EVIDENCE_RECORDS_PATH.relative_to(BACKEND_ROOT)
    )
    atomic_write_json(STAGING_SNAPSHOT_PATH, snapshot)
    atomic_write_json(STAGING_EVIDENCE_RECORDS_PATH, evidence_records)
    activation = (
        activate_snapshot(snapshot, evidence_records=evidence_records) if activate else None
    )
    source_metrics = _source_metrics(
        documents,
        records,
        permissions,
        oracles,
        dedup_links,
        retrieval,
    )
    if activation:
        created_ids = set(activation.get("_embedding_created_ids") or [])
        reused_ids = set(activation.get("_embedding_reused_ids") or [])
        for row in source_metrics:
            source_id = row["SOURCE_ID"]
            scoped_ids = {
                str(record["chunk_id"])
                for record in records
                if source_id
                in (record.get("provenance_source_ids") or [record.get("source_id")])
            }
            row["EMBEDDINGS_CREATED"] = len(scoped_ids & created_ids)
            row["EMBEDDINGS_REUSED"] = len(scoped_ids & reused_ids)
    report = build_final_report(snapshot, source_metrics=source_metrics, activation=activation)
    atomic_write_json(REPORT_PATH, report)
    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activate",
        action="store_true",
        help="Upsert the validated staging snapshot into the existing manifest and aem_guides Chroma collection.",
    )
    parser.add_argument("--timeout", type=float, default=45.0, help="Per-source HTTP timeout in seconds.")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_ingestion(activate=args.activate, timeout=args.timeout)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["STATUS"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
