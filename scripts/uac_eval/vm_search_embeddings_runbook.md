# VM read-only search / embedding diagnostic

Run this **after** the routing-only repair passes. It is a diagnostic, not a
deployment, corpus merger, customer import or authorization to resume writers.
The implementation is `verify_vm_search_embeddings.py`; tests use only fake HTTP
responses and in-memory data. No pip/npm installation is required.

## Exact scope

The script uses the VM's existing numeric loopback endpoints:

1. `/mcp` on ports 8001 and 4502: `check_rag_status`, before and after the probe.
   Require the same REMOTE target fingerprint, tenant/database, core collection
   UUIDs and counts. Availability is retained as a boolean, not model identity.
2. Chroma port 8000: get/count the existing `jira_qa`, `aem_guides`, and
   `dita_spec` collections and read up to three existing embeddings per collection.
   Validate finite, nonzero vectors and consistent dimensions within each sample.
   No collection creation, query-text embedding, writes or local database opens.
3. `/mcp` on ports 8001 and 4502: `search_jira_history`, with three fixed,
   non-sensitive queries about table editing, map-reference titles and publishing.
   Each request uses `top_k=3`, without customer/component filters. It checks the
   real `jira-history-search-v2` response, requested query fingerprint, index count,
   returned references/documents and the existing numerical retrieval fields.
4. Recheck direct collection identities/counts and MCP routing after searches.

This is a **Jira-history text-search smoke test**. It does not test product/DITA
documentation text search, the legacy REST bridge, a teammate's actual network
connection, their authentication, or a complete UAC-generation run. The existing
routing repair separately checked inventories of all seven collections and
sampled stored-vector queries; its MCP identity check covers three core collections.

## Safety and observable limits

- No import, merge, reindex, add/upsert/delete, model reset, synthesis/generation,
  service command, config edit, backend-module import or local Chroma client.
- The script prints a redacted JSON report to stdout. It does not read the private
  routing journal, `.env`, process environment files, backups or corpus files, and
  does not write a report file. Keep the current routing directory and archives.
- Only `AEM_STUDIO_TOKEN` is optionally read from the invoking environment. It is
  sent only to backend/MCP routes, never to Chroma. No token command-line option,
  auth bypass, arbitrary host/URL, proxy inheritance or redirect following exists.
- HTTP is limited to `127.0.0.1`, inside the existing VM. This is not permission
  to send credentials over an unencrypted public/LAN endpoint.
- **Read-only means no index/config/service mutation requests.** Ordinary backend
  retrieval may update in-memory embedding caches/recent-result history and logs.
  `check_rag_status` and search can also lazily initialize/download a model on a
  cold worker or use the configured external embedding fallback. This probe does
  not prevent those existing effects or assert that the same worker remained warm.
  It never sends stored corpus text for re-embedding; only its fixed generic
  search queries can reach the configured encoder. Do not run if even ordinary
  runtime embedding/cache/network effects are prohibited in your maintenance window.
- The current encoder ID and raw query vector are **not exposed** by the reviewed
  read APIs. `embedding_available=true`, a dimension of 384 and a returned hit do
  not prove that the current encoder equals the historical ingestion model.
  A text-only query cache can also return a previously encoded vector. Accordingly
  model parity and fresh encoding are always reported as unproven.
- Backend and gateway searches hit a stateful ranking process. Recent-result
  penalties can change rankings even for consecutive identical queries. Reference
  overlap is informational; this script does not demand identical order/scores.
- `searched_jira_qa=true` represents prerequisites; downstream encoder/query errors
  may still degrade to an empty result. Empty results are inconclusive, never proof
  of a missing ticket or a compatible model. No matching Human oracle is supplied,
  so relevance/recall and correctness of the returned UACs are not judged.
- Reports retain validated booleans, counters, UUIDs, fingerprints, dimensions and
  scores. Documents, titles, raw keys, metadata, vectors, auth and raw error text
  are not printed. No newly observed information becomes Human-approved learning.
- At most 25 fixed HTTP operations are attempted. Socket operations use a timeout
  of at most 45 seconds; a 360-second elapsed budget is checked before/after each
  response. No retries. These are not a hard deadline for a slow trickling HTTP
  response, nor cancellation of work already executing inside the backend.

## Commands

Once these three files and the existing `vm_chroma_routing_checks.py` helper have
been published and pulled, run from `/root/aem-guides-dataset-studio`:

```bash
python3 -I -B scripts/uac_eval/verify_vm_search_embeddings.py --self-test || echo "STOP: self-tests failed"
```

Only after the self-tests pass, with team traffic/imports/writers still paused:

```bash
if python3 -I -B scripts/uac_eval/verify_vm_search_embeddings.py; then
  echo "Query smoke passed ONLY; share the redacted report"
else
  echo "STOP or INCONCLUSIVE: share the redacted report; do not import or resume writers"
fi
```

The `if`/`||` wrappers avoid closing a shell that already has `set -e`. Use the
existing approved environment mechanism if a backend token is required; never
paste the token into a command argument or shared output. The script uses only
stdlib and does not need the Chroma/embedding venv to run.

## Reading the result

| Status | Exit | Meaning |
| --- | --- | --- |
| `PASS_QUERY_SMOKE_ONLY` | 0 | All six text requests returned validated results, availability was reported, and core routing identities/counts remained stable. |
| `PARTIAL_QUERY_SMOKE` | 2 | At least one query was empty/unavailable or availability was not reported true. Inspect each probe/route; do not assume a missing issue or model failure. |
| `BLOCKED` | 1 | Transport/auth/schema, vector-sample, routing-drift or another diagnostic failure. The report gives a fixed reason, phase and endpoint without raw error contents. |

Every outcome keeps `model_parity_proven`, `fresh_embedding_verified`,
`full_live_payload_equality_verified`, `ranking_parity_proven`,
`team_client_authentication_verified`, `import_authorized`, and
`resume_writers_authorized` false. A green smoke test alone is **not** a release
gate or an embedding-canary pass. No threshold/waiver flag bypasses failures.

Share only the printed report. Before approving new vector writes, separately
establish compatibility of the exact write encoder with stored text/vector
canaries and the live query encoder. That requires an approved observation
mechanism not available in these existing read APIs; do not substitute an importer
run, model reset, availability flag or same-dimensional model as proof.

## Audited repository contracts

Audited at `c1b06887c76a26d593e6dd027594a12c0b8b8f35`:

- `backend/app/api/routes/remote_mcp.py`: `_check_rag_status`, `_search_jira_history`,
  `_rpc_tool_result` (no `ask_dita_expert` or admin embedding tools are invoked).
- `backend/app/services/jira_history_search_service.py`: `search_jira_history_evidence`.
- `backend/app/services/jira_qa_retrieval_service.py`: `semantic_search_jira_qa`.
- `backend/app/services/jira_retrieval_service.py`: `retrieve_similar_jiras`,
  `retrieved_to_legacy_hit` (scores and recent-result penalties).
- `backend/app/services/embedding_service.py`: `is_embedding_available`,
  `_load_model`, `embed_query`, `embed_texts` (lazy load and configured fallback).
- `backend/app/services/jira_qa_copilot_cache.py`: text-only in-process vector cache.
- `backend/app/services/vector_store_service.py`: identity and existing-collection reads.

The report reflects the live response contract, not proof of the deployed code
commit or the running model artifact hash. Future API changes must be reviewed;
do not loosen schema checks solely to obtain a green status.
