import pytest

from app.services import chat_service
from app.services.chat_service import (
    _builtin_capability_response,
    _grounded_fact_matches_question,
    _is_capability_prompt,
)
from app.core.schemas_grounded_answer import NormalizedGroundedFactSet
from app.services.grounding_service import build_evidence_pack


def test_is_capability_prompt_matches_help_questions():
    assert _is_capability_prompt("What is your use?")
    assert _is_capability_prompt("What can you do")
    assert _is_capability_prompt("help")


def test_builtin_capability_response_lists_core_chat_uses():
    text = _builtin_capability_response("kone")

    assert "Summarize Jira issues and comments" in text
    assert "conref" in text.lower() and "keyref" in text.lower()
    assert "DITA-OT" in text
    assert "Current workspace: `kone`" in text


def test_grounded_fact_guard_rejects_topic_card_for_pdf_troubleshooting():
    facts = NormalizedGroundedFactSet(
        answer_kind="dita_element",
        source_policy="standards_doc",
        canonical_definition="<topic> is the base information unit in DITA.",
        allowed_children=["title", "shortdesc", "body", "related-links"],
        companion_attributes=["id", "conref", "xml:lang"],
    )

    assert not _grounded_fact_matches_question(
        "How do I debug a topic that publishes in HTML but fails in PDF?",
        facts,
    )
    assert _grounded_fact_matches_question(
        "What is a DITA topic and what can it contain?",
        facts,
    )


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
async def test_build_local_fallback_response_prefers_grounded_publish_filtering_answer(monkeypatch):
    pack = build_evidence_pack(
        query="exclude draft-only content at publish time",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "dita_spec",
                    "label": "DITAVAL",
                    "text": "DITAVAL Conditional Processing filters content based on profiling attributes.",
                    "url": "",
                    "metadata": {"title": "DITAVAL"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_grounded_pack(**_kwargs):
        return pack, {"strength": "partial", "reason": pack.decision.reason}, {}

    monkeypatch.setattr(chat_service, "_build_grounded_tool_evidence_pack", fake_grounded_pack)
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "DITA SPEC REFERENCE:\n[1] ditaval\nFiltering profile")

    text = await chat_service._build_local_fallback_response(
        "How do I exclude draft-only content at publish time?",
        "kone",
        answer_mode="grounded_dita_answer",
    )

    lowered = text.lower()
    assert "conditional processing" in lowered
    assert ".ditaval" in lowered
    assert "<draft-comment" in text
    assert "<topic" in text
    assert "<body>" in text
    assert "best available guidance" not in lowered


@pytest.mark.anyio
async def test_build_local_fallback_response_prefers_strong_learned_qa_match(monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "_build_rag_context",
        lambda *_args, **_kwargs: "LEARNED PROMPT CORPUS:\n[1] Prompt: upload files\nAnswer:\nUse the upload workflow.",
    )
    monkeypatch.setattr(
        chat_service,
        "retrieve_learned_qa",
        lambda *_args, **_kwargs: [
            {
                "prompt": "How do I troubleshoot AEM Guides upload of existing DITA files?",
                "final_answer": (
                    "## Short answer\n"
                    "For AEM Guides upload troubleshooting, validate the target folder, file names, dependencies, and duplicate assets before blaming DITA markup.\n\n"
                    "## Checklist\n"
                    "- Confirm the upload target is the intended DAM folder.\n"
                    "- Check whether related DITA files, images, and maps were uploaded together.\n"
                    "- Resolve duplicate filenames or path conflicts before retrying.\n"
                    "- Reopen the uploaded map or topic and verify references resolve in AEM Guides."
                ),
                "score": 0.98,
                "topic": "aem_guides_upload",
                "source_type": "learned_qa_seed",
            }
        ],
    )

    text = await chat_service._build_local_fallback_response(
        "How do I troubleshoot AEM Guides upload of existing DITA files?",
        "kone",
        answer_mode="grounded_aem_answer",
    )

    lowered = text.lower()
    assert "validate the target folder" in lowered
    assert "duplicate filenames" in lowered
    assert "couldn't verify this directly" not in lowered
    assert "best available guidance" not in lowered
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
        assert "## Short answer" in text
        assert "topichead" in text.lower()
        assert "local indexed knowledge" not in text.lower()
        assert "not configured" in text.lower() or "disabled" in text.lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_prefers_high_confidence_learned_answer_before_tool_mode(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(
        chat_service,
        "_build_learned_qa_local_fallback_response",
        lambda *_args, **_kwargs: (
            "## Short answer\n"
            "If a topic publishes in HTML but fails in PDF, debug it as an output-pipeline parity issue first."
        ),
    )
    monkeypatch.setattr(
        chat_service,
        "_should_use_tool_mode",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("tool mode should not run")),
    )

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "How do I debug a topic that publishes in HTML but fails in PDF?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "output-pipeline parity" in text
        assert "processing-role" not in text.lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_offline_prefers_grounded_structured_answer_for_dita_questions(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    pack = build_evidence_pack(
        query="What did morerows attribute do in table?",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "dita_spec",
                    "label": "morerows",
                    "text": "Use @morerows on a CALS table entry to make that cell span additional rows downward.",
                    "url": "",
                    "metadata": {"title": "morerows"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_grounded_pack(**_kwargs):
        return (
            pack,
            {"strength": "grounded", "reason": pack.decision.reason},
            {
                "lookup_dita_attribute": {
                    "attribute_name": "morerows",
                    "attribute_syntax": "non-negative integer row-span count",
                    "text_content": "@morerows attribute makes a CALS table <entry> span additional rows downward.",
                    "supported_elements": ["entry"],
                    "usage_contexts": [
                        "Use @morerows on a CALS table <entry> to make that cell span additional rows downward.",
                        "It applies to CALS table <entry> cells, not <simpletable> cells.",
                    ],
                    "default_scenarios": [
                        "morerows=\"1\" means the cell spans the current row plus one more row."
                    ],
                    "correct_examples": [
                        "<row><entry morerows=\"1\">Spans 2 rows</entry><entry>Row 1, Col 2</entry></row><row><entry>Row 2, Col 2</entry></row>"
                    ],
                    "common_mistakes": ["Using @morerows without checking that the resulting table grid remains valid."],
                    "sources": [{"label": "morerows", "snippet": "Use @morerows on a CALS table <entry> to make that cell span additional rows downward."}],
                    "status": "success",
                    "status_tone": "success",
                }
            },
        )

    monkeypatch.setattr(chat_service, "_build_grounded_tool_evidence_pack", fake_grounded_pack)
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "DITA SPEC REFERENCE:\n[1] morerows\nrow span")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "What did morerows attribute do in table?", tenant_id="kone"):
            events.append(event)

        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "## Short answer" in text
        assert "not <simpletable>" in text
        assert 'morerows="1"' in text
        assert "local indexed knowledge" not in text.lower()
        assert "not configured" in text.lower() or "disabled" in text.lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_offline_prefers_args_draft_guidance_for_dita_ot_pdf_question(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    pack = build_evidence_pack(
        query="What DITA-OT argument enables draft-comment in PDF?",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "aem_guides",
                    "label": "DITA-OT base parameters: args.draft",
                    "text": "args.draft specifies whether draft-comment and required-cleanup elements are included in output. Use --args.draft=yes for DITA-OT PDF/PDF2.",
                    "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                    "metadata": {"title": "DITA-OT base parameters: args.draft"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_grounded_pack(**_kwargs):
        return (
            pack,
            {"strength": "grounded", "reason": pack.decision.reason, "source_domain": "dita_ot"},
            {
                "lookup_aem_guides": {
                    "query": "What DITA-OT argument enables draft-comment in PDF?",
                    "summary": "args.draft specifies whether draft-comment and required-cleanup elements are included in output.",
                    "results": [
                        {
                            "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                            "title": "DITA-OT base parameters: args.draft",
                            "snippet": "args.draft specifies whether draft-comment and required-cleanup elements are included in output. Use --args.draft=yes for DITA-OT PDF/PDF2.",
                        }
                    ],
                    "count": 1,
                    "retrieval_mode": "lexical",
                    "semantic_required": False,
                    "allowed_host_suffixes": ["experienceleague.adobe.com", "dita-ot.org"],
                    "source_domain": "dita_ot",
                    "embedding": {"available": False},
                    "warnings": [],
                }
            },
        )

    monkeypatch.setattr(chat_service, "_build_grounded_tool_evidence_pack", fake_grounded_pack)
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "What DITA-OT argument enables draft-comment in PDF?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        lowered = text.lower()
        assert "args.draft" in lowered
        assert "--args.draft=yes" in lowered
        assert "<draft-comment>" in text
        assert "<task>" not in text
        assert "not configured" in lowered or "disabled" in lowered
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_offline_prefers_output_behavior_answer_for_glossentry_native_pdf_question(monkeypatch):
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)
    pack = build_evidence_pack(
        query="How does glossentry behave in Native PDF output?",
        tenant_id="kone",
        candidates=[
            type(
                "Candidate",
                (),
                {
                    "source": "dita_spec",
                    "label": "glossentry",
                    "text": "<glossentry> is a topic specialization for glossary definitions.",
                    "url": "",
                    "metadata": {"title": "glossentry"},
                    "score": 0.0,
                },
            )(),
            type(
                "Candidate",
                (),
                {
                    "source": "tenant_knowledge",
                    "label": "GUIDES-881",
                    "text": "glossStatus in Native PDF can differ from expected glossary navigation when the map or publish settings omit the glossary branch.",
                    "url": "",
                    "metadata": {"title": "GUIDES-881"},
                    "score": 0.0,
                },
            )(),
        ],
    )

    async def fake_grounded_pack(**_kwargs):
        return (
            pack,
            {"strength": "grounded", "reason": pack.decision.reason},
            {
                "lookup_dita_spec": {
                    "query_type": "element_definition",
                    "element_name": "glossentry",
                    "summary": "<glossentry> is a topic specialization for glossary definitions.",
                    "text_content": "<glossentry> is a topic specialization for glossary definitions.",
                    "correct_examples": [
                        "<glossentry id=\"gl_api\"><glossterm>API</glossterm><glossdef><p>Application programming interface.</p></glossdef></glossentry>"
                    ],
                },
                "generate_native_pdf_config": {
                    "short_answer": "Treat Native PDF behavior as a publishing-pipeline question: verify the output preset, template, and bookmark/TOC handling instead of assuming glossary markup alone controls the PDF result.",
                    "recommended_actions": [
                        "Confirm the glossary topic is included from the root map in the intended publish flow.",
                        "Verify the Native PDF preset and bookmark/TOC behavior for glossary branches.",
                    ],
                    "relevant_settings": [
                        "Native PDF output preset",
                        "Bookmark and TOC generation",
                    ],
                    "common_mistakes": [
                        "Changing template styling before confirming the glossary topic is actually in the output."
                    ],
                    "evidence": [{"title": "Native PDF guidance", "url": "https://example.invalid/native-pdf", "snippet": "Verify preset and bookmark handling."}],
                },
                "search_tenant_knowledge": {
                    "results": [
                        {
                            "label": "GUIDES-881",
                            "doc_type": "jira_qa",
                            "content": "glossStatus in Native PDF can differ from expected glossary navigation when the map or publish settings omit the glossary branch.",
                        }
                    ]
                },
            },
        )

    monkeypatch.setattr(chat_service, "_build_grounded_tool_evidence_pack", fake_grounded_pack)
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "How does glossentry behave in Native PDF output?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        lowered = text.lower()
        assert "## short answer" in lowered
        assert "## output behavior" in lowered
        assert "glossentry" in lowered
        assert "native pdf" in lowered
        assert "bookmark" in lowered or "toc" in lowered
        assert "indexed workspace/jira evidence" in lowered
        assert "not configured" in lowered or "disabled" in lowered
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
        assert "## Short answer" in text
        assert "topichead" in text.lower()
        assert "local indexed knowledge" not in text.lower()
    finally:
        chat_service.delete_session(session_id)
