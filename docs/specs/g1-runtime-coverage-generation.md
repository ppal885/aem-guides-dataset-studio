# Spec: G1 — make the runtime GENERATE coverage dimensions (not just flag them)

Status: Proposed (scoping)
Owner: (assign)
Supersedes the generation half (§3.5) of `canonical-runtime-coverage-stages.md`.
Basis: code trace of the shipped canonical runtime + the recurring miss on
GUIDES-14665 (single-language partition dropped) and the eval finding that a
skill-layer gate can never raise pipeline coverage (it only blocks).

## 1. Problem
The skill's coverage gates only VALIDATE a plan; the plans are produced by the VM
canonical runtime. So a dimension the skill would force can still be omitted by the
runtime. Worse, the omission is non-deterministic: on GUIDES-14665 the same ticket
produced a plan covering the config partition on one run and dropping it on another.
G1 is to make the runtime reliably PRODUCE, for every applicable coverage dimension,
either an acceptance criterion or an Open Question — so nothing is silently dropped.

## 2. Where it happens (code trace)
Pipeline (`backend/app/services/canonical_test_plan_runtime.py`, `_run_once`):
- `SEMANTIC_BEHAVIORAL_CLOSURE_EXPLORER` (~:927) -> `closure` (rows keyed by `SemanticDimension`).
- `COVERAGE_DISPOSITION_CLASSIFIER` (~:1155) -> `dispositions = classify_coverage(facts, closure, impacts, hypotheses, scope, questions)`.
- `ACCEPTANCE_CONTRACT_RESOLVER` (~:1173) -> `candidates = resolve_acceptance_contract_with_trace(facts, dispositions, questions)`. **This is the generation point.**
- `BEHAVIORAL_COMPLETENESS_GATE` (~:1181) -> checks `closure` dimensions are satisfied by dispositions/questions (a FLAG, not generation).
- `ACCEPTANCE_PROMOTION_GATE` (~:1213) -> promotes candidates to ACs.

Reasoning service (`backend/app/services/canonical_test_plan_reasoning_service.py`):
`classify_coverage`, `resolve_acceptance_contract(_with_trace)` (~:3358), `AcceptanceCandidate` (schema ~:3234), `behavioral_completeness_gate`.

**Root cause:** `closure` enumeration is evidence-driven. When evidence for a dimension is
thin or absent (e.g. a single-language variant not spelled out in the ticket), no closure
row exists -> no disposition -> no candidate -> the dimension is silently absent, and the
completeness gate cannot flag what was never enumerated.

## 3. Design (locked-runtime-safe: within-stage, no new stage)
The earlier bolt-on/new-stage attempts failed because `GateDecision.gate` is a fixed
`CanonicalRuntimeStage` enum and the runtime forbids injecting gates. G1 avoids that
entirely: it changes the BODY of two existing stages. No new stage, no stage-order
change, no new gate name — so the stage-order invariant test is untouched.

**3.1 One canonical dimension taxonomy, shared.**
Adopt a single dimension set used by BOTH the skill's `dimension_inventory` gate and the
runtime. Map each to a `SemanticDimension` (extend the enum only if a dimension has no
home): entry_points, consumers_and_siblings, state_config_partitions, output_scope,
error_and_negative_paths, performance_scale, security, localization, upgrade_migration,
regression_surface.

**3.2 Seed the closure with the canonical set (completeness by construction).**
In the closure explorer, after evidence-driven rows are built, ensure every canonical
dimension has a closure row: applicable ones flagged from `ScopeResolution`
signals (primary_output_type, publishing_mode, enable_dita_ot_processing, issue_domains,
change_surfaces), the rest marked `NOT_APPLICABLE` with a reason. The enumeration is
deterministic; the applicability is evidence-driven. This closes the "never enumerated"
hole without inventing coverage.

**3.3 Resolver emits candidate-or-OQ per applicable dimension.**
In `resolve_acceptance_contract`, for each applicable closure dimension not already
satisfied by a candidate: if evidence supports a decidable assertion, emit an
`AcceptanceCandidate` for it; otherwise emit an Open Question (a directed
`MissingQuestion`). Never drop it. This is the behavioural change that makes the pipeline
PRODUCE the dimension instead of flagging its absence.

**3.4 Keep ACs plain and evidence-bound.**
Generated candidates must obey the same output rules already enforced (plain QE English,
no code identifiers, evidence-bound, no unit-test-as-AC). Reuse the existing candidate
construction so promotion, lifecycle, and rendering are unchanged.

## 4. Implementation steps
1. Define the shared taxonomy (a small module/enum mapping) used by skill + runtime.
2. Closure explorer: seed-and-classify the canonical set (3.2); applicability from ScopeResolution.
3. `resolve_acceptance_contract`: the candidate-or-OQ guarantee per applicable dimension (3.3).
4. Ensure `behavioral_completeness_gate` now sees a complete closure (it should pass more, not fail).
5. Update `test_canonical_test_plan_runtime_contracts.py` for the enriched closure and any candidate-count assertions.

## 5. Test & measurement plan
- Unit: a dimension-thin ticket (single-language style) now yields a closure row +
  a candidate-or-OQ for that dimension; a genuinely-N/A dimension yields NOT_APPLICABLE, not a candidate.
- Regression: full `test_canonical_test_plan_runtime_contracts.py` green (update intentional assertions).
- End-to-end (the real bar): re-run `scripts/uac_eval/judge_pipeline.py` on the cleaned corpus
  with the hardened judge. Keep the change ONLY if it raises coverage on dimension-relevant
  tickets WITHOUT raising hallucinations (extra_criteria may rise; hallucinations must not).
  Build a dimension-enriched eval slice (backlog G5) so the effect is measurable, since the
  dimension is rare in the general corpus.

## 6. Risks & rollback
- Core generation change: affects every plan and the runtime-contract suite. Land behind the
  full suite + an eval that shows lift without hallucination regression.
- Over-generation: seeding the canonical set could add low-value OQs. Mitigate with strict
  applicability from ScopeResolution and a NOT_APPLICABLE default; measure OQ volume in the eval.
- Rollback is a clean revert of the two stage bodies (no schema/stage-order change if the
  SemanticDimension enum is not extended; if extended, that member is additive).

## 7. Acceptance criteria for this task
- For an applicable coverage dimension, the runtime plan always contains either an AC or an
  Open Question for it — verified on the GUIDES-14665-class case, deterministically across runs.
- A not-applicable dimension produces no spurious AC/OQ.
- Runtime-contract suite green; eval shows coverage lift on dimension-relevant tickets with
  no hallucination increase.
- No new CanonicalRuntimeStage, no stage-order change, no bolt-on gate (change is within
  the closure explorer and acceptance resolver only).
