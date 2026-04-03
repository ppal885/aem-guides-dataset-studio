# mcp_server.py
# Place at: C:\Users\prashantp\Videos\aem-guides-dataset-studio\mcp_server.py
import os
import sys
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


def _load_env_files() -> None:
    """Load project and backend env files so MCP tools match backend runtime config."""
    env_files = [
        PROJECT_ROOT / ".env",
        BACKEND_DIR / ".env",
    ]
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file, override=True)


_load_env_files()

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("aem-dataset-studio")

# Same resolution as backend tavily_search_service.get_tavily_api_key()
TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or os.getenv("TAVILY_KEY") or "").strip()

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


# ─────────────────────────────────────────────────────────────────────────────
# ADD THESE TWO TOOLS TO YOUR mcp_server.py
# These clone the DITAWriter GitHub repos and index them as RAG examples
# ─────────────────────────────────────────────────────────────────────────────

# Known DITAWriter repos — best public DITA examples available
DITA_EXAMPLE_REPOS = [
    {
        "url": "https://github.com/DITAWriter/pilot_training_mitchell_bomber",
        "name": "pilot_training_mitchell_bomber",
        "description": "Full DITA book — tasks, concepts, references, maps, reltables, conrefs",
    },
    {
        "url": "https://github.com/DITAWriter/dita_keys_examples",
        "name": "dita_keys_examples",
        "description": "Key definitions, keyrefs, keyscopes — exactly what AEM Guides needs",
    },
    {
        "url": "https://github.com/DITAWriter/dita_glossary_example",
        "name": "dita_glossary_example",
        "description": "Glossary entries, glossary maps, abbreviated-form usage",
    },
]

DITA_EXAMPLES_DIR = PROJECT_ROOT / "dita_examples" / "community"


@mcp.tool()
def clone_dita_example_repos() -> str:
    """
    Clone the DITAWriter GitHub repos as gold-standard DITA examples.
    These are expert-authored, spec-compliant DITA files covering:
    - pilot_training_mitchell_bomber: full book with tasks/concepts/refs/maps/reltables/conrefs
    - dita_keys_examples: keydefs, keyrefs, keyscopes (critical for AEM Guides)
    - dita_glossary_example: glossary entries, maps, abbreviated-form

    Clones to: dita_examples/community/ in your project root.
    Run once, then call index_dita_example_repos to index them.
    Requires git to be installed and internet access.
    """
    import subprocess

    DITA_EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    for repo in DITA_EXAMPLE_REPOS:
        target = DITA_EXAMPLES_DIR / repo["name"]

        # If already cloned, pull latest instead
        if target.exists():
            try:
                result = subprocess.run(
                    ["git", "-C", str(target), "pull", "--depth=1"],
                    capture_output=True, text=True, timeout=60
                )
                if result.returncode == 0:
                    results.append(f"✅ Updated: {repo['name']}")
                else:
                    results.append(f"⚠️ Update failed {repo['name']}: {result.stderr[:100]}")
            except Exception as e:
                results.append(f"⚠️ Pull failed {repo['name']}: {e}")
            continue

        # Fresh clone
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", repo["url"], str(target)],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0:
                # Count DITA files
                dita_count = len(list(target.rglob("*.dita"))) + len(list(target.rglob("*.ditamap")))
                results.append(f"✅ Cloned: {repo['name']} ({dita_count} DITA files) — {repo['description']}")
            else:
                results.append(f"❌ Clone failed {repo['name']}: {result.stderr[:200]}")
        except FileNotFoundError:
            return "❌ git not found. Install git: https://git-scm.com/download/win"
        except subprocess.TimeoutExpired:
            results.append(f"⏱️ Timeout cloning {repo['name']} — check internet connection")
        except Exception as e:
            results.append(f"❌ Error cloning {repo['name']}: {e}")

    summary = "\n".join(results)
    total_dita = sum(
        len(list((DITA_EXAMPLES_DIR / r["name"]).rglob("*.dita"))) +
        len(list((DITA_EXAMPLES_DIR / r["name"]).rglob("*.ditamap")))
        for r in DITA_EXAMPLE_REPOS
        if (DITA_EXAMPLES_DIR / r["name"]).exists()
    )

    return f"""
{summary}

Total DITA files available: {total_dita}
Location: {DITA_EXAMPLES_DIR}

Next step: run index_dita_example_repos to index these into ChromaDB.
"""


@mcp.tool()
def index_dita_example_repos(repo_name: str = "") -> str:
    """
    Index cloned DITAWriter DITA examples into ChromaDB collection 'dita_examples'.
    Must run clone_dita_example_repos first.

    repo_name: optional — index just one repo e.g. 'dita_keys_examples'
               Leave empty to index ALL cloned repos.

    After indexing, query_dita_examples will return real expert DITA patterns
    grounded in the same constructs as your Jira issues.
    """
    try:
        from backend.app.services.embedding_service import embed_texts_batched, embed_texts, is_embedding_available
        from backend.app.services.vector_store_service import (
            add_documents, delete_collection, is_chroma_available
        )

        if not DITA_EXAMPLES_DIR.exists():
            return "No repos cloned yet. Run clone_dita_example_repos first."

        # Decide which repos to index
        if repo_name:
            target_dirs = [DITA_EXAMPLES_DIR / repo_name]
            if not target_dirs[0].exists():
                available = [r["name"] for r in DITA_EXAMPLE_REPOS]
                return f"Repo '{repo_name}' not found. Available: {', '.join(available)}"
        else:
            target_dirs = [
                DITA_EXAMPLES_DIR / r["name"]
                for r in DITA_EXAMPLE_REPOS
                if (DITA_EXAMPLES_DIR / r["name"]).exists()
            ]

        if not target_dirs:
            return "No repos found. Run clone_dita_example_repos first."

        documents, metadatas, ids = [], [], []
        skipped = 0

        for repo_dir in target_dirs:
            repo = repo_dir.name
            dita_files = (
                    list(repo_dir.rglob("*.dita")) +
                    list(repo_dir.rglob("*.ditamap"))
            )

            for i, f in enumerate(dita_files):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace").strip()
                except Exception:
                    skipped += 1
                    continue

                if not content or len(content) < 50:
                    skipped += 1
                    continue

                # Detect topic type from root element
                topic_type = "unknown"
                for t in ["task", "concept", "reference", "glossentry", "glossmap", "map", "bookmap"]:
                    if f"<{t}" in content[:300]:
                        topic_type = t
                        break

                # Detect key DITA constructs present in this file
                constructs = []
                for c in ["conref", "keyref", "keydef", "keyscope", "reltable",
                          "topicgroup", "mapref", "abbreviated-form", "glossterm"]:
                    if c in content:
                        constructs.append(c)

                documents.append(content[:8000])
                metadatas.append({
                    "filename": f.name,
                    "repo": repo,
                    "topic_type": topic_type,
                    "constructs": ",".join(constructs),  # searchable
                    "relative_path": str(f.relative_to(DITA_EXAMPLES_DIR)),
                    "source": "dita_expert_example",
                })
                ids.append(f"ditaex_{repo}_{i}")

        if not documents:
            return f"No readable DITA files found in {[d.name for d in target_dirs]}"

        # Embed in batches (these repos can have 100+ files)
        if not is_embedding_available():
            return f"Found {len(documents)} files but embedding model not available."

        if not is_chroma_available():
            return f"Found {len(documents)} files but ChromaDB not available."

        embeddings = (
            embed_texts_batched(documents)
            if len(documents) > 64
            else embed_texts(documents)
        )

        if embeddings is None:
            return "Embedding failed."

        # Full replace of the collection
        delete_collection("dita_examples")
        success = add_documents(
            "dita_examples",
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=[e.tolist() for e in embeddings],
        )

        if not success:
            return "ChromaDB add_documents failed."

        # Summary by repo
        repo_counts = {}
        for m in metadatas:
            repo_counts[m["repo"]] = repo_counts.get(m["repo"], 0) + 1

        repo_summary = "\n".join(f"  {r}: {c} files" for r, c in repo_counts.items())
        topic_counts = {}
        for m in metadatas:
            topic_counts[m["topic_type"]] = topic_counts.get(m["topic_type"], 0) + 1
        topic_summary = "\n".join(f"  {t}: {c}" for t, c in sorted(topic_counts.items()))

        return f"""
✅ DITA Examples Indexed Successfully:

By repo:
{repo_summary}

By topic type:
{topic_summary}

Total indexed: {len(documents)} files
Skipped:       {skipped} files (empty/unreadable)

Now use query_dita_examples in your generation prompts!
"""

    except Exception as e:
        return f"Error indexing DITA examples: {e}"


@mcp.tool()
def query_dita_examples(
        query: str,
        topic_type: str = "",
        construct: str = "",
        k: int = 3,
) -> str:
    """
    Search expert DITAWriter examples for patterns matching your query.
    Returns real DITA XML you can use as generation reference.

    query: e.g. 'task with multiple steps and conref'
    topic_type: filter by type — 'task', 'concept', 'reference', 'map', 'glossentry'
    construct: filter by DITA feature — 'keyref', 'conref', 'keyscope', 'reltable',
               'topicgroup', 'mapref', 'abbreviated-form'
    k: number of examples to return (default 3)

    Use this BEFORE generating DITA so Cursor has a real expert pattern to follow.
    """
    try:
        from backend.app.services.embedding_service import embed_query, is_embedding_available
        from backend.app.services.vector_store_service import query_collection, is_chroma_available

        if not is_chroma_available():
            return "ChromaDB not available."
        if not is_embedding_available():
            return "Embedding model not available."

        query_emb = embed_query(query)
        if query_emb is None:
            return "Embedding failed."

        # Build ChromaDB where filter
        where = None
        if topic_type and construct:
            where = {
                "$and": [
                    {"topic_type": {"$eq": topic_type}},
                    {"constructs": {"$contains": construct}},
                ]
            }
        elif topic_type:
            where = {"topic_type": {"$eq": topic_type}}
        elif construct:
            where = {"constructs": {"$contains": construct}}

        rows = query_collection(
            "dita_examples",
            query_embedding=query_emb.tolist(),
            k=k,
            where=where,
        )

        if not rows:
            msg = "No matching examples found."
            if topic_type or construct:
                msg += f" Try without filters (topic_type='{topic_type}', construct='{construct}')."
            msg += " Run clone_dita_example_repos + index_dita_example_repos first."
            return msg

        parts = []
        for i, row in enumerate(rows, 1):
            meta = row.get("metadata") or {}
            doc = row.get("document") or ""
            constructs_found = meta.get("constructs", "")
            parts.append(
                f"[{i}] {meta.get('filename')} "
                f"| type: {meta.get('topic_type')} "
                f"| repo: {meta.get('repo')}"
                f"{' | constructs: ' + constructs_found if constructs_found else ''}\n\n"
                f"{doc[:3000]}"
                f"{'...[truncated]' if len(doc) > 3000 else ''}"
            )

        return "\n\n{'─'*60}\n\n".join(parts)

    except Exception as e:
        return f"Error querying DITA examples: {e}"


@mcp.tool()
def list_dita_example_repos() -> str:
    """
    List all cloned DITAWriter repos and their DITA file counts.
    Shows what's available for indexing and querying.
    """
    if not DITA_EXAMPLES_DIR.exists():
        return "No repos cloned yet. Run clone_dita_example_repos first."

    lines = []
    total = 0
    for repo in DITA_EXAMPLE_REPOS:
        repo_dir = DITA_EXAMPLES_DIR / repo["name"]
        if not repo_dir.exists():
            lines.append(f"❌ {repo['name']} — not cloned yet")
            continue

        dita_files = list(repo_dir.rglob("*.dita"))
        map_files = list(repo_dir.rglob("*.ditamap"))
        total += len(dita_files) + len(map_files)

        # Count by type
        types = {}
        for f in dita_files:
            content = ""
            try:
                content = f.read_text(encoding="utf-8", errors="replace")[:300]
            except Exception:
                pass
            for t in ["task", "concept", "reference", "glossentry"]:
                if f"<{t}" in content:
                    types[t] = types.get(t, 0) + 1
                    break

        type_str = ", ".join(f"{t}:{c}" for t, c in types.items())
        lines.append(
            f"✅ {repo['name']}\n"
            f"   {repo['description']}\n"
            f"   Files: {len(dita_files)} .dita, {len(map_files)} .ditamap\n"
            f"   Types: {type_str or 'mixed'}"
        )

    return f"""
DITAWriter Example Repos:
{'─' * 50}
{chr(10).join(lines)}
{'─' * 50}
Total DITA files: {total}
Location: {DITA_EXAMPLES_DIR}
"""


@mcp.tool()
def validate_dita_file(filename: str) -> str:
    """
    Validate DITA XML structure and return specific errors.
    Cursor can read errors and auto-fix them — creates self-healing loop.
    """
    try:
        from lxml import etree
        filepath = PROJECT_ROOT / "output" / "dita" / filename
        content = filepath.read_text(encoding="utf-8")

        errors = []

        # 1. XML well-formedness
        try:
            root = etree.fromstring(content.encode("utf-8"))
        except etree.XMLSyntaxError as e:
            return f"❌ Not valid XML: {e}"

        # 2. Required element checks per topic type
        tag = root.tag
        REQUIRED = {
            "task":      ["title", "taskbody"],
            "concept":   ["title", "conbody"],
            "reference": ["title", "refbody"],
            "topic":     ["title", "body"],
            "glossentry":["glossterm", "glossdef"],
        }
        for required_child in REQUIRED.get(tag, []):
            if root.find(f".//{required_child}") is None:
                errors.append(f"Missing required element: <{required_child}>")

        # 3. Check id attribute on root
        if not root.get("id"):
            errors.append("Root element missing required 'id' attribute")

        # 4. Check steps → step → cmd chain for tasks
        if tag == "task":
            for step in root.findall(".//step"):
                if step.find("cmd") is None:
                    errors.append("<step> missing required <cmd> child")

        # 5. Check shortdesc
        if root.find(".//shortdesc") is None:
            errors.append("Missing <shortdesc> (recommended)")

        if errors:
            return "❌ Validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        return "✅ Valid DITA — all required elements present"

    except Exception as e:
        return f"Error validating {filename}: {e}"


@mcp.tool()
def validate_and_fix_dita(filename: str) -> str:
    """
    Validate a DITA file and if errors found, instruct Cursor to fix them.
    Cursor should call this, read the errors, fix the file,
    save again, and call this again until it returns ✅
    """
    result = validate_dita_file(filename)
    if "✅" in result:
        return result

    # Return errors + explicit fix instructions for Cursor
    return f"""
{result}

ACTION REQUIRED:
1. Call read_dita_file('{filename}') to see current content
2. Fix each error listed above
3. Call save_dita_file('{filename}', fixed_content)
4. Call validate_and_fix_dita('{filename}') again
Repeat until you see ✅
"""


PROMPTS_DIR = PROJECT_ROOT / "backend" / "app" / "templates" / "prompts"

@mcp.tool()
def list_prompt_templates() -> str:
    """List all prompt templates available in the project."""
    if not PROMPTS_DIR.exists():
        return "No prompts directory found."
    files = list(PROMPTS_DIR.glob("*.txt")) + list(PROMPTS_DIR.glob("*.md"))
    if not files:
        return "No prompt templates found."
    return "\n".join(f.name for f in files)


@mcp.tool()
def read_prompt_template(name: str) -> str:
    """
    Read a prompt template by filename.
    e.g. 'intent_extractor.txt' or 'jira_dita_analysis.txt'
    """
    path = PROMPTS_DIR / name
    if not path.exists():
        return f"Template not found: {name}"
    return path.read_text(encoding="utf-8")


@mcp.tool()
def save_prompt_template(name: str, content: str) -> str:
    """
    Save an improved prompt template.
    Use this after Cursor refines a prompt during generation.
    Cursor can read → improve → save back → better results next time.
    """
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROMPTS_DIR / name
    path.write_text(content, encoding="utf-8")
    return f"✅ Saved prompt template: {path}"


@mcp.tool()
def bundle_dita_package(
        package_name: str,
        include_subfolders: bool = True
) -> str:
    """
    Bundle all files in output/dita/ into a ZIP package ready for AEM upload.
    Creates: output/packages/<package_name>.zip
    includes all .dita, .ditamap, images, and a package manifest.
    """
    import zipfile
    import json
    from datetime import datetime

    output_dir = PROJECT_ROOT / "output" / "dita"
    packages_dir = PROJECT_ROOT / "output" / "packages"
    packages_dir.mkdir(parents=True, exist_ok=True)

    zip_path = packages_dir / f"{package_name}.zip"
    manifest = {
        "package_name": package_name,
        "created": datetime.utcnow().isoformat(),
        "files": []
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        pattern = "**/*" if include_subfolders else "*"
        for f in output_dir.glob(pattern):
            if f.is_file():
                arcname = f.relative_to(output_dir)
                zf.write(f, arcname)
                manifest["files"].append(str(arcname))

        # Add manifest
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    return f"""
✅ DITA Package Created:
  Path:  {zip_path}
  Files: {len(manifest['files'])}
  Size:  {zip_path.stat().st_size / 1024:.1f} KB

Files included:
{chr(10).join('  ' + f for f in manifest['files'])}
"""


@mcp.tool()
def mark_issue_generated(issue_key: str, dita_files: list, notes: str = "") -> str:
    """
    Record that DITA has been generated for a Jira issue.
    Prevents duplicate work and tracks generation history.
    """
    import json
    log_path = PROJECT_ROOT / "output" / "generation_log.json"

    log = {}
    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))

    from datetime import datetime
    log[issue_key] = {
        "generated_at": datetime.utcnow().isoformat(),
        "dita_files": dita_files,
        "notes": notes
    }
    log_path.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return f"✅ Logged generation for {issue_key}: {dita_files}"


@mcp.tool()
def check_issue_generated(issue_key: str) -> str:
    """
    Check if DITA has already been generated for a Jira issue.
    Use before processing to avoid duplicate generation.
    """
    import json
    log_path = PROJECT_ROOT / "output" / "generation_log.json"
    if not log_path.exists():
        return f"{issue_key}: Not generated yet"

    log = json.loads(log_path.read_text(encoding="utf-8"))
    if issue_key in log:
        entry = log[issue_key]
        return f"""
{issue_key}: Already generated ✅
  Generated at: {entry['generated_at']}
  Files: {', '.join(entry['dita_files'])}
  Notes: {entry.get('notes', 'none')}
"""
    return f"{issue_key}: Not generated yet"


@mcp.tool()
def list_generation_history() -> str:
    """List all Jira issues that have had DITA generated."""
    import json
    log_path = PROJECT_ROOT / "output" / "generation_log.json"
    if not log_path.exists():
        return "No generation history yet."

    log = json.loads(log_path.read_text(encoding="utf-8"))
    if not log:
        return "No generation history yet."

    lines = []
    for key, entry in sorted(log.items()):
        lines.append(
            f"{key} | {entry['generated_at'][:10]} | "
            f"{', '.join(entry['dita_files'])}"
        )
    return f"Generation History ({len(log)} issues):\n" + "\n".join(lines)


@mcp.tool()
def score_dita_quality(filename: str) -> str:
    """
    Score generated DITA on multiple dimensions.
    Returns score + specific improvement suggestions for Cursor to act on.
    """
    try:
        from lxml import etree
        filepath = PROJECT_ROOT / "output" / "dita" / filename
        content = filepath.read_text(encoding="utf-8")
        root = etree.fromstring(content.encode("utf-8"))
        tag = root.tag

        scores = {}
        suggestions = []

        # 1. Structure (30 pts)
        structure = 30
        if root.find(".//shortdesc") is None:
            structure -= 10
            suggestions.append("Add <shortdesc> — improves discoverability")
        if root.find(".//prolog") is None:
            structure -= 5
            suggestions.append("Add <prolog><metadata> — required for AEM")
        if not root.get("id"):
            structure -= 15
            suggestions.append("Add id attribute to root element")
        scores["Structure"] = structure

        # 2. Content richness (30 pts)
        richness = 0
        if root.find(".//example") is not None:
            richness += 10
        if root.find(".//note") is not None:
            richness += 5
        if root.find(".//codeblock") is not None:
            richness += 10
        if tag == "task" and root.find(".//context") is not None:
            richness += 5
        scores["Content Richness"] = richness

        # 3. DITA features used (20 pts)
        features = 0
        text = content
        if "keyref=" in text: features += 5
        if "conref=" in text: features += 5
        if "<xref" in text:   features += 5
        if "<fig" in text:    features += 5
        scores["DITA Features"] = features

        # 4. AEM readiness (20 pts)
        aem = 20
        if 'xml:lang' not in text:
            aem -= 5
            suggestions.append("Add xml:lang='en-US' to root element for AEM")
        if 'outputclass' not in text:
            aem -= 5
            suggestions.append("Consider adding outputclass for AEM styling")
        if len(content) < 500:
            aem -= 10
            suggestions.append("Content seems thin — add more detail")
        scores["AEM Readiness"] = aem

        total = sum(scores.values())
        score_lines = "\n".join(f"  {k}: {v}" for k, v in scores.items())
        suggestion_lines = "\n".join(f"  - {s}" for s in suggestions) if suggestions else "  None — great job!"

        grade = "🟢 Excellent" if total >= 80 else "🟡 Good" if total >= 60 else "🔴 Needs work"

        return f"""
DITA Quality Score: {total}/100 {grade}

Breakdown:
{score_lines}

Suggestions for Cursor to fix:
{suggestion_lines}
"""
    except Exception as e:
        return f"Error scoring {filename}: {e}"


# =============================================================================
# SECTION 5 — MASTER TOOLS (Add above `if __name__ == "__main__":`)
# =============================================================================

@mcp.tool()
def generate_dita_from_jira(
        issue_key: str,
        dita_type: str = "auto",
) -> str:
    """
    THE MAIN TOOL — Give a Jira issue key, get DITA automatically.
    Handles everything: fetch → RAG → examples → generate → validate → enrich → score → log.

    issue_key: e.g. 'AEM-123'
    dita_type: 'auto' (recommended) or force 'task' / 'concept' / 'reference'

    Just call this and follow the instructions it returns.
    """
    try:
        steps_log = []

        # ── Step 1: Fetch issue + comments ────────────────────────────────
        from backend.app.services.jira_client import JiraClient, extract_description_from_issue
        jira = JiraClient()
        issue = jira.get_issue(issue_key)
        fields = issue.get("fields", {})
        description = extract_description_from_issue(issue)
        comments = jira.get_issue_comments(issue_key)
        summary = fields.get("summary", "")
        issue_type = fields.get("issuetype", {}).get("name", "").lower()
        labels = fields.get("labels", [])
        priority = fields.get("priority", {}).get("name", "")
        status = fields.get("status", {}).get("name", "")
        steps_log.append(f"✅ Fetched: {issue_key} — {summary[:60]}")

        # ── Step 2: Auto-detect DITA type ─────────────────────────────────
        if dita_type == "auto":
            if any(x in issue_type for x in ["bug", "task", "subtask"]):
                dita_type = "task"
            elif any(x in issue_type for x in ["story", "epic", "feature"]):
                dita_type = "concept"
            elif any(x in issue_type for x in ["doc", "ref", "reference"]):
                dita_type = "reference"
            elif any(x in " ".join(labels).lower() for x in ["howto", "procedure", "steps"]):
                dita_type = "task"
            else:
                dita_type = "concept"
        steps_log.append(f"✅ DITA type detected: {dita_type}")

        # ── Step 3: Load RAG context ──────────────────────────────────────
        from backend.app.services.doc_retriever_service import (
            retrieve_relevant_docs, format_docs_for_prompt
        )
        from backend.app.services.dita_knowledge_retriever import (
            retrieve_dita_knowledge, retrieve_dita_graph_knowledge
        )

        el_docs = retrieve_relevant_docs(query=summary, k=2)
        el_text = format_docs_for_prompt(el_docs) if el_docs else "Not indexed yet."

        spec_chunks = retrieve_dita_knowledge(query_text=summary, k=2)
        spec_text = "\n---\n".join(
            (c.get("text_content") or "")[:600]
            for c in spec_chunks
        ) if spec_chunks else "Not indexed yet."

        graph_text = retrieve_dita_graph_knowledge(
            element_hint=f"{dita_type} {summary}"
        ) or "Not available."
        steps_log.append("✅ RAG context loaded")

        # ── Step 4: Find closest expert DITA example ──────────────────────
        example_text = ""
        try:
            from backend.app.services.embedding_service import embed_query, is_embedding_available
            from backend.app.services.vector_store_service import query_collection, is_chroma_available

            if is_chroma_available() and is_embedding_available():
                q_emb = embed_query(f"{dita_type} {summary}")
                if q_emb is not None:
                    rows = query_collection(
                        "dita_examples",
                        query_embedding=q_emb.tolist(),
                        k=1,
                        where={"topic_type": {"$eq": dita_type}},
                    )
                    if rows:
                        example_text = (rows[0].get("document") or "")[:2000]
                        steps_log.append("✅ Expert example found")
                    else:
                        steps_log.append("⚠️ No expert example found — run index_dita_example_repos")
        except Exception:
            steps_log.append("⚠️ Expert examples not available")

        # ── Step 5: Format comments ───────────────────────────────────────
        comment_lines = []
        for c in comments[:5]:
            body = (c.get("body_text") or "")[:300]
            if body:
                comment_lines.append(f"{c.get('author', 'Unknown')}: {body}")
        comment_text = "\n".join(comment_lines) if comment_lines else "No comments."

        # ── Step 6: Build output filename ─────────────────────────────────
        filename = f"{issue_key}-{dita_type}.dita"
        root_id = issue_key.lower().replace("-", "_")

        # ── Step 7: Return complete generation package ────────────────────
        return f"""
GENERATION PACKAGE FOR {issue_key}
{'=' * 60}
{chr(10).join(steps_log)}

TARGET FILE: output/dita/{filename}
{'=' * 60}

JIRA DATA:
  Key:         {issue_key}
  Summary:     {summary}
  Type:        {fields.get('issuetype', {}).get('name', '')}
  Status:      {status}
  Priority:    {priority}
  Labels:      {', '.join(labels) or 'None'}

  Description:
  {description[:2000]}

  Comments:
  {comment_text}

{'=' * 60}
AEM GUIDES CONTEXT (Experience League):
{el_text[:1000]}

{'=' * 60}
DITA SPEC RULES (1.2 / 1.3):
{spec_text[:800]}

{'=' * 60}
ELEMENT NESTING RULES:
{graph_text[:600]}

{'=' * 60}
EXPERT EXAMPLE (mirror this structure):
{example_text if example_text else 'No example available — use spec rules above.'}

{'=' * 60}
YOUR TASK — GENERATE THIS FILE:
{'=' * 60}

Generate a complete DITA 1.3 {dita_type} topic XML using ALL context above.

REQUIREMENTS:
1. Start with: <?xml version="1.0" encoding="UTF-8"?>
2. Include correct DOCTYPE for {dita_type}
3. Root <{dita_type}> must have: id="{root_id}"
4. Include <title> reflecting the issue summary
5. Include <shortdesc> — one sentence summarizing the issue
6. Include <prolog><metadata> with author and created date
7. Use correct body element:
   - task      → <taskbody> with <prereq>, <context>, <steps>, <result>
   - concept   → <conbody> with <p>, <section>
   - reference → <refbody> with <section>, <properties>
8. Every <step> must have <cmd> as first child
9. Content must reflect the ACTUAL Jira issue — not generic
10. Follow nesting rules from element graph above
11. Mirror structure from expert example above

SCENARIO FIDELITY (mandatory — not a Jira field dump):
12. Do NOT treat the topic as finished if you only paraphrased the description into <p>
    blocks and added a metadata <simpletable> (issue key, status, labels). That is
    insufficient for editor, table, layout, or publishing defects.
13. Encode the reporter's STRUCTURE in DITA: if they describe a table with dimensions,
    include a real content <table> with <tgroup cols="N">, <colspec> per column,
    <thead>/<tbody>, and enough <row>/<entry> cells to match the described grid (pick a
    clear interpretation when Jira wording is ambiguous, e.g. "6 rows and 5 rows" → state
    5 columns × 6 rows in a short <p> or <note>).
14. UI actions (right-click, menu paths): use <menucascade> with <uicontrol> for each
    level (e.g. Delete → Columns). Order must match the Jira reproduction.
15. Every URL in description or comments: add <xref href="..." format="html" scope="external">.
16. Distinctive reporter wording that carries reproduction detail: preserve in a <note> or
    <lq> (verbatim or near-verbatim), then explain interpretation in following <p> if needed.
17. Procedural reproduction in a concept topic: add a dedicated <section> (e.g. reproduction)
    with <ol> or numbered steps; if dita_type is task, use <steps>/<step>/<cmd> instead.

AFTER GENERATING, EXECUTE IN ORDER:
1. save_dita_file('{filename}', generated_xml)
2. validate_and_fix_dita('{filename}')
3. enrich_dita_output()
4. score_dita_quality('{filename}')
5. mark_issue_generated('{issue_key}', ['{filename}'])
{'=' * 60}
"""

    except Exception as e:
        return f"Error generating for {issue_key}: {e}"


@mcp.tool()
def batch_generate_dita_from_jira(
        jql: str,
        max_issues: int = 10,
        dita_type: str = "auto",
) -> str:
    """
    THE BATCH TOOL — Give a JQL query, get DITA for ALL matching issues.
    Skips issues already generated. Returns ordered execution plan.

    jql: e.g. 'project = AEM AND status = Done AND updated >= -7d'
    max_issues: how many to process (default 10, max 50)
    dita_type: 'auto' or force 'task' / 'concept' / 'reference'

    After this returns the plan, execute each step in order.
    """
    try:
        import json
        from backend.app.services.jira_dita_fetch_service import fetch_jira_issues

        max_issues = min(max_issues, 50)  # safety cap

        # ── Check generation history ──────────────────────────────────────
        log_path = PROJECT_ROOT / "output" / "generation_log.json"
        log = {}
        if log_path.exists():
            try:
                log = json.loads(log_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # ── Fetch issues ──────────────────────────────────────────────────
        issues = fetch_jira_issues(jql, max_results=max_issues, fetch_comments=False)
        if not issues:
            return f"No issues found for JQL: {jql}"

        pending = [i for i in issues if i.get("issue_key") not in log]
        already_done = len(issues) - len(pending)

        if not pending:
            return (
                f"All {len(issues)} issues already generated.\n"
                f"Run list_generation_history to see them.\n"
                f"Run bundle_dita_package to package them."
            )

        # ── Build execution plan ──────────────────────────────────────────
        plan_lines = []
        filenames = []

        for i, issue in enumerate(pending, 1):
            key = issue.get("issue_key", "")
            summary = (issue.get("summary") or "")[:70]
            issue_type = (issue.get("issue_type") or "").lower()

            # Auto-detect type
            t = dita_type
            if t == "auto":
                if any(x in issue_type for x in ["bug", "task", "subtask"]):
                    t = "task"
                elif any(x in issue_type for x in ["story", "epic", "feature"]):
                    t = "concept"
                else:
                    t = "concept"

            fname = f"{key}-{t}.dita"
            filenames.append(fname)

            plan_lines.append(
                f"── Issue {i}/{len(pending)} ──────────────────────────\n"
                f"   Call: generate_dita_from_jira('{key}', dita_type='{t}')\n"
                f"   File: {fname}\n"
                f"   Info: {summary}"
            )

        # Build safe package name from JQL
        safe_name = jql[:30].replace(" ", "_").replace("=", "").replace(">", "").replace("<", "").strip("_")

        return f"""
BATCH GENERATION PLAN
{'=' * 60}
JQL:              {jql}
Total found:      {len(issues)}
Already done:     {already_done} (skipping)
To generate:      {len(pending)}
{'=' * 60}

EXECUTE EACH STEP IN ORDER:

{chr(10).join(plan_lines)}

{'=' * 60}
AFTER ALL {len(pending)} ISSUES GENERATED:
{'=' * 60}
1. enrich_dita_output()
   → adds shortdesc + prolog to all files

2. bundle_dita_package('{safe_name}')
   → creates ZIP package ready for AEM

3. list_generation_history()
   → confirm all issues logged
{'=' * 60}

Start with Step 1 now: generate_dita_from_jira('{pending[0].get("issue_key")}')
"""

    except Exception as e:
        return f"Error creating batch plan: {e}"


@mcp.tool()
def get_jira_issue_images(issue_key: str) -> str:
    """
    Fetch and download all image attachments from a Jira issue.
    Saves images to output/images/{issue_key}/ folder.
    Returns image metadata so Cursor can insert them into DITA as fig elements.

    Supports: PNG, JPG, GIF, SVG, BMP, WEBP
    Also detects: architecture diagrams, screenshots, flowcharts
    """
    try:
        import mimetypes
        from pathlib import Path
        from backend.app.services.jira_client import JiraClient
        from backend.app.services.jira_attachment_service import (
            ensure_attachment_cached,
            extract_excerpt,
        )
        from backend.app.db.session import SessionLocal
        from backend.app.db.jira_models import JiraAttachment, JiraIssue

        IMAGE_MIMES = {
            "image/png", "image/jpeg", "image/jpg", "image/gif",
            "image/svg+xml", "image/bmp", "image/webp", "image/tiff",
        }
        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp", ".tiff"}

        jira = JiraClient()

        # ── Get attachments from Jira API directly ────────────────────────────
        raw_attachments = jira.get_issue_attachments(issue_key)
        if not raw_attachments:
            return f"No attachments found for {issue_key}"

        # Filter images only
        image_attachments = []
        for att in raw_attachments:
            mime = (att.get("mimeType") or "").lower()
            filename = att.get("filename") or ""
            ext = Path(filename).suffix.lower()
            if mime in IMAGE_MIMES or ext in IMAGE_EXTS:
                image_attachments.append(att)

        if not image_attachments:
            return (
                f"No image attachments found for {issue_key}.\n"
                f"Total attachments: {len(raw_attachments)}\n"
                f"Types found: {', '.join(set(a.get('mimeType','unknown') for a in raw_attachments))}"
            )

        # ── Download images to output/images/{issue_key}/ ─────────────────────
        output_dir = PROJECT_ROOT / "output" / "images" / issue_key
        output_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for att in image_attachments:
            filename  = att.get("filename", "image.png")
            mime_type = att.get("mimeType", "image/png")
            size      = att.get("size", 0)
            content_url = att.get("content", "")

            # Download
            filepath = output_dir / filename
            if not filepath.exists():
                try:
                    content = jira.download_attachment(content_url)
                    filepath.write_bytes(content)
                except Exception as e:
                    results.append({
                        "filename": filename,
                        "error": str(e),
                        "downloaded": False,
                    })
                    continue

            # Detect image type for DITA alt text suggestion
            img_type = _detect_image_type(filename, mime_type)

            results.append({
                "filename": filename,
                "mime_type": mime_type,
                "size_bytes": size,
                "local_path": str(filepath),
                "relative_path": f"output/images/{issue_key}/{filename}",
                "aem_dam_path": f"/content/dam/dita-images/{issue_key}/{filename}",
                "image_type": img_type,
                "suggested_alt": _suggest_alt_text(filename, img_type),
                "suggested_title": _suggest_title(filename, img_type),
                "downloaded": True,
            })

        # Format output for Cursor
        lines = [
            f"✅ Found {len(results)} image(s) for {issue_key}",
            f"Saved to: {output_dir}",
            "",
            "IMAGES — Use these to insert fig elements in DITA:",
            "=" * 50,
            ]

        for i, r in enumerate(results, 1):
            if r.get("error"):
                lines.append(f"{i}. ❌ {r['filename']}: {r['error']}")
                continue
            lines.append(f"""
{i}. {r['filename']}
   Type:          {r['image_type']}
   Size:          {r['size_bytes']} bytes
   Local path:    {r['relative_path']}
   AEM DAM path:  {r['aem_dam_path']}
   Suggested alt: {r['suggested_alt']}
   Suggested title: {r['suggested_title']}

   DITA fig element to insert:
   <fig>
     <title>{r['suggested_title']}</title>
     <image href="{r['aem_dam_path']}"
            format="{r['mime_type'].split('/')[-1]}"
            scope="external">
       <alt>{r['suggested_alt']}</alt>
     </image>
   </fig>
""")

        lines.append("=" * 50)
        lines.append(
            "INSERT INSTRUCTION FOR CURSOR:\n"
            "For each image above, insert the fig element at the\n"
            "appropriate location in the DITA topic:\n"
            "- Screenshots → after the relevant step/context\n"
            "- Architecture diagrams → in concept body or section\n"
            "- Flowcharts → after context or before steps\n"
            "- Product images → in shortdesc context or section"
        )

        return "\n".join(lines)

    except Exception as e:
        return f"Error fetching images for {issue_key}: {e}"


@mcp.tool()
def save_dita_with_images(
        filename: str,
        content: str,
        issue_key: str,
) -> str:
    """
    Save a DITA file that references images.
    Validates that all <image href> paths exist locally.
    Reports any missing images so Cursor can fix them.

    filename: e.g. 'AEM-123-task.dita'
    content:  full DITA XML with fig/image elements
    issue_key: Jira issue key to find downloaded images
    """
    try:
        import re

        output_dir = PROJECT_ROOT / "output" / "dita"
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / filename

        # ── Check all image hrefs ─────────────────────────────────────────────
        image_refs = re.findall(r'<image[^>]+href="([^"]+)"', content)
        missing = []
        found   = []

        images_dir = PROJECT_ROOT / "output" / "images" / issue_key

        for href in image_refs:
            img_filename = href.split("/")[-1]
            local = images_dir / img_filename
            if local.exists():
                found.append(img_filename)
            else:
                missing.append(href)

        # Save the file
        filepath.write_text(content, encoding="utf-8")

        status_lines = [f"✅ Saved: {filepath}"]

        if found:
            status_lines.append(f"✅ Images verified: {', '.join(found)}")
        if missing:
            status_lines.append(f"⚠️ Missing images: {', '.join(missing)}")
            status_lines.append(
                "Run get_jira_issue_images to download missing images"
            )

        return "\n".join(status_lines)

    except Exception as e:
        return f"Error saving {filename}: {e}"


@mcp.tool()
def list_issue_images(issue_key: str) -> str:
    """
    List all downloaded images for a Jira issue.
    Use this to check what images are available before inserting into DITA.
    """
    try:
        images_dir = PROJECT_ROOT / "output" / "images" / issue_key
        if not images_dir.exists():
            return (
                f"No images downloaded for {issue_key} yet.\n"
                f"Run get_jira_issue_images('{issue_key}') first."
            )

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
        files = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]

        if not files:
            return f"No image files found in output/images/{issue_key}/"

        lines = [f"Images available for {issue_key}:", ""]
        for f in sorted(files):
            size = f.stat().st_size
            img_type = _detect_image_type(f.name, "")
            lines.append(
                f"  {f.name} ({size} bytes) — {img_type}\n"
                f"  AEM path: /content/dam/dita-images/{issue_key}/{f.name}"
            )

        return "\n".join(lines)

    except Exception as e:
        return f"Error listing images: {e}"


@mcp.tool()
def generate_fig_elements(issue_key: str) -> str:
    """
    Generate ready-to-paste DITA fig elements for all downloaded images.
    Cursor can copy these directly into the DITA topic.
    """
    try:
        images_dir = PROJECT_ROOT / "output" / "images" / issue_key
        if not images_dir.exists():
            return f"No images for {issue_key}. Run get_jira_issue_images first."

        IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".bmp", ".webp"}
        files = [
            f for f in images_dir.iterdir()
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        ]

        if not files:
            return "No images found."

        lines = [
            f"DITA fig elements for {issue_key}:",
            "Copy and paste into appropriate location in your topic:",
            "",
        ]

        for f in sorted(files):
            img_type = _detect_image_type(f.name, "")
            alt      = _suggest_alt_text(f.name, img_type)
            title    = _suggest_title(f.name, img_type)
            fmt      = f.suffix.lower().strip(".")
            dam_path = f"/content/dam/dita-images/{issue_key}/{f.name}"

            lines.append(f"<!-- {f.name} — {img_type} -->")
            lines.append(f"""<fig>
  <title>{title}</title>
  <image href="{dam_path}"
         format="{fmt}"
         placement="break"
         scope="external">
    <alt>{alt}</alt>
  </image>
</fig>
""")

        return "\n".join(lines)

    except Exception as e:
        return f"Error generating fig elements: {e}"


# ── Helper functions ──────────────────────────────────────────────────────────

def _detect_image_type(filename: str, mime_type: str) -> str:
    """Detect what kind of image this is from filename."""
    name = filename.lower()
    if any(x in name for x in ["screenshot", "screen", "capture", "snap"]):
        return "screenshot"
    if any(x in name for x in ["arch", "architecture", "diagram", "design"]):
        return "architecture_diagram"
    if any(x in name for x in ["flow", "flowchart", "process", "workflow"]):
        return "flowchart"
    if any(x in name for x in ["product", "ui", "interface", "portal"]):
        return "product_image"
    if mime_type == "image/svg+xml" or name.endswith(".svg"):
        return "diagram"
    return "screenshot"  # default assumption


def _suggest_alt_text(filename: str, img_type: str) -> str:
    """Generate a sensible alt text from filename and type."""
    # Remove extension and clean up
    name = filename.rsplit(".", 1)[0]
    name = name.replace("-", " ").replace("_", " ").strip()

    suggestions = {
        "screenshot":          f"Screenshot showing {name}",
        "architecture_diagram": f"Architecture diagram of {name}",
        "flowchart":           f"Flowchart illustrating {name}",
        "product_image":       f"Product interface showing {name}",
        "diagram":             f"Diagram of {name}",
    }
    return suggestions.get(img_type, f"Image showing {name}")


def _suggest_title(filename: str, img_type: str) -> str:
    """Generate a sensible fig title from filename."""
    name = filename.rsplit(".", 1)[0]
    name = name.replace("-", " ").replace("_", " ").strip()
    name = name.capitalize()

    titles = {
        "screenshot":           name,
        "architecture_diagram": f"{name} architecture",
        "flowchart":            f"{name} flow",
        "product_image":        name,
        "diagram":              f"{name} diagram",
    }
    return titles.get(img_type, name)

DITA_TRUSTED_SOURCES = [
    "docs.oasis-open.org",
    "experienceleague.adobe.com",
    "helpx.adobe.com",
    "dita-ot.org",
    "github.com/oasis-tcs",
]


def _get_tavily_client(TAVILY_API_KEY):
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

        output = ["Research for {issue_key}: {summary[:60]}", f"Search query: {query[:100]}", "=" * 60,
                  _format_research_result(
                      result,
                      title="Web Research for {issue_key}",
                      source_type="DITA/AEM Sources",
                  )]

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



if __name__ == "__main__":
    mcp.run()
