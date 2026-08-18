# RAG Ingestion Pipeline — Gaps & Test-Plan-Skill Improvements

Grounded in the live `AEM_GUIDES` Chroma collection (593 chunks) after ingesting SOURCE-1..4,
and in the Native-PDF dependency extraction. Every gap below is observed, not hypothetical.

## What the pipeline stores today (observed)

Metadata keys actually present across the 593 chunks:

| key | # chunks | note |
|---|---|---|
| `url`, `title` | 593 | on every chunk |
| `source_url`, `chunk_index`, `chunk_content_hash`, `content_hash`, `source_type`, `corpus`, `canonical_url`, `parser_version` | 567 | only on the curated SOURCE-1..4 ingest |
| (none of the above except url/title) | 26 | earlier bulk-ingested chunks — degraded schema |

Chunk size: min 10 chars, max 998, avg 819 (fixed-size `RecursiveCharacterTextSplitter`).

## Gaps found

**G1 — No queryable output-family / preset facet.** No chunk carries `output_type`,
`publishing_family`, `content_type`, `authority`, `product`, `domain`, `heading_path`, or
`dita_version`. The Native-vs-DITA-OT distinction exists only *implicitly* inside `source_url`,
so retrieval cannot apply a metadata `where` filter. This is the direct cause of the observed
contamination: **"DITA-OT PDF command-line arguments" surfaced a NATIVE_PDF chunk first**
(0.403) ahead of the true DITA_OT_PDF chunks (0.409, 0.437). Pure embedding similarity cannot
separate "Native PDF that documents optional DITA-OT preprocessing" from "the DITA-OT PDF
engine" — only a metadata facet can.

**G2 — Earlier bulk ingest used a thinner schema ("aise ingest nahi kiye").** The 26 pre-existing
chunks have only `url`+`title`: no `source_url`, no content hash, no `chunk_index`, no
`source_type`/`corpus`/`parser_version`. Consequences: they cannot be content-hash de-duplicated,
cannot be attributed to an output family, cannot be filtered, and cannot be re-ingested
idempotently. They are second-class evidence in the same collection.

**G3 — Fixed-size chunking severs conditional/dependency statements.** The Condition Preset
coupling ("… *This option is visible if you have added a condition for the DITA map*") straddled a
chunk boundary, and the DITA-OT-preprocessing → command-line-argument *enabling* sentence never
surfaced verbatim (the `-Dargs.rellinks` / `-Dpreprocess.*` tokens landed in a different chunk
from their governing toggle). The splitter is not heading/section-aware, so `OPTION_VISIBLE_WHEN`
/ `OPTION_ENABLED_WHEN` couplings get split apart — RAG can return the option *or* its condition
but not the dependency.

**G4 — No structured dependency-extraction stage.** The pipeline only produces prose chunks. The
QE-critical structure (option → dependency → state branches) is discarded; it had to be extracted
by hand into [native_pdf_dependency_map.json](native_pdf_dependency_map.json). There is no step
that emits `OPTION_VISIBLE_WHEN` / `OPTION_ENABLED_WHEN` / `OPTION_REQUIRES` /
`OPTION_CONTROLS_BEHAVIOR` records.

**G5 — Noise + encoding.** Tiny nav/menu fragments (min 10 chars, e.g. a bare breadcrumb list)
are ingested as content and dilute rankings. Bullet glyphs render as replacement chars (Unicode
not normalized during HTML cleanup).

**G6 — No pipeline-emitted manifest / authority tier.** The per-source ingestion manifest and the
`authority` classification were produced by hand this turn; the pipeline does not emit either, so
the skill's evidence-authority resolver cannot rank product-doc vs implementation vs historical
from metadata.

## How this improves the test-plan skill

The skill's `references/dita-spec-evidence.md` already mandates cross-output disambiguation and
treats all publishing presets as regression scope — but that protocol is **undermined by G1/G3**:
an `ask_dita_expert` / `lookup_aem_guides` probe for a publishing ticket can silently retrieve the
*wrong engine's* behaviour (Native vs DITA-OT) and yield a wrong Expected-Behaviour bullet or AC
verdict. Concrete, prioritized improvements:

| # | Improvement | Effort | Payoff |
|---|---|---|---|
| I1 (P0) | Add `output_type` + `content_type` + `authority` metadata facets at ingest; expose a retrieval helper that filters by output family. | M | Kills G1 contamination; makes the skill's cross-output disambiguation enforceable, not hopeful. |
| I2 (P0) | Skill reference note: when probing publishing behaviour, **scope the probe to the exact preset** and reject cross-family hits — until I1 lands, disambiguate by `source_url`. | S | Immediate; no pipeline change. |
| I3 (P1) | Heading/section-aware chunking (keep an option and its governing condition in one chunk; overlap across option boundaries). | M | Fixes G3 so dependency couplings are retrievable. |
| I4 (P1) | Add a dependency-extraction post-step emitting `OPTION_*` records; feed them to `state_compatibility_explorer` + `semantic_relationship_explorer`. | M | Fixes G4; turns docs into state/dependency test evidence. |
| I5 (P2) | Backfill the 26 legacy chunks (re-ingest their URLs through the curated path) and drop <40-char noise chunks; normalize Unicode. | S | Fixes G2/G5; uniform schema. |

**Anti-hardcoding note:** none of the above hardcodes option names. The dependency map is consumed
as *run-time evidence*; the retrieval facets are generic (output family / content type / authority),
not per-option rules. The Native-vs-DITA-OT distinction is preserved as a metadata facet, exactly
the semantic separation flagged earlier.
