import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import chat_multimodal_service, chat_service, chat_tools
from app.services.chat_service import _build_direct_tool_response
from app.services.chat_multimodal_service import generate_image, generate_xml_flowchart
from app.services.chat_tools import get_tool_catalog, parse_tool_intent_from_content


def test_get_tool_catalog_exposes_only_llm_invokable_tools():
    catalog = {item["name"]: item for item in get_tool_catalog()}

    assert set(catalog.keys()) == {"generate_dita", "generate_xml_flowchart"}
    assert catalog["generate_xml_flowchart"]["category"] == "Visualization"
    assert catalog["generate_xml_flowchart"]["primary_arg"] == "xml"

    assert catalog["generate_dita"]["approval_required"] is False
    assert catalog["generate_dita"]["review_first"] is True
    assert catalog["generate_dita"]["execution_mode"] == "preview_then_generate"


def test_parse_tool_intent_from_content_parses_slash_command_body():
    xml = (
        '<topic id="topic_a">'
        "<title>Sample topic</title>"
        "<shortdesc>Diagram this topic.</shortdesc>"
        '<body><section id="intro"><title>Overview</title><p>Text.</p></section></body>'
        "</topic>"
    )
    content = f"/generate_xml_flowchart\nxml_kind: topic\nrender_mode: both\n\n{xml}"

    intent = parse_tool_intent_from_content(content)

    assert intent is not None
    assert intent["name"] == "generate_xml_flowchart"
    assert intent["source"] == "slash"
    assert intent["args"]["xml_kind"] == "topic"
    assert intent["args"]["render_mode"] == "both"
    assert intent["args"]["xml"] == xml


@pytest.mark.anyio
async def test_generate_xml_flowchart_returns_mermaid_and_svg():
    xml = (
        '<map id="root-map">'
        "<title>Root map</title>"
        '<keydef keys="common-intro" href="../topics/common-intro.dita"/>'
        '<topicref keyref="common-intro"/>'
        '<mapref href="child-a.ditamap"/>'
        "</map>"
    )

    result = await generate_xml_flowchart(xml, xml_kind="map")

    assert result["diagram_kind"] == "map"
    assert result["title"] == "Root map"
    assert "flowchart TD" in result["mermaid"]
    assert "keydef" in result["mermaid"]
    assert result["preview_svg"].startswith("<svg")
    assert result["preview_svg_data_url"].startswith("data:image/svg+xml;base64,")
    assert result["display_mode"] == "complete_diagram"
    assert result["visible_node_count"] == result["total_node_count"]


@pytest.mark.anyio
async def test_generate_xml_flowchart_can_return_mermaid_only():
    xml = (
        '<topic id="topic_a">'
        "<title>Note</title>"
        "<shortdesc>Diagram this topic.</shortdesc>"
        '<body><section id="intro"><title>Overview</title><p>Text.</p></section></body>'
        "</topic>"
    )

    result = await generate_xml_flowchart(xml, xml_kind="topic", render_mode="mermaid")

    assert result["mermaid"].startswith("flowchart TD")
    assert result["preview_svg"] == ""
    assert result["preview_svg_data_url"] == ""


@pytest.mark.anyio
async def test_generate_xml_flowchart_simplifies_large_maps():
    topicrefs = "".join(
        f'<topicref href="topics/topic-{index}.dita" navtitle="Topic {index}"/>'
        for index in range(75)
    )
    xml = f'<map id="large-map"><title>Large map</title>{topicrefs}</map>'

    result = await generate_xml_flowchart(xml, xml_kind="map")

    assert result["diagram_kind"] == "map"
    assert result["display_mode"] == "structure_overview"
    assert result["is_simplified"] is True
    assert result["visible_node_count"] <= result["max_visible_nodes"]
    assert result["total_node_count"] > result["visible_node_count"]
    assert result["omitted_node_count"] > 0
    assert result["warnings"]
    assert "overview" in result["message"].lower()
    assert "not exhaustive" in " ".join(result["warnings"]).lower()


def test_direct_flowchart_response_mentions_missing_svg_preview_when_absent():
    text = _build_direct_tool_response(
        "generate_xml_flowchart",
        {
            "title": "Note",
            "mermaid": "flowchart TD\nA-->B",
            "preview_svg": "",
            "preview_svg_data_url": "",
        },
    )

    assert "did not include an SVG preview" in text


@pytest.mark.anyio
async def test_generate_image_returns_local_svg_artifact(monkeypatch):
    monkeypatch.setattr(chat_multimodal_service, "_OPENAI_API_KEY", "")

    result = await generate_image(
        "Create a clean enterprise illustration for DITA map review.",
        size="768x512",
        style="editorial",
        count=1,
    )

    assert result["provider"] == "local"
    assert result["artifacts"]
    artifact = result["artifacts"][0]
    assert artifact["mime_type"] == "image/svg+xml"
    assert artifact["data_url"].startswith("data:image/svg+xml;base64,")
    assert artifact["inline_svg"].startswith("<svg")
    assert artifact["width"] == 768
    assert artifact["height"] == 512


def test_chat_tools_endpoint_lists_llm_chat_tools():
    client = TestClient(app)

    response = client.get("/api/v1/chat/tools")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()["tools"]}
    assert names == {"generate_dita", "generate_xml_flowchart"}


@pytest.mark.anyio
async def test_chat_turn_with_tool_intent_runs_direct_xml_flowchart():
    session_id = chat_service.create_session()
    try:
        xml = (
            '<topic id="topic_a">'
            "<title>Sample topic</title>"
            "<shortdesc>Diagram this topic.</shortdesc>"
            '<body><section id="intro"><title>Overview</title><p>Text.</p></section></body>'
            "</topic>"
        )
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create a flowchart for this XML.",
            tenant_id="kone",
            tool_intent={
                "name": "generate_xml_flowchart",
                "args": {"xml": xml, "xml_kind": "topic", "render_mode": "both"},
                "source": "slash",
            },
        ):
            events.append(event)

        assert any(
            event["type"] == "tool" and event.get("name") == "generate_xml_flowchart"
            for event in events
        )
        assert events[-1]["type"] == "done"

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        assert assistant["tool_results"]["generate_xml_flowchart"]["diagram_kind"] == "topic"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_create_job_tool_intent_requires_approval():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Generate a compact key-resolution dataset.",
            tenant_id="kone",
            tool_intent={
                "name": "create_job",
                "args": {"recipe_type": "compact_parent_child_key_resolution"},
                "source": "slash",
            },
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert any(event["type"] == "approval_required" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        tool_results = assistant["tool_results"] or {}
        assert tool_results["_approval_state"]["state"] == "required"
        assert tool_results["_agent_plan"]["steps"][0]["tool_name"] == "create_job"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_execute_generate_dita_uses_shared_service_with_tenant_context(monkeypatch):
    captured: dict[str, object] = {}

    async def fake_run_generate_from_text(
        *,
        text: str,
        instructions: str | None,
        bundle_contract: dict[str, object] | None = None,
        run_id: str,
        request,
        user_id: str,
        tenant_id: str,
        skip_rag_check: bool = False,
        progress_run_id: str | None = None,
    ):
        captured.update(
            {
                "text": text,
                "instructions": instructions,
                "bundle_contract": bundle_contract,
                "run_id": run_id,
                "request": request,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "skip_rag_check": skip_rag_check,
                "progress_run_id": progress_run_id,
            }
        )
        return {
            "jira_id": "TEXT-123",
            "run_id": run_id,
            "bundle_summary": "Generated a DITA bundle with 1 map file and 10 topic files.",
            "artifact_counts": {"total_files": 11, "map_files": 1, "topic_files": 10},
            "representative_files": ["root-map.ditamap", "glossary-01.dita"],
        }

    monkeypatch.setattr(chat_tools, "run_generate_from_text", fake_run_generate_from_text)
    monkeypatch.setattr(chat_tools, "update_generate_progress", lambda *args, **kwargs: None)

    result = await chat_tools.execute_generate_dita(
        "Create a map and 10 glossary entries about AEM Guides terminology.",
        run_id="run-preview",
        user_id="user-123",
        tenant_id="tenant-abc",
    )

    assert captured["user_id"] == "user-123"
    assert captured["tenant_id"] == "tenant-abc"
    assert captured["skip_rag_check"] is True
    assert captured["bundle_contract"] is None
    assert result["bundle_summary"].startswith("Generated a DITA bundle")
    assert result["artifact_counts"]["map_files"] == 1


@pytest.mark.anyio
async def test_chat_turn_generate_dita_tool_intent_proposes_review_first_plan(monkeypatch):
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create a task topic from this Jira paste.",
            tenant_id="kone",
            tool_intent={
                "name": "generate_dita",
                "args": {"text": "Issue Summary: Add a task topic for cluster setup."},
                "source": "slash",
            },
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert any(event["type"] == "approval_required" for event in events)
        assert not any(event["type"] == "tool" and event.get("name") == "generate_dita" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        tool_results = assistant["tool_results"] or {}
        assert tool_results["_approval_state"]["state"] == "required"
        assert tool_results["_approval_state"]["kind"] == "review"
        assert tool_results["_agent_plan"]["mode"] == "generate_dita_preview"
        assert tool_results["_agent_plan"]["preview"]["status"] == "preview_ready"
        assert tool_results["_agent_plan"]["steps"][0]["gate_type"] == "review"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_dita_glossary_request_asks_for_clarification():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\nCreate a map and 10 glossaries",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert not any(event["type"] == "approval_required" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["clarification_needed"] is True
        assert "subject" in plan["preview"]["clarification_question"].lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_dita_unsupported_mixed_request_rejects_cleanly():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\nCreate a map, 10 glossaries, and step definitions for Playwright.",
            tenant_id="kone",
        ):
            events.append(event)

        assert not any(event["type"] == "plan" for event in events)
        assert not any(event["type"] == "approval_required" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        assert "DITA only" in str(assistant["content"] or "")
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_plain_generate_dita_request_uses_review_first_preview():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create 20 topics on cars",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert not any(event["type"] == "tool" and event.get("name") == "generate_dita" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["mode"] == "generate_dita_preview"
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["subject"] == "cars"
        assert "concept" in str(plan["preview"]["clarification_question"]).lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_new_generate_request_does_not_resume_old_clarification():
    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\nCreate a map and 10 glossaries",
            tenant_id="kone",
        ):
            pass

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create 20 topics on cars",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert not any(event["type"] == "approval_required" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["mode"] == "generate_dita_preview"
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["subject"] == "cars"
        assert "concept" in str(plan["preview"]["clarification_question"]).lower()
        assert "subject" not in str(plan["preview"]["clarification_question"]).lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_dita_clarification_then_approve_executes(monkeypatch):
    session_id = chat_service.create_session()
    captured: dict[str, object] = {}

    async def fake_run_tool(
        name: str,
        params: dict,
        *,
        user_id: str = "chat-user",
        session_id: str | None = None,
        run_id: str | None = None,
        tenant_id: str = "kone",
        jira_context: str | None = None,
    ):
        captured.update(
            {
                "name": name,
                "params": dict(params),
                "run_id": run_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "jira_context": jira_context,
            }
        )
        return {
            "jira_id": "TEXT-123",
            "run_id": run_id or "run-direct",
            "download_url": "/api/v1/ai/bundle/TEXT-123/run-direct/download",
            "bundle_summary": "Generated a DITA bundle with 1 map file and 10 topic files.",
            "artifact_counts": {"total_files": 11, "map_files": 1, "topic_files": 10},
            "representative_files": ["root-map.ditamap", "glossary-01.dita"],
            "summary": "Generated a DITA bundle with 1 map file and 10 topic files.",
        }

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\nCreate a map and 10 glossaries",
            tenant_id="kone",
        ):
            pass

        clarification_events = []
        async for event in chat_service.chat_turn(
            session_id,
            "AEM Guides terminology",
            tenant_id="kone",
        ):
            clarification_events.append(event)

        assert any(event["type"] == "plan" for event in clarification_events)
        assert any(event["type"] == "approval_required" for event in clarification_events)
        assert not captured

        approval_events = []
        async for event in chat_service.chat_turn(
            session_id,
            "approve",
            tenant_id="kone",
        ):
            approval_events.append(event)

        assert any(event["type"] == "tool_start" and event.get("name") == "generate_dita" for event in approval_events)
        assert any(event["type"] == "tool" and event.get("name") == "generate_dita" for event in approval_events)
        assert captured["name"] == "generate_dita"
        assert "AEM Guides terminology" in str((captured["params"] or {}).get("text"))
        assert captured["tenant_id"] == "kone"
        assert (captured["params"] or {}).get("bundle_contract", {}).get("topic_family") == "glossentry"

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        assert assistant["tool_results"]["generate_dita"]["bundle_summary"].startswith("Generated a DITA bundle")
        assert "Generated a DITA bundle with 1 map file and 10 topic files." in (assistant["content"] or "")
        assert "I prepared an agent plan for" not in (assistant["content"] or "")
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_approve_refreshes_generate_dita_step_from_preview(monkeypatch):
    session_id = chat_service.create_session()
    captured: dict[str, object] = {}

    async def fake_run_tool(
        name: str,
        params: dict,
        *,
        user_id: str = "chat-user",
        session_id: str | None = None,
        run_id: str | None = None,
        tenant_id: str = "kone",
        jira_context: str | None = None,
    ):
        captured.update(
            {
                "name": name,
                "params": dict(params),
                "run_id": run_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "jira_context": jira_context,
            }
        )
        return {
            "jira_id": "TEXT-777",
            "run_id": run_id or "run-direct",
            "download_url": "/api/v1/ai/bundle/TEXT-777/run-direct/download",
            "bundle_summary": "Generated a DITA bundle with 20 topic files.",
            "artifact_counts": {"total_files": 20, "map_files": 0, "topic_files": 20},
            "representative_files": ["reference_00001.dita", "reference_00002.dita"],
            "summary": "Generated a DITA bundle with 20 topic files.",
        }

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    try:
        plan = chat_service._build_generate_dita_preview_plan(
            user_request="Generate 20 reference topics about insurance reference",
            text="Generate 20 reference topics about insurance reference",
            instructions=None,
        )
        plan["status"] = "awaiting_approval"
        plan["generate_dita_request"] = {"text": "", "instructions": None, "bundle_contract": None}
        plan["steps"][0]["tool_input"] = {"text": "", "instructions": None, "bundle_contract": None}

        execution = chat_service.execution_from_plan(plan, current_step_id=None)
        approval_state = {
            "state": "required",
            "kind": "review",
            "pending_step_id": "generate_dita-step-1",
            "pending_tool_name": "generate_dita",
            "prompt": "Reply `approve` or `continue` when you want me to generate the bundle.",
            "allowed_responses": ["approve", "continue"],
        }
        chat_service._persist_assistant_message(
            session_id,
            "seed-approval-message",
            "Pending reviewed DITA bundle.",
            tool_results=chat_service._agent_payload(
                plan=plan,
                execution=execution,
                approval_state=approval_state,
                tool_results_by_name={},
            ),
        )

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "approve",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "tool" and event.get("name") == "generate_dita" for event in events)
        assert captured["name"] == "generate_dita"
        params = captured["params"] or {}
        assert params["text"] == "Generate 20 reference topics about insurance reference"
        assert params["bundle_contract"]["topic_family"] == "reference"
        assert params["bundle_contract"]["counts"]["reference"] == 20
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_chat_turn_generate_dita_processing_role_map_bundle_executes_end_to_end():
    session_id = chat_service.create_session()
    try:
        prompt = (
            '/generate_dita\n\n'
            'Generate 10 reference topics about insurance and keep 5 topics with '
            'processing-role="resource-only" in the map.'
        )
        async for _ in chat_service.chat_turn(
            session_id,
            prompt,
            tenant_id="kone",
        ):
            pass

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "approve",
            tenant_id="kone",
        ):
            events.append(event)

        tool_event = next(
            event for event in events if event["type"] == "tool" and event.get("name") == "generate_dita"
        )
        result = tool_event["result"]
        assert not result.get("error")
        assert result["artifact_counts"]["map_files"] == 1
        assert result["artifact_counts"]["topic_files"] == 10
        contract = result["generation_contract"]
        assert contract["topic_family"] == "reference"
        assert contract["counts"]["reference"] == 10
        assert contract["include_map"] is True
        assert contract["subject"] == "insurance"
        assert contract["topicref_attribute_distributions"][0]["attribute_name"] == "processing-role"
        assert contract["topicref_attribute_distributions"][0]["count"] == 5

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        assert "Generated a DITA bundle with 1 map file and 10 topic files." in (assistant["content"] or "")
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_dita_clarification_yes_reasks_missing_family():
    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\ninstructions: add external links with scope attribute as external\n\nGenerate 20 topics about cars",
            tenant_id="kone",
        ):
            pass

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "yes",
            tenant_id="kone",
        ):
            events.append(event)

        assert not any(event["type"] == "tool_start" and event.get("name") == "generate_dita" for event in events)
        assert not any(event["type"] == "approval_required" for event in events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["mode"] == "generate_dita_preview"
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["subject"] == "cars"
        assert "concept" in str(plan["preview"]["clarification_question"]).lower()
        assert "20" in str(plan["preview"]["clarification_question"]) or plan["preview"]["requested_count"] == 20
        assert assistant["content"].strip() == str(plan["preview"]["clarification_question"]).strip()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_dita_constraint_conflict_map_reply_adds_explicit_map():
    session_id = chat_service.create_session()
    try:
        base_text = 'Generate 10 reference topics about insurance and keep 5 topics with processing-role="resource-only".'
        plan = chat_service._build_generate_dita_preview_plan(
            user_request=base_text,
            text=base_text,
            instructions=None,
        )
        plan["status"] = "clarification_required"
        plan["preview"]["status"] = "clarification_required"
        plan["preview"]["clarification_needed"] = True
        plan["preview"]["clarification_question"] = (
            "The requested `reference` output cannot safely require `@processing-role`. "
            "Use a map request or remove the map-only attribute. "
            "Do you want to switch to map, reference or remove the conflicting DITA requirement?"
        )
        plan["preview"]["clarification_request"] = {
            "missing_field": "constraint_conflict",
            "question": plan["preview"]["clarification_question"],
            "options": ["map", "reference"],
        }
        plan["preview"]["conflicts"] = [
            {
                "kind": "attribute_family_conflict",
                "message": "The requested `reference` output cannot safely require `@processing-role`. Use a map request or remove the map-only attribute.",
                "suggested_families": ["map", "reference"],
            }
        ]
        plan["generate_dita_request"] = {
            "text": base_text,
            "instructions": None,
            "bundle_contract": None,
        }
        plan["steps"][0]["status"] = "blocked"
        plan["steps"][0]["note"] = str(plan["preview"]["clarification_question"])

        execution = chat_service.execution_from_plan(plan, current_step_id=None)
        chat_service._persist_assistant_message(
            session_id,
            "seed-conflict-message",
            "Need one clarification before generation.",
            tool_results=chat_service._agent_payload(
                plan=plan,
                execution=execution,
                approval_state={"state": "clarification_required", "kind": "review"},
                tool_results_by_name={},
            ),
        )

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "map",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        resumed_plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert resumed_plan["status"] in {"proposed", "awaiting_approval"}
        assert resumed_plan["preview"]["include_map"] is True
        assert resumed_plan["preview"]["topic_family"] == "reference"
        assert not resumed_plan["preview"]["conflicts"]
        request = resumed_plan["generate_dita_request"]
        assert "with a DITA map" in str(request["text"])
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_generate_keyscope_example_requires_shape_clarification():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Generate a keyscope example",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["mode"] == "generate_dita_preview"
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["example_request"] is True
        assert plan["preview"]["example_construct"] == "keyscope"
        assert plan["preview"]["example_shape"] == "unspecified"
        assert plan["preview"]["clarification_request"]["missing_field"] == "example_shape"
        assert "minimal demo" in str(plan["preview"]["clarification_question"]).lower()
        assert "full demo" in str(plan["preview"]["clarification_question"]).lower()
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_keyscope_example_full_demo_reply_unlocks_preview():
    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Generate a keyscope example",
            tenant_id="kone",
        ):
            pass

        followup_events = []
        async for event in chat_service.chat_turn(
            session_id,
            "full demo",
            tenant_id="kone",
        ):
            followup_events.append(event)

        assert any(event["type"] == "plan" for event in followup_events)
        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["status"] == "awaiting_approval"
        assert plan["preview"]["status"] == "preview_ready"
        assert plan["preview"]["example_construct"] == "keyscope"
        assert plan["preview"]["example_shape"] == "full_demo"
        assert plan["preview"]["counts"]["ditamap"] == 3
        assert plan["preview"]["counts"]["topic"] == 6
        assert not plan["preview"]["conflicts"]
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_new_generate_request_after_completed_bundle_starts_fresh_preview(monkeypatch):
    session_id = chat_service.create_session()
    captured: dict[str, object] = {}

    async def fake_run_tool(
        name: str,
        params: dict,
        *,
        user_id: str = "chat-user",
        session_id: str | None = None,
        run_id: str | None = None,
        tenant_id: str = "kone",
        jira_context: str | None = None,
    ):
        captured.update(
            {
                "name": name,
                "params": dict(params),
                "run_id": run_id,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "jira_context": jira_context,
            }
        )
        return {
            "jira_id": "TEXT-999",
            "run_id": run_id or "run-direct",
            "download_url": "/api/v1/ai/bundle/TEXT-999/run-direct/download",
            "bundle_summary": "Generated a DITA bundle with 1 map file and 10 topic files.",
            "artifact_counts": {"total_files": 11, "map_files": 1, "topic_files": 10},
            "representative_files": ["glossary.ditamap", "glossentry_00001.dita"],
            "summary": "Generated a DITA bundle with 1 map file and 10 topic files.",
        }

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "/generate_dita\n\nCreate a map and 10 glossaries",
            tenant_id="kone",
        ):
            pass

        async for _ in chat_service.chat_turn(
            session_id,
            "AEM Guides terminology",
            tenant_id="kone",
        ):
            pass

        async for _ in chat_service.chat_turn(
            session_id,
            "approve",
            tenant_id="kone",
        ):
            pass

        followup_events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create 20 topics on cars",
            tenant_id="kone",
        ):
            followup_events.append(event)

        assert any(event["type"] == "plan" for event in followup_events)
        assert not any(event["type"] == "tool" and event.get("name") == "generate_dita" for event in followup_events)

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        plan = (assistant["tool_results"] or {})["_agent_plan"]
        assert plan["mode"] == "generate_dita_preview"
        assert plan["status"] == "clarification_required"
        assert plan["preview"]["subject"] == "cars"
        assert "concept" in str(plan["preview"]["clarification_question"]).lower()
        assert "AEM Guides terminology" not in (assistant["content"] or "")
    finally:
        chat_service.delete_session(session_id)
