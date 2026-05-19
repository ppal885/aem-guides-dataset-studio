"""QA persona mode normalization and labels."""

from __future__ import annotations

from app.services.qa_persona_modes import (
    build_persona_copilot_section,
    normalize_persona_mode,
    persona_label,
)


def test_normalize_defaults_and_display_forms():
    assert normalize_persona_mode(None) == "senior_qa"
    assert normalize_persona_mode("") == "senior_qa"
    assert normalize_persona_mode("  Automation Architect ") == "automation_architect"
    assert normalize_persona_mode("release_qa") == "release_qa"
    assert normalize_persona_mode("Customer Escalation QA") == "customer_escalation_qa"


def test_persona_label_round_trip():
    assert persona_label("performance_qa") == "Performance QA"


def test_copilot_section_non_empty():
    assert "Automation Architect" in build_persona_copilot_section("automation_architect")
