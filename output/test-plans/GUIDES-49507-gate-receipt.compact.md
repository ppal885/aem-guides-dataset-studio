**Acceptance Criteria**
- AC-01
  - Starting point: an attribute has a friendly name in the active Editor configuration.
  - Action: an author opens Full Tags View for an element that uses the attribute.
  - Expected result: Full Tags View shows the saved friendly name.

- AC-02
  - Starting point: a conditional attribute has a friendly name in the active Editor configuration.
  - Action: an author opens the Condition Attributes panel.
  - Expected result: the panel shows the saved friendly name instead of the raw name.

- AC-03
  - Starting point: an attribute has a friendly name and is valid for the selected element.
  - Action: an author applies it from the Right Panel.
  - Expected result: the Right Panel keeps the saved friendly name in the selection and applied row.

- AC-04
  - Starting point: a custom attribute added to the DTD is valid for an editor surface.
  - Action: an author views it in Full Tags View, the Condition Attributes panel, or the Right Panel.
  - Expected result: the surface shows its configured friendly name, or its raw attribute name when no friendly name exists.

- AC-05
  - Starting point: an attribute is visible in Full Tags View, the Condition Attributes panel, and the Right Panel.
  - Action: an administrator adds, updates, or removes its friendly name in Workspace Settings.
  - Expected result: every surface automatically shows the change without a page reload.

- AC-06
  - Starting point: any new valid conditional attribute is added to the supported configuration.
  - Action: an author opens an in-scope editor surface.
  - Expected result: the surface shows its configured friendly name, or the raw attribute name when no friendly name exists.

- AC-07
  - Starting point: two logged-in users save different user-level friendly names for one attribute.
  - Action: both users open the same topic and editor surface.
  - Expected result: each user sees only the friendly name saved for that user.

- AC-08
  - Starting point: Use only above attributes is enabled with a configured attribute list.
  - Action: an author opens Add Attribute for any DTD-valid element.
  - Expected result: the list shows only configured attributes that are valid for that element.

- AC-09
  - Starting point: a topic already contains an attribute excluded by Use only above attributes.
  - Action: an author reopens the topic with that setting enabled.
  - Expected result: the existing attribute remains visible in the topic and present in its source XML.

- AC-10
  - Starting point: a profile has saved friendly-name mappings before a supported AEM Guides build upgrade.
  - Action: an author opens the same topics after the upgrade.
  - Expected result: the configured friendly names are preserved with their active-profile scope.

- AC-11
  - Starting point: element friendly names already work in Full Tags View and Quick Insert.
  - Action: an administrator saves an attribute friendly-name change.
  - Expected result: the existing friendly-name functionality for elements is not affected.

- AC-12
  - Starting point: the conditional list contains valid existing attributes.
  - Action: another valid conditional attribute is added.
  - Expected result: the existing entries remain available with their saved attribute names and values.

**Test Scenarios**
- Test data to prepare: use a supported build containing PR 8069; a standard product attribute mapped to mixed-case label TxDOT Product Class; a valid custom DTD attribute customflag; a custom conditional attribute market-segment added through an apps overlay with values; topics inside and outside a folder-profile scope; a global fallback mapping; Use only above attributes on and off; a topic with mapped, unmapped, already-applied, and element-friendly-name examples; a pre-upgrade configuration snapshot; exact label text, raw XML, active-profile, and source-view oracles; and cleanup that restores the profiles, overlay, and topics.
- P0 [TS-01] [AC-01]: Action: open Full Tags View for standard and custom attributes with saved mixed-case labels. Expected: each tag shows the exact saved label and the raw XML attribute name is unchanged.
- P0 [TS-02] [AC-02]: Action: open the Condition Attributes panel for a mapped built-in conditional attribute. Expected: the group heading shows the exact saved label with its original casing.
- P0 [TS-03] [AC-03]: Action: select, apply, and reopen a mapped attribute in the Right Panel. Expected: the exact saved label appears in the dropdown, edit state, and applied row.
- P0 [TS-04] [AC-04]: Action: show mapped and unmapped customflag in Full Tags View, the Condition Attributes panel, and the Right Panel. Expected: each surface shows the configured friendly name or, when none exists, the raw name customflag.
- P0 [TS-05] [AC-05]: Action: add, update, and remove the customflag friendly name in Workspace Settings while all three surfaces are open. Expected: every surface shows each change without a page reload.
- P0 [TS-06] [AC-06]: Action: use a disposable test build whose /libs/fmdita/config/condAttrList.csv includes market-segment, then inspect each in-scope surface. Expected: every surface shows its configured friendly name or, when none exists, the raw name market-segment.
- P1 [TS-07] [AC-07]: Action: save different customflag friendly names for two users, then open the same topic and surface as each user. Expected: each user sees only that user's saved friendly name.
- P1 [TS-08] [AC-08]: Action: enable Use only above attributes and inspect two elements with different DTD-valid choices. Expected: each Add Attribute list contains only choices allowed by both the profile and the selected element.
- P1 [TS-09] [AC-09]: Action: reopen a topic that already contains an excluded attribute while Use only above attributes is enabled. Expected: the attribute remains visible and unchanged in source XML.
- P1 [TS-10] [AC-10]: Action: capture the mappings before upgrade and repeat TS-01 through TS-03 after upgrade. Expected: the same labels and active-profile scope remain effective after upgrade.
- P1 [TS-11] [AC-11]: Action: save an attribute-label change and reopen Full Tags View plus Quick Insert. Expected: existing element friendly names retain their saved text and behavior.
- P1 [TS-12] [AC-12]: Action: compare existing conditional attributes before and after adding market-segment to the test configuration. Expected: every existing attribute keeps its saved name and values.
- Deferred surface checks: add Condition Presets, DITAVAL, Preview, and conditional value-label scenarios only after OQ-01 through OQ-04 receive explicit scope decisions.
- P3 [Regression]: Action: Validate Recheck raw XML after each label operation and confirm the stored attribute name and value are unchanged, because friendly names are display metadata and must not rewrite authored DITA. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck all eight built-in conditional attributes with mapped and unmapped labels, because the PR replaces their prior fixed display labels with profile-aware lookup and fallback behavior. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck two users in the same profile and in different profiles, because the unresolved user-versus-profile scope could expose another user's label. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the attribute dropdown, edit row, and applied row separately for an unmapped attribute, because two current lookup paths do not add an explicit raw-name fallback. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the apps overlay, libs fallback, and legacy XML precedence without editing libs, because upgrade-safe customer configuration must not depend on modifying shipped content. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck existing element friendly names in Full Tags View and Quick Insert, because attribute updates now share the controller path used by the established element feature. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Not covered - based on direct automation evidence for 12 AC mapping(s).
- AC-01: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-02: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-03: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-04: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-05: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-06: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-07: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-08: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-09: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-10: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-11: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-12: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
