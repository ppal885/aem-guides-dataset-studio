"""D1-d: applicable regression coverage reaches the flat acceptance contract.

The acceptance contract is flat: applicable behavior discovered by research,
code, docs, or adjacent/regression reasoning belongs INSIDE the criteria it
qualifies - as a sub-point - never parked in a separate QE-regression lane the
renderer never shows.  These tests pin that fusion and its guards.
"""

from app.core.schemas_canonical_test_plan_runtime import (
    AcceptanceCandidate,
    AcceptancePromotionDecision,
    AcceptanceSubPointKind,
    ContractFactSet,
    ContractMode,
    CoverageDisposition,
    CoverageDispositionRecord,
    PromotionStatus,
)
from app.services.canonical_test_plan_reasoning_service import (
    CanonicalTestPlanReasoningService,
)

PRIMARY = (
    "The Topic List report shows topics in the same order as they appear "
    "in the map."
)


def _facts() -> ContractFactSet:
    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT
    )


def _promoted_candidate() -> tuple[
    list[AcceptanceCandidate], list[AcceptancePromotionDecision]
]:
    candidate = AcceptanceCandidate(
        statement=PRIMARY,
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        in_scope=True,
        observable=True,
    )
    promotion = AcceptancePromotionDecision(
        candidate_id=candidate.candidate_id,
        status=PromotionStatus.PROMOTED,
        resulting_disposition=CoverageDisposition.PROPOSED_ACCEPTANCE_CONTRACT,
        authority_supported=True,
        scope_established=True,
        observable=True,
        exact_values_supported=True,
    )
    return [candidate], [promotion]


def _regression_row(
    candidate: str,
    *,
    priority: str = "P1",
    applicability: str = "APPLICABLE",
    coverage_class: str = "QE_REGRESSION",
) -> CoverageDispositionRecord:
    disposition = (
        CoverageDisposition.TECHNICAL_NOTE
        if coverage_class == "INVESTIGATION"
        else CoverageDisposition.SEMANTIC_REGRESSION
    )
    return CoverageDispositionRecord(
        candidate=candidate,
        disposition=disposition,
        rationale="Materially related regression behavior.",
        priority=priority,
        coverage_class=coverage_class,
        applicability=applicability,
        contract_type="POSITIVE",
    )


def _write(dispositions: list[CoverageDispositionRecord]):
    candidates, promotions = _promoted_candidate()
    service = CanonicalTestPlanReasoningService()
    return service.write_acceptance_criteria(
        candidates, promotions, _facts(), dispositions
    )


def _sub_texts(written) -> list[str]:
    return [
        sub.text
        for criterion in written
        for sub in criterion.sub_points
        if sub.kind == AcceptanceSubPointKind.CONFIRMED_VARIANT
    ]


def test_applicable_regression_coverage_attaches_as_a_contract_sub_point():
    row = _regression_row(
        "Sorting by the Title and File Name column headers keeps working "
        "in the Topic List report."
    )

    written = _write([row])

    subs = _sub_texts(written)
    assert subs, (
        "applicable QE_REGRESSION coverage never reached the acceptance "
        "contract; it was dropped with the regression lane"
    )
    assert any("Title and File Name" in text for text in subs)
    # It qualifies the outcome; it never becomes an acceptance outcome itself.
    assert len(written) == 1
    host = written[0]
    assert host.outcome.startswith("The Topic List report shows topics")
    assert row.disposition_id in host.source_disposition_ids


def test_bookkeeping_filler_never_becomes_acceptance_coverage():
    row = _regression_row(
        "HIERARCHY: internal evidence recorded for 12 closure records "
        "(see trace)"
    )

    written = _write([row])

    assert not _sub_texts(written), (
        "a bookkeeping pointer is not testable behavior and must never "
        "enter the acceptance contract"
    )
    assert len(written) == 1


def test_unrelated_regression_coverage_is_not_force_adopted():
    row = _regression_row(
        "Translation project creation keeps honouring the selected "
        "language folders."
    )

    written = _write([row])

    assert not _sub_texts(written)
    # It must not invent a parent criterion for itself either.
    assert len(written) == 1
    assert "Translation" not in written[0].outcome


def test_only_applicable_p1_regression_coverage_is_fused():
    rows = [
        _regression_row(
            "Sorting by the Title column header keeps working in the "
            "Topic List report.",
            applicability="NOT_APPLICABLE",
        ),
        _regression_row(
            "Filtering the Topic List report by Author keeps working.",
            priority="SUPPORTING",
        ),
        _regression_row(
            "The Topic List report keeps its displayed topic count.",
            priority="SUPPORTING",
            coverage_class="INVESTIGATION",
        ),
    ]

    written = _write(rows)

    assert not _sub_texts(written), (
        "non-applicable, non-P1, or investigation-class coverage must not "
        "be presented as confirmed acceptance behavior"
    )


def test_fused_sub_points_are_bounded_per_criterion():
    rows = [
        _regression_row(
            f"The Topic List report keeps behavior number {index} intact "
            "for map order."
        )
        for index in range(9)
    ]

    written = _write(rows)

    assert len(_sub_texts(written)) <= 4, (
        "the contract must stay scannable; the coverage matrix carries the "
        "long tail"
    )
