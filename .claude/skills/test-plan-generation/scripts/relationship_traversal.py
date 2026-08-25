"""Validate evidence-grounded one-hop relationship traversal.

This module is the umbrella for construct-specific relationship checks.  It does
not contain a construct-to-neighbour truth table.  Instead, callers record the
one-hop neighbours found in source code and in an evidence corpus, then this
module makes every recorded neighbour end in an acceptance criterion, an open
question, or an explicit out-of-scope decision.

The canonical ``construct_relationships`` block is::

    {
      "schema_version": "aem-guides-construct-relationships-v1",
      "construct": {"slug": "stable-slug", "label": "Readable label"},
      "edges": [
        {
          "relation_type": "CONSUMER",
          "neighbor_kind": "UI_SURFACE",
          "neighbor": "A neighbouring capability or surface",
          "source": "chunk_id:corpus-chunk-42",
          "disposition": "COVERED_BY_AC",
          "ac_ref": "AC-01"
        }
      ],
      "cross_dimensions": {
        "PERFORMANCE": {"applicable": false, "reason": "Grounded reason"},
        "SECURITY": {"applicable": false, "reason": "Grounded reason"},
        "PERMISSIONS": {"applicable": false, "reason": "Grounded reason"},
        "UPGRADE": {"applicable": false, "reason": "Grounded reason"},
        "CONCURRENCY": {"applicable": false, "reason": "Grounded reason"}
      },
      "discovery": {
        "code_search_terms": ["ExactSymbol", "exact-config-key"],
        "corpus_relation_queries": ["relations.source:stable-slug"],
        "clones_searched": ["C:/source/clone"],
        "code_neighborhood_sweep": {
          "affected_artifacts": ["C:/source/clone/path/config.json"],
          "sibling_config_keys": {
            "searched": true,
            "findings": [
              {
                "neighbor": "A sibling key",
                "source": "C:/source/clone/path/config.json:27"
              }
            ]
          },
          "sibling_ui_options": {
            "searched": true,
            "findings": [],
            "none_found_reason": "The affected artifact has no UI options."
          },
          "callers_and_same_path_processors": {
            "searched": true,
            "findings": [],
            "none_found_reason": "The call-site search found no other caller."
          }
        }
      }
    }

Honest limit: the code-neighbourhood sweep can find only relationships reachable
by the exact recorded search terms in the recorded clones.  An indirect or
unrecorded relationship can still escape it.  It does, however, turn a
grep-surfaced sibling, option, caller, or same-path processor into a finding that
must be dispositioned instead of something the plan can silently omit.  Likewise,
the corpus helper traverses explicit relation metadata; no returned candidates
does not prove that no relationship exists.

Stdlib only.  The module validates evidence; it never edits a test plan.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from typing import Any


SCHEMA_VERSION = "aem-guides-construct-relationships-v1"

RELATION_TYPES = (
    "CONSUMER",
    "PRODUCER",
    "SIBLING_CONFIG",
    "CALLER",
    "PRECONDITION",
)

NEIGHBOR_KINDS = (
    "UI_SURFACE",
    "SERVICE",
    "CONFIGURATION",
    "CALL_SITE",
    "PRIVILEGE",
    "OTHER",
)

DISPOSITIONS = (
    "COVERED_BY_AC",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
)

CROSS_DIMENSIONS = (
    "PERFORMANCE",
    "SECURITY",
    "PERMISSIONS",
    "UPGRADE",
    "CONCURRENCY",
)

CODE_NEIGHBORHOOD_CATEGORIES: dict[str, tuple[str, ...]] = {
    "sibling_config_keys": ("SIBLING_CONFIG",),
    "sibling_ui_options": ("SIBLING_CONFIG",),
    "callers_and_same_path_processors": ("CALLER", "CONSUMER"),
}

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CODE_SOURCE_RE = re.compile(r"^(?P<path>.+[\\/].+):(?P<line>\d+)(?:-\d+)?$")
_CHUNK_SOURCE_RE = re.compile(r"^chunk_id:(?P<chunk_id>[^\s:][^\s]*)$")
_REFERENCE_RE = re.compile(r"\b(?P<kind>AC|OQ)-(?P<number>\d+)\b", re.IGNORECASE)
_AC_LINE_RE = re.compile(
    r"(?m)^- (?P<id>AC-\d{2}) \[(?:Confirmed|Proposed)\]: "
    r"\((?P<sphere>Basic|Negative|Integration|Performance)\) (?P<text>.+)$"
)
_QUANTIFIED_ORACLE_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|x|ms|s|sec(?:ond)?s?|min(?:ute)?s?|"
    r"documents?|topics?|maps?|assets?|pages?|users?|requests?|jobs?)\b",
    re.IGNORECASE,
)
_ORACLE_AUTHORITY_RE = re.compile(
    r"\b(?:baseline|sla|threshold|limit|at\s+most|at\s+least|percentile|p\d{2})\b",
    re.IGNORECASE,
)
_NON_WORKLOAD_NUMBER_RE = re.compile(
    r"\b[A-Z][A-Z0-9]+-\d+\b|"
    r"\b(?:build|version|revision|commit|line|sha)\s*[#:=]?\s*[A-Za-z0-9._-]+|"
    r"\bv?\d+(?:\.\d+){1,}\b|"
    r"\b\d{4}-\d{2}-\d{2}\b|"
    r"\b[0-9a-f]{7,40}\b",
    re.IGNORECASE,
)
_FILE_LINE_TOKEN_RE = re.compile(r"\S+[\\/][^\s|]+:\d+(?:-\d+)?")
_URL_TOKEN_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_IDENTIFIER_NUMBER_RE = re.compile(
    r"\b(?:pr|pull\s+request|program|environment|tenant|customer|profile|issue|ticket)"
    r"\s*(?:id\s*)?[#:=]?\s*\d+\b|#\d{3,}\b",
    re.IGNORECASE,
)


# Signals are generic categories, never a feature or construct mapping.
_REVIEW_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "code-list/service/servlet signal",
        re.compile(
            r"\b(?:[A-Z][A-Za-z0-9]*(?:List|Service|Servlet)|"
            r"(?:list|service|servlet)\s+(?:class|implementation|handler|endpoint))\b"
        ),
    ),
    (
        "settings/configuration JSON signal",
        re.compile(
            r"(?:\b(?:settings?|config(?:uration)?)\b[^\n]{0,80}\.json\b|"
            r"\b[^\s]+(?:settings?|config)[^\s]*\.json\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "attribute/element model signal",
        re.compile(
            r"\b(?:attribute|element)\s+(?:list|model|registry|configuration|definition)s?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "permission/group check signal",
        re.compile(
            r"\b(?:permission|privilege|authorization|access|group(?:\s+membership)?)\b"
            r"[^\n]{0,80}\b(?:check|verify|member|allow|deny|grant|withhold|require)d?\b",
            re.IGNORECASE,
        ),
    ),
)

_PERFORMANCE_SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("bulk", re.compile(r"\b(?:bulk|batch|in\s+bulk)\b", re.IGNORECASE)),
    ("single click", re.compile(r"\bsingle[- ]click\b|\bin\s+(?:a|one)\s+click\b", re.IGNORECASE)),
    ("three-or-more-digit quantity", re.compile(r"(?<![\w.])\d{3,}(?![\w.])")),
    ("abbreviated large quantity", re.compile(r"(?<![\w.])\d+(?:\.\d+)?\s*k\b", re.IGNORECASE)),
    (
        "scaled entity count",
        re.compile(
            r"\b(?:n|many|multiple|large\s+(?:number|volume)\s+of|\d+(?:\.\d+)?\s*k?)\s+"
            r"(?:documents?|topics?|maps?|assets?|pages?|users?)\b",
            re.IGNORECASE,
        ),
    ),
    ("proportional growth", re.compile(r"\bproportion(?:al)?\s+to\b", re.IGNORECASE)),
    ("log size", re.compile(r"\blog\s+file\s+size\b", re.IGNORECASE)),
    (
        "runtime performance",
        re.compile(r"\b(?:concurren(?:cy|t)|throughput|latency|timeouts?|response\s+time)\b", re.IGNORECASE),
    ),
    ("large content unit", re.compile(r"\blarge\s+(?:map|topic)\b", re.IGNORECASE)),
)


def _nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty_string_list(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_string(item) for item in value)
    )


def is_present(manifest: Any) -> bool:
    """Return whether a manifest explicitly declares the optional umbrella block."""
    return isinstance(manifest, Mapping) and "construct_relationships" in manifest


def _normalise_name(value: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(value).casefold()))


def _source_kind(value: Any) -> str:
    """Return ``code``, ``corpus``, or an empty string for a grounding source."""
    if not _nonempty_string(value):
        return ""
    source = value.strip()
    if _CHUNK_SOURCE_RE.fullmatch(source):
        return "corpus"
    match = _CODE_SOURCE_RE.fullmatch(source)
    if match and match.group("path").strip() and int(match.group("line")) > 0:
        return "code"
    return ""


def _collect_text(value: Any) -> str:
    """Flatten strings without relying on a particular manifest sub-schema."""
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return "\n".join(_collect_text(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return "\n".join(_collect_text(item) for item in value)
    return ""


def _context_text(manifest: Mapping[str, Any] | None, issue_text: Any, behavior_model: Any) -> str:
    parts = [_collect_text(issue_text), _collect_text(behavior_model)]
    if isinstance(manifest, Mapping):
        for key in (
            "issue",
            "issue_text",
            "issue_description",
            "description",
            "problem_statement",
            "behavior_model",
        ):
            if key in manifest:
                parts.append(_collect_text(manifest[key]))
    return "\n".join(part for part in parts if part)


def _known_references(
    explicit: Iterable[str] | None,
    plan_text: str,
    kind: str,
) -> set[str] | None:
    if explicit is not None:
        return {str(item).strip() for item in explicit if str(item).strip()}
    if not plan_text:
        return None
    return {
        f"{match.group('kind').upper()}-{match.group('number')}"
        for match in _REFERENCE_RE.finditer(plan_text)
        if match.group("kind").upper() == kind
    }


def _validate_disposition(
    entry: Mapping[str, Any],
    tag: str,
    *,
    ac_ids: set[str] | None,
    open_question_ids: set[str] | None,
    allow_out_of_scope: bool,
) -> list[str]:
    problems: list[str] = []
    disposition = entry.get("disposition")
    allowed = DISPOSITIONS if allow_out_of_scope else DISPOSITIONS[:2]
    if disposition not in allowed:
        return [f"{tag}.disposition must be one of {allowed}"]

    if disposition == "COVERED_BY_AC":
        ref = str(entry.get("ac_ref", "")).strip()
        if not ref:
            problems.append(f"{tag}: COVERED_BY_AC requires ac_ref")
        elif ac_ids is not None and ref not in ac_ids:
            problems.append(f"{tag}.ac_ref {ref!r} does not exist in the plan")
    elif disposition == "OPEN_QUESTION":
        ref = str(entry.get("open_question_ref", "")).strip()
        if not ref:
            problems.append(f"{tag}: OPEN_QUESTION requires open_question_ref")
        elif open_question_ids is not None and ref not in open_question_ids:
            problems.append(
                f"{tag}.open_question_ref {ref!r} does not exist in the plan"
            )
    elif not str(entry.get("reason", "")).strip():
        problems.append(f"{tag}: OUT_OF_SCOPE requires a non-empty reason")
    return problems


def detect_performance_signals(
    value: Any = "",
    *,
    behavior_model: Any = "",
) -> list[str]:
    """Return the generic scale/performance signals present in supplied evidence."""
    text = "\n".join((_collect_text(value), _collect_text(behavior_model)))
    # Ticket IDs, versions, dates, SHAs and source line numbers are evidence
    # identifiers, not workload cardinalities. Remove them before applying the
    # deliberately broad numeric signal family.
    text = _URL_TOKEN_RE.sub(" ", text)
    text = _FILE_LINE_TOKEN_RE.sub(" ", text)
    text = _IDENTIFIER_NUMBER_RE.sub(" ", text)
    text = _NON_WORKLOAD_NUMBER_RE.sub(" ", text)
    return [label for label, pattern in _PERFORMANCE_SIGNAL_PATTERNS if pattern.search(text)]


def _open_question_text(manifest: Mapping[str, Any], question_id: str) -> str:
    for entry in manifest.get("open_questions") or []:
        if isinstance(entry, Mapping) and str(entry.get("id", "")) == question_id:
            return " ".join(
                str(entry.get(key, "")) for key in ("question", "qa_impact")
            )
    return ""


def validate_performance_dimension(
    block_or_manifest: Any, *, plan_text: str = ""
) -> list[str]:
    """Align the PERFORMANCE relationship dimension with its measurable oracle."""
    manifest = block_or_manifest if isinstance(block_or_manifest, Mapping) else {}
    block = manifest.get("construct_relationships", manifest)
    if not isinstance(block, Mapping):
        return []
    dimensions = block.get("cross_dimensions")
    performance = dimensions.get("PERFORMANCE") if isinstance(dimensions, Mapping) else None
    if not isinstance(performance, Mapping) or not isinstance(
        performance.get("applicable"), bool
    ):
        return []

    problems: list[str] = []
    assessment = manifest.get("performance_assessment")
    decision = assessment.get("decision") if isinstance(assessment, Mapping) else None
    if performance.get("applicable") is False:
        if decision in {"required", "conditional"}:
            problems.append(
                "PERFORMANCE.applicable false conflicts with performance_assessment.decision "
                f"{decision!r}"
            )
        return problems

    disposition = performance.get("disposition")
    if disposition == "COVERED_BY_AC":
        ac_ref = str(performance.get("ac_ref", ""))
        match = next(
            (
                candidate
                for candidate in _AC_LINE_RE.finditer(plan_text)
                if candidate.group("id") == ac_ref
            ),
            None,
        )
        if match is not None:
            if match.group("sphere") != "Performance":
                problems.append(
                    f"PERFORMANCE {ac_ref} must use the Performance sphere"
                )
            ac_text = match.group("text")
            if not _QUANTIFIED_ORACLE_RE.search(ac_text) or not _ORACLE_AUTHORITY_RE.search(ac_text):
                problems.append(
                    f"PERFORMANCE {ac_ref} needs a quantified baseline-relative or approved-SLA threshold"
                )
        if decision is not None and decision != "required":
            problems.append(
                "PERFORMANCE covered by an AC requires performance_assessment.decision='required'"
            )
        if isinstance(assessment, Mapping) and ac_ref not in set(
            assessment.get("performance_ac_ids") or []
        ):
            problems.append(
                f"PERFORMANCE {ac_ref} must be listed in performance_assessment.performance_ac_ids"
            )
    elif disposition == "OPEN_QUESTION":
        oq_ref = str(performance.get("open_question_ref", ""))
        if isinstance(manifest, Mapping) and "open_questions" in manifest:
            question_text = _open_question_text(manifest, oq_ref)
            if question_text and not _ORACLE_AUTHORITY_RE.search(question_text):
                problems.append(
                    f"PERFORMANCE {oq_ref} must ask for the baseline, SLA, or measurable threshold"
                )
        if decision is not None and decision != "conditional":
            problems.append(
                "PERFORMANCE exposed as an Open Question requires performance_assessment.decision='conditional'"
            )
    return problems


def detect_relationship_review_signals(value: Any) -> list[str]:
    """Detect evidence that should trigger a non-blocking traversal REVIEW note."""
    text = _collect_text(value)
    return [label for label, pattern in _REVIEW_SIGNAL_PATTERNS if pattern.search(text)]


def relationship_review_note(manifest: Any, *, behavior_model: Any = "") -> str | None:
    """Return a REVIEW note when relationship-like evidence has no declared block."""
    if not isinstance(manifest, Mapping):
        return None
    if isinstance(manifest.get("construct_relationships"), Mapping):
        return None
    context = _context_text(manifest, "", behavior_model)
    signals = detect_relationship_review_signals(context)
    if not signals:
        return None
    return (
        "REVIEW: relationship-like evidence was detected "
        f"({', '.join(signals)}), but construct_relationships is not declared; "
        "run the code and corpus one-hop traversal."
    )


def _validate_edges(
    edges: Any,
    *,
    ac_ids: set[str] | None,
    open_question_ids: set[str] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    problems: list[str] = []
    valid_edges: list[dict[str, Any]] = []
    if not isinstance(edges, list):
        return ["construct_relationships.edges must be a list"], valid_edges

    seen: set[tuple[str, str, str]] = set()
    for index, edge in enumerate(edges):
        tag = f"construct_relationships.edges[{index}]"
        if not isinstance(edge, dict):
            problems.append(f"{tag} must be an object")
            continue
        relation_type = edge.get("relation_type")
        if relation_type not in RELATION_TYPES:
            problems.append(f"{tag}.relation_type must be one of {RELATION_TYPES}")
        neighbor_kind = edge.get("neighbor_kind")
        if neighbor_kind is not None and neighbor_kind not in NEIGHBOR_KINDS:
            problems.append(f"{tag}.neighbor_kind must be one of {NEIGHBOR_KINDS}")
        neighbor = str(edge.get("neighbor", "")).strip()
        if not neighbor:
            problems.append(f"{tag}.neighbor must be non-empty")
        source = str(edge.get("source", "")).strip()
        if not _source_kind(source):
            problems.append(
                f"{tag}.source must be a code file:line or chunk_id:<stable-id>"
            )
        problems.extend(
            _validate_disposition(
                edge,
                tag,
                ac_ids=ac_ids,
                open_question_ids=open_question_ids,
                allow_out_of_scope=True,
            )
        )
        identity = (str(relation_type), _normalise_name(neighbor), source)
        if all(identity) and identity in seen:
            problems.append(f"{tag} duplicates a relation_type/neighbor/source edge")
        seen.add(identity)
        valid_edges.append(edge)
    return problems, valid_edges


def _validate_cross_dimensions(
    value: Any,
    *,
    ac_ids: set[str] | None,
    open_question_ids: set[str] | None,
) -> list[str]:
    problems: list[str] = []
    if not isinstance(value, dict):
        return ["construct_relationships.cross_dimensions must be an object"]
    for dimension in CROSS_DIMENSIONS:
        tag = f"construct_relationships.cross_dimensions.{dimension}"
        entry = value.get(dimension)
        if not isinstance(entry, dict):
            problems.append(f"{tag} must be present as an object")
            continue
        applicable = entry.get("applicable")
        if not isinstance(applicable, bool):
            problems.append(f"{tag}.applicable must be true or false")
            continue
        if applicable:
            problems.extend(
                _validate_disposition(
                    entry,
                    tag,
                    ac_ids=ac_ids,
                    open_question_ids=open_question_ids,
                    allow_out_of_scope=False,
                )
            )
        elif not str(entry.get("reason", "")).strip():
            problems.append(f"{tag}: applicable false requires a non-empty reason")
    return problems


def _finding_matches_edge(
    finding: Mapping[str, Any],
    edges: Iterable[Mapping[str, Any]],
    allowed_relation_types: tuple[str, ...],
) -> bool:
    wanted_neighbor = _normalise_name(finding.get("neighbor", ""))
    wanted_source = str(finding.get("source", "")).strip()
    return any(
        edge.get("relation_type") in allowed_relation_types
        and _normalise_name(edge.get("neighbor", "")) == wanted_neighbor
        and str(edge.get("source", "")).strip() == wanted_source
        for edge in edges
    )


def _validate_code_neighborhood(
    value: Any,
    *,
    edges: list[dict[str, Any]],
) -> list[str]:
    problems: list[str] = []
    tag = "construct_relationships.discovery.code_neighborhood_sweep"
    if not isinstance(value, dict):
        return [f"{tag} must be an object"]

    artifacts = value.get("affected_artifacts")
    if not _nonempty_string_list(artifacts):
        problems.append(f"{tag}.affected_artifacts must be a non-empty string list")

    for category, allowed_types in CODE_NEIGHBORHOOD_CATEGORIES.items():
        category_tag = f"{tag}.{category}"
        record = value.get(category)
        if not isinstance(record, dict):
            problems.append(f"{category_tag} must be present as an object")
            continue
        if record.get("searched") is not True:
            problems.append(f"{category_tag}.searched must be true")
        findings = record.get("findings")
        if not isinstance(findings, list):
            problems.append(f"{category_tag}.findings must be a list")
            continue
        if not findings and not str(record.get("none_found_reason", "")).strip():
            problems.append(
                f"{category_tag}: no findings requires a non-empty none_found_reason"
            )
        for index, finding in enumerate(findings):
            finding_tag = f"{category_tag}.findings[{index}]"
            if not isinstance(finding, dict):
                problems.append(f"{finding_tag} must be an object")
                continue
            neighbor = str(finding.get("neighbor", "")).strip()
            source = str(finding.get("source", "")).strip()
            if not neighbor:
                problems.append(f"{finding_tag}.neighbor must be non-empty")
            if _source_kind(source) != "code":
                problems.append(f"{finding_tag}.source must be a code file:line")
            if neighbor and _source_kind(source) == "code" and not _finding_matches_edge(
                finding, edges, allowed_types
            ):
                problems.append(
                    f"{finding_tag} is not dispositioned by a matching "
                    f"{'/'.join(allowed_types)} edge with the same neighbor and source"
                )
    return problems


def _validate_discovery(
    value: Any,
    *,
    edges: list[dict[str, Any]],
) -> list[str]:
    problems: list[str] = []
    tag = "construct_relationships.discovery"
    if not isinstance(value, dict):
        return [f"{tag} must be an object"]
    for key in ("code_search_terms", "corpus_relation_queries", "clones_searched"):
        if not _nonempty_string_list(value.get(key)):
            problems.append(f"{tag}.{key} must be a non-empty string list")
    problems.extend(
        _validate_code_neighborhood(value.get("code_neighborhood_sweep"), edges=edges)
    )
    return problems


def validate_construct_relationships(
    block_or_manifest: Any,
    *,
    ac_ids: Iterable[str] | None = None,
    open_question_ids: Iterable[str] | None = None,
    plan_text: str = "",
    issue_text: Any = "",
    behavior_model: Any = "",
) -> list[str]:
    """Validate a block and return hard-gate failure strings.

    ``block_or_manifest`` may be the block itself or a manifest containing a
    ``construct_relationships`` member.  A manifest with no member cleanly skips;
    use :func:`check_relationship_traversal` when the non-blocking REVIEW note is
    also wanted.
    """
    manifest: Mapping[str, Any] | None = None
    if isinstance(block_or_manifest, Mapping) and "construct_relationships" in block_or_manifest:
        manifest = block_or_manifest
        block = block_or_manifest.get("construct_relationships")
    elif isinstance(block_or_manifest, Mapping) and any(
        key in block_or_manifest for key in ("schema_version", "construct", "edges")
    ):
        block = block_or_manifest
    elif isinstance(block_or_manifest, Mapping):
        return []
    else:
        return ["construct_relationships must be an object"]

    if not isinstance(block, dict):
        return ["construct_relationships must be an object"]

    known_ac_ids = _known_references(ac_ids, plan_text, "AC")
    known_oq_ids = _known_references(open_question_ids, plan_text, "OQ")
    problems: list[str] = []

    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"construct_relationships.schema_version must be {SCHEMA_VERSION}")

    construct = block.get("construct")
    if not isinstance(construct, dict):
        problems.append("construct_relationships.construct must be an object")
    else:
        slug = str(construct.get("slug", "")).strip()
        if not _SLUG_RE.fullmatch(slug):
            problems.append(
                "construct_relationships.construct.slug must be a stable lowercase slug"
            )
        if not str(construct.get("label", "")).strip():
            problems.append("construct_relationships.construct.label must be non-empty")

    edge_problems, valid_edges = _validate_edges(
        block.get("edges"),
        ac_ids=known_ac_ids,
        open_question_ids=known_oq_ids,
    )
    problems.extend(edge_problems)

    discovery = block.get("discovery")
    edges = block.get("edges")
    if isinstance(edges, list) and not edges:
        exhausted = isinstance(discovery, dict) and discovery.get("exhausted") is True
        note = ""
        if isinstance(discovery, dict):
            note = str(
                discovery.get("note", discovery.get("exhausted_note", ""))
            ).strip()
        if not exhausted or not note:
            problems.append(
                "construct_relationships.edges must be non-empty, or discovery.exhausted "
                "must be true with a non-empty note"
            )

    cross_dimensions = block.get("cross_dimensions")
    problems.extend(
        _validate_cross_dimensions(
            cross_dimensions,
            ac_ids=known_ac_ids,
            open_question_ids=known_oq_ids,
        )
    )
    problems.extend(_validate_discovery(discovery, edges=valid_edges))

    if manifest is not None and any(
        edge.get("relation_type") == "CONSUMER"
        and edge.get("neighbor_kind") == "UI_SURFACE"
        for edge in valid_edges
    ) and not isinstance(manifest.get("ui_surface_scope"), Mapping):
        problems.append(
            "UI_SURFACE CONSUMER edges require ui_surface_scope so every catalog "
            "surface is dispositioned"
        )

    context = _context_text(manifest, issue_text, behavior_model)
    performance_signals = detect_performance_signals(context)
    if performance_signals:
        performance = (
            cross_dimensions.get("PERFORMANCE")
            if isinstance(cross_dimensions, Mapping)
            else None
        )
        if not isinstance(performance, Mapping) or performance.get("applicable") is not True:
            problems.append(
                "PERFORMANCE.applicable must be true with an AC or open-question "
                "disposition because scale/performance evidence was detected: "
                + ", ".join(performance_signals)
            )
    problems.extend(validate_performance_dimension(manifest or block, plan_text=plan_text))
    return problems


def check_relationship_traversal(
    manifest: Any,
    *,
    ac_ids: Iterable[str] | None = None,
    open_question_ids: Iterable[str] | None = None,
    plan_text: str = "",
    issue_text: Any = "",
    behavior_model: Any = "",
) -> tuple[list[str], list[str]]:
    """Return ``(failures, review_notes)`` for a manifest or a direct block."""
    if not isinstance(manifest, Mapping):
        return [], []
    if any(key in manifest for key in ("construct", "edges", "cross_dimensions")):
        return (
            validate_construct_relationships(
                manifest,
                ac_ids=ac_ids,
                open_question_ids=open_question_ids,
                plan_text=plan_text,
                issue_text=issue_text,
                behavior_model=behavior_model,
            ),
            [],
        )
    if "construct_relationships" not in manifest:
        note = relationship_review_note(manifest, behavior_model=behavior_model)
        return [], [note] if note else []
    return (
        validate_construct_relationships(
            manifest,
            ac_ids=ac_ids,
            open_question_ids=open_question_ids,
            plan_text=plan_text,
            issue_text=issue_text,
            behavior_model=behavior_model,
        ),
        [],
    )


def corpus_relation_queries(construct: str, capability: str = "") -> list[str]:
    """Build explicit relation-field queries; these are not similarity queries."""
    seeds = [item.strip() for item in (construct, capability) if item and item.strip()]
    queries: list[str] = []
    for seed in dict.fromkeys(seeds):
        escaped = seed.replace('"', '\\"')
        queries.extend(
            (
                f'relations.source:"{escaped}"',
                f'relations.target:"{escaped}"',
                f'relations.neighbor:"{escaped}"',
            )
        )
    return queries


def _relation_records(chunk: Mapping[str, Any]) -> list[Any]:
    records: list[Any] = []
    direct = chunk.get("relations")
    if isinstance(direct, list):
        records.extend(direct)
    elif direct is not None:
        records.append(direct)
    metadata = chunk.get("metadata")
    if isinstance(metadata, Mapping):
        nested = metadata.get("relations")
        if isinstance(nested, list):
            records.extend(nested)
        elif nested is not None:
            records.append(nested)
    return records


def _relation_type(value: Any) -> str:
    normalized = re.sub(r"[^A-Z]+", "_", str(value).upper()).strip("_")
    aliases = {
        "CONSUMES": "CONSUMER",
        "CONSUMED_BY": "CONSUMER",
        "PRODUCES": "PRODUCER",
        "PRODUCED_BY": "PRODUCER",
        "SIBLING": "SIBLING_CONFIG",
        "SIBLING_CONFIGURATION": "SIBLING_CONFIG",
        "CALLS": "CALLER",
        "CALLED_BY": "CALLER",
        "REQUIRES": "PRECONDITION",
        "DEPENDS_ON": "PRECONDITION",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in RELATION_TYPES else ""


def _chunk_id(chunk: Mapping[str, Any]) -> str:
    for candidate in (chunk.get("chunk_id"), chunk.get("id")):
        if _nonempty_string(candidate):
            return str(candidate).strip()
    metadata = chunk.get("metadata")
    if isinstance(metadata, Mapping) and _nonempty_string(metadata.get("chunk_id")):
        return str(metadata["chunk_id"]).strip()
    return ""


def _endpoint(record: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        if _nonempty_string(record.get(name)):
            return str(record[name]).strip()
    return ""


def _seed_matches(value: str, seeds: set[str]) -> bool:
    normalized = _normalise_name(value)
    return bool(normalized) and any(
        normalized == seed or normalized in seed or seed in normalized for seed in seeds
    )


def _parse_relation_string(record: str) -> tuple[str, str, str] | None:
    """Parse explicit ``source | relation | target`` or ``source -> target`` records."""
    pipe = [part.strip() for part in record.split("|")]
    if len(pipe) == 3 and all(pipe):
        return pipe[0], _relation_type(pipe[1]), pipe[2]
    arrow = [part.strip() for part in re.split(r"\s*(?:->|=>)\s*", record, maxsplit=1)]
    if len(arrow) == 2 and all(arrow):
        return arrow[0], "", arrow[1]
    return None


def corpus_relationship_candidates(
    construct: str,
    chunks: Iterable[Mapping[str, Any]],
    *,
    capability: str = "",
) -> list[dict[str, str]]:
    """Traverse explicit corpus relation records and return grounded neighbours.

    Free-text co-occurrence alone never produces a candidate.  Text is used only
    to bind a ``neighbor``-only relation record to the requested seed; endpoints,
    explicit neighbour metadata, and the returned ``chunk_id`` still do the
    grounding.  This keeps the helper a graph traversal rather than similarity
    search.
    """
    seeds = {
        _normalise_name(item)
        for item in (construct, capability)
        if _normalise_name(item)
    }
    if not seeds:
        return []

    candidates: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        if not isinstance(chunk, Mapping):
            continue
        chunk_id = _chunk_id(chunk)
        if not chunk_id:
            continue
        chunk_text = _collect_text(chunk.get("text", ""))
        text_names_seed = _seed_matches(chunk_text, seeds)
        for raw_record in _relation_records(chunk):
            source = ""
            target = ""
            neighbor = ""
            relation_type = ""
            candidate_kind = "capability"
            if isinstance(raw_record, Mapping):
                source = _endpoint(raw_record, ("source", "from", "subject", "construct"))
                target = _endpoint(raw_record, ("target", "to", "object"))
                neighbor = _endpoint(
                    raw_record,
                    ("neighbor", "neighbour", "capability", "surface", "related"),
                )
                relation_type = _relation_type(
                    _endpoint(raw_record, ("relation_type", "relation", "type", "kind"))
                )
                if _nonempty_string(raw_record.get("surface")):
                    candidate_kind = "surface"
            elif isinstance(raw_record, str):
                parsed = _parse_relation_string(raw_record)
                if parsed:
                    source, relation_type, target = parsed
            else:
                continue

            selected = ""
            if source and target:
                if _seed_matches(source, seeds) and not _seed_matches(target, seeds):
                    selected = target
                elif _seed_matches(target, seeds) and not _seed_matches(source, seeds):
                    selected = source
            elif neighbor and text_names_seed:
                selected = neighbor
            elif neighbor and source and _seed_matches(source, seeds):
                selected = neighbor

            if not selected or _seed_matches(selected, seeds):
                continue
            identity = (_normalise_name(selected), relation_type, chunk_id)
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(
                {
                    "neighbor": selected,
                    "relation_type": relation_type,
                    "kind": candidate_kind,
                    "source": f"chunk_id:{chunk_id}",
                    "chunk_id": chunk_id,
                }
            )
    return candidates


# Descriptive alias for callers that use a ``find_*`` naming convention.
find_corpus_relationship_candidates = corpus_relationship_candidates


def _self_test_block() -> dict[str, Any]:
    false_dimension = {"applicable": False, "reason": "No evidence makes this applicable."}
    return {
        "schema_version": SCHEMA_VERSION,
        "construct": {"slug": "label-registry", "label": "Label registry"},
        "edges": [
            {
                "relation_type": "SIBLING_CONFIG",
                "neighbor": "Sibling setting",
                "source": "C:/clone/config/settings.json:27",
                "disposition": "COVERED_BY_AC",
                "ac_ref": "AC-01",
            },
            {
                "relation_type": "CONSUMER",
                "neighbor": "Rendered summary",
                "source": "chunk_id:relation-42",
                "disposition": "OPEN_QUESTION",
                "open_question_ref": "OQ-01",
            },
        ],
        "cross_dimensions": {
            dimension: copy.deepcopy(false_dimension) for dimension in CROSS_DIMENSIONS
        },
        "discovery": {
            "code_search_terms": ["labelRegistry", "siblingSetting"],
            "corpus_relation_queries": ['relations.source:"label-registry"'],
            "clones_searched": ["C:/clone"],
            "code_neighborhood_sweep": {
                "affected_artifacts": ["C:/clone/config/settings.json"],
                "sibling_config_keys": {
                    "searched": True,
                    "findings": [
                        {
                            "neighbor": "Sibling setting",
                            "source": "C:/clone/config/settings.json:27",
                        }
                    ],
                },
                "sibling_ui_options": {
                    "searched": True,
                    "findings": [],
                    "none_found_reason": "The artifact does not define UI options.",
                },
                "callers_and_same_path_processors": {
                    "searched": True,
                    "findings": [],
                    "none_found_reason": "The exact caller search found no other caller.",
                },
            },
        },
    }


def run_self_tests() -> None:
    """Run strong, dependency-free smoke tests for the local module."""
    assert validate_construct_relationships({}, ac_ids={"AC-01"}) == []

    block = _self_test_block()
    assert validate_construct_relationships(
        block, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
    ) == []

    missing_terms = copy.deepcopy(block)
    missing_terms["discovery"]["code_search_terms"] = []
    assert any(
        "code_search_terms" in item
        for item in validate_construct_relationships(
            missing_terms, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        )
    )

    missing_dimension = copy.deepcopy(block)
    del missing_dimension["cross_dimensions"]["SECURITY"]
    assert any(
        "SECURITY" in item
        for item in validate_construct_relationships(
            missing_dimension, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        )
    )

    unknown_ref = copy.deepcopy(block)
    unknown_ref["edges"][0]["ac_ref"] = "AC-99"
    assert any(
        "does not exist" in item
        for item in validate_construct_relationships(
            unknown_ref, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        )
    )

    ui_manifest = {"construct_relationships": copy.deepcopy(block)}
    ui_manifest["construct_relationships"]["edges"][1]["neighbor_kind"] = "UI_SURFACE"
    assert any(
        "require ui_surface_scope" in item
        for item in validate_construct_relationships(
            ui_manifest, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        )
    )
    ui_manifest["ui_surface_scope"] = {"declared": True}
    assert validate_construct_relationships(
        ui_manifest, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
    ) == []

    unmatched_finding = copy.deepcopy(block)
    unmatched_finding["discovery"]["code_neighborhood_sweep"]["sibling_config_keys"][
        "findings"
    ][0]["neighbor"] = "Undispositioned sibling"
    assert any(
        "not dispositioned" in item
        for item in validate_construct_relationships(
            unmatched_finding, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        )
    )

    no_edges = copy.deepcopy(block)
    no_edges["edges"] = []
    no_edges["discovery"]["code_neighborhood_sweep"]["sibling_config_keys"] = {
        "searched": True,
        "findings": [],
        "none_found_reason": "No sibling keys were present.",
    }
    assert any(
        "edges must be non-empty" in item
        for item in validate_construct_relationships(no_edges)
    )
    no_edges["discovery"]["exhausted"] = True
    no_edges["discovery"]["note"] = "Both traversals returned no neighbour."
    assert validate_construct_relationships(no_edges) == []

    scaled = copy.deepcopy(block)
    failures = validate_construct_relationships(
        scaled,
        ac_ids={"AC-01"},
        open_question_ids={"OQ-01"},
        issue_text="A batch can contain 2500 documents and starts in a single click.",
    )
    assert any("PERFORMANCE.applicable must be true" in item for item in failures)
    scaled["cross_dimensions"]["PERFORMANCE"] = {
        "applicable": True,
        "disposition": "COVERED_BY_AC",
        "ac_ref": "AC-01",
    }
    assert validate_construct_relationships(
        scaled,
        ac_ids={"AC-01"},
        open_question_ids={"OQ-01"},
        issue_text="A batch can contain 2500 documents and starts in a single click.",
    ) == []

    review_manifest = {
        "issue": "The SettingsPanel.json configuration performs a permission check."
    }
    review_failures, review_notes = check_relationship_traversal(review_manifest)
    assert review_failures == [] and review_notes and review_notes[0].startswith("REVIEW:")

    chunks = [
        {
            "chunk_id": "graph-7",
            "text": "The label registry feeds the rendered summary.",
            "metadata": {
                "relations": [
                    {
                        "source": "label-registry",
                        "relation_type": "CONSUMER",
                        "target": "rendered-summary",
                        "surface": "rendered-summary",
                    }
                ]
            },
        },
        {
            "chunk_id": "similarity-only",
            "text": "The label registry appears near an unrelated feature.",
        },
    ]
    candidates = corpus_relationship_candidates("label-registry", chunks)
    assert candidates == [
        {
            "neighbor": "rendered-summary",
            "relation_type": "CONSUMER",
            "kind": "surface",
            "source": "chunk_id:graph-7",
            "chunk_id": "graph-7",
        }
    ]
    assert corpus_relation_queries("label-registry") == [
        'relations.source:"label-registry"',
        'relations.target:"label-registry"',
        'relations.neighbor:"label-registry"',
    ]


if __name__ == "__main__":
    run_self_tests()
    print("relationship_traversal self-tests: PASS")
