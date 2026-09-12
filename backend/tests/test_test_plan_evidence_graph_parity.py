from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest


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


@pytest.fixture
def skill_copies(tmp_path, monkeypatch):
    """Exercise the public check with isolated copies, never installed skills."""
    module = _load_parity_module()
    source = tmp_path / "codex"
    for relative, markers in module.REQUIRED_CONTRACT_MARKERS.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\n".join(markers))
    (source / "SKILL.md").write_bytes(b"Shared authoring contract.\n")
    reference = source / "references" / "nested" / "new-rule.md"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"Preserve evidence authority.\n")
    copies = {"Codex": source}
    for label in ("Claude", "canonical", "Unix", "Windows"):
        copies[label] = tmp_path / label.lower()
        shutil.copytree(source, copies[label])
    monkeypatch.setattr(module, "CODEX", source)
    monkeypatch.setattr(module, "CLAUDE", copies["Claude"])
    monkeypatch.setattr(module, "CANONICAL", copies["canonical"])
    monkeypatch.setattr(module, "TEAM_PACKAGES", (copies["Unix"], copies["Windows"]))
    assert module.check_parity() == []
    return module, copies


@pytest.mark.parametrize("copy", ["Codex", "Claude", "canonical", "Unix", "Windows"])
@pytest.mark.parametrize("relative", ["SKILL.md", "references/nested/new-rule.md"])
def test_one_sided_rule_edit_fails_default_cli(skill_copies, monkeypatch, capsys, copy, relative):
    module, copies = skill_copies
    target = copies[copy] / relative
    target.write_bytes(target.read_bytes() + b"Changed behavior.\n")
    monkeypatch.setattr(sys, "argv", ["check_test_plan_evidence_graph_parity.py"])

    assert module.main() == 1
    output = capsys.readouterr().out
    assert f"content drift: {relative}" in output
    assert "PASS" not in output


@pytest.mark.parametrize("copy", ["Codex", "Claude"])
@pytest.mark.parametrize("change", ["add", "delete"])
def test_one_sided_inventory_change_is_reported(skill_copies, copy, change):
    module, copies = skill_copies
    relative = "references/nested/new-rule.md"
    if change == "add":
        relative = "scripts/data/new-rule.json"
        (copies[copy] / relative).write_bytes(b'{"rule": "new"}\n')
    else:
        (copies[copy] / relative).unlink()

    failures = module.check_parity()
    assert failures
    assert all(relative in failure for failure in failures)
    expected = "missing file" if (copy == "Codex") == (change == "add") else "has extra file"
    assert all(expected in failure for failure in failures)


@pytest.mark.parametrize("copy", ["Codex", "Claude", "canonical", "Unix", "Windows"])
def test_missing_skill_tree_fails(skill_copies, copy):
    module, copies = skill_copies
    shutil.rmtree(copies[copy])
    assert module.check_parity()


def test_only_source_only_mode_excludes_release_copies(skill_copies):
    module, copies = skill_copies
    (copies["Unix"] / "SKILL.md").write_bytes(b"Stale package.\n")
    assert module.check_parity()
    assert module.check_parity(include_packages=False) == []


def test_existing_generated_file_exclusions_do_not_hide_new_rules(skill_copies):
    module, copies = skill_copies
    for relative in ("scripts/__pycache__/cache.pyc", "scripts/cache.pyc", ".DS_Store"):
        target = copies["Claude"] / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"local generated content")
    assert module.check_parity() == []
    (copies["Claude"] / "references" / "extra.md").write_bytes(b"New authoring rule.\n")
    assert module.check_parity() == ["Claude has extra file: references/extra.md"]


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
