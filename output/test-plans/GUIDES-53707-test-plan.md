**Understanding From Jira**
- Issue understood: When a map has a navigation-only topicref that carries a navigation title (navtitle) but no linked file (href) - a grouping heading such as "Group Heading No Href" that wraps real child topics - publishing that map to New/Native AEM Sites crashes with a NullPointerException, while Native PDF and Legacy AEM Sites publish the same map fine.
- Why it matters: A Critical, consistently reproducible production blocker; once it fails, every later New AEM Sites generation of that map keeps failing (even after the topicref is removed) until someone manually deletes the generated sites nodes, so the site cannot be updated at all. Customer context resolved from Jira: customer label Avaya, Priority Critical, component Publishing (Jira fields on GUIDES-53707).
- Requested outcome: New AEM Sites generation must succeed for a map that uses a no-href navtitle grouping topicref, must keep succeeding on repeat generations and after edits, and later map/TOC changes must take effect - without any manual node cleanup.
- Lifecycle understood as: Pre-Development UAC - the ticket is Open, fix version is Backlog, no fix or PR exists yet; current implementation is implicated from the stack trace and product-clone inspection, so PR and line-count evidence are Not applicable.
- Evidence boundary: Evidence mode: degraded - facts are from the live Jira issue fetched via the backend Jira client, its attached reproduction package npe-test (1).zip, and read-only inspection of the Starling product clone and the dxml-it-tests automation clone; title-branch behaviour is grounded in setTocItemTitle in the Starling clone; ask_dita_expert product RAG and the indexed jira history (search_jira_history) were unavailable this pass, so product-documentation and cross-customer historical claims remain unverified and DITA-spec confirmation is a VM step.
**Acceptance Criteria**
- AC-01 [Confirmed]: (Basic) Given a New AEM Sites preset and a map whose chapter contains a navigation-only grouping topicref with a navtitle and no href wrapping two href-bearing child topics | When the map is published to New AEM Sites for the first time | Then generation completes SUCCESS and the generated site navigation preserves the grouping node, showing its navigation title with the two child topics beneath it | Evidence: Jira description (Expected Result).
- AC-02 [Confirmed]: (Negative) Given the same no-href navtitle grouping map that already generated once | When the map is published to New AEM Sites a second time and on every subsequent attempt | Then each run still completes SUCCESS and the map stays regenerable so no manual deletion of generated site nodes is ever required to publish again | Evidence: Jira description (Actual Result: fails every subsequent time).
- AC-03 [Confirmed]: (Basic) Given a no-href navtitle grouping topicref whose lock-title flag is yes | When the map is published to New AEM Sites | Then the grouping node's displayed label is the authored navigation title from the locked-title branch | Evidence: source file NativeAemSitePublishing.java setTocItemTitle.
- AC-04 [Proposed]: (Negative) Given a no-href navtitle grouping topicref whose lock-title flag is no or absent, which resolve titles the same way | When the map is published to New AEM Sites | Then generation completes SUCCESS and the grouping label is produced through the fallback title-resolution path without a NullPointerException | Evidence: source file PathUtils.java appendUnixSlash.
- AC-05 [Proposed]: (Integration) Given a map already left in the failed state by an earlier pre-fix failure | When the map is regenerated after the fix without any manual cleanup | Then generation recovers and produces correct output from the already-corrupted persisted state | Evidence: Jira description (Business Impact).
- AC-06 [Proposed]: (Integration) Given a New AEM Sites preset configured to delete and recreate output | When the map is regenerated | Then the option actually clears the prior generated output for that map | Evidence: Jira description (delete and create setting have no effect).
- AC-07 [Proposed]: (Integration) Given the same no-href navtitle grouping map | When it is published to Native PDF | Then Native PDF generates successfully and renders the grouping navigation title, serving as the working comparison baseline the fix must not regress | Evidence: Jira description (Native PDF/Legacy sites generates fine).
- AC-08 [Proposed]: (Negative) Given a map with two or more sibling no-href navtitle grouping topicrefs at the same level | When the map is published to New AEM Sites | Then every grouping node generates successfully with no failure on any occurrence, not just the first | Evidence: source file NativeAemSitePublishing.java getTocItemUsingMap.
**Expected Behaviour**
- From Jira (verified): New AEM Sites publishing of the reproduction bookmap fails in ProcessGeneratedOutputStep.processNativeAemSiteOutput, caused by a NullPointerException in PathUtils.appendUnixSlash reached through the Native AEM Site TOC-building path; the first generation succeeds and subsequent ones fail until the generated sites nodes are deleted.
- From product clone (verified, provisional): In `C:\starling` the helper appendUnixSlash calls lastIndexOf on the raw path with no null check, while its sibling getNodeParentPath in the same file guards null, so a null path reaching appendPath/appendUnixSlash throws; a no-href grouping topicref is a concrete source of that null effective path.
- Title-resolution semantics (verified from clone, provisional): setTocItemTitle takes an early-return branch when lock-title is yes and navtitle is present, using the navtitle directly; otherwise it falls through to a topic-path title lookup, so lock-title yes is a distinct path while no and absent share the fallback path and are behaviourally equivalent for title display.
- Supported inference (not yet proven): whether lock-title yes also avoids the NullPointerException is unclear because the crash is in the path computation which may run independently of the title branch; treat it as an Open Question.
- Supported inference (not yet proven): the fails-until-nodes-deleted symptom indicates corrupted persistent navigation state written before or around the crash and re-read on the next run; the exact corrupted value is Unknown from current evidence.
- Whether a no-href topichead shares the same failing path is Unknown from current evidence.
**Scope From Git**
- Lifecycle stage is Pre-Development UAC and the readiness target is UAC-ready; no fix branch or PR exists (fix version Backlog).
- Issue source: live Jira GUIDES-53707 (Customer Request, Critical, component Publishing, labels Avaya / Plan_2610 / Triaged) fetched via the backend Jira client; reproduction package npe-test (1).zip downloaded and extracted (bookmap npe-book.ditamap with topics a/b/c).
- Backend clone `C:\starling` inspected read-only at branch develop, captured SHA fdfa72777a; not synced this pass with no fetch/ahead/behind performed, so all clone-derived claims are provisional and should be re-confirmed against the fix branch when it exists.
- Automation clone `C:\api automation\dxml-it-tests` inspected read-only for the three IT classes named in the Jira comments; SHA was not captured for this clone this pass, so coverage claims are provisional.
- Historical evidence was mined via live Jira JQL because the indexed history tool was unreachable; ask_dita_expert RAG was not reachable, so DITA-spec title-precedence confirmation is deferred to a VM pass.
- Figma design evidence is not applicable to this backend publishing defect.
**Code Touched**
- No code changes yet - development has not started.
- Current implementation implicated: `C:\starling\core\utils\src\main\java\com\adobe\fmdita\common\PathUtils.java` - appendUnixSlash and appendPath assume a non-null path and are the throw site; getNodeParentPath in the same file shows the null-guard pattern the fix likely needs.
- Current implementation implicated: `C:\starling\core\publish-workflow\src\main\java\com\adobe\dxml\article\publish\service\NativeAemSitePublishing.java` - getTocItemUsingMap builds each TOC item's path and title on the crashing path, and setTocItemTitle is where navtitle/lock-title/href title resolution branches.
- Current implementation implicated: `C:\starling\core\cloud-publish\src\main\java\com\adobe\aem\guides\job\ProcessGeneratedOutputStep.java` - the processNativeAemSiteOutput step reported at the top of the stack trace.
- Potential code impact (inference): the map-level guides-navigation property write/read path is the likely source of the repeat-generation persistence symptom and must be traced from the same publishing step; label this inference until confirmed against the fix.
**Lines Changed**
- Not applicable - development has not started.
**Test Scenarios**
- Test data to prepare: the attached reproduction npe-book.ditamap (bookmap id npebook; chapter -> topicref navtitle="Group Heading No Href" with NO href -> two child topicrefs GUID-9fb2d72d-d5c7-4a17-94d8-f619bb47f633.dita and GUID-8675c4ea-b762-48d8-9c20-20df545ab0e0.dita; chapter href GUID-892942f9-7402-4e66-8c4b-354646439ef5.dita); a New AEM Sites preset on an author instance; oracles are publishing job terminal state SUCCESS, no NullPointerException from PathUtils.appendUnixSlash in the log, the grouping entry present in the generated site navigation with its title, and an intact map-level guides-navigation property after each run.
- P0 [AC-01]: Action: publish the reproduction map to New AEM Sites the first time. Expected: the job succeeds and the generated navigation shows the "Group Heading No Href" grouping entry with its two child topics beneath it.
- P0 [AC-04]: Action: publish the no-href grouping map with lock-title no or absent. Expected: no NullPointerException and the grouping label is produced via the fallback path, which is the reported defect path.
- P0 [AC-02]: Action: publish the same map a second and third time without deleting anything. Expected: every run succeeds and the site updates, proving no corrupted persistent navigation state was left by an earlier run.
- P1 [AC-03]: Action: publish the no-href grouping map with lock-title yes. Expected: the grouping label is the authored navtitle from the locked-title branch.
- P1 [AC-05]: Action: starting from a map already in the failed state, regenerate after the fix without manual node deletion. Expected: generation recovers and produces correct output.
- P1 [AC-06]: Action: with the preset delete-and-recreate option enabled, regenerate. Expected: prior generated output is actually cleared.
- P1 [AC-07]: Action: publish the same map to Native PDF. Expected: it still generates and renders the grouping title as the comparison baseline.
- P2 [AC-08]: Action: build a map with two sibling no-href navtitle grouping topicrefs and publish to New AEM Sites. Expected: all grouping entries generate with no failure on any occurrence.
- P1 [AC-02]: Action: run the lifecycle sequence first publish, second publish, modify the grouping navtitle and republish, remove the grouping node and republish, then re-add it and republish. Expected: every step succeeds and the generated navigation reflects each change without manual node deletion.
- Implementation oracle (not an acceptance criterion): add a unit test for PathUtils.appendUnixSlash and appendPath with a null argument asserting no NullPointerException, mirroring the null guard already in getNodeParentPath; this internal check belongs in unit coverage, not the acceptance contract.
**Known Jira Bugs / Past Similar Tickets**
- Search status: the indexed search_jira_history tool was unreachable, so live Jira JQL was run instead - by error text (text ~ appendUnixSlash / lastIndexOf because / _path is null), by workflow (component = Publishing AND Native AEM Site AND navtitle/topicref AND fail), and by code area (text ~ guides-navigation); the three tickets below share the actual failure shape and the excluded candidates are named last.
- GUIDES-39988 - Native AEM Site publishing fails for a specific topicref href/scope shape in the map. Similarity: structural twin - same failure surface where Native AEM Site publish aborts while resolving a particular topicref href condition on the TOC/publish path, differing only in the trigger. Status: Open. Resolution: Unresolved. Affected version: 2603. Fix version: Undecided. RCA: not available in current evidence. Test evidence: not available in current evidence. Impact: strongest signal that the Native AEM Site TOC/href resolution path is fragile to topicref attribute shapes - reinforces AC-01 and AC-04.
- GUIDES-25755 - Native AEM Site publishing fails on republish of already-published content. Similarity: adjacent - same second-run/republish failure mechanism this ticket reports, on the same Native AEM Site publish path. Status: Closed. Resolution: Fixed. Affected version: 5.0. Fix version: 5.0. RCA: not available in current evidence (fixed historically; pull its commit on the VM). Test evidence: not available in current evidence. Impact: reusable oracle for the persistence side - informs AC-02, AC-05, and the lifecycle sequence.
- GUIDES-38410 - Native AEM Site generation fails when an external link is added at map level. Similarity: adjacent - same Native-AEM-Site-generation-aborts-on-a-map-construct surface, different construct. Status: Open. Resolution: Unresolved. Affected version: 2601. Fix version: Undecided. RCA: not available in current evidence. Test evidence: not available in current evidence. Impact: widens the regression net for map-construct edge cases - informs AC-07 and the null/edge-path guard.
- Excluded as different-mechanism: GUIDES-53903 (incremental-publishing failure, incremental-specific), GUIDES-24819 (parent-map data fetch hangs, a hang not a null-path crash), GUIDES-19736 (filtering removes a topicgroup, a filtering mechanism), and GUIDES-17118 (NPE in an unrelated AEM Tools navigation service user). The comment-referenced guides-29387 mapnavtitle.ditamap is existing automation, handled under Automation Coverage.
**Regression Areas**
- Highest priority: re-run New AEM Sites generation for maps that mix href-bearing topicrefs with no-href navtitle grouping nodes, because the fix touches the shared TOC path-building helper appendUnixSlash/appendPath and the setTocItemTitle branch that every Native AEM Site TOC entry flows through, so a wrong guard could drop or mis-title valid entries.
- Re-run the map-level navigation persistence path (the guides-navigation property written during Native AEM Site generation) across repeated generations, edits, and removals, because the subsequent-runs-keep-failing symptom implies a persisted-state bug a narrow null-guard fix might leave behind.
- Re-verify the lock-title title-resolution branches for grouping and normal topicrefs, because the fix sits next to that branch and could change which title is displayed.
- Re-verify Native PDF output for the same maps because it currently works and is the comparison baseline; extend to Legacy AEM Sites only if code inspection shows it shares the affected Native processing.
- Re-test the preset delete-and-recreate and incremental generation options for Native AEM Sites, because the ticket states delete-and-create currently has no effect on the failed state and the fix may alter cleanup behaviour.
**Automation Coverage & Gaps**
- Main feature coverage: Partially covered - existing navtitle AEM Site coverage does not exercise the no-href grouping case or a repeat generation.
- AC-01: Partially covered. `C:\api automation\dxml-it-tests\guides-regression\src\main\java\com\adobe\aem\guides\it\regression\tests\aemsitepublishing\AemSiteApiIT.java` test shouldGenerateAEMSiteWithNavtitleInContent publishes mapnavtitle.ditamap and asserts navtitle nodes, but its map has no no-href grouping topicref wrapping children; extend it with the reproduction map.
- AC-02: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: import the reproduction map; poll and timeout via the existing publishAemSiteWithPoller helper; assert SUCCESS on the second consecutive publish and an intact guides-navigation property; cleanup the published site nodes and imported map; tag with the aemsitepublishing regression suite; extend the existing class.
- AC-03: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: import the reproduction map with lock-title yes; poll and timeout via publishAemSiteWithPoller; assert the grouping node display name equals the authored navtitle; cleanup nodes and map; tag with the aemsitepublishing regression suite; add a test.
- AC-04: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: import the reproduction map with lock-title no or absent; poll and timeout via publishAemSiteWithPoller; assert no NullPointerException and a fallback grouping label; cleanup nodes and map; tag with the aemsitepublishing regression suite; add a test.
- AC-05: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: seed a pre-existing failed-output state via a fixture hook; poll and timeout via publishAemSiteWithPoller; assert post-fix recovery without manual node deletion; cleanup the seeded and generated nodes; tag with the aemsitepublishing regression suite; add a test.
- AC-06: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: enable the delete-and-recreate option and publish twice; poll and timeout via publishAemSiteWithPoller; assert prior output cleared on regeneration; cleanup nodes and map; tag with the aemsitepublishing regression suite; add a test.
- AC-07: Partially covered. `C:\api automation\dxml-it-tests\guides-regression\src\main\java\com\adobe\aem\guides\it\regression\tests\nativepublishing\TopicHeadNavTitleIT.java` asserts navtitle/topichead behaviour for Native PDF; extend it to publish the reproduction map as the Native PDF comparison baseline.
- AC-08: Not covered. Recipe - layer: API IT in AemSiteApiIT.java; setup: build a map with two sibling no-href grouping nodes; poll and timeout via publishAemSiteWithPoller; assert no failure and every grouping entry generated; cleanup the generated site and map; tag with the aemsitepublishing regression suite; add a multiplicity test.
**Open Questions**
- Does lock-title yes, which takes the early-return title branch, also avoid the no-href NullPointerException, or does the crash occur in the path computation regardless? QA impact: if it avoids the crash it becomes a documented workaround and a distinct passing scenario; if not, AC-03 and AC-04 share the same crash guard and the workaround must not be advertised.
- What exact persistent state is corrupted on the first failing run, and does the fix prevent the bad write, self-heal an already-corrupted map, or both? QA impact: prevent-only means AC-05 needs a fresh map, whereas self-heal requires a scenario starting from an already-failed map and an oracle for the repaired property.
- Does the identical crash occur for a no-href topichead grouping node? QA impact: if code or RAG confirms the shared path a topichead scenario is a same-priority fix; if not it is a separate ticket, kept as an investigation candidate rather than an AC.
- Is nested no-href grouping, a no-href grouping node inside another, supported and behaviourally meaningful for New AEM Sites? QA impact: if supported, add a nested-depth case to AC-08; if not, the nested case is out of scope and no scenario is needed.
- Beyond Native PDF, do Legacy AEM Sites, DITA-OT PDF, or HTML5 share the affected Native AEM Site navigation-processing code? QA impact: only presets shown by code or RAG to share the path are added as regression checks, avoiding a generic test-every-output matrix.
- Does the preset delete-and-recreate option need to change as part of this fix? QA impact: if in scope AC-06 gains a cleanup-behaviour assertion and a regression pass over incremental generation; if out of scope it becomes a separate follow-up.

# Appendix A - Automation Evidence

Existing navtitle AEM Site coverage - `C:\api automation\dxml-it-tests\guides-regression\src\main\java\com\adobe\aem\guides\it\regression\tests\aemsitepublishing\AemSiteApiIT.java` (read-only, provisional). Proves first-run navtitle nodes are asserted for a different map; does NOT cover the no-`href` grouping topicref or a second-run generation, so AC-01 is only Partially covered and AC-02 is Not covered.

```java
    public void shouldGenerateAEMSiteWithNavtitleInContent() throws IllegalAccessException,ClientException,InterruptedException{
        String mapPath = "/content/dam/guides_regression/guides-29387/mapnavtitle.ditamap";
        String aemSitePath = "/content/output/sites/mapnavtitle-ditamap";
        String aemSiteJsonPath = aemSitePath + ".2.json";
        publishAemSiteWithPoller(mapPath,aemSitePath,aemSiteJsonPath);
        JsonNode response = adminAuthor.doGetJson(aemSitePath, 2, 200);
        Assert.assertNotNull("Node 'check-nav-title' should be present in the response", response.get("check-nav-title"));
        Assert.assertNotNull("Node 'navtitle2' should be present in the response", response.get("navtitle2"));
```

Throw site - `C:\starling\core\utils\src\main\java\com\adobe\fmdita\common\PathUtils.java` (read-only develop @ fdfa72777a, provisional). Proves `appendUnixSlash` calls `lastIndexOf` on the raw path with no null guard, while `getNodeParentPath` in the same file does guard null - the guard the fix (AC-03) must add.

```java
    public static String getNodeParentPath(String _path) {
        _path = _path != null ? _path : "";
        int slashIndex = _path.lastIndexOf('/');
        return (slashIndex != -1) ? _path.substring(0, slashIndex) : "";
    }

    public static String appendPath(String path, String append) {
        return PathUtils.appendUnixSlash(path) + StringUtils.removeStartIgnoreCase(append, SLASH);
    }

    public static String appendUnixSlash(String _path) {
        int slashIndex = _path.lastIndexOf('/');
        return (slashIndex != _path.length() - 1) ? _path + SLASH : _path;
    }
```
