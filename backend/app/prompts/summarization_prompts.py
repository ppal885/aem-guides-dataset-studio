"""Summarization guardrail prompts for QA copilot."""

GROUNDING_RULES = """
Use only retrieved issue keys and evidence snippets for Jira facts. If evidence is empty,
say "No matching grounded historical issues found." Do not fabricate Jira keys, customers,
fix versions, environments, or root causes.
""".strip()

