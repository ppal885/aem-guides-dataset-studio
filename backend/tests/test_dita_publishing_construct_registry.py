import json

from app.services.dita_publishing_construct_registry import (
    SUMMARY_FILENAME,
    build_publishing_corpus,
    detect_publishing_constructs,
)
from app.services.publishing_dataset_intent_service import (
    detect_publishing_dataset_intent,
    expand_publishing_tool_args_with_context,
    normalize_publishing_request,
)


def test_detects_common_publishing_constructs():
    constructs = detect_publishing_constructs(
        "Generate DITA-OT PDF and HTML5 data for copy-to, chunk, xml:lang, keyref, conref, scope and reltable"
    )

    assert "copy-to" in constructs
    assert "chunk" in constructs
    assert "xml:lang" in constructs
    assert "keys" in constructs
    assert "conref" in constructs
    assert "scope-format" in constructs
    assert "reltable" in constructs


def test_detects_attribute_family_constructs():
    constructs = detect_publishing_constructs(
        "Generate data for conref, conrefpush, conrefend, conkeyrefs, xrefs, map attributes, "
        "conditional processing attributes audience platform product props otherprops and DITAVAL"
    )

    assert "conref" in constructs
    assert "conrefpush" in constructs
    assert "conref-range" in constructs
    assert "conkeyref" in constructs
    assert "xref" in constructs
    assert "map-attributes" in constructs
    assert "conditional-processing" in constructs


def test_publishing_dataset_intent_routes_to_dita_ot_not_generate_dita():
    intent = detect_publishing_dataset_intent(
        "Generate a dataset for copy-to with chunk and xml:lang, then create PDF and HTML5 output"
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"
    assert "copy-to" in intent["args"]["detected_constructs"]


def test_publishing_dataset_intent_routes_above_combination_pdf_to_dita_ot():
    intent = detect_publishing_dataset_intent("I want a DITA-OT PDF for the above combination")

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "pdf"
    assert intent["source"] == "auto_publishing_dataset"


def test_branch_filtering_all_attributes_expands_to_publishable_constructs():
    constructs = detect_publishing_constructs(
        "Generate DITA-OT PDF and HTML5 for how branch filtering behaves in case of all the attributes added"
    )

    assert "conditional-processing" in constructs
    assert "map-attributes" in constructs
    assert "chunk" in constructs
    assert "xml:lang" in constructs


def test_shared_intent_expands_above_context_before_generation():
    args = {"prompt": "I want a DITA-OT PDF for the above combination", "output_format": "pdf"}
    expanded = expand_publishing_tool_args_with_context(
        args,
        user_content=args["prompt"],
        prior_messages=[
            "How branch filtering behaves in case of all the attributes added: audience, platform, product, props, otherprops, rev, print, chunk, xml:lang, map attributes.",
        ],
    )

    assert "Previous user context" in expanded["prompt"]
    assert "conditional-processing" in expanded["detected_constructs"]
    assert "map-attributes" in expanded["detected_constructs"]
    assert "chunk" in expanded["detected_constructs"]
    assert "xml:lang" in expanded["detected_constructs"]


def test_mcp_normalization_uses_same_publishing_intent_rules():
    normalized = normalize_publishing_request(
        prompt="Generate DITA-OT PDF and HTML5 for branch filtering with all attributes",
        output_format="pdf",
    )

    assert normalized["output_format"] == "all"
    assert "conditional-processing" in normalized["detected_constructs"]
    assert "map-attributes" in normalized["detected_constructs"]


def test_plain_single_topic_generation_does_not_route_to_publishing():
    assert detect_publishing_dataset_intent("Write a concept topic about reusable content") is None


def test_registry_corpus_contains_constructs_and_oracles(tmp_path):
    result = build_publishing_corpus(
        tmp_path,
        "Generate a dataset for copy-to, chunk, xml:lang, keyref and conref with PDF and HTML5 output",
        output_format="all",
    )

    assert result is not None
    map_text = result["map_path"].read_text(encoding="utf-8")
    summary = json.loads((tmp_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert 'copy-to="topics/reused-copy-a.dita"' in map_text
    assert 'chunk="select-branch to-content"' in map_text
    assert 'xml:lang="fr-FR"' in map_text
    assert 'keys="product-name"' in map_text
    assert "conref-consumer.dita" in map_text
    assert "split" not in map_text
    assert "to-navigation" not in map_text
    assert summary["detected_constructs"]
    assert summary["qa_checklist"]
    assert summary["expected_pdf_review_areas"]
    assert summary["expected_html_review_areas"]
    assert summary["negative_or_risk_cases"]
    assert summary["validation_oracles"]


def test_registry_corpus_contains_requested_attribute_families(tmp_path):
    result = build_publishing_corpus(
        tmp_path,
        "Generate a dataset for conref, conrefpush, conrefend, conkeyrefs, xrefs, map attributes, "
        "conditional processing attributes, PDF and HTML5 output",
        output_format="all",
    )

    assert result is not None
    map_text = result["map_path"].read_text(encoding="utf-8")
    all_text = "\n".join(path.read_text(encoding="utf-8") for path in tmp_path.rglob("*.dita"))
    ditaval_text = (tmp_path / "filters" / "admin-windows.ditaval").read_text(encoding="utf-8")
    summary = json.loads((tmp_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert 'conref="' in all_text
    assert 'conrefend="' in all_text
    assert 'conaction="pushbefore"' in all_text
    assert 'conkeyref="reuse-key/reuse-para"' in all_text
    assert "<xref " in all_text
    assert 'navtitle="Locked map title"' in map_text
    assert 'locktitle="yes"' in map_text
    assert 'audience="admin"' in map_text
    assert 'platform="windows"' in map_text
    assert 'product="aem-guides"' in map_text
    assert '<prop att="audience"' in ditaval_text
    assert "conrefpush" in summary["detected_constructs"]
    assert "conditional-processing" in summary["detected_constructs"]
    assert summary["negative_or_risk_cases"]
    assert summary["validation_oracles"]
