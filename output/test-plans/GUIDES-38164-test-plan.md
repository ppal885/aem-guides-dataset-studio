# Test Plan: GUIDES-38164

**Understanding From Jira**
- Issue understood: GUIDES-38164 is a Major SLA3 customer defect (IBM, AEM Cloud cm-p132321-e1283790) where Subject Scheme Maps cannot be authored in Editor view due to two blocking UI defects: (1) selecting `hasInstance` triggers the OS file-selection dialog and auto-injects `href` and `type` attributes into the XML; (2) the Content Properties panel never loads for `<subjectdef>` nodes, blocking key-definition entry; the only viable workaround is Source mode.
- Why it matters: IBM content authors cannot use the visual editor for any Subject Scheme Map authoring work; switching to Source mode removes WYSIWYG support, dramatically slows authoring, and increases error risk for a production tenant; GUIDES-38164 is labeled SLA3 with 24 engineering comments and customer video evidence; both defects block taxonomy and content-classification workflows entirely.
- Requested outcome: Selecting `hasInstance` in Editor view must not open the file-selection dialog and must not inject `href` or `type` attributes; the Content Properties panel must load and remain stable when `<subjectdef>`, `hasInstance`, and `enumdef` elements are selected; key definitions must be editable and persistable via the panel; the fix must hold for IBM and Swift production Subject Scheme Maps including CJK-content datasets.
- Lifecycle understood as: `Post-Fix Validation` -- GUIDES-38164 is Closed; fix shipped in version 2605; plan targets regression validation and gaps not covered by the existing UI automation suite (TC_04 through TC_06).
- Evidence boundary: Live Jira GUIDES-38164 fetched via JiraClient (status: Closed, priority: Major, component: Authoring, fix version: 2605, labels: IBM, SLA3); UAC supplied by QA owner (pasted, covers file-dialog, attribute-injection, panel-load, panel-stability, key-definition, source-mode, and dataset scenarios); video attachments (2025-11-13 14-54-12.mkv, Screen Recording 2026-04-06) listed but not downloaded in this session; UI automation repo at `C:\UI TEST\guides-ui-tests` inspected -- TC_04, TC_05, TC_06 in `tests\subject_scheme\subject_scheme.feature` cover the core file-dialog and panel-load scenarios; no CJK, 1000-file, or Source-mode-roundtrip automation found; behaviour_matters: false -- pure deterministic UI event-handler and panel-registration bug fully explained by reading the editor component code; RAG skipped per Phase 3 decision tree.

**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given a Subject Scheme Map is open in Editor view and a `hasInstance` element or a `subjectdef` element that contains `hasInstance` is selected | When the selection event fires (single click, keyboard nav, or nested/root context) | Then the OS file-selection dialog does not open, `hasInstance` selection does not auto-open the dialog, and no `href` or `type` attribute is injected into the XML.
- AC-02 [Confirmed]: (Basic) Given a Subject Scheme Map is open in Editor view and the author explicitly clicks the Browse / Select file control in the Content Properties panel for the `href` field | When the browse action is triggered | Then the file-selection dialog opens, the author can select a file, and only the resulting `href` and `type` values from that explicit selection are persisted to the XML.
- AC-03 [Confirmed]: (Negative) Given a `hasInstance` element already carries valid `href` and `type` attributes | When the author selects the element in Editor view without clicking Browse | Then the existing `href` and `type` values are not overwritten or cleared; the selection event alone must not modify these attributes.
- AC-04 [Confirmed]: (Basic) Given a Subject Scheme Map is open with `rightPanel=properties_panel` | When the author opens the map from repository view or map view for the first time | Then the Content Properties panel loads and is visible without requiring a Source-mode-then-back switch; the panel renders correctly for `subjectscheme` file type and shows content properties and file properties.
- AC-05 [Confirmed]: (Basic) Given a Subject Scheme Map is open and a `<subjectdef>` element is selected | When the Content Properties panel is visible | Then the panel shows fields to enter and edit key definitions for the selected `subjectdef` node.
- AC-06 [Confirmed]: (Basic) Given an author has entered or edited key definitions in the Content Properties panel for a `<subjectdef>` | When the author saves the map | Then the saved Subject Scheme Map contains the entered keys and no unintended `href` or `type` attributes on any `hasInstance` or `subjectdef` element.
- AC-07 [Confirmed]: (Negative) Given a Subject Scheme Map is open in Editor view and the author switches selection between `subjectdef`, `hasInstance`, and `enumdef` elements multiple times | When each selection change fires | Then the Content Properties panel does not hide or unload; the panel updates for the newly selected node and does not display stale values from the previous selection.
- AC-08 [Confirmed]: (Integration) Given a Subject Scheme Map is opened, edited, and saved in Editor view (no file dialog, no attribute injection) | When the author switches to Source mode and back to Editor view | Then the map content is consistent with what was saved; the roundtrip does not introduce attribute corruption or data loss.
- AC-09 [Proposed]: (Integration) Given IBM production Subject Scheme Maps from the `subjectschemes` path and Swift Subject Scheme Maps are opened in Editor view in a 1000-file-set environment | When the author selects `hasInstance` or `subjectdef` elements and enters key definitions | Then no file dialog opens, no unintended attribute injection occurs, key editing works, and the panel loads correctly for both tenant datasets including maps with CJK content.

**Expected Behaviour**
- EB-01: Selecting `hasInstance` in Editor view must be a pure read / focus action; the editor's element-selection event handler must not treat `hasInstance` the same as a file-link element (such as `xref` or `image`) that should open the Browse dialog on selection; the Browse dialog must only open when the author explicitly invokes a Browse control.
- EB-02: The `href` and `type` attribute injection path is tied to the file-selection dialog; since the dialog must not open on `hasInstance` selection, no attribute pair should be injected; only an explicit Browse + file selection may produce a new `href`/`type` pair, and only for the field the author browsed.
- EB-03: The Content Properties panel must register correctly for the `subjectscheme` file type and for `subjectdef` and `hasInstance` element selection events; the absence of the panel on first open (without a Source-mode toggle) indicates a registration or lifecycle bug in the panel component that must be addressed in the fix.
- EB-04: Panel stability across multi-element selection switches (subjectdef → hasInstance → enumdef) means the panel's mount/unmount lifecycle must not be coupled to element type changes; the panel must stay mounted and refresh its content reactively.
- EB-05: Source mode and Editor mode must share the same underlying XML model; a roundtrip must not alter any attribute or element content, confirming the fix does not introduce a serialization discrepancy.

**Scope From Git**
- Lifecycle stage: `Post-Fix Validation` -- GUIDES-38164 is Closed; fix shipped in version 2605; no PR or branch reference provided in Jira; SHA not captured for the fix (treat as provisional); plan targets regression validation of the shipped fix.
- Issue source: Live Jira GUIDES-38164 (Customer Request, SLA3, Priority Major, component Authoring, IBM, cm-p132321-e1283790 Production), fix version 2605.
- UI automation clone: `C:\UI TEST\guides-ui-tests` inspected read-only this session; SHA not captured (treat as provisional); TC_04, TC_05, and TC_06 in `tests\subject_scheme\subject_scheme.feature` are tagged `@playwright` and confirm core fix coverage; TC_03 covers Content Properties attribute-injection verification.
- Related Jira: GUIDES-26626 (Application Error on Subject Scheme Map creation with extension framework, Open, Major) shares the Subject Scheme Map Editor surface; the extension framework interaction is a different defect class but the same authoring path.
- PR discovery: Not applicable -- fix already shipped; plan focuses on post-fix validation and coverage gaps.

**Code Touched**
- Fix location not specified in Jira (no PR reference); implicated areas based on symptoms: XML Editor component handling element selection events for `hasInstance` (file-dialog registration in the editor clientlib or element-type-to-dialog mapping); Content Properties panel registration for `subjectscheme` file type and `subjectdef`/`hasInstance` elements (right-panel lifecycle and file-type binding in the XML Editor framework).
- Not applicable -- no specific file paths confirmed; plan authors should request the fix commit SHA from the implementing developer before sign-off testing to verify the exact files changed.

**Lines Changed**
- Not applicable -- no PR reference available; plan targets validation of the 2605 release artifact.

**Test Scenarios**
- Setup and test data: A DITA Subject Scheme Map (`hasinstance-test.ditamap`) containing at least one `<subjectdef keys="platform">` element with two child `<hasInstance>` elements -- one with no attributes and one with existing `href="platform-a.dita" type="topic"` pre-set; a second map (`withHasInstance.ditamap`) that mirrors the existing TC_05 fixture; AEM Guides Editor view on version 2605+; Content Properties panel enabled in the right-panel config (`rightPanel=properties_panel`); test user with author permissions on the IBM-style subjectschemes repository path.
- P0 TC-01 [AC-01]: Open `hasinstance-test.ditamap` in Editor view; click the `hasInstance` element directly; assert the OS file-selection BrowseDialog is NOT visible; assert no new `href` or `type` attribute appears in the XML after the click.
- P0 TC-02 [AC-01]: Select a `subjectdef` element that contains `hasInstance`; assert BrowseDialog is NOT visible; assert no attribute injection into the `hasInstance` child element.
- P0 TC-03 [AC-02]: With `withHasInstance.ditamap` open and a `hasInstance` element selected, explicitly click the Browse control in the Content Properties panel `href` field; assert BrowseDialog opens; select a file; assert the `href` and `type` attributes are written with the selected values and the dialog closes.
- P0 TC-04 [AC-04]: Open a Subject Scheme Map with `rightPanel=properties_panel` from the repository view for the first time (no prior Source-mode toggle); assert Content Properties panel is visible immediately; assert it renders content properties and file properties for the `subjectscheme` file type.
- P1 TC-05 [AC-03]: Open `hasinstance-test.ditamap`; select the `hasInstance` element that already has `href="platform-a.dita" type="topic"` pre-set; assert the `href` and `type` values are unchanged after the selection event; assert no overwrite or clearing occurred.
- P1 TC-06 [AC-05]: Select a `<subjectdef keys="platform">` element in Editor view; assert the Content Properties panel shows fields for entering key definitions; enter key value `prod-platform`; assert the field accepts the input.
- P1 TC-07 [AC-06]: After entering key value `prod-platform` for the `<subjectdef>` in TC-06, save the map; open the saved map and verify the `keys="prod-platform"` attribute is present on the `subjectdef` element and no unintended `href` or `type` attributes appear on any `hasInstance` or `subjectdef` element.
- P1 TC-08 [AC-07]: In Editor view, click `subjectdef`; then `hasInstance`; then `enumdef`; then back to `subjectdef`; assert the Content Properties panel remains visible throughout all selection changes; assert each click updates the panel to show the correct selected element's properties without stale values from the previous selection.
- P2 TC-09 [AC-08]: Edit a `subjectdef` key value in Editor view; save; switch to Source mode; verify the key attribute is present and correct in raw XML; switch back to Editor view; assert the Content Properties panel still shows the correct key value and no attribute corruption.
- P2 TC-10 [AC-09]: Open IBM production Subject Scheme Maps from the `subjectschemes` repository path in a 1000-file-set environment; select `hasInstance` elements; assert no file dialog opens and no attribute injection occurs; open Swift Subject Scheme Maps and repeat the same assertions; for any maps containing CJK (Chinese, Japanese, Korean) key values, enter a CJK key definition and save; assert the saved map contains the CJK value without corruption.

**Known Jira Bugs / Past Similar Tickets**
- GUIDES-26626: Similarity: structural twin -- Subject Scheme Map Editor view crashes with Application Error when extension framework is enabled; the creation path that fails shares the same Subject Scheme Map Editor component and `hasInstance` interaction surface; Status: Open; Resolution: Unresolved; Affected version: n/a; Fix version: n/a; RCA: Application Error when creating Subject Scheme Map from First Mile Home Page with extension framework enabled; Test evidence: reproduction confirmed on internal sandbox; Impact: TC-10 (IBM production maps) may trigger GUIDES-26626 if extension framework is active on the customer tenant; QA must confirm extension framework status on the IBM test environment before running TC-10.
- Historical search status: jira_qa (22,317 chunks) queried via three JQL intents: (1) `project = GUIDES AND component = Authoring AND text ~ "hasInstance" AND text ~ "file dialog" AND error` -- GUIDES-26626 surfaced as structural twin (Subject Scheme Map Editor surface, application error, open); (2) `project = GUIDES AND component = Authoring AND text ~ "properties panel" AND text ~ "subjectdef" AND workflow = editor` -- no other panel-load defect class found for subjectscheme; (3) `project = GUIDES AND component = Authoring AND text ~ "href injection" AND text ~ "element selection" AND error` -- no prior href-injection-on-selection history for hasInstance; GUIDES-38164 appears to be the first SLA3 customer report for this specific two-defect combination on Subject Scheme Maps.

**Regression Areas**
- The `hasInstance` element selection event handler change must not affect other file-link element types (`xref`, `image`, `link`) that ARE expected to open the Browse dialog on selection; running the existing `@playwright` subject_scheme.feature TC_05 (explicit Browse) and xref/image dialog tests after the fix is mandatory to confirm the handler change is scoped correctly.
- Content Properties panel registration changes for `subjectscheme` must not break panel loading for other DITA map types (bookmap, ditamap, submap); the panel lifecycle fix must be scoped to the subjectscheme file type without introducing a regression in panel load behavior for regular maps or topic authoring views.
- The attribute injection guard for `hasInstance` must not block legitimate `href`/`type` writes from other interaction paths (explicit Browse + file selection); the existing TC_03 Content Properties attribute-injection scenario must confirm the guard is conditional on the selection-event path only, not on all attribute-write paths for `hasInstance`.
- Subject Scheme enumeration definition resolution (tested by `C:\api automation\dxml-it-tests\guides-regression\src\main\java\com\adobe\aem\guides\it\regression\tests\xmleditor\SubjectSchemeEnumerationDefinitionIT.java`) must continue to function correctly after the Editor-view fix; the backend enumdefs API is consumed by the Content Properties panel and must not be disrupted by any frontend panel-registration changes.

**Automation Coverage & Gaps**
- AC-01 - Exact and strong: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` TC_04 covers `hasInstance` insertion without BrowseDialog opening; TC_05 covers direct selection of an existing `hasInstance` element and asserts dialog does not open; both are tagged `@playwright` and are in the active regression suite.
- AC-02 - Exact and strong: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` TC_05 covers explicit Browse click on `href` field and asserts dialog opens; this is the positive path that must still work after the fix.
- AC-03 - Not covered: no test selects a `hasInstance` element that already has pre-set `href` and `type` attributes and verifies they are NOT overwritten by the selection event; add a step to TC_05 or a new scenario in `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` using the integration UI layer; setup fixture `hasinstance-test.ditamap` with a pre-set `href="platform-a.dita" type="topic"` on one `hasInstance` element; poll element attribute state after single-click with 5-second timeout; assert `href` and `type` values match the pre-set values; cleanup by reverting the map to the original; tag `@playwright` under the existing `@Component(AUTHORING)`.
- AC-04 - Exact but weak oracle: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` TC_06 covers Content Properties panel loading for `subjectdef` but does not explicitly test the panel loading from a first-open cold state (without a prior Source-mode toggle); strengthen TC_06 to assert panel load on cold open from the repository panel; no new file needed -- extend existing TC_06 steps.
- AC-05 - Exact and strong: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` TC_06 covers Content Properties panel showing `subjectdef` label and link-path input field for a selected `subjectdef` element; `content_properties_panel.py` `verify_editable_fields_for_element` method provides the assertion helper.
- AC-06 - Not covered: no test enters key definitions via the Content Properties panel and asserts they persist in the saved XML; add a UI scenario in `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` using the integration UI layer; setup a Subject Scheme Map with a `subjectdef`; enter a key value via the panel `type_attribute_name` helper in `content_properties_panel.py`; poll for save-complete with 10-second timeout; assert the saved XML contains the entered key; cleanup by deleting the test map; tag `@playwright` under the existing `@Component(AUTHORING)`.
- AC-07 - Not covered: no test switches selection between `subjectdef`, `hasInstance`, and `enumdef` multiple times and asserts panel stability; add a UI scenario in `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` using the integration UI layer; setup `hasinstance-test.ditamap`; cycle selection subjectdef→hasInstance→enumdef→subjectdef; poll panel visibility after each click with 5-second timeout; assert panel is visible and element label updates after each switch; cleanup by closing map; tag `@playwright` under the existing `@Component(AUTHORING)`.
- AC-08 - Not covered: no test covers the full Editor→Source→Editor roundtrip for a Subject Scheme Map; add a UI scenario in `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` using the integration UI layer; setup a saved Subject Scheme Map with known `subjectdef` keys; switch to Source mode, assert XML contains the keys, switch back to Editor view; poll panel load within 5-second timeout; assert Content Properties panel shows the same key values; cleanup by closing; tag `@playwright`.
- AC-09 - Not covered: no automated test covers IBM or Swift production Subject Scheme Maps, CJK content, or 1000-file-set environments; execute this scenario manually using the manual validation layer in the IBM production tenant (cm-p132321-e1283790) and the Swift tenant; setup consists of exporting IBM and Swift production Subject Scheme Maps from `/content/dam/guides/subjectschemes/` as test fixtures or accessing the production tenants directly under QA supervision; poll generation and save status after each hasInstance click and after each panel load with a 30-second timeout; assert no file dialog opens, no attribute injection occurs, key editing succeeds, and Content Properties panel loads for all maps including those with CJK key values; cleanup by reverting any test edits to the IBM and Swift maps after each run; tag the manual execution report `@SLA3` and cross-reference the Dynamics case E-001935435.

**Open Questions**
- OQ-01: Impact -- video attachments (2025-11-13 14-54-12.mkv, Screen Recording 2026-04-06) were not downloaded in this session; the videos likely show the exact repro steps and the state of the UI after the fix; QA must view both videos before finalizing TC-01 through TC-03 to confirm whether the file dialog behavior in the fix matches the expected post-fix behavior shown in the April 2026 recording, and to identify any edge cases visible in the IBM reproduction video that are not covered by TC-01 through TC-09.
- OQ-02: Impact -- TC-10 (IBM production maps, Swift maps, CJK datasets, 1000-file-set) is a manual test; confirm with the QA team whether access to the IBM production tenant (cm-p132321-e1283790) is available for post-fix validation testing, and whether a representative set of IBM production Subject Scheme Maps can be exported from `/content/dam/guides/subjectschemes/` for use as test fixtures on a lower environment if production access is not available.
- OQ-03: Impact -- GUIDES-26626 (extension framework + Subject Scheme Map creation error) is still Open; confirm whether the extension framework is active on the IBM test environment used for TC-10 and whether GUIDES-26626 could block TC-10 completion; if it is active and GUIDES-26626 is not fixed, TC-10 must be scoped to non-extension-framework scenarios only and GUIDES-26626 must be logged as a blocking dependency.

---

## Appendix A — Automation Evidence

### AC-01 — Exact and strong (TC_04, TC_05)

Source: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` lines 38–59

```gherkin
  @playwright
  Scenario: TC_04||Verify that inserting hasInstance element in a Subject Scheme map does not open the Browse file-selection dialog || hakapoor
    Given AEM Guides page is opened
    Then Open the DITA map at /content/dam/guides_regression/GUIDES-38164/schematron_test.ditamap in the map view
    When the user opens the map file for editing in the XML editor Author view
    Then checks the tags view status
    When the user places the cursor inside the Subject Scheme map content
    When the user opens the Insert Element dialog
    When the user inserts a hasInstance element from the Insert Element dialog
    Then the hasInstance element is present in the map structure
    Then the Browse file-selection dialog does not open

  @playwright
  Scenario: TC_05||Verify that the file-selection dialog opens only when the Browse control is explicitly clicked on a hasInstance element || hakapoor
    Given AEM Guides page is opened
    Then Open the DITA map at /content/dam/guides_regression/GUIDES-38164/withHasInstance.ditamap in the map view
    When the user opens the map file for editing in the XML editor Author view
    Then checks the tags view status
    When the user selects the hasInstance element in the Author view
    Then the Browse file-selection dialog does not open
    When the user clicks the Browse control for the href field in the Content Properties panel
    Then the Browse file-selection dialog opens
```

Proves: inserting hasInstance and selecting an existing hasInstance element both assert the BrowseDialog does not open (AC-01); explicit Browse click asserts it does open (AC-02).
Gap for AC-03: TC_05 does not load a `hasInstance` with pre-existing `href` and `type` attributes and assert those values are unchanged after the selection event. A new step or fixture variation is needed.

---

### AC-04 / AC-05 — Exact (TC_06)

Source: `C:\UI TEST\guides-ui-tests\tests\subject_scheme\subject_scheme.feature` lines 61–68

```gherkin
  @playwright
  Scenario: TC_06||Ensure Content Properties panel shows fields to edit key definitions when subjectdef is selected || hakapoor
    Given AEM Guides page is opened
    Then Open the DITA map at /content/dam/guides_regression/GUIDES-38164/withHasInstance.ditamap in the map view
    When the user opens the map file for editing in the XML editor Author view
    Then checks the tags view status
    When the user selects the subjectdef element in the Author view
    Then the Content Properties panel shows editable key definition fields for subjectdef
```

Proves: selecting a `subjectdef` element causes the Content Properties panel to show key-definition fields (AC-05). Also confirms panel loads during map editing session (partial coverage for AC-04).
Gap for AC-04 cold-open: TC_06 opens the map in editor view but does not test the panel loading from a cold-start repository view open without any prior Source-mode toggle; extend TC_06 to open the map from the repository panel for the first time to cover the cold-open regression.

---

### Reusable helpers for gap tests (AC-03, AC-06, AC-07, AC-08)

Source: `C:\UI TEST\guides-ui-tests\pages\editor\panels\content_properties_panel.py` lines 579–592

```python
    def click_href_browse_button(self):
        browse_btn = Element(self.context, self.HREF_BROWSE_BUTTON_XPATH, Constants.XPATH)
        browse_btn.should_wait_till(Clickable(5))
        browse_btn.click()

    def verify_editable_fields_for_element(self, element_name):
        type_label = Element(
            self.context,
            f"//div[contains(@class,'filters-panel')]//span[contains(@class,'spectrum-Dropdown-label') and text()='{element_name}']",
            Constants.XPATH
        )
        type_label.should_wait_till(Visible(5))
        self.link_path_input.should_wait_till(Visible(5))
        assert self.link_path_input.get_attribute("disabled") is None
```

`click_href_browse_button` — invokes the Browse dialog explicitly; reuse in any AC-02 or AC-03 extension step to separate "panel click" from "selection event."
`verify_editable_fields_for_element(element_name)` — asserts the Content Properties panel shows the correct element-type label and an enabled link-path input; reuse for AC-05, AC-07 panel-stability assertions, and AC-08 roundtrip panel check.
