"""Tests for Jira shortcut resolution before generate-from-text."""
import pytest

from app.services.jira_generate_resolve import (
    extract_issue_key_from_shortcut,
    is_jira_shortcut_input,
    resolve_text_for_generate_from_text,
)


def test_is_shortcut_issue_key_only():
    assert is_jira_shortcut_input("GUIDES-19555") is True
    assert is_jira_shortcut_input("guides-19555") is True
    assert is_jira_shortcut_input("  AEM-1  ") is True


def test_is_shortcut_browse_url():
    assert (
        is_jira_shortcut_input("https://jira.corp.adobe.com/browse/GUIDES-19555") is True
    )
    assert is_jira_shortcut_input("http://example.atlassian.net/browse/PROJ-123") is True


def test_not_shortcut_long_paste():
    long_text = "x" * 3000
    assert is_jira_shortcut_input(long_text) is False
    assert is_jira_shortcut_input("Some text\nGUIDES-1\nmore") is False


def test_extract_key_from_variants():
    assert extract_issue_key_from_shortcut("GUIDES-19555") == "GUIDES-19555"
    assert extract_issue_key_from_shortcut("guides-99") == "GUIDES-99"
    assert (
        extract_issue_key_from_shortcut(
            "https://jira.example.com/browse/DXML-42?focusedCommentId=1"
        )
        == "DXML-42"
    )
    assert (
        extract_issue_key_from_shortcut(
            "https://jira.example.com/secure/Dashboard.jspa?selectedIssue=ABC-7"
        )
        == "ABC-7"
    )
    assert extract_issue_key_from_shortcut("no key here") is None


def test_resolve_without_jira_config(monkeypatch):
    monkeypatch.delenv("JIRA_BASE_URL", raising=False)
    monkeypatch.delenv("JIRA_URL", raising=False)
    text, jid, warn = resolve_text_for_generate_from_text("GUIDES-19555")
    assert text == "GUIDES-19555"
    assert jid is None
    assert warn is None


def test_build_evidence_pack_forced_key():
    from app.api.v1.routes.ai_dataset import _build_evidence_pack_from_text

    run_id = "abc-def-000"
    blob = (
        "Issue Key: X\n\nIssue Summary\nHello summary\n\nIssue Description\nBody line 1\nBody line 2\n"
    )
    pack = _build_evidence_pack_from_text(blob, run_id, forced_issue_key="GUIDES-9")
    p = pack["primary"]
    assert p["issue_key"] == "GUIDES-9"
    assert "Hello summary" in p["summary"]
    assert "Body line 1" in p["description"]
