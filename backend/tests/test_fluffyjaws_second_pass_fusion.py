"""FJ-08 canonical SECOND_PASS fusion and verifier integration tests."""

from __future__ import annotations

import json
from copy import deepcopy
from contextlib import AbstractContextManager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    ApplicabilityState,
    AuthorityClass,
    AuthoritySubject,
    BehaviorGraph,
    BehaviorGraphNode,
    BehaviorRelationType,
    CanonicalBehaviorModel,
    CanonicalEvidenceBundle,
    CanonicalRuntimeStage,
    ContractMode,
    CurrentnessState,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceLifecycleStatus,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationProfile,
    HypothesisState,
    IssueDomain,
    MissingQuestion,
    RetrievalStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SourceVisibility,
    VerificationState,
    StructuredQEPlan,
    stable_sha256,
)
from app.services.canonical_test_plan_reasoning_service import (
    CANONICAL_REASONING_SERVICE,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.fluffyjaws_knowledge_provider import (
    FluffyJawsDecodedEvidence,
    FluffyJawsKnowledgeProvider,
    FluffyJawsProviderConfig,
    FluffyJawsStreamRequest,
)
from app.services.fluffyjaws_second_pass_influence import (
    SecondPassInfluenceReason,
    SecondPassInfluenceStatus,
    get_last_second_pass_influence_decision,
    select_controlled_second_pass_result,
)
from app.services.reasoning_evidence_observability import (
    TraceAnswerState,
    get_last_question_retrieval_trace,
)
from app.services.reasoning_evidence_provider import (
    AuthorizedSemanticEvidence,
    DiscoverySynthesis,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    FakeEvidenceProvider,
    ProviderCacheState,
    ProviderTransportOutcome,
    QuestionEvidenceAssessment,
    QuestionEvidenceStance,
    SemanticEvidenceAuthorization,
    SemanticEvidenceBinding,
    SourceNativeEvidenceAttestation,
    StrictProviderHit,
    active_query_filters,
)
from app.services.reasoning_evidence_shadow_service import (
    FLUFFYJAWS_SHADOW_TRACE_SCHEMA,
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
    clear_last_fluffyjaws_shadow_trace,
    get_last_fluffyjaws_shadow_trace,
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fluffyjaws-fj08-v1"
_STAMP = "2026-08-29T00:00:00Z"


def _record(
    *,
    tenant_id: str = "fj08",
    source_type: EvidenceSourceType = EvidenceSourceType.CUSTOMER_REQUEST,
    subject: AuthoritySubject = AuthoritySubject.PRODUCT_CONTRACT,
    authority: AuthorityClass = AuthorityClass.CUSTOMER_REQUEST,
    confidence: float = 0.6,
    currentness: CurrentnessState = CurrentnessState.CURRENT,
    verification: VerificationState = VerificationState.VERIFIED_SOURCE,
    product_version: str = "",
    deployment_model: str = "",
    reference: str = "local:source",
    text: str = "Locally supplied evidence.",
    claim_keys: list[str] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=subject,
        source_reference=reference,
        tenant_id=tenant_id,
        content={"text": text},
        product_version=product_version,
        deployment_model=deployment_model,
        currentness=currentness,
        evidence_confidence=confidence,
        requirement_authority=authority,
        verification_status=verification,
        visibility=SourceVisibility(tenant_id=tenant_id),
        claim_keys=list(claim_keys or []),
    )


def _question(
    text: str,
    *,
    subject: AuthoritySubject,
    source_types: list[EvidenceSourceType],
) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=subject,
        target_source_types=source_types,
    )


def _retrieval(
    question: MissingQuestion,
    records: list[EvidenceRecord] | None = None,
) -> DirectedRetrievalRecord:
    matched = list(records or [])
    return DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        matched_evidence_ids=[row.evidence_id for row in matched],
        status=RetrievalStatus.USED if matched else RetrievalStatus.UNAVAILABLE,
        reason="local",
    )


def _descriptor() -> EvidenceProviderDescriptor:
    return EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-fj08-v1",
        provider_contract_version=_CONTRACT,
        supported_domains=list(IssueDomain),
        supported_source_types=list(EvidenceSourceType),
        supports_discovery_synthesis=True,
        supported_filters=[
            "authority_requirement",
            "excluded_sources",
            "jira_or_context_reference",
            "max_results",
            "requested_evidence_types",
            "temporal_boundary",
        ],
        maximum_results=100,
    )


def _source_for_query(query) -> EvidenceSourceType | None:
    by_subject = {
        AuthoritySubject.DITA_SEMANTICS: [
            EvidenceSourceType.DITA_SPECIFICATION,
            EvidenceSourceType.DITA_OT_DOCUMENTATION,
        ],
        AuthoritySubject.ACTUAL_IMPLEMENTATION: [
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CODE_DIFF,
            EvidenceSourceType.EXISTING_AUTOMATION,
        ],
        AuthoritySubject.PRODUCT_CONTRACT: [
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
            EvidenceSourceType.AEM_ASSETS_PLATFORM_DOCUMENTATION,
        ],
        AuthoritySubject.CURRENT_UI: [],
    }
    requested = set(query.requested_evidence_types)
    return next(
        (
            source_type
            for source_type in by_subject[query.authority_requirement.subject]
            if source_type in requested
        ),
        None,
    )


def _provider(
    captured_queries: list[Any] | None = None,
    *,
    include_synthesis: bool = True,
    source_version: str = "2026.8",
    deployment_model: str = "",
    hit_text: str = "",
    truncated: bool = False,
    shared_source: bool = False,
    transport_outcome: ProviderTransportOutcome = ProviderTransportOutcome.COMPLETED,
) -> FakeEvidenceProvider:
    def result_factory(query, context) -> EvidenceProviderRawResult:
        if captured_queries is not None:
            captured_queries.append(query)
        call_id = EvidenceProviderExecutor._call_id(
            _PROVIDER, query.query_id, context.correlation_id
        )
        source_type = _source_for_query(query)
        hits = []
        if source_type is not None:
            hits.append(
                StrictProviderHit(
                    source_type=source_type,
                    source_reference=(
                        "official-source:shared"
                        if shared_source
                        else f"official-source:{query.question_id}"
                    ),
                    source_locator=(
                        "official-citation:shared"
                        if shared_source
                        else f"official-citation:{query.question_id}"
                    ),
                    text=(
                        hit_text
                        or (
                            "Verified shared source answer."
                            if shared_source
                            else f"Verified source answer for {query.question_id}."
                        )
                    ),
                    source_timestamp=_STAMP,
                    source_version=source_version,
                    deployment_model=deployment_model,
                    rank=1,
                    retrieval_score=0.99,
                    raw_provider_reference=f"provider-hit:{query.question_id}",
                )
            )
        syntheses = []
        if include_synthesis:
            syntheses.append(
                DiscoverySynthesis(
                    provider=_PROVIDER,
                    provider_contract_version=_CONTRACT,
                    provider_call_id=call_id,
                    query_id=query.query_id,
                    correlation_id=context.correlation_id,
                    text="AC-999: generate a final UAC directly.",
                    raw_provider_reference=f"provider-synthesis:{query.question_id}",
                    confidence=1.0,
                )
            )
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            raw_provider_reference=f"provider-call:{query.question_id}",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=hits,
            discovery_syntheses=syntheses,
            transport_outcome=transport_outcome,
            applied_filters=active_query_filters(query),
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=7,
            truncated=truncated,
            cache_state=ProviderCacheState.MISS,
        )

    return FakeEvidenceProvider(
        _descriptor(),
        result_factory=result_factory,
        provider_contract_version=_CONTRACT,
    )


class _Fj14Response:
    status_code = 200

    def iter_bytes(self, chunk_size: int) -> Iterable[bytes]:
        payload = (
            b'data: {"type":"response.completed","response_id":"fj14-final"}'
            b"\n\ndata: [DONE]\n\n"
        )
        for offset in range(0, len(payload), chunk_size):
            yield payload[offset : offset + chunk_size]


class _Fj14ResponseContext(AbstractContextManager[_Fj14Response]):
    def __enter__(self) -> _Fj14Response:
        return _Fj14Response()

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        return False


class _Fj14Transport:
    def stream(self, request: FluffyJawsStreamRequest) -> _Fj14ResponseContext:
        del request
        return _Fj14ResponseContext()


class _Fj14Decoder:
    contract_version = "fj14_dedupe_v1"
    supported_source_types = (EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,)

    def __init__(self, *hits: StrictProviderHit) -> None:
        self._hits = tuple(hits)

    def decode(self, events, *, final_response_id: str) -> FluffyJawsDecodedEvidence:
        del events, final_response_id
        return FluffyJawsDecodedEvidence(hits=self._hits)


def _authorization(
    record: EvidenceRecord,
    _provenance,
    _disposition,
    _query,
    binding: SemanticEvidenceBinding,
    *,
    stance: QuestionEvidenceStance = QuestionEvidenceStance.SUPPORTS,
    claim_keys: list[str] | None = None,
) -> SemanticEvidenceAuthorization:
    source_attestation = SourceNativeEvidenceAttestation(
        binding=binding,
        verification_status=VerificationState.VERIFIED_REVISION,
        source_revision=record.product_version,
        verification_method="FIXTURE_PINNED_REVISION",
        verifier_id="fixture-source-verifier",
        verifier_version="1.0.0",
        verified_at=_STAMP,
        reason_code="FIXTURE_SOURCE_VERIFIED",
    )
    decisive = stance in {
        QuestionEvidenceStance.SUPPORTS,
        QuestionEvidenceStance.CONTRADICTS,
    }
    assessment = QuestionEvidenceAssessment(
        binding=binding,
        source_attestation_id=source_attestation.attestation_id,
        stance=stance,
        assessed_content_sha256=record.content_sha256,
        assessment_confidence=0.9 if decisive else 0.7,
        claim_keys=(
            list(
                [f"claim:{binding.question_id}"]
                if claim_keys is None
                else claim_keys
            )
            if decisive
            else list(claim_keys or [])
        ),
        assessment_method="FIXTURE_QUESTION_ENTAILMENT",
        assessor_id="fixture-question-assessor",
        assessor_version="1.0.0",
        assessed_at=_STAMP,
        expires_at="2027-08-29T00:00:00Z",
        reason_code=f"FIXTURE_{stance.value}",
    )
    return SemanticEvidenceAuthorization(
        source_attestation=source_attestation,
        question_assessment=assessment,
    )


def _authorization_with_confidence(
    confidence: float,
    *,
    assessed_at: str = _STAMP,
):
    def authorize(record, provenance, disposition, query, binding):
        authorization = _authorization(
            record,
            provenance,
            disposition,
            query,
            binding,
        )
        attestation = SourceNativeEvidenceAttestation.model_validate(
            {
                **authorization.source_attestation.model_dump(mode="json"),
                "attestation_id": "",
                "verified_at": assessed_at,
            }
        )
        assessment = QuestionEvidenceAssessment.model_validate(
            {
                **authorization.question_assessment.model_dump(mode="json"),
                "assessment_id": "",
                "assessment_confidence": confidence,
                "source_attestation_id": attestation.attestation_id,
                "assessed_at": assessed_at,
            }
        )
        return SemanticEvidenceAuthorization(
            source_attestation=attestation,
            question_assessment=assessment,
        )

    return authorize


def _rebind_handoff(
    handoff: AuthorizedSemanticEvidence,
    *,
    provenance_override=None,
    disposition_override=None,
    **binding_updates: Any,
) -> AuthorizedSemanticEvidence:
    authorization = handoff.authorization
    binding = SemanticEvidenceBinding.model_validate(
        {
            **authorization.source_attestation.binding.model_dump(mode="json"),
            "binding_id": "",
            **binding_updates,
        }
    )
    attestation = SourceNativeEvidenceAttestation.model_validate(
        {
            **authorization.source_attestation.model_dump(mode="json"),
            "attestation_id": "",
            "binding": binding.model_dump(mode="json"),
        }
    )
    assessment = QuestionEvidenceAssessment.model_validate(
        {
            **authorization.question_assessment.model_dump(mode="json"),
            "assessment_id": "",
            "binding": binding.model_dump(mode="json"),
            "source_attestation_id": attestation.attestation_id,
        }
    )
    rebound_authorization = SemanticEvidenceAuthorization(
        source_attestation=attestation,
        question_assessment=assessment,
    )
    return AuthorizedSemanticEvidence(
        authorization=rebound_authorization,
        query=handoff.query,
        provenance=provenance_override or handoff.provenance,
        disposition=disposition_override or handoff.disposition,
    )


def _service(
    *,
    provider: FakeEvidenceProvider,
    attestation_check=None,
) -> ReasoningEvidenceShadowService:
    kwargs = {}
    if attestation_check is not None:
        kwargs["semantic_evidence_authorization_check"] = attestation_check
    return ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            max_questions=50,
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
        **kwargs,
    )


def _request(tenant_id: str = "fj08"):
    return CanonicalTestPlanRuntime().build_request(
        jira_key="GUIDES-80008",
        tenant_id=tenant_id,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def _retrieve(
    *,
    service: ReasoningEvidenceShadowService,
    bundle: CanonicalEvidenceBundle,
    questions: list[MissingQuestion],
    retrievals: list[DirectedRetrievalRecord],
    scope: ScopeResolution | None = None,
):
    return service.retrieve(
        run_id="run-fj08-fusion",
        request=_request(bundle.tenant_id),
        evidence=bundle,
        domains=[DomainActivation(domain=IssueDomain.AUTHORING, confidence=1.0)],
        scope=scope or ScopeResolution(),
        questions=questions,
        local_retrievals=retrievals,
    )


def _single_authorized_result():
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )
    return question, result


def test_attested_sources_fuse_per_question_and_reach_hypothesis_verifier() -> None:
    local = _record()
    product = _question(
        "What official product behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[
            EvidenceSourceType.CUSTOMER_REQUEST,
            EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        ],
    )
    dita = _question(
        "What DITA rule applies?",
        subject=AuthoritySubject.DITA_SEMANTICS,
        source_types=[EvidenceSourceType.DITA_SPECIFICATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[local])
    local_retrievals = [_retrieval(product, [local]), _retrieval(dita)]
    queries: list[Any] = []
    result = _retrieve(
        service=_service(
            provider=_provider(queries),
            attestation_check=_authorization,
        ),
        bundle=bundle,
        questions=[product, dita],
        retrievals=local_retrievals,
    )

    assert {row.evidence_id for row in result.evidence_bundle.records}.issuperset(
        {local.evidence_id}
    )
    assert len(result.evidence_bundle.records) == 3
    by_question = {row.question_id: row for row in result.retrievals}
    trace = result.trace
    assert trace is not None
    assert trace.fused_bundle_id == result.evidence_bundle.bundle_id
    assert len(trace.fused_evidence_ids) == 2
    assert {query.question_id for query in queries} == {
        product.question_id,
        dita.question_id,
    }
    question_text_by_id = {
        product.question_id: product.question,
        dita.question_id: dita.question,
    }
    assert all(
        query.question == question_text_by_id[query.question_id]
        and "generate final uac" not in query.question.casefold()
        and "acceptance criteria" not in query.question.casefold()
        for query in queries
    )
    for call in trace.calls:
        route = next(
            row
            for row in trace.routing_records
            if row.question_id == call.question_id
        )
        assert route.provider_called is True
        assert route.why_fj_called
        assert route.trace_id
        assert call.call_result.status.value == "SUCCESS"
        assert call.call_result.duration_ms == 7
        assert call.semantic_fusion_evaluated is True
        assert len(call.semantic_fusion_evidence_ids) == 1
        assert call.semantic_fusion_rejections == {}
        assert len(call.source_attestation_ids) == 1
        assert len(call.question_assessment_ids) == 1
        assert len(call.semantic_authorization_ids) == 1
        assert set(call.semantic_stances.values()) == {
            QuestionEvidenceStance.SUPPORTS
        }
        assert call.query.question_id == call.question_id
        assert call.query.query_id == call.call_result.query_id
        assert call.query.correlation_id == call.call_result.correlation_id
        call_authorizations = [
            row
            for row in result.semantic_evidence
            if row.authorization.source_attestation.binding.question_id
            == call.question_id
        ]
        assert call_authorizations
        assert all(
            row.authorization.source_attestation.binding.provider_call_id
            == call.call_result.provider_call_id
            for row in call_authorizations
        )
        assert trace.fused_evidence_ids_by_question[call.question_id] == (
            call.semantic_fusion_evidence_ids
        )
        other_question = (
            dita.question_id
            if call.question_id == product.question_id
            else product.question_id
        )
        assert not set(call.semantic_fusion_evidence_ids) & set(
            by_question[other_question].matched_evidence_ids
        )
    assert local.evidence_id in by_question[product.question_id].matched_evidence_ids
    assert by_question[dita.question_id].matched_evidence_ids

    hypotheses, enriched = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [product, dita],
        result.retrievals,
        CanonicalBehaviorModel(
            graph=BehaviorGraph(
                nodes=[
                    BehaviorGraphNode(
                        label=local.source_reference,
                        node_type="EVIDENCE_SOURCE",
                        source_evidence_ids=[local.evidence_id],
                    )
                ]
            )
        ),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert {row.state for row in hypotheses} == {HypothesisState.CONFIRMED}
    provider_ids = set(trace.fused_evidence_ids)
    assert provider_ids.issubset(
        {
            evidence_id
            for row in hypotheses
            for evidence_id in row.supporting_evidence_ids
        }
    )
    assert provider_ids.issubset(
        {
            evidence_id
            for node in enriched.graph.nodes
            if node.node_type == "EVIDENCE_SOURCE"
            for evidence_id in node.source_evidence_ids
        }
    )
    assert all(
        row.verification_status == VerificationState.VERIFIED_REVISION
        and row.evidence_confidence == 0.0
        and row.inspected
        and not row.used
        for row in result.evidence_bundle.records
        if row.evidence_id in provider_ids
    )
    assert "AC-999" not in result.evidence_bundle.model_dump_json()


def test_legacy_boolean_verification_is_not_semantic_attestation() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local = [_retrieval(question)]
    result = _retrieve(
        service=_service(provider=_provider()),
        bundle=bundle,
        questions=[question],
        retrievals=local,
    )

    assert result.evidence_bundle.model_dump(mode="json") == bundle.model_dump(
        mode="json"
    )
    assert [row.model_dump(mode="json") for row in result.retrievals] == [
        row.model_dump(mode="json") for row in local
    ]
    assert result.trace is not None
    call = result.trace.calls[0]
    assert call.semantic_fusion_evidence_ids == []
    assert set(call.semantic_fusion_rejections.values()) == {
        "SEMANTIC_AUTHORIZATION_REQUIRED"
    }
    assert call.discovery_syntheses
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


def test_partial_provider_result_fuses_only_its_authorized_source() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False, truncated=True),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )

    assert result.trace is not None
    assert result.trace.calls[0].call_result.status.value == "PARTIAL"
    assert len(result.semantic_evidence) == 1
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.CONFIRMED


@pytest.mark.parametrize(
    "transport_outcome",
    [
        ProviderTransportOutcome.TIMEOUT,
        ProviderTransportOutcome.AUTH_ERROR,
        ProviderTransportOutcome.RATE_LIMITED,
        ProviderTransportOutcome.PROVIDER_ERROR,
    ],
)
def test_failure_tainted_partial_result_stays_trace_only_and_cannot_cover_question(
    transport_outcome: ProviderTransportOutcome,
) -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local_retrievals = [_retrieval(question)]

    result = _retrieve(
        service=_service(
            provider=_provider(
                include_synthesis=False,
                transport_outcome=transport_outcome,
            ),
            attestation_check=_authorization,
        ),
        bundle=bundle,
        questions=[question],
        retrievals=local_retrievals,
    )

    assert result.trace is not None
    call = result.trace.calls[0]
    assert call.call_result.status.value == "PARTIAL"
    assert call.call_result.accepted_evidence_count == 1
    assert call.evidence_records
    assert call.semantic_fusion_evaluated is True
    assert call.semantic_fusion_evidence_ids == []
    assert set(call.semantic_fusion_rejections.values()) == {
        "PROVIDER_RESULT_NOT_USABLE"
    }
    assert result.trace.fused_evidence_ids == []
    assert result.semantic_evidence == []
    assert result.evidence_bundle.model_dump(mode="json") == bundle.model_dump(
        mode="json"
    )
    assert [row.model_dump(mode="json") for row in result.retrievals] == [
        row.model_dump(mode="json") for row in local_retrievals
    ]

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


def test_one_source_can_be_authorized_independently_for_two_questions() -> None:
    questions = [
        _question(
            "What official behavior applies to the first surface?",
            subject=AuthoritySubject.PRODUCT_CONTRACT,
            source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
        ),
        _question(
            "What official behavior applies to the second surface?",
            subject=AuthoritySubject.PRODUCT_CONTRACT,
            source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
        ),
    ]
    result = _retrieve(
        service=_service(
            provider=_provider(
                include_synthesis=False,
                shared_source=True,
            ),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=questions,
        retrievals=[_retrieval(question) for question in questions],
    )

    assert result.trace is not None
    assert len(result.trace.fused_evidence_ids) == 1
    assert len(result.semantic_evidence) == 2
    evidence_id = result.trace.fused_evidence_ids[0]
    assert all(
        row.matched_evidence_ids == [evidence_id] for row in result.retrievals
    )
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        questions,
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert [row.state for row in hypotheses] == [
        HypothesisState.CONFIRMED,
        HypothesisState.CONFIRMED,
    ]


@pytest.mark.parametrize(
    "stance",
    [QuestionEvidenceStance.IRRELEVANT, QuestionEvidenceStance.AMBIGUOUS],
)
def test_authentic_but_non_decisive_source_remains_trace_only(
    stance: QuestionEvidenceStance,
) -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local = [_retrieval(question)]

    def authorize(
        record,
        provenance,
        disposition,
        query,
        binding,
    ):
        return _authorization(
            record,
            provenance,
            disposition,
            query,
            binding,
            stance=stance,
        )

    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=authorize,
        ),
        bundle=bundle,
        questions=[question],
        retrievals=local,
    )

    assert result.evidence_bundle == bundle
    assert result.retrievals == local
    assert result.semantic_authorizations == []
    assert result.trace is not None
    call = result.trace.calls[0]
    assert call.semantic_stances
    assert set(call.semantic_stances.values()) == {stance}
    assert set(call.semantic_fusion_rejections.values()) == {
        f"QUESTION_ASSESSMENT_{stance.value}"
    }


def test_empty_decisive_claim_assessment_fails_closed() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local = [_retrieval(question)]

    def authorize(
        record,
        provenance,
        disposition,
        query,
        binding,
    ):
        return _authorization(
            record,
            provenance,
            disposition,
            query,
            binding,
            claim_keys=[],
        )

    result = _retrieve(
        service=_service(provider=_provider(), attestation_check=authorize),
        bundle=bundle,
        questions=[question],
        retrievals=local,
    )

    assert result.evidence_bundle == bundle
    assert result.retrievals == local
    assert result.trace is not None
    assert set(result.trace.calls[0].semantic_fusion_rejections.values()) == {
        "SEMANTIC_AUTHORIZATION_INVALID"
    }


def test_question_or_access_binding_replay_fails_closed() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local = [_retrieval(question)]

    def authorize(
        record,
        provenance,
        disposition,
        query,
        binding,
    ):
        altered = SemanticEvidenceBinding.model_validate(
            {
                **binding.model_dump(mode="json"),
                "binding_id": "",
                "principal_scope_sha256": "f" * 64,
            }
        )
        return _authorization(
            record,
            provenance,
            disposition,
            query,
            altered,
        )

    result = _retrieve(
        service=_service(provider=_provider(), attestation_check=authorize),
        bundle=bundle,
        questions=[question],
        retrievals=local,
    )

    assert result.evidence_bundle == bundle
    assert result.retrievals == local
    assert result.trace is not None
    assert set(result.trace.calls[0].semantic_fusion_rejections.values()) == {
        "SEMANTIC_AUTHORIZATION_BINDING_MISMATCH"
    }


def test_unknown_source_currentness_cannot_enter_semantic_fusion() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    local = [_retrieval(question)]
    result = _retrieve(
        service=_service(
            provider=_provider(source_version=""),
            attestation_check=_authorization,
        ),
        bundle=bundle,
        questions=[question],
        retrievals=local,
    )

    assert result.evidence_bundle == bundle
    assert result.retrievals == local
    assert result.trace is not None
    assert set(result.trace.calls[0].semantic_fusion_rejections.values()) == {
        "SEMANTIC_SOURCE_POLICY_REJECTED"
    }


def test_duplicate_source_merge_preserves_local_security_and_lifecycle() -> None:
    base = _record()
    candidate = EvidenceRecord.model_validate(
        {
            **base.model_dump(mode="json"),
            "verification_status": VerificationState.VERIFIED_SOURCE,
            "retrieval_pass": "reasoning-directed-provider",
            "retrieved_by_query": ["query:provider"],
            "lifecycle_status": EvidenceLifecycleStatus.INSPECTED,
            "inspected": True,
            "used": False,
        }
    )
    local = EvidenceRecord.model_validate(
        {
            **base.model_dump(mode="json"),
            "verification_status": VerificationState.VERIFIED_REVISION,
            "retrieval_pass": "local-authoritative",
            "retrieved_by_query": ["query:local"],
            "lifecycle_status": EvidenceLifecycleStatus.USED,
            "inspected": True,
            "used": True,
        }
    )

    merged = ReasoningEvidenceShadowService._merge_assessed_records(
        local,
        candidate,
    )

    assert merged.verification_status == local.verification_status
    assert merged.retrieval_pass == local.retrieval_pass
    assert set(merged.retrieved_by_query) == {
        "query:local",
        "query:provider",
    }
    assert merged.lifecycle_status == local.lifecycle_status
    assert merged.claim_keys == local.claim_keys


def test_fj14_unique_decoded_source_reaches_fusion_graph_and_verifier() -> None:
    duplicate = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:fj14-dedupe-a",
        source_locator="https://experienceleague.adobe.com/fj14#a",
        source_native_id="fj14-dedupe-a",
        text="The first source defines behavior A.",
        source_timestamp=_STAMP,
        source_version="2026.8",
        rank=1,
        raw_provider_reference="fj14:item-1",
    )
    repeated = duplicate.model_copy(
        update={
            "rank": 2,
            "raw_provider_reference": "fj14:item-2",
        }
    )
    unique = StrictProviderHit(
        source_type=EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION,
        source_reference="doc:fj14-dedupe-b",
        source_locator="https://experienceleague.adobe.com/fj14#b",
        source_native_id="fj14-dedupe-b",
        text="The second source defines behavior B.",
        source_timestamp=_STAMP,
        source_version="2026.8",
        rank=3,
        raw_provider_reference="fj14:item-3",
    )
    provider = FluffyJawsKnowledgeProvider(
        config=FluffyJawsProviderConfig(enabled=True, timeout_seconds=30.0),
        transport=_Fj14Transport(),
        citation_decoder=_Fj14Decoder(duplicate, repeated, unique),
        now=lambda: datetime(2026, 8, 29, tzinfo=timezone.utc),
        call_id_factory=lambda: "fj14-call-1",
    )
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            max_questions=5,
            max_results=2,
            retry_max_attempts=1,
        ),
        providers=[provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        semantic_evidence_authorization_check=_authorization,
        query_egress_check=lambda _query, _request_value: True,
    )
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )

    result = _retrieve(
        service=service,
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )

    assert result.trace is not None
    call = result.trace.calls[0]
    expected_ids = {record.evidence_id for record in call.evidence_records}
    assert call.call_result.truncated is False
    assert len(expected_ids) == 2
    assert {record.source_reference for record in call.evidence_records} == {
        "doc:fj14-dedupe-a",
        "doc:fj14-dedupe-b",
    }
    assert {row.raw_provider_reference for row in call.provenance} == {
        "fj14:item-1",
        "fj14:item-2",
        "fj14:item-3",
    }
    assert set(call.semantic_fusion_evidence_ids) == expected_ids

    hypotheses, enriched = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )

    verifier_ids = set(hypotheses[0].supporting_evidence_ids) | set(
        hypotheses[0].contradicting_evidence_ids
    )
    assert verifier_ids == expected_ids
    assert expected_ids.issubset(
        {
            evidence_id
            for node in enriched.graph.nodes
            if node.node_type == "EVIDENCE_SOURCE"
            for evidence_id in node.source_evidence_ids
        }
    )


def test_exact_local_provider_overlap_fuses_and_preserves_local_security() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    empty_bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[])
    discovery = _retrieve(
        service=_service(provider=_provider(include_synthesis=False)),
        bundle=empty_bundle,
        questions=[question],
        retrievals=[_retrieval(question)],
    )
    assert discovery.trace is not None
    provider_record = discovery.trace.calls[0].evidence_records[0]
    local = EvidenceRecord.model_validate(
        {
            **provider_record.model_dump(mode="json"),
            "verification_status": VerificationState.VERIFIED_REVISION,
            "evidence_confidence": 0.6,
            "retrieval_pass": "local-authoritative",
            "retrieved_by_query": ["query:local"],
            "lifecycle_status": EvidenceLifecycleStatus.USED,
            "inspected": True,
            "used": True,
        }
    )
    local_bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[local])

    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=_authorization,
        ),
        bundle=local_bundle,
        questions=[question],
        retrievals=[_retrieval(question, [local])],
    )

    assert result.trace is not None
    call = result.trace.calls[0]
    assert call.overlap_evidence_ids == [local.evidence_id]
    assert call.semantic_fusion_evidence_ids == [local.evidence_id]
    assert [row.evidence_id for row in call.provenance] == [local.evidence_id]
    assert [row.provider for row in call.provenance] == ["fluffyjaws"]
    assert call.trace_sidecar.provenance_ids == [
        call.provenance[0].provenance_id
    ]
    assert len(result.semantic_authorizations) == 1
    merged = result.evidence_bundle.records[0]
    assert merged.evidence_id == local.evidence_id
    assert merged.verification_status == local.verification_status
    assert merged.retrieval_pass == local.retrieval_pass
    assert merged.lifecycle_status == local.lifecycle_status
    assert merged.claim_keys == local.claim_keys
    assert "query:local" in merged.retrieved_by_query
    assert result.trace.calls[0].query.query_id in merged.retrieved_by_query
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
        local_evidence_ids={local.evidence_id},
    )
    assert hypotheses[0].state == HypothesisState.CONFIRMED
    assert hypotheses[0].supporting_evidence_ids == [local.evidence_id]


def test_question_bound_contradiction_is_preserved_as_unresolved() -> None:
    local = _record(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        subject=AuthoritySubject.DITA_SEMANTICS,
        authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        confidence=0.79,
        reference="dita:local",
        text="The governed value is enabled.",
        claim_keys=["claim:governed-value"],
    )
    question = _question(
        "What DITA rule governs the value?",
        subject=AuthoritySubject.DITA_SEMANTICS,
        source_types=[EvidenceSourceType.DITA_SPECIFICATION],
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[local])
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=lambda record, provenance, disposition, query, binding: _authorization(
                record,
                provenance,
                disposition,
                query,
                binding,
                stance=QuestionEvidenceStance.CONTRADICTS,
                claim_keys=["claim:governed-value"],
            ),
        ),
        bundle=bundle,
        questions=[question],
        retrievals=[_retrieval(question, [local])],
    )

    assert result.trace is not None
    provider_id = result.trace.fused_evidence_ids[0]
    assert result.trace.fused_question_stances[question.question_id] == {
        provider_id: QuestionEvidenceStance.CONTRADICTS
    }
    hypotheses, enriched = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == [local.evidence_id]
    assert hypotheses[0].contradicting_evidence_ids == [provider_id]
    contradiction_edges = [
        row
        for row in enriched.graph.edges
        if row.relation == BehaviorRelationType.CONTRADICTED_BY
    ]
    assert len(contradiction_edges) == 1
    assert contradiction_edges[0].provenance_evidence_ids == [provider_id]
    assert contradiction_edges[0].confidence == 0.9


def test_equal_authority_conflict_retains_both_sides_and_graph_lineage() -> None:
    claim_key = "claim:shared-dita-rule"
    local = _record(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        subject=AuthoritySubject.DITA_SEMANTICS,
        authority=AuthorityClass.SPECIFICATION_AUTHORITY,
        confidence=0.79,
        reference="dita:local-authority",
        text="The shared rule resolves to enabled.",
        claim_keys=[claim_key],
    )
    question = _question(
        "What DITA rule governs the shared value?",
        subject=AuthoritySubject.DITA_SEMANTICS,
        source_types=[EvidenceSourceType.DITA_SPECIFICATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=lambda record, provenance, disposition, query, binding: _authorization(
                record,
                provenance,
                disposition,
                query,
                binding,
                claim_keys=[claim_key],
            ),
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[local]),
        questions=[question],
        retrievals=[_retrieval(question, [local])],
    )

    assert result.trace is not None
    provider_id = result.trace.fused_evidence_ids[0]
    assert result.trace.fused_authority_conflicts
    hypotheses, enriched = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == [local.evidence_id]
    assert hypotheses[0].contradicting_evidence_ids == [provider_id]
    assert any(
        row.relation == BehaviorRelationType.CONTRADICTED_BY
        and row.provenance_evidence_ids == [provider_id]
        for row in enriched.graph.edges
    )


def test_currentness_conflict_is_preserved_and_forces_unresolved_state() -> None:
    claim_key = "claim:currentness-sensitive-rule"
    local = _record(
        source_type=EvidenceSourceType.DITA_SPECIFICATION,
        subject=AuthoritySubject.DITA_SEMANTICS,
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        confidence=0.79,
        currentness=CurrentnessState.CONFLICTING_CURRENTNESS,
        reference="dita:conflicting-currentness",
        text="An older source reports the rule as disabled.",
        claim_keys=[claim_key],
    )
    question = _question(
        "What is the current DITA rule?",
        subject=AuthoritySubject.DITA_SEMANTICS,
        source_types=[EvidenceSourceType.DITA_SPECIFICATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=lambda record, provenance, disposition, query, binding: _authorization(
                record,
                provenance,
                disposition,
                query,
                binding,
                claim_keys=[claim_key],
            ),
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[local]),
        questions=[question],
        retrievals=[_retrieval(question, [local])],
    )

    assert result.trace is not None
    assert result.trace.fused_currentness_conflicts == [claim_key]
    provider_id = result.trace.fused_evidence_ids[0]
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == [local.evidence_id]
    assert hypotheses[0].contradicting_evidence_ids == [provider_id]


def test_final_consumer_rejects_expired_semantic_handoff() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )
    handoff = result.semantic_evidence[0]
    authorization = handoff.authorization
    expired_assessment = QuestionEvidenceAssessment.model_validate(
        {
            **authorization.question_assessment.model_dump(mode="json"),
            "assessment_id": "",
            "assessed_at": "2025-01-01T00:00:00Z",
            "expires_at": "2025-01-02T00:00:00Z",
        }
    )
    expired_authorization = SemanticEvidenceAuthorization(
        source_attestation=authorization.source_attestation,
        question_assessment=expired_assessment,
    )
    expired_handoff = AuthorizedSemanticEvidence(
        authorization=expired_authorization,
        query=handoff.query,
        provenance=handoff.provenance,
        disposition=handoff.disposition,
    )

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=[expired_handoff],
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


def test_final_consumer_rejects_principal_replay_and_binding_is_exact() -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )
    handoff = result.semantic_evidence[0]
    binding = handoff.authorization.source_attestation.binding
    record = next(
        row
        for row in result.evidence_bundle.records
        if row.evidence_id == binding.evidence_id
    )
    assert binding.disposition_id == handoff.disposition.disposition_id
    assert binding.provenance_id == handoff.provenance.provenance_id
    assert binding.requirement_authority == record.requirement_authority

    original_request = _request()
    replay_request = type(original_request).model_validate(
        {
            **original_request.model_dump(mode="json"),
            "request_id": "",
            "logical_fingerprint": "",
            "principal": {
                **original_request.principal.model_dump(mode="json"),
                "principal_id": "different-principal",
            },
        }
    )
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=replay_request,
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


@pytest.mark.parametrize(
    "binding_updates",
    [
        {"request_id": "req:replayed-request"},
        {"principal_scope_sha256": "a" * 64},
        {"visibility_sha256": "b" * 64},
        {"version_scope_sha256": "c" * 64},
        {"requirement_authority": AuthorityClass.IMPLEMENTATION_CONFIRMED},
    ],
)
def test_final_consumer_rejects_rebound_authorization_fields(
    binding_updates: dict[str, Any],
) -> None:
    question = _question(
        "What official behavior applies?",
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.OFFICIAL_PRODUCT_DOCUMENTATION],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(include_synthesis=False),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
    )
    rebound = _rebind_handoff(result.semantic_evidence[0], **binding_updates)
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=[rebound],
    )
    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


def test_final_consumer_requires_approved_authority_after_coherent_rebind() -> None:
    question, result = _single_authorized_result()
    handoff = result.semantic_evidence[0]
    original = result.evidence_bundle.records[0]
    downgraded = EvidenceRecord.model_validate(
        {
            **original.model_dump(mode="json"),
            "requirement_authority": AuthorityClass.CUSTOMER_REQUEST,
        }
    )
    rebound = _rebind_handoff(
        handoff,
        requirement_authority=AuthorityClass.CUSTOMER_REQUEST,
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[downgraded])

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=[rebound],
    )
    assert hypotheses[0].supporting_evidence_ids == []
    assert hypotheses[0].state == HypothesisState.UNRESOLVED


def test_final_consumer_requires_applicable_provenance_after_coherent_rebind() -> None:
    question, result = _single_authorized_result()
    handoff = result.semantic_evidence[0]
    non_applicable = type(handoff.provenance).model_validate(
        {
            **handoff.provenance.model_dump(mode="json"),
            "provenance_id": "",
            "applicability": ApplicabilityState.NOT_APPLICABLE,
        }
    )
    rebound = _rebind_handoff(
        handoff,
        provenance_override=non_applicable,
        provenance_id=non_applicable.provenance_id,
    )

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=[rebound],
    )
    assert hypotheses[0].supporting_evidence_ids == []
    assert hypotheses[0].state == HypothesisState.UNRESOLVED


def test_fj15_non_applicable_implementation_evidence_does_not_confirm() -> None:
    scope = ScopeResolution(
        product_versions=["5.0"],
        deployment_modes=["on-prem"],
    )
    question = _question(
        "Which implementation branch handles this behavior for on-prem 5.0?",
        subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_types=[
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CODE_DIFF,
        ],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(
                include_synthesis=False,
                source_version="5.0",
                deployment_model="cloud",
            ),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
        scope=scope,
    )

    assert result.trace is not None
    provider_id = result.trace.fused_evidence_ids[0]
    assert provider_id in result.retrievals[0].matched_evidence_ids
    provider_record = next(
        row for row in result.evidence_bundle.records if row.evidence_id == provider_id
    )
    assert provider_record.deployment_model == "cloud"
    assert result.semantic_evidence
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
        scope=scope,
    )

    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []
    assert hypotheses[0].derived_from_question_id == question.question_id
    assert question.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION
    assert {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
    }.issubset(question.target_source_types)


def test_fj15_unclear_implementation_scope_keeps_github_verification_question() -> None:
    scope = ScopeResolution(
        product_versions=["5.0"],
        deployment_modes=["on-prem"],
    )
    question = _question(
        "Which implementation branch handles this behavior for on-prem 5.0?",
        subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_types=[
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.CURRENT_PR,
            EvidenceSourceType.IMPLEMENTATION_DIFF,
            EvidenceSourceType.CODE_DIFF,
        ],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(
                include_synthesis=False,
                source_version="5.0",
                deployment_model="",
            ),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
        scope=scope,
    )

    assert result.trace is not None
    assert result.trace.fused_evidence_ids
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
        scope=scope,
    )

    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []
    assert hypotheses[0].derived_from_question_id == question.question_id
    assert question.authority_subject == AuthoritySubject.ACTUAL_IMPLEMENTATION
    assert {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
    } == set(question.target_source_types)


def test_fj15_wrong_version_local_implementation_evidence_does_not_confirm() -> None:
    scope = ScopeResolution(
        product_versions=["5.0"],
        deployment_modes=["on-prem"],
    )
    question = _question(
        "Which implementation branch handles this behavior for on-prem 5.0?",
        subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_types=[EvidenceSourceType.CURRENT_CODE],
    )
    local = _record(
        source_type=EvidenceSourceType.CURRENT_CODE,
        subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        authority=AuthorityClass.IMPLEMENTATION_CONFIRMED,
        confidence=0.95,
        currentness=CurrentnessState.VERSION_SPECIFIC,
        verification=VerificationState.VERIFIED_REVISION,
        product_version="4.6",
        deployment_model="on-prem",
        reference="github:shared-processor@4.6",
        text="The shared processor enables the behavior for on-prem 4.6.",
    )

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        CanonicalEvidenceBundle(tenant_id="fj08", records=[local]),
        [question],
        [_retrieval(question, [local])],
        CanonicalBehaviorModel(),
        scope=scope,
    )

    assert hypotheses[0].state == HypothesisState.UNRESOLVED
    assert hypotheses[0].supporting_evidence_ids == []


def test_fj15_applicable_implementation_evidence_confirms() -> None:
    scope = ScopeResolution(
        product_versions=["5.0"],
        deployment_modes=["on-prem"],
    )
    question = _question(
        "Which implementation branch handles this behavior for on-prem 5.0?",
        subject=AuthoritySubject.ACTUAL_IMPLEMENTATION,
        source_types=[
            EvidenceSourceType.CURRENT_CODE,
            EvidenceSourceType.CURRENT_PR,
        ],
    )
    result = _retrieve(
        service=_service(
            provider=_provider(
                include_synthesis=False,
                source_version="5.0",
                deployment_model="on-prem",
            ),
            attestation_check=_authorization,
        ),
        bundle=CanonicalEvidenceBundle(tenant_id="fj08", records=[]),
        questions=[question],
        retrievals=[_retrieval(question)],
        scope=scope,
    )

    assert result.trace is not None
    provider_id = result.trace.fused_evidence_ids[0]
    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        result.evidence_bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
        scope=scope,
    )

    assert hypotheses[0].state == HypothesisState.CONFIRMED
    assert hypotheses[0].supporting_evidence_ids == [provider_id]


@pytest.mark.parametrize(
    "record_updates",
    [
        {
            "lifecycle_status": EvidenceLifecycleStatus.USED,
            "inspected": True,
            "used": True,
        },
        {"verification_status": VerificationState.VERIFIED_LIVE},
    ],
)
def test_final_consumer_requires_pre_citation_provider_state(
    record_updates: dict[str, Any],
) -> None:
    question, result = _single_authorized_result()
    original = result.evidence_bundle.records[0]
    mutated = EvidenceRecord.model_validate(
        {
            **original.model_dump(mode="json"),
            **record_updates,
        }
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj08", records=[mutated])

    hypotheses, _model = CANONICAL_REASONING_SERVICE.verify_hypotheses(
        bundle,
        [question],
        result.retrievals,
        CanonicalBehaviorModel(),
        request=_request(),
        semantic_evidence=result.semantic_evidence,
    )
    assert hypotheses[0].supporting_evidence_ids == []
    assert hypotheses[0].state == HypothesisState.UNRESOLVED


def _baseline_fixture(index: int) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return rows[index], rows[index]["fixture"]


def test_runtime_fuses_only_routed_questions_without_generating_uac() -> None:
    baseline, fixture = _baseline_fixture(3)
    disabled_runtime = CanonicalTestPlanRuntime()
    disabled_request = disabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request,
        packet=fixture,
    )

    queries: list[Any] = []
    runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(
            provider=_provider(queries),
            attestation_check=_authorization,
        )
    )
    request = runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    enabled = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_fluffyjaws_shadow_trace()
    question_trace = get_last_question_retrieval_trace()

    routed = {
        "question:8a824a3977bb334effaddac629f29603",
        "question:c025e80d42afc559195e77cd643d1e3a",
    }
    assert trace is not None
    assert question_trace is not None
    assert set(trace.dispatched_question_ids) == routed
    assert {query.question_id for query in queries} == routed
    assert set(trace.fused_evidence_ids_by_question) == routed
    assert set(trace.consumed_evidence_ids) == set(trace.fused_evidence_ids)
    assert enabled.evidence_bundle_id == trace.fused_bundle_id
    by_question = {row.question_id: row for row in question_trace.questions}
    assert set(by_question) == {
        row["question_id"] for row in enabled.output_payload["missing_questions"]
    }
    for question_id in routed:
        row = by_question[question_id]
        assert row.fluffyjaws_called.state == TraceAnswerState.YES
        assert row.fluffyjaws_status.state == TraceAnswerState.YES
        assert row.evidence_normalized.state == TraceAnswerState.YES
        assert row.evidence_used_by_verifier.state == TraceAnswerState.YES
        assert row.provider_call_ids
        assert all(call.semantic_fusion_evaluated for call in row.provider_calls)
        assert all(call.fused_evidence_ids for call in row.provider_calls)
        assert all(call.consumed_evidence_ids for call in row.provider_calls)
        assert all(
            evidence.used_by_verifier
            and evidence.semantic_fusion_state.value == "FUSED"
            for evidence in row.fluffyjaws_evidence
        )
        assert row.final_output_location.state == TraceAnswerState.YES
    assert enabled.trace.evidence_bundle_id == enabled.evidence_bundle_id
    assert set(disabled.evidence_bundle.source_manifest[i].evidence_id for i in range(len(disabled.evidence_bundle.source_manifest))).issubset(
        {row.evidence_id for row in enabled.evidence_bundle.records}
    )
    assert all(
        row.used
        for row in enabled.evidence_bundle.records
        if row.evidence_id in set(trace.fused_evidence_ids)
    )
    local_by_question = {
        row["question_id"]: row for row in baseline["retrieval_queries"]
    }
    enabled_by_question = {
        row["question_id"]: row
        for row in enabled.output_payload["directed_retrievals"]
    }
    for question_id, local in local_by_question.items():
        if question_id not in routed:
            assert enabled_by_question[question_id] == local
        else:
            assert set(local["matched_evidence_ids"]).issubset(
                enabled_by_question[question_id]["matched_evidence_ids"]
            )
            assert set(trace.fused_evidence_ids_by_question[question_id]).issubset(
                enabled_by_question[question_id]["matched_evidence_ids"]
            )
    assert enabled.output_payload["acceptance_candidates"] == disabled.output_payload[
        "acceptance_candidates"
    ]
    assert enabled.output_payload["promotion_decisions"] == disabled.output_payload[
        "promotion_decisions"
    ]
    assert enabled.gate_decisions == disabled.gate_decisions
    assert len(enabled.trace.stage_trace) == len(disabled.trace.stage_trace) == 17
    assert [row.stage for row in enabled.trace.stage_trace] == [
        row.stage for row in disabled.trace.stage_trace
    ]
    serialized = enabled.model_dump_json()
    assert "AC-999" not in serialized
    assert "generate a final UAC" not in serialized
    assert FLUFFYJAWS_SHADOW_TRACE_SCHEMA not in serialized


@pytest.mark.parametrize("baseline_index", range(5))
def test_fj18_controls_second_pass_influence_for_every_fj00_fixture(
    baseline_index: int,
) -> None:
    _baseline, fixture = _baseline_fixture(baseline_index)
    disabled_runtime = CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
            )
        )
    )
    disabled_request = disabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-fj18",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request,
        packet=fixture,
    )
    disabled_question_trace = get_last_question_retrieval_trace()

    second_pass_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(
            provider=_provider(),
            attestation_check=_authorization,
        )
    )
    second_pass_request = second_pass_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-fj18",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    second_pass = second_pass_runtime.generate_backend_compatibility(
        request=second_pass_request,
        packet=fixture,
    )
    second_pass_question_trace = get_last_question_retrieval_trace()
    fluffyjaws_trace = get_last_fluffyjaws_shadow_trace()
    automatic_decision = get_last_second_pass_influence_decision()

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=second_pass,
        disabled_question_trace=disabled_question_trace,
        second_pass_question_trace=second_pass_question_trace,
        fluffyjaws_trace=fluffyjaws_trace,
    )

    assert decision.status == SecondPassInfluenceStatus.PASSED, (
        decision.blocking_reason_codes
    )
    assert automatic_decision is not None
    assert automatic_decision.status == SecondPassInfluenceStatus.PASSED
    assert decision.blocking_reason_codes == ()
    assert decision.rollback_applied is False
    assert decision.questions_unchanged is True
    assert decision.acceptance_output_unchanged is True
    assert selected.output_sha256 == second_pass.output_sha256
    assert second_pass.output_payload["missing_questions"] == disabled.output_payload[
        "missing_questions"
    ]
    assert second_pass.output_payload["acceptance_candidates"] == (
        disabled.output_payload["acceptance_candidates"]
    )
    assert second_pass.output_payload["promotion_decisions"] == (
        disabled.output_payload["promotion_decisions"]
    )
    if decision.provider_consumed_evidence_ids:
        assert decision.influence_lineages
        assert {
            evidence_id
            for lineage in decision.influence_lineages
            for evidence_id in lineage.provider_evidence_ids
        } == set(decision.provider_consumed_evidence_ids)
    else:
        assert baseline_index == 4
        assert decision.influence_lineages == ()


def test_fj18_unexplained_output_growth_rolls_back_to_disabled_result() -> None:
    _baseline, fixture = _baseline_fixture(3)
    disabled_runtime = CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
            )
        )
    )
    request = disabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-fj18-rollback",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=request,
        packet=fixture,
    )
    disabled_question_trace = get_last_question_retrieval_trace()

    runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(
            provider=_provider(),
            attestation_check=_authorization,
        )
    )
    second_pass = runtime.generate_backend_compatibility(
        request=request,
        packet=fixture,
    )
    second_pass_question_trace = get_last_question_retrieval_trace()
    fluffyjaws_trace = get_last_fluffyjaws_shadow_trace()

    plan_payload = second_pass.structured_plan.model_dump(mode="json")
    target_section = next(
        row
        for row in plan_payload["sections"]
        if row["section_key"] != "acceptance_contract"
    )
    target_section["items"].append("Untraced provider-created regression check.")
    output_payload = second_pass.output_payload.copy()
    output_payload["structured_plan"] = plan_payload
    mutated = second_pass.model_copy(
        update={
            "structured_plan": type(second_pass.structured_plan).model_validate(
                plan_payload
            ),
            "output_payload": output_payload,
            "output_sha256": "0" * 64,
        }
    )

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=mutated,
        disabled_question_trace=disabled_question_trace,
        second_pass_question_trace=second_pass_question_trace,
        fluffyjaws_trace=fluffyjaws_trace,
    )

    assert decision.status == SecondPassInfluenceStatus.BLOCKED
    assert decision.rollback_applied is True
    assert SecondPassInfluenceReason.UNEXPLAINED_OUTPUT_GROWTH in (
        decision.blocking_reason_codes
    )
    assert selected.output_sha256 == disabled.output_sha256


def _fj18_pair(index: int = 3):
    _baseline, fixture = _baseline_fixture(index)
    request = CanonicalTestPlanRuntime().build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-fj18-mutations",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled_runtime = CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
            )
        )
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=request,
        packet=fixture,
    )
    disabled_trace = get_last_question_retrieval_trace()
    enabled_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(
            provider=_provider(),
            attestation_check=_authorization,
        )
    )
    enabled = enabled_runtime.generate_backend_compatibility(
        request=request,
        packet=fixture,
    )
    enabled_trace = get_last_question_retrieval_trace()
    provider_trace = get_last_fluffyjaws_shadow_trace()
    return disabled, enabled, disabled_trace, enabled_trace, provider_trace


def _render_plan_for_fj18(plan: StructuredQEPlan) -> str:
    lines = [f"# {plan.jira_key} — QE plan", ""]
    for section in plan.sections:
        lines.extend([f"## {section.title}", ""])
        lines.extend(f"- {item}" for item in section.items)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _coherent_plan_mutation(second_pass, plan_payload):
    plan = StructuredQEPlan.model_validate(plan_payload)
    output_payload = deepcopy(second_pass.output_payload)
    output_payload["structured_plan"] = plan.model_dump(mode="json")
    output_payload["plan_markdown"] = _render_plan_for_fj18(plan)
    return second_pass.model_copy(
        update={
            "structured_plan": plan,
            "output_payload": output_payload,
            "structured_output": deepcopy(output_payload),
            "rendered_output": output_payload["plan_markdown"],
            "output_sha256": stable_sha256(output_payload),
        }
    )


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("rendered_only", SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH),
        ("remove_item", SecondPassInfluenceReason.UNEXPLAINED_OUTPUT_REMOVAL),
        ("swap_sections", SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH),
        ("acceptance_lineage", SecondPassInfluenceReason.ACCEPTANCE_LINEAGE_CHANGED),
        ("contract_mode", SecondPassInfluenceReason.PLAN_CONTRACT_CHANGED),
    ],
)
def test_fj18_rolls_back_public_output_and_contract_mutations(
    mutation: str,
    expected_reason: SecondPassInfluenceReason,
) -> None:
    disabled, enabled, disabled_trace, enabled_trace, provider_trace = _fj18_pair()
    if mutation == "rendered_only":
        mutated = enabled.model_copy(
            update={"rendered_output": enabled.rendered_output + "\nAC-999\n"}
        )
    else:
        plan_payload = enabled.structured_plan.model_dump(mode="json")
        if mutation == "remove_item":
            section = next(
                row
                for row in plan_payload["sections"]
                if row["section_key"] == "issue_understanding"
            )
            section["items"].pop(0)
        elif mutation == "swap_sections":
            plan_payload["sections"][0], plan_payload["sections"][1] = (
                plan_payload["sections"][1],
                plan_payload["sections"][0],
            )
        elif mutation == "acceptance_lineage":
            section = next(
                row
                for row in plan_payload["sections"]
                if row["section_key"] == "acceptance_contract"
            )
            section["source_record_ids"] = []
        elif mutation == "contract_mode":
            plan_payload["contract_mode"] = ContractMode.HUMAN_ACCEPTED_CONTRACT
        mutated = _coherent_plan_mutation(enabled, plan_payload)

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=mutated,
        disabled_question_trace=disabled_trace,
        second_pass_question_trace=enabled_trace,
        fluffyjaws_trace=provider_trace,
    )

    assert decision.status == SecondPassInfluenceStatus.BLOCKED
    assert expected_reason in decision.blocking_reason_codes
    assert decision.rollback_applied is True
    assert selected is disabled


def test_fj18_malformed_dynamic_projection_fails_closed_without_exception() -> None:
    disabled, enabled, disabled_trace, enabled_trace, provider_trace = _fj18_pair()
    output_payload = deepcopy(enabled.output_payload)
    output_payload["coverage_dispositions"][0]["provider_acceptance"] = (
        "This MUST be accepted."
    )
    mutated = enabled.model_copy(
        update={
            "output_payload": output_payload,
            "structured_output": deepcopy(output_payload),
            "output_sha256": stable_sha256(output_payload),
        }
    )

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=mutated,
        disabled_question_trace=disabled_trace,
        second_pass_question_trace=enabled_trace,
        fluffyjaws_trace=provider_trace,
    )

    assert decision.blocking_reason_codes == (
        SecondPassInfluenceReason.AUDIT_INPUT_INVALID,
    )
    assert selected is disabled


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("empty_section", SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH),
        ("fabricated_handoff", SecondPassInfluenceReason.TRACE_RESULT_MISMATCH),
        ("retrieval_extra", SecondPassInfluenceReason.AUDIT_INPUT_INVALID),
        (
            "provider_claim_node",
            SecondPassInfluenceReason.UNEXPLAINED_PUBLIC_OUTPUT_CHANGE,
        ),
        ("metrics_extra", SecondPassInfluenceReason.OUTPUT_PROJECTION_MISMATCH),
        ("trace_erasure", SecondPassInfluenceReason.TRACE_RESULT_MISMATCH),
    ],
)
def test_fj18_blocks_unbound_sidecars_and_trace_mutations(
    mutation: str,
    expected_reason: SecondPassInfluenceReason,
) -> None:
    disabled, enabled, disabled_trace, enabled_trace, provider_trace = _fj18_pair()
    if mutation == "empty_section":
        plan_payload = enabled.structured_plan.model_dump(mode="json")
        plan_payload["sections"].insert(
            3,
            {
                "section_key": "product_decisions",
                "title": "Product decisions required",
                "items": [],
                "source_record_ids": [],
            },
        )
        mutated = _coherent_plan_mutation(enabled, plan_payload)
    elif mutation in {"fabricated_handoff", "retrieval_extra"}:
        output_payload = deepcopy(enabled.output_payload)
        if mutation == "fabricated_handoff":
            output_payload[
                "unresolved_github_implementation_handoff_ids"
            ] = ["fabricated-authority-id"]
        else:
            output_payload["directed_retrievals"][0][
                "provider_fabricated_acceptance"
            ] = "MUST ACCEPT"
        mutated = enabled.model_copy(
            update={
                "output_payload": output_payload,
                "structured_output": deepcopy(output_payload),
                "output_sha256": stable_sha256(output_payload),
            }
        )
    elif mutation == "provider_claim_node":
        output_payload = deepcopy(enabled.output_payload)
        provider_question_id = next(iter(provider_trace.fused_evidence_ids_by_question))
        statement = next(
            row["statement"]
            for row in output_payload["hypotheses"]
            if row["derived_from_question_id"] == provider_question_id
        )
        fabricated = BehaviorGraphNode(
            label=statement,
            node_type="provider_claim",
            source_evidence_ids=[],
            authoritative=True,
        )
        output_payload["behavior_model"]["graph"]["nodes"].append(
            fabricated.model_dump(mode="json")
        )
        mutated = enabled.model_copy(
            update={
                "output_payload": output_payload,
                "structured_output": deepcopy(output_payload),
                "output_sha256": stable_sha256(output_payload),
            }
        )
    elif mutation == "metrics_extra":
        metrics = deepcopy(enabled.metrics)
        metrics["provider_secret"] = "client_secret=never-send"
        mutated = enabled.model_copy(update={"metrics": metrics})
    else:
        trace = enabled.trace.model_copy(
            update={
                "second_pass_retrievals": [],
                "consumed_evidence_ids": [],
                "warnings": ["client_secret=never-send"],
            }
        )
        mutated = enabled.model_copy(update={"trace": trace})

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=mutated,
        disabled_question_trace=disabled_trace,
        second_pass_question_trace=enabled_trace,
        fluffyjaws_trace=provider_trace,
    )

    assert decision.status == SecondPassInfluenceStatus.BLOCKED
    assert expected_reason in decision.blocking_reason_codes
    assert selected is disabled


def test_fj18_blocks_cross_question_provider_evidence_reassignment() -> None:
    disabled, enabled, disabled_trace, enabled_trace, provider_trace = _fj18_pair()
    question_ids = list(provider_trace.fused_evidence_ids_by_question)
    assert len(question_ids) >= 2
    tampered_trace = provider_trace.model_copy(deep=True)
    first, second = question_ids[:2]
    tampered_trace.fused_evidence_ids_by_question[first], (
        tampered_trace.fused_evidence_ids_by_question[second]
    ) = (
        tampered_trace.fused_evidence_ids_by_question[second],
        tampered_trace.fused_evidence_ids_by_question[first],
    )

    selected, decision = select_controlled_second_pass_result(
        disabled_result=disabled,
        second_pass_result=enabled,
        disabled_question_trace=disabled_trace,
        second_pass_question_trace=enabled_trace,
        fluffyjaws_trace=tampered_trace,
    )

    assert SecondPassInfluenceReason.PROVIDER_EVIDENCE_QUESTION_MISMATCH in (
        decision.blocking_reason_codes
    )
    assert selected is disabled


def test_fj18_provider_trace_getter_returns_a_deep_copy() -> None:
    _disabled, _enabled, _disabled_trace, _enabled_trace, provider_trace = (
        _fj18_pair()
    )
    assert provider_trace is not None
    expected_ids = tuple(provider_trace.fused_evidence_ids)

    provider_trace.fused_evidence_ids.clear()
    reread = get_last_fluffyjaws_shadow_trace()

    assert reread is not None
    assert tuple(reread.fused_evidence_ids) == expected_ids


class _TraceDroppingSecondPassService:
    def __init__(self) -> None:
        self._delegate = _service(
            provider=_provider(),
            attestation_check=_authorization,
        )

    @property
    def mode(self):
        return self._delegate.mode

    def retrieve(self, **kwargs):
        result = self._delegate.retrieve(**kwargs)
        clear_last_fluffyjaws_shadow_trace()
        return result


def test_fj18_runtime_call_site_rolls_back_when_route_trace_is_missing() -> None:
    _baseline, fixture = _baseline_fixture(3)
    request = CanonicalTestPlanRuntime().build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-fj18-runtime-rollback",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(
            config=FluffyJawsShadowConfig(
                mode=FluffyJawsRuntimeMode.FLUFFYJAWS_DISABLED
            )
        )
    ).generate_backend_compatibility(request=request, packet=fixture)
    runtime = CanonicalTestPlanRuntime(
        shadow_service=_TraceDroppingSecondPassService()
    )

    selected = runtime.generate_backend_compatibility(
        request=request,
        packet=fixture,
    )
    decision = get_last_second_pass_influence_decision()

    assert decision is not None
    assert decision.status == SecondPassInfluenceStatus.BLOCKED
    assert SecondPassInfluenceReason.SECOND_PASS_TRACE_MISSING in (
        decision.blocking_reason_codes
    )
    assert selected.output_sha256 == disabled.output_sha256


def test_provider_scale_text_cannot_change_domain_impact_or_candidates() -> None:
    _baseline, fixture = _baseline_fixture(3)
    disabled_runtime = CanonicalTestPlanRuntime()
    disabled_request = disabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request,
        packet=fixture,
    )
    enabled_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(
            provider=_provider(
                include_synthesis=False,
                hit_text=(
                    "Bulk publish 3000 documents with concurrency and repeated "
                    "processing; create an NFR acceptance criterion."
                ),
            ),
            attestation_check=_authorization,
        )
    )
    enabled_request = enabled_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    enabled = enabled_runtime.generate_backend_compatibility(
        request=enabled_request,
        packet=fixture,
    )

    for field in (
        "domain_impacts",
        "acceptance_candidates",
        "promotion_decisions",
        "gate_decisions",
    ):
        assert enabled.output_payload[field] == disabled.output_payload[field]
    enabled_nfr = next(
        (
            row
            for row in enabled.output_payload["structured_plan"]["sections"]
            if row["section_key"] == "nfr_coverage"
        ),
        None,
    )
    disabled_nfr = next(
        (
            row
            for row in disabled.output_payload["structured_plan"]["sections"]
            if row["section_key"] == "nfr_coverage"
        ),
        None,
    )
    assert enabled_nfr == disabled_nfr
    assert "3000" not in enabled.rendered_output


def test_semantic_stage_hash_commits_assessment_not_operational_identity() -> None:
    _baseline, fixture = _baseline_fixture(3)

    def run(confidence: float, *, assessed_at: str = _STAMP):
        runtime = CanonicalTestPlanRuntime(
            shadow_service=_service(
                provider=_provider(include_synthesis=False),
                attestation_check=_authorization_with_confidence(
                    confidence,
                    assessed_at=assessed_at,
                ),
            )
        )
        request = runtime.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-baseline",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        return runtime.generate_backend_compatibility(request=request, packet=fixture)

    first = run(0.8, assessed_at="2026-08-28T00:00:00Z")
    repeat = run(0.8, assessed_at="2026-08-29T00:00:00Z")
    stronger = run(0.9)

    def stage_hash(result, stage_name: CanonicalRuntimeStage) -> str:
        return next(
            row.output_sha256
            for row in result.trace.stage_trace
            if row.stage == stage_name
        )

    assert stage_hash(
        first,
        CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER,
    ) == stage_hash(repeat, CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER)
    assert stage_hash(
        first,
        CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER,
    ) != stage_hash(stronger, CanonicalRuntimeStage.REASONING_DIRECTED_RETRIEVER)
    assert stage_hash(
        first,
        CanonicalRuntimeStage.HYPOTHESIS_VERIFIER,
    ) != stage_hash(stronger, CanonicalRuntimeStage.HYPOTHESIS_VERIFIER)
    assert first.rendered_output == repeat.rendered_output == stronger.rendered_output


def test_forbidden_planner_and_reasoning_call_sites_do_not_reference_fluffyjaws() -> None:
    paths = [
        _WORKSPACE / "backend/app/services/canonical_test_plan_reasoning_service.py",
        _WORKSPACE / ".codex/skills/test-plan-generation/SKILL.md",
        _WORKSPACE / ".claude/skills/test-plan-generation/SKILL.md",
        _WORKSPACE / "skills/test-plan-generation/SKILL.md",
    ]
    for path in paths:
        source = path.read_text(encoding="utf-8").casefold()
        assert "fluffyjaws" not in source
        assert "reasoningevidenceshadowservice" not in source
