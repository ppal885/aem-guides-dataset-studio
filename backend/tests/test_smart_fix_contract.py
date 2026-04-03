import asyncio

from app.services.smart_suggestions_service import apply_fix_with_review, fix_all_safe, is_safe_rule


def test_safe_rule_classifier_is_explicit():
    assert is_safe_rule("validation_xml_lang")
    assert is_safe_rule("reuse_add_keyref")
    assert not is_safe_rule("bug_report_language")
    assert not is_safe_rule("vague_steps")


def test_apply_fix_with_review_returns_change_metadata():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">
<concept id="circleci_job">
  <title>CircleCI accessibility overview</title>
  <conbody>
    <p>Details.</p>
  </conbody>
</concept>"""

    result = asyncio.run(
        apply_fix_with_review(
            xml=xml,
            suggestion={
                "rule_id": "missing_shortdesc",
                "title": "Missing shortdesc",
                "after": "Describe the successful outcome of the topic.",
            },
            issue={"issue_key": "AUTH-55"},
            tenant_id="kone",
            allow_llm=False,
        )
    )

    assert result["changed"] is True
    assert result["applied_rule_id"] == "missing_shortdesc"
    assert result["changed_ranges"]
    assert result["updated_review"]["quality_score"] >= 0
    assert "shortdesc" in result["xml"]
    assert isinstance(result["suggestions_report"]["suggestions"], list)


def test_fix_all_safe_does_not_apply_editorial_rewrites():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE concept PUBLIC "-//OASIS//DTD DITA Concept//EN" "technicalContent/dtd/concept.dtd">
<concept id="circleci_job">
  <title>Add 2nd-gen a11y test job to CircleCI</title>
  <shortdesc>This topic describes the bug.</shortdesc>
  <conbody>
    <p>Expected result: the job works.</p>
  </conbody>
</concept>"""

    result = asyncio.run(
        fix_all_safe(
            xml=xml,
            issue={
                "issue_key": "AUTH-44",
                "summary": "Add 2nd-gen a11y test job to CircleCI",
                "description": "Document the second-generation accessibility job in CircleCI for AEM Guides.",
                "issue_type": "Story",
            },
            tenant_id="kone",
        )
    )

    assert result["fixed_count"] >= 1
    assert "bug_report_language" not in result["applied_rule_ids"]
    assert any(rule_id in result["applied_rule_ids"] for rule_id in {"validation_xml_lang", "reuse_title_conref"})
