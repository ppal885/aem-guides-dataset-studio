from app.services.dita_query_interpreter import interpret_dita_query
from app.services.dita_spec_registry_service import get_element_spec, list_element_names


def test_list_element_names_comes_from_registry_not_static_hand_list():
    names = list_element_names()

    assert "taskbody" in names
    assert "choicetable" in names
    assert "topic" in names


def test_get_element_spec_merges_children_parents_and_examples():
    spec = get_element_spec("choicetable")

    assert spec is not None
    assert spec.name == "choicetable"
    assert "chrow" in spec.allowed_children
    assert "step" in spec.allowed_parents
    assert "relcolwidth" in spec.supported_attributes
    assert spec.common_mistakes
    assert spec.correct_examples


def test_topicgroup_has_verified_map_example_and_output_semantics():
    spec = get_element_spec("topicgroup")

    assert spec is not None
    assert spec.name == "topicgroup"
    assert "topicref" in spec.allowed_children
    assert "topicgroup" in spec.allowed_children
    assert "map" in spec.allowed_parents
    assert any("should not become a standalone heading" in item for item in spec.usage_contexts)
    assert any("<topicgroup>" in item and "<topicref" in item for item in spec.correct_examples)


def test_interpret_dita_query_detects_content_model_and_placement():
    content_intent = interpret_dita_query("What can go inside taskbody?")
    placement_intent = interpret_dita_query("Where can choicetable appear?")

    assert content_intent.mode == "content_model_query"
    assert content_intent.element_names == ["taskbody"]
    assert placement_intent.mode == "allowed_usage_query"
    assert placement_intent.element_names == ["choicetable"]


def test_interpret_dita_query_detects_attribute_and_element_comparisons():
    attr_intent = interpret_dita_query("conref vs conkeyref")
    element_intent = interpret_dita_query("task vs concept")

    assert attr_intent.mode == "attribute_comparison"
    assert attr_intent.attribute_names == ["conref", "conkeyref"]
    assert element_intent.mode == "element_comparison"
    assert element_intent.element_names == ["task", "concept"]


def test_fig_merges_fig_element_rows_including_figgroup_children():
    spec = get_element_spec("fig")

    assert spec is not None
    assert spec.name == "fig"
    assert "figgroup" in spec.allowed_children
    assert "simpletable" in spec.allowed_children
    assert spec.source_url and "langref/base/fig" in spec.source_url


def test_figgroup_registry_from_seed():
    spec = get_element_spec("figgroup")

    assert spec is not None
    assert "image" in spec.allowed_children
    assert spec.source_url and "figgroup" in spec.source_url
