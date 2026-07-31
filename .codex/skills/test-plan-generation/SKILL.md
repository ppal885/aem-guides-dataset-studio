---
name: test-plan-generation
description: "Generate evidence-backed, plain-English AEM Guides QA test plans from Jira, PR, branch, commit, pasted diff, Figma design links, or user-cloned repo context. Use when Codex must create, improve, or review a manual QA test plan with acceptance criteria, expected behaviour, Git/PR scope, touched code, changed lines, test scenarios, past similar tickets, regression areas, and targeted open questions; using Jira MCP for Jira facts, GitHub MCP to discover/fetch PRs when Jira does not mention one, Figma MCP to inspect existing designs and learn UI flows when design evidence is available, `ask_dita_expert` for VM-backed RAG behaviour learning, and user cloned repos such as Starling/backend, xmleditor, new editor, guides-ui-tests, and dxml-it-tests for code and automation evidence; with strict Draft blockers when Jira, RAG, PR/diff, repo sync, design evidence, open questions, or historical evidence is missing; and no tables or noisy raw evidence dumps."
---

# Test Plan Generation

## Goal

Produce a concrete AEM Guides QA test plan that reads like a senior manual QA engineer wrote it: practical, evidence-backed, plain-English, and bullet-only. Use RAG to learn product behaviour, but do not let RAG replace Jira facts or PR diff evidence. Treat Jira UAC/acceptance criteria as the primary acceptance and sign-off contract: it defines scope, out-of-scope, expected behaviour, integration expectations, regression boundaries, and open questions.

## Operating Mode

- Work evidence-first: collect facts, normalize behaviour, retrieve RAG, inspect diff, then write scenarios.
- Apply conflict priority in this order: Jira/UAC acceptance contract > inspected PR implementation > accepted RAG documentation > Figma UI intent > cloned repo/team memory. When sources conflict, surface the contradiction as a Draft blocker instead of silently choosing.
- Derive edge cases from concrete evidence: UAC boundaries, PR diff, code branches, API contracts, configs, old automation failures, and past similar Jira history; do not invent edge cases from generic module names.
- Map integration impact for every plan: identify adjacent workflows, callers, configs, output types, permissions, and automation areas that can break even if not directly changed.
- Use exact evidence probes before broad reasoning: RAG queries, Jira searches, repo searches, and automation searches must include the precise API path, config key, UI label, DITA construct, error text, or release/version boundary whenever one is available.
- Treat setup and test data as part of QA quality: each plan must make required environment, role, config, fixture, file type, output preset, and upgrade/source-target version needs visible inside `Test Scenarios`, `Regression Areas`, or `Open Questions`.
- Keep the final answer short and tester-facing; keep raw evidence, chunk scores, backend traces, and reasoning audits internal.
- Treat the plan as `Draft` unless current Jira facts, accepted behaviour evidence, past-similar-ticket search, and required Git/PR evidence are present.
- Ask for the missing Jira text, PR URL, branch, commit, or pasted diff only when that evidence is required and unavailable.
- Use user-provided local clones when present; do not ask teammates to clone dataset-studio, copy RAG JSON, copy ChromaDB, or run old test-plan MCP tools.

## Tool Boundary

- Use `ask_dita_expert` as the only VM RAG path for AEM Guides, Experience League, DITA, DITA-OT, workflow, release-note, and configuration behaviour facts.
- Use Jira MCP first for current Jira facts and historical similar-ticket search. If Jira MCP is unavailable, use pasted Jira details and mark the Jira evidence gap.
- Use GitHub MCP to inspect a PR when Jira includes one; if Jira has no PR link, use GitHub MCP to search likely repos by Jira key, summary terms, branch names, commit messages, and PR body before asking the user for a PR.
- Use Figma MCP read-only when Jira, PR, comments, attachments, or the user provides design links, frame names, prototype links, or asks to verify against existing UX/design flow.
- Do not use or expect any generated test-plan slash command or test-plan MCP tool.
- Use connected Jira/GitHub MCPs only if available in the current session. If unavailable, rely on user-provided Jira/PR/diff text and local clones, then mark gaps as Draft blockers.
- Use connected Figma MCP only if available in the current session. If unavailable, rely on pasted screenshots/design notes and mark the Figma evidence gap.
- If a local cloned repo is used for evidence, fetch before relying on it and never stash, reset, merge, or rebase automatically.

## Required References

- Read `references/rag-query-cookbook.md` before calling or judging `ask_dita_expert` evidence.
- Read `references/pr-and-repo-evidence.md` before searching GitHub MCP, inspecting PRs, or using user-cloned repos.
- Read `references/design-evidence-flow.md` before using Figma MCP or design screenshots as evidence.
- Read `references/output-template.md` before writing the final test plan.
- Read `references/uac-reference-examples.md` when normalizing Jira UAC, writing acceptance criteria, or turning feature notes into test scenarios.
- Read `references/open-questions-catalog.md` before writing the `Open Questions` section.
- Read `references/native-aemsite-baseline-metadata.md` when Jira scope mentions Native AEM Site, baseline publishing, output preset metadata, metadata propagation, copy-to, or incremental publishing metadata.
- Read `references/quality-gate-checklist.md` before marking a plan review-ready.

## Lifecycle

### Phase 0 — Classify Input

- Identify whether the user provided Jira only, PR only, Jira + PR, branch/commit, pasted diff, or only a vague request.
- If Jira facts are missing, keep the plan Draft and ask for Jira summary/description/AC or a Jira MCP connection.
- If PR/diff evidence is missing and fix-impact claims are needed, ask for PR URL, branch, commit, or pasted diff.
- If the user only wants a lightweight draft, still mark unsupported sections with `Draft blocker:`.

### Phase 1 — Collect Jira Facts

- Use connected Jira MCP first for the target Jira whenever available; otherwise use pasted Jira details and mark that Jira MCP was unavailable.
- Extract summary, description, expected/actual behaviour, acceptance criteria/UAC, comments, labels, components, affected/fix versions, status, customer impact, attachments, linked issues, and development links.
- Treat UAC as authoritative for acceptance criteria, scope, out-of-scope, expected behaviour, integrations, regression boundaries, and unresolved open questions.
- Do not invent AC, comments, customer impact, linked PRs, or related Jira keys.
- Convert unclear AC into tester-readable bullets and keep ambiguity visible.

### Phase 2 — Normalize Behaviour

- Convert Jira text into current behaviour, expected behaviour, affected workflow, data shape, error contract, version boundary, configuration boundary, roles/permissions, user impact, and open questions.
- Build an integration impact map: direct workflow, upstream callers, downstream outputs, shared components/APIs, configs, roles/permissions, environment matrix, test-data fixtures, and automation suites likely affected.
- Derive edge cases from UAC boundaries, inspected PR branches, API contracts, config permutations, old automation failures, and past similar tickets.
- Label inferred ownership, impacted code, or workflow assumptions as inferred unless PR/repo evidence confirms them.
- Build focused search intents before retrieval: exact failure/API/config/UI label, expected workflow, boundary/config/version, and regression/automation coverage.

### Phase 3 — Retrieve Behaviour RAG

- Call `ask_dita_expert` with focused questions from normalized behaviour, not raw keyword spam.
- Run at least three focused RAG probes when behaviour matters: exact API/config/UI/construct terms, expected workflow, and regression/config/version boundary.
- Use RAG to ground expected behaviour, workflow rules, product constraints, release-note behaviour, configuration effects, and regression areas.
- If RAG conflicts with Jira/UAC, PR implementation, or Figma design intent, keep Jira/UAC primary and surface the conflict instead of hiding it.
- Prefer latest matching release docs or current Experience League pages over older release notes when both describe the same behaviour; use older release notes only for version-specific upgrade/history claims.
- Reject chunks that only share broad vocabulary such as `topic`, `map`, `assets`, `metadata`, `cloud`, `report`, `translation`, or `workflow` without proving the actual behaviour.
- Never use attribute-only DITA evidence as proof for an exact element behaviour, or generic DITA docs as proof for AEM Guides UI behaviour.
- If RAG is unavailable, noisy, or unrelated, add a Draft blocker under `Expected Behaviour` or `Regression Areas`.

### Phase 4 — Find Past Similar Tickets

- Use Jira MCP/JQL if available; otherwise use only user-provided related tickets or available team memory.
- Search with multiple narrow JQL passes by exact Jira key links, exact error text, API route, config key, workflow, UI label, data shape, version boundary, and likely code area.
- Keep at most five past tickets. For each, explain why similar and what coverage it adds.
- Reject broad results that match only generic words or unrelated automation-bulk tickets; if only noisy matches exist, say historical evidence is unavailable instead of padding the section.

### Phase 5 — Inspect Git/PR Evidence

- Prefer connected GitHub MCP for PRs. If Jira does not mention a PR, search GitHub MCP by Jira key, summary terms, branch names, commit messages, and PR body across likely AEM Guides repos before asking the user for a PR.
- Capture changed files, functions/classes/components, added/deleted line counts, key hunks, tests, config/migration changes, API/error contract changes, and gaps.
- Inspect code branches/guards, API contracts, validation paths, error handling, config defaults, and data-shape boundaries to derive edge cases and integration risks.
- Inspect user-cloned repos when available for code and automation context: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- For `guides-ui-tests` and `dxml-it-tests`, mine existing tests, skipped/flaky history, fixtures, selectors/API clients, reusable scenarios, and automation coverage gaps.
- Check known local clone paths when present, including `C:\UI TEST\guides-ui-tests`, user workspace clones, and any repo paths provided through environment variables or user context.
- For local cloned repos, run `git fetch --all --prune`, inspect `git status -sb`, and fast-forward pull only if clean and behind. If dirty, diverged, no upstream, or fetch/pull fails, keep repo claims provisional.
- Never infer Git scope from Jira keywords alone.
- If line-level diff is unavailable, write `Draft blocker: line-level diff not inspected`.

### Phase 6 — Inspect Figma Design Evidence

- Use Figma MCP when a design/prototype/frame is linked or when the Jira is UI-flow heavy and the user says Figma should be used.
- Learn the existing flow before writing scenarios: entry point, primary path, alternate path, empty/error/loading states, dialogs, toasts, permissions, responsive states, and component variants.
- Compare design evidence with Jira UAC, RAG product behaviour, and PR implementation; call out contradictions as Draft blockers in the affected section.
- Do not treat Figma as proof of backend/API behaviour, permissions, versioning, or persistence unless Jira/PR/RAG also supports it.
- If Figma MCP or design access is missing for a design-dependent ticket, write `Draft blocker: Figma design evidence not inspected`.

### Phase 7 — Design Test Scenarios

- Write 6-10 scenarios maximum, priority-tagged `P0`, `P1`, or `P2`.
- Each scenario must include action + expected result in one plain-English bullet.
- Cover happy path, negative/boundary, role/permission, configuration, data-shape, environment matrix, setup/test-data fixture, upgrade/version, API contract, and fix-safety checks when relevant.
- Every P0/P1 scenario must trace to Jira AC, accepted RAG, PR diff, Figma flow evidence, past Jira learning, or an explicit high-risk regression.
- Include integration-impact scenarios when the ticket touches shared APIs, shared UI components, configs, publishing paths, editor flows, translation flows, upload/status flows, review flows, or automation infrastructure.

### Phase 8 — Capture Open Questions

- Capture only questions that materially affect QA sign-off, expected behaviour, configuration, environment setup, or scenario coverage.
- Ask permission, role, XML Editor config, AEM config, translation config, DITA, and DITA-OT output questions when the Jira domain requires them.
- For on-premise release, service pack, or upgrade tickets, always ask upgrade-impact questions when not answered: source/target versions, config migration, custom UI config retention, changed defaults, manual post-upgrade steps, backward compatibility, and cloud/on-prem parity.
- For publishing/output tickets, include DITA-OT, PDF, HTML5, preset, transformation, and output validation questions when not answered by Jira/RAG/PR.
- Do not ask generic questions already answered by Jira, RAG, Figma, PR, or repo evidence.
- If there are no meaningful unknowns, write `No open questions from current evidence`.

### Phase 9 — Decide Draft vs Review-Ready

- Use `Draft blocker:` bullets inside the affected final section; do not create a separate blocker section.
- Keep Draft if Jira facts, accepted RAG, historical Jira search, PR/diff, line counts, repo sync, required Figma design evidence, or sign-off-critical open questions are missing and required for confidence.
- Mark review-ready only when evidence supports expected behaviour, scope, code impact, test scenarios, regression areas, and no sign-off-critical open question is unresolved.

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
  9. `Open Questions`

## Section Rules

- **Acceptance Criteria**: Rewrite Jira AC/sign-off conditions as tester-readable bullets. If unclear, add `Draft blocker: acceptance criteria missing or unclear`.
- **Expected Behaviour**: State intended behaviour from Jira plus accepted `ask_dita_expert` and Figma design-flow evidence. If unsupported, write `Unknown from current evidence`.
- **Scope From Git**: List Jira development-link source, GitHub MCP PR-discovery result, PR/branch/commit, repo sync state, changed product area, whether diff was inspected, and Figma design evidence state when applicable.
- **Code Touched**: List only real files/functions/classes/components touched or directly implicated by PR/repo scan, with short QA impact.
- **Lines Changed**: Summarize added/deleted line counts and key hunks by file. If unavailable, add `Draft blocker: line-level diff not inspected`.
- **Test Scenarios**: Keep 6-10 practical P0/P1/P2 bullets, each with action + expected result; include Figma-observed UI states when design evidence exists.
- **Past Similar Tickets**: List up to five Jira keys with similarity reason and coverage impact. If unavailable, say so directly.
- **Regression Areas**: List nearby workflows, APIs, configs, roles, browsers, data shapes, design states, component variants, upgrade paths, integration impact, and automation coverage gaps likely to break.
- **Open Questions**: List targeted unanswered questions by domain; include permission/role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5, and on-premise upgrade-impact questions only when relevant. If none, say `No open questions from current evidence`.

## Hard Rules

- Keep acceptance criteria in the plan.
- Do not add extra headings such as `What can break`, `Likely bugs`, `Fix safety`, `Important combinations`, `Automation`, or `Draft blockers`.
- Put likely bugs, fix-safety, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Never call a plan `proper RAG-backed` when evidence is generic, unrelated, unavailable, or only keyword-matched.
- Never mark review-ready when required Jira, RAG, past-ticket, PR/diff, line-count, repo-sync, design evidence, or sign-off-critical open questions are missing.
