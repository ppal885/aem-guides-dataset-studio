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


@pytest.mark.anyio
async def test_chat_turn_grounded_dita_question_prefers_tool_evidence(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "summary": "Retrieved DITA specification guidance for `task`.",
                "warnings": [],
                "sources": [
                    {
                        "label": "task",
                        "snippet": "Task topics use taskbody with steps and step/cmd for procedural actions.",
                    }
                ],
                "spec_chunks": [
                    {
                        "element_name": "task",
                        "text_content": "Task topics use taskbody with steps and step/cmd for procedural actions.",
                    }
                ],
                "graph_knowledge": "task -> taskbody -> steps -> step -> cmd",
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when tool-backed grounded evidence is available")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "What is a DITA task topic and where do steps go?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "taskbody" in text.lower()
        assert "steps" in text.lower()
        assert "## Sources" in text
        assert "don't have enough verified information" not in text.lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_dita_attribute_question_uses_attribute_aware_spec_fallback(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA attribute questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_attribute":
            return {
                "error": "Attribute lookup temporarily unavailable",
            }
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "attribute_name": "format",
                "summary": "Retrieved DITA attribute guidance for `format`.",
                "warnings": [],
                "sources": [
                    {
                        "label": "format",
                        "url": "https://www.oxygenxml.com/dita/1.3/specs/langRef/attributes/theformatattribute.html",
                        "snippet": "The @format attribute identifies the format of the resource that is referenced.",
                    }
                ],
                "all_valid_values": ["dita", "ditamap", "html", "pdf", "txt"],
                "supported_elements": ["topicref", "xref", "link", "keydef", "mapref", "navref"],
                "combination_attributes": ["scope", "type"],
                "default_scenarios": ["topicref with omitted @format on data.xml defaults to dita"],
                "text_content": "The @format attribute identifies the format of the resource that is referenced.",
                "source_url": "https://www.oxygenxml.com/dita/1.3/specs/langRef/attributes/theformatattribute.html",
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when attribute-aware tool evidence is available")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Please provide information about format attribute.",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "@format attribute identifies the format" in text
        assert "## Valid values" in text
        assert "## Sources" in text
        assert "oxygenxml.com" in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["status"] in {"grounded", "partial"}
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_processing_role_question_prefers_attribute_tool(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA attribute questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_attribute":
            assert params.get("attribute_name") == "processing-role"
            return {
                "attribute_name": "processing-role",
                "summary": "Retrieved DITA attribute guidance for `processing-role`.",
                "warnings": [],
                "sources": [
                    {
                        "label": "processing-role",
                        "snippet": "The @processing-role attribute controls whether a referenced topic contributes to navigation output.",
                    }
                ],
                "all_valid_values": ["normal", "resource-only"],
                "supported_elements": ["topicref", "mapref", "keydef"],
                "combination_attributes": ["format", "scope", "chunk"],
                "text_content": "The @processing-role attribute controls whether a referenced topic contributes to navigation output.",
                "source_url": "",
                "status": "success",
                "status_tone": "success",
            }
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "summary": "Retrieved DITA specification guidance for `processing-role`.",
                "warnings": [],
                "sources": [],
                "spec_chunks": [],
                "graph_knowledge": "",
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when attribute tool evidence is available")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "What do you mean by processing-role in dita?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "@processing-role attribute controls whether a referenced topic contributes to navigation output" in text
        assert "## Valid values" in text
        assert "normal" in text.lower()
        assert "resource-only" in text.lower()
        assert "## Where it applies" in text
        assert "## Sources" in text
        assert "The term `you`" not in text
        assert "The term `mean`" not in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_map_construct"
        assert grounding_event["grounding"]["source_policy"] == "dita_spec_first"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_keyscope_question_prefers_attribute_tool_without_tenant_knowledge(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA attribute questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_attribute":
            assert params.get("attribute_name") == "keyscope"
            return {
                "attribute_name": "keyscope",
                "summary": "Retrieved DITA attribute guidance for `keyscope`.",
                "warnings": [],
                "sources": [
                    {
                        "label": "keyscope",
                        "snippet": "The @keyscope attribute creates a named scope for key definitions.",
                    }
                ],
                "all_valid_values": [],
                "supported_elements": ["map", "topicref", "mapref", "keydef"],
                "combination_attributes": ["keys", "scope", "format"],
                "default_scenarios": ["The root map defines an implicit unnamed scope."],
                "text_content": (
                    "The @keyscope attribute creates a named scope for key definitions.\n\n"
                    "Syntax: One or more space-separated scope names (same naming rules as keys)."
                ),
                "source_url": "",
                "status": "success",
                "status_tone": "success",
            }
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "attribute_name": "keyscope",
                "summary": "Retrieved DITA attribute guidance for `keyscope`.",
                "warnings": [],
                "sources": [],
                "all_valid_values": [],
                "supported_elements": ["map", "topicref", "mapref", "keydef"],
                "combination_attributes": ["keys", "scope", "format"],
                "default_scenarios": ["The root map defines an implicit unnamed scope."],
                "text_content": (
                    "The @keyscope attribute creates a named scope for key definitions.\n\n"
                    "Syntax: One or more space-separated scope names (same naming rules as keys)."
                ),
                "source_url": "",
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when attribute tool evidence is available")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "What is a keyscope in dita?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "@keyscope attribute creates a named scope for key definitions" in text
        assert "key definitions" in text.lower()
        assert "## Syntax" in text
        assert "space-separated scope names" in text.lower()
        assert "## Where it applies" in text
        assert "topicref" in text.lower()
        assert "## Default behavior" in text
        assert "valid values:" not in text.lower()
        assert "too thin or weak" not in text.lower()
        assert "## Sources" in text
        assert "tenant knowledge matches" not in text.lower()
        assert "copyfile syntaxdiagram example" not in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["status"] in {"grounded", "partial"}
        assert "too thin or weak" not in str(grounding_event["grounding"].get("reason") or "").lower()
        assert grounding_event["grounding"]["answer_kind"] == "dita_map_construct"
        assert grounding_event["grounding"]["source_policy"] == "dita_spec_first"
        assert grounding_event["grounding"]["example_verified"] is False
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_scalefit_question_uses_real_attribute_catalog(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA attribute questions")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when structured attribute evidence is available")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "What is a scalefit attribute?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "@scalefit attribute specifies whether an image is scaled up or down to fit within available space" in text
        assert "## Syntax" in text
        assert "-dita-use-conref-target" in text
        assert "## Valid values" in text
        assert "`yes`" in text
        assert "`no`" in text
        assert "## Supported elements" in text
        assert "`image`" in text
        assert "## Companion attributes" in text
        assert "`height`" in text
        assert "## Sources" in text
        assert "topicref" not in text.lower()
        assert "base information unit in dita" not in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_attribute"
        assert grounding_event["grounding"]["source_policy"] == "dita_spec_first"
        assert grounding_event["grounding"]["thin_evidence"] is False
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_topicref_question_renders_map_construct_sections(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA map construct questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "element",
                "element_name": "topicref",
                "summary": "<topicref> is the core building block of a DITA map.",
                "parent_elements": ["map", "topicgroup", "topichead"],
                "allowed_children": ["topicmeta", "topicref", "ditavalref", "topicgroup"],
                "supported_attributes": ["href", "navtitle", "type", "scope", "format", "chunk", "collection-type"],
                "usage_contexts": [
                    "Use <topicref> to include a topic in map navigation and processing.",
                    "Use @navtitle when the map should override the referenced topic title.",
                ],
                "graph_knowledge": "topicrefs define navigation order and processing context within map branches.",
                "common_mistakes": ["Assuming <topicref> itself contains topic body content."],
                "warnings": [],
                "sources": [{"label": "topicref", "snippet": "<topicref> is the core building block of a DITA map."}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "What is topicref in dita?", tenant_id="kone"):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "<topicref> is the core building block of a dita map." in text.lower()
        assert "## Where it applies" in text
        assert "`map`" in text
        assert "## What it can contain" in text
        assert "`topicmeta`" in text
        assert "## Common attributes" in text
        assert "`href`" in text
        assert "## Resolution behavior" in text
        assert "navigation order" in text.lower()
        assert "element 'topicref':" not in text.lower()
        assert "## Common mistakes" in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_map_construct"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_native_pdf_question_prefers_tool_evidence(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for Native PDF guidance questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "generate_native_pdf_config":
            return {
                "query": params.get("query"),
                "short_answer": "Use the Native PDF page layout and stylesheet together so the watermark stays at the page level.",
                "summary": "Use the Native PDF page layout and stylesheet together so the watermark stays at the page level.",
                "recommended_actions": [
                    "Start from the page layout used by the body pages.",
                    "Apply the watermark as page-level styling instead of embedding it inside the topic content.",
                ],
                "relevant_settings": ["Page layout", "Watermark background asset"],
                "warnings": [],
                "sources": [
                    {
                        "label": "Native PDF | PDF output generation | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/docs/native-pdf-output",
                        "snippet": "Use the Native PDF template and page layout to control repeating page decorations.",
                    }
                ],
                "evidence": [
                    {
                        "title": "Native PDF | PDF output generation | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/docs/native-pdf-output",
                        "snippet": "Use the Native PDF template and page layout to control repeating page decorations.",
                    }
                ],
                "status": "success",
                "status_tone": "success",
            }
        if name == "lookup_output_preset":
            return {
                "query": params.get("query"),
                "summary": "Found output preset guidance for Native PDF templates.",
                "warnings": [],
                "sources": [
                    {
                        "label": "Output preset guidance",
                        "snippet": "Output presets select the Native PDF template used during publishing.",
                    }
                ],
                "doc_results": [],
                "seed_results": [
                    {
                        "element_name": "output-presets",
                        "text_content": "Output presets select the Native PDF template used during publishing.",
                    }
                ],
                "status": "success",
                "status_tone": "success",
            }
        if name == "search_tenant_knowledge":
            return {
                "query": params.get("query"),
                "summary": "No tenant knowledge matches were found for the request.",
                "warnings": [],
                "sources": [],
                "results": [],
                "count": 0,
                "status": "warning",
                "status_tone": "warning",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_generate_text(*_args, **_kwargs):
        raise AssertionError("LLM generation should not run when Native PDF guidance is already structured")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fail_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "How do I configure a watermark in Native PDF?",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "watermark" in text.lower()
        assert "page layout" in text.lower()
        assert "## Recommended actions" in text
        assert "## Relevant settings" in text
        assert "## Sources" in text
        assert "don't have enough verified information" not in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "native_pdf_guidance"
        assert grounding_event["grounding"]["source_policy"] == "native_pdf_first"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_ditavalref_question_renders_content_model_sections(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA structure questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "content_model",
                "element_name": "ditavalref",
                "content_model_summary": "Inside <ditavalref>, DITA allows ditavalmeta.",
                "allowed_children": ["ditavalmeta"],
                "parent_elements": ["map", "topicref"],
                "supported_attributes": ["href", "format"],
                "common_mistakes": ["Using <ditavalref> as if it were a topic-body element."],
                "warnings": [],
                "sources": [{"label": "ditavalref", "snippet": "Inside <ditavalref>, DITA allows ditavalmeta."}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(chat_service, "_determine_answer_mode", lambda *_args, **_kwargs: "grounded_dita_answer")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "What can go inside ditavalref?", tenant_id="kone"):
            events.append(event)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Allowed children" in text
        assert "ditavalmeta" in text.lower()
        assert "## Placement notes" in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_content_model"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_choicetable_question_renders_placement_sections(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA placement questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "placement",
                "element_name": "choicetable",
                "placement_summary": "<choicetable> can appear inside step, substep, or stepsection content when task choices are needed.",
                "parent_elements": ["step", "substep", "stepsection"],
                "supported_attributes": ["relcolwidth"],
                "common_mistakes": ["Using <choicetable> outside task-oriented procedural context."],
                "warnings": [],
                "sources": [{"label": "choicetable", "snippet": "<choicetable> can appear inside step."}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(chat_service, "_determine_answer_mode", lambda *_args, **_kwargs: "grounded_dita_answer")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "Where can choicetable appear?", tenant_id="kone"):
            events.append(event)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Valid parents" in text
        assert "stepsection" in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_placement"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_grounded_conref_vs_conkeyref_renders_deterministic_comparison(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA comparison questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_dita_attribute":
            return {"error": "Use the comparison path for this request."}
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "attribute_comparison",
                "comparison_type": "attribute",
                "summary": "Compared DITA attributes `conref` and `conkeyref`.",
                "comparisons": [
                    {
                        "attribute_name": "conref",
                        "text_content": "@conref reuses content by directly pointing to a resolved target.",
                        "usage_contexts": ["Use conref when the target address is known directly."],
                        "supported_elements": ["p", "note", "step"],
                    },
                    {
                        "attribute_name": "conkeyref",
                        "text_content": "@conkeyref reuses content through key-based indirection.",
                        "usage_contexts": ["Use conkeyref when the target should be resolved through keys."],
                        "supported_elements": ["p", "note", "step"],
                    },
                ],
                "warnings": [],
                "sources": [{"label": "conref vs conkeyref", "snippet": "Compared DITA attributes `conref` and `conkeyref`."}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(chat_service, "_determine_answer_mode", lambda *_args, **_kwargs: "grounded_dita_answer")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "conref vs conkeyref", tenant_id="kone"):
            events.append(event)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Comparison" in text
        assert "`conref`" in text
        assert "`conkeyref`" in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_attribute_comparison"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_dita_comparison_with_xml_examples_does_not_generate_dita(monkeypatch):
    async def fail_agent_plan(*_args, **_kwargs):
        raise AssertionError("Question-led DITA comparison must not create a generate_dita preview plan")
        if False:
            yield {}

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "generate_dita":
            raise AssertionError("generate_dita must not run for explanation/comparison questions")
        if name == "lookup_dita_attribute":
            return {"error": "comparison path should use lookup_dita_spec"}
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "attribute_comparison",
                "comparison_type": "attribute",
                "summary": "Compared DITA attributes `conref`, `conkeyref`, and `keyref`.",
                "comparisons": [
                    {
                        "attribute_name": "conref",
                        "text_content": "@conref reuses content by directly addressing a target element.",
                        "attribute_syntax": 'conref="file.dita#topicId/elementId"',
                        "usage_contexts": ["Use when the reuse target file and element ID are known."],
                        "supported_elements": ["p", "note", "step"],
                        "correct_examples": ['<p conref="shared/warnings.dita#warnings/backup-warning"/>'],
                    },
                    {
                        "attribute_name": "conkeyref",
                        "text_content": "@conkeyref reuses content through a key-defined target.",
                        "attribute_syntax": 'conkeyref="keyname/elementid"',
                        "usage_contexts": ["Use when a map key should resolve the reusable source."],
                        "supported_elements": ["p", "note", "step"],
                        "correct_examples": ['<note conkeyref="shared-warnings/backup-warning"/>'],
                    },
                    {
                        "attribute_name": "keyref",
                        "text_content": "@keyref resolves links, variable text, or resources through map-defined keys.",
                        "attribute_syntax": 'keyref="keyname"',
                        "usage_contexts": ["Use when the link target or variable text should be map controlled."],
                        "supported_elements": ["xref", "keyword", "image"],
                        "correct_examples": ['<xref keyref="support-page">Support</xref>'],
                    },
                ],
                "warnings": [],
                "sources": [{"label": "DITA key and reuse attributes", "snippet": "conref conkeyref keyref"}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_stream_agent_plan_reply", fail_agent_plan)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        prompt = "What is the difference between conref, conkeyref, and keyref? Show XML examples."
        async for event in chat_service.chat_turn(session_id, prompt, tenant_id="kone"):
            events.append(event)
        assert not any(event.get("type") == "tool_start" and event.get("name") == "generate_dita" for event in events)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Comparison" in text
        assert "## Verified XML examples" in text
        assert 'conref="file.dita#topicId/elementId"' in text
        assert '<xref keyref="support-page">Support</xref>' in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_attribute_comparison"
        assert grounding_event["grounding"]["example_verified"] is True
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_linklist_title_toc_question_uses_dita_semantics_not_native_pdf(monkeypatch):
    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "generate_native_pdf_config":
            raise AssertionError("linklist/title TOC question must not route to Native PDF styling")
        if name == "lookup_dita_attribute":
            raise AssertionError("TOC here means table of contents, not the @toc attribute")
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "placement",
                "element_name": "linklist",
                "summary": "Retrieved DITA specification guidance for `linklist`.",
                "placement_summary": "<linklist> appears inside <related-links> to group related links.",
                "allowed_children": ["title", "desc", "link", "linkinfo"],
                "parent_elements": ["related-links"],
                "supported_attributes": ["type", "collection-type", "outputclass"],
                "usage_contexts": [
                    "Use <linklist> inside <related-links> when several related targets form a named group."
                ],
                "common_mistakes": [
                    "Using <linklist> as a normal body list instead of a related-links group."
                ],
                "sources": [
                    {
                        "label": "linklist",
                        "url": "https://docs.oasis-open.org/dita/v1.0/langspec/linklist.html",
                        "snippet": "The linklist element groups related link elements under a common heading.",
                    },
                    {
                        "label": "related-links",
                        "url": "https://dita-lang.org/1.3/dita/langref/base/related-links",
                        "snippet": "Related links appear after the topic body.",
                    },
                ],
                "spec_chunks": [
                    {
                        "element_name": "linklist",
                        "text_content": "The <linklist> element groups related <link> elements under a common heading.",
                    }
                ],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        prompt = "link list title should come in pdf output toc??"
        async for event in chat_service.chat_turn(session_id, prompt, tenant_id="kone"):
            events.append(event)

        assert not any(event.get("type") == "tool_start" and event.get("name") == "generate_native_pdf_config" for event in events)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "No. By default" in text
        assert "<linklist>/<title>" in text
        assert "topic-local related-links" in text
        assert "map/topicref" in text
        assert "not a normal PDF TOC entry" in text
        assert "## Recommended actions" not in text
        assert "TOC title and entry styles" not in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_placement"
        assert grounding_event["grounding"]["source_policy"] == "dita_spec_first"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_foreign_output_question_uses_dita_output_behavior_not_native_pdf(monkeypatch):
    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name in {"generate_native_pdf_config", "lookup_output_preset"}:
            raise AssertionError("foreign output behavior question must route to DITA construct semantics first")
        if name == "lookup_dita_attribute":
            return {"error": "No attribute requested"}
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "query_type": "element",
                "element_name": "foreign",
                "summary": "Retrieved DITA specification guidance for `foreign`.",
                "text_content": "<foreign> contains non-DITA content such as SVG, MathML, or custom XML.",
                "allowed_children": ["fallback"],
                "parent_elements": ["body", "section", "example"],
                "supported_attributes": ["outputclass"],
                "usage_contexts": [
                    "Use <foreign> to embed non-DITA vocabulary inside topic content.",
                    "Use fallback when output processors cannot render the foreign vocabulary.",
                ],
                "sources": [
                    {
                        "label": "foreign",
                        "url": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/foreign.html",
                        "snippet": "The foreign element contains non-DITA content.",
                    }
                ],
                "spec_chunks": [
                    {
                        "element_name": "foreign",
                        "text_content": "<foreign> contains non-DITA content. It can contain fallback content.",
                    }
                ],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA output questions")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        prompt = "how foreign element is used in PDF output and Web outputs??"
        async for event in chat_service.chat_turn(session_id, prompt, tenant_id="kone"):
            events.append(event)

        assert not any(event.get("type") == "tool_start" and event.get("name") == "generate_native_pdf_config" for event in events)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "<foreign> element carries non-DITA vocabulary" in text
        assert "## Output behavior" in text
        assert "Web/HTML output can preserve supported vocabularies" in text
        assert "PDF output depends on the PDF transform and formatter" in text
        assert "## PDF vs Web guidance" in text
        assert "## Recommended actions" not in text
        assert "Native PDF template" not in text
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "dita_output_behavior"
        assert grounding_event["grounding"]["source_policy"] == "dita_spec_first"
    finally:
        chat_service.delete_session(session_id)


def test_dita_element_answer_uses_structured_sections_not_generic_verified_details():
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_dita_answer",
        question="What is the itemgroup element in DITA?",
        tool_results_by_name={
            "lookup_dita_attribute": {"error": "No attribute requested"},
            "lookup_dita_spec": {
                "query_type": "element",
                "element_name": "itemgroup",
                "summary": "Retrieved DITA specification guidance for `itemgroup`.",
                "text_content": "<itemgroup> contains a group of items within list-like structures.",
                "allowed_children": ["ph", "keyword", "term"],
                "parent_elements": ["li", "sl", "dlentry"],
                "supported_attributes": ["outputclass"],
                "usage_contexts": ["Use <itemgroup> when list item content needs grouped inline or phrase-level material."],
                "common_mistakes": ["Using <itemgroup> as a standalone topic section."],
                "sources": [{"label": "itemgroup", "snippet": "The itemgroup element groups item content."}],
                "status": "success",
            },
        },
    )

    assert facts is not None
    assert facts.answer_kind == "dita_element"
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "## Short answer" in rendered
    assert "## Where it appears" in rendered
    assert "Inside `li`" in rendered
    assert "## What it can contain" in rendered
    assert "`ph`" in rendered
    assert "## Common attributes" in rendered
    assert "`outputclass`" in rendered
    assert "## Typical usage" in rendered
    assert "## Common mistakes" in rendered
    assert "## Verified details" not in rendered


def test_dita_element_comparison_renders_deterministic_comparison_sections():
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_dita_answer",
        question="What is the difference between data and data-about?",
        tool_results_by_name={
            "lookup_dita_attribute": {"error": "No attribute requested"},
            "lookup_dita_spec": {
                "query_type": "element_comparison",
                "summary": "Compared DITA elements `data` and `data-about`.",
                "comparisons": [
                    {
                        "element_name": "data",
                        "text_content": "<data> stores named metadata or machine-processable values in content.",
                        "parent_elements": ["prolog", "metadata"],
                        "supported_attributes": ["name", "value", "datatype"],
                        "usage_contexts": ["Use <data> for a metadata property or value."],
                    },
                    {
                        "element_name": "data-about",
                        "text_content": "<data-about> groups metadata about another subject or resource.",
                        "parent_elements": ["prolog", "metadata"],
                        "supported_attributes": ["href", "format", "scope"],
                        "usage_contexts": ["Use <data-about> when metadata describes an external subject."],
                    },
                ],
                "status": "success",
            },
        },
    )

    assert facts is not None
    assert facts.answer_kind == "dita_element_comparison"
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "## Short answer" in rendered
    assert "## Comparison" in rendered
    assert "`<data>`" in rendered
    assert "`<data-about>`" in rendered
    assert "valid parents" in rendered
    assert "common attributes" in rendered
    assert "typical usage" in rendered
    assert "## Verified details" not in rendered


@pytest.mark.anyio
async def test_chat_turn_mixed_explain_then_generate_shows_answer_and_preview(monkeypatch):
    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "generate_dita":
            raise AssertionError("Mixed prompt must not execute generate_dita before approval")
        if name == "lookup_dita_attribute":
            return {
                "attribute_name": "conref",
                "attribute_semantic_class": "reference_like",
                "attribute_syntax": 'conref="file.dita#topicId/elementId"',
                "text_content": "@conref reuses content by directly addressing a source element.",
                "supported_elements": ["p", "note", "step"],
                "usage_contexts": ["Use conref when the reusable target file and element ID are stable."],
                "correct_examples": ['<p conref="shared/warnings.dita#warnings/backup-warning"/>'],
                "sources": [{"label": "conref", "snippet": "@conref reuses content by direct reference."}],
                "status": "success",
                "status_tone": "success",
            }
        if name == "lookup_dita_spec":
            return {
                "query": params.get("query"),
                "attribute_name": "conref",
                "text_content": "@conref reuses content by directly addressing a source element.",
                "sources": [{"label": "conref", "snippet": "@conref reuses content by direct reference."}],
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        prompt = "Explain conref and then generate a conref example bundle."
        async for event in chat_service.chat_turn(session_id, prompt, tenant_id="kone"):
            events.append(event)

        assert any(event.get("type") == "grounding" for event in events)
        assert any(event.get("type") == "plan" for event in events)
        assert any(event.get("type") == "approval_required" for event in events)
        assert not any(event.get("type") == "tool_start" and event.get("name") == "generate_dita" for event in events)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "## Short answer" in text
        assert "@conref reuses content" in text
        assert "## Generation preview" in text
        assert "Generate DITA bundle" in text

        messages = chat_service.get_messages(session_id, limit=5)
        assistant = next(message for message in reversed(messages) if message.get("role") == "assistant")
        tool_results = assistant.get("tool_results") or {}
        assert tool_results["_mixed_intent"]["mixed_intent"] is True
        assert tool_results["_mixed_intent"]["answer_intent"] == "Explain conref"
        assert tool_results["_mixed_intent"]["generation_intent"] == "generate a conref example bundle"
        assert tool_results["_agent_plan"]["mode"] == "generate_dita_preview"
        assert tool_results["_approval_state"]["state"] == "required"
        assert tool_results["_grounding"]["answer_kind"] in {"dita_attribute", "dita_map_construct"}
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_keyscope_example_request_omits_unverified_xml_example(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for direct grounded DITA attribute questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name in {"lookup_dita_attribute", "lookup_dita_spec"}:
            return {
                "attribute_name": "keyscope",
                "summary": "Retrieved DITA attribute guidance for `keyscope`.",
                "warnings": [],
                "all_valid_values": [],
                "supported_elements": ["map", "topicref", "mapref", "keydef"],
                "combination_attributes": ["keys", "scope", "format"],
                "default_scenarios": ["The root map defines an implicit unnamed scope."],
                "correct_examples": ["Use @keyscope on a topicref branch to create a named key scope."],
                "text_content": (
                    "The @keyscope attribute creates a named scope for key definitions.\n\n"
                    "Syntax: One or more space-separated scope names (same naming rules as keys)."
                ),
                "source_url": "",
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(chat_service, "_determine_answer_mode", lambda *_args, **_kwargs: "grounded_dita_answer")
    monkeypatch.setattr(
        chat_service,
        "route_prompt",
        lambda *_args, **_kwargs: type("Decision", (), {"intent": "unknown", "legacy_answer_mode": "default", "candidate_contract": {}})(),
    )
    monkeypatch.setattr(
        chat_service,
        "decide_execution_policy",
        lambda *_args, **_kwargs: type("Policy", (), {"action": "answer_directly", "clarification_question": None})(),
    )

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, "What is keyscope in dita? Show an example.", tenant_id="kone"):
            events.append(event)
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "No verified snippet was available" in text
        assert "<topic id=" not in text.lower()
        grounding_event = next(event for event in events if event.get("type") == "grounding")
        assert grounding_event["grounding"]["example_verified"] is False
    finally:
        chat_service.delete_session(session_id)


def test_aem_translation_workflow_guidance_builds_verified_workflow_summary_and_actions():
    question = "How does the translation workflow work in AEM Guides?"
    aem = {
        "results": [
            {
                "title": "Best practices for content translation | Adobe Experience Manager",
                "snippet": (
                    "Content translation process must be started from DITA map console and not the Adobe Experience Manager Assets UI. "
                    "As translating content requires creation of a translation project, the user must have access to create project in Adobe Experience Manager."
                ),
            },
            {
                "title": "Best practices for content translation | Adobe Experience Manager",
                "snippet": (
                    "Configure translation service. In the Assets UI, select the source language folder. "
                    "Open the folder properties, and go to Cloud Services tab. In the Cloud Services tab, configure the translation service that you want to use."
                ),
            },
            {
                "title": "Best practices for content translation | Adobe Experience Manager",
                "snippet": (
                    "Start the translation job. In the Projects console, navigate to the project folder you created for localization. "
                    "Select the arrow on the Translation Job tile, and select Start from the list to start the translation workflow."
                ),
            },
            {
                "title": "Best practices for content translation | Adobe Experience Manager",
                "snippet": (
                    "After the translation completes, the status of the translation job changes to Ready to Review. "
                    "To complete the translation process, you need to accept the translated copy and asset metadata from the Translation Job tile in the Project console."
                ),
            },
        ]
    }

    summary = chat_service._select_aem_guidance_summary(question, aem, {})
    actions = chat_service._build_aem_guidance_actions(question, aem, {})

    assert summary.lower().startswith("in aem guides, the translation workflow is to")
    assert "configure the translation service" in summary.lower()
    assert "start the translation job" in summary.lower()
    assert "ready to review" in summary.lower()
    assert len(actions) >= 4
    assert actions[0].startswith("Configure the translation service")
    assert any("Translation Job" in action for action in actions)
    assert any("Ready to Review" in action for action in actions)


def test_aem_how_to_question_renders_verified_workflow_sections():
    question = "How do you create a topic or map in AEM Guides?"
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_aem_answer",
        question=question,
        tool_results_by_name={
            "lookup_aem_guides": {
                "results": [
                    {
                        "title": "Create topics",
                        "snippet": (
                            "In the Repository panel, select New and choose Topic to create a new topic."
                        ),
                    },
                    {
                        "title": "Create maps",
                        "snippet": (
                            "In the Map Console, select Create map and choose the template you want to use."
                        ),
                    },
                    {
                        "title": "Open in editor",
                        "snippet": (
                            "Open the created topic or map in the Web Editor to author and save your changes."
                        ),
                    },
                ]
            }
        },
    )

    assert facts is not None
    assert facts.guidance_kind == "how_to"
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "## Verified workflow" in rendered
    assert "Repository panel" in rendered
    assert "Create > DITA Map" in rendered


def test_aem_how_to_question_skips_xml_and_publishing_noise():
    question = "How do you create a topic or map in AEM Guides?"
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_aem_answer",
        question=question,
        tool_results_by_name={
            "lookup_aem_guides": {
                "results": [
                    {
                        "title": "DITA content reuse in AEM Guides",
                        "snippet": (
                            '<map id="ABC_manual"><topicref href="sample.dita"/></map> '
                            "Here the topic path changes during reuse."
                        ),
                    },
                    {
                        "title": "AEM Site",
                        "snippet": (
                            "Generate article-based output from the Map console for one or more topics."
                        ),
                    },
                    {
                        "title": "Create topics",
                        "snippet": (
                            "In the Repository panel, select New and choose Topic to create a new topic."
                        ),
                    },
                    {
                        "title": "Create a map",
                        "snippet": (
                            "Select Create > DITA Map, specify the title and template, and then select Create."
                        ),
                    },
                ]
            }
        },
    )

    assert facts is not None
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "Repository panel" in rendered
    assert "Create > DITA Map" in rendered
    assert "<topicref" not in rendered
    assert "Generate article-based output" not in rendered


def test_aem_create_topic_or_map_question_builds_canonical_authoring_workflow():
    question = "How do you create a topic or map in AEM Guides?"
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_aem_answer",
        question=question,
        tool_results_by_name={
            "lookup_aem_guides": {
                "_question": question,
                "results": [
                    {
                        "title": "Create topics | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                        "snippet": (
                            "Create topics from the Editor. In the Repository panel, select the New file icon and then select Topic from the dropdown menu. "
                            "The New topic dialog box is displayed."
                        ),
                    },
                    {
                        "title": "Create topics | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                        "snippet": (
                            "In the Assets UI, navigate to the location where you want to create the topic. "
                            "To create a new topic, select Create > DITA Topic. On the Blueprint page, select the type of DITA document you want to create and select Next."
                        ),
                    },
                    {
                        "title": "Create a map | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                        "snippet": (
                            "Select Create > DITA Map. On the Blueprint page, select the type of map templates you want to use and select Next."
                        ),
                    },
                    {
                        "title": "Create a map | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                        "snippet": (
                            "The New map dialog box is displayed. In the New map dialog box, provide the title and file name."
                        ),
                    },
                    {
                        "title": "Preview a topic | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-preview-topics",
                        "snippet": "Perform the following steps to create a branch, revert to a version, and maintain subsequent versions of a topic.",
                    },
                    {
                        "title": "Insert a content snippet from your data source | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/web-editor-content-snippet",
                        "snippet": "Create a topic using the topic generator from connected data sources.",
                    },
                ],
            }
        },
    )

    assert facts is not None
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "To create a map, select Create > DITA Map." in rendered
    assert "Repository panel New file icon and choose Topic" in rendered
    assert "Create > DITA Topic" in rendered
    assert "Choose the DITA topic type" in rendered
    assert "topic generator" not in rendered.lower()
    assert "create a branch" not in rendered.lower()
    assert "context menu" not in rendered.lower()


def test_aem_baseline_type_question_uses_baseline_docs_not_document_states():
    question = "What are types of baselines can a user create in AEM Guides?"
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_aem_answer",
        question=question,
        tool_results_by_name={
            "lookup_aem_guides": {
                "_question": question,
                "results": [
                    {
                        "title": "Configure document states | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/doc-state/customize-doc-state",
                        "snippet": (
                            "For example, the first state can be Draft and it can move to Review, Approved, Translated, and finally to Published."
                        ),
                    },
                    {
                        "title": "Create and manage baselines from the Map console | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline",
                        "snippet": (
                            "Baseline Type Options include Manual Update and Automatic Update. "
                            "Manual Update lets you create a static baseline using Date or Label. "
                            "Automatic Update creates a dynamic baseline and uses selected labels when the baseline is used."
                        ),
                    },
                    {
                        "title": "Create and manage new baseline (Beta) from the Map console | Adobe Experience Manager",
                        "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2",
                        "snippet": (
                            "For automatic update, label priority matters. Labels selected earlier take priority over later labels."
                        ),
                    },
                ],
            }
        },
    )

    assert facts is not None
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "Manual update static baselines" in rendered
    assert "Automatic update dynamic baselines" in rendered
    assert "Manual update baseline" in rendered
    assert "Automatic update baseline" in rendered
    assert "Label priority" in rendered
    assert "Draft" not in rendered
    assert "Approved" not in rendered
    assert "Translated" not in rendered


def test_aem_configuration_question_renders_relevant_settings_section():
    question = "How do I configure workspace settings in AEM Guides?"
    facts = chat_service._normalize_grounded_tool_facts(
        answer_mode="grounded_aem_answer",
        question=question,
        tool_results_by_name={
            "lookup_aem_guides": {
                "results": [
                    {
                        "title": "Workspace settings in Experience Manager Guides",
                        "snippet": (
                            "Open Workspace settings from the profile menu, update the General settings, and save the configuration."
                        ),
                    },
                    {
                        "title": "Workspace settings in Experience Manager Guides",
                        "snippet": (
                            "Use the Workspace settings page to manage General preferences and other editor-level settings."
                        ),
                    },
                ]
            }
        },
    )

    assert facts is not None
    assert facts.guidance_kind == "configuration"
    assert "Workspace settings" in facts.relevant_settings
    rendered = chat_service._render_normalized_grounded_fact_set(facts)
    assert "## Verified configuration steps" in rendered
    assert "## Relevant settings" in rendered
    assert "Workspace settings" in rendered


@pytest.mark.anyio
async def test_chat_turn_aem_grounding_metadata_includes_retrieval_diagnostics(monkeypatch):
    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for grounded AEM product answers")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_aem_guides":
            return {
                "query": params.get("query"),
                "summary": "Open Workspace settings from the profile menu.",
                "results": [
                    {
                        "title": "Workspace settings in Experience Manager Guides",
                        "snippet": "Open Workspace settings from the profile menu.",
                    }
                ],
                "retrieval_mode": "lexical",
                "semantic_required": False,
                "embedding": {
                    "available": False,
                    "configured_model": "all-MiniLM-L6-v2",
                    "configured_model_path": "",
                    "active_model_identifier": "all-MiniLM-L6-v2",
                    "load_mode": "fallback_none",
                    "error": "WinError 10013",
                },
                "warnings": ["Semantic retrieval was unavailable, so retrieval used lexical ranking only."],
                "status": "success",
                "status_tone": "warning",
            }
        if name == "lookup_output_preset":
            return {"results": []}
        if name == "search_tenant_knowledge":
            return {"results": []}
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", lambda *_args, **_kwargs: pytest.fail("LLM generation should not run"))
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)
    monkeypatch.setattr(chat_service, "_determine_answer_mode", lambda *_args, **_kwargs: "grounded_aem_answer")

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "How do I configure workspace settings in AEM Guides?",
            tenant_id="kone",
        ):
            events.append(event)

        grounding_event = next(event for event in events if event.get("type") == "grounding")
        retrieval = grounding_event["grounding"]["retrieval"]
        assert retrieval["mode"] == "lexical"
        assert retrieval["semantic_required"] is False
        assert retrieval["embedding"]["available"] is False
        assert "WinError 10013" in retrieval["embedding"]["error"]
        text = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "lexical ranking only" in text.lower()
    finally:
        chat_service.delete_session(session_id)
