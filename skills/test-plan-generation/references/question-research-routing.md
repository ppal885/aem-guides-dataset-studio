# Mandatory Research Routing for Question-Based Coverage

Material questions are identifiable from the current ticket and its
configuration, but Coverage and the Writer must **not** answer
documentation-dependent questions from inference. Every material question is
classified with a research route *before* any directed research runs, and the
chain stays traceable end to end:

```
Question -> Research Requirement -> Research Request -> Research Evidence
         -> Resolution -> Coverage Decision -> AC
```

## Routing record (`question_research.items[]`)

One item per routed question: `question_ref`, `material`, `research_requirement`,
`research_status`, `research_requests[]`, `research_evidence_ids[]`, and an
optional `coverage_disposition`. One routing entry per question; duplicates are
rejected. When the manifest also declares material `missing_questions`, each of
them must have a routing entry.

## Research requirements

- `NONE` — the current ticket authority is sufficient on its own (for example an
  explicit Human Accepted AC). Terminates as `NOT_REQUIRED`; no research
  requests are issued.
- `DOCUMENTATION` — must consult official product documentation / specification
  sources before coverage finalizes.
- `IMPLEMENTATION` — must consult current code / PR / automation evidence.
- `HISTORICAL` — must consult historical ticket evidence.
- `DOCUMENTATION_AND_IMPLEMENTATION` — both routes required.
- `MULTI_SOURCE` — three or more routes, or a route the classifier cannot name.

## Research statuses

`NOT_REQUIRED`, `PENDING` (classified, never executed), `ANSWER_FOUND`,
`PARTIAL`, `NOT_FOUND`, `SOURCE_UNAVAILABLE`, `CONFLICTED`, `NOT_APPLICABLE`
(non-material questions only).

## Hard rules the gate enforces (`scripts/question_research.py`)

- **Skipped mandatory research fails review.** A material question with a
  requirement other than `NONE` still `PENDING` is a Reviewer failure — Coverage
  must not finalize it, and the Writer must never compensate by authoring an
  answer from inference.
- **Incomplete research keeps the question open.** `PENDING`, `PARTIAL`,
  `NOT_FOUND`, `SOURCE_UNAVAILABLE`, and `CONFLICTED` may only carry an open
  coverage disposition (`OPEN_QUESTION`, `PRODUCT_SCOPE_QUESTION`,
  `ENGINEERING_DESIGN_DECISION`, `PRODUCT_DECISION`,
  `NEEDS_CURRENT_VERIFICATION`).
- **`NOT_FOUND` never asserts the opposite.** Research that executed and found
  no answer cannot ground `INVESTIGATED_AND_REJECTED` or any "the opposite
  behavior holds" claim; absence of evidence is not evidence of absence.
- **`ANSWER_FOUND` proves its request.** The record must cite the research
  request that produced the answer; `NONE`/`NOT_REQUIRED` records cite none.

## DITA construct semantics

When a material question names a DITA construct or governing attribute, route
it from the reusable DITA construct registry rather than a ticket-specific
keyword. The formal DITA source pair is mandatory:

- `DITA_SPECIFICATION` establishes the construct semantics.
- `DITA_OT_DOCUMENTATION` establishes the processor baseline.

The two sources are independent. If either is unavailable from the authorized
evidence bundle, the research status is `SOURCE_UNAVAILABLE`; if one source is
present but has not supplied admitted evidence for the question, the status is
`PARTIAL`. A retrieval hit that merely shares vocabulary does not satisfy this
pair. `NOT_FOUND` still means neither source established an answer, never that
the opposite behavior is true. AEM Guides product documentation may add
product-specific behavior, but it must not be credited for DITA or DITA-OT
behavior it does not establish.

## Worked shape

A documentation-dependent question ("what does the product document for this
mode?") that only matched ticket/configuration evidence is `PARTIAL` at best:
the mandated documentation source was not consulted, so the question stays an
open question even if the ticket wording reads like an answer. The same question
answered from the official documentation source becomes `ANSWER_FOUND` and may
finalize. An explicit Human Accepted AC needs none of this: it records
`NONE`/`NOT_REQUIRED` and proceeds on Jira authority alone.

## Backward compatibility

Absent `question_research` block: clean pass. The canonical runtime produces
these records on every run; the manifest block is how skill-authored plans carry
the same contract.

## Runtime contract (reusable, per question)

The runtime's `ResearchRequirementClassifier` stage is a thin batch loop over
the reusable per-question routing contract in
`app/services/question_research_routing_service.py` (`QUESTION_RESEARCH_ROUTER`).
A later Question Planner invokes the same contract per material question with
`ResearchRoutingRequest` fields `question_id`, `research_need`,
`required_source_type`, `product_context`, and `applicability` — the routing
decision is identical whether it is derived from a planned question's evidence
path or declared explicitly by the caller, and it is never hard-coded at ticket
level.
