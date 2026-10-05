"""Offline tests: judge_pipeline.py records which canonical gates stopped a run, and why."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge_pipeline as jp  # noqa: E402

BLOCKED = {"gate": "AcceptancePromotionGate", "status": "BLOCKED",
           "failures": ["cand-1: A blocking product decision remains unresolved.",
                        "cand-2: A blocking product decision remains unresolved."]}
PASSED = {"gate": "ContractIntegrityGate", "status": "PASSED", "failures": []}


class GateRecordingTests(unittest.TestCase):
    def test_only_gates_that_did_not_pass_are_kept(self) -> None:
        self.assertEqual(jp.gate_decisions({"gate_decisions": [PASSED, BLOCKED]}), [BLOCKED])

    def test_gates_nested_in_the_pipeline_dto_are_read(self) -> None:
        response = {"qe_review_package": {"canonical_result": {"gate_decisions": [BLOCKED]}}}
        self.assertEqual(jp.gate_decisions(response), [BLOCKED])

    def test_no_gate_decisions_is_an_empty_list(self) -> None:
        self.assertEqual(jp.gate_decisions({"status": "blocked"}), [])

    def test_reason_drops_the_candidate_id(self) -> None:
        self.assertEqual(jp.reason_key("cand-7: A blocking product decision remains unresolved."),
                         "A blocking product decision remains unresolved.")
        self.assertEqual(jp.reason_key("No authoritative product-contract fact is available."),
                         "No authoritative product-contract fact is available.")

    def test_summary_counts_tickets_per_gate_and_reason(self) -> None:
        other = {"gate": "BehavioralCompletenessGate", "status": "FAILED",
                 "failures": ["Mandatory DOC research is still PENDING for a material question: q1"]}
        per = [{"key": "A-1", "pipeline_gates": [BLOCKED]},
               {"key": "A-2", "pipeline_gates": [BLOCKED, other]},
               {"key": "A-3", "pipeline_gates": []}]
        summary = jp.gate_summary(per)
        self.assertEqual([g["gate"] for g in summary], ["AcceptancePromotionGate", "BehavioralCompletenessGate"])
        self.assertEqual(summary[0]["tickets"], 2)
        self.assertEqual(summary[0]["reasons"],
                         [{"reason": "A blocking product decision remains unresolved.", "tickets": 2}])
        self.assertEqual(summary[1]["status"], "FAILED")


if __name__ == "__main__":
    unittest.main()
