"""Reproduce the authoring demonstration, not a plan or acceptance verifier.

Reads a separately authored review; never invents a positive decision. Outputs
must be new files. Run from this directory after generating the initial scaffold.
"""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parents[2] / ".codex" / "skills" / "test-plan-generation"
sys.path.insert(0, str(SKILL / "scripts"))
import v3_scaffold


def main():
    manifest = json.loads((ROOT / "manifest.input.scaffold.json").read_text(encoding="utf-8"))
    review = json.loads((ROOT / "author-review.json").read_text(encoding="utf-8"))
    root_node = next(n for n in manifest["behavior_graph"]["nodes"]
                     if n.get("scaffold_key") == review["closure_review"]["scaffold_key"])
    closure = next(r for r in manifest["semantic_closure"]["records"]
                   if r["entity_ref"] == root_node["node_id"]
                   and r["dimension"] == review["closure_review"]["dimension"])
    closure.update({k: v for k, v in review["closure_review"].items() if k != "scaffold_key"})
    target = next(n for n in manifest["behavior_graph"]["nodes"]
                  if n.get("scaffold_key") == review["verification_review"]["scaffold_key"])
    edge = next(e for e in manifest["behavior_graph"]["edges"] if e["target"] == target["node_id"])
    manifest["verifications"] = [{"hypothesis_id": edge["hypothesis_ref"],
                                 **{k: v for k, v in review["verification_review"].items() if k != "scaffold_key"}}]
    manifest["open_questions"] = [review["open_question"]]
    result = v3_scaffold.scaffold(manifest, base_dir=ROOT)
    assert len(result["missing_questions"]) == 2
    assert all(q["open_question_ref"] == "OQ-01" for q in result["missing_questions"])
    assert all(row["status"] == "RETRIEVED" for row in result["evidence_lifecycle"])
    assert "acceptance_promotions" not in result
    with (ROOT / "manifest.author-progress.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(v3_scaffold.summarize(result))
    print("Two contextual questions added from explicit unresolved review; all other author decisions remain pending.")


if __name__ == "__main__":
    main()
