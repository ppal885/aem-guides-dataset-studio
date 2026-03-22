from fastapi import APIRouter
from app.api.v1.routes import (
    admin,
    aem_recipes,
    ai_flow,
    ai_dataset,
    authoring,
    bulk,
    chat,
    dataset_explorer,
    doc_pdf,
    intent,
    jira,
    limits,
    performance,
    preferences,
    presets,
    recipes,
    safety,
    scale_testing,
    schedule,
    specialized,
    smart_suggestions,
    tenants,
)

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
api_router.include_router(ai_flow.router, tags=["ai-flow"])
api_router.include_router(ai_dataset.router)
api_router.include_router(chat.router)
api_router.include_router(jira.router, prefix="/jira", tags=["jira"])
api_router.include_router(authoring.router, tags=["authoring"])
api_router.include_router(intent.router, prefix="/intent", tags=["intent"])
api_router.include_router(preferences.router, prefix="/prefs", tags=["preferences"])
api_router.include_router(safety.router, prefix="/safety", tags=["safety"])
api_router.include_router(tenants.router, prefix="/admin/tenants", tags=["tenants"])
api_router.include_router(doc_pdf.router, prefix="/docs", tags=["docs"])
api_router.include_router(smart_suggestions.router, prefix="/smart", tags=["smart"])
