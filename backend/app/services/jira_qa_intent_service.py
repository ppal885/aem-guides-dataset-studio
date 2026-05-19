"""Intent classification for Jira QA RAG / Copilot (rules + LLM + history-aware service)."""

from __future__ import annotations

from typing import Any

from app.services.intent_classifier_service import (
    COPILOT_INTENTS,
    IntentClassifierService,
    classify_intent_rules,
)

# Superset for template lookup / backward compatibility with scoped routes.
INTENTS = frozenset(COPILOT_INTENTS) | {"uac_discussion"}


def classify_jira_qa_intent_rules(message: str, jira_key: str | None) -> str | None:
    """High-precision rule path; returns None if ambiguous."""
    intent, _conf = classify_intent_rules(message, jira_key)
    return intent


async def classify_jira_qa_intent(
    message: str,
    jira_key: str | None = None,
    *,
    history: list[dict[str, Any]] | None = None,
) -> str:
    """Return canonical intent string (Copilot set)."""
    r = await IntentClassifierService().classify(message, jira_key=jira_key, history=history)
    return str(r.get("intent") or "general_qa_question")


async def classify_jira_qa_intent_with_confidence(
    message: str,
    jira_key: str | None = None,
    *,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return await IntentClassifierService().classify(message, jira_key=jira_key, history=history)


def intent_label(intent: str) -> str:
    return intent
