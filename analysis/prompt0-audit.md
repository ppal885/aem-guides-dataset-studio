# Prompt 0 — Implementation Audit (no code changed)

Audit of the current AEM Guides Test Plan / Pre-UAC skill to decide where the
behavioral-exploration architecture inserts with minimum disruption. Read-only.

## Nature of "the skill" (read this first)

This skill is **prompt-driven**, not a class pipeline. Its runtime is: **Claude
executes `SKILL.md` phases using tools (Jira, RAG, clones), authors the 11-section
plan, and a deterministic Python gate (`run_gates.py`) enforces quality.** So the
target components (BehaviorModelBuilder, CoverageHypothesisGenerator, …) are
implemented as three cooperating layers, not one autonomous pipeline:
1. **Procedure** — `SKILL.md` + `references/*.md` (what Claude must do).
2. **Structured hand-off** — the evidence **manifest JSON** (what Claude records).
3. **Enforcement** — `scripts/*.py` invoked by `run_gates.py` (what is machine-checked).

The DITA semantic explorer already follows exactly this shape (procedure =
`references/dita-semantic-relationship-explorer.md`; hand-off = manifest
`dita_semantics` block; enforcement = `semantic_relationship_explorer.evaluate_semantic_gate`
run by `run_gates.py`). **That triad is the template to reuse for every other component.**

## CURRENT ARCHITECTURE (actual runtime trace)

```
Jira key
 → JiraClient / Jira MCP  (issue + comments + attachments)        [SKILL Phase 1]
 → Claude normalizes behaviour IN-CONTEXT as prose               [SKILL Phase 2]   <-- not persisted/gated (except DITA)
 → RAG: ask_dita_expert (VM) or backend /api/v1/mcp/lookup_*     [SKILL Phase 3]
   + historical: search_jira_history or live JQL fallback        [SKILL Phase 4]
   + clones: C:/starling, dxml-it-tests, GitHub MCP              [SKILL Phase 5]
   (retrieval is effectively SINGLE-PASS, at Claude's discretion)
 → for DITA tickets only: structured semantic neighbourhood +
   hypotheses in manifest dita_semantics block                   [semantic_relationship_explorer]
 → Claude authors 11-section plan                                 [SKILL Output Contract]
 → run_gates.py: manifest-completeness + validate_test_plan (structure/AC-map)
   + verify_evidence (paths/lines/symbols/attachments/>=3 probes)
   + anti_hardcoding_audit + DITA semantic gate (only if active) + self-tests
 → save output/test-plans/<KEY>.md + index_test_plan.py (jira_qa)
```

### Component inventory (Component / File / Responsibility / Weakness / Action)

- **Jira ingestion, comments, attachments** — `backend/app/services/jira_client.py` + `SKILL.md` Phase 1 / Tool Boundary. Fetches issue/comments/attachments (load_dotenv required for ad-hoc). Weakness: none material. **REUSE.**
- **RAG / ChromaDB / Experience League / DITA 1.2-1.3 / DITA-OT** — `ask_dita_expert` (VM) or backend `/api/v1/mcp/lookup_dita_spec|lookup_aem_guides|lookup_dita_attribute`; `SKILL.md` Phase 3 + `references/rag-query-cookbook.md`, `references/dita-spec-evidence.md`. Weakness: single-pass; no reasoning-directed second retrieval. **EXTEND.**
- **Historical Jira** — `search_jira_history` MCP or live JQL fallback; Phase 4. Weakness: not persisted as structured hypotheses. **REUSE.**
- **Repo/code + automation search** — clones + GitHub MCP; Phase 5, `references/pr-and-repo-evidence.md`, `git-repo-sync.md`. Weakness: findings live in prose, not a structured consumer/contract model. **EXTEND.**
- **Query expansion** — prose guidance only ("exact probes"); `rag-query-cookbook.md`. Weakness: no MissingQuestion-driven query generation. **EXTEND.**
- **Evidence scoring / provenance** — `scripts/verify_evidence.py` (existence/line/symbol/attachment checks, factual not numeric) + AC `[Confirmed]/[Proposed]` labels. Weakness: provenance enforced for citations, not for a behavioral model. **REUSE.**
- **Relation generation / behavioral-or-graph model** — `scripts/semantic_relationship_explorer.py` (SemanticNeighborhood model, relation vocab, coverage-hypothesis gen, cartesian collapse, gate). **DITA-only.** **EXTEND / GENERALIZE.**
- **Final UAC/plan assembly** — Claude authoring per `SKILL.md` Output Contract + Section Rules. Weakness: consumes evidence directly; no required BehaviorModel input. **EXTEND.**
- **Evidence manifest** — JSON consumed by `run_gates.py`/`verify_evidence.py`; already carries `dita_semantics`. Weakness: no `behavior_model` / `coverage_hypotheses` / `dimensions` blocks. **EXTEND.**
- **Quality gates** — `scripts/run_gates.py` orchestrates manifest completeness, `validate_test_plan.py`, `verify_evidence.py`, `anti_hardcoding_audit.py`, DITA semantic gate (only when `active`), self-tests. Weakness: semantic completeness enforced ONLY for DITA. **EXTEND.**
- **Self-tests** — `scripts/test_skill_scripts.py` (39 checks, green). **EXTEND** (add per-phase tests).
- **Structured AC projection** — `scripts/extract_acs.py` (AC → JSON). **REUSE** (downstream of verified hypotheses).

## Answers to the 8 required questions

1. **UAC directly from chunks?** Partly. Claude synthesizes from evidence (not a raw chunk dump) and Phase 2 normalizes behaviour, but that understanding is **in-context prose, not persisted/gated** — except the DITA semantic block. For non-DITA tickets it is closer to evidence → author.
2. **Structured behavioral-understanding stage?** **Only for DITA** (`semantic_relationship_explorer` + `dita_semantics` manifest). Elsewhere it is procedural prose (Phase 2), not a machine-checked model.
3. **Distinguishes retrieved evidence vs verified behavioral fact?** **Yes for DITA** (relations carry `status` CONFIRMED/INFERRED_HIGH_CONFIDENCE/REJECTED/UNRESOLVED + `authority` + `evidence`). Elsewhere partial and unenforced (AC labels + Expected-Behaviour "observation vs inference" rule).
4. **Retrieval once?** Effectively yes — Phase 3 requires ≥3 probes but there is **no enforced MissingQuestion → second-pass retrieval loop**.
5. **"What else should QE investigate?" mechanism?** Only the DITA semantic explorer + Phase-2 cross-customer history mining + the Gap-13..17 prompts. **No generic CoverageHypothesis / MissingQuestion engine.**
6. **Possible scenario → test case immediately?** For DITA: **no** — a hypothesis must reach a terminal status and UNRESOLVED → Open Question is gate-enforced. Generally: instructed but **not machine-verified** outside DITA.
7. **Gate measures semantic completeness or only format/evidence/manifest/self-tests?** Both — but **semantic completeness only for the DITA dimension**. All other dimensions are format/evidence/manifest/self-tests only.
8. **Can a structurally perfect plan miss behavior and still PASS?** **Yes.** Missing a broader reference type, another consumer, an inverse state, or an NFR risk will PASS (no gate covers them). A missed **controlling DITA attribute** is caught **only if** the author set `dita_semantics.active` — if the block is omitted, the DITA gate is skipped and it also PASSES. This is the core gap the phased work closes.

## TARGET INSERTION POINTS

- **Manifest JSON** — the structured hand-off surface. Add `behavior_model`, `coverage_hypotheses`, `dimensions`, `missing_questions`, `evidence_lifecycle` blocks (mirroring `dita_semantics`).
- **`run_gates.py`** — the single enforcement point. Add a BehaviorModel presence check and generalize `evaluate_semantic_gate` into an all-dimensions coverage gate (PASS / NEEDS_REVIEW / FAIL).
- **`semantic_relationship_explorer.py`** — already has model + vocab + gate + cartesian-collapse; generalize (or add a sibling `coverage_model.py`) so non-DITA dimensions reuse the same machinery.
- **`SKILL.md`** — Phase 2 becomes the BehaviorModelBuilder procedure; Phase 3/5 host the explorers + MissingQuestion + directed retrieval; Phase 7/9 host verification + the coverage gate; Output Contract requires the plan to consume the BehaviorModel.
- **`test_skill_scripts.py`** — per-phase regression tests.

## REUSABLE COMPONENTS

JiraClient; ask_dita_expert / backend MCP bridge; search_jira_history / JQL; clone + GitHub-MCP inspection; `verify_evidence.py` (provenance/existence); `validate_test_plan.py` (structure + AC↔scenario↔automation mapping); `extract_acs.py`; **`semantic_relationship_explorer.py` (the model/vocab/status-machine/cartesian-collapse/gate template)**; `anti_hardcoding_audit.py`; the manifest schema; `run_gates.py` orchestration.

## MISSING CORE COMPONENTS (as enforced code, not prose)

- **BehaviorModelBuilder** — a structured, persisted, gated behavior model for all tickets (only DITA neighbourhood exists today).
- **CoverageHypothesisGenerator + generic explorers** — CONTRACT_BOUNDARY, CONSUMER, CONSUMER_POLICY, STATE_PARTITION, TYPE/REFERENCE_ARTIFACT, LIFECYCLE, NFR_RISK (DITA_SEMANTIC_DEPENDENCY already exists as the exemplar).
- **MissingQuestionGenerator + ReasoningDirectedRetriever** — with an evidence lifecycle (RETRIEVED / INSPECTED / USED / REJECTED) and an enforced, bounded second pass.
- **Generic HypothesisVerifier** — the CONFIRMED / INFERRED_HIGH_CONFIDENCE / REJECTED / UNRESOLVED machine exists for DITA relations; generalize to all dimensions.
- **Generalized SemanticCoverageGate** — currently DITA-only; extend to every activated dimension.

## MINIMUM IMPLEMENTATION PLAN (phased; reuse the DITA triad each time)

- **P1 BehaviorModelBuilder** — manifest `behavior_model` block + `behavior_model.py` (represent/validate, dataclass pattern copied from `semantic_relationship_explorer.py`) + `run_gates` presence check (when applicable) + SKILL Phase-2 procedure + tests for UI/backend/config/persistence/publishing/DITA tickets.
- **P2 CoverageHypotheses + Explorers** — generalize the explorer module to a `dimensions` + `coverage_hypotheses` manifest block; DITA stays the exemplar; keep cartesian-collapse; tests for non-activation, discovery, no explosion, no hardcoding.
- **P3 MissingQuestion + DirectedRetriever** — manifest `missing_questions` + `evidence_lifecycle`; gate check that a material question triggered a second, differently-worded probe; bounded loop.
- **P4 HypothesisVerifier** — generalize the status machine; gate: UNRESOLVED must appear in Open Questions, REJECTED excluded from ACs.
- **P5 SemanticCoverageGate (generalized)** — `evaluate_coverage_gate` over all activated dimensions → PASS / NEEDS_REVIEW / FAIL with structured reasons; wire into `run_gates.py`; adversarial tests.
- **P6 Final integration** — Output Contract consumes BehaviorModel + verified hypotheses; before/after examples; TRAIN-only regression tests.
- **P7 Independent audit** — runtime trace, dead-code check, negative-activation, hardcoding scan.

**Four critical (if time-boxed):** BehaviorModelBuilder; CoverageHypothesisGenerator+Explorers; MissingQuestion+ReasoningDirectedRetriever; HypothesisVerifier+SemanticCoverageGate — together they encode "infer the possibility, explore the behavior, verify the evidence, then write the plan." `locktitle`/`MAPREF`/Conditions-Panel/enumdef stay **regression fixtures only**, never production rules.

STOP — no code changed. Awaiting review before Prompt 1.
