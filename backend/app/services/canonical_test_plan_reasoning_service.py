"""Deterministic, stage-owned reasoning for the canonical Test Plan runtime.

The service contains no entry-point routing and no arbitrary generation hook.
It converts normalized evidence into typed intermediate records.  The runtime
calls these methods in the one fixed order declared by ``CANONICAL_STAGE_ORDER``.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Mapping

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptanceResolutionBatch,
    AcceptancePromotionDecision,
    AbstractSignal,
    AbstractSignalKind,
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorGraph,
    BehaviorGraphEdge,
    BehaviorGraphNode,
    BehaviorHypothesis,
    BehaviorRelationType,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    CandidateDedupDecision,
    CandidateLifecycleRecord,
    CandidateLifecycleStage,
    CandidateTerminalDisposition,
    ChangeSurface,
    ChangeSurfaceKind,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    ContractPreservationState,
    CoverageDisposition,
    CoverageDispositionRecord,
    CurrentnessState,
    DirectedRetrievalRecord,
    DitaOtProcessingState,
    DomainActivation,
    DomainImpact,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    FamilyActivationDecision,
    GateDecision,
    GateStatus,
    GeneratedOutputOracle,
    GenerationRequest,
    HypothesisState,
    IssueDomain,
    InvestigationFamilySatisfactionStatus,
    LifecycleOperation,
    MandatoryInvestigationFamily,
    MissingQuestion,
    MissingQuestionQualityReport,
    PlanSection,
    PromotionStatus,
    PublishingTransformationStage,
    QeInvestigationPreparation,
    QuestionGenerationDiagnosticTrace,
    QuestionGenerationFailureReason,
    QuestionGenerationStepOutcome,
    QuestionGenerationTraceStep,
    QuestionGenerationTraceStage,
    ReasoningPatternActivation,
    ReasoningQuestionFamily,
    RendererProjectionDecision,
    RetrievalStatus,
    ScopeResolution,
    SemanticDimension,
    StructuredQEPlan,
    VerificationState,
    stable_sha256,
)
from app.services.canonical_evidence_service import record_visible_to
from app.services.reasoning_evidence_provider import (
    AuthorizedSemanticEvidence,
    QuestionEvidenceStance,
)
from app.services.github_implementation_verification import (
    is_github_implementation_result_record,
)


_ACCEPTED_AUTHORITIES = {
    AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
    AuthorityClass.CONFIRMED_PRODUCT_DECISION,
}
_CONTRACT_AUTHORITIES = _ACCEPTED_AUTHORITIES | {
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.CUSTOMER_REQUEST,
}
_HUMAN_CONTRACT_SOURCES = {
    EvidenceSourceType.ACCEPTED_UAC,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.PRODUCT_DECISION,
}
_IMPLEMENTATION_SOURCES = {
    EvidenceSourceType.CURRENT_CODE,
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.CODE_DIFF,
    EvidenceSourceType.EXISTING_AUTOMATION,
}
_UI_SOURCES = {
    EvidenceSourceType.UI_OBSERVATION,
    EvidenceSourceType.OBSERVED_UI_FLOW,
    EvidenceSourceType.SCREENSHOT_REPRODUCTION,
}
_CURRENT_ISSUE_BEHAVIOR_SOURCES = {
    EvidenceSourceType.CURRENT_JIRA,
    EvidenceSourceType.JIRA_DESCRIPTION,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.CUSTOMER_REQUEST,
    EvidenceSourceType.CUSTOMER_WORKFLOW,
    EvidenceSourceType.BENCHMARK_PUBLIC_INPUT,
}
_SEMANTIC_HANDOFF_AUTHORITIES = {
    AuthorityClass.OFFICIAL_PRODUCT_CONTRACT,
    AuthorityClass.SPECIFICATION_AUTHORITY,
    AuthorityClass.IMPLEMENTATION_CONFIRMED,
}

_DOMAIN_SIGNALS: dict[IssueDomain, tuple[str, ...]] = {
    IssueDomain.PUBLISHING: (
        "publish",
        "output preset",
        "native pdf",
        "html5",
        "aem sites",
        "dita-ot",
        "dita ot",
        "generated page",
    ),
    IssueDomain.AUTHORING: (
        "authoring",
        "web editor",
        "editor",
        "full tags",
        "right panel",
    ),
    IssueDomain.CONTENT_MANAGEMENT: (
        "content management",
        "repository",
        "asset",
        "move asset",
        "rename asset",
        "delete asset",
        "move folder",
        "rename folder",
        "delete folder",
    ),
    IssueDomain.SEARCH_QUERY: (
        "query builder",
        "oak",
        "query engine",
        "search",
        "query",
    ),
    IssueDomain.WORKFLOW_JOB: ("workflow", "job", "queue", "executor", "scheduler"),
    IssueDomain.MIGRATION: ("migration", "migrate", "upgrade", "import"),
    IssueDomain.PERFORMANCE: (
        "performance",
        "bulk",
        "scale",
        "thousand",
        "concurrent",
        "large collection",
    ),
    IssueDomain.TRANSLATION: ("translation", "localization", "locale", "language copy"),
    IssueDomain.BASELINE: ("baseline", "version label"),
    IssueDomain.ASSETS: ("aem assets", "dam", "asset metadata"),
    IssueDomain.EXTENSION_FRAMEWORK: (
        "extension",
        "plugin",
        "customization",
        "extensibility",
    ),
    IssueDomain.API: (
        "api",
        "apis",
        "endpoint",
        "rest ",
        "request payload",
        "response code",
    ),
}

_OUT_OF_SCOPE_CLAUSE_RE = re.compile(
    r"\b(?:out\s+of\s+scope|not\s+in\s+scope|excluded\s+from\s+scope|"
    r"not\s+applicable|does\s+not\s+apply)\b",
    re.IGNORECASE,
)

_GENERATED_ARTIFACT_DELIVERY_SIGNALS = (
    "generate output",
    "output generation",
    "generated output",
    "generated artifact",
    "generated page",
    "publishing workflow",
    "publish job",
    "republish",
    "post generation",
    "output path",
    "download",
    "activation",
    "publication",
)

_CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE = re.compile(
    r"\bpublish(?:ed|es|ing)?\b.{0,40}"
    r"\b(?:documents?|pages?|maps?|topics?|outputs?|artifacts?|pdfs?|sites?)\b"
    r"|\b(?:documents?|pages?|maps?|topics?|outputs?|artifacts?|pdfs?|sites?)\b"
    r".{0,40}\bpublish(?:ed|es|ing)?\b",
    re.IGNORECASE,
)

_PUBLISHING_CONFIGURATION_ONLY_SIGNALS = (
    "configuration only",
    "ui only",
    "preset editor",
    "preset dialog",
    "field label",
    "dropdown",
)

_CONTENT_LIFECYCLE_RE = re.compile(
    r"(?:\b(?:move|rename|delete)(?:d|s|ing)?\b.{0,30}"
    r"\b(?:asset|file|folder|topic|map|repository|content)\b|"
    r"\b(?:asset|file|folder|topic|map|repository|content)\b.{0,30}"
    r"\b(?:move|rename|delete)(?:d|s|ing)?\b)",
    re.IGNORECASE,
)

_IMPLEMENTATION_MECHANICS_RE = re.compile(
    r"(?:\b(?:fix|implementation|internal code|method|class|handler|worker|service)\b"
    r".{0,40}\b(?:use|uses|using|invoke|call|implement|store)\b|"
    r"\b(?:hashmap|concurrenthashmap|keyset pagination|custom index|"
    r"internal api version|framework status|incidental code constant)\b|"
    r"\b(?:implementation|engineering|code)\s+(?:detail|details|mechanic|mechanics|choice|choices)\b|"
    r"\b[A-Z][A-Za-z0-9_$]+\.[a-z][A-Za-z0-9_$]*\s*\()",
    re.IGNORECASE,
)

_REGRESSION_ONLY_RE = re.compile(
    r"\b(?:regression\s+(?:coverage|check|test|retest)|retest\s+only|"
    r"(?:qa|test|automation)\s+suite\s+(?:should\s+|must\s+)?"
    r"(?:continue\s+)?(?:cover|verify|validate|test|retest)(?:s|ed|ing)?|"
    r"automated\s+tests?\s+(?:should\s+|must\s+)?"
    r"(?:continue\s+to\s+)?(?:cover|verify|validate|test|retest)(?:s|ed|ing)?)\b",
    re.IGNORECASE,
)

_NON_BEHAVIOR_CHANGE_RE = re.compile(
    r"\b(?:no|without)\s+(?:user[- ]visible|observable|product)\s+"
    r"behavio(?:u)?r\s+change\b|"
    r"\b(?:internal|code[- ]only|test[- ]only)\s+refactor(?:ing)?\b|"
    r"\brefactor(?:ing)?\s+only\b",
    re.IGNORECASE,
)

_SUMMARY_REFERENCE_RE = re.compile(r"(?:^|[.:$])(?:summary|title)$", re.IGNORECASE)

_DIMENSION_KEYWORDS: dict[SemanticDimension, tuple[str, ...]] = {
    SemanticDimension.GOVERNING_SEMANTICS: ("semantic", "specification", "defined"),
    SemanticDimension.CONTROLLING_ATTRIBUTES: ("attribute", "property", "flag"),
    SemanticDimension.GOVERNING_CONFIGURATION: (
        "config",
        "setting",
        "profile",
        "preset",
    ),
    SemanticDimension.DIRECT_CONSUMERS: ("consumer", "reader", "uses", "read"),
    SemanticDimension.SIBLING_CONSUMERS: ("sibling", "other consumer", "shared"),
    SemanticDimension.ALTERNATE_MECHANISMS: (
        "alternate",
        "alternative",
        "another mechanism",
    ),
    SemanticDimension.PARENT_CONTEXT: ("parent", "containing"),
    SemanticDimension.CHILD_CONTEXT: ("child", "nested"),
    SemanticDimension.HIERARCHY: ("hierarchy", "ancestor", "descendant"),
    SemanticDimension.SPECIALIZATIONS: ("specialization", "specialized", "bookmap"),
    SemanticDimension.REFERENCED_CONTENT: ("reference", "mapref", "topicref", "link"),
    SemanticDimension.NESTED_REFERENCED_CONTENT: ("nested map", "nested reference"),
    SemanticDimension.ALTERNATE_REPRESENTATION: (
        "alternate representation",
        "fallback title",
    ),
    SemanticDimension.FALLBACK: ("fallback", "raw name", "default behavior"),
    SemanticDimension.ABSENT_VALUE: ("missing", "absent", "not configured", "empty"),
    SemanticDimension.INVALID_VALUE: ("invalid", "unsupported", "malformed"),
    SemanticDimension.POSITIVE_STATE: ("enabled", "selected", "present", "success"),
    SemanticDimension.NEGATIVE_STATE: (
        "disabled",
        "not selected",
        "failure",
        "removed",
    ),
    SemanticDimension.LIFECYCLE: (
        "update",
        "delete",
        "move",
        "rename",
        "regenerate",
        "refresh",
    ),
    SemanticDimension.CROSS_SURFACE_SYNC: (
        "automatically",
        "without reload",
        "sync",
        "all views",
    ),
    SemanticDimension.DOWNSTREAM_PROCESSOR: ("processor", "transformer", "downstream"),
    SemanticDimension.GENERATED_OUTPUT: ("generated", "output", "artifact", "page"),
    SemanticDimension.PERSISTED_STATE: ("persist", "repository state", "stored", "cq:"),
    SemanticDimension.VERSION_APPLICABILITY: (
        "version",
        "upgrade",
        "backward compatible",
    ),
    SemanticDimension.DEPLOYMENT_APPLICABILITY: ("on-prem", "cloud", "deployment"),
    SemanticDimension.ROLE_PROFILE_APPLICABILITY: (
        "user",
        "role",
        "profile",
        "permission",
    ),
}

_QUESTION_TEXT: dict[SemanticDimension, str] = {
    SemanticDimension.GOVERNING_SEMANTICS: "What product or DITA rule governs {entity}?",
    SemanticDimension.CONTROLLING_ATTRIBUTES: "Which attributes control {entity}?",
    SemanticDimension.GOVERNING_CONFIGURATION: "Which configuration controls {entity}?",
    SemanticDimension.DIRECT_CONSUMERS: "Which consumers read or use {entity}?",
    SemanticDimension.SIBLING_CONSUMERS: "Which other consumers use the same source as {entity}?",
    SemanticDimension.ALTERNATE_MECHANISMS: "Does another supported mechanism provide {entity}?",
    SemanticDimension.PARENT_CONTEXT: "Can {entity} occur in a parent context?",
    SemanticDimension.CHILD_CONTEXT: "Can {entity} occur under child or nested content?",
    SemanticDimension.HIERARCHY: "How does hierarchy affect {entity}?",
    SemanticDimension.SPECIALIZATIONS: "Are specialized forms handled by the same path as {entity}?",
    SemanticDimension.REFERENCED_CONTENT: "Can referenced content reach {entity}?",
    SemanticDimension.NESTED_REFERENCED_CONTENT: "Can nested referenced content reach {entity}?",
    SemanticDimension.ALTERNATE_REPRESENTATION: "Is there another representation of {entity}?",
    SemanticDimension.FALLBACK: "What fallback is used for {entity}?",
    SemanticDimension.ABSENT_VALUE: "What happens when the value for {entity} is absent?",
    SemanticDimension.INVALID_VALUE: "What happens when the value for {entity} is invalid?",
    SemanticDimension.POSITIVE_STATE: "What is the expected enabled state for {entity}?",
    SemanticDimension.NEGATIVE_STATE: "What is the expected disabled or failure state for {entity}?",
    SemanticDimension.LIFECYCLE: "Which lifecycle operations affect {entity}?",
    SemanticDimension.CROSS_SURFACE_SYNC: "Which surfaces must stay synchronized for {entity}?",
    SemanticDimension.DOWNSTREAM_PROCESSOR: "Which downstream processor consumes {entity}?",
    SemanticDimension.GENERATED_OUTPUT: "Which generated output proves {entity} is correct?",
    SemanticDimension.PERSISTED_STATE: "Which persisted state is written or read for {entity}?",
    SemanticDimension.VERSION_APPLICABILITY: "Which product versions support {entity}?",
    SemanticDimension.DEPLOYMENT_APPLICABILITY: "Which deployment modes support {entity}?",
    SemanticDimension.ROLE_PROFILE_APPLICABILITY: "Is {entity} user, role, or profile specific?",
}


def _flatten_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            rows.extend(_flatten_strings(child, f"{path}.{key}"))
    elif isinstance(value, (list, tuple, set)):
        for index, child in enumerate(value):
            rows.extend(_flatten_strings(child, f"{path}[{index}]"))
    elif value is not None and not isinstance(value, bool):
        text = str(value).strip()
        if text:
            rows.append((path, text))
    return rows


def _words(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9_-]{2,}", value.casefold())
        if token
        not in {
            "what",
            "which",
            "when",
            "where",
            "does",
            "this",
            "that",
            "with",
            "from",
            "must",
            "should",
            "expected",
        }
    }


def _record_text(record: EvidenceRecord) -> str:
    if is_github_implementation_result_record(record):
        # A verification result answers one bound implementation question.  It
        # must not be re-read as broad issue/domain/semantic discovery prose.
        return ""
    return "\n".join(text for _, text in _flatten_strings(record.content))


def _positive_scope_clauses(values: list[str]) -> list[str]:
    """Remove explicit scope exclusions before routing or NFR activation."""

    clauses: list[str] = []
    for value in values:
        for clause in re.split(r"(?:\r?\n|;|(?<=[.!?])\s+)", value):
            normalized = clause.strip()
            if normalized and not _OUT_OF_SCOPE_CLAUSE_RE.search(normalized):
                clauses.append(normalized)
    return clauses


def _semantic_text_units(values: list[str]) -> tuple[str, ...]:
    """Return stable, record-bounded text units for semantic signal checks.

    Context-sensitive regular expressions must never run across independently
    sourced facts.  Fact IDs contain evidence lineage (including tenant-bound
    IDs), so their sort order is not a semantic input.  Keeping every value in
    its own unit makes the result independent of that incidental ordering while
    still allowing order-insensitive token checks.
    """

    return tuple(
        sorted(
            {
                re.sub(r"\s+", " ", str(value)).strip().casefold()
                for value in values
                if str(value).strip()
            }
        )
    )


_SCOPE_PRIMARY_PATH_LEAVES: dict[ContractFactType, frozenset[str]] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: frozenset(
        {"primary_product_area", "primary_component"}
    ),
    ContractFactType.PRIMARY_OUTPUT_TYPE: frozenset({"primary_output_type"}),
    ContractFactType.PRESET_TYPE: frozenset({"primary_preset_type"}),
}

_SCOPE_DIRECT_PATH_LEAVES: dict[ContractFactType, frozenset[str]] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: frozenset(
        {"product_area", "component", "components"}
    ),
    ContractFactType.PRIMARY_OUTPUT_TYPE: frozenset(
        {"output", "outputs", "output_type", "output_types"}
    ),
    ContractFactType.PRESET_TYPE: frozenset(
        {"preset", "presets", "preset_type", "output_preset", "output_presets"}
    ),
}

_SCOPE_UNRESOLVED_FIELD: dict[ContractFactType, str] = {
    ContractFactType.PRIMARY_PRODUCT_AREA: "PRIMARY_PRODUCT_AREA",
    ContractFactType.PRIMARY_OUTPUT_TYPE: "PRIMARY_OUTPUT_TYPE",
    ContractFactType.PRESET_TYPE: "PRIMARY_PRESET_TYPE",
}


def _scope_source_path(source_reference: str) -> str:
    """Return only the semantic JSON path, excluding provider identity.

    Evidence references and fact IDs may contain tenant-bound provenance.  The
    flattened JSON path appended by contract extraction is stable for the same
    semantic input and is the only part allowed to influence scope precedence.
    """

    marker = source_reference.rfind(":$")
    return source_reference[marker + 1 :] if marker >= 0 else ""


def _scope_source_priority(fact: ContractFact) -> tuple[int, int]:
    """Rank root scope fields above nested supporting material."""

    path = _scope_source_path(fact.source_reference)
    segments = tuple(
        match.group(1).casefold().replace("-", "_")
        for match in re.finditer(r"(?:^\$|\.)([a-zA-Z0-9_-]+)(?:\[\d+\])?", path)
    )
    if not segments:
        return (0, 0)
    leaf = segments[-1]
    primary = leaf in _SCOPE_PRIMARY_PATH_LEAVES.get(fact.fact_type, ())
    direct = primary or leaf in _SCOPE_DIRECT_PATH_LEAVES.get(
        fact.fact_type, ()
    )
    top_level = len(segments) == 1
    if top_level and primary:
        source_tier = 4
    elif top_level and direct:
        source_tier = 3
    elif primary:
        source_tier = 2
    elif direct:
        source_tier = 1
    else:
        source_tier = 0
    return (source_tier, -len(segments))


def _scope_semantic_value(fact: ContractFact) -> str:
    value = fact.normalized_value
    return str(value if value not in (None, "") else fact.literal).strip()


def _scope_semantic_key(value: str) -> str:
    return re.sub(r"[\s_-]+", " ", value.casefold()).strip()


def _units_contain_any(
    units: tuple[str, ...], signals: tuple[str, ...]
) -> bool:
    return any(signal in unit for unit in units for signal in signals)


def _units_match(units: tuple[str, ...], pattern: re.Pattern[str]) -> bool:
    return any(pattern.search(unit) is not None for unit in units)


def _bounded_behavior_subject(value: str, *, limit: int = 240) -> str:
    """Keep a source-authored behavior label readable and deterministically bounded."""

    normalized = re.sub(r"\s+", " ", value).strip()
    normalized = re.sub(
        r"^[*#\s]*(?:expected\s+behavio(?:u)?r|issue|summary)\s*[:\-]\s*",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).strip()
    if len(normalized) <= limit:
        return normalized
    clipped = normalized[: limit + 1].rsplit(" ", 1)[0].rstrip(" .,:;-")
    return f"{clipped}…"


def _behavior_reference_rank(source_reference: str) -> int:
    normalized = source_reference.casefold()
    if normalized.endswith(":$.summary"):
        return 0
    if normalized.endswith(".summary"):
        return 1
    if normalized.endswith(".title"):
        return 2
    return 3


def _material_behavior_fact(
    facts: ContractFactSet,
    *,
    allowed_evidence_ids: set[str] | None = None,
) -> ContractFact | None:
    """Select one current-issue behavior signal without using feature taxonomies."""

    excluded = {
        (fact.literal.casefold(), tuple(fact.source_evidence_ids))
        for fact in facts.facts
        if fact.fact_type == ContractFactType.OUT_OF_SCOPE
    }
    candidates: list[ContractFact] = []
    for fact in facts.facts:
        if allowed_evidence_ids is not None and not allowed_evidence_ids.intersection(
            fact.source_evidence_ids
        ):
            continue
        is_summary = bool(_SUMMARY_REFERENCE_RE.search(fact.source_reference))
        if (
            fact.fact_type != ContractFactType.DIRECT_EXPECTED_BEHAVIOR
            and not is_summary
        ):
            continue
        literal = fact.literal.strip()
        if len(literal) < 8:
            continue
        if (literal.casefold(), tuple(fact.source_evidence_ids)) in excluded:
            continue
        if (
            _OUT_OF_SCOPE_CLAUSE_RE.search(literal)
            or _NON_BEHAVIOR_CHANGE_RE.search(literal)
            or _REGRESSION_ONLY_RE.search(literal)
        ):
            continue
        candidates.append(fact)
    if not candidates:
        return None
    candidates.sort(
        key=lambda fact: (
            _behavior_reference_rank(fact.source_reference),
            0
            if re.search(
                r"\b(?:expected|should|must|incorrect|fails?|broken)\b",
                fact.literal,
                re.IGNORECASE,
            )
            else 1,
            len(fact.literal),
            fact.fact_id,
        )
    )
    return candidates[0]


def _scale_detection_text(text: str) -> str:
    """Remove identifier digits that cannot establish workload cardinality."""

    text = re.sub(r"\b[A-Z][A-Z0-9]+-\d+\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(?:[A-Za-z]:[\\/]|/)(?:[^\s,;]+[\\/])*[^\s,;]*",
        " ",
        text,
    )
    return re.sub(
        r"\b(?:line|offset|port|status|http)\s*[:#-]?\s*\d+\b",
        " ",
        text,
        flags=re.IGNORECASE,
    )


def _contains_domain_signal(text: str, signal: str) -> bool:
    normalized = signal.strip().casefold()
    if normalized in {"api", "apis"}:
        return bool(re.search(r"\bapis?\b", text))
    return normalized in text


def _contract_literals(path: str, literal: str) -> list[str]:
    """Split prose into source-exact clauses without paraphrasing it."""

    if any(
        token in path.casefold() for token in ("summary", "title", "label", "status")
    ):
        return [literal]
    parts = re.split(
        r"(?:\r?\n|\s*[;•]\s*|(?<=[.!?])\s+|"
        r"(?=\b(?:In scope|Out of scope|Enable DITA-OT Processing|Output preset type)\s*:))",
        literal,
        flags=re.IGNORECASE,
    )
    cleaned = [part.strip(" \t-*\u2022") for part in parts if part.strip(" \t-*\u2022")]
    return cleaned or [literal]


# A pasted stack trace / log dump is diagnostic noise, not an acceptance-relevant
# contract fact. Left intact it (a) mints junk "facts" out of individual frames and
# (b) can overflow bounded downstream fields (MissingQuestion behavior/oracle), which
# previously failed a whole run with HTTP 500. We keep the informative header lines
# ("<Exception>: message", "Caused by: ...") and drop the frame lines.
_STACK_FRAME_INLINE_RE = re.compile(r"\bat\s+[\w$.<>/]+\([^)]*\)")
_STACK_MORE_RE = re.compile(r"\.\.\.\s*\d+\s+more\b", re.IGNORECASE)
_STACK_SIGNATURE_RE = re.compile(
    r"(\bat\s+[\w$.<>/]+\([^)]*\)|Caused by:|\b[\w.]+(?:Exception|Error)\b\s*:)",
)


def _reduce_stack_frames(text: str) -> str:
    """Collapse a pasted stack trace to its header lines, leaving prose intact.

    No-op unless a stack-trace signature is present, so ordinary contract text is
    never altered.
    """

    if not text or not _STACK_SIGNATURE_RE.search(text):
        return text
    # Drop inline "at pkg.Class.method(File.java:NN)" frames and "... N more".
    reduced = _STACK_FRAME_INLINE_RE.sub(" ", text)
    reduced = _STACK_MORE_RE.sub(" ", reduced)
    # Drop any residual frame-only lines and collapse whitespace runs.
    kept_lines = [
        line
        for line in reduced.splitlines()
        if line.strip() and not re.fullmatch(r"\s*at\s+[\w$.<>/]+.*", line)
    ]
    reduced = "\n".join(kept_lines) if kept_lines else reduced
    reduced = re.sub(r"[ \t]{2,}", " ", reduced).strip()
    return reduced or text


def _is_contract_metadata(path: str, literal: str) -> bool:
    """Exclude transport/provenance identifiers before contract classification."""

    normalized_path = path.casefold().replace("[", ".").replace("]", "")
    leaf = normalized_path.rsplit(".", 1)[-1]
    if re.fullmatch(r"[A-Z][A-Z0-9]+-\d+", literal.strip(), re.IGNORECASE):
        return True
    if leaf in {
        "id",
        "issue_key",
        "jira_key",
        "source",
        "lookup_source",
        "source_hash",
        "source_url",
        "canonical_url",
        "chunk_id",
        "snapshot_id",
        "fingerprint",
        "schema_version",
        "line",
        "line_number",
        "commit_sha",
        "head_sha",
        "post_sync_sha",
        "created",
        "updated",
        "timestamp",
    }:
        return True
    return any(
        marker in normalized_path
        for marker in (
            ".evidence_snapshot.",
            ".source_manifest.",
            ".query_runtime.",
            ".generation.id",
        )
    )


def _fact_types(path: str, literal: str) -> list[ContractFactType]:
    key = path.casefold()
    text = literal.casefold()
    combined = f"{key} {text}"
    found: list[ContractFactType] = []
    mappings: tuple[tuple[ContractFactType, tuple[str, ...]], ...] = (
        (ContractFactType.OUT_OF_SCOPE, ("out_of_scope", "out of scope", "excluded")),
        (ContractFactType.IN_SCOPE, ("in_scope", "in scope", "applies to")),
        (
            ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            ("expected", "acceptance", "requirement", "should", "must"),
        ),
        (
            ContractFactType.PRIMARY_PRODUCT_AREA,
            ("product_area", "component", "feature area"),
        ),
        (
            ContractFactType.PRIMARY_OUTPUT_TYPE,
            ("output_type", "output type", "native pdf", "html5"),
        ),
        (ContractFactType.PRESET_TYPE, ("preset_type", "preset type", "output preset")),
        (ContractFactType.DITA_OT_PROCESSING_STATE, ("dita_ot", "dita-ot", "dita ot")),
        (ContractFactType.DEPLOYMENT_MODE, ("deployment", "on-prem", "cloud service")),
        (
            ContractFactType.PRODUCT_VERSION,
            ("fix version", "affects version", "product_version"),
        ),
        (
            ContractFactType.FEATURE_STATE,
            ("feature_state", "enabled", "disabled", "toggle"),
        ),
        (ContractFactType.EXACT_LABELS, ("label", "toggle name", "display name")),
        (ContractFactType.EXACT_DEFAULTS, ("default", "by default")),
        (ContractFactType.EXACT_STATUS_NAMES, ("status", "state name")),
        (ContractFactType.COLORS, ("color", "colour")),
        (ContractFactType.COUNTS, ("count", "number of", " documents", " pages")),
        (ContractFactType.LIMITS, ("limit", "maximum", "minimum", "timeout", "retry")),
        (
            ContractFactType.COMPATIBILITY_REQUIREMENTS,
            ("compatible", "upgrade", "existing behavior"),
        ),
        (
            ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
            ("must not", "should not", "without ", "no "),
        ),
        (
            ContractFactType.HUMAN_OPEN_QUESTIONS,
            ("open_question", "open question", "?"),
        ),
        (
            ContractFactType.ENGINEERING_DESIGN_QUESTIONS,
            ("design question", "implementation question"),
        ),
    )
    for fact_type, signals in mappings:
        if any(signal in combined for signal in signals):
            found.append(fact_type)
    if re.search(r"(?:\b\d+(?:\.\d+)?\b|#[0-9a-f]{3,8}\b)", literal, re.IGNORECASE):
        found.append(ContractFactType.EXACT_VALUES)
    if re.search(r"['\"“”][^'\"“”]{2,80}['\"“”]", literal):
        found.append(ContractFactType.HUMAN_TERMINOLOGY)
    slash_term = bool(
        re.search(
            r"\b[a-z][a-z0-9 _-]{1,30}/[a-z][a-z0-9 _-]{1,30}\b", literal, re.IGNORECASE
        )
        and not re.search(r"(?:https?://|/content/|/libs/|\\)", literal, re.IGNORECASE)
    )
    if slash_term:
        found.extend(
            [
                ContractFactType.HUMAN_TERMINOLOGY,
                ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
            ]
        )
    if not found and any(token in key for token in ("summary", "description", "title")):
        found.append(ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
    return list(dict.fromkeys(found))


def _normalized_fact_value(fact_type: ContractFactType, literal: str) -> str:
    """Produce a scope-friendly value without changing the preserved literal."""

    scoped_types = {
        ContractFactType.IN_SCOPE,
        ContractFactType.OUT_OF_SCOPE,
        ContractFactType.PRIMARY_PRODUCT_AREA,
        ContractFactType.PRIMARY_OUTPUT_TYPE,
        ContractFactType.PRESET_TYPE,
        ContractFactType.DITA_OT_PROCESSING_STATE,
        ContractFactType.DEPLOYMENT_MODE,
        ContractFactType.PRODUCT_VERSION,
        ContractFactType.FEATURE_STATE,
    }
    if fact_type in scoped_types and ":" in literal:
        value = literal.split(":", 1)[1].strip(" .;-")
        if value:
            return value
    if fact_type == ContractFactType.PRIMARY_OUTPUT_TYPE:
        match = re.search(
            r"\b(native\s+pdf|aem\s+sites|html5|json|pdf)\b",
            literal,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)
    if fact_type == ContractFactType.DEPLOYMENT_MODE:
        match = re.search(
            r"\b(on[- ]?prem(?:ises)?|cloud service|cloud)\b", literal, re.IGNORECASE
        )
        if match:
            return match.group(1)
    return literal


def _is_authoritative(record: EvidenceRecord) -> bool:
    return record.authority_subject == AuthoritySubject.PRODUCT_CONTRACT and (
        record.requirement_authority in _CONTRACT_AUTHORITIES
        or record.source_type in _HUMAN_CONTRACT_SOURCES
        or record.source_type
        in {EvidenceSourceType.JIRA_DESCRIPTION, EvidenceSourceType.CURRENT_JIRA}
    )


def _relation_for_surface(kind: ChangeSurfaceKind) -> BehaviorRelationType:
    return {
        ChangeSurfaceKind.CHANGED_BEHAVIOR: BehaviorRelationType.GOVERNED_BY,
        ChangeSurfaceKind.READS: BehaviorRelationType.READ_BY,
        ChangeSurfaceKind.WRITES: BehaviorRelationType.WRITTEN_BY,
        ChangeSurfaceKind.CALLERS: BehaviorRelationType.CALLS,
        ChangeSurfaceKind.CALLEES: BehaviorRelationType.CALLS,
        ChangeSurfaceKind.CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        ChangeSurfaceKind.CONFIG_DEPENDENCIES: BehaviorRelationType.CONFIGURED_BY,
        ChangeSurfaceKind.GENERATED_ARTIFACTS: BehaviorRelationType.GENERATED_BY,
        ChangeSurfaceKind.SHARED_PROCESSORS: BehaviorRelationType.PROCESSED_BY,
        ChangeSurfaceKind.ERROR_PATHS: BehaviorRelationType.EXECUTED_BY,
        ChangeSurfaceKind.PERSISTED_STATE: BehaviorRelationType.PERSISTS_THROUGH,
        ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        ChangeSurfaceKind.CHANGED_ENTITY: BehaviorRelationType.DEFINED_BY,
    }[kind]


_RELATION_KEYS: dict[str, BehaviorRelationType] = {
    **{item.value.casefold(): item for item in BehaviorRelationType},
    "consumers": BehaviorRelationType.CONSUMED_BY,
    "consumer": BehaviorRelationType.CONSUMED_BY,
    "reads": BehaviorRelationType.READ_BY,
    "readers": BehaviorRelationType.READ_BY,
    "writes": BehaviorRelationType.WRITTEN_BY,
    "writers": BehaviorRelationType.WRITTEN_BY,
    "callers": BehaviorRelationType.CALLS,
    "callees": BehaviorRelationType.CALLS,
    "config_dependencies": BehaviorRelationType.CONFIGURED_BY,
    "generated_artifacts": BehaviorRelationType.GENERATED_BY,
    "shared_processors": BehaviorRelationType.PROCESSED_BY,
    "persisted_state": BehaviorRelationType.PERSISTS_THROUGH,
    "downstream_decision_consumers": BehaviorRelationType.CONSUMED_BY,
    "parent": BehaviorRelationType.PARENT_OF,
    "children": BehaviorRelationType.CHILD_OF,
    "references": BehaviorRelationType.REFERENCES,
    "specializations": BehaviorRelationType.SPECIALIZED_BY,
}


def _explicit_relationships(
    value: Any,
    *,
    fallback_source: str,
    context: str = "",
) -> list[tuple[str, str, BehaviorRelationType]]:
    """Read typed relationships from arbitrary structured evidence fields."""

    rows: list[tuple[str, str, BehaviorRelationType]] = []
    if isinstance(value, dict):
        local_context = next(
            (
                str(value[key]).strip()
                for key in (
                    "entity",
                    "symbol",
                    "path",
                    "name",
                    "class",
                    "function",
                    "component",
                    "state",
                )
                if key in value
                and isinstance(value[key], (str, int, float))
                and str(value[key]).strip()
            ),
            context or fallback_source,
        )
        for key, child in value.items():
            normalized = str(key).casefold().replace("-", "_").replace(" ", "_")
            relation = _RELATION_KEYS.get(normalized)
            if relation is not None:
                for _, target in _flatten_strings(child):
                    if target != local_context:
                        rows.append((local_context, target[:500], relation))
            rows.extend(
                _explicit_relationships(
                    child,
                    fallback_source=fallback_source,
                    context=local_context,
                )
            )
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            rows.extend(
                _explicit_relationships(
                    child,
                    fallback_source=fallback_source,
                    context=context,
                )
            )
    return rows


def _subject_for_dimension(dimension: SemanticDimension) -> AuthoritySubject:
    if dimension in {
        SemanticDimension.GOVERNING_SEMANTICS,
        SemanticDimension.CONTROLLING_ATTRIBUTES,
        SemanticDimension.PARENT_CONTEXT,
        SemanticDimension.CHILD_CONTEXT,
        SemanticDimension.HIERARCHY,
        SemanticDimension.SPECIALIZATIONS,
        SemanticDimension.REFERENCED_CONTENT,
        SemanticDimension.NESTED_REFERENCED_CONTENT,
        SemanticDimension.FALLBACK,
    }:
        return AuthoritySubject.DITA_SEMANTICS
    if dimension == SemanticDimension.CROSS_SURFACE_SYNC:
        return AuthoritySubject.CURRENT_UI
    if dimension in {
        SemanticDimension.DIRECT_CONSUMERS,
        SemanticDimension.SIBLING_CONSUMERS,
        SemanticDimension.DOWNSTREAM_PROCESSOR,
        SemanticDimension.PERSISTED_STATE,
    }:
        return AuthoritySubject.ACTUAL_IMPLEMENTATION
    return AuthoritySubject.PRODUCT_CONTRACT


def _relation_for_dimension(
    dimension: SemanticDimension | None,
) -> BehaviorRelationType:
    return {
        SemanticDimension.GOVERNING_CONFIGURATION: BehaviorRelationType.CONFIGURED_BY,
        SemanticDimension.CONTROLLING_ATTRIBUTES: BehaviorRelationType.CONTROLLING_ATTRIBUTE,
        SemanticDimension.DIRECT_CONSUMERS: BehaviorRelationType.CONSUMED_BY,
        SemanticDimension.SIBLING_CONSUMERS: BehaviorRelationType.SIBLING_CONSUMER_OF,
        SemanticDimension.ALTERNATE_MECHANISMS: BehaviorRelationType.ALTERNATE_MECHANISM_TO,
        SemanticDimension.PARENT_CONTEXT: BehaviorRelationType.PARENT_OF,
        SemanticDimension.CHILD_CONTEXT: BehaviorRelationType.CHILD_OF,
        SemanticDimension.SPECIALIZATIONS: BehaviorRelationType.SPECIALIZED_BY,
        SemanticDimension.REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
        SemanticDimension.NESTED_REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
        SemanticDimension.DOWNSTREAM_PROCESSOR: BehaviorRelationType.PROCESSED_BY,
        SemanticDimension.GENERATED_OUTPUT: BehaviorRelationType.GENERATED_BY,
        SemanticDimension.PERSISTED_STATE: BehaviorRelationType.PERSISTS_THROUGH,
        SemanticDimension.CROSS_SURFACE_SYNC: BehaviorRelationType.SYNCHRONIZED_WITH,
        SemanticDimension.VERSION_APPLICABILITY: BehaviorRelationType.VERSION_DEPENDENT,
        SemanticDimension.DEPLOYMENT_APPLICABILITY: BehaviorRelationType.DEPLOYMENT_DEPENDENT,
        SemanticDimension.ROLE_PROFILE_APPLICABILITY: BehaviorRelationType.ROLE_DEPENDENT,
    }.get(dimension, BehaviorRelationType.DEFINED_BY)


def _target_sources(subject: AuthoritySubject) -> list[EvidenceSourceType]:
    return {
        AuthoritySubject.DITA_SEMANTICS: [
            EvidenceSourceType.DITA_SPECIFICATION,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.DITA_OT_DOCUMENTATION,
        ],
        AuthoritySubject.ACTUAL_IMPLEMENTATION: [
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.EXISTING_AUTOMATION,
        ],
        AuthoritySubject.CURRENT_UI: [
            EvidenceSourceType.UI_OBSERVATION,
            EvidenceSourceType.OBSERVED_UI_FLOW,
            EvidenceSourceType.SCREENSHOT_REPRODUCTION,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
        AuthoritySubject.PRODUCT_CONTRACT: [
            EvidenceSourceType.ACCEPTED_UAC,
            EvidenceSourceType.PRODUCT_DECISION,
            EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
            EvidenceSourceType.JIRA_DESCRIPTION,
            EvidenceSourceType.CUSTOMER_REQUEST,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
    }[subject]


# A contract fact must read as observable behaviour, not a raw evidence span. These
# shapes are evidence the miner pulled from the description/RAG/attachments (a screenshot
# ref, a doc-chunk lead-in, a bare number/version, a code line, a config-PID dump, a URL).
# Left as facts they flow through as coverage candidates and render as an evidence dump.
_EVIDENCE_IMAGE_RE = re.compile(r"\.(?:png|jpe?g|gif|bmp|svg)\b|\|thumbnail", re.I)
_EVIDENCE_DOCLEAD_RE = re.compile(
    r"^(?:documented purpose|learn about|configure |source page\b|how to use this in rag|"
    r"detected dita constructs|learned feature behaviou?r|publishing/output contexts)|"
    r"\| Adobe Experience Manager|"
    r"release of adobe experience manager|"  # release-note doc titles
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{4}\s+release\b",
    re.I,
)
_EVIDENCE_BARE_NUM_RE = re.compile(r"^[\d.\s]+$|^\d{4}\.\d")
_EVIDENCE_CODELINE_RE = re.compile(
    r"\b[A-Z][A-Za-z0-9]+\.[a-z][A-Za-z0-9_]*\(|"     # Class.method(
    r"\b[a-z][a-z0-9]*[A-Z][A-Za-z0-9]*\(|"           # camelCase(
    r"=\s*PropertiesUtil|\bimport\s|\.java\b|[A-Za-z]:\\\\|/src/|https?://|"
    r"\b\w+(?:\.\w+)+\s*=\s*(?:true|false)\b|"         # dotted config property = true/false
    r"\b\w+\.\w+\.\w+\.\w+\b"                          # 4-part dotted config PID
)


def _is_behavioural_literal(literal: str) -> bool:
    """True when a literal reads as observable behaviour rather than raw evidence."""

    s = (literal or "").strip()
    if len(s) < 6:
        return False
    if _EVIDENCE_IMAGE_RE.search(s):
        return False
    if _EVIDENCE_DOCLEAD_RE.search(s):
        return False
    if _EVIDENCE_BARE_NUM_RE.match(s):
        return False
    if _EVIDENCE_CODELINE_RE.search(s):
        return False
    return True


# A traceability anchor / evidence ID: a jira/UAC anchor prefix, an embedded UAC anchor,
# or a bare hex hash. These are record identifiers, never acceptance sentences.
_STRUCTURAL_ID_RE = re.compile(
    r"^(?:jira:)"          # jira anchor prefix (e.g. jira:GUIDES-33605:uac:<hash>)
    r"|:uac[:\-]"          # embedded UAC anchor (e.g. JIRA:GUIDES-1:UAC:UAC-14:<hash>)
    r"|^[0-9a-f]{16,}$",   # bare hex hash
    re.I,
)
# A bare snake_case dimension/axis tag with no whitespace (e.g. toolbar_customization,
# uuid_variant, locked_state). A real acceptance criterion contains prose, not a lone tag.
_BARE_TAG_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _is_structural_noise_literal(literal: str) -> bool:
    """True when a literal is a traceability ID or a bare dimension tag rather than an
    acceptance sentence.

    Applied to EVERY source (including accepted UAC / product decisions), because an
    anchor ID or a snake_case tag is structurally never a valid acceptance criterion no
    matter where it came from. Without this guard these tokens became contract facts,
    then acceptance candidates, then got promoted and rendered as acceptance-contract
    bullets (observed on GUIDES-33605: 95 bullets = 17 real ACs + 78 IDs/tags). Narrow by
    design: a real AC contains spaces and prose and will not match. See
    docs/specs/g1-runtime-consolidation.md."""

    s = (literal or "").strip()
    if not s:
        return False
    if " " in s or "\t" in s:
        # Prose. Only reject if it is a short concatenated anchor (<=2 tokens) that is
        # still an ID, never a genuine multi-word sentence.
        return bool(_STRUCTURAL_ID_RE.search(s)) and len(s.split()) <= 2
    if _STRUCTURAL_ID_RE.search(s) or _BARE_TAG_RE.match(s):
        return True
    # A lone single token with no whitespace - a bare dimension/axis label such as
    # "negative", "iframe", "ordering", "scope", "state" - is never an acceptance
    # sentence. Restricted to a single all-letter token (3-24 chars) so it cannot touch
    # multi-word prose, numbers, versions, or code-shaped values handled elsewhere.
    if re.fullmatch(r"[A-Za-z]{3,24}", s):
        return True
    return False


def _plain_candidate(value: str) -> str:
    """Humanize ontology prefixes while preserving the entity wording."""

    prefix, separator, remainder = value.partition(": ")
    if separator and re.fullmatch(r"[A-Z_]+", prefix):
        return f"{prefix.replace('_', ' ').capitalize()}: {remainder}"
    return value


def _scope_clause_value(value: str) -> str:
    _, separator, remainder = value.partition(":")
    selected = remainder if separator else value
    return selected.strip(" .;:-").casefold()


_CONTRADICTION_NEGATORS = {
    "disable",
    "disabled",
    "exclude",
    "excluded",
    "never",
    "no",
    "not",
    "off",
    "remove",
    "removed",
    "without",
}
_CONTRADICTION_STOP_WORDS = {
    "a",
    "an",
    "and",
    "as",
    "be",
    "for",
    "in",
    "is",
    "of",
    "on",
    "or",
    "should",
    "the",
    "to",
    "when",
    "with",
}


def _contract_terms(value: str) -> tuple[set[str], bool]:
    tokens = set(re.findall(r"[a-z0-9_-]+", value.casefold()))
    negative = bool(tokens & _CONTRADICTION_NEGATORS)
    return tokens - _CONTRADICTION_NEGATORS - _CONTRADICTION_STOP_WORDS, negative


def _contradicts_accepted_contract(
    candidate: str, accepted_literals: list[str]
) -> bool:
    """Detect only explicit polarity conflicts with a materially overlapping AC.

    The high overlap threshold deliberately avoids treating unrelated additional
    coverage as a contradiction.  Such additions are rejected separately when
    a Human Accepted Contract is active.
    """

    candidate_terms, candidate_negative = _contract_terms(candidate)
    if not candidate_terms:
        return False
    for literal in accepted_literals:
        accepted_terms, accepted_negative = _contract_terms(literal)
        if candidate_negative == accepted_negative or not accepted_terms:
            continue
        overlap = candidate_terms & accepted_terms
        denominator = min(len(candidate_terms), len(accepted_terms))
        if denominator and len(overlap) / denominator >= 0.6:
            return True
    return False


def _semantic_candidate_key(value: str) -> tuple[str, ...]:
    """Return a conservative outcome key for near-duplicate source wording.

    Only grammatical filler is removed.  Token order and every product noun
    remain significant so actor/object reversals and output/page distinctions
    cannot silently collapse into one acceptance candidate.
    """

    raw_terms = re.findall(r"[a-z0-9_-]+", value.casefold())
    negative = any(term in _CONTRADICTION_NEGATORS for term in raw_terms)
    terms = [
        term
        for term in raw_terms
        if term not in _CONTRADICTION_NEGATORS and term not in _CONTRADICTION_STOP_WORDS
    ]
    polarity = "__NEGATIVE__" if negative else "__POSITIVE__"
    return (polarity, *terms)


def _candidate_terminal_disposition(
    decision: AcceptancePromotionDecision,
) -> CandidateTerminalDisposition:
    if decision.status == PromotionStatus.PROMOTED:
        return CandidateTerminalDisposition.AC
    if decision.status == PromotionStatus.BLOCKED:
        return CandidateTerminalDisposition.OPEN_QUESTION
    if not decision.scope_established:
        return CandidateTerminalDisposition.OUT_OF_SCOPE
    return CandidateTerminalDisposition.INVESTIGATED_AND_REJECTED


def _canonical_product_versions(values: list[str]) -> set[str]:
    """Normalize explicit product-version labels without broadening their scope."""

    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"\s+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        matches = re.findall(
            r"\b\d+(?:\.\d+){1,3}(?:\s*(?:sp|service pack)\s*\d+)?\b",
            text,
        )
        normalized.update(re.sub(r"\s+", " ", match) for match in matches)
        if not matches:
            normalized.add(text)
    return normalized


def _canonical_deployment_modes(values: list[str]) -> set[str]:
    """Collapse only well-known Cloud/on-prem spelling variants."""

    normalized: set[str] = set()
    for value in values:
        text = re.sub(r"[_\s-]+", " ", str(value or "").strip().casefold())
        if not text:
            continue
        recognized = False
        if re.search(r"\bon\s*prem(?:ise|ises)?\b", text):
            normalized.add("on-prem")
            recognized = True
        if re.search(r"\bcloud(?:\s+service)?\b", text):
            normalized.add("cloud")
            recognized = True
        if not recognized:
            normalized.add(text)
    return normalized


def _implementation_scope_axes(
    record: EvidenceRecord,
) -> tuple[set[str], set[str]]:
    versions = _canonical_product_versions(
        [record.product_version, *record.version_scope.product_versions]
    )
    deployments = _canonical_deployment_modes(
        [record.deployment_model, record.version_scope.deployment_model]
    )
    return versions, deployments


def _implementation_evidence_matches_scope(
    record: EvidenceRecord,
    scope: ScopeResolution | None,
) -> bool:
    """Fail closed when implementation evidence cannot prove the active scope."""

    if (
        scope is None
        or record.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
    ):
        return True
    expected_versions = _canonical_product_versions(scope.product_versions)
    expected_deployments = _canonical_deployment_modes(scope.deployment_modes)
    actual_versions, actual_deployments = _implementation_scope_axes(record)
    return bool(
        (not expected_versions or expected_versions & actual_versions)
        and (not expected_deployments or expected_deployments & actual_deployments)
    )


def _implementation_scope_fully_covered(
    records: list[EvidenceRecord],
    question: MissingQuestion,
    scope: ScopeResolution | None,
) -> bool:
    """Require every requested version/deployment branch before confirmation."""

    if (
        scope is None
        or question.authority_subject != AuthoritySubject.ACTUAL_IMPLEMENTATION
    ):
        return True
    expected_versions = _canonical_product_versions(scope.product_versions)
    expected_deployments = _canonical_deployment_modes(scope.deployment_modes)
    if not expected_versions and not expected_deployments:
        return True
    actual_versions: set[str] = set()
    actual_deployments: set[str] = set()
    for record in records:
        versions, deployments = _implementation_scope_axes(record)
        actual_versions.update(versions)
        actual_deployments.update(deployments)
    return bool(
        (not expected_versions or expected_versions.issubset(actual_versions))
        and (
            not expected_deployments
            or expected_deployments.issubset(actual_deployments)
        )
    )


def _parse_authorization_time(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _semantic_handoff_is_current(
    handoff: AuthorizedSemanticEvidence,
    *,
    request: GenerationRequest,
    record: EvidenceRecord,
    question: MissingQuestion,
    retrieval: DirectedRetrievalRecord,
    local_evidence_ids: set[str],
    now: datetime,
) -> bool:
    """Revalidate the complete stage-10 authorization at its final consumer."""

    authorization = handoff.authorization
    attestation = authorization.source_attestation
    assessment = authorization.question_assessment
    binding = attestation.binding
    query = handoff.query
    provenance = handoff.provenance
    disposition = handoff.disposition
    content = record.content if isinstance(record.content, Mapping) else {}
    expected_source_reference_sha256 = stable_sha256(
        {
            "source_reference": record.source_reference,
            "source_locator": record.source_location,
            "source_native_id": record.source_native_id,
        }
    )
    expected_correlation_id = (
        "fj-shadow:"
        + stable_sha256(
            {
                "request_id": request.request_id,
                "question_id": question.question_id,
            }
        )[:32]
    )
    allowed = set(request.allowed_sources)
    expected_source_types = sorted(
        (
            source_type
            for source_type in question.target_source_types
            if not allowed or source_type in allowed
        ),
        key=lambda value: value.value,
    )
    verified_at = _parse_authorization_time(attestation.verified_at)
    attestation_expiry = _parse_authorization_time(attestation.expires_at)
    assessed_at = _parse_authorization_time(assessment.assessed_at)
    assessment_expiry = _parse_authorization_time(assessment.expires_at)
    expected_revision = next(
        (
            value
            for value in (
                record.version_scope.repository_revision,
                record.product_version,
                record.dita_version,
                record.version_scope.dita_version,
            )
            if str(value or "").strip()
        ),
        "",
    )
    is_preexisting_local_duplicate = record.evidence_id in local_evidence_ids
    lifecycle_is_valid = (
        record.inspected
        and record.lifecycle_status
        in {
            EvidenceLifecycleStatus.INSPECTED,
            EvidenceLifecycleStatus.USED,
        }
        if is_preexisting_local_duplicate
        else (
            record.retrieval_pass == "reasoning-directed-provider"  # noqa: S105
            and record.lifecycle_status == EvidenceLifecycleStatus.INSPECTED
            and record.inspected
            and not record.used
            and record.verification_status == attestation.verification_status
        )
    )
    if (
        authorization.question_assessment.binding != binding
        or assessment.source_attestation_id != attestation.attestation_id
        or binding.request_id != request.request_id
        or binding.tenant_id != request.tenant_id
        or binding.principal_scope_sha256
        != stable_sha256(request.principal.model_dump(mode="json"))
        or binding.question_id != question.question_id
        or binding.question_sha256 != stable_sha256(question.question)
        or binding.query_id != query.query_id
        or binding.evidence_id != record.evidence_id
        or binding.content_sha256 != record.content_sha256
        or binding.source_type != record.source_type
        or binding.authority_subject != record.authority_subject
        or binding.currentness != record.currentness
        or binding.requirement_authority != record.requirement_authority
        or record.requirement_authority not in _SEMANTIC_HANDOFF_AUTHORITIES
        or binding.version_scope_sha256
        != stable_sha256(record.version_scope.model_dump(mode="json"))
        or binding.visibility_sha256
        != stable_sha256(record.visibility.model_dump(mode="json"))
        or binding.source_reference_sha256 != expected_source_reference_sha256
        or binding.temporal_policy_sha256
        != stable_sha256(query.temporal_boundary.model_dump(mode="json"))
        or binding.authority_requirement_sha256
        != stable_sha256(query.authority_requirement.model_dump(mode="json"))
        or binding.provenance_id != provenance.provenance_id
        or provenance.applicability != ApplicabilityState.APPLICABLE
        or binding.disposition_id != disposition.disposition_id
        or binding.provider != provenance.provider
        or binding.provider_contract_version != provenance.provider_contract_version
        or binding.provider_call_id != provenance.provider_call_id
        or binding.correlation_id != provenance.correlation_id
        or query.question_id != question.question_id
        or query.question != question.question
        or query.dimension != question.dimension
        or query.authority_requirement.subject != question.authority_subject
        or query.requested_evidence_types != expected_source_types
        or query.jira_reference != request.jira_key
        or query.correlation_id != expected_correlation_id
        or query.blocking != question.blocking
        or (
            query.context_evidence_ids
            and not set(query.context_evidence_ids).issubset(
                retrieval.matched_evidence_ids
            )
        )
        or query.query_id not in record.retrieved_by_query
        or provenance.evidence_id != record.evidence_id
        or disposition.evidence_id != record.evidence_id
        or disposition.source_type != record.source_type
        or disposition.source_reference_sha256 != expected_source_reference_sha256
        or disposition.content_sha256
        != stable_sha256({"text": str(content.get("text") or "")})
        or disposition.provider_hit_sha256 != binding.provider_hit_sha256
        or assessment.assessed_content_sha256 != record.content_sha256
        or not lifecycle_is_valid
        or not record_visible_to(record, request.principal)
        or verified_at is None
        or verified_at > now
        or (attestation_expiry is not None and attestation_expiry <= now)
        or assessed_at is None
        or assessed_at > now
        or assessment_expiry is None
        or assessment_expiry <= now
    ):
        return False
    if record.currentness == CurrentnessState.VERSION_SPECIFIC:
        return bool(
            attestation.verification_status == VerificationState.VERIFIED_REVISION
            and expected_revision
            and attestation.source_revision == expected_revision
        )
    if record.currentness == CurrentnessState.ENVIRONMENT_SPECIFIC:
        return bool(
            (
                record.deployment_model
                or record.environment
                or record.version_scope.deployment_model
                or record.version_scope.environment
            )
            and attestation.verification_status
            in {VerificationState.VERIFIED_LIVE, VerificationState.VERIFIED_SOURCE}
        )
    return bool(
        record.currentness == CurrentnessState.CURRENT
        and attestation.verification_status
        in {VerificationState.VERIFIED_LIVE, VerificationState.VERIFIED_SOURCE}
    )


class CanonicalTestPlanReasoningService:
    """Typed transformations used by the canonical runtime in fixed order."""

    def extract_contract_facts(
        self, bundle: CanonicalEvidenceBundle
    ) -> ContractFactSet:
        facts: list[ContractFact] = []
        for record in bundle.records:
            if record.authority_subject != AuthoritySubject.PRODUCT_CONTRACT:
                continue
            for path, source_literal in _flatten_strings(record.content):
                source_literal = _reduce_stack_frames(source_literal)
                for literal in _contract_literals(path, source_literal):
                    if not literal.strip():
                        # A whitespace-only source value (e.g. an empty AC line or a
                        # non-breaking-space metadata value) must never become a fact:
                        # an authoritative fact with empty literal fails ContractIntegrityGate
                        # and hard-blocks the whole plan (no output). Skip it here.
                        continue
                    if _is_contract_metadata(path, literal):
                        continue
                    if _is_structural_noise_literal(literal):
                        # A traceability anchor ID or a bare dimension tag is never an
                        # acceptance sentence. Filter it from EVERY source (including
                        # accepted UAC) so it cannot become a fact -> candidate ->
                        # promoted acceptance-contract bullet. Filtering at extraction
                        # keeps the completeness invariant intact (facts are counted from
                        # extraction output, so no orphan disposition downstream).
                        continue
                    _accepted_source = record.source_type in {
                        EvidenceSourceType.ACCEPTED_UAC,
                        EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                        EvidenceSourceType.PRODUCT_DECISION,
                    }
                    if not _accepted_source and not _is_behavioural_literal(literal):
                        # An evidence-noise span from a lower-authority record (a
                        # screenshot ref, doc-chunk lead-in, bare number, code line,
                        # config-PID) must not become a contract fact; it renders as an
                        # evidence dump in the coverage sections. Accepted UAC / product
                        # decisions are never filtered.
                        continue
                    if len(literal) > 2000:
                        literal = literal[:2000]
                    fact_types = _fact_types(path, literal)
                    if (
                        record.source_type
                        in {
                            EvidenceSourceType.ACCEPTED_UAC,
                            EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                            EvidenceSourceType.PRODUCT_DECISION,
                        }
                        and len(literal) >= 4
                        and not any(
                            token in path.casefold()
                            for token in (
                                "fingerprint",
                                "snapshot_id",
                                "evidence_ref",
                                "source_clause_id",
                                "automation_consumption",
                                "schema_version",
                                "uac_id",
                                "priority",
                                "confidence",
                            )
                        )
                        and ContractFactType.DIRECT_EXPECTED_BEHAVIOR not in fact_types
                    ):
                        fact_types.insert(0, ContractFactType.DIRECT_EXPECTED_BEHAVIOR)
                    for fact_type in fact_types:
                        ambiguous = (
                            fact_type
                            == ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED
                        )
                        facts.append(
                            ContractFact(
                                fact_type=fact_type,
                                literal=literal,
                                normalized_value=_normalized_fact_value(
                                    fact_type, literal
                                ),
                                source_evidence_ids=[record.evidence_id],
                                source_reference=f"{record.source_reference}:{path}",
                                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                                authority_class=record.requirement_authority,
                                authoritative=_is_authoritative(record),
                                preservation_state=(
                                    ContractPreservationState.EXPLICITLY_FLAGGED_AS_AMBIGUOUS
                                    if ambiguous
                                    else ContractPreservationState.PRESERVED
                                ),
                                ambiguity="Human terminology requires clarification."
                                if ambiguous
                                else "",
                            )
                        )
        has_accepted = any(
            fact.authority_class in _ACCEPTED_AUTHORITIES
            or any(
                record.evidence_id in fact.source_evidence_ids
                and record.source_type == EvidenceSourceType.ACCEPTED_UAC
                for record in bundle.records
            )
            for fact in facts
        )
        has_human = any(
            record.source_type in _HUMAN_CONTRACT_SOURCES for record in bundle.records
        )
        has_authoritative = any(fact.authoritative for fact in facts)
        mode = (
            ContractMode.HUMAN_ACCEPTED_CONTRACT
            if has_accepted
            else ContractMode.PARTIAL_HUMAN_CONTRACT
            if has_human
            else ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
            if has_authoritative
            else ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT
        )
        return ContractFactSet(contract_mode=mode, facts=facts)

    def contract_integrity_gate(self, facts: ContractFactSet) -> GateDecision:
        failures: list[str] = []
        for fact in facts.facts:
            if not fact.authoritative:
                continue
            if fact.preservation_state == ContractPreservationState.LOST:
                failures.append(f"Authoritative fact was lost: {fact.fact_id}")
            if not fact.literal.strip():
                failures.append(
                    f"Authoritative source wording is empty: {fact.fact_id}"
                )
            if not fact.source_evidence_ids:
                failures.append(f"Authoritative fact has no source: {fact.fact_id}")
        if facts.contract_mode == ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT:
            failures.append("No authoritative product-contract fact is available.")
        return GateDecision(
            gate="ContractIntegrityGate",
            status=GateStatus.FAILED if failures else GateStatus.PASSED,
            failures=failures,
            checked_ids=facts.authoritative_fact_ids,
        )

    def route_domains(
        self, bundle: CanonicalEvidenceBundle, facts: ContractFactSet
    ) -> list[DomainActivation]:
        positive_values = [
            fact.literal
            for fact in facts.facts
            if fact.fact_type != ContractFactType.OUT_OF_SCOPE
        ] + [_record_text(record) for record in bundle.records]
        text = " ".join(_positive_scope_clauses(positive_values)).casefold()
        padded = f" {text} "
        scale_text = _scale_detection_text(padded)
        activations: list[DomainActivation] = []
        for domain, signals in _DOMAIN_SIGNALS.items():
            matched = sorted(
                {
                    signal.strip()
                    for signal in signals
                    if _contains_domain_signal(padded, signal)
                }
            )
            if domain == IssueDomain.PERFORMANCE and re.search(
                r"\b(?:\d{1,3}(?:,\d{3})+|\d{4,}|\d+(?:\.\d+)?\s*k)\b"
                r".{0,40}\b(?:documents?|pages?|items?|maps?|topics?)\b",
                scale_text,
            ):
                matched.append("explicit-high-cardinality")
            if (
                domain == IssueDomain.CONTENT_MANAGEMENT
                and _CONTENT_LIFECYCLE_RE.search(padded)
            ):
                matched.append("content-lifecycle-operation")
            if matched:
                activations.append(
                    DomainActivation(
                        domain=domain,
                        confidence=min(0.98, 0.65 + 0.08 * len(matched)),
                        evidence_ids=[
                            record.evidence_id
                            for record in bundle.records
                            if any(
                                _contains_domain_signal(
                                    " ".join(
                                        _positive_scope_clauses([_record_text(record)])
                                    ).casefold(),
                                    signal,
                                )
                                for signal in signals
                            )
                        ],
                        matched_signals=matched,
                    )
                )
        if not activations:
            activations.append(
                DomainActivation(
                    domain=IssueDomain.OTHER,
                    confidence=0.5,
                    matched_signals=["fallback"],
                )
            )
        return sorted(activations, key=lambda row: row.domain.value)

    def resolve_scope(
        self, facts: ContractFactSet, domains: list[DomainActivation]
    ) -> ScopeResolution:
        by_type: dict[ContractFactType, list[ContractFact]] = defaultdict(list)
        for fact in facts.facts:
            by_type[fact.fact_type].append(fact)
        publishing = any(row.domain == IssueDomain.PUBLISHING for row in domains)
        active_domains = {row.domain for row in domains}
        semantic_units = _semantic_text_units(
            [
                fact.literal
                for fact in facts.facts
                if fact.fact_type != ContractFactType.OUT_OF_SCOPE
            ]
        )
        dita_ot = DitaOtProcessingState.NOT_APPLICABLE
        if publishing:
            configuration_only = (
                _units_contain_any(
                    semantic_units, _PUBLISHING_CONFIGURATION_ONLY_SIGNALS
                )
                and not _units_contain_any(
                    semantic_units, _GENERATED_ARTIFACT_DELIVERY_SIGNALS
                )
                and not _units_match(
                    semantic_units, _CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE
                )
            )
            dita_scope_units = _semantic_text_units(
                [
                    fact.literal
                    for fact in by_type[ContractFactType.DITA_OT_PROCESSING_STATE]
                    if not fact.literal.casefold().startswith("out of scope")
                ]
            )
            on = _units_match(
                dita_scope_units,
                re.compile(r"dita[- ]?ot.{0,30}\b(on|enabled|true)\b"),
            )
            off = _units_match(
                dita_scope_units,
                re.compile(r"dita[- ]?ot.{0,30}\b(off|disabled|false)\b"),
            )
            dita_ot = (
                DitaOtProcessingState.NOT_APPLICABLE
                if configuration_only
                else DitaOtProcessingState.BOTH
                if on and off
                else DitaOtProcessingState.ON
                if on
                else DitaOtProcessingState.OFF
                if off
                else DitaOtProcessingState.UNRESOLVED
            )
        out_literals = {
            fact.literal.casefold() for fact in by_type[ContractFactType.OUT_OF_SCOPE]
        }
        selection_conflicts: set[ContractFactType] = set()

        def selected_literal(fact_type: ContractFactType) -> str:
            candidates = [
                fact
                for fact in by_type[fact_type]
                if fact.literal.casefold() not in out_literals
                and not fact.literal.casefold().startswith("out of scope")
            ]
            if not candidates:
                return ""

            def precedence(fact: ContractFact) -> tuple[int, int, int, int]:
                return (
                    fact.authority_class in _ACCEPTED_AUTHORITIES,
                    fact.authoritative,
                    *_scope_source_priority(fact),
                )

            highest_precedence = max(precedence(fact) for fact in candidates)
            highest_candidates = [
                fact for fact in candidates if precedence(fact) == highest_precedence
            ]
            semantic_values = {
                _scope_semantic_key(_scope_semantic_value(fact))
                for fact in highest_candidates
            }
            if len(semantic_values) != 1:
                selection_conflicts.add(fact_type)
                return ""

            return min(
                (_scope_semantic_value(fact) for fact in highest_candidates),
                key=lambda value: (value.casefold(), value),
            )

        product_area = selected_literal(ContractFactType.PRIMARY_PRODUCT_AREA)
        output_type = selected_literal(ContractFactType.PRIMARY_OUTPUT_TYPE)
        preset = selected_literal(ContractFactType.PRESET_TYPE)
        normalized_out_scope = " ".join(
            str(fact.normalized_value or fact.literal)
            for fact in by_type[ContractFactType.OUT_OF_SCOPE]
        ).casefold()
        shared_path_outputs = sorted(
            {
                fact.literal
                for fact in facts.facts
                if "share" in fact.literal.casefold()
                and any(
                    token in fact.literal.casefold()
                    for token in ("preset", "output", "processor", "resolver")
                )
            }
        )
        unresolved: list[str] = []
        if publishing and dita_ot == DitaOtProcessingState.UNRESOLVED:
            unresolved.append("ENABLE_DITA_OT_PROCESSING")
        if publishing and not preset:
            unresolved.append("PRIMARY_PRESET_TYPE")
        if publishing and not by_type[ContractFactType.OUT_OF_SCOPE]:
            unresolved.append("OUT_OF_SCOPE")
        if publishing and not shared_path_outputs:
            unresolved.append("SHARED_PATH_OUTPUTS")
        unresolved.extend(
            _SCOPE_UNRESOLVED_FIELD[fact_type]
            for fact_type in sorted(selection_conflicts, key=lambda row: row.value)
        )
        return ScopeResolution(
            primary_product_area=product_area,
            primary_publishing_mode=output_type or preset,
            primary_preset_type=preset,
            primary_output_type=output_type,
            enable_dita_ot_processing=dita_ot,
            aem_sites_implementation=(
                ApplicabilityState.NOT_APPLICABLE
                if "aem sites" in normalized_out_scope
                else ApplicabilityState.APPLICABLE
                if any("aem sites" in unit for unit in semantic_units)
                else ApplicabilityState.UNRESOLVED
                if publishing
                else ApplicabilityState.NOT_APPLICABLE
            ),
            in_scope=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.IN_SCOPE]
            ],
            out_of_scope=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.OUT_OF_SCOPE]
            ],
            shared_path_outputs=shared_path_outputs,
            execution_interfaces=sorted(
                ({"API"} if IssueDomain.API in active_domains else set())
                | ({"UI"} if IssueDomain.AUTHORING in active_domains else set())
            ),
            product_versions=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.PRODUCT_VERSION]
            ],
            deployment_modes=[
                str(fact.normalized_value or fact.literal)
                for fact in by_type[ContractFactType.DEPLOYMENT_MODE]
            ],
            unresolved_fields=unresolved,
            source_fact_ids=[fact.fact_id for fact in facts.facts],
        )

    def extract_change_surfaces(
        self, bundle: CanonicalEvidenceBundle, facts: ContractFactSet
    ) -> list[ChangeSurface]:
        surfaces: list[ChangeSurface] = []
        key_map: dict[str, ChangeSurfaceKind] = {
            "changed_entity": ChangeSurfaceKind.CHANGED_ENTITY,
            "changed_entities": ChangeSurfaceKind.CHANGED_ENTITY,
            "files": ChangeSurfaceKind.CHANGED_ENTITY,
            "path": ChangeSurfaceKind.CHANGED_ENTITY,
            "symbol": ChangeSurfaceKind.CHANGED_ENTITY,
            "reads": ChangeSurfaceKind.READS,
            "writes": ChangeSurfaceKind.WRITES,
            "callers": ChangeSurfaceKind.CALLERS,
            "callees": ChangeSurfaceKind.CALLEES,
            "consumers": ChangeSurfaceKind.CONSUMERS,
            "config_dependencies": ChangeSurfaceKind.CONFIG_DEPENDENCIES,
            "generated_artifacts": ChangeSurfaceKind.GENERATED_ARTIFACTS,
            "shared_processors": ChangeSurfaceKind.SHARED_PROCESSORS,
            "error_paths": ChangeSurfaceKind.ERROR_PATHS,
            "persisted_state": ChangeSurfaceKind.PERSISTED_STATE,
            "downstream_decision_consumers": ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS,
        }
        for record in bundle.records:
            if (
                record.source_type not in _IMPLEMENTATION_SOURCES
                or is_github_implementation_result_record(record)
            ):
                continue
            for path, literal in _flatten_strings(record.content):
                kind = next(
                    (value for key, value in key_map.items() if key in path.casefold()),
                    None,
                )
                if kind is None and not any(
                    token in path.casefold() for token in ("match", "file", "source")
                ):
                    continue
                surfaces.append(
                    ChangeSurface(
                        kind=kind or ChangeSurfaceKind.CHANGED_ENTITY,
                        entity=literal[:500],
                        source_evidence_ids=[record.evidence_id],
                        confidence=record.evidence_confidence,
                    )
                )
        if not surfaces:
            current_issue_evidence_ids = {
                record.evidence_id
                for record in bundle.records
                if record.source_type in _CURRENT_ISSUE_BEHAVIOR_SOURCES
            }
            behavior_fact = _material_behavior_fact(
                facts,
                allowed_evidence_ids=current_issue_evidence_ids,
            )
            if behavior_fact is not None:
                source_confidence = max(
                    (
                        record.evidence_confidence
                        for record in bundle.records
                        if record.evidence_id in behavior_fact.source_evidence_ids
                    ),
                    default=0.5,
                )
                surfaces.append(
                    ChangeSurface(
                        kind=ChangeSurfaceKind.CHANGED_BEHAVIOR,
                        entity=_bounded_behavior_subject(behavior_fact.literal),
                        source_evidence_ids=behavior_fact.source_evidence_ids,
                        confidence=max(0.5, source_confidence),
                    )
                )
            else:
                area = next(
                    (
                        fact.literal
                        for fact in facts.facts
                        if fact.fact_type == ContractFactType.PRIMARY_PRODUCT_AREA
                    ),
                    "AEM Guides behavior",
                )
                surfaces.append(
                    ChangeSurface(
                        kind=ChangeSurfaceKind.CHANGED_ENTITY,
                        entity=area,
                        source_evidence_ids=facts.source_evidence_ids,
                        confidence=0.5,
                    )
                )
        return sorted(
            {row.surface_id: row for row in surfaces}.values(),
            key=lambda row: row.surface_id,
        )

    def extract_abstract_signals(
        self, surfaces: list[ChangeSurface]
    ) -> list[AbstractSignal]:
        """Lift changed behavior into a feature-neutral semantic signal."""

        signals = [
            AbstractSignal(
                kind=AbstractSignalKind.CHANGED_BEHAVIOR,
                subject=surface.entity,
                source_surface_ids=[surface.surface_id],
                source_evidence_ids=surface.source_evidence_ids,
                confidence=surface.confidence,
            )
            for surface in surfaces
            if surface.kind == ChangeSurfaceKind.CHANGED_BEHAVIOR
        ]
        return sorted(
            {row.signal_id: row for row in signals}.values(),
            key=lambda row: row.signal_id,
        )

    def route_reasoning_patterns(
        self, signals: list[AbstractSignal]
    ) -> list[ReasoningPatternActivation]:
        """Route a changed behavior to its governing semantic question family."""

        activations = [
            ReasoningPatternActivation(
                question_family=ReasoningQuestionFamily.GOVERNING_SEMANTICS,
                semantic_dimension=SemanticDimension.GOVERNING_SEMANTICS,
                source_signal_ids=[signal.signal_id],
                subject=signal.subject,
            )
            for signal in signals
            if signal.kind == AbstractSignalKind.CHANGED_BEHAVIOR
        ]
        return sorted(
            {row.activation_id: row for row in activations}.values(),
            key=lambda row: row.activation_id,
        )

    def build_behavior_graph(
        self,
        bundle: CanonicalEvidenceBundle,
        facts: ContractFactSet,
        surfaces: list[ChangeSurface],
    ) -> BehaviorGraph:
        nodes: list[BehaviorGraphNode] = []
        edges: list[BehaviorGraphEdge] = []
        evidence_nodes: dict[str, BehaviorGraphNode] = {}
        graph_records = [
            record
            for record in bundle.records
            if not is_github_implementation_result_record(record)
        ]
        for record in graph_records:
            node = BehaviorGraphNode(
                label=record.source_reference,
                node_type="EVIDENCE_SOURCE",
                source_evidence_ids=[record.evidence_id],
                authoritative=_is_authoritative(record),
            )
            evidence_nodes[record.evidence_id] = node
            nodes.append(node)
        for fact in facts.facts:
            fact_node = BehaviorGraphNode(
                label=fact.literal[:500],
                node_type=f"CONTRACT_FACT:{fact.fact_type.value}",
                source_evidence_ids=fact.source_evidence_ids,
                authoritative=fact.authoritative,
            )
            nodes.append(fact_node)
            for evidence_id in fact.source_evidence_ids:
                source_node = evidence_nodes.get(evidence_id)
                if source_node:
                    record = next(
                        row for row in graph_records if row.evidence_id == evidence_id
                    )
                    edges.append(
                        BehaviorGraphEdge(
                            source_node_id=fact_node.node_id,
                            target_node_id=source_node.node_id,
                            relation=BehaviorRelationType.DEFINED_BY,
                            provenance_evidence_ids=[evidence_id],
                            authority_subject=fact.authority_subject,
                            authority_class=fact.authority_class,
                            currentness=record.currentness,
                            confidence=record.evidence_confidence,
                            verification_state=(
                                HypothesisState.CONFIRMED
                                if fact.authoritative
                                else HypothesisState.INFERRED_HIGH_CONFIDENCE
                            ),
                        )
                    )
        for surface in surfaces:
            surface_node = BehaviorGraphNode(
                label=surface.entity,
                node_type=f"CHANGE_SURFACE:{surface.kind.value}",
                source_evidence_ids=surface.source_evidence_ids,
            )
            nodes.append(surface_node)
            for evidence_id in surface.source_evidence_ids:
                source_node = evidence_nodes.get(evidence_id)
                if not source_node:
                    continue
                record = next(
                    row for row in graph_records if row.evidence_id == evidence_id
                )
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=surface_node.node_id,
                        target_node_id=source_node.node_id,
                        relation=_relation_for_surface(surface.kind),
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=record.authority_subject
                        or AuthoritySubject.ACTUAL_IMPLEMENTATION,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=surface.confidence,
                        verification_state=(
                            HypothesisState.CONFIRMED
                            if record.verification_status.value.startswith("verified")
                            else HypothesisState.INFERRED_HIGH_CONFIDENCE
                        ),
                    )
                )
        relationship_nodes: dict[tuple[str, str], BehaviorGraphNode] = {
            (row.node_type, row.label): row for row in nodes
        }
        for record in graph_records:
            for source_label, target_label, relation in _explicit_relationships(
                record.content,
                fallback_source=record.source_reference,
            ):
                source_key = ("BEHAVIOR_ENTITY", source_label)
                target_key = ("BEHAVIOR_ENTITY", target_label)
                source_node = relationship_nodes.get(source_key)
                if source_node is None:
                    source_node = BehaviorGraphNode(
                        label=source_label,
                        node_type="BEHAVIOR_ENTITY",
                        source_evidence_ids=[record.evidence_id],
                    )
                    relationship_nodes[source_key] = source_node
                    nodes.append(source_node)
                target_node = relationship_nodes.get(target_key)
                if target_node is None:
                    target_node = BehaviorGraphNode(
                        label=target_label,
                        node_type="BEHAVIOR_ENTITY",
                        source_evidence_ids=[record.evidence_id],
                    )
                    relationship_nodes[target_key] = target_node
                    nodes.append(target_node)
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=source_node.node_id,
                        target_node_id=target_node.node_id,
                        relation=relation,
                        provenance_evidence_ids=[record.evidence_id],
                        authority_subject=record.authority_subject
                        or AuthoritySubject.ACTUAL_IMPLEMENTATION,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=record.evidence_confidence,
                        verification_state=(
                            HypothesisState.CONFIRMED
                            if record.evidence_confidence >= 0.8
                            and record.source_type != EvidenceSourceType.MODEL_INFERENCE
                            else HypothesisState.INFERRED_HIGH_CONFIDENCE
                        ),
                    )
                )
        return BehaviorGraph(nodes=nodes, edges=edges)

    def build_behavior_model(
        self,
        domains: list[DomainActivation],
        scope: ScopeResolution,
        surfaces: list[ChangeSurface],
        graph: BehaviorGraph,
        facts: ContractFactSet,
    ) -> CanonicalBehaviorModel:
        domain_values = [row.domain for row in domains]
        entities = list(dict.fromkeys(row.entity for row in surfaces))[:12]
        behavior_units = _semantic_text_units(
            [
                fact.literal
                for fact in facts.facts
                if fact.fact_type != ContractFactType.OUT_OF_SCOPE
            ]
            + entities
        )
        publishing = IssueDomain.PUBLISHING in domain_values
        delivery_state = ApplicabilityState.NOT_APPLICABLE
        if publishing:
            if _units_contain_any(
                behavior_units, _GENERATED_ARTIFACT_DELIVERY_SIGNALS
            ) or _units_match(
                behavior_units, _CONTEXTUAL_GENERATED_ARTIFACT_DELIVERY_RE
            ):
                delivery_state = ApplicabilityState.APPLICABLE
            elif _units_contain_any(
                behavior_units, _PUBLISHING_CONFIGURATION_ONLY_SIGNALS
            ):
                delivery_state = ApplicabilityState.NOT_APPLICABLE
            else:
                delivery_state = ApplicabilityState.UNRESOLVED
        publishing_stages = {
            stage: ApplicabilityState.NOT_APPLICABLE
            for stage in PublishingTransformationStage
        }
        if publishing:
            for stage in (
                PublishingTransformationStage.PRESET,
                PublishingTransformationStage.PROFILE_CONFIG,
            ):
                publishing_stages[stage] = ApplicabilityState.APPLICABLE
            for stage in PublishingTransformationStage:
                if stage not in {
                    PublishingTransformationStage.PRESET,
                    PublishingTransformationStage.PROFILE_CONFIG,
                }:
                    publishing_stages[stage] = delivery_state
        oracles = (
            [
                GeneratedOutputOracle.ARTIFACT_EXISTS,
                GeneratedOutputOracle.CONTENT_CORRECT,
                GeneratedOutputOracle.HIERARCHY_CORRECT,
                GeneratedOutputOracle.LINKS_CORRECT,
                GeneratedOutputOracle.METADATA_CORRECT,
                GeneratedOutputOracle.OUTPUT_PATH_CORRECT,
                GeneratedOutputOracle.NO_DUPLICATES,
                GeneratedOutputOracle.NO_ORPHANS,
                GeneratedOutputOracle.NO_STALE_OUTPUT,
                GeneratedOutputOracle.STATUS_MATCHES_REAL_OUTPUT,
            ]
            if delivery_state == ApplicabilityState.APPLICABLE
            else []
        )
        conditional_oracles = {
            "title": GeneratedOutputOracle.TITLE_CORRECT,
            "order": GeneratedOutputOracle.ORDER_CORRECT,
            "navigation": GeneratedOutputOracle.NAVIGATION_CORRECT,
            "locale": GeneratedOutputOracle.LOCALE_CORRECT,
            "activation": GeneratedOutputOracle.ACTIVATION_STATE_CORRECT,
            "unchanged": GeneratedOutputOracle.UNCHANGED_CONTENT_NOT_REWRITTEN,
        }
        if delivery_state == ApplicabilityState.APPLICABLE:
            oracles.extend(
                oracle
                for signal, oracle in conditional_oracles.items()
                if any(signal in unit for unit in behavior_units)
            )
        lifecycle_signals: dict[LifecycleOperation, tuple[str, ...]] = {
            LifecycleOperation.FIRST_GENERATION: ("first generation",),
            LifecycleOperation.REGENERATION: ("regeneration", "regenerate"),
            LifecycleOperation.NO_CHANGE_REGENERATION: ("no-change", "no change"),
            LifecycleOperation.UPDATE: ("update",),
            LifecycleOperation.DELETE: ("delete", "removed"),
            LifecycleOperation.MOVE: ("move",),
            LifecycleOperation.RENAME: ("rename",),
            LifecycleOperation.SAVE_REOPEN: ("save", "reopen"),
            LifecycleOperation.REFRESH: ("refresh", "reload"),
            LifecycleOperation.REPUBLISH: ("republish",),
            LifecycleOperation.ACTIVATION: ("activation", "activate"),
            LifecycleOperation.CANCEL: ("cancel",),
            LifecycleOperation.RETRY: ("retry",),
            LifecycleOperation.FAILURE_THEN_RECOVERY: ("recovery", "recover"),
            LifecycleOperation.REPEATED_MEANINGFUL_CHANGES: ("repeated",),
        }
        lifecycle = [
            operation
            for operation, signals in lifecycle_signals.items()
            if any(signal in unit for unit in behavior_units for signal in signals)
        ]
        return CanonicalBehaviorModel(
            primary_entities=entities,
            domains=domain_values,
            graph=graph,
            publishing_transformation_stages=publishing_stages,
            generated_artifact_delivery=delivery_state,
            generated_output_oracles=list(dict.fromkeys(oracles)),
            lifecycle_operations=lifecycle,
        )

    def explore_semantic_closure(
        self,
        bundle: CanonicalEvidenceBundle,
        model: CanonicalBehaviorModel,
        signals: list[AbstractSignal] | None = None,
        activations: list[ReasoningPatternActivation] | None = None,
        mandatory_families: list[MandatoryInvestigationFamily] | None = None,
    ) -> list[ClosureDimensionResult]:
        signals = signals or []
        activations = activations or []
        mandatory_families = mandatory_families or []
        applicable = self.applicable_semantic_dimensions(bundle, model)
        applicable.update(
            row.family_id
            for row in mandatory_families
            if row.activation_decision
            in {
                FamilyActivationDecision.ACTIVATE_BLOCKING,
                FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
            }
        )
        unresolved_activation_dimensions = {
            row.family_id
            for row in mandatory_families
            if row.activation_decision
            == FamilyActivationDecision.UNRESOLVED_APPLICABILITY
        }
        rows: list[ClosureDimensionResult] = []
        activated_subjects = [
            activation.subject
            for activation in activations
            if activation.question_family == ReasoningQuestionFamily.GOVERNING_SEMANTICS
            and any(
                signal.signal_id in activation.source_signal_ids for signal in signals
            )
        ]
        entities = list(
            dict.fromkeys((model.primary_entities or []) + activated_subjects)
        ) or ["AEM Guides behavior"]
        for entity in entities:
            for dimension in SemanticDimension:
                is_applicable = dimension in applicable
                applicability_unresolved = (
                    dimension in unresolved_activation_dimensions
                    or (
                        dimension == SemanticDimension.GENERATED_OUTPUT
                        and model.generated_artifact_delivery
                        == ApplicabilityState.UNRESOLVED
                    )
                )
                evidence_ids = [
                    record.evidence_id
                    for record in bundle.records
                    if any(
                        keyword in _record_text(record).casefold()
                        for keyword in _DIMENSION_KEYWORDS[dimension]
                    )
                ]
                if applicability_unresolved:
                    disposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED
                    rationale = (
                        "Current applicability is unresolved, so this material family "
                        "cannot be silently activated or discarded."
                    )
                elif not is_applicable:
                    disposition = ClosureDisposition.NOT_APPLICABLE
                    rationale = (
                        "The activated domains do not make this dimension material."
                    )
                elif evidence_ids:
                    disposition = ClosureDisposition.COVERED
                    rationale = "Direct supplied evidence addresses this dimension."
                else:
                    disposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED
                    rationale = "The dimension is applicable but the supplied evidence does not resolve it."
                rows.append(
                    ClosureDimensionResult(
                        entity=entity,
                        dimension=dimension,
                        applicability=(
                            ApplicabilityState.UNRESOLVED
                            if applicability_unresolved
                            else ApplicabilityState.APPLICABLE
                            if is_applicable
                            else ApplicabilityState.NOT_APPLICABLE
                        ),
                        disposition=disposition,
                        evidence_ids=evidence_ids,
                        rationale=rationale,
                    )
                )
        return rows

    def applicable_semantic_dimensions(
        self,
        bundle: CanonicalEvidenceBundle,
        model: CanonicalBehaviorModel,
    ) -> set[SemanticDimension]:
        """Return the existing deterministic domain/model family set."""

        combined = " ".join(
            _record_text(record) for record in bundle.records
        ).casefold()
        domains = set(model.domains)
        dita_like = bool(
            re.search(
                r"\b(dita|topicref|mapref|bookmap|ditaval|attribute|specialization)\b",
                combined,
            )
        )
        publishing = IssueDomain.PUBLISHING in domains
        ui = bool(_UI_SOURCES & {record.source_type for record in bundle.records})
        implementation = bool(
            _IMPLEMENTATION_SOURCES & {record.source_type for record in bundle.records}
        )
        applicable: set[SemanticDimension] = {
            SemanticDimension.GOVERNING_SEMANTICS,
            SemanticDimension.POSITIVE_STATE,
            SemanticDimension.NEGATIVE_STATE,
            SemanticDimension.LIFECYCLE,
            SemanticDimension.VERSION_APPLICABILITY,
            SemanticDimension.DEPLOYMENT_APPLICABILITY,
        }
        if dita_like:
            applicable.update(
                {
                    SemanticDimension.CONTROLLING_ATTRIBUTES,
                    SemanticDimension.PARENT_CONTEXT,
                    SemanticDimension.CHILD_CONTEXT,
                    SemanticDimension.HIERARCHY,
                    SemanticDimension.SPECIALIZATIONS,
                    SemanticDimension.REFERENCED_CONTENT,
                    SemanticDimension.NESTED_REFERENCED_CONTENT,
                    SemanticDimension.FALLBACK,
                    SemanticDimension.ABSENT_VALUE,
                    SemanticDimension.INVALID_VALUE,
                }
            )
        if publishing:
            applicable.update(
                {
                    SemanticDimension.GOVERNING_CONFIGURATION,
                    SemanticDimension.REFERENCED_CONTENT,
                    SemanticDimension.DOWNSTREAM_PROCESSOR,
                    SemanticDimension.PERSISTED_STATE,
                }
            )
        if model.generated_artifact_delivery == ApplicabilityState.APPLICABLE:
            applicable.add(SemanticDimension.GENERATED_OUTPUT)
        if ui:
            applicable.update(
                {
                    SemanticDimension.GOVERNING_CONFIGURATION,
                    SemanticDimension.CROSS_SURFACE_SYNC,
                    SemanticDimension.ROLE_PROFILE_APPLICABILITY,
                    SemanticDimension.FALLBACK,
                }
            )
        if implementation:
            applicable.update(
                {
                    SemanticDimension.DIRECT_CONSUMERS,
                    SemanticDimension.SIBLING_CONSUMERS,
                    SemanticDimension.DOWNSTREAM_PROCESSOR,
                    SemanticDimension.PERSISTED_STATE,
                }
            )
        return applicable

    def generate_missing_questions(
        self,
        closure: list[ClosureDimensionResult],
        scope: ScopeResolution,
        facts: ContractFactSet,
        investigation: QeInvestigationPreparation | None = None,
    ) -> list[MissingQuestion]:
        questions: list[MissingQuestion] = []
        families = {
            row.family_id: row
            for row in (investigation.mandatory_families if investigation else [])
            if row.activation_decision != FamilyActivationDecision.DO_NOT_ACTIVATE
        }
        unresolved_by_dimension: dict[
            SemanticDimension, list[ClosureDimensionResult]
        ] = defaultdict(list)
        for row in closure:
            if row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED:
                unresolved_by_dimension[row.dimension].append(row)
        for dimension, unresolved_rows in sorted(
            unresolved_by_dimension.items(), key=lambda item: item[0].value
        ):
            subject = _subject_for_dimension(dimension)
            entity_text = ", ".join(
                dict.fromkeys(row.entity for row in unresolved_rows)
            )
            family = families.get(dimension)
            target_sources = list(_target_sources(subject))
            if family is not None:
                for source in family.preferred_evidence_sources:
                    if source not in target_sources:
                        target_sources.append(source)
            questions.append(
                MissingQuestion(
                    question=_QUESTION_TEXT[dimension].format(entity=entity_text),
                    dimension=dimension,
                    authority_subject=subject,
                    target_source_types=target_sources,
                    blocking=(
                        family.activation_decision
                        == FamilyActivationDecision.ACTIVATE_BLOCKING
                        if family
                        else False
                    ),
                    source_closure_ids=[row.closure_id for row in unresolved_rows],
                )
            )
        scope_questions = {
            "ENABLE_DITA_OT_PROCESSING": (
                "Is Enable DITA-OT Processing expected to be ON, OFF, both, or not applicable?",
                True,
            ),
            "PRIMARY_PRESET_TYPE": (
                "Which exact output preset owns this functionality?",
                True,
            ),
            "OUT_OF_SCOPE": ("What should explicitly be out of scope?", False),
            "SHARED_PATH_OUTPUTS": (
                "Which other presets intentionally share this behavior?",
                False,
            ),
        }
        for field in scope.unresolved_fields:
            question, blocking = scope_questions.get(
                field, (f"What is the intended value for {field}?", True)
            )
            questions.append(
                MissingQuestion(
                    question=question,
                    authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                    target_source_types=_target_sources(
                        AuthoritySubject.PRODUCT_CONTRACT
                    ),
                    blocking=blocking,
                )
            )
        for fact in facts.facts:
            if fact.fact_type != ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED:
                continue
            questions.append(
                MissingQuestion(
                    question=f'What exact product behavior does the human term "{fact.literal}" mean?',
                    authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                    target_source_types=_target_sources(
                        AuthoritySubject.PRODUCT_CONTRACT
                    ),
                    blocking=True,
                    source_fact_ids=[fact.fact_id],
                )
            )
        return sorted(
            {row.question_id: row for row in questions}.values(),
            key=lambda row: row.question_id,
        )

    def build_question_generation_trace(
        self,
        *,
        bundle: CanonicalEvidenceBundle,
        facts: ContractFactSet,
        surfaces: list[ChangeSurface],
        signals: list[AbstractSignal],
        activations: list[ReasoningPatternActivation],
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        investigation: QeInvestigationPreparation | None = None,
    ) -> QuestionGenerationDiagnosticTrace:
        """Build ordered, content-minimal proof of question-generation lineage."""

        current_issue_evidence_ids = {
            record.evidence_id
            for record in bundle.records
            if record.source_type in _CURRENT_ISSUE_BEHAVIOR_SOURCES
        }
        material_behavior_expected = (
            _material_behavior_fact(
                facts,
                allowed_evidence_ids=current_issue_evidence_ids,
            )
            is not None
        )
        behavior_surfaces = [
            row for row in surfaces if row.kind == ChangeSurfaceKind.CHANGED_BEHAVIOR
        ]
        governing_activations = [
            row
            for row in activations
            if row.question_family == ReasoningQuestionFamily.GOVERNING_SEMANTICS
        ]
        governing_subjects = {row.subject for row in governing_activations}
        governing_closure = [
            row
            for row in closure
            if row.dimension == SemanticDimension.GOVERNING_SEMANTICS
            and row.entity in governing_subjects
        ]
        governing_questions = [
            row
            for row in questions
            if row.dimension == SemanticDimension.GOVERNING_SEMANTICS
            and any(subject in row.question for subject in governing_subjects)
        ]

        surface_failure = (
            QuestionGenerationFailureReason.SIGNAL_MISSING
            if material_behavior_expected and not behavior_surfaces
            else None
        )
        signal_failure = (
            QuestionGenerationFailureReason.SIGNAL_MISSING
            if material_behavior_expected and behavior_surfaces and not signals
            else None
        )
        router_failure = (
            QuestionGenerationFailureReason.PATTERN_NOT_ACTIVATED
            if signals and not governing_activations
            else None
        )
        closure_failure = (
            QuestionGenerationFailureReason.CLOSURE_TRAVERSAL_STOPPED
            if governing_activations and not governing_closure
            else None
        )
        unresolved_governing = [
            row
            for row in governing_closure
            if row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED
        ]
        question_failure = (
            QuestionGenerationFailureReason.QUESTION_FAMILY_NOT_GENERATED
            if unresolved_governing and not governing_questions
            else None
        )

        steps = [
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.CHANGE_SURFACE_EXTRACTOR,
                sequence=1,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if surface_failure
                    else QuestionGenerationStepOutcome.PRODUCED
                    if behavior_surfaces
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=facts.source_evidence_ids,
                output_ids=[row.surface_id for row in behavior_surfaces],
                failure_reason=surface_failure,
                detail_code=(
                    "SOURCE_ANCHORED_CHANGED_BEHAVIOR"
                    if behavior_surfaces
                    else "NO_MATERIAL_CHANGED_BEHAVIOR"
                ),
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.ABSTRACT_SIGNAL_EXTRACTOR,
                sequence=2,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if signal_failure
                    else QuestionGenerationStepOutcome.PRODUCED
                    if signals
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.surface_id for row in behavior_surfaces],
                output_ids=[row.signal_id for row in signals],
                failure_reason=signal_failure,
                detail_code="CHANGED_BEHAVIOR_SIGNAL",
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.REASONING_PATTERN_ROUTER,
                sequence=3,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if router_failure
                    else QuestionGenerationStepOutcome.ACTIVATED
                    if governing_activations
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.signal_id for row in signals],
                output_ids=[row.activation_id for row in governing_activations],
                failure_reason=router_failure,
                detail_code="CHANGED_BEHAVIOR_TO_GOVERNING_SEMANTICS",
            ),
            QuestionGenerationTraceStep(
                stage=(
                    QuestionGenerationTraceStage.SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER
                ),
                sequence=4,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if closure_failure
                    else QuestionGenerationStepOutcome.TRAVERSED
                    if governing_closure
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.activation_id for row in governing_activations],
                output_ids=[row.closure_id for row in governing_closure],
                failure_reason=closure_failure,
                detail_code="GOVERNING_SEMANTICS_CLOSURE",
            ),
            QuestionGenerationTraceStep(
                stage=QuestionGenerationTraceStage.MISSING_QUESTION_GENERATOR,
                sequence=5,
                outcome=(
                    QuestionGenerationStepOutcome.FAILED
                    if question_failure
                    else QuestionGenerationStepOutcome.GENERATED
                    if governing_questions
                    else QuestionGenerationStepOutcome.RESOLVED_WITHOUT_QUESTION
                    if governing_closure and not unresolved_governing
                    else QuestionGenerationStepOutcome.NO_MATERIAL_SIGNAL
                ),
                input_ids=[row.closure_id for row in governing_closure],
                output_ids=[row.question_id for row in governing_questions],
                failure_reason=question_failure,
                detail_code="GOVERNING_SEMANTICS_QUESTION_FAMILY",
            ),
        ]
        first_failure = next(
            (row.failure_reason for row in steps if row.failure_reason), None
        )
        return QuestionGenerationDiagnosticTrace(
            steps=steps,
            earliest_failure=first_failure,
            recovered_failure=(
                QuestionGenerationFailureReason.SIGNAL_MISSING
                if behavior_surfaces
                else None
            ),
            governing_pattern_ids=[row.pattern_id for row in governing_activations],
            pattern_provider_status=(
                investigation.pattern_lookup.status if investigation else None
            ),
            matched_human_pattern_ids=(
                [row.pattern_id for row in investigation.matched_human_patterns]
                if investigation
                else []
            ),
            mandatory_family_ids=(
                [
                    row.family_id
                    for row in investigation.mandatory_families
                    if row.activation_decision
                    != FamilyActivationDecision.DO_NOT_ACTIVATE
                ]
                if investigation
                else []
            ),
            family_activation_decisions=(
                {
                    row.family_id: row.activation_decision
                    for row in investigation.mandatory_families
                }
                if investigation
                else {}
            ),
        )

    def retrieve_for_questions(
        self, bundle: CanonicalEvidenceBundle, questions: list[MissingQuestion]
    ) -> list[DirectedRetrievalRecord]:
        retrievals: list[DirectedRetrievalRecord] = []
        for question in questions:
            query_terms = _words(question.question)
            candidates: list[EvidenceRecord] = []
            for record in bundle.records:
                if is_github_implementation_result_record(record):
                    continue
                if record.source_type not in question.target_source_types:
                    continue
                record_terms = _words(_record_text(record))
                if query_terms & record_terms:
                    candidates.append(record)
            retrievals.append(
                DirectedRetrievalRecord(
                    question_id=question.question_id,
                    query=question.question,
                    authority_subject=question.authority_subject,
                    target_source_types=question.target_source_types,
                    matched_evidence_ids=[record.evidence_id for record in candidates],
                    status=RetrievalStatus.USED
                    if candidates
                    else RetrievalStatus.UNAVAILABLE,
                    reason=(
                        "Targeted supplied evidence matched the question."
                        if candidates
                        else "No supplied evidence matched; absence is not treated as rejection."
                    ),
                )
            )
        return retrievals

    def verify_hypotheses(
        self,
        bundle: CanonicalEvidenceBundle,
        questions: list[MissingQuestion],
        retrievals: list[DirectedRetrievalRecord],
        model: CanonicalBehaviorModel,
        *,
        scope: ScopeResolution | None = None,
        request: GenerationRequest | None = None,
        semantic_evidence: list[AuthorizedSemanticEvidence] | None = None,
        local_evidence_ids: set[str] | None = None,
    ) -> tuple[list[BehaviorHypothesis], CanonicalBehaviorModel]:
        records = {row.evidence_id: row for row in bundle.records}
        question_by_id = {row.question_id: row for row in questions}
        retrieval_by_question = {row.question_id: row for row in retrievals}
        provider_record_ids = {
            row.evidence_id
            for row in bundle.records
            if row.retrieval_pass == "reasoning-directed-provider"  # noqa: S105
        }
        authorizations_by_pair: dict[
            tuple[str, str], list[AuthorizedSemanticEvidence]
        ] = defaultdict(list)
        authorized_evidence_ids: set[str] = set()
        authorization_now = datetime.now(timezone.utc)
        for handoff in semantic_evidence or []:
            authorization = handoff.authorization
            binding = authorization.source_attestation.binding
            record = records.get(binding.evidence_id)
            question = question_by_id.get(binding.question_id)
            retrieval = retrieval_by_question.get(binding.question_id)
            if (
                request is None
                or record is None
                or question is None
                or retrieval is None
                or not _semantic_handoff_is_current(
                    handoff,
                    request=request,
                    record=record,
                    question=question,
                    retrieval=retrieval,
                    local_evidence_ids=set(local_evidence_ids or ()),
                    now=authorization_now,
                )
            ):
                continue
            authorizations_by_pair[(binding.question_id, binding.evidence_id)].append(
                handoff
            )
            authorized_evidence_ids.add(binding.evidence_id)
        provider_evidence_ids = provider_record_ids | authorized_evidence_ids
        provider_conflict_ids: set[str] = set()
        for conflict in bundle.authority_conflicts:
            conflict_ids = set(conflict.selected_evidence_ids) | set(
                conflict.competing_evidence_ids
            )
            if conflict_ids & provider_evidence_ids:
                provider_conflict_ids |= conflict_ids
        if bundle.currentness_conflicts:
            provider_conflict_claims = {
                claim_key
                for row in bundle.records
                if row.evidence_id in provider_evidence_ids
                for claim_key in row.claim_keys
                if claim_key in bundle.currentness_conflicts
            }
            provider_conflict_ids |= {
                row.evidence_id
                for row in bundle.records
                if set(row.claim_keys) & provider_conflict_claims
            }
        hypotheses: list[BehaviorHypothesis] = []
        for retrieval in retrievals:
            question = question_by_id[retrieval.question_id]
            all_matched = [
                records[evidence_id] for evidence_id in retrieval.matched_evidence_ids
            ]
            supporting_rows: list[EvidenceRecord] = []
            support_confidence: dict[str, float] = {}
            contradicting_ids: set[str] = set()
            for row in all_matched:
                if not _implementation_evidence_matches_scope(row, scope):
                    continue
                authorizations = authorizations_by_pair.get(
                    (retrieval.question_id, row.evidence_id),
                    [],
                )
                if authorizations:
                    stances = {
                        handoff.authorization.question_assessment.stance
                        for handoff in authorizations
                    }
                    if QuestionEvidenceStance.CONTRADICTS in stances:
                        contradicting_ids.add(row.evidence_id)
                        continue
                    supports = [
                        handoff
                        for handoff in authorizations
                        if handoff.authorization.question_assessment.stance
                        == QuestionEvidenceStance.SUPPORTS
                    ]
                    if supports:
                        supporting_rows.append(row)
                        support_confidence[row.evidence_id] = max(
                            handoff.authorization.question_assessment.assessment_confidence
                            for handoff in supports
                        )
                    continue
                if row.evidence_id in provider_record_ids:
                    continue
                supporting_rows.append(row)
                support_confidence[row.evidence_id] = row.evidence_confidence
            supporting_ids = [row.evidence_id for row in supporting_rows]
            conflict_ids = (
                set(supporting_ids) & provider_conflict_ids & provider_evidence_ids
            )
            contradicting_ids |= conflict_ids
            supporting_ids = sorted(set(supporting_ids) - contradicting_ids)
            if contradicting_ids:
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif not supporting_ids:
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif not _implementation_scope_fully_covered(
                supporting_rows,
                question,
                scope,
            ):
                state = HypothesisState.UNRESOLVED
                confidence = 0.0
            elif any(
                support_confidence[evidence_id] >= 0.8 for evidence_id in supporting_ids
            ):
                state = HypothesisState.CONFIRMED
                confidence = max(
                    support_confidence[evidence_id] for evidence_id in supporting_ids
                )
            else:
                state = HypothesisState.INFERRED_HIGH_CONFIDENCE
                confidence = max(
                    support_confidence[evidence_id] for evidence_id in supporting_ids
                )
            hypotheses.append(
                BehaviorHypothesis(
                    statement=question.question,
                    state=state,
                    supporting_evidence_ids=supporting_ids,
                    contradicting_evidence_ids=sorted(contradicting_ids),
                    derived_from_question_id=question.question_id,
                    confidence=confidence,
                )
            )
        nodes = list(model.graph.nodes)
        edges = list(model.graph.edges)
        evidence_nodes = {
            evidence_id: node
            for node in nodes
            if node.node_type == "EVIDENCE_SOURCE"
            for evidence_id in node.source_evidence_ids
        }
        provider_ids_in_retrievals = {
            evidence_id
            for hypothesis in hypotheses
            for evidence_id in (
                list(hypothesis.supporting_evidence_ids)
                + list(hypothesis.contradicting_evidence_ids)
            )
            if evidence_id in provider_evidence_ids
        }
        contradiction_ids_in_retrievals = {
            evidence_id
            for hypothesis in hypotheses
            for evidence_id in hypothesis.contradicting_evidence_ids
        }
        graph_evidence_ids = (
            provider_ids_in_retrievals | contradiction_ids_in_retrievals
        )
        for evidence_id in sorted(graph_evidence_ids):
            if evidence_id in evidence_nodes:
                continue
            record = records[evidence_id]
            evidence_node = BehaviorGraphNode(
                label=record.source_reference,
                node_type="EVIDENCE_SOURCE",
                source_evidence_ids=[record.evidence_id],
                authoritative=_is_authoritative(record),
            )
            nodes.append(evidence_node)
            evidence_nodes[evidence_id] = evidence_node
        for hypothesis in hypotheses:
            hypothesis_evidence_ids = sorted(
                set(hypothesis.supporting_evidence_ids)
                | set(hypothesis.contradicting_evidence_ids)
            )
            if not hypothesis_evidence_ids:
                continue
            question = question_by_id[hypothesis.derived_from_question_id]
            hypothesis_node = BehaviorGraphNode(
                label=hypothesis.statement,
                node_type="VERIFIED_HYPOTHESIS",
                source_evidence_ids=hypothesis_evidence_ids,
                authoritative=(
                    hypothesis.state == HypothesisState.CONFIRMED
                    and not hypothesis.contradicting_evidence_ids
                ),
            )
            nodes.append(hypothesis_node)
            for evidence_id in hypothesis.supporting_evidence_ids:
                evidence_node = evidence_nodes.get(evidence_id)
                if evidence_node is None:
                    continue
                record = records[evidence_id]
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=hypothesis_node.node_id,
                        target_node_id=evidence_node.node_id,
                        relation=_relation_for_dimension(question.dimension),
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=question.authority_subject,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=hypothesis.confidence,
                        verification_state=hypothesis.state,
                    )
                )
            for evidence_id in hypothesis.contradicting_evidence_ids:
                evidence_node = evidence_nodes.get(evidence_id)
                if evidence_node is None:
                    continue
                record = records[evidence_id]
                contradiction_confidence = max(
                    (
                        handoff.authorization.question_assessment.assessment_confidence
                        for handoff in authorizations_by_pair.get(
                            (question.question_id, evidence_id),
                            [],
                        )
                        if handoff.authorization.question_assessment.stance
                        == QuestionEvidenceStance.CONTRADICTS
                    ),
                    default=0.0,
                )
                edges.append(
                    BehaviorGraphEdge(
                        source_node_id=hypothesis_node.node_id,
                        target_node_id=evidence_node.node_id,
                        relation=BehaviorRelationType.CONTRADICTED_BY,
                        provenance_evidence_ids=[evidence_id],
                        authority_subject=question.authority_subject,
                        authority_class=record.requirement_authority,
                        currentness=record.currentness,
                        confidence=contradiction_confidence,
                        verification_state=HypothesisState.UNRESOLVED,
                    )
                )
        enriched_model = model.model_copy(
            update={"graph": BehaviorGraph(nodes=nodes, edges=edges)}
        )
        return hypotheses, enriched_model

    def model_domain_impact(
        self,
        bundle: CanonicalEvidenceBundle,
        domains: list[DomainActivation],
        model: CanonicalBehaviorModel,
    ) -> list[DomainImpact]:
        text = " ".join(
            _positive_scope_clauses([_record_text(record) for record in bundle.records])
        ).casefold()
        scale_text = _scale_detection_text(text)
        nfr_signals = [
            signal
            for signal in (
                "bulk",
                "thousand",
                "large query",
                "deep hierarchy",
                "many references",
                "concurrency",
                "repeated processing",
            )
            if signal in scale_text
        ]
        if re.search(
            r"\b(?:\d{1,3}(?:,\d{3})+|\d{4,}|\d+(?:\.\d+)?\s*k)\b"
            r".{0,40}\b(?:documents?|pages?|items?|maps?|topics?)\b",
            scale_text,
        ):
            nfr_signals.append("explicit high cardinality")
        return [
            DomainImpact(
                domain=activation.domain,
                materially_affected_entities=model.primary_entities,
                observable_outcomes=(
                    model.generated_output_oracles
                    if activation.domain == IssueDomain.PUBLISHING
                    else ["VISIBLE_BEHAVIOR_MATCHES_CONTRACT"]
                ),
                nfr_applicable=bool(nfr_signals),
                nfr_triggers=nfr_signals,
                evidence_ids=activation.evidence_ids,
            )
            for activation in domains
        ]

    def classify_coverage(
        self,
        facts: ContractFactSet,
        closure: list[ClosureDimensionResult],
        impacts: list[DomainImpact],
        hypotheses: list[BehaviorHypothesis],
        scope: ScopeResolution,
        questions: list[MissingQuestion],
    ) -> list[CoverageDispositionRecord]:
        rows: list[CoverageDispositionRecord] = []
        out_scope_values = [_scope_clause_value(value) for value in scope.out_of_scope]
        for fact in facts.facts:
            if fact.fact_type == ContractFactType.OUT_OF_SCOPE:
                disposition = CoverageDisposition.OUT_OF_SCOPE
            elif any(
                value and value in fact.literal.casefold() for value in out_scope_values
            ):
                disposition = CoverageDisposition.OUT_OF_SCOPE
            elif fact.fact_type in {
                ContractFactType.HUMAN_OPEN_QUESTIONS,
                ContractFactType.ENGINEERING_DESIGN_QUESTIONS,
                ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
            }:
                disposition = CoverageDisposition.OPEN_QUESTION
            elif fact.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR:
                if _REGRESSION_ONLY_RE.search(fact.literal):
                    disposition = CoverageDisposition.SEMANTIC_REGRESSION
                else:
                    disposition = (
                        CoverageDisposition.ACCEPTANCE_CONTRACT
                        if fact.authority_class in _ACCEPTED_AUTHORITIES
                        else CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                    )
            elif fact.fact_type == ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS:
                disposition = CoverageDisposition.NEGATIVE_BOUNDARY
            else:
                disposition = CoverageDisposition.CONFIGURATION_VARIANT
            rows.append(
                CoverageDispositionRecord(
                    candidate=fact.literal,
                    disposition=disposition,
                    source_fact_ids=[fact.fact_id],
                    evidence_ids=fact.source_evidence_ids,
                    rationale="Classified from an explicitly preserved contract fact.",
                )
            )
        dimension_disposition = {
            SemanticDimension.GENERATED_OUTPUT: CoverageDisposition.GENERATED_OUTPUT_VALIDATION,
            SemanticDimension.REFERENCED_CONTENT: CoverageDisposition.REFERENCE_REGRESSION,
            SemanticDimension.NESTED_REFERENCED_CONTENT: CoverageDisposition.REFERENCE_REGRESSION,
            SemanticDimension.PARENT_CONTEXT: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.CHILD_CONTEXT: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.HIERARCHY: CoverageDisposition.STRUCTURAL_REGRESSION,
            SemanticDimension.SPECIALIZATIONS: CoverageDisposition.SEMANTIC_REGRESSION,
            SemanticDimension.LIFECYCLE: CoverageDisposition.LIFECYCLE_COVERAGE,
            SemanticDimension.NEGATIVE_STATE: CoverageDisposition.NEGATIVE_BOUNDARY,
            SemanticDimension.INVALID_VALUE: CoverageDisposition.NEGATIVE_BOUNDARY,
            SemanticDimension.DOWNSTREAM_PROCESSOR: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.PERSISTED_STATE: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.DIRECT_CONSUMERS: CoverageDisposition.IMPLEMENTATION_ORACLE,
            SemanticDimension.SIBLING_CONSUMERS: CoverageDisposition.IMPLEMENTATION_ORACLE,
        }
        closure_groups: dict[
            tuple[SemanticDimension, ClosureDisposition], list[ClosureDimensionResult]
        ] = defaultdict(list)
        for item in closure:
            if item.disposition != ClosureDisposition.NOT_APPLICABLE:
                closure_groups[(item.dimension, item.disposition)].append(item)
        questions_by_closure_id: dict[str, list[MissingQuestion]] = defaultdict(list)
        for question in questions:
            for closure_id in question.source_closure_ids:
                questions_by_closure_id[closure_id].append(question)
        hypotheses_by_question: dict[str, list[BehaviorHypothesis]] = defaultdict(list)
        for hypothesis in hypotheses:
            if hypothesis.derived_from_question_id:
                hypotheses_by_question[hypothesis.derived_from_question_id].append(
                    hypothesis
                )
        linked_hypothesis_ids: set[str] = set()
        for (dimension, closure_disposition), items in sorted(
            closure_groups.items(),
            key=lambda item: (item[0][0].value, item[0][1].value),
        ):
            related_questions = sorted(
                {
                    question.question_id: question
                    for item in items
                    for question in questions_by_closure_id.get(item.closure_id, [])
                }.values(),
                key=lambda row: row.question_id,
            )
            related_hypotheses = sorted(
                {
                    hypothesis.hypothesis_id: hypothesis
                    for question in related_questions
                    for hypothesis in hypotheses_by_question.get(
                        question.question_id, []
                    )
                }.values(),
                key=lambda row: row.hypothesis_id,
            )
            linked_hypothesis_ids.update(
                hypothesis.hypothesis_id for hypothesis in related_hypotheses
            )
            hypothesis_states = {row.state for row in related_hypotheses}
            if HypothesisState.UNRESOLVED in hypothesis_states:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "The material hypothesis remains unresolved after targeted "
                    "retrieval and verification."
                )
            elif len(hypothesis_states) > 1:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "Material hypotheses have conflicting terminal states and "
                    "require a visible decision."
                )
            elif related_hypotheses and hypothesis_states == {HypothesisState.REJECTED}:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = "Targeted evidence rejected the material hypothesis."
            elif related_hypotheses:
                disposition = dimension_disposition.get(
                    dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = (
                    "Targeted evidence verified applicability; the result remains "
                    "QE coverage and is not promoted to product acceptance."
                )
            elif closure_disposition == ClosureDisposition.INVESTIGATED_AND_REJECTED:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = items[0].rationale
            elif closure_disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = items[0].rationale
            else:
                disposition = dimension_disposition.get(
                    dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = items[0].rationale
            entities = ", ".join(dict.fromkeys(item.entity for item in items))
            candidate = f"{dimension.value}: {entities}"
            if (
                disposition == CoverageDisposition.OPEN_QUESTION
                and len(related_questions) == 1
            ):
                candidate = related_questions[0].question
            rows.append(
                CoverageDispositionRecord(
                    candidate=candidate,
                    disposition=disposition,
                    source_closure_ids=[item.closure_id for item in items],
                    source_question_ids=[
                        question.question_id for question in related_questions
                    ],
                    source_hypothesis_ids=[
                        hypothesis.hypothesis_id for hypothesis in related_hypotheses
                    ],
                    evidence_ids=[
                        evidence_id
                        for item in items
                        for evidence_id in item.evidence_ids
                    ]
                    + [
                        evidence_id
                        for hypothesis in related_hypotheses
                        for evidence_id in (
                            hypothesis.supporting_evidence_ids
                            + hypothesis.contradicting_evidence_ids
                            + hypothesis.verification_evidence_ids
                        )
                    ],
                    rationale=rationale,
                )
            )
        for impact in impacts:
            if impact.nfr_applicable:
                rows.append(
                    CoverageDispositionRecord(
                        candidate=f"Validate {impact.domain.value} under: {', '.join(impact.nfr_triggers)}",
                        disposition=CoverageDisposition.NFR_COVERAGE,
                        evidence_ids=impact.evidence_ids,
                        rationale="NFR coverage is activated by explicit change-impact signals; no SLA is invented.",
                    )
                )
        questions_by_id = {row.question_id: row for row in questions}
        for hypothesis in hypotheses:
            if hypothesis.hypothesis_id in linked_hypothesis_ids:
                continue
            question = questions_by_id.get(hypothesis.derived_from_question_id)
            if hypothesis.state == HypothesisState.UNRESOLVED:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = "The material hypothesis remains unresolved."
            elif hypothesis.state == HypothesisState.REJECTED:
                disposition = CoverageDisposition.INVESTIGATED_AND_REJECTED
                rationale = "Targeted evidence rejected the material hypothesis."
            elif question is not None and question.dimension is not None:
                disposition = dimension_disposition.get(
                    question.dimension, CoverageDisposition.SEMANTIC_REGRESSION
                )
                rationale = (
                    "Targeted evidence verified applicability; the result remains "
                    "QE coverage and is not promoted to product acceptance."
                )
            else:
                disposition = CoverageDisposition.OPEN_QUESTION
                rationale = (
                    "Evidence was found, but no canonical answer value was extracted; "
                    "the material product decision remains visible."
                )
            rows.append(
                CoverageDispositionRecord(
                    candidate=hypothesis.statement,
                    disposition=disposition,
                    source_question_ids=(
                        [hypothesis.derived_from_question_id]
                        if hypothesis.derived_from_question_id
                        else []
                    ),
                    source_hypothesis_ids=[hypothesis.hypothesis_id],
                    evidence_ids=(
                        hypothesis.supporting_evidence_ids
                        + hypothesis.contradicting_evidence_ids
                        + hypothesis.verification_evidence_ids
                    ),
                    rationale=rationale,
                )
            )
        return sorted(
            {row.disposition_id: row for row in rows}.values(),
            key=lambda row: row.disposition_id,
        )

    def resolve_acceptance_contract_with_trace(
        self,
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord],
        questions: list[MissingQuestion],
    ) -> AcceptanceResolutionBatch:
        facts_by_id = {row.fact_id: row for row in facts.facts}
        accepted_literals = [
            row.literal
            for row in facts.facts
            if row.authority_class in _ACCEPTED_AUTHORITIES
            and row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
        ]
        blocking_ids = [row.question_id for row in questions if row.blocking]
        discovered_candidates: list[AcceptanceCandidate] = []
        for row in dispositions:
            if row.disposition not in {
                CoverageDisposition.ACCEPTANCE_CONTRACT,
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            }:
                continue
            source_facts = [
                facts_by_id[fact_id]
                for fact_id in row.source_fact_ids
                if fact_id in facts_by_id
            ]
            accepted_human_contract = any(
                fact.authority_class in _ACCEPTED_AUTHORITIES for fact in source_facts
            )
            exact_types = {
                ContractFactType.EXACT_VALUES,
                ContractFactType.COUNTS,
                ContractFactType.LIMITS,
                ContractFactType.COLORS,
                ContractFactType.EXACT_DEFAULTS,
                ContractFactType.EXACT_STATUS_NAMES,
            }
            has_exactness = bool(
                re.search(
                    r"(?:\b\d+(?:\.\d+)?\b|#[0-9a-f]{3,8}\b)",
                    row.candidate,
                    re.IGNORECASE,
                )
            )
            supporting_exact_facts = [
                fact
                for fact in facts.facts
                if fact.fact_type in exact_types and fact.literal == row.candidate
            ]
            exact_supported = (
                not has_exactness
                or bool(supporting_exact_facts)
                and all(fact.authoritative for fact in supporting_exact_facts)
            )
            discovered_candidates.append(
                AcceptanceCandidate(
                    statement=row.candidate,
                    contract_mode=facts.contract_mode,
                    accepted_human_contract=accepted_human_contract,
                    source_fact_ids=row.source_fact_ids,
                    source_disposition_ids=[row.disposition_id],
                    evidence_ids=row.evidence_ids,
                    in_scope=True,
                    observable=bool(row.candidate.strip()),
                    regression_only=bool(_REGRESSION_ONLY_RE.search(row.candidate)),
                    implementation_mechanics_only=bool(
                        _IMPLEMENTATION_MECHANICS_RE.search(row.candidate)
                    ),
                    exact_values_supported=exact_supported,
                    contradicts_human_contract=(
                        not accepted_human_contract
                        and _contradicts_accepted_contract(
                            row.candidate, accepted_literals
                        )
                    ),
                    unresolved_decision_ids=(
                        [] if accepted_human_contract else blocking_ids
                    ),
                )
            )
        grouped: dict[tuple[str, ...], list[AcceptanceCandidate]] = defaultdict(list)
        for candidate in discovered_candidates:
            grouped[_semantic_candidate_key(candidate.statement)].append(candidate)

        final_candidates: list[AcceptanceCandidate] = []
        dedup_decisions: list[CandidateDedupDecision] = []
        for semantic_key, group in sorted(grouped.items(), key=lambda item: item[0]):
            if len(group) == 1:
                final_candidates.append(group[0])
                continue

            def candidate_rank(candidate: AcceptanceCandidate) -> tuple[bool, bool, int, str]:
                return (
                    candidate.accepted_human_contract,
                    all(
                        facts_by_id[fact_id].authoritative
                        for fact_id in candidate.source_fact_ids
                        if fact_id in facts_by_id
                    ),
                    -len(candidate.statement),
                    candidate.statement,
                )

            selected = max(group, key=candidate_rank)
            accepted_human_contract = any(
                row.accepted_human_contract for row in group
            )
            survivor = AcceptanceCandidate(
                statement=selected.statement,
                contract_mode=selected.contract_mode,
                accepted_human_contract=accepted_human_contract,
                source_fact_ids=sorted(
                    {value for row in group for value in row.source_fact_ids}
                ),
                source_disposition_ids=sorted(
                    {value for row in group for value in row.source_disposition_ids}
                ),
                evidence_ids=sorted(
                    {value for row in group for value in row.evidence_ids}
                ),
                in_scope=all(row.in_scope for row in group),
                observable=all(row.observable for row in group),
                regression_only=any(row.regression_only for row in group),
                implementation_mechanics_only=any(
                    row.implementation_mechanics_only for row in group
                ),
                exact_values_supported=all(
                    row.exact_values_supported for row in group
                ),
                contradicts_human_contract=any(
                    row.contradicts_human_contract for row in group
                ),
                unresolved_decision_ids=(
                    []
                    if accepted_human_contract
                    else sorted(
                        {
                            value
                            for row in group
                            for value in row.unresolved_decision_ids
                        }
                    )
                ),
            )
            final_candidates.append(survivor)
            dedup_decisions.append(
                CandidateDedupDecision(
                    merged_candidate_ids=[row.candidate_id for row in group],
                    surviving_candidate_id=survivor.candidate_id,
                    merge_reason=(
                        "Candidates have the same polarity and ordered outcome terms "
                        "after grammatical filler is removed."
                    ),
                    semantic_equivalence_basis=" | ".join(semantic_key),
                )
            )
        return AcceptanceResolutionBatch(
            discovered_candidates=discovered_candidates,
            candidates=final_candidates,
            dedup_decisions=dedup_decisions,
        )

    def resolve_acceptance_contract(
        self,
        facts: ContractFactSet,
        dispositions: list[CoverageDispositionRecord],
        questions: list[MissingQuestion],
    ) -> list[AcceptanceCandidate]:
        """Compatibility projection of the traced acceptance resolution."""

        return self.resolve_acceptance_contract_with_trace(
            facts, dispositions, questions
        ).candidates

    def behavioral_completeness_gate(
        self,
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        scope: ScopeResolution,
        hypotheses: list[BehaviorHypothesis],
        dispositions: list[CoverageDispositionRecord],
        question_quality: MissingQuestionQualityReport | None = None,
    ) -> GateDecision:
        questions_by_id = {row.question_id: row for row in questions}
        question_closure_ids = {
            closure_id
            for question in questions
            for closure_id in question.source_closure_ids
        }
        dispositions_by_closure_id: dict[str, list[CoverageDispositionRecord]] = (
            defaultdict(list)
        )
        dispositions_by_hypothesis_id: dict[str, list[CoverageDispositionRecord]] = (
            defaultdict(list)
        )
        for disposition in dispositions:
            for closure_id in disposition.source_closure_ids:
                dispositions_by_closure_id[closure_id].append(disposition)
            for hypothesis_id in disposition.source_hypothesis_ids:
                dispositions_by_hypothesis_id[hypothesis_id].append(disposition)
        failures: list[str] = []
        nonblocking_unsatisfied_families: set[SemanticDimension] = set()
        if question_quality is not None:
            for family in question_quality.family_satisfaction:
                if (
                    family.status == InvestigationFamilySatisfactionStatus.UNSATISFIED
                    and family.activation_decision
                    == FamilyActivationDecision.ACTIVATE_NON_BLOCKING
                ):
                    nonblocking_unsatisfied_families.add(family.family_id)
                if (
                    family.status == InvestigationFamilySatisfactionStatus.UNSATISFIED
                    and family.activation_decision
                    == FamilyActivationDecision.ACTIVATE_BLOCKING
                ):
                    failures.append(
                        "Blocking investigation family has no valid contextual question "
                        "or evidence-backed resolution: "
                        f"{family.family_id.value}"
                    )
        for row in closure:
            if row.applicability == ApplicabilityState.NOT_APPLICABLE:
                continue
            if row.disposition == ClosureDisposition.NOT_APPLICABLE:
                failures.append(f"Applicable dimension was discarded: {row.closure_id}")
            terminal_rows = dispositions_by_closure_id.get(row.closure_id, [])
            if len(terminal_rows) != 1:
                failures.append(
                    "Material closure requires exactly one terminal disposition: "
                    f"{row.closure_id} (found {len(terminal_rows)})"
                )
            if (
                row.disposition == ClosureDisposition.UNRESOLVED_AND_EXPOSED
                and row.closure_id not in question_closure_ids
                and row.dimension not in nonblocking_unsatisfied_families
            ):
                failures.append(
                    f"Unresolved closure is not exposed by exact lineage: {row.closure_id}"
                )
        for hypothesis in hypotheses:
            terminal_rows = dispositions_by_hypothesis_id.get(
                hypothesis.hypothesis_id, []
            )
            if len(terminal_rows) != 1:
                failures.append(
                    "Material hypothesis requires exactly one terminal disposition: "
                    f"{hypothesis.hypothesis_id} (found {len(terminal_rows)})"
                )
                continue
            disposition = terminal_rows[0].disposition
            question = questions_by_id.get(hypothesis.derived_from_question_id)
            if hypothesis.state == HypothesisState.UNRESOLVED and disposition not in {
                CoverageDisposition.OPEN_QUESTION,
                CoverageDisposition.PRODUCT_SCOPE_QUESTION,
            }:
                failures.append(
                    "Unresolved material hypothesis is not exposed as an open "
                    f"question: {hypothesis.hypothesis_id}"
                )
            elif hypothesis.state == HypothesisState.REJECTED and disposition not in {
                CoverageDisposition.INVESTIGATED_AND_REJECTED,
                CoverageDisposition.OUT_OF_SCOPE,
            }:
                failures.append(
                    "Rejected material hypothesis lacks a rejected/out-of-scope "
                    f"disposition: {hypothesis.hypothesis_id}"
                )
            elif (
                hypothesis.state
                in {
                    HypothesisState.CONFIRMED,
                    HypothesisState.INFERRED_HIGH_CONFIDENCE,
                }
                and question is not None
                and question.dimension is not None
                and disposition
                not in {
                    CoverageDisposition.SEMANTIC_REGRESSION,
                    CoverageDisposition.STRUCTURAL_REGRESSION,
                    CoverageDisposition.CONFIGURATION_VARIANT,
                    CoverageDisposition.REFERENCE_REGRESSION,
                    CoverageDisposition.GENERATED_OUTPUT_VALIDATION,
                    CoverageDisposition.NEGATIVE_BOUNDARY,
                    CoverageDisposition.FAILURE_RECOVERY,
                    CoverageDisposition.CROSS_MODE_REGRESSION,
                    CoverageDisposition.LIFECYCLE_COVERAGE,
                    CoverageDisposition.NFR_COVERAGE,
                    CoverageDisposition.IMPLEMENTATION_ORACLE,
                    CoverageDisposition.TECHNICAL_NOTE,
                }
            ):
                failures.append(
                    "Verified material hypothesis did not reach QE regression "
                    f"coverage: {hypothesis.hypothesis_id}"
                )
        if (
            scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED
            and not any("DITA-OT" in row.question for row in questions)
        ):
            failures.append("Publishing DITA-OT scope is unresolved but hidden.")
        return GateDecision(
            gate="BehavioralCompletenessGate",
            status=GateStatus.FAILED if failures else GateStatus.PASSED,
            failures=failures,
            checked_ids=sorted(
                {row.closure_id for row in closure}
                | {row.question_id for row in questions}
                | (
                    {
                        f"family:{row.family_id.value}"
                        for row in question_quality.family_satisfaction
                    }
                    if question_quality is not None
                    else set()
                )
            ),
        )

    def acceptance_promotion_gate(
        self,
        candidates: list[AcceptanceCandidate],
        facts: ContractFactSet,
        scope: ScopeResolution,
        dispositions: list[CoverageDispositionRecord],
    ) -> tuple[GateDecision, list[AcceptancePromotionDecision]]:
        facts_by_id = {row.fact_id: row for row in facts.facts}
        dispositions_by_id = {row.disposition_id: row for row in dispositions}
        decisions: list[AcceptancePromotionDecision] = []
        integrity_failures: list[str] = []
        for candidate in candidates:
            source_facts = [
                facts_by_id[fact_id]
                for fact_id in candidate.source_fact_ids
                if fact_id in facts_by_id
            ]
            authority_supported = bool(source_facts) and all(
                row.authoritative for row in source_facts
            )
            source_dispositions = [
                dispositions_by_id[disposition_id]
                for disposition_id in candidate.source_disposition_ids
                if disposition_id in dispositions_by_id
            ]
            missing_disposition_ids = sorted(
                set(candidate.source_disposition_ids) - set(dispositions_by_id)
            )
            acceptance_disposition_supported = bool(source_dispositions) and all(
                row.disposition
                in {
                    CoverageDisposition.ACCEPTANCE_CONTRACT,
                    CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                }
                for row in source_dispositions
            )
            belongs_to_human_contract = (
                facts.contract_mode != ContractMode.HUMAN_ACCEPTED_CONTRACT
                or candidate.accepted_human_contract
            )
            candidate_text = candidate.statement.casefold()
            scope_established = candidate.in_scope and not any(
                value and value in candidate_text
                for value in map(_scope_clause_value, scope.out_of_scope)
            )
            unresolved = bool(candidate.unresolved_decision_ids)
            reasons: list[str] = []
            if missing_disposition_ids:
                reasons.append(
                    "Acceptance candidate references an unavailable coverage disposition."
                )
                integrity_failures.append(
                    f"{candidate.candidate_id}: missing source dispositions "
                    + ", ".join(missing_disposition_ids)
                )
            if not acceptance_disposition_supported:
                reasons.append(
                    "Non-acceptance coverage disposition cannot be promoted to acceptance."
                )
                integrity_failures.append(
                    f"{candidate.candidate_id}: source disposition is not acceptance eligible"
                )
            if not authority_supported:
                reasons.append("Intended behavior lacks product-contract authority.")
            if not belongs_to_human_contract:
                reasons.append(
                    "Human Accepted AC exists; this candidate is not part of that accepted contract."
                )
            if not scope_established:
                reasons.append(
                    "The candidate conflicts with or falls outside established scope."
                )
            if not candidate.observable:
                reasons.append("The expected result is not observable.")
            if candidate.regression_only:
                reasons.append("Regression coverage cannot be promoted to acceptance.")
            if candidate.implementation_mechanics_only:
                reasons.append(
                    "Implementation mechanics cannot define product acceptance."
                )
            if not candidate.exact_values_supported:
                reasons.append("An exact value is unsupported by authority.")
            if unresolved:
                reasons.append("A blocking product decision remains unresolved.")
            if candidate.contradicts_human_contract:
                reasons.append("The candidate contradicts Human Accepted AC.")
            promotable = not reasons
            status = (
                PromotionStatus.PROMOTED
                if promotable
                else PromotionStatus.BLOCKED
                if unresolved
                else PromotionStatus.REJECTED
            )
            resulting = (
                CoverageDisposition.ACCEPTANCE_CONTRACT
                if promotable and candidate.accepted_human_contract
                else CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                if promotable
                else CoverageDisposition.OPEN_QUESTION
                if unresolved
                else CoverageDisposition.UNSUPPORTED_INFERENCE
            )
            decisions.append(
                AcceptancePromotionDecision(
                    candidate_id=candidate.candidate_id,
                    status=status,
                    resulting_disposition=resulting,
                    authority_supported=authority_supported,
                    scope_established=scope_established,
                    observable=candidate.observable,
                    exact_values_supported=candidate.exact_values_supported,
                    contradicts_human_contract=candidate.contradicts_human_contract,
                    reasons=reasons,
                )
            )
        failures = [
            f"{row.candidate_id}: {reason}"
            for row in decisions
            if row.status == PromotionStatus.PROMOTED and row.reasons
            for reason in row.reasons
        ]
        blocking_failures = [
            f"{row.candidate_id}: {reason}"
            for row in decisions
            if row.status == PromotionStatus.BLOCKED
            for reason in row.reasons
        ]
        if not candidates:
            blocking_failures.append(
                "No supported acceptance-contract candidate is available."
            )
            if scope.unresolved_fields:
                blocking_failures.append(
                    "Material scope remains unresolved: "
                    + ", ".join(scope.unresolved_fields)
                )
        if candidates and not any(
            row.status == PromotionStatus.PROMOTED for row in decisions
        ):
            blocking_failures.append(
                "No acceptance-contract candidate passed the promotion gate."
            )
        status = (
            GateStatus.FAILED
            if failures or integrity_failures
            else GateStatus.BLOCKED
            if facts.contract_mode == ContractMode.INSUFFICIENT_EVIDENCE_FOR_CONTRACT
            or blocking_failures
            else GateStatus.PASSED
        )
        return (
            GateDecision(
                gate="AcceptancePromotionGate",
                status=status,
                failures=failures + integrity_failures + blocking_failures,
                checked_ids=sorted(
                    {row.candidate_id for row in candidates}
                    | {
                        disposition_id
                        for row in candidates
                        for disposition_id in row.source_disposition_ids
                    }
                ),
            ),
            decisions,
        )

    def build_candidate_lifecycle(
        self,
        resolution: AcceptanceResolutionBatch,
        promotions: list[AcceptancePromotionDecision],
    ) -> list[CandidateLifecycleRecord]:
        """Prove every discovered acceptance candidate reaches one terminal state."""

        promotion_by_candidate: dict[str, AcceptancePromotionDecision] = {}
        for decision in promotions:
            if decision.candidate_id in promotion_by_candidate:
                raise RuntimeError(
                    "Material acceptance candidate has multiple promotion decisions: "
                    f"{decision.candidate_id}"
                )
            promotion_by_candidate[decision.candidate_id] = decision
        final_by_id = {row.candidate_id: row for row in resolution.candidates}
        if set(promotion_by_candidate) != set(final_by_id):
            missing = sorted(set(final_by_id) - set(promotion_by_candidate))
            extra = sorted(set(promotion_by_candidate) - set(final_by_id))
            detail = []
            if missing:
                detail.append("missing=" + ",".join(missing))
            if extra:
                detail.append("unexpected=" + ",".join(extra))
            raise RuntimeError(
                "Every finalized acceptance candidate requires exactly one terminal "
                "promotion decision (" + "; ".join(detail) + ")"
            )
        merge_by_member = {
            candidate_id: decision
            for decision in resolution.dedup_decisions
            for candidate_id in decision.merged_candidate_ids
        }
        rows: list[CandidateLifecycleRecord] = []
        for discovered in resolution.discovered_candidates:
            merge = merge_by_member.get(discovered.candidate_id)
            canonical_id = (
                merge.surviving_candidate_id if merge else discovered.candidate_id
            )
            canonical = final_by_id.get(canonical_id)
            if canonical is None:
                raise RuntimeError(
                    "Discovered material candidate has no canonical survivor: "
                    f"{discovered.candidate_id}"
                )
            promotion = promotion_by_candidate[canonical_id]
            evidence_required = not canonical.accepted_human_contract
            evidence_collected = bool(canonical.evidence_ids)
            stages = [
                CandidateLifecycleStage.CANDIDATE_DISCOVERED,
                CandidateLifecycleStage.APPLICABILITY_EVALUATED,
            ]
            if evidence_collected:
                stages.append(CandidateLifecycleStage.EVIDENCE_COLLECTED)
            stages.append(CandidateLifecycleStage.FINAL_DISPOSITION)
            rows.append(
                CandidateLifecycleRecord(
                    discovered_candidate_id=discovered.candidate_id,
                    canonical_candidate_id=canonical_id,
                    stages=stages,
                    evidence_required=evidence_required,
                    evidence_collected=evidence_collected,
                    final_disposition=_candidate_terminal_disposition(promotion),
                    promotion_status=promotion.status,
                    dedup_decision_id=merge.decision_id if merge else "",
                )
            )
        return sorted(rows, key=lambda row: row.lifecycle_id)

    def render_final_plan(
        self,
        request: GenerationRequest,
        facts: ContractFactSet,
        scope: ScopeResolution,
        model: CanonicalBehaviorModel,
        closure: list[ClosureDimensionResult],
        questions: list[MissingQuestion],
        impacts: list[DomainImpact],
        dispositions: list[CoverageDispositionRecord],
        candidates: list[AcceptanceCandidate],
        promotions: list[AcceptancePromotionDecision],
        gates: list[GateDecision],
        acceptance_resolution: AcceptanceResolutionBatch | None = None,
        candidate_lifecycle: list[CandidateLifecycleRecord] | None = None,
    ) -> tuple[StructuredQEPlan, str]:
        acceptance_resolution = acceptance_resolution or AcceptanceResolutionBatch(
            discovered_candidates=candidates,
            candidates=candidates,
        )
        candidate_lifecycle = candidate_lifecycle or self.build_candidate_lifecycle(
            acceptance_resolution, promotions
        )
        candidate_by_id = {row.candidate_id: row for row in candidates}
        lifecycle_by_canonical: dict[str, list[CandidateLifecycleRecord]] = (
            defaultdict(list)
        )
        for lifecycle_row in candidate_lifecycle:
            lifecycle_by_canonical[lifecycle_row.canonical_candidate_id].append(
                lifecycle_row
            )
        disposition_sections: dict[CoverageDisposition, str] = {
            CoverageDisposition.SEMANTIC_REGRESSION: "semantic_coverage",
            CoverageDisposition.STRUCTURAL_REGRESSION: "structural_hierarchy_coverage",
            CoverageDisposition.REFERENCE_REGRESSION: "referenced_content_coverage",
            CoverageDisposition.CONFIGURATION_VARIANT: "configuration_state_coverage",
            CoverageDisposition.GENERATED_OUTPUT_VALIDATION: "generated_output_validation",
            CoverageDisposition.NEGATIVE_BOUNDARY: "negative_boundary_coverage",
            CoverageDisposition.FAILURE_RECOVERY: "failure_recovery_coverage",
            CoverageDisposition.LIFECYCLE_COVERAGE: "lifecycle_coverage",
            CoverageDisposition.CROSS_MODE_REGRESSION: "cross_mode_regression",
            CoverageDisposition.NFR_COVERAGE: "nfr_coverage",
            CoverageDisposition.PRODUCT_SCOPE_QUESTION: "product_decisions",
            CoverageDisposition.ENGINEERING_DESIGN_DECISION: "product_decisions",
            CoverageDisposition.OUT_OF_SCOPE: "explicit_out_of_scope",
            CoverageDisposition.INVESTIGATED_AND_REJECTED: "investigated_and_rejected",
            CoverageDisposition.IMPLEMENTATION_ORACLE: "transformation_processing_coverage",
            CoverageDisposition.TECHNICAL_NOTE: "technical_notes",
            CoverageDisposition.KNOWN_LIMITATION: "known_limitations",
            CoverageDisposition.OPEN_QUESTION: "evidence_gaps",
            CoverageDisposition.UNSUPPORTED_INFERENCE: "evidence_gaps",
        }
        titles = {
            "issue_understanding": "Issue understanding",
            "product_scope": "Publishing / product scope",
            "acceptance_contract": (
                "Acceptance contract"
                if facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                else "Proposed acceptance contract"
            ),
            "finalization": "Finalization",
            "product_decisions": "Product decisions required",
            "semantic_coverage": "Semantic coverage",
            "structural_hierarchy_coverage": "Structural / hierarchy coverage",
            "referenced_content_coverage": "Referenced content coverage",
            "configuration_state_coverage": "Configuration / state coverage",
            "transformation_processing_coverage": "Transformation / processing coverage",
            "generated_output_validation": "Generated output validation",
            "reference_link_integrity": "Reference / link integrity",
            "negative_boundary_coverage": "Negative / boundary coverage",
            "failure_recovery_coverage": "Failure / recovery coverage",
            "lifecycle_coverage": "Lifecycle coverage",
            "cross_mode_regression": "Cross-mode regression",
            "nfr_coverage": "NFR coverage",
            "explicit_out_of_scope": "Explicit out of scope",
            "investigated_and_rejected": "Investigated and rejected",
            "technical_notes": "Technical notes",
            "known_limitations": "Known limitations",
            "evidence_gaps": "Evidence gaps",
            "coverage_gate_result": "Coverage gate result",
        }
        section_items: dict[str, list[tuple[str, str]]] = defaultdict(list)
        understanding = [
            row
            for row in facts.facts
            if row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
        ]
        for fact in understanding:
            section_items["issue_understanding"].append((fact.literal, fact.fact_id))
        for item in scope.in_scope:
            section_items["product_scope"].append((f"In scope: {item}", ""))
        if scope.primary_preset_type:
            section_items["product_scope"].append(
                (f"Preset: {scope.primary_preset_type}", "")
            )
        for interface in scope.execution_interfaces:
            section_items["product_scope"].append(
                (f"Execution interface: {interface}", "")
            )
        if scope.enable_dita_ot_processing != DitaOtProcessingState.NOT_APPLICABLE:
            section_items["product_scope"].append(
                (
                    f"Enable DITA-OT Processing: {scope.enable_dita_ot_processing.value}",
                    "",
                )
            )
        promoted_ids: list[str] = []
        for decision in promotions:
            if decision.status == PromotionStatus.PROMOTED:
                candidate = candidate_by_id[decision.candidate_id]
                promoted_ids.append(candidate.candidate_id)
                statement = candidate.statement
                if (
                    facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                    and decision.resulting_disposition
                    == CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT
                ):
                    statement = f"Proposed: {statement}"
                section_items["acceptance_contract"].append(
                    (statement, candidate.candidate_id)
                )
                section_items["acceptance_contract"].extend(
                    (statement, disposition_id)
                    for disposition_id in candidate.source_disposition_ids
                )
                section_items["acceptance_contract"].extend(
                    (statement, fact_id) for fact_id in candidate.source_fact_ids
                )
                for lifecycle_row in lifecycle_by_canonical[candidate.candidate_id]:
                    section_items["acceptance_contract"].append(
                        (statement, lifecycle_row.discovered_candidate_id)
                    )
                    section_items["acceptance_contract"].append(
                        (statement, lifecycle_row.lifecycle_id)
                    )
                    if lifecycle_row.dedup_decision_id:
                        section_items["acceptance_contract"].append(
                            (statement, lifecycle_row.dedup_decision_id)
                        )
            else:
                candidate = candidate_by_id[decision.candidate_id]
                reason = "; ".join(decision.reasons) or "Not promoted."
                rejected_text = f"{candidate.statement} — {reason}"
                # Preserve the established public markdown projection.  The
                # typed lifecycle carries the more precise terminal state.
                section_key = "evidence_gaps"
                section_items[section_key].append(
                    (rejected_text, candidate.candidate_id)
                )
                section_items[section_key].extend(
                    (rejected_text, disposition_id)
                    for disposition_id in candidate.source_disposition_ids
                )
                section_items[section_key].extend(
                    (rejected_text, fact_id) for fact_id in candidate.source_fact_ids
                )
                for lifecycle_row in lifecycle_by_canonical[candidate.candidate_id]:
                    section_items[section_key].append(
                        (rejected_text, lifecycle_row.discovered_candidate_id)
                    )
                    section_items[section_key].append(
                        (rejected_text, lifecycle_row.lifecycle_id)
                    )
                    if lifecycle_row.dedup_decision_id:
                        section_items[section_key].append(
                            (rejected_text, lifecycle_row.dedup_decision_id)
                        )
        open_dispositions = {
            CoverageDisposition.OPEN_QUESTION,
            CoverageDisposition.PRODUCT_SCOPE_QUESTION,
            CoverageDisposition.ENGINEERING_DESIGN_DECISION,
        }
        linked_question_ids = {
            question_id
            for disposition in dispositions
            for question_id in disposition.source_question_ids
        }
        open_question_ids = {
            question_id
            for disposition in dispositions
            if disposition.disposition in open_dispositions
            for question_id in disposition.source_question_ids
        }
        resolved_question_ids = linked_question_ids - open_question_ids
        for question in questions:
            if question.question_id in resolved_question_ids:
                continue
            key = "product_decisions" if question.blocking else "evidence_gaps"
            section_items[key].append((question.question, question.question_id))
        for disposition in dispositions:
            if disposition.disposition in {
                CoverageDisposition.ACCEPTANCE_CONTRACT,
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            }:
                continue
            key = disposition_sections.get(disposition.disposition)
            if key is None:
                raise RuntimeError(
                    "FinalQEPlanRenderer has no section for disposition: "
                    f"{disposition.disposition.value}"
                )
            disposition_text = _plain_candidate(disposition.candidate)
            section_items[key].append((disposition_text, disposition.disposition_id))
            section_items[key].extend(
                (disposition_text, fact_id) for fact_id in disposition.source_fact_ids
            )
        for item in scope.out_of_scope:
            section_items["explicit_out_of_scope"].append((item, ""))
        for oracle in model.generated_output_oracles:
            section_items["generated_output_validation"].append(
                (oracle.replace("_", " ").title(), oracle)
            )
        for gate in gates:
            detail = f"{gate.gate.value}: {gate.status.value}"
            if gate.failures:
                detail += f" — {'; '.join(gate.failures)}"
            section_items["coverage_gate_result"].append((detail, gate.gate.value))

        # Zero-AC finalization gate: a plan must never leave the acceptance contract
        # silently empty. When nothing was promoted, state the finalization outcome and
        # WHY in a human-visible section instead of just omitting the contract heading
        # (the reason otherwise hides in "Coverage gate result"). Every item carries an
        # empty record id, so this does not affect the completeness-invariant projection
        # checks below.
        if not section_items["acceptance_contract"]:
            material_contract = (
                facts.contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
                or any(
                    row.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
                    for row in facts.facts
                )
            )
            block_reasons: list[str] = []
            for decision in promotions:
                if decision.status != PromotionStatus.PROMOTED:
                    for reason in decision.reasons:
                        if reason and reason not in block_reasons:
                            block_reasons.append(reason)
            unresolved = [q.question for q in questions if q.blocking]
            if not material_contract:
                state = (
                    "NO_ACCEPTANCE_CONTRACT_REQUIRED: no material customer/product "
                    "contract was extracted from the evidence."
                )
            elif block_reasons or unresolved:
                state = (
                    "NEEDS_REVIEW: a material contract exists but no acceptance criteria "
                    "were promoted — resolve the items below, then re-run."
                )
            else:
                state = (
                    "NEEDS_REVIEW: a material contract exists but no acceptance criteria "
                    "were promoted."
                )
            section_items["finalization"].append((state, ""))
            for reason in block_reasons[:6]:
                section_items["finalization"].append((f"Blocked: {reason}", ""))
            for question in unresolved[:6]:
                section_items["finalization"].append(
                    (f"Unresolved product decision: {question}", "")
                )

        order = list(titles)
        sections: list[PlanSection] = []
        for key in order:
            items = section_items.get(key, [])
            if not items:
                continue
            deduped: dict[str, set[str]] = {}
            for text, record_id in items:
                normalized_text = text.strip()
                deduped.setdefault(normalized_text, set())
                if record_id:
                    deduped[normalized_text].add(record_id)
            sections.append(
                PlanSection(
                    section_key=key,
                    title=titles[key],
                    items=list(deduped),
                    source_record_ids=sorted(
                        {
                            record_id
                            for record_ids in deduped.values()
                            for record_id in record_ids
                        }
                    ),
                )
            )
        sections_by_source_id: dict[str, list[PlanSection]] = defaultdict(list)
        for section in sections:
            for source_id in section.source_record_ids:
                sections_by_source_id[source_id].append(section)
        renderer_decisions: list[RendererProjectionDecision] = []
        for lifecycle_row in candidate_lifecycle:
            matching_sections = sections_by_source_id.get(
                lifecycle_row.discovered_candidate_id, []
            )
            if len(matching_sections) != 1:
                raise RuntimeError(
                    "FinalQEPlanRenderer requires exactly one projection for finalized "
                    f"candidate {lifecycle_row.discovered_candidate_id}; found "
                    f"{len(matching_sections)}"
                )
            section = matching_sections[0]
            renderer_decisions.append(
                RendererProjectionDecision(
                    discovered_candidate_id=lifecycle_row.discovered_candidate_id,
                    canonical_candidate_id=lifecycle_row.canonical_candidate_id,
                    final_disposition=lifecycle_row.final_disposition,
                    section_key=section.section_key,
                    source_record_ids=section.source_record_ids,
                    dedup_decision_id=lifecycle_row.dedup_decision_id,
                )
            )
        plan = StructuredQEPlan(
            jira_key=request.jira_key,
            contract_mode=facts.contract_mode,
            sections=sections,
            contract_fact_ids=[row.fact_id for row in facts.facts],
            closure_ids=[row.closure_id for row in closure],
            coverage_disposition_ids=[row.disposition_id for row in dispositions],
            promoted_candidate_ids=promoted_ids,
            open_question_ids=sorted(
                open_question_ids
                | {
                    row.question_id
                    for row in questions
                    if row.question_id not in linked_question_ids
                }
            ),
            candidate_lifecycle=candidate_lifecycle,
            dedup_decisions=acceptance_resolution.dedup_decisions,
            renderer_decisions=renderer_decisions,
            gate_decisions=gates,
        )
        lines = [f"# {request.jira_key} — QE plan", ""]
        for section in sections:
            lines.extend([f"## {section.title}", ""])
            lines.extend(f"- {item}" for item in section.items)
            lines.append("")
        rendered = "\n".join(lines).rstrip() + "\n"
        rendered_source_ids = {
            record_id for section in sections for record_id in section.source_record_ids
        }
        missing_disposition_ids = sorted(
            row.disposition_id
            for row in dispositions
            if row.disposition_id not in rendered_source_ids
        )
        if missing_disposition_ids:
            raise RuntimeError(
                "FinalQEPlanRenderer dropped terminal coverage dispositions: "
                + ", ".join(missing_disposition_ids)
            )
        missing_authoritative_fact_ids = [
            fact.fact_id
            for fact in facts.facts
            if fact.authoritative and fact.fact_id not in rendered_source_ids
        ]
        if missing_authoritative_fact_ids:
            raise RuntimeError(
                "FinalQEPlanRenderer dropped authoritative contract facts: "
                + ", ".join(missing_authoritative_fact_ids)
            )
        return plan, rendered


CANONICAL_REASONING_SERVICE = CanonicalTestPlanReasoningService()


__all__ = ["CANONICAL_REASONING_SERVICE", "CanonicalTestPlanReasoningService"]
