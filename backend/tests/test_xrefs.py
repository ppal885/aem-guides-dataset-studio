"""Tests for xrefs recipe family."""
import tempfile
from pathlib import Path

import pytest

from app.generator.xrefs import (
    generate_xref_topic_basic,
    generate_xref_section_target,
    generate_xref_self_section,
    generate_xref_external_pdf,
    generate_xref_broken_href,
)
from app.jobs.schemas import DatasetConfig
from app.utils.dita_validator import validate_dita_folder


def _write_and_validate(files: dict, base: Path) -> dict:
    for rel_path, content in files.items():
        out = base / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(content)
    return validate_dita_folder(base)


@pytest.fixture
def config():
    return DatasetConfig(name="test", seed="test-seed", root_folder="/tmp", recipes=[])


def test_xref_topic_basic(config):
    """xref_topic_basic: link to another topic."""
    files = generate_xref_topic_basic(config, "/tmp")
    assert "topics/source.dita" in files
    assert "topics/target.dita" in files
    assert b'href="target.dita"' in files["topics/source.dita"]
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []


def test_xref_section_target(config):
    """xref_section_target: link to section in another topic."""
    files = generate_xref_section_target(config, "/tmp")
    assert "topics/source.dita" in files
    assert "topics/target.dita" in files
    content = files["topics/source.dita"].decode("utf-8")
    assert 'type="section"' in content
    assert "#" in content and "/" in content
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []


def test_xref_self_section(config):
    """xref_self_section: same-file xref to section."""
    files = generate_xref_self_section(config, "/tmp")
    assert "topics/xref_self_section.dita" in files
    content = files["topics/xref_self_section.dita"].decode("utf-8")
    assert 'type="section"' in content
    assert 'href="#' in content
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []


def test_xref_external_pdf_format_scope(config):
    """xref_external_pdf: format and scope attributes."""
    files = generate_xref_external_pdf(config, "/tmp")
    content = files["topics/xref_external_pdf.dita"]
    assert b'format="pdf"' in content
    assert b'scope="local"' in content
    assert b".pdf" in content


def test_xref_broken_href_negative(config):
    """xref_broken_href: negative case, broken href."""
    files = generate_xref_broken_href(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert len(result["errors"]) >= 1
    assert any("broken" in e.lower() or "missing" in e.lower() or "nonexistent" in e.lower() for e in result["errors"])
