#!/usr/bin/env python3
"""Insert DITAVAL and indexterm spec entries into dita_spec_seed.json."""
import json
from pathlib import Path

SEED_PATH = Path(__file__).parent / "app" / "storage" / "dita_spec_seed.json"

NEW_ENTRIES = [
    # ── DITAVAL entries ──
    {
        "element_name": "ditaval_overview",
        "content_type": "concept",
        "text_content": (
            "A DITAVAL file (.ditaval) defines a conditional processing profile for filtering, flagging, "
            "and revision marking of DITA content. The root element is <val>. Structure: <val> contains "
            "an optional <style-conflict> followed by any number of <prop> or <revprop> elements. "
            "<prop> and <revprop> can contain <startflag> and <endflag>, which can contain <alt-text>. "
            "Processors should report attribute values in content that lack an explicit action. "
            "Actions: include (default, output content), exclude (remove from output), "
            "passthrough (include and preserve attribute for runtime), flag (include and visually flag). "
            "A <prop> with no @att and no @val sets the default action for all conditional attributes. "
            "Values not explicitly mentioned default to 'include' unless overridden by a catch-all prop."
        ),
        "parent_element": None,
        "children_elements": "val, style-conflict, prop, revprop, startflag, endflag, alt-text",
        "attributes": None,
        "test_data_coverage": {
            "all_values": ["include", "exclude", "passthrough", "flag"],
            "supported_elements": ["val", "prop", "revprop"],
            "combination_attributes": ["att", "val", "action", "color", "backcolor", "style"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/common/about-ditaval.html"
        }
    },
    {
        "element_name": "ditaval_val",
        "content_type": "element",
        "text_content": (
            "The <val> element is the root element of a DITAVAL file. It contains an optional "
            "<style-conflict> element followed by any number of <prop> or <revprop> elements. "
            "A DITAVAL file specifies filter, flagging, and revision rules applied during publishing. "
            "Example: <val><prop att='audience' val='admin' action='include'/>"
            "<prop att='audience' val='novice' action='exclude'/></val>. "
            "A <prop> with no @att and no @val sets the default action for all conditional attributes."
        ),
        "parent_element": None,
        "children_elements": "style-conflict, prop, revprop",
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-val.html"
        }
    },
    {
        "element_name": "ditaval_style_conflict",
        "content_type": "element",
        "text_content": (
            "The <style-conflict> element declares behavior when multiple flagging methods collide on "
            "a single content element. It is an empty element contained by <val>. "
            "Attributes: @foreground-conflict-color (optional, CDATA) for conflicting text colors, "
            "@background-conflict-color (optional, CDATA) for conflicting background colors. "
            "Conflict resolution rules: nested flags win over ancestor flags. For same-element conflicts: "
            "startflag/endflag - add all; color - use foreground-conflict-color; backcolor - use "
            "background-conflict-color; style - combine all (default to double-underline + conflict "
            "color for underline conflicts); changebar - add all."
        ),
        "parent_element": "val",
        "children_elements": None,
        "attributes": '{"foreground-conflict-color": "color for conflicting text", "background-conflict-color": "color for conflicting backgrounds"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-style-conflict.html"
        }
    },
    {
        "element_name": "ditaval_prop",
        "content_type": "element",
        "text_content": (
            "The <prop> element in a DITAVAL file identifies a conditional processing attribute and "
            "value to act upon. Content model: optional <startflag>, then optional <endflag>. "
            "Attributes: @att (optional, must be props/audience/platform/product/otherprops or a "
            "specialization of props; omitting sets default for all conditional attributes), "
            "@val (optional, the specific value to match; omitting sets default for all values of @att), "
            "@action (required: include|exclude|passthrough|flag), "
            "@color (optional, text color when action=flag, named colors or #rrggbb hex), "
            "@backcolor (optional, background color when action=flag), "
            "@style (optional: underline|double-underline|italics|overline|bold). "
            "Example: <prop att='platform' val='windows' action='exclude'/>. "
            "Duplicate prop with same att+val is an error."
        ),
        "parent_element": "val",
        "children_elements": "startflag, endflag",
        "attributes": '{"att": "conditional attribute name (audience|platform|product|otherprops|props)", "val": "value to match", "action": "include|exclude|passthrough|flag (required)", "color": "text color (#rrggbb or named)", "backcolor": "background color", "style": "underline|double-underline|italics|overline|bold"}',
        "test_data_coverage": {
            "all_values": ["include", "exclude", "passthrough", "flag"],
            "supported_elements": ["prop"],
            "combination_attributes": ["att", "val", "action", "color", "backcolor", "style"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-prop.html"
        }
    },
    {
        "element_name": "ditaval_revprop",
        "content_type": "element",
        "text_content": (
            "The <revprop> element identifies a value in the @rev attribute for flagging. "
            "Unlike other conditional attributes, @rev may only be used for flagging, NOT filtering. "
            "Content model: optional <startflag>, then optional <endflag>. "
            "Attributes: @val (optional, revision value to match; omitting sets default for all rev values), "
            "@action (required: include|passthrough|flag - NO exclude option since rev cannot filter), "
            "@changebar (optional, changebar color/style/character for flagged revisions), "
            "@color (optional, text color), @backcolor (optional, background color), "
            "@style (optional: underline|double-underline|italics|overline|bold). "
            "Default alt-text when none specified: localized 'Start of change' / 'End of change'."
        ),
        "parent_element": "val",
        "children_elements": "startflag, endflag",
        "attributes": '{"val": "revision value to match", "action": "include|passthrough|flag (required, no exclude)", "changebar": "changebar style for revisions", "color": "text color", "backcolor": "background color", "style": "underline|double-underline|italics|overline|bold"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-revprop.html"
        }
    },
    {
        "element_name": "ditaval_startflag",
        "content_type": "element",
        "text_content": (
            "The <startflag> element marks the beginning of flagged content with an optional image "
            "and/or alt-text. Content model: optional <alt-text>. Contained by: <prop>, <revprop>. "
            "Attributes: @imageref (required, URI reference to an image file, same syntax as href). "
            "Processing: if image specified, it flags the beginning of content with that image + alt-text. "
            "If only alt-text is specified (no image), that text is used instead. "
            "If neither specified, element has no defined purpose."
        ),
        "parent_element": "prop, revprop",
        "children_elements": "alt-text",
        "attributes": '{"imageref": "URI reference to flag image (required)"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-startflag.html"
        }
    },
    {
        "element_name": "ditaval_endflag",
        "content_type": "element",
        "text_content": (
            "The <endflag> element marks the end of flagged content with an optional image "
            "and/or alt-text. Content model: optional <alt-text>. Contained by: <prop>, <revprop>. "
            "Attributes: @imageref (required, URI reference to an image file). "
            "Processing: same logic as startflag - image flags end of content; alt-text used as "
            "fallback; if neither present, no defined purpose."
        ),
        "parent_element": "prop, revprop",
        "children_elements": "alt-text",
        "attributes": '{"imageref": "URI reference to flag image (required)"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/ditaval-endflag.html"
        }
    },
    {
        "element_name": "ditaval_flag_module_processing",
        "content_type": "concept",
        "text_content": (
            "The flag-module is a DITA-OT pre-processing step (since DITA-OT 1.7) that evaluates "
            "a DITAVAL file against all flagging attributes and inserts DITA-OT-specific hint elements. "
            "Two pseudo-specialization elements of <foreign> are injected: "
            "<ditaval-startprop> inserted as the first child of a flagged element, containing CSS styles "
            "on @outputclass, any <style-conflict>, and copies of active <prop>/<revprop> with <startflag> "
            "children but NOT <endflag>. "
            "<ditaval-endprop> inserted as the last child of a flagged element, containing copies of "
            "active <prop>/<revprop> with <endflag> children but NOT <startflag>. "
            "If no DITAVAL is used, the step is skipped. Transforms support flagging by processing "
            "these hint elements or can ignore them."
        ),
        "parent_element": None,
        "children_elements": "ditaval-startprop, ditaval-endprop",
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "ditaval",
            "source_url": "https://www.dita-ot.org/dev/reference/preprocess-flagging"
        }
    },
    # ── Indexterm entries ──
    {
        "element_name": "indexterm",
        "content_type": "element",
        "text_content": (
            "The <indexterm> element contains content used to produce an index entry in generated output. "
            "Inheritance: - topic/indexterm. Nested <indexterm> elements create multi-level indexes. "
            "Content model: text, <data>, <foreign>, <keyword>, <term>, <text>, <ph>, <indexterm>, "
            "<index-see>, <index-see-also>. "
            "Contained by: many block/inline elements including <p>, <section>, <li>, <ph>, <abstract>, "
            "<keywords>, <indexterm> itself, etc. "
            "Attributes: universal attributes + @keyref + @start (identifier marking beginning of index "
            "range) + @end (identifier marking end of index range). "
            "Rendering: content is NOT rendered in body text flow; it is rendered only in generated index. "
            "Index ranges: use @start on one <indexterm> and @end on another with matching identifiers "
            "to produce page-range entries (e.g., 'cheese 18-24'). "
            "Example: <indexterm>DITA<indexterm>maps</indexterm></indexterm> produces 'DITA, maps' in index. "
            "Example range: <indexterm start='cheese-range'>cheese</indexterm> ... "
            "<indexterm end='cheese-range'>cheese</indexterm> produces 'cheese 18-24'."
        ),
        "parent_element": "p, section, li, ph, abstract, keywords, indexterm, topic, prolog",
        "children_elements": "indexterm, index-see, index-see-also, keyword, term, ph, data, foreign, text",
        "attributes": '{"keyref": "key reference", "start": "identifier for start of index range", "end": "identifier for end of index range"}',
        "test_data_coverage": {
            "all_values": ["indexterm", "index-see", "index-see-also"],
            "supported_elements": ["indexterm"],
            "combination_attributes": ["start", "end", "keyref"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "indexing",
            "source_url": "https://dita-lang.org/dita/langref/base/indexterm"
        }
    },
    {
        "element_name": "index_see",
        "content_type": "element",
        "text_content": (
            "The <index-see> element directs the reader to an index entry that should be used INSTEAD "
            "of the current one (a 'see' cross-reference). Inheritance: - topic/index-see. "
            "Content model: text, <data>, <foreign>, <keyword>, <term>, <text>, <ph>, <indexterm>. "
            "Contained by: <indexterm> only. Attributes: universal attributes + @keyref. "
            "Processing: processors SHOULD ignore an <index-see> if its parent <indexterm> contains "
            "any <indexterm> children. Multiple <index-see> elements can appear in a single <indexterm>. "
            "The generated index entry has no page reference - only the redirection. "
            "Can redirect to multi-level entries by nesting <indexterm> inside <index-see>. "
            "Example: <indexterm>Vehicles<index-see>Cars</index-see></indexterm> produces "
            "'Vehicles, see Cars' in the index."
        ),
        "parent_element": "indexterm",
        "children_elements": "indexterm, keyword, term, ph, data, foreign, text",
        "attributes": '{"keyref": "key reference"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "indexing",
            "source_url": "https://dita-lang.org/dita/langref/base/index-see"
        }
    },
    {
        "element_name": "index_see_also",
        "content_type": "element",
        "text_content": (
            "The <index-see-also> element directs the reader to an index entry that can be used "
            "IN ADDITION to the current one (a 'see also' cross-reference). "
            "Inheritance: - topic/index-see-also. "
            "Content model: text, <data>, <foreign>, <keyword>, <term>, <text>, <ph>, <indexterm>. "
            "Contained by: <indexterm> only. Attributes: universal attributes + @keyref. "
            "Processing: processors SHOULD ignore an <index-see-also> if its parent <indexterm> "
            "contains any <indexterm> children. A single <indexterm> can contain multiple "
            "<index-see-also> elements. Unlike <index-see>, this generates both the primary index "
            "entry WITH a page reference AND the 'see also' redirection. "
            "Can redirect to multi-level entries by nesting <indexterm> inside <index-see-also>. "
            "Example: <indexterm>Markup languages<index-see-also>XML</index-see-also></indexterm> "
            "produces 'Markup languages 12, see also XML' in the index."
        ),
        "parent_element": "indexterm",
        "children_elements": "indexterm, keyword, term, ph, data, foreign, text",
        "attributes": '{"keyref": "key reference"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "indexing",
            "source_url": "https://dita-lang.org/dita/langref/base/index-see-also"
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
