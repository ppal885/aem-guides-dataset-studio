#!/usr/bin/env python3
"""Insert fn, note, ol, param, longdescref, longquoteref entries into dita_spec_seed.json."""
import json
from pathlib import Path

SEED_PATH = Path(__file__).parent / "app" / "storage" / "dita_spec_seed.json"

NEW_ENTRIES = [
    {
        "element_name": "fn_element",
        "content_type": "element",
        "text_content": (
            "The <fn> element is a footnote placed in the body of a topic. It produces a "
            "superscript reference at the point of insertion and renders the footnote text at "
            "the bottom of the page (PDF) or as a popup/endnote (HTML).\n\n"
            "Content model: inline and block content (text, ph, keyword, xref, p, ol, ul, dl, "
            "pre, codeblock, note, image).\n\n"
            "Contained by: most inline and block contexts (p, li, entry, ph, title, shortdesc, "
            "dd, fig, note, section, abstract, lq, stentry, etc.).\n\n"
            "Key attributes:\n"
            "- @id: used for cross-referencing the footnote\n"
            "- @callout: custom callout symbol (default is auto-numbered)\n\n"
            "Use-conref pattern: define a <fn> once with an @id, then reuse it elsewhere "
            "with <xref type='fn' href='#topicid/fnid'/>.\n\n"
            "Example:\n"
            "```xml\n"
            "<p>DITA supports content reuse<fn id=\"fn-reuse\">Content reuse includes "
            "conref, conkeyref, keyref, and topicref-based reuse.</fn> "
            "across multiple publications.</p>\n"
            "```\n\n"
            "Processing: in PDF output, footnotes appear at the bottom of the page. "
            "In HTML-based output, they typically appear as endnotes or tooltips."
        ),
        "parent_element": "p, li, entry, ph, title, shortdesc, dd, fig, note, section, abstract, lq, stentry",
        "children_elements": "ph, keyword, xref, p, ol, ul, dl, pre, codeblock, note, image",
        "attributes": '{"id": "footnote identifier for xref", "callout": "custom callout symbol"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/fn"
        }
    },
    {
        "element_name": "note_element",
        "content_type": "element",
        "text_content": (
            "The <note> element provides information that expands on or calls attention to a "
            "particular point within a topic. The @type attribute controls the visual rendering.\n\n"
            "Content model: block and inline content (text, p, ol, ul, dl, pre, codeblock, "
            "simpletable, table, fig, image, note, ph, keyword, xref).\n\n"
            "Contained by: body, bodydiv, section, sectiondiv, example, p, li, itemgroup, dd, "
            "fig, stentry, draft-comment, fn, entry, abstract, linklist, linkinfo, lq.\n\n"
            "Key attribute - @type (controls icon/styling):\n"
            "- note (default): general information\n"
            "- tip: helpful suggestion\n"
            "- important: important information\n"
            "- remember: reminder\n"
            "- restriction: constraint or limitation\n"
            "- attention: calls attention\n"
            "- caution: potential for minor damage or injury\n"
            "- warning: potential for serious injury\n"
            "- danger: potential for death or serious injury\n"
            "- trouble: troubleshooting tip\n"
            "- notice: regulatory notice\n"
            "- fastpath: shortcut or faster alternative\n"
            "- other: custom (use @othertype to specify)\n\n"
            "Other attributes: @spectitle (custom label), @othertype (when type='other').\n\n"
            "Example:\n"
            "```xml\n"
            "<note type=\"warning\">Do not modify the DTD files directly. "
            "Changes will be lost during upgrades.</note>\n"
            "```"
        ),
        "parent_element": "body, bodydiv, section, example, p, li, dd, fig, entry, abstract, lq",
        "children_elements": "p, ol, ul, dl, pre, codeblock, simpletable, table, fig, image, note, ph, keyword, xref",
        "attributes": '{"type": "note|tip|important|remember|restriction|attention|caution|warning|danger|trouble|notice|fastpath|other", "spectitle": "custom label", "othertype": "custom type when type=other"}',
        "test_data_coverage": {
            "all_values": ["note", "tip", "important", "remember", "restriction", "attention", "caution", "warning", "danger", "trouble", "notice", "fastpath", "other"],
            "supported_elements": ["note"],
            "combination_attributes": ["type", "spectitle", "othertype"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/note"
        }
    },
    {
        "element_name": "ol_element",
        "content_type": "element",
        "text_content": (
            "The <ol> element contains a list of items sorted by sequence or order of importance. "
            "Items are rendered with numbers or letters.\n\n"
            "Content model: one or more <li> elements.\n\n"
            "Contained by: body, bodydiv, section, sectiondiv, example, p, note, lq, li, "
            "itemgroup, dd, fig, stentry, draft-comment, fn, entry, abstract, linklist, linkinfo.\n\n"
            "Attributes: @compact (yes|no, controls spacing), @outputclass.\n\n"
            "Note: <ol> can nest inside <li> for multi-level numbered lists."
        ),
        "parent_element": "body, bodydiv, section, example, p, note, li, dd, fig, entry, abstract",
        "children_elements": "li",
        "attributes": '{"compact": "yes|no (control spacing)", "outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/ol"
        }
    },
    {
        "element_name": "param_element",
        "content_type": "element",
        "text_content": (
            "The <param> element provides a named parameter for an <object> element. "
            "Used to pass configuration values to embedded multimedia or applet objects.\n\n"
            "Content model: empty element.\n"
            "Contained by: <object> only.\n\n"
            "Key attributes:\n"
            "- @name (REQUIRED): parameter name\n"
            "- @value: parameter value\n"
            "- @valuetype: data|ref|object (how to interpret @value)\n"
            "- @type: MIME type (when valuetype='ref')\n\n"
            "Example:\n"
            "```xml\n"
            "<object data=\"video.mp4\" type=\"video/mp4\">\n"
            "  <param name=\"autoplay\" value=\"false\"/>\n"
            "  <param name=\"controls\" value=\"true\"/>\n"
            "</object>\n"
            "```"
        ),
        "parent_element": "object",
        "children_elements": None,
        "attributes": '{"name": "REQUIRED - parameter name", "value": "parameter value", "valuetype": "data|ref|object", "type": "MIME type"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/param"
        }
    },
    {
        "element_name": "longdescref",
        "content_type": "element",
        "text_content": (
            "The <longdescref> element provides a reference to a text description of an image "
            "or object. It links to a separate DITA topic or external file containing the full "
            "long description for accessibility purposes.\n\n"
            "Content model: empty element.\n"
            "Contained by: <image>, <object>.\n\n"
            "Key attributes:\n"
            "- @href (REQUIRED): URI to the long description resource\n"
            "- @type: format of the referenced resource\n"
            "- @scope: local|peer|external\n"
            "- @format: resource format (dita, html, etc.)\n\n"
            "Example:\n"
            "```xml\n"
            "<image href=\"architecture.png\">\n"
            "  <alt>System architecture diagram</alt>\n"
            "  <longdescref href=\"architecture-description.dita\"/>\n"
            "</image>\n"
            "```\n\n"
            "Purpose: provides a longer accessibility description than <alt> for complex images "
            "like charts, diagrams, and infographics."
        ),
        "parent_element": "image, object",
        "children_elements": None,
        "attributes": '{"href": "REQUIRED - URI to long description", "type": "resource format", "scope": "local|peer|external", "format": "dita|html|etc."}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/longdescref"
        }
    },
    {
        "element_name": "longquoteref",
        "content_type": "element",
        "text_content": (
            "The <longquoteref> element provides a reference to the source of a long quotation "
            "(<lq>). It links to the original source document being quoted.\n\n"
            "Content model: empty element.\n"
            "Contained by: <lq> (long quote) only.\n\n"
            "Key attributes:\n"
            "- @href (REQUIRED): URI to the source of the quotation\n"
            "- @scope: local|peer|external\n"
            "- @format: resource format\n\n"
            "Example:\n"
            "```xml\n"
            "<lq>\n"
            "  The fundamental concept in DITA is topic-based authoring...\n"
            "  <longquoteref href=\"https://www.oasis-open.org/dita-spec\" scope=\"external\"/>\n"
            "</lq>\n"
            "```\n\n"
            "Purpose: machine-readable source attribution for long quotations, complementing "
            "the @reftitle attribute on <lq> which provides human-readable attribution."
        ),
        "parent_element": "lq",
        "children_elements": None,
        "attributes": '{"href": "REQUIRED - URI to quotation source", "scope": "local|peer|external", "format": "resource format"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/longquoteref"
        }
    },
]


def main():
    with open(SEED_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    existing_names = {e["element_name"] for e in data}
    added = 0
    for entry in NEW_ENTRIES:
        if entry["element_name"] in existing_names:
            print(f"  SKIP (exists): {entry['element_name']}")
            continue
        data.append(entry)
        added += 1
        print(f"  ADD: {entry['element_name']}")

    with open(SEED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nDone. Added {added} entries. Total: {len(data)}")


if __name__ == "__main__":
    main()
