"""Deterministic clause-level analysis for historical Jira acceptance criteria."""

from __future__ import annotations

import hashlib
import html
import re
from collections import defaultdict
from dataclasses import dataclass, replace
from typing import Any


UAC_SCHEMA_VERSION = "historical-uac-v5"
CURRENT_UAC_SCHEMA_VERSION = "current-uac-v1"
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
    r"\b(?:out\s+of\s+scope|outside\s+(?:the\s+)?scope|beyond\s+(?:the\s+)?scope|not\s+in\s+scope|not\s+needed|"
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
    r"^\s*(?:problem\s+statement|business\s+impact|background|issue\s+description|description|automation)[\s:\u2013\u2014-]*$",
    re.I,
)
_HEADING_RE = re.compile(
    r"^\s*(?:capabilities?\s+needed|catalyst|notes?|other\s+pointers?)[\s:\u2013\u2014-]*$",
    re.I,
)
_FUNCTIONAL_SCOPE_HEADER_RE = re.compile(
    r"^\s*overall\s+functionality\b.{0,180}\bshould\s+work\s*:?\s*$",
    re.I,
)
_MATRIX_HEADER_RE = re.compile(r"^\s*following\s+validations?\s+to\s+work\s+as\s+is\s*:\s*$", re.I)
_ROLLOUT_CONTEXT_RE = re.compile(r"^\s*we\s+will\s+be\s+providing\s+(?:a\s+)?fix\s+in\b", re.I)
_PENDING_LINKED_SCOPE_RE = re.compile(
    r"\b(?:more\s+information\s+awaited|scope\s*:?\s*will\s+be\s+discussed|will\s+be\s+discussed\s+and\s+updated)\b",
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
_NO_ACCEPTED_UAC_RE = re.compile(
    r"^(?:(?:uac|acceptance\s+criteri(?:a|on))\s*[:\-]?\s*)?"
    r"(?:not\s+required|not\s+applicable|n\s*/?\s*a|none)\.?$",
    re.I,
)
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
_TENTATIVE_CAUSAL_EVIDENCE_RE = re.compile(
    r"\b(?:root\s+cause\s+(?:could|may|might)|could\s+be\s+linked|may\s+be|might\s+be|"
    r"seems?\s+to|appears?\s+to|potential(?:ly)?|hypothesis|to\s+confirm|"
    r"suggest(?:s|ed|ing)?\s+(?:disabling|checking|verifying)|if\s+this\s+is\s+in\s+fact)\b",
    re.I,
)
_CONFIRMED_CAUSAL_EVIDENCE_RE = re.compile(
    r"\b(?:root\s+cause\s+(?:is|was)|this\s+indicated\s+a\s+problem|"
    r"issue\s+(?:is|was)\s+environment[-\s]specific|"
    r"re-?index(?:ing|ed)[^.;\n]{0,140}(?:fixed|resolved)|"
    r"(?:fixed|resolved)[^.;\n]{0,100}after\s+re-?index(?:ing|ed)|"
    r"initial\s+assumption[^.;\n]{0,140}(?:invalid|incorrect|ruled\s+out))\b",
    re.I,
)
_CUSTOMER_VALIDATION_RE = re.compile(
    r"\b(?:customer|[A-Z][A-Za-z0-9_-]+\s+(?:IT|team))?[^.;\n]{0,80}"
    r"tested\s+and\s+validated[^.;\n]{0,120}(?:fixed|resolved|working)\b",
    re.I,
)
_ACCEPTANCE_EXECUTION_RE = re.compile(
    r"\b(?:ticket|issue)\s+(?:passes|passed)\s+all(?:\s+the)?(?:\s+mentioned)?\s+"
    r"(?:points?\s+of\s+)?acceptance\s+criteri(?:a|on)\b",
    re.I,
)
_EXECUTED_TEST_RE = re.compile(
    r"\btested\b[^.\n]{0,260}\b(?:build|file[-\s]?sets?|smaller|bigger|larger|button|"
    r"progress(?:\s+bar)?|common\s+tags?|select\s+all|filters?|broken\s+links?)\b",
    re.I,
)
_VERIFIED_VERSION_RE = re.compile(
    r"\bverified\s+on\s+(?:build\s+)?[\"']?v?\d+(?:\.\d+){1,3}[\"']?\b",
    re.I,
)
_HOTFIX_VERSION_VALIDATION_RE = re.compile(
    r"\b(?:this\s+is\s+)?(?:working\s+fine|works?|verified|validated)\s+on\s+"
    r"(?:the\s+)?hotfix\s+[\"']?v?\d+(?:\.\d+){1,3}[\"']?\b",
    re.I,
)
_HOTFIX_ONLY_SCOPE_RE = re.compile(
    r"\b(?:this\s+)?ticket\s+is\s+created\s+for\s+[^\n]{0,80}\bhotfix\s+only\b",
    re.I,
)
_MAINLINE_UAC_SCOPE_RE = re.compile(
    r"\bUAC\b[^.\n]{0,120}\b(?:is\s+)?(?:done|applies?|scoped)\s+for\s+"
    r"(?:\d{4}|\d+(?:\.\d+){1,3})\b",
    re.I,
)
_HOTFIX_POINT_FIX_RE = re.compile(
    r"\bfor\s+(?:the\s+)?hotfix\b[^.\n]{0,260}\b(?:point\s+fix|just\s+(?:done|includes?)|only)\b",
    re.I,
)
_COMMENT_ENTRY_START_RE = re.compile(r"(?m)^\[[^\]\n]{4,100}\]\s+[^:\n]{1,180}:\s*")
_COMMENT_TIMESTAMP_RE = re.compile(r"^\[(?P<timestamp>\d{4}-\d{2}-\d{2}(?:[T ][^\]]+)?)\]")
_FINAL_SCOPE_HEADER_RE = re.compile(r"(?im)^\s*(?:(?:final|accepted|agreed)\s+)?scope\s*:\s*(?:.*)$")
_FINAL_SCOPE_PHRASE_RE = re.compile(
    r"\b(?:final|accepted|agreed)\s+scope\b|"
    r"\bscope\s+of\s+(?:this\s+)?(?:bug|ticket|fix|change|jira)\s+"
    r"(?:is|was)\s+(?:limited|restricted|narrowed)\s+to\b",
    re.I,
)
_COMMENT_FOOTER_RE = re.compile(r"^\s*(?:cc\b|regards\b|pin\b)", re.I)
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
    (
        "condition_groups",
        re.compile(
            r"\b(?:condition\s+groups?|grouped\s+conditions?|condition\s+grouping|"
            r"existing\s+conditions?[^.;\n]{0,80}\bgroups?|its\s+group)\b",
            re.I,
        ),
    ),
    ("condition_color", re.compile(r"\b(?:condition\s+)?colou?r\b|\byellow\b", re.I)),
    ("folder_profile", re.compile(r"\b(?:folder\s+profile|FP)\b", re.I)),
    ("add_condition", re.compile(r"\b(?:add|adding|create|creating)\s+(?:a\s+)?new\s+conditions?\b", re.I)),
    ("edit_condition", re.compile(r"\b(?:edit|editing|update|updating)\s+(?:an?\s+)?existing\s+conditions?\b", re.I)),
    ("ditaval_asset", re.compile(r"\bditaval(?:\s+files?)?\b", re.I)),
    ("repository_search", re.compile(r"\brepository\s+search\b|\brepository\b[^.;]{0,80}\bfilter", re.I)),
    ("creation_dialog", re.compile(r"\bditaval\s+creation\b|\bnew\s+topic\b|\bcreat(?:e|es|ed|ing)\b[^.;]{0,80}\bditaval\b", re.I)),
    ("reports", re.compile(r"\b(?:metadata\s+reports?|reports?)\b", re.I)),
    ("metadata_report", re.compile(r"\bmetadata\s+report\b", re.I)),
    ("metadata_manage", re.compile(r"\b(?:manage\s+(?:button|dialog|functionality)|reports?\s*>\s*metadata|metadata\s+(?:center|panel))\b", re.I)),
    ("manage_button", re.compile(r"\bmanage\s+button\b", re.I)),
    ("common_tags", re.compile(r"\bcommon\s+tags?\b", re.I)),
    ("document_state", re.compile(r"\b(?:document|doc)\s+state\b", re.I)),
    ("select_all", re.compile(r"\b(?:select\s+all|allAssets\s*=\s*true)\b", re.I)),
    ("selective_assets", re.compile(r"\b(?:selective\s+(?:list\s+of\s+)?(?:assets?|files?)|selected\s+(?:assets?|files?))\b", re.I)),
    ("dita_asset", re.compile(r"\bDITA\s+(?:files?|assets?)\b", re.I)),
    ("non_dita_asset", re.compile(r"\bnon[-\s]?DITA(?:\s+(?:files?|assets?))?\b", re.I)),
    ("cloud", re.compile(r"\bcloud\b", re.I)),
    ("on_prem", re.compile(r"\bon[-\s]?prem(?:ise)?\b", re.I)),
    ("custom_tags", re.compile(r"\bcustom\s+tags?\b", re.I)),
    ("ootb_tags", re.compile(r"\b(?:OOTB|out[-\s]?of[-\s]?the[-\s]?box)\s+tags?\b", re.I)),
    ("bulk_operation", re.compile(r"\bbulk\s+operation\b", re.I)),
    ("updated_count", re.compile(r"\b(?:files?\s+updated|updated\s+(?:files?|count))\b", re.I)),
    ("skipped_count", re.compile(r"\b(?:files?\s+skipped|skipped(?:\s+files?)?[^.;\n]{0,60}\bcount(?:ed)?)\b", re.I)),
    ("error_message", re.compile(r"\b(?:proper|actionable|correct)\s+error\s+message\b", re.I)),
    ("timeout", re.compile(r"\btime(?:d)?\s*out|\btimeout\b", re.I)),
    ("loader", re.compile(r"\b(?:loader|progress\s+(?:bar|indicator))\b", re.I)),
    ("disabled_state", re.compile(r"\b(?:button\s+)?(?:is|be|gets?|remain(?:s)?)?\s*disabled\b", re.I)),
    ("enabled_state", re.compile(r"\b(?:button\s+)?(?:is|be|gets?|remain(?:s)?)?\s*enabled\b", re.I)),
    ("loading_shimmer", re.compile(r"\bloading\s+shimmer\b|\bshimmer\b", re.I)),
    ("broken_links", re.compile(r"\bbroken\s+links?\b", re.I)),
    ("fix_links", re.compile(r"\bfix\s+links?\b|\bfix\s+link\s+button\b", re.I)),
    ("filter_scope", re.compile(r"\bfilters?\s+(?:panel|applied|should\s+work|work\s+as\s+is)\b", re.I)),
    ("visible_assets", re.compile(r"\b(?:files?|assets?)\s+(?:present|visible)\b", re.I)),
    ("api_response", re.compile(r"\bAPI\s+response\b", re.I)),
    ("all_assets", re.compile(r"\ballAssets\b|\ball\s+assets\b", re.I)),
    ("uuid_to_path", re.compile(r"\bconvert(?:ing)?\s+UUID\s+to\s+path\b|\bUUID[-\s]?to[-\s]?path\b", re.I)),
    ("full_scan", re.compile(r"\b(?:scann?ing\s+(?:of\s+)?all\s+data|full\s+(?:repository|data)\s+scan)\b", re.I)),
    ("http_503", re.compile(r"\b503\b", re.I)),
    ("resource_stability", re.compile(r"\b(?:CPU|memory|pod|environment)\b[^.;\n]{0,100}\b(?:spike|crash|usage|load)\b", re.I)),
    ("duplicate_trigger_prevention", re.compile(r"\b(?:multiple|duplicate)\s+(?:triggers?|API\s+calls?)\b", re.I)),
    ("api_path", re.compile(r"\bbin/guides/v1/map/reports/metadata/tags/common\b", re.I)),
    ("file_type_filter", re.compile(r"\b(?:file\s+type|type)\s+filter(?:ing)?\b|\bDITA\s+Topic\b", re.I)),
    ("custom_namespace", re.compile(r"\b(?:custom\s+namespace|namespaced\s+propert(?:y|ies)|test:type)\b", re.I)),
    ("type_filter", re.compile(r"\bTypeFilter\b", re.I)),
    ("oak_index", re.compile(r"\b(?:Oak\s+index|Lucene\s+index|custom\s+index|indexing)\b", re.I)),
    ("dam_asset_lucene", re.compile(r"\bdamAssetLucene\b", re.I)),
    ("reindexing", re.compile(r"\bre-?index(?:ing|ed)?\b", re.I)),
    ("environment_specific", re.compile(r"\benvironment[-\s]specific\b", re.I)),
    ("filter_union", re.compile(r"\b(?:both|combined?|combining)\b[^.;]{0,80}\b(?:filters?|DITA\s+Topic|Others)\b", re.I)),
    ("result_count", re.compile(r"\b\d[\d,]*\s+(?:files?|results?|assets?)\b", re.I)),
    (
        "file_type_taxonomy",
        re.compile(
            r"\b(?:file\s+type|non[-\s]?dita|dita\s+topic\s+file|documents?\s*/\s*others?|"
            r"other\s+dita(?:\s+type)?(?:\s+document)?)\b",
            re.I,
        ),
    ),
    (
        "cross_touchpoint_taxonomy",
        re.compile(
            r"\b(?:touch\s*points?|treated\s+(?:differently|as)|inconsistent(?:ly|cy)?|"
            r"consistent\s+(?:classification|taxonomy))\b",
            re.I,
        ),
    ),
    ("navtitle", re.compile(r"\b(?:navtitle|navigation\s+title)\b", re.I)),
    ("toolbar_customization", re.compile(r"\b(?:toolbar|top\s+toolbar|relationship\s+table)\b", re.I)),
    ("custom_button", re.compile(r"\b(?:custom\s+(?:button|action)|Export\s+PDF)\b", re.I)),
    ("preview_mode", re.compile(r"\bpreview\s+mode\b", re.I)),
    ("locked_state", re.compile(r"\b(?:file\s+is\s+locked|locked\s+file|lock\s+scenario|locked)\b", re.I)),
    ("unlocked_state", re.compile(r"\b(?:file\s+is\s+unlocked|unlocked\s+file|unlock\s+scenario|unlocked)\b", re.I)),
    (
        "editor_toolbar_configuration",
        re.compile(r"\beditor_toolbar\.(?:js|json)\b", re.I),
    ),
    (
        "configuration_migration",
        re.compile(r"\b(?:port(?:ed|ing)?|migrat(?:e|ed|ing))\b[^.;\n]{0,120}\beditor_toolbar\.(?:js|json)\b", re.I),
    ),
    (
        "ui_configuration",
        re.compile(r"\b(?:ui[_\s-]*config(?:\.json)?|ditaAttributes|required\s+navtitle)\b", re.I),
    ),
    (
        "configuration_visibility",
        re.compile(
            r"\b(?:show\s*/\s*hide|show(?:s|n|ing)?|hide(?:s|den)?|absent|visible|visibility|"
            r"button\s+(?:comes?\s+up|appears?|disappears?|is\s+removed))\b",
            re.I,
        ),
    ),
    ("documentation_gap", re.compile(r"\b(?:documentation|documented|deprecat(?:e|ed|ion|ing))\b", re.I)),
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
    ("uuid_variant", re.compile(r"\buuid\b", re.I)),
    ("non_uuid_variant", re.compile(r"\bnon[-\s]?uuid\b", re.I)),
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
    ("asset_browser_thumbnail", re.compile(r"\bthumbnails?\b", re.I)),
    (
        "thumbnail_surfaces",
        re.compile(
            r"\b(?:home\s+repository(?:\s+content\s+view)?|bottom\s+search\s+panel|search\s+panel)\b",
            re.I,
        ),
    ),
    ("thumbnail_format_matrix", re.compile(r"\b(?:png|jpe?g|svg)\b", re.I)),
    (
        "thumbnail_freshness",
        re.compile(r"\bthumbnail\b[^.\n]{0,100}\b(?:latest\s+version|current\s+version)\b", re.I),
    ),
    (
        "thumbnail_fallback",
        re.compile(
            r"\b(?:unsupported|invalid)\b[^.\n]{0,100}\b(?:placeholder|broken\s+image|multimedia\s+icon)\b|"
            r"\b(?:default\s+placeholder|fallback\s+to\s+the\s+original\s+image|no\s+broken\s+UI)\b",
            re.I,
        ),
    ),
    (
        "thumbnail_lazy_loading",
        re.compile(r"\b(?:lazy[-\s]?load(?:ing)?|layout\s+jank|load\s+smoothly)\b", re.I),
    ),
    (
        "asset_picker_multi_selection",
        re.compile(r"\bmulti[-\s]?selection\b|\bselect\s+multiple\s+images?\b", re.I),
    ),
    (
        "xref_map_display_label",
        re.compile(
            r"\b(?:xref|cross[-\s]?reference)\b[^.\n]{0,180}\b(?:map|ditamap)\b"
            r"[^.\n]{0,180}\b(?:title|file\s*name|filename)\b|"
            r"\b(?:map|ditamap)\b[^.\n]{0,180}\b(?:xref|cross[-\s]?reference)\b"
            r"[^.\n]{0,180}\b(?:title|file\s*name|filename)\b|"
            r"\b(?:map|ditamap)\s+(?:files?\s+)?references?\b[^.\n]{0,180}"
            r"\b(?:title|file\s*name|filename)\b",
            re.I,
        ),
    ),
    (
        "map_reference",
        re.compile(r"\b(?:map|ditamap)\s+(?:files?\s+)?referenc(?:e|ed|es)\b", re.I),
    ),
    (
        "reference_display_label",
        re.compile(
            r"\b(?:display|show|shown|visible)\b[^.\n]{0,100}\b(?:title|file\s*name|filename)\b|"
            r"\b(?:title|file\s*name|filename)\b[^.\n]{0,100}\b(?:display|show|shown|visible)\b",
            re.I,
        ),
    ),
    (
        "authoring_viewport_stability",
        re.compile(
            r"\b(?:author(?:ing)?\s+(?:view|canvas)|editor\s+canvas|editing\s+location)\b"
            r"[^.\n]{0,220}\b(?:scroll|viewport|jump|visible|cursor|caret|selection|insertion\s+location)\b|"
            r"\b(?:cursor|caret|active\s+element|insertion\s+location)\b"
            r"[^.\n]{0,180}\b(?:remain|restore|visible|viewport|scroll)\b",
            re.I,
        ),
    ),
    (
        "map_preview_state",
        re.compile(
            r"\bmap\s+preview\b[^.\n]{0,220}\b(?:scroll|refresh|selected\s+topic|condition|"
            r"right\s+panel|return|edit)\b|\bpreview\b[^.\n]{0,120}\bscroll\s+position\b",
            re.I,
        ),
    ),
    (
        "state_restoration",
        re.compile(
            r"\b(?:restore|restored|restoration|retain|retained|preserve|preserved|maintain|maintained)\b"
            r"[^.\n]{0,100}\b(?:state|position|location|selection|scroll|viewport)\b",
            re.I,
        ),
    ),
    (
        "editor_scroll",
        re.compile(
            r"\b(?:author(?:ing)?\s+(?:view|canvas)|editor\s+canvas|editing)\b"
            r"[^.\n]{0,160}\b(?:scroll|viewport|jump)\b",
            re.I,
        ),
    ),
    (
        "active_element",
        re.compile(r"\b(?:active\s+element|active\s+editing\s+location|intended\s+insertion\s+location)\b", re.I),
    ),
    ("caret", re.compile(r"\b(?:caret|cursor|text\s+selection)\b", re.I)),
    (
        "reference_insertion",
        re.compile(
            r"\b(?:insert|update|adding?)\b[^.\n]{0,80}\b(?:cross[-\s]?reference|reference\s+link|xref)\b|"
            r"\b(?:cross[-\s]?reference|reference\s+link|xref)\b[^.\n]{0,80}\b(?:picker|dialog|insert|update)\b",
            re.I,
        ),
    ),
    ("large_topic", re.compile(r"\b(?:large|long|heavy)\s+(?:DITA\s+)?topics?\b", re.I)),
    ("scroll_to_top", re.compile(r"\b(?:scroll|jump|moves?)\b[^.\n]{0,60}\b(?:document\s+)?top\b", re.I)),
    ("cals_table", re.compile(r"\b(?:CALS|tgroup|colspec|namest|nameend)\b", re.I)),
    (
        "multi_column_delete",
        re.compile(r"\b(?:delete|deleting|remove|removing)\b[^.\n]{0,100}\b(?:two|2|multiple)\s+columns?\b", re.I),
    ),
    (
        "table_structure_integrity",
        re.compile(
            r"\b(?:table\s+structure|structural\s+integrity|ghost\s+column|blank\s+column|"
            r"tgroup\s*/?@?cols|colspec|namest|nameend)\b",
            re.I,
        ),
    ),
    ("large_file_tag_count", re.compile(r"\blargeFileTagCount\b", re.I)),
    (
        "large_file_safeguard",
        re.compile(
            r"\b(?:large[-\s]?file\s+mode|largeFileTagCount|undo/redo[^.\n]{0,80}(?:disabled|unavailable)|"
            r"dirty\s+marker[^.\n]{0,80}(?:disabled|unavailable|goes\s+away))\b",
            re.I,
        ),
    ),
    ("working_as_designed", re.compile(r"\bworking\s+as\s+designed\b", re.I)),
    (
        "configuration_driven_behavior",
        re.compile(
            r"\b(?:configuration[-\s]driven|system\s+configuration|configured\s+threshold|"
            r"largeFileTagCount)\b",
            re.I,
        ),
    ),
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
    source_origin: str
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
    release_scope_evidence: str
    release_scope_source: str
    release_scope_split: bool

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


def has_accepted_uac_label(labels: list[str] | tuple[str, ...] | set[str]) -> bool:
    return bool({_normalized_label(label) for label in labels} & _ACCEPTED_UAC_LABELS)


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


def is_no_uac_sentinel(value: Any) -> bool:
    """Return true only for a whole-field marker that explicitly says no UAC exists."""
    normalized = _clean(_normalize_source_text(str(value or ""))).strip()
    return bool(normalized and _NO_ACCEPTED_UAC_RE.fullmatch(normalized))


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


def _comment_entries(comment_documents: list[str] | tuple[str, ...]) -> list[str]:
    entries: list[str] = []
    for document in comment_documents:
        text = _normalize_source_text(document)
        if not text:
            continue
        starts = list(_COMMENT_ENTRY_START_RE.finditer(text))
        if not starts:
            entries.append(text)
            continue
        for index, start in enumerate(starts):
            end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
            entry = text[start.start() : end].strip()
            if entry:
                entries.append(entry)
    return entries


def is_explicit_final_scope_comment(value: Any) -> bool:
    """Return true only for comments that explicitly declare a final/scoped contract."""
    text = _normalize_source_text(str(value or ""))
    if not text:
        return False
    if _FINAL_SCOPE_PHRASE_RE.search(text):
        return True
    header = _FINAL_SCOPE_HEADER_RE.search(text)
    if not header:
        return False
    header_remainder = header.group(0).split(":", 1)[1].strip() if ":" in header.group(0) else ""
    scoped_lines = [header_remainder, *text[header.end() :].splitlines()]
    return any(
        len(_TOKEN_RE.findall(line)) >= 3
        and not _PENDING_LINKED_SCOPE_RE.search(line)
        and not _COMMENT_FOOTER_RE.match(line)
        for line in scoped_lines
        if line.strip()
    )


def _comment_body(entry: str) -> str:
    text = _normalize_source_text(entry)
    text = _COMMENT_ENTRY_START_RE.sub("", text, count=1).strip()
    if text.casefold().startswith("discussion:"):
        text = text.split(":", 1)[1].strip()
    return text


def _comment_recency_key(entry: str, index: int) -> tuple[int, str, int]:
    match = _COMMENT_TIMESTAMP_RE.match(entry.strip())
    if match:
        return 1, match.group("timestamp"), index
    return 0, "", index


def _extract_final_scope_text(entry: str) -> str:
    body = _comment_body(entry)
    if not body or not is_explicit_final_scope_comment(body):
        return ""
    lines = body.splitlines()
    header_indexes = [index for index, line in enumerate(lines) if _FINAL_SCOPE_HEADER_RE.match(line)]
    if header_indexes:
        start = header_indexes[-1]
    else:
        start = next(
            (index for index, line in enumerate(lines) if _FINAL_SCOPE_PHRASE_RE.search(line)),
            0,
        )
    scoped_lines: list[str] = []
    for line in lines[start:]:
        if scoped_lines and _COMMENT_FOOTER_RE.match(line):
            break
        scoped_lines.append(line.rstrip())
    preceding_out_of_scope = [
        line.strip()
        for line in lines[:start]
        if line.strip() and _OUT_OF_SCOPE_RE.search(line)
    ]
    text = "\n".join(scoped_lines).strip()
    if preceding_out_of_scope:
        text += "\nOut of Scope:\n" + "\n".join(preceding_out_of_scope)
    return text.strip()


def extract_comment_accepted_uac(
    *,
    labels: list[str] | tuple[str, ...] = (),
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    """Recover a final scoped UAC comment only when Jira explicitly marks UAC accepted."""
    normalized_labels = {_normalized_label(label) for label in labels}
    if not normalized_labels & _ACCEPTED_UAC_LABELS:
        return "", "missing"
    candidates: list[tuple[tuple[int, str, int], str]] = []
    for index, entry in enumerate(_comment_entries(comment_documents)):
        scope_text = _extract_final_scope_text(entry)
        if scope_text:
            candidates.append((_comment_recency_key(entry, index), scope_text))
    if not candidates:
        return "", "missing"
    candidates.sort(key=lambda candidate: candidate[0])
    return candidates[-1][1], "jira_comment_accepted_scope"


def resolve_historical_uac_text(
    *,
    acceptance_criteria: str = "",
    labels: list[str] | tuple[str, ...] = (),
    description: str = "",
    raw_text: str = "",
    fallback_documents: list[str] | tuple[str, ...] = (),
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    """Resolve accepted UAC deterministically, preferring the native field over comments."""
    field_text = str(acceptance_criteria or "").strip() or extract_historical_uac_text(
        description=description,
        raw_text=raw_text,
        fallback_documents=fallback_documents,
    )
    if field_text:
        if is_no_uac_sentinel(field_text):
            return "", "jira_no_uac_sentinel"
        return field_text, "jira_acceptance_field"
    return extract_comment_accepted_uac(labels=labels, comment_documents=comment_documents)


def _root_cause_candidate_score(text: str, source: str) -> int:
    confirmed_count = len(_CONFIRMED_CAUSAL_EVIDENCE_RE.findall(text))
    if _TENTATIVE_CAUSAL_EVIDENCE_RE.search(text) and confirmed_count == 0:
        return -1
    score = {
        "jira_comment_root_cause": 6,
        "jira_comment_explicit_analysis": 5,
        "jira_comment_confirmed_root_cause": 4,
    }[source]
    score += confirmed_count * 3
    score += int(bool(_CAUSAL_EVIDENCE_RE.search(text)))
    score += 2 * int(bool(re.search(r"\binitial\s+assumption\b.+\binvalid\b", text, re.I)))
    score += 2 * int(bool(re.search(r"\bdamAssetLucene\b|\benvironment[-\s]specific\b", text, re.I)))
    return score


def extract_explicit_root_cause_evidence(
    *,
    field_value: str = "",
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    field_text = _clean(field_value)
    if field_text:
        return field_text[:2400], "jira_root_cause_field"
    candidates: list[tuple[int, int, str, str]] = []
    for index, document in enumerate(_comment_entries(comment_documents)):
        section = _extract_comment_section(document, r"root\s+cause|rca")
        if section:
            score = _root_cause_candidate_score(section, "jira_comment_root_cause")
            if score >= 0:
                candidates.append((score, index, section, "jira_comment_root_cause"))
        section = _extract_comment_section(document, r"analysis")
        if section and _CAUSAL_EVIDENCE_RE.search(section):
            score = _root_cause_candidate_score(section, "jira_comment_explicit_analysis")
            if score >= 0:
                candidates.append((score, index, section, "jira_comment_explicit_analysis"))
        text = _clean(document)[:2400]
        if _CONFIRMED_CAUSAL_EVIDENCE_RE.search(text):
            score = _root_cause_candidate_score(text, "jira_comment_confirmed_root_cause")
            if score >= 0:
                candidates.append((score, index, text, "jira_comment_confirmed_root_cause"))
    if candidates:
        _, _, evidence, source = max(candidates, key=lambda item: (item[0], item[1]))
        return evidence, source
    return "", "missing"


def extract_explicit_test_evidence(
    *,
    field_value: str = "",
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    field_text = _clean(field_value)
    if field_text:
        return field_text[:2400], "jira_test_plan_field"
    candidates: list[tuple[int, int, str, str]] = []
    version_validations: list[str] = []
    entries = _comment_entries(comment_documents)
    for index, document in enumerate(entries):
        section = _extract_comment_section(document, r"qa\s+verification|verification")
        if section and _VERIFICATION_RESULT_RE.search(section):
            candidates.append((12, index, section, "jira_comment_qa_verification"))
        section = _extract_comment_section(document, r"after\s+fix")
        if section and _VERIFICATION_RESULT_RE.search(section):
            candidates.append((11, index, section, "jira_comment_after_fix"))
        text = _normalize_source_text(document)
        match = re.search(
            rf"(?is)\bverified\s+on\s+build[^\n]*(?:\n(?P<body>.+?))?(?=\n\s*(?:{_COMMENT_SECTION_HEADERS})\s*:?|\Z)",
            text,
        )
        if match:
            evidence = _clean(match.group(0))[:2400]
            if _VERIFICATION_RESULT_RE.search(evidence):
                candidates.append((12, index, evidence, "jira_comment_verified_build"))
        normalized = _clean(document)[:2400]
        if (
            _VERIFIED_VERSION_RE.search(normalized)
            or _HOTFIX_VERSION_VALIDATION_RE.search(normalized)
        ) and normalized not in version_validations:
            version_validations.append(normalized)
        acceptance_score = 0
        if _ACCEPTANCE_EXECUTION_RE.search(normalized):
            acceptance_score += 10
        if _EXECUTED_TEST_RE.search(normalized):
            acceptance_score += 12
        if acceptance_score:
            acceptance_score += 2 * int(bool(_VERIFICATION_RESULT_RE.search(normalized)))
            acceptance_score += 2 * int(
                bool(re.search(r"\b(?:disabled|progress\s+bar|common\s+tags?|select\s+all)\b", normalized, re.I))
            )
            candidates.append(
                (acceptance_score, index, normalized, "jira_comment_acceptance_validation")
            )
        if _CUSTOMER_VALIDATION_RE.search(normalized):
            candidates.append((9, index, normalized, "jira_comment_customer_validation"))
    if version_validations:
        candidates.append(
            (
                10,
                len(entries),
                " | ".join(version_validations)[:2400],
                "jira_comment_version_validation",
            )
        )
    if candidates:
        _, _, evidence, source = max(candidates, key=lambda item: (item[0], item[1]))
        return evidence, source
    return "", "missing"


def extract_release_scope_evidence(
    *,
    comment_documents: list[str] | tuple[str, ...] = (),
) -> tuple[str, str]:
    """Return an explicit mainline-UAC versus hotfix point-fix boundary."""
    candidates: list[tuple[int, str]] = []
    entries = _comment_entries(comment_documents)
    for index, document in enumerate(entries):
        normalized = _normalize_source_text(document)
        if not (
            _HOTFIX_ONLY_SCOPE_RE.search(normalized)
            and _MAINLINE_UAC_SCOPE_RE.search(normalized)
            and _HOTFIX_POINT_FIX_RE.search(normalized)
        ):
            continue
        relevant_lines = [
            _clean(line)
            for line in normalized.splitlines()
            if _HOTFIX_ONLY_SCOPE_RE.search(line)
            or _MAINLINE_UAC_SCOPE_RE.search(line)
            or _HOTFIX_POINT_FIX_RE.search(line)
        ]
        evidence = _clean(" ".join(relevant_lines))[:1200]
        if evidence:
            candidates.append((index, evidence))
    if candidates:
        return candidates[-1][1], "jira_comment_release_scope"
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
                or _FUNCTIONAL_SCOPE_HEADER_RE.match(line)
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
        if _FUNCTIONAL_SCOPE_HEADER_RE.match(line):
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
    release_scope_evidence: str = "",
    release_scope_source: str = "",
    acceptance_source: str = "",
) -> HistoricalUacAnalysis | None:
    source_text = _normalize_source_text(acceptance_criteria)
    if not jira_key.strip() or not source_text or is_no_uac_sentinel(source_text):
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
    resolved_release_scope_source = release_scope_source.strip() or (
        "jira_comment_release_scope" if _clean(release_scope_evidence) else "missing"
    )
    release_scope_split = bool(_clean(release_scope_evidence)) and resolved_release_scope_source != "missing"
    if release_scope_split:
        contradictions = tuple(
            dict.fromkeys(
                (
                    *contradictions,
                    "Accepted UAC is scoped to a separate mainline release; this Jira is explicitly limited to a hotfix point fix.",
                )
            )
        )
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
    if release_scope_split:
        reuse_tier = "candidate"
    normalized_labels = {_normalized_label(label) for label in labels or []}
    source_authority = (
        "jira_accepted_uac" if normalized_labels & _ACCEPTED_UAC_LABELS else "jira_acceptance_field"
    )
    source_origin = acceptance_source.strip() or "jira_acceptance_field"
    return HistoricalUacAnalysis(
        jira_key=jira_key.strip().upper(),
        source_hash=source_hash,
        source_authority=source_authority,
        source_origin=source_origin,
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
        release_scope_evidence=_clean(release_scope_evidence)[:1200],
        release_scope_source=resolved_release_scope_source,
        release_scope_split=release_scope_split,
    )


def _base_metadata(analysis: HistoricalUacAnalysis) -> dict[str, Any]:
    return {
        "uac_schema_version": UAC_SCHEMA_VERSION,
        "uac_analysis_method": UAC_ANALYSIS_METHOD,
        "uac_llm_used": False,
        "uac_source_hash": analysis.source_hash,
        "uac_source_authority": analysis.source_authority,
        "uac_source_origin": analysis.source_origin,
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
        "uac_release_scope_split": analysis.release_scope_split,
        "uac_release_scope_source": analysis.release_scope_source,
    }


def historical_uac_contract_dict(
    analysis: HistoricalUacAnalysis,
    *,
    acceptance_criteria: str = "",
    root_cause: str = "",
    test_evidence: str = "",
) -> dict[str, Any]:
    """Serialize a deterministic, automation-safe historical UAC contract."""

    def clause_payload(clause: HistoricalUacClause) -> dict[str, Any]:
        return {
            "source_id": clause.source_id,
            "stable_key": clause.stable_key,
            "text": clause.text,
            "kind": clause.kind,
            "dimensions": list(clause.dimensions),
            "unresolved": clause.unresolved,
            "unresolved_reasons": list(clause.unresolved_reasons),
            "citation": f"JIRA:{analysis.jira_key}:UAC:{clause.source_id}:{analysis.source_hash}",
        }

    if analysis.release_scope_split or analysis.reuse_tier == "candidate":
        allowed_uses = ["regression_signal", "open_question"]
        reuse_mode = "risk_signal_only"
    elif analysis.reuse_tier == "historical_verified" and analysis.contract_complete:
        allowed_uses = ["regression_signal", "proposed_ac_seed", "test_matrix_seed"]
        reuse_mode = "historical_verified_contract"
    else:
        allowed_uses = ["regression_signal", "open_question", "proposed_ac_seed"]
        reuse_mode = "supporting_uac_contract"

    clauses = [clause_payload(clause) for clause in analysis.clauses]
    return {
        "schema_version": UAC_SCHEMA_VERSION,
        "analysis_method": UAC_ANALYSIS_METHOD,
        "jira_key": analysis.jira_key,
        "source_snapshot_id": f"jira:{analysis.jira_key}:uac:{analysis.source_hash}",
        "source_hash": analysis.source_hash,
        "source_authority": analysis.source_authority,
        "source_origin": analysis.source_origin,
        "historical_outcome": analysis.historical_outcome,
        "reuse_tier": analysis.reuse_tier,
        "reuse_mode": reuse_mode,
        "allowed_uses": allowed_uses,
        "confirmed_ac_eligible": False,
        "current_ticket_authority": False,
        "contract_complete": analysis.contract_complete,
        "source_truncated": analysis.source_truncated,
        "issue_closed": analysis.issue_closed,
        "clauses": clauses,
        "in_scope_clause_ids": [clause.source_id for clause in analysis.in_scope_clauses],
        "out_of_scope_clause_ids": [clause.source_id for clause in analysis.out_of_scope_clauses],
        "reference_clause_ids": [clause.source_id for clause in analysis.reference_clauses],
        "context_clause_ids": [clause.source_id for clause in analysis.context_clauses],
        "unresolved_clause_ids": [clause.source_id for clause in analysis.unresolved_clauses],
        "contradictions": list(analysis.contradictions),
        "dimensions": list(analysis.dimensions),
        "performance": {
            "matters": analysis.performance_matters,
            "contract_complete": analysis.performance_contract_complete,
        },
        "root_cause": {
            "text": _clean(root_cause)[:1200],
            "source": analysis.root_cause_source,
            "explicit": analysis.explicit_root_cause,
        },
        "test_evidence": {
            "text": _clean(test_evidence)[:1200],
            "source": analysis.test_evidence_source,
            "explicit": analysis.explicit_test_evidence,
        },
        "release_scope": {
            "split": analysis.release_scope_split,
            "source": analysis.release_scope_source,
            "evidence": analysis.release_scope_evidence,
        },
        "source_excerpt": _clean(acceptance_criteria)[:1200],
        "reuse_rule": (
            "Historical UAC may seed Proposed criteria and regression coverage only. "
            "It can never create a Confirmed criterion for the current Jira."
        ),
    }


def current_uac_contract_dict(
    analysis: HistoricalUacAnalysis,
    *,
    accepted_label_present: bool,
    field_id: str = "",
    field_name: str = "Acceptance Criteria",
    mutable_fields_verified_live: bool = True,
) -> dict[str, Any]:
    """Serialize current-ticket UAC with a fail-closed automation approval decision."""
    contract = historical_uac_contract_dict(analysis)
    confirmed_eligible = bool(
        accepted_label_present
        and analysis.contract_complete
        and not analysis.source_truncated
        and not analysis.contradictions
        and not analysis.release_scope_split
    )
    contract.update(
        {
            "schema_version": CURRENT_UAC_SCHEMA_VERSION,
            "analysis_schema_version": UAC_SCHEMA_VERSION,
            "source_authority": "jira_accepted_uac" if accepted_label_present else "jira_draft_uac",
            "source_field_id": field_id,
            "source_field_name": field_name,
            "current_ticket_authority": True,
            "confirmed_ac_eligible": confirmed_eligible,
            "automation_consumption": "approved" if confirmed_eligible else "blocked",
            "approval_status": (
                "accepted"
                if confirmed_eligible
                else "invalid_accepted_contract"
                if accepted_label_present
                else "draft"
            ),
            "allowed_uses": (
                ["confirmed_ac", "test_matrix", "regression_boundary"]
                if confirmed_eligible
                else ["proposed_ac", "open_question", "regression_boundary"]
            ),
            "mutable_fields_verified_live": mutable_fields_verified_live,
            "reuse_rule": (
                "Only this current-ticket contract may create Confirmed ACs, and only when "
                "confirmed_ac_eligible=true. Historical contracts remain Proposed-only."
            ),
        }
    )
    return contract


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
    if analysis.release_scope_split:
        contract_lines.append(
            "Release-scope boundary: the accepted UAC belongs to a separate mainline release; only the explicitly listed hotfix point fix may be reused for this Jira."
        )
        contract_lines.append(f"Release-scope source: {analysis.release_scope_source}")
        contract_lines.append(f"Release-scope evidence: {analysis.release_scope_evidence}")
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
