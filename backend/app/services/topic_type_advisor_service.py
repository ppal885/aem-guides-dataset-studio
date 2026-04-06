"""
Topic Type Advisor - analyzes DITA XML content and recommends the correct
topic type (task, concept, reference, glossentry).

Pure rule-based analysis with zero LLM cost.  Detects misclassified content
and returns actionable remediation suggestions.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_TOPIC_TYPES = {"task", "concept", "reference", "glossentry", "topic"}

# Weights for individual signals (higher = stronger indicator)
_W_STRONG = 0.9
_W_MEDIUM = 0.6
_W_WEAK = 0.3

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Signal:
    signal: str
    weight: float
    supports_type: str


@dataclass
class AdvisorResult:
    current_type: str
    recommended_type: str
    is_misclassified: bool
    confidence: float
    reasoning: str
    signals: List[Dict[str, object]]
    suggested_fix: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_all_recursive(root: ET.Element, tag: str) -> List[ET.Element]:
    """Find all descendant elements with *tag* anywhere in the tree."""
    return list(root.iter(tag))


def _count_text_length(elem: ET.Element) -> int:
    """Return total character count of all text content under *elem*."""
    total = 0
    for e in elem.iter():
        if e.text:
            total += len(e.text.strip())
        if e.tail:
            total += len(e.tail.strip())
    return total


def _has_procedural_ol(root: ET.Element) -> bool:
    """Detect <ol> lists that look like step-by-step procedures."""
    for ol in root.iter("ol"):
        li_items = ol.findall("li")
        if len(li_items) >= 2:
            return True
    return False


def _has_header_row(table: ET.Element) -> bool:
    """Check whether a simpletable or table has a header row."""
    if table.find("sthead") is not None:
        return True
    if table.find(".//thead") is not None:
        return True
    return False


# ---------------------------------------------------------------------------
# Signal detection
# ---------------------------------------------------------------------------


def _collect_signals(root: ET.Element) -> List[Signal]:
    """Walk the XML tree and collect type-indicator signals.

    Body-wrapper elements (taskbody, conbody, refbody) are deliberately
    excluded because they merely mirror the root element and would mask
    misclassification.  We only look at *content* signals.
    """
    signals: List[Signal] = []

    # -- Task signals -------------------------------------------------------
    if _find_all_recursive(root, "steps"):
        signals.append(Signal("Contains <steps> element", _W_STRONG, "task"))
    if _find_all_recursive(root, "steps-unordered"):
        signals.append(Signal("Contains <steps-unordered> element", _W_STRONG, "task"))
    if _has_procedural_ol(root):
        signals.append(Signal(
            "Contains <ol> with 2+ items resembling a procedure",
            _W_MEDIUM, "task",
        ))
    if _find_all_recursive(root, "cmd"):
        signals.append(Signal("Contains <cmd> elements (step commands)", _W_MEDIUM, "task"))
    if _find_all_recursive(root, "stepresult"):
        signals.append(Signal("Contains <stepresult> elements", _W_MEDIUM, "task"))
    if _find_all_recursive(root, "prereq"):
        signals.append(Signal("Contains <prereq> element", _W_WEAK, "task"))
    if _find_all_recursive(root, "postreq"):
        signals.append(Signal("Contains <postreq> element", _W_WEAK, "task"))

    # -- Reference signals --------------------------------------------------
    if _find_all_recursive(root, "properties"):
        signals.append(Signal("Contains <properties> table", _W_STRONG, "reference"))
    for st in _find_all_recursive(root, "simpletable"):
        if _has_header_row(st):
            signals.append(Signal(
                "Contains <simpletable> with header row",
                _W_MEDIUM, "reference",
            ))
            break  # one signal is enough
    codeblocks = _find_all_recursive(root, "codeblock")
    if codeblocks:
        # If codeblock is accompanied by parameter-like lists, lean reference
        param_lists = (_find_all_recursive(root, "parml")
                       or _find_all_recursive(root, "dl"))
        if param_lists:
            signals.append(Signal(
                "Contains <codeblock> with parameter/definition lists",
                _W_MEDIUM, "reference",
            ))
        else:
            signals.append(Signal(
                "Contains <codeblock> element",
                _W_WEAK, "reference",
            ))
    if _find_all_recursive(root, "refsyn"):
        signals.append(Signal("Contains <refsyn> syntax section", _W_MEDIUM, "reference"))

    # -- Concept signals ----------------------------------------------------
    sections = _find_all_recursive(root, "section")
    if sections:
        prose_heavy = all(
            _count_text_length(s) > 50 for s in sections
        )
        if prose_heavy and len(sections) >= 1:
            signals.append(Signal(
                f"Contains {len(sections)} <section>(s) with substantial prose",
                _W_MEDIUM, "concept",
            ))
        elif sections:
            signals.append(Signal(
                f"Contains {len(sections)} <section> element(s)",
                _W_WEAK, "concept",
            ))
    # Note: <conbody> excluded -- it mirrors root and would mask misclassification

    # -- Glossentry signals -------------------------------------------------
    if _find_all_recursive(root, "glossBody") or _find_all_recursive(root, "glossbody"):
        signals.append(Signal("Contains <glossBody> element", _W_STRONG, "glossentry"))
    if _find_all_recursive(root, "glossdef"):
        signals.append(Signal("Contains <glossdef> definition", _W_STRONG, "glossentry"))
    if _find_all_recursive(root, "glossterm"):
        signals.append(Signal("Contains <glossterm> element", _W_MEDIUM, "glossentry"))

    return signals


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _score_signals(signals: List[Signal]) -> Dict[str, float]:
    """Aggregate signal weights per topic type.  Returns normalised scores."""
    raw: Dict[str, float] = {}
    for s in signals:
        raw[s.supports_type] = raw.get(s.supports_type, 0.0) + s.weight

    total = sum(raw.values()) or 1.0
    return {t: round(v / total, 4) for t, v in raw.items()}


def _pick_recommendation(
    scores: Dict[str, float],
    current_type: str,
    signals: List[Signal],
) -> tuple[str, float, str]:
    """Return (recommended_type, confidence, reasoning)."""
    if not scores:
        return current_type, 0.0, "No structural signals detected; keeping current type."

    sorted_types = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_type, best_score = sorted_types[0]

    # Detect mixed content
    if len(sorted_types) >= 2:
        second_type, second_score = sorted_types[1]
        if best_score - second_score < 0.15 and best_score < 0.6:
            reasoning = (
                f"Content has mixed signals: {best_type} ({best_score:.0%}) "
                f"and {second_type} ({second_score:.0%}). "
                "Consider splitting into separate topics."
            )
            return "mixed", round(best_score, 2), reasoning

    confidence = round(min(best_score * 1.2, 1.0), 2)
    reasoning = f"Strongest signals point to {best_type} ({best_score:.0%} of total weight)."
    return best_type, confidence, reasoning


# ---------------------------------------------------------------------------
# Misclassification detection
# ---------------------------------------------------------------------------


def _detect_misclassification(
    current_type: str,
    recommended_type: str,
    signals: List[Signal],
) -> tuple[bool, Optional[str]]:
    """Return (is_misclassified, suggested_fix)."""
    if recommended_type == "mixed":
        fix = (
            f"Current <{current_type}> contains mixed content. "
            "Split procedural steps into a <task> topic and keep "
            "conceptual prose in a <concept> topic."
        )
        return True, fix

    if current_type == recommended_type or recommended_type == current_type:
        return False, None

    # Build human-readable fix suggestion
    task_signals = [s.signal for s in signals if s.supports_type == "task"]
    ref_signals = [s.signal for s in signals if s.supports_type == "reference"]

    if current_type == "concept" and recommended_type == "task":
        fix = (
            f"Convert root <concept> to <task> and wrap procedural content in <steps>. "
            f"Detected: {'; '.join(task_signals[:2])}."
        )
    elif current_type == "task" and recommended_type == "concept":
        fix = (
            "Convert root <task> to <concept>. The topic contains only prose "
            "with no procedural steps."
        )
    elif current_type == "reference" and recommended_type == "task":
        fix = (
            "Convert root <reference> to <task>. The topic contains procedural "
            "content that belongs in a task topic."
        )
    elif recommended_type == "glossentry":
        fix = (
            f"Convert root <{current_type}> to <glossentry>. "
            "The topic contains glossary definitions."
        )
    else:
        fix = (
            f"Convert root <{current_type}> to <{recommended_type}>. "
            f"Structural signals support {recommended_type}."
        )

    return True, fix


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _detect_root_type(root: ET.Element) -> str:
    """Return the DITA topic type from the root element tag."""
    tag = root.tag.lower()
    if tag in VALID_TOPIC_TYPES:
        return tag
    # Some DITA files use specialisation tags; fall back to "topic"
    return "topic"


def analyze_topic_type(xml_content: str) -> dict:
    """Analyze DITA XML content and recommend the correct topic type.

    Parameters
    ----------
    xml_content:
        Raw DITA XML string.

    Returns
    -------
    dict  with keys: current_type, recommended_type, is_misclassified,
          confidence, reasoning, signals, suggested_fix.
    """
    if not xml_content or not xml_content.strip():
        logger.warning("topic_type_advisor_empty_input")
        return {
            "current_type": "unknown",
            "recommended_type": "unknown",
            "is_misclassified": False,
            "confidence": 0.0,
            "reasoning": "Input XML is empty.",
            "signals": [],
            "suggested_fix": None,
            "error": "empty_input",
        }

    # -- Parse XML ----------------------------------------------------------
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        logger.warning("topic_type_advisor_parse_error: %s", str(exc))
        return {
            "current_type": "unknown",
            "recommended_type": "unknown",
            "is_misclassified": False,
            "confidence": 0.0,
            "reasoning": f"Malformed XML: {exc}",
            "signals": [],
            "suggested_fix": None,
            "error": "malformed_xml",
        }

    current_type = _detect_root_type(root)

    # -- Collect and score signals ------------------------------------------
    signals = _collect_signals(root)
    scores = _score_signals(signals)
    recommended_type, confidence, reasoning = _pick_recommendation(
        scores, current_type, signals,
    )

    # -- Misclassification --------------------------------------------------
    is_misclassified, suggested_fix = _detect_misclassification(
        current_type, recommended_type, signals,
    )

    result = AdvisorResult(
        current_type=current_type,
        recommended_type=recommended_type,
        is_misclassified=is_misclassified,
        confidence=confidence,
        reasoning=reasoning,
        signals=[asdict(s) for s in signals],
        suggested_fix=suggested_fix,
    )

    logger.info(
        "topic_type_advisor_result",
        current=current_type,
        recommended=recommended_type,
        misclassified=is_misclassified,
        confidence=confidence,
    )

    return result.to_dict()
