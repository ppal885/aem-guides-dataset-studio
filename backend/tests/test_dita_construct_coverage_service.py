from app.services.dita_construct_coverage_service import (
    TOP_VALUE_CONSTRUCTS,
    build_dita_construct_coverage_report,
    coverage_for_construct,
    known_attribute_names,
    known_construct_names,
    verified_examples_for_construct,
)
from app.services.dita_construct_semantics_service import infer_construct_semantics


def test_coverage_matrix_has_core_top_value_constructs():
    report = build_dita_construct_coverage_report(
        names=[
            "topichead",
            "topicgroup",
            "linklist",
            "keyscope",
            "conkeyref",
            "xref",
            "codeblock",
            "ditavalref",
        ],
        include_attributes=False,
    )

    assert report.ok
    strategies = {entry.name: entry.generation_strategy for entry in report.entries}
    assert strategies["topichead"] == "deterministic:maps.topichead_basic"
    assert strategies["topicgroup"] == "deterministic:maps.topicgroup_basic"
    assert strategies["keyscope"] == "deterministic:keyscope_demo"
    assert strategies["xref"] == "deterministic:xref_variety_bundle"


def test_verified_example_registry_supplies_construct_true_linklist_snippet():
    examples = verified_examples_for_construct("linklist")

    assert examples
    assert any("<related-links>" in item.snippet and "<linklist>" in item.snippet for item in examples)
    assert any(item.source in {"spec_registry", "deterministic_template"} for item in examples)


def test_publishing_sensitive_constructs_use_dita_processor_policy():
    coverage = coverage_for_construct("topicgroup")

    assert coverage.coverage_status == "strong"
    assert coverage.publishing_source_policy == "dita_spec_first_then_processor_docs"
    assert coverage.example_source


def test_construct_semantics_expose_deterministic_recipe_id():
    semantics = infer_construct_semantics(
        text="Generate a topicgroup example bundle",
        element_names=[],
        attribute_names=[],
        preferred_structures=[],
        explicit_family=None,
    )

    topicgroup = next(item for item in semantics if item.name == "topicgroup")
    assert topicgroup.deterministic_recipe_id == "maps.topicgroup_basic"


def test_top_value_construct_registry_contains_no_accidental_empty_names():
    assert TOP_VALUE_CONSTRUCTS
    assert all(name and name == name.strip().lower() for name in TOP_VALUE_CONSTRUCTS)


def test_top_value_constructs_have_generation_decision_or_explicit_block():
    report = build_dita_construct_coverage_report(include_attributes=False)

    missing = [
        entry.name
        for entry in report.entries
        if entry.name in TOP_VALUE_CONSTRUCTS and entry.generation_strategy == "missing"
    ]
    assert missing == []


def test_default_coverage_report_scans_full_known_registry_not_only_top_value_subset():
    report = build_dita_construct_coverage_report(include_attributes=True)
    element_names = {entry.name for entry in report.entries if entry.item_type == "element"}
    attribute_names = {entry.name for entry in report.entries if entry.item_type == "attribute"}

    assert set(TOP_VALUE_CONSTRUCTS) <= element_names
    assert len(element_names) > len(TOP_VALUE_CONSTRUCTS)
    assert "taskbody" in element_names
    assert "choicetable" in element_names
    assert set(known_construct_names()) <= element_names
    assert set(known_attribute_names()) <= attribute_names
