"""Generate Behave-oriented scenarios with AEM Guides terminology."""

from __future__ import annotations

import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available


class BehaveScenarioGenerator:
    async def generate(self, *, jira_blob: str, jira_key: str | None, intent: str) -> str:
        jk = jira_key or "GUIDES-XXX"
        if is_llm_available() and len((jira_blob or "").strip()) > 40:
            system = (
                "Write enterprise Behave Gherkin for Adobe Experience Manager Guides. "
                "Output ONLY Gherkin text: Feature, optional Background, 1-2 Scenarios with Tags lines. "
                "Use realistic tags like @web_editor @baseline @publishing @regression @new_editor @ditaval. "
                "Include DITA map/topic, save/reopen, metadata, publish/preset, conref/keyref where relevant."
            )
            user = f"ticket: {jk}\nintent:{intent}\ncontext:\n{jira_blob[:6000]}"
            try:
                text = await generate_text(system, user, max_tokens=1200, step_name="enterprise_behave_gen")
                return text.strip()
            except Exception:
                pass
        return self._fallback(jk, jira_blob)

    def _fallback(self, jk: str, jira_blob: str) -> str:
        theme = "authoring regression"
        if "publish" in (jira_blob or "").lower():
            theme = "publishing output"
        if "baseline" in (jira_blob or "").lower():
            theme = "baseline compare"
        return f"""Feature: AEM Guides QA — {jk} ({theme})
  @regression @web_editor @aem_guides
  Background:
    Given a test user is logged into AEM
    And a DITA map "qa-map-{jk.lower()}" exists with at least one topic

  Scenario: Save and reopen preserves metadata and references
    Given the Web Editor is open on topic "qa-map-{jk.lower()}/topics/intro.dita"
    When the author edits dc:title and saves the topic
    And the author closes and reopens the topic
    Then the dc:title value should match the saved value
    And conref/keyref targets should still resolve in preview

  Scenario: Publish path sanity
    When the author triggers publish using the assigned output preset
    Then PDF or Sites output should complete without server 500 errors
    And logs should show no XML validation failures for referenced content
"""


class APIFlowReasoningEngine:
    def analyze(self, jira_blob: str) -> dict[str, Any]:
        t = (jira_blob or "").lower()
        flow: list[str] = []
        suspects: list[str] = []
        logs: list[str] = ["author.log", "error.log", "Dispatcher / reverse proxy access logs if publish"]
        validation_pts: list[str] = []

        if any(x in t for x in ("save", "reference", "keyref", "conref", "xref")):
            flow.append("Authoring save → reference listener / validation hooks → persistence")
            validation_pts.append("POST save payload + subsequent GET topic XML equality")
            suspects.append("Reference listener rejecting malformed ranges or stale UUIDs")
        if any(x in t for x in ("publish", "pdf", "sites", "output")):
            flow.append("Publish job → DITA-OT / Cloud pipeline → delivery")
            validation_pts.append("Publish report + output artifact checksum vs golden (sample)")
            suspects.append("Filter/DITAVAL dropping content silently")
        if "validatexml" in t or "/validate" in t:
            flow.append("validatexml endpoint or validation servlet")
            validation_pts.append("Structured error list matches UI")

        if not flow:
            flow = [
                "Typical: Web Editor UI → REST save → JCR/Oak persistence",
                "Optional: /referencelistener-style resolution on preview/publish",
            ]

        return {
            "expected_api_flow": flow[:8],
            "validation_points": validation_pts[:10] or ["HAR capture of save/publish XHR", "GUIDES debug bundles when enabled"],
            "suspected_failure_areas": suspects[:8] or ["Session expiry", "Permission-denied on /content/dam paths"],
            "recommended_logs": logs[:6],
        }
