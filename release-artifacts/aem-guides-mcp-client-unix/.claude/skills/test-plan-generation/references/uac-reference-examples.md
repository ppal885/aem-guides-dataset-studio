# UAC Reference Examples

Use this file when normalizing Jira UAC or when a user asks for a test plan that should read like a strong manual QA sign-off note.

## What Good UAC Looks Like

- Assign stable IDs such as `AC-01` and label derived requirements `[Proposed]` until Jira or the product owner confirms them.
- Write acceptance criteria as observable product contracts, not as test instructions beginning with `Verify`.
- Keep test execution steps in `Test Scenarios` and map each scenario back to one or more AC IDs.
- Start with a short business/feature context before listing test cases.
- Treat UAC as the primary acceptance and sign-off contract: it defines what QA must prove, what is out of scope, and which unresolved questions block review-ready status.
- Separate cloud and on-premise expectations when behaviour differs.
- State UI entry points explicitly, such as menu upload and drag/drop.
- Cover single item, multiple same-type items, and mixed-type files.
- Include negative and boundary coverage: restricted mime type, file size, invalid characters, existing assets, overwrite choices, abort/resume/cancel.
- Include configuration coverage when product behaviour depends on an AEM setting.
- State integration points explicitly, including nearby workflows, APIs, configs, permissions, automation, publishing, translation, upload/status, review, or editor areas that can regress.
- Mention platform parity requirements directly when the same test must run on cloud and on-premise.
- Keep expected behaviour, out-of-scope, regression boundaries, and open questions visible instead of burying them inside generic scenario text.
- Keep notes close to the scenario they constrain, for example folder upload is not allowed from a file-upload entry point.
- Use plain English and observable results; avoid tables and implementation-only wording.

## Gold Reference: Assets UI Upload Parity

Use this example as a quality bar for UAC structure and breadth. Do not copy it blindly into unrelated plans; adapt the pattern to the actual Jira, PR, RAG, and repo evidence.

**UAC**

- This ticket updates existing upload and drag/drop functionality in Assets UI.
- For cloud server, user should see upload status and should be able to abort/cancel the upload.
- For on-premise server, upload should behave the same as cloud. API calls should align with cloud because on-premise Assets UI upload previously used different APIs.
- For on-premise server, user should see upload status and should be able to abort/resume the upload.
- For on-premise overwrite of a working copy, behaviour should match cloud: a version should be created for the working copy, and the old checkbox option should become a note.

**Test Cases To Verify**

- Execute all core upload and drag/drop tests on both cloud and on-premise.
- Verify upload through the files-upload menu option with a single file.
- Verify upload through the files-upload menu option with multiple files of the same type.
- Verify upload through the files-upload menu option with mixed file types such as TIFF, PNG, GIF, JPG, DITA, PDF, Word, TXT, video, audio, ZIP, and PLT.
- Confirm folder upload is not allowed through the files-upload menu option.
- Verify drag/drop upload with a single file.
- Verify drag/drop upload with multiple files of the same type.
- Verify drag/drop upload with mixed file types such as TIFF, PNG, GIF, JPG, DITA, PDF, Word, TXT, video, audio, ZIP, and PLT.
- Confirm folder upload is not allowed through drag/drop when the feature only supports files.
- Verify file names with allowed and not-allowed characters.
- Verify the rename popup for both drag/drop and files-upload flows.
- Verify file names with different casing.
- Verify uploading existing files with overwrite and confirm the expected version is created.
- Verify uploading existing files without overwrite and confirm version behaviour remains correct.
- Verify a large set containing existing and new files, overwrite only selected files, and confirm versions are created only where expected.
- Verify aborting upload of new files and confirm aborted files are not uploaded.
- Verify aborting upload of existing files and confirm existing assets are not updated and versions remain unchanged.
- Verify upload with the create-version-for-uploaded-file setting enabled and disabled; expected result should follow the setting.
- Verify restricted mime type upload is blocked according to AEM upload restriction configuration.
- Verify files exceeding configured size limits are blocked according to AEM upload size configuration.
- Verify duplicate detection on and off in the `Day CQ DAM Create Asset` servlet for existing and non-existing files.

## Gold Reference: Review Comment Identity And Role Display

Use this example as a quality bar for review-functionality UAC, especially when the ticket affects reviewer task pages, editor review panels, tagging, replying, nested comment replies, notifications, or email side effects.

**Scope**

- Feature flag: no feature flag.
- Impact pages: reviewer task page and editor review right panel.
- Areas to check: tagging users, replying to comments, and ladder/nested replies inside a comment.
- Doc impact: yes.
- Automation impact: yes.

**P0 Test Cases To Verify**

- Verify that tagged/replying user identity displays as `Firstname Lastname <email>` when first name, last name, and email are available.
- Verify that if email is unavailable, the fallback remains the existing `user_id` behaviour.
- Verify that the user role from API response maps to the project to which the review task belongs.
- Verify that role labels are displayed in plural form such as `Reviewers`, `Authors`, or `Owners`.
- Verify that if no role is returned by the API due to an internal error, the UI displays only the email ID; if email is also unavailable, preserve the existing `user_id` fallback.
- Verify that search behaviour is not impacted by the identity/role display change.
- Verify there is no regression in notifications and emails for tagging, replies, and nested replies.

**Regression Areas To Carry Forward**

- Reviewer task page identity rendering.
- Editor review right panel identity rendering.
- Tagging user search and mention insertion.
- Reply and nested reply display.
- Project-specific role mapping.
- API fallback states for missing email, missing role, or internal errors.
- Notification and email delivery after tagging or replying.

## Gold Reference: Live Dropdown Filtering And Paste Behaviour

Use this example as a quality bar for autocomplete, combobox, dropdown, picker, mention, search, filter, or typeahead UAC. The important quality signal is that filtering reacts to the field value, not only keyboard events.

**UAC**

- Typing the first letter, such as `a`, filters the list to show only items that contain or start with `a`, according to the component's intended matching rule.
- Typing additional characters narrows the filtered results in real time.
- Pasting a complete word into the field triggers the same filtering logic as manual typing.
- If no items match the current input, the dropdown should be empty and the full list must not be displayed.
- Clearing the input field restores the full list.
- Filtering is case-insensitive unless Jira, design, or product copy explicitly says otherwise.
- The list updates immediately after typing or pasting without requiring an extra click, key-down, blur, focus change, or manual refresh.

**Test Cases To Verify**

- Verify typing one character filters the dropdown according to the expected matching rule and does not leave unrelated options visible.
- Verify typing multiple characters narrows the list with each input change in real time.
- Verify pasting a full word into the input applies the same filter result as typing that word character by character.
- Verify uppercase, lowercase, and mixed-case input return the same result when filtering is expected to be case-insensitive.
- Verify a no-match search shows an empty dropdown or approved empty state, and does not fall back to the full list.
- Verify clearing the input through backspace, select-all-delete, or clear icon restores the full list.
- Verify filtering works after reopening the dropdown, after focus/blur, and after selecting and then changing a value.
- Verify keyboard navigation continues to operate on the filtered list only, not hidden or stale full-list items.
- Verify mouse selection, Enter selection, and Escape/close behavior remain correct after filtering.
- Verify loading, large-list, and slow-response states do not show stale results for an older input value.

**Regression Areas To Carry Forward**

- Input `change`, `input`, `paste`, `keydown`, `keyup`, and clear-icon event handling.
- Case-insensitive matching and exact matching boundary rules.
- Empty-state rendering when there are no matches.
- Full-list restoration after clearing input.
- Stale result handling during fast typing or paste.
- Keyboard navigation, focus management, and screen-reader/ARIA state for filtered options.
- Existing selection behaviour after filter changes.
- Performance for large option lists.

## Gold Reference: Table Cell Whitespace Around Inline Tags

Use this example as a quality bar for DITA/XML whitespace tickets that affect table cells, inline tags, text normalization, or editor/publishing round-trip behaviour. The important quality signal is that user-authored cell text behaves like paragraph text while source-formatting indentation does not leak into rendered or saved content.

**UAC**

- Space before an inline tag inside a CALS table, `simpletable`, or `reltable` cell is preserved in both body cells and header cells.
- Cell whitespace behaviour matches `<p>` for leading, trailing, and inter-element spaces around inline tags.
- Different whitespace positions are covered: leading space, trailing space, inter-element space, before inline tags, after inline tags, before a newline, before a block child, and across structural indentation between `row` and `entry` tags.
- Space before a block child is intentionally trimmed when that is the product rule, and should not be treated as a preservation bug.
- Multiple consecutive regular spaces collapse to one visible/rendered space.
- Non-breaking spaces never collapse or drop, including alternating regular-space and NBSP runs.
- Text-forbidden tags must not get unnecessary whitespace preservation.
- Pretty-printed XML indentation between structural table tags must not leak into cell text.

**Test Cases To Verify**

- Verify a CALS table body cell preserves a user-authored space before an inline tag and renders/saves it the same way as paragraph text.
- Verify a CALS table header cell preserves a user-authored space before an inline tag and matches body-cell behaviour.
- Verify the same inline-tag whitespace cases in `simpletable` cells.
- Verify the same inline-tag whitespace cases in `reltable` cells.
- Verify leading, trailing, and inter-element spaces around inline tags in table cells match `<p>` behaviour.
- Verify spaces before and after inline tags are preserved or normalized exactly according to the paragraph rule.
- Verify a space before a newline in a cell does not disappear if it is user-authored content that should be preserved.
- Verify a space before a block child is trimmed when the intended rule says block-child boundary whitespace is not preserved.
- Verify multiple regular spaces collapse to one visible/rendered space.
- Verify NBSP remains intact and does not collapse or drop, including mixed runs like regular space + NBSP + regular space.
- Verify text-forbidden tags do not gain preserved whitespace where text is not allowed.
- Verify pretty-printed source indentation between `row`, `entry`, header, and body table structure does not appear in cell text.

**Regression Areas To Carry Forward**

- XML parser and serializer whitespace normalization.
- Editor save/reopen round trip for CALS table, `simpletable`, and `reltable`.
- Body-cell and header-cell rendering parity.
- Inline elements inside cells such as emphasis, cross-reference, keyword, term, filepath, code phrase, or user-mentioned tag types.
- Paragraph versus table-cell whitespace parity.
- NBSP handling in authoring, source view, preview, and publishing output.
- Pretty-print formatting and structural indentation around `row` and `entry`.
- Text-forbidden elements and mixed-content validation.
- PDF, HTML5, Native PDF, or AEM Sites output if the Jira mentions publishing impact.

## Gold Reference: Asset Status API Comma Paths

Use this example as a quality bar for API/path parsing tickets where DAM paths, folder names, file names, or excluded paths contain commas. The important quality signal is that a comma in a path segment is treated as a literal path character, never as a list delimiter or parse boundary.

**UAC**

- `/bin/guides/v1/assets/status` must treat a comma in any `paths` or `excludedPaths` value as a literal character, never as a delimiter.
- An asset under a comma-containing folder returns its real status, not a job `FAILED`, for example `/content/dam/comma_path_status/test,comma/aaa100100.dita`.
- An asset whose own file name contains a comma returns the correct status, for example `/content/dam/comma_path_status/plain/file,name.dita`.
- Multiple comma-containing paths in one request are resolved independently and are never merged, truncated, or mis-split.
- A mixed request with comma-containing and comma-free paths resolves every path correctly.
- A comma-containing folder query expands to all child assets under that folder.
- Each comma path reflects its true state such as `SUCCESS`, `FAILED`, or `UNPROCESSED`; unprocessed content is reported as not processed and is not masked as a job failure.
- A comma-containing `excludedPaths` entry excludes the matching subtree correctly.
- A `.ditamap` with a comma in the file name returns the correct status.
- Consecutive commas, multiple commas in one segment, commas with spaces, and commas with special characters are preserved exactly.
- Duplicate comma paths are de-duplicated, and direct asset query results match parent-folder query results.
- A relative path that does not start with `/` is rejected gracefully without crashing the batch.
- A non-existent comma path returns a clean not-found response, not a parse failure.
- A folder name ending with a comma, including comma next to `/`, is handled correctly.

**Test Cases To Verify**

- Verify `/content/dam/comma_path_status/test,comma/aaa100100.dita` returns the asset's real status and does not return a generic job `FAILED`.
- Verify `/content/dam/comma_path_status/plain/file,name.dita` returns the correct status when the comma is in the file name.
- Verify multiple comma paths in one `paths` request, such as `/content/dam/comma_path_status/multi/a,b/first.dita` and `/content/dam/comma_path_status/multi/c,d/second.dita`, are resolved as two independent paths.
- Verify a request mixing `/content/dam/comma_path_status/multi/a,b/first.dita` and `/content/dam/comma_path_status/multi/normal/third.dita` resolves both correctly.
- Verify querying `/content/dam/comma_path_status/folder,query` returns all expected child assets under that folder.
- Verify comma paths in different processing states return their true states, including `SUCCESS`, `FAILED`, and `UNPROCESSED` as not processed.
- Verify `excludedPaths=/content/dam/comma_path_status/excluded,root/skip,me` excludes that comma-containing subtree while the parent `/content/dam/comma_path_status/excluded,root` still resolves correctly.
- Verify `/content/dam/comma_path_status/map,folder/sample,map.ditamap` returns the correct `.ditamap` status.
- Verify consecutive and multiple commas are preserved in paths such as `/content/dam/comma_path_status/consecutive/test,,comma/multi_comma.dita` and `/content/dam/comma_path_status/consecutive/a,b,c/triple.dita`.
- Verify commas combined with spaces or special characters are handled in paths such as `/content/dam/comma_path_status/special/test, comma v2/space_comma.dita` and `/content/dam/comma_path_status/special/test,comma & more/special.dita`.
- Verify duplicate comma paths are de-duplicated and the direct asset query matches the parent-folder query for `/content/dam/comma_path_status/dup,folder/dup_asset.dita`.
- Verify relative path `content/dam/comma_path_status/test,comma/aaa100100.dita` is rejected gracefully and does not crash the rest of the batch.
- Verify `/content/dam/comma_path_status/does,not,exist/none.dita` returns clean not found and not a delimiter/parse error.
- Verify `/content/dam/comma_path_status/trailing,/edge.dita` resolves correctly when the folder segment ends with a comma.

**Regression Areas To Carry Forward**

- Query parameter parsing for `paths` and `excludedPaths`.
- Server-side list splitting, URL decoding, and path normalization.
- DAM asset versus folder status resolution.
- Folder expansion and child asset traversal under comma-containing folders.
- Mixed batch handling for comma and comma-free paths.
- Deduplication of repeated path inputs.
- Status mapping for `SUCCESS`, `FAILED`, `UNPROCESSED`, not found, and invalid path.
- `.dita` and `.ditamap` handling.
- Special characters, spaces, consecutive commas, trailing commas, and encoded comma variants.
- Error isolation so one bad path does not crash or mask the full batch.
- Automation coverage for API-level regression plus any UI caller that depends on asset status.

## Gold Reference: Empty Schematron File Validation

Use this example as a quality bar for Schematron validation tickets where the validation endpoint or editor save flow must distinguish an intentionally empty rule set from a genuinely broken `.sch` file. The important quality signal is that empty Schematron files pass silently while real validation and transform failures continue to behave correctly.

**Reference Ticket**

- GUIDES-48106.

**UAC**

- An empty Schematron file with no rules defined is treated as valid by the validation endpoint.
- No error, warning, or informational UI message is shown for the empty Schematron case.
- The user can save the current DITA topic without being blocked by an empty Schematron file.
- The user can save any other open files or topics in the editor without being blocked by an empty Schematron file.
- The fix applies only to Schematron files that are structurally empty or contain no rules.
- Malformed `.sch` files, invalid XSLT, or broken Schematron content that genuinely fails to transform are out of scope and should continue to be tracked separately unless dev/PM explicitly expands the scope.
- Existing valid Schematron files attached alongside an empty file must continue to report genuine rule violations.
- The fix must suppress only the false-positive or NPE case for empty rule sets, not real validation failures.
- Confirm whether the fix is server-side in the AEM `/bin/dxml/schematron` endpoint or client-side in the editor UI before deciding backend versus editor-only test coverage.
- Confirm whether the same behavior applies across on-prem and Cloud/Lapwing/ECP because endpoint paths or deployment layers may differ.

**Test Cases To Verify**

- Verify an empty Schematron file with no rules returns a valid/pass response from the validation endpoint.
- Verify the editor shows no error, warning, info banner, toast, inline marker, or validation panel entry for the empty Schematron file.
- Verify saving the active DITA topic succeeds when an empty Schematron file is attached or configured.
- Verify saving other open topics/files in the editor succeeds and is not blocked by the empty Schematron file.
- Verify a structurally empty `.sch` file is accepted only when it has no rules; do not treat malformed XML or invalid XSLT as covered by this fix.
- Verify a genuinely broken `.sch` file still reports the existing transform/validation failure and is not silently passed.
- Verify a valid Schematron file attached alongside the empty one still reports real rule violations as before.
- Verify a valid Schematron file attached alongside the empty one still passes clean content as before.
- Verify no new UI message is introduced for the empty-file case because silent pass-through is the agreed UX.
- Verify server-side behavior directly against `/bin/dxml/schematron` if the fix is backend-side.
- Verify editor-side save and validation behavior if the fix is client-side or if the UI still consumes endpoint output.
- Verify on-prem and Cloud/Lapwing/ECP parity only after dev/PM confirms the environment scope.

**Regression Areas To Carry Forward**

- Schematron endpoint response contract for valid, invalid, empty, and transform-failure inputs.
- Editor save flow for active topic and multiple open topics/files.
- UI validation panel, toast/banner messaging, inline markers, and blocking behavior.
- Mixed Schematron configuration where empty and valid rule files are attached together.
- NPE/false-positive handling for empty rule sets.
- Real rule violation reporting from existing valid Schematron files.
- Broken `.sch`, malformed XML, and invalid XSLT behavior, explicitly tracked as out of scope unless the Jira says otherwise.
- On-prem versus Cloud/Lapwing/ECP endpoint path and response parity.
- Automation coverage at API level and editor save-flow level.

**Open Questions To Carry Forward**

- Is the fix server-side in `/bin/dxml/schematron`, client-side in the editor, or both?
- Does the agreed behavior apply uniformly to on-prem and Cloud/Lapwing/ECP?
- Should malformed `.sch` content and invalid XSLT continue to fail exactly as before, or is there a separate Jira for those cases?
- Are there any configured Schematron attachment locations or XML Editor profile settings that must be included in QA setup?

## Gold Reference: Schematron Role Severity Parsing

Use this example as a quality bar for Schematron validation tickets where `<sch:assert>` and `<sch:report>` messages must be categorized by `role` severity and must control save blocking. The important quality signal is that QA verifies parsing, fixed category mapping, visual differentiation, save-blocking behaviour, backward compatibility, and performance with many messages.

**Scope**

- Parse the `role` attribute from `<sch:assert>` and `<sch:report>` elements.
- Support exactly four fixed severity categories: `fatal`, `error`, `warn`, and `info`.
- Accept only documented role variants: `fatal`, `error`, `warn`, `warning`, `info`, and `information`.
- Treat `warn` and `warning` as the `warn` category.
- Treat `info` and `information` as the `info` category.
- Match role values case-sensitively.
- Do not create custom severity categories for unsupported roles.

**UAC**

- `fatal` role messages are parsed from both `<sch:assert>` and `<sch:report>` and displayed under the Fatal severity category.
- `error` role messages are parsed from both `<sch:assert>` and `<sch:report>` and displayed under the Error severity category.
- `warn` and `warning` role messages are parsed from both `<sch:assert>` and `<sch:report>` and displayed under the Warn severity category.
- `info` and `information` role messages are parsed from both `<sch:assert>` and `<sch:report>` and displayed under the Info severity category.
- Invalid/custom role values outside the supported set must not create custom categories; based on the current UAC note, they should be grouped under Error unless Jira/PM confirms skip behaviour.
- Missing `role` attributes must preserve backward compatibility for existing Schematron files without roles.
- Role matching is case-sensitive; values such as `Fatal`, `ERROR`, `Warning`, or `INFO` must not be treated as valid mapped roles unless Jira explicitly changes the rule.
- The UI shows exactly four fixed categories in this order: Fatal, Error, Warn, Info.
- The UI visually differentiates Fatal, Error, Warn, and Info according to approved design mocks.
- Fatal and Error messages block save and cannot be overridden.
- Warn and Info messages allow save.
- When save is blocked, the UI shows a clear error message and identifies which messages are blocking.
- Users can filter validation messages by severity level.
- Tooltips explain the meaning of each severity level.
- The UI remains performant with many Schematron validation messages.

**Test Cases To Verify**

- Verify `<sch:assert role="fatal">` and `<sch:report role="fatal">` messages appear under Fatal and block save.
- Verify `<sch:assert role="error">` and `<sch:report role="error">` messages appear under Error and block save.
- Verify `<sch:assert role="warn">` and `<sch:report role="warning">` messages appear under Warn and do not block save.
- Verify `<sch:assert role="info">` and `<sch:report role="information">` messages appear under Info and do not block save.
- Verify role parsing works independently for both failed assertions and successful reports that produce messages.
- Verify all four categories render in severity order: Fatal, Error, Warn, Info.
- Verify no custom category appears when a Schematron file contains unsupported roles such as `critical`, `notice`, `debug`, or `blocker`.
- Verify unsupported/custom role messages are grouped under Error if that is the final accepted UAC; otherwise mark a Draft blocker if Jira still says invalid roles should be skipped.
- Verify missing-role Schematron messages continue working with existing backward-compatible behaviour and do not break save unexpectedly.
- Verify case-sensitive matching by testing `Fatal`, `ERROR`, `Warning`, and `INFO`; these must not map to supported categories unless Jira says otherwise.
- Verify Fatal plus Error together block save and the blocking message lists or highlights all blocking messages.
- Verify Fatal/Error save blocking cannot be bypassed through Save, Save All, keyboard shortcut, toolbar save, autosave path, or close-with-unsaved-changes flow.
- Verify Warn and Info messages allow Save and Save All while still remaining visible in the validation UI.
- Verify the blocked-save error message is clear, actionable, and disappears after blocking messages are fixed.
- Verify severity filters show only the selected severity and restore the full list when the filter is cleared.
- Verify tooltips for Fatal, Error, Warn, and Info are visible, accurate, and accessible through keyboard/mouse where applicable.
- Verify visual colors/icons/styles for all four severities match the approved design mocks.
- Verify performance remains acceptable with many messages across all severity categories, including scrolling, filtering, and save-block evaluation.
- Verify existing Schematron files without role attributes behave as before and existing validation failures are not silently dropped.

**Regression Areas To Carry Forward**

- Schematron parser for `<sch:assert>` and `<sch:report>` role attributes.
- Role normalization for `warn/warning` and `info/information`.
- Case-sensitive role matching and unsupported role fallback.
- Fixed severity category rendering and ordering.
- Validation message grouping, filtering, tooltip, color, and icon rendering.
- Editor save, Save All, keyboard shortcut save, autosave, and close-with-unsaved-changes flows.
- Blocking-message aggregation and error-message clearing after fixes.
- Backward compatibility for Schematron files without roles.
- Existing empty Schematron, malformed Schematron, and real-rule-violation behavior.
- Performance with large validation result sets.
- Figma/design parity for severity color, icon, tooltip, and filter UX.

**Open Questions To Carry Forward**

- Finalize the invalid/custom role behaviour: should unsupported roles be skipped, or grouped under Error as the latest UAC note says?
- What is the exact backward-compatible category or behavior for missing `role` attributes?
- Are approved Figma/design mocks available for Fatal, Error, Warn, and Info colors/icons/tooltips?
- What exact text should appear when Fatal/Error messages block save?
- Should the save-blocking rule apply to Save All, autosave, close-with-unsaved-changes, bulk save, or only explicit topic save?
- Is this behavior required on both Cloud and on-premise, and from which release or service pack?
- Should validation APIs expose severity in a normalized value, the original role value, or both?
- What performance threshold or data size should QA use for the many-message scenario?

## Gold Reference: Native PDF Print Tab Printer Marks And ICC

Use this example as a quality bar for Native PDF preset UI tickets that affect the Print tab, printer marks, page boxes, color conversion, ICC profiles, PDFReactor output, upgrade mapping, or preset cloning. The important quality signal is that UI state, saved preset JSON, generated `mergedHTML.json`, and rendered PDF output all agree.

**UAC**

- The changes are always active with no feature flag and no enabling configuration.
- The Print tab is organized in this order: Printer Marks, Page Boxes, Color & ICC.
- `All Printer's Marks` is a master toggle that turns individual mark toggles on and off together.
- Individual mark toggles update the master toggle state correctly, including after reload or reopen.
- Individual toggles are present and independently controllable for Trim Marks, Bleed Marks, Registration Marks, and Color Bars.
- Line Width is a number plus unit field and increments in `0.25 pt` steps.
- Line Color picker is available.
- Line Width and Line Color are not auto-filled; an empty value means not set.
- Page Boxes fields appear in this order: Media Box, then Bleed.
- Media Box Size supports Auto, named sizes such as RA/SRA sizes, and Custom.
- Selecting Custom reveals Width and Height fields.
- Bleed Box Width is a number plus unit field.
- Media Box and Bleed are not auto-filled; an empty value means not set.
- There is no box-size validation; users can enter any sizes without blocking or warning on nesting.
- Color Space supports RGB and CMYK, shown consistently in the UI.
- Convert Colors is a toggle defaulting to ON; for existing presets where backend state is undefined, undefined is treated as enabled.
- Rendering Intent is shown only when Convert Colors is ON.
- Rendering Intent options include Default, Perceptual, and Relative Colorimetric; Default emits nothing.
- Output Identifier Name supports None, FOGRA39, GRACoL, SWOP, SWOP 3, IFRA, Japan, Japan Newspaper, Japan Uncoated, Japan Web, and Other.
- Selecting a predefined identifier applies the built-in output profile and does not require a file or URL.
- Selecting None removes the output profile entirely.
- Selecting Other reveals Browse Profile, Use URL for Profile toggle default OFF, and Identifier Name text box.
- When Use URL for Profile is OFF, Browse Profile is usable.
- When Use URL for Profile is ON, Browse Profile and its path field are disabled, and URL for profile appears.
- Switching Output Identifier to a predefined value or None clears any previously entered Browse Profile file or URL.
- If both file path and URL exist in an existing preset, file path keeps precedence.
- Browse Profile offers ICC Profile filter for `.icc` and `.icm`, pre-selected with edit disabled similar to DITAVAL filter.
- URL for profile enforces basic URL validation; invalid URL is rejected, cannot be saved, and the URL field is cleared on failed validation.
- When Color Space is RGB and an output identifier profile is selected, a CMYK/RGB mismatch warning is shown.
- The mismatch warning clears when Color Space changes to CMYK or Output Identifier Name changes to None.
- Removed controls are not shown in the revamped Print tab: Art Box, Crop Box, Page Information, Registration prints-on-all-separations toggle, and read-only Trim Size/Page Size.
- Printer marks, page boxes, and color bars are emitted into one well-formed `@page` block with no duplicate `@page` and no stray comma before bleed.
- Bleed and Media Box values are emitted only when the user has set them.
- Printer-mark line color is emitted only when a color is set and never as an undefined color value.
- Convert Colors drives whether color conversion is applied; selecting CMYK auto-forces Convert Colors ON.
- Custom Other ICC profile is applied to both output intent and color conversion.
- Predefined Output Identifier applies the corresponding built-in output profile.
- Rendering Intent is reflected in output only when Convert Colors is ON and a non-default supported intent is selected.
- Generated output reflects Output Conformance chosen in the Advanced tab.
- Rendered PDF shows correct printer marks, bleed box, crop box, color bars, and applied ICC profile for CMYK plus Convert Colors plus profile.
- Feature works on PDFReactor 12.
- On PDFReactor 11, publishing does not break; additive settings are tolerated and output behaves as before, even if predefined/custom output profile is not applied.
- Existing preset ICC profile config maps correctly into the new UI during upgrade.
- All existing Print tab fields map correctly from old preset data into the new UI.
- Profile settings are preserved when cloned through template preset and when duplicated.

**Test Cases To Verify**

- Verify the Print tab appears without a feature flag and shows sections in order: Printer Marks, Page Boxes, Color & ICC.
- Verify `All Printer's Marks` toggles Trim Marks, Bleed Marks, Registration Marks, and Color Bars together.
- Verify changing any individual mark updates the master toggle state and persists correctly after reload or reopen.
- Verify Line Width supports number plus unit, increments by `0.25 pt`, and remains empty when not set.
- Verify Line Color picker is available and remains unset until the user picks a color.
- Verify Media Box and Bleed appear in the expected order and remain empty when not set.
- Verify Media Box Size options include Auto, named RA/SRA sizes, and Custom.
- Verify selecting Custom reveals Width and Height, and switching away hides or clears them according to product behavior.
- Verify Bleed Box Width accepts number plus unit.
- Verify no warning/blocking appears for non-nested or unusual page box sizes because box-size validation is intentionally absent.
- Verify RGB and CMYK Color Space options render consistently.
- Verify Convert Colors defaults ON for new presets and undefined existing backend state behaves enabled.
- Verify Rendering Intent appears only when Convert Colors is ON and hides when Convert Colors is OFF.
- Verify Output Identifier predefined values apply built-in profiles without requiring Browse Profile or URL.
- Verify selecting None removes output intent/profile from saved config and generated output.
- Verify selecting Other reveals Browse Profile, Use URL for Profile, Identifier Name, and URL field behavior.
- Verify Use URL OFF enables Browse Profile and path field.
- Verify Use URL ON disables Browse Profile and path field, and shows URL for profile.
- Verify switching from Other to predefined or None clears previously selected file path or URL.
- Verify existing preset with both file path and URL keeps file path precedence.
- Verify Browse Profile filters `.icc` and `.icm` files and does not allow editing the filter type.
- Verify invalid URL is rejected, cannot be saved, and clears the URL field.
- Verify RGB plus selected output identifier shows mismatch warning, and warning clears when switching to CMYK or Output Identifier None.
- Verify removed controls are absent: Art Box, Crop Box, Page Information, Registration prints-on-all-separations, and read-only Trim/Page Size.
- Verify generated `mergedHTML.json` has one well-formed `@page` block with no duplicate `@page` and no stray comma before bleed.
- Verify empty Media Box, Bleed, Line Width, and Line Color emit nothing in generated output.
- Verify selected Line Color emits a real color value and never `undefined`.
- Verify selecting CMYK auto-forces Convert Colors ON.
- Verify custom ICC profile applies to both output intent and color conversion.
- Verify predefined identifier applies the corresponding built-in output profile.
- Verify Rendering Intent output is emitted only for Convert Colors ON plus non-default supported intent.
- Verify Advanced tab Output Conformance is reflected in generated output.
- Verify rendered PDF visually shows expected printer marks, bleed box, crop box, color bars, and ICC profile behavior.
- Verify publishing works on PDFReactor 12.
- Verify PDFReactor 11 does not break publishing and tolerates unsupported additive settings.
- Verify upgrade maps existing ICC config and existing Print tab fields correctly into the revamped UI.
- Verify cloned template preset and duplicated preset preserve Print settings.

**Regression Areas To Carry Forward**

- Native PDF preset Print tab section order and field visibility.
- Master toggle and individual toggle state synchronization.
- Preset save/reload/reopen behavior.
- Number plus unit controls and `0.25 pt` increment behavior.
- Empty-field semantics where empty means not set.
- Media Box Custom width/height reveal logic.
- Absence of old removed controls.
- Color Space, Convert Colors, Rendering Intent, Output Identifier, Other profile, Browse Profile, and URL interactions.
- ICC profile file filter and URL validation.
- RGB/CMYK mismatch warning.
- Generated `mergedHTML.json`, `@page` block syntax, bleed/media output, and undefined value leakage.
- Rendered PDF visual output for printer marks, bleed/crop/color bars, and ICC profile.
- PDFReactor 12 behavior and PDFReactor 11 compatibility.
- Upgrade mapping from existing presets.
- Template preset cloning and duplicate preset preservation.

**Open Questions To Carry Forward**

- Is Relative Colorimetric fully supported in the target environment, and does it require Java 20 or above as PDFReactor documentation suggests?
- Is the Rendering Intent behavior final, or is product/dev discussion still pending?
- Which exact named RA/SRA sizes must be listed in QA data?
- Should Custom Width/Height values be cleared or merely hidden when Media Box changes away from Custom?
- Which PDF inspection tool should QA use to verify output intent, simulation profile visibility, and ICC profile behavior?
- Which PDFReactor versions are mandatory in CI, local QA, Cloud, and on-prem validation?

## Gold Reference: Old AEM Site Ditavalref Keydef Publishing

Use this example as a quality bar for Old AEM Site publishing tickets involving `ditavalref`, key definitions, `conkeyref`, resource-only behavior, and DITA-OT parity. The important quality signal is that key definitions support reference resolution without generating unwanted published pages.

**Scope**

- Old AEM Site publishing.
- Maps that use `ditavalref`.
- Key definitions and pages/content that consume those keys through `conkeyref`.
- `xref` behavior for pages implicitly treated as resource-only by DITA standards.

**UAC**

- With `ditavalref`, Old AEM Site publishing must not generate pages for `keydef` entries.
- `keydef` entries must still be available for resolving all `conkeyref` references in the published pages.
- Published pages must show resolved `conkeyref` content wherever the key definition is valid for the active conditions.
- `xref` must not resolve to pages that are implicitly marked resource-only according to DITA standards.
- Resource-only/keydef content must not appear as standalone navigable Old AEM Site pages.
- The fix must preserve DITA key resolution while preventing unwanted page generation.

**Out Of Scope**

- A `topicref` with dynamic title using `conkeyref` combined with `ditavalref` can still generate pages with a static title.
- The static-title behavior is DITA-OT behavior and should not be treated as a bug for this scope.

**Test Cases To Verify**

- Verify Old AEM Site publishing with `ditavalref` does not generate a standalone page for a `keydef` target.
- Verify a topic that uses `conkeyref` to the `keydef` publishes with the referenced content resolved correctly.
- Verify multiple `conkeyref` references backed by the same `keydef` resolve consistently across all published pages.
- Verify conditional filtering through `ditavalref` does not remove valid key definitions needed for published-page `conkeyref` resolution.
- Verify the Old AEM Site navigation/tree/sitemap does not include pages for `keydef` entries.
- Verify direct URL access or generated output artifacts do not expose resource-only/keydef content as a normal page.
- Verify an `xref` to a page implicitly resource-only by DITA standards does not resolve as a normal published page link.
- Verify regular non-resource-only `xref` links still resolve correctly in the same map.
- Verify no regression in standard topicref page generation for normal publishable topics under the same `ditavalref`.
- Verify the out-of-scope dynamic-title case is documented as DITA-OT behavior and is not marked failed unless Jira expands scope.

**Regression Areas To Carry Forward**

- Old AEM Site publishing pipeline.
- `ditavalref` condition filtering and branch handling.
- `keydef` and implicit resource-only treatment.
- `conkeyref` resolution in published output.
- `xref` resolution and non-resolution boundaries.
- Navigation, sitemap, page artifact generation, and direct URL behavior.
- DITA-OT parity, especially known dynamic-title/static-title behavior.
- Existing AEM Site or Native AEM Site behavior if the same map/preset can be published through multiple outputs.

**Open Questions To Carry Forward**

- Which exact Old AEM Site preset/template should be used for validation?
- Which `ditavalref` condition set is required to reproduce the affected keydef behavior?
- Should QA validate only generated pages/navigation, or also repository artifacts created during publishing?
- Is Native AEM Site explicitly unaffected, or should it be covered as a regression comparison?

## Gold Reference: UI Config JSON Upgrade Retention

Use this example as a quality bar for on-premise or Cloud release upgrade tickets involving `ui-config.json`, XML Editor settings, retained customizations, and default setting changes. The important quality signal is to separate upgraded-instance retention from fresh-install defaults.

**Scope**

- Upgrade from 2601 to 2605.
- XML Editor UI configuration stored through `ui-config.json` or equivalent editor configuration.
- Existing customizations that must survive upgrade.
- Fresh/default editor settings that changed or must be confirmed.

**UAC**

- Show Tags View and Show Breaking Spaces existing default values and user-updated values must be retained after upgrade.
- Custom CSS must continue to apply after upgrade.
- Custom `ui-config.json` components must continue to work after upgrade.
- Default shortcut keys and custom shortcut keys must continue to work after upgrade.
- Custom DITA attributes must continue to appear and behave as configured.
- Custom DITA elements must continue to appear and behave as configured.
- Default templates must remain available after upgrade.
- Custom snippets and custom labels must remain available after upgrade.
- For fresh/new editor defaults, Show Tags must be ON and Display Attributes must be OFF.
- XML Comments must be OFF by default.
- Quick Insert Menu must be ON by default.

**Test Cases To Verify**

- Verify an upgraded instance from 2601 to 2605 retains Show Tags View and Show Breaking Spaces values that were changed before upgrade.
- Verify a fresh 2605/new-editor profile has Show Tags ON and Display Attributes OFF by default.
- Verify XML Comments is OFF and Quick Insert Menu is ON by default after upgrade or fresh setup, based on the Jira-confirmed expectation.
- Verify custom CSS still loads in the XML Editor after upgrade and does not break editor layout, toolbar, panels, dialogs, or content rendering.
- Verify default shortcut keys still trigger the expected editor actions after upgrade.
- Verify custom shortcut keys configured before upgrade still trigger the mapped actions and do not collide with new defaults.
- Verify custom DITA attributes remain available in the attribute panel/insert flow and persist in saved topic XML.
- Verify custom DITA elements remain available in the insert/authoring flow and save correctly in topic XML.
- Verify default templates remain selectable and still create valid topics/maps.
- Verify custom snippets and labels remain visible, searchable/selectable, and insert the expected content after upgrade.
- Verify upgrade does not silently reset user/profile/folder-level editor settings back to product defaults.
- Verify no regression across old editor and new editor if both are in scope for the upgraded build.

**Regression Areas To Carry Forward**

- XML Editor settings migration and default-value initialization.
- `ui-config.json` merge/override handling.
- Custom CSS loading and editor layout.
- Shortcut key registry and collision handling.
- Custom DITA attributes/elements, snippets, labels, and templates.
- Folder profile/global profile inheritance.
- Old editor/new editor parity if both surfaces consume the same config.
- Upgrade scripts, cache/index refresh, and any manual post-upgrade config merge steps.

**Open Questions To Carry Forward**

- Is this validation only for upgraded instances from 2601 to 2605, or must fresh 2605 defaults also be tested separately?
- Which exact `ui-config.json` path/profile/folder-level config should QA use as the upgrade fixture?
- Should settings be verified at global profile, folder profile, user preference, or all supported levels?
- Are old editor and new editor both in scope after upgrade?
- Are there manual upgrade steps, config merges, cache clears, or package installs required before QA starts?
- Should Cloud parity be checked, or is this on-premise upgrade-only?

## Gold Reference: DB Log Noise And Splunk Validation

Use this example as a quality bar for DB logging tickets where the product behavior is unchanged but noisy or misleading database logs must be removed from Splunk. The important quality signal is to separate non-actionable JCR/on-prem DB warning or info noise from valid Cloud DB errors that must still be logged.

**Scope**

- No specific authoring functionality is intentionally impacted.
- DB-related warning, info, or exception noise must not be logged in Splunk for JCR or on-premise server flows when there is no valid DB failure.
- Valid DB errors must still be logged for Cloud DB server failures.
- Info-level DB logs in Splunk must be checked and removed when they are only noisy/default-value fallback logs.
- Authoring workflows and reference add/update flows are regression areas because they can exercise DB/JCR persistence paths.
- Upgrade impact is none unless Jira, PR, or release notes state otherwise.

**UAC**

- Non-actionable DB-related warnings or exceptions should not appear in Splunk for JCR/on-prem server flows.
- Valid DB errors must still appear in logs for real Cloud DB server failures.
- Info-level DB logs that only report expected/default fallback behavior should not pollute Splunk.
- `com.adobe.guides.dbdatastore.config.DatabaseConfiguratorService Error in configuring database connectionjava.lang.StringIndexOutOfBoundsException: Range [6, -1)` should no longer appear for normal JCR/on-prem flows.
- `Invalid numeric value: $[env:GUIDES_DB_VALIDATION_TIMEOUT]. Using default: 5000` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_KEEPALIVE_TIME]. Using default: 0` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_MAX_LIFETIME]. Using default: 1800000` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_LEAK_DETECTION_THRESHOLD]. Using default: 0` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_CONNECTION_TIMEOUT]. Using default: 30000` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_IDLE_TIMEOUT]. Using default: 600000` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:GUIDES_DB_MINIMUM_IDLE]. Using default: 10` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- `Invalid numeric value: $[env:DATABASE_CONNECTION_POOL_SIZE]. Using default: 10` should no longer appear as noisy Splunk output when it is expected fallback behavior.
- Authoring functionality must continue to work normally after the logging change.
- Reference addition and reference update must continue to work normally after the logging change.
- Automation is manual for now unless a Splunk-query setup exists; future automation should query Splunk and assert unwanted warning/info entries are absent.

**Test Cases To Verify**

- Verify normal authoring on a JCR/on-prem setup does not produce the listed `DatabaseConfiguratorService` warning, info, or exception noise in Splunk.
- Verify adding references on a JCR/on-prem setup completes successfully and does not produce the listed DB noise in Splunk.
- Verify updating references on a JCR/on-prem setup completes successfully and does not produce the listed DB noise in Splunk.
- Verify the exact `StringIndexOutOfBoundsException: Range [6, -1)` database configuration log is absent from Splunk for normal JCR/on-prem flows.
- Verify each listed invalid numeric environment-value fallback log is absent from Splunk when the fallback is expected and not an actionable DB failure.
- Verify info-level DB logs are removed or lowered/suppressed only for non-actionable default/fallback messages.
- Verify a real Cloud DB connection/configuration failure still logs a valid DB error with enough information for debugging.
- Verify the fix does not suppress unrelated real errors, stack traces, or actionable failure logs.
- Verify application behavior is unchanged for authoring flows after log suppression.
- Verify application behavior is unchanged for reference add/update flows after log suppression.
- Verify no upgrade-specific validation is needed when Jira confirms upgrade impact is none.
- Verify manual validation records the Splunk query, environment, time window, correlation ID/request ID if available, and exact unwanted log strings checked.

**Regression Areas To Carry Forward**

- `DatabaseConfiguratorService` database configuration and environment-variable parsing.
- JCR/on-prem startup and runtime paths that should not require Cloud DB configuration.
- Cloud DB connection failure logging and diagnosability.
- Log level changes for DB warnings, errors, and info fallback messages.
- Splunk ingestion/search patterns and exact logger/category names.
- Authoring save/open/edit flows that touch persistence.
- Reference addition, update, and related persistence/indexing flows.
- Environment-variable placeholder parsing such as `$[env:...]`.
- Default-value fallback behavior for DB timeout, pool, idle, keepalive, max lifetime, leak detection, and validation timeout settings.
- Manual-test evidence capture until Splunk-query automation exists.

**Open Questions To Carry Forward**

- Which exact Splunk index, source, sourcetype, environment, and time window should QA use?
- What is the exact JCR/on-prem environment where DB logs must be absent?
- What is the exact Cloud DB environment or safe failure simulation used to prove valid DB errors still log?
- Should noisy fallback messages be completely removed, lowered to debug, or gated by environment?
- Are all listed environment variables intentionally unset in JCR/on-prem flows, or should configuration also be corrected?
- Which request IDs, pod IDs, instance IDs, or correlation fields should QA capture with Splunk evidence?
- Is startup-only validation enough, or must authoring/reference workflows be executed after startup?
- When automation is added, which Splunk API/query credential and retention window should the test use?

## Gold Reference: Key Resolution And Broken Links Report

Use this example as a quality bar for report tickets where key references, content key references, root maps, key maps, and nested maps must resolve accurately. The important quality signal is that valid keys never show as broken, missing keys do show as broken, report metadata is accurate, and export data matches the UI.

**Scope**

- Validate key resolution in the broken links/reporting area.
- Check key definitions from root map, key map, and nested maps.
- Cover both `keyref` and `conkeyref`.
- Verify report refresh/update behavior after key create, rename, delete, indexing, and post-processing.
- Preserve existing regression behavior for key-based cross links and reusable content.

**UAC**

- Keys that exist in the root map must resolve and must not show as broken.
- Keys that exist in a key map must resolve and must not show as broken.
- Keys that exist in nested maps must resolve and must not show as broken.
- Missing keys must show as broken.
- The report must check the active root map and key map for key definitions.
- `keyref` links must show link type as `Key Reference`.
- `conkeyref` links must show link type as `Content Key Reference`.
- `keyref` and `conkeyref` rows must show the correct linked file when the key resolves.
- After creating a key, the report must update and remove false broken entries after post-processing/indexing completes.
- After renaming a key, the report must show the new key state correctly and mark old unresolved usage as broken only when applicable.
- After deleting a key, the report must show affected usages as broken.
- The Refresh button must show the latest report results.
- Valid keys must not appear in the broken list.
- After indexing completes, temporary false positives must clear and must not remain in the report.
- The broken link name must show the correct key name.
- `Used In` must show the correct topic title and path.
- File type must be accurate, such as Topic or Map.
- CSV/Excel export must contain the same correct data as the report.
- Exported `Link Type` values must be accurate.
- Exported broken link names must be accurate.
- Existing key-related regression functionality must remain unaffected for `keyref`, `conkeyref`, cross links, and reusable content.

**Test Cases To Verify**

- Verify a topic with `keyref` to a key defined in the root map resolves and does not appear in the broken report.
- Verify a topic with `conkeyref` to a key defined in the root map resolves and does not appear in the broken report.
- Verify a topic with `keyref` to a key defined in a key map resolves and does not appear in the broken report.
- Verify a topic with `conkeyref` to a key defined in a key map resolves and does not appear in the broken report.
- Verify keys defined in nested maps resolve correctly when they are in the active resolution scope.
- Verify a missing `keyref` appears as broken with the exact missing key name.
- Verify a missing `conkeyref` appears as broken with the exact missing key name.
- Verify `keyref` rows display `Key Reference` as the link type and the correct linked file when resolved.
- Verify `conkeyref` rows display `Content Key Reference` as the link type and the correct linked file when resolved.
- Verify creating a new key and completing post-processing/indexing updates the report so the previously broken key is no longer listed.
- Verify renaming a key updates the report: usages updated to the new key resolve, and stale old-key usages show broken only if still present.
- Verify deleting a key causes dependent usages to appear as broken after post-processing/indexing.
- Verify the Refresh button pulls the latest status after create, rename, delete, or post-processing completion.
- Verify valid keys do not remain as temporary false positives after indexing completes.
- Verify `Used In` shows the correct topic title and path for broken `keyref` and `conkeyref` usages.
- Verify file type is correct for topics and maps in the report.
- Verify CSV export contains correct key name, used-in title/path, file type, linked file, and link type.
- Verify Excel export contains correct key name, used-in title/path, file type, linked file, and link type.
- Verify existing keyref cross-link behavior still works outside the report.
- Verify existing conkeyref reusable-content behavior still works outside the report.

**Regression Areas To Carry Forward**

- Root map key resolution and active map context.
- Key map discovery and key definition indexing.
- Nested map key resolution scope.
- `keyref` link reporting, linked-file resolution, and broken-state classification.
- `conkeyref` content key reporting, linked-file resolution, and broken-state classification.
- Broken link name generation for missing keys.
- `Used In` topic title/path resolution.
- Topic versus map file-type classification.
- Report refresh, post-processing completion, indexing lag, and stale-cache invalidation.
- Key create, rename, delete, and dependent report recalculation.
- CSV and Excel export parity with report UI.
- Existing cross-link and reusable-content behavior driven by `keyref` and `conkeyref`.
- Automation coverage for report UI, export, and key-resolution fixtures.

**Open Questions To Carry Forward**

- Which report page/API is in scope, and is this the Broken Links report, Reports UI, or another report surface?
- Which root map/key map should QA use as the active resolution context?
- Are nested-map keys always in scope, or only when included by the active root map/key map?
- What exact post-processing/indexing completion signal should QA wait for before asserting no false positives?
- Should unresolved keys appear immediately during indexing, or should the report hide transient states until indexing completes?
- Which CSV and Excel columns are mandatory for validation?
- Are both UI report and backend/export APIs in scope?
- Is Cloud/on-prem parity required for key resolution and report export?

## Gold Reference: GUIDES-38333 Native PDF Reltable Parity

Use this example when final accepted UAC defines output parity, ordering, independent enablement controls, defaults, and explicit non-goals. The quality bar is semantic fidelity to the accepted Jira contract, not independent AC invention.

### Accepted Source-Clause Inventory

- `UAC-01` - Scope is Native PDF only. Map-level `<reltable>` related links must be added; existing topic-level `<related-links>` already work and must remain working.
- `UAC-02` - Match AEM Sites: map-level reltable entries appear first, topic-level entries appear afterward, both are shown under `Related Information`, and current formatting remains unchanged.
- `UAC-03` - For valid present/absent combinations of `<title>`, `<navtitle>`, and `<topichead>`, Native PDF behavior must match AEM Sites.
- `UAC-04` - Broken related-link entries must be shown the same way AEM Sites shows them.
- `UAC-05` - Default behavior does not generate map-level reltable links. The Native PDF preset must include `-Dargs.rellinks=nofamily` to request them.
- `UAC-06` - Floodgate feature flag `ENABLE_RELATED_LINKS_FOR_NATIVE_PDF` must be enabled on the server.
- `OOS-01` - Do not add DITA-OT-style `Related Concepts` or `Related Tasks` grouping.
- `OOS-02` - HTML5 output is intentionally different from Native PDF and AEM Sites; do not treat that difference as a failure.
- `OOS-03` - DITA-OT output validation is disabled for this ticket.

### Fidelity Lessons

- Do not replace `-Dargs.rellinks=nofamily` with the Floodgate flag. They are independent prerequisites and require separate negative configurations.
- Do not turn the accepted AEM Sites parity oracle into an invented broken-link result such as `plain text` or `not clickable` unless the AEM Sites reference output has been inspected or Jira states that result.
- Do not leave accepted ordering, unchanged formatting, `<topichead>`, or default-disabled behavior as `[Proposed]`; they are `[Confirmed]` because the final UAC approves them.
- Do not promote conditional-key, DITAVAL, deduplication, localization, performance, or historical-ticket behavior into `[Confirmed]` ACs unless the accepted UAC is updated. Keep evidence-backed additions `[Proposed]` or in `Open Questions`.
- Do not add HTML5 or DITA-OT parity as a sign-off regression. AEM Sites is the accepted comparison oracle; HTML5 difference and DITA-OT execution are explicit non-goals.

### Normalized Confirmed ACs

- AC-01 [Confirmed]: (Basic) Given `ENABLE_RELATED_LINKS_FOR_NATIVE_PDF` is enabled, the Native PDF preset contains `-Dargs.rellinks=nofamily`, and the map contains valid `<reltable>` relationships | When the map is published using Native PDF | Then map-level related-link entries appear under `Related Information` with working destinations | Evidence: `UAC-01`, `UAC-05`, and `UAC-06` from the final accepted UAC for GUIDES-38333.
- AC-02 [Confirmed]: (Integration) Given a topic receives relationships from both the map `<reltable>` and its existing topic-level `<related-links>` | When Native PDF is generated with both prerequisites enabled | Then map-level entries appear first, topic-level entries appear afterward, and current `Related Information` formatting remains unchanged as in AEM Sites | Evidence: `UAC-01` and `UAC-02` from the final accepted UAC for GUIDES-38333.
- AC-03 [Confirmed]: (Integration) Given valid map variants covering `<title>`, `<navtitle>`, and `<topichead>` as present or absent, plus AEM Sites output generated from the same inputs | When each variant is published using Native PDF with both prerequisites enabled | Then entry presence, visible labels, order, formatting, and destinations match the corresponding AEM Sites output | Evidence: `UAC-03` from the final accepted UAC for GUIDES-38333.
- AC-04 [Confirmed]: (Negative) Given a broken related-link fixture and AEM Sites output generated from that same fixture | When Native PDF is generated with both prerequisites enabled | Then the entry's presence, visible text, formatting, clickability, and destination state match AEM Sites | Evidence: `UAC-04` from the final accepted UAC for GUIDES-38333.
- AC-05 [Confirmed]: (Negative) Given the Floodgate flag is enabled but the Native PDF preset does not contain `-Dargs.rellinks=nofamily` | When the map is published | Then map-level reltable entries are not generated and existing topic-level related links retain their current behavior | Evidence: `UAC-01` and `UAC-05` from the final accepted UAC for GUIDES-38333.
- AC-06 [Confirmed]: (Negative) Given the Native PDF preset contains `-Dargs.rellinks=nofamily` but `ENABLE_RELATED_LINKS_FOR_NATIVE_PDF` is disabled | When the map is published | Then map-level reltable processing is not activated and existing topic-level related links retain their current behavior | Evidence: `UAC-01` and `UAC-06` from the final accepted UAC for GUIDES-38333.

### Internal Fidelity Mapping

```json
{
  "accepted_uac_present": true,
  "uac_fidelity": {
    "schema_version": "aem-guides-uac-fidelity-v1",
    "source_ref": "Jira GUIDES-38333 final accepted UAC",
    "accepted_clause_ids": ["UAC-01", "UAC-02", "UAC-03", "UAC-04", "UAC-05", "UAC-06"],
    "out_of_scope_clause_ids": ["OOS-01", "OOS-02", "OOS-03"],
    "clause_to_ac": {
      "UAC-01": ["AC-01", "AC-02", "AC-05", "AC-06"],
      "UAC-02": ["AC-02"],
      "UAC-03": ["AC-03"],
      "UAC-04": ["AC-04"],
      "UAC-05": ["AC-01", "AC-05"],
      "UAC-06": ["AC-01", "AC-06"]
    },
    "confirmed_ac_to_clause": {
      "AC-01": ["UAC-01", "UAC-05", "UAC-06"],
      "AC-02": ["UAC-01", "UAC-02"],
      "AC-03": ["UAC-03"],
      "AC-04": ["UAC-04"],
      "AC-05": ["UAC-01", "UAC-05"],
      "AC-06": ["UAC-01", "UAC-06"]
    },
    "proposed_ac_ids": [],
    "unresolved_clause_ids": [],
    "contradictions": [],
    "scope_expansions": [],
    "status": "pass"
  }
}
```

Customer statements about a large migrated reltable corpus are a performance-risk signal, not a numeric oracle. Until an approved workload and threshold exist, keep performance conditional in `Open Questions`; do not invent a `(Performance)` AC.

## Gold Reference: GUIDES-49325 Native AEM Site Baseline Metadata

Use this example when accepted UAC covers version-aware content and metadata propagation during Native AEM Site publishing. It demonstrates that a human UAC can have strong functional breadth while still requiring execution-level clarification before an automation draft is safe.

### What The Human UAC Gets Right

- Limits scope to `NATIVE_AEMSITE` and explicitly excludes Old AEM Site, chunked `by-topic` or `to-content` output, and multimedia metadata.
- Defines the central invariant: topic content and propagated metadata must resolve from the same selected baseline version instead of mixing baseline content with current working-copy metadata.
- Preserves existing working-copy behavior and the output preset's `metadatalist` allowlist.
- Includes custom metadata, static and dynamic baselines, incremental publishing, Copy To, map-properties fallback, and old-versus-new baseline regression coverage.
- Supplies a discriminating version fixture: the same map and topics have labels `v1.0` through `v4.0`, while `Baseline_v2.0` pins `v2.0` and current metadata differs at `v4.0`.

### Execution Gaps Normalization Must Expose

- The description alternates between generated-page `jcr:content/*` properties and `jcr:content/metadata`; automation needs the exact destination node and property path for each `metadatalist` entry.
- `Static baseline` and `Dynamic baseline` are named but their creation method, selection rule, and observable distinction are not defined.
- `Copy To scenario` does not specify the source, destination, copied version state, baseline membership, or expected post-copy repository/output oracle.
- `New baseline` and `old baseline` do not state whether age means creation time, selected version label, or regeneration order.
- `Use map properties` implies topic metadata wins when present and map metadata fills only missing fields, but the precedence oracle should be explicit for single-value, multi-value, boolean, and date/custom properties.
- Incremental publishing needs a deterministic mutation between runs and an exact assertion for republished versus untouched pages; otherwise a full publish could accidentally satisfy the test.
- These gaps do not authorize invented behavior. Keep the accepted semantic outcome `[Confirmed]`, carry the missing setup/oracle decisions to `Open Questions`, and mark the fidelity audit `blocked` until resolved.

### Accepted Source-Clause Inventory

- `UAC-01` - Metadata resolves from the baseline selected by the Native AEM Site preset.
- `UAC-02` - Working-copy publishing behavior remains unchanged.
- `UAC-03` - Only fields listed in the preset's `metadatalist` propagate.
- `UAC-04` - Custom metadata is supported.
- `UAC-05` - Validate static and dynamic baselines.
- `UAC-06` - Incremental publishing with a baseline keeps resolving metadata from that baseline and never falls back to the current working copy.
- `UAC-07` - Cover Copy To.
- `UAC-08` - Topic content and metadata resolve from the same version.
- `UAC-09` - With `Use map properties` enabled, map metadata fills a topic field only when that field is absent on the topic.
- `UAC-10` - Validate metadata propagation with both a new baseline and an old baseline.
- `OOS-01` - Old AEM Site is excluded.
- `OOS-02` - Chunked output using `by-topic` or `to-content` is excluded and tracked separately by GUIDES-53306.
- `OOS-03` - Multimedia metadata is excluded.

### Normalized Confirmed ACs

- AC-01 [Confirmed]: (Basic) Given the publication map and referenced topics have distinct `v2.0` and current `v4.0` content and metadata, `Baseline_v2.0` pins `v2.0`, and the `NATIVE_AEMSITE` preset selects that baseline | When output is generated | Then generated topic content and every propagated property named by `metadatalist` use the `v2.0` values and no `v4.0` working-copy value is substituted | Evidence: `UAC-01` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-02 [Confirmed]: (Basic) Given the same publication map is generated through the existing working-copy flow without a baseline | When Native AEM Site output is generated | Then content and configured metadata continue to resolve from the current working copy exactly as before this fix | Evidence: `UAC-02` from the accepted UAC for GUIDES-49325.
- AC-03 [Confirmed]: (Negative) Given the selected `v2.0` map version contains metadata properties both inside and outside the preset's `metadatalist` | When Native AEM Site output is generated against `Baseline_v2.0` | Then only properties listed in `metadatalist` propagate to the generated page | Evidence: `UAC-03` from the accepted UAC for GUIDES-49325.
- AC-04 [Confirmed]: (Basic) Given a custom property such as `custom-product-status` is listed in `metadatalist` with different values at `v2.0` and `v4.0` | When output is generated against `Baseline_v2.0` | Then the generated page receives the custom property's `v2.0` value | Evidence: `UAC-01` and `UAC-04` from the accepted UAC for GUIDES-49325.
- AC-05 [Confirmed]: (Integration) Given a static baseline pins the publication map and referenced topics to `v2.0` | When Native AEM Site output is generated from that baseline | Then both content and configured metadata resolve from `v2.0` | Evidence: `UAC-05` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-06 [Confirmed]: (Integration) Given a dynamic baseline resolves the publication map and referenced topics to `v2.0` under the accepted dynamic-baseline rule | When Native AEM Site output is generated from that baseline | Then both content and configured metadata resolve from `v2.0` | Evidence: `UAC-05` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-07 [Confirmed]: (Integration) Given an initial Native AEM Site publish used `Baseline_v2.0` and the current working-copy content and metadata are subsequently changed to distinct `v4.0` values | When incremental publishing runs again with `Baseline_v2.0` | Then every republished page continues to use `v2.0` content and metadata and does not fall back to `v4.0` | Evidence: `UAC-06` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-08 [Confirmed]: (Integration) Given a topic participates in the accepted Copy To workflow and the output preset selects a baseline version | When Native AEM Site output is generated after Copy To | Then the copied topic's published content and configured metadata resolve from the same selected baseline version | Evidence: `UAC-07` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-09 [Confirmed]: (Negative) Given baseline content is `v2.0` while map or topic working-copy metadata is `v4.0` | When Native AEM Site output is generated against `Baseline_v2.0` | Then no generated page combines `v2.0` topic content with `v4.0` metadata or `v4.0` content with `v2.0` metadata | Evidence: `UAC-01` and `UAC-08` from the accepted UAC for GUIDES-49325.
- AC-10 [Confirmed]: (Integration) Given `Use map properties` is enabled, a listed metadata field is absent from the topic's `v2.0` version, the map's `v2.0` version defines it, and the current map version has a different value | When output is generated against `Baseline_v2.0` | Then the generated topic receives the map's `v2.0` value | Evidence: `UAC-01` and `UAC-09` from the accepted UAC for GUIDES-49325.
- AC-11 [Confirmed]: (Negative) Given `Use map properties` is enabled and both the topic's and map's selected baseline versions define different values for the same listed metadata field | When output is generated | Then the topic's selected-baseline value is retained and the map value does not overwrite it | Evidence: `UAC-09` from the accepted UAC for GUIDES-49325.
- AC-12 [Confirmed]: (Integration) Given one baseline targets old label `v2.0` and another targets current label `v4.0` using metadata values that differ by version | When output is generated for both baselines and the old baseline is regenerated after the new one | Then each output consistently contains content and configured metadata from its own selected version without cache or working-copy fallback | Evidence: `UAC-01`, `UAC-08`, and `UAC-10` from the accepted UAC for GUIDES-49325.

### Internal Fidelity Mapping

```json
{
  "accepted_uac_present": true,
  "uac_fidelity": {
    "schema_version": "aem-guides-uac-fidelity-v1",
    "source_ref": "User-supplied GUIDES-49325 accepted UAC and Jira screenshot",
    "accepted_clause_ids": ["UAC-01", "UAC-02", "UAC-03", "UAC-04", "UAC-05", "UAC-06", "UAC-07", "UAC-08", "UAC-09", "UAC-10"],
    "out_of_scope_clause_ids": ["OOS-01", "OOS-02", "OOS-03"],
    "clause_to_ac": {
      "UAC-01": ["AC-01", "AC-04", "AC-09", "AC-10", "AC-12"],
      "UAC-02": ["AC-02"],
      "UAC-03": ["AC-03"],
      "UAC-04": ["AC-04"],
      "UAC-05": ["AC-05", "AC-06"],
      "UAC-06": ["AC-07"],
      "UAC-07": ["AC-08"],
      "UAC-08": ["AC-01", "AC-05", "AC-06", "AC-07", "AC-08", "AC-09", "AC-12"],
      "UAC-09": ["AC-10", "AC-11"],
      "UAC-10": ["AC-12"]
    },
    "confirmed_ac_to_clause": {
      "AC-01": ["UAC-01", "UAC-08"],
      "AC-02": ["UAC-02"],
      "AC-03": ["UAC-03"],
      "AC-04": ["UAC-01", "UAC-04"],
      "AC-05": ["UAC-05", "UAC-08"],
      "AC-06": ["UAC-05", "UAC-08"],
      "AC-07": ["UAC-06", "UAC-08"],
      "AC-08": ["UAC-07", "UAC-08"],
      "AC-09": ["UAC-01", "UAC-08"],
      "AC-10": ["UAC-01", "UAC-09"],
      "AC-11": ["UAC-09"],
      "AC-12": ["UAC-01", "UAC-08", "UAC-10"]
    },
    "proposed_ac_ids": [],
    "unresolved_clause_ids": ["UAC-01", "UAC-05", "UAC-07", "UAC-10"],
    "contradictions": [],
    "scope_expansions": [],
    "status": "blocked"
  }
}
```

Resolve four questions before automation handoff: the exact generated metadata node/property path (`UAC-01`), static versus dynamic baseline setup (`UAC-05`), the Copy To fixture and oracle (`UAC-07`), and the definition plus execution order of old/new baselines (`UAC-10`). No performance AC is justified by the supplied UAC because it provides no workload, latency, concurrency, or resource-risk signal.

## Gold Reference: GUIDES-10878 Baseline-Aware Map Preview

Use this human-authored UAC as the reference for a UI feature whose accepted contract mixes baseline versioning, editor parity, preview state, reference resolution, lifecycle safety, and an acknowledged but undecided performance requirement. The Jira screenshot shows the issue still in `Stage` with no final resolution, so implementation comments, linked test cases, and observed defects remain supporting evidence rather than replacements for the accepted UAC.

### What The Human UAC Gets Right

- It names the primary contract: map Preview must render the selected baseline instead of always rendering the latest working version.
- It places the switch in a specific UI surface and defines when `Show diff` becomes unavailable.
- It distinguishes static from dynamic baselines and map preview from topic preview.
- It calls out both old and new editors, mode-switch retention, working-copy refresh differences, selected-baseline deletion, and version-purge safety.
- It identifies conditions, direct and indirect references, keys, loader behavior, and performance as integration dimensions instead of testing only the happy-path toggle.
- It records customer and migration motivation without automatically turning every requested future capability into this ticket's scope.

### Normalization Gaps And Authority Boundaries

- `Dynamic baseline not in scope` conflicts with the later request for a loader in `dynamic/static baseline`; do not silently choose one interpretation.
- `Old and new Baseline` does not define whether this means creation UI, storage model, migrated data, or baseline age; the fixture and expected distinction must be confirmed.
- `Validate conditions`, `Verify direct and indirect references`, and `Check/Test for keys` are test intents, not complete product oracles. Ask which selected versions, key scopes, condition outcomes, and broken-reference behavior are expected.
- Loader behavior lacks trigger, placement, dismissal, timeout, failure, and rapid-switch expectations.
- `Check performance impact. TBD` proves performance matters but supplies no dataset size, percentile, latency budget, cache state, concurrency, or resource ceiling. Keep the performance AC proposed and blocked until these values are approved.
- The business-capability bullets about reverting baseline versions and editing version-specific metadata are future/customer context. A later Jira comment explicitly excludes revert/rollback from this feature; do not promote either capability into a Confirmed AC.
- A later Jira comment says Reports are not part of this requirement. Related bugs, subtasks, and linked test cases provide regression and automation evidence, not new accepted behavior.

### Accepted Source-Clause Inventory

- `UAC-01`: Map Preview displays content from the selected baseline rather than always displaying the latest working version.
- `UAC-02`: Preview filter panel shows a baseline on/off switch.
- `UAC-03`: The feature applies to both old and new baselines.
- `UAC-04`: Static baselines are in scope; dynamic baselines are not in scope.
- `UAC-05`: The feature applies only to map preview, not topic preview.
- `UAC-06`: `Show diff` is hidden while the baseline switch is on and a baseline is selected.
- `UAC-07`: Conditions must be validated with baseline-aware preview.
- `UAC-08`: Direct and indirect references must be validated.
- `UAC-09`: The behavior applies to both old and new editors.
- `UAC-10`: A loader matching Author-mode loading is requested for dynamic/static baseline preview.
- `UAC-11`: Baseline selection and preview state are retained while switching among Author, Source, and Preview.
- `UAC-12`: Keys must be validated.
- `UAC-13`: A version referenced by a baseline cannot be purged.
- `UAC-14`: If the selected baseline is deleted, the existing preview remains unchanged until another baseline is selected or the switch is turned off.
- `UAC-15`: Working-copy updates refresh automatically in the new editor; the old editor requires its refresh action.
- `UAC-16`: Performance impact must be checked, with acceptance values still TBD.
- `OOS-01`: Dynamic baseline behavior is outside this ticket.
- `OOS-02`: Topic preview is outside this ticket.
- `OOS-03`: Revert or rollback to a baseline version is outside this ticket according to the later scope clarification.
- `OOS-04`: Reports behavior is outside this ticket according to the later scope clarification.

### Normalized Confirmed ACs

- AC-01 [Confirmed]: (Functional) Given a map has a valid static baseline and that baseline is selected in Preview | When map Preview finishes loading | Then the rendered map content represents the versions selected by that baseline rather than the latest working-copy versions | Evidence: `UAC-01`, `UAC-04`, and `UAC-05` from the accepted UAC for GUIDES-10878.
- AC-02 [Confirmed]: (UI) Given a map is open in Preview | When the user opens the filter panel | Then a baseline on/off switch is available for baseline-aware map preview | Evidence: `UAC-02` from the accepted UAC for GUIDES-10878.
- AC-03 [Confirmed]: (Negative) Given a topic rather than a map is open in Preview | When the user opens the filter panel | Then the baseline-preview switch is not shown | Evidence: `UAC-05` and `OOS-02` from the accepted UAC for GUIDES-10878.
- AC-04 [Confirmed]: (UI) Given the baseline switch is on and a baseline is selected | When the Preview filter controls are displayed | Then `Show diff` is hidden | Evidence: `UAC-06` from the accepted UAC for GUIDES-10878.
- AC-05 [Confirmed]: (Compatibility) Given the same eligible map and static baseline are available in the old and new editors | When baseline-aware map Preview is used in each editor | Then each editor renders the selected-baseline content | Evidence: `UAC-09` from the accepted UAC for GUIDES-10878.
- AC-06 [Confirmed]: (State) Given a baseline is selected and its map content is displayed in Preview | When the user switches among Author, Source, and Preview and returns to Preview | Then the baseline selection and baseline-aware preview state are retained | Evidence: `UAC-11` from the accepted UAC for GUIDES-10878.
- AC-07 [Confirmed]: (Negative) Given a repository version is referenced by a baseline | When version purge is attempted for that version | Then the purge is refused and the baseline-referenced version remains available | Evidence: `UAC-13` from the accepted UAC for GUIDES-10878.
- AC-08 [Confirmed]: (Lifecycle) Given a selected baseline is currently rendered in Preview | When that baseline is deleted elsewhere | Then the current preview remains unchanged until the user selects another baseline or turns off the baseline switch | Evidence: `UAC-14` from the accepted UAC for GUIDES-10878.
- AC-09 [Confirmed]: (Compatibility) Given working-copy content changes while working-copy Preview is active | When the change is saved | Then the new editor refreshes the working-copy preview automatically, while the old editor shows the update only after its refresh action | Evidence: `UAC-15` from the accepted UAC for GUIDES-10878.
- AC-10 [Proposed]: (Performance) Given the approved large-map fixture, cache state, editor matrix, and baseline-preview latency budget recorded in Jira | When a user selects a static baseline and Preview resolves content, conditions, references, and keys | Then loader behavior, response latency, and resource use remain within those approved limits without stale or partially mixed-version content | Evidence: performance risk acknowledged by `UAC-16`; Blocker: workload, percentile, latency, concurrency, and resource thresholds are TBD.

### Internal Fidelity Mapping

```json
{
  "accepted_uac_present": true,
  "uac_fidelity": {
    "schema_version": "aem-guides-uac-fidelity-v1",
    "source_ref": "User-supplied GUIDES-10878 accepted UAC and Jira screenshot",
    "accepted_clause_ids": ["UAC-01", "UAC-02", "UAC-03", "UAC-04", "UAC-05", "UAC-06", "UAC-07", "UAC-08", "UAC-09", "UAC-10", "UAC-11", "UAC-12", "UAC-13", "UAC-14", "UAC-15", "UAC-16"],
    "out_of_scope_clause_ids": ["OOS-01", "OOS-02", "OOS-03", "OOS-04"],
    "clause_to_ac": {
      "UAC-01": ["AC-01"],
      "UAC-02": ["AC-02"],
      "UAC-04": ["AC-01"],
      "UAC-05": ["AC-01", "AC-03"],
      "UAC-06": ["AC-04"],
      "UAC-09": ["AC-05"],
      "UAC-11": ["AC-06"],
      "UAC-13": ["AC-07"],
      "UAC-14": ["AC-08"],
      "UAC-15": ["AC-09"]
    },
    "confirmed_ac_to_clause": {
      "AC-01": ["UAC-01", "UAC-04", "UAC-05"],
      "AC-02": ["UAC-02"],
      "AC-03": ["UAC-05"],
      "AC-04": ["UAC-06"],
      "AC-05": ["UAC-09"],
      "AC-06": ["UAC-11"],
      "AC-07": ["UAC-13"],
      "AC-08": ["UAC-14"],
      "AC-09": ["UAC-15"]
    },
    "proposed_ac_ids": ["AC-10"],
    "unresolved_clause_ids": ["UAC-03", "UAC-07", "UAC-08", "UAC-10", "UAC-12", "UAC-16"],
    "contradictions": ["UAC-10 requests dynamic/static loader behavior while OOS-01 excludes dynamic baselines"],
    "scope_expansions": [],
    "status": "blocked"
  }
}
```

Before automation handoff, define old/new baseline fixtures (`UAC-03`), the selected-version oracles for conditions, direct/indirect references, and keys (`UAC-07`, `UAC-08`, `UAC-12`), resolve the dynamic-loader contradiction (`UAC-10`), and approve measurable performance limits (`UAC-16`). Keep revert/rollback, version-specific metadata editing, Reports, and linked implementation defects outside Confirmed AC unless a newer accepted Jira clause explicitly adds them.

## Caution Reference: GUIDES-31711 DITAVAL Taxonomy Complaint Closed as Working as Designed

Use this example to prevent a customer complaint, screenshots, or a standards interpretation from being promoted into accepted UAC when Jira contains no accepted criteria and the product decision is `Working as Designed`. It is valuable historical context and regression evidence, but it is not a trusted behavior contract for a taxonomy-changing enhancement.

### Verified Current Evidence

- Repository Search shows `Ditaval Files` as a dedicated filter under `Non-DITA Files`.
- The DITAVAL creation flow uses the generic `New topic` dialog and a `Ditaval` template.
- Reports display a `.ditaval` asset with file type `Others`.
- The closed Jira clarification says all three choices are intentional: Repository Search uses a dedicated DITAVAL filter, the creation surface uses `topic` as a generic editable-piece abstraction, and Reports uses `Others` unless a separate enhancement requests a new category.
- The same clarification says a distinct Reports category or harmonized taxonomy requires an enhancement request rather than a bug fix.

### Standards And Authority Boundary

- OASIS DITA defines DITAVAL as a document type for conditional-processing profiles. It is not a DITA topic or DITA map.
- The DITA standard does not prescribe AEM Guides UI taxonomy, search-facet placement, creation-dialog labels, or Reports categories.
- `Other DITA type document` in the complaint is a requested interpretation, not accepted AEM Guides UI copy.
- The problem statement and screenshots prove the observed differences; they do not prove that the differences are defects.
- The Jira has no accepted UAC. Therefore `accepted_uac_present=false`, no clause may become `[Confirmed]`, and historical reuse remains `candidate`/non-fix caution.

### What The Analyzer Must Learn

- Keep the complaint lines as context statements, not acceptance clauses.
- Tag the evidence with `ditaval_asset`, `repository_search`, `creation_dialog`, `reports`, `file_type_taxonomy`, and `cross_touchpoint_taxonomy` so similar tickets can retrieve the decision.
- Preserve the historical outcome as `expected_product_behavior` or non-fix decision.
- Use the decision to challenge a new plan that assumes all three surfaces must use the same label without approved enhancement UAC.
- Never use this ticket alone to define a new canonical DITAVAL enum, UI label, migration rule, API value, or report-export value.

### Proposed Enhancement ACs Only

- No Confirmed AC is justified by GUIDES-31711.
- AC-01 [Proposed]: (Scope) Given product management has approved an exact canonical DITAVAL taxonomy and label in a new enhancement Jira | When that enhancement is implemented | Then its accepted UAC explicitly identifies which of Repository Search, creation, Reports, APIs, and exports must adopt the taxonomy and which current surface semantics remain unchanged.
- AC-02 [Proposed]: (Repository Search) Given the approved enhancement keeps the dedicated DITAVAL search capability | When a user filters repository assets for DITAVAL | Then only matching `.ditaval` assets are returned under the approved category without reducing the current filter's discoverability.
- AC-03 [Proposed]: (Creation UI) Given the approved enhancement defines DITAVAL creation terminology | When a user selects the `Ditaval` template | Then the dialog uses the approved DITAVAL wording and creates the same valid `.ditaval` asset without changing topic, map, or Markdown creation behavior.
- AC-04 [Proposed]: (Reports) Given the approved enhancement defines the Reports file-type value for DITAVAL | When a report contains a `.ditaval` asset | Then the row displays and filters by that exact approved value instead of silently inheriting a different surface's label.

### Required Open Questions Before Automation Handoff

- What exact canonical display label and persisted enum are approved, and are they intentionally different?
- Is Repository Search expected to remain under `Non-DITA Files` because that grouping serves search behavior, or must only its display label change?
- Must the creation dialog stop using the generic `topic` abstraction, or is only helper text/template labeling changing?
- Does Reports scope include the UI table only, or also downloaded CSV, APIs, saved filters, sorting, and analytics?
- Must existing `.ditaval` assets be reindexed or migrated, and what is the backward-compatible value for older records?
- Which AEM Guides versions, old/new editor surfaces, locales, roles, and upgrade paths are in scope?
- No performance AC is justified by the supplied ticket because it contains no workload, latency, scale, concurrency, or resource-risk signal.

### Regression Areas

- Repository Search filter counts, combined filters, clear/reset behavior, and `.ditaval`-only result accuracy.
- DITAVAL template selection, filename/extension handling, validation, save, reopen, and editing.
- Reports file-type display, filtering, sorting, refresh, and download behavior if the enhancement includes those surfaces.
- Existing DITA topic, DITA map, Markdown, image, multimedia, document, and JSON classifications must not move unintentionally.
- Customer-specific permissions and KONE content must not change the taxonomy outcome unless the enhancement explicitly introduces tenant configuration.

## Caution Reference: GUIDES-30001 Configuration-Gated Navtitle Button

Use this example to distinguish a feature that is hidden by configuration from a removed or deprecated feature. The Jira was closed as `Working as Designed`, has `UAC Not Required`, has no fix version, and records no product code change. Its value is configuration, documentation, automation, and regression evidence only.

### Verified Final Jira Evidence

- The customer screenshot shows the earlier `Refresh Navigation Title Attribute` control on a DITA map.
- Live Jira comments establish that the capability still exists and is controlled by the existing `ui_config` `ditaAttributes` setting.
- The value recorded by engineering to enable the capability is:

```json
"ditaAttributes": {
  "attributes": [],
  "constraint": false,
  "required": {"navtitle": true}
}
```

- The default `required` object is empty, so the button is hidden unless the configuration explicitly requires `navtitle`.
- The final product decision says the functionality works as expected, no product change was made, only automation was added, and the ticket was closed.
- The `Doc_Required` label and comments establish a documentation gap; they do not establish that the button was deprecated.
- Earlier comments disagree about whether the capability worked in 4.6 and propose a different label, `Reset navtitle`. Those superseded comments must not override the final no-change decision or be treated as accepted UI copy.

### Answers To The Enterprise Questions

- Why was the button not visible in 5.0? The 5.0 behavior correctly honored the existing UI configuration; the required `navtitle` entry was absent from the default configuration, so the control remained hidden.
- Was the button deprecated? This Jira provides no deprecation evidence. It concludes that the capability still exists and is configuration-gated.
- How is the functionality retained? Add the verified `ditaAttributes.required.navtitle=true` configuration, then validate the existing map behavior. Do not claim a product patch is required from this ticket.
- Where is the documentation? The Jira requests documentation but does not supply an authoritative published documentation URL. A generated plan must keep the final documentation location as an open question unless current official documentation is inspected.

### What The Analyzer Must Learn

- Treat whole-field markers such as `UAC Not Required`, `Acceptance Criteria: N/A`, or `None` as absence of accepted UAC, not as acceptance clauses.
- Preserve `Working as Designed` as `expected_product_behavior` with `candidate` reuse.
- Tag the historical context with `navtitle`, `ui_configuration`, `configuration_visibility`, `toolbar_customization`, and `documentation_gap`.
- Exact configuration evidence may support setup and regression coverage, but it must not become a `[Confirmed]` AC when the Jira explicitly has no UAC.
- Do not infer that a missing button means removal, deprecation, permission loss, feature-flag disablement, or unsupported release.
- Do not infer unverified behavior for `navtitle=false`, malformed JSON, conflicting overlays, toolbar position, UI label, editor variants, or upgrade migration.

### Proposed ACs Only For A New Change Ticket

- No Confirmed AC is justified by GUIDES-30001.
- AC-01 [Proposed]: (Configured visibility) Given an approved UI configuration contains `ditaAttributes.required.navtitle=true` | When a supported DITA map authoring surface loads | Then the navigation-title refresh control is visible in every explicitly approved view and position.
- AC-02 [Proposed]: (Default visibility) Given the effective UI configuration has an empty `required` object and no higher-priority overlay requires `navtitle` | When the same map surface loads | Then the navigation-title refresh control is not displayed.
- AC-03 [Proposed]: (Configuration removal) Given the control is visible through a custom configuration | When that customization is removed and the effective configuration returns to the supported default | Then the control is hidden after the documented configuration reload lifecycle.
- AC-04 [Proposed]: (Functional oracle) Given the control is visible and a map contains a testable stale `navtitle` case | When the user activates the control | Then the exact approved navigation-title update behavior occurs without changing unrelated map references or content.

### Required Open Questions Before Automation Handoff

- What is the authoritative file or configuration service, overlay precedence, deployment path, and reload/cache lifecycle for `ui_config`?
- Which views are supported: map Author, Layout, Preview, Read view, old editor, new editor, or a defined subset?
- What is the final visible label and icon: `Refresh Navigation Title Attribute`, `Reset navtitle`, or another approved design?
- What exact source XML and UI result should occur when the action runs for missing, stale, explicit, inherited, or locked `navtitle` values?
- Is `navtitle=false` valid, and how do malformed, duplicate, or conflicting configuration values fail?
- Does the same behavior apply to fresh 5.0 installs, upgrades from 4.3/4.6, 5.1+, Cloud, and on-premise?
- Which official documentation page records the setting, default, supported views, and rollback steps?
- No performance AC is justified by this Jira because it contains no workload, latency, scale, concurrency, or resource-risk signal.

### Regression Areas

- Effective configuration precedence, JSON validation, cache invalidation, and rollback to the default hidden state.
- DITA map Author/Layout view loading, toolbar composition, control duplication, localization, keyboard accessibility, and role/permission parity.
- Navigation-title refresh behavior for topicrefs with explicit, missing, stale, inherited, key-based, and subject-scheme-related values.
- Author/Preview switching, repository drag/drop, topic-reference insertion, reusable content, save/reopen, lock/check-out, and map refresh.
- Upgrade retention for custom UI configuration and the absence of accidental changes to unrelated `ditaAttributes` controls.
- Automation must assert both visibility states and the resulting source/content behavior; a visibility-only test is insufficient.

## Caution Reference: GUIDES-28847 Metadata Filter Index Incident

Use this example to prevent an early support hypothesis from becoming a trusted root cause. The issue has `UAC_Not_Required` and `Won't_Automate` labels, so it supplies historical incident, remediation, and regression evidence rather than accepted product UAC.

### Screenshot And Symptom Evidence

- The customer reported 442 DITA topic files, but applying only the `DITA Topic` file-type filter returned 2 files.
- Selecting both `DITA Topic` and `Others` returned more files, which exposed incorrect filtering or index results.
- The supplied screenshot verifies the combined `DITA Topic` plus `Others` filter state and a paginated view showing `50 of 442 files`.
- The screenshot does not by itself prove why the records were missing, whether the filter uses OR or union semantics internally, or whether custom metadata changed the stored file type.

### Superseded Investigation Hypotheses

- The description initially proposed that recent retrieval API changes, custom namespaced metadata such as `test:type`, or the `TypeFilter` class could be responsible.
- Those statements use tentative language and were not confirmed.
- Engineering later established that namespaced properties are not used by Reports file-type filtering.
- The early custom-index assumption was explicitly marked invalid.
- These theories may be retained only as disproved investigation history. They must never be returned as the root cause, current expected behaviour, or a Confirmed AC.

### Confirmed RCA And Remediation

- The query including `nodename=*.dita`, `type=dam:Asset`, and the target path returned one result, while the equivalent query without `type=dam:Asset` returned the correct set.
- All inspected DITA assets still had the expected `jcr:primaryType=dam:Asset`; the content itself was not reclassified by the custom namespace.
- The discrepancy identified an environment-specific problem with the `damAssetLucene` index, which had not been created correctly.
- Reindexing `damAssetLucene` restored the filtering results in the clone environment.
- KONE IT subsequently tested and validated that the issue was fixed after reindexing.
- Root-cause provenance is the later confirmed Jira comment, not the earlier SC hypothesis. Customer validation is remediation evidence, not an accepted product behavior contract.

### What The Analyzer Must Learn

- Split chronological comment digests into individual comments before extracting RCA; otherwise an early `RCA:` heading can incorrectly absorb later comments.
- Reject tentative causal sections containing `could`, `may`, `seems`, `hypothesis`, `suggest disabling`, or `to confirm` unless the same evidence contains a later explicit confirmation.
- Rank confirmed causal evidence above tentative sections and retain explicit invalidation text so the disproved theory cannot reappear as the answer.
- Tag the context with `metadata_report`, `file_type_filter`, `custom_namespace`, `type_filter`, `oak_index`, `dam_asset_lucene`, `reindexing`, `environment_specific`, `filter_union`, and `result_count`.
- Store `UAC Not Required` as status evidence, not as an acceptance-criteria chunk.
- Keep the Jira at `candidate` reuse unless a separate fixed product ticket provides accepted UAC, implementation evidence, and a reusable QA oracle.

### Proposed ACs Only For A New Product Change

- No Confirmed AC is justified by GUIDES-28847.
- AC-01 [Proposed]: (DITA Topic accuracy) Given a healthy supported index and a report scope containing a known number of DITA topics plus non-topic assets | When the user applies only `File type = DITA Topic` | Then every and only the expected DITA topic assets are returned across all result pages and the displayed total equals the independently calculated oracle.
- AC-02 [Proposed]: (Combined filters) Given the same fixture contains DITA topics and assets classified as `Others` | When the user selects both values | Then the result set follows the explicitly approved union semantics with no missing or duplicate assets and an exact count oracle.
- AC-03 [Proposed]: (Namespace independence) Given equivalent DITA topic assets with and without an extended metadata-schema property such as `test:type` | When the same file-type filter runs on a healthy index | Then both assets retain the same approved file-type classification and result inclusion unless an accepted requirement explicitly maps that namespace into file type.
- AC-04 [Proposed]: (Index recovery) Given a reproducible unsupported or stale `damAssetLucene` state and an approved recovery procedure | When reindexing completes successfully | Then the same query and UI filter return the expected full result set without requiring content edits or metadata removal.

### Required Open Questions Before Automation Handoff

- What exact Jira resolution was selected, and was any product fix, hotfix, index-definition update, or only operational reindexing delivered?
- What is the supported `damAssetLucene` definition and health oracle for the affected AEM/Guides version?
- What exact expected counts apply to `DITA Topic`, `Others`, and their combined selection after deduplication?
- Are file-type selections defined as OR/union, and does the same rule apply to downloaded CSV, pagination, sorting, and refreshed results?
- Which custom namespaces and extended schemas must be included as negative controls?
- What is the supported reindex procedure, required role, expected duration, failure handling, and production rollback?
- Does the issue reproduce on a clean environment, after upgrade, or only in the affected KONE index state?
- The 442-file corpus is a useful functional scale fixture, but no performance AC is justified because Jira supplies no latency, throughput, concurrency, or resource threshold.
- `Won't_Automate` records this ticket's historical automation decision; it does not prove that a future product change is inherently unautomatable.

### Regression Areas

- File-type filters for DITA Topic, DITA Map, DITAVAL/Others, images, multimedia, documents, and mixed selections.
- Exact totals across pagination, refresh, sorting, no-result states, filter removal, and downloaded report data.
- Assets with no custom metadata, simple metadata, and multiple custom namespaced properties.
- Query consistency with and without `type=dam:Asset`, plus index health before and after an approved reindex.
- Document-state, reference-type, tag, and file-type filter intersections must not hide or duplicate valid results.
- Environment upgrades, index recreation, custom index overlays, and reindex completion must not leave stale result counts.

## Caution Reference: GUIDES-28667 Custom Preview Button Configuration Migration

Use this example to distinguish a Jira field value of `Resolution: Fixed` from a verified product-code fix. Live Jira chronology shows that the customer was unblocked through custom-toolbar configuration, the result was explicitly called a workaround rather than a fix, and the remaining action moved to documentation.

### Verified Historical Evidence

- In AEM Guides 5.0, KONE reported that its custom `Export PDF` action for DITA-OT PDF was visible in Preview mode only while the file was locked; the earlier customization had allowed use in locked and unlocked states.
- The Jira description identifies the supplied customization as `KONEui_config.json`.
- An engineering comment says an updated `editor_toolbar.json` added the button for both lock and unlock scenarios.
- Support explicitly states that this configuration unblocked the customer but was still a workaround and not a fix.
- A later engineering comment says custom buttons configured in `ui_config.json` would not work in Preview and needed to be ported to `editor_toolbar.js` with explanatory documentation.
- The Jira was then closed because no further action remained on it, while documentation was tracked in GUIDES-28909.
- The evidence conflicts on the supported target filename: the attachment and one comment say `editor_toolbar.json`, while the migration comment says `editor_toolbar.js`. A generated plan must preserve this conflict as an open question until current product code or official documentation resolves it.

### What The Analyzer Must Learn

- Classify this history as `historical_outcome=configuration_migration`, `resolution_mechanism=configuration_migration`, and `resolution_evidence_source=jira_comment_configuration_migration`.
- Keep `learning_confidence=caution` and `is_verified_fix=false`; the Jira resolution field alone does not prove a product implementation.
- Preserve the workaround, configuration migration, and documentation closure as short provenance excerpts without copying full comments into the learning chunk.
- If a later comment explicitly records a merged, released, implemented, or build-verified product fix, that later evidence may override the earlier workaround classification.
- Tag comparable contracts with `custom_button`, `preview_mode`, `locked_state`, `unlocked_state`, `editor_toolbar_configuration`, `configuration_migration`, `ui_configuration`, `dita_ot`, `output`, and `documentation_gap`.
- No accepted UAC is present. The symptom and workaround are historical regression evidence only and must not define current supported behaviour.
- No Confirmed AC is justified by GUIDES-28667.

### Proposed ACs Only For A New Supported-Configuration Change

- AC-01 [Proposed]: (Visibility state matrix) Given the exact supported custom-toolbar file and schema contain one valid `Export PDF` action for Preview mode | When an authorized user opens the same supported DITA asset while it is locked and while it is unlocked | Then exactly one enabled action is visible in each approved state, with no duplicate or stale action after the state changes.
- AC-02 [Proposed]: (Action result) Given the action is visible in each approved lock state | When the user invokes it | Then the configured DITA-OT PDF operation starts once for the current asset and exposes the approved success or failure feedback without changing the asset lock state.
- AC-03 [Proposed]: (Upgrade migration) Given a supported pre-5.0 customization and the approved 5.0-or-later migration procedure | When the configuration is migrated and caches are refreshed as documented | Then the action retains its approved Preview visibility and invocation behaviour without changing unrelated toolbar actions or authoring modes.

### Required Open Questions Before Automation Handoff

- Is the supported target `editor_toolbar.json`, `editor_toolbar.js`, or a generated JavaScript artifact sourced from JSON? QA impact: the answer changes the fixture, deployment path, schema validation, and cache-refresh oracle.
- Which action keys, command handler, target asset types, Preview variants, and DITA-OT PDF preset are officially supported? QA impact: without them, visibility can be checked but invocation and output correctness cannot be deterministic.
- Are locked and unlocked the complete state matrix, or must testing also cover another user's lock, read-only access, checkout, insufficient permission, and stale lock transitions? QA impact: each supported state requires an explicit visibility and enabled-state expectation.
- Was `ui_config.json` support intentionally removed, deprecated, or never supported for Preview in 5.0? QA impact: this determines whether legacy behavior is a migration boundary, backward-compatibility defect, or unsupported customization.
- What official page under GUIDES-28909 documents migration, rollback, cache invalidation, and release applicability? QA impact: documentation is the authority for upgrade and supportability checks because GUIDES-28667 delivered no verified product patch.
- Does the action apply to maps, topics, Markdown, locked read-only previews, old/new editor, and every supported browser? QA impact: each included surface expands the functional and automation matrix.
- No performance AC is justified by this Jira; it provides no latency, job-start, throughput, concurrency, or resource threshold.

### Regression Areas

- Re-test custom Preview actions in locked, unlocked, lock-transition, reopen, and refresh flows because toolbar conditions can leave stale visibility or duplicate controls.
- Re-test Author, Source, and Preview mode switching because moving a customization into the editor-toolbar configuration can unintentionally expose the action in unsupported modes.
- Re-test DITA maps, topics, and any explicitly supported Markdown surface because related tickets show Preview action availability can vary by asset type.
- Re-test built-in Download/PDF actions alongside the custom action because overriding a toolbar command must not hide, duplicate, or redirect the product-provided action.
- Re-test configuration overlay precedence, syntax failure, cache invalidation, upgrade retention, and rollback because the historical resolution depended on moving the customization between configuration mechanisms.
- Re-test permissions and lock ownership because a visibility rule that only checks `locked` can expose the action to the wrong user or hide it for a valid unlocked workflow.

## Accepted Reference: GUIDES-28443 Bulk Metadata Manage Recovery

Use this example for report operations that combine a backend query correction, asynchronous UI state, bulk-result accounting, Cloud/on-premise parity, and a performance-shaped incident without an approved performance SLA. The full accepted UAC belongs to GUIDES-28443 and the 2507 delivery. GUIDES-29778 is a separate 5.0.1 hotfix point-fix and must not inherit the complete 2507 contract.

### Verified Defect And Root Cause

- The failing workflow is `Map Console > Reports > Metadata > Manage`, especially `Select all` where `allAssets=true`.
- The affected endpoint is `bin/guides/v1/map/reports/metadata/tags/common`.
- Engineering confirmed that the query-building path omitted UUID-to-path conversion. A null path was then passed into the query, causing a scan of all data and preventing common tags from being returned.
- This confirmed RCA supersedes the earlier question about a potentially missing index; do not return the index theory as the root cause.
- Customer-impact evidence includes a repository with approximately 20,000 DITA files, maps with 10-15 or more dependencies, multiple API triggers, CPU/memory pressure, pod instability, and a Cloud observation where seven files exceeded one minute and ended in HTTP 503.
- Those observations prove `performance_matters=true`; they do not define an approved performance pass/fail threshold.
- The supplied screenshot shows a service-outage banner only. It is incident evidence, not proof of Manage-button state, loader behavior, query results, or the accepted UI oracle.

### Full Accepted 2507 Contract

- Manage must apply tags and document state to all selected assets or a selective set of assets.
- The Manage dialog must show common tags and apply the user's tag changes.
- The workflow covers DITA and non-DITA assets, Custom tags and OOTB tags, and both Cloud and on-premise Guides deployments.
- A bulk operation must report the files updated and files skipped; any skipped file must be counted.
- Negative dialogs must be validated, and a timeout must surface a proper error message.
- After Manage is triggered, a loader/progress indication is shown and the Manage button remains disabled until the API response completes, preventing duplicate triggers; it becomes available again after completion.
- The Filters panel shows a loading shimmer and withholds details until the API response is available.
- The same disabled/in-progress state applies to the Fix Link button in Broken Links.
- If Fix Links cannot repair a link, the accepted behavior keeps it broken and does not show a separate error dialog.
- Existing filters continue to work, and Manage applies only to the files present or visible in the Metadata tab.
- The accepted UAC explicitly says the API correction does not introduce a separate performance change. Therefore `performance_contract_complete=false` until an approved latency, timeout, throughput, concurrency, and resource contract is supplied.

### Release-Scope Boundary

- GUIDES-29778 states: the ticket is for the 5.0.1 hotfix only, while the copied UAC is for 2507.
- Its explicit hotfix scope is limited to Manage/Broken Link button disable-enable behavior plus the common-tags point fix.
- Hotfix validation covered select-all common tags, tag/document-state updates for all and selective files, filters, and Broken Links on builds 5.0.0.211 and 5.0.1.2.
- The hotfix comment records a known issue: closing the Fix Link dialog without fixing a link while filters are applied refreshes the tab and clears the filters. Preserve this as a known regression signal, not an accepted expected behavior.
- Set `release_scope_split=true`, `release_scope_source=jira_comment_release_scope`, `contract_complete=false`, and `reuse_tier=candidate` for the copied UAC on GUIDES-29778. Never generate the entire 2507 plan as 5.0.1 hotfix sign-off scope.

### Verification And Automation Provenance

- `Acceptance Criteria Looks good to me` is sign-off only and is not execution evidence.
- `The ticket passes all the mentioned points of Acceptance Criteria. EM Review done` is explicit acceptance-validation evidence.
- The later customer validation is stronger: smaller and larger file sets were tested, the button disabled on first click, and a progress bar was shown.
- Engineering added API automation for common tags across all assets.
- The accepted automation gap is UI coverage for Select all, common tags, and Manage disable/enable behavior.
- Automation notes are context and coverage evidence; they must not become extra product UAC clauses.

### Normalized Confirmed ACs

- AC-01 [Confirmed]: (All/selective update) Given the Metadata report contains supported visible assets | When an authorized user applies tags or document state through Manage to all selected files or a selective set | Then every eligible targeted file is updated according to the action and untargeted files remain unchanged.
- AC-02 [Confirmed]: (Common tags) Given all targeted assets share one or more tags | When Manage loads for that selection | Then the dialog returns the common tags and persists the user's supported tag updates.
- AC-03 [Confirmed]: (Asset and deployment matrix) Given supported DITA and non-DITA assets with Custom and OOTB tags | When the same Manage workflow runs on an approved Cloud or on-premise build | Then the accepted tag and document-state behavior remains equivalent for every included matrix entry.
- AC-04 [Confirmed]: (Bulk accounting) Given a bulk update contains files that can be updated and files that must be skipped | When processing completes | Then the report identifies the updated files and skipped files and exposes an exact skipped count.
- AC-05 [Confirmed]: (Single-trigger lifecycle) Given Manage is enabled | When the user triggers it | Then one operation starts, a loader/progress indication appears, Manage remains disabled until the API completes, and it becomes enabled again only after the accepted terminal response.
- AC-06 [Confirmed]: (Filter loading state) Given the Filters panel depends on the same API response | When loading is in progress | Then the complete panel shows a shimmer and does not expose partial details before the response is available.
- AC-07 [Confirmed]: (Timeout feedback) Given the API does not respond within the configured timeout | When the request reaches that timeout | Then the user sees the approved error message and the UI exits the in-progress state without accepting duplicate triggers.
- AC-08 [Confirmed]: (Broken Links state) Given Fix Link processing is started | When it is running | Then the Fix Link button follows the same disable-enable lifecycle; if the link cannot be fixed, it remains broken without a separate error dialog.
- AC-09 [Confirmed]: (Visible-file scope) Given Metadata filters reduce the visible file set | When Manage runs | Then it applies only to the accepted present/visible set and existing filter behavior remains unchanged.

### Required Open Questions Before Automation Handoff

- What exact request/response schema, pagination behavior, and `allAssets` semantics define the targeted set? QA impact: this is required to prove that visible, selected, and all assets are not mixed.
- What timeout value, HTTP result, localized error copy, retry rule, and button re-enable behavior are approved? QA impact: `proper error message` is not deterministic without these values.
- What are the loader and shimmer terminal rules for success, empty response, partial failure, timeout, cancellation, navigation, and component unmount? QA impact: an indefinite disabled state can create a second outage.
- What exact reason schema and count reconciliation are required for skipped files? QA impact: the report cannot be asserted from a count alone when individual failures are hidden.
- Which DITA and non-DITA asset subtypes, document states, tag namespaces, permissions, and mixed selections are mandatory? QA impact: `all types` is broader than an executable fixture matrix.
- Does the accepted visible-file scope include only the current page, all filtered pages, or the complete server-side result set? QA impact: each interpretation changes the `allAssets=true` oracle.
- Is the GUIDES-29778 filter-reset issue accepted as a 5.0.1 limitation, fixed later, or a blocker for the target build? QA impact: it changes hotfix regression and release-sign-off expectations.
- If performance sign-off is required, what controlled dataset, warm/cold cache state, repetitions, percentile, maximum API/UI duration, concurrency, CPU, memory, and pod-stability ceilings are approved? Until answered, no Confirmed performance AC or principal-QA pass/fail verdict is valid.

### Regression Areas

- Select all versus selective files, current page versus all filtered pages, pagination, sorting, refresh, empty results, and stale selection.
- Common/no-common/mixed tags, Custom/OOTB tags, add/remove tags, document-state updates, permissions, locked assets, and partial skips.
- DITA topics, maps, DITAVAL, images, multimedia, documents, and any approved non-DITA types.
- Manage and Fix Link loader, disabled/enabled states, double-click, Enter key, retry, timeout, server error, navigation away, and dialog close.
- Filters-panel shimmer, retained filters, Broken Links filter reset, and visible-file scope after response.
- API query correctness for `allAssets=true`, UUID-to-path conversion, null-path prevention, exact common-tag response, and absence of full-repository scans.
- Cloud/on-premise parity, upgrade from affected 2502/5.0 builds, hotfix 5.0.1.2 boundaries, localization of changed error messages, and API/UI automation coverage.

## Product-Fix Reference: GUIDES-25769 Author-View Image Move Data Loss

Use this example when a closed Jira has no accepted UAC but does contain explicit implementation and build-verification chronology. The history is valuable for regression discovery, but it must not be promoted into Confirmed acceptance criteria or an inferred root cause.

### Evidence Boundary

- Jira marks the acceptance field as `UAC Not Required`. No Confirmed AC is justified by GUIDES-25769.
- The observed defect is narrow and severe: moving an existing image to another location inside the same topic in Author View breaks the image, and Source view no longer contains the image reference, causing data loss.
- A development comment explicitly says the issue was fixed in develop and cherry-picked for a hotfix, and links `AdobeStarling/xmleditor/pull/5088`. The linked diff was not inspected for this reference, so it proves a discoverable implementation link, not changed symbols or root cause.
- Jira records successful checks on `5.0.207`, `4.6.0.164`, and hotfix `4.6.4`. Preserve these as exact validation boundaries; do not generalize them to every 5.0 or 4.6 build.
- No explicit RCA is present. The missing source reference is a symptom and oracle, not proof of why the code removed it.
- The ticket carries both `Automated` and `Won't_Automate`. This is an unresolved automation-evidence conflict until the linked test or current suite is inspected.
- The attached recording was not downloaded or analyzed for this reference. Do not claim cursor position, DOM state, exact drag gesture, or visual timing from the attachment.

### Trust Classification

- Set `resolution_mechanism=product_fix` and `historical_outcome=implemented_fix` because the develop fix and hotfix cherry-pick are explicit.
- Set `qa_oracle_source=jira_comment_version_validation` for the exact version and hotfix validation comments.
- Set `behavior_contract_source=missing`, `behavior_contract_complete=false`, and `root_cause_source=missing` because Jira supplies neither accepted UAC nor RCA.
- Keep `learning_confidence=caution`, `is_verified_fix=false`, and reuse mode `risk_signal_only`. The issue may justify regression coverage and open questions, but it cannot independently define current expected behavior.

### Normalized Proposed ACs

- AC-01 [Proposed]: (Reference preservation) Given an existing image in a topic has a known source reference | When the author moves that image to another valid location in the same topic in Author View | Then the image remains rendered and Source view contains exactly one image element with the same reference value.
- AC-02 [Proposed]: (Persistence) Given the image was moved successfully | When the author saves, switches between Author and Source views, and reopens the topic | Then the moved image remains at the saved location and its reference and content are not deleted, replaced, or duplicated.
- AC-03 [Proposed]: (Failure safety) Given the requested destination is unsupported or the move cannot complete | When the editor rejects or cancels the operation | Then the original image and its source reference remain unchanged and no partial content loss is persisted.

### Required Open Questions Before Automation Handoff

- Does the fix apply to the old editor, new editor, CKEditor, Markup Editor, or a specific editor/build combination? QA impact: the Jira says Author View but does not define the editor matrix.
- Which reference forms are supported and must remain byte-equivalent: repository GUID, DAM path, relative path, `keyref`, or `conref`? QA impact: `same reference` is not executable until the accepted forms are named.
- Which source and destination containers are valid for moving an image, including paragraph, figure, list item, table cell, inline placement, and adjacent block boundaries? QA impact: a single happy-path destination cannot prove structural safety.
- Is the operation a move only, or are copy, cut/paste, keyboard movement, undo, and redo part of the same contract? QA impact: these paths can use different editor transactions.
- What is the expected behavior for unsaved topics, locked/read-only topics, concurrent edits, failed save, and browser refresh? QA impact: data-loss recovery and persistence cannot be signed off without state boundaries.
- Why do the Jira labels contain both `Automated` and `Won't_Automate`, and which repository/test is authoritative? QA impact: automation coverage must remain `Unverified` until direct evidence resolves the conflict.
- Does related GUIDES-19460 share the same editor transaction or only a similar drag/drop symptom? QA impact: it must be inspected before being treated as a same-mechanism Jira.

### Regression Areas

- Internal image reorder versus repository-panel insertion, toolbar insertion, copy/paste, cut/paste, and drag between topics.
- Author/Source parity before save, after save, after reopen, after check-in/version creation, and after browser refresh.
- Preservation of `href`, `alt`, `outputclass`, placement, dimensions/scaling, key/conref state, and adjacent inline or block content.
- Multiple images, repeated moves, first/last child positions, empty destinations, lists, tables, figures, and nested structures.
- Undo/redo, cancel, invalid drop targets, failed persistence, locked/read-only state, and prevention of deletion, duplication, broken rendering, or a newly minted reference.
- Exact fixed-build checks on `5.0.207`, `4.6.0.164`, and hotfix `4.6.4`, plus explicit validation on the current target build rather than inferred release-wide coverage.

## Accepted Comment-Scope Reference: GUIDES-23526 Folder-Profile Condition Preservation

Use this example when Jira's native acceptance field is empty but an accepted-UAC label and a later explicit scope comment establish the sign-off contract. The ticket history contains changing implementation proposals, so chronology and source provenance are mandatory.

### Evidence And Chronology Boundary

- Jira is Closed/Fixed, carries `UAC_Done`, affects 4.6, fixes 2502/4.6.3, and is associated with KONE and Authoring.
- The defect is that saving conditions through Folder Profile can flatten existing condition groups. A later observed variant also resets an edited condition's color to yellow.
- An early comment proposed that Folder Profile would not show groups while saving would preserve them. A later discussion considered displaying/editing group data because Folder Profile saves the complete condition object. Neither intermediate proposal overrides the final scoped comment.
- The final explicit scope comment limits the ticket to adding genuinely new conditions without altering existing conditions. It directs edits of existing conditions to XML Editor.
- The existing-condition Folder Profile defect—group removal and yellow color reset—is explicitly beyond this ticket and belongs to a separate enhancement.
- Engineering also stated that a stale Folder Profile page must be refreshed before editing and that reusing the same key/value is an edit because JSON keys are unique. These are implementation/usage notes, not automatically accepted product defaults.
- QA history records checks on UUID and non-UUID variants, Cloud and on-premise, plus hotfix builds. Preserve those exact validation boundaries as regression evidence; they do not broaden the accepted scope.
- The linked Starling PR and attached recordings/packages were not inspected for this reference. Do not infer changed symbols, package contents, exact UI controls, or root cause from their existence.

### Trust Classification

- Resolve the accepted behavior from the chronologically latest explicit final-scope comment only when the accepted-UAC label is present.
- Record `uac_source_authority=jira_accepted_uac` and `uac_source_origin=jira_comment_accepted_scope`.
- Keep `root_cause_source=missing` unless the PR/diff or a causal Jira statement is inspected. “Folder Profile saves the entire object” is mechanism context, not a confirmed RCA by itself.
- Keep the reusable tier at `supporting` unless explicit RCA and executed QA-oracle evidence also satisfy the verified-history rules.
- Never promote this comment path when Jira says `UAC Not Required`, when only a draft/pending scope exists, or when the accepted-UAC label is absent.

### Normalized Confirmed ACs

- AC-01 [Confirmed]: (New-condition preservation) Given the current Folder Profile state contains existing conditions with assigned groups and colors and the user adds a genuinely new key/value condition | When the Folder Profile change is saved | Then the new condition is persisted and every pre-existing condition retains its prior group and color without flattening, deletion, or reset.
- AC-02 [Confirmed]: (Persistence oracle) Given AC-01 completed successfully | When the condition data is reloaded and inspected through the authoritative stored configuration and XML Editor | Then the new condition is present exactly once and all prior group/color values match their pre-save values.
- AC-03 [Confirmed]: (Existing-condition boundary) Given an existing condition must be modified | When the user follows the accepted workflow | Then the edit is performed through XML Editor; editing that existing condition through Folder Profile is not a sign-off flow for this ticket.

### Required Open Questions

- Must Folder Profile visibly display existing group values, or is preservation without group editing the supported final UI? QA impact: this changes the UI oracle and whether blank group cells are expected.
- Is refreshing Folder Profile before adding a condition a product requirement, temporary workaround, or stale-state defect? QA impact: this changes setup and requires a separate stale-page scenario if refresh should not be mandatory.
- What exactly makes a condition “new”: unique attribute/value, unique JSON key, or another identifier? QA impact: duplicate-key behavior must be deterministic before automation can distinguish add from edit.
- Which current releases supersede the historical UUID/non-UUID, Cloud/on-premise, 2502, 4.6.3, and hotfix checks? QA impact: the execution matrix must target supported builds rather than infer release-wide coverage.
- Which PR or code path performs the merge/preservation? QA impact: without inspected implementation, concurrency, stale writes, ordering, and rollback remain targeted regression risks rather than confirmed RCA coverage.

### Regression Areas

- Add one and multiple genuinely new conditions while preserving several existing groups, colors, attributes, and values.
- Save, reload, browser refresh, XML Editor inspection, Folder Profile reopen, and stale-versus-refreshed page state.
- Duplicate key/value, blank group, special characters, ordering, concurrent edits, failed save, and rollback/no-partial-write behavior.
- Existing-condition editing in XML Editor versus the explicitly excluded Folder Profile edit path.
- UUID/non-UUID and Cloud/on-premise parity on the exact supported target builds; retain the historical hotfix matrix only as evidence.
- Import/export or configuration serialization that reads or writes the same condition object, ensuring unrelated groups and colors remain byte-equivalent where ordering is not semantically significant.

## How To Reuse This Pattern

- Put Jira’s UAC/sign-off conditions under `Acceptance Criteria`; treat them as the primary acceptance contract, not optional background.
- Let UAC drive `Expected Behaviour`, `Test Scenarios`, `Regression Areas`, and `Open Questions` before adding PR/RAG/Figma/repo-derived coverage.
- Use UAC scope and out-of-scope to avoid testing known non-goals as failures.
- Use UAC integration notes to decide what nearby workflows can break and must be listed under `Regression Areas`.
- Turn UAC setup details into executable QA conditions: test data, role, config, platform, environment, feature flag, version, and upgrade/source-target matrix must appear in scenarios or open questions.
- For API-focused UAC, always preserve exact endpoint names, parameter names, encoding/list-splitting rules, response fields, status/error behaviour, batch isolation, and log expectations.
- For future reference additions, prefer one high-quality UAC per feature family over many repetitive examples; split into domain-specific reference files once a family becomes large.
- Put cloud/on-premise parity, status, cancel/abort/resume, versioning, and configuration rules under `Expected Behaviour`.
- For review-functionality tickets, put impacted pages, no feature flag, doc impact, automation impact, and no-regression expectations under `Scope From Git`, `Test Scenarios`, and `Regression Areas` as applicable.
- For live filter tickets, always test typed input, pasted input, no-match empty state, clearing input, case-insensitive matching, stale results, and no-extra-action behaviour.
- For DITA table whitespace tickets, always test CALS table, `simpletable`, `reltable`, body/header cells, inline-tag boundaries, NBSP, regular-space collapse, block-child trimming, text-forbidden tags, and structural indentation leakage.
- For asset-status path parsing tickets, always test comma literals in `paths` and `excludedPaths`, folders, file names, `.ditamap`, multiple paths, mixed comma/non-comma batches, folder expansion, state mapping, duplicate paths, invalid relative paths, not-found paths, consecutive commas, spaces, special characters, and trailing commas.
- For Schematron validation tickets, always separate empty no-rule files from malformed/broken `.sch` files, verify save is not blocked, verify no UI message is introduced for empty files, keep real rule violations intact, and ask whether the fix is endpoint-side, editor-side, on-prem, Cloud, or all of them.
- For Schematron role-severity tickets, always test `<sch:assert>` and `<sch:report>`, fixed severities `fatal/error/warn/info`, accepted aliases `warning/information`, case-sensitive matching, unsupported-role fallback, missing-role backward compatibility, Fatal/Error save blocking, Warn/Info non-blocking, visual design parity, filtering/tooltips, and many-message performance.
- For Native PDF Print tab tickets, always test UI section order, removed controls, master/individual toggle sync, empty-field semantics, page box custom behavior, Color Space/Convert Colors/Rendering Intent visibility, ICC predefined/Other/None flows, generated `mergedHTML.json`, rendered PDF output, PDFReactor version compatibility, upgrade mapping, and preset cloning.
- For Old AEM Site publishing tickets with `ditavalref`, `keydef`, `conkeyref`, or resource-only behavior, always verify keydef pages are not generated, `conkeyref` resolves from key definitions, resource-only `xref` does not resolve as a normal page, normal topicrefs still publish, and known DITA-OT static-title behavior stays out of scope unless Jira says otherwise.
- For UI config JSON upgrade tickets, always separate upgraded-instance retained values from fresh-install defaults; verify custom CSS, custom `ui-config.json` components, shortcut keys, custom DITA attributes/elements, default templates, snippets, labels, Show Tags, Display Attributes, XML Comments, and Quick Insert Menu.
- For DB/Splunk logging tickets, always separate noisy JCR/on-prem DB warning/info logs from valid Cloud DB errors, verify exact unwanted logger strings are absent, preserve actionable error logging, test authoring and reference add/update regressions, capture Splunk query evidence, and keep automation as a gap until Splunk-query setup exists.
- For key-resolution report tickets, always test root map, key map, nested-map scope, valid versus missing keys, `keyref` versus `conkeyref` link types, correct linked file, post-processing/index refresh, create/rename/delete updates, no false positives, `Used In` title/path accuracy, Topic/Map file type, CSV/Excel export parity, and existing cross-link/reusable-content regressions.
- For Native AEM Site baseline-metadata tickets, always separate selected-baseline values from current working-copy values; cover `metadatalist` allowlisting, custom metadata, static/dynamic baselines, incremental publishing, Copy To, content/metadata version consistency, map-to-topic fallback precedence, and old/new baseline regeneration while preserving the ticket's explicit Old AEM Site, chunking, and multimedia exclusions.
- For baseline-aware Web Editor preview tickets, separate map from topic preview and static from dynamic baselines; cover selected-version rendering, filter-panel controls, Show diff visibility, editor parity, mode-switch retention, loader lifecycle, conditions, direct/indirect references, keys, selected-baseline deletion, version-purge protection, working-copy refresh behavior, and measurable large-map performance without promoting revert, metadata editing, Reports, or linked defects into scope.
- For Native PDF map-title inline-content tickets, separate map, project, and topic title scope; distinguish direct map-title `conref`/`conkeyref` exclusions from supported nested `<ph>`/`<keyword>` `keyref`, `conref`, and `conkeyref` paths; cover `<tm>`, inline emphasis, text decoration, `<image>`, `ditavalref`, conditional presets, DITA-OT enabled/disabled behavior, and text-only metadata titles; keep topic-title and unsupported video/object content outside scope, and require an explicit result for each DITA-OT state before creating Confirmed ACs.
- For GUID/UUID reference-insertion tickets, validate repository drag/drop and toolbar browse independently by inspecting source XML; require a GUID-backed `topicref/@href` and the accepted default `scope`, preserve the reference when another user moves the target before the map is saved, retain the target's original GUID without minting a replacement, test every stated UUID-property state, and run the same matrix in CKEditor and MarkupEditor; keep explicitly rejected external-scope path conversion outside sign-off and reconcile any editor-parity range that still includes an excluded UAC point.
- For translation v1/v2 first-run tickets, require the exact config name and default plus enabled/disabled outcomes; separate first translation from later buffer-copy runs; cover source-copy replacement after approval, translated-reference integrity, language-folder versus global assets, every named reference type, language-code GUID rules, mixed in-sync/missing-copy languages, machine/human/XLIFF/multilingual/baseline/API matrices, and related-asset no-copy/no-link behavior in both v1 and v2 while proving the config does not alter v1. Treat `work as is`, missing move/version outcomes, and pending linked-ticket scope as unresolved; when incident prose conflicts with final accepted UAC, keep the accepted UAC as sign-off authority and surface the conflict in `Open Questions` rather than merging both outcomes.
- For baseline-export asset-relocation tickets, test image and `topicref` moves from language to global, global back to language, and assets created globally without a language code then moved through both locations; require the exported baseline to resolve the current canonical asset path and the exact version created after the move without obsolete language-specific copies or missing-asset errors. Cover baselines/content created before upgrade and preserve translation asset retrieval, acceptance, rejection, XLIFF, human, and machine workflows. Treat `baseline export should work`, `no changes in normal workflows`, and upgrade checks without source/target builds or observable package/version outcomes as unresolved automation contracts.
- For on-premise release tickets, always ask upgrade-impact open questions about source/target versions, retained custom configs, changed defaults, manual post-upgrade steps, Cloud parity, and backward compatibility.
- Convert each UAC bullet into one practical `P0`, `P1`, or `P2` scenario with action and expected result.
- Keep file-type matrices compact; do not create a table unless the user explicitly asks.
- Add RAG-backed AEM configuration links only when `ask_dita_expert` confirms relevant upload restriction, duplicate detection, size, or versioning behaviour.

## Deterministic Reference: Authoring Viewport, Map Preview, CALS Deletion, and Large-File Safeguards

- Route an Author-view scroll-to-top issue to `authoring_viewport_stability` only when evidence names the editing canvas plus active caret/selection/element, reference insertion, or lost editing location. Cover typing, paste, link insert/update, picker cancel, repetition, active-element-relative reflow restoration, one correct reference, and unchanged surrounding content.
- Keep `map_preview_state` separate. Its contract covers selected topic, relative preview scroll, conditions/right-panel state, refresh, and Edit-return. Reject area-only historical overlap unless evidence identifies shared state restoration or editor-scroll implementation.
- For CALS multi-column deletion, use a 6-row by 5-column fixture and require a valid 6-row by 3-column result, no blank ghost column, preserved retained-cell order, and no orphan column/span metadata.
- Learn `GUIDES-35437` as `largeFileTagCount` configuration-driven working-as-designed behavior. Test below and at/above the effective parsed-tag threshold; never turn 411 cells into a hard-coded product defect or performance SLA.
- Exact screenshot-only records are not historical-UAC evidence. Index exact UAC only from live Jira or Jira CSV with a verified SHA-256 source hash.
