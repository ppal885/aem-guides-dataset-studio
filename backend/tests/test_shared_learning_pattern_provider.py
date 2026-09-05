from copy import deepcopy
from datetime import datetime, timezone

import pytest

from app.core.schemas_qe_pattern_mcp import ResolveQePatternsRequest, SharedLearningContext, SharedLearningMode
from app.services.shared_learning_pattern_provider import resolve_shared_learning


def _lesson(**overrides):
    row = {"lesson_id": "lesson-example", "version": 1, "kind": "GENERIC_PATTERN",
        "source": "HUMAN_FEEDBACK", "automatic_authority_promotion": False,
        "expected_behavior_authority": False, "delta_type": "OPEN_QUESTION_ADDED",
        "domains": ["PUBLISHING"], "surfaces": ["CHANGED_BEHAVIOR"], "signals": ["CHANGED_BEHAVIOR"],
        "families": ["ALTERNATE_MECHANISMS"], "scope": {},
        "guidance": "Investigate alternate mechanisms for the changed behavior.",
        "preferred_evidence": ["CURRENT_JIRA"], "materiality": "P1", "confidence": 0.8,
        "source_case_ids": ["GUIDES-81001", "GUIDES-81002"],
        "independent_support_groups": [{"group_id": "incident-a", "case_ids": ["GUIDES-81001"]},
            {"group_id": "incident-b", "case_ids": ["GUIDES-81002"]}],
        "human_approval": {"reviewer_id": "human-reviewer", "reviewed_at": "2026-08-01T00:00:00Z",
            "origin_confirmed": True, "applicability_confirmed": True, "counterexamples_checked": True},
        "counterexamples": [], "hard_negatives": [], "exception_attestation": {},
        "published_at": "2026-08-02T00:00:00Z", "revoked_at": None}
    row.update(overrides)
    return row


def _publication(*lessons, tenant_id="tenant-a", publication_id="a" * 64):
    return {"contract_version": "shared-uac-learning-publication-v1", "tenant_id": tenant_id,
        "publication_id": publication_id, "published_at": "2026-08-02T00:00:00Z", "lessons": list(lessons)}


def _context(**overrides):
    values = {"tenant_id": "tenant-a", "principal_id": "reader-a", "authenticated": True, "mode": "ENABLED"}
    values.update(overrides)
    return SharedLearningContext(**values)


def _request(**overrides):
    values = {"domain": "PUBLISHING", "change_surfaces": ["CHANGED_BEHAVIOR"], "abstract_signals": ["CHANGED_BEHAVIOR"]}
    values.update(overrides)
    return ResolveQePatternsRequest(**values)


def _resolve(publication, *, context=None, request=None):
    return resolve_shared_learning(request or _request(), context or _context(), loader=lambda **kwargs: deepcopy(publication))


def test_approved_generic_lesson_is_investigation_only():
    response = _resolve(_publication(_lesson()))
    assert response.status == "SUCCESS"
    assert response.publication_id == "a" * 64
    match = response.matched_patterns[0]
    assert match.pattern.lesson_id == "lesson-example"
    assert match.pattern.lesson_kind == "GENERIC_PATTERN"
    assert match.blocking_recommendations == []
    assert match.pattern.blocking_default is False
    assert match.pattern.provenance.source_kind == "SHARED_UAC_LEARNING"


def test_shadow_observes_matches_without_influence_or_scope_suppression():
    response = _resolve(_publication(_lesson()), context=_context(mode="SHADOW"))
    assert response.status == "SUCCESS" and response.shadow_pattern_ids
    assert response.matched_patterns == response.suppressed_patterns == []


@pytest.mark.parametrize("context", [_context(mode="DISABLED"), _context(benchmark_isolation=True), _context(authenticated=False)])
def test_disabled_untrusted_or_benchmark_context_never_reads_storage(context):
    def forbidden_loader(**kwargs):
        pytest.fail("storage must not be queried")
    response = resolve_shared_learning(_request(), context, loader=forbidden_loader)
    assert response.status in {"DISABLED", "UNAVAILABLE"}
    assert response.matched_patterns == []


def test_default_mode_is_shadow():
    assert SharedLearningContext(tenant_id="tenant-a", principal_id="reader").mode == SharedLearningMode.SHADOW


def test_tenant_mismatch_rejects_whole_publication():
    response = _resolve(_publication(_lesson(), tenant_id="tenant-b"))
    assert response.status == "INVALID_LIBRARY" and response.matched_patterns == []


def test_revocation_is_observed_on_next_call():
    publication = _publication(_lesson())
    def loader(**kwargs):
        return deepcopy(publication)
    assert resolve_shared_learning(_request(), _context(), loader=loader).matched_patterns
    publication["lessons"][0]["revoked_at"] = "2026-08-03T00:00:00Z"
    publication["publication_id"] = "b" * 64
    second = resolve_shared_learning(_request(), _context(), loader=loader)
    assert second.matched_patterns == [] and second.publication_id == "b" * 64
    assert second.excluded_pattern_counts["REVOKED"] == 1


def test_temporal_and_source_exclusions_are_forwarded_and_rechecked():
    seen = []
    context = _context(cutoff_at=datetime(2026, 8, 1, tzinfo=timezone.utc), excluded_source_case_ids={"GUIDES-81001"})
    def loader(**kwargs):
        seen.append(kwargs)
        return _publication(_lesson())
    assert not resolve_shared_learning(_request(), context, loader=loader).matched_patterns
    assert seen[0]["tenant_id"] == "tenant-a" and seen[0]["cutoff_at"] == context.cutoff_at
    assert seen[0]["excluded_source_case_ids"] == {"GUIDES-81001"}
    response = _resolve(_publication(_lesson()), context=_context(excluded_source_case_ids={"GUIDES-81001"}))
    assert response.excluded_pattern_counts["EXCLUDED_SOURCE_CASE"] == 1


@pytest.mark.parametrize("review_field", ["origin_confirmed", "applicability_confirmed", "counterexamples_checked"])
def test_missing_human_review_assertion_fails_closed(review_field):
    lesson = _lesson()
    lesson["human_approval"][review_field] = False
    assert _resolve(_publication(lesson)).status == "INVALID_LIBRARY"


def test_duplicate_case_variants_cannot_satisfy_independence():
    lesson = _lesson(independent_support_groups=[{"group_id": "one-incident", "case_ids": ["GUIDES-81001", "GUIDES-81002"]}])
    assert _resolve(_publication(lesson)).status == "INVALID_LIBRARY"
    lesson["exception_attestation"] = {"kind": "NORMATIVE_INVARIANT", "rationale": "The reviewed normative contract applies to every matching case.",
        "evidence_refs": ["reviewed-specification"], "reviewer_id": "human-reviewer", "reviewed_at": "2026-08-01T00:00:00Z"}
    assert _resolve(_publication(lesson)).status == "SUCCESS"


def test_scoped_single_case_requires_scope_and_only_matches_that_scope():
    lesson = _lesson(kind="SCOPED_CASE", source_case_ids=["GUIDES-81001"],
        independent_support_groups=[{"group_id": "incident-a", "case_ids": ["GUIDES-81001"]}])
    assert _resolve(_publication(lesson)).status == "INVALID_LIBRARY"
    lesson["scope"] = {"subject_terms": ["versioned publishing"]}
    assert _resolve(_publication(lesson)).matched_patterns == []
    response = _resolve(_publication(lesson), request=_request(subject_terms=["versioned publishing"]))
    assert response.matched_patterns[0].pattern.lesson_kind == "SCOPED_CASE"
    assert response.matched_patterns[0].blocking_recommendations == []


def test_current_oos_and_hard_negative_override_shared_lesson():
    response = _resolve(_publication(_lesson()), request=_request(scope_constraints={"explicit_out_of_scope": ["ALTERNATE_MECHANISMS"]}))
    assert not response.matched_patterns and response.suppressed_patterns
    assert not _resolve(_publication(_lesson(hard_negatives=["CHANGED_BEHAVIOR"]))).matched_patterns


def test_provider_failure_never_returns_stale_snapshot():
    def unavailable(**kwargs):
        raise RuntimeError("private database connection detail")
    response = resolve_shared_learning(_request(), _context(), loader=unavailable)
    assert response.status == "UNAVAILABLE" and response.publication_id is None
    assert response.matched_patterns == [] and "private database" not in response.model_dump_json()


def test_unverified_source_protection_is_explicitly_unavailable():
    publication = _publication()
    publication["source_protection_status"] = "UNVERIFIED"
    response = _resolve(publication)
    assert response.status == "UNAVAILABLE"
    assert response.error_code == "SHARED_LEARNING_SOURCE_PROTECTION_UNVERIFIED"
    assert not response.matched_patterns


def test_current_jira_is_exclusion_only_never_activation():
    response = _resolve(_publication(_lesson()), request=_request(current_jira_key="GUIDES-81001"))
    assert not response.matched_patterns
    assert response.excluded_pattern_counts["EXCLUDED_SOURCE_CASE"] == 1


def test_editorial_feedback_cannot_create_question_families():
    lesson = _lesson(influence_kind="AUTHORING_GUIDANCE", delta_type="LANGUAGE_SIMPLIFIED", families=[])
    response = _resolve(_publication(lesson))
    assert response.matched_patterns == []
    assert len(response.authoring_guidance) == 1
    assert response.authoring_guidance[0].consumption_state == "RETRIEVED_NOT_APPLIED"
    shadow = _resolve(_publication(lesson), context=_context(mode="SHADOW"))
    assert shadow.authoring_guidance == [] and shadow.shadow_authoring_guidance_ids == ["lesson-example"]


def _runtime_run(monkeypatch, *, mode="ENABLED", publication=None, resolver=None,
        auth_method="token", jira_key="GUIDES-82003", tenant_id="tenant-a"):
    from app.core.auth import UserIdentity
    from app.core.schemas_canonical_test_plan_runtime import GenerationProfile, RuntimeEntryPoint
    from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
    from app.services.qe_pattern_mcp_service import QePatternResolver

    class EmptyBaseline:
        def load(self):
            return [], "baseline", "c" * 64

    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", mode)
    runtime = CanonicalTestPlanRuntime(pattern_resolver=resolver or QePatternResolver(
        EmptyBaseline(), shared_loader=lambda **kwargs: deepcopy(publication or _publication(_lesson()))))
    request = runtime.build_request(jira_key=jira_key, tenant_id=tenant_id,
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        user=UserIdentity(id="reader", roles=["viewer"], allowed_tenants=[tenant_id], auth_method=auth_method))
    return runtime.generate_backend_compatibility(request=request, packet={
        "jira_key": jira_key,
        "issue": {"issue_key": jira_key,
            "summary": "Publishing should retain the exact Ready status.",
            "description": "In scope: Native PDF. Out of scope: HTML5. Output preset type: Native PDF. The existing behavior must remain compatible after upgrade.",
            "deployment_model": "On-prem", "product_version": "5.0"},
    })


def _contract_projection(result):
    return {
        (row["statement"], tuple(row["source_fact_ids"]), tuple(row["evidence_ids"]))
        for row in result.output_payload["acceptance_candidates"]
    }


def test_real_runtime_shared_lesson_reaches_question_and_disposition_not_acceptance(monkeypatch):
    disabled = _runtime_run(monkeypatch, mode="DISABLED")
    enabled = _runtime_run(monkeypatch)
    investigation = enabled.output_payload["qe_investigation"]
    patterns = investigation["matched_human_patterns"]
    assert patterns and patterns[0]["lesson_id"] == "lesson-example"
    family = next(row for row in investigation["mandatory_families"] if row["family_id"] == "ALTERNATE_MECHANISMS")
    assert any(row["source"] == "PATTERN_MCP" for row in family["sources"])
    questions = [row for row in enabled.output_payload["missing_questions"] if row["dimension"] == "ALTERNATE_MECHANISMS"]
    assert questions and all(row["blocking"] is False for row in questions)
    question_ids = {row["question_id"] for row in questions}
    dispositions = [row for row in enabled.output_payload["coverage_dispositions"] if question_ids & set(row.get("source_question_ids", []))]
    assert dispositions and all(row["disposition"] != "ACCEPTANCE_CONTRACT" for row in dispositions)
    assert _contract_projection(enabled) == _contract_projection(disabled)
    assert enabled.output_payload["promotion_decisions"] == disabled.output_payload["promotion_decisions"]


def test_runtime_shadow_and_disabled_have_identical_reasoning_and_rendered_output(monkeypatch):
    disabled = _runtime_run(monkeypatch, mode="DISABLED")
    shadow = _runtime_run(monkeypatch, mode="SHADOW")
    assert shadow.rendered_output == disabled.rendered_output
    assert _contract_projection(shadow) == _contract_projection(disabled)
    assert shadow.output_payload["missing_questions"] == disabled.output_payload["missing_questions"]
    lookup = shadow.output_payload["qe_investigation"]["pattern_lookup"]
    assert not lookup["matched_human_patterns"]
    assert any(row["shadow_pattern_ids"] for row in lookup["calls"])


def test_runtime_editorial_is_retrieved_context_not_discovery_or_claimed_application(monkeypatch):
    base = _runtime_run(monkeypatch, mode="DISABLED")
    result = _runtime_run(monkeypatch, publication=_publication(_lesson(
        influence_kind="AUTHORING_GUIDANCE", delta_type="LANGUAGE_SIMPLIFIED", families=[],
        guidance="Keep each action and expected result in one short sentence.")))
    prep = result.output_payload["qe_investigation"]
    assert prep["authoring_guidance"][0]["consumption_state"] == "RETRIEVED_NOT_APPLIED"
    assert not prep["matched_human_patterns"]
    assert result.output_payload["missing_questions"] == base.output_payload["missing_questions"]
    assert _contract_projection(result) == _contract_projection(base)


def test_runtime_shared_failure_retains_approved_baseline(monkeypatch):
    from app.services.qe_pattern_mcp_service import QePatternResolver
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider
    baseline_pattern = SharedLearningPatternLibraryProvider(_context(), loader=lambda **kwargs: _publication(_lesson())).load()[0][0]
    baseline_pattern = baseline_pattern.model_copy(update={"pattern_id": "BASELINE_APPROVED",
        "provenance": baseline_pattern.provenance.model_copy(update={"source_kind": "TEST_FIXTURE"})})

    class ApprovedBaseline:
        def load(self):
            return [baseline_pattern], "baseline", "a" * 64

    def unavailable(**kwargs):
        raise RuntimeError("offline")

    result = _runtime_run(monkeypatch, resolver=QePatternResolver(ApprovedBaseline(), shared_loader=unavailable))
    lookup = result.output_payload["qe_investigation"]["pattern_lookup"]
    assert any(row["pattern_id"] == "BASELINE_APPROVED" for row in lookup["matched_human_patterns"])
    assert any(row["provider_name"] == "SHARED_UAC_LEARNING" and row["provider_status"] == "UNAVAILABLE" for row in lookup["calls"])


def test_dev_bypass_cannot_read_shared_publication_in_runtime(monkeypatch):
    result = _runtime_run(monkeypatch, auth_method="dev_bypass")
    lookup = result.output_payload["qe_investigation"]["pattern_lookup"]
    assert not lookup["matched_human_patterns"]
    assert "SHARED_LEARNING_AUTHENTICATED_TENANT_REQUIRED" in lookup["warning_codes"]


@pytest.mark.parametrize("updates", [
    {"delta_type": "UNCLASSIFIED"},
    {"delta_type": "LANGUAGE_SIMPLIFIED", "influence_kind": "INVESTIGATION_CANDIDATE"},
    {"delta_type": "OPEN_QUESTION_ADDED", "influence_kind": "AUTHORING_GUIDANCE", "families": []},
    {"expected_behavior_authority": True},
    {"automatic_authority_promotion": True},
    {"source_origin": "AI_PROPOSAL"},
    {"guidance": "Use password=private for the test."},
    {"scope": {"product_versions": ["GUIDES-12345"]}},
    {"version": True},
    {"source_case_ids": ["GUIDES-81001", "guides-81001"]},
])
def test_malformed_or_authority_elevating_publication_fails_shared_lane(updates):
    assert _resolve(_publication(_lesson(**updates))).status == "INVALID_LIBRARY"


def test_reused_provider_drops_revoked_editorial_state():
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider

    publication = _publication(_lesson(influence_kind="AUTHORING_GUIDANCE",
        delta_type="LANGUAGE_SIMPLIFIED", families=[]))
    provider = SharedLearningPatternLibraryProvider(_context(), loader=lambda **kwargs: publication)
    provider.load()
    assert provider.authoring_records
    publication["lessons"] = []
    provider.load()
    assert provider.authoring_records == [] and provider.excluded_counts == {}


def test_malformed_shared_response_keeps_baseline_investigation(monkeypatch):
    from app.services.qe_pattern_mcp_service import QePatternResolver
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider

    baseline_pattern = SharedLearningPatternLibraryProvider(_context(), loader=lambda **kwargs: _publication(_lesson())).load()[0][0]

    class ApprovedBaseline:
        def load(self):
            return [baseline_pattern], "baseline", "a" * 64

    class MalformedSharedResolver:
        def resolve(self, request):
            response = QePatternResolver(ApprovedBaseline()).resolve(request).model_dump(mode="json")
            response["shared_learning"] = {"mode": "ENABLED", "status": "SUCCESS", "matched_patterns": ["not-a-pattern"]}
            return response

    result = _runtime_run(monkeypatch, resolver=MalformedSharedResolver())
    lookup = result.output_payload["qe_investigation"]["pattern_lookup"]
    assert lookup["matched_human_patterns"]
    assert "SHARED_LEARNING_INVALID_RESPONSE" in lookup["warning_codes"]


def test_changed_publication_during_domains_discards_shared_only():
    from app.core.schemas_canonical_test_plan_runtime import (
        DomainActivation, PatternLookupResult, PatternLookupRuntimeStatus,
    )
    from app.services.canonical_qe_investigation_service import CanonicalQeInvestigationService

    baseline = PatternLookupResult(status=PatternLookupRuntimeStatus.AVAILABLE_NO_MATCH)
    first = _resolve(_publication(_lesson()))
    second = _resolve(_publication(_lesson(), publication_id="b" * 64))
    result = CanonicalQeInvestigationService()._merge_shared_results(baseline,
        [(DomainActivation(domain="PUBLISHING", confidence=1), first),
         (DomainActivation(domain="OTHER", confidence=1), second)],
        facts=None, scope=None, surfaces=[], signals=[])
    assert result.matched_human_patterns == []
    assert "SHARED_LEARNING_PUBLICATION_CHANGED_DURING_LOOKUP" in result.warning_codes


def test_new_shared_qualifiers_do_not_change_baseline_negative_matching():
    from app.services.qe_pattern_mcp_service import QePatternResolver
    from app.services.shared_learning_pattern_provider import SharedLearningPatternLibraryProvider

    row = SharedLearningPatternLibraryProvider(_context(), loader=lambda **kwargs:
        _publication(_lesson(hard_negatives=["isolated deployment marker"]))).load()[0][0]
    baseline = row.model_copy(update={"pattern_id": "BASELINE_APPROVED",
        "provenance": row.provenance.model_copy(update={"source_kind": "TEST_FIXTURE"})})

    class BaselineProvider:
        def load(self):
            return [baseline], "baseline", "a" * 64

    request = _request(deployment_model="isolated deployment marker")
    assert QePatternResolver(BaselineProvider()).resolve(request).matched_patterns
    assert not _resolve(_publication(_lesson(hard_negatives=["isolated deployment marker"])), request=request).matched_patterns
