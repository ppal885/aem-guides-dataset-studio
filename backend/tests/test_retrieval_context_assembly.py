from app.core.schemas_dita_pipeline import AssembledRetrievalContext, RecipeSelectionResult, RecipeStoreCandidateSummary
from app.services.retrieval_context_assembly_service import (
    _xml_example_likeness,
    build_recipe_catalog_spec_examples_text,
    format_recipe_store_block,
)


def test_xml_likeness_prefers_markup():
    prose = "This guide explains tables in documentation."
    xmlish = '<task id="t"><title>X</title><taskbody><steps><step><cmd>Go</cmd></step></steps></taskbody></task>'
    assert _xml_example_likeness(xmlish) > _xml_example_likeness(prose)


def test_recipe_store_block_marks_selected():
    sel = RecipeSelectionResult(
        recipe_id="b",
        score=1.0,
        retrieval_candidates=[
            RecipeStoreCandidateSummary(recipe_id="a", title="A", retrieval_score=2.0, reasons=["x"]),
            RecipeStoreCandidateSummary(recipe_id="b", title="B", retrieval_score=1.5, reasons=["y"]),
        ],
    )
    text = format_recipe_store_block(sel)
    assert "SELECTED" in text
    assert "b:" in text


def test_catalog_spec_examples_from_spec():
    from app.generator.recipe_manifest import RecipeSpec

    s = RecipeSpec(
        id="t",
        title="t",
        description="d",
        example_input="in",
        example_output="<table/>",
    )
    t = build_recipe_catalog_spec_examples_text(s)
    assert "example_input" in t
    assert "table" in t.lower()


def test_assembled_to_prompt_includes_generation_contract():
    ctx = AssembledRetrievalContext(
        recipe_store_text="r",
        dita_spec_store_text="s",
    )
    p = ctx.to_prompt_sections()
    assert "GENERATION_CONTRACT" in p
    assert "RECIPE_STORE" in p
    assert "DITA_SPEC_STORE" in p
