# VM index divergence: root cause and guarded repair

Status: **PARTIAL — local guard/observability changes tested; VM consolidation NOT performed.**

## Evidence supplied by the operator

Diagnostic v1 observed at `2026-09-05T23:13:10.581381+00:00`, checkout
`6c4fb33553931c70038308093dd0c4ccf51222f7`, service PID `285989`.
The report was created at `/var/tmp/uac-vm-check-y0f7ym99/report.json` on the VM.
This document records the supplied report, not a new remote execution.

| Read path | jira_qa | aem_guides | dita_spec |
| --- | ---: | ---: | ---: |
| Nginx 4502 -> MCP | 35,927 | 3,682 | 5,357 |
| Backend 8001 -> MCP | 35,927 | 3,682 | 5,357 |
| Direct Chroma through 4502 `/api/v2/` | 2,847 | not measured | not measured |

The direct Chroma Jira collection UUID is
`756ee538-01ee-49cb-ba8f-2a691b14b59f` in `default_tenant/default_database`.
The old backend status does not report its collection UUID. Counts are Chroma
records/chunks, **not unique Jira counts**; their difference is not a count of
missing tickets.

Backend launch evidence:

- Working directory `/root/aem-guides-dataset-studio/backend`.
- Launcher `/root/aem-guides-dataset-studio/backend/venv/bin/uvicorn` with Python 3.11.
- `STORAGE_PATH=/app/storage`, `USE_AZURE_EMBEDDING=false`; no reported `CHROMA_HOST`.
- No repository `.env`; backend `.env` has the model-path hint
  `models/all-MiniLM-L6-v2`; backend `.env.docker` has no allowlisted overrides.
- No open Chroma SQLite descriptor was observed before status calls. Absence of
  a descriptor does not prove that the backend is remote or that a file is unused.

## Root cause established by code and report

**The system has two independently configured retrieval views. Installing a
shared Chroma server did not connect the backend to that server.** The 4502 MCP
gateway and 8001 backend agree; the discrepancy is with the independently
exposed Chroma route, not evidence that MCP loses 33,080 chunks in transit.

Actual implementation in the reported commit:

1. `backend/app/services/vector_store_service.py::_get_client()` selects an HTTP
   Chroma client only when `CHROMA_HOST` is nonempty. Otherwise it selects embedded
   storage. A failed HTTP connection returns unavailable; it does **not** silently
   retry against local storage.
2. `LocalStorage.__init__()` in `backend/app/storage/local_storage.py` resolves
   `STORAGE_PATH`; `_get_chroma_path()` appends `chroma_db`. The reported backend
   configuration therefore resolves to `/app/storage/chroma_db`.
3. `scripts/setup_shared_chroma.sh` instead defaults its independent server to
   `$REPO_ROOT/backend/storage/chroma_db`. It neither sets backend `CHROMA_HOST`
   nor reconciles the service's `STORAGE_PATH`.
4. `ingest_customer_csv.py::JiraQaAdapter.__init__()` previously loaded only
   `backend/.env`. An interactive shell does not inherit systemd's environment.
   Thus plain `--apply` could select the repository's embedded store instead of
   the backend store. No such import has been executed by this work.

The backend's configured embedded path is strongly supported. The **actual
direct service `--path` remains unobserved** in v1; do not substitute the setup
script's default for an observed VM path. v2 inspects that service and rescans
file descriptors after status requests. On-disk commit/hashes are not proof of
which code an already-running Python process loaded.

## Additional hazards found (not silently changed)

- `app.main` loads root `.env`, backend `.env`, then backend `.env.docker`; CLI,
  offline retrieval and importer have different loader sequences. `setup_vm.py`
  uses **root** `.env.docker` as the systemd environment file, not backend's file.
- `setup_shared_chroma.sh` installs an unpinned global Chroma. Its binary can
  differ from the backend venv version. Do not point it at a live embedded DB.
- `setup_vm.py` rewrites the Nginx site and can remove a manually added direct
  Chroma route. Raw Chroma need not be publicly exposed for team MCP usage.
- The legacy REST/stdio history adapter supports a different request shape from
  `/mcp` `search_jira_history`. An earlier REST probe containing component,
  top_k and exclusion fields did not prove those filters were applied. The
  verification below must use actual MCP, not that legacy REST endpoint.
- Matching embedding dimensions do not prove a matching model. The existing
  encoder can fall back between providers; environment parity alone is not a
  guarantee that all historic vectors use one model.

## Local changes implemented in this repair

- Existing `check_rag_status` has an additive `index_identity` field: cached-client
  storage mode, SHA-256 target fingerprint, tenant/database, collection UUIDs and
  counts. It reports null/unavailable honestly. It does not expose raw storage
  paths, hosts, credentials, documents, vectors or arbitrary collection metadata.
- `get_index_identity()` does not initialize a client or create a collection.
  It cannot attribute a replacement client or changed scope to an old snapshot.
  Existing retrieval and legacy status fields are unchanged.
- `vm_index_parity.py` compares fresh backend and gateway identities. Equal
  counts with different UUIDs, or copied UUIDs on a different configured target,
  fail. Direct-route UUID/count agreement is explicitly **not full content proof**.
- Import now requires the live VM backend to use shared HTTP Chroma. No
  implicit embedded import is allowed. Before each write, target, scope and
  collection UUIDs must remain pinned; current backend/client counts must agree.
  An unavailable or old backend cannot be bypassed with a saved diagnostic.
- New-vector insertion re-embeds three distinct existing texts in the **same
  batch** as the new text and compares their stored vectors. Different dimension,
  same-dimensional mismatch, missing samples, invalid values or changed fallback
  stops the insert. This is a conservative **sampled** compatibility guard, not
  proof of a homogeneous corpus or parity with every backend query embedding.
  Metadata-only reconciliation does not generate vectors.
- Diagnostic v2 adds direct service arguments, post-status FD inspection,
  installed package metadata, direct server version, launcher-config hints and
  stat-only file evidence. No live SQLite connection, Chroma initialization,
  reindex, service restart or configuration mutation is performed by that script.

These changes prevent the unsafe import path and make future divergence visible.
They do **not** move either store or claim that VM parity has already been restored.

## Safe VM consolidation — awaiting actual direct-store evidence

1. Run diagnostic v2, retaining both stores unchanged. Confirm direct service path,
   backend/runtime identities after deploying the additive status change, versions,
   all writers, and the existing embedding provenance. Do not rerun the old shared
   Chroma setup script as a repair.
2. Schedule maintenance and stop **all** writers/DB owners before copying embedded
   storage. Back up both full stores (including SQLite/WAL/vector files) and any
   enabled SQL evidence outbox to separate private destinations. Verify backups.
3. Inventory every collection: scope, UUID, IDs, document/metadata/vector hashes.
   A 2,847-record store may contain unique data absent from the larger one.
4. Create a **new** compatible shared-server target from the verified canonical
   dataset; never overwrite either original. Audit smaller-store-only records.
   Same-ID conflicts, incompatible model provenance or incomplete inventory must
   stop for review. No bulk re-embedding or synthetic reconciliation.
5. Make one private Chroma server the DB owner. Set explicit, consistent backend
   and importer HTTP configuration, resolving higher-priority env-file overrides.
   Avoid embedded and server processes opening the same DB concurrently. Retain
   originals and pre-change service/Nginx configuration for rollback.
6. Verify through backend 8001 MCP, Nginx 4502 MCP, the team endpoint and shipped
   client wrappers: same identities, query filters, exclusions, result keys/order,
   searched/unavailable status and provenance. Check IDs/content manifests, not
   just counts. If direct Chroma remains exposed, it must not serve an old store.
7. Only then import customer precedents and verify idempotency, membership metadata,
   embedding sample checks and actual MCP history retrieval. Keep held-out keys
   excluded during blind evaluation.

No new public port is required. Team members continue to use the authenticated
VM `/mcp` endpoint on port 4502; they do not need local Chroma copies or raw DB
write access.

## Scope and verification limits

Work is in isolated worktree `C:/uac-script-publish`, branch `codex/vm-index-parity`,
based on `6c4fb3355`. Original dirty checkout is not edited or staged.
Skills, evaluation metrics, dashboard, corpora, Human feedback records and UAC
reasoning logic are unchanged. No VM data/config/service changes, import,
reingestion, corpus consolidation or deployment were executed.

The local tests use fakes/temp files, not VM records. A passed identity check
is not permission to migrate, an atomic writer lock or proof that a stale proxy
and a copied database cannot agree temporarily. Writer maintenance and full
inventory remain mandatory.

Validation completed locally:

- `diagnose_vm_customer_index.py --self-test`: PASS.
- `vm_index_parity.py --self-test`: PASS.
- `ingest_customer_csv.py --self-test`: PASS, including same-dimensional encoder
  mismatch, missing/invalid canaries and early identity refusal.
- Focused pytest: **38 passed**, five pre-existing deprecation warnings. Includes
  new identity tests, existing remote MCP gateway tests, collection-record reads,
  evidence paging and evidence-event tests. Executed with `--noconftest` against
  the isolated clean runtime, not the original dirty checkout.
- `git diff --check`: PASS.
- Before publication, the original checkout remains at
  `cf5bc7e5e25599ead63b3303afe406f2e33aa90d` with no staged files.
  Publishing this repair does not deploy it or migrate either VM datastore.
