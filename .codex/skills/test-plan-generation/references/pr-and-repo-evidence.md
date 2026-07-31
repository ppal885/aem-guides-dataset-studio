# PR And Repo Evidence

Use this file before searching GitHub MCP, inspecting PRs, or using user-cloned repositories.

## Preferred Evidence Order

- Lifecycle stage and issue/UAC facts.
- User-cloned product repos that can be fetched and verified for current implementation.
- User-cloned automation repos that can be fetched and verified for existing coverage and gaps.
- Jira development panel or linked PR from Jira MCP when development may have started.
- GitHub MCP PR search by Jira key, summary, branch name, commit message, and PR body when implementation evidence is stage-relevant.
- User-provided PR URL, branch, commit, or pasted diff when one exists.
- Team memory or automation hints only as secondary coverage learning.

## Lifecycle Rules

- **Pre-Development UAC**: Do not search for or request a PR when the user states development has not started. Inspect product clones for current implementation and automation clones for coverage. Report changed code and line counts as not applicable.
- **Implementation Review**: Require and inspect the available branch, commit, PR, or pasted diff. Compare it with current product code and existing automation.
- **Post-Fix Validation**: Inspect the exact candidate fix/build source and its diff before making fix-impact or QA sign-off claims.

## GitHub MCP PR Discovery

When development may have started and Jira does not mention a PR:

- Search GitHub MCP for the Jira key in PR title/body, branch names, commits, and comments.
- Search summary/product terms only after exact Jira key search.
- Search likely repos in this order when accessible:
  - Starling/backend repo for backend/API/service changes.
  - `xmleditor` for XML editor UI/controller/model/service changes.
  - New editor repo for redesigned editor surfaces.
  - `guides-ui-tests` for UI automation coverage and regression hints.
  - `dxml-it-tests` for integration/API/backend regression coverage.
- If GitHub MCP cannot search or returns no confident PR, ask for the PR URL, branch, commit, or pasted diff only in implementation-review or post-fix stages.
- Never claim a PR was inspected unless the PR diff, changed files, and line counts were actually read.
- Never run PR discovery merely to satisfy an output template when the lifecycle stage is pre-development.

## User-Cloned Repo Evidence

Use local clones when the user already has them, provides paths, or exposes them as workspace roots. Do not require cloning just to use the skill, but always inspect every relevant available clone before declaring code or automation evidence unavailable.

Check these local path sources before saying a repo is unavailable:

- User-provided repo paths in the prompt.
- Workspace roots visible in the current environment.
- Environment variables such as `STARLING_REPO`, `XMLEDITOR_REPO`, `NEW_EDITOR_REPO`, `GUIDES_UI_TESTS_REPO`, and `DXML_IT_TESTS_REPO`.
- Common Windows teammate paths such as `C:\UI TEST\guides-ui-tests`, `C:\UI TEST\dxml-it-tests`, `C:\Users\<user>\guides-ui-tests`, and `C:\Users\<user>\dxml-it-tests`.
- Common Mac/Linux teammate paths such as `~/guides-ui-tests`, `~/dxml-it-tests`, `~/workspace/<repo>`, and `~/code/<repo>`.

Relevant clone categories:

- **Starling/backend**: backend code, APIs, services, persistence, migrations, workflow jobs, upload/reporting endpoints.
- **xmleditor**: classic XML editor UI, controllers, models, JSON views, dialogs, services, event handling.
- **new editor**: newer editor surfaces, redesigned panels/dialogs, new editor-specific services or state.
- **guides-ui-tests**: UI automation, Playwright/Selenium/Behave-style coverage, regression selectors, failure history.
- **dxml-it-tests**: integration/API/backend automation, service contracts, data migration, workflow and publish checks.

For each relevant clone:

- Run `git fetch --all --prune`.
- Run `git status -sb`.
- If the worktree is clean and behind upstream, run `git pull --ff-only`.
- If dirty, diverged, no upstream, detached, or fetch/pull fails, do not stash/reset/merge/rebase; mark evidence as provisional.
- Capture exact paths, functions/classes/components, tests, and line counts only from real diffs or search results.
- In pre-development, exact current files/functions/classes/workflows found by repo search are `Current implementation implicated`; they are not changed files.
- When a product clone is dirty, prefer verified remote refs for read-only current-code searches where practical and label the result provisional.

## Product Code Mining

- Search Starling/backend, xmleditor, and new editor clones using exact stack-trace classes, method names, workflow names, endpoint paths, config keys, error strings, JCR paths, UI labels, and component names.
- Read the matched implementation branches, guards, persistence paths, cleanup behavior, retries, timeouts, status transitions, and logging to derive testable risks.
- Report exact current paths and symbols under `Code Touched` as implicated in pre-development, or as changed only when a diff proves the change.
- If the relevant product clone is available but not inspected, the code-impact portion remains incomplete even when automation clones were inspected.
- If no relevant product clone is available, say `Current product implementation not inspected` and ask for a clone/path only when code-grounded UAC coverage is necessary.

## Automation Coverage Mining

For `guides-ui-tests` and `dxml-it-tests`, inspect automation evidence when the repos are available:

- Search by Jira key, summary terms, changed APIs, UI labels, selectors, config keys, workflow names, and similar failure text.
- Extract existing scenario names, test file paths, selectors/API fixtures, data builders, setup helpers, and assertions that already cover the workflow.
- Check skipped/flaky tags, quarantine markers, old failure names, recent failure screenshots/log names, and retry-specific code before claiming a scenario is safe.
- Search Jenkins/Allure-style names when present in Jira or failures, including build type, platform, vertical, suite name, feature file name, and scenario owner.
- For API/backend tickets, search `dxml-it-tests` by endpoint path, request parameter names, status/error contract, fixture path, and expected response fields.
- For UI tickets, search `guides-ui-tests` by visible label, data-testid/selector, page object method, feature file scenario title, step text, and failure screenshot folder/name.
- Identify automation coverage gaps: missing happy path, missing negative path, missing permissions/config coverage, missing cloud/on-prem parity, missing upgrade/backward-compat coverage, or missing API/UI pairing.
- Derive edge cases from existing assertions, fixtures, API contracts, branching conditions, historical failures, and similar Jira automation rather than from generic module names.
- Map useful existing coverage and automation coverage gaps into `Test Scenarios` or `Regression Areas`; do not dump raw automation files in the final plan.
- If automation repos are unavailable or stale/dirty, state that automation coverage gaps were not fully inspected and keep affected claims Draft.

## What To Search Locally

- Jira key.
- Exact error text.
- UI labels, command names, route names, API paths, config keys, workflow names.
- Release version, service pack, feature flag, cloud/on-prem build type, old/new UI marker, and output type when relevant.
- Changed package/module names from PR or Jira.
- Similar test names in `guides-ui-tests` and `dxml-it-tests`.
- Existing fixtures/data builders that exercise the same workflow.
- Skipped/flaky automation, failure screenshots, API fixtures, selectors, and reusable setup utilities in `guides-ui-tests` and `dxml-it-tests`.

Reject broad standalone words such as `topic`, `map`, `assets`, `metadata`, `cloud`, `workflow`, `report`, or `translation` unless combined with exact failure/context terms.

## Output Mapping

- Put lifecycle stage, clone discovery/sync state, and stage-relevant PR status under `Scope From Git`.
- In pre-development, put `No code changes yet` plus verified current implementation and automation evidence under `Code Touched`.
- In implementation/post-fix stages, put concrete changed files/functions/classes/components under `Code Touched`.
- In pre-development, put `Not applicable — development has not started` under `Lines Changed`.
- In implementation/post-fix stages, put added/deleted counts and key hunks under `Lines Changed`.
- Put existing automation coverage, reusable automation scenarios, and automation coverage gaps in `Regression Areas` or `Test Scenarios`.
- If no PR exists in pre-development, do not add a blocker. If product or automation clone evidence needed for a material claim is unavailable, identify that specific evidence gap.
- If an implementation/post-fix plan lacks a required diff, write `Draft blocker: implementation diff not inspected`.
