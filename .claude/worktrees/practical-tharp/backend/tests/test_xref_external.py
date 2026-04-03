"""Tests for xref to non-DITA resources recipe family."""
import re
import tempfile
from pathlib import Path

import pytest

from app.generator.xref_external import (
    generate_related_links_external_resources,
)
from app.generator.xrefs import (
    generate_xref_external_html,
    generate_xref_external_pdf,
    generate_xref_external_doc,
    generate_xref_external_url,
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


def _assert_xref_format_scope_href(content: bytes, non_dita: bool = True) -> None:
    """Verify xref elements have format, scope, and href to non-DITA resource."""
    text = content.decode("utf-8")
    xref_pattern = re.compile(r'<xref\s+([^>]+)/?>', re.IGNORECASE)
    for match in xref_pattern.finditer(text):
        attrs = match.group(1)
        assert "format=" in attrs, f"xref missing format attribute: {attrs}"
        assert "scope=" in attrs, f"xref missing scope attribute: {attrs}"
        href_match = re.search(r'href=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
        assert href_match, f"xref missing href attribute: {attrs}"
        href = href_match.group(1)
        if non_dita:
            assert not href.lower().endswith(".dita"), f"href should not point to DITA: {href}"
            assert not href.lower().endswith(".ditamap"), f"href should not point to DITA map: {href}"


@pytest.fixture
def config():
    return DatasetConfig(
        name="test",
        seed="test-seed",
        root_folder="/tmp",
        recipes=[],
    )


def test_xref_html_external_format_scope_href(config):
    """xref_external_html: format, scope, href to non-DITA."""
    files = generate_xref_external_html(config, "/tmp")
    assert "topics/xref_external_html.dita" in files
    content = files["topics/xref_external_html.dita"]
    _assert_xref_format_scope_href(content)
    assert "guide.html" in content.decode("utf-8") or "html" in content.decode("utf-8").lower()
    with tempfile.TemporaryDirectory() as tmp:
        _write_and_validate(files, Path(tmp))


def test_xref_pdf_local_format_scope_href(config):
    """xref_external_pdf: format, scope, href to non-DITA."""
    files = generate_xref_external_pdf(config, "/tmp")
    assert "topics/xref_external_pdf.dita" in files
    content = files["topics/xref_external_pdf.dita"]
    _assert_xref_format_scope_href(content)
    assert b'format="pdf"' in content
    assert b'scope="local"' in content
    assert b".pdf" in content
    with tempfile.TemporaryDirectory() as tmp:
        _write_and_validate(files, Path(tmp))


def test_xref_doc_external_format_scope_href(config):
    """xref_external_doc: format, scope, href to non-DITA."""
    files = generate_xref_external_doc(config, "/tmp")
    assert "topics/xref_external_doc.dita" in files
    content = files["topics/xref_external_doc.dita"]
    _assert_xref_format_scope_href(content)
    assert b'format="doc"' in content
    assert b'scope="external"' in content
    assert b".doc" in content
    with tempfile.TemporaryDirectory() as tmp:
        _write_and_validate(files, Path(tmp))


def test_xref_web_external_format_scope_href(config):
    """xref_external_url: format, scope, href to non-DITA."""
    files = generate_xref_external_url(config, "/tmp")
    assert "topics/xref_external_url.dita" in files
    content = files["topics/xref_external_url.dita"]
    _assert_xref_format_scope_href(content)
    assert b'format="html"' in content
    assert b'scope="external"' in content
    assert b"https://" in content
    with tempfile.TemporaryDirectory() as tmp:
        _write_and_validate(files, Path(tmp))


def test_related_links_external_resources_format_scope_href(config):
    """related_links_external_resources: format, scope, href to non-DITA."""
    files = generate_related_links_external_resources(config, "/tmp")
    assert "topics/related_links_external_resources.dita" in files
    content = files["topics/related_links_external_resources.dita"]
    _assert_xref_format_scope_href(content)
    assert "related-links" in content.decode("utf-8").lower()
    with tempfile.TemporaryDirectory() as tmp:
        _write_and_validate(files, Path(tmp))
