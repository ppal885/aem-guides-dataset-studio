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
