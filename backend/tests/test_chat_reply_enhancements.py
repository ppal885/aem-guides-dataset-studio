"""Tests for compact prompt / grounded reply UX enhancements (citations, follow-ups, thin evidence copy)."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from app.core.schemas_grounded_answer import NormalizedGroundedFactSet
from app.db.chat_models import ChatMessage
from app.db.session import SessionLocal
from app.services import chat_service
from app.services.learned_qa_senior_seed import get_senior_prompt_seed_items


def test_grounded_user_prompt_notes_internal_evidence_ids_when_present():
    prompt = chat_service._build_grounded_answer_user_prompt(
        question="What does keyref do?",
        evidence_context="[E1] DITA Spec | Keys\nIndirection for key-based references.\n\n[E2] Tenant\nUse consistent keyscopes.",
        transcript="",
    )
    assert "[E1]" in prompt
    assert "ignore those labels" in prompt


def test_grounded_user_prompt_processing_role_gets_tutorial_depth_addon():
    q = 'What is processing-role="resource-only" in DITA?'
    prompt = chat_service._build_grounded_answer_user_prompt(
        question=q,
        evidence_context="Spec excerpt…",
        transcript="",
        tutorial_depth_addon=chat_service._grounded_dita_tutorial_depth_addon(q),
    )
    assert "TUTORIAL DEPTH" in prompt
    assert "toc" in prompt.lower()


def test_grounded_dita_tutorial_depth_addon_empty_for_unrelated_question():
    assert chat_service._grounded_dita_tutorial_depth_addon("What is the weather?") == ""


def test_grounded_user_prompt_omits_extra_citation_line_without_evidence_ids():
    prompt = chat_service._build_grounded_answer_user_prompt(
        question="Hello",
        evidence_context="Some prose with no bracketed evidence ids.",
        transcript="",
    )
    assert "cite them inline" not in prompt


def test_compact_system_prompt_includes_followups_only_when_env_truthy(monkeypatch):
    monkeypatch.delenv("CHAT_SUGGEST_FOLLOWUPS", raising=False)
    off = chat_service._build_compact_chat_system_prompt()
    assert "FOLLOW-UP SUGGESTIONS" not in off

    monkeypatch.setenv("CHAT_SUGGEST_FOLLOWUPS", "true")
    on = chat_service._build_compact_chat_system_prompt()
    assert "FOLLOW-UP SUGGESTIONS" in on
    assert "Next questions" in on


def test_compact_system_prompt_always_includes_evidence_discipline_rule():
    prompt = chat_service._build_compact_chat_system_prompt()
    assert "No evidence line tags" in prompt or "do not include bracketed evidence" in prompt.lower()


def test_compact_system_prompt_sets_senior_dita_expert_contract():
    prompt = chat_service._build_compact_chat_system_prompt(
        rag_context="LEARNED PROMPT CORPUS:\n[1] Prompt: What is keyscope?\nAnswer:\nSenior answer"
    )

    assert "Senior DITA Expert" in prompt
    assert "ask you first before opening docs" in prompt
    assert "LEARNED QA PRIORITY" in prompt
    assert "search result" in prompt


def test_rag_grounded_fallback_uses_senior_guidance_not_generic_source_dump():
    text = chat_service._build_rag_grounded_fallback_response(
        "How do I troubleshoot missing images in AEM Guides Native PDF?",
        "AEM GUIDES DOCUMENTATION:\n[1] Native PDF images\nImages must resolve from repository paths.",
        "kone",
    )

    assert text.startswith("## Short answer")
    assert "## Senior handling" in text
    assert "Best available guidance" not in text
    assert "Using local indexed knowledge" not in text


def test_senior_seed_has_html_success_pdf_failure_answer():
    items = get_senior_prompt_seed_items()
    match = next(
        item for item in items if item["prompt"] == "How do I debug a topic that publishes in HTML but fails in PDF?"
    )

    answer = match["final_answer"].lower()
    assert "output-pipeline parity" in answer
    assert "processing-role" in answer
    assert "unless the actual symptom" in answer


def test_senior_seed_has_exact_high_value_dita_answers():
    items = get_senior_prompt_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    keyscope = by_prompt["What is keyscope in DITA? Show an example."]
    assert "keyref=\"admin.install\"" in keyscope
    assert "keyref=\"user.install\"" in keyscope
    assert "qualified form" in keyscope

    draft = by_prompt["How do I exclude draft-only content at publish time?"]
    assert "DITAVAL" in draft
    assert "audience=\"internal\"" in draft
    assert "--args.draft=no" in draft

    tables = by_prompt["What is the difference between simpletable and table in DITA?"]
    assert "`<simpletable>`" in tables
    assert "`@morerows` applies to CALS `<entry>` cells" in tables


def test_senior_seed_has_exact_common_dita_tag_answers():
    items = get_senior_prompt_seed_items()
    by_prompt = {str(item.get("prompt") or ""): str(item.get("final_answer") or "") for item in items}

    topicref = by_prompt["What is topicref in DITA? Show an example."]
    assert "<topicref href=\"intro.dita\"/>" in topicref
    assert "map construct" in topicref

    xref = by_prompt["What is xref in DITA? Show an example."]
    assert "<xref href=\"requirements.dita\"" in xref
    assert "keyref=\"support-page\"" in xref

    steps = by_prompt["What are steps, step, and cmd in DITA? Show an example."]
    assert "<steps>" in steps
    assert "<cmd>Open the DITA map.</cmd>" in steps

    reltable = by_prompt["What is reltable in DITA? Show an example."]
    assert "<reltable>" in reltable
    assert "map-level relationship metadata" in reltable

    prolog = by_prompt["What is prolog in DITA? Show an example."]
    assert "<prolog>" in prolog
    assert "not reader body content" in prolog


def test_fetch_last_messages_returns_latest_not_oldest():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        for i in range(8):
            db.add(
                ChatMessage(
                    id=str(uuid4()),
                    session_id=session_id,
                    role="user" if i % 2 == 0 else "assistant",
                    content=f"MSG-{i}",
                    created_at=base + timedelta(seconds=i),
                )
            )
        db.commit()
    finally:
        db.close()

    try:
        last_four = chat_service._fetch_last_messages_for_session(session_id, limit=4)
        assert [m["content"] for m in last_four] == ["MSG-4", "MSG-5", "MSG-6", "MSG-7"]

        tr = chat_service._recent_chat_transcript(session_id, limit=4)
        assert "MSG-7" in tr
        assert "MSG-0" not in tr
    finally:
        chat_service.delete_session(session_id)


def test_expand_follow_up_retrieval_merges_prior_user_turn():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Explain keyref usage in DITA maps.",
                created_at=base,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="assistant",
                content="Keys let you indirect hrefs.",
                created_at=base + timedelta(seconds=1),
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="What about conref?",
                created_at=base + timedelta(seconds=2),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        merged = chat_service._expand_follow_up_retrieval_query(session_id, "What about conref?")
        assert "keyref" in merged.lower()
        assert "conref" in merged.lower()
        assert "Follow-up:" in merged
    finally:
        chat_service.delete_session(session_id)


def test_expand_follow_up_does_not_merge_standalone_question():
    session_id = chat_service.create_session()
    db = SessionLocal()
    try:
        base = datetime.utcnow()
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="Hello",
                created_at=base,
            )
        )
        db.add(
            ChatMessage(
                id=str(uuid4()),
                session_id=session_id,
                role="user",
                content="What is the purpose of keyref in DITA?",
                created_at=base + timedelta(seconds=1),
            )
        )
        db.commit()
    finally:
        db.close()

    try:
        q = "What is the purpose of keyref in DITA?"
        merged = chat_service._expand_follow_up_retrieval_query(session_id, q)
        assert merged == q
    finally:
        chat_service.delete_session(session_id)


def test_render_normalized_grounded_fact_set_strengthen_hint_for_thin_evidence():
    facts = NormalizedGroundedFactSet(
        answer_kind="dita_element",
        source_policy="dita_spec_first",
        canonical_definition="The topic element wraps topic content.",
        thin_evidence=True,
    )
    text = chat_service._render_normalized_grounded_fact_set(facts)
    assert "What would strengthen this answer" in text


def test_render_normalized_grounded_fact_set_strengthen_hint_for_semantic_warnings():
    facts = NormalizedGroundedFactSet(
        answer_kind="dita_element",
        source_policy="dita_spec_first",
        canonical_definition="The topic element wraps topic content.",
        semantic_warnings=["Low semantic similarity to retrieval query."],
    )
    text = chat_service._render_normalized_grounded_fact_set(facts)
    assert "What would strengthen this answer" in text


@pytest.mark.anyio
async def test_synthesize_agent_answer_requests_recommended_step_and_higher_token_budget(monkeypatch):
    calls: list[dict] = []

    async def capture_generate_text(**kwargs):
        calls.append(kwargs)
        return "## Summary\n\nOK.\n\n## Details\n\n- a\n\n## Limits of evidence\n\n- none\n\n## Sources\n\n- s"

    monkeypatch.setattr(chat_service, "generate_text", capture_generate_text)
    monkeypatch.setattr(chat_service, "is_llm_available", lambda: True)

    plan = {"goal": "Explain reuse"}
    tool_results = {
        "lookup_dita_spec": {
            "spec_chunks": [
                {"element_name": "keydef", "text_content": "Keyref resolves via key space."},
            ],
        },
    }
    await chat_service._synthesize_agent_answer(
        user_content="What is keyref?",
        plan=plan,
        tool_results_by_name=tool_results,
    )
    assert calls, "generate_text should run when LLM is available and evidence is non-empty"
    system_prompt = calls[0]["system_prompt"]
    assert "Recommended next step" in system_prompt
    assert calls[0]["max_tokens"] == 1600


@pytest.mark.anyio
async def test_evidence_pack_prompt_context_numbers_candidates_for_grounded_path():
    """Regression: evidence shown to the LLM uses [E1], [E2] headers (aligned with citation UX)."""
    from app.services.grounding_service import build_evidence_pack

    c1 = type(
        "Candidate",
        (),
        {
            "source": "dita_spec",
            "label": "Keys",
            "text": "Keyref resolves to a key definition.",
            "url": "",
            "metadata": {"title": "Keys"},
            "score": 0.0,
        },
    )()
    c2 = type(
        "Candidate",
        (),
        {
            "source": "aem_guides",
            "label": "Guides",
            "text": "Map-level keys in AEM Guides.",
            "url": "",
            "metadata": {"title": "Guides"},
            "score": 0.0,
        },
    )()
    pack = build_evidence_pack(query="keyref", tenant_id="kone", candidates=[c1, c2])
    ctx = pack.build_prompt_context(limit=6)
    assert "[E1]" in ctx
    assert "[E2]" in ctx
