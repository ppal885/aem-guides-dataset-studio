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
        validation_oracles=("Source grep for `split` and `to-navigation` returns no matches.",),
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


def build_publishing_intent(prompt: str, output_format: str = "pdf") -> PublishingDatasetIntent:
    return PublishingDatasetIntent(
        prompt=prompt or "DITA-OT publishing dataset",
        detected_constructs=detect_publishing_constructs(prompt),
        output_format=detect_output_format(prompt, default=output_format or "pdf"),
    )


def _unique_specs(constructs: list[str]) -> list[ConstructSpec]:
    by_key = {spec.key: spec for spec in CONSTRUCT_REGISTRY}
    return [by_key[key] for key in constructs if key in by_key]


def build_publishing_corpus(work_dir: Path, title: str, output_format: str = "pdf") -> dict[str, Any] | None:
    intent = build_publishing_intent(title, output_format=output_format)
    specs = _unique_specs(intent.detected_constructs)
    if not specs:
        return None

    safe_title = _xml_text(title)
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
