"""FJ-07 conservative SECOND_PASS routing and plan-isolation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.schemas_canonical_test_plan_runtime import (
    AuthorityClass,
    AuthorityResolution,
    AuthoritySubject,
    CanonicalEvidenceBundle,
    CurrentnessState,
    DirectedRetrievalRecord,
    DomainActivation,
    EvidenceRecord,
    EvidenceSourceType,
    GenerationProfile,
    IssueDomain,
    MissingQuestion,
    ResolutionState,
    RetrievalStatus,
    RuntimeEntryPoint,
    ScopeResolution,
    SourceVisibility,
    VerificationState,
    stable_sha256,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.fluffyjaws_routing_policy import (
    ConservativeFluffyJawsRoutingPolicy,
    FluffyJawsNoCallReason,
    FluffyJawsRoutingRecord,
    FluffyJawsRoutingSignal,
)
from app.services.reasoning_evidence_provider import (
    DiscoverySynthesis,
    EvidenceProviderDescriptor,
    EvidenceProviderExecutor,
    EvidenceProviderRawResult,
    FakeEvidenceProvider,
    ProviderCacheState,
    ProviderTransportOutcome,
    QueryMateriality,
    StrictProviderHit,
    active_query_filters,
)
from app.services.reasoning_evidence_shadow_service import (
    FLUFFYJAWS_SHADOW_TRACE_SCHEMA,
    FluffyJawsRuntimeMode,
    FluffyJawsShadowConfig,
    ReasoningEvidenceShadowService,
    get_last_fluffyjaws_shadow_trace,
)


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_PROVIDER = "fluffyjaws"
_CONTRACT = "fake-fluffyjaws-routing-v1"
_STAMP = "2026-08-30T00:00:00Z"
_POLICY = ConservativeFluffyJawsRoutingPolicy()


def _evidence(
    *,
    tenant_id: str = "fj07",
    source_type: EvidenceSourceType = EvidenceSourceType.DITA_SPECIFICATION,
    subject: AuthoritySubject = AuthoritySubject.DITA_SEMANTICS,
    authority: AuthorityClass = AuthorityClass.SPECIFICATION_AUTHORITY,
    confidence: float = 0.8,
    verification: VerificationState = VerificationState.VERIFIED_SOURCE,
    currentness: CurrentnessState = CurrentnessState.CURRENT,
    reference: str = "source:one",
    content: str = "Authoritative behavior evidence.",
    claim_keys: list[str] | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        source_type=source_type,
        authority_subject=subject,
        source_reference=reference,
        tenant_id=tenant_id,
        content={"text": content},
        currentness=currentness,
        evidence_confidence=confidence,
        requirement_authority=authority,
        verification_status=verification,
        visibility=SourceVisibility(tenant_id=tenant_id),
        claim_keys=list(claim_keys or []),
    )


def _question(
    text: str = "What behavior is defined by the authoritative source?",
    *,
    subject: AuthoritySubject = AuthoritySubject.DITA_SEMANTICS,
    source_types: list[EvidenceSourceType] | None = None,
    blocking: bool = False,
) -> MissingQuestion:
    return MissingQuestion(
        question=text,
        authority_subject=subject,
        target_source_types=(
            [EvidenceSourceType.DITA_SPECIFICATION]
            if source_types is None
            else source_types
        ),
        blocking=blocking,
    )


def _retrieval(
    question: MissingQuestion,
    *records: EvidenceRecord,
    status: RetrievalStatus | None = None,
) -> DirectedRetrievalRecord:
    resolved_status = status or (
        RetrievalStatus.USED if records else RetrievalStatus.UNAVAILABLE
    )
    return DirectedRetrievalRecord(
        question_id=question.question_id,
        query=question.question,
        authority_subject=question.authority_subject,
        target_source_types=question.target_source_types,
        matched_evidence_ids=[record.evidence_id for record in records],
        status=resolved_status,
    )


def _evaluate(
    question: MissingQuestion,
    bundle: CanonicalEvidenceBundle,
    local: DirectedRetrievalRecord | None,
    materiality: QueryMateriality = QueryMateriality.P1,
):
    return _POLICY.evaluate(
        question=question,
        local=local,
        bundle=bundle,
        materiality=materiality,
    )


def _descriptor() -> EvidenceProviderDescriptor:
    return EvidenceProviderDescriptor(
        provider=_PROVIDER,
        adapter_version="fake-v1",
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


def _subject_matches(source_type: EvidenceSourceType, subject: AuthoritySubject) -> bool:
    if source_type in {
        EvidenceSourceType.DITA_SPECIFICATION,
        EvidenceSourceType.DITA_OT_DOCUMENTATION,
    }:
        return subject == AuthoritySubject.DITA_SEMANTICS
    if source_type in {
        EvidenceSourceType.CURRENT_CODE,
        EvidenceSourceType.CURRENT_PR,
        EvidenceSourceType.IMPLEMENTATION_DIFF,
        EvidenceSourceType.CODE_DIFF,
        EvidenceSourceType.EXISTING_AUTOMATION,
    }:
        return subject == AuthoritySubject.ACTUAL_IMPLEMENTATION
    if source_type in {
        EvidenceSourceType.UI_OBSERVATION,
        EvidenceSourceType.OBSERVED_UI_FLOW,
        EvidenceSourceType.SCREENSHOT_REPRODUCTION,
    }:
        return subject == AuthoritySubject.CURRENT_UI
    return subject == AuthoritySubject.PRODUCT_CONTRACT


def _provider(*, include_hit: bool = False) -> FakeEvidenceProvider:
    def result_factory(query, context) -> EvidenceProviderRawResult:
        call_id = EvidenceProviderExecutor._call_id(
            _PROVIDER, query.query_id, context.correlation_id
        )
        source_type = next(
            (
                candidate
                for candidate in query.requested_evidence_types
                if _subject_matches(candidate, query.authority_requirement.subject)
                and candidate
                not in {
                    EvidenceSourceType.ACCEPTED_UAC,
                    EvidenceSourceType.ENGINEERING_DECISION,
                    EvidenceSourceType.JIRA_ACCEPTANCE_CRITERIA,
                    EvidenceSourceType.JIRA_DESCRIPTION,
                    EvidenceSourceType.PRODUCT_DECISION,
                    EvidenceSourceType.CURRENT_JIRA,
                    EvidenceSourceType.USER_FEEDBACK,
                }
            ),
            None,
        )
        hits = []
        if include_hit and source_type is not None:
            hits.append(
                StrictProviderHit(
                    source_type=source_type,
                    source_reference=f"fj07-source:{query.question_id}",
                    source_locator=f"fj07-citation:{query.question_id}",
                    text="MUST create a new acceptance criterion automatically.",
                    rank=1,
                    retrieval_score=0.99,
                    raw_provider_reference=f"fj07-hit:{query.question_id}",
                )
            )
        synthesis = DiscoverySynthesis(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            text="MUST add AC-999 to the final plan without review.",
            raw_provider_reference=f"fj07-synthesis:{query.question_id}",
            confidence=1.0,
        )
        return EvidenceProviderRawResult(
            provider=_PROVIDER,
            provider_contract_version=_CONTRACT,
            provider_call_id=call_id,
            raw_provider_reference=f"fj07-call:{query.question_id}",
            query_id=query.query_id,
            correlation_id=context.correlation_id,
            raw_hits=hits,
            discovery_syntheses=[synthesis],
            transport_outcome=ProviderTransportOutcome.COMPLETED,
            applied_filters=active_query_filters(query),
            started_at=_STAMP,
            completed_at=_STAMP,
            duration_ms=3,
            cache_state=ProviderCacheState.MISS,
        )

    return FakeEvidenceProvider(
        _descriptor(),
        result_factory=result_factory,
        provider_contract_version=_CONTRACT,
    )


def _timeout_provider() -> FakeEvidenceProvider:
    return FakeEvidenceProvider(
        _descriptor(),
        error=TimeoutError("Authorization=Bearer fj09-secret-timeout"),
        provider_contract_version=_CONTRACT,
    )


def _service(
    provider: FakeEvidenceProvider | None,
    *,
    max_questions: int = 50,
) -> ReasoningEvidenceShadowService:
    return ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            max_questions=max_questions,
        ),
        providers=[] if provider is None else [provider],
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )


def _request(tenant_id: str = "fj07"):
    runtime = CanonicalTestPlanRuntime()
    return runtime.build_request(
        jira_key="GUIDES-70007",
        tenant_id=tenant_id,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )


def _capture(
    *,
    service: ReasoningEvidenceShadowService,
    bundle: CanonicalEvidenceBundle,
    questions: list[MissingQuestion],
    retrievals: list[DirectedRetrievalRecord],
    run_id: str = "run-fj07-routing",
):
    return service.capture(
        run_id=run_id,
        request=_request(bundle.tenant_id),
        evidence=bundle,
        domains=[DomainActivation(domain=IssueDomain.AUTHORING, confidence=1.0)],
        scope=ScopeResolution(),
        questions=questions,
        local_retrievals=retrievals,
    )


def _baseline_inputs(index: int):
    records = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    record = records[index]
    fixture = record["fixture"]
    runtime = CanonicalTestPlanRuntime()
    request = runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    evidence = runtime.normalize_packet(fixture, request=request)
    questions = [
        MissingQuestion.model_validate(row) for row in record["generated_questions"]
    ]
    retrievals = [
        DirectedRetrievalRecord.model_validate(row)
        for row in record["retrieval_queries"]
    ]
    domains = [DomainActivation.model_validate(row) for row in record["domains"]]
    scope = ScopeResolution.model_validate(record["scope"])
    return record, fixture, request, evidence, questions, retrievals, domains, scope


def test_low_confidence_unresolved_p1_routes_but_0_8_strong_evidence_skips() -> None:
    question = _question()
    weak = _evidence(confidence=0.79)
    weak_bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[weak])
    weak_result = _evaluate(question, weak_bundle, _retrieval(question, weak))

    assert weak_result.policy_eligible is True
    assert FluffyJawsRoutingSignal.LOCAL_RETRIEVAL_LOW_CONFIDENCE in (
        weak_result.eligibility_signals
    )
    assert FluffyJawsRoutingSignal.UNRESOLVED_P0_OR_P1 in (
        weak_result.eligibility_signals
    )

    strong = _evidence(confidence=0.8, reference="source:strong")
    strong_bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[strong])
    strong_result = _evaluate(
        question, strong_bundle, _retrieval(question, strong)
    )
    assert strong_result.policy_eligible is False
    assert strong_result.policy_skip_reason == (
        FluffyJawsNoCallReason.LOCAL_EVIDENCE_SUFFICIENT
    )


@pytest.mark.parametrize(
    ("verification", "currentness"),
    [
        (VerificationState.CACHED, CurrentnessState.CURRENT),
        (VerificationState.ANALYZED, CurrentnessState.CURRENT),
        (
            VerificationState.VERIFIED_SOURCE,
            CurrentnessState.HISTORICAL_COMPATIBILITY,
        ),
        (VerificationState.VERIFIED_SOURCE, CurrentnessState.VERSION_UNKNOWN),
    ],
)
def test_cached_unverified_or_noncurrent_local_evidence_does_not_suppress_fj(
    verification: VerificationState,
    currentness: CurrentnessState,
) -> None:
    question = _question()
    record = _evidence(
        confidence=0.99,
        verification=verification,
        currentness=currentness,
    )
    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[record])

    result = _evaluate(question, bundle, _retrieval(question, record))

    assert result.policy_eligible is True
    assert FluffyJawsRoutingSignal.UNRESOLVED_P0_OR_P1 in (
        result.eligibility_signals
    )


def test_confidence_and_authority_must_be_satisfied_by_the_same_local_record() -> None:
    question = _question()
    high_confidence_wrong_authority = _evidence(
        source_type=EvidenceSourceType.CUSTOMER_REQUEST,
        authority=AuthorityClass.CUSTOMER_REQUEST,
        confidence=0.99,
        reference="customer:high-confidence",
    )
    authoritative_low_confidence = _evidence(
        confidence=0.79,
        reference="spec:low-confidence",
    )
    bundle = CanonicalEvidenceBundle(
        tenant_id="fj07",
        records=[high_confidence_wrong_authority, authoritative_low_confidence],
    )

    result = _evaluate(
        question,
        bundle,
        _retrieval(
            question,
            high_confidence_wrong_authority,
            authoritative_low_confidence,
        ),
    )

    assert result.policy_eligible is True
    assert FluffyJawsRoutingSignal.UNRESOLVED_P0_OR_P1 in (
        result.eligibility_signals
    )


def test_empty_local_retrieval_routes_and_missing_product_authority_routes() -> None:
    empty_question = _question()
    empty_bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    empty_result = _evaluate(
        empty_question,
        empty_bundle,
        _retrieval(empty_question, status=RetrievalStatus.UNAVAILABLE),
    )
    assert empty_result.policy_eligible is True
    assert FluffyJawsRoutingSignal.LOCAL_RETRIEVAL_EMPTY in (
        empty_result.eligibility_signals
    )

    product_question = _question(
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        source_types=[EvidenceSourceType.CUSTOMER_REQUEST],
    )
    customer = _evidence(
        source_type=EvidenceSourceType.CUSTOMER_REQUEST,
        subject=AuthoritySubject.PRODUCT_CONTRACT,
        authority=AuthorityClass.CUSTOMER_REQUEST,
        confidence=0.99,
        reference="customer:request",
    )
    customer_bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[customer])
    product_result = _evaluate(
        product_question,
        customer_bundle,
        _retrieval(product_question, customer),
    )
    assert product_result.policy_eligible is True
    assert (
        FluffyJawsRoutingSignal.AUTHORITATIVE_INTERNAL_PRODUCT_CONTEXT_MISSING
        in product_result.eligibility_signals
    )


def test_only_question_scoped_material_conflict_routes() -> None:
    question = _question()
    first = _evidence(reference="spec:a", claim_keys=["claim:shared"])
    second = _evidence(
        reference="spec:b",
        content="A different asserted value.",
        claim_keys=["claim:shared"],
    )
    conflict = AuthorityResolution(
        claim_key="claim:shared",
        subject=AuthoritySubject.DITA_SEMANTICS,
        status=ResolutionState.CONFLICTED,
        selected_evidence_ids=[first.evidence_id],
        competing_evidence_ids=[second.evidence_id],
        reason="The canonical resolver preserved competing values.",
    )
    bundle = CanonicalEvidenceBundle(
        tenant_id="fj07",
        records=[first, second],
        authority_resolutions=[conflict],
    )
    routed = _evaluate(question, bundle, _retrieval(question, first, second))
    assert routed.policy_eligible is True
    assert FluffyJawsRoutingSignal.MATERIAL_EVIDENCE_CONFLICT in (
        routed.eligibility_signals
    )

    local = _evidence(reference="spec:local", claim_keys=["claim:local"])
    unrelated_a = _evidence(
        reference="spec:unrelated-a", claim_keys=["claim:unrelated"]
    )
    unrelated_b = _evidence(
        reference="spec:unrelated-b",
        content="Unrelated competing value.",
        claim_keys=["claim:unrelated"],
    )
    unrelated_conflict = AuthorityResolution(
        claim_key="claim:unrelated",
        subject=AuthoritySubject.DITA_SEMANTICS,
        status=ResolutionState.CONFLICTED,
        selected_evidence_ids=[unrelated_a.evidence_id],
        competing_evidence_ids=[unrelated_b.evidence_id],
        reason="Unrelated evidence is conflicted.",
    )
    unrelated_bundle = CanonicalEvidenceBundle(
        tenant_id="fj07",
        records=[local, unrelated_a, unrelated_b],
        authority_resolutions=[unrelated_conflict],
    )
    skipped = _evaluate(
        question, unrelated_bundle, _retrieval(question, local)
    )
    assert skipped.policy_eligible is False


@pytest.mark.parametrize("materiality", [QueryMateriality.P2, QueryMateriality.P3])
def test_nonmaterial_questions_never_route(materiality: QueryMateriality) -> None:
    question = _question()
    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    result = _evaluate(question, bundle, None, materiality)

    assert result.policy_eligible is False
    assert result.policy_skip_reason == FluffyJawsNoCallReason.NOT_MATERIAL_QUESTION


def test_policy_is_feature_neutral_and_contains_no_prohibited_routes() -> None:
    module_path = Path(
        __import__(
            "app.services.fluffyjaws_routing_policy",
            fromlist=["__file__"],
        ).__file__
    )
    production_source = module_path.read_text(encoding="utf-8").casefold()
    for prohibited in ("native pdf", "topichead", "@chunk", "codeblock"):
        assert prohibited not in production_source

    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    projections = []
    for feature_name in ("alpha", "beta", "gamma", "delta"):
        question = _question(f"What is the behavior for {feature_name}?")
        evaluation = _evaluate(question, bundle, None)
        projections.append(
            evaluation.model_dump(
                mode="json",
                exclude={"question_id"},
            )
        )
    assert projections.count(projections[0]) == len(projections)


def test_p0_precedes_p1_and_only_eligible_questions_consume_budget() -> None:
    provider = _provider()
    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    p1 = _question("What is the nonblocking behavior?")
    p0 = _question("What is the blocking contract?", blocking=True)
    trace = _capture(
        service=_service(provider, max_questions=1),
        bundle=bundle,
        questions=[p1, p0],
        retrievals=[_retrieval(p1), _retrieval(p0)],
    )

    assert trace is not None
    assert trace.dispatched_question_ids == [p0.question_id]
    by_question = {row.question_id: row for row in trace.routing_records}
    assert by_question[p0.question_id].provider_called is True
    assert by_question[p0.question_id].budget.eligible_priority == 1
    assert by_question[p1.question_id].why_fj_not_called == [
        FluffyJawsNoCallReason.QUESTION_BUDGET_EXCEEDED
    ]

    strong = _evidence()
    strong_bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[strong])
    answered = _question("What is already answered?")
    eligible = _question("What still needs evidence?")
    second_provider = _provider()
    second_trace = _capture(
        service=_service(second_provider, max_questions=1),
        bundle=strong_bundle,
        questions=[answered, eligible],
        retrievals=[_retrieval(answered, strong), _retrieval(eligible)],
        run_id="run-fj07-budget-after-eligibility",
    )
    assert second_trace is not None
    assert second_trace.dispatched_question_ids == [eligible.question_id]


def test_routing_record_has_required_fields_exclusive_reasons_and_no_content() -> None:
    secret_question = _question("SECRET_TOKEN must never appear in a route record")
    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    first = _capture(
        service=_service(_provider()),
        bundle=bundle,
        questions=[secret_question],
        retrievals=[_retrieval(secret_question)],
        run_id="run-fj07-deterministic-route",
    )
    second = _capture(
        service=_service(_provider()),
        bundle=bundle,
        questions=[secret_question],
        retrievals=[_retrieval(secret_question)],
        run_id="run-fj07-deterministic-route",
    )
    assert first is not None and second is not None
    route = first.routing_records[0]
    required = {
        "question_id",
        "materiality",
        "local_result_status",
        "why_fj_called",
        "why_fj_not_called",
        "expected_evidence_class",
        "budget",
        "trace_id",
    }
    assert required.issubset(route.model_dump())
    assert route.why_fj_called
    assert route.why_fj_not_called == []
    assert route.trace_id == second.routing_records[0].trace_id
    assert "SECRET_TOKEN" not in route.model_dump_json()
    payload = route.model_dump(mode="json")
    with pytest.raises(ValueError):
        FluffyJawsRoutingRecord.model_validate(
            {**payload, "raw_question": "content must not enter routing records"}
        )
    with pytest.raises(ValueError):
        FluffyJawsRoutingRecord.model_validate(
            {
                **payload,
                "provider_called": False,
                "why_fj_called": [],
                "why_fj_not_called": [
                    FluffyJawsNoCallReason.NO_ELIGIBLE_PROVIDER.value,
                    FluffyJawsNoCallReason.QUERY_EGRESS_POLICY_DENIED.value,
                ],
            }
        )


def test_missing_provider_falls_back_with_a_no_call_routing_record() -> None:
    question = _question()
    bundle = CanonicalEvidenceBundle(tenant_id="fj07", records=[])
    trace = _capture(
        service=_service(None),
        bundle=bundle,
        questions=[question],
        retrievals=[_retrieval(question)],
    )

    assert trace is not None
    assert trace.state == "CONFIG_UNAVAILABLE"
    assert trace.calls == []
    assert trace.routing_records[0].provider_called is False
    assert trace.routing_records[0].why_fj_called == []
    assert trace.routing_records[0].why_fj_not_called == [
        FluffyJawsNoCallReason.NO_ELIGIBLE_PROVIDER
    ]


def test_fj00_second_pass_call_set_is_conservative_and_deterministic() -> None:
    expected_counts = [16, 12, 6, 2, 0]
    expected_skips = [
        set(),
        set(),
        set(),
        {
            "question:0d9d06c80337278be61bd2d6531c0524",
            "question:197afe76222d9f9e02910d74de075899",
            "question:5560430d9d132f39846d2be29ba00feb",
            "question:b58bd6070d71e6f6a0cff839613322a2",
        },
        set(),
    ]
    for index, (expected_count, skipped) in enumerate(
        zip(expected_counts, expected_skips, strict=True)
    ):
        (
            _record,
            _fixture,
            request,
            evidence,
            questions,
            retrievals,
            domains,
            scope,
        ) = _baseline_inputs(index)
        trace = _service(_provider()).capture(
            run_id=f"run-fj07-baseline-{index}",
            request=request,
            evidence=evidence,
            domains=domains,
            scope=scope,
            questions=questions,
            local_retrievals=retrievals,
        )
        assert trace is not None
        assert len(trace.dispatched_question_ids) == expected_count
        assert set(question.question_id for question in questions) - set(
            trace.dispatched_question_ids
        ) == skipped
        assert len(trace.routing_records) == len(questions)


def _stable_stage_trace(result) -> list[dict[str, object]]:
    return [
        {
            "stage": str(stage.stage),
            "sequence": stage.sequence,
            "input_sha256": stage.input_sha256,
            "output_sha256": stage.output_sha256,
            "status": stage.status,
            "item_count": stage.item_count,
            "warnings": stage.warnings,
        }
        for stage in result.trace.stage_trace
    ]


def test_second_pass_cannot_expand_acceptance_criteria_or_change_plan() -> None:
    record, fixture, *_rest = _baseline_inputs(3)
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

    provider = _provider(include_hit=True)
    second_pass_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(provider)
    )
    second_pass_request = second_pass_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    second_pass = second_pass_runtime.generate_backend_compatibility(
        request=second_pass_request,
        packet=fixture,
    )
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    assert trace.mode == FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS
    assert trace.calls
    assert any(call.discovery_syntheses for call in trace.calls)
    assert second_pass.request_id == disabled.request_id
    assert second_pass.evidence_bundle_id == disabled.evidence_bundle_id
    assert second_pass.output_sha256 == disabled.output_sha256
    assert second_pass.rendered_output == disabled.rendered_output
    assert second_pass.output_payload == disabled.output_payload
    assert second_pass.structured_plan == disabled.structured_plan
    assert second_pass.gate_decisions == disabled.gate_decisions
    assert _stable_stage_trace(second_pass) == _stable_stage_trace(disabled)
    assert stable_sha256(_stable_stage_trace(second_pass)) == stable_sha256(
        _stable_stage_trace(disabled)
    )
    serialized = second_pass.model_dump_json()
    assert "AC-999" not in serialized
    assert "MUST create a new acceptance criterion" not in serialized
    assert FLUFFYJAWS_SHADOW_TRACE_SCHEMA not in serialized


def test_provider_failure_preserves_blocking_p0_as_an_open_question() -> None:
    packet = {
        "jira_key": "FWD-72",
        "issue": {
            "issue_key": "FWD-72",
            "summary": "Change an output preset setting.",
        },
    }
    disabled_runtime = CanonicalTestPlanRuntime()
    disabled_request = disabled_runtime.build_request(
        jira_key="FWD-72",
        tenant_id="fj09-p0",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    disabled = disabled_runtime.generate_backend_compatibility(
        request=disabled_request,
        packet=packet,
    )

    provider = _timeout_provider()
    failed_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(provider)
    )
    failed_request = failed_runtime.build_request(
        jira_key="FWD-72",
        tenant_id="fj09-p0",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    failed = failed_runtime.generate_backend_compatibility(
        request=failed_request,
        packet=packet,
    )
    trace = get_last_fluffyjaws_shadow_trace()

    blocking_question = next(
        row for row in failed.output_payload["missing_questions"] if row["blocking"]
    )
    hypothesis = next(
        row
        for row in failed.output_payload["hypotheses"]
        if row["derived_from_question_id"] == blocking_question["question_id"]
    )

    assert trace is not None
    assert trace.state == "SECOND_PASS_PARTIAL"
    assert trace.fused_evidence_ids == []
    assert trace.consumed_evidence_ids == []
    assert failed.status == disabled.status == "blocked"
    assert blocking_question["question_id"] in failed.structured_plan.open_question_ids
    assert hypothesis["state"] == "UNRESOLVED"
    assert hypothesis["supporting_evidence_ids"] == []
    assert failed.output_payload == disabled.output_payload
    assert failed.rendered_output == disabled.rendered_output
    assert failed.gate_decisions == disabled.gate_decisions
    assert "fj09-secret-timeout" not in trace.model_dump_json()


def test_provider_failure_preserves_unresolved_p1_and_needs_review() -> None:
    _baseline, fixture, *_rest = _baseline_inputs(3)
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

    provider = _timeout_provider()
    failed_runtime = CanonicalTestPlanRuntime(
        shadow_service=_service(provider)
    )
    failed_request = failed_runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    failed = failed_runtime.generate_backend_compatibility(
        request=failed_request,
        packet=fixture,
    )
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    routed_p1_ids = {
        row.question_id
        for row in trace.routing_records
        if row.materiality == QueryMateriality.P1 and row.provider_called
    }
    assert routed_p1_ids
    assert trace.state == "SECOND_PASS_PARTIAL"
    assert trace.fused_evidence_ids == []
    assert failed.status == disabled.status == "needs_human_review"
    unresolved_p1_ids = {
        row["derived_from_question_id"]
        for row in disabled.output_payload["hypotheses"]
        if row["derived_from_question_id"] in routed_p1_ids
        and row["state"] == "UNRESOLVED"
    }
    assert unresolved_p1_ids
    assert unresolved_p1_ids.issubset(
        set(failed.structured_plan.open_question_ids)
    )
    assert all(
        row["state"] == "UNRESOLVED"
        and row["supporting_evidence_ids"] == []
        for row in failed.output_payload["hypotheses"]
        if row["derived_from_question_id"] in unresolved_p1_ids
    )
    assert failed.output_payload == disabled.output_payload
    assert failed.rendered_output == disabled.rendered_output
    assert failed.gate_decisions == disabled.gate_decisions


def test_second_pass_executor_error_falls_back_without_crashing_generation() -> None:
    class RaisingExecutor:
        def execute(self, *_args, **_kwargs):
            raise RuntimeError("Authorization=Bearer internal-secret")

    _baseline, fixture, *_rest = _baseline_inputs(3)
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
    service = ReasoningEvidenceShadowService(
        config=FluffyJawsShadowConfig(
            mode=FluffyJawsRuntimeMode.FLUFFYJAWS_SECOND_PASS,
            max_questions=50,
        ),
        providers=[_provider()],
        executor=RaisingExecutor(),
        source_visibility_check=lambda _hit: True,
        source_verification_check=lambda _hit: True,
        query_egress_check=lambda _query, _request: True,
    )
    runtime = CanonicalTestPlanRuntime(shadow_service=service)
    request = runtime.build_request(
        jira_key=fixture["jira_key"],
        tenant_id="fluffyjaws-baseline",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )

    result = runtime.generate_backend_compatibility(request=request, packet=fixture)
    trace = get_last_fluffyjaws_shadow_trace()

    assert trace is not None
    eligible_routes = [row for row in trace.routing_records if row.policy_eligible]
    assert eligible_routes
    assert trace.state == "SECOND_PASS_PARTIAL"
    assert trace.metrics.provider_call_count == 0
    assert trace.metrics.internal_error_count == len(eligible_routes)
    assert all(row.provider_called is False for row in eligible_routes)
    assert all(
        row.why_fj_not_called
        == [FluffyJawsNoCallReason.PROVIDER_EXECUTOR_ERROR]
        for row in eligible_routes
    )
    assert all(
        trace.skip_reasons[row.question_id] == "PROVIDER_EXECUTOR_ERROR"
        for row in eligible_routes
    )
    assert result.output_payload == disabled.output_payload
    assert result.rendered_output == disabled.rendered_output
    assert result.gate_decisions == disabled.gate_decisions
    assert "internal-secret" not in trace.model_dump_json()
