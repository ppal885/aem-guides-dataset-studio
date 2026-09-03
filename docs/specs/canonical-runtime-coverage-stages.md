# Spec: Port skill coverage gates into the canonical test-plan runtime

Status: Proposed
Owner: (assign)
Author: generated from a live investigation (two failed bolt-on attempts, reverted)

## 1. Problem

The skill layer (`.codex/skills/test-plan-generation/scripts/run_gates.py`) enforces a
set of **proactive coverage gates** that the shipped **canonical runtime** does not
run. Measured on live tickets, the runtime-generated plan therefore silently drops
dimensions a senior reviewer routinely has to add:

- On **GUIDES-23883** and **GUIDES-40902**, the real pipeline plan omitted the
  single-topic **Download PDF** entry point, the **Map Preview** surface, and the
  retained **temporary-files / merged-HTML** artifact — exactly the dimensions the
  skill's `native_pdf_coverage` gate forces.
- The runtime also does not run `state_partition_coverage`, `reviewer_request_coverage`,
  `value_provenance_coverage`, `shared_path_regression_coverage`, or
  `publishing_scope_coverage`.

The reason the pipeline misses them: the canonical runtime's gate set is only
`ContractIntegrityGate`, `BehavioralCompletenessGate`, `AcceptancePromotionGate`.

## 2. Why a bolt-on does not work (verified)

Two attempts to append a coverage gate to the runtime's `gates` list both failed the
same 43 runtime-contract tests. Root causes, confirmed:

1. `GateDecision.gate` is typed as `CanonicalRuntimeStage`
   (`backend/app/core/schemas_canonical_test_plan_runtime.py`, `class GateDecision`,
   `gate: CanonicalRuntimeStage`). **Gates ARE stages.** A `GateDecision` whose gate
   name is not a declared `CanonicalRuntimeStage` member cannot even be constructed
   (pydantic `enum` validation error).
2. The runtime is deliberately locked. Module docstring of
   `backend/app/services/canonical_test_plan_runtime.py`: entry points "cannot inject a
   composer, reorder stages, **select a gate**, or bypass typed intermediate records."
   `test_runtime_has_no_arbitrary_generator_hook_and_owns_exact_stage_order` enforces it.
3. Blocking semantics: `blocked = any(gate.status in {GateStatus.FAILED, GateStatus.BLOCKED} ...)`
   (`canonical_test_plan_runtime.py` ~line 1288). A `FAILED` coverage gate hard-blocks;
   there is no non-blocking gate status today.

Conclusion: coverage must be added as **first-class canonical stage(s)**, not appended.

## 3. Design

### 3.1 Add a non-blocking gate status
Add `GateStatus.REVIEW = "REVIEW"` to `GateStatus`
(`schemas_canonical_test_plan_runtime.py`). It is excluded from the `blocked`
computation, so a coverage gap surfaces in `gate_decisions` without blocking an
otherwise-valid plan. Confirmed safe: the only status-set check that matters for
blocking is the one at ~line 1288; nothing does exhaustive matching on `GateStatus`.

### 3.2 Add coverage stages (the two options)

**Option A — one Coverage stage (recommended first step).**
Add a single `CanonicalRuntimeStage.PROACTIVE_COVERAGE_GATE = "ProactiveCoverageGate"`
appended to `CANONICAL_STAGE_ORDER` after `FINAL_QE_PLAN_RENDERER`. It runs the ported
coverage checks against the **rendered plan + structured scope/domains** and emits one
`GateDecision(gate=ProactiveCoverageGate, status=REVIEW|PASSED, failures=[...])`.
- Pros: minimal surface; one stage, one gate row; each ported check contributes a
  failure line.
- Cons: one gate row for many checks (coarser than the skill's per-gate rows).

**Option B — one stage per ported gate.**
Add a `CanonicalRuntimeStage` member and stage per coverage gate
(`NativePdfOutputCoverageGate`, `StatePartitionCoverageGate`, ...). Cleaner reporting,
larger change to `CANONICAL_STAGE_ORDER` and the stage-order test.

Start with Option A; graduate to B if per-gate granularity is needed.

### 3.3 Structured activation (do NOT text-grep)
Activate each ported check from the runtime's typed `ScopeResolution`
(`primary_output_type`, `primary_preset_type`, `primary_publishing_mode`,
`enable_dita_ot_processing`) and `issue_domains`/`change_surfaces` — not from a
substring search of the rendered text. The first bolt-on over-activated by grepping
"native pdf" in unrelated fixtures. Native-PDF activation = the resolved primary
output/preset is Native PDF.

### 3.4 Port the checks natively (no cross-boundary import)
Do NOT import `.codex/skills/.../scripts/*` from the backend (that path is not
deployed with the runtime). Re-implement the check bodies as small pure functions in
`canonical_test_plan_reasoning_service.py`, keeping parity with the skill gates:
- native-pdf: single-topic Download PDF, Map Preview, retained temp files / merged HTML
- state-partition: both values of a state axis (profile, baseline, enumdef-bound/unbound, flag on/off)
- reviewer-request: every reviewer-comment imperative check dispositioned (the runtime
  already has the Jira comments; feed them structurally)
- value-provenance, shared-path-regression, publishing-scope: as in the skill gates
Keep the skill gates as the source of truth for the check semantics; port, don't fork
silently — add a comment cross-referencing the skill module in each ported function.

### 3.5 The deeper fix (follow-up, not this task)
A REVIEW gate only *flags* a missing dimension. To make the pipeline *generate* the
Download-PDF / Preview / temp-files ACs, fold these dimensions into the
**acceptance-candidate generation** stage (`AcceptanceContractResolver` /
`CoverageDispositionClassifier`) so they become promoted candidates, not just a gate
finding. Track separately.

## 4. Implementation checklist

1. `schemas_canonical_test_plan_runtime.py`: add `GateStatus.REVIEW`; add the new
   `CanonicalRuntimeStage` member(s); append to `CANONICAL_STAGE_ORDER`.
2. `canonical_test_plan_reasoning_service.py`: add the ported coverage function(s)
   returning `GateDecision(gate=<new stage>, status=REVIEW|PASSED, failures=[...])`,
   activating from `ScopeResolution`.
3. `canonical_test_plan_runtime.py`: run the new stage via the existing `stage(...)`
   mechanism in `run()` (and `run_controlled_second_pass`) in the correct order; append
   its `GateDecision` to `gates` before `blocked`/trace/response assembly.
4. `test_plan_runtime_adapters.py` / renderer: optionally render a "Coverage review"
   section from the new gate's failures.
5. Update the stage-order invariant test and any test asserting the exact gate set.

## 5. Test plan

- New unit tests: Native-PDF scope + plan missing a dimension -> REVIEW with the right
  failure; plan covering it -> PASSED; non-Native-PDF scope -> PASSED (not activated).
- Regression: `pytest backend/tests/test_canonical_test_plan_runtime_contracts.py` stays
  green (85+), including the stage-order and gate-count assertions (update them
  intentionally for the new stage).
- End-to-end: re-run `scripts/uac_eval/judge_pipeline.py` on the held-out set; confirm
  the Native-PDF plans now surface the coverage review (and, after §3.5, actually cover
  the dimensions).

## 6. Risks

- Core, deliberately-locked service. Two naive attempts each broke 43 tests. Land behind
  the stage-order test and the full runtime-contract suite.
- Scope creep: keep this task to the *gate/flag* (§3.1–3.4). The *generation* change
  (§3.5) is a separate, larger task.

## 7. Acceptance criteria for this task

- Native-PDF runtime plans carry a `NativePdfOutputCoverageGate` (or `ProactiveCoverageGate`)
  `REVIEW` when they omit Download-PDF / Map-Preview / temp-files, and `PASSED` when they
  cover them; the plan is NOT blocked by it.
- Full `test_canonical_test_plan_runtime_contracts.py` suite green.
- No cross-boundary import of the skill scripts; parity comment referencing each skill gate.
