---
description: Generate an evidence-grounded AEM Guides test plan from a Jira key.
argument-hint: GUIDES-12345
---

You are running the registered AEM Guides Test Plan Generator workflow for authorized Adobe team members.

Input Jira key or arguments:

```text
$ARGUMENTS
```

Steps:

1. Extract exactly one Jira key from `$ARGUMENTS`, for example `GUIDES-12345`. If no key is present, ask for one and stop.
2. Load skill `aem-guides-test-scenario-generator` from `claude-skills/aem-guides-test-scenario-generator/SKILL.md`.
3. Use Adobe Jira MCP to fetch the complete ticket: summary, description, labels, components, issue type, priority, comments, attachments metadata, linked issues, and acceptance criteria fields.
4. Normalize ticket facts: current behaviour, expected behaviour/requested enhancement, business impact, customer context, acceptance criteria, and missing information.
5. Inspect local cloned repos before conclusions: `xmleditor`, `starling`, `guides-ui-tests`, `dxml-it-tests`. Cite file paths/line numbers for implementation and automation evidence.
6. Query the existing VM RAG/MCP only; do not create new RAG/vector DB/client code. Use `guides_test_plan_generator`, `find_similar_jira_issues`, and DITA/AEM Guides lookup tools as available.
7. If `test_plan_pipeline` is already registered, use it only as an existing deterministic evidence/scoring helper, not as a new app to build.
8. Generate evidence-grounded UACs and classify every conclusion with one of: ticket-confirmed, documentation-confirmed, specification-confirmed, implementation-derived, previous-JIRA-derived, assumption, human-clarification-required.
9. Score deterministically: ticket completeness, retrieval quality, evidence coverage, source consistency, UAC testability, requirement traceability.
10. Route by score: `>=85` -> `QE_REVIEW_READY`; `70-84` -> `QE_REVIEW_WITH_FLAGS`; `<70` -> ask focused human clarification questions before final plan.
11. Always require QE review; never auto-approve.
12. Write `docs/qa/test-plans/{JIRA-KEY}-test-plan.md`, validate with `scripts/validate_test_plan.py`, update registry.

Final answer: give the exact repo path to the saved `.md` file, routing status, score, and unresolved questions. Chat-only dumps are not the test plan.
