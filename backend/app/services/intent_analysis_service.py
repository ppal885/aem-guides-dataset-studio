"""Extract IntentRecord from user/Jira text (LLM JSON + keyword boosts).

Keyword rules are loaded from ``topic_type_keywords.json`` so they can be
updated without touching code.  The JSON file is re-read on every call in
dev mode (``RELOAD_KEYWORDS=true``) and cached otherwise.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Optional

from app.core.schemas_dita_pipeline import DetectedDitaConstruct, DomainSignals, IntentRecord
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"
_KEYWORDS_PATH = PROMPTS_DIR / "topic_type_keywords.json"

# ── JSON keyword config loader (hot-reloadable) ──
_keyword_config_cache: dict[str, Any] | None = None
_keyword_config_mtime: float = 0.0


def _load_keyword_config() -> dict[str, Any]:
    """Load topic_type_keywords.json, with optional hot-reload in dev mode."""
    global _keyword_config_cache, _keyword_config_mtime

    if not _KEYWORDS_PATH.exists():
        return {}

    mtime = _KEYWORDS_PATH.stat().st_mtime
    reload = os.getenv("RELOAD_KEYWORDS", "true").lower() == "true"

    if _keyword_config_cache is not None and (not reload or mtime == _keyword_config_mtime):
        return _keyword_config_cache

    try:
        raw = _KEYWORDS_PATH.read_text(encoding="utf-8")
        _keyword_config_cache = json.loads(raw)
        _keyword_config_mtime = mtime
        return _keyword_config_cache  # type: ignore[return-value]
    except Exception as e:
        logger.warning_structured(
            "Failed to load topic_type_keywords.json, using hardcoded fallback",
            extra_fields={"error": str(e)},
        )
        return {}


def _match_any(text: str, patterns: list[str]) -> bool:
    """Return True if any regex pattern from the list matches text."""
    for p in patterns:
        try:
            if re.search(rf"\b(?:{p})\b", text, re.IGNORECASE):
                return True
        except re.error:
            continue
    return False


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


# ── DITA attribute/element detection patterns ──
_DITA_ATTRIBUTE_PATTERNS: dict[str, re.Pattern[str]] = {
    "format": re.compile(r'\b(?:format\s*(?:=|attribute)|@format|format\s*=\s*["\']?\w+)\b', re.I),
    "scope": re.compile(r'\b(?:scope\s*(?:=|attribute)|@scope|scope\s*=\s*["\']?(?:local|peer|external))\b', re.I),
    "chunk": re.compile(r'\b(?:chunk\s*(?:=|attribute)|@chunk|chunk\s*=\s*["\']?\w+)\b', re.I),
    "type": re.compile(r'\b(?:@type|type\s*=\s*["\']?(?:topic|concept|task|reference|fig|fn|section|table))\b', re.I),
    "collection-type": re.compile(r'\b(?:collection[\-.]type|@collection-type)\b', re.I),
    "processing-role": re.compile(r'\b(?:processing[\-.]role|@processing-role|resource[\-.]only)\b', re.I),
    "linking": re.compile(r'\b(?:linking\s*(?:=|attribute)|@linking|targetonly|sourceonly)\b', re.I),
    "locktitle": re.compile(r'\b(?:locktitle|@locktitle|lock[\-.]title)\b', re.I),
    "conref": re.compile(r'\b(?:conref\s*(?:=|attribute)|@conref|conref\b)', re.I),
    "conkeyref": re.compile(r'\b(?:conkeyref\s*(?:=|attribute)|@conkeyref|conkeyref\b)', re.I),
    "keyref": re.compile(r'\b(?:keyref\s*(?:=|attribute)|@keyref|keyref\b)', re.I),
    "keys": re.compile(r'\b(?:keys\s*(?:=|attribute)|@keys|\bkeys\b)', re.I),
    "keyscope": re.compile(r'\b(?:keyscope\s*(?:=|attribute)|@keyscope|keyscope\b)', re.I),
    "href": re.compile(r'\b(?:href\s*(?:=|attribute)|@href)\b', re.I),
    "navtitle": re.compile(r'\b(?:navtitle\s*(?:=|attribute)|@navtitle)\b', re.I),
    "toc": re.compile(r'\b(?:@toc|toc\s*=\s*["\']?(?:yes|no))\b', re.I),
    "print": re.compile(r'\b(?:@print|print\s*=\s*["\']?(?:yes|no|printonly))\b', re.I),
}

_DITA_ELEMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "topicref": re.compile(r'\btopicref\b', re.I),
    "xref": re.compile(r'\b(?:xref|cross[\-\s]?ref)\b', re.I),
    "keydef": re.compile(r'\bkeydef\b', re.I),
    "reltable": re.compile(r'\b(?:reltable|relationship\s+table)\b', re.I),
    "mapref": re.compile(r'\bmapref\b', re.I),
    "topichead": re.compile(r'\btopichead\b', re.I),
    "topicgroup": re.compile(r'\btopicgroup\b', re.I),
    "glossentry": re.compile(r'\bglossentry\b', re.I),
    "bookmap": re.compile(r'\bbookmap\b', re.I),
    "image": re.compile(r'\b(?:<image|image\s+element)\b', re.I),
    "audio": re.compile(r'\b(?:<audio|audio\s+element)\b', re.I),
    "video": re.compile(r'\b(?:<video|video\s+element)\b', re.I),
}

_ATTR_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "format": re.compile(r'format\s*=\s*["\']?(\w+)', re.I),
    "scope": re.compile(r'scope\s*=\s*["\']?(local|peer|external)', re.I),
    "type": re.compile(r'type\s*=\s*["\']?(\w+(?:/\w+)?)', re.I),
    "chunk": re.compile(r'chunk\s*=\s*["\']?([\w\-]+)', re.I),
    "collection-type": re.compile(r'collection[\-.]type\s*=\s*["\']?(\w+)', re.I),
    "processing-role": re.compile(r'processing[\-.]role\s*=\s*["\']?([\w\-]+)', re.I),
    "linking": re.compile(r'linking\s*=\s*["\']?(\w+)', re.I),
    "toc": re.compile(r'toc\s*=\s*["\']?(yes|no)', re.I),
    "print": re.compile(r'print\s*=\s*["\']?(yes|no|printonly)', re.I),
}


def _detect_dita_construct(text: str, evidence_fields: dict | None = None) -> DetectedDitaConstruct:
    """Identify which DITA attributes/elements a Jira ticket is about."""
    ef = evidence_fields or {}
    search_text = (text or "") + " " + (ef.get("summary") or "") + " " + (ef.get("description") or "")

    detected_attrs: list[str] = []
    detected_elems: list[str] = []
    specific_values: dict[str, list[str]] = {}

    for attr_name, pattern in _DITA_ATTRIBUTE_PATTERNS.items():
        if pattern.search(search_text):
            detected_attrs.append(attr_name)
            val_pat = _ATTR_VALUE_PATTERNS.get(attr_name)
            if val_pat:
                vals = val_pat.findall(search_text)
                if vals:
                    specific_values[attr_name] = list(dict.fromkeys(vals))

    for elem_name, pattern in _DITA_ELEMENT_PATTERNS.items():
        if pattern.search(search_text):
            detected_elems.append(elem_name)

    confidence = 0.0
    if detected_attrs or detected_elems:
        confidence = 0.5
        if detected_attrs and detected_elems:
            confidence = 0.8
        if specific_values:
            confidence = min(1.0, confidence + 0.15)

    return DetectedDitaConstruct(
        attributes=detected_attrs,
        elements=detected_elems,
        specific_values=specific_values,
        confidence=confidence,
    )


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

    # ══════════════════════════════════════════════════════════════
    # JSON-driven keyword engine (edit topic_type_keywords.json to add keywords)
    # ══════════════════════════════════════════════════════════════
    kw_cfg = _load_keyword_config()
    intent_map = kw_cfg.get("content_intent_map", {})

    # ── 1. Explicit overrides (highest priority — user explicitly asked for a type) ──
    explicit = kw_cfg.get("explicit_overrides", {})
    for tt, tt_patterns in explicit.items():
        if tt.startswith("_"):
            continue
        if isinstance(tt_patterns, list) and _match_any(t, tt_patterns):
            topic_type = tt
            content_intent = intent_map.get(tt, content_intent if content_intent != "unknown" else "documentation")
            # Add related patterns (e.g., glossary → glossary pattern)
            if tt == "glossentry" and "glossary" not in patterns:
                patterns.append("glossary")
            break

    # ── 2. Inferred keywords (secondary — only when type is still ambiguous) ──
    if topic_type in ("unknown", "topic"):
        inferred = kw_cfg.get("inferred_keywords", {})
        for tt in ("reference", "task", "concept"):  # priority order
            tt_patterns = inferred.get(tt, [])
            if isinstance(tt_patterns, list) and _match_any(t, tt_patterns):
                topic_type = tt
                if content_intent == "unknown":
                    content_intent = intent_map.get(tt, "documentation")
                break

    # ── 3. Pattern boosters (add required_dita_patterns from keywords) ──
    boosters = kw_cfg.get("pattern_boosters", {})
    for pat_name, pat_keywords in boosters.items():
        if pat_name.startswith("_"):
            continue
        if isinstance(pat_keywords, list) and _match_any(t, pat_keywords):
            if pat_name not in patterns:
                patterns.append(pat_name)
            # Some patterns also imply a topic type
            if pat_name == "task_steps" and topic_type in ("unknown", "topic"):
                topic_type = "task"
            elif pat_name == "properties" and topic_type in ("unknown", "topic"):
                topic_type = "reference"

    # ── 4. Domain signal detection (from JSON) ──
    domain_cfg = kw_cfg.get("domain_signals", {})
    if isinstance(domain_cfg.get("aem_guides"), list) and _match_any(t, domain_cfg["aem_guides"]):
        dom.aem_guides = True
    if isinstance(domain_cfg.get("web_editor"), list) and _match_any(t, domain_cfg["web_editor"]):
        dom.web_editor = True
    if isinstance(domain_cfg.get("ui_workflow"), list) and _match_any(t, domain_cfg["ui_workflow"]):
        dom.ui_workflow = True
    if isinstance(domain_cfg.get("dita_ot"), list) and _match_any(t, domain_cfg["dita_ot"]):
        dom.dita_ot = True
    # Note: localization and publishing signals are informational (no DomainSignals field yet)
    # but they still help the LLM intent analyzer via keyword presence.

    # ── Legacy table/alignment patterns (kept for backward compat) ──
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

    # DITA construct detection (for test data generation)
    construct = _detect_dita_construct(user_text, evidence_fields=ef)

    spec = base.specialized_construct_required or bool(
        [p for p in patterns if p and p != "none"]
    )
    if construct.confidence >= 0.5:
        spec = True

    return base.model_copy(
        update={
            "required_dita_patterns": patterns or base.required_dita_patterns,
            "anti_fallback_signals": anti or base.anti_fallback_signals,
            "domain_signals": dom,
            "specialized_construct_required": spec,
            "dita_topic_type_guess": topic_type,
            "content_intent": content_intent,
            "detected_dita_construct": construct,
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
