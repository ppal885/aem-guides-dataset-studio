from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_codex_and_claude_evidence_graph_contracts_are_in_parity():
    path = ROOT / "scripts" / "check_test_plan_evidence_graph_parity.py"
    spec = importlib.util.spec_from_file_location("graph_skill_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.check_parity() == []
