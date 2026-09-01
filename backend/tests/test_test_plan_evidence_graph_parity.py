from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_parity_module():
    path = ROOT / "scripts" / "check_test_plan_evidence_graph_parity.py"
    spec = importlib.util.spec_from_file_location("graph_skill_parity", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_codex_and_claude_evidence_graph_contracts_are_in_parity():
    module = _load_parity_module()
    assert module.check_parity() == []


def test_recursive_inventory_catches_new_contract_files(tmp_path):
    module = _load_parity_module()
    reference = tmp_path / "reference"
    candidate = tmp_path / "candidate"
    new_contract = reference / "scripts" / "new_contract.py"
    new_contract.parent.mkdir(parents=True)
    new_contract.write_text("SCHEMA_VERSION = 'new-v1'\n", encoding="utf-8")
    candidate.mkdir()

    assert module._compare(reference, candidate, "candidate") == [
        "candidate missing file: scripts/new_contract.py"
    ]


def test_required_contract_markers_guard_manifest_v2_and_v3(tmp_path):
    module = _load_parity_module()
    source = tmp_path / "source"
    for relative, markers in module.REQUIRED_CONTRACT_MARKERS.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\n".join(markers))

    assert module._check_required_contracts(source, "source") == []

    run_gates = source / "scripts" / "run_gates.py"
    run_gates.write_bytes(b"aem-guides-evidence-manifest-v1\naem-guides-gate-receipt-v1")
    assert module._check_required_contracts(source, "source") == [
        "source required contract marker missing: "
        "scripts/run_gates.py: aem-guides-evidence-manifest-v2",
        "source required contract marker missing: "
        "scripts/run_gates.py: aem-guides-evidence-manifest-v3",
    ]
