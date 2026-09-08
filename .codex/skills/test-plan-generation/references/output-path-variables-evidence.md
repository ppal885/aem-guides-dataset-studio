# Output path and name variables

Recorded 2026-09-09 from [Experience League](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-variables), updated May 15, 2026. Documentation evidence, not Human approval or executed product validation.

## Behaviour and retrieval anchors

Readback IDs use prefix `aem_ingest_c7f47237c4_`; retrieve by source URL when IDs differ.

- `_0`: AEM Sites/PDF output settings accept individual or combined variables in Destination Path, Site path, AEM Site Name and PDF File Name.
- `_1`: `${map_filename}`, `${map_title}` and `${preset_name}` derive from the map filename, map title and preset name respectively.
- `_2`: `${language_code}` follows the map's language-folder location. `${map_parentpath}` supplies its full parent path.
- `_3`: `${path_after_langfolder}` supplies the path below the language folder. `${system_date}` uses the server date.
- `_4`: `${system_time}` uses server time. Map/bookmap properties under `/jcr:content/metadata` are also usable, for example `${dc:title}`.

`${map_parentpath}` and `${path_after_langfolder}` are explicitly excluded from AEM Site Name and PDF File Name (`_2`, `_3`). Do not lose these field-specific restrictions when retrieving only the introductory chunk.

## Surface and evidence boundaries

These are publishing path/name substitutions, not Native PDF Language Variable values or their fallback rules. Match the output type and target field before deciding coverage; the page does not establish support in every output format or build.

There are no article images: all-image extraction saved none; a separate successful HTML fetch found no images or picture elements in `main` and no `media_` references. Field names are text-verified, not visually verified. No dialog, panel layout or control interaction was observed.

Missing metadata, absent/ambiguous language folders, sanitization, unknown variables, collisions and evaluation timing have no defined fallback here. Investigate only when material; do not invent defaults, validation errors or automatic extra ACs. Treat sample casing, paths and date/time values as examples, not a complete formatting contract. The escaped spelling inside one path example is not alternative variable syntax.

## Vocabulary and receipt

Reuse Destination Path; add only the documented option names Site path, AEM Site Name and PDF File Name. Keep variable tokens in this reference, not as general UI names or hardcoded runtime rules. Provenance is DOCUMENT_VERIFIED, not HUMAN_APPROVED.

Local readback, append-only checks and retrieval receipts: `analysis/output-path-variables-ingest-20260909/`. Local ingestion does not update the shared VM.
