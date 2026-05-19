"""Automation agent facade for QA copilot."""

from __future__ import annotations

from app.tools.automation_tools import generate_automation_scenarios, generate_uac_points


class AutomationAgent:
    generate_automation_scenarios = staticmethod(generate_automation_scenarios)
    generate_uac_points = staticmethod(generate_uac_points)

