"""Customer-centric correlation when customer field or ticket text mentions accounts."""

from __future__ import annotations

from typing import Any

_KNOWN = ("cisco", "adobe", "internal", "nvidia", "oracle")


class CustomerIntelligenceEngine:
    def analyze(self, *, customer: str | None, jira_blob: str, related_titles: list[str]) -> dict[str, Any]:
        jb = (jira_blob or "").lower()
        cust = (customer or "").strip().lower()
        patterns: list[str] = []
        repeated: list[str] = []
        high_risk: list[str] = []

        for name in _KNOWN:
            if name in jb or name in cust:
                patterns.append(f"Anchored to customer signal: {name}")

        for title in related_titles[:15]:
            tl = title.lower()
            if cust and len(cust) > 2 and cust in tl:
                repeated.append(f"Related ticket title mentions customer context: {title[:120]}")

        if "production" in jb and cust:
            high_risk.append("Production-impacting issue with named customer — expand UAC sign-off")

        if not patterns:
            patterns.append("No explicit enterprise customer fingerprint; use indexed labels if present.")

        return {
            "customer_patterns": patterns[:8],
            "repeated_customer_issues": repeated[:8],
            "high_risk_customer_areas": high_risk[:6],
        }
