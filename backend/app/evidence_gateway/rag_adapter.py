from __future__ import annotations

import hashlib
import re
from typing import Any

from app.evidence_gateway.config import EvidenceGatewaySettings
from app.evidence_gateway.models import EvidenceChunk, KnowledgeResult
from app.services.embedding_service import embed_query, is_embedding_available
from app.services.vector_store_service import get_collection_count, is_chroma_available, query_collection
from app.services.vector_store_service import _get_client  # internal read-only access; no mutation


def _truncate(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[: max(0, limit - 1)] + "…", True


def _stable_doc_id(corpus: str, meta: dict[str, Any], chunk_id: str) -> str:
    source = meta.get("url") or meta.get("source_url") or meta.get("source") or meta.get("entry_id") or chunk_id
    return f"{corpus}:{hashlib.sha256(str(source).encode('utf-8')).hexdigest()[:16]}"


def _canonical_uri(meta: dict[str, Any], chunk_id: str) -> str:
    return str(meta.get("url") or meta.get("source_url") or meta.get("path") or meta.get("source") or chunk_id)


def _title(meta: dict[str, Any], fallback: str) -> str:
    return str(meta.get("title") or meta.get("element_name") or meta.get("topic") or fallback)


def _version(meta: dict[str, Any]) -> str | None:
    return str(meta.get("version") or meta.get("source_version") or meta.get("spec_version") or "") or None


def _section(meta: dict[str, Any]) -> str | None:
    return str(meta.get("section") or meta.get("heading") or meta.get("chunk_type") or "") or None


def _indexed(meta: dict[str, Any]) -> str | None:
    return str(meta.get("indexed_at") or meta.get("updated_at") or meta.get("last_indexed") or "") or None


def _row_to_result(corpus: str, row: dict[str, Any], score: float, method: str, settings: EvidenceGatewaySettings) -> KnowledgeResult:
    meta = row.get("metadata") or {}
    chunk_id = str(row.get("id") or "")
    passage, truncated = _truncate(str(row.get("document") or ""), settings.max_passage_chars)
    return KnowledgeResult(
        chunk_id=chunk_id,
        source_document_id=_stable_doc_id(corpus, meta, chunk_id),
        corpus=corpus,
        source_title=_title(meta, chunk_id),
        source_version=_version(meta),
        section=_section(meta),
        canonical_uri=_canonical_uri(meta, chunk_id),
        indexed_timestamp=_indexed(meta),
        relevance_score=score,
        retrieval_method=method,
        passage=passage,
        truncated=truncated,
    )


def collection_status(settings: EvidenceGatewaySettings) -> dict[str, int | None]:
    status: dict[str, int | None] = {}
    if not is_chroma_available():
        return {corpus_id: None for corpus_id in settings.corpora}
    for corpus_id, cfg in settings.corpora.items():
        status[corpus_id] = get_collection_count(cfg.collection)
    return status


def search_knowledge(query: str, corpus_ids: list[str], top_k: int, mode: str, settings: EvidenceGatewaySettings) -> list[KnowledgeResult]:
    if not is_chroma_available():
        return []
    results: list[KnowledgeResult] = []
    query_embedding = None
    if mode in {"auto", "semantic"} and is_embedding_available():
        emb = embed_query(query)
        if emb is not None:
            query_embedding = emb.tolist() if hasattr(emb, "tolist") else list(emb)

    for corpus_id in corpus_ids:
        cfg = settings.corpora[corpus_id]
        rows: list[dict[str, Any]] = []
        if query_embedding:
            rows.extend(query_collection(cfg.collection, query_embedding=query_embedding, k=top_k * 2))
        if mode in {"auto", "exact"}:
            rows.extend(_exact_search_collection(cfg.collection, query, limit=top_k * 4))
        seen: set[str] = set()
        for row in rows:
            chunk_id = str(row.get("id") or "")
            if not chunk_id or chunk_id in seen:
                continue
            seen.add(chunk_id)
            distance = float(row.get("distance") or 0.0)
            exact_score = _exact_score(query, str(row.get("document") or ""), row.get("metadata") or {})
            score = max(exact_score, 1.0 - distance if query_embedding else 0.0)
            method = "hybrid" if query_embedding and exact_score > 0 else ("semantic" if query_embedding else "exact")
            results.append(_row_to_result(corpus_id, row, score, method, settings))

    results.sort(key=lambda item: (-item.relevance_score, item.corpus, item.chunk_id))
    deduped: list[KnowledgeResult] = []
    seen_keys: set[tuple[str, str]] = set()
    for item in results:
        key = (item.corpus, item.canonical_uri)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(item)
        if len(deduped) >= top_k:
            break
    return deduped


def _exact_search_collection(collection_name: str, query: str, limit: int) -> list[dict[str, Any]]:
    client = _get_client()
    if not client:
        return []
    try:
        coll = client.get_collection(collection_name)
        count = coll.count()
        if count <= 0:
            return []
        got = coll.get(limit=min(count, 10000), include=["documents", "metadatas"])
    except Exception:
        return []
    scored: list[tuple[float, dict[str, Any]]] = []
    for idx, chunk_id in enumerate(got.get("ids") or []):
        doc = (got.get("documents") or [""])[idx] or ""
        meta = (got.get("metadatas") or [{}])[idx] or {}
        score = _exact_score(query, doc, meta)
        if score > 0:
            scored.append((score, {"id": chunk_id, "document": doc, "metadata": meta, "distance": 1.0 - min(score, 1.0)}))
    scored.sort(key=lambda item: -item[0])
    return [row for _score, row in scored[:limit]]


def _exact_score(query: str, document: str, meta: dict[str, Any]) -> float:
    haystack = f"{document} {' '.join(str(v) for v in meta.values())}".lower()
    tokens = [token.lower() for token in re.findall(r"[\w:${}@./#-]+", query) if len(token) >= 2]
    if not tokens:
        return 0.0
    matches = sum(1 for token in tokens if token in haystack)
    phrase_bonus = 2 if query.lower() in haystack else 0
    return (matches + phrase_bonus) / max(1, len(tokens))


def fetch_chunks(chunk_ids: list[str], neighbor_window: int, authorized_corpora: set[str], settings: EvidenceGatewaySettings) -> tuple[list[EvidenceChunk], list[str]]:
    found: list[EvidenceChunk] = []
    missing: list[str] = []
    for chunk_id in chunk_ids:
        located = _locate_chunk(chunk_id, authorized_corpora, settings)
        if not located:
            missing.append(chunk_id)
            continue
        corpus, row = located
        found.append(_row_to_chunk(corpus, row, selected=True, neighbor_of=None, settings=settings))
        for neighbor_id in _neighbor_ids(chunk_id, neighbor_window):
            if neighbor_id == chunk_id:
                continue
            neighbor = _locate_chunk(neighbor_id, {corpus}, settings)
            if neighbor:
                found.append(_row_to_chunk(corpus, neighbor[1], selected=False, neighbor_of=chunk_id, settings=settings))
    seen: set[str] = set()
    deduped: list[EvidenceChunk] = []
    for item in found:
        if item.chunk_id in seen:
            continue
        seen.add(item.chunk_id)
        deduped.append(item)
    return deduped, missing


def _locate_chunk(chunk_id: str, corpora: set[str], settings: EvidenceGatewaySettings) -> tuple[str, dict[str, Any]] | None:
    for corpus in corpora:
        cfg = settings.corpora.get(corpus)
        if not cfg:
            continue
        client = _get_client()
        if not client:
            continue
        try:
            coll = client.get_collection(cfg.collection)
            got = coll.get(ids=[chunk_id], include=["documents", "metadatas"])
            if got and got.get("ids"):
                return corpus, {
                    "id": got["ids"][0],
                    "document": (got.get("documents") or [""])[0] or "",
                    "metadata": (got.get("metadatas") or [{}])[0] or {},
                }
        except Exception:
            continue
    return None


def _row_to_chunk(corpus: str, row: dict[str, Any], selected: bool, neighbor_of: str | None, settings: EvidenceGatewaySettings) -> EvidenceChunk:
    meta = row.get("metadata") or {}
    chunk_id = str(row.get("id") or "")
    text, truncated = _truncate(str(row.get("document") or ""), settings.max_full_chunk_chars)
    return EvidenceChunk(
        chunk_id=chunk_id,
        selected=selected,
        neighbor_of=neighbor_of,
        source_document_id=_stable_doc_id(corpus, meta, chunk_id),
        corpus=corpus,
        source_title=_title(meta, chunk_id),
        source_version=_version(meta),
        section=_section(meta),
        canonical_uri=_canonical_uri(meta, chunk_id),
        indexed_timestamp=_indexed(meta),
        text=text,
        truncated=truncated,
    )


def _neighbor_ids(chunk_id: str, window: int) -> list[str]:
    if window <= 0:
        return []
    match = re.match(r"^(.*?)(\d+)$", chunk_id)
    if not match:
        return []
    prefix, number_text = match.groups()
    number = int(number_text)
    return [f"{prefix}{number + offset}" for offset in range(-window, window + 1) if offset != 0 and number + offset >= 0]
