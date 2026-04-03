import pytest

from app.services import chat_service
from app.services.chat_service import _builtin_capability_response, _is_capability_prompt
from app.services.grounding_service import build_evidence_pack


def test_is_capability_prompt_matches_help_questions():
    assert _is_capability_prompt("What is your use?")
    assert _is_capability_prompt("What can you do")
    assert _is_capability_prompt("help")


def test_builtin_capability_response_lists_core_chat_uses():
    text = _builtin_capability_response("kone")

    assert "Summarize Jira issues and comments" in text
    assert "conref" in text.lower() and "keyref" in text.lower()
    assert "DITA bundles" in text or "DITA bundle" in text
    assert "Current workspace: `kone`" in text


@pytest.mark.anyio
async def test_build_local_fallback_response_reviews_xml_with_local_suggestions(monkeypatch):
    def fake_rag_context(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(chat_service, "_build_rag_context", fake_rag_context)

    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "technicalContent/dtd/task.dtd">
<task id="guides_34724" xml:lang="en-US">
  <title>Resolve context highlighting on hover in AEM Guides</title>
  <shortdesc>Resolve the hover highlighting issue in AEM Guides.</shortdesc>
  <taskbody>
    <context><p>Use this task when context highlighting is wrong.</p></context>
    <steps><step><cmd>Update the hover styling.</cmd></step></steps>
    <result><p>The context highlights correctly on hover.</p></result>
  </taskbody>
</task>"""

    text = await chat_service._build_local_fallback_response(
        xml,
        "kone",
        {"issue_key": "GUIDES-34724", "issue_summary": "Resolve context highlighting on hover in AEM Guides"},
    )

    assert "Using local XML analysis" in text
    assert "Suggestions found:" in text
    assert "conref" in text.lower() or "keyword" in text.lower() or "keyref" in text.lower()
    assert "Workspace: `kone`" in text


@pytest.mark.anyio
async def test_chat_turn_uses_local_fallback_when_llm_is_unavailable(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    monkeypatch.setattr(
        chat_service,
        "_build_rag_context",
        lambda *_args, **_kwargs: "AEM GUIDES DOCUMENTATION:\n[1] topichead\ntopichead defines a navigation title override.",
    )

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "Explain topichead", tenant_id="kone"):
            events.append(event)

        assert events[-1]["type"] == "done"
        assert any(event["type"] == "chunk" for event in events)
        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "local indexed knowledge" in text.lower()
        assert "topichead" in text.lower()
        assert "not configured" in text.lower() or "disabled" in text.lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_falls_back_to_local_answer_on_provider_failure(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(
        chat_service,
        "_build_rag_context",
        lambda *_args, **_kwargs: "DITA SPEC REFERENCE:\n[1] topichead\ntopichead is used for generated navigation labels.",
    )

    pack = build_evidence_pack(
        query="What is a topichead?",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "dita_spec",
                    "label": "DITA Spec",
                    "text": "topichead is used for generated navigation labels.",
                    "url": "",
                    "metadata": {"title": "DITA Spec"},
                    "score": 0.0,
                },
            )(),
            type(
                "Candidate",
                (),
                {
                    "source": "aem_guides",
                    "label": "Experience League",
                    "text": "AEM Guides uses topichead for navigation structures in maps.",
                    "url": "",
                    "metadata": {"title": "Experience League"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_build_pack(*_args, **_kwargs):
        return pack, {"strength": "strong", "reason": pack.decision.reason}

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fake_build_pack)

    async def failing_generate_text(*_args, **_kwargs):
        raise RuntimeError("Error code: 429 - rate limit exceeded")

    monkeypatch.setattr(chat_service, "generate_text", failing_generate_text)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "What is a topichead?", tenant_id="kone"):
            events.append(event)

        assert events[-1]["type"] == "done"
        assert not any(event["type"] == "error" for event in events)
        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "local indexed knowledge" in text.lower()
        assert "topichead" in text.lower()
        assert "rate-limited" in text.lower() or "temporarily busy" in text.lower()
    finally:
        chat_service.delete_session(session_id)
