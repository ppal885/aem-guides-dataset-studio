"""Behavioral coverage expansion: broad discovery, strict promotion.

The skill was strong at evidence *authority* but too literal during coverage
*discovery*: it captured the explicit ask and silently missed the adjacent
behaviors that can regress with it (where a value comes from, what happens when
it is absent, whether it can be supplied indirectly, what a move or rename does
to it, whether it goes stale, and whether every consumer surface agrees).

These tests prove the expansion is generic - derived from requirement shape, not
from a feature keyword list - and that widening discovery never widens
acceptance.
"""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_STAGE_ORDER,
    CanonicalRuntimeStage,
    ClosureDisposition,
    CoverageExpansionAxis,
    CoverageExpansionTrigger,
    GenerationProfile,
    ResearchRequirement,
    RuntimeEntryPoint,
    SemanticDimension,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME

TENANT = "tenant-alpha"


def _run(packet: dict[str, object]):
    jira_key = str(packet["jira_key"])
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key=jira_key,
        tenant_id=TENANT,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request,
        packet=packet,
    )


def _expansion(result) -> dict[str, object]:
    return result.output_payload["behavioral_coverage_expansion"]


def _axes(result) -> set[str]:
    return {row["axis"] for row in _expansion(result)["candidates"]}


def _activated_dimensions(result) -> set[str]:
    return {
        dimension
        for row in _expansion(result)["candidates"]
        if row["material"]
        for dimension in row["dimensions"]
    }


# --------------------------------------------------------------------------
# Fixtures from three unrelated behavior families.  None of them shares a
# product vocabulary with another, so a rule that only fires for one of them is
# feature-specific rather than generic.
# --------------------------------------------------------------------------


def _ordering_and_reporting_packet() -> dict[str, object]:
    """GUIDES-11947 shape: a displayed value and an exported value of one thing."""

    return {
        "jira_key": "GUIDES-11947",
        "issue": {
            "issue_key": "GUIDES-11947",
            "summary": "Displayed topic order does not match the exported report order",
            "description": (
                "The console column displays the topic title, while the "
                "downloaded CSV report lists the same topics sorted by "
                "filename. The displayed order should match the exported "
                "order."
            ),
        },
    }


def _reference_resolution_packet() -> dict[str, object]:
    return {
        "jira_key": "GUIDES-22001",
        "issue": {
            "issue_key": "GUIDES-22001",
            "summary": "Reused content is not resolved in the generated output",
            "description": (
                "A referenced fragment is not resolved when the linked source "
                "is moved or renamed, so the output keeps the stale text."
            ),
        },
    }


def _configuration_state_packet() -> dict[str, object]:
    return {
        "jira_key": "GUIDES-33002",
        "issue": {
            "issue_key": "GUIDES-33002",
            "summary": "Preset setting does not change the stored status",
            "description": (
                "Changing the profile configuration does not update the "
                "persisted status property for the job."
            ),
        },
    }


# --------------------------------------------------------------------------
# 1. The stage exists in the locked pipeline and runs before closure.
# --------------------------------------------------------------------------


def test_expander_is_a_first_class_stage_that_runs_before_closure() -> None:
    order = list(CANONICAL_STAGE_ORDER)
    assert CanonicalRuntimeStage.BEHAVIORAL_COVERAGE_EXPANDER in order
    assert order.index(
        CanonicalRuntimeStage.BEHAVIOR_MODEL_BUILDER
    ) < order.index(CanonicalRuntimeStage.BEHAVIORAL_COVERAGE_EXPANDER) < order.index(
        CanonicalRuntimeStage.SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER
    )
    # It is deliberately not a *Gate: the posting boundary derives its required
    # gate set from stage names ending in "Gate".
    assert not CanonicalRuntimeStage.BEHAVIORAL_COVERAGE_EXPANDER.value.endswith("Gate")

    result = _run(_ordering_and_reporting_packet())
    assert [row.stage for row in result.trace.stage_trace] == order


# --------------------------------------------------------------------------
# 2. The explicit ask is still found (expansion adds, never replaces).
# --------------------------------------------------------------------------


def test_explicit_requirement_is_still_covered_after_expansion() -> None:
    result = _run(_ordering_and_reporting_packet())
    closure = result.output_payload["semantic_closure"]
    dimensions = {row["dimension"] for row in closure}
    # The stated ordering/parity ask keeps its own dimensions.
    assert SemanticDimension.CROSS_SURFACE_SYNC.value in dimensions
    assert SemanticDimension.POSITIVE_STATE.value in dimensions
    assert result.output_payload["contract_facts"]["facts"]


# --------------------------------------------------------------------------
# 3. Adjacent behaviors are discovered generically across three families.
# --------------------------------------------------------------------------


def test_ordering_ticket_discovers_provenance_resolution_identity_and_parity() -> None:
    result = _run(_ordering_and_reporting_packet())
    expansion = _expansion(result)

    assert CoverageExpansionTrigger.DISPLAYED_VALUE.value in expansion["triggers"]
    assert CoverageExpansionTrigger.EXPORTED_VALUE.value in expansion["triggers"]
    assert CoverageExpansionTrigger.ORDERING_RULE.value in expansion["triggers"]
    # Two readings of one value were derived compositionally, not from a
    # hardcoded list of AEM surfaces.
    assert (
        CoverageExpansionTrigger.MULTIPLE_CONSUMER_SURFACES.value
        in expansion["triggers"]
    )

    # These are exactly the dimensions the literal reading used to miss.
    assert {
        CoverageExpansionAxis.VALUE_PROVENANCE.value,
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION.value,
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE.value,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS.value,
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY.value,
        CoverageExpansionAxis.FALLBACK_AND_ABSENCE.value,
    } <= _axes(result)


def test_reference_resolution_ticket_discovers_broken_resolution_and_identity() -> None:
    result = _run(_reference_resolution_packet())
    expansion = _expansion(result)

    assert CoverageExpansionTrigger.RESOLVED_REFERENCE.value in expansion["triggers"]
    assert CoverageExpansionTrigger.IDENTITY_REFERENCE.value in expansion["triggers"]
    assert {
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION.value,
        CoverageExpansionAxis.NEGATIVE_AND_BROKEN_RESOLUTION.value,
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE.value,
    } <= _axes(result)
    assert SemanticDimension.BROKEN_RESOLUTION.value in _activated_dimensions(result)


def test_configuration_state_ticket_discovers_scope_and_freshness() -> None:
    result = _run(_configuration_state_packet())
    expansion = _expansion(result)

    assert (
        CoverageExpansionTrigger.CONFIGURATION_DEPENDENCY.value
        in expansion["triggers"]
    )
    assert CoverageExpansionTrigger.PERSISTED_VALUE.value in expansion["triggers"]
    assert CoverageExpansionTrigger.STATE_TRANSITION.value in expansion["triggers"]
    assert {
        CoverageExpansionAxis.CONTEXT_AND_SCOPE.value,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS.value,
        CoverageExpansionAxis.VALUE_PROVENANCE.value,
    } <= _axes(result)


def test_expansion_is_requirement_shaped_not_feature_keyed() -> None:
    """The same axes must be reachable from unrelated product vocabularies."""

    ordering = _axes(_run(_ordering_and_reporting_packet()))
    reference = _axes(_run(_reference_resolution_packet()))
    configuration = _axes(_run(_configuration_state_packet()))

    # No family produces the identical axis set - discovery reacts to the
    # requirement, not to a constant.
    assert ordering != reference
    assert reference != configuration
    # Yet a shared axis is reachable from all three, so the rules are not
    # per-feature branches.
    assert CoverageExpansionAxis.MUTATION_AND_FRESHNESS.value in ordering & reference & configuration


# --------------------------------------------------------------------------
# 4. Nothing discovered may silently disappear.
# --------------------------------------------------------------------------


def test_every_activated_dimension_is_dispositioned_by_closure() -> None:
    for packet in (
        _ordering_and_reporting_packet(),
        _reference_resolution_packet(),
        _configuration_state_packet(),
    ):
        result = _run(packet)
        closure = result.output_payload["semantic_closure"]
        decided = {row["dimension"] for row in closure}
        assert _activated_dimensions(result) <= decided, packet["jira_key"]

        # And every closure row carries an explicit terminal disposition.
        assert all(
            row["disposition"] in {row.value for row in ClosureDisposition}
            for row in closure
        )


def test_activated_dimension_cannot_be_universally_not_applicable() -> None:
    """The no-silent-loss check inside BehavioralCompletenessGate."""

    for packet in (
        _ordering_and_reporting_packet(),
        _reference_resolution_packet(),
        _configuration_state_packet(),
    ):
        result = _run(packet)
        live = {
            row["dimension"]
            for row in result.output_payload["semantic_closure"]
            if row["applicability"] != "NOT_APPLICABLE"
        }
        assert _activated_dimensions(result) <= live, packet["jira_key"]

        gate = next(
            row
            for row in result.output_payload["gate_decisions"]
            if row["gate"] == CanonicalRuntimeStage.BEHAVIORAL_COMPLETENESS_GATE.value
        )
        assert gate["status"] == "PASSED", gate["failures"]


# --------------------------------------------------------------------------
# 5. Discovery is not acceptance.
# --------------------------------------------------------------------------


def test_discovery_never_promotes_an_acceptance_criterion() -> None:
    result = _run(_ordering_and_reporting_packet())
    promoted = {
        row["candidate_id"]
        for row in result.output_payload["promotion_decisions"]
        if row["status"] == "PROMOTED"
    }
    discovered = {row["candidate_id"] for row in _expansion(result)["candidates"]}
    assert discovered
    # Expansion candidate ids live in their own namespace and can never appear
    # as a promoted acceptance candidate.
    assert all(row.startswith("covexp:") for row in discovered)
    assert not (discovered & promoted)


def test_missing_evidence_routes_to_research_rather_than_an_assumed_answer() -> None:
    result = _run(_reference_resolution_packet())
    activated = _activated_dimensions(result)
    unresolved = {
        row["dimension"]
        for row in result.output_payload["semantic_closure"]
        if row["disposition"] == ClosureDisposition.UNRESOLVED_AND_EXPOSED.value
    }
    assert activated & unresolved

    questioned = {
        row["dimension"] for row in result.output_payload["missing_questions"]
    }
    assert (activated & unresolved) <= questioned

    # Unresolved discovery becomes a research obligation, never an inferred
    # product answer.
    classifications = result.output_payload["research_requirements"]
    assert classifications
    assert any(
        row["research_requirement"] != ResearchRequirement.NONE.value
        for row in classifications
    )


# --------------------------------------------------------------------------
# 6. Distinct contracts are not merged; identical ones are not duplicated.
# --------------------------------------------------------------------------


def test_identity_change_and_lifecycle_stay_separate_contracts() -> None:
    result = _run(_reference_resolution_packet())
    activated = _activated_dimensions(result)
    # Moving or renaming the underlying item is a different product behavior
    # than an ordinary lifecycle state change, so they get separate closure
    # rows and separate questions.
    assert SemanticDimension.IDENTITY_CHANGE.value in activated
    assert SemanticDimension.LIFECYCLE.value in activated

    closure = result.output_payload["semantic_closure"]
    identity = [
        row
        for row in closure
        if row["dimension"] == SemanticDimension.IDENTITY_CHANGE.value
    ]
    lifecycle = [
        row for row in closure if row["dimension"] == SemanticDimension.LIFECYCLE.value
    ]
    assert identity and lifecycle
    assert {row["entity"] for row in identity} == {row["entity"] for row in lifecycle}


def test_candidates_are_deduplicated_and_deterministic() -> None:
    first = _expansion(_run(_ordering_and_reporting_packet()))
    second = _expansion(_run(_ordering_and_reporting_packet()))
    assert first == second

    ids = [row["candidate_id"] for row in first["candidates"]]
    assert len(ids) == len(set(ids))
    # One candidate per (axis, subject) pair - discovery is bounded.
    pairs = [(row["axis"], row["subject"]) for row in first["candidates"]]
    assert len(pairs) == len(set(pairs))


# --------------------------------------------------------------------------
# 7. GUIDES-11947 regression: the exact miss that motivated the change.
# --------------------------------------------------------------------------


def test_guides_11947_no_longer_stops_at_ordering_and_parity() -> None:
    """Regression fixture.

    The literal reading produced only map-ordering plus CSV parity and silently
    dropped title resolution, value provenance, asset move/rename, and
    staleness.  This test fails if coverage ever narrows back to that pair.
    """

    result = _run(_ordering_and_reporting_packet())
    axes = _axes(result)

    literal_only = {
        CoverageExpansionAxis.CONSUMER_SURFACE_PARITY.value,
        CoverageExpansionAxis.CONTEXT_AND_SCOPE.value,
    }
    assert axes - literal_only, "coverage collapsed back to the literal reading"

    missed_before = {
        CoverageExpansionAxis.VALUE_PROVENANCE.value,
        CoverageExpansionAxis.VALUE_RESOLUTION_OR_INDIRECTION.value,
        CoverageExpansionAxis.IDENTITY_AND_LIFECYCLE.value,
        CoverageExpansionAxis.MUTATION_AND_FRESHNESS.value,
    }
    assert missed_before <= axes

    activated = _activated_dimensions(result)
    assert {
        SemanticDimension.VALUE_PROVENANCE.value,
        SemanticDimension.VALUE_RESOLUTION_OR_INDIRECTION.value,
        SemanticDimension.IDENTITY_CHANGE.value,
        SemanticDimension.MUTATION_FRESHNESS.value,
        SemanticDimension.CROSS_SURFACE_SYNC.value,
        SemanticDimension.ALTERNATE_REPRESENTATION.value,
    } <= activated


# --------------------------------------------------------------------------
# 8. Human authority and existing question quality are untouched.
# --------------------------------------------------------------------------


def test_human_accepted_contract_keeps_its_authority_through_expansion() -> None:
    packet = {
        "jira_key": "GUIDES-44003",
        "issue": {
            "issue_key": "GUIDES-44003",
            "summary": "Job completion status",
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "When the job finishes, display status Ready and keep Batch size 250."
            ],
        },
    }
    result = _run(packet)
    assert _expansion(result)["candidates"]

    accepted = [
        row
        for row in result.output_payload["acceptance_candidates"]
        if "Batch size 250" in row["statement"]
    ]
    assert len(accepted) == 1
    assert accepted[0]["accepted_human_contract"] is True
    assert any(
        row["candidate_id"] == accepted[0]["candidate_id"]
        and row["status"] == "PROMOTED"
        for row in result.output_payload["promotion_decisions"]
    )
    # Broader discovery must not block an explicitly accepted contract.
    assert result.status == "completed"


def test_expansion_questions_still_satisfy_the_question_quality_contract() -> None:
    for packet in (
        _ordering_and_reporting_packet(),
        _reference_resolution_packet(),
        _configuration_state_packet(),
    ):
        result = _run(packet)
        quality = result.output_payload["missing_question_quality"]
        rejected = [
            row for row in quality["decisions"] if row["disposition"] != "ACCEPTED"
        ]
        assert not rejected, (packet["jira_key"], rejected)
        assert not [
            row
            for row in quality["family_satisfaction"]
            if row["status"] == "UNSATISFIED"
        ], packet["jira_key"]


def test_every_semantic_dimension_has_a_usable_question_contract() -> None:
    """Hardening for the latent gap this expansion exposed three times.

    Adding a SemanticDimension member silently breaks question generation in
    three separate direct-index tables. A missing keyword or question entry is a
    KeyError; a question whose wording does not intersect its mapped relation's
    terms is worse, because the question is generated and then rejected as
    NO_RELATIONSHIP, which strands the family as UNSATISFIED without a visible
    cause. Assert the contract for every member so the next dimension cannot
    reintroduce it.
    """

    from app.services.canonical_missing_question_service import (
        _PRODUCT_ASSUMPTION_RE,
        _RELATION_TERMS,
        _expected_relation,
        _tokens,
    )
    from app.services.canonical_test_plan_reasoning_service import (
        _DIMENSION_KEYWORDS,
        _QUESTION_TEXT,
    )

    for dimension in SemanticDimension:
        assert dimension in _DIMENSION_KEYWORDS, dimension.value
        assert dimension in _QUESTION_TEXT, dimension.value

        text = _QUESTION_TEXT[dimension].format(entity="the affected entity")

        # A question must not presuppose the product decision it is asking about.
        assert not _PRODUCT_ASSUMPTION_RE.search(text), (dimension.value, text)

        # The question must be recognisable as being about its own relation,
        # whether that relation is mapped explicitly or falls through to the
        # DEFINED_BY default.
        relation = _expected_relation(dimension)
        terms = _RELATION_TERMS.get(relation, frozenset())
        if terms:
            assert _tokens(text) & set(terms), (
                dimension.value,
                relation.value,
                text,
                sorted(terms),
            )