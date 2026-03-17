"""
DITA mechanism classifier - LLM-based with signal prior merge.

Classifies primary DITA mechanism from Jira evidence. Merges with signal priors.
Applies routing overrides from feedback when evidence matches learned keywords.
"""
import json
from pathlib import Path
from typing import Optional

from app.core.schemas_pipeline import IssueEvidence, MechanismClassification
from app.services.llm_service import generate_json, is_llm_available
from app.services.signal_prior_service import compute_signal_priors, merge_priors_with_llm
from app.services.recipe_scoring_service import RECIPE_FAMILY
from app.core.structured_logging import get_structured_logger
from app.core.agentic_config import agentic_config

logger = get_structured_logger(__name__)


def _effective_prior_weight(priors: dict[str, float]) -> float:
    """Use config prior weight; boost when priors have strong signal (max >= 0.6)."""
    base = getattr(agentic_config, "mechanism_prior_weight", 0.5)
    max_prior = max(priors.values()) if priors else 0.0
    if max_prior >= 0.6:
        return min(0.7, base + 0.15)  # Trust priors more when signal is strong
    return base


def _evidence_has_conrefend_cyclic_duplicate_id(text: str) -> bool:
    """Evidence mentions conrefend/cyclic/duplicate-id (conref-specific pattern)."""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ("conrefend", "cyclic", "duplicate id", "duplicate ID", "false duplicate"))


def _evidence_has_experience_league(text: str) -> bool:
    """Evidence mentions Experience League / doc-to-dita conversion."""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ("experience league", "scraped content", "doc to dita", "documentation to dita"))


def _evidence_has_topichead(text: str) -> bool:
    """Evidence mentions topichead - map structure element (NOT ditaval)."""
    if not text:
        return False
    t = text.lower()
    return any(k in t for k in ("topichead", "topic head", "output pages under topichead", "pages under topichead"))


def _evidence_has_subject_scheme(text: str) -> bool:
    """Evidence mentions subject scheme, topicmeta, controlled values - metadata pattern."""
    if not text:
        return False
    t = text.lower()
    return any(
        k in t
        for k in (
            "subject scheme", "subjectdef", "enumerationdef", "topicmeta",
            "keywords", "indexterm", "controlled values", "audience validation",
        )
    )


def _evidence_has_table_widths(text: str) -> bool:
    """Evidence mentions table widths, colwidth, column width - table_content pattern."""
    if not text:
        return False
    t = text.lower()
    return any(
        k in t
        for k in (
            "table width", "table widths", "colwidth", "colspec", "column width",
            "table column", "table formatting", "table layout", "width %", "width px",
            "widths %", "widths px", "tgroup", "colsep", "rowsep",
        )
    )


def _evidence_has_task_content(text: str) -> bool:
    """Evidence mentions steps, cmd, task, choicetable - DITA task topic / procedural content."""
    if not text:
        return False
    t = text.lower()
    return any(
        k in t
        for k in (
            "steps", "step", "cmd", "task", "taskbody", "prereq", "result",
            "procedure", "how-to", "how to", "substep", "context", "stepresult",
            "choicetable", "choice table", "chrow", "choption", "chdesc",
        )
    )


def _evidence_has_reference_content(text: str) -> bool:
    """Evidence mentions refbody, refsyn, section, choicetable - DITA reference topic content."""
    if not text:
        return False
    t = text.lower()
    return any(
        k in t
        for k in (
            "refbody", "refsyn", "section", "sectionref", "choicetable", "choice table",
            "chrow", "choption", "chdesc", "reference topic", "properties", "property",
            "api reference", "syntax reference", "definition",
        )
    )


def _evidence_has_inline_formatting(text: str) -> bool:
    """Evidence mentions cursor, arrow keys, RTE, inline tags (<i>, <b>, <u>) - editor/RTE behavior."""
    from app.utils.evidence_context import evidence_has_inline_formatting_rte_signal
    return evidence_has_inline_formatting_rte_signal(text)


def _get_routing_override_feature(evidence_text: str, priors: Optional[dict[str, float]] = None) -> Optional[str]:
    """If evidence matches routing override keywords, return the mechanism to use.
    Skips override when table_content has strong signal (table widths) - avoids
    video/media override incorrectly routing table-width issues to media_rich_content.
    Skips override when inline_formatting/RTE has strong signal (cursor, arrow keys) - avoids
    video/media override incorrectly routing RTE issues to media_rich_content.
    """
    if not evidence_text:
        return None
    try:
        from app.services.feedback_aggregation_service import load_routing_overrides
        from app.utils.evidence_context import evidence_has_inline_formatting_rte_signal

        overrides = load_routing_overrides()
        keywords_map = overrides.get("jira_evidence_keywords") or {}
        text_lower = evidence_text.lower()
        for kw, recipe_id in keywords_map.items():
            if kw.lower() in text_lower and recipe_id:
                mechanism = RECIPE_FAMILY.get(recipe_id)
                if mechanism and mechanism in ALLOWED_FEATURES:
                    # Don't override with image_reference when evidence is primarily about table widths
                    if mechanism == "image_reference" and _evidence_has_table_widths(evidence_text):
                        table_score = (priors or {}).get("table_content", 0.0)
                        if table_score >= 0.3:
                            logger.info_structured(
                                "Skipping routing override: table_content has stronger signal",
                                extra_fields={"override_kw": kw, "table_score": table_score},
                            )
                            continue
                    # Don't override with image_reference when evidence is primarily about RTE/cursor
                    if mechanism == "image_reference" and evidence_has_inline_formatting_rte_signal(evidence_text):
                        inline_score = (priors or {}).get("inline_formatting", 0.0)
                        if inline_score >= 0.3:
                            logger.info_structured(
                                "Skipping routing override: inline_formatting has stronger signal",
                                extra_fields={"override_kw": kw, "inline_score": inline_score},
                            )
                            continue
                    return mechanism
    except Exception:
        pass
    return None

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"
ALLOWED_FEATURES = [
    "keyref", "xref", "conref", "ditaval", "schematron",
    "metadata", "publishing", "glossary", "image_reference", "inline_formatting",
    "map_hierarchy", "baseline", "approval_workflow", "stress_dataset",
    "table_content", "experience_league", "task_content", "reference_content",
]


def _load_prompt() -> str:
    path = PROMPTS_DIR / "mechanism_classifier.txt"
    return path.read_text(encoding="utf-8") if path.exists() else ""


async def classify_mechanism(
    issue_evidence: IssueEvidence,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
    use_llm: bool = True,
) -> MechanismClassification:
    """
    Classify primary DITA mechanism. Merges signal priors with LLM when LLM available.
    When LLM unavailable or use_llm=False, uses signal priors only.
    """
    evidence_text = (issue_evidence.raw_text or "") + " " + (issue_evidence.summary or "") + " " + (issue_evidence.description or "")
    priors = compute_signal_priors(evidence_text)

    override_feature = _get_routing_override_feature(evidence_text, priors)
    if override_feature:
        logger.info_structured(
            "Mechanism override from routing feedback",
            extra_fields={"override_feature": override_feature},
        )
        return MechanismClassification(
            feature_scores=priors,
            selected_feature=override_feature,
            confidence=0.9,
            evidence=["routing_override:keyword_match"],
            rejected_features=[f for f in priors if f != override_feature and priors.get(f, 0) >= 0.2],
            assumptions=["Routing override applied from user feedback"],
            unknowns=[],
        )

    if not use_llm or not is_llm_available():
        selected = max(priors.items(), key=lambda x: x[1])[0] if priors else "keyref"
        rejected = [f for f, s in priors.items() if f != selected and s >= 0.25]
        logger.info_structured(
            "Mechanism classification (priors only)",
            extra_fields={"selected_feature": selected, "priors": {k: round(v, 2) for k, v in priors.items() if v > 0}},
        )
        return MechanismClassification(
            feature_scores=priors,
            selected_feature=selected,
            confidence=priors.get(selected, 0.5),
            evidence=[],
            rejected_features=rejected,
            assumptions=["LLM unavailable; used signal priors only"],
            unknowns=[],
        )

    prompt = _load_prompt()
    if not prompt:
        selected = max(priors.items(), key=lambda x: x[1])[0] if priors else "keyref"
        return MechanismClassification(
            feature_scores=priors,
            selected_feature=selected,
            confidence=0.5,
            evidence=[],
            rejected_features=[],
            assumptions=["Prompt not found; used signal priors"],
            unknowns=[],
        )

    evidence_payload = {
        "jira_id": issue_evidence.jira_id,
        "summary": (issue_evidence.summary or "")[:600],
        "description": (issue_evidence.description or "")[:4500],
        "raw_text_excerpt": evidence_text[:5500],
    }
    user = f"Evidence:\n{json.dumps(evidence_payload, indent=2)}"
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
            prompt, user, max_tokens=800, step_name="mechanism_classifier",
            trace_id=trace_id, jira_id=jira_id,
        )
    except Exception as e:
        logger.warning_structured(
            "Mechanism classifier LLM failed",
            extra_fields={"jira_id": jira_id, "error": str(e)},
        )
        selected = max(priors.items(), key=lambda x: x[1])[0] if priors else "keyref"
        return MechanismClassification(
            feature_scores=priors,
            selected_feature=selected,
            confidence=0.5,
            evidence=[],
            rejected_features=[],
            assumptions=[f"LLM failed: {e}; used signal priors"],
            unknowns=[],
        )

    llm_scores = result.get("feature_scores") or {}
    prior_weight = _effective_prior_weight(priors)
    merged = merge_priors_with_llm(priors, llm_scores, prior_weight=prior_weight)

    selected = result.get("selected_feature") or ""
    if selected not in ALLOWED_FEATURES:
        selected = max(merged.items(), key=lambda x: x[1])[0] if merged else "keyref"

    # Inline formatting (RTE, cursor, b/i/u tags): prefer over image_reference
    if _evidence_has_inline_formatting(evidence_text) and merged.get("inline_formatting", 0) >= 0.35:
        selected = "inline_formatting"
    # Do not override image_reference when it is selected and has strong score
    elif selected == "image_reference" and merged.get("image_reference", 0) >= 0.4:
        pass  # keep image_reference
    # When image_reference has higher score than keyref (e.g. media/image evidence), prefer it
    elif merged.get("image_reference", 0) >= 0.35 and merged.get("image_reference", 0) >= merged.get("keyref", 0):
        selected = "image_reference"
    # Conref+conrefend/cyclic/duplicate-id: prefer conref over keyref (conref-specific pattern)
    elif _evidence_has_conrefend_cyclic_duplicate_id(evidence_text) and merged.get("conref", 0) >= 0.35:
        selected = "conref"
    # Experience League: prefer when evidence strongly indicates doc-to-dita
    elif _evidence_has_experience_league(evidence_text) and merged.get("experience_league", 0) >= 0.35:
        selected = "experience_league"
    # Topichead: prefer map_hierarchy over ditaval (topichead is map structure, NOT conditional filtering)
    elif _evidence_has_topichead(evidence_text) and merged.get("map_hierarchy", 0) >= 0.35:
        selected = "map_hierarchy"
    # Table widths/colwidth: prefer table_content over image_reference (avoids video/media override)
    elif _evidence_has_table_widths(evidence_text) and merged.get("table_content", 0) >= 0.35:
        selected = "table_content"
    # Subject scheme / metadata: prefer when evidence strongly indicates metadata
    elif _evidence_has_subject_scheme(evidence_text) and merged.get("metadata", 0) >= 0.35:
        selected = "metadata"
    # Task content (steps, cmd, task): prefer when evidence strongly indicates procedural content
    elif _evidence_has_task_content(evidence_text) and merged.get("task_content", 0) >= 0.35:
        selected = "task_content"
    # Reference content (refbody, refsyn, section, choicetable): prefer when evidence indicates reference topic
    elif _evidence_has_reference_content(evidence_text) and merged.get("reference_content", 0) >= 0.35:
        selected = "reference_content"
    # Glossary: prefer when evidence strongly indicates glossary
    elif merged.get("glossary", 0) >= 0.5 and merged.get("glossary", 0) >= merged.get("keyref", 0):
        selected = "glossary"
    elif merged.get("keyref", 0) >= 0.3 and merged.get("keyref", 0) >= merged.get("xref", 0):
        selected = "keyref"

    # Do not override stress_dataset when it is highest and score is high (e.g. large topic / stress)
    stress_score = merged.get("stress_dataset", 0)
    if stress_score >= 0.5 and stress_score >= merged.get("keyref", 0):
        selected = "stress_dataset"

    rejected = result.get("rejected_features") or []
    if not rejected:
        rejected = [f for f, s in merged.items() if f != selected and s >= 0.25]

    logger.info_structured(
        "Mechanism classification",
        extra_fields={
            "selected_feature": selected,
            "confidence": result.get("confidence", 0.5),
            "rejected_features": rejected[:5],
        },
    )

    def _flatten_str_list(val):
        if not val:
            return []
        out = []
        for x in val:
            if isinstance(x, str):
                out.append(x)
            elif isinstance(x, list):
                out.extend(str(i) for i in x)
            else:
                out.append(str(x))
        return out

    return MechanismClassification(
        feature_scores=merged,
        selected_feature=selected,
        confidence=float(result.get("confidence", 0.5)),
        evidence=_flatten_str_list(result.get("evidence") or []),
        rejected_features=rejected,
        assumptions=_flatten_str_list(result.get("assumptions") or []),
        unknowns=_flatten_str_list(result.get("unknowns") or []),
    )
