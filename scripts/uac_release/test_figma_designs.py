"""The runner's read-only Figma design download (offline: fake Figma API, stubbed Copilot)."""
from __future__ import annotations

import io
import json
import logging
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402
import figma_designs  # noqa: E402
import release_dashboard as dashboard  # noqa: E402
import uac_release_runner as runner  # noqa: E402
from test_uac_release import COVERAGE, SOURCE, FakeJira, fake_copilot, make_config  # noqa: E402

DESIGN = "https://www.figma.com/design/AbC123/Upload-dialog?node-id=12-34&t=xyz"
IMAGE_URL = "https://figma-alpha-api.s3.us-west-2.amazonaws.com/images/abc"
FRAME = {
    "id": "12:34", "type": "FRAME", "name": "Upload dialog", "children": [
        {"id": "1", "type": "TEXT", "name": "Title", "characters": "Upload  files"},
        {"id": "2", "type": "INSTANCE", "name": "Button",
         "componentProperties": {"State#1:0": {"type": "VARIANT", "value": "Disabled"}},
         "children": [{"id": "3", "type": "TEXT", "name": "Label", "characters": "Cancel all"}]},
        {"id": "4", "type": "GROUP", "name": "Old banner", "visible": False,
         "children": [{"id": "5", "type": "TEXT", "name": "Hidden", "characters": "never shown"}]},
    ]}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class FakeFigmaApi:
    """Answers the Figma REST paths the client calls and records every request."""

    def __init__(self, fail: dict | None = None) -> None:
        self.requests: list = []
        self.fail = fail or {}

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        url = req.full_url
        for part, code in self.fail.items():
            if part in url:
                raise urllib.error.HTTPError(url, code, "error", {}, None)
        if url == IMAGE_URL:
            return FakeResponse(b"\x89PNG fake")
        if "/v1/images/" in url:
            return FakeResponse(json.dumps({"err": None, "images": {"12:34": IMAGE_URL}}).encode())
        if "/nodes?" in url:
            return FakeResponse(json.dumps({"name": "Guides upload", "lastModified": "2026-11-01T10:00:00Z",
                                            "version": "42", "nodes": {"12:34": {"document": FRAME}}}).encode())
        if "?depth=2" in url:
            return FakeResponse(json.dumps({"name": "Guides upload", "document": {"children": [
                {"id": "0:1", "children": [{"id": "12:34", "type": "FRAME"},
                                           {"id": "9:9", "type": "FRAME", "visible": False}]}]}}).encode())
        raise AssertionError(f"unexpected request {url}")


def client(api: FakeFigmaApi) -> figma_designs.FigmaClient:
    return figma_designs.FigmaClient("figd_test", opener=api)


class FigmaDesignTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.source = dict(SOURCE, comments=SOURCE["comments"] + [
            {"id": "9", "author": "ux.designer", "body": f"Final design: [upload|{DESIGN}]"},
            {"id": "10", "author": "uac.bot", "body": "https://www.figma.com/design/Bot999/x?node-id=1-1"},
        ])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_every_figma_link_form_gives_the_file_key_and_api_node_id(self) -> None:
        self.assertEqual(figma_designs.parse_link(DESIGN), ("AbC123", "12:34"))
        self.assertEqual(figma_designs.parse_link("https://www.figma.com/file/K1/n?node-id=12%3A34"), ("K1", "12:34"))
        self.assertEqual(figma_designs.parse_link("https://www.figma.com/proto/K2/n?node-id=I1-2;3-4"),
                         ("K2", "I1:2;3:4"))
        self.assertEqual(figma_designs.parse_link("https://www.figma.com/design/K3/branch/Br7/n"), ("Br7", ""))
        self.assertEqual(figma_designs.parse_link("https://www.figma.com/email_only"), ("", ""))
        self.assertEqual(figma_designs.parse_link("https://www.figma.com/community/file/123"), ("", ""))

    def test_outline_lists_text_and_variants_and_leaves_out_hidden_layers_and_shapes(self) -> None:
        frame = dict(FRAME, children=FRAME["children"] + [
            {"id": "6", "type": "INSTANCE", "name": "Copy icon", "children": [
                {"id": "7", "type": "VECTOR", "name": "iconFill"}]},
            {"id": "8", "type": "RECTANGLE", "name": "Divider"}])
        text, truncated = figma_designs.outline(frame)
        self.assertFalse(truncated)
        self.assertIn('- TEXT "Title": Upload files', text)
        self.assertIn("{State=Disabled}", text)
        self.assertIn('    - TEXT "Label": Cancel all', text)
        self.assertIn('- INSTANCE "Copy icon"', text, "an icon keeps its name")
        for left_out in ("Old banner", "never shown", "iconFill", "Divider"):
            self.assertNotIn(left_out, text)

    def test_a_ticket_without_a_figma_link_calls_figma_never(self) -> None:
        api = FakeFigmaApi()
        source = dict(SOURCE, comments=SOURCE["comments"] + [
            {"id": "11", "author": "dev.lead", "body": "Log in at https://www.figma.com/email_only first"}])
        entries = figma_designs.collect(source, self.out, "uac.bot", client(api))
        self.assertEqual(entries, [])
        self.assertEqual(api.requests, [], "no design link on the ticket means no Figma request at all")
        self.assertFalse((self.out / figma_designs.FIGMA_DESIGNS_DIR).exists())
        self.assertEqual(json.loads((self.out / figma_designs.FIGMA_DESIGNS_FILE).read_text(encoding="utf-8")), [])

    def test_without_a_token_each_design_is_unreadable_and_nothing_is_requested(self) -> None:
        entries = figma_designs.collect(self.source, self.out, "uac.bot", None)
        self.assertEqual([e["status"] for e in entries], ["UNREADABLE"], "the automation's own comment is ignored")
        self.assertIn("FIGMA_TOKEN", entries[0]["reason"])
        self.assertEqual(len(figma_designs.unread(entries)), 1)

    def test_a_linked_frame_is_saved_as_outline_and_image(self) -> None:
        api = FakeFigmaApi()
        entries = figma_designs.collect(self.source, self.out, "uac.bot", client(api))
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["status"], "READ")
        self.assertEqual(entry["title"], "Guides upload / Upload dialog")
        self.assertIn("Cancel all", Path(entry["outline"]).read_text(encoding="utf-8"))
        self.assertEqual(Path(entry["image"]).read_bytes(), b"\x89PNG fake")
        saved = json.loads((self.out / figma_designs.FIGMA_DESIGNS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(saved, entries)
        self.assertEqual(figma_designs.unread(entries), [])

    def test_access_is_read_only_and_the_token_never_leaves_the_figma_api(self) -> None:
        api = FakeFigmaApi()
        figma_designs.collect(self.source, self.out, "uac.bot", client(api))
        self.assertTrue(all(r.get_method() == "GET" for r in api.requests))
        for req in api.requests:
            to_api = req.full_url.startswith("https://api.figma.com/")
            self.assertEqual(req.get_header("X-figma-token") == "figd_test", to_api, req.full_url)

    def test_a_link_without_node_id_renders_the_first_pages_visible_frames(self) -> None:
        source = {"description": "https://www.figma.com/design/AbC123/Upload-dialog", "comments": []}
        entries = figma_designs.collect(source, self.out, "", client(FakeFigmaApi()))
        self.assertEqual([(e["status"], e["node_id"]) for e in entries], [("READ", "12:34")])

    def test_a_forbidden_file_is_unreadable_with_a_hint(self) -> None:
        entries = figma_designs.collect(self.source, self.out, "uac.bot", client(FakeFigmaApi({"/nodes?": 403})))
        self.assertEqual(entries[0]["status"], "UNREADABLE")
        self.assertIn("HTTP 403", entries[0]["reason"])
        self.assertIn("file_content:read", entries[0]["reason"])

    def test_a_failed_render_keeps_the_outline(self) -> None:
        entries = figma_designs.collect(self.source, self.out, "uac.bot", client(FakeFigmaApi({"/v1/images/": 500})))
        self.assertEqual(entries[0]["status"], "READ")
        self.assertNotIn("image", entries[0])
        self.assertIn("HTTP 500", entries[0]["image_error"])

    def test_links_beyond_the_limit_are_skipped_not_read(self) -> None:
        source = {"description": " ".join(f"https://www.figma.com/design/K{i}/x?node-id=12-34" for i in range(3)),
                  "comments": []}
        api = FakeFigmaApi()
        entries = figma_designs.collect(source, self.out, "", client(api), max_designs=1)
        self.assertEqual([e["status"] for e in entries], ["READ", "SKIPPED", "SKIPPED"])
        self.assertFalse(any("/K1/" in r.full_url or "/K2/" in r.full_url for r in api.requests))


class RunnerFigmaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.config = make_config(self.out)
        self.log = logging.getLogger("test")
        self.source = dict(SOURCE, comments=SOURCE["comments"] + [
            {"id": "9", "author": "ux.designer", "body": f"Final design: {DESIGN}"}])

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _run(self, figma) -> str:
        coverage = COVERAGE + [{"source": "comment:9", "text": f"Final design: {DESIGN}", "disposition": "AC", "ac": 1}]
        with mock.patch.object(runner.subprocess, "run", fake_copilot(True, coverage=coverage)), \
                mock.patch.object(runner, "check_outputs", return_value=[]), \
                mock.patch.object(runner.linked_docs.WikiClient, "from_env", return_value=None), \
                mock.patch.object(runner.figma_designs.FigmaClient, "from_env", return_value=figma):
            return runner.process_ticket("PROJ-1", self.config, FakeJira(source=self.source), self.log, dry_run=False)

    def test_prompt_points_the_session_at_the_downloaded_designs(self) -> None:
        self.assertIn("{figma_path}", runner.PROMPT)
        self.assertIn("do not try to open figma.com", runner.PROMPT)
        self.assertIn("never backend behaviour", runner.PROMPT)

    def test_a_read_design_is_saved_before_copilot_runs(self) -> None:
        self.assertEqual(self._run(client(FakeFigmaApi())), "POSTED")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(status["figma_designs_unread"], [])
        saved = json.loads((self.out / "PROJ-1" / figma_designs.FIGMA_DESIGNS_FILE).read_text(encoding="utf-8"))
        self.assertEqual(saved[0]["status"], "READ")

    def test_an_unreadable_design_still_writes_the_uac_and_is_flagged(self) -> None:
        self.assertEqual(self._run(None), "POSTED", "the UAC is always written")
        status = common.read_status(self.out / "PROJ-1")
        self.assertEqual(len(status["figma_designs_unread"]), 1)
        posted, _ = dashboard.collect_tickets(self.out)
        self.assertIn("linked Figma design not read", posted[0]["where"])


if __name__ == "__main__":
    unittest.main()
