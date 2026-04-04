"""
Tests for same-file xref, conref and conrefend support.
"""
import tempfile
from pathlib import Path

import pytest

from app.generator.generate import safe_join
from app.generator.self_conref import (
    generate_self_conref_basic_paragraph,
    generate_self_conref_section,
    generate_self_conrefend_range_paragraphs,
    generate_self_conrefend_range_section_content,
)
from app.generator.self_xref import (
    generate_self_xref_section,
    generate_self_xref_list_item,
    generate_self_xref_figure,
    generate_self_xref_table,
    generate_self_conref_basic,
    generate_self_conrefend_range,
    generate_self_xref_conref_positive_minimal,
    generate_self_xref_conref_boundary,
    generate_self_xref_conref_negative,
)
from app.jobs.schemas import DatasetConfig
from app.utils.dita_validator import validate_dita_folder


def _write_and_validate(files: dict, dita_root: Path) -> dict:
    """Write files under dita_root and run validator. Keys may be absolute or relative to dita_root."""
    dita_root = dita_root.resolve()
    for key, content in files.items():
        path = Path(key)
        if not path.is_absolute():
            path = dita_root / path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return validate_dita_folder(dita_root)


@pytest.fixture
def config():
    return DatasetConfig(
        name="test",
        seed="test-seed",
        root_folder="/tmp",
        recipes=[],
    )


def test_valid_self_xref_section(config):
    """Valid same-file xref to section passes validation."""
    files = generate_self_xref_section(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        result = _write_and_validate(files, Path(tmp))
    assert result["errors"] == []


def test_self_xref_section_minimal_deterministic(config):
    """Self xref section produces minimal dataset with deterministic IDs."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files1 = generate_self_xref_section(config, base_str)
        files2 = generate_self_xref_section(config, base_str)
        assert files1 == files2
        key = safe_join(base_str, "topics/self_xref_section.dita")
        assert key in files1
        content = files1[key].decode("utf-8")
        assert 'type="section"' in content
        assert 'href="#' in content
        assert "<section" in content


def test_self_xref_conref_positive_minimal(config):
    """Positive minimal: valid same-file xref and conref passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_conref_positive_minimal(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_self_xref_conref_boundary(config):
    """Boundary: multiple xrefs and conref passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_conref_boundary(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_self_xref_conref_negative(config):
    """Negative: broken xref and conref fail validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_conref_negative(config, base_str)
        result = _write_and_validate(files, root)
    assert len(result["errors"]) >= 1


def test_valid_self_xref_li(config):
    """Valid same-file xref to list item passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_list_item(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_valid_self_xref_fig(config):
    """Valid same-file xref to figure passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_figure(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_valid_self_xref_table(config):
    """Valid same-file xref to table passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_xref_table(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_valid_self_conref_basic(config):
    """Valid same-file conref basic passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_conref_basic(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_valid_self_conrefend_range(config):
    """Valid same-file conrefend range passes validation."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        base_str = safe_join(str(root), "")
        files = generate_self_conrefend_range(config, base_str)
        result = _write_and_validate(files, root)
    assert result["errors"] == []


def test_valid_same_file_conref_paragraph(config):
    """Valid same-file conref to paragraph passes validation."""
    files = generate_self_conref_basic_paragraph(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = _write_and_validate(files, base)
    assert result["errors"] == []
    assert len(result["warnings"]) == 0 or all("Broken" not in w for w in result["warnings"])


def test_valid_same_file_conref_section(config):
    """Valid same-file conref to section passes validation."""
    files = generate_self_conref_section(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = _write_and_validate(files, base)
    assert result["errors"] == []


def test_valid_same_file_conrefend_range(config):
    """Valid same-file conref+conrefend range passes validation."""
    files = generate_self_conrefend_range_paragraphs(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = _write_and_validate(files, base)
    assert result["errors"] == []


def test_valid_same_file_conrefend_range_section(config):
    """Valid same-file conrefend range of section content passes validation."""
    files = generate_self_conrefend_range_section_content(config, "/tmp")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        result = _write_and_validate(files, base)
    assert result["errors"] == []


def test_missing_target_fails():
    """Topic with conref to non-existent target fails validation."""
    doctype = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    topic = f'''<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="t1" xml:lang="en">
  <title>Test</title>
  <body>
    <p id="p1">Content</p>
    <p conref="#t1/nonexistent">Conref to missing</p>
  </body>
</topic>'''
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "topics").mkdir()
        (base / "topics" / "bad.dita").write_text(topic)
        result = validate_dita_folder(base)
    assert len(result["errors"]) >= 1
    assert any("missing" in e.lower() or "fragment" in e.lower() for e in result["errors"])


def test_invalid_conrefend_order_fails():
    """conrefend with end before start in document order fails."""
    doctype = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    topic = f'''<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="t1" xml:lang="en">
  <title>Test</title>
  <body>
    <p id="end_first">End block (appears first)</p>
    <p id="start_second">Start block (appears second)</p>
    <sectiondiv conref="#t1/start_second" conrefend="#t1/end_first"/>
  </body>
</topic>'''
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "topics").mkdir()
        (base / "topics" / "bad_order.dita").write_text(topic)
        result = validate_dita_folder(base)
    assert len(result["errors"]) >= 1
    assert any("order" in e.lower() or "before" in e.lower() for e in result["errors"])


def test_self_loop_fails():
    """Element with conref pointing to itself fails validation."""
    doctype = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    topic = f'''<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="t1" xml:lang="en">
  <title>Test</title>
  <body>
    <p id="self_loop" conref="#t1/self_loop">Self loop</p>
  </body>
</topic>'''
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "topics").mkdir()
        (base / "topics" / "self_loop.dita").write_text(topic)
        result = validate_dita_folder(base)
    assert len(result["errors"]) >= 1
    assert any("self" in e.lower() or "loop" in e.lower() for e in result["errors"])


def test_duplicate_id_still_fails():
    """Duplicate ids in folder still fail validation."""
    doctype = '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "topic.dtd">'
    topic1 = f'''<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="dup" xml:lang="en">
  <title>Topic 1</title>
  <body><p>Content</p></body>
</topic>'''
    topic2 = f'''<?xml version="1.0" encoding="UTF-8"?>
{doctype}
<topic id="dup" xml:lang="en">
  <title>Topic 2</title>
  <body><p>Content</p></body>
</topic>'''
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "topics").mkdir()
        (base / "topics" / "a.dita").write_text(topic1)
        (base / "topics" / "b.dita").write_text(topic2)
        result = validate_dita_folder(base)
    assert len(result["errors"]) >= 1
    assert any("duplicate" in e.lower() or "dup" in e.lower() for e in result["errors"])
