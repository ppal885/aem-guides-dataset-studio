from fastapi import APIRouter
from app.api.v1.routes import presets, schedule, dataset_explorer, performance, recipes, bulk, aem_recipes, specialized, scale_testing, limits, admin, ai_dataset, chat

api_router = APIRouter()


def _get_rag_status():
    """Shared RAG status logic for /rag-status and /ai/rag-status."""
    try:
        from app.services.vector_store_service import (
            is_chroma_available,
            get_collection_count,
            CHROMA_COLLECTION_AEM_GUIDES,
            CHROMA_COLLECTION_DITA_SPEC,
        )
        from app.utils.evidence_extractor import USE_AEM_DOCS_ENRICHMENT
        chroma_ok = is_chroma_available()
        aem_count = get_collection_count(CHROMA_COLLECTION_AEM_GUIDES) if chroma_ok else 0
        dita_count = get_collection_count(CHROMA_COLLECTION_DITA_SPEC) if chroma_ok else 0
        return {
            "chroma_available": chroma_ok,
            "aem_guides": {
                "source": "Experience League crawl (LangChain WebBaseLoader)",
                "collection": CHROMA_COLLECTION_AEM_GUIDES,
                "chunk_count": aem_count,
                "used_in": ["mechanism_classifier", "pattern_classifier", "evidence_extractor"],
                "populate_via": "POST /api/v1/ai/crawl-aem-guides",
                "enrichment_enabled": USE_AEM_DOCS_ENRICHMENT,
            },
            "dita_spec": {
                "source": "DITA 1.2 + 1.3 Part 1 Base PDFs (LangChain PyPDFLoader)",
                "collection": CHROMA_COLLECTION_DITA_SPEC,
                "chunk_count": dita_count,
                "used_in": ["scenario_expander", "plan_for_scenario"],
                "populate_via": "POST /api/v1/ai/index-dita-pdf",
            },
        }
    except Exception as e:
        from app.core.structured_logging import get_structured_logger
        get_structured_logger(__name__).warning_structured("RAG status failed", extra_fields={"error": str(e)})
        return {"chroma_available": False, "error": str(e)}


@api_router.get("/rag-status")
def get_rag_status_v1():
    """RAG source status (alias at /api/v1/rag-status). Also at /api/v1/ai/rag-status."""
    return _get_rag_status()


api_router.include_router(presets.router)
api_router.include_router(schedule.router)
api_router.include_router(dataset_explorer.router)
api_router.include_router(performance.router)
api_router.include_router(recipes.router)
api_router.include_router(bulk.router)
api_router.include_router(aem_recipes.router)
api_router.include_router(specialized.router)
api_router.include_router(scale_testing.router)
api_router.include_router(limits.router)
api_router.include_router(admin.router)
api_router.include_router(ai_dataset.router)
api_router.include_router(chat.router)