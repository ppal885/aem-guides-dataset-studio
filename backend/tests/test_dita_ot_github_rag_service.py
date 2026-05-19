"""Unit tests for DITA-OT GitHub issues RAG helpers."""

import json
import shutil
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services import dita_ot_github_rag_service as svc

_WORKDIR = Path(__file__).resolve().parents[1] / ".test_workdirs"


def _unique_ref_dir() -> Path:
    d = _WORKDIR / f"dita-ot-github-refs-{uuid.uuid4().hex}"
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture(autouse=True)
def _clear_dita_ot_ref_cache():
    yield
    svc._load_reference_issues_cached.cache_clear()


def test_should_query_dita_ot_github_rag_matches_toolkit_terms():
    assert svc.should_query_dita_ot_github_rag("Why does pdf2 fail on ditaval filter?")
    assert svc.should_query_dita_ot_github_rag("DITA-OT transtype html5 chunking")
    assert svc.should_query_dita_ot_github_rag("subject scheme hierarchical filtering propagation")
    assert svc.should_query_dita_ot_github_rag("What is DITA-OT?")
    assert svc.should_query_dita_ot_github_rag("How do I install dita open toolkit")
    assert svc.should_query_dita_ot_github_rag("Which args.xsl.param works with the integrator")
    assert not svc.should_query_dita_ot_github_rag("Summarize these release notes for stakeholders.")


def test_retrieve_curated_reference_when_chroma_empty():
    """Configured JSON references are returned for publishing-like queries even with no index."""
    with (
        patch.object(svc, "is_chroma_available", return_value=True),
        patch.object(svc, "is_embedding_available", return_value=True),
        patch.object(svc, "get_collection_count", return_value=0),
    ):
        rows = svc.retrieve_dita_ot_github_for_query("pdf2 publish error", k=10)
    issue_numbers = [r["issue_number"] for r in rows]
    assert 4768 in issue_numbers
    assert 4769 in issue_numbers
    assert 4713 in issue_numbers
    assert all(str(r["issue_number"]) in r["url"] for r in rows)


def test_retrieve_curated_reference_respects_k():
    with (
        patch.object(svc, "is_chroma_available", return_value=True),
        patch.object(svc, "is_embedding_available", return_value=True),
        patch.object(svc, "get_collection_count", return_value=0),
    ):
        rows = svc.retrieve_dita_ot_github_for_query("ditaval filter", k=1)
    assert len(rows) == 1
    # first entry sorted by issue_number is 4713
    assert rows[0]["issue_number"] == 4713


def test_retrieve_no_rows_when_query_not_in_scope():
    assert svc.retrieve_dita_ot_github_for_query("Summarize these release notes for stakeholders.", k=4) == []


def test_DITA_OT_GITHUB_REFERENCE_ISSUES_getattr_alias():
    assert svc.DITA_OT_GITHUB_REFERENCE_ISSUES == svc.get_dita_ot_github_reference_issues()


def test_override_reference_json_path(monkeypatch):
    work = _unique_ref_dir()
    try:
        p = work / "refs.json"
        p.write_text(
            json.dumps(
                {
                    "references": [
                        {"issue_number": 4700, "title": "Custom title", "snippet": "Custom snippet for tests."},
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DITA_OT_GITHUB_REFERENCE_JSON", str(p))
        refs = svc.get_dita_ot_github_reference_issues()
        assert len(refs) == 1
        assert refs[0]["issue_number"] == 4700
        assert refs[0]["url"].endswith("/4700")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_missing_reference_config_returns_empty(monkeypatch):
    missing = _unique_ref_dir() / "does-not-exist.json"
    monkeypatch.setenv("DITA_OT_GITHUB_REFERENCE_JSON", str(missing))
    assert svc.get_dita_ot_github_reference_issues() == ()


def test_retrieve_empty_when_no_reference_file_and_no_chroma(monkeypatch):
    missing = _unique_ref_dir() / "missing.json"
    monkeypatch.setenv("DITA_OT_GITHUB_REFERENCE_JSON", str(missing))
    with (
        patch.object(svc, "is_chroma_available", return_value=True),
        patch.object(svc, "is_embedding_available", return_value=True),
        patch.object(svc, "get_collection_count", return_value=0),
    ):
        assert svc.retrieve_dita_ot_github_for_query("pdf2 publish error", k=4) == []


def test_reference_config_rejects_non_dita_ot_url(monkeypatch):
    work = _unique_ref_dir()
    try:
        p = work / "refs.json"
        p.write_text(
            json.dumps(
                {
                    "references": [
                        {
                            "issue_number": 1,
                            "title": "bad",
                            "snippet": "bad",
                            "url": "https://evil.example/phish",
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("DITA_OT_GITHUB_REFERENCE_JSON", str(p))
        assert svc.get_dita_ot_github_reference_issues() == ()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_fetch_skips_pull_requests():
    pr_like = {
        "number": 99,
        "title": "Fix foo",
        "state": "open",
        "pull_request": {"url": "https://api.github.com/repos/dita-ot/dita-ot/pulls/99"},
    }
    issue_like = {"number": 100, "title": "Bug bar", "state": "open", "body": "text"}
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = [pr_like, issue_like]
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get.return_value = mock_resp
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_client
    mock_ctx.__exit__.return_value = None

    with patch.object(svc.httpx, "Client", return_value=mock_ctx):
        issues, errs = svc.fetch_dita_ot_issues(max_issues=10, state="all")
    assert errs == []
    assert len(issues) == 1
    assert issues[0]["number"] == 100


@pytest.mark.parametrize("state", ["bad", "pending"])
def test_index_request_invalid_state_rejected(state: str):
    from pydantic import ValidationError

    from app.api.v1.routes.ai_dataset import IndexDitaOtGithubIssuesRequest

    with pytest.raises(ValidationError):
        IndexDitaOtGithubIssuesRequest(state=state)


# ---------------------------------------------------------------------------
# chat_service integration: reference cap and system prompt addendum
# ---------------------------------------------------------------------------


def test_rag_part_dita_ot_github_does_not_truncate_reference_rows_at_1000():
    """Curated reference rows must not be cut at RAG_SNIPPET_CHARS (1000); they use the higher reference cap."""
    from app.services.chat_service import _rag_part_dita_ot_github, RAG_DITA_OT_GH_REFERENCE_CHARS

    long_snippet = "x" * 5000
    mock_row = {
        "url": "https://github.com/dita-ot/dita-ot/issues/4769",
        "title": "Hierarchical filtering test",
        "issue_number": 4769,
        "snippet": long_snippet,
        "source": "dita_ot_github_reference",
    }
    with patch("app.services.chat_service.retrieve_dita_ot_github_for_query", return_value=[mock_row]):
        result = _rag_part_dita_ot_github("child include propagation subject scheme")

    assert result, "Expected non-empty result"
    # snippet must survive beyond the old 1000-char cap
    assert long_snippet[:1001] in result, "Snippet was cut at RAG_SNIPPET_CHARS (1000); expected higher reference cap"
    # snippet must be capped at the reference cap, not pass through unbounded
    assert len(result) < 5000 + 500, "Result unexpectedly long; reference cap may not be applied"
    assert "x" * RAG_DITA_OT_GH_REFERENCE_CHARS in result or len(result) >= RAG_DITA_OT_GH_REFERENCE_CHARS


def test_build_compact_chat_system_prompt_adds_dita_ot_addendum_when_github_issues_present():
    """System prompt must include QA-oriented answer-shape addendum when DITA-OT GitHub context is present."""
    from app.services.chat_service import _build_compact_chat_system_prompt

    rag_with_github = (
        "DITA-OT GITHUB ISSUES (community / toolkit):\n"
        "[1] Hierarchical filtering: child include/flag does not propagate upward\n"
        "https://github.com/dita-ot/dita-ot/issues/4769\n"
        "Some snippet text here."
    )
    prompt = _build_compact_chat_system_prompt(rag_context=rag_with_github)

    assert "### Known issues" in prompt, "Missing '### Known issues' section in DITA-OT GitHub addendum"
    assert "### What's happening" in prompt, "Missing \"### What's happening\" section"
    assert "### How to reproduce" in prompt, "Missing '### How to reproduce' section"
    assert "DITA-OT GITHUB CONTEXT" in prompt, "Missing '# DITA-OT GITHUB CONTEXT' block header"


def test_build_compact_chat_system_prompt_no_dita_ot_addendum_without_github_issues():
    """System prompt must NOT include the DITA-OT addendum when GitHub issues are absent from context."""
    from app.services.chat_service import _build_compact_chat_system_prompt

    prompt_no_github = _build_compact_chat_system_prompt(rag_context="Some AEM guides context here.")
    assert "DITA-OT GITHUB CONTEXT" not in prompt_no_github

    prompt_empty = _build_compact_chat_system_prompt(rag_context="")
    assert "DITA-OT GITHUB CONTEXT" not in prompt_empty
