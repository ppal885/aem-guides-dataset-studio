from app.services.generate_dita_preview_service import (
    build_generate_dita_execution_contract,
    build_generate_dita_preview,
)


def test_generate_dita_preview_handles_single_topic_request():
    preview = build_generate_dita_preview(text="Create a task topic about installing AEM Guides.")

    assert preview["status"] == "preview_ready"
    assert preview["topic_family"] == "task"
    assert preview["counts"]["task"] == 1


def test_generate_dita_preview_requires_subject_for_glossaries():
    preview = build_generate_dita_preview(text="Create a map and 10 glossaries")

    assert preview["status"] == "clarification_required"
    assert preview["clarification_needed"] is True
    assert "subject" in str(preview["clarification_question"]).lower()


def test_generate_dita_preview_rejects_non_dita_outputs():
    preview = build_generate_dita_preview(
        text="Create a map, 10 glossaries, and matching step definitions for Playwright."
    )

    assert preview["status"] == "unsupported"
    assert "DITA" in preview["summary"]
    assert preview["warnings"]


def test_generate_dita_preview_requires_topic_family_for_generic_multi_topic_requests():
    preview = build_generate_dita_preview(text="Create 20 topics about cars.")

    assert preview["status"] == "clarification_required"
    assert preview["bundle_type"] == "topic_bundle"
    assert preview["artifacts"][0]["label"] == "20 topics"
    assert "concept" in str(preview["clarification_question"]).lower()


def test_generate_dita_preview_keeps_subject_separate_from_attribute_instructions():
    preview = build_generate_dita_preview(
        text="Generate 20 topics about cars.",
        instructions="add external links with scope attribute as external",
    )

    assert preview["status"] == "clarification_required"
    assert preview["subject"] == "cars"
    required_attributes = preview["required_attributes"]
    scope_constraint = next(item for item in required_attributes if item["attribute_name"] == "scope")
    assert scope_constraint["required_values"] == ["external"]
    assert "concept" in str(preview["clarification_question"]).lower()


def test_generate_dita_execution_contract_preserves_preview_shape():
    preview = build_generate_dita_preview(text="Create a concept topic about content reuse.")

    contract = build_generate_dita_execution_contract(preview=preview)

    assert contract is not None
    assert contract["topic_family"] == "concept"
    assert contract["include_map"] is False


def test_generate_dita_preview_infers_family_from_tags_without_clarifying():
    preview = build_generate_dita_preview(text="Create 5 topics using choicetable and stepxmp for output presets.")

    assert preview["status"] == "preview_ready"
    assert preview["topic_family"] == "task"
    assert any(item["name"] == "choicetable" for item in preview["required_elements"])


def test_generate_dita_preview_surfaces_constraint_conflicts():
    preview = build_generate_dita_preview(text="Create a concept topic with taskbody.")

    assert preview["status"] == "clarification_required"
    assert preview["conflicts"]
