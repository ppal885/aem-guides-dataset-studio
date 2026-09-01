#!/usr/bin/env python3
"""Regression tests for governed feature-map URL confirmation and merging."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "confirm_and_merge_feature_urls.py"
CANONICAL_MAP = (
    ROOT
    / ".codex"
    / "skills"
    / "test-plan-generation"
    / "data"
    / "aem_feature_map.json"
)
APPROVED_URL = (
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
    "user-guide/map-management-publishing/translate-content/"
    "translate-documents-web-editor"
)
REVIEW_URL = (
    "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/"
    "user-guide/review/review-address-review-comments"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("confirm_feature_urls_under_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {MODULE_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ConfirmAndMergeFeatureUrlsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.module = _load_module()
        self.temporary = tempfile.TemporaryDirectory()
        self.temp_root = Path(self.temporary.name)
        self.map_path = self.temp_root / "aem_feature_map.json"
        self.map_path.write_bytes(CANONICAL_MAP.read_bytes())
        self.draft_path = self.temp_root / "test_surface_draft.json"
        self.module.FEATURE_MAP = self.map_path
        self.module.DRAFTS = {"TEST_SURFACE": self.draft_path.name}

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _feature(name: str, **overrides) -> dict:
        feature = {
            "feature": name,
            "shared_flows": ["test shared flow"],
            "implied_dimension_axis": "LIFECYCLE",
            "candidate_template": f"{name} remains correct across the supported lifecycle",
            "reference": "Experience League source awaiting review",
            "reference_urls": [],
            "url_confirmed": False,
        }
        feature.update(overrides)
        return feature

    def _write_draft(self, features: list[dict], *, status: str = "PENDING_APPROVAL") -> None:
        self.draft_path.write_text(
            json.dumps(
                {
                    "surface": "TEST_SURFACE",
                    "curation_status": status,
                    "match": ["test surface"],
                    "native_features": features,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def _run(self, *args: str) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            result = self.module.main([*args, "--scratch-dir", str(self.temp_root)])
        return result, stream.getvalue()

    def test_pending_surface_merges_feature_level_human_approved_source(self) -> None:
        self._write_draft(
            [
                self._feature(
                    "approved feature",
                    reference="Experience League translate-documents-web-editor",
                    reference_urls=[APPROVED_URL],
                    url_confirmed=True,
                    approval_status="HUMAN_APPROVED",
                )
            ]
        )
        with mock.patch.object(
            self.module,
            "_query_top",
            side_effect=AssertionError("approved sources must not be rediscovered"),
        ):
            result, output = self._run("--apply")

        self.assertEqual(0, result)
        self.assertIn("HUMAN-APPROVED MERGE ELIGIBLE 1", output)
        data = json.loads(self.map_path.read_text(encoding="utf-8"))
        surface = next(item for item in data["surfaces"] if item["surface"] == "TEST_SURFACE")
        self.assertEqual([APPROVED_URL], surface["native_features"][0]["reference_urls"])
        self.assertEqual("HUMAN_APPROVED", surface["native_features"][0]["approval_status"])

    def test_similarity_hit_never_promotes_an_unapproved_feature(self) -> None:
        self._write_draft([self._feature("candidate only")], status="APPROVED")
        before = self.map_path.read_bytes()
        with mock.patch.object(
            self.module,
            "_query_top",
            return_value=(APPROVED_URL, "Translate documents", 0.10),
        ):
            result, output = self._run("--apply")

        self.assertEqual(0, result)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertIn("URL CANDIDATES AWAITING HUMAN APPROVAL 1", output)
        self.assertIn("NO MERGE", output)

    def test_retrieval_failure_is_reported_without_fabricating_a_source(self) -> None:
        self._write_draft([self._feature("retrieval unavailable")])
        before = self.map_path.read_bytes()
        with mock.patch.object(
            self.module,
            "_query_top",
            side_effect=RuntimeError("sensitive provider detail must not be rendered"),
        ):
            result, output = self._run("--apply")

        self.assertEqual(0, result)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertIn("STILL UNRESOLVED 1", output)
        self.assertIn("retrieval unavailable (RuntimeError)", output)
        self.assertNotIn("sensitive provider detail", output)

    def test_duplicate_draft_feature_fails_closed(self) -> None:
        self._write_draft(
            [
                self._feature(
                    "duplicate draft feature",
                    reference="Experience League translate-documents-web-editor",
                    reference_urls=[APPROVED_URL],
                    url_confirmed=True,
                    approval_status="HUMAN_APPROVED",
                ),
                self._feature("DUPLICATE DRAFT FEATURE"),
            ]
        )
        before = self.map_path.read_bytes()
        with mock.patch.object(
            self.module,
            "_query_top",
            side_effect=AssertionError("duplicate drafts must fail before classification"),
        ):
            result, output = self._run("--apply")

        self.assertEqual(2, result)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertIn("duplicate feature name in draft", output)
        self.assertNotIn("HUMAN-APPROVED MERGE ELIGIBLE 1", output)

    def test_all_tracked_drafts_remain_compatible_with_the_governed_map(self) -> None:
        drafts = ROOT / "scripts" / "feature_map_drafts"
        self.module.DRAFTS = {
            "PUBLISHING_OUTPUT": "publishing_surface_draft.json",
            "AUTHORING": "authoring_surface_draft.json",
            "REVIEW": "review_surface_draft.json",
            "BASELINE": "baseline_surface_draft.json",
            "EDITOR_OXYGEN": "editor_oxygen_surface_draft.json",
            "SECURITY": "security_surface_draft.json",
        }
        before = self.map_path.read_bytes()
        stream = io.StringIO()
        with (
            mock.patch.object(self.module, "_query_top", return_value=None),
            contextlib.redirect_stdout(stream),
        ):
            result = self.module.main(["--apply", "--scratch-dir", str(drafts)])
        output = stream.getvalue()

        self.assertEqual(0, result, output)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertNotIn("REFUSING", output)
        self.assertIn("ALREADY ACTIVE 7", output)
        self.assertIn("LEGACY SOURCE CONFIRMATIONS (NO MERGE) 11", output)
        self.assertIn("[BASELINE] baseline translation project", output)
        self.assertIn("[REVIEW] review task membership and selected-task state", output)
        self.assertIn("HUMAN-APPROVED MERGE ELIGIBLE 0", output)

    def test_invalid_legacy_source_cannot_bypass_current_url_validation(self) -> None:
        self._write_draft(
            [
                self._feature(
                    "invalid legacy source",
                    reference="Older descriptive source label",
                    reference_urls=["https://example.com/not-experience-league"],
                    url_confirmed=True,
                    approval_status="HUMAN_APPROVED",
                )
            ]
        )
        before = self.map_path.read_bytes()
        with mock.patch.object(
            self.module,
            "_query_top",
            side_effect=AssertionError("invalid legacy source must not be queried"),
        ):
            result, output = self._run("--apply")

        self.assertEqual(2, result)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertIn("REFUSING", output)

    def test_active_feature_is_reported_once_without_retrieval(self) -> None:
        self._write_draft(
            [
                self._feature(
                    "baseline translation project",
                    shared_flows=[
                        "translation project creation",
                        "baseline version selection for translation",
                    ],
                    candidate_template=(
                        "when Use Baseline is selected, the Translation page shows the files in "
                        "the chosen baseline for selection and creates the translation project "
                        "with the selected topic versions"
                    ),
                    implied_dimension_axis="CONFIG_BRANCH",
                    reference="Experience League translate-documents-web-editor",
                    reference_urls=[APPROVED_URL],
                    url_confirmed=True,
                    approval_status="HUMAN_APPROVED",
                )
            ]
        )
        self.module.DRAFTS = {"BASELINE": self.draft_path.name}
        draft = json.loads(self.draft_path.read_text(encoding="utf-8"))
        draft["surface"] = "BASELINE"
        draft["match"] = [
            "baseline",
            "work with baseline",
            "version-as-of",
            "version as of",
            "reference version resolution",
        ]
        self.draft_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        before = self.map_path.read_bytes()
        with mock.patch.object(
            self.module,
            "_query_top",
            side_effect=AssertionError("active features must not be queried"),
        ):
            result, output = self._run("--apply")

        self.assertEqual(0, result)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertIn("ALREADY ACTIVE 1", output)
        self.assertIn("HUMAN-APPROVED MERGE ELIGIBLE 0", output)
        self.assertIn("URL CANDIDATES AWAITING HUMAN APPROVAL 0", output)
        self.assertIn("STILL UNRESOLVED 0", output)

    def test_invalid_human_approved_url_fails_closed(self) -> None:
        invalid_urls = (
            "http://experienceleague.adobe.com/en/docs/experience-manager-guides/example",
            "https://experienceleague.adobe.com.example/en/docs/experience-manager-guides/example",
            "https://experienceleague.adobe.com/en/docs/experience-manager-cloud-service/example",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/",
            (
                "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
                "../experience-manager-cloud-service/example"
            ),
            (
                "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
                "%2e%2e/experience-manager-cloud-service/example"
            ),
            (
                "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
                "%252e%252e/experience-manager-cloud-service/example"
            ),
            (
                "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
                "%252f..%252fexperience-manager-cloud-service/example"
            ),
            APPROVED_URL + "?source=unsafe",
            APPROVED_URL + "#fragment",
        )
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url):
                self.map_path.write_bytes(CANONICAL_MAP.read_bytes())
                self._write_draft(
                    [
                        self._feature(
                            "invalid approved feature",
                            reference="Experience League invalid-source",
                            reference_urls=[invalid_url],
                            url_confirmed=True,
                            approval_status="HUMAN_APPROVED",
                        )
                    ]
                )
                before = self.map_path.read_bytes()
                with mock.patch.object(
                    self.module,
                    "_query_top",
                    side_effect=AssertionError("invalid approval must not fall back to retrieval"),
                ):
                    result, output = self._run("--apply")
                self.assertEqual(2, result)
                self.assertEqual(before, self.map_path.read_bytes())
                self.assertIn("REFUSING", output)

    def test_validation_failure_preserves_active_map(self) -> None:
        sys.path.insert(0, str(self.module.SKILL / "scripts"))
        import feature_map as feature_map_module

        before = self.map_path.read_bytes()
        invalid = json.loads(before.decode("utf-8"))
        invalid["curation_status"] = "MODEL_PROPOSED"
        problems = self.module._write_validated_map(invalid, feature_map_module)
        self.assertTrue(problems)
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertEqual([], list(self.temp_root.glob(f".{self.map_path.name}.*.tmp")))

    def test_active_current_approval_must_be_valid_and_match_the_map(self) -> None:
        invalid_or_drifted_urls = (
            "https://example.com/not-guides",
            REVIEW_URL,
        )
        for source_url in invalid_or_drifted_urls:
            with self.subTest(source_url=source_url):
                self.map_path.write_bytes(CANONICAL_MAP.read_bytes())
                self._write_draft(
                    [
                        self._feature(
                            "baseline translation project",
                            shared_flows=[
                                "translation project creation",
                                "baseline version selection for translation",
                            ],
                            candidate_template=(
                                "when Use Baseline is selected, the Translation page shows "
                                "the files in the chosen baseline for selection and creates "
                                "the translation project with the selected topic versions"
                            ),
                            implied_dimension_axis="CONFIG_BRANCH",
                            reference="Experience League translate-documents-web-editor",
                            reference_urls=[source_url],
                            url_confirmed=True,
                            approval_status="HUMAN_APPROVED",
                        )
                    ]
                )
                self.module.DRAFTS = {"BASELINE": self.draft_path.name}
                draft = json.loads(self.draft_path.read_text(encoding="utf-8"))
                draft["surface"] = "BASELINE"
                draft["match"] = ["baseline"]
                self.draft_path.write_text(
                    json.dumps(draft, indent=2) + "\n",
                    encoding="utf-8",
                )
                before = self.map_path.read_bytes()
                with mock.patch.object(
                    self.module,
                    "_query_top",
                    side_effect=AssertionError("active source validation must not query"),
                ):
                    result, output = self._run("--apply")

                self.assertEqual(2, result)
                self.assertEqual(before, self.map_path.read_bytes())
                self.assertIn("REFUSING", output)

    def test_replace_failure_preserves_active_map_and_cleans_temporary_file(self) -> None:
        sys.path.insert(0, str(self.module.SKILL / "scripts"))
        import feature_map as feature_map_module

        before = self.map_path.read_bytes()
        valid = json.loads(before.decode("utf-8"))
        valid["note"] = "Valid changed payload used to verify atomic replacement failure."
        with mock.patch.object(self.module.os, "replace", side_effect=OSError("blocked")):
            problems = self.module._write_validated_map(valid, feature_map_module)
        self.assertIn("could not be written atomically", " ".join(problems))
        self.assertEqual(before, self.map_path.read_bytes())
        self.assertEqual([], list(self.temp_root.glob(f".{self.map_path.name}.*.tmp")))

    def test_repository_approval_contract_is_selective_and_exact(self) -> None:
        drafts = ROOT / "scripts" / "feature_map_drafts"
        baseline = json.loads((drafts / "baseline_surface_draft.json").read_text(encoding="utf-8"))
        review = json.loads((drafts / "review_surface_draft.json").read_text(encoding="utf-8"))
        oxygen = json.loads((drafts / "editor_oxygen_surface_draft.json").read_text(encoding="utf-8"))
        active = json.loads(CANONICAL_MAP.read_text(encoding="utf-8"))

        self.assertEqual("PENDING_APPROVAL", baseline["curation_status"])
        baseline_approved = [
            feature
            for feature in baseline["native_features"]
            if feature.get("approval_status") == "HUMAN_APPROVED"
        ]
        self.assertEqual(["baseline translation project"], [item["feature"] for item in baseline_approved])
        self.assertEqual([APPROVED_URL], baseline_approved[0]["reference_urls"])

        self.assertEqual("PENDING_APPROVAL", review["curation_status"])
        review_approved = [
            feature
            for feature in review["native_features"]
            if feature.get("approval_status") == "HUMAN_APPROVED"
        ]
        self.assertEqual(
            {
                "review task membership and selected-task state",
                "review panel / task dropdown and details",
            },
            {item["feature"] for item in review_approved},
        )
        self.assertTrue(all(item["reference_urls"] == [REVIEW_URL] for item in review_approved))

        self.assertEqual("PENDING_APPROVAL", oxygen["curation_status"])
        self.assertFalse(any(item.get("approval_status") for item in oxygen["native_features"]))
        self.assertFalse(any(item.get("url_confirmed") for item in oxygen["native_features"]))
        self.assertNotIn("EDITOR_OXYGEN", {surface["surface"] for surface in active["surfaces"]})


if __name__ == "__main__":
    unittest.main()
