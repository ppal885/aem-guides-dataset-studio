**Acceptance Criteria**
- AC-01: a profile whose ui_config.json sets ditaAttributes.required.navtitle to true; when an author inserts an existing DITA topic as a reference in the Map Editor and saves, the saved <topicref> in Source mode carries a @navtitle attribute.

- AC-02: navtitle is required and a topic with a known <title> is referenced; when the topicref is inserted, the @navtitle value equals the referenced topic's <title> text exactly.

- AC-03: navtitle is required; when a topic reference is added through each map insertion entry point - the Insert Topic Reference dialog and drag-and-drop from the repository panel, @navtitle is auto-populated identically for both, not only for the dialog path.

- AC-04: a profile where navtitle is not marked required (ditaAttributes.required has no navtitle or it is false); when a topic reference is inserted, @navtitle is not auto-added, preserving the existing default behaviour.

- AC-05: navtitle is required in a Global Profile and separately in a Folder Profile; when a topic reference is inserted under each profile's scope, @navtitle is auto-populated in both, driven by ui_config.json ditaAttributes.required.navtitle.

- AC-06: navtitle is required; when a topicref is inserted on an element where the DTD permits @navtitle, @navtitle is added, and where the DTD does not permit it @navtitle is not added, so no DTD-invalid markup is produced.

- AC-07: navtitle is required; when an author creates a topichead (a topicref with no href), the required-navtitle configuration is honoured consistently for the topichead, whose navigation label is @navtitle rather than a referenced title.

- AC-08: navtitle is required; when a reference to another map is inserted (a mapref or a topicref with format ditamap), @navtitle is auto-populated from the referenced map's <title>.

- AC-09: navtitle is required and the referenced topic has an empty or missing <title>; when the reference is inserted, @navtitle is set to a defined fallback (empty or the reference identifier) without an editor error and without blocking the save.

- AC-10: @navtitle has been auto-populated on a topicref; when the map is saved, reopened, and edited further, @navtitle persists in Source mode across the round trip and is not stripped by later edits.

- AC-11: @navtitle is present on a topicref and @locktitle is set to yes; when the map is used in navigation and generated output, the auto-populated @navtitle is used as the display title per the locktitle semantics, and adding @navtitle does not change @locktitle behaviour.

- AC-12: navtitle is required; when multiple topic references are added in one action (multi-select insert or multi-item drag-and-drop), each inserted <topicref> independently receives its own @navtitle from its own referenced title with no cross-over between items.

- AC-13: several attributes are marked required in ditaAttributes.required (for example navtitle and another attribute); when a topic reference is inserted, every required attribute the editor supports auto-populating is applied, so the fix is not limited to navtitle in isolation.

- AC-14: a topicref whose navtitle was auto-populated and whose referenced topic is reused as content elsewhere (an xref or link with keyref to it, or the same topic referenced in more than one map); when the reuse consumer resolves its navigation or link text, it resolves to the populated navtitle consistently, and the populated form (the @navtitle attribute the editor writes today versus the <topicmeta><navtitle> element that keyref link-text resolution reads) is defined and consumed correctly.

- AC-15: navtitle is required; when a topic reference is added in the New Editor map surface as well as the xmleditor Map Editor, @navtitle is auto-populated in both editors, since the New Editor exposes its own navtitle field and the drag-drop and insert paths must behave consistently across editors.

- AC-16: a topicref with a stale or missing navtitle; when the author invokes the Refresh navigation title attribute action, @navtitle is re-derived from the current referenced topic title, consistent with the auto-population on insert.

- AC-17: navtitle is required; when a key definition (keydef with keys and href) is created by referencing a topic, @navtitle is not force-added to the keydef, because a keydef is a non-navigation key definition and required-navtitle applies to navigation-bearing references.

- AC-18: navtitle is required and a glossary term is referenced; when a glossref is created for a glossentry, its navigation title is derived appropriately for the glossref specialization rather than left empty.

- AC-19: navtitle is required in a bookmap; when specialized reference types such as chapter and appendix reference a topic, @navtitle is auto-populated on those specialized references as it is on a plain topicref.

- AC-20: a topicref that already has an author-entered @navtitle; when the reference is re-inserted or the map is edited under a required-navtitle profile, the existing author navtitle value is preserved and is replaced only when the author explicitly refreshes it.

- AC-21: navtitle is required and the reference target is external or non-DITA (scope external, or a format that is not dita or ditamap such as a PDF or URL); when the reference is inserted, @navtitle is set to a defined fallback rather than a DITA title, without an editor error.

**Test Scenarios**
- Test data to prepare: a Global Profile and a Folder Profile whose ui_config.json sets ditaAttributes.required.navtitle to true; DITA topics with known titles; a topic with an empty title; an existing map; a referenced sub-map; access to the Map Editor Author, Source, and Side-by-side views and to the repository panel for drag-and-drop.
- P0 [TS-01] [AC-01, AC-02]: Action: with navtitle required, insert a topic with a known title via the Insert Topic Reference dialog, save, and inspect Source mode. Expected: the topicref has navtitle equal to the referenced topic title.
- P0 [TS-02] [AC-03]: Action: repeat the insertion by dragging the topic from the repository panel into the map. Expected: navtitle is auto-populated identically to the dialog path.
- P1 [TS-03] [AC-04]: Action: with navtitle not required, insert a topic reference. Expected: no navtitle is added.
- P1 [TS-04] [AC-05]: Action: perform the insertion under a Global Profile and under a Folder Profile that each require navtitle. Expected: navtitle is populated under both.
- P1 [TS-05] [AC-06]: Action: insert references and inspect that navtitle is added only where the DTD allows it. Expected: no DTD-invalid navtitle is written.
- P1 [TS-06] [AC-07]: Action: with navtitle required, create a topichead with no href. Expected: the required-navtitle configuration is honoured consistently for the topichead label.
- P1 [TS-07] [AC-08]: Action: insert a reference to a sub-map. Expected: navtitle is populated from the referenced map title.
- P1 [TS-08] [AC-09]: Action: reference a topic whose title is empty or missing. Expected: navtitle is set to the defined fallback with no editor error and the save succeeds.
- P0 [TS-09] [AC-10]: Action: save, reopen, and further edit the map. Expected: navtitle persists in Source mode across the round trip.
- P1 [TS-10] [AC-11]: Action: set locktitle to yes on a topicref with the auto-populated navtitle and check navigation and generated output. Expected: navtitle is used as the display title and locktitle behaviour is unchanged.
- P1 [TS-11] [AC-12]: Action: insert several topic references in one multi-select or multi-item drag action. Expected: each topicref gets its own navtitle with no cross-over.
- P1 [TS-12] [AC-13]: Action: mark navtitle and one other supported attribute required and insert a reference. Expected: every supported required attribute is auto-populated.
- P1 [TS-13] [AC-14]: Action: auto-populate navtitle, then reuse the referenced topic via an xref/link with keyref and via a second map, and resolve navigation and link text. Expected: the reuse consumers resolve to the populated navtitle consistently.
- P1 [TS-14] [AC-15]: Action: insert a topic reference in the New Editor map surface and in the xmleditor Map Editor under a required-navtitle profile. Expected: navtitle is auto-populated in both editors.
- P1 [TS-15] [AC-16]: Action: on a topicref with missing navtitle, invoke Refresh navigation title attribute. Expected: navtitle is re-derived from the current referenced title.
- P1 [TS-16] [AC-17]: Action: create a keydef by referencing a topic under a required-navtitle profile. Expected: the keydef has keys and href but no force-added navtitle.
- P1 [TS-17] [AC-18]: Action: create a glossref for a glossentry. Expected: the glossref navigation title is derived appropriately.
- P1 [TS-18] [AC-19]: Action: in a bookmap, add chapter and appendix references. Expected: navtitle is auto-populated on the specialized references.
- P1 [TS-19] [AC-20]: Action: set an author navtitle, then re-insert or edit under a required-navtitle profile without refreshing. Expected: the author navtitle is preserved.
- P1 [TS-20] [AC-21]: Action: insert an external or non-DITA reference (scope external or a PDF or URL). Expected: navtitle falls back to a defined value with no error.
- P2 [Regression] [AC-04]: Action: with navtitle required, verify existing topicrefs already in the map are not retroactively rewritten on open. Expected: only newly inserted references receive navtitle unless product decides otherwise (OQ-01).
- P3 [Regression]: Action: Validate Re-test inserting topic references with navtitle not required so the default no-navtitle behaviour is preserved. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test other required ditaAttributes so the fix does not change attributes other than navtitle unexpectedly. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test the other topicref attributes (href, format, type, keys, keyref) so navtitle population does not drop or alter them, informed by the sibling-attribute gap in GUIDES-45251. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test map save, validation, and reopen so navtitle does not break map serialization or DTD validation. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test the generated-output navigation labels and bookmarks that consume navtitle so the auto-populated value renders correctly downstream, informed by GUIDES-10509. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test both navtitle-population consumers (the Insert Topic Reference dialog and the drag-and-drop path) that share the required-attribute logic, so a fix in the shared path does not regress either entry point. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test reuse consumers (keyref/xref link-text resolution and topics referenced in multiple maps) so the auto-populated navtitle resolves consistently for reused content. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test the New Editor map surface and the Refresh navigation title action so navtitle behaviour is consistent across editors and the refresh path. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test specialized references (keydef, glossref, chapter, appendix, reltable, navref) so required-navtitle is applied only where navigation applies and non-navigation references are not broken. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.
- P3 [Regression]: Action: Validate Re-test existing maps opened after the fix so previously saved topicrefs are not rewritten or corrupted on open. Expected: The named adjacent workflow remains correct and the primary fix introduces no regression.

**Jira Tickets Worth Checking**
- GUIDES-45251 - "[New Editor] Drag dropping topic or map is not adding type attribute".
- GUIDES-10509 - "Native-PDF - navtitle for topichead is not honoured".
- GUIDES-2413 - "Error saving a bookmap after updating navTitle for Topic".
- GUIDES-971 - "Title given while creating a new dita topic should be text of title".

**Automation Coverage**
- Main feature coverage: Unverified - based on direct automation evidence for 21 AC mapping(s).
- AC-01: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-02: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-03: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-04: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-05: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-06: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-07: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-08: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-09: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-10: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-11: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-12: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-13: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-14: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-15: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-16: Not covered - add high-level coverage in feature-file/UI automation for the primary action, observable result, negative boundary, and cleanup.
- AC-17: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-18: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-19: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-20: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
- AC-21: Not covered - add high-level coverage in integration/API test automation for the primary action, observable result, negative boundary, and cleanup.
