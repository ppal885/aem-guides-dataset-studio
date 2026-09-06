# Jira UAC review from a fresh Claude/Codex chat

Implementation validation, 2026-09-07. This is local evidence, not a VM deployment receipt.

## Change boundary

- Branch: `codex/jira-review-feedback` in `C:/aem-jira-review-feedback`.
- Base: `fb6ea78edb5946d2297cb56fa4952102126a8c25` from `origin/main`.
- The original dirty checkout was left untouched. After explicit approval, its
  customer-discovery skill changes were reconciled in this worktree and both global
  Claude/Codex skills were installed from the tested, merged source (details below).
- No VM/Jira writes, service restarts, feedback submissions to the VM, indexing,
  writer resumes, credential changes, or learning-mode changes were performed.
- No dashboard, evaluation calculation, corpus index, generation gate or promotion
  policy changed. The existing corpus-side advisory customer profile JSON was
  preserved unchanged as a dependency; it was not ingested or approved.
- No new database migration is required by this patch: source pins/snapshots use the
  existing immutable shared-learning JSON records. The existing shared-learning
  migration must still be present on the target deployment.

## Implemented flow

1. Reviewer supplies selected Human feedback after reading Jira, in either client.
2. The skill reads the raw Jira UAC and prepares an exact SHA-256 source pin; no old
   generation chat or draft ID is required.
3. The server independently verifies the tenant-pinned Jira field and creates an
   immutable review snapshot. It does not invent generator/run lineage.
4. Capture returns a pending/candidate receipt, not approval. A missing original
   remains pending; stale content conflicts; unavailable services can queue capture
   locally without claiming VM persistence.
5. The current live QE Assignee deliberately approves an exact lesson revision.
6. The existing SQL publication/resolver creates a relevant investigation in enabled
   mode. The question and disposition retain lesson provenance. Shadow mode does not
   alter UAC output. Revocation removes future influence even if indexing lags.

Existing capture/list/status/review tools are retained. `bind_uac_feedback` is an
explicit QE-only action, not an automatic retry. `get_uac_feedback_readiness` reports
configuration without SQL, Jira, Chroma, migration or worker actions. Both tools and
the source-pin capture contract are exposed through the remote gateway, rich stdio
client, Windows client and Unix client.

## Verification

- **251 focused backend/client/governance tests passed**, seven existing SQLAlchemy
  `datetime.utcnow` deprecation warnings. Includes identity, live QE assignment,
  source mismatch, stale versions, cross-tenant isolation, spoofed approval, lineage,
  old capture compatibility, outbox/revocation, SQL resolver, shadow replay and remote
  MCP/client request contracts. Legacy feedback API cases are exercised through the
  isolated-router wrappers in `test_shared_uac_learning_remote_review.py`.
- Independent review found exponential backtracking in the new Jira criterion-label
  prefix parser. Replaced the ambiguous nested repetition with disjoint prefixes;
  supported label styles still bind correctly, mismatched criterion IDs still fail,
  and a subprocess-bounded regression covers 99,000-character formatting-only lines.
- New helper self-tests passed: raw UTF-8/CRLF hashing, exact unique excerpts, no
  source-authority escalation, minimal queue, identical retry payload, permanent
  source conflict, read-only readiness and non-queued binding.
- All **five repository skill copies** printed `ALL SELF-TESTS PASSED` with clean,
  temporary global installations before global installation. No gate was disabled or
  patched for the test. Post-installation results are recorded below.
- After installation, **all seven actual copies** (five repository, global Claude,
  global Codex) printed `ALL SELF-TESTS PASSED` from the clean worktree without a
  temporary home or canonical-root override. Enforced byte parity passed for all
  seven, fingerprint `675d047452d99708f714479cc903f568a69f95e6009ba31f6617f2f2cb75faa1`.
- Windows/Unix client files match; repository skill copies were synchronized using
  the existing canonical `.codex` sync script.
- Skill metadata validation and production-hardcoding audit passed.
- Golden suite metadata validates (18 cases), but `golden_status=seeded`. No approved
  baseline or live blinded Claude/Codex generation comparison was claimed.

Reproduce the focused suite from the repository root in PowerShell:

```powershell
$env:PYTHONPATH = "$PWD/backend"
$env:SHARED_UAC_LEARNING_WORKER_ENABLED = 'false'
$feedbackTests = rg --files backend/tests | Where-Object { $_ -match 'test_(shared_uac|shared_learning|test_plan_feedback)' -and $_ -notmatch 'test_test_plan_feedback_api.py$' }
python -m pytest --noconftest $feedbackTests backend/tests/test_chat_authoring_governance.py -q
python .codex/skills/test-plan-generation/scripts/feedback_capture.py --self-test
python .codex/skills/test-plan-generation/scripts/audit_production_hardcoding.py
```

`--noconftest` avoids unrelated application startup/migration fixtures. Each focused
test owns isolated SQL/fake Jira; the legacy API tests run via the isolated wrappers,
not by importing the production app. Running the legacy API file directly with
`--noconftest` requires its original `client` fixture and otherwise causes setup errors.

`test_jira_reviewed_lesson_changes_investigation_trace_and_revocation_removes_it`
writes `jira-review-learning-proof.json` under its pytest temporary directory. The
receipt, approval, matches, question and disposition are genuine outputs of the
isolated test; all identities/content are synthetic. The proof explicitly records
`live_vm_proven=false`. Local logs and the retained proof are under
`analysis/jira-review-feedback/` (not production telemetry).

## Preserved customer changes and global installation

The initial global fingerprint check detected independent uncommitted work, not
just old versions. With explicit user approval, these changes were preserved:

- `data/miss_probes.json`
- `references/miss-probe-library.md`
- `scripts/coverage_hypotheses.py`
- `scripts/dimension_synthesizer.py`
- `scripts/miss_probe_library.py`
- `scripts/test_skill_scripts.py`

The user-added `scripts/customer_discovery.py`,
`references/customer-discovery-learning.md` and required corpus-side
`scripts/uac_eval/customer_profiles.json` were preserved too. Eight files match the
original normalized text exactly; `test_skill_scripts.py` retains the original
customer additions alongside newer upstream and feedback tests. No original file
was edited. Three mined probes remain SHADOW and four customer dimensions remain
VALIDATING/supporting-only. They do not enter the approved shared-learning index.

Verified backups of the original skill and both global installations are under:
`C:/Users/prashantp/.codex/backups/jira-review-skills-afa9b042a00840b4b296f5632c0af418`.
The manifest records SHA-256 for every non-cache file. The customer profile was also
backed up. Original/global hashes were rechecked immediately before installation.

The existing sync script populated five repository copies and the enforced global
files. Explicitly reconciled `SKILL.md` and `test_skill_scripts.py` were then copied
to both globals; `quality-gate-checklist.md` and unrelated extensions were preserved.
No files were deleted. Installation evidence is in
`analysis/jira-review-feedback/global-install-files.json`; raw self-test logs use
the `installed-` prefix. Final evidence is in
`analysis/jira-review-feedback/global-install-verification.json`.

Until this branch is merged into the original checkout, run validation from
`C:/aem-jira-review-feedback`. That checkout is the tested canonical source. The
original checkout deliberately remains older/dirty; running its gates against
the updated globals can report fingerprint drift. No global environment setting
or fingerprint policy was changed to conceal that difference.

## Remaining deployment/release checks

The VM has not received this patch. Personal credentials are not configured in this
execution session; the helper reports `CLIENT_NOT_CONFIGURED`, not a successful VM
probe. After reviewed installation/deployment, perform the real-client proof in
[the operations runbook](shared-uac-learning.md), retaining maintenance writer pauses
and shadow mode until separately authorized. Release qualification also requires an
approved blinded benchmark, not seeded expected answers.
