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

## Referenced PR Deep Analysis

When Jira or the user supplies a PR, branch, commit, or development link and GitHub MCP is connected:

- Fetch the PR itself; do not rely only on Jira development-panel metadata.
- Inspect repository, PR state, base/head branches, commits, changed files, complete diff hunks, line counts, reviews and unresolved comments when available, and checks/test results.
- Read changed functions and their adjacent branches, callers, API contracts, persistence, cleanup, retries, concurrency, permissions, configuration, logging, errors, feature flags, compatibility paths, and tests.
- Compare the diff with the relevant current product clone and existing `guides-ui-tests`/`dxml-it-tests` coverage.
- Map concrete hunks to AC IDs and P0/P1/P2 scenarios; map shared or adjacent impact to `Regression Areas`.
- Separate actual changed code from potential impact. Never list an untouched adjacent file as changed.
- If GitHub MCP cannot access the PR, use an exact local branch/commit or user-provided diff when available and state the evidence boundary.

## PR Supersession (More Than One PR/Branch On A Ticket)

A ticket can accumulate more than one PR over its lifetime: a narrower first attempt
later superseded by a broader fix, two parallel PRs for different platforms, or an
abandoned branch still linked in Jira dev-panel metadata. Grounding a plan on the first
PR noticed — without checking whether a later one supersedes it — produces Acceptance
Criteria for a fix that will never actually ship.

When Jira's dev-panel/comment history references more than one PR or branch:

- Fetch and diff **both** (or all) of them against the base branch, and against each
  other. `scripts/pr_supersession_check.py <repo_path> <base_ref> <pr_a> <pr_b>` automates
  the fetch + `diff --stat` steps and reports files unique to each PR plus a direct
  `pr_a...pr_b` diff, so the comparison is evidence-backed rather than a guess.
- Record the outcome in the manifest as `pr_references`, one entry per PR/branch:

```json
"pr_references": [
  {"pr_ref": "#8098", "status": "SUPERSEDED"},
  {"pr_ref": "#8135", "status": "AUTHORITATIVE",
   "comparison_note": "8135 supersedes 8098 with a full V1+V2 fix; diff --stat shows 8098's files as a strict subset of 8135's"}
]
```

- `status` ∈ `AUTHORITATIVE | SUPERSEDED | PARALLEL_UNRELATED | UNRESOLVED`.
- Exactly one entry must be `AUTHORITATIVE` (with a `comparison_note`) whenever more than
  one PR is listed, unless the supersession genuinely cannot be determined — in which case
  mark every entry `UNRESOLVED` with an `open_question_ref` and carry it forward as an
  Open Question rather than silently grounding on one of them.
- A single linked PR needs no `pr_references` block at all — this only activates once a
  ticket actually has more than one PR/branch in play.

## Batch Evidence Preparation (Many Tickets, One PR-Review Board)

When processing several tickets from one PR-review batch, the per-ticket fetch step (PR
ref fetch + `diff --stat` against the base branch) is otherwise repeated by hand for each
one. `scripts/batch_evidence_prep.py --batch tickets.json` runs this step for a whole
batch in one pass and prints a consolidated per-ticket report:

```json
[
  {"key": "GUIDES-44288", "repo": "C:\\starling", "pr": 8089},
  {"key": "GUIDES-49507", "repo": "C:\\xmleditor\\xmleditor", "pr": 8069, "base": "origin/develop"}
]
```

This is read-only evidence gathering only — it does not interpret the diff, write plan
content, or touch Jira; it just removes the repetitive fetch/diff toil across a batch.

## User-Cloned Repo Evidence

Use local clones when the user already has them, provides paths, or exposes them as workspace roots. Do not require cloning just to use the skill, but always inspect every relevant available clone before declaring code or automation evidence unavailable.

Before mining a clone, follow `git-repo-sync.md` and run `scripts/sync_evidence_repo.py <absolute-path> --stash-dirty`. This replaces ad hoc fetch/pull handling and creates an auditable, non-destructive sync record.

Check these local path sources before saying a repo is unavailable:

- User-provided repo paths in the prompt.
- Workspace roots visible in the current environment.
- Environment variables such as `STARLING_REPO`, `XMLEDITOR_REPO`, `NEW_EDITOR_REPO`, `GUIDES_UI_TESTS_REPO`, and `DXML_IT_TESTS_REPO`.
- Common Windows product paths such as `C:\starling`, `C:\xmleditor\xmleditor`, `C:\ui_framework\new_editor`, `C:\new_editor`, and immediate child repositories under those roots.
- Common Windows automation paths such as `C:\UI TEST\guides-ui-tests`, `C:\ui_framework\guides-ui-tests`, `C:\api automation\dxml-it-tests`, `C:\api automation\guides-ui-tests`, `C:\editor-e2e\guides-editor-e2e`, `C:\Users\<user>\guides-ui-tests`, and `C:\Users\<user>\dxml-it-tests`.
- Common Windows repository containers such as `C:\github_main-repo`, `C:\ui_framework`, `C:\api automation`, `C:\UI TEST`, `C:\editor-e2e`, and `C:\Users\<user>`; inspect their immediate children and one nested level for `.git` before declaring a clone missing.
- Common Mac/Linux teammate paths such as `~/guides-ui-tests`, `~/dxml-it-tests`, `~/workspace/<repo>`, and `~/code/<repo>`.

### Bounded Clone Discovery Protocol

- Do not limit clone discovery to the currently opened project or workspace root.
- On Windows, first test the explicit paths above, then inspect immediate children up to two levels under the listed repository containers. Do not recursively scan the entire system drive.
- Treat a directory as a clone only when it contains `.git`; account for wrapper directories such as `C:\xmleditor\xmleditor` and `C:\ui_framework\new_editor\<repo>`.
- Record every relevant resolved clone path and its Git sync state under `Scope From Git` before writing `Code Touched`.
- Search product clones and automation clones independently. Finding only `guides-ui-tests` never justifies saying no backend or product implementation exists.
- Before writing `none found`, report which relevant clones were searched and the exact Jira key, API terms, UI labels, enum names, workflow names, error strings, or config keys used. If a relevant available clone was not inspected, write `Clone discovered but not inspected` instead of `none found`.
- For translation-project API scope, search Starling/backend and integration tests with exact terms including `newTranslationProject`, `xliffTranslationProject`, `newMultiLingualTranslationProject`, `addToExistingProject`, `newScopingTranslationProject`, `translation project`, `baseline`, `versionAsOfDate`, and candidate endpoint/request field names from Jira.

Relevant clone categories:

- **Starling/backend**: backend code, APIs, services, persistence, migrations, workflow jobs, upload/reporting endpoints.
- **xmleditor**: classic XML editor UI, controllers, models, JSON views, dialogs, services, event handling.
- **new editor**: newer editor surfaces, redesigned panels/dialogs, new editor-specific services or state.
- **guides-ui-tests**: UI automation, Playwright/Selenium/Behave-style coverage, regression selectors, failure history.
- **dxml-it-tests**: integration/API/backend automation, service contracts, data migration, workflow and publish checks.

For each relevant clone:

- Record pre-sync SHA, branch, upstream, ahead/behind, and tracked/untracked status.
- Fetch all remotes with prune and tags before deciding whether pull is safe.
- For a dirty but otherwise fast-forwardable clone, preserve tracked and untracked developer work in a uniquely named stash, then pull only with `--ff-only`.
- Keep the successful sync stash intact and record its OID/ref and restore command; never pop or drop it automatically.
- If detached, diverged, without upstream, in an active Git operation, dirty in a submodule, or fetch/pull fails, do not reset/merge/rebase/switch/force-checkout. Use verified remote refs where possible and mark dependent claims provisional.
- Capture exact paths, functions/classes/components, tests, and line counts only from real diffs or search results.
- In pre-development, exact current files/functions/classes/workflows found by repo search are `Current implementation implicated`; they are not changed files.
- When synchronization is blocked, prefer verified remote refs for read-only current-code searches and label worktree-dependent results provisional.

## Product Code Mining

- Search Starling/backend, xmleditor, and new editor clones using exact stack-trace classes, method names, workflow names, endpoint paths, config keys, error strings, JCR paths, UI labels, and component names.
- Read the matched implementation branches, guards, persistence paths, cleanup behavior, retries, timeouts, status transitions, and logging to derive testable risks.
- Report exact current paths and symbols under `Code Touched` as implicated in pre-development, or as changed only when a diff proves the change.
- If the relevant product clone is available but not inspected, the code-impact portion remains incomplete even when automation clones were inspected.
- Never infer `Current implementation implicated: none found` from automation repositories alone. That conclusion requires completed searches in every discovered relevant product clone and must list the searched paths and terms.
- If no relevant product clone is available, say `Current product implementation not inspected` and ask for a clone/path only when code-grounded UAC coverage is necessary.

## Automation Coverage Mining

For `guides-ui-tests` and `dxml-it-tests`, inspect automation evidence when the repos are available:

- Synchronize each automation clone with `scripts/sync_evidence_repo.py <absolute-path> --stash-dirty` before searching it. Apply the same rule to editor E2E and any repository-specific UI, API, integration, publishing, or upgrade automation suite discovered during evidence collection.
- If an automation clone contains local developer changes, retain them in the named safety stash and inspect the clean synchronized revision. Report the stash OID/ref and restore command under `Scope From Git`; never count an unsynchronized dirty worktree as current automation coverage.

- Search by Jira key, summary terms, changed APIs, UI labels, selectors, config keys, workflow names, and similar failure text.
- Extract existing scenario names, test file paths, selectors/API fixtures, data builders, setup helpers, and assertions that already cover the workflow.
- Check skipped/flaky tags, quarantine markers, old failure names, recent failure screenshots/log names, and retry-specific code before claiming a scenario is safe.
- Search Jenkins/Allure-style names when present in Jira or failures, including build type, platform, vertical, suite name, feature file name, and scenario owner.
- For API/backend tickets, search `dxml-it-tests` by endpoint path, request parameter names, status/error contract, fixture path, and expected response fields.
- For UI tickets, search `guides-ui-tests` by visible label, data-testid/selector, page object method, feature file scenario title, step text, and failure screenshot folder/name.
- Identify automation coverage gaps: missing happy path, missing negative path, missing permissions/config coverage, missing cloud/on-prem parity, missing upgrade/backward-compat coverage, or missing API/UI pairing.
- Derive edge cases from existing assertions, fixtures, API contracts, branching conditions, historical failures, and similar Jira automation rather than from generic module names.
- Map useful existing coverage and automation coverage gaps into `Test Scenarios` or `Regression Areas`; do not dump raw automation files in the final plan.
- Prefer synchronized local automation clones for deep code search. Use GitHub MCP when a clone is absent or stale, when automation changes are in a PR/branch, or when current remote/default-branch evidence must be validated.
- Record the inspected revision or branch so old local tests are not reported as current coverage.
- Map automation evidence to AC IDs using `Covered`, `Partially covered`, `Not covered`, or `Not suitable for automation`.
- For each covered AC, capture the exact repository, test file, scenario/test method, reusable page object/API client/helper/fixture, setup/cleanup behavior, tags/suite, and key assertion.
- For every partial or missing AC, recommend the correct automation layer, exact existing file to extend or new file area, reusable helpers/fixtures, required test data, cleanup, polling/timeouts, assertions, and platform/config matrix.
- Identify skipped, flaky, quarantined, disabled, stale, and inaccessible tests separately; their existence does not count as reliable coverage.
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
- Put detailed existing automation, reusable helpers, reliability state, AC mapping, and missing automation recommendations in `Automation Coverage & Gaps`; keep only execution scenarios in `Test Scenarios` and product risk in `Regression Areas`.
- If no PR exists in pre-development, do not add a blocker. If product or automation clone evidence needed for a material claim is unavailable, identify that specific evidence gap.
- If an implementation/post-fix plan lacks a required diff, write `Draft blocker: implementation diff not inspected`.
