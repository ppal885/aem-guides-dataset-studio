# ============================================================
# RAG UPGRADE SETUP
# Run these commands from your project root with venv active
# ============================================================

# 1. Install new dependencies
pip install --break-system-packages \
    sentence-transformers>=2.7.0 \
    "sentence-transformers[cross-encoder]" \
    rank-bm25>=0.2.2 \
    torch>=2.0.0 \
    transformers>=4.40.0

# 2. Download the models (first run will auto-download, ~1.3GB total)
# BGE-large primary embedding model (~1.2GB)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en-v1.5')"

# BGE-base fallback (~400MB)
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"

# Cross-encoder reranker (~100MB)
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# 3. Re-index your existing ChromaDB collections with new embeddings
# Run in Cursor Agent:
# force_reindex_rag()

# ============================================================
# ADD TO requirements.txt:
# ============================================================
# sentence-transformers>=2.7.0
# rank-bm25>=0.2.2
# torch>=2.0.0
# transformers>=4.40.0

# ============================================================
# ADD TO .env:
# ============================================================
# RAG_EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
# RAG_RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
# RAG_CHUNK_SIZE=512
# RAG_CHUNK_OVERLAP=64
# RAG_HYBRID_ALPHA=0.6
# RAG_TOP_K_RETRIEVE=20
# RAG_TOP_K_RERANK=5

# ============================================================
# FILES TO COPY:
# ============================================================
# advanced_rag_service.py    → backend/app/services/advanced_rag_service.py
# query_executor_advanced.py → backend/app/services/query_executor.py  (REPLACE)

# ============================================================
# EXPECTED QUALITY IMPROVEMENT:
# ============================================================
# Metric                Before        After
# ──────────────────    ──────────    ──────────
# Embedding quality     MiniLM-L6     BGE-large (3x better on technical text)
# Chunk context         ~256 tokens   512 tokens with overlap
# Query variants        1             3 (expanded)
# Search type           semantic only BM25 + semantic hybrid
# After retrieval       none          cross-encoder reranking
# Duplicate chunks      frequent      deduplicated
# Stale content         all equal     freshness-penalized
# Low-quality sources   all equal     credibility-scored
# DITA section mapping  none          automatic
# Expected RAG quality  baseline      ~2-3x better relevance
