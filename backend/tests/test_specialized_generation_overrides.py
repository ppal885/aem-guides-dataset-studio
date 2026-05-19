from app.generator.specialized import (
    generate_concept_topics_dataset,
    generate_glossary_dataset,
    generate_reference_topics_dataset,
    generate_topic_topics_dataset,
)
from app.generator.generate import sanitize_filename
from app.generator.external_keydef_xref import generate_external_keydef_xref_bundle
from app.generator.keyscope_demo import generate_keyscope_demo_dataset
from app.generator.xref_variety import generate_xref_variety_bundle
from app.jobs.schemas import DatasetConfig


def _config() -> DatasetConfig:
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_reference_topics_dataset_uses_content_overrides():
    files = generate_reference_topics_dataset(
        _config(),
        "/tmp",
        topic_count=2,
        include_map=False,
        rand=None,
        content_titles=["Cars reference 01", "Cars reference 02"],
        content_shortdescs=["Reference details for cars 01.", "Reference details for cars 02."],
        content_property_seeds=["cars-01", "cars-02"],
        content_detail_snippets=[
            "Detailed reference information for the cars 01 domain.",
            "Detailed reference information for the cars 02 domain.",
        ],
    )

    text = b"\n".join(files.values()).decode("utf-8", errors="ignore")
    assert "Cars reference 01" in text
    assert "Reference details for cars 01." in text
    assert "cars-01.setting.1" in text
    assert "Detailed reference information for the cars 01 domain." in text


def test_reference_topics_dataset_renders_requested_yaml_codeblock_and_table_dimensions():
    files = generate_reference_topics_dataset(
        _config(),
        "/tmp",
        topic_count=2,
        include_map=False,
        rand=None,
        content_titles=["Kubernetes rollouts", "Kubernetes logs"],
        structure_requirements=[
            {"structure_name": "codeblock", "language": "yaml"},
            {"structure_name": "table", "columns": 5, "rows": 6},
        ],
    )

    topic_xmls = [
        content.decode("utf-8", errors="ignore")
        for path, content in sorted(files.items())
        if str(path).endswith(".dita")
    ]

    assert len(topic_xmls) == 2
    assert all('outputclass="language-yaml"' in text for text in topic_xmls)
    assert all('cols="5"' in text for text in topic_xmls)
    assert all(text.count("<row") >= 6 for text in topic_xmls)
    assert "Kubernetes rollouts R6C5" in topic_xmls[0]
    assert "Kubernetes logs R6C5" in topic_xmls[1]


def test_external_keydef_xref_bundle_uses_map_keydef_and_topic_keyref():
    files = generate_external_keydef_xref_bundle(
        _config(),
        "/tmp",
        key_name="external-docs",
        href="https://example.com/docs",
        format="html",
        scope="external",
    )

    map_xml = next(content.decode("utf-8", errors="ignore") for path, content in files.items() if str(path).endswith(".ditamap"))
    topic_xml = next(content.decode("utf-8", errors="ignore") for path, content in files.items() if str(path).endswith(".dita"))

    assert '<keydef keys="external-docs" href="https://example.com/docs" scope="external" format="html">' in map_xml
    assert "<linktext>External documentation</linktext>" in map_xml
    assert '<xref keyref="external-docs">External documentation</xref>' in topic_xml
    assert "<xref href=" not in topic_xml


def test_xref_variety_bundle_contains_same_cross_external_and_keyed_xrefs():
    files = generate_xref_variety_bundle(_config(), "/tmp")

    map_xml = next(content.decode("utf-8", errors="ignore") for path, content in files.items() if str(path).endswith(".ditamap"))
    topic_xmls = [
        content.decode("utf-8", errors="ignore")
        for path, content in files.items()
        if str(path).endswith(".dita")
    ]
    bundle_text = "\n".join([map_xml, *topic_xmls])

    assert len(topic_xmls) == 2
    assert '<keydef keys="external-docs" href="https://example.com/docs" scope="external" format="html">' in map_xml
    assert '<xref keyref="external-docs">external documentation</xref>' in bundle_text
    assert 'href="#' in bundle_text
    assert 'href="xref_targets.dita"' in bundle_text
    assert 'href="xref_targets.dita#' in bundle_text
    assert 'href="https://example.com/guide.html" scope="external" format="html"' in bundle_text
    assert 'href="resources/runbook.pdf" scope="local" format="pdf"' in bundle_text
    assert 'href="https://example.com/spec.docx" scope="external" format="doc"' in bundle_text
    assert "<related-links>" in bundle_text


def test_generic_topic_dataset_uses_subject_aware_content_overrides():
    files = generate_topic_topics_dataset(
        _config(),
        "/tmp",
        topic_count=2,
        include_map=False,
        rand=None,
        content_titles=["Cars overview 01", "Cars features 02"],
        content_shortdescs=["Plain-topic guidance related to cars.", "Plain-topic guidance related to cars."],
        content_body_snippets=[
            "This topic focuses on cars and highlights overview details that matter when documenting cars in DITA.",
            "This topic focuses on cars and highlights feature details that matter when documenting cars in DITA.",
        ],
    )

    text = b"\n".join(files.values()).decode("utf-8", errors="ignore")
    assert "<!DOCTYPE topic" in text
    assert "Cars overview 01" in text
    assert "Plain-topic guidance related to cars." in text
    assert "documenting cars in DITA" in text


def test_generic_topic_dataset_uses_safe_requested_filename_and_map_href():
    files = generate_topic_topics_dataset(
        _config(),
        "/tmp",
        topic_count=1,
        include_map=True,
        rand=None,
        content_titles=["Policy special filename"],
        content_filenames=["Policy_ A&B _draft__.dita"],
    )

    assert any(str(path).endswith("Policy_ A&B _draft__.dita") for path in files)
    map_xml = next(content.decode("utf-8", errors="ignore") for path, content in files.items() if str(path).endswith(".ditamap"))
    assert 'href="topics/generic/Policy_ A&amp;B _draft__.dita"' in map_xml


def test_sanitize_filename_handles_reserved_and_trailing_windows_names():
    assert sanitize_filename("CON.dita", True) == "CON_file.dita"
    assert sanitize_filename("topic name. ", True) == "topic name"
    assert sanitize_filename('A:B<C>?*.dita', True) == "A_B_C___.dita"


def test_glossary_dataset_uses_content_overrides():
    files = generate_glossary_dataset(
        _config(),
        "/tmp",
        entry_count=2,
        rand=None,
        content_terms=["Cars term 01", "Cars term 02"],
        content_definitions=[
            "A glossary definition covering cars terminology item 01.",
            "A glossary definition covering cars terminology item 02.",
        ],
        content_acronyms=["C01", "C02"],
    )

    text = b"\n".join(files.values()).decode("utf-8", errors="ignore")
    assert "Cars term 01" in text
    assert "A glossary definition covering cars terminology item 01." in text
    assert "C01" in text


def test_concept_topics_dataset_uses_concept_doctype():
    files = generate_concept_topics_dataset(
        _config(),
        "/tmp",
        topic_count=1,
        include_map=False,
        rand=None,
        content_titles=["Cars concept 01"],
    )

    topic_xml = next(content.decode("utf-8", errors="ignore") for _, content in files.items())
    assert '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN"' in topic_xml


def test_concept_topics_dataset_applies_distinct_body_snippets_per_topic():
    files = generate_concept_topics_dataset(
        _config(),
        "/tmp",
        topic_count=2,
        include_map=False,
        rand=None,
        content_titles=["Cars architecture concept 01", "Cars maintenance concept 02"],
        content_shortdescs=[
            "Conceptual guidance for cars, focusing on the structure and relationships.",
            "Conceptual guidance for cars, focusing on maintenance concepts.",
        ],
        content_body_snippets=[
            "This concept explains the structure, relationships, and internal organization for cars.",
            "This concept explains maintenance concepts and long-term upkeep patterns for cars.",
        ],
    )

    topic_xmls = [
        content.decode("utf-8", errors="ignore")
        for path, content in sorted(files.items())
        if str(path).endswith(".dita")
    ]

    assert "This concept explains the structure, relationships, and internal organization for cars." in topic_xmls[0]
    assert "This concept explains maintenance concepts and long-term upkeep patterns for cars." in topic_xmls[1]
    assert "This concept explains maintenance concepts and long-term upkeep patterns for cars." not in topic_xmls[0]


def test_reference_topics_dataset_keeps_all_topicrefs_when_only_subset_is_resource_only():
    files = generate_reference_topics_dataset(
        _config(),
        "/tmp",
        topic_count=10,
        include_map=True,
        rand=None,
        map_topicref_attribute_distributions=[
            {
                "attribute_name": "processing-role",
                "attribute_value": "resource-only",
                "count": 5,
            }
        ],
    )

    map_xml = next(
        content.decode("utf-8", errors="ignore")
        for path, content in files.items()
        if str(path).endswith(".ditamap")
    )

    assert map_xml.count("<topicref") == 10
    assert map_xml.count('processing-role="resource-only"') == 5


def test_keyscope_demo_full_shape_generates_three_maps_and_six_topics():
    files = generate_keyscope_demo_dataset(
        _config(),
        "/tmp",
        demo_shape="full_demo",
        include_qualified_keyrefs=True,
    )

    map_count = sum(1 for path in files if str(path).endswith(".ditamap"))
    topic_count = sum(1 for path in files if str(path).endswith(".dita"))
    readme = files["/tmp/aem_guides_keyscope_demo/README.txt"].decode("utf-8", errors="ignore")

    assert map_count == 3
    assert topic_count == 6
    assert "Submap S2" in readme


def test_keyscope_demo_minimal_shape_generates_two_maps_and_four_topics():
    files = generate_keyscope_demo_dataset(
        _config(),
        "/tmp",
        demo_shape="minimal_demo",
        include_qualified_keyrefs=False,
    )

    map_count = sum(1 for path in files if str(path).endswith(".ditamap"))
    topic_count = sum(1 for path in files if str(path).endswith(".dita"))
    readme = files["/tmp/aem_guides_keyscope_demo_minimal/README.txt"].decode("utf-8", errors="ignore")

    assert map_count == 2
    assert topic_count == 4
    assert "Submap S2" not in readme
