"""Turn recorded relationship findings into individually reviewable candidates.

This is not a source-code scanner or an applicability verifier. It reads only the
manifest's existing construct_relationships records. It never opens source files,
claims an inspection, marks evidence USED, or promotes a finding to an AC.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from relationship_traversal import CODE_NEIGHBORHOOD_CATEGORIES, RELATION_TYPES


GENERATOR = "CODE_NEIGHBORHOOD"
_CODE_SOURCE = re.compile(r"^(?P<path>.+[\\/].+):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_CHUNK_SOURCE = re.compile(r"^chunk_id:(?P<id>[^\s:][^\s]*)$")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _name(value: str) -> str:
    return " ".join(value.casefold().split())


def _path_identity(value: str) -> str:
    """Compare path spellings without resolving or reading the file system."""
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("\\\\"):
        return value.replace("\\", "/").casefold()
    return value


def _source_parts(source: str) -> tuple[str, str, int | None, int | None] | None:
    chunk = _CHUNK_SOURCE.fullmatch(source)
    if chunk:
        return ("chunk", chunk.group("id"), None, None)
    code = _CODE_SOURCE.fullmatch(source)
    if code:
        # This parser accepts citations, not unbounded numeric payloads. A malformed
        # line token must not crash the surrounding best-effort discovery pass.
        if len(code.group("start")) > 12 or len(code.group("end") or "") > 12:
            return None
        start = int(code.group("start"))
        end = int(code.group("end") or start)
        if start > 0 and end >= start:
            return ("code", _path_identity(code.group("path")), start, end)
    return None


def _catalog_entries(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    catalog = manifest.get("evidence_catalog")
    if isinstance(catalog, Mapping):
        catalog = catalog.get("sources") or catalog.get("entries")
    if not isinstance(catalog, list):
        return []
    return [entry for entry in catalog if isinstance(entry, Mapping)]


def _evidence_ids(source: str, catalog: list[Mapping[str, Any]]) -> list[str]:
    """Bind only declared catalog identities, not newly invented evidence IDs.

    A file-wide catalog entry can bind a line citation. If both records specify
    lines, their ranges must overlap; another line in the same file is not enough.
    Matching a declaration does not attest that its source was inspected.
    """
    wanted = _source_parts(source)
    if wanted is None:
        return []
    result: list[str] = []
    for entry in catalog:
        evidence_id = _text(entry.get("id")) or _text(entry.get("source_id"))
        reference = _text(entry.get("source_ref"))
        if not evidence_id or not reference:
            continue
        actual = _source_parts(reference)
        matches = actual == wanted
        if wanted[0] == "code":
            if actual and actual[0] == "code" and actual[1] == wanted[1]:
                matches = actual[2] <= wanted[3] and wanted[2] <= actual[3]
            elif actual is None:
                matches = _path_identity(reference) == wanted[1]
        if matches and evidence_id not in result:
            result.append(evidence_id)
    return result


def _valid_record(record: Any, *, code_only: bool = False) -> bool:
    if not isinstance(record, Mapping) or not _text(record.get("neighbor")):
        return False
    source = _source_parts(_text(record.get("source")))
    return source is not None and (not code_only or source[0] == "code")


def _same_neighbor(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        _name(_text(left.get("neighbor"))) == _name(_text(right.get("neighbor")))
        and _source_parts(_text(left.get("source"))) == _source_parts(_text(right.get("source")))
    )


def candidates_for(manifest: Any) -> list[dict[str, Any]]:
    """Emit one advisory coverage hypothesis for each exact recorded neighbor.

    Sweep findings are retained even when their disposition edge is missing.
    Matching edges are folded into the finding, not emitted a second time. The
    recorded disposition is preserved as context only; it never becomes a verdict.
    Malformed records generate no invented neighbor, source, or relationship.
    """
    if not isinstance(manifest, Mapping):
        return []
    block = manifest.get("construct_relationships")
    if not isinstance(block, Mapping):
        return []
    raw_edges = block.get("edges")
    edges = [
        edge for edge in raw_edges
        if _valid_record(edge) and edge.get("relation_type") in RELATION_TYPES
    ] if isinstance(raw_edges, list) else []
    catalog = _catalog_entries(manifest)
    candidates: list[dict[str, Any]] = []
    emitted: set[str] = set()
    matched_edges: set[int] = set()

    def emit(record: Mapping[str, Any], category: str, allowed: tuple[str, ...],
             edge: Mapping[str, Any] | None = None) -> None:
        neighbor = _text(record.get("neighbor"))
        source = _text(record.get("source"))
        relation = _text(edge.get("relation_type")) if edge is not None else ""
        identity = [category, _name(neighbor), _source_parts(source), relation, allowed]
        digest = hashlib.sha256(json.dumps(identity, ensure_ascii=True).encode("utf-8")).hexdigest()[:24]
        key = f"CODE_NEIGHBORHOOD:RECORDED:{digest}"
        if key in emitted:
            return
        emitted.add(key)
        evidence_ids = _evidence_ids(source, catalog)
        configuration = allowed == ("SIBLING_CONFIG",)
        item: dict[str, Any] = {
            "hypothesis_id": "",
            "dimension": "CONFIGURATION" if configuration else "CONSUMER",
            "implied_dimension_axis": "CONFIG_BRANCH" if configuration else "CODE_PATH_CONSUMER",
            "candidate": f"Investigate whether {neighbor} is affected by the changed behavior.",
            "reason": "A recorded one-hop neighbor requires its own evidence-backed scope decision.",
            "technical_basis": [f"Recorded {category} neighbor: {neighbor}", f"source:{source}"],
            "current_evidence": evidence_ids,
            "generator": GENERATOR,
            "equivalence_key": key,
            "status": "INVESTIGATION_CANDIDATE",
            "requires_more_evidence": True,
            "confidence": 0.0,
            "authority_class": "SUPPORTING_DISCOVERY",
            "advisory_only": True,
            "authoritative": False,
            "neighbor": neighbor,
            "discovery_category": category,
            "discovered_source": source,
            "relation_type": relation,
            "allowed_relation_types": list(allowed),
            "evidence_binding_status": "CATALOG_REFERENCE_MATCH" if evidence_ids else "MISSING_CATALOG_BINDING",
        }
        if edge is not None:
            item["recorded_disposition"] = {
                field: _text(edge.get(field))
                for field in ("disposition", "ac_ref", "open_question_ref", "reason")
                if _text(edge.get(field))
            }
        candidates.append(item)

    discovery = block.get("discovery")
    sweep = discovery.get("code_neighborhood_sweep") if isinstance(discovery, Mapping) else None
    if isinstance(sweep, Mapping):
        for category, allowed in CODE_NEIGHBORHOOD_CATEGORIES.items():
            record = sweep.get(category)
            findings = record.get("findings") if isinstance(record, Mapping) else None
            if not isinstance(findings, list):
                continue
            for finding in findings:
                if not _valid_record(finding, code_only=True):
                    continue
                matches = [
                    (index, edge) for index, edge in enumerate(edges)
                    if edge.get("relation_type") in allowed and _same_neighbor(finding, edge)
                ]
                if not matches:
                    emit(finding, category, allowed)
                for index, edge in matches:
                    matched_edges.add(index)
                    emit(finding, category, allowed, edge)
    for index, edge in enumerate(edges):
        if index not in matched_edges:
            emit(edge, "recorded_edges", (edge["relation_type"],), edge)
    return candidates
