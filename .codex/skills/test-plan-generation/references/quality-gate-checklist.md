# Quality Gate Checklist

Use this before calling a test plan review-ready.

## Evidence Gate

- Jira facts are collected with Jira MCP when available; fallback to pasted Jira details is clearly marked.
- Acceptance criteria are explicit, or missing AC is marked as a Draft blocker.
- Jira UAC/acceptance criteria are treated as the primary acceptance and sign-off contract for scope, out-of-scope, expected behaviour, integrations, regression boundaries, and open questions.
- Conflict priority is applied when evidence disagrees: Jira/UAC > PR implementation > accepted RAG docs > Figma UI intent > cloned repo/team memory.
- Edge cases are derived from UAC, PR diff, code branches, API contracts, configs, old automation failures, and similar Jira history.
- Integration impact identifies adjacent workflows, shared APIs/components, configs, roles, output types, and automation areas that can break.
- `ask_dita_expert` was used for behaviour facts unless the task is strictly code-only.
- RAG evidence was accepted only when direct and rejected when generic/noisy.
- Behaviour-sensitive plans used focused RAG probes for exact API/config/UI/construct terms, expected workflow, and boundary/version/regression behaviour.
- Accepted RAG came from exact feature/API/config/source overlap; broad release-note or validation-oracle chunks were rejected unless they directly matched the Jira.
- Latest matching current docs were preferred over older release notes unless the Jira is explicitly about older-release or upgrade behaviour.
- Past similar tickets were searched through Jira MCP/JQL, user-provided tickets, or available team memory.
- Past similar tickets were searched with multiple narrow passes and noisy automation-bulk/generic keyword hits were rejected.
- If Jira had no PR link, GitHub MCP PR discovery was attempted before asking the user for PR/branch/diff.
- Figma MCP was used when Jira/PR/user context supplied a Figma or prototype link, or when design evidence is required for a UI-heavy workflow.
- Existing design flow was inspected for entry points, states, dialogs, variants, and contradictions with Jira/RAG/PR evidence.
- PR/branch/commit/pasted diff was inspected when fix-impact claims are included.
- Changed files/functions and line counts come from real PR/Git evidence.
- Relevant user-cloned repos were inspected when available: Starling/backend, xmleditor, new editor, `guides-ui-tests`, and `dxml-it-tests`.
- `guides-ui-tests` and `dxml-it-tests` were inspected for existing coverage, old failures, reusable scenarios, and automation coverage gaps when available.
- Known local clone paths and environment-provided repo paths were checked before declaring automation/product repos unavailable.
- Local repo evidence states fetch/sync status and is not used as final proof when dirty, stale, diverged, or unsynced.
- Open questions are specific to unresolved permission, role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5 output, or on-premise upgrade-impact decisions.
- Test data, setup preconditions, role/config/platform matrix, and API contract questions are either answered by evidence or captured under `Open Questions`.

## Draft When

- Jira facts are missing or too vague.
- UAC scope or out-of-scope is ignored, softened, or contradicted without a visible blocker.
- RAG is down, noisy, unrelated, or unavailable for a behaviour claim.
- RAG was queried only with broad prose and not tightened with exact API/config/UI/construct terms when the first results were noisy.
- RAG relies on older release-note chunks while newer/current exact docs are available for the same behaviour.
- Historical Jira search was not possible and similar tickets matter for coverage.
- Historical Jira search returns only broad/noisy matches, automation bulk tickets, or generic keywords and the plan still treats them as similar.
- Jira had no PR, GitHub MCP could not find one, and the user did not provide PR/branch/diff while the plan claims code impact.
- PR/diff was not inspected but the plan claims code impact.
- Design evidence was required for UI expected behaviour, but Figma MCP/design screenshots were unavailable or not inspected.
- Figma design contradicts Jira, RAG, or PR implementation and the contradiction is unresolved.
- Line counts or key hunks are unavailable.
- Repo evidence is dirty, stale, behind, diverged, or not fetched.
- Relevant cloned repo paths are unavailable and code/automation impact is required.
- Known local clone paths such as `C:\UI TEST\guides-ui-tests` or environment-provided repo paths were available but not checked.
- Integration impact is missing, generic, or just repeats the direct feature area.
- Edge cases are guessed from generic module names instead of derived from UAC, PR diff, code branches, API contracts, configs, old automation failures, or similar Jira history.
- Automation repos are available but existing coverage, old failures, reusable scenarios, or automation coverage gaps were not inspected.
- Test data/setup/environment matrix is required for sign-off but absent from `Test Scenarios`, `Regression Areas`, and `Open Questions`.
- Backend/API contract is relevant but endpoint, parameters, response/error contract, batch behaviour, or logs are not clarified.
- Expected behaviour depends on an unverified product assumption.
- On-premise release/upgrade scope exists but source/target versions, retained configs, changed defaults, manual post-upgrade steps, or compatibility expectations are not clarified.
- Sign-off-critical permission, role, XML Editor config, AEM config, translation config, DITA, DITA-OT/PDF/HTML5, or on-premise upgrade-impact questions are unresolved.

## Review-Ready When

- Each expected-behaviour bullet is backed by Jira, accepted RAG, PR diff, or explicitly marked unknown.
- Each P0/P1 scenario maps to AC, expected behaviour, PR diff, past Jira learning, or a high-risk regression.
- Scope, code touched, and lines changed cite real PR/Git evidence.
- Scope states whether PR came from Jira, GitHub MCP discovery, user input, or local clone evidence.
- Design-dependent UI flows state whether Figma MCP, screenshots, or pasted design notes were inspected.
- Native AEM Site baseline metadata plans state baseline type, output preset `metadatalist`, custom metadata expectation, copy-to/incremental scope, and explicit out-of-scope items when applicable.
- Review identity/role display plans cover reviewer task page, editor review right panel, tagging, replies, nested reply ladder, project-specific role mapping, search non-impact, and notifications/email no-regression expectations when applicable.
- On-premise release/upgrade plans state source/target version coverage, retained custom config expectations, changed defaults, manual steps, and backward-compatibility risks when applicable.
- Relevant product and automation clones are either inspected or explicitly marked unavailable.
- Existing automation coverage and automation coverage gaps are mapped into `Test Scenarios` or `Regression Areas`.
- Evidence conflicts are resolved by the priority rule or shown as Draft blockers.
- Past similar tickets either list useful matches or clearly state no matches/evidence unavailable.
- Regression areas are specific to touched code and learned product behaviour, not generic module names.
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
