# Shared Human feedback: operation and rollout

This is reviewed team memory, not model training. The implementation lets Claude and Codex use the same VM publication through the existing port 4502 gateway. No React UI or new public port is required. The rollout checklist below has not yet been executed on the VM.

## Team workflow

1. Generate a UAC using `test-plan-generation`. Correct a specific missed check, wrong expectation, unnecessary scope, or confusing sentence in that active skill session.
2. Any authenticated teammate with tenant access may capture a correction. For active-session corrections, the skill uses `feedback_capture.py capture`: it submits only the selected Human correction, affected criteria and source references to the existing feedback API, registers an immutable UAC draft when needed, and queues the exact minimized request on a retryable delivery failure. This does not upload the whole conversation. `capture_uac_feedback` is the thin MCP alternative, not a local retry queue.
3. Read the receipt. `persisted=true` with `CANDIDATE` means saved and awaiting review. `PENDING_BINDING` means the original draft still needs resolving. A local queue is **not saved on the VM** and is not reusable memory.
4. The ticket's current **QE Assignee**, authenticated as a named Human with a personal identity, inspects the original/corrected text and binding, and explicitly approves a reusable lesson with `review_uac_feedback`. The server verifies the live Jira field for every binding or review request. Approving the Jira UAC alone is not approval to reuse the lesson.
5. Future runs retrieve the approved publication through `resolve_qe_patterns`. A lesson suggests an investigation, never an acceptance answer. The run trace records its publication, lesson, question and disposition. In shadow mode it records possible matches without changing output.
6. The current QE Assignee may reject, supersede or revoke using the exact latest revision and a reason. A Jira reassignment changes who may perform the next review action. Successful revocation takes effect at the next SQL-backed lookup even if vector cleanup is delayed.

Language lessons remain editorial guidance (`RETRIEVED_NOT_APPLIED`), not coverage requirements. Current Human out-of-scope decisions beat historical advice. A single case requires explicit applicability scope. Generic patterns require QE-confirmed independent incident groups (not duplicate ticket counts), or the reviewed normative/critical exception, and counterexample review. A supporting correction from another case must already have its own QE Assignee approval; the current reviewer cannot approve another ticket's correction by including it as support. Its exact approved revision is pinned. Revoked or superseded support stops the derived lesson's future influence until re-review. Existing unapproved patterns remain unapproved.

Read `review_policy=LIVE_JIRA_QE_ASSIGNEE`, `reuse_eligible`, and `publication_review_status` alongside the existing receipt fields. Publication review status is `PENDING_REVIEW`, `QE_APPROVED`, or `RE_REVIEW_REQUIRED`. An earlier role/admin-only approval without live QE proof remains immutable audit history but is excluded from publication until re-reviewed; an old `learning_status=APPROVED` alone does not establish current reuse eligibility.

## Identity and secure connection

Configure `AUTH_TOKENS_JSON` through the VM's existing protected environment/secrets mechanism. Each teammate needs a distinct token and stable `id` and `allowed_tenants`. Review additionally requires `principal_type: human` and an operator-provisioned `jira_identity` containing the tenant's Jira `server_url` and exactly one stable `user_key` or `account_id`. Do not use a display name, ordinary Jira Assignee, or name in prose as identity. Do not paste real tokens into repository files, command history, examples, logs, or conversations.

Only the ticket's current live **QE Assignee** may bind an existing pending correction or perform `APPROVE`, `REJECT`, `REVOKE`, or `SUPERSEDE`. Admin status, application roles, draft ownership and the ordinary Jira Assignee field do not override this rule. The `ADMIN_BEARER_TOKEN` shortcut is a shared identity; `API_BEARER_TOKEN` is a service identity. Neither can review. Dev bypass/test tokens, untyped identities, a supplied reviewer name, client type, or AI classification cannot establish review authority.

Example identity shape (replace values in protected configuration, not in this file):

```json
{"<personal-secret-token>": {"id":"team-person-id", "principal_type":"human", "roles":["writer"], "allowed_tenants":["team_tenant"], "jira_identity":{"server_url":"https://jira.example.com", "user_key":"stable-jira-user-key"}}}
```

For Jira Cloud, use `account_id` instead of `user_key`; do not configure both. These mappings belong only in protected server configuration, not in capture/review bodies or client manifests. Configure `SHARED_UAC_QE_FIELD_ID` if needed; it defaults to `customfield_18512`. The server also checks that the live field name is exactly `QE Assignee`, then matches its active user's stable identity. It does not fall back to the standard Assignee field or a role.

The tenant must be explicitly active with a pinned Jira URL and usable credentials. The personal mapping's server URL must match that tenant URL. Incomplete tenant credentials deny review; global Jira credentials are usable only when their URL exactly matches the pinned tenant server. A built-in/default tenant with an empty Jira URL cannot authorize review. Configure tenant access deliberately rather than relying on a global fallback.

Missing identity mapping, missing/invalid QE field, or unavailable Jira denies binding/review without changing the record's current state. Newly captured feedback stays pending/candidate; an unsuccessful revoke is not a revocation. Ordinary capture and generation continue. Do not bypass the check or retry a review automatically.

Clients use `AEM_STUDIO_URL` and `AEM_STUDIO_TOKEN`; canonical local adapters also locate the backend contracts through `AEM_STUDIO_REPO`. Prefer HTTPS on the existing gateway or a trusted SSH loopback tunnel. For the existing VPN-only HTTP VM address on port 4502, non-loopback HTTP requires the explicit client setting `AEM_STUDIO_ALLOW_INSECURE_HTTP=true`. That opt-in does not encrypt traffic; use only on the approved trusted network. Redirects are rejected so credentials are not forwarded to another URL.

## HTTP and CLI

All HTTP paths below use the existing `/api/v1` prefix and authenticated tenant access:

| Operation | Endpoint |
|---|---|
| Read-only readiness configuration | `GET /test-plan-learning/readiness?tenant_id=...` |
| Register immutable draft | `POST /test-plan-learning/drafts` |
| Capture selected correction | `POST /test-plan-learning/feedback` |
| Legacy/shared capture compatibility | Existing `POST /test-plans/{jira_key}/feedback` |
| List/status | `GET /test-plan-learning/feedback` and `/feedback/{id}` |
| Resolve source binding | `POST /test-plan-learning/feedback/{id}/bind` |
| Approve/reject/supersede/revoke | `POST /test-plan-learning/feedback/{id}/review` |
| Read authenticated publication | `GET /test-plan-learning/publication` |
| Resolve investigation advice | `POST /mcp/resolve-qe-patterns?tenant_id=...` |
| Index operation/recovery | `POST /test-plan-learning/index/drain` and `/index/retry` (admin) |

The strict request schemas are in OpenAPI and MCP `tools/list`; do not invent fields. Capture uses `shared-uac-feedback-v1`, an idempotency key, exact selected feedback, and the original draft/fingerprint. Review uses `expected_revision`, a reason, explicit Human-origin/applicability/counterexample attestations, and a reviewed lesson definition. `source_kind=AI_PROPOSAL` cannot become approved Human memory.

With personal credentials already set in the environment:

```bash
python .codex/skills/test-plan-generation/scripts/feedback_capture.py --help
python .codex/skills/test-plan-generation/scripts/feedback_capture.py readiness --tenant-id team_tenant
python .codex/skills/test-plan-generation/scripts/feedback_capture.py capture --input selected-feedback.json
python .codex/skills/test-plan-generation/scripts/feedback_capture.py list --tenant-id team_tenant
python .codex/skills/test-plan-generation/scripts/feedback_capture.py flush-queue
```

Run `--help` for status, draft registration, binding and review arguments. Resolving an existing pending binding requires the ticket's current live QE Assignee and tenant access. Review is never queued or automatically replayed. Network delivery failure keeps a redacted capture retry record; auth/validation conflicts require correction, not blind retries. A saved receipt is not proof that a later run used the lesson.

At the next configured skill invocation, make one bounded capture-queue flush and report saved/remaining/blocked counts. Do not convert an ambiguously failed MCP capture into a differently normalized helper request with the same idempotency key: reconcile it through list/status or replay the exact original MCP arguments. Never report a tool error as a saved or queued receipt.

### A teammate reviews an existing Jira UAC in a fresh session

The reviewer does not need the original Claude/Codex conversation. Read the live
Jira issue through Jira MCP, including the raw Acceptance Criteria field and its
field-name metadata. Use the helper's `prepare-jira-review` command with
`--jira-input`, `--input`, and `--field-id` to prepare the selected correction and an
exact source pin. Preparation is local and sends nothing. It must not be reported
as a VM receipt. Use `--help` for the input contract; do not derive the pin from
rendered HTML, an AI summary, or reconstructed criteria.

The prepared `reviewed_jira_uac` reference contains the actual custom field ID,
SHA-256 of its exact raw text, optional observed issue-update timestamp, and an
optional exact `original_reviewed_ac` excerpt. If `ac_id` is supplied, that excerpt
is required. Do not combine this reference with a generated draft, fingerprint,
bundle, or run ID. The helper does not infer `HUMAN_CORRECTION` merely because Jira
contains an acceptance field; the selected correction must actually come from
the Human reviewer.

Before submitting, check readiness for `capabilities.reviewed_jira_uac=true` on
the deployed backend. During capture, the server independently retrieves the
tenant's pinned Jira field and verifies its hash, timestamp when supplied, and
unique excerpt. Changed content is a conflict, not permission to capture a newer
version silently. Empty content cannot bind; unavailable Jira cannot establish a
source and may leave an exact retry queued locally. Reconcile the receipt rather
than claiming the review was saved.

The immutable snapshot records `generation_lineage_verified=false`. It proves
which Jira field was reviewed, not which model generated it or that its contents
are approved product truth. A later bind can use the same pinned
`reviewed_jira_uac` reference instead of a registered `draft_id`; resolving a
pending binding still requires the current live QE Assignee. Neither a snapshot
nor a Jira comment approves a reusable lesson. Explicit review and the later
publication/influence checks remain required.

## Readiness is not proof of learning

`GET /api/v1/test-plan-learning/readiness?tenant_id=...` is a bounded, authenticated,
tenant-scoped configuration check. It makes no database, Jira, embedding, index or
generation request, does not start a worker, and does not create or migrate storage.
Responses use `Cache-Control: no-store`. The contract is
`schema_version=shared-uac-learning-readiness-v1`.

The readiness response deliberately separates these states:

| Field | What it proves — and what it does not |
|---|---|
| `capabilities.capture` | This backend exposes the capture contract. Persistence is still `NOT_PROBED`. |
| `capabilities.reviewed_jira_uac` | The reviewed-Jira-UAC source-binding contract is supported by this backend version. It does not mean a particular source has been captured or verified. |
| `identity.personal_identity` | The authenticated server identity is a named Human identity. No identity or role supplied by the client can change it. |
| `identity.jira_identity_mapping_present` | An operator-provisioned Jira identity mapping exists. The live ticket's QE Assignee has **not** been verified by this check. |
| `worker.status=CONFIGURED_PAUSED` | The current process's worker setting disables startup scheduling. It does not inspect an already-created scheduler or prove its runtime state. |
| `worker.status=CONFIGURED_ENABLED_RUNTIME_UNVERIFIED` | Scheduling is configured on. This does not prove that a worker started, ran, or indexed anything. `running` remains `null`. |
| `learning.configured_mode=SHADOW` | The shared-learning lane records potential matches without changing the UAC output. |
| `learning.configured_mode=ENABLED` | Influence is configured, not demonstrated. A matching eligible lesson and a traceable investigation are still required. |
| `learning.publication/index=NOT_PROBED` | No SQL publication or index was consulted. Unknown does not mean empty or healthy. |

Development bypass and test tokens cannot use this endpoint. A real shared/service
token with tenant access may inspect configuration, but receives
`personal_identity=false` and gains no approval permission. Neither an admin role
nor an existing Jira identity mapping proves current QE-Assignee authority.
Invalid mode configuration reports `DISABLED`, matching the canonical resolver's
fail-closed behavior. No credentials, identity values, Jira URLs, correction text,
or database configuration are returned.

To answer **“was this correction saved, approved, indexed, and actually used?”**,
inspect its existing `/feedback/{feedback_id}?tenant_id=...` status and a later run
trace. These are separate claims:

- `persisted=true` proves a VM receipt; a local queue does not.
- `reuse_eligible=true` with `publication_review_status=QE_APPROVED` proves eligibility
  under current stored review/lineage policy; an old `APPROVED` label alone does not.
- `index_status=PENDING`, `FAILED`, or `INDEXED` describes that revision's outbox
  projection, not whether a future generation used it. The canonical resolver
  reads the current **SQL publication**, so pending vector projection alone does
  not make an otherwise eligible SQL lesson unavailable.
- Actual influence requires the later run's publication ID, lesson ID, relevant
  investigation question and disposition. Readiness always reports
  `actual_learning_proven=false`; even `ENABLED` plus `INDEXED` cannot establish use.

There is no automatic Jira-comment watcher. Reading or posting a Jira UAC review
does not itself create reusable memory. The skill must capture the selected Human
correction, receive a VM receipt, and obtain the explicit live-QE-Assignee review.
Configuration checks never perform those actions on the teammate's behalf.

## SQL, indexing and failure behavior

SQL is the authority: immutable draft, correction, source-binding and lesson-revision tables, plus mutable delivery outbox. Feedback/revision/outbox writes share one transaction. Identical retries are idempotent; conflicting payloads or stale review revisions fail with conflict. Legacy hashes-only feedback remains an audit record; this feature does not invent its missing text.

Only latest approved lessons enter the dedicated `uac_feedback` projection. Pending/candidate records are skipped. The bounded scheduled job processes at most 20 events from at most 10 tenants per tick, with a 60-second I/O budget, durable leases, retry/backoff and five automatic attempts. Projection subprocesses have explicit timeouts and return only safe status. Failed/exhausted jobs remain visible; an administrator can explicitly requeue after repairing indexing. Normal UAC generation does not depend on vector indexing or publication availability; it records a warning and retains the existing reasoning path.

Every retrieval rechecks the current SQL publication; there is no stale local-feedback fallback. The publication fingerprint includes policy/filter state, so compare the same cutoff and exclusion set across clients. The current target Jira is excluded automatically. Blinded generation disables this learning lane; protected validation/blind source cases cannot be published.

## Deployment checklist — not yet executed on the VM

1. Verify the deployed Git revision, Python environment, auth configuration, database dialect and migration state without printing secret values. Preserve local VM edits.
2. Take a consistent database backup using the site's SQLite backup API or PostgreSQL `pg_dump` procedure. Test restoration into a disposable database first. Do not copy a live SQLite main file alone when WAL is active.
3. Ensure metadata-only `benchmark/v2/manifests/split_manifest.json` is available. It is an existing ignored artifact, not an expected-answer file. In backend-only containers, mount it and set `SHARED_UAC_BENCHMARK_SPLIT_MANIFEST`. Missing/malformed policy permits capture but quarantines approval/publication.
4. Apply the additive `shared_uac_learning_v1` migration to a restored test database and verify existing feedback counts are unchanged. Then use the established Alembic procedure for the VM database. Do not downgrade: downgrade would remove the new learning records. SQLite development startup also creates these tables; coordinate migration state before running Alembic against an already auto-created schema.
5. Set production dev bypass off; issue personal identities with protected Jira identity mappings. Confirm `SHARED_UAC_QE_FIELD_ID` resolves to the live `QE Assignee` field. Start with `SHARED_UAC_LEARNING_MODE=SHADOW`. Preserve existing maintenance writer pauses, including `SHARED_UAC_LEARNING_WORKER_ENABLED=false`; this rollout does not authorize resuming them. Enable the learning worker only after the operator explicitly ends the relevant maintenance pause and approves indexing. Reload only through the established backend deployment procedure. No Nginx dashboard change is needed.
6. Verify `/mcp/health`, tools list, capture receipt, current-QE-Assignee review, SQL publication and bounded index job. Verify non-QE admins/teammates cannot bind/review and that missing Jira identity or unavailable Jira fails closed. Use a real approved training incident; do not upload synthetic tests or protected benchmark answers.
7. Repeat capture in Claude and retrieval in Codex, then reverse. Check publication/lesson IDs and shadow matches. Record the actual VM evidence separately from local test output.
8. Enable `SHARED_UAC_LEARNING_MODE=ENABLED` only after cross-client proof and blinded regression approval. Clients can remain shadow/disabled. Immediate rollback: set `DISABLED`; keep SQL audit records intact. Revoke individual lessons when needed.

The local implementation does not establish that the deployed VM has these migrations, identities or code. PostgreSQL deployment, VM storage backup/restore and real-client rollout remain release checks until run on that environment.
