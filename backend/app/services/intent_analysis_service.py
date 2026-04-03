"""Extract IntentRecord from user/Jira text (LLM JSON + keyword boosts)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.core.schemas_dita_pipeline import DomainSignals, IntentRecord
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"


# Jira issue type → (dita_topic_type_guess, content_intent) mapping
_JIRA_TYPE_TO_DITA: dict[str, tuple[str, str]] = {
    "bug": ("task", "bug_repro"),
    "story": ("concept", "feature_request"),
    "task": ("task", "task_procedure"),
    "epic": ("map_only", "documentation"),
    "improvement": ("concept", "feature_request"),
    "sub-task": ("task", "task_procedure"),
    "new feature": ("concept", "feature_request"),
    "documentation": ("concept", "documentation"),
}


def _keyword_boost_intent(
    user_text: str,
    base: IntentRecord,
    evidence_fields: dict | None = None,
) -> IntentRecord:
    """Merge rule-based signals so table/alignment issues never miss anti_fallback flags.

    When evidence_fields contains structured Jira data (issue_type, steps_to_reproduce, etc.),
    use them to boost topic type and content intent accuracy.
    """
    t = (user_text or "").lower()
    patterns = list(base.required_dita_patterns)
    anti = list(base.anti_fallback_signals)
    dom = base.domain_signals.model_copy()
    topic_type = base.dita_topic_type_guess
    content_intent = base.content_intent

    ef = evidence_fields or {}

    # --- Jira issue type → DITA topic type boost ---
    jira_type = (ef.get("issue_type") or "").strip().lower()
    if jira_type and jira_type in _JIRA_TYPE_TO_DITA:
        mapped_type, mapped_intent = _JIRA_TYPE_TO_DITA[jira_type]
        # Only override if LLM wasn't confident (unknown or low-confidence)
        if topic_type in ("unknown", "topic"):
            topic_type = mapped_type
        if content_intent == "unknown":
            content_intent = mapped_intent

    # --- Structured field signals ---
    if ef.get("steps_to_reproduce"):
        if "steps" not in patterns:
            patterns.append("steps")
        if topic_type in ("unknown", "topic", "concept"):
            topic_type = "task"
        if content_intent == "unknown":
            content_intent = "bug_repro"

    if ef.get("acceptance_criteria"):
        if "checklist" not in patterns:
            patterns.append("checklist")

    if ef.get("expected_behavior") and ef.get("actual_behavior"):
        # Troubleshooting pattern: symptom (actual) + remedy (expected)
        if content_intent == "unknown":
            content_intent = "bug_repro"
        if topic_type in ("unknown", "topic"):
            topic_type = "task"

    # --- BDD / user story patterns ---
    if re.search(r"\bgiven\b.*\bwhen\b.*\bthen\b", t, re.DOTALL):
        if "steps" not in patterns:
            patterns.append("steps")
        if topic_type in ("unknown", "topic"):
            topic_type = "task"

    if re.search(r"\bas\s+a\b.*\bi\s+want\b", t, re.DOTALL):
        if topic_type in ("unknown", "topic"):
            topic_type = "concept"
        if content_intent == "unknown":
            content_intent = "feature_request"

    # --- Original keyword patterns ---
    if "table" in t or "tables" in t or "cell" in t or "column" in t:
        if "table" not in patterns and "none" not in patterns:
            patterns.append("table")
        if any(x in t for x in ("align", "alignment", "right-click", "right click", "menu", "menus", "justify")):
            anti.extend(["table_alignment", "no_prose_only"])
            if "menucascade" not in patterns:
                patterns.append("menucascade")
    if any(x in t for x in ("aem", "xml documentation", "guides", "web editor", "oxygen")):
        dom.aem_guides = True
    if any(x in t for x in ("web editor", "author", "preview", "rte", "rich text")):
        dom.web_editor = True
    if any(x in t for x in ("menu", "click", "ui", "dialog", "context")):
        dom.ui_workflow = True

    # Dedupe patterns (remove none if we added real patterns)
    if any(p != "none" for p in patterns):
        patterns = [p for p in patterns if p != "none"]
    anti = list(dict.fromkeys(anti))

    spec = base.specialized_construct_required or bool(
        [p for p in patterns if p and p != "none"]
    )
    return base.model_copy(
        update={
            "required_dita_patterns": patterns or base.required_dita_patterns,
            "anti_fallback_signals": anti or base.anti_fallback_signals,
            "domain_signals": dom,
            "specialized_construct_required": spec,
            "dita_topic_type_guess": topic_type,
            "content_intent": content_intent,
        }
    )


def _load_intent_prompt() -> str:
    p = PROMPTS_DIR / "intent_analysis.txt"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _fallback_intent(user_text: str, evidence_fields: dict | None = None) -> IntentRecord:
    ir = IntentRecord(
        content_intent="unknown",
        dita_topic_type_guess="unknown",
        specialized_construct_required=False,
        user_expectation="Generate appropriate DITA from the request.",
        confidence=0.3,
    )
    return _keyword_boost_intent(user_text, ir, evidence_fields=evidence_fields)


async def analyze_intent_async(
    user_text: str,
    *,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    evidence_fields: dict | None = None,
) -> IntentRecord:
    from app.services.llm_service import generate_json, is_llm_available

    text = (user_text or "").strip()
    if not text:
        return _fallback_intent(text, evidence_fields=evidence_fields)

    prompt = _load_intent_prompt()
    if not prompt or not is_llm_available():
        logger.info_structured(
            "Intent analysis: LLM unavailable or prompt missing; keyword-only",
            extra_fields={"jira_id": jira_id},
        )
        return _keyword_boost_intent(text, _fallback_intent(text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)

    try:
        raw = await generate_json(
            prompt,
            f"USER TEXT:\n{text[:12000]}\n\nOutput JSON only:",
            max_tokens=1200,
            step_name="intent_analysis",
            trace_id=trace_id,
            jira_id=jira_id,
        )
        if not isinstance(raw, dict):
            raw = {}
        dom = raw.get("domain_signals") or {}
        base = IntentRecord(
            content_intent=raw.get("content_intent", "unknown"),
            dita_topic_type_guess=raw.get("dita_topic_type_guess", "unknown"),
            specialized_construct_required=bool(raw.get("specialized_construct_required", False)),
            required_dita_patterns=list(raw.get("required_dita_patterns") or []),
            domain_signals=DomainSignals(
                aem_guides=bool(dom.get("aem_guides", False)),
                dita_ot=bool(dom.get("dita_ot", False)),
                web_editor=bool(dom.get("web_editor", False)),
                ui_workflow=bool(dom.get("ui_workflow", False)),
            ),
            user_expectation=str(raw.get("user_expectation") or "")[:500],
            anti_fallback_signals=list(raw.get("anti_fallback_signals") or []),
            evidence_phrases=list(raw.get("evidence_phrases") or [])[:20],
            confidence=float(raw.get("confidence") or 0.5),
            assumptions=list(raw.get("assumptions") or [])[:10],
        )
        merged = _keyword_boost_intent(text, base, evidence_fields=evidence_fields)
        logger.info_structured(
            "Intent analysis complete",
            extra_fields={
                "jira_id": jira_id,
                "content_intent": merged.content_intent,
                "specialized_construct_required": merged.specialized_construct_required,
                "patterns": merged.required_dita_patterns[:8],
            },
        )
        return merged
    except Exception as e:
        logger.warning_structured(
            "Intent analysis LLM failed; keyword fallback",
            extra_fields={"error": str(e), "jira_id": jira_id},
        )
        return _keyword_boost_intent(text, _fallback_intent(text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)


def analyze_intent_sync(user_text: str, evidence_fields: dict | None = None) -> IntentRecord:
    """Synchronous keyword-only intent (for tight loops / tests)."""
    return _keyword_boost_intent(user_text, _fallback_intent(user_text, evidence_fields=evidence_fields), evidence_fields=evidence_fields)
