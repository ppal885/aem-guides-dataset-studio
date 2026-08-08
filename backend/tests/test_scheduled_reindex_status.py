"""Regression tests for truthful scheduled Jira reindex status."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from app.services.jira_sync_state import JiraQaIndexSyncState


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "repair_jira_rag_on_vm.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("repair_jira_rag_on_vm_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_main(monkeypatch, result):
    module = _load_script_module()
    payloads = []
    args = SimpleNamespace(
        env_file=Path("unused.env"),
        project="DXML",
        issue="",
        check=False,
    )
    monkeypatch.setattr(module, "parse_args", lambda: args)
    monkeypatch.setattr(module, "load_env_file", lambda _path: None)
    monkeypatch.setattr(module, "readiness", lambda: {"jira_qa_collection_count": 10})
    monkeypatch.setattr(module, "run_index", lambda _args, _project: result)
    monkeypatch.setattr(module, "print_json", payloads.append)
    return module.main(), payloads


def test_structured_search_error_returns_nonzero(monkeypatch):
    exit_code, payloads = _run_main(
        monkeypatch,
        {
            "errors_count": 1,
            "issues_failed": 0,
            "errors": ["search:startAt=0: HTTP 403"],
            "issues_indexed": 0,
        },
    )

    index_payload = next(item for item in payloads if item["phase"] == "index_result")
    assert exit_code == 1
    assert index_payload["success"] is False
    assert index_payload["exit_code"] == 1
    assert "errors_count=1" in index_payload["failure_reasons"]


def test_partial_issue_failure_returns_nonzero(monkeypatch):
    exit_code, payloads = _run_main(
        monkeypatch,
        {
            "errors_count": 0,
            "issues_failed": 1,
            "issues_indexed": 4,
            "errors": [],
        },
    )

    index_payload = next(item for item in payloads if item["phase"] == "index_result")
    assert exit_code == 1
    assert index_payload["failure_reasons"] == ["issues_failed=1"]


def test_clean_empty_incremental_run_remains_successful(monkeypatch):
    exit_code, payloads = _run_main(
        monkeypatch,
        {
            "errors_count": 0,
            "issues_failed": 0,
            "issues_indexed": 0,
            "errors": [],
        },
    )

    index_payload = next(item for item in payloads if item["phase"] == "index_result")
    assert exit_code == 0
    assert index_payload["success"] is True
    assert index_payload["failure_reasons"] == []


def test_sync_state_persistence_failure_is_returned(monkeypatch):
    from app.services import jira_qa_index_service

    monkeypatch.setattr(
        jira_qa_index_service,
        "save_jira_qa_sync_state",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = jira_qa_index_service._persist_jira_qa_sync_state_fields(
        persist_sync_state=True,
        state_id="project:DXML",
        prior_state=JiraQaIndexSyncState(),
        issues_indexed=1,
        errors=[],
        max_updated_seen="2026-08-08T00:00:00Z",
        last_key_ok="DXML-1",
        successful_keys=["DXML-1"],
    )

    assert result["sync_state_id"] == "project:DXML"
    assert result["sync_state_error"] == "Cursor state could not be persisted: disk full"
