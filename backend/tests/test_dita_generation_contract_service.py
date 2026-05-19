import xml.etree.ElementTree as ET

import pytest

from app.services.dita_generation_contract_service import (
    build_dita_generation_contract,
    validate_generated_bundle_against_contract,
)
from app.services.dita_xml_headers import build_dita_header, serialize_normalized_dita_tree


def test_contract_infers_task_family_from_required_elements():
    contract = build_dita_generation_contract(
        text="Create 5 topics using choicetable and stepxmp for output presets."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "task"
    assert {item.name for item in contract.required_elements} >= {"choicetable", "stepxmp"}
    assert contract.family_decision.inferred == "task"


def test_contract_extracts_required_attribute_values_for_map_request():
    contract = build_dita_generation_contract(
        text='Create a map using chunk="to-content" and collection-type="family" for car documentation.'
    )

    assert contract.status == "preview_ready"
    assert contract.include_map is True
    attrs = {item.attribute_name: item for item in contract.required_attributes}
    assert attrs["chunk"].required_values == ["to-content"]
    assert attrs["collection-type"].required_values == ["family"]


def test_contract_extracts_topicref_processing_role_distribution():
    contract = build_dita_generation_contract(
        text='Generate 10 reference topics about insurance and keep 5 topics with processing-role="resource-only" in the map.'
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "reference"
    assert contract.include_map is True
    assert contract.subject == "insurance"
    assert contract.required_attributes
    assert contract.topicref_attribute_distributions
    distribution = contract.topicref_attribute_distributions[0]
    assert distribution.attribute_name == "processing-role"
    assert distribution.attribute_value == "resource-only"
    assert distribution.count == 5


def test_contract_surfaces_family_conflict_for_invalid_structure():
    contract = build_dita_generation_contract(
        text="Create a concept topic with taskbody about authoring."
    )

    assert contract.status == "clarification_required"
    assert contract.conflicts
    assert "taskbody" in contract.conflicts[0].message.lower()


def test_contract_surfaces_map_attribute_conflict_for_non_map_family():
    contract = build_dita_generation_contract(
        text='Create a concept topic about authoring using chunk="to-content".'
    )

    assert contract.status == "clarification_required"
    assert contract.conflicts
    assert any("chunk" in item.message.lower() for item in contract.conflicts)


def test_contract_validation_requires_artifact_level_elements():
    contract = build_dita_generation_contract(
        text="Create 2 task topics using choicetable about AEM Guides."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "task_01.dita": "<task><title>Task 1</title><taskbody><steps><step><cmd>Do it</cmd></step></steps></taskbody></task>",
            "task_02.dita": "<task><title>Task 2</title><taskbody><steps><step><cmd>Do it again</cmd><choicetable><chrow><choption>One</choption><chdesc>Desc</chdesc></chrow></choicetable></step></steps></taskbody></task>",
        },
    )

    assert issues
    assert any("choicetable" in issue.lower() for issue in issues)


def test_contract_extracts_required_prolog_metadata_values():
    contract = build_dita_generation_contract(
        text="Generate 20 concept topics about insurance with prolog metadata: author=John Smith, audience=beginners"
    )

    assert contract.status == "preview_ready"
    metadata = {item.field_name: item for item in contract.required_metadata}
    assert metadata["author"].value == "John Smith"
    assert metadata["audience"].value == "beginners"
    assert contract.content_mode == "auto_hybrid"


def test_contract_requests_missing_prolog_metadata_values():
    contract = build_dita_generation_contract(
        text="Generate 20 topics about insurance with prolog metadata including author and keywords"
    )

    assert contract.status == "clarification_required"
    assert contract.clarification_request is not None
    assert contract.clarification_request.missing_field == "prolog_metadata_values"
    assert "author" in (contract.clarification_question or "").lower()
    assert "keywords" in (contract.clarification_question or "").lower()


def test_contract_supports_glossary_consuming_topics_mode():
    contract = build_dita_generation_contract(
        text="Create 20 glossary entries for car insurance terms and 5 concept topics that use them"
    )

    assert contract.status == "preview_ready"
    assert contract.bundle_type == "mixed_bundle"
    assert contract.glossary_usage_mode == "with_topics"
    assert contract.counts["glossentry"] == 20
    assert contract.counts["concept"] == 5


def test_contract_validation_requires_requested_metadata():
    contract = build_dita_generation_contract(
        text="Generate 2 concept topics about insurance with prolog metadata: author=John Smith"
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "concept_01.dita": '<concept><title>One</title><prolog><author>John Smith</author></prolog><conbody><p>Body</p></conbody></concept>',
            "concept_02.dita": "<concept><title>Two</title><conbody><p>Body</p></conbody></concept>",
        },
    )

    assert issues
    assert any("author" in issue.lower() for issue in issues)


def test_contract_validation_requires_total_topicrefs_and_resource_only_subset():
    contract = build_dita_generation_contract(
        text='Generate 10 reference topics about insurance and keep 5 topics with processing-role="resource-only" in the map.'
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "reference_topics.ditamap": (
                '<map>'
                '<topicref href="reference_01.dita" processing-role="resource-only"/>'
                '<topicref href="reference_02.dita" processing-role="resource-only"/>'
                '<topicref href="reference_03.dita" processing-role="resource-only"/>'
                '<topicref href="reference_04.dita" processing-role="resource-only"/>'
                '<topicref href="reference_05.dita" processing-role="resource-only"/>'
                '</map>'
            ),
            **{
                f"reference_{index:02d}.dita": f"<reference><title>Reference {index}</title><refbody><section><title>Details</title><p>Body</p></section></refbody></reference>"
                for index in range(1, 11)
            },
        },
    )

    assert issues
    assert any("expected 10 topicrefs" in issue.lower() for issue in issues)


def test_contract_keyscope_example_requires_shape_clarification():
    contract = build_dita_generation_contract(
        text="Generate a keyscope example"
    )

    assert contract.status == "clarification_required"
    assert contract.example_request is True
    assert contract.example_construct == "keyscope"
    assert contract.construct_scope == "bundle"
    assert contract.example_shape == "unspecified"
    assert contract.example_shape_clarification_required is True
    assert contract.include_map is True
    assert contract.clarification_request is not None
    assert contract.clarification_request.missing_field == "example_shape"
    assert "minimal demo" in (contract.clarification_question or "").lower()
    assert "full demo" in (contract.clarification_question or "").lower()


def test_contract_full_keyscope_demo_builds_map_bundle_counts():
    contract = build_dita_generation_contract(
        text="Generate a full keyscope demo"
    )

    assert contract.status == "preview_ready"
    assert contract.example_request is True
    assert contract.example_construct == "keyscope"
    assert contract.example_shape == "full_demo"
    assert contract.topic_family == "map"
    assert contract.counts["ditamap"] == 3
    assert contract.counts["topic"] == 6
    labels = [item.label for item in contract.artifacts]
    assert "3 DITA maps" in labels
    assert "6 topic files" in labels


def test_contract_rejects_single_topic_keyscope_example():
    contract = build_dita_generation_contract(
        text="Generate a single topic keyscope example"
    )

    assert contract.status == "clarification_required"
    assert contract.conflicts
    assert any("single topic" in item.message.lower() or "cannot be generated as a single topic" in item.message.lower() for item in contract.conflicts)


def test_contract_xml_for_keyscope_clarifies_bundle_shape():
    contract = build_dita_generation_contract(
        text="Give me XML for keyscope"
    )

    assert contract.status == "clarification_required"
    assert contract.example_request is True
    assert contract.example_construct == "keyscope"
    assert contract.clarification_request is not None
    assert contract.clarification_request.missing_field == "example_shape"


def test_contract_decomposes_kubernetes_operations_into_distinct_subtopics():
    contract = build_dita_generation_contract(
        text="Create 5 task topics about Kubernetes operations."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "task"
    assert contract.domain_decomposition is not None
    assert contract.domain_decomposition.focus == "operations"
    assert any("rollout" in item.lower() for item in contract.domain_decomposition.subtopics)
    assert any("logs" in item.lower() for item in contract.domain_decomposition.subtopics)


def test_contract_extracts_codeblock_language_and_table_dimensions():
    contract = build_dita_generation_contract(
        text="I need 5 reference topics about Kubernetes operations with YAML codeblocks and tables having 5 columns and 6 rows."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "reference"
    assert contract.subject == "Kubernetes operations"
    assert contract.domain_decomposition is not None
    requirements = {item.structure_name: item for item in contract.structure_requirements}
    assert requirements["codeblock"].language == "yaml"
    assert requirements["table"].columns == 5
    assert requirements["table"].rows == 6
    assert "codeblock" in contract.preferred_structures
    assert "table" in contract.preferred_structures
    assert not any(item.name == "i" for item in contract.required_elements)
    assert any(
        item.attribute_name == "outputclass" and item.required_values == ["language-yaml"]
        for item in contract.required_attributes
    )
    assert "Structure requirements from the prompt" in (contract.execution_instructions or "")
    assert "language=yaml" in (contract.execution_instructions or "")


def test_contract_uses_structure_requirements_to_resolve_generic_topics_to_reference():
    contract = build_dita_generation_contract(
        text="I need 5 topics about Kubernetes operations with YAML codeblocks and tables having 5 columns and 6 rows."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "reference"
    assert contract.counts["reference"] == 5
    assert contract.family_decision.reason == "structure-implied family"
    requirements = {item.structure_name: item for item in contract.structure_requirements}
    assert requirements["codeblock"].language == "yaml"
    assert requirements["table"].columns == 5
    assert requirements["table"].rows == 6


def test_contract_validation_checks_structure_requirements():
    contract = build_dita_generation_contract(
        text="Create a reference topic about Kubernetes operations with YAML codeblocks and tables having 5 columns and 6 rows."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "kubernetes_reference.dita": (
                "<reference><title>Kubernetes Operations</title><refbody>"
                "<section><title>Command</title><codeblock>kubectl get pods</codeblock></section>"
                "<table><tgroup cols=\"3\"><tbody><row><entry>A</entry><entry>B</entry><entry>C</entry></row></tbody></tgroup></table>"
                "</refbody></reference>"
            )
        },
    )

    assert any("language-yaml" in issue.lower() for issue in issues)
    assert any("5 table columns" in issue.lower() for issue in issues)
    assert any("6 table rows" in issue.lower() for issue in issues)


def test_contract_extracts_external_keydef_xref_requirement():
    contract = build_dita_generation_contract(
        text="I need to use external links as a keydef in a map and use them in a topic as crossreference."
    )

    assert contract.status == "preview_ready"
    assert contract.bundle_type == "map_bundle"
    assert contract.include_map is True
    assert contract.topic_family == "topic"
    assert contract.counts["ditamap"] == 1
    assert contract.counts["topic"] == 1
    assert contract.keyed_link_requirements
    requirement = contract.keyed_link_requirements[0]
    assert requirement.key_name == "external-docs"
    assert requirement.href == "https://example.com/docs"
    assert requirement.scope == "external"
    assert requirement.format == "html"
    assert {item.name for item in contract.required_elements} >= {"keydef", "topicref", "xref"}
    attrs = {item.attribute_name: item for item in contract.required_attributes}
    assert "keys" in attrs
    assert "href" in attrs
    assert attrs["scope"].required_values == ["external"]
    assert attrs["format"].required_values == ["html"]
    assert "keyref" in attrs


def test_contract_routes_all_cross_reference_types_to_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate a topic with all type of cross references."
    )

    assert contract.status == "preview_ready"
    assert contract.bundle_type == "map_bundle"
    assert contract.include_map is True
    assert contract.topic_family == "topic"
    assert contract.counts["ditamap"] == 1
    assert contract.counts["topic"] == 2
    assert {item.name for item in contract.required_elements} >= {"topicref", "keydef", "xref"}
    assert any("same-topic" in item for item in contract.assumptions)
    assert "Xref variety requirement" in (contract.execution_instructions or "")


def test_contract_extracts_and_sanitizes_requested_filename():
    contract = build_dita_generation_contract(
        text='Generate 1 topic about insurance with file name "Policy: A&B <draft>?.dita".'
    )

    assert contract.status == "preview_ready"
    assert contract.filename_requirements
    requirement = contract.filename_requirements[0]
    assert requirement.requested_name == "Policy: A&B <draft>?.dita"
    assert requirement.safe_name == "Policy_ A&B _draft__.dita"
    assert requirement.strategy == "sanitize"
    assert "Policy: A&B" in (contract.execution_instructions or "")
    assert "Policy_ A&B _draft__.dita" in (contract.execution_instructions or "")


def test_contract_clarifies_special_character_filename_without_exact_name():
    contract = build_dita_generation_contract(
        text="Generate a topic with special characters in file name."
    )

    assert contract.status == "clarification_required"
    assert contract.clarification_request is not None
    assert contract.clarification_request.missing_field == "file_name"


def test_contract_validation_enforces_external_keydef_xref_indirection():
    contract = build_dita_generation_contract(
        text="I need to use external links as a keydef in a map and use them in a topic as crossreference."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "external_links.ditamap": (
                '<map id="m1">'
                '<title>External links</title>'
                '<keydef keys="external-docs" href="https://example.com/docs" scope="external" format="html"/>'
                '<topicref href="external_reference.dita"/>'
                '</map>'
            ),
            "external_reference.dita": (
                '<topic id="t1"><title>External reference</title><body>'
                '<p>See <xref href="https://example.com/docs" scope="external" format="html">External documentation</xref>.</p>'
                '</body></topic>'
            ),
        },
    )

    assert any("keyref" in issue.lower() and "external-docs" in issue for issue in issues)
    assert any("direct external" in issue.lower() for issue in issues)


def test_contract_validation_rejects_missing_external_keydef_scope_or_format():
    contract = build_dita_generation_contract(
        text="I need to use external links as a keydef in a map and use them in a topic as crossreference."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "external_links.ditamap": (
                '<map id="m1">'
                '<title>External links</title>'
                '<keydef keys="external-docs" href="https://example.com/docs"/>'
                '<topicref href="external_reference.dita"/>'
                '</map>'
            ),
            "external_reference.dita": (
                '<topic id="t1"><title>External reference</title><body>'
                '<p>See <xref keyref="external-docs">External documentation</xref>.</p>'
                '</body></topic>'
            ),
        },
    )

    assert any('scope="external"' in issue for issue in issues)
    assert any('format="html"' in issue for issue in issues)


def test_contract_builds_conref_example_as_topic_bundle():
    contract = build_dita_generation_contract(
        text="Generate a conref example about product documentation."
    )

    assert contract.status == "preview_ready"
    assert contract.example_request is True
    assert contract.example_construct == "conref"
    assert contract.bundle_type == "topic_bundle"
    assert contract.counts["topic"] == 2
    assert any(item.attribute_name == "conref" for item in contract.required_attributes)
    assert any(item.name == "conref" for item in contract.construct_semantics)


def test_contract_builds_conkeyref_example_as_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate a conkeyref example about product documentation."
    )

    assert contract.status == "preview_ready"
    assert contract.example_request is True
    assert contract.example_construct == "conkeyref"
    assert contract.include_map is True
    assert contract.bundle_type == "map_bundle"
    assert contract.counts["ditamap"] == 1
    assert contract.counts["topic"] == 2
    assert any(item.attribute_name == "conkeyref" for item in contract.required_attributes)


def test_contract_routes_subject_scheme_example_to_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate a subject scheme example about audience values."
    )

    assert contract.status == "preview_ready"
    assert contract.example_request is True
    assert contract.example_construct == "subjectscheme"
    assert contract.topic_family == "map"
    assert contract.bundle_type == "map_bundle"
    assert contract.include_map is True
    assert contract.counts["subjectscheme"] == 1
    assert contract.counts["ditamap"] == 1
    assert any(item.name == "subjectScheme" for item in contract.required_elements)


def test_contract_routes_ditaval_example_to_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate a ditaval example for audience filtering."
    )

    assert contract.status == "preview_ready"
    assert contract.example_request is True
    assert contract.example_construct == "ditaval"
    assert contract.bundle_type == "map_bundle"
    assert contract.include_map is True
    assert contract.counts["ditaval"] == 1
    assert any(item.name == "ditavalref" for item in contract.required_elements)


def test_contract_refsyn_implies_reference_family():
    contract = build_dita_generation_contract(
        text="Create a topic using refbody and refsyn about API commands."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "reference"
    assert any(item.name == "refsyn" for item in contract.required_elements)


def test_contract_code_constructs_bias_toward_reference_family():
    contract = build_dita_generation_contract(
        text="Create topics about Kubernetes commands with codeblock and codeph."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "reference"
    assert any(item.name == "codeblock" for item in contract.construct_semantics)
    assert any(item.name == "codeph" for item in contract.construct_semantics)


def test_contract_attribute_only_keyref_routes_to_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate an example that uses @keyref for product names."
    )

    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.bundle_type == "map_bundle"
    assert contract.example_construct == "keyref"
    semantics = {item.name: item for item in contract.construct_semantics}
    assert "keyref" in semantics
    assert "keyref_keydef_exists" in semantics["keyref"].validation_rules
    assert any(item.name == "keydef" for item in contract.required_elements)


def test_contract_topichead_topicgroup_reltable_mapref_route_to_map_bundle():
    contract = build_dita_generation_contract(
        text="Generate a map with topichead, topicgroup, reltable, and mapref for Kubernetes operations."
    )

    assert contract.status == "preview_ready"
    assert contract.topic_family == "map"
    assert contract.include_map is True
    assert contract.bundle_type == "map_bundle"
    names = {item.name.lower() for item in contract.construct_semantics}
    assert {"topichead", "topicgroup", "reltable", "mapref"} <= names
    assert {item.name.lower() for item in contract.required_elements} >= {
        "topichead",
        "topicgroup",
        "reltable",
        "relrow",
        "relcell",
        "mapref",
    }


def test_contract_subject_scheme_single_topic_request_blocks():
    contract = build_dita_generation_contract(
        text="Generate a single topic subject scheme example for audience values."
    )

    assert contract.status == "clarification_required"
    assert any("subjectscheme" in item.requested.lower() for item in contract.conflicts if item.requested)
    assert any("single topic" in item.message.lower() for item in contract.conflicts)


def test_contract_detects_profiling_and_output_attributes_from_supplemental_catalog():
    contract = build_dita_generation_contract(
        text='Create 2 reference topics about Kubernetes with audience="admin", product="aks", outputclass="language-yaml", width="5in", and height="3in".'
    )

    assert contract.status == "preview_ready"
    attrs = {item.attribute_name: item for item in contract.required_attributes}
    assert attrs["audience"].required_values == ["admin"]
    assert attrs["product"].required_values == ["aks"]
    assert attrs["outputclass"].required_values == ["language-yaml"]
    assert attrs["width"].required_values == ["5in"]
    assert attrs["height"].required_values == ["3in"]


def test_contract_validation_enforces_conrefend_range_targets():
    contract = build_dita_generation_contract(
        text="Generate a conrefend example about product documentation."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "source.dita": '<topic id="source"><title>Source</title><body><p id="start">Start</p><p id="end">End</p></body></topic>',
            "consumer.dita": '<topic id="consumer"><title>Consumer</title><body><p conref="source.dita#source/start" conrefend="source.dita#source/missing"/></body></topic>',
        },
    )

    assert any("conref range target `missing`" in issue for issue in issues)


def test_contract_validation_enforces_keyref_keydef_resolution():
    contract = build_dita_generation_contract(
        text="Generate a keyref example about product names."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "root.ditamap": '<map id="root"><keydef keys="product-name"><topicmeta><keytext>Acme</keytext></topicmeta></keydef><topicref href="consumer.dita"/></map>',
            "consumer.dita": '<topic id="consumer"><title>Consumer</title><body><p><ph keyref="missing-key"/></p></body></topic>',
        },
    )

    assert any("does not match any generated `@keys` value" in issue for issue in issues)


def test_contract_validation_enforces_ditavalref_profile_artifact():
    contract = build_dita_generation_contract(
        text="Generate a DITAVAL and ditavalref filtering example."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "root.ditamap": '<map id="root"><topicref href="admin.dita"><ditavalref href="admin.xml" format="xml"/></topicref></map>',
            "admin.dita": '<topic id="admin"><title>Admin</title><body><p audience="admin">Admin only.</p></body></topic>',
        },
    )

    assert any("no `<val>` file" in issue.lower() for issue in issues)
    assert any("reference a `.ditaval` profile" in issue for issue in issues)
    assert any('format="ditaval"' in issue for issue in issues)


def test_contract_validation_can_enforce_expected_headers():
    contract = build_dita_generation_contract(
        text="Create 1 concept topic about cars."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "concept_01.dita": "<concept><title>Cars</title><conbody><p>Body</p></conbody></concept>",
        },
        enforce_headers=True,
    )

    assert any("expected XML declaration and DITA doctype header" in issue for issue in issues)


def test_serialize_normalized_dita_tree_preserves_expected_concept_header():
    root = ET.fromstring("<concept id=\"c1\"><title>Cars</title><conbody><p>About cars.</p></conbody></concept>")

    updated = serialize_normalized_dita_tree(root, "concept").decode("utf-8")

    assert updated.startswith(build_dita_header("concept"))
    assert '<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN"' in updated


def test_serialize_normalized_dita_tree_preserves_expected_task_header_after_id_updates():
    root = ET.fromstring(
        "<task id=\"task-1\"><title>Set up cars</title><taskbody><steps>"
        "<step id=\"dup\"><cmd>Do one thing.</cmd></step>"
        "<step id=\"dup\"><cmd>Do another thing.</cmd></step>"
        "</steps></taskbody></task>"
    )
    steps = list(root.iter("step"))
    steps[1].set("id", "dup_2")

    updated = serialize_normalized_dita_tree(root, "task").decode("utf-8")

    assert updated.startswith(build_dita_header("task"))
    assert updated.count('id="dup"') == 1
    assert 'id="dup_2"' in updated
    assert '<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN"' in updated


def test_contract_validation_counts_subject_scheme_and_ditaval_artifacts():
    contract = build_dita_generation_contract(
        text="Generate a subject scheme example about audience values."
    )

    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "subject-scheme.ditamap": '<?xml version="1.0" encoding="UTF-8"?><subjectScheme id="scheme"/>',
            "root-map.ditamap": '<?xml version="1.0" encoding="UTF-8"?><map id="root"><topicref href="topic.dita"/></map>',
            "topic.dita": '<?xml version="1.0" encoding="UTF-8"?><topic id="t1"><title>Audience values</title><body><p>Body</p></body></topic>',
        },
    )

    assert issues
    assert any("expected 2 `topic` files" in issue.lower() for issue in issues)


def test_validation_task_root_satisfies_artifact_level_topic_element_requirement():
    """Regression: contracts may list <topic> next to <task>; specialized roots must satisfy that check."""
    from app.core.schemas_dita_generation_contract import ArtifactContract, DitaGenerationContract, ElementConstraint

    contract = DitaGenerationContract(
        status="preview_ready",
        topic_family="task",
        bundle_type="map_bundle",
        counts={"task": 1},
        include_map=True,
        artifacts=[
            ArtifactContract(kind="ditamap", count=1, label="1 DITA map"),
            ArtifactContract(kind="task", count=1, label="1 task topic"),
        ],
        required_elements=[
            ElementConstraint(name="topic", scope="artifact"),
            ElementConstraint(name="map", scope="bundle"),
        ],
    )
    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "root.ditamap": '<map id="m1"><title>Root</title><topicref href="publish_task.dita"/></map>',
            "publish_task.dita": "<task id=\"t1\"><title>Publish</title><taskbody><steps><step><cmd>Go</cmd></step></steps></taskbody></task>",
        },
    )
    assert not any("required element `<topic>`" in issue.lower() for issue in issues)


def test_validation_dedupes_topicrefs_that_point_to_same_topic_file():
    """Regression: naive <topicref substring counts double-count duplicate hrefs or nesting."""
    from app.core.schemas_dita_generation_contract import DitaGenerationContract

    contract = DitaGenerationContract(
        status="preview_ready",
        topic_family="task",
        counts={"task": 1},
        include_map=True,
        artifacts=[],
    )
    issues = validate_generated_bundle_against_contract(
        contract=contract,
        generated_files={
            "root.ditamap": (
                '<map id="m1"><topicref href="publish_task.dita"/>'
                '<topicref href="publish_task.dita"/></map>'
            ),
            "publish_task.dita": "<task id=\"t1\"><title>Publish</title><taskbody><steps><step><cmd>Go</cmd></step></steps></taskbody></task>",
        },
    )
    assert not any("expected 1 topicref" in issue.lower() and "found 2" in issue.lower() for issue in issues)


def test_strip_removes_redundant_topic_element_when_topic_family_is_task():
    contract = build_dita_generation_contract(
        text="Create 1 DITA map and 1 task topic about publishing a map to PDF."
    )
    assert contract.status == "preview_ready"
    assert contract.topic_family == "task"
    assert not any(
        str(item.name or "").strip().lower() == "topic" and str(getattr(item, "scope", None) or "artifact").lower() == "artifact"
        for item in contract.required_elements
    )


def test_contract_nl_follow_up_more_topics_and_hierarchy_typos():
    text = (
        "Give me more data on the jira with different hierarcy or more topics\n\n"
        "---\nJira / ticket context:\nSummary: Broken publish\nDescription: stack trace..."
    )
    contract = build_dita_generation_contract(text=text)
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.bundle_type == "map_bundle"
    topic_like = sum(
        int((contract.counts or {}).get(k) or 0)
        for k in ("topic", "task", "concept", "reference")
    )
    assert topic_like >= 4
    assert "data" not in {str(e.name).lower() for e in contract.required_elements}
    assert contract.subject == "Broken publish"


def test_contract_nl_deeper_hierarchy_and_more_concepts():
    contract = build_dita_generation_contract(
        text="Use a deeper hierarchy and add several more concept topics about release notes."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    cts = contract.counts or {}
    assert (cts.get("concept") or 0) + (cts.get("topic") or 0) >= 4


def test_contract_nl_subtopics_implies_scale():
    contract = build_dita_generation_contract(
        text="Include child topics and a ditamap for the installation flow."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.topic_family == "task"
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like >= 4


def test_contract_more_data_in_section_does_not_require_data_element():
    contract = build_dita_generation_contract(text="Please add more data to the troubleshooting section.")
    assert contract.status in {"preview_ready", "clarification_required"}
    assert "data" not in {str(e.name).lower() for e in contract.required_elements}


def test_contract_nl_child_topics_map_introduction_infers_concept():
    contract = build_dita_generation_contract(
        text="Add child topics under a ditamap with an introduction to zero trust networking."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.topic_family == "concept"


def test_contract_nl_child_topics_map_defaults_task_without_domain_hint():
    contract = build_dita_generation_contract(
        text="Include child topics and a ditamap about widgets."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.topic_family == "task"
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like >= 4


@pytest.mark.parametrize(
    "typo",
    ("hyerarchy", "hirarchy", "heirarchy", "hierachy"),
)
def test_contract_nl_hierarchy_spelling_typos_set_map_and_scale(typo: str):
    contract = build_dita_generation_contract(
        text=f"Use different {typo} with a bookmap for backups."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like >= 4


def test_contract_nl_topic_pack_openapi_infers_reference():
    contract = build_dita_generation_contract(
        text="A topic pack and ditamap for OpenAPI endpoints."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert contract.topic_family == "reference"
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like >= 4


def test_contract_nl_three_separate_topics_word_floor():
    contract = build_dita_generation_contract(
        text="Three separate topics under a root map about caching."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like >= 3


def test_contract_nl_table_of_contents_with_topics_no_spurious_table_element():
    contract = build_dita_generation_contract(
        text="Table of contents with topics and a ditamap about onboarding."
    )
    assert contract.status == "preview_ready"
    assert contract.include_map is True
    assert "table" not in {str(e.name).lower() for e in contract.required_elements}


def test_contract_nl_single_topic_with_map_does_not_inflate_topic_count():
    contract = build_dita_generation_contract(text="Create only one topic and a ditamap about fish.")
    assert contract.status == "preview_ready"
    topic_like = sum(int((contract.counts or {}).get(k) or 0) for k in ("topic", "task", "concept", "reference"))
    assert topic_like < 4
