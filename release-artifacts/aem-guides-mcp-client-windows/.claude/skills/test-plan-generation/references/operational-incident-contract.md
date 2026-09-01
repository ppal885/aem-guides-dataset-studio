# Operational Incident and Job Contract

Use this contract for background jobs, scheduled or deployment-triggered work,
incident repair, migrations, asynchronous consumers, event listeners, queue workers,
and other long-running or restart-sensitive behavior. It is a general completeness
contract, not a ticket-specific checklist.

## Manifest block

The evidence manifest block is `operational_contract` with schema version
`aem-guides-operational-contract-v1`.

- Always provide the boolean `active` and a non-empty `reason`.
- Set `active: true` when issue, implementation, or behavior evidence contains an
  operational signal. Include every required dimension exactly once.
- Set `active: false` only when the feature is genuinely not operational, and explain
  why. Omit `dimensions` or use an empty list.
- A signal-bearing manifest cannot bypass the contract with `active: false`.

Example shape:

```json
{
  "operational_contract": {
    "schema_version": "aem-guides-operational-contract-v1",
    "active": true,
    "reason": "The change runs as a restart-sensitive background job.",
    "dimensions": [
      {
        "dimension": "TRIGGER_AND_DEPLOYMENT_SCOPE",
        "disposition": "COVERED_BY_AC",
        "ac_refs": ["AC-01"],
        "scenario_refs": ["TS-01"]
      },
      {
        "dimension": "DETERMINISTIC_AUTOMATION",
        "disposition": "COVERED_BY_SCENARIO",
        "scenario_refs": ["TS-09"]
      },
      {
        "dimension": "SHUTDOWN_TERMINAL_OUTCOME",
        "disposition": "OPEN_QUESTION",
        "open_question_refs": ["OQ-03"]
      },
      {
        "dimension": "QUEUE_ISOLATION",
        "disposition": "OUT_OF_SCOPE",
        "reason": "The approved change executes synchronously and creates no queue."
      }
    ]
  }
}
```

The example is abbreviated. An active block must include all required dimensions.

## Dispositions and references

- `COVERED_BY_AC` requires a non-empty `ac_refs` list. `scenario_refs` may also be
  supplied when a named scenario demonstrates the AC.
- `COVERED_BY_SCENARIO` requires a non-empty `scenario_refs` list. `ac_refs` may also
  be supplied when the scenario verifies named product behavior.
- `OPEN_QUESTION` requires a non-empty `open_question_refs` list. It must not be used
  as a substitute for an observable outcome that evidence already establishes.
- `OUT_OF_SCOPE` requires a concrete, non-empty `reason`; “not needed” is not enough.
- References must resolve to IDs actually present in the durable plan. The gate must
  pass the validator the complete known AC, Open Question, and scenario ID sets.
  Passing an empty set rejects every invented reference; omitting an index prevents
  referential integrity from being proved and also fails a reference-bearing entry.

## Required dimensions

- `TRIGGER_AND_DEPLOYMENT_SCOPE`: define who or what starts the work, whether it runs
  once, on every deployment/restart, on a schedule, or manually, and which repository,
  tenant, environment, or content scope it may touch.
- `FAILURE_POINTS_AND_MATRIX`: enumerate evidence-backed failure points and the
  expected continue/stop/skip/result behavior for each one. Do not collapse distinct
  failures into “fails gracefully.”
- `SUCCESS_TERMINAL_OUTCOME`: identify the exact terminal success state, persisted
  result, returned status, and completion signal.
- `FAILURE_TERMINAL_OUTCOME`: identify the exact terminal failure state and ensure a
  partial or exhausted run cannot be reported as success.
- `CANCELLATION_TERMINAL_OUTCOME`: separately define whether cancellation is allowed,
  when it takes effect, its visible state, and the state left behind.
- `SHUTDOWN_TERMINAL_OUTCOME`: separately define what happens on process, pod, or
  service shutdown and how restart observes, resumes, retries, or safely abandons it.
- `RETRY_POLICY`: define retryable failures, attempt limit, backoff source, exhaustion
  outcome, and duplicate-safety expectations.
- `DEFENSIVE_PROGRESS_BOUND`: define finite, measurable limits such as pages, items,
  elapsed time, repeated cursor/token count, or no-progress attempts. “Bounded” and
  “does not run forever” are not measurable contracts.
- `PARTIAL_WRITE_RECOVERY_IDEMPOTENCY`: define checkpoint/commit boundaries, partial
  output, rerun behavior, duplicate prevention, rollback or resume, and result repair.
- `CONCURRENCY_AND_SNAPSHOT_MUTATIONS`: define overlapping invocations and content
  created, changed, moved, or deleted while the run traverses its working snapshot.
- `QUEUE_ISOLATION`: define queue/topic ownership, concurrency/resource limits, and
  proof that this workload cannot starve unrelated jobs. Use `OUT_OF_SCOPE` with an
  evidence-backed reason when no queue exists.
- `OBSERVABILITY`: define correlated logs, metrics, progress, failure context, and a
  terminal signal sufficient for an operator or automated oracle to diagnose the run.
- `RECOVERY_SAFETY`: define safe incident recovery, validation, cleanup scope,
  rollback, and protection against broad or destructive repair actions.
- `DETERMINISTIC_AUTOMATION`: name scenarios that deterministically inject failures,
  retries, repeated cursors, cancellation, shutdown, partial writes, and concurrency
  where applicable, with exact terminal and output-integrity assertions.

## Validator API

Load `scripts/operational_contract.py` and call:

```python
problems = validate_operational_contract(
    manifest["operational_contract"],
    ac_ids={"AC-01", "AC-02"},
    open_question_ids={"OQ-03"},
    scenario_ids={"TS-01", "TS-09"},
)
```

For complete-manifest gating, call `validate_manifest(...)`. It also requires the
block when `likely_operational(...)` finds strong job/queue/retry/restart signals and
rejects an inactive block in the presence of those signals.

