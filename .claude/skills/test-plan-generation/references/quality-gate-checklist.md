# Quality Gate Checklist

Use this before calling a test plan review-ready.

## Stage Gate

- Declare exactly one lifecycle stage: `Pre-Development UAC`, `Implementation Review`, or `Post-Fix Validation`.
- In `Pre-Development UAC`, require a proposed acceptance contract, supported expected behaviour, relevant current product-clone inspection when available, automation-clone inspection when available, regression mapping, and sign-off decisions. Do not require a PR, changed files, or line counts.
- In `Implementation Review`, require the implementation diff, changed files, line counts, current-code comparison, and code-derived coverage.
- In `Post-Fix Validation`, require the candidate fix/build source, inspected diff, acceptance coverage, regression evidence, environment matrix, and resolved sign-off questions.
- Treat evidence gaps as local to the claims they affect. Do not downgrade an entire plan because an optional source is unavailable.

## Evidence Gate

- The manifest contains a timezone-aware `evidence_preflight` for exactly `product_rag`, `jira_history`, `live_jira`, `git`, and `figma`; each status comes from an actual check, not assumed configuration.
- Preflight mode is derived correctly: any unavailable source means `degraded`, degraded mode has concrete claim restrictions, and readiness impact is lifecycle-aware rather than globally blocking unrelated claims.
- `Evidence boundary` starts with the manifest's `Evidence mode: full` or `Evidence mode: degraded`; degraded plans name every unavailable source and what remains unverified.
- Source-specific restrictions are enforced: no unsupported RAG behavior, historical-no-match, live mutable Jira, current/diff Git, or exact Figma design claims survive when their source is unavailable.
- `Understanding From Jira` appears first and contains the five required confidence-check bullets: issue, impact, requested outcome, lifecycle, and evidence boundary.
- The Jira understanding is a faithful plain-English synthesis of live Jira or supplied issue evidence; it does not invent code changes, root cause, acceptance, or implementation.
- Jira facts are collected with Jira MCP when available; pasted Jira, Dynamics/support incident, customer escalation, logs, screenshots, and investigation notes are valid fallback evidence and their source is identified.
- Acceptance criteria are explicit, or missing AC is marked as a Draft blocker.
- Destructive operational procedures are excluded from product ACs and appear only as incident-recovery validation with observable restoration outcomes.
- Jira UAC/acceptance criteria are treated as the primary acceptance and sign-off contract for scope, out-of-scope, expected behaviour, integrations, regression boundaries, and open questions.
- When final accepted UAC exists, `accepted_uac_present=true` and a valid `aem-guides-uac-fidelity-v1` manifest audit maps every accepted clause to `[Confirmed]` ACs and every `[Confirmed]` AC back to accepted clauses.
- Normalization preserves exact config names and values, defaults, ordering, formatting, parity targets, and non-goals; linked tests, RAG, history, or generated coverage remain `[Proposed]` unless the accepted UAC approves them.
- Parity requirements use the named comparison surface as the oracle across entry presence, visible text, order, formatting, clickability, and destination; the plan does not invent a more specific result without inspecting that reference output.
- Independent controls such as a feature flag and preset argument remain separate and have positive plus one-control-missing configurations; one control is never substituted for the other.
- Out-of-scope behaviour is not converted into a sign-off AC or a blocking regression, and an intentional output difference is not reported as a defect.
- Conflict priority is applied when evidence disagrees: Jira/UAC > PR implementation > accepted RAG docs > Figma UI intent > cloned repo/team memory.
- Edge cases are derived from UAC, PR diff, code branches, API contracts, configs, old automation failures, and similar Jira history.
- Integration impact identifies adjacent workflows, shared APIs/components, configs, roles, output types, and automation areas that can break.
- `ask_dita_expert` was used for behaviour facts when available and relevant. If unavailable, exact acceptance-contract, log, current-code, design, or implementation evidence supports each retained claim; unsupported claims remain unknown or blocked.
- RAG evidence was accepted only when direct and rejected when generic/noisy.
- Behaviour-sensitive plans used focused RAG probes for exact API/config/UI/construct terms, expected workflow, and boundary/version/regression behaviour.
- Accepted RAG came from exact feature/API/config/source overlap; broad release-note or validation-oracle chunks were rejected unless they directly matched the Jira.
- Latest matching current docs were preferred over older release notes unless the Jira is explicitly about older-release or upgrade behaviour.
- Every Jira attachment was downloaded and actually analysed (screenshots opened, logs/sample content read), and embedded description/comment snippets (logs, code blocks, tables, pasted images) were mined; any claim about an attachment traces to opening it, not to its filename.
- At least three focused product-documentation probes were run through `ask_dita_expert` before writing, recorded under `rag_tool` and `rag_probes`, and every grounded finding is folded into `Expected Behaviour` with a RAG label.
- The indexed `jira_qa` history was queried separately through `search_jira_history` for both same-customer and cross-customer scope, recorded under `jira_history_tool`, `jira_history_queries`, and `indexed_history_run`; hits were validated live before citing and only same-mechanism results were retained.
- Test Scenarios include concrete `Setup and test data` bullets with real fixtures, identifier formats/example values, property/field/column names, config keys and values, environment matrix, and pass/fail oracles — not just abstract "create a map/topic" steps.
- Regression Areas are written as senior-QA regression items — each names the specific thing to re-test and the risk (what could break and why), ordered by blast radius with the top risk called out — not bare area names or keyword fragments.
- Open Questions are written as UAC decisions with the QA impact of each plausible answer (what each answer changes for scenarios, expected results, environment matrix, or sign-off) — not bare questions with no stated consequence.
- Acceptance Criteria are Principal-QA product contracts — each states precondition/input, trigger, and observable outcome with the scope boundary (included vs excluded) and the verification oracle, names exact properties/fields/enums and expected values, and passes/fails independently — not terse labels or generic "Verify..." steps.
- Every Covered / Partially covered automation item has its real code quoted verbatim (from the actual file, with absolute path, what it proves, and the gap) in an `Appendix A - Automation Evidence` section kept outside the eleven validated bullet-only sections; the combined file was delivered to the user and passed verify_evidence.py. verify_evidence.py hard-fails a Covered/Partially-covered verdict when the file has no fenced code evidence, so this cannot be silently skipped on a re-run - always regenerate Appendix A and run verify on the combined plan+appendix, never on the body alone.
- Past similar tickets were searched through Jira MCP/JQL, user-provided tickets, or available team memory.
- Past similar tickets were searched with multiple narrow passes and noisy automation-bulk/generic keyword hits were rejected.
- Each listed past ticket names a concrete shared defect mechanism (same failure shape/root-cause family), not merely a shared feature area, subsystem name, or keyword; cross-feature candidates surfaced by broad JQL (version-purge, map-collection, translation, etc.) were excluded unless the same code path/property/failure was shown, and the section was not padded to five.
- No Jira key is name-dropped in `Regression Areas` (or elsewhere) unless it is vetted and listed in `Known Jira Bugs`; regression risks are referenced by workflow/code path/automation, not by unrelated ticket numbers.
- The full similar-ticket list was re-audited (not just newly-flagged ones): no ticket survives on an abstract shape or shared domain across a different feature/entity/code path, none is kept by relabelling it "adjacent", and if no same-defect-class history exists the section says so and lists only excluded candidates.
- If development may have started and Jira had no PR link, GitHub MCP PR discovery was attempted before asking for PR/branch/diff. PR discovery is not required in pre-development.
- Figma MCP was used when Jira/PR/user context supplied a Figma or prototype link, or when design evidence is required for a UI-heavy workflow.
- Existing design flow was inspected for entry points, states, dialogs, variants, and contradictions with Jira/RAG/PR evidence.
- PR/branch/commit/pasted diff was inspected in implementation-review or post-fix stages and whenever changed-code or fix-impact claims are included.
- Changed files/functions and line counts come from real PR/Git evidence; pre-development uses `No code changes yet` and `Not applicable — development has not started`.
- Every relevant available user-cloned repo was inspected: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- Pre-development `Code Touched` distinguishes current implementation implicated from changed code and cites exact product-clone/log/API/workflow evidence.
- `guides-ui-tests` and `dxml-it-tests` were inspected for existing coverage, old failures, reusable scenarios, and automation coverage gaps when available.
- Every discovered automation clone, including editor E2E and repository-specific suites, completed the guarded fetch/stash/fast-forward flow or has an explicit blocked-sync boundary and verified remote-ref fallback.
- Known local clone paths and environment-provided repo paths were checked before declaring automation/product repos unavailable.
- Local repo evidence uses the guarded sync flow and states fetch/pull status; blocked, diverged, or unsynced worktree evidence is not used as final proof when a verified remote ref is unavailable.
- Every cited clone/file uses a complete absolute path plus branch, pre/post sync SHA, inspected ref, upstream/ahead/behind state, pre/post dirty state, fetch/pull result, and retained stash OID/ref when developer work was preserved; no path contains `...`.
- Dirty developer work was stashed only after safety checks, includes tracked and untracked files but not ignored files, remains recoverable with an exact restore command, and was never silently popped or dropped.
- Open questions are specific to unresolved permission, role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5 output, or on-premise upgrade-impact decisions.
- Test data, setup preconditions, role/config/platform matrix, and API contract questions are either answered by evidence or captured under `Open Questions`.
- Historical Jira entries include the narrow JQL/search intent, current status/resolution, affected/fix versions, RCA, linked test evidence, and scenario impact; unavailable fields are explicitly marked unavailable.
- Automation classification is contract-exact: adjacent happy-path coverage is not called partial coverage unless it asserts a named clause of the same AC.
- Automation gaps name the exact candidate test location, deterministic setup/injection, polling oracle, timeout source, output-integrity assertions, cleanup/rollback, and suite/tags.
- Approximate incident runtimes, dataset sizes, and resource recommendations remain baselines or open questions unless an approved SLA or controlled benchmark defines the oracle.
- Concurrency recovery checks successful completion and output integrity separately from retry-exhaustion terminal failure.

## Draft When

- Issue facts from Jira, Dynamics/support, customer escalation, logs, screenshots, or investigation notes are missing or too vague for the declared stage.
- UAC scope or out-of-scope is ignored, softened, or contradicted without a visible blocker.
- Final accepted UAC exists but its fidelity audit is missing, an accepted clause is unmapped, a `[Confirmed]` AC has no accepted source clause, or the audit reports an unresolved contradiction or scope expansion.
- A parity clause is rewritten as a more specific expected result without an inspected reference output or explicit accepted Jira wording.
- Independent enablement controls are conflated, or an out-of-scope HTML5/DITA-OT behavior is treated as a Native PDF sign-off failure.
- RAG is down, noisy, unrelated, or unavailable and the affected behaviour claim lacks another authoritative evidence source.
- RAG was queried only with broad prose and not tightened with exact API/config/UI/construct terms when the first results were noisy.
- RAG relies on older release-note chunks while newer/current exact docs are available for the same behaviour.
- Historical Jira search was not possible and the missing history leaves a material regression or expected-behaviour decision unsupported.
- Historical Jira search returns only broad/noisy matches, automation bulk tickets, or generic keywords and the plan still treats them as similar.
- An implementation-review or post-fix plan lacks the required branch/commit/PR/pasted diff while claiming changed-code or fix impact.
- A pre-development plan labels current code as changed code or treats missing PR/diff as a blocker.
- Design evidence was required for UI expected behaviour, but Figma MCP/design screenshots were unavailable or not inspected.
- Figma design contradicts Jira, RAG, or PR implementation and the contradiction is unresolved.
- Line counts or key hunks are unavailable in implementation-review or post-fix stages.
- Repo evidence needed for a claim is dirty, stale, behind, diverged, or not fetched and no verified remote-ref evidence supports that claim.
- A dirty evidence clone was pulled without a recorded safety stash, or a stash was created without reporting its exact OID/ref and restore command.
- Relevant cloned repo paths are unavailable and code/automation impact is required.
- Known local clone paths such as `C:\UI TEST\guides-ui-tests` or environment-provided repo paths were available but not checked.
- Integration impact is missing, generic, or just repeats the direct feature area.
- Edge cases are guessed from generic module names instead of derived from UAC, PR diff, code branches, API contracts, configs, old automation failures, or similar Jira history.
- Automation repos are available but existing coverage, old failures, reusable scenarios, or automation coverage gaps were not inspected.
- Test data/setup/environment matrix is required for sign-off but absent from `Test Scenarios`, `Regression Areas`, and `Open Questions`.
- Backend/API contract is relevant but endpoint, parameters, response/error contract, batch behaviour, or logs are not clarified.
- Expected behaviour depends on an unverified product assumption.
- Expected behaviour uses exclusive root-cause language such as `purely`, `only cause`, or `proves the root cause` without evidence that excludes credible alternatives.
- A destructive cleanup scenario omits ownership/correlation, approval, pre-change inventory/backup, unrelated-state protection, audit evidence, rollback, or post-cleanup verification.
- A plan marks adjacent happy-path automation as partial coverage of recovery, concurrency, orphan-state, queue-drain, or dashboard-consistency behavior.
- A performance scenario turns approximate customer timing, topic count, or heap guidance into a hard oracle without an approved SLA or controlled benchmark.
- On-premise release/upgrade scope exists but source/target versions, retained configs, changed defaults, manual post-upgrade steps, or compatibility expectations are not clarified.
- Sign-off-critical permission, role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5, or on-premise upgrade-impact questions are unresolved.

## Review-Ready When

- Each expected-behaviour bullet is backed by Jira, accepted RAG, PR diff, or explicitly marked unknown.
- Each P0/P1 scenario maps to AC, expected behaviour, PR diff, past Jira learning, or a high-risk regression.
- Scope states the lifecycle stage, issue source, clone sync state, and stage-relevant PR/diff status.
- Pre-development `Code Touched` says no code changes exist and cites exact current implementation/automation findings where available; `Lines Changed` is not applicable.
- Implementation/post-fix `Code Touched` and `Lines Changed` cite real PR/Git evidence.
- Design-dependent UI flows state whether Figma MCP, screenshots, or pasted design notes were inspected.
- Native AEM Site baseline metadata plans state baseline type, output preset `metadatalist`, custom metadata expectation, copy-to/incremental scope, and explicit out-of-scope items when applicable.
- Review identity/role display plans cover reviewer task page, editor review right panel, tagging, replies, nested reply ladder, project-specific role mapping, search non-impact, and notifications/email no-regression expectations when applicable.
- Review task-history/right-panel plans cover author persona, current/open/closed task dropdown, `Current` tag, selected-task metadata, read-only previous comments, import disabled state for non-current tasks, selected-task search/filter scoping, side-by-side diff, topic-switch reset, feature flag on/off, user-name fallback, and both-editor compatibility questions when applicable.
- On-premise release/upgrade plans state source/target version coverage, retained custom config expectations, changed defaults, manual steps, and backward-compatibility risks when applicable.
- Relevant product and automation clones are either inspected or explicitly marked unavailable.
- Existing automation coverage and automation coverage gaps are mapped into `Test Scenarios` or `Regression Areas`.
- Evidence conflicts are resolved by the priority rule or shown as Draft blockers.
- Past similar tickets either list useful matches or clearly state no matches/evidence unavailable.
- Regression areas are specific to touched code and learned product behaviour, not generic module names.
- Final output contains no mojibake markers and uses valid UTF-8 or safe ASCII punctuation.
- `Open Questions` exists and either lists targeted unresolved questions or says `No open questions from current evidence`.

## Anti-Patterns To Block

- Tables.
- Extra headings outside the required nine sections.
- Raw RAG chunks, scores, JSON, backend traces, or evidence matrices in the final plan.
- "Proper RAG-backed" claims when evidence is only keyword-matched.
- Test scenarios that say only "verify functionality" without action + expected result.
- Edge-case lists that are plausible but not tied to Jira/UAC, PR/diff, API/config evidence, automation history, or similar Jira evidence.
- Regression areas that omit integration impact for shared APIs, components, configs, publishing/editor/review/upload/translation flows, or automation repos.
- On-premise release test plans that omit upgrade impact, retained custom configs, changed defaults, or source/target version coverage.
- Confident product behaviour based only on memory, code names, or broad docs.
- Any non-empty line outside the eleven required sections, including a title, lifecycle preamble, connector warning, or tool trace.
- Acceptance labels other than exact `[Confirmed]` and `[Proposed]`.
- Historical cleanup observations presented as confirmed Jira AC when the native Jira/UAC acceptance field is empty.
- Product AC that prescribes node deletion, tracker reconciliation, mandatory workflow-step placement, a single-source-of-truth architecture, or a specific lock/retry/serialization implementation that Jira did not approve.
- `Not suitable for automation` applied to repeatable post-recovery behavior rather than only the destructive production operation.
- A Jira authorization warning retained even though another Jira MCP successfully supplied live issue evidence.

## Executable Gate

- Save the final draft as UTF-8 and run `python scripts/validate_test_plan.py <draft-file>` from the skill directory.
- A non-zero exit means the plan is not review-ready. Repair every reported error and rerun; never replace executable failures with a narrative claim that the gate passed.
