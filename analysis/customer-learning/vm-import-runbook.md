# VM-only customer-history import handoff

This is a pending operator runbook, not an executed deployment. The parity repair adds backend index-identity observability and import guards; it does not consolidate the VM stores. See [the root-cause report](vm-index-parity-root-cause.md). Customer-profile data and learned-probe/skill changes are separate and are not included. Keep the CSV, snapshots and audit output outside the dashboard webroot and out of version control. Start with diagnosis only; do not import until the target-index mismatch is resolved.

## First run: standalone diagnosis only

Copy `scripts/uac_eval/diagnose_vm_customer_index.py` to `/root/diagnose_vm_customer_index.py` on the VM. This one file is self-contained and needs only Python 3; no repo pull, CSV transfer, virtualenv activation or package install is required for diagnosis.

Alternatively, after pulling the scripts commit into a clean VM checkout, run it directly:

```bash
cd /root/aem-guides-dataset-studio
python3 scripts/uac_eval/diagnose_vm_customer_index.py --self-test
python3 scripts/uac_eval/diagnose_vm_customer_index.py
```

For the standalone copy, use:

```bash
python3 /root/diagnose_vm_customer_index.py --self-test
python3 /root/diagnose_vm_customer_index.py
```

Run as the existing root VM operator so `/proc` service information is readable. For a different checkout, add `--repo /absolute/path/to/repo`. The script prints a redacted report and its `REPORT_FILE` path under `/var/tmp/uac-vm-check-.../report.json`. Share that report before proceeding to import.

The diagnostic reads only allowlisted process/config hints, actual open Chroma file paths, and existing loopback status/count APIs on ports 4502 and 8001. It does not open live SQLite, load backend modules, instantiate Chroma, restart services, change configuration, upload the CSV, or request ingestion/reindexing. Its only explicit file write is a private, non-overwriting diagnostic report. Existing server status calls may initialize their own caches. No raw `.env`, tokens, database connection strings, Jira text or ACs are reported. If authentication is required it reports an unavailable/HTTP status; it does not bypass authentication or reuse backend credentials for Chroma.

Matching counts alone are never reported as proof that the index is ready for import. The Git commit/file hashes describe the checkout on disk, not necessarily the revision loaded by the running service. Config hints also do not prove the post-startup Python environment. Open file descriptors help distinguish the embedded backend index from the exposed HTTP Chroma server.

Local validation: standalone self-tests and mocked end-to-end mismatch diagnosis pass, including unavailable-versus-zero counts, redaction, blocked write endpoints, fixed loopback targets, and preservation of existing output files. The operator returned a v1 report confirming the count mismatch. The v2 report adds actual direct-service path/version evidence and a post-status FD rescan; that VM execution is pending. Do not run the import commands below until the storage/embedding audit and consolidation have been completed.

## Resolve the target before writing

1. Deploy the reviewed importer through the normal repository deployment process, preserving VM local edits. Customer-profile and synced skill changes require a separate reviewed deployment; this scripts-only commit does not install those learning changes. The diagnostic and CSV importer do not require that profile to run.
2. Identify the Python executable and environment used by `aem-backend.service`. Do not assume `.venv` and `venv` are interchangeable. Do not print secret environment values or copy credentials into commands. Export the operator's `AEM_STUDIO_TOKEN` using the approved secret mechanism before running the importer if authentication is required; the live check deliberately runs before reading backend `.env`.
3. Verify which Chroma tenant/database/storage the service uses. MCP currently reports 35,927 `jira_qa` chunks while direct Chroma on port 4502 reports 2,847. Resolve this mismatch before any import; do not merely select the endpoint that accepts writes.
4. Use the same embedding model/configuration as that existing collection. Embedding dimensionality alone does not establish model equivalence.
5. Back up both actual Chroma stores and any enabled evidence-graph SQL/outbox before consolidation. Quiesce all index writers for the import. An importer metadata snapshot is not a complete database backup. Complete the reviewed migration to one private HTTP Chroma server first. The backend must remain available for the importer's live read-only identity checks; do not run embedded imports beside it. HTTP clients must use the exact same loopback hostname/port/TLS configuration as the backend. The guard intentionally rejects even hostname aliases with differing target fingerprints.
6. Transfer the CSV to a private VM path. The example below uses `/root/private-uac-import/Hyundai-export.csv`; this path is proposed, not known to exist. Verify SHA-256 equals `4fb5b76cf4e5a7e46aa0d28064de6a4e76a556011a71a2499f6b4708292621df`.

## Commands after those prerequisites

Run from `/root/aem-guides-dataset-studio`, in the activated, verified backend environment. Each line is a separate command. No package installation, reingestion, eval-score change or credential change is required by these commands. The parity helper and diagnostic must be deployed beside the importer; unlike the standalone diagnostic, the importer is no longer a single-file copy.

```bash
cd /root/aem-guides-dataset-studio
python scripts/uac_eval/ingest_customer_csv.py --self-test
python scripts/uac_eval/vm_index_parity.py --self-test
python scripts/uac_eval/ingest_customer_csv.py --csv /root/private-uac-import/Hyundai-export.csv --customer Hyundai --dry-run
```

Expected CSV counts: 44 matching issues, 11 with AC, 33 without. Dry-run does not initialize or validate the index; it cannot prove correct deployment or key duplication state.

After reviewed consolidation, `python scripts/uac_eval/vm_index_parity.py --require-shared` must report matching backend/gateway identities. An old backend with no `index_identity`, embedded mode, UUID mismatch or conflicting direct route is not ready. Exit 0 is only a routing check: it is not a corpus/embedding audit or a maintenance lock.

Keep the held-out issue out of the import while its blind proof is pending:

```bash
python scripts/uac_eval/ingest_customer_csv.py --csv /root/private-uac-import/Hyundai-export.csv --customer Hyundai --exclude-key GUIDES-25663 --apply --reconcile-existing-metadata --snapshot-dir /root/private-uac-import/metadata-snapshots --output /root/private-uac-import/normalized-records.jsonl
```

This selects 43 issues / 10 source ACs. It skips already-indexed issue keys, optionally repairs only customer/component membership metadata, and appends missing issues using the existing schema. Existing documents/vectors/AC/authority are not replaced. The index's existing state determines insertion counts; do NOT expect the direct endpoint's 40/3 split to apply to the backend index. Each vector insert checks three distinct stored texts/vectors in the same embedding batch as the new text; mismatch, unavailable samples, or provider-fallback differences stop it. Do not lower this check's tolerance to force an import. The receipt says sampled compatibility only, not whole-corpus model proof. A blocked batch may follow earlier successful records: inspect receipts/snapshots before retrying.

Reuse the same CSV, exclusion, snapshot directory and output path for an interrupted retry. A differing existing audit file, completed-snapshot mismatch or concurrent change is an error to investigate, not permission to overwrite. Do not delete snapshots to bypass it. Stop on any failure and inspect private receipts before retrying.

If evidence-graph event capture is enabled, a new vector insert can succeed before the existing backend helper fails to enqueue its graph event. A rerun then skips that already-indexed key; it does not automatically repair the missing event. Resolve/reconcile that partial delivery through the existing VM graph mechanism before declaring success. Do not disable graph capture to bypass this check. The metadata-reconciliation retry tests do not prove recovery of this separate new-insert/outbox failure path.

## Verification after import

- Read back inserted keys and reconciled metadata through the same backend/index configuration.
- Restore normal service operation and verify `/health` and `/mcp/health` on port 4502.
- Call the existing `search_jira_history` tool with query `table header`, component `Authoring`, customer `Hyundai`, and held-out key excluded. Record returned keys and retrieval provenance. A successful write receipt alone is insufficient.
- Repeat the import safely and confirm no duplicate keys/chunks and no document/vector rewrites for existing issues.
- Confirm the team skill can resolve the same version of `scripts/uac_eval/customer_profiles.json`. Standalone clients need that packet explicitly or `AEM_STUDIO_REPO` pointing to the deployed repository. The profile remains LEARNED/VALIDATING advisory data.
- Run the held-out UAC only after retrieving the current Jira and its reproduction attachment; exclude its whole key from history even if old chunks already exist. Freeze generation before revealing Human AC.
- After the blind evaluation is frozen, import the remaining held-out issue as a separate, auditable action if desired. Do not describe the 43-issue import as importing all 44.

Never promote mined probes to ACTIVE, approve a pattern, fabricate missing AC text, weaken a gate, or change the VM storage configuration merely to make this verification pass.
