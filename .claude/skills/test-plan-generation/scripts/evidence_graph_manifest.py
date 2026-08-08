"""Deterministic evidence-graph manifest validation shared by the skill gate."""

from __future__ import annotations

from typing import Any


GRAPH_TOOL = "query_test_evidence_graph"
GRAPH_STATUSES = frozenset({"ready", "degraded", "unavailable", "disabled", "not_requested"})
GRAPH_INFLUENCE_MODES = frozenset({"off", "shadow", "augment"})


def _non_empty_strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _leaf_id(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("leaf_id") or "").strip()


def validate_evidence_graph_manifest(data: dict) -> list[str]:
    """Validate graph traceability without making graph availability a plan blocker."""
    failures: list[str] = []
    graph = data.get("evidence_graph")
    if not isinstance(graph, dict):
        return ["evidence_graph must be an object describing graph status and queries"]

    if graph.get("tool") != GRAPH_TOOL:
        failures.append(f"evidence_graph.tool must be '{GRAPH_TOOL}'")
    status = str(graph.get("status") or "").strip()
    if status not in GRAPH_STATUSES:
        failures.append("evidence_graph.status must be ready, degraded, unavailable, disabled, or not_requested")
    if not isinstance(graph.get("requested"), bool):
        failures.append("evidence_graph.requested must be true or false")
    influence_mode = str(graph.get("influence_mode") or "").strip()
    if influence_mode not in GRAPH_INFLUENCE_MODES:
        failures.append("evidence_graph.influence_mode must be off, shadow, or augment")
    used_for_plan = graph.get("used_for_plan")
    if not isinstance(used_for_plan, bool):
        failures.append("evidence_graph.used_for_plan must be true or false")
    if influence_mode in {"off", "shadow"} and used_for_plan is True:
        failures.append(f"evidence_graph.used_for_plan must be false in {influence_mode or 'unknown'} mode")
    if used_for_plan is True and influence_mode != "augment":
        failures.append("only augment evidence_graph mode may set used_for_plan=true")

    queries = graph.get("queries")
    if not isinstance(queries, list):
        failures.append("evidence_graph.queries must be a list")
        queries = []
    if status == "ready":
        if not str(graph.get("generation_id") or "").strip():
            failures.append("ready evidence_graph requires generation_id")
        if not queries:
            failures.append("ready evidence_graph requires at least one recorded query")
    elif status in {"degraded", "unavailable", "disabled"}:
        if not str(graph.get("degraded_reason") or "").strip():
            failures.append(f"{status} evidence_graph requires degraded_reason")
    elif status == "not_requested":
        if graph.get("requested") is not False:
            failures.append("not_requested evidence_graph requires requested=false")
        if not str(graph.get("not_requested_reason") or "").strip():
            failures.append("not_requested evidence_graph requires not_requested_reason")

    if graph.get("requested") is False and status != "not_requested":
        failures.append("evidence_graph.requested=false requires status=not_requested")
    if graph.get("requested") is True and status == "not_requested":
        failures.append("evidence_graph.requested=true cannot use status=not_requested")
    if influence_mode == "off" and graph.get("requested") is not False:
        failures.append("off evidence_graph mode requires requested=false")
    if graph.get("requested") is False and influence_mode != "off":
        failures.append("evidence_graph.requested=false requires influence_mode=off")

    all_path_ids: set[str] = set()
    all_leaf_ids: set[str] = set()
    for index, item in enumerate(queries):
        if not isinstance(item, dict):
            failures.append(f"evidence_graph.queries[{index}] must be an object")
            continue
        if not str(item.get("query") or "").strip():
            failures.append(f"evidence_graph.queries[{index}] is missing query")
        if not isinstance(item.get("duration_ms"), int) or item.get("duration_ms", -1) < 0:
            failures.append(f"evidence_graph.queries[{index}].duration_ms must be a non-negative integer")
        if not isinstance(item.get("cache_hit"), bool):
            failures.append(f"evidence_graph.queries[{index}].cache_hit must be true or false")
        path_ids = item.get("path_ids", [])
        leaf_citations = item.get("leaf_citations", [])
        if not _non_empty_strings(path_ids):
            failures.append(f"evidence_graph.queries[{index}].path_ids must be a list of non-empty strings")
            path_ids = []
        if not isinstance(leaf_citations, list):
            failures.append(f"evidence_graph.queries[{index}].leaf_citations must be a list")
            leaf_citations = []
        leaf_ids = [_leaf_id(citation) for citation in leaf_citations]
        if any(not leaf_id for leaf_id in leaf_ids):
            failures.append(
                f"evidence_graph.queries[{index}].leaf_citations entries require leaf_id and source provenance"
            )
        for citation_index, citation in enumerate(leaf_citations):
            if not isinstance(citation, dict):
                continue
            required = ("leaf_id", "source_type", "source_ref", "trust_tier")
            missing = [key for key in required if not str(citation.get(key) or "").strip()]
            if missing:
                failures.append(
                    f"evidence_graph.queries[{index}].leaf_citations[{citation_index}] missing {', '.join(missing)}"
                )
            if str(citation.get("leaf_id") or "").startswith(("path:", "graph-path:")):
                failures.append("graph path IDs cannot be recorded as leaf evidence")
        if path_ids and not leaf_ids:
            failures.append(
                f"evidence_graph.queries[{index}] records graph paths without underlying leaf citations"
            )
        all_path_ids.update(path_ids)
        all_leaf_ids.update(leaf_id for leaf_id in leaf_ids if leaf_id)

    if len(all_path_ids) != sum(
        len(item.get("path_ids", [])) for item in queries if isinstance(item, dict) and isinstance(item.get("path_ids", []), list)
    ):
        failures.append("evidence_graph path_ids must be unique across recorded queries")
    if len(all_leaf_ids) != sum(
        len(item.get("leaf_citations", []))
        for item in queries
        if isinstance(item, dict) and isinstance(item.get("leaf_citations", []), list)
    ):
        failures.append("evidence_graph leaf_citations must be deduplicated by leaf_id")
    if used_for_plan is True and not all_leaf_ids:
        failures.append("evidence_graph.used_for_plan=true requires at least one underlying leaf citation")
    return failures
