"""Tests for the Style Guide Enforcer service and rules engine."""

import pytest

from app.services.style_rules_engine import (
    check_banned_terms,
    check_future_tense,
    check_passive_voice,
    check_pronoun_ambiguity,
    check_sentence_length,
    evaluate,
)
from app.services.style_guide_enforcer_service import enforce


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CLEAN_TOPIC = """\
<topic id="clean">
  <title>Configure the proxy settings</title>
  <shortdesc>Set up proxy settings for outbound connections.</shortdesc>
  <body>
    <p>Open the configuration file.</p>
    <steps>
      <step><cmd>Click Settings.</cmd></step>
      <step><cmd>Select the Proxy tab.</cmd></step>
      <step><cmd>Enter the proxy address.</cmd></step>
    </steps>
  </body>
</topic>
"""

DIRTY_TOPIC = """\
<topic id="dirty">
  <title>How To Configure The Proxy Settings For Your Organisation</title>
  <shortdesc>This is a short description that is way too long because it contains too many words and keeps going on and on and on and on and on and on and on and on and on and on and on and on and on.</shortdesc>
  <body>
    <p>The configuration file is opened by the administrator when the system was installed and deployed to the production environment by the operations team in order to set up the proxy that will be used.</p>
    <ul>
      <li>Item without intro</li>
    </ul>
    <steps>
      <step><cmd>The button should be clicked.</cmd></step>
    </steps>
    <p>It is important. This enables the feature. They should know.</p>
  </body>
</topic>
"""


# ---------------------------------------------------------------------------
# 1. Sentence length violation detection
# ---------------------------------------------------------------------------

class TestSentenceLength:
    def test_long_sentence_flagged(self):
        text = "This is a really long sentence that has way more than twenty five words in it because it keeps on going and going and going without stopping."
        violations = check_sentence_length(text, {"max_words": 25, "severity": "warning"})
        assert len(violations) >= 1
        assert violations[0]["rule_id"] == "sentence_length"

    def test_short_sentence_passes(self):
        text = "Open the file."
        violations = check_sentence_length(text, {"max_words": 25, "severity": "warning"})
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 2. Passive voice detection
# ---------------------------------------------------------------------------

class TestPassiveVoice:
    def test_passive_detected(self):
        text = "The file was opened by the user."
        violations = check_passive_voice(text, {"severity": "warning"})
        assert len(violations) >= 1
        assert violations[0]["rule_id"] == "passive_voice"

    def test_active_voice_passes(self):
        text = "The user opens the file."
        violations = check_passive_voice(text, {"severity": "warning"})
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 3. Banned term detection
# ---------------------------------------------------------------------------

class TestBannedTerms:
    def test_click_on_flagged(self):
        text = "Click on the button to proceed."
        violations = check_banned_terms(text, {"severity": "warning", "terms": {"click on": "click"}})
        assert len(violations) == 1
        assert "click on" in violations[0]["message"].lower()
        assert "click" in violations[0]["suggestion"].lower()

    def test_in_order_to_flagged(self):
        text = "Do this in order to complete the task."
        violations = check_banned_terms(text, {"severity": "warning", "terms": {"in order to": "to"}})
        assert len(violations) == 1

    def test_clean_text_passes(self):
        text = "Click the button to proceed."
        violations = check_banned_terms(text, {"severity": "warning", "terms": {"click on": "click"}})
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 4. Step imperative check (cmd element)
# ---------------------------------------------------------------------------

class TestStepImperative:
    def test_non_imperative_flagged(self):
        xml = '<topic id="t"><body><steps><step><cmd>The button should be clicked.</cmd></step></steps></body></topic>'
        result = evaluate(xml)
        step_violations = [v for v in result["violations"] if v["rule_id"] == "step_imperative"]
        assert len(step_violations) >= 1

    def test_imperative_passes(self):
        xml = '<topic id="t"><body><steps><step><cmd>Click the button.</cmd></step></steps></body></topic>'
        result = evaluate(xml)
        step_violations = [v for v in result["violations"] if v["rule_id"] == "step_imperative"]
        assert len(step_violations) == 0


# ---------------------------------------------------------------------------
# 5. Shortdesc length check
# ---------------------------------------------------------------------------

class TestShortdescLength:
    def test_long_shortdesc_flagged(self):
        words = " ".join(["word"] * 55)
        xml = f'<topic id="t"><shortdesc>{words}</shortdesc><body/></topic>'
        result = evaluate(xml)
        sd_violations = [v for v in result["violations"] if v["rule_id"] == "shortdesc_length"]
        assert len(sd_violations) >= 1

    def test_short_shortdesc_passes(self):
        xml = '<topic id="t"><shortdesc>A brief description.</shortdesc><body/></topic>'
        result = evaluate(xml)
        sd_violations = [v for v in result["violations"] if v["rule_id"] == "shortdesc_length"]
        assert len(sd_violations) == 0


# ---------------------------------------------------------------------------
# 6. Clean content passes all rules
# ---------------------------------------------------------------------------

class TestCleanContent:
    def test_clean_topic_high_score(self):
        report = enforce(CLEAN_TOPIC)
        assert report["score"] >= 90
        assert report["grade"] == "A"


# ---------------------------------------------------------------------------
# 7. Score calculation
# ---------------------------------------------------------------------------

class TestScoreCalculation:
    def test_perfect_score(self):
        xml = '<topic id="t"><title>Configure settings</title><shortdesc>Set up settings.</shortdesc><body><p>Open the file.</p></body></topic>'
        report = enforce(xml)
        assert report["score"] >= 90

    def test_violations_lower_score(self):
        report = enforce(DIRTY_TOPIC)
        assert report["score"] < 90


# ---------------------------------------------------------------------------
# 8. Grade assignment
# ---------------------------------------------------------------------------

class TestGradeAssignment:
    def test_a_grade(self):
        report = enforce(CLEAN_TOPIC)
        assert report["grade"] == "A"

    def test_lower_grade_for_dirty(self):
        report = enforce(DIRTY_TOPIC)
        assert report["grade"] in ("B", "C", "D", "F")


# ---------------------------------------------------------------------------
# 9. Custom rules config
# ---------------------------------------------------------------------------

class TestCustomConfig:
    def test_disable_rule(self):
        config = {"passive_voice": {"enabled": False}}
        xml = '<topic id="t"><body><p>The file was opened by the user.</p></body></topic>'
        result = evaluate(xml, config)
        passive_violations = [v for v in result["violations"] if v["rule_id"] == "passive_voice"]
        assert len(passive_violations) == 0

    def test_custom_banned_terms(self):
        config = {"banned_terms": {"terms": {"utilize": "use"}}}
        xml = '<topic id="t"><body><p>Utilize the tool.</p></body></topic>'
        result = evaluate(xml, config)
        banned_violations = [v for v in result["violations"] if v["rule_id"] == "banned_terms"]
        assert len(banned_violations) >= 1


# ---------------------------------------------------------------------------
# 10. Multiple violations in one document
# ---------------------------------------------------------------------------

class TestMultipleViolations:
    def test_dirty_topic_has_many_violations(self):
        report = enforce(DIRTY_TOPIC)
        assert len(report["violations"]) >= 3
        rule_ids = {v["rule_id"] for v in report["violations"]}
        assert len(rule_ids) >= 2  # at least 2 different rules triggered


# ---------------------------------------------------------------------------
# 11. Pronoun ambiguity detection
# ---------------------------------------------------------------------------

class TestPronounAmbiguity:
    def test_ambiguous_pronoun_flagged(self):
        text = "Configure the proxy. It is important for connectivity."
        violations = check_pronoun_ambiguity(text, {"severity": "warning"})
        assert len(violations) >= 1
        assert violations[0]["rule_id"] == "pronoun_ambiguity"

    def test_no_pronoun_passes(self):
        text = "Configure the proxy. The proxy enables connectivity."
        violations = check_pronoun_ambiguity(text, {"severity": "warning"})
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 12. Future tense detection
# ---------------------------------------------------------------------------

class TestFutureTense:
    def test_will_flagged(self):
        text = "The system will restart automatically."
        violations = check_future_tense(text, {"severity": "warning"})
        assert len(violations) >= 1
        assert violations[0]["rule_id"] == "future_tense"

    def test_present_tense_passes(self):
        text = "The system restarts automatically."
        violations = check_future_tense(text, {"severity": "warning"})
        assert len(violations) == 0


# ---------------------------------------------------------------------------
# 13. List introduction check
# ---------------------------------------------------------------------------

class TestListIntro:
    def test_list_without_intro_flagged(self):
        xml = '<topic id="t"><body><ul><li>First item</li></ul></body></topic>'
        result = evaluate(xml)
        list_violations = [v for v in result["violations"] if v["rule_id"] == "list_intro"]
        assert len(list_violations) >= 1

    def test_list_with_intro_passes(self):
        xml = '<topic id="t"><body><p>Consider the following items:</p><ul><li>First item</li></ul></body></topic>'
        result = evaluate(xml)
        list_violations = [v for v in result["violations"] if v["rule_id"] == "list_intro"]
        assert len(list_violations) == 0


# ---------------------------------------------------------------------------
# 14. Malformed XML handling
# ---------------------------------------------------------------------------

class TestMalformedXml:
    def test_malformed_xml_does_not_crash(self):
        bad_xml = "<topic><title>Broken</title><body><p>Unclosed paragraph"
        report = enforce(bad_xml)
        assert "score" in report
        assert "violations" in report
        assert isinstance(report["score"], int)

    def test_malformed_xml_runs_text_rules(self):
        bad_xml = "<topic><title>Broken</title><body><p>The file was opened by the user. Click on the button in order to proceed."
        report = enforce(bad_xml)
        # Should still catch text-based violations
        rule_ids = {v["rule_id"] for v in report["violations"]}
        assert len(rule_ids) >= 1


# ---------------------------------------------------------------------------
# 15. Empty content handling
# ---------------------------------------------------------------------------

class TestEmptyContent:
    def test_empty_string(self):
        report = enforce("")
        assert report["score"] == 100
        assert report["grade"] == "A"
        assert report["violations"] == []

    def test_whitespace_only(self):
        report = enforce("   \n  ")
        assert report["score"] == 100
        assert report["grade"] == "A"


# ---------------------------------------------------------------------------
# 16. Report structure
# ---------------------------------------------------------------------------

class TestReportStructure:
    def test_report_has_all_keys(self):
        report = enforce(CLEAN_TOPIC)
        assert "score" in report
        assert "grade" in report
        assert "violations" in report
        assert "summary" in report
        assert "passed_rules" in report
        assert "total_rules" in report
        assert "errors" in report["summary"]
        assert "warnings" in report["summary"]
        assert "info" in report["summary"]

    def test_violations_sorted_by_severity(self):
        report = enforce(DIRTY_TOPIC)
        if len(report["violations"]) >= 2:
            severity_order = {"error": 0, "warning": 1, "info": 2}
            severities = [severity_order[v["severity"]] for v in report["violations"]]
            assert severities == sorted(severities)
