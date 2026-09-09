# RAG Query Cookbook

Use this file before calling or judging `ask_dita_expert`.

## Query Set

Run focused queries from normalized behaviour:

- **Exact failure**: `<Jira key or exact error/user symptom> in AEM Guides <area/workflow>`
- **Exact API/config/UI/construct**: `<api path/config key/UI label/DITA construct> <expected verb> <boundary term>`
- **Expected workflow**: `How should <workflow> behave in AEM Guides when <condition/config/version> applies?`
- **Boundary/config**: `What are the rules for <configuration/permission/version/data-shape> in <workflow>?`
- **Regression**: `Which nearby AEM Guides workflows can be affected by <changed area/API/component>?`

Always run at least three probes for behaviour-sensitive tickets:

- Exact probe with the precise API route, config key, UI label, DITA element/attribute, error text, or release version.
- Workflow probe with the user action and expected product surface.
- Boundary probe with platform, role, version, config, data-shape, or output/preset constraints.

If the first probe is noisy, tighten the query with exact tokens instead of broad prose. For example, prefer `ignored.post.processing.paths enabled.post.processing.paths rules child successors same folder ignored wins` over a long generic question about folder postprocessing.

For DITA questions:

- Ask for the exact element or attribute name.
- Include the output/channel if relevant: AEM Sites, Native PDF, PDF2, HTML5, translation, review, baseline, map dashboard, editor.
- Do not accept an attribute chunk as proof for an element, or generic DITA docs as proof for AEM Guides UI behaviour.

## Accept Evidence When

- It names the same workflow, element, attribute, configuration, release note, API, UI area, or product feature.
- It explains expected behaviour, constraints, side effects, permissions, or version boundaries.
- It directly changes a scenario, expected result, regression area, or AC interpretation.
- It has a credible source title/URL or clear corpus origin from the VM RAG response.
- It appears in top results with exact feature/API/config/source overlap, not just broad semantic similarity.
- For release behaviour, it is the latest matching current doc unless the Jira is explicitly about an older release, upgrade, or regression history.

## Reject Evidence When

- It only matches broad words such as `topic`, `map`, `assets`, `metadata`, `cloud`, `workflow`, `translation`, `baseline`, or `report`.
- It describes a different product surface than the Jira/PR.
- It is generic DITA/DITA-OT guidance but the claim is about AEM Guides UI/AEM Sites behaviour.
- It is release-note text that does not mention the affected behaviour or nearby component.
- It conflicts with Jira facts or inspected PR diff.
- It is an older release note that only matches generic product terms while newer/current docs cover the same area more directly.
- It names a related feature area but not the exact API/config/UI/DITA behaviour being claimed.

## How To Use RAG In The Plan

- Convert accepted RAG into short behaviour facts, not citations dumps.
- Put supported facts under `Expected Behaviour` or coverage impact under `Regression Areas`.
- If RAG does not support the claim, write `Unknown from current evidence` or `Draft blocker: RAG did not confirm expected behaviour`.
- Never phrase unsupported RAG as certainty.
- If RAG returns mixed useful and noisy chunks, keep only the exact-matching chunks and say unrelated chunks were rejected internally.
- If all top chunks are generic release-note or validation-oracle text, mark RAG as noisy and do not use it as behaviour proof.

## Output-Family Disambiguation (publishing tickets)

For Native PDF template, preset, or environment evidence, consult
`references/native-pdf-publishing-evidence.md`: it records the exact Experience League
sources, chunk anchors, every inspected image, and source/version limitations. Retrieve
only the applicable facts; it is not a mandatory list of acceptance criteria.

For HTML5 output presets, use `references/html5-publishing-evidence.md` to locate
the relevant chunks and inspected UI labels. Preserve the console/dashboard field
mapping, engine restrictions, and version-dependent outside-map content setting;
do not transfer Native PDF behaviour into HTML5 because the field names overlap.

For Custom DITA-OT presets, use `references/custom-publishing-evidence.md`. Retrieve
the integrated-plugin/transformation relationship, not just a shared option name.
The Custom page's EPUB wording is a source inconsistency, not proof of output format
or default destination; inspect the target plugin and configuration when relevant.

For custom toolkit deployment and DITA Profiles, use `references/custom-dita-ot-setup-evidence.md`.
Retrieve the uploaded toolkit and profile assignment separately from output-preset settings.
Profile scope, toolkit compatibility and fallback require their own evidence; screenshot
values are not defaults, and DITA Profiles are not Folder Profiles.

For publishing path/name substitutions, use `references/output-path-variables-evidence.md`.
Retrieve the variable's permitted target fields as well as its value source. Do not import
Language Variable fallback rules or infer undocumented handling of missing metadata.

For publishing scope or task management, use `references/output-generation-overview-evidence.md`.
Retrieve the requested output/engine and the relevant detailed source after the overview.
Its Publish Dashboard and LwDITA references are discovery anchors, not proof that every
engine supports every output, selective-publishing path or cancellation outcome. Retrieve
the separate privilege paragraph when roles matter; it is absent from the dashboard chunk.

For Map Collection, use `references/map-collection-publishing-evidence.md`. Retrieve
membership/locale association, preset enablement, generation selection, queued/running
restrictions and bulk metadata separately as relevant. Query Document State common
allowed choices and File Properties synchronization when metadata is affected. Nearby
New Map Collection results are not interchangeable evidence; collection membership
removal does not establish repository deletion. One source hit is not full-page coverage.

For Native PDF TOC and booklist questions, use `references/bookmap-toc-native-pdf-evidence.md`.
Retrieve source-structure ordering separately from template layout selection and ordinary
DITA-map inclusion controls. Do not infer bookmap control support from a matching label
or turn a documentation example into a validated DITA fixture.

For shared Global/Folder Profile presets, use
`references/profile-output-presets-evidence.md`. Retrieve profile-level role and
map-independence rules separately from map-specific settings. Default PDF / Download
as PDF names a preset selection, not a publishing-engine equivalence or fallback.

For condition-preset management and selection, use `references/condition-presets-evidence.md`.
Retrieve default-action scope and duplicate naming with their console/dashboard section
context. Condition presets are not the authoring Conditions panel or DITAVAL editor;
the source's dashboard-section naming inconsistency must not become invented UI parity.

The AEM Guides RAG corpus co-locates multiple publishing engines that share vocabulary, so
embedding similarity alone can return the WRONG engine's behaviour. This is observed, not
theoretical: a probe for "DITA-OT PDF command-line arguments" ranks a Native-PDF chunk first,
because the Native-PDF page documents *optional* DITA-OT preprocessing. Native PDF using DITA-OT
preprocessing is NOT the DITA-OT PDF engine — do not treat one as evidence for the other.

- When the claim is about a specific output preset, name the preset in the probe AND verify each
  accepted chunk's source is that preset (check the chunk `source_url` / title): AEM Sites
  (`aem-site...`), PDF overview (`generate-output-pdf`), DITA-OT PDF (`...-pdf-dita-ot`), Native
  PDF (`native-pdf-web-editor`), HTML5.
- Reject a chunk from a different output family even if its similarity score is high. A Native-PDF
  chunk mentioning `-Dargs.*` / `-Dpreprocess.*` is evidence about Native-PDF's optional
  preprocessing, not about the DITA-OT PDF engine's own arguments.
- For configuration dependencies (an option that is visible/enabled only under a condition), the
  governing toggle and the dependent option may sit in different chunks. Retrieve both and state
  the coupling; do not assert an option's availability without its controlling condition. See the
  worked dependency records in `analysis/native_pdf_dependency_map.json` (consume as run-time
  evidence — never hardcode option names). Known couplings to look for generically:
  `OPTION_VISIBLE_WHEN`, `OPTION_ENABLED_WHEN`, `OPTION_REQUIRES`, `OPTION_CONTROLS_BEHAVIOR`.
- Metadata gap (why this is manual today): current chunks carry only `source_url`/`title`, not an
  `output_type` facet, so a `where` filter is not yet possible; disambiguate by `source_url` until
  the ingest adds an output-family facet. Tracked in `analysis/rag_ingestion_gaps.md`.

## Good vs Noisy Examples

For output-preset edit/duplicate/delete questions, consult
`references/output-preset-actions-evidence.md` and retrieve the exact management-page
source. Keep console field editing/Options separate from dashboard top-bar actions.
The template-preset administrator restriction is not a rule for every preset;
the page does not specify duplication naming, copied state, or deletion side effects.

Good:

- Jira is about postprocessing path enable/ignore rules, and RAG returns exact rules for `ignored.post.processing.paths` and `enabled.post.processing.paths`.
- Jira is about AEM Guides release behaviour, and RAG returns a matching release note or upgrade instruction.
- Jira is about a DITA element, and RAG returns the exact element reference and valid parent/child rules.

Noisy:

- Jira is about metadata schema editing, and RAG returns a generic assets metadata overview without edit behaviour.
- Jira is about AEM Sites title rendering, and RAG returns only DITA `<title>` or `<searchtitle>` syntax with no AEM Sites mapping.
- Jira is about an API regression, and RAG returns only UI workflow documentation.
