# Shared Human Feedback Learning baseline

Implementation base: `51036655052ad8392c77c83774610325a3555db9` (verified `origin/main`).
Branch: `codex/shared-uac-feedback-learning`; isolated sparse worktree: `C:/aem-uac-learning`.
The original checkout at `cf5bc7e5e25599ead63b3303afe406f2e33aa90d` contains existing changes and is not edited.

## Before-change tests

Executed on the clean same-commit dashboard-only worktree with Python 3.11.0, a fresh temporary SQLite database, startup corpus synchronization disabled, and no live providers.

Selected suites: test_test_plan_feedback_service, test_test_plan_feedback_api, test_test_plan_feedback_migration, test_qe_pattern_mcp_service, test_qe_pattern_mcp_interfaces, test_pfix02_pattern_runtime_integration, test_canonical_test_plan_runtime_contracts, test_remote_mcp_gateway.

Result: **158 passed, 1 failed, 5 warnings** (11.77 seconds). The existing failure is `test_tenant_identity_cannot_change_semantic_activation`: expected `Publishing`, received `Native_PDF`. Do not repair or waive this unrelated classification failure here.

The production-hardcoding audit also fails identically on the clean base and implementation worktree: eight pre-existing Jira-key occurrences in `scripts/coverage_forcing.py` at lines 267, 468 (two), 486, 492, 504, 509, and 515. That file is unchanged by this work. These failures are recorded, not waived or silently repaired using the user's unrelated dirty changes.

An ignored existing TRAIN taxonomy is needed for replay: `benchmark/v2/train_mining/reasoning_pattern_taxonomy_train_v2.json`, SHA-256 `b19c9a7dc4f04da2a0885b0f6fd92de362fa7f5ab3cb4529700d6b7e39dcd2ac`. It was copied unchanged from the user's checkout, not ingested, regenerated, or staged. Python 3.12 lacked the MCP dependency, so the final baseline uses the existing Python 3.11 backend environment.

## Observed integration gaps

- Canonical generation identifies evidence with `bundle:`; legacy feedback validation accepts `evidence:` identifiers only.
- Feedback audit storage contains hashes, not the correction text required for reusable lessons.
- Current clients do not expose feedback capture/review/status tools.
- Existing pattern resolution does not consume reviewed feedback publications.
- Shared development/service credentials cannot identify a named Human approver.

## Proof boundary

The live HTTP gateway was reachable during the prior audit, but SSH access was denied. This work does not claim deployed migrations, VM backups, production indexing, or live cross-client learning until those are separately verified. Test fixtures are local only; no artificial Human feedback is sent to the VM.
