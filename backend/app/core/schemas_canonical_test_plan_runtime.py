"""Versioned contracts for the canonical AEM Guides Test Plan runtime.

These models preserve contract, scope, graph, closure, retrieval, promotion,
gate, plan, and trace state until the final renderer.  Entry adapters share
this contract and cannot replace the canonical reasoning stages.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.core.schemas_qe_pattern_mcp import SharedAuthoringGuidance


EVIDENCE_RECORD_SCHEMA = "aem-guides-evidence-record-v2"
EVIDENCE_BUNDLE_SCHEMA = "aem-guides-canonical-evidence-bundle-v2"
GENERATION_REQUEST_SCHEMA = "aem-guides-generation-request-v2"
GENERATION_RESULT_SCHEMA = "aem-guides-generation-result-v2"
CANONICAL_RUNTIME_ID = "aem-guides-test-plan-runtime"
CANONICAL_RUNTIME_VERSION = "2.0.0"
GITHUB_IMPLEMENTATION_HANDOFF_SCHEMA = (
    "aem-guides-github-implementation-verification-handoff-v1"
)
GITHUB_IMPLEMENTATION_RESULT_SCHEMA = (
    "aem-guides-github-implementation-verification-result-v1"
)
_GITHUB_V2_INSPECTION_IDENTITY_FIELDS = {
    "blast_radius_contract",
    "changed_symbols",
    "produced_values",
    "state_writes",
    "state_reads",
    "data_flow_edges",
    "direct_callers",
    "transitive_callers",
    "shared_abstractions",
    "sibling_implementations",
    "alternate_entry_points",
    "role_branches",
    "cross_repo_consumers",
    "tests_found",
    "missing_test_areas",
    "uncertain_relationships",
    "blast_radius_completed_targets",
    "blast_radius_target_outcomes",
    "blast_radius_negative_search_evidence",
}


def canonical_json(value: Any) -> str:
    """Return the one serialization used by deterministic IDs and hashes."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=True)
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def stable_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


_HANDOFF_SECRET_RE = re.compile(
    r"(?i)(?:"
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{4,}|"
    r"\b(?:authorization|proxy[_-]?authorization|password|passwd|secret|"
    r"api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"private[_-]?key|cookie|set[_-]?cookie|token)\b\s*[:=]|"
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{12,}\b|"
    r"\bgithub_pat_[A-Za-z0-9_]{12,}\b|"
    r"\bglpat-[A-Za-z0-9_-]{12,}\b|"
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b|"
    r"-----BEGIN\s+(?:(?:RSA|EC|DSA|OPENSSH)\s+)?PRIVATE\s+KEY-----|"
    r"\[REDACTED\]|"
    r"\b(?:AKIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA|ASIA)[A-Z0-9]{12,}\b|"
    r"[a-z][a-z0-9+.-]*://[^/@\s:]+:[^/@\s]+@|"
    r"[?&#](?:access_token|api_key|apikey|auth|authorization|credential|"
    r"id_token|key|sig|signature|token|x-amz-credential|"
    r"x-amz-security-token|x-amz-signature)="
    r")"
)


def _safe_handoff_text(value: Any, *, max_length: int = 1000) -> str:
    """Normalize bounded correlation text and reject credential-shaped input."""

    text = str(value or "").strip()
    if any(ord(character) < 32 and character not in "\t" for character in text):
        raise ValueError("runtime handoff text contains control characters")
    if _HANDOFF_SECRET_RE.search(text):
        raise ValueError("runtime handoff text cannot contain credentials")
    if len(text) > max_length:
        raise ValueError("runtime handoff text exceeds its size limit")
    return text


class RuntimeEntryPoint(StrEnum):
    CODEX_SKILL = "codex_skill"
    BACKEND_API = "backend_api"
    REST_BRIDGE = "rest_bridge"
    CLI = "cli"
    BENCHMARK_V2 = "benchmark_v2"
    LEGACY_PACKET = "legacy_packet"
    PYTHON_API = "python_api"


class GenerationProfile(StrEnum):
    CODEX_CANONICAL = "codex_canonical_v1"
    BACKEND_COMPATIBILITY = "backend_compatibility_v1"
    LEGACY_PACKET_COMPATIBILITY = "legacy_packet_compatibility_v1"


class EvidenceSourceType(StrEnum):
    JIRA_DESCRIPTION = "JIRA_DESCRIPTION"
    JIRA_ACCEPTANCE_CRITERIA = "JIRA_ACCEPTANCE_CRITERIA"
    JIRA_COMMENT = "JIRA_COMMENT"
    JIRA_ATTACHMENT = "JIRA_ATTACHMENT"
    LINKED_JIRA = "LINKED_JIRA"
    ACCEPTED_UAC = "ACCEPTED_UAC"
    PRODUCT_DECISION = "PRODUCT_DECISION"
    ENGINEERING_DECISION = "ENGINEERING_DECISION"
    OFFICIAL_PRODUCT_DOCUMENTATION = "OFFICIAL_PRODUCT_DOCUMENTATION"
    DITA_SPECIFICATION = "DITA_SPECIFICATION"
    DITA_OT_DOCUMENTATION = "DITA_OT_DOCUMENTATION"
    CURRENT_CODE = "CURRENT_CODE"
    CURRENT_PR = "CURRENT_PR"
    HISTORICAL_JIRA = "HISTORICAL_JIRA"
    EXISTING_AUTOMATION = "EXISTING_AUTOMATION"
    UI_OBSERVATION = "UI_OBSERVATION"
    OBSERVED_UI_FLOW = "OBSERVED_UI_FLOW"
    USER_FEEDBACK = "USER_FEEDBACK"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    CUSTOMER_WORKFLOW = "CUSTOMER_WORKFLOW"
    WORKAROUND = "WORKAROUND"
    BUSINESS_IMPACT = "BUSINESS_IMPACT"
    SCALE_SIGNAL = "SCALE_SIGNAL"
    AEM_ASSETS_PLATFORM_DOCUMENTATION = "AEM_ASSETS_PLATFORM_DOCUMENTATION"
    SCREENSHOT_REPRODUCTION = "SCREENSHOT_REPRODUCTION"
    CURRENT_JIRA = "CURRENT_JIRA"
    DRAFT_UAC = "DRAFT_UAC"
    IMPLEMENTATION_DIFF = "IMPLEMENTATION_DIFF"
    CODE_DIFF = "CODE_DIFF"
    EVIDENCE_GRAPH_LEAF = "EVIDENCE_GRAPH_LEAF"
    MODEL_INFERENCE = "MODEL_INFERENCE"
    BENCHMARK_PUBLIC_INPUT = "BENCHMARK_PUBLIC_INPUT"
    CODEX_MANIFEST = "CODEX_MANIFEST"
    UNKNOWN = "UNKNOWN"

    # Compatibility names used by Phase 1 packet adapters.
    OFFICIAL_DOCUMENTATION = OFFICIAL_PRODUCT_DOCUMENTATION
    DITA_OT = DITA_OT_DOCUMENTATION
    REPOSITORY_CODE = CURRENT_CODE
    PULL_REQUEST = CURRENT_PR
    DESIGN_UI = UI_OBSERVATION
    AUTOMATION = EXISTING_AUTOMATION


class AuthorityClass(StrEnum):
    ACCEPTED_PRODUCT_REQUIREMENT = "ACCEPTED_PRODUCT_REQUIREMENT"
    CONFIRMED_PRODUCT_DECISION = "CONFIRMED_PRODUCT_DECISION"
    OFFICIAL_PRODUCT_CONTRACT = "OFFICIAL_PRODUCT_CONTRACT"
    SPECIFICATION_AUTHORITY = "SPECIFICATION_AUTHORITY"
    IMPLEMENTATION_CONFIRMED = "IMPLEMENTATION_CONFIRMED"
    HISTORICAL_EXPECTATION = "HISTORICAL_EXPECTATION"
    TECHNICALLY_INFERRED = "TECHNICALLY_INFERRED"
    USER_EXPECTATION = "USER_EXPECTATION"
    CUSTOMER_REQUEST = "CUSTOMER_REQUEST"
    PROPOSED = "PROPOSED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    UNKNOWN = "UNKNOWN"

    # Compatibility names; values remain the required canonical classes.
    CURRENT_ACCEPTED_UAC = ACCEPTED_PRODUCT_REQUIREMENT
    CURRENT_JIRA = CUSTOMER_REQUEST
    CURRENT_IMPLEMENTATION = IMPLEMENTATION_CONFIRMED
    CURRENT_DESIGN = TECHNICALLY_INFERRED
    AUTHORITATIVE_SPECIFICATION = SPECIFICATION_AUTHORITY
    OFFICIAL_DOCUMENTATION = OFFICIAL_PRODUCT_CONTRACT
    VERIFIED_AUTOMATION = IMPLEMENTATION_CONFIRMED
    VERIFIED_HISTORICAL = HISTORICAL_EXPECTATION
    HISTORICAL = HISTORICAL_EXPECTATION
    USER_FEEDBACK_CANDIDATE = PENDING_HUMAN_REVIEW
    MODEL_INFERENCE = TECHNICALLY_INFERRED


class VerificationState(StrEnum):
    CONFIRMED = "CONFIRMED"
    INFERRED_HIGH_CONFIDENCE = "INFERRED_HIGH_CONFIDENCE"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"
    NOT_EVALUATED = "NOT_EVALUATED"
    VERIFIED_LIVE = "verified_live"
    VERIFIED_REVISION = "verified_revision"
    VERIFIED_SOURCE = "verified_source"
    ANALYZED = "analyzed"
    CACHED = "cached"
    UNVERIFIED = "unverified"
    FAILED = "failed"


class CurrentnessState(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL_COMPATIBILITY = "HISTORICAL_COMPATIBILITY"
    SUPERSEDED = "SUPERSEDED"
    VERSION_SPECIFIC = "VERSION_SPECIFIC"
    ENVIRONMENT_SPECIFIC = "ENVIRONMENT_SPECIFIC"
    VERSION_UNKNOWN = "VERSION_UNKNOWN"
    CONFLICTING_CURRENTNESS = "CONFLICTING_CURRENTNESS"

    STALE = HISTORICAL_COMPATIBILITY
    CONFLICTED = CONFLICTING_CURRENTNESS
    UNVERSIONED = VERSION_UNKNOWN
    UNKNOWN = VERSION_UNKNOWN


class EvidenceLifecycleStatus(StrEnum):
    RETRIEVED = "RETRIEVED"
    AVAILABLE_NOT_INSPECTED = "AVAILABLE_NOT_INSPECTED"
    INSPECTED = "INSPECTED"
    USED = "USED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"
    IGNORED_BY_COMPATIBILITY_PATH = "IGNORED_BY_COMPATIBILITY_PATH"


class EvidenceConfidenceLevel(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


# Backward-compatible symbol while Phase 2 adapters migrate to the explicit name.
LifecycleState = EvidenceLifecycleStatus


class UiApplicability(StrEnum):
    APPLICABLE_CURRENT = "APPLICABLE_CURRENT"
    APPLICABLE_HISTORICAL = "APPLICABLE_HISTORICAL"
    POSSIBLY_APPLICABLE = "POSSIBLY_APPLICABLE"
    VERSION_MISMATCH = "VERSION_MISMATCH"
    SUPERSEDED = "SUPERSEDED"
    UNKNOWN = "UNKNOWN"


class FeedbackClassification(StrEnum):
    USER_OBSERVATION = "USER_OBSERVATION"
    USER_EXPECTATION = "USER_EXPECTATION"
    USER_PAIN_POINT = "USER_PAIN_POINT"
    CUSTOMER_WORKFLOW = "CUSTOMER_WORKFLOW"
    WORKAROUND = "WORKAROUND"
    SCALE_SIGNAL = "SCALE_SIGNAL"
    BUSINESS_IMPACT = "BUSINESS_IMPACT"
    CUSTOMER_PROPOSED_SOLUTION = "CUSTOMER_PROPOSED_SOLUTION"
    FEATURE_REQUEST = "FEATURE_REQUEST"


class ProductContractOwnership(StrEnum):
    AEM_GUIDES_PRODUCT_CONTRACT = "AEM_GUIDES_PRODUCT_CONTRACT"
    AEM_ASSETS_PLATFORM_CONTRACT = "AEM_ASSETS_PLATFORM_CONTRACT"
    DITA_SPECIFICATION_CONTRACT = "DITA_SPECIFICATION_CONTRACT"
    DITA_OT_PROCESSING_BEHAVIOR = "DITA_OT_PROCESSING_BEHAVIOR"
    CURRENT_IMPLEMENTATION_EVIDENCE = "CURRENT_IMPLEMENTATION_EVIDENCE"
    OBSERVED_UI_STATE = "OBSERVED_UI_STATE"
    USER_REPORTED_BEHAVIOR = "USER_REPORTED_BEHAVIOR"
    UNKNOWN_CROSS_PRODUCT_DEPENDENCY = "UNKNOWN_CROSS_PRODUCT_DEPENDENCY"


class EvidenceDirectness(StrEnum):
    DIRECT = "direct"
    DERIVED = "derived"


class VisibilityClass(StrEnum):
    PUBLIC = "public"
    TENANT = "tenant"
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class ResolutionState(StrEnum):
    RESOLVED = "resolved"
    CONFLICTED = "conflicted"
    STALE = "stale"
    SUPERSEDED = "superseded"
    UNKNOWN = "unknown"


class AuthoritySubject(StrEnum):
    """The question an authority decision is answering."""

    PRODUCT_CONTRACT = "PRODUCT_CONTRACT"
    DITA_SEMANTICS = "DITA_SEMANTICS"
    ACTUAL_IMPLEMENTATION = "ACTUAL_IMPLEMENTATION"
    CURRENT_UI = "CURRENT_UI"


class ContractMode(StrEnum):
    HUMAN_ACCEPTED_CONTRACT = "HUMAN_ACCEPTED_CONTRACT"
    PARTIAL_HUMAN_CONTRACT = "PARTIAL_HUMAN_CONTRACT"
    EVIDENCE_BACKED_PROPOSED_CONTRACT = "EVIDENCE_BACKED_PROPOSED_CONTRACT"
    INSUFFICIENT_EVIDENCE_FOR_CONTRACT = "INSUFFICIENT_EVIDENCE_FOR_CONTRACT"


class ContractFactType(StrEnum):
    DIRECT_EXPECTED_BEHAVIOR = "DIRECT_EXPECTED_BEHAVIOR"
    IN_SCOPE = "IN_SCOPE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    PRIMARY_PRODUCT_AREA = "PRIMARY_PRODUCT_AREA"
    PRIMARY_OUTPUT_TYPE = "PRIMARY_OUTPUT_TYPE"
    PRESET_TYPE = "PRESET_TYPE"
    DITA_OT_PROCESSING_STATE = "DITA_OT_PROCESSING_STATE"
    DEPLOYMENT_MODE = "DEPLOYMENT_MODE"
    PRODUCT_VERSION = "PRODUCT_VERSION"
    FEATURE_STATE = "FEATURE_STATE"
    EXACT_LABELS = "EXACT_LABELS"
    EXACT_DEFAULTS = "EXACT_DEFAULTS"
    EXACT_VALUES = "EXACT_VALUES"
    EXACT_STATUS_NAMES = "EXACT_STATUS_NAMES"
    COLORS = "COLORS"
    COUNTS = "COUNTS"
    LIMITS = "LIMITS"
    HUMAN_TERMINOLOGY = "HUMAN_TERMINOLOGY"
    COMPATIBILITY_REQUIREMENTS = "COMPATIBILITY_REQUIREMENTS"
    EXPLICIT_NEGATIVE_REQUIREMENTS = "EXPLICIT_NEGATIVE_REQUIREMENTS"
    HUMAN_OPEN_QUESTIONS = "HUMAN_OPEN_QUESTIONS"
    ENGINEERING_DESIGN_QUESTIONS = "ENGINEERING_DESIGN_QUESTIONS"
    TERMINOLOGY_CLARIFICATION_REQUIRED = "TERMINOLOGY_CLARIFICATION_REQUIRED"


class ContractPreservationState(StrEnum):
    PRESERVED = "PRESERVED"
    NORMALIZED_WITHOUT_SEMANTIC_CHANGE = "NORMALIZED_WITHOUT_SEMANTIC_CHANGE"
    EXPLICITLY_FLAGGED_AS_AMBIGUOUS = "EXPLICITLY_FLAGGED_AS_AMBIGUOUS"
    LOST = "LOST"


class IssueDomain(StrEnum):
    PUBLISHING = "PUBLISHING"
    AUTHORING = "AUTHORING"
    CONTENT_MANAGEMENT = "CONTENT_MANAGEMENT"
    SEARCH_QUERY = "SEARCH_QUERY"
    WORKFLOW_JOB = "WORKFLOW_JOB"
    MIGRATION = "MIGRATION"
    PERFORMANCE = "PERFORMANCE"
    TRANSLATION = "TRANSLATION"
    BASELINE = "BASELINE"
    ASSETS = "ASSETS"
    EXTENSION_FRAMEWORK = "EXTENSION_FRAMEWORK"
    API = "API"
    OTHER = "OTHER"


class DitaOtProcessingState(StrEnum):
    ON = "ON"
    OFF = "OFF"
    BOTH = "BOTH"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


class PublishingTransformationStage(StrEnum):
    SOURCE_CONTENT = "SOURCE_CONTENT"
    MAP_ROOT_CONTEXT = "MAP_ROOT_CONTEXT"
    PRESET = "PRESET"
    PROFILE_CONFIG = "PROFILE_CONFIG"
    FILTERING_KEY_REFERENCE_RESOLUTION = "FILTERING_KEY_REFERENCE_RESOLUTION"
    SEMANTIC_PROCESSING = "SEMANTIC_PROCESSING"
    INTERMEDIATE_REPRESENTATION = "INTERMEDIATE_REPRESENTATION"
    TRANSFORMER = "TRANSFORMER"
    OUTPUT_BUILDER = "OUTPUT_BUILDER"
    POST_GENERATION = "POST_GENERATION"
    GENERATED_ARTIFACT = "GENERATED_ARTIFACT"
    PERSISTED_REPOSITORY_STATE = "PERSISTED_REPOSITORY_STATE"
    ACTIVATION_PUBLICATION = "ACTIVATION_PUBLICATION"
    STATUS_HISTORY_LOGGING = "STATUS_HISTORY_LOGGING"


class GeneratedOutputOracle(StrEnum):
    ARTIFACT_EXISTS = "ARTIFACT_EXISTS"
    CONTENT_CORRECT = "CONTENT_CORRECT"
    TITLE_CORRECT = "TITLE_CORRECT"
    HIERARCHY_CORRECT = "HIERARCHY_CORRECT"
    ORDER_CORRECT = "ORDER_CORRECT"
    NAVIGATION_CORRECT = "NAVIGATION_CORRECT"
    LINKS_CORRECT = "LINKS_CORRECT"
    METADATA_CORRECT = "METADATA_CORRECT"
    REPOSITORY_STATE_CORRECT = "REPOSITORY_STATE_CORRECT"
    OUTPUT_PATH_CORRECT = "OUTPUT_PATH_CORRECT"
    LOCALE_CORRECT = "LOCALE_CORRECT"
    NO_DUPLICATES = "NO_DUPLICATES"
    NO_ORPHANS = "NO_ORPHANS"
    NO_STALE_OUTPUT = "NO_STALE_OUTPUT"
    UNCHANGED_CONTENT_NOT_REWRITTEN = "UNCHANGED_CONTENT_NOT_REWRITTEN"
    ACTIVATION_STATE_CORRECT = "ACTIVATION_STATE_CORRECT"
    STATUS_MATCHES_REAL_OUTPUT = "STATUS_MATCHES_REAL_OUTPUT"


class LifecycleOperation(StrEnum):
    FIRST_GENERATION = "FIRST_GENERATION"
    REGENERATION = "REGENERATION"
    NO_CHANGE_REGENERATION = "NO_CHANGE_REGENERATION"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    MOVE = "MOVE"
    RENAME = "RENAME"
    SAVE_REOPEN = "SAVE_REOPEN"
    REFRESH = "REFRESH"
    REPUBLISH = "REPUBLISH"
    ACTIVATION = "ACTIVATION"
    CANCEL = "CANCEL"
    RETRY = "RETRY"
    FAILURE_THEN_RECOVERY = "FAILURE_THEN_RECOVERY"
    REPEATED_MEANINGFUL_CHANGES = "REPEATED_MEANINGFUL_CHANGES"


class ApplicabilityState(StrEnum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


class CanonicalRuntimeStage(StrEnum):
    CONTRACT_FACT_EXTRACTOR = "ContractFactExtractor"
    CONTRACT_INTEGRITY_GATE = "ContractIntegrityGate"
    ISSUE_DOMAIN_ROUTER = "IssueDomainRouter"
    SCOPE_RESOLVER = "ScopeResolver"
    CHANGE_SURFACE_EXTRACTOR = "ChangeSurfaceExtractor"
    EVIDENCE_BACKED_BEHAVIOR_GRAPH_BUILDER = "EvidenceBackedBehaviorGraphBuilder"
    BEHAVIOR_MODEL_BUILDER = "BehaviorModelBuilder"
    SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER = "SemanticBehavioralClosureExplorer"
    MISSING_QUESTION_GENERATOR = "MissingQuestionGenerator"
    REASONING_DIRECTED_RETRIEVER = "ReasoningDirectedRetriever"
    HYPOTHESIS_VERIFIER = "HypothesisVerifier"
    DOMAIN_SPECIFIC_IMPACT_MODEL = "DomainSpecificImpactModel"
    COVERAGE_DISPOSITION_CLASSIFIER = "CoverageDispositionClassifier"
    ACCEPTANCE_CONTRACT_RESOLVER = "AcceptanceContractResolver"
    BEHAVIORAL_COMPLETENESS_GATE = "BehavioralCompletenessGate"
    ACCEPTANCE_PROMOTION_GATE = "AcceptancePromotionGate"
    FINAL_QE_PLAN_RENDERER = "FinalQEPlanRenderer"


CANONICAL_STAGE_ORDER: tuple[CanonicalRuntimeStage, ...] = tuple(CanonicalRuntimeStage)


class ChangeSurfaceKind(StrEnum):
    CHANGED_BEHAVIOR = "CHANGED_BEHAVIOR"
    CHANGED_ENTITY = "CHANGED_ENTITY"
    READS = "READS"
    WRITES = "WRITES"
    CALLERS = "CALLERS"
    CALLEES = "CALLEES"
    CONSUMERS = "CONSUMERS"
    CONFIG_DEPENDENCIES = "CONFIG_DEPENDENCIES"
    GENERATED_ARTIFACTS = "GENERATED_ARTIFACTS"
    SHARED_PROCESSORS = "SHARED_PROCESSORS"
    ERROR_PATHS = "ERROR_PATHS"
    PERSISTED_STATE = "PERSISTED_STATE"
    DOWNSTREAM_DECISION_CONSUMERS = "DOWNSTREAM_DECISION_CONSUMERS"


class AbstractSignalKind(StrEnum):
    """Feature-neutral signals retained between surface extraction and closure."""

    CHANGED_BEHAVIOR = "CHANGED_BEHAVIOR"


class ReasoningQuestionFamily(StrEnum):
    """Question families activated by abstract signals, not product names."""

    GOVERNING_SEMANTICS = "GOVERNING_SEMANTICS"


class QuestionGenerationTraceStage(StrEnum):
    """Ordered diagnostic substages; these do not alter canonical stage order."""

    CHANGE_SURFACE_EXTRACTOR = "ChangeSurfaceExtractor"
    ABSTRACT_SIGNAL_EXTRACTOR = "AbstractSignalExtractor"
    REASONING_PATTERN_ROUTER = "ReasoningPatternRouter"
    SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER = "SemanticBehavioralClosureExplorer"
    MISSING_QUESTION_GENERATOR = "MissingQuestionGenerator"


QUESTION_GENERATION_TRACE_ORDER: tuple[QuestionGenerationTraceStage, ...] = tuple(
    QuestionGenerationTraceStage
)


class QuestionGenerationFailureReason(StrEnum):
    SIGNAL_MISSING = "SIGNAL_MISSING"
    PATTERN_NOT_AVAILABLE = "PATTERN_NOT_AVAILABLE"
    PATTERN_NOT_ACTIVATED = "PATTERN_NOT_ACTIVATED"
    CLOSURE_TRAVERSAL_STOPPED = "CLOSURE_TRAVERSAL_STOPPED"
    QUESTION_FAMILY_NOT_GENERATED = "QUESTION_FAMILY_NOT_GENERATED"
    QUESTION_PRUNED = "QUESTION_PRUNED"
    QUESTION_DEDUPED_INCORRECTLY = "QUESTION_DEDUPED_INCORRECTLY"
    SCOPE_FILTERED = "SCOPE_FILTERED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class QuestionGenerationStepOutcome(StrEnum):
    PRODUCED = "PRODUCED"
    ACTIVATED = "ACTIVATED"
    TRAVERSED = "TRAVERSED"
    GENERATED = "GENERATED"
    RESOLVED_WITHOUT_QUESTION = "RESOLVED_WITHOUT_QUESTION"
    NO_MATERIAL_SIGNAL = "NO_MATERIAL_SIGNAL"
    FAILED = "FAILED"


class MissingQuestionOrigin(StrEnum):
    """The author of question wording; Python never impersonates Claude."""

    CLAUDE_DESKTOP = "CLAUDE_DESKTOP"
    PYTHON_COMPATIBILITY_FALLBACK = "PYTHON_COMPATIBILITY_FALLBACK"


class MissingQuestionResolutionStatus(StrEnum):
    PENDING_EVIDENCE = "PENDING_EVIDENCE"
    RESOLVED_BY_EVIDENCE = "RESOLVED_BY_EVIDENCE"
    UNRESOLVED_HUMAN = "UNRESOLVED_HUMAN"
    REJECTED_QUALITY = "REJECTED_QUALITY"


class HumanQuestionClass(StrEnum):
    PRODUCT_EXPECTATION_UNDECIDED = "PRODUCT_EXPECTATION_UNDECIDED"
    CURRENT_SCOPE_UNDECIDED = "CURRENT_SCOPE_UNDECIDED"
    IMPLEMENTATION_APPLICABILITY_UNRESOLVED = "IMPLEMENTATION_APPLICABILITY_UNRESOLVED"
    SUPPORTED_CONFIGURATION_UNDECIDED = "SUPPORTED_CONFIGURATION_UNDECIDED"
    CUSTOMER_SPECIFIC_REPRO_CONDITION_UNKNOWN = (
        "CUSTOMER_SPECIFIC_REPRO_CONDITION_UNKNOWN"
    )


class QuestionEvidenceProvider(StrEnum):
    CURRENT_EVIDENCE = "CURRENT_EVIDENCE"
    PATTERN_MCP_DISCOVERY = "PATTERN_MCP_DISCOVERY"
    GITHUB_MCP = "GITHUB_MCP"
    DITA_SPECIFICATION = "DITA_SPECIFICATION"
    DITA_OT = "DITA_OT"
    FLUFFYJAWS = "FLUFFYJAWS"
    EXPERIENCE_LEAGUE = "EXPERIENCE_LEAGUE"
    CONFIGURATION_OR_TESTS = "CONFIGURATION_OR_TESTS"
    HUMAN_PRODUCT = "HUMAN_PRODUCT"
    UNSPECIFIED = "UNSPECIFIED"


class MissingQuestionQualityFailureReason(StrEnum):
    NO_CHANGED_BEHAVIOR_REFERENCE = "NO_CHANGED_BEHAVIOR_REFERENCE"
    NO_RELATIONSHIP = "NO_RELATIONSHIP"
    NOT_EVIDENCE_SEEKING = "NOT_EVIDENCE_SEEKING"
    ASSERTS_ANSWER = "ASSERTS_ANSWER"
    TOO_GENERIC = "TOO_GENERIC"
    WRONG_FAMILY = "WRONG_FAMILY"
    DUPLICATE_COLLAPSE_LOSS = "DUPLICATE_COLLAPSE_LOSS"
    PRODUCT_DECISION_ASSUMED = "PRODUCT_DECISION_ASSUMED"
    QUESTION_ALREADY_ANSWERED_BY_EVIDENCE = "QUESTION_ALREADY_ANSWERED_BY_EVIDENCE"
    NO_EVIDENCE_PATH = "NO_EVIDENCE_PATH"
    MATERIAL_DIMENSION_LOST = "MATERIAL_DIMENSION_LOST"
    REPEATS_CURRENT_JIRA = "REPEATS_CURRENT_JIRA"
    UNKNOWN_CONTEXT_REFERENCE = "UNKNOWN_CONTEXT_REFERENCE"
    SEMANTIC_DUPLICATE = "SEMANTIC_DUPLICATE"


class QuestionValidationDisposition(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class InvestigationFamilySatisfactionStatus(StrEnum):
    SATISFIED_BY_VALID_QUESTION = "SATISFIED_BY_VALID_QUESTION"
    SATISFIED_BY_EVIDENCE = "SATISFIED_BY_EVIDENCE"
    UNSATISFIED = "UNSATISFIED"
    NOT_REQUIRED = "NOT_REQUIRED"


class BehaviorRelationType(StrEnum):
    DEFINED_BY = "DEFINED_BY"
    CONTRADICTED_BY = "CONTRADICTED_BY"
    CONFIGURED_BY = "CONFIGURED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    CONTROLLING_ATTRIBUTE = "CONTROLLING_ATTRIBUTE"
    REQUIRES = "REQUIRES"
    REQUIRES_ACTIVE_CONTEXT = "REQUIRES_ACTIVE_CONTEXT"
    CONSUMED_BY = "CONSUMED_BY"
    SIBLING_CONSUMER_OF = "SIBLING_CONSUMER_OF"
    ALTERNATE_MECHANISM_TO = "ALTERNATE_MECHANISM_TO"
    FILTERED_BY = "FILTERED_BY"
    CONTROLS_ELIGIBILITY = "CONTROLS_ELIGIBILITY"
    PARENT_OF = "PARENT_OF"
    CHILD_OF = "CHILD_OF"
    SPECIALIZED_BY = "SPECIALIZED_BY"
    REFERENCES = "REFERENCES"
    RESOLVES_THROUGH = "RESOLVES_THROUGH"
    PROCESSED_BY = "PROCESSED_BY"
    GENERATED_BY = "GENERATED_BY"
    PUBLISHED_BY = "PUBLISHED_BY"
    AFFECTS_OUTPUT_OF = "AFFECTS_OUTPUT_OF"
    CALLS = "CALLS"
    DELEGATES_TO = "DELEGATES_TO"
    EXECUTED_BY = "EXECUTED_BY"
    READ_BY = "READ_BY"
    WRITTEN_BY = "WRITTEN_BY"
    CACHED_BY = "CACHED_BY"
    INVALIDATED_BY = "INVALIDATED_BY"
    REFRESHED_BY = "REFRESHED_BY"
    PERSISTS_THROUGH = "PERSISTS_THROUGH"
    SYNCHRONIZED_WITH = "SYNCHRONIZED_WITH"
    AVAILABLE_IN = "AVAILABLE_IN"
    VERSION_DEPENDENT = "VERSION_DEPENDENT"
    DEPLOYMENT_DEPENDENT = "DEPLOYMENT_DEPENDENT"
    ROLE_DEPENDENT = "ROLE_DEPENDENT"
    FEATURE_FLAG_DEPENDENT = "FEATURE_FLAG_DEPENDENT"


class SemanticDimension(StrEnum):
    GOVERNING_SEMANTICS = "GOVERNING_SEMANTICS"
    CONTROLLING_ATTRIBUTES = "CONTROLLING_ATTRIBUTES"
    GOVERNING_CONFIGURATION = "GOVERNING_CONFIGURATION"
    DIRECT_CONSUMERS = "DIRECT_CONSUMERS"
    SIBLING_CONSUMERS = "SIBLING_CONSUMERS"
    ALTERNATE_MECHANISMS = "ALTERNATE_MECHANISMS"
    PARENT_CONTEXT = "PARENT_CONTEXT"
    CHILD_CONTEXT = "CHILD_CONTEXT"
    HIERARCHY = "HIERARCHY"
    SPECIALIZATIONS = "SPECIALIZATIONS"
    REFERENCED_CONTENT = "REFERENCED_CONTENT"
    NESTED_REFERENCED_CONTENT = "NESTED_REFERENCED_CONTENT"
    ALTERNATE_REPRESENTATION = "ALTERNATE_REPRESENTATION"
    FALLBACK = "FALLBACK"
    ABSENT_VALUE = "ABSENT_VALUE"
    INVALID_VALUE = "INVALID_VALUE"
    POSITIVE_STATE = "POSITIVE_STATE"
    NEGATIVE_STATE = "NEGATIVE_STATE"
    LIFECYCLE = "LIFECYCLE"
    CROSS_SURFACE_SYNC = "CROSS_SURFACE_SYNC"
    DOWNSTREAM_PROCESSOR = "DOWNSTREAM_PROCESSOR"
    GENERATED_OUTPUT = "GENERATED_OUTPUT"
    PERSISTED_STATE = "PERSISTED_STATE"
    VERSION_APPLICABILITY = "VERSION_APPLICABILITY"
    DEPLOYMENT_APPLICABILITY = "DEPLOYMENT_APPLICABILITY"
    ROLE_PROFILE_APPLICABILITY = "ROLE_PROFILE_APPLICABILITY"


class PatternLookupRuntimeStatus(StrEnum):
    """Runtime-safe projection of Pattern MCP availability and validity."""

    AVAILABLE_MATCH = "AVAILABLE_MATCH"
    AVAILABLE_NO_MATCH = "AVAILABLE_NO_MATCH"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class PatternSuggestionState(StrEnum):
    """Historical pattern status; never an acceptance-authority decision."""

    PATTERN_SUGGESTED = "PATTERN_SUGGESTED"


class CurrentPatternApplicability(StrEnum):
    """Current-case verification state kept separate from pattern suggestion."""

    CURRENTLY_VERIFIED = "CURRENTLY_VERIFIED"
    CURRENTLY_REJECTED = "CURRENTLY_REJECTED"
    CURRENTLY_UNRESOLVED = "CURRENTLY_UNRESOLVED"


class InvestigationMateriality(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FamilyActivationDecision(StrEnum):
    """Explicit terminal decision for every candidate investigation family."""

    ACTIVATE_BLOCKING = "ACTIVATE_BLOCKING"
    ACTIVATE_NON_BLOCKING = "ACTIVATE_NON_BLOCKING"
    DO_NOT_ACTIVATE = "DO_NOT_ACTIVATE"
    UNRESOLVED_APPLICABILITY = "UNRESOLVED_APPLICABILITY"


class InvestigationFamilySourceKind(StrEnum):
    CURRENT_CHANGE_SURFACE = "CURRENT_CHANGE_SURFACE"
    DETERMINISTIC_REASONING_PATTERN = "DETERMINISTIC_REASONING_PATTERN"
    PATTERN_MCP = "PATTERN_MCP"
    DOMAIN_INVARIANT = "DOMAIN_INVARIANT"
    CURRENT_JIRA_EXPLICIT = "CURRENT_JIRA_EXPLICIT"
    NORMATIVE_SEMANTIC = "NORMATIVE_SEMANTIC"


class ClosureDisposition(StrEnum):
    COVERED = "COVERED"
    INVESTIGATED_AND_REJECTED = "INVESTIGATED_AND_REJECTED"
    UNRESOLVED_AND_EXPOSED = "UNRESOLVED_AND_EXPOSED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class HypothesisState(StrEnum):
    CONFIRMED = "CONFIRMED"
    INFERRED_HIGH_CONFIDENCE = "INFERRED_HIGH_CONFIDENCE"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class RetrievalStatus(StrEnum):
    USED = "USED"
    REJECTED = "REJECTED"
    UNAVAILABLE = "UNAVAILABLE"


class GitHubInspectionTarget(StrEnum):
    """Code relationships that GitHub MCP must inspect before a terminal result."""

    PR_DIFF = "PR_DIFF"
    CHANGED_FILES_CLASSES_METHODS = "CHANGED_FILES_CLASSES_METHODS"
    UPSTREAM_CALLERS = "UPSTREAM_CALLERS"
    DOWNSTREAM_CONSUMERS = "DOWNSTREAM_CONSUMERS"
    SHARED_RESOLVER_USAGE = "SHARED_RESOLVER_USAGE"
    OUTPUT_TYPE_CONSUMERS = "OUTPUT_TYPE_CONSUMERS"
    CONFIGURATION_BRANCHES = "CONFIGURATION_BRANCHES"
    FEATURE_FLAGS = "FEATURE_FLAGS"
    TESTS_CHANGED_ADDED = "TESTS_CHANGED_ADDED"
    MISSING_TESTS = "MISSING_TESTS"


class GitHubBlastRadiusTarget(StrEnum):
    """PFIX-05 value, data, state, and consumer traversal dimensions."""

    CHANGED_SYMBOLS = "CHANGED_SYMBOLS"
    PRODUCED_VALUES = "PRODUCED_VALUES"
    STATE_WRITES = "STATE_WRITES"
    STATE_READS = "STATE_READS"
    DATA_FLOW_EDGES = "DATA_FLOW_EDGES"
    DIRECT_CALLERS = "DIRECT_CALLERS"
    TRANSITIVE_CALLERS = "TRANSITIVE_CALLERS"
    DOWNSTREAM_CONSUMERS = "DOWNSTREAM_CONSUMERS"
    SHARED_ABSTRACTIONS = "SHARED_ABSTRACTIONS"
    SIBLING_IMPLEMENTATIONS = "SIBLING_IMPLEMENTATIONS"
    ALTERNATE_ENTRY_POINTS = "ALTERNATE_ENTRY_POINTS"
    CONFIGURATION_BRANCHES = "CONFIGURATION_BRANCHES"
    FEATURE_FLAGS = "FEATURE_FLAGS"
    ROLE_BRANCHES = "ROLE_BRANCHES"
    CROSS_REPO_CONSUMERS = "CROSS_REPO_CONSUMERS"
    TESTS_FOUND = "TESTS_FOUND"
    MISSING_TEST_AREAS = "MISSING_TEST_AREAS"
    UNCERTAIN_RELATIONSHIPS = "UNCERTAIN_RELATIONSHIPS"


class GitHubImplementationVerificationStatus(StrEnum):
    SHARED_PATH_CONFIRMED = "SHARED_PATH_CONFIRMED"
    UNRELATED_PATH = "UNRELATED_PATH"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE = "UNAVAILABLE"


class GitHubInspectionOutcome(StrEnum):
    FOUND = "FOUND"
    NONE_FOUND = "NONE_FOUND"
    UNAVAILABLE = "UNAVAILABLE"


class CoverageDisposition(StrEnum):
    ACCEPTANCE_CONTRACT = "ACCEPTANCE_CONTRACT"
    PROPOSED_ACCEPTANCE_CONTRACT = "PROPOSED_ACCEPTANCE_CONTRACT"
    SEMANTIC_REGRESSION = "SEMANTIC_REGRESSION"
    STRUCTURAL_REGRESSION = "STRUCTURAL_REGRESSION"
    CONFIGURATION_VARIANT = "CONFIGURATION_VARIANT"
    REFERENCE_REGRESSION = "REFERENCE_REGRESSION"
    GENERATED_OUTPUT_VALIDATION = "GENERATED_OUTPUT_VALIDATION"
    NEGATIVE_BOUNDARY = "NEGATIVE_BOUNDARY"
    FAILURE_RECOVERY = "FAILURE_RECOVERY"
    CROSS_MODE_REGRESSION = "CROSS_MODE_REGRESSION"
    LIFECYCLE_COVERAGE = "LIFECYCLE_COVERAGE"
    NFR_COVERAGE = "NFR_COVERAGE"
    PRODUCT_SCOPE_QUESTION = "PRODUCT_SCOPE_QUESTION"
    OPEN_QUESTION = "OPEN_QUESTION"
    ENGINEERING_DESIGN_DECISION = "ENGINEERING_DESIGN_DECISION"
    IMPLEMENTATION_ORACLE = "IMPLEMENTATION_ORACLE"
    TECHNICAL_NOTE = "TECHNICAL_NOTE"
    KNOWN_LIMITATION = "KNOWN_LIMITATION"
    INVESTIGATED_AND_REJECTED = "INVESTIGATED_AND_REJECTED"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    UNSUPPORTED_INFERENCE = "UNSUPPORTED_INFERENCE"


class PromotionStatus(StrEnum):
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class CandidateLifecycleStage(StrEnum):
    CANDIDATE_DISCOVERED = "CANDIDATE_DISCOVERED"
    APPLICABILITY_EVALUATED = "APPLICABILITY_EVALUATED"
    EVIDENCE_COLLECTED = "EVIDENCE_COLLECTED"
    FINAL_DISPOSITION = "FINAL_DISPOSITION"


class CandidateTerminalDisposition(StrEnum):
    AC = "AC"
    OPEN_QUESTION = "OPEN_QUESTION"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    INVESTIGATED_AND_REJECTED = "INVESTIGATED_AND_REJECTED"


class GateStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


class RuntimePrincipal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    principal_id: str = "system"
    tenant_id: str
    roles: list[str] = Field(default_factory=lambda: ["system"])

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, roles: list[str]) -> list[str]:
        return sorted(
            {str(role).strip().casefold() for role in roles if str(role).strip()}
        )


class SourceVisibility(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: VisibilityClass = VisibilityClass.TENANT
    tenant_id: str
    allowed_roles: list[str] = Field(default_factory=list)
    contains_customer_data: bool = False
    redacted: bool = True

    @field_validator("allowed_roles")
    @classmethod
    def normalize_roles(cls, roles: list[str]) -> list[str]:
        return sorted(
            {str(role).strip().casefold() for role in roles if str(role).strip()}
        )


class VersionScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_versions: list[str] = Field(default_factory=list)
    dita_version: str = ""
    deployment_model: str = ""
    repository: str = ""
    repository_revision: str = ""
    branch: str = ""
    dirty: bool | None = None
    environment: str = ""
    source_updated_at: str = ""
    retrieved_at: str = ""

    @field_validator("product_versions")
    @classmethod
    def normalize_versions(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class ProductOwnership(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str = "AEM Guides"
    product_area: str = ""
    capability: str = ""
    surface: str = ""
    contract_ownership: ProductContractOwnership = (
        ProductContractOwnership.UNKNOWN_CROSS_PRODUCT_DEPENDENCY
    )
    component: str = ""
    repository: str = ""
    layer: Literal[
        "frontend",
        "backend",
        "cross_layer",
        "automation",
        "documentation",
        "design",
        "unknown",
    ] = "unknown"
    owner_status: Literal["confirmed", "inferred", "unknown"] = "unknown"
    owner_source_ids: list[str] = Field(default_factory=list)


class UserFeedbackCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    classifications: list[FeedbackClassification] = Field(default_factory=list)
    event_type: Literal[
        "review_decision",
        "ac_edit",
        "execution_outcome",
        "escaped_defect",
        "other",
    ] = "other"
    plan_fingerprint: str = ""
    evidence_bundle_id: str = ""
    ac_fingerprint: str = ""
    execution_environment: str = ""
    escaped_defect_jira: str = ""
    corroborating_evidence_ids: list[str] = Field(default_factory=list)
    promotion_state: Literal[
        "candidate",
        "corroborated",
        "rejected",
    ] = "candidate"
    automatic_authority_promotion: Literal[False] = False
    authoritative_for: list[
        Literal["experienced_state", "workflow", "impact", "scale_frequency"]
    ] = Field(default_factory=list)
    intended_behavior_authority: Literal[False] = False

    @field_validator("classifications", "authoritative_for")
    @classmethod
    def normalize_feedback_sets(cls, values: list[Any]) -> list[Any]:
        return sorted(set(values), key=str)


class EvidenceRecord(BaseModel):
    """A source-native fact with independent authority and confidence axes."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-evidence-record-v2"] = EVIDENCE_RECORD_SCHEMA
    evidence_id: str = ""
    source_type: EvidenceSourceType
    authority_subject: AuthoritySubject | None = None
    source_reference: str = Field(min_length=1)
    source_location: str = ""
    source_native_id: str = ""
    tenant_id: str
    product: str = "AEM Guides"
    product_area: str = ""
    capability: str = ""
    surface: str = ""
    content: Any
    extracted_facts: list[str] = Field(default_factory=list)
    source_timestamp: str = ""
    retrieved_at: str = ""
    product_version: str = ""
    dita_version: str = ""
    deployment_model: str = ""
    environment: str = ""
    currentness: CurrentnessState = CurrentnessState.VERSION_UNKNOWN
    ui_applicability: UiApplicability = UiApplicability.UNKNOWN
    evidence_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_confidence_level: EvidenceConfidenceLevel = EvidenceConfidenceLevel.UNKNOWN
    requirement_authority: AuthorityClass = AuthorityClass.UNKNOWN
    verification_status: VerificationState = VerificationState.UNVERIFIED
    lifecycle_status: EvidenceLifecycleStatus = EvidenceLifecycleStatus.RETRIEVED
    evidence_role: str = "UNKNOWN"
    retrieval_query: str = ""
    retrieval_pass: str = ""
    retrieved_by_query: list[str] = Field(default_factory=list)
    entered_compatibility_input: bool = False
    inspected: bool = False
    used: bool = False
    rejected_reason: str = ""
    content_sha256: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    directness: EvidenceDirectness = EvidenceDirectness.DIRECT
    version_scope: VersionScope = Field(default_factory=VersionScope)
    ownership: ProductOwnership = Field(default_factory=ProductOwnership)
    visibility: SourceVisibility
    claim_keys: list[str] = Field(default_factory=list)
    derived_from: list[str] = Field(default_factory=list)
    supersedes: list[str] = Field(default_factory=list)
    feedback: UserFeedbackCandidate | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "claim_keys",
        "derived_from",
        "supersedes",
        "extracted_facts",
        "retrieved_by_query",
    )
    @classmethod
    def normalize_string_sets(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})

    @model_validator(mode="after")
    def finalize_identity_and_feedback_policy(self) -> "EvidenceRecord":
        if self.authority_subject is None:
            if self.source_type in {
                EvidenceSourceType.DITA_SPECIFICATION,
                EvidenceSourceType.DITA_OT_DOCUMENTATION,
            }:
                self.authority_subject = AuthoritySubject.DITA_SEMANTICS
            elif self.source_type in {
                EvidenceSourceType.CURRENT_CODE,
                EvidenceSourceType.CURRENT_PR,
                EvidenceSourceType.IMPLEMENTATION_DIFF,
                EvidenceSourceType.CODE_DIFF,
                EvidenceSourceType.EXISTING_AUTOMATION,
            }:
                self.authority_subject = AuthoritySubject.ACTUAL_IMPLEMENTATION
            elif self.source_type in {
                EvidenceSourceType.UI_OBSERVATION,
                EvidenceSourceType.OBSERVED_UI_FLOW,
                EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            }:
                self.authority_subject = AuthoritySubject.CURRENT_UI
            else:
                self.authority_subject = AuthoritySubject.PRODUCT_CONTRACT
        content_hash = stable_sha256(self.content)
        if self.content_sha256 and self.content_sha256 != content_hash:
            raise ValueError("content_sha256 does not match canonical content")
        self.content_sha256 = content_hash
        identity = {
            "schema": self.schema_version,
            "source_type": self.source_type.value,
            "authority_subject": self.authority_subject.value,
            "source_reference": self.source_reference,
            "source_location": self.source_location,
            "source_native_id": self.source_native_id,
            "tenant_id": self.tenant_id,
            "product": self.product,
            "product_area": self.product_area,
            "capability": self.capability,
            "surface": self.surface,
            "source_timestamp": self.source_timestamp,
            "product_version": self.product_version,
            "dita_version": self.dita_version,
            "deployment_model": self.deployment_model,
            "environment": self.environment,
            "repository_revision": self.version_scope.repository_revision,
            "content_sha256": content_hash,
        }
        expected_id = f"ev:{self.source_type.value}:{stable_sha256(identity)[:32]}"
        if self.evidence_id and self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match deterministic source identity")
        self.evidence_id = expected_id
        if self.visibility.tenant_id != self.tenant_id:
            raise ValueError("visibility tenant must match evidence tenant")
        if self.directness == EvidenceDirectness.DERIVED and not self.derived_from:
            raise ValueError("derived evidence requires transformation lineage")
        if (
            self.evidence_confidence_level == EvidenceConfidenceLevel.UNKNOWN
            and self.evidence_confidence > 0
        ):
            self.evidence_confidence_level = (
                EvidenceConfidenceLevel.HIGH
                if self.evidence_confidence >= 0.8
                else EvidenceConfidenceLevel.MEDIUM
                if self.evidence_confidence >= 0.5
                else EvidenceConfidenceLevel.LOW
            )
        if self.lifecycle_status in {
            EvidenceLifecycleStatus.RETRIEVED,
            EvidenceLifecycleStatus.AVAILABLE_NOT_INSPECTED,
        }:
            if self.inspected or self.used or self.rejected_reason:
                raise ValueError(
                    "available evidence cannot be inspected, used, or rejected"
                )
        elif self.lifecycle_status == EvidenceLifecycleStatus.INSPECTED:
            if not self.inspected or self.used or self.rejected_reason:
                raise ValueError(
                    "INSPECTED evidence must be inspected but not used/rejected"
                )
        elif self.lifecycle_status == EvidenceLifecycleStatus.USED:
            if not self.inspected or not self.used or self.rejected_reason:
                raise ValueError("USED evidence must be inspected and used")
        elif self.lifecycle_status == EvidenceLifecycleStatus.REJECTED:
            if self.used or not self.rejected_reason.strip():
                raise ValueError(
                    "REJECTED evidence requires a reason and cannot be used"
                )
        elif self.lifecycle_status == EvidenceLifecycleStatus.UNAVAILABLE:
            if self.inspected or self.used:
                raise ValueError("UNAVAILABLE evidence cannot be inspected or used")
        elif (
            self.lifecycle_status
            == EvidenceLifecycleStatus.IGNORED_BY_COMPATIBILITY_PATH
        ):
            if not self.inspected or self.used or not self.rejected_reason.strip():
                raise ValueError(
                    "IGNORED_BY_COMPATIBILITY_PATH evidence requires inspection and a reason"
                )
        if self.source_type == EvidenceSourceType.USER_FEEDBACK:
            if self.feedback is None:
                raise ValueError(
                    "user feedback evidence requires feedback candidate metadata"
                )
            if self.requirement_authority not in {
                AuthorityClass.USER_EXPECTATION,
                AuthorityClass.CUSTOMER_REQUEST,
                AuthorityClass.PENDING_HUMAN_REVIEW,
                AuthorityClass.UNKNOWN,
            }:
                raise ValueError(
                    "user feedback cannot become intended-product authority"
                )
        return self

    @property
    def source_key(self) -> str:
        return self.source_reference

    @property
    def authority_class(self) -> AuthorityClass:
        return self.requirement_authority

    @property
    def confidence(self) -> float:
        return self.evidence_confidence

    @property
    def verification_state(self) -> VerificationState:
        return self.verification_status

    @property
    def lifecycle(self) -> EvidenceLifecycleStatus:
        return self.lifecycle_status

    def stable_projection(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "source_type": self.source_type.value,
            "authority_subject": self.authority_subject.value,
            "source_reference": self.source_reference,
            "source_location": self.source_location,
            "tenant_id": self.tenant_id,
            "product": self.product,
            "product_area": self.product_area,
            "capability": self.capability,
            "surface": self.surface,
            "content_sha256": self.content_sha256,
            "requirement_authority": self.requirement_authority.value,
            "verification_status": self.verification_status.value,
            "currentness": self.currentness.value,
            "ui_applicability": self.ui_applicability.value,
            "directness": self.directness.value,
            "ownership": self.ownership.model_dump(mode="json"),
            "repository_revision": self.version_scope.repository_revision,
            "dita_version": self.dita_version,
            "deployment_model": self.deployment_model,
            "environment": self.environment,
        }

    def usage_projection(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "lifecycle_status": self.lifecycle_status.value,
            "retrieved_by_query": self.retrieved_by_query,
            "retrieval_query": self.retrieval_query,
            "retrieval_pass": self.retrieval_pass,
            "entered_compatibility_input": self.entered_compatibility_input,
            "inspected": self.inspected,
            "used": self.used,
            "rejected_reason": self.rejected_reason,
        }


class AuthorityResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_key: str
    subject: AuthoritySubject = AuthoritySubject.PRODUCT_CONTRACT
    status: ResolutionState
    selected_evidence_ids: list[str] = Field(default_factory=list)
    competing_evidence_ids: list[str] = Field(default_factory=list)
    reason: str

    @field_validator("selected_evidence_ids", "competing_evidence_ids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class SourceManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    source_type: EvidenceSourceType
    source_reference: str
    source_location: str = ""
    lifecycle_status: EvidenceLifecycleStatus


class CompatibilityProjectionLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legacy_path: str
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("evidence_ids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class LegacyCompatibilityProjection(BaseModel):
    """Lossless legacy payload plus a non-invasive evidence-ID sidecar."""

    model_config = ConfigDict(extra="forbid")

    projection_version: Literal["legacy-packet-projection-v1"] = (
        "legacy-packet-projection-v1"
    )
    legacy_payload: dict[str, Any]
    evidence_links: list[CompatibilityProjectionLink] = Field(default_factory=list)


class CanonicalEvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-canonical-evidence-bundle-v2"] = (
        EVIDENCE_BUNDLE_SCHEMA
    )
    bundle_id: str = ""
    tenant_id: str
    records: list[EvidenceRecord] = Field(default_factory=list)
    issue_facts: dict[str, Any] = Field(default_factory=dict)
    source_manifest: list[SourceManifestEntry] = Field(default_factory=list)
    authority_resolutions: list[AuthorityResolution] = Field(default_factory=list)
    authority_conflicts: list[AuthorityResolution] = Field(default_factory=list)
    currentness_conflicts: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    source_counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "CanonicalEvidenceBundle":
        unique: dict[str, EvidenceRecord] = {}
        for record in self.records:
            if record.tenant_id != self.tenant_id:
                raise ValueError(
                    "cross-tenant evidence cannot enter one canonical bundle"
                )
            existing = unique.get(record.evidence_id)
            if existing and existing.usage_projection() != record.usage_projection():
                raise ValueError(
                    "one evidence identity cannot have conflicting usage states"
                )
            unique.setdefault(record.evidence_id, record)
        self.records = sorted(unique.values(), key=lambda row: row.evidence_id)
        self.source_manifest = [
            SourceManifestEntry(
                evidence_id=row.evidence_id,
                source_type=row.source_type,
                source_reference=row.source_reference,
                source_location=row.source_location,
                lifecycle_status=row.lifecycle_status,
            )
            for row in self.records
        ]
        self.authority_resolutions = sorted(
            self.authority_resolutions,
            key=lambda row: (
                row.claim_key,
                row.subject.value,
                row.status.value,
                row.selected_evidence_ids,
            ),
        )
        counts: dict[str, int] = {}
        for record in self.records:
            counts[record.source_type.value] = (
                counts.get(record.source_type.value, 0) + 1
            )
        self.source_counts = dict(sorted(counts.items()))
        self.authority_conflicts = [
            row
            for row in self.authority_resolutions
            if row.status == ResolutionState.CONFLICTED
        ]
        self.currentness_conflicts = sorted(
            {
                claim
                for row in self.records
                if row.currentness == CurrentnessState.CONFLICTING_CURRENTNESS
                for claim in row.claim_keys
            }
        )
        self.unavailable_sources = sorted(
            {
                str(value).strip()
                for value in self.unavailable_sources
                if str(value).strip()
            }
        )
        identity = {
            "schema": self.schema_version,
            "tenant_id": self.tenant_id,
            "records": [record.stable_projection() for record in self.records],
            "usage": [record.usage_projection() for record in self.records],
            "authority_resolutions": [
                row.model_dump(mode="json", exclude_none=True)
                for row in self.authority_resolutions
            ],
            "issue_facts": self.issue_facts,
            "unavailable_sources": self.unavailable_sources,
        }
        expected_id = f"bundle:{stable_sha256(identity)}"
        if self.bundle_id and self.bundle_id != expected_id:
            raise ValueError("bundle_id does not match deterministic evidence contents")
        self.bundle_id = expected_id
        return self


class PipelineCompatibilityOptions(BaseModel):
    """Lossless typed projection of TestPlanPipelineRequest options."""

    model_config = ConfigDict(extra="forbid")

    evidence_k: int = Field(default=8, ge=3, le=12)
    include_repository_evidence: bool = True
    max_repo_matches: int = Field(default=30, ge=5, le=100)
    skip_uac_label_gate: bool = False
    full_rag: bool = True
    include_evidence_graph: bool = True
    graph_max_paths: int = Field(default=20, ge=1, le=50)
    include_uac_intelligence: bool = True
    compose_draft_plan: bool = True
    write_starling_artifacts: bool = False
    starling_repo_path: str | None = None
    publish_to_team_ui: bool = False
    human_review_threshold: int = Field(default=50, ge=0, le=100)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-generation-request-v2"] = (
        GENERATION_REQUEST_SCHEMA
    )
    request_id: str = ""
    logical_fingerprint: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    jira_key: str
    tenant_id: str
    entry_point: RuntimeEntryPoint
    generation_profile: GenerationProfile
    lifecycle_stage: Literal[
        "pre_development",
        "implementation_review",
        "post_fix_validation",
        "unknown",
    ] = "unknown"
    output_contract: str = "aem-guides-test-plan-output-v1"
    principal: RuntimePrincipal
    benchmark_version: str = ""
    benchmark_split: Literal["", "train", "validation", "blind"] = ""
    benchmark_record_id: str = ""
    allowed_sources: list[EvidenceSourceType] = Field(default_factory=list)
    retrieval_budget: dict[str, int] = Field(default_factory=dict)
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    runtime_context: dict[str, Any] = Field(default_factory=dict)
    options: PipelineCompatibilityOptions = Field(
        default_factory=PipelineCompatibilityOptions
    )

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "GenerationRequest":
        self.jira_key = self.jira_key.strip().upper()
        if self.principal.tenant_id != self.tenant_id:
            raise ValueError("principal tenant must match request tenant")
        if self.entry_point == RuntimeEntryPoint.BENCHMARK_V2:
            if self.benchmark_version != "V2" or not self.benchmark_split:
                raise ValueError("Benchmark V2 requests require version and split")
        identity = self.model_dump(
            mode="json",
            exclude={"request_id", "logical_fingerprint", "entry_point"},
            exclude_none=True,
        )
        expected_fingerprint = stable_sha256(identity)
        if (
            self.logical_fingerprint
            and self.logical_fingerprint != expected_fingerprint
        ):
            raise ValueError("logical_fingerprint does not match deterministic request")
        self.logical_fingerprint = expected_fingerprint
        expected_id = f"req:{expected_fingerprint}"
        if self.request_id and self.request_id != expected_id:
            raise ValueError("request_id does not match deterministic request")
        self.request_id = expected_id
        return self


class ContractFact(BaseModel):
    """An authoritative statement preserved before any prose generation."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = ""
    fact_type: ContractFactType
    literal: str = Field(min_length=1)
    normalized_value: Any = None
    source_evidence_ids: list[str] = Field(default_factory=list)
    source_reference: str = ""
    authority_subject: AuthoritySubject = AuthoritySubject.PRODUCT_CONTRACT
    authority_class: AuthorityClass = AuthorityClass.UNKNOWN
    authoritative: bool = False
    preservation_state: ContractPreservationState = ContractPreservationState.PRESERVED
    ambiguity: str = ""

    @field_validator("source_evidence_ids")
    @classmethod
    def normalize_sources(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})

    @model_validator(mode="after")
    def identify(self) -> "ContractFact":
        identity = self.model_dump(mode="json", exclude={"fact_id"}, exclude_none=True)
        expected = f"fact:{stable_sha256(identity)[:32]}"
        if self.fact_id and self.fact_id != expected:
            raise ValueError("fact_id does not match deterministic fact identity")
        self.fact_id = expected
        if (
            self.preservation_state
            == ContractPreservationState.EXPLICITLY_FLAGGED_AS_AMBIGUOUS
            and not self.ambiguity.strip()
        ):
            raise ValueError("ambiguous contract facts require an explanation")
        return self


class ContractFactSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_mode: ContractMode
    facts: list[ContractFact] = Field(default_factory=list)
    authoritative_fact_ids: list[str] = Field(default_factory=list)
    source_evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize(self) -> "ContractFactSet":
        unique = {fact.fact_id: fact for fact in self.facts}
        self.facts = sorted(unique.values(), key=lambda fact: fact.fact_id)
        self.authoritative_fact_ids = sorted(
            fact.fact_id for fact in self.facts if fact.authoritative
        )
        self.source_evidence_ids = sorted(
            {source for fact in self.facts for source in fact.source_evidence_ids}
        )
        return self


class DomainActivation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: IssueDomain
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)


class ScopeResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_product_area: str = ""
    primary_publishing_mode: str = ""
    primary_preset_type: str = ""
    primary_output_type: str = ""
    enable_dita_ot_processing: DitaOtProcessingState = (
        DitaOtProcessingState.NOT_APPLICABLE
    )
    aem_sites_implementation: ApplicabilityState = ApplicabilityState.NOT_APPLICABLE
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    shared_path_outputs: list[str] = Field(default_factory=list)
    execution_interfaces: list[str] = Field(default_factory=list)
    product_versions: list[str] = Field(default_factory=list)
    deployment_modes: list[str] = Field(default_factory=list)
    unresolved_fields: list[str] = Field(default_factory=list)
    source_fact_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "in_scope",
        "out_of_scope",
        "shared_path_outputs",
        "execution_interfaces",
        "product_versions",
        "deployment_modes",
        "unresolved_fields",
        "source_fact_ids",
    )
    @classmethod
    def normalize_sets(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class ChangeSurface(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_id: str = ""
    kind: ChangeSurfaceKind
    entity: str = Field(min_length=1)
    related_entity: str = ""
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def identify(self) -> "ChangeSurface":
        identity = self.model_dump(mode="json", exclude={"surface_id"})
        expected = f"surface:{stable_sha256(identity)[:32]}"
        if self.surface_id and self.surface_id != expected:
            raise ValueError("surface_id does not match deterministic identity")
        self.surface_id = expected
        self.source_evidence_ids = sorted(set(self.source_evidence_ids))
        return self


class AbstractSignal(BaseModel):
    """A source-bound semantic signal independent of any named feature."""

    model_config = ConfigDict(extra="forbid")

    signal_id: str = ""
    kind: AbstractSignalKind
    subject: str = Field(min_length=1, max_length=500)
    source_surface_ids: list[str] = Field(default_factory=list)
    source_evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def identify(self) -> "AbstractSignal":
        self.source_surface_ids = sorted(set(self.source_surface_ids))
        self.source_evidence_ids = sorted(set(self.source_evidence_ids))
        identity = self.model_dump(mode="json", exclude={"signal_id"})
        expected = f"signal:{stable_sha256(identity)[:32]}"
        if self.signal_id and self.signal_id != expected:
            raise ValueError("signal_id does not match deterministic identity")
        self.signal_id = expected
        return self


class ReasoningPatternActivation(BaseModel):
    """A generic signal-to-question-family routing decision."""

    model_config = ConfigDict(extra="forbid")

    activation_id: str = ""
    pattern_id: Literal["CHANGED_BEHAVIOR_TO_GOVERNING_SEMANTICS"] = (
        "CHANGED_BEHAVIOR_TO_GOVERNING_SEMANTICS"
    )
    question_family: ReasoningQuestionFamily
    semantic_dimension: SemanticDimension
    source_signal_ids: list[str] = Field(default_factory=list)
    subject: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def identify(self) -> "ReasoningPatternActivation":
        self.source_signal_ids = sorted(set(self.source_signal_ids))
        if not self.source_signal_ids:
            raise ValueError("reasoning pattern activation requires a source signal")
        identity = self.model_dump(mode="json", exclude={"activation_id"})
        expected = f"activation:{stable_sha256(identity)[:32]}"
        if self.activation_id and self.activation_id != expected:
            raise ValueError("activation_id does not match deterministic identity")
        self.activation_id = expected
        return self


class PatternLookupCallRecord(BaseModel):
    """One redacted, deterministic Pattern MCP resolver invocation."""

    model_config = ConfigDict(extra="forbid")

    domain: IssueDomain
    provider_name: str = Field(min_length=1, max_length=100)
    provider_status: str = Field(min_length=1, max_length=100)
    pattern_library_version: str = Field(min_length=1, max_length=200)
    pattern_library_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    matched_pattern_ids: list[str] = Field(default_factory=list)
    suppressed_pattern_ids: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    shared_learning_mode: Literal["", "DISABLED", "SHADOW", "ENABLED"] = ""
    shadow_pattern_ids: list[str] = Field(default_factory=list)
    shadow_authoring_guidance_ids: list[str] = Field(default_factory=list)
    retrieved_authoring_guidance_ids: list[str] = Field(default_factory=list)
    excluded_pattern_counts: dict[str, int] = Field(default_factory=dict, max_length=50)

    @field_validator(
        "matched_pattern_ids",
        "suppressed_pattern_ids",
        "warning_codes",
    )
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class MatchedHumanPatternView(BaseModel):
    """Bounded Human-backed pattern view safe for investigation preparation.

    Raw historical Jira/UAC text, case IDs, reviewer identity, and source
    locators are deliberately absent.
    """

    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    pattern_version: str = Field(min_length=1, max_length=100)
    lesson_id: str = Field(default="", max_length=200)
    lesson_kind: Literal["GENERIC_PATTERN", "SCOPED_CASE"] = "GENERIC_PATTERN"
    abstract_trigger: list[str] = Field(default_factory=list, max_length=100)
    relationship_to_explore: list[str] = Field(default_factory=list, max_length=50)
    support_count: int = Field(ge=1)
    independent_case_count: int = Field(ge=1)
    counterexample_summary: list[str] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0.0, le=1.0)
    applicability: float = Field(ge=0.0, le=1.0)
    suggestion_state: Literal[PatternSuggestionState.PATTERN_SUGGESTED] = (
        PatternSuggestionState.PATTERN_SUGGESTED
    )
    current_applicability: CurrentPatternApplicability = (
        CurrentPatternApplicability.CURRENTLY_UNRESOLVED
    )
    recommended_question_families: list[SemanticDimension] = Field(default_factory=list)
    preferred_evidence_sources: list[EvidenceSourceType] = Field(default_factory=list)
    materiality: InvestigationMateriality
    blocking_default: bool = False

    @field_validator(
        "abstract_trigger",
        "relationship_to_explore",
        "counterexample_summary",
    )
    @classmethod
    def normalize_text(cls, values: list[str]) -> list[str]:
        return sorted(
            {
                _safe_handoff_text(value, max_length=500)
                for value in values
                if str(value).strip()
            }
        )


class PatternApplicabilityRecord(BaseModel):
    """Pattern suggestion and current-case applicability remain orthogonal."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,127}$")
    suggestion_state: PatternSuggestionState | None = None
    current_applicability: CurrentPatternApplicability
    reason_codes: list[str] = Field(default_factory=list)
    recommended_question_families: list[SemanticDimension] = Field(
        default_factory=list,
        max_length=50,
    )
    counterexample_evidence: list[str] = Field(default_factory=list, max_length=100)
    preferred_evidence_sources: list[EvidenceSourceType] = Field(
        default_factory=list,
        max_length=50,
    )
    materiality: InvestigationMateriality | None = None
    blocking_default: bool = False
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    applicability: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("reason_codes", "counterexample_evidence")
    @classmethod
    def normalize_reasons(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})

    @field_validator("recommended_question_families")
    @classmethod
    def normalize_families(
        cls, values: list[SemanticDimension]
    ) -> list[SemanticDimension]:
        return sorted(set(values), key=lambda row: row.value)

    @field_validator("preferred_evidence_sources")
    @classmethod
    def normalize_evidence_sources(
        cls, values: list[EvidenceSourceType]
    ) -> list[EvidenceSourceType]:
        return sorted(set(values), key=lambda row: row.value)


class PatternLookupResult(BaseModel):
    """Fail-closed Pattern MCP output before family activation."""

    model_config = ConfigDict(extra="forbid")

    status: PatternLookupRuntimeStatus
    calls: list[PatternLookupCallRecord] = Field(default_factory=list)
    matched_human_patterns: list[MatchedHumanPatternView] = Field(default_factory=list)
    applicability_records: list[PatternApplicabilityRecord] = Field(
        default_factory=list
    )
    warning_codes: list[str] = Field(default_factory=list)
    authoring_guidance: list[SharedAuthoringGuidance] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_status(self) -> "PatternLookupResult":
        self.calls = sorted(self.calls, key=lambda row: row.domain.value)
        self.matched_human_patterns = sorted(
            self.matched_human_patterns,
            key=lambda row: row.pattern_id,
        )
        self.applicability_records = sorted(
            self.applicability_records,
            key=lambda row: row.pattern_id,
        )
        self.warning_codes = sorted(set(self.warning_codes))
        if self.status == PatternLookupRuntimeStatus.AVAILABLE_MATCH:
            if not self.matched_human_patterns:
                raise ValueError("AVAILABLE_MATCH requires a validated pattern")
        elif self.matched_human_patterns:
            raise ValueError("non-match Pattern status cannot carry pattern influence")
        return self


class InvestigationFamilySourceContribution(BaseModel):
    """One provenance-preserving reason an investigation family is required."""

    model_config = ConfigDict(extra="forbid")

    contribution_id: str = ""
    source: InvestigationFamilySourceKind
    source_ids: list[str] = Field(default_factory=list)
    why_required: str = Field(min_length=1, max_length=500)
    linked_change_surface_ids: list[str] = Field(default_factory=list)
    linked_pattern_ids: list[str] = Field(default_factory=list)
    materiality: InvestigationMateriality = InvestigationMateriality.P2
    blocking_status: bool = False
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    preferred_evidence_sources: list[EvidenceSourceType] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "InvestigationFamilySourceContribution":
        self.source_ids = sorted(set(self.source_ids))
        self.linked_change_surface_ids = sorted(set(self.linked_change_surface_ids))
        self.linked_pattern_ids = sorted(set(self.linked_pattern_ids))
        self.preferred_evidence_sources = sorted(
            set(self.preferred_evidence_sources), key=lambda row: row.value
        )
        identity = self.model_dump(mode="json", exclude={"contribution_id"})
        expected = f"family-source:{stable_sha256(identity)[:32]}"
        if self.contribution_id and self.contribution_id != expected:
            raise ValueError("family source ID does not match deterministic identity")
        self.contribution_id = expected
        return self


class MandatoryInvestigationFamily(BaseModel):
    """Explicit family decision with every contributing source retained.

    The legacy class/field name is retained for public-interface compatibility;
    records may now also disposition a candidate as unresolved or not activated.
    """

    model_config = ConfigDict(extra="forbid")

    family_id: SemanticDimension
    sources: list[InvestigationFamilySourceContribution] = Field(min_length=1)
    source: list[InvestigationFamilySourceKind] = Field(default_factory=list)
    why_required: list[str] = Field(default_factory=list)
    linked_change_surface: list[str] = Field(default_factory=list)
    linked_change_surface_ids: list[str] = Field(default_factory=list)
    linked_pattern_ids: list[str] = Field(default_factory=list)
    positive_evidence: list[str] = Field(default_factory=list, max_length=500)
    counterexample_evidence: list[str] = Field(default_factory=list, max_length=100)
    materiality: InvestigationMateriality
    priority: int = Field(default=2, ge=0, le=3)
    activation_decision: FamilyActivationDecision
    blocking_status: bool = False
    preferred_evidence_sources: list[EvidenceSourceType] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    applicability_reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def normalize_merged_fields(self) -> "MandatoryInvestigationFamily":
        unique = {row.contribution_id: row for row in self.sources}
        self.sources = sorted(
            unique.values(), key=lambda row: (row.source.value, row.contribution_id)
        )
        self.source = sorted(
            {row.source for row in self.sources} | set(self.source),
            key=lambda row: row.value,
        )
        self.why_required = sorted(
            {row.why_required for row in self.sources} | set(self.why_required)
        )
        self.linked_change_surface_ids = sorted(
            {value for row in self.sources for value in row.linked_change_surface_ids}
            | set(self.linked_change_surface_ids)
        )
        self.linked_change_surface = sorted(
            set(self.linked_change_surface) | set(self.linked_change_surface_ids)
        )
        self.linked_pattern_ids = sorted(
            {value for row in self.sources for value in row.linked_pattern_ids}
            | set(self.linked_pattern_ids)
        )
        self.positive_evidence = sorted(
            {
                value
                for row in self.sources
                for value in (row.source_ids or [row.contribution_id])
            }
            | set(self.positive_evidence)
        )
        self.counterexample_evidence = sorted(set(self.counterexample_evidence))
        materiality_order = (
            InvestigationMateriality.P0,
            InvestigationMateriality.P1,
            InvestigationMateriality.P2,
            InvestigationMateriality.P3,
        )
        self.materiality = min(
            (row.materiality for row in self.sources),
            key=materiality_order.index,
        )
        self.priority = materiality_order.index(self.materiality)
        self.blocking_status = (
            self.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
        )
        if self.blocking_status and self.materiality not in {
            InvestigationMateriality.P0,
            InvestigationMateriality.P1,
        }:
            raise ValueError("blocking family activation requires P0 or P1 materiality")
        self.preferred_evidence_sources = sorted(
            {value for row in self.sources for value in row.preferred_evidence_sources}
            | set(self.preferred_evidence_sources),
            key=lambda row: row.value,
        )
        self.confidence = max(row.confidence for row in self.sources)
        return self


class QeInvestigationConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    explicit_out_of_scope: list[str] = Field(default_factory=list)
    excluded_relationships: list[str] = Field(default_factory=list)
    current_product_decisions: list[str] = Field(default_factory=list)

    @field_validator(
        "explicit_out_of_scope",
        "excluded_relationships",
        "current_product_decisions",
    )
    @classmethod
    def normalize_values(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class InvestigationRetrievalHint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: SemanticDimension
    preferred_evidence_sources: list[EvidenceSourceType] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("preferred_evidence_sources")
    @classmethod
    def normalize_sources(
        cls, values: list[EvidenceSourceType]
    ) -> list[EvidenceSourceType]:
        return sorted(set(values), key=lambda row: row.value)


class QeInvestigationPreparation(BaseModel):
    """Canonical pre-question payload shared by every runtime entry adapter."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-qe-investigation-preparation-v1"] = (
        "aem-guides-qe-investigation-preparation-v1"
    )
    preparation_id: str = ""
    request_id: str | None = None
    plan_id: str | None = None
    normalized_jira_facts: ContractFactSet
    scope: ScopeResolution
    out_of_scope: list[str] = Field(default_factory=list)
    open_decisions: list[str] = Field(default_factory=list)
    domains: list[DomainActivation] = Field(default_factory=list)
    change_surfaces: list[ChangeSurface] = Field(default_factory=list)
    abstract_signals: list[AbstractSignal] = Field(default_factory=list)
    pattern_lookup: PatternLookupResult
    matched_human_patterns: list[MatchedHumanPatternView] = Field(default_factory=list)
    authoring_guidance: list[SharedAuthoringGuidance] = Field(default_factory=list, max_length=50)
    mandatory_families: list[MandatoryInvestigationFamily] = Field(default_factory=list)
    already_investigated_dimensions: list[SemanticDimension] = Field(
        default_factory=list
    )
    constraints: QeInvestigationConstraints
    retrieval_hints: list[InvestigationRetrievalHint] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "QeInvestigationPreparation":
        self.out_of_scope = sorted(set(self.out_of_scope))
        self.open_decisions = sorted(set(self.open_decisions))
        self.domains = sorted(self.domains, key=lambda row: row.domain.value)
        self.change_surfaces = sorted(
            self.change_surfaces, key=lambda row: row.surface_id
        )
        self.abstract_signals = sorted(
            self.abstract_signals, key=lambda row: row.signal_id
        )
        self.matched_human_patterns = sorted(
            self.matched_human_patterns, key=lambda row: row.pattern_id
        )
        self.mandatory_families = sorted(
            self.mandatory_families, key=lambda row: row.family_id.value
        )
        self.already_investigated_dimensions = sorted(
            set(self.already_investigated_dimensions), key=lambda row: row.value
        )
        self.retrieval_hints = sorted(
            self.retrieval_hints, key=lambda row: row.family_id.value
        )
        if self.matched_human_patterns != self.pattern_lookup.matched_human_patterns:
            raise ValueError("preparation pattern view must match Pattern lookup")
        if self.authoring_guidance != self.pattern_lookup.authoring_guidance:
            raise ValueError("preparation editorial context must match reviewed lookup")
        identity = self.model_dump(mode="json", exclude={"preparation_id"})
        expected = f"investigation:{stable_sha256(identity)[:32]}"
        if self.preparation_id and self.preparation_id != expected:
            raise ValueError("preparation ID does not match deterministic identity")
        self.preparation_id = expected
        return self


class BehaviorGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = ""
    label: str = Field(min_length=1)
    node_type: str
    source_evidence_ids: list[str] = Field(default_factory=list)
    authoritative: bool = False

    @model_validator(mode="after")
    def identify(self) -> "BehaviorGraphNode":
        identity = self.model_dump(mode="json", exclude={"node_id"})
        expected = f"node:{stable_sha256(identity)[:32]}"
        if self.node_id and self.node_id != expected:
            raise ValueError("node_id does not match deterministic identity")
        self.node_id = expected
        self.source_evidence_ids = sorted(set(self.source_evidence_ids))
        return self


class BehaviorGraphEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_id: str = ""
    source_node_id: str
    target_node_id: str
    relation: BehaviorRelationType
    provenance_evidence_ids: list[str] = Field(default_factory=list)
    authority_subject: AuthoritySubject
    authority_class: AuthorityClass
    currentness: CurrentnessState
    applicability: ApplicabilityState = ApplicabilityState.APPLICABLE
    confidence: float = Field(ge=0.0, le=1.0)
    verification_state: HypothesisState = HypothesisState.UNRESOLVED

    @model_validator(mode="after")
    def identify(self) -> "BehaviorGraphEdge":
        identity = self.model_dump(mode="json", exclude={"edge_id"})
        expected = f"edge:{stable_sha256(identity)[:32]}"
        if self.edge_id and self.edge_id != expected:
            raise ValueError("edge_id does not match deterministic identity")
        self.edge_id = expected
        self.provenance_evidence_ids = sorted(set(self.provenance_evidence_ids))
        return self


class BehaviorGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[BehaviorGraphNode] = Field(default_factory=list)
    edges: list[BehaviorGraphEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_graph(self) -> "BehaviorGraph":
        self.nodes = sorted(
            {row.node_id: row for row in self.nodes}.values(),
            key=lambda row: row.node_id,
        )
        self.edges = sorted(
            {row.edge_id: row for row in self.edges}.values(),
            key=lambda row: row.edge_id,
        )
        node_ids = {row.node_id for row in self.nodes}
        dangling = [
            edge.edge_id
            for edge in self.edges
            if edge.source_node_id not in node_ids
            or edge.target_node_id not in node_ids
        ]
        if dangling:
            raise ValueError(f"behavior graph has dangling edges: {dangling}")
        return self


class CanonicalBehaviorModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_entities: list[str] = Field(default_factory=list)
    domains: list[IssueDomain] = Field(default_factory=list)
    graph: BehaviorGraph = Field(default_factory=BehaviorGraph)
    publishing_transformation_stages: dict[
        PublishingTransformationStage, ApplicabilityState
    ] = Field(default_factory=dict)
    generated_artifact_delivery: ApplicabilityState = ApplicabilityState.NOT_APPLICABLE
    generated_output_oracles: list[GeneratedOutputOracle] = Field(default_factory=list)
    lifecycle_operations: list[LifecycleOperation] = Field(default_factory=list)


class ClosureDimensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    closure_id: str = ""
    entity: str
    dimension: SemanticDimension
    applicability: ApplicabilityState
    disposition: ClosureDisposition
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def identify(self) -> "ClosureDimensionResult":
        if (
            self.applicability == ApplicabilityState.APPLICABLE
            and self.disposition == ClosureDisposition.NOT_APPLICABLE
        ):
            raise ValueError(
                "applicable closure dimensions require a material disposition"
            )
        identity = self.model_dump(mode="json", exclude={"closure_id"})
        expected = f"closure:{stable_sha256(identity)[:32]}"
        if self.closure_id and self.closure_id != expected:
            raise ValueError("closure_id does not match deterministic identity")
        self.closure_id = expected
        self.evidence_ids = sorted(set(self.evidence_ids))
        return self


class MissingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = ""
    # ``question`` is retained for every existing API/CLI/MCP projection.
    # ``question_text`` is the PFIX-04 canonical name.  The validator keeps
    # both byte-for-byte equal so callers can migrate without semantic drift.
    question: str = Field(default="", max_length=2000)
    question_text: str = Field(default="", max_length=2000)
    dimension: SemanticDimension | None = None
    family_id: SemanticDimension | None = None
    why_it_matters: str = Field(default="", max_length=2000)
    linked_change_surface: list[str] = Field(default_factory=list, max_length=100)
    linked_behavior_or_state: str = Field(default="", max_length=1000)
    relationship_being_tested: BehaviorRelationType | None = None
    expected_evidence_type: list[EvidenceSourceType] = Field(
        default_factory=list,
        max_length=50,
    )
    preferred_provider: QuestionEvidenceProvider = QuestionEvidenceProvider.UNSPECIFIED
    materiality: InvestigationMateriality = InvestigationMateriality.P2
    blocking_status: bool = False
    active_domain: list[IssueDomain] = Field(default_factory=list, max_length=20)
    active_reasoner: str = Field(default="", max_length=200)
    linked_pattern_ids: list[str] = Field(default_factory=list, max_length=100)
    current_fact_refs: list[str] = Field(default_factory=list, max_length=100)
    expected_oracle: str = Field(default="", max_length=1000)
    resolution_status: MissingQuestionResolutionStatus = (
        MissingQuestionResolutionStatus.PENDING_EVIDENCE
    )
    human_question_class: HumanQuestionClass | None = None
    origin: MissingQuestionOrigin = MissingQuestionOrigin.PYTHON_COMPATIBILITY_FALLBACK
    authority_subject: AuthoritySubject
    target_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    blocking: bool = False
    source_closure_ids: list[str] = Field(default_factory=list)
    source_fact_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identify(self) -> "MissingQuestion":
        legacy_text = self.question.strip()
        canonical_text = self.question_text.strip()
        if legacy_text and canonical_text and legacy_text != canonical_text:
            raise ValueError("question and question_text must be identical")
        selected_text = canonical_text or legacy_text
        if not selected_text:
            raise ValueError("missing question text cannot be empty")
        self.question = selected_text
        self.question_text = selected_text
        if self.dimension is not None and self.family_id is not None:
            if self.dimension != self.family_id:
                raise ValueError(
                    "dimension and family_id must identify the same family"
                )
        self.dimension = self.family_id or self.dimension
        self.family_id = self.dimension
        if self.blocking_status != self.blocking:
            blocking = self.blocking_status or self.blocking
            self.blocking_status = blocking
            self.blocking = blocking
        if not self.expected_evidence_type:
            self.expected_evidence_type = list(self.target_source_types)
        if not self.target_source_types:
            self.target_source_types = list(self.expected_evidence_type)
        if set(self.expected_evidence_type) != set(self.target_source_types):
            raise ValueError(
                "expected_evidence_type and target_source_types must describe the same evidence path"
            )
        self.linked_change_surface = sorted(set(self.linked_change_surface))
        self.active_domain = sorted(set(self.active_domain), key=lambda row: row.value)
        self.linked_pattern_ids = sorted(set(self.linked_pattern_ids))
        self.current_fact_refs = sorted(set(self.current_fact_refs))
        self.source_closure_ids = sorted(set(self.source_closure_ids))
        self.source_fact_ids = sorted(set(self.source_fact_ids))
        # Preserve the pre-PFIX-04 opaque ID for compatibility.  Rich context
        # is validated and traced separately, while the established question
        # text/dimension/authority/evidence-path identity remains stable.
        identity = {
            "question": self.question,
            "dimension": self.dimension,
            "authority_subject": self.authority_subject,
            "target_source_types": self.target_source_types,
            "blocking": self.blocking,
        }
        expected = f"question:{stable_sha256(identity)[:32]}"
        if self.question_id and self.question_id != expected:
            raise ValueError("question_id does not match deterministic identity")
        self.question_id = expected
        return self


class ClaudeMissingQuestionSubmission(BaseModel):
    """Hash-bound Claude Desktop output; no backend LLM is invoked."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-claude-missing-question-submission-v1"] = (
        "aem-guides-claude-missing-question-submission-v1"
    )
    submission_id: str = ""
    preparation_id: str = Field(pattern=r"^investigation:[a-f0-9]{32}$")
    request_id: str | None = Field(default=None, pattern=r"^req:[a-f0-9]{64}$")
    questions: list[MissingQuestion] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "ClaudeMissingQuestionSubmission":
        for row in self.questions:
            for value, max_length in (
                (row.question, 2000),
                (row.why_it_matters, 2000),
                (row.linked_behavior_or_state, 1000),
                (row.expected_oracle, 1000),
                (row.active_reasoner, 200),
            ):
                _safe_handoff_text(value, max_length=max_length)
        if any(
            row.origin != MissingQuestionOrigin.CLAUDE_DESKTOP for row in self.questions
        ):
            raise ValueError(
                "Claude submission can contain only CLAUDE_DESKTOP questions"
            )
        if len({row.question_id for row in self.questions}) != len(self.questions):
            raise ValueError("Claude submission contains duplicate opaque question IDs")
        self.questions = sorted(self.questions, key=lambda row: row.question_id)
        identity = self.model_dump(mode="json", exclude={"submission_id"})
        expected = f"question-submission:{stable_sha256(identity)[:32]}"
        if self.submission_id and self.submission_id != expected:
            raise ValueError("submission_id does not match deterministic contents")
        self.submission_id = expected
        return self


class MissingQuestionQualityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^question:[a-f0-9]{32}$")
    disposition: QuestionValidationDisposition
    failure_reasons: list[MissingQuestionQualityFailureReason] = Field(
        default_factory=list
    )
    semantic_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    family_satisfaction_eligible: bool = False

    @model_validator(mode="after")
    def validate_disposition(self) -> "MissingQuestionQualityDecision":
        self.failure_reasons = sorted(
            set(self.failure_reasons), key=lambda row: row.value
        )
        if self.disposition == QuestionValidationDisposition.ACCEPTED:
            if self.failure_reasons:
                raise ValueError("accepted question cannot carry quality failures")
        elif not self.failure_reasons:
            raise ValueError(
                "rejected question requires a deterministic failure reason"
            )
        if self.family_satisfaction_eligible and self.disposition != (
            QuestionValidationDisposition.ACCEPTED
        ):
            raise ValueError("only an accepted question can satisfy a family")
        return self


class InvestigationFamilySatisfaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: SemanticDimension
    activation_decision: FamilyActivationDecision
    status: InvestigationFamilySatisfactionStatus
    valid_question_ids: list[str] = Field(default_factory=list)
    evidence_resolution_ids: list[str] = Field(default_factory=list)
    failure_reasons: list[MissingQuestionQualityFailureReason] = Field(
        default_factory=list
    )

    @model_validator(mode="after")
    def normalize(self) -> "InvestigationFamilySatisfaction":
        self.valid_question_ids = sorted(set(self.valid_question_ids))
        self.evidence_resolution_ids = sorted(set(self.evidence_resolution_ids))
        self.failure_reasons = sorted(
            set(self.failure_reasons), key=lambda row: row.value
        )
        if self.status == InvestigationFamilySatisfactionStatus.UNSATISFIED:
            if MissingQuestionQualityFailureReason.MATERIAL_DIMENSION_LOST not in (
                self.failure_reasons
            ):
                raise ValueError(
                    "unsatisfied family must expose MATERIAL_DIMENSION_LOST"
                )
        elif self.failure_reasons:
            raise ValueError("satisfied/not-required family cannot carry failures")
        return self


class MissingQuestionQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-missing-question-quality-report-v1"] = (
        "aem-guides-missing-question-quality-report-v1"
    )
    report_id: str = ""
    preparation_id: str = Field(pattern=r"^investigation:[a-f0-9]{32}$")
    question_origin: MissingQuestionOrigin
    submitted_questions: list[MissingQuestion] = Field(default_factory=list)
    accepted_questions: list[MissingQuestion] = Field(default_factory=list)
    decisions: list[MissingQuestionQualityDecision] = Field(default_factory=list)
    family_satisfaction: list[InvestigationFamilySatisfaction] = Field(
        default_factory=list
    )
    duplicate_collapse_loss: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "MissingQuestionQualityReport":
        self.submitted_questions = sorted(
            self.submitted_questions, key=lambda row: row.question_id
        )
        self.accepted_questions = sorted(
            self.accepted_questions, key=lambda row: row.question_id
        )
        self.decisions = sorted(self.decisions, key=lambda row: row.question_id)
        self.family_satisfaction = sorted(
            self.family_satisfaction, key=lambda row: row.family_id.value
        )
        self.duplicate_collapse_loss = sorted(set(self.duplicate_collapse_loss))
        submitted_ids = {row.question_id for row in self.submitted_questions}
        accepted_ids = {row.question_id for row in self.accepted_questions}
        decision_ids = {row.question_id for row in self.decisions}
        if submitted_ids != decision_ids or not accepted_ids.issubset(submitted_ids):
            raise ValueError(
                "quality decisions must cover every submitted question exactly"
            )
        accepted_decision_ids = {
            row.question_id
            for row in self.decisions
            if row.disposition == QuestionValidationDisposition.ACCEPTED
        }
        if accepted_ids != accepted_decision_ids:
            raise ValueError("accepted questions must match accepted quality decisions")
        identity = self.model_dump(mode="json", exclude={"report_id"})
        expected = f"question-quality:{stable_sha256(identity)[:32]}"
        if self.report_id and self.report_id != expected:
            raise ValueError("quality report ID does not match deterministic contents")
        self.report_id = expected
        return self


class MissingQuestionResolutionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str = Field(pattern=r"^question:[a-f0-9]{32}$")
    status: MissingQuestionResolutionStatus
    evidence_ids: list[str] = Field(default_factory=list)
    disposition_ids: list[str] = Field(default_factory=list)
    human_question_class: HumanQuestionClass | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def normalize(self) -> "MissingQuestionResolutionRecord":
        self.evidence_ids = sorted(set(self.evidence_ids))
        self.disposition_ids = sorted(set(self.disposition_ids))
        if self.status == MissingQuestionResolutionStatus.UNRESOLVED_HUMAN:
            if self.human_question_class is None:
                raise ValueError(
                    "unresolved Human question requires a classified reason"
                )
        elif self.human_question_class is not None:
            raise ValueError("only unresolved Human questions carry a Human class")
        return self


class DirectedRetrievalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_id: str = ""
    question_id: str
    query: str
    authority_subject: AuthoritySubject
    target_source_types: list[EvidenceSourceType] = Field(default_factory=list)
    matched_evidence_ids: list[str] = Field(default_factory=list)
    status: RetrievalStatus
    reason: str = ""

    @model_validator(mode="after")
    def identify(self) -> "DirectedRetrievalRecord":
        identity = self.model_dump(mode="json", exclude={"retrieval_id"})
        expected = f"retrieval:{stable_sha256(identity)[:32]}"
        if self.retrieval_id and self.retrieval_id != expected:
            raise ValueError("retrieval_id does not match deterministic identity")
        self.retrieval_id = expected
        self.matched_evidence_ids = sorted(set(self.matched_evidence_ids))
        return self


class GitHubExpectedChangeSurface(BaseModel):
    """Source-bound change surface supplied to GitHub MCP."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    surface_id: str = Field(alias="SURFACE_ID", pattern=r"^surface:[a-f0-9]{32}$")
    kind: ChangeSurfaceKind = Field(alias="KIND")
    entity: str = Field(alias="ENTITY", min_length=1, max_length=500)
    source_evidence_ids: list[str] = Field(
        default_factory=list,
        alias="SOURCE_EVIDENCE_IDS",
        max_length=100,
    )

    @field_validator("entity")
    @classmethod
    def validate_entity(cls, value: str) -> str:
        return _safe_handoff_text(value, max_length=500)

    @field_validator("source_evidence_ids")
    @classmethod
    def normalize_evidence_ids(cls, values: list[str]) -> list[str]:
        normalized = sorted(set(values))
        if any(
            re.fullmatch(r"ev:[A-Z0-9_]+:[a-f0-9]{32}", value) is None
            for value in normalized
        ):
            raise ValueError("change-surface lineage must use canonical evidence IDs")
        return normalized


class GitHubImplementationContext(BaseModel):
    """Bounded Jira/PR scope sent to GitHub MCP; never contains credentials."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    jira_key: str = Field(alias="JIRA_KEY", min_length=1, max_length=64)
    pull_request_references: list[str] = Field(
        default_factory=list,
        alias="PULL_REQUEST_REFERENCES",
        max_length=50,
    )
    repository_revisions: list[str] = Field(
        default_factory=list,
        alias="REPOSITORY_REVISIONS",
        max_length=50,
    )
    product_versions: list[str] = Field(
        default_factory=list,
        alias="PRODUCT_VERSIONS",
        max_length=50,
    )
    deployment_modes: list[str] = Field(
        default_factory=list,
        alias="DEPLOYMENT_MODES",
        max_length=20,
    )
    source_evidence_ids: list[str] = Field(
        default_factory=list,
        alias="SOURCE_EVIDENCE_IDS",
        max_length=100,
    )

    @field_validator("jira_key")
    @classmethod
    def validate_jira_key(cls, value: str) -> str:
        text = _safe_handoff_text(value, max_length=64).upper()
        if re.fullmatch(r"[A-Z][A-Z0-9_]*-[A-Z0-9][A-Z0-9_-]*", text) is None:
            raise ValueError("JIRA_KEY must use a bounded Jira-style identifier")
        return text

    @field_validator(
        "pull_request_references",
        "repository_revisions",
        "product_versions",
        "deployment_modes",
        "source_evidence_ids",
    )
    @classmethod
    def normalize_context_values(cls, values: list[str]) -> list[str]:
        normalized = sorted(
            {
                _safe_handoff_text(value, max_length=512)
                for value in values
                if str(value or "").strip()
            }
        )
        return normalized

    @field_validator("source_evidence_ids")
    @classmethod
    def validate_context_evidence_ids(cls, values: list[str]) -> list[str]:
        if any(
            re.fullmatch(r"ev:[A-Z0-9_]+:[a-f0-9]{32}", value) is None
            for value in values
        ):
            raise ValueError("Jira/PR context must use canonical evidence IDs")
        return values


class GitHubImplementationInspection(BaseModel):
    """Structured GitHub MCP code-inspection result with no free-form payload."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    pr_diff_refs: list[str] = Field(
        default_factory=list, alias="PR_DIFF", max_length=100
    )
    changed_files: list[str] = Field(
        default_factory=list, alias="CHANGED_FILES", max_length=500
    )
    changed_classes: list[str] = Field(
        default_factory=list, alias="CHANGED_CLASSES", max_length=500
    )
    changed_methods: list[str] = Field(
        default_factory=list, alias="CHANGED_METHODS", max_length=500
    )
    blast_radius_contract: Literal["LEGACY_V1", "VALUE_DATA_STATE_FLOW_V2"] = Field(
        default="LEGACY_V1",
        alias="BLAST_RADIUS_CONTRACT",
    )
    changed_symbols: list[str] = Field(
        default_factory=list, alias="CHANGED_SYMBOLS", max_length=500
    )
    produced_values: list[str] = Field(
        default_factory=list, alias="PRODUCED_VALUES", max_length=500
    )
    state_writes: list[str] = Field(
        default_factory=list, alias="STATE_WRITES", max_length=500
    )
    state_reads: list[str] = Field(
        default_factory=list, alias="STATE_READS", max_length=500
    )
    data_flow_edges: list[str] = Field(
        default_factory=list, alias="DATA_FLOW_EDGES", max_length=1000
    )
    direct_callers: list[str] = Field(
        default_factory=list, alias="DIRECT_CALLERS", max_length=500
    )
    transitive_callers: list[str] = Field(
        default_factory=list, alias="TRANSITIVE_CALLERS", max_length=1000
    )
    upstream_callers: list[str] = Field(
        default_factory=list, alias="UPSTREAM_CALLERS", max_length=500
    )
    downstream_consumers: list[str] = Field(
        default_factory=list, alias="DOWNSTREAM_CONSUMERS", max_length=500
    )
    shared_resolver_usage: list[str] = Field(
        default_factory=list, alias="SHARED_RESOLVER_USAGE", max_length=500
    )
    shared_abstractions: list[str] = Field(
        default_factory=list, alias="SHARED_ABSTRACTIONS", max_length=500
    )
    sibling_implementations: list[str] = Field(
        default_factory=list, alias="SIBLING_IMPLEMENTATIONS", max_length=500
    )
    alternate_entry_points: list[str] = Field(
        default_factory=list, alias="ALTERNATE_ENTRY_POINTS", max_length=500
    )
    output_type_consumers: list[str] = Field(
        default_factory=list, alias="OUTPUT_TYPE_CONSUMERS", max_length=500
    )
    configuration_branches: list[str] = Field(
        default_factory=list, alias="CONFIGURATION_BRANCHES", max_length=500
    )
    feature_flags: list[str] = Field(
        default_factory=list, alias="FEATURE_FLAGS", max_length=500
    )
    role_branches: list[str] = Field(
        default_factory=list, alias="ROLE_BRANCHES", max_length=500
    )
    cross_repo_consumers: list[str] = Field(
        default_factory=list, alias="CROSS_REPO_CONSUMERS", max_length=500
    )
    tests_changed_or_added: list[str] = Field(
        default_factory=list, alias="TESTS_CHANGED_ADDED", max_length=500
    )
    missing_tests: list[str] = Field(
        default_factory=list, alias="MISSING_TESTS", max_length=500
    )
    tests_found: list[str] = Field(
        default_factory=list, alias="TESTS_FOUND", max_length=500
    )
    missing_test_areas: list[str] = Field(
        default_factory=list, alias="MISSING_TEST_AREAS", max_length=500
    )
    uncertain_relationships: list[str] = Field(
        default_factory=list, alias="UNCERTAIN_RELATIONSHIPS", max_length=500
    )
    shared_path_evidence: list[str] = Field(
        default_factory=list, alias="SHARED_PATH_EVIDENCE", max_length=500
    )
    unrelated_path_evidence: list[str] = Field(
        default_factory=list, alias="UNRELATED_PATH_EVIDENCE", max_length=500
    )
    completed_targets: list[GitHubInspectionTarget] = Field(
        default_factory=list, alias="COMPLETED_TARGETS", max_length=20
    )
    target_outcomes: dict[GitHubInspectionTarget, GitHubInspectionOutcome] = Field(
        default_factory=dict, alias="TARGET_OUTCOMES", max_length=20
    )
    negative_search_evidence: dict[GitHubInspectionTarget, list[str]] = Field(
        default_factory=dict,
        alias="NEGATIVE_SEARCH_EVIDENCE",
        max_length=20,
    )
    blast_radius_completed_targets: list[GitHubBlastRadiusTarget] = Field(
        default_factory=list,
        alias="BLAST_RADIUS_COMPLETED_TARGETS",
        max_length=len(GitHubBlastRadiusTarget),
    )
    blast_radius_target_outcomes: dict[
        GitHubBlastRadiusTarget, GitHubInspectionOutcome
    ] = Field(
        default_factory=dict,
        alias="BLAST_RADIUS_TARGET_OUTCOMES",
        max_length=len(GitHubBlastRadiusTarget),
    )
    blast_radius_negative_search_evidence: dict[
        GitHubBlastRadiusTarget, list[str]
    ] = Field(
        default_factory=dict,
        alias="BLAST_RADIUS_NEGATIVE_SEARCH_EVIDENCE",
        max_length=len(GitHubBlastRadiusTarget),
    )

    @field_validator(
        "pr_diff_refs",
        "changed_files",
        "changed_classes",
        "changed_methods",
        "changed_symbols",
        "produced_values",
        "state_writes",
        "state_reads",
        "data_flow_edges",
        "direct_callers",
        "transitive_callers",
        "upstream_callers",
        "downstream_consumers",
        "shared_resolver_usage",
        "shared_abstractions",
        "sibling_implementations",
        "alternate_entry_points",
        "output_type_consumers",
        "configuration_branches",
        "feature_flags",
        "role_branches",
        "cross_repo_consumers",
        "tests_changed_or_added",
        "missing_tests",
        "tests_found",
        "missing_test_areas",
        "uncertain_relationships",
        "shared_path_evidence",
        "unrelated_path_evidence",
    )
    @classmethod
    def normalize_inspection_values(cls, values: list[str]) -> list[str]:
        return sorted(
            {
                _safe_handoff_text(value, max_length=1000)
                for value in values
                if str(value or "").strip()
            }
        )

    @field_validator("completed_targets")
    @classmethod
    def normalize_completed_targets(
        cls, values: list[GitHubInspectionTarget]
    ) -> list[GitHubInspectionTarget]:
        return sorted(set(values), key=lambda value: value.value)

    @model_validator(mode="after")
    def validate_target_outcomes(self) -> "GitHubImplementationInspection":
        if set(self.completed_targets) != set(self.target_outcomes):
            raise ValueError(
                "completed GitHub inspection targets require explicit outcomes"
            )
        self.target_outcomes = dict(
            sorted(self.target_outcomes.items(), key=lambda item: item[0].value)
        )
        normalized_negative: dict[GitHubInspectionTarget, list[str]] = {}
        for target, values in self.negative_search_evidence.items():
            if target not in self.completed_targets:
                raise ValueError(
                    "negative GitHub search evidence must reference a completed target"
                )
            normalized = sorted(
                {
                    _safe_handoff_text(value, max_length=1000)
                    for value in values
                    if str(value or "").strip()
                }
            )
            if normalized:
                normalized_negative[target] = normalized
        self.negative_search_evidence = dict(
            sorted(normalized_negative.items(), key=lambda item: item[0].value)
        )

        evidence_by_target = {
            GitHubInspectionTarget.PR_DIFF: self.pr_diff_refs,
            GitHubInspectionTarget.CHANGED_FILES_CLASSES_METHODS: [
                *self.changed_files,
                *self.changed_classes,
                *self.changed_methods,
            ],
            GitHubInspectionTarget.UPSTREAM_CALLERS: self.upstream_callers,
            GitHubInspectionTarget.DOWNSTREAM_CONSUMERS: self.downstream_consumers,
            GitHubInspectionTarget.SHARED_RESOLVER_USAGE: self.shared_resolver_usage,
            GitHubInspectionTarget.OUTPUT_TYPE_CONSUMERS: self.output_type_consumers,
            GitHubInspectionTarget.CONFIGURATION_BRANCHES: self.configuration_branches,
            GitHubInspectionTarget.FEATURE_FLAGS: self.feature_flags,
            GitHubInspectionTarget.TESTS_CHANGED_ADDED: self.tests_changed_or_added,
            GitHubInspectionTarget.MISSING_TESTS: self.missing_tests,
        }
        for target, outcome in self.target_outcomes.items():
            if (
                outcome == GitHubInspectionOutcome.FOUND
                and not evidence_by_target[target]
            ):
                raise ValueError(
                    f"FOUND GitHub inspection outcome requires evidence for {target.value}"
                )
            if (
                outcome == GitHubInspectionOutcome.NONE_FOUND
                and not self.negative_search_evidence.get(target)
            ):
                raise ValueError(
                    "NONE_FOUND GitHub inspection outcome requires bounded negative "
                    f"search evidence for {target.value}"
                )

        self.blast_radius_completed_targets = sorted(
            set(self.blast_radius_completed_targets), key=lambda value: value.value
        )
        if set(self.blast_radius_completed_targets) != set(
            self.blast_radius_target_outcomes
        ):
            raise ValueError(
                "completed blast-radius targets require explicit outcomes"
            )
        self.blast_radius_target_outcomes = dict(
            sorted(
                self.blast_radius_target_outcomes.items(),
                key=lambda item: item[0].value,
            )
        )
        normalized_blast_negative: dict[GitHubBlastRadiusTarget, list[str]] = {}
        for target, values in self.blast_radius_negative_search_evidence.items():
            if target not in self.blast_radius_completed_targets:
                raise ValueError(
                    "blast-radius negative search evidence requires a completed target"
                )
            normalized = sorted(
                {
                    _safe_handoff_text(value, max_length=1000)
                    for value in values
                    if str(value or "").strip()
                }
            )
            if normalized:
                normalized_blast_negative[target] = normalized
        self.blast_radius_negative_search_evidence = dict(
            sorted(
                normalized_blast_negative.items(),
                key=lambda item: item[0].value,
            )
        )
        if self.blast_radius_contract == "VALUE_DATA_STATE_FLOW_V2" and (
            set(self.blast_radius_completed_targets) != set(GitHubBlastRadiusTarget)
        ):
            raise ValueError(
                "PFIX-05 inspection requires the full value/data/state-flow traversal"
            )
        blast_evidence_by_target = {
            GitHubBlastRadiusTarget.CHANGED_SYMBOLS: self.changed_symbols,
            GitHubBlastRadiusTarget.PRODUCED_VALUES: self.produced_values,
            GitHubBlastRadiusTarget.STATE_WRITES: self.state_writes,
            GitHubBlastRadiusTarget.STATE_READS: self.state_reads,
            GitHubBlastRadiusTarget.DATA_FLOW_EDGES: self.data_flow_edges,
            GitHubBlastRadiusTarget.DIRECT_CALLERS: self.direct_callers,
            GitHubBlastRadiusTarget.TRANSITIVE_CALLERS: self.transitive_callers,
            GitHubBlastRadiusTarget.DOWNSTREAM_CONSUMERS: self.downstream_consumers,
            GitHubBlastRadiusTarget.SHARED_ABSTRACTIONS: self.shared_abstractions,
            GitHubBlastRadiusTarget.SIBLING_IMPLEMENTATIONS: (
                self.sibling_implementations
            ),
            GitHubBlastRadiusTarget.ALTERNATE_ENTRY_POINTS: (
                self.alternate_entry_points
            ),
            GitHubBlastRadiusTarget.CONFIGURATION_BRANCHES: (
                self.configuration_branches
            ),
            GitHubBlastRadiusTarget.FEATURE_FLAGS: self.feature_flags,
            GitHubBlastRadiusTarget.ROLE_BRANCHES: self.role_branches,
            GitHubBlastRadiusTarget.CROSS_REPO_CONSUMERS: self.cross_repo_consumers,
            GitHubBlastRadiusTarget.TESTS_FOUND: (
                self.tests_found or self.tests_changed_or_added
            ),
            GitHubBlastRadiusTarget.MISSING_TEST_AREAS: (
                self.missing_test_areas or self.missing_tests
            ),
            GitHubBlastRadiusTarget.UNCERTAIN_RELATIONSHIPS: (
                self.uncertain_relationships
            ),
        }
        for target, outcome in self.blast_radius_target_outcomes.items():
            if (
                outcome == GitHubInspectionOutcome.FOUND
                and not blast_evidence_by_target[target]
            ):
                raise ValueError(
                    "FOUND blast-radius outcome requires evidence for "
                    f"{target.value}"
                )
            if (
                outcome == GitHubInspectionOutcome.NONE_FOUND
                and not self.blast_radius_negative_search_evidence.get(target)
            ):
                raise ValueError(
                    "NONE_FOUND blast-radius outcome requires bounded negative "
                    f"search evidence for {target.value}"
                )
        return self


class GitHubImplementationVerificationHandoff(BaseModel):
    """Deterministic discovery-to-GitHub-MCP implementation request."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[
        "aem-guides-github-implementation-verification-handoff-v1"
    ] = Field(default=GITHUB_IMPLEMENTATION_HANDOFF_SCHEMA, alias="SCHEMA_VERSION")
    handoff_id: str = Field(
        default="",
        alias="HANDOFF_ID",
        pattern=r"^(?:github-handoff:[a-f0-9]{32})?$",
    )
    question_id: str = Field(alias="QUESTION_ID", pattern=r"^question:[a-f0-9]{32}$")
    hypothesis_id: str = Field(
        alias="HYPOTHESIS_ID", pattern=r"^hypothesis:[a-f0-9]{32}$"
    )
    implementation_question: str = Field(
        alias="IMPLEMENTATION_QUESTION", min_length=1, max_length=1000
    )
    expected_change_surface: list[GitHubExpectedChangeSurface] = Field(
        default_factory=list,
        alias="EXPECTED_CHANGE_SURFACE",
        max_length=20,
    )
    omitted_change_surface_count: int = Field(
        default=0,
        alias="OMITTED_CHANGE_SURFACE_COUNT",
        ge=0,
    )
    symbols_or_paths_if_known: list[str] = Field(
        default_factory=list,
        alias="SYMBOLS_OR_PATHS_IF_KNOWN",
        max_length=200,
    )
    why_code_verification_required: str = Field(
        alias="WHY_CODE_VERIFICATION_REQUIRED", min_length=1, max_length=1000
    )
    jira_pr_context: GitHubImplementationContext = Field(alias="JIRA_PR_CONTEXT")
    trace_id: str = Field(
        default="",
        alias="TRACE_ID",
        pattern=r"^(?:implementation-trace:[a-f0-9]{32})?$",
    )
    inspection_scope: list[GitHubInspectionTarget] = Field(
        default_factory=lambda: sorted(
            GitHubInspectionTarget, key=lambda value: value.value
        ),
        alias="INSPECTION_SCOPE",
        min_length=len(GitHubInspectionTarget),
        max_length=len(GitHubInspectionTarget),
    )
    blast_radius_contract: Literal["LEGACY_V1", "VALUE_DATA_STATE_FLOW_V2"] = Field(
        default="LEGACY_V1",
        alias="BLAST_RADIUS_CONTRACT",
    )
    blast_radius_scope: list[GitHubBlastRadiusTarget] = Field(
        default_factory=lambda: sorted(
            GitHubBlastRadiusTarget, key=lambda value: value.value
        ),
        alias="BLAST_RADIUS_SCOPE",
        min_length=len(GitHubBlastRadiusTarget),
        max_length=len(GitHubBlastRadiusTarget),
    )
    materiality: Literal["P0", "P1"] = Field(default="P1", alias="MATERIALITY")
    authority_subject: Literal[AuthoritySubject.ACTUAL_IMPLEMENTATION] = Field(
        default=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        alias="AUTHORITY_SUBJECT",
    )
    acceptance_authority: Literal[False] = Field(
        default=False, alias="ACCEPTANCE_AUTHORITY"
    )

    @field_validator("implementation_question", "why_code_verification_required")
    @classmethod
    def validate_handoff_text(cls, value: str) -> str:
        return _safe_handoff_text(value)

    @field_validator("symbols_or_paths_if_known")
    @classmethod
    def normalize_symbols_or_paths(cls, values: list[str]) -> list[str]:
        return sorted(
            {
                _safe_handoff_text(value, max_length=1000)
                for value in values
                if str(value or "").strip()
            }
        )

    @field_validator("expected_change_surface")
    @classmethod
    def normalize_change_surfaces(
        cls, values: list[GitHubExpectedChangeSurface]
    ) -> list[GitHubExpectedChangeSurface]:
        return sorted(
            {value.surface_id: value for value in values}.values(),
            key=lambda value: value.surface_id,
        )

    @field_validator("inspection_scope")
    @classmethod
    def require_complete_inspection_scope(
        cls, values: list[GitHubInspectionTarget]
    ) -> list[GitHubInspectionTarget]:
        normalized = sorted(set(values), key=lambda value: value.value)
        if set(normalized) != set(GitHubInspectionTarget):
            raise ValueError(
                "GitHub MCP handoff must request the full inspection scope"
            )
        return normalized

    @field_validator("blast_radius_scope")
    @classmethod
    def require_complete_blast_radius_scope(
        cls, values: list[GitHubBlastRadiusTarget]
    ) -> list[GitHubBlastRadiusTarget]:
        normalized = sorted(set(values), key=lambda value: value.value)
        if set(normalized) != set(GitHubBlastRadiusTarget):
            raise ValueError(
                "GitHub MCP handoff must request the full value/data/state-flow scope"
            )
        return normalized

    @model_validator(mode="after")
    def identify(self) -> "GitHubImplementationVerificationHandoff":
        expected_trace = (
            "implementation-trace:"
            + stable_sha256(
                {
                    "jira_key": self.jira_pr_context.jira_key,
                    "question_id": self.question_id,
                    "hypothesis_id": self.hypothesis_id,
                }
            )[:32]
        )
        if self.trace_id and self.trace_id != expected_trace:
            raise ValueError("TRACE_ID does not match deterministic handoff lineage")
        self.trace_id = expected_trace
        identity = {
            "schema_version": self.schema_version,
            "question_id": self.question_id,
            "hypothesis_id": self.hypothesis_id,
            "implementation_question": self.implementation_question,
            "expected_change_surface": [
                row.model_dump(mode="json") for row in self.expected_change_surface
            ],
            "omitted_change_surface_count": self.omitted_change_surface_count,
            "symbols_or_paths_if_known": self.symbols_or_paths_if_known,
            "why_code_verification_required": self.why_code_verification_required,
            "jira_pr_context": self.jira_pr_context.model_dump(mode="json"),
            "trace_id": self.trace_id,
            "inspection_scope": [row.value for row in self.inspection_scope],
            "materiality": self.materiality,
            "authority_subject": self.authority_subject.value,
            "acceptance_authority": self.acceptance_authority,
        }
        if self.blast_radius_contract == "VALUE_DATA_STATE_FLOW_V2":
            identity.update(
                {
                    "blast_radius_contract": self.blast_radius_contract,
                    "blast_radius_scope": [
                        row.value for row in self.blast_radius_scope
                    ],
                }
            )
        expected_id = f"github-handoff:{stable_sha256(identity)[:32]}"
        if self.handoff_id and self.handoff_id != expected_id:
            raise ValueError("HANDOFF_ID does not match deterministic request")
        self.handoff_id = expected_id
        return self


class GitHubImplementationVerificationResult(BaseModel):
    """Typed GitHub MCP conclusion; authoritative only for implementation."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: Literal[
        "aem-guides-github-implementation-verification-result-v1"
    ] = Field(default=GITHUB_IMPLEMENTATION_RESULT_SCHEMA, alias="SCHEMA_VERSION")
    result_id: str = Field(
        default="",
        alias="RESULT_ID",
        pattern=r"^(?:github-result:[a-f0-9]{32})?$",
    )
    handoff_id: str = Field(
        alias="HANDOFF_ID", pattern=r"^github-handoff:[a-f0-9]{32}$"
    )
    question_id: str = Field(alias="QUESTION_ID", pattern=r"^question:[a-f0-9]{32}$")
    hypothesis_id: str = Field(
        alias="HYPOTHESIS_ID", pattern=r"^hypothesis:[a-f0-9]{32}$"
    )
    trace_id: str = Field(
        alias="TRACE_ID", pattern=r"^implementation-trace:[a-f0-9]{32}$"
    )
    status: GitHubImplementationVerificationStatus = Field(alias="STATUS")
    applicability_rationale: str = Field(
        alias="APPLICABILITY_RATIONALE", min_length=1, max_length=2000
    )
    inspection: GitHubImplementationInspection = Field(alias="INSPECTION")
    verified_context: GitHubImplementationContext = Field(alias="VERIFIED_CONTEXT")
    source_references: list[str] = Field(
        default_factory=list, alias="SOURCE_REFERENCES", max_length=100
    )
    repository_revisions: list[str] = Field(
        default_factory=list, alias="REPOSITORY_REVISIONS", max_length=100
    )
    primary_repository_revision: str = Field(
        default="", alias="PRIMARY_REPOSITORY_REVISION", max_length=64
    )
    authority_subject: Literal[AuthoritySubject.ACTUAL_IMPLEMENTATION] = Field(
        default=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        alias="AUTHORITY_SUBJECT",
    )
    implementation_truth: bool = Field(alias="IMPLEMENTATION_TRUTH")
    acceptance_authority: Literal[False] = Field(
        default=False, alias="ACCEPTANCE_AUTHORITY"
    )

    @field_validator("applicability_rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        return _safe_handoff_text(value, max_length=2000)

    @field_validator("source_references", "repository_revisions")
    @classmethod
    def normalize_result_references(cls, values: list[str]) -> list[str]:
        return sorted(
            {
                _safe_handoff_text(value, max_length=1000)
                for value in values
                if str(value or "").strip()
            }
        )

    @model_validator(mode="after")
    def validate_and_identify(self) -> "GitHubImplementationVerificationResult":
        terminal = {
            GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED,
            GitHubImplementationVerificationStatus.UNRELATED_PATH,
        }
        if self.status in terminal:
            if set(self.inspection.completed_targets) != set(GitHubInspectionTarget):
                raise ValueError(
                    "terminal GitHub implementation result requires the full inspection"
                )
            if (
                not self.source_references
                or not self.repository_revisions
                or not self.primary_repository_revision
            ):
                raise ValueError(
                    "terminal GitHub implementation result requires source and revision proof"
                )
            if any(
                outcome == GitHubInspectionOutcome.UNAVAILABLE
                for outcome in self.inspection.target_outcomes.values()
            ):
                raise ValueError(
                    "terminal GitHub implementation result cannot contain unavailable checks"
                )
            if any(
                outcome == GitHubInspectionOutcome.UNAVAILABLE
                for outcome in self.inspection.blast_radius_target_outcomes.values()
            ):
                raise ValueError(
                    "terminal GitHub implementation result cannot contain unavailable "
                    "blast-radius checks"
                )
        if self.implementation_truth != (self.status in terminal):
            raise ValueError(
                "IMPLEMENTATION_TRUTH is true only for terminal implementation findings"
            )
        if (
            self.status == GitHubImplementationVerificationStatus.SHARED_PATH_CONFIRMED
            and (
                not self.inspection.shared_path_evidence
                or self.inspection.target_outcomes.get(
                    GitHubInspectionTarget.SHARED_RESOLVER_USAGE
                )
                != GitHubInspectionOutcome.FOUND
                or not any(
                    self.inspection.target_outcomes.get(target)
                    == GitHubInspectionOutcome.FOUND
                    for target in (
                        GitHubInspectionTarget.DOWNSTREAM_CONSUMERS,
                        GitHubInspectionTarget.OUTPUT_TYPE_CONSUMERS,
                    )
                )
            )
        ):
            raise ValueError(
                "shared-path confirmation requires a found shared resolver and consumer"
            )
        if self.status == GitHubImplementationVerificationStatus.UNRELATED_PATH and (
            not self.inspection.unrelated_path_evidence
            or self.inspection.target_outcomes.get(
                GitHubInspectionTarget.SHARED_RESOLVER_USAGE
            )
            != GitHubInspectionOutcome.NONE_FOUND
        ):
            raise ValueError(
                "unrelated-path conclusion requires a negative shared-resolver search"
            )
        if (
            self.status == GitHubImplementationVerificationStatus.UNRELATED_PATH
            and self.inspection.blast_radius_contract
            == "VALUE_DATA_STATE_FLOW_V2"
            and self.inspection.blast_radius_target_outcomes.get(
                GitHubBlastRadiusTarget.UNCERTAIN_RELATIONSHIPS
            )
            != GitHubInspectionOutcome.NONE_FOUND
        ):
            raise ValueError(
                "unrelated-path conclusion requires uncertainty to be resolved"
            )
        if any(
            re.fullmatch(r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})", value) is None
            for value in self.repository_revisions
        ):
            raise ValueError(
                "repository revisions must use full immutable commit hashes"
            )
        if self.primary_repository_revision:
            if (
                re.fullmatch(
                    r"(?:[a-fA-F0-9]{40}|[a-fA-F0-9]{64})",
                    self.primary_repository_revision,
                )
                is None
                or self.primary_repository_revision not in self.repository_revisions
            ):
                raise ValueError(
                    "primary repository revision must name one verified commit"
                )
        if self.status in terminal:
            if self.repository_revisions != [self.primary_repository_revision]:
                raise ValueError(
                    "terminal result must bind to exactly one primary repository revision"
                )
            if (
                not self.verified_context.pull_request_references
                or self.source_references
                != self.verified_context.pull_request_references
            ):
                raise ValueError(
                    "terminal source references must match the verified PR context"
                )
        if not set(self.repository_revisions).issubset(
            set(self.verified_context.repository_revisions)
        ):
            raise ValueError(
                "verified result revisions must be retained in its Jira/PR context"
            )
        inspection_identity = self.inspection.model_dump(
            mode="json",
            exclude=(
                _GITHUB_V2_INSPECTION_IDENTITY_FIELDS
                if self.inspection.blast_radius_contract == "LEGACY_V1"
                else None
            ),
        )
        identity = {
            "schema_version": self.schema_version,
            "handoff_id": self.handoff_id,
            "question_id": self.question_id,
            "hypothesis_id": self.hypothesis_id,
            "trace_id": self.trace_id,
            "status": self.status.value,
            "applicability_rationale": self.applicability_rationale,
            "inspection": inspection_identity,
            "verified_context": self.verified_context.model_dump(mode="json"),
            "source_references": self.source_references,
            "repository_revisions": self.repository_revisions,
            "primary_repository_revision": self.primary_repository_revision,
            "authority_subject": self.authority_subject.value,
            "implementation_truth": self.implementation_truth,
            "acceptance_authority": self.acceptance_authority,
        }
        expected_id = f"github-result:{stable_sha256(identity)[:32]}"
        if self.result_id and self.result_id != expected_id:
            raise ValueError("RESULT_ID does not match deterministic result")
        self.result_id = expected_id
        return self


class BehaviorHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str = ""
    statement: str
    state: HypothesisState
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    verification_evidence_ids: list[str] = Field(default_factory=list)
    verification_origin_hypothesis_id: str = Field(
        default="", pattern=r"^(?:hypothesis:[a-f0-9]{32})?$"
    )
    derived_from_question_id: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def identify(self) -> "BehaviorHypothesis":
        self.supporting_evidence_ids = sorted(set(self.supporting_evidence_ids))
        self.contradicting_evidence_ids = sorted(set(self.contradicting_evidence_ids))
        self.verification_evidence_ids = sorted(set(self.verification_evidence_ids))
        if set(self.supporting_evidence_ids) & set(self.contradicting_evidence_ids):
            raise ValueError("one evidence record cannot both support and contradict")
        # FJ-17 verification lineage is an operational sidecar.  Excluding it
        # preserves the pre-FJ-17 semantic hypothesis identity while state and
        # supporting/contradicting evidence continue to seal material changes.
        identity = self.model_dump(
            mode="json",
            exclude={
                "hypothesis_id",
                "verification_evidence_ids",
                "verification_origin_hypothesis_id",
            },
        )
        expected = f"hypothesis:{stable_sha256(identity)[:32]}"
        if self.hypothesis_id and self.hypothesis_id != expected:
            raise ValueError("hypothesis_id does not match deterministic identity")
        self.hypothesis_id = expected
        return self


class DomainImpact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    domain: IssueDomain
    materially_affected_entities: list[str] = Field(default_factory=list)
    observable_outcomes: list[str] = Field(default_factory=list)
    nfr_applicable: bool = False
    nfr_triggers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class CoverageDispositionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition_id: str = ""
    candidate: str
    disposition: CoverageDisposition
    source_fact_ids: list[str] = Field(default_factory=list)
    source_closure_ids: list[str] = Field(default_factory=list)
    source_question_ids: list[str] = Field(default_factory=list)
    source_hypothesis_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def identify(self) -> "CoverageDispositionRecord":
        self.source_fact_ids = sorted(set(self.source_fact_ids))
        self.source_closure_ids = sorted(set(self.source_closure_ids))
        self.source_question_ids = sorted(set(self.source_question_ids))
        self.source_hypothesis_ids = sorted(set(self.source_hypothesis_ids))
        self.evidence_ids = sorted(set(self.evidence_ids))
        identity = self.model_dump(mode="json", exclude={"disposition_id"})
        expected = f"disposition:{stable_sha256(identity)[:32]}"
        if self.disposition_id and self.disposition_id != expected:
            raise ValueError("disposition_id does not match deterministic identity")
        self.disposition_id = expected
        return self


class AcceptanceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str = ""
    statement: str
    contract_mode: ContractMode
    accepted_human_contract: bool = False
    source_fact_ids: list[str] = Field(default_factory=list)
    source_disposition_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    in_scope: bool
    observable: bool
    regression_only: bool = False
    implementation_mechanics_only: bool = False
    exact_values_supported: bool = True
    contradicts_human_contract: bool = False
    unresolved_decision_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identify(self) -> "AcceptanceCandidate":
        self.source_fact_ids = sorted(set(self.source_fact_ids))
        self.source_disposition_ids = sorted(set(self.source_disposition_ids))
        self.evidence_ids = sorted(set(self.evidence_ids))
        self.unresolved_decision_ids = sorted(set(self.unresolved_decision_ids))
        identity = self.model_dump(mode="json", exclude={"candidate_id"})
        expected = f"candidate:{stable_sha256(identity)[:32]}"
        if self.candidate_id and self.candidate_id != expected:
            raise ValueError("candidate_id does not match deterministic identity")
        self.candidate_id = expected
        return self


class CandidateDedupDecision(BaseModel):
    """Auditable merge of candidates proven semantically equivalent."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = ""
    merged_candidate_ids: list[str] = Field(min_length=2)
    surviving_candidate_id: str
    merge_reason: str = Field(min_length=1, max_length=500)
    semantic_equivalence_basis: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "CandidateDedupDecision":
        self.merged_candidate_ids = sorted(set(self.merged_candidate_ids))
        if len(self.merged_candidate_ids) < 2:
            raise ValueError("candidate dedup requires at least two distinct inputs")
        if any(
            re.fullmatch(r"candidate:[a-f0-9]{32}", value) is None
            for value in [*self.merged_candidate_ids, self.surviving_candidate_id]
        ):
            raise ValueError("candidate dedup lineage requires canonical candidate IDs")
        identity = self.model_dump(mode="json", exclude={"decision_id"})
        expected = f"candidate-dedup:{stable_sha256(identity)[:32]}"
        if self.decision_id and self.decision_id != expected:
            raise ValueError("candidate dedup decision ID is not deterministic")
        self.decision_id = expected
        return self


class AcceptanceResolutionBatch(BaseModel):
    """Raw candidates, safe merges, and surviving acceptance candidates."""

    model_config = ConfigDict(extra="forbid")

    discovered_candidates: list[AcceptanceCandidate] = Field(default_factory=list)
    candidates: list[AcceptanceCandidate] = Field(default_factory=list)
    dedup_decisions: list[CandidateDedupDecision] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_lineage(self) -> "AcceptanceResolutionBatch":
        self.discovered_candidates = sorted(
            {row.candidate_id: row for row in self.discovered_candidates}.values(),
            key=lambda row: row.candidate_id,
        )
        self.candidates = sorted(
            {row.candidate_id: row for row in self.candidates}.values(),
            key=lambda row: row.candidate_id,
        )
        self.dedup_decisions = sorted(
            {row.decision_id: row for row in self.dedup_decisions}.values(),
            key=lambda row: row.decision_id,
        )
        discovered_ids = {row.candidate_id for row in self.discovered_candidates}
        surviving_ids = {row.candidate_id for row in self.candidates}
        merged_members: dict[str, str] = {}
        for decision in self.dedup_decisions:
            if decision.surviving_candidate_id not in surviving_ids:
                raise ValueError("candidate dedup survivor is absent from final candidates")
            for candidate_id in decision.merged_candidate_ids:
                if candidate_id not in discovered_ids:
                    raise ValueError("candidate dedup references an undiscovered candidate")
                if candidate_id in merged_members:
                    raise ValueError("one discovered candidate cannot enter multiple merges")
                merged_members[candidate_id] = decision.decision_id
        unaccounted = sorted(discovered_ids - surviving_ids - set(merged_members))
        if unaccounted:
            raise ValueError(
                "discovered acceptance candidates were silently lost: "
                + ", ".join(unaccounted)
            )
        unexpected_survivors = sorted(
            surviving_ids - discovered_ids - {
                row.surviving_candidate_id for row in self.dedup_decisions
            }
        )
        if unexpected_survivors:
            raise ValueError(
                "final acceptance candidates lack discovery or merge lineage: "
                + ", ".join(unexpected_survivors)
            )
        return self


class AcceptancePromotionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    status: PromotionStatus
    resulting_disposition: CoverageDisposition
    authority_supported: bool
    scope_established: bool
    observable: bool
    exact_values_supported: bool
    contradicts_human_contract: bool = False
    reasons: list[str] = Field(default_factory=list)


class CandidateLifecycleRecord(BaseModel):
    """One discovered material candidate's path to a terminal disposition."""

    model_config = ConfigDict(extra="forbid")

    lifecycle_id: str = ""
    discovered_candidate_id: str
    canonical_candidate_id: str
    stages: list[CandidateLifecycleStage]
    evidence_required: bool
    evidence_collected: bool
    final_disposition: CandidateTerminalDisposition
    promotion_status: PromotionStatus
    dedup_decision_id: str = ""

    @model_validator(mode="after")
    def validate_and_identify(self) -> "CandidateLifecycleRecord":
        expected_order = [
            CandidateLifecycleStage.CANDIDATE_DISCOVERED,
            CandidateLifecycleStage.APPLICABILITY_EVALUATED,
            CandidateLifecycleStage.EVIDENCE_COLLECTED,
            CandidateLifecycleStage.FINAL_DISPOSITION,
        ]
        if len(self.stages) != len(set(self.stages)):
            raise ValueError("candidate lifecycle stages cannot repeat")
        if not self.stages or self.stages[0] != expected_order[0]:
            raise ValueError("candidate lifecycle must start at discovery")
        if self.stages[-1] != CandidateLifecycleStage.FINAL_DISPOSITION:
            raise ValueError("candidate lifecycle requires a final disposition")
        if self.stages != [stage for stage in expected_order if stage in self.stages]:
            raise ValueError("candidate lifecycle stages are out of order")
        if self.evidence_collected != (
            CandidateLifecycleStage.EVIDENCE_COLLECTED in self.stages
        ):
            raise ValueError("candidate evidence state must match its lifecycle stage")
        if any(
            re.fullmatch(r"candidate:[a-f0-9]{32}", value) is None
            for value in [self.discovered_candidate_id, self.canonical_candidate_id]
        ):
            raise ValueError("candidate lifecycle requires canonical candidate IDs")
        if self.dedup_decision_id and re.fullmatch(
            r"candidate-dedup:[a-f0-9]{32}", self.dedup_decision_id
        ) is None:
            raise ValueError("candidate lifecycle has an invalid dedup decision ID")
        identity = self.model_dump(mode="json", exclude={"lifecycle_id"})
        expected = f"candidate-lifecycle:{stable_sha256(identity)[:32]}"
        if self.lifecycle_id and self.lifecycle_id != expected:
            raise ValueError("candidate lifecycle ID is not deterministic")
        self.lifecycle_id = expected
        return self


class RendererProjectionDecision(BaseModel):
    """Proof that one finalized candidate reached its rendered section."""

    model_config = ConfigDict(extra="forbid")

    projection_id: str = ""
    discovered_candidate_id: str
    canonical_candidate_id: str
    final_disposition: CandidateTerminalDisposition
    section_key: str = Field(min_length=1, max_length=100)
    rendered: Literal[True] = True
    source_record_ids: list[str] = Field(default_factory=list)
    dedup_decision_id: str = ""

    @model_validator(mode="after")
    def normalize_and_identify(self) -> "RendererProjectionDecision":
        self.source_record_ids = sorted(set(self.source_record_ids))
        if self.discovered_candidate_id not in self.source_record_ids:
            raise ValueError("renderer decision must retain discovered candidate lineage")
        if self.canonical_candidate_id not in self.source_record_ids:
            raise ValueError("renderer decision must retain canonical candidate lineage")
        identity = self.model_dump(mode="json", exclude={"projection_id"})
        expected = f"renderer-projection:{stable_sha256(identity)[:32]}"
        if self.projection_id and self.projection_id != expected:
            raise ValueError("renderer projection ID is not deterministic")
        self.projection_id = expected
        return self


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: CanonicalRuntimeStage
    status: GateStatus
    failures: list[str] = Field(default_factory=list)
    checked_ids: list[str] = Field(default_factory=list)


class PlanSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: str
    title: str
    items: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)


class StructuredQEPlan(BaseModel):
    """Lossless pre-render plan.  Every material disposition remains addressable."""

    model_config = ConfigDict(extra="forbid")

    jira_key: str
    contract_mode: ContractMode
    sections: list[PlanSection] = Field(default_factory=list)
    contract_fact_ids: list[str] = Field(default_factory=list)
    closure_ids: list[str] = Field(default_factory=list)
    coverage_disposition_ids: list[str] = Field(default_factory=list)
    promoted_candidate_ids: list[str] = Field(default_factory=list)
    open_question_ids: list[str] = Field(default_factory=list)
    candidate_lifecycle: list[CandidateLifecycleRecord] = Field(default_factory=list)
    dedup_decisions: list[CandidateDedupDecision] = Field(default_factory=list)
    renderer_decisions: list[RendererProjectionDecision] = Field(default_factory=list)
    gate_decisions: list[GateDecision] = Field(default_factory=list)


class RuntimeStageTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: CanonicalRuntimeStage
    sequence: int = Field(ge=1)
    started_at: str
    completed_at: str
    duration_ms: float = Field(ge=0.0)
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["completed", "failed", "blocked"]
    item_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)


class EvidenceUsageTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    lifecycle_status: EvidenceLifecycleStatus
    inspected: bool
    used: bool
    rejected_reason: str = ""


class QuestionGenerationTraceStep(BaseModel):
    """Content-minimal lineage for one question-generation diagnostic substage."""

    model_config = ConfigDict(extra="forbid")

    stage: QuestionGenerationTraceStage
    sequence: int = Field(ge=1, le=len(QUESTION_GENERATION_TRACE_ORDER))
    outcome: QuestionGenerationStepOutcome
    input_ids: list[str] = Field(default_factory=list)
    output_ids: list[str] = Field(default_factory=list)
    failure_reason: QuestionGenerationFailureReason | None = None
    detail_code: str = Field(default="", max_length=96)

    @field_validator("input_ids", "output_ids")
    @classmethod
    def normalize_ids(cls, values: list[str]) -> list[str]:
        return sorted({str(value).strip() for value in values if str(value).strip()})


class QuestionGenerationDiagnosticTrace(BaseModel):
    """Raw, ordered lineage used to localize a missing material question."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-question-generation-diagnostic-v1"] = (
        "aem-guides-question-generation-diagnostic-v1"
    )
    steps: list[QuestionGenerationTraceStep] = Field(default_factory=list)
    earliest_failure: QuestionGenerationFailureReason | None = None
    recovered_failure: QuestionGenerationFailureReason | None = None
    governing_pattern_ids: list[str] = Field(default_factory=list)
    pattern_provider_status: PatternLookupRuntimeStatus | None = None
    matched_human_pattern_ids: list[str] = Field(default_factory=list)
    mandatory_family_ids: list[SemanticDimension] = Field(default_factory=list)
    family_activation_decisions: dict[SemanticDimension, FamilyActivationDecision] = (
        Field(default_factory=dict)
    )
    fluffyjaws_independent: Literal[True] = True

    @model_validator(mode="after")
    def validate_order_and_failure(self) -> "QuestionGenerationDiagnosticTrace":
        observed = [row.stage for row in self.steps]
        if observed != list(QUESTION_GENERATION_TRACE_ORDER[: len(observed)]):
            raise ValueError(
                "question-generation diagnostics are not the ordered trace prefix"
            )
        if [row.sequence for row in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError(
                "question-generation diagnostic sequence is not contiguous"
            )
        failures = [row.failure_reason for row in self.steps if row.failure_reason]
        if self.earliest_failure != (failures[0] if failures else None):
            raise ValueError(
                "earliest_failure must match the first failed diagnostic step"
            )
        self.governing_pattern_ids = sorted(set(self.governing_pattern_ids))
        self.matched_human_pattern_ids = sorted(set(self.matched_human_pattern_ids))
        self.mandatory_family_ids = sorted(
            set(self.mandatory_family_ids), key=lambda row: row.value
        )
        self.family_activation_decisions = dict(
            sorted(
                self.family_activation_decisions.items(),
                key=lambda item: item[0].value,
            )
        )
        return self


class RuntimeTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: Literal["aem-guides-test-plan-runtime"] = CANONICAL_RUNTIME_ID
    runtime_version: Literal["2.0.0"] = CANONICAL_RUNTIME_VERSION
    run_id: str = Field(min_length=1)
    request_id: str
    entry_point: RuntimeEntryPoint
    generation_profile: GenerationProfile
    evidence_bundle_id: str
    started_at: str
    completed_at: str
    stage_trace: list[RuntimeStageTrace] = Field(default_factory=list)
    consumed_evidence_ids: list[str] = Field(default_factory=list)
    evidence_usage_trace: list[EvidenceUsageTrace] = Field(default_factory=list)
    question_generation_trace: QuestionGenerationDiagnosticTrace | None = None
    qe_investigation: QeInvestigationPreparation | None = None
    missing_question_quality: MissingQuestionQualityReport | None = None
    missing_question_resolutions: list[MissingQuestionResolutionRecord] = Field(
        default_factory=list
    )
    source_counts: dict[str, int] = Field(default_factory=dict)
    compatibility_projection: list[CompatibilityProjectionLink] = Field(
        default_factory=list
    )
    compatibility_adapter: str = ""
    deprecated_path: bool = False
    quality_gate: str = ""
    warnings: list[str] = Field(default_factory=list)
    authoritative_facts_extracted: list[str] = Field(default_factory=list)
    authoritative_facts_preserved: list[str] = Field(default_factory=list)
    primary_entities: list[str] = Field(default_factory=list)
    graph_nodes_visited: list[str] = Field(default_factory=list)
    edges_visited: list[str] = Field(default_factory=list)
    edges_rejected: list[str] = Field(default_factory=list)
    semantic_dimensions_considered: list[str] = Field(default_factory=list)
    second_pass_retrievals: list[str] = Field(default_factory=list)
    implementation_verification_handoff_ids: list[str] = Field(default_factory=list)
    implementation_verification_result_ids: list[str] = Field(default_factory=list)
    unresolved_implementation_handoff_ids: list[str] = Field(default_factory=list)
    hypotheses_confirmed: list[str] = Field(default_factory=list)
    hypotheses_rejected: list[str] = Field(default_factory=list)
    hypotheses_unresolved: list[str] = Field(default_factory=list)
    ac_candidates: list[str] = Field(default_factory=list)
    candidate_lifecycle_ids: list[str] = Field(default_factory=list)
    candidate_dedup_decision_ids: list[str] = Field(default_factory=list)
    renderer_projection_ids: list[str] = Field(default_factory=list)
    regression_candidates: list[str] = Field(default_factory=list)
    promotion_rejections: list[str] = Field(default_factory=list)
    gate_failures: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_stage_order(self) -> "RuntimeTrace":
        observed = [row.stage for row in self.stage_trace]
        expected_prefix = list(CANONICAL_STAGE_ORDER[: len(observed)])
        if observed != expected_prefix:
            raise ValueError("runtime stage trace is not the canonical ordered prefix")
        if [row.sequence for row in self.stage_trace] != list(
            range(1, len(self.stage_trace) + 1)
        ):
            raise ValueError("runtime stage trace sequence is not contiguous")
        return self


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["aem-guides-generation-result-v2"] = (
        GENERATION_RESULT_SCHEMA
    )
    runtime_id: Literal["aem-guides-test-plan-runtime"] = CANONICAL_RUNTIME_ID
    runtime_version: Literal["2.0.0"] = CANONICAL_RUNTIME_VERSION
    run_id: str = Field(min_length=1)
    request_id: str
    evidence_bundle_id: str
    evidence_bundle: CanonicalEvidenceBundle
    status: Literal["completed", "needs_human_review", "blocked", "failed"]
    output_contract: str
    output_kind: Literal["test_plan", "pipeline_compatibility", "packet_compatibility"]
    output_payload: dict[str, Any] = Field(default_factory=dict)
    rendered_output: str = ""
    structured_output: dict[str, Any] = Field(default_factory=dict)
    structured_plan: StructuredQEPlan | None = None
    gate_decisions: list[GateDecision] = Field(default_factory=list)
    output_sha256: str = Field(default="", pattern=r"^$|^[a-f0-9]{64}$")
    validation_status: Literal["passed", "failed", "not_run", "legacy_advisory"] = (
        "not_run"
    )
    validation_result: dict[str, Any] = Field(default_factory=dict)
    runtime_warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    trace: RuntimeTrace

    @model_validator(mode="after")
    def identify_output(self) -> "GenerationResult":
        if "plan_markdown" in self.output_payload:
            if self.structured_output != self.output_payload:
                raise ValueError(
                    "structured output must match the canonical output payload"
                )
            if self.rendered_output != self.output_payload.get("plan_markdown"):
                raise ValueError("rendered output must match canonical plan_markdown")
            if self.structured_plan is None or self.output_payload.get(
                "structured_plan"
            ) != self.structured_plan.model_dump(mode="json"):
                raise ValueError(
                    "structured plan must match the canonical output payload"
                )
        expected = stable_sha256(self.output_payload)
        if self.output_sha256 and self.output_sha256 != expected:
            raise ValueError("output_sha256 does not match output payload")
        self.output_sha256 = expected
        if self.trace.request_id != self.request_id:
            raise ValueError("trace request does not match result request")
        if self.trace.run_id != self.run_id:
            raise ValueError("trace run does not match result run")
        if self.trace.evidence_bundle_id != self.evidence_bundle_id:
            raise ValueError("trace evidence bundle does not match result")
        if self.evidence_bundle.bundle_id != self.evidence_bundle_id:
            raise ValueError("embedded evidence bundle does not match result")
        return self


__all__ = [
    "AcceptanceCandidate",
    "AcceptanceResolutionBatch",
    "AcceptancePromotionDecision",
    "AbstractSignal",
    "AbstractSignalKind",
    "ApplicabilityState",
    "AuthorityClass",
    "AuthorityResolution",
    "AuthoritySubject",
    "BehaviorGraph",
    "BehaviorGraphEdge",
    "BehaviorGraphNode",
    "BehaviorHypothesis",
    "BehaviorRelationType",
    "CANONICAL_RUNTIME_ID",
    "CANONICAL_RUNTIME_VERSION",
    "CANONICAL_STAGE_ORDER",
    "CanonicalBehaviorModel",
    "CanonicalEvidenceBundle",
    "CanonicalRuntimeStage",
    "CandidateDedupDecision",
    "CandidateLifecycleRecord",
    "CandidateLifecycleStage",
    "CandidateTerminalDisposition",
    "ChangeSurface",
    "ChangeSurfaceKind",
    "ClosureDimensionResult",
    "CompatibilityProjectionLink",
    "ContractFact",
    "ContractFactSet",
    "ContractFactType",
    "ContractMode",
    "ContractPreservationState",
    "CoverageDisposition",
    "CoverageDispositionRecord",
    "CurrentnessState",
    "DirectedRetrievalRecord",
    "DitaOtProcessingState",
    "DomainActivation",
    "DomainImpact",
    "EvidenceDirectness",
    "EvidenceConfidenceLevel",
    "EvidenceLifecycleStatus",
    "EvidenceRecord",
    "EvidenceSourceType",
    "EvidenceUsageTrace",
    "FeedbackClassification",
    "GenerationProfile",
    "GenerationRequest",
    "GenerationResult",
    "GeneratedOutputOracle",
    "GateDecision",
    "GateStatus",
    "ClaudeMissingQuestionSubmission",
    "GITHUB_IMPLEMENTATION_HANDOFF_SCHEMA",
    "GITHUB_IMPLEMENTATION_RESULT_SCHEMA",
    "GitHubBlastRadiusTarget",
    "GitHubExpectedChangeSurface",
    "GitHubImplementationContext",
    "GitHubImplementationInspection",
    "GitHubImplementationVerificationHandoff",
    "GitHubImplementationVerificationResult",
    "GitHubImplementationVerificationStatus",
    "GitHubInspectionOutcome",
    "GitHubInspectionTarget",
    "HypothesisState",
    "HumanQuestionClass",
    "IssueDomain",
    "InvestigationFamilySourceContribution",
    "InvestigationFamilySourceKind",
    "InvestigationFamilySatisfaction",
    "InvestigationFamilySatisfactionStatus",
    "InvestigationMateriality",
    "FamilyActivationDecision",
    "InvestigationRetrievalHint",
    "LifecycleState",
    "LifecycleOperation",
    "LegacyCompatibilityProjection",
    "PipelineCompatibilityOptions",
    "PlanSection",
    "PromotionStatus",
    "ProductContractOwnership",
    "ProductOwnership",
    "PublishingTransformationStage",
    "QuestionGenerationDiagnosticTrace",
    "QuestionGenerationFailureReason",
    "QuestionGenerationStepOutcome",
    "QuestionGenerationTraceStep",
    "QuestionGenerationTraceStage",
    "QuestionEvidenceProvider",
    "QuestionValidationDisposition",
    "QUESTION_GENERATION_TRACE_ORDER",
    "ReasoningPatternActivation",
    "ReasoningQuestionFamily",
    "ResolutionState",
    "RuntimeEntryPoint",
    "RuntimePrincipal",
    "RuntimeStageTrace",
    "RuntimeTrace",
    "ScopeResolution",
    "SemanticDimension",
    "ClosureDisposition",
    "MissingQuestion",
    "MissingQuestionOrigin",
    "MissingQuestionQualityDecision",
    "MissingQuestionQualityFailureReason",
    "MissingQuestionQualityReport",
    "MissingQuestionResolutionRecord",
    "MissingQuestionResolutionStatus",
    "MandatoryInvestigationFamily",
    "MatchedHumanPatternView",
    "CurrentPatternApplicability",
    "PatternApplicabilityRecord",
    "PatternLookupCallRecord",
    "PatternLookupResult",
    "PatternLookupRuntimeStatus",
    "PatternSuggestionState",
    "QeInvestigationConstraints",
    "QeInvestigationPreparation",
    "RetrievalStatus",
    "RendererProjectionDecision",
    "SourceVisibility",
    "SourceManifestEntry",
    "UserFeedbackCandidate",
    "UiApplicability",
    "StructuredQEPlan",
    "VerificationState",
    "VersionScope",
    "VisibilityClass",
    "canonical_json",
    "stable_sha256",
]
