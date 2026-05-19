"""Parse optional Allure-shaped payloads (categories, failed tests, Behave excerpts)."""

from __future__ import annotations

import json
import re
from typing import Any


class AllureAnalysisService:
    def analyze(self, enterprise_context: dict[str, Any]) -> dict[str, Any]:
        allure = enterprise_context.get("allure") if isinstance(enterprise_context, dict) else {}
        if not isinstance(allure, dict):
            allure = {}

        failed = [str(x) for x in (allure.get("failed_tests") or []) if x]
        flaky = [str(x) for x in (allure.get("flaky_candidates") or []) if x]
        categories_raw = allure.get("categories_json") or allure.get("categories")
        cat_hints: list[str] = []
        if isinstance(categories_raw, str) and categories_raw.strip():
            try:
                data = json.loads(categories_raw)
                if isinstance(data, list):
                    for c in data[:20]:
                        if isinstance(c, dict) and c.get("name"):
                            cat_hints.append(str(c["name"]))
                        elif isinstance(c, str):
                            cat_hints.append(c)
            except json.JSONDecodeError:
                for m in re.findall(r'"name"\s*:\s*"([^"]+)"', categories_raw):
                    cat_hints.append(m)

        component_dist: dict[str, int] = {}
        for name in failed:
            head = name.split("/")[0].split(".")[0] if name else "unknown"
            component_dist[head] = component_dist.get(head, 0) + 1

        api_patterns: list[str] = []
        step_blob = "\n".join(str(x) for x in (allure.get("failed_steps") or []) if x).lower()
        if "api" in step_blob or "http" in step_blob or "rest" in step_blob:
            api_patterns.append("HTTP/API assertions in failing steps")

        env_failures: list[str] = []
        if "agent" in step_blob or "grid" in step_blob or "browser" in step_blob:
            env_failures.append("Possible grid/browser instability")

        failure_summary = {
            "failed_test_count": len(failed),
            "flaky_candidate_count": len(flaky),
            "category_names_sample": cat_hints[:8],
        }

        recommendations: list[str] = []
        if failed:
            recommendations.append("Stabilize top component failures before expanding scope.")
        if flaky:
            recommendations.append("Quarantine or retry-wrapper flaky specs; inspect timing locators.")
        if not failed and not flaky:
            recommendations.append("Provide Allure `failed_tests` or `history_excerpt` for deeper correlation.")

        return {
            "failure_summary": failure_summary,
            "top_flaky_tests": flaky[:12],
            "top_failed_steps": [str(x) for x in (allure.get("failed_steps") or [])[:12]],
            "component_failure_distribution": dict(sorted(component_dist.items(), key=lambda x: -x[1])[:15]),
            "api_failure_patterns": api_patterns,
            "environmental_failures": env_failures,
            "recommended_actions": recommendations[:8],
        }
