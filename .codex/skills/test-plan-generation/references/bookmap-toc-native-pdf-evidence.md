# Native PDF bookmap TOC: source-backed memory

Recorded 2026-09-09. Documentation evidence, not Human approval or a tested release contract. Investigate only current-ticket scope; never auto-add ACs.

## Sources and retrieval

- [Requested KB](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/kb-articles/publishing/native-pdf/how-to-include-bookmap-toc-in-pdf-publishing), updated May 15, 2026; ingested and read back as `aem_ingest_c1a9c3ee4d_0` through `_3`.
- [Template settings clarification](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/components-pdf-template#page-order), independently checked online, not newly ingested by this task.

Retrieve the exact KB URL with the changed behaviour. `_0` covers placement; `_1` generation; `_2` layout, ordering and ordinary-map controls. `_3` contains resource links, not extra behaviour.

## Behaviour boundaries

- A bookmap requests a TOC through `<booklists>/<toc>` in `<frontmatter>` or `<backmatter>`. Related list elements include `<figurelist>`, `<tablelist>` and `<indexlist>`.
- Native PDF follows bookmap structure for TOC/list sequence. A dedicated layout and `layout.css` control presentation, not that sequence.
- Ordinary DITA maps use template controls for automatic TOC inclusion. The template-settings source explicitly limits ordering/inclusion controls to DITA maps, excluding bookmaps. It also says Chapters & Topics cannot be toggled off.
- Template settings document TOC layout fallback: selected Front Matter Pages, then Default Page Layout when no dedicated TOC/front-matter layout is selected. Do not infer an empty TOC or publishing failure from a missing dedicated layout.

## Every extracted image viewed

Both assets were opened, not inferred from filenames. Asset URLs are relative to the KB directory.

1. `media_10d72a6698f4a158b381cbb5e700aa00a765e5565.png`: template Page Layouts settings; TOC layout mapping highlighted. Other dropdowns map chapter, figure/table-list, index and glossary layouts. This is not the output preset.
2. `media_15405e6210a73a2f7ca79e7de317f71b73d646983.png`: template Settings → Page Layout Order; TOC and figure-list switches on, table-list/index/glossary switches off; drag handles and merge controls visible. These are example states, not defaults.

## Limits

The KB's full-bookmap example has unbalanced chapter tags; do not reuse it as a validated fixture. No PDF was generated. Missing-list behaviour, duplicate TOCs, and DITA-OT PDF-engine equivalence are not established. Verify current-build labels. New vocabulary is DOCUMENT_VERIFIED, not a Human-approved lesson.

Audit/readback/images: `analysis/bookmap-toc-ingest-20260909/`. Local ingestion does not update the shared VM corpus.
