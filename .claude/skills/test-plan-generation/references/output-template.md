# Output Template

Use this file before writing the full validated record artifact.

## Required Shape

Use exactly these sections. Keep every line as a bullet.

```markdown
**Understanding From Jira**
- Issue understood: <plain-English statement of the user-visible problem or requested feature>.
- Why it matters: <customer, workflow, release, data, or business impact stated in Jira/supplied evidence>.
- Requested outcome: <observable end state requested by Jira/UAC or explicitly marked proposed>.
- Lifecycle understood as: <Pre-Development UAC, Implementation Review, or Post-Fix Validation, with one short reason>.
- Evidence boundary: <live Jira, indexed Jira, supplied incident, contradictions, and material facts not yet verified>.

**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given <precondition/input> | When <single trigger/action> | Then <observable outcome> | Evidence: <underlying Jira, URL/chunk, DITA source, Figma node, attachment, or inspected code citation>.
- AC-02 [Proposed]: (Negative) Given <invalid/unsupported input or wrong state> | When <single trigger/action> | Then <exact observable rejection and unchanged state> | Evidence: <underlying source, never only a graph path ID>.
- AC-03 [Proposed]: (Integration) Given <evidence-backed adjacent workflow/API/config/output> | When <single trigger/action> | Then <observable coupled-system outcome> | Evidence: <underlying source>.

**Expected Behaviour**
- ...

**Scope From Git**
- ...

**Code Touched**
- ...

**Lines Changed**
- ...

**Test Scenarios**
- Incident recovery validation: Confirm target correlation and approved scope; capture pre-change inventory/backup, execute the safe cleanup, preserve unrelated state, retain audit evidence, verify queue/dashboard recovery, and prove rollback readiness.
- P0 [AC-01]: ...
- P1 [AC-02, AC-03]: ...

**Known Jira Bugs / Past Similar Tickets**
- ...

**Regression Areas**
- ...

**Automation Coverage & Gaps**
- AC-01 - Covered: `<absolute repo path>:<complete file path>:<test method>` using `<fixture/helper>` at `<branch>@<SHA>`; clone is `<clean/dirty, ahead/behind, fetch result>`.
- AC-02 - Partially covered: existing test directly proves <named clause of AC-02>; missing <specific clause/boundary/assertion>. Adjacent happy-path tests are reusable infrastructure, not partial coverage.
- AC-03 - Not covered: add/extend `<exact file/class/method>` in `<UI/API/integration layer>`; reuse `<client/helper/fixture>`, create state through `<deterministic setup/injection>`, poll `<endpoint/state>` with `<timeout source>`, assert `<terminal and output-integrity oracle>`, and clean up or roll back through `<mechanism>` under `<suite/tags>`.

**Open Questions**
- ...
```

## Performance AC Rule

- Do not copy a Performance AC by default. First complete the internal `aem-guides-performance-assessment-v1` manifest review.
- Only `required` adds the next contiguous `(Performance)` AC and a mapped load/stress/soak/scalability/concurrency/benchmark scenario. Its `Given` contains a numeric workload and its `Then` contains a numeric metric threshold with units from an approved SLA or controlled benchmark.
- `conditional` adds only a QA-impact Open Question for the missing workload/SLA/baseline. `not_required` adds nothing reader-facing. Never create a Performance Analysis section.

## Default Chat/UI Projection

- Keep the complete eleven-section body and any appendix in the `.md` record artifact.
- After `run_gates.py` passes, run `python scripts/render_compact_view.py <full-plan.md> --out <compact-view.md>`.
- Present only `Acceptance Criteria`, `Regression Areas`, `Past Jiras`, and `Open Questions`, in that order, unless the user explicitly asks to see another section or the complete record.
- The compact view is copied deterministically from the validated record; never rewrite, summarize, or regenerate its AC, regression, or open-question bullets.
- Before an automation-draft agent consumes the plan, run `python scripts/extract_acs.py <full-plan.md> --out <acceptance-criteria.json>`. A nonzero exit blocks handoff; the agent consumes that JSON rather than reparsing prose.

## Writing Style

- Write like a manual QA engineer: direct action, observable result, no implementation jargon unless needed.
- State the lifecycle stage in `Scope From Git`: `Pre-Development UAC`, `Implementation Review`, or `Post-Fix Validation`.
- Prefer “Verify that…” and “Confirm that…” over vague words like “check properly”.
- Keep bullets short enough to scan.
- Put only stage-relevant missing evidence in the section it affects: `Draft blocker: ...`.
- For pre-development, use `Not applicable — development has not started` for PR, changed-code, and line-count fields; never call these Draft blockers.
- In pre-development `Code Touched`, separate `No code changes yet` from `Current implementation implicated` findings obtained from product clones, logs, APIs, workflows, or exact error strings.
- Include setup, test data, role, config, platform, and environment matrix details inside the affected bullet instead of adding a new section.
- In `Automation Coverage & Gaps`, distinguish existing reusable automation from missing coverage and map both to AC IDs.
- Do not create extra sections.
- Do not use tables.
- Before returning, scan for mojibake (`â€`, `â‰`, `Ã`, `Â`, or `�`) and repair it; use ASCII punctuation if the client encoding is uncertain.
- Never abbreviate repository or file paths with `...`; include branch, commit SHA, sync state, and dirty/clean state.
- Keep destructive cleanup procedures out of Acceptance Criteria and place them under `Incident recovery validation` in Test Scenarios.
- Do not use approximate customer timing, topic count, or heap guidance as a hard oracle without an approved SLA or controlled benchmark.
- For concurrency recovery, assert successful publishing and output integrity separately from bounded terminal failure after retry exhaustion.
- Every AC uses the exact `AC-## [Confirmed|Proposed]: (<Sphere>) Given ... | When ... | Then ... | Evidence: <underlying source>.` field order and cites an underlying source. Graph path IDs stay internal traceability metadata.

## Stage Mapping

- **Pre-Development UAC**: Define proposed acceptance criteria, inspect current product and automation clones, list implicated current implementation, and make PR/line-count fields not applicable.
- **Implementation Review**: Inspect the real branch/commit/PR, list changed code and line counts, and map code branches to scenarios.
- **Post-Fix Validation**: Inspect the candidate fix/build and diff, then map acceptance, regression, environment, and fix-safety evidence to QA sign-off.

## Scenario Formula

Use:

`- P0 [AC-01, AC-02]: <action/test data/config/user role> -> <expected observable result>.`

Examples:

- `P0: Create a translation project from a map with postprocessing enabled -> project creation completes and generated assets remain under the expected DAM path.`
- `P1: Repeat the workflow for a child folder ignored for postprocessing -> child and successor folders are skipped consistently.`
- `P1: Repeat the API/UI flow on the required cloud/on-prem or old/new UI matrix -> behaviour stays consistent or follows the documented platform difference.`
- `P2: Refresh the UI after the operation -> status, toast, and persisted state remain consistent without duplicate actions.`

## Sample Pre-Development UAC

```markdown
**Understanding From Jira**
- Issue understood: The affected workflow does not satisfy the behavior requested in the issue.
- Why it matters: The failure blocks the documented customer or release workflow described in the supplied evidence.
- Requested outcome: The workflow reaches the Jira-defined observable outcome without the reported failure.
- Lifecycle understood as: `Pre-Development UAC` because development has not started.
- Evidence boundary: Jira or supplied issue facts were used; implementation and unresolved behavior remain separately identified.

**Acceptance Criteria**
- AC-01 [Proposed]: (Basic) Given the affected user role and a valid configuration | When the user runs the configured workflow | Then the workflow completes and reaches the documented observable outcome | Evidence: Jira UAC GUIDES-xxxxx.
- AC-02 [Proposed]: (Negative) Given invalid or unsupported input | When the user submits it to the same workflow | Then the operation is blocked with a clear specific error and no partial state is written | Evidence: Jira description GUIDES-xxxxx.

**Expected Behaviour**
- AEM Guides should follow the documented configuration rule returned by accepted RAG evidence.
- The UI should show the final status without requiring a manual refresh.
- Unknown from current evidence: exact behaviour for upgraded instances was not confirmed by Jira or RAG.

**Scope From Git**
- Lifecycle stage: `Pre-Development UAC`; development has not started.
- Issue source: <Jira, Dynamics/support case, customer escalation, pasted logs, or investigation notes>.
- Product clones: <absolute Starling/backend, xmleditor, or new editor path; branch; pre/post SHA; upstream/ahead/behind; pre/post dirty state; fetch/pull result; inspected ref; retained stash and restore command when applicable>.
- Automation clones: <absolute guides-ui-tests/dxml-it-tests path with the same guarded sync evidence>.
- PR discovery: Not applicable — development has not started.
- Figma/design evidence: <Figma MCP inspected link/frame, screenshot/design notes used, or not applicable>.

**Code Touched**
- No code changes yet — development has not started.
- Current implementation implicated: `<verified product-clone file/function/class/workflow>` affects <workflow/API/UI state>; evidence source is <exact repo match/log/API/config>.
- Current automation coverage: `<automation file/scenario/helper>` covers <existing path>; missing <negative/concurrency/recovery/config coverage> remains a gap.

**Lines Changed**
- Not applicable — development has not started.

**Test Scenarios**
- Setup and test data: create the Jira-required valid and invalid fixtures, affected role, configuration values, environment matrix, and UI/API/log oracle before execution.
- P0 [AC-01]: Action: run the primary Jira workflow with valid data. Expected: the operation reaches the AC-01 observable outcome and persists the expected UI/API state.
- P1 [AC-02]: Action: submit the evidence-backed invalid or boundary input. Expected: the exact AC-02 rejection appears and no partial state is saved.

**Known Jira Bugs / Past Similar Tickets**
- `GUIDES-xxxxx`: similar because <reason>; adds coverage for <area>.
- Historical search status: <Jira MCP/JQL result, user-provided incidents only, or unavailable>. Add a Draft blocker only when missing history leaves a material behaviour or regression decision unsupported.

**Regression Areas**
- Shared validation/API path used by <nearby workflow>.
- Role/permission combinations around <feature>.
- Config/version boundary around <setting/release>.
- Automation coverage gaps in `guides-ui-tests` or `dxml-it-tests` for <workflow>.

**Open Questions**
- Sign-off decision: confirm any Jira acceptance condition not represented by AC-01 or AC-02. QA impact: an added condition requires its own canonical AC, mapped scenario, and automation verdict before handoff.
- Permission/role: Confirm whether admin, author, reviewer, publisher, or restricted users must be covered.
- Configuration: Confirm whether XML Editor profile, AEM OSGi/DAM setting, or translation configuration changes are required for this Jira.
- Upgrade impact: For on-premise release/upgrade scope, confirm source/target versions, retained custom configs, changed defaults, manual post-upgrade steps, and backward-compatibility expectations.
- DITA/output: Confirm whether PDF, HTML5, Native PDF, DITA-OT, preset, or plugin-specific output must be validated.
```
