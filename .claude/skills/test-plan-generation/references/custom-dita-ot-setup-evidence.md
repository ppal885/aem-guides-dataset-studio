# Custom DITA-OT setup: behaviour and UI memory

Recorded 2026-09-09 from the [requested Experience League KB](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/kb-articles/publishing/dita-ot/setup-a-custom-dita-ot), updated May 15, 2026.

This is documentation evidence, not Human approval, a product-test result or an automatic AC checklist. Use only for current-scope toolkit/profile questions. Native PDF configuration and Custom output-preset configuration are separate evidence areas.

## Retrieval anchors and behaviour

Actual readback: `aem_ingest_226b34e70a_0` and `_1`. Retrieve by source URL if IDs differ.

- `_0`: obtain the bundled archive from `/etc/fmdita/dita_resources/DITA-OT.zip`, or another toolkit version from DITA-OT; customize plug-ins and upload the ZIP under `/apps/<project-folder>/dita_resources`. The custom project folder is a recommendation, not a fixed required folder name.
- `_1`: add a DITA Profile through Tools → Guides → DITA Profiles and reference the uploaded toolkit. Uploading alone is not the whole documented setup.

## Every image inspected

One PNG was saved and opened: `media_1ca91315be40476066e02cf92da68bb14270bbe33.png`, relative to the KB directory.

The Profiles editor shows a selected custom profile. Assigned Paths scopes the configuration; AEM DITA-OT Zip Path points to its toolkit. Profile Extract Path is separate. Schema catalogs appear on the left; timeout, arguments, libraries, build/Ant, environment, plug-in and temporary-path settings appear on the right. No generation result is shown.

The pictured profile name, repository paths, toolkit version and timeout are examples, not supported-version guarantees or defaults. Exact profile matching, overlap precedence, fallback, timeout units and reload behaviour need separate evidence. Do not equate DITA Profiles with Folder Profiles or output presets. Check the target release/deployment before prescribing repository uploads.

## Vocabulary and audit boundary

`DITA Profiles` is text-backed. `Assigned Paths`, `AEM DITA-OT Zip Path` and `Profile Extract Path` are visually verified labels, not text-chunk matches. Their provenance is DOCUMENT_VERIFIED. Existing block/advisory rules remain unchanged.

Audit, readback and original image: `analysis/custom-dita-ot-setup-ingest-20260909/`. Local corpus ingestion does not update the shared VM. No toolkit was installed or AEM profile changed by this documentation task.
