"""PFIX-03 generic family-applicability and materiality sentinels.

The fixtures use abstract relationships only.  Historical patterns remain
discovery input; current issue facts and change surfaces decide activation.
"""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
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
    InvestigationMateriality,
    IssueDomain,
    MatchedHumanPatternView,
    PatternApplicabilityRecord,
    PatternLookupResult,
    PatternLookupRuntimeStatus,
    PatternSuggestionState,
    RuntimeEntryPoint,
    ScopeResolution,
    SemanticDimension,
)
from app.services.canonical_qe_investigation_service import (
    CanonicalQeInvestigationService,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime


def _request():
    return CanonicalTestPlanRuntime().build_request(
        jira_key="TEST-63003",
        tenant_id="pfix03-tests",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def _facts(*values: tuple[ContractFactType, str]) -> ContractFactSet:
    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=fact_type,
                literal=literal,
                authoritative=True,
            )
            for fact_type, literal in values
        ],
    )


def _surface(kind: ChangeSurfaceKind, *, entity: str = "current behavior"):
    return ChangeSurface(kind=kind, entity=entity, confidence=0.94)


def _matched_pattern(
    family: SemanticDimension,
    *,
    pattern_id: str = "GENERIC_RELATIONSHIP_PATTERN",
    materiality: InvestigationMateriality = InvestigationMateriality.P1,
    blocking: bool = True,
) -> PatternLookupResult:
    view = MatchedHumanPatternView(
        pattern_id=pattern_id,
        pattern_version="fixture-v1",
        abstract_trigger=["abstract current relationship"],
        relationship_to_explore=["shared consumer relationship"],
        support_count=2,
        independent_case_count=2,
        counterexample_summary=["COUNTEREXAMPLES_REVIEWED:1"],
        confidence=0.92,
        applicability=0.9,
        recommended_question_families=[family],
        preferred_evidence_sources=[EvidenceSourceType.CURRENT_CODE],
        materiality=materiality,
        blocking_default=blocking,
    )
    return PatternLookupResult(
        status=PatternLookupRuntimeStatus.AVAILABLE_MATCH,
        matched_human_patterns=[view],
        applicability_records=[
            PatternApplicabilityRecord(
                pattern_id=pattern_id,
                suggestion_state=PatternSuggestionState.PATTERN_SUGGESTED,
                current_applicability=(
                    CurrentPatternApplicability.CURRENTLY_UNRESOLVED
                ),
                reason_codes=["CURRENT_EVIDENCE_VERIFICATION_REQUIRED"],
                recommended_question_families=[family],
                preferred_evidence_sources=[EvidenceSourceType.CURRENT_CODE],
                materiality=materiality,
                blocking_default=blocking,
                confidence=0.92,
                applicability=0.9,
            )
        ],
    )


def _suppressed_pattern(
    family: SemanticDimension,
    *,
    conflict: str,
    pattern_id: str = "GENERIC_RELATIONSHIP_PATTERN",
    materiality: InvestigationMateriality = InvestigationMateriality.P1,
) -> PatternLookupResult:
    return PatternLookupResult(
        status=PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH,
        applicability_records=[
            PatternApplicabilityRecord(
                pattern_id=pattern_id,
                suggestion_state=PatternSuggestionState.PATTERN_SUGGESTED,
                current_applicability=(CurrentPatternApplicability.CURRENTLY_REJECTED),
                reason_codes=["COUNTEREXAMPLE_OR_SCOPE_SUPPRESSION"],
                recommended_question_families=[family],
                counterexample_evidence=[conflict],
                preferred_evidence_sources=[EvidenceSourceType.CURRENT_CODE],
                materiality=materiality,
                blocking_default=True,
                confidence=0.91,
                applicability=0.88,
            )
        ],
    )


def _prepare(
    *,
    facts: ContractFactSet | None = None,
    surfaces: list[ChangeSurface] | None = None,
    domains: list[IssueDomain] | None = None,
    lookup: PatternLookupResult | None = None,
    deterministic_dimensions: set[SemanticDimension] | None = None,
):
    domain_rows = [
        DomainActivation(domain=domain, confidence=0.9)
        for domain in (domains or [IssueDomain.OTHER])
    ]
    return CanonicalQeInvestigationService().prepare_qe_investigation(
        request=_request(),
        facts=facts or _facts(),
        scope=ScopeResolution(),
        domains=domain_rows,
        surfaces=surfaces or [],
        signals=[],
        activations=[],
        deterministic_dimensions=deterministic_dimensions or set(),
        pattern_lookup=lookup
        or PatternLookupResult(status=PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH),
    )


def _family(preparation, family: SemanticDimension):
    return next(
        row for row in preparation.mandatory_families if row.family_id == family
    )


def _active(preparation):
    return [
        row
        for row in preparation.mandatory_families
        if row.activation_decision
        in {
            FamilyActivationDecision.ACTIVATE_BLOCKING,
            FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
        }
    ]


def test_high_material_direct_issue_activates_blocking_families() -> None:
    preparation = _prepare(
        facts=_facts(
            (
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                "Prevent data loss when the current state is saved.",
            )
        ),
        surfaces=[_surface(ChangeSurfaceKind.WRITES)],
    )

    governing = _family(preparation, SemanticDimension.GOVERNING_SEMANTICS)
    persisted = _family(preparation, SemanticDimension.PERSISTED_STATE)
    assert governing.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
    assert persisted.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
    assert governing.materiality == InvestigationMateriality.P0
    assert governing.blocking_status is True


def test_pattern_relevant_and_current_applicability_true_can_block() -> None:
    surface = _surface(ChangeSurfaceKind.CONSUMERS)
    preparation = _prepare(
        surfaces=[surface],
        lookup=_matched_pattern(SemanticDimension.DIRECT_CONSUMERS),
    )

    family = _family(preparation, SemanticDimension.DIRECT_CONSUMERS)
    assert family.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
    assert family.linked_pattern_ids == ["GENERIC_RELATIONSHIP_PATTERN"]
    assert family.linked_change_surface == [surface.surface_id]
    assert family.positive_evidence
    assert family.confidence == 0.94


def test_pattern_match_alone_is_unresolved_and_never_blocking() -> None:
    preparation = _prepare(
        surfaces=[_surface(ChangeSurfaceKind.CHANGED_BEHAVIOR)],
        lookup=_matched_pattern(SemanticDimension.DIRECT_CONSUMERS),
    )

    family = _family(preparation, SemanticDimension.DIRECT_CONSUMERS)
    assert (
        family.activation_decision == FamilyActivationDecision.UNRESOLVED_APPLICABILITY
    )
    assert family.blocking_status is False


def test_current_applicability_false_dispositions_pattern_candidate() -> None:
    preparation = _prepare(
        surfaces=[_surface(ChangeSurfaceKind.CHANGED_BEHAVIOR)],
        lookup=_suppressed_pattern(
            SemanticDimension.DIRECT_CONSUMERS,
            conflict="CURRENT_RELATIONSHIP_EXCLUDED:no shared consumer exists",
        ),
    )

    family = _family(preparation, SemanticDimension.DIRECT_CONSUMERS)
    assert family.activation_decision == FamilyActivationDecision.DO_NOT_ACTIVATE
    assert family.blocking_status is False
    assert any(
        "CURRENT_RELATIONSHIP_EXCLUDED" in value
        for value in family.counterexample_evidence
    )


def test_strong_hard_negative_suppresses_historical_activation() -> None:
    preparation = _prepare(
        lookup=_suppressed_pattern(
            SemanticDimension.ALTERNATE_MECHANISMS,
            conflict="HARD_NEGATIVE:relationship is local and has no alternate path",
        )
    )

    family = _family(preparation, SemanticDimension.ALTERNATE_MECHANISMS)
    assert family.activation_decision == FamilyActivationDecision.DO_NOT_ACTIVATE
    assert family.priority == 1
    assert family.preferred_evidence_sources == [EvidenceSourceType.CURRENT_CODE]


def test_current_explicit_requirement_overrides_historical_negative() -> None:
    preparation = _prepare(
        facts=_facts(
            (
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                "Prevent data loss under the current governing behavior.",
            )
        ),
        lookup=_suppressed_pattern(
            SemanticDimension.GOVERNING_SEMANTICS,
            conflict="COUNTEREXAMPLE:historical variant used another relationship",
            materiality=InvestigationMateriality.P0,
        ),
    )

    family = _family(preparation, SemanticDimension.GOVERNING_SEMANTICS)
    assert family.activation_decision == FamilyActivationDecision.ACTIVATE_BLOCKING
    assert family.counterexample_evidence
    assert "overrides" in family.applicability_reason


def test_simple_ui_issue_remains_small_and_non_blocking() -> None:
    preparation = _prepare(
        facts=_facts(
            (
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                "Show the updated button label.",
            ),
            (
                ContractFactType.EXACT_VALUES,
                "Reproduce with six open tabs; investigation reference is available.",
            ),
        ),
        surfaces=[_surface(ChangeSurfaceKind.CHANGED_BEHAVIOR)],
        deterministic_dimensions={SemanticDimension.GOVERNING_SEMANTICS},
    )

    active = _active(preparation)
    assert [row.family_id for row in active] == [SemanticDimension.GOVERNING_SEMANTICS]
    assert (
        active[0].activation_decision == FamilyActivationDecision.ACTIVATE_NON_BLOCKING
    )
    assert not any(row.blocking_status for row in preparation.mandatory_families)


def test_plain_enabled_disabled_state_does_not_imply_configuration_dependency() -> None:
    preparation = _prepare(
        facts=_facts(
            (
                ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                "Show Ready after a successful save.",
            ),
            (
                ContractFactType.FEATURE_STATE,
                "The result is shown when the feature is enabled.",
            ),
            (
                ContractFactType.FEATURE_STATE,
                "A disabled feature must not show Ready.",
            ),
        ),
        surfaces=[_surface(ChangeSurfaceKind.CHANGED_BEHAVIOR)],
        deterministic_dimensions={SemanticDimension.GOVERNING_SEMANTICS},
    )

    active_ids = {row.family_id for row in _active(preparation)}
    assert SemanticDimension.GOVERNING_SEMANTICS in active_ids
    assert SemanticDimension.GOVERNING_CONFIGURATION not in active_ids


def test_cross_domain_current_surfaces_activate_multiple_relevant_families() -> None:
    preparation = _prepare(
        surfaces=[
            _surface(ChangeSurfaceKind.GENERATED_ARTIFACTS),
            _surface(ChangeSurfaceKind.CONFIG_DEPENDENCIES),
        ],
        domains=[IssueDomain.PUBLISHING, IssueDomain.PERFORMANCE],
    )

    active_ids = {row.family_id for row in _active(preparation)}
    assert {
        SemanticDimension.GENERATED_OUTPUT,
        SemanticDimension.GOVERNING_CONFIGURATION,
    }.issubset(active_ids)


def test_same_feature_name_with_different_surface_does_not_false_activate() -> None:
    changed_only = _prepare(
        surfaces=[
            _surface(
                ChangeSurfaceKind.CHANGED_BEHAVIOR,
                entity="shared display token",
            )
        ]
    )
    consumer_change = _prepare(
        surfaces=[_surface(ChangeSurfaceKind.CONSUMERS, entity="shared display token")]
    )

    assert SemanticDimension.DIRECT_CONSUMERS not in {
        row.family_id for row in changed_only.mandatory_families
    }
    assert (
        _family(consumer_change, SemanticDimension.DIRECT_CONSUMERS).activation_decision
        == FamilyActivationDecision.ACTIVATE_NON_BLOCKING
    )
