# Test Oracles and Fault Injection

A scenario is not review-ready unless it has observable oracles. `No error`, `works correctly`, and `verify behavior` are not valid expected results by themselves.

## Multi-Layer Oracles

Use applicable layers:

- UI: visible state, banner text, disabled/enabled action, dirty indicator, row count, panel state, focus, accessibility label;
- Network/API: endpoint, status code, response body/error code, request payload, retry behavior;
- Backend exception: exception type, mapped error contract, warning/error message, absence of swallowed stack trace;
- Persistence: repository node/file content, version, metadata, relationship, generated artifact, reopen after refresh;
- State/recovery: rollback, cleanup, idempotency, retry state, cache invalidation, partial success handling;
- Logs/jobs: job state, queue entry, diagnostic event, correlation ID, useful log line;
- Generated output: DITA/XML/PDF/HTML output structure, validation result, link resolution, published metadata.

Every high-risk scenario should prefer at least two independent oracle layers when feasible.

## Failure Injection

Add failure-injection coverage when the changed path touches parser, validator, transformation, API, persistence, async/job, retry, cache, or UI recovery behavior.

Examples:

- parser: malformed XML, empty file, multiple files, missing root, unsupported encoding;
- validator: missing rules, duplicate rule IDs, invalid Schematron, empty Schematron, multiple Schematron files;
- transformation/output: missing template, invalid preset, broken link, metadata propagation failure;
- API: 4xx/5xx mapping, timeout, partial payload, stale ETag/version conflict;
- persistence: failed save, stale version, deleted target, permission denied, reopen/reload;
- async/job: retry, cancellation, stuck queued state, partial success, duplicate submission;
- UI: stale panel state, disabled action mismatch, optimistic success banner, concurrent tab state.

## Automation Strength

Classify existing and proposed automation as:

- Exact and strong: exact path with meaningful multi-layer oracle;
- Exact but weak oracle: exact path but only superficial assertion;
- Partial: related path or variant only;
- Obsolete: no longer matches current UI/API/code path;
- Mocked-path only: verifies mocked behavior but not integration contract;
- Missing: no relevant automation found.
