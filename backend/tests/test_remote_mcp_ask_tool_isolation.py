import asyncio

from app.api.routes import remote_mcp
from app.services import aem_guides_incident_answer_service, chat_service


def test_remote_ask_dita_expert_disables_chat_tool_routing(monkeypatch):
    captured = {}

    monkeypatch.setattr(aem_guides_incident_answer_service, "answer_aem_sites_oak_conflict_from_jira", lambda question: None)
    monkeypatch.setattr(chat_service, "create_session", lambda: "isolated-session")
    monkeypatch.setattr(chat_service, "delete_session", lambda session_id: None)

    async def fake_chat_turn(session_id, question, **kwargs):
        captured.update(kwargs)
        yield {"type": "chunk", "content": "Not verified from current evidence."}
        yield {"type": "grounding", "grounding": {"status": "abstain", "confidence": 0.2}}

    monkeypatch.setattr(chat_service, "chat_turn", fake_chat_turn)

    answer = asyncio.run(
        remote_mcp._ask_dita_expert(
            {"question": "Generate a behavior matrix for unresolved keyref", "tenant_id": "kone"}
        )
    )

    assert captured["allow_tool_routing"] is False
    assert "Not verified from current evidence" in answer
    assert "Status: abstain" in answer
