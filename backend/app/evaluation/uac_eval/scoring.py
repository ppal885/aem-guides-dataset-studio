"""
UAC similarity scoring — cosine coverage, Jaccard overlap, and F1-like metrics.

All functions are pure (no side-effects) and work on plain string lists.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence


# ── text normalisation ────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> set[str]:
    STOPWORDS = {
        "verify", "that", "the", "a", "an", "is", "are", "in", "on", "to", "of",
        "and", "or", "not", "when", "after", "before", "with", "without", "for",
        "should", "must", "does", "do", "be", "been", "has", "have",
    }
    return {w for w in _normalise(text).split() if w not in STOPWORDS and len(w) > 2}


# ── embedding-based cosine similarity ────────────────────────────────────────

def _cosine(v1: list[float], v2: list[float]) -> float:
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = sum(a * a for a in v1) ** 0.5
    n2 = sum(b * b for b in v2) ** 0.5
    return dot / (n1 * n2) if n1 and n2 else 0.0


def _embed_batch(texts: list[str]) -> list[list[float]] | None:
    try:
        from app.services.embedding_service import embed_texts_batched
        embs = embed_texts_batched(texts, batch_size=32)
        if embs is None:
            return None
        return [e.tolist() if hasattr(e, "tolist") else list(e) for e in embs]
    except Exception:
        return None


# ── per-scenario pair scoring ─────────────────────────────────────────────────

def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _best_match(query: str, candidates: list[str], query_emb: list[float] | None,
                cand_embs: list[list[float]] | None) -> float:
    """Return the highest similarity between query and any candidate (cosine if available, else Jaccard)."""
    if not candidates:
        return 0.0
    sims: list[float] = []
    for i, cand in enumerate(candidates):
        if query_emb and cand_embs and i < len(cand_embs):
            cos = _cosine(query_emb, cand_embs[i])
            jac = _jaccard(query, cand)
            sims.append(0.7 * cos + 0.3 * jac)
        else:
            sims.append(_jaccard(query, cand))
    return max(sims)


# ── public dataclasses ────────────────────────────────────────────────────────

@dataclass
class ScenarioMatch:
    reference: str
    best_generated: str
    score: float            # 0–1


@dataclass
class SimilarityResult:
    """Aggregate similarity metrics for one ticket."""
    jira_key: str
    coverage_score: float       # avg best-match of each reference in generated
    precision_score: float      # avg best-match of each generated in reference
    f1_score: float             # harmonic mean
    coverage_threshold: float   # fraction of reference scenarios "covered" (score >= threshold)
    matches: list[ScenarioMatch] = field(default_factory=list)
    uncovered: list[str] = field(default_factory=list)  # reference scenarios not covered
    extra: list[str] = field(default_factory=list)       # generated scenarios with no reference match

    def to_dict(self) -> dict:
        return {
            "jira_key": self.jira_key,
            "coverage_score": round(self.coverage_score, 3),
            "precision_score": round(self.precision_score, 3),
            "f1_score": round(self.f1_score, 3),
            "coverage_threshold": round(self.coverage_threshold, 3),
            "uncovered_count": len(self.uncovered),
            "extra_count": len(self.extra),
        }


# ── main scoring function ─────────────────────────────────────────────────────

COVERAGE_MIN = 0.45   # minimum score for a reference scenario to count as "covered"


def score_similarity(
    jira_key: str,
    reference_scenarios: Sequence[str],
    generated_scenarios: Sequence[str],
    *,
    coverage_min: float = COVERAGE_MIN,
) -> SimilarityResult:
    """Compare generated UAC scenarios against reference scenarios.

    Uses embedding cosine similarity when the embedding service is available,
    falls back to Jaccard token overlap otherwise.
    """
    refs = list(reference_scenarios)
    gens = list(generated_scenarios)

    if not refs:
        return SimilarityResult(jira_key=jira_key, coverage_score=0.0, precision_score=0.0,
                                f1_score=0.0, coverage_threshold=0.0)
    if not gens:
        return SimilarityResult(jira_key=jira_key, coverage_score=0.0, precision_score=0.0,
                                f1_score=0.0, coverage_threshold=0.0, uncovered=refs[:])

    # try to get embeddings for both lists
    ref_embs = _embed_batch(refs)
    gen_embs = _embed_batch(gens)

    # coverage: for each reference, find best match in generated
    matches: list[ScenarioMatch] = []
    uncovered: list[str] = []
    cov_scores: list[float] = []
    for i, ref in enumerate(refs):
        ref_emb = ref_embs[i] if ref_embs and i < len(ref_embs) else None
        score = _best_match(ref, gens, ref_emb, gen_embs)
        best_gen = max(gens, key=lambda g: _jaccard(ref, g)) if gens else ""
        matches.append(ScenarioMatch(reference=ref, best_generated=best_gen, score=score))
        cov_scores.append(score)
        if score < coverage_min:
            uncovered.append(ref)

    coverage_score = sum(cov_scores) / len(cov_scores)
    covered_fraction = sum(1 for s in cov_scores if s >= coverage_min) / len(cov_scores)

    # precision: for each generated, find best match in reference
    prec_scores: list[float] = []
    extra: list[str] = []
    for j, gen in enumerate(gens):
        gen_emb = gen_embs[j] if gen_embs and j < len(gen_embs) else None
        score = _best_match(gen, refs, gen_emb, ref_embs)
        prec_scores.append(score)
        if score < coverage_min:
            extra.append(gen)

    precision_score = sum(prec_scores) / len(prec_scores) if prec_scores else 0.0

    f1 = (
        2 * coverage_score * precision_score / (coverage_score + precision_score)
        if (coverage_score + precision_score) > 0
        else 0.0
    )

    return SimilarityResult(
        jira_key=jira_key,
        coverage_score=coverage_score,
        precision_score=precision_score,
        f1_score=f1,
        coverage_threshold=covered_fraction,
        matches=matches,
        uncovered=uncovered,
        extra=extra,
    )


# ── aggregate across benchmark ────────────────────────────────────────────────

@dataclass
class BenchmarkScore:
    ticket_count: int
    mean_coverage: float
    mean_precision: float
    mean_f1: float
    mean_threshold_coverage: float
    by_domain: dict[str, dict[str, float]] = field(default_factory=dict)
    per_ticket: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticket_count": self.ticket_count,
            "mean_coverage": round(self.mean_coverage, 3),
            "mean_precision": round(self.mean_precision, 3),
            "mean_f1": round(self.mean_f1, 3),
            "mean_threshold_coverage": round(self.mean_threshold_coverage, 3),
            "by_domain": {d: {k: round(v, 3) for k, v in m.items()} for d, m in self.by_domain.items()},
            "per_ticket": self.per_ticket,
        }


def aggregate_scores(results: list[tuple[str, str, SimilarityResult]]) -> BenchmarkScore:
    """Aggregate a list of (jira_key, domain, SimilarityResult) into a BenchmarkScore."""
    if not results:
        return BenchmarkScore(0, 0.0, 0.0, 0.0, 0.0)

    by_domain: dict[str, list[SimilarityResult]] = {}
    per_ticket: list[dict] = []
    for key, domain, r in results:
        by_domain.setdefault(domain, []).append(r)
        d = r.to_dict()
        d["domain"] = domain
        per_ticket.append(d)

    def _mean(lst: list[float]) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    all_cov = [r.coverage_score for _, _, r in results]
    all_prec = [r.precision_score for _, _, r in results]
    all_f1 = [r.f1_score for _, _, r in results]
    all_thr = [r.coverage_threshold for _, _, r in results]

    domain_agg: dict[str, dict[str, float]] = {}
    for domain, rs in by_domain.items():
        domain_agg[domain] = {
            "mean_coverage": _mean([r.coverage_score for r in rs]),
            "mean_f1": _mean([r.f1_score for r in rs]),
            "ticket_count": len(rs),
        }

    return BenchmarkScore(
        ticket_count=len(results),
        mean_coverage=_mean(all_cov),
        mean_precision=_mean(all_prec),
        mean_f1=_mean(all_f1),
        mean_threshold_coverage=_mean(all_thr),
        by_domain=domain_agg,
        per_ticket=per_ticket,
    )
