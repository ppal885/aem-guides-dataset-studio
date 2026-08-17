# Chat Deliverable - Concise Four-Section QA View

Use this contract only after the complete eleven-section Markdown record passes `run_gates.py`.

## Required Presentation

- Render the compact projection with `python scripts/render_compact_view.py <full-plan.md> --out <compact-view.md>`.
- Keep Jira analysis, evidence boundaries, code findings, and detailed reasoning in the full Markdown artifact. Do not expose an analysis card in the default UI.
- Show exactly four headings in this order:
  1. `Acceptance Criteria`
  2. `Test Scenarios`
  3. `Jira Tickets Worth Checking`
  4. `Automation Coverage`
- Do not add Understanding, Regression Areas, Expected Behaviour, Code Touched, Performance Analysis, Open Questions, or another heading to compact chat/UI output.
- Keep those details in the full eleven-section Markdown artifact and show them only when the user requests the full plan or a named hidden section.
- Keep `Open Questions` mandatory in the validated full record, but hide that section from the default compact UI.
- Do not manually paraphrase the compact result. The renderer is the presentation authority.

## Fidelity

- Acceptance Criteria show a straightforward `AC-##: Given | When | Then` product contract. Keep status, sphere, and underlying evidence in the validated full artifact and machine-readable AC JSON.
- Test Scenarios retain setup/test-data bullets and P0/P1/P2 Action/Expected wording. Focused regression checks are merged into this section as `P3 [Regression]` scenarios.
- Jira Tickets Worth Checking includes only validated same-mechanism/same-defect-class Jira keys and concise titles. Hide similarity reasons, status, resolution, versions, RCA, ownership, and corpus-analysis detail.
- Automation Coverage begins with `Main feature coverage: Covered|Partially covered|Not covered|Unverified`, then states at a high level whether to extend a feature-file/UI test or an integration/API test.
- Performance, when required, appears inside a `(Performance)` AC; it never creates another compact section.
