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
- Clone discovery is not limited to the current workspace. Follow the bounded Windows/Mac/Linux discovery protocol in `references/pr-and-repo-evidence.md`, resolve wrapper directories to the nested `.git` repository, and list the paths actually inspected.

## Tool Boundary

- Use `ask_dita_expert` as the only VM RAG path for AEM Guides, Experience League, DITA, DITA-OT, workflow, release-note, and configuration behaviour facts.
- Use Jira MCP first for current Jira facts and historical similar-ticket search. If Jira MCP is unavailable, use pasted Jira, Dynamics, support-case, customer-escalation, log, screenshot, and investigation details; state the evidence source without automatically blocking a pre-development UAC.
- When the Dataset Studio app or local repo is available, use its `jira_qa` related-ticket retrieval as the first historical-learning candidate source, then validate mutable Jira facts with Jira MCP. Treat indexed learning as historical QA evidence only, never as current Jira truth or product documentation.
- Use GitHub MCP to inspect or discover a PR only when development may have started, a fix is claimed, or changed-code evidence is requested. Do not search for or request a PR when the issue is explicitly pre-development and no implementation exists.
- When live Jira contains a development link, PR URL, branch, commit, or pull-request reference, treat it as mandatory implementation evidence for `Implementation Review` and `Post-Fix Validation`. Use GitHub MCP when connected; do not stop at Jira development metadata or a PR title.
- Use Figma MCP read-only when Jira, PR, comments, attachments, or the user provides design links, frame names, prototype links, or asks to verify against existing UX/design flow.
- Do not use or expect any generated test-plan slash command or test-plan MCP tool.
- Use connected Jira/GitHub MCPs only if available in the current session. If unavailable, rely on user-provided evidence and local clones, then apply only stage-relevant gaps or blockers.
- For automation evidence, inspect synchronized local clones first because they support exact code, fixture, helper, tag, and history searches. Use GitHub MCP to inspect automation repositories when a local clone is unavailable or stale, to inspect automation PRs/branches, and to validate current remote files or default-branch coverage. Combine both sources when available and state which revision was inspected.
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
- Before returning any plan, write the proposed final Markdown to a UTF-8 temporary file and run `python scripts/validate_test_plan.py <draft-file>`. If it reports any error, repair the draft and rerun until it exits successfully. Do not show an invalid draft as the final answer or claim the quality gate passed without this validation.

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
- When the user supplies a concrete Jira key, fetch that issue before drafting the plan. Do not silently describe the source as pasted text, and do not continue from historical RAG as though it were the live issue. If Jira MCP cannot fetch the key, state the exact Jira evidence failure; use pasted issue content only when the user supplied it.
- Treat placeholders such as `GUIDES-XXXXX` as missing input, not as a real Jira key. Ask for the actual key instead of producing a Jira-backed plan.
- Extract summary, description, expected/actual behaviour, acceptance criteria/UAC, customer and business impact, environment, product/version, logs, error text, affected assets/workflows, actions already taken, requested engineering help, attachments, linked issues, and development links when present.
- Treat supplied UAC as authoritative. When UAC does not exist, derive a proposed acceptance contract from the problem statement and end goal, label every derived criterion `[Proposed]`, label Jira criteria `[Confirmed]`, and do not pretend proposed criteria are already approved.
- Historical observations, completed cleanup steps, support comments, and previously successful recovery are evidence for `Expected Behaviour` or `Incident recovery validation`; they are not Jira-authored AC and must not receive `[Confirmed]` when the native Jira/UAC acceptance field is empty.
- Do not invent AC, comments, customer impact, linked PRs, or related Jira keys.
- Assign stable IDs (`AC-01`, `AC-02`, ...) to every acceptance criterion. Write each criterion as an independently testable product contract containing input or precondition, behavior, and observable outcome; do not write acceptance criteria as generic `Verify...` test instructions.
- Split compound requirements when their outcomes can pass or fail independently. Preserve every named enum, mode, project type, provider, state, filter, version boundary, and failure outcome either as its own criterion or as an explicit exhaustive matrix inside one criterion.
- Convert unclear AC into tester-readable product contracts and keep ambiguity visible. Never infer defaults for omitted filters, duplicate handling, reference classification, rollback, response codes, or status semantics; move undecided behavior to `Open Questions`.

### Phase 2 — Normalize Behaviour

- Convert Jira text into current behaviour, expected behaviour, affected workflow, data shape, error contract, version boundary, configuration boundary, roles/permissions, user impact, and open questions.
- Build an integration impact map: direct workflow, upstream callers, downstream outputs, shared components/APIs, configs, roles/permissions, environment matrix, test-data fixtures, and automation suites likely affected.
- Derive edge cases from UAC boundaries, inspected PR branches, API contracts, config permutations, old automation failures, and past similar tickets.
- Label inferred ownership, impacted code, or workflow assumptions as inferred unless PR/repo evidence confirms them.
- Build focused search intents before retrieval: exact failure/API/config/UI label, expected workflow, boundary/config/version, and regression/automation coverage.

#### Operational Incident And Recovery UAC Rules

- Use these rules for Dynamics/support incidents, production escalations, stuck jobs, queue blockage, workflow failures, cleanup requests, performance degradation, concurrency failures, and customer-restoration plans.
- Separate immediate remediation from permanent product behavior: backend cleanup, service restoration, workflow/config correction, code safeguard, resource change, and automation must each have explicit in-scope or out-of-scope status.
- Do not turn a destructive operational procedure into a product acceptance criterion. Node deletion, workflow termination, pod restart, manual queue repair, and similar one-time engineering actions belong under `Test Scenarios` as an `Incident recovery validation` bullet; acceptance criteria may state only the observable restoration or permanent product contract.
- For mixed-lifecycle incidents, distinguish `Incident recovery validation` from the pre-development product UAC. A closed incident or successful cleanup does not confirm that a proposed concurrency, retry, cancellation, queue, or status-consistency safeguard has been implemented.
- Convert the end goal into proposed acceptance criteria, but keep unapproved engineering choices visible as open questions rather than presenting them as decided UAC.
- Define the exact affected output type, workflow, environment/build, target paths, job IDs/UUIDs, queue states, customer-like fixture size, and normal-versus-failure timing baseline.
- Require terminal-state contracts for success, failure, cancel, retry exhaustion, and recovery; define the maximum allowed duration for Waiting, Executing, Post Publishing, cancellation requested, or equivalent states.
- Define concurrency behavior for same map, same preset, same destination, overlapping destinations, and unrelated destinations: serialize, lock, retry, fail fast, or isolate.
- Define partial-write behavior: rollback, reuse, overwrite, cleanup, idempotent retry, duplicate prevention, orphan prevention, and preservation of previously valid output.
- Define queue isolation and fairness: one failed job must not indefinitely block unrelated jobs, and recovery must specify whether successors auto-resume or require manual restart.
- Define cleanup safety: exact nodes/workflows targeted, correlation evidence, backup, approval, audit trail, unrelated-state preservation, rollback, and post-cleanup verification.
- Define restart and failover behavior for author pod restart, workflow restart, deployment, timeout, network interruption, and repeated cancellation.
- Define performance and resource acceptance separately: completion SLA, dataset scale, heap/pod limits, indexing state, CPU/memory evidence, and criteria for deciding whether a resource increase is required.
- Never convert an observed customer duration, approximate normal runtime, topic count, heap recommendation, or support anecdote into a hard pass/fail oracle unless Jira/UAC, an approved SLA, or a controlled benchmark defines the dataset, environment, repetitions, percentile, and threshold. Otherwise treat it as a measured baseline or an open question.
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
- Include both resolved historical bugs that provide reusable RCA/test oracles and open known bugs that can affect execution, expected results, environment choice, or sign-off. Validate current status with Jira MCP before calling a bug open, closed, fixed, duplicated, deferred, or regressed.
- For each selected Jira bug, capture the key, similarity reason, current status/resolution, affected/fix version when available, historical root cause or behavior contract, reusable test evidence, and the exact scenario or regression area it changes. Do not expose raw retrieval scores.
- Record the actual JQL/search intents used and whether each historical fact came from current Jira fields, comments, linked test evidence, or indexed history. Write `not available in current evidence` for missing fix versions, affected versions, RCA, or test evidence; never silently omit those fields or infer them from ticket status.
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
- For every referenced or confidently discovered PR, inspect through GitHub MCP: repository, base/head branches, PR state, commits, changed files, complete diff hunks, added/deleted lines, review comments and unresolved threads when available, checks/test results, and linked Jira context. Read the implementation branches and error paths, not only filenames.
- Map each relevant PR hunk and branch to acceptance criteria, test scenarios, regression areas, logging/error behavior, permissions/configuration, persistence/cleanup, concurrency/retry, backward compatibility, and automation impact. Report unrelated or generated-file changes separately and do not inflate QA scope from them.
- If GitHub MCP is unavailable, inspect the exact PR/branch/commit from an available local clone or user-provided diff. In implementation/post-fix stages, do not claim deep PR analysis when only Jira metadata or a summary was available.
- For `guides-ui-tests` and `dxml-it-tests`, mine existing tests, skipped/flaky history, fixtures, selectors/API clients, reusable scenarios, polling/timeouts, cleanup helpers, and automation gaps.
- Also inspect relevant editor E2E or repository-specific automation suites discovered locally or through GitHub MCP. Search by Jira key, AC terms, endpoint and request fields, UI labels, project types, enum values, config keys, workflow names, failure text, and exact implementation symbols.
- Build an AC-to-automation map internally: `Covered`, `Partially covered`, `Not covered`, or `Not suitable for automation`. For covered items, retain exact repository, file, scenario/test method, helper/fixture, layer, and revision. For gaps, recommend the correct UI/API/integration layer, reusable fixture/helper, data setup, cleanup, assertions, tags/suite, and whether a new test or extension is needed.
- Classify automation by the complete AC contract, not by feature-name similarity. A happy-path publish test does not partially cover post-cleanup recovery, concurrency safety, orphan-state cancellation, queue draining, or cross-dashboard consistency unless it creates that precondition and asserts that outcome. Use `Partially covered` only when an existing test proves a named clause of the same AC; otherwise use `Not covered` and list reusable helpers separately.
- A gap recommendation must name the exact repository and candidate test file/class/method, automation layer, reusable client/helper/fixture, deterministic failure or state-injection mechanism, data setup, polling endpoint and terminal oracle, timeout source, output-integrity assertions, cleanup/rollback, suite/tags, and whether to extend or add a test. If the repository cannot safely create the required state, say which test hook or harness capability is needed instead of prescribing manual production mutation.
- Do not claim zero automation from one repository or broad keyword search. Search every relevant discovered automation clone and GitHub automation repository before declaring a gap; distinguish missing coverage from undiscovered, stale, skipped, flaky, quarantined, or inaccessible coverage.
- Never label files as changed without a real diff. Never infer current implementation from generic Jira keywords; require exact repo matches or label the area inferred.
- If an implementation-stage diff is unavailable, add `Draft blocker: implementation diff not inspected`. Do not emit this blocker in pre-development.

### Phase 6 — Inspect Figma Design Evidence

- Use Figma MCP when a design/prototype/frame is linked or when the Jira is UI-flow heavy and the user says Figma should be used.
- Learn the existing flow before writing scenarios: entry point, primary path, alternate path, empty/error/loading states, dialogs, toasts, permissions, responsive states, and component variants.
- Compare design evidence with Jira UAC, RAG product behaviour, and PR implementation; call out contradictions as Draft blockers in the affected section.
- Do not treat Figma as proof of backend/API behaviour, permissions, versioning, or persistence unless Jira/PR/RAG also supports it.
- If Figma MCP or design access is missing for a design-dependent ticket, write `Draft blocker: Figma design evidence not inspected`.

### Phase 7 — Design Test Scenarios

- Write the minimum number of scenarios needed to cover every acceptance criterion and material risk. Use 6-10 for narrow changes and 12-20 for broad APIs, multi-provider workflows, large enum matrices, recovery incidents, or cross-version features; coverage takes priority over an arbitrary cap.
- Each scenario must include action + expected result in one plain-English bullet.
- Prefix every scenario with the acceptance IDs it covers, for example `P0 [AC-01, AC-04]`. No confirmed or proposed AC may remain without at least one scenario, and no expected result may introduce behavior absent from an AC or accepted evidence.
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
- Never expose numeric retrieval confidence such as `0.88` in the user-facing plan. Describe evidence as verified, partial, inferred, conflicting, or unavailable and identify the evidence type.
- Emit valid UTF-8 text. Before returning, scan for mojibake markers such as `â€`, `â‰`, `Ã`, `Â`, or the replacement character; repair them or use ASCII punctuation such as `-`, `->`, and `>=` when the client encoding is uncertain.
- Do not emit a title, lifecycle preamble, authorization warning, tool trace, or quality-audit prose outside the ten required sections. Put lifecycle and evidence availability under `Scope From Git`.
- Use exactly these sections, in this order:
  1. `Acceptance Criteria`
  2. `Expected Behaviour`
  3. `Scope From Git`
  4. `Code Touched`
  5. `Lines Changed`
  6. `Test Scenarios`
  7. `Known Jira Bugs / Past Similar Tickets`
  8. `Regression Areas`
  9. `Automation Coverage & Gaps`
  10. `Open Questions`

## Section Rules

- **Acceptance Criteria**: Write `AC-## [Confirmed]` for Jira-approved behavior and `AC-## [Proposed]` for criteria derived from requirements, incidents, or identified gaps. Each bullet must be an independently testable product contract, not a `Verify...` test step. If a sign-off-critical decision is unknown, keep it in `Open Questions` and add a Draft blocker only when it prevents UAC readiness.
- **Expected Behaviour**: State intended behaviour from Jira plus accepted `ask_dita_expert` and Figma design-flow evidence. Separate observation, supported inference, and confirmed root cause. Do not use exclusive wording such as `purely`, `only cause`, or `proves the root cause` unless the evidence rules out credible alternatives for the relevant time window. If unsupported, write `Unknown from current evidence`.
- **Scope From Git**: Start with lifecycle stage and readiness target. List issue/development-link source, relevant clone discovery and sync state, GitHub MCP/PR status only when stage-relevant, current or changed product area, diff-inspection state, and Figma evidence state when applicable. For every cited clone include absolute repository path, branch, full or short commit SHA, upstream/ahead/behind state, dirty/clean state, fetch result, and whether claims use the worktree or a verified remote ref.
- **Code Touched**: In pre-development, write `No code changes yet — development has not started`, then list exact current files/functions/classes/workflows under `Current implementation implicated` and evidence-backed likely change points under `Potential code impact`; label inference and never present it as changed code. Use complete absolute file paths and exact symbols; never abbreviate a path with `...`. In implementation/post-fix stages, list actual changed files/symbols from the inspected diff, plus adjacent callers, shared services, configs, persistence paths, UI states, and automation code that can be impacted, with a short QA implication for each.
- **Lines Changed**: In pre-development, write `Not applicable — development has not started`; never add a line-level Draft blocker. In implementation/post-fix stages, summarize added/deleted counts and key hunks by file; if unavailable, add `Draft blocker: implementation diff not inspected`.
- **Test Scenarios**: Map every practical P0/P1/P2 bullet to one or more AC IDs and include action + observable result. Put destructive one-time remediation under a clearly labelled `Incident recovery validation` bullet rather than an AC. Such validation must include target ownership/correlation, approved exact scope, backup/export, dry-run or pre-delete inventory, unrelated-state preservation, audit evidence, rollback, post-cleanup queue/dashboard checks, and safe production boundaries. For concurrency safeguards, separately assert successful completion after serialization/retry, valid output integrity, no duplicate/partial/orphan state, and bounded terminal failure after retry exhaustion; reaching any terminal failure is not sufficient when the business contract requires successful publishing. Use enough scenarios to cover every AC and required matrix; include Figma-observed UI states when design evidence exists.
- **Known Jira Bugs / Past Similar Tickets**: List up to five validated Jira keys covering relevant open known bugs and resolved historical bugs. Include status/resolution, similarity, RCA or behavior lesson when available, affected/fix version, reusable test evidence, and concrete impact on scenarios or regression. Include the narrow Jira/JQL and indexed-history search status. Mark every unavailable field explicitly instead of inferring or omitting it.
- **Regression Areas**: List nearby workflows, APIs, configs, roles, browsers, data shapes, design states, component variants, upgrade paths, integration impact, and automation coverage gaps likely to break.
- **Automation Coverage & Gaps**: For each relevant AC or grouped matrix, state `Covered`, `Partially covered`, `Not covered`, or `Not suitable for automation`. `Partially covered` requires an existing test to exercise and assert a named clause of that same AC; adjacent happy-path coverage is only reusable infrastructure. For existing coverage, include exact local/GitHub repository, complete file path, test/scenario method, helper or fixture, test layer, and inspected revision. For gaps, include the exact candidate file/class/method, layer, reusable infrastructure, deterministic setup/injection, polling oracle, timeout source, output-integrity assertions, cleanup/rollback, suite/tags, and whether to extend or add a test. Call out skipped, flaky, quarantined, stale, or inaccessible automation separately.
- **Open Questions**: List targeted unanswered questions by domain; include permission/role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5, and on-premise upgrade-impact questions only when relevant. If none, say `No open questions from current evidence`.

## Hard Rules

- Keep acceptance criteria in the plan.
- Always state the lifecycle stage and apply its evidence requirements consistently.
- Always inspect relevant available product clones for current implementation and automation clones for coverage before declaring code or automation evidence unavailable.
- Never write `no backend/Starling clone available`, `none found`, or `full coverage gap` after searching only the opened automation workspace. Such conclusions require the bounded clone discovery protocol, separate product and automation searches, exact searched terms, and resolved clone paths.
- Never treat missing PR, changed files, or line counts as a blocker in `Pre-Development UAC`.
- Never present current implementation found in a clone as changed code unless a real diff proves the change.
- Never abbreviate cited repository or file paths with `...`, and never describe a clone as current from wall-clock recency such as `last commit today`; report its exact revision and sync state.
- Never promote an approximate incident runtime, dataset size, or resource recommendation into a pass/fail requirement without an approved SLA or controlled benchmark contract.
- Never treat `terminal success/failure` as sufficient for a workflow whose acceptance contract requires successful output; test success, output integrity, and retry-exhaustion failure as distinct outcomes.
- Only exact labels `AC-## [Confirmed]` and `AC-## [Proposed]` are valid. Reject decorated labels such as `[Confirmed - historical]`, `[Confirmed - incident recovery]`, or any equivalent punctuation variant.
- Acceptance criteria describe observable product outcomes, not implementation choices. Keep node deletion, tracker reconciliation, mandatory workflow-step placement, single-source-of-truth architecture, lock type, retry mechanism, serialization strategy, and concrete cleanup commands in scenarios, code-impact analysis, or open questions unless Jira explicitly approves that implementation contract.
- Every non-incident P0/P1/P2 scenario must contain at least one `[AC-##]` mapping. `Incident recovery validation` bullets are the only traceability exemption.
- `Not suitable for automation` applies only to the destructive one-time production operation itself. Repeatable post-recovery product behavior on a production-equivalent environment is `Covered`, `Partially covered`, or `Not covered`.
- When one Jira connector requires authorization but another connected Jira MCP succeeds, omit the failed-connector warning from the final plan and report only the evidence source actually used.

## Quality-Gate Audit Requests

- When the user asks to audit a previous answer, first read `references/quality-gate-checklist.md` and run `scripts/validate_test_plan.py` against the previous plan when its text is available.
- List every validator failure plus evidence-quality failures that static validation cannot detect. Do not stop after the first few failures.
- Regenerate a complete plan only after the failure list. Validate the regenerated draft with the same script and return only the failure list followed by the corrected ten-section plan.
- Do not retain an obsolete Jira-authorization warning when live Jira evidence was subsequently fetched successfully.
- Do not add extra headings such as `What can break`, `Likely bugs`, `Fix safety`, `Important combinations`, or `Draft blockers` beyond the required output sections.
- Put likely bugs, fix-safety, automation, and blocker notes under `Test Scenarios`, `Regression Areas`, or the relevant evidence section.
- Never call a plan `proper RAG-backed` when evidence is generic, unrelated, unavailable, or only keyword-matched.
- Never mark a plan ready when evidence required for its declared lifecycle stage or a sign-off-critical decision is missing. Do not impose implementation-stage PR, diff, or line-count requirements on pre-development UAC work.
