**Understanding From Jira**
- Issue understood: The PurgePresetExecutionDataJob Sling job keeps paging DITA maps after RuntimeNodeTraversalException, so one failed execution can keep writing errors instead of reaching a terminal result.
- Why it matters: Customer context resolved from Jira: Broadcom is identified by the Jira customer field and issue tag; the production incident produced about 1 GB of logs per minute and filled the author disk to 98 percent.
- Requested outcome: Stop the failed execution, report truthful results, limit retries and logs, support cancellation and shutdown, expose useful status, and keep cleanup safe to retry.
- Lifecycle understood as: Pre-Development UAC because GUIDES-53897 is Open, its fix version is Backlog, and no implementation change is linked.
- Evidence boundary: Evidence mode: full; live Jira, product RAG, indexed Jira history, and inspected local Git clones supplied evidence. Git claims are provisional because dirty worktrees were not synchronized, and Figma is not applicable to this backend job.

**Acceptance Criteria**
- AC-01 [Confirmed]: (Negative) Given the map query raises RuntimeNodeTraversalException | When the cleanup job handles that query failure | Then the current execution sends zero later page queries | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-02 [Confirmed]: (Negative) Given a query, delete, or save step raises an unexpected error | When the cleanup job handles the error | Then the current execution sends zero more requests for that page | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-03 [Confirmed]: (Negative) Given the read-limit failure repeats on every queue attempt | When the configured retry policy finishes | Then the job has at most three executions and at most one error log per execution | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-04 [Confirmed]: (Negative) Given a cleanup execution ends after an error | When the Sling job result is recorded | Then the result is failed | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-05 [Confirmed]: (Integration) Given a cleanup execution receives a cancellation signal | When the current page finishes | Then the execution stops with a cancelled result | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-06 [Confirmed]: (Basic) Given all matching map pages are available | When the cleanup job processes every page | Then the Sling job result is succeeded | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-07 [Confirmed]: (Negative) Given one page fails during cleanup | When the cleanup execution handles that failure | Then zero later pages are processed and success is not reported | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-08 [Confirmed]: (Integration) Given service shutdown begins during a cleanup execution | When the current page finishes | Then the execution stops with a cancelled result | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-09 [Confirmed]: (Integration) Given a cleanup execution fails | When its failure entry is written | Then one log entry records the job ID, page position and query parameters plus the last successful map path or none | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-10 [Confirmed]: (Integration) Given a cleanup job has one supported execution state | When its Sling status is read | Then the status is running, failed, or completed as applicable | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-11 [Confirmed]: (Integration) Given preset execution data was already removed | When the cleanup job is retried or rerun | Then the job keeps valid preset data and reports no missing-node error | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-12 [Confirmed]: (Basic) Given a map contains valid preset data plus data for a deleted preset | When the cleanup job completes | Then the orphan data is absent and the valid preset data remains saved | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.
- AC-13 [Confirmed]: (Basic) Given the repository contains zero matching map assets | When the cleanup job requests its first page | Then the job returns succeeded without changing repository content | Evidence: Jira accepted UAC comment GUIDES-53897 dated 2026-08-24.

**Expected Behaviour**
- Current implementation observation: process enters an open paging loop at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:56` and exits only after an empty result page.
- Current implementation observation: the catch block logs an exception at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:70`, then advances the offset at line 73 and starts another iteration.
- Current implementation observation: process returns succeeded after leaving the loop at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:76`, even though the catch path records no failure result.
- Current implementation observation: deletePresetExecDataInMap skips an absent map-context node and removes only execution data whose backing preset is missing at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:79`.
- Current implementation observation: the administrative queue uses one ordered worker, two retries, and a 2000 millisecond retry delay in `C:\starling\AEM6.x\repo\jcr_root\libs\fmdita\config\org.apache.sling.event.jobs.QueueConfiguration~guidesAdministrativeTaskQueue.xml:4`.
- Current implementation observation: deleting a folder-profile preset schedules this topic for the next day when no equivalent job is already scheduled at `C:\starling\core\utils\src\main\java\com\adobe\fmdita\presets\service\FolderProfilePresetStrategy.java:78`.
- RAG-supported guidance: a large AEM repository query needs a suitable index and a measurable workload, but current evidence does not define an approved completion or log-growth SLA for this job.

**Scope From Git**
- Lifecycle stage: Pre-Development UAC; readiness target is accepted behavior for an implementation that has not started.
- Issue and development evidence: live Jira GUIDES-53897 was fetched; no pull request, branch, commit, or candidate build is linked, so PR discovery is not applicable.
- Product clone: `C:\starling`; branch develop; pre-sync and inspected SHA fdfa72777a2d73b2cdba6d2bdd60ea5535bad75f; upstream and ahead/behind not captured; dirty before and after; fetch and pull not run; the inspected worktree is provisional and remained unchanged.
- UI automation clone: `C:\UI TEST\guides-ui-tests`; branch main; pre-sync and inspected SHA 67fe7f35b1b4cf06fb87ebbd17d449dbf27ad1ac; upstream and ahead/behind not captured; dirty before and after; fetch and pull not run; the inspected worktree is provisional and remained unchanged.
- Backend automation clone: `C:\api automation\dxml-it-tests`; branch fix-changebars-nativepdf-lapwing-benchmark; pre-sync and inspected SHA 46709a94fbf357a6277f780202401149c5820054; upstream and ahead/behind not captured; dirty before and after; fetch and pull not run; the inspected worktree is provisional and remained unchanged.
- Figma and design evidence: not applicable because this ticket changes a backend Sling job and no UI flow is in scope.

**Code Touched**
- No code changes yet - development has not started.
- Current implementation implicated: `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java` contains process, deletePresetExecDataInMap, and getQueryPredicatesForGettingDitamaps.
- Current implementation implicated: `C:\starling\AEM6.x\repo\jcr_root\libs\fmdita\config\org.apache.sling.event.jobs.QueueConfiguration~guidesAdministrativeTaskQueue.xml` defines queue attempts, delay, order, and worker count.
- Current implementation implicated: `C:\starling\core\utils\src\main\java\com\adobe\fmdita\presets\service\FolderProfilePresetStrategy.java` schedules the cleanup topic after preset deletion.
- Potential code impact, inferred rather than changed: the failure exit, terminal result, stop signal, progress reporting, paging strategy, and repository index may need coordinated changes.

**Lines Changed**
- Not applicable - development has not started.

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

**Known Jira Bugs / Past Similar Tickets**
- No same-mechanism Jira ticket was established from validated indexed history; area-only query and queue results were excluded.
- Historical search status: same-customer and cross-customer indexed searches used the Platform component with the RuntimeNodeTraversalException error plus purge-job workflow terms; both returned no match. No Jira JQL candidate was retained, so no mutable historical status or fix claim is used.

**Regression Areas**
- Highest priority: rerun normal folder-profile preset cleanup on a small repository and confirm orphan data is removed while valid data remains, because the fix changes the loop that owns those repository updates.
- Recheck the Guides Administrative Task Queue with a failed cleanup followed by an unrelated administrative job, because new failure results and retries could block the single ordered worker.
- Recheck preset delete scheduling and duplicate suppression across repeated deletions, because changing termination behavior must not create duplicate scheduled cleanup jobs.
- Recheck the workflow that writes map-context preset execution data before cleanup, because retry safety depends on preserving valid records created by that producer.
- Recheck large DAM queries with the deployed index state on Cloud and supported on-premise builds, because query or index changes can alter page membership and repository read cost.
- Recheck restart, cancellation, and rerun from page-level partial state, because the job saves each page and a new exit path could skip required cleanup or repeat repository changes.

**Automation Coverage & Gaps**
- Main feature coverage: Not covered - exact searches found no existing automated test; the target layer is backend integration, setup uses seeded job data, poll reads Sling state, timeout uses the approved job wait, assert checks terminal and repository results, cleanup removes fixtures, and tag is platform-backend-regression.
- AC-01, AC-02, AC-03, AC-04, AC-06, AC-07, AC-13 - Not covered: Layer is backend integration in a new job-focused test under `C:\api automation\dxml-it-tests`; setup uses seeded maps and deterministic query/delete/save failures; poll reads the Sling terminal record; timeout comes from the approved job-wait configuration; assert checks query count, attempts, error count, terminal result, and repository content; cleanup removes fixtures and restores failure settings; tag the test platform-backend-regression.
- AC-05, AC-08, AC-10 - Not covered: Layer is backend integration under `C:\api automation\dxml-it-tests`; setup starts a long job with controllable cancellation and shutdown; poll reads running through terminal status; timeout comes from the approved stop-wait configuration; assert checks cancelled results plus unchanged later-page content; cleanup restarts only the isolated test service and removes fixtures; tag the test platform-job-lifecycle.
- AC-09 - Not covered: Layer is backend integration with captured logs under `C:\api automation\dxml-it-tests`; setup injects failures before and after a successful page; poll waits for the terminal job state; timeout comes from the approved job-wait configuration; assert checks one correlated log entry and every required field; cleanup removes fixtures and captured logs; tag the test platform-observability.
- AC-11, AC-12 - Not covered: Layer is backend repository integration under `C:\api automation\dxml-it-tests`; setup seeds valid, orphan, and already-absent data; poll waits for terminal status; timeout comes from the approved job-wait configuration; assert compares before and after repository snapshots; cleanup removes seeded maps and presets; tag the test platform-cleanup-idempotency.

**Open Questions**
- OQ-01: Should query or index redesign be included, and what production-scale map count plus completion or log-growth SLA should QA use? QA impact: the answer decides whether performance testing becomes a sign-off criterion and supplies its workload and threshold.
- OQ-02: Which query, delete, and save failures are retryable, and may any retry occur inside one execution? QA impact: the answer defines the fault matrix and whether AC-02 expects an immediate stop or a finite internal retry.
- OQ-03: What page, item, elapsed-time, or no-progress limit must end a runaway execution? QA impact: the approved value supplies the missing measurable progress-bound scenario and terminal oracle.
- OQ-04: After content mutation or service restart during paging, should cleanup resume or restart, and what proves no map was skipped or repeated? QA impact: the answer defines snapshot, checkpoint, and restart scenarios for deterministic sign-off.
- OQ-05: Should a deterministic read-limit failure short-circuit two queue retries, and how should unrelated queued jobs proceed? QA impact: the answer changes total-attempt assertions, aggregate log limits, and the queue-isolation scenario.
- OQ-06: Must status expose stalled and retrying in addition to running, failed, and completed? QA impact: the answer decides whether extra visible states and transition scenarios are required.
- OQ-07: Must the fixed job recover orphan data left by an earlier blocked purge? QA impact: the answer decides whether stale-state convergence is a sign-off requirement or a separate recovery task.
- OQ-08: Is raising On-Premise Oak QueryEngineSettings LimitReads an approved temporary mitigation for Broadcom? QA impact: the answer decides whether QA validates a config-only mitigation before the product fix is released.
