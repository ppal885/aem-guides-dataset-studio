# UACGAP-07 implementation and proof status

Status: **PARTIAL**. Generator implementation and automated regression checks pass.
The requested fully author-dispositioned, run_gates-green real-ticket proof has
**not been completed**. Do not interpret a written scaffold, a passing unit test,
or the existing ticket's earlier AC comment as that proof.

## Implemented

- `scripts/v3_scaffold.py --manifest <path>` creates a new editable manifest;
  existing inputs/outputs cannot be overwritten. Reruns preserve authored IDs,
  questions, evidence usage and decisions, and append missing entities/dimensions.
- Evidence-bound graph nodes and typed candidate edges use the canonical enums.
  Role vocabulary, per-kind material defaults and question leads are in
  `scripts/data/v3_scaffold_policy.json`, not product-specific Python rules.
- All generated nodes/edges have confidence 0, currentness UNKNOWN,
  applicability UNRESOLVED, and verification_state INVESTIGATION_CANDIDATE.
- Every material node gets all 31 closure dimensions, with explicit review-only
  N/A/rejected placeholders. Non-material context nodes are excluded. No wildcard
  closure or truncated three-digit ID limit remains.
- Each unresolved closure/verification produces a contextual question stub with
  an existing OQ link, canonical sources and entity-derived search concepts.
  Python stubs are labelled PYTHON_SCAFFOLD, never Claude-authored questions.
- Selected local files get actual SHA-256 bindings and RETRIEVED lifecycle rows.
  No query, authority, second pass or USED event is fabricated. Changed bytes do
  not overwrite older evidence hashes.
- Graph, closure and evidence-use review placeholders are rejected by the normal
  gates, including attempts to fill only a disposition ID or flip a review flag.

No generator authors ACs, positive verification verdicts or acceptance promotions.
No backend runtime or product repository code was changed. No Jira writes,
commits or pushes were performed. Existing unrelated worktree changes retained.

## Verification

Runtime HEAD during this run: `219a158a93af650ebdddce804f5628a35b051cb8`
(working tree includes these uncommitted skill changes).

- All five repository copies and both global installs: ALL SELF-TESTS PASSED.
- 164 enforced files byte-match across all seven copies. SKILL.md and
  test_skill_scripts.py also byte-match. Details: proof-guides-54348/copy-parity.json.
- Bundle SHA-256: `f193a209b3a10307c3bc09180c1644e5dd008bcf0d15144ca9ded6f2306a5951`.
- Production hardcoding audit: PASS.
- skill-creator quick validation: PASS.
- git diff --check: PASS (existing Git CRLF-conversion warnings only).
- Backend benchmark-schema and evidence-graph-parity regression tests:
  17 passed, five pre-existing deprecation warnings. This is not a live golden
  benchmark or a Claude Desktop execution claim.
- Reviewed synthetic graph/closure/verification/disposition integration passes the
  canonical semantic validator without adding an AC or automatic positive result.
  That proves schema compatibility, not real-ticket completeness.

## Selected-ticket run

The user selected the existing GUIDES-54348 example. This is a new run on that
ticket, not a fresh-ticket or blind evaluation. The live issue was fetched.
Only its description is retained as acceptance input; the comment explicitly
labels its ACs AI-generated and not yet Human-reviewed.

`proof-guides-54348/manifest.input.json` contains the source-grounded model and
catalog. Running the production CLI wrote `manifest.input.scaffold.json` with:

- 14 nodes and 13 candidate edges;
- 434 explicit closure records (14 x 31), zero provenance gaps;
- four verified file hashes and RETRIEVED lifecycle rows;
- no fabricated verdicts, acceptance promotions, or questions without unknowns.

The separate `author-review.json` records one actual unresolved scope decision.
`replay_scaffold.py` applies that review and reruns the production generator.
The resulting `manifest.author-progress.json` has two linked contextual Missing
Questions: one for the unresolved closure and one for the unresolved verification.
It preserves all other pending decisions. The author still needs to complete
those decisions; the example does not automatically bulk-reject them.

The available candidate branch changes refresh-event routing, whereas the live
bug describes automatic population on insertion. No inspected source or runtime
execution established that those are the same fix. That remains OQ-01. See
`source-review.md`, `retrieval-status.json` and the seven clone-sync reports.

## Full-gate result and remaining work

- Replaying the old complete ticket artifacts under current gates produced 34
  failures: missing contract/domain/disposition/promotion blocks, invalid graph
  bindings/fields, and missing questions. Its eight legacy reasoning waivers also
  make it non-postable. This was the pre-existing artifact, not a new green plan.
- The new, deliberately unfinished scaffold was also submitted to the full gate
  with the old plan as an incompatibility check. It correctly failed (1032
  messages, many repeated per-row review errors), and its receipt is non-postable.
  This pairing is not presented as a completed plan: the old AC/OQ set has not
  been reconciled with the new author-progress manifest.
- Finish source-backed author dispositions, real directed retrieval for its
  Missing Questions, the remaining contract/domain/applicability blocks and
  accepted/proposed AC mappings. Then create a matching plan/combined artifact
  and run full gates with self-tests. Do not waive the missing reasoning or claim
  every generated N/A row was investigated.
- The refresh-versus-insertion scope discrepancy needs engineering/product
  clarification or further implementation/runtime evidence. The skill's
  clarification-gate.md requires the affected acceptance decision to remain open;
  it does not authorize inventing an answer to produce a green receipt.

## Reproduction

From the repository root (choose a new output filename if it already exists):

```text
py -3.11 .codex/skills/test-plan-generation/scripts/v3_scaffold.py --manifest analysis/uacgap07/proof-guides-54348/manifest.input.json --out analysis/uacgap07/proof-guides-54348/manifest.replayed.json
py -3.11 .codex/skills/test-plan-generation/scripts/test_skill_scripts.py
py -3.11 .codex/skills/test-plan-generation/scripts/audit_production_hardcoding.py
```

The full authoring procedure is in the skill's
`references/v3-reasoning-authoring.md`. Its scaffold exit 0 is not gate approval.
