#!/usr/bin/env python3
"""Insert DITA 1.3 table and body element spec entries into dita_spec_seed.json."""
import json
from pathlib import Path

SEED_PATH = Path(__file__).parent / "app" / "storage" / "dita_spec_seed.json"

NEW_ENTRIES = [
    {
        "element_name": "table_cals",
        "content_type": "element",
        "text_content": (
            "The <table> element organizes arbitrarily complex relationships of tabular information "
            "using the OASIS Exchange Table Model (CALS). It supports column/row spanning, captions, "
            "and accessibility features.\n\n"
            "Content model: optional <title>, optional <desc>, then one or more <tgroup>.\n\n"
            "Contained by: body, bodydiv, section, sectiondiv, example, p, note, lq, li, itemgroup, "
            "dd, fig, stentry, draft-comment, fn, entry, abstract, linklist, linkinfo.\n\n"
            "Key attributes:\n"
            "- @frame: top|bottom|topbot|all|sides|none (which sides get borders)\n"
            "- @colsep: 0|1 (column separators)\n"
            "- @rowsep: 0|1 (row separators)\n"
            "- @pgwide: 0|1 (span page width)\n"
            "- @rowheader: firstcol|headers|norowheader (which column is a row header)\n"
            "- @orient: port|land (portrait or landscape)\n"
            "- @scale: percentage for font scaling\n"
            "- Display attributes: @expanse, @frame, @scale\n\n"
            "Example:\n"
            "```xml\n"
            "<table frame=\"all\" rowsep=\"1\" colsep=\"1\">\n"
            "  <title>Supported output types</title>\n"
            "  <tgroup cols=\"3\">\n"
            "    <colspec colname=\"c1\" colwidth=\"1*\"/>\n"
            "    <colspec colname=\"c2\" colwidth=\"2*\"/>\n"
            "    <colspec colname=\"c3\" colwidth=\"1*\"/>\n"
            "    <thead>\n"
            "      <row>\n"
            "        <entry>Format</entry>\n"
            "        <entry>Description</entry>\n"
            "        <entry>Status</entry>\n"
            "      </row>\n"
            "    </thead>\n"
            "    <tbody>\n"
            "      <row>\n"
            "        <entry>PDF</entry>\n"
            "        <entry>Native PDF output</entry>\n"
            "        <entry>Supported</entry>\n"
            "      </row>\n"
            "    </tbody>\n"
            "  </tgroup>\n"
            "</table>\n"
            "```"
        ),
        "parent_element": "body, bodydiv, section, example, p, note, li, dd, fig, entry, abstract",
        "children_elements": "title, desc, tgroup",
        "attributes": '{"frame": "top|bottom|topbot|all|sides|none", "colsep": "0|1", "rowsep": "0|1", "pgwide": "0|1", "rowheader": "firstcol|headers|norowheader", "orient": "port|land", "scale": "percentage"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/table"
        }
    },
    {
        "element_name": "tgroup",
        "content_type": "element",
        "text_content": (
            "The <tgroup> element contains the header rows and body rows of a CALS table. "
            "It acts as the structural container within a <table> element.\n\n"
            "Content model: zero or more <colspec>, optional <thead>, then required <tbody>.\n\n"
            "Contained by: <table> only.\n\n"
            "Key attributes:\n"
            "- @cols (REQUIRED): number of columns in the table group\n"
            "- @colsep: 0|1 (column separators)\n"
            "- @rowsep: 0|1 (row separators)\n"
            "- @align: left|right|center|justify|char (text alignment)\n\n"
            "A <table> can have multiple <tgroup> elements, each defining a separate "
            "section with its own column structure."
        ),
        "parent_element": "table",
        "children_elements": "colspec, thead, tbody",
        "attributes": '{"cols": "REQUIRED - number of columns", "colsep": "0|1", "rowsep": "0|1", "align": "left|right|center|justify|char"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/tgroup"
        }
    },
    {
        "element_name": "simpletable_element",
        "content_type": "element",
        "text_content": (
            "The <simpletable> element is used for tables that are regular in structure and do not "
            "need a caption. Suitable for displaying tabular data in consistent rows and columns "
            "without the complexity of the CALS table model.\n\n"
            "Content model: optional <sthead> (header row), then one or more <strow> (body rows).\n\n"
            "Contained by: body, bodydiv, section, sectiondiv, example, p, note, lq, li, itemgroup, "
            "dd, fig, draft-comment, fn, entry, abstract, linklist, linkinfo.\n\n"
            "Key attributes:\n"
            "- @keycol: number identifying which column is the key/header column\n"
            "- @relcolwidth: proportional column widths (e.g., '1* 2* 1*')\n"
            "- @spectitle: string title\n\n"
            "Example:\n"
            "```xml\n"
            "<simpletable relcolwidth=\"1* 3*\">\n"
            "  <sthead>\n"
            "    <stentry>Setting</stentry>\n"
            "    <stentry>Description</stentry>\n"
            "  </sthead>\n"
            "  <strow>\n"
            "    <stentry>chunk</stentry>\n"
            "    <stentry>Controls how topics are combined in output</stentry>\n"
            "  </strow>\n"
            "</simpletable>\n"
            "```\n\n"
            "Difference from <table>: simpletable has no title, no column/row spanning, "
            "no colspec. Use <table> when you need spanning, captions, or complex structure."
        ),
        "parent_element": "body, bodydiv, section, example, p, note, li, dd, fig, entry, abstract",
        "children_elements": "sthead, strow",
        "attributes": '{"keycol": "number (key column)", "relcolwidth": "proportional widths (e.g. 1* 2*)", "spectitle": "string title"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/simpletable"
        }
    },
    {
        "element_name": "row_element",
        "content_type": "element",
        "text_content": (
            "The <row> element contains a single row in a CALS table. "
            "Content model: one or more <entry> elements.\n"
            "Contained by: <thead> or <tbody>.\n"
            "Attributes: @rowsep (0|1, row separator), @valign (top|bottom|middle)."
        ),
        "parent_element": "thead, tbody",
        "children_elements": "entry",
        "attributes": '{"rowsep": "0|1", "valign": "top|bottom|middle"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/row"
        }
    },
    {
        "element_name": "entry_element",
        "content_type": "element",
        "text_content": (
            "The <entry> element defines a single cell in a CALS table.\n\n"
            "Content model: inline and block content (text, ph, keyword, xref, image, dl, fig, "
            "note, ol, ul, p, pre, codeblock, simpletable, etc.).\n\n"
            "Contained by: <row> only.\n\n"
            "Key attributes for spanning and alignment:\n"
            "- @namest + @nameend: column spanning (first and last column names)\n"
            "- @morerows: row spanning (number of additional rows)\n"
            "- @colname: references a <colspec> by name\n"
            "- @rotate: 0|1 (rotate cell content 90 degrees)\n"
            "- @align: left|right|center|justify|char\n"
            "- @valign: top|bottom|middle\n"
            "- @colsep, @rowsep: 0|1\n"
            "- @scope: row|col|rowgroup|colgroup (accessibility - identifies header cells)\n"
            "- @headers: IDREFS to header entries (accessibility)\n\n"
            "Example of column spanning:\n"
            "```xml\n"
            "<row>\n"
            "  <entry namest=\"c1\" nameend=\"c3\">This spans all 3 columns</entry>\n"
            "</row>\n"
            "```\n\n"
            "Example of row spanning:\n"
            "```xml\n"
            "<row>\n"
            "  <entry morerows=\"1\">Spans 2 rows</entry>\n"
            "  <entry>Normal cell</entry>\n"
            "</row>\n"
            "```"
        ),
        "parent_element": "row",
        "children_elements": "p, ph, keyword, xref, image, dl, fig, note, ol, ul, pre, codeblock, simpletable",
        "attributes": '{"namest": "first column in span", "nameend": "last column in span", "morerows": "additional rows spanned", "colname": "references colspec", "rotate": "0|1", "align": "left|right|center|justify|char", "valign": "top|bottom|middle", "scope": "row|col|rowgroup|colgroup", "headers": "IDREFS to header entries"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/entry"
        }
    },
    {
        "element_name": "cals_table_attributes",
        "content_type": "concept",
        "text_content": (
            "CALS table attributes are a set of attributes available on CALS table elements "
            "(table, tgroup, colspec, thead, tbody, row, entry) for controlling alignment, "
            "separators, row headers, and vertical alignment.\n\n"
            "Attributes:\n"
            "- @align (tgroup, colspec, entry): left|right|center|justify|char - text alignment\n"
            "- @char (colspec, entry): alignment character when align='char'\n"
            "- @charoff (colspec, entry): horizontal offset 0-100 for char alignment\n"
            "- @colsep (table, tgroup, colspec, entry): 0|1 - column separator lines\n"
            "- @rowsep (table, tgroup, row, colspec, entry): 0|1 - row separator lines\n"
            "- @rowheader (table, colspec): firstcol|headers|norowheader - identifies row headers\n"
            "- @valign (thead, tbody, row, entry): top|bottom|middle - vertical alignment\n\n"
            "Cascading: attribute values cascade from table -> tgroup -> colspec -> entry, "
            "with the most specific (closest to the cell) winning."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": '{"align": "left|right|center|justify|char", "char": "alignment character", "charoff": "0-100 offset", "colsep": "0|1", "rowsep": "0|1", "rowheader": "firstcol|headers|norowheader", "valign": "top|bottom|middle"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "tables",
            "source_url": "https://dita-lang.org/1.3/dita/langref/attributes/calstableattributes"
        }
    },
    {
        "element_name": "bodydiv_element",
        "content_type": "element",
        "text_content": (
            "The <bodydiv> element is an informal grouping container within the body of a topic. "
            "It has no explicit semantics; it is used to organize content into logical groups, "
            "primarily as a specialization base or for conref reuse of body fragments.\n\n"
            "Content model: block-level content (p, ol, ul, dl, table, simpletable, fig, note, "
            "image, section, example, bodydiv, etc.).\n\n"
            "Contained by: <body>, <bodydiv> (can nest).\n\n"
            "Use cases: (1) group paragraphs for conref as a unit, (2) specialization base for "
            "custom body-level groupings, (3) wrap content for conditional processing.\n\n"
            "Example:\n"
            "```xml\n"
            "<body>\n"
            "  <bodydiv id=\"prereqs-group\">\n"
            "    <p>Before you begin, ensure:</p>\n"
            "    <ul>\n"
            "      <li>AEM 6.5 SP18+ is installed</li>\n"
            "      <li>Java 11 is available</li>\n"
            "    </ul>\n"
            "  </bodydiv>\n"
            "</body>\n"
            "```"
        ),
        "parent_element": "body, bodydiv",
        "children_elements": "p, ol, ul, dl, table, simpletable, fig, note, image, section, example, bodydiv",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/bodydiv"
        }
    },
    {
        "element_name": "desc_element",
        "content_type": "element",
        "text_content": (
            "The <desc> element contains the description of the current element. It provides "
            "additional information in contexts like figures, tables, cross-references, and objects.\n\n"
            "Content model: inline content (text, ph, keyword, xref, term, image, draft-comment).\n\n"
            "Contained by: <table>, <fig>, <xref>, <link>, <object>.\n\n"
            "Processing: on <table> and <fig>, <desc> renders as a caption/description. "
            "On <xref> and <link>, <desc> provides hover/tooltip text."
        ),
        "parent_element": "table, fig, xref, link, object",
        "children_elements": "ph, keyword, xref, term, image, draft-comment",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/desc"
        }
    },
    {
        "element_name": "alt_element",
        "content_type": "element",
        "text_content": (
            "The <alt> element provides alternate text for an image. It replaces the deprecated "
            "@alt attribute on the <image> element.\n\n"
            "Content model: inline content (text, ph, keyword).\n"
            "Contained by: <image> only.\n\n"
            "Example:\n"
            "```xml\n"
            "<image href=\"logo.png\">\n"
            "  <alt>Company logo</alt>\n"
            "</image>\n"
            "```"
        ),
        "parent_element": "image",
        "children_elements": "ph, keyword",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/alt"
        }
    },
    {
        "element_name": "dlentry_element",
        "content_type": "element",
        "text_content": (
            "The <dlentry> element groups a single entry in a definition list, including a term "
            "(<dt>) and one or more definitions (<dd>).\n\n"
            "Content model: one or more <dt>, then one or more <dd>.\n"
            "Contained by: <dl> only.\n\n"
            "Example:\n"
            "```xml\n"
            "<dl>\n"
            "  <dlentry>\n"
            "    <dt>conref</dt>\n"
            "    <dd>Content reference - reuses content from another element by ID</dd>\n"
            "  </dlentry>\n"
            "  <dlentry>\n"
            "    <dt>keyref</dt>\n"
            "    <dd>Key reference - indirect addressing via key names</dd>\n"
            "  </dlentry>\n"
            "</dl>\n"
            "```"
        ),
        "parent_element": "dl",
        "children_elements": "dt, dd",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/dlentry"
        }
    },
    {
        "element_name": "dd_element",
        "content_type": "element",
        "text_content": (
            "The <dd> element contains the description/definition of a term in a <dlentry>.\n\n"
            "Content model: block and inline content (p, ol, ul, dl, fig, note, pre, codeblock, "
            "image, table, simpletable, etc.).\n"
            "Contained by: <dlentry> only."
        ),
        "parent_element": "dlentry",
        "children_elements": "p, ol, ul, dl, fig, note, pre, codeblock, image, table, simpletable",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/dd"
        }
    },
    {
        "element_name": "dt_element",
        "content_type": "element",
        "text_content": (
            "The <dt> element contains a term in a definition list entry (<dlentry>).\n\n"
            "Content model: inline content (text, ph, keyword, term, xref, image).\n"
            "Contained by: <dlentry> only.\n"
            "Attributes: @keyref (key reference), @outputclass."
        ),
        "parent_element": "dlentry",
        "children_elements": "ph, keyword, term, xref, image",
        "attributes": '{"keyref": "key reference", "outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/dt"
        }
    },
    {
        "element_name": "ddhd_element",
        "content_type": "element",
        "text_content": (
            "The <ddhd> element provides an optional heading for the description column in a "
            "definition list. Contained by <dlhead>. Content model: inline content."
        ),
        "parent_element": "dlhead",
        "children_elements": "ph, keyword, term, xref, image",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/ddhd"
        }
    },
    {
        "element_name": "dthd_element",
        "content_type": "element",
        "text_content": (
            "The <dthd> element provides an optional heading for the term column in a "
            "definition list. Contained by <dlhead>. Content model: inline content."
        ),
        "parent_element": "dlhead",
        "children_elements": "ph, keyword, term, xref, image",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/dthd"
        }
    },
    {
        "element_name": "draft_comment",
        "content_type": "element",
        "text_content": (
            "The <draft-comment> element facilitates review and discussion of topic contents "
            "within the marked-up content. Designed for internal commenting during authoring.\n\n"
            "Content model: block and inline content (text, p, ol, ul, dl, ph, keyword, image).\n\n"
            "Contained by: nearly all body-level and inline contexts (body, section, p, li, dd, "
            "entry, ph, fig, note, title, shortdesc, abstract).\n\n"
            "Key attributes:\n"
            "- @author: string, originator of the comment\n"
            "- @time: string, creation date\n"
            "- @disposition: string, status (e.g., 'open', 'accepted', 'rejected')\n"
            "- @translate: defaults to 'no'\n\n"
            "Processing: processors SHOULD strip <draft-comment> from final output by default "
            "and only render it in draft mode. In AEM Guides, draft comments appear in the "
            "Web Editor review workflow but are excluded from published output."
        ),
        "parent_element": "body, section, p, li, dd, entry, ph, fig, note, title, shortdesc, abstract",
        "children_elements": "p, ol, ul, dl, ph, keyword, image",
        "attributes": '{"author": "originator", "time": "creation date", "disposition": "status (open|accepted|rejected)", "translate": "no (default)"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/draft-comment"
        }
    },
    {
        "element_name": "example_element",
        "content_type": "element",
        "text_content": (
            "The <example> element is a section-like element that contains examples illustrating "
            "or supporting the current topic. Can contain both sample code and discussion.\n\n"
            "Content model: optional <title>, then block and inline content (p, ol, ul, dl, table, "
            "simpletable, fig, note, pre, codeblock, image).\n\n"
            "Contained by: body, conbody, refbody, taskbody (after prereq, context, steps, result).\n\n"
            "Attributes: @spectitle (string), @outputclass.\n\n"
            "Note: <example> is a section-level element like <section>. It cannot nest inside "
            "itself or inside <section>."
        ),
        "parent_element": "body, conbody, refbody, taskbody",
        "children_elements": "title, p, ol, ul, dl, table, simpletable, fig, note, pre, codeblock, image",
        "attributes": '{"spectitle": "string title", "outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/example"
        }
    },
    {
        "element_name": "fig_element",
        "content_type": "element",
        "text_content": (
            "The <fig> element represents a figure (exhibit) with an optional title. Commonly "
            "displays images but can contain text objects, code, and other content.\n\n"
            "Content model: optional <title>, optional <desc>, then content: figgroup, image, "
            "ol, ul, dl, p, pre, codeblock, lines, simpletable, xref, fn, note, draft-comment.\n\n"
            "Contained by: body, bodydiv, section, sectiondiv, example, p, note, lq, li, "
            "itemgroup, dd, entry, abstract, linklist, linkinfo, stentry.\n\n"
            "Attributes: @spectitle, @outputclass, @expanse, @frame, @scale (display-atts).\n\n"
            "Example:\n"
            "```xml\n"
            "<fig id=\"arch-diagram\">\n"
            "  <title>System Architecture</title>\n"
            "  <desc>Overview of the AEM Guides publishing pipeline</desc>\n"
            "  <image href=\"architecture.png\" placement=\"break\">\n"
            "    <alt>Architecture diagram</alt>\n"
            "  </image>\n"
            "</fig>\n"
            "```"
        ),
        "parent_element": "body, bodydiv, section, example, p, note, li, dd, entry, abstract",
        "children_elements": "title, desc, figgroup, image, ol, ul, dl, p, pre, codeblock, simpletable, xref, fn, note",
        "attributes": '{"spectitle": "string", "outputclass": "string", "expanse": "display attribute", "frame": "display attribute", "scale": "display attribute"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/fig"
        }
    },
    {
        "element_name": "figgroup_element",
        "content_type": "element",
        "text_content": (
            "The <figgroup> element is used primarily for specialization to create segments "
            "within a figure. It enables creation of complex specialized structures and can "
            "contain cross-references, footnotes, keywords, and images.\n\n"
            "Content model: title, figgroup (nesting), xref, fn, ph, keyword, image, draft-comment.\n"
            "Contained by: <fig>, <figgroup> (can nest)."
        ),
        "parent_element": "fig, figgroup",
        "children_elements": "title, figgroup, xref, fn, ph, keyword, image, draft-comment",
        "attributes": '{"outputclass": "string"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "body_elements",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/figgroup"
        }
    },
    {
        "element_name": "dita_use_conref_target",
        "content_type": "concept",
        "text_content": (
            "The value '-dita-use-conref-target' is a special token for enumerated attributes "
            "that allows the conref resolution process to pull the attribute value from the "
            "referenced element, rather than preserving the locally-specified value.\n\n"
            "Purpose: lets authors specify a value for a required attribute while still deferring "
            "to the conref source. When an element uses @conref and an attribute is set to "
            "'-dita-use-conref-target', that attribute value is replaced by the corresponding "
            "attribute value from the referenced element during conref resolution.\n\n"
            "Applies to: any enumerated attribute where not prohibited by the specification. "
            "NOT allowed on @id for topic elements.\n\n"
            "Example: a <note> that conrefs another note but defers the @type value:\n"
            "```xml\n"
            "<note conref=\"common.dita#common/warning-note\" type=\"-dita-use-conref-target\"/>\n"
            "```\n"
            "After resolution, @type takes the value from the referenced element."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "attributes",
            "source_url": "https://dita-lang.org/1.3/dita/langref/attributes/ditauseconreftarget"
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
