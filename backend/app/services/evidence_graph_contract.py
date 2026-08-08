"""Deterministic contracts shared by evidence graph adapters and queries."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit


GRAPH_SCHEMA_VERSION = "evidence-graph-v2"
GRAPH_STATE_KEY = "__evidence_graph__"
GRAPH_NAMESPACE = uuid.UUID("4e4bb281-4de3-4ef2-b694-4464ed6d99bd")

NODE_TYPES = frozenset(
    {
        "jira_issue",
        "customer",
        "component",
        "domain",
        "subdomain",
        "feature",
        "workflow",
        "output",
        "release",
        "documentation_page",
        "source_chunk",
        "dita_element",
        "dita_attribute",
        "behavior_claim",
        "symptom",
        "root_cause",
        "qa_oracle",
        "risk",
        "error_signature",
        "api_route",
        "config_key",
    }
)

RELATIONS = frozenset(
    {
        "HAS_CHUNK",
        "REPORTED_BY",
        "IN_COMPONENT",
        "IN_DOMAIN",
        "IN_SUBDOMAIN",
        "AFFECTS_FEATURE",
        "AFFECTS_OUTPUT",
        "AFFECTS_VERSION",
        "FIXED_IN_RELEASE",
        "APPLIES_TO_RELEASE",
        "DOCUMENTS_FEATURE",
        "DOCUMENTS_OUTPUT",
        "MENTIONS_DITA_ENTITY",
        "HAS_EXPECTED_BEHAVIOR",
        "HAS_ACTUAL_BEHAVIOR",
        "HAS_ROOT_CAUSE",
        "HAS_QA_ORACLE",
        "HAS_RISK",
        "HAS_ERROR_SIGNATURE",
        "USES_API_ROUTE",
        "USES_CONFIG_KEY",
        "ALLOWS_CHILD",
        "HAS_ATTRIBUTE",
        "SPECIALIZES",
        "CONSTRAINS",
        "BELONGS_TO_DOMAIN",
        "MENTIONS_ISSUE",
    }
)

TRUST_TIERS = frozenset({"authoritative", "historical_verified", "supporting", "candidate"})
TRUST_WEIGHTS = {
    "authoritative": 1.0,
    "historical_verified": 0.9,
    "supporting": 0.65,
    "candidate": 0.2,
}

NODE_PROPERTY_ALLOWLIST = {
    "jira_issue": frozenset(
        {
            "jira_key",
            "status",
            "resolution",
            "priority",
            "issue_type",
            "source_type",
            "jira_updated_at",
            "mutable_facts_require_live_validation",
        }
    ),
    "documentation_page": frozenset({"canonical_url", "source_type", "official"}),
    "source_chunk": frozenset({"collection", "chunk_id", "evidence_type"}),
    "release": frozenset({"channel", "version", "mutable_fact"}),
    "behavior_claim": frozenset(
        {"claim_role", "exact_source_text", "mechanism_signal", "cannot_define_expected_behavior"}
    ),
    "symptom": frozenset({"claim_role", "mechanism_signal"}),
    "root_cause": frozenset({"root_cause_source", "mechanism_signal"}),
    "qa_oracle": frozenset({"qa_oracle_source", "cannot_define_expected_behavior"}),
    "risk": frozenset({"cannot_define_expected_behavior"}),
    "error_signature": frozenset({"mechanism_signal"}),
    "api_route": frozenset({"mechanism_signal"}),
    "config_key": frozenset({"mechanism_signal"}),
    "domain": frozenset({"ranking_only"}),
    "subdomain": frozenset({"ranking_only"}),
    "feature": frozenset({"ranking_only"}),
    "dita_element": frozenset({"content_type"}),
    "dita_attribute": frozenset({"description"}),
}

EDGE_PROPERTY_ALLOWLIST = frozenset(
    {
        "ranking_only",
        "mechanism_signal",
        "cannot_define_expected_behavior",
        "claim_role",
        "root_cause_source",
        "qa_oracle_source",
        "requires_live_jira_validation",
        "mutable_fact",
        "exact_source_text",
        "channel",
        "version",
    }
)

MECHANISM_NODE_TYPES = frozenset(
    {"root_cause", "behavior_claim", "error_signature", "api_route", "config_key", "symptom"}
)

_WHITESPACE_RE = re.compile(r"\s+")
_SLUG_RE = re.compile(r"[^a-z0-9@._-]+")
_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_IMS_ORG_RE = re.compile(r"\b[0-9A-F]{24}@AdobeOrg\b", re.IGNORECASE)
_MENTION_RE = re.compile(r"\[(?:~accountid:[^\]]]+|~[^\]]+)\]")
_SECRET_RE = re.compile(
    r"(?i)\b(?:api[_ -]?key|access[_ -]?token|refresh[_ -]?token|client[_ -]?secret|password)\b"
    r"\s*[:=]\s*[^\s,;]+"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}")
_API_ROUTE_RE = re.compile(r"(?<![A-Za-z0-9])/(?:bin|api|libs|content|mnt)/[A-Za-z0-9_./{}:-]+")
_ERROR_RE = re.compile(
    r"\b(?:HTTP\s+[45]\d\d|[A-Za-z_$][\w.$]*(?:Exception|Error)|[A-Z][A-Z0-9_]{3,}_ERROR)\b"
)
_CONFIG_RE = re.compile(
    r"\b(?=[A-Z0-9_]*_)[A-Z][A-Z0-9_]{3,}\b|"
    r"\b[a-z][a-z0-9_.-]{2,}\.(?:enabled|timeout|limit|path|url)\b"
)


def normalize_text(value: Any) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "")).strip()


def normalized_token(value: Any) -> str:
    return _SLUG_RE.sub("-", normalize_text(value).casefold()).strip("-")


def stable_digest(*parts: Any, length: int = 32) -> str:
    payload = "\x1f".join(normalize_text(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()[:length]


def deterministic_id(*parts: Any) -> str:
    return str(uuid.uuid5(GRAPH_NAMESPACE, "\x1f".join(normalize_text(part) for part in parts)))


def canonical_url(value: Any) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return text
    if not parsed.scheme or not parsed.netloc:
        return text
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/":
        path = path.rstrip("/")
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, "", ""))


def stable_key(node_type: str, value: Any) -> str:
    if node_type not in NODE_TYPES:
        raise ValueError(f"Unsupported evidence graph node type: {node_type}")
    text = normalize_text(value)
    if node_type == "jira_issue":
        return f"jira:{text.upper()}"
    if node_type == "documentation_page":
        return f"doc:{stable_digest(canonical_url(text), length=40)}"
    if node_type == "source_chunk":
        return f"chunk:{stable_digest(text, length=40)}"
    if node_type == "release":
        channel, separator, version = text.partition(":")
        if not separator or not normalized_token(channel) or not normalized_token(version):
            raise ValueError("Release keys require '<channel>:<version>'.")
        return f"release:{normalized_token(channel)}:{normalized_token(version)}"
    if node_type in {"behavior_claim", "symptom", "root_cause", "qa_oracle", "risk", "error_signature"}:
        return f"{node_type}:{stable_digest(text.casefold(), length=40)}"
    return f"{node_type.replace('_', '-')}:{normalized_token(text)}"


def sanitize_excerpt(value: Any, *, max_chars: int = 1000) -> tuple[str, int]:
    text = normalize_text(value)
    redactions = 0
    for pattern, replacement in (
        (_MENTION_RE, "[redacted-mention]"),
        (_EMAIL_RE, "[redacted-email]"),
        (_IMS_ORG_RE, "[redacted-ims-org]"),
        (_SECRET_RE, "[redacted-secret]"),
        (_BEARER_RE, "Bearer [redacted-token]"),
    ):
        text, count = pattern.subn(replacement, text)
        redactions += count
    return text[: max(0, int(max_chars))], redactions


def contains_sensitive_text(value: Any) -> bool:
    text = str(value or "")
    return any(
        pattern.search(text)
        for pattern in (_EMAIL_RE, _IMS_ORG_RE, _MENTION_RE, _SECRET_RE, _BEARER_RE)
    )


def sanitize_structured_properties(
    node_type: str | None,
    properties: dict[str, Any] | None,
    *,
    edge: bool = False,
) -> tuple[dict[str, Any], int]:
    """Keep only approved scalar properties and redact bounded string values."""
    allowed = EDGE_PROPERTY_ALLOWLIST if edge else NODE_PROPERTY_ALLOWLIST.get(node_type or "", frozenset())
    clean: dict[str, Any] = {}
    redactions = 0
    for key, raw in dict(properties or {}).items():
        if key not in allowed or raw is None:
            continue
        if isinstance(raw, bool):
            clean[key] = raw
        elif isinstance(raw, (int, float)):
            clean[key] = raw
        elif isinstance(raw, str):
            value, count = sanitize_excerpt(raw, max_chars=1000)
            clean[key] = value
            redactions += count
    return clean, redactions


def json_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [normalize_text(item) for item in value if normalize_text(item)]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return [text]
        return json_values(decoded)
    return []


def exact_source_claim(claim: Any, source_text: Any) -> bool:
    normalized_claim = normalize_text(claim).casefold()
    normalized_source = normalize_text(source_text).casefold()
    return bool(normalized_claim and len(normalized_claim) >= 12 and normalized_claim in normalized_source)


def extract_api_routes(value: Any) -> list[str]:
    return sorted(set(_API_ROUTE_RE.findall(str(value or ""))))[:20]


def extract_error_signatures(value: Any) -> list[str]:
    return sorted(set(normalize_text(item) for item in _ERROR_RE.findall(str(value or ""))))[:20]


def extract_config_keys(value: Any) -> list[str]:
    return sorted(set(normalize_text(item) for item in _CONFIG_RE.findall(str(value or ""))))[:20]


@dataclass(frozen=True)
class EvidenceSpec:
    source_kind: str
    source_ref: str
    source_record_id: str
    source_hash: str
    extraction_method: str
    authority: str
    trust_tier: str
    excerpt: str = ""
    source_chunk_id: str = ""
    visibility: str = "internal"
    tenant_id: str | None = None
    source_updated_at: datetime | None = None

    def __post_init__(self):
        if self.trust_tier not in TRUST_TIERS:
            raise ValueError(f"Unsupported evidence graph trust tier: {self.trust_tier}")


@dataclass
class NodeSpec:
    stable_key: str
    node_type: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)
    visibility: str = "internal"
    tenant_id: str | None = None
    evidence: list[EvidenceSpec] = field(default_factory=list)

    def __post_init__(self):
        if self.node_type not in NODE_TYPES:
            raise ValueError(f"Unsupported evidence graph node type: {self.node_type}")


@dataclass
class EdgeSpec:
    source_key: str
    relation: str
    target_key: str
    trust_tier: str
    confidence: float
    properties: dict[str, Any] = field(default_factory=dict)
    evidence: list[EvidenceSpec] = field(default_factory=list)

    def __post_init__(self):
        if self.relation not in RELATIONS:
            raise ValueError(f"Unsupported evidence graph relation: {self.relation}")
        if self.trust_tier not in TRUST_TIERS:
            raise ValueError(f"Unsupported evidence graph trust tier: {self.trust_tier}")
