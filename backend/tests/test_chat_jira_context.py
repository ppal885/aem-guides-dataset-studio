"""Jira/ticket field: persistence, tool merge, and regenerate wiring for text-only chat."""

import pytest

from app.services import chat_service
from app.services import chat_tools


def test_user_supplied_jira_system_block_empty_when_no_context():
    assert chat_service._user_supplied_jira_system_block(None) == ""
    assert chat_service._user_supplied_jira_system_block("") == ""
    assert chat_service._user_supplied_jira_system_block("   ") == ""


def test_user_supplied_jira_system_block_includes_trimmed_ticket_text():
    block = chat_service._user_supplied_jira_system_block("PROJ-1\nDo the thing.")
    assert "USER-SUPPLIED JIRA" in block
    assert "PROJ-1" in block
    assert "Do the thing." in block


@pytest.mark.anyio
async def test_chat_turn_persists_jira_context_without_attachments(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Hello",
            tenant_id="kone",
            jira_context="TICKET-42\nAcceptance: foo bar",
        ):
            pass
        msgs = chat_service.get_messages(session_id)
        user = next(m for m in msgs if m["role"] == "user")
        assert user["tool_results"] is not None
        assert user["tool_results"]["_jira_context"] == "TICKET-42\nAcceptance: foo bar"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_run_tool_merges_jira_into_generate_dita(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_execute_generate_dita(text: str, **kwargs: object) -> dict:
        captured["text"] = text
        return {"ok": True, "jira_id": "TEXT-test", "run_id": "r1"}

    monkeypatch.setattr(chat_tools, "execute_generate_dita", fake_execute_generate_dita)

    await chat_tools.run_tool(
        "generate_dita",
        {"text": "Write a short concept about widgets."},
        jira_context="JIRA-9\nWidget must support offline mode.",
    )
    assert "JIRA-9" in captured["text"]
    assert "offline mode" in captured["text"]
    assert "widgets" in captured["text"]


@pytest.mark.anyio
async def test_run_tool_skips_jira_merge_when_already_substring_of_text(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_execute_generate_dita(text: str, **kwargs: object) -> dict:
        captured["text"] = text
        return {"ok": True}

    monkeypatch.setattr(chat_tools, "execute_generate_dita", fake_execute_generate_dita)

    body = "JIRA-9\nWidget must support offline mode."
    await chat_tools.run_tool(
        "generate_dita",
        {"text": f"Please use this issue.\n\n{body}"},
        jira_context=body,
    )
    assert captured["text"] == f"Please use this issue.\n\n{body}"


@pytest.mark.anyio
async def test_run_tool_merges_jira_into_create_job_prompt_text(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_execute_create_job(
        recipe_type: str,
        config: dict | None = None,
        user_id: str = "chat-user",
        *,
        subject: str = "",
        prompt_text: str = "",
        trace_id: str | None = None,
        jira_id: str | None = None,
    ) -> dict:
        captured["prompt_text"] = prompt_text
        return {"job_id": "job-1"}

    monkeypatch.setattr(chat_tools, "execute_create_job", fake_execute_create_job)

    await chat_tools.run_tool(
        "create_job",
        {"recipe_type": "task_topics", "subject": "Demo", "prompt_text": "Focus on install steps."},
        jira_context="REQ-100\nMust cover Linux only.",
    )
    assert "REQ-100" in captured["prompt_text"]
    assert "Linux only" in captured["prompt_text"]
    assert "install steps" in captured["prompt_text"]


@pytest.mark.anyio
async def test_regenerate_passes_persisted_jira_for_text_only_turn(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    orig_stream = chat_service._stream_assistant_reply
    contexts: list[str | None] = []

    async def spy(*args, **kwargs):
        contexts.append(kwargs.get("jira_context"))
        async for ev in orig_stream(*args, **kwargs):
            yield ev

    monkeypatch.setattr(chat_service, "_stream_assistant_reply", spy)

    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Hi",
            tenant_id="kone",
            jira_context="X-1: regeneration note",
        ):
            pass
        assert contexts and contexts[0] == "X-1: regeneration note"

        contexts.clear()
        async for _ in chat_service.regenerate_last_assistant(session_id, tenant_id="kone"):
            pass
        assert contexts and contexts[0] == "X-1: regeneration note"
    finally:
        chat_service.delete_session(session_id)
