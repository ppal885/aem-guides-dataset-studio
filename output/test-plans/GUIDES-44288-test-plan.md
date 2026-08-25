**Understanding From Jira**
- Issue understood: One publish writes the same DITA-OT generation log twice because PublishWorkflowStep logs it after generation and again after storing output metadata.
- Why it matters: Customer context resolved from Jira: EY forwards these logs to Splunk or ELK and can publish 2,000-3,000 documents in one bulk action, so duplicate entries increase log volume and make automated analysis harder.
- Requested outcome: Write one application-log entry for each DITA-OT generation log while keeping its text, the publish result, the published path, and saved output-history data unchanged.
- Lifecycle understood as: Implementation Review for AdobeStarling/starling PR #8089 at captured commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c.
- Evidence boundary: Evidence mode: full. Live Jira and all eight comments were previously fetched, product RAG and indexed Jira history were queried, the PR branch and Starling source were inspected, and both automation clones were searched in this pass. Jira has no attachments, Figma is not applicable, and the performance threshold remains unresolved in OQ-01.

**Acceptance Criteria**
- AC-01 [Proposed]: (Basic) Given one map completes output generation | When its publish result is processed | Then the application log contains exactly one matching DITA-OT generation entry | Evidence: Jira description GUIDES-44288 and source file C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishWorkflowStep.java:497-501,923-925.
- AC-02 [Proposed]: (Negative) Given output generation returns a DITA-OT log before a later publish step fails | When the publish ends with that later failure | Then the application log still contains exactly one matching DITA-OT generation entry | Evidence: commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c and its inspected unit-test change.
- AC-03 [Proposed]: (Integration) Given output generation returns a known DITA-OT log | When that log is written to the application log | Then its single entry contains the complete returned text | Evidence: source file C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishOutput.java:69-70 and commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c.
- AC-04 [Proposed]: (Integration) Given a valid map and preset have a saved before-fix baseline | When the same map is published after the fix | Then its result and saved output details match the baseline | Evidence: source file C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishWorkflowStep.java:887-925 and commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c.

**Expected Behaviour**
- Jira reports two identical application-log writes for one publish, with the second write occurring during output-metadata storage.
- Current source writes the returned generation log at C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishWorkflowStep.java:501 and again at line 925.
- PR #8089 removes only the second write at line 925. It leaves the earlier write, metadata save, exception handling, and output processing unchanged.
- PublishOutput.getErrorLog returns the full publishLog text at C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishOutput.java:69-70.
- Output history continues to store the generation log at C:/starling/core/publish-workflow/src/main/java/com/adobe/fmdita/publishworkflow/PublishWorkflowStep.java:890-900, so the application-log change must not remove the retained history log.
- Performance sign-off is conditional because Jira gives a 2,000-3,000-document workload but no approved environment, baseline, latency threshold, throughput threshold, or log-growth threshold.

**Scope From Git**
- Product clone C:\starling was inspected on branch develop at local SHA fdfa72777a2d73b2cdba6d2bdd60ea5535bad75f; the previously fetched origin/develop ref is SHA 69a98eab3948e98aa78684276be7d37fe30b39ea, and the current worktree is 0 ahead and 1230 behind that captured ref with unrelated user changes preserved.
- PR evidence uses the captured origin/crosshair/guides-44288 ref at SHA 0fb599b1d2247ee1c0edcd79c373e184b02f027c. Its diff against the captured origin/develop ref changes only PublishWorkflowStep.java and PublishWorkflowStepTest.java.
- Automation clone C:\api automation\dxml-it-tests was searched at local SHA 46709a94fbf357a6277f780202401149c5820054 on branch fix-changebars-nativepdf-lapwing-benchmark; the clone is 2 ahead and 0 behind its captured upstream, and no GUIDES-44288, getErrorLog, DITA-OT generation log, or PublishWorkflowStep scenario was found.
- Automation clone C:\ui_framework\new_editor\guides-ui-tests was searched at local SHA bf5dca679ec84f6128d4fe8d9b3b12201e2cc5bb on branch develop; the clone is 0 ahead and 1000 behind its captured upstream, and no GUIDES-44288, getErrorLog, DITA-OT generation log, or PublishWorkflowStep scenario was found.
- Figma evidence is not applicable because this change only removes one backend log write and introduces no visual behavior.

**Code Touched**
- Changed source: C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\publishworkflow\PublishWorkflowStep.java removes the second log.info call after session.save in storeGeneratedOutputMetadata.
- Changed test: C:\starling\core\publish-workflow\src\test\java\com\adobe\fmdita\publishworkflow\PublishWorkflowStepTest.java checks one log write on success and one log write when a downstream step fails.
- Unchanged producer: C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\publishworkflow\PublishOutput.java still returns the full publishLog text from getErrorLog.

**Lines Changed**
- PublishWorkflowStep.java has 0 additions and 5 deletions in the captured PR diff.
- PublishWorkflowStepTest.java has 75 additions and 17 deletions in the captured PR diff.

**Test Scenarios**
- Test data to prepare: use a build containing commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c; create map /content/dam/guides-44288/single.ditamap and 20 small numbered maps; configure one supported preset that uses PublishWorkflowStep; capture application logs with a publish-job identifier; save a before-fix output path, job result, output-history properties, and retained DITA-OT log; provide a fault hook after output generation; and clean up the generated outputs, history nodes, and log captures.
- P0 [TS-01] [AC-01]: Action: publish single.ditamap successfully and count matching DITA-OT generation entries for its job identifier. Expected: exactly one matching application-log entry exists.
- P0 [TS-02] [AC-02]: Action: publish single.ditamap while the post-generation fault hook fails the next publish step. Expected: exactly one matching DITA-OT generation entry exists even though the publish ends in failure.
- P1 [TS-03] [AC-03]: Action: publish a map whose generated log contains a unique marker and compare the emitted entry with PublishOutput.getErrorLog. Expected: the one emitted entry matches the complete returned text byte for byte.
- P1 [TS-04] [AC-04]: Action: repeat the baseline publish after the fix and compare the job result, output path, output-history properties, and retained DITA-OT log. Expected: every saved value matches the before-fix baseline except the application-log entry count.
- P2 [TS-05] [AC-01]: Action: publish the 20 numbered maps through the supported bulk API and group captured entries by job and map. Expected: every completed map has exactly one matching DITA-OT generation entry, with no missing or duplicate map entry.

**Known Jira Bugs / Past Similar Tickets**
- Search status: indexed Jira history was searched for EY duplicate-log symptoms and for cross-customer PublishWorkflowStep duplicate logging in the Publishing component; no same-mechanism ticket was found.
- Narrow JQL intents covered the exact error text with text ~ "PublishWorkflowStep" AND text ~ "log.info", plus the workflow symptom with text ~ "duplicate" AND text ~ "log" AND component = Publishing; neither search returned a same-defect-class ticket.
- No same-defect-class history is used as acceptance authority because the available results did not identify another publish-workflow log-emission defect.

**Regression Areas**
- Re-test Native PDF, AEM Sites, Native AEM Site, HTML5, EPUB, and JSON presets that use PublishWorkflowStep because the shared metadata-storage method is not limited to one output type.
- Re-test output-history log storage and metadata after both successful and failed publishes because removing the application-log duplicate must not remove the retained DITA-OT log or change saved job data.
- Re-test customer log forwarding with a unique job identifier because removing the wrong call could leave Splunk or ELK without the generation log that EY uses for automated analysis.
- Re-test a small functional bulk batch for one-entry-per-map behavior, while keeping the 2,000-3,000-document performance run blocked until its workload and oracle are approved.

**Automation Coverage & Gaps**
- Main feature coverage: Partially covered - the captured PR branch has unit checks for one log write on success and after a downstream failure, but the product automation repositories have no matching end-to-end scenario.
- AC-01, AC-02, AC-03 - Partially covered: the PR test class checks the success count, downstream-failure count, and retained full log text; an end-to-end application-log assertion is still absent from dxml-it-tests.
- AC-04 - Not covered: Layer: backend integration; Setup: record a successful before-fix publish and its output-history data; Poll: wait for the post-fix job to finish; Timeout: use the suite's configured publish-job timeout; Assert: compare result, path, properties, and retained log with the baseline; Cleanup: remove the generated output and history fixture; Tag: publish-workflow-log-regression.
- Conditional performance coverage: Unverified until OQ-01 supplies an approved environment, a workload within EY's 2,000-3,000-document range, and measurable baseline or SLA thresholds.

**Open Questions**
- OQ-01: Which approved workload should QA use within EY's reported 2,000-3,000-document bulk publish, and what measurable baseline or SLA threshold must latency, throughput, and log growth meet? QA impact: The answer defines the environment, load model, metrics, and pass or fail oracle for performance sign-off.
- OQ-02: Must one DITA-OT generation log still be written when generation succeeds but a later publish step fails? QA impact: The answer decides whether AC-02 is release-blocking product scope or only a PR regression check.
- OQ-03: Must the application log preserve the complete text returned by PublishOutput.getErrorLog? QA impact: The answer decides whether exact text comparison in AC-03 is a release-blocking product contract or only regression coverage.
- OQ-04: Must publish results and saved output metadata remain identical to the before-fix baseline? QA impact: The answer decides whether AC-04 is a release-blocking product contract or only regression coverage.
