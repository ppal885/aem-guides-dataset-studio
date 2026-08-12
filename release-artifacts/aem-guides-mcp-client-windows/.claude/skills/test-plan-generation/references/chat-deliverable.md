# Chat Deliverable - Jira Understanding Card Plus Five Sections

Use this contract only after the complete eleven-section Markdown record passes `run_gates.py`.

## Required Presentation

- Render the compact projection with `python scripts/render_compact_view.py <full-plan.md> --out <compact-view.md>`.
- Show a Jira Understanding card above the plan. The card is not a section.
- `What I understood from Jira` combines the affected workflow, trigger, visible failure, and requested outcome from `Understanding From Jira`.
- `Why it matters` uses only evidence-backed customer or QA impact. If no impact is supplied, show exactly `Impact not specified; QA impact requires confirmation`.
- Show exactly five headings in this order:
  1. `Acceptance Criteria`
  2. `Test Scenarios`
  3. `Regression Areas`
  4. `Past Jiras`
  5. `Open Questions`
- Do not add Automation Coverage, Expected Behaviour, Code Touched, Performance Analysis, or another heading to compact chat/UI output.
- Keep those details in the full eleven-section Markdown artifact and show them only when the user requests the full plan or a named hidden section.
- Do not manually paraphrase the compact result. The renderer is the presentation authority.

## Fidelity

- Acceptance Criteria retain their exact validated one-line Given/When/Then/Evidence grammar.
- Test Scenarios retain setup/test-data bullets and P0/P1/P2 Action/Expected wording.
- Past Jiras includes only same-defect-class validated entries and uses the deterministic no-match line when none qualifies.
- Performance, when required, appears inside a `(Performance)` AC; it never creates another compact section.
