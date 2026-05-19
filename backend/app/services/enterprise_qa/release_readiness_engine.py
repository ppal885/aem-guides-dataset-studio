"""Aggregate release risk over multiple Jira keys + automation gaps."""

from __future__ import annotations

from typing import Any


class ReleaseReadinessEngine:
    def analyze(
        self,
        *,
        release_ticket_keys: list[str],
        coverage: dict[str, Any],
        risk_level: str,
        failure_intel: dict[str, Any],
    ) -> dict[str, Any]:
        keys = [str(k).strip().upper() for k in release_ticket_keys if str(k).strip()]
        weak: list[str] = []
        if (coverage.get("coverage_score") or 0) < 50:
            weak.append("Automation coverage score low vs described areas")

        fi = failure_intel.get("failure_clusters") or []
        if isinstance(fi, list) and len(fi) >= 3:
            weak.append("Multiple failure clusters detected in CI payloads")

        manual_focus = [
            "Cross-editor parity (classic vs web) if maps touched",
            "Publishing parity (PDF + Sites) for customer-visible templates",
        ]
        if risk_level == "high":
            manual_focus.insert(0, "Full regression smoke on authoring + publish before sign-off")

        rec = [
            "Gate release on top 3 risk themes from Jira + CI correlation",
            "Document explicit out-of-scope areas in UAC",
        ]

        rel_risk = "low"
        if risk_level == "high" or len(keys) > 8:
            rel_risk = "high"
        elif risk_level == "medium" or len(keys) > 3:
            rel_risk = "medium"

        return {
            "release_risk": rel_risk,
            "weak_areas": weak[:10],
            "automation_gaps": (coverage.get("gaps") or [])[:10],
            "manual_focus_areas": manual_focus[:8],
            "recommendations": rec[:8],
        }
