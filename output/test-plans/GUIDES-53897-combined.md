**Understanding From Jira**
- Issue understood: The PurgePresetExecutionDataJob Sling job keeps paging DITA maps after RuntimeNodeTraversalException, so one failed execution can keep writing errors instead of reaching a terminal result.
- Why it matters: Customer context resolved from Jira: Broadcom is identified by the Jira customer field and issue tag; the production incident produced about 1 GB of logs per minute and filled the author disk to 98 percent.
- Requested outcome: Stop the repeated query loop, preserve failed-page position, report success only after complete cleanup, stop cooperatively, and record correlated failure evidence.
- Lifecycle understood as: Pre-Development UAC because GUIDES-53897 is Open, its fix version is Backlog, and no implementation change is linked.
- Evidence boundary: Evidence mode: full; live Jira, product RAG, indexed Jira history, and inspected local Git clones supplied evidence. Git claims are provisional because dirty worktrees were not synchronized, and Figma is not applicable to this backend job.

**Acceptance Criteria**
- AC-01 [Proposed]: (Negative) Given the map query raises RuntimeNodeTraversalException | When the cleanup job handles the exception | Then no later page query runs in the same execution | Evidence: Jira GUIDES-53897, inspected process loop, and human comparison supplied on 2026-08-25.
- AC-02 [Proposed]: (Negative) Given a query, cleanup, delete, or persistence step fails | When the cleanup job handles the failed result page | Then the failure is reported and the Sling job result marks that result page as unsuccessful | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-03 [Proposed]: (Integration) Given the current result-page completion has failed | When cleanup evaluates pagination progress | Then pagination progress does not advance | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-04 [Proposed]: (Basic) Given every fetched page completed successfully | When a later query returns no matching maps | Then the job returns succeeded | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-05 [Proposed]: (Basic) Given the initial query returns no matching maps | When the cleanup job handles that result | Then the job returns succeeded without starting cleanup | Evidence: Jira GUIDES-53897 and inspected PurgePresetExecutionDataJob process method.
- AC-06 [Proposed]: (Integration) Given PurgePresetExecutionDataJob receives a Sling job cancellation or service shutdown request | When the job reaches an approved stop point | Then no new page starts and the execution does not report success | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-07 [Proposed]: (Integration) Given one cleanup execution fails | When primary failure logging completes | Then one event records the Sling job ID, pagination offset, last processed path, query parameters, and exception details | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-08 [Proposed]: (Negative) Given the read-limit failure persists | When the approved retry policy is exhausted | Then query attempts and primary failure events stay within the approved policy limit | Evidence: Jira GUIDES-53897 and human comparison supplied on 2026-08-25.
- AC-09 [Proposed]: (Basic) Given a map has valid and deleted-preset execution data | When cleanup completes | Then deleted-preset data is absent and valid-preset data remains | Evidence: Jira GUIDES-53897 and inspected deletePresetExecDataInMap method.

**Expected Behaviour**
- Current implementation observation: process enters an open paging loop at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:56` and exits only after an empty result page.
- Current implementation observation: the catch block logs an exception at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:70`, then advances the offset at line 73 and starts another iteration.
- Current implementation observation: process returns succeeded after leaving the loop at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:76`, even though the catch path records no failure result.
- Current implementation observation: deletePresetExecDataInMap skips an absent map-context node and removes only execution data whose backing preset is missing at `C:\starling\core\publish-listener\src\main\java\com\adobe\aem\guides\publish\job\PurgePresetExecutionDataJob.java:79`.
- Current implementation observation: the captured administrative-queue configuration uses one ordered worker, two retries, and a 2000 millisecond retry delay in `C:\starling\AEM6.x\repo\jcr_root\libs\fmdita\config\org.apache.sling.event.jobs.QueueConfiguration~guidesAdministrativeTaskQueue.xml:4`; the target retry and terminal-result contract remains unresolved.
- Current implementation observation: both `C:\starling\core\utils\src\main\java\com\adobe\fmdita\presets\service\FolderProfilePresetStrategy.java:78` and `C:\starling\core\publish-listener\src\main\java\com\adobe\fmdita\rest\folderprofiles\FolderProfilesAPI.java:1213` can schedule the cleanup topic, so scheduling parity remains an explicit question.
- Human-review boundary: retryable versus permanent errors, exact Sling terminal results, restart behavior, and idempotent rerun are not yet approved product contracts.
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
- Current implementation implicated: `C:\starling\core\publish-listener\src\main\java\com\adobe\fmdita\rest\folderprofiles\FolderProfilesAPI.java` contains a second cleanup-topic scheduling path after folder-profile deletion.
- Potential code impact, inferred rather than changed: the failure exit, terminal result, stop signal, progress reporting, paging strategy, and repository index may need coordinated changes.

**Lines Changed**
- Not applicable - development has not started.

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

**Known Jira Bugs / Past Similar Tickets**
- No same-mechanism Jira ticket was established from validated indexed history; area-only query and queue results were excluded.
- Historical search status: same-customer and cross-customer indexed searches used the Platform component with the RuntimeNodeTraversalException error plus purge-job workflow terms; both returned no match. No Jira JQL candidate was retained, so no mutable historical status or fix claim is used.

**Regression Areas**
- Highest priority: rerun normal folder-profile preset cleanup on a small repository and confirm orphan data is removed while valid data remains, because the fix changes the loop that owns those repository updates.
- Recheck the Guides Administrative Task Queue with a failed cleanup followed by an unrelated administrative job, because new failure results and retries could block the single ordered worker.
- Recheck both preset-delete and folder-profile-delete scheduling paths together, because their duplicate-suppression and later-rescheduling parity is unresolved and may create overlapping cleanup work.
- Recheck the workflow that writes map-context preset execution data before cleanup, because retry safety depends on preserving valid records created by that producer.
- Recheck large DAM queries with the deployed index state on Cloud and supported on-premise builds, because query or index changes can alter page membership and repository read cost.
- Recheck restart, cancellation, and rerun from page-level partial state, because the job saves each page and a new exit path could skip required cleanup or repeat repository changes.

**Automation Coverage & Gaps**
- Main feature coverage: Not covered - exact searches found no existing automated test; the target layer is backend integration, setup uses seeded job data, poll reads Sling state, timeout uses the approved job wait, assert checks terminal and repository results, cleanup removes fixtures, and tag is platform-backend-regression.
- AC-01, AC-02, AC-03, AC-04, AC-05, AC-08, AC-09 - Not covered: Layer: backend integration in `C:\api automation\dxml-it-tests`; Setup: seed paged maps and controllable query, delete, and save failures; Poll: read the job record; Timeout: use the approved job timeout; Assert: check query attempts, page position, result, and repository snapshots; Cleanup: restore failure settings and remove fixtures; Tag: platform-backend-regression.
- AC-06 - Not covered: Layer: job-lifecycle integration in `C:\api automation\dxml-it-tests`; Setup: add controllable cancellation and shutdown hooks at each approved stop point; Poll: wait until processing stops; Timeout: use the approved job timeout; Assert: check that no later page starts and success is not reported; Cleanup: restore the isolated service; Tag: platform-job-lifecycle.
- AC-07 - Not covered: Layer: log-capture integration in `C:\api automation\dxml-it-tests`; Setup: fail once before and once after a successful page; Poll: wait until the execution ends; Timeout: use the approved job timeout; Assert: check one primary event and every required field; Cleanup: remove captured logs and fixtures; Tag: platform-observability.

**Open Questions**
- OQ-01: Must the large DAM query keep offset-based pagination, use a custom index, or only stop safely at the Oak read limit? What controlled workload, before-fix baseline, completion threshold, and log-growth threshold apply? QA impact: the answer separates bounded failure from successful large-repository cleanup and supplies the performance sign-off oracle.
- OQ-02: Which query, result-iteration, delete, save, and unexpected errors are retryable, and which are permanent? QA impact: the answer defines the error matrix and whether the same page may retry without advancing position.
- OQ-03: What Sling result applies separately to explicit stop, retryable failure, permanent failure, and service shutdown, and which deployed queue configuration defines attempts, delay, and aggregate log limits? QA impact: the answer defines terminal-result, retry-exhaustion, and queue-isolation assertions without inventing three executions.
- OQ-04: There is no approved upper bound today. What limit on execution duration, page count, mutation count, or consecutive no-progress count must end one execution? QA impact: the approved value supplies a measurable defensive bound without imposing an unsupported limit on valid large repositories.
- OQ-05: After restart or interruption, must cleanup restart from the beginning, resume from a saved position, or require a new request? QA impact: the answer defines partial-write, restart, and rerun oracles without assuming idempotency.
- OQ-06: When concurrent repository changes shift result positions during paging, what snapshot rule proves that no eligible asset is skipped or processed more than once? QA impact: the answer defines the concurrent-mutation fixture and page-membership oracle.
- OQ-07: Which structured Sling job progress or job-context status is missing today? Which values are execution results, and which states such as queued, retrying, running, or stalled belong only to operational monitoring? QA impact: the answer separates terminal-result assertions from dashboard or watchdog-state assertions.
- OQ-08: Must the fixed job recover orphan data left by an earlier blocked purge? QA impact: the answer decides whether old-state convergence is sign-off scope or a separate recovery task.
- OQ-09: Must preset deletion and folder-profile deletion use the same duplicate-scheduling rule, produce one logical cleanup job, and allow a later legitimate schedule after termination? QA impact: the answer defines caller parity, duplicate-event, and rescheduling tests.
- OQ-10: Is raising On-Premise Oak QueryEngineSettings LimitReads an approved temporary mitigation for Broadcom? QA impact: the answer decides whether QA validates an environment-specific workaround separately from the product fix.
