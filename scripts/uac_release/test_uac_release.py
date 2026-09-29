"""Offline tests for the UAC release automation (fake Jira, stubbed Copilot CLI)."""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
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


SOURCE = {
    "description": "*Requirement*\nThe report must open from the Map console.\n* An empty report should show a message.\n!shot.png!",
    "comments": [
        {"id": "7", "author": "support.eng", "body": "Please also check that the export button works. [~dev.lead]"},
        {"id": "8", "author": "uac.bot", "body": "Draft UAC ready for QE review with four criteria."},
    ],
    "attachments": [{"filename": "shot.png", "author": "support.eng"},
                    {"filename": "PROJ-1-test-plan.md", "author": "uac.bot"}],
}
COVERAGE = [
    {"source": "description", "text": "The report must open from the Map console.", "disposition": "AC", "ac": 1},
    {"source": "description", "text": "An empty report should show a message.", "disposition": "TBD", "ac": 2},
    {"source": "comment:7", "text": "Please also check that the export button works.", "disposition": "OUT_OF_SCOPE",
     "reason": "export is a separate feature with its own ticket"},
    {"source": "attachment:shot.png", "text": "screenshot of the report", "disposition": "AC", "ac": 1,
     "surfaces": ["Map console"]},
]

SURFACES = [
    {"surface": "Map console", "evidence": ["https://experienceleague.adobe.com/report", "src/views/report_panel.json:12"],
     "authority": "TICKET", "disposition": "AC", "ac": 1},
    {"surface": "Report dialog", "evidence": ["src/controllers/report_dialog.ts:40"], "authority": "CODE_REUSE",
     "disposition": "TBD", "ac": 2},
    {"surface": "Email notification", "evidence": ["https://experienceleague.adobe.com/notify"],
     "authority": "DOCUMENTATION", "disposition": "OUT_OF_SCOPE", "reason": "the email is sent by another product"},
]


class FakeJira:
    def __init__(self, field_value: str = "", rendered_ok: bool = True, source=None) -> None:
        self.field_value = field_value
        self.rendered_ok = rendered_ok
        self.source = SOURCE if source is None else source
        self.calls: list[tuple] = []

    def myself(self):
        return {"name": "uac.bot"}

    def get_source(self, key):
        if isinstance(self.source, Exception):
            raise self.source
        return self.source

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
                 transcript: str = "task agent_type=uac-doc-researcher -> result", coverage=COVERAGE,
                 surfaces=SURFACES):
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
            if coverage is not None:
                (uac_path.parent / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
            if surfaces is not None:
                (uac_path.parent / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(surfaces), encoding="utf-8")
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

    def test_ticket_without_source_coverage_is_not_posted(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, coverage=None)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        self.assertEqual(jira.calls, [])
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any("was not mapped to the UAC" in p for p in problems))

    def test_unreadable_jira_source_fails_closed(self) -> None:
        jira = FakeJira(source=RuntimeError("HTTP 503"))
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=True), "FAILED")
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any("could not read the Jira ticket" in p for p in problems))

    def test_source_clauses_skip_markup_mentions_and_own_comments(self) -> None:
        clauses = runner.source_clauses(SOURCE, own_name="uac.bot")
        self.assertEqual(clauses, [
            ("description", "the report must open from the map console"),
            ("description", "an empty report should show a message"),
            ("comment:7", "please also check that the export button works"),
        ])

    def test_source_coverage_problems(self) -> None:
        ticket = self.out / "PROJ-4"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")

        def problems(entries):
            (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(entries), encoding="utf-8")
            return runner.source_coverage_problems(ticket, SOURCE, own_name="uac.bot")

        self.assertEqual(problems(COVERAGE), [])
        found = problems(COVERAGE[1:])
        self.assertTrue(any("1 Jira sentence(s) are not mapped" in p and "map console" in p for p in found))
        found = problems(COVERAGE[:3])
        self.assertIn("attachment shot.png is not mapped to the UAC", found)
        wrong_tbd = [dict(COVERAGE[0], disposition="TBD")] + COVERAGE[1:]
        self.assertTrue(any("has no TBD line" in p for p in problems(wrong_tbd)))
        missing_ac = [dict(COVERAGE[0], ac=7)] + COVERAGE[1:]
        self.assertTrue(any("does not exist in UAC.md" in p for p in problems(missing_ac)))
        empty_reason = COVERAGE[:2] + [dict(COVERAGE[2], reason="n/a")] + COVERAGE[3:]
        self.assertTrue(any("needs a concrete reason" in p for p in problems(empty_reason)))
        self.assertTrue(any("not one of" in p for p in problems([dict(COVERAGE[0], disposition="MAYBE")] + COVERAGE[1:])))

    def test_ticket_without_surface_inventory_is_not_posted(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, surfaces=None)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        self.assertEqual(jira.calls, [])
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any("places the feature appears were not listed" in p for p in problems))

    def test_surface_inventory_problems(self) -> None:
        ticket = self.out / "PROJ-5"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")

        def problems(entries):
            (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(entries), encoding="utf-8")
            return runner.surface_inventory_problems(ticket)

        self.assertEqual(problems(SURFACES), [])
        self.assertTrue(any("non-empty JSON list" in p for p in problems([])))
        unnamed = [dict(SURFACES[0], surface="Review UI")] + SURFACES[1:]
        self.assertTrue(any("does not name this surface" in p for p in problems(unnamed)))
        self.assertTrue(any("cites no code reference" in p
                            for p in problems([dict(s, evidence=[e for e in s["evidence"] if e.startswith("https")]
                                                    or ["https://experienceleague.adobe.com/a"]) for s in SURFACES])))
        self.assertTrue(any("cites no documentation page" in p
                            for p in problems([dict(s, evidence=["src/a.ts:1"]) for s in SURFACES])))
        self.assertTrue(any("must be a documentation URL" in p
                            for p in problems([dict(SURFACES[0], evidence=["looked at the code"])] + SURFACES[1:])))
        self.assertTrue(any("has no TBD line" in p for p in problems([dict(SURFACES[1], ac=1)] + SURFACES[:1])))
        self.assertTrue(any("needs a concrete reason" in p
                            for p in problems(SURFACES[:2] + [dict(SURFACES[2], reason="n/a")])))

    def test_discovered_surface_may_only_get_a_regression_ac(self) -> None:
        ticket = self.out / "PROJ-6"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")

        def problems(entries):
            (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(entries), encoding="utf-8")
            return runner.surface_inventory_problems(ticket)

        invented = [dict(SURFACES[0], authority="CODE_REUSE")] + SURFACES[1:]
        self.assertTrue(any("may only check that it still works" in p for p in problems(invented)))
        (ticket / common.UAC_FILE).write_text(
            UAC.replace("Verify that the report opens from the Map console.",
                        "Verify that the report still opens from the Map console as before."), encoding="utf-8")
        self.assertEqual(problems(invented), [])
        self.assertTrue(any("authority None is not one of" in p
                            for p in problems([{k: v for k, v in SURFACES[0].items() if k != "authority"}] + SURFACES[1:])))

    def test_attachment_screens_must_be_in_the_surface_inventory(self) -> None:
        ticket = self.out / "PROJ-7"
        ticket.mkdir()
        (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(SURFACES), encoding="utf-8")

        def problems(coverage):
            (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
            return runner.attachment_surface_problems(ticket, SOURCE, own_name="uac.bot")

        self.assertEqual(problems(COVERAGE), [])
        unnamed = COVERAGE[:3] + [{k: v for k, v in COVERAGE[3].items() if k != "surfaces"}]
        self.assertTrue(any("list the product screens it shows" in p for p in problems(unnamed)))
        unknown = COVERAGE[:3] + [dict(COVERAGE[3], surfaces=["Map console", "Your tasks widget"])]
        self.assertIn("attachment shot.png shows Your tasks widget, which is not in the surface inventory", problems(unknown))

    def _ticket_with(self, name, uac, coverage=COVERAGE, surfaces=SURFACES):
        ticket = self.out / name
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(uac, encoding="utf-8")
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
        (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(surfaces), encoding="utf-8")
        return ticket

    def test_hotfix_ticket_needs_a_scope_file(self) -> None:
        ticket = self.out / "PROJ-1"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        hotfix = dict(SOURCE, summary="[On-prem]HOTFIX : Add PKCE")
        problems = runner.hotfix_scope_problems(ticket, hotfix)
        self.assertTrue(any(common.HOTFIX_SCOPE_FILE in p for p in problems))
        self.assertEqual(runner.hotfix_scope_problems(ticket, SOURCE), [], "ordinary tickets are not checked")

    def test_hotfix_scope_problems_come_from_the_skill_check(self) -> None:
        ticket = self.out / "PROJ-1"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        (ticket / common.HOTFIX_SCOPE_FILE).write_text(json.dumps({"acs": []}), encoding="utf-8")
        hotfix = dict(SOURCE, description="Backport to release-hotfix-5.2.2")
        scope_check = common.import_skill_module("hotfix_scope_check")
        with mock.patch.object(scope_check, "check", return_value=["Acceptance Criteria 02: not a hotfix regression"]):
            problems = runner.hotfix_scope_problems(ticket, hotfix)
        self.assertEqual(problems, ["hotfix scope: Acceptance Criteria 02: not a hotfix regression"])

    def test_orphan_notes_go_to_the_draft_and_do_not_fail_the_ticket(self) -> None:
        jira = FakeJira()
        note = "Acceptance Criteria 2 is not tied to any ticket sentence"
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]), \
                mock.patch.object(runner, "orphan_ac_problems", return_value=[note]):
            result = runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False)
        self.assertEqual(result, "DRAFT_POSTED")
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertIn("*Please check before approving*", comment)
        self.assertIn(note, comment)
        self.assertEqual(common.read_status(self.out / "PROJ-1")["review_notes"], [note])

    def test_orphan_acceptance_criterion_fails(self) -> None:
        self.assertEqual(runner.orphan_ac_problems(self._ticket_with("PROJ-8", UAC)), [])
        extra = UAC + ("- Acceptance Criteria 03: Verify that an export with no rows shows an empty file.\n"
                       "  **Source:** Ticket description.\n")
        found = runner.orphan_ac_problems(self._ticket_with("PROJ-9", extra))
        self.assertEqual(len(found), 1)
        self.assertIn("Acceptance Criteria 3 is not tied to any ticket sentence", found[0])

    def test_regression_ac_on_a_discovered_surface_is_not_an_orphan(self) -> None:
        extra = UAC + ("- Acceptance Criteria 03: Verify that the Report dialog still opens as before.\n"
                       "  **Source:** src/controllers/report_dialog.ts line 40.\n")
        surfaces = SURFACES + [{"surface": "Report dialog", "evidence": ["src/controllers/report_dialog.ts:40"],
                                "authority": "CODE_REUSE", "disposition": "AC", "ac": 3}]
        self.assertEqual(runner.orphan_ac_problems(self._ticket_with("PROJ-10", extra, surfaces=surfaces)), [])

    def test_one_ticket_sentence_can_drive_several_criteria(self) -> None:
        extra = UAC + ("- Acceptance Criteria 03: Verify that an export with no rows shows an empty file.\n"
                       "  **Source:** Ticket description.\n")
        coverage = [dict(COVERAGE[0], ac=[1, 3])] + COVERAGE[1:]
        ticket = self._ticket_with("PROJ-14", extra, coverage=coverage)
        self.assertEqual(runner.orphan_ac_problems(ticket), [])
        self.assertEqual(runner.source_coverage_problems(ticket, SOURCE, own_name="uac.bot"), [])

    def test_qe_reasoning_only_needs_a_tbd(self) -> None:
        uac = UAC.replace("  **Source:** Ticket description; ReportServlet.java line 10.\n",
                          "  **Source:** QE reasoning: nothing in the ticket defines this.\n")
        found = runner.orphan_ac_problems(self._ticket_with("PROJ-11", uac))
        self.assertTrue(any("rests only on QE reasoning" in p for p in found))
        with_tbd = uac.replace("- Acceptance Criteria 02:", "  **TBD:** Is this in scope?\n- Acceptance Criteria 02:")
        self.assertFalse(any("QE reasoning" in p for p in runner.orphan_ac_problems(self._ticket_with("PROJ-12", with_tbd))))

    def test_check_dir_runs_every_check_on_an_existing_folder(self) -> None:
        ticket = self._ticket_with("PROJ-13", UAC)
        (ticket / common.JIRA_SOURCE_FILE).write_text(json.dumps(SOURCE), encoding="utf-8")
        ok = subprocess.CompletedProcess([], 0, "PASS", "")
        with mock.patch.object(runner.subprocess, "run", return_value=ok):
            self.assertEqual(runner.main(["--check-dir", str(ticket), "--own-name", "uac.bot"]), 1)
            (ticket / common.PLAN_FILE).write_text("plan", encoding="utf-8")
            (ticket / common.DOC_RESEARCH_FILE).write_text(json.dumps(DOC_RESEARCH), encoding="utf-8")
            (ticket / "copilot-transcript.md").write_text("uac-doc-researcher ran", encoding="utf-8")
            self.assertEqual(runner.main(["--check-dir", str(ticket), "--own-name", "uac.bot"]), 0)

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


def close_logger(name: str) -> None:
    run_logger = logging.getLogger(name)
    for handler in list(run_logger.handlers):
        handler.close()
        run_logger.removeHandler(handler)


class RunLoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = dict(make_config(self.out), tickets=["PROJ-1", "PROJ-2"],
                           alerts={"ticket": "OPS-1", "mention": ["qe.lead"]})
        self.log = logging.getLogger("test")
        self.env = ["--env-file", str(self.out / "missing.env")]

    def tearDown(self) -> None:
        close_logger("uac-runner")
        close_logger("uac-poster")
        self.tmp.cleanup()

    def run_runner(self, jira, process=None, health=(), extra=()):
        with mock.patch.object(runner, "health", return_value=list(health)), \
                mock.patch.object(runner.common, "load_config", return_value=self.config), \
                mock.patch.object(runner.common.JiraClient, "from_env", return_value=jira), \
                mock.patch.object(runner, "process_ticket", side_effect=process or (lambda k, *a: "READY")):
            return runner.main(["--config", "unused.json", *self.env, *extra])

    def runs(self) -> list[dict]:
        lines = (self.out / common.RUNS_FILE).read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines]

    def alert_comments(self, jira) -> list[str]:
        return [c[2] for c in jira.calls if c[0] == "comment" and c[1] == "OPS-1"]

    def test_one_ticket_crashing_does_not_stop_the_others(self) -> None:
        seen = []

        def process(key, *args):
            seen.append(key)
            if key == "PROJ-1":
                raise ConnectionError("Jira returned 500")
            return "DRAFT_POSTED"

        jira = FakeJira()
        self.assertEqual(self.run_runner(jira, process), 1)
        self.assertEqual(seen, ["PROJ-1", "PROJ-2"])
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "ERROR")
        self.assertIn("Jira returned 500", status["last_error"])
        record = self.runs()[-1]
        self.assertEqual(record["tickets"], {"PROJ-1": "ERROR", "PROJ-2": "DRAFT_POSTED"})
        self.assertEqual(record["exit_code"], 1)
        log_text = "".join(p.read_text(encoding="utf-8") for p in (self.out / "logs").glob("uac-runner-*.log"))
        self.assertIn("Traceback", log_text, "the traceback goes to the daily log, not only cron.log")
        [alert] = self.alert_comments(jira)
        self.assertIn("[~qe.lead]", alert)
        self.assertIn("PROJ-1: unexpected error - ConnectionError: Jira returned 500", alert)

    def test_error_after_the_draft_keeps_the_posted_state(self) -> None:
        common.write_status(self.out / "PROJ-1", {"state": "DRAFT_POSTED"})
        results, errors = common.run_each(["PROJ-1"], lambda k: 1 / 0, self.log, self.out)
        self.assertEqual(results, {"PROJ-1": "ERROR"})
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "DRAFT_POSTED")
        self.assertIn("ZeroDivisionError", status["last_error"])

    def test_failed_ticket_is_alerted_with_its_first_problem(self) -> None:
        def process(key, *args):
            if key == "PROJ-2":
                common.write_status(self.out / key, {"state": "FAILED", "problems": ["no doc researcher run", "x"]})
                return "FAILED"
            return "DRAFT_POSTED"

        jira = FakeJira()
        self.run_runner(jira, process)
        [alert] = self.alert_comments(jira)
        self.assertIn("PROJ-2: draft not posted - no doc researcher run (and 1 more)", alert)
        self.assertNotIn("PROJ-1", alert)

    def test_health_failure_is_alerted_and_no_ticket_runs(self) -> None:
        jira = FakeJira()
        process = mock.Mock(return_value="READY")
        self.assertEqual(self.run_runner(jira, process, health=["Copilot CLI not found on PATH"]), 2)
        process.assert_not_called()
        [alert] = self.alert_comments(jira)
        self.assertIn("Health check failed, no tickets processed: Copilot CLI not found on PATH", alert)
        self.assertEqual(self.runs()[-1]["health_problems"], ["Copilot CLI not found on PATH"])

    def test_a_run_that_stops_is_recorded_and_alerted(self) -> None:
        self.config.pop("tickets")
        jira = FakeJira()
        jira.search_keys = mock.Mock(side_effect=TimeoutError("search timed out"))
        self.assertEqual(self.run_runner(jira), 3)
        [alert] = self.alert_comments(jira)
        self.assertIn("The run stopped before finishing: TimeoutError: search timed out", alert)
        self.assertEqual(self.runs()[-1]["exit_code"], 3)

    def test_clean_run_is_recorded_without_an_alert(self) -> None:
        jira = FakeJira()
        self.assertEqual(self.run_runner(jira), 0)
        self.assertEqual(self.alert_comments(jira), [])
        record = self.runs()[-1]
        self.assertEqual(record["tool"], "uac-runner")
        self.assertEqual(record["tickets"], {"PROJ-1": "READY", "PROJ-2": "READY"})
        self.assertTrue(record["run_id"])

    def test_dry_run_never_sends_the_alert(self) -> None:
        jira = FakeJira()
        self.run_runner(jira, health=["Jira: 401"], extra=["--dry-run"])
        self.assertEqual(self.alert_comments(jira), [])
        self.assertEqual(self.runs()[-1]["alerts"], ["Health check failed, no tickets processed: Jira: 401"])

    def test_same_alert_is_not_repeated_until_the_problem_clears(self) -> None:
        jira = FakeJira()
        send = lambda lines: common.send_alert(self.config, jira, self.log, "uac-poster", "r1", lines)  # noqa: E731
        self.assertEqual(send(["PROJ-1: approved but not posted"]), "POSTED")
        self.assertEqual(send(["PROJ-1: approved but not posted"]), "SUPPRESSED")
        self.assertEqual(send(["PROJ-1: approved but not posted", "PROJ-2: x"]), "POSTED")
        self.assertEqual(send([]), "NONE")
        self.assertEqual(send(["PROJ-1: approved but not posted"]), "POSTED")
        self.assertEqual(len(self.alert_comments(jira)), 3)

    def test_alert_without_a_ticket_is_only_logged(self) -> None:
        jira = FakeJira()
        config = dict(self.config, alerts={})
        self.assertEqual(common.send_alert(config, jira, self.log, "uac-runner", "r1", ["x"]), "NOT_CONFIGURED")
        self.assertEqual(jira.calls, [])

    def test_alert_that_jira_rejects_does_not_crash(self) -> None:
        jira = FakeJira()
        jira.add_comment = mock.Mock(side_effect=ConnectionError("down"))
        self.assertEqual(common.send_alert(self.config, jira, self.log, "uac-runner", "r1", ["x"]), "FAILED")

    def test_rerun_keeps_the_previous_attempt(self) -> None:
        ticket = self.out / "PROJ-1"
        common.write_status(ticket, {"state": "FAILED", "problems": ["old"]})
        (ticket / "copilot-transcript.md").write_text("first run", encoding="utf-8")
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            runner.process_ticket("PROJ-1", self.config, FakeJira(), self.log, dry_run=True)
        [attempt] = list((ticket / common.ATTEMPTS_DIR).iterdir())
        self.assertEqual((attempt / "copilot-transcript.md").read_text(encoding="utf-8"), "first run")
        self.assertEqual(json.loads((attempt / common.STATUS_FILE).read_text(encoding="utf-8"))["problems"], ["old"])
        self.assertEqual(common.read_status(ticket)["state"], "READY")

    def test_only_the_newest_attempts_are_kept(self) -> None:
        ticket = self.out / "PROJ-1"
        for n in range(4):
            (ticket / common.ATTEMPTS_DIR / f"2026010{n}-000000").mkdir(parents=True)
        common.write_status(ticket, {"state": "FAILED"})
        common.archive_attempt(ticket, keep=3)
        kept = sorted(p.name for p in (ticket / common.ATTEMPTS_DIR).iterdir())
        self.assertEqual(len(kept), 3)
        self.assertNotIn("20260100-000000", kept)
        self.assertNotIn("20260101-000000", kept)

    def test_old_log_files_are_deleted(self) -> None:
        logs = self.out / "logs"
        logs.mkdir()
        old, new = logs / "uac-runner-20250101.log", logs / "uac-runner-20260101.log"
        old.write_text("x", encoding="utf-8")
        new.write_text("x", encoding="utf-8")
        long_ago = time.time() - 40 * 86400
        os.utime(old, (long_ago, long_ago))
        self.assertEqual(common.prune_logs(logs, 30), [old.name])
        self.assertTrue(new.exists())
        self.assertEqual(common.prune_logs(logs, 0), [])

    def test_poster_alerts_on_tickets_it_could_not_post(self) -> None:
        jira = FakeJira()
        jira.search_keys = lambda jql, max_results=100: ["PROJ-1", "PROJ-2"]
        results = {"PROJ-1": "FIELD_NOT_EMPTY", "PROJ-2": "POSTED"}
        with mock.patch.object(poster.common, "load_config", return_value=self.config), \
                mock.patch.object(poster.common.JiraClient, "from_env", return_value=jira), \
                mock.patch.object(poster, "post_ticket", side_effect=lambda k, *a: results[k]):
            self.assertEqual(poster.main(["--config", "unused.json", *self.env]), 1)
        [alert] = self.alert_comments(jira)
        self.assertIn("PROJ-1: approved but not posted - the Acceptance Criteria field already has other text", alert)
        self.assertEqual(self.runs()[-1]["tool"], "uac-poster")


if __name__ == "__main__":
    unittest.main()
