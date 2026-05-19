"""Structural validation for chat-authored DITA."""

from app.services.dita_authoring_structure import (
    validate_dita_topic_structure,
    validate_dita_topic_structure_categorized,
)
from app.services.dita_xml_headers import build_dita_header


def test_valid_task_minimal():
    body = """<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc><taskbody><steps><step id="s1"><cmd>C</cmd></step></steps></taskbody></task>"""
    xml = f"{build_dita_header('task')}\n{body}"
    issues = validate_dita_topic_structure(xml, expected_root="task")
    assert issues == []


def test_wrong_root():
    body = """<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc><taskbody><steps><step id="s1"><cmd>C</cmd></step></steps></taskbody></task>"""
    xml = f"{build_dita_header('task')}\n{body}"
    issues = validate_dita_topic_structure(xml, expected_root="concept")
    assert any("Root element" in i for i in issues)
    assert any("Root element is <task> but expected <concept>" in i for i in issues)


def test_duplicate_ids():
    body = """<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc><taskbody><steps><step id="x"><cmd>A</cmd></step><step id="x"><cmd>B</cmd></step></steps></taskbody></task>"""
    xml = f"{build_dita_header('task')}\n{body}"
    issues = validate_dita_topic_structure(xml, expected_root="task")
    assert any("Duplicate" in i for i in issues)


def test_not_well_formed_xml_error():
    xml = f"{build_dita_header('task')}\n<task><unclosed>"
    errs, warns = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert errs and any("Not well-formed XML" in e for e in errs)
    assert warns == []


def test_missing_shortdesc_warning_only():
    body = (
        '<topic id="x" xml:lang="en-US"><title>T</title><body><p>Hi</p></body></topic>'
    )
    xml = f"{build_dita_header('topic')}\n{body}"
    errs, warns = validate_dita_topic_structure_categorized(xml, expected_root="topic")
    assert errs == []
    assert any("Missing <shortdesc>" in w for w in warns)


def test_nested_p_error():
    body_bad = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody><steps><step id="s1"><cmd><p>outer<p>inner</p></p></cmd></step></steps></taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body_bad}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("Illegal nesting: <p> contains <p>" in e for e in errs)


def test_section_directly_under_taskbody_is_error():
    """Regression: <section> is not a valid direct child of <taskbody> (DITA 1.3)."""
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody>'
        '<steps><step id="s1"><cmd>Open</cmd></step></steps>'
        '<section id="form-and-settings"><title>Form And Settings</title><p>x</p></section>'
        '</taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("<section> is not a valid direct child of <taskbody>" in e for e in errs), errs


def test_simpletable_directly_under_taskbody_is_error():
    """Regression: <simpletable> must live inside <example>/<section>/etc., not <taskbody>."""
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody>'
        '<steps><step id="s1"><cmd>Open</cmd></step></steps>'
        '<simpletable><sthead><stentry>A</stentry></sthead><strow><stentry>1</stentry></strow></simpletable>'
        '</taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("<simpletable> is not a valid direct child of <taskbody>" in e for e in errs), errs


def test_step_missing_cmd_error():
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody><steps><step id="s1"><info><p>x</p></info></step></steps></taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("missing <cmd>" in e for e in errs)


def test_empty_xref_href_error():
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody><steps><step id="s1"><cmd>See <xref href=""/>.</cmd></step></steps></taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("Empty xref @href" in e for e in errs)


def test_unresolved_conref_fragment_error():
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody><steps><step id="s1"><cmd><ph conref="#no-such-id"/></cmd></step></steps></taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, _ = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert any("Unresolved conref" in e for e in errs)


def test_suspicious_onclick_warning_example_ui_string():
    body = (
        '<task id="t1" xml:lang="en-US"><title>T</title><shortdesc>S</shortdesc>'
        '<taskbody><steps><step id="s1" onclick="alert(1)"><cmd>C</cmd></step></steps></taskbody></task>'
    )
    xml = f"{build_dita_header('task')}\n{body}"
    errs, warns = validate_dita_topic_structure_categorized(xml, expected_root="task")
    assert errs == []
    assert any(w == "Suspicious attribute on <step>: @onclick" for w in warns)


def test_categorized_warnings_do_not_appear_in_errors_only_api():
    body = '<topic id="x" xml:lang="en-US"><title>T</title><body><p>x</p></body></topic>'
    xml = f"{build_dita_header('topic')}\n{body}"
    errs_only = validate_dita_topic_structure(xml, expected_root="topic")
    assert errs_only == []
    _, warns = validate_dita_topic_structure_categorized(xml, expected_root="topic")
    assert len(warns) >= 1
