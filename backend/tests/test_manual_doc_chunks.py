from pathlib import Path

import pytest

from app.services import doc_retriever_service


@pytest.fixture(autouse=True)
def _disable_required_semantic_retrieval_by_default(monkeypatch):
    monkeypatch.setenv("AEM_GUIDES_REQUIRE_SEMANTIC_RETRIEVAL", "false")


def test_manual_svg_reference_chunks_are_present():
    path = Path(__file__).resolve().parents[1] / "storage" / "manual_aem_guides_doc_chunks.json"
    text = path.read_text(encoding="utf-8")

    assert "dita-techcomm/langref/containers/svg-elements" in text
    assert "dita-techcomm/langref/technicalcontent/svg-container" in text
    assert "dita-techcomm/langref/technicalcontent/svgref" in text


def test_manual_syntaxdiagram_reference_chunks_are_present():
    path = Path(__file__).resolve().parents[1] / "storage" / "manual_aem_guides_doc_chunks.json"
    text = path.read_text(encoding="utf-8")

    assert "dita-techcomm/langref/containers/syntaxdiagram-d" in text
    assert "dita-techcomm/langref/technicalcontent/delim" in text
    assert "dita-techcomm/langref/technicalcontent/fragment" in text
    assert "dita-techcomm/langref/technicalcontent/fragref" in text
    assert "dita-techcomm/langref/technicalcontent/groupchoice" in text
    assert "dita-techcomm/langref/technicalcontent/groupcomp" in text
    assert "dita-techcomm/langref/technicalcontent/groupseq" in text
    assert "dita-techcomm/langref/technicalcontent/kwd" in text
    assert "dita-techcomm/langref/technicalcontent/oper" in text
    assert "dita-techcomm/langref/technicalcontent/repsep" in text
    assert "dita-techcomm/langref/technicalcontent/synph" in text
    assert "dita-techcomm/langref/technicalcontent/synblk" in text


def test_manual_dita_ot_troubleshooting_chunks_are_present():
    path = Path(__file__).resolve().parents[1] / "storage" / "manual_aem_guides_doc_chunks.json"
    text = path.read_text(encoding="utf-8")

    assert "https://www.dita-ot.org/dev/parameters/parameters-base" in text
    assert "https://www.dita-ot.org/dev/parameters/dita-command-arguments" in text
    assert "--args.draft=yes" in text
    assert "https://www.dita-ot.org/dev/topics/error-messages" in text
    assert "https://www.dita-ot.org/dev/topics/dita-command-help" in text
    assert "https://www.dita-ot.org/dev/topics/pdf2-creating-change-bars" in text
    assert "https://www.dita-ot.org/dev/topics/pdf-themes" in text


def test_manual_content_reuse_report_chunk_is_present():
    path = Path(__file__).resolve().parents[1] / "storage" / "manual_aem_guides_doc_chunks.json"
    text = path.read_text(encoding="utf-8")

    assert "reports-aem-guide/reports-content-reuse" in text
    assert "Average Content Reuse = Content Reuse Instances / Total Topic Count" in text
    assert "post-processing workflows must be enabled" in text


def test_manual_aem_guides_curated_url_chunks_are_present():
    path = Path(__file__).resolve().parents[1] / "storage" / "manual_aem_guides_doc_chunks.json"
    text = path.read_text(encoding="utf-8")

    expected_urls = [
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/about-aemg/intro",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/about-aemg/aemg-works-features/intro-how-dxml-works",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/appendix/troubleshooting/session-timeout-prompt",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/manage-metadata/manage-metadata",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/manage-metadata/web-editor-smart-tagging",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/map-console-overview",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/open-files-map-console",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-intro",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-web-editor",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-ditamap",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-content-reuse",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-convertion-status",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-reverted-file-version-history",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-first-time",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor#create-a-translation-project",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor#add-the-translation-rules",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-modified-topics-6234",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/web-editor-manage-output-presets",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-variables",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/pass-metadata-dita-ot",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-map-collection-output-generation",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-new-map-collection-output-generation",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-create-edit-preset",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-use-condition-presets",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-conditional-attribute-profiling",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/aemg-integrations/conf-new-baseline-on-prem",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2#key-enhancements-introduced-in-the-new-baseline",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/new-baseline-migration-faq",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing#create-a-baseline",
        "https://www.oxygenxml.com/dita/1.3/specs/archSpec/base/document-type-shells.html",
        "https://www.oxygenxml.com/dita/1.3/specs/archSpec/base/dita-metadata.html",
        "https://www.oxygenxml.com/dita/1.3/specs/archSpec/base/metadata-elements.html",
    ]

    for url in expected_urls:
        assert url in text


def test_retrieve_relevant_docs_uses_manual_aem_guides_feature_chunks(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    checks = [
        (
            "AEM Guides smart tagging XML Keyword Extract Run Post Process Properties page",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/manage-metadata/web-editor-smart-tagging",
        ),
        (
            "AEM Guides Map Console Reports Topic List Metadata Multimedia Broken links",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-web-editor",
        ),
        (
            "DITA metadata topicmeta lockmeta map metadata overrides topic metadata",
            "https://www.oxygenxml.com/dita/1.3/specs/archSpec/base/dita-metadata.html",
        ),
        (
            "DITA document-type shell structural domain constraint modules topic nesting",
            "https://www.oxygenxml.com/dita/1.3/specs/archSpec/base/document-type-shells.html",
        ),
        (
            "AEM Guides Conversion Status Report Word IDML DocBook Success Failed Queued conversion log",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-convertion-status",
        ),
        (
            "AEM Guides Revert Version Logs Revert From Revert To Show Logs version history report",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-reverted-file-version-history",
        ),
        (
            "AEM Guides translation human machine Microsoft Translator translation provider imported assets",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation",
        ),
        (
            "AEM Guides translation first time cloud services connector DITA Map console Ready to Review",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-first-time",
        ),
        (
            "AEM Guides Map Console translation XLIFF SRX Mark In Sync Force Sync project cleanup",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor",
        ),
        (
            "Translation project language groups Apply Send for Translation Project Title XLIFF scoping target folders",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor#create-a-translation-project",
        ),
        (
            "AEM Guides Segmentation Rules eXchange SRX en-US.srx ar-AE.srx Translation SRX location",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translate-documents-web-editor#add-the-translation-rules",
        ),
        (
            "AEM Guides translate modified topics Out of Sync Mark in Sync Accept Translation Reject Translation DAM",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-modified-topics-6234",
        ),
        (
            "publishing output preset duplicate delete Options dropdown top bar preset management",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-create-edit-preset",
        ),
        (
            "AEM Guides Global Folder Profile output presets Add to folder profile Default PDF View log related maps",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/web-editor-manage-output-presets",
        ),
        (
            "AEM Guides output variables map_filename map_title preset_name language_code path_after_langfolder dc:title PDF File Name",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-variables",
        ),
        (
            "AEM Guides pass metadata DITA-OT metadataList dc:description dc:language dc:title docstate File properties Config.Manager 2502",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/pass-metadata-dita-ot",
        ),
        (
            "AEM Guides Map Collection Generate Selected Generate All Modified Preset Language Configure Metadata Remove From Collection",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-map-collection-output-generation",
        ),
        (
            "AEM Guides New map collection Beta Generated history Published history Fetch presets Select available translations Publish to Preview",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output-use-new-map-collection-output-generation",
        ),
        (
            "AEM Guides condition presets Include Exclude Passthrough Flag Add all Output presets",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-use-condition-presets",
        ),
        (
            "AEM Guides conditional attribute profiling Folder Profile Name Value Label Properties tab",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-conditional-attribute-profiling",
        ),
        (
            "AEM Guides baseline Manual update Automatic update Pick Automatically Export Baseline exact copy label",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline",
        ),
        (
            "AEM Guides new baseline Beta Bulk Processor migration Rebuild Download GUID dependency preview",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2",
        ),
        (
            "AEM Guides new baseline key enhancements incremental loading GUID search dependency impact row-level deterministic save REST API Java SDK",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline-v2#key-enhancements-introduced-in-the-new-baseline",
        ),
        (
            "New Baseline migration FAQ invalid references reltable DIRECT scope peer rollback working copy On-Premise 5.2",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/new-baseline-migration-faq",
        ),
        (
            "AEM Guides On-Premise enable faster Baseline v2 ConfigManager enable.baseline.v2 configMgr Save",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/aemg-integrations/conf-new-baseline-on-prem",
        ),
        (
            "AEM Guides Map dashboard baseline Label Version on Browse All Topics Add Labels translated baseline",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing",
        ),
        (
            "Create a baseline Assets UI Baselines page Baseline Name Set the version based on Label Version on Save",
            "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing#create-a-baseline",
        ),
    ]

    for query, expected_url in checks:
        docs = doc_retriever_service.retrieve_relevant_docs(query, k=8)
        urls = {item.get("url") for item in docs}
        assert expected_url in urls


def test_retrieve_relevant_docs_uses_manual_content_reuse_report(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "AEM Guides Content Reuse Report Number of Times Reused Referenced By CSV",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/reports-aem-guide/reports-content-reuse" in urls


def test_retrieve_relevant_docs_uses_manual_reports_decision_guide(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Which AEM Guides report should I use for broken links content reuse conversion logs and reverted versions?",
        k=8,
    )
    urls = {item.get("url") for item in docs}

    assert "manual://aem-guides/reports-suite-decision-guide" in urls


def test_retrieve_relevant_docs_uses_manual_translation_decision_guide(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Explain AEM Guides translation setup human vs machine XLIFF SRX Out of Sync Ready to Review",
        k=8,
    )
    urls = {item.get("url") for item in docs}

    assert "manual://aem-guides/translation-workflow-decision-guide" in urls


def test_retrieve_relevant_docs_uses_manual_dita_ot_pdf_themes(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT PDF themes --theme com.elovirta.pdf YAML",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/topics/pdf-themes" in urls


def test_retrieve_relevant_docs_uses_manual_dita_ot_change_bars(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT PDF revision bars changebar revprop DITAVAL",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/topics/pdf2-creating-change-bars" in urls


def test_retrieve_relevant_docs_uses_manual_dita_ot_args_draft(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT PDF draft-comment argument args.draft",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/parameters/parameters-base" in urls


def test_retrieve_relevant_docs_uses_manual_svg_chunks(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs("svg-container svgref svg", k=5)
    urls = {item.get("url") for item in docs}

    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/svg-container" in urls
    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/svgref" in urls


def test_retrieve_relevant_docs_uses_manual_syntaxdiagram_chunks(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs("syntaxdiagram groupchoice groupseq kwd repsep", k=10)
    urls = {item.get("url") for item in docs}

    assert "https://dita-lang.org/dita-techcomm/langref/containers/syntaxdiagram-d" in urls
    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/groupchoice" in urls
    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/groupseq" in urls
    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/kwd" in urls


def test_retrieve_relevant_docs_uses_manual_synph_chunk(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs("synph syntax phrase inline syntax", k=5)
    urls = {item.get("url") for item in docs}

    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/synph" in urls


def test_retrieve_relevant_docs_uses_manual_synblk_chunk(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs("synblk block syntax syntaxdiagram", k=5)
    urls = {item.get("url") for item in docs}

    assert "https://dita-lang.org/dita-techcomm/langref/technicalcontent/synblk" in urls


def test_retrieve_relevant_docs_uses_manual_dita_ot_error_messages(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT DOTJ conkeyref error messages build log",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/topics/error-messages" in urls


def test_retrieve_relevant_docs_uses_manual_dita_command_help(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do I access help for dita command options and subcommands?",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/topics/dita-command-help" in urls


def test_retrieve_relevant_docs_uses_manual_dita_command_arguments(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT dita command --input --format transtype output directory propertyfile resource filter",
        k=8,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/parameters/dita-command-arguments" in urls


def test_retrieve_relevant_docs_can_filter_to_experience_league_and_rerank_translation_docs(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://dita-lang.org/dita/archspec/base/context-hooks-for-user-assistance",
                "title": "Context hooks for user assistance",
                "content": "Accessibility and translation. Context hooks for user assistance.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation",
                "title": "Content translation overview | Adobe Experience Manager",
                "content": (
                    "Content translation overview. Adobe Experience Manager Guides supports human and machine "
                    "translation workflows and translation status tracking."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/translate-content/translation-first-time",
                "title": "Best practices for content translation | Adobe Experience Manager",
                "content": (
                    "Start the translation job. Create a translation project, add content, start the translation "
                    "job, and review translated output."
                ),
            },
        ],
    )

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How does the translation workflow work in AEM Guides?",
        k=3,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert docs
    assert docs[0]["url"].startswith("https://experienceleague.adobe.com/")
    assert "translation" in docs[0]["title"].lower() or "translation" in docs[0]["snippet"].lower()
    assert all("experienceleague.adobe.com" in str(item.get("url") or "") for item in docs)


def test_retrieve_relevant_docs_prefers_authoring_pages_for_create_topic_or_map_question(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/generate-output/single-topic-publishing/generate-output-aem-site",
                "title": "Incremental output generation | Adobe Experience Manager",
                "content": "Generate article-based output from the Map console. Select the topics that you want to regenerate.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/knowledge-base/kb-articles/authoring/webeditor/content-reusability-in-aem-guides",
                "title": "DITA content reuse in AEM Guides | Adobe Experience Manager",
                "content": "<map id=\"ABC_manual\"><topicref href=\"sample.dita\"/></map> Here the topic path is changed during reuse.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                "title": "Create topics | Adobe Experience Manager",
                "content": "In the Repository panel, select the New file icon and then select Topic from the dropdown menu.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                "title": "Create a map | Adobe Experience Manager",
                "content": "Select Create > DITA Map, specify the map title and template, and then select Create.",
            },
        ],
    )

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do you create a topic or map in AEM Guides?",
        k=4,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    urls = [str(item.get("url") or "") for item in docs]

    assert urls[0] in {
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
    }
    assert set(urls[:2]) == {
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
        "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
    }


def test_retrieve_relevant_docs_prefers_precise_authoring_chunks_over_generic_create_noise(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                "title": "Create topics | Adobe Experience Manager",
                "content": (
                    "Create topics from the Editor. In the Repository panel, select the New file icon and then select Topic from the dropdown menu."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-create-topics",
                "title": "Create topics | Adobe Experience Manager",
                "content": (
                    "In the Assets UI, navigate to the location where you want to create the topic. To create a new topic, select Create > DITA Topic."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                "title": "Create a map | Adobe Experience Manager",
                "content": (
                    "Select Create > DITA Map. On the Blueprint page, select the type of map templates you want to use and select Next."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                "title": "Create a map | Adobe Experience Manager",
                "content": (
                    "The New map dialog box is displayed. In the New map dialog box, provide the title and file name."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/create-preview-topics/web-editor-preview-topics",
                "title": "Preview a topic | Adobe Experience Manager",
                "content": "Perform the following steps to create a branch, revert to a version, and maintain subsequent versions of a topic.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/work-with-editor/web-editor-content-snippet",
                "title": "Insert a content snippet from your data source | Adobe Experience Manager",
                "content": "Create a topic using the topic generator and connected data sources.",
            },
        ],
    )

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do you create a topic or map in AEM Guides?",
        k=4,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    snippets = " \n ".join(str(item.get("snippet") or "") for item in docs)
    assert "Repository panel" in snippets
    assert "Create > DITA Topic" in snippets
    assert "Select Create > DITA Map" in snippets
    assert "topic generator" not in snippets.lower()
    assert "create a branch" not in snippets.lower()


def test_retrieve_relevant_docs_prefers_baseline_pages_over_document_state_noise(monkeypatch):
    monkeypatch.setenv("AEM_GUIDES_REQUIRE_SEMANTIC_RETRIEVAL", "false")
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/doc-state/customize-doc-state",
                "title": "Configure document states | Adobe Experience Manager",
                "content": "The first state can be Draft and it can move to Review, Approved, Translated, and finally to Published.",
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/web-editor-baseline",
                "title": "Create and manage baselines from the Map console | Adobe Experience Manager",
                "content": (
                    "Baseline Type Options include Manual Update and Automatic Update. Manual Update creates a static baseline. "
                    "Automatic Update creates a dynamic baseline."
                ),
            },
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/work-with-baseline/generate-output-use-baseline-for-publishing",
                "title": "Work with Baseline | Adobe Experience Manager",
                "content": "Use the Baseline tab in the Map console to select a baseline before generating output.",
            },
        ],
    )

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What are types of baselines can a user create in AEM Guides?",
        k=3,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert docs
    assert "work-with-baseline" in str(docs[0].get("url") or "")
    snippets = " \n ".join(str(item.get("snippet") or "") for item in docs)
    assert "Manual Update" in snippets
    assert "Automatic Update" in snippets
    assert "Draft" not in snippets
    assert "Published" not in snippets


def test_retrieve_relevant_docs_with_diagnostics_reports_lexical_fallback(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "get_embedding_diagnostics",
        lambda: {
            "configured_model": "all-MiniLM-L6-v2",
            "configured_model_path": "",
            "active_model_identifier": "all-MiniLM-L6-v2",
            "using_local_path": False,
            "available": False,
            "load_mode": "fallback_none",
            "error": "WinError 10013",
        },
    )
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/author-content/map-editor/map-editor-create-map",
                "title": "Create a map | Adobe Experience Manager",
                "content": "Select Create > DITA Map, choose the template, and continue.",
            }
        ],
    )

    payload = doc_retriever_service.retrieve_relevant_docs_with_diagnostics(
        "How do you create a map in AEM Guides?",
        k=2,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert payload["retrieval_mode"] == "lexical"
    assert payload["count"] == 1
    assert payload["embedding"]["available"] is False
    assert "WinError 10013" in str(payload["warnings"][0])


def test_retrieve_relevant_docs_with_diagnostics_can_require_semantic(monkeypatch):
    monkeypatch.setenv("AEM_GUIDES_REQUIRE_SEMANTIC_RETRIEVAL", "true")
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(
        doc_retriever_service,
        "get_embedding_diagnostics",
        lambda: {
            "configured_model": "all-MiniLM-L6-v2",
            "configured_model_path": "",
            "active_model_identifier": "all-MiniLM-L6-v2",
            "using_local_path": False,
            "available": False,
            "load_mode": "fallback_none",
            "error": "WinError 10013",
        },
    )
    monkeypatch.setattr(
        doc_retriever_service,
        "_load_chunks",
        lambda: [
            {
                "url": "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-conf-guide/workspace-configs/workspace-settings",
                "title": "Workspace settings in Experience Manager Guides",
                "content": "Open Workspace settings from the profile menu.",
            }
        ],
    )

    payload = doc_retriever_service.retrieve_relevant_docs_with_diagnostics(
        "How do I configure workspace settings in AEM Guides?",
        k=2,
        allowed_host_suffixes=("experienceleague.adobe.com",),
    )

    assert payload["retrieval_mode"] == "semantic_unavailable"
    assert payload["semantic_required"] is True
    assert payload["results"] == []
    assert "DITA_EMBEDDING_MODEL_PATH" in str(payload["error"])
