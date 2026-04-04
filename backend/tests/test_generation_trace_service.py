import json
import tempfile
from pathlib import Path

from app.services.generation_trace_service import (
    gather_scenario_xml_snapshot,
    infer_trace_outcome,
    write_generation_trace_file,
)
from app.core.schemas_generation_trace import GenerationRunTrace


def test_infer_trace_outcome_success():
    assert infer_trace_outcome(True, "llm_generated_dita", {}) == "success"


def test_infer_trace_outcome_deterministic():
    assert (
        infer_trace_outcome(False, "table_semantics_reference", {"recipes_executed": ["x"]})
        == "deterministic_recipe_failed"
    )


def test_gather_scenario_xml_snapshot():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        d = tmp_path / "t.dita"
        d.write_text("<topic id=\"a\"><title>T</title></topic>", encoding="utf-8")
        paths, combined = gather_scenario_xml_snapshot(tmp_path)
        assert paths
        assert "topic" in combined


def test_write_generation_trace_file():
    with tempfile.TemporaryDirectory() as td:
        tmp_path = Path(td)
        tr = GenerationRunTrace(trace_id="tid", jira_id="J-1", outcome="validation_failed")
        p = write_generation_trace_file(tmp_path, tr)
        assert p.exists()
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data["trace_id"] == "tid"
        assert "construct_demonstration_reminder" in data
