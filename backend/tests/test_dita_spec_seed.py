import json
from pathlib import Path

from app.services import dita_knowledge_retriever
from app.services.dita_construct_semantics_service import infer_construct_semantics
from app.services.dita_attribute_catalog import get_attribute_spec
from app.services.dita_spec_registry_service import get_element_spec


def _seed_entries() -> dict[str, dict]:
    seed_path = Path(__file__).resolve().parents[1] / "app" / "storage" / "dita_spec_seed.json"
    data = json.loads(seed_path.read_text(encoding="utf-8"))
    return {str(item.get("element_name") or ""): item for item in data if isinstance(item, dict)}


def test_dita_seed_includes_oasis_dita_12_bookmap_langref_pages():
    entries = _seed_entries()
    expected_sources = {
        "bookmap": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bookmap.html",
        "toc_attribute": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/toc.html",
        "abbrevlist": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/abbrevlist.html",
        "amendments": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/amendments.html",
        "appendices": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/appendices.html",
        "appendix": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/appendix.html",
        "backmatter": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/backmatter.html",
        "bibliolist": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bibliolist.html",
        "bookabstract": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bookabstract.html",
        "booklibrary": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklibrary.html",
        "booklist": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklist.html",
        "booklists": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklists.html",
        "booktitle": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booktitle.html",
        "booktitlealt": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booktitlealt.html",
        "dedication": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/dedication.html",
        "colophon": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/colophon.html",
        "draftintro": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/draftintro.html",
        "figurelist": "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/figurelist.html",
    }

    for element_name, source_url in expected_sources.items():
        assert element_name in entries
        assert entries[element_name]["source_url"] == source_url


def test_toc_attribute_catalog_uses_oasis_source_url():
    toc = get_attribute_spec("toc")

    assert toc is not None
    assert toc.source_url == "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/toc.html"
    assert toc.semantic_class in {"map_scoped", "boolean_like"}
    assert {"yes", "no"}.issubset(set(toc.all_valid_values))
    assert toc.correct_examples
    assert any("toc=" in ex for ex in toc.correct_examples)
    assert any("topicref" in ex for ex in toc.correct_examples)


def test_bookmap_registry_includes_requested_oasis_bookmap_elements():
    for name in (
        "bookmap",
        "abbrevlist",
        "amendments",
        "appendices",
        "appendix",
        "backmatter",
        "bibliolist",
        "bookabstract",
        "booklibrary",
        "booklist",
        "booklists",
        "booktitle",
        "booktitlealt",
        "dedication",
        "colophon",
        "draftintro",
        "figurelist",
    ):
        spec = get_element_spec(name)
        assert spec is not None
        assert spec.source_url.startswith("https://docs.oasis-open.org/dita/v1.2/os/spec/langref/")


def test_dita_retrieval_boost_terms_include_bookmap_langref_elements():
    for term in (
        "bookmap",
        "abbrevlist",
        "amendments",
        "appendices",
        "appendix",
        "backmatter",
        "bibliolist",
        "bookabstract",
        "booklibrary",
        "booklist",
        "booklists",
        "booktitle",
        "booktitlealt",
        "dedication",
        "colophon",
        "draftintro",
        "figurelist",
    ):
        assert term in dita_knowledge_retriever.DITA_BOOST_TERMS


def test_dita_seed_includes_related_links_family_reference_pages():
    entries = _seed_entries()
    expected_sources = {
        "related-links": "https://dita-lang.org/1.3/dita/langref/base/related-links",
        "link": "https://docs.oasis-open.org/dita/v1.0/langspec/link.html",
        "relatedl": "https://docs.oasis-open.org/dita/v1.0/langspec/relatedl.html",
        "linkinfo": "https://docs.oasis-open.org/dita/v1.0/langspec/linkinfo.html",
        "linklist": "https://docs.oasis-open.org/dita/v1.0/langspec/linklist.html",
    }

    for element_name, source_url in expected_sources.items():
        assert element_name in entries
        assert entries[element_name]["source_url"] == source_url
        assert entries[element_name]["metadata"]["source_url"] == source_url


def test_related_links_family_registry_exposes_linklist_structure():
    spec = get_element_spec("linklist")

    assert spec is not None
    assert spec.source_url == "https://docs.oasis-open.org/dita/v1.0/langspec/linklist.html"
    assert "title" in spec.allowed_children
    assert "link" in spec.allowed_children
    assert "related-links" in spec.allowed_parents


def test_dita_retrieval_boost_terms_include_related_links_family():
    for term in ("related-links", "relatedl", "link", "linklist", "linkinfo"):
        assert term in dita_knowledge_retriever.DITA_BOOST_TERMS


def test_dita_seed_includes_oasis_dita_13_metadata_extension_pages():
    entries = _seed_entries()
    expected_sources = {
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
        "id_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/idAttributes.html",
        "metadata_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/metadataAttributes.html",
        "localization_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html",
        "debug_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/debugAttributes.html",
        "architectural_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/architecturalAttributes.html",
        "common_map_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html",
        "cals_table_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/calsTableAttributes.html",
        "display_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts",
        "date_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/dateAttributes.html",
        "link_relationship_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/linkRelationshipAttributes.html",
        "common_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html",
        "simpletable_attributes": "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html",
    }

    for element_name, source_url in expected_sources.items():
        assert element_name in entries
        assert entries[element_name]["source_url"] == source_url
        assert entries[element_name]["metadata"]["source_url"] == source_url


def test_oasis_metadata_extension_registry_exposes_key_semantics():
    foreign = get_element_spec("foreign")
    data_about = get_element_spec("data-about")
    boolean = get_element_spec("boolean")
    index_base = get_element_spec("index-base")
    itemgroup = get_element_spec("itemgroup")
    no_topic_nesting = get_element_spec("no-topic-nesting")
    state = get_element_spec("state")
    unknown = get_element_spec("unknown")
    required_cleanup = get_element_spec("required-cleanup")
    ditaval_elements = get_element_spec("ditaval-elements")
    val = get_element_spec("val")
    prop = get_element_spec("prop")
    revprop = get_element_spec("revprop")
    startflag = get_element_spec("startflag")
    endflag = get_element_spec("endflag")
    alt_text = get_element_spec("alt-text")
    style_conflict = get_element_spec("style-conflict")

    assert foreign is not None
    assert foreign.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/foreign.html"
    assert "non-DITA content" in foreign.description

    assert data_about is not None
    assert data_about.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/data-about.html"
    assert "data" in data_about.allowed_parents

    assert boolean is not None
    assert boolean.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/boolean.html"
    assert "deprecated" in boolean.description.lower()

    assert index_base is not None
    assert index_base.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/index-base.html"
    assert index_base.parent_element == "indexterm"
    assert "indexterm" in index_base.allowed_parents

    assert itemgroup is not None
    assert itemgroup.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/itemgroup.html"
    assert "list item" in itemgroup.description.lower()

    assert no_topic_nesting is not None
    assert no_topic_nesting.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/no-topic-nesting.html"
    assert "nested topics" in no_topic_nesting.description.lower()

    assert state is not None
    assert state.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/state.html"
    assert "metadata" in state.description.lower()

    assert unknown is not None
    assert unknown.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/unknown.html"
    assert "migration" in unknown.description.lower()

    assert required_cleanup is not None
    assert required_cleanup.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/required-cleanup.html"
    assert "cleanup" in required_cleanup.description.lower()

    assert ditaval_elements is not None
    assert ditaval_elements.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/containers/ditaval-elements.html"
    assert "prop" in ditaval_elements.allowed_children

    assert val is not None
    assert val.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-val.html"
    assert "prop" in val.allowed_children

    assert prop is not None
    assert prop.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-prop.html"
    assert "startflag" in prop.allowed_children

    assert revprop is not None
    assert revprop.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-revprop.html"
    assert "endflag" in revprop.allowed_children

    assert startflag is not None
    assert startflag.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-startflag.html"
    assert "alt-text" in startflag.allowed_children

    assert endflag is not None
    assert endflag.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-endflag.html"
    assert "alt-text" in endflag.allowed_children

    assert alt_text is not None
    assert alt_text.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-alt-text.html"
    assert "alternate text" in alt_text.description.lower()

    assert style_conflict is not None
    assert style_conflict.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-style-conflict.html"
    assert "conflicting" in style_conflict.description.lower()


def test_dita_retrieval_boost_terms_include_oasis_metadata_extension_pages():
    for term in (
        "foreign",
        "data",
        "data-about",
        "boolean",
        "index-base",
        "itemgroup",
        "no-topic-nesting",
        "state",
        "unknown",
        "required-cleanup",
        "ditaval-elements",
        "val",
        "prop",
        "revprop",
        "startflag",
        "endflag",
        "alt-text",
        "style-conflict",
        "id attributes",
        "metadata attributes",
        "localization attributes",
        "debug attributes",
        "architectural attributes",
        "common map attributes",
        "cals table attributes",
        "display attributes",
        "date attributes",
        "link relationship attributes",
        "common attributes",
        "simpletable attributes",
        "expanse",
        "frame",
        "scale",
        "expiry",
        "golive",
        "role",
        "otherrole",
        "base",
        "status",
        "keycol",
        "relcolwidth",
        "refcols",
    ):
        assert term in dita_knowledge_retriever.DITA_BOOST_TERMS
    for element in (
        "foreign",
        "data",
        "data-about",
        "boolean",
        "index-base",
        "itemgroup",
        "no-topic-nesting",
        "state",
        "unknown",
        "required-cleanup",
        "ditaval-elements",
        "val",
        "prop",
        "revprop",
        "startflag",
        "endflag",
        "alt-text",
        "style-conflict",
        "id attributes",
        "metadata attributes",
        "localization attributes",
        "debug attributes",
        "architectural attributes",
        "common map attributes",
        "cals table attributes",
        "display attributes",
        "date attributes",
        "link relationship attributes",
        "common attributes",
        "simpletable attributes",
        "expanse",
        "frame",
        "scale",
        "expiry",
        "golive",
        "role",
        "otherrole",
        "base",
        "status",
        "keycol",
        "relcolwidth",
        "refcols",
        "indexterm",
    ):
        assert element in dita_knowledge_retriever.DITA_ELEMENT_NAMES


def test_construct_semantics_detect_oasis_metadata_extension_constructs():
    semantics = infer_construct_semantics(
        text=(
            "Generate a topic with <foreign>, data-about, boolean element, index-base, itemgroup, "
            "<state>, <unknown>, required-cleanup, no-topic-nesting, and DITAVAL elements "
            "including <val>, DITAVAL prop, revprop, startflag, endflag, alt-text, and style-conflict."
        ),
        element_names=[],
        attribute_names=[],
        preferred_structures=[],
        explicit_family=None,
    )
    by_name = {item.name: item for item in semantics}

    assert by_name["foreign"].source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/foreign.html"
    assert by_name["data-about"].validation_rules == [
        "data_about_inside_data",
        "data_about_metadata_not_visible_body_content",
    ]
    assert "deprecated_element_requires_warning" in by_name["boolean"].validation_rules
    assert "index_base_inside_indexterm" in by_name["index-base"].validation_rules
    assert "itemgroup_inside_list_item_context" in by_name["itemgroup"].validation_rules
    assert "no_topic_nesting_only_in_grammar_configuration" in by_name["no-topic-nesting"].validation_rules
    assert "state_not_aem_document_state" in by_name["state"].validation_rules
    assert "unknown_used_only_for_migration_review" in by_name["unknown"].validation_rules
    assert "required_cleanup_not_final_publish_content" in by_name["required-cleanup"].validation_rules
    assert by_name["ditaval-elements"].construct_scope == "bundle"
    assert by_name["val"].source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-val.html"
    assert "ditaval_val_root" in by_name["val"].validation_rules
    assert by_name["prop"].source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-prop.html"
    assert "ditaval_prop_inside_val" in by_name["prop"].validation_rules
    assert by_name["revprop"].source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-revprop.html"
    assert "ditaval_revprop_inside_val" in by_name["revprop"].validation_rules
    assert "startflag_inside_prop_or_revprop" in by_name["startflag"].validation_rules
    assert "endflag_inside_prop_or_revprop" in by_name["endflag"].validation_rules
    assert "alt_text_inside_startflag_or_endflag" in by_name["alt-text"].validation_rules
    assert "style_conflict_inside_val" in by_name["style-conflict"].validation_rules


def test_oasis_attribute_group_catalog_sources_are_grounded():
    id_attr = get_attribute_spec("id")
    audience = get_attribute_spec("audience")
    delivery_target = get_attribute_spec("deliveryTarget")
    xml_lang = get_attribute_spec("xml:lang")
    direction = get_attribute_spec("dir")
    translate = get_attribute_spec("translate")
    xtrf = get_attribute_spec("xtrf")
    xtrc = get_attribute_spec("xtrc")
    class_attr = get_attribute_spec("class")
    domains = get_attribute_spec("domains")
    processing_role = get_attribute_spec("processing-role")
    collection_type = get_attribute_spec("collection-type")
    colsep = get_attribute_spec("colsep")
    align = get_attribute_spec("align")
    expanse = get_attribute_spec("expanse")
    frame = get_attribute_spec("frame")
    scale = get_attribute_spec("scale")
    expiry = get_attribute_spec("expiry")
    golive = get_attribute_spec("golive")
    role = get_attribute_spec("role")
    otherrole = get_attribute_spec("otherrole")
    status = get_attribute_spec("status")
    outputclass = get_attribute_spec("outputclass")
    keycol = get_attribute_spec("keycol")
    relcolwidth = get_attribute_spec("relcolwidth")
    refcols = get_attribute_spec("refcols")

    assert id_attr is not None
    assert id_attr.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/idAttributes.html"
    assert id_attr.semantic_class == "open_token"

    assert audience is not None
    assert audience.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/metadataAttributes.html"
    assert audience.semantic_class == "open_token"

    assert delivery_target is not None
    assert delivery_target.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/metadataAttributes.html"

    assert xml_lang is not None
    assert xml_lang.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html"
    assert xml_lang.semantic_class == "open_token"

    assert direction is not None
    assert direction.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html"
    assert {"ltr", "rtl"}.issubset(set(direction.all_valid_values))

    assert translate is not None
    assert translate.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html"
    assert {"yes", "no"}.issubset(set(translate.all_valid_values))

    assert xtrf is not None
    assert xtrf.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/debugAttributes.html"
    assert xtrf.semantic_class == "open_token"

    assert xtrc is not None
    assert xtrc.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/debugAttributes.html"

    assert class_attr is not None
    assert class_attr.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/architecturalAttributes.html"
    assert class_attr.semantic_class == "open_token"

    assert domains is not None
    assert domains.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/architecturalAttributes.html"

    assert processing_role is not None
    assert processing_role.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html"
    assert processing_role.semantic_class == "map_scoped"
    assert {"normal", "resource-only"}.issubset(set(processing_role.all_valid_values))

    assert collection_type is not None
    assert collection_type.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html"
    assert {"sequence", "family"}.issubset(set(collection_type.all_valid_values))

    assert colsep is not None
    assert colsep.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/calsTableAttributes.html"
    assert {"0", "1"}.issubset(set(colsep.all_valid_values))

    assert align is not None
    assert align.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/calsTableAttributes.html"
    assert {"left", "right", "center"}.issubset(set(align.all_valid_values))

    assert expanse is not None
    assert expanse.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts"
    assert {"page", "column", "textline"}.issubset(set(expanse.all_valid_values))

    assert frame is not None
    assert frame.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts"
    assert {"all", "none"}.issubset(set(frame.all_valid_values))

    assert scale is not None
    assert scale.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts"
    assert scale.semantic_class == "open_token"

    assert expiry is not None
    assert expiry.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/dateAttributes.html"

    assert golive is not None
    assert golive.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/dateAttributes.html"

    assert role is not None
    assert role.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/linkRelationshipAttributes.html"
    assert role.semantic_class == "open_token"
    assert "normal" not in role.all_valid_values

    assert otherrole is not None
    assert otherrole.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/linkRelationshipAttributes.html"

    assert status is not None
    assert status.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html"
    assert {"new", "changed", "deleted"}.issubset(set(status.all_valid_values))

    assert outputclass is not None
    assert outputclass.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html"

    assert keycol is not None
    assert keycol.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html"

    assert relcolwidth is not None
    assert relcolwidth.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html"

    assert refcols is not None
    assert refcols.source_url == "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html"
