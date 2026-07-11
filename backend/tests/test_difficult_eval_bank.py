import json
from pathlib import Path

from app.evaluation.difficult_eval_bank import EXTENDED_SEED_ENTRIES
from app.evaluation.run_chat_human_eval import build_cases

SEED_PATH = Path(__file__).resolve().parents[1] / "app" / "storage" / "learned_qa_seed.json"


def test_extended_seed_bank_has_92_entries():
    assert len(EXTENDED_SEED_ENTRIES) == 92


def test_learned_qa_seed_has_110_entries():
    items = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    assert len(items) == 110


def test_difficult_eval_suite_has_at_least_110_cases():
    cases = build_cases(limit=0, suite="difficult")
    assert len(cases) >= 110
    domains = {case.domain for case in cases}
    assert "dita_spec" in domains
    assert "dita_ot" in domains
    assert "aem_guides" in domains
