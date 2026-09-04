# Spec: Runtime render/synthesis quality — coverage bullets are raw evidence

Status: Proposed (scoping)
Owner: (assign)
Basis: code trace of the shipped runtime renderer + the observed evidence-dump in the
`## Configuration / state coverage` section of the GUIDES-14665 plan. This is the real
quality ceiling of the runtime's plan output, distinct from G1 (dimension production,
which the runtime already handles).

## 1. Problem
The runtime's coverage sections read like an evidence dump, not a QE plan. Observed
bullets under `## Configuration / state coverage`:
- `!screenshot-1.png|thumbnail!`
- `Documented purpose: Learn about the bug fixes and how to upgrade to the ... release`
- `4.6`
- `Boolean ppLangCopies = PropertiesUtil.toBoolean(cfgMgr.getConfig(...), false)`
A reviewer cannot act on these; they are raw evidence spans, not observable behaviour.

## 2. Root cause (code trace)
`backend/app/services/canonical_test_plan_reasoning_service.py`:
- `classify_coverage` builds `CoverageDispositionRecord` with `candidate=fact.literal`
  (~:3003). The candidate statement IS the raw fact text.
- `facts` come from `extract_contract_facts`, which splits the Jira description / RAG /
  repo evidence into literal spans — so a RAG chunk, a screenshot reference, a bare
  number, or a code line becomes a `fact.literal` -> a disposition `candidate`.
- `render_final_plan` faithfully prints `_plain_candidate(disposition.candidate)`
  (~:3951) into the section. The renderer is not the problem; it prints what it is given.
- The reasoning service makes **zero LLM calls** (deterministic by design), so nothing
  rewrites a raw literal into a synthesized behaviour statement.

Net: coverage candidates are un-synthesized evidence fragments, printed verbatim.

## 3. Constraint
The runtime is deterministic (LLM-free) on purpose. Any fix in-runtime must be
**rule-based**. A bounded LLM synthesis pass is possible but is an architecture change
(introduce a controlled generative stage) and must be justified separately — start
rule-based.

## 4. Design (rule-based, two parts)
**4.1 Evidence-fragment filter (do not let non-behavioural evidence become a candidate).**
Before a `fact.literal` becomes a coverage `candidate`, drop the shapes that are clearly
evidence, not observable behaviour:
- image/screenshot refs (`!...png|thumbnail!`, `.png/.jpg/.gif`),
- RAG doc-chunk lead-ins ("Documented purpose:", "Learn about", "Configure ... | Adobe Experience Manager"),
- bare numbers / version fragments (`4.6`, `2023.10.14029`),
- raw code lines (assignments, `Class.method(`, camelCase identifiers, config-PID dumps, file paths, URLs),
- stack-trace remnants (already reduced upstream by `_reduce_stack_frames`; reuse it).
Reuse the detectors already written: the skill's `coverage_forcing` code-identifier
regexes, `gold_quality`'s pointer/near-empty logic, and `_reduce_stack_frames`. Port the
shapes into a small `_is_behavioural_literal(literal)` helper in the reasoning service.

**4.2 Statement normalization (make survivors read like criteria).**
Normalize a surviving literal into a consistent, plain QE statement: strip markup and
ontology prefixes (extend `_plain_candidate`), and where the literal is a bare noun
phrase, front it with a QE verb ("Verify that ..."). No new facts, no paraphrase beyond
framing — deterministic and meaning-preserving.

**4.3 (Follow-up, gated) bounded LLM synthesis.**
If rule-based framing is not enough, add ONE controlled generative sub-step that rewrites
each surviving literal into a one-line behaviour statement, bound to the same evidence
ids (so it cannot invent). This changes the "LLM-free runtime" property and must be
measured to justify. Not in the first cut.

## 5. Measurement
- New lint (build it): count evidence-fragment-shaped bullets per rendered plan
  (image refs, bare numbers, code lines, doc-chunk lead-ins). Target: near zero after 4.1.
- Eval on the cleaned corpus with the hardened judge: holistic should RISE (cleaner,
  actionable plans); coverage must NOT drop (the filter must not remove real behaviour);
  hallucinations must NOT rise. Keep only if holistic up and coverage flat/up.
- Spot-check the GUIDES-14665-class config section reads as behaviour, not evidence.

## 6. Risks
- Over-filtering removes a real behavioural literal -> coverage drop. Mitigate: filter
  only unambiguous evidence shapes; measure coverage as the guard.
- Normalization distorts meaning. Mitigate: framing-only ("Verify that <literal>"), no
  paraphrase; keep evidence-id binding.
- Blast radius: `classify_coverage` + `render_final_plan` feed every plan and the
  runtime-contract suite; land behind the full suite + the eval.

## 7. Acceptance criteria
- Coverage-section bullets read as observable QE behaviour, not evidence fragments; the
  evidence-fragment lint is ~zero on a sample of rendered plans.
- Eval: holistic up, coverage not down, hallucination not up (else revert).
- Runtime-contract suite green; deterministic (no new LLM dependency in the first cut).
