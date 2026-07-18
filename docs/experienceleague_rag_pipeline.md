# Experience League to AEM Guides RAG Pipeline

## Discovery Summary

- Source crawler: `scripts/scrape_experienceleague_to_dita.py`.
- RAG indexer: `backend/app/services/experience_league_index_service.py`.
- Retriever/API evidence path: `backend/app/services/doc_retriever_service.py`, `backend/app/evidence_gateway/rag_adapter.py`, and MCP tools in `mcp_server.py`.
- Vector database: ChromaDB through `backend/app/services/vector_store_service.py`; no parallel vector system is introduced.
- Durable local corpus state: `experienceleague-dita-corpus/queue.json`, `manifest.json`, `crawl_state.json`, `pending_xrefs.json`, `conflicts.json`, `raw_snapshots/`, and `topics/`.

## Safety and Scope

The crawler only accepts canonical URLs under `https://experienceleague.adobe.com/en/docs/experience-manager-guides/` unless `--scope-prefix` is explicitly changed. It removes query strings and fragments, rejects non-Experience League hosts, rejects unsupported file extensions, checks robots.txt, applies a polite delay, restricts redirects back into the allowlisted scope, and never stores cookies or authorization headers.

## Incremental Crawl Behavior

Each successful fetch records ETag, Last-Modified, source content hash, crawl timestamp, source last-updated value, HTTP status, canonical URL, fetched URL, raw snapshot path, parser/converter version, retry/failure details, and generated DITA relpath in `crawl_state.json`.

Use:

```powershell
python scripts\scrape_experienceleague_to_dita.py --resume --refresh-known --limit 100
```

`--refresh-known` conditionally re-checks already converted URLs. HTTP 304 or matching content hash skips reconversion. A failed refresh does not remove the last valid DITA topic or manifest entry.

## Provenance

Converted DITA topics include `<prolog><metadata>` entries for source type, source URL, canonical URL, product, page title, source last-updated value, crawl timestamp, source language, content hash, raw snapshot, HTTP validators, and converter version. Test-plan citations should use `source-url` or `canonical-url`, not the local DITA path.

## RAG Metadata

Experience League RAG chunks now carry `source_url`, `canonical_url`, `source_type`, `corpus`, `content_hash`, `chunk_content_hash`, `chunk_index`, and `parser_version`. Retrieval returns this metadata along with snippets so downstream test-plan generation can cite official Experience League URLs.

## Behavior Knowledge Corpus

Converted DITA topics can be indexed as behavior assertions with:

```powershell
backend\.venv312\Scripts\python.exe scripts\index_dita_behavior_corpus.py
```

This writes `backend/storage/aem_guides_behavior_chunks.json` and does not mutate ChromaDB unless `--upsert-chroma` is provided. The script:

- filters to AEM Guides Experience League URLs by default;
- derives missing source URLs from mirrored DITA paths;
- removes common boilerplate and repairs common mojibake;
- chunks by topic summary, section, list, table, note, and code behavior;
- stores `feature_area`, `evidence_type`, `source_url`, `canonical_url`, `dita_path`, `section`, content hashes, and neighbor chunk IDs.

To review before indexing:

```powershell
backend\.venv312\Scripts\python.exe scripts\index_dita_behavior_corpus.py --sample-output tmp\behavior_sample.json --output tmp\behavior_chunks_review.json
```

To upsert reviewed chunks into the existing `aem_guides` Chroma collection:

```powershell
backend\.venv312\Scripts\python.exe scripts\index_dita_behavior_corpus.py --upsert-chroma
```

## Validation

Run syntax checks:

```powershell
backend\.venv312\Scripts\python.exe -m py_compile scripts\scrape_experienceleague_to_dita.py
backend\.venv312\Scripts\python.exe -m py_compile backend\app\services\experience_league_index_service.py backend\app\services\doc_retriever_service.py
```

Run a small safe crawl:

```powershell
python scripts\scrape_experienceleague_to_dita.py --state-dir tmp\el-smoke --limit 1 --delay 0 --reset
```

Review `tmp\el-smoke\crawl_state.json`, the generated `.dita`, and `raw_snapshots/` before scaling.
