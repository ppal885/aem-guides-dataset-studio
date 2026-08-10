# UAC Reference Examples

Use this file when normalizing Jira UAC or when a user asks for a test plan that should read like a strong manual QA sign-off note.

## What Good UAC Looks Like

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

## Accepted User-Provided Reference: Native PDF ICC Profile Color Conversion

Use this reference when a Native PDF defect mixes two different failure classes: resolving an ICC profile from DAM or a remote URL, and actually applying that profile during CMYK conversion. The final UAC was supplied directly by the user, but the primary Jira key was not supplied. Only the exact profile-application contract is confirmed; source-specific resolution, picker behavior, failure handling, migration, and performance remain proposed until the ticket scope or implementation evidence confirms them.

**Accepted UAC (Verbatim)**

- CMYK ICC Profile color conversion will now be applied correctly

**Evidence Classification**

- The user-provided evidence describes a Native PDF Print preset configured with Color Space `CMYK`, an identifier name, and a custom ICC profile.
- `uac_source_origin=user_provided_final_uac`; the exact accepted behavior is ICC-backed CMYK color conversion, not every surrounding source-selection or preset-lifecycle behavior.
- The primary Jira key is still missing, so the accepted wording must be retained as user-provided evidence and must not be attributed to any related Jira.
- The reproducible DAM fixture is `Coated_Fogra39L_VIGC_300.icc`, stored at a path such as `/content/dam/archive/Coated_Fogra39L_VIGC_300.icc`.
- The evidence identifies two independent failure mechanisms: a DAM profile path causes publishing to fail, while a direct profile URL permits publishing but does not apply the expected CMYK profile.
- `GUIDES-25967`, `GUIDES-25017`, and `GUIDES-14741` are related-history candidates only. Their current status, accepted scope, workaround validity, fix version, and same-mechanism strength must be checked through indexed history and live Jira before they influence a plan.
- A workaround recorded on an older ticket is not an expected-behaviour oracle when current reproduction shows that it no longer works.

**Normalized Acceptance Criteria**

- AC-01 [Confirmed]: (Publishing) Given a Native PDF preset configured with Color Space CMYK, Convert Colors enabled, and a valid selected ICC profile, when Native PDF output is generated, then the selected ICC profile is applied during color conversion; PDF inspection must confirm the selected profile/output intent and conversion behavior, and the profiled output must not be equivalent to the no-profile control where the fixture is designed to expose a conversion difference.
- AC-02 [Proposed]: (DAM Profile Resolution) Given an accessible `.icc` or `.icm` asset selected from DAM and a Native PDF preset configured for CMYK conversion, when output is generated, then the publishing job completes without a profile-resolution error and uses the selected DAM asset rather than treating the JCR path as a local filesystem path or unsupported URL.
- AC-03 [Proposed]: (Remote Profile Resolution) Given a valid reachable ICC profile URL and the URL profile mode enabled, when Native PDF output is generated, then publishing completes and the fetched profile is passed to the renderer; a successful job without profile application does not satisfy this AC.
- AC-04 [Proposed]: (Configuration Consistency) Given a saved custom ICC configuration, when the preset is reopened and output is generated, then the UI state, persisted preset data, generated renderer input, publishing logs, and final PDF identify the same source mode, profile, identifier name, color space, and Convert Colors state.
- AC-05 [Proposed]: (DAM Selection) Given the custom profile file mode, when Browse Profile is used, then eligible `.icc` and `.icm` DAM assets can be selected and the selected repository path is retained after save and reopen.
- AC-06 [Proposed]: (Failure Handling) Given a missing, unreadable, unauthorized, malformed, unsupported, or unreachable profile source, when publishing is attempted, then the job fails deterministically with a useful profile-specific error and never reports success while silently producing an unprofiled PDF.
- AC-07 [Proposed]: (Preset Lifecycle) Given a working DAM-path or URL profile configuration, when the preset is edited, duplicated, cloned through a template, or migrated from an older preset shape, then the intended source mode and profile values are preserved without stale file/URL precedence.
- AC-08 [Proposed]: (Historical Regression) Given environments where the earlier Browse Profile or direct-URL behavior was previously fixed or documented, when the current flow is validated, then both source selection and actual profile application are retested; the result must not rely solely on the former `GUIDES-25967` workaround.

**Test Data And Oracles**

- Prepare one known-good ICC profile in DAM, the same profile from a reachable URL, one invalid ICC payload, one missing DAM path, one inaccessible DAM asset, one unreachable URL, and one URL returning a redirect or non-ICC response if redirects are supported.
- Prepare a CMYK-sensitive image or vector fixture whose expected conversion under `Coated_Fogra39L_VIGC_300.icc` is known, plus a no-profile control output generated from identical content.
- Verify the publishing job state and profile-specific logs first; a generic successful job is insufficient.
- Verify persisted preset properties and generated renderer configuration to prove that the selected source reached the publishing pipeline.
- Use an approved PDF preflight/inspection tool to verify output intent, embedded or referenced ICC identity, color space, and separation/conversion behavior. Visual comparison is supporting evidence only and must not be the sole proof that CMYK conversion occurred.
- Compare DAM-path and URL-mode outputs produced from the same fixture. Equivalent profile sources should produce equivalent profile metadata and materially equivalent color conversion within the approved comparison tolerance.

**Regression Areas To Carry Forward**

- DAM path resolution, repository permissions, asset rendition/original-binary access, spaces or encoded characters in paths, and `.icc` versus `.icm` filtering.
- URL validation, redirects, proxy/network access, timeout behavior, non-ICC content, and unreachable hosts.
- Output Identifier Name, Convert Colors, Rendering Intent, RGB/CMYK mismatch warning, and file-versus-URL precedence.
- Saved preset reopen, duplicate preset, template clone, upgrade/migration, and stale values left after switching source modes.
- Generated renderer input, PDFReactor version compatibility, publishing logs, output intent, color conversion, and no-profile control comparison.
- Related regressions from `GUIDES-25967`, `GUIDES-25017`, and `GUIDES-14741`, but only after live scope and outcome validation.

**Open Questions To Carry Forward**

- What is the primary Jira key, and is the text supplied here the final accepted UAC or only defect/reproduction evidence?
- Which DAM property or persisted preset field stores the selected profile, and should it hold a JCR path, asset identifier, binary URL, or resolved repository resource?
- Must remote profile URLs support redirects, authentication, proxies, caching, and offline reuse, and what timeout or retry contract applies?
- What exact error message and job status should appear for missing, unreadable, unauthorized, malformed, or unreachable profiles?
- Which PDFReactor and Guides versions are in scope, and is PDFReactor 11 expected to apply the profile or only remain backward compatible without failing?
- Which PDF inspection tool, expected output-intent identity, color-space assertions, and visual/numeric comparison tolerance are approved as the sign-off oracle?
- Is Browse Profile selection itself in the current ticket scope, or should `GUIDES-25017` remain a separate dependency/regression?
- Does profile download or conversion require a performance AC, and if so what publish-time, timeout, cache, memory, and concurrency thresholds must be met?

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

## Accepted Reference: GUIDES-52343 HTML Topic Title Selector Precedence

Use this example for HTML topic-creation defects where a template offers both a product-specific title container and the legacy top-level `<h1>` fallback. The accepted contract is selector precedence, not a general license to populate every heading in the template.

### Sanitized Evidence Boundary

- `uac_source_origin=jira_acceptance_field`; `accepted_uac_present=true`; customer, tenant, environment, attachment, and person data are intentionally omitted.
- Preserve the Jira source component independently. For test-plan retrieval, classify the mechanism under Authoring, HTML topic initialization, template selector resolution, and title fallback.
- Historical UAC can seed a proposed AC for a new ticket, but it is never current-ticket authority by itself.
- No performance AC is justified because the accepted UAC contains no workload, latency, concurrency, or resource contract.

### Accepted Source-Clause Inventory

- `UAC-01` - During HTML topic creation, the supplied title is populated at `/html/body/header[1][@data-rhwidget='TopicHeader']/h1[1][@data-rhwidget='TopicTitle']` when that exact product header/title structure exists.
- `UAC-02` - If that header title is not present, the title is populated at the legacy fallback `/html/body/h1[1]`.

### Fidelity Lessons

- Treat `UAC-01` and `UAC-02` as an ordered selector contract: exact `TopicHeader`/`TopicTitle` target first, legacy `/html/body/h1[1]` only as fallback.
- Do not invent simultaneous writes to both selectors, duplicate headings, or a broader descendant search.
- `Header title is not present` does not define whether the header node, nested `<h1>`, one `data-rhwidget` attribute, or all of them are missing. Keep those variants in `Open Questions` until implementation or accepted Jira evidence defines them.
- Existing non-empty title replacement, multiple matching headers, malformed templates, namespaces, and localization are not Confirmed by this UAC.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Basic) Given a new HTML topic template contains `/html/body/header[1][@data-rhwidget='TopicHeader']/h1[1][@data-rhwidget='TopicTitle']` | When the user creates the topic with a title | Then that exact `<h1>` contains the supplied title after creation, save, and reopen | Evidence: `UAC-01` from GUIDES-52343.
- AC-02 [Confirmed]: (Fallback) Given the exact `TopicHeader`/`TopicTitle` target is absent and `/html/body/h1[1]` exists | When the user creates the topic with a title | Then `/html/body/h1[1]` contains the supplied title after creation, save, and reopen | Evidence: `UAC-02` from GUIDES-52343.
- AC-03 [Proposed]: (Negative) Given both the exact custom target and legacy fallback exist | When the topic is created | Then only the approved precedence target is populated and no duplicate title is introduced | Evidence needed: inspected implementation or an accepted Jira clarification.

### Required Open Questions

- Which missing-node and missing-attribute combinations qualify as `header title is not present`?
- If both selectors exist, must the legacy `<h1>` remain empty, retain template text, or be removed?
- Should creation overwrite a non-empty title already present in the template?
- What is the expected error or fallback when neither selector exists or when more than one matching custom header exists?
- Which HTML topic/template types and old/new editor creation surfaces share this initialization path?

### Regression Areas

- HTML topic creation from default and custom templates.
- Exact `data-rhwidget='TopicHeader'` and `data-rhwidget='TopicTitle'` matching.
- Legacy `/html/body/h1[1]` behavior.
- Save, reopen, source/author view parity, and duplicate-title prevention.
- Templates with missing nodes, missing attributes, multiple headers, and pre-populated title text.
- Existing DITA topic creation must not inherit HTML selector behavior.

## Accepted Reference: GUIDES-50143 Baseline Label Autocomplete Input Parity

Use this example for autocomplete defects where filtering is bound to keyboard events instead of the input value. The mechanism is event parity: typing, paste, clear, and repeated interactions must drive one deterministic filter path.

### Sanitized Evidence Boundary

- `uac_source_origin=jira_acceptance_field`; `accepted_uac_present=true`; AVAYA tenant, environment, case, recording, and investigation identifiers are intentionally omitted.
- Classify the mechanism under Authoring, Baseline, label selector, autocomplete filtering, and input-event handling while preserving the imported Jira component separately.
- `Real time` is a functional responsiveness phrase, not an approved numeric performance SLA.
- Historical UAC can support regression discovery for a new ticket but cannot replace current Jira, implementation, or design evidence.

### Accepted Source-Clause Inventory

- `UAC-01` - Typing the first letter filters the list to items containing or starting with that value.
- `UAC-02` - Typing additional characters further narrows the filtered results in real time.
- `UAC-03` - Pasting a complete word triggers the same filtering logic as typing it.
- `UAC-04` - A no-match value produces an empty dropdown; it must not display the full list.
- `UAC-05` - Clearing the field restores the full list.
- `UAC-06` - Filtering is case-insensitive unless a newer accepted contract specifies otherwise.
- `UAC-07` - Typing or pasting updates the list without an extra click, key-down, blur, focus change, or other user action.

### Fidelity Lessons

- Preserve typing/paste equivalence; do not write separate expected option sets for the same value.
- The phrase `containing/starting with` is ambiguous. A discriminating fixture cannot be automated until product, implementation, or design evidence selects contains, prefix, or a documented hybrid rule.
- No-match and clear are distinct state transitions. Do not allow no-match to fall back to the unfiltered list.
- The reported repeat-paste sequence is a high-value regression case, but do not invent debounce duration or network timing thresholds.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Basic) Given the Baseline label dropdown is open with a known label fixture | When the user types one character and then additional characters | Then the visible options are recomputed after every input value change and narrow according to the approved matching rule | Evidence: `UAC-01` and `UAC-02` from GUIDES-50143.
- AC-02 [Confirmed]: (Integration) Given the same label value and initial dropdown state | When the user enters the value once by typing and once by paste | Then both interactions produce the same filtered option set without another action | Evidence: `UAC-03` and `UAC-07` from GUIDES-50143.
- AC-03 [Confirmed]: (Negative) Given an input value matches no label | When filtering completes | Then the dropdown is empty or shows the approved empty state and does not show the full list | Evidence: `UAC-04` from GUIDES-50143.
- AC-04 [Confirmed]: (State) Given the dropdown is filtered | When the user clears the complete input value | Then the full label list is restored without an extra action | Evidence: `UAC-05` and `UAC-07` from GUIDES-50143.
- AC-05 [Confirmed]: (Compatibility) Given labels differ only by input letter case | When each case variant is typed or pasted | Then filtering returns the same option set unless a newer accepted contract explicitly defines case-sensitive behavior | Evidence: `UAC-06` from GUIDES-50143.
- AC-06 [Proposed]: (Regression) Given the user has pasted, cleared, blurred/reopened, and pasted again | When the second and later input events occur | Then every interaction recomputes the list with no stale result | Evidence: issue reproduction plus historical defect context; confirm against current implementation before promoting.

### Required Open Questions

- Is the approved matching rule prefix, substring, token, fuzzy, or another documented algorithm?
- What ordering rule applies after filtering, and must the current selection remain visible when it no longer matches?
- Does clearing mean backspace, select-all-delete, clear icon, programmatic reset, and dialog reopen?
- Are keyboard navigation, screen-reader announcements, loading states, and remote pagination part of this component's contract?
- Is the behavior required in Create Baseline, Edit Baseline, static/dynamic baseline flows, and both old/new editor surfaces?

### Regression Areas

- `input`, `paste`, change, keyboard, clear, focus, blur, reopen, and repeated-paste event paths.
- Prefix-versus-contains matching once clarified, case normalization, no-match state, and full-list restoration.
- Stale results during rapid value replacement or delayed responses.
- Keyboard selection, mouse selection, Escape, Enter, focus management, and ARIA option state.
- Create/Edit Baseline parity and existing selected-label retention.

## Accepted Reference: GUIDES-49144 Table-Cell Inline Whitespace Preservation

Use this example for editor parser/serializer regressions where user-authored whitespace around inline DITA elements is confused with structural indentation. The accepted oracle is paragraph parity plus explicit exceptions, not blanket whitespace preservation.

### Sanitized Evidence Boundary

- `uac_source_origin=jira_acceptance_field`; `accepted_uac_present=true`; IBM tenant, environment, case, attachment, and investigation identifiers are intentionally omitted.
- Preserve source component `Editor`; classify the mechanism under mixed-content parsing, table-cell whitespace, inline DITA, serialization, and round-trip integrity.
- A Jira engineering comment attributes the regression to the custom table-cell parser omitting the preserve-whitespace flag. Store this only as `root_cause_source=jira_comment_engineering_rca`; it is historical implementation evidence, not an OASIS DITA rule.
- The issue description reports HTML/PDF impact, but the accepted UAC does not define an output matrix. Keep publishing-output checks proposed unless current Jira or inspected code explicitly includes them.
- No performance AC is justified by the accepted UAC.

### Accepted Source-Clause Inventory

- `UAC-01` - Preserve a user-authored space before an inline tag in CALS `table`, `simpletable`, and `reltable`, in both body and header cells.
- `UAC-02` - Cell behavior matches `<p>` for leading, trailing, and inter-element spaces around inline tags.
- `UAC-03` - Cover leading, trailing, inter-element, before/after inline, before newline, before a block child, and structural indentation between `row`/`entry`; the block-child boundary is intentionally trimmed.
- `UAC-04` - Multiple consecutive regular spaces collapse to one; NBSP never collapses or drops, including alternating regular-space/NBSP runs.
- `UAC-05` - Do not add unnecessary preservation to text-forbidden tags.
- `UAC-06` - Pretty-printed structural indentation must not leak into cell text.

### Fidelity Lessons

- Distinguish authored mixed-content whitespace from source-formatting indentation. Preserving all whitespace would violate `UAC-03` and `UAC-06`.
- Do not generalize CALS `entry` behavior to every XML node without DITA grammar or implementation evidence.
- `Text-forbidden tags` is not an executable matrix until the exact element list is supplied; keep that source clause accepted but automation handoff blocked for that sub-case.
- NBSP is a distinct character oracle. Do not normalize it into a regular space in fixtures, logs, or expected output.
- GUIDES-28188 is a candidate same-mechanism regression reference; validate mechanism and version boundaries before reusing its oracle.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Matrix) Given CALS `table`, `simpletable`, and `reltable` fixtures with body and header cells containing text followed by an inline DITA element | When each topic is opened, saved, and reopened | Then the authored space before the inline element remains present and visible | Evidence: `UAC-01` from GUIDES-49144.
- AC-02 [Confirmed]: (Parity) Given equivalent mixed-content fixtures in `<p>` and each supported table cell | When leading, trailing, and inter-element spaces surround inline tags | Then cell normalization matches the approved paragraph behavior | Evidence: `UAC-02` from GUIDES-49144.
- AC-03 [Confirmed]: (Boundary) Given fixtures for leading, trailing, inter-element, before/after inline, before newline, before block child, and structural `row`/`entry` indentation | When the editor parses and serializes them | Then authored inline-boundary whitespace is preserved, the approved block-child boundary is trimmed, and structural indentation is not introduced as cell text | Evidence: `UAC-03` and `UAC-06` from GUIDES-49144.
- AC-04 [Confirmed]: (Normalization) Given runs of multiple regular spaces | When the content is round-tripped | Then each run collapses to one regular space according to the accepted paragraph rule | Evidence: `UAC-04` from GUIDES-49144.
- AC-05 [Confirmed]: (Character Integrity) Given one or more NBSP characters, including alternating regular-space/NBSP runs | When the content is round-tripped | Then every NBSP remains present and is not collapsed or dropped | Evidence: `UAC-04` from GUIDES-49144.
- AC-06 [Proposed]: (Schema Boundary) Given the approved list of text-forbidden elements | When those elements occur in table structures | Then the parser does not introduce preserved text whitespace where text is forbidden | Evidence needed: exact element matrix for `UAC-05`.
- AC-07 [Proposed]: (Publishing Regression) Given a validated author/source round-trip fixture | When supported HTML and PDF outputs are generated | Then visible word boundaries match the saved source without concatenation | Evidence needed: current-ticket output scope or inspected publishing implementation.

### Required Open Questions

- Which exact inline elements form the minimum matrix: `xref`, `keyword`, `uicontrol`, `wintitle`, and which additional mixed-content elements?
- Which exact DITA elements are meant by `text-forbidden tags`?
- Does paragraph parity refer to source XML, Author view, Preview, persisted DAM content, or all of them?
- Which block children intentionally trim preceding whitespace, and is trailing whitespace after a block child governed by the same rule?
- Are HTML5, Native PDF, DITA-OT PDF, and AEM Sites outputs in accepted scope or regression-only scope?
- Which old/new editor and upgrade paths define the regression boundary?

### Regression Areas

- CALS body/header `entry`, `simpletable` cells, and `reltable` cells.
- Inline mixed-content parsing and serialization around `xref`, `keyword`, `uicontrol`, `wintitle`, and the approved element matrix.
- Author/Source/Preview save-reopen parity and undo/redo around whitespace edits.
- Regular-space collapse, NBSP preservation, mixed runs, newline boundaries, and block-child boundaries.
- Pretty-printed XML indentation and text-forbidden structural elements.
- Candidate regression GUIDES-28188 after mechanism verification.
- Publishing outputs only when current scope confirms them.

## Accepted Reference: GUIDES-48587 Alphanumeric User-Dictionary Spellcheck

Use this example for spell-check defects where dictionary matching and tokenization differ for alphabetic, numeric-boundary, and special-character terms. The accepted behavior is position-sensitive and must be tested in both editor generations without broadening it into an unspecified punctuation policy.

### Sanitized Evidence Boundary

- `uac_source_origin=jira_acceptance_field`; `accepted_uac_present=true`; CIENA tenant, IMS Org, program/environment, case, attachment, person, and investigation identifiers are intentionally omitted.
- Classify the mechanism under Editor, spell check, user dictionary, tokenization, alphanumeric terms, and old/new editor parity while preserving the imported Jira component separately.
- The support statement that filtering `appears to drop tokens containing digits` is a candidate investigation hypothesis, not a verified RCA. Record `root_cause_source=missing` until code or an explicit engineering conclusion confirms it.
- No performance AC is justified because the accepted UAC contains no workload, latency, throughput, concurrency, or resource contract.
- Historical UAC may seed regression coverage for a new ticket, but it is never current-ticket authority by itself.

### Accepted Source-Clause Inventory

- `UAC-01` - The accepted spell-check behavior applies to both the old editor and the new editor.
- `UAC-02` - A string with numeric characters at its starting or ending boundary must not be shown as misspelled when that exact string is present in the user dictionary.
- `UAC-03` - The existing behavior for special characters does not change; applicable special-character strings continue to be shown as misspelled.
- `UAC-04` - If a special character occurs in the middle of a word, the spell checker ignores that word.

### Fidelity Lessons

- Do not reduce `UAC-02` to trailing digits only because the supplied incident examples are suffix-number acronyms. The accepted wording also names the starting boundary.
- Do not infer behavior for digits in the middle, numeric-only tokens, decimals, version strings, or multiple numeric runs; those positions are not defined by the accepted UAC.
- `Special character` has no approved character set. Hyphen, underscore, slash, period, apostrophe, colon, symbols, and Unicode punctuation cannot be treated as equivalent without a fixture matrix.
- `Ignore the word` must not be silently rewritten as dictionary acceptance. It describes a tokenizer/spell-check bypass whose exact UI oracle requires clarification.
- Dictionary deployment, cache refresh, editor restart, save/reopen, language, and case-sensitivity behavior come from incident context, not the four accepted clauses; keep them proposed until current evidence confirms them.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Compatibility) Given the same user dictionary is active in the old editor and new editor | When the same accepted spell-check fixture is evaluated in each editor | Then both editors return the same misspelled or ignored state for every accepted clause | Evidence: `UAC-01` from GUIDES-48587.
- AC-02 [Confirmed]: (Boundary) Given an exact user-dictionary entry containing a numeric character at the accepted starting or ending boundary | When spell check evaluates the matching token in either editor | Then the token is not shown as misspelled | Evidence: `UAC-02` from GUIDES-48587.
- AC-03 [Confirmed]: (Negative) Given a fixture from the approved special-character set that is covered by the unchanged misspelled rule | When spell check evaluates it in either editor | Then it continues to be shown as misspelled | Evidence: `UAC-03` from GUIDES-48587; automation remains blocked until the character/position matrix is approved.
- AC-04 [Confirmed]: (Tokenizer Boundary) Given a fixture from the approved special-character set with that character in the middle of the word | When spell check evaluates it in either editor | Then the word is ignored according to the approved visible/UI oracle | Evidence: `UAC-04` from GUIDES-48587; automation remains blocked until `ignored` and the character set are defined.
- AC-05 [Proposed]: (Persistence) Given an alphanumeric term is added to `/apps/fmdita/config/user_dictionary.txt` and the supported dictionary-refresh action completes | When the topic is saved, reopened, and the editor is restarted | Then the accepted non-misspelled result persists | Evidence needed: current implementation or accepted Jira scope for refresh/cache lifecycle.

### Required Open Questions

- Does `starting and ending` mean either boundary independently, both boundaries in one token, or both categories as separate fixtures?
- What is the expected behavior for digits in the middle, multiple digit runs, numeric-only values, dotted versions, and decimal-like tokens?
- Which exact ASCII and Unicode characters are `special characters`, and which positions are covered by the unchanged misspelled rule?
- What exact observable defines `ignored`: no underline, no correction menu, no dictionary lookup, no telemetry entry, or all of these?
- Must a middle-special-character word be ignored whether or not it exists in the user dictionary?
- Is dictionary matching case-sensitive, locale-specific, normalized for Unicode, or based on exact code points?
- What supported deployment/reload event makes a changed user dictionary active in old and new editors?

### Regression Areas

- Old editor and new editor spell-check parity.
- Existing alphabetic user-dictionary terms and unknown alphabetic words.
- Numeric prefix, numeric suffix, both-boundary, middle-digit, multiple-digit, and numeric-only tokenization once clarified.
- Special characters at start, middle, and end using the approved ASCII/Unicode matrix.
- User-dictionary exact matching, case handling, language handling, load/reload, cache invalidation, and editor restart.
- Underline state, correction suggestions, right-click behavior, save/reopen persistence, and repeated spell-check runs.
- Candidate implementation flow `SpellCheckFeature` to `AEMSpellChecker` only after inspected code confirms it is the active path.

## Accepted Reference: GUIDES-48450 DITA Element Predicate Request Serialization

Use this example for Assets Admin Search Rail defects where a custom predicate renders correctly but omits the selected value from the QueryBuilder request. The accepted contract spans request serialization, server submission, result filtering, applied-filter chip lifecycle, and search-text tokenization; a UI-only assertion or backend-only assertion is insufficient.

### Sanitized Evidence Boundary

- `uac_source_origin=jira_acceptance_field_and_user_transcription`; `accepted_uac_present=true`; customer, IMS Org, program/environment, author URLs, case, Slack, person, and attachment identifiers are intentionally omitted.
- Preserve source Jira component `Asset Management`; classify the mechanism under Assets Admin Search Rail, DITA Element Predicate, QueryBuilder serialization, applied filters, and search tokenization.
- The issue evidence shows that DITA metadata extraction and indexing work, and that a manually completed QueryBuilder request filters correctly. Guides Editor Repository search is a control, not proof that the Assets Admin predicate is fixed.
- The supplied investigation does not contain an inspected implementation or explicit engineering RCA. Record `root_cause_source=missing`; do not infer the faulty UI class, event handler, or serializer.
- Status, resolution, fix version, branch, and commit facts shown in a screenshot are mutable and must be validated through live Jira/Git before use in a current plan.
- No performance AC is justified by the accepted UAC because it defines no workload, latency, throughput, concurrency, or resource threshold.

### Accepted Source-Clause Inventory

- `UAC-01` - Applying the DITA Element filter sends the actual value selected by the user instead of an empty value.
- `UAC-02` - Applying the filter sends a proper search request to the server with all DITA Element filter details.
- `UAC-03` - The results list updates to contain only items matching the DITA Element filter.
- `UAC-04` - An applied-filter chip appears and visibly represents the active DITA Element filter.
- `UAC-05` - Removing the applied-filter chip clears the DITA Element filter and refreshes the results to the unfiltered state.
- `UAC-06` - Search text is tokenized first and the form is submitted again so the returned results match the text entered by the user.

### Fidelity Lessons

- Preserve the exact request contract. For an Element `title` and Value `difference`, the request evidence expects `211_group.1_property=jcr:content/ditameta/title`, `211_group.1_property.operation=like`, and `211_group.1_property.value=difference`; a request containing only the first two parameters is an empty skeleton and fails `UAC-01` and `UAC-02`.
- Do not collapse request correctness, filtered results, and filter-chip state into one assertion. Each is independently observable and each can regress while the others appear correct.
- Do not invent tokenization semantics from `UAC-06`. Word splitting, quoting, punctuation, case normalization, wildcard insertion, debounce, and submit timing remain unresolved until current implementation or product scope defines them.
- Do not promote the working Guides Editor Repository search into accepted scope. It is a control proving metadata/index readiness and a regression signal only.
- Cloud and on-prem reproduction broadens the validation matrix, but it does not establish a Confirmed parity AC unless current Jira scope explicitly requires both.
- Do not treat a populated chip as proof that the server received `property.value`; inspect the actual network request and returned result set.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Integration) Given DITA metadata extraction and indexing are configured and the user selects Element `title` with Value `difference` in the Assets Admin DITA Element filter | When the user applies the filter | Then the submitted QueryBuilder predicate includes the mapped `property`, its `property.operation`, and the non-empty selected `property.value` rather than an empty skeleton | Evidence: `UAC-01` and `UAC-02` from GUIDES-48450.
- AC-02 [Confirmed]: (Basic) Given indexed DITA assets where only a known subset matches the selected element/value pair | When the DITA Element filter request completes | Then the results list contains only the matching assets and excludes known nonmatching controls | Evidence: `UAC-03` from GUIDES-48450.
- AC-03 [Confirmed]: (UI State) Given a DITA Element filter is successfully applied | When the filtered results are shown | Then an applied-filter chip is visible and represents the active DITA Element filter | Evidence: `UAC-04` from GUIDES-48450.
- AC-04 [Confirmed]: (Reset) Given a DITA Element filter chip is active and the results are filtered | When the user removes that chip | Then the predicate value is removed from the next request and the results refresh to the corresponding unfiltered state | Evidence: `UAC-05` from GUIDES-48450.
- AC-05 [Confirmed]: (Tokenization) Given the user enters search text for the DITA Element predicate | When the supported text-processing event completes | Then the text is tokenized before submission, the form submits again with the processed value, and the returned results match the entered text under the approved tokenization rule | Evidence: `UAC-06` from GUIDES-48450; automation requires the exact tokenization rule.
- AC-06 [Proposed]: (Composition) Given DITA Element, full-text, path, file-type, and other Assets filters are active together | When the combined search is submitted and individual chips are removed | Then each predicate retains its own value and the approved AND/OR semantics without clearing unrelated filters | Evidence needed: accepted combined-filter contract or inspected implementation.
- AC-07 [Proposed]: (Regression Control) Given the same indexed DITA fixture | When Guides Editor Repository search and Assets Admin Search Rail are exercised independently | Then the existing Repository search behavior remains unchanged while the Assets Admin predicate satisfies AC-01 through AC-05 | Evidence needed: current-ticket regression scope.

### Required Open Questions

- What exact element-name-to-`jcr:content/ditameta/*` mapping is supported, including namespaced, specialized, mixed-case, invalid, and unknown element names?
- What are the approved `property.operation`, wildcard, escaping, URL-encoding, case-sensitivity, and multi-value rules?
- What does `tokenized` mean for multiple words, quoted phrases, punctuation, Unicode, repeated spaces, pasted text, and empty tokens?
- Which event triggers the second submission, and what debounce, cancellation, stale-response, or duplicate-request behavior is expected?
- What exact label/value must the chip display, and must chip state survive browser back/forward, page refresh, saved search, or deep-link reuse?
- What is the empty-value and no-match behavior: block submission, omit the predicate, show zero results, or restore the unfiltered list?
- How does the DITA Element predicate combine with multiple DITA Element rows and other Assets filters?
- Are Cloud and on-prem both release-blocking scope, and which AEM/Guides versions define the compatibility matrix?

### Regression Areas

- Search Forms configuration, DITA metadata extraction, DAM index readiness, and element-to-property mapping.
- QueryBuilder group numbering, `property`, `property.operation`, `property.value`, URL encoding, empty values, and repeated predicates.
- Filter application, response/result replacement, pagination, sorting, no-match state, and known matching/nonmatching controls.
- Applied-filter chip creation, displayed label/value, removal, clear-all, browser navigation, and refresh behavior.
- Typing, paste, tokenization, resubmission, debounce, stale responses, and duplicate network requests.
- Composition with full-text, path, file type, tags, and multiple DITA Element filters once semantics are approved.
- Guides Editor Repository search as a non-regression control, not as a substitute for Assets Admin Search Rail validation.

## Accepted User-Provided Reference: Per-Topic Review Completion

Use this example for review-workflow enhancements that add reviewer-specific completion per topic without silently changing task-level completion. The accepted contract is binary per-topic state keyed by reviewer and current topic version, plus an explicit task-completion action; it is not a three-state workflow and it does not treat merely opening a topic as completion.

### Sanitized Evidence Boundary

- `uac_source_origin=user_provided_final_uac`; `accepted_uac_present=true`; `primary_jira_key=missing`. Do not invent or infer a Jira key until the current issue is supplied and validated.
- Customer, tenant, environment, case, investigation, attachment, and person identifiers are intentionally omitted. They are not required to preserve the reusable behavior contract.
- The final human-written UAC is sign-off authority. Earlier incident requests for `Not Started / In Progress / Done`, task auto-completion, notifications, and topic-status API payloads are proposal history only and are not Confirmed by this reference.
- A Figma node was supplied, but the connected Figma source required reauthentication during ingestion. Record `figma_source_status=degraded_reauthentication_required` and `figma_visual_contract_verified=false`; only the textual requirement to use the approved Figma progress-bar design is accepted, not colors, dimensions, spacing, animation, or responsive behavior.
- No inspected implementation, persistence schema, endpoint contract, or explicit engineering RCA was supplied. Record `root_cause_source=missing` and keep storage, concurrency, notification, and API-shape claims open.
- Incident workload observations such as 5-20 topics and estimated cycle-time impact are not performance SLAs. No Confirmed latency, throughput, concurrency, or resource AC is justified without measurable thresholds.

### Accepted Source-Clause Inventory

- `UAC-01` - Each topic has a `Mark topic as done` checkbox.
- `UAC-02` - There is no separate `Not Done` state; unchecked means not done.
- `UAC-03` - A reviewer manually checks or unchecks the checkbox, whose default state is unchecked.
- `UAC-04` - Completion is reviewer-specific; one reviewer's action does not change another reviewer's state.
- `UAC-05` - With the feature flag enabled, the task-level button is named `Complete review task`; with the flag disabled, existing `Mark as Done` behavior remains unchanged.
- `UAC-06` - A topic not assigned to the current reviewer shows a disabled, unchecked checkbox.
- `UAC-07` - When an author changes a topic version after completion, the completion state resets to unchecked.
- `UAC-08` - After reassignment, the new assignee sees their own completion state for the topic's current version; their prior completion of that same version remains checked regardless of the previous assignee.
- `UAC-09` - Completed topics show a green dot in the left panel; incomplete topics show no completion indicator.
- `UAC-10` - The header shows `Topics viewed` as `Completed/Assigned` with the approved Figma progress bar.
- `UAC-11` - The completed numerator counts topics marked done by the current reviewer for the current topic version.
- `UAC-12` - The assigned denominator counts review-enabled topics assigned to the reviewer, or all review-enabled topics when the review allows any reviewer to review any topic.
- `UAC-13` - `Topics viewed` does not track whether a topic has merely been opened; it tracks current-version completion.
- `UAC-14` - Per-topic completion is available in Preview and non-Preview edit/review modes.
- `UAC-15` - The backend validates that the acting user is a reviewer of the review before allowing a completion-state update, independent of client-side state.
- `UAC-16` - The checkbox, green dot, and progress UI are visible only to users who currently have access to the existing `Mark as Done` action; view-only authors and administrators do not see them.
- `UAC-17` - Any topic version change clears all previous completion status for that topic for every reviewer, and reverting to a previously completed version does not restore the prior checked state.
- `UAC-18` - Completion history is not retained across versions, and the whole capability is released behind a feature flag.

### Fidelity Lessons

- Preserve the binary state model. Do not generate `Not Started`, `In Progress`, or a separate `Not Done` state from the earlier customer proposal.
- Do not rename `Topics viewed` in generated criteria and do not interpret it literally. Its numerator is topics marked done for the current reviewer and current version, not topics opened, focused, scrolled, or commented on.
- Treat reviewer identity and current topic version as independent state dimensions. One reviewer's completion cannot leak to another, and any version transition invalidates every reviewer's prior completion for that topic.
- Do not resurrect completion when content returns to an older version. The accepted round trip is checked on v1.0, reset on v1.1, checked on v1.1, and still unchecked after reverting to v1.0.
- Reassignment does not copy the previous assignee's state. It resolves the newly assigned reviewer's own state for the current version, including a prior completion by that same reviewer.
- Keep task completion explicit. The final UAC names `Complete review task`; it does not authorize automatic task completion when the numerator reaches the denominator.
- Keep feature-flag-off behavior byte-for-behavior compatible with the existing `Mark as Done` flow. Do not expose partial new UI when the flag is disabled.
- UI visibility is not authorization. A hidden or disabled control does not satisfy `UAC-15`; the backend must reject an unauthorized mutation and preserve stored state.
- Do not promote email/AEM notifications, review-dashboard three-state status, or a topic-status API response into Confirmed ACs. Those appear only in earlier proposal text.
- Incident workload observations are not performance SLAs; keep performance thresholds as an open question unless current scope supplies measurable pass/fail values.

### Normalized Acceptance Criteria

- AC-01 [Confirmed]: (Basic) Given an assigned review-enabled topic has no completion recorded for the current reviewer and current version | When the reviewer opens the review in Preview or non-Preview mode | Then a `Mark topic as done` checkbox is visible and unchecked, and no separate `Not Done` state is displayed | Evidence: `UAC-01`, `UAC-02`, `UAC-03`, and `UAC-14`.
- AC-02 [Confirmed]: (State Change) Given the current reviewer can act on an assigned topic at its current version | When the reviewer checks and then unchecks `Mark topic as done` | Then only that reviewer's binary completion state for that topic version changes to checked and then unchecked | Evidence: `UAC-03` and `UAC-04`.
- AC-03 [Confirmed]: (Reviewer Isolation) Given two reviewers can review the same current topic version | When one reviewer changes their completion checkbox | Then the other reviewer's completion state and displayed checkbox remain unchanged | Evidence: `UAC-04`.
- AC-04 [Confirmed]: (Feature Flag) Given the feature flag is enabled | When an eligible reviewer opens the review | Then per-topic completion UI is available and the task-level action is labeled `Complete review task`; given the flag is disabled, the new capability is unavailable and existing `Mark as Done` behavior remains unchanged | Evidence: `UAC-05` and `UAC-18`.
- AC-05 [Confirmed]: (Assignment Boundary) Given a review-enabled topic is not assigned to the current reviewer | When the reviewer views that topic | Then the per-topic checkbox is visible only if the reviewer otherwise meets the visibility rule, remains unchecked, is disabled, and cannot mutate completion | Evidence: `UAC-06` and `UAC-16`.
- AC-06 [Confirmed]: (Version Invalidation) Given one or more reviewers marked a topic version done | When the author changes the topic to any different version, including a later revert to an older version | Then completion is unchecked for every reviewer, prior completion is not restored, and no completion history carries across the version change | Evidence: `UAC-07`, `UAC-17`, and `UAC-18`.
- AC-07 [Confirmed]: (Reassignment) Given a topic is reassigned | When the newly assigned reviewer opens its current version | Then the checkbox reflects that reviewer's own state for the current version, preserves their own earlier completion of that same version, and does not inherit the previous assignee's state | Evidence: `UAC-08`.
- AC-08 [Confirmed]: (Left Panel) Given the current reviewer marks an assigned topic's current version done | When the left navigation refreshes | Then that topic shows a green dot; when it is not done for that reviewer and version, no completion indicator is shown | Evidence: `UAC-09`.
- AC-09 [Confirmed]: (Progress Numerator) Given the review contains assigned topics across completed, incomplete, and changed versions | When the `Topics viewed` progress is calculated for the current reviewer | Then the numerator counts only topics marked done by that reviewer at each topic's current version and does not increase merely because a topic was opened | Evidence: `UAC-10`, `UAC-11`, and `UAC-13`.
- AC-10 [Confirmed]: (Progress Denominator) Given assignment-restricted and any-reviewer review fixtures | When `Topics viewed` is calculated | Then the denominator is the review-enabled topics assigned to the current reviewer for an assignment-restricted review, or all review-enabled topics for an any-reviewer review, and the UI renders `Completed/Assigned` with the approved progress design | Evidence: `UAC-10` and `UAC-12`; exact visual styling requires restored Figma access.
- AC-11 [Confirmed]: (Mode Parity) Given an eligible reviewer and the same review/topic/version state | When the reviewer uses Preview and non-Preview edit/review modes | Then checkbox state, left-panel indicator, progress counts, assignment behavior, and version-reset behavior are consistent in both modes | Evidence: `UAC-14`.
- AC-12 [Confirmed]: (Authorization) Given a user is not a verified reviewer of the review | When that user submits or replays a per-topic completion request regardless of manipulated client state | Then the backend rejects the update and no reviewer/topic/version completion state changes | Evidence: `UAC-15`.
- AC-13 [Confirmed]: (Visibility) Given an eligible reviewer, a view-only author, and a view-only administrator | When each opens the same review | Then only users who currently qualify for the existing `Mark as Done` action see the checkbox, green dot, and `Topics viewed` progress UI | Evidence: `UAC-16`.
- AC-14 [Proposed]: (Task Completion Guard) Given fewer than all eligible topics are complete or the set changes during review | When the reviewer invokes `Complete review task` | Then the system follows an explicitly approved enablement, warning, blocking, or completion rule without silently auto-completing the task | Evidence needed: final task-level completion semantics.
- AC-15 [Proposed]: (Performance) Given an approved large-review fixture and concurrent reviewer workload | When per-topic completion and progress recalculation run | Then UI latency, API latency, throughput, and resource use remain within approved measurable thresholds | Evidence needed: a signed performance contract.
- AC-16 [Proposed]: (Accessibility) Given keyboard-only and assistive-technology users | When they inspect and operate completion controls and progress | Then checkbox label, disabled state, focus order, status indication, and progress semantics are programmatically exposed without relying on green color alone | Evidence needed: approved accessibility/design contract.

### Required Open Questions

- What is the primary Jira key, exact feature-flag key, default state, rollout environment, and rollback behavior?
- Can `Complete review task` be invoked before every eligible topic is done, and is the action enabled, blocked, warned, or always available? The final UAC does not approve auto-completion.
- What persistent identifier represents the current topic version, and which operations count as a version change: save, checkpoint, label, revert, restore, or source replacement?
- How are concurrent updates, stale tabs, retries, duplicate requests, network failure, and optimistic UI rollback handled without losing or resurrecting completion?
- How are reassignment, unassignment, topic deletion, review-disabled topics, duplicate references, and assignment changes reflected in the denominator and left-panel state?
- What response codes, error payloads, audit fields, and idempotency rules apply to authorized and unauthorized completion requests?
- After Figma reauthentication, what exact progress-bar states, colors, dimensions, empty/zero state, loading state, error state, overflow behavior, and responsive rules are approved?
- What keyboard, screen-reader, contrast, tooltip, and non-color indicator requirements apply to the checkbox, green dot, progress, and task button?
- Do notifications, dashboard state, or public APIs change? No Confirmed AC is justified for notification payloads or topic-status API shape from the final UAC.
- If performance sign-off matters, what topic counts, reviewer counts, repetitions, percentile, maximum UI/API latency, and CPU/memory ceilings define pass/fail?

### Regression Areas

- Single-topic and multi-topic reviews; one reviewer, multiple reviewers, assignment-restricted reviews, and any-reviewer reviews.
- Check, uncheck, repeated toggle, refresh, reopen, browser back/forward, stale tab, retry, duplicate request, and failed request rollback.
- Topic version advance, revert, restore, multiple sequential versions, and reset across every reviewer without history resurrection.
- Assignment, reassignment, unassignment, reviewer removal/re-add, current-version prior completion, and isolation from the previous assignee.
- Preview and non-Preview mode parity, topic navigation, left-panel green-dot lifecycle, and `Topics viewed` numerator/denominator reconciliation.
- Feature flag on/off, task-button label, legacy `Mark as Done` behavior, rollout rollback, and no partial new UI while disabled.
- Reviewer, view-only author, view-only administrator, removed reviewer, direct API replay, and client-state tampering.
- Existing review comments, replies, attachments, side-by-side diff, task navigation, current/closed review state, and final task completion remain unchanged unless explicitly included.
- Notifications, dashboard aggregation, API payloads, accessibility, localization, and large-review performance remain targeted gaps until their contracts are approved.


## How To Reuse This Pattern

- Put Jira’s UAC/sign-off conditions under `Acceptance Criteria`; treat them as the primary acceptance contract, not optional background.
- Let UAC drive `Expected Behaviour`, `Test Scenarios`, `Regression Areas`, and `Open Questions` before adding PR/RAG/Figma/repo-derived coverage.
- Use UAC scope and out-of-scope to avoid testing known non-goals as failures.
- Use UAC integration notes to decide what nearby workflows can break and must be listed under `Regression Areas`.
- Put cloud/on-premise parity, status, cancel/abort/resume, versioning, and configuration rules under `Expected Behaviour`.
- For review-functionality tickets, put impacted pages, no feature flag, doc impact, automation impact, and no-regression expectations under `Scope From Git`, `Test Scenarios`, and `Regression Areas` as applicable.
- For per-topic review-completion tickets, preserve the binary checked/unchecked model, reviewer-and-current-version isolation, reset-without-history on every version change, reassignment to the new reviewer's own state, assignment-aware `Completed/Assigned` counting, Preview/non-Preview parity, feature-flag-off legacy behavior, explicit task completion, and backend reviewer authorization; do not infer three-state status, opened-topic progress, auto-completion, notifications, API payloads, or Figma styling.
- For live filter tickets, always test typed input, pasted input, no-match empty state, clearing input, case-insensitive matching, stale results, and no-extra-action behaviour.
- For Assets Admin DITA Element Predicate tickets, inspect the real QueryBuilder request and require mapped `property`, `property.operation`, and non-empty `property.value`; independently verify filtered results, applied-filter chip creation/removal, tokenization-before-resubmit, and Repository-search control behavior without inventing tokenization or combined-filter semantics.
- For DITA table whitespace tickets, always test CALS table, `simpletable`, `reltable`, body/header cells, inline-tag boundaries, NBSP, regular-space collapse, block-child trimming, text-forbidden tags, and structural indentation leakage.
- For HTML topic-title initialization tickets, verify exact custom selector precedence, legacy `<h1>` fallback, missing-selector combinations, duplicate prevention, and save/reopen persistence without applying HTML rules to DITA topics.
- For user-dictionary spell-check tickets, separate alphabetic, numeric-prefix, numeric-suffix, middle-digit, and special-character positions; verify old/new editor parity and never invent a punctuation set, dictionary-refresh rule, or definition of `ignored`.
- For asset-status path parsing tickets, always test comma literals in `paths` and `excludedPaths`, folders, file names, `.ditamap`, multiple paths, mixed comma/non-comma batches, folder expansion, state mapping, duplicate paths, invalid relative paths, not-found paths, consecutive commas, spaces, special characters, and trailing commas.
- For Schematron validation tickets, always separate empty no-rule files from malformed/broken `.sch` files, verify save is not blocked, verify no UI message is introduced for empty files, keep real rule violations intact, and ask whether the fix is endpoint-side, editor-side, on-prem, Cloud, or all of them.
- For Schematron role-severity tickets, always test `<sch:assert>` and `<sch:report>`, fixed severities `fatal/error/warn/info`, accepted aliases `warning/information`, case-sensitive matching, unsupported-role fallback, missing-role backward compatibility, Fatal/Error save blocking, Warn/Info non-blocking, visual design parity, filtering/tooltips, and many-message performance.
- For Native PDF Print tab tickets, always test UI section order, removed controls, master/individual toggle sync, empty-field semantics, page box custom behavior, Color Space/Convert Colors/Rendering Intent visibility, ICC predefined/Other/None flows, generated `mergedHTML.json`, rendered PDF output, PDFReactor version compatibility, upgrade mapping, and preset cloning.
- For Old AEM Site publishing tickets with `ditavalref`, `keydef`, `conkeyref`, or resource-only behavior, always verify keydef pages are not generated, `conkeyref` resolves from key definitions, resource-only `xref` does not resolve as a normal page, normal topicrefs still publish, and known DITA-OT static-title behavior stays out of scope unless Jira says otherwise.
- For UI config JSON upgrade tickets, always separate upgraded-instance retained values from fresh-install defaults; verify custom CSS, custom `ui-config.json` components, shortcut keys, custom DITA attributes/elements, default templates, snippets, labels, Show Tags, Display Attributes, XML Comments, and Quick Insert Menu.
- For DB/Splunk logging tickets, always separate noisy JCR/on-prem DB warning/info logs from valid Cloud DB errors, verify exact unwanted logger strings are absent, preserve actionable error logging, test authoring and reference add/update regressions, capture Splunk query evidence, and keep automation as a gap until Splunk-query setup exists.
- For key-resolution report tickets, always test root map, key map, nested-map scope, valid versus missing keys, `keyref` versus `conkeyref` link types, correct linked file, post-processing/index refresh, create/rename/delete updates, no false positives, `Used In` title/path accuracy, Topic/Map file type, CSV/Excel export parity, and existing cross-link/reusable-content regressions.
- For on-premise release tickets, always ask upgrade-impact open questions about source/target versions, retained custom configs, changed defaults, manual post-upgrade steps, Cloud parity, and backward compatibility.
- Convert each UAC bullet into one practical `P0`, `P1`, or `P2` scenario with action and expected result.
- Keep file-type matrices compact; do not create a table unless the user explicitly asks.
- Add RAG-backed AEM configuration links only when `ask_dita_expert` confirms relevant upload restriction, duplicate detection, size, or versioning behaviour.
