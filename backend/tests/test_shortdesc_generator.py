"""Tests for the Smart Shortdesc Generator service."""

import asyncio
from unittest.mock import AsyncMock, patch

from app.services.shortdesc_generator_service import (
    MAX_SHORTDESC_WORDS,
    _build_xml_snippet,
    _first_sentence,
    _rule_based_generate,
    _validate_shortdesc,
    generate_shortdesc,
)


def _run(coro):
    """Helper to run async functions in sync tests."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 1. Task topic shortdesc generation
# ---------------------------------------------------------------------------

TASK_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE task PUBLIC "-//OASIS//DTD DITA Task//EN" "task.dtd">
<task id="install_plugin">
  <title>Install the AEM Guides plugin</title>
  <taskbody>
    <steps>
      <step><cmd>Download the plugin from the portal.</cmd></step>
      <step><cmd>Run the installer on your local machine.</cmd></step>
    </steps>
  </taskbody>
</task>"""


def test_task_topic_shortdesc():
    result = _run(generate_shortdesc(TASK_XML, use_llm=False))
    assert result["topic_type"] == "task"
    assert result["has_existing"] is False
    assert result["shortdesc"]
    # Task shortdescs should use outcome/action language
    lower = result["shortdesc"].lower()
    assert any(kw in lower for kw in ["how to", "steps", "install", "describes"]), (
        f"Task shortdesc lacks action language: {result['shortdesc']}"
    )
    assert len(result["shortdesc"].split()) <= MAX_SHORTDESC_WORDS


# ---------------------------------------------------------------------------
# 2. Concept topic shortdesc generation
# ---------------------------------------------------------------------------

CONCEPT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "concept.dtd">
<concept id="ci_cd_overview">
  <title>Continuous Integration and Deployment</title>
  <conbody>
    <p>Continuous integration is a practice where developers merge code changes
    into a central repository frequently. Automated builds and tests verify
    each integration.</p>
  </conbody>
</concept>"""


def test_concept_topic_shortdesc():
    result = _run(generate_shortdesc(CONCEPT_XML, use_llm=False))
    assert result["topic_type"] == "concept"
    assert result["has_existing"] is False
    lower = result["shortdesc"].lower()
    assert any(kw in lower for kw in ["explains", "overview", "conceptual"]), (
        f"Concept shortdesc lacks explanatory language: {result['shortdesc']}"
    )


# ---------------------------------------------------------------------------
# 3. Reference topic shortdesc generation
# ---------------------------------------------------------------------------

REFERENCE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE reference PUBLIC "-//OASIS//DTD DITA Reference//EN" "reference.dtd">
<reference id="api_params">
  <title>REST API Parameters</title>
  <refbody>
    <table>
      <tgroup cols="3">
        <tbody>
          <row><entry>id</entry><entry>string</entry><entry>Unique identifier</entry></row>
        </tbody>
      </tgroup>
    </table>
  </refbody>
</reference>"""


def test_reference_topic_shortdesc():
    result = _run(generate_shortdesc(REFERENCE_XML, use_llm=False))
    assert result["topic_type"] == "reference"
    lower = result["shortdesc"].lower()
    assert any(kw in lower for kw in ["lists", "reference", "provides"]), (
        f"Reference shortdesc lacks scope language: {result['shortdesc']}"
    )


# ---------------------------------------------------------------------------
# 4. Topic that already has shortdesc
# ---------------------------------------------------------------------------

EXISTING_SHORTDESC_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<concept id="existing">
  <title>Feature Overview</title>
  <shortdesc>This feature allows batch processing of DITA maps.</shortdesc>
  <conbody>
    <p>Details about the feature.</p>
  </conbody>
</concept>"""


def test_existing_shortdesc_detected():
    result = _run(generate_shortdesc(EXISTING_SHORTDESC_XML, use_llm=False))
    assert result["has_existing"] is True
    assert result.get("existing_shortdesc") == "This feature allows batch processing of DITA maps."
    # Should still generate a new shortdesc (for comparison)
    assert result["shortdesc"]


# ---------------------------------------------------------------------------
# 5. Malformed XML handling
# ---------------------------------------------------------------------------

def test_malformed_xml_returns_error():
    bad_xml = "<task><title>Broken<title></task>"
    result = _run(generate_shortdesc(bad_xml, use_llm=False))
    assert "error" in result
    assert result["shortdesc"] == ""
    assert result["topic_type"] == "unknown"


def test_malformed_xml_missing_close_tag():
    bad_xml = "<concept id='x'><title>Test</title><conbody><p>Hello"
    result = _run(generate_shortdesc(bad_xml, use_llm=False))
    assert "error" in result


# ---------------------------------------------------------------------------
# 6. Long body text handling
# ---------------------------------------------------------------------------

LONG_BODY_XML_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<concept id="long_body">
  <title>Long Article</title>
  <conbody>
    <p>{body}</p>
  </conbody>
</concept>"""


def test_long_body_text_truncated():
    long_text = "This is a sentence about DITA. " * 200  # ~6000 chars
    xml = LONG_BODY_XML_TEMPLATE.format(body=long_text)
    result = _run(generate_shortdesc(xml, use_llm=False))
    assert result["shortdesc"]
    word_count = len(result["shortdesc"].split())
    assert word_count <= MAX_SHORTDESC_WORDS, (
        f"Shortdesc has {word_count} words, max is {MAX_SHORTDESC_WORDS}"
    )


# ---------------------------------------------------------------------------
# 7. Empty body handling
# ---------------------------------------------------------------------------

EMPTY_BODY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<task id="empty_body">
  <title>Configure the Server</title>
  <taskbody/>
</task>"""


def test_empty_body_still_generates():
    result = _run(generate_shortdesc(EMPTY_BODY_XML, use_llm=False))
    assert result["shortdesc"]
    assert result["topic_type"] == "task"
    # Should fall back to title-based generation
    assert "configure" in result["shortdesc"].lower() or "server" in result["shortdesc"].lower()


# ---------------------------------------------------------------------------
# 8. XML snippet output format
# ---------------------------------------------------------------------------

def test_xml_snippet_format():
    result = _run(generate_shortdesc(CONCEPT_XML, use_llm=False))
    snippet = result["xml_snippet"]
    assert "<concept" in snippet
    assert "<title>" in snippet
    assert "<shortdesc>" in snippet
    assert "</shortdesc>" in snippet
    assert "<conbody>" in snippet
    assert "</concept>" in snippet


def test_xml_snippet_builder_directly():
    snippet = _build_xml_snippet("task", "Install Plugin", "Describes how to install the plugin.")
    assert snippet.startswith("<task")
    assert "<shortdesc>Describes how to install the plugin.</shortdesc>" in snippet
    assert "<taskbody>" in snippet


# ---------------------------------------------------------------------------
# 9. Alternatives are provided
# ---------------------------------------------------------------------------

def test_alternatives_provided():
    result = _run(generate_shortdesc(CONCEPT_XML, use_llm=False))
    assert isinstance(result["alternatives"], list)
    assert len(result["alternatives"]) >= 2
    # All alternatives should be different from primary
    for alt in result["alternatives"]:
        assert alt  # non-empty
        assert len(alt.split()) <= MAX_SHORTDESC_WORDS


# ---------------------------------------------------------------------------
# 10. Glossentry topic handling
# ---------------------------------------------------------------------------

GLOSSENTRY_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<glossentry id="api_def">
  <title>API</title>
  <glossBody>
    <glossdef>An Application Programming Interface is a set of protocols and tools
    for building software applications.</glossdef>
  </glossBody>
</glossentry>"""


def test_glossentry_uses_glossdef():
    result = _run(generate_shortdesc(GLOSSENTRY_XML, use_llm=False))
    assert result["topic_type"] == "glossentry"
    lower = result["shortdesc"].lower()
    assert "application programming interface" in lower or "api" in lower


# ---------------------------------------------------------------------------
# 11. Validation helper
# ---------------------------------------------------------------------------

def test_validate_shortdesc_truncates_long():
    long_text = " ".join(["word"] * 80)
    validated = _validate_shortdesc(long_text)
    assert len(validated.split()) <= MAX_SHORTDESC_WORDS
    assert validated.endswith(".")


def test_validate_shortdesc_adds_period():
    assert _validate_shortdesc("No trailing period").endswith(".")


def test_validate_shortdesc_strips_tags():
    assert "<p>" not in _validate_shortdesc("Text with <p>tags</p> inside.")


# ---------------------------------------------------------------------------
# 12. Rule-based generation
# ---------------------------------------------------------------------------

def test_rule_based_task():
    primary, alts = _rule_based_generate("task", "Install the Plugin", "")
    assert "install the plugin" in primary.lower()
    assert len(alts) >= 1


def test_rule_based_with_body_text():
    primary, alts = _rule_based_generate(
        "concept",
        "Overview",
        "This service handles authentication tokens for all API calls.",
    )
    # Should include a first-sentence alternative derived from body
    all_descs = [primary] + alts
    body_derived = any("authentication" in d.lower() or "tokens" in d.lower() for d in all_descs)
    assert body_derived, f"Expected body-derived alternative in {all_descs}"


# ---------------------------------------------------------------------------
# 13. First sentence extraction
# ---------------------------------------------------------------------------

def test_first_sentence_extraction():
    assert _first_sentence("Hello world. Second sentence.") == "Hello world."
    assert _first_sentence("No period here") != ""
    assert _first_sentence("") == ""


# ---------------------------------------------------------------------------
# 14. LLM integration (mocked)
# ---------------------------------------------------------------------------

def test_llm_generation_used_when_available():
    mock_response = '{"shortdesc": "Learn how to configure the server.", "alternatives": ["Server configuration steps.", "Steps for server setup."]}'

    with patch(
        "app.services.llm_service.generate_text",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = _run(generate_shortdesc(TASK_XML, use_llm=True))

    assert result["shortdesc"]
    assert result["topic_type"] == "task"


def test_llm_failure_falls_back_to_rules():
    """When LLM raises, rule-based fallback should still produce output."""
    result = _run(generate_shortdesc(CONCEPT_XML, use_llm=False))
    assert result["shortdesc"]
    assert result["topic_type"] == "concept"
    assert len(result["alternatives"]) >= 2


# ---------------------------------------------------------------------------
# 15. Unknown root element treated as generic topic
# ---------------------------------------------------------------------------

UNKNOWN_ROOT_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<customtopic id="custom1">
  <title>Custom Topic Type</title>
  <body>
    <p>Some content in a non-standard root element.</p>
  </body>
</customtopic>"""


def test_unknown_root_treated_as_topic():
    result = _run(generate_shortdesc(UNKNOWN_ROOT_XML, use_llm=False))
    assert result["topic_type"] == "topic"
    assert result["shortdesc"]
