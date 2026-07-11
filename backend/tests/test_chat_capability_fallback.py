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
@pytest.mark.parametrize(
    ("prompt", "expected_terms"),
    [
        (
            "What does the DITA-OT copy-to preprocess step do?",
            ["copy-to", "preprocess", "@copy-to", "effective resource"],
        ),
        (
            "How does DITA-OT rewrite links after copy-to processing?",
            ["copy-to", "effective resource", "links", "clean.temp", ".job.xml"],
        ),
        (
            "Why can a conkeyref resolve differently after branch filtering?",
            ["conkeyref", "branch filtering", "effective map", "key space", "clean.temp"],
        ),
        (
            "What does conrefpush do in DITA-OT preprocessing?",
            ["conrefpush", "pushbefore", "pushafter", "pushreplace"],
        ),
        (
            "Which DITA-OT module resolves normal conref references?",
            ["conref", "@conref", "xslt", "effective processed content"],
        ),
        (
            "Which DITA-OT preprocess step filters content with DITAVAL and print rules?",
            ["profile", "ditaval", "@print", "preprocessing"],
        ),
        (
            "What are DITA command arguments like --input, --format, and --output used for?",
            ["--input", "--format", "--output", "--filter"],
        ),
    ],
)
async def test_build_local_fallback_response_formats_dita_ot_runtime_modules(prompt, expected_terms, monkeypatch):
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "DITA-OT runtime module docs")

    text = await chat_service._build_local_fallback_response(
        prompt,
        "kone",
        answer_mode="grounded_dita_answer",
    )

    lowered = text.lower()
    for term in expected_terms:
        assert term.lower() in lowered
    assert "## example" in lowered
    assert "## expected result" in lowered
    assert len(text) > 900


@pytest.mark.parametrize(
    ("prompt", "expected_terms"),
    [
        (
            "My copied topic is there but the reused note inside it vanished in PDF. How should I debug this like a DITA-OT expert?",
            ["copy-to", "conref", "profile", "ditaval", "expected result"],
        ),
        (
            "I need a full example where one topic becomes two outputs and one version filters internal text.",
            ["copy-to", "two effective topic resources", "filter", "expected result"],
        ),
        (
            "Can you explain why the XML I authored is not the same as the XML DITA-OT transforms?",
            ["source xml", "effective processed content", "copy-to", "conref"],
        ),
        (
            "A pushed warning should appear before a step but does not. Show how it should work.",
            ["conrefpush", "pushbefore", "target element", "expected result"],
        ),
        (
            "My conref target exists but the final PDF is blank at that location. What are deterministic checks?",
            ["conref", "effective processed content", "target", "debugging guidance"],
        ),
        (
            "Why does resource-only reusable content still resolve but not appear in TOC?",
            ["resource-only", "reuse source", "toc", "conref"],
        ),
        (
            "I passed --filter but nothing changed. Give me exact checks and expected behavior.",
            ["--filter", "ditaval", "profile", "expected result"],
        ),
        (
            "Give me a complete troubleshooting answer for DITA-OT runtime options and filters.",
            ["dita", "--input", "--format", "--filter", "expected result"],
        ),
    ],
)
def test_dita_ot_humanized_prompt_regression_answers_stay_senior(prompt, expected_terms):
    text = chat_service._build_dita_ot_preprocess_runtime_fallback_response(prompt)

    assert text, f"Prompt did not route to the DITA-OT senior fallback: {prompt}"
    lowered = text.lower()
    for term in expected_terms:
        assert term.lower() in lowered


@pytest.mark.parametrize(
    "prompt",
    [
        "Why can a conkeyref resolve differently after branch filtering?",
        "How does DITA-OT rewrite links after copy-to processing?",
        "Why does a keyref work in one map but not another?",
        "How do I debug a topic that publishes in HTML but fails in PDF?",
    ],
)
def test_behavior_questions_do_not_route_to_basic_attribute_lookup(prompt):
    requests = chat_service._grounded_tool_requests("grounded_dita_answer", prompt)

    assert ("lookup_dita_attribute", {"attribute_name": "conkeyref"}) not in requests
    assert not any(name == "lookup_dita_attribute" for name, _payload in requests)


def test_html_success_pdf_failure_gets_senior_troubleshooting_answer():
    text = chat_service._build_dita_ot_preprocess_runtime_fallback_response(
        "How do I debug a topic that publishes in HTML but fails in PDF?"
    )

    lowered = text.lower()
    assert "transform-specific failure" in lowered
    assert "clean.temp=no" in lowered
    assert "xsl-fo" in lowered
    assert "expected result" in lowered
    assert "<topic> is the base information unit" not in lowered


@pytest.mark.parametrize(
    ("prompt", "bad_answer", "expected_terms"),
    [
        (
            "How do I debug a topic that publishes in HTML but fails in PDF?",
            "Short answer\n<topic> is the base information unit in DITA.\n\nQuick reference\nField Details\nCommon children <title>, <body>",
            ["transform-specific failure", "clean.temp=no", "xsl-fo"],
        ),
        (
            "Why can a conkeyref resolve differently after branch filtering?",
            "Short answer\n@conkeyref enables indirect content references by combining key resolution with conref.\n\nQuick reference\nField Details",
            ["effective map context", "branch filtering", "key space"],
        ),
        (
            "How does DITA-OT rewrite links after copy-to processing?",
            "Short answer\n@copy-to is a DITA attribute used on topicref.\n\nQuick reference\nField Details",
            ["effective resource uri", "temporary", "copy-to"],
        ),
    ],
)
def test_behavior_answer_quality_gate_replaces_basic_definition_answers(prompt, bad_answer, expected_terms):
    repaired = chat_service._repair_mismatched_behavior_answer(prompt, bad_answer)
    lowered = repaired.lower()

    assert repaired != bad_answer
    assert "quick reference\nfield details" not in lowered
    for term in expected_terms:
        assert term.lower() in lowered


@pytest.mark.anyio
async def test_local_fallback_prefers_learned_qa_over_dita_ot_toc_false_positive(monkeypatch):
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "")

    prompt = (
        "What is the difference between topicref, topichead, and topicgroup? "
        "Show a realistic ditamap and explain TOC output."
    )
    text = await chat_service._build_local_fallback_response(
        prompt,
        "kone",
        answer_mode="grounded_dita_answer",
    )

    lowered = text.lower()
    assert "topicref" in lowered
    assert "topichead" in lowered
    assert "topicgroup" in lowered
    assert "conref is the dita-ot preprocess step" not in lowered


@pytest.mark.anyio
@pytest.mark.parametrize(
    "prompt",
    [
        "How do I exclude draft-only content at publish time?",
        "Quick question for our docs team: How do I exclude draft-only content at publish time?",
        "We hit this in a customer map today. What is the difference between topicref, topichead, and topicgroup? Show a realistic ditamap and explain TOC output.",
    ],
)
async def test_local_fallback_uses_learned_qa_for_humanized_seed_prompts(prompt, monkeypatch):
    monkeypatch.setattr(chat_service, "_build_rag_context", lambda *_args, **_kwargs: "")

    text = await chat_service._build_local_fallback_response(
        prompt,
        "kone",
        answer_mode="grounded_dita_answer",
    )

    lowered = text.lower()
    if "draft-only" in prompt.lower() or "exclude draft" in prompt.lower():
        assert "draft-comment" in lowered
        assert "required-cleanup" in lowered
        assert "## quick reference" not in lowered
    else:
        assert "topichead" in lowered
        assert "topicgroup" in lowered
        assert "conref is the dita-ot preprocess step" not in lowered


def test_should_try_dita_ot_runtime_fallback_blocks_pure_map_authoring_questions():
    assert not chat_service._should_try_dita_ot_runtime_fallback(
        "What is the difference between topicref, topichead, and topicgroup?"
    )
    assert chat_service._should_try_dita_ot_runtime_fallback(
        "Which DITA-OT preprocess step filters content with DITAVAL and print rules?"
    )


@pytest.mark.anyio
async def test_build_local_fallback_response_prefers_grounded_publish_filtering_answer(monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "try_build_learned_qa_fallback_answer",
        lambda *_args, **_kwargs: "",
    )
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
    assert "<draft-comment>" in text
    assert "<topic id=\"publish-filtering-example\">" in text
    assert "<body>" in text
    assert "best available guidance" not in lowered


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
