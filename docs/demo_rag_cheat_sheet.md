# Demo cheat sheet: RAG in the AEM Guides test-plan generator

Quick answers for live demo questions. Facts below come from the backend code
(`backend/app/services/`, `backend/app/rag/`). Technical terms stay in English.

## What is RAG here?

The LLM does not know our AEM Guides product history. Before generating a test
plan we first retrieve evidence (docs, old Jiras, DITA spec, code), then give
that evidence to the LLM so the answer is grounded. Retrieve first, then
generate.

## Vector database

ChromaDB, persistent on disk. One collection per knowledge type:

| Collection       | Contents                          |
|------------------|-----------------------------------|
| `aem_guides`     | Product documentation             |
| `dita_spec`      | DITA specification chunks         |
| `jira_qa`        | Historical Jira issues            |
| `dita_ot_github` | DITA-OT source from GitHub        |
| `learned_qa`     | Learned behaviour from QA reviews |
| `docker_docs`    | Docker documentation              |

Source: `backend/app/services/vector_store_service.py`

## Embedding model

- Default: `all-MiniLM-L6-v2` (sentence-transformers), 384 dimensions, runs locally.
- Optional: locally fine-tuned DITA model via `DITA_EMBEDDING_MODEL_PATH`.
- Optional: Azure OpenAI `text-embedding-ada-002` (1536 dimensions) via `USE_AZURE_EMBEDDING`.
- Embeddings from different models are never mixed in one index, even when
  vector sizes match.

Source: `backend/app/services/embedding_service.py`

## Hybrid search (not vector-only)

Final score for historical Jiras:

| Signal                                                       | Weight |
|--------------------------------------------------------------|--------|
| Vector similarity                                            | 0.45   |
| Metadata match (domain, DITA entities, outputs, customer)    | 0.35   |
| Keyword overlap                                              | 0.20   |

Minimum thresholds: vector 0.50, metadata 0.18, at least 1 overlapping
entity. Vector-only matches with no metadata overlap get a penalty (0.14).
Results are deduped by Jira key, and diversified when the query is broad.

Source: `backend/app/services/jira_retrieval_service.py`

## Chunking

Jiras are chunked by meaning, not fixed-size windows. Sections become
separate chunks: summary, root cause, comments summary, QA notes, automation
notes, resolution, linked issue patterns. Each chunk is capped at 4,000
characters. DITA spec content has its own curated chunking.

Source: `backend/app/rag/chunking.py`, `backend/app/services/jira_chunking_service.py`

## Reranking

- Jira hits: boost for exact customer, feature, environment and issue-type
  matches, up to +0.2 on the score.
- DITA examples: a separate rerank pushes real XML snippets above prose.

Source: `backend/app/rag/reranker.py`, `backend/app/services/retrieval_context_assembly_service.py`

## Corrective RAG (weak results)

Retrieved results are graded on term coverage, issue coverage, source
diversity, duplicate ratio and off-topic ratio. If evidence is weak, the
query is rewritten (alias expansion, clause splitting, optional LLM rewrite)
and retrieval runs again. Web search through Tavily is the last fallback.

Source: `backend/app/services/corrective_rag_service.py`

## Sources used for one test plan

For a single Jira key the pipeline collects, 8 items per source by default:

1. Experience League / AEM docs (non-AEM docs filtered out)
2. Learned behaviour from past QA
3. DITA spec chunks
4. DITA-OT publishing context
5. Similar historical Jiras
6. Evidence graph links
7. Repository code evidence from product and automation clones

Source: `backend/app/services/guides_test_plan_generator_service.py`

## Evidence graph

Not Neo4j. Stored in our own database tables through SQLAlchemy. Links
Jiras, features, customers and fixes; syncs incrementally. Customer details
are not shared across customers unless explicitly allowed.

Source: `backend/app/services/evidence_graph_sync_service.py`

## Stopping hallucination

- Every claim needs evidence; a claim verifier checks this.
- Output validators and guardrails run on the generated plan.
- AI output and historical similarity are supporting discovery only.
  Human/product decisions are the acceptance authority.

## Measuring quality

Evaluation runs are saved as JSON and shown on a read-only dashboard
(`scripts/uac_eval/dashboard.html`). The dashboard only reads saved
results; it never recalculates or invents metrics.

## Same behaviour everywhere

The skill, CLI (`scripts/run_test_plan_pipeline.py`), REST
(`POST /api/v1/test-plans/pipeline`) and MCP tool
(`guides_test_plan_generator`) all call the same Python pipeline
(`backend/app/services/test_plan_pipeline_service.py`).
