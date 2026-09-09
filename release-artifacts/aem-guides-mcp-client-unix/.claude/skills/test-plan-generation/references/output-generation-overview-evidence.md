# Output generation overview

Recorded 2026-09-09 from [Experience League](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output), updated May 15, 2026. Documentation evidence, not Human approval or executed product validation.

## Behaviour and retrieval anchors

Local readback IDs use `aem_ingest_57c1930e9c_`; retrieve by source URL on other indexes.

- `_0`: Guides lists AEM Sites, PDF, HTML5, EPUB, JSON and custom output, with DITA-OT, Native PDF and FMPS as publishing mechanisms. It describes whole-map publishing, publishing selected updated topics, and Baseline selection of map/topic versions.
- `_1`: Output generation supports LwDITA maps/topics. Publish Dashboard provides a view of queued/running tasks and cancellation/termination. Publishing automation uses post-publishing workflows. Templates customize layouts; custom DITA-OT plug-ins can reuse PDF publishing processes.
- `_2`: The described features require Publishers or administrator privileges. Links lead to output presets, condition presets, Baseline, map console generation, Map Collection, task management and troubleshooting.

The privilege paragraph is separate from the dashboard paragraph. Retrieve both when assessing role-sensitive task management.

Observed local retrieval limitation: a source-filtered top-2 query about publishing privileges returned `_0` and `_1`, omitting `_2`. Source URL alone is not proof that the needed rule was retrieved. Read the missing paragraph or expand the bounded source readback before deciding role coverage; do not report the initial query as sufficient.

## UI and source boundaries

Publish Dashboard is a text-verified publishing surface. The page also uses Publishing Dashboard; this does not establish a synonym for Map dashboard or Bulk Publish dashboard. LwDITA names a supported content type, not a panel. Reuse existing Baseline, Map Collection and engine vocabulary.

All-image extraction saved zero images. Independent HTTP 200 HTML inspection found no article images, pictures, video, iframe or SVG elements, and no `media_` image references. There is no screenshot to view or UI layout to describe from this page.

## Use as discovery, not an automatic checklist

Select only the branch relevant to the changed behaviour. Example retrieval questions:

- Which output engine and input content type are involved?
- Does this path publish a whole map, selected topics, or a Baseline version?
- Which task action and user privileges apply?

The overview does not specify an engine-format matrix, per-format selective publishing support, cancellation timing/cleanup, exact terminal states, unknown-input fallback, or a complete role matrix. Resolve these with the linked detailed source and current implementation when material. Do not equate post-publishing workflows with another similarly named control without evidence.

For task details, follow the page's [Publish Dashboard link](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-publish-dashboard). This link is a discovery lead; that article was not ingested or reviewed in this task.

## Provenance and index boundary

Publish Dashboard and LwDITA are DOCUMENT_VERIFIED vocabulary, not HUMAN_APPROVED new rules. No AC, gate relaxation or learned-probe promotion is created.

Local append/readback, image inventory and fresh VM-backed RAG evidence are in `analysis/output-generation-ingest-20260909/`. The VM query returned this exact source before any VM ingestion. Local chunk IDs and counts are not VM IDs or corpus-parity proof; avoid duplicate VM ingestion without a source inventory check.
