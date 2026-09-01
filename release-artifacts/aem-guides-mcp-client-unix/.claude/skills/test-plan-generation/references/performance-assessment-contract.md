# Principal Performance QA Contract

## Purpose

Every ticket receives an internal performance-risk review. This review never creates a plan section, heading, or standalone regression bullet. It is stored only in the evidence manifest as `performance_assessment`.

The visible plan changes only when evidence supports performance testing:

- `required`: emit one or more canonical `(Performance)` Acceptance Criteria and mapped performance scenarios.
- `conditional`: emit no Performance AC because the pass/fail oracle is unresolved; add one targeted `Open Questions` bullet with QA impact.
- `not_required`: emit no Performance AC and no reader-facing filler.

Performance evidence can come from the current ticket or a retained historical ticket only when that ticket shares the exact mechanism or an inspected shared execution path. A generic ticket from the same component is area-only evidence and cannot trigger a Performance AC.

## Principal-Level Risk Review

Review all seven signal categories against Jira, attachments/logs, exact product documentation, same-mechanism Jira history, and inspected code:

- Data volume or cardinality growth.
- Concurrency or contention.
- Repetition or long duration.
- Latency, timeout, or throughput.
- CPU, memory, GC, or storage.
- Queue, backlog, or external dependency.
- Persistence cleanup or stale state.

Use `present`, `absent`, or `unknown` for every category and cite at least one underlying source for each finding. Customer anecdotes or approximate timing are signals, not pass/fail thresholds.

## Manifest Shape

`performance_assessment` contains:

- `schema_version`: exactly `aem-guides-performance-assessment-v1`.
- `decision`: `required`, `conditional`, or `not_required`.
- `risk_rating`: `high`, `medium`, or `low`.
- `signal_review`: exactly the seven category keys. Every value contains `status`, `finding`, and a non-empty `evidence_refs` list.
- `workload_model`: non-empty `operation`, `cardinality`, `concurrency`, `repetition`, and `duration`.
- `metrics`: controlled latency, throughput, error, resource, queue, storage, or reference-cardinality values.
- `oracle`: `status` (`quantified`, `unresolved`, or `not_applicable`), `source_ref`, and `thresholds`.
- `test_types`: controlled `load`, `stress`, `soak`, `scalability`, `concurrency`, or `benchmark` values.
- `performance_ac_ids`: exact visible Performance AC IDs.
- `historical_contracts`: evaluated historical performance contracts with Jira key, relationship, retained flag, mechanism, quantified workload, measurable oracle, and evidence references.
- `rationale`: the evidence-based decision explanation.

## Decision Rules

### Required

Use when at least one material signal is present and a source-backed, quantified workload and oracle are available.

- Risk is `high` or `medium`.
- Define operation, cardinality, concurrency, repetitions, and duration.
- Select relevant metrics and test types.
- Use approved SLA values, quantified controlled-baseline thresholds, or a source-backed comparative target.
- Add canonical Performance ACs whose `Given` contains a numeric workload and whose `Then` contains a measurable numeric or comparative oracle.
- Map every Performance AC to an explicit load, stress, soak, scalability, concurrency, or benchmark scenario.
- Also use `required` when a validated historical Jira supplies a quantified contract and inspected current-code or API evidence proves the same mechanism or shared execution path. A retained historical contract cannot remain a passive Regression Areas note.
- A source-backed comparative target against a controlled before-fix baseline is a valid benchmark oracle even when no absolute latency SLA exists. Preserve the source's exact metric and comparison operator; do not substitute an example value.

### Conditional

Use when a material signal is present or unknown but workload, environment, or pass/fail threshold is not approved.

- Do not invent a Performance AC.
- Keep the oracle `unresolved`.
- Add an `Open Questions` item that asks for the missing workload/SLA/baseline decision and states the QA impact.
- Reclassify as `required` after the missing evidence is supplied.

### Not Required

Use only when all seven reviewed signals are absent.

- Risk is `low`.
- Do not declare metrics, test types, thresholds, or Performance AC IDs.
- Keep the result internal.

## AC Quality

A Performance AC uses the same `aem-guides-ac-v1` grammar as every other AC:

`- AC-## [Confirmed|Proposed]: (Performance) Given <quantified workload> | When <single trigger> | Then <numeric or source-backed comparative metric oracle> | Evidence: <underlying source>.`

An acceptable workload contains the source-backed operation, cardinality, concurrency, repetition, duration, dataset, and environment needed for reproduction. An acceptable outcome contains an approved numeric SLA or a source-backed comparative metric and controlled baseline. Never copy an illustrative or historical number into a new plan.

Never use `large dataset`, `acceptable performance`, or `should be fast` as an oracle. If a threshold cannot be sourced, use `conditional` and ask the question instead.

## Historical Contract Applicability

- A historical performance issue is a retrieval candidate, not a production rule. Its key never activates a contract.
- Retain it only when inspected current code/API evidence proves the same mechanism or shared execution path, its workload and environment apply to the current target, and its original source text provides a quantified oracle.
- Record currentness, applicability, exact provenance, workload, baseline, metric, comparison, and environment. Any unresolved material field makes the decision `conditional` and requires an Open Question instead of a Performance AC.
- Feature-area similarity without shared-path proof is `area_only`; do not retain its workload or oracle.
- When retained, promote only source-backed values from the evidence record. Never use a value remembered from an example, customer anecdote, or regression fixture.

## Manifest Alignment

The contract is enforced by `scripts/performance_contract.py` and `scripts/run_gates.py`:

- `performance_ac_ids` exactly matches visible Performance AC IDs.
- A `required` decision fails when no Performance AC exists.
- A retained same-mechanism/shared-path historical contract fails unless the decision is `required`.
- A `conditional` or `not_required` decision fails when a Performance AC is emitted.
- A conditional decision fails without a performance-related Open Question that states QA impact.
- Required ACs fail when workload or outcome is not quantitative.
- Every Performance AC fails unless at least one mapped performance scenario exists.
- No additional output section is permitted.
