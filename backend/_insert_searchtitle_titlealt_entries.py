#!/usr/bin/env python3
"""Insert searchtitle, titlealt, titlealts spec entries into dita_spec_seed.json."""
import json
from pathlib import Path

SEED_PATH = Path(__file__).parent / "app" / "storage" / "dita_spec_seed.json"

NEW_ENTRIES = [
    {
        "element_name": "searchtitle",
        "content_type": "element",
        "text_content": (
            "The <searchtitle> element specifies an alternative title displayed by search tools "
            "that locate the topic. It is useful when the topic has a title that makes sense in the "
            "context of a single information set but may be too general in a list of search results. "
            "For example, a topic titled 'Markup example' might use searchtitle 'DITA markup example' "
            "so search results are more descriptive.\n\n"
            "In DITA 2.0, <searchtitle> is a convenience shorthand for <titlealt title-role='search'>. "
            "It specializes from <titlealt> and is defined in the alternative-titles domain module. "
            "Inheritance: + topic/titlealt alternativeTitles-d/searchtitle.\n\n"
            "Where to place <searchtitle>:\n"
            "- In a TOPIC: inside <prolog> (DITA 2.0) or inside <titlealts> (DITA 1.3)\n"
            "- In a MAP: inside <topicmeta> on a <topicref>\n\n"
            "Content model: text, <data>, <foreign>, <keyword>, <term>, <text>, <ph>, "
            "<draft-comment>, <required-cleanup>.\n\n"
            "Attributes: universal attributes + @title-role (defaults to 'search').\n\n"
            "Processing: when present, search engines should use <searchtitle> instead of <title> "
            "in search result listings. If absent, falls back to <titlealt title-role='linking'>, "
            "then to <title>.\n\n"
            "Example in a topic (DITA 2.0):\n"
            "```xml\n"
            "<topic id=\"programming-example\">\n"
            "  <title>Programming example</title>\n"
            "  <prolog>\n"
            "    <searchtitle>Example of basic programming in XSLT</searchtitle>\n"
            "  </prolog>\n"
            "  <body><!-- content --></body>\n"
            "</topic>\n"
            "```\n\n"
            "Example in a topic (DITA 1.3):\n"
            "```xml\n"
            "<topic id=\"programming-example\">\n"
            "  <title>Programming example</title>\n"
            "  <titlealts>\n"
            "    <searchtitle>Example of basic programming in XSLT</searchtitle>\n"
            "  </titlealts>\n"
            "  <body><!-- content --></body>\n"
            "</topic>\n"
            "```\n\n"
            "Example in a map (overriding from topicref):\n"
            "```xml\n"
            "<topicref href=\"programming-example.dita\">\n"
            "  <topicmeta>\n"
            "    <navtitle>Programming example</navtitle>\n"
            "    <searchtitle>Example of programming in XSLT</searchtitle>\n"
            "  </topicmeta>\n"
            "</topicref>\n"
            "```\n\n"
            "In AEM Guides / AEM Sites: The <searchtitle> value is used as the page title in "
            "AEM Sites search results and in the HTML <meta> tags for SEO. When publishing to "
            "AEM Sites, the search title influences how pages appear in AEM's built-in search, "
            "the Assets search, and external search engines indexing the site."
        ),
        "parent_element": "prolog, titlealts, topicmeta",
        "children_elements": "keyword, term, ph, data, foreign, text, draft-comment, required-cleanup",
        "attributes": '{"title-role": "search (default for this element)", "universal": "id, conref, conkeyref, outputclass, class, translate, xml:lang, dir, audience, platform, product, otherprops, props, rev, deliveryTarget"}',
        "test_data_coverage": {
            "all_values": ["search", "linking", "navigation", "subtitle", "hint"],
            "supported_elements": ["searchtitle", "titlealt"],
            "combination_attributes": ["title-role"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "titles",
            "source_url": "https://dita-lang.org/dita/langref/base/searchtitle"
        }
    },
    {
        "element_name": "titlealt",
        "content_type": "element",
        "text_content": (
            "The <titlealt> element provides an alternative title for a document, used in contexts "
            "other than straightforward display. It is the base element from which convenience "
            "elements like <searchtitle>, <navtitle>, <subtitle>, <linktitle>, and <titlehint> "
            "are specialized.\n\n"
            "The @title-role attribute (REQUIRED) specifies the role. Defined roles:\n"
            "- 'linking': title for generated links (parent/child/sibling, reltable). Also the "
            "FALLBACK for navigation and search roles.\n"
            "- 'navigation': title for TOCs and navigation. Falls back to 'linking' if absent.\n"
            "- 'search': title for search results. Falls back to 'linking' if absent.\n"
            "- 'subtitle': subtitle for the document.\n"
            "- 'hint': hint for map authors about the referenced resource. No processing effect.\n\n"
            "Multiple roles can be specified as space-separated tokens: "
            "title-role='linking navigation'.\n\n"
            "Where to place <titlealt>:\n"
            "- In a TOPIC: inside <prolog>\n"
            "- In a MAP: inside <topicmeta>\n"
            "- In root <map>'s <topicmeta>: applies to the map itself\n"
            "- Inside a <topicref>: applies to the referenced resource\n"
            "- When referenced resource is a DITA topic: alt titles from <topicref> are merged "
            "with those in the topic, with <topicref> titles taking higher priority.\n\n"
            "Content model: text, <data>, <foreign>, <keyword>, <term>, <text>, <ph>, "
            "<draft-comment>, <required-cleanup>.\n\n"
            "Inheritance: - topic/titlealt\n\n"
            "Example - subtitle on a map:\n"
            "```xml\n"
            "<map>\n"
            "  <title>Publication title</title>\n"
            "  <topicmeta>\n"
            "    <titlealt title-role=\"subtitle\">Publication subtitle</titlealt>\n"
            "  </topicmeta>\n"
            "</map>\n"
            "```\n\n"
            "Example - multiple roles on a topicref:\n"
            "```xml\n"
            "<topicref keys=\"about\" href=\"about.dita\">\n"
            "  <topicmeta>\n"
            "    <titlealt title-role=\"linking navigation\">About the product</titlealt>\n"
            "    <titlealt title-role=\"search\">About</titlealt>\n"
            "    <titlealt title-role=\"hint\">About the Acme TextMax 5000</titlealt>\n"
            "  </topicmeta>\n"
            "</topicref>\n"
            "```\n\n"
            "Unrecognized @title-role tokens SHOULD be ignored by processors."
        ),
        "parent_element": "prolog, topicmeta",
        "children_elements": "keyword, term, ph, data, foreign, text, draft-comment, required-cleanup",
        "attributes": '{"title-role": "REQUIRED - linking|navigation|search|subtitle|hint (space-separated for multiple roles)"}',
        "test_data_coverage": {
            "all_values": ["linking", "navigation", "search", "subtitle", "hint"],
            "supported_elements": ["titlealt"],
            "combination_attributes": ["title-role"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "titles",
            "source_url": "https://dita-lang.org/dita/langref/base/titlealt"
        }
    },
    {
        "element_name": "titlealts_dita13",
        "content_type": "element",
        "text_content": (
            "The <titlealts> element is a DITA 1.3 wrapper element that contains alternative titles "
            "for a topic. It appears after <title> and before <shortdesc>/<abstract> in the topic "
            "prologue area.\n\n"
            "IMPORTANT: <titlealts> was REMOVED in DITA 2.0. In DITA 2.0, alternative titles "
            "(<searchtitle>, <navtitle>, <titlealt>) are placed directly inside <prolog> instead.\n\n"
            "Content model (DITA 1.3): optional <navtitle>, then optional <searchtitle>.\n\n"
            "Contained by: <topic>, <concept>, <task>, <reference>, <glossentry>, and all "
            "topic specializations.\n\n"
            "Attributes (DITA 1.3): @id, @conref, @conkeyref, @conrefend, @conaction, "
            "@outputclass, @class, @translate, @xml:lang, @dir.\n\n"
            "Example (DITA 1.3):\n"
            "```xml\n"
            "<topic id=\"install-guide\">\n"
            "  <title>Installation</title>\n"
            "  <titlealts>\n"
            "    <navtitle>Install Guide</navtitle>\n"
            "    <searchtitle>How to install AEM Guides on AEM 6.5</searchtitle>\n"
            "  </titlealts>\n"
            "  <shortdesc>Steps to install.</shortdesc>\n"
            "  <body><!-- content --></body>\n"
            "</topic>\n"
            "```\n\n"
            "Migration to DITA 2.0: replace <titlealts> wrapper with direct children of <prolog>:\n"
            "```xml\n"
            "<topic id=\"install-guide\">\n"
            "  <title>Installation</title>\n"
            "  <prolog>\n"
            "    <navtitle>Install Guide</navtitle>\n"
            "    <searchtitle>How to install AEM Guides on AEM 6.5</searchtitle>\n"
            "  </prolog>\n"
            "  <shortdesc>Steps to install.</shortdesc>\n"
            "  <body><!-- content --></body>\n"
            "</topic>\n"
            "```"
        ),
        "parent_element": "topic, concept, task, reference, glossentry",
        "children_elements": "navtitle, searchtitle",
        "attributes": '{"id": "optional", "conref": "optional", "conkeyref": "optional", "outputclass": "optional", "class": "- topic/titlealts", "translate": "optional", "xml:lang": "optional", "dir": "optional"}',
        "metadata": {
            "category": "dita_spec",
            "subcategory": "titles",
            "source_url": "https://dita-lang.org/1.3/dita/langref/base/titlealts"
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
