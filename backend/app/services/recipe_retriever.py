"""Recipe retriever - lexical and embedding-based scoring for recipe candidates.

Uses embedding similarity when USE_RECIPE_EMBEDDING=true. Optional LLM re-ranking when
AI_USE_LLM_RETRIEVAL=true (higher cost, more flexibility). No hardcoded boosts or exclusions;
the LLM reasons from evidence and recipe metadata (use_when, avoid_when, output_scale).
"""
import json
import os
import re
from pathlib import Path
from typing import Optional

from app.core.agentic_config import agentic_config
from app.generator.recipe_manifest import discover_recipe_specs, recipe_to_retrieval_text, RecipeSpec
from app.services.embedding_service import embed_query, embed_texts, is_embedding_available
from app.services.llm_service import generate_json, is_llm_available
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

USE_RECIPE_EMBEDDING = os.getenv("USE_RECIPE_EMBEDDING", "true").lower() in ("true", "1", "yes")
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "templates" / "prompts"

# Cache: (specs, searchable_texts, embeddings)
_recipe_embedding_cache: Optional[tuple[list, list[str], object]] = None


def _tokenize(text: str) -> set[str]:
    """Extract searchable tokens."""
    if not text:
        return set()
    text = re.sub(r"[^\w\s-]", " ", str(text).lower())
    return {t for t in text.split() if len(t) >= 2}




def _get_recipe_embeddings():
    """Get or build recipe embeddings cache. Returns (specs, texts, embeddings) or None."""
    global _recipe_embedding_cache
    if not is_embedding_available() or not USE_RECIPE_EMBEDDING:
        return None
    try:
        specs = [s for s in discover_recipe_specs() if isinstance(s, RecipeSpec)]
        if not specs:
            return None
        texts = [recipe_to_retrieval_text(s) for s in specs]
        embs = embed_texts(texts)
        if embs is None:
            return None
        _recipe_embedding_cache = (specs, texts, embs)
        return _recipe_embedding_cache
    except Exception as e:
        logger.warning_structured(
            "Recipe embedding cache failed",
            extra_fields={"error": str(e)},
        )
        return None


def _retrieve_recipes_sync(
    query: str,
    k: int,
    exclude_ids: Optional[list[str]] = None,
    evidence_context: Optional[str] = None,
) -> list[dict]:
    """Internal sync retrieval by lexical + embedding scoring."""
    global _recipe_embedding_cache
    exclude = set(exclude_ids or [])
    specs = discover_recipe_specs()
    effective_query = f"{evidence_context or ''} {query}".strip() if evidence_context else query
    query_tokens = _tokenize(effective_query)

    embedding_scores: dict[str, float] = {}
    cache = _recipe_embedding_cache or _get_recipe_embeddings()
    if cache and effective_query and effective_query.strip():
        try:
            import numpy as np

            cached_specs, _, chunk_embeddings = cache
            query_emb = embed_query(effective_query)
            if query_emb is not None:
                scores = np.dot(chunk_embeddings, query_emb)
                for i, spec in enumerate(cached_specs):
                    if isinstance(spec, RecipeSpec):
                        embedding_scores[spec.id] = float(scores[i])
        except Exception as e:
            logger.warning_structured(
                "Recipe embedding score failed",
                extra_fields={"error": str(e)},
            )

    scored = []
    for spec in specs:
        if not isinstance(spec, RecipeSpec):
            continue
        if spec.id in exclude:
            continue
        score = 0.0
        rationale_parts = []

        searchable = recipe_to_retrieval_text(spec).lower()
        search_tokens = _tokenize(searchable)

        matched_features = []
        for qt in query_tokens:
            if qt in search_tokens:
                score += 1.0
                rationale_parts.append(f"match:{qt}")
                matched_features.append(qt)

        emb_score = embedding_scores.get(spec.id)
        if emb_score is not None:
            score += emb_score * 2.0
            rationale_parts.append("embedding")
            matched_features.append("embedding")

        try:
            from app.training.recipe_feedback_pairs import get_feedback_boost_keywords
            boost_map = get_feedback_boost_keywords()
            effective_lower = effective_query.lower()
            for kw, recipe_id in boost_map.items():
                if kw.lower() in effective_lower and spec.id == recipe_id:
                    score += 1.5
                    rationale_parts.append(f"feedback_boost:{kw}")
                    matched_features.append("feedback_boost")
                    break
        except Exception:
            pass

        if score > 0:
            scored.append((score, spec, " ".join(rationale_parts) or "lexical_match", matched_features))

    scored.sort(key=lambda x: -x[0])
    results = []
    for score, spec, rationale, matched_features in scored[:k]:
        results.append({
            "recipe_id": spec.id,
            "score": round(score, 2),
            "matched_features": matched_features,
            "spec": spec,
            "rationale": rationale,
        })
    return results


# Strong evidence keywords -> if top recipe has these in avoid_when, demote
_EVIDENCE_AVOID_KEYWORDS = ("keydef", "keyref", "nested", "conref", "conditional", "stress", "parse")


def _post_rerank_sanity_check(reranked: list[dict], evidence: str, k: int) -> list[dict]:
    """
    If evidence contains strong keywords and top recipe has those in avoid_when, demote it.
    """
    if not reranked or not evidence:
        return reranked
    evidence_lower = evidence.lower()
    top = reranked[0]
    spec = top.get("spec")
    if not spec:
        return reranked
    avoid_when = getattr(spec, "avoid_when", None) or []
    avoid_text = " ".join(str(a).lower() for a in avoid_when)
    for kw in _EVIDENCE_AVOID_KEYWORDS:
        if kw in evidence_lower and kw in avoid_text:
            logger.info_structured(
                "Rerank sanity: demoting recipe (evidence keyword in avoid_when)",
                extra_fields={"recipe_id": top.get("recipe_id"), "keyword": kw},
            )
            demoted = reranked.pop(0)
            reranked.append(demoted)
            break
    return reranked[:k]


def _load_reranker_prompt() -> str:
    """Load recipe reranker prompt."""
    path = PROMPTS_DIR / "recipe_reranker.txt"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return "Rank recipe candidates by relevance. Return JSON: {\"ranked_recipe_ids\": [\"id1\", \"id2\", ...]}"


async def llm_rerank_candidates(
    query: str,
    evidence_context: Optional[str],
    candidates: list[dict],
    k: int,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> list[dict]:
    """
    Use LLM to re-rank recipe candidates. Returns top k in relevance order.
    candidates: list of dicts with recipe_id, spec, etc.
    """
    if not candidates or not is_llm_available():
        return candidates[:k] if candidates else []

    prompt = _load_reranker_prompt()
    candidate_list = []
    for c in candidates:
        spec = c.get("spec")
        rid = c.get("recipe_id")
        if not rid:
            continue
        if spec and hasattr(spec, "use_when"):
            item = {
                "id": rid,
                "title": getattr(spec, "title", "") or "",
                "description": (getattr(spec, "description", "") or "")[:200],
                "use_when": (getattr(spec, "use_when", None) or [])[:5],
                "avoid_when": (getattr(spec, "avoid_when", None) or [])[:5],
                "output_scale": getattr(spec, "output_scale", "") or "",
            }
        else:
            item = {
                "id": rid,
                "title": getattr(spec, "title", "") if spec else "",
                "description": (getattr(spec, "description", "") if spec else "")[:200],
                "use_when": [],
                "avoid_when": [],
                "output_scale": "",
            }
        candidate_list.append(item)
    evidence_snippet = (evidence_context or "")[:2000]
    user = f"Query/Scenario: {query[:500]}\n\nEvidence: {evidence_snippet}\n\nCANDIDATES (rank these by relevance, return top {k}):\n{json.dumps(candidate_list, indent=2)}\n\nOutput JSON only:"
    try:
        result = await generate_json(
            prompt, user, max_tokens=500, step_name="recipe_reranker",
            trace_id=trace_id, jira_id=jira_id,
        )
        if not result or not isinstance(result, dict):
            return candidates[:k]
        ranked_ids = result.get("ranked_recipe_ids", [])[:k]
    except Exception as e:
        logger.warning_structured(
            "LLM rerank failed, using original order",
            extra_fields={"error": str(e)},
        )
        return candidates[:k]

    by_id = {c.get("recipe_id"): c for c in candidates}
    reranked = []
    for rid in ranked_ids:
        if rid in by_id:
            reranked.append(by_id[rid])
    for c in candidates:
        if c.get("recipe_id") not in {r.get("recipe_id") for r in reranked}:
            reranked.append(c)

    reranked = _post_rerank_sanity_check(reranked, evidence_context or "", k)
    return reranked[:k]


async def retrieve_recipes(
    query: str,
    k: int = 6,
    scenario_hint: Optional[str] = None,
    exclude_ids: Optional[list[str]] = None,
    evidence_context: Optional[str] = None,
    trace_id: Optional[str] = None,
    jira_id: Optional[str] = None,
) -> list[dict]:
    """
    Retrieve recipe candidates by lexical + embedding scoring.
    When AI_USE_LLM_RETRIEVAL=true, fetches 2*k candidates then LLM re-ranks to top k.
    Exclude specs whose id is in exclude_ids.
    """
    inner_k = 2 * k if agentic_config.use_llm_retrieval else k
    raw = _retrieve_recipes_sync(query, inner_k, exclude_ids, evidence_context)
    if agentic_config.use_llm_retrieval and raw and is_llm_available():
        return await llm_rerank_candidates(
            query, evidence_context, raw, k,
            trace_id=trace_id, jira_id=jira_id,
        )
    return raw[:k] if agentic_config.use_llm_retrieval else raw
