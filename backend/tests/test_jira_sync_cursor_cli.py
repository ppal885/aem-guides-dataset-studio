"""Tests for the Jira sync-cursor VM command."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_jira_sync_cursor.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("bootstrap_jira_sync_cursor_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vm_command_loads_quoted_systemd_environment(monkeypatch, tmp_path):
    module = _load_script_module()
    env_file = tmp_path / ".env.docker"
    env_file.write_text(
        "# service configuration\n"
        'export CHROMA_DB_PATH="/srv/aem data/chroma"\n'
        "JIRA_QA_RAG_PROJECT_KEY=DXML\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("CHROMA_DB_PATH", raising=False)
    monkeypatch.delenv("JIRA_QA_RAG_PROJECT_KEY", raising=False)

    assert module._load_env_file(env_file) is None
    assert os.environ["CHROMA_DB_PATH"] == "/srv/aem data/chroma"
    assert os.environ["JIRA_QA_RAG_PROJECT_KEY"] == "DXML"


def test_vm_command_reports_missing_environment_file(tmp_path):
    module = _load_script_module()

    warning = module._load_env_file(tmp_path / "missing.env")

    assert warning is not None
    assert "env file not found" in warning
