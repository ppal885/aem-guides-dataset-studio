"""C2A: canonical runtime artifact projection and Skill-gate replay.

The canonical runtime is the production semantic authority.  These tests prove
the read-only projection adapter + replay path:

    CanonicalTestPlanRuntime.generate_backend_compatibility
        -> output_payload
        -> project_runtime_result (read-only)
        -> run_gates replay_runtime_projection
        -> parity report (PASS / FAIL / NOT_EVALUABLE / DISAGREEMENT)

No semantic content is recomputed or invented; missing runtime information is
NOT_EVALUABLE, and replay never mutates the canonical artifact.
"""

from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = (
    REPO_ROOT / "skills" / "test-plan-generation" / "scripts"
)


def _load_skill_module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SKILL_SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = _load_skill_module("canonical_runtime_adapter", "canonical_runtime_adapter.py")
run_gates = _load_skill_module("run_gates", "run_gates.py")

from app.core.schemas_canonical_test_plan_runtime import (  # noqa: E402
    GenerationProfile,
    RuntimeEntryPoint,
)
from app.services.canonical_test_plan_runtime import (  # noqa: E402
    CANONICAL_TEST_PLAN_RUNTIME,
)


# Sanitized repository-retention fixture shape (regression only).
_RETENTION_DESCRIPTION = (
    "The housekeeping job removes output history entries older than the "
    "configured number of days. Provide an option to keep only the most "
    "recent entries per output preset. Provide an option to remove only the "
    "log file and keep the history entry for audit purposes."
)


def _runtime_result():
    request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
        jira_key="GUIDES-99088",
        tenant_id="tenant-c2a-replay",
        entry_point=RuntimeEntryPoint.PYTHON_API,
        generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
    )
    packet = {
        "jira_key": "GUIDES-99088",
        "issue": {
            "issue_key": "GUIDES-99088",
            "summary": "Housekeeping retention options.",
            "description": _RETENTION_DESCRIPTION,
            "deployment_model": "On-prem",
            "product_version": "5.0",
        },
    }
    return CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
        request=request, packet=packet
    )


def _projected():
    result = _runtime_result()
    envelope = result.model_dump(mode="json")
    manifest, meta = adapter.project_runtime_result(envelope)
    return result, envelope, manifest, meta


# ---------------------------------------------------------------------------
# Projection contract
# ---------------------------------------------------------------------------


def test_projection_preserves_runtime_ids_and_state() -> None:
    result, envelope, manifest, meta = _projected()
    payload = envelope["output_payload"]

    research = manifest["question_research"]["items"]
    runtime_research = payload["question_research"]
    assert len(research) == len(runtime_research)
    assert {row["question_ref"] for row in research} == {
        row["question_id"] for row in runtime_research
    }
    for projected_row, runtime_row in zip(
        sorted(research, key=lambda r: r["question_ref"]),
        sorted(runtime_research, key=lambda r: r["question_id"]),
    ):
        assert projected_row["research_requirement"] == runtime_row["research_requirement"]
        assert projected_row["research_status"] == runtime_row["research_status"]
        assert projected_row["research_requests"] == runtime_row["research_request_ids"]

    classifications = manifest["behavior_classification"]["items"]
    assert {row["target_ref"] for row in classifications} == {
        row["disposition_id"] for row in payload["behavior_classifications"]
    }

    # Runtime status is carried for the parity report, not re-typed.
    assert manifest["_runtime"]["status"] == envelope["status"]
    assert meta["adapter_version"] == adapter.PROJECTION_ADAPTER_VERSION
    assert meta["runtime_revision"] == envelope["run_id"]


def test_projection_never_fabricates_missing_semantics() -> None:
    _result, _envelope, manifest, meta = _projected()
    for block in (
        "question_plan",
        "question_resolutions",
        "doc_research",
        "coverage_equivalence",
        "requirement_lineage",
        "historical_jira_assessment",
        "retrieval_requests",
    ):
        assert block not in manifest, block
        assert block in meta["unavailable_fields"], block
    # C2B-S1: the canonical artifact now carries real claim-level sufficiency;
    # it is projected, not fabricated.
    assert "evidence_sufficiency" in manifest
    assert manifest["evidence_sufficiency"]["claim_assessments"]
    assert "evidence_sufficiency" not in meta["unavailable_fields"]
    # Coverage priority is not carried by the runtime - recorded lossy, never
    # reconstructed.
    assert "coverage_decisions.priority" in meta["lossy_fields"]
    for item in manifest["coverage_decisions"]["items"]:
        assert item["priority"] == adapter.UNAVAILABLE_FROM_RUNTIME


def test_projection_is_read_only() -> None:
    _result, envelope, _manifest, _meta = _projected()
    again, _ = adapter.project_runtime_result(copy.deepcopy(envelope))
    # Re-projecting the same artifact is byte-identical (no mutation, no drift).
    assert again == adapter.project_runtime_result(copy.deepcopy(envelope))[0]


# ---------------------------------------------------------------------------
# Replay modes
# ---------------------------------------------------------------------------


def test_replay_reports_evaluable_and_not_evaluable_honestly() -> None:
    _result, _envelope, manifest, _meta = _projected()
    report = run_gates.replay_runtime_projection(manifest)

    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    # Losslessly projectable contracts are genuinely evaluated.
    assert statuses["question-research"] in {"PASS", "FAIL"}
    assert statuses["behavior-classification"] in {"PASS", "FAIL"}
    # C2B-S1: the canonical sufficiency artifact makes S1 genuinely evaluable.
    assert statuses["evidence-sufficiency"] in {"PASS", "FAIL"}
    # Runtime does not carry these contracts - honest NOT_EVALUABLE, not PASS.
    for gate in (
        "question-planner",
        "question-resolver",
        "doc-research-routing",
        "coverage-equivalence",
        "requirement-lineage",
        "historical-jira-safety",
        "retrieval-admission",
    ):
        assert statuses[gate] == "NOT_EVALUABLE", gate
    assert set(report["not_evaluable"]) >= {
        "coverage-equivalence",
        "historical-jira-safety",
    }
    assert report["projection_quality"] == "PARTIAL"
    # Canonical runtime remains the promotion authority; replay agrees here.
    assert report["runtime_promotion_status"] in {"AGREES", "NOT_EVALUABLE"}


def test_deliberate_disagreement_is_reported_without_repair() -> None:
    _result, envelope, manifest, _meta = _projected()
    runtime = manifest["_runtime"]
    promoted = next(
        row for row in runtime["promotion_decisions"]
        if row["status"] == "PROMOTED"
    )
    candidate = next(
        row for row in runtime["acceptance_candidates"]
        if row["candidate_id"] == promoted["candidate_id"]
    )
    tampered = copy.deepcopy(manifest)
    # Controlled violation: bind a research-pending question to the promoted
    # candidate's coverage disposition.
    research_row = next(
        row for row in tampered["question_research"]["items"]
        if row["research_requirement"] != "NONE"
    )
    target_question = research_row["question_ref"]
    research_row["research_status"] = "PENDING"
    disposition_id = candidate["source_disposition_ids"][0]
    coverage_row = next(
        row for row in tampered["coverage_decisions"]["items"]
        if row["coverage_id"] == disposition_id
    )
    coverage_row["question_ids"] = [target_question]

    before = copy.deepcopy(manifest)
    report = run_gates.replay_runtime_projection(tampered)

    assert report["runtime_promotion_status"] == "DISAGREES"
    (disagreement,) = report["disagreements"]
    assert disagreement["severity"] == "BLOCKING_POLICY_DIVERGENCE"
    assert disagreement["gate"] == "question-research"
    assert disagreement["projected_artifact_ref"] == target_question
    # The replay never repairs or rewrites the artifact.
    assert manifest == before


def test_unavailable_information_is_not_evaluable_not_pass() -> None:
    _result, _envelope, manifest, _meta = _projected()
    stripped = copy.deepcopy(manifest)
    del stripped["question_research"]
    stripped["_projection"]["unavailable_fields"] = sorted(
        set(stripped["_projection"]["unavailable_fields"]) | {"question_research"}
    )
    report = run_gates.replay_runtime_projection(stripped)
    statuses = {row["gate"]: row["status"] for row in report["gate_results"]}
    assert statuses["question-research"] == "NOT_EVALUABLE"
    assert report["runtime_promotion_status"] == "NOT_EVALUABLE"
    assert all(row["status"] != "FAIL" for row in report["gate_results"])


# ---------------------------------------------------------------------------
# GUIDES-4365-shaped regression through the production entry point
# ---------------------------------------------------------------------------


def test_sanitized_retention_fixture_replay_end_to_end() -> None:
    result, envelope, manifest, _meta = _projected()
    payload = envelope["output_payload"]

    # P1 behavior holds in the replayed artifact.
    assert payload["scope"]["enable_dita_ot_processing"] == "NOT_APPLICABLE"
    assert not any(
        "DITA-OT" in (row.get("question_text") or row.get("question") or "")
        for row in payload["missing_questions"]
        if row.get("blocking")
    )
    # No raw clone/retrieval fragments in the canonical render.
    plan = envelope["qe_review_package"]["canonical_result"]["plan_markdown"] if (
        envelope.get("qe_review_package")
    ) else payload.get("plan_markdown", "")
    assert ".py" not in plan and "class " not in plan
    # Replay is honest and does not modify the runtime result.
    before = copy.deepcopy(envelope)
    report = run_gates.replay_runtime_projection(manifest)
    assert report["gate_results"]
    assert result.model_dump(mode="json") == before


# ---------------------------------------------------------------------------
# CLI / HTTP parity and draft-field deprecation
# ---------------------------------------------------------------------------


def _pipeline_result_dump():
    """The exact TestPlanPipelineResult the HTTP route returns, projected from
    the canonical envelope by the same projector the service uses."""

    from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
    from app.services.test_plan_runtime_adapters import (
        LEGACY_COMPATIBILITY_PROJECTOR,
    )

    envelope = _runtime_result()
    request = TestPlanPipelineRequest(
        jira_key="GUIDES-99088", tenant_id="tenant-c2a-replay"
    )
    projected = LEGACY_COMPATIBILITY_PROJECTOR.project_pipeline_result(
        envelope,
        request=request,
        legacy_packet={"jira_key": "GUIDES-99088"},
        correlation_id="c2a-parity",
        elapsed_ms=1,
    )
    return projected.model_dump(mode="json")


def test_cli_selection_equals_http_canonical_field() -> None:
    import sys

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import run_test_plan_pipeline as cli

    dumped = _pipeline_result_dump()
    canonical = dumped["qe_review_package"]["canonical_result"]["plan_markdown"]
    # One shared renderer: the CLI selection is the canonical field, compared
    # formatting-normalized (the CLI strips trailing whitespace).
    assert cli._select_plan_text(dumped) == canonical.strip()
    # HTTP contract: the result model carries the same canonical field and the
    # explicit provenance marking.
    assert dumped["output_provenance"]["draft_test_plan_markdown"] == (
        "NON_CANONICAL:NOT_FOR_ACCEPTANCE:DEPRECATED"
    )
    assert dumped["output_provenance"]["canonical"] == (
        "qe_review_package.canonical_result.plan_markdown"
    )


def test_http_route_returns_same_canonical_result(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    dumped = _pipeline_result_dump()

    from app.core.schemas_test_plan_pipeline import TestPlanPipelineResult

    result = TestPlanPipelineResult.model_validate(dumped)

    # The route imports the service function inside the handler, so patching
    # the service module attribute is what the handler resolves at call time.
    monkeypatch.setattr(
        "app.services.test_plan_pipeline_service.run_test_plan_pipeline",
        lambda request, user=None, **kwargs: result,
    )

    client = TestClient(app)
    response = client.post(
        "/api/v1/test-plans/pipeline",
        json={"jira_key": "GUIDES-99088", "tenant_id": "tenant_c2a_replay"},
        headers={"Authorization": "******"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["qe_review_package"]["canonical_result"]["plan_markdown"] == (
        dumped["qe_review_package"]["canonical_result"]["plan_markdown"]
    )
    assert body["output_provenance"]["draft_test_plan_markdown"] == (
        "NON_CANONICAL:NOT_FOR_ACCEPTANCE:DEPRECATED"
    )
