"""PFIX-02 deterministic Pattern MCP runtime-integration contracts.

These tests intentionally use only synthetic, Human-QE-approved ACTIVE
patterns.  Historical case text is test data, never an acceptance source.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AbstractSignal,
    AbstractSignalKind,
    ChangeSurface,
    ChangeSurfaceKind,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CurrentPatternApplicability,
    DomainActivation,
    EvidenceSourceType,
    FamilyActivationDecision,
    GenerationProfile,
    InvestigationFamilySourceKind,
    IssueDomain,
    PatternLookupRuntimeStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
)
from app.core.schemas_qe_pattern_mcp import (
    QePatternMatch,
    QePatternMateriality,
    QePatternProductionStatus,
    QePatternProvenance,
    QePatternProviderStatus,
    QePatternRecord,
    QePatternSupportGroup,
    QePatternValidationStatus,
    ResolveQePatternsResponse,
)
from app.services.canonical_qe_investigation_service import (
    PATTERN_PROVIDER_ERROR,
    PATTERN_PROVIDER_INVALID_RESPONSE,
    PATTERN_PROVIDER_UNAVAILABLE,
    CanonicalQeInvestigationService,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.qe_pattern_mcp_service import (
    PatternLibraryUnavailable,
    QePatternResolver,
)
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
)


_HASH = "a" * 64
_TENANT = "pfix02-tests"


class _StaticLibraryProvider:
    provider_name = "PFIX02_TEST_LIBRARY"

    def __init__(self, patterns: list[QePatternRecord]) -> None:
        self._patterns = patterns

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        return self._patterns, "pfix02-test-library-v1", _HASH


class _UnavailableLibraryProvider:
    provider_name = "PFIX02_UNAVAILABLE_LIBRARY"

    def load(self) -> tuple[list[QePatternRecord], str, str]:
        raise PatternLibraryUnavailable("synthetic provider unavailable")


class _RecordingResolver:
    def __init__(self, delegate: Any, events: list[str] | None = None) -> None:
        self.delegate = delegate
        self.events = events if events is not None else []
        self.requests: list[Any] = []

    def resolve(self, request: Any) -> Any:
        self.events.append("pattern_lookup")
        self.requests.append(request)
        return self.delegate.resolve(request)


class _CallableResolver:
    def __init__(self, callback: Callable[[Any], Any]) -> None:
        self.callback = callback

    def resolve(self, request: Any) -> Any:
        return self.callback(request)


def _pattern(
    pattern_id: str,
    *,
    family: str,
    sources: list[str] | None = None,
    materiality: QePatternMateriality = QePatternMateriality.P1,
    blocking: bool = True,
    counterexamples: list[str] | None = None,
    hard_negatives: list[str] | None = None,
) -> QePatternRecord:
    """Build an ACTIVE pattern with deliberately sensitive raw provenance."""

    case_id = f"SECRET-CASE-{pattern_id}"
    return QePatternRecord(
        pattern_id=pattern_id,
        pattern_version="fixture-v1",
        validation_status=QePatternValidationStatus.APPROVED,
        production_status=QePatternProductionStatus.ACTIVE,
        abstract_change_surface=[ChangeSurfaceKind.CHANGED_BEHAVIOR.value],
        applicable_domains=[IssueDomain.PUBLISHING.value],
        abstract_signals=[AbstractSignalKind.CHANGED_BEHAVIOR.value],
        question_families=[family],
        relationship_to_explore=["governing semantic relationship"],
        preferred_evidence_sources=sources
        or [
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION.value,
            EvidenceSourceType.CURRENT_CODE.value,
        ],
        materiality=materiality,
        blocking_default=blocking,
        human_support_count=1,
        independent_case_count=1,
        supporting_case_ids=[case_id],
        qualifying_human_support_case_ids=[case_id],
        independent_support_groups=[
            QePatternSupportGroup(group_id="independent-human-case", case_ids=[case_id])
        ],
        counterexamples=counterexamples or [],
        hard_negatives=hard_negatives or [],
        confidence=0.91,
        customer_specific=False,
        jira_specific=False,
        provenance=QePatternProvenance(
            source_kind="TEST_FIXTURE",
            source_locator="private/reviewer/pattern-source.json",
            source_sha256=_HASH,
            source_schema_version="private-human-review-v1",
            derivation_partition="TEST_ONLY",
            human_backed=True,
            raw_human_uac_included=False,
            candidate_source_case_ids=[case_id],
            approval_overlay_sha256=_HASH,
            approval_authority="HUMAN_QE",
            validated_by="Secret Human Reviewer",
            validated_at="2026-09-01T00:00:00Z",
        ),
    )


def _resolver(patterns: list[QePatternRecord]) -> QePatternResolver:
    return QePatternResolver(_StaticLibraryProvider(patterns))


def _packet(*, out_of_scope: str = "HTML5") -> dict[str, object]:
    return {
        "jira_key": "GUIDES-62002",
        "issue": {
            "issue_key": "GUIDES-62002",
            "summary": "Publishing should retain the exact Ready status.",
            "description": (
                "In scope: Native PDF. "
                f"Out of scope: {out_of_scope}. "
                "Enable DITA-OT Processing: ON. "
                "Output preset type: Native PDF. "
                "The existing behavior must remain compatible after upgrade."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
        "repository_evidence": {
            "repositories": [
                {
                    "id": "starling",
                    "head_sha": "abc123",
                    "matches": [
                        {
                            "path": "src/publish/StatusWriter.java",
                            "consumers": ["ActivationStatusResolver"],
                        }
                    ],
                }
            ]
        },
    }


def _run(
    resolver: Any,
    *,
    packet: dict[str, object] | None = None,
):
    runtime = CanonicalTestPlanRuntime(pattern_resolver=resolver)
    request = runtime.build_request(
        jira_key="GUIDES-62002",
        tenant_id=_TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return runtime.generate_backend_compatibility(
        request=request,
        packet=packet or _packet(),
    )


def _lookup_context(
    *,
    out_of_scope: list[str] | None = None,
    include_direct_fact: bool = False,
) -> dict[str, Any]:
    surface = ChangeSurface(
        kind=ChangeSurfaceKind.CHANGED_BEHAVIOR,
        entity="current behavior",
        confidence=0.9,
    )
    signal = AbstractSignal(
        kind=AbstractSignalKind.CHANGED_BEHAVIOR,
        subject="current behavior",
        source_surface_ids=[surface.surface_id],
        confidence=0.9,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=(
            [
                ContractFact(
                    fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                    literal="Retain the current publishing status.",
                    authoritative=True,
                )
            ]
            if include_direct_fact
            else []
        ),
    )
    return {
        "facts": facts,
        "scope": ScopeResolution(out_of_scope=out_of_scope or []),
        "domains": [DomainActivation(domain=IssueDomain.PUBLISHING, confidence=0.9)],
        "surfaces": [surface],
        "signals": [signal],
    }


def _response_for(pattern: QePatternRecord) -> ResolveQePatternsResponse:
    return ResolveQePatternsResponse(
        provider_status=QePatternProviderStatus.SUCCESS,
        pattern_library_version="pfix02-test-library-v1",
        pattern_library_sha256=_HASH,
        pattern_count=1,
        validated_production_pattern_count=1,
        matched_patterns=[
            QePatternMatch(
                pattern=pattern,
                match_reason=["synthetic exact match"],
                applicability_score=0.9,
                recommended_families=pattern.question_families,
                blocking_recommendations=(
                    pattern.question_families if pattern.blocking_default else []
                ),
                influence_allowed=True,
            )
        ],
    )


def test_pattern_lookup_and_payload_precede_missing_question_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    recording = _RecordingResolver(
        _resolver(
            [
                _pattern(
                    "ALTERNATE_PATH_PATTERN",
                    family=SemanticDimension.ALTERNATE_MECHANISMS.value,
                )
            ]
        ),
        events,
    )
    runtime = CanonicalTestPlanRuntime(pattern_resolver=recording)
    original = runtime._reasoning.generate_missing_questions
    seen_preparation: list[Any] = []

    def capture_questions(*args: Any, **kwargs: Any):
        events.append("missing_questions")
        preparation = args[3] if len(args) > 3 else kwargs["investigation"]
        seen_preparation.append(preparation)
        return original(*args, **kwargs)

    monkeypatch.setattr(
        runtime._reasoning,
        "generate_missing_questions",
        capture_questions,
    )
    request = runtime.build_request(
        jira_key="GUIDES-62002",
        tenant_id=_TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    result = runtime.generate_backend_compatibility(request=request, packet=_packet())

    assert events.index("pattern_lookup") < events.index("missing_questions")
    assert seen_preparation
    assert [row.pattern_id for row in seen_preparation[0].matched_human_patterns] == [
        "ALTERNATE_PATH_PATTERN"
    ]
    assert result.trace.qe_investigation == seen_preparation[0]
    assert result.output_payload["qe_investigation"]["matched_human_patterns"]


def test_runtime_exposes_only_bounded_pattern_view_without_raw_human_provenance() -> None:
    result = _run(
        _resolver(
            [
                _pattern(
                    "SAFE_VIEW_PATTERN",
                    family=SemanticDimension.ALTERNATE_MECHANISMS.value,
                )
            ]
        )
    )
    view = result.output_payload["qe_investigation"]["matched_human_patterns"][0]
    serialized = json.dumps(view, sort_keys=True)

    assert view["pattern_id"] == "SAFE_VIEW_PATTERN"
    assert {
        "supporting_case_ids",
        "qualifying_human_support_case_ids",
        "provenance",
        "source_locator",
        "validated_by",
        "validated_at",
    }.isdisjoint(view)
    assert "SECRET-CASE" not in serialized
    assert "Secret Human Reviewer" not in serialized
    assert "private/reviewer" not in serialized


def test_two_patterns_for_one_family_merge_without_provenance_loss() -> None:
    context = _lookup_context()
    service = CanonicalQeInvestigationService(
        _resolver(
            [
                _pattern(
                    "DIRECT_CONSUMER_ALPHA",
                    family=SemanticDimension.DIRECT_CONSUMERS.value,
                ),
                _pattern(
                    "DIRECT_CONSUMER_BETA",
                    family=SemanticDimension.DIRECT_CONSUMERS.value,
                    sources=[EvidenceSourceType.CURRENT_PR.value],
                ),
            ]
        )
    )
    lookup = service.lookup_patterns(**context)
    request = CanonicalTestPlanRuntime().build_request(
        jira_key="GUIDES-62002",
        tenant_id=_TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    preparation = service.prepare_qe_investigation(
        request=request,
        activations=[],
        deterministic_dimensions=set(),
        pattern_lookup=lookup,
        **context,
    )

    assert lookup.status == PatternLookupRuntimeStatus.AVAILABLE_MATCH
    family = preparation.mandatory_families[0]
    assert family.family_id == SemanticDimension.DIRECT_CONSUMERS
    assert family.linked_pattern_ids == [
        "DIRECT_CONSUMER_ALPHA",
        "DIRECT_CONSUMER_BETA",
    ]
    assert [row.source for row in family.sources] == [
        InvestigationFamilySourceKind.PATTERN_MCP,
        InvestigationFamilySourceKind.PATTERN_MCP,
    ]
    assert set(family.preferred_evidence_sources) == {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    }


def test_pattern_source_merges_with_stronger_current_runtime_sources() -> None:
    context = _lookup_context(include_direct_fact=True)
    service = CanonicalQeInvestigationService(
        _resolver(
            [
                _pattern(
                    "GOVERNING_SEMANTIC_PATTERN",
                    family=SemanticDimension.GOVERNING_SEMANTICS.value,
                    materiality=QePatternMateriality.P0,
                    blocking=True,
                )
            ]
        )
    )
    lookup = service.lookup_patterns(**context)
    activations = CANONICAL_REASONING_SERVICE.route_reasoning_patterns(
        context["signals"]
    )
    request = CanonicalTestPlanRuntime().build_request(
        jira_key="GUIDES-62002",
        tenant_id=_TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    preparation = service.prepare_qe_investigation(
        request=request,
        activations=activations,
        deterministic_dimensions={SemanticDimension.GOVERNING_SEMANTICS},
        pattern_lookup=lookup,
        **context,
    )
    family = next(
        row
        for row in preparation.mandatory_families
        if row.family_id == SemanticDimension.GOVERNING_SEMANTICS
    )

    assert {row.source for row in family.sources} == {
        InvestigationFamilySourceKind.CURRENT_JIRA_EXPLICIT,
        InvestigationFamilySourceKind.DETERMINISTIC_REASONING_PATTERN,
        InvestigationFamilySourceKind.DOMAIN_INVARIANT,
        InvestigationFamilySourceKind.PATTERN_MCP,
    }
    assert family.materiality.value == "P0"
    assert family.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
    assert family.blocking_status is True
    pattern_view = lookup.matched_human_patterns[0]
    assert pattern_view.blocking_default is True
    assert (
        pattern_view.current_applicability
        == CurrentPatternApplicability.CURRENTLY_UNRESOLVED
    )


@pytest.mark.parametrize(
    ("pattern_kwargs", "out_of_scope"),
    [
        ({"counterexamples": ["CHANGED_BEHAVIOR"]}, []),
        ({}, ["CHANGED_BEHAVIOR"]),
    ],
    ids=["counterexample", "current-oos"],
)
def test_counterexample_or_current_oos_suppresses_pattern_influence(
    pattern_kwargs: dict[str, Any],
    out_of_scope: list[str],
) -> None:
    context = _lookup_context(out_of_scope=out_of_scope)
    pattern = _pattern(
        "SUPPRESSED_PATTERN",
        family=SemanticDimension.ALTERNATE_MECHANISMS.value,
        **pattern_kwargs,
    )
    lookup = CanonicalQeInvestigationService(_resolver([pattern])).lookup_patterns(
        **context
    )

    assert lookup.status == PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH
    assert lookup.matched_human_patterns == []
    applicability = lookup.applicability_records[0]
    assert (
        applicability.current_applicability
        == CurrentPatternApplicability.CURRENTLY_REJECTED
    )
    assert "COUNTEREXAMPLE_OR_SCOPE_CONFLICT" in applicability.reason_codes


def test_empty_pattern_library_is_not_reported_as_provider_failure() -> None:
    lookup = CanonicalQeInvestigationService(_resolver([])).lookup_patterns(
        **_lookup_context()
    )

    assert lookup.status == PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH
    assert lookup.warning_codes == []
    assert lookup.matched_human_patterns == []


def test_pattern_request_bounds_current_jira_constraint_text() -> None:
    context = _lookup_context()
    context["facts"] = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                literal=f"decision-{index}-" + ("x" * 500),
                authoritative=True,
            )
            for index in range(12)
        ],
    )
    recording = _RecordingResolver(_resolver([]))

    CanonicalQeInvestigationService(recording).lookup_patterns(**context)

    assert recording.requests
    decisions = recording.requests[0].scope_constraints.current_product_decisions
    assert len(decisions) <= 5
    assert all(len(value) <= 200 for value in decisions)


def test_unavailable_pattern_provider_continues_with_exact_warning() -> None:
    resolver = QePatternResolver(_UnavailableLibraryProvider())
    lookup = CanonicalQeInvestigationService(resolver).lookup_patterns(
        **_lookup_context()
    )

    assert lookup.status == PatternLookupRuntimeStatus.PROVIDER_UNAVAILABLE
    assert lookup.warning_codes == [PATTERN_PROVIDER_UNAVAILABLE]
    assert lookup.matched_human_patterns == []

    result = _run(resolver)
    assert result.status in {"completed", "needs_human_review"}
    assert PATTERN_PROVIDER_UNAVAILABLE in result.runtime_warnings


@pytest.mark.parametrize(
    ("callback", "expected_status", "expected_warning"),
    [
        (
            lambda _request: {"provider_status": "SUCCESS"},
            PatternLookupRuntimeStatus.INVALID_RESPONSE,
            PATTERN_PROVIDER_INVALID_RESPONSE,
        ),
        (
            lambda _request: (_ for _ in ()).throw(RuntimeError("synthetic")),
            PatternLookupRuntimeStatus.PROVIDER_ERROR,
            PATTERN_PROVIDER_ERROR,
        ),
    ],
    ids=["invalid-response", "provider-exception"],
)
def test_invalid_or_failed_provider_fails_pattern_influence_closed(
    callback: Callable[[Any], Any],
    expected_status: PatternLookupRuntimeStatus,
    expected_warning: str,
) -> None:
    lookup = CanonicalQeInvestigationService(
        _CallableResolver(callback)
    ).lookup_patterns(**_lookup_context())

    assert lookup.status == expected_status
    assert lookup.warning_codes == [expected_warning]
    assert lookup.matched_human_patterns == []


@pytest.mark.parametrize(
    "pattern",
    [
        _pattern("UNKNOWN_FAMILY_PATTERN", family="NOT_A_CANONICAL_DIMENSION"),
        _pattern(
            "UNKNOWN_SOURCE_PATTERN",
            family=SemanticDimension.GOVERNING_SEMANTICS.value,
            sources=["NOT_A_CANONICAL_EVIDENCE_SOURCE"],
        ),
    ],
    ids=["unknown-family", "unknown-evidence-source"],
)
def test_unknown_family_or_evidence_source_invalidates_entire_pattern_response(
    pattern: QePatternRecord,
) -> None:
    lookup = CanonicalQeInvestigationService(
        _CallableResolver(lambda _request: _response_for(pattern))
    ).lookup_patterns(**_lookup_context())

    assert lookup.status == PatternLookupRuntimeStatus.INVALID_RESPONSE
    assert lookup.warning_codes == [PATTERN_PROVIDER_INVALID_RESPONSE]
    assert lookup.matched_human_patterns == []


def test_normalized_view_validation_failure_cannot_block_runtime() -> None:
    pattern = _pattern(
        "GENERIC_OVERSIZED_PATTERN",
        family=SemanticDimension.GOVERNING_SEMANTICS.value,
    ).model_copy(
        update={
            "abstract_change_surface": [f"surface-{index}" for index in range(50)],
            "abstract_signals": [f"signal-{index}" for index in range(100)],
        }
    )
    service = CanonicalQeInvestigationService(
        _CallableResolver(lambda _request: _response_for(pattern))
    )

    result = service.lookup_patterns(**_lookup_context())

    assert result.status == PatternLookupRuntimeStatus.INVALID_RESPONSE
    assert result.warning_codes == [PATTERN_PROVIDER_INVALID_RESPONSE]
    assert result.matched_human_patterns == []


def test_mutated_response_instance_is_revalidated_before_pattern_influence() -> None:
    response = _response_for(
        _pattern(
            "MUTATED_AUTHORITY_PATTERN",
            family=SemanticDimension.GOVERNING_SEMANTICS.value,
        )
    )
    response.matched_patterns[0].pattern.provenance.approval_authority = "NONE"
    service = CanonicalQeInvestigationService(
        _CallableResolver(lambda _request: response)
    )

    result = service.lookup_patterns(**_lookup_context())

    assert result.status == PatternLookupRuntimeStatus.INVALID_RESPONSE
    assert result.warning_codes == [PATTERN_PROVIDER_INVALID_RESPONSE]
    assert result.matched_human_patterns == []


def test_credential_shaped_pattern_text_is_not_exposed() -> None:
    pattern = _pattern(
        "CREDENTIAL_TEXT_PATTERN",
        family=SemanticDimension.GOVERNING_SEMANTICS.value,
    ).model_copy(update={"relationship_to_explore": ["api_key=do-not-expose"]})
    service = CanonicalQeInvestigationService(
        _CallableResolver(lambda _request: _response_for(pattern))
    )

    result = service.lookup_patterns(**_lookup_context())

    assert result.status == PatternLookupRuntimeStatus.INVALID_RESPONSE
    assert result.warning_codes == [PATTERN_PROVIDER_INVALID_RESPONSE]
    assert result.matched_human_patterns == []


def test_pattern_suggestion_cannot_directly_create_acceptance_criteria() -> None:
    baseline = _run(_resolver([]))
    patterned = _run(
        _resolver(
            [
                _pattern(
                    "DISCOVERY_ONLY_PATTERN",
                    family=SemanticDimension.ALTERNATE_MECHANISMS.value,
                )
            ]
        )
    )

    def contract_projection(result: Any) -> set[tuple[str, tuple[str, ...], tuple[str, ...]]]:
        return {
            (
                row["statement"],
                tuple(row["source_fact_ids"]),
                tuple(row["evidence_ids"]),
            )
            for row in result.output_payload["acceptance_candidates"]
        }

    # The historical default remains visible in Pattern trace, but a merely
    # suggested/currently-unresolved pattern cannot block or create acceptance
    # authority.  Existing current-contract promotions remain unchanged.
    assert contract_projection(patterned) == contract_projection(baseline)
    serialized_candidates = json.dumps(
        patterned.output_payload["acceptance_candidates"], sort_keys=True
    )
    assert "DISCOVERY_ONLY_PATTERN" not in serialized_candidates
    assert "governing semantic relationship" not in serialized_candidates
    pattern_questions = [
        row
        for row in patterned.output_payload["missing_questions"]
        if row.get("dimension") == SemanticDimension.ALTERNATE_MECHANISMS.value
    ]
    assert pattern_questions
    assert all(question["blocking"] is False for question in pattern_questions)
    related_dispositions = [
        row
        for row in patterned.output_payload["coverage_dispositions"]
        if set(row.get("source_question_ids", []))
        & {question["question_id"] for question in pattern_questions}
    ]
    assert related_dispositions
    assert all(
        row["disposition"] != "ACCEPTANCE_CONTRACT" for row in related_dispositions
    )
    assert (
        patterned.output_payload["promotion_decisions"]
        == baseline.output_payload["promotion_decisions"]
    )


def test_controlled_second_pass_reuses_the_same_pattern_dependency() -> None:
    recording = _RecordingResolver(
        _resolver(
            [
                _pattern(
                    "PAIRED_RUNTIME_PATTERN",
                    family=SemanticDimension.ALTERNATE_MECHANISMS.value,
                )
            ]
        )
    )
    runtime = CanonicalTestPlanRuntime(
        pattern_resolver=recording,
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
            ),
            providers=[],
        ),
    )
    request = runtime.build_request(
        jira_key="GUIDES-62002",
        tenant_id=_TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    bundle = runtime.normalize_packet(_packet(), request=request)
    selected, _decision = runtime.run_controlled_second_pass(request, bundle)

    # The paired DISABLED and SECOND_PASS executions must share the exact
    # resolver dependency and receive equivalent deterministic lookups.
    assert recording.requests
    assert len(recording.requests) % 2 == 0
    midpoint = len(recording.requests) // 2
    assert recording.requests[:midpoint] == recording.requests[midpoint:]
    assert selected.trace.qe_investigation is not None
    assert selected.trace.qe_investigation.pattern_lookup.status == (
        PatternLookupRuntimeStatus.AVAILABLE_MATCH
    )
    assert [
        row.pattern_id
        for row in selected.trace.qe_investigation.matched_human_patterns
    ] == ["PAIRED_RUNTIME_PATTERN"]
