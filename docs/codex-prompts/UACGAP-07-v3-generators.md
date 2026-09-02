# Codex task — UACGAP-07: build the missing v3 generators

**Repo:** `aem-guides-dataset-studio` · **Skill:** `.codex/skills/test-plan-generation`
**Source of truth:** `.codex/skills/test-plan-generation` (sync to the other copies with
`scripts/sync_test_plan_skill_copies.py`, SOURCE=.codex; then mirror to `~/.codex` and
`~/.claude`). Byte-match self-test in `scripts/test_skill_scripts.py` enforces copy parity.

## Why this exists

UACGAP-04 shipped the v3 **validators** but no **generators**. Authoring one green v3 UAC
by hand (proved on GUIDES-54348) requires: `evidence_catalog` (SHA-bound code) +
`behavior_model` + `behavior_graph` (BGN nodes/typed edges with provenance, confidence,
verification_state) + `coverage_hypotheses` + `verifications` + `evidence_lifecycle` +
`semantic_closure` (**all 31 `CLOSURE_DIMENSIONS` × every material entity**, wildcards
rejected) + `missing_questions` (one per unresolved closure/verification) + `contract_facts`
+ `issue_domains`, all mutually cross-referenced. `scripts/dimension_synthesizer.py` exists,
but nothing scaffolds `behavior_graph`, `semantic_closure`, or the evidence bindings. So the
record is a machine-scale artifact a human/Claude author cannot produce without hand-typing
~31×N closure records — impractical and against the v3 rule *"do not fabricate to pass a
gate."* Net effect: no real plan can reach v3-green; every plan is stuck REVIEW/non-postable.

## Goal

Make the v3 pipeline authorable end to end by shipping the generators the validators assume.
Each generator produces an **author-editable scaffold with non-committal defaults** — it must
never emit a CONFIRMED verdict, an APPLICABLE closure, or an AC.

## Scope (generic, stdlib only, self-tested, byte-matched across all copies + globals)

1. **behavior_graph scaffolder** — from `behavior_model` entities (processors, attributes,
   configuration, consumers, state) emit `BGN-##` nodes + typed edges. Edge `relation_type`
   from the canonical `RELATION_TYPES`; `provenance` drawn from `evidence_catalog` ids;
   `material` defaulted per node kind; `confidence` in [0,1]; `verification_state =
   INVESTIGATION_CANDIDATE`; `currentness = UNKNOWN`; `applicability = UNRESOLVED` until the
   author confirms.

2. **semantic_closure scaffolder** — for each **material** behavior_graph node, emit one
   record per `CLOSURE_DIMENSION` defaulting `applicability = NOT_APPLICABLE`, `status =
   INVESTIGATED_AND_REJECTED`, with a `disposition_ref` placeholder and a "AUTHOR MUST CONFIRM"
   reason. The author flips only the genuinely applicable ones to APPLICABLE/COVERED (with a
   real `disposition_ref`) or UNRESOLVED (with `open_question_ref`). Never auto-assert
   APPLICABLE — silence must default to a reviewable NOT_APPLICABLE, not a hidden gap.

3. **missing_questions auto-gen** — one contextual question per UNRESOLVED closure record and
   per UNRESOLVED verification: `search_concepts` derived from the entity + dimension,
   `preferred_sources` from the known `PREFERRED_SOURCES` vocab, `why_it_matters` templated,
   `blocking`/`material` defaulted for author review, `open_question_ref` linked.

4. **evidence-binding helper** — given inspected files, compute `evidence_catalog` entries
   (`source_ref` + `source_hash = sha256:<64hex>` verified on disk) and stub
   `evidence_lifecycle` items (`status = RETRIEVED`, valid `source` vocab) for the author to
   mark USED and bind to hypotheses.

5. **authoring entrypoint** — `scripts/v3_scaffold.py --manifest <path>` runs 1–4 against a
   manifest that already has `behavior_model` + `evidence_catalog`, writing the scaffold
   blocks for the author to disposition, after which `run_gates.py` validates. Update
   `references/v3-reasoning-authoring.md` with the scaffold-then-disposition workflow.

## Constraints

- Scaffolds carry `INVESTIGATION_CANDIDATE` / `NOT_APPLICABLE` / `RETRIEVED` defaults ONLY —
  no CONFIRMED, no APPLICABLE, no AC, no USED. The human/Claude author supplies every positive
  verdict with evidence.
- Anti-hardcoding audit must stay green (no concrete GUIDES keys, no construct→construct truth
  tables baked into `.py`; put any vocab in `data/*.json`).
- Keep all existing self-tests green; add self-tests for each generator; mirror to all 5
  in-repo copies via the sync script and to `~/.codex` + `~/.claude`.

## Proof of done

`scripts/v3_scaffold.py` turns a `behavior_model`+`evidence_catalog` manifest into a
`run_gates.py`-green record after the author dispositions the scaffold — with no fabricated
positive verdicts. Demonstrate on a fresh ticket end to end.
