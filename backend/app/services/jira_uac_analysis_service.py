"""Deterministic clause-level analysis for historical Jira acceptance criteria."""

from __future__ import annotations

import hashlib
import html
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any


UAC_SCHEMA_VERSION = "historical-uac-v1"
UAC_ANALYSIS_METHOD = "deterministic-rules"
UAC_CONTRACT_CHUNK_TYPE = "historical_uac_contract_chunk"
UAC_CLAUSE_CHUNK_TYPE = "historical_uac_clause_chunk"
UAC_OUT_OF_SCOPE_CHUNK_TYPE = "historical_uac_out_of_scope_chunk"
UAC_REFERENCE_CHUNK_TYPE = "historical_uac_reference_chunk"
UAC_CONTEXT_CHUNK_TYPE = "historical_uac_context_chunk"
UAC_DIMENSION_CHUNK_TYPE = "historical_uac_dimension_chunk"
HISTORICAL_UAC_CHUNK_TYPES: frozenset[str] = frozenset(
    {
        UAC_CONTRACT_CHUNK_TYPE,
        UAC_CLAUSE_CHUNK_TYPE,
        UAC_OUT_OF_SCOPE_CHUNK_TYPE,
        UAC_REFERENCE_CHUNK_TYPE,
        UAC_CONTEXT_CHUNK_TYPE,
        UAC_DIMENSION_CHUNK_TYPE,
    }
)

_FIXED_OUTCOMES = {"fixed", "done", "complete", "partially complete", "documentation complete"}
_CAUTION_OUTCOMES = {
    "duplicate",
    "won't do",
    "won't fix",
    "not a bug",
    "working as designed",
    "cannot reproduce",
    "rejected",
    "deferred",
    "canceled",
    "no longer applies",
    "question answered",
    "transfer to product",
}
_CLOSED_STATUSES = {"closed", "resolved", "done", "complete", "completed"}
_OPEN_RESOLUTION_VALUES = {"", "none", "null", "open", "unresolved", "unspecified"}
_ACCEPTED_UAC_LABELS = {"uacdone", "uacapproved", "uacaccepted", "uacverified"}
_OUT_OF_SCOPE_RE = re.compile(
    r"\b(?:out\s+of\s+scope|outside\s+(?:the\s+)?scope|not\s+in\s+scope|not\s+needed|"
    r"not\s+part\s+of\s+(?:this|the)\s+(?:ticket|requirement))\b",
    re.I,
)
_OUT_OF_SCOPE_HEADER_RE = re.compile(r"^\s*(?:out\s+of\s+scope|excluded|exclusions?)\s*:?[\s-]*(.*)$", re.I)
_IN_SCOPE_HEADER_RE = re.compile(r"^\s*(?:in\s+scope|scope)\s*:?[\s-]*(.*)$", re.I)
_ACCEPTANCE_HEADER_RE = re.compile(
    r"^\s*(?:acceptance\s+criteri(?:a|on)|uac)[\s:\u2013\u2014-]*$",
    re.I,
)
_CONTEXT_HEADER_RE = re.compile(
    r"^\s*(?:problem\s+statement|business\s+impact|background|issue\s+description|description)[\s:\u2013\u2014-]*$",
    re.I,
)
_HEADING_RE = re.compile(
    r"^\s*(?:capabilities?\s+needed|catalyst|notes?)[\s:\u2013\u2014-]*$",
    re.I,
)
_MATRIX_HEADER_RE = re.compile(r"^\s*following\s+validations?\s+to\s+work\s+as\s+is\s*:\s*$", re.I)
_ROLLOUT_CONTEXT_RE = re.compile(r"^\s*we\s+will\s+be\s+providing\s+(?:a\s+)?fix\s+in\b", re.I)
_PENDING_LINKED_SCOPE_RE = re.compile(
    r"\b(?:more\s+information\s+awaited|scope\s+will\s+be\s+discussed)\b",
    re.I,
)
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+\u2022\u25cf\u25aa]+|\d{1,3}[.)]|[A-Za-z][.)])\s+")
_NUMBERED_LIST_PREFIX_RE = re.compile(r"^\s*\d{1,3}[.)]\s+")
_NUMBERED_ITEM_RE = re.compile(r"^\s*(\d{1,3})[.)]\s+(.+)$")
_UAC_POINT_RANGE_RE = re.compile(r"\bUAC\s+points?\s+(\d{1,3})\s*[\u2013\u2014-]\s*(\d{1,3})\b", re.I)
_TBD_RE = re.compile(r"\b(?:tbd|to\s+be\s+decided|to\s+be\s+confirmed|unknown|pending\s+confirmation)\b", re.I)
_VAGUE_START_RE = re.compile(r"^\s*(?:check(?:/test)?|test|verify|validate|handle)\b", re.I)
_GENERIC_SUCCESS_RE = re.compile(
    r"\b(?:should\s+(?:also\s+)?work|work(?:s|ing)?\s+(?:fine|properly|correctly|as\s+expected|as\s+is)|"
    r"behave(?:s|d)?\s+correctly|no\s+regression|no\s+changes?\s+(?:in|to)\s+(?:normal\s+)?workflows?)\b",
    re.I,
)
_OUTCOME_RE = re.compile(
    r"\b(?:must|should|will|shall|then|shows?|shown|displays?|displayed|renders?|rendered|"
    r"hidden|retained|remains?|unchanged|updates?|updated|refused|blocked|broken|ignored|not\s+allowed|"
    r"allowed|cannot|resolves?|resolved|populates?|populated|creat(?:e|es|ed)|insert(?:s|ed)?|minted|supported|excluded|first|priority)\b",
    re.I,
)
_PERFORMANCE_METRIC_RE = re.compile(
    r"(?:\bp(?:50|75|90|95|99)\b|\d+(?:\.\d+)?\s*(?:ms|milliseconds?|s|sec(?:onds?)?|minutes?|%|percent))",
    re.I,
)
_PERFORMANCE_WORKLOAD_RE = re.compile(
    r"(?:\d[\d,]*\s*(?:topics?|maps?|pages?|assets?|users?|jobs?|requests?|mb|gb)|"
    r"concurrent|large[-\s](?:map|site|repository|dataset)|warm\s+cache|cold\s+cache)",
    re.I,
)
_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{2,}", re.I)
_JIRA_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b", re.I)
_JIRA_REFERENCE_PREFIX_RE = re.compile(
    r"^\s*(?:mentioned|linked|related|reference(?:d)?|see|covered|more\s+information)\s+(?:with|to|in|by)?\b",
    re.I,
)
_NO_FEATURE_FLAG_RE = re.compile(r"^\s*feature\s+flag\s*[-:]\s*(?:no|none|not\s+required|without)\b", re.I)
_NOT_APPLICABLE_RE = re.compile(r"(?:\bnot\s+applicable\b|(?<![A-Z0-9])N\s*/?\s*A(?![A-Z0-9]))", re.I)
_CONFIGURATION_STATE_PAIR_RE = re.compile(
    r"\b(?:on\s*/\s*off|on\s+and\s+off|enabled\s*/\s*disabled|enabled\s+and\s+disabled)\b",
    re.I,
)
_CONFIGURATION_LIMITATION_RE = re.compile(
    r"\b(?:does\s+not|will\s+not|cannot|unsupported|not\s+supported|only\s+supported|disabled)\b",
    re.I,
)
_CONFIGURATION_STATE_TOKEN_RE = re.compile(
    r"(?:\b(?:enabled|disabled)\b|\b(?:when|if|while|state|switch|dita[-\s]?ot|feature\s+flag)\s+(?:is\s+)?(?:on|off)\b)",
    re.I,
)
_OUTPUT_TARGET_RE = re.compile(
    r"\b(?:native\s+pdf|merged\s*html(?:\.htm)?|mergedpdf\s+html|html5|aem\s+sites?|pdf\s+output|html\s+output|preview|editor)\b",
    re.I,
)
_CRUD_OPERATION_RE = re.compile(
    r"\b(?:create|insert|add|edit|update|delete|remove|copy|paste|cut|undo|redo|save|reopen)\b",
    re.I,
)
_MATHML_COMPLEXITY_RE = re.compile(
    r"\b(?:mfrac|mtable|mrow|msqrt|mroot|mfenced|fraction|matrix|nested|inline|block|superscript|subscript)\b",
    re.I,
)
_COMMENT_SECTION_HEADERS = (
    r"root\s+cause|analysis|qa\s+verification|verification|verified\s+on\s+build|"
    r"before\s+fix|after\s+fix|confirmation\s+needed|automation\s+prs?|expected\s+result|"
    r"actual\s+result|mergedhtml\s+diff|pr|regards|cc"
)
_CAUSAL_EVIDENCE_RE = re.compile(
    r"\b(?:because|caused\s+by|due\s+to|instead\s+of|failed\s+to|did\s+not|"
    r"was\s+dropped\s+when|were\s+dropped\s+when|was\s+not\s+considered|"
    r"were\s+not\s+considered|missing\s+because|root\s+cause)\b",
    re.I,
)
_VERIFICATION_RESULT_RE = re.compile(
    r"\b(?:verified|passed|applied|propagat(?:e|ed|ing)|render(?:s|ed|ing)?|generated|"
    r"retained|preserved|matches?|successful|works?)\b",
    re.I,
)
_UAC_DESCRIPTION_MARKER_RE = re.compile(
    r"(?is)##\s*UAC\s+Criteria\s*\(custom\s+field\)\s*\n(?P<uac>.+)$"
)
_TOKEN_STOP = {
    "applicable",
    "behavior",
    "check",
    "criteria",
    "current",
    "feature",
    "scope",
    "should",
    "not",
    "allowed",
    "and",
    "are",
    "attribute",
    "attributes",
    "current",
    "element",
    "elements",
    "fix",
    "for",
    "from",
    "into",
    "outputclass",
    "sprint",
    "taking",
    "that",
    "the",
    "too",
    "this",
    "ticket",
    "validate",
    "verify",
    "with",
}

_DIMENSION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("performance", re.compile(r"\b(?:performance|latency|response\s+time|throughput|load|scale|concurr|memory|cpu|heap|p95|p99)\b", re.I)),
    ("baseline", re.compile(r"\bbaseline\b", re.I)),
    ("editor_parity", re.compile(r"\b(?:old\s+editor|new\s+editor|both\s+editors?|web\s*editor|ckeditor|markup\s*editor)\b", re.I)),
    ("versioning", re.compile(r"\b(?:version|checkpoint|working\s+copy|purge|rollback|revert)\b", re.I)),
    ("conditions", re.compile(r"\b(?:conditions?|ditaval|conditional)\b", re.I)),
    ("ditavalref", re.compile(r"\bditavalrefs?\b", re.I)),
    ("conditional_preset", re.compile(r"\bconditional\s+presets?\b", re.I)),
    ("references", re.compile(r"\b(?:direct\s+references?|indirect\s+references?|references?|topic-?refs?|href|xref|conref)\b", re.I)),
    ("keys", re.compile(r"\b(?:keys?|keyrefs?|conkeyrefs?|keyscope)\b", re.I)),
    ("ui", re.compile(r"\b(?:preview|switch|toggle|filter\s+panel|dropdown|show\s+diff|loader|button|tab|dialog)\b", re.I)),
    ("state", re.compile(r"\b(?:retain|retained|remain|selected|switching|state|refresh|stale)\b", re.I)),
    ("lifecycle", re.compile(r"\b(?:create|created|delete|deleted|update|updated|move|moved|purge|incremental)\b", re.I)),
    ("configuration", re.compile(r"\b(?:config|configuration|feature\s+flag|preset|argument|metadatalist|uuid\s+property|cq:conf|index)\b", re.I)),
    ("output", re.compile(r"\b(?:native\s+pdf|aem\s+sites?|merged\s*html(?:\.htm)?|html5|pdf|output|publish|publishing)\b", re.I)),
    ("ordering", re.compile(r"\b(?:order|ordering|first|priority|before|after)\b", re.I)),
    ("defaults", re.compile(r"\bdefault\b", re.I)),
    ("parity", re.compile(r"\b(?:same\s+as|replicate|parity|both\s+old\s+and\s+new)\b", re.I)),
    ("security_permissions", re.compile(r"\b(?:role|permission|access|authorization|authentication)\b", re.I)),
    ("automation", re.compile(r"\b(?:automation|automated|test\s+case)\b", re.I)),
    ("feature_flag", re.compile(r"\bfeature\s+flag\b", re.I)),
    ("dita_ot", re.compile(r"\bdita[-\s]?ot\b", re.I)),
    ("native_pdf", re.compile(r"\bnative\s+pdf\b", re.I)),
    ("map_title", re.compile(r"\b(?:bookmap|map)\s+title\b", re.I)),
    ("project_title", re.compile(r"\bproject\s+title\b", re.I)),
    ("topic_title", re.compile(r"\btopic\s+title\b", re.I)),
    ("metadata_title", re.compile(r"\bmetadata\s+title\b", re.I)),
    ("guid_reference", re.compile(r"\b(?:guid|uuid)\b", re.I)),
    ("source_xml", re.compile(r"\bsource\s+xml\b", re.I)),
    ("ditamap", re.compile(r"\bditamap\b", re.I)),
    ("topicref", re.compile(r"\btopic-?ref\b", re.I)),
    ("repository_drag_drop", re.compile(r"\b(?:drag[-\s]?drop|repository\s+panel)\b", re.I)),
    ("toolbar_insert", re.compile(r"\b(?:toolbar\s+insert|insert.+toolbar|browse\s+dialog)\b", re.I)),
    ("scope_attribute", re.compile(r"\bscope\b", re.I)),
    ("local_scope", re.compile(r"\b(?:scope[^.;]{0,50}local|local[^.;]{0,50}scope)\b", re.I)),
    ("external_scope", re.compile(r"\b(?:scope[^.;]{0,50}external|external[^.;]{0,50}scope)\b", re.I)),
    ("absolute_dam_path", re.compile(r"/content/dam(?:/|\b)", re.I)),
    ("move_before_save", re.compile(r"\b(?:move-before-save|move[^.;]{0,80}before[^.;]{0,40}save)\b", re.I)),
    ("reference_integrity", re.compile(r"\b(?:broken\s+references?|breaks?\s+the\s+refs?|resolve\s+correctly|not\s+broken)\b", re.I)),
    ("guid_identity", re.compile(r"\b(?:original\s+guid|new\s+guid|guid\s+assigned|guid\s+minted|spurious\s+new\s+guid)\b", re.I)),
    ("uuid_property", re.compile(r"\buuid\s+property\b", re.I)),
    ("translation", re.compile(r"\btranslat(?:e|ed|ion|ing)\b", re.I)),
    ("translation_v1", re.compile(r"\bv1(?:\s+translation|\s*/\s*translation|\s+workflow)?\b", re.I)),
    ("translation_v2", re.compile(r"\bv2(?:\s+translation|\s+workflow)?\b", re.I)),
    ("translation_first_run", re.compile(r"\b(?:first\s+time|1st\s+translation|first\s+translation)\b", re.I)),
    ("translation_subsequent_run", re.compile(r"\b(?:2nd\s+(?:time|translation)|second\s+(?:time|translation)|2nd\s+or\s+furthermore)\b", re.I)),
    ("source_language_copy", re.compile(r"\b(?:source\s+language\s+assets?|source\s+content\s+cop(?:y|ies))\b", re.I)),
    ("target_language_folder", re.compile(r"\b(?:target\s+(?:language\s+)?folder|translation\s+language\s+folders?|lang\s+folder|(?:to|from)\s+lang)\b", re.I)),
    ("translation_output_buffer", re.compile(r"\b(?:translation_output|translation\s+output|buffer\s+cop(?:y|ies))\b", re.I)),
    ("translation_approval", re.compile(r"\b(?:assets?\s+are\s+approved|post\s+approval|translation\s+completes?)\b", re.I)),
    ("global_asset", re.compile(r"\b(?:global\s+(?:asset|folder)|(?:to|from|in)\s+(?:the\s+)?global)\b", re.I)),
    ("language_guid", re.compile(r"\b(?:lang(?:uage)?\s+code[^.;]{0,40}guid|guid[^.;]{0,40}lang(?:uage)?\s+code)\b", re.I)),
    ("asset_language_code", re.compile(r"\b(?:no|without)\s+lang(?:uage)?\s+code\s+appended\b", re.I)),
    ("move_lang_to_global", re.compile(r"\b(?:from\s+)?lang(?:uage)?(?:\s+folder)?\s+to\s+global\b", re.I)),
    ("move_global_to_lang", re.compile(r"\b(?:back\s+to\s+lang(?:uage)?(?:\s+folder)?\s+from\s+global|from\s+global\s+to\s+lang(?:uage)?(?:\s+folder)?|global\s+and\s+then\s+moved\s+to\s+lang)\b", re.I)),
    ("multilingual_translation", re.compile(r"\b(?:multiple\s+languages|multi-lingual\s+translation|multilingual\s+translation)\b", re.I)),
    ("translation_sync", re.compile(r"\b(?:insync|in\s+sync|missing\s+cop(?:y|ies))\b", re.I)),
    ("translation_workflow", re.compile(r"\b(?:(?:machine|human|xliff|multi-lingual|multilingual)\s+translation|xliff(?:\s+workflow)?|human\s+and\s+machine)\b", re.I)),
    ("translation_workflow_matrix", re.compile(r"\bfollowing\s+workflows?\s+to\s+be\s+covered\b", re.I)),
    ("translation_parity_matrix", re.compile(r"\brelated\s+assets?.+validated\s+in\s+v1\s+and\s+v2\b", re.I)),
    ("baseline_translation", re.compile(r"\b(?:with\s+baseline|baseline\s+export)\b", re.I)),
    ("baseline_export", re.compile(r"\b(?:baseline\s+export|exported\s+baseline|export\s+(?:the\s+)?baseline)\b", re.I)),
    ("translation_asset_retrieval", re.compile(r"\btranslation\s+asset\s+retrieval\b", re.I)),
    ("translation_acceptance", re.compile(r"\btranslation[^.;]{0,40}\bacceptance\b|\bacceptance[^.;]{0,40}\btranslation\b", re.I)),
    ("translation_rejection", re.compile(r"\btranslation[^.;]{0,40}\brejection\b|\brejection[^.;]{0,40}\btranslation\b", re.I)),
    ("upgrade_compatibility", re.compile(r"\b(?:pre[-\s]?upgrade|post[-\s]?upgrade|before\s+upgrad|after\s+upgrad|upgrading\s+the\s+server)\b", re.I)),
    ("label_propagation", re.compile(r"\blabel\s+propagation\b", re.I)),
    ("related_assets", re.compile(r"\b(?:related\s+assets?|relate\s*>\s*source|link\s+information)\b", re.I)),
    ("project_create_api", re.compile(r"\b(?:translation\s+project\s+create\s+api|projects?\s+created\s+via\s+v1)\b", re.I)),
    ("empty_xml", re.compile(r"\bempty\s+xml\b", re.I)),
    ("markdown", re.compile(r"\bmarkdown\b", re.I)),
    ("config_placeholder", re.compile(r"<\s*name\s+to\s+be\s+confirmed\s+by\s+dev\s*>", re.I)),
    ("ckeditor", re.compile(r"\bckeditor\b", re.I)),
    ("markup_editor", re.compile(r"\bmarkup\s*editor\b", re.I)),
    ("dita_ph", re.compile(r"(?:<\s*ph\b|\bph\s+tag\b|\bph\s*->)", re.I)),
    ("trademark", re.compile(r"(?:<\s*tm\b|\btm\s+symbol\b|\btrademark\s+symbol\b)", re.I)),
    ("dita_image", re.compile(r"(?:<\s*image\b|\bimage\s+in\s+(?:the\s+)?(?:map|topic)\s+title\b)", re.I)),
    ("dita_object", re.compile(r"(?:<\s*object\b|\bobject\b)", re.I)),
    ("inline_styling", re.compile(r"\b(?:inline\s+styling|italics?|bold|text\s+decorations?)\b", re.I)),
    ("not_applicable", _NOT_APPLICABLE_RE),
    ("mathml", re.compile(r"\bmathml\b", re.I)),
    ("styling", re.compile(r"\b(?:outputclass|output\s+class|css|style|styling|italics?|bold|text\s+decorations?|landscape|portrait)\b", re.I)),
    ("authoring_crud", re.compile(r"\b(?:crud|create|edit|update|delete|copy|paste|cut|undo|redo)\b", re.I)),
    ("jira_reference", _JIRA_KEY_RE),
    ("merged_html", re.compile(r"\bmerged\s*html(?:\.htm)?\b", re.I)),
    ("dita_structure", re.compile(r"\b(?:ditamap|topichead|topicgroup|topic-?ref)\b", re.I)),
    ("multimedia", re.compile(r"\b(?:video|audio|multimedia)\b", re.I)),
    ("svg", re.compile(r"\bsvg\b", re.I)),
    ("foreign", re.compile(r"\bforeign\b", re.I)),
    ("iframe", re.compile(r"\biframe\b", re.I)),
    ("image_integrity", re.compile(r"\bimages?\b", re.I)),
    ("diff_validation", re.compile(r"\bdiff\s+comparison\b", re.I)),
)

_TITLE_SCOPE_DIMENSIONS = frozenset({"map_title", "project_title", "topic_title"})
_CONTRADICTION_CONTEXT_TOKENS = frozenset({"etc", "example", "map", "other", "project", "title", "topic"})
_CONTRADICTION_BOUNDARY_DIMENSIONS = frozenset({"external_scope", "local_scope"})
_CONTRADICTION_SPECIFIC_DIMENSIONS = frozenset(
    {
        "absolute_dam_path",
        "baseline",
        "ckeditor",
        "conditional_preset",
        "conditions",
        "diff_validation",
        "dita_image",
        "dita_object",
        "dita_ot",
        "dita_ph",
        "dita_structure",
        "ditamap",
        "ditavalref",
        "editor_parity",
        "external_scope",
        "feature_flag",
        "foreign",
        "guid_identity",
        "guid_reference",
        "iframe",
        "image_integrity",
        "inline_styling",
        "keys",
        "local_scope",
        "map_title",
        "markup_editor",
        "mathml",
        "merged_html",
        "metadata_title",
        "move_before_save",
        "multimedia",
        "native_pdf",
        "not_applicable",
        "performance",
        "project_title",
        "reference_integrity",
        "repository_drag_drop",
        "scope_attribute",
        "security_permissions",
        "source_xml",
        "styling",
        "svg",
        "toolbar_insert",
        "topic_title",
        "topicref",
        "trademark",
        "uuid_property",
        "versioning",
    }
)
_TRANSLATION_OUTCOME_REQUIRED_DIMENSIONS = frozenset(
    {
        "empty_xml",
        "global_asset",
        "language_guid",
        "project_create_api",
        "related_assets",
        "source_language_copy",
        "target_language_folder",
        "translation_output_buffer",
        "translation_sync",
    }
)
_TRANSLATION_MATRIX_DIMENSIONS = frozenset(
    {"translation_parity_matrix", "translation_workflow_matrix"}
)


@dataclass(frozen=True)
class HistoricalUacClause:
    source_id: str
    stable_key: str
    text: str
    kind: str
    dimensions: tuple[str, ...]
    unresolved_reasons: tuple[str, ...]

    @property
    def unresolved(self) -> bool:
        return bool(self.unresolved_reasons)


@dataclass(frozen=True)
class HistoricalUacAnalysis:
    jira_key: str
    source_hash: str
    source_authority: str
    reuse_tier: str
    historical_outcome: str
    issue_closed: bool
    source_truncated: bool
    contract_complete: bool
    clauses: tuple[HistoricalUacClause, ...]
    contradictions: tuple[str, ...]
    dimensions: tuple[str, ...]
    performance_matters: bool
    performance_contract_complete: bool
    explicit_root_cause: bool
    explicit_test_evidence: bool
    root_cause_source: str
    test_evidence_source: str

    @property
    def in_scope_clauses(self) -> tuple[HistoricalUacClause, ...]:
        return tuple(clause for clause in self.clauses if clause.kind == "in_scope")

    @property
    def out_of_scope_clauses(self) -> tuple[HistoricalUacClause, ...]:
        return tuple(clause for clause in self.clauses if clause.kind == "out_of_scope")

    @property
    def reference_clauses(self) -> tuple[HistoricalUacClause, ...]:
        return tuple(clause for clause in self.clauses if clause.kind == "reference")

    @property
    def context_clauses(self) -> tuple[HistoricalUacClause, ...]:
        return tuple(clause for clause in self.clauses if clause.kind == "context")

    @property
    def unresolved_clauses(self) -> tuple[HistoricalUacClause, ...]:
        return tuple(clause for clause in self.clauses if clause.unresolved)


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_label(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def _historical_outcome(resolution: str) -> str:
    normalized = _clean(resolution).casefold()
    if normalized in _FIXED_OUTCOMES:
        return "implemented_fix"
    if normalized == "duplicate":
        return "duplicate_reference"
    if normalized == "working as designed":
        return "expected_product_behavior"
    if normalized in _CAUTION_OUTCOMES:
        return "non_fix_decision"
    return "other_resolution"


def _normalize_source_text(raw_text: str) -> str:
    text = html.unescape(str(raw_text or ""))
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    text = re.sub(r"\{(?:color|panel|code|noformat)(?::[^}]*)?\}", "", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_historical_uac_text(
    *,
    description: str = "",
    raw_text: str = "",
    fallback_documents: list[str] | tuple[str, ...] = (),
) -> str:
    """Recover the complete Jira UAC field before falling back to legacy truncated chunks."""
    for source in (description, raw_text):
        match = _UAC_DESCRIPTION_MARKER_RE.search(str(source or ""))
        if match:
            return match.group("uac").strip()
    bodies: list[str] = []
    for document in fallback_documents:
        body = str(document or "").strip()
        if "\n\n" in body:
            body = body.split("\n\n", 1)[1].strip()
        if body.casefold().startswith("acceptance criteria:"):
            body = body.split(":", 1)[1].strip()
        if body:
            bodies.append(body)
    return "\n".join(bodies).strip()


def _extract_comment_section(document: str, labels_pattern: str) -> str:
    text = _normalize_source_text(document)
    if not text:
        return ""
    match = re.search(
        rf"(?is)\b(?:{labels_pattern})\s*:\s*(?P<body>.+?)(?=\n\s*(?:{_COMMENT_SECTION_HEADERS})\s*:?|\Z)",
        text,
    )
    if not match:
        return ""
    return _clean(match.group("body"))[:2400]


def extract_explicit_root_cause_evidence(
    *,
    field_value: str = "",
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    field_text = _clean(field_value)
    if field_text:
        return field_text[:2400], "jira_root_cause_field"
    for document in comment_documents:
        section = _extract_comment_section(document, r"root\s+cause")
        if section:
            return section, "jira_comment_root_cause"
        section = _extract_comment_section(document, r"analysis")
        if section and _CAUSAL_EVIDENCE_RE.search(section):
            return section, "jira_comment_explicit_analysis"
    return "", "missing"


def extract_explicit_test_evidence(
    *,
    field_value: str = "",
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    field_text = _clean(field_value)
    if field_text:
        return field_text[:2400], "jira_test_plan_field"
    for document in comment_documents:
        section = _extract_comment_section(document, r"qa\s+verification|verification")
        if section and _VERIFICATION_RESULT_RE.search(section):
            return section, "jira_comment_qa_verification"
        section = _extract_comment_section(document, r"after\s+fix")
        if section and _VERIFICATION_RESULT_RE.search(section):
            return section, "jira_comment_after_fix"
        text = _normalize_source_text(document)
        match = re.search(
            rf"(?is)\bverified\s+on\s+build[^\n]*(?:\n(?P<body>.+?))?(?=\n\s*(?:{_COMMENT_SECTION_HEADERS})\s*:?|\Z)",
            text,
        )
        if match:
            evidence = _clean(match.group(0))[:2400]
            if _VERIFICATION_RESULT_RE.search(evidence):
                return evidence, "jira_comment_verified_build"
    return "", "missing"


def _split_sentences(line: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9<`])", line) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if _TBD_RE.fullmatch(part.rstrip(". ")) and merged:
            merged[-1] = f"{merged[-1]} {part}".strip()
        else:
            merged.append(part)
    return merged or ([line.strip()] if line.strip() else [])


def _strip_jira_line_markup(line: str) -> str:
    value = str(line or "").strip()
    for _ in range(3):
        cleaned = re.sub(r"\\*\{[_*]?\}", "", value)
        cleaned = re.sub(r"\[([^\]|]+)\|[^\]]+\]", r"\1", cleaned)
        cleaned = re.sub(r"^\[\s*(.*?)\s*\]$", r"\1", cleaned)
        cleaned = re.sub(r"\*{1,2}([^*\n]+?)\*{1,2}", r"\1", cleaned)
        cleaned = re.sub(r"_{1,2}([^_\n]+?)_{1,2}", r"\1", cleaned)
        if cleaned == value:
            break
        value = cleaned
    return value


def _is_parent_list_item(line: str) -> bool:
    normalized = _clean(line).rstrip(".")
    words = _TOKEN_RE.findall(normalized)
    return bool(
        normalized
        and len(words) <= 6
        and not _OUTCOME_RE.search(normalized)
        and not _TBD_RE.search(normalized)
        and not normalized.endswith(":")
    )


def _source_fragments(raw_text: str) -> tuple[list[tuple[str, str]], bool]:
    text = _normalize_source_text(raw_text)
    fragments: list[tuple[str, str]] = []
    mode = "in_scope"
    pending_parent: tuple[str, str, list[str], str] | None = None

    def append_sentence(source_mode: str, sentence: str) -> None:
        is_reference = bool(
            _JIRA_KEY_RE.search(sentence)
            and (
                _JIRA_REFERENCE_PREFIX_RE.match(sentence)
                or _JIRA_KEY_RE.fullmatch(sentence.strip().rstrip("."))
            )
        )
        if is_reference:
            kind = "reference"
        elif source_mode == "context":
            kind = "context"
        else:
            kind = (
                "out_of_scope"
                if source_mode == "out_of_scope" or _OUT_OF_SCOPE_RE.search(sentence)
                else "in_scope"
            )
        fragments.append((kind, sentence.strip()))

    def flush_parent() -> None:
        nonlocal pending_parent
        if pending_parent is None:
            return
        parent_mode, parent_text, children, collection_mode = pending_parent
        combined = parent_text
        if children:
            if collection_mode in {"numbered", "example"}:
                combined = f"{parent_text}: {' '.join(children)}"
            else:
                combined = f"{parent_text} {', '.join(children)}."
        append_sentence(parent_mode, combined)
        pending_parent = None

    for raw_line in text.splitlines():
        is_numbered = bool(_NUMBERED_LIST_PREFIX_RE.match(raw_line))
        line = _strip_jira_line_markup(_LIST_PREFIX_RE.sub("", raw_line))
        if not line:
            if pending_parent is None or pending_parent[3] != "numbered":
                flush_parent()
            continue
        if pending_parent is not None and pending_parent[3] in {"numbered", "example"}:
            is_section_header = bool(
                _ACCEPTANCE_HEADER_RE.match(line)
                or _CONTEXT_HEADER_RE.match(line)
                or _OUT_OF_SCOPE_HEADER_RE.match(line)
                or _IN_SCOPE_HEADER_RE.match(line)
                or _HEADING_RE.match(line)
                or _MATRIX_HEADER_RE.match(line)
                or _ROLLOUT_CONTEXT_RE.match(line)
                or _PENDING_LINKED_SCOPE_RE.search(line)
            )
            if is_numbered or is_section_header:
                flush_parent()
            else:
                pending_parent[2].append(line)
                continue
        if _ACCEPTANCE_HEADER_RE.match(line):
            flush_parent()
            mode = "in_scope"
            continue
        if _CONTEXT_HEADER_RE.match(line):
            flush_parent()
            mode = "context"
            continue
        out_header = _OUT_OF_SCOPE_HEADER_RE.match(line)
        if out_header:
            flush_parent()
            mode = "out_of_scope"
            line = out_header.group(1).strip()
            if not line:
                continue
        else:
            in_header = _IN_SCOPE_HEADER_RE.match(line)
            if in_header:
                flush_parent()
                mode = "in_scope"
                remainder = in_header.group(1).strip()
                line = f"Scope: {remainder}" if remainder else ""
                if not line:
                    continue
            elif _HEADING_RE.match(line):
                flush_parent()
                continue
        if _MATRIX_HEADER_RE.match(line):
            flush_parent()
            continue
        if _ROLLOUT_CONTEXT_RE.match(line):
            flush_parent()
            append_sentence("context", line)
            continue
        if _PENDING_LINKED_SCOPE_RE.search(line):
            flush_parent()
            append_sentence("context", line)
            continue
        if pending_parent is not None:
            if mode == pending_parent[0] and _is_parent_list_item(line):
                pending_parent[2].append(line.rstrip("."))
                continue
            flush_parent()
        if is_numbered and (line.endswith(":") or _is_parent_list_item(line)):
            pending_parent = (mode, line.rstrip(":").strip(), [], "numbered")
            continue
        if re.search(r"\b(?:i\.e\.|for\s+example)\s*:?[\s-]*$", line, re.I):
            pending_parent = (mode, line.rstrip(":").strip(), [], "example")
            continue
        if line.endswith(":") and re.search(r"\b(?:following|elements?|values?|operations?|outputs?)\b", line, re.I):
            pending_parent = (mode, line, [], "matrix")
            continue
        for sentence in _split_sentences(line):
            append_sentence(mode, sentence)
    flush_parent()
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for kind, text_value in fragments:
        key = (kind, _clean(text_value).casefold())
        if not text_value or key in seen:
            continue
        seen.add(key)
        deduped.append((kind, text_value))
    return deduped[:200], len(deduped) > 200


def _dimensions(text: str, kind: str) -> tuple[str, ...]:
    found = [name for name, pattern in _DIMENSION_RULES if pattern.search(text)]
    if (
        kind == "out_of_scope"
        or _NOT_APPLICABLE_RE.search(text)
        or re.search(r"\b(?:not|cannot|without|hidden|broken|disabled|excluded|refused)\b", text, re.I)
    ):
        found.append("negative")
    if re.search(r"\b(?:scope|only\s+for|applicable\s+for)\b", text, re.I):
        found.append("scope")
    return tuple(dict.fromkeys(found))


def _has_ambiguous_configuration_limitation(text: str) -> bool:
    if not _CONFIGURATION_STATE_PAIR_RE.search(text):
        return False
    segments = [segment.strip() for segment in re.split(r"[.;()]", text) if segment.strip()]
    return any(
        _CONFIGURATION_LIMITATION_RE.search(segment)
        and not _CONFIGURATION_STATE_TOKEN_RE.search(segment)
        for segment in segments
    )


def _unresolved_reasons(text: str, dimensions: tuple[str, ...], kind: str) -> tuple[str, ...]:
    if kind in {"out_of_scope", "reference", "context"}:
        return ()
    reasons: list[str] = []
    normalized = _clean(text)
    has_observable_outcome = bool(
        _OUTCOME_RE.search(normalized)
        or _NOT_APPLICABLE_RE.search(normalized)
        or _NO_FEATURE_FLAG_RE.search(normalized)
    )
    if _TBD_RE.search(normalized):
        reasons.append("tbd_marker")
    if _VAGUE_START_RE.search(normalized) and not has_observable_outcome:
        reasons.append("missing_observable_outcome")
    if (
        "upgrade_compatibility" in dimensions
        and _VAGUE_START_RE.search(normalized)
        and re.search(r"\b(?:before\s+upgrad\w*|pre[-\s]?upgrade)\b", normalized, re.I)
        and not re.search(r"\b(?:after\s+upgrad\w*|post[-\s]?upgrade)\b", normalized, re.I)
    ):
        reasons.append("missing_observable_outcome")
    if (
        not has_observable_outcome
        and not normalized.casefold().startswith("scope:")
        and {"trademark", "inline_styling", "dita_image", "ditavalref", "conditional_preset"}
        & set(dimensions)
    ):
        reasons.append("missing_observable_outcome")
    if (
        not has_observable_outcome
        and _TRANSLATION_OUTCOME_REQUIRED_DIMENSIONS & set(dimensions)
        and not _TRANSLATION_MATRIX_DIMENSIONS & set(dimensions)
    ):
        reasons.append("missing_observable_outcome")
    if _GENERIC_SUCCESS_RE.search(normalized):
        reasons.append("generic_success_outcome")
    if "authoring_crud" in dimensions and re.search(r"\bcrud\b", normalized, re.I):
        explicit_operations = {match.group(0).casefold() for match in _CRUD_OPERATION_RE.finditer(normalized)}
        if len(explicit_operations) < 3:
            reasons.append("crud_operation_matrix_missing")
    if "mathml" in dimensions and re.search(r"\bcomplex\b", normalized, re.I) and not _MATHML_COMPLEXITY_RE.search(
        normalized
    ):
        reasons.append("complex_fixture_definition_missing")
    if "styling" in dimensions and not _OUTPUT_TARGET_RE.search(normalized):
        reasons.append("output_target_matrix_missing")
    if (
        {"configuration", "dita_ot", "feature_flag"} & set(dimensions)
        and _has_ambiguous_configuration_limitation(normalized)
    ):
        reasons.append("configuration_state_outcome_mapping_missing")
    if (
        "uuid_property" in dimensions
        and re.search(r"\btrue\b", normalized, re.I)
        and not re.search(r"\bfalse\b", normalized, re.I)
    ):
        reasons.append("uuid_false_state_behavior_missing")
    if re.search(r"\b(?:old\s+and\s+new|new\s+and\s+old)\s+baselines?\b", normalized, re.I):
        reasons.append("baseline_fixture_definition_missing")
    if "ui" in dimensions and re.search(r"\bloader\b", normalized, re.I) and not re.search(
        r"\b(?:until|while|after|dismiss|hide|hidden|failure|timeout|complete|finishes?)\b",
        normalized,
        re.I,
    ):
        reasons.append("loader_lifecycle_missing")
    if "performance" in dimensions:
        if not _PERFORMANCE_METRIC_RE.search(normalized):
            reasons.append("performance_metric_missing")
        if not _PERFORMANCE_WORKLOAD_RE.search(normalized):
            reasons.append("performance_workload_missing")
    words = _TOKEN_RE.findall(normalized)
    if (
        len(words) <= 8
        and not has_observable_outcome
        and "scope" not in dimensions
        and "performance" not in dimensions
        and not _TRANSLATION_MATRIX_DIMENSIONS & set(dimensions)
        and not _NO_FEATURE_FLAG_RE.search(normalized)
        and not normalized.casefold().startswith("scope:")
    ):
        reasons.append("requirement_fragment")
    return tuple(dict.fromkeys(reasons))


def _stable_clause_key(jira_key: str, kind: str, text: str) -> str:
    digest = hashlib.sha256(f"{kind}\n{_clean(text).casefold()}".encode("utf-8")).hexdigest()[:20]
    return f"jira:{jira_key.strip().upper()}:uac:{digest}"


def _semantic_tokens(text: str) -> set[str]:
    return {token.casefold() for token in _TOKEN_RE.findall(text) if token.casefold() not in _TOKEN_STOP}


def _contradictions(clauses: list[HistoricalUacClause]) -> tuple[str, ...]:
    in_scope = [clause for clause in clauses if clause.kind == "in_scope"]
    excluded = [clause for clause in clauses if clause.kind == "out_of_scope"]
    found: list[str] = []
    for included_clause in in_scope:
        included_tokens = _semantic_tokens(included_clause.text) - _CONTRADICTION_CONTEXT_TOKENS
        for excluded_clause in excluded:
            excluded_boundaries = (
                set(excluded_clause.dimensions) & _CONTRADICTION_BOUNDARY_DIMENSIONS
            )
            if excluded_boundaries and not excluded_boundaries & set(included_clause.dimensions):
                continue
            shared_dimensions = (
                set(included_clause.dimensions)
                & set(excluded_clause.dimensions)
                & _CONTRADICTION_SPECIFIC_DIMENSIONS
            )
            if not shared_dimensions:
                continue
            excluded_tokens = _semantic_tokens(excluded_clause.text) - _CONTRADICTION_CONTEXT_TOKENS
            shared = sorted(included_tokens & excluded_tokens)
            if not shared:
                continue
            found.append(
                f"{included_clause.source_id} conflicts with {excluded_clause.source_id} on: {', '.join(shared[:6])}"
            )
    return tuple(found[:50])


def _apply_scope_target_gaps(clauses: list[HistoricalUacClause]) -> list[HistoricalUacClause]:
    explicit_targets = {
        dimension
        for clause in clauses
        if clause.kind == "in_scope" and "scope" in clause.dimensions
        for dimension in clause.dimensions
        if dimension in _TITLE_SCOPE_DIMENSIONS
    }
    if not explicit_targets:
        return clauses
    adjusted: list[HistoricalUacClause] = []
    for clause in clauses:
        clause_targets = set(clause.dimensions) & _TITLE_SCOPE_DIMENSIONS
        unexpected_targets = clause_targets - explicit_targets
        if (
            clause.kind == "in_scope"
            and "scope" not in clause.dimensions
            and unexpected_targets
            and clause_targets & explicit_targets
        ):
            adjusted.append(
                replace(
                    clause,
                    unresolved_reasons=tuple(
                        dict.fromkeys((*clause.unresolved_reasons, "scope_target_mismatch"))
                    ),
                )
            )
        else:
            adjusted.append(clause)
    return adjusted


def _apply_numbered_scope_gaps(
    clauses: list[HistoricalUacClause],
    source_text: str,
) -> list[HistoricalUacClause]:
    excluded_numbers: set[int] = set()
    for raw_line in source_text.splitlines():
        match = _NUMBERED_ITEM_RE.match(raw_line)
        if not match:
            continue
        if _OUT_OF_SCOPE_RE.search(_strip_jira_line_markup(match.group(2))):
            excluded_numbers.add(int(match.group(1)))
    if not excluded_numbers:
        return clauses
    adjusted: list[HistoricalUacClause] = []
    for clause in clauses:
        range_match = _UAC_POINT_RANGE_RE.search(clause.text)
        if range_match:
            lower = min(int(range_match.group(1)), int(range_match.group(2)))
            upper = max(int(range_match.group(1)), int(range_match.group(2)))
            if any(lower <= number <= upper for number in excluded_numbers):
                adjusted.append(
                    replace(
                        clause,
                        unresolved_reasons=tuple(
                            dict.fromkeys(
                                (*clause.unresolved_reasons, "range_includes_out_of_scope_point")
                            )
                        ),
                    )
                )
                continue
        adjusted.append(clause)
    return adjusted


def analyze_historical_uac(
    *,
    jira_key: str,
    acceptance_criteria: str,
    status: str = "",
    resolution: str = "",
    labels: list[str] | None = None,
    root_cause: str = "",
    test_evidence: str = "",
    root_cause_source: str = "",
    test_evidence_source: str = "",
) -> HistoricalUacAnalysis | None:
    source_text = _normalize_source_text(acceptance_criteria)
    if not jira_key.strip() or not source_text:
        return None
    source_hash = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
    fragments, source_truncated = _source_fragments(source_text)
    clauses: list[HistoricalUacClause] = []
    in_index = 0
    out_index = 0
    reference_index = 0
    context_index = 0
    for kind, text in fragments:
        if kind == "out_of_scope":
            out_index += 1
            source_id = f"OOS-{out_index:02d}"
        elif kind == "reference":
            reference_index += 1
            source_id = f"REF-{reference_index:02d}"
        elif kind == "context":
            context_index += 1
            source_id = f"CTX-{context_index:02d}"
        else:
            in_index += 1
            source_id = f"UAC-{in_index:02d}"
        dimensions = _dimensions(text, kind)
        clauses.append(
            HistoricalUacClause(
                source_id=source_id,
                stable_key=_stable_clause_key(jira_key, kind, text),
                text=text,
                kind=kind,
                dimensions=dimensions,
                unresolved_reasons=_unresolved_reasons(text, dimensions, kind),
            )
        )
    if not clauses:
        return None
    in_scope_has_output_target = any(
        clause.kind == "in_scope" and _OUTPUT_TARGET_RE.search(clause.text) for clause in clauses
    )
    if in_scope_has_output_target:
        clauses = [
            replace(
                clause,
                unresolved_reasons=tuple(
                    reason for reason in clause.unresolved_reasons if reason != "output_target_matrix_missing"
                ),
            )
            if clause.kind == "in_scope"
            else clause
            for clause in clauses
        ]
    clauses = _apply_scope_target_gaps(clauses)
    clauses = _apply_numbered_scope_gaps(clauses, source_text)
    contradictions = _contradictions(clauses)
    all_dimensions = tuple(sorted({dimension for clause in clauses for dimension in clause.dimensions}))
    performance_clauses = [clause for clause in clauses if "performance" in clause.dimensions]
    unresolved_in_scope = [clause for clause in clauses if clause.kind == "in_scope" and clause.unresolved]
    contract_complete = bool(in_index) and not unresolved_in_scope and not contradictions and not source_truncated
    outcome = _historical_outcome(resolution)
    normalized_resolution = _clean(resolution).casefold()
    issue_closed = (
        _clean(status).casefold() in _CLOSED_STATUSES
        or normalized_resolution not in _OPEN_RESOLUTION_VALUES
    )
    resolved_root_cause_source = root_cause_source.strip() or (
        "jira_root_cause_field" if _clean(root_cause) else "missing"
    )
    resolved_test_evidence_source = test_evidence_source.strip() or (
        "jira_test_plan_field" if _clean(test_evidence) else "missing"
    )
    explicit_root_cause = bool(_clean(root_cause)) and resolved_root_cause_source != "missing"
    explicit_test_evidence = bool(_clean(test_evidence)) and resolved_test_evidence_source != "missing"
    if outcome == "implemented_fix" and contract_complete and explicit_root_cause and explicit_test_evidence:
        reuse_tier = "historical_verified"
    elif outcome == "implemented_fix" and any(
        clause.kind == "in_scope" and not clause.unresolved for clause in clauses
    ):
        reuse_tier = "supporting"
    else:
        reuse_tier = "candidate"
    normalized_labels = {_normalized_label(label) for label in labels or []}
    source_authority = (
        "jira_accepted_uac" if normalized_labels & _ACCEPTED_UAC_LABELS else "jira_acceptance_field"
    )
    return HistoricalUacAnalysis(
        jira_key=jira_key.strip().upper(),
        source_hash=source_hash,
        source_authority=source_authority,
        reuse_tier=reuse_tier,
        historical_outcome=outcome,
        issue_closed=issue_closed,
        source_truncated=source_truncated,
        contract_complete=contract_complete,
        clauses=tuple(clauses),
        contradictions=contradictions,
        dimensions=all_dimensions,
        performance_matters=bool(performance_clauses),
        performance_contract_complete=bool(performance_clauses)
        and all(not clause.unresolved for clause in performance_clauses),
        explicit_root_cause=explicit_root_cause,
        explicit_test_evidence=explicit_test_evidence,
        root_cause_source=resolved_root_cause_source,
        test_evidence_source=resolved_test_evidence_source,
    )


def _base_metadata(analysis: HistoricalUacAnalysis) -> dict[str, Any]:
    return {
        "uac_schema_version": UAC_SCHEMA_VERSION,
        "uac_analysis_method": UAC_ANALYSIS_METHOD,
        "uac_llm_used": False,
        "uac_source_hash": analysis.source_hash,
        "uac_source_authority": analysis.source_authority,
        "uac_reuse_tier": analysis.reuse_tier,
        "uac_source_truncated": analysis.source_truncated,
        "uac_contract_complete": analysis.contract_complete,
        "uac_issue_closed": analysis.issue_closed,
        "uac_historical_outcome": analysis.historical_outcome,
        "uac_clause_count": len(analysis.in_scope_clauses),
        "uac_out_of_scope_count": len(analysis.out_of_scope_clauses),
        "uac_reference_count": len(analysis.reference_clauses),
        "uac_context_count": len(analysis.context_clauses),
        "uac_unresolved_count": len(analysis.unresolved_clauses),
        "uac_contradiction_count": len(analysis.contradictions),
        "uac_performance_matters": analysis.performance_matters,
        "uac_performance_complete": analysis.performance_contract_complete,
        "uac_root_cause_source": analysis.root_cause_source,
        "uac_test_evidence_source": analysis.test_evidence_source,
    }


def build_historical_uac_chunks(analysis: HistoricalUacAnalysis) -> list[dict[str, Any]]:
    base = _base_metadata(analysis)
    chunks: list[dict[str, Any]] = []
    contract_lines = [
        f"Historical Jira UAC contract: {analysis.jira_key}",
        f"Source authority: {analysis.source_authority}",
        f"Historical outcome: {analysis.historical_outcome}",
        f"Reuse tier: {analysis.reuse_tier}",
        f"Contract complete: {str(analysis.contract_complete).lower()}",
        "In-scope clauses:",
    ]
    contract_lines.extend(f"{clause.source_id}: {clause.text}" for clause in analysis.in_scope_clauses)
    if analysis.context_clauses:
        contract_lines.append("Context statements (not acceptance criteria):")
        contract_lines.extend(f"{clause.source_id}: {clause.text}" for clause in analysis.context_clauses)
    if analysis.out_of_scope_clauses:
        contract_lines.append("Out-of-scope clauses:")
        contract_lines.extend(f"{clause.source_id}: {clause.text}" for clause in analysis.out_of_scope_clauses)
    if analysis.reference_clauses:
        contract_lines.append("Referenced Jira evidence:")
        contract_lines.extend(f"{clause.source_id}: {clause.text}" for clause in analysis.reference_clauses)
    if analysis.unresolved_clauses:
        contract_lines.append(
            "Unresolved clauses: "
            + ", ".join(
                f"{clause.source_id} ({', '.join(clause.unresolved_reasons)})"
                for clause in analysis.unresolved_clauses
            )
        )
    if analysis.contradictions:
        contract_lines.append("Contradictions: " + " | ".join(analysis.contradictions))
    if analysis.source_truncated:
        contract_lines.append(
            "Source truncation: more than 200 unique clauses were present; this contract is incomplete and cannot be reused."
        )
    contract_lines.append(
        "Reuse rule: current Jira UAC and inspected implementation remain authoritative; candidate clauses may only add open questions or risk coverage."
    )
    chunks.append(
        {
            "chunk_type": UAC_CONTRACT_CHUNK_TYPE,
            "chunk_text": "\n".join(contract_lines),
            **base,
            "uac_dimensions": list(analysis.dimensions),
        }
    )
    for clause in analysis.clauses:
        chunk_type = (
            UAC_OUT_OF_SCOPE_CHUNK_TYPE
            if clause.kind == "out_of_scope"
            else UAC_REFERENCE_CHUNK_TYPE
            if clause.kind == "reference"
            else UAC_CONTEXT_CHUNK_TYPE
            if clause.kind == "context"
            else UAC_CLAUSE_CHUNK_TYPE
        )
        chunks.append(
            {
                "chunk_type": chunk_type,
                "chunk_text": "\n".join(
                    [
                        f"Historical Jira UAC clause: {analysis.jira_key} {clause.source_id}",
                        f"Source text: {clause.text}",
                        f"Clause kind: {clause.kind}",
                        f"Dimensions: {', '.join(clause.dimensions) if clause.dimensions else 'unclassified'}",
                        f"Reuse tier: {analysis.reuse_tier if not clause.unresolved else 'candidate'}",
                        "Unresolved: "
                        + (", ".join(clause.unresolved_reasons) if clause.unresolved_reasons else "no"),
                    ]
                ),
                **base,
                "uac_clause_id": clause.source_id,
                "uac_clause_stable_key": clause.stable_key,
                "uac_clause_kind": clause.kind,
                "uac_dimensions": list(clause.dimensions),
                "uac_clause_unresolved": clause.unresolved,
                "uac_clause_reuse_tier": "candidate" if clause.unresolved else analysis.reuse_tier,
            }
        )
    grouped: dict[str, list[HistoricalUacClause]] = defaultdict(list)
    for clause in analysis.clauses:
        for dimension in clause.dimensions:
            grouped[dimension].append(clause)
    for dimension in sorted(grouped):
        dimension_clauses = grouped[dimension]
        chunks.append(
            {
                "chunk_type": UAC_DIMENSION_CHUNK_TYPE,
                "chunk_text": "\n".join(
                    [
                        f"Historical Jira UAC test dimension: {analysis.jira_key} {dimension}",
                        *[f"{clause.source_id}: {clause.text}" for clause in dimension_clauses],
                        "Reuse rule: preserve exact source boundaries and do not infer missing outcomes.",
                    ]
                ),
                **base,
                "uac_dimension": dimension,
                "uac_dimensions": [dimension],
                "uac_dimension_has_unresolved": any(clause.unresolved for clause in dimension_clauses),
            }
        )
    return chunks
