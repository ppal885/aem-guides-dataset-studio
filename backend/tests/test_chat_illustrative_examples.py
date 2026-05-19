"""Tests for LLM-backed illustrative DITA XML examples in grounded chat."""

from __future__ import annotations

import pytest

from app.core.schemas_grounded_answer import NormalizedGroundedFactSet
from app.services import chat_service as cs


@pytest.mark.asyncio
async def test_maybe_enrich_adds_well_formed_llm_snippet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES", True)
    monkeypatch.setattr(cs, "is_llm_available", lambda: True)

    async def _fake_generate_text(**_kwargs):  # noqa: ANN003
        return '{"snippets":["<map><topicref href=\\"a.dita\\" toc=\\"no\\"/></map>"]}'

    monkeypatch.setattr(cs, "generate_text", _fake_generate_text)

    facts = NormalizedGroundedFactSet(
        answer_kind="dita_map_construct",
        source_policy="dita_spec_first",
        canonical_definition="The @toc attribute controls TOC visibility.",
        syntax="yes or no",
        valid_values=["yes", "no"],
        supported_elements=["topicref"],
        verified_examples=[],
        example_verified=False,
        semantic_warnings=[
            "No verified snippet was available for this construct, so the answer omits example XML.",
        ],
    )
    tools = {"lookup_dita_attribute": {"attribute_name": "toc"}}

    out = await cs._maybe_enrich_illustrative_dita_examples(
        question="share some XML examples with toc",
        facts=facts,
        tool_results_by_name=tools,
        trace_id="trace-unit-test",
    )

    assert len(out.verified_examples) == 1
    assert out.verified_examples[0].source == "llm_suggested"
    assert out.example_verified is False
    assert out.example_source == "illustrative_llm"
    assert out.generation_strategy == "llm_illustrative_gap_fill"
    assert cs._STALE_NO_VERIFIED_SNIPPET_WARNING not in out.semantic_warnings


@pytest.mark.asyncio
async def test_maybe_enrich_skips_malformed_snippets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES", True)
    monkeypatch.setattr(cs, "is_llm_available", lambda: True)

    async def _fake_generate_text(**_kwargs):  # noqa: ANN003
        return '{"snippets":["<map><topicref href=\\"a.dita\\" toc=\\"no\\""]}'

    monkeypatch.setattr(cs, "generate_text", _fake_generate_text)

    facts = NormalizedGroundedFactSet(
        answer_kind="dita_map_construct",
        source_policy="dita_spec_first",
        canonical_definition="The @toc attribute controls TOC visibility.",
        supported_elements=["topicref"],
        verified_examples=[],
        example_verified=False,
    )
    tools = {"lookup_dita_attribute": {"attribute_name": "toc"}}

    out = await cs._maybe_enrich_illustrative_dita_examples(
        question="show me an example snippet",
        facts=facts,
        tool_results_by_name=tools,
        trace_id="trace-unit-test",
    )

    assert out.verified_examples == []


@pytest.mark.asyncio
async def test_maybe_enrich_does_not_run_without_example_intent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES", True)
    monkeypatch.setattr(cs, "is_llm_available", lambda: True)

    called = {"n": 0}

    async def _fake_generate_text(**_kwargs):  # noqa: ANN003
        called["n"] += 1
        return '{"snippets":["<map/>"]}'

    monkeypatch.setattr(cs, "generate_text", _fake_generate_text)

    facts = NormalizedGroundedFactSet(
        answer_kind="dita_map_construct",
        source_policy="dita_spec_first",
        canonical_definition="The @toc attribute controls TOC visibility.",
        supported_elements=["topicref"],
        verified_examples=[],
    )
    out = await cs._maybe_enrich_illustrative_dita_examples(
        question="What does the toc attribute do?",
        facts=facts,
        tool_results_by_name={},
        trace_id="trace-unit-test",
    )
    assert called["n"] == 0
    assert out.verified_examples == []


@pytest.mark.asyncio
async def test_maybe_enrich_respects_feature_flag_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cs, "CHAT_LLM_ILLUSTRATIVE_DITA_EXAMPLES", False)
    monkeypatch.setattr(cs, "is_llm_available", lambda: True)

    async def _fake_generate_text(**_kwargs):  # noqa: ANN003
        raise AssertionError("LLM should not be called when flag is off")

    monkeypatch.setattr(cs, "generate_text", _fake_generate_text)

    facts = NormalizedGroundedFactSet(
        answer_kind="dita_attribute",
        source_policy="dita_spec_first",
        canonical_definition="Test.",
        supported_elements=["topicref"],
        verified_examples=[],
    )
    out = await cs._maybe_enrich_illustrative_dita_examples(
        question="show an example",
        facts=facts,
        tool_results_by_name={"lookup_dita_attribute": {"attribute_name": "toc"}},
        trace_id="trace-unit-test",
    )
    assert out.verified_examples == []
