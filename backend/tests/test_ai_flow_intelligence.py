import shutil
from pathlib import Path
from uuid import uuid4

import pytest
from app.services import ai_flow_intelligence_service as flow_service


@pytest.fixture
def flow_state(monkeypatch):
    temp_dir = Path(__file__).resolve().parent.parent / "storage" / "test_ai_flow"
    temp_dir.mkdir(parents=True, exist_ok=True)
    state_path = temp_dir / f"{uuid4().hex}.json"
    monkeypatch.setattr(flow_service, "_state_path", lambda: state_path)
    try:
        yield state_path
    finally:
        for path in (state_path, state_path.with_suffix(".tmp")):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_query_source_learning_degrades_and_recovers(flow_state):
    source, note = flow_service.choose_query_source("kone", "aem_guides", "tavily")
    assert source == "tavily"
    assert note == ""

    flow_service.record_query_result("kone", "aem_guides", "tavily", success=False, error="timeout")
    flow_service.record_query_result("kone", "aem_guides", "tavily", success=False, error="timeout")

    source, note = flow_service.choose_query_source("kone", "aem_guides", "tavily")
    assert source == "rag"
    assert "Learning" in note

    flow_service.record_query_result("kone", "aem_guides", "tavily", success=True, result_count=2)
    snapshot = flow_service.get_tenant_flow_intelligence("kone")
    category = next(item for item in snapshot["query_health"] if item["category"] == "aem_guides")
    assert category["preferred_source"] == "tavily"
    assert category["learning_note"].startswith("Self-healing")


def test_authoring_learning_tracks_failed_checks_and_healing(flow_state):
    flow_service.record_authoring_outcome(
        "kone",
        "task",
        quality_score=52,
        validation=[
            {"label": "xml:lang present", "passing": False},
            {"label": "taskbody present", "passing": False},
        ],
        healed=True,
        healing_actions=["structural_repair", "repair_prompt"],
    )

    hints = flow_service.get_authoring_hints("kone", "task")
    snapshot = flow_service.get_tenant_flow_intelligence("kone")
    task_health = next(item for item in snapshot["authoring_health"] if item["dita_type"] == "task")

    assert any("xml:lang" in hint for hint in hints)
    assert any("taskbody" in hint for hint in hints)
    assert task_health["healed_runs"] == 1
    assert any(item["strategy"] == "repair_prompt" for item in task_health["healing_strategies"])


def test_recipe_learning_prefers_proven_alternative(flow_state):
    flow_service.record_recipe_outcome("keyref", "basic_key_resolution", "keys.keydef_basic", success=False)
    flow_service.record_recipe_outcome("keyref", "basic_key_resolution", "keys.keydef_basic", success=False)
    flow_service.record_recipe_outcome("keyref", "basic_key_resolution", "llm_generated_dita", success=True)
    flow_service.record_recipe_outcome("keyref", "basic_key_resolution", "llm_generated_dita", success=True)
    flow_service.record_recipe_outcome("keyref", "basic_key_resolution", "llm_generated_dita", success=True)

    recipe, reason = flow_service.recommend_recipe("keyref", "basic_key_resolution", "keys.keydef_basic")

    assert recipe == "llm_generated_dita"
    assert "performed better" in reason
