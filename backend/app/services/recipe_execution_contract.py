"""Materialize a hard execution contract for every selected recipe (constructs, fallbacks, rules, hints)."""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from app.core.schemas_dita_pipeline import IntentRecord, PlanConstruct, RecipeExecutionContract
from app.generator.recipe_manifest import RecipeSpec
from app.core.structured_logging import get_structured_logger

logger = get_structured_logger(__name__)

DEFAULT_REPAIR_HINTS = [
    "Satisfy every entry in required_constructs with at least min_count occurrences of valid DITA markup.",
    "Do not replace required structures (tables, menucascade, keyref graphs, etc.) with plain <p> or <ul> alone.",
    "Re-read GENERATION_PLAN_JSON and RECIPE_EXECUTION_CONTRACT JSON in ADDITIONAL INSTRUCTIONS before emitting files.",
]

DEFAULT_FORBIDDEN = [
    "paragraph_only_substitution_for_required_structure",
    "unordered_list_as_stand_in_for_required_table_or_reference_markup",
]

DEFAULT_VALIDATION_RULE: dict[str, Any] = {
    "id": "contract_dita_root_present",
    "when": "",
    "require": {
        "regex": r"<\s*(map|bookmap|concept|task|reference|topic)\b",
    },
    "severity": "error",
    "hint": "Include at least one valid DITA root (map, bookmap, or topic-class element).",
}


def _local_name(tag: str) -> str:
    if not tag:
        return ""
    t = tag.split("}")[-1] if "}" in tag else tag
    return t.split(":")[-1].lower()


def aggregate_element_counts_from_bytes(files: Dict[str, bytes]) -> dict[str, int]:
    """Count DITA/XML element local names across generated files."""
    total: dict[str, int] = {}
    for raw in files.values():
        try:
            text = raw.decode("utf-8", errors="ignore")
        except Exception:
            continue
        body = re.sub(r"<\?xml[^?]*\?>", "", text, flags=re.I)
        body = re.sub(r"<!DOCTYPE[^>]*>", "", body, flags=re.I)
        try:
            root = ET.fromstring(body[:500000])
            for el in root.iter():
                name = _local_name(el.tag)
                if name:
                    total[name] = total.get(name, 0) + 1
        except ET.ParseError:
            continue
    return total


def effective_construct_count(counts: dict[str, int], construct_name: str) -> int:
    """Map plan construct names to aggregated element counts (aliases)."""
    n = (construct_name or "").strip().lower()
    if n == "table":
        return counts.get("table", 0) + counts.get("simpletable", 0)
    if n == "topic":
        return (
            counts.get("topic", 0)
            + counts.get("concept", 0)
            + counts.get("task", 0)
            + counts.get("reference", 0)
        )
    if n == "map":
        return counts.get("map", 0) + counts.get("bookmap", 0)
    return counts.get(n, 0)


def missing_required_constructs(
    required: List[PlanConstruct], counts: dict[str, int]
) -> List[str]:
    out: list[str] = []
    for req in required:
        need = max(1, int(req.min_count or 1))
        got = effective_construct_count(counts, req.name)
        if got < need:
            out.append(f"{req.name}(need>={need},found={got})")
    return out


def build_recipe_execution_contract(
    spec: RecipeSpec,
    *,
    intent: Optional[IntentRecord] = None,
) -> RecipeExecutionContract:
    """
    Produce a complete contract for the selected recipe. Empty recipe fields are
    filled with deterministic defaults so downstream stages never see partial contracts.
    """
    req: list[PlanConstruct] = []
    for rc in spec.required_constructs or []:
        if isinstance(rc, dict) and rc.get("name"):
            req.append(
                PlanConstruct(
                    name=str(rc["name"]),
                    min_count=max(1, int(rc.get("min_count") or 1)),
                )
            )

    if not req:
        picked = False
        for c in spec.constructs or []:
            cl = str(c).lower()
            if cl in ("map", "topic", "concept", "task", "reference", "bookmap"):
                req.append(PlanConstruct(name=cl, min_count=1))
                picked = True
                break
        if not picked:
            tt = (spec.topic_type or "").strip().lower()
            if tt in ("map", "map_only"):
                req.append(PlanConstruct(name="map", min_count=1))
            elif tt in ("concept", "task", "reference", "topic"):
                req.append(PlanConstruct(name=tt, min_count=1))
            else:
                req.append(PlanConstruct(name="topic", min_count=1))

    forbidden = list(spec.forbidden_fallback_patterns or [])
    for ap in spec.anti_patterns or []:
        if isinstance(ap, dict) and ap.get("id"):
            forbidden.append(str(ap["id"]))
    if intent and intent.anti_fallback_signals:
        for sig in intent.anti_fallback_signals[:8]:
            tag = f"intent_signal:{sig}"
            if tag not in forbidden:
                forbidden.append(tag)
    if not forbidden:
        forbidden = list(DEFAULT_FORBIDDEN)

    rules = [r for r in (spec.validation_rules or []) if isinstance(r, dict)]
    if not rules:
        rules = [dict(DEFAULT_VALIDATION_RULE)]

    hints = list(spec.repair_hints or [])
    if not hints:
        hints = list(DEFAULT_REPAIR_HINTS)

    contract = RecipeExecutionContract(
        recipe_id=spec.id,
        required_constructs=req,
        forbidden_fallback_patterns=list(dict.fromkeys(forbidden)),
        validation_rules=rules,
        repair_hints=hints,
    )

    logger.debug_structured(
        "Recipe execution contract materialized",
        extra_fields={
            "recipe_id": spec.id,
            "required_n": len(req),
            "forbidden_n": len(contract.forbidden_fallback_patterns),
            "rules_n": len(contract.validation_rules),
            "hints_n": len(contract.repair_hints),
        },
    )
    return contract


def check_contract_required_constructs_or_raise(
    contract: RecipeExecutionContract | dict[str, Any],
    files: Dict[str, bytes],
) -> None:
    """
    Fail fast when emitted XML does not satisfy required_constructs.
    Raises ValueError with a stable prefix for callers to detect contract failure.
    """
    if isinstance(contract, dict):
        raw_req = contract.get("required_constructs") or []
        required: list[PlanConstruct] = []
        for item in raw_req:
            if isinstance(item, dict) and item.get("name"):
                required.append(
                    PlanConstruct(
                        name=str(item["name"]),
                        min_count=max(1, int(item.get("min_count") or 1)),
                    )
                )
    else:
        required = list(contract.required_constructs)

    if not required:
        return

    counts = aggregate_element_counts_from_bytes(files)
    missing = missing_required_constructs(required, counts)
    if not missing:
        return

    hints = (
        contract.get("repair_hints", [])
        if isinstance(contract, dict)
        else contract.repair_hints
    )
    hint_txt = "; ".join(str(h) for h in (hints or [])[:3])
    raise ValueError(
        "RECIPE_CONTRACT_VIOLATION: required constructs not satisfied: "
        + ", ".join(missing)
        + (f" | repair_hints: {hint_txt}" if hint_txt else "")
    )
