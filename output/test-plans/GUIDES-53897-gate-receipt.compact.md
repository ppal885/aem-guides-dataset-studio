**Acceptance Criteria**
- AC-01
  - Starting point: the map query raises RuntimeNodeTraversalException.
  - Action: the cleanup job handles that query failure.
  - Expected result: the current execution sends zero later page queries.

- AC-02
  - Starting point: a query, delete, or save step raises an unexpected error.
  - Action: the cleanup job handles the error.
  - Expected result: the current execution sends zero more requests for that page.

- AC-03
  - Starting point: the read-limit failure repeats on every queue attempt.
  - Action: the configured retry policy finishes.
  - Expected result: the job has at most three executions and at most one error log per execution.

- AC-04
  - Starting point: a cleanup execution ends after an error.
  - Action: the Sling job result is recorded.
  - Expected result: the result is failed.

- AC-05
  - Starting point: a cleanup execution receives a cancellation signal.
  - Action: the current page finishes.
  - Expected result: the execution stops with a cancelled result.

- AC-06
  - Starting point: all matching map pages are available.
  - Action: the cleanup job processes every page.
  - Expected result: the Sling job result is succeeded.

- AC-07
  - Starting point: one page fails during cleanup.
  - Action: the cleanup execution handles that failure.
  - Expected result: zero later pages are processed and success is not reported.

- AC-08
  - Starting point: service shutdown begins during a cleanup execution.
  - Action: the current page finishes.
  - Expected result: the execution stops with a cancelled result.

- AC-09
  - Starting point: a cleanup execution fails.
  - Action: its failure entry is written.
  - Expected result: one log entry records the job ID, page position and query parameters plus the last successful map path or none.

- AC-10
  - Starting point: a cleanup job has one supported execution state.
  - Action: its Sling status is read.
  - Expected result: the status is running, failed, or completed as applicable.

- AC-11
  - Starting point: preset execution data was already removed.
  - Action: the cleanup job is retried or rerun.
  - Expected result: the job keeps valid preset data and reports no missing-node error.

- AC-12
  - Starting point: a map contains valid preset data plus data for a deleted preset.
  - Action: the cleanup job completes.
  - Expected result: the orphan data is absent and the valid preset data remains saved.

- AC-13
  - Starting point: the repository contains zero matching map assets.
  - Action: the cleanup job requests its first page.
  - Expected result: the job returns succeeded without changing repository content.

**Test Scenarios**
- Test data to prepare: use a production-equivalent author with a folder-profile configuration, one valid preset, one deleted preset, DITA maps under /content/dam, known map-context execution data, a controlled RuntimeNodeTraversalException hook, query/delete/save failure hooks, cancellation and shutdown controls, Sling job state access, captured logs, repository snapshots, and cleanup that restores LimitReads when that test setting is used.
- Incident recovery validation: confirm the affected job ID and customer-owned paths, obtain approval for exact scope, export a pre-change inventory and backup, test the rollback, preserve unrelated jobs and content, retain audit evidence, verify queue and disk recovery, and keep destructive actions outside production unless engineering approves them.
- P0 [TS-01] [AC-01]: Action: trigger RuntimeNodeTraversalException on the first map page. Expected: the current execution sends zero later page queries and the repository snapshot stays unchanged.
- P0 [TS-02] [AC-02]: Action: inject separate failures during query, delete, and save processing. Expected: each execution sends zero more requests for its failed page and preserves later-page repository content.
- P0 [TS-03] [AC-03]: Action: keep the read-limit failure active through queue exhaustion. Expected: the records show at most three executions and at most one matching error entry per execution.
- P0 [TS-04] [AC-04, AC-07]: Action: fail one cleanup page before later maps are processed. Expected: the Sling result is failed and no later map content changes.
- P1 [TS-05] [AC-05]: Action: request cancellation during a page of a long cleanup run. Expected: processing stops after that page and the Sling result is cancelled.
- P0 [TS-06] [AC-06]: Action: run cleanup across several valid pages with orphan data. Expected: every orphan entry is removed before the Sling result becomes succeeded.
- P1 [TS-07] [AC-07]: Action: fail a middle page while later pages contain orphan data. Expected: later pages remain unchanged and the execution reports no success.
- P1 [TS-08] [AC-08]: Action: begin service shutdown during a cleanup page. Expected: processing stops after that page and the Sling result is cancelled.
- P1 [TS-09] [AC-09]: Action: fail once before any successful page and once after a successful page. Expected: each single failure entry contains the job ID, page position, query parameters, and the required last-path value.
- P1 [TS-10] [AC-10]: Action: observe one active run, one failed run, and one completed run. Expected: the visible Sling status matches running, failed, and completed for those records.
- P1 [TS-11] [AC-11]: Action: retry a partial run and rerun the completed cleanup. Expected: valid preset data remains present and no missing-node error appears.
- P0 [TS-12] [AC-12]: Action: run cleanup for a map containing valid plus orphan preset data. Expected: the saved repository state contains the valid entry and excludes the orphan entry.
- P1 [TS-13] [AC-13]: Action: run cleanup with zero matching map assets. Expected: repository content stays unchanged and the Sling result is succeeded after the first query.
- P2 [TS-14] [AC-11, AC-12]: Action: rehearse approved incident recovery on a production-equivalent copy, then rerun cleanup. Expected: target orphan data is absent, valid data is present, unrelated content is unchanged, and rollback evidence is retained.
- P3 [Regression]: Action: Validate Highest priority: rerun normal folder-profile preset cleanup on a small repository and confirm orphan data is removed while valid data remains, because the fix changes the loop that owns those repository updates. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the Guides Administrative Task Queue with a failed cleanup followed by an unrelated administrative job, because new failure results and retries could block the single ordered worker. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck preset delete scheduling and duplicate suppression across repeated deletions, because changing termination behavior must not create duplicate scheduled cleanup jobs. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the workflow that writes map-context preset execution data before cleanup, because retry safety depends on preserving valid records created by that producer. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck large DAM queries with the deployed index state on Cloud and supported on-premise builds, because query or index changes can alter page membership and repository read cost. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck restart, cancellation, and rerun from page-level partial state, because the job saves each page and a new exit path could skip required cleanup or repeat repository changes. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Not covered - based on direct automation evidence for 4 AC mapping(s).
- AC-01, AC-02, AC-03, AC-04, AC-06, AC-07, AC-13: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-05, AC-08, AC-10: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-09: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-11, AC-12: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
