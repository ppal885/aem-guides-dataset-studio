"""Tests for topicmeta recipe family."""
import tempfile
from pathlib import Path

import pytest

from app.generator.topicmeta_recipes import (
    generate_topicmeta_keywords,
    generate_topicmeta_keywords_indexterm,
    generate_topicmeta_cascade,
    generate_topicmeta_negative,
)
from app.jobs.schemas import DatasetConfig
from app.utils.dita_validator import validate_dita_folder


def _write_and_validate(files: dict, base: Path) -> dict:
    """Write files to base and run validator."""
    for rel_path, content in files.items():
        out = base / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    return validate_dita_folder(base)


@pytest.fixture
def config():
    return DatasetConfig(
        name="test",
        seed="test-seed",
        root_folder="/tmp",
        recipes=[],
    )


def test_topicmeta_keywords(config):
    """Topicmeta with keywords passes validation."""
    files = generate_topicmeta_keywords(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []
    assert "topicmeta" in files["maps/topicmeta_keywords.ditamap"].decode("utf-8").lower()
    assert "keywords" in files["maps/topicmeta_keywords.ditamap"].decode("utf-8").lower()


def test_topicmeta_keywords_indexterm(config):
    """Topicmeta with keywords and indexterm passes validation."""
    files = generate_topicmeta_keywords_indexterm(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []
    assert "indexterm" in files["maps/topicmeta_keywords_indexterm.ditamap"].decode("utf-8").lower()


def test_topicmeta_cascade(config):
    """Topicmeta cascade via nested topicref passes validation."""
    files = generate_topicmeta_cascade(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []
    assert "author" in files["maps/topicmeta_cascade.ditamap"].decode("utf-8").lower()


def test_topicmeta_negative(config):
    """Invalid topicmeta placement fails validation."""
    files = generate_topicmeta_negative(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert len(result["errors"]) >= 1
    assert any("topicmeta" in e.lower() for e in result["errors"])
