"""Deterministic, read-only resolver for Human-backed QE reasoning patterns.

The service adapts the already-recovered TRAIN-V2 mining artifact.  It does not
re-ingest Jira, call an LLM, or generate acceptance criteria.  Production
influence is fail-closed: only an artifact-version-bound Human QE approval can
make a pattern ACTIVE.
"""

from __future__ import annotations

import hashlib
import json
import re
from threading import RLock
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.core.schemas_qe_pattern_mcp import (
    QePatternMatch,
    QePatternMateriality,
    QePatternProductionStatus,
    QePatternProvenance,
    QePatternProviderStatus,
    QePatternRecord,
    QePatternSupportGroup,
    QePatternSuppressedMatch,
    QePatternValidationStatus,
    ResolveQePatternsRequest,
    ResolveQePatternsResponse,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LIBRARY_PATH = (
    _REPOSITORY_ROOT
    / "benchmark"
    / "v2"
    / "train_mining"
    / "reasoning_pattern_taxonomy_train_v2.json"
)
_DEFAULT_APPROVAL_PATH = (
    _REPOSITORY_ROOT / "backend" / "config" / "qe_pattern_approvals_v1.json"
)
_MAX_LIBRARY_BYTES = 5 * 1024 * 1024
_WORD_RE = re.compile(r"[a-z0-9]+")
_JIRA_KEY_RE = re.compile(r"\b[a-z][a-z0-9]+-\d+\b", re.IGNORECASE)
_MATCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "current",
    "evidence",
    "feature",
    "for",
    "from",
    "in",
    "is",
    "issue",
    "of",
    "on",
    "or",
    "out",
    "requirement",
    "scope",
    "that",
    "the",
    "to",
    "with",
}


class PatternLibraryUnavailable(RuntimeError):
    """The configured provider cannot be reached/read."""


class PatternLibraryInvalid(RuntimeError):
    """The provider returned a malformed or untrusted library."""


class PatternLibraryProvider(Protocol):
    provider_name: str

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        """Return records, library version, and lowercase SHA-256."""


class _PatternApproval(BaseModel):
    """Human-owned overlay; an empty overlay keeps all mined patterns analysis-only."""

    model_config = ConfigDict(extra="forbid")

    pattern_id: str
    pattern_version: str
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_authority: str
    validated_by: str = Field(min_length=1, max_length=200)
    validated_at: str = Field(min_length=1, max_length=100)
    production_status: QePatternProductionStatus
    abstract_change_surface: list[str] = Field(min_length=1)
    applicable_domains: list[str] = Field(min_length=1)
    applicable_publishing_modes: list[str] = Field(default_factory=list)
    applicable_configuration_states: list[str] = Field(default_factory=list)
    abstract_signals: list[str] = Field(min_length=1)
    question_families: list[str] = Field(min_length=1)
    relationship_to_explore: list[str] = Field(min_length=1)
    preferred_evidence_sources: list[str] = Field(default_factory=list)
    materiality: QePatternMateriality
    blocking_default: bool
    qualifying_human_support_case_ids: list[str] = Field(min_length=1)
    independent_support_groups: list[QePatternSupportGroup] = Field(min_length=1)
    counterexamples: list[str] = Field(default_factory=list)
    hard_negatives: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    customer_specific: bool
    jira_specific: bool

    @field_validator("validated_by")
    @classmethod
    def normalize_reviewer(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reviewer must not be blank")
        return cleaned

    @field_validator("validated_at")
    @classmethod
    def normalize_review_time(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("review timestamp must not be blank")
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("review timestamp must be ISO-8601") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("review timestamp must include a timezone")
        return cleaned

    @model_validator(mode="after")
    def validate_generic_semantics(self) -> "_PatternApproval":
        semantic_values = [
            *self.abstract_change_surface,
            *self.applicable_domains,
            *self.applicable_publishing_modes,
            *self.applicable_configuration_states,
            *self.abstract_signals,
            *self.question_families,
            *self.relationship_to_explore,
            *self.counterexamples,
            *self.hard_negatives,
        ]
        if any(_JIRA_KEY_RE.search(value) for value in semantic_values):
            raise ValueError("approval semantic fields must not contain Jira keys")
        if self.customer_specific or self.jira_specific:
            raise ValueError("production approvals must be generic")
        return self


def _read_json_object(path: Path) -> tuple[dict, str]:
    try:
        resolved = path.resolve(strict=True)
        size = resolved.stat().st_size
        if size <= 0 or size > _MAX_LIBRARY_BYTES:
            raise PatternLibraryInvalid(
                "pattern library size is outside the safe bound"
            )
        raw = resolved.read_bytes()
    except PatternLibraryInvalid:
        raise
    except OSError as exc:
        raise PatternLibraryUnavailable("pattern library is unavailable") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise PatternLibraryInvalid("pattern library is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise PatternLibraryInvalid("pattern library root must be an object")
    return parsed, hashlib.sha256(raw).hexdigest()


def _pattern_version(raw_pattern: dict) -> str:
    canonical = json.dumps(
        raw_pattern,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"train-v2-{hashlib.sha256(canonical).hexdigest()[:16]}"


def _approved_pattern_version(
    source_pattern_version: str,
    approval: _PatternApproval,
) -> str:
    approval_payload = approval.model_dump(mode="json")
    canonical = json.dumps(
        approval_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    approval_digest = hashlib.sha256(canonical).hexdigest()[:16]
    return f"{source_pattern_version}+approval-{approval_digest}"


def _string_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return sorted({str(value).strip() for value in raw if str(value).strip()})


def _safe_source_locator(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPOSITORY_ROOT)).replace("\\", "/")
    except ValueError:
        return f"external-fixture/{path.name}"


class TrainV2PatternLibraryProvider:
    """Strict adapter over the existing TRAIN-only artifact plus Human approvals."""

    provider_name = "TRAIN_V2_PATTERN_ADAPTER"

    def __init__(
        self,
        library_path: Path | None = None,
        approval_path: Path | None = None,
    ) -> None:
        self._library_path = library_path or _DEFAULT_LIBRARY_PATH
        self._approval_path = approval_path or _DEFAULT_APPROVAL_PATH
        self._cache_lock = RLock()
        self._cached_file_signature: tuple[tuple[str, int, int], ...] | None = None
        self._cached_result: tuple[tuple[QePatternRecord, ...], str, str] | None = None

    def _file_signature(self) -> tuple[tuple[str, int, int], ...]:
        """Version the cache by resolved path, nanosecond mtime, and size."""

        signatures: list[tuple[str, int, int]] = []
        for path in (self._library_path, self._approval_path):
            try:
                resolved = path.resolve(strict=True)
                stat = resolved.stat()
            except OSError as exc:
                raise PatternLibraryUnavailable(
                    "pattern library is unavailable"
                ) from exc
            signatures.append((str(resolved), stat.st_mtime_ns, stat.st_size))
        return tuple(signatures)

    def _load_approvals(self) -> tuple[dict[str, _PatternApproval], str]:
        raw, approval_sha = _read_json_object(self._approval_path)
        if raw.get("schema_version") != "aem-guides-qe-pattern-approvals-v1":
            raise PatternLibraryInvalid("unsupported pattern approval schema")
        approval_rows = raw.get("approvals")
        if not isinstance(approval_rows, list):
            raise PatternLibraryInvalid("pattern approvals must be a list")
        approvals: dict[str, _PatternApproval] = {}
        for row in approval_rows:
            try:
                approval = _PatternApproval.model_validate(row)
            except ValidationError as exc:
                raise PatternLibraryInvalid("invalid pattern approval record") from exc
            if approval.approval_authority != "HUMAN_QE":
                raise PatternLibraryInvalid(
                    "pattern approval authority must be HUMAN_QE"
                )
            if approval.pattern_id in approvals:
                raise PatternLibraryInvalid("duplicate pattern approval")
            approvals[approval.pattern_id] = approval
        return approvals, approval_sha

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        signature = self._file_signature()
        with self._cache_lock:
            if (
                signature == self._cached_file_signature
                and self._cached_result is not None
            ):
                records, version, source_sha256 = self._cached_result
                return (
                    [record.model_copy(deep=True) for record in records],
                    version,
                    source_sha256,
                )
        library, library_sha = _read_json_object(self._library_path)
        if library.get("schema_version") != "aem-guides-qe-pattern-taxonomy-train-v2":
            raise PatternLibraryInvalid("unsupported pattern library schema")
        if library.get("derivation_partition") != "TRAIN_V2_ONLY":
            raise PatternLibraryInvalid("pattern library is not TRAIN-V2 scoped")
        expected_boundaries = {
            "historical_candidate_definitions_imported": False,
            "validation_ground_truth_used_for_pattern_discovery": False,
            "blind_ground_truth_used_for_pattern_discovery": False,
            "raw_human_uac_included": False,
        }
        for field_name, expected in expected_boundaries.items():
            if library.get(field_name) is not expected:
                raise PatternLibraryInvalid(
                    f"pattern library violates the {field_name} boundary"
                )
        rows = library.get("patterns")
        if not isinstance(rows, list):
            raise PatternLibraryInvalid("pattern library patterns must be a list")
        declared_count = library.get("pattern_count")
        if declared_count != len(rows):
            raise PatternLibraryInvalid("pattern library count does not match contents")
        approvals, approval_sha = self._load_approvals()
        records: list[QePatternRecord] = []
        seen_ids: set[str] = set()
        source_locator = _safe_source_locator(self._library_path)
        for raw_pattern in rows:
            if not isinstance(raw_pattern, dict):
                raise PatternLibraryInvalid("pattern entries must be objects")
            if raw_pattern.get("promotion_status") != "PROMOTED_TRAIN_V2":
                raise PatternLibraryInvalid(
                    "pattern library contains a non-promoted TRAIN pattern"
                )
            pattern_id = str(raw_pattern.get("pattern_id") or "").strip()
            if not pattern_id or pattern_id in seen_ids:
                raise PatternLibraryInvalid("pattern IDs must be present and unique")
            seen_ids.add(pattern_id)
            version = _pattern_version(raw_pattern)
            approval = approvals.get(pattern_id)
            if approval is not None:
                if approval.pattern_version != version:
                    raise PatternLibraryInvalid("approval pattern version is stale")
                if approval.source_sha256 != library_sha:
                    raise PatternLibraryInvalid("approval source hash is stale")
            supporting_case_ids = _string_list(raw_pattern.get("source_jiras"))
            activation_guardrails = _string_list(raw_pattern.get("negative_activation"))
            if approval is None:
                record = QePatternRecord(
                    pattern_id=pattern_id,
                    pattern_version=version,
                    validation_status=QePatternValidationStatus.HUMAN_BACKED_CANDIDATE,
                    production_status=QePatternProductionStatus.ANALYSIS_ONLY,
                    abstract_change_surface=[pattern_id],
                    applicable_domains=[],
                    applicable_publishing_modes=[],
                    applicable_configuration_states=[],
                    abstract_signals=[
                        pattern_id,
                        *_string_list(raw_pattern.get("activation_signals")),
                    ],
                    question_families=[pattern_id],
                    relationship_to_explore=[pattern_id],
                    preferred_evidence_sources=_string_list(
                        raw_pattern.get("evidence_to_seek")
                    ),
                    materiality=QePatternMateriality(
                        str(raw_pattern.get("priority") or "P1")
                    ),
                    blocking_default=False,
                    human_support_count=0,
                    independent_case_count=0,
                    supporting_case_ids=[],
                    qualifying_human_support_case_ids=[],
                    independent_support_groups=[],
                    counterexamples=[],
                    hard_negatives=[],
                    activation_guardrails=activation_guardrails,
                    confidence=None,
                    customer_specific=False,
                    jira_specific=False,
                    provenance=QePatternProvenance(
                        source_kind="TRAIN_MINING_ARTIFACT",
                        source_locator=source_locator,
                        source_sha256=library_sha,
                        source_schema_version=str(library["schema_version"]),
                        derivation_partition=str(library["derivation_partition"]),
                        human_backed=True,
                        raw_human_uac_included=bool(
                            library.get("raw_human_uac_included", False)
                        ),
                        candidate_source_case_ids=supporting_case_ids,
                    ),
                )
            else:
                qualifying_ids = sorted(set(approval.qualifying_human_support_case_ids))
                if not set(qualifying_ids).issubset(set(supporting_case_ids)):
                    raise PatternLibraryInvalid(
                        "approval support IDs must exist in candidate provenance"
                    )
                record = QePatternRecord(
                    pattern_id=pattern_id,
                    pattern_version=_approved_pattern_version(version, approval),
                    validation_status=QePatternValidationStatus.APPROVED,
                    production_status=approval.production_status,
                    abstract_change_surface=approval.abstract_change_surface,
                    applicable_domains=approval.applicable_domains,
                    applicable_publishing_modes=(approval.applicable_publishing_modes),
                    applicable_configuration_states=(
                        approval.applicable_configuration_states
                    ),
                    abstract_signals=approval.abstract_signals,
                    question_families=approval.question_families,
                    relationship_to_explore=approval.relationship_to_explore,
                    preferred_evidence_sources=approval.preferred_evidence_sources,
                    materiality=approval.materiality,
                    blocking_default=approval.blocking_default,
                    human_support_count=len(qualifying_ids),
                    independent_case_count=len(approval.independent_support_groups),
                    supporting_case_ids=qualifying_ids,
                    qualifying_human_support_case_ids=qualifying_ids,
                    independent_support_groups=approval.independent_support_groups,
                    counterexamples=approval.counterexamples,
                    hard_negatives=approval.hard_negatives,
                    activation_guardrails=activation_guardrails,
                    confidence=approval.confidence,
                    customer_specific=approval.customer_specific,
                    jira_specific=approval.jira_specific,
                    provenance=QePatternProvenance(
                        source_kind="TRAIN_MINING_ARTIFACT",
                        source_locator=source_locator,
                        source_sha256=library_sha,
                        source_schema_version=str(library["schema_version"]),
                        derivation_partition=str(library["derivation_partition"]),
                        human_backed=True,
                        raw_human_uac_included=bool(
                            library.get("raw_human_uac_included", False)
                        ),
                        candidate_source_case_ids=supporting_case_ids,
                        approval_overlay_sha256=approval_sha,
                        approval_authority="HUMAN_QE",
                        validated_by=approval.validated_by,
                        validated_at=approval.validated_at,
                    ),
                )
            records.append(record)
        unknown_approvals = sorted(set(approvals) - seen_ids)
        if unknown_approvals:
            raise PatternLibraryInvalid("approval references an unknown pattern")
        result = (
            sorted(records, key=lambda row: row.pattern_id),
            str(library.get("benchmark_version") or "TRAIN_V2"),
            library_sha,
        )
        with self._cache_lock:
            self._cached_file_signature = signature
            self._cached_result = (
                tuple(record.model_copy(deep=True) for record in result[0]),
                result[1],
                result[2],
            )
        return result


def _normalized_tokens(value: str) -> set[str]:
    without_jira_keys = _JIRA_KEY_RE.sub(" ", value)
    tokens = {
        token
        for token in _WORD_RE.findall(without_jira_keys.replace("_", " ").casefold())
        if token not in _MATCH_STOPWORDS
    }
    return tokens


def _similarity(left: str, right: str) -> float:
    left_tokens = _normalized_tokens(left)
    right_tokens = _normalized_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), len(right_tokens))


def _best_similarity(
    inputs: list[str], candidates: list[str]
) -> tuple[float, str, str]:
    best = (0.0, "", "")
    for input_value in inputs:
        for candidate in candidates:
            score = _similarity(input_value, candidate)
            if score > best[0]:
                best = (score, input_value, candidate)
    return best


class QePatternResolver:
    def __init__(self, provider: PatternLibraryProvider | None = None) -> None:
        self._provider = provider or TrainV2PatternLibraryProvider()

    def resolve(self, request: ResolveQePatternsRequest) -> ResolveQePatternsResponse:
        try:
            patterns, library_version, library_sha = self._provider.load()
        except PatternLibraryUnavailable:
            return ResolveQePatternsResponse(
                provider_status=QePatternProviderStatus.UNAVAILABLE,
                pattern_library_version="UNAVAILABLE",
                pattern_count=0,
                validated_production_pattern_count=0,
                warnings=[
                    "Pattern provider unavailable; no pattern influenced reasoning."
                ],
                error_code="QE_PATTERN_PROVIDER_UNAVAILABLE",
            )
        except (PatternLibraryInvalid, ValidationError, ValueError):
            return ResolveQePatternsResponse(
                provider_status=QePatternProviderStatus.INVALID_LIBRARY,
                pattern_library_version="INVALID",
                pattern_count=0,
                validated_production_pattern_count=0,
                warnings=["Pattern library rejected; no pattern influenced reasoning."],
                error_code="QE_PATTERN_LIBRARY_INVALID",
            )

        active_count = sum(row.production_influence_allowed for row in patterns)
        excluded = Counter()
        matches: list[QePatternMatch] = []
        suppressed: list[QePatternSuppressedMatch] = []
        request_domain = request.domain.strip().upper()
        context_values = [
            *request.change_surfaces,
            *request.abstract_signals,
            request.publishing_mode or "",
            request.configuration_state or "",
        ]
        context_values = [value for value in context_values if value]

        for pattern in patterns:
            reason_codes: list[str] = []
            conflicts: list[str] = []
            if pattern.customer_specific:
                reason_codes.append("CUSTOMER_SPECIFIC_PATTERN_REJECTED")
            if pattern.jira_specific:
                reason_codes.append("JIRA_SPECIFIC_PATTERN_REJECTED")
            if (
                not request.include_analysis_candidates
                and not pattern.production_influence_allowed
            ):
                reason_codes.append("NOT_VALIDATED_FOR_PRODUCTION")
            if pattern.applicable_domains and request_domain not in {
                value.upper() for value in pattern.applicable_domains
            }:
                reason_codes.append("DOMAIN_MISMATCH")

            mode_score, _, mode_pattern = _best_similarity(
                [request.publishing_mode] if request.publishing_mode else [],
                pattern.applicable_publishing_modes,
            )
            if pattern.applicable_publishing_modes:
                if request.publishing_mode is None:
                    reason_codes.append("PUBLISHING_MODE_CONTEXT_MISSING")
                elif mode_score < 0.5:
                    reason_codes.append("PUBLISHING_MODE_MISMATCH")

            configuration_score, _, configuration_pattern = _best_similarity(
                [request.configuration_state] if request.configuration_state else [],
                pattern.applicable_configuration_states,
            )
            if pattern.applicable_configuration_states:
                if request.configuration_state is None:
                    reason_codes.append("CONFIGURATION_STATE_CONTEXT_MISSING")
                elif configuration_score < 0.5:
                    reason_codes.append("CONFIGURATION_STATE_MISMATCH")

            surface_score, surface_input, surface_pattern = _best_similarity(
                request.change_surfaces,
                pattern.abstract_change_surface,
            )
            signal_score, signal_input, signal_pattern = _best_similarity(
                request.abstract_signals,
                pattern.abstract_signals,
            )
            relationship_score, _, _ = _best_similarity(
                [*request.change_surfaces, *request.abstract_signals],
                pattern.relationship_to_explore,
            )
            surface_matches = not request.change_surfaces or surface_score >= 0.5
            signal_matches = not request.abstract_signals or signal_score >= 0.5
            if not surface_matches:
                reason_codes.append("CHANGE_SURFACE_MISMATCH")
            if not signal_matches:
                reason_codes.append("ABSTRACT_SIGNAL_MISMATCH")
            if (
                not request.change_surfaces
                and not request.abstract_signals
                and relationship_score < 0.5
            ):
                reason_codes.append("NO_ABSTRACT_RELATIONSHIP_MATCH")

            scope_targets = [
                *pattern.abstract_change_surface,
                *pattern.applicable_domains,
                *pattern.applicable_publishing_modes,
                *pattern.applicable_configuration_states,
                *pattern.abstract_signals,
                *pattern.question_families,
                *pattern.relationship_to_explore,
            ]
            for value in request.scope_constraints.explicit_out_of_scope:
                score, _, candidate = _best_similarity([value], scope_targets)
                if score >= 0.5:
                    conflicts.append(f"CURRENT_EXPLICIT_OOS:{candidate}")
            for value in request.scope_constraints.excluded_relationships:
                score, _, candidate = _best_similarity(
                    [value], pattern.relationship_to_explore
                )
                if score >= 0.5:
                    conflicts.append(f"CURRENT_RELATIONSHIP_EXCLUDED:{candidate}")
            for value in request.scope_constraints.current_product_decisions:
                score, _, candidate = _best_similarity([value], scope_targets)
                if score >= 0.5:
                    conflicts.append(f"CURRENT_PRODUCT_DECISION:{candidate}")
            for hard_negative in pattern.hard_negatives:
                score, _, _ = _best_similarity([hard_negative], context_values)
                if score >= 0.75:
                    conflicts.append(f"HARD_NEGATIVE:{hard_negative}")
            for counterexample in pattern.counterexamples:
                score, _, _ = _best_similarity([counterexample], context_values)
                if score >= 0.75:
                    conflicts.append(f"COUNTEREXAMPLE:{counterexample}")
            if conflicts:
                reason_codes.append("COUNTEREXAMPLE_OR_SCOPE_SUPPRESSION")

            if reason_codes:
                for code in set(reason_codes):
                    excluded[code] += 1
                if (
                    max(surface_score, signal_score, relationship_score) >= 0.5
                    and conflicts
                ):
                    suppressed.append(
                        QePatternSuppressedMatch(
                            pattern_id=pattern.pattern_id,
                            reason_codes=sorted(set(reason_codes)),
                            counterexample_conflicts=sorted(set(conflicts)),
                            recommended_families=pattern.question_families,
                            relationship_to_explore=pattern.relationship_to_explore,
                            preferred_evidence_sources=(
                                pattern.preferred_evidence_sources
                            ),
                            materiality=pattern.materiality,
                            blocking_default=pattern.blocking_default,
                            confidence=pattern.confidence,
                            applicability_score=max(
                                surface_score,
                                signal_score,
                                relationship_score,
                            ),
                        )
                    )
                continue

            domain_score = 1.0 if pattern.applicable_domains else 0.5
            ranked_mode_score = (
                mode_score if pattern.applicable_publishing_modes else 0.5
            )
            ranked_configuration_score = (
                configuration_score if pattern.applicable_configuration_states else 0.5
            )
            applicability = round(
                (0.35 * surface_score)
                + (0.25 * signal_score)
                + (0.10 * relationship_score)
                + (0.05 * domain_score)
                + (0.125 * ranked_mode_score)
                + (0.125 * ranked_configuration_score),
                6,
            )
            match_reason: list[str] = []
            if surface_score:
                match_reason.append(
                    f"change_surface:{surface_input}->{surface_pattern}"
                )
            if signal_score:
                match_reason.append(f"abstract_signal:{signal_input}->{signal_pattern}")
            if relationship_score:
                match_reason.append("semantic_relationship_match")
            if mode_score and mode_pattern:
                match_reason.append(f"publishing_mode:{mode_pattern}")
            if configuration_score and configuration_pattern:
                match_reason.append(f"configuration_state:{configuration_pattern}")
            matches.append(
                QePatternMatch(
                    pattern=pattern,
                    match_reason=match_reason,
                    applicability_score=applicability,
                    counterexample_conflicts=[],
                    recommended_families=pattern.question_families,
                    blocking_recommendations=(
                        pattern.question_families
                        if pattern.production_influence_allowed
                        and pattern.blocking_default
                        else []
                    ),
                    influence_allowed=pattern.production_influence_allowed,
                )
            )

        matches.sort(key=lambda row: (-row.applicability_score, row.pattern.pattern_id))
        selected = matches[: request.max_results]
        status = (
            QePatternProviderStatus.SUCCESS
            if selected
            else QePatternProviderStatus.EMPTY
        )
        warnings: list[str] = []
        if request.include_analysis_candidates:
            warnings.append(
                "Analysis candidates are observable but cannot influence production reasoning."
            )
        if active_count == 0:
            warnings.append(
                "No Human-QE-approved ACTIVE patterns exist; production influence is empty."
            )
        return ResolveQePatternsResponse(
            provider_status=status,
            pattern_library_version=library_version,
            pattern_library_sha256=library_sha,
            pattern_count=len(patterns),
            validated_production_pattern_count=active_count,
            matched_patterns=selected,
            suppressed_patterns=sorted(
                suppressed,
                key=lambda row: row.pattern_id,
            ),
            excluded_pattern_counts=dict(sorted(excluded.items())),
            warnings=warnings,
        )


_DEFAULT_RESOLVER = QePatternResolver()


def resolve_qe_patterns(
    request: ResolveQePatternsRequest,
) -> ResolveQePatternsResponse:
    """Resolve generic investigation patterns; never generate final ACs."""

    return _DEFAULT_RESOLVER.resolve(request)


def pattern_error_response(
    *,
    status: QePatternProviderStatus,
    error_code: str,
    warning: str,
) -> ResolveQePatternsResponse:
    """Build one redacted, schema-valid fail-closed MCP response."""

    return ResolveQePatternsResponse(
        provider_status=status,
        pattern_library_version="NOT_LOADED",
        pattern_count=0,
        validated_production_pattern_count=0,
        warnings=[warning],
        error_code=error_code,
    )


__all__ = [
    "PatternLibraryInvalid",
    "PatternLibraryProvider",
    "PatternLibraryUnavailable",
    "QePatternResolver",
    "TrainV2PatternLibraryProvider",
    "pattern_error_response",
    "resolve_qe_patterns",
]
