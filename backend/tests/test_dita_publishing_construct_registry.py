import json

from app.services.chat_service import detect_publishing_dataset_intent
from app.services.dita_publishing_construct_registry import (
    SUMMARY_FILENAME,
    build_publishing_corpus,
    detect_publishing_constructs,
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


def test_publishing_dataset_intent_routes_to_dita_ot_not_generate_dita():
    intent = detect_publishing_dataset_intent(
        "Generate a dataset for copy-to with chunk and xml:lang, then create PDF and HTML5 output"
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"
    assert "copy-to" in intent["args"]["detected_constructs"]


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
