# Dashboard-only UI cleanup baseline

This baseline freezes the repository state used for the dashboard-only UI cleanup. It is evidence for the deletion boundary and regression comparison; it does not change runtime behavior.

## Source state

- Source commit: `cf5bc7e5e25599ead63b3303afe406f2e33aa90d`
- Implementation branch: `codex/dashboard-only-ui-cleanup`
- Active frontend tree: `a160c84f8bfd2157907a811afdfc8458a9157210`
- Tracked files under `frontend/`: `162`
- Original checkout status digest (SHA-256): `03008b5f3dc06b8130c371614f6d3b0fd3142466bea5fd6c80ada14e6f6e6034`

The implementation uses a separate clean worktree. The original dirty checkout is not modified.

## Retained interface hashes

These files must remain byte-identical during this cleanup:

| Interface | SHA-256 |
| --- | --- |
| `scripts/uac_eval/dashboard.html` | `a573b055cc351c23e5f9e526bc9404dd6c9538be850e90a4ccf047b6eacd6614` |
| `scripts/uac_eval/dashboard_data.json` | `df84014d4dfd5026a2c2faa5f0ec87e0a5bdd959f87b7c854ea1cb7770461ab4` |
| `scripts/uac_eval/aggregate_runs.py` | `533bbf222ee8129ed7881fcf44bf3ace8a36069ee2b5ddbd4d9dab9b6bb06bf5` |
| `scripts/run_test_plan_pipeline.py` | `92083ba1860f2e86f218a6a548a7bd89b5e28388405917e7a31c69a99ce34546` |

## Authorized deletion boundary

Only the 162 tracked files in the active top-level `frontend/` tree may be removed. Ignored or untracked files in the user's original checkout, including `frontend/.env` and `frontend/node_modules`, are outside this operation.

Historical UI snapshots under `.claude/worktrees/` and `incoming_archives/` remain intact. The backend, UAC skill and mirrors, MCP adapters, evaluation code and data, CLI pipeline, corpora, evidence, benchmarks, and `ui_harvester/` also remain intact.

## Baseline regression result

- Eval aggregator self-test: PASS.
- Selected canonical runtime tests: 110 passed, 1 failed, 6 warnings.
- The one failure is pre-existing: `test_tenant_identity_cannot_change_semantic_activation` expected `Publishing`, while the baseline returned `Native_PDF`.

The cleanup must preserve this runtime result; it must not hide or repair that unrelated baseline failure.
