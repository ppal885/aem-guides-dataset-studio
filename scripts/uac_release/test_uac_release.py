"""Offline tests for the UAC release automation (fake Jira, stubbed Copilot CLI)."""
from __future__ import annotations

import json
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
        self.calls.append(("search", jql, max_results))
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

    def get_people(self, key):
        self.calls.append(("people", key))
        return {"assignee": "dev.lead", "reporter": "support.eng"}


DECISIONS = (
    "### What we found\n- The [Home page] menu does not read extensions ({{menu_service.ts}}).\n\n"
    "### Decision needed\n1. Is a button enough?\n\n"
    "### Impact on the Acceptance Criteria\n- Acceptance Criteria 02 depends on question 1.\n"
)


DOC_RESEARCH = {
    "status": "ANSWER_FOUND",
    "findings": [{"claim": "The Home page lists tasks.", "evidence_role": "EXISTING_BEHAVIOR",
                  "source_refs": ["doc:home"], "provenance": {"locator": "https://experienceleague.adobe.com/home"}}],
    "source_refs": ["doc:home"], "applicability": "Cloud Service", "limitations": [], "conflicts": [],
}


def make_config(out: Path) -> dict:
    return {
        "jql": "project = PROJ",
        "output_dir": str(out),
        "acceptance_criteria_field": "customfield_1",
        "labels": {"draft": "UAC_Draft", "approved": "UAC_Approved", "posted": "QEVision_UAC_DONE", "rework": "UAC_Rework"},
        "copilot": {"command": "copilot", "add_dirs": ["/repos/a"], "allow_all_tools": True,
                    "deny_tools": ["corp-jira(update_jira_issue)"], "timeout_minutes": 1},
    }


def fake_copilot(write_files: bool, returncode: int = 0, decisions: str = "", doc_research=DOC_RESEARCH,
                 transcript: str = "task agent_type=uac-doc-researcher -> result"):
    def run(cmd, **kwargs):
        prompt = cmd[cmd.index("-p") + 1]
        if write_files:
            uac_path = Path(prompt.split("1. ", 1)[1].split(": only", 1)[0].strip())
            uac_path.write_text(UAC, encoding="utf-8")
            (uac_path.parent / common.PLAN_FILE).write_text("plan", encoding="utf-8")
            if decisions:
                (uac_path.parent / common.DECISIONS_FILE).write_text(decisions, encoding="utf-8")
            if doc_research is not None:
                (uac_path.parent / common.DOC_RESEARCH_FILE).write_text(json.dumps(doc_research), encoding="utf-8")
            share = next(a.split("=", 1)[1] for a in cmd if a.startswith("--share="))
            Path(share).write_text(prompt + chr(10) + transcript, encoding="utf-8")
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

    def test_config_ticket_list_overrides_jql(self) -> None:
        config = dict(self.config, tickets=["PROJ-7", "PROJ-8"])
        jira = FakeJira()
        seen = []
        with mock.patch.object(runner, "health", return_value=[]), \
                mock.patch.object(runner.common, "load_config", return_value=config), \
                mock.patch.object(runner.common.JiraClient, "from_env", return_value=jira), \
                mock.patch.object(runner, "process_ticket", side_effect=lambda k, *a: seen.append(k) or "READY"):
            runner.main(["--config", "unused.json", "--env-file", str(self.out / "missing.env")])
        run_logger = logging.getLogger("uac-runner")
        for handler in list(run_logger.handlers):
            handler.close()
            run_logger.removeHandler(handler)
        self.assertEqual(seen, ["PROJ-7", "PROJ-8"])
        self.assertFalse(any(c[0] == "search" for c in jira.calls))

    def test_jql_search_is_capped_by_max_tickets(self) -> None:
        config = dict(self.config, max_tickets=10)
        jira = FakeJira()
        with mock.patch.object(runner, "health", return_value=[]),                 mock.patch.object(runner.common, "load_config", return_value=config),                 mock.patch.object(runner.common.JiraClient, "from_env", return_value=jira),                 mock.patch.object(runner, "process_ticket", return_value="READY"):
            runner.main(["--config", "unused.json", "--env-file", str(self.out / "missing.env")])
        run_logger = logging.getLogger("uac-runner")
        for handler in list(run_logger.handlers):
            handler.close()
            run_logger.removeHandler(handler)
        self.assertIn(("search", config["jql"], 10), jira.calls)

    def test_ticket_without_doc_researcher_result_is_not_posted(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, doc_research=None)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        self.assertEqual(jira.calls, [])
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any("Doc Researcher did not run" in p for p in problems))

    def test_doc_researcher_must_appear_in_transcript_beyond_the_prompt(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, transcript="done without research")), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        self.assertEqual(jira.calls, [])
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any("transcript shows no uac-doc-researcher run" in p for p in problems))

    def test_doc_research_result_is_checked(self) -> None:
        ticket = self.out / "PROJ-3"
        ticket.mkdir()
        (ticket / "copilot-transcript.md").write_text("uac-doc-researcher ran", encoding="utf-8")
        cases = [
            ({"status": "FAILED"}, "expected one of"),
            ({"status": "ANSWER_FOUND", "findings": []}, "no findings"),
            ({"status": "NOT_FOUND", "limitations": []}, "without limitations"),
            ({"status": "PARTIAL", "findings": [{"claim": "x", "source_refs": ["doc:a"]}]}, "provenance locator"),
        ]
        for result, expected in cases:
            (ticket / common.DOC_RESEARCH_FILE).write_text(json.dumps(result), encoding="utf-8")
            self.assertTrue(any(expected in p for p in runner.doc_research_problems(ticket, "")), expected)
        (ticket / common.DOC_RESEARCH_FILE).write_text(
            json.dumps({"status": "NOT_FOUND", "limitations": ["searched Experience League Workfront pages"]}),
            encoding="utf-8")
        self.assertEqual(runner.doc_research_problems(ticket, ""), [])

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
        self.assertIn(("labels", "PROJ-1", ["QEVision_UAC_DONE"], ["UAC_Draft"]), jira.calls)

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
        self.assertIn('labels != "QEVision_UAC_DONE"', jql)


class DecisionRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.config["decision_comment"] = {"enabled": True, "mention": ["assignee"], "cc": ["qa.lead"]}
        self.log = logging.getLogger("test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def draft(self, decisions: str = DECISIONS) -> FakeJira:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, decisions=decisions)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "DRAFT_POSTED")
        return jira

    def test_draft_shows_the_decision_request_for_qe_review(self) -> None:
        jira = self.draft()
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertIn("*Decision request*", comment)
        self.assertIn("tagging the assignee, [~qa.lead]", comment)
        self.assertIn("# Is a button enough?", comment)
        self.assertIn("\\[Home page\\]", comment)
        self.assertNotIn(("people", "PROJ-1"), jira.calls, "nobody is tagged before approval")

    def test_tbd_without_decisions_file_warns_and_sends_nothing(self) -> None:
        jira = self.draft(decisions="")
        status = common.read_status(self.out / "PROJ-1")
        self.assertTrue(any("DECISIONS.md was not written" in w for w in status["warnings"]))
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertNotIn("Decision request", comment)

    def test_decisions_missing_a_section_are_not_sent(self) -> None:
        self.draft(decisions="### Decision needed\n1. Is a button enough?\n")
        status = common.read_status(self.out / "PROJ-1")
        self.assertTrue(any("missing section" in w for w in status["warnings"]))
        self.assertFalse((self.out / "PROJ-1" / common.DECISION_BODY_FILE).exists())

    def test_poster_sends_decision_request_once_with_mentions(self) -> None:
        self.draft()
        jira = FakeJira()
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "POSTED")
        comments = [c[2] for c in jira.calls if c[0] == "comment"]
        request = [c for c in comments if "product decisions are still open" in c]
        self.assertEqual(len(request), 1)
        self.assertTrue(request[0].startswith("[~dev.lead] [~qa.lead] "))
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(poster.post_decision_request("PROJ-1", self.config, jira, self.log,
                                                      self.out / "PROJ-1", status), "ALREADY_POSTED")

    def test_poster_skips_changed_decisions_and_disabled_setting(self) -> None:
        self.draft()
        ticket = self.out / "PROJ-1"
        (ticket / common.DECISIONS_FILE).write_text(DECISIONS + "- edited later\n", encoding="utf-8")
        jira = FakeJira()
        self.assertEqual(poster.post_ticket("PROJ-1", self.config, jira, self.log, overwrite=False), "POSTED")
        self.assertFalse(any("product decisions are still open" in c[2] for c in jira.calls if c[0] == "comment"))
        disabled = dict(self.config, decision_comment={"enabled": False})
        self.assertEqual(poster.post_decision_request("PROJ-1", disabled, jira, self.log, ticket,
                                                      common.read_status(ticket)), "NONE")


if __name__ == "__main__":
    unittest.main()
