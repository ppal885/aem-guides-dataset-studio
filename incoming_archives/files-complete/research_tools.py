# =============================================================================
# SECTION 7 — RESEARCH TOOLS (Tavily AI Search)
# Add these to mcp_server.py above if __name__ == "__main__":
#
# Setup:
#   1. Get free API key: https://tavily.com (1000 searches/month free)
#   2. Add to .env: TAVILY_API_KEY=tvly-xxxxxxxxxxxx
#   3. pip install tavily-python
# =============================================================================

import os

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Known authoritative sources for DITA/AEM content
DITA_TRUSTED_SOURCES = [
    "docs.oasis-open.org",
    "experienceleague.adobe.com",
    "helpx.adobe.com",
    "dita-ot.org",
    "github.com/oasis-tcs",
]


def _get_tavily_client():
    """Get Tavily client. Raises clear error if not configured."""
    if not TAVILY_API_KEY:
        raise ValueError(
            "TAVILY_API_KEY not set in .env\n"
            "Get free key at: https://tavily.com\n"
            "Then add: TAVILY_API_KEY=tvly-xxxx to your .env"
        )
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=TAVILY_API_KEY)
    except ImportError:
        raise ImportError(
            "tavily-python not installed.\n"
            "Run: pip install tavily-python"
        )


@mcp.tool()
def research_dita_spec(query: str, max_results: int = 5) -> str:
    """
    Search OASIS DITA specification website for latest spec rules.
    Searches docs.oasis-open.org for DITA 1.2, 1.3, and 2.0 content.

    Use this when:
    - You need the latest DITA element rules
    - Validating element nesting or attributes
    - Checking if something changed in recent spec versions

    query: e.g. 'keyref resolution keyscope DITA 1.3'
            or 'task topic required elements'
            or 'conref push mechanism'
    """
    try:
        client = _get_tavily_client()

        # Focus search on OASIS and DITA spec sites
        result = client.search(
            query=f"DITA specification {query}",
            search_depth="advanced",
            include_domains=["docs.oasis-open.org", "dita-ot.org", "github.com/oasis-tcs"],
            max_results=max_results,
            include_answer=True,
        )

        return _format_research_result(
            result,
            title=f"DITA Spec Research: {query}",
            source_type="OASIS DITA Specification",
        )

    except Exception as e:
        return f"Research error: {e}"


@mcp.tool()
def research_aem_guides(query: str, max_results: int = 5) -> str:
    """
    Search Adobe Experience League for latest AEM Guides documentation.
    Searches experienceleague.adobe.com for current AEM Guides content.

    Use this when:
    - You need current AEM Guides features or behavior
    - Checking release notes for a specific version
    - Finding AEM-specific DITA authoring patterns
    - Looking for AEM Guides API documentation

    query: e.g. 'AEM Guides 4.2 release notes'
            or 'keyref resolution AEM Guides'
            or 'DITA map publishing AEM'
    """
    try:
        client = _get_tavily_client()

        result = client.search(
            query=f"AEM Guides Adobe {query}",
            search_depth="advanced",
            include_domains=[
                "experienceleague.adobe.com",
                "helpx.adobe.com",
                "adobe.com",
            ],
            max_results=max_results,
            include_answer=True,
        )

        return _format_research_result(
            result,
            title=f"AEM Guides Research: {query}",
            source_type="Adobe Experience League",
        )

    except Exception as e:
        return f"Research error: {e}"


@mcp.tool()
def research_for_jira_issue(issue_key: str, custom_query: str = "") -> str:
    """
    Research web content relevant to a Jira issue.
    Automatically builds search query from issue content.
    Searches DITA spec + AEM Guides + technical articles.

    Useful for:
    - Finding known solutions for reported bugs
    - Understanding the technical context of an issue
    - Finding examples of the problematic DITA construct
    - Getting latest release notes that address the issue

    issue_key:    e.g. 'AEM-456'
    custom_query: optional extra search terms
    """
    try:
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue

        # Fetch issue for context
        jira = JiraClient()
        raw = jira.get_issue(issue_key)
        fields = raw.get("fields", {})
        summary = fields.get("summary", "")
        description = extract_description_from_issue(raw)
        labels = fields.get("labels", [])

        # Build smart search query from issue content
        query_parts = [summary[:100]]
        if labels:
            query_parts.extend(labels[:3])
        if custom_query:
            query_parts.append(custom_query)

        query = " ".join(query_parts)

        client = _get_tavily_client()

        # Search across DITA + AEM sources
        result = client.search(
            query=f"AEM Guides DITA {query}",
            search_depth="advanced",
            include_domains=DITA_TRUSTED_SOURCES,
            max_results=5,
            include_answer=True,
        )

        output = [
            f"Research for {issue_key}: {summary[:60]}",
            f"Search query: {query[:100]}",
            "=" * 60,
        ]
        output.append(_format_research_result(
            result,
            title=f"Web Research for {issue_key}",
            source_type="DITA/AEM Sources",
        ))

        # Suggest indexing if useful content found
        if result.get("results"):
            output.append(
                "\n💡 Tip: Run research_and_index_to_rag() to add "
                "this content to your RAG knowledge base"
            )

        return "\n".join(output)

    except Exception as e:
        return f"Research error for {issue_key}: {e}"


@mcp.tool()
def research_aem_release_notes(version: str = "") -> str:
    """
    Search for latest AEM Guides release notes.
    Finds what changed, what bugs were fixed, new features.

    version: e.g. '4.2', '4.3', '2024.2' — leave empty for latest
    """
    try:
        client = _get_tavily_client()

        query = f"AEM Guides release notes {version}".strip()

        result = client.search(
            query=query,
            search_depth="advanced",
            include_domains=[
                "experienceleague.adobe.com",
                "helpx.adobe.com",
            ],
            max_results=5,
            include_answer=True,
        )

        return _format_research_result(
            result,
            title=f"AEM Guides Release Notes {version}".strip(),
            source_type="Adobe Experience League",
        )

    except Exception as e:
        return f"Release notes research error: {e}"


@mcp.tool()
def research_and_index_to_rag(query: str, topic: str = "general") -> str:
    """
    Research a topic AND index the results into your ChromaDB RAG.
    This makes future DITA generation smarter for this topic.

    Steps:
    1. Searches Tavily for relevant content
    2. Embeds the results using your sentence-transformers model
    3. Stores in ChromaDB collection 'research_cache'
    4. Future query_combined_context() calls will include this

    query: search query
    topic: category tag e.g. 'dita-spec', 'aem-guides', 'release-notes'
    """
    try:
        client = _get_tavily_client()

        result = client.search(
            query=f"DITA AEM {query}",
            search_depth="advanced",
            include_domains=DITA_TRUSTED_SOURCES,
            max_results=5,
            include_answer=True,
        )

        raw_results = result.get("results", [])
        if not raw_results:
            return "No results found to index."

        # Prepare documents for ChromaDB
        from backend.app.services.embedding_service import embed_texts, is_embedding_available
        from backend.app.services.vector_store_service import add_documents, is_chroma_available

        if not is_chroma_available():
            return "ChromaDB not available — results shown but not indexed.\n" + \
                   _format_research_result(result, query, "Web")

        if not is_embedding_available():
            return "Embedding model not available — results shown but not indexed.\n" + \
                   _format_research_result(result, query, "Web")

        documents = []
        metadatas = []
        ids       = []

        for i, r in enumerate(raw_results):
            content = f"{r.get('title', '')}\n{r.get('content', '')}"
            if len(content.strip()) < 50:
                continue
            documents.append(content[:4000])
            metadatas.append({
                "url":   r.get("url", ""),
                "title": r.get("title", ""),
                "topic": topic,
                "query": query[:100],
                "source": "tavily_research",
            })
            ids.append(f"research_{topic}_{i}_{hash(r.get('url', str(i))) % 100000}")

        if not documents:
            return "No indexable content found."

        embeddings = embed_texts(documents)
        if embeddings is None:
            return "Embedding failed."

        success = add_documents(
            "research_cache",
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=[e.tolist() for e in embeddings],
        )

        status = "✅ Indexed" if success else "⚠️ Index failed"

        return f"""
{status} {len(documents)} research results into RAG (collection: research_cache)
Topic tag: {topic}
Query: {query}

{_format_research_result(result, f'Research: {query}', 'Web')}
"""

    except Exception as e:
        return f"Research + index error: {e}"


@mcp.tool()
def query_research_cache(query: str, k: int = 3) -> str:
    """
    Search previously researched content from Tavily that was indexed into RAG.
    Faster than live web search — uses your local ChromaDB.

    Use this to retrieve previously researched content
    without making a new web search API call.
    """
    try:
        from backend.app.services.embedding_service import embed_query, is_embedding_available
        from backend.app.services.vector_store_service import query_collection, is_chroma_available

        if not is_chroma_available() or not is_embedding_available():
            return "ChromaDB or embedding not available."

        q_emb = embed_query(query)
        if q_emb is None:
            return "Embedding failed."

        rows = query_collection(
            "research_cache",
            query_embedding=q_emb.tolist(),
            k=k,
        )

        if not rows:
            return (
                "No cached research found for this query.\n"
                "Run research_and_index_to_rag() to populate the cache."
            )

        parts = []
        for i, row in enumerate(rows, 1):
            meta = row.get("metadata") or {}
            doc  = row.get("document") or ""
            parts.append(
                f"[{i}] {meta.get('title', 'Untitled')}\n"
                f"     {meta.get('url', '')}\n"
                f"     Topic: {meta.get('topic', 'general')}\n\n"
                f"{doc[:1000]}"
            )

        return f"Cached research for '{query}':\n\n" + "\n\n---\n\n".join(parts)

    except Exception as e:
        return f"Cache query error: {e}"


# ── Formatter helper ──────────────────────────────────────────────────────────

def _format_research_result(result: dict, title: str, source_type: str) -> str:
    """Format Tavily search result for Cursor consumption."""
    lines = [f"=== {title} ===", f"Source: {source_type}", ""]

    # AI-generated answer (best summary)
    answer = result.get("answer", "")
    if answer:
        lines.append("SUMMARY:")
        lines.append(answer)
        lines.append("")

    # Individual results
    raw_results = result.get("results", [])
    if raw_results:
        lines.append(f"SOURCES ({len(raw_results)} found):")
        for i, r in enumerate(raw_results, 1):
            url     = r.get("url", "")
            rtitle  = r.get("title", "")
            content = r.get("content", "")[:500]
            score   = r.get("score", 0)
            lines.append(f"""
[{i}] {rtitle}
     {url}
     Relevance: {score:.2f}
     {content}
""")

    if not answer and not raw_results:
        lines.append("No results found.")

    return "\n".join(lines)
