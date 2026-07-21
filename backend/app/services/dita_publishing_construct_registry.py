"""Registry-backed DITA-OT publishing corpus generation.

This module keeps publishing-behavior datasets deterministic and construct-driven.
Adding support for another DITA element/attribute should be a registry addition,
not a new branch in the chat or MCP routing layer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any


SUMMARY_FILENAME = "generation_summary.json"


@dataclass(frozen=True)
class PublishingDatasetIntent:
    prompt: str
    detected_constructs: list[str]
    output_format: str = "pdf"


@dataclass(frozen=True)
class ConstructSpec:
    key: str
    labels: tuple[str, ...]
    aliases: tuple[str, ...]
    map_entries: tuple[str, ...] = ()
    reltable_entries: tuple[str, ...] = ()
    files: dict[str, str] = field(default_factory=dict)
    what_was_generated: tuple[str, ...] = ()
    expected_behavior: tuple[str, ...] = ()
    qa_checklist: tuple[str, ...] = ()
    expected_pdf_review_areas: tuple[str, ...] = ()
    expected_html_review_areas: tuple[str, ...] = ()
    negative_or_risk_cases: tuple[str, ...] = ()
    validation_oracles: tuple[str, ...] = ()


def _xml_text(value: str) -> str:
    return escape(value or "", quote=False)


def _concept(topic_id: str, title: str, shortdesc: str, body: str, *, lang: str = "en-US") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="{topic_id}" xml:lang="{lang}">
  <title>{_xml_text(title)}</title>
  <shortdesc>{_xml_text(shortdesc)}</shortdesc>
  <conbody>
{body}
  </conbody>
</concept>
"""


def _searchtitle_topic() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="searchtitle-topic" xml:lang="en-US">
  <title>Primary topic title shown in authored navigation</title>
  <titlealts>
    <searchtitle>AEM Guides search-title publishing oracle</searchtitle>
  </titlealts>
  <shortdesc>This topic intentionally uses a search title that differs from the primary title.</shortdesc>
  <body>
    <section id="searchtitle-positive"><title>Positive publishing behavior</title>
      <p>The authored <xmlelement>title</xmlelement> remains the visible topic title, while <xmlelement>searchtitle</xmlelement> provides alternate title metadata for search-oriented consumers and integrations.</p>
      <p>Review HTML5 and AEM Sites output for title/search metadata and review PDF output separately; PDF body navigation should not silently replace the primary title unless a custom transform is configured to do so.</p>
    </section>
    <section id="searchtitle-risk"><title>Risk behavior</title>
      <p>An empty, misplaced, or stale <xmlelement>searchtitle</xmlelement> can make search results disagree with authored topic titles even when publishing succeeds.</p>
    </section>
  </body>
</topic>
"""


def _metadata_cascade_topic() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">
<topic id="metadata-cascade-topic" xml:lang="en-US">
  <title>Topic-level metadata cascade target</title>
  <shortdesc>This topic contains topic-level metadata that is combined with map-level topicmeta during processing.</shortdesc>
  <prolog>
    <metadata>
      <audience type="writer"/>
      <keywords>
        <keyword>topic-keyword</keyword>
      </keywords>
    </metadata>
  </prolog>
  <body>
    <section id="metadata-cascade-positive"><title>Metadata cascade behavior</title>
      <p>The map contributes <xmlelement>topicmeta</xmlelement> such as navigation title, search title, and keywords. The topic contributes <xmlelement>prolog</xmlelement> metadata.</p>
      <p>The QA oracle is to compare source map metadata, topic metadata, generated HTML metadata, and any PDF bookmarks/metadata emitted by the active transform.</p>
    </section>
    <section id="metadata-cascade-risk"><title>Risk behavior</title>
      <p>Incorrect cascade handling can drop map metadata, overwrite topic metadata unexpectedly, or use stale navigation/search titles after map context changes.</p>
    </section>
  </body>
</topic>
"""


def _dataset_display_title(intent: PublishingDatasetIntent) -> str:
    if intent.detected_constructs:
        return "DITA-OT publishing dataset for " + ", ".join(intent.detected_constructs)
    return "DITA-OT publishing smoke test"


INTRO_TOPIC = _concept(
    "publishing-dataset-overview",
    "Publishing behavior dataset overview",
    "This topic explains the generated DITA-OT publishing QA corpus.",
    """    <section id="purpose"><title>Purpose</title>
      <p>This dataset is generated from the requested DITA tags and attributes. It is intended for PDF, XHTML, and HTML5 publishing checks rather than single-topic authoring.</p>
      <p>The map, source topics, README, manifest, and generated outputs should be reviewed together as an evidence bundle.</p>
    </section>""",
)


ORACLE_TOPIC = _concept(
    "publishing-oracles",
    "Shared PDF and HTML5 publishing oracles",
    "These checks apply across all generated DITA publishing datasets.",
    """    <section id="pdf"><title>PDF oracle</title>
      <ul>
        <li>DITA-OT exits with code 0 for the <codeph>pdf</codeph> transtype.</li>
        <li>The generated PDF is non-empty and opens successfully.</li>
        <li>Expected map entries appear in TOC, bookmarks, or readable body content where the transform includes them.</li>
      </ul>
    </section>
    <section id="html5"><title>HTML5 oracle</title>
      <ul>
        <li>DITA-OT exits with code 0 for the <codeph>html5</codeph> transtype.</li>
        <li>Generated pages, links, and filenames reflect map addressing rules.</li>
        <li>Expected body markers from each generated source topic appear in output.</li>
      </ul>
    </section>""",
)


CONSTRUCT_REGISTRY: tuple[ConstructSpec, ...] = (
    ConstructSpec(
        key="copy-to",
        labels=("copy-to",),
        aliases=("copy-to", "copy to", "copyto"),
        map_entries=(
            '  <topicref href="topics/copy-source.dita" copy-to="topics/reused-copy-a.dita"><topicmeta><navtitle>Reuse instance via copy-to</navtitle></topicmeta></topicref>',
        ),
        files={
            "topics/copy-source.dita": _concept(
                "copy-source",
                "Reusable source topic for copy-to",
                "The map references this physical topic with a distinct copy-to target.",
                """    <section id="copy-to"><title>copy-to publishing effect</title>
      <p>This source should publish through an effective target such as <filepath>reused-copy-a</filepath>.</p>
      <p>The authored file remains <filepath>copy-source.dita</filepath>; <xmlatt>copy-to</xmlatt> changes the effective publishing URI, not the physical source file.</p>
    </section>""",
            ),
        },
        what_was_generated=("A reusable source topic referenced with a unique `copy-to` target.",),
        expected_behavior=("`copy-to` changes effective publishing URI/output target without renaming the physical source.",),
        qa_checklist=("Inspect the map for unique `copy-to` targets and verify the authored source remains unchanged.",),
        expected_pdf_review_areas=("PDF TOC/body should expose the copy-to instance without effective URI errors.",),
        expected_html_review_areas=("HTML5 should include a distinct copy-to target page such as `reused-copy-a.html`.",),
        negative_or_risk_cases=("Multiple refs to the same source or duplicate `copy-to` values can collide in some transforms; this corpus keeps the positive control publishable and records that risk.",),
        validation_oracles=("Generated HTML5 filenames include copy-to targets.",),
    ),
    ConstructSpec(
        key="chunk",
        labels=("chunk",),
        aliases=("chunk", "chunking"),
        map_entries=(
            '  <topicref href="topics/chunk-parent.dita" chunk="select-branch to-content">',
            '    <topicref href="topics/chunk-child-a.dita" chunk="by-topic"/>',
            '    <topicref href="topics/chunk-child-b.dita" chunk="by-topic"/>',
            "  </topicref>",
        ),
        files={
            "topics/chunk-parent.dita": _concept(
                "chunk-parent",
                "Chunk parent topic",
                "This parent branch uses valid chunk tokens only.",
                """    <section id="chunk"><title>Valid chunk values</title>
      <p>The map uses <codeph>select-branch</codeph>, <codeph>to-content</codeph>, and <codeph>by-topic</codeph>.</p>
      <p>Invalid values such as <codeph>split</codeph> and <codeph>to-navigation</codeph> must not be generated.</p>
    </section>""",
            ),
            "topics/chunk-child-a.dita": _concept(
                "chunk-child-a",
                "Chunk child A",
                "This child should be included by selected branch publishing.",
                '    <section id="marker"><title>Marker</title><p>Chunk child A output marker.</p></section>',
            ),
            "topics/chunk-child-b.dita": _concept(
                "chunk-child-b",
                "Chunk child B",
                "This child should be included by selected branch publishing.",
                '    <section id="marker"><title>Marker</title><p>Chunk child B output marker.</p></section>',
            ),
        },
        what_was_generated=("A selected branch with valid chunk tokens: `select-branch`, `to-content`, and `by-topic`.",),
        expected_behavior=("Chunk controls output boundaries and branch inclusion; invalid values are excluded.",),
        qa_checklist=("Verify no invalid chunk values such as `split` or `to-navigation` appear in generated source.",),
        expected_pdf_review_areas=("PDF should include selected branch content from chunk child topics.",),
        expected_html_review_areas=("HTML5 should generate/link chunked child-topic pages according to map boundaries.",),
        negative_or_risk_cases=("Invalid chunk tokens are a known generation risk and must be absent.",),
        validation_oracles=("Generated map/topicref `chunk` attributes never use invalid values such as `split` or `to-navigation`.",),
    ),
    ConstructSpec(
        key="xml:lang",
        labels=("xml:lang",),
        aliases=("xml:lang", "xml lang", "language", "locale"),
        map_entries=('  <topicref href="topics/french-topic.dita" xml:lang="fr-FR" chunk="by-topic"/>',),
        files={
            "topics/french-topic.dita": _concept(
                "french-topic",
                "Sujet français pour xml:lang",
                "Ce sujet vérifie la conservation du contexte de langue.",
                """    <section id="language"><title>Contrôle de langue</title>
      <p>Ce contenu utilise <codeph>xml:lang="fr-FR"</codeph> et doit rester identifiable comme contenu français dans les sorties générées.</p>
    </section>""",
                lang="fr-FR",
            ),
        },
        what_was_generated=("A French topic and topicref override using `xml:lang=\"fr-FR\"` under an English root map.",),
        expected_behavior=("`xml:lang` remains language/locale metadata and is not changed by addressing or chunking features.",),
        qa_checklist=("Compare generated output for English root-map context and French topic/topicref override.",),
        expected_pdf_review_areas=("PDF should include French content without publishing errors from language metadata.",),
        expected_html_review_areas=("HTML5 should preserve French text and language context where emitted by DITA-OT.",),
        negative_or_risk_cases=("Root map language should not incorrectly overwrite explicit topic language.",),
        validation_oracles=("Generated source includes both `en-US` root context and `fr-FR` override.",),
    ),
    ConstructSpec(
        key="searchtitle",
        labels=("searchtitle", "search title", "titlealts"),
        aliases=("searchtitle", "search title", "search-title", "titlealts", "titlealt", "title alternative"),
        map_entries=(
            '  <topicref href="topics/searchtitle-topic.dita" chunk="by-topic"><topicmeta><navtitle>Navigation title for searchtitle check</navtitle></topicmeta></topicref>',
        ),
        files={
            "topics/searchtitle-topic.dita": _searchtitle_topic(),
        },
        what_was_generated=(
            "A topic with a primary `<title>`, a distinct `<titlealts>/<searchtitle>`, and map-level `navtitle` context.",
        ),
        expected_behavior=(
            "`searchtitle` is alternate title metadata for search-oriented consumers; it should not be treated as the authored body title.",
            "AEM Sites/HTML5 metadata can expose search-title behavior, while PDF visible headings commonly continue to use the primary topic title unless customized.",
        ),
        qa_checklist=(
            "Verify the source topic contains `<titlealts><searchtitle>...` immediately after the primary title.",
            "Compare primary title, navtitle, and searchtitle so search metadata does not mask the authored title.",
        ),
        expected_pdf_review_areas=(
            "PDF visible topic heading/TOC should be checked against the primary title and navtitle, not assumed to use searchtitle.",
            "If PDF metadata or bookmarks use searchtitle in a customized pipeline, record that as transform-specific evidence.",
        ),
        expected_html_review_areas=(
            "HTML5/AEM Sites output should be inspected for page title, search metadata, and rendered heading differences.",
            "Generated HTML should still contain the topic body marker from the searchtitle test topic.",
        ),
        negative_or_risk_cases=(
            "Empty or stale search titles can make search results disagree with authored topic titles.",
            "Misplacing `<searchtitle>` outside `<titlealts>` should be treated as invalid source, not a publishing success case.",
        ),
        validation_oracles=(
            "Generated source contains `<titlealts>` and `<searchtitle>` with a value different from the primary `<title>`.",
            "QA compares generated HTML/AEM Sites search metadata separately from PDF visible-title behavior.",
        ),
    ),
    ConstructSpec(
        key="metadata-cascade",
        labels=("metadata cascading", "topicmeta", "metadata"),
        aliases=(
            "metadata cascading",
            "metadata cascade",
            "cascade",
            "cascading",
            "topicmeta",
            "lockmeta",
            "metadata",
            "prolog",
        ),
        map_entries=(
            '  <topicref href="topics/metadata-cascade-topic.dita" locktitle="yes" chunk="by-topic">',
            "    <topicmeta>",
            "      <navtitle>Map navtitle used for cascade oracle</navtitle>",
            "      <searchtitle>Map searchtitle used for metadata oracle</searchtitle>",
            "      <keywords><keyword>map-keyword</keyword></keywords>",
            "    </topicmeta>",
            "  </topicref>",
        ),
        files={
            "topics/metadata-cascade-topic.dita": _metadata_cascade_topic(),
        },
        what_was_generated=(
            "A topic with topic-level `<prolog>/<metadata>` plus a map `topicref` with `<topicmeta>`, `navtitle`, `searchtitle`, keywords, and `locktitle`.",
        ),
        expected_behavior=(
            "Metadata cascading must preserve the effective map context while keeping topic-authored metadata available to output transforms.",
            "`locktitle=\"yes\"` makes the map navigation title authoritative for navigation contexts without rewriting the topic source title.",
        ),
        qa_checklist=(
            "Inspect root map `topicmeta`, topic `prolog`, and generated output metadata together.",
            "Confirm map navigation/search metadata does not silently replace the visible topic title unless the transform explicitly does so.",
        ),
        expected_pdf_review_areas=(
            "PDF TOC/bookmarks should be reviewed for map navtitle behavior and visible body title behavior.",
            "PDF document metadata should be checked only if the active DITA-OT/AEM transform maps DITA metadata into PDF properties.",
        ),
        expected_html_review_areas=(
            "HTML5 page title, navigation text, and metadata/search fields should be compared against map `topicmeta` and topic `prolog`.",
            "Generated HTML should include the metadata cascade body marker topic.",
        ),
        negative_or_risk_cases=(
            "Missing `topicmeta`, stale `searchtitle`, or incorrect `locktitle` handling can create mismatches between navigation, search, and visible title.",
        ),
        validation_oracles=(
            "Generated source contains both map-level `<topicmeta>` and topic-level `<prolog>/<metadata>`.",
            "QA records separate PDF and HTML5 observations for navtitle, searchtitle, keywords, and visible title.",
        ),
    ),
    ConstructSpec(
        key="keys",
        labels=("keys", "keyref"),
        aliases=("keyref", "keys", "keydef", "key definition"),
        map_entries=(
            '  <keydef keys="product-name" href="topics/key-target.dita"/>',
            '  <topicref href="topics/keyref-consumer.dita" chunk="by-topic"/>',
        ),
        files={
            "topics/key-target.dita": _concept(
                "key-target",
                "AEM Guides keyed target",
                "This topic supplies the key definition target.",
                '    <section id="target"><title>Key target</title><p>This content is addressed by the <codeph>product-name</codeph> key.</p></section>',
            ),
            "topics/keyref-consumer.dita": _concept(
                "keyref-consumer",
                "Keyref consumer topic",
                "This topic uses a key reference resolved from the map.",
                '    <section id="keyref"><title>Resolved key reference</title><p>The product key resolves through <ph keyref="product-name">fallback product name</ph>.</p></section>',
            ),
        },
        what_was_generated=("A `keydef` plus a topic that consumes the key with `keyref`.",),
        expected_behavior=("Key references resolve from the effective root map context during publishing.",),
        qa_checklist=("Verify the map contains `keys=\"product-name\"` and the consumer contains `keyref=\"product-name\"`.",),
        expected_pdf_review_areas=("PDF should render the keyref consumer without unresolved-key text or fatal errors.",),
        expected_html_review_areas=("HTML5 should render/link the key target and consumer consistently.",),
        negative_or_risk_cases=("Missing key definitions produce unresolved references; this corpus includes the positive control keydef.",),
        validation_oracles=("DITA-OT exits successfully with the key definition map context.",),
    ),
    ConstructSpec(
        key="conkeyref",
        labels=("conkeyref",),
        aliases=("conkeyref", "conkeyrefs", "conkey reference"),
        map_entries=(
            '  <keydef keys="reuse-key" href="topics/conkeyref-source.dita"/>',
            '  <topicref href="topics/conkeyref-consumer.dita" chunk="by-topic"/>',
        ),
        files={
            "topics/conkeyref-source.dita": _concept(
                "conkeyref-source",
                "Conkeyref source topic",
                "This topic provides a keyed reusable element.",
                '    <section id="reuse"><title>Reusable keyed content</title><p id="reuse-para">Reusable paragraph resolved through conkeyref.</p></section>',
            ),
            "topics/conkeyref-consumer.dita": _concept(
                "conkeyref-consumer",
                "Conkeyref consumer topic",
                "This topic resolves reusable content through the map key context.",
                '    <section id="consumer"><title>Conkeyref resolution</title><p conkeyref="reuse-key/reuse-para">fallback conkeyref paragraph</p></section>',
            ),
        },
        what_was_generated=("A keyed reusable source and a consumer using `conkeyref=\"reuse-key/reuse-para\"`.",),
        expected_behavior=("`conkeyref` resolves reusable content through the effective map key space, so map context matters.",),
        qa_checklist=("Verify the key definition and `conkeyref` target ID agree before blaming PDF/HTML transforms.",),
        expected_pdf_review_areas=("PDF should show the keyed reusable paragraph in the consumer topic.",),
        expected_html_review_areas=("HTML5 should show the keyed reusable paragraph in the consumer page.",),
        negative_or_risk_cases=("Missing keys, wrong element IDs, or changed key scopes can make conkeyref fail only in specific map contexts.",),
        validation_oracles=("Generated output contains `Reusable paragraph resolved through conkeyref`.",),
    ),
    ConstructSpec(
        key="conref",
        labels=("conref", "conkeyref"),
        aliases=("conref", "conkeyref", "content reference"),
        map_entries=(
            '  <topicref href="topics/conref-source.dita" processing-role="resource-only"/>',
            '  <topicref href="topics/conref-consumer.dita" chunk="by-topic"/>',
        ),
        files={
            "topics/conref-source.dita": _concept(
                "conref-source",
                "Conref source topic",
                "This topic owns reusable phrase content.",
                '    <section id="reuse"><title>Reusable content</title><p id="reuse-phrase">Reusable phrase resolved through conref.</p></section>',
            ),
            "topics/conref-consumer.dita": _concept(
                "conref-consumer",
                "Conref consumer topic",
                "This topic pulls phrase content from a same-topic target so the positive control remains publishable.",
                """    <section id="source"><title>Same-topic conref source</title><p id="reuse-phrase">Reusable paragraph resolved through conref.</p></section>
    <section id="consumer"><title>Conref resolution</title><p conref="#conref-consumer/reuse-phrase">fallback conref paragraph</p></section>""",
            ),
        },
        what_was_generated=("A conref source marker and consumer reference with a same-topic `conref` positive control.",),
        expected_behavior=("DITA-OT resolves conref before final output generation.",),
        qa_checklist=("Verify the conref consumer contains `conref=\"#conref-consumer/reuse-phrase\"` and output resolves the reusable paragraph.",),
        expected_pdf_review_areas=("PDF should show resolved reusable paragraph content, not fallback-only text.",),
        expected_html_review_areas=("HTML5 should show resolved reusable paragraph content in the consumer page.",),
        negative_or_risk_cases=("Broken target IDs cause unresolved conrefs; this corpus provides a valid control target.",),
        validation_oracles=("Generated output contains `Reusable paragraph resolved through conref`.",),
    ),
    ConstructSpec(
        key="conref-range",
        labels=("conrefend", "conref range"),
        aliases=("conrefend", "conref range", "range conref", "range reference"),
        map_entries=('  <topicref href="topics/conref-range-consumer.dita" chunk="by-topic"/>',),
        files={
            "topics/conref-range-consumer.dita": _concept(
                "conref-range-consumer",
                "Conref range consumer topic",
                "This topic includes source range markers and a range conref control.",
                """    <section id="range-source"><title>Range source</title>
      <p id="range-start">Range start paragraph for conrefend checks.</p>
      <p id="range-middle">Range middle paragraph for conrefend checks.</p>
      <p id="range-end">Range end paragraph for conrefend checks.</p>
    </section>
    <section id="range-consumer"><title>Range consumer</title>
      <p conref="#conref-range-consumer/range-start" conrefend="#conref-range-consumer/range-end">fallback range conref paragraph</p>
    </section>""",
            ),
        },
        what_was_generated=("A same-topic range conref using both `conref` and `conrefend`.",),
        expected_behavior=("`conrefend` extends a conref to an inclusive range; target ordering and element compatibility are critical.",),
        qa_checklist=("Verify range start/end IDs are ordered and compatible before treating output differences as renderer bugs.",),
        expected_pdf_review_areas=("PDF should show the range content or expose a clear DITA-OT range-resolution diagnostic if the transform rejects it.",),
        expected_html_review_areas=("HTML5 should preserve resolved range content or expose the same range-resolution diagnostic.",),
        negative_or_risk_cases=("Crossing structural boundaries or using incompatible start/end elements can create invalid effective content.",),
        validation_oracles=("Source contains both `conref=` and `conrefend=` on the same control element.",),
    ),
    ConstructSpec(
        key="conrefpush",
        labels=("conrefpush", "conaction"),
        aliases=("conrefpush", "conref push", "conaction", "pushbefore", "pushafter", "pushreplace"),
        map_entries=(
            '  <topicref href="topics/conrefpush-target.dita" chunk="by-topic"/>',
            '  <topicref href="topics/conrefpush-source.dita" processing-role="resource-only"/>',
        ),
        files={
            "topics/conrefpush-target.dita": _concept(
                "conrefpush-target",
                "Conrefpush target topic",
                "This topic owns the target element that pushed content addresses.",
                '    <section id="target"><title>Push target</title><p id="push-target">Original target paragraph for conrefpush.</p></section>',
            ),
            "topics/conrefpush-source.dita": _concept(
                "conrefpush-source",
                "Conrefpush source topic",
                "This resource-only topic carries push actions for preprocess inspection.",
                """    <section id="push-source"><title>Push source</title>
      <p conaction="pushbefore" conref="conrefpush-target.dita#conrefpush-target/push-target">Pushed paragraph before target.</p>
      <p conaction="mark" conref="conrefpush-target.dita#conrefpush-target/push-target"/>
    </section>""",
            ),
        },
        what_was_generated=("A `conrefpush` control pair using `conaction=\"pushbefore\"` and `conaction=\"mark\"`.",),
        expected_behavior=("Conref push changes effective processed content during preprocessing, not the authored target file.",),
        qa_checklist=("Inspect DITA-OT temp/effective content when pushed content is missing or appears in the wrong place.",),
        expected_pdf_review_areas=("PDF should be checked for pushed content placement near the original target paragraph.",),
        expected_html_review_areas=("HTML5 should be checked for pushed content placement near the original target paragraph.",),
        negative_or_risk_cases=("Push actions can be silently confusing when target IDs move, map context filters resources, or push order changes.",),
        validation_oracles=("Source contains `conaction=\"pushbefore\"`, `conaction=\"mark\"`, and a concrete target `conref`.",),
    ),
    ConstructSpec(
        key="xref",
        labels=("xref", "cross reference"),
        aliases=("xref", "xrefs", "cross reference", "cross-reference", "href link"),
        map_entries=(
            '  <keydef keys="xref-product-name" href="topics/xref-target.dita"/>',
            '  <topicref href="topics/xref-target.dita" chunk="by-topic"/>',
            '  <topicref href="topics/xref-consumer.dita" chunk="by-topic"/>',
        ),
        files={
            "topics/xref-target.dita": _concept(
                "xref-target",
                "Xref target topic",
                "This topic provides topic and section targets for xref checks.",
                '    <section id="target-section"><title>Target section</title><p>Xref target section marker.</p></section>',
            ),
            "topics/xref-consumer.dita": _concept(
                "xref-consumer",
                "Xref consumer topic",
                "This topic contains local, section, external, and keyed cross references.",
                """    <section id="links"><title>Xref link controls</title>
      <p><xref href="xref-target.dita">Local topic xref</xref></p>
      <p><xref href="xref-target.dita#xref-target/target-section">Local section xref</xref></p>
      <p><xref href="https://www.dita-ot.org/" scope="external" format="html">External HTML xref</xref></p>
      <p><xref keyref="xref-product-name">Keyed xref text</xref></p>
    </section>""",
            ),
        },
        what_was_generated=("Local topic, local section, external, and keyed `xref` controls.",),
        expected_behavior=("Xrefs resolve against the effective output location; copy-to, chunking, keys, scope, and format can change final link targets.",),
        qa_checklist=("Verify local, section, external, and keyed links separately in generated HTML5 and PDF.",),
        expected_pdf_review_areas=("PDF should show link text and preserve clickable/link semantics where supported by the renderer.",),
        expected_html_review_areas=("HTML5 should generate correct relative links for local and section xrefs, plus external URL behavior.",),
        negative_or_risk_cases=("Broken href fragments, wrong scope/format, and copy-to relocation can produce links that look correct in source but fail after preprocessing.",),
        validation_oracles=("Generated source includes `href`, section fragment, `scope=\"external\" format=\"html\"`, and `keyref` xref variants.",),
    ),
    ConstructSpec(
        key="scope-format",
        labels=("scope", "format"),
        aliases=("scope", "format", "external link", "external links"),
        map_entries=('  <topicref href="topics/scope-format-links.dita" chunk="by-topic"/>',),
        files={
            "topics/scope-format-links.dita": _concept(
                "scope-format-links",
                "Scope and format link topic",
                "This topic validates internal and external link publishing behavior.",
                """    <section id="links"><title>Link behavior</title>
      <p><xref href="https://www.dita-ot.org/" scope="external" format="html">DITA-OT external link</xref></p>
      <p><xref href="publishing-oracles.dita" scope="local" format="dita">Local DITA link to shared oracle</xref></p>
    </section>""",
            ),
        },
        what_was_generated=("A topic with local and external xrefs using `scope` and `format`.",),
        expected_behavior=("`scope` and `format` guide generated link handling for local DITA and external HTML targets.",),
        qa_checklist=("Inspect generated links for local-vs-external behavior.",),
        expected_pdf_review_areas=("PDF should render external link text and local oracle link text without broken-link failures.",),
        expected_html_review_areas=("HTML5 should preserve external URL behavior and local link navigation.",),
        negative_or_risk_cases=("Incorrect scope/format can create broken links or wrong output assumptions.",),
        validation_oracles=("Generated source includes both `scope=\"external\" format=\"html\"` and `scope=\"local\" format=\"dita\"`.",),
    ),
    ConstructSpec(
        key="map-attributes",
        labels=("map attributes", "topicref attributes"),
        aliases=(
            "map attributes",
            "map attrs",
            "topicref attributes",
            "topicref attrs",
            "navtitle",
            "locktitle",
            "toc",
            "linking",
            "collection-type",
            "print",
            "type attribute",
        ),
        map_entries=(
            '  <topicref href="topics/map-attribute-topic.dita" navtitle="Locked map title" locktitle="yes" toc="yes" linking="normal" print="yes" collection-type="sequence" type="concept" format="dita" scope="local" processing-role="normal"/>',
        ),
        files={
            "topics/map-attribute-topic.dita": _concept(
                "map-attribute-topic",
                "Topic title overridden by map attributes",
                "This topic validates common map and topicref publishing attributes.",
                '    <section id="map-attrs"><title>Map attribute marker</title><p>Map attributes control navigation, linking, print inclusion, type hints, and title locking.</p></section>',
            ),
        },
        what_was_generated=("A topicref using common map attributes: `navtitle`, `locktitle`, `toc`, `linking`, `print`, `collection-type`, `type`, `format`, `scope`, and `processing-role`.",),
        expected_behavior=("Map/topicref attributes influence navigation, linking, print inclusion, collection semantics, and output titles from the map context.",),
        qa_checklist=("Inspect TOC/bookmarks/navigation for locked navtitle and verify the topic remains publishable.",),
        expected_pdf_review_areas=("PDF TOC/bookmarks should prefer locked map title where the transform honors `locktitle`.",),
        expected_html_review_areas=("HTML5 navigation should include the topic and preserve expected map-driven title/link behavior.",),
        negative_or_risk_cases=("Wrong `format`, `scope`, `processing-role`, or `locktitle` assumptions can make content appear missing or mislabeled only after publish.",),
        validation_oracles=("Root map contains a single topicref with the common map attribute matrix.",),
    ),
    ConstructSpec(
        key="processing-role",
        labels=("processing-role",),
        aliases=("processing-role", "resource-only", "resource only"),
        map_entries=(
            '  <topicref href="topics/resource-only.dita" processing-role="resource-only"/>',
            '  <topicref href="topics/processing-role-consumer.dita" chunk="by-topic"/>',
        ),
        files={
            "topics/resource-only.dita": _concept(
                "resource-only",
                "Resource-only topic",
                "This topic is present for processing but should not become normal navigation content.",
                '    <section id="resource"><title>Resource marker</title><p>Resource-only marker.</p></section>',
            ),
            "topics/processing-role-consumer.dita": _concept(
                "processing-role-consumer",
                "Processing role consumer",
                "This topic validates resource-only behavior.",
                '    <section id="consumer"><title>Consumer marker</title><p>Normal navigation content should include this consumer topic.</p></section>',
            ),
        },
        what_was_generated=("A `processing-role=\"resource-only\"` topicref plus a normal consumer topic.",),
        expected_behavior=("Resource-only references are available to processing but should not appear as normal navigation topics.",),
        qa_checklist=("Compare source map entries with generated navigation to ensure resource-only behavior is respected.",),
        expected_pdf_review_areas=("PDF should include the consumer topic and should not promote the resource-only topic as normal content.",),
        expected_html_review_areas=("HTML5 navigation should include the consumer topic and avoid normal navigation for resource-only content.",),
        negative_or_risk_cases=("Resource-only content accidentally appearing in navigation is a regression risk.",),
        validation_oracles=("Generated source includes exactly one `processing-role=\"resource-only\"` topicref.",),
    ),
    ConstructSpec(
        key="conditional-processing",
        labels=("conditional processing", "DITAVAL attributes"),
        aliases=(
            "conditional processing",
            "conditional attributes",
            "branch filtering",
            "branch filter",
            "profiling",
            "profile",
            "ditaval",
            "audience",
            "@audience",
            "platform",
            "@platform",
            "product",
            "@product",
            "props",
            "@props",
            "otherprops",
            "@otherprops",
            "rev",
            "@rev",
        ),
        map_entries=('  <topicref href="topics/conditional-processing.dita" audience="admin" platform="windows" product="aem-guides" chunk="by-topic"/>',),
        files={
            "topics/conditional-processing.dita": _concept(
                "conditional-processing",
                "Conditional processing topic",
                "This topic exercises common profiling attributes used with DITAVAL.",
                """    <section id="profiled"><title>Profiled content</title>
      <p audience="admin" platform="windows" product="aem-guides" props="publishing" otherprops="dita-ot" rev="r1">Admin Windows AEM Guides publishing marker.</p>
      <p audience="author" platform="linux" product="dita-ot" props="authoring" otherprops="html5" rev="r2">Author Linux DITA-OT HTML5 marker.</p>
    </section>""",
            ),
            "filters/admin-windows.ditaval": """<?xml version="1.0" encoding="UTF-8"?>
<val>
  <prop att="audience" val="author" action="exclude"/>
  <prop att="platform" val="linux" action="exclude"/>
  <prop att="product" val="dita-ot" action="exclude"/>
</val>
""",
        },
        what_was_generated=("A profiled topic plus a sample DITAVAL filter for `audience`, `platform`, and `product`.",),
        expected_behavior=("Conditional processing filters profiled content during preprocessing when a DITAVAL filter is passed to DITA-OT.",),
        qa_checklist=("Run with and without `filters/admin-windows.ditaval` when testing actual filtering behavior.",),
        expected_pdf_review_areas=("PDF should be reviewed for included/excluded profiled paragraphs when a filter is used.",),
        expected_html_review_areas=("HTML5 should be reviewed for included/excluded profiled paragraphs when a filter is used.",),
        negative_or_risk_cases=("Missing filter arguments, inherited map profiling attrs, or conflicting props can make filtered content look like a transform bug.",),
        validation_oracles=("Source contains `audience`, `platform`, `product`, `props`, `otherprops`, `rev`, and a DITAVAL filter file.",),
    ),
    ConstructSpec(
        key="mapref",
        labels=("mapref",),
        aliases=("mapref", "nested map", "submap"),
        map_entries=('  <mapref href="submap.ditamap" format="ditamap"/>',),
        files={
            "submap.ditamap": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">
<map id="submap" xml:lang="en-US">
  <title>Nested submap</title>
  <topicref href="topics/submap-topic.dita"/>
</map>
""",
            "topics/submap-topic.dita": _concept(
                "submap-topic",
                "Nested map topic",
                "This topic is pulled into the root deliverable through a mapref.",
                '    <section id="submap"><title>Submap marker</title><p>Nested map output marker.</p></section>',
            ),
        },
        what_was_generated=("A nested `submap.ditamap` referenced by root-map `mapref`.",),
        expected_behavior=("Map references include subordinate map content in the effective publication context.",),
        qa_checklist=("Verify root map references `submap.ditamap` and output includes the nested topic marker.",),
        expected_pdf_review_areas=("PDF should include nested submap topic content.",),
        expected_html_review_areas=("HTML5 should include/link the nested submap topic output.",),
        negative_or_risk_cases=("Incorrect mapref format/path can drop nested content.",),
        validation_oracles=("Generated output contains `Nested map output marker`.",),
    ),
    ConstructSpec(
        key="reltable",
        labels=("reltable",),
        aliases=("reltable", "relationship table", "relrow", "relcell"),
        map_entries=(
            '  <topicref href="topics/reltable-a.dita" chunk="by-topic"/>',
            '  <topicref href="topics/reltable-b.dita" chunk="by-topic"/>',
        ),
        reltable_entries=(
            "  <reltable>",
            "    <relheader><relcolspec type=\"concept\"/><relcolspec type=\"concept\"/></relheader>",
            "    <relrow><relcell><topicref href=\"topics/reltable-a.dita\"/></relcell><relcell><topicref href=\"topics/reltable-b.dita\"/></relcell></relrow>",
            "  </reltable>",
        ),
        files={
            "topics/reltable-a.dita": _concept(
                "reltable-a",
                "Reltable source A",
                "This topic participates in a relationship table.",
                '    <section id="a"><title>A marker</title><p>Reltable A marker.</p></section>',
            ),
            "topics/reltable-b.dita": _concept(
                "reltable-b",
                "Reltable source B",
                "This topic participates in a relationship table.",
                '    <section id="b"><title>B marker</title><p>Reltable B marker.</p></section>',
            ),
        },
        what_was_generated=("A relationship table connecting two concept topics.",),
        expected_behavior=("Relationship tables can generate related-links behavior depending on transform configuration.",),
        qa_checklist=("Verify both reltable participant topics publish and relationship markup is valid.",),
        expected_pdf_review_areas=("PDF should publish both topics without reltable validation failures.",),
        expected_html_review_areas=("HTML5 should publish both topics; related links may appear depending on DITA-OT configuration.",),
        negative_or_risk_cases=("Invalid reltable cells or missing targets can break related-link generation.",),
        validation_oracles=("Root map contains a valid `reltable` with two `relcell` targets.",),
    ),
)


def detect_publishing_constructs(prompt: str) -> list[str]:
    text = (prompt or "").lower()
    detected: list[str] = []
    for spec in CONSTRUCT_REGISTRY:
        if any(re.search(rf"(?<![a-z0-9_-]){re.escape(alias)}(?![a-z0-9_-])", text) for alias in spec.aliases):
            detected.append(spec.key)
    if "keyref" in text and "keys" not in detected:
        detected.append("keys")
    if (
        re.search(r"\b(branch[-\s]?filter(?:ing)?|profil(?:e|ing)|ditaval|conditional\s+processing)\b", text)
        and re.search(r"\b(all|every)\s+(?:the\s+)?attributes?\b", text)
    ):
        for key in ("conditional-processing", "map-attributes", "chunk", "xml:lang"):
            if key not in detected:
                detected.append(key)
    return detected


def detect_output_format(prompt: str, default: str = "pdf") -> str:
    text = (prompt or "").lower()
    wants_pdf = bool(re.search(r"\b(pdf|pdf2)\b", text))
    wants_html = bool(re.search(r"\b(html5|html|xhtml|classic\s+html)\b", text))
    if "all" in text or (wants_pdf and wants_html):
        return "all"
    if "html5" in text:
        return "html5"
    if re.search(r"\b(html|xhtml|classic\s+html)\b", text):
        return "html"
    if wants_pdf:
        return "pdf"
    return default


def _canonical_output_format(output_format: str | None) -> str | None:
    value = (output_format or "").strip().lower()
    if value in {"both", "all"}:
        return "all"
    if value in {"pdf", "pdf2"}:
        return "pdf"
    if value in {"html5", "html", "xhtml"}:
        return value
    return None


def build_publishing_intent(prompt: str, output_format: str = "auto") -> PublishingDatasetIntent:
    requested_output = _canonical_output_format(output_format)
    return PublishingDatasetIntent(
        prompt=prompt or "DITA-OT publishing dataset",
        detected_constructs=detect_publishing_constructs(prompt),
        output_format=requested_output or detect_output_format(prompt, default="pdf"),
    )


def _unique_specs(constructs: list[str]) -> list[ConstructSpec]:
    by_key = {spec.key: spec for spec in CONSTRUCT_REGISTRY}
    return [by_key[key] for key in constructs if key in by_key]


def build_publishing_corpus(work_dir: Path, title: str, output_format: str = "auto") -> dict[str, Any] | None:
    intent = build_publishing_intent(title, output_format=output_format)
    specs = _unique_specs(intent.detected_constructs)
    if not specs:
        return None

    display_title = _dataset_display_title(intent)
    safe_title = _xml_text(display_title)
    topics_dir = work_dir / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)

    files: dict[str, str] = {
        "topics/publishing-dataset-overview.dita": INTRO_TOPIC,
        "topics/publishing-oracles.dita": ORACLE_TOPIC,
    }
    map_entries = [
        '  <topicref href="topics/publishing-dataset-overview.dita" chunk="by-topic"/>',
    ]
    reltable_entries: list[str] = []
    for spec in specs:
        map_entries.extend(spec.map_entries)
        reltable_entries.extend(spec.reltable_entries)
        files.update(spec.files)
    map_entries.append('  <topicref href="topics/publishing-oracles.dita" chunk="to-content"/>')
    map_entries.extend(reltable_entries)

    map_name = "publishing-construct-dataset.ditamap"
    map_path = work_dir / map_name
    map_path.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "map.dtd">',
                '<map id="publishing-construct-dataset" xml:lang="en-US">',
                f"  <title>{safe_title}</title>",
                *map_entries,
                "</map>",
                "",
            ]
        ),
        encoding="utf-8",
    )

    for relative_path, content in files.items():
        path = work_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    source_files = [map_name, *sorted(files)]
    what_was_generated = [
        "One root DITA map with `xml:lang=\"en-US\"`.",
        "A shared overview topic and shared PDF/HTML5 oracle topic.",
        *[item for spec in specs for item in spec.what_was_generated],
    ]
    expected_behavior = [item for spec in specs for item in spec.expected_behavior]
    qa_checklist = [
        "Confirm DITA-OT exits with code 0 for every requested format.",
        "Open the ZIP and verify the root map, README, manifest, and generated topics are present.",
        *[item for spec in specs for item in spec.qa_checklist],
    ]
    expected_pdf_review_areas = [
        "PDF should open successfully, be non-empty, and include expected generated content.",
        *[item for spec in specs for item in spec.expected_pdf_review_areas],
    ]
    expected_html_review_areas = [
        "HTML/HTML5 output should open successfully and include expected generated pages/content.",
        *[item for spec in specs for item in spec.expected_html_review_areas],
    ]
    negative_or_risk_cases = [item for spec in specs for item in spec.negative_or_risk_cases]
    validation_oracles = [
        "All generated XML files parse as well-formed XML.",
        "DITA-OT publish commands complete for requested outputs.",
        *[item for spec in specs for item in spec.validation_oracles],
    ]
    summary = {
        "title": "Spec-driven DITA-OT publishing dataset",
        "detected_constructs": intent.detected_constructs,
        "what_was_generated": what_was_generated,
        "source_files": source_files,
        "expected_behavior": expected_behavior,
        "qa_checklist": qa_checklist,
        "expected_pdf_review_areas": expected_pdf_review_areas,
        "expected_html_review_areas": expected_html_review_areas,
        "negative_or_risk_cases": negative_or_risk_cases,
        "validation_oracles": validation_oracles,
        "recommended_user_next_step": "Download the ZIP, inspect the root map for detected constructs, then review PDF and HTML5 outputs against the listed oracles.",
        "confidence_contract": [
            "Success means DITA-OT produced every requested output and core artifact oracles passed.",
            "Manual QA still needs to inspect PDF/HTML navigation, generated links, and transform-specific rendering details.",
        ],
        "formats_requested": [intent.output_format],
        "input_map": str(map_path),
    }

    (work_dir / "README.md").write_text(_render_readme(safe_title, summary, map_name), encoding="utf-8")
    source_files.append("README.md")
    summary["source_files"] = sorted(source_files)
    (work_dir / SUMMARY_FILENAME).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"map_path": map_path, "summary": summary}


def _render_readme(title: str, summary: dict[str, Any], map_name: str) -> str:
    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values)

    return f"""# {title}

This corpus was generated by the spec-driven DITA-OT publishing dataset builder.

## Detected constructs

{bullets(summary.get("detected_constructs") or [])}

## What was generated

{bullets(summary.get("what_was_generated") or [])}

## QA checklist

{bullets(summary.get("qa_checklist") or [])}

## PDF review areas

{bullets(summary.get("expected_pdf_review_areas") or [])}

## HTML/HTML5 review areas

{bullets(summary.get("expected_html_review_areas") or [])}

## Commands

```bash
dita --input={map_name} --format=pdf --output=publish/pdf
dita --input={map_name} --format=xhtml --output=publish/xhtml
dita --input={map_name} --format=html5 --output=publish/html5
```
"""
