"""Automation generation guidance for AEM Guides QA copilot."""

BEHAVE_GUIDANCE = """
Generate Behave scenarios only from retrieved Jira evidence. Prefer stable fixtures,
observable assertions, publishing/output checks, save-reopen validation, and negative cases.
If no issue evidence exists, return no scenarios.
""".strip()

