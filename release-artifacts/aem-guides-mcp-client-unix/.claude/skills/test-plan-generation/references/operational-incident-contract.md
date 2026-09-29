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

## Operational Incident And Recovery UAC Rules

Moved verbatim from SKILL.md on 2026-09-30 when SKILL.md was consolidated. The rules are unchanged.

- Use these rules for Dynamics/support incidents, production escalations, stuck jobs, queue blockage, workflow failures, cleanup requests, performance degradation, concurrency failures, and customer-restoration plans.
- Populate `operational_contract` schema `aem-guides-operational-contract-v1`. Strong job/queue/retry/restart/partial-write signals require `active=true`; `active=false` cannot bypass detected signals. Disposition every dimension to real AC, stable `TS-##` scenario, stable `OQ-##`, or a concrete out-of-scope reason.
- Separate immediate remediation from permanent product behavior: backend cleanup, service restoration, workflow/config correction, code safeguard, resource change, and automation must each have explicit in-scope or out-of-scope status.
- Do not turn a destructive operational procedure into a product acceptance criterion. Node deletion, workflow termination, pod restart, manual queue repair, and similar one-time engineering actions belong under `Test Scenarios` as an `Incident recovery validation` bullet; acceptance criteria may state only the observable restoration or permanent product contract.
- For mixed-lifecycle incidents, distinguish `Incident recovery validation` from the pre-development product UAC. A closed incident or successful cleanup does not confirm that a proposed concurrency, retry, cancellation, queue, or status-consistency safeguard has been implemented.
- Convert the end goal into proposed acceptance criteria, but keep unapproved engineering choices visible as open questions rather than presenting them as decided UAC.
- Define the exact affected output type, workflow, environment/build, target paths, job IDs/UUIDs, queue states, customer-like fixture size, and normal-versus-failure timing baseline.
- Require terminal-state contracts for success, failure, cancel, retry exhaustion, and recovery; define the maximum allowed duration for Waiting, Executing, Post Publishing, cancellation requested, or equivalent states.
- Enumerate failure points across acquisition, query construction/execution, result iteration, item mutation/delete, save/commit, refresh/cleanup, and result reporting when those phases exist. Define retryable versus terminal categories, maximum attempts, delay/backoff source, short-circuit rule, exhausted outcome, and aggregate logging bound across all attempts.
- Keep scheduler/deployment trigger, queue-level retry, and an in-run loop as distinct recurrence sources. Cover every caller/producer path, environment/build, individual-item action, and bulk/profile action that evidence places in scope.
- Define concurrency behavior for same map, same preset, same destination, overlapping destinations, and unrelated destinations: serialize, lock, retry, fail fast, or isolate.
- Define snapshot behavior for source additions, deletions, renames, and updates during paging/traversal; specify the observable no-skip/no-duplicate/output-integrity oracle without prescribing a cursor implementation unless accepted UAC does.
- Define partial-write behavior: rollback, reuse, overwrite, cleanup, idempotent retry, duplicate prevention, orphan prevention, and preservation of previously valid output.
- Define queue isolation and fairness: one failed job must not indefinitely block unrelated jobs, and recovery must specify whether successors auto-resume or require manual restart.
- Define cleanup safety: exact nodes/workflows targeted, correlation evidence, backup, approval, audit trail, unrelated-state preservation, rollback, and post-cleanup verification.
- Define restart and failover behavior for author pod restart, workflow restart, deployment, timeout, network interruption, and repeated cancellation.
- Define performance and resource acceptance separately: completion SLA, dataset scale, heap/pod limits, indexing state, CPU/memory evidence, and criteria for deciding whether a resource increase is required.
- Never convert an observed customer duration, approximate normal runtime, topic count, heap recommendation, or support anecdote into a hard pass/fail oracle unless Jira/UAC, an approved SLA, or a controlled benchmark defines the dataset, environment, repetitions, percentile, and threshold. Otherwise treat it as a measured baseline or an open question.
- Define observability: required correlation IDs, job/output/workflow UUIDs, target path, stage timings, retry count, terminal reason, actionable errors, and sensitive-data redaction.
- Provide an explicit fallback value when failure happens before path/page/item context exists, and bound both per-attempt and aggregate cross-retry log volume.
- Verify the final generated output, not only DITA-OT/build success or UI status: page/file count, links, assets, metadata, navigation, history nodes, workflow completion, and absence of partial/orphan state as applicable.
- For evidence-backed publishing/export artifacts, populate every oracle in `aem-guides-generated-output-contract-v2`: artifact existence, content/title/hierarchy/order/navigation/links/metadata/repository state/output path/locale, duplicates, orphans, stale output, unchanged-content rewrites, activation state, status-versus-real-output, and conditional delivery availability. Record primary-content versus diagnostic inventory and root/hierarchy/relative-path rules. Require the real download surface and cover `DELIVERY_AVAILABLE` only when `delivery_in_scope=true`; mark it not applicable when false or expose an Open Question when unresolved. An archive that contains only logs or merely exists is not a sufficient product oracle.
- Inspect product clones using exact stack-trace classes, workflow model names, JCR paths, APIs, config keys, and error strings; inspect automation clones for timeout, polling, cancel, cleanup, concurrency, performance, and recovery gaps.
- Keep destructive production reproduction out of scope unless explicitly approved; prefer a production-equivalent clone and engineering-approved cleanup validation.
