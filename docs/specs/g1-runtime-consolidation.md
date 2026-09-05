# G1 — Runtime acceptance-contract hygiene (scoped)

Status: Scoped, not implemented
Basis: uac_eval n=30 (seed 5, fixed extractor) + direct inspection of the runtime on
GUIDES-33605. Supersedes the earlier framing of G1 as "the runtime over-generates
distinct ACs and needs a semantic-consolidation engine." That framing was wrong. The
measured defect is narrower, lower-risk, and has a concrete root cause in the renderer's
input, not in the volume of genuine ACs.

## The measured defect

The precision axis (after the extractor fix) flagged ~6/29 scorable plans with a
precision of 0 because their `## Acceptance contract` section carried 29–95 bullets.
GUIDES-33605 is the worst and was inspected directly. Its 95 acceptance-contract bullets
are, in fact:

| kind | count | examples |
|---|---|---|
| real acceptance sentences | **17** | "Bulk metadata update tools must not modify locked items and must clearly indicate locked items are skipped." |
| raw evidence / traceability IDs | 42 | `jira:GUIDES-33605:uac:1f772c7ebb10…`, `JIRA:GUIDES-33605:UAC:UAC-14:<64-hex>` |
| bare dimension / axis tags | 21 | `toolbar_customization`, `uuid_variant`, `locked_state`, `guid_reference`, `negative`, `test_matrix` |
| short fragments (<5 words) | 15 | `no duplicate or missing events are introduced.` |

So the 17 sentences are good, well-factored ACs. The other **78 bullets are traceability
IDs and dimension tags that leaked into `AcceptanceCandidate.statement` and were promoted
and rendered as acceptance criteria.** This is a candidate-statement hygiene bug, not
semantic over-decomposition. (The 861 "near-duplicate pairs" the deterministic detector
reported are mostly these junk tokens sharing substrings, not genuine ACs said twice.)

## Root cause (file:line)

`backend/app/services/canonical_test_plan_reasoning_service.py`

1. `resolve_acceptance_contract_with_trace` (~3248) builds candidates:
   `AcceptanceCandidate(statement=row.candidate, …)` at **3302–3327**, where `row` is a
   `CoverageDispositionRecord`. `observable=bool(row.candidate.strip())` (3311) — an ID or
   a tag is non-empty, so it is treated as observable. There is no check that
   `row.candidate` is an English acceptance sentence.
2. `row.candidate` originates in `classify_coverage`, which sets
   `candidate = fact.literal` (~3003). For tickets with an existing structured UAC
   (HUMAN_ACCEPTED_CONTRACT mode) the contract-fact extractor emits facts whose `literal`
   is a UAC anchor ID (`jira:…:uac:<hash>`) or a dimension tag (`toolbar_customization`),
   not the UAC sentence — so those literals become candidate statements.
3. `render_final_plan` (**3908–3940**) appends each promoted candidate's `statement` to
   `section_items["acceptance_contract"]`, and the serializer (**4095**,
   `lines.extend(f"- {item}" for item in section.items)`) emits one bullet per unique
   statement text. Exact-text dedup exists (4025–4035) but does nothing for 78 distinct
   junk tokens.

The existing `_semantic_candidate_key` grouping (3328–3336) only merges semantically
equal statements; it has no notion of "this statement is not a sentence."

## The fix (candidate-statement hygiene gate)

A single, well-placed classifier that decides whether a candidate statement is a
promotable acceptance sentence. Two integration points, pick the earlier one:

- **Preferred — at candidate construction (3302–3327):** compute an
  `is_acceptance_sentence(statement)` predicate and set a new typed field on
  `AcceptanceCandidate` (e.g. `malformed_statement: bool`). A candidate that fails the
  predicate is NOT eligible for promotion to the acceptance contract.
- **At promotion (ACCEPTANCE_PROMOTION_GATE / `resolve_acceptance_contract`, ~3410 →
  the promotion decisions consumed at 3908):** a malformed statement yields a
  non-promoted decision with reason "statement is a traceability artifact, not an
  acceptance criterion," routing it to a coverage/evidence disposition instead of the
  contract.

`is_acceptance_sentence(s)` — deterministic, standard library, fail-closed:
- REJECT if `s` matches an evidence/ID pattern: `^(jira:|JIRA:)`, contains `:UAC:`, is a
  bare hex hash `^[0-9a-f]{16,}$`, or is a bare snake_case token `^[a-z][a-z0-9]*(_[a-z0-9]+)+$`
  with no spaces.
- REJECT if it has fewer than N content words (start N=4; tune against the corpus).
- ACCEPT otherwise. Mirror the same token classes used in
  `scripts/uac_eval/precision.py` so the eval and the runtime agree on what an AC is.

### Completeness-invariant constraint (do not violate)

The runtime enforces that every extracted fact/disposition is dispositioned or traced
downstream — `render_final_plan` raises `RuntimeError` if a disposition has no rendered
projection (4101–4107), and the renderer requires exactly one projection per finalized
candidate (4054–4059). Therefore a rejected junk statement **must not be silently
dropped** — it must be routed to a non-acceptance disposition (its underlying evidence ID
already belongs in `source_fact_ids` / `source_disposition_ids`, which are aggregated into
`source_record_ids`, not printed as bullets). The correct outcome is: the traceability ID
stays as a *record id* on the real AC it supports, and never appears as its own statement.
Verify no `RuntimeError` from the invariant checks after the change.

### Secondary — near-duplicate merge (optional, lower priority)

For the genuinely-sentence candidates, add a Jaccard≥0.6 merge (same threshold as
`precision.py`) so parameterized variants collapse with aggregated evidence. On 33605
this is minor (the 17 sentences are mostly distinct); it matters more on tickets whose
tail is real parameterized ACs (e.g. per-topic-type variants). Ship the hygiene gate
first; measure; add the merge only if the eval still shows a precision tail.

## Validation (measure, keep or revert)

1. Re-run `python scripts/uac_eval/run.py --n 30 --seed 5`. Expected: pipeline
   deterministic precision rises from ~70% toward ~90% as the 6 junk-inflated plans drop
   from precision 0 to high; coverage on the 17 clean-plan cases must NOT fall (the hygiene
   gate only removes non-sentences — it must not remove real ACs). Combined (F1) is the
   keep/revert number.
2. Spot-check GUIDES-33605, 28171, 27789, 42582, 26516, 34084 by hand: acceptance-contract
   bullet count should drop to the real-sentence count (33605: 95 → ~17) with the 17
   sentences preserved verbatim.
3. Confirm no new `RuntimeError` from the completeness-invariant checks on the full n=30.
4. A known-good single-AC ticket (e.g. GUIDES-49386, already precision 100) must be
   unchanged — the gate is a no-op on clean plans.

## Risks / non-goals

- Risk: the predicate is too aggressive and drops a terse real AC ("no duplicate or missing
  events are introduced." is a real 8-word AC — the <5-word rule would keep it; a <4-word
  rule is the floor). Tune N against the corpus; err toward keeping. The eval's coverage
  number is the guard — if coverage drops, the predicate is eating real ACs.
- Non-goal: LLM-based rewriting/consolidation of ACs. This is a deterministic hygiene gate,
  consistent with the runtime's LLM-free design. No new stage; a within-stage predicate on
  the existing candidate/promotion path.
- Non-goal: changing what the contract-fact extractor emits. Fixing the upstream so a UAC
  anchor ID never becomes a fact literal is a larger, riskier change; the hygiene gate at
  promotion contains the damage regardless of which upstream path produced the junk.

## Recommended order

1. Add `is_acceptance_sentence` + `malformed_statement` field + promotion guard.
2. Re-run the eval (step 1 above); keep only if combined rises and coverage holds.
3. If a precision tail remains and it is genuine sentences, add the Jaccard merge.
