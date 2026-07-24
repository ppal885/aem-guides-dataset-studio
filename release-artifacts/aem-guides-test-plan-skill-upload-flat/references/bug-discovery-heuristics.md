# Bug Discovery Heuristics

The primary objective of a JIRA-driven AEM Guides test plan is bug discovery and regression prevention. Test cases are only the delivery format.

## Bug Hypothesis Register

After blast-radius analysis and before scenario design, generate a ranked Bug Hypothesis Register. Each hypothesis must have an ID (`BH-001`), trigger, suspected failure, evidence, priority, confidence, and scenario/exclusion mapping.

Derive hypotheses from:

- changed conditions, guards, feature flags, defaults, and branching order;
- adjacent branches not directly mentioned in the fix;
- null, empty, missing, duplicate, malformed, very large, and unexpected inputs;
- collection ordering, stable sorting, deduplication, and first/last item behavior;
- exception mapping, swallowed errors, error-code/message changes, and UI/backend contract drift;
- shared callers, reused validators, common parser utilities, common persistence services, and shared UI components;
- persistence, versioning, dirty state, cache invalidation, and reopen behavior;
- configuration inheritance across global/folder/workspace/user settings;
- partial failures, retries, async jobs, rollback, cleanup, and idempotency;
- concurrency, multiple tabs, repeated Save/Save All, and stale UI state;
- historical defects, reopened issues, customer escapes, similar stack traces, and prior missing automation.

## Kill the Fix Analysis

When a fix diff is available, try to prove the fix is incomplete or unsafe. Generate tests that detect:

- incomplete fixes where only the exact reproduction is handled;
- overly narrow fixes that miss empty/multiple/malformed variants;
- overly broad fixes that suppress valid behavior;
- UI-only fixes that do not enforce backend/API contracts;
- backend-only fixes where UI state, warnings, or recovery remain wrong;
- branch-order regressions and adjacent condition inversions;
- changed exception contracts that break callers or observability.

Every changed branch, guard, exception mapping, error contract, and modified shared utility must map to a scenario or an evidence-backed exclusion.

## Interaction Matrix

Build a targeted/pairwise interaction matrix instead of a full Cartesian product. Include only combinations that can exercise the changed path. Explain why each selected interaction matters and what defect it is intended to expose.

Common AEM Guides axes: content state, Schematron present/absent, empty/multiple Schematron files, folder profile inheritance, map/topic/bookmap, UUID/non-UUID, author/source mode, Save/Save All, Cloud/on-prem, output preset, baseline, permissions, cache state, and concurrent edits.

## Regression Packs

Divide coverage into:

- PR Gate: fastest exact reproduction, fix-escape, R0 control, and strongest oracle checks;
- Component Regression: service/parser/validator/API/component paths and adjacent branches;
- Nightly: larger data, concurrency, async/retry/cache/persistence, and historical regression signals;
- Release Regression: cross-version/configuration/output compatibility and customer-critical flows;
- Exploratory: focused charters for high-risk or low-confidence unknowns.
