"""PFIX-04 Claude Missing Question contract and quality regressions."""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    ApplicabilityState,
    AuthoritySubject,
    BehaviorRelationType,
    ChangeSurface,
    ChangeSurfaceKind,
    ClaudeMissingQuestionSubmission,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceSourceType,
    FamilyActivationDecision,
    InvestigationFamilySatisfactionStatus,
    InvestigationFamilySourceContribution,
    InvestigationFamilySourceKind,
    InvestigationMateriality,
    IssueDomain,
    MandatoryInvestigationFamily,
    MissingQuestion,
    MissingQuestionOrigin,
    MissingQuestionQualityFailureReason,
    MissingQuestionResolutionStatus,
    PatternLookupResult,
    PatternLookupRuntimeStatus,
    QeInvestigationConstraints,
    QeInvestigationPreparation,
    QuestionEvidenceProvider,
    RetrievalStatus,
    RuntimeEntryPoint,
    GenerationProfile,
    ScopeResolution,
    SemanticDimension,
)
from app.services.canonical_missing_question_service import (
    CanonicalMissingQuestionService,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime


TENANT = "pfix04-tenant"


def _family(
    family_id: SemanticDimension,
    surface: ChangeSurface,
    *,
    pattern_ids: list[str] | None = None,
) -> MandatoryInvestigationFamily:
    contribution = InvestigationFamilySourceContribution(
        source=(
            InvestigationFamilySourceKind.PATTERN_MCP
            if pattern_ids
            else InvestigationFamilySourceKind.CURRENT_CHANGE_SURFACE
        ),
        source_ids=pattern_ids or [surface.surface_id],
        why_required=f"Investigate {family_id.value} for the current changed state.",
        linked_change_surface_ids=[surface.surface_id],
        linked_pattern_ids=pattern_ids or [],
        materiality=InvestigationMateriality.P1,
        blocking_status=True,
        confidence=0.9,
        preferred_evidence_sources=[EvidenceSourceType.CURRENT_CODE],
    )
    return MandatoryInvestigationFamily(
        family_id=family_id,
        sources=[contribution],
        materiality=InvestigationMateriality.P1,
        activation_decision=FamilyActivationDecision.ACTIVATE_BLOCKING,
        confidence=0.9,
        applicability_reason="The relationship is directly present in the current case.",
    )


def _preparation(
    families: list[SemanticDimension],
    *,
    already_resolved: list[SemanticDimension] | None = None,
    pattern_ids: dict[SemanticDimension, list[str]] | None = None,
    domains: list[IssueDomain] | None = None,
) -> tuple[QeInvestigationPreparation, ChangeSurface]:
    surface = ChangeSurface(
        kind=ChangeSurfaceKind.CHANGED_BEHAVIOR,
        entity="resolved publishing status",
        confidence=0.95,
    )
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                literal=(
                    "Publishing uses the changed resolved publishing status in the "
                    "current workflow."
                ),
                authoritative=True,
            )
        ],
    )
    selected_domains = domains or [IssueDomain.PUBLISHING]
    preparation = QeInvestigationPreparation(
        request_id="req:" + "a" * 64,
        normalized_jira_facts=facts,
        scope=ScopeResolution(),
        domains=[
            DomainActivation(domain=domain, confidence=0.9)
            for domain in selected_domains
        ],
        change_surfaces=[surface],
        abstract_signals=[],
        pattern_lookup=PatternLookupResult(
            status=PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH
        ),
        mandatory_families=[
            _family(
                family_id,
                surface,
                pattern_ids=(pattern_ids or {}).get(family_id),
            )
            for family_id in families
        ],
        already_investigated_dimensions=already_resolved or [],
        constraints=QeInvestigationConstraints(),
    )
    return preparation, surface


def _closure(
    family_id: SemanticDimension,
    *,
    disposition: ClosureDisposition = ClosureDisposition.UNRESOLVED_AND_EXPOSED,
) -> ClosureDimensionResult:
    return ClosureDimensionResult(
        entity="resolved publishing status",
        dimension=family_id,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=disposition,
        evidence_ids=(
            ["evidence:current:resolved"]
            if disposition != ClosureDisposition.UNRESOLVED_AND_EXPOSED
            else []
        ),
        rationale="The current relationship requires investigation.",
    )


def _question(
    preparation: QeInvestigationPreparation,
    surface: ChangeSurface,
    closure: ClosureDimensionResult,
    *,
    text: str,
    family_id: SemanticDimension = SemanticDimension.DIRECT_CONSUMERS,
    relation: BehaviorRelationType = BehaviorRelationType.CONSUMED_BY,
    pattern_ids: list[str] | None = None,
) -> MissingQuestion:
    return MissingQuestion(
        question_text=text,
        family_id=family_id,
        why_it_matters=(
            "A shared consumer could keep the old behavior or create inconsistent output."
        ),
        linked_change_surface=[surface.surface_id],
        linked_behavior_or_state="resolved publishing status",
        relationship_being_tested=relation,
        expected_evidence_type=[EvidenceSourceType.CURRENT_CODE],
        preferred_provider=QuestionEvidenceProvider.GITHUB_MCP,
        materiality=InvestigationMateriality.P1,
        blocking_status=True,
        active_domain=[row.domain for row in preparation.domains],
        active_reasoner="Claude Desktop",
        linked_pattern_ids=pattern_ids or [],
        expected_oracle="Current code identifies every consumer of the resolved publishing status.",
        origin=MissingQuestionOrigin.CLAUDE_DESKTOP,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        source_closure_ids=[closure.closure_id],
    )


def _select(
    preparation: QeInvestigationPreparation,
    closure: list[ClosureDimensionResult],
    questions: list[MissingQuestion],
):
    submission = ClaudeMissingQuestionSubmission(
        preparation_id=preparation.preparation_id,
        request_id=preparation.request_id,
        questions=questions,
    )
    return CanonicalMissingQuestionService().select_questions(
        preparation=preparation,
        closure=closure,
        compatibility_questions=[],
        claude_submission=submission,
    )


def _reasons(report, question: MissingQuestion):
    return set(
        next(
            row.failure_reasons
            for row in report.decisions
            if row.question_id == question.question_id
        )
    )


def test_generic_question_is_rejected_and_cannot_satisfy_family() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text="Does this affect anything else?",
    )

    report = _select(preparation, [closure], [question])

    assert report.accepted_questions == []
    assert MissingQuestionQualityFailureReason.TOO_GENERIC in _reasons(report, question)
    assert report.family_satisfaction[0].status == (
        InvestigationFamilySatisfactionStatus.UNSATISFIED
    )


def test_answer_asserting_question_is_rejected() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text=(
            "Verify that every consumer reads the changed resolved publishing status?"
        ),
    )

    report = _select(preparation, [closure], [question])

    assert MissingQuestionQualityFailureReason.ASSERTS_ANSWER in _reasons(
        report, question
    )


def test_product_decision_assumption_is_rejected() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text=(
            "Which consumer must always read the changed resolved publishing status?"
        ),
    )

    report = _select(preparation, [closure], [question])

    assert MissingQuestionQualityFailureReason.PRODUCT_DECISION_ASSUMED in _reasons(
        report, question
    )


def test_contextual_evidence_seeking_question_is_accepted() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text=(
            "Which current code consumers read the changed resolved publishing "
            "status, and do they use the same processing path?"
        ),
    )

    report = _select(preparation, [closure], [question])

    assert [row.question_id for row in report.accepted_questions] == [
        question.question_id
    ]
    assert report.family_satisfaction[0].status == (
        InvestigationFamilySatisfactionStatus.SATISFIED_BY_VALID_QUESTION
    )


def test_exact_code_surface_anchor_makes_compact_question_contextual() -> None:
    preparation, surface = _preparation([SemanticDimension.GOVERNING_CONFIGURATION])
    closure = _closure(SemanticDimension.GOVERNING_CONFIGURATION)
    question = MissingQuestion(
        question_text=(
            "Which configuration controls src/main/java/SharedResolver.java?"
        ),
        family_id=SemanticDimension.GOVERNING_CONFIGURATION,
        why_it_matters="The changed implementation may have configuration branches.",
        linked_change_surface=[surface.surface_id],
        linked_behavior_or_state="src/main/java/SharedResolver.java",
        relationship_being_tested=BehaviorRelationType.CONFIGURED_BY,
        expected_evidence_type=[EvidenceSourceType.CURRENT_CODE],
        preferred_provider=QuestionEvidenceProvider.GITHUB_MCP,
        materiality=InvestigationMateriality.P1,
        blocking_status=True,
        active_domain=[IssueDomain.PUBLISHING],
        active_reasoner="Claude Desktop",
        expected_oracle=(
            "Current code identifies configuration branches for SharedResolver."
        ),
        origin=MissingQuestionOrigin.CLAUDE_DESKTOP,
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        target_source_types=[EvidenceSourceType.CURRENT_CODE],
        source_closure_ids=[closure.closure_id],
    )

    report = _select(preparation, [closure], [question])

    assert [row.question_id for row in report.accepted_questions] == [
        question.question_id
    ]


def test_claude_question_handoff_rejects_credential_shaped_text() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text=(
            "Which consumer reads the changed resolved publishing status "
            "with token: example?"
        ),
    )

    with pytest.raises(ValueError, match="cannot contain credentials"):
        ClaudeMissingQuestionSubmission(
            preparation_id=preparation.preparation_id,
            request_id=preparation.request_id,
            questions=[question],
        )


def test_distinct_material_families_are_not_deduplicated() -> None:
    preparation, surface = _preparation(
        [
            SemanticDimension.DIRECT_CONSUMERS,
            SemanticDimension.DOWNSTREAM_PROCESSOR,
        ]
    )
    direct = _closure(SemanticDimension.DIRECT_CONSUMERS)
    downstream = _closure(SemanticDimension.DOWNSTREAM_PROCESSOR)
    questions = [
        _question(
            preparation,
            surface,
            direct,
            text=(
                "Which current code consumers read the changed resolved publishing "
                "status?"
            ),
        ),
        _question(
            preparation,
            surface,
            downstream,
            text=(
                "Which downstream processor transforms the changed resolved "
                "publishing status?"
            ),
            family_id=SemanticDimension.DOWNSTREAM_PROCESSOR,
            relation=BehaviorRelationType.PROCESSED_BY,
        ),
    ]

    report = _select(preparation, [direct, downstream], questions)

    assert {row.family_id for row in report.accepted_questions} == {
        SemanticDimension.DIRECT_CONSUMERS,
        SemanticDimension.DOWNSTREAM_PROCESSOR,
    }
    assert report.duplicate_collapse_loss == []


def test_semantic_duplicate_merges_without_lineage_loss() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    first_closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    second_closure = ClosureDimensionResult(
        entity="resolved publishing status",
        dimension=SemanticDimension.DIRECT_CONSUMERS,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=ClosureDisposition.UNRESOLVED_AND_EXPOSED,
        rationale="A second exact closure carries independent lineage.",
    )
    questions = [
        _question(
            preparation,
            surface,
            first_closure,
            text="Which code consumers read the changed resolved publishing status?",
        ),
        _question(
            preparation,
            surface,
            second_closure,
            text="What code consumers use the changed resolved publishing status?",
        ),
    ]

    report = _select(preparation, [first_closure, second_closure], questions)

    assert len(report.accepted_questions) == 1
    assert set(report.accepted_questions[0].source_closure_ids) == {
        first_closure.closure_id,
        second_closure.closure_id,
    }
    assert report.duplicate_collapse_loss == []


def test_authoritative_resolution_prevents_unnecessary_human_question() -> None:
    preparation, surface = _preparation(
        [SemanticDimension.DIRECT_CONSUMERS],
        already_resolved=[SemanticDimension.DIRECT_CONSUMERS],
    )
    closure = _closure(
        SemanticDimension.DIRECT_CONSUMERS,
        disposition=ClosureDisposition.COVERED,
    )
    question = _question(
        preparation,
        surface,
        closure,
        text="Which code consumers read the changed resolved publishing status?",
    )

    report = _select(preparation, [closure], [question])
    resolutions = CanonicalMissingQuestionService().resolve_after_evidence(
        report=report,
        retrievals=[],
        dispositions=[],
        closure=[closure],
    )

    assert report.accepted_questions == []
    assert (
        MissingQuestionQualityFailureReason.QUESTION_ALREADY_ANSWERED_BY_EVIDENCE
        in _reasons(report, question)
    )
    assert report.family_satisfaction[0].status == (
        InvestigationFamilySatisfactionStatus.SATISFIED_BY_EVIDENCE
    )
    assert resolutions[0].status == (
        MissingQuestionResolutionStatus.RESOLVED_BY_EVIDENCE
    )
    assert resolutions[0].evidence_ids == ["evidence:current:resolved"]


def test_pattern_relationship_is_contextualized_for_current_case() -> None:
    pattern_id = "SHARED_VALUE_CONSUMER_PATTERN"
    preparation, surface = _preparation(
        [SemanticDimension.DIRECT_CONSUMERS],
        pattern_ids={SemanticDimension.DIRECT_CONSUMERS: [pattern_id]},
    )
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text=(
            "Which current code consumers read the changed resolved publishing status?"
        ),
        pattern_ids=[pattern_id],
    )

    report = _select(preparation, [closure], [question])

    assert report.accepted_questions[0].linked_pattern_ids == [pattern_id]
    assert "publishing status" in report.accepted_questions[0].question


def test_simple_case_does_not_create_additional_questions() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text="Which code consumers read the changed resolved publishing status?",
    )

    report = _select(preparation, [closure], [question])

    assert len(report.submitted_questions) == 1
    assert len(report.accepted_questions) == 1


def test_cross_domain_case_preserves_multiple_question_families() -> None:
    preparation, surface = _preparation(
        [
            SemanticDimension.DIRECT_CONSUMERS,
            SemanticDimension.DOWNSTREAM_PROCESSOR,
        ],
        domains=[IssueDomain.PUBLISHING, IssueDomain.API],
    )
    direct = _closure(SemanticDimension.DIRECT_CONSUMERS)
    processor = _closure(SemanticDimension.DOWNSTREAM_PROCESSOR)
    questions = [
        _question(
            preparation,
            surface,
            direct,
            text="Which code consumers read the changed resolved publishing status?",
        ),
        _question(
            preparation,
            surface,
            processor,
            text=(
                "Which downstream processor transforms the changed resolved "
                "publishing status?"
            ),
            family_id=SemanticDimension.DOWNSTREAM_PROCESSOR,
            relation=BehaviorRelationType.PROCESSED_BY,
        ),
    ]

    report = _select(preparation, [direct, processor], questions)

    assert len(report.accepted_questions) == 2
    assert all(
        set(row.active_domain) == {IssueDomain.PUBLISHING, IssueDomain.API}
        for row in report.accepted_questions
    )


def test_provider_unavailable_keeps_material_question_unresolved() -> None:
    preparation, surface = _preparation([SemanticDimension.DIRECT_CONSUMERS])
    closure = _closure(SemanticDimension.DIRECT_CONSUMERS)
    question = _question(
        preparation,
        surface,
        closure,
        text="Which code consumers read the changed resolved publishing status?",
    )
    report = _select(preparation, [closure], [question])
    retrieval = DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        status=RetrievalStatus.UNAVAILABLE,
        reason="Provider unavailable.",
    )
    disposition = CoverageDispositionRecord(
        candidate=question.question,
        disposition=CoverageDisposition.OPEN_QUESTION,
        source_closure_ids=[closure.closure_id],
        source_question_ids=[question.question_id],
        rationale="No authoritative implementation evidence was available.",
    )

    resolution = CanonicalMissingQuestionService().resolve_after_evidence(
        report=report,
        retrievals=[retrieval],
        dispositions=[disposition],
        closure=[closure],
    )[0]

    assert resolution.status == MissingQuestionResolutionStatus.UNRESOLVED_HUMAN
    assert resolution.evidence_ids == []


def test_canonical_runtime_accepts_hash_bound_claude_submission() -> None:
    runtime = CanonicalTestPlanRuntime()
    request = runtime.build_request(
        jira_key="PFIX-04-CONTROL",
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "PFIX-04-CONTROL",
        "issue": {
            "issue_key": "PFIX-04-CONTROL",
            "summary": "Publishing status should remain visible after refresh.",
            "description": "Output preset type: Native PDF.",
        },
        "repository_evidence": {
            "repositories": [
                {
                    "id": "starling",
                    "head_sha": "abc123",
                    "matches": [
                        {
                            "path": "StatusReader.java",
                            "consumers": ["StatusPanel"],
                        }
                    ],
                }
            ]
        },
    }
    baseline = runtime.generate_backend_compatibility(
        request=request,
        packet=packet,
    )
    preparation_id = baseline.output_payload["qe_investigation"]["preparation_id"]
    claude_questions: list[MissingQuestion] = []
    for row in baseline.output_payload["missing_question_quality"][
        "accepted_questions"
    ]:
        payload = dict(row)
        payload.pop("question_id", None)
        payload["origin"] = MissingQuestionOrigin.CLAUDE_DESKTOP
        payload["active_reasoner"] = "Claude Desktop"
        claude_questions.append(MissingQuestion.model_validate(payload))
    submission = ClaudeMissingQuestionSubmission(
        preparation_id=preparation_id,
        request_id=request.request_id,
        questions=claude_questions,
    )

    result = runtime.generate_backend_compatibility(
        request=request,
        packet=packet,
        claude_question_submission=submission,
    )

    assert result.output_payload["missing_question_quality"]["question_origin"] == (
        MissingQuestionOrigin.CLAUDE_DESKTOP.value
    )
    assert all(
        row["origin"] == MissingQuestionOrigin.CLAUDE_DESKTOP.value
        for row in result.output_payload["missing_questions"]
    )
    assert len(result.output_payload["missing_questions"]) <= len(
        baseline.output_payload["missing_questions"]
    )
