"""P2: problem statement / UX gap -> unstated solution promotion guard.

Invariant: AN ESTABLISHED PROBLEM DOES NOT ESTABLISH A PARTICULAR SOLUTION.

Built on the canonical ClaimSufficiencyRecord (C2B-S1) - no new sufficiency
representation, no second promotion pipeline.  Named scenario shapes appear
only as fixtures; production logic stays generic.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AuthorityClass,
    AuthoritySubject,
    ClarificationAnswerClass,
    ClarificationStatus,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    EvidenceSourceType,
    GenerationProfile,
    HumanClarification,
    MissingQuestion,
    OpenQuestionClass,
    PromotionStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SufficiencyStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    assess_claim_sufficiency,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = REPO_ROOT / "skills" / "test-plan-generation" / "scripts"


def _load_skill(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_skill("cra_p2", "canonical_runtime_adapter.py")
run_gates = _load_skill("run_gates_p2", "run_gates.py")


# ---------------------------------------------------------------------------
# Sanitized media-label fixture (spec section 15)
# ---------------------------------------------------------------------------

_PROBLEM_TEXTS = [
    "There is no easy way to manage version labels on rich assets.",
    "The upload dialog does not have an option to assign a label.",
    "The current label entry is not driven by the managed label source.",
    "This makes release tracking hard to manage.",
]
_CURRENT_BEHAVIOR = (
    "Version labels can be managed through the existing properties workflow."
)
_SOLUTION_REQUIREMENT = (
    "When a new asset version is created, users must select a version label "
    "from the managed labels configured for the applicable folder profile."
)


def _fact(
    text: str,
    *,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    fact_type: ContractFactType | None = None,
    evidence: str = "ev:jira",
) -> ContractFact:
    if fact_type is None:
        fact_type = (
            ContractFactType.PROBLEM_STATEMENT
            if text in _PROBLEM_TEXTS
            else ContractFactType.DIRECT_EXPECTED_BEHAVIOR
        )
    return ContractFact(
        fact_type=fact_type,
        literal=text,
        source_evidence_ids=[evidence],
        source_reference="jira:test:$.description",
        authority_class=authority,
        authoritative=True,
    )


def _fixture_facts(with_solution: bool = False) -> ContractFactSet:
    facts = [_fact(text) for text in _PROBLEM_TEXTS]
    facts.append(_fact(_CURRENT_BEHAVIOR))
    if with_solution:
        facts.append(
            _fact(
                _SOLUTION_REQUIREMENT,
                authority=AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT,
                evidence="ev:accepted",
            )
        )
    return ContractFactSet(
        contract_mode=(
            ContractMode.HUMAN_ACCEPTED_CONTRACT
            if with_solution
            else ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
        ),
        facts=facts,
    )


def _assess(candidate, facts):
    return assess_claim_sufficiency(
        candidate,
        facts_by_id={row.fact_id: row for row in facts.facts},
        dispositions_by_id={},
        research_by_question={},
        classifications_by_disposition={},
        evidence_currentness={},
        admitted_clarifications=[],
    )


def _candidate(statement: str, facts: list[ContractFact]) -> AcceptanceCandidate:
    return AcceptanceCandidate(
        statement=statement,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        accepted_human_contract=False,
        source_fact_ids=[row.fact_id for row in facts],
        source_disposition_ids=[],
        evidence_ids=["ev:jira"],
        in_scope=True,
        observable=True,
        exact_values_supported=True,
        contradicts_human_contract=False,
        unresolved_decision_ids=[],
    )


# ---------------------------------------------------------------------------
# Evidence role classification (spec section 2)
# ---------------------------------------------------------------------------


def test_problem_statements_never_become_acceptance_coverage() -> None:
    facts = _fixture_facts()
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), []
    )
    by_fact = {row.source_fact_ids[0]: row for row in dispositions}
    for fact in facts.facts:
        disposition = by_fact[fact.fact_id].disposition
        if fact.fact_type == ContractFactType.PROBLEM_STATEMENT:
            assert disposition == CoverageDisposition.KNOWN_LIMITATION, (
                fact.literal
            )
        elif fact.literal == _CURRENT_BEHAVIOR:
            assert disposition in {
                CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                CoverageDisposition.ACCEPTANCE_CONTRACT,
            }


def test_problem_claim_may_be_sufficient_but_is_not_acceptance() -> None:
    facts = _fixture_facts()
    problem_fact = next(
        row
        for row in facts.facts
        if row.fact_type == ContractFactType.PROBLEM_STATEMENT
    )
    record = _assess(_candidate(problem_fact.literal, [problem_fact]), facts)
    # The problem itself is fully established by the ticket...
    assert record.status == SufficiencyStatus.SUFFICIENT
    # ...but its coverage disposition keeps it out of acceptance entirely.
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], ScopeResolution(), []
    )
    assert not any(
        row.disposition
        in {
            CoverageDisposition.ACCEPTANCE_CONTRACT,
            CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        }
        for row in dispositions
        if row.source_fact_ids == [problem_fact.fact_id]
    )


def test_unstated_solution_is_insufficient_and_not_promotable() -> None:
    facts = _fixture_facts()
    problem_facts = [
        row
        for row in facts.facts
        if row.fact_type == ContractFactType.PROBLEM_STATEMENT
    ]
    for solution in (
        "Add label selection to the asset upload dialog.",
        "Add label selection to the asset update dialog.",
        "Use a dropdown for label entry.",
        "Drive the new control from the managed label configuration.",
        "Show asset usage information in a dedicated panel.",
        "All rich asset types support the same new workflow.",
    ):
        candidate = _candidate(solution, problem_facts)
        record = _assess(candidate, facts)
        assert record.status == SufficiencyStatus.INSUFFICIENT, solution
        assert "problem" in record.decision_reason

        gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
            [candidate],
            facts,
            ScopeResolution(),
            [],
            sufficiency=[record],
        )
        (decision,) = decisions
        assert decision.status == PromotionStatus.REJECTED, solution
        assert any(
            "PROBLEM_TO_SOLUTION_PROMOTION" in reason
            or "INSUFFICIENT" in reason
            for reason in decision.reasons
        )


def test_gap_reversal_needs_solution_evidence() -> None:
    """Current-absence + unrelated establishing evidence still cannot carry
    a claim whose behavior content nothing establishes (spec section 3)."""

    facts = _fixture_facts()
    problem_facts = [
        row
        for row in facts.facts
        if row.fact_type == ContractFactType.PROBLEM_STATEMENT
    ]
    current = _fact(_CURRENT_BEHAVIOR)
    all_facts = problem_facts + [current]
    candidate = _candidate(
        "The upload dialog provides managed label selection.", all_facts
    )
    record = _assess(candidate, facts)
    assert record.status == SufficiencyStatus.INSUFFICIENT
    assert "does not establish a particular solution" in record.decision_reason


# ---------------------------------------------------------------------------
# Neutral question (spec section 7) + ACCEPTANCE_TBD (section 10)
# ---------------------------------------------------------------------------


def test_neutral_product_decision_question_without_embedded_solution() -> None:
    facts = _fixture_facts()
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], ScopeResolution(), facts
    )
    neutral = [row for row in questions if "addresses this gap" in row.question]
    assert len(neutral) == 1
    question = neutral[0]
    assert question.blocking is True
    assert question.open_question_class == OpenQuestionClass.USER_ACCEPTANCE_DECISION
    # The gap is named; no solution vocabulary beyond the gap text is embedded.
    lowered = question.question.casefold()
    for banned in ("dropdown", "must select", "add a", "add "):
        assert banned not in lowered


def test_established_solution_suppresses_the_neutral_question() -> None:
    facts = _fixture_facts(with_solution=True)
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], ScopeResolution(), facts
    )
    assert not any("addresses this gap" in row.question for row in questions)


# ---------------------------------------------------------------------------
# Positive control (spec section 16)
# ---------------------------------------------------------------------------


def test_positive_control_solution_promotes_with_authority() -> None:
    facts = _fixture_facts(with_solution=True)
    solution_fact = next(
        row for row in facts.facts if row.authority_class ==
        AuthorityClass.ACCEPTED_PRODUCT_REQUIREMENT
    )
    candidate = _candidate(_SOLUTION_REQUIREMENT, [solution_fact])
    candidate.contract_mode = ContractMode.HUMAN_ACCEPTED_CONTRACT
    candidate.accepted_human_contract = True
    record = _assess(candidate, facts)
    assert record.status == SufficiencyStatus.SUFFICIENT

    disposition = CoverageDispositionRecord(
        candidate=candidate.statement,
        disposition=CoverageDisposition.ACCEPTANCE_CONTRACT,
        source_fact_ids=[solution_fact.fact_id],
        rationale="accepted contract",
    )
    candidate.source_disposition_ids = [disposition.disposition_id]
    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate], facts, ScopeResolution(), [disposition],
        sufficiency=[record],
    )
    (decision,) = decisions
    assert decision.status == PromotionStatus.PROMOTED


# ---------------------------------------------------------------------------
# Unfamiliar regressions (spec sections 17-18)
# ---------------------------------------------------------------------------


def test_unfamiliar_a_no_dashboard_column_inference() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.PROBLEM_STATEMENT,
                literal="Users cannot easily identify failed background jobs.",
                source_evidence_ids=["ev:j"],
                source_reference="jira:test:$.description",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], ScopeResolution(), facts
    )
    neutral = [row for row in questions if "addresses this gap" in row.question]
    assert len(neutral) == 1
    assert "column" not in neutral[0].question.casefold()
    assert "dashboard" not in neutral[0].question.casefold()

    invented = _candidate(
        "Add a status column to the background-jobs dashboard.",
        facts.facts,
    )
    record = _assess(invented, facts)
    assert record.status == SufficiencyStatus.INSUFFICIENT


def test_unfamiliar_b_mechanism_remains_unspecified() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.PROBLEM_STATEMENT,
                literal=(
                    "Validation state remains stale until the user manually "
                    "refreshes."
                ),
                source_evidence_ids=["ev:j"],
                source_reference="jira:test:$.description",
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )
    invented = _candidate(
        "Implement push-based auto-refresh for validation state.",
        facts.facts,
    )
    record = _assess(invented, facts)
    assert record.status == SufficiencyStatus.INSUFFICIENT


# ---------------------------------------------------------------------------
# Human clarification resume (spec section 14)
# ---------------------------------------------------------------------------


def test_authorized_clarification_establishes_the_solution() -> None:
    facts = _fixture_facts()
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], ScopeResolution(), facts
    )
    neutral = next(row for row in questions if "addresses this gap" in row.question)

    clarification = HumanClarification(
        question_ref=neutral.question_id,
        question_revision=neutral.question_revision,
        answer=(
            "Users select a version label from the managed labels configured "
            "for the applicable folder profile when a new asset version is "
            "created."
        ),
        answer_classification=ClarificationAnswerClass.PRODUCT_DECISION,
        provided_by="product-owner",
        authority_role=AuthorityClass.CONFIRMED_PRODUCT_DECISION,
    )
    admitted, errors = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [clarification.model_dump(mode="json")], questions
    )
    assert errors == []
    (row,) = admitted
    assert row.status == ClarificationStatus.ADMITTED

    batch = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts,
        [],
        questions,
        resolved_question_ids={neutral.question_id},
        research_records=[],
        clarifications=admitted,
    )
    synthesized = [
        candidate
        for candidate in batch.candidates
        if candidate.evidence_ids == [f"clarification:{row.clarification_id}"]
    ]
    assert len(synthesized) == 1
    candidate = synthesized[0]
    record = next(
        r for r in batch.sufficiency if r.claim_ref == candidate.candidate_id
    )
    assert record.status == SufficiencyStatus.SUFFICIENT
    assert record.authority_basis == "HUMAN_CLARIFICATION"

    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        batch.candidates, facts, ScopeResolution(), [],
        sufficiency=batch.sufficiency, clarifications=admitted,
    )
    decision = next(
        d for d in decisions if d.candidate_id == candidate.candidate_id
    )
    assert decision.status == PromotionStatus.PROMOTED


# ---------------------------------------------------------------------------
# Production entry point + renderer (spec section 21)
# ---------------------------------------------------------------------------


def _runtime_run(description: str, clarifications=None):
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99101",
        tenant_id="tenant_p2",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        options={"human_clarifications": clarifications or []},
    )
    packet = {
        "jira_key": "GUIDES-99101",
        "issue": {
            "issue_key": "GUIDES-99101",
            "summary": "Hard to manage version labels on rich assets",
            "description": description,
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_production_path_cannot_promote_unstated_solution() -> None:
    description = (
        "There is no easy way to manage version labels on rich assets. "
        "The upload dialog does not have an option to assign a label. "
        "The current label entry is not driven by the managed label source. "
        "This makes release tracking hard to manage."
    )
    result = _runtime_run(description)
    payload = result.output_payload

    promoted = [
        row for row in payload["promotion_decisions"] if row["status"] == "PROMOTED"
    ]
    promoted_ids = {row["candidate_id"] for row in promoted}
    candidates = {
        row["candidate_id"]: row for row in payload["acceptance_candidates"]
    }
    for candidate_id in promoted_ids:
        statement = candidates[candidate_id]["statement"].casefold()
        assert "dropdown" not in statement
        assert "upload dialog" not in statement

    questions = payload["missing_questions"]
    assert any(
        "addresses this gap" in (row.get("question_text") or "")
        and row.get("blocking")
        for row in questions
    )
    # The rendered human UAC contains no unpromoted solution claim.
    rendered = result.rendered_output.casefold()
    assert "add label selection" not in rendered
    assert "dropdown" not in rendered

    # C2A/S1 replay of the same canonical artifact agrees.
    manifest, meta = adapter.project_runtime_result(result.model_dump(mode="json"))
    report = run_gates.replay_runtime_projection(manifest)
    assert report["runtime_promotion_status"] == "AGREES"


def test_production_path_resume_establishes_solution() -> None:
    description = (
        "There is no easy way to manage version labels on rich assets. "
        "The upload dialog does not have an option to assign a label."
    )
    first = _runtime_run(description)
    neutral = next(
        row
        for row in first.output_payload["missing_questions"]
        if "addresses this gap" in (row.get("question_text") or "")
    )
    clarification = {
        "question_ref": neutral["question_id"],
        "question_revision": neutral["question_revision"],
        "answer": (
            "Users select a version label from the managed labels configured "
            "for the applicable folder profile when a new asset version is "
            "created."
        ),
        "answer_classification": "PRODUCT_DECISION",
        "provided_by": "product-owner",
        "authority_role": "CONFIRMED_PRODUCT_DECISION",
    }
    second = _runtime_run(description, clarifications=[clarification])
    payload = second.output_payload
    assert payload["promotion_decisions"]
    promoted_statements = {
        row["candidate_id"]: row
        for row in payload["acceptance_candidates"]
        if row["candidate_id"]
        in {
            d["candidate_id"]
            for d in payload["promotion_decisions"]
            if d["status"] == "PROMOTED"
        }
    }
    assert any(
        "managed labels" in row["statement"].casefold()
        for row in promoted_statements.values()
    )
    trace_statuses = {
        row.status.value for row in second.trace.human_clarifications
    }
    assert trace_statuses == {"ADMITTED"}
