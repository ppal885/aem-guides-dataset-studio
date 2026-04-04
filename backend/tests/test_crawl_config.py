from pathlib import Path

from app.services import crawl_service


def test_bundled_crawl_config_includes_customized_map_templates(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/user-guide/author-content/map-editor/create-maps-customized-templates"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_map_console_baseline_v2_and_reports(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)
    urls = crawl_service._load_crawl_urls()
    assert any("web-editor-baseline-v2" in u for u in urls)
    assert any("web-editor-baseline" in u and "web-editor-baseline-v2" not in u for u in urls)
    assert any("open-files-map-console" in u for u in urls)
    assert any("reports-aem-guide/reports-intro" in u for u in urls)
    assert any("reports-aem-guide/reports-web-editor" in u for u in urls)
    assert any("work-with-editor/web-editor-features" in u for u in urls)
