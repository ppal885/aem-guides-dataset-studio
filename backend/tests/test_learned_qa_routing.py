"""Fast unit tests for learned Q&A routing helpers (no Chroma/LLM)."""

from app.services.learned_qa_service import (
    strip_humanized_chat_prefix,
    try_build_learned_qa_fallback_answer,
)
from app.services import chat_service


def test_strip_humanized_chat_prefix():
    assert strip_humanized_chat_prefix(
        "Quick question for our docs team: What is keyscope in DITA?"
    ) == "What is keyscope in DITA?"


def test_learned_qa_seed_match_topicref_topichead_topicgroup():
    prompt = (
        "We hit this in a customer map today. "
        "What is the difference between topicref, topichead, and topicgroup? "
        "Show a realistic ditamap and explain TOC output."
    )
    answer = try_build_learned_qa_fallback_answer(prompt)
    lowered = answer.lower()
    assert "topicref" in lowered
    assert "topichead" in lowered
    assert "topicgroup" in lowered
    assert "conref is the dita-ot preprocess step" not in lowered


def test_learned_qa_seed_match_draft_publish():
    answer = try_build_learned_qa_fallback_answer(
        "How do I exclude draft-only content at publish time?"
    )
    lowered = answer.lower()
    assert "draft-comment" in lowered
    assert "required-cleanup" in lowered


def test_dita_ot_fallback_not_used_for_pure_map_authoring_question():
    prompt = (
        "What is the difference between topicref, topichead, and topicgroup? "
        "Show a realistic ditamap and explain TOC output."
    )
    assert not chat_service._should_try_dita_ot_runtime_fallback(prompt)
    assert not chat_service._build_dita_ot_preprocess_runtime_fallback_response(prompt)


def test_dita_ot_fallback_still_routes_resource_only_toc_troubleshooting():
    prompt = "Why does resource-only reusable content still resolve but not appear in TOC?"
    text = chat_service._build_dita_ot_preprocess_runtime_fallback_response(prompt)
    assert text
    assert "conref" in text.lower()
    assert "resource-only" in text.lower()


def test_learned_qa_seed_match_draft_review_vs_final_output():
    prompt = "How do I include draft comments for review output but exclude them from final DITA-OT output?"
    answer = try_build_learned_qa_fallback_answer(prompt)
    lowered = answer.lower()
    assert "draft-comment" in lowered
    assert "args.draft" in lowered
    assert "## quick reference" not in lowered


def test_dita_ot_preprocess_prompt_does_not_match_unrelated_seed():
    assert try_build_learned_qa_fallback_answer(
        "What does the DITA-OT copy-to preprocess step do?"
    ) == ""
    assert try_build_learned_qa_fallback_answer(
        "What does conrefpush do in DITA-OT preprocessing?"
    ) == ""
