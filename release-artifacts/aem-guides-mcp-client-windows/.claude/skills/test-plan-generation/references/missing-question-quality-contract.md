+# Claude Missing Question Quality Contract

Use this contract whenever Claude Desktop is asked to produce QE Missing Questions
for the canonical AEM Guides test-plan runtime.

## Runtime ownership

- Claude Desktop is the only LLM that writes contextual natural-language Missing
  Questions.
- The Python backend prepares the investigation context and deterministically
  validates, deduplicates, routes, resolves, and traces those questions.
- The backend must not invoke another LLM or silently present its compatibility
  fallback as Claude output.
- Pattern MCP proposes investigation relationships. It is not acceptance or
  product-decision authority.

## Two-part handoff

The canonical pipeline result exposes:

- `qe_investigation`: the hash-identified preparation, including current facts,
  scope, domains, changed surfaces, signals, matched Human-backed patterns,
  mandatory family decisions, already-investigated dimensions, constraints, and
  retrieval hints;
- `missing_question_quality`: submitted and accepted questions, deterministic
  decisions, and family satisfaction;
- `missing_question_resolutions`: evidence-resolved, unresolved-Human, pending,
  or quality-rejected outcomes.

When a caller supplies Claude questions, send a
`ClaudeMissingQuestionSubmission` bound to the exact `preparation_id` (and to
the request ID when available). The REST pipeline accepts it as
`claude_question_submission`. The local canonical adapter accepts the same JSON
with `--claude-question-submission`.

Never copy a submission from another run. Never edit its derived opaque IDs.
If the preparation changes, regenerate the questions.

## Required question fields

Every Claude question must provide:

- `family_id`
- `question_text`
- `why_it_matters`
- `linked_change_surface`
- `linked_behavior_or_state`
- `relationship_being_tested`
- `expected_evidence_type`
- `preferred_provider`
- `materiality`
- `blocking_status`
- `active_domain`
- `active_reasoner`
- `linked_pattern_ids`
- `current_fact_refs`
- `expected_oracle`
- `resolution_status`
- `origin=CLAUDE_DESKTOP`

The canonical model derives `question_id`. The retained `question` field is a
compatibility alias and must equal `question_text`.

## Question-writing rules

A question is valid only when it:

1. names the current changed behavior or state;
2. asks about the activated family's exact relationship;
3. can drive retrieval from a declared evidence source;
4. asks for evidence and does not assert the answer;
5. does not assume a product decision;
6. is specific enough to produce a bounded query;
7. preserves the intended material family;
8. does not combine different material relationships into a vague umbrella;
9. does not merely repeat Jira wording; and
10. is not already answered by authoritative current evidence.

Write natural, plain English. Do not use a fixed question template. The current
facts, changed surfaces, family relationship, and expected oracle must determine
the wording.

## Evidence before Human escalation

A valid question is investigated through the authority-appropriate provider
before it becomes a Human Open Question:

- current Jira, comments, and attachments for current product contract;
- GitHub MCP for implementation applicability;
- DITA 1.2 or 1.3 for normative DITA semantics;
- DITA-OT for transformation/reference semantics;
- FluffyJaws or Experience League for documented AEM Guides behavior;
- configuration and tests when authoritative for that question.

Pattern MCP may guide discovery but cannot answer the product contract.

When authoritative evidence already resolves the family, record
`RESOLVED_BY_EVIDENCE`; do not ask the Human. A material unresolved question may
become a Human question only with one of the generic unresolved classes defined
by the canonical schema.

## Family completeness and deduplication

An activated mandatory family is satisfied only by:

- at least one accepted contextual question for that family; or
- a recorded evidence-backed resolution for that family.

Rejected or generic questions never satisfy a family. An unsatisfied activated
family must fail the behavioral completeness gate with
`MATERIAL_DIMENSION_LOST`.

Deduplicate only when family, relationship, current behavior, and evidence intent
are semantically equivalent. Merge provenance for a true duplicate. Do not merge
governing semantics, downstream consumers, configuration, lifecycle, or other
different material relationships merely because they mention the same feature.

## Safe failure

If a provider is unavailable, preserve the material question as unresolved.
Never fabricate an answer, silently drop the family, or turn Pattern MCP analogy
into acceptance truth. Question handoff text is bounded and rejects control
characters and credential-shaped content.

