"""Offline forward tests of discovery -> review -> terminal disposition.

Synthetic inspected files and explicit test decisions; no Jira, provider or AC write.
"""
from copy import deepcopy
import tempfile
from unittest.mock import patch

import dimension_synthesizer as ds
import coverage_hypotheses
from test_discovery_disposition import terminal_fixture


def run_tests(check):
    with tempfile.TemporaryDirectory() as root, patch.object(ds, "_load_offline_retrieval", return_value=None):
        _, template = terminal_fixture(root)
        entry = deepcopy(template["evidence_catalog"][0])
        manifest = {
            "evidence_catalog": [entry, dict(entry, id="E-DECISION-0"), dict(entry, id="E-DECISION-1")],
            "construct_relationships": {
                "discovery": {"code_neighborhood_sweep": {
                    "sibling_config_keys": {"searched": True, "findings": [
                        {"neighbor": "primary choice", "source": entry["source_ref"] + ":1"},
                        {"neighbor": "alternate choice", "source": entry["source_ref"] + ":1"},
                    ]}
                }},
                "edges": [],
            },
        }
        before = deepcopy(manifest)
        generated = ds.synthesize(manifest)["candidates"]
        check("recorded siblings reach synthesis as distinct legal hypotheses",
              len(generated) == 2 and len({c["hypothesis_id"] for c in generated}) == 2
              and coverage_hypotheses.validate_coverage_block(generated) == [])
        check("recorded sibling synthesis does not alter source manifest", manifest == before)
        check("each recorded sibling starts as a discovery review", len(ds.review_notes(manifest)) == 2)
        manifest["coverage_hypotheses"] = deepcopy(generated)
        check("copying generated rows does not settle either sibling", len(ds.review_notes(manifest)) == 2)
        manifest["verifications"], manifest["dispositions"], manifest["evidence_lifecycle"] = [], [], []
        for index, candidate in enumerate(generated):
            hypothesis = manifest["coverage_hypotheses"][index]
            hypothesis.update(status="REJECTED", requires_more_evidence=False)
            hid = candidate["hypothesis_id"]
            # Separate ledger IDs prevent one hypothesis borrowing another's use.
            eid = f"E-DECISION-{index}"
            # Retain original discovered source ID and use that exact source in a
            # per-hypothesis catalog/ledger record, as the normal schema permits.
            use = deepcopy(template["evidence_lifecycle"][0])
            use.update(evidence_id=eid, hypothesis_id=hid)
            manifest["evidence_lifecycle"].append(use)
            verification = deepcopy(template["verifications"][0])
            verification.update(hypothesis_id=hid, disproving_evidence=[eid])
            manifest["verifications"].append(verification)
            disposition = deepcopy(template["dispositions"][0])
            disposition.update(finding_id=f"DIS-{index}", source_refs=[hid])
            manifest["dispositions"].append(disposition)
            remaining = ds.review_notes(manifest)
            check(f"a terminal sibling decision clears only itself ({index + 1}/2)", len(remaining) == 1 - index)
        check("investigated rejection produces no acceptance promotion",
              "acceptance_promotions" not in manifest and all(
                  h["status"] == "REJECTED" for h in manifest["coverage_hypotheses"]))
        changed = deepcopy(manifest)
        changed["construct_relationships"]["discovery"]["code_neighborhood_sweep"]["sibling_config_keys"]["findings"][1]["neighbor"] = "new choice"
        check("a new neighbor cannot reuse an old sibling decision", len(ds.review_notes(changed)) == 1)
        broad = deepcopy(before)
        broad["coverage_hypotheses"] = [{"dimension": "CONFIGURATION"}]
        check("broad configuration coverage cannot hide two recorded siblings", len(ds.review_notes(broad)) == 2)

        trigger_only = {"behavior_model": {"trigger": ["Generate Native PDF"]}}
        native = [c for c in ds.synthesize(trigger_only)["candidates"] if c.get("surface") == "NATIVE_PDF_CONTENT"]
        check("surface in trigger reaches curated discovery without duplicated fact text",
              {c["feature"] for c in native} == {"Variables", "Variable Sets"})
        check("unrelated caret behavior does not expand into publishing candidates",
              ds.synthesize({"behavior_model": {"trigger": ["Move the caret"]}})["candidates"] == [])


if __name__ == "__main__":
    def check(label, result):
        if not result:
            raise AssertionError(label)
        print("PASS " + label)
    run_tests(check)
