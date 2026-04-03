import pytest

from app.services import chat_service, chat_tools
from app.api.v1.routes import chat as chat_routes


@pytest.mark.anyio
async def test_execute_create_job_starts_background_generation_and_returns_contract(monkeypatch):
    captured: dict[str, object] = {}

    def fake_enforce(user_id: str) -> None:
        captured["limit_user_id"] = user_id

    def fake_create(config_dict: dict, *, user_id: str, name: str):
        captured["create_user_id"] = user_id
        captured["create_name"] = name
        captured["create_config"] = config_dict
        return {
            "id": "job-123",
            "name": name,
            "status": "pending",
            "created_at": "2026-03-23T10:00:00",
            "config": {"name": name, "recipes": [{"type": "task_topics"}]},
        }

    def fake_start(job_id: str, config_dict: dict) -> None:
        captured["started_job_id"] = job_id
        captured["started_config"] = config_dict

    monkeypatch.setattr(chat_tools, "enforce_concurrent_job_limit", fake_enforce)
    monkeypatch.setattr(chat_tools, "create_dataset_job_record", fake_create)
    monkeypatch.setattr(chat_tools, "start_dataset_job_in_background", fake_start)

    result = await chat_tools.execute_create_job(
        "task_topics",
        config={"name": "Enterprise task job"},
        user_id="real-user-7",
    )

    assert captured["limit_user_id"] == "real-user-7"
    assert captured["create_user_id"] == "real-user-7"
    assert captured["started_job_id"] == "job-123"
    assert result == {
        "job_id": "job-123",
        "name": "Enterprise task job",
        "recipe_type": "task_topics",
        "status": "pending",
        "status_url": "/api/v1/jobs/job-123",
        "download_url": "/api/v1/datasets/job-123/download",
        "message": "Dataset generation started. The in-chat status card will update when the ZIP is ready.",
    }


def test_chat_route_passes_authenticated_user_id_to_chat_turn(client, auth_headers, monkeypatch):
    captured: dict[str, object] = {}

    async def fake_chat_turn(session_id: str, user_content: str, user_id: str = "chat-user", **kwargs):
        captured["session_id"] = session_id
        captured["user_content"] = user_content
        captured["user_id"] = user_id
        captured["tenant_id"] = kwargs.get("tenant_id")
        yield {"type": "done"}

    monkeypatch.setattr(chat_routes, "chat_turn", fake_chat_turn)

    session_id = chat_service.create_session()
    try:
        response = client.post(
            f"/api/v1/chat/sessions/{session_id}/messages",
            headers=auth_headers,
            json={"content": "Generate a task dataset"},
        )
        assert response.status_code == 200
        _ = response.text
        assert captured["session_id"] == session_id
        assert captured["user_content"] == "Generate a task dataset"
        assert captured["user_id"] == "test-user-1"
    finally:
        chat_service.delete_session(session_id)
