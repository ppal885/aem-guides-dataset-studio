"""
Recipe scoring and routing for DITA dataset generation.

Input: normalized Jira evidence.
Output: feature_scores, selected_feature, pattern_scores, selected_pattern,
        selected_recipe, cross_feature_blocked, assumptions, unknowns.

Rules:
- Key/keyref/keydef/duplicate key/nested keymap/map hierarchy -> heavily prefer keyref
- Reject generic xref recipe for keyref issue
- Do not mix conref/xref/ditaval unless explicitly mentioned
- Deterministic code routing after classification
"""
import re
from typing import Any, Optional

from app.core.schemas_pipeline import IssueEvidence, RecipeScoringResult
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)


def load_routing_overrides() -> dict[str, Any]:
    """Load routing overrides from feedback (jira_evidence_keywords, deprioritize_for_evidence)."""
    from app.services.feedback_aggregation_service import load_routing_overrides as _load
    return _load()

# --- Feature keyword groups (boost score when evidence contains these) ---
KEYREF_KEYWORDS = [
    "key", "keyref", "keydef", "keyscope", "key scope",
    "duplicate key", "duplicate keys", "nested keymap", "nested keydef",
    "map hierarchy", "key resolution", "unresolved key",
    "keydef chain", "key shadow", "scoped keys", "keymap",
    "nested key resolution", "nested keydef chain", "outer map intermediate keymap",
    "keyword topic source", "recursive key loading", "web editor nested keys",
    "dita-ot resolves correctly", "web editor author preview does not",
    "context map", "intermediate map workaround",
]
XREF_KEYWORDS = [
    "xref", "href", "cross reference", "cross-reference", "external link",
    "link to topic", "link to section", "broken href", "fragment",
]
CONREF_KEYWORDS = [
    "conref", "conkeyref", "content reuse", "reuse", "conrefend",
    "cyclic", "duplicate id", "duplicate ID", "false duplicate",
    "conrefend cyclic", "guides web editor",
]
DITAVAL_KEYWORDS = [
    "ditaval", "audience", "platform", "product", "profiling",
    "conditional", "filter", "attribute filtering",
]
MAP_HIERARCHY_KEYWORDS = [
    "mapref", "map ref", "map cycle", "cyclic map", "circular map",
    "map cyclic", "mapref cycle", "map references map",
    "topichead", "topic head", "output pages under topichead", "pages under topichead",
    "output under topichead", "toc under topichead", "table of contents",
    "topicgroup", "topic group", "grouping topicrefs",
    "reltable", "relationship table", "relrow", "relcell",
]
STRESS_DATASET_KEYWORDS = [
    "large topic", "heavy topic", "6000 line", "huge topic", "massive topic",
    "single topic", "one topic", "bulky topic", "save load stress", "author loading",
    "source view slow", "profiling", "conditional rendering", "filtering problem",
    "audience platform otherprops", "audience/platform/otherprops", "stress test",
    "performance test", "performance issue", "filtering test", "rendering test",
    "conditional processing", "heavy conditional", "editor rendering", "indexing", "validation",
]
TABLE_CONTENT_KEYWORDS = [
    "table width", "table widths", "colwidth", "colspec", "column width",
    "table column", "table formatting", "table display", "table layout",
    "tgroup", "colsep", "rowsep", "table frame", "table rendering",
]
EXPERIENCE_LEAGUE_KEYWORDS = [
    "experience league", "scraped content", "authentic documentation",
    "aem guides docs", "aem guides documentation", "experience league content",
    "convert docs to dita", "doc to dita", "documentation to dita",
    "scraped docs", "web docs to dita", "html to dita",
]
GLOSSARY_KEYWORDS = [
    "glossary", "glossentry", "glossterm", "abbreviated-form",
    "glossary resolution", "term definition", "term reference",
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
INLINE_FORMATTING_KEYWORDS = [
    "cursor", "arrow key", "arrow keys", "keyboard navigation",
    "rich text editor", "rte", "inline tag", "italic tag", "bold tag",
    "opening italic tag", "inline formatting", "nested tag", "editor behavior",
]
# DITA constructs not covered by recipe catalog - trigger LLM DITA generator fallback
# topicgroup removed: now has deterministic routing via maps.topicgroup_basic/nested
NOVEL_CONSTRUCT_KEYWORDS = [
    "topicset", "topic set", "navref", "nav ref",
    "foreign", "foreign element", "topicmeta", "anchor", "anchorref",
    "chunk", "searchtitle",
    "bookmap", "book map", "bookmeta", "book meta",
]


def evidence_mentions_novel_construct(evidence_text: str) -> bool:
    """Return True if evidence mentions DITA constructs not covered by recipes."""
    if not evidence_text or not isinstance(evidence_text, str):
        return False
    text_lower = evidence_text.lower()
    return any(kw in text_lower for kw in NOVEL_CONSTRUCT_KEYWORDS)


# Default feature set for scoring
ALL_FEATURES = ["keyref", "xref", "conref", "ditaval", "metadata", "map_hierarchy", "publishing", "stress_dataset", "image_reference", "inline_formatting", "table_content", "experience_league", "glossary", "task_content", "reference_content"]

# Pattern sets per feature (for pattern scoring)
KEYREF_PATTERNS = [
    "basic_key_resolution",
    "duplicate_keys_same_map",
    "duplicate_keys_sibling_submaps",
    "duplicate_keys_nested_submap",
    "key_scope_shadowing",
    "unresolved_key",
    "key_to_external_resource",
    "key_to_image",
    "key_to_keyword",
    "map_hierarchy_key_resolution",
    "nested_keydef_chain_map_to_map_to_topic",
]
XREF_PATTERNS = [
    "xref_internal_topic",
    "xref_section_target",
    "xref_external_resource",
    "xref_self_reference",
]
CONREF_PATTERNS = ["conref_basic", "conrefend_range", "conrefend_cyclic_duplicate_id", "conref_title"]
CONREF_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "conrefend_cyclic_duplicate_id": [
        "conrefend", "cyclic", "duplicate id", "duplicate ID",
        "false duplicate", "Guides Web Editor", "conrefend cyclic",
    ],
    "conref_title": [
        "conref in title", "title conref", "content reuse in title",
        "reusable title", "variable title",
    ],
}
DITAVAL_PATTERNS = ["ditaval_profile_filtering", "ditaval_platform_filter"]
DITAVAL_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "ditaval_profile_filtering": [
        "ditaval", "audience", "product", "profiling", "attribute filtering",
    ],
    "ditaval_platform_filter": [
        "platform", "platform-specific", "windows", "linux", "platform filter",
    ],
}
MAP_HIERARCHY_PATTERNS = [
    "map_cyclic", "topichead_output", "topicgroup_output", "topicgroup_nested",
    "mapref_output", "reltable_output",
]
MAP_HIERARCHY_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "map_cyclic": [
        "map cyclic", "mapref cycle", "circular map", "map references map",
        "cyclic mapref", "map a map b",
    ],
    "topichead_output": [
        "topichead", "topic head", "output pages under topichead", "pages under topichead",
        "output under topichead", "toc under topichead", "not getting opened", "not opened",
    ],
    "topicgroup_output": [
        "topicgroup", "topic group", "grouping topicrefs", "flat topicrefs",
    ],
    "topicgroup_nested": [
        "nested topicgroup", "hierarchical grouping", "topicgroup nested",
    ],
    "mapref_output": [
        "mapref", "submap", "nested map", "map ref", "map references",
    ],
    "reltable_output": [
        "reltable", "relationship table", "relrow", "relcell", "next previous related",
    ],
}
STRESS_DATASET_PATTERNS = ["heavy_conditional_topic_6000_lines"]
STRESS_DATASET_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "heavy_conditional_topic_6000_lines": [
        "large topic", "heavy topic", "single topic", "6000 line", "huge topic", "massive topic",
        "profiling", "audience", "platform", "otherprops", "filtering",
        "stress test", "stress testing", "filtering test", "rendering test", "performance test",
        "conditional", "performance", "save load", "heavy conditional",
    ],
}
IMAGE_REFERENCE_PATTERNS = ["media_rich", "image_basic", "image_with_alt"]
IMAGE_REFERENCE_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "media_rich": [
        "media", "images", "videos", "embed", "placeholder", "media operations",
    ],
    "image_basic": ["image", "figure", "asset"],
    "image_with_alt": ["alt text", "accessibility", "alt attribute"],
}
INLINE_FORMATTING_PATTERNS = ["rte_inline_tags"]
INLINE_FORMATTING_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "rte_inline_tags": [
        "cursor", "arrow key", "arrow keys", "keyboard navigation",
        "rich text editor", "rte", "italic tag", "bold tag", "inline tag",
        "<i>", "<b>", "<u>", "<li>", "nested tag", "editor behavior",
    ],
}
TABLE_CONTENT_PATTERNS = ["table_width_formatting"]
TABLE_CONTENT_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "table_width_formatting": [
        "table width", "table widths", "colwidth", "colspec", "column width",
        "table column", "table formatting", "table display", "table layout",
        "width %", "width px", "widths %", "widths px",  # e.g. "widths like 50% or 100px"
    ],
}
EXPERIENCE_LEAGUE_PATTERNS = ["doc_to_dita"]
EXPERIENCE_LEAGUE_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "doc_to_dita": [
        "experience league", "scraped content", "authentic documentation",
        "doc to dita", "documentation to dita",
    ],
}
METADATA_PATTERNS = ["subject_scheme", "topicmeta_keywords"]
TASK_CONTENT_PATTERNS = ["task_procedure"]
TASK_CONTENT_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "task_procedure": [
        "steps", "step", "cmd", "task", "taskbody", "prereq", "result",
        "procedure", "how-to", "how to", "substep", "context", "stepresult",
        "choicetable", "choice table", "chrow", "choption", "chdesc",
    ],
}
REFERENCE_CONTENT_PATTERNS = ["reference_properties", "reference_choicetable"]
REFERENCE_CONTENT_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "reference_properties": [
        "refbody", "refsyn", "section", "sectionref", "properties", "property",
        "reference topic", "api reference", "syntax reference", "definition",
    ],
    "reference_choicetable": [
        "choicetable", "choice table", "chrow", "choption", "chdesc",
    ],
}
METADATA_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "subject_scheme": [
        "subject scheme", "subjectdef", "enumerationdef", "subjectScheme",
        "controlled values", "audience validation", "attribute validation",
    ],
    "topicmeta_keywords": [
        "topicmeta", "keywords", "indexterm", "metadata",
    ],
}

# Pattern -> keyword hints for scoring
KEYREF_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "basic_key_resolution": ["keydef", "keyref", "basic", "resolution"],
    "duplicate_keys_same_map": ["duplicate key", "same map", "same scope"],
    "duplicate_keys_sibling_submaps": ["sibling", "submap", "duplicate", "different scope"],
    "duplicate_keys_nested_submap": ["nested", "nested keydef", "map map topic"],
    "key_scope_shadowing": ["keyscope", "shadow", "scope shadow"],
    "unresolved_key": ["unresolved", "not resolved", "fails to resolve"],
    "key_to_external_resource": ["external", "pdf", "resource", "format"],
    "key_to_image": ["image", "keyref image"],
    "key_to_keyword": ["keyword", "productname", "versionstring"],
    "map_hierarchy_key_resolution": ["map hierarchy", "nested map", "map a map b", "recursive"],
    "nested_keydef_chain_map_to_map_to_topic": [
        "nested keydef chain", "outer map intermediate keymap keyword topic source",
        "DITA-OT resolves correctly", "Web Editor author preview does not",
        "nested key resolution", "keydef chain", "map A map B topic C",
        "keys resolve only when intermediate keymap opened", "web editor nested keys",
        "author preview unresolved keyref dita-ot correct", "recursive key loading",
        "parity editor DITA-OT", "intermediate map workaround",
    ],
}

# Deterministic routing: (feature, pattern) -> recipe_id
ROUTE_TABLE: dict[tuple[str, str], str] = {
    # keyref family
    ("keyref", "basic_key_resolution"): "keys.keydef_basic",
    ("keyref", "duplicate_keys_same_map"): "keys.duplicate_key_same_scope_negative",
    ("keyref", "duplicate_keys_sibling_submaps"): "keys.duplicate_key_different_scope",
    ("keyref", "duplicate_keys_nested_submap"): "keys.keyscope_nested_resolution",
    ("keyref", "key_scope_shadowing"): "keys.keyscope_shadow_2level",
    ("keyref", "unresolved_key"): "keys.keydef_basic",  # minimal repro for unresolved
    ("keyref", "key_to_external_resource"): "keys.external_resource_keydef",
    ("keyref", "key_to_image"): "keys.keyref_image",
    ("keyref", "key_to_keyword"): "nested_keydef_map_map_topic",
    ("keyref", "map_hierarchy_key_resolution"): "nested_keydef_map_map_topic",
    ("keyref", "nested_keydef_chain_map_to_map_to_topic"): "keyref_nested_keydef_chain_map_to_map_to_topic",
    # xref family
    ("xref", "xref_internal_topic"): "xref_topic_basic",
    ("xref", "xref_section_target"): "xref_section_target",
    ("xref", "xref_external_resource"): "xref_external_pdf",
    ("xref", "xref_self_reference"): "xref_self_section",
    # conref family
    ("conref", "conref_basic"): "conref_pack",
    ("conref", "conrefend_range"): "conref_pack",
    ("conref", "conrefend_cyclic_duplicate_id"): "conrefend_cyclic_duplicate_id",
    ("conref", "conref_title"): "dita_conref_title_dataset_recipe",
    # ditaval family
    ("ditaval", "ditaval_profile_filtering"): "conditionals.audience_filter",
    ("ditaval", "ditaval_platform_filter"): "conditionals.platform_filter",
    # map_hierarchy family
    ("map_hierarchy", "map_cyclic"): "map_cyclic",
    ("map_hierarchy", "topichead_output"): "maps.topichead_basic",
    ("map_hierarchy", "topicgroup_output"): "maps.topicgroup_basic",
    ("map_hierarchy", "topicgroup_nested"): "maps.topicgroup_nested",
    ("map_hierarchy", "mapref_output"): "maps.mapref_basic",
    ("map_hierarchy", "reltable_output"): "maps.reltable_basic",
    # stress_dataset family
    ("stress_dataset", "heavy_conditional_topic_6000_lines"): "heavy_conditional_topic_6000_lines",
    # image_reference family
    ("image_reference", "media_rich"): "media_rich_content",
    ("image_reference", "image_basic"): "assets.image_basic",
    ("image_reference", "image_with_alt"): "assets.image_with_alt",
    # inline_formatting family (RTE, cursor, b/i/u tags)
    ("inline_formatting", "rte_inline_tags"): "inline_formatting_nested",
    # table_content family (table width, colwidth, formatting - NOT xref to table)
    ("table_content", "table_width_formatting"): "heavy_topics_tables_codeblocks",
    # experience_league family (scraped Experience League docs to DITA)
    ("experience_league", "doc_to_dita"): "experience_league_to_dita",
    # glossary family
    ("glossary", "glossary_basic"): "glossary.glossentry_basic",
    ("glossary", "term_reference"): "glossary.term_reference_basic",
    # metadata family (subject scheme, topicmeta)
    ("metadata", "subject_scheme"): "dita_subject_scheme_dataset_recipe",
    ("metadata", "topicmeta_keywords"): "metadata.topicmeta_keywords_indexterm",
    # task_content family (steps, cmd, task - procedural DITA)
    ("task_content", "task_procedure"): "task_topics",
    # reference_content family (refbody, refsyn, section, choicetable - reference DITA)
    ("reference_content", "reference_properties"): "reference_topics",
    ("reference_content", "reference_choicetable"): "reference_topics",
}

# Recipe ID -> mechanism family (for anti-blending validation)
RECIPE_FAMILY: dict[str, str] = {}
for (feat, _), rid in ROUTE_TABLE.items():
    RECIPE_FAMILY[rid] = feat

# Generic xref recipes that must be rejected for keyref issues
GENERIC_XREF_RECIPES = frozenset({
    "xref_topic_basic", "xref_section_target", "xref_list_item_target",
    "xref_figure_target", "xref_table_target", "xref_self_section",
})


def _tokenize_lower(text: str) -> set[str]:
    """Extract lowercase tokens (words and bigrams) for matching."""
    if not text:
        return set()
    t = re.sub(r"[^\w\s-]", " ", str(text).lower())
    words = {w for w in t.split() if len(w) >= 2}
    # Add bigrams for phrases like "duplicate key"
    parts = t.split()
    for i in range(len(parts) - 1):
        bigram = f"{parts[i]} {parts[i+1]}"
        if len(bigram) >= 4:
            words.add(bigram)
    return words


def compute_feature_scores(evidence: IssueEvidence) -> dict[str, float]:
    """
    Compute feature scores from evidence keywords. Heavily prefer keyref when
    key/keyref/keydef/duplicate key/nested keymap/map hierarchy present.
    """
    text = (evidence.raw_text or "") + " " + (evidence.summary or "") + " " + (evidence.description or "")
    tokens = _tokenize_lower(text)
    scores: dict[str, float] = {f: 0.0 for f in ALL_FEATURES}

    # Keyref: strong boost
    keyref_matches = sum(1 for kw in KEYREF_KEYWORDS if kw in text.lower() or kw.replace(" ", "") in "".join(tokens))
    if keyref_matches > 0:
        scores["keyref"] = min(1.0, 0.3 + keyref_matches * 0.2)
        scores["map_hierarchy"] = max(scores["map_hierarchy"], 0.4 if "map hierarchy" in text.lower() or "nested" in text.lower() else 0.0)

    # Xref
    xref_matches = sum(1 for kw in XREF_KEYWORDS if kw in text.lower())
    if xref_matches > 0 and scores["keyref"] < 0.5:
        scores["xref"] = min(1.0, 0.2 + xref_matches * 0.15)

    # Conref (strong boost when conrefend/cyclic/duplicate-id present)
    conref_matches = sum(1 for kw in CONREF_KEYWORDS if kw in text.lower())
    if conref_matches > 0:
        conref_boost = 0.35 if any(k in text.lower() for k in ("conrefend", "cyclic", "duplicate id", "duplicate ID")) else 0.2
        scores["conref"] = min(1.0, 0.25 + conref_matches * conref_boost)

    # Glossary
    glossary_matches = sum(1 for kw in GLOSSARY_KEYWORDS if kw in text.lower())
    if glossary_matches > 0:
        scores["glossary"] = min(1.0, 0.35 + glossary_matches * 0.15)

    # Ditaval
    ditaval_matches = sum(1 for kw in DITAVAL_KEYWORDS if kw in text.lower())
    if ditaval_matches > 0:
        scores["ditaval"] = min(1.0, 0.2 + ditaval_matches * 0.15)

    # Map hierarchy (mapref cycle, topichead, etc.)
    map_hierarchy_matches = sum(1 for kw in MAP_HIERARCHY_KEYWORDS if kw in text.lower())
    if map_hierarchy_matches > 0:
        scores["map_hierarchy"] = min(1.0, 0.3 + map_hierarchy_matches * 0.2)
    # Topichead: strong boost for map_hierarchy, suppress ditaval (topichead is NOT ditaval)
    if "topichead" in text.lower() or "topic head" in text.lower():
        scores["map_hierarchy"] = max(scores.get("map_hierarchy", 0), 0.7)
        scores["ditaval"] = 0.0

    # Stress dataset (heavy conditional topic)
    stress_matches = sum(1 for kw in STRESS_DATASET_KEYWORDS if kw in text.lower())
    if stress_matches > 0:
        scores["stress_dataset"] = min(1.0, 0.35 + stress_matches * 0.15)

    # Image reference (media, images, videos)
    image_ref_keywords = ["image", "images", "video", "videos", "media", "media operations", "asset", "assets", "figure", "alt text"]
    image_ref_matches = sum(1 for kw in image_ref_keywords if kw in text.lower())
    if image_ref_matches > 0:
        scores["image_reference"] = min(1.0, 0.35 + image_ref_matches * 0.15)

    # Table content (table width, colwidth, formatting - NOT xref to table)
    table_content_matches = sum(1 for kw in TABLE_CONTENT_KEYWORDS if kw in text.lower())
    if table_content_matches > 0:
        scores["table_content"] = min(1.0, 0.4 + table_content_matches * 0.2)

    # Experience League (scraped docs to DITA)
    experience_league_matches = sum(1 for kw in EXPERIENCE_LEAGUE_KEYWORDS if kw in text.lower())
    if experience_league_matches > 0:
        scores["experience_league"] = min(1.0, 0.35 + experience_league_matches * 0.15)

    # Metadata (subject scheme, topicmeta, keywords, indexterm)
    metadata_matches = sum(1 for kw in METADATA_KEYWORDS if kw in text.lower())
    if metadata_matches > 0:
        scores["metadata"] = min(1.0, 0.35 + metadata_matches * 0.15)

    # Task content (steps, cmd, task, procedure - DITA task topics)
    task_content_matches = sum(1 for kw in TASK_CONTENT_KEYWORDS if kw in text.lower())
    if task_content_matches > 0:
        scores["task_content"] = min(1.0, 0.35 + task_content_matches * 0.15)

    # Reference content (refbody, refsyn, section, choicetable - DITA reference topics)
    reference_content_matches = sum(1 for kw in REFERENCE_CONTENT_KEYWORDS if kw in text.lower())
    if reference_content_matches > 0:
        scores["reference_content"] = min(1.0, 0.35 + reference_content_matches * 0.15)

    # Inline formatting (RTE, cursor, b/i/u tags) - suppress image_reference when present
    inline_formatting_matches = sum(1 for kw in INLINE_FORMATTING_KEYWORDS if kw in text.lower())
    if inline_formatting_matches > 0:
        scores["inline_formatting"] = min(1.0, 0.5 + inline_formatting_matches * 0.15)
        scores["image_reference"] = 0.0  # RTE/cursor issues are NOT media

    # Normalize: ensure at least one non-zero
    if max(scores.values()) == 0:
        scores["keyref"] = 0.1  # default fallback for unknown
    return scores


def select_feature(scores: dict[str, float]) -> tuple[str, list[str]]:
    """
    Select the most specific primary feature. Prefer keyref when score is high.
    Returns (selected_feature, rejected_features).
    """
    sorted_features = sorted(scores.items(), key=lambda x: -x[1])
    if not sorted_features:
        return "keyref", []

    selected = sorted_features[0][0]
    threshold = 0.25
    rejected = [f for f, s in sorted_features[1:] if s >= threshold]

    # Rule: conref strong (conrefend/cyclic/duplicate-id) → prefer conref over keyref
    if scores.get("conref", 0) >= 0.5 and scores.get("conref", 0) >= scores.get("keyref", 0):
        selected = "conref"
        rejected = [f for f in ALL_FEATURES if f != "conref" and scores.get(f, 0) > 0]
    # Rule: glossary strong → prefer glossary
    elif scores.get("glossary", 0) >= 0.5 and scores.get("glossary", 0) >= scores.get("keyref", 0):
        selected = "glossary"
        rejected = [f for f in ALL_FEATURES if f != "glossary" and scores.get(f, 0) > 0]
    # Rule: experience_league strong → prefer experience_league
    elif scores.get("experience_league", 0) >= 0.5 and scores.get("experience_league", 0) >= scores.get("keyref", 0):
        selected = "experience_league"
        rejected = [f for f in ALL_FEATURES if f != "experience_league" and scores.get(f, 0) > 0]
    # Rule: metadata strong (subject scheme, topicmeta) → prefer metadata
    elif scores.get("metadata", 0) >= 0.5 and scores.get("metadata", 0) >= scores.get("keyref", 0):
        selected = "metadata"
        rejected = [f for f in ALL_FEATURES if f != "metadata" and scores.get(f, 0) > 0]
    # Rule: task_content strong (steps, cmd, task) → prefer task_content
    elif scores.get("task_content", 0) >= 0.5 and scores.get("task_content", 0) >= scores.get("keyref", 0):
        selected = "task_content"
        rejected = [f for f in ALL_FEATURES if f != "task_content" and scores.get(f, 0) > 0]
    # Rule: reference_content strong (refbody, refsyn, section, choicetable) → prefer reference_content
    elif scores.get("reference_content", 0) >= 0.5 and scores.get("reference_content", 0) >= scores.get("keyref", 0):
        selected = "reference_content"
        rejected = [f for f in ALL_FEATURES if f != "reference_content" and scores.get(f, 0) > 0]
    # Rule: inline_formatting strong (RTE, cursor, b/i/u tags) → prefer inline_formatting
    elif scores.get("inline_formatting", 0) >= 0.5 and scores.get("inline_formatting", 0) >= scores.get("keyref", 0):
        selected = "inline_formatting"
        rejected = [f for f in ALL_FEATURES if f != "inline_formatting" and scores.get(f, 0) > 0]
    # Rule: if keyref is top and score > 0.3, always choose keyref
    elif scores.get("keyref", 0) >= 0.3 and scores.get("keyref", 0) >= scores.get("xref", 0):
        selected = "keyref"
        rejected = [f for f in ALL_FEATURES if f != "keyref" and scores.get(f, 0) > 0]

    return selected, rejected


def compute_pattern_scores(evidence: IssueEvidence, selected_feature: str) -> dict[str, float]:
    """Compute pattern scores within the selected feature."""
    text = (evidence.raw_text or "").lower()
    tokens = _tokenize_lower(text)

    if selected_feature == "keyref":
        patterns = KEYREF_PATTERNS
        keyword_map = KEYREF_PATTERN_KEYWORDS
    elif selected_feature == "xref":
        patterns = XREF_PATTERNS
        keyword_map = {}
    elif selected_feature == "conref":
        patterns = CONREF_PATTERNS
        keyword_map = CONREF_PATTERN_KEYWORDS
    elif selected_feature == "ditaval":
        patterns = DITAVAL_PATTERNS
        keyword_map = DITAVAL_PATTERN_KEYWORDS
    elif selected_feature == "map_hierarchy":
        patterns = MAP_HIERARCHY_PATTERNS
        keyword_map = MAP_HIERARCHY_PATTERN_KEYWORDS
    elif selected_feature == "stress_dataset":
        patterns = STRESS_DATASET_PATTERNS
        keyword_map = STRESS_DATASET_PATTERN_KEYWORDS
    elif selected_feature == "image_reference":
        patterns = IMAGE_REFERENCE_PATTERNS
        keyword_map = IMAGE_REFERENCE_PATTERN_KEYWORDS
    elif selected_feature == "inline_formatting":
        patterns = INLINE_FORMATTING_PATTERNS
        keyword_map = INLINE_FORMATTING_PATTERN_KEYWORDS
    elif selected_feature == "table_content":
        patterns = TABLE_CONTENT_PATTERNS
        keyword_map = TABLE_CONTENT_PATTERN_KEYWORDS
    elif selected_feature == "experience_league":
        patterns = EXPERIENCE_LEAGUE_PATTERNS
        keyword_map = EXPERIENCE_LEAGUE_PATTERN_KEYWORDS
    elif selected_feature == "metadata":
        patterns = METADATA_PATTERNS
        keyword_map = METADATA_PATTERN_KEYWORDS
    elif selected_feature == "task_content":
        patterns = TASK_CONTENT_PATTERNS
        keyword_map = TASK_CONTENT_PATTERN_KEYWORDS
    elif selected_feature == "reference_content":
        patterns = REFERENCE_CONTENT_PATTERNS
        keyword_map = REFERENCE_CONTENT_PATTERN_KEYWORDS
    elif selected_feature == "glossary":
        patterns = ["glossary_basic", "term_reference"]
        keyword_map = {
            "glossary_basic": ["glossentry", "glossary", "term definition"],
            "term_reference": ["term reference", "abbreviated-form", "glossary link", "glossary resolution"],
        }
    else:
        return {"basic": 0.5}

    scores: dict[str, float] = {}
    for p in patterns:
        hints = keyword_map.get(p, [])
        score = 0.1
        for h in hints:
            if h in text or h.replace(" ", "") in "".join(tokens):
                score += 0.25
        scores[p] = min(1.0, score)

    if max(scores.values()) == 0.1:
        scores[patterns[0]] = 0.5
    return scores


def select_pattern(scores: dict[str, float]) -> tuple[str, list[str]]:
    """Select the highest-scoring pattern. Returns (selected_pattern, rejected_patterns)."""
    if not scores:
        return "basic_key_resolution", []
    sorted_pats = sorted(scores.items(), key=lambda x: -x[1])
    selected = sorted_pats[0][0]
    rejected = [p for p, s in sorted_pats[1:] if s >= 0.2]
    return selected, rejected


def route_recipe(selected_feature: str, selected_pattern: str) -> tuple[str, str]:
    """
    Deterministic routing: (feature, pattern) -> recipe_id.
    Returns (recipe_id, route_reason).
    """
    key = (selected_feature, selected_pattern)
    if key in ROUTE_TABLE:
        return ROUTE_TABLE[key], f"routed:{selected_feature}+{selected_pattern}"

    # Fallback: first recipe for feature
    for (f, p), rid in ROUTE_TABLE.items():
        if f == selected_feature:
            return rid, f"fallback:{selected_feature} (pattern {selected_pattern} not in table)"
    return "keys.keydef_basic", "default:keyref basic"


def validate_no_cross_feature_blend(
    selected_feature: str,
    selected_recipe: str,
) -> tuple[bool, bool]:
    """
    Validate that recipe family matches selected feature. Reject generic xref for keyref issue.
    Returns (is_valid, cross_feature_blocked).
    """
    recipe_family = RECIPE_FAMILY.get(selected_recipe, "")
    cross_feature_blocked = False

    if selected_feature == "keyref":
        if selected_recipe in GENERIC_XREF_RECIPES or (recipe_family and recipe_family == "xref"):
            logger.info_structured(
                "Cross-feature block: rejecting xref recipe for keyref issue",
                extra_fields={"selected_recipe": selected_recipe, "selected_feature": selected_feature},
            )
            return False, True
        cross_feature_blocked = True

    if recipe_family and recipe_family != selected_feature:
        logger.info_structured(
            "Recipe family mismatch",
            extra_fields={
                "selected_feature": selected_feature,
                "selected_recipe": selected_recipe,
                "recipe_family": recipe_family,
            },
        )
        return False, True

    return True, cross_feature_blocked


def score_and_route(evidence: IssueEvidence) -> RecipeScoringResult:
    """
    Main entry: score features, select feature, score patterns, select pattern,
    route to recipe, validate. Returns RecipeScoringResult.
    """
    assumptions: list[str] = []
    unknowns: list[str] = []

    feature_scores = compute_feature_scores(evidence)
    selected_feature, rejected_features = select_feature(feature_scores)
    logger.debug_structured(
        "Feature scoring",
        extra_fields={
            "feature_scores": feature_scores,
            "selected_feature": selected_feature,
            "rejected_features": rejected_features,
        },
    )

    pattern_scores = compute_pattern_scores(evidence, selected_feature)
    selected_pattern, rejected_patterns = select_pattern(pattern_scores)
    logger.debug_structured(
        "Pattern scoring",
        extra_fields={
            "selected_feature": selected_feature,
            "pattern_scores": pattern_scores,
            "selected_pattern": selected_pattern,
            "rejected_patterns": rejected_patterns,
        },
    )

    selected_recipe, route_reason = route_recipe(selected_feature, selected_pattern)
    is_valid, cross_feature_blocked = validate_no_cross_feature_blend(selected_feature, selected_recipe)

    if not is_valid:
        assumptions.append("Recipe family mismatch; falling back to keyref basic")
        selected_recipe = "keys.keydef_basic"
        route_reason = "fallback:validation_failed"

    logger.info_structured(
        "Recipe routing",
        extra_fields={
            "selected_feature": selected_feature,
            "selected_pattern": selected_pattern,
            "selected_recipe": selected_recipe,
            "route_reason": route_reason,
            "cross_feature_blocked": cross_feature_blocked,
        },
    )

    return RecipeScoringResult(
        feature_scores=feature_scores,
        selected_feature=selected_feature,
        pattern_scores=pattern_scores,
        selected_pattern=selected_pattern,
        selected_recipe=selected_recipe,
        cross_feature_blocked=cross_feature_blocked,
        assumptions=assumptions,
        unknowns=unknowns,
    )
