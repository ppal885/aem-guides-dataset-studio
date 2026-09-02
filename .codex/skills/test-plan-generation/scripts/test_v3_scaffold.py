"""Offline, stdlib conformance tests for author-editable v3 scaffolding."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from unittest.mock import patch

import behavior_graph
import coverage_hypotheses
import evidence_binding
import missing_questions
import semantic_closure
import v3_scaffold
import verify_evidence


def run_tests(check):
    model = {
        "trigger": ["a request arrives"], "operations": ["resolve a value"],
        "processors": ["value resolver"], "attributes": ["display option"],
        "config": ["active profile"], "consumers": ["details panel"],
        "affected_state": ["displayed value"],
        "facts": [{"fact": "The value resolver uses the display option and active profile for the details panel and displayed value.",
                   "evidence_ids": ["E1"], "authority": "CURRENT_IMPLEMENTATION", "confidence": 0.9}],
    }
    original = {"schema_version": "aem-guides-evidence-manifest-v3", "behavior_model": model,
                "evidence_catalog": [{"id": "E1", "source_type": "code"}]}
    frozen = deepcopy(original)
    result = v3_scaffold.scaffold(original)
    graph = result["behavior_graph"]
    records = result["semantic_closure"]["records"]
    check("scaffold does not mutate input", original == frozen)
    check("model roles produce typed candidate nodes and edges", len(graph["nodes"]) == 6
          and len(graph["edges"]) == 5 and all(e["relation_type"] in behavior_graph.RELATION_TYPES for e in graph["edges"])
          and all(e["verification_state"] == "INVESTIGATION_CANDIDATE" for e in graph["nodes"] + graph["edges"]))
    check("graph provenance comes only from bound facts", all(n["provenance"] == ["E1"] for n in graph["nodes"] + graph["edges"]))
    check("nodes and edges retain explicit unknown verification context", all(
        n["currentness"] == "UNKNOWN" and n["applicability"] == "UNRESOLVED" and n["confidence"] == 0.0
        for n in graph["nodes"] + graph["edges"]))
    policy = v3_scaffold.load_policy()
    check("scaffold vocabulary is data-backed and canonical", set(policy["material_by_kind"]) == set(behavior_graph.NODE_KINDS)
          and all(r["relation_type"] in behavior_graph.RELATION_TYPES for r in policy["entity_fields"].values()))
    for invalid_policy in ({}, dict(policy, material_by_kind={}), dict(policy, entity_fields={
            "processors": {"kind": "PROCESSOR", "relation_type": "INVENTED", "dimension": "CONSUMER"}})):
        with patch.object(v3_scaffold.Path, "read_text", return_value=json.dumps(invalid_policy)):
            try:
                v3_scaffold.load_policy()
            except ValueError:
                rejected = True
            else:
                rejected = False
        check("malformed policy cannot introduce invented vocabulary", rejected)
    typed = deepcopy(original)
    typed["behavior_model"]["processors"] = [{"name": "context role", "kind": "ROLE", "evidence_ids": ["E1"]},
        {"name": "material role", "kind": "ROLE", "material": True, "evidence_ids": ["E1"]}]
    typed["behavior_model"]["configuration"] = [{"name": "enabled flag", "evidence_ids": ["E1"]}]
    typed_result = v3_scaffold.scaffold(typed)
    typed_graph = typed_result["behavior_graph"]
    check("materiality follows actual node kind with explicit author override", not next(
        n for n in typed_graph["nodes"] if n["label"] == "context role")["material"] and next(
        n for n in typed_graph["nodes"] if n["label"] == "material role")["material"])
    check("configuration model field is scaffolded", any(n["label"] == "enabled flag" and n["kind"] == "CONFIGURATION"
          for n in typed_graph["nodes"]))
    nonmaterial_ids = {n["node_id"] for n in typed_graph["nodes"] if not n["material"]}
    check("closure matrix excludes nonmaterial context nodes", not any(
        r["entity_ref"] in nonmaterial_ids for r in typed_result["semantic_closure"]["records"]))
    check("closure scaffold emits complete per-node matrix", len(records) == 6 * len(semantic_closure.CLOSURE_DIMENSIONS)
          and len({(r["entity_ref"], r["dimension"]) for r in records}) == len(records))
    check("closure never asserts applicability or a disposition", all(r["applicability"] == "NOT_APPLICABLE"
          and r["status"] == "INVESTIGATED_AND_REJECTED" and not r["disposition_ref"] for r in records))
    check("scaffold emits no verdicts, ACs or fake unresolved questions", "verifications" not in result
          and "acceptance_promotions" not in result and result["missing_questions"] == [])
    check("candidate graph edges are declared hypotheses", {e["hypothesis_ref"] for e in graph["edges"]}
          <= {h["hypothesis_id"] for h in result["coverage_hypotheses"]}
          and not coverage_hypotheses.validate_coverage_block(result["coverage_hypotheses"], require_ids=True))
    check("fresh scaffold deterministically reruns", v3_scaffold.scaffold(result) == result)
    malformed = deepcopy(original)
    malformed["behavior_graph"] = {"schema_version": behavior_graph.SCHEMA_VERSION,
                                   "nodes": [{"material": True}], "edges": []}
    try:
        v3_scaffold.scaffold(malformed)
    except ValueError:
        rejected = True
    else:
        rejected = False
    check("malformed existing node fails with a controlled validation error", rejected)

    # Authoring edits must survive reruns; generated questions carry real context.
    record = records[0]
    record.update(applicability="UNRESOLVED", status="UNRESOLVED_AND_EXPOSED",
                  open_question_ref="OQ-01", reason="The source does not define precedence.", author_review_required=False)
    hid = result["coverage_hypotheses"][0]["hypothesis_id"]
    result["verifications"] = [{"hypothesis_id": hid, "verdict": "UNRESOLVED", "subject": "ACTUAL_IMPLEMENTATION",
                                "open_question_ref": "OQ-02"}]
    rerun = v3_scaffold.scaffold(result)
    questions = rerun["missing_questions"]
    check("one contextual question per unresolved closure and verification", len(questions) == 2
          and graph["nodes"][0]["label"] in questions[0]["question"]
          and questions[1]["hypothesis_id"] == hid
          and all(q["search_concepts"] and q["why_it_matters"] and q["generator"] == "PYTHON_SCAFFOLD" for q in questions)
          and not missing_questions.validate_required_questions(rerun))
    check("questions use subject-specific source vocabulary", all(not missing_questions.validate_question(
        missing_questions.MissingQuestion.from_dict(q)) for q in questions))
    check("unresolved question does not invent second-pass retrieval", rerun["evidence_lifecycle"] == []
          and any("second-pass" in p for p in missing_questions.check_retrieval_discipline(questions, [])))
    rerun["missing_questions"][0]["question"] = "Author's more precise question?"
    again = v3_scaffold.scaffold(rerun)
    check("rerun preserves authored rows and IDs", again == rerun and again["semantic_closure"]["records"][0] == record)
    result["behavior_model"]["processors"].append({"name": "new consumer", "evidence_ids": ["E1"]})
    expanded = v3_scaffold.scaffold(result)
    check("new entities append without renumbering decisions", expanded["behavior_graph"]["nodes"][:6] == graph["nodes"]
          and expanded["semantic_closure"]["records"][:len(records)] == records)

    check("unreviewed graph defaults cannot validate", any("author must confirm" in p for p in behavior_graph.validate_behavior_graph(graph)))
    guarded = deepcopy(result["semantic_closure"])
    for row in guarded["records"]:
        row["disposition_ref"] = "CD-01"
        row["author_review_required"] = False
    check("filling disposition IDs cannot launder default rejection", any("author must confirm" in p for p in
          semantic_closure.validate_semantic_closure(guarded, material_entity_ids=behavior_graph.material_node_ids(graph))))
    reviewed_graph = deepcopy(graph)
    for row in reviewed_graph["nodes"] + reviewed_graph["edges"]:
        row["author_review_required"] = False
        row["review_note"] = "Reviewed the named role against the supplied source. Applicability still needs verification."
    check("reviewed candidate graph validates without auto-confirmation", not behavior_graph.validate_behavior_graph(reviewed_graph, evidence_ids=["E1"]))
    for row in guarded["records"]:
        if row["applicability"] == "NOT_APPLICABLE":
            row["reason"] = "The inspected fixture is a scalar lookup and this relationship is outside its modeled boundary."
    check("author-dispositioned closure can validate", not semantic_closure.validate_semantic_closure(
          guarded, material_entity_ids=behavior_graph.material_node_ids(graph), open_question_ids=["OQ-01"]))
    guarded["records"].append(dict(guarded["records"][0], closure_id="SC-9999"))
    check("conflicting duplicate closure pair fails", any("duplicate entity/dimension" in p for p in semantic_closure.validate_semantic_closure(
          guarded, material_entity_ids=behavior_graph.material_node_ids(graph))))

    unavailable = deepcopy(original)
    unavailable["evidence_catalog"][0]["availability"] = "unavailable"
    unavailable["behavior_model"]["processors"].append("unrelated name")
    missing = v3_scaffold.scaffold(unavailable)
    check("unavailable sources never become invented graph provenance", all(not row["provenance"] for row in missing["behavior_graph"]["nodes"])
          and bool(missing["v3_scaffold"]["gaps"]))
    unrelated = deepcopy(original)
    unrelated["behavior_model"]["processors"] = ["unrelated name"]
    missing = v3_scaffold.scaffold(unrelated)
    check("unmentioned entity cannot borrow arbitrary catalog evidence", not next(n for n in missing["behavior_graph"]["nodes"]
          if n["label"] == "unrelated name")["provenance"])
    # Matrix sizes are real: 31 x N exceeds the former three-digit closure limit.
    large = deepcopy(original)
    large["behavior_model"]["processors"] = [{"name": f"processor {i}", "evidence_ids": ["E1"]} for i in range(101)]
    matrix = v3_scaffold.scaffold(large)
    graph_errors = behavior_graph.validate_behavior_graph(matrix["behavior_graph"], evidence_ids=["E1"])
    closure_errors = semantic_closure.validate_semantic_closure(matrix["semantic_closure"], material_entity_ids=behavior_graph.material_node_ids(matrix["behavior_graph"]))
    check("large matrices have valid unique IDs without truncation", len(matrix["semantic_closure"]["records"]) > 999
          and not any("stable" in p or "duplicates" in p or "silently omits" in p for p in graph_errors + closure_errors))

    with tempfile.TemporaryDirectory(prefix="v3-scaffold-") as directory:
        root = Path(directory)
        source = root / "inspected source.py"
        source.write_bytes(b"value = 1\r\n")
        base = deepcopy(original)
        base["evidence_catalog"] = {"schema_version": "catalog-v1", "entries": []}
        bound = v3_scaffold.scaffold(base, inspected_files=[source.name], base_dir=root)
        entry = evidence_binding.catalog_entries(bound)[0]
        check("file binding hashes exact bytes and resolves relative path", entry["source_hash"] == "sha256:" + hashlib.sha256(source.read_bytes()).hexdigest()
              and entry["source_ref"] == source.resolve().as_posix() and not entry["content_inspected"])
        partial = deepcopy(original)
        partial["evidence_catalog"][0]["source_ref"] = source.resolve().as_posix()
        completed = v3_scaffold.scaffold(partial, inspected_files=[source.name], base_dir=root)
        check("hash helper completes existing file IDs without breaking model bindings", len(completed["evidence_catalog"]) == 1
              and completed["evidence_catalog"][0]["id"] == "E1"
              and completed["evidence_catalog"][0]["source_hash"] == entry["source_hash"]
              and not completed["v3_scaffold"]["gaps"])
        lifecycle = bound["evidence_lifecycle"][0]
        check("binding does not invent a query, authority, use or second pass", lifecycle["status"] == "RETRIEVED"
              and lifecycle["query"] == lifecycle["subject"] == lifecycle["authority"] == "" and lifecycle["pass"] == "initial")
        check("pending binding is rejected even if marked USED", any("author must confirm" in p for p in missing_questions.check_retrieval_discipline(
              [], [dict(lifecycle, status="USED", query="inspected source", hypothesis_id="H-01")])) )
        saved = root / "bound.json"
        saved.write_text(json.dumps(dict(bound, behavior_model={})), encoding="utf-8")
        check("file entries use existing provenance validator contract", not verify_evidence.verify_provenance("", str(saved))[0])
        repeat = deepcopy(bound)
        evidence_binding.bind_files(repeat, [source.name], base_dir=root)
        check("same file binding is idempotent and preserves lifecycle edits", repeat == bound)
        source.write_bytes(b"value = 2\n")
        evidence_binding.bind_files(repeat, [source.name], base_dir=root)
        check("changed bytes never overwrite old evidence", len(evidence_binding.catalog_entries(repeat)) == 2
              and evidence_binding.catalog_entries(repeat)[0] == entry)
        absent = deepcopy(base)
        report = evidence_binding.bind_files(absent, ["absent.py", "."], base_dir=root)
        check("missing files and directories yield gaps without evidence", len(report["gaps"]) == 2
              and evidence_binding.catalog_entries(absent) == [] and absent["evidence_lifecycle"] == [])
        input_file = root / "manifest.json"
        input_file.write_text(json.dumps(original), encoding="utf-8")
        before = input_file.read_bytes()
        check("CLI creates a separate scaffold", v3_scaffold.main(["--manifest", str(input_file)]) == 0
              and (root / "manifest.scaffold.json").is_file())
        check("CLI refuses overwriting input or existing output", v3_scaffold.main(["--manifest", str(input_file), "--out", str(input_file)]) == 2
              and v3_scaffold.main(["--manifest", str(input_file)]) == 2 and input_file.read_bytes() == before)
        bad = root / "bad.json"
        bad.write_text("[]", encoding="utf-8")
        check("malformed manifest yields controlled failure and no file", v3_scaffold.main(["--manifest", str(bad)]) == 2
              and not (root / "bad.scaffold.json").exists())


if __name__ == "__main__":
    def check(name, result):
        if not result:
            raise AssertionError(name)
        print("PASS " + name)
    run_tests(check)
