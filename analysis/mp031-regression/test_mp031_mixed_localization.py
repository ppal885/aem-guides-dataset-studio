"""Regression fixture: preserve per-language import research beside output research.

Run: python analysis/mp031-regression/test_mp031_mixed_localization.py
Baseline: 62029b634 (2026-10-28 inspection). Expected to fail until the
synthesizer preserves distinct probe identities and their authority metadata.
Synthetic discovery evidence only; no translation/copy/empty outcome is asserted.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/test-plan-generation/scripts"))
import dimension_synthesizer as ds
import miss_probe_library as mpl


class PerLanguageImportRegression(unittest.TestCase):
    def test_shadow_import_probe_survives_multilingual_output_neighbor(self):
        manifest = {"evidence_catalog": [
            {"id": "E-IMPORT", "text": "Import adds new language variables."},
            {"id": "E-OUTPUT", "text": "The resulting multilingual output uses template labels."},
        ]}
        pairs = [(e["id"], e["text"]) for e in manifest["evidence_catalog"]]
        raw = {c["probe_id"]: c for c in mpl.candidates_for(pairs)}
        self.assertIn("MP-026", raw)
        self.assertIn("MP-031", raw)
        self.assertTrue(raw["MP-031"]["non_authoritative"])
        # Disable optional corpus retrieval, not the real library or deduplication.
        with patch.object(ds, "_load_offline_retrieval", return_value=None):
            candidates = ds.synthesize(manifest)["candidates"]
        learned = {c["probe_id"]: c for c in candidates if c["generator"] == "LEARNED_PROBE"}
        with self.subTest("separate research questions and provenance"):
            self.assertIn("MP-031", learned, "Per-language propagation research was dropped")
            shadow = learned["MP-031"]
            self.assertEqual(shadow["candidate"], raw["MP-031"]["candidate"])
            self.assertEqual(shadow["current_evidence"], ["E-IMPORT"])
            self.assertTrue(shadow["non_authoritative"])
            self.assertEqual(shadow["confidence"], 0.3)
            self.assertEqual(shadow["status"], "INVESTIGATION_CANDIDATE")
            self.assertTrue(shadow["requires_more_evidence"])
            self.assertIn("MP-026", learned)
            self.assertNotEqual(shadow["hypothesis_id"], learned["MP-026"]["hypothesis_id"])
        with self.subTest("shadow provenance never inherits active metadata"):
            for candidate in candidates:
                if "LEARNED_PROBE:MP-031" in candidate["technical_basis"]:
                    self.assertTrue(candidate["non_authoritative"])
                    self.assertLessEqual(candidate["confidence"], 0.3)


if __name__ == "__main__":
    unittest.main()
