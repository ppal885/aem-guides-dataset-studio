"""Question Planner gate for Question-Based UAC reasoning (backward-compatible).

WHY THIS EXISTS
---------------
Question-Based UAC reasoning inserts two coordinator/reasoning stages into the
existing agentic workflow (Evidence Agent -> Question Planner -> Material
Questions -> Research Router -> Doc Researcher / authorized evidence routes ->
Question Resolver -> Coverage Reasoner input -> Writer -> Reviewer -> Final
UAC).  The existing agents are not replaced; the planner is not an autonomous
agent.  This gate validates the planner's manifest block, `question_plan`.

Every material question must carry: ``question_id``, ``category``, ``question``,
``why_material``, ``triggering_evidence_ids``, ``acceptance_impact``,
``applicability``, ``research_requirement``, and ``status``.

Rules enforced (all generic):

- The 13 initial categories are the closed vocabulary
  (EXPECTED_OUTCOME, STATE_TRANSITION, PERSISTENCE, NEGATIVE_CONTRACT, SCOPE,
  VARIANT, ENTRY_PATH, CONFIGURATION, APPLICABILITY, PRESERVATION,
  ERROR_RECOVERY, SCALE, COMPATIBILITY).  Do not emit every category for every
  ticket: emitting a near-complete category carpet fails review, because only
  questions whose answers could materially improve acceptance understanding or
  coverage may be planned.
- A question is not an AC: the question text must be evidence-seeking (a real
  question), and a question record must not declare itself an AC.
- The question budget is bounded (`budget`, default 12).  Exceeding it without
  an explicit `overflow` block fails; the overflow block must carry the excess
  questions itself with an `OVERFLOW` state and an escalation note - questions
  are never silently discarded.

Backward-compatible: absent `question_plan` -> clean pass.
Generic only. Stdlib only. Sibling import of `question_research` for the shared
research-requirement vocabulary (same pattern as `scaffold_support`).
"""
from __future__ import annotations

from question_research import RESEARCH_REQUIREMENTS

QUESTION_CATEGORIES = (
    "EXPECTED_OUTCOME",
    "STATE_TRANSITION",
    "PERSISTENCE",
    "NEGATIVE_CONTRACT",
    "SCOPE",
    "VARIANT",
    "ENTRY_PATH",
    "CONFIGURATION",
    "APPLICABILITY",
    "PRESERVATION",
    "ERROR_RECOVERY",
    "SCALE",
    "COMPATIBILITY",
)

# Emitting this many distinct categories for one ticket means the planner is
# carpeting the taxonomy instead of selecting material questions.
CATEGORY_CARPET_THRESHOLD = 10

QUESTION_STATUSES = (
    "PLANNED",
    "ROUTED",
    "RESOLVED",
    "ESCALATED",
)

QUESTION_APPLICABILITY = (
    "APPLICABLE",
    "NOT_APPLICABLE",
    "UNRESOLVED",
)

DEFAULT_QUESTION_BUDGET = 12

# Budget overflow escalates explicitly instead of silently dropping questions.
# ``QUESTION_BUDGET_EXCEEDED`` is the canonical state; ``OVERFLOW`` remains
# accepted for earlier manifests.
OVERFLOW_STATES = ("QUESTION_BUDGET_EXCEEDED", "OVERFLOW")


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("question_plan"), dict)


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _validate_item(i, item, *, overflow=False):
    problems = []
    where = "question_plan.overflow.items" if overflow else "question_plan.items"
    tag = f"{where}[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each question must be an object"]

    if not _nonempty(item.get("question_id")):
        problems.append(f"{tag}: missing question_id")
    category = item.get("category")
    if category not in QUESTION_CATEGORIES:
        problems.append(
            f"{tag}: category '{category}' must be one of "
            f"{', '.join(QUESTION_CATEGORIES)}"
        )
    question_text = item.get("question")
    if not _nonempty(question_text):
        problems.append(f"{tag}: missing question")
    elif not str(question_text).rstrip().endswith("?"):
        problems.append(
            f"{tag}: a question is evidence-seeking, not an AC - the question "
            "text must be a real question"
        )
    if not _nonempty(item.get("why_material")):
        problems.append(
            f"{tag}: missing why_material - only questions whose answers could "
            "materially improve acceptance understanding or coverage may be "
            "planned"
        )
    triggering = item.get("triggering_evidence_ids")
    if not isinstance(triggering, list) or not triggering:
        problems.append(f"{tag}: triggering_evidence_ids must be a non-empty list")
    if not _nonempty(item.get("acceptance_impact")):
        problems.append(f"{tag}: missing acceptance_impact")
    applicability = item.get("applicability")
    if applicability not in QUESTION_APPLICABILITY:
        problems.append(
            f"{tag}: applicability '{applicability}' must be one of "
            f"{', '.join(QUESTION_APPLICABILITY)}"
        )
    requirement = item.get("research_requirement")
    if requirement not in RESEARCH_REQUIREMENTS:
        problems.append(
            f"{tag}: research_requirement '{requirement}' must be one of "
            f"{', '.join(RESEARCH_REQUIREMENTS)}"
        )
    status = item.get("status")
    if status not in QUESTION_STATUSES:
        problems.append(
            f"{tag}: status '{status}' must be one of {', '.join(QUESTION_STATUSES)}"
        )
    if item.get("is_ac") or item.get("ac_id") or item.get("promoted_to_ac"):
        problems.append(
            f"{tag}: a question is not an AC - question records cannot declare "
            "acceptance identity"
        )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["question_plan"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["question_plan.items must be a list"]
    problems = []
    budget = block.get("budget", DEFAULT_QUESTION_BUDGET)
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        problems.append(
            f"question_plan.budget must be a positive integer (got {budget!r})"
        )
        budget = DEFAULT_QUESTION_BUDGET

    seen_ids = set()
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        qid = item.get("question_id") if isinstance(item, dict) else None
        if qid:
            if qid in seen_ids:
                problems.append(
                    f"question_plan.items[{i}]: duplicate question_id '{qid}'"
                )
            seen_ids.add(qid)

    overflow = block.get("overflow")
    overflow_items = []
    if overflow is not None:
        if not isinstance(overflow, dict):
            problems.append("question_plan.overflow must be an object")
            overflow = None
        else:
            if overflow.get("state") not in OVERFLOW_STATES:
                problems.append(
                    "question_plan.overflow.state must be QUESTION_BUDGET_EXCEEDED "
                    "- the overflow state is the explicit escalation, not silence"
                )
            if not _nonempty(overflow.get("escalation")):
                problems.append(
                    "question_plan.overflow.escalation must say who/what the "
                    "overflow escalates to"
                )
            overflow_items = overflow.get("items", [])
            if not isinstance(overflow_items, list):
                problems.append("question_plan.overflow.items must be a list")
                overflow_items = []
    if overflow_items:
        for i, item in enumerate(overflow_items):
            problems.extend(_validate_item(i, item, overflow=True))
            qid = item.get("question_id") if isinstance(item, dict) else None
            if qid:
                if qid in seen_ids:
                    problems.append(
                        f"question_plan.overflow.items[{i}]: duplicate "
                        f"question_id '{qid}'"
                    )
                seen_ids.add(qid)

    if len(items) > budget and overflow is None:
        problems.append(
            f"question_plan: material-question budget {budget} exceeded "
            f"({len(items)} questions) without an explicit overflow/escalation "
            "state - never silently discard questions"
        )
    if overflow is not None and len(items) > budget:
        problems.append(
            f"question_plan: {len(items)} questions remain in the main plan over "
            f"the budget {budget}; move the excess into the overflow block so "
            "every question is dispositioned explicitly"
        )
    if overflow is not None and not overflow_items and len(items) <= budget:
        # An empty overflow block is noise, not an error.
        pass

    distinct_categories = {
        item.get("category")
        for item in [*items, *overflow_items]
        if isinstance(item, dict) and item.get("category") in QUESTION_CATEGORIES
    }
    if len(distinct_categories) >= CATEGORY_CARPET_THRESHOLD:
        problems.append(
            f"question_plan: {len(distinct_categories)} distinct categories "
            "emitted for one ticket - do not emit every category for every "
            "ticket; plan only questions whose answers could materially improve "
            "acceptance understanding or coverage"
        )
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "QuestionPlanner: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    block = manifest["question_plan"]
    n = len(block.get("items", []) or [])
    overflow = block.get("overflow") or {}
    extra = len(overflow.get("items", []) or []) if isinstance(overflow, dict) else 0
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"QuestionPlanner: {status} ({n} question(s), {extra} overflow)"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Question Planner gate for Question-Based UAC reasoning"
    )
    ap.add_argument("--manifest")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    print(summarize(manifest))
    return 0 if not validate(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
