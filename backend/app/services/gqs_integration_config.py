"""Guides QA Studio (GQS) integration environment — repo root, RAG dirs, LLM, engine stub."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def guides_repo_root() -> Path | None:
    """Resolved checkout root for guides-ui-tests (or compatible automation repo)."""
    for key in ("GQS_GUIDES_REPO_ROOT", "QA_STUDIO_UI_TESTS_PATH"):
        raw = (os.getenv(key) or "").strip().strip('"').strip("'")
        if not raw:
            continue
        p = Path(raw).expanduser().resolve()
        if p.is_dir():
            return p
    return None


def guides_repo_configured() -> bool:
    return guides_repo_root() is not None


def rag_enabled() -> bool:
    return _truthy(os.getenv("GQS_RAG_ENABLED"))


def rag_dir() -> Path | None:
    raw = (os.getenv("GQS_RAG_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def visual_corpus_dir() -> Path | None:
    raw = (os.getenv("GQS_RAG_VISUAL_CORPUS_DIR") or "").strip()
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def engine_stub() -> bool:
    return _truthy(os.getenv("GQS_ENGINE_STUB", "true"))


def demo_plans_enabled() -> bool:
    return _truthy(os.getenv("QA_STUDIO_DEMO_PLANS")) or _truthy(os.getenv("GQS_DEMO_PLANS"))


def use_app_llm_for_authoring() -> bool:
    """Legacy: explicit opt-in to counting app LLM as the authoring provider.

    Today authoring uses the same ``llm_service`` as AI chat whenever GQS OpenAI-compatible
    credentials are not set, unless ``QA_STUDIO_USE_APP_LLM`` is explicitly set to false
    (see :func:`llm_configured_for_authoring`).
    """
    return _truthy(os.getenv("QA_STUDIO_USE_APP_LLM"))


def _explicitly_opted_out_of_app_llm_for_qa() -> bool:
    """When true, QA Studio authoring will not use the app LLM; only a full GQS_LLM_* pair counts."""
    v = (os.getenv("QA_STUDIO_USE_APP_LLM") or "").strip().lower()
    return v in ("0", "false", "no", "off")


def _qa_studio_llm_authoring_explicitly_disabled() -> bool:
    v = (os.getenv("QA_STUDIO_LLM_AUTHORING") or "").strip().lower()
    return v in ("0", "false", "no", "off")


def authoring_llm_execution_enabled() -> bool:
    """Whether the server may run paid/LLM plan and generate endpoints.

    Default: same as chat — if ``is_llm_available()``, authoring may run (unless explicitly disabled).
    Optional overrides: truthy ``QA_STUDIO_LLM_AUTHORING`` / ``GQS_AUTHORING_ENABLED``, or
    ``GQS_LLM_API_KEY`` (legacy auto-enable). Set ``QA_STUDIO_LLM_AUTHORING=false`` to turn off
    QA Studio LLM calls while leaving chat enabled.
    """
    if _qa_studio_llm_authoring_explicitly_disabled():
        return False
    if _truthy(os.getenv("QA_STUDIO_LLM_AUTHORING")):
        return True
    if _truthy(os.getenv("GQS_AUTHORING_ENABLED")):
        return True
    if (os.getenv("GQS_LLM_API_KEY") or "").strip():
        return True
    from app.services.llm_service import is_llm_available

    return is_llm_available()


def llm_configured_for_authoring() -> bool:
    """Authoring model is ready: full GQS OpenAI-compatible credentials, or app LLM (chat provider).

    ``GQS_LLM_API_KEY`` + ``GQS_LLM_MODEL`` select a dedicated OpenAI-compatible endpoint; otherwise
    the primary app LLM (``LLM_PROVIDER``, ``ANTHROPIC_*``, ``OPENAI_*``, etc.) is used — the same stack as AI chat.
    Set ``QA_STUDIO_USE_APP_LLM=false`` to require GQS credentials only (no app LLM for QA authoring).
    """
    c = gqs_llm_credentials()
    if c.get("api_key_set") and (c.get("model") or "").strip():
        return True
    from app.services.llm_service import is_llm_available

    if not is_llm_available():
        return False
    if _explicitly_opted_out_of_app_llm_for_qa():
        return False
    return True


def gqs_llm_credentials() -> dict[str, Any]:
    return {
        "api_key_set": bool((os.getenv("GQS_LLM_API_KEY") or "").strip()),
        "base_url": (os.getenv("GQS_LLM_BASE_URL") or "").strip() or None,
        "model": (os.getenv("GQS_LLM_MODEL") or "").strip() or None,
        "timeout_secs": float(os.getenv("GQS_LLM_TIMEOUT_SECS", "120") or "120"),
    }


def ai_index_dir(repo: Path | None = None) -> Path | None:
    root = repo or guides_repo_root()
    if not root:
        return None
    return root / "resources" / "ai_index"


INDEX_FILES = ("xpath_library.json", "page_methods.json", "step_phrases.json")
