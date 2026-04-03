# =============================================================================
# SECTION 9 — AGENTIC MCP TOOLS
# Add to mcp_server.py above if __name__ == "__main__":
# =============================================================================

@mcp.tool()
async def run_aem_release_agent() -> str:
    """
    AGENTIC TOOL — Checks for new AEM Guides releases and
    automatically indexes them into RAG if found.

    This is the core agentic loop:
    1. Checks OASIS + Experience League for new content
    2. If changed → runs Tavily research
    3. Indexes everything into ChromaDB
    4. Re-crawls Experience League pages
    5. Future DITA generation uses latest docs automatically

    Run manually or let the scheduler trigger it every 6 hours.
    """
    try:
        from backend.app.services.aem_release_agent import run_aem_release_agent
        result = await run_aem_release_agent()

        action  = result.get("action", "unknown")
        version = result.get("version", "unknown")

        if action == "no_action":
            return f"""
AEM Release Agent — No action needed
{'='*50}
Status:  No new AEM release detected
Checked: {result.get('checked_at', '')}
RAG:     Already up to date

Run again later or use force_reindex_rag() to refresh anyway.
"""

        return f"""
AEM Release Agent — New Release Indexed!
{'='*50}
Version detected:    {version}
Changed pages:       {len(result.get('changed_urls', []))}
Research chunks:     {result.get('tavily_indexed', 0)} indexed via Tavily
Experience League:   {result.get('crawl_chunks', 0)} chunks re-crawled
Errors:              {len(result.get('errors', []))}

{chr(10).join(result.get('errors', [])) if result.get('errors') else ''}

✅ RAG updated with AEM Guides {version} documentation.
Future DITA generation will use the latest release notes,
new features, and updated authoring patterns automatically.

Message: {result.get('message', '')}
"""

    except Exception as e:
        return f"Agent error: {e}"


@mcp.tool()
async def force_reindex_rag() -> str:
    """
    Force re-index ALL RAG sources regardless of whether
    new content was detected.

    Use this when:
    - You want to manually refresh RAG
    - After adding new DITA example repos
    - Before a big batch generation session
    - When generation quality seems stale

    Runs:
    1. Tavily research on all DITA/AEM topics
    2. Experience League re-crawl
    3. DITA spec PDF re-index
    """
    try:
        from backend.app.services.aem_release_agent import auto_index_new_release
        from backend.app.services.crawl_service import crawl_and_index
        from backend.app.services.dita_pdf_index_service import index_dita_pdf

        results = []

        # Tavily research
        index_result = await auto_index_new_release(version=None)
        results.append(
            f"✅ Tavily: {index_result.get('tavily_indexed', 0)} chunks indexed"
        )
        results.append(
            f"✅ Experience League: {index_result.get('crawl_chunks', 0)} chunks"
        )

        # Re-index DITA spec PDFs
        try:
            pdf_stats = index_dita_pdf()
            results.append(
                f"✅ DITA Spec PDFs: {pdf_stats.get('chunks_stored', 0)} chunks"
            )
        except Exception as e:
            results.append(f"⚠️ DITA PDF index: {str(e)[:60]}")

        return f"""
Force Re-index Complete
{'='*50}
{chr(10).join(results)}

All RAG sources refreshed.
Next DITA generation will use fully updated knowledge.
"""

    except Exception as e:
        return f"Force reindex error: {e}"


@mcp.tool()
def get_agent_status() -> str:
    """
    Show current state of the agentic pipeline:
    - Last AEM release detected
    - Last auto-index timestamp
    - What was indexed
    - Next scheduled run
    """
    try:
        from backend.app.services.aem_release_agent import get_agent_status
        status = get_agent_status()

        last_detected = status.get("last_release_detected", "Never")
        last_version  = status.get("last_version", "Unknown")
        last_indexed  = status.get("last_auto_index", "Never")
        index_results = status.get("last_auto_index_results", {})

        return f"""
Agentic Pipeline Status
{'='*50}
Last release detected:  {last_detected}
Last version:           {last_version}
Last auto-index:        {last_indexed}

Last index results:
  Tavily chunks:        {index_results.get('tavily_chunks', 0)}
  Crawl chunks:         {index_results.get('crawl_chunks', 0)}

Monitoring:
  URLs monitored:       {status.get('monitored_urls', 0)}
  Index topics:         {status.get('index_topics', 0)}

Schedule: Every 6 hours (AEM_RELEASE_AGENT_CRON in .env)

Triggers available:
  1. Scheduled    → automatic every 6 hours
  2. Webhook      → POST /api/v1/agent/aem-release
  3. Manual       → run_aem_release_agent() here
  4. Force        → force_reindex_rag()
"""

    except Exception as e:
        return f"Status error: {e}"
