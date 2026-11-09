"""Regression tests for Jira chunking gaps: stale chunk cleanup, comment digest recency,
and linked-issue / attachment context reaching the smart chunk path."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.schemas_jira_enrichment import JiraEnrichedDocument
from app.services import jira_qa_index_service as index_service
from app.services.jira_chunking_service import build_comments_digest, build_smart_chroma_chunks
from app.services.jira_qa_chunking_service import build_jira_qa_chunks


class _FakeChroma:
    """In-memory stand-in for the jira_qa collection: id -> metadata."""

    def __init__(self, stored: dict[str, dict[str, Any]]):
        self.stored = dict(stored)
        self.deleted: list[str] = []
        self.lookup_fails = False

    def ids_where(self, collection: str, where: dict) -> list[str] | None:
        _ = collection
        if self.lookup_fails:
            return None
        return [cid for cid, meta in self.stored.items() if all(meta.get(k) == v for k, v in where.items())]

    def delete(self, collection: str, ids: list[str]) -> bool:
        _ = collection
        for cid in ids:
            self.stored.pop(cid, None)
        self.deleted.extend(ids)
        return True


@pytest.fixture
def fake_chroma(monkeypatch):
    def _install(stored: dict[str, dict[str, Any]]) -> _FakeChroma:
        fake = _FakeChroma(stored)
        monkeypatch.setattr(index_service, "get_document_ids_where", fake.ids_where)
        monkeypatch.setattr(index_service, "delete_documents", fake.delete)
        return fake

    return _install


def _row(chunk_id: str, key: str) -> dict[str, Any]:
    return {"chunk_id": chunk_id, "document": "x", "metadata": {"jira_key": key}}


# --- Items 1 & 2: stale chunks after re-index / delete -------------------------------------


def test_prune_removes_ids_the_rebuild_no_longer_produces(fake_chroma):
    fake = fake_chroma(
        {
            "G-1::problem_chunk::0": {"jira_key": "G-1"},
            "G-1::problem_chunk::1": {"jira_key": "G-1"},  # description got shorter
            "G-1::historical_uac_clause_chunk::7": {"jira_key": "G-1"},  # UAC lost clauses
            "G-1::customer_problem::0": {"jira_key": "G-1"},  # legacy type before smart switch
            "G-2::problem_chunk::1": {"jira_key": "G-2"},  # other issue: untouched
        }
    )
    new_rows = [_row("G-1::problem_chunk::0", "G-1"), _row("G-1::summary_chunk::0", "G-1")]

    removed = index_service.prune_stale_jira_chunks(new_rows)

    assert removed == 3
    assert set(fake.deleted) == {"G-1::problem_chunk::1", "G-1::historical_uac_clause_chunk::7", "G-1::customer_problem::0"}
    assert "G-1::problem_chunk::0" in fake.stored
    assert "G-2::problem_chunk::1" in fake.stored


def test_prune_keeps_chunks_owned_by_other_writers(fake_chroma):
    fake = fake_chroma(
        {
            "G-1::testplan::steps::0": {"jira_key": "G-1"},  # test_plan_index_service
            "G-1::learning_behavior_chunk::0": {"jira_key": "G-1"},  # learning backfill
            "G-1::problem_chunk::1": {"jira_key": "G-1"},
        }
    )

    index_service.prune_stale_jira_chunks([_row("G-1::summary_chunk::0", "G-1")])

    assert fake.deleted == ["G-1::problem_chunk::1"]
    assert "G-1::testplan::steps::0" in fake.stored
    assert "G-1::learning_behavior_chunk::0" in fake.stored


def test_prune_does_nothing_when_lookup_fails(fake_chroma):
    fake = fake_chroma({"G-1::problem_chunk::1": {"jira_key": "G-1"}})
    fake.lookup_fails = True

    assert index_service.prune_stale_jira_chunks([_row("G-1::problem_chunk::0", "G-1")]) == 0
    assert fake.deleted == []


def test_flush_prunes_only_after_successful_upsert(fake_chroma, monkeypatch):
    import numpy as np

    fake = fake_chroma({"G-1::problem_chunk::1": {"jira_key": "G-1"}})
    rows = [_row("G-1::problem_chunk::0", "G-1")]
    monkeypatch.setattr(index_service, "embed_texts_batched", lambda docs, batch_size: np.ones((len(docs), 4)))

    monkeypatch.setattr(index_service, "add_documents", lambda *a, **k: False)
    count, err = index_service._flush_chunk_rows(rows, force_reindex=True)
    assert err == "Chroma upsert failed."
    assert fake.deleted == []  # a failed rebuild must not empty the issue

    monkeypatch.setattr(index_service, "add_documents", lambda *a, **k: True)
    count, err = index_service._flush_chunk_rows(rows, force_reindex=False)
    assert (count, err) == (1, None)
    assert fake.deleted == ["G-1::problem_chunk::1"]


def test_flush_does_not_predelete_when_embedding_fails(fake_chroma, monkeypatch):
    fake = fake_chroma({"G-1::problem_chunk::0": {"jira_key": "G-1"}})
    monkeypatch.setattr(index_service, "embed_texts_batched", lambda docs, batch_size: None)

    _, err = index_service._flush_chunk_rows([_row("G-1::problem_chunk::0", "G-1")], force_reindex=True)

    assert err == "Embedding batch failed."
    assert fake.deleted == []
    assert "G-1::problem_chunk::0" in fake.stored


def test_delete_jira_key_chunks_removes_high_index_chunks(fake_chroma):
    stored = {f"G-1::historical_uac_clause_chunk::{i}": {"jira_key": "G-1"} for i in range(12)}
    stored["G-2::historical_uac_clause_chunk::9"] = {"jira_key": "G-2"}
    stored["G-1::testplan::steps::0"] = {"jira_key": "G-1"}
    fake = fake_chroma(stored)

    assert index_service.delete_jira_key_chunks("G-1") is True

    assert [cid for cid in fake.stored if cid.startswith("G-1::")] == ["G-1::testplan::steps::0"]
    assert "G-2::historical_uac_clause_chunk::9" in fake.stored


def test_delete_jira_key_chunks_falls_back_to_known_slots_without_metadata(fake_chroma):
    fake = fake_chroma({"G-1::summary_chunk::0": {}})  # written without jira_key metadata

    index_service.delete_jira_key_chunks("G-1")

    assert "G-1::summary_chunk::0" in fake.deleted


# --- Item 4: comment digest keeps the newest comments ----------------------------------------


def _comment(i: int, body: str, *, day: int | None = None) -> dict[str, str]:
    d = day if day is not None else (i // 24) + 1
    return {
        "author": "qa",
        "created": f"2026-01-{d:02d}T{i % 24:02d}:00:00.000+0000",
        "body_text": body,
    }


def test_digest_keeps_latest_verification_comment_beyond_forty():
    comments = [_comment(i, f"comment {i} regression still fails on publish in build {i}") for i in range(60)]
    comments.append(
        _comment(60, "Verified fixed in 2026.11; QA confirmed final outcome and closing this ticket", day=28)
    )

    digest = build_comments_digest(comments)

    assert "Verified fixed in 2026.11" in digest
    assert "build 59" in digest
    assert "build 0\n" not in digest and not digest.endswith("build 0")
    assert len(digest) <= 3200


def test_digest_is_chronological_and_never_cuts_a_line():
    comments = [_comment(i, f"regression note {i} " + "detail " * 60) for i in range(30)]

    digest = build_comments_digest(comments, max_chars=1500)
    lines = digest.split("\n")

    assert len(digest) <= 1500
    assert all(line.rstrip().endswith("detail") for line in lines)  # whole comments only
    numbers = [int(line.split("regression note ", 1)[1].split()[0]) for line in lines]
    assert numbers == sorted(numbers)
    assert numbers[-1] == 29


def test_digest_orders_by_timestamp_not_input_order():
    newest = _comment(1, "Verified fix merged; regression confirmed resolved on publish", day=20)
    older = [_comment(i, f"regression still fails on build {i} with more context") for i in range(3)]

    digest = build_comments_digest([newest, *older], max_chars=4000)

    assert digest.split("\n")[-1].endswith("regression confirmed resolved on publish")


def test_digest_scope_comment_cannot_starve_latest_regular_comments():
    scope = _comment(
        0,
        "Scope:\nAdd new conditions via Folder Profile.\n" + "Existing conditions remain unchanged. " * 200,
        day=10,
    )
    latest = _comment(1, "Verified fixed on 2026.11 build; regression confirmed resolved", day=27)

    digest = build_comments_digest([scope, latest])

    assert digest.startswith("[2026-01-10")
    assert "Verified fixed on 2026.11 build" in digest
    assert len(digest) <= 3200


def test_legacy_comments_chunk_keeps_newest_forty(monkeypatch):
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "false")
    comments = [{"author": "a", "created": f"t{i}", "body_text": f"comment number {i}"} for i in range(50)]
    issue = {"fields": {"summary": "S", "description": "D", "labels": [], "components": []}}

    rows = build_jira_qa_chunks("G-1", issue, comments=comments, linked_issues=[])
    doc = next(r["document"] for r in rows if r["metadata"]["chunk_type"] == "comments_discussion")

    assert "comment number 49" in doc
    assert "comment number 9:" not in doc and "comment number 9\n" not in doc


# --- Item 7: linked issues and attachment text reach the smart path --------------------------


def _issue() -> dict[str, Any]:
    return {
        "key": "G-1",
        "fields": {
            "summary": "Native PDF drops glossary",
            "description": "Publishing a bookmap drops glossentry content.",
            "labels": [],
            "components": [],
        },
    }


def _enriched(**kw: Any) -> JiraEnrichedDocument:
    return JiraEnrichedDocument(jira_key="G-1", summary="Native PDF drops glossary", **kw)


def test_smart_path_indexes_linked_issue_summaries():
    rows = build_smart_chroma_chunks(
        "G-1",
        _issue(),
        enriched=_enriched(linked_issue_refs=["G-2", "G-3"]),
        linked_issues=[{"key": "G-2", "summary": "Glossary acronyms missing in PDF"}],
    )
    linked = [r for r in rows if r["metadata"]["chunk_type"] == "linked_issue_chunk"]

    assert len(linked) == 1
    assert "G-2: Glossary acronyms missing in PDF" in linked[0]["document"]
    assert "G-3" in linked[0]["document"]


def test_smart_path_indexes_attachment_text_as_separate_chunks():
    rows = build_smart_chroma_chunks(
        "G-1",
        _issue(),
        enriched=_enriched(attachment_filenames=["publish.log", "topic.dita"]),
        attachment_search_blobs=[
            "publish.log:\nERROR FOP glossentry id=g1 unresolved",
            "topic.dita:\n<glossentry id='g1'/>",
            "   ",
        ],
    )
    att = [r for r in rows if r["metadata"]["chunk_type"] == "attachment_signal_chunk"]
    ids = [r["chunk_id"] for r in att]

    assert len(att) == 3  # filenames chunk + one per non-empty blob
    assert ids == [
        "G-1::attachment_signal_chunk::0",
        "G-1::attachment_signal_chunk::1",
        "G-1::attachment_signal_chunk::2",
    ]
    assert any("ERROR FOP glossentry id=g1 unresolved" in r["document"] for r in att)
    assert len(ids) == len(set(r["chunk_id"] for r in rows if r["chunk_id"] in ids))


def test_build_jira_qa_chunks_forwards_bundle_context_on_smart_path(monkeypatch):
    monkeypatch.setenv("JIRA_SMART_CHUNKING", "true")

    rows = build_jira_qa_chunks(
        "G-1",
        _issue(),
        comments=[],
        linked_issues=[{"key": "G-9", "summary": "Related FOP crash"}],
        attachment_search_blobs=["fop.log:\nNullPointerException in glossary handler"],
        enriched=_enriched(),
    )
    docs = "\n".join(r["document"] for r in rows)

    assert "G-9: Related FOP crash" in docs
    assert "NullPointerException in glossary handler" in docs


def test_fetch_issue_bundle_returns_attachment_text(monkeypatch):
    import app.services.jira_generate_resolve as resolve

    texts = {
        "new.log": "ERROR newest failure",
        "image.png": "",
        "huge.log": "[File too large to inline: huge.log (900 KB) — set JIRA_MAX_ATTACHMENT_BYTES to increase limit]",
        "old.log": "ERROR oldest failure",
    }
    monkeypatch.setattr(resolve, "_read_attachment_text", lambda client, att: texts[att["filename"]])
    monkeypatch.setattr(index_service, "_INDEX_ATTACHMENT_MAX", 2)

    class _Client:
        def get_issue(self, key, fields=None):
            return {
                "key": key,
                "fields": {
                    "attachment": [
                        {"filename": "old.log", "created": "2026-01-01T00:00:00.000+0000"},
                        {"filename": "image.png", "created": "2026-01-04T00:00:00.000+0000"},
                        {"filename": "huge.log", "created": "2026-01-03T00:00:00.000+0000"},
                        {"filename": "new.log", "created": "2026-01-05T00:00:00.000+0000"},
                    ]
                },
            }

        def get_issue_comments(self, key):
            return []

    bundle = index_service.fetch_issue_bundle(_Client(), "G-1")

    assert bundle["attachment_search_blobs"] == ["new.log:\nERROR newest failure", "old.log:\nERROR oldest failure"]


def test_fetch_issue_bundle_attachment_text_can_be_disabled(monkeypatch):
    monkeypatch.setattr(index_service, "_INDEX_ATTACHMENT_TEXT", False)

    class _Client:
        def get_issue(self, key, fields=None):
            return {"key": key, "fields": {"attachment": [{"filename": "a.log"}]}}

        def get_issue_comments(self, key):
            return []

    assert index_service.fetch_issue_bundle(_Client(), "G-1")["attachment_search_blobs"] == []
