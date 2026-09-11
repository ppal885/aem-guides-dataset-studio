"""Offline adversarial regression for the September 9 AC grouping boundary.

Run: python -B backend/tests/test_ac_equivalence_boundary.py -v
Loads real canonical skill modules, without app startup, conftest, DB, or LLM calls.

The synthetic requirements below are test data, not AEM product requirements.
They test declared contracts: these gates do not infer missing/false signatures or
material dimensions from prose. This is not an end-to-end generation benchmark.
Scenario reduction and AC grouping are separate layers; both are exercised here.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import importlib.util
from itertools import permutations
from pathlib import Path
import unittest


SCRIPTS = Path(__file__).resolve().parents[2] / "skills/test-plan-generation/scripts"


def _load(name):
    path = SCRIPTS / (name + ".py")
    spec = importlib.util.spec_from_file_location("ac_boundary_" + name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load canonical skill module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reducer = _load("scenario_reducer")
language = _load("ac_language_policy")
synthesis = _load("acceptance_synthesizer")

# One fixture, six independently executable cases, five required contracts.
# Close wording is intentional: changing just one facet must prevent a merge.
BASE = (
    "An empty label uses the filename. Preview appears immediately in source order. "
    "An editor is allowed to open Preview."
)
CASES = (
    ("CF-01", "missing label", BASE, None),
    ("CF-02", "blank label", BASE, None),
    ("CF-03", "identifier fallback policy",
     BASE.replace("filename", "raw identifier"), "configuration"),
    ("CF-04", "deferred preview policy",
     BASE.replace("immediately", "only after refresh"), "lifecycle"),
    ("CF-05", "reverse ordering policy",
     BASE.replace("in source order", "in reverse source order"), "ordering"),
    ("CF-06", "denied preview permission",
     BASE.replace("is allowed", "is not allowed"), "negative_boundary"),
)
# Hand-authored oracle, never derived from reducer.signature() or reducer.reduce().
GROUPS = (("CF-01", "CF-02"), ("CF-03",), ("CF-04",), ("CF-05",), ("CF-06",))
SOURCE_IDS = tuple(case[0] for case in CASES)
BOUNDARIES = ("fallback", "timing", "ordering", "permission")


def _scenarios():
    return [
        {
            "scenario_id": cid,
            "signature": {
                "semantic_decision": "preview listing",
                "implementation_branch": "shared preview reader",
                "state_transition": "saved content unchanged",
                "resulting_contract": outcome,
            },
            "distinguishing_factors": [],
            "representative": cid != "CF-02",
            **({"collapsed_into": "CF-01"} if cid == "CF-02" else {}),
        }
        for cid, _case, outcome, _dimension in CASES
    ]


def _manifest():
    by_id = {case[0]: case for case in CASES}
    final_acs = []
    for index, ids in enumerate(GROUPS, 1):
        outcome = by_id[ids[0]][2]
        named_cases = "\n".join("  - " + by_id[cid][1] for cid in ids)
        final_acs.append({
            "ac_ref": f"AC-{index:02d}",
            "title": "Preview contract: " + by_id[ids[0]][1],
            "body": outcome + "\nCases:\n" + named_cases,
            "candidate_ids": list(ids),
            "merged_candidate_ids": list(ids) if len(ids) > 1 else [],
            "evidence_ids": ["synthetic-source:" + cid for cid in ids],
            "scope_basis": "Explicit synthetic fixture requirements",
            "oracle": outcome,
            "synthesis_group": "CORE_CUSTOMER_CONTRACT",
            "distinct_contract_count": 1,
            "distinct_material_dimensions": [],
        })
    return {"ac_synthesis": {"source_candidate_ids": list(SOURCE_IDS), "final_acs": final_acs}}


class TestAcEquivalenceBoundary(unittest.TestCase):
    def test_equivalent_cases_share_one_ac_without_losing_trace(self):
        manifest = _manifest()
        self.assertEqual([], language.validate(manifest))
        self.assertEqual([], synthesis.validate(manifest))
        self.assertEqual([], reducer.validate_reduction(_scenarios()))
        # Separate executable branches do not require separate product ACs.
        separate_paths = _scenarios()
        separate_paths[1]["signature"]["implementation_branch"] = "blank label reader"
        separate_paths[1]["representative"] = True
        separate_paths[1].pop("collapsed_into")
        self.assertEqual([], reducer.validate_reduction(separate_paths))
        self.assertEqual(6, len(reducer.reduce(separate_paths)[0]))
        acs = manifest["ac_synthesis"]["final_acs"]
        self.assertEqual(GROUPS, tuple(tuple(ac["candidate_ids"]) for ac in acs))
        self.assertEqual(Counter(SOURCE_IDS), Counter(cid for ac in acs for cid in ac["candidate_ids"]))

    def test_result_only_differences_survive_every_input_order(self):
        scenarios = _scenarios()
        # Whitespace/case noise is equivalent, unlike any of the four outcomes.
        scenarios[1]["signature"]["resulting_contract"] = "  " + BASE.upper().replace(" ", "  ") + "  "
        for ordered in permutations(scenarios):
            reps, collapsed = reducer.reduce(ordered)
            first_equivalent = next(s["scenario_id"] for s in ordered if s["scenario_id"] in GROUPS[0])
            self.assertEqual({first_equivalent, "CF-03", "CF-04", "CF-05", "CF-06"},
                             {s["scenario_id"] for s in reps})
            self.assertEqual(set(GROUPS[0]) - {first_equivalent},
                             {s["scenario_id"] for s in collapsed})
            self.assertEqual(Counter(SOURCE_IDS), Counter(s["scenario_id"] for s in reps + collapsed))

    def test_different_result_cannot_be_declared_collapsed(self):
        for boundary, case in zip(BOUNDARIES, CASES[2:]):
            with self.subTest(boundary=boundary):
                scenarios = _scenarios()
                target = next(s for s in scenarios if s["scenario_id"] == case[0])
                target.update(representative=False, collapsed_into="CF-01")
                problems = reducer.validate_reduction(scenarios)
                self.assertTrue(any("signatures differ" in p and case[0] in p for p in problems), problems)

    def test_distinct_ac_merge_is_rejected_even_when_all_ids_survive(self):
        for boundary, case in zip(BOUNDARIES, CASES[2:]):
            with self.subTest(boundary=boundary):
                manifest = _manifest()
                acs = manifest["ac_synthesis"]["final_acs"]
                other = next(ac for ac in acs if case[0] in ac["candidate_ids"])
                merged = acs[0]
                for field in ("candidate_ids", "merged_candidate_ids", "evidence_ids"):
                    merged[field].extend(other["candidate_ids"] if field == "merged_candidate_ids" else other[field])
                # Use the existing schema vocabulary, not new permission/timing enums.
                merged["distinct_material_dimensions"] = [case[3]]
                acs.remove(other)
                self.assertEqual([], synthesis.validate(manifest))
                problems = language.validate(manifest)
                self.assertTrue(any("HIDDEN_MATERIAL_SCENARIO" in p for p in problems), problems)
                self.assertFalse(any("MATERIAL_CANDIDATE_LOSS" in p for p in problems), problems)

    def test_merged_variant_cannot_disappear_or_survive_only_as_a_merged_id(self):
        manifest = _manifest()
        first = manifest["ac_synthesis"]["final_acs"][0]
        first["candidate_ids"].remove("CF-02")
        self.assertTrue(any("not in candidate_ids" in p for p in synthesis.validate(manifest)))
        first["merged_candidate_ids"].remove("CF-02")
        self.assertTrue(any("MATERIAL_CANDIDATE_LOSS" in p and "CF-02" in p
                            for p in language.validate(manifest)))

    def test_redundant_representatives_and_duplicate_ac_are_rejected(self):
        scenarios = _scenarios()
        scenarios[1]["representative"] = True
        scenarios[1].pop("collapsed_into")
        self.assertTrue(any("collapse them" in p for p in reducer.validate_reduction(scenarios)))
        manifest = _manifest()
        duplicate = deepcopy(manifest["ac_synthesis"]["final_acs"][0])
        duplicate["ac_ref"] = "AC-06"
        manifest["ac_synthesis"]["final_acs"].append(duplicate)
        self.assertTrue(any("REDUNDANT_AC" in p for p in language.validate(manifest)))


if __name__ == "__main__":
    unittest.main()
