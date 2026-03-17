"""Generate self-supervised contrastive pairs for DITA embedding fine-tuning.

Positive pairs: same semantic meaning, different surface form.
Negative pairs: unrelated chunks (different content_type or elements).
"""
import json
import random
from pathlib import Path
from typing import Optional

SEED_PATH = Path(__file__).resolve().parent.parent / "storage" / "dita_spec_seed.json"

# Sibling elements that co-occur (e.g. in reltable)
SIBLING_GROUPS = [
    ["reltable", "relrow", "relcolspec"],
    ["dl", "dlentry", "dt", "dd", "dlhead"],
    ["steps", "step", "cmd", "info", "stepresult"],
    ["taskbody", "prereq", "context", "result", "steps"],
    ["subjectScheme", "subjectdef", "schemeref"],
    ["map", "topicref", "mapref", "keydef", "keyscope"],
]


def _load_seed(path: Optional[Path] = None) -> list[dict]:
    """Load DITA seed corpus."""
    p = path or SEED_PATH
    if not p.exists():
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _chunk_to_text(chunk: dict, variant: str = "default") -> str:
    """Build text representation of chunk. Variant: default, alternate, compact."""
    el = chunk.get("element_name") or ""
    txt = chunk.get("text_content") or ""
    if variant == "alternate":
        return f"{el}: {txt}"
    if variant == "compact":
        return f"{el} {txt}"[:200]
    return f"{el} {txt}"


def _build_positive_pairs(chunks: list[dict]) -> list[tuple[str, str]]:
    """Build positive pairs (anchor, positive) from chunks."""
    pairs = []
    for c in chunks:
        anchor = _chunk_to_text(c, "default")
        if not anchor.strip():
            continue
        # Same chunk, different surface form
        pairs.append((anchor, _chunk_to_text(c, "alternate")))
        pairs.append((anchor, _chunk_to_text(c, "compact")))
    return pairs


def _build_sibling_pairs(chunks: list[dict]) -> list[tuple[str, str]]:
    """Build positive pairs from sibling elements (e.g. relrow, relcolspec)."""
    pairs = []
    by_el = {c.get("element_name"): c for c in chunks if c.get("element_name")}
    for group in SIBLING_GROUPS:
        available = [by_el[el] for el in group if el in by_el]
        if len(available) >= 2:
            for i, a in enumerate(available):
                for b in available[i + 1 :]:
                    pairs.append((_chunk_to_text(a), _chunk_to_text(b)))
    return pairs


def _build_negative_pairs(
    chunks: list[dict], num_negatives: int = 3, random_gen: Optional[random.Random] = None
) -> list[tuple[str, str, list[str]]]:
    """Build (anchor, positive, negatives) for MultipleNegativesRankingLoss."""
    rng = random_gen or random
    by_type = {}
    for c in chunks:
        ct = c.get("content_type") or "element"
        if ct not in by_type:
            by_type[ct] = []
        by_type[ct].append(c)

    positives = _build_positive_pairs(chunks) + _build_sibling_pairs(chunks)
    if not positives:
        return []

    result = []
    for anchor, positive in positives:
        negatives = []
        for _ in range(num_negatives):
            other = rng.choice(chunks)
            neg_text = _chunk_to_text(other)
            if neg_text != anchor and neg_text != positive and neg_text not in negatives:
                negatives.append(neg_text)
        if len(negatives) < num_negatives:
            for c in chunks:
                if len(negatives) >= num_negatives:
                    break
                t = _chunk_to_text(c)
                if t not in (anchor, positive) and t not in negatives:
                    negatives.append(t)
        result.append((anchor, positive, negatives[:num_negatives]))
    return result


def generate_contrastive_pairs(
    seed_path: Optional[Path] = None,
    num_negatives: int = 3,
    max_pairs: Optional[int] = None,
    random_seed: int = 42,
) -> list[tuple[str, str, list[str]]]:
    """
    Generate (anchor, positive, negatives) for contrastive fine-tuning.

    Returns list of tuples suitable for MultipleNegativesRankingLoss.
    """
    rng = random.Random(random_seed)

    chunks = _load_seed(seed_path)
    if not chunks:
        return []

    pairs = _build_negative_pairs(chunks, num_negatives, rng)
    if max_pairs:
        pairs = rng.sample(pairs, min(max_pairs, len(pairs)))
    return pairs


def generate_input_output_pairs(
    seed_path: Optional[Path] = None,
    max_pairs: Optional[int] = None,
) -> list[tuple[str, str]]:
    """
    Generate (anchor, positive) pairs only (for simpler losses).
    """
    chunks = _load_seed(seed_path)
    if not chunks:
        return []
    pairs = _build_positive_pairs(chunks) + _build_sibling_pairs(chunks)
    if max_pairs:
        pairs = random.sample(pairs, min(max_pairs, len(pairs)))
    return pairs
