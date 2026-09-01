**Understanding From Jira**

- Issue understood: In Native PDF publishing, the temporary metadata.xml receives only the output preset Metadata tab values and omits the Advanced tab File (Asset) properties, so selected source properties such as dc:title, dc:description, dc:language, and docstate never reach the Native PDF metadata.xml.
- Why it matters: Customer context resolved from Jira: Broadcom and Gulfstream are moving from DITA-OT/FMPS to Native PDF and their toolkit rules read the source map path from metadata.xml to style the PDF; Native PDF exposes no equivalent source metadata, which blocks their migration.
- Requested outcome: Native PDF metadata.xml must carry the selected File (Asset) properties for the source map and its topics using the established sourceProps structure from GUIDES-17324 and GUIDES-17997, consistent with other publishing presets, without changing existing Metadata tab behaviour.
- Lifecycle understood as: Pre-Development UAC; the acceptance field is empty, there are no comments, and no development link exists, so every acceptance criterion is Proposed.
- Evidence boundary: Evidence mode: degraded. Live Jira fetched through JiraClient; Starling inspected at publish-workflow BaseExecutor and publish-listener exportditamap; the single attachment was downloaded and opened; ask_dita_expert and indexed Jira history (search_jira_history) were not available this session, so product-behaviour grounding used the lookup_aem_guides fallback and inspected Starling code, and no same-mechanism historical status is claimed; these gaps remain unverified.

**Acceptance Criteria**

- AC-01 [Proposed]: (Basic) Given a Native PDF preset with values on both the Metadata tab and the Advanced File (Asset) properties control | When Native PDF output is generated | Then the metadata.xml contains the applicable metadata from both sources and the existing Metadata tab values remain unchanged | Evidence: Jira GUIDES-29816; sourceProps contract GUIDES-17324 and GUIDES-17997.
- AC-02 [Proposed]: (Basic) Given a Native PDF publish of a specific source map | When the metadata.xml is generated | Then it contains the source map basic sourceProps for the map being published now, including damPath and the source identifier where available, and none from a previous map or job | Evidence: Starling BaseExecutor.getMetadataList damPath sourceProp; GUIDES-17324.
- AC-03 [Proposed]: (Basic) Given File (Asset) properties selected in the Advanced tab that exist on the source map | When Native PDF output is generated | Then those selected properties are written for the source map in metadata.xml, including supported default and custom properties | Evidence: Jira GUIDES-29816; preset file-metadata configuration GUIDES-3704.
- AC-04 [Proposed]: (Integration) Given topics included in the Native PDF output | When metadata.xml is generated | Then each topic carries its own selected File (Asset) properties and never a value taken from another topic, the parent map, or a previously processed topic | Evidence: Jira GUIDES-29816.
- AC-05 [Proposed]: (Integration) Given a topic included through a nested map or a supported reference | When metadata.xml is generated | Then that topic metadata stays associated with its correct source asset and reuse or nesting does not move one topic metadata onto another | Evidence: Jira GUIDES-29816.
- AC-06 [Proposed]: (Basic) Given several File (Asset) properties selected in the Advanced tab | When Native PDF output is generated | Then all applicable selected properties are written and the result is not limited to the first property, to Adobe-defined names, or to a fixed name list | Evidence: Jira GUIDES-29816 screenshot showing dc:description, dc:language, dc:title, and docstate.
- AC-07 [Proposed]: (Basic) Given source properties written to Native PDF metadata.xml | When the file is generated | Then map and topic properties appear in the established sourceProps structure with the same property names, complete values, and correct source association used by other publishing presets | Evidence: Jira GUIDES-29816; sourceProps contract GUIDES-17324 and GUIDES-17997.
- AC-08 [Proposed]: (Negative) Given a supported metadata value that contains XML-sensitive or Unicode characters | When metadata.xml is generated | Then the value is written as valid XML and retains its value after parsing, and escaping alone never fails Native PDF generation | Evidence: Jira GUIDES-29816.
- AC-09 [Proposed]: (Negative) Given a selected File (Asset) property that is absent on a particular map or topic | When Native PDF output is generated | Then generation completes, the property is omitted for that asset, only values actually present on the asset are written, metadata.xml stays valid XML, and the remaining available metadata is still included | Evidence: Jira GUIDES-29816; Starling BaseExecutor.getMetadataList property-existence guard.
- AC-10 [Proposed]: (Basic) Given the preset has Retain temporary files enabled | When Native PDF output is generated | Then the retained metadata.xml shows the current source map sourceProps, the map-level and topic-level selected File (Asset) properties, and correct source-to-metadata association | Evidence: Jira GUIDES-29816 screenshot Retain temporary files control.
- AC-11 [Proposed]: (Integration) Given a second Native PDF generation for a different map or preset, or a changed File (Asset) properties selection | When output is generated again | Then metadata.xml reflects the current map, current preset, and current selection and retains no values from an earlier generation | Evidence: Jira GUIDES-29816.
- AC-12 [Proposed]: (Basic) Given a Native PDF preset that uses only the Metadata tab | When Native PDF output is generated | Then it produces the same supported PDF document metadata as before the change | Evidence: Jira GUIDES-29816 regression boundary.
- AC-13 [Proposed]: (Basic) Given a Native PDF preset with no File (Asset) properties selected | When Native PDF output is generated | Then generation succeeds with the existing metadata behaviour and File (Asset) properties remain optional | Evidence: Jira GUIDES-29816 regression boundary.
- AC-14 [Proposed]: (Integration) Given the same source map and preset | When PDF output is generated with DITA-OT processing on and again with DITA-OT processing off | Then the existing metadata behaviour stays the same in both modes and only the Native PDF output adds the selected File (Asset) properties | Evidence: Jira GUIDES-29816; Starling BaseExecutor nativeOutput branch.
- AC-15 [Proposed]: (Integration) Given the change to source metadata in metadata.xml | When output is generated for a non-Native-PDF preset such as AEM Site, HTML5, JSON, or DITA-OT PDF | Then that preset output is unchanged and the fix is scoped to the Native PDF preset only, unless shared-code analysis proves the metadata path is shared | Evidence: Jira GUIDES-29816 scope; Starling shared getMetadataList path review.
- AC-16 [Proposed]: (Integration) Given a selected File (Asset) property whose value is set directly on the source asset repository metadata node through CRX DE or the DAM properties view | When Native PDF output is generated | Then the value written to metadata.xml is read from that asset jcr:content metadata node and matches the repository value regardless of how it was set | Evidence: Jira GUIDES-29816; Starling BaseExecutor.getMetadataList reads jcr:content metadata from the source node.

**Expected Behaviour**

- Native PDF publishing builds metadata.xml through the OT executor path in Starling BaseExecutor.getMetadataList, which reads each configured property name from the source asset jcr:content/metadata node and always adds sourceProps such as UUID, last modified, damPath, and version path. RAG provenance: not available this session; grounded from inspected Starling code.
- The property names that BaseExecutor extracts come from the preset property list passed into the executor, so the Metadata tab selections flow through today while the Advanced File (Asset) properties selections do not, which matches the reported symptom that only Metadata tab values reach metadata.xml.
- damPath is already added to metadata.xml as a sourceProp for the source asset, so the customer blocker is narrower than a total absence of source metadata; the missing piece is the selected File (Asset) properties set and its correct per-asset association.
- The reference contract from GUIDES-17324 and GUIDES-17997 defines sourceProps as the basic source information for all assets across output types; Native PDF must reuse that structure rather than introduce a Native PDF only shape.
- The single attachment shows the Native PDF preset Metadata tab, the Advanced tab File (Asset) properties control populated with dc:description, dc:language, dc:title, and docstate, the Retain temporary files toggle, and an XMP RDF metadata.xml that currently reflects only the Metadata tab.

**Scope From Git**

- Lifecycle stage: Pre-Development UAC; readiness target is a UAC-ready acceptance contract, not an implementation review.
- Issue source: live Jira GUIDES-29816 fetched through the backend JiraClient; no development link, branch, or PR is present, so implementation-review evidence is not applicable.
- Product clone inspected: C:\starling on the on-disk worktree; relevant paths core/publish-workflow/src/main/java/com/adobe/fmdita/ot/BaseExecutor.java and core/publish-listener/src/main/java/com/adobe/fmdita/rest/exportditamap/ContentMetadataExporter.java were read directly. Provisional acknowledgment: the exact commit SHA was not captured and no fetch or ahead/behind comparison was run this session, so these are current-implementation-implicated claims from the local worktree, not a synchronized-revision guarantee.
- content-metadata.json belongs to the Export DITAMAP flow in publish-listener and is not the Native PDF publish artifact; the Native PDF artifact is metadata.xml written by BaseExecutor.
- Automation clones were not inspected for this pre-development pass; automation coverage is recorded as unverified rather than claimed absent.

**Code Touched**

- No code changes yet - development has not started.
- Current implementation implicated: C:\starling\core\publish-workflow\src\main\java\com\adobe\fmdita\ot\BaseExecutor.java getMetadataList builds the per-asset metadata.xml property list from the preset property names and marks source entries with setSourceProp, including the damPath entry.
- Potential code impact: the preset-to-executor property list assembly that currently omits the Advanced File (Asset) properties selection; this is inferred as the likely change point and is not a confirmed diff.

**Lines Changed**

- Not applicable - development has not started.

**Test Scenarios**

- Test data to prepare: a Native PDF preset with three variants being Metadata tab only, File (Asset) properties only, and both together; a source map with a nested submap and a reused or referenced topic; default properties such as dc:title and dc:language plus one supported custom property; a property present on one topic and absent on another; a metadata value with XML-sensitive and Unicode characters; two distinct maps Map A and Map B and two presets for isolation checks; Retain temporary files enabled so the temporary metadata.xml can be opened and read.
- P0 [AC-01, AC-03, AC-04]: Action: generate Native PDF with both the Metadata tab and File (Asset) properties set and open the retained metadata.xml. Expected: map-level and topic-level selected properties and the Metadata tab values are all present, each on the correct asset.
- P0 [AC-02, AC-10]: Action: publish a specific source map with Retain temporary files enabled and open the retained metadata.xml. Expected: the current map damPath and source identifier are present without any manual editing.
- P1 [AC-05]: Action: include a reused or nested topic in the output. Expected: each occurrence keeps its own source metadata and no cross-assignment occurs.
- P1 [AC-06]: Action: select multiple default and custom File (Asset) properties. Expected: all applicable selected properties are written to metadata.xml.
- P1 [AC-08]: Action: set a metadata value containing XML-sensitive and Unicode characters and generate output. Expected: metadata.xml is valid XML, the value is intact after parsing, and generation succeeds.
- P1 [AC-09]: Action: leave a selected property absent on one topic while present on another. Expected: generation continues, no value is fabricated or borrowed, and other metadata is still written.
- P2 [AC-11]: Action: generate for Map A, then Map B, then change the selection and regenerate. Expected: no stale carryover and the updated selection is reflected.
- P2 [AC-07]: Action: compare the generated sourceProps structure against the established metadata.xml contract. Expected: property names, values, and source association match the existing structure with no Native PDF only shape.
- P1 [AC-16]: Action: set a selected File (Asset) property value directly in CRX DE on the source asset jcr:content metadata node (not via the preset), then generate Native PDF and open the retained metadata.xml. Expected: the value in metadata.xml matches the repository node value.
- P2 [AC-14]: Action: generate PDF using a DITA-OT engine preset and confirm its metadata.xml still exposes the source map path as before. Expected: DITA-OT PDF metadata behaviour is unchanged and only the native Native PDF path is affected by the fix.
- P2 [AC-15]: Action: generate output for AEM Site, HTML5, and JSON presets before and after the change. Expected: their output is unchanged, confirming the fix is scoped to the Native PDF preset unless shared code is proven.
- P3 [Regression] [AC-12, AC-13]: Action: generate with a Metadata tab only preset and separately with a preset that has no File (Asset) properties selected. Expected: existing PDF document metadata behaviour is unchanged and generation still succeeds.

**Known Jira Bugs / Past Similar Tickets**

- No same-defect-class Jira ticket was established from validated indexed history; the sourceProps contract tickets GUIDES-17324 and GUIDES-17997 and the preset file-metadata ticket GUIDES-3704 are cited as the contract oracle in Acceptance Criteria and Expected Behaviour, not as same-mechanism defect history, because they define the expected structure rather than the same failure shape.
- Historical search status: the indexed history tool search_jira_history was not available this session; intended narrow JQL intents were an error search on metadata.xml missing File properties in Native PDF, a workflow search on Native PDF output preset Advanced File properties, and a config search on sourceProps damPath across output presets. None could be validated live, so no mutable historical status, resolution, affected version, fix version, RCA, test evidence, or impact claim is made.

**Regression Areas**

- Re-run a Native PDF publish that uses only the Metadata tab and confirm the document properties in metadata.xml are unchanged, because the fix touches the shared preset-to-executor metadata property assembly in BaseExecutor and could alter existing Metadata tab output.
- Re-run Native PDF generation for a large source map with many topics and confirm per-topic source association stays correct, because adding File (Asset) properties per asset increases the chance of a value being attached to the wrong topic during traversal.
- Re-run other publishing presets that already emit sourceProps such as AEM Site and HTML5 and confirm their metadata.xml is unaffected, because a shared change to the sourceProps assembly could regress outputs beyond Native PDF.
- Re-run a Native PDF publish with Retain temporary files enabled and confirm the temporary files still download and open, because the acceptance oracle depends on the retained metadata.xml being present and readable.

**Automation Coverage & Gaps**

- Main feature coverage: Unverified - automation clones were not synchronized or inspected in this pre-development pass, so existing coverage cannot be confirmed or denied.
- AC-01, AC-02, AC-03, AC-06, AC-07, AC-10 - Unverified: recommend a Native PDF publishing IT that generates with Retain temporary files enabled, opens the retained metadata.xml, and asserts presence, correct structure, and value fidelity of the selected File (Asset) properties for the source map, building on existing Native PDF publish IT fixtures in the dxml-it-tests suite.
- AC-04, AC-05, AC-11 - Unverified: recommend an IT that covers multiple topics, a nested submap, a reused topic, and repeated generation for different maps and presets, asserting correct per-asset association and no stale carryover.
- AC-08, AC-09 - Unverified: recommend an IT that injects XML-sensitive and Unicode values and an absent selected property, asserting valid XML, value fidelity, and safe continuation.
- AC-12, AC-13 - Unverified: recommend a regression IT that generates with a Metadata tab only preset and with no File (Asset) properties selected, asserting unchanged existing metadata behaviour.
- AC-16 - Unverified: recommend an IT that sets a metadata value directly on the asset jcr:content metadata node (repository/CRX DE) and asserts the retained metadata.xml reflects that value for the selected property.
- AC-14, AC-15 - Unverified: recommend an engine-and-preset scope IT that generates DITA-OT PDF and non-Native-PDF presets before and after the change, asserting DITA-OT and other-preset metadata output is unchanged.

**Open Questions**

- OQ-01: Which File (Asset) properties are mandatory sourceProps for every asset versus added only when selected in the Advanced tab. QA impact: this separates the always-present assertion in AC-02 from the selection-driven assertions in AC-03 and AC-06.
- OQ-02: When the same property is set on both the Metadata tab and the Advanced File (Asset) properties control, is one authoritative or are both retained. QA impact: this defines the precedence oracle for AC-01 and prevents inventing a rule.
- OQ-03: For a topic reused multiple times in a map, does metadata.xml contain one source-asset entry or one entry per processing occurrence. QA impact: this defines the association oracle for AC-05.
- OQ-04: Should the selected File (Asset) properties be written into the same XMP RDF packet that currently holds Metadata tab values or into a separate sourceProps region of metadata.xml. QA impact: this determines the exact location the tester and the customer toolkit rules read for AC-03, AC-07, and AC-10.
- OQ-05: Should a metadata property that is present on the source asset repository node but is not selected in the preset File (Asset) properties also be written to metadata.xml, or is inclusion strictly limited to the selected property names. QA impact: the current code reads only the selected names, so this decides whether a CRX DE set but unselected property is expected in the output or correctly excluded.
