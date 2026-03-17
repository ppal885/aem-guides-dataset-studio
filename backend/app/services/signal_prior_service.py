"""
Signal prior scoring for DITA mechanism classification.

Keyword-based boosts merged with LLM mechanism classification.
Returns normalized scores 0.0-1.0 per mechanism.
Applies routing overrides from feedback (jira_evidence_keywords -> recipe -> mechanism boost).
"""
import re
from typing import Optional

from app.core.structured_logging import get_structured_logger
from app.services.recipe_scoring_service import RECIPE_FAMILY

logger = get_structured_logger(__name__)

KEYREF_KEYWORDS = [
    "key", "keyref", "keydef", "keyscope", "key scope",
    "duplicate key", "duplicate keys", "nested keymap", "nested keydef",
    "map hierarchy", "key resolution", "unresolved key",
    "keydef chain", "key shadow", "scoped keys", "keymap",
    "nested key resolution", "nested keydef chain", "outer map intermediate keymap",
    "keyword topic source", "recursive key loading", "keydef points to keymap",
    "keydef points to topic", "keys resolve only when intermediate",
    "web editor does not resolve nested keys", "dita-ot resolves correctly",
    "web editor author preview does not", "context map", "intermediate map workaround",
]
XREF_KEYWORDS = [
    "xref", "href", "cross reference", "cross-reference", "external link",
    "link to topic", "link to section", "broken href", "fragment",
]
CONREF_KEYWORDS = [
    "conref", "conkeyref", "content reuse", "reuse", "conrefend",
    "cyclic", "duplicate id", "duplicate ID", "false duplicate",
    "conrefend cyclic", "guides web editor",
    "conref in title", "title conref", "reusable title", "variable title",
]
GLOSSARY_KEYWORDS = [
    "glossary", "glossentry", "glossterm", "abbreviated-form",
    "glossary resolution", "term definition", "term reference",
    "abbreviation", "acronym", "glossref",
]
DITAVAL_KEYWORDS = [
    "ditaval", "audience", "platform", "product", "profiling",
    "conditional", "filter", "attribute filtering",
]
STRESS_DATASET_KEYWORDS = [
    "large topic", "heavy topic", "6000 line", "huge topic", "massive topic",
    "single topic", "one topic", "bulky topic", "save load stress", "author loading",
    "source view slow", "profiling", "conditional rendering", "filtering problem",
    "audience platform otherprops", "audience/platform/otherprops", "stress test",
    "performance test", "performance issue", "filtering test", "rendering test",
    "conditional processing", "heavy conditional", "editor rendering", "indexing", "validation",
]
IMAGE_REFERENCE_KEYWORDS = [
    "image", "images", "video", "videos", "media", "media operations",
    "asset", "assets", "figure", "alt text", "placeholder image",
    "embed", "embedding",
]
INLINE_FORMATTING_KEYWORDS = [
    "cursor", "arrow key", "arrow keys", "keyboard navigation",
    "rich text editor", "rte", "inline tag", "italic tag", "bold tag",
    "<i>", "<b>", "<u>", "<li>", "opening italic tag", "opening bold tag",
    "inline formatting", "nested tag", "nested tags", "editor behavior",
]
TABLE_CONTENT_KEYWORDS = [
    "table width", "table widths", "colwidth", "colspec", "column width",
    "table column", "table formatting", "table display", "table layout",
    "tgroup", "colsep", "rowsep", "table frame", "table rendering",
    "width %", "width px", "widths %", "widths px",  # e.g. "widths like 50% or 100px"
]
EXPERIENCE_LEAGUE_KEYWORDS = [
    "experience league", "scraped content", "authentic documentation",
    "aem guides docs", "aem guides documentation", "experience league content",
    "convert docs to dita", "doc to dita", "documentation to dita",
    "scraped docs", "web docs to dita", "html to dita",
]
MAP_HIERARCHY_KEYWORDS = [
    "mapref", "map ref", "map cycle", "cyclic map", "circular map",
    "map cyclic", "mapref cycle", "map references map",
    "topichead", "topic head", "output pages under topichead", "pages under topichead",
    "output under topichead", "toc under topichead",
    "topicgroup", "topic group", "grouping topicrefs",
    "reltable", "relationship table", "relrow", "relcell",
]
METADATA_KEYWORDS = [
    "subject scheme", "subjectdef", "enumerationdef", "subjectScheme",
    "topicmeta", "keywords", "indexterm", "controlled values",
    "audience validation", "attribute validation",
]
TASK_CONTENT_KEYWORDS = [
    "steps", "step", "cmd", "task", "taskbody", "task body",
    "prereq", "prerequisite", "result", "procedure", "how-to", "how to",
    "substep", "substeps", "context", "stepresult",
    "choicetable", "choice table", "chrow", "choption", "chdesc",
]
REFERENCE_CONTENT_KEYWORDS = [
    "refbody", "ref body", "refsyn", "ref syn", "section", "sectionref",
    "choicetable", "choice table", "chrow", "choption", "chdesc",
    "reference topic", "reference type", "properties", "property",
    "api reference", "syntax reference", "definition",
]

ALL_MECHANISMS = [
    "keyref", "xref", "conref", "ditaval", "schematron",
    "metadata", "publishing", "glossary", "image_reference", "inline_formatting",
    "map_hierarchy", "baseline", "approval_workflow", "stress_dataset",
    "table_content", "experience_league", "task_content", "reference_content",
]


def _apply_routing_override_boosts(text: str, scores: dict[str, float]) -> None:
    """Apply boosts from routing_overrides when evidence contains override keywords."""
    try:
        from app.services.feedback_aggregation_service import load_routing_overrides
        overrides = load_routing_overrides()
        keywords_map = overrides.get("jira_evidence_keywords") or {}
        for kw, recipe_id in keywords_map.items():
            if kw.lower() in text and recipe_id:
                mechanism = RECIPE_FAMILY.get(recipe_id)
                if mechanism and mechanism in scores:
                    scores[mechanism] = min(1.0, scores.get(mechanism, 0) + 0.5)
    except Exception:
        pass


def compute_signal_priors(evidence_text: str) -> dict[str, float]:
    """
    Compute keyword-based signal priors from evidence text.
    Returns normalized scores 0.0-1.0 per mechanism.
    Applies routing override boosts when evidence matches feedback-learned keywords.
    """
    if not evidence_text:
        return {m: 0.0 for m in ALL_MECHANISMS}

    text = evidence_text.lower()
    scores: dict[str, float] = {m: 0.0 for m in ALL_MECHANISMS}

    keyref_matches = sum(1 for kw in KEYREF_KEYWORDS if kw in text)
    if keyref_matches > 0:
        scores["keyref"] = min(1.0, 0.3 + keyref_matches * 0.2)
        if "map hierarchy" in text or "nested" in text:
            scores["map_hierarchy"] = max(scores["map_hierarchy"], 0.5)

    xref_matches = sum(1 for kw in XREF_KEYWORDS if kw in text)
    if xref_matches > 0 and scores["keyref"] < 0.5:
        scores["xref"] = min(1.0, 0.2 + xref_matches * 0.15)

    conref_matches = sum(1 for kw in CONREF_KEYWORDS if kw in text)
    if conref_matches > 0:
        # Strong boost when conrefend/cyclic/duplicate-id present (conref-specific)
        conref_boost = 0.35 if any(k in text for k in ("conrefend", "cyclic", "duplicate id", "duplicate ID")) else 0.2
        scores["conref"] = min(1.0, 0.25 + conref_matches * conref_boost)

    glossary_matches = sum(1 for kw in GLOSSARY_KEYWORDS if kw in text)
    if glossary_matches > 0:
        scores["glossary"] = min(1.0, 0.35 + glossary_matches * 0.15)

    ditaval_matches = sum(1 for kw in DITAVAL_KEYWORDS if kw in text)
    if ditaval_matches > 0:
        scores["ditaval"] = min(1.0, 0.2 + ditaval_matches * 0.15)

    map_hierarchy_matches = sum(1 for kw in MAP_HIERARCHY_KEYWORDS if kw in text)
    if map_hierarchy_matches > 0:
        scores["map_hierarchy"] = min(1.0, 0.3 + map_hierarchy_matches * 0.2)
    # Topichead: strong map_hierarchy boost, suppress ditaval (topichead is NOT ditaval)
    if "topichead" in text or "topic head" in text:
        scores["map_hierarchy"] = max(scores.get("map_hierarchy", 0), 0.7)
        scores["ditaval"] = 0.0

    stress_matches = sum(1 for kw in STRESS_DATASET_KEYWORDS if kw in text)
    if stress_matches > 0:
        scores["stress_dataset"] = min(1.0, 0.35 + stress_matches * 0.15)

    image_matches = sum(1 for kw in IMAGE_REFERENCE_KEYWORDS if kw in text)
    if image_matches > 0:
        scores["image_reference"] = min(1.0, 0.35 + image_matches * 0.15)

    # Inline formatting (RTE, cursor, b/i/u tags) - suppress image_reference when present
    inline_matches = sum(1 for kw in INLINE_FORMATTING_KEYWORDS if kw in text)
    if inline_matches > 0:
        scores["inline_formatting"] = min(1.0, 0.5 + inline_matches * 0.15)
        scores["image_reference"] = 0.0  # RTE/cursor issues are NOT media

    table_content_matches = sum(1 for kw in TABLE_CONTENT_KEYWORDS if kw in text)
    if table_content_matches > 0:
        scores["table_content"] = min(1.0, 0.4 + table_content_matches * 0.2)

    experience_league_matches = sum(1 for kw in EXPERIENCE_LEAGUE_KEYWORDS if kw in text)
    if experience_league_matches > 0:
        scores["experience_league"] = min(1.0, 0.35 + experience_league_matches * 0.15)

    metadata_matches = sum(1 for kw in METADATA_KEYWORDS if kw in text)
    if metadata_matches > 0:
        scores["metadata"] = min(1.0, 0.35 + metadata_matches * 0.15)

    task_content_matches = sum(1 for kw in TASK_CONTENT_KEYWORDS if kw in text)
    if task_content_matches > 0:
        scores["task_content"] = min(1.0, 0.35 + task_content_matches * 0.15)

    reference_content_matches = sum(1 for kw in REFERENCE_CONTENT_KEYWORDS if kw in text)
    if reference_content_matches > 0:
        scores["reference_content"] = min(1.0, 0.35 + reference_content_matches * 0.15)

    _apply_routing_override_boosts(text, scores)

    if max(scores.values()) == 0:
        scores["keyref"] = 0.1

    logger.debug_structured(
        "Signal priors computed",
        extra_fields={"scores": {k: round(v, 2) for k, v in scores.items() if v > 0}},
    )
    return scores


def merge_priors_with_llm(
    priors: dict[str, float],
    llm_scores: dict[str, float],
    prior_weight: float = 0.4,
) -> dict[str, float]:
    """
    Merge signal priors with LLM classification scores.
    prior_weight: weight for priors (1 - prior_weight for LLM).
    """
    merged: dict[str, float] = {}
    all_keys = set(priors.keys()) | set(llm_scores.keys())
    for k in all_keys:
        p = priors.get(k, 0.0)
        l = llm_scores.get(k, 0.0)
        merged[k] = prior_weight * p + (1 - prior_weight) * l
    return merged
