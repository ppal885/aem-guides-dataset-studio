"""Enterprise intent classification with confidence and conversation context."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

from app.services.llm_service import generate_text, is_llm_available

# Canonical copilot intents (superset); legacy aliases mapped in classify.
COPILOT_INTENTS = frozenset(
    {
        "ticket_summary",
        "related_tickets",
        "testing_scope",
        "edge_cases",
        "regression_analysis",
        "automation_fit",
        "test_case_generation",
        "gherkin_generation",
        "uac_preparation",
        "gap_analysis",
        "risk_prediction",
        "api_validation",
        "data_setup",
        "debugging_assistance",
        "test_ticket_creation",
        "general_qa_question",
    }
)

_LEGACY_INTENT_MAP = {
    "uac_discussion": "uac_preparation",
}


@dataclass
class IntentClassification:
    intent: str
    confidence: float


def _normalize_intent(raw: str) -> str:
    s = (raw or "").strip()
    return _LEGACY_INTENT_MAP.get(s, s)


def _history_blob(history: list[dict[str, Any]] | None, max_turns: int = 6) -> str:
    if not history:
        return ""
    lines: list[str] = []
    for turn in history[-max_turns:]:
        role = str(turn.get("role") or "").strip()
        content = str(turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content[:800]}")
    return "\n".join(lines)


def classify_intent_rules(message: str, jira_key: str | None) -> tuple[Optional[str], float]:
    """Return (intent, confidence) or (None, 0) if ambiguous."""
    m = (message or "").strip().lower()
    if not m:
        return "general_qa_question", 0.35

    # High-confidence patterns
    if re.search(r"\b(behave|gherkin|given\b|when\b|then\b|feature file)\b", m):
        return "gherkin_generation", 0.92
    if re.search(r"\b(edge case|boundary|corner case)\b", m):
        return "edge_cases", 0.88
    if re.search(r"\b(regression|what broke|impact analysis|blast radius)\b", m):
        return "regression_analysis", 0.86
    if re.search(r"\b(gap|missing acceptance|incomplete spec|what.s missing)\b", m):
        return "gap_analysis", 0.85
    if re.search(r"\b(risk|probability|production risk|how risky)\b", m):
        return "risk_prediction", 0.84
    if re.search(r"\b(api validate|validatexml|referencelistener|rest endpoint)\b", m):
        return "api_validation", 0.82
    if re.search(r"\b(test data|fixture|seed data|data setup)\b", m):
        return "data_setup", 0.82
    if re.search(r"\b(debug|stack trace|repro not|cannot reproduce)\b", m):
        return "debugging_assistance", 0.8
    if re.search(r"\b(test ticket draft|create a test ticket|qa ticket draft)\b", m):
        return "test_ticket_creation", 0.9
    if re.search(r"\b(test case|test cases|generate tests)\b", m):
        return "test_case_generation", 0.88
    if re.search(r"\b(automation fit|automate|can this be automated)\b", m):
        return "automation_fit", 0.87
    if re.search(r"\b(uac|discussion points|raise in uac|acceptance discussion)\b", m):
        return "uac_preparation", 0.88
    if re.search(r"\b(what should (i|we) test|testing scope|qa scope)\b", m):
        return "testing_scope", 0.85
    if re.search(r"\b(related tickets?|similar tickets?)\b", m):
        return "related_tickets", 0.86
    if re.search(r"\b(summary of (this )?ticket|summarize (this )?ticket|ticket summary)\b", m):
        return "ticket_summary", 0.88
    if jira_key and len(m) < 80 and any(x in m for x in ("summary", "summarize", "overview")):
        return "ticket_summary", 0.72
    return None, 0.0


class IntentClassifierService:
    async def classify(
        self,
        message: str,
        *,
        jira_key: Optional[str] = None,
        history: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        intent_hit, conf = classify_intent_rules(message, jira_key)
        hist = _history_blob(history)

        if intent_hit:
            boosted = min(1.0, conf + (0.03 if jira_key else 0) + (0.02 if hist else 0))
            return {"intent": intent_hit, "confidence": round(boosted, 3)}

        if not is_llm_available():
            return {"intent": "general_qa_question", "confidence": 0.45}

        system = (
            "Classify the user's intent for an AEM Guides QA copilot. "
            f'Reply JSON only: {{"intent":"<one>","confidence":0.0-1.0}}\n'
            f"Intents: {', '.join(sorted(COPILOT_INTENTS))}\n"
            "Use conversation summary only for disambiguation. "
            "If unclear, use general_qa_question with confidence 0.35-0.55."
        )
        user = (
            f"jira_key: {jira_key or 'none'}\n"
            f"recent_conversation:\n{hist[:6000]}\n\nlatest_message:\n{(message or '')[:2000]}"
        )
        try:
            raw = await generate_text(system, user, max_tokens=120, step_name="jira_copilot_intent")
            raw = raw.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            intent = _normalize_intent(str(data.get("intent") or "").strip())
            c = float(data.get("confidence") or 0.5)
            c = max(0.0, min(1.0, c))
            if intent not in COPILOT_INTENTS:
                intent = "general_qa_question"
                c = min(c, 0.55)
            return {"intent": intent, "confidence": round(c, 3)}
        except Exception:
            return {"intent": "general_qa_question", "confidence": 0.4}
