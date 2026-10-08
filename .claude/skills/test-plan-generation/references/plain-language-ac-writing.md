# Plain-Language Acceptance Criteria

## Goal

Write acceptance criteria that a tester can understand on the first read. Keep the product meaning exact, but remove sentence structures that make readers stop and re-read.

## Required Style

- Use the canonical one-line format `AC-## [Confirmed|Proposed]: (<Sphere>) <plain-English criterion>. Evidence: <source>.` in the validated record. Never use Given/When/Then labels or pipes anywhere - not in the record, chat, Jira, or the linked markdown.
- In the human-facing UAC, state the named product item and its observable result directly, the way human QE UACs do; a `Verify that` lead is allowed but not required. Keep the underlying record as a product outcome; do not squeeze a setup procedure, action sequence, and result into one sentence.
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
- **Plain statement:** the criterion statement says one thing a QE can check, in at most two clauses: what the
  user does (only when it matters) and what they see. It uses only names shown on screen (screens, buttons,
  settings as labelled). No colon or semicolon lists, and no internal terms such as rendition, propagation,
  transitive, payload, async, regression or variant in the statement - say what the user sees instead.
- Exact technical values - API paths and fields, configuration keys and setting values, enum values, status
  codes, file names - go in a sub-point of that criterion (or the full test plan), not in the statement.
  Statement: "An invalid request is rejected as a whole and returns no results." Sub-point: "returns 400".
- Shortening never changes meaning: never merge, drop or replace a named product item to save words. Keep
  each one by its own name - a map template and a topic template are different things, so "a topic created
  from a map template" is wrong; write "each new topic made from a topic template the map template refers
  to". Shorten by moving cases and detail to sub-points, not by renaming.
- A rewrite is not only wording: before rewriting a criterion, re-read the ticket's description, every
  comment and every attachment, and check that the rewritten statement is about the same screen, item and
  behaviour its sources say. A developer or product comment that names the screen (for example "this
  dropdown is AEM's own task reassignment") decides which screen the criterion is about.
- A documentation answer marked not verified, or one that cites unrelated pages, can only become a TBD,
  never a criterion or a sub-point.
- Avoid semicolons, double negatives, parenthetical explanations, and long comma-separated lists.
- Move setup steps, matrices, implementation details, and background explanations to Test Scenarios or Open Questions.
- A code change can reveal an extra behavior, such as a new fallback or error response, but it does not prove that product scope approved that behavior. Keep it Proposed and ask the scope question unless Jira, accepted UAC, or an explicit product decision approves it.
- Keep long examples, extension lists, implementation explanations, and parenthetical exceptions outside the tester sentence. Put them in Test data, a scenario, or a `Note for developer:` bullet.
- Name the exact screen. Move code, file paths, implementation jargon, and performance internals to a `Note for developer:` bullet in an existing technical section instead of tester-facing AC text. Preserve a source-mandated exact identifier when fidelity requires it, and expose the readability tradeoff for review.
- Preserve human reviewer wording as the semantic baseline. Simplify its sentence structure without changing the actor, scope, UI label, timing, fallback, exact path, or product outcome.
- Use familiar QE verbs such as verify, show, use, keep, and remove when they describe the result precisely. `Verify that` is valid only with a named screen, property, construct, or artifact and an observable result; never write `Verify that the system...`. Keep documented product names such as Language Variable; do not replace them with invented technical synonyms or unnecessary qualifiers. Do not substitute a DITA element name for a visible label or CSS-generated text unless it really is that DITA element.
- Check negative wording against the allowed fallback and configuration cases. "Do not use X" is valid only under the stated condition; it must not reject X when the approved fallback legitimately selects it.
- If inspected code conflicts with human feedback, keep the requested meaning and add an Open Question that states the conflict. Do not silently replace the requirement with current implementation.
- Do not refer to another criterion such as AC-04 inside the criterion text. State the required fallback or result directly so each criterion stands alone.
- Review an existing or AI-supplied AC set through the full evidence manifest and `run_gates.py` pipeline. A conversational review alone is not a gated result.
- Resolve every readability and implementation-scope review before posting. The gate can still exit successfully for backward compatibility, but its receipt remains non-postable.

## Human-Facing Format

The renderer and Jira poster produce this deterministic view from the record - one plain-English line per AC, its source on its own line, and any still-open product decision attached to the AC it governs:

```text
- AC-01: Verify that a DITA-OT publish that returns a generation log records exactly one generation-log payload in the application logger.
  **Source:** the Jira description.
- AC-02: Verify that adding a Folder Profile condition makes it appear in the DITAVAL Attribute dropdown and deleting it removes it.
  **Source:** Experience League Folder Profile condition documentation.
  **TBD:** are custom user-defined conditions in scope for the same dropdown refresh?
```

The delivered chat view is a list of criteria: no ticket title line and no separate Open Questions section; the only other lines are the optional Note, Scope line and Out of scope list (see SKILL.md "Acceptance Scope And The Delivered UAC"). A criterion that covers several cases of the same outcome lists them as up to five short indented sub-points. Do not manually paraphrase this view. Render each concrete outcome as written, keep the underlying terms unchanged, keep the criterion body free of bold, backticks and links so it pastes cleanly into Jira, and strip the `**Source:**` / `**TBD:**` emphasis to plain labels before any Jira write.

Once a user has confirmed this shape, reuse it verbatim on every later revision of the same UAC. Re-deriving a different layout - adding headings, splitting one outcome into several criteria, or restoring an Open Questions section - is a format defect, not an improvement.

## Quick Review

Before accepting an AC, ask:

- Can I explain its purpose in one short sentence?
- Is its condition, trigger, or action clear without inventing a new step?
- Does it state only one result?
- Can any shorter common word replace a formal phrase?
- Does another AC already require this outcome? If so, what unique condition or check must survive the merge?
- Are these different contracts, or just different cases of one contract?
- Can QE identify what to inspect and what it must show without translating implementation terminology?

## Name actions the way the user sees them

- Readers know the screen, not the code. Describe the action in plain words and add the exact UI name in brackets on first mention.
- Write: "Verify that Generate does not start while pages of the site are being removed from the live site (Unpublish)."
- Avoid: "Verify that output generation is blocked while a deactivation of the destination path is in process." (code/log words: output generation, deactivation, destination path)
- Keep code and log names (deactivate, replication, class names, line numbers) on the Source line only.

## Use the everyday AEM Guides words

QE talk about content in the words they use every day in AEM Guides. Use those words in the AC statement and
keep DITA element names, file extensions and code words for sub-points or the Source line.

| Write (everyday word) | Instead of |
|---|---|
| topic reference | topicref, `<topicref>` element, href to a topic |
| map reference | mapref, submap reference, `<mapref>` element |
| direct reference / indirect reference | reltable link (an indirect reference is a link through a relationship table) |
| forward reference / backward reference | incoming links, where-used, referencing files, dependents |
| conref, conkeyref, keyref | content reuse attribute, key-based reuse, key resolution |
| DITA map, bookmap | ditamap file, map XML, bookmap XML |
| topic | DITA topic file, topic XML, .dita file |
| DITA files / non-DITA files | XML assets, binary assets, non-XML assets |
| images | graphic assets, image binaries, image renditions |
| asset update | asset modification, asset mutation, asset overwrite |
| Map console / Map dashboard | Advanced Map Editor, map management page |
| publishing / output generation | transformation run, publish job, generation request |
| review | review workflow, review task process |
| postprocessing | asset processing job, post-upload processing step |
| DAM Update Asset workflow | asset update workflow model, dam-update-asset |
| Cloud (AEMaaCS) | AEM as a Cloud Service, cloud deployment, cloud environment |
| doc state (Document State) | document status property, docstate metadata |
| Global Profile / Folder Profile | global configuration node, profile settings node |
| XML Editor Configuration | editor configuration files, editor config JSON |
| ui config | ui_config.json (keep the file name for a sub-point) |
| Repository View | asset tree, file browser, repository panel |
| Layout View / Preview / Side By Side View | layout mode, render preview, diff view, compare view |
| Content Fragment | CF, content fragment node |
| Download / Download Map | export, map export, download as ZIP |
| output presets, PDF preset (Native PDF or DITA-OT) | publish configuration, transformation profile, PDF generation settings |
| Workfront | project management integration, work item system |
| fmditaTitle, dc:title | title metadata property, jcr title field |
| asset state, doc state | asset status, lifecycle status |
| Tags View / non-tag view | tag display mode, markup view, plain view |
| new baseline (V2 baseline) / old baseline (V1 baseline) | baseline v2 API, legacy baseline, baseline node |
| new AEM Sites (Native AEM Sites) / old AEM Site (DITA-OT based) | sites publishing, site output engine, sites v2 |
| output | generated artifact, rendition, publish result |
| General / Metadata / Layout / Security / Print / Advanced tab (of an output preset) | preset section, settings group |
| Conditional filtering: None / Using DITAVAL / Using condition preset | ditaval filtering, condition filter, profiling |
| Author view / Source view / Side-by-side / Preview (Editor modes) | WYSIWYG mode, XML mode, raw view, diff mode |
| left panel (Collections panel with Lightbox and user collections, Explorer, Map Panel, Outline Panel, Glossary panel, Templates panel, Snippets Panel, Subject Scheme Panel, Find and Replace) | navigation sidebar, repository tree, file tree |
| PDF templates | Native PDF template definitions, template folder |
| variables, language variables | placeholder values, i18n strings, localized labels |
| element, tag, attribute, friendly names | XML node, DOM node, node property, element label mapping |
| Workspace Settings, Publish profile, Assets View | user settings JSON, publish configuration, DAM asset browser |
| context menu (Save as new version, Copy > Copy UUID / Copy path, Locate in, Add to, Properties, Close) | right-click options, overflow actions |
| top toolbar (Menu, Insert element, Insert image, Multimedia, Version, Lock) | editor header bar, action bar |
| ellipses menu (Cross-reference, Reusable content, Symbol, Snippets, Keyword) | more-options overflow, kebab menu |
| Save as new version dialog (Last Version, Comments for new version, Version labels) | version commit dialog, version tag field |
| Menu dropdown (Cut, Copy, Delete, Version label, Merge) | file actions list, editor main menu |
| check out / check in | acquire lock, release lock, lock owner change |
| Repository Search | DAM query, asset search API, repository lookup |
| Explorer folder options menu (New, Upload assets, Refresh, Collapse, Find files in folder, Add to collections, Reprocess asset(s), View in Assets UI) | folder actions, tree node menu |
| Explorer file options menu (Edit, Edit in Oxygen, Unlock, Preview, Duplicate, Move to, Rename, Delete, Generate, Add to, Copy, Reprocess asset, View in Assets UI, Properties) | file actions, asset node menu |
| Explorer + menu (Topic, Map, Folder) | create-new dropdown |
| element context menu in Author view (Rename element, Surround with element, Unwrap element, Insert before, Insert after, Create snippet, Generate IDs, Locate in explorer, View in assets UI) | node operations, wrap/unwrap XML, auto-ID generation |
| Map Panel selection bar (N selected; Save as new version and unlock, Properties) | bulk selection toolbar, multi-select actions |
| app switcher (Home, Editor, Map console) | mode dropdown, app menu, workspace switch |
| Map console left panel (Output presets, Reports, Baseline, Condition presets, Translation) | map dashboard sidebar, publishing tabs |
| Map console map dropdown (Open in editor, Select another map) | map picker, switch context |
| New output preset dialog, Type: AEM Sites, PDF, Knowledge Base, HTML5, JSON, Custom, SCORM | preset type enum, output format option |
| Single Topic Publishing (STP) | topic-level publish, per-topic generation |
| schematron file(s) | .sch rules file, validation rule set |
| toggle on / toggle off | enable or disable the flag, set the property to true or false, checked or unchecked switch |
| Workspace settings tabs: General, Panels, Elements list, Attributes list, Colors, Font list, Publish profiles, Validation, Display attributes, Translation, Metadata | user preference keys, editor settings JSON |
| right panel (File properties: General, References, Outputs, Translations; Content properties: Type, Attributes) | properties sidebar, inspector, metadata pane, element inspector |
| options menu at the top right (Assets, Editor settings, Workspace settings) | app menu, settings overflow |
| breadcrumb | element path, node path, XPath bar |
| editor search bar | find widget, search overlay, quick search component |

- Write: "A topic reference added to the DITA map shows in the Map View."
- Avoid: "A topicref element appended to the ditamap XML is rendered in the map tree."
- When one technical value must be checked (an element name, a file extension, a property), put it in a sub-point:
  "  - the reference is a <topicref> with format=dita".
- conref, conkeyref, keyref, fmditaTitle and dc:title are everyday QE words: they may stay in the statement.
- "element", "tag" and "attribute" are everyday words. When the Editor shows a friendly name for an element,
  use the friendly name in the statement and the element name in a sub-point.
- Say which baseline: "new baseline (V2)" or "old baseline (V1)", or both when both are in scope.
- Say which AEM Sites output: "new AEM Sites" (Native AEM Sites, the same output) or "old AEM Site" (the
  DITA-OT based one), or both when both are in scope. Never list new AEM Sites and Native AEM Sites as two outputs.
- Name the output preset tab where the setting lives, as it is shown on screen: "the Layout tab of the Native PDF
  preset", "Using DITAVAL in Conditional filtering on the General tab".
- Name the Editor area where the check happens: left panel, right panel, breadcrumb, editor search bar, or the
  mode (Author, Source, Side-by-side, Preview).
- For a Workspace settings option, name the tab, the section and the toggle as shown: "with Highlight conditional
  text in the Author view toggled on (Workspace settings, General tab, Condition)". A panel shown or hidden from
  the Panels tab is named as listed there (Map, Outline, and in More section: Reusable content, Glossary,
  Conditions, Subject scheme, Snippets, Templates, Citations, Language variables, Variables, Output templates,
  Find and replace, Data sources, Review).
- A metadata property is named by its Label from the Metadata tab of Workspace settings (Title, Document State,
  Tags); its Metadata Path goes in a sub-point ("  - metadata/cq:tags").
- Name the menu and the option as shown: "Duplicate from the file options menu in Explorer", "Reprocess asset(s)
  from the folder options menu".
- In the References section of the right panel, use the screen labels: "Used in" (backward references) and
  "Outgoing links" (forward references); an empty list shows "No used references found".
- Validation tab options are named as shown: "Run validation check before saving the file", "Allow all users to
  add schematron files in validation panel", and the Schematron Files list.
- Translation tab labels are named as shown: Language groups (Name, Languages, Add), Additional settings,
  "Propagate source version labels to the target version", and "Translation project cleanup after completion"
  with None, Disable or Delete.
- In the New output preset dialog the Type is named as listed (AEM Sites, PDF, Knowledge Base, HTML5, JSON,
  Custom, SCORM). A preset of Type PDF is a Native PDF or DITA-OT PDF preset depending on its Generate PDF Using
  setting; say which.
- The same setting can have a different label per preset type: "DITA-OT command line arguments" in a Custom
  preset, "Additional DITA-OT command line arguments" in a Native PDF preset. Use the label of that preset type.
  A Custom preset has the General and Advanced tabs (Transformation name, File name, Output path). The Post
  generation workflow dropdown lists AEM workflow models by title; name the model as shown.
- Native PDF preset Advanced tab toggles, named as shown: Create accessible (tagged) PDF, Merge PDFs included in
  the TOC, Embed used fonts, Use automatic hyphenation, Enable JavaScript, Embed multimedia files, Use full
  compression to optimize the PDF size, Use image compression to optimize the PDF size, Use custom resolution
  (pixels per inch), Show Watermark, Enable MathML equations, Create interactive PDF form, Include track changes,
  Retain temporary files; then PDF conformance and File (Asset) properties (not the right panel's File properties).
- Leaving a preset with unsaved edits shows the Save changes dialog (Don't Save, Cancel, Save).
- Say which PDF preset: "Native PDF preset" or "DITA-OT PDF preset", or both when both are in scope.
- Use the precise kind when the ticket is about it: "bookmap" when only bookmaps are affected, "map" when every DITA map is.

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
