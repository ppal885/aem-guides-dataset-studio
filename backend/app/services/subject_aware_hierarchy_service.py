"""LLM-driven subject-aware content for structural / scale recipes.

When the user asks for, e.g. "Generate DITA for Kubernetes with deep nested
hierarchy", the chat layer used to pick a structural/scale recipe (deep_hierarchy,
wide_branching, flat_hierarchical_dita, large_scale) which produced templated
placeholders like "Level 0 Topic 00000" with body "Content at depth level 0.".

This module asks the configured LLM to author N (capped) titles + 1-paragraph
bodies for the user's subject. The output is fed into the generators via the
``content_subject``, ``content_titles``, ``content_bodies`` recipe fields.

Design notes:
- The total node count for these recipes can be huge (deep_hierarchy with
  depth=10, children_per_level=5 = 12,207,031 nodes!). We cap the LLM-authored
  span at ``MAX_LLM_AUTHORED_NODES`` and let the generator fall back to
  subject-templated text for the rest. The user-visible navigation ("Kubernetes
  — Topic 00007") still reflects the subject for every node.
- Validates inputs (rule 5: input validation) and never logs the subject text
  itself at INFO level (rule 6: do not log sensitive data — even though subject
  is not sensitive, we still keep payloads out of structured logs by default).
"""
from __future__ import annotations

import json
import re
from typing import Any

from app.core.structured_logging import get_structured_logger
from app.services.llm_service import generate_json, is_llm_available

logger = get_structured_logger(__name__)

# Hard cap so we never produce a single LLM call for millions of nodes.
# Authoring beyond this falls back to subject-templated text in the generator.
MAX_LLM_AUTHORED_NODES = 60
# Hard floor — generating only 1-2 nodes via LLM is wasteful; below this we still call
# the LLM but log a reason. We never raise.
MIN_AUTHORED_NODES = 2

# Recipe types we know how to estimate node counts for. Other recipes are skipped.
HIERARCHY_RECIPE_TYPES = {
    "deep_hierarchy",
    "wide_branching",
    "flat_hierarchical_dita",
    "large_scale",
}

# Flat content recipes that the chat ``create_job`` tool can target. Each one
# already accepts ``content_*`` kwargs in its generator and (after this work) in
# its Pydantic schema, so we can author per-topic titles + bodies (and recipe-
# specific extras) the same way ``_maybe_apply_llm_deterministic_drafts`` does
# for the REST/contract path.
FLAT_CONTENT_RECIPE_TYPES = {
    "task_topics",
    "concept_topics",
    "reference_topics",
    "glossary_pack",
}

# Hard cap for flat-content authoring. The recipe schemas allow up to 5000 (or
# 10000 for glossary), but in practice anything beyond ~120 explodes the LLM
# call without adding signal — the generator's templated fallback handles the
# tail and is still subject-themed when content_subject is set.
MAX_FLAT_CONTENT_ITEMS = 120


def is_hierarchy_recipe(recipe_type: str) -> bool:
    """Return True when recipe is one of the structural/scale recipes that benefits from subject content."""
    return (recipe_type or "").strip().lower() in HIERARCHY_RECIPE_TYPES


def is_flat_content_recipe(recipe_type: str) -> bool:
    """Return True when recipe is one of the flat content recipes (task/concept/reference/glossary)."""
    return (recipe_type or "").strip().lower() in FLAT_CONTENT_RECIPE_TYPES


def estimate_authored_node_count(recipe_type: str, params: dict[str, Any]) -> int:
    """Compute how many leading nodes we should ask the LLM to author for a recipe.

    Returns 0 when we cannot estimate or when the recipe is not one of the
    supported hierarchy recipes. Otherwise returns ``min(total_nodes, MAX_LLM_AUTHORED_NODES)``.
    """
    rt = (recipe_type or "").strip().lower()
    if rt not in HIERARCHY_RECIPE_TYPES:
        return 0
    p = params or {}
    try:
        if rt == "deep_hierarchy":
            depth = max(1, int(p.get("depth", 10)))
            children = max(2, int(p.get("children_per_level", 5)))
            depth = min(depth, 20)
            children = min(children, 100)
            total = sum(children ** level if level > 0 else 1 for level in range(depth + 1))
        elif rt == "wide_branching":
            roots = max(1, int(p.get("root_topics", 10)))
            cpr = max(10, int(p.get("children_per_root", 1000)))
            total = roots + roots * cpr
        elif rt == "flat_hierarchical_dita":
            total = max(1, int(p.get("topic_count", 5000)))
        elif rt == "large_scale":
            total = max(1, int(p.get("topic_count", 100000)))
        else:
            return 0
    except (TypeError, ValueError):
        return 0
    return min(total, MAX_LLM_AUTHORED_NODES)


def _normalize_str_list(value: Any, count: int) -> list[str]:
    """Coerce LLM JSON output to a clean list[str] of length <= count."""
    if not isinstance(value, list):
        return []
    cleaned: list[str] = []
    for item in value[:count]:
        if not isinstance(item, str):
            continue
        text = re.sub(r"\s+", " ", item).strip()
        if text:
            cleaned.append(text)
    return cleaned


def _detect_subject_from_prompt(prompt_text: str) -> str:
    """Best-effort subject extraction from a free-text user prompt.

    Returns "" when no subject is obvious. The caller may also pass an explicit
    ``subject`` arg, which always wins. This is a conservative regex pass — it
    tries to lift the most obvious subject phrase ("for Kubernetes", "about
    Kubernetes", "of Kubernetes") and falls back to empty.
    """
    text = (prompt_text or "").strip()
    if not text:
        return ""
    # "X for Kubernetes [with|that|deep|...]"
    for pattern in (
        r"\bfor\s+([A-Z][\w\-/]+(?:\s+[A-Z]?[\w\-/]+){0,3})",
        r"\babout\s+([A-Z][\w\-/]+(?:\s+[A-Z]?[\w\-/]+){0,3})",
        r"\bon\s+([A-Z][\w\-/]+(?:\s+[A-Z]?[\w\-/]+){0,3})",
        r"\bof\s+([A-Z][\w\-/]+(?:\s+[A-Z]?[\w\-/]+){0,3})",
    ):
        m = re.search(pattern, text)
        if m:
            candidate = re.sub(r"\s+", " ", m.group(1)).strip(" .,:;!?-")
            # Trim trailing structural words ("with deep nested hierarchy", "and ...")
            candidate = re.split(
                r"\b(?:with|and|that|deep|nested|hierarchy|structure|map|topics?|dataset)\b",
                candidate,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[0].strip(" .,:;!?-")
            if 2 <= len(candidate) <= 60:
                return candidate
    return ""


async def generate_subject_content(
    *,
    subject: str,
    recipe_type: str,
    recipe_params: dict[str, Any],
    user_prompt: str | None = None,
    trace_id: str | None = None,
    jira_id: str | None = None,
) -> dict[str, Any]:
    """Ask the LLM to author titles + bodies for the leading nodes of a hierarchy recipe.

    Returns a dict with shape::

        {
          "applied": bool,
          "reason": str,                 # explanation when applied=False
          "subject": str,                # echoed (possibly inferred) subject
          "node_count": int,             # number of authored nodes (<= MAX_LLM_AUTHORED_NODES)
          "titles": list[str],           # ready to drop into recipe.content_titles
          "bodies": list[str],           # ready to drop into recipe.content_bodies
          "fallback_used": bool,         # True when LLM unavailable or returned nothing
        }

    The caller is responsible for setting ``content_subject`` on the recipe to
    ``result["subject"]`` so the generator's per-node fallback also stays themed.
    """
    rt = (recipe_type or "").strip().lower()
    if not is_hierarchy_recipe(rt):
        return {
            "applied": False,
            "reason": f"recipe_type {rt!r} is not a hierarchy recipe",
            "subject": (subject or "").strip(),
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": False,
        }

    resolved_subject = (subject or "").strip()
    if not resolved_subject and user_prompt:
        resolved_subject = _detect_subject_from_prompt(user_prompt)
    resolved_subject = re.sub(r"\s+", " ", resolved_subject).strip(" .,:;!?-")
    if not resolved_subject:
        return {
            "applied": False,
            "reason": "no subject provided or inferred",
            "subject": "",
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": False,
        }

    node_count = estimate_authored_node_count(rt, recipe_params)
    if node_count <= 0:
        return {
            "applied": False,
            "reason": "could not estimate node count from recipe params",
            "subject": resolved_subject,
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": False,
        }
    node_count = max(MIN_AUTHORED_NODES, node_count)

    if not is_llm_available():
        # Without LLM, the generator's subject-templated fallback still themes everything by subject.
        return {
            "applied": True,
            "reason": "LLM unavailable; generator will use subject-templated fallback",
            "subject": resolved_subject,
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": True,
        }

    structure_hint = _structure_hint(rt, recipe_params)
    system_prompt = (
        "You author concrete, domain-specific DITA topic titles and one-paragraph bodies "
        "for a structural test dataset. You return strict JSON only. "
        "Titles must be unique and informative — no 'Topic 1' style placeholders. "
        "Each body is one to three sentences and stays focused on the subject."
    )
    user_payload = {
        "task": "Author leading hierarchy nodes for a structural DITA dataset.",
        "subject": resolved_subject,
        "recipe_type": rt,
        "structure": structure_hint,
        "node_count": node_count,
        "ordering_rule": _ordering_rule(rt),
        "rules": [
            f"Return arrays exactly sized for node_count={node_count}.",
            "Titles ≤ 100 chars, no leading 'Topic'/'Section' tokens.",
            "Bodies are one paragraph; do NOT use bullet lists or markdown.",
            "Stay strictly on subject. No marketing fluff.",
            "If subject is technical (e.g. Kubernetes), use real concept names "
            "(Pods, Deployments, Services, Ingress, ConfigMaps, ReplicaSets, etc.) — never invent fake APIs.",
        ],
        "expected_fields": ["titles", "bodies"],
    }
    if user_prompt:
        # Pass through (truncated) user prompt so the LLM can pick up extra hints
        # (e.g. "focus on networking and storage").
        user_payload["user_prompt_excerpt"] = user_prompt.strip()[:1500]

    try:
        # Each title + body averages ~80 + 220 chars; budget ~200 tokens per node + framing.
        max_tokens = min(8000, 600 + 220 * node_count)
        draft = await generate_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
            max_tokens=max_tokens,
            step_name="subject_aware_hierarchy",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured(
            "subject_aware_hierarchy_llm_failed",
            extra_fields={"recipe_type": rt, "node_count": node_count, "error": str(exc)},
        )
        return {
            "applied": True,
            "reason": f"LLM call failed: {exc}; generator will use subject-templated fallback",
            "subject": resolved_subject,
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": True,
        }

    titles = _normalize_str_list(draft.get("titles") if isinstance(draft, dict) else None, node_count)
    bodies = _normalize_str_list(draft.get("bodies") if isinstance(draft, dict) else None, node_count)
    if not titles and not bodies:
        return {
            "applied": True,
            "reason": "LLM returned no titles or bodies; generator will use subject-templated fallback",
            "subject": resolved_subject,
            "node_count": 0,
            "titles": [],
            "bodies": [],
            "fallback_used": True,
        }

    logger.info_structured(
        "subject_aware_hierarchy_llm_applied",
        extra_fields={
            "recipe_type": rt,
            "node_count_requested": node_count,
            "titles_returned": len(titles),
            "bodies_returned": len(bodies),
        },
    )
    return {
        "applied": True,
        "reason": "ok",
        "subject": resolved_subject,
        "node_count": max(len(titles), len(bodies)),
        "titles": titles,
        "bodies": bodies,
        "fallback_used": False,
    }


def _structure_hint(recipe_type: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a concise structural hint for the LLM so it understands ordering."""
    p = params or {}
    if recipe_type == "deep_hierarchy":
        return {
            "kind": "tree",
            "depth": int(p.get("depth", 10) or 10),
            "children_per_level": int(p.get("children_per_level", 5) or 5),
            "ordering": "BFS — level 0 first, then level 1 left to right, etc.",
        }
    if recipe_type == "wide_branching":
        return {
            "kind": "wide_tree",
            "root_topics": int(p.get("root_topics", 10) or 10),
            "children_per_root": int(p.get("children_per_root", 1000) or 1000),
            "ordering": "All roots first (in order), then children of root 1, then children of root 2, etc.",
        }
    if recipe_type == "flat_hierarchical_dita":
        return {
            "kind": "flat_plus_sectioned",
            "topic_count": int(p.get("topic_count", 5000) or 5000),
            "topics_per_section": int(p.get("topics_per_section", 50) or 50),
            "flat_submap_count": int(p.get("flat_submap_count", 1) or 1),
            "ordering": "Topic 1, 2, 3, ... by index. Same titles are reused for the flat and sectioned views.",
        }
    if recipe_type == "large_scale":
        return {
            "kind": "flat_pool",
            "topic_count": int(p.get("topic_count", 100000) or 100000),
            "ordering": "Topic 1, 2, 3, ... by index.",
        }
    return {}


def _ordering_rule(recipe_type: str) -> str:
    if recipe_type == "deep_hierarchy":
        return (
            "Index 0 is the root topic for the whole subject. "
            "Indices 1..children_per_level are direct children of the root. "
            "Each level expands left to right. Keep parent-child themes coherent."
        )
    if recipe_type == "wide_branching":
        return (
            "First root_topics entries are the root topics. After that, the next "
            "children_per_root entries are children of root 1, then children of root 2, etc."
        )
    return "Topics are indexed sequentially starting at 0."


def estimate_flat_item_count(recipe_type: str, params: dict[str, Any]) -> int:
    """Compute how many leading items the LLM should author for a flat content recipe.

    Returns 0 when we can't estimate or the recipe isn't supported. Otherwise
    returns ``min(configured_count, MAX_FLAT_CONTENT_ITEMS)``.
    """
    rt = (recipe_type or "").strip().lower()
    if not is_flat_content_recipe(rt):
        return 0
    p = params or {}
    try:
        if rt == "glossary_pack":
            total = max(1, int(p.get("entry_count", 100) or 100))
        else:
            total = max(1, int(p.get("topic_count", 50) or 50))
    except (TypeError, ValueError):
        return 0
    return min(total, MAX_FLAT_CONTENT_ITEMS)


def _normalize_steps_by_topic(value: Any, topic_count: int) -> list[list[str]]:
    """Coerce LLM ``steps_by_topic`` output to ``list[list[str]]`` of length <= topic_count."""
    if not isinstance(value, list):
        return []
    out: list[list[str]] = []
    for item in value[:topic_count]:
        if not isinstance(item, list):
            continue
        steps = [re.sub(r"\s+", " ", str(step)).strip() for step in item if isinstance(step, (str, int, float))]
        steps = [s for s in steps if s]
        if steps:
            out.append(steps[:20])
    return out


def _expected_fields_for_flat_recipe(recipe_type: str) -> list[str]:
    """Tell the LLM which JSON fields to populate for each recipe."""
    if recipe_type == "task_topics":
        return ["titles", "shortdescs", "steps_by_topic"]
    if recipe_type == "concept_topics":
        return ["titles", "shortdescs", "body_snippets"]
    if recipe_type == "reference_topics":
        return ["titles", "shortdescs", "property_seeds", "detail_snippets"]
    if recipe_type == "glossary_pack":
        return ["terms", "definitions", "acronyms"]
    return ["titles", "shortdescs"]


async def generate_flat_content(
    *,
    subject: str,
    recipe_type: str,
    recipe_params: dict[str, Any],
    user_prompt: str | None = None,
    trace_id: str | None = None,
    jira_id: str | None = None,
) -> dict[str, Any]:
    """Ask the LLM to author per-topic content for a flat content recipe.

    Mirrors ``generate_subject_content`` but for the flat recipes
    (``task_topics``, ``concept_topics``, ``reference_topics``, ``glossary_pack``).
    The output is shaped so callers can drop fields directly into the recipe
    params dict.

    Returns a dict::

        {
          "applied": bool,
          "reason": str,
          "subject": str,
          "item_count": int,
          "fields": dict[str, list],   # ready to merge into recipe params
          "fallback_used": bool,
        }

    When ``applied`` is True but ``fields`` is empty, the caller should still
    set ``content_subject`` so the generator's templated fallback stays themed.
    """
    rt = (recipe_type or "").strip().lower()
    if not is_flat_content_recipe(rt):
        return {
            "applied": False,
            "reason": f"recipe_type {rt!r} is not a flat content recipe",
            "subject": (subject or "").strip(),
            "item_count": 0,
            "fields": {},
            "fallback_used": False,
        }

    resolved_subject = (subject or "").strip()
    if not resolved_subject and user_prompt:
        resolved_subject = _detect_subject_from_prompt(user_prompt)
    resolved_subject = re.sub(r"\s+", " ", resolved_subject).strip(" .,:;!?-")
    if not resolved_subject:
        return {
            "applied": False,
            "reason": "no subject provided or inferred",
            "subject": "",
            "item_count": 0,
            "fields": {},
            "fallback_used": False,
        }

    item_count = estimate_flat_item_count(rt, recipe_params)
    if item_count <= 0:
        return {
            "applied": False,
            "reason": "could not estimate item count from recipe params",
            "subject": resolved_subject,
            "item_count": 0,
            "fields": {},
            "fallback_used": False,
        }
    item_count = max(MIN_AUTHORED_NODES, item_count)

    if not is_llm_available():
        return {
            "applied": True,
            "reason": "LLM unavailable; only content_subject is set, generator will use subject-templated fallback",
            "subject": resolved_subject,
            "item_count": 0,
            "fields": {},
            "fallback_used": True,
        }

    expected_fields = _expected_fields_for_flat_recipe(rt)
    family_hint = {
        "task_topics": "Procedural task topics. Each topic explains how to perform a specific operation.",
        "concept_topics": "Conceptual topics. Each topic explains an idea, mechanism, or piece of architecture.",
        "reference_topics": "Reference topics. Each topic documents a configuration, command, API, or property table.",
        "glossary_pack": "Glossary entries. Each entry defines one term concisely.",
    }.get(rt, "DITA topics for the requested subject.")

    system_prompt = (
        "You author concrete, domain-specific DITA content for a deterministic generator. "
        "You return strict JSON only. Titles must be unique, informative, and specific to the subject — "
        "no 'Topic 1' style placeholders. Each shortdesc is one sentence. "
        "Stay strictly on subject and never invent fake APIs."
    )
    user_payload: dict[str, Any] = {
        "task": "Author leading items for a flat DITA dataset.",
        "subject": resolved_subject,
        "recipe_type": rt,
        "family_hint": family_hint,
        "item_count": item_count,
        "expected_fields": expected_fields,
        "rules": [
            f"Return arrays exactly sized for item_count={item_count} when possible.",
            "Titles ≤ 100 chars, no leading 'Topic'/'Section' tokens.",
            "Shortdescs are one sentence each.",
            "If subject is technical (e.g. Terraform, Kubernetes), use real concept names "
            "(resources, providers, modules, variables, etc.) — never invent fake APIs.",
        ],
    }
    if rt == "task_topics":
        user_payload["rules"].append(
            "steps_by_topic[i] is the ordered list of <cmd> texts for task i (3-7 imperative steps each)."
        )
    if rt == "reference_topics":
        user_payload["rules"].append(
            "property_seeds[i] is a comma-separated list of property names for topic i's <properties> table."
        )
    if rt == "glossary_pack":
        user_payload["rules"].append(
            "terms[i] is the glossary term, definitions[i] its definition, acronyms[i] the expansion (or empty string)."
        )
    if user_prompt:
        user_payload["user_prompt_excerpt"] = user_prompt.strip()[:1500]

    try:
        max_tokens = min(8000, 600 + 180 * item_count)
        draft = await generate_json(
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False),
            max_tokens=max_tokens,
            step_name="subject_aware_flat_content",
            trace_id=trace_id,
            jira_id=jira_id,
        )
    except Exception as exc:
        logger.warning_structured(
            "subject_aware_flat_content_llm_failed",
            extra_fields={"recipe_type": rt, "item_count": item_count, "error": str(exc)},
        )
        return {
            "applied": True,
            "reason": f"LLM call failed: {exc}; only content_subject is set",
            "subject": resolved_subject,
            "item_count": 0,
            "fields": {},
            "fallback_used": True,
        }

    if not isinstance(draft, dict):
        draft = {}

    fields: dict[str, list] = {}
    titles = _normalize_str_list(draft.get("titles"), item_count)
    if titles:
        fields["content_titles"] = titles
    shortdescs = _normalize_str_list(draft.get("shortdescs"), item_count)
    if shortdescs:
        fields["content_shortdescs"] = shortdescs

    if rt == "task_topics":
        steps_by_topic = _normalize_steps_by_topic(draft.get("steps_by_topic"), item_count)
        if steps_by_topic:
            fields["content_steps_by_topic"] = steps_by_topic
    elif rt == "concept_topics":
        body_snippets = _normalize_str_list(draft.get("body_snippets"), item_count)
        if body_snippets:
            fields["content_body_snippets"] = body_snippets
    elif rt == "reference_topics":
        property_seeds = _normalize_str_list(draft.get("property_seeds"), item_count)
        if property_seeds:
            fields["content_property_seeds"] = property_seeds
        detail_snippets = _normalize_str_list(draft.get("detail_snippets"), item_count)
        if detail_snippets:
            fields["content_detail_snippets"] = detail_snippets
    elif rt == "glossary_pack":
        terms = _normalize_str_list(draft.get("terms"), item_count)
        if terms:
            fields["content_terms"] = terms
        definitions = _normalize_str_list(draft.get("definitions"), item_count)
        if definitions:
            fields["content_definitions"] = definitions
        acronyms = _normalize_str_list(draft.get("acronyms"), item_count)
        if acronyms:
            fields["content_acronyms"] = acronyms

    if not fields:
        return {
            "applied": True,
            "reason": "LLM returned no usable fields; only content_subject is set",
            "subject": resolved_subject,
            "item_count": 0,
            "fields": {},
            "fallback_used": True,
        }

    logger.info_structured(
        "subject_aware_flat_content_llm_applied",
        extra_fields={
            "recipe_type": rt,
            "item_count_requested": item_count,
            "fields_returned": sorted(fields.keys()),
        },
    )
    return {
        "applied": True,
        "reason": "ok",
        "subject": resolved_subject,
        "item_count": item_count,
        "fields": fields,
        "fallback_used": False,
    }
