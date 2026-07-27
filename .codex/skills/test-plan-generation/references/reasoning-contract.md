# Jira Evidence-To-Test-Plan Reasoning Contract

Use this JSON only as an internal evidence checklist or when a pipeline explicitly asks for the packet. For user-facing test plans, convert this evidence into the plain-English bullet sections required by `SKILL.md`.

```json
{
  "jira_key": "GUIDES-00000",
  "stage_status": {
    "team_test_plan_memory": {
      "status": "complete|partial|missing",
      "memory_files_read": [],
      "matched_jiras": [],
      "missing": []
    },
    "current_jira_mcp": {
      "status": "complete|partial|missing",
      "fields_used": [],
      "missing": []
    },
    "claude_ticket_analysis": {
      "status": "complete|partial|missing",
      "open_questions": []
    },
    "behavior_rag": {
      "status": "complete|partial|missing",
      "queries": [],
      "evidence_refs": [],
      "unknowns": []
    },
    "historical_jira_mcp": {
      "status": "complete|partial|missing",
      "jql_run": [],
      "missing": []
    },
    "repository_scan": {
      "status": "complete|partial|missing",
      "repo_sync": [
        {
          "repo": "",
          "remote": "",
          "branch": "",
          "fetched": true,
          "working_tree": "clean|dirty|unknown",
          "upstream_state": "up_to_date|behind|ahead|diverged|no_upstream|unknown",
          "pull_action": "not_needed|ff_only_pulled|blocked_dirty|blocked_diverged|blocked_no_upstream|failed|waived",
          "evidence": ""
        }
      ],
      "repos_checked": [],
      "missing": []
    },
    "git_pr_diff": {
      "status": "complete|partial|missing",
      "jira_pr_link_status": "present|missing|unknown",
      "user_pr_request_status": "not_needed|required|provided|declined",
      "user_supplied_pr_links": [],
      "pr_links_checked": [],
      "git_queries": [],
      "missing": []
    },
    "change_impact_analysis": {
      "status": "complete|partial|missing",
      "draft_blockers": []
    }
  },
  "team_memory_matches": [
    {
      "jira_key": "",
      "plan_file": "",
      "why_relevant": "",
      "reusable_learning": "",
      "limits": "Prior plan memory only; validate against current Jira/RAG/repo/diff evidence."
    }
  ],
  "normalized_ticket": {
    "current_behavior": "",
    "expected_behavior": "",
    "affected_surface": [],
    "user_workflow": [],
    "data_shape": [],
    "error_contracts": [],
    "version_boundary": "",
    "customer_or_business_impact": "",
    "acceptance_criteria": [],
    "ambiguities": []
  },
  "behavior_rag_queries": [
    {
      "query": "",
      "why": "",
      "expected_source": "Experience League|VM RAG|DITA spec|DITA-OT|other"
    }
  ],
  "historical_jql": [
    {
      "jql": "",
      "why": ""
    }
  ],
  "historical_jira_rows": [
    {
      "key": "",
      "summary": "",
      "status_resolution": "",
      "similarity_reason": "",
      "risk_signal": "previous_fix|reopened|customer_escape|similar_exception|missing_automation|none",
      "coverage_change": ""
    }
  ],
  "repo_hypotheses": [
    {
      "expected_repo": "xmleditor|starling|guides-ui-tests|dxml-it-tests",
      "owner": "frontend|backend|frontend_qa_automation|backend_qa_automation",
      "hypothesis": "",
      "confidence": "high|medium|low",
      "needs_validation": true
    }
  ],
  "repo_queries": [
    {
      "query": "",
      "kind": "api_route|error_code|class_or_service|method_or_property|ui_component|config_key|exact_message|test_fixture|fallback",
      "expected_repo": "xmleditor|starling|guides-ui-tests|dxml-it-tests",
      "why_from_jira": "",
      "stage_source": "current_jira_mcp|claude_ticket_analysis|behavior_rag|historical_jira_mcp|git_pr_diff",
      "repo_sync_status": "up_to_date|ff_only_pulled|blocked|unknown",
      "confidence": "high|medium|low"
    }
  ],
  "code_scan_evidence": [
    {
      "repo": "",
      "path": "",
      "line": 0,
      "symbol_or_match": "",
      "what_it_proves": "",
      "repo_sync_status": "up_to_date|ff_only_pulled|blocked|unknown"
    }
  ],
  "pr_and_diff_targets": {
    "jira_comment_pr_links_required": true,
    "ask_user_for_pr_when_jira_has_no_pr": true,
    "user_pr_request_status": "not_needed|required|provided|declined",
    "pr_links_found": [],
    "user_supplied_pr_links": [],
    "git_search_terms": [],
    "expected_changed_areas": []
  },
  "diff_evidence": [
    {
      "source": "github_pr|git_commit|local_git|not_available",
      "ref": "",
      "changed_files": [],
      "changed_contracts": [],
      "tests_added_or_missing": "",
      "impact": ""
    }
  ],
  "plain_english_test_plan": {
    "acceptance_criteria": [],
    "expected_behaviour": [],
    "scope_from_git": [],
    "code_touched": [],
    "lines_changed": [],
    "test_scenarios": [],
    "past_similar_tickets": [],
    "regression_areas": []
  },
  "memory_update": {
    "memory_file": "docs/qa/test-plans/team-test-plan-memory.json",
    "registry_file": "docs/qa/test-plans/test-plans-registry.json",
    "entry": {
      "jira_key": "",
      "plan_file": "",
      "review_status": "",
      "component": "",
      "scope_hint": "",
      "api_routes": [],
      "error_contracts": [],
      "code_paths": [],
      "acceptance_ids": [],
      "scenario_ids": [],
      "automation": {},
      "related_past_jiras": [],
      "pr_links_found": [],
      "draft_blockers": []
    }
  }
}
```

Rules:
- Do not invent Jira IDs, PR URLs, classes, changed files, or comments.
- Current Jira MCP evidence is mandatory before historical Jira or PR analysis.
- If current Jira has no PR, branch, commit, or development-panel link, ask the user for the Git PR URL/number/branch before final plan generation.
- If the user supplies a PR, inspect it with GitHub MCP when available; do not mark review-ready until the PR/diff evidence is captured.
- Before using local repo evidence, fetch each relevant repo and confirm it is up to date or fast-forward pulled on a clean worktree; if sync is blocked, keep the plan Draft and record the repo-sync blocker.
- Team test-plan memory must be read before scenario design and updated after plan creation/material changes.
- Historical Jira MCP evidence is mandatory before review-ready sign-off.
- Git/GitHub PR diff evidence is mandatory for fix-impact claims.
- Inferred repo queries are allowed only when labeled with non-high confidence.
- Keep the user-facing plan compact, bullet-only, and limited to: Acceptance Criteria, Expected Behaviour, Scope From Git, Code Touched, Lines Changed, Test Scenarios, Past Similar Tickets, and Regression Areas.
- Do not use tables in the user-facing plan.
- If blockers exist, place them as short bullets inside the relevant final section; do not create extra blocker/audit headings.
