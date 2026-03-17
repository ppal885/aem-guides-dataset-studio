"""
Evidence similarity and feedback-based recipe lookup for self-realization.

- Find similar past evidence with user corrections
- Evidence similarity via word overlap (Jaccard) or embeddings when available
"""
import re
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

SIMILARITY_THRESHOLD = 0.25  # Min Jaccard overlap to consider "similar"
MAX_EVIDENCE_PAIRS = 100  # Max stored pairs for similarity lookup


def _tokenize(text: str) -> set[str]:
    """Extract word tokens (lowercase, len >= 2)."""
    if not text or not isinstance(text, str):
        return set()
    text = re.sub(r"[^\w\s-]", " ", text.lower())
    return {t for t in text.split() if len(t) >= 2}


def _jaccard_similarity(a: set[str], b: set[str]) -> float:
    """Jaccard similarity: |intersection| / |union|."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def find_similar_feedback_recipe(
    evidence_text: str,
    evidence_pairs: list[dict],
    threshold: float = SIMILARITY_THRESHOLD,
) -> Optional[tuple[str, float]]:
    """
    Find past evidence similar to current; return (expected_recipe_id, similarity) if found.
    evidence_pairs: list of {evidence_snippet, expected_recipe_id}
    """
    if not evidence_text or not evidence_pairs:
        return None
    query_tokens = _tokenize(evidence_text)
    if not query_tokens:
        return None

    best_recipe = None
    best_score = 0.0

    for pair in evidence_pairs[:MAX_EVIDENCE_PAIRS]:
        snippet = pair.get("evidence_snippet") or ""
        expected = pair.get("expected_recipe_id")
        if not expected or not snippet:
            continue
        doc_tokens = _tokenize(snippet)
        sim = _jaccard_similarity(query_tokens, doc_tokens)
        if sim >= threshold and sim > best_score:
            best_score = sim
            best_recipe = expected

    if best_recipe:
        return (best_recipe, best_score)
    return None
