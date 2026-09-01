"""Evidence-backed typed behavior graph.

Graph discovery produces investigation candidates.  It never turns an inferred
edge into accepted product behaviour; authority and promotion are separate gates.
"""

from __future__ import annotations

import re
import json
from collections.abc import Mapping
from pathlib import Path


SCHEMA_VERSION = "aem-guides-behavior-graph-v1"

RELATION_TYPES = (
    "DEFINED_BY", "CONFIGURED_BY", "GOVERNED_BY", "CONTROLLING_ATTRIBUTE",
    "REQUIRES", "REQUIRES_ACTIVE_CONTEXT", "CONSUMED_BY", "SIBLING_CONSUMER_OF",
    "ALTERNATE_MECHANISM_TO", "FILTERED_BY", "CONTROLS_ELIGIBILITY", "PARENT_OF",
    "CHILD_OF", "SPECIALIZED_BY", "REFERENCES", "RESOLVES_THROUGH", "PROCESSED_BY",
    "GENERATED_BY", "PUBLISHED_BY", "AFFECTS_OUTPUT_OF", "CALLS", "DELEGATES_TO",
    "EXECUTED_BY", "READ_BY", "WRITTEN_BY", "CACHED_BY", "INVALIDATED_BY",
    "REFRESHED_BY", "PERSISTS_THROUGH", "SYNCHRONIZED_WITH", "AVAILABLE_IN",
    "VERSION_DEPENDENT", "DEPLOYMENT_DEPENDENT", "ROLE_DEPENDENT",
    "FEATURE_FLAG_DEPENDENT",
)

NODE_KINDS = (
    "PRODUCT_BEHAVIOR", "CONTENT", "DITA_ENTITY", "CONFIGURATION", "ATTRIBUTE",
    "UI_SURFACE", "API", "PROCESSOR", "SERVICE", "PERSISTED_STATE", "GENERATED_ARTIFACT",
    "PRESET", "PROFILE", "ROLE", "DEPLOYMENT", "VERSION", "OTHER",
)
CURRENTNESS = ("CURRENT", "HISTORICAL", "UNKNOWN")
APPLICABILITY = ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED")
VERIFICATION_STATES = ("INVESTIGATION_CANDIDATE", "CONFIRMED", "REJECTED", "UNRESOLVED")


def _authority_policy():
    path = Path(__file__).with_name("data") / "authority_policy.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("subjects", {})


SUBJECT_POLICIES = _authority_policy()


def _string_list(value, *, nonempty=False):
    return (
        isinstance(value, list)
        and (not nonempty or bool(value))
        and all(isinstance(x, str) and x.strip() for x in value)
    )


def validate_behavior_graph(block, *, evidence_ids=None, open_question_ids=None):
    problems = []
    if not isinstance(block, Mapping):
        return ["behavior_graph must be an object"]
    if block.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"behavior_graph.schema_version must be {SCHEMA_VERSION}")
    nodes = block.get("nodes")
    edges = block.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return problems + ["behavior_graph.nodes must be a non-empty list"]
    if not isinstance(edges, list):
        return problems + ["behavior_graph.edges must be a list"]
    node_ids = set()
    material_nodes = set()
    known_evidence = None if evidence_ids is None else set(evidence_ids)
    known_questions = None if open_question_ids is None else set(open_question_ids)
    for index, node in enumerate(nodes):
        tag = f"behavior_graph.nodes[{index}]"
        if not isinstance(node, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        node_id = str(node.get("node_id", ""))
        if not re.fullmatch(r"BGN-\d{2}", node_id):
            problems.append(f"{tag}.node_id must use stable BGN-## form")
        elif node_id in node_ids:
            problems.append(f"{tag}.node_id duplicates {node_id}")
        node_ids.add(node_id)
        if node.get("kind") not in NODE_KINDS:
            problems.append(f"{tag}.kind must be one of {', '.join(NODE_KINDS)}")
        if not str(node.get("label", "")).strip():
            problems.append(f"{tag}.label must be non-empty")
        if not isinstance(node.get("material"), bool):
            problems.append(f"{tag}.material must be a boolean")
        elif node.get("material"):
            material_nodes.add(node_id)
        if not _string_list(node.get("provenance"), nonempty=True):
            problems.append(f"{tag}.provenance must be a non-empty string list")
        elif known_evidence is not None and any(
            ref not in known_evidence for ref in node.get("provenance", [])
        ):
            problems.append(f"{tag}.provenance contains an unknown evidence reference")

    edge_ids = set()
    for index, edge in enumerate(edges):
        tag = f"behavior_graph.edges[{index}]"
        if not isinstance(edge, Mapping):
            problems.append(f"{tag} must be an object")
            continue
        edge_id = str(edge.get("edge_id", ""))
        if not re.fullmatch(r"BGE-\d{2}", edge_id):
            problems.append(f"{tag}.edge_id must use stable BGE-## form")
        elif edge_id in edge_ids:
            problems.append(f"{tag}.edge_id duplicates {edge_id}")
        edge_ids.add(edge_id)
        for endpoint in ("source", "target"):
            if edge.get(endpoint) not in node_ids:
                problems.append(f"{tag}.{endpoint} must reference a declared behavior node")
        if edge.get("relation_type") not in RELATION_TYPES:
            problems.append(f"{tag}.relation_type must be one of the canonical typed relations")
        if not _string_list(edge.get("provenance"), nonempty=True):
            problems.append(f"{tag}.provenance must be a non-empty string list")
        subject = str(edge.get("subject", "")).strip()
        authority = str(edge.get("authority", "")).strip()
        if subject not in SUBJECT_POLICIES:
            problems.append(
                f"{tag}.subject must be one of {', '.join(SUBJECT_POLICIES)}"
            )
        if not authority:
            problems.append(f"{tag}.authority must be non-empty")
        elif subject in SUBJECT_POLICIES and authority not in set(
            SUBJECT_POLICIES[subject].get("ranking", [])
        ):
            problems.append(
                f"{tag}.authority {authority!r} is not valid for subject {subject}"
            )
        if _string_list(edge.get("provenance"), nonempty=True) and known_evidence is not None and any(
            ref not in known_evidence for ref in edge.get("provenance", [])
        ):
            problems.append(f"{tag}.provenance contains an unknown evidence reference")
        if edge.get("currentness") not in CURRENTNESS:
            problems.append(f"{tag}.currentness must be one of {', '.join(CURRENTNESS)}")
        if edge.get("applicability") not in APPLICABILITY:
            problems.append(f"{tag}.applicability must be one of {', '.join(APPLICABILITY)}")
        confidence = edge.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            problems.append(f"{tag}.confidence must be between 0 and 1")
        state = edge.get("verification_state")
        if state not in VERIFICATION_STATES:
            problems.append(f"{tag}.verification_state must be one of {', '.join(VERIFICATION_STATES)}")
        if not isinstance(edge.get("material"), bool):
            problems.append(f"{tag}.material must be a boolean")
        if state == "INVESTIGATION_CANDIDATE" and not str(edge.get("hypothesis_ref", "")).strip():
            problems.append(f"{tag}: investigation candidates require hypothesis_ref")
        if state == "CONFIRMED" and authority == "INFERENCE":
            problems.append(f"{tag}: graph inference cannot become CONFIRMED without evidence authority")
        if state == "UNRESOLVED":
            ref = str(edge.get("open_question_ref", "")).strip()
            if not ref or (known_questions is not None and ref not in known_questions):
                problems.append(f"{tag}: UNRESOLVED edge requires a declared open_question_ref")

    paths = block.get("traversal_paths", [])
    if not isinstance(paths, list):
        problems.append("behavior_graph.traversal_paths must be a list")
    else:
        for index, path in enumerate(paths):
            tag = f"behavior_graph.traversal_paths[{index}]"
            if not isinstance(path, Mapping):
                problems.append(f"{tag} must be an object")
                continue
            members = path.get("edge_refs")
            if not _string_list(members, nonempty=True):
                problems.append(f"{tag}.edge_refs must be a non-empty list")
                continue
            if len(members) > 4:
                problems.append(f"{tag} exceeds the bounded four-hop traversal limit")
            if any(ref not in edge_ids for ref in members):
                problems.append(f"{tag}.edge_refs contains an unknown edge")
    return problems


def material_item_ids(block):
    if not isinstance(block, Mapping):
        return []
    result = [
        node.get("node_id") for node in block.get("nodes", [])
        if isinstance(node, Mapping) and node.get("material") is True
    ]
    result.extend(
        edge.get("edge_id") for edge in block.get("edges", [])
        if isinstance(edge, Mapping) and edge.get("material") is True
    )
    return [str(x) for x in result if x]


def material_node_ids(block):
    if not isinstance(block, Mapping):
        return []
    return [
        str(node.get("node_id")) for node in block.get("nodes", [])
        if isinstance(node, Mapping) and node.get("material") is True and node.get("node_id")
    ]


def is_present(manifest):
    return isinstance(manifest, Mapping) and isinstance(manifest.get("behavior_graph"), Mapping)
