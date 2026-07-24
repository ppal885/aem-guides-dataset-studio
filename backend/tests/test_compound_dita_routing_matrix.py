from app.services import chat_service
from app.services.generation_intent_router_service import route_generation_intent
from app.services.prompt_router_service import route_prompt
from app.services.publishing_dataset_intent_service import detect_publishing_dataset_intent


def test_compound_dita_ot_evidence_question_stays_grounded_answer():
    prompt = (
        "How does DITA-OT preprocess conref, keyref, copy-to, chunk, and profile "
        "before PDF or HTML5 generation? Give evidence."
    )

    route = route_prompt(prompt)

    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert detect_publishing_dataset_intent(prompt) is None
    assert route_generation_intent(prompt, requested_tool="ask_dita_expert") is None
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_compound_dita_ot_publish_request_routes_to_publishing_dataset():
    prompt = (
        "Publish DITA-OT PDF and HTML5 for conref, keyref, copy-to, chunk, and profile "
        "with expected output oracles."
    )

    route = route_prompt(prompt)
    intent = detect_publishing_dataset_intent(prompt)

    assert route.intent == "dita_ot_generation"
    assert route.execution_hint == "run_directly"
    assert route.candidate_contract["name"] == "generate_dita_ot_pdf"
    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"
    assert {"conref", "keys", "copy-to", "chunk", "conditional-processing"}.issubset(
        set(intent["args"]["detected_constructs"])
    )


def test_compound_aem_guides_behavior_question_does_not_publish():
    prompt = (
        "How does copy-to with chunk and keyref behave in AEM Guides Map Console "
        "when publishing to DITA-OT PDF and HTML5? Give evidence."
    )

    route = route_prompt(prompt)

    assert route.legacy_answer_mode in {"grounded_dita_answer", "grounded_aem_answer", "default"}
    assert route.execution_hint == "answer_directly"
    assert detect_publishing_dataset_intent(prompt) is None


def test_metadata_cascading_output_question_routes_to_grounded_dita():
    prompt = "What is metadata cascading? how it works in AEM Sites or pdf"

    route = route_prompt(prompt)

    assert route.intent == "dita_question"
    assert route.execution_hint == "answer_directly"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert detect_publishing_dataset_intent(prompt) is None


def test_searchtitle_output_question_routes_to_grounded_dita():
    prompt = "How does searchtitle behave in AEM Sites or PDF?"

    route = route_prompt(prompt)

    assert route.intent == "dita_question"
    assert route.execution_hint == "answer_directly"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert detect_publishing_dataset_intent(prompt) is None


def test_followup_same_combination_generation_routes_to_dita_ot_with_context():
    prompt = "Now generate PDF and HTML5 test data for the same combination."
    prior = [
        "How does copy-to with chunk and keyref behave in AEM Guides Map Console "
        "when publishing to DITA-OT PDF and HTML5?"
    ]

    intent = route_generation_intent(
        prompt,
        prior_messages=prior,
        requested_tool="generate_dita",
        source="unit",
    )

    assert intent is not None
    assert intent["name"] == "generate_dita_ot_pdf"
    assert intent["args"]["output_format"] == "all"
    assert "Previous user context" in intent["args"]["prompt"]
    assert {"copy-to", "chunk", "keys"}.issubset(set(intent["args"]["detected_constructs"]))


def test_route_prompt_recognizes_searchtitle_followup_html5_generation():
    prompt = "Generate a HTML5 for the same containing the searchtitle tag"

    route = route_prompt(prompt)

    assert route.intent == "dita_ot_generation"
    assert route.execution_hint == "run_directly"
    assert route.candidate_contract["name"] == "generate_dita_ot_pdf"
    assert route.candidate_contract["args"]["output_format"] == "html5"
    assert "searchtitle" in route.candidate_contract["args"]["detected_constructs"]


def test_route_prompt_recognizes_branch_filtering_all_attrs_publishing_generation():
    prompt = (
        "I want PDF and HTML5 publishing evidence for branch filtering with conref, conrefpush, "
        "conrefend, keyref, xref, conkeyref, map attrs and conditional processing attrs"
    )

    route = route_prompt(prompt)

    assert route.intent == "dita_ot_generation"
    assert route.candidate_contract["args"]["output_format"] == "all"
    assert {
        "conref",
        "conrefpush",
        "conref-range",
        "conkeyref",
        "xref",
        "map-attributes",
        "conditional-processing",
    }.issubset(set(route.candidate_contract["args"]["detected_constructs"]))


def test_route_prompt_accepts_human_pdf2_html5_spellings():
    prompt = "Generate PD2 and HTML 5 transformation evidence for same chunk and xml:lang combination"

    route = route_prompt(prompt)
    intent = detect_publishing_dataset_intent(prompt)

    assert route.intent == "dita_ot_generation"
    assert intent is not None
    assert intent["args"]["output_format"] == "all"
    assert {"chunk", "xml:lang"}.issubset(set(intent["args"]["detected_constructs"]))


def test_compound_aem_guides_upload_request_is_not_dita_ot_generation():
    prompt = "Upload the generated DITA-OT PDF and HTML5 dataset to AEM Guides under /content/dam/test."

    assert detect_publishing_dataset_intent(prompt) is None


def test_single_topic_authoring_with_pdf_word_is_not_publishing_dataset():
    prompt = "Write one DITA concept topic explaining when to use format='pdf' on an xref."

    assert detect_publishing_dataset_intent(prompt) is None
