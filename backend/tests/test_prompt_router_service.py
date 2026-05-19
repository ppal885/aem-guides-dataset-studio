from app.services.execution_policy_service import decide_execution_policy
from app.services.prompt_router_service import is_dita_ot_parameter_query, route_prompt
from app.services import chat_service


def test_route_prompt_detects_plain_dita_generation_request():
    route = route_prompt("Create 20 concept topics on cars")

    assert route.intent == "dita_generation"
    assert route.supported is True
    assert route.legacy_answer_mode == "generation_request"
    assert route.candidate_contract["preview"]["topic_family"] == "concept"
    assert route.candidate_contract["preview"]["status"] == "preview_ready"


def test_route_prompt_detects_ambiguous_dita_generation_request():
    route = route_prompt("Create 20 topics on cars")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_generation"
    assert route.needs_clarification is True
    assert policy.action == "clarify_first"
    assert "concept" in str(policy.clarification_question).lower()


def test_route_prompt_uses_constraint_implied_family_for_dita_generation():
    route = route_prompt("Create 5 topics using choicetable and stepxmp for output presets")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_generation"
    assert route.needs_clarification is False
    assert route.candidate_contract["preview"]["topic_family"] == "task"
    assert policy.action == "preview_first"


def test_route_prompt_detects_dita_question():
    route = route_prompt("What can go inside taskbody?")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"


def test_route_prompt_keeps_linklist_title_toc_question_on_dita_path():
    prompt = "link list title should come in pdf output toc??"
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_route_prompt_keeps_dita_construct_output_question_on_dita_path():
    prompt = "how foreign element is used in PDF output and Web outputs??"
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_route_prompt_keeps_native_pdf_dita_ot_args_on_aem_product_path():
    prompt = "How DITA OT Arguments affect draft comment in Native PDF"
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "native_pdf_guidance"
    assert route.legacy_answer_mode == "grounded_aem_answer"
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_aem_answer"
    assert chat_service._should_include_structural_dita_rag(prompt) is False


def test_is_dita_ot_parameter_query_matches_typo_arguments():
    assert is_dita_ot_parameter_query("What Argumernts should be given in dita ot?") is True


def test_route_prompt_routes_standalone_dita_ot_parameter_question_to_grounded_dita():
    prompt = "What Argumernts should be given in dita ot?"
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_ot_build"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"
    assert chat_service._should_include_structural_dita_rag(prompt) is True


def test_route_prompt_prefers_dita_comparison_answer_over_xml_generation():
    prompt = "What is the difference between conref, conkeyref, and keyref? Show XML examples."
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert route.candidate_contract == {}
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"
    assert chat_service._is_plain_generate_dita_request(prompt) is False


def test_route_prompt_detects_answer_then_generation_mixed_intent():
    prompt = "Explain conref and then generate a conref example bundle."
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_answer_then_generation"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert route.candidate_contract["mixed_intent"] is True
    assert route.candidate_contract["answer_segment"].lower() == "explain conref"
    assert route.candidate_contract["generation_segment"].lower() == "generate a conref example bundle"
    assert route.candidate_contract["intent_order"] == ["answer", "generation"]
    assert policy.action == "answer_then_preview"
    assert policy.review_required is True


def test_route_prompt_detects_generation_first_mixed_intent():
    prompt = "Generate a conref bundle and explain what it will contain."
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_answer_then_generation"
    assert route.candidate_contract["intent_order"] == ["generation", "answer"]
    assert route.candidate_contract["generation_segment"].lower() == "generate a conref bundle"
    assert policy.action == "answer_then_preview"


def test_route_prompt_keeps_plain_construct_example_on_generation_path():
    route = route_prompt("Show me a keyscope example")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_generation"
    assert route.legacy_answer_mode == "generation_request"
    assert policy.action in {"preview_first", "clarify_first"}


def test_route_prompt_answers_plain_construct_example_without_generation_artifacts():
    route = route_prompt("Give me example of topichead please")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"


def test_route_prompt_generates_when_construct_example_requests_bundle():
    route = route_prompt("Generate a topichead example bundle")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_generation"
    assert route.legacy_answer_mode == "generation_request"
    assert policy.action in {"preview_first", "clarify_first"}


def test_route_prompt_detects_processing_role_as_dita_question():
    route = route_prompt("What do you mean by processing-role in dita?")
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"


def test_route_prompt_detects_oasis_metadata_extension_dita_questions():
    for prompt in (
        "What is the foreign element in DITA?",
        "What is data-about in DITA?",
        "What is the boolean element in DITA?",
        "What is index-base in DITA?",
        "What is itemgroup in DITA?",
        "What is no-topic-nesting in DITA?",
        "What is the state element in DITA?",
        "What is the unknown element in DITA?",
        "What is required-cleanup in DITA?",
        "What are DITAVAL elements?",
        "What is DITAVAL prop?",
        "What is revprop?",
        "What is startflag in a DITAVAL file?",
        "What is style-conflict in DITAVAL?",
        "What are id attributes in DITA?",
        "What are metadata attributes in DITA?",
        "What are localization attributes in DITA?",
        "What are debug attributes in DITA?",
        "What are architectural attributes in DITA?",
        "What are common map attributes in DITA?",
        "What are CALS table attributes in DITA?",
        "What are display attributes in DITA?",
        "What are date attributes in DITA?",
        "What are link relationship attributes in DITA?",
        "What are common attributes in DITA?",
        "What are simpletable attributes in DITA?",
        "What is xtrf in DITA?",
        "What is the class attribute in DITA?",
        "What is colsep in a CALS table?",
        "What is expanse in DITA?",
        "What is relcolwidth in DITA?",
        "What is golive in DITA?",
        "What is xml:lang?",
        "What is the translate attribute?",
    ):
        route = route_prompt(prompt)
        policy = decide_execution_policy(route)

        assert route.intent == "dita_question"
        assert route.legacy_answer_mode == "grounded_dita_answer"
        assert policy.action == "answer_directly"
        assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_route_prompt_prefers_aem_guides_question_over_dita_generation_keywords():
    route = route_prompt("How do you create a topic or map in AEM Guides?")
    policy = decide_execution_policy(route)

    assert route.intent == "aem_guides_question"
    assert route.legacy_answer_mode == "grounded_aem_answer"
    assert policy.action == "answer_directly"


def test_route_prompt_routes_choicetable_authoring_in_aem_guides_to_grounded_dita():
    prompt = "How to create Choicetables in AEM guides?"
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_directly"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_route_prompt_routes_downloadable_zip_bundle_before_grounded_dita_answer():
    prompt = (
        "How does processing-role work on a topicgroup with mapref? "
        "I want the root map and submap with those topicrefs generated as a zip."
    )
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_answer_then_generation"
    assert route.legacy_answer_mode == "grounded_dita_answer"
    assert policy.action == "answer_then_preview"
    assert chat_service._determine_answer_mode(prompt) == "grounded_dita_answer"


def test_route_prompt_routes_standalone_map_zip_request_to_generation():
    prompt = (
        "I need a root ditamap with topicgroup processing-role resource-only, a mapref to submap.ditamap, "
        "and a topicref to topic.dita, plus submap.ditamap with a topicref. Deliver the bundle in zip."
    )
    route = route_prompt(prompt)
    policy = decide_execution_policy(route)

    assert route.intent == "dita_generation"
    assert route.legacy_answer_mode == "generation_request"
    assert policy.action in {"preview_first", "clarify_first"}
    assert chat_service._determine_answer_mode(prompt) == "generation_request"


def test_route_prompt_does_not_misroute_zip_definition_question_to_generation():
    prompt = "What is a zip file in DITA output workflows?"
    route = route_prompt(prompt)

    assert route.intent == "dita_question"
    assert route.legacy_answer_mode == "grounded_dita_answer"


def test_route_prompt_rejects_non_dita_automation_request():
    route = route_prompt("Generate Playwright page objects and step definitions")
    policy = decide_execution_policy(route)

    assert route.intent == "unsupported"
    assert route.supported is False
    assert policy.action == "reject_as_unsupported"
