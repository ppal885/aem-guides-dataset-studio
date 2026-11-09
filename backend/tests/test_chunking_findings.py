"""Regression tests for the remaining chunking findings: Jira truncation and metadata, stable UAC
clause ids, extraction regexes, header stripping, the PDF and GitHub DITA chunkers, and
evidence-gateway neighbour expansion."""

from __future__ import annotations

import re
from typing import Any

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.evidence_gateway import rag_adapter
from app.evidence_gateway.config import EvidenceGatewaySettings
from app.services import doc_pdf_index_service as pdf
from app.services import github_dita_examples_service as gh
from app.services import jira_chunking_service as jc
from app.services import jira_learning_chunk_service as learning
from app.services.jira_qa_chunking_service import build_jira_qa_chunks
from app.services.jira_qa_index_service import _is_chunker_owned_id

# --- shared text splitter --------------------------------------------------------------------


def _words(n: int, prefix: str = "w") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_split_text_slices_covers_everything_without_mid_word_cuts():
    text = _words(3000)
    slices = jc.split_text_slices(text, 1000, overlap=100)

    assert all(len(piece) <= 1000 for piece in slices)
    covered = set(" ".join(slices).split())
    assert covered == set(text.split())
    assert all(re.fullmatch(r"w\d+", piece.split()[0]) and re.fullmatch(r"w\d+", piece.split()[-1]) for piece in slices)


def test_split_text_slices_terminates_with_oversized_overlap():
    slices = jc.split_text_slices("x" * 5000, 100, overlap=10_000)
    assert "".join(s[:1] for s in slices)  # finished, did not hang
    assert sum(len(s) for s in slices) >= 5000


# --- item 5: long descriptions ---------------------------------------------------------------


def _problem_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    return [c["chunk_text"] for c in chunks if c["chunk_type"] == "problem_chunk"]


def test_problem_chunks_cover_the_whole_long_description():
    body = _words(3000)  # ~17k chars; previously only 5,600 chars were indexed
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", description=body))
    problem = _problem_chunks(chunks)

    assert len(problem) > 2
    assert "w2999" in problem[-1]
    assert set(" ".join(problem).split()) >= set(body.split())
    assert problem[1].startswith(f"Description continued (2/{len(problem)})")


def test_problem_chunk_keeps_line_structure():
    description = "Steps:\n1. Open the map\n2. Publish PDF\n\nThe output is empty."
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", description=description))

    assert "1. Open the map\n2. Publish PDF" in _problem_chunks(chunks)[0]


def test_problem_body_removes_expected_actual_despite_line_breaks():
    expected = "The PDF contains every glossary entry in the right order"
    description = (
        "Intro paragraph.\nThe PDF contains every glossary\nentry in the right order\n"
        "More detail.\nThe PDF contains every glossary entry in the right order"
    )
    enriched = JiraEnrichedDocument(jira_key="G-1", description=description, expected_behavior=expected)

    body = jc._problem_body_without_expected_actual(description, enriched)

    assert "glossary" not in body
    assert "Intro paragraph." in body and "More detail." in body


# --- item 6: oversized single fields ---------------------------------------------------------


def test_oversized_field_is_split_into_parts_not_truncated():
    plan = _words(2500, "step")  # ~20k chars
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", test_plan=plan))
    parts = [c for c in chunks if c["chunk_type"] == "test_evidence_chunk"]

    assert len(parts) > 1
    assert all(len(p["chunk_text"]) <= jc._MAX_CHUNK_CHARS for p in parts)
    assert [p["chunk_part"] for p in parts] == list(range(1, len(parts) + 1))
    assert parts[0]["chunk_text"].startswith(f"[part 1/{len(parts)}]")
    assert "step2499" in parts[-1]["chunk_text"]
    assert not any(p["chunk_truncated"] for p in parts)


def test_part_cap_flags_truncation(monkeypatch):
    monkeypatch.setattr(jc, "_MAX_PARTS_PER_FIELD", 2)
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", test_plan=_words(2500, "step")))
    parts = [c for c in chunks if c["chunk_type"] == "test_evidence_chunk"]

    assert len(parts) == 2
    assert [p["chunk_truncated"] for p in parts] == [False, True]


def test_expected_actual_no_longer_capped_at_2000():
    expected = _words(600, "exp")  # ~3.5k chars
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", expected_behavior=expected))
    ea = " ".join(c["chunk_text"] for c in chunks if c["chunk_type"] == "expected_actual_chunk")

    assert "exp599" in ea


def test_part_metadata_reaches_chroma_rows():
    enriched = JiraEnrichedDocument(jira_key="G-1", test_plan=_words(2500, "step"))
    rows = jc.smart_chunks_to_chroma_rows("G-1", {"fields": {}}, enriched, jc.create_jira_chunks(enriched))
    parts = [r for r in rows if r["metadata"]["chunk_type"] == "test_evidence_chunk"]

    assert parts[0]["metadata"]["chunk_part"] == 1
    assert parts[0]["metadata"]["chunk_part_count"] == len(parts)
    assert len({r["chunk_id"] for r in rows}) == len(rows)


# --- item 8: metadata on the wrong chunk -----------------------------------------------------


def test_blank_learning_chunk_does_not_stamp_previous_chunk(monkeypatch):
    monkeypatch.setattr(
        learning,
        "build_learning_chunk_from_enriched",
        lambda enriched: {"chunk_type": "learning_behavior_chunk", "chunk_text": "   ", "is_verified_fix": True},
    )
    chunks = jc.create_jira_chunks(
        JiraEnrichedDocument(jira_key="G-1", attachment_filenames=["publish.log"])
    )

    assert chunks[-1]["chunk_type"] == "attachment_signal_chunk"
    assert "is_verified_fix" not in chunks[-1]
    assert not any(c["chunk_type"] == "learning_behavior_chunk" for c in chunks)


def test_append_chunk_returns_only_appended_rows():
    out: list[dict[str, Any]] = [{"chunk_type": "summary_chunk"}]
    enriched = JiraEnrichedDocument(jira_key="G-1")

    assert jc._append_chunk(out, chunk_type="x", chunk_text="  ", enriched=enriched) == []
    rows = jc._append_chunk(out, chunk_type="x", chunk_text="body", enriched=enriched)
    assert rows == [out[-1]] and len(out) == 2


# --- item 3: stable UAC clause ids -----------------------------------------------------------


def _uac_doc(clauses: list[str]) -> JiraEnrichedDocument:
    return JiraEnrichedDocument(
        jira_key="GUIDES-38333",
        summary="Native PDF reltable links",
        description="Reltable links are missing from Native PDF output.",
        status="Closed",
        resolution="Fixed",
        labels=["UAC_Done"],
        domain="publishing",
        affected_outputs=["Native PDF"],
        acceptance_criteria="Acceptance Criteria:\nScope: Native PDF\n" + "\n".join(clauses),
    )


def _clause_ids(doc: JiraEnrichedDocument) -> dict[str, str]:
    rows = jc.smart_chunks_to_chroma_rows(doc.jira_key, {"fields": {}}, doc, jc.create_jira_chunks(doc))
    return {
        r["metadata"]["uac_clause_stable_key"]: r["chunk_id"]
        for r in rows
        if r["metadata"]["chunk_type"] == "historical_uac_clause_chunk"
    }


def test_clause_ids_survive_inserting_a_clause():
    a = "Map-level related links must render before topic-level related links."
    b = "Topic-level related links must keep their authored order."
    before = _clause_ids(_uac_doc([a, b]))
    after = _clause_ids(_uac_doc(["Reltable links must appear in the PDF bookmarks.", a, b]))

    assert len(after) == len(before) + 1  # the "Scope:" line is a clause too
    for stable_key, chunk_id in before.items():
        assert after[stable_key] == chunk_id
    assert all(_is_chunker_owned_id(cid, "GUIDES-38333") for cid in after.values())


def test_duplicate_clause_keys_get_unique_ids():
    enriched = JiraEnrichedDocument(jira_key="G-1")
    clause = {"chunk_type": "historical_uac_clause_chunk", "uac_clause_stable_key": "jira:G-1:uac:abc123"}
    smart = [{**clause, "chunk_text": "one"}, {**clause, "chunk_text": "two"}]

    ids = [r["chunk_id"] for r in jc.smart_chunks_to_chroma_rows("G-1", {"fields": {}}, enriched, smart)]

    assert ids == ["G-1::historical_uac_clause_chunk::abc123", "G-1::historical_uac_clause_chunk::abc123-2"]


# --- item 12: reproduction extraction ---------------------------------------------------------


def test_repro_stops_at_expected_heading_without_blank_line():
    description = (
        "Steps to reproduce:\n1. Open map\n2. Publish\nExpected result: PDF has glossary\n"
        "Actual: glossary missing\nEnvironment: AEM 6.5"
    )
    repro = jc._extract_repro_from_description(description)

    assert repro == "1. Open map\n2. Publish"


def test_repro_keeps_step_lines_that_start_with_a_heading_word():
    description = "Steps to reproduce:\n1. Open map\nNote that the page reloads twice\n2. Publish\nExpected: PDF"
    assert jc._extract_repro_from_description(description) == (
        "1. Open map\nNote that the page reloads twice\n2. Publish"
    )


# --- low: customer signal uses cleaned tokens --------------------------------------------------


def test_customer_signal_uses_cleaned_customer_tokens():
    chunks = jc.create_jira_chunks(
        JiraEnrichedDocument(jira_key="G-1", customer_names=["Acme Corp", "Triaged", "Uac_done"])
    )
    text = next(c["chunk_text"] for c in chunks if c["chunk_type"] == "customer_signal_chunk")

    assert text.startswith("Customers: Acme Corp |")


def test_customer_signal_skipped_when_only_junk_tokens():
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", customer_names=["Triaged"]))
    assert not any(c["chunk_type"] == "customer_signal_chunk" for c in chunks)


# --- item 11: legacy expected/actual regexes ---------------------------------------------------


def _legacy_section(description: str, monkeypatch) -> str:
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    issue = {"fields": {"summary": "S", "description": description, "labels": [], "components": []}}
    rows = build_jira_qa_chunks("G-1", issue, comments=[], linked_issues=[])
    return next((r["document"] for r in rows if r["metadata"]["chunk_type"] == "steps_expected_actual"), "")


def test_legacy_regex_ignores_unexpected_and_concurrently(monkeypatch):
    doc = _legacy_section("The dialog throws an unexpected error when concurrently saving.", monkeypatch)
    assert "Expected:" not in doc and "Actual / current:" not in doc


def test_legacy_regex_still_finds_labelled_sections(monkeypatch):
    doc = _legacy_section(
        "Expected: PDF generates.\nActual: error 500.\nSteps to reproduce: 1. open map", monkeypatch
    )
    assert "Expected:\nPDF generates." in doc
    assert "Actual / current:\nerror 500." in doc
    assert "Steps to reproduce:\n1. open map" in doc


def test_legacy_long_windows_have_no_redundant_tail(monkeypatch):
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    issue = {"fields": {"summary": "S", "description": "x" * 9500, "labels": [], "components": []}}
    rows = build_jira_qa_chunks("G-1", issue, comments=[], linked_issues=[])
    parts = [r for r in rows if r["metadata"]["chunk_type"] == "description_long_part"]

    assert len(parts) == 2  # [0, 6000) and [4500, 9500); a third [9000, 9500) would be a subset


# --- low: chunk header stripping -------------------------------------------------------------


def test_chunk_body_strips_smart_header_with_prefix():
    doc = "[G-1 | test_evidence_chunk]\ndomain=publishing | outputs=PDF\n\nPara one.\n\nPara two."
    assert learning._chunk_body(doc) == "Para one.\n\nPara two."


def test_chunk_body_strips_smart_header_without_prefix():
    assert learning._chunk_body("[G-1 | comment_chunk]\n\nDiscussion:\nok") == "Discussion:\nok"


def test_chunk_body_keeps_first_paragraph_when_there_is_no_header():
    doc = "Root cause: the transform dropped reltables.\n\nFix merged in 2026.11."
    assert learning._chunk_body(doc) == doc


# --- items 9, 10, 15, 16: PDF chunker -------------------------------------------------------


def _page(num: int, text: str) -> dict[str, Any]:
    return {"page_num": num, "text": text, "has_text": True}


def test_pdf_chunks_carry_exactly_their_own_pages():
    p1 = " ".join(f"one{i}." for i in range(400))
    p2 = " ".join(f"two{i}." for i in range(400))

    for chunk in pdf._chunk_pages([_page(1, p1), _page(2, p2)], {}):
        expected = {1} if "one" in chunk["text"] else set()
        expected |= {2} if "two" in chunk["text"] else set()
        assert set(chunk["pages"]) == expected, (chunk["pages"], chunk["text"][:40], chunk["text"][-40:])


def test_pdf_short_tail_section_is_kept():
    chunks = pdf._chunk_pages([_page(1, "A" * 100 + " end."), _page(2, "INTRO\nshort tail here")], {})
    text = "\n".join(c["text"] for c in chunks)

    assert "short tail here" in text
    assert 2 in chunks[-1]["pages"]


def test_pdf_detects_mid_page_heading():
    body = "Body sentence about publishing. " * 5
    page = f"{body}\n2.3 Configure Output Presets\nPreset text explains output settings. " * 1 + "x " * 60
    chunks = pdf._chunk_pages([_page(1, page)], {})

    assert [c["section"] for c in chunks] == ["", "2.3 Configure Output Presets"]


def test_pdf_numbered_steps_are_not_headings():
    assert not pdf._is_heading_line("1. Click Save.")
    assert not pdf._is_heading_line("10 items were found.")
    assert pdf._is_heading_line("4 Publishing")
    assert pdf._is_heading_line("APPENDIX")


def test_pdf_large_overlap_setting_does_not_hang(monkeypatch):
    monkeypatch.setattr(pdf, "CHUNK_OVERLAP", 10_000)
    chunks = pdf._chunk_pages([_page(1, " ".join(f"s{i}." for i in range(2000)))], {})

    assert len(chunks) > 1
    assert "s1999." in chunks[-1]["text"]


def test_pdf_table_rows_already_in_text_are_not_duplicated():
    text = "Name Value\nalpha 1\nbeta 2"
    tables = [[["Name", "Value"], ["alpha", "1"], ["gamma", "3"]]]

    assert pdf._table_lines_missing_from_text(text, tables) == ["gamma | 3"]


# --- items 15, 17: GitHub DITA chunker -------------------------------------------------------


def _dita(paragraphs: int) -> str:
    body = "\n".join(f'  <p id="p{i}">Paragraph {i} explains <b>bold</b> content.</p>' for i in range(paragraphs))
    return f'<topic id="t"><title>Glossary</title>\n<body>\n{body}\n</body>\n</topic>'


def test_github_chunks_never_cut_inside_a_tag(monkeypatch):
    monkeypatch.setattr(gh, "CHUNK_SIZE", 400)
    monkeypatch.setattr(gh, "CHUNK_OVERLAP", 60)
    chunks = gh._chunk_document(_dita(80))

    assert len(chunks) > 3
    for chunk in chunks:
        assert chunk.rfind("<") < chunk.rfind(">"), chunk[-40:]  # no dangling open tag at the end
        assert not re.match(r"^[^<]*>", chunk), chunk[:40]  # no dangling tag tail at the start
    assert "p79" in chunks[-1]


def test_github_chunker_terminates_when_overlap_exceeds_size(monkeypatch):
    monkeypatch.setattr(gh, "CHUNK_SIZE", 200)
    monkeypatch.setattr(gh, "CHUNK_OVERLAP", 500)
    chunks = gh._chunk_document(_dita(40))

    assert "p39" in chunks[-1]


def test_github_later_chunks_name_their_file():
    first = gh._with_chunk_context("<p/>", path="topics/gloss.dita", title="Glossary", index=0, total=3)
    later = gh._with_chunk_context("<p/>", path="topics/gloss.dita", title="Glossary", index=1, total=3)

    assert first == "<p/>"
    assert later.startswith("<!-- Glossary (topics/gloss.dita), part 2 of 3 -->\n")


# --- item 14: neighbour expansion -------------------------------------------------------------


def test_neighbours_from_another_document_are_skipped(monkeypatch):
    rows = {
        "ex_4": {"id": "ex_4", "document": "a.dita end", "metadata": {"path": "a.dita"}},
        "ex_5": {"id": "ex_5", "document": "b.dita start", "metadata": {"path": "b.dita"}},
        "ex_6": {"id": "ex_6", "document": "b.dita middle", "metadata": {"path": "b.dita"}},
    }
    monkeypatch.setattr(
        rag_adapter,
        "_locate_chunk",
        lambda chunk_id, corpora, settings: ("dita_spec", rows[chunk_id]) if chunk_id in rows else None,
    )

    chunks, _ = rag_adapter.fetch_chunks(
        ["ex_5"], neighbor_window=1, authorized_corpora={"dita_spec"}, settings=EvidenceGatewaySettings()
    )

    assert {c.chunk_id for c in chunks} == {"ex_5", "ex_6"}


def test_neighbour_ids_keep_zero_padding():
    assert rag_adapter._neighbor_ids("chunk_007", 1) == ["chunk_006", "chunk_008"]
    assert rag_adapter._neighbor_ids("chunk_7", 1) == ["chunk_6", "chunk_8"]


# --- Talos review follow-ups ---------------------------------------------------------------


def test_markup_cut_ignores_greater_than_inside_quoted_attribute():
    # Talos: '<p outputclass="' + 210 'a' + '>\n' + 20 'b' + '">Text</p>' + trailing text.
    doc = '<p outputclass="' + "a" * 210 + ">\n" + "b" * 20 + '">Text</p>' + " trailing words here" * 20
    window = doc[:400]
    attribute_end = doc.index('">Text')

    cut = gh._markup_aware_cut(window)

    assert not (0 < cut <= attribute_end), (cut, window[max(0, cut - 5) : cut + 5])


def test_xml_cut_map_skips_comments_cdata_and_quoted_values():
    text = "<a x='1>2'>t<!-- a > b --><![CDATA[ c > d ]]>u</a>"
    outside, tag_end = gh._xml_cut_map(text)

    real_ends = {i for i in range(len(text) + 1) if tag_end[i]}
    assert real_ends == {
        text.index("'>t") + 2,  # end of <a x='1>2'>
        text.index("-->") + 3,
        text.index("]]>") + 3,
        len(text),  # </a>
    }
    assert not outside[text.index("2'")]  # inside the quoted value
    assert not outside[text.index(" b -->")]  # inside the comment


def test_github_chunks_never_split_quoted_attribute(monkeypatch):
    monkeypatch.setattr(gh, "CHUNK_SIZE", 300)
    monkeypatch.setattr(gh, "CHUNK_OVERLAP", 40)
    para = '<p outputclass="' + "a" * 120 + '>\n' + "b" * 30 + '">Text body here.</p>\n'
    chunks = gh._chunk_document("<body>\n" + para * 12 + "</body>")

    for chunk in chunks:
        # every chunk boundary is outside markup: no chunk ends inside an attribute value
        outside, _ = gh._xml_cut_map(chunk)
        assert outside[len(chunk)], chunk[-60:]


def test_pdf_table_row_kept_when_only_a_substring_is_on_the_page():
    # Talos: "timeout 100" in the text must not suppress the row ["timeout", "10"].
    assert pdf._table_lines_missing_from_text("timeout 100", [[["timeout", "10"]]]) == ["timeout | 10"]


def test_pdf_table_row_kept_when_cells_appear_out_of_order_or_apart():
    text = "10 is the timeout\nretries 3"
    tables = [[["timeout", "10"], ["retries", "3"]]]

    assert pdf._table_lines_missing_from_text(text, tables) == ["timeout | 10"]


def test_problem_truncation_flagged_when_only_first_slice_is_kept(monkeypatch):
    # Talos: JIRA_SMART_MAX_PARTS_PER_FIELD=1 truncated the description without the flag.
    monkeypatch.setattr(jc, "_MAX_PARTS_PER_FIELD", 1)
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", description=_words(3000)))
    problem = [c for c in chunks if c["chunk_type"] == "problem_chunk"]

    assert len(problem) == 1
    assert problem[0].get("chunk_truncated") is True


def test_problem_truncation_flag_lands_on_last_retained_row(monkeypatch):
    monkeypatch.setattr(jc, "_MAX_PARTS_PER_FIELD", 3)
    chunks = jc.create_jira_chunks(JiraEnrichedDocument(jira_key="G-1", description=_words(3000)))
    problem = [c for c in chunks if c["chunk_type"] == "problem_chunk"]

    assert len(problem) == 3
    assert [bool(c.get("chunk_truncated")) for c in problem] == [False, False, True]


def test_legacy_expected_heading_with_content_on_next_line(monkeypatch):
    # Talos: "Expected result:\nPDF generates." stopped matching.
    doc = _legacy_section(
        "Expected result:\nPDF generates.\nActual result:\nerror 500.\nSteps to reproduce: 1. open map",
        monkeypatch,
    )
    assert "Expected:\nPDF generates." in doc
    assert "Actual / current:\nerror 500." in doc


def test_legacy_empty_expected_section_does_not_capture_next_heading(monkeypatch):
    doc = _legacy_section("Expected:\nActual: error 500.", monkeypatch)
    assert "Expected:" not in doc
    assert "Actual / current:\nerror 500." in doc


def test_legacy_comments_keep_newest_within_document_budget(monkeypatch):
    # Talos: 40 long comments were cut from the front at 12,000 chars, dropping the newest.
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    comments = [
        {"author": "qa", "created": f"2026-01-{i + 1:02d}", "body_text": f"comment {i} " + "detail " * 280}
        for i in range(45)
    ]
    comments[-1]["body_text"] = "Verified fixed in 2026.11 build; closing. " + "detail " * 200
    issue = {"fields": {"summary": "S", "description": "D", "labels": [], "components": []}}

    rows = build_jira_qa_chunks("G-1", issue, comments=comments, linked_issues=[])
    doc = next(r["document"] for r in rows if r["metadata"]["chunk_type"] == "comments_discussion")

    assert len(doc) <= 12000
    assert "Verified fixed in 2026.11 build" in doc
    assert "comment 43 " in doc
    assert "comment 0 " not in doc
    assert doc.rstrip().endswith("detail")  # the newest comment is whole, not cut


def test_pdf_short_final_section_keeps_its_own_section_name():
    # Talos: a short final "INTRO" section was merged into the previous section's chunk.
    first = "1 Overview\n" + "Overview body sentence about publishing output. " * 4
    chunks = pdf._chunk_pages(
        [_page(1, first), _page(2, "INTRO\nThis section has a brief instruction.")], {}
    )

    assert [c["section"] for c in chunks] == ["1 Overview", "INTRO"]
    assert chunks[-1]["text"] == "INTRO\nThis section has a brief instruction."
    assert chunks[-1]["pages"] == [2]
    assert "brief instruction" not in chunks[0]["text"]


def test_pdf_short_mid_document_section_is_not_relabelled_as_the_next_one():
    long_body = "Body sentence explaining configuration in detail. " * 4
    pages = [_page(1, "1 Setup\n" + long_body + "\n2 Notes\nKeep backups.\n3 Publish\n" + long_body)]

    chunks = pdf._chunk_pages(pages, {})
    by_section = {c["section"]: c["text"] for c in chunks}

    assert by_section["2 Notes"] == "2 Notes\nKeep backups."
    assert "Keep backups." not in by_section["3 Publish"]


def test_pdf_short_tail_of_same_section_still_merges():
    body = "Same section body sentence with enough words to stand alone. " * 3
    chunks = pdf._chunk_pages([_page(1, "1 Setup\n" + body), _page(2, "tail words only")], {})

    assert len(chunks) == 1
    assert chunks[0]["text"].endswith("tail words only")
    assert chunks[0]["pages"] == [1, 2]


def test_legacy_steps_do_not_stop_at_prose_starting_with_a_heading_word(monkeypatch):
    # Talos: a step line beginning with "Current" ended the steps after the first step.
    doc = _legacy_section(
        "Steps to reproduce:\n1. Open the map\nCurrent selection must remain unchanged while loading\n2. Publish",
        monkeypatch,
    )
    assert (
        "Steps to reproduce:\n1. Open the map\nCurrent selection must remain unchanged while loading\n2. Publish"
        in doc
    )


def test_legacy_steps_still_stop_at_heading_labels(monkeypatch):
    for heading in ("Expected:", "Actual result", "Current behaviour:", "Observed"):
        doc = _legacy_section(f"Steps to reproduce:\n1. Open the map\n{heading}\nPDF fails", monkeypatch)
        assert doc.split("Steps to reproduce:\n", 1)[1] == "1. Open the map", heading
