# Shared Human Feedback Learning — implementation report

Status: **IMPLEMENTED LOCALLY; ROLLOUT BLOCKED**. No claim of a live VM deployment or actual desktop-session proof.

Worktree: `C:/aem-uac-learning`  
Branch: `codex/shared-uac-feedback-learning`  
Base: `51036655052ad8392c77c83774610325a3555db9`

## Delivered

- Backward-compatible capture for legacy `evidence:` and canonical `bundle:` references, plus immutable draft registration and explicit pending binding.
- Selected Human correction and proposed rewrite stored separately, with redaction, source hashes, tenant scope, authenticated submitter identity and versioned reviewer decisions.
- Current live Jira **QE Assignee** approval, replacing the earlier named-admin/reviewer-role policy. Personal server-mapped Jira identity and a fresh field read are required; standard Assignee, admin/role, draft ownership, dev/shared/service credentials and client-supplied names confer no authority. AI proposals and protected benchmark sources remain excluded.
- Binding/review proofs record the observed field, stable identity, server and time. Supporting corrections require their own exact QE-approved revision. Revoked/superseded support and proofless old approvals cannot influence publication, even while stale physical vectors remain.
- Additive SQL migration, immutable correction/binding/revision records, transactional outbox, payload-conflict detection, concurrent retry/review protection, bounded index worker and explicit exhausted-job recovery.
- Dedicated approved-feedback vector projection; fresh SQL publication remains the authority for scope, source exclusions, supersession and revocation even if indexing fails or old vectors remain.
- Four feedback MCP tools across the remote gateway, full stdio server and both release clients; equivalent HTTP and stdlib CLI access. No new UI or public port.
- Helper-first active-skill capture with exact redacted retry payloads, OS locking, destination/credential binding, honest local-vs-remote receipts, and capture-only bounded retry on the next configured invocation. Reviews are never automatically retried.
- Existing Pattern resolver/canonical investigation integration. Default SHADOW records matches without changing UAC output. Enabled lessons suggest investigation, not acceptance truth. Editorial lessons remain separately identified guidance, not coverage expansion.
- Source skill synchronized to all five repository copies. Actual global installations were preserved because of conflicting existing local edits.

The test-plan-generation and security skills drove the source-authority, blinded-evaluation, credential, minimal-capture and reviewed-publication boundaries. No gates were weakened or blanket waivers added.

## Observed local proof

`local-learning-proof.json` records actual test-generated identifiers and transitions:

1. A real canonical compatibility-runtime result supplies the bound draft, run, bundle and exact criterion.
2. The selected synthetic correction is persisted as a bound candidate in isolated SQL.
3. An authenticated named test reviewer, matched to the synthetic live Jira QE Assignee response, approves its exact revision and persists the authorization proof.
4. The approved SQL publication is resolved for a different case.
5. The lesson is linked to an investigation question and a non-acceptance disposition.
6. Acceptance-contract and promotion outputs remain unchanged.
7. Revocation removes the publication and future influence.

Authenticated HTTP/MCP integration tests separately exercise Claude-to-Codex and Codex-to-Claude identities, tenant denial and review-claim rejection. These are protocol-level tests using synthetic identities, not two real desktop sessions or VM records. The runtime proof uses the existing Python compatibility profile, not a live Claude reasoning call.

## Validation

| Check | Result |
|---|---|
| Selected backend/API/MCP/security/learning regression suites | **301 passed, 1 pre-existing failure** |
| New live-QE authorization transport/mapping tests | 31 passed, synthetic Jira reads only |
| Server identity and bounded lineage/error-redaction tests | 10 passed |
| Original entry-point stage/decision/output-hash parity | PASS after fixing disabled-mode trace difference |
| Six-case disabled vs shadow replay | All six rendered outputs and semantic projections unchanged |
| Blinded replay | Zero shared-learning loader calls |
| Feedback CLI self-test | PASS |
| Five repository copies | All 176 checked source files byte-match each copy |
| Standard skill suites | Each stops at the same pre-existing hardcoding assertion |
| Previous-run diagnostic continuation after that assertion | Remaining checks passed in all five copies before this QE-policy update; not rerun as part of this update and not a green/waived standard suite |
| Production-hardcoding audit | Same eight pre-existing findings as clean base, in unchanged `coverage_forcing.py` |
| `git diff --check` | PASS |
| Original dirty checkout safety | Original HEAD and all 16 recorded dirty-file hashes unchanged |

The remaining backend failure is `test_tenant_identity_cannot_change_semantic_activation` (`Publishing` expected, `Native_PDF` observed). It also failed in the before-change baseline. No evaluation metric, judge, dashboard, corpus, or unrelated source file was changed to hide either baseline failure.

Final normal logs and hashes are in `validation-report.json`; continuation diagnostics are separate `skill-self-tests-continuation-*.txt` files. `runtime-shadow-proof.json` contains the six replay hashes. `safety-report.json` records protected-path and original-checkout checks.

The live-page field verification, revised reviewer policy and rollout boundaries are in
`qe-assignee-policy.md`. That page verification is not a live VM approval test; real QE
identity mappings, credentials, field read and approval still need deployment validation.

## Release blockers and next steps

1. **VM access/deployment:** prior SSH access was denied. Database backup/restore, deployed authentication, additive migration, real Chroma projection and named real-client proof are not verified. Follow `docs/operations/shared-uac-learning.md`; do not send synthetic tests to production.
2. **Global installation conflicts:** reconcile the existing global Codex/Claude skill edits before synchronization. They were not overwritten or silently replaced with this branch's older baseline files.
3. **Existing regression failures:** review the unrelated classification failure and eight existing hardcoded references separately. They remain failures, not waivers.
4. **Broader rollout validation:** PostgreSQL deployment and a full Human-scored golden benchmark were not executed. The six-case blind/shadow replay proves output invariance only, not improved Human-requirement recall or precision.

Keep SHADOW until these rollout checks pass. DISABLED remains the rollback switch. No model training, bulk reingestion, existing-pattern bulk approval, Jira posting, commit, push, or VM mutation was performed.
