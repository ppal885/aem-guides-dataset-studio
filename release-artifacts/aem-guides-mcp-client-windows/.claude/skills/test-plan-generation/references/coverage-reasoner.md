# UAC Coverage Reasoner

A dedicated Coverage Reasoner decides coverage on top of resolved
Question-Based UAC evidence. **The Writer never decides coverage** — it
receives only accepted coverage decisions. Enforced by
`scripts/coverage_reasoner.py` over the manifest `coverage_decisions` block;
follows `references/question-based-reasoning.md` (planner/resolver) and
`references/question-research-routing.md` (research routing).

## Inputs

Authoritative requirements, resolved questions, research findings,
applicability, conflicts, attachment observations, existing behavior, new
behavior, and preservation requirements.

## Decision record (`coverage_decisions.items[]`)

One record per candidate behavior: `coverage_id`, `behavior`, `question_ids[]`,
`evidence_ids[]`, `priority`, `coverage_class`, `positive_or_negative`
(`POSITIVE`/`NEGATIVE`), `surface`, `state`, `configuration`, `applicability`,
`reason`, `acceptance_impact`, and `dimensions_considered[]` (present always;
empty asserts no axis applies).

## Priority and class

| priority | meaning | coverage_class |
|---|---|---|
| `P0` | required to prove the primary ticket contract and prevent the direct customer regression | `ACCEPTANCE` |
| `P1` | materially related regression behavior | `QE_REGRESSION` |
| `SUPPORTING` | supporting regression/investigation coverage | `QE_REGRESSION` or `INVESTIGATION` |
| `EXCLUDED` | explicitly excluded with a reason; never reaches the Writer | any |

**Do not promote generic test ideas**: every decision traces to at least one
resolved question or evidence id.

## Dimension axes (reasoned about when applicable)

`SINGLE_BULK`, `REFRESH_REVISIT`, `STATE_TRANSITIONS`, `NEGATIVE_CONTRACTS`,
`ALTERNATE_UI_PATHS`, `CONFIGURATION_BRANCHES`, `NEW_OLD_EDITOR`,
`AUTHOR_SOURCE`, `COLLECTIONS_EXPLORER_MAP_CONSOLE`, `CLOUD_65`,
`NATIVE_PDF_DITA_OT`, `PREPROCESSING_ON_OFF`, `SCALE`, `PRESERVATION`.

## Grounding rules (chain integrity)

A coverage decision may stand only on questions whose resolution and research
permit it:

- `ANSWERED` → any class; `PARTIALLY_ANSWERED` → `QE_REGRESSION` /
  `INVESTIGATION`; `ACCEPTANCE_TBD` → `INVESTIGATION` only;
  `INVESTIGATION_ONLY` → `INVESTIGATION` only; `NOT_APPLICABLE`, `DUPLICATE`,
  `CONFLICTED` → ground nothing.
- A planned-but-unresolved question cannot ground coverage; a question that was
  never planned cannot ground coverage.
- Required research cannot be skipped: a question whose mandated research is
  `PENDING`/`PARTIAL`/`NOT_FOUND`/`SOURCE_UNAVAILABLE`/`CONFLICTED` cannot
  ground an `ACCEPTANCE` decision. NOT_FOUND is not negative proof.
- `EXISTING_CONFIRMED` (documented-today) behavior must not be repackaged as a
  new `ACCEPTANCE` decision when linked via `behavior_ref` — it grounds
  regression/preservation coverage.

## Writer handoff and review

- The Writer receives only accepted (non-`EXCLUDED`) decisions. When
  `writer_handoff` is declared, it must contain no `EXCLUDED` decision and must
  represent every `P0` decision.
- The Reviewer verifies all P0 coverage is represented and that P1 has not
  expanded scope.

## Backward compatibility

Absent `coverage_decisions` block: clean pass.
