"""P1: production runtime parity - material-question suppression, human
clarification resume, and promotion safety.

Driven by a real runtime failure on a repository-retention enhancement ticket:
a mechanical scope question reached ASK_USER without a materiality check, the
human answer had no intake channel (re-runs re-derived the same block), and
draft text carried cross-product / retained-object / backward-compat claims the
promotion contracts never admitted.  Named ticket/feature details appear only
as fixture shapes; production logic stays generic.
"""

from __future__ import annotations

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
    DitaOtProcessingState,
    DomainActivation,
    EvidenceSourceType,
    GateStatus,
    HumanClarification,
    IssueDomain,
    MissingQuestion,
    OpenQuestionClass,
    PromotionStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    scope_question_id,
    scope_question_revision,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fact(
    text: str,
    fact_type: ContractFactType = ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
    *,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    authoritative: bool = True,
) -> ContractFact:
    return ContractFact(
        fact_type=fact_type,
        literal=text,
        source_evidence_ids=["ev:src"],
        source_reference="jira:test:$.description",
        authority_class=authority,
        authoritative=authoritative,
    )


def _retention_facts() -> ContractFactSet:
    """Sanitized shape of the observed run: repository housekeeping/retention,
    no output generation or transformation involvement."""

    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact(
                "The housekeeping job removes history entries older than the "
                "configured number of days."
            ),
            _fact(
                "Provide an option to keep only the most recent entries per "
                "preset."
            ),
            _fact(
                "Provide an option to remove only the log file and keep the "
                "history entry for audit purposes."
            ),
        ],
    )


def _transformation_facts() -> ContractFactSet:
    """A ticket whose evidence DOES involve output generation - the adjacent
    processing toggle stays material and must still be asked."""

    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact("The generated output must include the merged appendix."),
            _fact("Output generation must preserve the existing page order."),
        ],
    )


_PUBLISHING = [DomainActivation(domain=IssueDomain.PUBLISHING, confidence=0.9)]


def _clarification(
    *,
    field: str = "ENABLE_DITA_OT_PROCESSING",
    answer: str = "not applicable",
    revision: str | None = None,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    classification: ClarificationAnswerClass = (
        ClarificationAnswerClass.APPLICABILITY_NOT_APPLICABLE
    ),
    question_ref: str | None = None,
    provided_by: str = "product-owner",
) -> dict[str, object]:
    return {
        "question_ref": question_ref if question_ref is not None else field,
        "question_revision": (
            scope_question_revision(field) if revision is None else revision
        ),
        "answer": answer,
        "answer_classification": classification.value,
        "provided_by": provided_by,
        "authority_role": authority.value,
        "decision_reason": "The toggle does not interact with this feature.",
    }


# ---------------------------------------------------------------------------
# Material-question suppression (spec section 3)
# ---------------------------------------------------------------------------


def test_irrelevant_adjacent_dimension_is_suppressed_with_basis() -> None:
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        _retention_facts(), _PUBLISHING
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE
    assert scope.dita_ot_resolution_basis == "NO_MATERIAL_INTERACTION_EVIDENCE"
    assert "ENABLE_DITA_OT_PROCESSING" not in scope.unresolved_fields

    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, _retention_facts()
    )
    assert not any("DITA-OT" in row.question for row in questions)


def test_material_interaction_evidence_keeps_the_question() -> None:
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        _transformation_facts(), _PUBLISHING
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED
    assert "ENABLE_DITA_OT_PROCESSING" in scope.unresolved_fields

    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, _transformation_facts()
    )
    dita_questions = [row for row in questions if "DITA-OT" in row.question]
    assert len(dita_questions) == 1
    assert dita_questions[0].blocking is True
    assert (
        dita_questions[0].open_question_class
        == OpenQuestionClass.USER_ACCEPTANCE_DECISION
    )
    assert dita_questions[0].question_revision


def test_explicit_processing_state_evidence_still_wins() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact("The generated output must include the merged appendix."),
            _fact(
                "Enable DITA-OT Processing: ON",
                ContractFactType.DITA_OT_PROCESSING_STATE,
            ),
        ],
    )
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(facts, _PUBLISHING)
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.ON
    assert scope.dita_ot_resolution_basis == "EVIDENCE"


# ---------------------------------------------------------------------------
# Clarification lifecycle (spec sections 4-7, 14)
# ---------------------------------------------------------------------------


def test_admitted_clarification_resolves_scope_and_resumes() -> None:
    facts = _transformation_facts()
    blocked = CANONICAL_REASONING_SERVICE.resolve_scope(facts, _PUBLISHING)
    assert blocked.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED

    resumed = CANONICAL_REASONING_SERVICE.resolve_scope(
        facts, _PUBLISHING, clarifications=[_clarification()]
    )
    assert resumed.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE
    assert resumed.dita_ot_resolution_basis == "HUMAN_CLARIFICATION"
    assert resumed.applied_clarification_ids
    assert "ENABLE_DITA_OT_PROCESSING" not in resumed.unresolved_fields

    # The clarification is recorded and admitted against the deterministic
    # question identity, and a resume run does not ask the question again.
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], resumed, facts
    )
    assert not any("DITA-OT" in row.question for row in questions)
    admitted, errors = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [_clarification()], questions
    )
    assert errors == []
    (row,) = admitted
    assert row.status == ClarificationStatus.ADMITTED
    assert "scope resolution" in row.admission_detail


def test_stale_clarification_is_never_rebound() -> None:
    facts = _transformation_facts()
    stale = _clarification(revision="outdated-revision")
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        facts, _PUBLISHING, clarifications=[stale]
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED
    assert scope.applied_clarification_ids == []

    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, facts
    )
    admitted, _ = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [stale], questions
    )
    (row,) = admitted
    assert row.status == ClarificationStatus.STALE


def test_insufficient_authority_clarification_is_rejected() -> None:
    facts = _transformation_facts()
    weak = _clarification(authority=AuthorityClass.TECHNICALLY_INFERRED)
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        facts, _PUBLISHING, clarifications=[weak]
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED

    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, facts
    )
    admitted, _ = CANONICAL_REASONING_SERVICE.admit_clarifications([weak], questions)
    (row,) = admitted
    assert row.status == ClarificationStatus.REJECTED
    assert "cannot establish" in row.admission_detail


def test_contradictory_clarifications_are_rejected() -> None:
    facts = _transformation_facts()
    first = _clarification(answer="not applicable", provided_by="reviewer-a")
    second = _clarification(
        answer="on",
        provided_by="reviewer-b",
        classification=ClarificationAnswerClass.SCOPE_VALUE,
    )
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        facts, _PUBLISHING, clarifications=[first, second]
    )
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.UNRESOLVED

    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, facts
    )
    admitted, _ = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [first, second], questions
    )
    assert {row.status for row in admitted} == {ClarificationStatus.REJECTED}
    assert all("contradictory" in row.admission_detail for row in admitted)


def test_clarification_bound_to_a_wrong_question_is_rejected() -> None:
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [],
        CANONICAL_REASONING_SERVICE.resolve_scope(
            _transformation_facts(), _PUBLISHING
        ),
        _transformation_facts(),
    )
    wrong = _clarification(question_ref="question:" + "0" * 32)
    admitted, _ = CANONICAL_REASONING_SERVICE.admit_clarifications([wrong], questions)
    (row,) = admitted
    assert row.status == ClarificationStatus.REJECTED
    assert "does not exist" in row.admission_detail


def test_answering_one_question_does_not_unblock_another() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact("The generated output must include the merged appendix."),
            _fact(
                'What does the human term "cleanup" mean?',
                ContractFactType.TERMINOLOGY_CLARIFICATION_REQUIRED,
            ),
        ],
    )
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(
        facts, _PUBLISHING, clarifications=[_clarification()]
    )
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [], scope, facts
    )
    blocking = {row.question_id for row in questions if row.blocking}
    # The clarified DITA-OT question is gone; the independent preset-type and
    # terminology questions keep blocking.
    assert len(blocking) == 2
    assert not any("DITA-OT" in row.question for row in questions if row.blocking)

    admitted, _ = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [_clarification()], questions
    )
    # The scope-consumed clarification stays auditable as ADMITTED; its alias
    # ref matches no live question id, so nothing else is released.
    (row,) = admitted
    assert row.status == ClarificationStatus.ADMITTED
    assert "scope resolution" in row.admission_detail

    resolved_ids = {
        row.question_ref
        for row in admitted
        if row.status == ClarificationStatus.ADMITTED
    }
    batch = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts,
        [
            CoverageDispositionRecord(
                candidate="The merged appendix appears in the generated output.",
                disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
                source_fact_ids=[facts.facts[0].fact_id],
                rationale="from ticket",
            )
        ],
        questions,
        resolved_question_ids=resolved_ids,
    )
    candidate = batch.candidates[0]
    assert candidate.unresolved_decision_ids == sorted(blocking)


# ---------------------------------------------------------------------------
# Promotion safety parity (spec sections 8-11)
# ---------------------------------------------------------------------------


def _candidate(
    statement: str,
    facts: list[ContractFact],
    dispositions: list[CoverageDispositionRecord],
) -> AcceptanceCandidate:
    return AcceptanceCandidate(
        statement=statement,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        accepted_human_contract=False,
        source_fact_ids=[row.fact_id for row in facts],
        source_disposition_ids=[row.disposition_id for row in dispositions],
        evidence_ids=["ev:src"],
        in_scope=True,
        observable=True,
        exact_values_supported=True,
        contradicts_human_contract=False,
        unresolved_decision_ids=[],
    )


def _promote(
    candidate: AcceptanceCandidate, facts: list[ContractFact]
) -> tuple[GateStatus, list[str]]:
    dispositions = [
        CoverageDispositionRecord(
            candidate=candidate.statement,
            disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
            source_fact_ids=[row.fact_id for row in facts],
            rationale="from ticket",
        )
    ]
    candidate.source_disposition_ids = [row.disposition_id for row in dispositions]
    gate, decisions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        [candidate],
        ContractFactSet(
            contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
            facts=facts,
        ),
        CANONICAL_REASONING_SERVICE.resolve_scope(
            ContractFactSet(
                contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
                facts=facts,
            ),
            [],
        ),
        dispositions,
    )
    return gate.status, decisions[0].reasons


def test_cross_product_requires_combination_evidence() -> None:
    count_fact = _fact("A count limit keeps only the most recent N entries.")
    logs_fact = _fact("A log-only action removes just the log file.")
    combined = _candidate(
        "When both the count limit and the log-only action are configured "
        "together, a run keeps the last N entries and removes only their log "
        "files.",
        [count_fact, logs_fact],
        [],
    )
    _status, reasons = _promote(combined, [count_fact, logs_fact])
    assert any("cross-product" in reason for reason in reasons)

    combination_fact = _fact(
        "When both the count limit and the log-only action apply together, "
        "entries are retained by count and only their logs are removed."
    )
    combined_with_evidence = _candidate(
        "When both the count limit and the log-only action are configured "
        "together, a run keeps the last N entries and removes only their log "
        "files.",
        [count_fact, logs_fact, combination_fact],
        [],
    )
    _status, reasons = _promote(
        combined_with_evidence, [count_fact, logs_fact, combination_fact]
    )
    assert not any("cross-product" in reason for reason in reasons)


def test_retained_object_usability_requires_separate_evidence() -> None:
    retention_fact = _fact(
        "The log-only action keeps the history entry and removes the log file."
    )
    usability = _candidate(
        "The retained history entry still opens in the UI and shows its run "
        "details after the log file is removed.",
        [retention_fact],
        [],
    )
    _status, reasons = _promote(usability, [retention_fact])
    assert any("Retained-object usability" in reason for reason in reasons)

    usability_fact = _fact(
        "After the log file is removed, the retained entry remains openable "
        "and readable in the history view."
    )
    supported = _candidate(
        "The retained history entry still opens in the UI and shows its run "
        "details after the log file is removed.",
        [retention_fact, usability_fact],
        [],
    )
    _status, reasons = _promote(supported, [retention_fact, usability_fact])
    assert not any("Retained-object usability" in reason for reason in reasons)


def test_backward_compatibility_requires_compatibility_evidence() -> None:
    plain_fact = _fact("The new retention option defaults to the age mode.")
    compat_claim = _candidate(
        "Existing installations remain unchanged after the upgrade.",
        [plain_fact],
        [],
    )
    _status, reasons = _promote(compat_claim, [plain_fact])
    assert any("compatibility" in reason.casefold() for reason in reasons)

    compat_fact = _fact(
        "Existing configurations remain unchanged after the upgrade.",
        ContractFactType.COMPATIBILITY_REQUIREMENTS,
    )
    supported = _candidate(
        "Existing installations remain unchanged after the upgrade.",
        [plain_fact, compat_fact],
        [],
    )
    _status, reasons = _promote(supported, [plain_fact, compat_fact])
    assert not any("compatibility" in reason.casefold() for reason in reasons)


# ---------------------------------------------------------------------------
# Production entry-point parity (spec section 15)
# ---------------------------------------------------------------------------


def _runtime_packet(description: str) -> dict[str, object]:
    return {
        "jira_key": "GUIDES-99077",
        "issue": {
            "issue_key": "GUIDES-99077",
            "summary": "Housekeeping job retention options.",
            "description": description,
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }


_RETENTION_DESCRIPTION = (
    "The housekeeping job removes output history entries older than the "
    "configured number of days. Provide an option to keep only the most "
    "recent entries per output preset. Provide an option to remove only the "
    "log file and keep the history entry for audit purposes."
)


def _run_runtime(packet: dict[str, object], options: dict[str, object] | None = None):
    from app.core.schemas_canonical_test_plan_runtime import (
        GenerationProfile,
        RuntimeEntryPoint,
    )
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99077",
        tenant_id="tenant-p1-parity",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        options=options or {},
    )
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_production_entry_point_suppresses_irrelevant_dimension() -> None:
    """The real top-level runtime path never asks the immaterial question."""

    result = _run_runtime(_runtime_packet(_RETENTION_DESCRIPTION))
    payload = result.output_payload
    scope_block = payload["scope"]
    assert scope_block["enable_dita_ot_processing"] == "NOT_APPLICABLE"
    assert scope_block["dita_ot_resolution_basis"] == (
        "NO_MATERIAL_INTERACTION_EVIDENCE"
    )
    questions = payload["missing_questions"]
    assert not any("DITA-OT" in row["question"] for row in questions)
    rendered = payload.get("plan_markdown") or ""
    assert "Is Enable DITA-OT Processing" not in rendered


def test_production_entry_point_resume_with_clarification() -> None:
    """Same production entry, two runs: blocked -> clarified -> not re-asked."""

    description = (
        "The generated page must include the merged appendix. "
        "Output generation must preserve the existing page order."
    )
    first = _run_runtime(_runtime_packet(description))
    first_questions = first.output_payload["missing_questions"]
    dita_question = next(
        row for row in first_questions if "DITA-OT" in row["question"]
    )
    assert dita_question["blocking"] is True

    clarification = _clarification()
    assert clarification["question_revision"] == dita_question["question_revision"]

    second = _run_runtime(
        _runtime_packet(description),
        options={"human_clarifications": [clarification]},
    )
    scope_block = second.output_payload["scope"]
    assert scope_block["enable_dita_ot_processing"] == "NOT_APPLICABLE"
    assert scope_block["dita_ot_resolution_basis"] == "HUMAN_CLARIFICATION"
    second_questions = second.output_payload["missing_questions"]
    assert not any("DITA-OT" in row["question"] for row in second_questions)
    trace_rows = second.trace.human_clarifications
    assert len(trace_rows) == 1
    assert trace_rows[0].status == ClarificationStatus.ADMITTED


# ---------------------------------------------------------------------------
# CLI presentation parity (spec section 15: no second semantic pipeline)
# ---------------------------------------------------------------------------


def test_cli_prefers_the_canonical_rendered_output() -> None:
    import importlib.util
    from pathlib import Path

    script = (
        Path(__file__).resolve().parents[2]
        / "scripts"
        / "run_test_plan_pipeline.py"
    )
    spec = importlib.util.spec_from_file_location("run_test_plan_pipeline", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    canonical_first = module._select_plan_text(
        {
            "draft_test_plan_markdown": "unvetted draft text",
            "qe_review_package": {"canonical_result": {
                "plan_markdown": "canonical plan text"}},
        }
    )
    assert canonical_first == "canonical plan text"

    fallback = module._select_plan_text(
        {"draft_test_plan_markdown": "draft only", "qe_review_package": {}}
    )
    assert fallback == "draft only"

    with pytest.raises(SystemExit):
        module._select_plan_text({"qe_review_package": {}})


# ---------------------------------------------------------------------------
# Noisy clone-grep coverage (spec section 16)
# ---------------------------------------------------------------------------


def test_raw_clone_fragments_never_become_human_coverage_prose() -> None:
    from app.core.schemas_canonical_test_plan_runtime import (
        ApplicabilityState,
        ClosureDimensionResult,
        ClosureDisposition,
        SemanticDimension,
    )

    raw_entity = (
        r"src/common/app_event_handler.ts, class DataKeyLoadMorePaginationMixin:, "
        r"resources/ui_config_custom_panel.json"
    )
    closure_row = ClosureDimensionResult(
        entity=raw_entity,
        dimension=SemanticDimension.GOVERNING_CONFIGURATION,
        applicability=ApplicabilityState.APPLICABLE,
        disposition=ClosureDisposition.COVERED,
        rationale="Covered by inspected implementation evidence.",
    )
    rows = CANONICAL_REASONING_SERVICE.classify_coverage(
        _retention_facts(), [closure_row], [], [],
        CANONICAL_REASONING_SERVICE.resolve_scope(_retention_facts(), []),
        [],
    )
    assert rows
    for row in rows:
        assert "app_event_handler.ts" not in row.candidate
        assert "class DataKeyLoadMorePaginationMixin" not in row.candidate
    covered = next(row for row in rows if row.source_closure_ids)
    # Evidence stays auditable on the record; only the prose is cleaned.
    assert covered.source_closure_ids == [closure_row.closure_id]
    assert "see trace" in covered.candidate


# ---------------------------------------------------------------------------
# Unfamiliar fixture (spec section 19): structurally different scenario
# exercising suppression, resume, and cross-product non-inference.
# ---------------------------------------------------------------------------


def test_unfamiliar_fixture_export_archive_cleanup() -> None:
    """A scheduled export-archive cleanup ticket (no publishing semantics in
    the observed sense at all beyond the domain route) gets the same three
    contracts."""

    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            _fact(
                "The scheduled cleanup removes expired export archives older "
                "than the configured retention window."
            ),
            _fact("Provide a maximum number of retained archives per profile."),
            _fact(
                "Provide an option to delete only the manifest file and keep "
                "the archive entry."
            ),
        ],
    )
    scope = CANONICAL_REASONING_SERVICE.resolve_scope(facts, _PUBLISHING)
    assert scope.enable_dita_ot_processing == DitaOtProcessingState.NOT_APPLICABLE

    # Cross-product non-inference on the unfamiliar shape.
    keep_fact = facts.facts[1]
    manifest_fact = facts.facts[2]
    combined = _candidate(
        "When both the archive count limit and the manifest-only delete are "
        "active together, cleanup keeps the newest archives and removes only "
        "manifests.",
        [keep_fact, manifest_fact],
        [],
    )
    _status, reasons = _promote(combined, [keep_fact, manifest_fact])
    assert any("cross-product" in reason for reason in reasons)

    # Clarification resume binds a question by deterministic id + revision.
    question = MissingQuestion(
        question="Does the retention window apply to shared profiles?",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[EvidenceSourceType.JIRA_DESCRIPTION],
        blocking=True,
    )
    admitted, errors = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [
            {
                "question_ref": question.question_id,
                "question_revision": question.question_revision,
                "answer": "not applicable - shared profiles are exempt",
                "answer_classification": (
                    ClarificationAnswerClass.APPLICABILITY_NOT_APPLICABLE.value
                ),
                "provided_by": "product-owner",
                "authority_role": AuthorityClass.CONFIRMED_PRODUCT_DECISION.value,
                "decision_reason": "Product decision recorded in review.",
            }
        ],
        [question],
    )
    assert errors == []
    (row,) = admitted
    assert row.status == ClarificationStatus.ADMITTED

    batch = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, [], [question], resolved_question_ids={question.question_id}
    )
    assert batch.candidates == []
