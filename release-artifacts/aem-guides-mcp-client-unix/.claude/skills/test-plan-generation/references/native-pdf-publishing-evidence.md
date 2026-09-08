# Native PDF: source-backed behaviour and UI memory

Recorded 2026-09-09 from all four requested pages, actual `aem_guides` chunk readback,
and visual inspection of every extracted image. This is documentation evidence and
terminology guidance, not Human feedback, a release-independent contract, or proof
that a product test passed. Follow current Jira scope; investigate only relevant
behaviours. Never turn this reference into an automatic AC checklist.

## Source ledger and retrieval anchors

| Source | Actual ingested IDs | What the page establishes |
| --- | --- | --- |
| [Template/content-styles overview](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/output-gen-config/config-native-pdf-publish/template-content-styles) | `aem_ingest_0862a326e8_0`–`_1` | Native PDF can publish a topic or map; templates combine layout, CSS and localized strings. It is a navigation hub, not the detailed contract for every linked style feature. |
| [Publishing essentials session](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/expert-session/native-pdf-publishing-essentials-feb23) | `aem_ingest_7c6d0ba00a_0`–`_1` | A session landing page with a recording link, not a transcript. The session is dated February 2023; its demonstrated features are scoped to on-prem 4.2+ and Cloud 2211+. No video-only behaviour was inferred. |
| [Environment configuration KB](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/kb-articles/publishing/native-pdf/configuring-aem-environment-for-native-pdf-publishing) | `aem_ingest_795bdb98ce_0`–`_7` | Legacy OS/Java-dependent setup and troubleshooting. The manual Linux node-module workaround is limited to 4.1 or earlier; 4.2+ skips it. Recheck supported versions before applying setup advice. |
| [Native PDF output preset](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/output-presets-aemg/pdf-preset/native-pdf-web-editor) | `aem_ingest_5494c3c9c9_0`–`_33` | Preset controls and their dependencies; retrieve the relevant chunks below with their source URL. |

Ingest IDs identify this append-only snapshot, not universal IDs after another crawl.
If an ID is unavailable, retrieve by the exact source URL plus the scoped terms.

## Preset behaviour: retrieval map

Suffixes below belong to `aem_ingest_5494c3c9c9_`.

- `_2`–`_4`: Map console creation; folder-profile health checks produce informational logs.
- `_8`–`_10`: filename defaults; multiple DITAVAL selection, invalid-file handling, condition-dependent preset visibility.
- `_11`–`_13`: comparison baselines and added/deleted-text styling. Do not conflate version comparison with DITAVAL flagging.
- `_14`: **cross-reference text** language resolves topic `xml:lang`, then preset, then `en_US`. Do not extend this to every language-variable fallback.
- `_15`: arguments require preprocessing. Native PDF with optional DITA-OT preprocessing is not the DITA-OT PDF engine.
- `_17`–`_20`: map, XMP or explicit metadata; localized values.
- `_21`–`_24`: template selection; viewer defaults; owner-password-dependent restrictions.
- `_25`–`_27`: from 5.0/2025.02.0, configure printing in the preset; retained template settings no longer apply. CMYK PDF/A requires an ICC profile.
- `_28`–`_33`: accessibility, PDF merging, embedding permissions, compression, MathML, temporary HTML and `system_config.xml`, conformance and configurable metadata propagation.

## Every image inspected

Media filenames below are source provenance; descriptions come from opening the
images, not guessing from filenames or alt text. All URLs resolve relative to the
corresponding source page's directory. Nine unique media assets were saved and viewed;
the information icon appears twice on the preset page. Three SVGs were rasterized
offline for inspection, without changing their source bytes.

### Overview and session

Neither page contains an article image. The session contains a video link; it was
not treated as a viewed recording or an extracted UI screenshot.

### Environment KB: four images

1. `media_1218bb7295f7745a7b7c5caa1a605add61e2d6887.png`: terminal showing a Node REPL loading a Java bridge and printing classpath/native-binding information. This is an environment diagnostic, not an Editor panel.
2. `media_12d0339b807616a90128e88a6f28e93190f34101c.png`: yellow stack-trace image showing a null-pointer failure through publishing and workflow code. It does not show a user-facing error dialog.
3. `media_1c134f132fdf42ae2b45bf284730b96d44632f9de.png`: terminal library/ABI loading error and module-loader stack. It is not a missing-content warning in Guides.
4. `media_1a9cfda28d7aff668bee91fa04066c16e140c1ede.png`: publishing log with HTML merging, PDF transformation, output-copy/completion lines and a timeout message. A screenshot of these lines does not prove successful output or a universal timeout contract.

### Output preset: five images

1. `media_1f629d86fd277a188bda1414a975853f9fbd368a0.svg`: globe icon; the article uses it to identify folder-profile presets. It is not a separate dashboard.
2. `media_119bf770f0f8779490ce0608ff301f12e9ead5eae.png`: **Map console → Output presets**, with a Native PDF preset selected. General is selected beside Metadata, Layout, Security, Print and Advanced. Visible controls include output path, separate-PDF toggle, PDF filename, conditional filtering, DITAVAL browsing and language. Other preset types in the list do not establish their behaviour here.
3. `media_1e8f847bc6a8f65c4166574095ad0380c12a34d27.png`: Metadata section with three radio choices: map metadata, XMP, or explicit names/values. The selected explicit mode shows a property table using metadata variables and literal text.
4. `media_110da843a7d2aff7b2596b507f706f013fae31b3b.svg`: circular information icon. No hover tooltip contents are shown by the asset itself.
5. `media_1d9aa6d39e15eb27c44dd1ef6bee6c888a0d0d0bb.svg`: folder with magnifier, used for template browsing. The selection dialog itself is described in text, not pictured by this icon.

## Terminology and evidence limits

The 22 new `canonical_terms` are listed with URL/chunk provenance in
`data/guides_vocabulary.json` under `canonical_term_sources`. They are document-vetted
names, not new blocking rules or Human-approved lessons. Existing block/advisory rules
and synonyms are unchanged. Existing PDF template/layout/style vocabulary is reused.

- Screenshot labels and prose differ: the General image says **Conditional filtering**;
  the text uses **Apply Conditions Using**. Metadata's first radio label also differs
  from the prose. Verify the current UI before prescribing an exact click target.
- The preset article contains a DITA-OT engine-name slip in its Native PDF tab description
  and a duplicated argument note beneath Post Generation Workflow. Do not derive engine
  equivalence or an argument-input workflow control from those inconsistencies.
- The KB mixes platform examples, includes a questionable resource path and an example
  profile identifier. Do not copy its commands into a repair, generalize that identifier,
  invent timeout units, or turn preset recreation advice into a "stale preset" mechanism.
- Windows settings, terminal output and Acrobat properties are external surfaces, not
  new Guides product vocabulary. No Sites/Forms terms were added. The preset's interactive
  PDF option is not evidence for the separate AEM Forms product.
- The overview's links are leads for later retrieval; their child pages were not ingested
  by this task. Configuration KB screenshots do not establish the current build's UI.

Local audit/readback/image files are under `analysis/native-pdf-ingest-20260909/`.
The Chroma corpus is gitignored: syncing the skill or pushing Git does not index the VM.
