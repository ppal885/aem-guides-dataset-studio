"""R2: Canonical Agentic Research Orchestration.

RESEARCH_REQUIRED must mean a research worker actually executes, or the
runtime records that the worker could not execute.  A flag saying "research
required" is not research.

Covers: worker execution through the production entry point, the
research-before-clarification invariant, negative/implementation-only/
conflict controls, doc-only/code-only routing, and worker failure honesty.
All fixtures are sanitized; no ticket/feature/repository hardcoding in
production code.
"""

from __future__ import annotations

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    ContractFactType,
    ContractMode,
    EvidenceSourceType,
    GenerationProfile,
    MissingQuestion,
    OpenQuestionClass,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
    RuntimeEntryPoint,
    SourceVisibility,
    EvidenceRecord,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME
from app.services.research_workers import (
    AttachmentResearchWorker,
    CodeResearchWorker,
    DocResearchWorker,
    ResearchOrchestrator,
)
from app.services.question_research_routing_service import QUESTION_RESEARCH_ROUTER


def _record(
    reference: str,
    text: str,
    source_type: EvidenceSourceType,
    authority: AuthorityClass = AuthorityClass.CURRENT_JIRA,
) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_reference=f"test:{reference}",
        tenant_id="tenant_r2",
        visibility=SourceVisibility(tenant_id="tenant_r2"),
        requirement_authority=authority,
        content={"description": text},
    )


def _bundle(*records: EvidenceRecord) -> CanonicalEvidenceBundle:
    return CanonicalEvidenceBundle(tenant_id="tenant_r2", records=list(records))


def _question(text: str, dimension=None) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        dimension=dimension,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        target_source_types=[],
        blocking=True,
        open_question_class=OpenQuestionClass.USER_ACCEPTANCE_DECISION,
    )


def _requirement(
    question: MissingQuestion,
    research_requirement: ResearchRequirement,
    source_types: list[EvidenceSourceType],
) -> ResearchRequirementRecord:
    return ResearchRequirementRecord(
        question_id=question.question_id,
        research_requirement=research_requirement,
        material=True,
        required_source_types=source_types,
        rationale="test requirement",
    )


def t_fact(text: str):
    from app.core.schemas_canonical_test_plan_runtime import ContractFact

    return ContractFact(
        fact_type=ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
        literal=text,
        normalized_value=text.casefold(),
        source_evidence_ids=["ev-test"],
        source_reference="test:description",
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        authority_class=AuthorityClass.CUSTOMER_REQUEST,
        authoritative=True,
    )


# ---------------------------------------------------------------------------
# Worker units: honest availability and structured findings
# ---------------------------------------------------------------------------


def test_doc_worker_reports_source_unavailable_without_documentation() -> None:
    question = _question("What does the documentation establish for output retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = DocResearchWorker().research(question, requirement, _bundle())
    assert result.status == ResearchWorkerStatus.SOURCE_UNAVAILABLE
    assert result.limitations
    assert not result.findings


def test_doc_worker_finds_documentation_evidence() -> None:
    doc = _record(
        "doc1",
        "The retention job removes entries older than the configured period.",
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
    )
    question = _question(
        "What does the documentation establish for retention period?"
    )
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.DITA_OT_DOCUMENTATION],
    )
    result = DocResearchWorker().research(
        question, requirement, _bundle(doc)
    )
    assert result.status == ResearchWorkerStatus.ANSWER_FOUND
    assert result.findings
    assert result.findings[0].source_refs == [doc.evidence_id]
    assert result.findings[0].evidence_role.value == "EXISTING_BEHAVIOR"


def test_code_worker_bundle_evidence_and_unavailable_without_sources() -> None:
    code = _record(
        "code1",
        "The resolver returns the computed state for each entry.",
        EvidenceSourceType.CURRENT_CODE,
    )
    question = _question("Does current implementation expose a computed state?")
    requirement = _requirement(
        question,
        ResearchRequirement.IMPLEMENTATION,
        [EvidenceSourceType.CURRENT_CODE],
    )
    found = CodeResearchWorker().research(
        question, requirement, _bundle(code), repository_roots=[]
    )
    assert found.status == ResearchWorkerStatus.ANSWER_FOUND
    assert found.findings[0].evidence_role.value == "IMPLEMENTATION_EVIDENCE"

    missing = CodeResearchWorker().research(
        question, requirement, _bundle(), repository_roots=[]
    )
    assert missing.status == ResearchWorkerStatus.SOURCE_UNAVAILABLE


def test_attachment_worker_never_fabricates_visual_content() -> None:
    raw_attachment = _record(
        "att1", "image-0001.png", EvidenceSourceType.JIRA_ATTACHMENT
    )
    question = _question("What does the customer evidence show?")
    requirement = _requirement(
        question,
        ResearchRequirement.MULTI_SOURCE,
        [EvidenceSourceType.JIRA_ATTACHMENT],
    )
    result = AttachmentResearchWorker().research(
        question, requirement, _bundle(raw_attachment)
    )
    # Unanalyzed visual content is a recorded limitation, not a finding.
    assert result.status == ResearchWorkerStatus.SOURCE_UNAVAILABLE
    assert any("not analyzed" in note for note in result.limitations)
    assert not result.findings


def test_orchestrator_dispatches_only_mandated_routes() -> None:
    doc = _record(
        "doc2",
        "The configuration controls the retention window.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    )
    attachment = _record(
        "att2",
        "Screenshot evidence from an unrelated ticket observation.",
        EvidenceSourceType.JIRA_ATTACHMENT,
    )
    bundle = _bundle(doc, attachment)
    doc_question = _question("Which configuration controls retention?")
    doc_requirement = _requirement(
        doc_question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    code_question = _question("Does the implementation honor the window?")
    code_requirement = _requirement(
        code_question,
        ResearchRequirement.IMPLEMENTATION,
        [EvidenceSourceType.CURRENT_CODE],
    )
    results, executions = ResearchOrchestrator().execute(
        [doc_question, code_question],
        [doc_requirement, code_requirement],
        bundle,
        repository_roots=[],
    )
    by_role = {}
    for execution in executions:
        by_role.setdefault(execution.worker_role, []).append(execution)
    # Doc question -> doc worker only; code question -> code worker only.
    assert len(by_role[ResearchWorkerRole.DOC_RESEARCHER]) == 1
    assert len(by_role[ResearchWorkerRole.CODE_RESEARCHER]) == 1
    # An unrelated ticket attachment must not fan out an attachment worker to
    # documentation or implementation questions.
    assert ResearchWorkerRole.ATTACHMENT_RESEARCHER not in by_role
    assert all(execution.result_ref for execution in executions)


def test_orchestrator_dispatches_attachment_worker_only_when_required() -> None:
    attachment = _record(
        "att3",
        "A screenshot that must be inspected for the requested visual behavior.",
        EvidenceSourceType.JIRA_ATTACHMENT,
    )
    question = _question("What does the attached screenshot show?")
    requirement = _requirement(
        question,
        ResearchRequirement.MULTI_SOURCE,
        [EvidenceSourceType.JIRA_ATTACHMENT],
    )

    _results, executions = ResearchOrchestrator().execute(
        [question],
        [requirement],
        _bundle(attachment),
        repository_roots=[],
    )

    assert [execution.worker_role for execution in executions] == [
        ResearchWorkerRole.ATTACHMENT_RESEARCHER
    ]


def test_resolve_consumes_worker_results() -> None:
    question = _question("What does documentation establish for retention?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    # No retrieval/handoff execution at all -> PENDING without workers.
    pending = QUESTION_RESEARCH_ROUTER.resolve(requirement)
    assert pending.research_status.value == "PENDING"
    # A worker envelope counts as executed research.
    worker = ResearchWorkerResult(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        status=ResearchWorkerStatus.NOT_FOUND,
        limitations=["searched"],
    )
    resolved = QUESTION_RESEARCH_ROUTER.resolve(
        requirement, worker_results=[worker]
    )
    assert resolved.research_status.value == "NOT_FOUND"
    assert worker.research_id in resolved.research_request_ids
    # A worker that could not execute yields SOURCE_UNAVAILABLE, not a clean
    # NOT_FOUND.
    failed = ResearchWorkerResult(
        worker_role=ResearchWorkerRole.DOC_RESEARCHER,
        question_id=question.question_id,
        status=ResearchWorkerStatus.WORKER_UNAVAILABLE,
        limitations=["no doc source"],
    )
    unavailable = QUESTION_RESEARCH_ROUTER.resolve(
        requirement, worker_results=[failed]
    )
    assert unavailable.research_status.value == "SOURCE_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Production entry point: sanitized linked-fix regression (spec 12/13/20)
# ---------------------------------------------------------------------------


def _packet(*, with_fix: bool, with_implementation: bool) -> dict:
    issue = {
        "issue_key": "GUIDES-99301",
        "summary": "Generation can succeed with unnoticed log entries.",
        "description": (
            "Generation completes successfully but can contain log entries "
            "that reviewers do not notice without opening the log. "
            "There is no easy way to notice entries that need attention."
        ),
        "deployment_model": "On-prem",
        "product_version": "5.0",
        "attachments": [
            {"id": "att-1", "filename": "capture.png", "url": "", "size": 10}
        ],
    }
    if with_fix:
        issue["labels"] = ["accepted_uac"]
        issue["acceptance_criteria"] = [
            "Completed generation that contains log entries requiring "
            "attention is shown with a distinct attention state, separate "
            "from hard failure."
        ]
        issue["comments"] = [
            {
                "id": "c-1",
                "author": "engineer",
                "created": "2024-01-01",
                "body": (
                    "Fixed by: completed output carrying log entries is "
                    "inspected and a distinct attention indication is shown "
                    "in the output listing."
                ),
            }
        ]
    if with_implementation:
        return {
            "jira_key": "GUIDES-99301",
            "issue": issue,
            "implementation_diff_evidence": {
                "id": "repo-pr-1",
                "url": "https://git.example.test/example/repo/pull/1",
                "commit_sha": "a" * 40,
                "changed_files": ["src/main/java/com/example/State.java"],
                "changed_methods": ["State.compute"],
            },
        }
    return {"jira_key": "GUIDES-99301", "issue": issue}


def _run(packet: dict):
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99301",
        tenant_id="tenant_r2",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def test_linked_fix_evidence_is_researched_before_clarification() -> None:
    result = _run(_packet(with_fix=True, with_implementation=True))
    payload = result.output_payload
    trace = result.trace
    # Workers actually executed (auditable execution records, not flags).
    assert trace.research_worker_executions
    assert all(
        execution.result_ref for execution in trace.research_worker_executions
    )
    # The attached screenshot does not fan out to unrelated questions unless
    # their source requirements explicitly name Jira attachment evidence.
    assert all(
        execution.worker_role.value != "ATTACHMENT_RESEARCHER"
        for execution in trace.research_worker_executions
    )
    # The accepted fix establishes the bounded intended behavior without any
    # human clarification.
    promoted = [
        row
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    ]
    assert promoted
    candidate_ids = {row["candidate_id"] for row in promoted}
    candidates = {
        row["candidate_id"]: row for row in payload["acceptance_candidates"]
    }
    assert any(
        "attention" in candidates[candidate_id]["statement"].casefold()
        for candidate_id in candidate_ids
    )
    assert result.status != "blocked"
    # Human output must not render the blocked clarification document.
    rendered = result.rendered_output or ""
    assert "No Acceptance Criteria were generated" not in rendered
    # No raw fragments or paths leak into human output.
    assert ".java" not in rendered


def test_negative_control_problem_without_fix_stays_blocked() -> None:
    result = _run(_packet(with_fix=False, with_implementation=False))
    payload = result.output_payload
    assert result.status == "blocked"
    assert not payload["acceptance_candidates"]
    assert not [
        row
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    ]
    rendered = result.rendered_output or ""
    assert "None generated until the blocking decisions are resolved." in rendered
    # P2 preservation: the neutral product decision is still asked.
    assert "Open product decisions" in rendered
    # Workers ran (attachments present) but established nothing.
    assert result.trace.research_worker_executions


def test_implementation_only_control_does_not_promote_a_solution() -> None:
    result = _run(_packet(with_fix=False, with_implementation=True))
    payload = result.output_payload
    # Implementation research executed and recorded findings/handoffs, but no
    # product authority adopted the implementation as the fix.
    assert not [
        row
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    ]
    assert result.status in {"blocked", "needs_human_review"}


def test_research_resolved_question_is_not_reasked() -> None:
    # A blocking question whose mandated research terminates ANSWER_FOUND on
    # establishing-authority evidence releases without human clarification.
    doc = _record(
        "doc3",
        "The retention window is controlled by the configured period.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        authority=AuthorityClass.SPECIFICATION_AUTHORITY,
    )
    bundle = _bundle(doc)
    question = _question("Which configuration controls the retention window?")
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    results, _executions = ResearchOrchestrator().execute(
        [question], [requirement], bundle, repository_roots=[]
    )
    record = QUESTION_RESEARCH_ROUTER.resolve(
        requirement, worker_results=results
    )
    assert record.research_status.value in {"ANSWER_FOUND", "PARTIAL"}
    assert record.research_status.value != "PENDING"
    assert doc.evidence_id in record.evidence_ids


# ---------------------------------------------------------------------------
# C1 consumes the ACTUAL R2 worker artifacts (lineage proof)
# ---------------------------------------------------------------------------


def _rebuild_runtime_inputs(payload: dict):
    """Reconstruct typed inputs from the production payload for the
    dependency-mutation half of the proof."""
    from app.core.schemas_canonical_test_plan_runtime import (
        BehaviorHypothesis,
        ClosureDimensionResult,
        ContractFactSet,
        DomainImpact,
        MissingQuestion,
        ResearchRequirementRecord,
        ScopeResolution,
    )

    return {
        "facts": ContractFactSet.model_validate(payload["contract_facts"]),
        "closure": [
            ClosureDimensionResult.model_validate(row)
            for row in payload["semantic_closure"]
        ],
        "impacts": [
            DomainImpact.model_validate(row) for row in payload["domain_impacts"]
        ],
        "hypotheses": [
            BehaviorHypothesis.model_validate(row) for row in payload["hypotheses"]
        ],
        "scope": ScopeResolution.model_validate(payload["scope"]),
        "questions": [
            MissingQuestion.model_validate(row)
            for row in payload["missing_questions"]
        ],
        "requirements": [
            ResearchRequirementRecord.model_validate(row)
            for row in payload["research_requirements"]
        ],
    }


def test_coverage_consumes_actual_worker_results_not_ticket_text() -> None:
    """Required lineage: ResearchWorkerExecution -> ResearchWorkerResult ->
    Question Resolution -> ClaimSufficiencyRecord -> Coverage Decision.

    Removing or rebinding the ResearchWorkerResult must break the dependent
    coverage decision - proving C1 consumes the real R2 research artifact
    rather than reproducing the expected classification from ticket text.
    """
    from app.core.schemas_canonical_test_plan_runtime import (
        QuestionResearchRecord,
        ResearchWorkerResult,
    )
    from app.services.canonical_test_plan_reasoning_service import (
        CANONICAL_REASONING_SERVICE,
    )

    result = _run(_packet(with_fix=True, with_implementation=True))
    trace = result.trace
    payload = result.output_payload

    # --- Lineage: execution -> result -----------------------------------
    assert trace.research_worker_executions
    worker_results = {row.research_id: row for row in trace.research_worker_results}
    for execution in trace.research_worker_executions:
        assert execution.result_ref in worker_results
        assert (
            worker_results[execution.result_ref].question_id
            == execution.question_id
        )

    # --- Lineage: result -> question resolution --------------------------
    worker_bound = [
        row
        for row in trace.question_research
        if any(
            request_id in worker_results
            for request_id in row.research_request_ids
        )
    ]
    assert worker_bound
    research_by_question = {row.question_id: row for row in trace.question_research}

    # --- Lineage: resolution -> coverage decision ------------------------
    # The worker-bound question's coverage disposition must link the same
    # canonical question id and carry a real C1 class.
    dependent: dict[str, dict] = {}
    for row in payload["coverage_dispositions"]:
        for question_id in row["source_question_ids"]:
            if question_id in {r.question_id for r in worker_bound}:
                dependent[question_id] = row
    assert dependent

    # --- Lineage: coverage -> sufficiency (C2B-C1 sufficiency_ref) -------
    sufficiency_coverage_refs = {
        ref
        for row in payload["sufficiency"]
        for ref in row["coverage_refs"]
    }
    # At least the promoted path is sufficiency-tracked; a disposition linked
    # to a promoted candidate must carry a sufficiency record reference.
    promoted = {
        row["candidate_id"]
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    candidates = {
        row["candidate_id"]: row for row in payload["acceptance_candidates"]
    }
    promoted_disposition_ids = {
        disposition_id
        for candidate_id in promoted
        for disposition_id in candidates[candidate_id]["source_disposition_ids"]
    }
    assert promoted_disposition_ids <= sufficiency_coverage_refs

    # --- Dependency: remove the worker result ----------------------------
    inputs = _rebuild_runtime_inputs(payload)
    requirements_by_question = {
        row.question_id: row for row in inputs["requirements"]
    }
    target_question_id = sorted(dependent)[0]
    original_record = research_by_question[target_question_id]
    target_results = [
        row
        for row in trace.research_worker_results
        if row.question_id == target_question_id
    ]
    assert target_results

    requirement = requirements_by_question[target_question_id]
    retrievals = [
        row
        for row in result.trace.directed_retrievals
        if row.question_id == target_question_id
    ] if hasattr(result.trace, "directed_retrievals") else []
    retrievals = [
        row
        for row in (result.output_payload.get("directed_retrievals") or [])
        if row["question_id"] == target_question_id
    ]
    from app.core.schemas_canonical_test_plan_runtime import DirectedRetrievalRecord

    typed_retrievals = [
        DirectedRetrievalRecord.model_validate(row) for row in retrievals
    ]
    hypotheses = [
        row
        for row in inputs["hypotheses"]
        if row.derived_from_question_id == target_question_id
    ]

    without_worker = QUESTION_RESEARCH_ROUTER.resolve(
        requirement,
        retrievals=typed_retrievals,
        hypotheses=hypotheses,
        worker_results=[],
    )
    assert without_worker.research_status != original_record.research_status
    # Removing the worker envelope degrades the research state.
    assert without_worker.research_status.value in {
        "PENDING",
        "PARTIAL",
        "NOT_FOUND",
        "SOURCE_UNAVAILABLE",
    }

    # --- Dependency: rebinding is detected, never silently accepted ------
    other_question_id = next(
        row.question_id
        for row in inputs["questions"]
        if row.question_id != target_question_id
    )
    # Rebinding the envelope to another question changes the identity: the
    # deterministic-id validator rejects the tampered artifact outright.
    rebound_payload = target_results[0].model_dump(mode="json")
    rebound_payload["question_id"] = other_question_id
    with pytest.raises(ValueError, match="deterministic identity"):
        ResearchWorkerResult.model_validate(rebound_payload)
    # And even if a stale-id copy is smuggled past validation, resolution
    # binds by question_id: it contributes nothing to this question.
    rebound = target_results[0].model_copy(
        update={"question_id": other_question_id}
    )
    rebound_record = QUESTION_RESEARCH_ROUTER.resolve(
        requirement,
        retrievals=typed_retrievals,
        hypotheses=hypotheses,
        worker_results=[rebound],
    )
    assert rebound_record.research_status == without_worker.research_status
    assert rebound_record.research_request_ids == (
        without_worker.research_request_ids
    )

    # --- Dependency: the dependent coverage decision loses eligibility ---
    downgraded_research = [
        without_worker if row.question_id == target_question_id else row
        for row in [
            QuestionResearchRecord.model_validate(r.model_dump(mode="json"))
            for r in trace.question_research
        ]
    ]
    reclassified = CANONICAL_REASONING_SERVICE.classify_coverage(
        inputs["facts"],
        inputs["closure"],
        inputs["impacts"],
        inputs["hypotheses"],
        inputs["scope"],
        inputs["questions"],
        downgraded_research,
    )
    by_id = {row.disposition_id: row for row in reclassified}
    before = dependent[target_question_id]
    after = by_id[before["disposition_id"]]
    if original_record.research_status.value == "ANSWER_FOUND":
        # Mandatory research incomplete => the question stays open; the
        # previously finalized disposition is forced back to OPEN_QUESTION.
        assert after.disposition.value == "OPEN_QUESTION"
        assert after.coverage_class != before["coverage_class"] or (
            before["coverage_class"] != "ACCEPTANCE"
        )
        assert after.coverage_class == "INVESTIGATION"
    else:
        # Already-open rows cannot be silently finalized either.
        assert after.disposition.value == "OPEN_QUESTION"


def test_removing_worker_result_flips_finalized_coverage_to_open() -> None:
    """The worker envelope is the difference between finalized QE_REGRESSION
    coverage and a forced OPEN_QUESTION: remove the ResearchWorkerResult and
    the dependent Coverage Decision loses eligibility.  This is the strong
    form of the C1-consumes-R2 proof - the classification cannot be
    reproduced from ticket text alone."""
    from app.core.schemas_canonical_test_plan_runtime import (
        BehaviorHypothesis,
        ClosureDimensionResult,
        ClosureDisposition,
        ContractFactSet,
        ContractMode,
        HypothesisState,
        ResearchFinding,
        ResearchFindingEvidenceRole,
        ScopeResolution,
        SemanticDimension,
    )
    from app.services.canonical_test_plan_reasoning_service import (
        CANONICAL_REASONING_SERVICE,
    )

    doc = _record(
        "doc-flip",
        "The configured period governs the retention of entries.",
        EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        authority=AuthorityClass.SPECIFICATION_AUTHORITY,
    )
    bundle = _bundle(doc)
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            # An established expected behavior so the run is material.
            t_fact("Retention must keep the most recent entries."),
        ],
    )
    closure = [
        ClosureDimensionResult(
            entity="retention window",
            dimension=SemanticDimension.GOVERNING_CONFIGURATION,
            applicability="APPLICABLE",
            disposition=ClosureDisposition.UNRESOLVED_AND_EXPOSED,
            rationale="unresolved",
        )
    ]
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        closure, ScopeResolution(), facts
    )
    question = next(
        row
        for row in questions
        if row.dimension == SemanticDimension.GOVERNING_CONFIGURATION
    )
    requirement = _requirement(
        question,
        ResearchRequirement.DOCUMENTATION,
        [EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    hypothesis = BehaviorHypothesis(
        statement=question.question,
        state=HypothesisState.CONFIRMED,
        supporting_evidence_ids=[doc.evidence_id],
        derived_from_question_id=question.question_id,
        confidence=0.9,
    )
    # The worker executes and answers from the authorized documentation.
    results, executions = ResearchOrchestrator().execute(
        [question], [requirement], bundle, repository_roots=[]
    )
    worker_result = next(
        row
        for row in results
        if row.worker_role == ResearchWorkerRole.DOC_RESEARCHER
    )
    assert worker_result.status == ResearchWorkerStatus.ANSWER_FOUND

    resolved_with = QUESTION_RESEARCH_ROUTER.resolve(
        requirement, hypotheses=[hypothesis], worker_results=results
    )
    assert resolved_with.research_status.value == "ANSWER_FOUND"
    # The research record cites the actual worker research id.
    assert worker_result.research_id in resolved_with.research_request_ids

    def _coverage(research_record):
        return {
            row.disposition_id: row
            for row in CANONICAL_REASONING_SERVICE.classify_coverage(
                facts,
                closure,
                [],
                [hypothesis],
                ScopeResolution(),
                questions,
                [research_record],
            )
        }

    with_worker = _coverage(resolved_with)
    finalized = next(
        row
        for row in with_worker.values()
        if question.question_id in row.source_question_ids
    )
    # Research complete => coverage finalizes as real regression coverage.
    assert finalized.disposition.value != "OPEN_QUESTION"
    assert finalized.coverage_class == "QE_REGRESSION"

    # Remove the ResearchWorkerResult: research degrades (nothing else
    # executed) and the same coverage decision is forced back open.
    resolved_without = QUESTION_RESEARCH_ROUTER.resolve(
        requirement, hypotheses=[hypothesis], worker_results=[]
    )
    assert resolved_without.research_status.value == "PENDING"
    without_worker = _coverage(resolved_without)
    reopened = next(
        row
        for row in without_worker.values()
        if question.question_id in row.source_question_ids
    )
    assert reopened.disposition.value == "OPEN_QUESTION"
    assert reopened.coverage_class == "INVESTIGATION"
    assert finalized.coverage_class != reopened.coverage_class


# ---------------------------------------------------------------------------
# Clone-path ownership: clone-backed research resolves paths on the caller's
# machine, so the caller's roots must survive intact from request to worker.
# ---------------------------------------------------------------------------


def test_pipeline_request_carries_caller_repository_roots_losslessly() -> None:
    """The caller's local clone roots must survive the typed projection in
    both directions, and default to empty so a same-machine CLI run keeps
    falling back to this host's configured repository env vars."""

    from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
    from app.services.test_plan_runtime_adapters import (
        generation_request_from_pipeline_request,
        pipeline_request_from_generation_request,
    )

    roots = ["C:\\UI TEST\\guides-ui-tests", "C:\\repos\\starling"]
    request = TestPlanPipelineRequest(
        jira_key="GUIDES-00000", research_repository_roots=roots
    )
    generation = generation_request_from_pipeline_request(
        request, entry_point="rest_bridge"
    )
    assert generation.options.research_repository_roots == roots
    assert (
        pipeline_request_from_generation_request(
            generation
        ).research_repository_roots
        == roots
    )

    default = generation_request_from_pipeline_request(
        TestPlanPipelineRequest(jira_key="GUIDES-00000"), entry_point="cli"
    )
    assert default.options.research_repository_roots == []


def test_runtime_threads_caller_repository_roots_into_research_orchestrator() -> None:
    """The runtime must hand the caller's roots to the orchestrator.  Omitting
    the argument silently re-resolved clone paths against the runtime host,
    which is the wrong machine whenever the caller is remote."""

    import ast
    import inspect

    from app.services import canonical_test_plan_runtime as runtime_module

    tree = ast.parse(inspect.getsource(runtime_module.CanonicalTestPlanRuntime))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "execute"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "RESEARCH_ORCHESTRATOR"
    ]
    assert calls, "runtime no longer dispatches research through the orchestrator"
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "repository_roots" in keywords
        source = ast.unparse(call)
        assert "research_repository_roots" in source