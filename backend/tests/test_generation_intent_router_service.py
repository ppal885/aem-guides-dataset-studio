from app.services.generation_intent_router_service import (
    normalize_generation_tool_intent,
    route_generation_intent,
)


def test_router_sends_publishing_requests_to_dita_ot():
    intent = route_generation_intent(
        "Generate DITA-OT PDF and HTML5 data for copy-to, chunk, and xml:lang",
        requested_tool="generate_dita",
        source="unit",
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"
    assert "copy-to" in intent["args"]["detected_constructs"]


def test_router_uses_prior_context_for_same_example_requests():
    intent = route_generation_intent(
        "show me an example of above",
        prior_messages=[
            "What is metadata cascading?",
            "How cascade will behave in publishing",
        ],
        requested_tool="generate_dita",
        source="unit",
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert "metadata cascading" in intent["args"]["prompt"].lower()
    assert "metadata-cascade" in intent["args"]["detected_constructs"]


def test_router_keeps_plain_single_topic_authoring_on_generate_dita():
    intent = route_generation_intent(
        "Write one DITA concept topic about authoring snippets",
        requested_tool="generate_dita",
        source="unit",
    )

    assert intent is None


def test_normalizer_only_rewrites_generate_dita_intents():
    intent = normalize_generation_tool_intent(
        {
            "name": "generate_dita",
            "args": {"text": "I want a DITA-OT PDF for copy-to and chunk"},
            "source": "llm",
        },
        user_content="I want a DITA-OT PDF for copy-to and chunk",
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["source"] == "llm_redirected_to_dita_ot"
