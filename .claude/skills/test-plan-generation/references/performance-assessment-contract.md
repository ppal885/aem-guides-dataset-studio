# Principal Performance QA Contract

## Purpose

Every ticket receives an internal performance-risk review. This review never creates a plan section, heading, or standalone regression bullet. It is stored only in the evidence manifest as `performance_assessment`.

The visible plan changes only when the evidence supports performance testing:

- `required`: emit one or more canonical `(Performance)` Acceptance Criteria and mapped performance scenarios.
- `conditional`: emit no Performance AC because the pass/fail oracle is unresolved; add one targeted `Open Questions` bullet with QA impact.
- `not_required`: emit no Performance AC and no reader-facing â€œnot requiredâ€ note.

## Principal-Level Risk Review

Review all seven signal categories against Jira, attachments/logs, exact product documentation, same-mechanism Jira history, and inspected code:

- Data volume or cardinality growth: large maps, topics, assets, languages, outputs, references, rows, versions, or unbounded metadata.
- Concurrency or contention: simultaneous users, jobs, publishing runs, shared paths, locks, retries, or queue competition.
- Repetition or long duration: repeated operations, cumulative degradation, leaks, soak behavior, or long-running jobs.
- Latency, timeout, or throughput: slow requests, timeout errors, queue delay, processing rate, or explicit SLA symptoms.
- CPU, memory, GC, or storage: heap pressure, large multi-value properties, repository/storage growth, GC pauses, or pod/resource changes.
- Queue, backlog, or external dependency: asynchronous workers, third-party APIs, network/storage latency, or backlog accumulation.
- Persistence cleanup or stale state: orphan references, undeleted metadata, index growth, repeated scans, or data that grows after lifecycle operations.

Use `present`, `absent`, or `unknown` for every category and cite at least one underlying source for each finding. Customer anecdotes or approximate timing are signals, not pass/fail thresholds.

## Decision Rules

## Manifest Shape

`performance_assessment` contains:

- `schema_version`: exactly `aem-guides-performance-assessment-v1`.
- `decision`: `required`, `conditional`, or `not_required`.
- `risk_rating`: `high`, `medium`, or `low`.
- `signal_review`: exactly the seven category keys above. Every value contains `status`, `finding`, and a non-empty `evidence_refs` list.
- `workload_model`: non-empty `operation`, `cardinality`, `concurrency`, `repetition`, and `duration`.
- `metrics`: controlled values from latency percentiles, throughput, error/timeout rate, CPU, memory/heap/GC, queue/backlog, storage growth, and reference cardinality.
- `oracle`: `status` (`quantified`, `unresolved`, or `not_applicable`), `source_ref`, and `thresholds`.
- `test_types`: controlled `load`, `stress`, `soak`, `scalability`, `concurrency`, or `benchmark` values.
- `performance_ac_ids`: exact visible Performance AC IDs.
- `rationale`: the evidence-based decision explanation.

### Required

Use only when at least one material signal is present and a source-backed, quantified workload and oracle are available.

- Risk is `high` or `medium`.
- Define operation, cardinality, concurrency, repetitions, and duration.
- Select relevant metrics and test types.
- Use approved SLA values or quantified controlled-baseline thresholds.
- Add canonical Performance ACs whose `Given` contains a numeric workload and whose `Then` contains a numeric metric threshold with units.
- Map each Performance AC to a load, stress, soak, scalability, concurrency, or benchmark scenario.

### Conditional

Use when a material signal is present or unknown but workload, environment, or pass/fail threshold is not approved.

- Do not invent a Performance AC.
- Keep the oracle `unresolved`.
- Add an `Open Questions` item that asks for the missing workload/SLA/baseline decision and states the QA impact.
- Reclassify as `required` only after the missing evidence is supplied.

### Not Required

Use only when all seven reviewed signals are absent.

- Risk is `low`.
- Do not declare metrics, test types, thresholds, or Performance AC IDs.
- Keep the result internal; do not add visible filler saying performance is not required.

## AC Quality

A Performance AC uses the same `aem-guides-ac-v1` grammar as every other AC:

`- AC-## [Confirmed|Proposed]: (Performance) Given <quantified workload> | When <single trigger> | Then <numeric metric threshold with units> | Evidence: <underlying source>.`

Examples of acceptable workload inputs include `10,000 topics`, `20 concurrent users`, `50 publishing jobs`, or `100 iterations`. Examples of measurable results include `p95 <= 2000 ms`, `throughput >= 25 jobs/minute`, `timeout rate = 0%`, or `heap growth <= 200 MB`.

Never use â€œlarge dataset,â€ â€œacceptable performance,â€ â€œshould be fast,â€ or an approximate customer observation as the oracle. If a threshold cannot be sourced, use `conditional` and ask the question instead.

## Manifest Alignment

The manifest contract is enforced by `scripts/performance_contract.py` and `scripts/run_gates.py`:

- `performance_ac_ids` exactly matches visible Performance AC IDs.
- A `required` decision fails when no Performance AC exists.
- A `conditional` or `not_required` decision fails when a Performance AC is emitted.
- A conditional decision fails without a performance-related Open Question that states QA impact.
- Required ACs fail when workload or outcome is not quantitative.
- No additional output section is permitted.
