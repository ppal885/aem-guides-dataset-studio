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

---

# Part 2: deeper answers

## Stopping hallucination (detailed)

Five checkpoints, before, during and after generation.

1. **Evidence authority before generation.** Each retrieved chunk carries an
   authority score by source: tenant-approved context 1.0, approved examples
   0.95, AEM Guides docs 0.78, DITA spec 0.72, web results (Tavily) 0.2.
   Weak hits are already filtered by the hybrid thresholds; weak sets trigger
   Corrective RAG instead of letting the LLM guess.
2. **Citation IDs.** Evidence is packed as `[n] label + text`; output tracks
   `citation_ids` and a separate `unsupported_points` list.
3. **Claim verifier.** Every scenario, risk driver and clarification becomes a
   claim checked for an anchor (real entity/output/customer from the ticket or
   similar Jiras), word overlap with evidence, and strong-language. Strong
   assertion with no overlap is dropped; anchor but weak overlap is
   downgraded; overlap-only is kept with a warning. Recorded in
   `dropped_claims`, `downgraded_claims`, `unsupported_claims`.
4. **Guardrails.** Blocked outright: customer-impact claims with no customer
   in the ticket, "regressed before" with no similar Jira retrieved,
   secret/credential patterns, generic filler phrases.
5. **Output validator.** Each scenario needs title, why, non-empty evidence,
   test layer, priority; one LLM repair pass, then strict validation again.
6. **Humans last.** Output is a recommendation; human/product decision is the
   acceptance authority. Reviewer corrections go through QE approval before
   becoming shared learning.

Sources: `backend/app/services/grounding_service.py`,
`backend/services/uac/claim_verifier.py`, `uac_guardrails.py`,
`uac_output_validator.py`.

## What is an anchor?

A concrete noun from the real evidence: Jira key, DITA entities, affected
outputs (PDF, HTML5...), components, customer names, labels, features, risk
tags, symptoms, plus significant words from similar Jiras' titles. The anchor
check asks whether a generated claim mentions at least one of them.

Plain example: ticket says "Export to PDF button does nothing when the
document name has `&` or `#`". Anchors: export, pdf, button, special
characters, document name.
- "Verify Export to PDF works when the name contains `&`" → anchored.
- "Verify the application works as expected" → no anchor, flagged.
- "This also breaks Export to Word for all customers" → wrong output, no
  customer evidence, blocked.

Analogy: an essay about the Taj Mahal that never mentions Taj Mahal, Agra or
Shah Jahan is off-topic however well written.

Source: `backend/app/services/uac_evidence_gate.py:117-225`.

## QA reasoning applied (in order)

1. Lifecycle stage: pre-development UAC, implementation review, or post-fix
   validation. Evidence requirements change with the stage.
2. Scope: Jira description, comments, attachments are the contract; discovery
   can widen, never shrink.
3. Discovery-first dimension sweep before writing: entry points, consumers,
   write/read parity, UI surface proof, config branches, locale. Every
   dimension dispositioned (COVERED_BY_AC / OPEN_QUESTION / OUT_OF_SCOPE /
   NOT_APPLICABLE) or the gate fails.
4. Miss-probe library: 30 probes encoding real past reviewer misses.
5. Behavioural coverage expansion, triggered by requirement shape (displays,
   exports, orders, filters, persists, moves, changes state, config).
6. Question-based reasoning: planner (budget 12) → research router →
   resolver with a terminal state per question.
7. Evidence sufficiency: SUFFICIENT / PARTIAL / INSUFFICIENT / CONFLICTED;
   NOT_FOUND is never proof of the opposite; wrong-version evidence stays
   insufficient.
8. Coverage reasoner: P0 proves the contract, P1 related regression,
   SUPPORTING exploration, EXCLUDED never reaches the writer. Each decision
   traces to a question or evidence ID.
9. Three-perspective convergence: PM intent, developer reality, QE
   observables. Missing product decisions become open questions.
10. Root-cause / fix-driven authoring when a PR or diff exists.
11. Specialised contracts: security, localisation, upgrade/migration,
    operational incidents, config settings with Cloud vs on-prem defaults.
12. Reproduction-dimension matrix for bugs (version, deployment, output type,
    preset, engine, locale, role, browser, dataset size, concurrency...).
13. Writing: `Action:` / `Expected:` in plain English, prefixed with AC IDs;
    every AC gets a scenario; nothing added beyond ACs or accepted evidence.
14. Readiness: draft vs review-ready; open questions as `OQ-##` with
    `QA impact:`.

Sources: `.codex/skills/test-plan-generation/SKILL.md` (Phases 0–9),
`references/reasoning-pipeline-phases.md`, `coverage-reasoner.md`,
`question-based-reasoning.md`, `evidence-sufficiency.md`,
`data/miss_probes.json`.

## Knowledge base updates

No retraining; the LLM is not trained on our data. Updating knowledge means
updating the index, incrementally.
- Jira: synced by last-updated time, upserted by key, no duplicates.
- SQL is the source of truth, Chroma the search copy; a reconciliation job
  rebuilds missing Chroma rows from SQL (dry-run supported).
- Docs and DITA spec: re-indexed per collection; content hashes avoid
  duplicates; a corpus audit reports gaps and versions.
- Evidence graph: event-based; a worker applies events into a new generation,
  audits it, then promotes it. Old generation stays live until then.
- Human learning: durable outbox worker into `learned_qa`, with drain/retry.
- Next request uses the new data immediately. Only an embedding-model change
  needs a full re-index (vectors from different models are never mixed).

Sources: `backend/app/services/jira_index_service.py`,
`jira_rag_reconciliation_service.py`, `evidence_graph_sync_service.py`,
`knowledge_corpus_audit_service.py`.

## Experience League docs changed

We crawl, not own. Allow-listed URLs only. Chunk IDs are derived from URL +
chunk number, so a re-crawl overwrites in place; untouched pages are kept.
Each chunk stores `content_hash`, `chunk_content_hash`, `parser_version`.
Triggered by admin API `POST /crawl-aem-guides` (status at `/crawl-status`),
targeted VM scripts (`scripts/upsert_*_vm.sh`), or the in-app scheduler when
enabled. Versions (Cloud Service vs 6.5, release tags) are kept side by side;
retrieval rules decide which applies. Non-AEM pages are filtered out of test
plan evidence.

Source: `backend/app/services/experience_league_index_service.py`.

## Past history check

Two searches run together: semantic search over indexed Jiras (`jira_qa`) and
deterministic Jira history searches with exact probes (error text, API path,
config key, UI label, DITA element, version). Hybrid score 45/35/20 with
thresholds; dedupe by key; diversity for broad queries. Each match gets a
plain-English reason naming concrete overlap. Selection is by same defect
mechanism, not same feature area; four sharp matches beat five with padding;
different surface is excluded by default. Safety: history is discovery, not
authority (AUTHORITATIVE_HISTORY only with explicit basis; otherwise
SUPPORTING_PRECEDENT, DISCOVERY_ONLY, NOT_APPLICABLE, CONFLICTING_HISTORY).
Old actual results and root causes never become today's ACs. Evidence graph
adds connected findings, shadow mode by default.

Sources: `backend/app/services/jira_retrieval_service.py`,
`jira_history_search_service.py`, `references/historical-ticket-selection.md`,
`historical-jira-safety.md`.

## How a query is formed

The user never types it. Base query = Jira key + summary + description +
snippet + status + labels (test-plan flow), or the enriched ticket with
entities/outputs/components (history flow). Stopwords and domain filler
(issue, ticket, user, should, resolve...) removed; tokens capped at 12.
Up to 12 deterministic variants: CamelCase split, brand words stripped,
issue extension (components, fix versions), alias expansion from a config
file, pattern triggers (reference family, editor views), category hints
(`+ AEM Guides`, `+ DITA`, `+ workaround fix`). Each channel gets its own
phrasing (Jira history, direct probes, DITA spec, product docs, gold XML).
Skill cookbook prescribes a query set: exact failure, exact
API/config/UI/construct, expected workflow, boundary/config, regression.
Weak results → rewrite and retry → Tavily last.

Sources: `guides_test_plan_generator_service.py` (`_issue_query_text`),
`corrective_rag_service.py` (`_deterministic_query_variants`),
`rag_query_rewrite_service.py`, `references/rag-query-cookbook.md`.

## Reducing overlap

Retrieval side: stable chunk IDs; dedupe by Jira key; dedupe by normalised
content (first ~220 chars); diversity safeguards for broad queries; duplicate
ratio counted as weak evidence; hierarchical expansion deduped and fitted to
a token budget.
Plan side: coverage equivalence compares decisions structurally (outcome,
state, scope, config, applicability), not by wording. SAME_OUTCOME_VARIANT
merges into one AC; DISTINCT_OUTCOME stays separate; DEPENDENT_OUTCOME never
auto-merged; CONFLICT kept visible. Minimum-scenarios rule; historical list
pruning; claim-level dedupe; reviewer checks for duplicate or wrongly
collapsed ACs.

Sources: `corrective_rag_service.py`, `jira_retrieval_service.py`
(`_apply_enterprise_diversity`), `hierarchical_retriever.py`,
`references/reasoning-pipeline-phases.md` Phase 6.8.

## Running on the VM nightly

Always on: `aem-backend.service` (uvicorn :8001) behind Nginx :4502, which
serves the dashboard and proxies `/api`, `/mcp`, `/health`. Installed by
`setup_vm.py`.

In-app scheduler (APScheduler, env-configured): Jira indexing every 6 h
(`updated >= -7d`), docs crawl and DITA PDF index on their own crons,
evidence graph incremental drain plus nightly full reconciliation.

Cron (UTC on the VM, IST = +5:30):

| IST | Job |
|---|---|
| 07:00 daily | `uac_release_runner.py`: generate UACs, post those that pass checks |
| 07:30 Mon–Fri | `uac_staleness_watch.py`: alert QE when root cause/fix/PR arrives after a UAC |
| every 30 min | `uac_learning_harvester.py` + `release_dashboard.py` |
| 1st, 11:30 | monthly learning report |

Runner steps: health checks (Jira, MCP, Copilot CLI) → JQL (unresolved,
`UAC_Check`, empty AC field, not `QEVision_UAC_DONE`, updated ≤30d, max 10)
→ skip `UAC_Not_Required` and closure-requested tickets → Copilot CLI with
the skill, clones mounted read-only → checks (validator, 1–10 ACs, blocked
vocabulary, Doc Researcher ran, every sentence/attachment mapped, ≥3
`ask_dita_expert` probes, ≥2 narrow history searches) → post to empty field,
verify render, attach plan, comment, label, decision-request comment for TBDs.
Copilot cannot write to Jira or `git push` (denied tools); only the runner
writes. Secrets in `/opt/uac-release/uac.env` (chmod 600). Lock file, 30-day
logs, last 5 attempts kept.

Sources: `scripts/uac_release/uac-release.cron`, `config.example.json`,
`uac_release_runner.py`, `README.md`, `backend/app/main.py`, `setup_vm.py`.

## Vision PR arrives after UAC: rewrite?

No, not automatically. `QEVision_UAC_DONE` excludes the ticket from the
nightly JQL; `regenerate_existing` is false; a field with text is never
overwritten. Vision comments (`[Vision] ...`) are bot notices, not human
comments. The staleness watch alerts QE once per new root cause/fix/PR;
QE decides whether to re-run. Unmerged PR → UAC carries a `PROPOSED` note.

## Timings and timeouts

No published average latency; every pipeline call logs `elapsed_ms`
(`test_plan_pipeline_done`) and every nightly ticket records
`copilot_seconds` in `status.json`, so real p50/p95 come from VM logs.

| Layer | Timeout |
|---|---|
| Nginx → backend (`/api`, `/mcp`) | 600 s read/send, 75 s connect |
| CLI `--http` client | 900 s |
| Each LLM call | 120 s (`AI_LLM_TIMEOUT_SECONDS`) |
| Hierarchical retrieval expansion | 500 ms |
| Copilot per ticket (nightly) | 100 min |
| Run lock max age | 12 h |

Practical: retrieval in seconds, full plan in minutes, hard 10-minute ceiling
over HTTP. Dashboard "time saved" uses a configured 10 min per criterion,
not measured runtime.

## FastAPI: REST and MCP from one app

One FastAPI app, one business layer, two protocols:
- REST: `POST /api/v1/test-plans/pipeline`
- Remote MCP: `POST /mcp` (JSON-RPC `initialize`, `tools/list`, `tools/call`)
- REST bridge for MCP-shaped tools: `POST /api/v1/mcp/guides-test-plan-generator`
Plus local stdio MCP (`mcp_server.py`, FastMCP) and `mcp_api_adapter`
(thin wrappers over REST). All call `test_plan_pipeline_service.py`, so
output is equivalent everywhere. Same bearer auth, same `/health`.

## Vision agent integration

Direction: our agent writes the UAC; Vision reads it from the Jira
Acceptance Criteria field (AC text only). Contract: JQL
`labels = QEVision_UAC_DONE AND "Acceptance Criteria" is not EMPTY`; format
`- Acceptance Criteria NN: ...` with indented `**Source:**` / `**TBD:**`
lines and an optional proposed-fix `Note:` first line; TBD = decision
pending. Vision must keep the `[Vision]` comment prefix so the runner
ignores its comments (no loop), and must never write the AC field or our
labels. Full implementation prompt: `docs/vision_uac_integration_prompt.md`.

## On-demand UAC requests (REST and MCP)

Live since PR #220. Any caller, Vision included, can ask for a UAC on one
ticket and have it generated, checked and **posted** into the Acceptance
Criteria field, instead of waiting for the nightly batch. Same FastAPI app,
two protocols, one handler.

```
caller ── POST /api/v1/uac-requests {"jira_key": "GUIDES-60001"}   ─┐
       ── MCP tools/call request_uac {"jira_key": ...}            ─┤ 202 {request_id, status: queued, poll_url}
                                                                   ▼
          request file in UAC_REQUESTS_DIR (backend writes nothing else)
                                                                   ▼
          uac_release_runner.py --on-demand   (cron every 2 min, same run lock as nightly)
          → process_ticket, unchanged: skill generation · all checks · AC field
            · test plan attached · QEVision_UAC_DONE · outcome written on the request
                                                                   ▼
caller ── GET /api/v1/uac-requests/{id} | MCP request_uac_status | watch the label
       → posted (ac_count) | failed (CHECKS_FAILED + problems, WRITTEN_UNRENDERED, ERROR)
         | skipped (FIELD_KEPT, NOT_REQUIRED, CLOSURE_ASKED, OPS_REQUEST, ALREADY_POSTED)
```

Points to make in the demo:
- Trigger to posted is typically 10-30 minutes: 2-minute pickup plus the
  normal generation and checks. The call is asynchronous by design; the
  proxy's 10-minute ceiling would cut a synchronous one.
- The backend only records the request. Jira is written by the runner,
  after every check the nightly run applies; Copilot still has Jira writes
  denied. Nothing about generation or posting changed.
- A second request for a ticket still queued or running returns the same
  request (HTTP 200), not a duplicate. A ticket whose field already has
  text is skipped with FIELD_KEPT: read that UAC.
- Max 3 requests per on-demand run, so a burst cannot starve the nightly
  batch. A request left running by a dead run is queued again after the
  lock timeout.
- Three entry points now: `UAC_Check` label (nightly), this API/MCP
  (on-demand), `--ticket KEY` on the VM (manual). Same engine, same checks.

Example for Vision:

```bash
curl -X POST http://<VM>:4502/api/v1/uac-requests \
  -H "Authorization: Bearer $STUDIO_TOKEN" -H "Content-Type: application/json" \
  -d '{"jira_key": "GUIDES-60001", "requested_by": "vision"}'
# poll every 1-2 min, allow ~2 h; on "posted", read the AC field and start the fix
```

Deployment: backend env `UAC_REQUESTS_DIR` = runner `requests_dir`
(`/opt/uac-release/runs/requests`), the `*/2` cron line from
`scripts/uac_release/uac-release.cron`, first request with `--dry-run`.

Sources: `backend/app/api/v1/routes/uac_requests.py`,
`backend/app/services/uac_request_service.py`,
`backend/app/api/routes/remote_mcp.py` (`request_uac`, `request_uac_status`),
`scripts/uac_release/uac_request_queue.py`, `uac_release_runner.py`
(`process_requests`, `--on-demand`), `docs/vision_uac_contract.md` section 8.
