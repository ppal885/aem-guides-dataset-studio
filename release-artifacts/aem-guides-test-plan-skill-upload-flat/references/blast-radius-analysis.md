# What can break — impact analysis reference

> **Plain English:** This file supports **section 2 — What can break & risks** in the test plan. Internal name: blast-radius analysis. In the **plan body**, write **what can break**, **what goes wrong**, **must not break** — not "blast radius" or "oracle".

Use this reference for every JIRA-driven AEM Guides test plan before selecting or generating scenarios. Impact analysis remains a blocking gate; the goal is bug discovery and regression prevention.

## Workflow

The mandatory sequence is JIRA intake -> evidence collection -> RAG retrieval -> implementation and automation repository inspection -> blast-radius analysis -> bug hypothesis register -> kill-the-fix analysis when diff exists -> historical regression analysis -> interaction matrix -> risk prioritization -> scenario design -> automation strength assessment -> regression pack split -> residual risk and validation.

Do not claim a plan is review-ready if blast-radius, bug-hypothesis, oracle, or residual-risk analysis is missing or incomplete.

## What to Trace

For every bug, enhancement, regression, behavior change, refactor, dependency update, configuration change, or infrastructure JIRA, trace user/technical entry point, requested/current behavior, changed or suspected implementation point, upstream callers and inputs, shared services/utilities/validators and contracts, persistence/cache/state/asynchronous boundaries, error handling and recovery, downstream UI/API/job/output consumers, existing automation strength, compatibility dimensions, proven non-impacts, and unknown evidence gaps.

## When a Diff Exists

Compare the correct base and target revisions. Identify changed files, methods, conditions, branch order, default values, exception paths, error contracts, and data-shape changes. Find callers and downstream consumers. Find existing automated tests coupled to the path. Record repository, branch/commit, path, and line evidence. Perform Kill the Fix analysis: every changed branch and error contract maps to a test or evidence-backed exclusion.

## When No Diff Exists

Start from reproduction steps, endpoint, UI label, configuration, error message, content construct, or historical defect pattern. Trace the current implementation. Produce a provisional blast radius and bug hypotheses. Clearly label assumptions and unknown areas. Do not present suspected impact as confirmed impact. Plans with missing code evidence remain Draft unless explicitly accepted.

## Impact Classifications

| Impact level | Definition | Required action |
| --- | --- | --- |
| Direct | The behavior, code, configuration, or contract is explicitly being changed. | Mandatory direct functional, negative, boundary, reproduction, and fix-escape testing. |
| Shared-path | Another workflow uses the modified service, utility, validator, endpoint, DTO, state, or exception handling. | Representative regression plus shared-caller hypothesis testing is mandatory. |
| Downstream | A UI component, panel, API consumer, persistence layer, publishing job, output, or integration consumes the changed result. | Cover critical contracts and consumers with multi-layer oracles. |
| Compatibility | A deployment, browser, content version, output type, permission, or configuration variant can alter the changed path. | Include targeted or pairwise interactions only when evidence establishes interaction. |
| Observability/Recovery | The change can affect error handling, retry, dirty state, partial success, cache invalidation, rollback, diagnostics, or recovery. | Include failure-injection and recovery coverage. |
| Not impacted | Code, documentation, or runtime evidence shows the area does not use or consume the changed path. | Exclude from regression with concise evidence-backed reason. |
| Unknown | Available evidence is insufficient. | Add decision-changing question, lower confidence, or mark plan Draft. |

## Regression Rings

| Ring | Purpose |
| --- | --- |
| R0 - Control | Smallest normal unchanged behavior proving standard workflow still works. |
| R1 - Direct | Exact acceptance criteria, customer reproduction, minimal reproduction, negative and immediate boundaries. |
| R2 - Shared path | Other inputs or workflows using the changed service, contract, utility, state, or error handling. |
| R3 - Downstream | Persistence, UI consumers, background jobs, output, cache, error handling, retry, recovery, observability. |
| R4 - Compatibility | Deployment, content type/version, browser, output, permission, and configuration combinations proven relevant. |

R0-R3 normally contain mandatory P0/P1 regression. R4 must use evidence-based pairwise or targeted combinations; do not generate a full Cartesian combination.

## AEM Guides Areas to Consider

Consider but do not include blindly: Web Editor Save and Save All, Author and Source mode, multiple tabs/files, workspace/folder/global settings, validation and Schematron, content persistence and versioning, UUID/non-UUID, Cloud/on-prem, topic/map/bookmap, Native PDF, DITA-OT output, AEM Site output, baseline/review workflows, permissions, caching/indexing, large content, concurrency, localization, accessibility, logging and diagnostics.

Include only when requirement, code, configuration, runtime, documentation, or historical-defect evidence establishes interaction. Otherwise classify as `Not impacted` with a concise reason.

## Evidence and Exclusion Rules

Every scenario must trace to a requirement, risk, blast-radius item, bug hypothesis, historical signal, or interaction. Every P0/P1 risk and every Direct/Shared-path blast-radius item must be covered or explicitly excluded. Exclusions require evidence and a concise reason. Suspected impact must be labeled provisional. Missing Jira/RAG/code evidence forces Draft status.
