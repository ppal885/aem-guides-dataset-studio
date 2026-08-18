# Architecture Audit & Readiness (foreground; does not touch mining)

This audit prepares the ground so that, once mining finishes and the P0 patterns are
frozen, implementation is a matter of routing patterns into existing components rather
than building new pipelines. It reads only the current skill code and the roadmap; it
does not read any Human-UAC text, so it cannot contaminate the benchmark split.

## Capability readiness map

Every core reasoning capability the roadmap needs already exists in the team-package
skill (`.claude/skills/test-plan-generation/scripts/`), landed additively in Prompts
1-17. A mined pattern attaches to one of these; no new engine is required.

| Roadmap capability | Existing component (file) | Manifest block | Status |
|---|---|---|---|
| Canonical evidence intake | `run_gates.py` evidence_preflight + dual-source + clones | evidence_preflight, rag_tool, jira_history_* | IMPLEMENTED |
| Behaviour model | `behavior_model.py` | behavior_model | IMPLEMENTED |
| Coverage hypotheses | `coverage_hypotheses.py` | coverage_hypotheses | IMPLEMENTED |
| Generic explorers (contract/consumer/state/type/lifecycle/NFR) | `coverage_hypotheses.py` dimensions + `references/coverage-hypotheses-and-explorers.md` | coverage_hypotheses (dimension) | IMPLEMENTED (procedure) |
| DITA semantic relationship explorer | `semantic_relationship_explorer.py` | dita_semantics | IMPLEMENTED |
| Missing questions + directed retrieval | `missing_questions.py` | missing_questions, evidence_lifecycle | IMPLEMENTED |
| Hypothesis verifier | `hypothesis_verifier.py` | verifications | IMPLEMENTED |
| Behavioral relevance prioritizer | `relevance_prioritizer.py` | coverage_hypotheses (distance fields) | IMPLEMENTED |
| Coverage disposition classifier | `disposition_classifier.py` | dispositions | IMPLEMENTED |
| Test oracle builder | `test_oracle_builder.py` | scenario_oracles | IMPLEMENTED |
| Existing-state compatibility explorer | `state_compatibility_explorer.py` | state_compatibility | IMPLEMENTED |
| Cross-surface impact resolver | `cross_surface_resolver.py` | cross_surface | IMPLEMENTED |
| Structural equivalence verifier | `structural_equivalence_verifier.py` | structural_equivalence | IMPLEMENTED |
| Scenario equivalence reducer | `scenario_reducer.py` | scenario_reduction | IMPLEMENTED |
| Evidence authority resolver | `evidence_authority_resolver.py` | evidence_authority | IMPLEMENTED |
| Change impact explorer | `change_impact_explorer.py` | change_impact | IMPLEMENTED |
| Semantic coverage gate | `coverage_gate.py` | (aggregates all) | IMPLEMENTED |
| Pre-UAC quality critic | `pre_uac_critic.py` | critic | IMPLEMENTED |
| Feature-intent / ABS-extension specialists | not yet built | (to design) | MISSING (candidate P1 specialists) |
| Reasoning pattern router | not yet built | pattern_router (to design) | MISSING (needed to route mined patterns) |

**Two genuine gaps to fill after the P0 freeze:** a `ReasoningPatternRouter` (chooses
which explorers/specialists activate per Jira from the mined activation signals) and the
domain specialists the mining flags as P0 (likely a Feature-Intent explorer for Customer
Features and a Product-vs-Extension ownership explorer for ABS). Everything else is a
routing target, not new construction.

## Generic pattern schema (what `qe_reasoning_patterns.yaml` records must satisfy)

A mined record is only promotable to the core engine when it is a reasoning operation,
not a Jira-specific mapping. Required fields:

- `pattern_id`, `name` (a reasoning abstraction, e.g. CONTRACT_BOUNDARY_EXPANSION — never
  NAVTITLE_LOCKTITLE).
- `description`, `activation_signals`, `negative_activation`, `reasoning_questions`,
  `evidence_to_seek`, `possible_outputs`.
- `supported_examples`: **>= 2 TRAIN Jira keys** for a generic pattern (one-Jira patterns
  stay TENTATIVE unless spec/architecture supports generalization).
- `classification`: STRONG_REUSABLE_PATTERN | REUSABLE_PATTERN | DOMAIN_SPECIALIST_PATTERN
  | TENTATIVE_PATTERN | ONE_OFF_BEHAVIOR.
- `dataset_support`: features | abs | both.
- `mapped_component`: one of the existing components above, or a named new specialist.
- `priority`: P0 | P1 | P2 | EXPERIMENTAL.
- `generalizability_test`: a one-line statement of how this reasoning applies to an unseen
  Jira with completely different entities (fails the anti-hardcoding audit otherwise).

## Mining Results Review + P0 Freeze gate (mandatory before implementation)

Implementation does not start when mining ends. First run a short review that:
1. merges duplicate patterns (same reasoning operation under different names);
2. rejects one-off Jira patterns (single-Jira, no spec/architecture backing) to ONE_OFF/TENTATIVE;
3. separates generic reusable patterns from domain specialists;
4. requires every promoted pattern to trace to >= 2 TRAIN Jira in `pattern_traceability.csv`;
5. freezes the minimum P0 capability set (the smallest set of reasoning operations that
   covers the highest-impact systematic gaps) and records it as the implementation contract.

Only the frozen shared-generic P0 set is promoted into the core engine; specialists are
conditional (activated by signals), never always-on.

## Evaluation harness

`analysis/eval_harness.py` scores a generated Pre-UAC against the reconstructed Human-UAC
for a Jira using deterministic, mapping-driven metrics (behavioural recall, open-question
recall, unsupported-assertion rate, available-evidence-missed, inferable-but-not-explored,
false-positive exploration). It consumes a scoring-input JSON (human atomic requirements +
generated items + the evaluator's semantic match verdicts) and never reads raw CSVs, so it
runs on TRAIN and VALIDATION without touching BLIND. It ships with self-tests.
