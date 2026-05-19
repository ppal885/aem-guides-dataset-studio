from __future__ import annotations

import re

from app.core.schemas_dita_generation_contract import ConstructSemantic, DomainDecomposition

_CONSTRUCT_PATTERN_MAP: dict[str, tuple[re.Pattern[str], ...]] = {
    "conref": (
        re.compile(r"\bconref\b", re.IGNORECASE),
        re.compile(r"\bcontent reuse\b", re.IGNORECASE),
    ),
    "conkeyref": (
        re.compile(r"\bconkeyref\b", re.IGNORECASE),
    ),
    "xref": (
        re.compile(r"\bxref\b|\bxrefs\b", re.IGNORECASE),
        re.compile(r"\bcross[- ]references?\b", re.IGNORECASE),
        re.compile(r"\bself[- ]references?\b", re.IGNORECASE),
    ),
    "glossentry": (
        re.compile(r"\bglossary\b|\bglossaries\b|\bglossentry\b|\bglossentries\b", re.IGNORECASE),
    ),
    "subjectscheme": (
        re.compile(r"\bsubject\s+scheme\b|\bsubjectscheme\b", re.IGNORECASE),
        re.compile(r"\bsubjectdef\b|\benumerationdef\b|\bschemeref\b", re.IGNORECASE),
    ),
    "ditaval": (
        re.compile(r"\bditaval\b|\bditavalref\b", re.IGNORECASE),
        re.compile(r"\bconditional processing\b|\bprofiling\b|\bfiltering\b", re.IGNORECASE),
    ),
    "refbody": (
        re.compile(r"\brefbody\b", re.IGNORECASE),
    ),
    "refsyn": (
        re.compile(r"\brefsyn\b", re.IGNORECASE),
    ),
    "codeblock": (
        re.compile(r"\bcode\s*blocks?\b|\bcodeblock\b", re.IGNORECASE),
    ),
    "codeph": (
        re.compile(r"\bcodeph\b|\binline code\b", re.IGNORECASE),
    ),
}

_CONSTRUCT_LIBRARY: dict[str, dict[str, object]] = {
    "conref": {
        "category": "reuse",
        "bundle_strategy": "topic_bundle",
        "family_hint": "topic",
        "include_map": False,
        "requires_contract_path": True,
        "required_attributes": ["conref"],
        "example_counts": {"topic": 2},
        "notes": [
            "A conref example needs a reusable source and a consuming topic.",
        ],
    },
    "conkeyref": {
        "category": "reuse",
        "bundle_strategy": "map_bundle",
        "family_hint": "map",
        "include_map": True,
        "requires_contract_path": True,
        "required_attributes": ["conkeyref", "keys"],
        "required_elements": ["keydef", "topicref"],
        "example_counts": {"ditamap": 1, "topic": 2},
        "notes": [
            "A conkeyref example needs keys or keydefs plus a consumer target.",
        ],
    },
    "xref": {
        "category": "linking",
        "bundle_strategy": "topic_bundle",
        "family_hint": "topic",
        "include_map": False,
        "requires_contract_path": True,
        "required_elements": ["xref"],
        "example_counts": {"topic": 2},
        "notes": [
            "Cross-reference examples need a source topic and a target topic.",
        ],
    },
    "glossentry": {
        "category": "terminology",
        "bundle_strategy": "glossary_pack",
        "family_hint": "glossentry",
        "include_map": False,
        "requires_contract_path": False,
        "required_elements": ["glossentry"],
        "example_counts": {"glossentry": 5},
        "notes": [
            "Glossary bundles work best when terms stay in one subject domain.",
        ],
    },
    "subjectscheme": {
        "category": "taxonomy",
        "bundle_strategy": "map_bundle",
        "family_hint": "map",
        "include_map": True,
        "requires_contract_path": True,
        "required_elements": ["subjectScheme", "subjectdef", "enumerationdef"],
        "example_counts": {"subjectscheme": 1, "ditamap": 1, "topic": 2},
        "notes": [
            "Subject scheme examples need a subjectScheme map plus topics that use the controlled values.",
        ],
    },
    "ditaval": {
        "category": "filtering",
        "bundle_strategy": "map_bundle",
        "family_hint": "map",
        "include_map": True,
        "requires_contract_path": True,
        "required_elements": ["ditavalref"],
        "required_attributes": ["audience"],
        "preferred_structures": ["ditaval"],
        "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        "notes": [
            "DITAVAL examples need a profile plus at least one filtered topic or map branch.",
        ],
    },
    "refbody": {
        "category": "reference_structure",
        "bundle_strategy": "single_topic",
        "family_hint": "reference",
        "include_map": False,
        "requires_contract_path": False,
        "required_elements": ["refbody"],
        "example_counts": {"reference": 1},
        "notes": [
            "refbody belongs inside a reference topic.",
        ],
    },
    "refsyn": {
        "category": "reference_structure",
        "bundle_strategy": "single_topic",
        "family_hint": "reference",
        "include_map": False,
        "requires_contract_path": True,
        "required_elements": ["refsyn"],
        "example_counts": {"reference": 1},
        "notes": [
            "refsyn belongs inside a reference topic and usually pairs with refbody.",
        ],
    },
    "codeblock": {
        "category": "code_formatting",
        "bundle_strategy": "single_topic",
        "family_hint": "reference",
        "include_map": False,
        "requires_contract_path": True,
        "preferred_structures": ["codeblock"],
        "example_counts": {"reference": 1},
        "notes": [
            "Code blocks work best in task, reference, or API-style topics where commands and syntax are explicit.",
        ],
    },
    "codeph": {
        "category": "code_formatting",
        "bundle_strategy": "single_topic",
        "family_hint": "reference",
        "include_map": False,
        "requires_contract_path": True,
        "preferred_structures": ["codeph"],
        "example_counts": {"reference": 1},
        "notes": [
            "Inline code examples should stay tied to concrete commands, file names, or parameter names.",
        ],
    },
}

_SOURCE_URLS = {
    "attributes": "https://dita-lang.org/1.3/dita/langref/attributes/attributes",
    "processing": "https://docs.oasis-open.org/dita/dita/v1.3/dita-v1.3-part1-base.html",
    "topicref": "https://dita-lang.org/dita/langref/base/topicref",
    "keydef": "https://dita-lang.org/dita/langref/base/keydef",
    "mapref": "https://dita-lang.org/dita/langref/base/mapref",
    "ditavalref": "https://dita-lang.org/dita/langref/base/ditavalref",
    "subjectdef": "https://dita-lang.org/dita/langref/base/subjectdef",
    "related-links": "https://dita-lang.org/1.3/dita/langref/base/related-links",
    "link": "https://docs.oasis-open.org/dita/v1.0/langspec/link.html",
    "relatedl": "https://docs.oasis-open.org/dita/v1.0/langspec/relatedl.html",
    "linkinfo": "https://docs.oasis-open.org/dita/v1.0/langspec/linkinfo.html",
    "linklist": "https://docs.oasis-open.org/dita/v1.0/langspec/linklist.html",
    "foreign": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/foreign.html",
    "data-about": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/data-about.html",
    "boolean": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/boolean.html",
    "data": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/data.html",
    "index-base": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/index-base.html",
    "itemgroup": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/itemgroup.html",
    "no-topic-nesting": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/no-topic-nesting.html",
    "state": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/state.html",
    "unknown": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/unknown.html",
    "required-cleanup": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/required-cleanup.html",
    "ditaval-elements": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/containers/ditaval-elements.html",
    "val": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-val.html",
    "prop": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-prop.html",
    "revprop": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-revprop.html",
    "startflag": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-startflag.html",
    "endflag": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-endflag.html",
    "alt-text": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-alt-text.html",
    "style-conflict": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-style-conflict.html",
}

_DETERMINISTIC_RECIPE_IDS: dict[str, str] = {
    "topicref": "maps.topicref_basic",
    "topichead": "maps.topichead_basic",
    "topicgroup": "maps.topicgroup_basic",
    "mapref": "maps.mapref_basic",
    "navref": "maps.navref_basic",
    "reltable": "maps.reltable_basic",
    "relrow": "maps.reltable_basic",
    "relcell": "maps.reltable_basic",
    "keyscope": "keyscope_demo",
    "xref": "xref_variety_bundle",
    "conref": "conref_pack",
    "conrefend": "conref_pack",
    "conkeyref": "dita_conref_keyref_dataset_recipe",
    "keyref": "keys.keydef_basic",
    "keys": "keys.keydef_basic",
    "keydef": "keys.keydef_basic",
    "subjectscheme": "dita_subject_scheme_dataset_recipe",
    "subjectdef": "dita_subject_scheme_dataset_recipe",
    "ditaval": "conditionals.audience_filter",
    "ditavalref": "conditionals.audience_filter",
    "related-links": "xref_variety_bundle",
    "link": "xref_variety_bundle",
    "linklist": "xref_variety_bundle",
    "linkinfo": "xref_variety_bundle",
    "refbody": "reference_topics",
    "refsyn": "reference_topics",
    "codeblock": "reference_topics",
    "codeph": "reference_topics",
}


def _patterns(*items: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(item, re.IGNORECASE) for item in items)


_COMMON_TOPIC_CONTEXT: dict[str, object] = {
    "construct_scope": "artifact",
    "valid_root_types": ["topic", "concept", "task", "reference"],
    "valid_artifact_types": ["topic", "concept", "task", "reference"],
    "compatible_topic_families": ["topic", "concept", "task", "reference"],
}


_MAP_CONTEXT: dict[str, object] = {
    "construct_scope": "bundle",
    "bundle_strategy": "map_bundle",
    "family_hint": "map",
    "include_map": True,
    "requires_contract_path": True,
    "valid_root_types": ["map", "bookmap"],
    "valid_artifact_types": ["ditamap"],
    "compatible_topic_families": ["map"],
}

_CONSTRUCT_PATTERN_MAP.update(
    {
        "conrefend": _patterns(r"\bconrefend\b", r"\bconref\s+range\b"),
        "related-links": _patterns(r"\brelated[- ]links?\b"),
        "link": _patterns(r"\b<link\b", r"\blink\s+element\b", r"\brelated\s+links?\b"),
        "relatedl": _patterns(r"\brelatedl\b", r"\brelated\s+links?\s+container\b"),
        "linkinfo": _patterns(r"\blinkinfo\b", r"\blink\s+info\b", r"\blink\s+description\b"),
        "linklist": _patterns(r"\blinklists?\b", r"\blink\s+lists?\b", r"\bgrouped\s+links?\b"),
        "foreign": _patterns(r"<foreign\b", r"\bforeign\s+element\b", r"\bnon[- ]dita\s+content\b", r"\bmathml\b", r"\bsvg\b"),
        "data-about": _patterns(r"<data-about\b", r"\bdata-about\b", r"\bdata\s+about\b"),
        "data": _patterns(r"<data(?:\s|>|/)", r"\bdata\s+element\b", r"\bmetadata\s+element\b"),
        "boolean": _patterns(r"<boolean\b", r"\bboolean\s+element\b", r"\bdeprecated\s+boolean\b"),
        "index-base": _patterns(r"<index-base\b", r"\bindex-base\b", r"\bindex\s+base\b"),
        "itemgroup": _patterns(r"<itemgroup\b", r"\bitemgroup\b", r"\bitem\s+group\b"),
        "no-topic-nesting": _patterns(r"<no-topic-nesting\b", r"\bno-topic-nesting\b", r"\bno\s+topic\s+nesting\b"),
        "state": _patterns(r"<state\b", r"\bstate\s+element\b", r"\bdita\s+state\b"),
        "unknown": _patterns(r"<unknown\b", r"\bunknown\s+element\b", r"\bdita\s+unknown\b"),
        "required-cleanup": _patterns(r"<required-cleanup\b", r"\brequired-cleanup\b", r"\brequired\s+cleanup\b"),
        "ditaval-elements": _patterns(r"\bditaval\s+elements?\b", r"<val\b", r"\bprop\s+revprop\b", r"\bstartflag\b", r"\bendflag\b"),
        "val": _patterns(r"<val\b", r"\bditaval\s+val\b", r"\bval\s+root\b", r"\bval\s+element\b"),
        "prop": _patterns(r"<prop\b", r"\bditaval\s+prop\b", r"\bprop\s+element\b", r"\bprofiling\s+property\s+rule\b"),
        "revprop": _patterns(r"<revprop\b", r"\bditaval\s+revprop\b", r"\brevprop\b", r"\brevision\s+property\s+rule\b"),
        "startflag": _patterns(r"<startflag\b", r"\bstartflag\b", r"\bstart\s+flag\b"),
        "endflag": _patterns(r"<endflag\b", r"\bendflag\b", r"\bend\s+flag\b"),
        "alt-text": _patterns(r"<alt-text\b", r"\balt-text\b", r"\balt\s+text\b", r"\bflag\s+alternate\s+text\b"),
        "style-conflict": _patterns(r"<style-conflict\b", r"\bstyle-conflict\b", r"\bstyle\s+conflict\b"),
        "keyref": _patterns(r"\bkeyref\b", r"\bkey references?\b"),
        "keys": _patterns(r"\bkeys\b", r"\bkey names?\b"),
        "keydef": _patterns(r"\bkeydefs?\b", r"\bkey definitions?\b"),
        "keyscope": _patterns(r"\bkeyscope\b", r"\bkey scopes?\b"),
        "topicref": _patterns(r"\btopicrefs?\b"),
        "topichead": _patterns(r"\btopicheads?\b"),
        "topicgroup": _patterns(r"\btopicgroups?\b"),
        "mapref": _patterns(r"\bmaprefs?\b", r"\bmap references?\b"),
        "navref": _patterns(r"\bnavrefs?\b"),
        "reltable": _patterns(r"\breltables?\b|\brelationship tables?\b"),
        "relrow": _patterns(r"\brelrows?\b"),
        "relcell": _patterns(r"\brelcells?\b"),
        "subjectdef": _patterns(r"\bsubjectdefs?\b"),
        "subjecthead": _patterns(r"\bsubjectheads?\b"),
        "enumerationdef": _patterns(r"\benumerationdefs?\b"),
        "attributedef": _patterns(r"\battributedefs?\b"),
        "ditavalref": _patterns(r"\bditavalrefs?\b", r"\bbranch filtering\b"),
        "reference": _patterns(r"\b<reference\b", r"\breference\s+element\b"),
        "properties": _patterns(r"\bproperties\b|\bproperty table\b"),
        "simpletable": _patterns(r"\bsimpletables?\b"),
        "section": _patterns(r"\bsections?\b"),
        "example": _patterns(r"\b<example\b", r"\bexample\s+element\b"),
        "note": _patterns(r"\b<note\b", r"\bnote\s+element\b"),
        "ph": _patterns(r"\bph\b|\bphrase\b"),
        "keyword": _patterns(r"\b<keyword\b", r"\bkeyword\s+element\b"),
        "term": _patterns(r"\b<term\b", r"\bterm\s+element\b"),
        "pre": _patterns(r"\bpreformatted\b|\bpre\b"),
        "msgblock": _patterns(r"\bmsgblocks?\b|\bmessage blocks?\b"),
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        "conref": {
            **_CONSTRUCT_LIBRARY["conref"],
            "construct_group": "reuse/linking",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["processing"],
            "required_companion_artifacts": ["reusable-source-topic", "consumer-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["conref_target_exists"],
        },
        "conrefend": {
            "category": "reuse",
            "construct_group": "reuse/linking",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["attributes"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_attributes": ["conref", "conrefend"],
            "required_companion_artifacts": ["range-source-topic", "consumer-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["conref_range_start_and_end_exist"],
            "example_counts": {"topic": 2},
            "notes": ["A conrefend example needs a range start and range end in compatible source content."],
        },
        "conkeyref": {
            **_CONSTRUCT_LIBRARY["conkeyref"],
            "construct_group": "reuse/linking",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["attributes"],
            "required_companion_artifacts": ["map-with-keydef", "reusable-source-topic", "consumer-topic"],
            "valid_root_types": _MAP_CONTEXT["valid_root_types"],
            "valid_artifact_types": _MAP_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _MAP_CONTEXT["compatible_topic_families"],
            "invalid_single_topic_reason": "conkeyref resolves through map-defined keys, so a standalone topic cannot demonstrate it correctly.",
            "validation_rules": ["conkeyref_keydef_exists", "conkeyref_target_id_exists"],
        },
        "xref": {
            **_CONSTRUCT_LIBRARY["xref"],
            "construct_group": "reuse/linking",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["processing"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["xref_target_exists_or_external_scope"],
        },
        "related-links": {
            "category": "linking",
            "construct_group": "reuse/linking",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["related-links"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["related-links", "link"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["related_link_target_exists_or_external_scope"],
            "example_counts": {"topic": 2},
            "notes": ["related-links should contain valid link targets rather than prose-only summaries."],
        },
        "link": {
            "category": "linking",
            "construct_group": "reuse/linking",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["link"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["related-links", "link"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["related_link_target_exists_or_external_scope"],
            "example_counts": {"topic": 2},
        },
        "relatedl": {
            "category": "linking",
            "construct_group": "reuse/linking",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["relatedl"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["related-links", "link"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["related_link_target_exists_or_external_scope"],
            "example_counts": {"topic": 2},
            "notes": ["relatedl is legacy DITA 1.0 related-link container terminology; modern output should use related-links."],
        },
        "linkinfo": {
            "category": "linking",
            "construct_group": "reuse/linking",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["linkinfo"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["related-links", "link", "linkinfo"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["related_link_target_exists_or_external_scope"],
            "example_counts": {"topic": 2},
            "notes": ["linkinfo should describe why a related link is useful; it should not replace normal topic prose."],
        },
        "linklist": {
            "category": "linking",
            "construct_group": "reuse/linking",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["linklist"],
            "bundle_strategy": "topic_bundle",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["related-links", "linklist", "link"],
            "required_companion_artifacts": ["source-topic", "target-topic"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": _COMMON_TOPIC_CONTEXT["compatible_topic_families"],
            "validation_rules": ["related_link_target_exists_or_external_scope"],
            "example_counts": {"topic": 2},
            "notes": ["linklist groups related links inside related-links; it is not a replacement for normal body lists."],
        },
        "foreign": {
            "category": "specialization_container",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["foreign"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["foreign"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["foreign_contains_non_dita_or_fallback"],
            "example_counts": {"topic": 1},
            "notes": ["foreign holds non-DITA vocabulary such as SVG or MathML; provide fallback when portability matters."],
        },
        "data": {
            "category": "metadata",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["data"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["data"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["data_metadata_not_visible_body_content"],
            "example_counts": {"topic": 1},
            "notes": ["data stores metadata in content flow and is ignored by default unless a processor or specialization uses it."],
        },
        "data-about": {
            "category": "metadata",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["data-about"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["data", "data-about"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["data_about_inside_data", "data_about_metadata_not_visible_body_content"],
            "example_counts": {"topic": 1},
            "notes": ["data-about identifies the subject of metadata stored in a data structure."],
        },
        "boolean": {
            "category": "deprecated_metadata",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["boolean"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["boolean"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["deprecated_element_requires_warning"],
            "example_counts": {"topic": 1},
            "notes": ["boolean is deprecated; explain legacy content and avoid creating new boolean markup unless explicitly requested."],
        },
        "index-base": {
            "category": "indexing",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["index-base"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["indexterm", "index-base"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["index_base_inside_indexterm", "index_base_ignored_unless_specialized"],
            "example_counts": {"topic": 1},
            "notes": ["index-base has no standalone processing meaning; it should only appear under indexterm and is mainly a specialization base."],
        },
        "itemgroup": {
            "category": "list_structure",
            "construct_group": "topic_structure",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["itemgroup"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["itemgroup"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["itemgroup_inside_list_item_context", "itemgroup_not_map_or_publishing_control"],
            "example_counts": {"topic": 1},
            "notes": ["itemgroup groups content inside list-item contexts and is mainly a specialization base."],
        },
        "no-topic-nesting": {
            "category": "grammar_configuration",
            "construct_group": "configuration",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["no-topic-nesting"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["no-topic-nesting"],
            "valid_root_types": ["configuration"],
            "valid_artifact_types": ["dtd", "mod", "rng"],
            "compatible_topic_families": [],
            "invalid_single_topic_reason": "no-topic-nesting belongs to grammar/configuration modules, not regular authored topic content.",
            "validation_rules": ["no_topic_nesting_only_in_grammar_configuration"],
            "example_counts": {"topic": 0},
            "notes": ["no-topic-nesting prevents nested topics in grammar/configuration contexts; do not generate it as topic body content."],
        },
        "state": {
            "category": "metadata",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["state"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["state"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["state_has_name_or_value_semantics", "state_not_aem_document_state"],
            "example_counts": {"topic": 1},
            "notes": ["state is DITA metadata/property markup; it is not AEM Guides workflow document state."],
        },
        "unknown": {
            "category": "migration_cleanup",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["unknown"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["unknown"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["unknown_used_only_for_migration_review"],
            "example_counts": {"topic": 1},
            "notes": ["unknown is a temporary migration/review element when source semantics are not known."],
        },
        "required-cleanup": {
            "category": "migration_cleanup",
            "construct_group": "metadata/extension",
            "construct_scope": "artifact",
            "source_url": _SOURCE_URLS["required-cleanup"],
            "bundle_strategy": "single_topic",
            "family_hint": "topic",
            "requires_contract_path": True,
            "required_elements": ["required-cleanup"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["required_cleanup_not_final_publish_content"],
            "example_counts": {"topic": 1},
            "notes": ["required-cleanup marks content that must be fixed before publication."],
        },
        "ditaval-elements": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["ditaval-elements"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "revprop"],
            "required_companion_artifacts": ["ditaval-profile", "map-branch-with-ditavalref"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "DITAVAL elements belong in .ditaval profile files, not topic body content.",
            "validation_rules": ["ditaval_elements_inside_val_profile", "ditavalref_references_profile"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
            "notes": ["DITAVAL elements define profile/filter rules in .ditaval files; maps reference them with ditavalref."],
        },
        "val": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["val"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "ditavalref"],
            "required_companion_artifacts": ["ditaval-profile-root", "map-branch-with-ditavalref", "filtered-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<val> is the root of a .ditaval profile file, not standalone topic body content.",
            "validation_rules": ["ditaval_val_root", "ditavalref_references_profile"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "prop": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["prop"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "ditavalref"],
            "required_attributes": ["att", "val", "action"],
            "required_companion_artifacts": ["ditaval-profile", "map-branch-with-ditavalref", "filtered-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<prop> belongs in a .ditaval profile under <val>, not in a standalone topic.",
            "validation_rules": ["ditaval_prop_inside_val", "ditaval_prop_has_att_action", "ditavalref_references_profile"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "revprop": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["revprop"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "revprop", "ditavalref"],
            "required_attributes": ["val", "action"],
            "required_companion_artifacts": ["ditaval-profile", "map-branch-with-ditavalref", "rev-marked-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<revprop> belongs in a .ditaval profile and filters or flags @rev-marked content.",
            "validation_rules": ["ditaval_revprop_inside_val", "revprop_targets_rev_values", "ditavalref_references_profile"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "startflag": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["startflag"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "startflag", "ditavalref"],
            "required_companion_artifacts": ["ditaval-profile-with-flagging", "map-branch-with-ditavalref", "flagged-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<startflag> belongs inside a DITAVAL <prop> or <revprop> rule, not topic content.",
            "validation_rules": ["startflag_inside_prop_or_revprop", "flag_rule_has_action_flag"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "endflag": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["endflag"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "endflag", "ditavalref"],
            "required_companion_artifacts": ["ditaval-profile-with-flagging", "map-branch-with-ditavalref", "flagged-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<endflag> belongs inside a DITAVAL <prop> or <revprop> rule, not topic content.",
            "validation_rules": ["endflag_inside_prop_or_revprop", "flag_rule_has_action_flag"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "alt-text": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["alt-text"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "prop", "startflag", "alt-text", "ditavalref"],
            "required_companion_artifacts": ["ditaval-profile-with-accessible-flag", "map-branch-with-ditavalref", "flagged-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<alt-text> is DITAVAL flag metadata under <startflag> or <endflag>, not a topic-body element.",
            "validation_rules": ["alt_text_inside_startflag_or_endflag", "flag_image_has_alternate_text"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
        "style-conflict": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["style-conflict"],
            "bundle_strategy": "map_bundle",
            "family_hint": "map",
            "include_map": True,
            "requires_contract_path": True,
            "required_elements": ["val", "style-conflict", "prop", "ditavalref"],
            "required_companion_artifacts": ["ditaval-profile-with-overlapping-flags", "map-branch-with-ditavalref", "flagged-topic"],
            "valid_root_types": ["val", "map"],
            "valid_artifact_types": ["ditaval", "ditamap", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "<style-conflict> belongs in a .ditaval profile for flagging-style conflict handling.",
            "validation_rules": ["style_conflict_inside_val", "style_conflict_only_for_flagging_styles"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
        },
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        name: {
            "category": category,
            "construct_group": group,
            "construct_scope": "artifact",
            "source_url": f"https://dita-lang.org/dita/langref/base/{name}",
            "bundle_strategy": "single_topic",
            "family_hint": family_hint,
            "requires_contract_path": requires_contract_path,
            "required_elements": [name],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": compatible_families,
            "preferred_structures": [name] if name in {"codeblock", "codeph", "pre", "msgblock"} else [],
            "validation_rules": validation_rules,
            "example_counts": {"reference" if family_hint == "reference" else "topic": 1},
        }
        for name, category, group, family_hint, requires_contract_path, compatible_families, validation_rules in [
            ("section", "topic_structure", "reference/code", "topic", False, ["topic", "concept", "task", "reference"], []),
            ("example", "topic_structure", "reference/code", "topic", False, ["topic", "concept", "task", "reference"], []),
            ("note", "topic_structure", "reference/code", "topic", False, ["topic", "concept", "task", "reference"], []),
            ("ph", "inline", "inline/code", "topic", False, ["topic", "concept", "task", "reference"], ["inline_context"]),
            ("keyword", "inline", "inline/code", "topic", False, ["topic", "concept", "task", "reference"], ["inline_context"]),
            ("term", "inline", "inline/code", "topic", False, ["topic", "concept", "task", "reference"], ["inline_context"]),
            ("pre", "code_formatting", "inline/code", "reference", True, ["topic", "concept", "task", "reference"], ["pre_in_block_context"]),
            ("msgblock", "code_formatting", "inline/code", "reference", True, ["topic", "concept", "task", "reference"], ["msgblock_in_block_context"]),
        ]
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        "codeblock": {
            **_CONSTRUCT_LIBRARY["codeblock"],
            "construct_group": "inline/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/codeblock",
            "required_elements": ["codeblock"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["codeblock_in_block_context"],
        },
        "codeph": {
            **_CONSTRUCT_LIBRARY["codeph"],
            "construct_group": "inline/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/codeph",
            "required_elements": ["codeph"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["topic", "concept", "task", "reference"],
            "validation_rules": ["codeph_in_inline_context"],
        },
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        "ditaval": {
            **_CONSTRUCT_LIBRARY["ditaval"],
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["ditavalref"],
            "required_companion_artifacts": ["ditaval-profile", "map-branch-with-ditavalref", "filtered-topic"],
            "valid_root_types": ["map", "val"],
            "valid_artifact_types": ["ditamap", "ditaval", "topic"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "DITAVAL filtering requires a profile and a map branch that references it.",
            "validation_rules": ["ditaval_file_exists", "ditavalref_references_profile"],
        },
        "ditavalref": {
            "category": "filtering",
            "construct_group": "filtering/taxonomy",
            "source_url": _SOURCE_URLS["ditavalref"],
            "required_elements": ["ditavalref"],
            "required_attributes": ["href", "format", "processing-role"],
            "preferred_structures": ["ditaval"],
            "required_companion_artifacts": ["ditaval-profile", "map-branch-with-ditavalref"],
            "validation_rules": ["ditavalref_references_profile", "ditavalref_format_is_ditaval"],
            "example_counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
            "invalid_single_topic_reason": "ditavalref is a map-branch filtering construct, not topic body content.",
            **_MAP_CONTEXT,
        },
        "reference": {
            "category": "reference_structure",
            "construct_group": "reference/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/reference",
            "bundle_strategy": "single_topic",
            "family_hint": "reference",
            "required_elements": ["reference", "refbody"],
            "valid_root_types": ["reference"],
            "valid_artifact_types": ["reference"],
            "compatible_topic_families": ["reference"],
            "example_counts": {"reference": 1},
        },
        "refbody": {
            **_CONSTRUCT_LIBRARY["refbody"],
            "construct_group": "reference/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/refbody",
            "valid_root_types": ["reference"],
            "valid_artifact_types": ["reference"],
            "compatible_topic_families": ["reference"],
        },
        "refsyn": {
            **_CONSTRUCT_LIBRARY["refsyn"],
            "construct_group": "reference/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/refsyn",
            "required_elements": ["refbody", "refsyn"],
            "valid_root_types": ["reference"],
            "valid_artifact_types": ["reference"],
            "compatible_topic_families": ["reference"],
            "validation_rules": ["refsyn_inside_reference"],
        },
        "properties": {
            "category": "reference_structure",
            "construct_group": "reference/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/properties",
            "bundle_strategy": "single_topic",
            "family_hint": "reference",
            "required_elements": ["refbody", "properties"],
            "valid_root_types": ["reference"],
            "valid_artifact_types": ["reference"],
            "compatible_topic_families": ["reference"],
            "example_counts": {"reference": 1},
        },
        "simpletable": {
            "category": "table",
            "construct_group": "reference/code",
            "construct_scope": "artifact",
            "source_url": "https://dita-lang.org/dita/langref/base/simpletable",
            "bundle_strategy": "single_topic",
            "family_hint": "reference",
            "required_elements": ["simpletable"],
            "valid_root_types": _COMMON_TOPIC_CONTEXT["valid_root_types"],
            "valid_artifact_types": _COMMON_TOPIC_CONTEXT["valid_artifact_types"],
            "compatible_topic_families": ["reference", "concept", "task", "topic"],
            "example_counts": {"reference": 1},
        },
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        "reltable": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["reltable", "relrow", "relcell", "topicref"],
            "validation_rules": ["reltable_has_relrow_relcell_topicrefs"],
            "example_counts": {"ditamap": 1, "topic": 3},
            **_MAP_CONTEXT,
        },
        "relrow": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["reltable", "relrow", "relcell", "topicref"],
            "validation_rules": ["reltable_has_relrow_relcell_topicrefs"],
            "example_counts": {"ditamap": 1, "topic": 3},
            **_MAP_CONTEXT,
        },
        "relcell": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["reltable", "relrow", "relcell", "topicref"],
            "validation_rules": ["reltable_has_relrow_relcell_topicrefs"],
            "example_counts": {"ditamap": 1, "topic": 3},
            **_MAP_CONTEXT,
        },
        "subjectscheme": {
            **_CONSTRUCT_LIBRARY["subjectscheme"],
            "construct_group": "filtering/taxonomy",
            "construct_scope": "bundle",
            "source_url": _SOURCE_URLS["subjectdef"],
            "required_elements": ["subjectScheme", "subjectdef", "enumerationdef", "attributedef"],
            "required_companion_artifacts": ["subject-scheme-map", "classified-topic-or-map"],
            "valid_root_types": ["subjectScheme"],
            "valid_artifact_types": ["subjectscheme"],
            "compatible_topic_families": ["map"],
            "invalid_single_topic_reason": "subjectScheme is a map-level taxonomy artifact, not a standalone topic.",
            "validation_rules": ["subjectscheme_root", "subjectdefs_exist", "enumeration_binding_exists"],
        },
        "subjectdef": {
            "category": "taxonomy",
            "construct_group": "filtering/taxonomy",
            "source_url": _SOURCE_URLS["subjectdef"],
            "required_elements": ["subjectScheme", "subjectdef"],
            "validation_rules": ["subjectdefs_exist"],
            "example_counts": {"subjectscheme": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
        "subjecthead": {
            "category": "taxonomy",
            "construct_group": "filtering/taxonomy",
            "source_url": _SOURCE_URLS["subjectdef"],
            "required_elements": ["subjectScheme", "subjectHead", "subjectdef"],
            "validation_rules": ["subjectheads_have_subjectdefs"],
            "example_counts": {"subjectscheme": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
        "enumerationdef": {
            "category": "taxonomy",
            "construct_group": "filtering/taxonomy",
            "source_url": _SOURCE_URLS["subjectdef"],
            "required_elements": ["subjectScheme", "enumerationdef", "attributedef", "subjectdef"],
            "validation_rules": ["enumeration_binding_exists"],
            "example_counts": {"subjectscheme": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
        "attributedef": {
            "category": "taxonomy",
            "construct_group": "filtering/taxonomy",
            "source_url": _SOURCE_URLS["subjectdef"],
            "required_elements": ["subjectScheme", "enumerationdef", "attributedef", "subjectdef"],
            "validation_rules": ["enumeration_binding_exists"],
            "example_counts": {"subjectscheme": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
    }
)

_CONSTRUCT_LIBRARY.update(
    {
        "keyref": {
            "category": "keys",
            "construct_group": "reuse/linking",
            "source_url": _SOURCE_URLS["attributes"],
            "required_attributes": ["keyref", "keys"],
            "required_elements": ["keydef", "topicref"],
            "required_companion_artifacts": ["map-with-keydef", "consumer-topic"],
            "validation_rules": ["keyref_keydef_exists"],
            "example_counts": {"ditamap": 1, "topic": 2},
            "invalid_single_topic_reason": "keyref is resolved from map-defined keys, so an example needs a map bundle.",
            **_MAP_CONTEXT,
        },
        "keys": {
            "category": "keys",
            "construct_group": "reuse/linking",
            "source_url": _SOURCE_URLS["attributes"],
            "required_attributes": ["keys"],
            "required_elements": ["keydef", "topicref"],
            "required_companion_artifacts": ["map-with-keydef"],
            "validation_rules": ["keys_defined_on_map_reference"],
            "example_counts": {"ditamap": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
        "keydef": {
            "category": "keys",
            "construct_group": "reuse/linking",
            "source_url": _SOURCE_URLS["keydef"],
            "required_attributes": ["keys"],
            "required_elements": ["keydef", "topicref"],
            "required_companion_artifacts": ["map-with-keydef", "consumer-topic"],
            "validation_rules": ["keydef_has_keys"],
            "example_counts": {"ditamap": 1, "topic": 1},
            **_MAP_CONTEXT,
        },
        "keyscope": {
            **_CONSTRUCT_LIBRARY.get("keyscope", {}),
            "category": "keys",
            "construct_group": "reuse/linking",
            "source_url": _SOURCE_URLS["attributes"],
            "required_attributes": ["keyscope", "keys", "keyref"],
            "required_elements": ["keydef", "topicref"],
            "required_companion_artifacts": ["root-map", "scoped-map-branch", "consumer-topic"],
            "validation_rules": ["scoped_keydefs_exist", "scoped_keyrefs_resolve"],
            "example_counts": {"ditamap": 2, "topic": 4},
            "invalid_single_topic_reason": "keyscope is resolved in maps and map branches, not in standalone topic content.",
            "notes": [
                "keyscope creates named map scopes for key definitions; consumers qualify keys from outside the scope with scope-name.key-name.",
                "A construct-true keyscope example needs map branches, key definitions, and consumer topics.",
            ],
            **_MAP_CONTEXT,
        },
        "topicref": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["topicref"],
            "required_attributes": ["href"],
            "validation_rules": ["topicref_targets_exist_or_external_scope"],
            "example_counts": {"ditamap": 1, "topic": 2},
            **_MAP_CONTEXT,
        },
        "topichead": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["topichead", "topicref"],
            "validation_rules": ["topichead_contains_navigation_branch"],
            "example_counts": {"ditamap": 1, "topic": 2},
            **_MAP_CONTEXT,
        },
        "topicgroup": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["topicgroup", "topicref"],
            "validation_rules": ["topicgroup_contains_topicrefs"],
            "example_counts": {"ditamap": 1, "topic": 2},
            **_MAP_CONTEXT,
        },
        "mapref": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["mapref"],
            "required_elements": ["mapref"],
            "required_attributes": ["href"],
            "required_companion_artifacts": ["parent-map", "child-map"],
            "validation_rules": ["mapref_target_map_exists"],
            "example_counts": {"ditamap": 2, "topic": 1},
            **_MAP_CONTEXT,
        },
        "navref": {
            "category": "map_structure",
            "construct_group": "maps",
            "source_url": _SOURCE_URLS["topicref"],
            "required_elements": ["navref"],
            "required_attributes": ["mapref"],
            "validation_rules": ["navref_target_exists"],
            "example_counts": {"ditamap": 2, "topic": 1},
            **_MAP_CONTEXT,
        },
    }
)

_DOMAIN_FOCUS_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "operations": (
        re.compile(r"\boperations?\b|\boperational\b|\badministration\b|\badmin\b|\brunbooks?\b", re.IGNORECASE),
    ),
    "architecture": (
        re.compile(r"\barchitecture\b|\bcomponents?\b|\btopology\b", re.IGNORECASE),
    ),
    "security": (
        re.compile(r"\bsecurity\b|\bhardening\b|\baccess control\b", re.IGNORECASE),
    ),
    "configuration": (
        re.compile(r"\bconfiguration\b|\bsettings\b|\bsetup\b", re.IGNORECASE),
    ),
    "troubleshooting": (
        re.compile(r"\btroubleshooting\b|\bdiagnostics\b|\bdebugging\b", re.IGNORECASE),
    ),
}

_DOMAIN_SUBTOPICS: dict[str, dict[str, list[str]]] = {
    "kubernetes": {
        "operations": [
            "deployment rollouts and rollout status",
            "pod logs and live diagnostics",
            "scaling workloads and replica management",
            "service exposure and ingress updates",
            "ConfigMap and Secret changes",
            "rollback and revision history",
            "namespace-scoped operations",
            "persistent volume operations",
            "node health and scheduling checks",
            "cluster maintenance and upgrade tasks",
        ],
        "architecture": [
            "control plane responsibilities",
            "worker node responsibilities",
            "pod scheduling flow",
            "service discovery and networking",
            "storage and persistent volume model",
        ],
        "security": [
            "RBAC and service account scope",
            "Secret handling and least privilege",
            "network policy boundaries",
            "admission control and policy enforcement",
            "image provenance and runtime hardening",
        ],
    },
}

_GENERIC_FOCUS_SUBTOPICS: dict[str, list[str]] = {
    "operations": [
        "setup and initialization",
        "routine execution",
        "monitoring and verification",
        "configuration changes",
        "maintenance and cleanup",
        "troubleshooting and recovery",
        "security checks",
        "integration touchpoints",
        "performance tuning",
        "governance and compliance",
    ],
    "architecture": [
        "core components and responsibilities",
        "data flow and processing boundaries",
        "dependencies and integration points",
        "scaling considerations",
        "resilience and recovery patterns",
    ],
    "security": [
        "authentication and authorization",
        "data protection controls",
        "policy boundaries",
        "audit and monitoring expectations",
        "hardening and safe defaults",
    ],
    "configuration": [
        "baseline settings",
        "advanced options",
        "environment-specific overrides",
        "validation checkpoints",
        "rollback considerations",
    ],
    "troubleshooting": [
        "symptom identification",
        "diagnostic inputs",
        "root cause isolation",
        "remediation sequence",
        "verification and follow-up",
    ],
}

_FAMILY_HINT_PRIORITY = {
    "map": 5,
    "reference": 4,
    "task": 3,
    "concept": 2,
    "topic": 1,
    "glossentry": 1,
}


def _normalize_construct_name(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())
    return normalized


def _detect_code_family_hint(text: str, explicit_family: str | None) -> str:
    if explicit_family and explicit_family not in {"auto", "topic"}:
        return explicit_family
    lowered = str(text or "").lower()
    if re.search(r"\b(how to|procedure|steps?|workflow)\b", lowered):
        return "task"
    if re.search(r"\b(commands?|syntax|parameters?|api|apis|response|responses)\b", lowered):
        return "reference"
    return "topic"


def _construct_family_hint(name: str, text: str, explicit_family: str | None) -> str | None:
    if name == "glossentry":
        return "glossentry"
    if name in {"codeblock", "codeph"}:
        return _detect_code_family_hint(text, explicit_family)
    if explicit_family and explicit_family not in {"auto", "topic"}:
        return explicit_family
    hint = _CONSTRUCT_LIBRARY.get(name, {}).get("family_hint")
    return str(hint or "").strip() or None


def infer_construct_semantics(
    *,
    text: str,
    element_names: list[str],
    attribute_names: list[str],
    preferred_structures: list[str],
    explicit_family: str | None,
) -> list[ConstructSemantic]:
    lowered_text = str(text or "")
    normalized_elements = {_normalize_construct_name(item) for item in element_names if str(item or "").strip()}
    normalized_attributes = {_normalize_construct_name(item) for item in attribute_names if str(item or "").strip()}
    normalized_structures = {_normalize_construct_name(item) for item in preferred_structures if str(item or "").strip()}

    semantics: list[ConstructSemantic] = []
    for canonical_name, patterns in _CONSTRUCT_PATTERN_MAP.items():
        matches_prompt = any(pattern.search(lowered_text) for pattern in patterns)
        if canonical_name == "reference" and explicit_family == "reference" and not matches_prompt:
            continue
        if canonical_name == "example" and not matches_prompt:
            continue
        if not matches_prompt and canonical_name not in normalized_elements and canonical_name not in normalized_attributes and canonical_name not in normalized_structures:
            continue
        spec = _CONSTRUCT_LIBRARY.get(canonical_name, {})
        family_hint = _construct_family_hint(canonical_name, lowered_text, explicit_family)
        semantics.append(
            ConstructSemantic(
                name=canonical_name,
                category=str(spec.get("category") or ""),
                construct_group=str(spec.get("construct_group") or spec.get("category") or ""),
                construct_scope=spec.get("construct_scope"),  # type: ignore[arg-type]
                source="prompt",
                source_url=str(spec.get("source_url") or "") or None,
                family_hint=family_hint,
                bundle_strategy=spec.get("bundle_strategy"),  # type: ignore[arg-type]
                include_map=bool(spec.get("include_map")),
                requires_contract_path=bool(spec.get("requires_contract_path")),
                required_elements=[str(item) for item in spec.get("required_elements", [])],
                required_attributes=[str(item) for item in spec.get("required_attributes", [])],
                required_companion_artifacts=[str(item) for item in spec.get("required_companion_artifacts", [])],
                valid_root_types=[str(item) for item in spec.get("valid_root_types", [])],
                valid_artifact_types=[str(item) for item in spec.get("valid_artifact_types", [])],
                compatible_topic_families=[str(item) for item in spec.get("compatible_topic_families", [])],
                preferred_structures=[str(item) for item in spec.get("preferred_structures", [])],
                example_counts={str(key): int(value) for key, value in dict(spec.get("example_counts", {})).items()},
                invalid_single_topic_reason=str(spec.get("invalid_single_topic_reason") or "") or None,
                canonical_demo_shape=str(spec.get("canonical_demo_shape") or ""),
                validation_rules=[str(item) for item in spec.get("validation_rules", [])],
                deterministic_recipe_id=str(spec.get("deterministic_recipe_id") or _DETERMINISTIC_RECIPE_IDS.get(canonical_name) or "") or None,
                notes=[str(item) for item in spec.get("notes", [])],
            )
        )

    def _priority(item: ConstructSemantic) -> tuple[int, int, str]:
        family_score = _FAMILY_HINT_PRIORITY.get(str(item.family_hint or ""), 0)
        bundle_score = 1 if item.bundle_strategy in {"map_bundle", "mixed_bundle"} else 0
        return (-bundle_score, -family_score, item.name)

    return sorted(semantics, key=_priority)


def primary_construct_semantic(constructs: list[ConstructSemantic]) -> ConstructSemantic | None:
    return constructs[0] if constructs else None


def get_construct_library_snapshot() -> dict[str, dict[str, object]]:
    """Return a read-only-ish copy of construct semantics for coverage audits."""
    snapshot: dict[str, dict[str, object]] = {}
    for name, spec in _CONSTRUCT_LIBRARY.items():
        record = dict(spec)
        if name in _DETERMINISTIC_RECIPE_IDS and "deterministic_recipe_id" not in record:
            record["deterministic_recipe_id"] = _DETERMINISTIC_RECIPE_IDS[name]
        snapshot[str(name)] = record
    return snapshot


def choose_family_hint(constructs: list[ConstructSemantic]) -> str | None:
    best_hint: str | None = None
    best_score = -1
    for item in constructs:
        score = _FAMILY_HINT_PRIORITY.get(str(item.family_hint or ""), 0)
        if score > best_score and item.family_hint:
            best_score = score
            best_hint = item.family_hint
    return best_hint


def infer_domain_decomposition(
    *,
    text: str,
    subject: str | None,
    count: int,
    constructs: list[ConstructSemantic],
) -> DomainDecomposition | None:
    clean_subject = re.sub(r"\s+", " ", str(subject or "").strip()).strip(" .,:;!?")
    if not clean_subject:
        return None

    if any(item.name == "glossentry" for item in constructs):
        return None

    lowered = f"{clean_subject} {text}".lower()
    focus: str | None = None
    for candidate, patterns in _DOMAIN_FOCUS_PATTERNS.items():
        if any(pattern.search(lowered) for pattern in patterns):
            focus = candidate
            break

    domain_key: str | None = None
    if re.search(r"\bkubernetes\b|\bk8s\b", lowered):
        domain_key = "kubernetes"

    subtopics: list[str] = []
    if domain_key and focus and focus in _DOMAIN_SUBTOPICS.get(domain_key, {}):
        subtopics = list(_DOMAIN_SUBTOPICS[domain_key][focus])
    elif focus and focus in _GENERIC_FOCUS_SUBTOPICS:
        subtopics = [f"{clean_subject} {item}" for item in _GENERIC_FOCUS_SUBTOPICS[focus]]

    if not subtopics:
        return None

    target_count = max(1, count)
    return DomainDecomposition(
        source="heuristic",
        focus=focus,
        subtopics=subtopics[:target_count],
        reason=f"Expanded `{clean_subject}` into {focus} subtopics for more distinct DITA planning.",
    )
