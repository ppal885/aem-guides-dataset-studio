"""Reusable per-question research-routing contract.

The canonical runtime routes every planned question through this router, and a
later Question Planner invokes the same contract per material question without
another architectural rewrite:

    router = QUESTION_RESEARCH_ROUTER
    request = ResearchRoutingRequest(
        question_id=...,            # binds to the planned question
        research_need=...,          # optional explicit route declaration
        required_source_type=...,   # optional mandated sources
        product_context=...,        # product / versions / deployment
        applicability=...,          # APPLICABLE / NOT_APPLICABLE / UNRESOLVED
    )
    requirement = router.classify(request, question=question, contract_mode=...)
    research = router.resolve(requirement, retrievals=..., hypotheses=...)

The contract is deliberately not ticket-scoped: classification and resolution
take one question at a time, and every ticket-level caller (the runtime's
``ResearchRequirementClassifier`` stage today) is a thin batch loop over the
per-question contract.

Deterministic only: no LLM, no provider calls, no source-authority changes.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.core.schemas_canonical_test_plan_runtime import (
    ApplicabilityState,
    AuthoritySubject,
    BehaviorHypothesis,
    CanonicalEvidenceBundle,
    ContractMode,
    DirectedRetrievalRecord,
    EvidenceSourceType,
    GitHubImplementationVerificationHandoff,
    HypothesisState,
    InvestigationMateriality,
    MissingQuestion,
    PatternLookupRuntimeStatus,
    QuestionEvidenceProvider,
    QuestionResearchRecord,
    ResearchRequirement,
    ResearchRequirementRecord,
    ResearchRoutingRequest,
    ResearchStatus,
    ResearchWorkerResult,
    ResearchWorkerRole,
    ResearchWorkerStatus,
)


# Mandatory research routing.  The current Jira authority (description, accepted
# ACs, product decisions, comments) is evidence, not research: a question that
# only needs that authority requires no external research.  Every other source
# category names research that must actually execute before coverage may
# finalize a material question.
RESEARCH_CATEGORY_JIRA_AUTHORITY = "JIRA_AUTHORITY"
RESEARCH_CATEGORY_DOCUMENTATION = "DOCUMENTATION"
RESEARCH_CATEGORY_IMPLEMENTATION = "IMPLEMENTATION"
RESEARCH_CATEGORY_HISTORICAL = "HISTORICAL"

JIRA_AUTHORITY_RESEARCH_SOURCES = {
    EvidenceSourceType.JIRA_DESCRIPTION,
    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
    EvidenceSourceType.JIRA_COMMENT,
    EvidenceSourceType.JIRA_ATTACHMENT,
    EvidenceSourceType.CURRENT_JIRA,
    EvidenceSourceType.ACCEPTED_UAC,
    EvidenceSourceType.PRODUCT_DECISION,
    EvidenceSourceType.ENGINEERING_DECISION,
    EvidenceSourceType.CUSTOMER_REQUEST,
    EvidenceSourceType.DRAFT_UAC,
    EvidenceSourceType.CUSTOMER_WORKFLOW,
    EvidenceSourceType.BUSINESS_IMPACT,
    EvidenceSourceType.USER_FEEDBACK,
    EvidenceSourceType.WORKAROUND,
    EvidenceSourceType.SCALE_SIGNAL,
}
DOCUMENTATION_RESEARCH_SOURCES = {
    EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
    EvidenceSourceType.DITA_SPECIFICATION,
    EvidenceSourceType.DITA_OT_DOCUMENTATION,
    EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
    EvidenceSourceType.UI_OBSERVATION,
    EvidenceSourceType.OBSERVED_UI_FLOW,
    EvidenceSourceType.SCREENSHOT_REPRODUCTION,
}
IMPLEMENTATION_RESEARCH_SOURCES = {
    EvidenceSourceType.CURRENT_CODE,
    EvidenceSourceType.CURRENT_PR,
    EvidenceSourceType.IMPLEMENTATION_DIFF,
    EvidenceSourceType.CODE_DIFF,
    EvidenceSourceType.EXISTING_AUTOMATION,
    EvidenceSourceType.EVIDENCE_GRAPH_LEAF,
}
HISTORICAL_RESEARCH_SOURCES = {
    EvidenceSourceType.HISTORICAL_JIRA,
    EvidenceSourceType.LINKED_JIRA,
}


def research_source_category(source_type: EvidenceSourceType) -> str:
    if source_type in JIRA_AUTHORITY_RESEARCH_SOURCES:
        return RESEARCH_CATEGORY_JIRA_AUTHORITY
    if source_type in DOCUMENTATION_RESEARCH_SOURCES:
        return RESEARCH_CATEGORY_DOCUMENTATION
    if source_type in IMPLEMENTATION_RESEARCH_SOURCES:
        return RESEARCH_CATEGORY_IMPLEMENTATION
    if source_type in HISTORICAL_RESEARCH_SOURCES:
        return RESEARCH_CATEGORY_HISTORICAL
    # Uncategorised sources can never satisfy a named research route; they push
    # the question to MULTI_SOURCE so a Human reviews the routing decision.
    return f"OTHER:{source_type.value}"


def research_provider_category(
    provider: QuestionEvidenceProvider,
) -> str | None:
    return {
        QuestionEvidenceProvider.CURRENT_EVIDENCE: RESEARCH_CATEGORY_JIRA_AUTHORITY,
        QuestionEvidenceProvider.HUMAN_PRODUCT: RESEARCH_CATEGORY_JIRA_AUTHORITY,
        QuestionEvidenceProvider.DITA_SPECIFICATION: RESEARCH_CATEGORY_DOCUMENTATION,
        QuestionEvidenceProvider.DITA_OT: RESEARCH_CATEGORY_DOCUMENTATION,
        QuestionEvidenceProvider.EXPERIENCE_LEAGUE: RESEARCH_CATEGORY_DOCUMENTATION,
        QuestionEvidenceProvider.FLUFFYJAWS: RESEARCH_CATEGORY_DOCUMENTATION,
        QuestionEvidenceProvider.GITHUB_MCP: RESEARCH_CATEGORY_IMPLEMENTATION,
        QuestionEvidenceProvider.CONFIGURATION_OR_TESTS: (
            RESEARCH_CATEGORY_IMPLEMENTATION
        ),
        QuestionEvidenceProvider.PATTERN_MCP_DISCOVERY: RESEARCH_CATEGORY_HISTORICAL,
    }.get(provider)


REQUIREMENT_CATEGORY_SOURCES: dict[str, frozenset[EvidenceSourceType]] = {
    RESEARCH_CATEGORY_DOCUMENTATION: frozenset(DOCUMENTATION_RESEARCH_SOURCES),
    RESEARCH_CATEGORY_IMPLEMENTATION: frozenset(IMPLEMENTATION_RESEARCH_SOURCES),
    RESEARCH_CATEGORY_HISTORICAL: frozenset(HISTORICAL_RESEARCH_SOURCES),
}

MATERIAL_RESEARCH_MATERIALITY = {
    InvestigationMateriality.P0,
    InvestigationMateriality.P1,
}

_REQUIREMENT_DEFAULT_SOURCES: dict[ResearchRequirement, frozenset[EvidenceSourceType]] = {
    ResearchRequirement.DOCUMENTATION: frozenset(DOCUMENTATION_RESEARCH_SOURCES),
    ResearchRequirement.IMPLEMENTATION: frozenset(IMPLEMENTATION_RESEARCH_SOURCES),
    ResearchRequirement.HISTORICAL: frozenset(HISTORICAL_RESEARCH_SOURCES),
    ResearchRequirement.DOCUMENTATION_AND_IMPLEMENTATION: frozenset(
        DOCUMENTATION_RESEARCH_SOURCES | IMPLEMENTATION_RESEARCH_SOURCES
    ),
    ResearchRequirement.MULTI_SOURCE: frozenset(
        DOCUMENTATION_RESEARCH_SOURCES
        | IMPLEMENTATION_RESEARCH_SOURCES
        | HISTORICAL_RESEARCH_SOURCES
    ),
}


class QuestionResearchRouter:
    """Per-question research-routing contract.

    ``classify`` turns one ``ResearchRoutingRequest`` into a
    ``ResearchRequirementRecord``; ``resolve`` turns that requirement plus the
    executed research into a terminal ``QuestionResearchRecord``.  Both are
    pure functions of their inputs so any caller (runtime stage today,
    Question Planner later) gets the same routing decision for the same
    question.
    """

    def build_request(
        self,
        question: MissingQuestion,
        *,
        research_need: ResearchRequirement | None = None,
        required_source_type: Iterable[EvidenceSourceType] = (),
        product_context: object = None,
        applicability: ApplicabilityState = ApplicabilityState.APPLICABLE,
    ) -> ResearchRoutingRequest:
        """Bind the routing contract to a planned question."""

        return ResearchRoutingRequest(
            question_id=question.question_id,
            research_need=research_need,
            required_source_type=list(required_source_type),
            product_context=product_context,  # type: ignore[arg-type]
            applicability=applicability,
        )

    def classify(
        self,
        request: ResearchRoutingRequest,
        *,
        question: MissingQuestion | None = None,
        contract_mode: ContractMode = ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        material: bool | None = None,
    ) -> ResearchRequirementRecord:
        """Classify the mandatory research route of one question.

        Source authority is not changed: classification only names the research
        the question's evidence path (or the caller's explicit ``research_need``)
        already requires.
        """

        if question is not None and question.question_id != request.question_id:
            raise ValueError(
                "routing request and planned question disagree on question_id"
            )
        if question is None and request.research_need is None:
            raise ValueError(
                "research routing needs the planned question or an explicit "
                "research_need"
            )
        subject = question.authority_subject if question is not None else None
        blocking = bool(question.blocking) if question is not None else False
        if material is None:
            material = (
                blocking or question.materiality in MATERIAL_RESEARCH_MATERIALITY
                if question is not None
                else True
            )
        material = bool(material) and (
            request.applicability != ApplicabilityState.NOT_APPLICABLE
        )
        carried = {
            "routing_request_id": request.request_id,
            "product_context": request.product_context,
            "applicability": request.applicability,
        }

        if request.research_need is not None:
            requirement = request.research_need
            if requirement == ResearchRequirement.NONE:
                return ResearchRequirementRecord(
                    question_id=request.question_id,
                    research_requirement=requirement,
                    material=material,
                    blocking=blocking,
                    rationale=(
                        "The routing request declared that no external research "
                        "is required for this question."
                    ),
                    **carried,
                )
            required_sources = list(request.required_source_type)
            if not required_sources and question is not None:
                required_sources = [
                    source_type
                    for source_type in question.target_source_types
                    if research_source_category(source_type)
                    != RESEARCH_CATEGORY_JIRA_AUTHORITY
                ]
            if not required_sources:
                required_sources = sorted(
                    _REQUIREMENT_DEFAULT_SOURCES[requirement],
                    key=lambda row: row.value,
                )
            return ResearchRequirementRecord(
                question_id=request.question_id,
                research_requirement=requirement,
                material=material,
                blocking=blocking,
                required_source_types=required_sources,
                rationale=(
                    "The routing request declared "
                    f"{requirement.value.lower().replace('_', ' ')} research; "
                    "coverage may not finalize this question until that research "
                    "resolves."
                ),
                **carried,
            )

        assert question is not None  # guaranteed by the guard above
        if (
            contract_mode == ContractMode.HUMAN_ACCEPTED_CONTRACT
            and subject == AuthoritySubject.PRODUCT_CONTRACT
        ):
            return ResearchRequirementRecord(
                question_id=request.question_id,
                research_requirement=ResearchRequirement.NONE,
                material=material,
                blocking=blocking,
                rationale=(
                    "The Human Accepted contract is the acceptance authority; "
                    "Jira authority alone answers this product-contract "
                    "question, so no documentation, implementation, or "
                    "historical research is required."
                ),
                **carried,
            )
        categories = {
            research_source_category(source_type)
            for source_type in question.target_source_types
        }
        provider_category = research_provider_category(question.preferred_provider)
        if provider_category is not None:
            categories.add(provider_category)
        categories.discard(RESEARCH_CATEGORY_JIRA_AUTHORITY)
        if not categories:
            return ResearchRequirementRecord(
                question_id=request.question_id,
                research_requirement=ResearchRequirement.NONE,
                material=material,
                blocking=blocking,
                rationale=(
                    "The question's evidence path targets only current Jira "
                    "authority; no external research is required."
                ),
                **carried,
            )
        if categories == {RESEARCH_CATEGORY_DOCUMENTATION}:
            requirement = ResearchRequirement.DOCUMENTATION
        elif categories == {RESEARCH_CATEGORY_IMPLEMENTATION}:
            requirement = ResearchRequirement.IMPLEMENTATION
        elif categories == {RESEARCH_CATEGORY_HISTORICAL}:
            requirement = ResearchRequirement.HISTORICAL
        elif categories == {
            RESEARCH_CATEGORY_DOCUMENTATION,
            RESEARCH_CATEGORY_IMPLEMENTATION,
        }:
            requirement = ResearchRequirement.DOCUMENTATION_AND_IMPLEMENTATION
        else:
            requirement = ResearchRequirement.MULTI_SOURCE
        required_sources = sorted(
            {
                source_type
                for source_type in question.target_source_types
                if research_source_category(source_type) in categories
            },
            key=lambda row: row.value,
        )
        covered = {
            research_source_category(source_type) for source_type in required_sources
        }
        for category in sorted(categories - covered):
            required_sources.extend(
                sorted(
                    REQUIREMENT_CATEGORY_SOURCES.get(category, frozenset()),
                    key=lambda row: row.value,
                )
            )
        return ResearchRequirementRecord(
            question_id=request.question_id,
            research_requirement=requirement,
            material=material,
            blocking=blocking,
            required_source_types=required_sources,
            rationale=(
                "The question's evidence path requires "
                f"{requirement.value.lower().replace('_', ' ')} research "
                "before coverage may finalize it."
            ),
            **carried,
        )

    def resolve(
        self,
        requirement: ResearchRequirementRecord,
        *,
        retrievals: Iterable[DirectedRetrievalRecord] = (),
        hypotheses: Iterable[BehaviorHypothesis] = (),
        evidence: CanonicalEvidenceBundle | None = None,
        implementation_handoffs: Iterable[GitHubImplementationVerificationHandoff]
        = (),
        unresolved_implementation_handoff_ids: Iterable[str] = (),
        pattern_provider_status: PatternLookupRuntimeStatus | None = None,
        worker_results: Iterable[ResearchWorkerResult] = (),
    ) -> QuestionResearchRecord:
        """Resolve the terminal research status of one routed question.

        ``NOT_FOUND`` means the mandated research executed and found no answer;
        it never asserts that the opposite behavior is true.
        """

        question_id = requirement.question_id
        question_retrievals = [
            row for row in retrievals if row.question_id == question_id
        ]
        question_hypotheses = [
            row
            for row in hypotheses
            if row.derived_from_question_id == question_id
        ]
        question_handoffs = [
            row for row in implementation_handoffs if row.question_id == question_id
        ]
        # R2: structured worker envelopes bound to this question.
        question_worker_results = [
            row for row in worker_results if row.question_id == question_id
        ]
        unresolved_handoffs = set(unresolved_implementation_handoff_ids)
        source_type_by_evidence_id = {
            row.evidence_id: row.source_type
            for row in (evidence.records if evidence is not None else [])
        }

        def build(
            status: ResearchStatus,
            reason: str,
            request_ids: list[str] | None = None,
            evidence_ids: list[str] | None = None,
        ) -> QuestionResearchRecord:
            return QuestionResearchRecord(
                question_id=question_id,
                requirement_id=requirement.requirement_id,
                research_requirement=requirement.research_requirement,
                research_status=status,
                research_request_ids=request_ids or [],
                evidence_ids=evidence_ids or [],
                reason=reason,
            )

        if requirement.research_requirement == ResearchRequirement.NONE:
            return build(ResearchStatus.NOT_REQUIRED, requirement.rationale)
        if not requirement.material:
            return build(
                ResearchStatus.NOT_APPLICABLE,
                "The question is not material to the current change; "
                "mandatory research routing does not apply.",
            )
        request_ids = [row.retrieval_id for row in question_retrievals] + [
            row.handoff_id for row in question_handoffs
        ] + [row.research_id for row in question_worker_results]
        if not request_ids:
            return build(
                ResearchStatus.PENDING,
                "Mandatory research was classified but never executed; "
                "coverage must not finalize this question from the current "
                "Jira/configuration evidence alone.",
            )
        evidence_ids = sorted(
            {
                evidence_id
                for row in question_retrievals
                for evidence_id in row.matched_evidence_ids
            }
            | {
                evidence_id
                for row in question_hypotheses
                for evidence_id in (
                    list(row.supporting_evidence_ids)
                    + list(row.contradicting_evidence_ids)
                    + list(row.verification_evidence_ids)
                )
            }
            | {
                source_ref
                for row in question_worker_results
                for finding in row.findings
                for source_ref in finding.source_refs
            }
        )
        required_categories = {
            research_source_category(source_type)
            for source_type in requirement.required_source_types
        } - {RESEARCH_CATEGORY_JIRA_AUTHORITY}
        researched_categories = {
            research_source_category(source_type_by_evidence_id[evidence_id])
            for evidence_id in evidence_ids
            if evidence_id in source_type_by_evidence_id
        }
        # R2: an executed worker envelope covers its route's category even when
        # its findings cite no bundle evidence (e.g. read-only repository
        # research); a worker that could not execute never covers it.
        _WORKER_ROLE_CATEGORY = {
            ResearchWorkerRole.DOC_RESEARCHER: RESEARCH_CATEGORY_DOCUMENTATION,
            ResearchWorkerRole.CODE_RESEARCHER: RESEARCH_CATEGORY_IMPLEMENTATION,
            ResearchWorkerRole.ATTACHMENT_RESEARCHER: RESEARCH_CATEGORY_JIRA_AUTHORITY,
        }
        executed_worker_categories = set()
        unavailable_worker_categories = set()
        for result in question_worker_results:
            category = _WORKER_ROLE_CATEGORY.get(result.worker_role)
            if category is None:
                continue
            if result.status in {
                ResearchWorkerStatus.ANSWER_FOUND,
                ResearchWorkerStatus.PARTIAL,
                ResearchWorkerStatus.NOT_FOUND,
                ResearchWorkerStatus.CONFLICTED,
            }:
                executed_worker_categories.add(category)
            else:
                unavailable_worker_categories.add(category)
        researched_categories |= executed_worker_categories
        unresolved_worker_categories = (
            unavailable_worker_categories - executed_worker_categories
        )
        resolved_handoffs = [
            row
            for row in question_handoffs
            if row.handoff_id not in unresolved_handoffs
        ]
        if (
            resolved_handoffs
            and RESEARCH_CATEGORY_IMPLEMENTATION in required_categories
        ):
            researched_categories.add(RESEARCH_CATEGORY_IMPLEMENTATION)
        unresearched = required_categories - researched_categories
        states = {row.state for row in question_hypotheses}
        # R2: workers executed and found nothing, with no other evidence or
        # hypothesis: that is a true NOT_FOUND (executed, no answer), never a
        # PARTIAL upgrade and never evidence of the opposite behavior.
        if (
            question_worker_results
            and not evidence_ids
            and not question_hypotheses
            and not unresearched
            and all(
                row.status == ResearchWorkerStatus.NOT_FOUND
                for row in question_worker_results
            )
        ):
            return build(
                ResearchStatus.NOT_FOUND,
                "Mandatory research executed and found no answer; absence "
                "of evidence is not treated as the opposite behavior.",
                request_ids,
                evidence_ids,
            )
        has_contradiction = any(
            row.contradicting_evidence_ids for row in question_hypotheses
        )
        terminal_states = states & {
            HypothesisState.CONFIRMED,
            HypothesisState.INFERRED_HIGH_CONFIDENCE,
            HypothesisState.REJECTED,
        }
        if has_contradiction or len(states) > 1:
            return build(
                ResearchStatus.CONFLICTED,
                "Directed research produced conflicting evidence; a Human "
                "must settle the conflict before coverage finalizes.",
                request_ids,
                evidence_ids,
            )
        # R2: a CONFLICTED worker envelope forces CONFLICTED research status;
        # the runtime never silently picks a side.
        if any(
            row.status == ResearchWorkerStatus.CONFLICTED
            for row in question_worker_results
        ):
            return build(
                ResearchStatus.CONFLICTED,
                "A research worker returned conflicting findings; a Human "
                "must settle the conflict before coverage finalizes.",
                request_ids,
                evidence_ids,
            )
        if terminal_states and not unresearched:
            return build(
                ResearchStatus.ANSWER_FOUND,
                "Mandatory research executed and produced a terminal answer "
                "from the required source.",
                request_ids,
                evidence_ids,
            )
        if not unresearched:
            return build(
                ResearchStatus.PARTIAL,
                "The mandated source was researched but yielded no terminal "
                "answer; the question remains partially answered.",
                request_ids,
                evidence_ids,
            )
        if evidence_ids or resolved_handoffs:
            return build(
                ResearchStatus.PARTIAL,
                "Research gathered evidence without consulting every mandated "
                "source; coverage must not finalize from the current "
                "Jira/configuration evidence alone.",
                request_ids,
                evidence_ids,
            )
        if (
            RESEARCH_CATEGORY_IMPLEMENTATION in unresearched
            and question_handoffs
            and not resolved_handoffs
        ):
            return build(
                ResearchStatus.SOURCE_UNAVAILABLE,
                "The mandated implementation source could not be inspected; "
                "the question remains open.",
                request_ids,
                evidence_ids,
            )
        if (
            RESEARCH_CATEGORY_HISTORICAL in unresearched
            and pattern_provider_status
            in {
                PatternLookupRuntimeStatus.PROVIDER_UNAVAILABLE,
                PatternLookupRuntimeStatus.PROVIDER_ERROR,
            }
        ):
            return build(
                ResearchStatus.SOURCE_UNAVAILABLE,
                "The mandated historical source could not be inspected; "
                "the question remains open.",
                request_ids,
                evidence_ids,
            )
        # R2: infrastructure failure is never disguised as a clean NOT_FOUND.
        if unresearched & unresolved_worker_categories:
            return build(
                ResearchStatus.SOURCE_UNAVAILABLE,
                "A mandated research worker could not execute; the question "
                "remains open and sufficiency stays bounded.",
                request_ids,
                evidence_ids,
            )
        return build(
            ResearchStatus.NOT_FOUND,
            "Mandatory research executed and found no answer; absence "
            "of evidence is not treated as the opposite behavior.",
            request_ids,
            evidence_ids,
        )


QUESTION_RESEARCH_ROUTER = QuestionResearchRouter()


__all__ = [
    "DOCUMENTATION_RESEARCH_SOURCES",
    "HISTORICAL_RESEARCH_SOURCES",
    "IMPLEMENTATION_RESEARCH_SOURCES",
    "JIRA_AUTHORITY_RESEARCH_SOURCES",
    "MATERIAL_RESEARCH_MATERIALITY",
    "QUESTION_RESEARCH_ROUTER",
    "REQUIREMENT_CATEGORY_SOURCES",
    "RESEARCH_CATEGORY_DOCUMENTATION",
    "RESEARCH_CATEGORY_HISTORICAL",
    "RESEARCH_CATEGORY_IMPLEMENTATION",
    "RESEARCH_CATEGORY_JIRA_AUTHORITY",
    "QuestionResearchRouter",
    "research_provider_category",
    "research_source_category",
]
