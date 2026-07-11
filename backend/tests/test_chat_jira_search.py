import pytest
from datetime import datetime
from uuid import uuid4

from app.services import chat_service, jira_chat_search_service
from app.db.chat_models import ChatMessage
from app.db.session import SessionLocal


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
        text = "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")
        assert "GUIDES-42533" in text
        assert "## Top Jira matches" in text
        assert "Open" in text
        assert "Bug" in text
        assert "â" not in text

        messages = chat_service.get_messages(session_id)
        assistant = next(message for message in messages if message["role"] == "assistant")
        assert "search_jira_issues" in (assistant.get("tool_results") or {})
        assert "GUIDES-42533" in str(assistant.get("content") or "")
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_vague_dita_ot_issue_followup_resolves_previous_topic(monkeypatch):
    captured: dict[str, object] = {}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Vague DITA-OT issue follow-up should resolve context and use Jira search")

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
        return {
            "query": params.get("query"),
            "source": "jira_index",
            "issues": [],
            "message": "No Jira issues matched the resolved topic.",
        }

    monkeypatch.setattr(chat_service, "generate_chat_stream_with_tools", fail_if_called)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Why can a conkeyref resolve differently after branch filtering?",
                created_at=datetime.utcnow(),
            )
        )
        db.commit()

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Give me any Jira issues of dita ot related to it",
            user_id="real-user-9",
            tenant_id="kone",
        ):
            events.append(event)

        assert captured["name"] == "search_jira_issues"
        resolved_query = str(captured["params"]["query"]).lower()
        assert "dita-ot" in resolved_query
        assert "conkeyref" in resolved_query
        assert "branch-filtering" in resolved_query
        assert " it" not in resolved_query
        assert any(event.get("type") == "tool" and event.get("name") == "search_jira_issues" for event in events)
    finally:
        db.close()
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_vague_dita_ot_issue_followup_uses_github_issue_corpus(monkeypatch):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("DITA-OT issue lookup should not fall through to generic LLM")

    def fake_retrieve(query: str, k: int = 4):
        assert "dita-ot" in query.lower()
        assert "conkeyref" in query.lower()
        assert "branch-filtering" in query.lower()
        assert " it" not in query.lower()
        return [
            {
                "issue_number": 1234,
                "title": "Branch filtering changes indirect reference resolution",
                "url": "https://github.com/dita-ot/dita-ot/issues/1234",
                "snippet": "A filtered branch can create a different effective key space for conkeyref resolution.",
            }
        ]

    monkeypatch.setattr(chat_service, "generate_chat_stream_with_tools", fail_if_called)
    monkeypatch.setattr("app.services.dita_ot_github_rag_service.retrieve_dita_ot_github_for_query", fake_retrieve)

    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Why can a conkeyref resolve differently after branch filtering?",
                created_at=datetime.utcnow(),
            )
        )
        db.commit()

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Give me any issues of dita ot related to it",
            user_id="real-user-10",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(
            event.get("type") == "tool" and event.get("name") == "search_dita_ot_github_issues"
            for event in events
        )
        text = "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")
        assert "DITA-OT GitHub issue lookup" in text
        assert "Branch filtering changes indirect reference resolution" in text
        assert "No Jira issues matched" not in text
        assert "dita ot it" not in text.lower()
    finally:
        db.close()
        chat_service.delete_session(session_id)


def test_dita_ot_issue_without_jira_does_not_route_to_jira_search():
    assert not chat_service._is_direct_jira_search_request("Give me any issues of dita ot related to it")
    assert not chat_service._is_direct_jira_search_request("Show DITA-OT GitHub issues about copy-to")
    assert chat_service._is_direct_jira_search_request("Show Jira issues about conkeyref branch filtering")


@pytest.mark.anyio
async def test_explicit_dita_ot_github_issues_bypass_agent_plan(monkeypatch):
    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("DITA-OT GitHub issue lookup should not use LLM/tool planning")

    def fake_retrieve(query: str, k: int = 4):
        assert "copy-to" in query.lower()
        return [
            {
                "issue_number": 991,
                "title": "copy-to links are rewritten incorrectly",
                "url": "https://github.com/dita-ot/dita-ot/issues/991",
                "snippet": "copy-to link rewrite issue",
            }
        ]

    monkeypatch.setattr(chat_service, "generate_chat_stream_with_tools", fail_if_called)
    monkeypatch.setattr("app.services.dita_ot_github_rag_service.retrieve_dita_ot_github_for_query", fake_retrieve)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Show DITA-OT GitHub issues about copy-to link rewriting",
            user_id="real-user-11",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(
            event.get("type") == "tool" and event.get("name") == "search_dita_ot_github_issues"
            for event in events
        )
        text = "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")
        assert "DITA-OT GitHub issue lookup" in text
        assert "copy-to links are rewritten incorrectly" in text
        assert "## Plan" not in text
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_routes_glossstatus_native_pdf_jira_prompt_without_calling_llm(monkeypatch):
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
        return {
            "query": "glossStatus native pdf",
            "source": "jira_index",
            "issues": [
                {
                    "issue_key": "GUIDES-881",
                    "summary": "Native PDF drops glossStatus in glossary bookmaps",
                    "status": "Open",
                    "issue_type": "Bug",
                    "url": "https://jira.example.com/browse/GUIDES-881",
                    "source": "jira_index",
                }
            ],
            "message": "Found 1 matching Jira issue.",
        }

    monkeypatch.setattr(chat_service, "generate_chat_stream_with_tools", fail_if_called)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    session_id = chat_service.create_session()
    try:
        events = []
        prompt = "Show me related Jira issues for glossStatus in Native PDF."
        async for event in chat_service.chat_turn(
            session_id,
            prompt,
            user_id="real-user-8",
            tenant_id="kone",
        ):
            events.append(event)

        assert captured["name"] == "search_jira_issues"
        assert captured["params"] == {"query": prompt}
        text = "".join(str(event.get("content", "")) for event in events if event.get("type") == "chunk")
        assert "GUIDES-881" in text
        assert "glossStatus" in text
        assert "Native PDF" in text
        assert "Open" in text
        assert "Bug" in text
        assert "â" not in text
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
