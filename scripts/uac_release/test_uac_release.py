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
import uac_learning_harvester as harvester  # noqa: E402
import uac_staleness_watch as staleness  # noqa: E402
import uac_release_runner as runner  # noqa: E402
import release_dashboard as dashboard  # noqa: E402
import linked_docs  # noqa: E402
import record_manual_rewrite  # noqa: E402

UAC = (
    "Note: The root cause and the fix are not confirmed yet. These criteria cover what the customer reported and "
    "will be checked again when the fix is known.\n\n"
    "- Acceptance Criteria 01: Verify that the report opens from the Map console.\n"
    "  **Source:** Ticket description; ReportServlet.java line 10.\n"
    "- Acceptance Criteria 02: Verify that an empty report shows a message.\n"
    "  **Source:** Ticket description.\n"
    "  **TBD:** Which message text should be shown?\n"
    "- Acceptance Criteria 03: The report still opens from the Map dashboard as before.\n"
    "  **Source:** Experience League report page.\n"
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
     "surfaces": ["Map console"],
     "facts": [{"fact": "the report opens from the Map console", "disposition": "AC", "ac": 1}]},
]

SURFACES = [
    {"surface": "Map console", "evidence": ["https://experienceleague.adobe.com/report", "src/views/report_panel.json:12"],
     "authority": "TICKET", "disposition": "AC", "ac": 1},
    {"surface": "Report dialog", "evidence": ["src/controllers/report_dialog.ts:40"], "authority": "CODE_REUSE",
     "disposition": "TBD", "ac": 2},
    {"surface": "Email notification", "evidence": ["https://experienceleague.adobe.com/notify"],
     "authority": "DOCUMENTATION", "disposition": "OUT_OF_SCOPE", "reason": "the email is sent by another product"},
    {"surface": "Map dashboard", "evidence": ["https://experienceleague.adobe.com/report"],
     "authority": "DOCUMENTATION", "disposition": "AC", "ac": 3},
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


EVIDENCE = {
    "preflight": {"product_rag": {"status": "available", "route": "backend"},
                  "jira_history": {"status": "available", "route": "backend"},
                  "live_jira": {"status": "available", "route": "REST"},
                  "clones": {"status": "available", "route": "local clones"}},
    "rag_probes": [{"question": f"question {n}", "result": "ok", "summary": "answer"} for n in range(3)],
    "history_attempts": [{"source": "search_jira_history", "query": f"query {n}", "result": "empty", "count": 0}
                         for n in range(2)],
    "doc_findings": [{"finding": 1, "disposition": "SET_ASIDE",
                      "reason": "the Home page task list is not the screen this ticket changes"}],
    "similar_uacs": {"status": "none_found", "queries": ["component = Publishing AND text ~ report"], "uacs": []},
    "scenario": {"customer_steps": ["The report must open from the Map console."], "acs": [
        {"ac": 1, "scenario": "CUSTOMER", "step": "The report must open from the Map console."},
        {"ac": 2, "scenario": "CUSTOMER", "step": "The report must open from the Map console."},
        {"ac": 3, "scenario": "ADJACENT"}]},
    "fix_basis": {"status": "UNCONFIRMED"},
    "pre_existing_items": {"disposition": "NOT_APPLICABLE", "reason": "the report screen stores nothing made before the change"},
    "action_variants": {"entry_points": [{"name": "the only route", "disposition": "NOT_APPLICABLE",
                            "reason": "the change has a single route with no alternative path"}],
        "config_switches": [], "config_switches_reason": "no setting changes what this screen shows",
        "mechanism": {"general_ask": False, "reason": "the ticket asks only about this one screen",
                      "reverse_action": {"name": "undo", "disposition": "NOT_APPLICABLE",
                                         "reason": "the screen only displays data and has no reverse action"},
                      "item_origin": {"name": "older items", "disposition": "NOT_APPLICABLE",
                                      "reason": "every item is shown the same way whatever its history"},
                      "value_shapes": {"name": "values", "disposition": "NOT_APPLICABLE",
                                       "reason": "the screen shows fixed labels and reads no user value"}}},
    "scope_boundaries": [], "scope_boundaries_reason": "nobody decided a version, type or path that this change leaves out",
    "shared_consumers": {"consumers": [], "reason": "the change reads nothing that another screen also reads"},
}


def make_config(out: Path) -> dict:
    return {
        "jql": "project = PROJ",
        "output_dir": str(out),
        "acceptance_criteria_field": "customfield_1",
        "labels": {"posted": "QEVision_UAC_DONE"},
        "copilot": {"command": "copilot", "add_dirs": ["/repos/a"], "allow_all_tools": True,
                    "deny_tools": ["corp-jira(update_jira_issue)"], "timeout_minutes": 1},
    }


def fake_copilot(write_files: bool, returncode: int = 0, decisions: str = "", doc_research=DOC_RESEARCH,
                 transcript: str = ("task agent_type=uac-doc-researcher -> result\n"
                                    "task agent_type=uac-code-researcher -> result\n"
                                    "task agent_type=uac-attachment-researcher -> result"), coverage=COVERAGE,
                 surfaces=SURFACES, evidence=EVIDENCE):
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
            if evidence is not None:
                (uac_path.parent / common.EVIDENCE_FILE).write_text(json.dumps(evidence), encoding="utf-8")
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

    def test_command_adds_the_real_interpreter_folder(self) -> None:
        # backend/venv/bin/python links to the system interpreter; Copilot checks the resolved path, so
        # without its folder the non-interactive session is denied the canonical runtime.
        with mock.patch.object(runner, "interpreter_dir", return_value="/usr/bin"):
            cmd = runner.copilot_command(self.config, "hello", self.out / "t.md", "/repo/backend/venv/bin/python")
        self.assertIn("--add-dir=/usr/bin", cmd)
        self.assertEqual(sum(1 for c in cmd if c == "--add-dir=/usr/bin"), 1)
        with mock.patch.object(runner, "interpreter_dir", return_value=str(Path("/repos/a/venv/bin"))):
            cmd = runner.copilot_command(self.config, "hello", self.out / "t.md", "/repos/a/venv/bin/python")
        self.assertFalse(any("venv" in c for c in cmd if c.startswith("--add-dir=")), "already inside an add_dir")
        self.assertEqual(runner.copilot_command(self.config, "hello", self.out / "t.md"),
                         runner.copilot_command(self.config, "hello", self.out / "t.md", ""))

    def _run(self, jira: FakeJira) -> str:
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            return runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False)

    def test_passing_ticket_writes_the_field_and_adds_the_done_label(self) -> None:
        jira = FakeJira()
        self.assertEqual(self._run(jira), "POSTED")
        kinds = [c[0] for c in jira.calls]
        self.assertEqual(kinds[:4], ["attach", "set_field", "comment", "labels"])
        field_body = (self.out / "PROJ-1" / "field-body.txt").read_text(encoding="utf-8")
        self.assertTrue(field_body.startswith("_Note: The root cause"))
        self.assertNotIn("ReportServlet", field_body, "code names never reach the field")
        self.assertIn("* Source: Ticket description.", field_body)
        self.assertNotIn("Suggested", field_body)
        self.assertIn("*Acceptance Criteria 03:* The report still opens from the Map dashboard as before.", field_body,
                      "a research check that matters is an Acceptance Criterion")
        self.assertIn("* Source: Experience League report page.", field_body)
        self.assertIn(("set_field", "PROJ-1", "customfield_1", field_body), jira.calls)
        self.assertIn(("labels", "PROJ-1", ["QEVision_UAC_DONE"], []), jira.calls)
        comment = jira.calls[2][2]
        self.assertEqual(comment, "*Full test plan:* [^PROJ-1-test-plan.md]", "the comment is only the test plan")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "POSTED", "the harvester learns from it")
        self.assertEqual(status["posted_sha256"], common.sha256_file(self.out / "PROJ-1" / "field-body.txt"))
        self.assertIn(common.text_key(field_body), common.posted_body_keys(self.out / "PROJ-1"),
                      "every posted text is remembered for the harvester")
        self.assertNotIn("suggested", status, "there are no suggested checks to record")
        self.assertNotIn("suggested_merged", status)
        self.assertEqual(status["uac_sha256"], common.sha256_file(self.out / "PROJ-1" / common.UAC_FILE))
        self.assertEqual(status["source_code_refs_removed"], ["ReportServlet.java line 10."])

    def test_written_comment_is_only_the_full_test_plan(self) -> None:
        self.assertEqual(runner.written_comment("PROJ-1-test-plan.md"), "*Full test plan:* [^PROJ-1-test-plan.md]")

    def test_prompt_no_longer_asks_for_suggested_checks(self) -> None:
        self.assertNotIn("Suggested checks (QE decide)", runner.PROMPT)
        self.assertNotIn("SUGGESTED", runner.PROMPT)
        self.assertIn("still works as before", runner.PROMPT)

    def test_a_uac_with_a_suggested_section_is_refused(self) -> None:
        check = common.import_skill_module("uac_completeness_check")
        legacy = UAC + "\nSuggested checks (QE decide):\n- Suggested check 01: D works.\n  **Source:** doc page\n"
        self.assertTrue(check.suggested_problems(legacy))
        self.assertEqual(check.suggested_problems(UAC), [])

    def test_runner_never_overwrites_a_filled_field(self) -> None:
        jira = FakeJira(field_value="Criteria written by a person")
        self.assertEqual(self._run(jira), "FIELD_KEPT")
        self.assertEqual([c[0] for c in jira.calls], [], "nothing is written to the ticket")
        self.assertEqual(common.read_status(self.out / "PROJ-1")["state"], "FIELD_KEPT")
        self.assertEqual(self._run(FakeJira()), "SKIPPED", "the next run does not write it again")


    def test_text_the_runner_wrote_before_is_replaced_not_kept(self) -> None:
        # A run wrote the field, then stopped before the comment and label; the next run finishes the post.
        earlier = "*Acceptance Criteria 01:* An earlier draft.\n* Source: Ticket description."
        (self.out / "PROJ-1").mkdir(exist_ok=True)
        common.remember_posted_body(self.out / "PROJ-1", earlier)
        jira = FakeJira(field_value=earlier.replace("\n", "\r\n"))
        self.assertEqual(self._run(jira), "POSTED")
        self.assertIn("set_field", [c[0] for c in jira.calls])
    def test_field_that_does_not_render_is_recorded_as_written_not_failed(self) -> None:
        jira = FakeJira(rendered_ok=False)
        self.assertEqual(self._run(jira), common.WRITTEN_UNRENDERED)
        kinds = [c[0] for c in jira.calls]
        self.assertIn("set_field", kinds, "the UAC is in the field")
        self.assertNotIn("labels", kinds, "no done label on a broken field")
        self.assertNotIn("comment", kinds)
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], common.WRITTEN_UNRENDERED)
        self.assertIn("did not render", status["problems"][0])
        self.assertEqual(self._run(FakeJira()), "SKIPPED", "the next run does not generate it again")

    def test_field_rendered_accepts_the_first_label_number_the_uac_used(self) -> None:
        self.assertTrue(runner.field_rendered("*Acceptance Criteria 1:* x", "<p><b>Acceptance Criteria 1:</b> x</p>"))
        self.assertTrue(runner.field_rendered("_Note: n_\n\n*Acceptance Criteria 01:* x",
                                              "<p><b>Acceptance Criteria 01:</b> x</p>"))
        self.assertFalse(runner.field_rendered("*Acceptance Criteria 1:* x", "<p>*Acceptance Criteria 1:* x</p>"))

    def test_uac_numbered_from_1_is_posted(self) -> None:
        jira = FakeJira()
        jira.get_field = lambda key, field, rendered=False: (
            "<p><b>Acceptance Criteria 1:</b> x</p>" if rendered else jira.field_value)
        unpadded = fake_copilot(True)

        def copilot(cmd, **kwargs):
            result = unpadded(cmd, **kwargs)
            uac = self.out / "PROJ-1" / common.UAC_FILE
            uac.write_text(uac.read_text(encoding="utf-8").replace("Criteria 01", "Criteria 1")
                           .replace("Criteria 02", "Criteria 2"), encoding="utf-8")
            return result
        with mock.patch.object(runner.subprocess, "run", copilot), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "POSTED")

    def test_cron_sets_a_path_that_finds_copilot(self) -> None:
        cron = (Path(runner.__file__).parent / "uac-release.cron").read_text(encoding="utf-8")
        self.assertRegex(cron, r"(?m)^PATH=.*/usr/local/bin", "cron's default PATH has no npm global bin")

    def test_runtime_fallback_uac_is_written_with_the_failed_gates_listed(self) -> None:
        base = fake_copilot(True)

        def copilot_with_fallback(cmd, **kwargs):
            done = base(cmd, **kwargs)
            prompt = cmd[cmd.index("-p") + 1]
            fallback = self.out / "PROJ-1" / common.RUNTIME_FALLBACK_FILE
            self.assertIn("Runtime fallback", prompt)
            self.assertIn(str(fallback), prompt, "the prompt names the fallback file")
            fallback.write_text(json.dumps({
                "canonical_status": "waiting_for_agent_research",
                "failed_gates": [{"gate": "BehavioralCompletenessGate", "reason": "research still pending"},
                                 {"gate": "FinalQEPlanRenderer", "reason": "no criteria to render"}]}),
                encoding="utf-8")
            return done

        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", copilot_with_fallback), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "POSTED")
        self.assertIn(("labels", "PROJ-1", ["QEVision_UAC_DONE"], []), jira.calls, "a fallback UAC is posted too")
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertNotIn("Runtime gates", comment, "the gates stay in status.json and the release page")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["runtime_fallback"], ["BehavioralCompletenessGate: research still pending",
                                                      "FinalQEPlanRenderer: no criteria to render"])

    def test_a_canonical_uac_has_no_fallback_section(self) -> None:
        jira = FakeJira()
        self.assertEqual(self._run(jira), "POSTED")
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertNotIn("Runtime gates not passed", comment)
        self.assertNotIn("runtime_fallback", common.read_status(self.out / "PROJ-1"))

    def test_runtime_fallback_record_is_read_defensively(self) -> None:
        ticket = self.out / "PROJ-9"
        ticket.mkdir()
        self.assertIsNone(runner.runtime_fallback_gates(ticket))
        (ticket / common.RUNTIME_FALLBACK_FILE).write_text("{not json", encoding="utf-8")
        self.assertEqual(runner.runtime_fallback_gates(ticket), ["the runtime fallback record is not valid JSON"])
        (ticket / common.RUNTIME_FALLBACK_FILE).write_text(json.dumps({"canonical_status": "blocked"}), encoding="utf-8")
        self.assertEqual(runner.runtime_fallback_gates(ticket), ["canonical runtime status: blocked"])

    def test_runtime_result_is_saved_for_every_run_and_summarized(self) -> None:
        env = runner.copilot_env(Path("/runs/PROJ-1"))
        self.assertEqual(Path(env["TEST_PLAN_RESULT_PATH"]), Path("/runs/PROJ-1") / common.RUNTIME_RESULT_FILE)
        ticket = self.out / "PROJ-8"
        ticket.mkdir()
        self.assertEqual(runner.runtime_result_summary(ticket), {"saved": False})
        path = ticket / common.RUNTIME_RESULT_FILE
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(runner.runtime_result_summary(ticket)["error"], "the saved runtime result is not valid JSON")
        path.write_text(json.dumps({"qe_review_package": {"canonical_result": {
            "status": "blocked", "postable": False,
            "uac_delivery": {"failures": ["no deliverable criteria"]},
            "gate_decisions": [
                {"gate": "AcceptancePromotionGate", "status": "PASSED", "failures": []},
                {"gate": "FinalQEPlanRenderer", "status": "FAILED",
                 "failures": ["P0 coverage d-1 has no human-facing acceptance projection."]},
                {"gate": "BehavioralCompletenessGate", "status": "BLOCKED", "failures": []}]}}}),
            encoding="utf-8")
        self.assertEqual(runner.runtime_result_summary(ticket), {
            "saved": True, "canonical_status": "blocked", "postable": False,
            "gate_failures": ["FinalQEPlanRenderer: P0 coverage d-1 has no human-facing acceptance projection.",
                              "BehavioralCompletenessGate: BLOCKED"],
            "delivery_failures": ["no deliverable criteria"]})

    def test_the_pipeline_cli_saves_its_result_only_when_asked(self) -> None:
        import importlib.util
        script = common.REPO_ROOT / "scripts" / "run_test_plan_pipeline.py"
        spec = importlib.util.spec_from_file_location("run_test_plan_pipeline_for_test", script)
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "PROJ-1" / common.RUNTIME_RESULT_FILE
            with mock.patch.dict(os.environ, {"TEST_PLAN_RESULT_PATH": str(target)}):
                cli._save_result({"jira_key": "PROJ-1", "score": {"overall": 3}})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["jira_key"], "PROJ-1")
            self.assertFalse(target.with_name(target.name + ".tmp").exists())
            other = Path(tmp) / "unset.json"
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("TEST_PLAN_RESULT_PATH", None)
                cli._save_result({"jira_key": "PROJ-2"})
            self.assertFalse(other.exists())

    def test_each_ticket_records_which_checks_fired(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=True)
        bad = dict(EVIDENCE, rag_probes=[])
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, evidence=bad)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-2", self.config, jira, self.log, dry_run=True), "FAILED")
        with mock.patch.object(runner.subprocess, "run", fake_copilot(False, returncode=1)):
            runner.process_ticket("PROJ-3", self.config, jira, self.log, dry_run=True)
        lines = (self.out / "logs" / runner.GATE_LOG_FILE).read_text(encoding="utf-8").splitlines()
        rows = [json.loads(line) for line in lines]
        self.assertEqual([r["key"] for r in rows], ["PROJ-1", "PROJ-2"], "no checks ran when Copilot failed")
        ok, failed = rows
        self.assertTrue(ok["passed"])
        self.assertEqual(ok["checks"]["evidence.rag_probes"], 0)
        self.assertIn("advisory.orphan_acs", ok["checks"])
        self.assertFalse(failed["passed"])
        self.assertEqual(failed["checks"]["evidence.rag_probes"], 1)
        self.assertEqual(failed["checks"]["source_coverage"], 0)

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

    def test_source_coverage_ignores_chatter_and_copy_differences(self) -> None:
        ticket = self.out / "PROJ-8"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        source = {
            "description": "• Customer case: E-002460814\n"
                           "The customer follows the official doc ([doc link|https://x/doc]) and configures copilot.\n"
                           "server: https://author.example.net [credentials shared with ]\n"
                           "direct link to access map on server: use this link",
            "comments": [{"id": "1", "author": "a", "body": "Hi, can you please share an ETA on this"},
                         {"id": "2", "author": "b", "body": "hey , has this task been picked up"},
                         {"id": "3", "author": "c", "body": "cc : issues have been created for the​ output failure"},
                         {"id": "4", "author": "d", "body": "Dynamics CRM is Watching this ticket E-1"}],
        }
        self.assertEqual([c for _, c in runner.source_clauses(source)], [
            "the customer follows the official doc (doc link) and configures copilot",
            "issues have been created for the output failure",
        ])
        coverage = [{"source": "description", "text": "Customer case: E-002460814", "disposition": "NOT_MATERIAL",
                     "reason": "support case id"},
                    {"source": "description", "text": "The customer follows the official doc (doc link) and configures "
                     "copilot.", "disposition": "AC", "ac": 1},
                    {"source": "comment:3", "text": "issues have been created for the output failure",
                     "disposition": "NOT_MATERIAL", "reason": "tracking note"}]
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
        self.assertEqual(runner.source_coverage_problems(ticket, source), [])
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps([coverage[0], coverage[2]]), encoding="utf-8")
        self.assertTrue(any("1 Jira sentence(s)" in p and "official doc" in p
                            for p in runner.source_coverage_problems(ticket, source)))
        long_ping = ("can you share an eta and confirm the export button keeps the selected language "
                     "for every map in the batch")
        self.assertEqual(runner.source_clauses({"description": long_ping}), [("description", long_ping)])

    def test_support_template_metadata_and_status_pings_need_no_mapping(self) -> None:
        # Lines from GUIDES-51134, 51558, 51870, 52444 and 53402 that failed real runs.
        source = {
            "description": "\u2022 IMS Org ID: 8E84279C699C715B0A495E50@AdobeOrg\n"
                           "\u2022 Internal discussion thread: Slack link\n"
                           "\u2022 Internal SME discussion: Slack link\n"
                           "\u2022 Slack thread: [https://cq-dev.slack.com/archives/C1/p17812]\n"
                           "\u2022 Program/Env ID : TD-1 stage\n"
                           "\u2022 Program / Environment : cm-p185304-e1959210 (stage) \u2013 author url https://autho\n"
                           "Posted on guides channel: [https://cq-dev.slack.com/archives/C1/p1785]\n"
                           "Full investigation available here: [https://aemcs-workspace.adobe.com/bot/dynamic]\n"
                           "user: pkumar5@expediagroup.com ; editor load 08:42:43\n"
                           "1) Go to [http://ip/libs/fmdita/report/report.html/content/dam/samples/en/travel]\n"
                           "Headings below H1 render as H1 in the Sites output.",
            "comments": [
                {"id": "1", "author": "a", "body": "This case is pending from 2 days ago can you please prioritize this"},
                {"id": "2", "author": "b", "body": "Can you please update here"},
                {"id": "3", "author": "c", "body": "Could you let me know which release would this bug be fixed in "
                                                 "so that I can inform the customer"},
            ],
        }
        self.assertEqual([c for _, c in runner.source_clauses(source)],
                         ["headings below h1 render as h1 in the sites output"])

    def test_reference_lines_need_no_mapping_but_requirements_with_colons_do(self) -> None:
        # Lines from GUIDES-51134, 55885 and 57170 that blocked real runs, and lines that must stay.
        source = {"description": (
            "• Sample affected URL (stage): publish-p185304-e1959210/.../reference.html\n"
            "• Account / Org ID: 39BFB008560A6FB87F000101@AdobeOrg (Micron Experience Cloud)\n"
            "• Authentication performed with Adobe ID someone@example.com (member of the IMS org)\n"
            "• Customer case: E-002460814\n"
            "• Internal KB pointing out environment-scoping gap: [E-000874107 – Guides add-on per "
            "environment limitation|https://kb.example.com/1]\n"
            "• Related Jira (env-scoped MCP enablement): AEMAGT-2195\n"
            "Max limit: 1000 assets per request\n"
            "Expected Result: Images should render while using the core image component.\n"
            "To confirm on the customer env, check the size of the target path/jcr:content/published-map-order")}
        self.assertEqual([c for _, c in runner.source_clauses(source)], [
            "max limit: 1000 assets per request",
            "expected result: images should render while using the core image component",
            "to confirm on the customer env, check the size of the target path/jcr:content/published-map-order"])

    def test_a_rewritten_link_does_not_break_a_copied_sentence(self) -> None:
        ticket = self.out / "PROJ-10"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        source = {"description": "Open the report from [http://ip/libs/fmdita/report/report.html] and export it."}
        coverage = [{"source": "description", "text": "Open the report from http://<host>/libs/fmdita/report "
                     "and export it.", "disposition": "AC", "ac": 1}]
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
        self.assertEqual(runner.source_coverage_problems(ticket, source), [])

    def test_unmapped_comment_is_a_review_note_but_unmapped_description_still_fails(self) -> None:
        ticket = self.out / "PROJ-11"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        source = {"description": "The report must open from the Map console.",
                  "comments": [{"id": "56176281", "author": "support.eng",
                                "body": "Can you please send me a screen recording so that I can provide it to the customer"}]}
        coverage = [{"source": "description", "text": "The report must open from the Map console.",
                     "disposition": "AC", "ac": 1}]
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(coverage), encoding="utf-8")
        self.assertEqual(runner.source_coverage_problems(ticket, source), [], "a comment never stops the UAC")
        notes = runner.unmapped_comment_notes(ticket, source)
        self.assertEqual(len(notes), 1)
        self.assertIn("Comment 56176281 is not covered by the UAC", notes[0])
        self.assertIn("screen recording", notes[0])
        (ticket / common.SOURCE_COVERAGE_FILE).write_text("[]", encoding="utf-8")
        self.assertTrue(any("1 Jira sentence(s)" in p and "description:" in p
                            for p in runner.source_coverage_problems(ticket, source)),
                        "an unmapped description sentence still stops the UAC")

    def test_unmapped_comment_note_is_recorded_for_qe_not_posted_to_the_ticket(self) -> None:
        source = dict(SOURCE, comments=SOURCE["comments"] + [
            {"id": "99", "author": "support.eng", "body": "Can you share the server url to do UAT please"}])
        jira = FakeJira(source=source)
        self.assertEqual(self._run(jira), "POSTED")
        comments = "\n".join(c[2] for c in jira.calls if c[0] == "comment")
        self.assertNotIn("Comment 99", comments, "review notes stay off the ticket")
        self.assertIn("Comment 99 is not covered by the UAC", common.read_status(self.out / "PROJ-1")["review_notes"][-1])

    def test_rotated_logs_are_not_screens(self) -> None:
        for name in ("request.log.2026-07-07", "access.log.2026-06-29", "error.log.1", "server.log.gz",
                     "global-profile-listener.log.2026-06-29"):
            self.assertTrue(runner.is_non_visual_attachment(name), name)
        for name in ("shot.png", "recording.mp4", "screen.log.png"):
            self.assertFalse(runner.is_non_visual_attachment(name), name)

    def test_bot_closure_notice_is_not_a_requirement(self) -> None:
        source = {"description": "", "comments": [{"id": "1", "author": "xmladdon",
                                                    "body": "Jira closed without automating. Moving to open"}]}
        self.assertEqual(runner.source_clauses(source), [])

    def test_report_documents_are_not_screens(self) -> None:
        for name in ("translation_parallel_execution_test_summary.pdf", "Translation_Performance_Test_Report.docx",
                     "AEM-Guides-permissions.xlsx", "notes.doc", "data.xls"):
            self.assertTrue(runner.is_non_visual_attachment(name), name)
        self.assertFalse(runner.is_non_visual_attachment("Screen Recording 2026-08-20 at 12.45.33 PM.mov"))

    def test_log_attachment_needs_no_surfaces(self) -> None:
        ticket = self.out / "PROJ-9"
        ticket.mkdir()
        (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(SURFACES), encoding="utf-8")
        (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps([
            {"source": "attachment:logs 11 Aug.txt", "text": "server log", "disposition": "NOT_MATERIAL",
             "reason": "log excerpt"}]), encoding="utf-8")
        self.assertEqual(runner.attachment_surface_problems(ticket, SOURCE), [])

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

    def test_a_surface_named_in_a_sub_point_counts(self) -> None:
        ticket = self.out / "PROJ-7"
        ticket.mkdir()
        uac = ("- Acceptance Criteria 01: Existing screens still work as before.\n  - Outline panel\n"
               "  **Source:** Ticket description.\n")
        (ticket / common.UAC_FILE).write_text(uac, encoding="utf-8")
        entry = {"surface": "Outline panel", "evidence": ["https://experienceleague.adobe.com/o", "src/o.ts:1"],
                 "authority": "TICKET", "disposition": "AC", "ac": 1}
        (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps([entry]), encoding="utf-8")
        self.assertFalse(any("does not name" in p for p in runner.surface_inventory_problems(ticket)))
        named_only_in_source = uac.replace("  - Outline panel\n", "").replace("Ticket description", "Outline panel doc")
        (ticket / common.UAC_FILE).write_text(named_only_in_source, encoding="utf-8")
        self.assertTrue(any("does not name" in p for p in runner.surface_inventory_problems(ticket)),
                        "a Source line is not where a criterion names its surface")

    def test_source_lines_keep_documentation_urls_and_dates(self) -> None:
        text, removed = runner.clean_source_lines(
            "- Acceptance Criteria 01: X.\n  **Source:** GUIDES-1 description; "
            "https://experienceleague.adobe.com/docs/guides/x.html; comment on 07/07/2026; "
            "xmleditor/src/a/B.java; abc1234f\n")
        self.assertIn("https://experienceleague.adobe.com/docs/guides/x.html", text)
        self.assertIn("comment on 07/07/2026", text)
        self.assertEqual(removed, ["xmleditor/src/a/B.java", "abc1234f"])

    def test_a_wrapped_fix_note_is_removed_whole(self) -> None:
        uac = ("Note: The root cause and the fix are not confirmed yet. These criteria cover what the customer\n"
               "reported and will be checked again when the fix is known.\n\n- Acceptance Criteria 01: X.\n")
        out = runner.normalize_note(uac, "CONFIRMED")
        self.assertTrue(out.startswith("- Acceptance Criteria 01: X."), out)
        kept = runner.normalize_note("Note: Applies to Native PDF only.\n\n- Acceptance Criteria 01: X.\n", "CONFIRMED")
        self.assertTrue(kept.startswith("Note: Applies to Native PDF only."), "other notes stay")

    def test_malformed_doc_research_is_a_problem_not_a_crash(self) -> None:
        ticket = self.out / "PROJ-8"
        ticket.mkdir()
        (ticket / common.DOC_RESEARCH_FILE).write_text(json.dumps({"status": "PARTIAL", "findings": ["doc says X"]}),
                                                       encoding="utf-8")
        problems = runner.doc_research_problems(ticket, "")
        self.assertTrue(any("finding 1 is not an object" in p for p in problems), problems)

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

    def test_discovered_surface_can_go_to_the_test_plan(self) -> None:
        ticket = self.out / "PROJ-10"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")

        def problems(entries):
            (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(entries), encoding="utf-8")
            return runner.surface_inventory_problems(ticket)

        to_plan = SURFACES[:3] + [{k: v for k, v in SURFACES[3].items() if k != "ac"} | {"disposition": "TEST_PLAN"}]
        self.assertTrue(any("the full test plan does not name this surface" in p for p in problems(to_plan)))
        (ticket / common.PLAN_FILE).write_text("## Regression\n- The Map dashboard still opens the report.\n",
                                               encoding="utf-8")
        self.assertEqual(problems(to_plan), [])
        asked = [dict(SURFACES[0], disposition="TEST_PLAN")] + SURFACES[1:]
        self.assertTrue(any("needs an Acceptance Criterion or a TBD, not TEST_PLAN" in p for p in problems(asked)))

    def test_research_found_test_plan_surface_is_named_in_the_regression_areas(self) -> None:
        ticket = self.out / "PROJ-12"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
        plan = ("**Regression Areas**\n- Re-run the existing report export and assert the file still downloads.\n\n"
                "**Automation Coverage & Gaps**\n- Main feature coverage: Not covered - none.\n")
        (ticket / common.PLAN_FILE).write_text(plan, encoding="utf-8")
        to_plan = SURFACES[:3] + [{k: v for k, v in SURFACES[3].items() if k != "ac"} | {"disposition": "TEST_PLAN"}]
        asked = dict(SURFACES[0], surface="Ticket screen", disposition="TEST_PLAN")
        (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(to_plan + [asked]), encoding="utf-8")

        self.assertEqual(runner.add_test_plan_surfaces(ticket), ["Map dashboard"])
        text = (ticket / common.PLAN_FILE).read_text(encoding="utf-8")
        lines = text.splitlines()
        added = lines.index("- Re-run Map dashboard and assert it still works as before, because research found it "
                            "on the path this change touches; it is checked here rather than in the UAC.")
        self.assertEqual(lines[added + 1:added + 3], ["", "**Automation Coverage & Gaps**"], "kept in Regression Areas")
        self.assertNotIn("Ticket screen", text, "a surface the ticket asks for is not moved to the test plan")
        problems = runner.surface_inventory_problems(ticket)
        self.assertFalse(any("Map dashboard" in p for p in problems), problems)
        self.assertTrue(any("Ticket screen" in p and "not TEST_PLAN" in p for p in problems), problems)
        self.assertEqual(runner.add_test_plan_surfaces(ticket), [], "a named surface is not added twice")

    def test_one_criterion_lists_few_discovered_surfaces(self) -> None:
        ticket = self.out / "PROJ-11"
        ticket.mkdir()
        (ticket / common.UAC_FILE).write_text(
            UAC.replace("The report still opens from the Map dashboard as before.",
                        "The report still opens as before from the Map dashboard, Baseline panel, Review panel, "
                        "Map Collection, Output history and Translation panel."), encoding="utf-8")

        def problems(entries):
            (ticket / common.SURFACE_INVENTORY_FILE).write_text(json.dumps(entries), encoding="utf-8")
            return runner.surface_inventory_problems(ticket)

        extra = [dict(SURFACES[3], surface=name)
                 for name in ("Baseline panel", "Review panel", "Map Collection", "Output history")]
        self.assertEqual(problems(SURFACES + extra), [])
        too_many = SURFACES + extra + [dict(SURFACES[3], surface="Translation panel")]
        self.assertIn("Acceptance Criteria 3 lists 6 screens found only by research; keep at most 5 and move the "
                      "rest to TEST_PLAN", problems(too_many))

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

    def test_staleness_finds_fix_comments_after_the_uac_changed(self) -> None:
        issue = {
            "changelog": {"histories": [
                {"created": "2026-01-10T10:00:00.000+0000", "items": [{"field": "Acceptance Criteria"}]},
                {"created": "2026-01-11T10:00:00.000+0000", "items": [{"field": "labels"}]},
            ]},
            "fields": {"comment": {"comments": [
                {"id": "1", "author": {"name": "dev"}, "created": "2026-01-09T09:00:00.000+0000", "body": "Root cause: x"},
                {"id": "2", "author": {"name": "dev"}, "created": "2026-01-12T09:00:00.000+0000", "body": "Root cause: bad XML"},
                {"id": "3", "author": {"name": "qa"}, "created": "2026-01-12T10:00:00.000+0000", "body": "Any update?"},
                {"id": "4", "author": {"name": "uac.bot"}, "created": "2026-01-12T11:00:00.000+0000", "body": "the fix is in"},
                {"id": "5", "author": {"name": "dev"}, "created": "2026-01-13T09:00:00.000+0000",
                 "body": "PR: https://git.example.com/org/repo/pull/8295"},
            ]}},
        }
        since = staleness.last_ac_change(issue, "customfield_1")
        self.assertEqual(since, "2026-01-10T10:00:00.000+0000", "only Acceptance Criteria changes count")
        found = [c["id"] for c in staleness.fix_comments_after(issue, since, "uac.bot")]
        self.assertEqual(found, ["2", "5"], "before the UAC, plain questions and own comments are ignored")

    def test_staleness_alerts_each_comment_once_and_never_writes_the_ticket(self) -> None:
        issue = {"changelog": {"histories": [{"created": "2026-01-10T10:00:00.000+0000",
                                              "items": [{"fieldId": "customfield_1"}]}]},
                 "fields": {"comment": {"comments": [
                     {"id": "9", "author": {"name": "dev"}, "created": "2026-01-12T09:00:00.000+0000",
                      "body": "Root cause found"}]}}}
        jira = FakeJira()
        jira._json = mock.Mock(return_value=issue)
        state: dict = {}
        first = staleness.stale_lines(self.config, jira, self.log, ["PROJ-1"], state)
        second = staleness.stale_lines(self.config, jira, self.log, ["PROJ-1"], state)
        self.assertEqual(len(first), 1)
        self.assertIn("PROJ-1: a root cause or fix was reported by dev on 2026-01-12", first[0])
        self.assertEqual(second, [], "an already alerted comment is not alerted again")
        self.assertEqual(jira.calls, [], "the watcher never writes to the ticket")

    def test_staleness_alerts_a_contract_or_design_added_after_the_uac(self) -> None:
        issue = {"changelog": {"histories": [{"created": "2026-10-04T05:08:00.000+0000",
                                              "items": [{"fieldId": "customfield_1"}]}]},
                 "fields": {
                     "comment": {"comments": [
                         {"id": "20", "author": {"name": "dev"}, "created": "2026-10-05T10:43:00.000+0000",
                          "body": "[^translation-status-api-contract.md]"},
                         {"id": "21", "author": {"name": "dev"}, "created": "2026-10-05T11:00:00.000+0000",
                          "body": "Design: https://wiki.corp.adobe.com/spaces/x/pages/9/Design"},
                         {"id": "22", "author": {"name": "dev"}, "created": "2026-10-01T11:00:00.000+0000",
                          "body": "Old design: https://wiki.corp.adobe.com/spaces/x/pages/8/Old"}]},
                     "attachment": [
                         {"id": "301", "filename": "translation-status-api-contract.md",
                          "author": {"name": "dev"}, "created": "2026-10-05T10:43:00.000+0000"},
                         {"id": "300", "filename": "PROJ-1-test-plan.md",
                          "author": {"name": "uac.bot"}, "created": "2026-10-04T05:08:00.000+0000"}]}}
        jira = FakeJira()
        jira._json = mock.Mock(return_value=issue)
        state: dict = {}
        first = staleness.stale_lines(self.config, jira, self.log, ["PROJ-1"], state, "uac.bot")
        self.assertEqual(len(first), 2, first)
        self.assertIn("dev added a wiki page link (design document or specification) on 2026-10-05", first[0])
        self.assertIn("dev added the attachment translation-status-api-contract.md on 2026-10-05", first[1])
        self.assertEqual(staleness.stale_lines(self.config, jira, self.log, ["PROJ-1"], state, "uac.bot"), [],
                         "each attachment and link is alerted once")
        self.assertEqual(jira.calls, [], "the watcher never writes to the ticket")

    def test_staleness_alerts_an_api_contract_written_in_a_comment(self) -> None:
        issue = {"changelog": {"histories": [{"created": "2026-01-10T10:00:00.000+0000",
                                              "items": [{"field": "Acceptance Criteria"}]}]},
                 "fields": {"comment": {"comments": [
                     {"id": "1", "author": {"name": "dev"}, "created": "2026-01-12T09:00:00.000+0000",
                      "body": "API contract:\nPOST /bin/guides/v1/purge\nRequest body: {path}\nStatus codes: 200, 409"},
                     {"id": "2", "author": {"name": "qa"}, "created": "2026-01-12T10:00:00.000+0000",
                      "body": "Is the API ready for testing?"},
                     {"id": "3", "author": {"name": "dev"}, "created": "2026-01-12T11:00:00.000+0000",
                      "body": "Root cause found; the response body now has the job id. PR #812"},
                     {"id": "4", "author": {"name": "uac.bot"}, "created": "2026-01-12T12:00:00.000+0000",
                      "body": "GET /bin/guides/v1/status"}]}}}
        found = staleness.new_evidence_after(issue, "2026-01-10T10:00:00.000+0000", "uac.bot")
        self.assertEqual([(f["id"], f["what"]) for f in found], [("1", "an API contract or design in a comment")],
                         "'the response body now has ...' is not a contract")
        jira = FakeJira()
        jira._json = mock.Mock(return_value=issue)
        lines = staleness.stale_lines(self.config, jira, self.log, ["PROJ-1"], {}, "uac.bot")
        self.assertEqual(len(lines), 2)
        self.assertIn("PROJ-1: a root cause or fix was reported by dev", lines[0])
        self.assertIn("PROJ-1: dev added an API contract or design in a comment on 2026-01-12", lines[1])

    def test_contract_signal_ignores_repro_steps_and_errors(self) -> None:
        contract = ["POST https://author.example.com/bin/guides/v1/purge with {path}",
                    "GET /bin/guides/v1/status?jobId=1", "Request body: {\"path\": \"/content/dam\"}",
                    "Status codes: 200, 409", "See the API spec", "OpenAPI file attached in the wiki"]
        not_contract = ["Delete /content/dam/guides/topic.dita and reopen the map",
                        "I get /content/dam/x not found", "Saving fails with status code 500",
                        "the response body is empty", "Is the API ready for testing?"]
        for text in contract:
            self.assertTrue(staleness.CONTRACT_SIGNAL.search(text), text)
        for text in not_contract:
            self.assertFalse(staleness.CONTRACT_SIGNAL.search(text), text)

    def test_staleness_compares_real_times_and_skips_generator_accounts(self) -> None:
        issue = {"changelog": {"histories": [{"created": "2026-10-25T01:30:00.000+0100",
                                              "items": [{"field": "Acceptance Criteria"}]}]},
                 "fields": {"comment": {"comments": [
                     {"id": "1", "author": {"name": "dev"}, "created": "2026-10-25T01:10:00.000+0000",
                      "body": "Root cause: the cache"},
                     {"id": "2", "author": {"name": "qe.author"}, "created": "2026-10-26T01:10:00.000+0000",
                      "body": "the fix is in PR #9"}]}}}
        self.assertEqual(staleness.last_ac_change(issue, "customfield_1"), "2026-10-25T01:30:00.000+0100")
        jira = FakeJira()
        jira._json = mock.Mock(return_value=issue)
        config = dict(self.config, learning_generator_users=["qe.author"])
        lines = staleness.stale_lines(config, jira, self.log, ["PROJ-1"], {}, "uac.bot")
        self.assertEqual(len(lines), 1, lines)
        self.assertIn("PROJ-1: a root cause or fix was reported by dev on 2026-10-25", lines[0],
                      "01:10 UTC is after 01:30+01:00 (00:30 UTC)")

    def test_staleness_keeps_other_alerts_when_one_ticket_cannot_be_read(self) -> None:
        good = {"changelog": {"histories": [{"created": "2026-01-10T10:00:00.000+0000",
                                             "items": [{"field": "Acceptance Criteria"}]}]},
                "fields": {"comment": {"comments": [
                    {"id": "9", "author": {"name": "dev"}, "created": "2026-01-12T09:00:00.000+0000",
                     "body": "Root cause found"}]}}}
        jira = FakeJira()
        jira._json = mock.Mock(side_effect=[good, RuntimeError("HTTP 503")])
        state: dict = {}
        lines = staleness.stale_lines(self.config, jira, self.log, ["PROJ-1", "PROJ-2"], state, "uac.bot")
        self.assertIn("PROJ-1: a root cause or fix was reported by dev", lines[0])
        self.assertIn("PROJ-2: could not be checked", lines[1])
        self.assertEqual(state, {"PROJ-1": ["9"]})

    def test_staleness_state_is_saved_only_when_the_alert_was_delivered(self) -> None:
        issue = {"changelog": {"histories": [{"created": "2026-01-10T10:00:00.000+0000",
                                              "items": [{"field": "Acceptance Criteria"}]}]},
                 "fields": {"comment": {"comments": [
                     {"id": "9", "author": {"name": "dev"}, "created": "2026-01-12T09:00:00.000+0000",
                      "body": "Root cause found"}]}}}
        config_path = self.out / "config.json"
        config_path.write_text(json.dumps(self.config), encoding="utf-8")
        state_file = Path(self.config["output_dir"]) / staleness.STATE_FILE
        for result, saved in (("FAILED", False), ("POSTED", True)):
            jira = FakeJira()
            jira._json = mock.Mock(side_effect=lambda *a, **k: issue)
            jira.myself = mock.Mock(return_value={"name": "uac.bot"})
            jira.search_keys = mock.Mock(return_value=["PROJ-1"])
            with mock.patch.object(staleness.common.JiraClient, "from_env", return_value=jira), \
                    mock.patch.object(staleness.common, "load_env_file"), \
                    mock.patch.object(staleness.common, "send_alert", return_value=result):
                try:
                    staleness.main(["--config", str(config_path)])
                finally:
                    # main() opens a log file; Windows cannot delete the temp folder while it is open.
                    close_logger("uac-staleness")
            self.assertEqual(state_file.is_file(), saved, result)
        self.assertEqual(jira.calls, [], "the watcher never writes to the ticket")

    def test_staleness_jql_uses_the_posted_label(self) -> None:
        jql = staleness.staleness_jql(dict(self.config, approved_scope_jql="project = PROJ"))
        self.assertEqual(jql, '(project = PROJ) AND labels = "QEVision_UAC_DONE" AND updated >= -7d')

    def test_ticket_without_evidence_record_is_not_posted(self) -> None:
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, evidence=None)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        problems = common.read_status(self.out / "PROJ-1")["problems"]
        self.assertTrue(any(common.EVIDENCE_FILE in p for p in problems))

    def test_skipped_rag_and_unused_doc_finding_are_not_posted(self) -> None:
        evidence = json.loads(json.dumps(EVIDENCE))
        evidence["rag_probes"] = []
        evidence["doc_findings"] = []
        jira = FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, evidence=evidence)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False), "FAILED")
        problems = " ".join(common.read_status(self.out / "PROJ-1")["problems"])
        self.assertIn("probe(s) were recorded", problems)
        self.assertIn("documentation finding 1", problems)

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

    def test_orphan_notes_stay_in_status_and_do_not_fail_the_ticket(self) -> None:
        jira = FakeJira()
        note = "Acceptance Criteria 2 is not tied to any ticket sentence"
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True)), \
                mock.patch.object(runner, "check_outputs", return_value=[]), \
                mock.patch.object(runner, "orphan_ac_problems", return_value=[note]):
            result = runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False)
        self.assertEqual(result, "POSTED")
        comment = [c for c in jira.calls if c[0] == "comment"][0][2]
        self.assertNotIn(note, comment, "review notes are not posted to the ticket")
        self.assertEqual(common.read_status(self.out / "PROJ-1")["review_notes"], [note])

    def test_orphan_acceptance_criterion_fails(self) -> None:
        self.assertEqual(runner.orphan_ac_problems(self._ticket_with("PROJ-8", UAC)), [])
        extra = UAC + ("- Acceptance Criteria 04: Verify that an export with no rows shows an empty file.\n"
                       "  **Source:** Ticket description.\n")
        found = runner.orphan_ac_problems(self._ticket_with("PROJ-9", extra))
        self.assertEqual(len(found), 1)
        self.assertIn("Acceptance Criteria 4 is not tied to any ticket sentence", found[0])

    def test_regression_ac_on_a_discovered_surface_is_not_an_orphan(self) -> None:
        extra = UAC + ("- Acceptance Criteria 04: Verify that the Report dialog still opens as before.\n"
                       "  **Source:** src/controllers/report_dialog.ts line 40.\n")
        surfaces = SURFACES + [{"surface": "Report dialog", "evidence": ["src/controllers/report_dialog.ts:40"],
                                "authority": "CODE_REUSE", "disposition": "AC", "ac": 4}]
        self.assertEqual(runner.orphan_ac_problems(self._ticket_with("PROJ-10", extra, surfaces=surfaces)), [])

    def test_one_ticket_sentence_can_drive_several_criteria(self) -> None:
        extra = UAC + ("- Acceptance Criteria 04: Verify that an export with no rows shows an empty file.\n"
                       "  **Source:** Ticket description.\n")
        coverage = [dict(COVERAGE[0], ac=[1, 4])] + COVERAGE[1:]
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
            self.assertEqual(runner.main(["--check-dir", str(ticket), "--own-name", "uac.bot"]), 1,
                             "the evidence record is still missing")
            (ticket / common.EVIDENCE_FILE).write_text(json.dumps(EVIDENCE), encoding="utf-8")
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


POSTED_FIELD = (
    "*Acceptance Criteria 01:* Verify that the report opens from the Map console.\n"
    "* Source: Ticket description; {{ReportServlet.java}} line 10.\n\n"
    "*Acceptance Criteria 02:* Verify that an empty report shows a message.\n"
    "* Source: Ticket description.\n"
    "* TBD: Which message text should be shown?\n\n"
    "*Acceptance Criteria 03:* Verify that the export button still downloads a CSV file.\n"
    "* Source: QE reasoning."
)
HUMAN_FIELD = (
    "* Verify that the report opens from the Map console.\n"
    " * Verify that an empty report shows the message No data for this map.\n"
    " * Verify that the report opens from the Map dashboard too."
)


def _issue(field_text: str, status: str, changes: list[tuple[str, str]]) -> dict:
    return {
        "fields": {"customfield_1": field_text, "status": {"name": status}, "summary": "Report",
                   "components": [{"name": "Publishing"}]},
        "changelog": {"histories": [{"created": at, "author": {"name": by}, "items": [{"fieldId": "customfield_1"}]}
                                    for at, by in changes]},
    }


class LearningHarvesterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.log = logging.getLogger("test")
        ticket = self.out / "PROJ-1"
        ticket.mkdir()
        (ticket / "field-body.txt").write_text(POSTED_FIELD, encoding="utf-8")
        common.write_status(ticket, {"state": "POSTED"})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def jira_with(self, issue: dict) -> FakeJira:
        jira = FakeJira()
        jira._json = mock.Mock(return_value=issue)
        return jira

    def test_backfill_reads_the_posted_version_from_jira_history(self) -> None:
        issue = _issue(HUMAN_FIELD, "In Progress", [])
        issue["changelog"]["histories"] = [
            {"created": "2026-01-01T10:00:00.000+0000", "author": {"name": "dev.lead"},
             "items": [{"fieldId": "customfield_1", "toString": "* PKCE check should work"}]},
            {"created": "2026-01-02T10:00:00.000+0000", "author": {"name": "qe.author"},
             "items": [{"fieldId": "customfield_1", "toString": POSTED_FIELD}]},
            {"created": "2026-01-05T09:30:00.000+0000", "author": {"name": "qe.lead"},
             "items": [{"fieldId": "customfield_1", "toString": HUMAN_FIELD}]},
        ]
        jira = self.jira_with(issue)
        generators = harvester.generator_users(self.config, "uac.bot", ["qe.author"])
        [record] = harvester.backfill(self.config, jira, self.log, generators, ["PROJ-9"])
        self.assertEqual((record["source"], record["posted_by"], record["editor"]), ("backfill", "qe.author", "qe.lead"))
        self.assertEqual(record["posted_text"], POSTED_FIELD, "the generator's last write is the posted version")
        self.assertEqual(record["counts"], {"accepted": 1, "changed": 1, "removed": 1, "added": 1, "promoted": 0})
        self.assertEqual(jira.calls, [], "the backfill only reads Jira")
        self.assertEqual(harvester.backfill(self.config, jira, self.log, generators, ["PROJ-9"]), [],
                         "the same version is recorded once")

    def test_backfill_waits_while_the_generator_wrote_last(self) -> None:
        issue = _issue(POSTED_FIELD, "Open", [])
        issue["changelog"]["histories"] = [
            {"created": "2026-01-02T10:00:00.000+0000", "author": {"name": "qe.author"},
             "items": [{"fieldId": "customfield_1", "toString": POSTED_FIELD}]}]
        jira = self.jira_with(issue)
        generators = harvester.generator_users(self.config, "uac.bot", ["qe.author"])
        self.assertEqual(harvester.backfill(self.config, jira, self.log, generators, ["PROJ-9"]), [])
        no_generator = harvester.generator_users(self.config, "uac.bot")
        self.assertEqual(harvester.backfill(self.config, jira, self.log, no_generator, ["PROJ-9"]), [],
                         "without a generator write there is no posted version")

    def test_backfill_dry_run_writes_nothing(self) -> None:
        issue = _issue(HUMAN_FIELD, "UAT", [])
        issue["changelog"]["histories"] = [
            {"created": "2026-01-02T10:00:00.000+0000", "author": {"name": "qe.author"},
             "items": [{"fieldId": "customfield_1", "toString": POSTED_FIELD}]},
            {"created": "2026-01-05T09:30:00.000+0000", "author": {"name": "qe.lead"},
             "items": [{"fieldId": "customfield_1", "toString": HUMAN_FIELD}]}]
        generators = harvester.generator_users(self.config, "uac.bot", ["qe.author"])
        records = harvester.backfill(self.config, self.jira_with(issue), self.log, generators, ["PROJ-9"], dry_run=True)
        self.assertEqual(len(records), 1)
        self.assertFalse((self.out / "learning" / "records.jsonl").exists())

    def test_generator_users_from_config_are_not_counted_as_qe_edits(self) -> None:
        config = dict(self.config, learning_generator_users=["qe.author"])
        issue = _issue(HUMAN_FIELD, "In Progress", [("2026-01-01T10:00:00.000+0000", "qe.author")])
        self.assertEqual(harvester.harvest(config, self.jira_with(issue), self.log, "uac.bot"), [])

    def test_a_later_write_by_our_own_user_is_not_learned_as_a_qe_edit(self) -> None:
        own_edit = HUMAN_FIELD + "\n * Note added by the automation's user."
        issue = _issue(own_edit, "In Progress", [])
        issue["changelog"]["histories"] = [
            {"created": "2026-01-05T09:30:00.000+0000", "author": {"name": "dev.lead"},
             "items": [{"fieldId": "customfield_1", "toString": HUMAN_FIELD}]},
            {"created": "2026-01-06T09:30:00.000+0000", "author": {"name": "uac.bot"},
             "items": [{"fieldId": "customfield_1", "toString": own_edit}]}]
        [record] = harvester.harvest(self.config, self.jira_with(issue), self.log, "uac.bot")
        self.assertEqual(record["editor"], "dev.lead")
        self.assertEqual(record["current_text"], HUMAN_FIELD, "the automation user's own edit is left out")

    def test_only_our_own_user_editing_teaches_nothing(self) -> None:
        issue = _issue(HUMAN_FIELD, "In Progress", [("2026-01-05T09:30:00.000+0000", "uac.bot")])
        self.assertEqual(harvester.harvest(self.config, self.jira_with(issue), self.log, "uac.bot"), [])

    def test_a_same_account_rewrite_is_the_baseline_for_qe_edits(self) -> None:
        rewritten = POSTED_FIELD.replace("* Source: Ticket description; {{ReportServlet.java}} line 10.",
                                         "* Source: Ticket description.")

        def history(*writes):
            return [{"created": at, "author": {"name": by}, "items": [{"fieldId": "customfield_1", "toString": text}]}
                    for at, by, text in writes]

        posted = ("2026-01-01T10:00:00.000+0000", "uac.bot", POSTED_FIELD)
        session = ("2026-01-01T15:00:00.000+0000", "uac.bot", rewritten)
        issue = _issue(HUMAN_FIELD, "In Progress", [])
        issue["changelog"]["histories"] = history(posted, session,
                                                  ("2026-01-05T09:30:00.000+0000", "qe.lead", HUMAN_FIELD))
        [record] = harvester.harvest(self.config, self.jira_with(issue), self.log, "uac.bot")
        self.assertEqual(record["posted_text"], rewritten, "the session's rewrite is not counted as a QE change")
        self.assertEqual(record["editor"], "qe.lead")

        accepted = _issue(rewritten, "UAT", [])
        accepted["changelog"]["histories"] = history(posted, session)
        [record] = harvester.harvest(self.config, self.jira_with(accepted), self.log, "uac.bot")
        self.assertEqual(record["outcome"], "ACCEPTED_AS_IS")

    def test_shared_account_edits_that_are_not_a_posted_text_are_qe_edits(self) -> None:
        # GUIDES-54956: the cron and the QE both write as the same Jira user.
        rerun = POSTED_FIELD.replace("an empty report shows a message", "an empty report shows a short message")
        (self.out / "PROJ-1" / "field-body.txt").write_text(rerun, encoding="utf-8")
        common.remember_posted_body(self.out / "PROJ-1", POSTED_FIELD)
        common.remember_posted_body(self.out / "PROJ-1", rerun)

        def history(*writes):
            return [{"created": at, "author": {"name": "shared.user"},
                     "items": [{"fieldId": "customfield_1", "toString": text.replace("\n", "\r\n")}]}
                    for at, text in writes]

        issue = _issue(HUMAN_FIELD, "In Progress", [])
        issue["changelog"]["histories"] = history(("2026-10-04T05:08:00.000+0000", POSTED_FIELD),
                                                  ("2026-10-04T08:40:00.000+0000", rerun),
                                                  ("2026-10-06T10:08:00.000+0000", HUMAN_FIELD))
        self.assertEqual(harvester.harvest(self.config, self.jira_with(issue), self.log, "shared.user"), [],
                         "without the setting every write by the automation's user is generated")
        config = dict(self.config, learning_shared_account=True)
        [record] = harvester.harvest(config, self.jira_with(issue), self.log, "shared.user")
        self.assertEqual(record["outcome"], "CHANGED")
        self.assertEqual(record["editor"], "shared.user")
        self.assertEqual(record["edited_at"], "2026-10-06T10:08:00.000+0000")
        self.assertEqual(record["posted_text"].replace("\r\n", "\n"), rerun,
                         "the QE edit is compared with the cron's last posted version")

    def test_runner_remembers_every_posted_text(self) -> None:
        ticket = self.out / "PROJ-1"
        common.remember_posted_body(ticket, "a\r\nb ")
        self.assertIn(common.text_key("a\nb"), common.posted_body_keys(ticket))
        self.assertIn(common.text_key(POSTED_FIELD), common.posted_body_keys(ticket), "field-body.txt counts too")

    def test_field_now_records_any_change_for_the_release_page(self) -> None:
        issue = _issue(HUMAN_FIELD, "In Progress", [("2026-01-05T09:30:00.000+0000", "uac.bot")])
        harvester.harvest(self.config, self.jira_with(issue), self.log, "uac.bot")
        now = json.loads((self.out / "PROJ-1" / harvester.FIELD_NOW_FILE).read_text(encoding="utf-8"))
        self.assertEqual((now["criteria"], now["changed"], now["last_change_by"]), (3, True, "uac.bot"),
                         "an edit made with our own account still shows on the release page")
        harvester.harvest(self.config, self.jira_with(_issue(POSTED_FIELD, "In Progress", [])), self.log, "uac.bot")
        now = json.loads((self.out / "PROJ-1" / harvester.FIELD_NOW_FILE).read_text(encoding="utf-8"))
        self.assertEqual((now["criteria"], now["changed"]), (3, False))

    def test_open_questions_are_not_part_of_a_criterion(self) -> None:
        text = ("Understanding: the list is out of order.\n\n"
                "AC-01: The Conditions panel lists conditions by label.\n"
                "AC-02: In Editor Preview the conditions are ordered by label.\n\n"
                "Open Questions:\n"
                "OQ-01 (fallback): confirm the sort when a label is missing.\n"
                "-[To Confirm] OQ-06 (review app): the list also appears in the Review app.-\n"
                "AC-03: The groups stay in label order.")
        criteria = harvester.parse_criteria(text)
        self.assertEqual([c["text"] for c in criteria], [
            "The Conditions panel lists conditions by label.",
            "In Editor Preview the conditions are ordered by label.",
            "The groups stay in label order."])

    def test_missed_screens_are_screens_our_uac_never_named(self) -> None:
        posted = "AC-01: The Conditions panel lists conditions by label. AC-02: Editor Preview is ordered too."
        self.assertEqual(harvester.missed_screens("Conditions displayed in right panel are ordered by label.", posted),
                         ["right panel"])
        self.assertEqual(harvester.missed_screens("The Conditions panel keeps the group order.", posted), [],
                         "a screen our UAC already named is not a missed screen")

    def test_monthly_report_counts_each_missed_screen_once_per_ticket(self) -> None:
        human = HUMAN_FIELD + "\n * Verify that the right panel lists the report.\n * Verify that the right panel sorts it."
        jira = self.jira_with(_issue(human, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("Overall: 3 posted criteria - accepted 1, changed 1, removed 1; QE added 3 (missed screens 2).", report)
        self.assertIn("Missed screens (named by a QE-added criterion, never named in our UAC):", report)
        self.assertEqual(report.count("PROJ-1: right panel -"), 1)
        self.assertIn("PROJ-1: map dashboard -", report)

    def test_a_suggested_check_qe_moved_into_the_field_is_promoted_not_missed(self) -> None:
        common.write_status(self.out / "PROJ-1", {"state": "POSTED",
                                                  "suggested": ["Verify that the report opens from the Map dashboard."]})
        jira = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        self.assertEqual((record["counts"]["added"], record["counts"]["promoted"]), (0, 1))
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("QE added 0, promoted 1 suggested", report)
        self.assertIn("Suggested checks QE moved into the criteria:", report)

    def test_monthly_report_shows_how_often_each_runner_check_fired(self) -> None:
        firing = common.import_skill_module("gate_firing_log")
        log = self.out / "logs" / "gate-firing.jsonl"
        firing.record(log, tool="uac-runner", key="PROJ-1", checks={"evidence.scenario": 2, "outputs": 0})
        firing.record(log, tool="uac-runner", key="PROJ-2", checks={"evidence.scenario": 0, "outputs": 0})
        jira = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("## Runner checks this month", report)
        self.assertIn("| evidence.scenario | 1 | 50% | 2 |", report)
        self.assertIn("| outputs | 0 | 0% | 0 |", report)

    def test_comment_requested_criteria_and_qe_notes_are_reported_apart(self) -> None:
        posted = ("- Acceptance Criteria 01: A folder profile Admin User can add another Admin User.\n"
                  "  Source: the fix pull request.\n\n"
                  "- Acceptance Criteria 02: An added Admin User has the license to open the content.\n"
                  "  Source: Jira comment by a reviewer, 26 Aug.\n\n"
                  "- Acceptance Criteria 03: Admin Users are kept after an upgrade.\n"
                  "  Source: the fix version.")
        current = ("- Acceptance Criteria 01: A folder profile Admin User can add another Admin User.\n"
                   "Source: the fix pull request.\n\n"
                   " - -Acceptance Criteria 02: An added Admin User has the license to open the content.-\n"
                   "{-}Source: Jira comment by a reviewer, 26 Aug.{-} (not needed, as discussed with the dev)\n\n"
                   " - Acceptance Criteria 03: -Admin Users are kept after an upgrade.-\n"
                   "{-}Source: the fix version.{-}(upgrade is not impacted)\n\n"
                   "Automation UI or API is required")
        self.assertEqual(harvester.closing_notes(current), ["Automation UI or API is required"])
        self.assertEqual(harvester.closing_notes(posted), [])
        entries = harvester.compare(harvester.parse_criteria(posted), harvester.parse_criteria(current))
        removed = {e["number"]: e for e in entries if e["kind"] == "removed"}
        self.assertTrue(removed[2].get("requested_in_comment"))
        self.assertFalse(removed[3].get("requested_in_comment"))
        jira = self.jira_with(_issue(current, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        (self.out / "PROJ-1" / "field-body.txt").write_text(posted, encoding="utf-8")
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        self.assertEqual(record["qe_notes"], ["Automation UI or API is required"])
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("removed 2 (1 asked for in a Jira comment)", report)
        self.assertIn("Asked for in a Jira comment, then removed by QE", report)
        self.assertIn("PROJ-1: An added Admin User has the license", report.split("Asked for in a Jira comment")[1])
        self.assertIn("PROJ-1: Admin Users are kept after an upgrade", report.split("What we wrote that QE removed:")[1])
        self.assertIn("Notes QE added below the criteria (not criteria):", report)
        self.assertIn("- PROJ-1: Automation UI or API is required", report)

    def test_out_of_scope_items_are_not_criteria(self) -> None:
        text = ("1. Related links from the reltable appear in Native PDF.\n"
                "2. Default behaviour stays without related links.\n\n"
                "Out of Scope:\n1. HTML5 output.\n2. DITA-OT disabled.")
        self.assertEqual([c["text"] for c in harvester.parse_criteria(text)],
                         ["Related links from the reltable appear in Native PDF.",
                          "Default behaviour stays without related links."])

    def test_suggested_checks_in_the_field_are_not_criteria(self) -> None:
        text = ("- Acceptance Criteria 01: The report opens from the Map console.\n\n"
                "Suggested checks (QE decide):\n"
                "- Suggested check 01: The report opens from the Map dashboard.\n")
        self.assertEqual([c["text"] for c in harvester.parse_criteria(text)], ["The report opens from the Map console."])

    def test_labels_in_every_format_are_criteria(self) -> None:
        text = ("AC-01: A folder profile Admin User can add an Admin User.\n"
                "AC-02: The same user can remove an Admin User.\n\n"
                " - Acceptance Criteria 03: Verify that the Global Profile is unchanged.\n"
                "Source: FolderProfilesAPI.java:639.\n\n"
                "Automation UI or API is required")
        criteria = harvester.parse_criteria(text)
        self.assertEqual([c["text"] for c in criteria], [
            "A folder profile Admin User can add an Admin User.",
            "The same user can remove an Admin User.",
            "Verify that the Global Profile is unchanged."])
        self.assertIn("FolderProfilesAPI.java", criteria[2]["source"])

    def test_struck_criteria_are_removed_with_the_qe_reason(self) -> None:
        posted = harvester.parse_criteria(
            "*Acceptance Criteria 01:* Verify that an Admin User can add another Admin User.\n\n"
            "*Acceptance Criteria 02:* Verify that a new Admin User has the license to open the content.\n\n"
            "*Acceptance Criteria 03:* Verify that Admin Users are kept after upgrading to the new release.\n\n"
            "*Acceptance Criteria 04:* Verify that another user cannot change the list. The request returns HTTP 200.")
        current = harvester.parse_criteria(
            " - Acceptance Criteria 01: Verify that an Admin User can add another Admin User.\n\n"
            " - -Acceptance Criteria 02: Verify that a new Admin User has the license to open the content.-\n"
            "{-}Source: reviewer comment. ({-}not needed, the groups are mutually exclusive)\n\n"
            " - Acceptance Criteria 03: -Verify that Admin Users are kept after upgrading to the new release.-\n"
            "{-}Source: fix version.{-}(confirmed with the dev, upgrade is not impacted)\n\n"
            " - Acceptance Criteria 04: Verify that another user cannot change the list.\n"
            "-The request returns HTTP 200.-\n"
            "{-}TBD: Should it return an error?({-}not relevant for UI)\n\n"
            "Automation UI or API is required")
        self.assertEqual([c["struck"] for c in current], [False, True, True, False])
        entries = harvester.compare(posted, current)
        kinds = {e["old"][:31]: (e["kind"], e.get("reason", "")) for e in entries}
        self.assertEqual(kinds["Verify that an Admin User can a"][0], "accepted")
        self.assertEqual(kinds["Verify that a new Admin User ha"],
                         ("removed", "not needed, the groups are mutually exclusive"))
        self.assertEqual(kinds["Verify that Admin Users are kep"],
                         ("removed", "confirmed with the dev, upgrade is not impacted"))
        self.assertEqual(kinds["Verify that another user cannot"], ("changed", "not relevant for UI"))
        self.assertFalse(any(e["kind"] == "added" for e in entries), "the closing note is not a new criterion")

    def test_monthly_report_shows_the_qe_reason(self) -> None:
        struck = ("*Acceptance Criteria 01:* Verify that the report opens from the Map console.\n\n"
                  "*Acceptance Criteria 02:* -Verify that an empty report shows a message.-\n"
                  "{-}Source: Ticket description.{-}(not in scope for this fix)\n\n"
                  "*Acceptance Criteria 03:* Verify that the export button still downloads a CSV file.")
        jira = self.jira_with(_issue(struck, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("Verify that an empty report shows a message. (QE: not in scope for this fix)", report)

    def test_parse_reads_our_labels_and_human_bullets(self) -> None:
        ours = harvester.parse_criteria(POSTED_FIELD)
        self.assertEqual([c["text"] for c in ours][0], "Verify that the report opens from the Map console.")
        self.assertIn("ReportServlet.java", ours[0]["source"], "Source lines belong to their criterion")
        self.assertEqual(ours[1]["tbd"], "Which message text should be shown?")
        self.assertEqual(len(harvester.parse_criteria("Summary\n\nSome context.\n\n" + HUMAN_FIELD)), 3,
                         "text before the first criterion is ignored")

    def test_compare_classifies_each_criterion(self) -> None:
        entries = harvester.compare(harvester.parse_criteria(POSTED_FIELD), harvester.parse_criteria(HUMAN_FIELD))
        kinds = sorted(e["kind"] for e in entries)
        self.assertEqual(kinds, ["accepted", "added", "changed", "removed"])
        removed = next(e for e in entries if e["kind"] == "removed")
        self.assertIn("export button", removed["old"])
        added = next(e for e in entries if e["kind"] == "added")
        self.assertIn("Map dashboard", added["new"])

    def test_untouched_field_counts_only_after_the_ticket_moves_on(self) -> None:
        in_progress = self.jira_with(_issue(POSTED_FIELD, "In Progress", [("2026-01-01T10:00:00.000+0000", "uac.bot")]))
        self.assertEqual(harvester.harvest(self.config, in_progress, self.log, "uac.bot"), [])
        uat = self.jira_with(_issue(POSTED_FIELD, "UAT", [("2026-01-01T10:00:00.000+0000", "uac.bot")]))
        [record] = harvester.harvest(self.config, uat, self.log, "uac.bot")
        self.assertEqual(record["outcome"], "ACCEPTED_AS_IS")
        self.assertEqual(record["counts"]["accepted"], 3)
        self.assertEqual(harvester.harvest(self.config, uat, self.log, "uac.bot"), [], "a version is recorded once")

    def test_only_human_edits_are_learned_and_jira_is_never_written(self) -> None:
        bot_only = self.jira_with(_issue(HUMAN_FIELD, "In Progress", [("2026-01-01T10:00:00.000+0000", "uac.bot")]))
        self.assertEqual(harvester.harvest(self.config, bot_only, self.log, "uac.bot"), [])
        human = self.jira_with(_issue(HUMAN_FIELD, "In Progress", [("2026-01-01T10:00:00.000+0000", "uac.bot"),
                                                                   ("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, human, self.log, "uac.bot")
        self.assertEqual((record["outcome"], record["editor"]), ("CHANGED", "qe.lead"))
        self.assertEqual(record["edited_at"], "2026-01-05T09:30:00.000+0000")
        self.assertEqual(record["posted_text"], POSTED_FIELD)
        self.assertEqual(record["current_text"], HUMAN_FIELD)
        self.assertEqual(record["components"], ["Publishing"])
        self.assertEqual(human.calls, [], "the harvester only reads Jira")
        lines = (self.out / "learning" / "records.jsonl").read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)

    def test_tickets_not_posted_to_the_field_are_skipped(self) -> None:
        common.write_status(self.out / "PROJ-1", {"state": "DRAFT_POSTED"})
        jira = self.jira_with(_issue(HUMAN_FIELD, "UAT", []))
        self.assertEqual(harvester.harvest(self.config, jira, self.log, "uac.bot"), [])
        jira._json.assert_not_called()

    def test_criterion_kinds_come_from_the_evidence_record(self) -> None:
        evidence = {
            "scenario": {"acs": [{"ac": 1, "scenario": "CUSTOMER"}, {"ac": 2, "scenario": "VARIANT"},
                                 {"ac": 3, "scenario": "REGRESSION"}]},
            "action_variants": {
                "entry_points": [{"name": "Map dashboard", "disposition": "AC", "ac": 2},
                                 {"name": "Map Collection", "disposition": "NOT_APPLICABLE", "reason": "x"}],
                "config_switches": [{"name": "flag", "disposition": "AC", "acs": [2, 3]}],
                "input_sources": [{"name": "Word", "disposition": "AC", "ac": 1}],
                "mechanism": {"variants": [{"name": "map", "disposition": "TBD", "ac": 1}],
                              "reverse_action": {"name": "undo", "disposition": "AC", "ac": 3},
                              "value_shapes": {"name": "values", "disposition": "NOT_APPLICABLE", "reason": "x"}}},
            "pre_existing_items": {"disposition": "AC", "ac": 1},
            "failure_path": {"remaining_items": {"disposition": "AC", "ac": 3}},
        }
        self.assertEqual(harvester.criterion_kinds(evidence), {
            1: ["reporter step", "input source", "item type", "items made before the change"],
            2: ["variant", "entry point", "switch state"],
            3: ["regression check", "switch state", "reverse action", "failure path"]})
        self.assertEqual(harvester.criterion_kinds({}), {})

    def test_monthly_report_counts_removals_by_kind(self) -> None:
        (self.out / "PROJ-1" / "UAC_EVIDENCE.json").write_text(json.dumps({
            "scenario": {"acs": [{"ac": 1, "scenario": "CUSTOMER"}, {"ac": 2, "scenario": "CUSTOMER"},
                                 {"ac": 3, "scenario": "REGRESSION"}]},
            "action_variants": {"entry_points": [{"name": "export", "disposition": "AC", "ac": 3}]}}),
            encoding="utf-8")
        jira = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        removed = [e for e in record["criteria"] if e["kind"] == "removed"]
        self.assertEqual([(e["number"], e.get("kinds")) for e in removed], [(3, ["regression check", "entry point"])])
        self.assertEqual((record["posted_count"], record["kept_count"]), (3, 3))
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("## Removed by kind", report)
        self.assertIn("| reporter step | 2 | 0 | 0% |", report)
        self.assertIn("| regression check | 1 | 1 | 100% |", report)
        self.assertIn("| entry point | 1 | 1 | 100% |", report)
        self.assertIn("we posted a median of 3, QE left a median of 3", report)

    def test_criteria_without_an_evidence_record_are_counted_apart(self) -> None:
        jira = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, jira, self.log, "uac.bot")
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("| (no evidence record) | 3 | 1 | 33% |", report)

    def test_monthly_report_lists_what_we_overwrote_and_missed(self) -> None:
        human = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, human, self.log, "uac.bot")
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("## Publishing", report)
        self.assertIn("Criteria accepted 1, changed 1, removed 1, added 1", report)
        self.assertIn("What we wrote that QE removed:", report)
        self.assertIn("export button", report)
        self.assertIn("What QE added that we missed:", report)
        self.assertIn("Map dashboard", report)

    def test_report_shows_runtime_fallback_uacs_separately(self) -> None:
        ticket = self.out / "PROJ-1"
        common.write_status(ticket, {"state": "POSTED",
                                     "runtime_fallback": ["FinalQEPlanRenderer: no criteria to render"]})
        human = self.jira_with(_issue(HUMAN_FIELD, "UAT", [("2026-01-05T09:30:00.000+0000", "qe.lead")]))
        [record] = harvester.harvest(self.config, human, self.log, "uac.bot")
        self.assertEqual(record["uac_origin"], "RUNTIME_FALLBACK")
        self.assertEqual(record["runtime_fallback_gates"], ["FinalQEPlanRenderer: no criteria to render"])
        lines = harvester.origin_report_lines([record, {"key": "PROJ-2", "uac_origin": "CANONICAL",
                                                        "criteria": [{"kind": "accepted"}, {"kind": "accepted"}]}])
        text = "\n".join(lines)
        self.assertIn("| Skill runtime (all gates passed) | 1 | 2 | 2 | 0 | 0 | 0 | 100% |", text)
        self.assertIn("| Runtime fallback (gates not passed) | 1 | 3 | 1 | 1 | 1 | 1 | 33% |", text)
        self.assertIn("- FinalQEPlanRenderer: 1", text)
        report = harvester.monthly_report(self.config, record["harvested_at"][:7]).read_text(encoding="utf-8")
        self.assertIn("## By how the UAC was written", report)

    def test_records_without_an_origin_count_as_runtime_or_backfill(self) -> None:
        self.assertEqual(harvester._origin({"key": "A"}), "CANONICAL")
        self.assertEqual(harvester._origin({"key": "B", "source": "backfill"}), "HAND_POSTED")


class DecisionRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.config["decision_comment"] = {"enabled": True, "mention": ["assignee"], "cc": ["qa.lead"]}
        self.log = logging.getLogger("test")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def post(self, decisions: str = DECISIONS, config: dict | None = None, jira: FakeJira | None = None) -> FakeJira:
        jira = jira or FakeJira()
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, decisions=decisions)), \
                mock.patch.object(runner, "check_outputs", return_value=[]):
            self.assertEqual(runner.process_ticket("PROJ-1", config or self.config, jira, self.log, dry_run=False),
                             "POSTED")
        return jira

    def requests(self, jira: FakeJira) -> list[str]:
        return [c[2] for c in jira.calls if c[0] == "comment" and "product decisions are still open" in c[2]]

    def test_decision_request_is_sent_once_with_mentions_after_the_field_is_written(self) -> None:
        jira = self.post()
        [request] = self.requests(jira)
        self.assertTrue(request.startswith("[~dev.lead] [~qa.lead] "))
        self.assertIn("# Is a button enough?", request)
        self.assertIn("\\[Home page\\]", request)
        kinds = [c[0] for c in jira.calls]
        self.assertLess(kinds.index("set_field"), kinds.index("people"), "people are tagged only after the UAC is in")
        ticket = self.out / "PROJ-1"
        status = common.read_status(ticket)
        self.assertTrue(status["decision_comment_id"])
        self.assertEqual(runner.post_decision_request("PROJ-1", self.config, jira, self.log, ticket, status, "x"),
                         "ALREADY_POSTED")

    def test_a_failed_decision_request_keeps_the_ticket_posted(self) -> None:
        jira = FakeJira()
        original = jira.add_comment

        def add_comment(key, body):
            if "product decisions are still open" in body:
                raise RuntimeError("HTTP 500")
            return original(key, body)
        jira.add_comment = add_comment
        self.post(jira=jira)
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "POSTED")
        self.assertIn("HTTP 500", status["decision_request_error"])
        self.assertNotIn("last_error", status)

    def test_tbd_without_decisions_file_warns_and_sends_nothing(self) -> None:
        jira = self.post(decisions="")
        status = common.read_status(self.out / "PROJ-1")
        self.assertTrue(any("DECISIONS.md was not written" in w for w in status["warnings"]))
        self.assertEqual(self.requests(jira), [])

    def test_decisions_missing_a_section_are_not_sent(self) -> None:
        jira = self.post(decisions="### Decision needed\n1. Is a button enough?\n")
        status = common.read_status(self.out / "PROJ-1")
        self.assertTrue(any("missing section" in w for w in status["warnings"]))
        self.assertFalse((self.out / "PROJ-1" / common.DECISION_BODY_FILE).exists())
        self.assertEqual(self.requests(jira), [])

    def test_disabled_setting_sends_no_decision_request(self) -> None:
        jira = self.post(config=dict(self.config, decision_comment={"enabled": False}))
        self.assertEqual(self.requests(jira), [])


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
            return "POSTED"

        jira = FakeJira()
        self.assertEqual(self.run_runner(jira, process), 1)
        self.assertEqual(seen, ["PROJ-1", "PROJ-2"])
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "ERROR")
        self.assertIn("Jira returned 500", status["last_error"])
        record = self.runs()[-1]
        self.assertEqual(record["tickets"], {"PROJ-1": "ERROR", "PROJ-2": "POSTED"})
        self.assertEqual(record["exit_code"], 1)
        log_text = "".join(p.read_text(encoding="utf-8") for p in (self.out / "logs").glob("uac-runner-*.log"))
        self.assertIn("Traceback", log_text, "the traceback goes to the daily log, not only cron.log")
        [alert] = self.alert_comments(jira)
        self.assertIn("[~qe.lead]", alert)
        self.assertIn("PROJ-1: unexpected error - ConnectionError: Jira returned 500", alert)

    def test_error_after_posting_keeps_the_posted_state(self) -> None:
        common.write_status(self.out / "PROJ-1", {"state": "POSTED"})
        results, errors = common.run_each(["PROJ-1"], lambda k: 1 / 0, self.log, self.out)
        self.assertEqual(results, {"PROJ-1": "ERROR"})
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["state"], "POSTED")
        self.assertIn("ZeroDivisionError", status["last_error"])

    def test_failed_ticket_is_alerted_with_its_first_problem(self) -> None:
        def process(key, *args):
            if key == "PROJ-2":
                common.write_status(self.out / key, {"state": "FAILED", "problems": ["no doc researcher run", "x"]})
                return "FAILED"
            return "POSTED"

        jira = FakeJira()
        self.run_runner(jira, process)
        [alert] = self.alert_comments(jira)
        self.assertIn("PROJ-2: UAC not posted - no doc researcher run (and 1 more)", alert)
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
        send = lambda lines: common.send_alert(self.config, jira, self.log, "uac-runner", "r1", lines)  # noqa: E731
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


class ReleaseDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ticket(self, key: str, status: dict, summary: str = "", body: str = "") -> None:
        folder = self.out / key
        folder.mkdir()
        common.write_status(folder, status)
        if summary:
            (folder / common.JIRA_SOURCE_FILE).write_text(json.dumps({"summary": summary}), encoding="utf-8")
        if body:
            (folder / "field-body.txt").write_text(body, encoding="utf-8")

    def test_a_fallback_uac_is_posted_and_marked(self) -> None:
        self.ticket("PROJ-1", {"state": "POSTED", "runtime_fallback": ["FinalQEPlanRenderer: no criteria"]})
        self.ticket("PROJ-2", {"state": "POSTED"})
        posted, _ = dashboard.collect_tickets(self.out)
        where = {r["key"]: r["where"] for r in posted}
        self.assertIn("runtime gates not passed", where["PROJ-1"])
        self.assertEqual(where["PROJ-2"], "Acceptance Criteria field")

    def test_dashboard_hint_says_how_shared_account_edits_are_counted(self) -> None:
        page = dashboard.render([], [], [], 0, "", "now")
        self.assertIn("are not counted here", page)
        shared = dashboard.render([], [], [], 0, "", "now", shared_account=True)
        self.assertIn("share one Jira account", shared)
        self.assertNotIn("are not counted here", shared)

    def test_a_field_changed_after_posting_shows_both_counts(self) -> None:
        body = "\n".join(f"*Acceptance Criteria {n:02d}:* c{n}" for n in range(1, 10))
        self.ticket("PROJ-1", {"state": "POSTED"}, "Save timeout", body)
        self.ticket("PROJ-2", {"state": "POSTED"}, "Untouched", "*Acceptance Criteria 01:* a")
        (self.out / "PROJ-1" / dashboard.FIELD_NOW_FILE).write_text(json.dumps(
            {"criteria": 7, "changed": True, "last_change_at": "2026-10-04T08:15:00.000+0530",
             "last_change_by": "prashantp"}), encoding="utf-8")
        (self.out / "PROJ-2" / dashboard.FIELD_NOW_FILE).write_text(json.dumps(
            {"criteria": 1, "changed": False}), encoding="utf-8")
        posted, _ = dashboard.collect_tickets(self.out)
        page = dashboard.render(posted, [], [], 0, "https://jira.example", "now")
        self.assertIn("9 &rarr; 7 (edited)", page)
        self.assertIn("last by prashantp at 2026-10-04 08:15", page)
        self.assertEqual(dashboard._criteria_cell(posted[1]), "1")

    def test_posted_ticket_shows_its_review_notes_behind_a_click(self) -> None:
        self.ticket("PROJ-1", {"state": "POSTED", "review_notes": [
            'Comment 99 is not covered by the UAC; check it is not a requirement: "share the <server> url"']},
            "Report", "*Acceptance Criteria 01:* a")
        self.ticket("PROJ-2", {"state": "POSTED"}, "Clean", "*Acceptance Criteria 01:* a")
        posted, _ = dashboard.collect_tickets(self.out)
        page = dashboard.render(posted, [], [], 0, "https://jira.example", "now")
        self.assertIn("<summary>1 review note(s)</summary>", page)
        self.assertIn("share the &lt;server&gt; url", page, "notes are escaped")
        self.assertEqual(page.count("review note(s)"), 1, "a ticket without notes shows none")

    def test_tickets_split_into_posted_and_not_posted_with_reasons(self) -> None:
        self.ticket("PROJ-1", {"state": "POSTED", "posted_at": "2026-10-02T07:05:00+0000"}, "Report",
                    "*Acceptance Criteria 01:* a\n*Acceptance Criteria 02:* b")
        self.ticket("PROJ-2", {"state": "FAILED", "problems": ["UAC.md was not written", "test-plan.md was not written"]})
        self.ticket("PROJ-3", {"state": "FIELD_KEPT"})
        self.ticket("PROJ-4", {"state": "POSTED", "last_error": "Jira returned 500"})
        (self.out / "logs").mkdir()
        posted, not_posted = dashboard.collect_tickets(self.out)
        self.assertEqual([(r["key"], r["criteria"], r["summary"]) for r in posted], [("PROJ-1", 2, "Report")])
        reasons = {r["key"]: r["reason"] for r in not_posted}
        self.assertEqual(reasons["PROJ-2"], "UAC.md was not written (and 1 more)")
        self.assertIn("already had text", reasons["PROJ-3"])
        self.assertEqual(reasons["PROJ-4"], "Unexpected error: Jira returned 500")

    def test_human_edits_keep_the_newest_change_per_ticket(self) -> None:
        learning = self.out / "learning"
        learning.mkdir()
        lines = [{"key": "PROJ-1", "outcome": "CHANGED", "editor": "qe.a", "edited_at": "2026-10-01"},
                 {"key": "PROJ-1", "outcome": "CHANGED", "editor": "dev.b", "edited_at": "2026-10-03"},
                 {"key": "PROJ-2", "outcome": "ACCEPTED_AS_IS"}]
        (learning / "records.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\nnot json\n",
                                                encoding="utf-8")
        edits, accepted = dashboard.collect_human_edits(self.out)
        self.assertEqual([(r["key"], r["editor"]) for r in edits], [("PROJ-1", "dev.b")])
        self.assertEqual(accepted, 1)

    def test_page_escapes_ticket_text_and_links_to_jira(self) -> None:
        self.ticket("PROJ-1", {"state": "FAILED", "problems": ["<script>alert(1)</script>"]}, "A <b>bold</b> title")
        config = self.out / "config.json"
        config.write_text(json.dumps(dict(make_config(self.out), output_dir=str(self.out))), encoding="utf-8")
        page = self.out / "site" / "index.html"
        with mock.patch.dict(os.environ, {"JIRA_BASE_URL": "https://jira.example.com"}):
            self.assertEqual(dashboard.main(["--config", str(config), "--env-file", str(self.out / "none.env"),
                                             "--out", str(page)]), 0)
        text = page.read_text(encoding="utf-8")
        self.assertNotIn("<script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn('href="https://jira.example.com/browse/PROJ-1"', text)
        self.assertIn("No UAC posted yet.", text)

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_page_folder_is_readable_by_the_web_server_under_a_strict_umask(self) -> None:
        old = os.umask(0o077)
        try:
            page = self.out / "site" / "index.html"
            dashboard.write_atomic(page, "<!doctype html>")
        finally:
            os.umask(old)
        self.assertEqual(page.parent.stat().st_mode & 0o777, 0o755)
        self.assertEqual(page.stat().st_mode & 0o777, 0o644)


WIKI = "https://wiki.corp.adobe.com/spaces/projecttrack/pages/4066975661/Asset+translation+status+API"


class FakeWiki:
    def __init__(self, text: str = "<h2>Response</h2><table><tr><th>status</th><td>IN_SYNC</td></tr></table>"):
        self.text = text

    def fetch(self, url):
        return "4066975661", "Asset translation status API", linked_docs.storage_to_text(self.text)


class LinkedDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.log = logging.getLogger("test")
        self.source = dict(SOURCE, comments=SOURCE["comments"] + [
            {"id": "9", "author": "dev.lead", "body": "Design document to be reviewed " + WIKI},
            {"id": "10", "author": "uac.bot", "body": "see https://wiki.corp.adobe.com/pages/viewpage.action?pageId=1"},
        ])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_links_come_from_the_description_and_human_comments_only(self) -> None:
        source = {"description": "Spec: [design|https://wiki.corp.adobe.com/display/DOC/My+Page]. "
                                 "Other: https://example.com/x",
                  "comments": self.source["comments"]}
        self.assertEqual(linked_docs.find_links(source, "uac.bot"),
                         ["https://wiki.corp.adobe.com/display/DOC/My+Page", WIKI])

    def test_page_id_from_every_wiki_link_form(self) -> None:
        client = linked_docs.WikiClient("https://wiki.corp.adobe.com", "t")
        self.assertEqual(client.page_id(WIKI), "4066975661")
        self.assertEqual(client.page_id("https://wiki.corp.adobe.com/pages/viewpage.action?pageId=42"), "42")
        with mock.patch.object(client, "_get", return_value={"results": [{"id": 77}]}) as get:
            self.assertEqual(client.page_id("https://wiki.corp.adobe.com/display/DOC/My+Page"), "77")
        self.assertIn("title=My+Page", get.call_args[0][0])

    def test_storage_format_becomes_readable_text(self) -> None:
        text = linked_docs.storage_to_text("<h2>Errors</h2><ul><li>404 &amp; missing</li><li>403</li></ul>"
                                           "<table><tr><th>field</th><td>status</td></tr></table>")
        self.assertIn("Errors", text)
        self.assertIn("- 404 & missing", text)
        self.assertIn("| field | status", text)

    def test_without_a_wiki_token_every_link_is_recorded_as_unreadable(self) -> None:
        entries = linked_docs.collect(self.source, self.out, "uac.bot", None)
        self.assertEqual([e["status"] for e in entries], ["UNREADABLE"])
        self.assertIn("WIKI_PAT", entries[0]["reason"])
        self.assertEqual(len(linked_docs.unread(entries)), 1)

    def test_a_read_page_is_saved_for_the_copilot_session(self) -> None:
        entries = linked_docs.collect(self.source, self.out, "uac.bot", FakeWiki())
        self.assertEqual(entries[0]["status"], "READ")
        text = Path(entries[0]["file"]).read_text(encoding="utf-8")
        self.assertIn("Asset translation status API", text)
        self.assertIn("IN_SYNC", text)
        saved = json.loads((self.out / linked_docs.LINKED_DOCS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(saved, entries)

    def test_code_blocks_are_kept(self) -> None:
        text = linked_docs.storage_to_text('<p>Submit</p><ac:structured-macro ac:name="code"><ac:plain-text-body>'
                                           '<![CDATA[POST /api/x\n{"mapPath": "/a"}]]></ac:plain-text-body>'
                                           '</ac:structured-macro>')
        self.assertIn("POST /api/x", text)
        self.assertIn('"mapPath"', text)

    def test_pages_linked_from_an_index_page_are_read_once(self) -> None:
        child_a = "https://wiki.corp.adobe.com/spaces/x/pages/2/Product+Note"
        child_b = "https://wiki.corp.adobe.com/spaces/x/pages/3/Design+Document"
        pages = {WIKI: ("1", "Index", f"{child_a}\n{child_b}\n{WIKI}"),
                 child_a: ("2", "Product Note", f"note text {WIKI}"),
                 child_b: ("3", "Design Document", "POST /bin/guides/v1/translation/map/references")}
        wiki = FakeWiki()
        wiki.fetch = lambda url: pages[url]
        entries = linked_docs.collect(self.source, self.out, "uac.bot", wiki)
        self.assertEqual([e["title"] for e in entries], ["Index", "Product Note", "Design Document"])
        self.assertEqual([e.get("via", "") for e in entries], ["", WIKI, WIKI])
        self.assertTrue(all(e["status"] == "READ" for e in entries))

    def test_a_failing_page_does_not_stop_the_others(self) -> None:
        wiki = FakeWiki()
        wiki.fetch = mock.Mock(side_effect=RuntimeError("wiki GET failed: HTTP 403"))
        entries = linked_docs.collect(self.source, self.out, "uac.bot", wiki)
        self.assertEqual(entries[0]["status"], "UNREADABLE")
        self.assertIn("403", entries[0]["reason"])

    def _run(self, coverage, wiki) -> str:
        jira = FakeJira(source=self.source)
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, coverage=coverage)),                 mock.patch.object(runner, "check_outputs", return_value=[]),                 mock.patch.object(runner.linked_docs.WikiClient, "from_env", return_value=wiki):
            return runner.process_ticket("PROJ-1", self.config, jira, self.log, dry_run=False)

    def _coverage(self, linked: bool) -> list:
        design = {"source": "comment:9", "text": "Design document to be reviewed " + WIKI, "disposition": "AC", "ac": 1}
        page = {"source": f"linked:{WIKI}", "text": "status IN_SYNC", "disposition": "AC", "ac": 1}
        return COVERAGE + [design] + ([page] if linked else [])

    def test_prompt_points_the_session_at_the_downloaded_pages(self) -> None:
        self.assertIn("{linked_docs_path}", runner.PROMPT)
        self.assertIn("do not try to open the wiki yourself", runner.PROMPT)

    def test_a_downloaded_page_is_evidence_not_a_gate(self) -> None:
        self.assertEqual(self._run(self._coverage(False), FakeWiki()), "POSTED",
                         "a page the UAC does not cite never blocks the UAC")

    def test_a_mapped_page_is_posted(self) -> None:
        self.assertEqual(self._run(self._coverage(True), FakeWiki()), "POSTED")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["linked_docs_unread"], [])
        self.assertTrue((self.out / "PROJ-1" / linked_docs.LINKED_DOCS_DIR / "4066975661.md").is_file())

    def test_an_unreadable_page_still_writes_the_uac_and_is_flagged(self) -> None:
        self.assertEqual(self._run(self._coverage(False), None), "POSTED", "the UAC is always written")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(len(status["linked_docs_unread"]), 1)
        posted, _ = dashboard.collect_tickets(self.out)
        self.assertIn("linked design document not read", posted[0]["where"])


class DeliveryCleanupTests(unittest.TestCase):
    """The Note line and Source lines in the field are decided by the runner, not by wording."""

    def test_note_follows_fix_basis(self) -> None:
        check = common.import_skill_module("uac_completeness_check")
        self.assertTrue(runner.normalize_note(UAC, "NOT_A_DEFECT").startswith("- Acceptance Criteria 01"),
                        "a new capability has no root-cause note")
        self.assertTrue(runner.normalize_note(UAC, "CONFIRMED").startswith("- Acceptance Criteria 01"))
        proposed = runner.normalize_note(UAC, "PROPOSED")
        self.assertTrue(proposed.startswith(check.PROPOSED_NOTE))
        self.assertNotIn("not confirmed", proposed)
        self.assertEqual(runner.normalize_note(proposed, "UNCONFIRMED").count("Note:"), 1)
        known = runner.normalize_note(runner.normalize_note(UAC, "UNCONFIRMED"), "CAUSE_KNOWN")
        self.assertTrue(known.startswith(check.CAUSE_KNOWN_NOTE), "the cause-known note replaces the other note")
        self.assertNotIn("not confirmed", known)
        self.assertEqual(known.count("Note:"), 1)

    def test_a_feature_request_label_drops_the_root_cause_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            (ticket / common.UAC_FILE).write_text(UAC, encoding="utf-8")
            (ticket / common.EVIDENCE_FILE).write_text(
                json.dumps({"fix_basis": {"status": "UNCONFIRMED", "reason": "no comment"}}), encoding="utf-8")
            feature, _ = runner.deliverable_uac(ticket, {"labels": ["Emerson", "customer-Features"]})
            defect, _ = runner.deliverable_uac(ticket, {"labels": ["sla3"]})
        self.assertNotIn("not confirmed", feature, "an access-review story has no root-cause note")
        self.assertIn("not confirmed", defect)

    def test_process_deliverables_are_not_criteria(self) -> None:
        text = ("- Acceptance Criteria 01: HTML5 output generates after the publishing ZIP becomes available.\n"
                "- Acceptance Criteria 02: The incident record identifies the missing-ZIP cause.\n"
                "- Acceptance Criteria 03: Creation and upload have separate timings for each batch.\n"
                "- Acceptance Criteria 04: The approved urgent rollback to AEM release 2608 lets customers publish.\n"
                "  - Source: comment saying the incident record is updated.\n")
        problems = runner.process_ac_problems(text)
        self.assertEqual([p.split(" is ")[0] for p in problems],
                         ["Acceptance Criteria 02", "Acceptance Criteria 03", "Acceptance Criteria 04"])

    def test_wording_nudges_are_review_notes_not_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: A topic created from a map template shows the same reused content.\n"
                "- Acceptance Criteria 02: Each new topic made from a referenced topic template shows it too.\n",
                encoding="utf-8")
            notes = runner.vocabulary_notes(ticket)
            self.assertEqual(len(notes), 1)
            self.assertIn("topic-from-map-template", notes[0])
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: Each new topic shows the reused content.\n"
                "  - External conref with topicId/elementId.\n", encoding="utf-8")
            ids = " ".join(runner.vocabulary_notes(ticket))
            self.assertIn("external-conref", ids, "case sub-points are checked too")
            self.assertIn("camelcase-id-names", ids)
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: Each new topic shows the reused content.\n"
                '  - A conref with href="file.dita#topicID/elementID" and href="file.dita#elementID" both work.\n',
                encoding="utf-8")
            self.assertEqual(runner.vocabulary_notes(ticket), [], "the href form is the wording we want")
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: Each new topic shows the reused content.\n"
                "  - The supported long fragment displays the intended external content.\n", encoding="utf-8")
            ids = " ".join(runner.vocabulary_notes(ticket))
            self.assertIn("fragment-jargon", ids)
            self.assertIn("intended-vague", ids)
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: Each new topic shows the reused content.\n"
                "  - References to copied topic templates still resolve to their new topics.\n", encoding="utf-8")
            ids = " ".join(runner.vocabulary_notes(ticket))
            self.assertIn("resolve-jargon", ids)
            self.assertIn("copied-topic-templates", ids)
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: A locked file keeps its Tags.\n"
                "  - Try it with Use Database for AEM Guides toggled on, and again toggled off.\n", encoding="utf-8")
            self.assertIn("db-jcr-flavour", " ".join(runner.vocabulary_notes(ticket)))
            (ticket / common.UAC_FILE).write_text(
                "- Acceptance Criteria 01: A locked file keeps its Tags.\n"
                "  - Try it on Cloud with the DB flavour, and again with the JCR flavour.\n", encoding="utf-8")
            self.assertEqual(runner.vocabulary_notes(ticket), [], "the flavour wording is what we want")
            blocked, _ = runner._vocabulary_hits((ticket / common.UAC_FILE).read_text(encoding="utf-8"))
            self.assertEqual(blocked, [], "a nudge never blocks the UAC")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(runner.vocabulary_notes(Path(tmp)), [])

    def test_process_criteria_move_to_the_test_plan_and_the_uac_is_still_delivered(self) -> None:
        text = ("Note: n\n\n- Acceptance Criteria 01: HTML5 output generates after the publishing ZIP becomes available.\n"
                "  **Source:** ticket.\n"
                "- Acceptance Criteria 02: The incident record identifies the missing-ZIP cause.\n"
                "  **Source:** comment.\n"
                "- Acceptance Criteria 03: Retried generation finishes without an error.\n"
                "Out of scope:\n- Customer network.\n")
        delivered, moved = runner.move_process_acs(text)
        self.assertIn("- Acceptance Criteria 01: HTML5 output generates", delivered)
        self.assertIn("- Acceptance Criteria 02: Retried generation finishes", delivered, "the rest is renumbered")
        self.assertNotIn("incident record", delivered)
        self.assertIn("Out of scope:", delivered)
        self.assertEqual(len(moved), 1)
        self.assertTrue(moved[0].startswith("Acceptance Criteria 02: The incident record"))
        only = "- Acceptance Criteria 01: The incident record identifies the cause.\n"
        self.assertEqual(runner.move_process_acs(only), (only, []), "the UAC is never emptied")
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            (ticket / common.PLAN_FILE).write_text("plan", encoding="utf-8")
            runner.record_moved_acs(ticket, moved)
            self.assertIn("Moved from the UAC", (ticket / common.PLAN_FILE).read_text(encoding="utf-8"))

    def test_source_lines_lose_revisions_paths_and_code_names_but_keep_attachments(self) -> None:
        text = ("- Acceptance Criteria 01: x.\n"
                "  **Source:** GUIDES-1 comment 58244293; inspected starling commit 16a8982; Starling PublishListener.\n"
                "- Acceptance Criteria 02: y.\n"
                "  **Source:** GUIDES-1 description and {{componentMapping.json}}.\n")
        out, removed = runner.clean_source_lines(text, ["componentMapping.json"])
        self.assertIn("**Source:** GUIDES-1 comment 58244293.", out)
        self.assertIn("{{componentMapping.json}}", out)
        self.assertEqual(removed, ["inspected starling commit 16a8982", "Starling PublishListener."])

    def test_pull_requests_linked_in_comments_are_listed_for_the_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = {"description": "", "comments": [
                {"author": "bot", "body": "PR [starling #1|https://git.corp.adobe.com/A/starling/pull/8294] needs review"}]}
            entries = linked_docs.collect(source, Path(tmp), "uac.bot", None)
        self.assertEqual(entries, [{"url": "https://git.corp.adobe.com/A/starling/pull/8294", "kind": "pull_request",
                                    "status": "LINKED", "note": "a proposed fix; read its diff in the matching clone"}])
        self.assertEqual(linked_docs.unread(entries), [], "a linked pull request is not an unread page")

    def test_completeness_check_knows_proposed_and_new_capability_tickets(self) -> None:
        check = common.import_skill_module("uac_completeness_check")
        source = {"description": "Add an API.", "comments": [{"body": "Fix: https://x/y/pull/1 needs review"}]}
        ok = check.fix_basis_problems({"fix_basis": {"status": "PROPOSED", "signal": "Fix: https://x/y/pull/1 needs review"}},
                                      runner.normalize_note(UAC, "PROPOSED"), source)
        self.assertEqual(ok, [])
        self.assertTrue(check.fix_basis_problems({"fix_basis": {"status": "PROPOSED", "signal": "Fix: https://x/y/pull/1 needs review"}},
                                                 UAC, source), "PROPOSED needs the proposed-fix note")
        feature = {"fix_basis": {"status": "NOT_A_DEFECT", "reason": "the ticket asks for a new status API"}}
        self.assertEqual(check.fix_basis_problems(feature, runner.normalize_note(UAC, "NOT_A_DEFECT"), source), [])
        self.assertTrue(check.fix_basis_problems(feature, UAC, source), "a new capability has no root-cause note")

    def test_copilot_runs_with_the_ticket_research_store(self) -> None:
        env = runner.copilot_env(Path("/runs/PROJ-1"))
        self.assertEqual(env["AGENT_RESEARCH_MODE"], "copilot_host")
        self.assertEqual(Path(env["AGENT_RESEARCH_STORE"]), Path("/runs/PROJ-1") / "agent-research")
        self.assertIn("PATH", env, "the rest of the environment is kept")
        self.assertIn("never with --http", runner.PROMPT)
        self.assertIn("fulfill-agent --store", runner.PROMPT)
        self.assertIn("{research_store}", runner.PROMPT)

    def test_the_session_uses_the_backend_python(self) -> None:
        self.assertEqual(runner.runtime_python({"runtime_python": "/opt/py311/bin/python"}), "/opt/py311/bin/python")
        with tempfile.TemporaryDirectory() as tmp:
            venv = Path(tmp) / "backend" / "venv" / "bin"
            venv.mkdir(parents=True)
            (venv / "python").write_text("", encoding="utf-8")
            with mock.patch.object(runner.common, "REPO_ROOT", Path(tmp)):
                self.assertEqual(runner.runtime_python({}), str(venv / "python"), "backend/venv is found")
            with mock.patch.object(runner.common, "REPO_ROOT", Path(tmp) / "elsewhere"):
                self.assertEqual(runner.runtime_python({}), "")
        env = runner.copilot_env(Path("/runs/PROJ-1"), "/opt/py311/bin/python")
        self.assertTrue(env["PATH"].startswith(str(Path("/opt/py311/bin")) + os.pathsep))
        self.assertIn("{runtime_python} scripts/run_test_plan_pipeline.py {key}", runner.PROMPT)
        self.assertIn("{runtime_python} scripts/agent_research_bridge.py fulfill-agent", runner.PROMPT)

    def test_unanswered_runtime_research_is_counted_and_noted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            pending, fulfilled = ticket / "agent-research" / "pending", ticket / "agent-research" / "fulfilled"
            pending.mkdir(parents=True)
            fulfilled.mkdir()
            for name, role in (("a.json", "DOC_RESEARCHER"), ("b.json", "CODE_RESEARCHER"), ("c.json", "DOC_RESEARCHER")):
                (pending / name).write_text(json.dumps({"worker_role": role}), encoding="utf-8")
            (fulfilled / "c.json").write_text("{}", encoding="utf-8")
            summary = runner.research_store_summary(ticket)
            self.assertEqual(summary, {"requests": 3, "answered": 1,
                                       "unanswered_by_role": {"CODE_RESEARCHER": 1, "DOC_RESEARCHER": 1}})
            self.assertEqual(runner.research_store_notes(summary), [
                "canonical runtime research requests not answered: 2 of 3 (1 CODE_RESEARCHER, 1 DOC_RESEARCHER); "
                "the runtime could not use them"])
            (fulfilled / "a.json").write_text("{}", encoding="utf-8")
            (fulfilled / "b.json").write_text("{}", encoding="utf-8")
            self.assertEqual(runner.research_store_notes(runner.research_store_summary(ticket)), [])
        self.assertEqual(runner.research_store_summary(Path(tmp) / "missing"),
                         {"requests": 0, "answered": 0, "unanswered_by_role": {}})

    def test_each_attempt_starts_with_an_empty_store_and_records_its_research(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            stale = out / "PROJ-1" / "agent-research" / "pending"
            stale.mkdir(parents=True)
            (stale / "old.json").write_text(json.dumps({"worker_role": "CODE_RESEARCHER"}), encoding="utf-8")
            seen_env = {}
            base = fake_copilot(True)

            def copilot(cmd, **kwargs):
                seen_env.update(kwargs.get("env") or {})
                self.assertFalse((stale / "old.json").exists(), "the previous attempt's requests are gone")
                return base(cmd, **kwargs)
            with mock.patch.object(runner.subprocess, "run", copilot), \
                    mock.patch.object(runner, "check_outputs", return_value=[]):
                result = runner.process_ticket("PROJ-1", make_config(out), FakeJira(), logging.getLogger("test"),
                                               dry_run=False)
            self.assertEqual(result, "POSTED")
            self.assertEqual(Path(seen_env["AGENT_RESEARCH_STORE"]), out / "PROJ-1" / "agent-research")
            self.assertEqual(common.read_status(out / "PROJ-1")["runtime_research"],
                             {"requests": 0, "answered": 0, "unanswered_by_role": {}})

    def test_skipped_code_or_attachment_researcher_is_a_review_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            prompt = "run the uac-doc-researcher"
            transcript = ticket / "copilot-transcript.md"
            transcript.write_text(prompt + "\ntask agent_type=uac-doc-researcher -> result", encoding="utf-8")
            notes = runner.researcher_run_notes(ticket, prompt, SOURCE, "uac.bot")
            self.assertEqual(len(notes), 2, notes)
            self.assertIn("uac-code-researcher", notes[0])
            self.assertIn("1 attachment(s) from people", notes[1], "the automation's own test plan is not counted")
            transcript.write_text(prompt + "\ntask agent_type=uac-code-researcher -> r\n"
                                  "task agent_type=uac-attachment-researcher -> r", encoding="utf-8")
            self.assertEqual(runner.researcher_run_notes(ticket, prompt, SOURCE, "uac.bot"), [])
            transcript.write_text(prompt, encoding="utf-8")
            (ticket / common.EVIDENCE_FILE).write_text(json.dumps(
                {"preflight": {"clones": {"status": "unavailable"}}}), encoding="utf-8")
            no_attachments = dict(SOURCE, attachments=[])
            self.assertEqual(runner.researcher_run_notes(ticket, prompt, no_attachments, "uac.bot"), [],
                             "no clones and no attachments: nothing for those researchers to do")

    def test_researcher_notes_never_block_posting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            only_doc = fake_copilot(True, transcript="task agent_type=uac-doc-researcher -> result")
            with mock.patch.object(runner.subprocess, "run", only_doc), \
                    mock.patch.object(runner, "check_outputs", return_value=[]):
                result = runner.process_ticket("PROJ-1", make_config(out), FakeJira(), logging.getLogger("test"),
                                               dry_run=False)
            self.assertEqual(result, "POSTED")
            notes = common.read_status(out / "PROJ-1")["review_notes"]
        self.assertTrue(any("uac-code-researcher" in n for n in notes), notes)
        self.assertTrue(any("uac-attachment-researcher" in n for n in notes), notes)

    def test_attachment_without_facts_is_a_review_note_not_a_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ticket = Path(tmp)
            no_facts = [dict(COVERAGE[3])]
            no_facts[0].pop("facts")
            (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(no_facts), encoding="utf-8")
            notes = runner.attachment_fact_notes(ticket, SOURCE, "uac.bot")
            self.assertEqual(notes, ["attachment shot.png lists no facts (configuration, status or log lines it shows)"],
                             "the automation's own test plan needs no facts")
            (ticket / common.SOURCE_COVERAGE_FILE).write_text(json.dumps(COVERAGE), encoding="utf-8")
            self.assertEqual(runner.attachment_fact_notes(ticket, SOURCE, "uac.bot"), [])

    def test_prompt_asks_for_plain_statements_with_technical_values_in_sub_points(self) -> None:
        self.assertIn("in at most two clauses, using only names shown on screen", runner.PROMPT)
        self.assertIn("status codes, file names - go in a sub-point, never in the statement", runner.PROMPT)
        self.assertIn("Shortening never merges, drops or renames a named product item", runner.PROMPT)
        self.assertIn("a comment that names the screen decides which screen it is about", runner.PROMPT)
        self.assertIn("marked not verified, or one citing unrelated pages, can only be a TBD", runner.PROMPT)

    def test_prompt_asks_for_attachment_facts_and_an_observable_result(self) -> None:
        self.assertIn('"facts"', runner.PROMPT)
        self.assertIn("every two seconds", runner.PROMPT)
        self.assertIn("is not proof that the output changed", runner.PROMPT)
        self.assertIn("one item in a job is not a", runner.PROMPT)

    def test_new_miss_probes_are_active(self) -> None:
        lib = common.import_skill_module("miss_probe_library")
        status = {p["probe_id"]: lib.effective_status(p)[0] for p in lib.load_library()}
        for probe in ("MP-018", "MP-019", "MP-020", "MP-021", "MP-022", "MP-023", "MP-024", "MP-025"):
            self.assertEqual(status.get(probe), "ACTIVE", probe)

    def test_attachment_state_probes(self) -> None:
        lib = common.import_skill_module("miss_probe_library")

        def fired(text: str) -> set:
            return {c["probe_id"] for c in lib.candidates_for([("evidence", text)])}
        self.assertIn("MP-023", fired("Repeat with any baseline selected in the preset; it works. No baseline fails."))
        self.assertIn("MP-024", fired("Although only a warning, generation terminates with No output created."))
        self.assertIn("MP-025", fired("Log: Starting regeneration for 5 topic(s) ... Found 0 existing published pages."))
        self.assertFalse({"MP-023", "MP-024", "MP-025"} & fired("Customer has built a temporary workaround listener."),
                         "a workaround alone is not a sibling configuration")

    def test_role_scoped_failure_probe_fires_on_service_user_writes_but_not_on_digit_runs(self) -> None:
        lib = common.import_skill_module("miss_probe_library")

        def fires(text: str) -> bool:
            return any(c["probe_id"] == "MP-022" for c in lib.candidates_for([("description", text)]))
        self.assertTrue(fires("The listener records modifier fmdita-serviceuser; profile reads return HTTP 400."))
        self.assertTrue(fires("Enabling the API returns 403 Forbidden for the org."))
        self.assertFalse(fires("Server author-p38855-e340376-cmstg, build 2026.9.0.413 reproduces it."),
                         "a digit run such as e340376 is not a 403")
        self.assertFalse(fires("Closing this ticket as it is not reproducible with the given steps."))


class PropertyJira:
    """Fake Jira with issue properties and an AC-field changelog."""

    def __init__(self, changes=None):
        self.props: dict = {}
        self.changes = changes or []

    def get_issue_property(self, key, name):
        return self.props.get((key, name))

    def set_issue_property(self, key, name, value):
        self.props[(key, name)] = value

    def get_field(self, key, field, rendered=False):
        return "current text"

    def _json(self, method, path, payload=None):
        return {"changelog": {"histories": [
            {"author": {"name": by}, "created": at, "items": [{"fieldId": "customfield_1", "field": "Acceptance Criteria",
                                                              "fromString": "", "toString": text}]}
            for by, at, text in self.changes]}, "fields": {}}


class ClaudeRewriteTests(unittest.TestCase):
    def test_marked_text_is_a_claude_rewrite_and_anything_else_a_qe_edit(self) -> None:
        jira = PropertyJira()
        record_manual_rewrite.mark(jira, "PROJ-1", ["new text"], "readability rewrite")
        hashes = harvester.rewrite_hashes(jira, "PROJ-1")
        rewrite = {"outcome": "CHANGED", "current_sha256": harvester._sha("new text")}
        self.assertEqual(harvester.edit_origin(rewrite, hashes),
                         {"edit_origin": "CLAUDE_REWRITE", "rewrite_reason": "readability rewrite"})
        qe = {"outcome": "CHANGED", "current_sha256": harvester._sha("a QE's text")}
        self.assertEqual(harvester.edit_origin(qe, hashes), {"edit_origin": "QE_EDIT"})
        self.assertEqual(harvester.edit_origin({"outcome": "ACCEPTED_AS_IS"}, hashes), {})
        self.assertEqual(record_manual_rewrite.mark(jira, "PROJ-1", ["new text"], "again"), [], "marked once")
        self.assertEqual(harvester.rewrite_hashes(object(), "PROJ-1"), {}, "a client without properties")

    def test_history_marks_every_own_write_after_the_runner_post(self) -> None:
        jira = PropertyJira([("uac.bot", "2026-10-01", "runner post"), ("qa.person", "2026-10-02", "qe text"),
                             ("uac.bot", "2026-10-03", "claude rewrite 1"), ("uac.bot", "2026-10-04", "claude rewrite 2")])
        texts = record_manual_rewrite.history_texts(jira, "PROJ-1", "customfield_1", "uac.bot")
        self.assertEqual(texts, ["claude rewrite 1", "claude rewrite 2"])

    def test_report_keeps_claude_rewrites_out_of_the_learning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            learning = Path(tmp) / harvester.LEARNING_DIR
            learning.mkdir()
            base = {"harvested_at": "2026-10-08T03:00:00+0000", "outcome": "CHANGED", "components": ["Review"],
                    "posted_text": "", "criteria": [{"kind": "added", "old": "", "new": "A QE-added check", "reason": ""}],
                    "counts": {}}
            rows = [dict(base, key="PROJ-1", edit_origin="QE_EDIT"),
                    dict(base, key="PROJ-2", edit_origin="CLAUDE_REWRITE", rewrite_reason="readability rewrite",
                         criteria=[{"kind": "added", "old": "", "new": "A Claude-added line", "reason": ""}])]
            (learning / harvester.RECORDS_FILE).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            report = harvester.monthly_report(config, "2026-10").read_text(encoding="utf-8")
        self.assertIn("Claude or Codex rewrites (not counted below, not QE feedback): 1", report)
        self.assertIn("PROJ-2: readability rewrite", report)
        self.assertIn("A QE-added check", report)
        self.assertNotIn("A Claude-added line", report)

    def test_relabel_labels_already_harvested_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            learning = Path(tmp) / harvester.LEARNING_DIR
            learning.mkdir()
            rows = [{"key": "PROJ-1", "outcome": "CHANGED", "current_sha256": harvester._sha("claude text")},
                    {"key": "PROJ-1", "outcome": "CHANGED", "current_sha256": harvester._sha("qe text")},
                    {"key": "PROJ-2", "outcome": "ACCEPTED_AS_IS", "current_sha256": "x"}]
            (learning / harvester.RECORDS_FILE).write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            jira = PropertyJira()
            record_manual_rewrite.mark(jira, "PROJ-1", ["claude text"], "user-directed correction")
            self.assertEqual(harvester.relabel(config, jira, logging.getLogger("test")), 2)
            out = [json.loads(line) for line in (learning / harvester.RECORDS_FILE).read_text(encoding="utf-8").splitlines()]
        self.assertEqual([r.get("edit_origin") for r in out], ["CLAUDE_REWRITE", "QE_EDIT", None])

    def test_relabel_rechecks_qe_edits_marked_later(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = make_config(Path(tmp))
            learning = Path(tmp) / harvester.LEARNING_DIR
            learning.mkdir()
            row = {"key": "PROJ-1", "outcome": "CHANGED", "current_sha256": harvester._sha("late text"),
                   "edit_origin": "QE_EDIT"}
            (learning / harvester.RECORDS_FILE).write_text(json.dumps(row) + "\n", encoding="utf-8")
            jira = PropertyJira()
            logger = logging.getLogger("test")
            self.assertEqual(harvester.relabel(config, jira, logger), 0, "no mark yet: label unchanged")
            record_manual_rewrite.mark(jira, "PROJ-1", ["late text"], "marked after the relabel")
            self.assertEqual(harvester.relabel(config, jira, logger), 1)
            self.assertEqual(harvester.relabel(config, jira, logger), 0)
            out = json.loads((learning / harvester.RECORDS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(out["edit_origin"], "CLAUDE_REWRITE")
        self.assertEqual(out["rewrite_reason"], "marked after the relabel")


if __name__ == "__main__":
    unittest.main()
