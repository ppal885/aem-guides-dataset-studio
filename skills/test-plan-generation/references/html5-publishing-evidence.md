# HTML5: source-backed behaviour and UI memory

Source: [Use HTML5](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/generate-output-html5), updated July 28, 2026; ingested and inspected September 9, 2026.
Documentation evidence only: not Human approval, an automatic AC checklist, or a
passed product test. Match current Jira scope, deployment, version and engine first.

## Actual chunk anchors

All suffixes below use `aem_ingest_b69c4e51a8_`. Retrieve by source URL if IDs are
unavailable. `_15` is footer material, not behaviour evidence.

| Suffix | Behaviour or dependency to retrieve |
| --- | --- |
| `_0`–`_5` | Map console creation uses DITA-OT. Map dashboard also documents administrator-configured FMPS. General/Advanced are console tabs; dashboard fields differ. |
| `_1`, `_2`, `_11`, `_14` | Conditions, condition presets, baselines and health checks depend on map/folder-profile setup. Health-check findings are informational, not publication blockers. |
| `_6` | Output location depends on administrator-configured `${base_output_path}`. |
| `_7` | From release 2502, outside-map content requires explicit `-Dgenerate.copy.outer=3`. |
| `_8` | Unspecified output filename falls back to map title, then map filename; configured sanitization applies. |
| `_10`–`_11` | First matching DITAVAL wins; FMPS cannot use multiple DITAVAL files. Moved/deleted references need manual updates; non-DITAVAL selection errors. Flagging is supported. |
| `_12` | Post-generation workflow runs after generation; custom transformations require an integrated DITA-OT plugin. |
| `_13` | Retained ZIP includes `system_config.xml` externalization URLs; selected file properties add `metadata.xml`. |
| `_14` | Flattening puts content in one folder; otherwise hierarchy is preserved. File properties propagate selected map/bookmap metadata. |

## Every image viewed

Three unique source assets were saved and opened, including both SVG icons rendered
offline for viewing. No image was inferred from its filename. Resolve media names
relative to the source page directory.

| Source media | Visual observation |
| --- | --- |
| `media_174da43a92a29b54a02da222a61dac04cfd005e88.png` | New output preset dialog: Type is HTML5, Name contains HTML5 preset, Generate HTML5 Using is DITA-OT. Add to the current folder profile is unchecked. Cancel and Add are visible. |
| `media_1f629d86fd277a188bda1414a975853f9fbd368a0.svg` | Dark globe silhouette; the accompanying prose identifies the folder-profile preset marker. It is not a folder-shaped icon. |
| `media_150d64b1888f53184c9d69c8fecf242f7e1b53a28.svg` | Document with folded corner and zip fastener; the prose associates it with downloading retained temporary files. |

## Exact vocabulary and boundaries

- Prose: **Generate HTML Using**, **Add to current folder profile**. Screenshot:
  **Generate HTML5 Using**, **Add to the current folder profile**. Both variants
  are source-backed; neither proves the target build's exact label.
- Console **Output path** corresponds to dashboard **Destination Path**. Dashboard
  engine selection is **Generate Responsive Using**. Do not infer console FMPS
  availability from the dashboard instructions.
- **Conditional filtering** appears in `_1`; `_9` contains a malformed label.
  Do not promote that typo into vocabulary. Existing **Apply Conditions Using**
  remains separate from the console label.
- Other added terms are **HTML5 output preset**, **DITA-OT**, **FrameMaker Publishing
  Server**, publishing **Map dashboard**, **Transformation name**, **Flatten file
  hierarchy**, and **Download temporary files**. Generic button/field labels were
  not added. Terms and source IDs/images are recorded in `guides_vocabulary.json`.
- No dashboard screenshot, generated-output screenshot, runtime interaction or
  engine-equivalence test is supplied by these images. They do not establish
  hidden dropdown choices, defaults beyond the shown state, or exact error text.
- Keep Native PDF preprocessing, PDF conformance and comparison change bars out
  of HTML5 claims unless separate current evidence establishes them. Preserve the
  governing condition with each retrieved option; do not accept a detached chunk
  as proof that a conditional setting is always available.
