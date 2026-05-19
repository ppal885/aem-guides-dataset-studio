"""Grounded response composition and hallucination guardrails."""

from __future__ import annotations

from app.models.jira_models import (
    AutomationFit,
    AutomationScenario,
    CommonPattern,
    GroundingReport,
    JiraIssueSearchResult,
    UacPoint,
)
from app.models.tool_models import ExtractedEntities


class ResponseGroundingService:
    """Compose the final answer using only retrieved issue evidence."""

    def compose(
        self,
        *,
        entities: ExtractedEntities,
        issues: list[JiraIssueSearchResult],
        patterns: list[CommonPattern],
        scenarios: list[AutomationScenario],
        uac_points: list[UacPoint],
        automation_fit: AutomationFit | None,
        semantic_fallback_used: bool,
        metadata_filter_used: bool,
    ) -> tuple[str, GroundingReport]:
        issue_keys = [issue.issue_key for issue in issues if issue.issue_key]
        warnings: list[str] = []
        hallucination_guard = False
        if not issues:
            hallucination_guard = True
            warnings.append("No matching grounded historical issues found.")
        if semantic_fallback_used:
            warnings.append("Metadata incomplete. Semantic similarity retrieval used.")

        lines: list[str] = []
        if semantic_fallback_used:
            lines.append("Metadata incomplete. Semantic similarity retrieval used.")
            lines.append("")
        if not issues:
            lines.append("No matching grounded historical issues found.")
            lines.append("")

        lines.append("## 1. Historical Matching Issues")
        if issues:
            for issue in issues:
                lines.extend(
                    [
                        f"- Jira Key: {issue.issue_key}",
                        f"  Summary: {issue.summary or 'Not stated in indexed data.'}",
                        f"  Customer: {issue.customer or 'Not stated in indexed metadata.'}",
                        f"  Feature: {issue.feature or entities.feature or 'Not stated.'}",
                        f"  Environment: {issue.environment or 'Not stated in indexed metadata.'}",
                        f"  Why Relevant: {issue.why_relevant or 'Matched by retrieval signals.'}",
                        f"  Root Cause Summary: {issue.root_cause_summary or 'Not stated in retrieved evidence.'}",
                    ]
                )
        else:
            lines.append("- No Jira issue rows were retrieved, so no Jira keys are listed.")

        lines.append("")
        lines.append("## 2. Common Historical Patterns")
        if patterns:
            for pattern in patterns:
                roots = "; ".join(pattern.probable_root_causes[:3]) or "Not stated in retrieved evidence."
                keys = ", ".join(pattern.supporting_issues)
                modules = ", ".join(pattern.impacted_modules) or "Not stated"
                lines.append(
                    f"- {pattern.pattern}: frequency {pattern.frequency}, risk {pattern.regression_risk}, "
                    f"modules {modules}, supporting issues {keys}. Root cause signals: {roots}"
                )
        else:
            lines.append("- No repeated grounded pattern could be established from retrieved issues.")

        lines.append("")
        lines.append("## 3. Automation Scenarios")
        if scenarios:
            for scenario in scenarios:
                lines.append(f"### {scenario.title}")
                lines.append(scenario.scenario_text.rstrip())
        else:
            lines.append("No grounded automation scenarios generated because retrieved Jira evidence was insufficient.")

        lines.append("")
        lines.append("## 4. QA/UAC Discussion Points")
        if uac_points:
            for point in uac_points:
                keys = ", ".join(point.grounded_in) or "retrieved evidence"
                lines.append(f"- {point.category}: {point.point} (risk: {point.risk_level}; grounded in {keys})")
        else:
            lines.append("- No grounded UAC points were generated from historical Jira evidence.")

        lines.append("")
        lines.append("## 5. Automation Fit Analysis")
        if automation_fit:
            lines.extend(
                [
                    f"- Automation recommended: {'Yes' if automation_fit.automation_recommended else 'No/Partial'}",
                    f"- Priority: {automation_fit.priority}",
                    f"- Framework: {automation_fit.framework}",
                    f"- Complexity: {automation_fit.complexity}",
                    f"- Score: {automation_fit.score_0_10}/10",
                    f"- Dependencies: {', '.join(automation_fit.dependencies) or 'Not stated'}",
                    f"- Required test data: {', '.join(automation_fit.required_test_data) or 'Not stated'}",
                    f"- Rationale: {automation_fit.rationale}",
                ]
            )
        else:
            lines.append("- Automation fit could not be scored without grounded issue evidence.")

        return "\n".join(lines).strip(), GroundingReport(
            grounded_issue_keys=issue_keys,
            semantic_fallback_used=semantic_fallback_used,
            metadata_filter_used=metadata_filter_used,
            warnings=warnings,
            hallucination_prevention_triggered=hallucination_guard,
        )

