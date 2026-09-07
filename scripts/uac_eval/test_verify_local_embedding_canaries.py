"""Only synthetic exported rows and fake encoders; no ML dependencies."""
from collections import namedtuple
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import verify_local_embedding_canaries as canaries
from verify_local_embedding_canaries import CheckFailed, compare_canaries, file_hash, model_hash, read_canaries


class CanaryTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.path = self.root / "export.jsonl"
        self.rows = [("one", [0.1, 0.2]), ("two", [0.3, 0.4]), ("three", [0.5, 0.6])]
        self.path.write_text("".join(json.dumps({"id": str(i), "document": text, "embedding": vector}) + "\n"
                                     for i, (text, vector) in enumerate(self.rows)), encoding="utf-8")

    def test_reads_only_verified_distinct_export_canaries(self):
        self.assertEqual(read_canaries(self.path, file_hash(self.path)), self.rows)

    def test_hash_mismatch_fails_before_encoding(self):
        with self.assertRaisesRegex(CheckFailed, "EXPORT_HASH_MISMATCH"):
            read_canaries(self.path, "0" * 64)

    def test_same_dimension_wrong_model_fails(self):
        with self.assertRaisesRegex(CheckFailed, "STORED_VECTOR_MISMATCH"):
            compare_canaries(self.rows, lambda texts: [[0.9, 0.1]] * 3, 2)

    def test_matching_samples_pass_without_global_parity_claim(self):
        receipt = compare_canaries(self.rows, lambda texts: [v for _, v in self.rows], 2)
        self.assertEqual(receipt, {"status": "SAMPLED_STORED_VECTORS_MATCH", "samples": 3, "dimension": 2})

    def test_dimension_mismatch_fails_without_truncating(self):
        with self.assertRaisesRegex(CheckFailed, "DIMENSION_MISMATCH"):
            compare_canaries(self.rows, lambda texts: [[0.1, 0.2, 0.3]] * 3, 2)

    def test_partial_nonfinite_and_zero_vectors_fail(self):
        for value in (None, [], [[0.1, 0.2]], [[float("nan"), 0.2]] * 3, [[0.0, 0.0]] * 3):
            with self.subTest(value=value), self.assertRaises(CheckFailed):
                compare_canaries(self.rows, lambda texts: value, 2)

    def test_fewer_than_three_distinct_texts_fails(self):
        self.path.write_text(json.dumps({"id": "a", "document": "one", "embedding": [0.1, 0.2]}) + "\n")
        with self.assertRaisesRegex(CheckFailed, "THREE_DISTINCT_CANARIES_REQUIRED"):
            read_canaries(self.path, file_hash(self.path))

    def test_model_hash_detects_changed_file(self):
        before = model_hash(self.root)
        self.path.write_text("changed")
        self.assertNotEqual(model_hash(self.root), before)

    def test_private_text_not_in_receipt(self):
        receipt = compare_canaries(self.rows, lambda texts: [v for _, v in self.rows], 2)
        self.assertNotIn("document", json.dumps(receipt))
        self.assertNotIn("embedding", json.dumps(receipt))


class MainPathTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.model_path = self.root / "model"
        self.model_path.mkdir()
        self.model_file = self.model_path / "model-fixture.json"
        self.model_file.write_text('{"fixture":true}', encoding="utf-8")
        self.export_path = self.root / "export.jsonl"
        self.documents = ["PRIVATE_DOCUMENT_ONE", "PRIVATE_DOCUMENT_TWO", "PRIVATE_DOCUMENT_THREE"]
        self.vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        self.export_path.write_text("".join(
            json.dumps({"id": "private-id-" + str(i), "document": text, "embedding": vector}) + "\n"
            for i, (text, vector) in enumerate(zip(self.documents, self.vectors))
        ), encoding="utf-8")
        self.export_digest = file_hash(self.export_path)
        self.model_digest = model_hash(self.model_path)
        self.model = Mock(spec=["encode"])
        self.model.encode.return_value = self.vectors
        self.constructor = Mock(return_value=self.model)
        self.module = ModuleType("sentence_transformers")
        self.module.SentenceTransformer = self.constructor

    def run_main(self, *, releaselevel="final", module=None):
        version = namedtuple("Version", "major minor micro releaselevel serial")(3, 11, 16, releaselevel, 0)
        runtime = SimpleNamespace(version_info=version, get_int_max_str_digits=lambda: 4300,
                                  dont_write_bytecode=False)
        output = io.StringIO()
        with patch.object(canaries, "sys", runtime), patch.dict(os.environ, {}, clear=True), patch.dict(
            sys.modules, {"sentence_transformers": self.module if module is None else module}
        ), redirect_stdout(output):
            code = canaries.main([
                "--model-path", str(self.model_path),
                "--export", str(self.export_path), self.export_digest,
                "--expected-dimension", "2",
            ])
        report = json.loads(output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())
        for text in self.documents + ["private-id-0", "private-id-1", "private-id-2"]:
            self.assertNotIn(text, output.getvalue())
        for field in ("database_opened", "services_changed", "index_writes",
                      "whole_corpus_model_identity_verified", "live_backend_verified", "resume_writers_authorized"):
            self.assertIs(report[field], False)
        return code, report

    def test_prerelease_rejects_before_importing_ml_module(self):
        module = ModuleType("sentence_transformers")
        attempted_import = Mock(side_effect=ImportError("PRIVATE_IMPORT_ERROR"))
        module.__getattr__ = attempted_import
        code, report = self.run_main(releaselevel="candidate", module=module)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "FINAL_PYTHON_311_OR_NEWER_REQUIRED")
        attempted_import.assert_not_called()
        self.constructor.assert_not_called()

    def test_import_failure_is_blocked_without_raw_exception_leak(self):
        module = ModuleType("sentence_transformers")
        private = "PRIVATE_IMPORT_ERROR Authorization: not-a-real-token"
        module.__getattr__ = Mock(side_effect=ImportError(private))
        code, report = self.run_main(module=module)
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "IMPORT_ENCODE_OR_FILE_FAILED")
        self.assertNotIn(private, json.dumps(report))
        self.assertEqual(report["samples"], [])
        self.constructor.assert_not_called()

    def test_success_preserves_offline_controls_and_reports_sample_scope_only(self):
        def construct(*args, **kwargs):
            for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY"):
                self.assertEqual(os.environ[key], "1")
            self.assertEqual(os.environ["TOKENIZERS_PARALLELISM"], "false")
            self.assertTrue(canaries.sys.dont_write_bytecode)
            return self.model
        self.constructor.side_effect = construct
        code, report = self.run_main()
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "PASS_OFFLINE_SAMPLES_ONLY")
        self.assertEqual(report["provider"], "LOCAL")
        self.assertEqual(report["model_sha256"], self.model_digest)
        self.assertEqual(report["python"], [3, 11, 16, "final", 0])
        self.assertEqual(report["samples"], [{"export_sha256": self.export_digest,
                                             "status": "SAMPLED_STORED_VECTORS_MATCH",
                                             "samples": 3, "dimension": 2}])
        self.constructor.assert_called_once_with(str(self.model_path), device="cpu", local_files_only=True,
                                                 trust_remote_code=False)
        self.model.encode.assert_called_once_with(self.documents, convert_to_numpy=True)

    def test_model_mutation_during_encode_blocks_success(self):
        def encode(*args, **kwargs):
            self.model_file.write_text('{"fixture":"changed"}', encoding="utf-8")
            return self.vectors
        self.model.encode.side_effect = encode
        code, report = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "MODEL_CHANGED_DURING_PROBE")
        self.assertNotIn("model_sha256", report)

    def test_export_mutation_during_encode_blocks_success(self):
        def encode(*args, **kwargs):
            self.export_path.write_text("changed fixture export", encoding="utf-8")
            return self.vectors
        self.model.encode.side_effect = encode
        code, report = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "EXPORT_CHANGED_DURING_PROBE")
        self.assertEqual(report["samples"], [])

    def test_encode_failure_is_blocked_without_document_or_exception_leak(self):
        private = "PRIVATE_ENCODE_ERROR " + self.documents[0]
        self.model.encode.side_effect = RuntimeError(private)
        code, report = self.run_main()
        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["reason"], "IMPORT_ENCODE_OR_FILE_FAILED")
        self.assertNotIn(private, json.dumps(report))
        self.assertEqual(report["samples"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
