# Profile output presets: source-backed behaviour and UI memory

Source: [Manage Global and Folder Profile output presets](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/web-editor-manage-output-presets), updated May 15, 2026; ingested and visually inspected September 9, 2026.
This is documentation evidence, not Human approval, a passed product test or an
automatic AC checklist. Retrieve the relevant source and verify current ticket,
profile, role and build applicability before using it as an expectation.

## Actual chunk anchors

Suffixes use `aem_ingest_c48989faa6_`. Retrieve by exact source URL if IDs differ.

| Suffix | Behaviour or dependency to investigate |
| --- | --- |
| `_0` | Global/Folder Profile presets are available only to folder-level administrative users. Administrators manage these shared presets for maps related to the profile. This is not a blanket permission rule for ordinary map-specific presets. |
| `_1` | From a DITA map, Edit Topics opens the Editor; Open in map console leads to Output presets and the add control. Creation uses Type, Name and Target for a Knowledgebase preset. Add to folder profile makes the preset available in related maps' Output presets tabs. |
| `_2` | Profile presets are independent of maps, so map-specific configurations are not present. Generate output shows generation status, then View Output in the Success dialog. An out-of-box PDF output preset is documented. |
| `_3` | Options include Generate output, View output, View log, Rename, Duplicate and Delete. Default PDF selects an existing PDF preset used by Download as PDF for a map. Deleting a Global/Folder Profile preset removes it from all related maps' Output presets tabs. |

## Every image viewed

Both article assets were saved and opened. The SVG was safety-checked and rendered
offline for viewing; original bytes were preserved. Resolve media names relative
to the source page directory.

| Source media | Visual observation |
| --- | --- |
| `media_1800ad6965262d2eafa6ea42f14b274383b605030.png` | New output preset dialog. Type shows Select, Name is empty, Target shows a greyed Select, and Add to the current folder profile is unchecked. Cancel and a greyed Add are visible. No target choices or role selector are shown; the image alone does not explain the greyed controls. |
| `media_1f629d86fd277a188bda1414a975853f9fbd368a0.svg` | Dark globe silhouette. The accompanying prose identifies this as the folder-profile preset marker; the shape alone does not establish profile type or scope. |

## Vocabulary and evidence boundaries

- Added **Add to folder profile**, **Default PDF**, **Download as PDF** and
  **Knowledgebase preset**, bound to the actual text chunks as `DOCUMENT_VERIFIED`.
  Reuse existing **New output preset** and **Add to the current folder profile**
  for the screenshot. The prose calls it the Add preset dialog and abbreviates
  the checkbox; do not silently replace one build's label with another.
- Profile sharing and map independence are distinct from map-specific presets.
  The source does not enumerate every omitted map-specific field, define
  Global-versus-folder precedence, or show the precise global/profile selector.
- **Default PDF** does not mean Native PDF, DITA-OT PDF or FMPS equivalence.
  The page does not define fallback after deleting a default or precedence
  between multiple defaults. Keep those as investigation questions when material.
- The documented deletion propagates preset availability, not deletion of
  generated output. No cache timing, concurrent-edit resolution or upgrade
  persistence contract is established here.
- The screenshots do not demonstrate Options-menu interactions, default-PDF
  selection, generation results or validation messages. Do not claim those were
  product-tested. Do not import HTML5/Custom/Native PDF settings indiscriminately.
