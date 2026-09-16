# Requirement Lineage (end-to-end AC traceability)

After evidence sufficiency, coverage reasoning, and semantic equivalence have
produced the admitted coverage package, requirement lineage mechanically
traces every final AC back to the evidence that justified it:

Original Source -> Evidence -> Question -> Research (when required) ->
Question Resolution -> Sufficiency -> Coverage Decision -> Equivalence Group
(when applicable) -> Written AC -> Reviewer Decision.

Recorded in the manifest `requirement_lineage` block and validated by
`scripts/requirement_lineage.py`; follows
`references/coverage-equivalence.md`. The gate validates **referential
integrity** across the existing R1/Q1/S1/C1/E1 blocks. It adds traceability
and integrity only — it introduces no new acceptance semantics, and lineage
proves **provenance and structural integrity, not semantic correctness**.

## ID strategy

Existing production IDs are preserved and referenced without rewriting:
`question_id`, `research_id`, `coverage_id`, `equivalence_id`, `ac_id`. The
lineage block adds two conceptual families: `SRC-` (original admitted source)
and `REV-` (Reviewer decision bound to an exact Writer revision).

## Blocks

- `sources[]` — one row per original source: `source_id`, `source_type`
  (`JIRA_ACCEPTANCE_CRITERIA`, `JIRA_EXPECTED_RESULT`, `JIRA_DESCRIPTION`,
  `JIRA_COMMENT`, `JIRA_ATTACHMENT`, `OFFICIAL_PRODUCT_DOC`, `SPECIFICATION`,
  `IMPLEMENTATION`, `HISTORICAL_JIRA`, `OTHER_APPROVED_SOURCE`),
  `source_locator`, optional `source_version`, optional `authority_role`
  (reusing the existing answer-authority vocabulary), optional
  `applicability`, `status` (`ADMITTED` / `RETRIEVED` / `REJECTED` /
  `UNAVAILABLE`), and `evidence_ids`.
- `ac_lineage[]` — one row per final AC: `ac_id`, `coverage_refs`,
  `equivalence_refs`, `question_refs`, `evidence_refs`, `research_refs`,
  `source_refs`, `writer_revision`, `source_versions`, and
  `human_source_line`.
- `tbd_lineage[]` — one row per unresolved ACCEPTANCE_TBD question:
  `question_ref`, `research_refs`, `research_status` (`PARTIAL` / `NOT_FOUND`
  / `SOURCE_UNAVAILABLE` / `CONFLICTED`), `sufficiency`, `disposition`,
  `reason_unresolved`, `evidence_refs`, `source_refs`. Unsuccessful research
  stays visible instead of being erased; a TBD row never references a
  confirmed AC.
- `reviews[]` — one row per Reviewer decision: `review_id`,
  `reviewed_writer_revision`, `ac_ids`, `decision` (`APPROVED` / `REJECTED` /
  `CHANGES_REQUESTED`), `failures`, `upstream_refs`.

## Integrity rules

- Every referenced ID exists in the producing block, and its type is valid
  for the relation (e.g. `research_refs` name Doc Researcher results, not
  question-research request IDs).
- Every Writer-package AC has complete lineage; the Writer cannot fabricate
  lineage (no invented coverage, research, question, or source IDs).
- AC lineage preserves the exact question/evidence/research unions of the
  coverage decisions and equivalence groups it references; unrelated or
  unused retrieved evidence never contaminates an AC, and an unused
  `RETRIEVED` source never appears in a Source line.
- A `QE_REGRESSION` member of an equivalence group never becomes acceptance
  authority through the group: an AC bound to the group must still bind an
  ACCEPTANCE-class member coverage decision.
- `human_source_line` derives only from the admitted supporting source
  lineage and never contains internal IDs or machinery (`Q-`, `COV-`,
  `SUF-`, `EQ-`, `DR-`, `EV-`, `SRC-`, `REV-`, `MERGE-`,
  `canonical_outcome`, attestation jargon).
- The Reviewer binds to the exact Writer revision: a Writer change makes the
  review stale (never reused across changed drafts), and a source-version
  change invalidates the dependent lineage.
- A question never cites nonexistent evidence or research.

## Writer / Reviewer binding

The Writer only emits ACs whose coverage lineage is admitted and complete;
the human Source line is derived from `source_refs`, never invented. The
Reviewer verifies lineage completeness and staleness and routes failures
upstream instead of repairing them. `trace_ac(manifest, ac_id)` renders the
"why is this AC here" chain for inspection.

## Backward compatibility

Absent `requirement_lineage` block: clean pass.
