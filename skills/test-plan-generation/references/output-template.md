# Output Template

Use this file before writing the final user-facing plan.

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
- AC-01 [Confirmed]: (Basic) Given <precondition/input> | When <trigger> | Then <observable outcome>.
- AC-02 [Proposed]: (Negative) Given <invalid/unsupported input or wrong state> | When <trigger> | Then <blocked with the exact error contract, no partial state>.
- AC-03 [Proposed]: (Integration) Given <adjacent workflow/API/config/output in scope> | When <trigger> | Then <coupled system behaves consistently>.
- AC-04 [Proposed]: (Performance) Given <bulk/large/concurrent evidence-backed scale> | When <trigger> | Then <no regression vs baseline / meets approved SLA, no errors or timeouts>.
(Format: `(<Sphere>) Given | When | Then` — Sphere is one of Basic, Negative, Integration, Performance. Include Integration/Performance ONLY when the evidence shows that dimension; do not manufacture empty spheres. No embedded Scope/Oracle fields — put scope boundary and verification oracle in the mapped Test Scenarios.)

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
- P2 [AC-04]: ...

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
- Windows paths that contain spaces (e.g. `C:\api automation\`, `C:\UI TEST\`) MUST be wrapped in backtick characters as a single unit; an unquoted path with spaces tokenizes on whitespace and the second token fails the absolute-path check.
- Keep destructive cleanup procedures out of Acceptance Criteria and place them under `Incident recovery validation` in Test Scenarios.
- In `Automation Coverage & Gaps`, mark ACs that require hardware fault injection, JCR write-fault injection, or OS-level tooling unavailable in the IT framework as "Not suitable for automation: manual test; reason: …" — NOT "Not covered". The seven-term recipe (layer/setup/poll/timeout/assert/cleanup/tag) applies only to "Not covered" bullets, not to "Not suitable for automation" bullets.
- The `Known Jira Bugs / Past Similar Tickets` historical search status sentence MUST contain the three literal strings `jql`, `error`, and `workflow` (case-insensitive) somewhere in that section — e.g. "JQL intents: (1) … (error pattern); (2) … (workflow regression)."
- In `Code Touched` and `Automation Coverage & Gaps`, do NOT name a JCR property, method, or constant symbol in a "does NOT assert" or "not found" clause — the evidence verifier checks for the named symbol in the cited file regardless of negation. Instead write "has no post-delete property validation" or "covers the SAVE path only; no delete-path assertion" without naming the specific symbol.
- Do not use approximate customer timing, topic count, or heap guidance as a hard oracle without an approved SLA or controlled benchmark.
- For concurrency recovery, assert successful publishing and output integrity separately from bounded terminal failure after retry exhaustion.

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
- AC-01 [Proposed]: Given the affected user role and a valid configuration | When the user runs the configured workflow | Then the workflow completes and reaches the documented observable outcome.
- AC-02 [Proposed]: Given invalid or unsupported input | When the user submits it to the same workflow | Then the operation is blocked with a clear, specific error and no partial state is written.
- Draft blocker: Jira acceptance criteria are incomplete; confirm final sign-off conditions.

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
- P0: Run the primary Jira workflow with valid data -> operation succeeds and expected UI/API state is persisted.
- P0: Run the workflow with the Jira failure condition -> previous failure does not reproduce.
- P1: Use invalid or boundary input -> user sees a clear error and no partial state is saved.
- P1: Follow the Figma-observed alternate UI state when applicable -> visible state, copy, and recovery action match the intended flow.
- P1: Use the Jira-required test fixture, role, config, and platform matrix -> expected behaviour is proven without relying on default setup assumptions.
- P1: Repeat after browser refresh/session reload -> state remains consistent.
- P2: Verify nearby workflow that shares the touched component -> no regression in existing behaviour.

**Known Jira Bugs / Past Similar Tickets**
- `GUIDES-xxxxx`: similar because <reason>; adds coverage for <area>.
- Historical search status: <Jira MCP/JQL result, user-provided incidents only, or unavailable>. Add a Draft blocker only when missing history leaves a material behaviour or regression decision unsupported.

**Regression Areas**
- Shared validation/API path used by <nearby workflow>.
- Role/permission combinations around <feature>.
- Config/version boundary around <setting/release>.
- Automation coverage gaps in `guides-ui-tests` or `dxml-it-tests` for <workflow>.

**Open Questions**
- Permission/role: Confirm whether admin, author, reviewer, publisher, or restricted users must be covered.
- Configuration: Confirm whether XML Editor profile, AEM OSGi/DAM setting, or translation configuration changes are required for this Jira.
- Upgrade impact: For on-premise release/upgrade scope, confirm source/target versions, retained custom configs, changed defaults, manual post-upgrade steps, and backward-compatibility expectations.
- DITA/output: Confirm whether PDF, HTML5, Native PDF, DITA-OT, preset, or plugin-specific output must be validated.
```
