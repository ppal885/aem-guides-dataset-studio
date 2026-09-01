"""Frozen FJ-00 replay guard for the default, provider-disabled runtime."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from app.core.schemas_canonical_test_plan_runtime import (
    GenerationProfile,
    RuntimeEntryPoint,
    stable_sha256,
)
from app.services.canonical_test_plan_runtime import CANONICAL_TEST_PLAN_RUNTIME


_WORKSPACE = Path(__file__).resolve().parents[2]
_BASELINE_CASES = _WORKSPACE / "analysis" / "fluffyjaws" / "00_baseline_cases.jsonl"
_PROVIDER_MODULES = (
    _WORKSPACE / "backend" / "app" / "services" / "reasoning_evidence_provider.py",
    _WORKSPACE / "backend" / "app" / "services" / "fluffyjaws_knowledge_provider.py",
    _WORKSPACE
    / "backend"
    / "app"
    / "services"
    / "reasoning_evidence_shadow_service.py",
)
_FORBIDDEN_IMPORTS = {
    "app.api.v1.routes.test_plans",
    "app.db.test_plan_feedback_models",
    "app.evidence_gateway.rag_adapter",
    "app.evaluation.uac_eval.scoring",
    "app.services.jira_client",
    "app.services.acceptance_promotion",
    "app.services.canonical_test_plan_reasoning_service",
    "app.services.canonical_test_plan_runtime",
    "app.services.enterprise_qa.qa_learning_engine",
    "app.services.test_plan_artifact_service",
    "app.services.test_plan_feedback_service",
    "benchmark.v2.evaluator_access",
}
_FORBIDDEN_CALLS = {
    "add_comment",
    "approve_test_plan_review",
    "normalize_user_feedback",
    "publish_test_plan",
    "post_acceptance_criteria_for_human_review",
    "record_test_plan_feedback",
    "request_test_plan_review_changes",
    "transition_issue",
    "update_issue",
}


def _stable_stage_trace(result: object) -> list[dict[str, object]]:
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


def test_fj00_frozen_artifacts_remain_valid_after_authorized_reasoning_change() -> None:
    records = [
        json.loads(line)
        for line in _BASELINE_CASES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 5

    for record in records:
        fixture = record["fixture"]
        request = CANONICAL_TEST_PLAN_RUNTIME.build_request(
            jira_key=fixture["jira_key"],
            tenant_id="fluffyjaws-baseline",
            entry_point=RuntimeEntryPoint.PYTHON_API,
            generation_profile=GenerationProfile.BACKEND_COMPATIBILITY,
        )
        result = CANONICAL_TEST_PLAN_RUNTIME.generate_backend_compatibility(
            request=request,
            packet=fixture,
        )
        stable_trace = _stable_stage_trace(result)

        assert stable_sha256(record["fixture"]) == record["fixture_sha256"]
        assert stable_sha256(record["stable_stage_trace"]) == record[
            "stable_stage_trace_sha256"
        ]
        assert result.request_id == record["request_id"]
        assert result.evidence_bundle_id == record["evidence_bundle_id"]
        assert result.trace.question_generation_trace is not None
        assert len(stable_trace) == len(record["stable_stage_trace"])
        assert [row["stage"] for row in stable_trace] == [
            row["stage"] for row in record["stable_stage_trace"]
        ]


def test_isolated_provider_modules_do_not_import_reasoning_or_delivery_layers() -> None:
    for path in _PROVIDER_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        for imported in imports:
            matches_forbidden = any(
                imported == forbidden
                or imported == forbidden.rsplit(".", 1)[-1]
                or imported.endswith(f".{forbidden.rsplit('.', 1)[-1]}")
                for forbidden in _FORBIDDEN_IMPORTS
            )
            assert not matches_forbidden, (
                f"forbidden isolated-provider import: {imported}"
            )
        call_names = {
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else ""
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
        }
        assert not call_names.intersection(_FORBIDDEN_CALLS), (
            "isolated provider cannot call feedback, review, or publish surfaces"
        )
