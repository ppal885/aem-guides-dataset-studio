"""The on-demand request queue and the runner's --on-demand mode."""
from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import uac_release_runner as runner  # noqa: E402
import uac_request_queue as q  # noqa: E402


class QueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.queue = q.UacRequestQueue(Path(self.tmp.name) / "requests")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_create_normalises_key_and_dedupes_open_requests(self) -> None:
        first, created = self.queue.create("guides-1", requested_by="vision")
        self.assertTrue(created)
        self.assertEqual(first["jira_key"], "GUIDES-1")
        self.assertEqual(first["status"], "queued")
        again, created = self.queue.create("GUIDES-1")
        self.assertFalse(created, "an open request is reused")
        self.assertEqual(again["request_id"], first["request_id"])
        self.queue.finish(first["request_id"], runner_state="POSTED", ac_count=4)
        third, created = self.queue.create("GUIDES-1")
        self.assertTrue(created, "a finished ticket can be requested again")
        self.assertNotEqual(third["request_id"], first["request_id"])

    def test_invalid_keys_and_ids_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.queue.create("not a key")
        with self.assertRaises(ValueError):
            self.queue.get("../../etc/passwd")
        self.assertIsNone(self.queue.get("req_000000000000"))

    def test_queued_is_oldest_first_one_per_ticket_and_limited(self) -> None:
        ids = []
        for key in ("GUIDES-3", "GUIDES-2", "GUIDES-2", "GUIDES-1"):
            row, _ = self.queue.create(key)
            ids.append(row["request_id"])
            # force distinct, increasing created_at values
            path = self.queue._path(row["request_id"])
            data = json.loads(path.read_text(encoding="utf-8"))
            data["created_at"] = f"2026-01-01T00:00:0{len(ids)}+0000"
            data["created_ts"] = float(len(ids))
            path.write_text(json.dumps(data), encoding="utf-8")
        picked = self.queue.queued(limit=2)
        self.assertEqual([r["jira_key"] for r in picked], ["GUIDES-3", "GUIDES-2"])
        self.assertEqual(len(self.queue.queued(limit=10)), 3, "GUIDES-2 appears once")

    def test_finish_maps_runner_states(self) -> None:
        cases = {
            "POSTED": ("posted", ""),
            "FIELD_KEPT": ("skipped", "FIELD_KEPT"),
            "NOT_REQUIRED": ("skipped", "NOT_REQUIRED"),
            "CLOSURE_ASKED": ("skipped", "CLOSURE_ASKED"),
            "SKIPPED": ("skipped", "ALREADY_POSTED"),
            "FAILED": ("failed", "CHECKS_FAILED"),
            "WRITTEN_UNRENDERED": ("failed", "WRITTEN_UNRENDERED"),
            "ERROR": ("failed", "ERROR"),
            "SOMETHING_NEW": ("failed", "SOMETHING_NEW"),
        }
        for index, (state, expected) in enumerate(cases.items()):
            row, _ = self.queue.create(f"GUIDES-{100 + index}")
            done = self.queue.finish(row["request_id"], runner_state=state, problems=["p1", "p2"], ac_count=3)
            self.assertEqual((done["status"], done["reason"]), expected, state)
            self.assertEqual(done["problems"], ["p1", "p2"])
            self.assertEqual(done["ac_count"], 3)

    def test_mark_running_only_from_queued_and_stale_running_is_requeued(self) -> None:
        row, _ = self.queue.create("GUIDES-7")
        self.assertEqual(self.queue.mark_running(row["request_id"], run_id="r1")["status"], "running")
        self.assertIsNone(self.queue.mark_running(row["request_id"], run_id="r2"), "already running")
        path = self.queue._path(row["request_id"])
        old = time.time() - 3600
        os.utime(path, (old, old))
        self.assertEqual(self.queue.requeue_stale_running(max_age_seconds=1800), [row["request_id"]])
        self.assertEqual(self.queue.get(row["request_id"])["status"], "queued")
        self.assertEqual(self.queue.requeue_stale_running(max_age_seconds=1800), [], "fresh files stay")

    def test_public_view_has_poll_url_and_no_internals(self) -> None:
        row, _ = self.queue.create("GUIDES-9", note="from a test")
        view = q.public_view(row)
        self.assertEqual(view["poll_url"], f"/api/v1/uac-requests/{row['request_id']}")
        self.assertEqual(view["note"], "from a test")


class OnDemandRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "runs"
        self.out.mkdir()
        self.config = {"output_dir": str(self.out), "lock_max_age_minutes": 720, "on_demand_max_tickets": 2}
        self.queue = q.UacRequestQueue(runner.requests_dir(self.config))
        self.log = logging.getLogger("uac-request-queue-test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _fake_process_ticket(self, outcomes: dict[str, tuple[str, str, str]]):
        def fake(key, config, jira, logger, dry_run):
            result, state, uac = outcomes[key]
            ticket_dir = self.out / key
            ticket_dir.mkdir(parents=True, exist_ok=True)
            if uac:
                (ticket_dir / common.UAC_FILE).write_text(uac, encoding="utf-8")
            common.write_status(ticket_dir, {"key": key, "state": state,
                                             "problems": [] if result != "FAILED" else ["validator said no"]})
            return result
        return fake

    def test_requests_dir_defaults_under_output_dir(self) -> None:
        self.assertEqual(runner.requests_dir(self.config), self.out / "requests")
        self.assertEqual(runner.requests_dir({**self.config, "requests_dir": "/elsewhere"}), Path("/elsewhere"))

    def test_process_requests_runs_the_ticket_flow_and_records_each_outcome(self) -> None:
        posted, _ = self.queue.create("GUIDES-11", requested_by="vision")
        kept, _ = self.queue.create("GUIDES-12")
        third, _ = self.queue.create("GUIDES-13")  # beyond on_demand_max_tickets, stays queued
        uac = "- Acceptance Criteria 01: A.\n- Acceptance Criteria 02: B.\n"
        outcomes = {"GUIDES-11": ("POSTED", "POSTED", uac), "GUIDES-12": ("SKIPPED", "FIELD_KEPT", "")}
        with mock.patch.object(runner, "process_ticket", side_effect=self._fake_process_ticket(outcomes)):
            results, errors = runner.process_requests(self.config, jira=None, logger=self.log, run_id="run-x", dry_run=False)
        self.assertEqual(results, {"GUIDES-11": "POSTED", "GUIDES-12": "SKIPPED"})
        self.assertEqual(errors, {})
        done = self.queue.get(posted["request_id"])
        self.assertEqual((done["status"], done["ac_count"], done["run_id"]), ("posted", 2, "run-x"))
        skipped = self.queue.get(kept["request_id"])
        self.assertEqual((skipped["status"], skipped["reason"]), ("skipped", "FIELD_KEPT"))
        self.assertEqual(self.queue.get(third["request_id"])["status"], "queued")

    def test_already_posted_ticket_and_failures_are_reported(self) -> None:
        again, _ = self.queue.create("GUIDES-21")
        failed, _ = self.queue.create("GUIDES-22")
        outcomes = {"GUIDES-21": ("SKIPPED", "POSTED", "- Acceptance Criteria 01: old.\n"),
                    "GUIDES-22": ("FAILED", "FAILED", "")}
        with mock.patch.object(runner, "process_ticket", side_effect=self._fake_process_ticket(outcomes)):
            runner.process_requests(self.config, jira=None, logger=self.log, run_id="run-y", dry_run=False)
        self.assertEqual(self.queue.get(again["request_id"])["reason"], "ALREADY_POSTED")
        view = self.queue.get(failed["request_id"])
        self.assertEqual((view["status"], view["reason"], view["problems"]), ("failed", "CHECKS_FAILED", ["validator said no"]))

    def test_an_exception_in_one_ticket_does_not_stop_the_others(self) -> None:
        boom, _ = self.queue.create("GUIDES-31")
        ok, _ = self.queue.create("GUIDES-32")
        good = self._fake_process_ticket({"GUIDES-32": ("POSTED", "POSTED", "- Acceptance Criteria 01: x.\n")})

        def fake(key, *args):
            if key == "GUIDES-31":
                raise RuntimeError("copilot exploded")
            return good(key, *args)

        with mock.patch.object(runner, "process_ticket", side_effect=fake):
            results, errors = runner.process_requests(self.config, jira=None, logger=self.log, run_id="run-z", dry_run=False)
        self.assertEqual(results, {"GUIDES-31": "ERROR", "GUIDES-32": "POSTED"})
        self.assertIn("copilot exploded", errors["GUIDES-31"])
        view = self.queue.get(boom["request_id"])
        self.assertEqual((view["status"], view["reason"]), ("failed", "ERROR"))
        self.assertIn("copilot exploded", view["error"])
        self.assertEqual(self.queue.get(ok["request_id"])["status"], "posted")

    def test_main_on_demand_uses_the_queue_not_the_jql(self) -> None:
        self.queue.create("GUIDES-41")
        config = {**self.config, "jql": "project = X", "max_tickets": 5}
        seen = []

        class FakeJira:
            calls = []

            def search_keys(self, jql, max_results=100):
                self.calls.append(("search", jql))
                return ["GUIDES-99"]

        jira = FakeJira()
        with mock.patch.object(runner, "health", return_value=[]), \
                mock.patch.object(runner.common, "load_config", return_value=config), \
                mock.patch.object(runner.common.JiraClient, "from_env", return_value=jira), \
                mock.patch.object(runner.common, "send_alert", return_value=""), \
                mock.patch.object(runner, "process_ticket",
                                  side_effect=lambda k, *a: seen.append(k) or self._fake_process_ticket(
                                      {k: ("POSTED", "POSTED", "- Acceptance Criteria 01: y.\n")})(k, *a)):
            code = runner.main(["--config", "unused.json", "--env-file", str(self.out / "missing.env"), "--on-demand"])
        run_logger = logging.getLogger("uac-runner")
        for handler in list(run_logger.handlers):
            handler.close()
            run_logger.removeHandler(handler)
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["GUIDES-41"])
        self.assertEqual(jira.calls, [], "on-demand never runs the JQL")


if __name__ == "__main__":
    unittest.main()
