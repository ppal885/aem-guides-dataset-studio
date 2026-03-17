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


if __name__ == "__main__":
    mcp.run()