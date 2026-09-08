"""Service-free checks for the guarded publishing-knowledge replay."""
from __future__ import annotations

import contextlib
import io
import json
import os
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
