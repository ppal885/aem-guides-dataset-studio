"""Correlate Jira text with CI/automation signals (Allure/Jenkins payloads when provided)."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any


class FailureIntelligenceEngine:
    def analyze(self, jira_blob: str, enterprise_context: dict[str, Any]) -> dict[str, Any]:
        jb = (jira_blob or "").lower()
        allure = enterprise_context.get("allure") if isinstance(enterprise_context, dict) else {}
        jenkins = enterprise_context.get("jenkins") if isinstance(enterprise_context, dict) else {}
        if not isinstance(allure, dict):
            allure = {}
        if not isinstance(jenkins, dict):
            jenkins = {}

        failed_tests: list[str] = []
        for x in allure.get("failed_tests") or []:
            if x:
                failed_tests.append(str(x))
        for x in jenkins.get("failed_tests") or []:
            if x:
                failed_tests.append(str(x))

        related_failures: list[dict[str, Any]] = []
        for name in failed_tests[:20]:
            score = 0.0
            toks = set(re.findall(r"[a-z0-9]{4,}", name.lower()))
            jtoks = set(re.findall(r"[a-z0-9]{4,}", jb))
            if toks & jtoks:
                score = min(1.0, 0.35 + 0.1 * len(toks & jtoks))
            if score > 0.2:
                related_failures.append({"test": name, "correlation": round(score, 3)})

        stack_hints = []
        for key in ("stack_excerpts", "log_excerpts"):
            for blob in allure.get(key) or jenkins.get(key) or []:
                if isinstance(blob, str) and blob.strip():
                    stack_hints.append(blob[:500])

        clusters: dict[str, list[str]] = {}
        for name in failed_tests:
            prefix = name.split(":")[0].split(".")[0][:40] or "unknown"
            clusters.setdefault(prefix, []).append(name)

        failure_clusters = [
            {"signature": k, "count": len(v), "examples": v[:5]} for k, v in sorted(clusters.items(), key=lambda x: -len(x[1]))[:8]
        ]

        hist = Counter()
        for line in stack_hints:
            if "assert" in line.lower():
                hist["assertion_mismatch"] += 1
            if "timeout" in line.lower():
                hist["timing"] += 1
            if "stale" in line.lower() or "not found" in line.lower():
                hist["locator"] += 1
            if "500" in line or "api" in line.lower():
                hist["api_backend"] += 1

        historical_patterns = [f"{k}: {v}" for k, v in hist.most_common(5)]

        suites = set()
        for name in failed_tests:
            if "/" in name:
                suites.add(name.split("/")[0])
            elif "." in name:
                suites.add(name.split(".")[0])
        for s in list(suites)[:12]:
            if any(t in jb for t in re.findall(r"[a-z0-9_]{4,}", s.lower())):
                pass

        flaky = "Unknown without Allure history JSON; request `allure.history_excerpt` or `failed_tests`."
        if allure.get("flaky_candidates"):
            flaky = "Flaky candidates supplied in context; treat reruns and environment variance carefully."
        elif len(failed_tests) >= 4:
            flaky = "Multiple failing tests; check for shared environment or ordering flakiness."

        likely_suites = sorted(suites)[:15] or ["authoring_regression", "publish_smoke", "api_contracts"]

        repeated = []
        c = Counter(failed_tests)
        for name, n in c.items():
            if n > 1:
                repeated.append(f"{name} (x{n})")

        return {
            "related_failures": related_failures[:15],
            "historical_patterns": historical_patterns,
            "likely_affected_suites": likely_suites,
            "flaky_risk": flaky,
            "repeated_failure_signals": repeated[:10] or ["none_detected_without_history"],
            "failure_clusters": failure_clusters,
        }
