# mcp_server.py
# Place at: C:\Users\prashantp\Videos\aem-guides-dataset-studio\mcp_server.py

import sys
import os
from pathlib import Path

# ── Resolve both import styles used across your codebase ─────────────────────
# Some files use `from app.xxx`, others use `from backend.app.xxx`
# Adding both roots means both styles resolve correctly at runtime.
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"

for p in [str(PROJECT_ROOT), str(BACKEND_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)
# ─────────────────────────────────────────────────────────────────────────────

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("aem-dataset-studio")

# All imports are lazy (inside each tool function) so a single missing
# dependency never kills the entire MCP server — only that one tool fails.


# =============================================================================
# SECTION 1 — JIRA TOOLS
# =============================================================================

@mcp.tool()
def get_jira_issue(issue_key: str) -> str:
    """
    Fetch a single Jira issue by key (e.g. AEM-123).
    Returns summary, description, type, status, labels, priority.
    Use as the first step before generating DITA for a specific issue.
    """
    try:
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue
        jira = JiraClient()
        issue = jira.get_issue(issue_key)
        fields = issue.get("fields", {})
        description = extract_description_from_issue(issue)
        return f"""
Issue Key:   {issue.get('key')}
Summary:     {fields.get('summary', '')}
Type:        {fields.get('issuetype', {}).get('name', '')}
Status:      {fields.get('status', {}).get('name', '')}
Priority:    {fields.get('priority', {}).get('name', 'N/A')}
Labels:      {', '.join(fields.get('labels', [])) or 'None'}

Description:
{description}
"""
    except Exception as e:
        return f"Error fetching {issue_key}: {e}"


@mcp.tool()
def get_jira_issue_with_comments(issue_key: str) -> str:
    """
    Fetch a Jira issue AND all its comments in one call.
    Richer context for DITA generation — use when description alone is thin.
    """
    try:
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue
        jira = JiraClient()
        issue = jira.get_issue(issue_key)
        fields = issue.get("fields", {})
        description = extract_description_from_issue(issue)
        comments = jira.get_issue_comments(issue_key)

        comment_lines = []
        for c in comments:
            comment_lines.append(
                f"[{c.get('created', '')}] {c.get('author', 'Unknown')}:\n{c.get('body_text', '')}"
            )

        return f"""
Issue Key:   {issue.get('key')}
Summary:     {fields.get('summary', '')}
Type:        {fields.get('issuetype', {}).get('name', '')}
Status:      {fields.get('status', {}).get('name', '')}
Priority:    {fields.get('priority', {}).get('name', 'N/A')}
Labels:      {', '.join(fields.get('labels', [])) or 'None'}

Description:
{description}

Comments ({len(comments)}):
{chr(10).join(comment_lines) if comment_lines else 'No comments.'}
"""
    except Exception as e:
        return f"Error fetching {issue_key} with comments: {e}"


@mcp.tool()
def search_jira_issues(jql: str, max_results: int = 20) -> str:
    """
    Search Jira using JQL with full fields for DITA analysis.
    Returns summary, description, labels, priority per issue.
    Example JQL: 'project = AEM AND issuetype = Story AND status = Done ORDER BY updated DESC'
    """
    try:
        from backend.app.services.jira_dita_fetch_service import fetch_jira_issues
        issues = fetch_jira_issues(jql, max_results=max_results, fetch_comments=False)
        if not issues:
            return "No issues found for the given JQL."

        lines = []
        for issue in issues:
            lines.append(f"""
--- {issue.get('issue_key')} ---
Summary:  {issue.get('summary', '')}
Status:   {issue.get('status', '')}
Priority: {issue.get('priority', 'N/A')}
Labels:   {', '.join(issue.get('labels', [])) or 'None'}
Desc:     {(issue.get('description') or '')[:300]}...
""")
        return f"Found {len(issues)} issues:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error searching Jira: {e}"


@mcp.tool()
def find_similar_jira_issues(query_text: str, k: int = 5, project_key: str = "") -> str:
    """
    Find Jira issues similar to a query using embedding or lexical search.
    Uses jira_similarity_service — requires issues to be indexed in DB first via index_jira_issues.
    query_text: free text, or paste a Jira summary/description
    project_key: optional project filter e.g. 'AEM'
    """
    try:
        from backend.app.services.jira_similarity_service import find_similar_issues
        from backend.app.db.session import SessionLocal

        session = SessionLocal()
        try:
            filters = {"project": project_key} if project_key else None
            results = find_similar_issues(
                session=session,
                query_text=query_text,
                k=k,
                filters=filters,
            )
        finally:
            session.close()

        if not results:
            return (
                "No similar issues found. Index issues first using index_jira_issues tool.\n"
                "Example: index_jira_issues('project = AEM AND updated >= -30d')"
            )

        lines = []
        for r in results:
            lines.append(f"""
--- {r.get('issue_key')} (score: {r.get('score', 0)}) ---
Summary:  {r.get('summary', '')}
Type:     {r.get('issue_type', '')}
Status:   {r.get('status', '')}
Desc:     {(r.get('description') or '')[:200]}...
""")
        return f"Found {len(results)} similar issues:\n" + "\n".join(lines)
    except Exception as e:
        return f"Error finding similar issues: {e}"


@mcp.tool()
def index_jira_issues(jql: str, limit: int = 100) -> str:
    """
    Index Jira issues into the local DB so find_similar_jira_issues works.
    Run this once before using similarity search.
    Example JQL: 'project = AEM AND updated >= -30d'
    """
    try:
        from backend.app.services.jira_index_service import index_recent_issues
        from backend.app.db.session import SessionLocal

        session = SessionLocal()
        try:
            result = index_recent_issues(session=session, jql=jql, limit=limit)
            session.commit()
        finally:
            session.close()

        return (
            f"✅ Indexed {result.get('indexed', 0)} of "
            f"{result.get('total_fetched', 0)} issues.\n"
            f"{result.get('error', '')}"
        )
    except Exception as e:
        return f"Error indexing issues: {e}"


# =============================================================================
# SECTION 2 — RAG TOOLS (Experience League + DITA Spec)
# =============================================================================

@mcp.tool()
def check_rag_status() -> str:
    """
    Check if RAG sources (Experience League + DITA spec PDFs) are indexed and ready.
    Always run this first before using RAG query tools.
    """
    try:
        from backend.app.services.doc_retriever_service import check_rag_readiness
        status = check_rag_readiness()
        return f"""
RAG Status:
  Experience League (AEM Guides): {'✅ Ready' if status['aem_guides_ready'] else '❌ Not indexed — run crawl_experience_league'}
  DITA Spec (1.2 / 1.3 PDFs):    {'✅ Ready' if status['dita_spec_ready'] else '❌ Not indexed — run index_dita_spec_pdfs'}
  Any ready:                       {'✅ Yes' if status['any_ready'] else '❌ No'}

{status['message']}
"""
    except Exception as e:
        return f"Error checking RAG status: {e}"


@mcp.tool()
def crawl_experience_league(urls: list = None) -> str:
    """
    Crawl and index AEM Guides docs from Experience League into the RAG knowledge base.
    Run this once to populate Experience League RAG. Takes 2-5 minutes.
    urls: optional list of specific URLs. Leave empty to use config/defaults.
    """
    try:
        from backend.app.services.crawl_service import crawl_and_index
        stats = crawl_and_index(urls=urls or None)
        return f"""
✅ Experience League Crawl Complete:
  Pages crawled:  {stats.get('pages_crawled', 0)}
  Chunks stored:  {stats.get('chunks_stored', 0)}
  Errors:         {len(stats.get('errors', []))}
{chr(10).join(stats.get('errors', [])) if stats.get('errors') else ''}
"""
    except Exception as e:
        return f"Error crawling Experience League: {e}"


@mcp.tool()
def index_dita_spec_pdfs() -> str:
    """
    Download and index DITA 1.2 and 1.3 spec PDFs into ChromaDB.
    Run this once to populate DITA spec RAG. Requires internet. Takes 2-5 minutes.
    """
    try:
        from backend.app.services.dita_pdf_index_service import index_dita_pdf
        stats = index_dita_pdf()
        return f"""
✅ DITA Spec PDF Indexing Complete:
  Pages loaded:    {stats.get('pages_loaded', 0)}
  Chunks stored:   {stats.get('chunks_stored', 0)}
  Sources indexed: {', '.join(stats.get('sources_indexed', [])) or 'None'}
  Errors:          {len(stats.get('errors', []))}
{chr(10).join(stats.get('errors', [])) if stats.get('errors') else ''}
"""
    except Exception as e:
        return f"Error indexing DITA spec PDFs: {e}"


@mcp.tool()
def query_experience_league(query: str, k: int = 5) -> str:
    """
    Semantic search over indexed Experience League (AEM Guides) documentation.
    Uses ChromaDB → embedding → lexical fallback automatically.
    Example: 'how to structure a task topic in AEM Guides'
    """
    try:
        from backend.app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        docs = retrieve_relevant_docs(query=query, k=k)
        if not docs:
            return "No docs found. Run crawl_experience_league first."
        return format_docs_for_prompt(docs)
    except Exception as e:
        return f"Error querying Experience League: {e}"


@mcp.tool()
def query_dita_spec(query: str, k: int = 5) -> str:
    """
    Semantic search over indexed DITA 1.2/1.3 spec PDFs.
    Use to validate DITA element usage, nesting rules, required attributes.
    Example: 'task topic required elements', 'keyref vs conref difference'
    """
    try:
        from backend.app.services.dita_knowledge_retriever import retrieve_dita_knowledge
        chunks = retrieve_dita_knowledge(query_text=query, k=k)
        if not chunks:
            return "No DITA spec chunks found. Run index_dita_spec_pdfs first."

        parts = []
        for i, chunk in enumerate(chunks, 1):
            element = chunk.get("element_name") or ""
            source = chunk.get("source_url") or ""
            text = (chunk.get("text_content") or "")[:1500]
            header = f"[{i}] Element: {element} | {source}" if element else f"[{i}] {source}"
            parts.append(f"{header}\n{text}")
        return "\n\n".join(parts)
    except Exception as e:
        return f"Error querying DITA spec: {e}"


@mcp.tool()
def query_dita_graph(element_hint: str) -> str:
    """
    Query the DITA element graph for nesting rules and valid attributes.
    Use to check what elements can nest inside another before generating XML.
    Example: 'task steps cmd info stepresult', 'concept section nesting'
    """
    try:
        from backend.app.services.dita_knowledge_retriever import retrieve_dita_graph_knowledge
        result = retrieve_dita_graph_knowledge(element_hint=element_hint)
        if not result:
            return f"No graph data for: '{element_hint}'. DITA spec may not be indexed yet."
        return result
    except Exception as e:
        return f"Error querying DITA graph: {e}"


@mcp.tool()
def query_combined_context(query: str) -> str:
    """
    Query Experience League + DITA spec + element graph in ONE call.
    Best tool to call before generating any DITA — gives Cursor full grounded context.
    Always use this before asking Cursor to generate DITA XML.
    """
    try:
        from backend.app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        from backend.app.services.dita_knowledge_retriever import retrieve_dita_knowledge, retrieve_dita_graph_knowledge

        # Experience League
        el_docs = retrieve_relevant_docs(query=query, k=3)
        el_text = format_docs_for_prompt(el_docs) if el_docs else "❌ Not indexed. Run crawl_experience_league."

        # DITA spec
        spec_chunks = retrieve_dita_knowledge(query_text=query, k=3)
        if spec_chunks:
            spec_parts = []
            for i, chunk in enumerate(spec_chunks, 1):
                element = chunk.get("element_name") or ""
                source = chunk.get("source_url") or ""
                text = (chunk.get("text_content") or "")[:1000]
                header = f"[{i}] {element} | {source}" if element else f"[{i}] {source}"
                spec_parts.append(f"{header}\n{text}")
            spec_text = "\n\n".join(spec_parts)
        else:
            spec_text = "❌ Not indexed. Run index_dita_spec_pdfs."

        # DITA element graph
        graph_text = retrieve_dita_graph_knowledge(element_hint=query) or "No graph data available."

        return f"""
=== Experience League (AEM Guides Documentation) ===
{el_text}

=== DITA Spec 1.2 / 1.3 ===
{spec_text}

=== DITA Element Graph (Nesting + Attributes) ===
{graph_text}
"""
    except Exception as e:
        return f"Error querying combined context: {e}"


# =============================================================================
# SECTION 3 — JIRA → DITA ANALYSIS PIPELINE
# =============================================================================

@mcp.tool()
async def run_jira_dita_analysis_pipeline(jql: str, max_issues: int = 20) -> str:
    """
    Run the full Jira → DITA analysis pipeline on a set of issues.
    Pipeline: fetch → normalize → LLM analysis → dataset records → save to JSONL.
    Results saved to: backend/storage/datasets/jira_dita_analysis/records.jsonl
    Requires LLM configured via ANTHROPIC_API_KEY in .env
    Example JQL: 'project = AEM AND issuetype = Bug AND status = Done'
    """
    try:
        from backend.app.services.jira_dita_analysis_service import run_jira_dita_analysis
        result = await run_jira_dita_analysis(jql=jql, max_issues=max_issues, append=True)
        dist = result.get("categories_distribution", {})
        dist_lines = "\n".join(f"  {k}: {v}" for k, v in dist.items()) if dist else "  None"
        return f"""
✅ Jira → DITA Analysis Pipeline Complete:
  Issues processed: {result.get('records_count', 0)}
  Dataset path:     {result.get('dataset_path', '')}

Categories:
{dist_lines}
"""
    except Exception as e:
        return f"Error running pipeline: {e}"


# =============================================================================
# SECTION 4 — DITA FILE OUTPUT TOOLS
# =============================================================================

@mcp.tool()
def save_dita_file(filename: str, content: str) -> str:
    """
    Save generated DITA XML to output/dita/ in the project root.
    filename: e.g. 'AEM-123-task.dita' or 'AEM-123.ditamap'
    content: full DITA XML string
    Call enrich_dita_output after saving to ensure spec compliance.
    """
    try:
        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        return f"✅ Saved: {filepath}"
    except Exception as e:
        return f"Error saving {filename}: {e}"


@mcp.tool()
def save_dita_files(files: dict) -> str:
    """
    Save multiple DITA files at once.
    files: dict of filename → XML content
    e.g. {'AEM-123-task.dita': '<?xml...', 'AEM-123.ditamap': '<?xml...'}
    """
    try:
        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for filename, content in files.items():
            filepath = output_dir / filename
            filepath.write_text(content, encoding="utf-8")
            saved.append(filename)
        return f"✅ Saved {len(saved)} files:\n" + "\n".join(saved)
    except Exception as e:
        return f"Error saving files: {e}"


@mcp.tool()
def enrich_dita_output() -> str:
    """
    Run DITA enrichment on all files in output/dita/:
    Adds missing <shortdesc> and <prolog><metadata> to all topic files.
    Always call this after save_dita_file to ensure spec-compliant output.
    """
    try:
        from backend.app.services.dita_enrichment_service import enrich_dita_folder
        output_dir = PROJECT_ROOT / "output" / "dita"
        if not output_dir.exists():
            return "No output/dita/ directory. Save DITA files first using save_dita_file."
        stats = enrich_dita_folder(output_dir)
        return f"""
✅ DITA Enrichment Complete:
  Topics processed:  {stats['topics_processed']}
  shortdesc added:   {stats['shortdesc_added']}
  prolog added:      {stats['prolog_added']}
  Errors:            {len(stats['errors'])}
{chr(10).join(stats['errors']) if stats['errors'] else ''}
"""
    except Exception as e:
        return f"Error enriching DITA output: {e}"


@mcp.tool()
def list_dita_files() -> str:
    """List all generated DITA files in output/dita/."""
    try:
        output_dir = PROJECT_ROOT / "output" / "dita"
        if not output_dir.exists():
            return "No output/dita/ directory yet."
        files = sorted(f for f in output_dir.rglob("*") if f.is_file())
        if not files:
            return "No DITA files yet."
        return "\n".join(str(f.relative_to(PROJECT_ROOT)) for f in files)
    except Exception as e:
        return f"Error listing files: {e}"


@mcp.tool()
def read_dita_file(filename: str) -> str:
    """
    Read an existing DITA file from output/dita/ for review or refinement.
    filename: e.g. 'AEM-123-task.dita'
    """
    try:
        filepath = PROJECT_ROOT / "output" / "dita" / filename
        if not filepath.exists():
            return f"File not found: {filename}. Use list_dita_files to see available files."
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading {filename}: {e}"


if __name__ == "__main__":
    mcp.run()
