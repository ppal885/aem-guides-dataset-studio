"""Tests for Jira → LLM plan → dataset job + optional runner/preset persistence."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_parse_create_job_from_jira_normalizes_inline_browse_url() -> None:
    from app.services.chat_tools import parse_tool_intent_from_content

    intent = parse_tool_intent_from_content(
        "/create_job_from_jira https://jira.corp.adobe.com/browse/GUIDES-45800"
    )

    assert intent is not None
    assert intent["name"] == "create_job_from_jira"
    assert intent["args"]["jira_key"] == "GUIDES-45800"


def test_parse_create_job_from_jira_normalizes_body_browse_url() -> None:
    from app.services.chat_tools import parse_tool_intent_from_content

    intent = parse_tool_intent_from_content(
        "/create_job_from_jira\n\nhttps://jira.corp.adobe.com/browse/GUIDES-45800"
    )

    assert intent is not None
    assert intent["name"] == "create_job_from_jira"
    assert intent["args"]["jira_key"] == "GUIDES-45800"


@pytest.mark.anyio
async def test_execute_create_job_from_jira_plan_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_plan(*_a, **_k):
        return {"ok": False, "error": "Invalid or disallowed recipe_type from model: 'bogus'.", "classification": {"recipe_type": "bogus"}}

    monkeypatch.setattr(
        "app.services.jira_dataset_plan_service.plan_dataset_job_from_jira_issue",
        fake_plan,
    )
    from app.services.chat_tools import execute_create_job_from_jira

    out = await execute_create_job_from_jira("GUIDES-1", user_id="u1", tenant_id="default")
    assert out.get("error")
    assert "recipe_type" in (out.get("error") or "")


@pytest.mark.anyio
async def test_execute_create_job_from_jira_normalizes_browse_url_before_planning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_plan(jira_key: str, **_kwargs):
        captured["jira_key"] = jira_key
        return {"ok": False, "error": "planned stop"}

    monkeypatch.setattr(
        "app.services.jira_dataset_plan_service.plan_dataset_job_from_jira_issue",
        fake_plan,
    )
    from app.services.chat_tools import execute_create_job_from_jira

    out = await execute_create_job_from_jira(
        "https://jira.corp.adobe.com/browse/GUIDES-45800",
        user_id="u1",
        tenant_id="default",
    )

    assert captured["jira_key"] == "GUIDES-45800"
    assert out.get("error") == "planned stop"


@pytest.mark.anyio
async def test_execute_create_job_from_jira_saves_runner_and_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_plan(*_a, **_k):
        return {
            "ok": True,
            "jira_key": "GUIDES-99",
            "recipe_type": "task_topics",
            "base_config": {
                "name": "Chat Job - task_topics",
                "seed": "chat-seed",
                "root_folder": "/content/dam/dataset-studio",
                "windows_safe_filenames": True,
                "recipes": [
                    {
                        "type": "task_topics",
                        "topic_count": 3,
                        "steps_per_task": 2,
                        "include_prereq": True,
                        "include_result": True,
                        "include_map": True,
                        "pretty_print": True,
                    }
                ],
            },
            "subject": "Widgets",
            "prompt_text": "",
            "classification": {"recipe_type": "task_topics", "save_runner": True, "preset_label": "bulk_a"},
            "save_runner": True,
            "preset_label": "bulk_a",
        }

    monkeypatch.setattr(
        "app.services.jira_dataset_plan_service.plan_dataset_job_from_jira_issue",
        fake_plan,
    )

    async def fake_execute_create_job(*_a, **_k):
        return {
            "job_id": "job-test-1",
            "recipe_type": "task_topics",
            "status": "pending",
            "download_url": "/api/v1/jobs/job-test-1/download",
            "status_url": "/api/v1/jobs/job-test-1",
        }

    monkeypatch.setattr("app.services.chat_tools.execute_create_job", fake_execute_create_job)

    class _JobRow:
        user_id = "chat-user"
        config = {
            "__artifact_tenant_id__": "default",
            "name": "Chat Job - task_topics",
            "seed": "chat-seed",
            "root_folder": "/content/dam/dataset-studio",
            "windows_safe_filenames": True,
            "recipes": [
                {
                    "type": "task_topics",
                    "topic_count": 3,
                    "steps_per_task": 2,
                    "include_prereq": True,
                    "include_result": True,
                    "include_map": True,
                    "pretty_print": True,
                }
            ],
        }

    mock_crud = MagicMock()

    def _get_job(_session, jid: str):
        return _JobRow() if jid == "job-test-1" else None

    mock_crud.get_job = _get_job
    monkeypatch.setattr("app.services.chat_tools.crud", mock_crud)
    monkeypatch.setattr("app.services.chat_bulk_preset_service.crud", mock_crud)

    persisted: dict = {}

    def _persist(**kwargs):
        persisted.update(kwargs)
        return "runner_scripts/default/bulk_a_GUIDES_99_ab12cd34.py"

    monkeypatch.setattr(
        "app.services.runner_script_persist_service.persist_cli_script_file",
        _persist,
    )

    monkeypatch.setattr(
        "app.services.chat_tools.normalize_dataset_job_config",
        lambda cfg: dict(cfg),
    )
    monkeypatch.setattr(
        "app.services.chat_tools.render_jobs_api_python_script",
        lambda **kwargs: "# script\n",
    )

    saved: dict = {}

    def _save_bulk_preset(**kwargs):
        saved.update(kwargs)
        return {"preset_id": "preset-1", "label": kwargs.get("label"), "source_job_id": kwargs.get("job_id"), "message": "ok"}

    monkeypatch.setattr("app.services.chat_tools.save_bulk_preset", _save_bulk_preset)

    from app.services.chat_tools import execute_create_job_from_jira

    out = await execute_create_job_from_jira(
        "GUIDES-99",
        user_id="chat-user",
        tenant_id="default",
        preset_label="",
        force_save_runner=False,
    )
    assert out.get("job_id") == "job-test-1"
    assert out.get("jira_key") == "GUIDES-99"
    assert out.get("runner_script_saved_path") == "runner_scripts/default/bulk_a_GUIDES_99_ab12cd34.py"
    assert saved.get("job_id") == "job-test-1"
    assert saved.get("jira_key") == "GUIDES-99"
    assert saved.get("runner_script_relpath") == "runner_scripts/default/bulk_a_GUIDES_99_ab12cd34.py"
    assert persisted.get("tenant_id") == "default"
    assert isinstance(persisted.get("script_body"), str)


@pytest.mark.anyio
async def test_plan_clamps_topic_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """PARAM_CAPS enforcement on recipe_overrides (no LLM call)."""
    from app.services.ai_executor_service import PARAM_CAPS
    from app.services.jira_dataset_plan_service import plan_dataset_job_from_jira_issue

    cap = int(PARAM_CAPS.get("topic_count") or 200)
    huge = cap + 5000

    async def fake_generate_text(_system: str, _user: str, **_k):
        return (
            '{"recipe_type":"task_topics","subject":"S","prompt_text":"","recipe_overrides":'
            f'{{"topic_count":{huge}}},"save_runner":false,"preset_label":"","rationale":"t"}}'
        )

    monkeypatch.setattr("app.services.jira_dataset_plan_service.fetch_issue_text_for_generate", lambda _k: ("Title: T\n\nBody.", None))
    monkeypatch.setattr("app.services.jira_dataset_plan_service.is_llm_available", lambda: True)
    monkeypatch.setattr("app.services.jira_dataset_plan_service.generate_text", fake_generate_text)

    from app.services.chat_tools import RECIPE_TYPE_ALLOWLIST

    plan = await plan_dataset_job_from_jira_issue("GUIDES-2", allowlist=RECIPE_TYPE_ALLOWLIST)
    assert plan.get("ok") is True
    recipes = plan["base_config"].get("recipes") or []
    assert recipes and int(recipes[0].get("topic_count") or 0) <= cap


@pytest.mark.anyio
async def test_plan_accepts_jira_browse_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services.ai_executor_service import PARAM_CAPS
    from app.services.jira_dataset_plan_service import plan_dataset_job_from_jira_issue

    cap = int(PARAM_CAPS.get("topic_count") or 200)

    async def fake_generate_text(_system: str, _user: str, **_k):
        return (
            '{"recipe_type":"task_topics","subject":"S","prompt_text":"","recipe_overrides":'
            f'{{"topic_count":{cap}}},"save_runner":false,"preset_label":"","rationale":"t"}}'
        )

    monkeypatch.setattr("app.services.jira_dataset_plan_service.fetch_issue_text_for_generate", lambda _k: ("Title: T\n\nBody.", None))
    monkeypatch.setattr("app.services.jira_dataset_plan_service.is_llm_available", lambda: True)
    monkeypatch.setattr("app.services.jira_dataset_plan_service.generate_text", fake_generate_text)

    from app.services.chat_tools import RECIPE_TYPE_ALLOWLIST

    plan = await plan_dataset_job_from_jira_issue(
        "https://jira.corp.adobe.com/browse/GUIDES-77",
        allowlist=RECIPE_TYPE_ALLOWLIST,
    )
    assert plan.get("ok") is True
    assert plan.get("jira_key") == "GUIDES-77"
