"""Regression guards for planned-question subjects and identity-change closure.

Both defects were observed together on a Topic List report ticket: every planned
question rendered as "the affected behavior", so the researchers could not answer
any of them, and the move/rename dimension was marked resolved by the ordinary
word "uuid" appearing in retrieved evidence.
"""

from app.core.schemas_canonical_test_plan_runtime import (
    ApplicabilityState,
    AuthoritySubject,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    ClosureDimensionResult,
    ClosureDisposition,
    ContractFact,
    ContractFactSet,
    ContractFactType,
    ContractMode,
    EvidenceRecord,
    FamilyActivationDecision,
    InvestigationFamilySourceContribution,
    InvestigationFamilySourceKind,
    InvestigationMateriality,
    MandatoryInvestigationFamily,
    MissingQuestion,
    EvidenceSourceType,
    SemanticDimension,
    SourceVisibility,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE as SERVICE,
)
from app.services.canonical_test_plan_reasoning_service import (
    _DIMENSION_KEYWORDS,
    _behavior_subject_from_facts,
)
from app.services.canonical_missing_question_service import _resolved_materiality
from app.services.question_research_routing_service import (
    MATERIAL_RESEARCH_MATERIALITY,
)

PRODUCT_AREA = "Topic List report in the new Reports UI"

# Retrieval closure legitimately returns non-product identifiers alongside real
# product entities; none of them may become the subject a human question asks about.
RETRIEVAL_ENTITIES = [
    "tests/upgrade/3_post_upgrade_scenarios.feature",
    "core/reports/src/main/java/com/adobe/guides/reports/servlet/TopicListReportController.java",
    "C:\\xmleditor\\xmleditor\\src\\controllers\\widgets\\reports\\reports_panel.test.ts",
    "RO1_shouldCorrectly_ReadAll_DitaProfiles",
    # camelCase is how Java and TypeScript name test methods and accessors, so
    # these reach closure looking like ordinary words.
    "Native_PDF",
    "shouldThrowExceptionWhenInvalidPresetTypeInUpdateExistingPresets",
    "getId",
]

PLANNED_DIMENSIONS = [
    SemanticDimension.VALUE_PROVENANCE,
    SemanticDimension.MUTATION_FRESHNESS,
    SemanticDimension.IDENTITY_CHANGE,
    SemanticDimension.PERSISTED_STATE,
]


def _unresolved_closure() -> list[ClosureDimensionResult]:
    return [
        ClosureDimensionResult(
            entity=entity,
            dimension=dimension,
            disposition=ClosureDisposition.UNRESOLVED_AND_EXPOSED,
            applicability=ApplicabilityState.APPLICABLE,
            evidence_ids=["ev-1"],
            rationale="The dimension is applicable but the supplied evidence does not resolve it.",
        )
        for dimension in PLANNED_DIMENSIONS
        for entity in RETRIEVAL_ENTITIES
    ]


def _facts(literal: str = PRODUCT_AREA) -> ContractFactSet:
    return ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.PRIMARY_PRODUCT_AREA,
                literal=literal,
                source_evidence_ids=["ev-1"],
                authoritative=True,
            )
        ],
    )


def _plan(facts: ContractFactSet):
    scope = SERVICE.resolve_scope(facts, [])
    return SERVICE.generate_missing_questions(_unresolved_closure(), scope, facts)


def test_planned_questions_name_the_product_subject() -> None:
    questions = _plan(_facts())

    assert questions, "unresolved closure rows must still plan questions"
    for question in questions:
        assert PRODUCT_AREA in question.question, question.question
        assert "the affected behavior" not in question.question, question.question


def test_retrieval_identifiers_never_become_a_question_subject() -> None:
    questions = _plan(_facts())

    for question in questions:
        for entity in RETRIEVAL_ENTITIES:
            assert entity not in question.question, question.question
        assert ".feature" not in question.question, question.question
        assert "\\" not in question.question, question.question


def test_camelcase_code_identifiers_never_become_a_question_subject() -> None:
    """Java/TypeScript test methods and accessors are code, not product language.

    Observed on a Native PDF bookmap-title ticket: every planned question was
    asked about "shouldThrowExceptionWhenInvalidPresetTypeInUpdateExistingPresets,
    getId", so no researcher could answer any of them and the run never left
    waiting_for_agent_research.
    """
    questions = _plan(_facts())

    for question in questions:
        assert "shouldThrowException" not in question.question, question.question
        assert "getId" not in question.question, question.question
        assert "Native_PDF" not in question.question, question.question
        assert PRODUCT_AREA in question.question, question.question


def test_sentence_shaped_fact_is_reduced_to_its_subject_noun_phrase() -> None:
    """A contract fact is a whole source sentence; a subject is a noun phrase.

    Substituting the sentence produced "Where does the value shown for Map
    title/dc:title shows entire booktitle element. come from?" - unanswerable.
    """
    facts = _facts("Map title/dc:title shows entire booktitle element.")
    questions = _plan(facts)

    assert questions
    provenance = next(
        question
        for question in questions
        if question.dimension == SemanticDimension.VALUE_PROVENANCE
    )
    assert "Map title/dc:title" in provenance.question
    assert "shows entire booktitle element" not in provenance.question


def test_ticket_behavior_beats_generic_component_as_question_subject() -> None:
    """A component label must not replace the behavior named by the ticket."""

    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT,
        facts=[
            ContractFact(
                fact_type=ContractFactType.PRIMARY_PRODUCT_AREA,
                literal="Editor",
                source_evidence_ids=["ev-1"],
                authoritative=True,
            ),
            ContractFact(
                fact_type=ContractFactType.CONTEXT_STATEMENT,
                literal=(
                    "In Web Editor Author view, add the colsep attributes "
                    "for table columns."
                ),
                source_evidence_ids=["ev-1"],
                authoritative=True,
            ),
        ],
    )

    subject = _behavior_subject_from_facts(facts)

    assert subject == "Web Editor Author view the colsep attributes for table columns"


def test_identity_change_question_is_planned_for_a_report_reading_stored_state() -> None:
    questions = _plan(_facts())

    planned = {question.dimension for question in questions}
    assert SemanticDimension.IDENTITY_CHANGE in planned
    identity = next(
        question
        for question in questions
        if question.dimension == SemanticDimension.IDENTITY_CHANGE
    )
    assert "moved or renamed" in identity.question


def test_subject_falls_back_when_no_product_area_is_extractable() -> None:
    facts = ContractFactSet(
        contract_mode=ContractMode.EVIDENCE_BACKED_PROPOSED_CONTRACT, facts=[]
    )
    questions = _plan(facts)

    assert questions
    for question in questions:
        for entity in RETRIEVAL_ENTITIES:
            assert entity not in question.question, question.question


def test_identity_change_is_not_resolved_by_ordinary_uuid_vocabulary() -> None:
    keywords = _DIMENSION_KEYWORDS[SemanticDimension.IDENTITY_CHANGE]

    # Every AEM Guides asset carries a UUID and an identity, so these bare tokens
    # appear in unrelated evidence and previously marked the dimension covered.
    assert "uuid" not in keywords
    assert "identity" not in keywords

    incidental = "The report lists the topic uuid and its identity column.".casefold()
    assert not any(keyword in incidental for keyword in keywords)

    actual_change = "The topic was renamed and the asset moved to a new path.".casefold()
    assert any(keyword in actual_change for keyword in keywords)


TENANT = "tenant_subject_binding"

# LIFECYCLE is always applicable, so it exercises the resolution branch without
# depending on which dimensions a particular expansion activates.
CLOSURE_DIMENSION = SemanticDimension.LIFECYCLE


def _closure_row(source_type: EvidenceSourceType) -> ClosureDimensionResult:
    keyword = _DIMENSION_KEYWORDS[CLOSURE_DIMENSION][0]
    bundle = CanonicalEvidenceBundle(
        tenant_id=TENANT,
        records=[
            EvidenceRecord(
                source_type=source_type,
                authority_subject=AuthoritySubject.PRODUCT_CONTRACT,
                source_reference="test:closure-record",
                tenant_id=TENANT,
                visibility=SourceVisibility(tenant_id=TENANT),
                content={"text": f"The entry is {keyword} in the product."},
            )
        ],
    )
    rows = SERVICE.explore_semantic_closure(bundle, CanonicalBehaviorModel())
    return next(row for row in rows if row.dimension is CLOSURE_DIMENSION)


def test_retrieved_documentation_does_not_resolve_a_behavioral_dimension() -> None:
    # A corpus chunk that merely shares the dimension's vocabulary is a topic
    # match. Treating it as resolution silently closed most dimensions.
    row = _closure_row(EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION)

    assert row.disposition is ClosureDisposition.UNRESOLVED_AND_EXPOSED
    # The chunk stays attached so the topic evidence is not lost.
    assert row.evidence_ids


def test_change_bound_evidence_still_resolves_a_behavioral_dimension() -> None:
    for source_type in (
        EvidenceSourceType.JIRA_DESCRIPTION,
        EvidenceSourceType.CURRENT_CODE,
    ):
        row = _closure_row(source_type)
        assert row.disposition is ClosureDisposition.COVERED, source_type
        assert row.evidence_ids, source_type


def test_planned_dimension_questions_are_material_enough_to_be_researched() -> None:
    # A P2 question is classified NOT_APPLICABLE by the research router, so the
    # mandated research never runs and coverage silently loses the dimension.
    questions = _plan(_facts())

    dimension_questions = [q for q in questions if q.dimension is not None]
    assert dimension_questions

    immaterial = [
        q
        for q in dimension_questions
        if not q.blocking and q.materiality not in MATERIAL_RESEARCH_MATERIALITY
    ]
    assert not immaterial, [
        (q.dimension, q.materiality) for q in immaterial
    ]


def _family(materiality: InvestigationMateriality) -> MandatoryInvestigationFamily:
    return MandatoryInvestigationFamily(
        family_id=CLOSURE_DIMENSION,
        sources=[
            InvestigationFamilySourceContribution(
                source=list(InvestigationFamilySourceKind)[0],
                why_required="closure left this dimension unresolved",
                materiality=materiality,
            )
        ],
        materiality=materiality,
        activation_decision=FamilyActivationDecision.ACTIVATE_NON_BLOCKING,
        confidence=0.9,
        applicability_reason="applicable to the change under test",
    )


def _question(materiality: InvestigationMateriality) -> MissingQuestion:
    return MissingQuestion(
        authority_subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        family_id=CLOSURE_DIMENSION,
        question=f"What happens to the stored state for {PRODUCT_AREA}?",
        materiality=materiality,
    )


def test_family_never_lowers_an_explicit_producer_materiality():
    """A family activates a dimension; it must not de-materialize it.

    The planner marks a closure-exposed dimension question material so its
    mandated research runs. When the family's own materiality was allowed to
    win unconditionally, that decision was reset to the P2 default, the research
    router classified the question NOT_APPLICABLE, and the dimension was lost.
    """
    resolved = _resolved_materiality(
        _question(InvestigationMateriality.P1),
        _family(InvestigationMateriality.P2),
    )
    assert resolved is InvestigationMateriality.P1
    assert resolved in MATERIAL_RESEARCH_MATERIALITY


def test_family_still_raises_materiality_above_the_producer():
    assert (
        _resolved_materiality(
            _question(InvestigationMateriality.P1),
            _family(InvestigationMateriality.P0),
        )
        is InvestigationMateriality.P0
    )


def test_default_materiality_is_unchanged_without_a_family():
    assert (
        _resolved_materiality(_question(InvestigationMateriality.P2), None)
        is InvestigationMateriality.P2
    )
