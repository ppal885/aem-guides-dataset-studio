# Evidence Preflight And Degraded Mode

Run this preflight before collecting evidence or drafting a plan. A configured connector is not proof that it works: make an actual lightweight call, record the result, and restrict only the claims that depend on a failed source.

## Required Source Checks

- `product_rag`: call `check_rag_status` when available, then run the focused `ask_dita_expert` probes required by the plan. A configured MCP endpoint alone is not `available`.
- `jira_history`: run `search_jira_history` with the required same-customer and cross-customer searches. A live-Jira 403 does not prove the indexed history tool is unavailable; check it separately.
- `live_jira`: fetch the supplied Jira issue or run a lightweight Jira lookup. Record authentication, permission, missing-issue, and connector failures distinctly.
- `git`: inspect a synchronized local clone, a supplied diff, or the relevant GitHub ref. In pre-development with no implementation claim, use `not_applicable` and explain why.
- `figma`: inspect the supplied design/prototype when design evidence is relevant. If no design evidence is supplied or required, use `not_applicable` and explain why.

Use only these source statuses:

- `available`: an actual check or evidence call succeeded.
- `unavailable`: an actual check failed or the required connector/evidence could not be reached.
- `not_applicable`: the source cannot affect claims for this lifecycle stage and input.

## Manifest Contract

Add this object to every evidence manifest:

```json
{
  "evidence_preflight": {
    "mode": "full",
    "checked_at": "2026-08-08T15:30:00+05:30",
    "sources": {
      "product_rag": {"status": "available", "checked_via": "check_rag_status and ask_dita_expert", "reason": ""},
      "jira_history": {"status": "available", "checked_via": "search_jira_history", "reason": ""},
      "live_jira": {"status": "available", "checked_via": "Jira MCP issue fetch", "reason": ""},
      "git": {"status": "not_applicable", "checked_via": "lifecycle classification", "reason": "Pre-development; no implementation or changed-code claim exists."},
      "figma": {"status": "not_applicable", "checked_via": "input inspection", "reason": "No design link, screenshot, or UI-intent claim is in scope."}
    },
    "readiness_impact": "none",
    "readiness_impact_reason": "",
    "claim_restrictions": []
  }
}
```

Contract rules:

- Include exactly the five source keys shown above.
- Every source needs a non-empty `checked_via` value.
- `unavailable` and `not_applicable` sources need a non-empty `reason`.
- Use `mode: degraded` whenever any source is `unavailable`; otherwise use `mode: full`.
- A degraded preflight must list concrete `claim_restrictions`.
- Use `readiness_impact: none`, `draft_only`, or `blocked`. A non-`none` impact needs `readiness_impact_reason`.
- `checked_at` must be a timezone-aware ISO-8601 timestamp.
- If `product_rag` is unavailable but behavior matters, keep `rag_tool: ask_dita_expert` and record the three focused attempted questions in `rag_probes`; the preflight and Evidence boundary explain that no RAG answer was accepted.
- If `jira_history` is unavailable, set top-level `jira_history_unavailable_reason`, keep `jira_history_queries` empty, and put the attempted-search fallback reason in `indexed_history_run`; do not set it to `true`.

## Claim Restrictions

- When `product_rag` is unavailable, do not claim documented product behavior from RAG. Keep unsupported behavior unknown or support it with authoritative Jira/UAC, inspected implementation, or accepted design evidence.
- When `jira_history` is unavailable, do not claim that no similar customer defects exist. State that historical similarity and regression learning are incomplete.
- When `live_jira` is unavailable, do not claim current status, resolution, fix version, comments, attachments, or mutable issue facts unless the user supplied them and the source is named.
- When `git` is unavailable, do not claim current implementation, changed files, changed lines, root cause, or fix impact.
- When `figma` is unavailable and design evidence is required, do not claim exact layout, interaction state, visual variant, or prototype behavior.

## Lifecycle Readiness

- `Pre-Development UAC`: an unavailable optional source does not automatically block the plan. Use `none` when alternate authoritative evidence supports all retained UAC claims; otherwise use `draft_only` for the affected decisions.
- `Implementation Review`: unavailable Git/diff evidence normally requires `draft_only` because implementation and changed-code claims cannot be verified.
- `Post-Fix Validation`: use `blocked` when the candidate build, live mutable Jira facts, or fix diff required for sign-off is unavailable.
- Never hide a source failure. Start the visible `Evidence boundary:` bullet with `Evidence mode: full` or `Evidence mode: degraded`. In degraded mode, name every unavailable source and state what remains unverified.
