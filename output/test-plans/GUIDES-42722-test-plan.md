**Understanding From Jira**

- Issue understood: In Native PDF publishing, when a custom PDF template has a metadata page layout that shows topic metadata and that layout is set to Merge with Previous page in the Page layout order, the generated PDF shows the static metadata labels but the dynamic metadata values, such as the change description and the version, are blank on the merged page.
- Why it matters: Customer context resolved from Jira: the customer is Ariel; their Native PDF template relies on the merged metadata page to display per-topic change description and version, and a blank merged page blocks that publishing use.
- Requested outcome: The merged Native PDF page must render the actual topic metadata values (change description and version or last modified) and not only the static labels, for each topic in the map.
- Lifecycle understood as: Pre-Development UAC; the acceptance field is empty, no code change for GUIDES-42722 exists in Starling, and prior comments are QE open questions, so every acceptance criterion is Proposed.
- Evidence boundary: Evidence mode: degraded. Live Jira was fetched through JiraClient and all five attachments were downloaded and opened; product RAG (ask_dita_expert and the lookup_aem_guides fallback) and indexed and offline Jira history were unavailable because the backend is down, and the Native PDF page-merge and metadata-render engine is not in the Starling clone, so behaviour grounding used the ticket and the opened attachments, no changed-code or file:line render claim is made, and those gaps remain unverified.

**Acceptance Criteria**

- AC-01 [Proposed]: (Basic) Given a Native PDF custom template whose metadata page layout shows topic metadata and is set to Merge with Previous page in Page Layout Order | When Native PDF output is generated from the map | Then the merged page shows the actual topic metadata values and not only the static labels | Evidence: Jira GUIDES-42722; attachment no-metadata-in-pdf.png.
- AC-02 [Proposed]: (Basic) Given a topic that has a change description value and a version or last modified value | When Native PDF output is generated with the merged metadata layout | Then both the change description value and the version or last modified value are shown with the topic real values | Evidence: Jira GUIDES-42722 steps to reproduce; attachment no-metadata-in-pdf.png.
- AC-03 [Proposed]: (Integration) Given a map with two topics that each have a different change description value | When Native PDF output is generated | Then each topic merged metadata page shows that topic own values and shows no value taken from another topic | Evidence: Jira GUIDES-42722 steps to reproduce.
- AC-04 [Proposed]: (Basic) Given a topic whose content spans more than one page in the PDF | When Native PDF output is generated with the merged metadata layout | Then the merged metadata page still shows the correct metadata for that topic | Evidence: Jira GUIDES-42722 steps to reproduce.
- AC-05 [Proposed]: (Basic) Given the merged metadata layout that renders the VER and CHANGE DESCRIPTION labels | When Native PDF output is generated | Then the static labels still render after the fix and are not removed | Evidence: Jira GUIDES-42722; attachment no-metadata-in-pdf.png.
- AC-06 [Proposed]: (Basic) Given a metadata page layout set to Merge with None so it is not merged | When Native PDF output is generated | Then the metadata values render correctly on the standalone metadata page | Evidence: Jira GUIDES-42722; attachment image-2026-02-26-15-05-09-709.png.
- AC-07 [Proposed]: (Integration) Given a metadata page layout set to Merge with Next page | When Native PDF output is generated | Then the metadata values render on the merged page in the same way as the Merge with Previous page case | Evidence: Jira GUIDES-42722 prior QE comment open question.
- AC-08 [Proposed]: (Integration) Given a metadata Field authored in the metadata Page Layout that is bound to a topic metadata property such as change description or version | When Native PDF output is generated with the merged (Merge with Previous page) metadata layout | Then the Field resolves to the topic value for every metadata property field configured in the layout, whether the field is bound to a topic metadata property or a map file metadata property, and not only for change description | Evidence: Jira GUIDES-42722; Page Layout template editor metadata Field.
- AC-09 [Proposed]: (Integration) Given the same map and layout published as Native PDF with the native engine and DITA-OT processing off | When output is also generated for a DITA-OT preset with processing on | Then the metadata rendering fix applies to the Native PDF native engine in scope, and the DITA-OT PDF and other presets such as HTML5 and AEM Site keep their existing metadata behaviour and stay out of scope for this fix | Evidence: Jira GUIDES-42722 component Publishing.

**Expected Behaviour**

- The reported defect is that the merged Native PDF page displays the static metadata labels but the dynamic metadata values are blank; the opened attachment no-metadata-in-pdf.png shows the VER label with no value and the CHANGE DESCRIPTION label with no value. RAG provenance: not available this session; grounded from the ticket and the opened attachments.
- The expected behaviour from the ticket is that the last, merged PDF page displays the metadata of the topic, so the fix must restore the topic metadata context on the merged page rather than only on a standalone metadata page.
- The opened attachment image-2026-02-26-15-05-09-709.png confirms the trigger configuration: the metadata page layout has Merge with set to Previous page in the Page layout order table.
- Whether the same context loss affects Merge with Next page, and whether it affects map-level metadata Fields as well as topic-level metadata Fields in the layout, is not confirmed by current evidence and is carried as Open Questions.
- The Native PDF page-merge and metadata-render engine is not present in the inspected Starling clone, so the exact code point that drops the metadata context on merge is Unknown from current evidence.

**Scope From Git**

- Lifecycle stage: Pre-Development UAC; readiness target is a UAC-ready acceptance contract, not an implementation review.
- Issue source: live Jira GUIDES-42722 fetched through the backend JiraClient; no development link, branch, or PR exists and git -C C:/starling found no 42722 branch, so implementation-review evidence is not applicable.
- Product clone inspected: C:\starling; NativePdfPresetService.java and the CORTopicMetadata and CORDitaMetadata metadata model classes were read for context. Provisional acknowledgment: the Native PDF page-merge and metadata-render engine is a separate Native PDF engine that is not in this clone, so no changed code, file:line, or clone SHA is claimed for the render path.
- Automation clones were not inspected in this pre-development pass; automation coverage is recorded as unverified rather than claimed absent.

**Code Touched**

- No code changes yet - development has not started.
- Current implementation implicated, traced from UI to staging to metadata.xml to renderer, is listed below with complete absolute paths.
- Page layout order and Merge with Previous or Next or None is configured in C:\xmleditor\xmleditor\src\config\ui\views\template_editor_ui.json line 45, and the template controller is C:\xmleditor\xmleditor\src\controllers\widgets\publish\template_details_controller.ts line 6; the metadata Field is authored into the template layout content.
- Native PDF preset handling is in C:\starling\core\publish-listener\src\main\java\com\adobe\fmdita\rest\folderprofiles\NativePdfPresetService.java line 419 mergeNativePdfSpecificFields.
- Template staging for the renderer copies the page layout template and its Field placeholders to disk in C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\ot\NodeJsExecutor.java at line 893 projectTemplatesDir and line 938 extractTemplate.
- The metadata the Field reads is built per asset into metadata.xml in C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\ot\NodeJsExecutor.java at line 717 getMetadataDirectory and line 737 and line 768 createMetadataFile, which is the same metadata.xml pipeline as GUIDES-29816.
- The external renderer is invoked in C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\ot\NodeJsExecutor.java line 1035 executeNodeProcess, which runs the external Node PDF renderer with the staged template and metadata.
- Boundary: the external Node PDF renderer resolves the metadata Field from the topic entry in metadata.xml and is not present in any inspected clone, so the exact Field-resolution-on-merge code is not inspectable, but its inputs the staged template and metadata.xml are verified above; the likely defect is that the merged page is not associated with the correct topic entry in metadata.xml, or that entry is absent.

**Lines Changed**

- Not applicable - development has not started.

**Test Scenarios**

- Test data to prepare: the client sample test-content-pdf-issue.zip with topic1 and topic2 that each carry a different changeDesc value and a version, where topic2 has enough content to span two pages; a map that includes topic1 and topic2 with an updated version; the client PDF template with a metadata page layout that shows change description and version; three layout variants of the template with the metadata layout set to Merge with Previous page, Merge with Next page, and Merge with None; a metadata Page Layout that carries more than one Field placeholder bound to topic metadata properties, such as change description and version, plus one map file metadata Field; and a DITA-OT PDF preset and one other preset for the engine and preset scope check.
- P0 [TS-01] [AC-01, AC-02]: Action: generate Native PDF with the metadata layout set to Merge with Previous page and open the last page. Expected: the merged page shows the change description value and the version value, not only the labels.
- P0 [TS-02] [AC-05]: Action: generate the same Native PDF output and inspect the merged page labels. Expected: the VER and CHANGE DESCRIPTION labels still render.
- P1 [TS-03] [AC-03]: Action: generate Native PDF for the two-topic map. Expected: each topic merged metadata page shows that topic own change description and no value from the other topic.
- P1 [TS-04] [AC-04]: Action: generate Native PDF where topic2 spans more than one page. Expected: the merged metadata page still shows topic2 correct metadata.
- P1 [TS-05] [AC-06]: Action: set the metadata layout to Merge with None and generate Native PDF. Expected: the standalone metadata page renders the metadata values correctly.
- P1 [TS-06] [AC-07]: Action: set the metadata layout to Merge with Next page and generate Native PDF. Expected: the merged page renders the metadata values in the same way as the Previous page case.
- P2 [TS-07] [AC-08]: Action: configure the metadata Page Layout with more than one Field bound to topic metadata properties, such as change description and version, plus one map file metadata Field, then generate Native PDF with the merged layout. Expected: every configured Field resolves the correct topic or map value on the merged page, not only the change description Field.
- P2 [TS-08] [AC-09]: Action: generate the Native PDF native engine output and a DITA-OT PDF preset output for the same map. Expected: the Native PDF merged page carries the metadata values while the DITA-OT PDF and other presets keep their existing metadata behaviour.

**Known Jira Bugs / Past Similar Tickets**

- No same-defect-class Jira ticket was established from validated history; the linked Native PDF metadata tickets GUIDES-20063, GUIDES-29816, and GUIDES-23044 are cited as related same-area context in the same Native PDF metadata surface, not as same-mechanism defect history for the merged-layout render loss.
- Historical search status: the indexed history tool search_jira_history was unavailable this session and the backend was down so the offline jira_qa corpus was also unreachable; intended narrow JQL intents were an error-text search on the blank merged metadata page in Native PDF, a workflow search on Native PDF merged page layout metadata rendering, and a config search on Page layout order Merge with previous page. None could be validated live, so no mutable historical status, resolution, affected version, fix version, underlying cause, or test evidence is claimed.

**Regression Areas**

- Re-run Native PDF with the metadata layout set to Merge with None and confirm the metadata values still render, because the fix changes how the merged page resolves the topic metadata context and could affect the non-merged path.
- Re-run Native PDF and confirm the static VER and CHANGE DESCRIPTION labels still render on the merged page, because the fix changes the merged-page metadata resolution and could disturb the labels that currently work.
- Re-run the other output presets DITA-OT PDF, HTML5, and AEM Site and confirm their metadata rendering is unchanged, because a page-merge change in the publishing path could affect other presets.
- Re-run Native PDF for a large map with many topics and confirm each merged metadata page keeps the correct per-topic values, because per-topic association across a merged layout is the highest-priority regression risk.
- Re-test the metadata.xml assembly path (NodeJsExecutor.extractMetadata / MetadataManager.createMetadataFile) for Native PDF because this ticket shares the exact metadata.xml pipeline exercised by GUIDES-29816, so a change to per-asset metadata assembly can affect both the merged-layout Field values and the damPath and source-props behaviour.

**Automation Coverage & Gaps**

- Main feature coverage: Unverified - automation clones were not synchronized or inspected in this pre-development pass, so existing Native PDF publishing coverage cannot be confirmed or denied.
- AC-01, AC-02, AC-05 - Unverified: recommend a Native PDF publishing IT that generates output with a merged metadata page layout, opens the last page, and asserts both the metadata values and the static labels render, building on existing Native PDF publish fixtures in the dxml-it-tests suite.
- AC-03, AC-04 - Unverified: recommend an IT covering a two-topic map and a topic spanning more than one page, asserting correct per-topic metadata on each merged page.
- AC-06, AC-07 - Unverified: recommend an IT that varies the Merge with setting across None, Previous page, and Next page and asserts values render in each case.
- AC-08 - Unverified: recommend an IT that generates Native PDF with a merged metadata layout carrying several Fields bound to topic and map metadata properties and asserts each configured Field resolves the correct value on the merged page, not only change description.
- AC-09 - Unverified: recommend an engine and preset scope IT that generates Native PDF and a DITA-OT PDF preset and asserts the other presets metadata behaviour is unchanged.

**Open Questions**

- OQ-01: Does Merge with Next page use the same metadata-context propagation path as Merge with Previous page? QA impact: decides whether AC-07 is a shared-fix guarantee or a separate defect that development may down-scope.
- OQ-02: Does the same context loss affect map-level metadata fields as well as topic-level metadata fields in the layout? QA impact: sets the scope of AC-08.
- OQ-03: Is a standalone non-merged custom layout intended to have topic metadata context at all? QA impact: sets the baseline expectation for AC-06 so the non-merged case is not asserted incorrectly.
- OQ-04: Is the topic metadata context dropped specifically when a page layout is merged, since the underlying cause is not yet confirmed? QA impact: determines whether the fix target is the page-merge path and which regression areas apply.
- OQ-05: On the merged page, does the metadata.xml built by MetadataManager and NodeJsExecutor contain the topic entry the Field reads, and does the Node renderer associate the merged page with that topic entry? QA impact: separates a metadata.xml assembly gap shared with GUIDES-29816 from a renderer topic-association bug on merge, and decides whether the fix is backend or renderer.
