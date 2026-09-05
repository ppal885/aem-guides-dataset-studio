"""Synthetic/public-issue-only parity replay; no Human answer files are read."""
from copy import deepcopy
import hashlib
import json

import pytest

from app.core.auth import UserIdentity
from app.core.schemas_canonical_test_plan_runtime import (
    AbstractSignalKind, ChangeSurfaceKind, GenerationProfile, IssueDomain,
    RuntimeEntryPoint,
)
from app.services.canonical_test_plan_runtime import CanonicalTestPlanRuntime
from app.services.qe_pattern_mcp_service import QePatternResolver
from app.services.reasoning_evidence_shadow_service import (
    FluffyJawsShadowConfig, ReasoningEvidenceShadowService,
)
from test_shared_learning_pattern_provider import _lesson, _publication


# Only raw issue descriptions are adapted from existing tests. The three other
# cases are synthetic inputs, not benchmark cases or accepted-Human answers.
RAW_INPUT_CASES = [
    {
        "case": "title_semantics", "jira_key": "GUIDES-93001",
        "origin": "test_canonical_test_plan_runtime_contracts.py::test_issue_identifier_digits_cannot_activate_scale_coverage/raw_issue",
        "summary": "Documents display their configured title.", "description": "",
    },
    {
        "case": "native_pdf_configuration", "jira_key": "GUIDES-93002",
        "origin": "test_canonical_test_plan_runtime_contracts.py::test_runtime_trace_records_canonical_stage_and_usage_lifecycles/raw_issue",
        "summary": "Publishing should retain the exact Ready status.",
        "description": "In scope: Native PDF. Out of scope: HTML5. Enable DITA-OT Processing: ON. Output preset type: Native PDF.",
    },
    {
        "case": "shared_consumer", "jira_key": "GUIDES-93003", "origin": "synthetic_raw_issue",
        "summary": "The shared title resolver should retain the configured title.",
        "description": "Both map navigation and generated output consume the shared title resolver. Existing configured titles should remain unchanged in both consumers.",
    },
    {
        "case": "assets_eligibility", "jira_key": "GUIDES-93004", "origin": "synthetic_raw_issue",
        "summary": "The Assets UI action should be available only for eligible DITA topics.",
        "description": "In the Assets UI, the action is enabled for a DITA topic with write permission. It must remain disabled for read-only topics and non-DITA assets.",
    },
    {
        "case": "copy_paste", "jira_key": "GUIDES-93005", "origin": "synthetic_raw_issue",
        "summary": "Copy and paste should preserve the selected inline element.",
        "description": "In the XML Editor, copying an inline element and pasting into another topic should retain its text and valid DITA structure. The source topic must remain unchanged.",
    },
    {
        "case": "simple_ui", "jira_key": "GUIDES-93006",
        "origin": "test_canonical_test_plan_runtime_contracts.py::test_negated_generated_output_keeps_configuration_only_delivery_out_of_scope/raw_issue",
        "summary": "Rename an output-preset field label.",
        "description": "Only the preset configuration UI is in scope. Publishing is out of scope. Generated output is out of scope.",
    },
]

PROJECTION_FIELDS = (
    "contract_facts", "scope", "domains", "change_surfaces", "abstract_signals",
    "behavior_model", "reasoning_activations", "missing_questions", "hypotheses",
    "semantic_closure", "coverage_dispositions", "acceptance_candidates",
    "promotion_decisions", "plan_sections",
)


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False).encode()).hexdigest()


def _projection(result):
    projection = {key: result.output_payload[key] for key in PROJECTION_FIELDS
        if key in result.output_payload}
    preparation = deepcopy(result.output_payload["qe_investigation"])
    preparation.pop("pattern_lookup", None)
    preparation.pop("preparation_id", None)  # Hash includes the removed lookup trace.
    projection["qe_investigation_without_lookup_trace"] = preparation
    projection["rendered_output"] = result.rendered_output
    return projection


def _run_case(case, mode, monkeypatch, *, blind=False):
    calls = {"shared_loader": 0, "baseline_provider": 0}

    class EmptyBaseline:
        def load(self):
            calls["baseline_provider"] += 1
            return [], "no-provider-fixture", "c" * 64

    def reviewed_fixture_loader(**kwargs):
        calls["shared_loader"] += 1
        if blind:
            raise AssertionError("A blinded runtime must not consult shared learning.")
        return _publication(_lesson(domains=[row.value for row in IssueDomain],
            surfaces=[row.value for row in ChangeSurfaceKind],
            signals=[row.value for row in AbstractSignalKind]))

    monkeypatch.setenv("SHARED_UAC_LEARNING_MODE", mode)
    runtime = CanonicalTestPlanRuntime(
        shadow_service=ReasoningEvidenceShadowService(config=FluffyJawsShadowConfig(), providers=()),
        pattern_resolver=QePatternResolver(EmptyBaseline(), shared_loader=reviewed_fixture_loader))
    request = runtime.build_request(jira_key=case["jira_key"], tenant_id="tenant-a",
        entry_point=RuntimeEntryPoint.BENCHMARK_V2 if blind else RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        benchmark_version="V2" if blind else "", benchmark_split="blind" if blind else "",
        benchmark_record_id=case["case"] if blind else "",
        user=UserIdentity(id="replay-reader", auth_method="token", roles=["viewer"],
            allowed_tenants=["tenant-a"]))
    result = runtime.generate_backend_compatibility(request=request, packet={
        "jira_key": case["jira_key"], "issue": {"issue_key": case["jira_key"],
            "summary": case["summary"], "description": case["description"]}})
    return result, calls


def collect_runtime_shadow_proof(monkeypatch):
    results = []
    for case in RAW_INPUT_CASES:
        disabled, disabled_calls = _run_case(case, "DISABLED", monkeypatch)
        shadow, shadow_calls = _run_case(case, "SHADOW", monkeypatch)
        blind, blind_calls = _run_case(case, "ENABLED", monkeypatch, blind=True)
        disabled_projection, shadow_projection = _projection(disabled), _projection(shadow)
        assert disabled_projection == shadow_projection, case["case"]
        assert disabled_calls["shared_loader"] == 0
        assert shadow_calls["shared_loader"] > 0
        assert blind_calls["shared_loader"] == 0
        blind_lookup = blind.output_payload["qe_investigation"]["pattern_lookup"]
        assert not blind_lookup["matched_human_patterns"]
        assert "SHARED_LEARNING_BENCHMARK_ISOLATION" in blind_lookup["warning_codes"]
        assert _projection(blind) == disabled_projection, case["case"]
        shadow_lookup = shadow.output_payload["qe_investigation"]["pattern_lookup"]
        shadow_ids = sorted({pattern_id for call in shadow_lookup["calls"]
            for pattern_id in call["shadow_pattern_ids"]})
        results.append({"case": case["case"], "input_origin": case["origin"],
            "input_sha256": _sha({"summary": case["summary"], "description": case["description"]}),
            "disabled_projection_sha256": _sha(disabled_projection),
            "shadow_projection_sha256": _sha(shadow_projection),
            "shadow_equals_disabled": True, "blind_equals_disabled": True,
            "acceptance_candidate_count": len(disabled.output_payload["acceptance_candidates"]),
            "shadow_shared_loader_calls": shadow_calls["shared_loader"],
            "shadow_matched_lesson_count": len(shadow_ids),
            "disabled_shared_loader_calls": disabled_calls["shared_loader"],
            "blind_shared_loader_calls": blind_calls["shared_loader"]})
    return {"schema_version": "shared-uac-learning-runtime-shadow-proof-v1",
        "test": "backend/tests/test_shared_learning_shadow_replay.py",
        "scope": "Six local raw-input regression cases; not a Human-quality or deployed-VM benchmark.",
        "external_evidence_providers": [], "human_answer_files_read": [],
        "comparison": "Exact canonical semantic projection and rendered output; Pattern lookup trace excluded.",
        "trace_exclusions": ["qe_investigation.pattern_lookup",
            "qe_investigation.preparation_id (identity hash includes lookup trace)"],
        "projection_fields": [*PROJECTION_FIELDS, "qe_investigation_without_lookup_trace", "rendered_output"],
        "case_count": len(results), "cases": results}


def test_multi_case_shadow_parity_and_blind_loader_isolation(monkeypatch):
    proof = collect_runtime_shadow_proof(monkeypatch)
    assert proof["case_count"] == 6


def test_server_disabled_preserves_complete_output_hash_for_benchmark_entry(monkeypatch):
    normal, normal_calls = _run_case(RAW_INPUT_CASES[1], "DISABLED", monkeypatch)
    benchmark, benchmark_calls = _run_case(RAW_INPUT_CASES[1], "DISABLED", monkeypatch, blind=True)
    assert normal_calls["shared_loader"] == benchmark_calls["shared_loader"] == 0
    assert normal.output_payload == benchmark.output_payload
    assert normal.output_sha256 == benchmark.output_sha256


if __name__ == "__main__":
    with pytest.MonkeyPatch.context() as patch:
        print(json.dumps(collect_runtime_shadow_proof(patch), sort_keys=True, indent=2))
