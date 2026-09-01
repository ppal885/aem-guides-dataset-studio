"""PFIX-04 deterministic contract and quality gate for Missing Questions.

Claude Desktop owns natural-language question wording.  This module owns only
typed normalization, validation, semantic deduplication, family accounting,
and post-retrieval resolution.  It never invokes an LLM and never promotes a
question or a Pattern MCP match into acceptance truth.
"""

from __future__ import annotations

from collections import defaultdict
import re

from app.core.schemas_canonical_test_plan_runtime import (
    AuthoritySubject,
    BehaviorRelationType,
    ClaudeMissingQuestionSubmission,
    ClosureDimensionResult,
    ClosureDisposition,
    CoverageDisposition,
    CoverageDispositionRecord,
    DirectedRetrievalRecord,
    EvidenceSourceType,
    FamilyActivationDecision,
    HumanQuestionClass,
    InvestigationFamilySatisfaction,
    InvestigationFamilySatisfactionStatus,
    InvestigationMateriality,
    MissingQuestion,
    MissingQuestionOrigin,
    MissingQuestionQualityDecision,
    MissingQuestionQualityFailureReason,
    MissingQuestionQualityReport,
    MissingQuestionResolutionRecord,
    MissingQuestionResolutionStatus,
    QeInvestigationPreparation,
    QuestionEvidenceProvider,
    QuestionValidationDisposition,
    RetrievalStatus,
    SemanticDimension,
    stable_sha256,
)


_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.:@/-]{1,}", re.IGNORECASE)
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "anything",
    "before",
    "could",
    "does",
    "else",
    "from",
    "have",
    "into",
    "other",
    "should",
    "that",
    "their",
    "there",
    "these",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
}
_INTERROGATIVE_RE = re.compile(
    r"\b(?:which|what|where|when|how|whether|does|do|is|are|can|could|will|would|should)\b",
    re.IGNORECASE,
)
_ASSERTING_PREFIX_RE = re.compile(
    r"^\s*(?:please\s+)?(?:verify|confirm|ensure|validate|check|prove)\s+(?:that\s+)?",
    re.IGNORECASE,
)
_PRODUCT_ASSUMPTION_RE = re.compile(
    r"\b(?:must|will\s+always|is\s+required\s+to|is\s+expected\s+to|"
    r"must\s+not|cannot\s+ever)\b",
    re.IGNORECASE,
)
_GENERIC_QUESTION_RE = re.compile(
    r"^\s*(?:does|do|is|are|can|could|will|would|should)?\s*"
    r"(?:this|it)?\s*(?:affect|impact|work)(?:\s+anything)?(?:\s+else)?\s*\?\s*$",
    re.IGNORECASE,
)
_GENERIC_BEHAVIOR_ANCHORS = {
    "current issue behavior",
    "current issue scope",
    "output preset behavior",
    "output preset functionality",
}


_DIMENSION_RELATION: dict[SemanticDimension, BehaviorRelationType] = {
    SemanticDimension.GOVERNING_SEMANTICS: BehaviorRelationType.GOVERNED_BY,
    SemanticDimension.CONTROLLING_ATTRIBUTES: BehaviorRelationType.CONTROLLING_ATTRIBUTE,
    SemanticDimension.GOVERNING_CONFIGURATION: BehaviorRelationType.CONFIGURED_BY,
    SemanticDimension.DIRECT_CONSUMERS: BehaviorRelationType.CONSUMED_BY,
    SemanticDimension.SIBLING_CONSUMERS: BehaviorRelationType.SIBLING_CONSUMER_OF,
    SemanticDimension.ALTERNATE_MECHANISMS: BehaviorRelationType.ALTERNATE_MECHANISM_TO,
    SemanticDimension.PARENT_CONTEXT: BehaviorRelationType.PARENT_OF,
    SemanticDimension.CHILD_CONTEXT: BehaviorRelationType.CHILD_OF,
    SemanticDimension.HIERARCHY: BehaviorRelationType.PARENT_OF,
    SemanticDimension.SPECIALIZATIONS: BehaviorRelationType.SPECIALIZED_BY,
    SemanticDimension.REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
    SemanticDimension.NESTED_REFERENCED_CONTENT: BehaviorRelationType.REFERENCES,
    SemanticDimension.ALTERNATE_REPRESENTATION: BehaviorRelationType.RESOLVES_THROUGH,
    SemanticDimension.CROSS_SURFACE_SYNC: BehaviorRelationType.SYNCHRONIZED_WITH,
    SemanticDimension.DOWNSTREAM_PROCESSOR: BehaviorRelationType.PROCESSED_BY,
    SemanticDimension.GENERATED_OUTPUT: BehaviorRelationType.GENERATED_BY,
    SemanticDimension.PERSISTED_STATE: BehaviorRelationType.PERSISTS_THROUGH,
    SemanticDimension.VERSION_APPLICABILITY: BehaviorRelationType.VERSION_DEPENDENT,
    SemanticDimension.DEPLOYMENT_APPLICABILITY: BehaviorRelationType.DEPLOYMENT_DEPENDENT,
    SemanticDimension.ROLE_PROFILE_APPLICABILITY: BehaviorRelationType.ROLE_DEPENDENT,
}

_RELATION_TERMS: dict[BehaviorRelationType, set[str]] = {
    BehaviorRelationType.DEFINED_BY: {
        "affect",
        "absent",
        "behavior",
        "expected",
        "fallback",
        "govern",
        "invalid",
        "lifecycle",
        "rule",
        "scope",
        "state",
        "value",
    },
    BehaviorRelationType.GOVERNED_BY: {"govern", "rule", "semantic", "defined"},
    BehaviorRelationType.CONFIGURED_BY: {
        "config",
        "configuration",
        "preset",
        "setting",
    },
    BehaviorRelationType.CONTROLLING_ATTRIBUTE: {"attribute", "control", "govern"},
    BehaviorRelationType.CONSUMED_BY: {"consumer", "read", "use", "uses"},
    BehaviorRelationType.SIBLING_CONSUMER_OF: {"consumer", "same", "shared", "sibling"},
    BehaviorRelationType.ALTERNATE_MECHANISM_TO: {
        "alternate",
        "another",
        "entry",
        "mechanism",
        "path",
    },
    BehaviorRelationType.PARENT_OF: {"child", "hierarchy", "nested", "parent"},
    BehaviorRelationType.CHILD_OF: {"child", "nested", "parent", "under"},
    BehaviorRelationType.SPECIALIZED_BY: {"base", "specialized", "specialization"},
    BehaviorRelationType.REFERENCES: {"reference", "referenced", "resolve"},
    BehaviorRelationType.RESOLVES_THROUGH: {"representation", "resolve", "resolved"},
    BehaviorRelationType.PROCESSED_BY: {
        "downstream",
        "process",
        "processor",
        "transform",
    },
    BehaviorRelationType.GENERATED_BY: {"artifact", "generate", "generated", "output"},
    BehaviorRelationType.PERSISTS_THROUGH: {
        "persist",
        "read",
        "repository",
        "state",
        "write",
    },
    BehaviorRelationType.SYNCHRONIZED_WITH: {"surface", "sync", "synchronized", "view"},
    BehaviorRelationType.VERSION_DEPENDENT: {"support", "upgrade", "version"},
    BehaviorRelationType.DEPLOYMENT_DEPENDENT: {"cloud", "deployment", "on-prem"},
    BehaviorRelationType.ROLE_DEPENDENT: {"permission", "profile", "role", "user"},
}


def _tokens(value: str) -> set[str]:
    return {
        token.casefold()
        for token in _WORD_RE.findall(value or "")
        if token.casefold() not in _STOP_WORDS
    }


def _expected_relation(
    family_id: SemanticDimension | None,
) -> BehaviorRelationType:
    if family_id is None:
        return BehaviorRelationType.DEFINED_BY
    return _DIMENSION_RELATION.get(family_id, BehaviorRelationType.DEFINED_BY)


def _preferred_provider(
    source_types: list[EvidenceSourceType],
) -> QuestionEvidenceProvider:
    sources = set(source_types)
    if sources & {
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CURRENT_CODE,
    }:
        return QuestionEvidenceProvider.GITHUB_MCP
    if EvidenceSourceType.DITA_SPECIFICATION in sources:
        return QuestionEvidenceProvider.DITA_SPECIFICATION
    if EvidenceSourceType.DITA_OT_DOCUMENTATION in sources:
        return QuestionEvidenceProvider.DITA_OT
    if EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION in sources:
        return QuestionEvidenceProvider.FLUFFYJAWS
    if EvidenceSourceType.EXISTING_AUTOMATION in sources:
        return QuestionEvidenceProvider.CONFIGURATION_OR_TESTS
    if sources:
        return QuestionEvidenceProvider.CURRENT_EVIDENCE
    return QuestionEvidenceProvider.UNSPECIFIED


def _semantic_key(question: MissingQuestion) -> str:
    return stable_sha256(
        {
            "family_id": question.family_id,
            "relationship": question.relationship_being_tested,
            "behavior_tokens": sorted(_tokens(question.linked_behavior_or_state)),
            "expected_evidence_type": sorted(
                row.value for row in question.expected_evidence_type
            ),
        }
    )


def _question_class(question: MissingQuestion) -> HumanQuestionClass:
    if question.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION:
        return HumanQuestionClass.IMPLEMENTATION_APPLICABILITY_UNRESOLVED
    if question.family_id in {
        SemanticDimension.GOVERNING_CONFIGURATION,
        SemanticDimension.DEPLOYMENT_APPLICABILITY,
        SemanticDimension.VERSION_APPLICABILITY,
    }:
        return HumanQuestionClass.SUPPORTED_CONFIGURATION_UNDECIDED
    if question.family_id is None and "scope" in question.question.casefold():
        return HumanQuestionClass.CURRENT_SCOPE_UNDECIDED
    return HumanQuestionClass.PRODUCT_EXPECTATION_UNDECIDED


class CanonicalMissingQuestionService:
    """Validate Claude wording and preserve family/evidence lineage."""

    def _compatibility_behavior(
        self,
        question: MissingQuestion,
        preparation: QeInvestigationPreparation,
        closure_by_id: dict[str, ClosureDimensionResult],
    ) -> str:
        entities = [
            closure_by_id[closure_id].entity
            for closure_id in question.source_closure_ids
            if closure_id in closure_by_id
        ]
        if entities:
            return ", ".join(dict.fromkeys(entities))
        facts = {
            fact.fact_id: fact.literal
            for fact in preparation.normalized_jira_facts.facts
        }
        fact_values = [
            facts[fact_id] for fact_id in question.source_fact_ids if fact_id in facts
        ]
        if fact_values:
            return ", ".join(dict.fromkeys(fact_values))
        lowered = question.question.casefold()
        if "dita-ot" in lowered:
            return "Enable DITA-OT Processing state"
        if "preset" in lowered:
            return (
                "output preset behavior"
                if "behavior" in lowered
                else "output preset functionality"
            )
        if "scope" in lowered:
            return "current issue scope"
        return "current issue behavior"

    def _enrich_compatibility_question(
        self,
        question: MissingQuestion,
        preparation: QeInvestigationPreparation,
        closure_by_id: dict[str, ClosureDimensionResult],
    ) -> MissingQuestion:
        families = {row.family_id: row for row in preparation.mandatory_families}
        family = families.get(question.family_id)
        behavior = self._compatibility_behavior(
            question,
            preparation,
            closure_by_id,
        )
        source_types = list(question.target_source_types)
        if family is not None:
            for source_type in family.preferred_evidence_sources:
                if source_type not in source_types:
                    source_types.append(source_type)
        relation = _expected_relation(question.family_id)
        why = (
            "; ".join(family.why_required)
            if family is not None
            else "The unresolved current-case dimension must remain visible until evidence resolves it."
        )
        materiality = (
            family.materiality
            if family is not None
            else InvestigationMateriality.P1
            if question.blocking
            else InvestigationMateriality.P2
        )
        payload = question.model_dump(
            mode="python",
            exclude={"question_id"},
        )
        payload.update(
            {
                "question_text": question.question,
                "family_id": question.dimension,
                "why_it_matters": why,
                "linked_change_surface": (
                    list(family.linked_change_surface_ids) if family else []
                ),
                "linked_behavior_or_state": behavior,
                "relationship_being_tested": relation,
                "expected_evidence_type": source_types,
                "target_source_types": source_types,
                "preferred_provider": _preferred_provider(source_types),
                "materiality": materiality,
                "blocking_status": question.blocking,
                "active_domain": [row.domain for row in preparation.domains],
                "active_reasoner": "Python compatibility fallback",
                "linked_pattern_ids": (
                    list(family.linked_pattern_ids) if family else []
                ),
                "current_fact_refs": list(question.source_fact_ids),
                "expected_oracle": (
                    f"Evidence identifies {relation.value} for {behavior}."
                ),
                "origin": MissingQuestionOrigin.PYTHON_COMPATIBILITY_FALLBACK,
            }
        )
        return MissingQuestion.model_validate(payload)

    def _validate_question(
        self,
        question: MissingQuestion,
        preparation: QeInvestigationPreparation,
    ) -> list[MissingQuestionQualityFailureReason]:
        failures: set[MissingQuestionQualityFailureReason] = set()
        question_tokens = _tokens(question.question)
        behavior_tokens = _tokens(question.linked_behavior_or_state)
        if not behavior_tokens or not (question_tokens & behavior_tokens):
            failures.add(
                MissingQuestionQualityFailureReason.NO_CHANGED_BEHAVIOR_REFERENCE
            )

        relation = question.relationship_being_tested
        relation_terms = _RELATION_TERMS.get(relation, set()) if relation else set()
        if relation is None or not (question_tokens & relation_terms):
            failures.add(MissingQuestionQualityFailureReason.NO_RELATIONSHIP)

        if not question.question.rstrip().endswith("?") or not _INTERROGATIVE_RE.search(
            question.question
        ):
            failures.add(MissingQuestionQualityFailureReason.NOT_EVIDENCE_SEEKING)
        if _ASSERTING_PREFIX_RE.search(question.question):
            failures.add(MissingQuestionQualityFailureReason.ASSERTS_ANSWER)
        if _ASSERTING_PREFIX_RE.search(
            question.question
        ) or _PRODUCT_ASSUMPTION_RE.search(question.question):
            failures.add(MissingQuestionQualityFailureReason.PRODUCT_DECISION_ASSUMED)
        has_bound_context = bool(
            question.linked_change_surface or question.current_fact_refs
        ) and (
            question.linked_behavior_or_state.casefold()
            not in _GENERIC_BEHAVIOR_ANCHORS
        )
        if (
            (len(question_tokens) < 4 and not has_bound_context)
            or _GENERIC_QUESTION_RE.fullmatch(question.question) is not None
            or not question.why_it_matters.strip()
            or not question.expected_oracle.strip()
        ):
            failures.add(MissingQuestionQualityFailureReason.TOO_GENERIC)

        families = {row.family_id: row for row in preparation.mandatory_families}
        family = families.get(question.family_id)
        if question.origin == MissingQuestionOrigin.CLAUDE_DESKTOP:
            if question.family_id is not None and family is None:
                failures.add(MissingQuestionQualityFailureReason.WRONG_FAMILY)
            if family is not None and family.activation_decision == (
                FamilyActivationDecision.DO_NOT_ACTIVATE
            ):
                failures.add(MissingQuestionQualityFailureReason.WRONG_FAMILY)
        if question.family_id is not None and relation != _expected_relation(
            question.family_id
        ):
            failures.add(MissingQuestionQualityFailureReason.WRONG_FAMILY)
        if family is not None and not set(question.linked_pattern_ids).issubset(
            family.linked_pattern_ids
        ):
            failures.add(MissingQuestionQualityFailureReason.WRONG_FAMILY)

        known_surface_ids = {row.surface_id for row in preparation.change_surfaces}
        known_fact_ids = {
            row.fact_id for row in preparation.normalized_jira_facts.facts
        }
        if not set(question.linked_change_surface).issubset(
            known_surface_ids
        ) or not set(question.current_fact_refs).issubset(known_fact_ids):
            failures.add(MissingQuestionQualityFailureReason.UNKNOWN_CONTEXT_REFERENCE)

        if question.family_id in preparation.already_investigated_dimensions:
            failures.add(
                MissingQuestionQualityFailureReason.QUESTION_ALREADY_ANSWERED_BY_EVIDENCE
            )
        if (
            not question.expected_evidence_type
            or not question.target_source_types
            or question.preferred_provider == QuestionEvidenceProvider.UNSPECIFIED
            or question.preferred_provider
            == QuestionEvidenceProvider.PATTERN_MCP_DISCOVERY
        ):
            failures.add(MissingQuestionQualityFailureReason.NO_EVIDENCE_PATH)

        for fact in preparation.normalized_jira_facts.facts:
            fact_tokens = _tokens(fact.literal)
            if len(fact_tokens) < 5:
                continue
            overlap = len(question_tokens & fact_tokens) / max(
                len(question_tokens | fact_tokens),
                1,
            )
            if overlap >= 0.90:
                failures.add(MissingQuestionQualityFailureReason.REPEATS_CURRENT_JIRA)
                break
        return sorted(failures, key=lambda row: row.value)

    def _merge_semantic_duplicates(
        self,
        questions: list[MissingQuestion],
        decisions: dict[str, MissingQuestionQualityDecision],
    ) -> list[MissingQuestion]:
        selected: dict[str, MissingQuestion] = {}
        for question in sorted(questions, key=lambda row: row.question_id):
            key = _semantic_key(question)
            existing = selected.get(key)
            if existing is None:
                selected[key] = question
                continue
            payload = existing.model_dump(mode="python", exclude={"question_id"})
            payload["source_closure_ids"] = sorted(
                set(existing.source_closure_ids) | set(question.source_closure_ids)
            )
            payload["source_fact_ids"] = sorted(
                set(existing.source_fact_ids) | set(question.source_fact_ids)
            )
            payload["linked_change_surface"] = sorted(
                set(existing.linked_change_surface)
                | set(question.linked_change_surface)
            )
            payload["linked_pattern_ids"] = sorted(
                set(existing.linked_pattern_ids) | set(question.linked_pattern_ids)
            )
            payload["current_fact_refs"] = sorted(
                set(existing.current_fact_refs) | set(question.current_fact_refs)
            )
            selected[key] = MissingQuestion.model_validate(payload)
            decisions[question.question_id] = MissingQuestionQualityDecision(
                question_id=question.question_id,
                disposition=QuestionValidationDisposition.REJECTED,
                failure_reasons=[
                    MissingQuestionQualityFailureReason.SEMANTIC_DUPLICATE
                ],
                semantic_key=key,
                family_satisfaction_eligible=False,
            )
        return sorted(selected.values(), key=lambda row: row.question_id)

    def select_questions(
        self,
        *,
        preparation: QeInvestigationPreparation,
        closure: list[ClosureDimensionResult],
        compatibility_questions: list[MissingQuestion],
        claude_submission: ClaudeMissingQuestionSubmission | None = None,
        expected_request_id: str | None = None,
    ) -> MissingQuestionQualityReport:
        """Select only contextual questions for the canonical retrieval stage."""

        if claude_submission is not None:
            if claude_submission.preparation_id != preparation.preparation_id:
                raise ValueError(
                    "Claude question submission is bound to another preparation"
                )
            bound_request_id = expected_request_id or preparation.request_id
            if (
                claude_submission.request_id is not None
                and bound_request_id is not None
                and claude_submission.request_id != bound_request_id
            ):
                raise ValueError(
                    "Claude question submission is bound to another request"
                )
            submitted = list(claude_submission.questions)
            origin = MissingQuestionOrigin.CLAUDE_DESKTOP
        else:
            closure_by_id = {row.closure_id: row for row in closure}
            submitted = [
                self._enrich_compatibility_question(
                    question,
                    preparation,
                    closure_by_id,
                )
                for question in compatibility_questions
            ]
            origin = MissingQuestionOrigin.PYTHON_COMPATIBILITY_FALLBACK

        decisions: dict[str, MissingQuestionQualityDecision] = {}
        provisionally_accepted: list[MissingQuestion] = []
        for question in sorted(submitted, key=lambda row: row.question_id):
            semantic_key = _semantic_key(question)
            failures = self._validate_question(question, preparation)
            accepted = not failures
            decisions[question.question_id] = MissingQuestionQualityDecision(
                question_id=question.question_id,
                disposition=(
                    QuestionValidationDisposition.ACCEPTED
                    if accepted
                    else QuestionValidationDisposition.REJECTED
                ),
                failure_reasons=failures,
                semantic_key=semantic_key,
                family_satisfaction_eligible=accepted
                and question.family_id is not None,
            )
            if accepted:
                provisionally_accepted.append(question)

        accepted_questions = self._merge_semantic_duplicates(
            provisionally_accepted,
            decisions,
        )
        accepted_ids = {row.question_id for row in accepted_questions}
        for question_id, decision in list(decisions.items()):
            if (
                decision.disposition == QuestionValidationDisposition.ACCEPTED
                and question_id not in accepted_ids
            ):
                decisions[question_id] = MissingQuestionQualityDecision(
                    question_id=question_id,
                    disposition=QuestionValidationDisposition.REJECTED,
                    failure_reasons=[
                        MissingQuestionQualityFailureReason.SEMANTIC_DUPLICATE
                    ],
                    semantic_key=decision.semantic_key,
                    family_satisfaction_eligible=False,
                )

        accepted_by_family: dict[SemanticDimension, list[str]] = defaultdict(list)
        for question in accepted_questions:
            if question.family_id is not None:
                accepted_by_family[question.family_id].append(question.question_id)
        evidence_resolution_by_family: dict[SemanticDimension, list[str]] = defaultdict(
            list
        )
        for row in closure:
            if row.disposition in {
                ClosureDisposition.COVERED,
                ClosureDisposition.INVESTIGATED_AND_REJECTED,
            }:
                evidence_resolution_by_family[row.dimension].append(row.closure_id)

        family_satisfaction: list[InvestigationFamilySatisfaction] = []
        for family in preparation.mandatory_families:
            valid_question_ids = accepted_by_family.get(family.family_id, [])
            evidence_ids = evidence_resolution_by_family.get(family.family_id, [])
            if family.activation_decision == FamilyActivationDecision.DO_NOT_ACTIVATE:
                status = InvestigationFamilySatisfactionStatus.NOT_REQUIRED
                failures: list[MissingQuestionQualityFailureReason] = []
            elif evidence_ids or family.family_id in (
                preparation.already_investigated_dimensions
            ):
                status = InvestigationFamilySatisfactionStatus.SATISFIED_BY_EVIDENCE
                failures = []
            elif valid_question_ids:
                status = (
                    InvestigationFamilySatisfactionStatus.SATISFIED_BY_VALID_QUESTION
                )
                failures = []
            else:
                status = InvestigationFamilySatisfactionStatus.UNSATISFIED
                failures = [MissingQuestionQualityFailureReason.MATERIAL_DIMENSION_LOST]
            family_satisfaction.append(
                InvestigationFamilySatisfaction(
                    family_id=family.family_id,
                    activation_decision=family.activation_decision,
                    status=status,
                    valid_question_ids=valid_question_ids,
                    evidence_resolution_ids=evidence_ids,
                    failure_reasons=failures,
                )
            )

        return MissingQuestionQualityReport(
            preparation_id=preparation.preparation_id,
            question_origin=origin,
            submitted_questions=submitted,
            accepted_questions=accepted_questions,
            decisions=list(decisions.values()),
            family_satisfaction=family_satisfaction,
            duplicate_collapse_loss=[],
        )

    def resolve_after_evidence(
        self,
        *,
        report: MissingQuestionQualityReport,
        retrievals: list[DirectedRetrievalRecord],
        dispositions: list[CoverageDispositionRecord],
        closure: list[ClosureDimensionResult],
    ) -> list[MissingQuestionResolutionRecord]:
        """Prevent answerable evidence questions from becoming Human questions."""

        retrieval_by_question = {row.question_id: row for row in retrievals}
        dispositions_by_question: dict[str, list[CoverageDispositionRecord]] = (
            defaultdict(list)
        )
        for disposition in dispositions:
            for question_id in disposition.source_question_ids:
                dispositions_by_question[question_id].append(disposition)
        closure_evidence = {row.closure_id: list(row.evidence_ids) for row in closure}
        accepted_ids = {row.question_id for row in report.accepted_questions}
        decisions_by_question = {row.question_id: row for row in report.decisions}
        evidence_resolutions_by_family = {
            row.family_id: row
            for row in report.family_satisfaction
            if row.status == InvestigationFamilySatisfactionStatus.SATISFIED_BY_EVIDENCE
        }
        rows: list[MissingQuestionResolutionRecord] = []
        for question in report.submitted_questions:
            if question.question_id not in accepted_ids:
                decision = decisions_by_question[question.question_id]
                evidence_resolution = evidence_resolutions_by_family.get(
                    question.family_id
                )
                if (
                    MissingQuestionQualityFailureReason.QUESTION_ALREADY_ANSWERED_BY_EVIDENCE
                    in decision.failure_reasons
                    and evidence_resolution is not None
                ):
                    evidence_ids = {
                        evidence_id
                        for closure_id in evidence_resolution.evidence_resolution_ids
                        for evidence_id in closure_evidence.get(closure_id, [])
                    }
                    rows.append(
                        MissingQuestionResolutionRecord(
                            question_id=question.question_id,
                            status=(
                                MissingQuestionResolutionStatus.RESOLVED_BY_EVIDENCE
                            ),
                            evidence_ids=sorted(evidence_ids),
                            reason=(
                                "Authoritative current evidence had already resolved "
                                "this family, so the question was not sent to a Human."
                            ),
                        )
                    )
                    continue
                rows.append(
                    MissingQuestionResolutionRecord(
                        question_id=question.question_id,
                        status=MissingQuestionResolutionStatus.REJECTED_QUALITY,
                        reason="The deterministic PFIX-04 quality gate rejected the question.",
                    )
                )
                continue
            question_dispositions = dispositions_by_question.get(
                question.question_id,
                [],
            )
            evidence_ids = {
                evidence_id
                for disposition in question_dispositions
                for evidence_id in disposition.evidence_ids
            }
            for disposition in question_dispositions:
                for closure_id in disposition.source_closure_ids:
                    evidence_ids.update(closure_evidence.get(closure_id, []))
            open_dispositions = [
                row
                for row in question_dispositions
                if row.disposition
                in {
                    CoverageDisposition.OPEN_QUESTION,
                    CoverageDisposition.PRODUCT_SCOPE_QUESTION,
                }
            ]
            resolved_dispositions = [
                row
                for row in question_dispositions
                if row.disposition
                not in {
                    CoverageDisposition.OPEN_QUESTION,
                    CoverageDisposition.PRODUCT_SCOPE_QUESTION,
                    CoverageDisposition.UNSUPPORTED_INFERENCE,
                }
            ]
            retrieval = retrieval_by_question.get(question.question_id)
            if resolved_dispositions and evidence_ids:
                rows.append(
                    MissingQuestionResolutionRecord(
                        question_id=question.question_id,
                        status=MissingQuestionResolutionStatus.RESOLVED_BY_EVIDENCE,
                        evidence_ids=sorted(evidence_ids),
                        disposition_ids=[
                            row.disposition_id for row in resolved_dispositions
                        ],
                        reason=(
                            "Current evidence was verified and received a non-Human "
                            "terminal disposition."
                        ),
                    )
                )
            elif open_dispositions or (
                retrieval is not None
                and retrieval.status == RetrievalStatus.UNAVAILABLE
                and (
                    question.blocking
                    or question.materiality
                    in {InvestigationMateriality.P0, InvestigationMateriality.P1}
                )
            ):
                rows.append(
                    MissingQuestionResolutionRecord(
                        question_id=question.question_id,
                        status=MissingQuestionResolutionStatus.UNRESOLVED_HUMAN,
                        evidence_ids=sorted(evidence_ids),
                        disposition_ids=[
                            row.disposition_id for row in open_dispositions
                        ],
                        human_question_class=_question_class(question),
                        reason=(
                            "The material dimension remains unresolved after available "
                            "authoritative retrieval and verification."
                        ),
                    )
                )
            else:
                rows.append(
                    MissingQuestionResolutionRecord(
                        question_id=question.question_id,
                        status=MissingQuestionResolutionStatus.PENDING_EVIDENCE,
                        evidence_ids=sorted(evidence_ids),
                        disposition_ids=[
                            row.disposition_id for row in question_dispositions
                        ],
                        reason="No authoritative terminal resolution is available yet.",
                    )
                )
        return sorted(rows, key=lambda row: row.question_id)

    def apply_resolutions(
        self,
        questions: list[MissingQuestion],
        resolutions: list[MissingQuestionResolutionRecord],
    ) -> list[MissingQuestion]:
        resolution_by_id = {row.question_id: row for row in resolutions}
        output: list[MissingQuestion] = []
        for question in questions:
            resolution = resolution_by_id.get(question.question_id)
            if resolution is None:
                output.append(question)
                continue
            payload = question.model_dump(mode="python", exclude={"question_id"})
            payload["resolution_status"] = resolution.status
            payload["human_question_class"] = resolution.human_question_class
            output.append(MissingQuestion.model_validate(payload))
        return sorted(output, key=lambda row: row.question_id)


CANONICAL_MISSING_QUESTION_SERVICE = CanonicalMissingQuestionService()


__all__ = [
    "CANONICAL_MISSING_QUESTION_SERVICE",
    "CanonicalMissingQuestionService",
]
