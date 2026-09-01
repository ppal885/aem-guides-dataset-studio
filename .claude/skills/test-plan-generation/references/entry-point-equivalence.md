# Product Entry-Point Equivalence (UACFIX-04)

A customer operation can be reached through several supported entry points (toolbar vs
context menu; Generate PDF vs Preview vs Download PDF; one backend API from several UI
surfaces). Discover them - but do NOT assume they are equivalent because the
user-visible intent looks similar.

> **SAME_USER_INTENT != SAME_IMPLEMENTATION.**

## Candidate fields (`entry_point_equivalence.candidates[]`)

`entry_point_id`, `product_action`, `domain`, `surface`, `trigger`, `input`, `output`,
`implementation_handler`, `shared_state`, `shared_processing_path`,
`customer_visible_result`, `applicability`, `evidence`, `equivalence_type`,
`disposition`, optional `open_question_ref`, `searched_sources`.

## Equivalence types

SAME_USER_INTENT, SAME_PRODUCT_ACTION (intent-level, NOT proof of shared code);
SAME_HANDLER, SAME_PROCESSING_PIPELINE, SAME_STATE_MUTATION, SAME_FINAL_OUTPUT
(shared-path, evidence-backed); DIFFERENT_IMPLEMENTATION; UNKNOWN_RELATIONSHIP.

## Flow

discovered entry point -> shared-path investigation -> applicability -> Candidate
Ledger -> scope gate -> AC / SHARED_REGRESSION / OPEN_QUESTION / REJECTED /
REFERENCE_ONLY.

## Rules the gate enforces (`scripts/entry_point_equivalence.py`)

- **Intent-level or unknown equivalence cannot enter AC/SHARED_REGRESSION coverage** -
  a shared handler / pipeline / state / output must be evidenced first.
- **A shared-path equivalence promoted to coverage needs `shared_processing_path` or
  `implementation_handler` evidence** of the shared code path.
- **DIFFERENT_IMPLEMENTATION must not become shared regression/AC** - use REFERENCE_ONLY
  or REJECTED.
- **Only unresolved MATERIAL relationships become an Open Question**, and only after
  `searched_sources` (code/docs/tests) are recorded - do not ask the Human before
  searching.

This gate plugs into the scope gate (`scope_applicability`) and the human-feedback
learner's ENTRY_POINT_PATTERN. Backward-compatible: absent block is a clean pass.
