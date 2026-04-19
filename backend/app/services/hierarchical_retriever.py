"""Hierarchical retriever — expands semantic search hits with structural context.

After primary vector search returns isolated chunks, this service expands
each hit by fetching parent, children, conref sources, keydef definitions,
and siblings to assemble a context bundle.

Feature flag: HIERARCHICAL_RETRIEVAL_ENABLED (default False)
"""
import os
from typing import Optional

from app.core.structured_logging import get_structured_logger
from app.models.chunk_metadata import (
    ChunkMetadata,
    DocType,
    RetrievalBundle,
    ScoredChunk,
)

logger = get_structured_logger("hierarchical_retriever")

# Authority scores by source type (mirrors grounding_service)
_SOURCE_AUTHORITY = {
    "seed": 0.72,
    "crawl": 0.78,
    "upload": 0.90,
    "jira": 0.50,
    "generated": 0.40,
}

# Default expansion depth
_DEFAULT_EXPAND_DEPTH = int(os.getenv("HIERARCHICAL_EXPAND_DEPTH", "1"))
_DEFAULT_TOKEN_BUDGET = int(os.getenv("HIERARCHICAL_TOKEN_BUDGET", "4000"))
_EXPANSION_TIMEOUT_MS = int(os.getenv("HIERARCHICAL_EXPANSION_TIMEOUT_MS", "500"))


def _estimate_tokens(text: str) -> int:
    """Quick token estimate (3.5 chars/token for regular text)."""
    return max(1, len(text) // 3) if text else 0


def _compute_final_score(
    semantic_sim: float,
    authority: float,
    structural_relevance: float,
    chunk_priority: float,
) -> float:
    """Weighted scoring: semantic 40%, authority 25%, structural 20%, priority 15%."""
    return (
        semantic_sim * 0.40
        + authority * 0.25
        + structural_relevance * 0.20
        + chunk_priority * 0.15
    )


def _score_primary_chunk(
    chunk_id: str,
    content: str,
    metadata: ChunkMetadata,
    similarity: float,
) -> ScoredChunk:
    """Score a primary (direct semantic hit) chunk."""
    authority = _SOURCE_AUTHORITY.get(metadata.source_type, 0.5)
    final = _compute_final_score(similarity, authority, 0.0, metadata.chunk_priority)
    return ScoredChunk(
        chunk_id=chunk_id,
        content=content,
        metadata=metadata,
        semantic_similarity=similarity,
        authority_score=authority,
        structural_relevance=0.0,
        final_score=final,
        relationship_type=None,
    )


def _score_context_chunk(
    chunk_id: str,
    content: str,
    metadata: ChunkMetadata,
    relationship: str,
    primary_similarity: float = 0.0,
) -> ScoredChunk:
    """Score a context (structurally related) chunk."""
    authority = _SOURCE_AUTHORITY.get(metadata.source_type, 0.5)
    # Structural relevance varies by relationship type
    struct_bonus = {
        "parent": 0.8,
        "child": 0.6,
        "conref_source": 0.7,
        "keydef": 0.75,
        "sibling_prev": 0.4,
        "sibling_next": 0.4,
    }.get(relationship, 0.3)

    # Context chunks get a fraction of the primary's semantic score
    inherited_sim = primary_similarity * 0.3
    final = _compute_final_score(inherited_sim, authority, struct_bonus, metadata.chunk_priority)

    return ScoredChunk(
        chunk_id=chunk_id,
        content=content,
        metadata=metadata,
        semantic_similarity=inherited_sim,
        authority_score=authority,
        structural_relevance=struct_bonus,
        final_score=final,
        relationship_type=relationship,
    )


def _deduplicate_chunks(chunks: list[ScoredChunk]) -> list[ScoredChunk]:
    """Deduplicate by content_hash, keeping the highest-scored version."""
    seen: dict[str, ScoredChunk] = {}
    for c in chunks:
        key = c.metadata.content_hash or c.chunk_id
        if key not in seen or c.final_score > seen[key].final_score:
            seen[key] = c
    return sorted(seen.values(), key=lambda x: x.final_score, reverse=True)


def _fit_to_budget(chunks: list[ScoredChunk], budget: int) -> list[ScoredChunk]:
    """Trim chunks to fit within token budget, keeping highest-scored first."""
    result: list[ScoredChunk] = []
    used = 0
    for c in chunks:
        tokens = _estimate_tokens(c.content)
        if used + tokens > budget:
            continue
        result.append(c)
        used += tokens
    return result


async def hierarchical_retrieve(
    query: str,
    *,
    primary_chunks: Optional[list[dict]] = None,
    k: int = 8,
    expand_depth: int = _DEFAULT_EXPAND_DEPTH,
    token_budget: int = _DEFAULT_TOKEN_BUDGET,
    doc_type_filter: Optional[str] = None,
    chunk_lookup_fn=None,
) -> RetrievalBundle:
    """Perform hierarchical retrieval with structural expansion.

    Args:
        query: The user's search query.
        primary_chunks: Pre-retrieved chunks from vector search, each a dict with
            keys: chunk_id, content, metadata (ChunkMetadata dict), similarity.
            If None, caller should do vector search first.
        k: Number of primary chunks to process.
        expand_depth: How many levels of relationships to follow.
        token_budget: Max tokens for the assembled bundle.
        doc_type_filter: Optional filter by document type.
        chunk_lookup_fn: Async function(chunk_ids: list[str]) -> list[dict]
            to fetch chunks by ID for expansion. Returns dicts with
            chunk_id, content, metadata keys.

    Returns:
        RetrievalBundle with primary and context chunks.
    """
    if not primary_chunks:
        return RetrievalBundle(query=query)

    # Limit to top-k
    primaries = primary_chunks[:k]

    # Score primary chunks
    scored_primaries: list[ScoredChunk] = []
    for pc in primaries:
        meta = pc.get("metadata")
        if isinstance(meta, dict):
            meta = ChunkMetadata(**meta)
        elif meta is None:
            meta = ChunkMetadata(chunk_id=pc.get("chunk_id", ""))

        scored = _score_primary_chunk(
            chunk_id=pc.get("chunk_id", ""),
            content=pc.get("content", ""),
            metadata=meta,
            similarity=pc.get("similarity", 0.0),
        )
        scored_primaries.append(scored)

    # Expand context if lookup function provided
    context_chunks: list[ScoredChunk] = []
    relationships_used: set[str] = set()

    if chunk_lookup_fn and expand_depth > 0:
        ids_to_fetch: set[str] = set()
        id_to_relationship: dict[str, tuple[str, float]] = {}  # id -> (relationship, primary_sim)

        for sp in scored_primaries:
            meta = sp.metadata

            # Parent expansion (when chunk needs context bundle)
            if meta.requires_context_bundle and meta.parent_chunk_id:
                pid = meta.parent_chunk_id
                if pid not in ids_to_fetch:
                    ids_to_fetch.add(pid)
                    id_to_relationship[pid] = ("parent", sp.semantic_similarity)

            # Child expansion (for maps/bookmaps)
            if meta.doc_type in (DocType.MAP, DocType.BOOKMAP):
                for cid in meta.child_chunk_ids[:5]:  # Limit children
                    if cid not in ids_to_fetch:
                        ids_to_fetch.add(cid)
                        id_to_relationship[cid] = ("child", sp.semantic_similarity)

            # Conref source expansion
            for cid in meta.conref_source_ids[:3]:
                if cid not in ids_to_fetch:
                    ids_to_fetch.add(cid)
                    id_to_relationship[cid] = ("conref_source", sp.semantic_similarity)

            # Keydef expansion for keyrefs
            # Note: This requires a different lookup — by keydef_keys, not chunk_id.
            # For now, we collect keyref_keys and the caller should resolve them.

            # Sibling expansion
            for sid in [meta.sibling_prev_id, meta.sibling_next_id]:
                if sid and sid not in ids_to_fetch:
                    ids_to_fetch.add(sid)
                    rel = "sibling_prev" if sid == meta.sibling_prev_id else "sibling_next"
                    id_to_relationship[sid] = (rel, sp.semantic_similarity)

        # Fetch expanded chunks
        if ids_to_fetch:
            try:
                fetched = await chunk_lookup_fn(list(ids_to_fetch))
                for fc in fetched:
                    fid = fc.get("chunk_id", "")
                    rel, prim_sim = id_to_relationship.get(fid, ("unknown", 0.0))
                    relationships_used.add(rel)

                    fmeta = fc.get("metadata")
                    if isinstance(fmeta, dict):
                        fmeta = ChunkMetadata(**fmeta)
                    elif fmeta is None:
                        fmeta = ChunkMetadata(chunk_id=fid)

                    context_chunks.append(_score_context_chunk(
                        chunk_id=fid,
                        content=fc.get("content", ""),
                        metadata=fmeta,
                        relationship=rel,
                        primary_similarity=prim_sim,
                    ))
            except Exception as e:
                logger.warning(
                    f"Hierarchical expansion failed, returning primary chunks only: {e}"
                )

    # Combine, deduplicate, and fit to budget
    all_chunks = scored_primaries + context_chunks
    all_chunks = _deduplicate_chunks(all_chunks)

    # Split back into primary and context after dedup
    primary_ids = {sp.chunk_id for sp in scored_primaries}
    final_primaries = [c for c in all_chunks if c.chunk_id in primary_ids]
    final_context = [c for c in all_chunks if c.chunk_id not in primary_ids]

    # Apply token budget
    final_primaries = _fit_to_budget(final_primaries, token_budget * 2 // 3)
    remaining_budget = token_budget - sum(_estimate_tokens(c.content) for c in final_primaries)
    final_context = _fit_to_budget(final_context, max(0, remaining_budget))

    total_tokens = sum(_estimate_tokens(c.content) for c in final_primaries + final_context)
    root_docs = list({c.metadata.root_doc_id for c in all_chunks if c.metadata.root_doc_id})

    return RetrievalBundle(
        primary_chunks=final_primaries,
        context_chunks=final_context,
        total_tokens=total_tokens,
        root_docs=root_docs,
        relationships_used=sorted(relationships_used),
        query=query,
    )


def format_bundle_for_prompt(bundle: RetrievalBundle, max_chars: int = 8000) -> str:
    """Format a retrieval bundle as context text for the LLM prompt."""
    if not bundle.primary_chunks and not bundle.context_chunks:
        return ""

    sections: list[str] = []
    char_count = 0

    # Primary chunks first
    for i, chunk in enumerate(bundle.primary_chunks, 1):
        header = f"[{i}] {chunk.metadata.doc_type}/{chunk.metadata.element_name}"
        if chunk.metadata.section_title:
            header += f": {chunk.metadata.section_title}"
        text = f"{header}\n{chunk.content}"
        if char_count + len(text) > max_chars:
            break
        sections.append(text)
        char_count += len(text)

    # Context chunks (structural neighbors)
    if bundle.context_chunks:
        sections.append("\n--- Structural context ---")
        for chunk in bundle.context_chunks:
            rel = chunk.relationship_type or "related"
            header = f"[{rel}] {chunk.metadata.doc_type}/{chunk.metadata.element_name}"
            if chunk.metadata.section_title:
                header += f": {chunk.metadata.section_title}"
            text = f"{header}\n{chunk.content}"
            if char_count + len(text) > max_chars:
                break
            sections.append(text)
            char_count += len(text)

    return "\n\n".join(sections)
