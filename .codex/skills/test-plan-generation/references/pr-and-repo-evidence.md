# PR And Repo Evidence

Use this file before searching GitHub MCP, inspecting PRs, or using user-cloned repositories.

## Preferred Evidence Order

- Jira development panel or linked PR from Jira MCP.
- GitHub MCP PR search by Jira key, summary, branch name, commit message, and PR body.
- User-provided PR URL, branch, commit, or pasted diff.
- User-cloned local repos that can be fetched and verified.
- Team memory or automation hints only as secondary coverage learning.

## GitHub MCP PR Discovery

When Jira does not mention a PR:

- Search GitHub MCP for the Jira key in PR title/body, branch names, commits, and comments.
- Search summary/product terms only after exact Jira key search.
- Search likely repos in this order when accessible:
  - Starling/backend repo for backend/API/service changes.
  - `xmleditor` for XML editor UI/controller/model/service changes.
  - New editor repo for redesigned editor surfaces.
  - `guides-ui-tests` for UI automation coverage and regression hints.
  - `dxml-it-tests` for integration/API/backend regression coverage.
- If GitHub MCP cannot search or returns no confident PR, ask the user for the PR URL, branch, commit, or pasted diff.
- Never claim a PR was inspected unless the PR diff, changed files, and line counts were actually read.

## User-Cloned Repo Evidence

Use local clones only when the user already has them or provides paths. Do not require cloning just to use the skill.

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

- Put PR discovery status and repo sync state under `Scope From Git`.
- Put concrete files/functions/classes/components under `Code Touched`.
- Put added/deleted counts and key hunks under `Lines Changed`.
- Put existing automation coverage, reusable automation scenarios, and automation coverage gaps in `Regression Areas` or `Test Scenarios`.
- If no PR and no reliable clone evidence are available, write `Draft blocker: PR/diff not found via Jira or GitHub MCP; user PR/branch/diff required`.
