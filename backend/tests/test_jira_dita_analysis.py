"""Tests for JIRA DITA issue analysis pipeline."""
from app.services.llm_analyzer import normalize_issue_text
from app.services.dataset_generator import sanitize_dataset_example, generate_dataset_record


def test_normalize_issue_text():
    """Build correct text from issue dict."""
    issue = {
        "issue_key": "GUIDES-123",
        "summary": "Keyref not resolving",
        "description": "Keys defined in map are not resolved in topic.",
        "labels": ["dita", "keyref"],
        "comments": [
            {"body_text": "Confirmed in 4.2", "author": "dev", "created": "2024-01-01"},
        ],
    }
    text = normalize_issue_text(issue)
    assert "Summary: Keyref not resolving" in text
    assert "Description: Keys defined" in text
    assert "Labels: dita, keyref" in text
    assert "Comments:" in text
    assert "Confirmed in 4.2" in text


def test_normalize_issue_text_empty():
    """Empty issue returns No content."""
    text = normalize_issue_text({})
    assert text == "No content"


def test_sanitize_dataset_example():
    """IDs are prefixed with issue_key to avoid duplicates."""
    dataset_example = {
        "map": '<map id="m1"><topicref href="t1.dita"/></map>',
        "topic": '<topic id="t1"><title>Test</title></topic>',
        "glossary": "",
        "subject_scheme": "",
    }
    out = sanitize_dataset_example(dataset_example, "GUIDES-43199")
    assert 'id="GUIDES_43199_m1"' in out["map"]
    assert 'id="GUIDES_43199_t1"' in out["topic"]
    assert out["glossary"] == ""
    assert out["subject_scheme"] == ""


def test_sanitize_dataset_example_single_quotes():
    """Single-quoted id attributes are also prefixed."""
    dataset_example = {"topic": "<topic id='foo'><title>x</title></topic>", "map": "", "glossary": "", "subject_scheme": ""}
    out = sanitize_dataset_example(dataset_example, "X-1")
    assert "id='X_1_foo'" in out["topic"]


def test_generate_dataset_record():
    """Build full record with sanitized dataset_example."""
    issue = {"issue_key": "GUIDES-99", "summary": "Conref conflict"}
    llm_result = {
        "category": "conref_conflict",
        "dita_features": ["conref", "topicref"],
        "root_cause": "Duplicate ID after conref",
        "fix": "Use unique IDs",
        "dataset_example": {"map": '<map id="m1"/>', "topic": '<topic id="t1"/>', "glossary": "", "subject_scheme": ""},
    }
    record = generate_dataset_record(issue, llm_result)
    assert record["issue_key"] == "GUIDES-99"
    assert record["summary"] == "Conref conflict"
    assert record["category"] == "conref_conflict"
    assert record["dita_features"] == ["conref", "topicref"]
    assert record["root_cause"] == "Duplicate ID after conref"
    assert record["fix"] == "Use unique IDs"
    assert 'id="GUIDES_99_m1"' in record["dataset_example"]["map"]
    assert 'id="GUIDES_99_t1"' in record["dataset_example"]["topic"]
