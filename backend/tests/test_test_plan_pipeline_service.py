"""Tests for the single canonical Test Plan pipeline entry point."""

from __future__ import annotations

from app.core.schemas_canonical_test_plan_runtime import (
    CANONICAL_STAGE_ORDER,
    ClaudeMissingQuestionSubmission,
    MissingQuestion,
    MissingQuestionOrigin,
)
from app.core.schemas_test_plan_pipeline import TestPlanPipelineRequest
from app.services import test_plan_pipeline_service as pipeline


def _accepted_packet(key: str = "GUIDES-49065") -> dict:
    return {
        "jira_key": key,
        "issue": {
            "issue_key": key,
            "source": "jira_api",
            "summary": "The editor updates a configured friendly name automatically.",
            "labels": ["accepted_uac"],
            "acceptance_criteria": [
                "The editor updates a configured friendly name automatically."
            ],
        },
    }


def _blocked_packet(key: str = "GUIDES-49066") -> dict:
    return {
        "jira_key": key,
        "issue": {
            "issue_key": key,
            "source": "jira_api",
        },
    }


def _patch_artifact_storage(monkeypatch, tmp_path):
    from app.services import test_plan_artifact_service as artifacts

    monkeypatch.setattr(artifacts, "TEST_PLANS_DIR", tmp_path)
    monkeypatch.setattr(
        artifacts,
        "PIPELINE_MEMORY_DIR",
        tmp_path / ".pipeline-memory",
    )
    monkeypatch.setattr(
        artifacts,
        "PIPELINE_MEMORY_INDEX",
        tmp_path / ".pipeline-memory" / "index.json",
    )
    return artifacts


def test_service_exposes_only_the_canonical_pipeline_api() -> None:
    assert pipeline.__all__ == ["run_test_plan_pipeline"]
    for removed in (
        "build_ticket_brief",
        "build_evidence_grounded_acceptance_criteria",
        "score_pipeline_readiness",
        "compose_draft_test_plan",
        "render_pipeline_result_markdown",
        "write_starling_artifacts",
    ):
        assert not hasattr(pipeline, removed)


def test_pipeline_retrieves_once_and_runs_the_full_canonical_stage_order(
    monkeypatch,
    tmp_path,
) -> None:
    calls = 0

    def evidence_packet(*args, **kwargs):
        nonlocal calls
        calls += 1
        return _accepted_packet()

    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_evidence_packet",
        evidence_packet,
    )
    _patch_artifact_storage(monkeypatch, tmp_path)

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(jira_key="GUIDES-49065")
    )

    assert calls == 1
    assert result.score.tier != "blocked"
    assert result.draft_test_plan_markdown
    assert result.stages_completed[: len(CANONICAL_STAGE_ORDER)] == [
        stage.value for stage in CANONICAL_STAGE_ORDER
    ]
    canonical = result.qe_review_package["canonical_result"]
    assert canonical["status"] == "completed"
    assert canonical["validation_status"] == "passed"
    assert canonical["postable"] is True
    assert canonical["run_id"]
    assert canonical["trace"]["stage_trace"]


def test_pipeline_exposes_preparation_and_accepts_hash_bound_claude_questions(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_evidence_packet",
        lambda *args, **kwargs: _accepted_packet("GUIDES-49069"),
    )
    _patch_artifact_storage(monkeypatch, tmp_path)

    prepared = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(jira_key="GUIDES-49069")
    )
    questions = [
        MissingQuestion.model_validate(
            {
                **row,
                "origin": MissingQuestionOrigin.CLAUDE_DESKTOP.value,
            }
        )
        for row in prepared.missing_question_quality["accepted_questions"]
    ]
    submission = ClaudeMissingQuestionSubmission(
        preparation_id=prepared.qe_investigation["preparation_id"],
        questions=questions,
    )

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(
            jira_key="GUIDES-49069",
            claude_question_submission=submission,
        )
    )

    assert result.qe_investigation["preparation_id"] == submission.preparation_id
    assert result.missing_question_quality["question_origin"] == "CLAUDE_DESKTOP"
    assert result.missing_question_quality["accepted_questions"]
    assert result.missing_question_resolutions


def test_non_postable_result_does_not_write_any_artifact(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_evidence_packet",
        lambda *args, **kwargs: _blocked_packet(),
    )
    artifacts = _patch_artifact_storage(monkeypatch, tmp_path)

    def unexpected_write(*args, **kwargs):
        raise AssertionError("blocked canonical runs must be side-effect free")

    monkeypatch.setattr(artifacts, "record_pipeline_memory", unexpected_write)
    monkeypatch.setattr(artifacts, "save_test_plan", unexpected_write)
    monkeypatch.setattr(
        pipeline, "_write_canonical_starling_artifacts", unexpected_write
    )

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(
            jira_key="GUIDES-49066",
            write_starling_artifacts=True,
            publish_to_team_ui=True,
        )
    )

    assert result.score.tier == "blocked"
    assert result.artifacts_written == []
    assert result.qe_review_package["canonical_result"]["postable"] is False


def test_benchmark_entrypoint_is_always_side_effect_free(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_evidence_packet",
        lambda *args, **kwargs: _accepted_packet("GUIDES-49067"),
    )
    artifacts = _patch_artifact_storage(monkeypatch, tmp_path)

    def unexpected_write(*args, **kwargs):
        raise AssertionError("benchmark runs must not write production artifacts")

    monkeypatch.setattr(artifacts, "record_pipeline_memory", unexpected_write)
    monkeypatch.setattr(artifacts, "save_test_plan", unexpected_write)
    monkeypatch.setattr(
        pipeline, "_write_canonical_starling_artifacts", unexpected_write
    )

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(
            jira_key="GUIDES-49067",
            write_starling_artifacts=True,
            publish_to_team_ui=True,
        ),
        entry_point="benchmark_v2",
        benchmark_split="train",
        benchmark_input={
            "record_id": "GUIDES-49067",
            "summary": "The editor updates a configured friendly name automatically.",
        },
    )

    assert result.artifacts_written == []
    assert result.qe_review_package["trace"]["entry_point"] == "benchmark_v2"


def test_postable_run_persists_only_canonical_markdown(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        pipeline,
        "build_guides_test_plan_evidence_packet",
        lambda *args, **kwargs: _accepted_packet("GUIDES-49068"),
    )
    artifacts = _patch_artifact_storage(monkeypatch, tmp_path)
    saved_markdown: list[str] = []

    def save_test_plan(key: str, markdown: str):
        saved_markdown.append(markdown)
        return {"filename": f"{key}-test-plan.md"}

    monkeypatch.setattr(artifacts, "save_test_plan", save_test_plan)
    monkeypatch.setattr(
        artifacts,
        "record_pipeline_memory",
        lambda result: {"memory_path": "memory.json"},
    )

    result = pipeline.run_test_plan_pipeline(
        TestPlanPipelineRequest(
            jira_key="GUIDES-49068",
            publish_to_team_ui=True,
        )
    )

    assert saved_markdown == [result.draft_test_plan_markdown]
    assert "publish_team_ui" in result.stages_completed
    assert "pipeline_memory" in result.stages_completed
