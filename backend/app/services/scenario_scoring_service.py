"""Scenario quality scoring - novelty, generator diversity, hint diversity, evidence coverage."""
import re
from typing import Optional

from app.core.schemas_ai import Scenario
from app.services.recipe_retriever import _retrieve_recipes_sync
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

MIN_SCORE_THRESHOLD = 0.3


def _tokenize(text: str) -> set[str]:
    """Extract searchable tokens."""
    if not text:
        return set()
    text = re.sub(r"[^\w\s-]", " ", str(text).lower())
    return {t for t in text.split() if len(t) >= 2}


def _novelty_score(scenario: Scenario, earlier_scenarios: list[Scenario]) -> float:
    """Score 0-1: higher if scenario is novel compared to earlier ones."""
    if not earlier_scenarios:
        return 1.0
    current_tokens = _tokenize(f"{scenario.title} {scenario.description}")
    if not current_tokens:
        return 0.5
    earlier_tokens = set()
    for s in earlier_scenarios:
        earlier_tokens.update(_tokenize(f"{s.title} {s.description}"))
    overlap = len(current_tokens & earlier_tokens) / len(current_tokens)
    return max(0.0, 1.0 - overlap)


def _generator_diversity_score(
    scenario: Scenario,
    earlier_recipe_ids: set[str],
    k: int = 6,
) -> float:
    """Score 0-1: higher if scenario would use recipes not used by earlier scenarios."""
    candidates = _retrieve_recipes_sync(
        f"{scenario.title} {scenario.description}",
        k=k,
    )
    recipe_ids = {c.get("spec").id for c in candidates if c.get("spec")}
    if not recipe_ids:
        return 0.5
    new_ids = recipe_ids - earlier_recipe_ids
    return len(new_ids) / len(recipe_ids)


def _hint_diversity_score(scenario: Scenario, earlier_scenarios: list[Scenario]) -> float:
    """Score 0-1: higher if scenario type is unique among earlier scenarios."""
    if not earlier_scenarios:
        return 1.0
    earlier_types = {s.type for s in earlier_scenarios}
    return 1.0 if scenario.type not in earlier_types else 0.5


def _evidence_coverage_score(scenario: Scenario, evidence_pack: dict) -> float:
    """Score 0-1: higher if scenario references evidence."""
    refs = scenario.evidence_refs or []
    primary = evidence_pack.get("primary") or {}
    similar = evidence_pack.get("similar") or []
    available_refs = set()
    if primary.get("issue_key"):
        available_refs.add(primary["issue_key"])
    for s in similar[:5]:
        if s.get("issue_key"):
            available_refs.add(s["issue_key"])
    if not available_refs:
        return 1.0 if refs else 0.5
    if not refs:
        return 0.0
    covered = len(set(refs) & available_refs) / max(len(available_refs), 1)
    return min(1.0, 0.5 + 0.5 * covered)


def score_scenario(
    scenario: Scenario,
    index: int,
    all_scenarios: list[Scenario],
    evidence_pack: dict,
    earlier_recipe_ids: Optional[set[str]] = None,
) -> float:
    """
    Score a scenario 0-1 using novelty, generator diversity, hint diversity, evidence coverage.
    """
    earlier = all_scenarios[:index]
    recipe_ids = earlier_recipe_ids or set()

    novelty = _novelty_score(scenario, earlier)
    gen_div = _generator_diversity_score(scenario, recipe_ids)
    hint_div = _hint_diversity_score(scenario, earlier)
    evidence = _evidence_coverage_score(scenario, evidence_pack)

    score = (novelty * 0.25 + gen_div * 0.25 + hint_div * 0.15 + evidence * 0.35)
    return max(0.0, min(1.0, score))


def filter_scenarios_by_score(
    scenarios: list[Scenario],
    evidence_pack: dict,
    min_score: float = MIN_SCORE_THRESHOLD,
) -> list[Scenario]:
    """
    Score each scenario and discard those with score < min_score.
    Always keep S1_MIN_REPRO (first scenario).
    """
    if not scenarios:
        return []
    filtered = []
    accumulated_recipe_ids: set[str] = set()
    for i, scenario in enumerate(scenarios):
        if i == 0 and scenario.id == "S1_MIN_REPRO":
            filtered.append(scenario)
            candidates = _retrieve_recipes_sync(
                f"{scenario.title} {scenario.description}",
                k=6,
            )
            accumulated_recipe_ids.update(c.get("spec").id for c in candidates if c.get("spec"))
            continue
        s = score_scenario(scenario, i, scenarios, evidence_pack, accumulated_recipe_ids)
        if s >= min_score:
            filtered.append(scenario)
            candidates = _retrieve_recipes_sync(
                f"{scenario.title} {scenario.description}",
                k=6,
            )
            accumulated_recipe_ids.update(c.get("spec").id for c in candidates if c.get("spec"))
        else:
            logger.info_structured(
                "Scenario discarded by quality score",
                extra_fields={"scenario_id": scenario.id, "score": round(s, 3), "threshold": min_score},
            )
    return filtered[:5]
