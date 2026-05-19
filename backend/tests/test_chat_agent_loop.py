import pytest

from app.services import chat_service
from app.services.chat_agent_service import build_agent_plan


def test_build_agent_plan_for_dataset_request_requires_approval():
    plan = build_agent_plan(
        "Create a dataset with the parent_child_maps_keys_conref_conkeyref_selfrefs recipe for QA."
    )

    assert plan is not None
    assert plan["requires_approval"] is True
    assert plan["steps"][0]["tool_name"] == "create_job"
    assert plan["steps"][0]["tool_input"]["recipe_type"] == "parent_child_maps_keys_conref_conkeyref_selfrefs"


@pytest.mark.anyio
async def test_chat_turn_dataset_request_emits_plan_and_approval():
    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Create a dataset with the task_topics recipe.",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert any(event["type"] == "approval_required" for event in events)
        assert events[-1]["type"] == "done"

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        tool_results = assistant["tool_results"] or {}
        assert tool_results["_approval_state"]["state"] == "required"
        assert tool_results["_agent_plan"]["status"] == "awaiting_approval"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_approve_executes_saved_create_job_plan(monkeypatch):
    session_id = chat_service.create_session()
    try:
        async for _ in chat_service.chat_turn(
            session_id,
            "Create a dataset with the task_topics recipe.",
            tenant_id="kone",
        ):
            pass

        captured: dict[str, object] = {}

        async def fake_run_tool(name: str, params: dict, **kwargs):
            captured["name"] = name
            captured["params"] = params
            captured["user_id"] = kwargs.get("user_id")
            return {
                "job_id": "job-4242",
                "recipe_type": params.get("recipe_type"),
                "status": "pending",
                "status_url": "/api/v1/jobs/job-4242",
                "download_url": "/api/v1/datasets/job-4242/download",
            }

        monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "approve",
            tenant_id="kone",
            user_id="test-user-1",
        ):
            events.append(event)

        assert any(event["type"] == "tool" and event.get("name") == "create_job" for event in events)
        assert captured["name"] == "create_job"
        assert captured["params"] == {"recipe_type": "task_topics"}
        assert captured["user_id"] == "test-user-1"

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        tool_results = assistant["tool_results"] or {}
        assert tool_results["create_job"]["job_id"] == "job-4242"
        assert tool_results["_agent_plan"]["status"] == "completed"
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_can_show_step_results_for_pending_plan(monkeypatch):
    session_id = chat_service.create_session()
    try:
        async def fake_run_tool(name: str, params: dict, **kwargs):
            assert name == "find_recipes"
            return {
                "query": params.get("query"),
                "recipes": [
                    {
                        "recipe_id": "compact_parent_child_key_resolution",
                        "description": "Compact parent/child key-resolution dataset.",
                    }
                ],
                "count": 1,
            }

        monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

        async for _ in chat_service.chat_turn(
            session_id,
            "Create a dataset for compact parent child key resolution testing.",
            tenant_id="kone",
        ):
            pass

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "show step 1 results",
            tenant_id="kone",
        ):
            events.append(event)

        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "Step 1" in text
        assert "compact_parent_child_key_resolution" in text
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_chat_turn_domain_question_runs_read_only_research_plan(monkeypatch):
    session_id = chat_service.create_session()
    try:
        async def fake_run_tool(name: str, params: dict, **kwargs):
            if name == "lookup_aem_guides":
                return {
                    "results": [
                        {
                            "title": "Author view in AEM Guides",
                            "url": "https://experienceleague.adobe.com/example-author-view",
                            "snippet": "Author view renders resolved references in map context.",
                        }
                    ],
                    "count": 1,
                }
            if name == "lookup_dita_spec":
                return {
                    "spec_chunks": [
                        {
                            "element_name": "topicref",
                            "text_content": "The @href attribute points to a topic resource.",
                        }
                    ],
                    "query": params.get("query"),
                }
            if name == "search_tenant_knowledge":
                return {"results": [], "indexed_doc_count": 0, "count": 0}
            raise AssertionError(f"Unexpected tool {name}")

        monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
        monkeypatch.setattr(chat_service, "is_llm_available", lambda: False)

        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "Do we require href in Hasinstance, and how should it resolve in Author view of AEM Guides?",
            tenant_id="kone",
        ):
            events.append(event)

        assert any(event["type"] == "plan" for event in events)
        assert any(event["type"] == "step_status" for event in events)
        assert not any(event["type"] == "approval_required" for event in events)
        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "At a glance" in text
        assert "Author view renders resolved references in map context" in text
        assert "Search AEM Guides documentation: completed" not in text

        messages = chat_service.get_messages(session_id)
        assistant = messages[-1]
        tool_results = assistant["tool_results"] or {}
        assert tool_results["_agent_plan"]["status"] == "completed"
        assert "lookup_aem_guides" in tool_results
        assert "lookup_dita_spec" in tool_results
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
def test_build_agent_plan_skips_standard_translation_question():
    plan = build_agent_plan("How does the translation workflow work in AEM Guides?")

    assert plan is None


def test_tool_mode_skips_standard_translation_question():
    assert chat_service._should_use_tool_mode("How does the translation workflow work in AEM Guides?") is False


@pytest.mark.anyio
async def test_chat_turn_translation_workflow_question_uses_grounded_path(monkeypatch):
    from conftest import mock_llm_echo_grounding_evidence

    async def fail_build_pack(*_args, **_kwargs):
        raise AssertionError("Corrective RAG pack should not run for grounded AEM product questions")

    async def fake_run_tool(name: str, params: dict, **kwargs):
        if name == "lookup_aem_guides":
            return {
                "query": params.get("query"),
                "summary": "Configure the translation service, create the localization project, start the translation job, and review the translated output when it is ready.",
                "warnings": [],
                "sources": [
                    {
                        "label": "Configure translation service",
                        "url": "https://experienceleague.adobe.com/example-configure-translation",
                        "snippet": "Open the source language folder properties, go to Cloud Services, and configure the translation service before starting localization.",
                    },
                    {
                        "label": "Start the translation job",
                        "url": "https://experienceleague.adobe.com/example-start-translation-job",
                        "snippet": "In the Projects console, open the localization project and start the Translation Job from the Translation Job tile.",
                    },
                    {
                        "label": "Review translated output",
                        "url": "https://experienceleague.adobe.com/example-review-translation",
                        "snippet": "After the translation completes, the Translation Job changes to Ready to Review and you accept the translated copy from the Translation Job tile.",
                    },
                ],
                "results": [
                    {
                        "title": "Configure translation service",
                        "url": "https://experienceleague.adobe.com/example-configure-translation",
                        "snippet": "Open the source language folder properties, go to Cloud Services, and configure the translation service before starting localization.",
                    },
                    {
                        "title": "Create localization project",
                        "url": "https://experienceleague.adobe.com/example-create-localization-project",
                        "snippet": "Content translation must start from the DITA map console and requires creation of a translation project in Adobe Experience Manager.",
                    },
                    {
                        "title": "Start the translation job",
                        "url": "https://experienceleague.adobe.com/example-start-translation-job",
                        "snippet": "In the Projects console, open the localization project and start the Translation Job from the Translation Job tile.",
                    },
                    {
                        "title": "Review translated output",
                        "url": "https://experienceleague.adobe.com/example-review-translation",
                        "snippet": "After the translation completes, the Translation Job changes to Ready to Review and you accept the translated copy from the Translation Job tile.",
                    },
                ],
                "count": 4,
                "status": "success",
                "status_tone": "success",
            }
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "_build_chat_evidence_pack", fail_build_pack)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", mock_llm_echo_grounding_evidence)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(
            session_id,
            "How does the translation workflow work in AEM Guides?",
            tenant_id="kone",
        ):
            events.append(event)

        assert not any(event["type"] == "plan" for event in events)
        assert any(event["type"] == "grounding" for event in events)
        text = "".join(event.get("content", "") for event in events if event["type"] == "chunk")
        assert "## At a glance" in text
        assert "localization project" in text.lower()
        assert "translation job" in text.lower()
        assert "ready to review" in text.lower()
        assert "tenant knowledge" not in text.lower()
        assert "Search AEM Guides documentation: completed" not in text
        grounding_event = next(event for event in events if event["type"] == "grounding")
        assert grounding_event["grounding"]["answer_kind"] == "aem_guides_guidance"
        assert grounding_event["grounding"]["source_policy"] == "aem_guides_first"
        assert "Tenant knowledge was blended" not in " ".join(
            grounding_event["grounding"].get("semantic_warnings") or []
        )
    finally:
        chat_service.delete_session(session_id)


def test_grounded_tool_requests_skip_tenant_lookup_for_pure_aem_product_question():
    requests = chat_service._grounded_tool_requests(
        "grounded_aem_answer",
        "How does the translation workflow work in AEM Guides?",
    )

    assert requests == [
        ("lookup_aem_guides", {"query": "How does the translation workflow work in AEM Guides?"}),
    ]


def test_grounded_tool_requests_keep_tenant_lookup_for_workspace_specific_aem_question():
    query = "How is the translation workflow configured in our tenant in AEM Guides?"
    requests = chat_service._grounded_tool_requests("grounded_aem_answer", query)

    assert requests[0] == ("lookup_aem_guides", {"query": query})
    assert ("search_tenant_knowledge", {"query": query}) in requests


def test_grounded_tool_requests_output_preset_includes_aem_guides_lookup():
    q = "How do I configure HTML5 output presets?"
    requests = chat_service._grounded_tool_requests("grounded_aem_answer", q)

    assert ("lookup_output_preset", {"query": q}) in requests
    assert ("lookup_aem_guides", {"query": q}) in requests


def test_grounded_tool_requests_output_preset_taxonomy_boosts_retrieval_query():
    q = "What are the 7 output preset types in AEM Guides and when to use each?"
    requests = chat_service._grounded_tool_requests("grounded_aem_answer", q)

    assert ("lookup_output_preset", {"query": q}) in requests
    aem_req = next(r for r in requests if r[0] == "lookup_aem_guides")
    assert "understand output presets" in aem_req[1]["query"].lower()


def test_grounded_tool_requests_native_pdf_dita_ot_args_preserve_product_anchors():
    q = "How DITA OT Arguments affect draft comment in Native PDF"
    requests = chat_service._grounded_tool_requests("grounded_aem_answer", q)

    names = [name for name, _params in requests]
    assert names[:3] == ["generate_native_pdf_config", "lookup_output_preset", "lookup_aem_guides"]
    assert "lookup_dita_spec" in names

    native_pdf_req = requests[0][1]
    assert native_pdf_req["config_type"] == "dita_ot_arguments"
    query = native_pdf_req["query"].lower()
    assert "native pdf" in query
    assert "dita-ot" in query or "dita ot" in query
    assert "draft-comment" in query or "draft comment" in query
    assert "prophead" not in query


def test_needs_broad_map_construct_answer_topichead_and_navtitle():
    q = "What is <topichead> and how does navtitle interact with locktitle on topicref?"
    assert chat_service._needs_broad_map_construct_answer(q) is True


def test_grounded_dita_requests_skip_attribute_when_broad_map_question():
    q = "What is <topichead> and how does navtitle interact with locktitle on topicref?"
    requests = chat_service._grounded_tool_requests("grounded_dita_answer", q)

    assert ("lookup_dita_attribute", {"attribute_name": "navtitle"}) not in requests
    assert ("lookup_dita_spec", {"query": q}) in requests


def test_grounded_dita_requests_keep_attribute_for_navtitle_only_question():
    q = "What is the navtitle attribute in DITA maps?"
    requests = chat_service._grounded_tool_requests("grounded_dita_answer", q)

    assert ("lookup_dita_attribute", {"attribute_name": "navtitle"}) in requests
    assert ("lookup_dita_spec", {"query": q}) in requests


def test_grounded_dita_requests_dita_ot_build_params_boost_query_and_tenant_search():
    q = "What arguments should I pass to DITA-OT for draft content?"
    requests = chat_service._grounded_tool_requests("grounded_dita_answer", q)

    spec = next(r for r in requests if r[0] == "lookup_dita_spec")[1]
    merged_q = spec["query"].lower()
    assert "args.draft" in merged_q
    assert "required-cleanup" in merged_q
    assert ("lookup_aem_guides", {"query": spec["query"]}) in requests
    assert ("search_tenant_knowledge", {"query": spec["query"]}) in requests


def test_expand_follow_up_keeps_dita_ot_pdf_draft_argument_context(monkeypatch):
    current = "I am using DITA-OT PDF"

    def fake_user_lines(_sid: str, *, limit: int) -> list[str]:
        return [
            "How can I enable draft-comments to be visible in PDF output ?",
            "What is the argument to be used ?",
            current,
        ]

    monkeypatch.setattr(chat_service, "_fetch_last_user_messages_for_session", fake_user_lines)

    merged = chat_service._expand_follow_up_retrieval_query("sess-1", current)
    assert "draft-comments" in merged.lower()
    assert "args.draft" in merged.lower()
    assert "--args.draft=yes" in merged.lower()
    assert chat_service._determine_answer_mode(current, session_id="sess-1") == "grounded_dita_answer"
    contextual = chat_service._build_contextual_docs_query("sess-1", current)
    assert contextual.source_domain == "dita_ot"
    assert "what command-line argument enables" in contextual.answer_question.lower()


def test_dita_ot_source_gate_rejects_dita_spec_element_only_candidate():
    candidates = [
        chat_service._GroundingCandidate(
            source="dita_spec",
            label="<task>",
            text="<task> is a topic specialization for step-by-step procedures.",
            url="https://dita-lang.org/dita/langref/base/task",
        )
    ]

    selected, debug = chat_service._apply_docs_source_domain_gate(
        query="DITA-OT PDF argument to include draft-comment in output args.draft",
        candidates=candidates,
    )

    assert selected == []
    assert debug["source_domain"] == "dita_ot"
    assert debug["source_domain_mismatch"] is True
    assert "DITA spec element evidence is not enough" in debug["rejected_candidates"][0]["reason"]


def test_dita_ot_source_gate_prefers_official_parameter_candidate():
    official = chat_service._GroundingCandidate(
        source="aem_guides",
        label="DITA-OT base parameters: args.draft",
        text="The args.draft parameter includes draft-comment and required-cleanup content. Use --args.draft=yes.",
        url="https://www.dita-ot.org/dev/parameters/parameters-base",
    )
    unrelated = chat_service._GroundingCandidate(
        source="dita_graph",
        label="<choicetable> placement",
        text="Can appear inside step.",
        url="",
    )

    selected, debug = chat_service._apply_docs_source_domain_gate(
        query="DITA-OT PDF argument to include draft-comment in output args.draft",
        candidates=[unrelated, official],
    )

    assert selected[0] is official
    assert unrelated not in selected
    assert debug["official_evidence_found"] is True


def test_expand_follow_up_adds_args_draft_when_prior_mentions_draft_comment(monkeypatch):
    def fake_recent(_sid: str, latest: str, *, limit: int = 3) -> list[str]:
        if "dita ot" in latest.lower():
            return ["How can draft-comment appear in Native PDF?"]
        return []

    monkeypatch.setattr(chat_service, "_recent_user_messages_before_latest", fake_recent)
    merged = chat_service._expand_follow_up_retrieval_query("sess-1", "What arguments in dita ot?")
    assert "args.draft" in merged.lower()


@pytest.mark.anyio
async def test_dita_ot_pdf_draft_followup_uses_official_docs_and_llm(monkeypatch):
    current = "I am using DITA-OT PDF"

    def fake_user_lines(_sid: str, *, limit: int) -> list[str]:
        return [
            "How can I enable draft-comments to be visible in PDF output ?",
            "What is the argument to be used ?",
            current,
        ]

    async def fake_run_tool(name: str, params: dict, **_kwargs):
        if name == "lookup_dita_spec":
            return {
                "status": "success",
                "query_type": "element",
                "element_name": "task",
                "content_model_summary": "<task> is a topic specialization for step-by-step procedures.",
                "source_url": "https://dita-lang.org/dita/langref/base/task",
            }
        if name == "lookup_aem_guides":
            return {
                "query": params.get("query"),
                "summary": "args.draft includes draft-comment and required-cleanup content in DITA-OT output.",
                "results": [
                    {
                        "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                        "title": "DITA-OT base parameters: args.draft",
                        "snippet": (
                            "args.draft specifies whether draft-comment and required-cleanup elements are "
                            "included in output. Use --args.draft=yes for DITA-OT PDF/PDF2."
                        ),
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
        if name == "search_tenant_knowledge":
            return {"query": params.get("query"), "results": [], "count": 0}
        raise AssertionError(f"Unexpected tool {name}")

    llm_called = {"value": False}

    async def fake_generate_text(*, user_prompt: str = "", **_kwargs):
        llm_called["value"] = True
        assert "args.draft" in user_prompt
        assert "DITA-OT base parameters" in user_prompt
        return (
            "## At a glance\n"
            "For DITA-OT PDF/PDF2, use `--args.draft=yes`. It enables `args.draft`, "
            "which includes `<draft-comment>` and `<required-cleanup>` content in output.\n"
        )

    monkeypatch.setattr(chat_service, "_fetch_last_user_messages_for_session", fake_user_lines)
    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)
    monkeypatch.setattr(chat_service, "generate_text", fake_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    session_id = chat_service.create_session()
    try:
        events = []
        async for event in chat_service.chat_turn(session_id, current, tenant_id="kone"):
            events.append(event)

        assert llm_called["value"] is True
        answer = "".join(str(event.get("content") or "") for event in events if event.get("type") == "chunk")
        assert "args.draft" in answer
        assert "--args.draft=yes" in answer
        assert "<draft-comment>" in answer
        assert "<task>" not in answer

        grounding = next(event["grounding"] for event in events if event.get("type") == "grounding")
        assert grounding["source_domain"] == "dita_ot"
        assert grounding["source_domain_mismatch"] is True
        assert grounding["official_docs_retry"] is False
        assert grounding["llm_gate_reason"] == "llm_synthesis_attempted_with_grounded_evidence"
        rejected = grounding["retrieval_debug"]["rejected_candidates"]
        assert any("DITA spec element evidence is not enough" in row["reason"] for row in rejected)
    finally:
        chat_service.delete_session(session_id)


@pytest.mark.anyio
async def test_dita_ot_tool_grounding_retries_official_docs_before_abstaining(monkeypatch):
    calls = {"lookup_aem_guides": 0}

    async def fake_run_tool(name: str, params: dict, **_kwargs):
        if name == "lookup_dita_spec":
            return {
                "status": "success",
                "query_type": "element",
                "element_name": "draft-comment",
                "content_model_summary": "Processors should not render draft-comment by default.",
                "source_url": "https://dita-lang.org/dita/langref/base/draft-comment",
            }
        if name == "lookup_aem_guides":
            calls["lookup_aem_guides"] += 1
            if calls["lookup_aem_guides"] == 1:
                return {
                    "query": params.get("query"),
                    "results": [
                        {
                            "url": "https://experienceleague.adobe.com/docs/experience-manager-guides",
                            "title": "Generate PDF using DITA-OT",
                            "snippet": "AEM Guides can pass command-line arguments to DITA-OT output presets.",
                        }
                    ],
                    "count": 1,
                }
            return {
                "query": params.get("query"),
                "results": [
                    {
                        "url": "https://www.dita-ot.org/dev/parameters/parameters-base",
                        "title": "DITA-OT base parameters: args.draft",
                        "snippet": "Use --args.draft=yes to include draft-comment and required-cleanup content.",
                    }
                ],
                "count": 1,
            }
        if name == "search_tenant_knowledge":
            return {"query": params.get("query"), "results": [], "count": 0}
        raise AssertionError(f"Unexpected tool {name}")

    monkeypatch.setattr(chat_service, "run_tool", fake_run_tool)

    pack, meta, _results = await chat_service._build_grounded_tool_evidence_pack(
        answer_mode="grounded_dita_answer",
        user_content="What DITA-OT argument enables draft-comment in PDF?",
        tenant_id="kone",
        user_id="test-user",
        session_id="",
    )

    assert calls["lookup_aem_guides"] == 2
    assert meta["official_docs_retry"] is True
    assert meta["source_domain"] == "dita_ot"
    assert pack.decision.status == "grounded"
    assert any("args.draft" in chunk.content for chunk in pack.chunks)


def test_expand_follow_up_merges_share_examples_with_prior_user_question(monkeypatch):
    def fake_recent(_sid: str, latest: str, *, limit: int = 3) -> list[str]:
        if "Share me" in latest:
            return ["What is <topichead> in a DITA map?"]
        return []

    monkeypatch.setattr(chat_service, "_recent_user_messages_before_latest", fake_recent)
    merged = chat_service._expand_follow_up_retrieval_query("sess-1", "Share me some examples of it")
    assert "topichead" in merged.lower()
    assert "follow-up:" in merged.lower()


def test_strong_direct_dita_tool_evidence_accepts_element_and_sources_only():
    assert chat_service._has_strong_direct_dita_tool_evidence(
        {
            "status": "success",
            "element_name": "topichead",
            "query_type": "element",
            "summary": "Navigation heading without a topic.",
            "sources": [{"label": "topichead", "snippet": "Title-only branch node."}],
        }
    )
