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
from app.services import chat_service
from app.services.chat_tools import parse_tool_intent_from_content


def test_detects_common_publishing_constructs():
    constructs = detect_publishing_constructs(
        "Generate DITA-OT PDF and HTML5 data for copy-to, chunk, xml:lang, keyref, conref, scope, reltable, and search title"
    )

    assert "copy-to" in constructs
    assert "chunk" in constructs
    assert "xml:lang" in constructs
    assert "keys" in constructs
    assert "conref" in constructs
    assert "scope-format" in constructs
    assert "reltable" in constructs
    assert "searchtitle" in constructs


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


def test_shared_intent_preserves_searchtitle_context_for_html5_generation():
    args = {"prompt": "generate a HTML5 for the same containing the tag", "output_format": "html5"}
    expanded = expand_publishing_tool_args_with_context(
        args,
        user_content=args["prompt"],
        prior_messages=[
            "what is search title and how it is used in dita",
            "how it works in AEM Sites or pdf",
        ],
    )

    assert "Previous user context" in expanded["prompt"]
    assert expanded["output_format"] == "html5"
    assert "searchtitle" in expanded["detected_constructs"]


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


def test_generate_dita_slash_redirects_publishing_to_dita_ot():
    intent = parse_tool_intent_from_content(
        "/generate_dita Generate DITA-OT PDF and HTML5 data for copy-to with chunk and xml:lang"
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"


def test_generate_dita_tool_intent_redirects_to_dita_ot():
    intent = chat_service._normalize_generation_tool_intent(
        "session-id",
        "Generate DITA-OT PDF data for copy-to with chunk and xml:lang",
        {
            "name": "generate_dita",
            "args": {"text": "Generate DITA-OT PDF data for copy-to with chunk and xml:lang"},
            "source": "llm",
        },
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["source"] == "llm_redirected_to_dita_ot"


def test_contextual_same_generation_routes_to_freeform_dataset(monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "_recent_user_messages_before_latest",
        lambda session_id, user_content, limit=4: [
            "How does conref and keyref behave together in a DITA map?"
        ],
    )

    intent = chat_service._contextual_dita_dataset_tool_intent(
        "session-id",
        "generate DITA data for the same",
    )

    assert intent is not None
    assert intent["name"] == "create_job"
    assert intent["args"]["recipe_type"] == "freeform"
    assert "conref" in intent["args"]["prompt_text"]


def test_contextual_example_above_metadata_cascading_routes_to_dataset(monkeypatch):
    monkeypatch.setattr(
        chat_service,
        "_recent_user_messages_before_latest",
        lambda session_id, user_content, limit=4: [
            "What is metadata cascading?",
            "How cascade will behave in publishing",
        ],
    )

    intent = chat_service._contextual_dita_dataset_tool_intent(
        "session-id",
        "show me an example of above",
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert "metadata cascading" in intent["args"]["prompt"].lower()
    assert "metadata-cascade" in intent["args"]["detected_constructs"]


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


def test_registry_corpus_contains_searchtitle_topic_and_oracles(tmp_path):
    result = build_publishing_corpus(
        tmp_path,
        "generate a HTML5 for the same containing the tag\n\n"
        "Previous user context to preserve for DITA-OT publishing dataset generation:\n"
        "what is search title and how it is used in dita\n\n"
        "how it works in AEM Sites or pdf",
        output_format="html5",
    )

    assert result is not None
    map_text = result["map_path"].read_text(encoding="utf-8")
    topic_text = (tmp_path / "topics" / "searchtitle-topic.dita").read_text(encoding="utf-8")
    summary = json.loads((tmp_path / SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert "<title>DITA-OT publishing dataset for searchtitle</title>" in map_text
    assert "<titlealts>" in topic_text
    assert "<searchtitle>AEM Guides search-title publishing oracle</searchtitle>" in topic_text
    assert "generate a HTML5 for the same" not in topic_text
    assert "searchtitle" in summary["detected_constructs"]
    assert any("AEM Sites" in item or "HTML5" in item for item in summary["expected_html_review_areas"])
