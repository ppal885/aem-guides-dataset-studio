"""Load and upsert authoritative curated DITA specification chunks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.embedding_service import embed_texts, embed_texts_batched, is_embedding_available
from app.services.vector_store_service import (
    CHROMA_COLLECTION_DITA_SPEC,
    add_documents as chroma_add_documents,
    is_chroma_available,
)


CURATED_CHUNKS_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_gap_chunks.json"
REQUIRED_FIELDS = {
    "id",
    "title",
    "construct",
    "section",
    "source_url",
    "spec_version",
    "content_type",
    "content",
}
OASIS_DITA_PREFIX = "https://docs.oasis-open.org/dita/"


def load_curated_dita_spec_chunks(path: Path = CURATED_CHUNKS_PATH) -> list[dict[str, Any]]:
    """Load validated OASIS-backed DITA specification chunks."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"expected JSON array in {path}")

    records: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, record in enumerate(raw):
        if not isinstance(record, dict):
            raise ValueError(f"record {index} must be an object")
        missing = sorted(REQUIRED_FIELDS - record.keys())
        if missing:
            raise ValueError(f"record {index} missing required fields: {', '.join(missing)}")
        record_id = str(record["id"]).strip()
        if not record_id or record_id in seen_ids:
            raise ValueError(f"record {index} has an empty or duplicate id: {record_id!r}")
        source_url = str(record["source_url"]).strip()
        if not source_url.startswith(OASIS_DITA_PREFIX):
            raise ValueError(f"record {record_id} must use an authoritative OASIS DITA URL")
        content = str(record["content"]).strip()
        if len(content) < 200:
            raise ValueError(f"record {record_id} content is too short for reliable retrieval")
        seen_ids.add(record_id)
        records.append({
            **record,
            "id": record_id,
            "source_url": source_url,
            "content": content,
            "curated": True,
        })
    return records


def curated_chunk_metadata(record: dict[str, Any]) -> dict[str, str | bool]:
    """Return Chroma-compatible scalar metadata for a curated record."""
    return {
        "source_url": str(record["source_url"]),
        "page": "",
        "title": str(record["title"]),
        "construct": str(record["construct"]),
        "section": str(record["section"]),
        "spec_version": str(record["spec_version"]),
        "content_type": str(record["content_type"]),
        "curated": True,
    }


def upsert_curated_dita_spec_chunks(*, batch_size: int = 64) -> int:
    """Embed and upsert curated records into the dedicated DITA spec collection."""
    records = load_curated_dita_spec_chunks()
    if not is_embedding_available():
        raise RuntimeError("DITA embedding model is unavailable")
    if not is_chroma_available():
        raise RuntimeError("ChromaDB is unavailable")

    upserted = 0
    for start in range(0, len(records), max(1, batch_size)):
        batch = records[start : start + max(1, batch_size)]
        texts = [str(record["content"]) for record in batch]
        embeddings = embed_texts_batched(texts) if len(texts) > 64 else embed_texts(texts)
        if embeddings is None or len(embeddings) != len(batch):
            raise RuntimeError(f"embedding failed for curated batch starting at {start}")
        vectors = [embedding.tolist() if hasattr(embedding, "tolist") else list(embedding) for embedding in embeddings]
        stored = chroma_add_documents(
            CHROMA_COLLECTION_DITA_SPEC,
            ids=[str(record["id"]) for record in batch],
            documents=texts,
            metadatas=[curated_chunk_metadata(record) for record in batch],
            embeddings=vectors,
        )
        if not stored:
            raise RuntimeError(f"Chroma upsert failed for curated batch starting at {start}")
        upserted += len(batch)
    return upserted
