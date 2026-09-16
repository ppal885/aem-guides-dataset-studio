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
`shared_dimensions` / `differing_dimensions`, plus a required `merge_allowed`
flag (true only for `SAME_OUTCOME_VARIANT`). Textual similarity alone is never
the basis: same nouns do not mean the same outcome, and different wording does
not mean different outcomes.

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
`SAME_OUTCOME_VARIANT` decision with `merge_allowed: true` between the merged
members exists in `decisions[]`. A merge record (group) carries
`equivalence_id`, `coverage_refs`, `canonical_outcome` (internal grouping label
— never evidence), `question_refs`, `evidence_refs`, `research_refs`,
`variant_refs`, `source_lineage`, `priority`, `applicability`, and
`partial_members`. A merge preserves:

- all question IDs, all evidence IDs, and all research IDs of every merged
  decision (exact unions),
- all approved member variants (`variant_refs` must equal the members'
  variant labels — a variant is never omitted or invented),
- the source lineage (`source_lineage`),
- the highest member `priority`.

An `EXCLUDED` decision can never be merged; one decision survives into exactly
one AC (no coverage decision appears in two merges). Merge members must share
applicability, surface, configuration, and state — same-looking behavior under
a different engine, version, surface, or material configuration is never
merged (parity is never inferred); those differences belong to variants of one
decision. **Distinct behavior is never merged simply to reduce AC count.**

## Sufficiency boundary (S1 integration)

Only sufficiently established portions participate in a confirmed merge:
INSUFFICIENT coverage cannot merge into confirmed acceptance; CONFLICTED
coverage never merges; PARTIAL coverage participates only through its
established portion and must be listed in `partial_members`. A merge never
absorbs an unresolved acceptance dimension — a member grounded on an
ACCEPTANCE_TBD question fails the merge. (A SUFFICIENT new behavior and its
unresolved scope question stay separate.)

## Writer / Reviewer binding

The Writer receives equivalence-resolved groups and never re-runs equivalence
independently. With the C1 `writer_package`: an AC may reference a merge via
`equivalence_refs` and must then carry every merged variant; two ACs may never
cover different members of the same merge (one merged outcome becomes one AC).
The Reviewer detects duplicate ACs for a merged group, collapsed distinct
outcomes, lost TBD dimensions, omitted or invented variants, and lost source
lineage — and routes semantic failures upstream instead of repairing them.

Semantic sameness remains agentic reasoning recorded in these artifacts; the
structural gates validate bindings and safe transitions, not semantic truth.

## Backward compatibility

Absent `coverage_equivalence` block: clean pass.
