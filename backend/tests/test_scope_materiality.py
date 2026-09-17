"""Materiality gate: UNKNOWN VALUE is not a MATERIAL acceptance question.

A configuration/applicability dimension becomes a user-facing acceptance
question only when admitted evidence ties the dimension itself to
conditional or differing behavior.  Same-domain existence, unknown value,
or generic vocabulary is NON_MATERIAL_TO_CURRENT_ACCEPTANCE: no question,
no TBD, no promotion block, no acceptance coverage.

Generic mechanism only; no ticket, feature, or configuration-name
hardcoding in production logic.
"""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    DitaOtProcessingState,
    GenerationProfile,
    RuntimeEntryPoint,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE as S,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME


def _fact(
    text: str,
    fact_type: ContractFactType | None = None,
) -> ContractFact:
    from app.services.canonical_test_plan_reasoning_service import _fact_types

    return ContractFact(
        # Route through the real extractor classification so dimension facts
        # (processing state, preset type) carry their real types.
        fact_type=fact_type or _fact_types("description", text)[0],
        literal=text,
        normalized_value=text.casefold(),
        source_evidence_ids=["ev-1"],
        source_reference="test:description",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        authority_class=AuthorityClass.CUSTOMER_REQUEST,
        authoritative=True,
    )


def _publishing_facts(*literals: str) -> ContractFactSet:
    from app.services.canonical_test_plan_reasoning_service import _fact_types

    facts: list[ContractFact] = []
    for text in literals:
        # Mirror the real extractor: one fact per classified type.
        for fact_type in _fact_types("description", text):
            facts.append(_fact(text, fact_type))
    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=facts,
    )


_PUBLISHING_DOMAINS = None  # resolved via route_domains in each test


def _scope_for(*literals: str, clarifications=None):
    facts = _publishing_facts(*literals)
    domains = S.route_domains(
        _bundle_for(facts),
        facts,
    )
    return S.resolve_scope(facts, domains, clarifications=clarifications)


def _bundle_for(facts: ContractFactSet):
    from app.core.schemas_canonical_test_plan_runtime import (
        CanonicalEvidenceBundle,
        EvidenceRecord,
        EvidenceSourceType,
        SourceVisibility,
    )

    return CanonicalEvidenceBundle(
        tenant_id="tenant_mat",
        records=[
            EvidenceRecord(
                source_type=EvidenceSourceType.JIRA_DESCRIPTION,
                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                source_reference="test:description",
                tenant_id="tenant_mat",
                visibility=SourceVisibility(tenant_id="tenant_mat"),
                content={
                    "description": " ".join(f.literal for f in facts.facts)
                },
            )
        ],
    )


# ---------------------------------------------------------------------------
# Negative control (spec section 9)
# ---------------------------------------------------------------------------


def test_dimension_existing_in_same_domain_is_not_material() -> None:
    # Behavior concerns output status visibility; a processing toggle exists
    # in the same broad domain and its value is unknown, but no admitted
    # evidence ties the toggle to conditional or differing behavior.  The
    # publishing route activates from the behavior vocabulary.
    scope = _scope_for(
        "When publishing the archive, authors must see a clear indication "
        "that completed output carries log entries needing review."
    )
    # Publishing route activates from the behavior vocabulary.
    assert "ENABLE_DITA_OT_PROCESSING" not in scope.unresolved_fields
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE
    assert scope.dimension_materiality.get("ENABLE_DITA_OT_PROCESSING") == (
        "NON_MATERIAL_TO_CURRENT_ACCEPTANCE:NO_MATERIAL_INTERACTION_EVIDENCE"
    )
    # No user-facing question is generated for the suppressed dimension.
    questions = S.generate_missing_questions([], scope, _publishing_facts(
        "When publishing the archive, authors must see a clear indication "
        "that completed output carries log entries needing review."
    ))
    assert not any(
        "ON, OFF, both" in row.question for row in questions
    )


def test_bare_processing_vocabulary_is_not_interaction_evidence() -> None:
    # The word "processing" in a status-indication sentence is same-domain
    # vocabulary, not evidence that the processing mode changes the contract.
    scope = _scope_for(
        "Authors are not shown the processing state and would need to open "
        "the log to notice entries."
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE


# ---------------------------------------------------------------------------
# Positive control (spec section 8)
# ---------------------------------------------------------------------------


def test_conditional_behavior_evidence_makes_dimension_material() -> None:
    # Evidence ties the dimension to differing behavior; the in-scope value
    # stays unresolved -> the question legitimately survives.
    scope = _scope_for(
        "The generated archive must record a completion marker. The result "
        "differs between DITA-OT processing modes."
    )
    assert "ENABLE_DITA_OT_PROCESSING" in scope.unresolved_fields
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED
    assert (
        scope.dimension_materiality.get("ENABLE_DITA_OT_PROCESSING") == "MATERIAL"
    )
    questions = S.generate_missing_questions(
        [],
        scope,
        _publishing_facts(
            "The generated archive must record a completion marker. The "
            "result differs between DITA-OT processing modes."
        ),
    )
    assert any("ON, OFF, both" in row.question for row in questions)


def test_explicit_mode_values_still_resolve_from_evidence() -> None:
    # When evidence states the mode outright, the dimension resolves from
    # evidence (no question, no materiality escalation needed).
    scope = _scope_for(
        "The generated archive must record a completion marker. "
        "Enable DITA-OT processing: on."
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.ON
    assert "ENABLE_DITA_OT_PROCESSING" not in scope.unresolved_fields


# ---------------------------------------------------------------------------
# Clarification resume is preserved through the gate (P1)
# ---------------------------------------------------------------------------


def test_human_clarification_applies_even_without_interaction_evidence() -> None:
    # A human answer is itself the authority: clarification admission happens
    # before materiality suppression so resume keeps working.
    from app.services.canonical_test_plan_reasoning_service import (
        scope_question_revision,
    )

    clarifications = [
        {
            "question_ref": "ENABLE_DITA_OT_PROCESSING",
            "question_revision": scope_question_revision("ENABLE_DITA_OT_PROCESSING"),
            "answer": "not applicable",
            "answer_classification": "SCOPE_VALUE",
            "provided_by": "qe-reviewer",
            "authority_role": "CONFIRMED_PRODUCT_DECISION",
        }
    ]
    scope = _scope_for(
        "When publishing the archive, authors must see a clear indication "
        "that completed output carries log entries needing review.",
        clarifications=clarifications,
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE
    assert scope.dita_ot_resolution_basis == "HUMAN_CLARIFICATION"
    assert scope.applied_clarification_ids


# ---------------------------------------------------------------------------
# Uncertain materiality: research first, never a blocking question (4, 5, 9)
# ---------------------------------------------------------------------------


def test_bare_mention_routes_research_first_never_blocks() -> None:
    # The ticket mentions the dimension by name but never ties it to
    # differing behavior: plausible relationship -> bounded research probe,
    # NOT silent suppression and NOT a blocking human question.
    scope = _scope_for(
        "When publishing the archive, authors must see a clear indication "
        "that completed output carries log entries needing review. The "
        "DITA-OT configuration exists in this area."
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE
    assert "ENABLE_DITA_OT_PROCESSING" not in scope.unresolved_fields
    assert scope.dimension_materiality.get("ENABLE_DITA_OT_PROCESSING") == (
        "UNRESOLVED_MATERIALITY:RESEARCH_FIRST"
    )
    questions = S.generate_missing_questions([], scope, _publishing_facts(
        "When publishing the archive, authors must see a clear indication "
        "that completed output carries log entries needing review. The "
        "DITA-OT configuration exists in this area."
    ))
    # No ON/OFF value question; a non-blocking research-first probe exists.
    assert not any("ON, OFF, both" in row.question for row in questions)
    probes = [
        row
        for row in questions
        if row.open_question_class.value == "RESEARCH_REQUIRED"
        and "change the behavior under acceptance" in row.question
    ]
    assert len(probes) == 1
    assert not probes[0].blocking


def test_production_probe_dispatches_workers_and_never_blocks() -> None:
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99313",
        tenant_id="tenant_mat",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99313",
        "issue": {
            "issue_key": "GUIDES-99313",
            "summary": "Completed archives need a visible attention state.",
            "description": (
                "When the generated page is produced, authors are not shown "
                "that entries need review. The DITA-OT toggle exists in this "
                "area of the product."
            ),
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "Completed generation carrying entries that need review is "
                "shown with a distinct attention state."
            ],
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )
    payload = result.output_payload
    # Dimension considered and gated, never a blocking question, no TBD, and
    # the accepted claim still promotes.
    assert not any(
        "ON, OFF, both" in q["question"] for q in payload["missing_questions"]
    )
    assert not [
        row
        for row in payload["coverage_dispositions"]
        if row["disposition"] == "ACCEPTANCE_TBD"
    ]
    assert any(
        row["status"] == "PROMOTED" for row in payload["promotion_decisions"]
    )
    # The research-first probe actually dispatched workers (R2).
    executions = payload["research_worker_executions"]
    probe_questions = {
        q["question_id"]
        for q in payload["missing_questions"]
        if "change the behavior under acceptance" in q["question"]
    }
    assert probe_questions
    assert any(
        execution["question_id"] in probe_questions for execution in executions
    )


# ---------------------------------------------------------------------------
# Production entry point (spec section 1 trace + regression)
# ---------------------------------------------------------------------------


def test_production_run_never_asks_non_material_dimension() -> None:
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99312",
        tenant_id="tenant_mat",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99312",
        "issue": {
            "issue_key": "GUIDES-99312",
            "summary": "Completed archives need a visible attention state.",
            "description": (
                "When the generated page is produced, authors are not shown "
                "that entries need review and would need to open the log to "
                "notice them."
            ),
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )
    questions = result.output_payload["missing_questions"]
    assert not any("ON, OFF, both" in q["question"] for q in questions)
    scope = result.output_payload["scope"]
    assert scope["dimension_materiality"].get("ENABLE_DITA_OT_PROCESSING") == (
        "NON_MATERIAL_TO_CURRENT_ACCEPTANCE:NO_MATERIAL_INTERACTION_EVIDENCE"
    )
