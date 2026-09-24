"""Offline tests for the UAC release automation (fake Jira, stubbed Copilot CLI)."""
from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import uac_approved_poster as poster  # noqa: E402
import uac_release_runner as runner  # noqa: E402

UAC = (
    "- Acceptance Criteria 01: Verify that the report opens from the Map console.\n"
    "  **Source:** Ticket description; ReportServlet.java line 10.\n"
    "- Acceptance Criteria 02: Verify that an empty report shows a message.\n"
    "  **Source:** Ticket description.\n"
    "  **TBD:** Which message text should be shown?\n"
)


class FakeJira:
    def __init__(self, field_value: str = "", rendered_ok: bool = True) -> None:
        self.field_value = field_value
        self.rendered_ok = rendered_ok
        self.calls: list[tuple] = []

    def search_keys(self, jql: str, max_results: int = 100) -> list[str]:
        self.calls.append(("search", jql))
        return ["PROJ-1"]

    def get_field(self, key, field, rendered=False):
        if rendered:
            return "<p><b>Acceptance Criteria 01:</b> x</p>" if self.rendered_ok else "<pre>x</pre>"
        return self.field_value

    def set_field(self, key, field, value):
        self.calls.append(("set_field", key, field, value))
        self.field_value = value

    def update_labels(self, key, add=(), remove=()):
        self.calls.append(("labels", key, list(add), list(remove)))

    def add_comment(self, key, body):
        self.calls.append(("comment", key, body))
        return "c1"

    def attach_file(self, key, path):
        self.calls.append(("attach", key, Path(path).name))
        return "a1"


def make_config(out: Path) -> dict:
    return {
        "jql": "project = PROJ",
        "output_dir": str(out),
        "acceptance_criteria_field": "customfield_1",
        "labels": {"draft": "UAC_Draft", "approved": "UAC_Approved", "posted": "UAC_Posted", "rework": "UAC_Rework"},
        "copilot": {"command": "copilot", "add_dirs": ["/repos/a"], "allow_all_tools": True,
                    "deny_tools": ["corp-jira(update_jira_issue)"], "timeout_minutes": 1},
    }


def fake_copilot(write_files: bool, returncode: int = 0):
    def run(cmd, **kwargs):
        prompt = cmd[cmd.index("-p") + 1]
        if write_files:
            uac_path = Path(prompt.split("1. ", 1)[1].split(": only", 1)[0].strip())
            uac_path.write_text(UAC, encoding="utf-8")
            (uac_path.parent / common.PLAN_FILE).write_text("plan", encoding="utf-8")
        return subprocess.CompletedProcess(cmd, returncode, "done", "")
    return run


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.log = logging.getLogger("test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_command_has_non_interactive_flags_and_denies_jira_writes(self) -> None:
        cmd = runner.copilot_command(self.config, "hello", self.out / "t.md")
        for flag in ("-p", "-s", "--no-ask-user", "--allow-all-tools", "--add-dir=/repos/a",
                     "--deny-tool=corp-jira(update_jira_issue)"):
            self.assertIn(flag, cmd)
        self.assertIn(f"--share={self.out / 't.md'}", cmd)

    def test_passing_ticket_posts_draft_comment_attachment_and_label(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            result = runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False)
        self.assertEqual(result, "DRAFT_POSTED")
        kinds = [c[0] for c in jira.calls]
        self.assertEqual(kinds, ["attach", "comment", "labels"])
        comment = jira.calls[1][2]
        self.assertIn("*Acceptance Criteria 01:*", comment)
        self.assertIn("{{ReportServlet.java}}", comment)
        self.assertNotIn(("set_field",), [c[:1] for c in jira.calls], "runner never fills the AC field")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "DRAFT_POSTED")
        self.assertEqual(status["uac_sha256"], common.sha256_file(self.out / "PROJ-1" / common.UAC_FILE))

    def test_dry_run_writes_nothing_to_jira(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=True), "READY")
        self.assertEqual(jira.calls, [])

    def test_failed_copilot_run_is_not_posted(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(False, returncode=1)):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        self.assertEqual(jira.calls, [])
        self.assertEqual(common.read_status(self.out / "PROJ-1")["state"], "FAILED")

    def test_check_outputs_rejects_missing_files_and_bad_ac_count(self) -> None:
        ticket = self.out / "PROJ-2"
        ticket.mkdir()
        self.assertTrue(any("was not written" in p for p in runner.check_outputs(ticket)))
        (ticket / common.UAC_FILE).write_text("- Acceptance Criteria 01: Verify x.\n" * 11, encoding="utf-8")
        (ticket / common.PLAN_FILE).write_text("plan", encoding="utf-8")
        ok = subprocess.CompletedProcess([], 0, "PASS", "")
        with mock.patch.object(runner.subprocess, "run", return_value=ok):
            problems = runner.check_outputs(ticket)
        self.assertTrue(any("11 Acceptance Criteria" in p for p in problems), problems)


class PosterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.log = logging.getLogger("test")
        ticket = self.out / "PROJ-1"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        (ticket / "field-body.txt").write_text("*Acceptance Criteria 01:* x", encoding="utf-8")
        common.write_status(ticket, {"state": "DRAFT_POSTED", "uac_sha256": common.sha256_file(ticket / common.UAC_FILE)})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_posts_approved_draft_and_swaps_labels(self) -> None:
        jira = FakeJira()
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "POSTED")
        self.assertIn(("set_field", "PROJ-1", "customfield_1", "*Acceptance Criteria 01:* x"), jira.calls)
        self.assertIn(("labels", "PROJ-1", ["UAC_Posted"], ["UAC_Draft"]), jira.calls)

    def test_never_overwrites_human_text(self) -> None:
        jira = FakeJira(field_value="Existing text written by a person")
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "FIELD_NOT_EMPTY")
        self.assertFalse(any(c[0] == "set_field" for c in jira.calls))

    def test_refuses_when_uac_changed_after_draft(self) -> None:
        (self.out / "PROJ-1" / common.UAC_FILE).write_text(UAC + "- Acceptance Criteria 03: new\n", encoding="utf-8")
        jira = FakeJira()
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "DRAFT_CHANGED")
        self.assertEqual(jira.calls, [])

    def test_render_check_failure_is_reported(self) -> None:
        jira = FakeJira(rendered_ok=False)
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "RENDER_CHECK_FAILED")

    def test_approved_jql_excludes_posted(self) -> None:
        jql = poster.approved_jql(self.config)
        self.assertIn('labels = "UAC_Approved"', jql)
        self.assertIn('labels != "UAC_Posted"', jql)


if __name__ == "__main__":
    unittest.main()
