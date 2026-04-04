"""
Tenant Admin Routes
Register in router.py:
  from app.api.v1.routes import tenants
  api_router.include_router(tenants.router, prefix="/admin/tenants", tags=["admin"])
"""
from fastapi import APIRouter, UploadFile, File
router = APIRouter()


@router.post("")
async def create_tenant(body: dict):
    """Create new client workspace."""
    try:
        from app.services.tenant_service import create_tenant
        cfg = create_tenant(
            tenant_id  = body.get("tenant_id", ""),
            name       = body.get("name", ""),
            jira_url   = body.get("jira_url", ""),
            jira_token = body.get("jira_token", ""),
            jira_email = body.get("jira_email", ""),
            plan       = body.get("plan", "standard"),
        )
        return cfg.to_dict()
    except Exception as e:
        return {"error": str(e)}


@router.get("")
async def list_tenants():
    """List all tenant workspaces."""
    try:
        from app.services.tenant_service import list_tenants
        return {"tenants": list_tenants()}
    except Exception as e:
        return {"error": str(e)}


@router.post("/{tenant_id}/knowledge-base/terminology")
async def upload_terminology(tenant_id: str, body: dict):
    """
    Upload terminology mapping for a tenant.
    Body: { "terms": { "generic": "client-specific", ... } }
    """
    try:
        from app.services.tenant_service import update_tenant_kb
        cfg = update_tenant_kb(
            tenant_id  = tenant_id,
            terminology = body.get("terms", {}),
            forbidden_terms = body.get("forbidden_terms", []),
        )
        return {"updated": True, "term_count": len(cfg.terminology)}
    except Exception as e:
        return {"error": str(e)}


@router.post("/{tenant_id}/knowledge-base/style-guide")
async def upload_style_guide(tenant_id: str, body: dict):
    """
    Upload style guide rules as text.
    In production: accept PDF and auto-extract rules.
    """
    try:
        from app.services.tenant_service import update_tenant_kb
        update_tenant_kb(
            tenant_id   = tenant_id,
            style_rules = body.get("style_rules", ""),
        )
        return {"updated": True}
    except Exception as e:
        return {"error": str(e)}


@router.post("/{tenant_id}/knowledge-base/component-map")
async def update_component_map(tenant_id: str, body: dict):
    """
    Map Jira components to audiences and products.
    Body: { "Swift Evolution": {"audience": "developer", "product": "Swift language"} }
    """
    try:
        from app.services.tenant_service import update_tenant_kb
        update_tenant_kb(
            tenant_id     = tenant_id,
            component_map = body.get("component_map", {}),
        )
        return {"updated": True}
    except Exception as e:
        return {"error": str(e)}


@router.post("/{tenant_id}/knowledge-base/seed-topics")
async def seed_topics(tenant_id: str, body: dict):
    """
    Index approved past topics as style reference.
    Body: { "topics": [{"filename": "...", "content": "..."}] }
    """
    try:
        from app.services.tenant_service import get_tenant
        from app.services.advanced_rag_service import (
            smart_chunk_text, embed_texts_advanced
        )
        from app.services.vector_store_service import add_documents, is_chroma_available

        cfg    = get_tenant(tenant_id)
        topics = body.get("topics", [])

        if not is_chroma_available():
            return {"error": "ChromaDB not available", "indexed": 0}

        indexed = 0
        for topic in topics:
            content  = topic.get("content", "")
            filename = topic.get("filename", "unknown.dita")
            if not content:
                continue

            chunks = smart_chunk_text(
                text       = content,
                chunk_size = 256,
                overlap    = 32,
                source_url = f"seed:{filename}",
            )
            if not chunks:
                continue

            texts      = [c["text"] for c in chunks]
            embeddings = embed_texts_advanced(texts)
            ids        = [f"seed_{tenant_id}_{filename}_{i}" for i in range(len(chunks))]
            metas      = [{"tenant_id": tenant_id, "filename": filename, "source": "seed"} for _ in chunks]

            add_documents(
                cfg.examples_collection,
                ids=ids, documents=texts,
                metadatas=metas, embeddings=embeddings,
            )
            indexed += 1

        return {"indexed": indexed, "total": len(topics)}
    except Exception as e:
        return {"error": str(e)}


@router.get("/{tenant_id}")
async def get_tenant(tenant_id: str):
    """Get tenant config (without sensitive fields)."""
    try:
        from app.services.tenant_service import get_tenant
        cfg = get_tenant(tenant_id)
        return cfg.to_dict()
    except Exception as e:
        return {"error": str(e)}
