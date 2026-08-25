# Plain-Language Acceptance Criteria

## Goal

Write acceptance criteria that a tester can understand on the first read. Keep the product meaning exact, but remove sentence structures that make readers stop and re-read.

## Required Style

- Use the canonical one-line Given | When | Then | Evidence format only in the hidden validated record.
- Never show Given, When, Then, pipes, sphere, or Evidence to the user. Chat uses `AC-##` with `Starting point`, `Action`, and `Expected result`; Jira uses the same lines and also keeps `[Proposed]` or `[Confirmed]`.
- Write each Given, When, and Then value as a complete plain-language clause because the shared projector copies it verbatim. Do not rely on the hidden field label to make a fragment understandable.
- Give each AC one purpose.
- Do not add a summary AC that repeats outcomes already covered by earlier criteria. Use Test Scenarios to show the combined DITA/non-DITA or positive/negative matrix.
- Use Given only for the minimum setup needed for that purpose.
- Use When for one trigger or user action.
- Use Then for one observable result.
- Aim to keep Given to 20 words or fewer and When to 12 words or fewer.
- Aim to keep Then to 20 words or fewer. More than 28 words, more than two sentences, or many stacked clauses in any Given, When, or Then field is a loud review finding; only an outcome over 45 words is a hard failure.
- Split the AC when two results can pass or fail independently.
- Do not remove accepted meaning to meet a length target. Split a long accepted UAC into smaller Confirmed ACs and preserve every source-clause mapping.
- Prefer short words: use, before, after, if, and for.
- Keep exact product names, UI labels, API paths, configuration keys, enum values, and error codes when they matter.
- Avoid semicolons, double negatives, parenthetical explanations, and long comma-separated lists.
- Move setup steps, matrices, implementation details, and background explanations to Test Scenarios or Open Questions.
- A code change can reveal an extra behavior, such as a new fallback or error response, but it does not prove that product scope approved that behavior. Keep it Proposed and ask the scope question unless Jira, accepted UAC, or an explicit product decision approves it.
- Keep long examples, extension lists, implementation explanations, and parenthetical exceptions outside the tester sentence. Put them in Test data, a scenario, or a `Note for developer:` bullet.
- Name the exact screen. Move code, file paths, implementation jargon, and performance internals to a `Note for developer:` bullet in an existing technical section instead of tester-facing AC text. Preserve a source-mandated exact identifier when fidelity requires it, and expose the readability tradeoff for review.
- Preserve human reviewer wording as the semantic baseline. Simplify its sentence structure without changing the actor, scope, UI label, timing, fallback, exact path, or product outcome.
- If inspected code conflicts with human feedback, keep the requested meaning and add an Open Question that states the conflict. Do not silently replace the requirement with current implementation.
- Do not refer to another criterion such as AC-04 inside Given, When, or Then. State the required fallback or result directly so each criterion stands alone.
- Review an existing or AI-supplied AC set through the full evidence manifest and `run_gates.py` pipeline. A conversational review alone is not a gated result.
- Resolve every readability and implementation-scope review before posting. The gate can still exit successfully for backward compatibility, but its receipt remains non-postable.

## Human-Facing Format

The renderer and Jira poster produce this deterministic view from the hidden record:

```text
- AC-01
  - Starting point: a DITA-OT publish returns a generation log.
  - Action: the publish workflow completes.
  - Expected result: the application logger records one generation-log payload.
```

Do not manually paraphrase this view. Keeping the three verified clauses separate is easier to scan and preserves technical terms exactly.

## Quick Review

Before accepting an AC, ask:

- Can I explain its purpose in one short sentence?
- Does When contain only one trigger?
- Does Then contain only one result?
- Can any shorter common word replace a formal phrase?
- Would two smaller ACs be easier to test?

## Examples

### Publishing log

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Integration) Given a publish operation is started for a map for which DITA-OT logging is enabled and a custom logger and external log sink have been configured | When output generation and all downstream metadata processing have completed | Then the same generated log information is written only once in the application log and customer log sink while the output and history remain unchanged | Evidence: Jira description for the current issue.

Easy-to-read internal records; the user sees the three-line format above:

- AC-01 [Proposed]: (Basic) Given a DITA-OT publish returns a generation log | When the publish workflow completes | Then the application logger records one generation-log payload | Evidence: Jira description for the current issue.
- AC-02 [Proposed]: (Integration) Given the customer logger sends PublishWorkflowStep events to Splunk | When one publish workflow completes | Then Splunk receives one correlated generation-log payload | Evidence: Jira description for the current issue.
- AC-03 [Proposed]: (Basic) Given a publish workflow creates valid output | When generation-log handling completes | Then the published output remains unchanged | Evidence: inspected fix and Jira description for the current issue.

### UI action

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Basic) Given a user who has the required permissions opens the map and navigates to the output preset panel in which several existing presets and configuration states are visible | When the user selects the target preset and chooses the edit action | Then the system opens the correct configuration without losing the current selection, changing another preset, or displaying stale values | Evidence: Jira description for the current issue.

Easy-to-read internal records; the user sees the three-line format above:

- AC-01 [Proposed]: (Basic) Given an authorized user selects an output preset | When the user chooses Edit | Then the selected preset opens with its saved values | Evidence: Jira description for the current issue.
- AC-02 [Proposed]: (Negative) Given another output preset is not selected | When the user edits the current preset | Then the other preset remains unchanged | Evidence: Jira description for the current issue.

### API error

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Negative) Given an API caller provides an invalid path or unsupported request value in the event that the target resource cannot be resolved | When the request is submitted and validation is performed | Then an appropriate error response is returned without the system creating partial data or modifying an existing resource | Evidence: Jira UAC for the current issue.

Easy-to-read internal records; the user sees the three-line format above:

- AC-01 [Proposed]: (Negative) Given an API request contains an invalid target path | When the caller submits the request | Then the API returns the approved error response | Evidence: Jira UAC for the current issue.
- AC-02 [Proposed]: (Negative) Given the API rejects an invalid target path | When request processing ends | Then no partial resource is created | Evidence: Jira UAC for the current issue.

### Configuration-driven entry

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Integration) Given a new supported conditional attribute with a friendly name has been added to the active configuration while existing mapped and unmapped attributes remain available | When the relevant authoring screen is opened and the configuration is loaded | Then the new attribute and all existing entries are displayed using the correct mapping and fallback behavior without requiring a product-code allowlist change | Evidence: Jira description and inspected configuration for the current issue.

Easy-to-read internal records; the user sees the three-line format above:

- AC-01 [Proposed]: (Integration) Given the active configuration contains a new valid conditional attribute | When the authoring screen loads | Then the new attribute appears in the list | Evidence: Jira description and inspected configuration for the current issue.
- AC-02 [Proposed]: (Basic) Given a configured attribute has a friendly name | When the attribute list loads | Then the list shows that friendly name | Evidence: Jira description and inspected configuration for the current issue.
- AC-03 [Proposed]: (Negative) Given a configured attribute has no friendly name | When the attribute list loads | Then the list shows the approved fallback label | Evidence: Jira description and inspected configuration for the current issue.
