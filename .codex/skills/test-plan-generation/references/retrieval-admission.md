# Question-Level Retrieval Quality & Evidence Admission (RAG-Q1)

Retrieval is not evidence. A document mentioning the same feature is not
automatically an answer to a material Question; a search snippet is not
fetched source evidence; a fetched source is not automatically decisive; a
decisive source is not automatically authoritative. Enforced by
`scripts/retrieval_admission.py` over the manifest `retrieval_requests` /
`retrieval_results` blocks; extends the existing read-only retrieval path
(`offline_retrieval.py`, `relevance_prioritizer.py`) and composes with the
R1 Doc Researcher and H1 historical-Jira safety. It does not build another
RAG system, replace the vector store, re-index, or change source authority.

Target flow: Material Question → Research Query → Retrieval → Candidate
Evidence → Applicability/quality assessment → Evidence Admission → Question
Resolver → S1 → C1 → E1 → L1.

## Question-bound retrieval (`retrieval_requests.items[]`)

Every request binds `request_id`, `question_id` (must exist in the Question
Plan), `research_id`, `query` (the actual query used), `required_source_type`,
`product_context`, `applicability`, `requested_claim`, `top_k` (bounded —
never raised to force an answer; no answer is a valid result), and
`retrieval_mode` (`PRODUCTION` / `OFFLINE_RETRIEVAL_EVAL` /
`LIVE_READ_ONLY_RETRIEVAL_SMOKE`, reported separately). Query rewrites may
improve retrieval quality but the Question binding never changes; the actual
query is recorded. Retrieval budgets (`queries_per_question`,
`chunks_retrieved`, `chunks_fetched`, `research_rounds`) are tracked.

## Candidate contract (`retrieval_results.items[]`)

Each candidate records `retrieval_result_id`, `request_id`, `question_id`
(matching the request), `source_id`, `chunk_id`, `rank`, `retrieval_score`
(discovery metadata — never authority), `source_type`,
version/currentness, `applicability` (`CONFIRMED` / `UNCLEAR` / `WRONG` /
`NOT_ASSESSED`), `relationship`, `supported_claim`, `decisiveness`,
`limitations[]`, `fetched` (exact evidence fetched through the authorized
read-only interface before material use), optional `fetched_evidence_id`,
`subject_key` (exact configuration/property identity), `stale`, and
`is_historical`.

## Relationships and the admission ceiling

- `TOPIC_MATCH` — related terminology/functionality; does not materially
  answer the Question; discovery only; cannot make S1 SUFFICIENT.
- `RELEVANT` — materially concerns the functionality but does not establish
  the claim; may refine research or locate another source.
- `SUPPORTS_CLAIM` — consistent with a material part of the answer; may be
  partial/indirect; S1 determines final sufficiency.
- `DECISIVE` — directly establishes the requested claim for the applicable
  product context, **subject to source authority** — never automatically
  authoritative, never automatically SUFFICIENT.

`max_admissible_relationship()` is the structural ceiling, independent of
retrieval score: NOT_ASSESSED → TOPIC_MATCH; WRONG applicability →
TOPIC_MATCH; not fetched → RELEVANT at best; `subject_key` mismatch with the
request (nearby configuration with a same-looking value is not the same
property) → TOPIC_MATCH; stale revision → TOPIC_MATCH; UNCLEAR applicability
→ SUPPORTS_CLAIM at best; otherwise DECISIVE at most. The gate fails any
declared relationship above the ceiling. DECISIVE additionally requires
CONFIRMED applicability plus non-empty `supported_claim` and `decisiveness`.

## Integrations

- **Doc Researcher** consumes question-bound candidates and distinguishes
  "source found" from "Question answered"; a TOPIC_MATCH is never cited as
  proof.
- **H1** — retrieved historical Jira requires an H1 assessment for the same
  question+source before SUPPORTS_CLAIM/DECISIVE; rank never upgrades
  historical authority.
- **S1** — TOPIC_MATCH/RELEVANT never make a Question SUFFICIENT;
  SUPPORTS_CLAIM may contribute; DECISIVE may support SUFFICIENT only when
  authority/applicability/currentness also permit.
- **L1** — only fetched SUPPORTS_CLAIM/DECISIVE evidence reaches AC lineage
  and final Source lines; unused retrieved chunks stay auditable outside it.

## Offline benchmark (`retrieval_benchmark.py`)

A question-level evaluation dataset across representative domains (each item:
question, product context, applicability, expected source class,
known-decisive / acceptable-supporting / hard-negative sources with tagged
kinds, unanswerable flags, and ranked fixture candidates — never final UAC
prose as query or ground truth). Metrics, reported separately for retrieval
and admission: Recall@K, MRR, Decisive Evidence Recall@K, Applicable
Evidence Recall@K, Hard-Negative Retrieval Rate, Wrong-Version /
Wrong-Surface Admission Rates, Topic-Match-as-Proof Rate, Fetch-before-use
compliance, unanswerable false-answer rate — and the headline metric
**DECISIVE_EVIDENCE_MISADMISSION_RATE**. High recall with unsafe admission is
not acceptable. Unanswerable questions expect NOT_FOUND/PARTIAL, never
hallucinated decisive evidence.

Live smoke (`--live`) only reports the existing read-only gateway status; it
never reindexes, writes the corpus, or enables providers, and a connectivity
PASS is not semantic-quality proof.

## Backward compatibility

Absent `retrieval_requests`/`retrieval_results` blocks: clean pass.
