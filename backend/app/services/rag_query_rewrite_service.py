"""
Build :class:`RetrievalQueryBundle` from intent + **selected** recipe (query expansion only).

Recipe **catalog** retrieval lives in ``recipe_retriever`` / ``recipe_selector_service`` — not here.
This module only produces queries for the **DITA spec** channel (and bundle metadata reused by
``retrieval_context_assembly_service`` for gold XML / AEM queries).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from app.core.schemas_dita_pipeline import IntentRecord, RetrievalQueryBundle
from app.generator.recipe_manifest import RecipeSpec
from app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge
from app.core.structured_logging import get_structured_logger

if TYPE_CHECKING:
    pass

logger = get_structured_logger(__name__)


def build_retrieval_bundle(intent: IntentRecord, spec: RecipeSpec, user_text: str) -> RetrievalQueryBundle:
    """Deterministic query expansion from intent flags and recipe metadata."""
    parts: list[str] = []
    for p in intent.required_dita_patterns:
        if p and p != "none":
            parts.append(p.replace("_", " "))
    parts.extend(intent.evidence_phrases[:8])
    primary = " ".join(parts).strip() or (user_text[:400] if user_text else "DITA topic")
    primary = f"{primary} DITA structure example"

    dita_queries: list[str] = []
    for kw in spec.retrieval_keywords or []:
        if kw:
            dita_queries.append(kw)
    for hint in spec.retrieval_element_hints or []:
        dita_queries.append(f"DITA {hint} element attribute usage")
    if "table" in intent.required_dita_patterns or "table" in (spec.constructs or []):
        dita_queries.extend(
            [
                "DITA table tgroup colspec entry row thead tbody",
                "DITA align attribute colspec entry",
            ]
        )
    if "table_alignment" in intent.anti_fallback_signals:
        dita_queries.append("DITA table text alignment left right center justify char")

    aem_queries: list[str] = []
    if intent.domain_signals.aem_guides or intent.domain_signals.web_editor:
        aem_queries.extend(
            [
                "AEM Guides DITA table formatting",
                "XML Documentation tables editor alignment",
            ]
        )

    element_focus = list(spec.retrieval_element_hints or [])
    for p in intent.required_dita_patterns:
        if p in ("table", "simpletable", "menucascade", "xref", "keydef_keyref", "conref", "task_steps"):
            element_focus.append(p.split("_")[0])

    negative: list[str] = []
    if "table" in intent.required_dita_patterns or "table_alignment" in intent.anti_fallback_signals:
        negative.extend(["keyref resolution", "glossary"])

    return RetrievalQueryBundle(
        primary_query=primary[:500],
        dita_spec_queries=list(dict.fromkeys(q for q in dita_queries if q))[:8],
        aem_guides_queries=list(dict.fromkeys(aem_queries))[:5],
        element_focus=list(dict.fromkeys(element_focus))[:12],
        negative_terms=list(dict.fromkeys(negative))[:6],
    )


def fetch_dita_spec_store_for_bundle(
    bundle: RetrievalQueryBundle,
    *,
    k_per_query: int = 3,
    include_graph: bool = True,
) -> tuple[str, list[dict]]:
    """
    DITA spec store only: ``retrieve_dita_knowledge`` per bundle query + optional graph summary.
    Separate from recipe catalog, gold XML examples, and AEM Guides product docs.
    """
    all_chunks: list[dict] = []
    seen_text: set[str] = set()

    queries = [bundle.primary_query] + bundle.dita_spec_queries
    for q in queries:
        if not q or not str(q).strip():
            continue
        chunks = retrieve_dita_knowledge(q.strip(), k=k_per_query)
        for c in chunks or []:
            txt = (c.get("text_content") or "")[:600]
            key = (c.get("element_name") or "") + txt[:80]
            if key in seen_text:
                continue
            seen_text.add(key)
            all_chunks.append(c)

    lines: list[str] = []
    for i, c in enumerate(all_chunks[:20]):
        el = c.get("element_name") or ""
        tx = (c.get("text_content") or "")[:500]
        lines.append(f"[{i + 1}] {el}: {tx}")

    graph_block = ""
    if include_graph and bundle.element_focus:
        hint = " ".join(bundle.element_focus[:6])
        try:
            graph_block = retrieve_dita_graph_knowledge(element_hint=hint) or ""
        except Exception as e:
            logger.debug_structured("Graph retrieval skipped", extra_fields={"error": str(e)})

    digest = "DITA KNOWLEDGE (retrieval bundle):\n" + "\n---\n".join(lines)
    if graph_block:
        digest += "\n\nDITA STRUCTURE:\n" + graph_block[:2000]

    return digest, all_chunks


def fetch_rag_context_for_bundle(
    bundle: RetrievalQueryBundle,
    *,
    k_per_query: int = 3,
    include_graph: bool = True,
) -> tuple[str, list[dict]]:
    """Backward-compatible alias for :func:`fetch_dita_spec_store_for_bundle`."""
    return fetch_dita_spec_store_for_bundle(
        bundle, k_per_query=k_per_query, include_graph=include_graph
    )


def maybe_fetch_aem_docs(query_bundle: RetrievalQueryBundle, user_text: str) -> str:
    """Optional AEM Guides RAG block when domain signals warrant it."""
    if not query_bundle.aem_guides_queries:
        return ""
    try:
        from app.utils.evidence_extractor import AEM_GUIDES_TRIGGER_TERMS

        lower = user_text.lower()
        if not any(t in lower for t in AEM_GUIDES_TRIGGER_TERMS):
            return ""
        from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt

        q = " ".join(query_bundle.aem_guides_queries[:2])
        docs = retrieve_relevant_docs(q[:2000], k=2, max_snippet_chars=400)
        if docs:
            return "\n\nAEM GUIDES DOCS:\n" + format_docs_for_prompt(docs)
    except Exception as e:
        logger.debug_structured("AEM doc retrieval skipped", extra_fields={"error": str(e)})
    return ""
