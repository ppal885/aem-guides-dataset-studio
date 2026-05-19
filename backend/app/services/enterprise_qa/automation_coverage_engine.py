"""Heuristic automation coverage vs Jira area (extend with Chroma enterprise_qa index)."""

from __future__ import annotations

import re
from typing import Any


class AutomationCoverageEngine:
    def analyze(self, jira_blob: str, enterprise_context: dict[str, Any]) -> dict[str, Any]:
        auto = enterprise_context.get("automation") if isinstance(enterprise_context, dict) else {}
        if not isinstance(auto, dict):
            auto = {}

        features = [str(x) for x in (auto.get("feature_excerpts") or []) if str(x).strip()]
        tags = [str(x) for x in (auto.get("tags") or []) if str(x).strip()]
        test_names = [str(x) for x in (auto.get("allure_test_names") or []) if str(x).strip()]

        jb = (jira_blob or "").lower()
        keywords = set(re.findall(r"[a-z]{4,}", jb))
        matching_features: list[str] = []
        matching_tags: list[str] = []

        for excerpt in features[:40]:
            etoks = set(re.findall(r"[a-z]{4,}", excerpt.lower()))
            if keywords & etoks:
                matching_features.append(excerpt[:200])

        for tag in tags:
            tl = tag.lower().lstrip("@")
            if tl in jb or any(k in tl for k in keywords if len(k) > 4):
                matching_tags.append(tag)

        score = 20
        if matching_features:
            score += min(40, 10 * len(matching_features[:4]))
        if matching_tags:
            score += min(25, 5 * len(matching_tags[:5]))
        if test_names and any(n.lower() in jb for n in test_names[:30]):
            score += 15
        score = min(100, score)

        gaps: list[str] = []
        if score < 50:
            gaps.append("No strong Behave/feature overlap detected; plan new scenarios or index automation repo into enterprise_qa collection.")
        if "baseline" in jb and not any("baseline" in f.lower() for f in matching_features):
            gaps.append("Baseline workflows may lack automated coverage")
        if "publish" in jb and not any("publish" in f.lower() for f in matching_features):
            gaps.append("Publishing path coverage unclear from excerpts")

        rec = []
        if "web editor" in jb or "editor" in jb:
            rec.append("@web_editor scenario covering save/reopen + metadata assertion")
        if "keyref" in jb or "conref" in jb:
            rec.append("@references map with keydef + conref range validation")

        return {
            "automation_exists": score >= 55,
            "matching_features": matching_features[:10],
            "matching_tags": list(dict.fromkeys(matching_tags))[:12],
            "coverage_score": score,
            "gaps": gaps[:8],
            "recommended_new_tests": rec[:8],
        }
