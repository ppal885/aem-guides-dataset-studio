"""Aggregated setup checklist for QA Studio / GQS integration UI."""

from __future__ import annotations

from typing import Any

from app.services.framework_index_service import read_framework_qa_health
from app.services.gqs_integration_config import (
    authoring_llm_execution_enabled,
    demo_plans_enabled,
    engine_stub,
    gqs_llm_credentials,
    guides_repo_configured,
    guides_repo_root,
    llm_configured_for_authoring,
    rag_enabled,
)
from app.services.guides_qa_rag_service import guides_rag_health
from app.services.llm_service import is_llm_available
from app.services.embedding_service import get_embedding_diagnostics, is_embedding_available
from app.services.vector_store_service import is_chroma_available


def llm_authoring_readiness() -> dict[str, Any]:
    cred = gqs_llm_credentials()
    gqs_ok = bool(cred.get("api_key_set") and cred.get("model"))
    app_llm = is_llm_available()
    configured = llm_configured_for_authoring()
    exec_on = authoring_llm_execution_enabled()

    if not configured:
        state = "not_configured"
        reason = (
            "Configure the same LLM as AI chat (e.g. ANTHROPIC_API_KEY + ANTHROPIC_MODEL, or your LLM_PROVIDER "
            "variables). Optional: set GQS_LLM_API_KEY and GQS_LLM_MODEL only if QA authoring must use a separate "
            "OpenAI-compatible gateway. Set QA_STUDIO_USE_APP_LLM=false to forbid app LLM for QA Studio."
        )
    elif not exec_on:
        state = "blocked"
        reason = (
            "QA Studio LLM authoring is turned off because QA_STUDIO_LLM_AUTHORING is false. "
            "Set it to true or unset it to use the same app LLM as AI chat."
        )
    else:
        state = "configured"
        reason = None

    return {
        "state": state,
        "reason": reason,
        "gqs_credentials_present": gqs_ok,
        "app_llm_available": app_llm,
        "demo_plans_enabled": demo_plans_enabled(),
        "model": cred.get("model"),
        "base_url_configured": bool(cred.get("base_url")),
    }


def build_setup_checklist() -> list[dict[str, Any]]:
    fw = read_framework_qa_health()
    rh = guides_rag_health()
    emb = get_embedding_diagnostics()
    llm = llm_authoring_readiness()
    repo = guides_repo_root()

    def row(
        item_id: str,
        label: str,
        ok: bool,
        detail: str,
        fix: str,
        action: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": item_id,
            "label": label,
            "status": "ok" if ok else "missing",
            "detail": detail,
            "fix": fix,
            "action": action,
        }

    checklist: list[dict[str, Any]] = []
    checklist.append(
        row(
            "guides_repo",
            "Guides UI repo configured",
            guides_repo_configured(),
            str(repo) if repo else "(not set)",
            "Set GQS_GUIDES_REPO_ROOT to your guides-ui-tests checkout (example: C:\\ui_framework\\guides-ui-tests).",
            "configure_env",
        )
    )
    checklist.append(
        row(
            "framework_index",
            "Framework index directory (resources/ai_index)",
            fw.get("status") == "ready",
            f"status={fw.get('status')} — {fw.get('reason') or 'OK'}",
            "Run POST /api/v1/framework/reindex after the repo is configured.",
            "framework_reindex",
        )
    )
    idx_files = fw.get("index_files") or {}

    def _file_detail(fname: str) -> tuple[bool, str]:
        meta = idx_files.get(fname) or {}
        exists = bool(meta.get("exists"))
        cnt = int(meta.get("count") or 0)
        ok = exists and cnt > 0
        detail = f"{fname} count={cnt}" + (f" path={meta.get('path')}" if meta.get("path") else "")
        return ok, detail

    ox, dx = _file_detail("xpath_library.json")
    checklist.append(
        row(
            "xpath_library_file",
            "XPath library index (xpath_library.json)",
            ox,
            dx,
            "Run Framework Reindex from Index Admin when the repo is configured.",
            "framework_reindex",
        )
    )
    pm_ok, pm_d = _file_detail("page_methods.json")
    checklist.append(
        row(
            "page_methods_file",
            "Page method index (page_methods.json)",
            pm_ok,
            pm_d,
            "Run Framework Reindex from the Index Admin panel.",
            "framework_reindex",
        )
    )
    sp_ok, sp_d = _file_detail("step_phrases.json")
    checklist.append(
        row(
            "step_phrases_file",
            "Step phrase index (step_phrases.json)",
            sp_ok,
            sp_d,
            "Run Framework Reindex.",
            "framework_reindex",
        )
    )
    checklist.append(
        row(
            "rag_enabled",
            "RAG enabled (GQS_RAG_ENABLED)",
            rag_enabled(),
            "on" if rag_enabled() else "off",
            "Set GQS_RAG_ENABLED=1 and GQS_RAG_DIR to a persistent directory.",
            "configure_env",
        )
    )
    checklist.append(
        row(
            "vector_store",
            "Vector store (Chroma) available",
            is_chroma_available(),
            "available" if is_chroma_available() else "unavailable",
            "pip install chromadb; ensure backend/storage is writable.",
            None,
        )
    )
    checklist.append(
        row(
            "text_embedder",
            "Text embedder available",
            is_embedding_available(),
            emb.get("active_model_identifier", "") or "",
            emb.get("error") or "Install sentence-transformers / model weights.",
            None,
        )
    )
    checklist.append(
        row(
            "image_rag",
            "Screenshot / CLIP embedder",
            False,
            "not_implemented",
            "Image RAG is not wired in this backend build.",
            None,
        )
    )
    vready = bool(rh.get("overall_vector_ready"))
    checklist.append(
        row(
            "rag_vectors",
            "Guides QA vector collections populated",
            vready,
            "overall_vector_ready=%s" % rh.get("overall_vector_ready"),
            "Run POST /api/v1/rag/reindex after framework indexes exist.",
            "rag_reindex",
        )
    )
    lstate = llm.get("state")
    lc = llm_configured_for_authoring()
    checklist.append(
        row(
            "llm_provider",
            "LLM provider configured for authoring",
            lc,
            str(lstate),
            str(llm.get("reason") or ""),
            "configure_env",
        )
    )
    checklist.append(
        row(
            "llm_model",
            "LLM model id set (GQS_LLM_MODEL)",
            bool(gqs_llm_credentials().get("model")) or (is_llm_available() and not gqs_llm_credentials().get("api_key_set")),
            str(gqs_llm_credentials().get("model") or "(using app default)"),
            "Set GQS_LLM_MODEL when using GQS_LLM_*; otherwise the app uses LLM_PROVIDER / model env from chat.",
            "configure_env",
        )
    )
    checklist.append(
        row(
            "engine_stub",
            "Video-to-test engine live (optional)",
            not engine_stub(),
            "GQS_ENGINE_STUB=%s" % engine_stub(),
            "Set GQS_ENGINE_STUB=false when the video engine integration is available.",
            "configure_env",
        )
    )
    return checklist
