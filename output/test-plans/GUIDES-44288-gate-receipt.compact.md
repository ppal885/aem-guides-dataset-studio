**Acceptance Criteria**
- AC-01
  - Starting point: one map completes output generation.
  - Action: its publish result is processed.
  - Expected result: the application log contains exactly one matching DITA-OT generation entry.

- AC-02
  - Starting point: output generation returns a DITA-OT log before a later publish step fails.
  - Action: the publish ends with that later failure.
  - Expected result: the application log still contains exactly one matching DITA-OT generation entry.

- AC-03
  - Starting point: output generation returns a known DITA-OT log.
  - Action: that log is written to the application log.
  - Expected result: its single entry contains the complete returned text.

- AC-04
  - Starting point: a valid map and preset have a saved before-fix baseline.
  - Action: the same map is published after the fix.
  - Expected result: its result and saved output details match the baseline.

**Test Scenarios**
- Test data to prepare: use a build containing commit 0fb599b1d2247ee1c0edcd79c373e184b02f027c; create map /content/dam/guides-44288/single.ditamap and 20 small numbered maps; configure one supported preset that uses PublishWorkflowStep; capture application logs with a publish-job identifier; save a before-fix output path, job result, output-history properties, and retained DITA-OT log; provide a fault hook after output generation; and clean up the generated outputs, history nodes, and log captures.
- P0 [TS-01] [AC-01]: Action: publish single.ditamap successfully and count matching DITA-OT generation entries for its job identifier. Expected: exactly one matching application-log entry exists.
- P0 [TS-02] [AC-02]: Action: publish single.ditamap while the post-generation fault hook fails the next publish step. Expected: exactly one matching DITA-OT generation entry exists even though the publish ends in failure.
- P1 [TS-03] [AC-03]: Action: publish a map whose generated log contains a unique marker and compare the emitted entry with PublishOutput.getErrorLog. Expected: the one emitted entry matches the complete returned text byte for byte.
- P1 [TS-04] [AC-04]: Action: repeat the baseline publish after the fix and compare the job result, output path, output-history properties, and retained DITA-OT log. Expected: every saved value matches the before-fix baseline except the application-log entry count.
- P2 [TS-05] [AC-01]: Action: publish the 20 numbered maps through the supported bulk API and group captured entries by job and map. Expected: every completed map has exactly one matching DITA-OT generation entry, with no missing or duplicate map entry.
- P3 [Regression]: Action: Validate Re-test Native PDF, AEM Sites, Native AEM Site, HTML5, EPUB, and JSON presets that use PublishWorkflowStep because the shared metadata-storage method is not limited to one output type. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test output-history log storage and metadata after both successful and failed publishes because removing the application-log duplicate must not remove the retained DITA-OT log or change saved job data. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test customer log forwarding with a unique job identifier because removing the wrong call could leave Splunk or ELK without the generation log that EY uses for automated analysis. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test a small functional bulk batch for one-entry-per-map behavior, while keeping the 2,000-3,000-document performance run blocked until its workload and oracle are approved. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Partially covered - based on direct automation evidence for 3 AC mapping(s).
- AC-01, AC-02, AC-03: Partially covered - extend integration/API test automation to cover the missing primary-result or boundary assertion.
- AC-04: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- Main feature: Unverified - confirm coverage in the appropriate feature file or integration-test suite before automation handoff.
