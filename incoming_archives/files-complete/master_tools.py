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
