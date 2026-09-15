# Semantic Coverage / AC Equivalence

After the Coverage Reasoner emits coverage decisions, semantic equivalence
decides which decisions describe the same outcome and may share one AC —
**before** the Writer authors anything. Enforced by
`scripts/coverage_equivalence.py` over the manifest `coverage_equivalence`
block; follows `references/coverage-reasoner.md`.

The primary comparison happens on **coverage decisions**, not merely Writer
prose: each equivalence decision compares two `coverage_id`s across structured
dimensions — `COVERAGE_IDS`, `QUESTION_IDS`, `EXPECTED_OUTCOME`,
`STATE_TRANSITION`, `SCOPE`, `CONFIGURATION`, `APPLICABILITY` — declared as
`shared_dimensions` / `differing_dimensions`. Textual similarity alone is never
the basis.

## Classifications (`decisions[]`)

- `SAME_OUTCOME_VARIANT` — the same expected outcome observed through variant
  phrasing or polarity. Example: "the review state remains after refresh" and
  "refresh does not return the state to the previous one". Requires
  `EXPECTED_OUTCOME` in `shared_dimensions`. The Writer should normally create
  one AC.
- `DISTINCT_OUTCOME` — different expected outcomes. Example: "the file remains
  in its review state" vs "the project becomes Completed". Requires
  `EXPECTED_OUTCOME` in `differing_dimensions`. Never merge.
- `DEPENDENT_OUTCOME` — one outcome depends on the other. Requires
  `EXPECTED_OUTCOME` differing plus `dependency` naming the direction. Keep
  separate, ordered ACs.
- `CONFLICT` — the same outcome asserted contradictorily. Requires
  `EXPECTED_OUTCOME` shared plus a `conflict_summary`. Never merge; the
  conflict stays visible for the Reviewer.

## Merging (`merges[]`)

Allowed **only** for `SAME_OUTCOME_VARIANT`, and only when a
`SAME_OUTCOME_VARIANT` decision between the merged members exists in
`decisions[]`. A merge preserves:

- all question IDs of every merged decision,
- all evidence IDs of every merged decision,
- all applicable variants (`variants`),
- the source lineage (`source_lineage`),
- the highest member `priority`.

An `EXCLUDED` decision can never be merged, and one decision survives into
exactly one AC (no coverage decision appears in two merges). **Distinct
behavior is never merged simply to reduce AC count.**

## Backward compatibility

Absent `coverage_equivalence` block: clean pass.
