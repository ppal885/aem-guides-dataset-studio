# Contributing to the `test-plan-generation` skill

This skill exists in **four copies** kept consistent by a byte-match self-test.
Read this before editing any script or reference.

## The four copies

| Copy | Path | Role |
|---|---|---|
| **Canonical** | `skills/test-plan-generation` | Source of truth. Edit here first. |
| **`.claude` variant** | `.claude/skills/test-plan-generation` | Must byte-match canonical for the enforced file set. |
| **`.codex` variant** | `.codex/skills/test-plan-generation` | Must byte-match canonical except `codex_only_extensions` (SKILL.md, references/quality-gate-checklist.md, scripts/test_skill_scripts.py). |
| **Global executing copy** | `~/.claude/skills/test-plan-generation` | The copy that actually runs when generating UACs. **Separate lineage** — apply changes logically; never `cp` canonical's `test_skill_scripts.py` onto it (its sibling modules can differ). |

`test_skill_scripts.py::_find_repo_root()` finds the repo, then the
"readability contract matches canonical" checks compare the `.claude` and `.codex`
variants **byte-for-byte** against canonical `skills/` for an enforced set
(SKILL.md, several references, and scripts incl. `ac_presentation.py`,
`ac_contract.py`, `extract_acs.py`, `render_compact_view.py`,
`validate_test_plan.py`, `test_skill_scripts.py`). `run_gates.py` and new gate
modules are not byte-enforced but should be kept consistent anyway.

## Editing safely

1. Make the change in **canonical `skills/`** first.
2. Mirror the enforced files to `.claude` and `.codex`.
3. Apply the same change logically to the global `~/.claude` copy.
4. Verify **all four**:
   ```bash
   python <copy>/scripts/test_skill_scripts.py   # expect: ALL SELF-TESTS PASSED
   ```
5. Run the full gate against a real manifest (catches caller/definition drift that
   the standalone self-test misses):
   ```bash
   python skills/test-plan-generation/scripts/run_gates.py \
     --plan <body.md> --combined <plan+appendix.md> --manifest <manifest.json>
   ```
   Treat exit code 0 as the sole pass signal.

> Two real breakages seen this way: (a) a refactor updated canonical + `.codex` but
> left `.claude` stale, failing the byte-match test at HEAD; (b) `run_gates.py`
> called two self-test functions the refactor had renamed in `test_skill_scripts.py`,
> so every *full* gate run failed while the standalone self-test passed. Always run
> the full gate, not just the standalone self-test.

## Adding a new gate (the wiring pattern)

Every gate follows the same shape and must be registered in **two** places:

1. Create `scripts/<name>.py` with `validate(...)` (or `validate_block`) returning a
   `list[str]` of problems, `is_present(manifest)`, and `summarize(manifest)`.
   Backward-compatible: an absent block returns `[]` (clean pass).
2. `test_skill_scripts.py`: `_load` the module, add `def test_<name>()`, and call it
   in `main()`.
3. `run_gates.py`: `_load` the module, add a body check
   (`failures.extend(f"[<name>] {p}" for p in <mod>.validate(data))`), and add
   `self_tests.test_<name>()` to the self-test block.
4. Add a `references/<name>.md` explaining the block and its invariants.
5. Mirror to all four copies; verify each is green.

Keep gates **generic** (no Jira-specific or feature-specific literals — the
anti-hardcoding audit scans the scripts) and **stdlib-only**.

## Gates added for the UAC-fidelity / evidence-quality work

All backward-compatible (absent block = clean pass), opt-in via the named manifest block:

| Gate | Manifest block | Enforces |
|---|---|---|
| `fluffyjaws_evidence.py` | `fluffyjaws` | FluffyJaws = SUPPORTING_DISCOVERY only, must re-ground into a first-class source, never sole basis for a Covered AC, no FJ→AC path, no secret-shaped keys. Reached via the native Claude enterprise connector (see `docs/fluffyjaws_setup.md`). |
| `temporal_evidence.py` | `temporal_evidence` / `temporal_applicability` on items | 7-state version applicability; UNKNOWN/non-current can't silently support an AC; SUPERSEDED must name what supersedes it; normative authority not superseded by recency alone. |
| `evidence_conflict_resolver.py` | `conflict_resolution` | Question-specific authority; code-vs-contract mismatch is a DEFECT (never "implementation wins"); FluffyJaws never wins; non-settling states can't silently support an AC. |
| `scope_applicability.py` | `scope_applicability` | No scope expansion on name-only bases; in-scope needs semantic/impl applicability + evidence; target-surface-first; UNRESOLVED_SCOPE → Open Question. |

See each gate's `references/*.md` for field shapes.

## The v3 canonical semantic pipeline (manifest schema `aem-guides-evidence-manifest-v3`)

Declaring any of `contract_facts`, `issue_domains`, `behavior_graph`,
`semantic_closure`, `acceptance_promotions` activates the full cross-validated
pipeline (`validate_canonical_semantic_pipeline`). Highlights:

- `contract_facts` literals must be verbatim substrings of a grounded source
  (`issue.*` fields or a hash-bound `contract_source_records` artifact).
- `behavior_graph` edge `authority` must be valid for its `subject` per
  `data/authority_policy.json`; provenance must reference known evidence ids.
- `semantic_closure` needs a record for **every material node × all closure
  dimensions**; UNRESOLVED records need a linked `missing_question` + a second-pass
  `evidence_lifecycle` entry.
- `acceptance_promotions` promotes one candidate per visible plan AC;
  `PRODUCT_CONTRACT` subject + human/Jira acceptance authority; every promotion ties
  to a `dispositions` finding.

`output/test-plans/GUIDES-53897-*` is a complete worked example.
