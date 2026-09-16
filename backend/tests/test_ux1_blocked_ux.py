"""UX1: Blocked-Run UX, Human Question Quality, and Evidence-Driven NFR.

Based on a real canonical run of a thin legacy UI-enhancement ticket where
the runtime correctly failed closed (status=blocked, zero candidates) but
the user experience was wrong: a plan-shaped document with description
sentences as proposed ACs, grep-soup questions, and carpet NFR coverage.

Contracts under test (all generic; no ticket/feature hardcoding):

- Blocked is a first-class output state: compact clarification document,
  never a plan-shaped artifact.
- Zero promotions means zero acceptance criteria; narrative description
  context never becomes a proposed acceptance contract.
- Human-facing questions satisfy a readability quality contract; raw
  evidence entities are projected to typed dimensions or suppressed.
- NFR activation is domain-bound: a generic scale signal activates only
  domains whose own evidence carries the signal.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthoritySubject,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactType,
    ContractMode,
    DomainActivation,
    EvidenceRecord,
    EvidenceSourceType,
    GateDecision,
    GateStatus,
    IssueDomain,
    RuntimeEntryPoint,
    GenerationProfile,
    ScopeResolution,
    SemanticDimension,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
    _fact_types,
    _human_question_safe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


def _runtime_run(description: str, summary: str = "A thin legacy report"):
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99103",
        tenant_id="tenant_ux1",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99103",
        "issue": {
            "issue_key": "GUIDES-99103",
            "summary": summary,
            "description": description,
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


# ---------------------------------------------------------------------------
# Blocked-run rendering (spec sections 2, 3, 4, 5, 13)
# ---------------------------------------------------------------------------


def test_blocked_run_renders_compact_clarification_document() -> None:
    result = _runtime_run(
        "The old dialog gives a colored hint as an indication that you "
        "should check the log. "
        "In this example, an image is missing but the author must open the "
        "log to notice. There is no easy way to see processing problems."
    )
    assert result.status == "blocked"
    payload = result.output_payload
    assert not payload["acceptance_candidates"]
    assert not [
        row
        for row in payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    ]
    rendered = result.rendered_output
    # Compact blocked shape.
    assert "## Generation status" in rendered
    assert "UAC needs product clarification." in rendered
    assert (
        "No Acceptance Criteria were generated because required product "
        "decisions remain unresolved." in rendered
    )
    assert (
        "None generated until the blocking decisions are resolved."
        in rendered
    )
    # Never a plan-shaped artifact.
    assert "Acceptance contract" not in rendered
    assert "Coverage gate result" not in rendered
    assert "NFR coverage" not in rendered
    assert "internal evidence recorded" not in rendered
    # No raw fragments or local paths leak into human output.
    assert "C:\\" not in rendered
    assert ".feature" not in rendered


def test_narrative_description_never_becomes_acceptance_contract() -> None:
    # Zero-promotion invariant at the source: narrative/current-state
    # description sentences carry no requirement signal, so they are context,
    # never DIRECT_EXPECTED_BEHAVIOR and never a coverage disposition.
    narrative = (
        "The old interface shows a small indicator next to each output entry."
    )
    assert _fact_types("description", narrative) == [
        ContractFactType.CONTEXT_STATEMENT
    ]
    # Person-burden observations classify as the problem, not the solution.
    burden = (
        "The old interface gives a status hint as an indication that you "
        "should check the log."
    )
    assert ContractFactType.PROBLEM_STATEMENT in _fact_types(
        "description", burden
    )
    assert ContractFactType.DIRECT_EXPECTED_BEHAVIOR not in _fact_types(
        "description", burden
    )
    result = _runtime_run(narrative)
    payload = result.output_payload
    assert not payload["acceptance_candidates"]
    dispositions = payload["coverage_dispositions"]
    assert not [
        row
        for row in dispositions
        if row["disposition"] == "PROPOSED_ACCEPTANCE_CONTRACT"
        and "small indicator" in row["candidate"]
    ]
    # Context still informs issue understanding (rendered, not dropped).
    assert "small indicator" in (result.rendered_output or "")


# ---------------------------------------------------------------------------
# Human question quality contract (spec sections 6, 7, 8)
# ---------------------------------------------------------------------------


def test_human_question_quality_contract() -> None:
    assert _human_question_safe("the affected behavior")
    assert _human_question_safe("output history entries")
    # Raw local paths.
    assert not _human_question_safe(r"C:\repo\tests\feature.feature")
    # Code symbol soup.
    assert not _human_question_safe("class OutputHistory extends Base")
    assert not _human_question_safe("def render_plan(")
    # Environment/constant dumps.
    assert not _human_question_safe("when ENABLE_LOADFILES_PAGINATION is true")
    # Arbitrary numeric/token lists.
    assert not _human_question_safe("alpha, beta, gamma, delta")
    # Empty interpolation.
    assert not _human_question_safe("")


def _unresolved_closure(entity: str) -> ClosureDimensionResult:
    return ClosureDimensionResult(
        entity=entity,
        dimension=SemanticDimension.DIRECT_CONSUMERS,
        applicability="APPLICABLE",
        disposition=ClosureDisposition.UNRESOLVED_AND_EXPOSED,
        rationale="unresolved",
    )


def test_raw_entities_project_to_typed_dimension_question() -> None:
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [_unresolved_closure(r"C:\repo\src\handler.ts, class Consumer(Base)")],
        ScopeResolution(),
        _facts("Export jobs must write a completion marker."),
    )
    assert questions
    for question in questions:
        assert _human_question_safe(question.question)
        assert "the affected behavior" in question.question
    # Typed dimension and lineage are preserved for research routing.
    assert questions[0].dimension == SemanticDimension.DIRECT_CONSUMERS
    assert questions[0].source_closure_ids


def test_equivalent_blocking_questions_deduplicate() -> None:
    questions = CANONICAL_REASONING_SERVICE.generate_missing_questions(
        [
            _unresolved_closure(r"C:\repo\a\consumer_one.ts"),
            _unresolved_closure(r"C:\repo\b\consumer_two.ts"),
        ],
        ScopeResolution(),
        _facts("Export jobs must write a completion marker."),
    )
    consumer_questions = [
        row for row in questions if row.dimension == SemanticDimension.DIRECT_CONSUMERS
    ]
    # Both raw entities project to the same typed question text, which
    # collapses to one canonical question (content-hashed identity).
    assert len(consumer_questions) == 1
    assert len(consumer_questions[0].source_closure_ids) == 2


# ---------------------------------------------------------------------------
# Domain-bound NFR activation (spec sections 10, 11, 12)
# ---------------------------------------------------------------------------


def _record(reference: str, text: str) -> EvidenceRecord:
    from app.core.schemas_canonical_test_plan_runtime import SourceVisibility

    # The schema computes a deterministic evidence_id from the source
    # identity; callers read it back from the constructed record.
    return EvidenceRecord(
        source_type=EvidenceSourceType.JIRA_DESCRIPTION,
        authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_reference=f"test:{reference}",
        tenant_id="tenant_ux1",
        visibility=SourceVisibility(tenant_id="tenant_ux1"),
        content={"description": text},
    )


def _bundle(*records: EvidenceRecord) -> CanonicalEvidenceBundle:
    return CanonicalEvidenceBundle(
        tenant_id="tenant_ux1", records=list(records)
    )


def test_nfr_activation_is_domain_bound() -> None:
    # A generic scale signal in one domain's evidence must not fan out.
    publishing_record = _record(
        "pub", "Bulk generation of outputs is the concern here."
    )
    authoring_record = _record(
        "auth", "The authoring panel shows a status hint."
    )
    bundle = _bundle(publishing_record, authoring_record)
    domains = [
        DomainActivation(
            domain=IssueDomain.PUBLISHING,
            confidence=0.9,
            evidence_ids=[publishing_record.evidence_id],
        ),
        DomainActivation(
            domain=IssueDomain.AUTHORING,
            confidence=0.8,
            evidence_ids=[authoring_record.evidence_id],
        ),
        DomainActivation(domain=IssueDomain.ASSETS, confidence=0.5, evidence_ids=[]),
    ]
    impacts = CANONICAL_REASONING_SERVICE.model_domain_impact(
        bundle, domains, CanonicalBehaviorModel()
    )
    by_domain = {impact.domain: impact for impact in impacts}
    assert by_domain[IssueDomain.PUBLISHING].nfr_applicable
    assert by_domain[IssueDomain.PUBLISHING].nfr_evidence_ids == [
        publishing_record.evidence_id
    ]
    assert by_domain[IssueDomain.PUBLISHING].nfr_materiality_basis
    assert not by_domain[IssueDomain.AUTHORING].nfr_applicable
    assert not by_domain[IssueDomain.ASSETS].nfr_applicable


def test_nfr_positive_control_explicit_scale_evidence() -> None:
    # Explicit cardinality evidence tied to one domain activates exactly that
    # domain - the fix suppresses carpet coverage, not genuine NFR coverage.
    scale_record = _record(
        "scale",
        "Publishing must handle 5000 topics in one map without data loss.",
    )
    ui_record = _record("ui", "The panel shows a colored status hint.")
    bundle = _bundle(scale_record, ui_record)
    domains = [
        DomainActivation(
            domain=IssueDomain.PUBLISHING,
            confidence=0.9,
            evidence_ids=[scale_record.evidence_id],
        ),
        DomainActivation(
            domain=IssueDomain.AUTHORING,
            confidence=0.8,
            evidence_ids=[ui_record.evidence_id],
        ),
    ]
    impacts = CANONICAL_REASONING_SERVICE.model_domain_impact(
        bundle, domains, CanonicalBehaviorModel()
    )
    by_domain = {impact.domain: impact for impact in impacts}
    assert by_domain[IssueDomain.PUBLISHING].nfr_applicable
    assert (
        "explicit high cardinality"
        in by_domain[IssueDomain.PUBLISHING].nfr_triggers
    )
    assert not by_domain[IssueDomain.AUTHORING].nfr_applicable
    # And the coverage disposition cites the domain-bound evidence.
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        _facts("Publishing must handle 5000 topics in one map without data loss."),
        [],
        impacts,
        [],
        ScopeResolution(),
        [],
    )
    nfr_rows = [
        row for row in dispositions if row.disposition.value == "NFR_COVERAGE"
    ]
    assert len(nfr_rows) == 1
    assert nfr_rows[0].evidence_ids == [scale_record.evidence_id]
    assert "domain-bound" in nfr_rows[0].rationale


# ---------------------------------------------------------------------------
# Blocked vs review vs completed renderer distinction (spec section 14)
# ---------------------------------------------------------------------------


def _facts(text: str, fact_type: ContractFactType | None = None):
    from app.core.schemas_canonical_test_plan_runtime import ContractFactSet

    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=fact_type or ContractFactType.DIRECT_EXPECTED_BEHAVIOR,
                literal=text,
                normalized_value=text.casefold(),
                source_evidence_ids=["ev-1"],
                source_reference="test:description",
                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                authority_class=AuthorityClass.CUSTOMER_REQUEST,
                authoritative=True,
            )
        ],
    )


def _render(gates):
    scope = ScopeResolution()
    facts = _facts("The export job writes a completion marker.")
    dispositions = CANONICAL_REASONING_SERVICE.classify_coverage(
        facts, [], [], [], scope, []
    )
    resolution = CANONICAL_REASONING_SERVICE.resolve_acceptance_contract_with_trace(
        facts, dispositions, []
    )
    candidates = resolution.candidates
    _gate, promotions = CANONICAL_REASONING_SERVICE.acceptance_promotion_gate(
        candidates, facts, scope, dispositions
    )
    return CANONICAL_REASONING_SERVICE.render_final_plan(
        _render_request(), facts, scope, CanonicalBehaviorModel(), [], [],
        [], dispositions, candidates, promotions, gates,
        acceptance_resolution=resolution,
    )


def _render_request():
    from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

    return CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99104",
        tenant_id="tenant_ux1",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def test_blocked_review_completed_render_distinction() -> None:
    # A. BLOCKED: gate blocked -> compact clarification document.
    blocked_gate = GateDecision(
        gate="AcceptancePromotionGate",
        status=GateStatus.BLOCKED,
        failures=["No supported acceptance-contract candidate is available."],
    )
    _plan, blocked_render = _render([blocked_gate])
    assert "## Generation status" in blocked_render
    assert "Proposed acceptance contract" not in blocked_render
    assert "Coverage gate result" not in blocked_render

    # C. non-blocked: normal canonical sections render.
    passing_gate = GateDecision(
        gate="AcceptancePromotionGate", status=GateStatus.PASSED
    )
    _plan, normal_render = _render([passing_gate])
    assert "## Coverage gate result" in normal_render
    assert "Generation status" not in normal_render


# ---------------------------------------------------------------------------
# CLI presentation parity (spec section 15)
# ---------------------------------------------------------------------------


def test_cli_selects_canonical_text_and_never_falls_back_to_draft(
    capsys,
) -> None:
    import run_test_plan_pipeline as cli

    result = {
        "qe_review_package": {
            "canonical_result": {"plan_markdown": "CANONICAL PLAN TEXT"}
        },
        "draft_test_plan_markdown": "DRAFT TEXT - NON CANONICAL",
    }
    assert cli._select_plan_text(result) == "CANONICAL PLAN TEXT"
    # No side-channel write inside selection (single write happens in main).
    assert capsys.readouterr().out == ""

    with pytest.raises(SystemExit):
        cli._select_plan_text(
            {
                "qe_review_package": {"canonical_result": {}},
                "draft_test_plan_markdown": "DRAFT TEXT - NON CANONICAL",
            }
        )


# ---------------------------------------------------------------------------
# Clarification binding/resume from blocked output (spec section 17)
# ---------------------------------------------------------------------------


def test_blocked_questions_keep_canonical_identity_for_resume() -> None:
    result = _runtime_run(
        "The old dialog gives a colored hint that the log should be checked. "
        "There is no easy way to see processing problems before publishing."
    )
    assert result.status == "blocked"
    questions = result.output_payload["missing_questions"]
    assert questions
    rendered = result.rendered_output
    # Every unresolved blocking question visible in human output is the
    # canonical question text (no presentation rewrite), so its ID/revision
    # stays bound for clarification resume.
    decisions_section = rendered.split("## Open product decisions")[-1]
    for question in questions:
        if question["blocking"]:
            assert question["question"] in decisions_section
    # P1 admission binds the same canonical question id.
    from app.core.schemas_canonical_test_plan_runtime import MissingQuestion

    target = next(row for row in questions if row["blocking"])
    mq = MissingQuestion(
        **{k: v for k, v in target.items() if k in MissingQuestion.model_fields}
    )
    admitted, errors = CANONICAL_REASONING_SERVICE.admit_clarifications(
        [
            {
                "question_ref": target["question_id"],
                "question_revision": target["question_revision"],
                "answer": "The status hint is shown before publishing starts.",
                "answer_classification": "PRODUCT_DECISION",
                "provided_by": "qe-reviewer",
                "authority_role": "CONFIRMED_PRODUCT_DECISION",
            }
        ],
        [mq],
    )
    assert not errors
    assert admitted and admitted[0].status.value == "ADMITTED"
