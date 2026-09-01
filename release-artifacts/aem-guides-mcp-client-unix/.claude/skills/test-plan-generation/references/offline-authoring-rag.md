# Offline Authoring RAG (UACDISCOVER-04)

Use this fallback only when the authoring process cannot reach the running backend or
the live `ask_dita_expert` / `search_jira_history` MCP tools. It reads the existing
local Chroma collections through the backend package; it neither starts a service nor
creates, updates, or re-ingests an index.

## Authority and honesty

- Every result is `source_label=OFFLINE_CHROMA`,
  `authority_class=SUPPORTING_DISCOVERY`, and `non_authoritative=true`.
- A retrieved page or historical Jira creates an `INVESTIGATION_CANDIDATE` only. It
  never authors an AC, confirms current scope, or proves that a behavior applies.
- Offline history always carries `indexed_history_run=false`. It never satisfies the
  manifest requirement for a live `search_jira_history` run and must not be described
  as one.
- An official page discovered offline retains its title and URL so a later verifier
  can inspect the underlying source. The Chroma hit itself does not promote authority.
- Historical acceptance/UAC/Human-feedback chunks are excluded from offline history
  discovery. The current target Jira key is also excluded before candidates are made.

## Runtime path

`scripts/offline_retrieval.py` locates an ancestor repository checkout (or one rooted
at the current working directory) that contains `backend/app/services`. It then reuses:

- `embedding_service.embed_query`
- `vector_store_service.query_collection`
- `CHROMA_COLLECTION_AEM_GUIDES`
- `CHROMA_COLLECTION_JIRA_QA`

The NumPy embedding is converted to a plain list before it crosses the vector-store
boundary. Query text and result counts are bounded. Product-documentation results are
deduplicated by source URL; history results are deduplicated by Jira key and filtered
to the requested canonical component using the backend's component aliases.

If the package, Chroma runtime, collection, embedding, or query is unavailable, the
helper returns `[]` and records a sanitized reason through `retrieval_status()`. It
does not echo credentials, fabricate a result, or make canonical generation fail.

## Dimension-synthesizer behavior

`RAG_NEIGHBORHOOD` runs when recorded RAG probes or current behavior/evidence text can
form a query. It uses a bounded base query plus optional query expansions derived from
matched, Human-approved `FEATURE_MAP` entries (`feature + shared_flows`). The feature
map supplies search vocabulary only; a candidate is emitted only when Chroma returns a
real product-documentation row. This lets a shared-flow change discover adjacent
native behavior without a Jira-specific or feature-specific production branch.

When no live history run is recorded, `HISTORY_NEIGHBORHOOD` may query `jira_qa` with
the current behavior and component. Returned tickets remain recurring-defect leads for
investigation. The synthesizer never mutates the input manifest and never changes
`indexed_history_run` to `true`.

Unrepresented offline candidates appear only through the existing non-blocking
`REVIEW DISCOVERY:` note. The author must verify applicability and then cover, reject,
or expose the behavior as an Open Question using the normal evidence pipeline.

## Degraded mode

When local collections are absent, both offline generators record their gap and emit
no offline candidate. Existing recorded RAG-probe signal discovery remains available,
and a recorded live history run still takes precedence over the offline path.

