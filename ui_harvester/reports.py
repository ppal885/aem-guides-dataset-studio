"""Serialize harvest results: metadata JSONL, graphs, RAG records, and reports."""

import json
from pathlib import Path

from . import rag_records, taxonomy, transitions as trans_mod
from .surface_resolution import make_surface_identity

GAP_CLASSES = (
    "NOT_DISCOVERED", "DISCOVERED_BUT_BLOCKED", "MISSING_FIXTURE",
    "AUTHORIZATION_REQUIRED", "CONFIGURATION_REQUIRED", "MUTATION_REQUIRED",
    "VISION_REQUIRED", "FAILED_TO_LOAD", "OUTSIDE_SAFE_CRAWL",
)


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_metadata(result, output_dir):
    meta = Path(output_dir) / "metadata"
    states = [s.to_dict() for s in result.states.values()]
    trans = [t.to_dict() for t in result.transitions]
    flows = trans_mod.extract_flow_paths(result.transitions)
    caps = [{"identity_key": c, "capability": v.get("capability", c),
             "surface": v.get("surface", ""), "route_identity": v.get("route_identity", ""),
             "lifecycle": v.get("lifecycle", "VERSION_UNKNOWN"),
             "state_count": len(v["states"])}
            for c, v in sorted(result.capabilities.items())]
    _write_jsonl(meta / "states.jsonl", states)
    _write_jsonl(meta / "transitions.jsonl", trans)
    _write_jsonl(meta / "flows.jsonl", flows)
    _write_jsonl(meta / "capabilities.jsonl", caps)
    _write_jsonl(meta / "vision_candidates.jsonl", result.vision_candidates)
    return flows


def write_graphs(result, output_dir, flows):
    graph = Path(output_dir) / "graph"
    graph.mkdir(parents=True, exist_ok=True)
    # Route-scoped surface topology: same capability on different routes stays distinct.
    surface_graph = {}
    for identity_key, v in result.capabilities.items():
        surface_graph[identity_key] = {
            "surface": v.get("surface") or "UNKNOWN",
            "route_identity": v.get("route_identity", ""),
            "lifecycle": v.get("lifecycle", "VERSION_UNKNOWN"),
            "capabilities": [v.get("capability", identity_key)],
        }
    (graph / "ui_surface_graph.json").write_text(json.dumps(surface_graph, indent=2, ensure_ascii=False), encoding="utf-8")
    # state graph: nodes + edges
    state_graph = {
        "nodes": [{"state_id": s.state_id, "surface": s.surface,
                   "route_identity": s.route_identity, "lifecycle": s.currentness,
                   "dialog": s.open_dialog,
                   "menu": s.open_menu, "screenshot_id": s.screenshot_id}
                  for s in result.states.values()],
        "edges": [{"from": t.from_state_id, "to": t.to_state_id, "relation": t.relation,
                   "action": (t.action or {}).get("capability", ""), "authority": t.authority}
                  for t in result.transitions],
    }
    (graph / "ui_state_graph.json").write_text(json.dumps(state_graph, indent=2, ensure_ascii=False), encoding="utf-8")
    (graph / "ui_flow_graph.json").write_text(json.dumps({"flows": flows}, indent=2, ensure_ascii=False), encoding="utf-8")


def build_rag_records(result, flows):
    records = []
    for s in result.states.values():
        records.append(rag_records.state_record(s))
    for t in result.transitions:
        records.append(rag_records.transition_record(t))
    for f in flows:
        records.append(rag_records.flow_record(f))
    for identity_key, value in sorted(result.capabilities.items()):
        surface = make_surface_identity(
            value.get("capability", identity_key),
            value.get("surface", ""),
            value.get("route_identity", ""),
            lifecycle=value.get("lifecycle", "VERSION_UNKNOWN"),
        )
        records.append(rag_records.surface_identity_record(surface))
    for parent, relation, child in taxonomy.PRODUCT_HIERARCHY_EDGES:
        records.append(rag_records.hierarchy_record(parent, relation, child))
    for parent, relation, child in taxonomy.CAPABILITY_HIERARCHY_EDGES:
        records.append(rag_records.hierarchy_record(
            parent, relation, child, hierarchy_type="CAPABILITY"
        ))
    for dependency in taxonomy.CONFIGURATION_DEPENDENCIES:
        records.append(rag_records.configuration_dependency_record(**dependency))
    return records


def write_reports(result, output_dir, flows):
    rep = Path(output_dir) / "reports"
    rep.mkdir(parents=True, exist_ok=True)
    summ = result.summary()

    by_surface = {}
    for s in result.states.values():
        by_surface.setdefault(s.surface or "UNKNOWN", 0)
        by_surface[s.surface or "UNKNOWN"] += 1

    coverage = ["# UI coverage", "", f"- Unique states: {summ['unique_states']}",
                f"- Transitions: {summ['transitions']}", f"- Capabilities: {summ['capabilities']}",
                f"- Control patterns observed across states", "", "## States by surface"]
    for surf, n in sorted(by_surface.items()):
        coverage.append(f"- {surf}: {n} state(s)")
    coverage += ["", "Note: this is NOT a claim of 100% product UI coverage."]
    (rep / "coverage.md").write_text("\n".join(coverage) + "\n", encoding="utf-8")

    flow_lines = ["# Flow coverage", "", f"- Observed workflows: {len(flows)}", ""]
    for i, f in enumerate(flows, 1):
        chain = " -> ".join(step["action"] or "action" for step in f["steps"])
        flow_lines.append(f"{i}. ({f.get('surface') or 'UNKNOWN'}) {chain}  [OBSERVED_UI_FLOW]")
    (rep / "flow_coverage.md").write_text("\n".join(flow_lines) + "\n", encoding="utf-8")

    gaps = ["# Gaps", "", "Missing/unexplored areas classified (not merely 'not covered'):", ""]
    if result.auth_status != "OK":
        gaps.append(f"- AUTHORIZATION_REQUIRED: {result.auth_status}")
    if result.unknown_actions:
        gaps.append(f"- OUTSIDE_SAFE_CRAWL: {len(result.unknown_actions)} UNKNOWN action(s) not auto-clicked")
    if result.blocked_actions:
        gaps.append(f"- MUTATION_REQUIRED: {len(result.blocked_actions)} destructive action(s) observed but not executed")
    if result.vision_candidates:
        gaps.append(f"- VISION_REQUIRED: {len(result.vision_candidates)} ambiguous surface(s)")
    if result.failures:
        gaps.append(f"- FAILED_TO_LOAD: {len(result.failures)} failure(s) - see failures.md")
    (rep / "gaps.md").write_text("\n".join(gaps) + "\n", encoding="utf-8")

    _write_md_table(rep / "blocked_actions.md", "# Blocked actions", result.blocked_actions)
    _write_md_table(rep / "failures.md", "# Failures", result.failures)
    dup = ["# Duplicate report", "", f"- Duplicate states skipped (already captured): {result.duplicates_skipped}"]
    (rep / "duplicate_report.md").write_text("\n".join(dup) + "\n", encoding="utf-8")


def _write_md_table(path, title, rows):
    lines = [title, ""]
    if not rows:
        lines.append("- none")
    else:
        for r in rows:
            lines.append("- " + ", ".join(f"{k}={v}" for k, v in r.items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
