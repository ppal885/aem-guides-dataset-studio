---
name: test-plan-generation
description: "Generate evidence-backed, plain-English AEM Guides test plans from Jira. Use when Codex must create, improve, or review a Jira-driven QA test plan by extracting acceptance criteria, expected behavior, Git scope, touched code, changed lines, test scenarios, past similar tickets, and regression areas; retrieving product behavior evidence; syncing local repos with remote before repo evidence; inspecting Git/GitHub PR diffs; and keeping the plan Draft when required evidence is missing."
---

# Test Plan Generation

## Goal

Produce a concrete, high-value test plan that reads like it was written by a manual QA engineer with 5+ years of experience. Gather evidence from Jira, behavior RAG, historical tickets, synced repos, and PR/diff inspection, but keep the final user-facing test plan short, plain-English, and bullet-only.

## Required Sequence

Run these stages in order. Do not skip ahead to repo keywords or scenarios.

0. **Read team test-plan memory**
   - Read `{STARLING}/docs/qa/test-plans/team-test-plan-memory.json` and `{STARLING}/docs/qa/test-plans/test-plans-registry.json` when available.
   - Use memory only as prior-plan learning: similar APIs, code paths, risks, scenario IDs, automation gaps, and related past Jiras.
   - Do not treat memory as proof of current behavior; current Jira MCP, behavior RAG, repo scan, and PR diff override memory.

1. **Current Jira MCP extraction**
   - Use Adobe Jira MCP first for the target Jira.
   - Pull summary, description, expected/actual behavior, acceptance criteria/UAC text, comments, linked issues, attachments, labels, components, affected/fix versions, status, customer impact, and any development-panel or PR links.
   - If Jira has no PR, branch, commit, or development-panel link, record that explicitly; do not replace the missing PR link with guessed local git history.
   - If Jira MCP is unavailable, do not invent missing comments, linked PRs, or related Jira IDs; keep the result Draft.

2. **Claude deep ticket analysis**
   - Normalize the issue into current behavior, expected behavior, affected user workflow, data shape, error contract, version boundary, business impact, acceptance criteria, and ambiguity gaps.
   - Infer likely frontend/backend/test ownership only after reading the Jira fields.
   - Mark each inference as confirmed, inferred, or blocked by missing evidence.

3. **Behavior RAG retrieval**
   - Build RAG queries from the normalized workflow and expected behavior, not from raw keyword lists.
   - Retrieve product behavior from Experience League/VM RAG/DITA evidence where relevant.
   - Capture what the product is supposed to do, what is unknown, and whether documentation is enough to support sign-off.
   - Treat RAG as mandatory for functionality facts and expected behavior unless the Jira is strictly code-only; never expose raw RAG chunks in the final plan.

4. **Historical Jira MCP analysis**
   - Use Adobe Jira MCP again with semantic JQL derived from exact error text, workflow, API route, component, version boundary, customer impact, and likely code area.
   - Curate related Jira rows: key, summary, status/resolution, similarity reason, previous fix/escape/reopen/automation signal, and how each row changes test coverage.
   - If no results or MCP unavailable, state the exact JQL required and keep the plan Draft.

5. **Repository scan from the test-plan template**
   - Before scanning any local clone, verify it is up to date with its configured remote so other developers' latest changes are included.
   - Run `git fetch --all --prune` and check `git status -sb` plus upstream ahead/behind state for each relevant repo.
   - If the repo is behind its upstream and the worktree is clean, run `git pull --ff-only` before using repo evidence.
   - If the repo has uncommitted changes, no upstream, diverged history, or the fast-forward pull fails, do not stash, reset, merge, or rebase automatically; ask the user to sync the repo or provide the intended branch/remote.
   - Treat unsynced repo evidence as provisional and keep the plan Draft until the repo sync blocker is resolved or explicitly waived.
   - Use the semantic repo queries from the analysis to scan local clones: `xmleditor`, `starling`, `guides-ui-tests`, and `dxml-it-tests`.
   - Cite real paths/functions/tests. If no repo path is found, keep code-path claims provisional.
   - Do not use broad standalone words such as `map`, `topic`, `type`, `format`, `reports`, `cloud`, or `baseline`.

6. **Git/GitHub MCP PR and diff inspection**
   - Fetch PR URLs from Jira comments, issue links, development panel, and linked commits.
   - Prefer the configured GitHub MCP in Claude Code when available through Claude `mcp.json`; only use local git as a fallback for commit-history hints.
   - If Jira contains no PR/branch/commit link, ask the user for the GitHub PR URL, PR number, or branch before writing the final plan: `Jira has no PR link for <JIRA_KEY>. Please share the Git PR/branch so I can inspect the fix diff.`
   - If the user provides a PR, inspect it with GitHub MCP and capture changed files, changed functions/classes, added/deleted line counts, important changed hunks, removed branches, new tests, config/migration changes, API/error contract changes, and test gaps.
   - If using local git fallback, capture `git diff --stat`, `git diff --numstat`, and relevant hunk/function names from the branch/commit range before writing `Scope From Git`, `Code Touched`, or `Lines Changed`.
   - If GitHub MCP is unavailable, the user cannot provide a PR, or no fix exists yet, write `fix diff not inspected - user PR required` and design fix-safety checks from current product HEAD only.

7. **Final Claude impact analysis**
   - Combine Jira facts, behavior RAG, historical Jira evidence, repo code scan, and PR diff.
   - Produce plain-English analysis: what can break, likely bugs to watch, fix safety checks, important combinations, automation strength, regression pack, and what remains unverified.
   - Every P0/P1 scenario must trace to an acceptance criterion, historical Jira, behavior source, repo path, PR diff, or explicit risk.

8. **Update team test-plan memory**
   - After writing or materially changing a plan, update `team-test-plan-memory.json` and `test-plans-registry.json`.
   - Store the Jira key, plan path, review status, component/scope, APIs, error contracts, code paths, AC IDs, scenario IDs, automation coverage, related past Jiras, PR/diff refs, and remaining blockers.
   - If backend pipeline memory exists, cite the retained pipeline memory path too.

## Output Contract

- Use `references/reasoning-contract.md` as an internal evidence checklist or pipeline packet only when JSON is explicitly requested.
- For normal test-plan generation, output Markdown bullets only; do not output JSON, tables, raw RAG audits, backend trace dumps, or long evidence matrices.
- Write like an experienced manual QA engineer: clear, practical, concise, and focused on what should be tested.
- Use only these final sections, in this order:
  1. `Acceptance Criteria`
  2. `Expected Behaviour`
  3. `Scope From Git`
  4. `Code Touched`
  5. `Lines Changed`
  6. `Test Scenarios`
  7. `Past Similar Tickets`
  8. `Regression Areas`
- Keep every section as bullets. If evidence is missing, add a short blocker bullet inside the relevant section instead of creating extra sections.
- Every local repo evidence bullet must state whether the repo was fetched and whether it was clean/up to date, fast-forward pulled, or blocked by sync risk.
- Every PR/diff bullet must cite the PR URL, commit, or local git evidence. If missing, say `fix diff not inspected - user PR required`.
- Every past-ticket bullet must explain why the ticket is similar and how it changes coverage.

## Final Section Content Guide

- **Acceptance Criteria**: Rewrite Jira acceptance/sign-off conditions as tester-readable bullets. If Jira has no clear AC, add `Draft blocker: acceptance criteria missing or unclear`.
- **Expected Behaviour**: State the intended product behavior from Jira plus behavior RAG/product docs. Mark any unsupported behavior as `Unknown from current evidence`.
- **Scope From Git**: List PR/branch/commit, repo sync state, changed product area, and whether the diff was inspected. Do not infer scope from keywords alone.
- **Code Touched**: List only real files/functions/classes/components touched or directly implicated by repo scan/diff, with short QA impact.
- **Lines Changed**: Summarize added/deleted line counts and key hunks by file from PR/Git diff. If line counts are unavailable, add `Draft blocker: line-level diff not inspected`.
- **Test Scenarios**: Write 6-10 practical bullets max, priority-tagged `P0`, `P1`, or `P2`. Each bullet should include action + expected result in plain English; cover happy path, negative/boundary, permission/config/state, and fix-safety checks when relevant.
- **Past Similar Tickets**: List up to five related Jira keys with why similar and what coverage they add. If historical Jira MCP is unavailable or returns no matches, say that directly.
- **Regression Areas**: List nearby workflows/APIs/configurations/roles/browsers/data shapes/automation gaps most likely to break because of the touched code and past-ticket learning.

## Test Plan Rules

- Keep raw backend/RAG audit sections out of the final test plan.
- Keep acceptance criteria in the plan.
- Do not use tables; use compact bullet points only.
- Do not add extra headings such as `What can break`, `Likely bugs to watch`, `Fix safety checks`, `Important combinations`, `Automation`, or `Draft blockers`.
- Put fix-safety, likely-bug, important-combination, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Prefix missing-evidence bullets with `Draft blocker:` inside the relevant final section; do not create a separate blocker section.
- Never mark review-ready when current Jira MCP, behavior RAG, historical Jira MCP, required repo evidence, or PR/diff inspection is missing.
- Never silently continue as review-ready when Jira has no PR link; ask the user for the Git PR first, then keep Draft/flags if no PR is provided.
- Never create a plan without reading/updating team memory unless the file is unavailable; in that case list it as a Draft blocker/action item.
- Never rely on stale local repo evidence when a relevant repo is behind remote; fast-forward pull clean worktrees or keep the plan Draft with a repo-sync blocker.
