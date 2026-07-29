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

## What To Search Locally

- Jira key.
- Exact error text.
- UI labels, command names, route names, API paths, config keys, workflow names.
- Changed package/module names from PR or Jira.
- Similar test names in `guides-ui-tests` and `dxml-it-tests`.
- Existing fixtures/data builders that exercise the same workflow.

Reject broad standalone words such as `topic`, `map`, `assets`, `metadata`, `cloud`, `workflow`, `report`, or `translation` unless combined with exact failure/context terms.

## Output Mapping

- Put PR discovery status and repo sync state under `Scope From Git`.
- Put concrete files/functions/classes/components under `Code Touched`.
- Put added/deleted counts and key hunks under `Lines Changed`.
- Put automation coverage or missing automation in `Regression Areas` or `Test Scenarios`.
- If no PR and no reliable clone evidence are available, write `Draft blocker: PR/diff not found via Jira or GitHub MCP; user PR/branch/diff required`.
