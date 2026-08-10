# Output Template

Use this file to create the full validated record artifact.

## Full Record Shape

Use exactly these sections and keep section content as Markdown bullets.

```markdown
**Understanding From Jira**
- Issue understood: <plain-English issue>.
- Why it matters: <customer/workflow/release impact>.
- Requested outcome: <observable end state>.
- Lifecycle understood as: <Pre-Development UAC, Implementation Review, or Post-Fix Validation>.
- Evidence boundary: <sources used, contradictions, and material gaps>.

**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given <precondition/input> | When <single trigger/action> | Then <observable outcome> | Evidence: <underlying source>.
- AC-02 [Proposed]: (Negative) Given <invalid input or wrong state> | When <single trigger/action> | Then <observable rejection and unchanged state> | Evidence: <underlying source>.
- AC-03 [Proposed]: (Integration) Given <evidence-backed coupled workflow> | When <single trigger/action> | Then <observable coupled-system outcome> | Evidence: <underlying source>.

**Expected Behaviour**
- ...

**Scope From Git**
- ...

**Code Touched**
- ...

**Lines Changed**
- ...

**Test Scenarios**
- Setup and test data: <fixtures, roles, configs, environments, and oracles>.
- P0 [AC-01]: Action: <tester action>. Expected: <observable result>.
- P1 [AC-02, AC-03]: Action: <tester action>. Expected: <observable result>.

**Known Jira Bugs / Past Similar Tickets**
- GUIDES-xxxxx - <same-mechanism match, status, lesson, and scenario impact>.

**Regression Areas**
- <specific workflow/config/API/data shape to retest and why it is at risk>.

**Automation Coverage & Gaps**
- AC-01 - <Covered|Partially covered|Not covered|Not suitable for automation>: <evidence or exact gap recipe>.

**Open Questions**
- <decision>. QA impact: <what each answer changes for tests or sign-off>.
```

## Performance AC Rule

- Complete `aem-guides-performance-assessment-v1` internally. Only `required` emits a quantified `(Performance)` AC and mapped performance scenario; `conditional` emits a QA-impact Open Question; `not_required` emits nothing reader-facing.
- Never add a Performance Analysis section or invent a workload/SLA/baseline threshold.

## Canonical AC Contract

- Schema version is `aem-guides-ac-v1`.
- IDs are unique and contiguous from `AC-01`.
- Status is exactly `Confirmed` or `Proposed`.
- Sphere is exactly `Basic`, `Negative`, `Integration`, or `Performance`.
- Field order is exactly `Given | When | Then | Evidence`, on one line, ending with a period.
- Every AC cites an underlying source; graph path IDs alone are invalid.
- Run `python scripts/extract_acs.py <full-plan.md> --out <acceptance-criteria.json>` before automation handoff. A nonzero exit blocks handoff.

## Default Chat/UI Projection

- Keep the full record in the `.md` artifact.
- Run `python scripts/render_compact_view.py <full-plan.md> --out <compact-view.md>`.
- Show only `Acceptance Criteria`, `Regression Areas`, `Past Jiras`, and `Open Questions`, in that order.
- Show the full record or a hidden section only after the user explicitly requests it.
- Never manually paraphrase the projected AC, regression, or open-question bullets.
