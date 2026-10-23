"""Tests for the shared Acceptance Criteria grammar and the Vision comment classification."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import uac_field_parser as parser  # noqa: E402
import uac_release_runner as runner  # noqa: E402

UAC_MD = """- Acceptance Criteria 01: Export to PDF works when the document name contains & or #.
    - Name with &: the PDF opens.
    - Name with #: the PDF opens.
    **Source:** Jira description, line 2.
- Acceptance Criteria 02: Export to PDF with a plain name still works as before.
    **Source:** Experience League, Publishing outputs.
    **TBD:** Should the file name keep the special characters or encode them?
"""

UAC_MD_WITH_NOTE = ("Note: A fix is proposed in a linked pull request but is not merged; the criteria below "
                    "describe the expected behaviour.\n" + UAC_MD)

# What jira_safe_text.jira_field_body makes of UAC_MD (wiki markup), before any QE edit.
FIELD_WIKI = """* *Acceptance Criteria 01:* Export to PDF works when the document name contains & or #.
** Name with &: the PDF opens.
** Name with #: the PDF opens.
** *Source:* Jira description, line 2.
* *Acceptance Criteria 02:* Export to PDF with a plain name still works as before.
** *Source:* Experience League, Publishing outputs.
** *TBD:* Should the file name keep the special characters or encode them?
"""

FIELD_WIKI_WITH_NOTE = ("_Note: A fix is proposed in a linked pull request but is not merged; the criteria below "
                        "describe the expected behaviour._\n" + FIELD_WIKI)

# QE added a criterion by hand (AC-NN label, no bold) and struck the second one through.
FIELD_WIKI_EDITED = """* *Acceptance Criteria 01:* Export to PDF works when the document name contains & or #.
** *Source:* Jira description, line 2.
* -*Acceptance Criteria 02:* Export to PDF with a plain name still works as before.- (covered by regression suite)
** *Source:* Experience League, Publishing outputs.
- AC-03: Export to PDF shows a clear error when the name is empty.
"""

VISION_COMMENTS = [
    "[Vision] Needs review — xmleditor · via Copilot\n\n*Outcome*: A PR was opened, but needs review — please "
    "review before merging.\n\n*PR*: xmleditor #8516\n*Fix*: Open PR already exists for this ticket "
    "(https://git.example.test/org/xmleditor/pull/8516) and the ticket is unchanged since it was opened.\n\n"
    "— Vision · GUIDES-00001 · Needs review",
    "[Vision] Checked PR for feedback — xmleditor #8516 · via Copilot\n\n*Outcome*: All reviews are APPROVED — "
    "no feedback to address\n\n— Vision · GUIDES-00001 · review feedback",
    "[Vision] PR created — xmleditor · via Copilot\n\n*Outcome*: A pull request is ready for your review.\n\n"
    "*PR*: xmleditor #8516\n*Root cause*: Backend rejects non-GUID renames with HTTP 400.",
    "h3. [Vision] Needs review — xmleditor · via Copilot",
]


class MarkdownGrammarTests(unittest.TestCase):
    def test_lines_blocks_and_count(self):
        self.assertEqual(parser.ac_count_md(UAC_MD), 2)
        lines = parser.ac_lines_md(UAC_MD)
        self.assertEqual(sorted(lines), [1, 2])
        self.assertTrue(lines[1].startswith("Export to PDF works"))
        blocks = parser.ac_blocks_md(UAC_MD)
        self.assertIn("**TBD:**", blocks[2])
        self.assertNotIn("Acceptance Criteria 02", blocks[1])

    def test_statements_and_cases_in_order(self):
        self.assertEqual(parser.statements_and_cases_md(UAC_MD), [
            "Export to PDF works when the document name contains & or #.",
            "Name with &: the PDF opens.",
            "Name with #: the PDF opens.",
            "Export to PDF with a plain name still works as before.",
        ])

    def test_note_line_is_not_a_criterion(self):
        self.assertEqual(parser.ac_count_md(UAC_MD_WITH_NOTE), 2)
        self.assertEqual(len(parser.NOTE_LINE_MD.findall(UAC_MD_WITH_NOTE)), 1)

    def test_block_regex_stops_at_out_of_scope(self):
        text = UAC_MD + "Out of scope:\n- Export to Word.\n"
        self.assertNotIn("Export to Word", parser.ac_blocks_md(text)[2])

    def test_empty_uac(self):
        self.assertEqual(parser.ac_count_md(""), 0)
        self.assertEqual(parser.ac_lines_md("Nothing here"), {})
        self.assertEqual(parser.statements_and_cases_md(""), [])


class JiraFieldGrammarTests(unittest.TestCase):
    def test_field_as_posted(self):
        criteria = parser.parse_field(FIELD_WIKI)
        self.assertEqual([c["number"] for c in criteria], [1, 2])
        # The harvester keeps the bold marker's trailing "* " in Source; consumers use ``text``, not ``source``.
        self.assertTrue(criteria[0]["source"].endswith("Jira description, line 2."), criteria[0]["source"])
        self.assertTrue(criteria[1]["tbd"].endswith("keep the special characters or encode them?"), criteria[1]["tbd"])
        self.assertEqual(parser.ac_texts_only(FIELD_WIKI), [
            "Export to PDF works when the document name contains & or #.",
            "Export to PDF with a plain name still works as before.",
        ])
        self.assertTrue(parser.has_open_decision(FIELD_WIKI))

    def test_note_line_in_field_is_skipped(self):
        self.assertEqual(parser.ac_texts_only(FIELD_WIKI_WITH_NOTE), parser.ac_texts_only(FIELD_WIKI))

    def test_qe_edits_added_and_struck(self):
        texts = parser.ac_texts_only(FIELD_WIKI_EDITED)
        self.assertEqual(texts, [
            "Export to PDF works when the document name contains & or #.",
            "Export to PDF shows a clear error when the name is empty.",
        ])
        with_struck = parser.ac_texts_only(FIELD_WIKI_EDITED, include_struck=True)
        self.assertEqual(len(with_struck), 3)
        self.assertIn("plain name still works", with_struck[1])
        self.assertFalse(parser.has_open_decision(FIELD_WIKI_EDITED))

    def test_label_variants(self):
        for label in ("*Acceptance Criteria 1:*", "*Acceptance Criteria 01:*", "AC-01:", "Acceptance Criterion 1:"):
            self.assertEqual(parser.ac_texts_only(f"* {label} The criterion."), ["The criterion."], label)

    def test_field_without_criteria(self):
        self.assertEqual(parser.ac_texts_only(""), [])
        self.assertEqual(parser.ac_texts_only("Some free text QE typed, no criteria yet."), [])

    def test_round_trip_from_markdown_through_jira_field_body(self):
        jira_text = common.import_skill_module("jira_safe_text")
        field = jira_text.jira_field_body(UAC_MD_WITH_NOTE)
        self.assertEqual(parser.ac_texts_only(field), parser.ac_texts_only(FIELD_WIKI))
        self.assertTrue(runner.field_rendered(field, "<b>Acceptance Criteria 01:</b>"))


class VisionCommentTests(unittest.TestCase):
    def test_every_observed_vision_shape_is_a_bot_notice(self):
        for body in VISION_COMMENTS:
            self.assertTrue(runner._BOT_COMMENT.match(runner._words(body)), body[:40])

    def test_human_comments_are_not_bot_notices(self):
        for body in ("Please confirm the expected behaviour for names with #.",
                     "Vision of this feature was discussed; see the design document.",
                     "The vision statement in the PRD is outdated."):
            words = runner._words(body)
            self.assertFalse(runner._BOT_COMMENT.match(words) and words.startswith("vision needs"), body)
        # Only a comment that *starts* with the Vision tag is a bot notice.
        self.assertFalse(runner._BOT_COMMENT.match(runner._words("Please confirm. [Vision] says otherwise.")))

    def test_vision_comment_never_counts_as_a_closure_request(self):
        source = {"comments": [
            {"author": "qe", "body": "Please confirm else we should close?"},
            {"author": "dev", "body": VISION_COMMENTS[0]},
        ]}
        request = runner.closure_request(source, own_name="automation")
        self.assertIsNotNone(request)
        self.assertEqual(request["author"], "qe")
        self.assertIsNone(runner.closure_request({"comments": [{"author": "dev", "body": VISION_COMMENTS[2]}]}))


if __name__ == "__main__":
    unittest.main()
