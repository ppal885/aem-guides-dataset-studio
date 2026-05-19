import pytest

from app.services.chat_agent_service import (
    _collect_research_bullets,
    _collect_sources,
    _completed_source_labels,
    _summarize_tool_result,
)
from app.services.chat_tools import execute_generate_native_pdf_config


@pytest.mark.anyio
async def test_generate_native_pdf_config_returns_structured_guidance(monkeypatch):
    def fake_retrieve_dita_knowledge(_query: str, k: int = 5):
        assert k == 5
        return [
            {
                "element_name": "glossBody",
                "text_content": "Seed hint for PDF body page styling.",
            }
        ]

    def fake_retrieve_relevant_docs(_query: str, k: int = 5):
        assert k == 5
        return [
            {
                "url": "https://experienceleague.adobe.com/docs/native-pdf-watermark",
                "title": "Native PDF | PDF output generation | Adobe Experience Manager",
                "snippet": "Use the Native PDF template and page layout to control repeating page decorations.",
            }
        ]

    monkeypatch.setattr("app.services.dita_knowledge_retriever.retrieve_dita_knowledge", fake_retrieve_dita_knowledge)
    monkeypatch.setattr("app.services.doc_retriever_service.retrieve_relevant_docs", fake_retrieve_relevant_docs)

    result = await execute_generate_native_pdf_config(
        "How do I add a watermark only to body pages?",
        config_type="watermark",
    )

    assert result["config_area"] == "watermark"
    assert "page layout" in result["short_answer"].lower()
    assert result["recommended_actions"]
    assert result["relevant_settings"]
    assert result["evidence"][0]["title"] == "Native PDF | PDF output generation | Adobe Experience Manager"
    assert result["warnings"] == []
    assert result.get("retrieval_status") == "retrieved"


@pytest.mark.anyio
async def test_generate_native_pdf_config_no_docs_exposes_fallback_troubleshooting(monkeypatch):
    def fake_retrieve_dita_knowledge(_query: str, k: int = 5):
        return []

    def fake_retrieve_relevant_docs(_query: str, k: int = 5):
        return []

    monkeypatch.setattr("app.services.dita_knowledge_retriever.retrieve_dita_knowledge", fake_retrieve_dita_knowledge)
    monkeypatch.setattr("app.services.doc_retriever_service.retrieve_relevant_docs", fake_retrieve_relevant_docs)

    result = await execute_generate_native_pdf_config("watermark on body pages", config_type="watermark")

    assert result.get("retrieval_status") == "no_docs"
    assert "No matching Native PDF product documentation" in result["short_answer"]
    assert result["recommended_actions"] == []
    assert result["evidence"] == []
    assert "generic_troubleshooting" in result
    gt = result["generic_troubleshooting"]
    assert "page layout" in str(gt.get("short_answer", "")).lower()
    assert gt.get("recommended_actions")


def test_native_pdf_research_summary_prefers_guidance_over_doc_dump():
    result = {
        "short_answer": "Use the page layout and stylesheet together so the watermark stays at the page level.",
        "recommended_actions": [
            "Start from the page layout used by body pages.",
        ],
        "evidence": [
            {
                "title": "Native PDF | PDF output generation | Adobe Experience Manager",
                "url": "https://experienceleague.adobe.com/docs/native-pdf-watermark",
                "snippet": "Control repeating page decorations through the template.",
            }
        ],
    }

    bullets = _summarize_tool_result("generate_native_pdf_config", result)

    assert bullets[0] == result["short_answer"]
    assert "Recommended next step" in bullets[1]
    assert "Verified against" in bullets[2]


def test_native_pdf_research_helpers_use_structured_guidance_fields():
    tool_results = {
        "generate_native_pdf_config": {
            "short_answer": "Start from the output preset, because it decides which Native PDF template is actually in use.",
            "recommended_actions": [
                "Confirm the output preset points to the intended Native PDF template.",
            ],
            "evidence": [
                {
                    "title": "Native PDF | PDF output generation | Adobe Experience Manager",
                    "url": "https://experienceleague.adobe.com/docs/native-pdf-output",
                    "snippet": "Output presets determine which Native PDF template is used during publishing.",
                }
            ],
        }
    }

    bullets = _collect_research_bullets(tool_results)
    sources = _collect_sources(tool_results)
    labels = _completed_source_labels(tool_results)

    assert any("Native PDF guidance" in bullet for bullet in bullets)
    assert any("Recommended action" in bullet for bullet in bullets)
    assert len(sources) == 1
    assert "Native PDF | PDF output generation | Adobe Experience Manager" in sources[0]
    assert "https://experienceleague.adobe.com/docs/native-pdf-output" in sources[0]
    assert labels == ["Native PDF guidance"]
