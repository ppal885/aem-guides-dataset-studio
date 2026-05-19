import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.ai_executor_service import execute_plan
from app.services import ai_executor_service, generate_from_text_service
from app.services.dita_generation_contract_service import validate_generated_bundle_against_contract
from app.services.generate_from_text_service import (
    _build_generator_plan_from_bundle_contract,
    _maybe_apply_llm_deterministic_drafts,
)


def test_bundle_contract_maps_concept_bundle_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "concept",
            "subject": "cars",
            "include_map": False,
            "counts": {"concept": 20},
            "artifacts": [{"kind": "concept", "count": 20, "label": "20 concept topics"}],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "concept_topics"
    assert selected.params["topic_count"] == 20
    assert selected.params["include_map"] is False
    assert len(selected.params["content_titles"]) == 20
    assert len(selected.params["content_body_snippets"]) == 20
    assert len(set(selected.params["content_shortdescs"])) > 1
    assert len(set(selected.params["content_body_snippets"])) > 1


def test_bundle_contract_maps_glossary_bundle_to_glossary_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "mixed_bundle",
            "topic_family": "glossentry",
            "subject": "AEM Guides terminology",
            "include_map": True,
            "counts": {"ditamap": 1, "glossentry": 10},
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "glossentry", "count": 10, "label": "10 glossary entries"},
            ],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "glossary"
    assert selected.params["entry_count"] == 10
    assert len(selected.params["content_terms"]) == 10
    assert "AEM Guides terminology" in selected.params["content_definitions"][0]


def test_bundle_contract_maps_reference_bundle_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "reference",
            "subject": "cars",
            "include_map": True,
            "counts": {"reference": 5, "ditamap": 1},
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "reference", "count": 5, "label": "5 reference topics"},
            ],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "reference_topics"
    assert selected.params["topic_count"] == 5
    assert selected.params["include_map"] is True
    assert len(selected.params["content_titles"]) == 5
    assert len(selected.params["content_property_seeds"]) == 5
    assert len(set(selected.params["content_shortdescs"])) == 5
    assert len(set(selected.params["content_detail_snippets"])) == 5
    assert all("cars-" in seed for seed in selected.params["content_property_seeds"])


def test_execute_plan_uses_builtin_fallback_when_manifest_misses_reference_recipe(monkeypatch):
    monkeypatch.setattr(ai_executor_service, "discover_recipe_specs", lambda: [])
    output_dir = Path("tests") / "_tmp" / f"fallback_reference_{uuid4().hex}"
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "reference",
            "subject": "insurance",
            "include_map": False,
            "counts": {"reference": 2},
            "artifacts": [{"kind": "reference", "count": 2, "label": "2 reference topics"}],
        }
    )

    assert plan is not None
    try:
        result = execute_plan(
            plan,
            str(output_dir),
            seed="fallback-reference",
            skip_experience_league_companion=True,
        )
        generated = sorted(path.name for path in output_dir.rglob("*.dita"))
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir)

    assert "reference_topics" in result["recipes_executed"]
    assert any("built-in fallback spec" in warning for warning in result["warnings"])
    assert len(generated) == 2


def test_bundle_contract_keeps_reference_family_root_on_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "reference",
            "subject": "insurance reference",
            "include_map": False,
            "counts": {"reference": 20},
            "required_elements": [
                {"name": "reference", "scope": "artifact"},
            ],
            "artifacts": [{"kind": "reference", "count": 20, "label": "20 reference topics"}],
        },
        evidence_pack={"primary": {"summary": "Create 20 reference topics about insurance reference"}},
        trace_id="trace-reference",
        jira_id="TEXT-reference",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "reference_topics"
    assert selected.params["topic_count"] == 20
    assert selected.params["include_map"] is False
    assert len(selected.params["content_titles"]) == 20


def test_bundle_contract_keeps_processing_role_distribution_on_deterministic_reference_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "reference",
            "subject": "insurance",
            "include_map": True,
            "counts": {"reference": 10, "ditamap": 1},
            "required_attributes": [
                {
                    "attribute_name": "processing-role",
                    "scope": "bundle",
                    "required_values": ["resource-only"],
                }
            ],
            "topicref_attribute_distributions": [
                {
                    "attribute_name": "processing-role",
                    "attribute_value": "resource-only",
                    "count": 5,
                }
            ],
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "reference", "count": 10, "label": "10 reference topics"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate 10 reference topics about insurance and keep 5 as resource-only in the map"}},
        trace_id="trace-processing-role",
        jira_id="TEXT-processing-role",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "reference_topics"
    assert selected.params["topic_count"] == 10
    assert selected.params["include_map"] is True
    assert selected.params["map_topicref_attribute_distributions"][0]["attribute_name"] == "processing-role"
    assert selected.params["map_topicref_attribute_distributions"][0]["count"] == 5


def test_bundle_contract_maps_generic_topic_bundle_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "topic",
            "subject": "cars",
            "include_map": False,
            "counts": {"topic": 20},
            "artifacts": [{"kind": "topic", "count": 20, "label": "20 topics"}],
        },
        evidence_pack={"primary": {"summary": "Create 20 topics on cars", "description": "Need a generic topic bundle."}},
        trace_id="trace-topic",
        jira_id="TEXT-topic",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "topic_topics"
    assert selected.params["topic_count"] == 20
    assert selected.params["include_map"] is False
    assert len(selected.params["content_titles"]) == 20
    assert "Cars" in selected.params["content_titles"][0]
    assert "cars" in selected.params["content_body_snippets"][0].lower()
    assert len(set(selected.params["content_shortdescs"])) > 1
    assert len(set(selected.params["content_body_snippets"])) > 1


def test_bundle_contract_maps_task_bundle_to_distinct_deterministic_steps():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "task",
            "subject": "kubernetes",
            "include_map": False,
            "counts": {"task": 3},
            "artifacts": [{"kind": "task", "count": 3, "label": "3 task topics"}],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "task_topics"
    assert len(selected.params["content_shortdescs"]) == 3
    assert len(selected.params["content_steps_by_topic"]) == 3
    assert all(len(steps) == 4 for steps in selected.params["content_steps_by_topic"])
    assert selected.params["content_steps_by_topic"][0][0] != selected.params["content_steps_by_topic"][1][0]


def test_bundle_contract_with_explicit_structure_constraints_uses_llm_contract_path():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "task",
            "subject": "cars",
            "include_map": False,
            "counts": {"task": 5},
            "required_elements": [
                {"name": "choicetable", "scope": "artifact"},
                {"name": "stepxmp", "scope": "artifact"},
            ],
            "required_attributes": [
                {"attribute_name": "conref", "scope": "bundle", "required_values": []},
            ],
            "artifacts": [{"kind": "task", "count": 5, "label": "5 task topics"}],
        },
        evidence_pack={"primary": {"summary": "Create task topics about cars", "description": "Need reusable task topics."}},
        clean_instructions=None,
        trace_id="trace-1",
        jira_id="TEXT-12345678",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "llm_generated_dita"
    recipe_contract = selected.params["recipe_execution_contract"]
    assert any(item["name"] == "choicetable" for item in recipe_contract["required_constructs"])
    assert recipe_contract["required_attributes"][0]["attribute_name"] == "conref"


def test_bundle_contract_routes_external_keydef_xref_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "topic",
            "include_map": True,
            "counts": {"ditamap": 1, "topic": 1},
            "keyed_link_requirements": [
                {
                    "key_name": "external-docs",
                    "href": "https://example.com/docs",
                    "format": "html",
                    "scope": "external",
                    "definition_element": "keydef",
                    "consumer_element": "xref",
                    "link_text": "External documentation",
                }
            ],
            "required_elements": [
                {"name": "keydef", "scope": "bundle"},
                {"name": "xref", "scope": "artifact"},
            ],
            "required_attributes": [
                {"attribute_name": "keys", "scope": "bundle", "required_values": []},
                {"attribute_name": "href", "scope": "bundle", "required_values": []},
                {"attribute_name": "scope", "scope": "bundle", "required_values": ["external"]},
                {"attribute_name": "format", "scope": "bundle", "required_values": ["html"]},
                {"attribute_name": "keyref", "scope": "artifact", "required_values": []},
            ],
        },
        evidence_pack={"primary": {"summary": "Use external links as keydefs and xrefs"}},
        trace_id="trace-external-keydef",
        jira_id="TEXT-external-keydef",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "external_keydef_xref_bundle"
    assert selected.params["key_name"] == "external-docs"
    assert selected.params["href"] == "https://example.com/docs"
    assert selected.params["scope"] == "external"
    assert selected.params["format"] == "html"


def test_bundle_contract_routes_all_xref_types_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "topic",
            "include_map": True,
            "counts": {"ditamap": 1, "topic": 2},
            "execution_text": "Generate a topic with all type of cross references.",
            "construct_semantics": [
                {
                    "name": "xref",
                    "requires_contract_path": True,
                    "bundle_strategy": "topic_bundle",
                }
            ],
            "required_elements": [
                {"name": "topicref", "scope": "bundle"},
                {"name": "keydef", "scope": "bundle"},
                {"name": "xref", "scope": "artifact"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate all cross-reference types"}},
        trace_id="trace-xref-variety",
        jira_id="TEXT-xref-variety",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "xref_variety_bundle"
    assert selected.params["subject"] == "DITA cross references"


def test_bundle_contract_passes_safe_filename_to_topic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "single_topic",
            "topic_family": "topic",
            "subject": "insurance",
            "include_map": True,
            "counts": {"topic": 1, "ditamap": 1},
            "filename_requirements": [
                {
                    "requested_name": "Policy: A&B <draft>?.dita",
                    "safe_name": "Policy_ A&B _draft__.dita",
                    "strategy": "sanitize",
                }
            ],
        },
        evidence_pack={"primary": {"summary": "Generate topic with special filename"}},
        trace_id="trace-filename",
        jira_id="TEXT-filename",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "topic_topics"
    assert selected.params["content_filenames"] == ["Policy_ A&B _draft__.dita"]


def test_bundle_contract_keeps_reference_structure_requirements_on_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "reference",
            "subject": "Kubernetes operations",
            "include_map": True,
            "counts": {"reference": 5, "ditamap": 1},
            "preferred_structures": ["codeblock", "yaml", "table"],
            "structure_requirements": [
                {"structure_name": "codeblock", "language": "yaml"},
                {"structure_name": "table", "columns": 5, "rows": 6},
            ],
            "construct_semantics": [
                {
                    "name": "codeblock",
                    "requires_contract_path": True,
                    "bundle_strategy": "single_topic",
                }
            ],
            "required_attributes": [
                {
                    "attribute_name": "outputclass",
                    "scope": "artifact",
                    "required_values": ["language-yaml"],
                    "supported_elements": ["codeblock"],
                }
            ],
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "reference", "count": 5, "label": "5 reference topics"},
            ],
        },
        evidence_pack={"primary": {"summary": "Create Kubernetes reference topics with YAML and tables"}},
        trace_id="trace-structure",
        jira_id="TEXT-structure",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "reference_topics"
    assert selected.params["topic_count"] == 5
    assert selected.params["structure_requirements"][0]["structure_name"] == "codeblock"
    assert selected.params["structure_requirements"][1]["columns"] == 5


def test_bundle_contract_keeps_metadata_only_concept_bundle_on_deterministic_path():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "concept",
            "subject": "insurance",
            "include_map": False,
            "counts": {"concept": 20},
            "required_metadata": [
                {"field_name": "author", "value": "John Smith"},
                {"field_name": "audience", "value": "beginners"},
            ],
            "artifacts": [{"kind": "concept", "count": 20, "label": "20 concept topics"}],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "concept_topics"
    assert selected.params["content_prolog_metadata"]["author"] == "John Smith"
    assert selected.params["content_prolog_metadata"]["audience"] == "beginners"


def test_bundle_contract_routes_glossary_with_consuming_topics_through_contract_path():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "mixed_bundle",
            "topic_family": "concept",
            "subject": "car insurance terms",
            "include_map": True,
            "counts": {"ditamap": 1, "glossentry": 20, "concept": 5},
            "glossary_usage_mode": "with_map_and_topics",
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "glossentry", "count": 20, "label": "20 glossary entries"},
                {"kind": "concept", "count": 5, "label": "5 concept topics"},
            ],
        },
        evidence_pack={"primary": {"summary": "Create glossary entries and concept topics", "description": "Need a linked mixed bundle."}},
        trace_id="trace-glossary-mixed",
        jira_id="TEXT-glossary-mixed",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "llm_generated_dita"
    assert selected.params["recipe_execution_contract"]["glossary_usage_mode"] == "with_map_and_topics"


def test_bundle_contract_routes_full_keyscope_demo_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "map",
            "include_map": True,
            "example_request": True,
            "example_construct": "keyscope",
            "construct_scope": "bundle",
            "example_shape": "full_demo",
            "counts": {"ditamap": 3, "topic": 6},
            "artifacts": [
                {"kind": "ditamap", "count": 3, "label": "3 DITA maps"},
                {"kind": "topic", "count": 6, "label": "6 topic files"},
            ],
            "required_attributes": [
                {"attribute_name": "keyscope", "scope": "bundle", "required_values": []},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate a full keyscope demo"}},
        trace_id="trace-keyscope-demo",
        jira_id="TEXT-keyscope-demo",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "keyscope_demo"
    assert selected.params["demo_shape"] == "full_demo"
    assert selected.params["include_qualified_keyrefs"] is True


@pytest.mark.anyio
async def test_deterministic_recipe_can_apply_llm_draft_fields(monkeypatch):
    monkeypatch.setattr(generate_from_text_service, "is_llm_available", lambda: True)

    async def fake_generate_json(*_args, **_kwargs):
        return {
            "titles": ["Electric cars overview", "Battery systems in electric cars"],
            "shortdescs": [
                "Overview of electric cars and their main subsystems.",
                "Reference details for the major battery system components.",
            ],
            "body_snippets": [
                "Electric cars combine batteries, motors, charging systems, and control software.",
                "Battery systems determine range, charging behavior, and long-term performance.",
            ],
        }

    monkeypatch.setattr(generate_from_text_service, "generate_json", fake_generate_json)

    updated, meta = await _maybe_apply_llm_deterministic_drafts(
        selected=generate_from_text_service.SelectedRecipe(
            recipe_id="topic_topics",
            params={"topic_count": 2, "include_map": False},
            evidence_used=[],
        ),
        contract={"topic_family": "topic", "subject": "electric cars"},
        trace_id="trace-llm-draft",
        jira_id="TEXT-llm-draft",
    )

    assert meta["llm_draft_used"] is True
    assert meta["path"] == "deterministic_plus_llm_draft"
    assert "titles" in meta["fields"]
    assert updated.params["content_titles"][0] == "Electric cars overview"
    assert "Electric cars combine batteries" in updated.params["content_body_snippets"][0]


@pytest.mark.anyio
async def test_task_recipe_llm_draft_can_apply_steps_by_topic(monkeypatch):
    monkeypatch.setattr(generate_from_text_service, "is_llm_available", lambda: True)

    async def fake_generate_json(*_args, **_kwargs):
        return {
            "titles": ["Kubernetes operations: deployment rollouts", "Kubernetes operations: pod logs"],
            "shortdescs": [
                "Procedure guidance for deployment rollouts.",
                "Procedure guidance for pod logs.",
            ],
            "steps_by_topic": [
                [
                    "Review the current Kubernetes rollout state.",
                    "Run kubectl rollout status for the deployment.",
                    "Apply the rollout change and capture the result.",
                    "Verify the updated workload health.",
                ],
                [
                    "Review the current pod state.",
                    "Run kubectl logs for the target pod.",
                    "Capture the relevant diagnostics output.",
                    "Verify that the log findings match the expected state.",
                ],
            ],
        }

    monkeypatch.setattr(generate_from_text_service, "generate_json", fake_generate_json)

    updated, meta = await _maybe_apply_llm_deterministic_drafts(
        selected=generate_from_text_service.SelectedRecipe(
            recipe_id="task_topics",
            params={"topic_count": 2, "include_map": False},
            evidence_used=[],
        ),
        contract={
            "topic_family": "task",
            "subject": "Kubernetes operations",
            "domain_decomposition": {
                "subtopics": ["deployment rollouts", "pod logs"],
            },
        },
        trace_id="trace-task-llm-draft",
        jira_id="TEXT-task-llm-draft",
    )

    assert meta["llm_draft_used"] is True
    assert "steps_by_topic" in meta["fields"]
    assert "kubectl rollout status" in updated.params["content_steps_by_topic"][0][1]


def test_bundle_contract_routes_minimal_keyscope_demo_to_deterministic_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "map",
            "include_map": True,
            "example_request": True,
            "example_construct": "keyscope",
            "construct_scope": "bundle",
            "example_shape": "minimal_demo",
            "counts": {"ditamap": 2, "topic": 4},
            "artifacts": [
                {"kind": "ditamap", "count": 2, "label": "2 DITA maps"},
                {"kind": "topic", "count": 4, "label": "4 topic files"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate a minimal keyscope demo"}},
        trace_id="trace-keyscope-demo-min",
        jira_id="TEXT-keyscope-demo-min",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "keyscope_demo"
    assert selected.params["demo_shape"] == "minimal_demo"
    assert selected.params["include_qualified_keyrefs"] is False


def test_bundle_contract_routes_topichead_example_to_deterministic_map_recipe():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "map",
            "include_map": True,
            "example_request": True,
            "example_construct": "topichead",
            "counts": {"ditamap": 1, "topic": 2},
            "construct_semantics": [
                {
                    "name": "topichead",
                    "requires_contract_path": True,
                    "bundle_strategy": "map_bundle",
                    "validation_rules": ["topichead_contains_navigation_branch"],
                }
            ],
            "required_elements": [
                {"name": "topichead", "scope": "bundle"},
                {"name": "topicref", "scope": "bundle"},
            ],
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "topic", "count": 2, "label": "2 topics"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate a topichead example"}},
        trace_id="trace-topichead-example",
        jira_id="TEXT-topichead-example",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "maps.topichead_basic"
    assert selected.params["topic_count"] == 2


def test_bundle_contract_routes_topicgroup_example_to_deterministic_map_recipe():
    contract = {
        "status": "preview_ready",
        "bundle_type": "map_bundle",
        "topic_family": "map",
        "include_map": True,
        "counts": {"ditamap": 1, "topic": 2},
        "example_request": True,
        "example_construct": "topicgroup",
        "construct_semantics": [
            {
                "name": "topicgroup",
                "bundle_strategy": "map_bundle",
                "family_hint": "map",
                "include_map": True,
                "requires_contract_path": True,
                "required_elements": ["topicgroup", "topicref"],
                "validation_rules": ["topicgroup_contains_topicrefs"],
                "deterministic_recipe_id": "maps.topicgroup_basic",
            }
        ],
        "required_elements": [
            {"name": "topicgroup", "scope": "bundle"},
            {"name": "topicref", "scope": "bundle"},
        ],
        "artifacts": [
            {"kind": "ditamap", "count": 1},
            {"kind": "topic", "count": 2},
        ],
    }

    plan = _build_generator_plan_from_bundle_contract(
        contract,
        evidence_pack={"primary": {"summary": "Generate a topicgroup example"}},
        trace_id="trace-topicgroup-example",
        jira_id="TEXT-topicgroup-example",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "maps.topicgroup_basic"
    assert selected.params["topic_count"] == 2


def test_topichead_example_execution_matches_reviewed_contract():
    contract = {
        "bundle_type": "map_bundle",
        "topic_family": "map",
        "include_map": True,
        "example_request": True,
        "example_construct": "topichead",
        "counts": {"ditamap": 1, "topic": 2},
        "construct_semantics": [
            {
                "name": "topichead",
                "requires_contract_path": True,
                "bundle_strategy": "map_bundle",
                "validation_rules": ["topichead_contains_navigation_branch"],
            }
        ],
        "required_elements": [
            {"name": "topichead", "scope": "bundle"},
            {"name": "topicref", "scope": "bundle"},
        ],
        "artifacts": [
            {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
            {"kind": "topic", "count": 2, "label": "2 topics"},
        ],
    }
    plan = _build_generator_plan_from_bundle_contract(contract)
    assert plan is not None

    output_dir = Path("tests") / "_tmp" / f"topichead_execution_{uuid4().hex}"
    try:
        result = execute_plan(plan, str(output_dir), seed="topichead-test", skip_experience_league_companion=True)
        assert result["warnings"] == []

        generated_files = {
            path.name: path.read_text(encoding="utf-8", errors="ignore")
            for path in output_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".dita", ".ditamap", ".xml"}
        }
    finally:
        if output_dir.exists():
            shutil.rmtree(output_dir)

    assert sum(1 for text in generated_files.values() if "<map" in text.lower()) == 1
    assert sum(1 for text in generated_files.values() if "<topic " in text.lower()) == 2
    assert any("<topichead" in text.lower() for text in generated_files.values())
    assert validate_generated_bundle_against_contract(contract=contract, generated_files=generated_files) == []


def test_bundle_contract_uses_domain_decomposition_for_kubernetes_tasks():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "topic_bundle",
            "topic_family": "task",
            "subject": "Kubernetes operations",
            "include_map": False,
            "counts": {"task": 5},
            "domain_decomposition": {
                "focus": "operations",
                "subtopics": [
                    "deployment rollouts and rollout status",
                    "pod logs and live diagnostics",
                    "scaling workloads and replica management",
                    "service exposure and ingress updates",
                    "rollback and revision history",
                ],
            },
            "artifacts": [{"kind": "task", "count": 5, "label": "5 task topics"}],
        }
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "task_topics"
    assert selected.params["content_titles"][0].lower().startswith("kubernetes operations:")
    assert "rollouts" in selected.params["content_titles"][0].lower()
    assert "kubectl" in selected.params["content_steps_by_topic"][0][1].lower()


def test_bundle_contract_routes_construct_aware_examples_through_llm_contract_path():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "map",
            "subject": "audience filtering",
            "include_map": True,
            "example_request": True,
            "example_construct": "ditaval",
            "counts": {"ditamap": 1, "topic": 1, "ditaval": 1},
            "construct_semantics": [
                {
                    "name": "ditaval",
                    "requires_contract_path": True,
                    "bundle_strategy": "map_bundle",
                }
            ],
            "required_elements": [{"name": "ditavalref", "scope": "bundle"}],
            "required_attributes": [{"attribute_name": "audience", "scope": "artifact", "required_values": []}],
            "domain_decomposition": {"subtopics": ["audience filtering"]},
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "topic", "count": 1, "label": "1 topic"},
                {"kind": "ditaval", "count": 1, "label": "1 DITAVAL profile"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate a ditaval example for audience filtering"}},
        trace_id="trace-ditaval-example",
        jira_id="TEXT-ditaval-example",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "llm_generated_dita"
    recipe_contract = selected.params["recipe_execution_contract"]
    assert any(item["name"] == "ditaval" for item in recipe_contract["required_constructs"])
    assert recipe_contract["domain_decomposition"]["subtopics"] == ["audience filtering"]


def test_bundle_contract_passes_construct_validation_rules_and_companions_to_llm_path():
    plan = _build_generator_plan_from_bundle_contract(
        {
            "bundle_type": "map_bundle",
            "topic_family": "map",
            "subject": "Kubernetes operations",
            "include_map": True,
            "counts": {"ditamap": 1, "topic": 3},
            "construct_semantics": [
                {
                    "name": "reltable",
                    "requires_contract_path": True,
                    "bundle_strategy": "map_bundle",
                    "validation_rules": ["reltable_has_relrow_relcell_topicrefs"],
                    "required_companion_artifacts": ["relationship-map", "related-topics"],
                },
                {
                    "name": "mapref",
                    "requires_contract_path": True,
                    "bundle_strategy": "map_bundle",
                    "validation_rules": ["mapref_target_map_exists"],
                    "required_companion_artifacts": ["parent-map", "child-map"],
                },
            ],
            "required_elements": [
                {"name": "reltable", "scope": "bundle"},
                {"name": "mapref", "scope": "bundle"},
            ],
            "domain_decomposition": {"subtopics": ["deployment rollouts", "pod logs", "rollback"]},
            "artifacts": [
                {"kind": "ditamap", "count": 1, "label": "1 DITA map"},
                {"kind": "topic", "count": 3, "label": "3 topics"},
            ],
        },
        evidence_pack={"primary": {"summary": "Generate a reltable and mapref example"}},
        trace_id="trace-map-constructs",
        jira_id="TEXT-map-constructs",
    )

    assert plan is not None
    selected = plan.recipes[0]
    assert selected.recipe_id == "llm_generated_dita"
    recipe_contract = selected.params["recipe_execution_contract"]
    assert "reltable_has_relrow_relcell_topicrefs" in recipe_contract["construct_validation_rules"]
    assert "mapref_target_map_exists" in recipe_contract["construct_validation_rules"]
    assert "parent-map" in recipe_contract["required_companion_artifacts"]
    assert "relationship-map" in recipe_contract["required_companion_artifacts"]
    assert "Post-generation validation rules" in selected.params["additional_instructions"]


def test_build_evidence_pack_keeps_full_nl_request_in_description():
    from app.services.generate_from_text_service import build_evidence_pack_from_text

    text = "Generate a DITA task topic that explains how to publish a map to PDF in AEM Guides"
    pack = build_evidence_pack_from_text(text, "abc12345", forced_issue_key=None)
    primary = pack["primary"]
    assert primary["description"] == text
    assert primary["summary"] == text
    assert "AEM Guides" in (primary["description"] or "")


def test_build_evidence_pack_long_nl_includes_full_text_in_description():
    from app.services.generate_from_text_service import build_evidence_pack_from_text

    prefix = "Generate a DITA task topic for AEM Guides. " * 25
    text = prefix.strip() + " ENDMARKER"
    assert len(text) > 500
    pack = build_evidence_pack_from_text(text, "abc12345", forced_issue_key=None)
    assert pack["primary"]["description"] == text
    assert pack["primary"]["summary"] == text[:500].strip()
    assert "ENDMARKER" in pack["primary"]["description"]
