"""Create editable v3 graph, closure, question and evidence-binding scaffolds.

This is a local, deterministic authoring aid, not a planner or verifier. Existing
decisions are preserved; generated defaults require explicit author review.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import behavior_graph
import coverage_hypotheses
import evidence_binding
import missing_questions
import semantic_closure
from scaffold_support import AUTHOR_CONFIRM, next_id, object_list, pending_review, strings


def load_policy():
    """Load generic model-role vocabulary; never infer product relationships."""
    path = Path(__file__).with_name("data") / "v3_scaffold_policy.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(policy, dict) or policy.get("schema_version") != "aem-guides-v3-scaffold-policy-v1":
        raise ValueError("invalid v3 scaffold policy schema")
    defaults = policy.get("material_by_kind")
    if (not isinstance(defaults, dict) or set(defaults) != set(behavior_graph.NODE_KINDS)
            or any(not isinstance(value, bool) for value in defaults.values())):
        raise ValueError("scaffold policy requires a boolean material default for every canonical node kind")
    roles = policy.get("entity_fields")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("scaffold policy requires entity_fields")
    for field, role in roles.items():
        if (not isinstance(field, str) or not field.isidentifier() or not isinstance(role, dict)
                or role.get("kind") not in behavior_graph.NODE_KINDS
                or role.get("relation_type") not in behavior_graph.RELATION_TYPES
                or role.get("dimension") not in coverage_hypotheses.COVERAGE_DIMENSIONS):
            raise ValueError(f"invalid canonical vocabulary in scaffold policy field {field!r}")
    return policy


def _block(manifest, name, schema, fields):
    block = manifest.setdefault(name, {"schema_version": schema})
    if not isinstance(block, dict) or block.get("schema_version") != schema:
        raise ValueError(f"{name} requires schema_version={schema}")
    for field in fields:
        object_list(block.setdefault(field, []), f"{name}.{field}")
    return block


def scaffold_behavior_graph(manifest):
    """Append evidence-bound candidate nodes/edges, preserving authored rows."""
    model = manifest["behavior_model"]
    policy = load_policy()
    entries = evidence_binding.catalog_entries(manifest)
    available = {evidence_binding.entry_id(row) for row in entries
                 if str(row.get("availability") or row.get("status", "")).lower()
                 not in {"unavailable", "degraded", "not_available", "missing_source"}}
    facts = object_list(model.get("facts", []), "behavior_model.facts")
    evidence_map = model.get("entity_evidence", {})
    if not isinstance(evidence_map, dict):
        raise ValueError("behavior_model.entity_evidence must be an object")
    graph = _block(manifest, "behavior_graph", behavior_graph.SCHEMA_VERSION,
                   ("nodes", "edges", "traversal_paths"))
    nodes, edges = graph["nodes"], graph["edges"]
    for row in nodes:
        if not isinstance(row.get("node_id"), str) or not row["node_id"].strip() or not isinstance(row.get("label"), str):
            raise ValueError("existing behavior graph nodes require a non-empty node_id and a string label")
    hypotheses = object_list(manifest.setdefault("coverage_hypotheses", []), "coverage_hypotheses")
    gaps = []

    def provenance(key, label, explicit=None):
        refs = strings(explicit if explicit is not None else evidence_map.get(key, []), key + ".evidence_ids")
        if not refs:
            # Exact entity phrase in an authored fact, not an arbitrary catalog hit.
            refs = sorted({eid for fact in facts if label.casefold() in str(fact.get("fact", "")).casefold()
                           for eid in strings(fact.get("evidence_ids", []), "fact.evidence_ids")})
        unknown = set(refs) - available
        if unknown:
            gaps.append(f"{key}: unavailable/unknown evidence IDs: {', '.join(sorted(unknown))}")
        refs = [eid for eid in refs if eid in available]
        if not refs:
            gaps.append(f"{key}: bind entity_evidence to inspected catalog IDs; no provenance guessed.")
        return refs

    def node(key, label, kind, material, refs):
        row = next((row for row in nodes if row.get("scaffold_key") == key), None)
        if row is None:
            matches = [row for row in nodes if row.get("kind") == kind and row.get("label") == label]
            if len(matches) > 1:
                raise ValueError("ambiguous existing graph entities; assign scaffold_key before rerunning")
            row = matches[0] if matches else None
        if row is None:
            row = {"node_id": next_id(nodes, "node_id", "BGN"), "kind": kind, "label": label,
                   "material": material, "provenance": refs, "scaffold_key": key,
                   "verification_state": "INVESTIGATION_CANDIDATE",
                   "currentness": "UNKNOWN", "applicability": "UNRESOLVED", "confidence": 0.0,
                   "author_review_required": True,
                   "review_note": AUTHOR_CONFIRM + ": entity kind, evidence binding and materiality."}
            nodes.append(row)
        return row

    trigger = strings(model.get("trigger", []), "behavior_model.trigger")
    operations = strings(model.get("operations", []), "behavior_model.operations")
    if not trigger and not operations:
        raise ValueError("behavior_model needs a trigger or operation; cannot invent a graph root")
    root_refs = sorted({eid for fact in facts for eid in strings(fact.get("evidence_ids", []), "fact.evidence_ids")
                        if eid in available})
    root = node("behavior_model", "; ".join(trigger + operations), "PRODUCT_BEHAVIOR",
                policy["material_by_kind"]["PRODUCT_BEHAVIOR"], root_refs)
    if not root_refs:
        gaps.append("behavior_model: no available fact evidence for the root.")
    for field, role in policy["entity_fields"].items():
        kind, relation, dimension = role["kind"], role["relation_type"], role["dimension"]
        values = model.get(field, [])
        if not isinstance(values, list):
            raise ValueError(f"behavior_model.{field} must be a list")
        for value in values:
            raw = value if isinstance(value, dict) else {"name": value}
            label = raw.get("name") or raw.get("label")
            if not isinstance(label, str) or not label.strip():
                raise ValueError(f"behavior_model.{field} entities need a name/label")
            label = label.strip()
            entity_kind = raw.get("kind", kind)
            entity_material = raw.get("material", policy["material_by_kind"].get(entity_kind)) if isinstance(entity_kind, str) else None
            if entity_kind not in behavior_graph.NODE_KINDS or not isinstance(entity_material, bool):
                raise ValueError(f"behavior_model.{field}: invalid kind/material")
            key = f"{field}:{label}"
            refs = provenance(key, label, raw.get("evidence_ids"))
            target = node(key, label, entity_kind, entity_material, refs)
            if root["node_id"] == target["node_id"]:
                continue
            triple = (root["node_id"], target["node_id"], relation)
            if any((edge.get("source"), edge.get("target"), edge.get("relation_type")) == triple for edge in edges):
                continue
            edge_id = next_id(edges, "edge_id", "BGE")
            hkey = "BEHAVIOR_GRAPH:" + ":".join(triple)
            hid = "H-BG-" + hashlib.sha256(hkey.encode("utf-8")).hexdigest()[:24]
            if any(row.get("hypothesis_id") == hid for row in hypotheses):
                raise ValueError("generated graph hypothesis ID collision")
            edges.append({
                "edge_id": edge_id, "source": triple[0], "target": triple[1], "relation_type": relation,
                "provenance": refs, "subject": "PRODUCT_CONTRACT", "authority": "INFERENCE",
                "currentness": "UNKNOWN", "applicability": "UNRESOLVED", "confidence": 0.0,
                "verification_state": "INVESTIGATION_CANDIDATE", "material": target["material"],
                "hypothesis_ref": hid, "author_review_required": True,
                "review_note": AUTHOR_CONFIRM + ": model-role relationship, not a verified implementation edge.",
            })
            hypotheses.append({
                "hypothesis_id": hid, "dimension": dimension,
                "candidate": f"Investigate whether {label} participates through {relation.lower().replace('_', ' ')} in the modeled behavior.",
                "reason": "The authored model names this role; applicability is not yet verified.",
                "technical_basis": [f"behavior_model.{field}: {label}"], "current_evidence": refs,
                "generator": "BEHAVIOR_GRAPH", "equivalence_key": hkey,
                "status": "INVESTIGATION_CANDIDATE", "requires_more_evidence": True,
                "confidence": 0.0, "authority_class": "SUPPORTING_DISCOVERY",
            })
    return gaps


def scaffold_semantic_closure(manifest):
    """Fill missing node/dimension pairs, never assert investigated applicability."""
    block = _block(manifest, "semantic_closure", semantic_closure.SCHEMA_VERSION, ("records",))
    records = block["records"]
    pairs = {(row.get("entity_ref"), row.get("dimension")) for row in records}
    if len(pairs) != len(records):
        raise ValueError("duplicate closure entity/dimension pairs must be resolved by the author")
    sequence = int(next_id(records, "closure_id", "SC").split("-")[1])
    for node in manifest["behavior_graph"]["nodes"]:
        if node.get("material") is not True:
            continue
        for dimension in semantic_closure.CLOSURE_DIMENSIONS:
            pair = (node["node_id"], dimension)
            if pair in pairs:
                continue
            records.append({
                "closure_id": f"SC-{sequence:02d}", "entity_ref": pair[0],
                "dimension": dimension, "subject": node.get("subject", "PRODUCT_CONTRACT"),
                "applicability": "NOT_APPLICABLE", "status": "INVESTIGATED_AND_REJECTED",
                "reason": f"{AUTHOR_CONFIRM}: assess {dimension.lower().replace('_', ' ')} for {node['label']}. Default is not an investigation result.",
                "disposition_ref": "", "author_review_required": True,
            })
            pairs.add(pair)
            sequence += 1


def scaffold(manifest, *, inspected_files=(), base_dir=None):
    """Return a detached full manifest; never mutate the input or author verdicts."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("behavior_model"), dict):
        raise ValueError("manifest requires a behavior_model object")
    if "evidence_catalog" not in manifest:
        raise ValueError("manifest requires an evidence_catalog (an explicit empty list is allowed)")
    result = deepcopy(manifest)
    for name in ("contract_facts", "behavior_graph", "semantic_closure"):
        if name in result and not isinstance(result[name], dict):
            raise ValueError(f"{name} must be an object")
    for name in ("verifications", "coverage_hypotheses", "missing_questions"):
        if name in result:
            object_list(result[name], name)
    files = strings(result.get("inspected_files", []), "inspected_files") + list(inspected_files)
    binding = evidence_binding.bind_files(result, list(dict.fromkeys(files)), base_dir=base_dir or Path.cwd())
    gaps = binding["gaps"] + scaffold_behavior_graph(result)
    scaffold_semantic_closure(result)
    questions = object_list(result.setdefault("missing_questions", []), "missing_questions")
    questions.extend(missing_questions.derive_missing_question_stubs(result))
    result["v3_scaffold"] = {"schema_version": "aem-guides-v3-scaffold-v1",
                             "generator": "PYTHON_SCAFFOLD", "gaps": gaps,
                             "file_bindings": binding["bindings"]}
    return result


def summarize(manifest):
    graph = manifest.get("behavior_graph", {})
    closure = manifest.get("semantic_closure", {}).get("records", [])
    rows = graph.get("nodes", []) + graph.get("edges", []) + closure + manifest.get("evidence_lifecycle", [])
    return (f"Scaffold: {len(graph.get('nodes', []))} nodes, {len(graph.get('edges', []))} edges, "
            f"{len(closure)} closure records, {len(manifest.get('missing_questions', []))} questions; "
            f"{sum(pending_review(row) for row in rows)} rows await author review. "
            "This is not a gate pass or posting authority.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--out", type=Path, help="new output file; existing files are never overwritten")
    parser.add_argument("--inspected-file", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        source = args.manifest.resolve(strict=True)
        output = args.out or source.with_name(source.stem + ".scaffold.json")
        # Reject existing paths (including symlinks/hardlinks to input) before any write.
        if output.exists() or output.is_symlink():
            raise ValueError("output already exists; choose a new --out path")
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        result = scaffold(data, inspected_files=args.inspected_file, base_dir=source.parent)
        payload = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        print(summarize(result))
        for gap in result["v3_scaffold"]["gaps"]:
            print("GAP: " + gap)
        print(f"Written: {output.resolve()}")
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(f"Scaffold not written: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
