"""
DITA pattern classifier - LLM-based pattern selection within a feature family.

Classifies specific pattern (e.g. keyref: map_hierarchy_key_resolution) from evidence.
"""
import json
from pathlib import Path
from typing import Optional

from app.core.schemas_pipeline import IssueEvidence, PatternClassification
from app.services.llm_service import generate_json, is_llm_available
from app.services.recipe_scoring_service import (
    KEYREF_PATTERNS,
    XREF_PATTERNS,
    CONREF_PATTERNS,
    DITAVAL_PATTERNS,
    MAP_HIERARCHY_PATTERNS,
    METADATA_PATTERNS,
    TASK_CONTENT_PATTERNS,
    REFERENCE_CONTENT_PATTERNS,
    STRESS_DATASET_PATTERNS,
    IMAGE_REFERENCE_PATTERNS,
    INLINE_FORMATTING_PATTERNS,
    TABLE_CONTENT_PATTERNS,
    EXPERIENCE_LEAGUE_PATTERNS,
    compute_pattern_scores,
    select_pattern,
)
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"

PATTERNS_BY_FEATURE: dict[str, list[str]] = {
    "keyref": KEYREF_PATTERNS,
    "xref": XREF_PATTERNS,
    "conref": CONREF_PATTERNS,
    "ditaval": DITAVAL_PATTERNS,
    "map_hierarchy": MAP_HIERARCHY_PATTERNS,
    "metadata": METADATA_PATTERNS,
    "task_content": TASK_CONTENT_PATTERNS,
    "reference_content": REFERENCE_CONTENT_PATTERNS,
    "stress_dataset": STRESS_DATASET_PATTERNS,
    "image_reference": IMAGE_REFERENCE_PATTERNS,
    "inline_formatting": INLINE_FORMATTING_PATTERNS,
    "table_content": TABLE_CONTENT_PATTERNS,
    "experience_league": EXPERIENCE_LEAGUE_PATTERNS,
}


def _load_prompt(feature: str) -> str:
    if feature == "keyref":
        path = PROMPTS_DIR / "keyref_pattern_classifier.txt"
    elif feature == "stress_dataset":
        path = PROMPTS_DIR / "stress_dataset_pattern_classifier.txt"
    elif feature == "image_reference":
        path = PROMPTS_DIR / "image_reference_pattern_classifier.txt"
    elif feature == "table_content":
        path = PROMPTS_DIR / "table_content_pattern_classifier.txt"
    elif feature in ("experience_league", "map_hierarchy", "metadata", "task_content", "reference_content", "inline_formatting"):
        path = PROMPTS_DIR / "pattern_classifier.txt"
    else:
        path = PROMPTS_DIR / "pattern_classifier.txt"
    if not path.exists():
        path = PROMPTS_DIR / "keyref_pattern_classifier.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


async def classify_pattern(
    issue_evidence: IssueEvidence,
    selected_feature: str,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    use_llm: bool = True,
) -> PatternClassification:
    """
    Classify pattern within selected feature. Uses deterministic scoring when LLM unavailable.
    """
    patterns = PATTERNS_BY_FEATURE.get(selected_feature, KEYREF_PATTERNS)
    det_scores = compute_pattern_scores(issue_evidence, selected_feature)
    det_selected, det_rejected = select_pattern(det_scores)

    if not use_llm or not is_llm_available():
        logger.info_structured(
            "Pattern classification (deterministic)",
            extra_fields={"selected_feature": selected_feature, "selected_pattern": det_selected},
        )
        return PatternClassification(
            selected_feature=selected_feature,
            pattern_scores=det_scores,
            selected_pattern=det_selected,
            confidence=det_scores.get(det_selected, 0.5),
            evidence=[],
            rejected_patterns=det_rejected,
            assumptions=["LLM unavailable; used deterministic scoring"],
            unknowns=[],
        )

    prompt = _load_prompt(selected_feature)
    if not prompt:
        return PatternClassification(
            selected_feature=selected_feature,
            pattern_scores=det_scores,
            selected_pattern=det_selected,
            confidence=0.5,
            evidence=[],
            rejected_patterns=det_rejected,
            assumptions=["Prompt not found; used deterministic scoring"],
            unknowns=[],
        )

    evidence_text = (issue_evidence.raw_text or "") + " " + (issue_evidence.summary or "") + " " + (issue_evidence.description or "")
    evidence_payload = {
        "summary": issue_evidence.summary[:500],
        "description": (issue_evidence.description or "")[:2000],
        "raw_text_excerpt": (issue_evidence.raw_text or "")[:3000],
    }
    user = f"Evidence (selected_feature={selected_feature}):\n{json.dumps(evidence_payload, indent=2)}"
    try:
        from app.utils.evidence_extractor import USE_AEM_DOCS_ENRICHMENT, AEM_GUIDES_TRIGGER_TERMS
        from app.services.doc_retriever_service import retrieve_relevant_docs, format_docs_for_prompt
        if USE_AEM_DOCS_ENRICHMENT and any(t in evidence_text.lower() for t in AEM_GUIDES_TRIGGER_TERMS):
            docs = retrieve_relevant_docs(evidence_text[:3000], k=3, max_snippet_chars=500)
            if docs:
                user += f"\n\nAEM Guides documentation context:\n{format_docs_for_prompt(docs)}"
    except Exception:
        pass
    user += "\n\nOutput STRICT JSON only:"

    try:
        result = await generate_json(
            prompt, user, max_tokens=600, step_name="pattern_classifier",
            trace_id=trace_id, jira_id=jira_id,
        )
    except Exception as e:
        logger.warning_structured(
            "Pattern classifier LLM failed",
            extra_fields={"jira_id": jira_id, "selected_feature": selected_feature, "error": str(e)},
        )
        return PatternClassification(
            selected_feature=selected_feature,
            pattern_scores=det_scores,
            selected_pattern=det_selected,
            confidence=0.5,
            evidence=[],
            rejected_patterns=det_rejected,
            assumptions=[f"LLM failed: {e}; used deterministic scoring"],
            unknowns=[],
        )

    llm_scores = result.get("pattern_scores") or {}
    merged = {p: max(det_scores.get(p, 0), llm_scores.get(p, 0)) for p in patterns}
    if not merged:
        merged = det_scores

    selected = result.get("selected_pattern") or ""
    if selected not in patterns:
        selected = max(merged.items(), key=lambda x: x[1])[0] if merged else det_selected

    rejected = result.get("rejected_patterns") or []
    if not rejected:
        rejected = [p for p, s in merged.items() if p != selected and s >= 0.2]

    logger.info_structured(
        "Pattern classification",
        extra_fields={
            "selected_feature": selected_feature,
            "selected_pattern": selected,
            "rejected_patterns": rejected[:5],
        },
    )

    return PatternClassification(
        selected_feature=selected_feature,
        pattern_scores=merged,
        selected_pattern=selected,
        confidence=float(result.get("confidence", 0.5)),
        evidence=result.get("evidence") or [],
        rejected_patterns=rejected,
        assumptions=result.get("assumptions") or [],
        unknowns=result.get("unknowns") or [],
    )
