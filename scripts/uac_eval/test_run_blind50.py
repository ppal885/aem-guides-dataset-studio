"""Offline tests for run_blind50.py (stubbed Copilot CLI)."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_blind50 as rb  # noqa: E402

CONFIG = {"jql": "x", "output_dir": "/tmp", "labels": {"posted": "X"}, "acceptance_criteria_field": "cf",
          "copilot": {"command": "copilot", "add_dirs": ["/repos/a"], "allow_all_tools": True,
                      "deny_tools": ["corp-jira(update_jira_issue)"]}}


def fake_copilot(transcript_extra: str = ""):
    def run(cmd, **kwargs):
        prompt = cmd[cmd.index("-p") + 1]
        uac = Path(re.search(r"^1\. (\S+):", prompt, re.M).group(1))
        uac.write_text("- Acceptance Criteria 01: A works.\n  **Source:** ticket\n"
                       "- Acceptance Criteria 02: B works.\n  **Source:** ticket\n", encoding="utf-8")
        share = next(a.split("=", 1)[1] for a in cmd if a.startswith("--share="))
        Path(share).write_text(prompt + "\nresearch done" + transcript_extra, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, "ok", "")
    return run


class Blind50Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.ticket = root / "set" / "GUIDES-1"
        self.ticket.mkdir(parents=True)
        (self.ticket / "input.json").write_text(json.dumps({"key": "GUIDES-1", "summary": "S"}), encoding="utf-8")
        (self.ticket / "human_uac.md").write_text("secret human UAC", encoding="utf-8")
        self.work = root / "work"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_only_input_is_given_and_jira_is_denied(self) -> None:
        calls = []

        def spy(cmd, **kwargs):
            calls.append(cmd)
            return fake_copilot()(cmd, **kwargs)
        with mock.patch.object(rb.subprocess, "run", spy):
            record = rb.run_ticket(self.ticket, CONFIG, self.work, ["corp-jira"], 60)
        cmd = calls[0]
        self.assertIn("--deny-tool=corp-jira", cmd)
        self.assertIn("--deny-tool=corp-jira(update_jira_issue)", cmd, "the runner's deny list is kept")
        self.assertIn(f"--add-dir={self.work / 'GUIDES-1'}", cmd)
        self.assertNotIn(str(self.ticket), " ".join(cmd), "the blind set folder is never given to Copilot")
        self.assertEqual(sorted(p.name for p in (self.work / "GUIDES-1").iterdir() if p.name == "human_uac.md"), [])
        prompt = cmd[cmd.index("-p") + 1]
        self.assertIn("Acceptance Criteria NN", prompt, "the nightly UAC format is reused")
        self.assertTrue((self.ticket / "skill_uac.md").is_file())
        self.assertEqual(record["criteria"], 2)
        self.assertEqual(record["leaks"], [])
        self.assertEqual(json.loads((self.ticket / "run.json").read_text())["criteria"], 2)

    def test_reading_the_human_uac_or_jira_is_flagged(self) -> None:
        extra = (f"\ncat {self.ticket}/human_uac.md\n### `corp-jira-get_issue`\nGUIDES-1 summary")
        with mock.patch.object(rb.subprocess, "run", fake_copilot(extra)):
            record = rb.run_ticket(self.ticket, CONFIG, self.work, ["corp-jira"], 60)
        self.assertIn("transcript reads the blind set folder", record["leaks"])
        self.assertIn("transcript reads a human_uac.md path", record["leaks"])
        self.assertIn("transcript calls Jira tool corp-jira", record["leaks"])

    def test_mentions_in_repository_code_and_denied_jira_calls_are_not_leaks(self) -> None:
        extra = ("\nticket with input.json, human_uac.md, the drafts\n_FIELDS = {\"human_uac\"}\n"
                 "deny_tools default corp-jira\n### `corp-jira-search_jira_issues` — Failed\npermission denied")
        with mock.patch.object(rb.subprocess, "run", fake_copilot(extra)):
            record = rb.run_ticket(self.ticket, CONFIG, self.work, ["corp-jira"], 60)
        self.assertEqual(record["leaks"], [])

    def test_a_draft_that_copies_the_human_wording_is_flagged(self) -> None:
        (self.ticket / "human_uac.md").write_text("A works when the author saves the topic twice in a row today.",
                                                  encoding="utf-8")
        draft = "- Acceptance Criteria 01: A works when the author saves the topic twice in a row today.\n"
        self.assertTrue(rb.leaks("", "", "GUIDES-1", ["corp-jira"], self.ticket, draft))
        self.assertEqual(rb.leaks("", "", "GUIDES-1", ["corp-jira"], self.ticket, "- Acceptance Criteria 01: B."), [])

    def test_a_tag_keeps_the_baseline_draft(self) -> None:
        (self.ticket / "skill_uac.md").write_text("baseline", encoding="utf-8")
        with mock.patch.object(rb.subprocess, "run", fake_copilot()):
            record = rb.run_ticket(self.ticket, CONFIG, self.work, ["corp-jira"], 60, tag="vm1")
        self.assertEqual((self.ticket / "skill_uac.md").read_text(encoding="utf-8"), "baseline")
        self.assertTrue((self.ticket / "skill_uac_vm1.md").is_file())
        self.assertTrue((self.ticket / "copilot-transcript_vm1.md").is_file())
        self.assertEqual(json.loads((self.ticket / "run_vm1.json").read_text())["criteria"], 2)
        self.assertEqual(record["tag"], "vm1")

    def test_set_dir_inside_the_repo_is_refused(self) -> None:
        config = Path(self.tmp.name) / "config.json"
        config.write_text(json.dumps(CONFIG), encoding="utf-8")
        with self.assertRaises(SystemExit):
            rb.main(["--config", str(config), "--set-dir", str(rb.common.REPO_ROOT / "scripts")])


if __name__ == "__main__":
    unittest.main()
