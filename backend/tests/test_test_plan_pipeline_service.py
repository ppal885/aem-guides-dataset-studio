"""Unit tests for the unified test-plan pipeline."""

from __future__ import annotations

from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
from app.services import test_plan_pipeline_service as pipeline


def _stub_issue(key: str = "GUIDES-49065") -> dict:
    return {
        "issue_key": key,
        "source": "jira_api",
        "summary": "Asset Status API fails for comma paths",
        "description": "POST /bin/guides/v1/assets/status with test,comma folder fails.",
        "labels": ["UAC_Check", "UAC_Done"],
        "expected_behavior": "Poll returns SUCCESS with full path intact.",
        "actual_behavior": "Job FAILED with Not an absolute path: comma/...",
    }


def _stub_packet(*, blocked: bool = False) -> dict:
    if blocked:
        return {
            "jira_key": "GUIDES-49065",
            "generation_mode": "blocked",
            "issue": _stub_issue(),
            "uac_label_gate": {"blocked_reason": "Missing UAC_Check"},
        }
    return {
        "jira_key": "GUIDES-49065",
        "generation_mode": "full_rag",
        "mcp_fast_mode": False,
        "issue": _stub_issue(),
        "uac_label_gate": {"uac_check_present": True, "uac_done_present": True},
        "experience_league_evidence": [{"title": "API doc"}],
        "learned_behavior_evidence": {
            "available": True,
            "results": [{"title": "Asset Status API behavior", "source_url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides"}],
        },
        "repo_evidence_status": "partial",
        "repository_evidence": {
            "status": "partial",
            "repositories": [
                {
                    "id": "starling",
                    "match_count": 1,
                    "matches": [{"path": "src/AssetStatusService.java", "line": 12}],
                }
            ],
        },
        "planning_seeds": {
            "test_area_seed": [
                {"id": "TA-1", "category": "Comma path repro", "priority": "P0", "rationale": "Customer repro"}
            ],
            "blast_radius_seed": [
                {"category": "POST API", "priority": "Direct", "rationale": "Entry point"}
            ],
            "regression_risk_seed": [
                {"id": "R-1", "priority": "P0", "rationale": "Path split failure"}
            ],
            "bug_hypothesis_seed": [
                {"rationale": "Comma delimiter in job properties"}
            ],
        },
        "implementation_diff_evidence": {"summary_line": "AssetStatusJobPathCodec added"},
    }


def _stub_uac() -> dict:
    return {
        "acceptance_criteria": ["POST accepts comma path", "Poll SUCCESS"],
        "similar_jira_evidence": [{"jira_key": "GUIDES-30456", "why_similar": "Same API family"}],
        "ambiguities": [],
        "quality_score": {"evidence_coverage": 0.8, "clarity_of_expectations": 0.9},
        "pm_questions": ["Is comma in file name in scope?"],
        "qa_questions": ["Which Author env for repro?"],
    }


def test_score_pipeline_high_when_evidence_rich():
    brief = pipeline.build_ticket_brief(_stub_packet())
    criteria = pipeline.build_evidence_grounded_acceptance_criteria(
        _stub_packet(), _stub_uac(), brief, None
    )
    cases = pipeline.build_grounded_test_cases(_stub_packet(), criteria, brief, None)
    coverage = pipeline.build_requirement_test_coverage(criteria, cases)
    score = pipeline.score_pipeline_readiness(
        _stub_packet(),
        _stub_uac(),
        ticket_brief=brief,
        acceptance_criteria=criteria,
        coverage_matrix=coverage,
    )
    assert score.overall >= 60
    assert score.tier in {"medium", "high"}
    assert not score.blockers
    assert score.dimensions
    assert score.routing_status in {"QE_REVIEW_WITH_FLAGS", "QE_REVIEW_READY"}


def test_score_pipeline_blocked_without_uac_check():
    score = pipeline.score_pipeline_readiness(_stub_packet(blocked=True), None)
    assert score.overall == 0
    assert score.tier == "blocked"
    assert score.human_review_required


def test_compose_draft_plan_action_first_layout():
    brief = pipeline.build_ticket_brief(_stub_packet())
    score = pipeline.score_pipeline_readiness(_stub_packet(), _stub_uac())
    md = pipeline.compose_draft_test_plan(_stub_packet(), _stub_uac(), score, brief)
    assert "## 1. Action items" in md
    assert "## 2. Supplementary" in md
    assert "**AC-1:**" in md
    assert "S-01" in md


def test_run_pipeline_blocked_skips_uac(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_packet",
        lambda *a, **k: _stub_packet(blocked=True),
    )
    from app.services import test_plan_artifact_service as artifacts

    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_DIR", tmp_path / ".pipeline-memory")
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_INDEX", tmp_path / ".pipeline-memory" / "index.json")

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(
            jira_key="GUIDES-49065",
            skip_uac_label_gate=False,
            include_uac_intelligence=True,
            compose_draft_plan=True,
        )
    )
    assert result.score.tier == "blocked"
    assert result.uac_intelligence is None
    assert result.draft_test_plan_markdown is None
    assert "rag" in result.stages_completed
    assert "pipeline_memory" in result.stages_completed


def test_run_pipeline_full_stages(monkeypatch, tmp_path):
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_packet",
        lambda *a, **k: _stub_packet(),
    )
    from app.services import test_plan_artifact_service as artifacts

    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_DIR", tmp_path / ".pipeline-memory")
    monkeypatch.setattr(artifacts, "PIPELINE_MEMORY_INDEX", tmp_path / ".pipeline-memory" / "index.json")

    def _fake_uac(*a, **k):
        return _stub_uac()

    import services.uac.uac_orchestrator as uac_mod

    monkeypatch.setattr(uac_mod, "run_requirement_intelligence", _fake_uac)

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(jira_key="GUIDES-49065", include_uac_intelligence=True)
    )
    assert "uac_intelligence" in result.stages_completed
    assert "draft_test_plan" in result.stages_completed
    assert result.draft_test_plan_markdown
    assert result.qe_handoff.review_status in {"Ready for QE review", "Needs human review", "Draft"}
    assert result.ticket_analysis["current_behaviour"]
    assert result.acceptance_criteria
    assert result.test_cases
    assert result.coverage_matrix["uac_coverage_percentage"] >= 0
    assert result.confidence_dimensions
    assert result.qe_review_package["review_id"].startswith("QE-GUIDES-49065-")
    assert result.state_history
    assert "pipeline_memory" in result.stages_completed
    assert artifacts.list_pipeline_memory("GUIDES-49065")
