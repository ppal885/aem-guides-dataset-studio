# Reviewer-Request Coverage Gate (UACFIX-18)

Items a human reviewer explicitly asks to check — a Jira comment such as
"also check Map Preview / Download PDF / sorting / temp files" — and shared-consumer
surfaces placed in scope are **Acceptance Criteria with their own scenarios**, never
demoted to a P3 Regression bullet or a generic Open Question. This gate makes that
non-negotiable enforceable. See the SKILL.md rule "Reviewer-requested checks and
shared-consumer surfaces are ACCEPTANCE CRITERIA, not P3 regression."

## Activation (conservative)

The gate fires only when the manifest carries a non-empty `reviewer_requests` block
**or** an explicit `reviewer_comments` list whose text contains an imperative check
("also check…", "please verify…", "impact on…", "make sure…", "what about…"). It never
scans the plan's own Test Scenarios for verbs like "verify", so plans without reviewer
feedback pass untouched (backward-compatible).

## Manifest block

```
"reviewer_requests": [
  {
    "request_id": "RR-01",
    "source": "jira_comment",
    "reviewer": "<name>",
    "raw_text": "<exact reviewer ask>",
    "surface_or_behavior": "Map Preview index labels",
    "disposition": "COVERED_BY_AC" | "OPEN_QUESTION_UNRESOLVED_PATH" | "OUT_OF_SCOPE",
    "ac_refs": ["AC-13"],            // required for COVERED_BY_AC
    "open_question_ref": "OQ-02",    // required for OPEN_QUESTION_UNRESOLVED_PATH
    "reason": "..."                  // required for OUT_OF_SCOPE
  }
]
```

Optionally supply the reviewer feedback verbatim as `reviewer_comments` (a list of
strings or `{body}`/`{text}` objects) so the gate can confirm every imperative ask was
captured.

## Hard failures (prefix `REVIEWER-REQUEST GATE:`)

1. A reviewer-request signal is present but no `reviewer_requests` block exists.
2. An entry's `disposition` is not one of the three allowed values — in particular a
   reviewer ask can never be parked as a regression bullet.
3. `COVERED_BY_AC` with empty `ac_refs`, or `ac_refs` that are not present in the plan's
   Acceptance Criteria.
4. `OPEN_QUESTION_UNRESOLVED_PATH` with no `open_question_ref`, or one that is not a known
   Open Question (plan body or manifest `open_questions`). Use this disposition only when
   the code path is genuinely unresolved.
5. `OUT_OF_SCOPE` with no `reason`.
6. An imperative reviewer comment that is not captured by any `reviewer_requests` entry.

## Coordination

This gate enforces that reviewer-named checks become ACs. It complements — and does not
duplicate — `clarification_gate` (enumerate dimensions before authoring) and
`qe_completeness_coverage` (nothing checkable left parked in Open Questions/Regression).
