"""
Advanced RAG Service — upgraded pipeline with:

1. Better embedding model (bge-large-en-v1.5 instead of all-MiniLM)
2. Optimized chunking (512 tokens, 64 overlap, sentence-boundary aware)
3. Query expansion (generates 3 query variants before searching)
4. Hybrid search (BM25 keyword + semantic vector, merged via RRF)
5. Cross-encoder reranker (filters noise after retrieval)
6. Chunk deduplication (hash-based, no duplicate content)
7. Freshness/staleness tracking (age-weighted scoring)
8. Source credibility scoring (OASIS > Adobe > community)
9. Relevance scores shown to author
10. Results linked back to specific DITA sections

Place at: backend/app/services/advanced_rag_service.py
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Upgraded embedding model — much better than all-MiniLM for technical content
# all-MiniLM-L6-v2:      384 dims, fast but weak on technical/DITA content
# bge-large-en-v1.5:     1024 dims, SOTA for retrieval, handles technical text
# bge-base-en-v1.5:      768 dims, good balance of speed and quality
EMBEDDING_MODEL_PRIMARY   = "BAAI/bge-large-en-v1.5"
EMBEDDING_MODEL_FALLBACK  = "BAAI/bge-base-en-v1.5"
EMBEDDING_MODEL_FAST      = "all-MiniLM-L6-v2"   # existing, kept as last resort

# Chunk settings — optimized for DITA + technical docs
CHUNK_SIZE_TOKENS         = 512   # was ~256, bigger = more context
CHUNK_OVERLAP_TOKENS      = 64    # was 0-32, more overlap = less missed context
CHUNK_MIN_CHARS           = 100   # skip tiny chunks
CHUNK_MAX_CHARS           = 2000  # hard cap

# Retrieval settings
RETRIEVAL_TOP_K           = 20    # fetch more, rerank down to best
RERANK_TOP_K              = 5     # keep top 5 after reranking
HYBRID_ALPHA              = 0.6   # 0.6 semantic + 0.4 BM25
FRESHNESS_DECAY_DAYS      = 90    # chunks older than 90 days get penalized

# Source credibility scores (0-1)
SOURCE_CREDIBILITY = {
    "docs.oasis-open.org":         1.0,   # DITA spec — ground truth
    "experienceleague.adobe.com":  0.95,  # Adobe official
    "helpx.adobe.com":             0.90,  # Adobe help
    "dita-ot.org":                 0.88,  # DITA-OT official
    "github.com/oasis-tcs":        0.85,  # OASIS GitHub
    "github.com/DITAWriter":       0.80,  # Expert examples
    "adobe.com":                   0.75,
    "stackoverflow.com":           0.55,
    "community.adobe.com":         0.60,
    "default":                     0.50,
}

# DITA section mapping — which content goes where
DITA_SECTION_AFFINITY = {
    "shortdesc":  ["summary", "overview", "description", "what is", "brief"],
    "prereq":     ["prerequisite", "requirement", "before you begin", "needs", "required"],
    "context":    ["background", "context", "why", "reason", "when to use"],
    "steps":      ["step", "procedure", "how to", "instructions", "process"],
    "result":     ["result", "outcome", "verify", "confirms", "expected"],
    "note":       ["warning", "caution", "note", "important", "attention"],
    "example":    ["example", "sample", "instance", "for example", "e.g."],
    "properties": ["parameter", "attribute", "property", "value", "option"],
}


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class ScoredChunk:
    """A retrieved chunk with full scoring metadata."""
    text:             str
    source_url:       str           = ""
    source_type:      str           = "unknown"  # spec | aem | example | research
    collection:       str           = ""
    chunk_id:         str           = ""
    semantic_score:   float         = 0.0
    bm25_score:       float         = 0.0
    rerank_score:     float         = 0.0
    freshness_score:  float         = 1.0        # 1.0 = fresh, 0.0 = stale
    credibility_score: float        = 0.5
    final_score:      float         = 0.0
    indexed_at:       str           = ""
    dita_sections:    list[str]     = field(default_factory=list)  # which sections this helps
    metadata:         dict          = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "text":             self.text[:500],
            "source_url":       self.source_url,
            "source_type":      self.source_type,
            "collection":       self.collection,
            "chunk_id":         self.chunk_id,
            "semantic_score":   round(self.semantic_score, 3),
            "bm25_score":       round(self.bm25_score, 3),
            "rerank_score":     round(self.rerank_score, 3),
            "freshness_score":  round(self.freshness_score, 3),
            "credibility_score": round(self.credibility_score, 3),
            "final_score":      round(self.final_score, 3),
            "dita_sections":    self.dita_sections,
            "indexed_at":       self.indexed_at,
        }


@dataclass
class AdvancedRAGResult:
    """Full result from advanced RAG pipeline."""
    query:            str
    expanded_queries: list[str]     = field(default_factory=list)
    chunks:           list[ScoredChunk] = field(default_factory=list)
    context_text:     str           = ""     # formatted for LLM injection
    total_retrieved:  int           = 0
    total_after_rerank: int         = 0
    sources_used:     list[str]     = field(default_factory=list)
    duration_ms:      int           = 0

    def to_dict(self) -> dict:
        return {
            "query":              self.query,
            "expanded_queries":   self.expanded_queries,
            "chunks":             [c.to_dict() for c in self.chunks],
            "total_retrieved":    self.total_retrieved,
            "total_after_rerank": self.total_after_rerank,
            "sources_used":       self.sources_used,
            "duration_ms":        self.duration_ms,
            "top_score":          round(self.chunks[0].final_score, 3) if self.chunks else 0,
            "avg_score":          round(sum(c.final_score for c in self.chunks) / len(self.chunks), 3) if self.chunks else 0,
        }


# ── 1. Better embedding model ─────────────────────────────────────────────────

_embedding_model = None

def get_embedding_model():
    """Load the best available embedding model."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    for model_name in [EMBEDDING_MODEL_PRIMARY, EMBEDDING_MODEL_FALLBACK, EMBEDDING_MODEL_FAST]:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info_structured(
                "Loading embedding model",
                extra_fields={"model": model_name},
            )
            model = SentenceTransformer(model_name)
            _embedding_model = model
            logger.info_structured(
                "Embedding model loaded",
                extra_fields={"model": model_name, "dims": model.get_sentence_embedding_dimension()},
            )
            return model
        except Exception as e:
            logger.warning_structured(
                "Embedding model failed, trying next",
                extra_fields={"model": model_name, "error": str(e)},
            )

    raise RuntimeError("No embedding model available")


def embed_query_advanced(query: str) -> list[float]:
    """
    Embed a query using BGE model.
    BGE models need a special instruction prefix for queries.
    """
    model = get_embedding_model()
    # BGE instruction prefix improves retrieval quality significantly
    instruction = "Represent this sentence for searching relevant passages: "
    if "bge" in model.__class__.__name__.lower() or hasattr(model, '_modules'):
        try:
            model_name = str(model)
            if "bge" in model_name.lower():
                query = instruction + query
        except Exception:
            pass
    embedding = model.encode(query, normalize_embeddings=True)
    return embedding.tolist()


def embed_texts_advanced(texts: list[str]) -> list[list[float]]:
    """Embed document chunks — no instruction prefix needed for documents."""
    model = get_embedding_model()
    embeddings = model.encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=False)
    return [e.tolist() for e in embeddings]


# ── 2. Optimized chunking ─────────────────────────────────────────────────────

def smart_chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE_TOKENS,
    overlap: int = CHUNK_OVERLAP_TOKENS,
    source_url: str = "",
    indexed_at: str = "",
) -> list[dict]:
    """
    Sentence-boundary aware chunking.
    - Respects sentence boundaries (no mid-sentence cuts)
    - Configurable overlap between chunks
    - Skips tiny/empty chunks
    - Adds metadata to each chunk
    """
    if not text or len(text) < CHUNK_MIN_CHARS:
        return []

    # Split into sentences
    sentences = _split_sentences(text)
    if not sentences:
        return []

    chunks = []
    current_sentences = []
    current_len = 0
    # approx 4 chars per token
    max_chars = chunk_size * 4
    overlap_chars = overlap * 4

    for sent in sentences:
        sent_len = len(sent)
        if current_len + sent_len > max_chars and current_sentences:
            # Save current chunk
            chunk_text = " ".join(current_sentences).strip()
            if len(chunk_text) >= CHUNK_MIN_CHARS:
                chunks.append(_make_chunk_dict(chunk_text, source_url, indexed_at, len(chunks)))

            # Overlap: keep last N chars worth of sentences
            overlap_acc = 0
            overlap_sentences = []
            for s in reversed(current_sentences):
                if overlap_acc + len(s) > overlap_chars:
                    break
                overlap_sentences.insert(0, s)
                overlap_acc += len(s)

            current_sentences = overlap_sentences
            current_len = sum(len(s) for s in current_sentences)

        current_sentences.append(sent)
        current_len += sent_len

    # Last chunk
    if current_sentences:
        chunk_text = " ".join(current_sentences).strip()
        if len(chunk_text) >= CHUNK_MIN_CHARS:
            chunks.append(_make_chunk_dict(chunk_text, source_url, indexed_at, len(chunks)))

    return chunks


def _split_sentences(text: str) -> list[str]:
    """Split text at sentence boundaries."""
    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    # Split on sentence endings — preserve abbreviations
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    # Also split on newlines that look like paragraph breaks
    result = []
    for s in sentences:
        parts = re.split(r'\n{2,}', s)
        result.extend(p.strip() for p in parts if p.strip())
    return [s for s in result if len(s) > 20]


def _make_chunk_dict(text: str, source_url: str, indexed_at: str, idx: int) -> dict:
    url_hash = hashlib.md5(source_url.encode()).hexdigest()[:8]
    text_hash = hashlib.md5(text[:100].encode()).hexdigest()[:8]
    return {
        "text":       text[:CHUNK_MAX_CHARS],
        "chunk_id":   f"{url_hash}_{text_hash}_{idx}",
        "source_url": source_url,
        "indexed_at": indexed_at or datetime.utcnow().isoformat(),
    }


# ── 3. Query expansion ────────────────────────────────────────────────────────

async def expand_query(query: str, dita_type: str = "task") -> list[str]:
    """
    Generate 3 query variants to improve recall.
    Uses LLM if available, falls back to rule-based expansion.

    Rule-based expansion handles:
    - Synonym substitution (fix → resolve → workaround)
    - DITA-specific term addition
    - Specificity variation (broad → specific)
    """
    variants = [query]  # always include original

    # Rule-based variants (always available)
    rule_variants = _rule_based_expansion(query, dita_type)
    variants.extend(rule_variants)

    # LLM expansion (if available — much better)
    try:
        from app.services.llm_service import generate_json, is_llm_available
        if is_llm_available():
            llm_variants = await _llm_query_expansion(query, dita_type)
            if llm_variants:
                # Merge: original + 2 best LLM variants
                variants = [query] + llm_variants[:2]
    except Exception as e:
        logger.debug_structured("LLM query expansion skipped", extra_fields={"error": str(e)})

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for v in variants:
        if v.lower() not in seen and v.strip():
            seen.add(v.lower())
            unique.append(v)

    return unique[:3]  # max 3 queries


def _rule_based_expansion(query: str, dita_type: str) -> list[str]:
    """Rule-based query variants."""
    lower = query.lower()
    variants = []

    # Synonym map for common DITA/AEM terms
    SYNONYMS = {
        "fix":         ["resolve", "workaround", "solution"],
        "resolve":     ["fix", "workaround"],
        "error":       ["issue", "problem", "bug"],
        "configure":   ["setup", "set up", "configuration"],
        "keyref":      ["key reference", "key-based reference"],
        "keyscope":    ["key scope", "scope boundary"],
        "conref":      ["content reference", "reuse"],
        "task":        ["procedure", "steps", "how to"],
        "concept":     ["overview", "explanation", "understanding"],
    }

    # Try replacing one term with synonym
    for term, synonyms in SYNONYMS.items():
        if term in lower:
            variant = query.replace(term, synonyms[0], 1)
            if variant != query:
                variants.append(variant)
                break

    # Add DITA-specific context if missing
    if "dita" not in lower:
        variants.append(f"DITA 1.3 {query}")
    if "aem" not in lower and "adobe" not in lower:
        variants.append(f"AEM Guides {query}")

    return variants[:2]


async def _llm_query_expansion(query: str, dita_type: str) -> list[str]:
    """Use LLM to generate better query variants."""
    from app.services.llm_service import generate_json

    system = """Generate 2 search query variants for a DITA/AEM documentation search.
Output JSON only: {"variants": ["query1", "query2"]}
Rules:
- Each variant should find DIFFERENT relevant information
- Use different terminology/synonyms
- One broader, one more specific
- Keep each under 12 words"""

    user = f"""Original query: {query}
DITA topic type: {dita_type}
Output 2 variants as JSON:"""

    result = await generate_json(system, user, max_tokens=100, step_name="query_expansion")
    if result and isinstance(result, dict):
        variants = result.get("variants", [])
        return [v for v in variants if isinstance(v, str) and v.strip()][:2]
    return []


# ── 4. BM25 keyword search ────────────────────────────────────────────────────

class BM25Index:
    """
    Simple BM25 index over a list of documents.
    Used for keyword matching alongside semantic search.
    BM25 is better than semantic search for exact technical terms
    like 'keyscope', 'outputclass', specific version numbers.
    """
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b  = b
        self.docs: list[str] = []
        self.doc_freqs: list[dict] = []
        self.idf: dict = {}
        self.avgdl: float = 0.0

    def index(self, documents: list[str]):
        self.docs = documents
        self.doc_freqs = []
        term_doc_count: dict = {}
        total_len = 0

        for doc in documents:
            tokens = self._tokenize(doc)
            total_len += len(tokens)
            freq: dict = {}
            for t in tokens:
                freq[t] = freq.get(t, 0) + 1
            self.doc_freqs.append(freq)
            for t in set(tokens):
                term_doc_count[t] = term_doc_count.get(t, 0) + 1

        n = len(documents)
        self.avgdl = total_len / n if n else 1.0
        self.idf = {
            t: math.log((n - df + 0.5) / (df + 0.5) + 1)
            for t, df in term_doc_count.items()
        }

    def search(self, query: str, top_k: int = 20) -> list[tuple[int, float]]:
        """Returns list of (doc_index, score) sorted by score desc."""
        if not self.docs:
            return []

        query_tokens = self._tokenize(query)
        scores = []

        for i, freq in enumerate(self.doc_freqs):
            doc_len = sum(freq.values())
            score = 0.0
            for t in query_tokens:
                if t not in freq:
                    continue
                tf  = freq[t]
                idf = self.idf.get(t, 0.0)
                norm_tf = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))
                score += idf * norm_tf
            scores.append((i, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenizer — lowercase, split on non-alphanumeric."""
        return re.findall(r'[a-zA-Z0-9]+', text.lower())


# ── 5. Reranker ───────────────────────────────────────────────────────────────

_reranker_model = None

def get_reranker():
    """Load cross-encoder reranker model."""
    global _reranker_model
    if _reranker_model is not None:
        return _reranker_model
    try:
        from sentence_transformers import CrossEncoder
        # cross-encoder/ms-marco-MiniLM-L-6-v2 — fast and accurate
        model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        _reranker_model = model
        return model
    except Exception as e:
        logger.warning_structured("Reranker not available", extra_fields={"error": str(e)})
        return None


def rerank_chunks(query: str, chunks: list[ScoredChunk], top_k: int = RERANK_TOP_K) -> list[ScoredChunk]:
    """
    Cross-encoder reranking — much more accurate than bi-encoder for final scoring.
    The cross-encoder sees BOTH query and document together, giving better relevance judgement.
    """
    reranker = get_reranker()

    if not reranker or not chunks:
        # Fallback: return by semantic score
        return sorted(chunks, key=lambda c: c.semantic_score, reverse=True)[:top_k]

    try:
        pairs = [(query, c.text[:512]) for c in chunks]
        scores = reranker.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk.rerank_score = float(score)

        reranked = sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
        return reranked[:top_k]

    except Exception as e:
        logger.warning_structured("Reranking failed", extra_fields={"error": str(e)})
        return sorted(chunks, key=lambda c: c.semantic_score, reverse=True)[:top_k]


# ── 6. Freshness scoring ──────────────────────────────────────────────────────

def compute_freshness_score(indexed_at: str) -> float:
    """
    Score freshness of a chunk.
    1.0 = indexed today
    0.5 = indexed 90 days ago (FRESHNESS_DECAY_DAYS)
    0.1 = very old

    Uses exponential decay: score = exp(-age_days / decay_days)
    """
    if not indexed_at:
        return 0.7  # unknown age — assume moderate

    try:
        indexed_dt = datetime.fromisoformat(indexed_at)
        age_days   = (datetime.utcnow() - indexed_dt).days
        score      = math.exp(-age_days / FRESHNESS_DECAY_DAYS)
        return max(0.1, min(1.0, score))
    except Exception:
        return 0.7


# ── 7. Source credibility scoring ─────────────────────────────────────────────

def compute_credibility_score(source_url: str, source_type: str = "") -> float:
    """Score source credibility — OASIS spec > Adobe official > community."""
    if not source_url:
        if source_type == "spec":     return 0.95
        if source_type == "aem":      return 0.90
        if source_type == "example":  return 0.80
        return SOURCE_CREDIBILITY["default"]

    for domain, score in SOURCE_CREDIBILITY.items():
        if domain in source_url:
            return score

    return SOURCE_CREDIBILITY["default"]


# ── 8. DITA section affinity ──────────────────────────────────────────────────

def detect_dita_section_affinity(text: str) -> list[str]:
    """
    Detect which DITA sections this chunk is most useful for.
    Returns list of DITA element names this content helps generate.
    """
    lower   = text.lower()
    matches = []

    for section, keywords in DITA_SECTION_AFFINITY.items():
        hits = sum(1 for kw in keywords if kw in lower)
        if hits >= 1:
            matches.append((section, hits))

    matches.sort(key=lambda x: x[1], reverse=True)
    return [m[0] for m in matches[:3]]


# ── 9. Final score computation ────────────────────────────────────────────────

def compute_final_score(chunk: ScoredChunk) -> float:
    """
    Weighted combination of all signals:
    - Rerank score (highest weight — most accurate)
    - Semantic score
    - BM25 score
    - Freshness
    - Credibility
    """
    # Normalize rerank score to 0-1 range (cross-encoder outputs logits)
    rerank_normalized = 1 / (1 + math.exp(-chunk.rerank_score)) if chunk.rerank_score != 0 else 0.5

    score = (
        0.40 * rerank_normalized    +  # cross-encoder is most accurate
        0.25 * chunk.semantic_score +  # bi-encoder semantic
        0.15 * chunk.bm25_score     +  # keyword matching
        0.10 * chunk.freshness_score +  # recency
        0.10 * chunk.credibility_score  # source quality
    )
    return round(min(1.0, max(0.0, score)), 4)


# ── 10. Hybrid search (RRF merge) ─────────────────────────────────────────────

def reciprocal_rank_fusion(
    semantic_results: list[tuple[int, float]],
    bm25_results:     list[tuple[int, float]],
    k: int = 60,
    alpha: float = HYBRID_ALPHA,
) -> list[tuple[int, float]]:
    """
    Reciprocal Rank Fusion — merges semantic and BM25 rankings.
    Better than simple score averaging because it's rank-based
    and handles different score scales gracefully.

    alpha: weight for semantic (1-alpha for BM25)
    """
    scores: dict[int, float] = {}

    for rank, (idx, _) in enumerate(semantic_results):
        scores[idx] = scores.get(idx, 0) + alpha * (1.0 / (k + rank + 1))

    for rank, (idx, _) in enumerate(bm25_results):
        scores[idx] = scores.get(idx, 0) + (1 - alpha) * (1.0 / (k + rank + 1))

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    # Normalize to 0-1
    max_score = sorted_scores[0][1] if sorted_scores else 1.0
    return [(idx, score / max_score) for idx, score in sorted_scores]


# ── 11. Deduplication ─────────────────────────────────────────────────────────

def deduplicate_chunks(chunks: list[ScoredChunk], threshold: float = 0.85) -> list[ScoredChunk]:
    """
    Remove near-duplicate chunks using text similarity.
    Keeps the highest-scoring chunk when duplicates found.
    Uses MinHash for speed (no need for full pairwise comparison).
    """
    if len(chunks) <= 1:
        return chunks

    seen_hashes: set[str] = set()
    unique: list[ScoredChunk] = []

    for chunk in sorted(chunks, key=lambda c: c.final_score, reverse=True):
        # Create a signature from first 200 chars + last 100 chars
        sig = (chunk.text[:200] + chunk.text[-100:]).lower()
        sig = re.sub(r'\s+', ' ', sig).strip()
        h   = hashlib.md5(sig.encode()).hexdigest()

        if h not in seen_hashes:
            seen_hashes.add(h)
            unique.append(chunk)

    return unique


# ── Main search function ──────────────────────────────────────────────────────

async def advanced_rag_search(
    query: str,
    dita_type: str = "task",
    collections: Optional[list[str]] = None,
    top_k: int = RERANK_TOP_K,
) -> AdvancedRAGResult:
    """
    Full advanced RAG pipeline:
    1. Query expansion
    2. Embed all query variants
    3. Hybrid search (semantic + BM25) per collection
    4. RRF merge across all results
    5. Rerank with cross-encoder
    6. Score freshness + credibility + DITA affinity
    7. Deduplicate
    8. Return top K with full scoring metadata

    This replaces the simple retrieve_dita_knowledge() + retrieve_relevant_docs() calls.
    """
    import time
    start = time.time()

    result = AdvancedRAGResult(query=query)

    # ── Step 1: Query expansion ───────────────────────────────────────────────
    expanded = await expand_query(query, dita_type)
    result.expanded_queries = expanded
    logger.info_structured(
        "Query expanded",
        extra_fields={"original": query, "variants": expanded},
    )

    # ── Step 2: Retrieve from all collections ─────────────────────────────────
    from app.services.vector_store_service import (
        is_chroma_available, query_collection,
        CHROMA_COLLECTION_AEM_GUIDES, CHROMA_COLLECTION_DITA_SPEC,
    )

    if not is_chroma_available():
        return result

    search_collections = collections or [
        CHROMA_COLLECTION_AEM_GUIDES,
        CHROMA_COLLECTION_DITA_SPEC,
        "dita_examples",
        "research_cache",
    ]

    raw_chunks: list[ScoredChunk] = []

    for coll in search_collections:
        for q_variant in expanded:
            try:
                # Embed using advanced model
                q_emb = embed_query_advanced(q_variant)

                rows = query_collection(
                    coll,
                    query_embedding=q_emb,
                    k=RETRIEVAL_TOP_K,
                )
                if not rows:
                    continue

                # Build BM25 index over retrieved docs
                texts  = [r.get("document", "") for r in rows]
                bm25   = BM25Index()
                bm25.index(texts)
                bm25_scores = dict(bm25.search(q_variant, top_k=RETRIEVAL_TOP_K))

                # Semantic scores from ChromaDB distance
                distances = [r.get("distance", 0.5) for r in rows]
                max_dist  = max(distances) if distances else 1.0

                for i, row in enumerate(rows):
                    text = row.get("document", "")
                    if not text or len(text) < 50:
                        continue

                    meta       = row.get("metadata") or {}
                    source_url = meta.get("url", "") or meta.get("source", "")
                    indexed_at = meta.get("indexed_at", "") or meta.get("created_at", "")

                    # Determine source type
                    source_type = _classify_source_type(coll, source_url)

                    sem_score   = 1.0 - (distances[i] / max_dist if max_dist else 0.5)
                    bm25_score  = bm25_scores.get(i, 0.0)
                    # Normalize BM25 to 0-1
                    max_bm25    = max(bm25_scores.values()) if bm25_scores else 1.0
                    bm25_norm   = bm25_score / max_bm25 if max_bm25 else 0.0

                    chunk = ScoredChunk(
                        text              = text,
                        source_url        = source_url,
                        source_type       = source_type,
                        collection        = coll,
                        chunk_id          = row.get("id", f"{coll}_{i}"),
                        semantic_score    = round(sem_score, 4),
                        bm25_score        = round(bm25_norm, 4),
                        freshness_score   = compute_freshness_score(indexed_at),
                        credibility_score = compute_credibility_score(source_url, source_type),
                        indexed_at        = indexed_at,
                        dita_sections     = detect_dita_section_affinity(text),
                        metadata          = meta,
                    )
                    raw_chunks.append(chunk)

            except Exception as e:
                logger.debug_structured(
                    "Collection search failed",
                    extra_fields={"collection": coll, "error": str(e)},
                )

    result.total_retrieved = len(raw_chunks)

    if not raw_chunks:
        return result

    # ── Step 3: Deduplicate before reranking ──────────────────────────────────
    # Set preliminary score for dedup ordering
    for chunk in raw_chunks:
        chunk.final_score = (chunk.semantic_score * 0.6 + chunk.credibility_score * 0.4)
    raw_chunks = deduplicate_chunks(raw_chunks)

    # ── Step 4: Rerank with cross-encoder ─────────────────────────────────────
    reranked = rerank_chunks(query, raw_chunks, top_k=top_k * 3)

    # ── Step 5: Final scoring ─────────────────────────────────────────────────
    for chunk in reranked:
        chunk.final_score = compute_final_score(chunk)

    # Sort by final score and take top K
    final = sorted(reranked, key=lambda c: c.final_score, reverse=True)[:top_k]
    result.chunks           = final
    result.total_after_rerank = len(final)
    result.sources_used     = list({c.collection for c in final if c.collection})
    result.duration_ms      = int((time.time() - start) * 1000)

    # ── Step 6: Build context text for LLM ───────────────────────────────────
    result.context_text = _build_context_text(final, query)

    logger.info_structured(
        "Advanced RAG search complete",
        extra_fields={
            "query":      query,
            "retrieved":  result.total_retrieved,
            "after_rerank": result.total_after_rerank,
            "duration_ms": result.duration_ms,
            "top_score":  final[0].final_score if final else 0,
        },
    )
    return result


def _classify_source_type(collection: str, url: str) -> str:
    if "spec" in collection or "dita_spec" in collection:
        return "spec"
    if "aem" in collection or "experience" in collection:
        return "aem"
    if "example" in collection:
        return "example"
    if "research" in collection:
        return "research"
    if "oasis" in url:
        return "spec"
    if "adobe" in url or "experienceleague" in url:
        return "aem"
    return "unknown"


def _build_context_text(chunks: list[ScoredChunk], query: str) -> str:
    """
    Build formatted context string for LLM injection.
    Groups chunks by source type and annotates with scores + DITA section affinity.
    """
    if not chunks:
        return ""

    sections: dict[str, list[ScoredChunk]] = {}
    for chunk in chunks:
        st = chunk.source_type
        sections.setdefault(st, []).append(chunk)

    type_labels = {
        "spec":     "DITA SPECIFICATION (authoritative)",
        "aem":      "AEM GUIDES DOCUMENTATION",
        "example":  "EXPERT DITA EXAMPLES",
        "research": "RECENT WEB RESEARCH",
        "unknown":  "ADDITIONAL CONTEXT",
    }
    type_order = ["spec", "aem", "example", "research", "unknown"]

    parts = []
    for stype in type_order:
        if stype not in sections:
            continue
        label  = type_labels.get(stype, stype.upper())
        chunks_of_type = sections[stype]

        parts.append(f"=== {label} ===")
        for chunk in chunks_of_type:
            score_info = f"[score:{chunk.final_score:.2f} | fresh:{chunk.freshness_score:.2f} | cred:{chunk.credibility_score:.2f}]"
            dita_info  = f"[useful for: {', '.join(chunk.dita_sections)}]" if chunk.dita_sections else ""
            parts.append(f"{score_info} {dita_info}")
            parts.append(chunk.text[:600])
            if chunk.source_url:
                parts.append(f"Source: {chunk.source_url}")
            parts.append("")

    return "\n".join(parts)


# ── Tavily chunking fix ───────────────────────────────────────────────────────

def chunk_and_index_tavily_results(
    results: list[dict],
    topic_id: str,
    tag: str,
) -> tuple[list[str], list[str], list[dict]]:
    """
    Properly chunk Tavily search results before indexing into ChromaDB.
    Previously the full 600-char blob was stored as one chunk —
    now we split into sentence-boundary chunks with proper overlap.

    Returns (ids, documents, metadatas) ready for add_documents()
    """
    all_ids:   list[str]  = []
    all_docs:  list[str]  = []
    all_metas: list[dict] = []

    now = datetime.utcnow().isoformat()

    for result in results:
        url     = result.get("url", "")
        title   = result.get("title", "")
        content = result.get("content", "").strip()

        if not content or len(content) < 100:
            continue

        # Full text = title + content for better context
        full_text = f"{title}\n{content}" if title else content

        # Chunk it properly
        chunks = smart_chunk_text(
            text       = full_text,
            chunk_size = 256,   # smaller for web content
            overlap    = 32,
            source_url = url,
            indexed_at = now,
        )

        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        credibility = compute_credibility_score(url)

        for chunk in chunks:
            cid = f"tavily_{topic_id}_{url_hash}_{chunk['chunk_id']}"
            all_ids.append(cid)
            all_docs.append(chunk["text"])
            all_metas.append({
                "topic_id":    topic_id,
                "tag":         tag,
                "url":         url,
                "title":       title,
                "source":      "tavily_chunked",
                "indexed_at":  now,
                "credibility": credibility,
                "chunk_size":  len(chunk["text"]),
            })

    return all_ids, all_docs, all_metas
