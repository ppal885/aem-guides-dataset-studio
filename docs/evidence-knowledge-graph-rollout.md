# Evidence Knowledge Graph VM Rollout

This rollout targets the existing SQLite, systemd, and Nginx deployment. It does not use Docker or Neo4j.

## 1. Update and preflight

```bash
cd /root/aem-guides-dataset-studio
git fetch origin
git switch main
git pull --ff-only origin main
git status --short
(cd backend && .venv/bin/python -m alembic -c alembic.ini heads)
```

Do not continue with an unresolved merge, cherry-pick, or dirty tracked file. The evidence-graph migration must report `evidence_graph_phase_b` as the single head.

## 2. Keep graph reads disabled

Set these values in `backend/.env` before migration and initial build:

```dotenv
EVIDENCE_GRAPH_ENABLED=false
EVIDENCE_GRAPH_DEFAULT_TENANT_ID=kone
EVIDENCE_GRAPH_TEST_PLAN_MODE=shadow
EVIDENCE_GRAPH_QUERY_CACHE_TTL_SECONDS=60
EVIDENCE_GRAPH_QUERY_CACHE_MAX_ENTRIES=256
EVIDENCE_GRAPH_STATUS_CACHE_TTL_SECONDS=5
EVIDENCE_GRAPH_QUERY_BUDGET_MS=1500
EVIDENCE_GRAPH_AUDIT_HASH_KEY=<long-random-secret>
EVIDENCE_GRAPH_INTEGRITY_KEY=<different-long-random-secret>
EVIDENCE_GRAPH_INTEGRITY_KEY_ID=2026-08-primary
EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=false
EVIDENCE_GRAPH_SYNC_ENABLED=false
EVIDENCE_GRAPH_RECONCILE_ENABLED=true
EVIDENCE_GRAPH_BATCH_SIZE=500
EVIDENCE_GRAPH_REBUILD_MAX_SECONDS=1200
EVIDENCE_GRAPH_REBUILD_MAX_MEMORY_MB=1536
```

## 3. Back up SQLite and ChromaDB

The backup command stops `aem-backend.service`, creates a SQLite online-backup image, archives ChromaDB, writes checksums and a manifest, and restarts the service even if backup creation fails.

```bash
sudo bash scripts/backup_evidence_graph_vm.sh --manage-service
```

Verify the newest backup before continuing:

```bash
BACKUP_DIR="$(find /root/rag-backups -maxdepth 1 -type d -name 'evidence-graph-*' -printf '%T@ %p\n' | sort -nr | head -1 | cut -d' ' -f2-)"
cat "$BACKUP_DIR/manifest.json"
(cd "$BACKUP_DIR" && sha256sum --check SHA256SUMS)
```

## 4. Apply the database migration

```bash
cd /root/aem-guides-dataset-studio
(cd backend && .venv/bin/python -m alembic -c alembic.ini upgrade head)
(cd backend && .venv/bin/python -m alembic -c alembic.ini current)
```

## 5. Audit a dry-run build

The dry run scans ChromaDB in batches and must scan exactly the collection count. A partial page, retry exhaustion, dangling edge, missing assertion, unsupported relationship, redaction failure, runtime over 20 minutes, or peak memory over 1.5 GB returns nonzero and prevents promotion. Partial `--sources` selections are audit-only; an applied build is refused unless `jira`, `docs`, and `dita` are all included, preventing accidental active-generation data loss.

```bash
bash scripts/build_evidence_graph_vm.sh --dry-run --batch-size 500
```

Do not run `--apply` unless the JSON reports `"valid": true` and complete source scans.

## 6. Build and promote

```bash
bash scripts/build_evidence_graph_vm.sh --apply --batch-size 500
bash scripts/audit_evidence_graph_vm.sh
PYTHONPATH=backend backend/.venv/bin/python scripts/evidence_graph_admin.py status
```

The apply command builds a blue/green generation and promotes it only after all audits pass. The prior successful generation is retained for content rollback.
Promotion stores a deterministic SHA-256 integrity manifest and, when `EVIDENCE_GRAPH_INTEGRITY_KEY` is configured, an external-key HMAC seal. Later audits and rollback refuse a generation whose nodes, edges, or assertions were modified after promotion. Changing the integrity key requires a full rebuild with a new key ID. Phase B uses graph schema `evidence-graph-v2`; an older active generation remains queryable only as degraded and must be rebuilt before enabling augmentation.

## 7. Enable queries and synchronization

Update `backend/.env`:

```dotenv
EVIDENCE_GRAPH_ENABLED=true
EVIDENCE_GRAPH_DEFAULT_TENANT_ID=kone
EVIDENCE_GRAPH_TEST_PLAN_MODE=shadow
EVIDENCE_GRAPH_QUERY_CACHE_TTL_SECONDS=60
EVIDENCE_GRAPH_QUERY_CACHE_MAX_ENTRIES=256
EVIDENCE_GRAPH_STATUS_CACHE_TTL_SECONDS=5
EVIDENCE_GRAPH_QUERY_BUDGET_MS=1500
EVIDENCE_GRAPH_AUDIT_HASH_KEY=<same-long-random-secret>
EVIDENCE_GRAPH_INTEGRITY_KEY=<same-integrity-secret-used-for-build>
EVIDENCE_GRAPH_INTEGRITY_KEY_ID=2026-08-primary
EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED=true
EVIDENCE_GRAPH_SYNC_ENABLED=true
EVIDENCE_GRAPH_SYNC_SCHEDULE=*/5 * * * *
EVIDENCE_GRAPH_SYNC_MAX_EVENTS=500
EVIDENCE_GRAPH_SYNC_MAX_RETRIES=5
EVIDENCE_GRAPH_RECONCILE_ENABLED=true
EVIDENCE_GRAPH_RECONCILE_SCHEDULE=30 2 * * *
EVIDENCE_GRAPH_BATCH_SIZE=500
EVIDENCE_GRAPH_REBUILD_MAX_SECONDS=1200
EVIDENCE_GRAPH_REBUILD_MAX_MEMORY_MB=1536
```

Restart and verify the existing service:

```bash
sudo systemctl restart aem-backend.service
sleep 10
sudo systemctl --no-pager --full status aem-backend.service
sudo journalctl -u aem-backend.service -n 100 --no-pager
```

## 8. Verify through Nginx on port 4502

Use the public MCP endpoint, not the obsolete direct RAG-status route:

```bash
curl -fsS -H 'Authorization: Bearer dev-bypass' \
  http://10.42.46.78:4502/mcp | python3 -m json.tool

GRAPH_SMOKE_JIRA_KEY=GUIDES-12345 \
GRAPH_SMOKE_CUSTOMER='Verified Customer Name' \
bash scripts/smoke_evidence_graph_mcp_vm.sh
```

Replace the Jira key and customer with a real indexed same-customer pair. The smoke test verifies `tools/list`, graph status, a documented-behaviour query, a same-customer query, a cross-customer same-mechanism query, leaf citations, and redaction-safe responses.

## 9. Verify schedules and failure semantics

The backend scheduler drains source events every five minutes and runs full reconciliation at 02:30. The existing scheduled reindex also invokes graph synchronization and exits nonzero on any partial or failed run.

```bash
bash scripts/sync_evidence_graph_vm.sh --max-events 500 --max-retries 5 --batch-size 500
bash scripts/reconcile_evidence_graph_vm.sh --dry-run --batch-size 500
bash scripts/scheduled_reindex.sh
PYTHONPATH=backend backend/.venv/bin/python scripts/evidence_graph_admin.py events --status failed
```

Do not treat a Jira HTTP 403 as loss of historical corpus data. It marks live Jira validation and freshness as degraded; indexed historical evidence remains queryable.

Failed source events are dead letters and keep scheduled synchronization nonzero. Inspect them before replaying. Replay selected records rather than the entire queue whenever possible:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/evidence_graph_admin.py events --status failed --limit 100
bash scripts/replay_evidence_graph_events_vm.sh --event-id '<event-id>'
bash scripts/sync_evidence_graph_vm.sh --max-events 500 --max-retries 5 --batch-size 500
```

The incremental worker renews its database lease after cloning, while applying event batches, before audit, and before promotion. Lease loss fails the run and never changes the active generation.

## 10. Shadow acceptance before augmentation

Keep `EVIDENCE_GRAPH_TEST_PLAN_MODE=shadow` until the status shows all of the following for the agreed observation window:

- active schema is `evidence-graph-v2` and integrity verification passes;
- no failed events and synchronization lag stays below 15 minutes;
- query p95 stays at or below 1500 ms;
- tenant/redaction and same-mechanism audits have no violations;
- sampled test plans are byte-equivalent in plan-driving inputs with graph enabled versus graph disabled.

Only then set `EVIDENCE_GRAPH_TEST_PLAN_MODE=augment` and restart the service. Roll back immediately to `shadow` if plan content, scoring, citations, repository scope, or automation verdicts change without an independently valid leaf source.

## 11. Content rollback

Rollback only switches the active generation pointer; it does not downgrade the database schema:

```bash
PYTHONPATH=backend backend/.venv/bin/python scripts/evidence_graph_admin.py rollback
bash scripts/audit_evidence_graph_vm.sh
sudo systemctl restart aem-backend.service
```

If the service itself must be restored, disable graph reads in `backend/.env`, restart the service, and restore the verified SQLite and Chroma artifacts according to the normal VM recovery procedure.
