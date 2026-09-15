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
`evidence_ids[]`, `research_ids[]` (the admitted research behind the underlying
questions), `priority`, `coverage_class`, `contract_type`
(`POSITIVE`/`NEGATIVE`/`PRESERVATION`; the earlier `positive_or_negative` field
remains an alias), `surface`, `state_or_transition`, `configuration`,
`applicability`, `variants[]` (same-outcome variants, each with its own
`label` + `evidence_ids`), `reason`, `acceptance_impact`, and
`dimensions_considered[]` (present always; empty asserts no axis applies).

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
  `INVESTIGATION` (the established portion only); `ACCEPTANCE_TBD` →
  `INVESTIGATION` only (never converted into confirmed behavior);
  `INVESTIGATION_ONLY` → `INVESTIGATION` only; `NOT_APPLICABLE`, and
  `CONFLICTED` ground nothing; a `DUPLICATE` contributes linkage through its
  surviving question and never creates duplicate coverage.
- A planned-but-unresolved question cannot ground coverage; a question that was
  never planned cannot ground coverage.
- Required research cannot be skipped: a question whose mandated research is
  `PENDING`/`PARTIAL`/`NOT_FOUND`/`SOURCE_UNAVAILABLE`/`CONFLICTED` cannot
  ground an `ACCEPTANCE` decision. NOT_FOUND is not negative proof.
- `EXISTING_CONFIRMED` (documented-today) behavior must not be repackaged as a
  new `ACCEPTANCE` decision when linked via `behavior_ref` — it grounds
  regression/preservation coverage; a `NEW_REQUIREMENT` is never a
  `PRESERVATION` contract.
- An acceptance decision never rests on actual-result, observation, suspected
  root-cause, historical-ticket, or inference answer authority.
- `research_ids` must reference real Doc Researcher results and cover the
  underlying resolutions' research bindings.

## Writer handoff and review

- The Writer receives an explicit admitted package: `writer_handoff` is
  mandatory once decisions exist, contains no `EXCLUDED` decision, and
  represents every `P0` decision.
- The Writer must not invent acceptance behavior, promote `QE_REGRESSION` to
  `ACCEPTANCE`, convert `INVESTIGATION` into an AC, resolve `ACCEPTANCE_TBD`,
  add unapproved variants, or independently decide P0/P1. It may simplify
  wording, combine approved same-outcome variants, and preserve required
  product terminology.
- The Reviewer verifies via the optional `writer_package.acs` block: every AC
  maps to admitted `ACCEPTANCE` coverage ids; every admitted P0 acceptance
  decision is represented by an AC; no `QE_REGRESSION`/`INVESTIGATION`/
  `EXCLUDED` decision leaks into an AC; no unapproved variant appears. Semantic
  failures route upstream to the Coverage Reasoner — the Reviewer never
  silently repairs acceptance semantics.

## Backward compatibility

Absent `coverage_decisions` block: clean pass.
