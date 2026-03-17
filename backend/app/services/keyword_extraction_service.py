"""
Extract discriminative keywords from Jira evidence when user corrects recipe.

Used for self-learning: when (evidence, recipe_used, expected_recipe) is known,
extract keywords that should route to expected_recipe. LLM when available, else simple NLP.
"""
import re
from typing import Optional

from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

# Common stopwords - exclude from keyword extraction
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for", "of",
    "with", "by", "from", "as", "is", "was", "are", "were", "been", "be",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "may", "might", "must", "can", "this", "that", "these", "those", "it",
    "its", "when", "where", "which", "who", "what", "how", "why", "not",
})


def _extract_keywords_simple(evidence_text: str, max_keywords: int = 5) -> list[str]:
    """
    Simple NLP: extract significant words (exclude stopwords, prefer longer tokens).
    Returns up to max_keywords, ordered by relevance (length * freq).
    """
    if not evidence_text or not isinstance(evidence_text, str):
        return []
    text = re.sub(r"[^\w\s-]", " ", evidence_text.lower())
    tokens = [t for t in text.split() if len(t) >= 3 and t not in _STOPWORDS]
    if not tokens:
        return []
    # Count frequency, weight by length (longer = more specific)
    from collections import Counter
    counts = Counter(tokens)
    scored = [(t, counts[t] * (1 + len(t) * 0.1)) for t in set(tokens)]
    scored.sort(key=lambda x: -x[1])
    return [t for t, _ in scored[:max_keywords]]


async def extract_keywords_from_correction(
    evidence_text: str,
    recipe_used: Optional[str],
    expected_recipe_id: str,
    max_keywords: int = 5,
    trace_id: Optional[str] = None,
) -> list[str]:
    """
    Extract discriminative keywords that, when present in evidence, should route to expected_recipe.
    Uses LLM when available for better quality; falls back to simple NLP.
    """
    if not evidence_text or not expected_recipe_id:
        return []

    try:
        from app.services.llm_service import generate_json, is_llm_available

        if is_llm_available():
            prompt = """You are a DITA routing assistant. Given Jira evidence where the wrong recipe was used and the correct recipe, extract 3-5 SHORT keywords or phrases (1-3 words each) that appear in the evidence and would help route similar evidence to the correct recipe.

RULES:
- Keywords must appear in the evidence text
- Prefer DITA-specific terms (steps, cmd, task, refbody, keyref, conref, etc.)
- Prefer specific over generic (e.g. "choicetable" over "table")
- Output JSON only: {"keywords": ["kw1", "kw2", ...]}
- Max 5 keywords"""

            user = f"Evidence (excerpt): {evidence_text[:1500]}\n\nRecipe used (wrong): {recipe_used or 'unknown'}\nCorrect recipe: {expected_recipe_id}\n\nOutput JSON:"
            result = await generate_json(
                prompt, user, max_tokens=200, step_name="keyword_extraction",
                trace_id=trace_id,
            )
            if isinstance(result, dict) and result.get("keywords"):
                kw = result["keywords"]
                if isinstance(kw, list):
                    return [str(k).lower().strip() for k in kw[:max_keywords] if k]
    except Exception as e:
        logger.debug_structured(
            "Keyword extraction LLM failed, using simple NLP",
            extra_fields={"error": str(e)},
        )

    return _extract_keywords_simple(evidence_text, max_keywords)
