"""Risk-based suite and test recommendations from Jira + failure intel."""

from __future__ import annotations

from typing import Any


class TestImpactAnalysisEngine:
    def analyze(
        self,
        *,
        jira_blob: str,
        labels: list[str],
        components: list[str],
        failure_intel: dict[str, Any],
        test_strategy: dict[str, Any],
    ) -> dict[str, Any]:
        t = (jira_blob or "").lower()
        suites = list(dict.fromkeys((failure_intel.get("likely_affected_suites") or [])[:20]))
        if not suites:
            suites = ["web_editor_smoke", "publish_pipeline", "api_sanity"]

        feat = []
        for area in ("publish", "pdf", "editor", "baseline", "conref", "keyref", "ditaval", "asset"):
            if area in t:
                feat.append(f"aem_guides_{area}")

        high_pri = []
        if "blocker" in t or "production" in t:
            high_pri.append("End-to-end publish + reopen for customer corpus")
        if "api" in t or "/api/" in t:
            high_pri.append("Contract tests for affected REST endpoints")
        if not high_pri:
            high_pri.append("Smoke authoring path + one negative permissions case")

        rerun = [x.get("test") for x in (failure_intel.get("related_failures") or []) if isinstance(x, dict) and x.get("test")]
        rerun = [str(x) for x in rerun if x][:15]

        skip = ["Cosmetic UI-only areas with no shared components (confirm with dev)"]
        if "documentation" in t:
            skip.append("Pure doc-only changes if no code path touched")

        order = ["Stability: API → integration → UI"] + suites[:5]
        ts_api = test_strategy.get("test_layers", {}).get("api") if isinstance(test_strategy, dict) else []
        if isinstance(ts_api, list) and ts_api:
            order = [str(x) for x in ts_api[:3]] + order

        return {
            "recommended_suites": suites[:12],
            "recommended_features": feat[:12] or components[:8],
            "high_priority_tests": high_pri[:8],
            "tests_to_rerun": rerun,
            "safe_to_skip": skip[:5],
            "risk_based_order": order[:12],
        }
