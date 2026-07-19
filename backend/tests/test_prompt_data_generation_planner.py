from app.services.prompt_data_generation_planner import (
    build_prompt_generation_plan,
    render_prompt_generation_plan,
)


def test_prompt_generation_plan_preserves_constructs_outputs_and_oracles():
    plan = build_prompt_generation_plan(
        "Generate a QA dataset for copy-to, chunk, xref and xml:lang with PDF and HTML5 evidence"
    )

    assert plan["wants_dataset"] is True
    assert plan["wants_publishing"] is True
    assert plan["requested_output"] == "all"
    assert "copy-to" in plan["detected_constructs"]
    assert "chunk" in plan["detected_constructs"]
    assert "xref" in plan["detected_constructs"]
    assert any("root DITA map" in item for item in plan["artifact_expectations"])
    assert any("publishing checks" in item for item in plan["oracle_expectations"])
    assert plan["negative_or_risk_cases"]


def test_render_prompt_generation_plan_is_injectable_text():
    plan = build_prompt_generation_plan("Create conref and keyref test data with negative cases")
    rendered = render_prompt_generation_plan(plan)

    assert "Prompt-derived data generation plan" in rendered
    assert "Detected constructs" in rendered
    assert "Quality rules" in rendered
