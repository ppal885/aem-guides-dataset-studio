# Doc Research Routing (Existing UAC Doc Researcher)

The UAC Doc Researcher (`agents/uac-doc-researcher.md`) exists, but the
agentic workflow could previously continue without invoking it even when
existing product documentation materially affects acceptance reasoning. This
contract — recorded after Evidence in the manifest `doc_research` block and
enforced by `scripts/doc_research_routing.py` — makes the routing decision
explicit and auditable. It introduces no new agent and changes no source
authority.

## Routing states (`doc_research.routing.state`)

- `RESEARCH_NOT_REQUIRED` — documentation would not materially change
  acceptance reasoning (e.g. an explicit authoritative Human Accepted AC is
  sufficient). Requires `not_required_reason`; carries no triggers or results.
- `DOC_RESEARCH_REQUIRED` — a material trigger fired. **HARD GATE**: without a
  terminal Doc Researcher result, Coverage/Writer MUST NOT proceed.
- Terminal states: `DOC_RESEARCH_COMPLETED`, `DOC_RESEARCH_PARTIAL`,
  `DOC_RESEARCH_UNAVAILABLE`, `DOC_RESEARCH_CONFLICTED`.

## Material triggers (`doc_research.routing.triggers`)

`CHANGES_DOCUMENTED_FUNCTIONALITY`,
`EXISTING_BEHAVIOR_MUST_BE_UNDERSTOOD_OR_PRESERVED`,
`CONFIGURATION_SEMANTICS_UNESTABLISHED`,
`APPLICABILITY_NEEDS_CONFIRMATION`,
`BACKWARD_COMPATIBILITY_MATERIAL`,
`TERMINOLOGY_MATERIAL`,
`JIRA_EVIDENCE_INSUFFICIENT_DOC_MAY_ANSWER`,
`EVIDENCE_AGENT_REQUEST`.

Never invoke the Researcher merely because related documentation exists:
`DOC_RESEARCH_REQUIRED` must declare at least one trigger.

## Result contract (`doc_research.results[]`)

`research_id`, `status` (terminal state matching the routing state), `topics[]`,
`findings[]`, `source_ids[]`, `applicability`, `limitations[]`, `conflicts[]`,
and `produced_by: uac-doc-researcher` — the coordinator/main agent must not
impersonate the Researcher.

Every finding carries `claim`, `source_id`, `source_type`, `authority`,
`applicability`, `currentness`/version when available, and `evidence_role`:

- `EXISTING_BEHAVIOR` — what the documentation establishes today.
- `REQUIREMENT_CLARIFICATION` — documentation clarifying the ticket's
  requirement.
- `SUPPORTING_CONTEXT` — background only, never acceptance truth.

## Researcher boundaries

The Researcher must NOT write ACs, decide final acceptance scope, override a
Human Accepted AC, infer new behavior from old documentation, promote nearby
functionality, or treat NOT_FOUND as evidence of the opposite behavior. A
result with no findings is UNAVAILABLE or PARTIAL (with `limitations`), never
COMPLETED; PARTIAL must name what is missing; CONFLICTED retains the competing
claims.

## Reviewer failures

- required research was skipped (the hard gate);
- a finding cites documentation the research never retrieved (`source_id`
  missing from `source_ids`);
- PARTIAL research is represented as complete (routing/result status
  mismatch);
- documentation is used to support behavior it does not establish (an
  `EXISTING_BEHAVIOR` finding linked via `supports_behavior_ref` to a
  `NEW_REQUIREMENT` behavior fails).

## Writer admission

The Writer receives only admitted research (`admitted_research_ids`, which must
reference real results) through the existing reasoning path — never arbitrary
raw search results. `RESEARCH_NOT_REQUIRED` admits nothing.

## Backward compatibility

Absent `doc_research` block: clean pass.
