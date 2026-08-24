**Acceptance Criteria**
- AC-01
  - Starting point: an attribute has a friendly name in the active Editor configuration.
  - Action: an author opens Full Tags View for an element that uses the attribute.
  - Expected result: Full Tags View shows the saved friendly name.

- AC-02
  - Starting point: a conditional attribute has a friendly name in the active Editor configuration.
  - Action: an author opens the Condition Attributes panel.
  - Expected result: the panel shows the saved friendly name.

- AC-03
  - Starting point: an attribute has a friendly name and is valid for the selected element.
  - Action: an author applies it from the Right Panel.
  - Expected result: the Right Panel keeps the saved friendly name in the selection and applied row.

- AC-04
  - Starting point: a valid custom or built-in attribute has no friendly name.
  - Action: an author views it in Full Tags View, Condition Attributes, or the Right Panel.
  - Expected result: the surface shows its defined nonblank fallback: raw name for custom attributes, default label for built-in conditional attributes.

- AC-05
  - Starting point: a mapped attribute is visible in Full Tags View, Condition Attributes, and the Right Panel.
  - Action: an administrator adds, changes, or removes its friendly name.
  - Expected result: rendered rows plus the open dropdown update before reload or panel reopen, and removal restores the AC-04 fallback.

- AC-06
  - Starting point: a valid custom conditional attribute belongs to the active profile and schema.
  - Action: its name is added to the supported conditional-attribute list.
  - Expected result: the editor discovers it at runtime and shows its mapped or fallback label without a product-code change.

- AC-07
  - Starting point: two signed-in authors open topics governed by different active profiles.
  - Action: each author views the same raw attribute.
  - Expected result: each session shows the label from its topic's active profile without using the other profile's mapping.

- AC-08
  - Starting point: Use only above attributes is enabled with configured valid choices.
  - Action: an author opens Add Attribute for the selected element.
  - Expected result: the list shows only choices that are both configured and valid for that element.

- AC-09
  - Starting point: a topic already contains an attribute excluded by Use only above attributes.
  - Action: an author reopens the topic with that setting enabled.
  - Expected result: the existing attribute remains visible in the topic and present in its source XML.

- AC-10
  - Starting point: a profile has saved friendly-name mappings before a supported AEM Guides upgrade.
  - Action: an author opens the same topics after the upgrade.
  - Expected result: the same labels and active-profile scope still apply.

- AC-11
  - Starting point: element friendly names already work in Full Tags View and Quick Insert.
  - Action: an administrator saves an attribute friendly-name change.
  - Expected result: the existing element friendly names remain unchanged.

**Test Scenarios**
- Test data to prepare: use a supported build containing PR 8069; a standard product attribute mapped to mixed-case label TxDOT Product Class; a valid custom DTD attribute customflag; a custom conditional attribute market-segment added through an apps overlay with values; topics inside and outside a folder-profile scope; a global fallback mapping; Use only above attributes on and off; a topic with mapped, unmapped, already-applied, and element-friendly-name examples; a pre-upgrade configuration snapshot; exact label text, raw XML, active-profile, and source-view oracles; and cleanup that restores the profiles, overlay, and topics.
- P0 [TS-01] [AC-01]: Action: open Full Tags View for standard and custom attributes with saved mixed-case labels. Expected: each tag shows the exact saved label and the raw XML attribute name is unchanged.
- P0 [TS-02] [AC-02]: Action: open the Condition Attributes panel for a mapped built-in conditional attribute. Expected: the group heading shows the exact saved label with its original casing.
- P0 [TS-03] [AC-03]: Action: select, apply, and reopen a mapped attribute in the Right Panel. Expected: the exact saved label appears in the dropdown, edit state, and applied row.
- P0 [TS-04] [AC-04]: Action: remove mappings from customflag and one built-in conditional attribute, then inspect all three affected surfaces. Expected: customflag shows its raw name, the built-in shows its default label, and neither label is blank.
- P0 [TS-05] [AC-05]: Action: add, change, and remove one mapping while its rows and dropdown stay open. Expected: Full Tags View, Condition Attributes, and the Right Panel update without reload or panel reopen; removal restores the AC-04 fallback.
- P0 [TS-06] [AC-06]: Action: add market-segment through the supported apps overlay for the active profile and schema, then open a valid element. Expected: the editor discovers it without a product-code change and shows its mapped label or AC-04 fallback.
- P1 [TS-07] [AC-07]: Action: have two authors open the same raw attribute in topics governed by different active profiles. Expected: each session shows only its topic's applicable label and does not leak the other mapping.
- P1 [TS-08] [AC-08]: Action: enable Use only above attributes and inspect two elements with different DTD-valid choices. Expected: each Add Attribute list contains only choices allowed by both the profile and the selected element.
- P1 [TS-09] [AC-09]: Action: reopen a topic that already contains an excluded attribute while Use only above attributes is enabled. Expected: the attribute remains visible and unchanged in source XML.
- P1 [TS-10] [AC-10]: Action: capture the mappings before upgrade and repeat TS-01 through TS-03 after upgrade. Expected: the same labels and active-profile scope remain effective after upgrade.
- P1 [TS-11] [AC-11]: Action: save an attribute-label change and reopen Full Tags View plus Quick Insert. Expected: existing element friendly names retain their saved text and behavior.
- Deferred surface checks: add Condition Presets, DITAVAL, Preview, and conditional value-label scenarios only after OQ-01 through OQ-04 receive explicit scope decisions.
- P3 [Regression]: Action: Validate Recheck raw XML after each label operation and confirm the stored attribute name and value are unchanged, because friendly names are display metadata and must not rewrite authored DITA. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck all eight built-in conditional attributes with mapped and unmapped labels, because the PR replaces their prior fixed display labels with profile-aware lookup and fallback behavior. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck folder-profile and global-profile isolation for two author sessions, because a stale cached mapping could expose a label from the wrong content scope. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the attribute dropdown, edit row, and applied row separately for an unmapped attribute, because two current lookup paths do not add an explicit raw-name fallback. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck the apps overlay, libs fallback, and legacy XML precedence without editing libs, because upgrade-safe customer configuration must not depend on modifying shipped content. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Recheck existing element friendly names in Full Tags View and Quick Insert, because attribute updates now share the controller path used by the established element feature. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- No same-mechanism Jira ticket is worth checking from the validated evidence.

**Automation Coverage**
- Main feature coverage: Not covered - based on direct automation evidence for 11 AC mapping(s).
- AC-01: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-02: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-03: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-04: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-05: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-06: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-07: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-08: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-09: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
- AC-10: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-11: Not covered - add high-level coverage in the appropriate feature file or integration-test suite for the primary action, observable result, negative boundary, and cleanup.
