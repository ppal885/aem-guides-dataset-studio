"""Guides QA RAG: Chroma collections for framework indexes + bundled knowledge metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.embedding_service import embed_texts_batched, get_embedding_diagnostics, is_embedding_available
from app.services.framework_index_service import read_framework_qa_health
from app.services.gqs_integration_config import rag_dir, rag_enabled, guides_repo_root
from app.services.qa_studio_bundled import (
    load_action_catalog_bundle,
    load_dom_patterns_bundle,
    load_playbooks_bundle,
)
from app.services.vector_store_service import (
    add_documents,
    delete_collection,
    get_collection_count,
    is_chroma_available,
    query_collection,
)

# Chroma collection names (prefix avoids collision with aem_guides / jira_qa)
COL_XPATH = "guides_qa_xpath_entries"
COL_PAGE_METHODS = "guides_qa_page_methods"
COL_STEP_PHRASES = "guides_qa_step_phrases"
COL_ACTION_SEQ = "guides_qa_action_sequences"
COL_SCENARIOS = "guides_qa_scenarios"
COL_PO_BODIES = "guides_qa_page_object_bodies"
COL_FRAMEWORK_DOCS = "guides_qa_framework_docs"
COL_UI_REF = "guides_qa_ui_references"
COL_UI_SNAP = "guides_qa_ui_snapshots"
COL_SCREENSHOT_DESC = "guides_qa_screenshot_descriptions"
COL_SCREENSHOTS = "guides_qa_screenshots"
COL_AUTHORING_OUT = "guides_qa_authoring_outcomes"
COL_PLAYBOOKS = "guides_qa_playbooks_embedded"
COL_ACTION_CAT = "guides_qa_action_catalog_embedded"
COL_DOM_PAT = "guides_qa_dom_patterns_embedded"
COL_SURFACES = "guides_qa_surfaces"

STATE_FILENAME = "guides_qa_rag_state.json"


def _rag_state_path() -> Path | None:
    rd = rag_dir()
    if rd:
        return rd / STATE_FILENAME
    backend = Path(__file__).resolve().parent.parent.parent
    d = backend / "storage" / "guides_qa_rag"
    d.mkdir(parents=True, exist_ok=True)
    return d / STATE_FILENAME


def _load_rag_state() -> dict[str, Any]:
    p = _rag_state_path()
    if not p or not p.is_file():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_rag_state(data: dict[str, Any]) -> None:
    p = _rag_state_path()
    if not p:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _bundled_counts() -> dict[str, int]:
    try:
        pb = load_playbooks_bundle()
        ac = load_action_catalog_bundle()
        dm = load_dom_patterns_bundle()
        return {
            "playbooks": len(pb.get("playbooks") or []),
            "action_catalog": len(ac.get("actions") or []),
            "dom_patterns": len(dm.get("patterns") or []),
        }
    except Exception:
        return {"playbooks": 0, "action_catalog": 0, "dom_patterns": 0}


def guides_rag_health() -> dict[str, Any]:
    chroma = is_chroma_available()
    emb = is_embedding_available()
    emb_diag = get_embedding_diagnostics()
    fw = read_framework_qa_health()
    bundled = _bundled_counts()
    state = _load_rag_state()
    last_reindex = state.get("last_full_reindex_utc")

    def coll(name: str, *, bundled_src: str | None = None, bundled_n: int = 0, not_impl: bool = False) -> dict[str, Any]:
        if not_impl:
            return {
                "source": "not_implemented",
                "chroma_count": 0,
                "bundled_fallback_count": 0,
                "ready": False,
                "reason": "Not implemented in this backend version.",
            }
        c = get_collection_count(name) if chroma else 0
        src = "chroma"
        rn = c
        reason = None
        if bundled_src and c == 0 and bundled_n > 0:
            src = "bundled_degraded"
            rn = bundled_n
            reason = "Using bundled JSON only until Full RAG Reindex populates Chroma."
        elif not rag_enabled():
            src = "disabled"
            rn = bundled_n if bundled_src else 0
            reason = "GQS_RAG_ENABLED is not set — vector indexes are not built."
        elif not chroma:
            src = "chroma_unavailable"
            reason = "ChromaDB unavailable (dependency or init failure)."
        elif not emb:
            src = "embedder_unavailable"
            reason = f"Text embedder unavailable: {emb_diag.get('error') or 'model not loaded'}"
        elif c == 0 and not bundled_src:
            reason = "Index not built or empty — run Full RAG Reindex."
        return {
            "source": src,
            "chroma_collection": name,
            "chroma_count": c,
            "bundled_fallback_count": bundled_n if bundled_src else 0,
            "ready": c > 0 or (bundled_src is not None and bundled_n > 0 and src == "bundled_degraded"),
            "reason": reason,
        }

    collections = {
        "xpath_entries": coll(COL_XPATH),
        "page_methods": coll(COL_PAGE_METHODS),
        "step_phrases": coll(COL_STEP_PHRASES),
        "action_sequences": coll(COL_ACTION_SEQ, not_impl=True),
        "playbooks": coll(COL_PLAYBOOKS, bundled_src="playbooks", bundled_n=bundled["playbooks"]),
        "action_catalog": coll(COL_ACTION_CAT, bundled_src="action_catalog", bundled_n=bundled["action_catalog"]),
        "dom_patterns": coll(COL_DOM_PAT, bundled_src="dom_patterns", bundled_n=bundled["dom_patterns"]),
        "surfaces": coll(COL_SURFACES, not_impl=True),
        "scenarios": coll(COL_SCENARIOS, not_impl=True),
        "page_object_bodies": coll(COL_PO_BODIES, not_impl=True),
        "framework_docs": coll(COL_FRAMEWORK_DOCS, not_impl=True),
        "ui_references": coll(COL_UI_REF, not_impl=True),
        "ui_snapshots": coll(COL_UI_SNAP, not_impl=True),
        "screenshot_descriptions": coll(COL_SCREENSHOT_DESC, not_impl=True),
        "screenshots": coll(COL_SCREENSHOTS, not_impl=True),
        "authoring_outcomes": coll(COL_AUTHORING_OUT, not_impl=True),
    }

    overall_ready = rag_enabled() and chroma and emb and fw.get("status") == "ready"
    chroma_nonempty = sum(get_collection_count(n) for n in (COL_XPATH, COL_PAGE_METHODS, COL_STEP_PHRASES)) > 0

    return {
        "rag_enabled": rag_enabled(),
        "chroma_available": chroma,
        "text_embedder": emb_diag,
        "framework_index": fw,
        "bundled_knowledge_counts": bundled,
        "collections": collections,
        "last_full_reindex_utc": last_reindex,
        "overall_vector_ready": overall_ready and chroma_nonempty,
        "degraded_bundled_only": rag_enabled() and chroma and emb and not chroma_nonempty and sum(bundled.values()) > 0,
    }


def _chunks_from_xpath_file(path: Path) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict[str, Any]] = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    entries = data.get("entries") if isinstance(data, dict) else []
    if not isinstance(entries, list):
        return ids, docs, metas
    for i, row in enumerate(entries):
        if not isinstance(row, dict):
            continue
        xp = str(row.get("xpath") or "")
        if not xp:
            continue
        sid = f"xpath-{i}"
        ids.append(sid)
        docs.append(xp + "\n" + str(row.get("source_file") or ""))
        metas.append({"kind": "xpath", "source_file": str(row.get("source_file") or "")})
    return ids, docs, metas


def _chunks_methods(path: Path) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids, docs, metas = [], [], []
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    methods = data.get("methods") if isinstance(data, dict) else []
    if not isinstance(methods, list):
        return ids, docs, metas
    for i, row in enumerate(methods):
        if not isinstance(row, dict):
            continue
        c = str(row.get("class") or "")
        m = str(row.get("method") or "")
        if not m:
            continue
        sid = f"pm-{i}"
        ids.append(sid)
        docs.append(f"{c}.{m}\n{row.get('source_file') or ''}")
        metas.append({"kind": "page_method", "class": c, "method": m, "source_file": str(row.get("source_file") or "")})
    return ids, docs, metas


def _chunks_phrases(path: Path) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids, docs, metas = [], [], []
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    phrases = data.get("phrases") or data.get("steps") or []
    if isinstance(data, dict) and not phrases and isinstance(data.get("phrases"), list):
        phrases = data["phrases"]
    if not isinstance(phrases, list):
        return ids, docs, metas
    for i, line in enumerate(phrases):
        t = str(line).strip()
        if not t:
            continue
        sid = f"sp-{i}"
        ids.append(sid)
        docs.append(t)
        metas.append({"kind": "step_phrase"})
    return ids, docs, metas


def _embed_and_upsert(collection: str, ids: list[str], docs: list[str], metas: list[dict[str, Any]]) -> int:
    if not ids or not is_chroma_available():
        return 0
    embs = embed_texts_batched(docs, batch_size=48)
    if embs is None:
        return 0
    vec = embs.tolist() if hasattr(embs, "tolist") else list(embs)
    if len(vec) != len(ids):
        return 0
    delete_collection(collection)
    if add_documents(collection, ids, docs, metas, vec):
        return len(ids)
    return 0


def _embed_bundled_playbooks() -> int:
    pb = load_playbooks_bundle()
    ids, docs, metas = [], [], []
    for i, p in enumerate(pb.get("playbooks") or []):
        if not isinstance(p, dict):
            continue
        title = str(p.get("title") or p.get("id") or "")
        blob = json.dumps(p, ensure_ascii=False)[:8000]
        ids.append(f"pb-{i}")
        docs.append(title + "\n" + blob)
        metas.append({"kind": "playbook", "id": str(p.get("id") or "")})
    return _embed_and_upsert(COL_PLAYBOOKS, ids, docs, metas)


def _embed_bundled_actions() -> int:
    ac = load_action_catalog_bundle()
    ids, docs, metas = [], [], []
    for i, a in enumerate(ac.get("actions") or []):
        if not isinstance(a, dict):
            continue
        blob = json.dumps(a, ensure_ascii=False)
        ids.append(f"ac-{i}")
        docs.append(str(a.get("summary") or a.get("id")) + "\n" + blob)
        metas.append({"kind": "action", "id": str(a.get("id") or "")})
    return _embed_and_upsert(COL_ACTION_CAT, ids, docs, metas)


def _embed_bundled_dom() -> int:
    dm = load_dom_patterns_bundle()
    ids, docs, metas = [], [], []
    for i, p in enumerate(dm.get("patterns") or []):
        if not isinstance(p, dict):
            continue
        blob = json.dumps(p, ensure_ascii=False)
        ids.append(f"dm-{i}")
        docs.append(str(p.get("description") or p.get("id")) + "\n" + blob)
        metas.append({"kind": "dom_pattern", "id": str(p.get("id") or "")})
    return _embed_and_upsert(COL_DOM_PAT, ids, docs, metas)


def guides_rag_full_reindex() -> dict[str, Any]:
    if not rag_enabled():
        return {"ok": False, "error": "Set GQS_RAG_ENABLED=1 to build vector indexes."}
    if not is_chroma_available():
        return {"ok": False, "error": "ChromaDB is not available — pip install chromadb and check storage permissions."}
    if not is_embedding_available():
        return {"ok": False, "error": "Text embedding model failed to load — see text_embedder diagnostics."}
    root = guides_repo_root()
    if not root:
        return {"ok": False, "error": "GQS_GUIDES_REPO_ROOT is not configured."}
    idx = root / "resources" / "ai_index"
    stats: dict[str, Any] = {}
    errors: list[str] = []

    def run_file(col: str, name: str, fn) -> None:
        path = idx / name
        if not path.is_file():
            errors.append(f"Missing {path} — run Framework Reindex first.")
            stats[col] = 0
            return
        try:
            ids, docs, metas = fn(path)
            stats[col] = _embed_and_upsert(col, ids, docs, metas)
        except Exception as e:
            errors.append(f"{col}: {e}")
            stats[col] = 0

    run_file(COL_XPATH, "xpath_library.json", _chunks_from_xpath_file)
    run_file(COL_PAGE_METHODS, "page_methods.json", _chunks_methods)
    run_file(COL_STEP_PHRASES, "step_phrases.json", _chunks_phrases)

    try:
        stats[COL_PLAYBOOKS] = _embed_bundled_playbooks()
        stats[COL_ACTION_CAT] = _embed_bundled_actions()
        stats[COL_DOM_PAT] = _embed_bundled_dom()
    except Exception as e:
        errors.append(f"bundled: {e}")

    st = _load_rag_state()
    st["last_full_reindex_utc"] = datetime.now(timezone.utc).isoformat()
    st["last_stats"] = stats
    _save_rag_state(st)

    return {
        "ok": len(errors) == 0,
        "stats": stats,
        "errors": errors,
        "last_full_reindex_utc": st["last_full_reindex_utc"],
    }


def guides_rag_query(collection_key: str, query: str, k: int = 8) -> dict[str, Any]:
    key_map = {
        "xpath_entries": COL_XPATH,
        "page_methods": COL_PAGE_METHODS,
        "step_phrases": COL_STEP_PHRASES,
        "playbooks": COL_PLAYBOOKS,
        "action_catalog": COL_ACTION_CAT,
        "dom_patterns": COL_DOM_PAT,
    }
    col = key_map.get(collection_key)
    if not col:
        return {"ok": False, "error": f"Unknown collection_key: {collection_key}"}
    if not query.strip():
        return {"ok": False, "error": "query is empty"}
    from app.services.embedding_service import embed_query

    emb = embed_query(query[:12000])
    if emb is None:
        return {"ok": False, "error": "Embedding unavailable"}
    qv = emb.tolist() if hasattr(emb, "tolist") else list(emb)
    rows = query_collection(col, qv, k=min(max(k, 1), 50))
    return {"ok": True, "collection": col, "hits": rows}
