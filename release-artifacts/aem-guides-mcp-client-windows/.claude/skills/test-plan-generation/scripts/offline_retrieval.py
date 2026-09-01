"""Fail-open local Chroma retrieval for authoring-time discovery (UACDISCOVER-04).

This module gives the skill a read-only retrieval path when the backend process and
its MCP tools are unavailable but the repository's local Chroma collections are
present.  It reuses the backend's real embedding and vector-store services; it does
not implement a second index or infer evidence when those services are unavailable.

Honesty contract:

* every result is labelled ``OFFLINE_CHROMA`` and ``SUPPORTING_DISCOVERY``;
* results are non-authoritative investigation inputs, never Acceptance Criteria;
* offline Jira history is never represented as a live ``indexed_history_run``;
* import, collection, embedding, and query failures return ``[]`` and record a
  machine-readable reason through :func:`retrieval_status`.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


SOURCE_LABEL = "OFFLINE_CHROMA"
AUTHORITY_CLASS = "SUPPORTING_DISCOVERY"
MAX_QUERY_CHARS = 2_000
MAX_RESULTS = 20
_MAX_HISTORY_SCAN = 160
_STATUS_LOCK = threading.Lock()
_LAST_STATUS: dict[str, dict[str, Any]] = {
    "docs": {"status": "NOT_RUN", "reason": "not_run", "result_count": 0},
    "history": {"status": "NOT_RUN", "reason": "not_run", "result_count": 0},
}


def _record_status(kind: str, status: str, reason: str, result_count: int = 0) -> None:
    with _STATUS_LOCK:
        _LAST_STATUS[kind] = {
            "status": status,
            "reason": reason,
            "result_count": max(0, int(result_count)),
            "source_label": SOURCE_LABEL,
            "authority_class": AUTHORITY_CLASS,
            "non_authoritative": True,
        }


def retrieval_status(kind: str | None = None) -> dict[str, Any]:
    """Return the last fail-open outcome without exposing credentials or raw errors."""
    with _STATUS_LOCK:
        if kind in _LAST_STATUS:
            return dict(_LAST_STATUS[str(kind)])
        return {name: dict(value) for name, value in _LAST_STATUS.items()}


def _bounded_query(query: object) -> str:
    text = " ".join(str(query or "").split())
    return text[:MAX_QUERY_CHARS]


def _bounded_k(k: object) -> int:
    try:
        value = int(k)
    except (TypeError, ValueError):
        value = 5
    return max(1, min(value, MAX_RESULTS))


def _candidate_backend_dirs() -> list[Path]:
    roots: list[Path] = []
    for start in (Path(__file__).resolve(), Path.cwd().resolve()):
        roots.extend((start, *start.parents))
    candidates: list[Path] = []
    for root in dict.fromkeys(roots):
        backend = root if root.name.casefold() == "backend" else root / "backend"
        repo_root = backend.parent
        if (backend / "app" / "services" / "embedding_service.py").is_file() and (
            backend / "app" / "services" / "vector_store_service.py"
        ).is_file() and (repo_root / ".git").exists() and (
            repo_root / "scripts" / "run_test_plan_quality_benchmark.py"
        ).is_file():
            candidates.append(backend.resolve())
    return list(dict.fromkeys(candidates))


def _load_backend() -> dict[str, Any] | None:
    """Load the repository services lazily; a running backend is not required."""
    candidates = _candidate_backend_dirs()
    if not candidates:
        return None
    backend_dir = candidates[0]
    backend_text = str(backend_dir)
    if backend_text not in sys.path:
        sys.path.insert(0, backend_text)
    try:
        from app.services.embedding_service import embed_query
        from app.services.vector_store_service import (
            CHROMA_COLLECTION_AEM_GUIDES,
            CHROMA_COLLECTION_JIRA_QA,
            get_collection_count,
            is_chroma_available,
            query_collection,
        )
    except Exception:
        return None
    return {
        "embed_query": embed_query,
        "query_collection": query_collection,
        "get_collection_count": get_collection_count,
        "is_chroma_available": is_chroma_available,
        "docs_collection": CHROMA_COLLECTION_AEM_GUIDES,
        "history_collection": CHROMA_COLLECTION_JIRA_QA,
    }


def _query_rows(kind: str, query: object, k: object, *, overfetch: int = 1) -> list[dict]:
    query_text = _bounded_query(query)
    if not query_text:
        _record_status(kind, "EMPTY", "empty_query")
        return []
    backend = _load_backend()
    if backend is None:
        _record_status(kind, "UNAVAILABLE", "backend_package_not_importable")
        return []

    collection_key = "docs_collection" if kind == "docs" else "history_collection"
    collection = str(backend[collection_key])
    try:
        if not bool(backend["is_chroma_available"]()):
            _record_status(kind, "UNAVAILABLE", "chroma_unavailable")
            return []
        if int(backend["get_collection_count"](collection)) <= 0:
            _record_status(kind, "UNAVAILABLE", "collection_absent_or_empty")
            return []
        embedding = backend["embed_query"](query_text)
        if embedding is None:
            _record_status(kind, "UNAVAILABLE", "embedding_unavailable")
            return []
        vector = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        if not vector:
            _record_status(kind, "UNAVAILABLE", "embedding_empty")
            return []
        requested = min(_bounded_k(k) * max(1, int(overfetch)), _MAX_HISTORY_SCAN)
        rows = backend["query_collection"](collection, vector, k=requested)
    except Exception as exc:
        _record_status(kind, "ERROR", f"query_failed:{type(exc).__name__}")
        return []
    if not isinstance(rows, list):
        _record_status(kind, "ERROR", "invalid_query_response")
        return []
    clean_rows = [row for row in rows if isinstance(row, dict)]
    if not clean_rows:
        _record_status(kind, "EMPTY", "query_returned_no_rows")
        return []
    _record_status(kind, "SUCCESS", "rows_returned", len(clean_rows))
    return clean_rows


def _clean_text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _distance(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_url(value: object) -> str:
    url = _clean_text(value, 2_048)
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    if parsed.username or parsed.password:
        return ""
    return url


def _metadata(row: dict) -> dict:
    value = row.get("metadata")
    return value if isinstance(value, dict) else {}


def retrieve_docs(query: object, k: int = 5) -> list[dict[str, Any]]:
    """Retrieve normalized local product-documentation neighbors.

    The returned authority is deliberately capped at supporting discovery even when
    the underlying row identifies an official source.  A later verifier may inspect
    that underlying source directly; this helper cannot promote it by itself.
    """
    limit = _bounded_k(k)
    rows = _query_rows("docs", query, limit)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        metadata = _metadata(row)
        title = _clean_text(metadata.get("title") or metadata.get("name"), 300)
        snippet = _clean_text(row.get("document"), 1_000)
        url = _clean_url(
            metadata.get("url") or metadata.get("source_url") or metadata.get("canonical_url"),
        )
        row_id = _clean_text(row.get("id"), 300)
        if not title and not snippet:
            continue
        source_ref = url or row_id or title
        dedupe_key = source_ref.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "source_label": SOURCE_LABEL,
                "source": SOURCE_LABEL,
                "authority_class": AUTHORITY_CLASS,
                "non_authoritative": True,
                "title": title,
                "snippet": snippet,
                "url": url,
                "source_ref": source_ref,
                "distance": _distance(row.get("distance")),
                "source_type": _clean_text(metadata.get("source_type"), 120),
                "underlying_authority": _clean_text(metadata.get("authority"), 120),
            }
        )
        if len(normalized) >= limit:
            break
    if normalized:
        _record_status("docs", "SUCCESS", "normalized_results", len(normalized))
    elif retrieval_status("docs").get("status") == "SUCCESS":
        _record_status("docs", "EMPTY", "no_normalizable_results")
    return normalized


def _component_values(metadata: dict) -> list[str]:
    raw = metadata.get("components")
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            decoded = [part.strip() for part in raw.split(",")]
    else:
        decoded = raw
    if not isinstance(decoded, list):
        decoded = [metadata.get("component")]
    return [_clean_text(value, 200) for value in decoded if _clean_text(value, 200)]


def _component_tokens(values: list[str]) -> set[str]:
    """Return raw and canonical component tokens using the backend's real aliases."""
    clean = [value for value in values if value]
    tokens = {value.casefold() for value in clean}
    try:
        from app.services.jira_component_metadata_service import canonical_component_names

        tokens.update(value.casefold() for value in canonical_component_names(clean))
    except Exception:
        pass
    return tokens


def _safe_history_snippet(value: object) -> str:
    """Keep defect context while excluding embedded Human/UAC answer sections."""
    text = str(value or "")
    lowered = text.casefold()
    cut = len(text)
    for marker in ("acceptance criteria:", "## uac", "uac criteria", "human feedback"):
        position = lowered.find(marker)
        if position >= 0:
            cut = min(cut, position)
    return _clean_text(text[:cut], 1_000)


def retrieve_history(query: object, component: object = "", k: int = 5) -> list[dict[str, Any]]:
    """Retrieve distinct same-component defect neighbors from local ``jira_qa``.

    This function never returns or mutates ``indexed_history_run``.  It also excludes
    explicit acceptance/UAC/feedback chunks so a historical Human answer cannot be
    mistaken for current-ticket acceptance truth during blinded generation.
    """
    limit = _bounded_k(k)
    rows = _query_rows("history", query, limit, overfetch=8)
    requested_component = _clean_text(component, 200)
    wanted_tokens = _component_tokens([requested_component]) if requested_component else set()
    normalized: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in rows:
        metadata = _metadata(row)
        chunk_type = _clean_text(metadata.get("chunk_type"), 120).casefold()
        if any(marker in chunk_type for marker in ("acceptance", "uac", "human_feedback")):
            continue
        components = _component_values(metadata)
        if wanted_tokens and not wanted_tokens.intersection(_component_tokens(components)):
            continue
        jira_key = _clean_text(metadata.get("jira_key"), 80).upper()
        if not jira_key or jira_key in seen_keys:
            continue
        seen_keys.add(jira_key)
        title = _clean_text(metadata.get("title"), 300)
        snippet = _safe_history_snippet(row.get("document"))
        normalized.append(
            {
                "source_label": SOURCE_LABEL,
                "source": SOURCE_LABEL,
                "authority_class": AUTHORITY_CLASS,
                "non_authoritative": True,
                "indexed_history_run": False,
                "jira_key": jira_key,
                "title": title,
                "snippet": snippet,
                "component": components[0] if components else requested_component,
                "source_ref": jira_key,
                "distance": _distance(row.get("distance")),
            }
        )
        if len(normalized) >= limit:
            break
    if normalized:
        _record_status("history", "SUCCESS", "normalized_results", len(normalized))
    elif retrieval_status("history").get("status") == "SUCCESS":
        reason = "no_same_component_results" if wanted_tokens else "no_normalizable_results"
        _record_status("history", "EMPTY", reason)
    return normalized
