import pytest

from app.services import chat_service, jira_chat_search_service


@pytest.mark.anyio
async def test_chat_turn_routes_jira_search_requests_without_calling_llm(monkeypatch):
    captured: dict[str, object] = {}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("LLM tool chat should not run for direct Jira search requests")

    async def fake_run_tool(
        name: str,
        params: dict,
        user_id: str = "chat-user",
        session_id: str | None = None,
        run_id: str | None = None,
        tenant_id: str = "kone",
    ):
        captured["name"] = name
        captured["params"] = params
        captured["user_id"] = user_id
        captured["session_id"] = session_id
        captured["run_id"] = run_id
        captured["tenant_id"] = tenant_id
        return {
            "query": "reltables",
            "source": "jira_index",
            "issues": [
                {
                    "issue_key": "GUIDES-42533",
                    "summary": "Reltable references fail in nested maps",
                    "status": "Open",
                    "issue_type": "Bug",
                    "url": "https://jira.example.com/browse/GUIDES-42533",
                }
            ],
            "message": "Found 1 matching Jira issue.",
        }

    monkeypatch.setattr(chat_service, "generate_chat_stream_with_tools", fail_if_called)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "can you fetch me the related jiras to reltables",
            user_id="real-user-7",
            tenant_id="kone",
        ):
            events.append(event)

        assert captured["name"] == "search_jira_issues"
        assert captured["params"] == {"query": "can you fetch me the related jiras to reltables"}
        assert captured["user_id"] == "real-user-7"
        assert captured["tenant_id"] == "kone"
        assert any(event.get("type") == "tool" and event.get("name") == "search_jira_issues" for event in events)
        assert any("GUIDES-42533" in str(event.get("content", "")) for event in events if event.get("type") == "chunk")

        messages = chat_service.get_messages(session_id)
        assistant = next(message for message in messages if message["role"] == "assistant")
        assert "search_jira_issues" in (assistant.get("tool_results") or {})
        assert "GUIDES-42533" in str(assistant.get("content") or "")
    finally:
        chat_service.delete_session(session_id)


def test_search_related_jira_issues_uses_indexed_fallback_when_live_jira_is_unavailable(monkeypatch):
    class _DummyClient:
        base_url = "https://jira.example.com"
        username = ""
        password = ""
        email = ""
        api_token = ""

    monkeypatch.setattr(jira_chat_search_service, "build_jira_client", lambda _tenant_id: _DummyClient())
    monkeypatch.setattr(jira_chat_search_service, "_search_live_jira", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        jira_chat_search_service,
        "_search_indexed_jira",
        lambda *_args, **_kwargs: [
            {
                "issue_key": "GUIDES-34724",
                "summary": "Relationship table output breaks in map preview",
                "status": "In Progress",
                "issue_type": "Bug",
                "url": "https://jira.example.com/browse/GUIDES-34724",
                "source": "jira_index",
            }
        ],
    )

    result = jira_chat_search_service.search_related_jira_issues(
        "can you fetch me the related jiras to reltables",
        tenant_id="kone",
    )

    assert result["query"] == "reltables"
    assert result["source"] == "jira_index"
    assert result["issues"][0]["issue_key"] == "GUIDES-34724"
    assert "cache" in result["message"].lower()


def test_search_related_jira_issues_reports_unavailable_without_inventing_issue_ids(monkeypatch):
    class _DummyClient:
        base_url = ""
        username = ""
        password = ""
        email = ""
        api_token = ""

    monkeypatch.setattr(jira_chat_search_service, "build_jira_client", lambda _tenant_id: _DummyClient())
    monkeypatch.setattr(jira_chat_search_service, "_search_live_jira", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(jira_chat_search_service, "_search_indexed_jira", lambda *_args, **_kwargs: [])

    result = jira_chat_search_service.search_related_jira_issues(
        "show me related jiras for reltables",
        tenant_id="kone",
    )

    assert result["issues"] == []
    assert result["source"] == "unavailable"
    assert "configured" in result["message"].lower()
    assert "AEM-6453" not in result["message"]
    assert "DITA-OT-1234" not in result["message"]


def test_search_related_jira_issues_filters_out_incorrect_semantic_matches(monkeypatch):
    class _DummyClient:
        base_url = "https://jira.example.com"
        username = ""
        password = ""
        email = ""
        api_token = ""

    monkeypatch.setattr(jira_chat_search_service, "build_jira_client", lambda _tenant_id: _DummyClient())
    monkeypatch.setattr(jira_chat_search_service, "_search_live_jira", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        jira_chat_search_service,
        "_search_indexed_jira",
        lambda *_args, **_kwargs: [
            {
                "issue_key": "GUIDES-11111",
                "summary": "Table rendering breaks in authoring view",
                "description": "The preview panel renders a malformed HTML table.",
                "status": "Open",
                "issue_type": "Bug",
                "url": "https://jira.example.com/browse/GUIDES-11111",
                "source": "jira_index",
            }
        ],
    )

    result = jira_chat_search_service.search_related_jira_issues(
        "show me related jiras for reltables",
        tenant_id="kone",
    )

    assert result["issues"] == []
    assert "GUIDES-11111" not in result["message"]


def test_search_related_jira_issues_keeps_alias_matches_for_reltables(monkeypatch):
    class _DummyClient:
        base_url = "https://jira.example.com"
        username = ""
        password = ""
        email = ""
        api_token = ""

    monkeypatch.setattr(jira_chat_search_service, "build_jira_client", lambda _tenant_id: _DummyClient())
    monkeypatch.setattr(jira_chat_search_service, "_search_live_jira", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        jira_chat_search_service,
        "_search_indexed_jira",
        lambda *_args, **_kwargs: [
            {
                "issue_key": "GUIDES-34724",
                "summary": "Relationship table output breaks in map preview",
                "description": "A reltable row disappears after save.",
                "status": "In Progress",
                "issue_type": "Bug",
                "url": "https://jira.example.com/browse/GUIDES-34724",
                "source": "jira_index",
            }
        ],
    )

    result = jira_chat_search_service.search_related_jira_issues(
        "show me related jiras for reltables",
        tenant_id="kone",
    )

    assert result["issues"][0]["issue_key"] == "GUIDES-34724"
    assert result["source"] == "jira_index"
