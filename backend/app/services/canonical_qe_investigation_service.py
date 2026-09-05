"""Deterministic Pattern MCP preparation for the canonical QE runtime.

This adapter is deliberately discovery-only.  It converts only Human-QE-
approved ACTIVE Pattern MCP matches into typed investigation-family inputs.
It never creates ContractFacts, evidence, hypotheses, or acceptance criteria.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any, Protocol

from pydantic import ValidationError

from app.core.schemas_canonical_test_plan_runtime import (
    AbstractSignal,
    ChangeSurface,
    ChangeSurfaceKind,
    ContractFactSet,
    ContractFactType,
    CurrentPatternApplicability,
    DomainActivation,
    EvidenceSourceType,
    FamilyActivationDecision,
    GenerationRequest,
    InvestigationFamilySourceContribution,
    InvestigationFamilySourceKind,
    InvestigationMateriality,
    InvestigationRetrievalHint,
    IssueDomain,
    MandatoryInvestigationFamily,
    MatchedHumanPatternView,
    PatternApplicabilityRecord,
    PatternLookupCallRecord,
    PatternLookupResult,
    PatternLookupRuntimeStatus,
    PatternSuggestionState,
    QeInvestigationConstraints,
    QeInvestigationPreparation,
    ReasoningPatternActivation,
    ScopeResolution,
    SemanticDimension,
    _safe_handoff_text,
)
from app.core.schemas_qe_pattern_mcp import (
    QePatternProviderStatus,
    ResolveQePatternsRequest,
    ResolveQePatternsResponse,
    SharedLearningContext,
    SharedLearningEnvelope,
    SharedLearningMode,
)
from app.services.qe_pattern_mcp_service import QePatternResolver, configured_shared_learning_mode


PATTERN_PROVIDER_UNAVAILABLE = "PATTERN_PROVIDER_UNAVAILABLE"
PATTERN_PROVIDER_ERROR = "PATTERN_PROVIDER_ERROR"
PATTERN_PROVIDER_INVALID_RESPONSE = "PATTERN_PROVIDER_INVALID_RESPONSE"


class PatternResolver(Protocol):
    def resolve(self, request: ResolveQePatternsRequest) -> Any: ...


_MATERIALITY_ORDER = {
    InvestigationMateriality.P0: 0,
    InvestigationMateriality.P1: 1,
    InvestigationMateriality.P2: 2,
    InvestigationMateriality.P3: 3,
}

_P0_RISK_RE = re.compile(
    r"\b(data\s+loss|corrupt(?:ion|ed)?|identity\s+corruption|"
    r"reference\s+corruption|wrong\s+persistent\s+state|orphan(?:ed)?\s+state)\b",
    re.IGNORECASE,
)

_SURFACE_FAMILY_MAP: dict[ChangeSurfaceKind, tuple[SemanticDimension, ...]] = {
    ChangeSurfaceKind.WRITES: (SemanticDimension.PERSISTED_STATE,),
    ChangeSurfaceKind.CONSUMERS: (SemanticDimension.DIRECT_CONSUMERS,),
    ChangeSurfaceKind.CONFIG_DEPENDENCIES: (SemanticDimension.GOVERNING_CONFIGURATION,),
    ChangeSurfaceKind.GENERATED_ARTIFACTS: (SemanticDimension.GENERATED_OUTPUT,),
    ChangeSurfaceKind.SHARED_PROCESSORS: (SemanticDimension.SIBLING_CONSUMERS,),
    ChangeSurfaceKind.ERROR_PATHS: (
        SemanticDimension.NEGATIVE_STATE,
        SemanticDimension.LIFECYCLE,
    ),
    ChangeSurfaceKind.PERSISTED_STATE: (
        SemanticDimension.PERSISTED_STATE,
        SemanticDimension.LIFECYCLE,
    ),
    ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS: (
        SemanticDimension.DOWNSTREAM_PROCESSOR,
    ),
}

_CURRENT_SOURCE_KINDS = {
    InvestigationFamilySourceKind.CURRENT_CHANGE_SURFACE,
    InvestigationFamilySourceKind.DETERMINISTIC_REASONING_PATTERN,
    InvestigationFamilySourceKind.DOMAIN_INVARIANT,
    InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
    InvestigationFamilySourceKind.NORMATIVE_SEMANTIC,
}

_STRONG_CURRENT_SOURCE_KINDS = {
    InvestigationFamilySourceKind.CURRENT_CHANGE_SURFACE,
    InvestigationFamilySourceKind.DETERMINISTIC_REASONING_PATTERN,
    InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
    InvestigationFamilySourceKind.NORMATIVE_SEMANTIC,
}


def _bounded_constraint(value: Any, *, limit: int = 200) -> str:
    """Keep resolver constraints useful without feeding unbounded Jira prose."""

    normalized = " ".join(str(value or "").split())
    return normalized if 0 < len(normalized) <= limit else ""


def _strongest_materiality(
    contributions: list[InvestigationFamilySourceContribution],
) -> InvestigationMateriality:
    return min(
        (row.materiality for row in contributions),
        key=lambda value: _MATERIALITY_ORDER[value],
    )


def _current_issue_materiality(
    facts: ContractFactSet,
    surfaces: list[ChangeSurface],
    domains: list[DomainActivation],
) -> InvestigationMateriality:
    """Assess only generic current-case impact signals, never feature popularity."""

    material_text = " ".join(
        fact.literal
        for fact in facts.facts
        if fact.fact_type
        in {
            ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
        }
    )
    if _P0_RISK_RE.search(material_text):
        return InvestigationMateriality.P0
    if any(
        fact.fact_type
        in {
            ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
            ContractFactType.COMPATIBILITY_REQUIREMENTS,
            ContractFactType.LIMITS,
            ContractFactType.COUNTS,
        }
        for fact in facts.facts
    ):
        return InvestigationMateriality.P1
    if any(
        surface.kind
        in {
            ChangeSurfaceKind.WRITES,
            ChangeSurfaceKind.CONSUMERS,
            ChangeSurfaceKind.CONFIG_DEPENDENCIES,
            ChangeSurfaceKind.GENERATED_ARTIFACTS,
            ChangeSurfaceKind.SHARED_PROCESSORS,
            ChangeSurfaceKind.ERROR_PATHS,
            ChangeSurfaceKind.PERSISTED_STATE,
            ChangeSurfaceKind.DOWNSTREAM_DECISION_CONSUMERS,
        }
        for surface in surfaces
    ) or any(row.domain == IssueDomain.PERFORMANCE for row in domains):
        return InvestigationMateriality.P1
    return InvestigationMateriality.P2


def _activation_decision(
    *,
    rows: list[InvestigationFamilySourceContribution],
    materiality: InvestigationMateriality,
    matched_pattern_ids: set[str],
    counterexample_evidence: list[str],
) -> tuple[FamilyActivationDecision, str]:
    current_rows = [row for row in rows if row.source in _CURRENT_SOURCE_KINDS]
    strong_current_rows = [
        row for row in current_rows if row.source in _STRONG_CURRENT_SOURCE_KINDS
    ]
    explicit_rows = [
        row
        for row in current_rows
        if row.source == InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT
    ]
    pattern_rows = [
        row for row in rows if row.source == InvestigationFamilySourceKind.PATTERN_MCP
    ]
    matched_pattern_rows = [
        row for row in pattern_rows if set(row.linked_pattern_ids) & matched_pattern_ids
    ]

    if current_rows:
        current_requires_blocking = any(row.blocking_status for row in current_rows)
        pattern_blocking_is_verified = bool(strong_current_rows) and any(
            row.blocking_status for row in matched_pattern_rows
        )
        if materiality in {
            InvestigationMateriality.P0,
            InvestigationMateriality.P1,
        } and (current_requires_blocking or pattern_blocking_is_verified):
            reason = (
                "Current explicit evidence overrides the historical negative boundary."
                if explicit_rows and counterexample_evidence
                else "Current evidence verifies a material relationship whose omission could make the UAC incomplete."
            )
            return FamilyActivationDecision.ACTIVATE_BLOCKING, reason
        return (
            FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
            "Current evidence independently supports this useful investigation family.",
        )

    if counterexample_evidence:
        return (
            FamilyActivationDecision.DO_NOT_ACTIVATE,
            "Current scope or counterexample evidence rejects the historical relationship.",
        )
    if matched_pattern_rows:
        if materiality in {
            InvestigationMateriality.P0,
            InvestigationMateriality.P1,
        }:
            return (
                FamilyActivationDecision.UNRESOLVED_APPLICABILITY,
                "The Human-backed pattern is material, but current evidence has not verified that its relationship exists here.",
            )
        return (
            FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
            "The pattern supports non-blocking exploration while current applicability remains unverified.",
        )
    return (
        FamilyActivationDecision.DO_NOT_ACTIVATE,
        "No current evidence supports this candidate family.",
    )


def _current_constraints(
    facts: ContractFactSet,
    scope: ScopeResolution,
) -> QeInvestigationConstraints:
    out_of_scope = {
        *(_bounded_constraint(value) for value in scope.out_of_scope),
        *(
            _bounded_constraint(fact.literal)
            for fact in facts.facts
            if fact.authoritative and fact.fact_type == ContractFactType.OUT_OF_SCOPE
        ),
    }
    out_of_scope.discard("")
    decisions = {
        _bounded_constraint(fact.normalized_value or fact.literal)
        for fact in facts.facts
        if fact.authoritative
        and fact.fact_type
        in {
            ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
            ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS,
        }
    }
    decisions.discard("")
    return QeInvestigationConstraints(
        explicit_out_of_scope=sorted(out_of_scope)[:20],
        excluded_relationships=[],
        current_product_decisions=sorted(decisions)[:5],
    )


def _warning_codes(response: ResolveQePatternsResponse) -> list[str]:
    values = [response.error_code] if response.error_code else []
    if response.warnings:
        values.append("PATTERN_PROVIDER_REPORTED_WARNING")
    return sorted(set(values))


class CanonicalQeInvestigationService:
    """Prepare one typed investigation payload inside the canonical path."""

    def __init__(self, resolver: PatternResolver | None = None) -> None:
        self._resolver: PatternResolver = resolver or QePatternResolver()

    @property
    def resolver(self) -> PatternResolver:
        """Expose the immutable dependency for paired-runtime parity."""

        return self._resolver

    def lookup_patterns(
        self,
        *,
        facts: ContractFactSet,
        scope: ScopeResolution,
        domains: list[DomainActivation],
        surfaces: list[ChangeSurface],
        signals: list[AbstractSignal],
        generation_request: GenerationRequest | None = None,
    ) -> PatternLookupResult:
        """Contain every malformed-provider boundary before canonical reasoning."""

        try:
            shared_results: list[tuple[DomainActivation, Any]] = []
            result = self._lookup_patterns(
                facts=facts,
                scope=scope,
                domains=domains,
                surfaces=surfaces,
                signals=signals,
                generation_request=generation_request,
                shared_results=shared_results,
            )
        except (ValidationError, ValueError, TypeError, AttributeError):
            return PatternLookupResult(
                status=PatternLookupRuntimeStatus.INVALID_RESPONSE,
                warning_codes=[PATTERN_PROVIDER_INVALID_RESPONSE],
            )
        except Exception:
            return PatternLookupResult(
                status=PatternLookupRuntimeStatus.PROVIDER_ERROR,
                warning_codes=[PATTERN_PROVIDER_ERROR],
            )
        try:
            return self._merge_shared_results(result, shared_results,
                facts=facts, scope=scope, surfaces=surfaces, signals=signals)
        except Exception:
            # An independently malformed shared handoff must not erase a
            # successfully validated TRAIN/explicit-provider baseline.
            return result.model_copy(update={"warning_codes": [
                *result.warning_codes, "SHARED_LEARNING_INVALID_RESPONSE"]})

    def _merge_shared_results(self, baseline, shared_results, *, facts, scope, surfaces, signals):
        """Validate the shared lane independently so its failures retain baseline."""
        calls = list(baseline.calls)
        warnings = list(baseline.warning_codes)
        matched = {row.pattern_id: row for row in baseline.matched_human_patterns}
        applicability = {row.pattern_id: row for row in baseline.applicability_records}
        guidance = {}
        validated_shared = []
        for domain, payload in shared_results:
            try:
                envelope = SharedLearningEnvelope.model_validate(payload)
            except (ValueError, TypeError, ValidationError):
                warnings.append("SHARED_LEARNING_INVALID_RESPONSE")
                calls.append(PatternLookupCallRecord(domain=domain.domain,
                    provider_name="SHARED_UAC_LEARNING", provider_status="INVALID_LIBRARY",
                    pattern_library_version="NOT_LOADED",
                    warning_codes=["SHARED_LEARNING_INVALID_RESPONSE"]))
                continue
            validated_shared.append((domain, envelope))
        publication_ids = {envelope.publication_id for _, envelope in validated_shared
            if envelope.publication_id}
        if len(publication_ids) > 1:
            # A concurrent review/revocation between domain reads must never
            # splice revisions from two publications into one investigation.
            warning = "SHARED_LEARNING_PUBLICATION_CHANGED_DURING_LOOKUP"
            calls.extend(PatternLookupCallRecord(domain=domain.domain,
                provider_name="SHARED_UAC_LEARNING", provider_status="INVALID_LIBRARY",
                pattern_library_version=envelope.publication_id or "NOT_LOADED",
                pattern_library_sha256=envelope.publication_id,
                shared_learning_mode=envelope.mode.value, warning_codes=[warning])
                for domain, envelope in validated_shared)
            return baseline.model_copy(update={"calls": calls,
                "warning_codes": [*warnings, warning]})
        for domain, envelope in validated_shared:
            shared_warning_codes = sorted({
                *([envelope.error_code] if envelope.error_code else []),
                *(value for value in envelope.warnings
                    if re.fullmatch(r"SHARED_LEARNING_[A-Z0-9_]{1,100}", value)),
            })
            call = PatternLookupCallRecord(domain=domain.domain,
                provider_name="SHARED_UAC_LEARNING", provider_status=envelope.status,
                pattern_library_version=envelope.publication_id or "NOT_LOADED",
                pattern_library_sha256=envelope.publication_id,
                shared_learning_mode=envelope.mode.value,
                matched_pattern_ids=[row.pattern.pattern_id for row in envelope.matched_patterns],
                suppressed_pattern_ids=[row.pattern_id for row in envelope.suppressed_patterns],
                shadow_pattern_ids=envelope.shadow_pattern_ids,
                shadow_authoring_guidance_ids=envelope.shadow_authoring_guidance_ids,
                retrieved_authoring_guidance_ids=[row.lesson_id for row in envelope.authoring_guidance],
                excluded_pattern_counts=envelope.excluded_pattern_counts,
                warning_codes=shared_warning_codes)
            calls.append(call)
            warnings.extend(shared_warning_codes)
            if envelope.mode != SharedLearningMode.ENABLED or envelope.status not in {"SUCCESS", "EMPTY"}:
                continue
            # Reuse exactly the existing normalized Pattern handoff. The shared
            # source has its own snapshot hash, never a rebound baseline hash.
            shared_response = ResolveQePatternsResponse(
                provider_name="SHARED_UAC_LEARNING",
                provider_status="SUCCESS" if envelope.matched_patterns else "EMPTY",
                pattern_library_version=envelope.publication_id or "EMPTY",
                pattern_library_sha256=envelope.publication_id,
                pattern_count=envelope.pattern_count,
                validated_production_pattern_count=envelope.pattern_count,
                matched_patterns=envelope.matched_patterns,
                suppressed_patterns=envelope.suppressed_patterns)

            class PublishedSharedResolver:
                def resolve(self, _request):
                    return shared_response

            normalized = CanonicalQeInvestigationService(PublishedSharedResolver()).lookup_patterns(
                facts=facts, scope=scope, domains=[domain], surfaces=surfaces, signals=signals)
            if normalized.status not in {PatternLookupRuntimeStatus.AVAILABLE_MATCH,
                    PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH}:
                call.provider_status = "INVALID_LIBRARY"
                call.matched_pattern_ids = []
                call.retrieved_authoring_guidance_ids = []
                warnings.append("SHARED_LEARNING_INVALID_RESPONSE")
                continue
            for row in normalized.matched_human_patterns:
                prior = matched.get(row.pattern_id)
                if prior is None or row.applicability > prior.applicability:
                    matched[row.pattern_id] = row
            applicability.update({row.pattern_id: row for row in normalized.applicability_records})
            for row in envelope.authoring_guidance:
                safe_text = _safe_handoff_text(row.guidance, max_length=2000)
                if safe_text:
                    guidance[(row.lesson_id, row.lesson_version)] = row.model_copy(update={"guidance": safe_text})
        payload = baseline.model_dump(mode="python")
        payload.update(calls=calls, warning_codes=warnings,
            matched_human_patterns=list(matched.values()), applicability_records=list(applicability.values()),
            authoring_guidance=[guidance[key] for key in sorted(guidance)][:50])
        if matched:
            payload["status"] = PatternLookupRuntimeStatus.AVAILABLE_MATCH
        return PatternLookupResult.model_validate(payload)

    def _lookup_patterns(
        self,
        *,
        facts: ContractFactSet,
        scope: ScopeResolution,
        domains: list[DomainActivation],
        surfaces: list[ChangeSurface],
        signals: list[AbstractSignal],
        generation_request: GenerationRequest | None = None,
        shared_results: list[tuple[DomainActivation, Any]] | None = None,
    ) -> PatternLookupResult:
        """Call the shared resolver once per domain and fail Pattern influence closed."""

        constraints = _current_constraints(facts, scope)
        active_domains = sorted(
            {row.domain for row in domains} or {IssueDomain.OTHER},
            key=lambda value: value.value,
        )
        change_surface_tokens = sorted({row.kind.value for row in surfaces})
        signal_tokens = sorted({row.kind.value for row in signals})
        if not change_surface_tokens and not signal_tokens:
            return PatternLookupResult(
                status=PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH,
                calls=[],
                matched_human_patterns=[],
                applicability_records=[],
            )
        publishing_mode = (
            scope.primary_publishing_mode
            or scope.primary_output_type
            or scope.primary_preset_type
            or None
        )
        feature_states = sorted(
            {
                fact.literal
                for fact in facts.facts
                if fact.fact_type == ContractFactType.FEATURE_STATE
            }
        )
        configuration_state = feature_states[0] if len(feature_states) == 1 else None
        calls: list[PatternLookupCallRecord] = []
        matched_by_id: dict[str, MatchedHumanPatternView] = {}
        pattern_payloads: dict[str, str] = {}
        applicability: dict[str, PatternApplicabilityRecord] = {}
        failure_status: PatternLookupRuntimeStatus | None = None
        failure_warning: str | None = None

        for domain in active_domains:
            try:
                request = ResolveQePatternsRequest(
                    domain=domain.value,
                    change_surfaces=change_surface_tokens,
                    abstract_signals=signal_tokens,
                    publishing_mode=publishing_mode,
                    configuration_state=configuration_state,
                    current_jira_key=generation_request.jira_key if generation_request else "",
                    subject_terms=sorted({_bounded_constraint(row.entity, limit=500) for row in surfaces if _bounded_constraint(row.entity, limit=500)})[:30],
                    deployment_model=scope.deployment_modes[0] if len(scope.deployment_modes) == 1 else None,
                    product_version=scope.product_versions[0] if len(scope.product_versions) == 1 else None,
                    scope_constraints={
                        "explicit_out_of_scope": constraints.explicit_out_of_scope,
                        "excluded_relationships": constraints.excluded_relationships,
                        "current_product_decisions": (
                            constraints.current_product_decisions
                        ),
                    },
                    include_analysis_candidates=False,
                )
                contextual = getattr(self._resolver, "resolve_for_runtime", None)
                if generation_request is not None and callable(contextual):
                    context = SharedLearningContext(
                        tenant_id=generation_request.tenant_id,
                        principal_id=generation_request.principal.principal_id,
                        authenticated=generation_request.runtime_context.get("shared_learning_authenticated") is True,
                        mode=configured_shared_learning_mode(),
                        benchmark_isolation=bool(generation_request.benchmark_split))
                    raw_response = contextual(request, context)
                else:
                    raw_response = self._resolver.resolve(request)
                response_payload = (
                    raw_response.model_dump(mode="python")
                    if isinstance(raw_response, ResolveQePatternsResponse)
                    else raw_response
                )
                if isinstance(response_payload, dict):
                    response_payload = dict(response_payload)
                    shared_payload = response_payload.pop("shared_learning", None)
                    if shared_payload is not None and shared_results is not None:
                        shared_results.append((DomainActivation(domain=domain, confidence=1.0), shared_payload))
                response = ResolveQePatternsResponse.model_validate(response_payload)
            except (ValidationError, ValueError, TypeError, AttributeError):
                failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                break
            except Exception:
                failure_status = PatternLookupRuntimeStatus.PROVIDER_ERROR
                failure_warning = PATTERN_PROVIDER_ERROR
                break

            calls.append(
                PatternLookupCallRecord(
                    domain=domain,
                    provider_name=response.provider_name,
                    provider_status=response.provider_status.value,
                    pattern_library_version=response.pattern_library_version,
                    pattern_library_sha256=response.pattern_library_sha256,
                    matched_pattern_ids=[
                        row.pattern.pattern_id for row in response.matched_patterns
                    ],
                    suppressed_pattern_ids=[
                        row.pattern_id for row in response.suppressed_patterns
                    ],
                    warning_codes=_warning_codes(response),
                )
            )
            for suppressed in response.suppressed_patterns:
                suppressed_families = sorted(
                    {
                        SemanticDimension(value)
                        for value in suppressed.recommended_families
                    },
                    key=lambda value: value.value,
                )
                suppressed_sources = sorted(
                    {
                        EvidenceSourceType(value)
                        for value in suppressed.preferred_evidence_sources
                    },
                    key=lambda value: value.value,
                )
                applicability[suppressed.pattern_id] = PatternApplicabilityRecord(
                    pattern_id=suppressed.pattern_id,
                    suggestion_state=PatternSuggestionState.PATTERN_SUGGESTED,
                    current_applicability=(
                        CurrentPatternApplicability.CURRENTLY_REJECTED
                    ),
                    reason_codes=[
                        *suppressed.reason_codes,
                        *(
                            "COUNTEREXAMPLE_OR_SCOPE_CONFLICT"
                            for _ in suppressed.counterexample_conflicts[:1]
                        ),
                    ],
                    recommended_question_families=suppressed_families,
                    counterexample_evidence=[
                        *suppressed.counterexample_conflicts,
                        *suppressed.reason_codes,
                    ],
                    preferred_evidence_sources=suppressed_sources,
                    materiality=(
                        InvestigationMateriality(suppressed.materiality.value)
                        if suppressed.materiality is not None
                        else None
                    ),
                    blocking_default=suppressed.blocking_default,
                    confidence=suppressed.confidence,
                    applicability=suppressed.applicability_score,
                )

            if response.provider_status == QePatternProviderStatus.UNAVAILABLE:
                failure_status = PatternLookupRuntimeStatus.PROVIDER_UNAVAILABLE
                failure_warning = PATTERN_PROVIDER_UNAVAILABLE
                break
            if response.provider_status in {
                QePatternProviderStatus.INVALID_LIBRARY,
                QePatternProviderStatus.INVALID_REQUEST,
            }:
                failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                break
            if response.provider_status == QePatternProviderStatus.SUCCESS:
                if not response.matched_patterns:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
            elif response.provider_status == QePatternProviderStatus.EMPTY:
                if response.matched_patterns:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
            else:
                failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                break

            for match in response.matched_patterns:
                pattern = match.pattern
                authority_is_bound = (
                    pattern.production_influence_allowed
                    and pattern.provenance.human_backed
                    and not pattern.provenance.raw_human_uac_included
                    and pattern.provenance.approval_authority == "HUMAN_QE"
                    and pattern.provenance.approval_overlay_sha256 is not None
                    and pattern.provenance.source_sha256
                    == response.pattern_library_sha256
                    and not match.counterexample_conflicts
                    and set(match.recommended_families).issubset(
                        set(pattern.question_families)
                    )
                    and set(match.blocking_recommendations).issubset(
                        set(match.recommended_families)
                    )
                )
                if not match.influence_allowed or not authority_is_bound:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
                try:
                    families = sorted(
                        {
                            SemanticDimension(value)
                            for value in match.recommended_families
                        },
                        key=lambda value: value.value,
                    )
                    preferred_sources = sorted(
                        {
                            EvidenceSourceType(value)
                            for value in pattern.preferred_evidence_sources
                        },
                        key=lambda value: value.value,
                    )
                    materiality = InvestigationMateriality(pattern.materiality.value)
                except ValueError:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
                if not families or pattern.confidence is None:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
                pattern_projection = pattern.model_dump_json(
                    exclude={"provenance", "supporting_case_ids"},
                    exclude_none=True,
                )
                prior = pattern_payloads.get(pattern.pattern_id)
                if prior is not None and prior != pattern_projection:
                    failure_status = PatternLookupRuntimeStatus.INVALID_RESPONSE
                    failure_warning = PATTERN_PROVIDER_INVALID_RESPONSE
                    break
                pattern_payloads[pattern.pattern_id] = pattern_projection
                current = matched_by_id.get(pattern.pattern_id)
                view = MatchedHumanPatternView(
                    pattern_id=pattern.pattern_id,
                    pattern_version=pattern.pattern_version,
                    lesson_id=pattern.lesson_id,
                    lesson_kind=pattern.lesson_kind,
                    abstract_trigger=[
                        *pattern.abstract_change_surface,
                        *pattern.abstract_signals,
                    ],
                    relationship_to_explore=pattern.relationship_to_explore,
                    support_count=pattern.human_support_count,
                    independent_case_count=pattern.independent_case_count,
                    counterexample_summary=[
                        f"COUNTEREXAMPLES_REVIEWED:{len(pattern.counterexamples)}",
                        f"HARD_NEGATIVES_REVIEWED:{len(pattern.hard_negatives)}",
                    ],
                    confidence=pattern.confidence,
                    applicability=max(
                        match.applicability_score,
                        current.applicability if current is not None else 0.0,
                    ),
                    recommended_question_families=families,
                    preferred_evidence_sources=preferred_sources,
                    materiality=materiality,
                    blocking_default=pattern.blocking_default,
                )
                matched_by_id[pattern.pattern_id] = view
                applicability[pattern.pattern_id] = PatternApplicabilityRecord(
                    pattern_id=pattern.pattern_id,
                    suggestion_state=PatternSuggestionState.PATTERN_SUGGESTED,
                    current_applicability=(
                        CurrentPatternApplicability.CURRENTLY_UNRESOLVED
                    ),
                    reason_codes=["CURRENT_EVIDENCE_VERIFICATION_REQUIRED"],
                    recommended_question_families=families,
                    preferred_evidence_sources=preferred_sources,
                    materiality=materiality,
                    blocking_default=pattern.blocking_default,
                    confidence=pattern.confidence,
                    applicability=view.applicability,
                )
            if failure_status is not None:
                break

        if failure_status is not None:
            return PatternLookupResult(
                status=failure_status,
                calls=calls,
                matched_human_patterns=[],
                applicability_records=[
                    row
                    for row in applicability.values()
                    if row.current_applicability
                    == CurrentPatternApplicability.CURRENTLY_REJECTED
                ],
                warning_codes=[failure_warning] if failure_warning else [],
            )
        matched = list(matched_by_id.values())
        return PatternLookupResult(
            status=(
                PatternLookupRuntimeStatus.AVAILABLE_MATCH
                if matched
                else PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH
            ),
            calls=calls,
            matched_human_patterns=matched,
            applicability_records=list(applicability.values()),
        )

    def prepare_qe_investigation(
        self,
        *,
        request: GenerationRequest,
        facts: ContractFactSet,
        scope: ScopeResolution,
        domains: list[DomainActivation],
        surfaces: list[ChangeSurface],
        signals: list[AbstractSignal],
        activations: list[ReasoningPatternActivation],
        deterministic_dimensions: set[SemanticDimension],
        pattern_lookup: PatternLookupResult,
    ) -> QeInvestigationPreparation:
        """Merge current and Pattern-backed family sources without authority drift."""

        contributions: dict[
            SemanticDimension, list[InvestigationFamilySourceContribution]
        ] = defaultdict(list)
        all_surface_ids = [row.surface_id for row in surfaces]
        signal_surface_ids = {
            signal.signal_id: signal.source_surface_ids for signal in signals
        }
        signals_by_id = {signal.signal_id: signal for signal in signals}
        issue_materiality = _current_issue_materiality(facts, surfaces, domains)
        domain_confidence = max(
            (row.confidence for row in domains),
            default=0.5,
        )

        for dimension in sorted(deterministic_dimensions, key=lambda row: row.value):
            contributions[dimension].append(
                InvestigationFamilySourceContribution(
                    source=InvestigationFamilySourceKind.DOMAIN_INVARIANT,
                    source_ids=[row.domain.value for row in domains],
                    why_required=(
                        f"Current domain and behavior model require {dimension.value}."
                    ),
                    linked_change_surface_ids=all_surface_ids,
                    materiality=InvestigationMateriality.P2,
                    confidence=domain_confidence,
                )
            )
        for surface in surfaces:
            for dimension in _SURFACE_FAMILY_MAP.get(surface.kind, ()):
                contributions[dimension].append(
                    InvestigationFamilySourceContribution(
                        source=InvestigationFamilySourceKind.CURRENT_CHANGE_SURFACE,
                        source_ids=[
                            surface.surface_id,
                            *surface.source_evidence_ids,
                        ],
                        why_required=(
                            f"Current {surface.kind.value} evidence makes "
                            f"{dimension.value} applicable."
                        ),
                        linked_change_surface_ids=[surface.surface_id],
                        materiality=issue_materiality,
                        blocking_status=(
                            issue_materiality == InvestigationMateriality.P0
                        ),
                        confidence=surface.confidence,
                    )
                )
        for activation in activations:
            linked_surfaces = sorted(
                {
                    surface_id
                    for signal_id in activation.source_signal_ids
                    for surface_id in signal_surface_ids.get(signal_id, [])
                }
            )
            contributions[activation.semantic_dimension].append(
                InvestigationFamilySourceContribution(
                    source=(
                        InvestigationFamilySourceKind.DETERMINISTIC_REASONING_PATTERN
                    ),
                    source_ids=[activation.activation_id],
                    why_required=(
                        "A current change signal activated the canonical "
                        f"{activation.question_family.value} reasoning family."
                    ),
                    linked_change_surface_ids=linked_surfaces,
                    materiality=issue_materiality,
                    blocking_status=(issue_materiality == InvestigationMateriality.P0),
                    confidence=max(
                        (
                            signals_by_id[signal_id].confidence
                            for signal_id in activation.source_signal_ids
                            if signal_id in signals_by_id
                        ),
                        default=0.5,
                    ),
                )
            )
        direct_fact_ids = [
            fact.fact_id
            for fact in facts.facts
            if fact.fact_type == ContractFactType.DIRECT_EXPECTED_BEHAVIOR
        ]
        if direct_fact_ids:
            contributions[SemanticDimension.GOVERNING_SEMANTICS].append(
                InvestigationFamilySourceContribution(
                    source=InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
                    source_ids=direct_fact_ids,
                    why_required=(
                        "The current Jira states expected behavior that must be "
                        "checked against governing semantics."
                    ),
                    linked_change_surface_ids=all_surface_ids,
                    materiality=issue_materiality,
                    blocking_status=(issue_materiality == InvestigationMateriality.P0),
                    confidence=1.0,
                )
            )
        negative_fact_ids = [
            fact.fact_id
            for fact in facts.facts
            if fact.fact_type == ContractFactType.EXPLICIT_NEGATIVE_REQUIREMENTS
        ]
        if negative_fact_ids:
            contributions[SemanticDimension.NEGATIVE_STATE].append(
                InvestigationFamilySourceContribution(
                    source=InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
                    source_ids=negative_fact_ids,
                    why_required=(
                        "The current Jira defines a negative boundary that protects "
                        "supported behavior."
                    ),
                    linked_change_surface_ids=all_surface_ids,
                    materiality=issue_materiality,
                    blocking_status=(issue_materiality == InvestigationMateriality.P0),
                    confidence=1.0,
                )
            )
        configuration_fact_ids = [
            fact.fact_id
            for fact in facts.facts
            if fact.fact_type
            in {
                ContractFactType.DITA_OT_PROCESSING_STATE,
                ContractFactType.EXACT_DEFAULTS,
                ContractFactType.PRESET_TYPE,
            }
        ]
        if configuration_fact_ids:
            contributions[SemanticDimension.GOVERNING_CONFIGURATION].append(
                InvestigationFamilySourceContribution(
                    source=InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
                    source_ids=configuration_fact_ids,
                    why_required=(
                        "The current Jira defines product configuration or an exact "
                        "configuration value."
                    ),
                    linked_change_surface_ids=all_surface_ids,
                    materiality=issue_materiality,
                    blocking_status=(issue_materiality == InvestigationMateriality.P0),
                    confidence=1.0,
                )
            )
        for pattern in pattern_lookup.matched_human_patterns:
            for family in pattern.recommended_question_families:
                contributions[family].append(
                    InvestigationFamilySourceContribution(
                        source=InvestigationFamilySourceKind.PATTERN_MCP,
                        source_ids=[pattern.pattern_id],
                        why_required=(
                            f"Human-backed pattern {pattern.pattern_id} recommends "
                            f"investigating {family.value}; current evidence must "
                            "still verify applicability before it can block acceptance."
                        ),
                        linked_change_surface_ids=all_surface_ids,
                        linked_pattern_ids=[pattern.pattern_id],
                        materiality=pattern.materiality,
                        # Historical blocking_default is a recommendation, not
                        # current-case acceptance authority.  The normalized
                        # pattern view retains it for trace/debug purposes.
                        blocking_status=pattern.blocking_default,
                        confidence=round(
                            pattern.confidence * pattern.applicability,
                            6,
                        ),
                        preferred_evidence_sources=(pattern.preferred_evidence_sources),
                    )
                )

        for applicability in pattern_lookup.applicability_records:
            if (
                applicability.current_applicability
                != CurrentPatternApplicability.CURRENTLY_REJECTED
            ):
                continue
            for family in applicability.recommended_question_families:
                contributions[family].append(
                    InvestigationFamilySourceContribution(
                        source=InvestigationFamilySourceKind.PATTERN_MCP,
                        source_ids=[applicability.pattern_id],
                        why_required=(
                            f"Human-backed pattern {applicability.pattern_id} was "
                            "considered and rejected for the current case."
                        ),
                        linked_change_surface_ids=all_surface_ids,
                        linked_pattern_ids=[applicability.pattern_id],
                        materiality=(
                            applicability.materiality or InvestigationMateriality.P2
                        ),
                        blocking_status=False,
                        confidence=round(
                            (applicability.confidence or 0.0)
                            * (applicability.applicability or 0.0),
                            6,
                        ),
                        preferred_evidence_sources=(
                            applicability.preferred_evidence_sources
                        ),
                    )
                )

        matched_pattern_ids = {
            pattern.pattern_id for pattern in pattern_lookup.matched_human_patterns
        }
        counterexamples_by_family: dict[SemanticDimension, list[str]] = defaultdict(
            list
        )
        for applicability in pattern_lookup.applicability_records:
            if (
                applicability.current_applicability
                != CurrentPatternApplicability.CURRENTLY_REJECTED
            ):
                continue
            for family in applicability.recommended_question_families:
                counterexamples_by_family[family].extend(
                    [
                        *applicability.counterexample_evidence,
                        *applicability.reason_codes,
                    ]
                )

        families: list[MandatoryInvestigationFamily] = []
        for family, rows in contributions.items():
            materiality = _strongest_materiality(rows)
            counterexample_evidence = sorted(set(counterexamples_by_family[family]))
            decision, applicability_reason = _activation_decision(
                rows=rows,
                materiality=materiality,
                matched_pattern_ids=matched_pattern_ids,
                counterexample_evidence=counterexample_evidence,
            )
            families.append(
                MandatoryInvestigationFamily(
                    family_id=family,
                    sources=rows,
                    materiality=materiality,
                    activation_decision=decision,
                    counterexample_evidence=counterexample_evidence,
                    confidence=max((row.confidence for row in rows), default=0.0),
                    applicability_reason=applicability_reason,
                )
            )
        open_decisions = [
            *scope.unresolved_fields,
            *(
                fact.literal
                for fact in facts.facts
                if fact.fact_type
                in {
                    ContractFactType.HUMAN_OPEN_QUESTIONS,
                    ContractFactType.ENGINEERING_DESIGN_QUESTIONS,
                }
            ),
        ]
        constraints = _current_constraints(facts, scope)
        return QeInvestigationPreparation(
            # GenerationRequest identity contains entry-adapter/benchmark fields.
            # Preparation is intentionally transport-neutral, so the RuntimeTrace
            # remains the owner of the actual request correlation ID.
            request_id=None,
            plan_id=None,
            normalized_jira_facts=facts,
            scope=scope,
            out_of_scope=constraints.explicit_out_of_scope,
            open_decisions=open_decisions,
            domains=domains,
            change_surfaces=surfaces,
            abstract_signals=signals,
            pattern_lookup=pattern_lookup,
            matched_human_patterns=pattern_lookup.matched_human_patterns,
            authoring_guidance=pattern_lookup.authoring_guidance,
            mandatory_families=families,
            already_investigated_dimensions=[],
            constraints=constraints,
            retrieval_hints=[
                InvestigationRetrievalHint(
                    family_id=family.family_id,
                    preferred_evidence_sources=(family.preferred_evidence_sources),
                    reason=(
                        "Retrieve current evidence for this activated or unresolved "
                        "family."
                    ),
                )
                for family in families
                if family.activation_decision
                != FamilyActivationDecision.DO_NOT_ACTIVATE
            ],
        )


__all__ = [
    "CanonicalQeInvestigationService",
    "PATTERN_PROVIDER_ERROR",
    "PATTERN_PROVIDER_INVALID_RESPONSE",
    "PATTERN_PROVIDER_UNAVAILABLE",
    "PatternResolver",
]
