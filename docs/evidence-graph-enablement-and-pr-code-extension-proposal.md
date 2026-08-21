# Evidence Graph Enablement and PR/Code Extension Proposal

## Decision Boundary

This document is a proposal only. It does not enable the Evidence Knowledge Graph, change its schema, add PR/code ingestion, or alter the current test-plan flow. Both options below require an explicit approval before implementation.

## Current Architecture

- The graph augments the existing Chroma collections; it does not replace semantic retrieval.
- SQLAlchemy stores blue/green graph generations, nodes, edges, provenance assertions, source events, source checkpoints, sync runs, and query audits.
- Alembic migrations already create the graph tables in this order: `add_evidence_graph`, `evidence_graph_phase_b`, and `test_plan_feedback_v1`.
- Full builds currently reconcile deterministic evidence from Jira, Experience League documentation, and DITA specification sources.
- Incremental synchronization accepts only `jira`, `docs`, and `dita` source events.
- Promotion is blocked by incomplete source scans or graph audit failures. The previous successful generation remains available for rollback.
- The current contract is `evidence-graph-v2`. It has no `pull_request` or `code_change` nodes and no `FIXED_BY` or `SUPERSEDES` relations.
- Existing node, edge, and assertion tables are generic enough to store additional contract types. A PR/code extension would still require a new graph contract version, deterministic adapters, query rules, and tests even if no new table columns are needed.
- Runtime querying, event capture, and synchronization remain disabled by default in `backend/.env.example`.

## Option A — Enable the Existing Graph As-Is

### Required rollout work

1. Back up the live SQLite database and Chroma directory with `scripts/backup_evidence_graph_vm.sh --manage-service`.
2. Apply Alembic through the current head so all graph and query-audit tables exist.
3. Keep `EVIDENCE_GRAPH_ENABLED=false` and run `scripts/build_evidence_graph_vm.sh --dry-run`.
4. Stop if Jira, documentation, or DITA scan counts are incomplete, or if any graph audit fails.
5. Run `scripts/build_evidence_graph_vm.sh --apply`; promotion must succeed before enabling queries.
6. Set a dedicated audit hash key and integrity key, then enable graph querying in `shadow` test-plan mode.
7. Enable durable event capture and five-minute synchronization only after the promoted generation passes smoke and authorization checks.
8. Keep test-plan mode at `shadow` until a golden-ticket benchmark confirms useful paths, citation precision, latency, and no regression in the direct RAG/Jira/Git evidence flow.
9. Move to `augment` only after benchmark approval. Direct source retrieval remains mandatory and graph paths never replace leaf citations.

### Cost

- Engineering change cost is low because the migrations, build/audit CLI, blue/green promotion, rollback, scheduler, and Nginx-facing MCP integration already exist.
- Expected operational effort is about one engineer-day for backup, migration, dry run, full build, audit, smoke checks, and rollback rehearsal; allow another half-day if live storage paths or service environment variables need correction.
- The configured full-build guardrails are 20 minutes and 1.5 GB peak memory with batches of 500. Actual duration and storage must be measured on the VM; no fixed storage multiplier should be promised before the dry run reports node, edge, and assertion counts.
- Ongoing cost is a five-minute incremental drain, nightly reconciliation, SQLite growth for generation retention, and periodic cleanup/backup monitoring.

### Gain

- Connects documented behavior, Jira symptoms, root causes, QA oracles, releases, outputs, and DITA entities with deterministic provenance.
- Improves same-mechanism historical discovery while keeping customer, component, and domain overlap as ranking boosts rather than proof.
- Exposes graph freshness, coverage, redaction, and degraded-source warnings to MCP callers.
- Gives test-plan generation traceable multi-source paths without double-counting graph and direct evidence.
- Supports atomic promotion and content rollback without reverting the database schema.

### Remaining limitations

- A graph path cannot identify the PR or code change that implemented a Jira fix.
- It cannot determine whether one implementation superseded another.
- Git, PR, product-code, and automation evidence must continue to be inspected live and cited directly.
- A Jira HTTP 403 still prevents validation of mutable current Jira facts, although indexed historical evidence remains usable with a degraded warning.

## Option B — Extend the Graph With PR and Code-Change Evidence

### Proposed contract

- Bump the contract to `evidence-graph-v3`.
- Add node type `pull_request` with stable key `pull-request:<repository>:<number>`.
- Add node type `code_change` with stable key `code-change:<repository>:<commit>:<path>:<symbol-or-hash>`.
- Add `FIXED_BY` from `jira_issue` to `pull_request`.
- Add `CONTAINS_CHANGE` from `pull_request` to `code_change`; this supporting relation is necessary so code-change nodes are not disconnected.
- Add `SUPERSEDES` between pull requests and between code changes when deterministic ancestry, replacement, revert, or explicit supersession evidence exists.
- Keep code text and repository snapshots out of the graph. Store only whitelisted identifiers, repository/path/symbol metadata, commit hashes, state, timestamps, and short sanitized excerpts.
- Treat explicit Jira development links, repository-native PR metadata, commit ancestry, and inspected diffs as deterministic evidence. Never infer fix or supersession edges from semantic similarity alone.
- A `FIXED_BY` path may rank evidence but cannot prove current behavior unless the referenced diff and current repository state are inspected directly.

### Services and interfaces affected

- `evidence_graph_contract.py`: node types, relation endpoints, property allowlists, stable keys, trust rules, and schema version.
- `evidence_graph_build_service.py`: a paginated PR/code adapter, deterministic link extraction, source hashes, redaction, and complete-scan accounting.
- `evidence_graph_sync_service.py`: a new `code` source kind, event coalescing, retries, checkpoints, deletion/tombstone handling, and reconciliation.
- `evidence_graph_store.py`: audits for new endpoint combinations, assertions, dangling code nodes, generation integrity, and source coverage.
- `evidence_graph_query_service.py`: approved traversal, mechanism ranking, freshness, authorization, result sections, path deduplication, and direct-leaf citations.
- `evidence_graph_models.py` and migrations: likely no new columns because the tables are generic, but add an explicit migration/checkpoint for contract-v3 rollout if indexes or source-state constraints change.
- `scripts/evidence_graph_admin.py` and VM scripts: include/exclude `code`, report coverage, preserve nonzero failure exits, and support dry-run sizing.
- MCP and test-plan integration: expose PR/code paths as traceability only, require direct Git/PR inspection, and deduplicate by repository/PR/commit/path leaf identifiers.
- Tests and operations: stable IDs, redaction, idempotency, deleted/force-pushed PRs, supersession rules, authorization, pagination, rollback, latency, and scheduler locking.

### Rough implementation size

- Contract, deterministic adapter, synchronization, query integration, administration, and migration/checkpoint work: roughly 1,500–3,000 production lines plus tests and fixtures.
- Delivery estimate: 8–15 engineering days, normally 2–4 calendar weeks including repository-access decisions, security review, representative backfill, benchmark tuning, and VM rollout.
- Storage growth is proportional to the selected repositories, PR retention window, and file/symbol granularity. Size the first dry run before promotion and cap per-PR code-change nodes; do not ingest full source files or complete repository history.

### Risks and controls

- Repository credentials and cross-repository visibility require explicit authorization and redaction rules.
- Force pushes, rebases, backports, reverts, and cherry-picks make `SUPERSEDES` unsafe unless supported by deterministic repository evidence.
- Large monorepos can exceed query and rebuild budgets; adapters must paginate and restrict repositories, time windows, and changes per PR.
- Stale PR state must be surfaced as degraded rather than silently treated as current.
- Candidate or similarity-only links must never become expected behavior, acceptance criteria, or same-mechanism proof.

## Recommendation

Approve Option A first as a controlled `shadow` rollout. It provides immediate deterministic Jira/documentation/DITA relationship value with low code risk and produces real VM sizing data. Keep live Git and PR inspection unchanged.

Evaluate Option B as a separate contract-v3 project after the shadow benchmark. Start with one repository and explicit Jira-to-PR links, measure precision and storage, then add code-change and supersession relationships only after deterministic rules pass audit.

## Approval Gates

- Option A implementation requires approval to migrate, build, and change VM flags.
- Option B implementation requires a separate approved design for repositories, credentials, retention, authorization, relation semantics, and performance budgets.
- Until those approvals are recorded, the current disabled flags and graph schema remain unchanged.
