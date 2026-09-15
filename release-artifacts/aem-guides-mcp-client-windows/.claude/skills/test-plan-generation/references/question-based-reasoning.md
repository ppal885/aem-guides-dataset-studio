# Question-Based UAC Reasoning (Planner → Research Router → Resolver)

Structured reasoning stages layered onto the existing agentic test-plan
workflow. The existing agents keep their roles — Evidence Agent, Doc
Researcher, Writer, Reviewer — and the **Question Planner** and **Question
Resolver** are coordinator/reasoning stages, not new autonomous agents.
Enforced by `scripts/question_planner.py` and `scripts/question_resolver.py`;
research routing between them is the `question_research` contract (see
`references/question-research-routing.md`).

```
Jira + attachments
    → Evidence Agent
    → Question Planner        (material questions)
    → Research Router         (research_requirement / research_status)
    → Doc Researcher / other authorized evidence routes
    → Question Resolver       (terminal resolution per question)
    → Coverage Reasoner input
    → Writer
    → Reviewer
    → Final UAC
```

## Question record (`question_plan.items[]`)

Every material question carries: `question_id`, `category`, `question`,
`why_material`, `triggering_evidence_ids`, `acceptance_impact`,
`applicability` (`APPLICABLE` / `NOT_APPLICABLE` / `UNRESOLVED`),
`research_requirement` (the R1 vocabulary `RESEARCH_NOT_REQUIRED` /
`DOC_RESEARCH_REQUIRED`, or the richer research-routing vocabulary), optional
`research_topics[]`, and `status` (`PLANNED` / `ROUTED` / `RESOLVED` /
`ESCALATED`).

Initial categories (closed vocabulary): `EXPECTED_OUTCOME`, `STATE_TRANSITION`,
`PERSISTENCE`, `NEGATIVE_CONTRACT`, `SCOPE`, `VARIANT`, `ENTRY_PATH`,
`CONFIGURATION`, `APPLICABILITY`, `PRESERVATION`, `ERROR_RECOVERY`, `SCALE`,
`COMPATIBILITY`.

**Do not emit every category for every ticket.** Plan only questions whose
answers could materially improve acceptance understanding or coverage; a
near-complete category carpet fails review.

## Bounded question budget

`question_plan.budget` (default 12) bounds the main plan. If the material
questions exceed it, **never silently discard them**: move the excess into
`question_plan.overflow` with `state: QUESTION_BUDGET_EXCEEDED` and an
`escalation` note naming who/what the overflow escalates to. Overflow questions
keep the full question record shape.

## Resolution record (`question_resolutions.items[]`)

One terminal resolution per planned question. Canonical Q1 shape:
`question_id`, `disposition` (`ANSWERED`, `PARTIALLY_ANSWERED`,
`ACCEPTANCE_TBD`, `INVESTIGATION_ONLY`, `NOT_APPLICABLE`, `DUPLICATE`,
`CONFLICTED`), `answer` (the claim text), `source_ids`, `source_authority`,
`applicability`, `limitations[]`, `contradictions[]`, `decision_reason`
(required — every material semantic decision is recorded with its reason so
downstream stages consume the artifact instead of reconstructing the answer
from raw ticket text), and `research_ids[]` binding the admitted research that
produced the answer. The earlier nested shape (`question_ref` + `status` + an
`answer` object holding the same retention fields) is accepted unchanged.

- `PARTIALLY_ANSWERED` must record what remains unresolved in `limitations`.
- `CONFLICTED` must retain the competing claims in `contradictions`.
- `ACCEPTANCE_TBD` is allowed **only** when different plausible answers
  materially change acceptance behavior / scope / configuration /
  applicability / compatibility / preservation — it requires `material_impact`
  (one or more of those areas) and at least two `plausible_answers`.
- `DUPLICATE` requires `duplicate_of` (the surviving question) and preserves
  all of the duplicate's triggering evidence IDs on that surviving question.
- `NOT_APPLICABLE` requires a `reason`.
- Root cause, diagnostics, and implementation mechanics
  (`investigation_topic`) are normally `INVESTIGATION_ONLY`; any other status
  requires an explicit `acceptance_relevance` justification, and they never
  become `ACCEPTANCE_TBD` merely because the uncertainty matters to
  engineering.

## Hard rules

1. A question is not an AC.
2. An answer is not automatically an AC.
3. Actual Result cannot establish Expected Result.
4. Do not reverse a reported failure to invent desired behavior.
5. A suspected root cause does not become acceptance behavior.
6. An attachment observation does not establish desired behavior without
   authority.
7. Historical Jira does not automatically establish current behavior.
8. NOT_FOUND is not negative proof.
9. Required research cannot be skipped — including R1-required research: a
   documentation-requiring material question depends on the existing Doc
   Researcher routing contract (`doc_research`, see
   `references/doc-research-routing.md`). It cannot resolve
   ANSWERED/PARTIALLY_ANSWERED while the doc routing has no terminal result; a
   `RESEARCH_NOT_REQUIRED` doc routing contradicts documentation-requiring
   questions; `DOC_RESEARCH_UNAVAILABLE` forbids documentation-based answers;
   `DOC_RESEARCH_CONFLICTED` keeps the question CONFLICTED. A documentation
   answer must cite the admitted `research_ids` that produced it — stale or
   wrong-bound research cannot answer another question.
10. An equal-authority conflict remains unresolved — an `ANSWERED` resolution
    carrying contradictions must record the higher-authority basis in
    `conflict_resolution`, otherwise the question stays CONFLICTED.
11. PARTIAL research cannot produce a fully confirmed answer — at most
    PARTIALLY_ANSWERED for the established portion.
12. ACCEPTANCE_TBD only under the material-impact condition above, and never
    for root-cause/diagnostic/mechanics uncertainty.
13. Root cause / diagnostics / implementation mechanics are normally
    INVESTIGATION_ONLY.

## Writer boundary

The Writer must not receive raw unresolved questions as instructions to invent
behavior; it consumes only downstream admitted behavior from the existing
reasoning path. Questions themselves are never rendered directly as ACs (the
coverage gate rejects a coverage decision whose text is the question text).
ACCEPTANCE_TBD questions reach the final Open Questions contract only through
the existing approved downstream path.

Structurally, none of `ACTUAL_RESULT`, `SUSPECTED_ROOT_CAUSE`,
`ATTACHMENT_OBSERVATION`, `HISTORICAL_JIRA`, or `AI_INFERENCE` may be the
`source_authority` of an `ANSWERED` claim; and when the `question_research`
block is present, a question whose required research is `PENDING` or
`NOT_FOUND` cannot resolve `ANSWERED`/`PARTIALLY_ANSWERED`.

## Preserved invariants

These stages add traceable structure only. Source authority,
observation-vs-requirement separation, exact Jira intake, attachment evidence
handling, Doc Researcher routing, the Writer language contract, Reviewer
independence, and draft-only behavior remain exactly as defined by the rest of
the skill.

## Chain integrity

When the blocks coexist: every planned material question must have a
`question_research` routing entry and a terminal `question_resolutions` entry;
a resolution for a question that was never planned fails; a planned question
with no resolution fails. Questions are never silently dropped.

## Backward compatibility

Absent `question_plan` / `question_resolutions` blocks: clean pass.
