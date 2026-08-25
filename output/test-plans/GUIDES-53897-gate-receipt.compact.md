**Acceptance Criteria**
- AC-01
  - Starting point: the map query raises RuntimeNodeTraversalException.
  - Action: the cleanup job handles the exception.
  - Expected result: no later page query runs in the same execution.

- AC-02
  - Starting point: a query, cleanup, delete, or persistence step fails.
  - Action: the cleanup job handles the failed result page.
  - Expected result: the failure is reported and the Sling job result marks that result page as unsuccessful.

- AC-03
  - Starting point: the current result-page completion has failed.
  - Action: cleanup evaluates pagination progress.
  - Expected result: pagination progress does not advance.

- AC-04
  - Starting point: every fetched page completed successfully.
  - Action: a later query returns no matching maps.
  - Expected result: the job returns succeeded.

- AC-05
  - Starting point: the initial query returns no matching maps.
  - Action: the cleanup job handles that result.
  - Expected result: the job returns succeeded without starting cleanup.

- AC-06
  - Starting point: PurgePresetExecutionDataJob receives a Sling job cancellation or service shutdown request.
  - Action: the job reaches an approved stop point.
  - Expected result: no new page starts and the execution does not report success.

- AC-07
  - Starting point: one cleanup execution fails.
  - Action: primary failure logging completes.
  - Expected result: one event records the Sling job ID, pagination offset, last processed path, query parameters, and exception details.

- AC-08
  - Starting point: the read-limit failure persists.
  - Action: the approved retry policy is exhausted.
  - Expected result: query attempts and primary failure events stay within the approved policy limit.

- AC-09
  - Starting point: a map has valid and deleted-preset execution data.
  - Action: cleanup completes.
  - Expected result: deleted-preset data is absent and valid-preset data remains.

**Test Scenarios**
- Test data to prepare: use a production-equivalent author with a folder profile, one valid preset, one deleted preset, paged DITA maps under /content/dam, known map-context execution data, both scheduling callers, controlled query/delete/save failures, stop and shutdown controls, captured logs, repository snapshots, and cleanup that restores LimitReads when used.
- Incident recovery validation: confirm the affected job ID and customer-owned paths, obtain approval for exact scope, export a pre-change inventory and backup, test the rollback, preserve unrelated jobs and content, retain audit evidence, verify queue and disk recovery, and keep destructive actions outside production unless engineering approves them.
- P0 [TS-01] [AC-01]: Action: trigger RuntimeNodeTraversalException on the first map query. Expected: the same execution sends no later page query.
- P0 [TS-02] [AC-02]: Action: inject separate query, cleanup, delete, and persistence failures on a middle page. Expected: each failure is reported and the failed page is not treated as successful.
- P0 [TS-03] [AC-03]: Action: fail each processing stage before page completion. Expected: page position does not advance after any failed stage.
- P0 [TS-04] [AC-04]: Action: process several valid pages and then return an empty result. Expected: succeeded is returned only after every fetched page completes.
- P1 [TS-05] [AC-05]: Action: run cleanup with zero matching map assets. Expected: the initial empty result returns succeeded and no cleanup starts.
- P1 [TS-06] [AC-06]: Action: request cancellation and service shutdown at every approved stop point. Expected: no new page starts after the request is observed and the execution does not report success.
- P1 [TS-07] [AC-07]: Action: fail once before any successful page and once after a successful page. Expected: each execution emits one primary event with job ID, page position, last processed path, query parameters, and exception details.
- P0 [TS-08] [AC-08]: Action: keep the read-limit failure active through the approved retry policy. Expected: query attempts and primary failure events do not exceed the approved limit.
- P0 [TS-09] [AC-09]: Action: run cleanup for a map containing valid and deleted-preset execution data. Expected: the saved state keeps valid data and removes deleted-preset data.
- P2 [TS-10] [AC-09]: Action: rehearse approved incident recovery on a production-equivalent copy, then run normal cleanup. Expected: target orphan data is absent, valid data remains, unrelated content is unchanged, and rollback evidence is retained.
- P3 [Regression]: Action: Validate Highest priority: rerun normal folder-profile preset cleanup on a small repository and confirm orphan data is removed while valid data remains, because the fix changes the loop that owns those repository updates. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the Guides Administrative Task Queue with a failed cleanup followed by an unrelated administrative job, because new failure results and retries could block the single ordered worker. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck both preset-delete and folder-profile-delete scheduling paths together, because their duplicate-suppression and later-rescheduling parity is unresolved and may create overlapping cleanup work. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the workflow that writes map-context preset execution data before cleanup, because retry safety depends on preserving valid records created by that producer. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck large DAM queries with the deployed index state on Cloud and supported on-premise builds, because query or index changes can alter page membership and repository read cost. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck restart, cancellation, and rerun from page-level partial state, because the job saves each page and a new exit path could skip required cleanup or repeat repository changes. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Not covered - based on direct automation evidence for 3 AC mapping(s).
- AC-01, AC-02, AC-03, AC-04, AC-05, AC-08, AC-09: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-06: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-07: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
