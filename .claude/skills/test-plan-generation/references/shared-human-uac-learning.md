# Shared Human UAC feedback learning

Use this workflow when a Human corrects a generated UAC and the correction may help
future tickets.  The shared ledger is a governed learning input, not a chat archive and
not an automatic fine-tuning path.

## Non-negotiable authority rules

- Capture only feedback the Human actually supplied.  Model critique, AI suggestions,
  FluffyJaws output, and inferred user intent are not Human feedback.
- Never upload an entire Claude/Codex conversation.  Send the selected correction and
  the minimum identifiers needed to bind it to the generated draft.
- `PENDING_BINDING` and `CANDIDATE` records cannot influence another plan.
- Any authenticated teammate with tenant access may capture a correction. Only the
  ticket's current live **QE Assignee**, using a personal named Human identity, may
  bind an existing pending correction or approve, reject, revoke, or supersede a lesson.
  Admin status, application roles, draft ownership, the ordinary Jira Assignee, and
  names in tool arguments or prose do not grant review authority.
- `APPROVED` is still not the same as `INDEXED`.  Report the API's actual
  `learning_status` and `index_status`; do not infer either status.
- Also read `review_policy=LIVE_JIRA_QE_ASSIGNEE`, `reuse_eligible`, and
  `publication_review_status` (`PENDING_REVIEW`, `QE_APPROVED`, or
  `RE_REVIEW_REQUIRED`). A prior admin/role-only approval without live QE proof is
  retained as audit history, not reusable publication, until re-reviewed.
- Approval requires explicit origin, applicability, and counterexample attestations.
  A generic pattern also needs the independent Human support or reviewed exception
  required by the server policy. A supporting correction from another case must
  already have its own QE Assignee approval; including it cannot approve it implicitly.
  Support is pinned to that exact revision. Revoked or superseded support removes the
  derived lesson's future influence until re-review.
- Current-ticket feedback is excluded from that ticket's generation.  Jira/customer
  names are provenance and exclusion data, never production matching selectors.
- Language-only lessons remain authoring guidance.  They cannot activate discovery
  families, create an AC, or change an acceptance contract.

## Capture flow

0. At the start of a configured generation/capture skill invocation, make one bounded
   `feedback_capture.py flush-queue` attempt.  Replay capture records only and report
   the returned sent/remaining/blocked counts.  A context mismatch leaves the queue
   intact. Do not flush on a status/readiness-only request. Never use this step to
   retry any review decision or silently replace a stale Jira source pin.
1. Preserve the generated plan identity: `draft_id` when available, the 64-character
   `plan_fingerprint`, `evidence_bundle_id`, `run_id`, and optional `ac_id`.
2. When the Human supplies a correction, prefer `feedback_capture.py capture` whenever
   the helper is available.  It minimizes/redacts the DTO before its first send and can
   queue that exact wire request after a retryable failure.  Use a unique
   `idempotency_key`, the exact selected feedback, and the identifiers above.  Set
   `client_context.client` to `claude_desktop` or `codex`; session/message IDs are
   traceability only.  MCP `capture_uac_feedback` is a non-queueing alternate.  After an
   ambiguous MCP failure, reconcile through list/status or replay the exact same MCP
   arguments; never reuse the key with a differently normalized helper request.
3. Show the returned state honestly:
   - `QUEUED_LOCAL`: only a redacted correction is on this machine.  It is not saved,
     bound, approved, or indexed.
   - `SAVED_REMOTE`: the API persisted it; inspect `binding_status`, `learning_status`,
     and `index_status` separately.  Pending/candidate feedback normally reports
     `index_status=SKIPPED`; that is not an indexing failure and not reusable learning.
   - `INDEXED`: the API explicitly reported `index_status=INDEXED`.
4. A queued correction can be replayed with `feedback_capture.py flush-queue`.  Capture
   idempotency prevents duplicate ledger entries.  The queue never contains the draft,
   token, AI classification, session/message identifiers, or approval request.  Human
   source text and any proposed rewrite remain separate redacted fields.
5. If the record is `PENDING_BINDING`, register/locate the corresponding draft or
   verify the exact reviewed Jira UAC using the fresh-chat path below. The
   current QE Assignee may deliberately bind it through the authenticated API or
   `feedback_capture.py bind` / `bind_uac_feedback`. Do not silently bind it during
   status, capture retry, or review. Binding is explicit and does not approve a lesson.

## Fresh Claude/Codex chat after reviewing Jira

The reviewer can say: "I reviewed this Jira UAC. It misses the existing-file case.
Save this feedback for QE review." They do not need the old chat or a generated run ID.
Use this path for genuine selected Human feedback, not to mine all Jira comments or
silently manufacture feedback from model critique.

1. Read the live issue with configured Jira MCP. Identify the actual custom field
   from Jira `names` metadata (`Acceptance Criteria`, `Acceptance Criterion`, or `UAC`)
   and keep its raw string plus `fields.updated`. An installation can pin the exact
   field with `JIRA_ACCEPTANCE_CRITERIA_FIELD_ID`; do not guess another field. Preserve
   UTF-8 content, whitespace and line endings. Rendered text/HTML or structured ADF is
   not a substitute. Read only the selected source; do not attach issue history/chat.
2. Prepare a private selected-feedback JSON containing `tenant_id`, `raw_feedback`,
   `source_kind=HUMAN_CORRECTION` only for actual Human text, and
   `client_context.client`. Keep an optional proposed rewrite separate. When selecting
   a particular `ac_id`, include `original_reviewed_ac` as a unique exact excerpt of
   that original criterion. A missed scenario can be attached to the whole UAC without
   inventing an AC ID. Secret-bearing excerpts must be omitted together with `ac_id`.
3. Run the helper against the raw Jira response. Preserve its prepared payload and
   idempotency key for capture/retries; preparing again creates a new logical capture.

   ```text
   python scripts/feedback_capture.py readiness --tenant-id <configured-tenant>
   python scripts/feedback_capture.py prepare-jira-review --jira-input raw-jira.json --input selected-feedback.json --field-id <actual-custom-field-id>
   python scripts/feedback_capture.py capture --input prepared-feedback.json
   ```

   The preparation command prints JSON; save that exact output privately as
   `prepared-feedback.json` before capture. It performs no network request. It emits
   `reviewed_jira_uac={field_id, expected_sha256, expected_issue_updated,
   original_reviewed_ac}` with SHA-256 of the exact raw field. Do not send a full draft,
   `draft_id`, `plan_fingerprint`, `evidence_bundle_id`, or `run_id` along with this pin.
   MCP `capture_uac_feedback` accepts the same source-pin object when the helper is
   unavailable. Compute the hash mechanically; never invent it.
4. The VM independently fetches the tenant-pinned Jira field, checks its name, raw
   hash, optional update timestamp and excerpt, and registers an immutable
   `JIRA_REVIEW_SNAPSHOT`. This proves which Jira UAC was reviewed, **not** its original
   generator/run lineage and **not** that AI-written UAC text is Human-approved truth.
   Only the selected Human correction is a learning candidate.
5. A stale hash/version returns a conflict. Stop that retry and ask the reviewer which
   version they reviewed; never silently capture the new current UAC. An unavailable
   Jira read is retryable; an empty field stays pending. If raw MCP data is unavailable,
   save the selected correction without source IDs as `PENDING_BINDING`, instead of
   inventing a pin. Only the live QE Assignee may later bind it deliberately.
6. Show a short receipt: "Feedback <id> saved on VM. Pending QE review; not yet shared
   learning." Or "Queued locally—not saved on VM." Include a binding issue if returned.
   Do not say "learned" merely because capture succeeded. If the server lacks the new
   capability, report that deployment gap; do not pretend the new binding path ran.

For an existing pending item, `bind_uac_feedback` accepts exactly one `draft_id` or
`reviewed_jira_uac` source plus `feedback_id`, `tenant_id`, and an idempotency key.
The CLI equivalent is `bind --feedback-id <id> --tenant-id <tenant>
--reviewed-jira-uac pin-only.json --idempotency-key <unique-key>`.
Never queue or automatically replay binding or review decisions.

Example CLI capture payload (write this to a private file or pass it on stdin; do not
put credentials in it):

```json
{
  "tenant_id": "team_tenant",
  "jira_key": "PROJECT-123",
  "idempotency_key": "client-session-message",
  "raw_feedback": "The Human's selected correction",
  "source_kind": "HUMAN_CORRECTION",
  "proposed_correction": "Optional corrected AC text",
  "delta_type": "COVERAGE_ADDED",
  "draft_id": "server-draft-id",
  "plan_fingerprint": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "evidence_bundle_id": "bundle:sha256",
  "run_id": "runtime-run-id",
  "ac_id": "AC-03",
  "client_context": {
    "client": "codex",
    "session_id": "local-session-id",
    "message_id": "local-message-id"
  }
}
```

Run:

```text
python scripts/feedback_capture.py register-draft --input draft.json
python scripts/feedback_capture.py capture --input capture.json
python scripts/feedback_capture.py flush-queue
python scripts/feedback_capture.py status --feedback-id <id>
```

The helper reads `AEM_STUDIO_URL` and a personal `AEM_STUDIO_TOKEN`.  `dev-bypass` is
rejected for this workflow because it cannot establish a named Human actor.  Plain HTTP
is automatic only on loopback; the private/VPN VM address requires the explicit
`AEM_STUDIO_ALLOW_INSECURE_HTTP=true` opt-in.  Team/production deployments should use
TLS or a loopback tunnel.

The server's protected `AUTH_TOKENS_JSON` entry maps that personal identity to
`jira_identity={server_url, user_key}` or `{server_url, account_id}`; configure exactly
one stable Jira identifier, never a display name. This mapping is not a client argument.
The server reads the live ticket using `SHARED_UAC_QE_FIELD_ID` (default
`customfield_18512`) and verifies that the field is named `QE Assignee` before checking
the current active user. If identity cannot be verified, the field is missing, or Jira
is unavailable, binding/review is denied. Pending feedback stays pending, existing
review state is unchanged, and normal generation continues. Do not substitute a role,
standard Assignee, cached name, or local approval.

The configured tenant must be active and have an explicit pinned Jira URL and usable
credentials. The personal Jira identity must match that server; an empty default
tenant URL or incomplete tenant credentials cannot fall back to an arbitrary global
Jira connection. Global credentials are allowed only for the exact pinned server URL.

## Review flow

1. Use `list_uac_feedback` to find visible pending candidates and
   `get_uac_feedback_status` to read the current revision and binding state.
2. Investigate the Human correction against current Jira decisions, evidence,
   counterexamples, and hard negatives.  Do not approve a generated lesson merely
   because its wording sounds plausible.
3. The ticket's current live QE Assignee, authenticated as a named Human, calls
   `review_uac_feedback` with
   `expected_revision`, a unique review idempotency key, `APPROVE`, `REJECT`,
   `REVOKE`, or `SUPERSEDE`, and the required attestations.  Approval/supersession is a
   single deliberate request.
   The server rechecks current QE assignment on every request; a prior successful
   review or later Jira reassignment is not continuing authority for the old reviewer.
   Review operations are never queued or automatically retried.
4. Read status again.  Only an approved SQL publication is eligible for shared
   resolution, and revocation must remove its future influence.  The separate index
   projection may lag or fail; always report its real status without treating it as the
   authority for SQL-backed resolution.

## Use during future generation

The canonical runtime resolves shared learning through the authenticated VM
`resolve_qe_patterns` route.  It must not read the local retry queue or a local feedback
JSON file.

- `DISABLED`: do not call the shared resolver.
- `SHADOW`: trace matching approved lessons, but do not alter questions, evidence,
  hypotheses, dispositions, or rendered UAC.  This is the default rollout mode.
- `ENABLED`: only server-published, non-revoked lessons may be returned.  Discovery
  patterns still propose what to investigate, never the answer.  Authoring guidance is
  returned separately as `RETRIEVED_NOT_APPLIED`; a Human/Claude author decides whether
  it applies and the trace must not claim it was applied merely because it was retrieved.

If the shared VM is unavailable, preserve the existing approved TRAIN baseline and emit
the explicit shared-learning status `UNAVAILABLE` with no shared matches.  Never silently
fall back to pending feedback, a stale local shared snapshot, or the retry queue.

## MCP tool contract

The desktop clients expose exactly these governed tools:

- `capture_uac_feedback`: persist a Human correction as pending/candidate feedback.
- `list_uac_feedback`: list records visible to the authenticated actor.
- `get_uac_feedback_status`: return binding, review, publication, and index state.
- `get_uac_feedback_readiness`: configuration-only diagnostics; does not inspect SQL,
  Jira, Chroma, the outbox or publication state, and never grants review authority.
- `bind_uac_feedback`: explicitly bind an existing pending correction to its verified
  source; restricted to the current live QE Assignee and never an approval operation.
- `review_uac_feedback`: approve/reject/revoke/supersede with optimistic revision and attestations.

All six are thin forwards to the shared VM using the same personal Bearer credential.
The server, not the desktop client, enforces tenant scope and current live QE Assignee
authorization. Roles and ownership do not confer review authority. MCP capture does not use the helper's local retry
queue; use the helper-first capture flow above when offline retry is required.
