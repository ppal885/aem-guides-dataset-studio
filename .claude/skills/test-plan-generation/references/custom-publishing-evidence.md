# Custom publishing: source-backed behaviour and UI memory

Source: [Custom](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/generate-output-custom), updated July 28, 2026; ingested and inspected September 9, 2026.
This is documentation evidence, not Human approval, a passed product test or an
automatic AC checklist. Apply only to current scope and verify the target plugin,
configuration and build. Do not infer Native PDF or FMPS equivalence.

## Actual chunk anchors

Suffixes use `aem_ingest_abb689fe11_`. Retrieve by the exact source URL if IDs differ.

| Suffix | Behaviour or dependency to retrieve |
| --- | --- |
| `_0`, `_5`, `_6` | Custom publishing uses an integrated custom DITA-OT plug-in and its transformation name; extra DITA-OT arguments are configurable. |
| `_1`–`_4` | Console General/Advanced organization differs from dashboard creation. Conditions and baselines depend on map setup. |
| `_2` | Folder-profile health-check configuration controls toggle visibility; findings are informational, not output blockers. |
| `_6` | Blank output filename falls back to map title, then map filename; configured sanitization applies. |
| `_7`–`_9` | Earlier DITAVAL files take precedence for matching conditions. Moved/deleted references need updates; wrong file types error. Condition presets require existing map configuration. |
| `_10` | Administrator-defined base output location; retained temporary ZIP; selected properties add `metadata.xml`. See the EPUB inconsistency below. |
| `_11`–`_12` | Workflow runs after generation; existing baseline selects a publish version; map/bookmap file properties supply selected metadata. Ignore the trailing footer. |

## Every image viewed

All five source assets were saved and opened. The SVG was rendered offline; the tiny
download PNG was enlarged for inspection. Original bytes remain intact. Resolve
media names relative to the source page directory.

| Source media | Visual observation |
| --- | --- |
| `media_1d916565a45ad911c8c97ad3587b8e074ed0ac0fb.png` | New output preset dialog: Custom type, Custom preset name, unchecked Add to the current folder profile. Cancel and a greyed Add control are visible. The image does not explain why Add is disabled. |
| `media_164c31c497fe23eb29c6daba2928934a76962a806.png` | Map console, Output presets, selected Custom preset, General selected and Advanced visible. Shows arguments, required-marked Transformation name and Output path, File name, None/Using DITAVAL choices and Post generation workflow toggle. File name contains `${map_filename}_${preset_name}`; Output path contains `${base_output_path}/epub`. These are shown values, not universal defaults. |
| `media_1fd149e52d168dac1f8da655b971ab948521d75dd.png` | Map dashboard Output Presets form with Custom selected. Shows arguments, Transformation Name, File Name, Destination Path, Retain temporary files, Apply Conditions using, Run post generation workflow, Use Baseline and Properties. Baseline area is greyed and says No Baselines created. Destination Path displays `${base_output_path}/epub`. |
| `media_1f629d86fd277a188bda1414a975853f9fbd368a0.svg` | Dark globe silhouette; page prose identifies the folder-profile preset marker. |
| `media_196349ecf0408f30151d0240aafcb1489409c24e1.png` | Tiny document/archive icon with folded corner and zip detail; page prose identifies Download temporary files. |

## Vocabulary and evidence boundaries

- Added terms: **Custom output preset**, **custom DITA-OT plug-in**, and dashboard
  **Run post generation workflow**. The last names a checkbox; **Post Generation
  Workflow** names the dependent selection. Neither introduces a per-run workflow
  object. Exact provenance is in `guides_vocabulary.json` as `DOCUMENT_VERIFIED`.
- Reuse existing **New output preset**, **Transformation name**, **Output path** /
  **Destination Path**, **Conditional filtering** / **Apply Conditions Using**,
  **Retain temporary files**, **Use Baseline**, and **File properties**. Dashboard
  **Properties** is the documented counterpart of console **File properties**;
  do not add generic words or duplicate case-only variants to vocabulary.
- `_10` calls the destination EPUB output; both screenshots show an `/epub` path.
  Preserve this inconsistency rather than silently correcting source chunks or
  asserting that Custom always generates EPUB. The plugin/transformation defines
  the intended output; a path alone is not an output-type contract.
- Screenshot filename expressions and the prose's blank-name fallback describe
  different states. Do not substitute the screenshot value for the fallback rule.
- Hidden condition-preset/health-check controls are conditional, not disproved by
  the supplied screenshot. No Advanced-tab contents, dropdown interactions,
  generated output or exact validation error strings were demonstrated in images.
- Do not import HTML5 flattening or its release-specific outside-map setting,
  Native PDF options, FMPS restrictions, or `system_config.xml` guarantees from
  other pages. Retrieve separate applicable evidence if those questions matter.
