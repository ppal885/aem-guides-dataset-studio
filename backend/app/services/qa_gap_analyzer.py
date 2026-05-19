"""Gap analysis for Jira tickets (rules + optional LLM augmentation)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_service import generate_text, is_llm_available

_Gap = dict[str, Any]


def analyze_gaps_rule_based(context_blob: str, jira_key: str | None) -> list[_Gap]:
    text = (context_blob or "").lower()
    gaps: list[_Gap] = []

    if "acceptance criteria" not in text and "acceptance" not in text:
        gaps.append(
            {
                "type": "missing_acceptance_criteria",
                "description": "No explicit acceptance criteria found in indexed ticket text.",
                "impact": "high",
                "question_to_ask": "What are the measurable acceptance criteria for this fix?",
            }
        )
    if not re.search(r"\bexpected\b|\bshould\b|\bmust\b", text):
        gaps.append(
            {
                "type": "missing_expected_behavior",
                "description": "Expected behavior is vague or absent.",
                "impact": "high",
                "question_to_ask": "What exact UI/API output should we see after the fix?",
            }
        )
    if not re.search(r"\benvironment\b|\bversion\b|\bguides\b|\baem\b|\bchrome\b|\beditor\b", text):
        gaps.append(
            {
                "type": "missing_environment",
                "description": "Environment / version / editor context not explicit.",
                "impact": "medium",
                "question_to_ask": "Which Guides + AEM versions and browsers must we validate?",
            }
        )
    if "negative" not in text and "error" not in text and "invalid" not in text:
        gaps.append(
            {
                "type": "missing_negative_scenarios",
                "description": "Few or no explicit negative / error-path scenarios.",
                "impact": "medium",
                "question_to_ask": "What invalid inputs, permissions, or failure modes should QA cover?",
            }
        )
    if not re.search(r"\btest data\b|\bsample\b|\bmap\b|\btopic\b|\bfixture\b", text):
        gaps.append(
            {
                "type": "unclear_data_setup",
                "description": "Test data / corpus references are thin.",
                "impact": "medium",
                "question_to_ask": "Which DITA maps/topics should QA use and can we get a frozen copy?",
            }
        )
    if "validation" not in text and "verify" not in text and "assert" not in text:
        gaps.append(
            {
                "type": "missing_validation_points",
                "description": "Limited explicit validation checkpoints (UI/API/output).",
                "impact": "low",
                "question_to_ask": "Where should we assert state: DOM, logs, published PDF, or API response?",
            }
        )
    return gaps[:12]


class QAGapAnalyzer:
    async def analyze(
        self,
        context_blob: str,
        *,
        jira_key: str | None = None,
        customer_context: str | None = None,
        label_context: str | None = None,
    ) -> dict[str, Any]:
        gaps = analyze_gaps_rule_based(context_blob, jira_key)
        if is_llm_available() and len(context_blob) > 200:
            try:
                system = (
                    "Find QA/UAC gaps in the Jira evidence. Reply JSON only: "
                    '{"gaps":[{"type":"short_snake","description":"...","impact":"high|medium|low",'
                    '"question_to_ask":"..."}]} Max 5 NEW gaps not already covered by rules. '
                    "If none, return {\"gaps\":[]}."
                )
                cc = (customer_context or "").strip()
                lc = (label_context or "").strip()
                tail_parts: list[str] = []
                if cc:
                    tail_parts.append(f"### Customer intelligence\n{cc[:3500]}")
                if lc:
                    tail_parts.append(f"### Label intelligence\n{lc[:3500]}")
                tail = ("\n\n" + "\n\n".join(tail_parts)) if tail_parts else ""
                raw = await generate_text(
                    system,
                    f"jira: {jira_key or 'n/a'}\n\nEVIDENCE:\n{context_blob[:9000]}{tail}",
                    max_tokens=500,
                    step_name="jira_copilot_gap_llm",
                )
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                data = json.loads(raw)
                extra = data.get("gaps") if isinstance(data, dict) else []
                seen = {g["type"] for g in gaps}
                for g in extra:
                    if not isinstance(g, dict):
                        continue
                    t = str(g.get("type") or "").strip()
                    if t and t not in seen:
                        seen.add(t)
                        gaps.append(
                            {
                                "type": t,
                                "description": str(g.get("description") or "")[:500],
                                "impact": str(g.get("impact") or "medium"),
                                "question_to_ask": str(g.get("question_to_ask") or "")[:300],
                            }
                        )
            except Exception:
                pass
        return {"gaps": gaps}
