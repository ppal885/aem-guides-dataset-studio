"""Tests for domain shallow semantic rules (valid XML, weak DITA structure)."""
import re

from app.core.schemas_dita_pipeline import GenerationPlan, IntentRecord
from app.services.dita_shallow_semantic_rules import evaluate_domain_shallow_rules


def _counts(xml: str) -> dict[str, int]:
    from app.services.semantic_dita_validator import _count_elements

    body = re.sub(r"<\?xml[^?]*\?>", "", xml, flags=re.I)
    body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.I)
    return _count_elements(body)


def test_task_without_steps_is_shallow():
    xml = (
        '<task id="t"><title>Do</title><taskbody>'
        "<context><p>Just narrative.</p></context></taskbody></task>"
    )
    c = _counts(xml)
    plan = GenerationPlan(recipe_id="x", topic_type="task")
    v = evaluate_domain_shallow_rules(xml, xml.lower(), c, plan, None, domains={"task"})
    ids = {x.rule_id for x in v}
    assert "shallow.task_no_steps" in ids


def test_map_without_topicref_is_shallow():
    xml = '<map id="m"><title>Only</title></map>'
    c = _counts(xml)
    plan = GenerationPlan(recipe_id="x", topic_type="topic")
    v = evaluate_domain_shallow_rules(xml, xml.lower(), c, plan, None, domains={"map"})
    assert any(x.rule_id == "shallow.map_no_navigation" for x in v)


def test_table_alignment_prose_only():
    xml = (
        "<topic id=\"t\"><title>Align</title><body>"
        "<p>Values: left, right, center, justify, char for table text alignment in cells.</p>"
        "<ul><li>left</li><li>right</li></ul></body></topic>"
    )
    c = _counts(xml)
    plan = GenerationPlan(recipe_id="x", topic_type="topic")
    intent = IntentRecord(anti_fallback_signals=["table_alignment"])
    v = evaluate_domain_shallow_rules(xml, xml.lower(), c, plan, intent, domains={"table_alignment"})
    assert any(x.rule_id == "shallow.table_alignment_prose_only" for x in v)


def test_glossentry_without_glossdef():
    xml = (
        '<glossentry id="g"><glossterm>Term</glossterm></glossentry>'
    )
    c = _counts(xml)
    plan = GenerationPlan(recipe_id="x", topic_type="topic")
    v = evaluate_domain_shallow_rules(xml, xml.lower(), c, plan, None, domains={"glossary"})
    assert any(x.rule_id == "shallow.glossentry_missing_glossdef" for x in v)


def test_subjectscheme_without_defs():
    xml = '<map><subjectScheme id="s"><title>Schemes</title></subjectScheme></map>'
    c = _counts(xml)
    plan = GenerationPlan(recipe_id="x", topic_type="topic")
    v = evaluate_domain_shallow_rules(xml, xml.lower(), c, plan, None, domains={"subject_scheme"})
    assert any(x.rule_id == "shallow.subjectscheme_no_definitions" for x in v)
