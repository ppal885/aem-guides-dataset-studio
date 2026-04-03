import pytest

from app.services import chat_service
from app.services.grounding_service import build_evidence_pack


def _make_pack(query: str, *, source: str, text: str, title: str):
    candidate = type(
        "Candidate",
        (),
        {
            "source": source,
            "label": title,
            "text": text,
            "url": "",
            "metadata": {"title": title},
            "score": 0.0,
        },
    )()
    return build_evidence_pack(query=query, tenant_id="kone", candidates=[candidate])


@pytest.mark.anyio
async def test_chat_turn_abstains_without_calling_llm_when_grounding_is_weak(monkeypatch):
    pack = build_evidence_pack(query="unsupported hidden feature", tenant_id="kone", candidates=[])

    async def fake_build_pack(*_args, **_kwargs):
        return pack, {"strength": "weak", "reason": pack.decision.reason}

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("LLM text generation should not run when grounding abstains early")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fake_build_pack)
    monkeypatch.setattr(chat_service, "generate_text", fail_if_called)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "Tell me about the unsupported hidden feature", tenant_id="kone"):
            events.append(event)

        assert any(event.get("type") == "grounding" for event in events)
        assert any("don't have enough verified information" in str(event.get("content", "")).lower() for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = next(message for message in messages if message["role"] == "assistant")
        assert "_grounding" in (assistant.get("tool_results") or {})
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_persists_grounding_metadata_for_supported_answer(monkeypatch):
    pack = build_evidence_pack(
        query="door operator terminology",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "tenant_context",
                    "label": "KONE terminology",
                    "text": "Use the term door operator in all author-facing task topics.",
                    "url": "",
                    "metadata": {"label": "KONE terminology", "doc_type": "terminology", "credibility": "0.95"},
                    "score": 0.0,
                },
            )(),
            type(
                "Candidate",
                (),
                {
                    "source": "tenant_examples",
                    "label": "approved-task.dita",
                    "text": "Approved example uses the phrase door operator in procedural steps.",
                    "url": "",
                    "metadata": {"filename": "approved-task.dita"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_build_pack(*_args, **_kwargs):
        return pack, {
            "strength": "strong",
            "reason": pack.decision.reason,
            "corrected_query": "",
            "correction_applied": False,
        }

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fake_build_pack)
    async def fake_generate_text(*_args, **_kwargs):
        return "Use the term door operator in the topic title and steps."

    monkeypatch.setattr(
        chat_service,
        "generate_text",
        fake_generate_text,
    )
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "How should I phrase door operator terminology?", tenant_id="kone"):
            events.append(event)

        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["citations"]
        assert grounding_event["grounding"]["status"] in {"grounded", "partial"}
        answer_chunks = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in answer_chunks
        assert "## Sources" in answer_chunks

        messages = chat_service.get_messages(session_id)
        assistant = next(message for message in messages if message["role"] == "assistant")
        assert "_grounding" in (assistant.get("tool_results") or {})
    finally:
        chat_service.delete_session(session_id)
