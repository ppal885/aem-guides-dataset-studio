#!/usr/bin/env python3
"""Insert DITA Subject Scheme spec entries into dita_spec_seed.json."""
import json
from pathlib import Path

SEED_PATH = Path(__file__).parent / "app" / "storage" / "dita_spec_seed.json"

NEW_ENTRIES = [
    {
        "element_name": "subject_scheme_overview",
        "content_type": "concept",
        "text_content": (
            "Subject scheme maps define controlled vocabularies and taxonomies for DITA attributes. "
            "A subject scheme map uses <subjectScheme> as root element and contains <subjectdef> elements "
            "that define subjects (controlled values). Subject schemes can bind controlled values to specific "
            "attributes using <enumerationDef>, constrain attribute values for quality control, "
            "define hierarchical taxonomies with <hasNarrower>/<hasPart>/<hasKind>/<hasInstance>, "
            "and classify content via <topicSubjectTable>. Subject scheme maps are processed as "
            "resource-only by default (processing-role='resource-only'). They can be referenced from a "
            "root map using <mapref> and affect all maps in the publication scope. "
            "Key elements: <subjectScheme>, <subjectdef>, <enumerationDef>, <hasNarrower>, "
            "<hasPart>, <hasKind>, <hasInstance>, <subjectRelTable>, <topicSubjectTable>, "
            "<attributedef>, <elementdef>, <defaultSubject>."
        ),
        "parent_element": None,
        "children_elements": "subjectdef, enumerationDef, subjectRelTable, hasNarrower, hasPart, hasKind, hasInstance",
        "attributes": None,
        "test_data_coverage": {
            "all_values": ["subjectScheme", "subjectdef", "enumerationDef", "hasNarrower", "hasPart", "hasKind", "hasInstance"],
            "supported_elements": ["subjectScheme"],
            "combination_attributes": ["processing-role", "mapref"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/subject-scheme-maps-and-usage"
        }
    },
    {
        "element_name": "subject_scheme_definition",
        "content_type": "element",
        "text_content": (
            "The <subjectScheme> element is a specialization of <map> that defines a collection of "
            "controlled values (subjects). A subject scheme map can define a taxonomy of subjects, "
            "bind those subjects to attributes via <enumerationDef>, and establish relationships "
            "between subjects. The <subjectdef> element defines a single subject in the taxonomy. "
            "Each <subjectdef> has a @keys attribute that names the subject and can nest child "
            "<subjectdef> elements to create hierarchies. Example: "
            '<subjectScheme><subjectdef keys="os"><subjectdef keys="linux"/>'
            '<subjectdef keys="windows"/><subjectdef keys="macos"/></subjectdef></subjectScheme>. '
            "The @navtitle attribute or nested <topicmeta>/<navtitle> provides human-readable labels. "
            "Subject definitions without @keys are category groupings only."
        ),
        "parent_element": None,
        "children_elements": "subjectdef, enumerationDef, subjectRelTable",
        "attributes": '{"keys": "key name for subject", "href": "optional topic with definition", "navtitle": "human-readable label"}',
        "test_data_coverage": {
            "all_values": ["subjectScheme", "subjectdef"],
            "supported_elements": ["subjectScheme", "subjectdef"],
            "combination_attributes": ["keys", "navtitle", "href"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/subjectschema"
        }
    },
    {
        "element_name": "subject_scheme_binding",
        "content_type": "concept",
        "text_content": (
            "The <enumerationDef> element binds a set of controlled values (subjects) to a DITA attribute. "
            "It contains <attributedef> to specify which attribute is constrained, optional <elementdef> "
            "to limit the binding to specific elements, and <subjectdef> referencing the subject hierarchy. "
            "Example binding @platform to OS values: "
            '<enumerationDef><attributedef name="platform"/>'
            '<subjectdef keyref="os"/></enumerationDef>. '
            "This constrains @platform to only accept values defined under the 'os' subject hierarchy. "
            "If <elementdef> is included, the binding only applies to that element type. "
            "A <defaultSubject> element can specify the default value when the attribute is omitted. "
            "Multiple <enumerationDef> elements can bind different attributes in the same scheme. "
            "Processors should issue warnings for attribute values not in the enumeration. "
            "The binding affects all maps that reference the subject scheme map."
        ),
        "parent_element": "subjectScheme",
        "children_elements": "attributedef, elementdef, subjectdef, defaultSubject",
        "attributes": None,
        "test_data_coverage": {
            "all_values": ["audience", "platform", "product", "otherprops", "deliveryTarget", "props"],
            "supported_elements": ["enumerationDef", "attributedef", "elementdef", "defaultSubject"],
            "combination_attributes": ["name", "keyref"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/binding-controlled-values-to-attribute"
        }
    },
    {
        "element_name": "subject_scheme_processing",
        "content_type": "concept",
        "text_content": (
            "When processing controlled attribute values bound by subject schemes, DITA processors must: "
            "(1) Resolve the subject scheme hierarchy to determine all valid values for each bound attribute. "
            "(2) When filtering (DITAVAL), treat hierarchical subjects correctly - filtering out a parent "
            "subject also filters all descendant subjects. For example, if 'os' has children 'linux' and "
            "'windows', excluding 'os' excludes both children. (3) When a subject has child subjects, "
            "content tagged with the parent value matches queries for any descendant. "
            "(4) Issue warnings for attribute values not in the enumeration. "
            "(5) The @navtitle of a <subjectdef> provides the display label for authoring tools. "
            "Processors should present controlled values in editing interfaces (dropdowns, etc.). "
            "Subject scheme bindings cascade through the map hierarchy - a scheme referenced by the "
            "root map applies to all nested maps and topics."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/processing-controlled-attribute-values"
        }
    },
    {
        "element_name": "subject_scheme_extending",
        "content_type": "concept",
        "text_content": (
            "Subject scheme maps can extend other subject scheme maps by adding new values or "
            "refining existing taxonomies. Extension is done by creating a new subject scheme map "
            "that references the base scheme via <schemeref> and adds additional <subjectdef> elements. "
            "Extension rules: (1) New values can be added to existing subject hierarchies. "
            "(2) Existing values cannot be removed (only the base scheme owner can remove). "
            "(3) The extending scheme can add deeper nesting under existing subjects. "
            "(4) Multiple schemes can extend the same base scheme. "
            "(5) If two extending schemes define conflicting bindings for the same attribute, "
            "the last-referenced scheme wins. Example: A base scheme defines @platform with "
            "'linux' and 'windows'. An extending scheme adds 'macos' under the same hierarchy."
        ),
        "parent_element": None,
        "children_elements": "schemeref, subjectdef",
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/extending-a-subject-scheme"
        }
    },
    {
        "element_name": "subject_scheme_taxonomy",
        "content_type": "concept",
        "text_content": (
            "Subject schemes can define taxonomies by scaling controlled values into hierarchical "
            "classification systems. The hierarchy elements are: "
            "<hasNarrower> - defines an is-a/narrower relationship (e.g., 'mammal' hasNarrower 'dog'). "
            "<hasPart> - defines a part-of relationship (e.g., 'car' hasPart 'engine'). "
            "<hasKind> - defines a kind-of relationship. "
            "<hasInstance> - defines an instance-of relationship. "
            "<hasRelated> - defines an associative relationship. "
            "These elements contain <subjectdef> children to build the hierarchy. "
            "Taxonomy hierarchies affect filtering behavior: filtering a broader term "
            "automatically filters all narrower terms. They also enable faceted classification "
            "where content can be classified along multiple independent dimensions. "
            "Example: <subjectdef keys='animals'><hasNarrower><subjectdef keys='mammals'/>"
            "<subjectdef keys='birds'/></hasNarrower></subjectdef>."
        ),
        "parent_element": "subjectScheme, subjectdef",
        "children_elements": "subjectdef",
        "attributes": None,
        "test_data_coverage": {
            "all_values": ["hasNarrower", "hasPart", "hasKind", "hasInstance", "hasRelated"],
            "supported_elements": ["subjectdef"],
            "combination_attributes": ["keys", "navtitle"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/scaling-controlled-values-to-define-a-taxonomy"
        }
    },
    {
        "element_name": "subject_scheme_classification_maps",
        "content_type": "concept",
        "text_content": (
            "Classification maps use <topicSubjectTable> to classify topics against subject scheme "
            "taxonomies. A <topicSubjectTable> is a specialized relationship table where: "
            "The first column contains <topicref> elements pointing to topics to classify. "
            "Subsequent columns reference subjects from the scheme via <subjectref>. "
            "The table header row uses <topicSubjectHeader> to label columns with the attribute "
            "or category being classified. Each body row (<topicSubjectRow>) associates a topic "
            "with one or more subjects. Example: classifying topics by audience and platform - "
            "header defines columns for audience and platform, body rows map each topic to its "
            "applicable audience(s) and platform(s). This classification is equivalent to setting "
            "the corresponding profiling attributes on the topics themselves, but managed centrally."
        ),
        "parent_element": "subjectScheme, map",
        "children_elements": "topicSubjectHeader, topicSubjectRow, topicref, subjectref",
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/classification-maps"
        }
    },
    {
        "element_name": "subject_scheme_filtering_example",
        "content_type": "example",
        "text_content": (
            "Example of subject scheme filtering. A subject scheme defines OS values: "
            '<subjectScheme><subjectdef keys="os">'
            '<subjectdef keys="linux"><subjectdef keys="redhat"/><subjectdef keys="suse"/></subjectdef>'
            '<subjectdef keys="windows"><subjectdef keys="win10"/><subjectdef keys="win11"/></subjectdef>'
            '</subjectdef>'
            '<enumerationDef><attributedef name="platform"/><subjectdef keyref="os"/></enumerationDef>'
            '</subjectScheme>. '
            "Filtering behavior: A DITAVAL rule <prop att='platform' val='linux' action='exclude'/> "
            "excludes all content with platform='linux', platform='redhat', or platform='suse' "
            "because redhat and suse are narrower terms of linux. "
            "A DITAVAL rule including platform='linux' includes all its descendants too. "
            "Content with platform='win10' is unaffected by linux filtering rules."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/example-subjectscheme-filtering"
        }
    },
    {
        "element_name": "subject_scheme_extension_example",
        "content_type": "example",
        "text_content": (
            "Example of extending a subject scheme. Base scheme defines operating systems: "
            '<subjectScheme><subjectdef keys="os">'
            '<subjectdef keys="linux"/><subjectdef keys="windows"/>'
            '</subjectdef></subjectScheme>. '
            "Extension scheme adds macOS and refines Linux: "
            '<subjectScheme><schemeref href="base-scheme.ditamap"/>'
            '<subjectdef keys="os"><subjectdef keys="macos"/>'
            '<subjectdef keys="linux"><subjectdef keys="ubuntu"/>'
            '<subjectdef keys="fedora"/></subjectdef>'
            '</subjectdef></subjectScheme>. '
            "After extension, valid @platform values include: linux, windows, macos, ubuntu, fedora. "
            "The extending scheme cannot remove values defined in the base scheme."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/example-subjectscheme-extension"
        }
    },
    {
        "element_name": "subject_scheme_extension_upwards_example",
        "content_type": "example",
        "text_content": (
            "Example of extending a subject scheme upwards by adding broader terms. "
            "Base scheme defines specific platforms: "
            '<subjectScheme><subjectdef keys="linux"/><subjectdef keys="windows"/></subjectScheme>. '
            "Extension adds a broader parent category 'desktop-os' above existing values: "
            '<subjectScheme><schemeref href="base-scheme.ditamap"/>'
            '<subjectdef keys="desktop-os">'
            '<subjectdef keys="linux"/><subjectdef keys="windows"/><subjectdef keys="macos"/>'
            '</subjectdef></subjectScheme>. '
            "This creates a new hierarchy where filtering desktop-os affects all three platforms. "
            "Upward extension is useful when an organization needs to add grouping categories "
            "without modifying the original base scheme."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/example-subjectscheme-extension-upwards.dita"
        }
    },
    {
        "element_name": "subject_scheme_deliverytarget_example",
        "content_type": "example",
        "text_content": (
            "Example of using subject scheme to define controlled values for @deliveryTarget. "
            "The @deliveryTarget attribute (DITA 1.3) specifies intended delivery formats. "
            "A subject scheme can bind controlled values: "
            '<subjectScheme><subjectdef keys="deliveryTargetValues">'
            '<subjectdef keys="html5"/><subjectdef keys="pdf"/>'
            '<subjectdef keys="epub"/><subjectdef keys="aemsite"/>'
            '<subjectdef keys="markdown"/></subjectdef>'
            '<enumerationDef><attributedef name="deliveryTarget"/>'
            '<subjectdef keyref="deliveryTargetValues"/></enumerationDef></subjectScheme>. '
            "This constrains @deliveryTarget to only accept: html5, pdf, epub, aemsite, markdown. "
            "Content can then be filtered by output format: "
            '<p deliveryTarget="pdf">This paragraph only appears in PDF output.</p>. '
            "DITAVAL filtering: <prop att='deliveryTarget' val='pdf' action='include'/>."
        ),
        "parent_element": None,
        "children_elements": None,
        "attributes": None,
        "test_data_coverage": {
            "all_values": ["html5", "pdf", "epub", "aemsite", "markdown"],
            "supported_elements": ["enumerationDef"],
            "combination_attributes": ["deliveryTarget", "attributedef"]
        },
        "metadata": {
            "category": "dita_spec",
            "subcategory": "subject_scheme",
            "source_url": "https://dita-lang.org/1.3/dita/archspec/base/example-subjectscheme-values-for-deliverytarget"
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
