"""Service-free checks for the guarded publishing-knowledge replay."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import logging
import os
import tempfile
from types import SimpleNamespace
import unittest
from pathlib import Path
from unittest import mock

from scripts import replay_publishing_knowledge as replay
from scripts import ingest_urls as ingest


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

    def test_single_url_dispatches_without_changing_the_default_url_list(self) -> None:
        result, _, check, apply = self.run_main(["--check", "--url", URLS[0]])
        self.assertEqual(result, 0)
        check.assert_called_once_with(single_url=URLS[0])
        apply.assert_not_called()

    def test_single_url_apply_dispatches_after_single_url_check(self) -> None:
        result, _, check, apply = self.run_main(["--apply", "--url", URLS[0]])
        self.assertEqual(result, 0)
        check.assert_called_once_with(single_url=URLS[0])
        apply.assert_called_once()

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


class PreparedPageTests(unittest.TestCase):
    """The new path never calls the permissive legacy fetch, a model, or a database."""

    def response(self, *, status=200, body=b"<title>Variables</title><p>Variable Sets use values.</p>",
                 content_type="text/html; charset=utf-8", location=None):
        headers = {"content-type": content_type}
        if location:
            headers["location"] = location
        value = mock.MagicMock(status_code=status, headers=headers, encoding="utf-8")
        value.__enter__.return_value = value
        value.iter_bytes.return_value = [body]
        return value

    def prepare(self, responses, url=URLS[0]):
        client = mock.MagicMock()
        client.__enter__.return_value = client
        client.stream.side_effect = responses
        httpx = SimpleNamespace(Client=mock.Mock(return_value=client))
        with (mock.patch.dict(replay.sys.modules, {"httpx": httpx}),
              mock.patch("ssl.create_default_context", return_value="verified-CA") as tls,
              mock.patch.object(ingest, "_fetch_text", side_effect=AssertionError("No legacy refetch")),
              mock.patch.object(ingest, "_split", side_effect=lambda text, size, overlap: [text]) as split):
            result = ingest.prepare_guides_page(url, cafile="reviewed-CA-file")
        tls.assert_called_once_with(cafile="reviewed-CA-file")
        httpx.Client.assert_called_once_with(timeout=30, follow_redirects=False, verify="verified-CA")
        return result, client, split

    def test_fetches_once_and_uses_existing_split_and_id_contract(self):
        result, client, split = self.prepare([self.response()])
        client.stream.assert_called_once_with("GET", URLS[0])
        split.assert_called_once_with("Variables Variable Sets use values.", 1000, 200)
        self.assertEqual(result["ids"], ["aem_ingest_" + hashlib.md5(URLS[0].encode()).hexdigest()[:10] + "_0"])
        self.assertEqual(result["metadatas"], [{"url": URLS[0], "title": "Variables"}])
        self.assertEqual(len(result["page_sha256"]), 64)
        self.assertEqual(result["text_sha256"], hashlib.sha256(result["documents"][0].encode()).hexdigest())

    def test_valid_same_origin_redirect_keeps_original_provenance(self):
        result, client, _ = self.prepare([self.response(status=302, location=URLS[1]), self.response()])
        self.assertEqual(result["url"], URLS[0])
        self.assertEqual(result["final_url"], URLS[1])
        self.assertEqual(client.stream.call_count, 2)

    def test_cross_origin_redirect_is_never_requested(self):
        with self.assertRaisesRegex(ValueError, "UNEXPECTED_URL"):
            self.prepare([self.response(status=302, location="http://127.0.0.1/private")])

    def test_rejects_status_content_type_empty_text_and_oversize(self):
        for response in [self.response(status=404), self.response(status=500),
                         self.response(content_type="application/json"), self.response(body=b"<p></p>"),
                         self.response(body=b"x" * (2 * 1024 * 1024 + 1))]:
            with self.subTest(response=response), self.assertRaises(ValueError):
                self.prepare([response])

    def test_rejects_excessive_redirects(self):
        with self.assertRaisesRegex(ValueError, "PAGE_REDIRECT_LIMIT"):
            self.prepare([self.response(status=302, location=URLS[0]) for _ in range(6)])

    def test_rejects_http_200_soft_error_and_access_pages(self):
        for html in [b"<title>Page not found</title><main><h1>404</h1><p>The requested page could not be found.</p></main>",
                     b"<title>Access denied | Adobe</title><h1>Forbidden</h1>",
                     b"<title>Variables</title><h1>Sign in</h1><p>Authentication required</p>",
                     b"<title>Just a moment...</title><p>Verify you are human.</p>"]:
            with self.subTest(html=html), self.assertRaisesRegex(ValueError, "PAGE_ERROR_DOCUMENT"):
                self.prepare([self.response(body=html)])

    def test_rejects_generic_landing_after_same_origin_redirect(self):
        with self.assertRaisesRegex(ValueError, "PAGE_GENERIC_LANDING"):
            self.prepare([self.response(status=302, location=URLS[1]),
                          self.response(body=b"<title>Experience League | Adobe</title><h1>Welcome</h1>")])

    def test_accepts_real_document_that_mentions_error_message_in_its_body(self):
        html = b"<title>Native PDF troubleshooting</title><h1>Fix publishing problems</h1><p>A missing image can show Page not found or Access denied.</p>"
        prepared, _, _ = self.prepare([self.response(body=html)])
        self.assertIn("Page not found", prepared["documents"][0])

    def test_rejects_url_credentials_ports_queries_fragments_and_other_products(self):
        for url in [URLS[0].replace("https://", "https://user:secret@"), URLS[0] + "?token=secret",
                    URLS[0] + "#heading", URLS[0].replace(".com/", ".com:443/"),
                    URLS[0].replace("experience-manager-guides", "experience-manager"), URLS[0] + "\n",
                    URLS[0].replace("/using/", "/../"), URLS[0].replace("/using/", "/%2e%2e/"),
                    URLS[0].replace("/using/", "/%5c..%5c/")]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                ingest.validate_guides_url(url)


class MissingOnlyAppendTests(unittest.TestCase):
    def setUp(self):
        self.prepared = {"url": URLS[0], "final_url": URLS[1], "ids": ["aem_ingest_fixture_0"],
                         "documents": ["Public documentation about Variables."],
                         "metadatas": [{"url": URLS[0], "title": "Variables"}]}
        self.vectors = [[0.125] * 384]
        self.receipt = {"index_write_requested": False}
        self.rows = {}
        self.collection = mock.Mock()
        self.collection.get.side_effect = self.get
        self.collection.add.side_effect = self.add
        self.embed = mock.Mock(return_value=self.vectors)
        self.queue = mock.Mock(return_value=True)
        self.state = mock.Mock()

    def get(self, *, ids=None, where=None, **kwargs):
        keys = [key for key, value in self.rows.items()
                if (key in ids if ids is not None else all(value["metadata"].get(k) == v for k, v in where.items()))]
        return {"ids": keys, "documents": [self.rows[key]["document"] for key in keys],
                "metadatas": [self.rows[key]["metadata"] for key in keys],
                "embeddings": [self.rows[key]["embedding"] for key in keys]}

    def add(self, *, ids, documents, metadatas, embeddings):
        # Chroma add, unlike upsert, leaves existing IDs unchanged.
        for key, doc, meta, vector in zip(ids, documents, metadatas, embeddings):
            self.rows.setdefault(key, {"document": doc, "metadata": meta, "embedding": vector})

    def run_append(self):
        replay.append_missing_page(self.collection, self.prepared, self.embed, self.queue, self.state, self.receipt)

    def test_adds_frozen_payload_without_upsert_and_verifies_all_payload_fields(self):
        self.run_append()
        self.collection.add.assert_called_once_with(ids=self.prepared["ids"], documents=self.prepared["documents"],
                                                    metadatas=self.prepared["metadatas"], embeddings=self.vectors)
        self.collection.upsert.assert_not_called()
        self.assertTrue(self.receipt["exact_payload_readback"])
        self.assertTrue(self.receipt["index_write_requested"])
        self.state.assert_called_once()
        self.queue.assert_called_once()

    def test_existing_url_under_any_metadata_field_or_alternate_id_stops_without_write(self):
        for field in ("url", "source_url", "source"):
            for url in (URLS[0], URLS[1], URLS[0] + "/"):
                with self.subTest(field=field, url=url):
                    self.rows = {"crawler-other-id": {"document": "Existing page", "metadata": {field: url},
                                                      "embedding": self.vectors[0]}}
                    with self.assertRaisesRegex(replay.ReplayError, "URL_ALREADY_PRESENT_NO_WRITE"):
                        self.run_append()
        self.embed.assert_not_called()
        self.collection.add.assert_not_called()
        self.queue.assert_not_called()
        self.assertFalse(self.receipt["index_write_requested"])

    def test_id_collision_even_with_unrelated_metadata_stops_without_write(self):
        self.rows[self.prepared["ids"][0]] = {"document": "Unrelated", "metadata": {}, "embedding": self.vectors[0]}
        with self.assertRaisesRegex(replay.ReplayError, "INGEST_ID_ALREADY_PRESENT_NO_WRITE"):
            self.run_append()
        self.collection.add.assert_not_called()

    def test_repeated_run_never_overwrites_or_duplicates(self):
        self.run_append()
        original = copy.deepcopy(self.rows)
        with self.assertRaisesRegex(replay.ReplayError, "URL_ALREADY_PRESENT_NO_WRITE"):
            self.run_append()
        self.assertEqual(self.rows, original)
        self.collection.add.assert_called_once()

    def test_changed_identity_during_embedding_stops_before_add(self):
        self.state.side_effect = replay.ReplayError("STATE_CHANGED_BEFORE_ADD")
        with self.assertRaisesRegex(replay.ReplayError, "STATE_CHANGED_BEFORE_ADD"):
            self.run_append()
        self.collection.add.assert_not_called()

    def test_second_absence_check_catches_writer_during_embedding(self):
        def encode(documents):
            self.rows["new-crawler-id"] = {"document": "Writer added page", "metadata": {"url": URLS[0]},
                                           "embedding": self.vectors[0]}
            return self.vectors
        self.embed.side_effect = encode
        with self.assertRaisesRegex(replay.ReplayError, "URL_ALREADY_PRESENT_NO_WRITE"):
            self.run_append()
        self.collection.add.assert_not_called()

    def test_conflicting_race_at_add_never_overwrites_and_fails_readback(self):
        conflict = {"document": "Concurrent content", "metadata": {"url": URLS[0]}, "embedding": self.vectors[0]}
        def racing_add(**kwargs):
            self.rows[self.prepared["ids"][0]] = copy.deepcopy(conflict)
            self.add(**kwargs)
        self.collection.add.side_effect = racing_add
        with self.assertRaisesRegex(replay.ReplayError, "EXACT_PAYLOAD_READBACK_MISMATCH"):
            self.run_append()
        self.assertEqual(self.rows[self.prepared["ids"][0]], conflict)
        self.queue.assert_not_called()
        self.assertTrue(self.receipt["index_write_requested"])

    def test_incomplete_readback_fails_without_graph_event(self):
        self.collection.add.side_effect = None
        with self.assertRaisesRegex(replay.ReplayError, "INGEST_RECORDS_MISSING"):
            self.run_append()
        self.queue.assert_not_called()

    def test_wrong_vector_readback_fails(self):
        def changed_vector(**kwargs):
            self.add(**kwargs)
            self.rows[self.prepared["ids"][0]]["embedding"] = [0.25] * 384
        self.collection.add.side_effect = changed_vector
        with self.assertRaisesRegex(replay.ReplayError, "EXACT_PAYLOAD_READBACK_MISMATCH"):
            self.run_append()

    def test_graph_failure_is_honest_about_already_added_vectors(self):
        self.queue.return_value = False
        with self.assertRaisesRegex(replay.ReplayError, "GRAPH_EVENT_CAPTURE_FAILED_AFTER_ADD"):
            self.run_append()
        self.assertTrue(self.receipt["index_write_requested"])
        self.assertTrue(self.receipt["exact_payload_readback"])
        self.assertEqual(len(self.rows), 1)

    def test_graph_exception_and_logs_are_suppressed_and_logging_restored(self):
        fixture_secret = "fixture-secret-not-for-terminal"
        original_level = logging.root.manager.disable
        output, errors = io.StringIO(), io.StringIO()
        def fail(*args, **kwargs):
            logging.getLogger("graph-fixture").error(fixture_secret)
            print(fixture_secret)
            print(fixture_secret, file=replay.sys.stderr)
            raise RuntimeError(fixture_secret)
        self.queue.side_effect = fail
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            with self.assertRaisesRegex(replay.ReplayError, "GRAPH_EVENT_CAPTURE_FAILED_AFTER_ADD"):
                self.run_append()
        self.assertNotIn(fixture_secret, output.getvalue() + errors.getvalue())
        self.assertEqual(logging.root.manager.disable, original_level)
        self.assertTrue(self.receipt["index_write_requested"])
        self.assertTrue(self.receipt["exact_payload_readback"])

    def test_bad_embedding_never_reaches_add(self):
        for vectors in [None, [], [[0.1] * 383], [[0] * 384], [[float("nan")] * 384],
                        [[float("inf")] * 384], [[1e100] * 384], [[True] * 384]]:
            self.embed.return_value = vectors
            with self.subTest(vectors=str(vectors)[:30]), self.assertRaises(replay.ReplayError):
                self.run_append()
        self.collection.add.assert_not_called()

    def test_malformed_absence_result_never_reaches_embedding(self):
        self.collection.get.side_effect = None
        self.collection.get.return_value = {"missing": "ids"}
        with self.assertRaisesRegex(replay.ReplayError, "ABSENCE_RESPONSE_INVALID"):
            self.run_append()
        self.embed.assert_not_called()

    def test_apply_writes_frozen_receipt_without_refetch_or_legacy_ingest(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            root = parent / "repo"
            config = root / "backend/config/aem_guides_crawl_urls.json"
            config.parent.mkdir(parents=True)
            original_config = json.dumps({"urls": [URLS[0]]}).encode()
            config.write_bytes(original_config)
            prepared = {**self.prepared, "page_sha256": "a" * 64, "text_sha256": "b" * 64}
            context = {"urls": [URLS[0]], "prepared": prepared, "token": "fixture-only", "services": {},
                       "identity": {"collections": {"aem_guides": {"id": "fixture-aem", "count": 100},
                                                   "jira_qa": {"id": "fixture-jira", "count": 50}}}}
            self.collection.id = "fixture-aem"
            original_get = self.collection.get.side_effect
            def get(**kwargs):
                if kwargs.get("limit") == 20:
                    return {"documents": ["First canary", "Second canary", "Third canary"],
                            "embeddings": self.vectors * 3}
                return original_get(**kwargs)
            self.collection.get.side_effect = get
            vector_service = SimpleNamespace(_get_client=lambda: SimpleNamespace(get_collection=lambda name: self.collection),
                                             get_index_identity=lambda: context["identity"],
                                             _queue_evidence_graph_events=self.queue)
            model_check = SimpleNamespace(model_hash=lambda path: replay.MODEL_HASH,
                                          compare_canaries=mock.Mock(return_value={"status": "PASS_SAMPLES"}))
            imports = {"app": SimpleNamespace(), "app.services": SimpleNamespace(
                embedding_service=SimpleNamespace(embed_texts=self.embed), vector_store_service=vector_service)}
            helpers = {"verify_local_embedding_canaries": model_check, "vm_chroma_routing_checks":
                       SimpleNamespace(_checked_identity=lambda identity, collections: identity)}
            def identity(token):
                actual = copy.deepcopy(context["identity"])
                actual["collections"]["aem_guides"]["count"] += len(self.rows)
                return actual
            receipt = {}
            with (mock.patch.object(replay, "ROOT", root), mock.patch.dict(replay.sys.modules, imports),
                  mock.patch.object(replay, "helper", side_effect=lambda name: helpers[name]),
                  mock.patch.object(replay, "service_snapshot", return_value={}),
                  mock.patch.object(replay, "shared_identity", side_effect=identity),
                  mock.patch.object(replay, "missing_url_lock", return_value=contextlib.nullcontext()),
                  mock.patch.object(replay, "ingest_helper", side_effect=AssertionError("No refetch")),
                  mock.patch.object(replay.subprocess, "run", side_effect=AssertionError("No legacy upsert"))):
                replay.apply(context, parent, receipt)
            self.assertEqual(receipt["status"], "PASS_SINGLE_URL_APPENDED")
            self.assertEqual(receipt["chunks_by_url"], {URLS[0]: 1})
            self.assertFalse(receipt["crawl_config_changed"])
            self.assertEqual(config.read_bytes(), original_config)
            frozen_file = Path(receipt["output_directory"]) / "prepared-page.json"
            self.assertEqual(json.loads(frozen_file.read_text(encoding="utf-8")), prepared)
            self.assertEqual(hashlib.sha256(frozen_file.read_bytes()).hexdigest(), receipt["prepared_payload_sha256"])
            self.collection.upsert.assert_not_called()
            model_check.compare_canaries.assert_called_once()


if __name__ == "__main__":
    unittest.main()
