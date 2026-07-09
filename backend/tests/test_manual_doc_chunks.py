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
    assert "https://www.dita-ot.org/dev/release-notes/" in text
    assert "https://www.dita-ot.org/dev/topics/markdown-input" in text
    assert "https://www.dita-ot.org/dev/reference/markdown/markdown-dita-syntax" in text
    assert "https://www.dita-ot.org/dev/topics/lwdita-input" in text
    assert "https://www.dita-ot.org/dev/topics/dita2dita" in text
    assert "https://www.dita-ot.org/dev/reference/architecture" in text
    assert "https://www.dita-ot.org/dev/reference/processing-structure" in text
    assert "https://www.dita-ot.org/dev/reference/map-first-preprocessing" in text
    assert "https://www.dita-ot.org/dev/reference/processing-pipeline-modules" in text
    assert "https://www.dita-ot.org/dev/reference/processing-order" in text
    assert "https://www.dita-ot.org/dev/reference/store-api" in text
    assert "https://www.dita-ot.org/dev/reference/preprocessing" in text
    assert "https://www.dita-ot.org/dev/reference/preprocess-genlist" in text
    assert "https://www.dita-ot.org/dev/reference/preprocess-debugfilter" in text
    assert "https://www.dita-ot.org/dev/reference/preprocess-mapref" in text
    assert "https://www.dita-ot.org/dev/reference/preprocess-branch-filter" in text
    assert "https://www.dita-ot.org/dev/reference/preprocess-keyref" in text
    assert "map-first pre-processing" in text
    assert "preprocess2" in text
    assert "XSLT shell files" in text
    assert "filtering before conref resolution" in text
    assert "store-type=memory" in text
    assert "gen-list" in text
    assert "table column names" in text
    assert "referenced map" in text
    assert "ditavalref" in text
    assert "key-based text replacement" in text
    assert "temporary working directory" in text
    assert "https://www.dita-ot.org/dev/reference/markdown/mdita-syntax" in text
    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-guide/cs-ig/web-editor-configs-cs/conf-pdf-generation-dita-ot" in text
    assert "DOWNLOAD_TOPIC_PDF" in text
    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides-learn/videos/advanced-user-guide/conver-ui-config" in text
    assert "Convert UI config to JSON" in text
    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides-learn/videos/advanced-user-guide/conver-ui-config#understanding-targeteditor-properties" in text
    assert "documentSubType" in text
    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/archSpec/base/cascading-in-a-ditamap.html" in text
    assert "https://docs.oasis-open.org/dita/v1.2/os/spec/archSpec/cascading-in-a-ditamap.html" in text
    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html" in text


def test_retrieve_relevant_docs_uses_manual_dita_ot_args_draft(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT PDF draft-comment argument args.draft",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/parameters/parameters-base" in urls


def test_retrieve_relevant_docs_uses_aem_guides_dita_ot_pdf_config(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do I enable old DITA-OT PDF generation from topic preview in AEM Guides Cloud Service Web Editor?",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/install-guide/cs-ig/web-editor-configs-cs/conf-pdf-generation-dita-ot" in urls


def test_retrieve_relevant_docs_uses_aem_guides_ui_config_conversion(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do I convert old ui_config customizations to modular JSON in AEM Guides XML Editor?",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides-learn/videos/advanced-user-guide/conver-ui-config" in urls


def test_retrieve_relevant_docs_uses_aem_guides_targeteditor_anchor(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What are targetEditor mode displayMode documentType documentSubType and flag in AEM Guides UI config?",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://experienceleague.adobe.com/en/docs/experience-manager-guides-learn/videos/advanced-user-guide/conver-ui-config#understanding-targeteditor-properties" in urls


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


def test_retrieve_relevant_docs_prioritizes_dita_command_required_arguments(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What are the required arguments for the dita command?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/parameters/dita-command-arguments" in urls[:2]


def test_retrieve_relevant_docs_prioritizes_dita_ot_pdf2_debugging(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do I debug a topic that publishes in HTML5 but fails in PDF2?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/error-messages" in urls[:3]


def test_retrieve_relevant_docs_prioritizes_dita_ot_logs_and_evidence(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What DITA-OT evidence should I collect for a PDF2 failure?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/error-messages" in urls[:3]


def test_retrieve_relevant_docs_prioritizes_dita_ot_draft_comment_parameter(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "My PDF transform ignores draft-comment content. What command-line option should I try?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/parameters/parameters-base" in urls[:2]


def test_retrieve_relevant_docs_uses_manual_dita_ot_release_notes(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "DITA-OT release notes upgrade Java 17 changed defaults regression",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/release-notes/" in urls


def test_retrieve_relevant_docs_uses_manual_dita_ot_markdown_input(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Can DITA-OT process Markdown input with format markdown and convert to DITA?",
        k=5,
    )
    urls = {item.get("url") for item in docs}

    assert "https://www.dita-ot.org/dev/topics/markdown-input" in urls


def test_retrieve_relevant_docs_prioritizes_customer_markdown_pdf_failure(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "I have a customer saying markdown topics work in HTML but not in PDF. What would you ask first?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/markdown-input" in urls[:3]


def test_retrieve_relevant_docs_uses_manual_markdown_dita_syntax(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How does Markdown DITA syntax create topic IDs, maps, keys, and tables?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/markdown/markdown-dita-syntax" in urls[:3]


def test_retrieve_relevant_docs_uses_markdown_dita_syntax_for_map_schema(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "In Markdown DITA, how do I use YAML schema to author a DITA map with topicrefs?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/markdown/markdown-dita-syntax" in urls[:3]


def test_retrieve_relevant_docs_uses_manual_lwdita_input(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What are XDITA MDITA and HDITA in DITA-OT Lightweight DITA?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/lwdita-input" in urls[:3]


def test_retrieve_relevant_docs_uses_lwdita_for_format_values(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Which format values should I use for xdita, mdita, and hdita topicrefs?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/lwdita-input" in urls[:3]


def test_retrieve_relevant_docs_uses_lwdita_for_conditional_processing(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How does conditional processing work in MDITA and HDITA with data-props?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/lwdita-input" in urls[:3]


def test_retrieve_relevant_docs_uses_markdown_input_for_dita_only_semantics(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "My Markdown content needs profiling and conkeyrefs later. Should I keep it as Markdown?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/markdown-input" in urls[:3]


def test_retrieve_relevant_docs_uses_lwdita_for_hdita_map_limit(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Can I create an HDITA map directly, or do I need another map type?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/lwdita-input" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_normalized_dita(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How do I inspect normalized DITA to see resolved keys and conrefs after preprocessing?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/topics/dita2dita" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_architecture_for_pipeline(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Explain the DITA-OT preprocessing pipeline architecture, map-first processing, and extension points.",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/architecture" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_processing_structure(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How does DITA-OT process maps and topics in temporary files, and does it modify source files?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/processing-structure" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_map_first_preprocessing(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How is map-first preprocessing different from default preprocess in DITA-OT, and when should I use preprocess2?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/map-first-preprocessing" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_processing_pipeline_modules(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How are DITA-OT processing modules implemented with Ant targets, XSLT shell files, Java, and plug-ins?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/processing-pipeline-modules" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_processing_order(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Does DITA-OT apply filtering before conref resolution, and can another DITA processor use a different processing order?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/processing-order" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_store_api(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What is the DITA-OT Store API and how does store-type=memory use Cache Store for temporary resources?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/store-api" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocessing_modules(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What are DITA-OT preprocessing modules such as debug-filter, mapref, keyref, conref, profile, and chunk?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocessing" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocess_genlist(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Which DITA-OT preprocess step creates conref.list, dita.list, image.list, and referenced topic lists?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocess-genlist" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocess_debugfilter(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Which DITA-OT preprocess step copies referenced DITA content, applies filtering, inserts debugging information, and adjusts table column names?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocess-debugfilter" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocess_mapref(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What does the DITA-OT mapref preprocess step do with topicrefs and relationship tables from a referenced submap?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocess-mapref" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocess_branch_filter(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "How does the DITA-OT branch-filter preprocess step use ditavalref rules for branch-specific filtering?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocess-branch-filter" in urls[:3]


def test_retrieve_relevant_docs_uses_dita_ot_preprocess_keyref(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Which DITA-OT preprocess step resolves keyref, replaces key-based href targets, and performs key-based text replacement?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/preprocess-keyref" in urls[:3]


def test_retrieve_relevant_docs_uses_mdita_syntax_for_shortdesc_simpletable(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "In MDITA syntax, why does the first paragraph become shortdesc and tables become simpletable?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/markdown/mdita-syntax" in urls[:3]


def test_retrieve_relevant_docs_uses_dita13_cascading(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "In DITA 1.3, how do cascade merge and nomerge affect audience and product metadata?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/archSpec/base/cascading-in-a-ditamap.html" in urls[:3]


def test_retrieve_relevant_docs_uses_dita12_cascading(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "For DITA 1.2, which map attributes cascade before DITA 1.3 cascade merge tokens existed?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://docs.oasis-open.org/dita/v1.2/os/spec/archSpec/cascading-in-a-ditamap.html" in urls[:3]


def test_retrieve_relevant_docs_uses_dita13_common_map_attributes(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Compare processing-role resource-only, toc, linking, chunk, copy-to, and keyscope on topicrefs.",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonMapAttributes.html" in urls[:3]


def test_retrieve_relevant_docs_uses_markdown_format_comparison(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "What is the difference between Markdown DITA and MDITA?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://www.dita-ot.org/dev/reference/markdown/format-comparison" in urls[:3]


def test_retrieve_relevant_docs_uses_metadata_maps_topics_for_effective_metadata(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Why does metadata appear in output if the topic source does not contain it?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/archSpec/base/metadata-in-maps-and-topics.html" in urls[:3]


def test_retrieve_relevant_docs_uses_common_attributes_for_every_element_question(monkeypatch):
    monkeypatch.setattr(doc_retriever_service, "is_chroma_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "is_embedding_available", lambda: False)
    monkeypatch.setattr(doc_retriever_service, "get_embedding_diagnostics", lambda: {"available": False})

    docs = doc_retriever_service.retrieve_relevant_docs(
        "Can every DITA element use every common attribute like conref outputclass keyref?",
        k=5,
    )
    urls = [item.get("url") for item in docs]

    assert "https://docs.oasis-open.org/dita/dita/v1.3/os/part1-base/langRef/attributes/commonAttributes.html" in urls[:3]


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
