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
`research_requirement` (the research-routing vocabulary), and `status`
(`PLANNED` / `ROUTED` / `RESOLVED` / `ESCALATED`).

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
`question_plan.overflow` with `state: OVERFLOW` and an `escalation` note naming
who/what the overflow escalates to. Overflow questions keep the full question
record shape.

## Resolution record (`question_resolutions.items[]`)

One terminal resolution per planned question: `question_ref`, `status`
(`ANSWERED`, `PARTIALLY_ANSWERED`, `ACCEPTANCE_TBD`, `INVESTIGATION_ONLY`,
`NOT_APPLICABLE`, `DUPLICATE`, `CONFLICTED`), and for answering statuses a
retained `answer` with `claim`, `source_ids`, `source_authority`,
`applicability`, `limitations[]`, `contradictions[]`.

- `PARTIALLY_ANSWERED` must record what remains unresolved in `limitations`.
- `CONFLICTED` must retain the competing claims in `contradictions`.
- `ACCEPTANCE_TBD` is allowed **only** when different plausible answers
  materially change acceptance behavior / scope / configuration /
  applicability / compatibility / preservation — it requires `material_impact`
  (one or more of those areas) and at least two `plausible_answers`.
- `DUPLICATE` requires `duplicate_of` (the surviving question).
- `NOT_APPLICABLE` requires a `reason`.
- Root cause, diagnostics, and implementation mechanics
  (`investigation_topic`) are normally `INVESTIGATION_ONLY`; any other status
  requires an explicit `acceptance_relevance` justification.

## Hard rules

1. A question is not an AC.
2. An answer is not automatically an AC.
3. Actual Result cannot establish Expected Result.
4. Do not reverse a reported failure to invent desired behavior.
5. A suspected root cause does not become acceptance behavior.
6. An attachment observation does not establish desired behavior.
7. Historical Jira does not automatically establish current behavior.
8. NOT_FOUND is not negative proof.
9. Required research cannot be skipped.
10. ACCEPTANCE_TBD only under the material-impact condition above.
11. Root cause / diagnostics / implementation mechanics are normally
    INVESTIGATION_ONLY.

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
