"""Tests for conrefend + cyclic references recipe (false duplicate ID warnings)."""
import tempfile
from pathlib import Path

import pytest

from app.generator.conrefend_cyclic import generate_conrefend_cyclic_duplicate_id
from app.jobs.schemas import DatasetConfig
from app.utils.dita_validator import validate_dita_folder


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_conrefend_cyclic_generates_valid_structure(config):
    """Generator produces topic_a, topic_b, map, and README."""
    files = generate_conrefend_cyclic_duplicate_id(config, "/tmp")
    assert "conrefend_cyclic/topics/topic_a.dita" in files or any("topic_a" in k for k in files)
    assert any("topic_b" in k for k in files)
    assert any("main.ditamap" in k or "ditamap" in k for k in files)
    assert any("README" in k for k in files)


def test_conrefend_cyclic_has_conrefend_and_cycle(config):
    """Topic A conrefs to B; Topic B conrefs to A (cycle)."""
    files = generate_conrefend_cyclic_duplicate_id(config, "/tmp")
    topic_a = next((v for k, v in files.items() if "topic_a" in k and k.endswith(".dita")), None)
    topic_b = next((v for k, v in files.items() if "topic_b" in k and k.endswith(".dita")), None)
    assert topic_a and topic_b

    a_str = topic_a.decode("utf-8")
    b_str = topic_b.decode("utf-8")

    assert "conref" in a_str and "conrefend" in a_str
    assert "topic_b.dita" in a_str
    assert "conref" in b_str and "conrefend" in b_str
    assert "topic_a.dita" in b_str


def test_conrefend_cyclic_validates(config):
    """Generated DITA validates (IDs, hrefs, conrefs)."""
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        files = generate_conrefend_cyclic_duplicate_id(config, str(base))
        for rel_path, content in files.items():
            if rel_path.endswith((".dita", ".ditamap")):
                out = base / rel_path
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(content)
        result = validate_dita_folder(base)
        assert "errors" in result
        assert len(result.get("errors", [])) == 0, f"Validation errors: {result.get('errors')}"
