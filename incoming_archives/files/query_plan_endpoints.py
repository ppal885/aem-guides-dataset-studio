"""
ADD THESE ENDPOINTS TO: backend/app/api/v1/routes/jira.py
(or create backend/app/api/v1/routes/query_plan.py and register in router.py)
"""

# ── Add these imports at top of jira.py ──────────────────────────────────────
# from app.services.query_planner import generate_query_plan
# from app.services.query_executor import execute_query_plan


@router.post("/query-plan")
async def generate_query_plan_endpoint(body: dict):
    """
    Step 1 of research flow — generate research queries for an issue.
    Author reviews these before research runs.

    Input:  { "issue_key": "AEM-123" }
            OR { "issue": { full issue dict } }
    Output: QueryPlan dict with 5 queries across all categories
    """
    try:
        from app.services.query_planner import generate_query_plan

        issue     = body.get("issue") or {}
        issue_key = body.get("issue_key") or issue.get("issue_key", "")

        # Fetch from Jira if only key given
        if not issue.get("summary") and issue_key:
            from app.services.jira_client import JiraClient, extract_description_from_issue
            jira   = JiraClient()
            raw    = jira.get_issue(issue_key)
            fields = raw.get("fields", {})
            issue  = {
                "issue_key":   raw.get("key"),
                "summary":     fields.get("summary", ""),
                "description": extract_description_from_issue(raw),
                "issue_type":  fields.get("issuetype", {}).get("name", ""),
                "labels":      fields.get("labels", []),
                "status":      fields.get("status", {}).get("name", ""),
                "priority":    fields.get("priority", {}).get("name", ""),
            }

        if not issue:
            return {"error": "issue_key or issue dict required"}

        plan = await generate_query_plan(issue)
        return plan.to_dict()

    except Exception as e:
        return {"error": str(e), "queries": []}


@router.post("/execute-queries")
async def execute_queries_endpoint(body: dict):
    """
    Step 2 of research flow — execute approved queries.
    Called after author reviews and approves queries.

    Input:
    {
      "issue_key": "AEM-123",
      "queries": [
        {
          "id": "q_dita_elements",
          "category": "dita_elements",
          "query": "DITA 1.3 task topic required elements",
          "source": "rag",
          "approved": true
        },
        ...
      ]
    }

    Output: ResearchContext with results from RAG + Tavily
    """
    try:
        from app.services.query_executor import execute_query_plan

        issue_key = body.get("issue_key", "unknown")
        queries   = body.get("queries", [])

        # Only run approved queries
        approved = [q for q in queries if q.get("approved", True)]

        if not approved:
            return {"error": "No approved queries to execute", "results": []}

        context = await execute_query_plan(
            issue_key=issue_key,
            approved_queries=approved,
        )

        return context.to_dict()

    except Exception as e:
        return {"error": str(e), "results": []}
