"""Tests for the knowledge-audit command quality-gate exit codes."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "audit_knowledge_corpora.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("audit_knowledge_corpora_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_high_gate_fails_when_high_gaps_exist(monkeypatch, tmp_path):
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "audit_knowledge_corpora",
        lambda **kwargs: {
            "available": True,
            "summary": {"critical_gap_count": 0, "high_gap_count": 2},
        },
    )
    output = tmp_path / "audit.json"

    assert module.main(["--output", str(output), "--fail-on", "high"]) == 2
    assert output.exists()


def test_cli_none_gate_reports_without_failing(monkeypatch):
    module = _load_script_module()
    monkeypatch.setattr(
        module,
        "audit_knowledge_corpora",
        lambda **kwargs: {
            "available": True,
            "summary": {"critical_gap_count": 3, "high_gap_count": 5},
        },
    )

    assert module.main(["--fail-on", "none"]) == 0
