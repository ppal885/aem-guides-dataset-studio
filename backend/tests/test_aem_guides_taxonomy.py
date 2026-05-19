"""AEM Guides taxonomy YAML loader and fallback."""

from __future__ import annotations

from pathlib import Path

from app.core import aem_guides_taxonomy as tax

REQUIRED_DOMAIN_IDS = (
    "editor",
    "publishing",
    "native_pdf",
    "aem_sites",
    "baseline",
    "ditaval",
    "keyref",
    "conref",
    "subject_scheme",
    "assets",
    "image_rendition",
    "glossary",
    "metadata",
    "uuid",
    "post_processing",
    "migration",
    "performance",
)


def test_taxonomy_loads_from_config_file():
    tax.reload_taxonomy()
    assert tax.taxonomy_yaml_path().name == "aem_guides_taxonomy.yaml"
    data = tax.load_taxonomy()
    assert "editor" in data.get("domains", {})
    assert any(dom == "native_pdf" for dom, _kws, _w in tax.get_domain_specs())


def test_required_domains_present_with_keywords_and_test_layers():
    tax.reload_taxonomy()
    data = tax.load_taxonomy()
    domains = data.get("domains") or {}
    for dom_id in REQUIRED_DOMAIN_IDS:
        assert dom_id in domains, f"missing domain {dom_id}"
        spec = domains[dom_id]
        assert isinstance(spec, dict)
        kws = spec.get("keywords") or []
        assert isinstance(kws, list) and len(kws) >= 1, dom_id
        assert "entities" in spec, dom_id
        assert isinstance(spec.get("entities"), list), dom_id
        tl = spec.get("test_layers") or []
        assert isinstance(tl, list) and len(tl) >= 1, dom_id


def test_taxonomy_bullet_summary_non_empty():
    tax.reload_taxonomy()
    s = tax.taxonomy_bullet_summary_for_prompt()
    assert "editor" in s.lower() or "taxonomy domains" in s.lower()
    assert len(s) > 80


def test_taxonomy_fallback_when_yaml_missing(monkeypatch):
    tax.reload_taxonomy()
    monkeypatch.setattr(tax, "taxonomy_yaml_path", lambda: Path("__definitely_missing_aem_taxonomy__.yaml"))
    try:
        tax.reload_taxonomy()
        specs = tax.get_domain_specs()
        dom_ids = [d[0] for d in specs]
        assert "publishing" in dom_ids
        assert "editor" in dom_ids
    finally:
        monkeypatch.undo()
        tax.reload_taxonomy()
