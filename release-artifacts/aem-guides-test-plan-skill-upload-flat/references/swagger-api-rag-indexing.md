# Swagger / OpenAPI RAG indexing (AEM Guides REST tickets)

Use when a Jira ticket is **REST/API-scoped** (`/bin/guides/v1/...`) and Experience League has **no** dedicated API page. Indexed Swagger becomes the **contract oracle** for EB bullets, AC oracles, and negative cases.

## When to run

| Signal | Action |
| --- | --- |
| Ticket mentions servlet path, curl, `AssetStatus*`, Dxml API | Index Assets Swagger (or relevant spec) |
| `learned_behavior_evidence` returns only generic EL Assets pages | Index Swagger before marking plan Review-ready |
| User provides Author Swagger URL (`api-docs/index.html?urls.primaryName=...`) | Fetch YAML, index both corpora |
| Spec already indexed for same Author + API version | Skip re-index unless YAML changed |

## Two corpora (both required)

| Corpus | Script | Output JSON | Chunk shape |
| --- | --- | --- | --- |
| **Doc index** (contract text) | `backend/tmp/index_guides_assets_api.py` | `backend/storage/manual_aem_guides_doc_chunks.json` | 1 chunk per path + overview + key DTOs |
| **Learning corpus** (QA oracles) | `backend/tmp/index_guides_assets_learning_chunks.py` | `backend/storage/aem_guides_enriched_behavior_chunks.json` | 3 chunks per endpoint: summary, evidence excerpt, QA oracle pack |

Both upsert into Chroma collection `aem_guides`. Retriever host filter must include **`adobeaemcloud.com`** (already set in `guides_test_plan_generator_service.py`).

## Procedure

### 1. Fetch OpenAPI YAML from Author

Default Assets spec URL pattern:

```text
https://{author-host}/libs/fmdita/clientlibs/api-docs/docs/guides-assets.yaml
```

Save snapshot under ticket test-data or shared swagger folder:

```text
docs/qa/test-data/swagger/guides-baseline.yaml
docs/qa/test-data/GUIDES-49065/guides-assets.yaml
```

```powershell
cd C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend
python tmp/index_guides_assets_api.py && python tmp/index_guides_assets_learning_chunks.py
python tmp/index_guides_baseline_api.py && python tmp/index_guides_baseline_learning_chunks.py
python tmp/index_guides_publishing_api.py && python tmp/index_guides_publishing_learning_chunks.py
python tmp/index_guides_reports_api.py && python tmp/index_guides_reports_learning_chunks.py
```

| Spec | Paths | Doc chunks | Learning chunks |
| --- | --- | --- | --- |
| guides-assets.yaml | 17 | 19 | 63 |
| guides-baseline.yaml | 9 | 11 | 34 |
| guides-publishing.yaml | 3 | 5 | 14 |
| guides-reports.yaml | 21 | 23 | 72 |

Each spec merges independently by yaml file name (no overwrite across specs).

### 2. Point indexers at the snapshot

Both scripts default to:

```text
C:/starling/docs/qa/test-data/GUIDES-49065/guides-assets.yaml
```

Edit `YAML_PATH` at top of each script if the Jira key differs.

### 3. Run indexers (backend Python — not MCP stdio)

```powershell
cd C:\Users\prashantp\Videos\aem-guides-dataset-studio\backend
python tmp/index_guides_assets_api.py
python tmp/index_guides_assets_learning_chunks.py
```

Expected output (Assets API v2026.9.0, 17 paths):

- Doc index: **19** records (17 paths + overview + Asset Status DTOs)
- Learning corpus: **59** new enriched chunks (3 × 17 + overview + 7 DTOs)

### 4. Verify corpus + retrieval

```powershell
# MCP or backend
show_mcp_rag_corpus_status
```

Spot-check learned behavior (backend):

```python
from app.services.guides_test_plan_generator_service import _retrieve_learned_behavior_evidence
r = _retrieve_learned_behavior_evidence(
    "POST /bin/guides/v1/assets/status paths jobId", k=8
)
# Expect top hit: "Assets API — /bin/guides/v1/assets/status" (enriched_learned_behavior)
```

### 5. Full RAG packet (test plan generation)

For complete `learned_behavior_evidence`, run **`guides_test_plan_generator` with full backend mode** (`mcp_fast_mode=false`). MCP stdio fast mode **skips** learned-behavior retrieval to avoid timeout — plans must stay **Draft** unless Swagger evidence is cited from a prior full run or manual index verify.

## Test plan Key evidence (inline wording)

When Swagger is indexed, add **both** bullets in section 1 (replace generic “no REST doc” gap):

```markdown
- **Swagger doc RAG (manual corpus):** N OpenAPI doc chunks in `manual_aem_guides_doc_chunks.json` + Chroma; spec snapshot `docs/qa/test-data/{JIRA}/guides-assets.yaml`.
- **Learned-behavior RAG (Swagger vX.Y.Z):** enriched chunks from Author `guides-assets.yaml` — per-endpoint summary + evidence + QA oracle; includes `{ticket endpoint}` and contract DTOs.
```

Update **Draft gates**: Swagger contract indexed does **not** replace Author UAC — runtime poll/auth still required.

## Per-endpoint learning chunk contents

For each `/bin/guides/v1/...` path:

1. **Learned behavior summary** — `enriched_learned_behavior`
2. **Evidence excerpt** — parameters, responses, DTO fields
3. **QA oracle pack** — HTTP oracles, auth 401, negative/risk cases

Ticket-specific risks (e.g. comma in `paths[]`) belong in oracle pack + blast-radius table — cite Swagger chunk as contract source, Jira/code as bug source.

## Assets API scope map (17 paths)

All under tag **Assets** or **Assets Processing** in Swagger UI:

- `/bin/guides/v1/asset` (+ import, list, lock, update, validatexml, version/*)
- `/bin/guides/v1/assets/process` (+ status)
- `/bin/guides/v1/assets/properties`
- `/bin/guides/v1/assets/status` — async job poll; comma-path encoding is a known QA oracle

UI entry: `{author}/libs/fmdita/clientlibs/api-docs/index.html?urls.primaryName=Assets`

## DO / DON'T

**DO:** Save YAML snapshot in starling test-data; run both indexers; verify ticket endpoint ranks in retrieval; cite spec version in plan.

**DON'T:** Treat ChatGPT/public API docs as contract; skip learning corpus (doc-only misses QA oracles); mark Review-ready on MCP fast mode without Swagger evidence; use Experience League generic “Assets view” pages as REST contract.
