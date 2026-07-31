---
name: test-plan-generation
description: "Generate evidence-backed, plain-English AEM Guides QA test plans and UACs from Jira, Dynamics/support incidents, customer escalations, PRs, branches, commits, pasted diffs, logs, screenshots, Figma designs, or user-cloned repos. Use for pre-development UAC planning, implementation review, and post-fix validation; inspect available product clones such as Starling/backend, xmleditor, and new editor for current or changed implementation, plus guides-ui-tests and dxml-it-tests for automation evidence; use Jira/GitHub/Figma MCPs and `ask_dita_expert` when available; apply lifecycle-stage-specific evidence requirements so missing PRs and line counts are not blockers before development starts; and output concise bullet-only plans without tables or raw evidence dumps."
---

# Test Plan Generation

## Goal

Produce a concrete AEM Guides QA test plan that reads like a senior manual QA engineer wrote it: practical, evidence-backed, plain-English, and bullet-only. Adapt evidence requirements to the lifecycle stage. Use RAG to learn product behaviour, but do not let RAG replace issue facts, UAC, current implementation evidence, or an available fix diff. Treat Jira UAC, pasted acceptance criteria, or a normalized support-incident acceptance contract as the primary scope and sign-off contract.

## Operating Mode

- Work evidence-first: classify lifecycle stage, collect facts, inspect available clones, normalize behaviour, retrieve RAG, inspect an available diff when stage-relevant, then write scenarios.
- Apply conflict priority in this order: Jira/UAC or normalized incident acceptance contract > inspected fix implementation when one exists > accepted RAG documentation > Figma UI intent > verified current product clone > automation clone > team memory. Surface material contradictions instead of silently choosing.
- Derive edge cases from concrete evidence: UAC boundaries, PR diff, code branches, API contracts, configs, old automation failures, and past similar Jira history; do not invent edge cases from generic module names.
- Map integration impact for every plan: identify adjacent workflows, callers, configs, output types, permissions, and automation areas that can break even if not directly changed.
- Use exact evidence probes before broad reasoning: RAG queries, Jira searches, repo searches, and automation searches must include the precise API path, config key, UI label, DITA construct, error text, or release/version boundary whenever one is available.
- Treat setup and test data as part of QA quality: each plan must make required environment, role, config, fixture, file type, output preset, and upgrade/source-target version needs visible inside `Test Scenarios`, `Regression Areas`, or `Open Questions`.
- Keep the final answer short and tester-facing; keep raw evidence, chunk scores, backend traces, and reasoning audits internal.
- Judge readiness against the lifecycle stage: UAC-ready before development, implementation-review-ready while code is changing, or QA-sign-off-ready after a fix is available.
- Ask for a PR, branch, commit, or pasted diff only in implementation-review or post-fix stages, or when the user explicitly requests changed-code claims.
- Inspect every relevant user-provided or discoverable local clone before declaring code or automation evidence unavailable; do not ask teammates to clone dataset-studio, copy RAG JSON, copy ChromaDB, or run old test-plan MCP tools.

## Tool Boundary

- Use `ask_dita_expert` as the only VM RAG path for AEM Guides, Experience League, DITA, DITA-OT, workflow, release-note, and configuration behaviour facts.
- Use Jira MCP first for current Jira facts and historical similar-ticket search. If Jira MCP is unavailable, use pasted Jira, Dynamics, support-case, customer-escalation, log, screenshot, and investigation details; state the evidence source without automatically blocking a pre-development UAC.
- When the Dataset Studio app or local repo is available, use its `jira_qa` related-ticket retrieval as the first historical-learning candidate source, then validate mutable Jira facts with Jira MCP. Treat indexed learning as historical QA evidence only, never as current Jira truth or product documentation.
- Use GitHub MCP to inspect or discover a PR only when development may have started, a fix is claimed, or changed-code evidence is requested. Do not search for or request a PR when the issue is explicitly pre-development and no implementation exists.
- Use Figma MCP read-only when Jira, PR, comments, attachments, or the user provides design links, frame names, prototype links, or asks to verify against existing UX/design flow.
- Do not use or expect any generated test-plan slash command or test-plan MCP tool.
- Use connected Jira/GitHub MCPs only if available in the current session. If unavailable, rely on user-provided evidence and local clones, then apply only stage-relevant gaps or blockers.
- Use connected Figma MCP only if available in the current session. If unavailable, rely on pasted screenshots/design notes and mark the Figma evidence gap.
- If a local cloned repo is used for evidence, fetch before relying on it and never stash, reset, merge, or rebase automatically.

## Required References

- Read `references/rag-query-cookbook.md` before calling or judging `ask_dita_expert` evidence.
- Read `references/pr-and-repo-evidence.md` before searching GitHub MCP, inspecting PRs, or using user-cloned repos.
- Read `references/design-evidence-flow.md` before using Figma MCP or design screenshots as evidence.
- Read `references/output-template.md` before writing the final test plan.
- Read `references/uac-reference-examples.md` when normalizing Jira UAC, writing acceptance criteria, or turning feature notes into test scenarios.
- Read `references/review-workflow-uac.md` when Jira scope mentions review tasks, review comments, review right panel, comment import, side-by-side review diff, task dropdowns, current/closed task state, or author incorporation of review comments.
- Read `references/open-questions-catalog.md` before writing the `Open Questions` section.
- Read `references/native-aemsite-baseline-metadata.md` when Jira scope mentions Native AEM Site, baseline publishing, output preset metadata, metadata propagation, copy-to, or incremental publishing metadata.
- Read `references/quality-gate-checklist.md` before marking a plan review-ready.

## Lifecycle

### Phase 0 — Classify Stage And Input

- Classify the lifecycle stage before applying evidence gates:
  - `Pre-Development UAC`: acceptance criteria are being created or refined and development has not started.
  - `Implementation Review`: a branch, commit, PR, patch, or active implementation exists and code-impact review is required.
  - `Post-Fix Validation`: a candidate fix/build exists and QA sign-off or regression validation is required.
- Classify the input source: Jira, Dynamics/support case, customer escalation, logs, screenshots, investigation notes, PR, branch/commit, pasted diff, Figma, local clones, or a combination.
- Infer `Pre-Development UAC` when the user states that UAC is not final, development has not started, or no code change exists. In this stage, missing PR, changed files, and line counts are `Not applicable`, not Draft blockers.
- Treat operational incidents as valid pre-development inputs when they include customer context, symptoms, logs, investigation findings, recovery actions, similar incidents, and an end goal. Normalize these facts into an acceptance contract and targeted open questions.
- If the stage is unclear, infer it from explicit evidence and state the assumption under `Scope From Git`; ask only when the distinction materially changes the plan.
- Keep a pre-development plan Draft only for missing sign-off-critical UAC decisions, unsupported expected behaviour, missing required product-clone evidence, or unresolved environment/test-data constraints—not merely because implementation does not exist.

### Phase 1 — Collect Issue Facts

- Use connected Jira MCP first for a Jira-backed request whenever available; otherwise use pasted Jira, Dynamics, support-case, customer-escalation, logs, screenshots, and investigation details and identify the source.
- Extract summary, description, expected/actual behaviour, acceptance criteria/UAC, customer and business impact, environment, product/version, logs, error text, affected assets/workflows, actions already taken, requested engineering help, attachments, linked issues, and development links when present.
- Treat supplied UAC as authoritative. When UAC does not exist, derive a proposed acceptance contract from the problem statement and end goal, label unresolved product decisions as open questions, and do not pretend proposed criteria are already approved.
- Do not invent AC, comments, customer impact, linked PRs, or related Jira keys.
- Convert unclear AC into tester-readable bullets and keep ambiguity visible.

### Phase 2 — Normalize Behaviour

- Convert Jira text into current behaviour, expected behaviour, affected workflow, data shape, error contract, version boundary, configuration boundary, roles/permissions, user impact, and open questions.
- Build an integration impact map: direct workflow, upstream callers, downstream outputs, shared components/APIs, configs, roles/permissions, environment matrix, test-data fixtures, and automation suites likely affected.
- Derive edge cases from UAC boundaries, inspected PR branches, API contracts, config permutations, old automation failures, and past similar tickets.
- Label inferred ownership, impacted code, or workflow assumptions as inferred unless PR/repo evidence confirms them.
- Build focused search intents before retrieval: exact failure/API/config/UI label, expected workflow, boundary/config/version, and regression/automation coverage.

#### Operational Incident And Recovery UAC Rules

- Use these rules for Dynamics/support incidents, production escalations, stuck jobs, queue blockage, workflow failures, cleanup requests, performance degradation, concurrency failures, and customer-restoration plans.
- Separate immediate remediation from permanent product behavior: backend cleanup, service restoration, workflow/config correction, code safeguard, resource change, and automation must each have explicit in-scope or out-of-scope status.
- Convert the end goal into proposed acceptance criteria, but keep unapproved engineering choices visible as open questions rather than presenting them as decided UAC.
- Define the exact affected output type, workflow, environment/build, target paths, job IDs/UUIDs, queue states, customer-like fixture size, and normal-versus-failure timing baseline.
- Require terminal-state contracts for success, failure, cancel, retry exhaustion, and recovery; define the maximum allowed duration for Waiting, Executing, Post Publishing, cancellation requested, or equivalent states.
- Define concurrency behavior for same map, same preset, same destination, overlapping destinations, and unrelated destinations: serialize, lock, retry, fail fast, or isolate.
- Define partial-write behavior: rollback, reuse, overwrite, cleanup, idempotent retry, duplicate prevention, orphan prevention, and preservation of previously valid output.
- Define queue isolation and fairness: one failed job must not indefinitely block unrelated jobs, and recovery must specify whether successors auto-resume or require manual restart.
- Define cleanup safety: exact nodes/workflows targeted, correlation evidence, backup, approval, audit trail, unrelated-state preservation, rollback, and post-cleanup verification.
- Define restart and failover behavior for author pod restart, workflow restart, deployment, timeout, network interruption, and repeated cancellation.
- Define performance and resource acceptance separately: completion SLA, dataset scale, heap/pod limits, indexing state, CPU/memory evidence, and criteria for deciding whether a resource increase is required.
- Define observability: required correlation IDs, job/output/workflow UUIDs, target path, stage timings, retry count, terminal reason, actionable errors, and sensitive-data redaction.
- Verify the final generated output, not only DITA-OT/build success or UI status: page/file count, links, assets, metadata, navigation, history nodes, workflow completion, and absence of partial/orphan state as applicable.
- Inspect product clones using exact stack-trace classes, workflow model names, JCR paths, APIs, config keys, and error strings; inspect automation clones for timeout, polling, cancel, cleanup, concurrency, performance, and recovery gaps.
- Keep destructive production reproduction out of scope unless explicitly approved; prefer a production-equivalent clone and engineering-approved cleanup validation.

#### Translation Project API UAC Reference

- Use this UAC when scope covers an automation API that creates a translation project for a supplied DITA map and selected filters.
- Require support for project types `newTranslationProject`, `xliffTranslationProject`, `newMultiLingualTranslationProject`, `addToExistingProject`, and `newScopingTranslationProject`.
- For `latestVersion`, resolve forward references from the latest saved version of the DITA map and exclude working-copy changes.
- For `baseline`, resolve forward references exactly as they existed when the specified baseline was created.
- For `versionAsOfDate`, resolve forward references exactly as they existed at the supplied date and time.
- Cover `referenceType` values `Direct` and `Indirect`.
- Cover `fileType` values `Map`, `Topic`, and `Others`.
- Cover `documentState` values `Draft`, `In-Review`, and `Reviewed`.
- Cover `translationStatus` values `Out of Date`, `In Progress`, `In Sync`, `Out of Sync`, and `Missing copy`.
- Require the API request to accept the DITA map, project title, project type, language list, version selection and required version value, and selected filters.
- Verify the API creates missing target-language folders before creating or updating the translation project.
- Derive positive, negative, boundary, filter-combination, version-resolution, missing-language-folder, permissions, idempotency, validation, error-contract, and automation-consumability scenarios from this UAC.
- Keep unspecified API details as open questions, including endpoint and method, request/response schema, baseline identifier format, date/time zone and inclusivity, filter combination semantics, existing-project identifier, duplicate project-title behavior, partial-failure rollback, folder naming/location, and permissions.

#### EDS GitHub And GitLab Publishing Profile UAC Reference

- Use this UAC when scope covers creating or using EDS Publishing Profiles with GitHub or GitLab repositories.
- Support GitHub Cloud public/private, GitLab Cloud public/private, self-hosted GitHub Enterprise, and self-hosted GitLab repositories.
- Provide a `Git Provider` selector with GitHub and GitLab options, dynamically update provider-specific UI fields, and default the server URL to the self-hosted GitLab URL when GitLab is selected.
- Enforce mandatory-field validation and enable `Save` only after all required fields are present and authentication succeeds; never persist an unauthenticated profile.
- Support OAuth authentication for both providers using Client ID, Client Secret, and token exchange.
- Show clear errors for invalid repository details or credentials, expired/revoked tokens, insufficient or read-only permissions, authentication failures, network interruption, API timeout, and server failure.
- Prevent publishing when authentication fails or repository permissions are insufficient.
- Verify `Push to Live` commits and pushes content to the configured repository and branch for both providers, while preserving the existing EDS workflow and downstream EDS pipeline trigger.
- Verify Publishing Profile APIs behave consistently for GitHub and GitLab.
- Preserve backward compatibility for existing GitHub publishing profiles, Push to Live, APIs, logging, upgrades, and all supported AEM Guides Cloud versions.
- Preserve existing publishing profiles during upgrades and confirm no impact to Salesforce publishing.
- Verify the required AEM Admin suffix configuration change from `HTML` to `HTM`; keep the exact setting, scope, default, and upgrade behavior as open questions when Jira does not define them.
- Verify supported content publishes through both providers without content loss or formatting issues, including DITA topics, DITAMAPs, Bookmaps, Markdown, images, multimedia, MathML, tables, code blocks, cross-references, keyrefs, conrefs, conditional content, multilingual content, and other supported assets.
- Require logging for authentication, token exchange, publishing, commit creation, push operations, API failures, and retries when applicable.
- Verify Client Secret, Access Token, and OAuth Token values are never logged, exposed in UI errors, or returned through unsafe API responses.
- Derive positive, negative, provider/platform matrix, public/private repository, permission, authentication lifecycle, UI-state, API-contract, upgrade, logging/redaction, retry, pipeline-trigger, content-fidelity, and regression scenarios from this UAC.
- Keep unspecified details as open questions, including exact OAuth grant/token-exchange flow, redirect URI, scopes, token storage/refresh, provider-specific required fields, self-hosted TLS/proxy requirements, GitLab default URL behavior, branch protections, retry policy, rollback after partial commit/push failure, supported file-size limits, and the supported AEM Guides Cloud version matrix.

### Phase 3 — Retrieve Behaviour RAG

- Call `ask_dita_expert` with focused questions from normalized behaviour, not raw keyword spam.
- Run at least three focused RAG probes when behaviour matters: exact API/config/UI/construct terms, expected workflow, and regression/config/version boundary.
- Use RAG to ground expected behaviour, workflow rules, product constraints, release-note behaviour, configuration effects, and regression areas.
- If RAG conflicts with Jira/UAC, PR implementation, or Figma design intent, keep Jira/UAC primary and surface the conflict instead of hiding it.
- Prefer latest matching release docs or current Experience League pages over older release notes when both describe the same behaviour; use older release notes only for version-specific upgrade/history claims.
- Reject chunks that only share broad vocabulary such as `topic`, `map`, `assets`, `metadata`, `cloud`, `report`, `translation`, or `workflow` without proving the actual behaviour.
- Never use attribute-only DITA evidence as proof for an exact element behaviour, or generic DITA docs as proof for AEM Guides UI behaviour.
- If RAG is unavailable, noisy, or unrelated, state that evidence status under `Expected Behaviour` or `Regression Areas`. Add a Draft blocker only when the affected behaviour is not already supported by the acceptance contract, exact logs, verified current implementation, design evidence, or another authoritative source.

### Phase 4 — Find Past Similar Tickets

- Use the app's indexed Jira learning retrieval (`jira_qa`) when available, then use Jira MCP/JQL to validate current status, links, comments, and any facts that may have changed. If indexed retrieval is unavailable, use Jira MCP/JQL; otherwise use only user-provided related tickets or available team memory.
- Prefer `learning_behavior_chunk`, acceptance-criteria, resolution/RCA, and test-evidence hits over summary-only matches when their structural evidence is comparable.
- Preserve each learning hit's confidence, historical outcome, verified-fix flag, behavior contract, root cause, QA oracle, and regression risks. A `caution` or non-fix outcome is a risk signal only and must never define current expected behavior.
- Reuse a historical behavior contract or QA oracle only when the outcome is an implemented fix and confidence is `medium` or `high`; keep current Jira/UAC authoritative.
- Search with multiple narrow JQL passes by exact Jira key links, exact error text, API route, config key, workflow, UI label, data shape, version boundary, and likely code area.
- Keep at most five past tickets. For each, explain why similar and what coverage it adds.
- Reject broad results that match only generic words or unrelated automation-bulk tickets; if only noisy matches exist, say historical evidence is unavailable instead of padding the section.

### Phase 5 — Inspect Clones And Available Git Changes

- Always inspect every relevant available clone, regardless of lifecycle stage: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- Check user-provided workspace roots, environment variables, common teammate paths, and known paths such as `C:\UI TEST\guides-ui-tests` and `C:\UI TEST\dxml-it-tests` before declaring a clone unavailable.
- For each clone, run `git fetch --all --prune`, inspect `git status -sb`, and fast-forward pull only if clean and behind. If dirty, diverged, detached, without upstream, or fetch/pull fails, do not alter the worktree; use verified remote refs when possible and label claims provisional.
- In `Pre-Development UAC`, inspect product clones to identify the current implementation directly implicated by exact classes, workflow names, API paths, config keys, error strings, logs, or UI labels. Report these as `Current implementation implicated`, never as changed code.
- In `Pre-Development UAC`, inspect automation clones for existing happy-path, negative, concurrency, recovery, role/config, performance, and regression coverage. Missing PR/diff and line counts are `Not applicable — development has not started`.
- In `Implementation Review`, inspect the branch/commit/PR diff and capture changed files, functions/classes/components, added/deleted counts, key hunks, tests, config/migration changes, API/error contracts, and gaps. Also compare changed code with the current implementation and existing automation.
- In `Post-Fix Validation`, inspect the exact candidate-fix diff/build source and map changed branches, guards, retries, persistence, cleanup, errors, and tests to fix-safety and regression scenarios.
- Prefer connected GitHub MCP for a referenced PR. If development is expected but Jira has no PR link, search by Jira key, summary, branch, commit message, and PR body before asking for a PR.
- For `guides-ui-tests` and `dxml-it-tests`, mine existing tests, skipped/flaky history, fixtures, selectors/API clients, reusable scenarios, polling/timeouts, cleanup helpers, and automation gaps.
- Never label files as changed without a real diff. Never infer current implementation from generic Jira keywords; require exact repo matches or label the area inferred.
- If an implementation-stage diff is unavailable, add `Draft blocker: implementation diff not inspected`. Do not emit this blocker in pre-development.

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
- Every P0/P1 scenario must trace to Jira AC, accepted RAG, PR diff, Figma flow evidence, a medium/high implemented-fix Jira learning oracle, or an explicit high-risk regression. Cautionary/non-fix Jira history may justify exploration but not a sign-off expectation.
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
- For `Pre-Development UAC`, mark UAC-ready when issue facts, proposed acceptance criteria, current product-clone evidence where available, automation evidence where available, expected-behaviour support, regression areas, test-data/environment needs, and sign-off decisions are sufficiently explicit. PRs, changed files, and line counts are not required.
- For `Implementation Review`, mark review-ready only when the implementation diff, changed files, line counts, current-code comparison, expected behaviour, test scenarios, and integration impact are inspected.
- For `Post-Fix Validation`, mark QA-sign-off-ready only when the candidate fix/build, changed code, acceptance coverage, regression evidence, required environment matrix, and sign-off-critical questions are resolved.
- RAG or historical search unavailability is a blocker only when the missing evidence is necessary to establish a disputed or otherwise unsupported behaviour claim. Do not block a well-supported pre-development UAC merely because an optional source is unavailable.
- Dirty or unavailable clones block only claims that depend on those clones. Keep verified evidence and mark dependent findings provisional instead of downgrading every section automatically.

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
- **Scope From Git**: Start with lifecycle stage and readiness target. List issue/development-link source, relevant clone discovery and sync state, GitHub MCP/PR status only when stage-relevant, current or changed product area, diff-inspection state, and Figma evidence state when applicable.
- **Code Touched**: In pre-development, write `No code changes yet — development has not started`, then list exact current files/functions/classes/workflows directly implicated by product-clone or log evidence under `Current implementation implicated`; keep inferred areas labeled. In implementation/post-fix stages, list only files/functions/classes/components actually changed or directly implicated by the inspected diff, plus short QA impact.
- **Lines Changed**: In pre-development, write `Not applicable — development has not started`; never add a line-level Draft blocker. In implementation/post-fix stages, summarize added/deleted counts and key hunks by file; if unavailable, add `Draft blocker: implementation diff not inspected`.
- **Test Scenarios**: Keep 6-10 practical P0/P1/P2 bullets, each with action + expected result; include Figma-observed UI states when design evidence exists.
- **Past Similar Tickets**: List up to five Jira keys with similarity reason, historical outcome/confidence, reusable lesson or caution, and concrete coverage impact. If unavailable, say so directly.
- **Regression Areas**: List nearby workflows, APIs, configs, roles, browsers, data shapes, design states, component variants, upgrade paths, integration impact, and automation coverage gaps likely to break.
- **Open Questions**: List targeted unanswered questions by domain; include permission/role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5, and on-premise upgrade-impact questions only when relevant. If none, say `No open questions from current evidence`.

## Hard Rules

- Keep acceptance criteria in the plan.
- Always state the lifecycle stage and apply its evidence requirements consistently.
- Always inspect relevant available product clones for current implementation and automation clones for coverage before declaring code or automation evidence unavailable.
- Never treat missing PR, changed files, or line counts as a blocker in `Pre-Development UAC`.
- Never present current implementation found in a clone as changed code unless a real diff proves the change.
- Do not add extra headings such as `What can break`, `Likely bugs`, `Fix safety`, `Important combinations`, `Automation`, or `Draft blockers`.
- Put likely bugs, fix-safety, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Never call a plan `proper RAG-backed` when evidence is generic, unrelated, unavailable, or only keyword-matched.
- Never mark a plan ready when evidence required for its declared lifecycle stage or a sign-off-critical decision is missing. Do not impose implementation-stage PR, diff, or line-count requirements on pre-development UAC work.
