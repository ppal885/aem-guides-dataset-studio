"""
Updated Query Executor — uses advanced_rag_service instead of basic retrieval.
Drop-in replacement for backend/app/services/query_executor.py

Changes from old version:
- Uses advanced_rag_search() instead of direct ChromaDB calls
- Query expansion built-in (3 variants per query)
- Hybrid BM25 + semantic search
- Cross-encoder reranking
- Freshness + credibility scoring
- Deduplication
- Tavily results properly chunked before indexing
- Full relevance scores returned to frontend
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from app.core.structured_logging import get_structured_logger
from app.services.advanced_rag_service import (
    advanced_rag_search,
    chunk_and_index_tavily_results,
    compute_credibility_score,
    SOURCE_CREDIBILITY,
)

logger = get_structured_logger(__name__)

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
TRUSTED_SOURCES = list(SOURCE_CREDIBILITY.keys())[:-1]  # all except "default"


@dataclass
class QueryResult:
    query_id:     str
    category:     str
    query:        str
    source:       str
    chunks:       list[str] = field(default_factory=list)
    summary:      str = ""
    urls:         list[str] = field(default_factory=list)
    error:        str = ""
    duration_ms:  int = 0
    # NEW: scoring metadata
    top_score:    float = 0.0
    avg_score:    float = 0.0
    expanded_queries: list[str] = field(default_factory=list)
    chunk_scores: list[dict] = field(default_factory=list)   # per-chunk scores
    dita_section_map: dict = field(default_factory=dict)     # section → best chunks

    def to_dict(self) -> dict:
        return {
            "query_id":         self.query_id,
            "category":         self.category,
            "query":            self.query,
            "source":           self.source,
            "chunks":           self.chunks[:3],
            "summary":          self.summary,
            "urls":             self.urls[:5],
            "error":            self.error,
            "duration_ms":      self.duration_ms,
            "top_score":        round(self.top_score, 3),
            "avg_score":        round(self.avg_score, 3),
            "expanded_queries": self.expanded_queries,
            "chunk_scores":     self.chunk_scores[:5],
            "dita_section_map": self.dita_section_map,
        }

    def has_results(self) -> bool:
        return bool(self.chunks or self.summary)


@dataclass
class ResearchContext:
    issue_key:    str
    results:      list[QueryResult] = field(default_factory=list)
    completed_at: str = ""

    def to_dict(self) -> dict:
        return {
            "issue_key":    self.issue_key,
            "results":      [r.to_dict() for r in self.results],
            "completed_at": self.completed_at,
            "total_chunks": sum(len(r.chunks) for r in self.results),
            "sources_used": list({r.source for r in self.results if r.has_results()}),
            # NEW: aggregate quality metrics
            "avg_top_score":   round(
                sum(r.top_score for r in self.results if r.top_score) /
                max(1, sum(1 for r in self.results if r.top_score)), 3
            ),
            "freshness_summary": _summarize_freshness(self.results),
        }

    def build_context_for_generation(self) -> str:
        """
        Build generation context — now includes scores and DITA section hints.
        """
        parts = []
        cat_order = ["dita_elements", "dita_spec", "expert_examples", "aem_guides", "bugs_fixes"]
        cat_labels = {
            "dita_elements":   "DITA ELEMENT RULES",
            "dita_spec":       "DITA SPEC CONSTRAINTS",
            "expert_examples": "EXPERT DITA EXAMPLES",
            "aem_guides":      "AEM GUIDES CONTEXT",
            "bugs_fixes":      "KNOWN ISSUES & FIXES",
        }

        for cat in cat_order:
            cat_results = [r for r in self.results if r.category == cat and r.has_results()]
            if not cat_results:
                continue

            label = cat_labels.get(cat, cat.upper())
            parts.append(f"=== {label} ===")

            for r in cat_results:
                if r.expanded_queries:
                    parts.append(f"[Searched: {' | '.join(r.expanded_queries[:2])}]")
                if r.summary:
                    parts.append(r.summary)
                for chunk in r.chunks[:2]:
                    if chunk and len(chunk) > 50:
                        parts.append(chunk[:600])

        return "\n\n".join(parts) if parts else ""


def _summarize_freshness(results: list[QueryResult]) -> str:
    scores = [r.chunk_scores[0].get("freshness_score", 0) for r in results if r.chunk_scores]
    if not scores:
        return "unknown"
    avg = sum(scores) / len(scores)
    if avg > 0.8: return "fresh"
    if avg > 0.5: return "moderate"
    return "stale — consider re-indexing"


# ── RAG query runner (upgraded) ───────────────────────────────────────────────

async def _run_rag_query_advanced(query_id: str, category: str, query: str, dita_type: str = "task") -> QueryResult:
    """Run advanced RAG search with all upgrades."""
    import time
    start = time.time()

    result = QueryResult(
        query_id = query_id,
        category = category,
        query    = query,
        source   = "rag",
    )

    try:
        rag_result = await advanced_rag_search(
            query       = query,
            dita_type   = dita_type,
            top_k       = 5,
        )

        result.expanded_queries = rag_result.expanded_queries
        result.duration_ms      = rag_result.duration_ms

        if rag_result.chunks:
            result.chunks = [c.text for c in rag_result.chunks]
            result.urls   = [c.source_url for c in rag_result.chunks if c.source_url]
            result.top_score = rag_result.chunks[0].final_score
            result.avg_score = sum(c.final_score for c in rag_result.chunks) / len(rag_result.chunks)

            # Per-chunk scoring metadata for frontend display
            result.chunk_scores = [
                {
                    "text_preview":    c.text[:100],
                    "final_score":     round(c.final_score, 3),
                    "semantic_score":  round(c.semantic_score, 3),
                    "rerank_score":    round(c.rerank_score, 3),
                    "freshness_score": round(c.freshness_score, 3),
                    "credibility":     round(c.credibility_score, 3),
                    "source_type":     c.source_type,
                    "dita_sections":   c.dita_sections,
                    "source_url":      c.source_url,
                }
                for c in rag_result.chunks
            ]

            # Build DITA section map — which chunks help which sections
            for chunk in rag_result.chunks:
                for section in chunk.dita_sections:
                    if section not in result.dita_section_map:
                        result.dita_section_map[section] = chunk.text[:300]

    except Exception as e:
        result.error       = str(e)[:200]
        result.duration_ms = int((time.time() - start) * 1000)
        logger.warning_structured("RAG query failed", extra_fields={"error": str(e)})

    return result


# ── Tavily query runner (with proper chunking) ────────────────────────────────

def _run_tavily_query_chunked(query_id: str, category: str, query: str) -> QueryResult:
    """
    Run Tavily search AND properly chunk results before indexing.
    Old version stored 600-char blobs. Now uses smart_chunk_text().
    """
    import time
    start = time.time()

    result = QueryResult(
        query_id = query_id,
        category = category,
        query    = query,
        source   = "tavily",
    )

    if not TAVILY_API_KEY:
        result.error = "TAVILY_API_KEY not set"
        return result

    try:
        from tavily import TavilyClient

        DOMAIN_MAP = {
            "aem_guides": ["experienceleague.adobe.com", "helpx.adobe.com"],
            "bugs_fixes":  ["experienceleague.adobe.com", "helpx.adobe.com", "adobe.com"],
            "dita_spec":   ["docs.oasis-open.org", "dita-ot.org"],
        }
        domains = DOMAIN_MAP.get(category, [
            "experienceleague.adobe.com",
            "docs.oasis-open.org",
            "dita-ot.org",
        ])

        client   = TavilyClient(api_key=TAVILY_API_KEY)
        response = client.search(
            query          = query,
            search_depth   = "advanced",
            include_domains= domains,
            max_results    = 5,
            include_answer = True,
        )

        answer = response.get("answer", "")
        if answer:
            result.summary = answer

        raw_results = response.get("results", [])

        # Properly chunk results before extracting text
        ids, docs, metas = chunk_and_index_tavily_results(
            results  = raw_results,
            topic_id = query_id,
            tag      = category,
        )

        result.chunks = docs[:5]
        result.urls   = list({m.get("url", "") for m in metas if m.get("url")})[:5]

        # Score credibility per source
        cred_scores = [compute_credibility_score(m.get("url", "")) for m in metas[:5]]
        if cred_scores:
            result.top_score = max(cred_scores)
            result.avg_score = sum(cred_scores) / len(cred_scores)
            result.chunk_scores = [
                {
                    "text_preview":    d[:100],
                    "final_score":     round(c, 3),
                    "credibility":     round(c, 3),
                    "source_type":     "web",
                    "source_url":      m.get("url", ""),
                    "freshness_score": 0.95,  # Tavily = recent
                }
                for d, c, m in zip(docs[:5], cred_scores, metas[:5])
            ]

        # Also index chunked results into ChromaDB for future queries
        _async_index_to_rag(ids, docs, metas)

        result.duration_ms = int((time.time() - start) * 1000)

    except ImportError:
        result.error = "tavily-python not installed"
    except Exception as e:
        result.error       = str(e)[:200]
        result.duration_ms = int((time.time() - start) * 1000)

    return result


def _async_index_to_rag(ids, docs, metas):
    """Index Tavily chunks into RAG in background (best-effort)."""
    try:
        from app.services.advanced_rag_service import embed_texts_advanced
        from app.services.vector_store_service import add_documents, is_chroma_available
        if not is_chroma_available() or not docs:
            return
        embeddings = embed_texts_advanced(docs)
        add_documents(
            "research_cache",
            ids        = ids,
            documents  = docs,
            metadatas  = metas,
            embeddings = embeddings,
        )
    except Exception as e:
        logger.debug_structured("Background RAG indexing failed", extra_fields={"error": str(e)})


# ── Main executor ─────────────────────────────────────────────────────────────

async def execute_query_plan(
    issue_key: str,
    approved_queries: list[dict],
    dita_type: str = "task",
) -> ResearchContext:
    """
    Execute all approved research queries using advanced pipeline.
    """
    import asyncio

    context = ResearchContext(issue_key=issue_key)

    logger.info_structured(
        "Executing query plan (advanced)",
        extra_fields={"issue_key": issue_key, "queries": len(approved_queries)},
    )

    rag_tasks    = []
    tavily_tasks = []

    for q in approved_queries:
        qid      = q.get("id", "")
        category = q.get("category", "")
        query    = q.get("query", "")
        source   = q.get("source", "rag")

        if source == "rag":
            rag_tasks.append((qid, category, query))
        elif source == "tavily":
            tavily_tasks.append((qid, category, query))

    # Run RAG queries (async, parallel)
    if rag_tasks:
        rag_results = await asyncio.gather(*[
            _run_rag_query_advanced(qid, cat, q, dita_type)
            for qid, cat, q in rag_tasks
        ])
        context.results.extend(rag_results)

    # Run Tavily queries in thread pool (sync but parallelized)
    if tavily_tasks:
        loop = asyncio.get_event_loop()
        tavily_results = await asyncio.gather(*[
            loop.run_in_executor(None, _run_tavily_query_chunked, qid, cat, q)
            for qid, cat, q in tavily_tasks
        ])
        context.results.extend(tavily_results)

    context.completed_at = datetime.utcnow().isoformat()

    logger.info_structured(
        "Query plan executed (advanced)",
        extra_fields={
            "issue_key":    issue_key,
            "total_chunks": sum(len(r.chunks) for r in context.results),
            "avg_top_score": context.to_dict().get("avg_top_score", 0),
        },
    )
    return context
