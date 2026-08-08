---
name: test-plan-generation
description: "Generate evidence-backed, plain-English AEM Guides QA test plans from Jira, PR, branch, commit, pasted diff, or user-cloned repo context. Use when Codex must create, improve, or review a manual QA test plan with acceptance criteria, expected behaviour, Git/PR scope, touched code, changed lines, test scenarios, past similar tickets, and regression areas; using Jira MCP for Jira facts, GitHub MCP to discover/fetch PRs when Jira does not mention one, `ask_dita_expert` for VM-backed RAG behaviour learning, and user cloned repos such as Starling/backend, xmleditor, new editor, guides-ui-tests, and dxml-it-tests for code and automation evidence; with strict Draft blockers when Jira, RAG, PR/diff, repo sync, or historical evidence is missing; and no tables or noisy raw evidence dumps."
---

# Test Plan Generation

## Goal

Produce a concrete AEM Guides QA test plan that reads like a senior manual QA engineer wrote it: practical, evidence-backed, plain-English, and bullet-only. Use RAG to learn product behaviour, but do not let RAG replace Jira facts or PR diff evidence.

## Operating Mode

- Work evidence-first: collect facts, normalize behaviour, retrieve RAG, inspect diff, then write scenarios.
- Preserve direct evidence collection: run three focused `ask_dita_expert` probes and both same-customer and cross-customer `search_jira_history` calls before querying the evidence graph.
- Keep the final answer short and tester-facing; keep raw evidence, chunk scores, backend traces, and reasoning audits internal.
- Treat the plan as `Draft` unless current Jira facts, accepted behaviour evidence, past-similar-ticket search, and required Git/PR evidence are present.
- Ask for the missing Jira text, PR URL, branch, commit, or pasted diff only when that evidence is required and unavailable.
- Use user-provided local clones when present; do not ask teammates to clone dataset-studio, copy RAG JSON, copy ChromaDB, or run old test-plan MCP tools.

## Tool Boundary

- Use `ask_dita_expert` as the only VM RAG path for AEM Guides, Experience League, DITA, DITA-OT, workflow, release-note, and configuration behaviour facts.
- Use `search_jira_history` for indexed Jira history; never treat it as product documentation or current mutable Jira truth.
- Call `query_test_evidence_graph` after direct RAG and Jira retrieval. Default to shadow influence unless deployment explicitly enables augment; shadow output cannot change the plan. Graph paths are traceability only; only underlying leaf citations can support a claim.
- Use Jira MCP first for current Jira facts and historical similar-ticket search. If Jira MCP is unavailable, use pasted Jira details and mark the Jira evidence gap.
- Use GitHub MCP to inspect a PR when Jira includes one; if Jira has no PR link, use GitHub MCP to search likely repos by Jira key, summary terms, branch names, commit messages, and PR body before asking the user for a PR.
- Do not use or expect `/aem-guides-test-plan`, `guides_test_plan_generator`, `test_plan_pipeline`, or any generated test-plan MCP tool.
- Use connected Jira/GitHub MCPs only if available in the current session. If unavailable, rely on user-provided Jira/PR/diff text and local clones, then mark gaps as Draft blockers.
- If a local cloned repo is used for evidence, fetch before relying on it and never stash, reset, merge, or rebase automatically.

## Required References

- Read `references/rag-query-cookbook.md` before calling or judging `ask_dita_expert` evidence.
- Read `references/pr-and-repo-evidence.md` before searching GitHub MCP, inspecting PRs, or using user-cloned repos.
- Read `references/output-template.md` before writing the final test plan.
- Read `references/quality-gate-checklist.md` before marking a plan review-ready.
- Read `references/evidence-graph-contract.md` before using graph-connected findings.

## Lifecycle

### Phase 0 — Classify Input

- Identify whether the user provided Jira only, PR only, Jira + PR, branch/commit, pasted diff, or only a vague request.
- If Jira facts are missing, keep the plan Draft and ask for Jira summary/description/AC or a Jira MCP connection.
- If PR/diff evidence is missing and fix-impact claims are needed, ask for PR URL, branch, commit, or pasted diff.
- If the user only wants a lightweight draft, still mark unsupported sections with `Draft blocker:`.

### Phase 1 — Collect Jira Facts

- Use connected Jira MCP first for the target Jira whenever available; otherwise use pasted Jira details and mark that Jira MCP was unavailable.
- Extract summary, description, expected/actual behaviour, acceptance criteria/UAC, comments, labels, components, affected/fix versions, status, customer impact, attachments, linked issues, and development links.
- Do not invent AC, comments, customer impact, linked PRs, or related Jira keys.
- Convert unclear AC into tester-readable bullets and keep ambiguity visible.

### Phase 2 — Normalize Behaviour

- Convert Jira text into current behaviour, expected behaviour, affected workflow, data shape, error contract, version boundary, configuration boundary, roles/permissions, user impact, and open questions.
- Label inferred ownership, impacted code, or workflow assumptions as inferred unless PR/repo evidence confirms them.
- Build three concise search intents: exact failure, expected workflow, and configuration/boundary.

### Phase 3 — Retrieve Behaviour RAG

- Call `ask_dita_expert` with focused questions from normalized behaviour, not raw keyword spam.
- Run at least three focused probes when behaviour matters and record their exact questions.
- Use RAG to ground expected behaviour, workflow rules, product constraints, release-note behaviour, configuration effects, and regression areas.
- Reject chunks that only share broad vocabulary such as `topic`, `map`, `assets`, `metadata`, `cloud`, `report`, `translation`, or `workflow` without proving the actual behaviour.
- Never use attribute-only DITA evidence as proof for an exact element behaviour, or generic DITA docs as proof for AEM Guides UI behaviour.
- If RAG is unavailable, noisy, or unrelated, add a Draft blocker under `Expected Behaviour` or `Regression Areas`.

### Phase 4 — Find Past Similar Tickets

- Use Jira MCP/JQL if available; otherwise use only user-provided related tickets or available team memory.
- Run `search_jira_history` twice with the canonical component: once with the current customer and once without a customer filter. Retain only same-mechanism results.
- Search by exact error text, workflow, API route, component, UI label, data shape, version boundary, and likely code area.
- Keep at most five past tickets. For each, explain why similar and what coverage it adds.
- Reject broad results that match only generic words.

### Phase 4.5 — Connect Evidence Graph

- Query `query_test_evidence_graph` with the normalized failure shape and exact Jira/customer/component/output/DITA selectors after direct retrieval.
- Record `influence_mode`, `used_for_plan`, duration, and cache status. In `shadow`, `used_for_plan=false` and graph output cannot change plan content, scoring, citations, repository scope, or automation verdicts.
- Reject candidate-only, area-only, and path-only findings. Deduplicate graph and direct evidence by leaf/source ID.
- Only in explicit `augment` mode, fold trusted graph findings into existing sections; never add an Evidence Graph section.
- Record status, generation, query, path IDs, leaf citations, and degraded reason in the evidence manifest. Graph unavailability alone is not a Draft blocker when direct authoritative evidence covers behaviour.

### Phase 5 — Inspect Git/PR Evidence

- Prefer connected GitHub MCP for PRs. If Jira does not mention a PR, search GitHub MCP by Jira key, summary terms, branch names, commit messages, and PR body across likely AEM Guides repos before asking the user for a PR.
- Capture changed files, functions/classes/components, added/deleted line counts, key hunks, tests, config/migration changes, API/error contract changes, and gaps.
- Inspect user-cloned repos when available for code and automation context: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- For local cloned repos, run `git fetch --all --prune`, inspect `git status -sb`, and fast-forward pull only if clean and behind. If dirty, diverged, no upstream, or fetch/pull fails, keep repo claims provisional.
- Never infer Git scope from Jira keywords alone.
- If line-level diff is unavailable, write `Draft blocker: line-level diff not inspected`.

### Phase 6 — Design Test Scenarios

- Write 6-10 scenarios maximum, priority-tagged `P0`, `P1`, or `P2`.
- Each scenario must include action + expected result in one plain-English bullet.
- Cover happy path, negative/boundary, role/permission, configuration, data-shape, upgrade/version, and fix-safety checks when relevant.
- Every P0/P1 scenario must trace to Jira AC, accepted RAG, PR diff, past Jira learning, or an explicit high-risk regression.

### Phase 7 — Decide Draft vs Review-Ready

- Use `Draft blocker:` bullets inside the affected final section; do not create a separate blocker section.
- Keep Draft if Jira facts, accepted RAG, historical Jira search, PR/diff, line counts, or repo sync are missing and required for confidence.
- Mark review-ready only when evidence supports expected behaviour, scope, code impact, test scenarios, and regression areas.

## Output Contract

- Output Markdown bullets only.
- Do not use tables.
- Do not output JSON unless explicitly requested.
- Do not include raw RAG chunks, chunk scores, backend traces, evidence matrices, or long citations.
- Use exactly these sections, in this order:
  1. `Acceptance Criteria`
  2. `Expected Behaviour`
  3. `Scope From Git`
  4. `Code Touched`
  5. `Lines Changed`
  6. `Test Scenarios`
  7. `Past Similar Tickets`
  8. `Regression Areas`

## Section Rules

- **Acceptance Criteria**: Rewrite Jira AC/sign-off conditions as tester-readable bullets. Every AC mapped to P0/P1 ends with `| Evidence: <underlying Jira, URL/chunk, DITA source, Figma node, attachment, or inspected code citation>`; a graph path alone is invalid. If unclear, add `Draft blocker: acceptance criteria missing or unclear`.
- **Expected Behaviour**: State intended behaviour from Jira plus accepted `ask_dita_expert` evidence. If unsupported, write `Unknown from current evidence`.
- **Scope From Git**: List Jira development-link source, GitHub MCP PR-discovery result, PR/branch/commit, repo sync state, changed product area, and whether diff was inspected.
- **Code Touched**: List only real files/functions/classes/components touched or directly implicated by PR/repo scan, with short QA impact.
- **Lines Changed**: Summarize added/deleted line counts and key hunks by file. If unavailable, add `Draft blocker: line-level diff not inspected`.
- **Test Scenarios**: Keep 6-10 practical P0/P1/P2 bullets, each with action + expected result.
- **Past Similar Tickets**: List up to five Jira keys with similarity reason and coverage impact. If unavailable, say so directly.
- **Regression Areas**: List nearby workflows, APIs, configs, roles, browsers, data shapes, upgrade paths, and automation gaps likely to break.

## Hard Rules

- Keep acceptance criteria in the plan.
- Do not add extra headings such as `What can break`, `Likely bugs`, `Fix safety`, `Important combinations`, `Automation`, or `Draft blockers`.
- Put likely bugs, fix-safety, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Never call a plan `proper RAG-backed` when evidence is generic, unrelated, unavailable, or only keyword-matched.
- Never mark review-ready when required Jira, RAG, past-ticket, PR/diff, line-count, or repo-sync evidence is missing.
