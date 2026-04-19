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


def test_bundled_crawl_config_includes_keyboard_shortcuts(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/user-guide/author-content/work-with-editor/web-editor-keyboard-shortcuts"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_aem_asset_search_config(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/aem-asset-search/conf-dita-search"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_doc_state_customization(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/doc-state/customize-doc-state"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_doc_state_filters(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/doc-state/conf-doc-state-filters"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_workspace_settings(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/workspace-configs/workspace-settings"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_custom_indexing_cs(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/aemg-customization/custom-indexing-cs"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_custom_indexing_on_prem(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/aemg-customization/custom-indexing-on-prem"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_component_mapping(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/aemg-customization/component-mapping"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_aem_cloud_service_indexing(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/"
        "experience-manager-cloud-service/content/operations/indexing"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_aem_cloud_service_replication(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/"
        "experience-manager-cloud-service/content/operations/replication"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_special_characters_config(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/editor-configs/conf-special-chars"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_editor_dictionary_and_text_filters(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/editor-configs/customize-aem-default-dictionary",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/editor-configs/conf-text-filters",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_output_generation_config(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/install-conf-guide/output-gen-config/conf-output-generation"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_web_editor_views(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/user-guide/author-content/work-with-editor/web-editor-views"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_apply_citations(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/"
        "using/user-guide/author-content/work-with-editor/web-editor-apply-citations"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_editor_configuration_video(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/"
        "experience-manager-guides-learn/videos/advanced-user-guide/editor-configuration"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_user_settings_preferences_toolbars_video(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = (
        "https://experienceleague.adobe.com/en/docs/"
        "experience-manager-guides-learn/videos/advanced-user-guide/"
        "user-settings-preferences-toolbars"
    )

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_oxygen_cross_referencing(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = "https://www.oxygenxml.com/dita/styleguide/c_Cross-referencing.html"

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_oxygen_object_reference(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_url = "https://www.oxygenxml.com/dita/1.3/specs/langRef/base/object.html"

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = crawl_service._load_crawl_urls()

    assert target_url in urls


def test_bundled_crawl_config_includes_oasis_dita_12_bookmap_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/toc.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bookmap.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/abbrevlist.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/amendments.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/appendices.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/appendix.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/backmatter.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bibliolist.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/bookabstract.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklibrary.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklist.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booklists.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booktitle.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/booktitlealt.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/dedication.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/colophon.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/draftintro.html",
        "https://docs.oasis-open.org/dita/v1.2/os/spec/langref/figurelist.html",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_dita_svg_reference_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://dita-lang.org/dita-techcomm/langref/containers/svg-elements",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/svg-container",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/svgref",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_dita_syntaxdiagram_reference_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://dita-lang.org/dita-techcomm/langref/containers/syntaxdiagram-d",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/delim",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/fragment",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/fragref",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/groupchoice",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/groupcomp",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/groupseq",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/kwd",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/oper",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/repsep",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/synph",
        "https://dita-lang.org/dita-techcomm/langref/technicalcontent/synblk",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_dita_scoped_key_examples(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://dita-lang.org/dita/archspec/base/examples-of-scoped-keys",
        "https://dita-lang.org/dita/archspec/base/example-scoped-keys-for-variable-text",
        "https://dita-lang.org/dita/archspec/base/example-scoped-key-references",
        "https://dita-lang.org/dita/archspec/base/example-nested-key-scopes",
        "https://dita-lang.org/dita/archspec/base/example-key-scopes-omnibus-publications",
        "https://dita-lang.org/dita/archspec/base/example-keys-scope-defining-precedence",
        "https://dita-lang.org/dita/archspec/base/example-scoped-key-name-conflicts",
        "https://dita-lang.org/dita/archspec/base/example-subjectrefs-attribute-with-key-scopes",
        "https://dita-lang.org/dita/archspec/base/context-hooks-for-user-assistance",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_dita_related_links_family_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://dita-lang.org/1.3/dita/langref/base/related-links",
        "https://docs.oasis-open.org/dita/v1.0/langspec/related-links.html",
        "https://docs.oasis-open.org/dita/v1.0/langspec/link.html",
        "https://docs.oasis-open.org/dita/v1.0/langspec/relatedl.html",
        "https://docs.oasis-open.org/dita/v1.0/langspec/linkinfo.html",
        "https://docs.oasis-open.org/dita/v1.0/langspec/linklist.html",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


def test_bundled_crawl_config_includes_oasis_dita_13_metadata_extension_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/foreign.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/data-about.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/boolean.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/data.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/index-base.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/itemgroup.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/no-topic-nesting.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/state.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/unknown.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/base/required-cleanup.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/containers/ditaval-elements.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-val.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-style-conflict.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-prop.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-revprop.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-startflag.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-endflag.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/ditaval/ditaval-alt-text.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/idAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/metadataAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/localizationAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/debugAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/architecturalAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/calsTableAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/displayAttributes.html#display-atts",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/dateAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/linkRelationshipAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html",
        "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/simpletableAttributes.html",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)


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


def test_bundled_crawl_config_includes_requested_authoring_assets_and_ditaval_pages(monkeypatch):
    backend_dir = Path(__file__).resolve().parents[1]
    config_path = backend_dir / "config" / "aem_guides_crawl_urls.json"
    target_urls = {
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/authoring-download-assets",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/ditaval-editor/ditaval-editor",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/ditaval-editor/ditaval-editor#working-with-ditaval-files-in-the-assets-ui",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/author-using-desktop-tools/author-desktop-tools",
    }

    monkeypatch.setattr(crawl_service, "_get_crawl_config_path", lambda: config_path)

    urls = set(crawl_service._load_crawl_urls())

    assert target_urls.issubset(urls)
