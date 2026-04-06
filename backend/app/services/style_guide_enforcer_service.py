"""Style Guide Enforcer service for DITA XML content.

Parses DITA XML, delegates to the pure-Python style_rules_engine, and
returns a structured quality report with score, grade, and violations.
"""

import xml.etree.ElementTree as ET
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.services.style_rules_engine import evaluate as run_rules_engine

logger = get_structured_logger("style_guide_enforcer_service")


# ---------------------------------------------------------------------------
# Grade mapping
# ---------------------------------------------------------------------------

def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enforce(
    dita_xml: str,
    rules_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Analyse *dita_xml* against the style guide and return a quality report.

    Parameters
    ----------
    dita_xml : str
        Raw DITA XML string (topic, task, concept, reference, etc.).
    rules_config : dict, optional
        Tenant-level overrides for the rules engine (enabled rules,
        severity levels, custom banned/required terms).

    Returns
    -------
    dict
        {
            "score": int (0-100),
            "grade": str ("A"/"B"/"C"/"D"/"F"),
            "violations": [...],
            "summary": {"errors": int, "warnings": int, "info": int},
            "passed_rules": int,
            "total_rules": int,
        }
    """
    if not dita_xml or not dita_xml.strip():
        logger.info("style_guide_enforcer_empty_content")
        return {
            "score": 100,
            "grade": "A",
            "violations": [],
            "summary": {"errors": 0, "warnings": 0, "info": 0},
            "passed_rules": 0,
            "total_rules": 0,
        }

    # Validate XML is at least parseable (engine handles fallback too)
    try:
        ET.fromstring(dita_xml)
    except ET.ParseError as exc:
        logger.warning("style_guide_enforcer_xml_parse_warning: %s", str(exc))
        # Still run text-only rules — engine handles this gracefully

    result = run_rules_engine(dita_xml, rules_config)

    score: int = result["score"]
    grade = _score_to_grade(score)

    # Sort violations: errors first, then warnings, then info
    severity_order = {"error": 0, "warning": 1, "info": 2}
    sorted_violations = sorted(
        result["violations"],
        key=lambda v: severity_order.get(v["severity"], 3),
    )

    report = {
        "score": score,
        "grade": grade,
        "violations": sorted_violations,
        "summary": result["summary"],
        "passed_rules": result["passed_rules"],
        "total_rules": result["total_rules"],
    }

    logger.info(
        "style_guide_enforcer_result: score=%d grade=%s errors=%d warnings=%d info=%d",
        score, grade, result["summary"]["errors"],
        result["summary"]["warnings"], result["summary"]["info"],
    )

    return report
