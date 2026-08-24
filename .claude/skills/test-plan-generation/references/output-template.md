# Output Template

Use this file before writing the full validated record artifact.

## Required Shape

Use exactly these sections. Keep every line as a bullet.

After the complete record passes `run_gates.py` and produces a postable hash-bound receipt, render the compact UI with `render_compact_view.py`. Keep all Jira understanding, evidence analysis, code scope, detailed automation proof, and Open Questions in the eleven-section durable artifact. The compact UI contains exactly four headings, in this order: `Acceptance Criteria`, `Test Scenarios`, `Jira Tickets Worth Checking`, and `Automation Coverage`.

- Project each Acceptance Criterion into three short lines labelled `Starting point`, `Action`, and `Expected result`; do not show `Given`, `When`, `Then`, pipes, status, sphere, evidence, or analysis in the compact UI.
- Append every validated Regression Areas bullet to `Test Scenarios` as a `P3 [Regression]` scenario with an action and observable expected result.
- Show only the Jira key and title for validated same-mechanism tickets. Do not expose status, resolution, versions, RCA, similarity analysis, or retrieval notes in the compact UI.
- Show one main-feature automation verdict plus high-level feature-file/UI or integration/API guidance. Keep exact paths, methods, SHAs, code excerpts, and evidence analysis in the durable artifact.
- Do not add a Jira Understanding card, Open Questions, or any fifth heading.

```markdown
**Understanding From Jira**
- Issue understood: <plain-English statement of the user-visible problem or requested feature>.
- Why it matters: Customer context resolved from Jira: <canonical customer(s), sourced from explicit customer fields, labels, both, or not identified>; <workflow, release, data, or business impact>.
- Requested outcome: <observable end state requested by Jira/UAC or explicitly marked proposed>.
- Lifecycle understood as: <Pre-Development UAC, Implementation Review, or Post-Fix Validation, with one short reason>.
- Evidence boundary: Evidence mode: <full|degraded>; <available evidence sources; every unavailable source and resulting claim restriction; customer field/label conflicts, missing customer profiles, contradictions, and material facts not yet verified>.

**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given <precondition/input> | When <single trigger/action> | Then <observable outcome> | Evidence: <underlying Jira, URL/chunk, DITA source, Figma node, attachment, or inspected code citation>.
- AC-02 [Proposed]: (Negative) Given <invalid/unsupported input or wrong state> | When <single trigger/action> | Then <exact observable rejection and unchanged state> | Evidence: <underlying source, never only a graph path ID>.
- AC-03 [Proposed]: (Integration) Given <evidence-backed adjacent workflow/API/config/output> | When <single trigger/action> | Then <observable coupled-system outcome> | Evidence: <underlying source>.

**Expected Behaviour**
- <Evidence-backed intended behavior, or `Unknown from current evidence`>.

**Scope From Git**
- <Lifecycle, issue source, exact clone/revision/sync boundary, implementation evidence, automation evidence, and design evidence>.

**Code Touched**
- <Stage-correct changed-code statement or current implementation implicated, with exact evidence>.

**Lines Changed**
- <Stage-correct line counts/hunks, or `Not applicable - development has not started`>.

**Test Scenarios**
- Test data to prepare: <clear list of maps/topics/assets/references/preset/target path/roles/config/version/scale/failure fixture/expected snapshot/cleanup data>.
- Incident recovery validation: Confirm target correlation and approved scope; capture pre-change inventory/backup, execute the safe cleanup, preserve unrelated state, retain audit evidence, verify queue/dashboard recovery, and prove rollback readiness.
- P0 [AC-01]: Action: <simple tester action>. Expected: <visible or measurable result>.
- P1 [AC-02, AC-03]: Action: <simple tester action>. Expected: <visible or measurable result>.
- P1 [AC-##]: Customer-shaped fixture for <customer>, supported by <representative Jira keys>. Action: <simple action using prepared data>. Expected: <observable current-Jira result and cleanup result>.
- P2 [AC-##]: Customer-derived exploratory coverage for <customer>, supported by <concentration or representative Jira keys>. Action: <adjacent state, boundary, recovery, or integration check>. Expected: <observable no-regression result>.

**Known Jira Bugs / Past Similar Tickets**
- **Observed Customer Jira Profile: <customer> -** resolved from <Jira customer field/label>; profile <version>, approval <status>, <distinct-key count> Jira keys including <native Bug/Defect count> and <failure-like problem-report count/corpus percentage>, and <classification coverage>; current-Jira-relevant reported-problem taxonomy and concentrations are <types/areas/counts/percentages>; test-data, regression, and exploratory recommendations are <signals>; representative candidate keys are <keys>. Aggregate context only - validate direct Jira evidence before using any assertion. Repeat this bullet separately for every Jira customer; if missing, write `Observed Customer Jira Profile: <customer> - unavailable`.
- <Up to five same-mechanism Jira records with Similarity, mutable status/version facts, evidence, and scenario impact; or an explicit no-match result>.

**Regression Areas**
- Customer-derived regression focus: <customer>; <bug area, corpus count/percentage, representative keys>; overlaps <current Jira/code/shared workflow> and adds <exact regression check/fixture>. Aggregate risk guidance, not product-behaviour proof.
- Re-run <specific adjacent workflow/config/API/output> and assert <observable result>, because <shared path or changed mechanism> creates <specific regression risk>.

**Automation Coverage & Gaps**
- Main feature coverage: <Covered|Partially covered|Not covered|Unverified> - <one-sentence verdict based on direct automation evidence>.
- AC-01 - Covered: `<absolute repo path>:<complete file path>:<test method>` using `<fixture/helper>` at `<branch>@<SHA>`; clone is `<clean/dirty, ahead/behind, fetch result>`.
- AC-02 - Partially covered: existing test directly proves <named clause of AC-02>; missing <specific clause/boundary/assertion>. Adjacent happy-path tests are reusable infrastructure, not partial coverage.
- AC-03 - Not covered: add/extend `<exact file/class/method>` in `<UI/API/integration layer>`; reuse `<client/helper/fixture>`, create state through `<deterministic setup/injection>`, poll `<endpoint/state>` with `<timeout source>`, assert `<terminal and output-integrity oracle>`, and clean up or roll back through `<mechanism>` under `<suite/tags>`.

**Open Questions**
- OQ-01: <Decision the team must make>. QA impact: <what each plausible answer changes for scenarios, expected results, environment, or sign-off>.
```

## Performance AC Rule

- Do not copy a Performance AC by default. First complete the internal `aem-guides-performance-assessment-v1` manifest review.
- Only `required` adds the next contiguous `(Performance)` AC and a mapped load/stress/soak/scalability/concurrency/benchmark scenario. Its `Given` contains a numeric workload and its `Then` contains a numeric metric threshold with units or a source-backed comparative controlled-baseline target. A retained same-mechanism/shared-path historical performance contract forces this path and cannot remain only as a regression bullet.
- `conditional` adds only a QA-impact Open Question for the missing workload/SLA/baseline. `not_required` adds nothing reader-facing. Never create a Performance Analysis section.

## Operational Contract Projection

- Do not add a twelfth plan section. Project `operational_contract` decisions into existing ACs, `Test Scenarios`, `Regression Areas`, `Automation Coverage & Gaps`, and stable Open Questions.
- Use separate scenario bullets for the failure-point matrix; success, failure, cancellation, shutdown, and retry exhaustion; retry taxonomy/backoff/aggregate-log limit; partial-write recovery/idempotency; same/overlapping/unrelated concurrency; add/delete/rename/update snapshot mutations; queue isolation; observability/context fallback; safe recovery; and deterministic automation injection when applicable.
- Every unresolved dimension points to a real `OQ-##`; every excluded dimension has an evidence-backed reason. Never satisfy this contract with `bounded`, `does not run forever`, `failed or aborted`, or an implementation menu.

## Default Chat/UI Projection

- Keep the complete eleven-section body and any appendix in the `.md` record artifact.
- Run `python scripts/run_gates.py --plan <body> --combined <combined> --manifest <manifest> --receipt <receipt>`; only exit 0 plus `passed=true` permits rendering or handoff, and only `postable=true` permits an explicitly approved Jira write.
- After the gate passes, run `python scripts/render_compact_view.py <full-plan.md> --out <compact-view.md>`.
- Present only `Acceptance Criteria`, `Test Scenarios`, `Jira Tickets Worth Checking`, and `Automation Coverage`, in that order, unless the user explicitly asks to see another section or the complete record.
- Keep `Open Questions` in the validated full record and reveal it only on explicit request.
- Render Acceptance Criteria as `Starting point`, `Action`, and `Expected result` lines copied verbatim from the verified fields. Keep canonical Given/When/Then labels, status, sphere, and evidence only in the durable artifact and extracted JSON.
- Convert validated Regression Areas deterministically into `P3 [Regression]` scenarios under `Test Scenarios`; do not expose a separate Regression Areas heading.
- Render only Jira key and title for tickets worth checking; keep all similarity, status, resolution, version, RCA, and retrieval details hidden in the durable artifact.
- Render the declared main-feature automation verdict and high-level target layer; never expose raw source paths, SHAs, code excerpts, or internal analysis in the compact view.
- Before an automation-draft agent consumes the plan, run `python scripts/extract_acs.py <full-plan.md> --out <acceptance-criteria.json>`. A nonzero exit blocks handoff; the agent consumes that JSON rather than reparsing prose.
- Never use the compact projection as an input to extraction, automation, runtime adaptation, or Jira posting. An explicitly approved Jira write uses the strict plan plus the current postable receipt, keeps `[Proposed]` or `[Confirmed]`, and uses the same simple `Starting point` / `Action` / `Expected result` projection. Sphere, canonical labels, and local Evidence paths remain hidden in Jira.

## Writing Style

- Apply `plain-language-ac-writing.md` to every acceptance criterion before validation.
- Write like a manual QA engineer: direct action, observable result, no implementation jargon unless needed.
- State the lifecycle stage in `Scope From Git`: `Pre-Development UAC`, `Implementation Review`, or `Post-Fix Validation`.
- In the internal record, state the product contract directly through Given, When, and Then. In chat and Jira, show only the three simple presentation labels. Use Verify or Confirm only for tester actions in Test Scenarios.
- Keep bullets short enough to scan.
- Put only stage-relevant missing evidence in the section it affects: `Draft blocker: ...`.
- For pre-development, use `Not applicable — development has not started` for PR, changed-code, and line-count fields; never call these Draft blockers.
- In pre-development `Code Touched`, separate `No code changes yet` from `Current implementation implicated` findings obtained from product clones, logs, APIs, workflows, or exact error strings.
- Include setup, test data, role, config, platform, and environment matrix details inside the affected bullet instead of adding a new section.
- In `Automation Coverage & Gaps`, distinguish existing reusable automation from missing coverage and map both to AC IDs.
- Start `Automation Coverage & Gaps` with exactly one `Main feature coverage: Covered|Partially covered|Not covered|Unverified` verdict based on direct feature-file or integration-test evidence.
- Resolve customer context from Jira fields and labels without asking the user again; preserve multiple customers and keep each customer profile separate.
- Do not create extra sections.
- Do not use tables.
- Before returning, scan for mojibake (`â€`, `â‰`, `Ã`, `Â`, or `�`) and repair it; use ASCII punctuation if the client encoding is uncertain.
- Never abbreviate repository or file paths with `...`; include branch, commit SHA, sync state, and dirty/clean state.
- Keep destructive cleanup procedures out of Acceptance Criteria and place them under `Incident recovery validation` in Test Scenarios.
- Do not use approximate customer timing, topic count, or heap guidance as a hard oracle without an approved SLA or controlled benchmark.
- For concurrency recovery, assert successful publishing and output integrity separately from bounded terminal failure after retry exhaustion.
- Customer ticket frequencies describe what is frequently represented or affected in the Jira corpus; they do not prove feature usage or product behaviour.
- Every internal AC uses the exact `AC-## [Confirmed|Proposed]: (<Sphere>) Given ... | When ... | Then ... | Evidence: <underlying source>.` field order and cites an underlying source. Human-facing projections are never accepted as source. Graph path IDs stay internal traceability metadata.
- Reject unresolved markers, vague/non-finite bounds, implementation-choice menus, and combined terminal outcomes from ACs; move the decision to a stable `OQ-##` record with QA impact.

## Stage Mapping

- **Pre-Development UAC**: Define proposed acceptance criteria, inspect current product and automation clones, list implicated current implementation, and make PR/line-count fields not applicable.
- **Implementation Review**: Inspect the real branch/commit/PR, list changed code and line counts, and map code branches to scenarios.
- **Post-Fix Validation**: Inspect the candidate fix/build and diff, then map acceptance, regression, environment, and fix-safety evidence to QA sign-off.

## Scenario Formula

Use:

`- P0 [AC-01, AC-02]: Action: <what the tester does using prepared data>. Expected: <visible or measurable result>.`

When an operational contract references the scenario, use:

`- P0 [TS-01] [AC-01, AC-02]: Action: <deterministic trigger or injected condition>. Expected: <exact output and terminal-state oracle>.`

Examples:

- `P0 [AC-01]: Action: create a translation project from a map with postprocessing enabled. Expected: project creation completes and generated assets remain under the expected DAM path.`
- `P1 [AC-02]: Action: repeat the workflow for a child folder ignored for postprocessing. Expected: child and successor folders are skipped consistently.`
- `P1 [AC-03]: Action: repeat the API/UI flow on the required cloud/on-prem or old/new UI matrix. Expected: behavior stays consistent or follows the documented platform difference.`
- `P2 [AC-04]: Action: refresh the UI after the operation. Expected: status, toast, and persisted state remain consistent without duplicate actions.`

## Sample Pre-Development UAC

```markdown
**Understanding From Jira**
- Issue understood: The affected workflow does not satisfy the behavior requested in the issue.
- Why it matters: Customer context resolved from Jira: not identified; the failure blocks the documented customer or release workflow described in the supplied evidence.
- Requested outcome: The workflow reaches the Jira-defined observable outcome without the reported failure.
- Lifecycle understood as: `Pre-Development UAC` because development has not started.
- Evidence boundary: Evidence mode: full; Jira or supplied issue facts were used; implementation and unresolved behavior remain separately identified.

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
- Test data to prepare: create the Jira-required valid and invalid fixtures, affected role, configuration values, environment matrix, and UI/API/log oracle before execution.
- P0 [AC-01]: Action: run the primary Jira workflow with valid data. Expected: the operation reaches the AC-01 observable outcome and persists the expected UI/API state.
- P1 [AC-02]: Action: submit the evidence-backed invalid or boundary input. Expected: the exact AC-02 rejection appears and no partial state is saved.

**Known Jira Bugs / Past Similar Tickets**
- No same-mechanism Jira ticket was established from the validated evidence; area-only candidates were excluded.
- Historical search status: <Jira MCP/JQL exact-error search result plus workflow/mechanism search result, user-provided incidents only with those two intents unavailable, or both searches unavailable>. Add a Draft blocker only when missing history leaves a material behaviour or regression decision unsupported.

**Regression Areas**
- Re-run the shared validation/API path used by <nearby workflow> and assert its stored response remains correct, because the proposed change may alter common validation behavior.
- Re-run the supported role and permission combinations around <feature> and assert allowed and denied outcomes remain distinct, because authorization shares the affected entry point.
- Re-run the positive and negative config/version boundary around <setting/release> and assert the documented behavior remains stable across the required environment matrix.
- Re-run the nearest existing `guides-ui-tests` or `dxml-it-tests` workflow and its cleanup assertions, because reusable setup without the new oracle can otherwise hide a regression.

**Automation Coverage & Gaps**
- Main feature coverage: Unverified - exact automation repositories and symbols must be inspected before handoff.
- AC-01: Unverified - search the exact UI/API action, config key, and implementation symbol in every relevant automation clone; record the candidate layer, deterministic setup, oracle, timeout, and cleanup.
- AC-02: Unverified - search the exact rejection and unchanged-state oracle; adjacent happy-path coverage is reusable infrastructure only.

**Open Questions**
- OQ-01: Confirm any Jira acceptance condition not represented by AC-01 or AC-02. QA impact: an added condition requires its own canonical AC, mapped scenario, and automation verdict before handoff; no added condition leaves the current scope unchanged.
- OQ-02: Confirm which admin, author, reviewer, publisher, or restricted roles are in scope. QA impact: the answer defines the permission matrix and allowed/denied expected results.
- OQ-03: Confirm whether XML Editor profile, AEM OSGi/DAM setting, translation configuration, or upgrade matrix changes are required. QA impact: any required setting/version adds positive/negative configuration fixtures and upgrade regression coverage; none keeps the base environment only.
```

## Capability-eligibility & scope-alignment output (when those blocks are active)

These are NOT new top-level sections (the validated plan stays eleven sections). They are
projections woven into the existing sections and the chat view, shown only when the
`capability_eligibility` / `scope_conflict` manifest blocks are active.

- **Per-capability Acceptance Criteria.** When several actions share a surface, write a
  separate AC per capability with its own eligibility predicate (entity type / metadata /
  state / surface / permission / selection). Never one AC covering all buttons. If a
  capability's predicate is unproven, keep it `[Proposed]` or move it to Open Questions.
- **Implementation Verification (inside Test Scenarios).** Findings dispositioned
  `IMPLEMENTATION_ORACLE` / `DIAGNOSTIC_CHECK` go under an implementation-verification
  scenario bullet, never as a customer-facing AC. Every functional scenario must carry a
  PRIMARY_PRODUCT_ORACLE; "no exception" alone never passes it.
- **Secondary Findings (inside Test Scenarios or Open Questions).** A `SECONDARY_DEFECT`
  discovered during investigation is recorded as a separate finding/thread, never folded
  into the main acceptance contract. A reported-but-unaddressed second problem must be
  surfaced (SEPARATE_THREAD / OUT_OF_SCOPE / SEPARATE_DEFECT_CANDIDATE), not dropped.
- **Scope / Fix Alignment (inside Understanding From Jira and Open Questions).** Show this
  ONLY when a material discrepancy exists between reported Jira scope and current fix scope:
  - Reported Scope: <what the Jira/customer reported>
  - Current Fix Evidence: <what the PR/fix actually changes>
  - Alignment: FULL / PARTIAL / DIFFERENT / UNKNOWN
  - Unresolved: <the Open Question that surfaces the gap>
  A PARTIAL/DIFFERENT/UNKNOWN alignment MUST have a matching Open Question, or `run_gates`
  fails the plan.
