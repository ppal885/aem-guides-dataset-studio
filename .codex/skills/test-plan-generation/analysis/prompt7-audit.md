# Prompt 7 — Independent Implementation Verification (no production code changed)

Read-only audit of whether the skill genuinely implements

```
Evidence -> Behavior -> Hypothesis -> Explore -> Retrieve -> Verify -> Semantic Gate -> Pre-UAC
```

or still effectively does `Jira -> RAG -> UAC`.

## Method note

This is a **prompt-driven** skill. Its runtime is: Claude executes `SKILL.md` with
tools and records structured outputs in the evidence manifest; `run_gates.py`
invokes deterministic validators that ENFORCE each stage. So "invocation" is
verified at the enforcement layer (are the validators actually called, do they
fire, do they block?), while the generation of each stage is Claude-driven and
gate-checked — there is no autonomous class pipeline, by design.

## Runtime verification (representative full-pipeline trace)

A manifest exercising every stage, run against the real GUIDES-53707 plan via
`python scripts/run_gates.py`, produced this actual invocation trace (each NOTE is
a validator that fired):

| Stage | File / function (invoked by run_gates.run) | Input | Output (observed) |
|---|---|---|---|
| Behavior | `behavior_model.validate_behavior_model` via `check_behavior_model` | manifest.behavior_model | "behavior model validated" |
| Hypotheses | `coverage_hypotheses.validate_coverage_block` via `check_coverage_hypotheses` | manifest.coverage_hypotheses | "coverage hypotheses validated" |
| Explore/Retrieve | `missing_questions.check_retrieval_discipline` via `check_retrieval` | missing_questions + evidence_lifecycle | "retrieval discipline validated" |
| Verify | `hypothesis_verifier.verify_all` via `check_verifications` | verifications + coverage_hypotheses | "hypothesis verifications validated" |
| Semantic Gate | `coverage_gate.evaluate` via `check_coverage_gate` | all reasoning blocks | "semantic coverage gate: PASS" |
| DITA gate | `semantic_relationship_explorer.evaluate_semantic_gate` | manifest.dita_semantics | "semantic coverage gate: PASSED" |
| Pre-UAC integration | `uac_integration.check_integration` | manifest + plan body | "final plan consumes the reasoning outputs" |

Invocation proof (source): `run_gates.py` lines 41-48 load all eight modules; lines
139/120/100/79/53 define `check_behavior_model` / `check_coverage_hypotheses` /
`check_retrieval` / `check_verifications` / `check_coverage_gate`; the `run()` body
(lines ~245-282) calls each plus `audit_mod.audit_paths` and
`integration_mod.check_integration`. None are unreferenced -> **no DEAD_CODE**.
Self-tests: **140 assertions, ALL PASSED**.

## Capability status

| Capability | Status | Evidence |
|---|---|---|
| BehaviorModelBuilder | IMPLEMENTED (enforcement + procedure) | `behavior_model.py`; validated & invoked; 15 self-tests |
| CoverageHypothesisGenerator | IMPLEMENTED | `coverage_hypotheses.py`; invoked; collapse + evidence discipline tested |
| Contract Boundary Explorer | IMPLEMENTED (procedure) | dimension `CONTRACT_BOUNDARY` + `references/coverage-hypotheses-and-explorers.md` (A) |
| Consumer Surface Explorer | IMPLEMENTED (procedure) | dimension `CONSUMER` (B) |
| Consumer-Specific Policy Explorer | IMPLEMENTED (procedure) | dimension `CONSUMER_POLICY` (C) |
| State / Partition Explorer | IMPLEMENTED (procedure) | dimension `STATE_PARTITION` (D) |
| Type / Reference / Artifact Explorer | IMPLEMENTED (procedure) | dimension `TYPE_ABSTRACTION` / `REFERENCE_ARTIFACT` (E) |
| Lifecycle Explorer | IMPLEMENTED (procedure) | dimension `LIFECYCLE` (F) |
| NFR Risk Explorer | IMPLEMENTED (procedure) | dimension `NFR_RISK` (G) |
| DITA Semantic Relationship Explorer | IMPLEMENTED (code + procedure) | `semantic_relationship_explorer.py`; navtitle/conref/keyref self-tests; DITA gate |
| MissingQuestionGenerator | IMPLEMENTED | `missing_questions.py`; question schema + `search_concepts` enforced |
| ReasoningDirectedRetriever | IMPLEMENTED (enforcement); retrieval act is model-driven | `missing_questions.check_retrieval_discipline`; second-pass discipline + lifecycle enforced (see trace below). It validates/forces the second pass; it does not autonomously call retrieval tools (a prompt-driven-skill design choice, not a missing service). |
| HypothesisVerifier | IMPLEMENTED | `hypothesis_verifier.py`; verdict + disposition rules; 12 self-tests |
| SemanticCoverageGate | IMPLEMENTED | `coverage_gate.py`; PASS/NEEDS_REVIEW/FAIL; adversarial suite |
| Final Pre-UAC integration | IMPLEMENTED | `uac_integration.py`; plan-body cross-checks + evidence trace |

No DUPLICATED components: the DITA gate is the single source for `DITA_SEMANTICS`;
`behavior_model` is reused by the coverage gate rather than re-implemented.

## Explore-not-Infer

- `INVESTIGATION_CANDIDATE` cannot directly become an AC: an AC's `evidence_trace`
  must link to a `CONFIRMED`/`INFERRED_HIGH_CONFIDENCE` verification
  (`uac_integration.validate_evidence_trace`) — self-tests "AC tracing to a REJECTED
  hypothesis fails", "evidence_trace without evidence_ids fails".
- `UNRESOLVED -> Open Question`: enforced in `hypothesis_verifier` (disposition map,
  UNRESOLVED->OPEN_QUESTION only) AND cross-checked against the plan body
  (`check_open_questions_surfaced`) — self-tests "UNRESOLVED cannot become an AC",
  "unresolved missing from plan Open Questions fails integration".
- `REJECTED` excluded from output: disposition `EXCLUDED`/`CONTEXT` only — self-test
  "REJECTED cannot enter an AC".

## Second-retrieval trace (real, from the full-pipeline run)

```
initial : E1  source=current repository  query="appendUnixSlash null"  status=USED
behavior: no-href navtitle yields null path (fact, authority CURRENT_IMPLEMENTATION)
question: Q1 (blocking) "Does topichead reach the same null path"  search_concepts=[topichead toc path]
second  : E2  source=current repository  query="topichead toc getTocItemUsingMap"  status=INSPECTED
verify  : H2 -> UNRESOLVED -> disposition OPEN_QUESTION (open_question_ref OQ-1)
gate    : SECOND_PASS_RETRIEVAL = COVERED (new second-pass query differs from initial)
```

The second query is genuinely new vs the initial keyword query, and the discipline
is enforced (`new_second_pass_queries`, `find_duplicate_retrievals`). Because the
retrieval act itself is model-driven, this is **IMPLEMENTED at the enforcement
layer**; a fully-autonomous retriever service was never in scope for a prompt-driven skill.

## DITA semantic generalization

- `semantic_relationship_explorer` self-tests confirm it discovers `locktitle` from
  `navtitle` without a hint, and generalizes to `conref` and `keyref` fixtures — no
  attribute-pair lookup table.
- `anti_hardcoding_audit.py` scans all scripts/prompts and **PASSES** (26+ files):
  no `if <construct>: test_<other>()` and no construct->construct rule literals.

## Negative activation (verified this pass)

- UI-only ticket (behavior_model only): dimensions = `{BEHAVIOR_MODEL: COVERED}`;
  DITA **not** activated, NFR **not** activated, no migration/backward-compat dim.
- A bare `topicref` mention with no coverage candidate: no reference/DITA activation.
- Ticket with no reasoning blocks: `coverage_gate.is_present` = False (gate does not run).
Activation is evidence-driven (declared candidates/blocks), never keyword-driven.

## Semantic gate adversarial

`test_coverage_gate` proves the gate catches: unexplored contract/consumer
(`NEEDS_REVIEW`), unevaluated NFR signal (`NEEDS_REVIEW`), a hidden `UNRESOLVED`
(`FAIL`), a missing directed second pass (`NEEDS_REVIEW`), and an uninvestigated DITA
dependency (`NEEDS_REVIEW`); it passes fully-explored and investigated-and-rejected plans.

## Final verdict

```
PARTIALLY_READY
```

**Why not READY_FOR_VALIDATION:** the entire reasoning architecture is implemented,
invoked, tested (140 assertions), non-duplicated, free of dead code, generalizing,
and free of hardcoding — the machinery is real and the gate genuinely catches
omissions. **But every reasoning block is opt-in** (deliberate backward
compatibility): if an author omits `behavior_model` / `coverage_hypotheses` /
`verifications`, the corresponding checks skip and a plan can still be produced as
`Jira -> RAG -> UAC` (exactly what GUIDES-53707 did, and it PASSED). So production
does not yet *force* the pipeline.

**Single change to reach READY_FOR_VALIDATION (not done here — audit only):** make
the reasoning blocks mandatory in `run_gates.py` for behavioral/DITA tickets (e.g.
require `behavior_model` whenever `behaviour_matters` is true, and require
`coverage_hypotheses`+`verifications` whenever any dimension is activated), turning
the opt-in enforcement into a required gate. That is a policy flip on top of the
now-complete machinery.

STOP — no code changed.
