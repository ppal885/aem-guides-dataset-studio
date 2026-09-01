"""Index UI records into the EXISTING RAG (ChromaDB) - no new vector DB.

Reuses the backend's embedding model (all-MiniLM-L6-v2, 384-dim) and Chroma
client so UI records are query-compatible with the existing corpora. Adds two
sibling collections: ui_state and ui_transition. Always writes the records and
an ingestion_manifest to disk first (deterministic), then upserts to Chroma if
the backend services are importable and embeddings are available.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

COLLECTION_UI_STATE = "ui_state"
COLLECTION_UI_TRANSITION = "ui_transition"

# Which record_type lands in which collection.
_STATE_TYPES = {
    "UI_STATE", "UI_SURFACE", "UI_CAPABILITY", "UI_CURRENTNESS",
    "UI_SURFACE_IDENTITY", "UI_HIERARCHY",
}
_TRANSITION_TYPES = {
    "UI_TRANSITION",
    "UI_FLOW",
    "UI_SURFACE_RELATION",
    "UI_CONFIGURATION_DEPENDENCY",
}


def _backend_on_path():
    """Make backend/app importable when running from the repo root."""
    root = Path(__file__).resolve().parent.parent
    backend = root / "backend"
    if backend.is_dir() and str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def _sanitize_metadata(md):
    """Chroma metadata values must be scalar (str/int/float/bool). Drop None,
    JSON-encode anything structured that slipped through."""
    clean = {}
    for k, v in (md or {}).items():
        if v is None:
            continue
        if isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = json.dumps(v, ensure_ascii=False)
    return clean


def write_records(output_dir, records):
    """Always persist the RAG records + an ingestion manifest to disk."""
    rag_dir = Path(output_dir) / "rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    recs_path = rag_dir / "ui_rag_records.jsonl"
    with recs_path.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "by_type": _count_by(records, lambda r: r["metadata"]["record_type"]),
        "collections": {
            COLLECTION_UI_STATE: sum(1 for r in records if r["metadata"]["record_type"] in _STATE_TYPES),
            COLLECTION_UI_TRANSITION: sum(1 for r in records if r["metadata"]["record_type"] in _TRANSITION_TYPES),
        },
        "embedding_model": "all-MiniLM-L6-v2",
        "records_file": "rag/ui_rag_records.jsonl",
        "chroma_upserted": False,
    }
    (rag_dir / "ingestion_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def upsert_to_chroma(output_dir, records):
    """Embed + upsert records into ui_state / ui_transition. Returns a status dict.
    Never raises: on any missing dependency it records the reason and returns."""
    status = {"chroma_upserted": False, "reason": "", "counts": {}}
    try:
        _backend_on_path()
        from app.services.embedding_service import embed_texts_batched, is_embedding_available
        from app.services.vector_store_service import add_documents, get_collection_count
    except Exception as exc:  # noqa: BLE001
        status["reason"] = f"backend RAG services unavailable: {exc}"
        return status
    if not is_embedding_available():
        status["reason"] = "embedding model unavailable"
        return status

    buckets = {COLLECTION_UI_STATE: [], COLLECTION_UI_TRANSITION: []}
    for r in records:
        rt = r["metadata"]["record_type"]
        target = COLLECTION_UI_STATE if rt in _STATE_TYPES else COLLECTION_UI_TRANSITION
        buckets[target].append(r)

    ok_any = False
    for collection, recs in buckets.items():
        if not recs:
            continue
        embeddings = embed_texts_batched([r["document"] for r in recs])
        ok = add_documents(
            collection,
            ids=[r["id"] for r in recs],
            documents=[r["document"] for r in recs],
            metadatas=[_sanitize_metadata(r["metadata"]) for r in recs],
            embeddings=embeddings,
        )
        try:
            status["counts"][collection] = get_collection_count(collection)
        except Exception:  # noqa: BLE001
            status["counts"][collection] = None
        ok_any = ok_any or (ok is not False)

    status["chroma_upserted"] = ok_any
    # reflect the upsert in the on-disk manifest
    manifest_path = Path(output_dir) / "rag" / "ingestion_manifest.json"
    if manifest_path.is_file():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        m["chroma_upserted"] = ok_any
        m["chroma_counts"] = status["counts"]
        manifest_path.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return status


def validate_retrieval(query, *, collection=COLLECTION_UI_TRANSITION, k=3):
    """Query a UI collection to prove structured records are retrievable without
    screenshot filenames. Returns a list of {id, document, metadata, distance}."""
    _backend_on_path()
    from app.services.embedding_service import embed_query
    from app.services.vector_store_service import query_collection

    emb = embed_query(query)
    return query_collection(collection, emb, k=k)


def _count_by(items, keyfn):
    out = {}
    for it in items:
        key = keyfn(it)
        out[key] = out.get(key, 0) + 1
    return out
