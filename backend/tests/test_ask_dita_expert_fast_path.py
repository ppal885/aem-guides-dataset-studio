import mcp_server


def test_challenge_prompt_does_not_treat_steps_or_scope_as_constructs():
    question = (
        "Provide source DITA, publishing steps, expected HTML/JCR output, negative cases, "
        "mapping scope, evidence source, and explicitly list every behavior that is not yet verified"
    )

    assert mcp_server._recognized_dita_constructs_from_question(question) == []


def test_searchtitle_product_verification_bypasses_registry_fast_path():
    question = (
        "For searchtitle, provide publishing steps, expected HTML/JCR output, mapping scope, "
        "evidence sources, negative cases, fallback behavior, and AEM search indexing behavior."
    )
    constructs = mcp_server._recognized_dita_constructs_from_question(question)

    assert constructs == ["searchtitle"]
    assert not mcp_server._should_use_dita_construct_fast_path(question, constructs)


def test_simple_explicit_construct_question_keeps_fast_path():
    question = "What does @cascade do?"
    constructs = mcp_server._recognized_dita_constructs_from_question(question)

    assert constructs == ["cascade"]
    assert mcp_server._should_use_dita_construct_fast_path(question, constructs)


def test_simple_bare_unambiguous_construct_question_keeps_fast_path():
    question = "What is tablelist used for?"
    constructs = mcp_server._recognized_dita_constructs_from_question(question)

    assert constructs == ["tablelist"]
    assert mcp_server._should_use_dita_construct_fast_path(question, constructs)


def test_explicit_ambiguous_construct_remains_supported():
    question = "What does the @scope attribute do?"
    constructs = mcp_server._recognized_dita_constructs_from_question(question)

    assert constructs == ["scope"]
    assert mcp_server._should_use_dita_construct_fast_path(question, constructs)
