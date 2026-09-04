# Spec: Render/synthesis Part 3 — gated LLM statement synthesis (presentation layer)

Status: Proposed (scoping)
Owner: (assign)
Parent: `runtime-render-synthesis-quality.md` (Part 1 shipped; Part 2 rule-based framing
reverted as net-neutral). Part 3 is the only remaining lever on render quality.

## 1. Problem
Part 1 removed evidence noise; the surviving coverage bullets still read as internal
labels / bare noun phrases ("Detected DITA constructs: ...", "Translation", "November
2023 release ..."). Part 2 proved rule-based framing cannot turn arbitrary internal
candidate text into clean QE criteria (it mangled evidence-y prose and measured
net-negative). Only a generative rewrite can produce "Verify that <behaviour>"-quality
statements. That requires an LLM.

## 2. Hard constraint (the line this crosses)
The canonical runtime is deterministic and LLM-free BY DESIGN (0 LLM calls; typed,
auditable, reproducible). Part 3 must NOT put an LLM inside the runtime. Instead it adds
an optional, gated **presentation-synthesis layer DOWNSTREAM** of the deterministic
runtime, so the reasoning/structured contract stays deterministic and only the rendered
prose is polished.

## 3. Design
**3.1 Location.** After `run()` produces the deterministic result, the packet is built at
`adapt_legacy_packet` -> `LEGACY_COMPATIBILITY_PROJECTOR.project_result`
(`guides_test_plan_generator_service.build_guides_test_plan_packet`). Add the synthesis as
an optional post-projection pass over the rendered coverage bullets, reusing the existing
`app/services/llm_service.py` `generate_json`. The runtime module is untouched.

**3.2 Unit of work.** For each coverage-section bullet (a disposition candidate that
survived Part 1), rewrite the text into one plain QE line, keeping its evidence_ids. Batch
ALL bullets of a plan into ONE call (cost/latency).

**3.3 Rewrite-only contract (anti-invention - the critical guard).**
- Prompt: rewrite each bullet into a single "Verify that ..." observable-behaviour line;
  do NOT add any specific the source does not contain (no new number, config key, API,
  field, default, name); if a bullet is not a checkable behaviour, return it unchanged.
- Post-validation: reject a rewrite that introduces a token/number/code-identifier absent
  from {source bullet + its evidence text}. Reuse the detectors from `coverage_forcing`
  (code identifiers) and the judge's invented-fact notion. On any rejection -> keep the
  deterministic bullet.

**3.4 Gating + graceful degradation.** Env flag (e.g. `RENDER_SYNTHESIS_LLM`, default
OFF). LLM unavailable / error / validation failure -> the deterministic Part-1 bullet is
the floor. The plan is always renderable without the LLM.

**3.5 Determinism / reproducibility.** The structured_plan, candidates, gate_decisions,
and evidence bindings stay byte-deterministic (unchanged). Only the rendered prose is
polished, and it is marked "presentation-synthesized". Use temperature 0 and cache by a
hash of (bullet, evidence) so repeated runs are stable. The reproducibility contract
applies to the structured layer, not the polished prose.

## 4. Measurement (the bar)
A/B on the eval (cleaned corpus, hardened judge), WITH vs WITHOUT the flag:
- KEEP only if holistic rises MEANINGFULLY (materially more than Part 1's +0.3, since this
  costs an LLM call) AND coverage does not drop AND **hallucinations do NOT rise**. The
  invented-fact risk is real; the hallucination metric + the 3.3 post-validation are the
  guards. `extra_criteria` may rise.
- Also track cost/latency per plan (one batched call) and cache hit rate.

## 5. Risks
- **Invention** (top risk): an LLM rewrite adds an unsupported claim. Guarded by 3.3
  post-validation AND the eval hallucination gate; if either fails, do not ship.
- **Non-determinism**: mitigated by keeping the structured layer deterministic + temp 0 +
  caching; the polished prose is explicitly outside the reproducible contract.
- **Cost/latency**: one batched call, bounded tokens, cache.
- **Scope creep**: synthesis is strictly PRESENTATION (rewrite existing bullets), never
  reasoning or new coverage. It must never create a bullet, only reword one.

## 6. Acceptance criteria
- Flag OFF (default) = today's deterministic behaviour, byte-identical.
- Flag ON: coverage bullets read as clean QE "Verify that ..." statements; no bullet
  contains a specific absent from its source+evidence (post-validation passes).
- Eval: holistic up meaningfully, coverage not down, hallucinations not up (else do not
  default-on / revert).
- Runtime module unchanged and still LLM-free; synthesis lives only in the downstream
  presentation layer.

## 7. Recommendation
Build behind the flag, default OFF, measure, and only consider default-ON if the eval
shows a meaningful holistic gain with zero hallucination increase. This is the one place
the LLM-free line is crossed, but it is crossed OUTSIDE the runtime, so the deterministic,
auditable reasoning core is preserved. If the gain is not clearly worth the LLM cost and
the invention risk, do not ship it - Part 1 already captured the safe, deterministic win.
