"""Retrieval-quality gate for the grounded chat evidence pack.

These are deterministic (no LLM required), so they run in CI and catch regressions in
the three retrieval defects found in the DITA-OT eval:
  1. near-duplicate chunks (even across different source collections) dominating,
  2. a single source filling the whole pack (no cross-source evidence),
  3. a high-authority but off-topic chunk outranking a genuinely relevant one.
"""
from __future__ import annotations

import types

from app.services.grounding_service import build_evidence_pack


def _cand(source: str, text: str, score: float = 0.5, title: str = "t", url: str = "http://x"):
    return types.SimpleNamespace(source=source, text=text, score=score, metadata={"url": url, "title": title})


def _titles(pack):
    return [c.title for c in pack.chunks]


def _sources(pack):
    return [c.source_kind for c in pack.chunks]


def test_near_duplicate_chunks_collapse_across_sources():
    dup = (
        "The conref attribute reuses content by directly addressing a source element in "
        "another topic file so the content can be maintained once and reused everywhere."
    )
    cands = [
        _cand("learned_qa", dup, 0.9, title="conref-A"),
        _cand("dita_spec", dup, 0.8, title="conref-B"),  # exact duplicate content, different source
        _cand("dita_ot_github", "conref push uses conaction pushbefore and pushreplace.", 0.7, title="conaction"),
    ]
    pack = build_evidence_pack(query="how does conref reuse resolve", tenant_id="t", candidates=cands, max_chunks=8)
    titles = _titles(pack)
    assert not ("conref-A" in titles and "conref-B" in titles), "near-duplicate content was not collapsed"


def test_source_diversity_cap_prevents_single_source_domination():
    cands = [_cand("learned_qa", f"chunk number {i} about keyref resolution and scopes", 0.9 - i * 0.01, title=f"L{i}") for i in range(8)]
    cands += [
        _cand("dita_spec", "keyref resolves against the effective key space built from keyscopes.", 0.6, title="SPEC"),
        _cand("dita_ot_github", "keyref build failures are reported as DOTJ messages during preprocessing.", 0.6, title="OT"),
    ]
    pack = build_evidence_pack(query="how does keyref resolution work with keyscope", tenant_id="t", candidates=cands, max_chunks=6)
    srcs = _sources(pack)
    assert len(set(srcs)) >= 2, f"evidence pack is single-source: {srcs}"
    assert srcs.count("learned_qa") <= max(2, (6 + 1) // 2), f"one source dominated: {srcs}"


def test_relevant_chunk_outranks_offtopic_high_authority_chunk():
    cands = [
        # High-authority source, but off-topic for the query.
        _cand("dita_spec", "The shortdesc element provides a short description used in links and search.", 0.2, title="offtopic"),
        # Lower nominal authority, but directly on-topic (strong lexical + semantic match).
        _cand("dita_ot_github", "DITA-OT preprocessing runs modules in order: branch-filter, then keyref, then conref.", 0.95, title="ontopic"),
    ]
    pack = build_evidence_pack(
        query="in what order does dita-ot run preprocessing modules branch-filter keyref conref",
        tenant_id="t",
        candidates=cands,
        max_chunks=8,
    )
    assert _titles(pack)[0] == "ontopic", f"off-topic high-authority chunk ranked first: {_titles(pack)}"
