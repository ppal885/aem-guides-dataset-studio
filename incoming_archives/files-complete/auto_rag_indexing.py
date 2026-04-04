# =============================================================================
# SECTION 8 — AUTO RAG INDEXING FROM RESEARCH
# Research automatically indexes to RAG — future generation improves
# Add these to mcp_server.py above if __name__ == "__main__":
# =============================================================================

import json
import hashlib
from datetime import datetime
from pathlib import Path

# Track what's already been indexed to avoid duplicates
RAG_INDEX_LOG = PROJECT_ROOT / "output" / "rag_index_log.json"

# Topics to auto-research and index
AUTO_RESEARCH_TOPICS = [
    {
        "id":    "dita_spec_task",
        "query": "DITA 1.3 task topic required elements structure",
        "tag":   "dita-spec",
        "domains": ["docs.oasis-open.org", "dita-ot.org"],
    },
    {
        "id":    "dita_spec_concept",
        "query": "DITA 1.3 concept topic conbody section structure",
        "tag":   "dita-spec",
        "domains": ["docs.oasis-open.org"],
    },
    {
        "id":    "dita_spec_keyref",
        "query": "DITA 1.3 keyref keyscope resolution rules",
        "tag":   "dita-spec",
        "domains": ["docs.oasis-open.org", "dita-ot.org"],
    },
    {
        "id":    "dita_spec_conref",
        "query": "DITA 1.3 conref content reference push mechanism",
        "tag":   "dita-spec",
        "domains": ["docs.oasis-open.org"],
    },
    {
        "id":    "aem_guides_latest",
        "query": "AEM Guides latest release notes features 2024",
        "tag":   "aem-guides",
        "domains": ["experienceleague.adobe.com", "helpx.adobe.com"],
    },
    {
        "id":    "aem_guides_authoring",
        "query": "AEM Guides DITA authoring best practices",
        "tag":   "aem-guides",
        "domains": ["experienceleague.adobe.com"],
    },
    {
        "id":    "aem_guides_maps",
        "query": "AEM Guides ditamap management publishing",
        "tag":   "aem-guides",
        "domains": ["experienceleague.adobe.com"],
    },
    {
        "id":    "aem_guides_keyrefs",
        "query": "AEM Guides key references keyscopes configuration",
        "tag":   "aem-guides",
        "domains": ["experienceleague.adobe.com"],
    },
]


def _load_index_log() -> dict:
    """Load the RAG index log to track what's been indexed."""
    if not RAG_INDEX_LOG.exists():
        return {}
    try:
        return json.loads(RAG_INDEX_LOG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_index_log(log: dict) -> None:
    """Save the RAG index log."""
    RAG_INDEX_LOG.parent.mkdir(parents=True, exist_ok=True)
    RAG_INDEX_LOG.write_text(json.dumps(log, indent=2), encoding="utf-8")


def _is_already_indexed(topic_id: str, max_age_days: int = 7) -> bool:
    """Check if a topic was indexed recently (within max_age_days)."""
    log = _load_index_log()
    if topic_id not in log:
        return False
    indexed_at = log[topic_id].get("indexed_at", "")
    if not indexed_at:
        return False
    try:
        indexed_dt = datetime.fromisoformat(indexed_at)
        age_days = (datetime.utcnow() - indexed_dt).days
        return age_days < max_age_days
    except Exception:
        return False


def _mark_as_indexed(topic_id: str, query: str, chunks: int) -> None:
    """Mark a topic as indexed in the log."""
    log = _load_index_log()
    log[topic_id] = {
        "query":      query,
        "indexed_at": datetime.utcnow().isoformat(),
        "chunks":     chunks,
    }
    _save_index_log(log)


@mcp.tool()
def auto_index_research_to_rag(force: bool = False) -> str:
    """
    Automatically research and index ALL standard DITA/AEM topics into RAG.
    Skips topics already indexed in last 7 days (unless force=True).

    This is the CORE tool that makes your RAG smarter over time.
    Run once → future generations grounded in latest DITA spec + AEM docs.

    Topics indexed:
    - DITA 1.3 task/concept/reference/map structure
    - DITA keyref, conref, keyscope rules
    - AEM Guides latest release notes
    - AEM Guides authoring best practices
    - AEM Guides ditamap management

    force: True to re-index even if recently indexed
    """
    if not TAVILY_API_KEY:
        return (
            "❌ TAVILY_API_KEY not set.\n"
            "Get free key at https://tavily.com\n"
            "Add to .env: TAVILY_API_KEY=tvly-xxxx"
        )

    try:
        from tavily import TavilyClient
        from backend.app.services.embedding_service import (
            embed_texts_batched, embed_texts, is_embedding_available
        )
        from backend.app.services.vector_store_service import (
            add_documents, is_chroma_available
        )

        if not is_chroma_available():
            return "❌ ChromaDB not available. Start ChromaDB first."
        if not is_embedding_available():
            return "❌ Embedding model not available."

        client = TavilyClient(api_key=TAVILY_API_KEY)
        results_log = []
        total_chunks = 0
        skipped = 0

        for topic in AUTO_RESEARCH_TOPICS:
            topic_id = topic["id"]

            # Skip if recently indexed
            if not force and _is_already_indexed(topic_id):
                skipped += 1
                results_log.append(f"⏭️  Skipped (recent): {topic_id}")
                continue

            try:
                # Search
                result = client.search(
                    query=topic["query"],
                    search_depth="advanced",
                    include_domains=topic["domains"],
                    max_results=5,
                    include_answer=True,
                )

                raw_results = result.get("results", [])
                answer      = result.get("answer", "")

                if not raw_results and not answer:
                    results_log.append(f"⚠️  No results: {topic_id}")
                    continue

                # Build documents to index
                documents = []
                metadatas = []
                ids       = []

                # Index the AI-generated answer first (highest quality)
                if answer:
                    doc_id = f"research_{topic_id}_answer"
                    documents.append(f"[SUMMARY] {topic['query']}\n\n{answer}")
                    metadatas.append({
                        "topic_id":  topic_id,
                        "tag":       topic["tag"],
                        "query":     topic["query"],
                        "type":      "answer",
                        "source":    "tavily_answer",
                        "url":       "",
                        "indexed_at": datetime.utcnow().isoformat(),
                    })
                    ids.append(doc_id)

                # Index individual search results
                for i, r in enumerate(raw_results):
                    content = r.get("content", "").strip()
                    if len(content) < 100:
                        continue

                    url     = r.get("url", "")
                    rtitle  = r.get("title", "")
                    doc_text = f"{rtitle}\n{url}\n\n{content}"

                    # Use URL hash for deduplication
                    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
                    doc_id   = f"research_{topic_id}_{url_hash}"

                    documents.append(doc_text[:4000])
                    metadatas.append({
                        "topic_id":  topic_id,
                        "tag":       topic["tag"],
                        "query":     topic["query"],
                        "type":      "result",
                        "source":    "tavily_search",
                        "url":       url,
                        "title":     rtitle,
                        "indexed_at": datetime.utcnow().isoformat(),
                    })
                    ids.append(doc_id)

                if not documents:
                    results_log.append(f"⚠️  No indexable content: {topic_id}")
                    continue

                # Embed
                embeddings = (
                    embed_texts_batched(documents)
                    if len(documents) > 8
                    else embed_texts(documents)
                )
                if embeddings is None:
                    results_log.append(f"❌ Embedding failed: {topic_id}")
                    continue

                # Store in ChromaDB collection 'research_cache'
                success = add_documents(
                    "research_cache",
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=[e.tolist() for e in embeddings],
                )

                if success:
                    _mark_as_indexed(topic_id, topic["query"], len(documents))
                    total_chunks += len(documents)
                    results_log.append(
                        f"✅ Indexed: {topic_id} ({len(documents)} chunks)"
                    )
                else:
                    results_log.append(f"❌ Index failed: {topic_id}")

            except Exception as e:
                results_log.append(f"❌ Error {topic_id}: {str(e)[:100]}")

        return f"""
AUTO RAG INDEXING COMPLETE
{'='*50}
Topics processed: {len(AUTO_RESEARCH_TOPICS)}
Newly indexed:    {len(AUTO_RESEARCH_TOPICS) - skipped}
Skipped (recent): {skipped}
Total chunks:     {total_chunks}

Results:
{chr(10).join(results_log)}

{'='*50}
Your RAG now includes latest:
✅ DITA 1.3 spec rules from OASIS
✅ AEM Guides documentation from Experience League
✅ Keyref, conref, keyscope rules
✅ AEM Guides release notes

Next generation will automatically use this knowledge.
Run weekly to keep RAG fresh (force=True to refresh now).
"""

    except ImportError:
        return "❌ tavily-python not installed. Run: pip install tavily-python"
    except Exception as e:
        return f"❌ Auto indexing failed: {e}"


@mcp.tool()
def research_jira_issue_and_index(issue_key: str) -> str:
    """
    Research web content for a specific Jira issue AND index to RAG.
    Automatically improves future generation for similar issues.

    This is the SMART workflow:
    1. Reads your Jira issue
    2. Searches relevant DITA/AEM content
    3. Indexes results into ChromaDB
    4. Future issues of same type get better DITA

    Run this BEFORE generate_dita_from_jira for best results.
    """
    if not TAVILY_API_KEY:
        return "❌ TAVILY_API_KEY not set in .env"

    try:
        from tavily import TavilyClient
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue
        from backend.app.services.embedding_service import embed_texts, is_embedding_available
        from backend.app.services.vector_store_service import add_documents, is_chroma_available

        # Fetch issue
        jira    = JiraClient()
        raw     = jira.get_issue(issue_key)
        fields  = raw.get("fields", {})
        summary = fields.get("summary", "")
        labels  = fields.get("labels", [])
        desc    = extract_description_from_issue(raw)

        # Build targeted queries from issue content
        queries = []

        # Base query from summary
        queries.append(f"DITA AEM Guides {summary[:80]}")

        # Label-based queries
        dita_labels = [l for l in labels if any(
            x in l.lower() for x in
            ["dita", "keyref", "conref", "map", "topic", "aem", "guides"]
        )]
        if dita_labels:
            queries.append(f"DITA {' '.join(dita_labels[:3])} AEM Guides")

        # Content-based query
        if desc:
            queries.append(f"AEM Guides {desc[:100]}")

        client = TavilyClient(api_key=TAVILY_API_KEY)
        all_documents = []
        all_metadatas = []
        all_ids       = []
        search_log    = []

        for i, query in enumerate(queries[:3]):  # Max 3 queries per issue
            try:
                result = client.search(
                    query=query,
                    search_depth="advanced",
                    include_domains=DITA_TRUSTED_SOURCES,
                    max_results=3,
                    include_answer=True,
                )

                answer = result.get("answer", "")
                if answer:
                    all_documents.append(f"[Q: {query}]\n{answer}")
                    all_metadatas.append({
                        "issue_key": issue_key,
                        "query":     query,
                        "type":      "answer",
                        "source":    "tavily_answer",
                        "url":       "",
                        "tag":       "issue-research",
                        "indexed_at": datetime.utcnow().isoformat(),
                    })
                    all_ids.append(
                        f"issue_{issue_key}_q{i}_answer"
                    )

                for j, r in enumerate(result.get("results", [])):
                    content = r.get("content", "").strip()
                    if len(content) < 100:
                        continue
                    url_hash = hashlib.md5(
                        r.get("url", str(j)).encode()
                    ).hexdigest()[:8]
                    all_documents.append(
                        f"{r.get('title','')}\n{r.get('url','')}\n\n{content[:3000]}"
                    )
                    all_metadatas.append({
                        "issue_key": issue_key,
                        "query":     query,
                        "type":      "result",
                        "source":    "tavily_search",
                        "url":       r.get("url", ""),
                        "title":     r.get("title", ""),
                        "tag":       "issue-research",
                        "indexed_at": datetime.utcnow().isoformat(),
                    })
                    all_ids.append(f"issue_{issue_key}_q{i}_{url_hash}")

                search_log.append(
                    f"  ✅ Query {i+1}: {len(result.get('results',[]))} results"
                )

            except Exception as e:
                search_log.append(f"  ⚠️ Query {i+1} failed: {str(e)[:60]}")

        if not all_documents:
            return f"No research content found for {issue_key}"

        # Index to ChromaDB
        indexed = 0
        if is_chroma_available() and is_embedding_available():
            embeddings = embed_texts(all_documents)
            if embeddings is not None:
                success = add_documents(
                    "research_cache",
                    ids=all_ids,
                    documents=all_documents,
                    metadatas=all_metadatas,
                    embeddings=[e.tolist() for e in embeddings],
                )
                if success:
                    indexed = len(all_documents)

        return f"""
RESEARCH + INDEX for {issue_key}
{'='*50}
Issue:   {summary[:80]}
Labels:  {', '.join(labels) or 'None'}
Queries: {len(queries)}

Search results:
{chr(10).join(search_log)}

Indexed: {indexed} chunks into research_cache

{'='*50}
✅ RAG updated for {issue_key}
Now run: generate_dita_from_jira('{issue_key}')

The generation will use:
→ Your DITA spec RAG (ChromaDB)
→ Your Experience League RAG (ChromaDB)
→ This fresh research (research_cache)
→ Expert DITA examples (dita_examples)
"""

    except ImportError:
        return "❌ tavily-python not installed. Run: pip install tavily-python"
    except Exception as e:
        return f"❌ Research + index failed: {e}"


@mcp.tool()
def show_rag_index_status() -> str:
    """
    Show what research has been indexed into RAG and when.
    See which topics are fresh vs need refresh.
    """
    log = _load_index_log()

    if not log:
        return (
            "No research indexed yet.\n"
            "Run auto_index_research_to_rag() to populate."
        )

    lines = [
        "RAG Research Index Status",
        "=" * 50,
        f"Total topics indexed: {len(log)}",
        "",
    ]

    now = datetime.utcnow()
    fresh   = []
    stale   = []
    missing = []

    for topic in AUTO_RESEARCH_TOPICS:
        tid = topic["id"]
        if tid in log:
            entry = log[tid]
            try:
                dt   = datetime.fromisoformat(entry["indexed_at"])
                days = (now - dt).days
                info = (
                    f"{'✅' if days < 7 else '⚠️ '} {tid}\n"
                    f"   Indexed: {days} days ago | "
                    f"Chunks: {entry.get('chunks', '?')}"
                )
                if days < 7:
                    fresh.append(info)
                else:
                    stale.append(info)
            except Exception:
                missing.append(f"❓ {tid} — date parse error")
        else:
            missing.append(f"❌ {tid} — not indexed yet")

    if fresh:
        lines.append("FRESH (indexed < 7 days ago):")
        lines.extend(fresh)
        lines.append("")

    if stale:
        lines.append("STALE (needs refresh):")
        lines.extend(stale)
        lines.append("")

    if missing:
        lines.append("NOT INDEXED:")
        lines.extend(missing)
        lines.append("")

    lines.append("=" * 50)
    if stale or missing:
        lines.append(
            "Run auto_index_research_to_rag() to refresh stale topics\n"
            "Run auto_index_research_to_rag(force=True) to re-index all"
        )
    else:
        lines.append("✅ All topics fresh — RAG is up to date!")

    return "\n".join(lines)
