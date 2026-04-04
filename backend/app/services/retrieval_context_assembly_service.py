"""
Merge separated retrieval channels before LLM generation.

Pipeline (conceptual):
1. **Recipe store** — catalog candidates (lexical + embedding + optional LLM rerank); see ``RecipeSelectionResult.retrieval_candidates``.
2. **Recipe catalog spec/examples** — ``RecipeSpec`` example_input / example_output / examples (not RAG).
3. **DITA spec store** — normative chunks from ``retrieve_dita_knowledge`` (+ graph hints).
4. **Gold XML examples** — same vector store as AEM Guides when GitHub DITA is merged; queries biased
   toward markup; snippets **reranked** by XML-likeness so code-like chunks float up.
5. **AEM Guides store** — product documentation (optional), separate section.

``assemble_retrieval_for_generation`` returns :class:`AssembledRetrievalContext` for prompts and plan summaries.
"""
from __future__ import annotations

import re

from app.core.schemas_dita_pipeline import (
    AssembledRetrievalContext,
    IntentRecord,
    RecipeSelectionResult,
    RetrievalQueryBundle,
)
from app.generator.recipe_manifest import RecipeSpec
from app.services.rag_query_rewrite_service import (
    fetch_dita_spec_store_for_bundle,
    maybe_fetch_aem_docs,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

_ROOTISH = re.compile(
    r"<\s*(topic|concept|task|reference|map|bookmap|glossentry|subjectscheme)\b",
    re.IGNORECASE,
)


def _xml_example_likeness(snippet: str) -> float:
    """Heuristic: prefer chunks that look like DITA/XML, not marketing prose."""
    s = snippet or ""
    score = min(6.0, s.count("<") * 0.12)
    if _ROOTISH.search(s):
        score += 5.0
    for tag in ("<table", "<tgroup", "<keydef", "<steps", "<xref", "<glossdef", "<subjectdef"):
        if tag.lower() in s.lower():
            score += 1.2
    return score


def _dedupe_docs(docs: list[dict]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for d in docs:
        sn = (d.get("snippet") or "")[:160]
        if sn in seen:
            continue
        seen.add(sn)
        out.append(d)
    return out


def _rerank_docs_for_xml_examples(docs: list[dict]) -> list[dict]:
    return sorted(docs, key=lambda d: -_xml_example_likeness(d.get("snippet") or ""))


def format_recipe_store_block(selection: RecipeSelectionResult) -> str:
    """Human-readable recipe retrieval slice (separate from DITA spec / gold XML)."""
    cands = selection.retrieval_candidates or []
    if not cands:
        return f"(No multi-candidate recipe retrieval; selected: {selection.recipe_id})"
    lines = [
        "Candidates are ordered after retrieval scoring + intent construct overlap (see reasons). "
        "LLM rerank may have reordered the initial embedding/lexical list inside retrieve_recipes.",
        f"Final selected recipe_id: {selection.recipe_id} (score={selection.score}).",
        "",
    ]
    for c in cands:
        mark = " <- SELECTED" if c.recipe_id == selection.recipe_id else ""
        r = ", ".join(c.reasons[:4]) if c.reasons else ""
        lines.append(f"- {c.recipe_id}: {c.title[:120]}{mark}  [retrieval_score={c.retrieval_score}]  ({r})")
    return "\n".join(lines)


def build_recipe_catalog_spec_examples_text(spec: RecipeSpec) -> str:
    """Recipe spec / example fields only (not vector retrieval)."""
    parts: list[str] = []
    if spec.example_input:
        parts.append(f"example_input:\n{spec.example_input.strip()[:1200]}")
    if spec.example_output:
        parts.append(f"example_output_excerpt:\n{spec.example_output.strip()[:1600]}")
    for i, ex in enumerate(spec.examples or []):
        if not isinstance(ex, dict):
            continue
        if ex.get("prompt"):
            parts.append(f"catalog.examples[{i}] prompt: {str(ex['prompt'])[:600]}")
        if ex.get("output"):
            parts.append(f"catalog.examples[{i}] output: {str(ex['output'])[:800]}")
    return "\n\n".join(parts) if parts else "(No example_input / example_output / examples on this RecipeSpec.)"


def fetch_gold_xml_examples_digest(
    bundle: RetrievalQueryBundle,
    user_text: str,
    *,
    max_queries: int = 6,
    k_per_query: int = 2,
    max_snippets: int = 8,
) -> tuple[str, int]:
    """
    Query the **gold** path (typically ``aem_guides`` Chroma, including merged GitHub DITA when enabled).
    Rerank retrieved snippets toward XML-heavy content before formatting.
    """
    try:
        from app.services.doc_retriever_service import format_docs_for_prompt, retrieve_relevant_docs
    except Exception as e:
        logger.debug_structured("Gold XML retrieval unavailable", extra_fields={"error": str(e)})
        return "", 0

    queries: list[str] = []
    for q in bundle.dita_spec_queries[:4]:
        queries.append(f"{q} DITA XML element example")
    for el in bundle.element_focus[:5]:
        queries.append(f"minimal valid DITA {el} XML snippet topic or map")
    if user_text.strip():
        queries.append(f"{user_text[:500]} DITA XML reproduction sample")
    queries.append(f"{bundle.primary_query} DITA markup")

    raw: list[dict] = []
    for q in queries[:max_queries]:
        q = (q or "").strip()
        if not q:
            continue
        raw.extend(retrieve_relevant_docs(q, k=k_per_query, max_snippet_chars=1200))

    merged = _dedupe_docs(raw)
    reranked = _rerank_docs_for_xml_examples(merged)[:max_snippets]
    if not reranked:
        return "", 0
    text = format_docs_for_prompt(reranked)
    return text, len(reranked)


def fetch_aem_guides_store_text(bundle: RetrievalQueryBundle, user_text: str) -> str:
    """Product documentation channel (may overlap corpus with gold path; kept as its own section)."""
    return (maybe_fetch_aem_docs(bundle, user_text) or "").strip()


def assemble_retrieval_for_generation(
    _intent: IntentRecord,
    spec: RecipeSpec,
    user_text: str,
    bundle: RetrievalQueryBundle,
    selection_meta: RecipeSelectionResult,
) -> AssembledRetrievalContext:
    """
    Run spec store, gold-example retrieval (with rerank), AEM channel; merge with recipe store text.
    """
    dita_digest, dita_chunks = fetch_dita_spec_store_for_bundle(bundle)
    gold_text, gold_n = fetch_gold_xml_examples_digest(bundle, user_text)
    aem_text = fetch_aem_guides_store_text(bundle, user_text)

    fusion_note = (
        f"dita_spec_chunks={len(dita_chunks)}, gold_xml_snippets={gold_n}, "
        "gold_snippets_reranked_by_XML_likeness"
    )

    return AssembledRetrievalContext(
        recipe_store_text=format_recipe_store_block(selection_meta),
        recipe_catalog_spec_examples_text=build_recipe_catalog_spec_examples_text(spec),
        dita_spec_store_text=dita_digest,
        gold_xml_examples_text=gold_text,
        aem_guides_store_text=aem_text,
        dita_spec_chunk_count=len(dita_chunks),
        gold_example_snippet_count=gold_n,
        fusion_note=fusion_note,
    )
