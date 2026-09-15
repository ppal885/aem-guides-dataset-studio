# Evidence Sufficiency

"Evidence exists" is not "evidence is sufficient to support this answer or
coverage." Evaluated at **both** the resolved-question level and the
coverage-decision level in the manifest `evidence_sufficiency` block, enforced
by `scripts/evidence_sufficiency.py`. Integrates the R1 research state and the
Q1 dispositions; sits between Question Resolution and the Coverage Reasoner.

## Question assessment (`question_assessments[]`)

Per material resolved question: `question_id`, `sufficiency_status`
(`SUFFICIENT` / `PARTIAL` / `INSUFFICIENT` / `CONFLICTED`), the eight
evaluation `dimensions` notes, the structured sub-states:

- `authority_status`: `ESTABLISHING` / `NON_ESTABLISHING` — one applicable
  authoritative source may be sufficient; volume alone is not.
- `research_completion`: `NOT_REQUIRED` / `PENDING` / `COMPLETED` / `PARTIAL` /
  `NOT_FOUND` / `SOURCE_UNAVAILABLE` / `CONFLICTED` — must match the mandatory
  research state.
- `applicability_status`: `APPLICABLE` / `WRONG_APPLICABILITY` / `UNCLEAR`.
- `currentness_status`: `CURRENT` / `STALE` / `UNKNOWN`.
- `contradiction_status`: `NONE` / `CONFLICTING`.

plus claim-level `supported_claims[]` / `unsupported_claims[]`,
`limitations[]`, bound `evidence_ids[]` / `research_ids[]`, and
`decision_reason` (required).

## Rules

- `SUFFICIENT` requires ESTABLISHING authority, at least one supported claim,
  confirmed applicability, and completed research. `PARTIAL` research allows it
  only with a demonstrably `immaterial_limitation`; wrong-applicability or
  stale evidence needs explicit `compatibility_evidence_ids`.
- `PARTIAL` names the established portion and the unsupported claims; it is
  never silently upgraded.
- `INSUFFICIENT` never establishes the opposite behavior.
- `CONFLICTED` retains the competing claims; equal-authority conflicts are not
  settled by convenience or confidence.
- Evidence binds to the question's own pool (research evidence, answer
  sources, admitted doc research, triggering evidence) — no claim bleed;
  `research_ids` must cite admitted Doc Researcher results; a question revision
  invalidates a stale assessment.

## Coverage assessment (`coverage_assessments[]`)

Per coverage decision: `coverage_ref`, `sufficiency_status`,
`sufficiency_reason`, and lineage bindings (`question_refs`, `evidence_ids`,
`research_ids`) that must match the coverage decision exactly.

- Computed from the underlying questions: any CONFLICTED underneath forces
  CONFLICTED; any INSUFFICIENT/PARTIAL underneath caps below SUFFICIENT.
- `ACCEPTANCE` class requires SUFFICIENT at P0/P1 unless explicitly
  `represented_as_acceptance_tbd`; INSUFFICIENT never generates acceptance
  coverage; CONFLICTED never silently generates an AC; cross-product coverage
  is not SUFFICIENT merely because each control exists.
- Writer handoff: every admitted decision is assessed; INSUFFICIENT/CONFLICTED
  never reach the Writer; `ACCEPTANCE` in the handoff requires SUFFICIENT or
  the explicit TBD representation; PARTIAL names the usable portion.
- Reviewer (with the C1 `writer_package`): no AC on INSUFFICIENT/CONFLICTED
  evidence; a PARTIAL coverage's unestablished portion never appears as
  complete.

## Backward compatibility

Absent `evidence_sufficiency` block: clean pass.
