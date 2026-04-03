"""
Query Executor — runs approved research queries against RAG + Tavily
and returns structured results for injection into DITA generation.

Place at: backend/app/services/query_executor.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


@dataclass
class QueryResult:
    """Result from a single research query."""
    query_id:  str
    category:  str
    query:     str
    source:    str          # rag | tavily | both
    chunks:    list[str] = field(default_factory=list)   # text chunks
    summary:   str = ""     # AI summary of results
    urls:      list[str] = field(default_factory=list)   # source URLs
    error:     str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "query_id":   self.query_id,
            "category":   self.category,
            "query":      self.query,
            "source":     self.source,
            "chunks":     self.chunks[:3],
            "summary":    self.summary,
            "urls":       self.urls[:5],
            "error":      self.error,
            "duration_ms": self.duration_ms,
        }

    def has_results(self) -> bool:
        return bool(self.chunks or self.summary)


@dataclass
class ResearchContext:
    """All research results combined — injected into DITA generation."""
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
        }

    def build_context_for_generation(self) -> str:
        """
        Build a single context string to inject into DITA generation prompt.
        Groups results by category for clear LLM consumption.
        """
        sections = []
        cat_order = [
            "dita_elements", "dita_spec", "expert_examples",
            "aem_guides", "bugs_fixes",
        ]
        cat_labels = {
            "dita_elements":  "DITA ELEMENT RULES",
            "dita_spec":      "DITA SPEC CONSTRAINTS",
            "expert_examples":"EXPERT DITA EXAMPLES",
            "aem_guides":     "AEM GUIDES CONTEXT",
            "bugs_fixes":     "KNOWN ISSUES & FIXES",
        }

        for cat in cat_order:
            cat_results = [r for r in self.results if r.category == cat and r.has_results()]
            if not cat_results:
                continue

            label = cat_labels.get(cat, cat.upper())
            parts = [f"=== {label} ==="]

            for r in cat_results:
                if r.summary:
                    parts.append(r.summary)
                for chunk in r.chunks[:2]:
                    if chunk and len(chunk) > 50:
                        parts.append(chunk[:600])

            sections.append("\n".join(parts))

        return "\n\n".join(sections) if sections else ""


# ── RAG query runner ──────────────────────────────────────────────────────────

def _run_rag_query(query_id: str, category: str, query: str) -> QueryResult:
    """Run a query against local ChromaDB RAG collections."""
    import time
    start = time.time()

    result = QueryResult(
        query_id = query_id,
        category = category,
        query    = query,
        source   = "rag",
    )

    try:
        chunks = []

        # DITA spec + element graph
        if category in ("dita_elements", "dita_spec", "expert_examples"):
            from app.services.dita_knowledge_retriever import (
                retrieve_dita_knowledge,
                retrieve_dita_graph_knowledge,
            )
            spec_chunks = retrieve_dita_knowledge(query_text=query, k=3)
            if spec_chunks:
                for c in spec_chunks:
                    text = c.get("text_content") or ""
                    if isinstance(text, list):
                        text = " ".join(text)
                    if text and len(text) > 50:
                        chunks.append(str(text)[:800])

            graph = retrieve_dita_graph_knowledge(element_hint=query)
            if graph:
                chunks.append(graph[:600])

        # Experience League
        if category in ("aem_guides", "bugs_fixes", "dita_elements"):
            from app.services.doc_retriever_service import (
                retrieve_relevant_docs,
                format_docs_for_prompt,
            )
            docs = retrieve_relevant_docs(query=query, k=3)
            if docs:
                for doc in docs:
                    text = doc.get("text_content") or doc.get("content") or ""
                    if text and len(text) > 50:
                        chunks.append(str(text)[:600])

        # Research cache (previously indexed Tavily results)
        try:
            from app.services.embedding_service import embed_query, is_embedding_available
            from app.services.vector_store_service import query_collection, is_chroma_available
            if is_chroma_available() and is_embedding_available():
                q_emb = embed_query(query)
                if q_emb is not None:
                    rows = query_collection(
                        "research_cache",
                        query_embedding=q_emb.tolist(),
                        k=2,
                    )
                    for row in (rows or []):
                        doc = row.get("document") or ""
                        if doc and len(doc) > 50:
                            chunks.append(str(doc)[:500])
        except Exception:
            pass

        result.chunks      = [c for c in chunks if c][:5]
        result.duration_ms = int((time.time() - start) * 1000)

    except Exception as e:
        result.error       = str(e)[:200]
        result.duration_ms = int((time.time() - start) * 1000)

    return result


# ── Tavily query runner ───────────────────────────────────────────────────────

def _run_tavily_query(query_id: str, category: str, query: str) -> QueryResult:
    """Run a query against Tavily web search."""
    import time
    start = time.time()

    result = QueryResult(
        query_id = query_id,
        category = category,
        query    = query,
        source   = "tavily",
    )

    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if not tavily_key:
        result.error = "TAVILY_API_KEY not configured"
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

        client   = TavilyClient(api_key=tavily_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            include_domains=domains,
            max_results=4,
            include_answer=True,
        )

        # AI-generated answer = best summary
        answer = response.get("answer", "")
        if answer:
            result.summary = answer

        # Individual results as chunks
        for r in response.get("results", []):
            content = r.get("content", "").strip()
            url     = r.get("url", "")
            if content and len(content) > 100:
                result.chunks.append(content[:600])
            if url:
                result.urls.append(url)

        result.duration_ms = int((time.time() - start) * 1000)

    except ImportError:
        result.error = "tavily-python not installed"
    except Exception as e:
        result.error       = str(e)[:200]
        result.duration_ms = int((time.time() - start) * 1000)

    return result


# ── Main executor ─────────────────────────────────────────────────────────────

async def execute_query_plan(
    issue_key: str,
    approved_queries: list[dict],
) -> ResearchContext:
    """
    Execute all approved research queries.
    Runs RAG queries synchronously, Tavily queries in parallel.

    approved_queries: list of query dicts from QueryPlan.to_dict()
    Returns ResearchContext with all results.
    """
    import asyncio

    context = ResearchContext(issue_key=issue_key)

    logger.info_structured(
        "Executing query plan",
        extra_fields={
            "issue_key": issue_key,
            "queries":   len(approved_queries),
        },
    )

    # Run queries
    tasks = []
    for q in approved_queries:
        qid      = q.get("id", "")
        category = q.get("category", "")
        query    = q.get("query", "")
        source   = q.get("source", "rag")

        if source == "rag":
            # RAG is synchronous — run in thread pool
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                _run_rag_query,
                qid, category, query,
            )
            context.results.append(result)

        elif source == "tavily":
            # Tavily is also synchronous but we can parallelize
            tasks.append((qid, category, query))

    # Run Tavily queries in parallel
    if tasks:
        loop = asyncio.get_event_loop()
        tavily_results = await asyncio.gather(*[
            loop.run_in_executor(None, _run_tavily_query, qid, cat, q)
            for qid, cat, q in tasks
        ])
        context.results.extend(tavily_results)

    context.completed_at = datetime.utcnow().isoformat()

    total_chunks = sum(len(r.chunks) for r in context.results)
    errors       = [r.error for r in context.results if r.error]

    logger.info_structured(
        "Query plan executed",
        extra_fields={
            "issue_key":    issue_key,
            "total_chunks": total_chunks,
            "errors":       errors[:3],
        },
    )

    return context
