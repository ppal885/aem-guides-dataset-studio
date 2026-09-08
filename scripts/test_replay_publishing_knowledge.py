"""Service-free checks for the guarded publishing-knowledge replay."""
from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

from scripts import replay_publishing_knowledge as replay


URLS = [
    "https://experienceleague.adobe.com/en/docs/"
    f"experience-manager-guides/using/replay-test/article-{index}"
    for index in range(9)
]


def success_output(urls: list[str] = URLS, chunks: int = 2) -> str:
    return "\n".join(f"OK  {chunks:3d} chunks  {url}" for url in urls)


class ReadUrlsTests(unittest.TestCase):
    def read_text(self, urls: list[str]) -> list[str]:
        with mock.patch.object(Path, "read_text", return_value="\n".join(urls) + "\n"):
            return replay.read_urls(Path("replay-test-urls.txt"))

    def test_accepts_nine_unique_documentation_urls_in_input_order(self) -> None:
        self.assertEqual(self.read_text(URLS), URLS)

    def test_rejects_duplicate_url_even_with_nine_lines(self) -> None:
        with self.assertRaises(replay.ReplayError):
            self.read_text(URLS[:-1] + [URLS[0]])

    def test_rejects_wrong_number_of_urls(self) -> None:
        for urls in ([], URLS[:-1], URLS + [URLS[0] + "-extra"]):
            with self.subTest(count=len(urls)), self.assertRaises(replay.ReplayError):
                self.read_text(urls)

    def test_rejects_unapproved_host_or_scheme(self) -> None:
        replacements = (
            URLS[0].replace("experienceleague.adobe.com", "example.invalid"),
            URLS[0].replace("experienceleague.adobe.com", "experienceleague.adobe.com.example.invalid"),
            URLS[0].replace("https://", "http://"),
            URLS[0].replace("/en/docs/", "/en/search/"),
        )
        for url in replacements:
            with self.subTest(url=url), self.assertRaises(replay.ReplayError):
                self.read_text([url] + URLS[1:])


class RequireTests(unittest.TestCase):
    def test_failed_requirement_raises_a_replay_error_with_the_reason(self) -> None:
        with self.assertRaisesRegex(replay.ReplayError, "CORPUS_ID_MISMATCH"):
            replay.require(False, "CORPUS_ID_MISMATCH")

    def test_satisfied_requirement_passes(self) -> None:
        replay.require(True, "CORPUS_ID_MISMATCH")


class ModelConfigurationTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="replay-model-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.service_cwd = self.root / "backend"
        self.model = self.service_cwd / "models/all-MiniLM-L6-v2"
        self.model.mkdir(parents=True)
        self.environment = {
            "USE_AZURE_EMBEDDING": "false",
            "DITA_EMBEDDING_MODEL_PATH": str(self.model),
        }
        model_patch = mock.patch.object(replay, "MODEL", self.model)
        model_patch.start()
        self.addCleanup(model_patch.stop)

    def assert_rejected(self, reason: str, environment: dict | None = None) -> None:
        with self.assertRaises(replay.ReplayError) as raised:
            replay.validate_model_configuration(
                self.environment if environment is None else environment, self.service_cwd
            )
        self.assertEqual(str(raised.exception), reason)

    def test_accepts_equivalent_absolute_and_relative_paths(self) -> None:
        for configured in (
            str(self.model),
            str(self.model) + "/",
            "models/all-MiniLM-L6-v2",
            "./models/all-MiniLM-L6-v2/",
            "models/../models/all-MiniLM-L6-v2",
            " \tmodels/all-MiniLM-L6-v2\n",
        ):
            with self.subTest(configured=configured):
                self.environment["DITA_EMBEDDING_MODEL_PATH"] = configured
                self.assertEqual(
                    replay.validate_model_configuration(self.environment, self.service_cwd),
                    self.model.resolve(strict=True),
                )

    def test_relative_path_uses_service_directory_without_changing_process_cwd(self) -> None:
        original_cwd = Path.cwd()
        self.assertNotEqual(original_cwd, self.service_cwd)
        self.environment["DITA_EMBEDDING_MODEL_PATH"] = "models/all-MiniLM-L6-v2"
        self.assertEqual(
            replay.validate_model_configuration(self.environment, self.service_cwd), self.model
        )
        self.assertEqual(Path.cwd(), original_cwd)

    def test_accepts_false_provider_values_and_missing_provider_default(self) -> None:
        for provider in ("false", "FALSE", "0", "no", "NO", "off", "Off"):
            with self.subTest(provider=provider):
                self.environment["USE_AZURE_EMBEDDING"] = provider
                self.assertEqual(
                    replay.validate_model_configuration(self.environment, self.service_cwd), self.model
                )
        del self.environment["USE_AZURE_EMBEDDING"]
        self.assertEqual(
            replay.validate_model_configuration(self.environment, self.service_cwd), self.model
        )

    def test_rejects_azure_invalid_and_whitespace_padded_provider_values(self) -> None:
        for provider in ("true", "TRUE", "1", "yes", "on", "", "invalid", " false ", "off\n", None):
            with self.subTest(provider=provider):
                self.environment["USE_AZURE_EMBEDDING"] = provider
                self.assert_rejected("EMBEDDING_PROVIDER_NOT_LOCAL")

    def test_rejects_missing_empty_or_non_string_path_without_using_bundled_model(self) -> None:
        for configured in ("", " \t\n", None, 123):
            with self.subTest(configured=configured):
                self.environment["DITA_EMBEDDING_MODEL_PATH"] = configured
                self.assert_rejected("MODEL_PATH_NOT_CONFIGURED")
        del self.environment["DITA_EMBEDDING_MODEL_PATH"]
        self.assert_rejected("MODEL_PATH_NOT_CONFIGURED")

    def test_rejects_missing_malformed_or_non_directory_path(self) -> None:
        file_path = self.service_cwd / "model-file"
        file_path.touch()
        for configured in ("models/missing", str(file_path), "models/invalid\0path"):
            with self.subTest(configured=configured):
                self.environment["DITA_EMBEDDING_MODEL_PATH"] = configured
                self.assert_rejected("MODEL_PATH_UNAVAILABLE")

    def test_rejects_a_different_existing_directory(self) -> None:
        other = self.service_cwd / "models/other"
        other.mkdir()
        for configured in (str(other), "models/other", ".", ".."):
            with self.subTest(configured=configured):
                self.environment["DITA_EMBEDDING_MODEL_PATH"] = configured
                self.assert_rejected("MODEL_PATH_TARGET_MISMATCH")

    def test_rejects_unavailable_reviewed_directory(self) -> None:
        file_path = self.root / "reviewed-model-file"
        file_path.touch()
        for reviewed in (self.root / "missing-reviewed-model", file_path):
            with self.subTest(reviewed=reviewed), mock.patch.object(replay, "MODEL", reviewed):
                self.assert_rejected("REVIEWED_MODEL_DIRECTORY_UNAVAILABLE")

    def test_does_not_expand_shell_syntax_or_remove_literal_quotes(self) -> None:
        with (
            mock.patch.dict(os.environ, {"REPLAY_TEST_MODEL": str(self.model)}),
            mock.patch.object(Path, "expanduser", side_effect=AssertionError("Unexpected expansion")),
            mock.patch.object(os.path, "expanduser", side_effect=AssertionError("Unexpected expansion")),
        ):
            for configured in (
                "~/models/all-MiniLM-L6-v2",
                "$REPLAY_TEST_MODEL",
                "${REPLAY_TEST_MODEL}",
                "%REPLAY_TEST_MODEL%",
                '"models/all-MiniLM-L6-v2"',
                "'models/all-MiniLM-L6-v2'",
            ):
                with self.subTest(configured=configured):
                    self.environment["DITA_EMBEDDING_MODEL_PATH"] = configured
                    self.assert_rejected("MODEL_PATH_UNAVAILABLE")

    def test_rejects_a_relative_service_directory(self) -> None:
        with self.assertRaises(replay.ReplayError) as raised:
            replay.validate_model_configuration(self.environment, Path("backend"))
        self.assertEqual(str(raised.exception), "SERVICE_WORKING_DIRECTORY_MISMATCH")

    def test_resolves_symlinks_before_comparing_the_reviewed_directory(self) -> None:
        alias = self.service_cwd / "model-alias"
        other = self.service_cwd / "other-model"
        other.mkdir()
        other_alias = self.service_cwd / "other-alias"
        try:
            alias.symlink_to(self.model, target_is_directory=True)
            other_alias.symlink_to(other, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"Directory symlinks are unavailable: {type(exc).__name__}")
        self.environment["DITA_EMBEDDING_MODEL_PATH"] = "model-alias"
        self.assertEqual(
            replay.validate_model_configuration(self.environment, self.service_cwd), self.model
        )
        self.environment["DITA_EMBEDDING_MODEL_PATH"] = "other-alias"
        self.assert_rejected("MODEL_PATH_TARGET_MISMATCH")

    def test_live_loader_accepts_relative_dotenv_override_and_normalizes_child_environment(self) -> None:
        python = self.root / "candidate-python"
        ca = self.root / "test-ca.pem"
        root_env = self.root / ".env"
        backend_env = self.service_cwd / ".env"
        for path in (python, ca, root_env, backend_env):
            path.touch()
        launch = {**replay.ROUTING, **self.environment, "REPLAY_TEST_WRITER": "off"}
        process = Path("/proc/12345")
        original_resolve = Path.resolve

        def resolve(path, *args, **kwargs):
            if path == process / "cwd":
                return self.service_cwd
            if path == process / "exe":
                return python
            return original_resolve(path, *args, **kwargs)

        def read_bytes(path):
            if path == process / "cmdline":
                return str(python).encode() + b"\0"
            if path == process / "environ":
                return b"\0".join(f"{key}={value}".encode() for key, value in launch.items())
            raise AssertionError(f"Unexpected read: {path}")

        def load_dotenv(path, **kwargs):
            self.assertEqual(kwargs, {"override": True, "encoding": "utf-8-sig"})
            if path == backend_env:
                os.environ["DITA_EMBEDDING_MODEL_PATH"] = "models/all-MiniLM-L6-v2"

        dotenv = SimpleNamespace(load_dotenv=mock.Mock(side_effect=load_dotenv))
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.dict(replay.sys.modules, {"dotenv": dotenv}),
            mock.patch.object(replay, "ROOT", self.root),
            mock.patch.object(replay, "PYTHON", python),
            mock.patch.object(replay, "CA", str(ca)),
            mock.patch.object(Path, "resolve", resolve),
            mock.patch.object(Path, "read_bytes", read_bytes),
            mock.patch.object(Path, "write_text", side_effect=AssertionError("Unexpected write")),
            mock.patch.object(Path, "write_bytes", side_effect=AssertionError("Unexpected write")),
            mock.patch.object(replay, "helper", return_value=SimpleNamespace(WRITERS=["REPLAY_TEST_WRITER"])) as helper,
        ):
            self.assertEqual(replay.load_live_configuration({"aem-backend.service": {"MainPID": "12345"}}), "")
            self.assertEqual(os.environ["DITA_EMBEDDING_MODEL_PATH"], str(self.model))
            self.assertEqual(os.environ["HF_HUB_OFFLINE"], "1")
            self.assertEqual(os.environ["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual([call.args[0] for call in dotenv.load_dotenv.call_args_list], [root_env, backend_env])
        helper.assert_called_once_with("repair_vm_chroma_routing")


class ParseSuccessTests(unittest.TestCase):
    def test_counts_every_requested_url_with_unrelated_log_lines(self) -> None:
        output = "Initializing local model\n" + success_output(list(reversed(URLS)), chunks=3)
        self.assertEqual(replay.parse_success(output, URLS), dict.fromkeys(URLS, 3))

    def test_rejects_missing_success_even_if_process_would_exit_zero(self) -> None:
        with self.assertRaises(replay.ReplayError):
            replay.parse_success(success_output(URLS[:-1]), URLS)

    def test_rejects_duplicate_success_for_a_requested_url(self) -> None:
        output = success_output() + "\n" + success_output([URLS[0]])
        with self.assertRaises(replay.ReplayError):
            replay.parse_success(output, URLS)

    def test_rejects_zero_chunks(self) -> None:
        output = success_output(URLS[:-1]) + "\n" + success_output([URLS[-1]], chunks=0)
        with self.assertRaises(replay.ReplayError):
            replay.parse_success(output, URLS)

    def test_rejects_negative_or_non_numeric_chunk_count(self) -> None:
        for count in ("-1", "two"):
            output = success_output(URLS[:-1]) + f"\nOK {count} chunks  {URLS[-1]}"
            with self.subTest(count=count), self.assertRaises(replay.ReplayError):
                replay.parse_success(output, URLS)

    def test_rejects_failure_or_skip_despite_all_success_lines(self) -> None:
        for status in ("FAIL", "SKIP"):
            output = success_output() + f"\n{status} {URLS[0]}"
            with self.subTest(status=status), self.assertRaises(replay.ReplayError):
                replay.parse_success(output, URLS)

    def test_rejects_success_for_an_unrequested_url(self) -> None:
        output = success_output() + "\n" + success_output([URLS[0] + "-unrequested"])
        with self.assertRaises(replay.ReplayError):
            replay.parse_success(output, URLS)


class VerifyRecordsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected_ids = ["aem_ingest_test_0", "aem_ingest_test_1"]
        self.records = {
            "ids": list(self.expected_ids),
            "documents": ["Native PDF template content.", "HTML5 preset content."],
            "metadatas": [{"url": URLS[0]}, {"url": URLS[0]}],
        }

    def test_accepts_complete_records_returned_in_a_different_order(self) -> None:
        reordered = {key: list(reversed(values)) for key, values in self.records.items()}
        replay.verify_records(reordered, URLS[0], self.expected_ids)

    def test_rejects_a_missing_expected_id(self) -> None:
        incomplete = {key: values[:-1] for key, values in self.records.items()}
        with self.assertRaises(replay.ReplayError):
            replay.verify_records(incomplete, URLS[0], self.expected_ids)

    def test_rejects_unexpected_ids_in_the_returned_record_set(self) -> None:
        self.records["ids"].append("aem_ingest_test_2")
        self.records["documents"].append("Content outside the requested ID set.")
        self.records["metadatas"].append({"url": URLS[0]})
        with self.assertRaises(replay.ReplayError):
            replay.verify_records(self.records, URLS[0], self.expected_ids)

    def test_rejects_wrong_id_even_when_total_count_matches(self) -> None:
        self.records["ids"][1] = "aem_ingest_other_url_1"
        with self.assertRaises(replay.ReplayError):
            replay.verify_records(self.records, URLS[0], self.expected_ids)

    def test_rejects_empty_or_non_string_documents(self) -> None:
        for document in ("", " \n\t ", None, 123):
            self.records["documents"][1] = document
            with self.subTest(document=document), self.assertRaises(replay.ReplayError):
                replay.verify_records(self.records, URLS[0], self.expected_ids)

    def test_rejects_metadata_for_a_different_url(self) -> None:
        self.records["metadatas"][1] = {"url": URLS[1]}
        with self.assertRaises(replay.ReplayError):
            replay.verify_records(self.records, URLS[0], self.expected_ids)

    def test_rejects_missing_document_or_metadata_entries(self) -> None:
        for key in ("documents", "metadatas"):
            incomplete = {name: list(values) for name, values in self.records.items()}
            incomplete[key].pop()
            with self.subTest(field=key), self.assertRaises(replay.ReplayError):
                replay.verify_records(incomplete, URLS[0], self.expected_ids)

    def test_rejects_metadata_without_the_source_url(self) -> None:
        for metadata in ({}, None, {"source": URLS[0]}):
            self.records["metadatas"][1] = metadata
            with self.subTest(metadata=metadata), self.assertRaises(replay.ReplayError):
                replay.verify_records(self.records, URLS[0], self.expected_ids)


class MainModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = {"urls": URLS, "token": "fixture-only-token", "services": {}, "identity": {}}

    def run_main(self, argv: list[str], check_error: Exception | None = None):
        def apply_stub(context, output_parent, receipt):
            receipt.update(status="PASS_APPLIED", phase="COMPLETE")

        stdout = io.StringIO()
        with (
            mock.patch.object(replay, "check", return_value=self.context, side_effect=check_error) as check,
            mock.patch.object(replay, "apply", side_effect=apply_stub) as apply,
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(Path, "write_text", side_effect=AssertionError("Unexpected file write")) as write,
            contextlib.redirect_stdout(stdout),
        ):
            result = replay.main(argv)
        write.assert_not_called()
        self.assertNotIn(self.context["token"], stdout.getvalue())
        return result, json.loads(stdout.getvalue()), check, apply

    def test_default_mode_checks_without_applying(self) -> None:
        result, receipt, check, apply = self.run_main([])
        self.assertEqual(result, 0)
        self.assertEqual(receipt["status"], "PASS_CHECK_ONLY")
        self.assertEqual(receipt["mode"], "check")
        self.assertFalse(receipt["model_compatibility_checked"])
        check.assert_called_once_with()
        apply.assert_not_called()

    def test_explicit_check_does_not_apply(self) -> None:
        result, receipt, check, apply = self.run_main(["--check"])
        self.assertEqual(result, 0)
        self.assertEqual(receipt["status"], "PASS_CHECK_ONLY")
        check.assert_called_once_with()
        apply.assert_not_called()

    def test_explicit_apply_dispatches_only_after_the_check(self) -> None:
        result, receipt, check, apply = self.run_main(["--apply", "--output-parent", "mock-output-parent"])
        self.assertEqual(result, 0)
        self.assertEqual(receipt["status"], "PASS_APPLIED")
        self.assertEqual(receipt["mode"], "apply")
        check.assert_called_once_with()
        apply.assert_called_once()
        self.assertIs(apply.call_args.args[0], self.context)
        self.assertEqual(apply.call_args.args[1], Path("mock-output-parent"))

    def test_failed_check_never_reaches_apply(self) -> None:
        result, receipt, check, apply = self.run_main(
            ["--apply"], check_error=replay.ReplayError("COLLECTION_UUID_CHANGED")
        )
        self.assertEqual(result, 1)
        self.assertEqual(receipt["status"], "STOP")
        self.assertEqual(receipt["reason"], "COLLECTION_UUID_CHANGED")
        check.assert_called_once_with()
        apply.assert_not_called()

    def test_unexpected_check_failure_does_not_disclose_exception_details(self) -> None:
        result, receipt, _, apply = self.run_main(
            ["--apply"], check_error=RuntimeError(self.context["token"])
        )
        self.assertEqual(result, 1)
        self.assertEqual(receipt["reason"], "UNEXPECTED_FAILURE")
        apply.assert_not_called()

    def test_conflicting_modes_are_rejected_before_any_check_or_apply(self) -> None:
        with (
            mock.patch.object(replay, "check") as check,
            mock.patch.object(replay, "apply") as apply,
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as raised,
        ):
            replay.main(["--check", "--apply"])
        self.assertEqual(raised.exception.code, 2)
        check.assert_not_called()
        apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
