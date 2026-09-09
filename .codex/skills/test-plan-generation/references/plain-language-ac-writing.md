# Plain-Language Acceptance Criteria

## Goal

Write acceptance criteria that a tester can understand on the first read. Keep the product meaning exact, but remove sentence structures that make readers stop and re-read.

## Required Style

- Use the canonical one-line format `AC-## [Confirmed|Proposed]: (<Sphere>) <plain-English criterion>. Evidence: <source>.` in the validated record. Never use Given/When/Then labels or pipes anywhere - not in the record, chat, Jira, or the linked markdown.
- Lead with the concrete product outcome in a short sentence. Include only the condition needed to understand it; do not squeeze a setup procedure, action sequence, and result into one sentence. Use short indented sub-points for required cases.
- Never show sphere, status, or Evidence in human-facing AC text. Chat and Jira show `AC-##: <criterion>` plus optional sub-points. Keep `[Proposed]` / `[Confirmed]` and evidence in the validated record only.
- Consolidate to at most ten AC points in the presented UAC, but consolidation is LOSS-LESS: it reorganizes coverage, it never removes a checkable point. List every distinct point first; after merging, each one must survive as a clause of a merged AC, a sub-point under it, or an entry in the linked full-record markdown. If you synthesized more (say twenty), merge related criteria into a single AC the way a senior human QA does and express the merged detail as sub-points. Never drop a point to hit the cap, and never split one idea into many thin ACs to pad the list.
- Give each AC one purpose.
- Do not add a summary AC that repeats earlier outcomes with words such as "all", "everywhere", or "consistently". Move any genuinely new, evidence-backed consumer or condition into the relevant AC's explicit coverage; never discard it along with the repeated sentence.
- State only the minimum setup the criterion needs.
- Name the relevant condition, trigger, or user action from the source; do not invent an action for a state-based requirement.
- State one observable result.
- Keep the criterion to one sentence a reader can scan; if it needs more, move detail into short sub-points.
- More than 28 words, more than two sentences, or many stacked clauses in a single AC sentence is a loud review finding; an AC whose observable result runs over 45 words is a hard failure - split it or use sub-points.
- Split when the required behavior or expected outcome differs, not merely because two test cases can fail independently. Different languages, entry points, or surfaces may share one AC when they have the same contract; a different fallback, failure outcome, timing, ordering, or permission rule must stay distinguishable.
- Do not remove accepted meaning to meet a length or count target. Use short sub-points for equivalent cases, split genuinely different contracts, and preserve every source-clause mapping. The AC count follows the outcomes, not a desired list length.
- Prefer short words: use, before, after, if, and for.
- Keep exact product names, UI labels, API paths, configuration keys, enum values, and error codes when they matter.
- Avoid semicolons, double negatives, parenthetical explanations, and long comma-separated lists.
- Move setup steps, matrices, implementation details, and background explanations to Test Scenarios or Open Questions.
- A code change can reveal an extra behavior, such as a new fallback or error response, but it does not prove that product scope approved that behavior. Keep it Proposed and ask the scope question unless Jira, accepted UAC, or an explicit product decision approves it.
- Keep long examples, extension lists, implementation explanations, and parenthetical exceptions outside the tester sentence. Put them in Test data, a scenario, or a `Note for developer:` bullet.
- Name the exact screen. Move code, file paths, implementation jargon, and performance internals to a `Note for developer:` bullet in an existing technical section instead of tester-facing AC text. Preserve a source-mandated exact identifier when fidelity requires it, and expose the readability tradeoff for review.
- Preserve human reviewer wording as the semantic baseline. Simplify its sentence structure without changing the actor, scope, UI label, timing, fallback, exact path, or product outcome.
- Use familiar QE verbs such as show, use, keep, and remove when they describe the result precisely. Keep documented product names such as Language Variable; do not replace them with invented technical synonyms or unnecessary qualifiers. Do not substitute a DITA element name for a visible label or CSS-generated text unless it really is that DITA element.
- Check negative wording against the allowed fallback and configuration cases. "Do not use X" is valid only under the stated condition; it must not reject X when the approved fallback legitimately selects it.
- If inspected code conflicts with human feedback, keep the requested meaning and add an Open Question that states the conflict. Do not silently replace the requirement with current implementation.
- Do not refer to another criterion such as AC-04 inside the criterion text. State the required fallback or result directly so each criterion stands alone.
- Review an existing or AI-supplied AC set through the full evidence manifest and `run_gates.py` pipeline. A conversational review alone is not a gated result.
- Resolve every readability and implementation-scope review before posting. The gate can still exit successfully for backward compatibility, but its receipt remains non-postable.

## Human-Facing Format

The renderer and Jira poster produce this deterministic view from the record - one plain-English line per AC, with optional short sub-points:

```text
- AC-01: A DITA-OT publish that returns a generation log records exactly one generation-log payload in the application logger.
- AC-02: Condition changes in a Folder Profile are reflected in the DITAVAL editor dropdowns.
  - Adding a condition to the profile makes it appear in the Attribute dropdown.
  - Deleting a condition removes it from the dropdown.
```

Do not manually paraphrase this view. Keep the criterion text verbatim so technical terms are preserved exactly, and use sub-points only to break a genuinely long criterion into scannable clauses.

## Quick Review

Before accepting an AC, ask:

- Can I explain its purpose in one short sentence?
- Is its condition, trigger, or action clear without inventing a new step?
- Does it state only one result?
- Can any shorter common word replace a formal phrase?
- Does another AC already require this outcome? If so, what unique condition or check must survive the merge?
- Are these different contracts, or just different cases of one contract?
- Can QE identify what to inspect and what it must show without translating implementation terminology?

## Group outcomes without hiding coverage

Before rewriting, list each existing outcome and its named cases. Group by the required behavior and result, not by repeated words or a common product area. Keep an internal old-to-new mapping so a merged sentence cannot silently remove scope.

- Keep material language, configuration, surface, entry-point and consumer cases visible in the AC's short sub-points. Detailed setup and individual executions belong in mapped Test Scenarios; do not hide reviewer-requested scope only in a separate artifact.
- Keep fix validation separate from preservation of behavior that already works. Regression checks may share an AC when they protect the same invariant, with every named check retained. Do not move an in-scope check out of acceptance merely to shorten the list.
- Do not assume equivalent behavior from similar names. If the evidence gives different outcomes, keep them separate; if applicability is undecided, preserve the Open Question instead of asserting parity.
- For example, if approved source text requires the same displayed value in two named views, write the value rule once and list both views underneath. If another clause defines what appears when the value is missing, retain that fallback as a distinct contract. These are writing examples, not new product requirements.

## Examples

### Publishing log

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Integration) Given a publish operation is started for a map for which DITA-OT logging is enabled and a custom logger and external log sink have been configured | When output generation and all downstream metadata processing have completed | Then the same generated log information is written only once in the application log and customer log sink while the output and history remain unchanged | Evidence: Jira description for the current issue.

Easy-to-read records in the canonical plain format:

- AC-01 [Proposed]: (Basic) A DITA-OT publish that returns a generation log records exactly one generation-log payload in the application logger when the publish workflow completes. Evidence: Jira description for the current issue.
- AC-02 [Proposed]: (Integration) When the customer logger sends PublishWorkflowStep events to Splunk, one completed publish workflow delivers exactly one correlated generation-log payload to Splunk. Evidence: Jira description for the current issue.
- AC-03 [Proposed]: (Basic) A publish workflow that creates valid output leaves the published output unchanged after generation-log handling completes. Evidence: inspected fix and Jira description for the current issue.

### UI action

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Basic) Given a user who has the required permissions opens the map and navigates to the output preset panel in which several existing presets and configuration states are visible | When the user selects the target preset and chooses the edit action | Then the system opens the correct configuration without losing the current selection, changing another preset, or displaying stale values | Evidence: Jira description for the current issue.

Easy-to-read records in the canonical plain format:

- AC-01 [Proposed]: (Basic) An authorized user who selects an output preset and chooses Edit sees the selected preset open with its saved values. Evidence: Jira description for the current issue.
- AC-02 [Proposed]: (Negative) Editing the current output preset leaves any other preset unchanged. Evidence: Jira description for the current issue.

### API error

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Negative) Given an API caller provides an invalid path or unsupported request value in the event that the target resource cannot be resolved | When the request is submitted and validation is performed | Then an appropriate error response is returned without the system creating partial data or modifying an existing resource | Evidence: Jira UAC for the current issue.

Easy-to-read records in the canonical plain format:

- AC-01 [Proposed]: (Negative) An API request with an invalid target path returns the approved error response. Evidence: Jira UAC for the current issue.
- AC-02 [Proposed]: (Negative) An API request rejected for an invalid target path creates no partial resource. Evidence: Jira UAC for the current issue.

### Configuration-driven entry

Hard-to-read internal record - do not use:

- AC-01 [Proposed]: (Integration) Given a new supported conditional attribute with a friendly name has been added to the active configuration while existing mapped and unmapped attributes remain available | When the relevant authoring screen is opened and the configuration is loaded | Then the new attribute and all existing entries are displayed using the correct mapping and fallback behavior without requiring a product-code allowlist change | Evidence: Jira description and inspected configuration for the current issue.

Easy-to-read records in the canonical plain format:

- AC-01 [Proposed]: (Integration) A new valid conditional attribute in the active configuration appears in the attribute list when the authoring screen loads. Evidence: Jira description and inspected configuration for the current issue.
- AC-02 [Proposed]: (Basic) A configured attribute that has a friendly name shows that friendly name in the attribute list. Evidence: Jira description and inspected configuration for the current issue.
- AC-03 [Proposed]: (Negative) A configured attribute that has no friendly name shows the approved fallback label in the attribute list. Evidence: Jira description and inspected configuration for the current issue.

## Senior-QA Style (five rules, learned from a human UAC example)

A senior human QA wrote that UAC as a 3-line Scope plus seven one-line ACs, and it read far clearer than a longer AI draft. Apply these five rules so a UAC reads like that:

1. **Draw the boundary up front when it is non-obvious.** A short Scope line (output/surface in scope, source constructs in scope, what is explicitly the only thing supported) is a good option when the boundary is easy to get wrong - e.g. "Scope: Native PDF; Map/Bookmap topicmeta/bookmeta; only the image element is supported." This is optional, not mandatory: in the measured corpus only ~2% of human UACs use an explicit "Scope:" block, so do not force one - most UACs draw the boundary implicitly through tight, well-scoped ACs. Prefer the boundary being clear over a ceremonial header.
2. **One concrete product contract per AC.** Keep the main sentence short. Group same-outcome cases as named sub-points; split different behavior or results. The words "and" or "whether" alone do not decide whether two cases need separate ACs.
3. **Resolve specifics from evidence.** Replace a question such as "which image formats?" with the supported set only when the current requirement or documentation establishes it. Do not invent a sensible-looking default. Reserve Open Questions for decisions the evidence cannot settle.
4. **Name the real artifact or pipeline the tester checks, not an abstract mechanism.** "The image is present in the generated temporary files" beats "the engine downloads the image" (vague). "No tag loss in the merged HTML" beats "content is preserved". Ground each AC in the concrete thing a tester can open and verify.
5. **Shorter is the target, not a side effect.** Prefer seven tight one-liners over thirteen padded ones. Do not enumerate every construct variant as its own AC when the Scope already bounds them; push variants into Test Scenarios.

### Concrete verification dimensions to consider for Native PDF / output-generation tickets

These are real, testable dimensions a senior QA includes and an AI draft repeatedly misses (source: human UAC examples). Consider each and cover it or consciously scope it out:

- **Temporary-files artifact:** the referenced image or asset is present in the generated temporary files (author with "Retain temporary files" and open them). This is the concrete form of any "the engine picks up / downloads the asset" claim - never leave that mechanism vague.
- **Assets UI update flow:** updating the asset in the AEM Assets UI is reflected when the PDF is generated again (a DAM update propagates to the output).
- **No tag loss in the merged HTML** produced by the publish pipeline.
- **Renditions:** image renditions are applied according to renditionmapping.xml.
- **CSS styles** are honored for the element (size, placement).
- **Custom DTD / specialization** support (for example a specialized topicmeta) still resolves.
- **Supported type matrix:** enumerate the decided supported set (for example image types gif/jpg/bmp/png/svg/tiff) rather than asking which are supported.
