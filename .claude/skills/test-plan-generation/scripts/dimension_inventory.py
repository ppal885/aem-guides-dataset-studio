"""Enumerate-first dimension inventory (G2), fail-closed.

WHY THIS EXISTS
---------------
The recurring failure is authoring ACs from the ticket text plus a couple of greps,
then having a reviewer add the dimension that was missed (an entry point, a sibling
surface, a state/config partition, an output-preset variant, an error path). The fix
is to force enumeration of the WHOLE dimension space BEFORE the ACs are written, and
make every dimension carry an explicit disposition.

This gate requires a behavioural plan to declare a manifest `dimension_inventory`
block that dispositions each canonical dimension. It is fail-closed: a behavioural
plan (one that has acceptance criteria) with no inventory block - and no concrete
opt-out - does not pass. When the block is present, every canonical dimension must be
dispositioned. The point is discovery discipline, not paperwork: a dimension that does
not apply is dispositioned NOT_APPLICABLE with a one-line reason, which still proves it
was considered rather than forgotten.

Trace code (consumers, siblings, entry points) in the BACKGROUND to fill this in; the
ACs themselves stay plain QE English (see coverage_forcing plain-language rule).

Generic only. Standard library only.
"""
from __future__ import annotations

import re

# The canonical dimension space every behavioural UAC must consider.
CANONICAL_DIMENSIONS = {
    "entry_points": "every way the behaviour can be triggered (UI action, API, service, scheduler)",
    "consumers_and_siblings": "code consumers and adjacent/sibling surfaces that share the touched path",
    "state_config_partitions": "on/off settings, profiles, baselines, locales and other state axes (both values)",
    "output_scope": "which output presets/types are affected; DITA-OT processing on/off where relevant",
    "error_and_negative_paths": "failure, invalid-input, empty and boundary conditions",
    "performance_scale": "behaviour at volume/scale/timeout when any workload signal exists",
    "security": "input parsing, injection, permission/tenant surfaces when relevant",
    "localization": "language/locale/translation surfaces when relevant",
    "upgrade_migration": "versioned or persisted state, upgrade/downgrade, older data",
    "regression_surface": "existing behaviour that must not break",
}
DISPOSITIONS = ("COVERED_BY_AC", "OPEN_QUESTION", "OUT_OF_SCOPE", "NOT_APPLICABLE")


def _acceptance_block(plan_text: str) -> str:
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def _has_acceptance_criteria(plan_text: str) -> bool:
    for raw in _acceptance_block(plan_text).splitlines():
        if re.match(r"^\s*(?:[-*]\s*)?AC[-\s]?\d", raw, re.I):
            return True
    return False


def _opt_out_reason(manifest) -> str:
    if not isinstance(manifest, dict):
        return ""
    na = manifest.get("dimension_inventory_not_applicable")
    if isinstance(na, dict):
        return str(na.get("reason", "")).strip()
    if isinstance(na, str):
        return na.strip()
    return ""


def _dispositioned(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    disp = str(entry.get("disposition", "")).strip()
    reason = str(entry.get("reason", "")).strip()
    return disp in DISPOSITIONS and len(reason) >= 8


def validate(manifest, plan_text: str = "") -> list[str]:
    # Only behavioural plans (those that actually assert acceptance criteria) are gated.
    if not _has_acceptance_criteria(plan_text):
        return []
    if len(_opt_out_reason(manifest)) >= 12:
        return []
    inv = manifest.get("dimension_inventory") if isinstance(manifest, dict) else None
    if not isinstance(inv, dict) or not inv:
        return [
            "This UAC has acceptance criteria but declares no dimension_inventory. "
            "Enumerate the dimension space FIRST and disposition each of: "
            + ", ".join(CANONICAL_DIMENSIONS)
            + " (each COVERED_BY_AC / OPEN_QUESTION / OUT_OF_SCOPE / NOT_APPLICABLE with a "
            "reason), or set dimension_inventory_not_applicable with a concrete reason."
        ]
    problems: list[str] = []
    for dim, desc in CANONICAL_DIMENSIONS.items():
        if not _dispositioned(inv.get(dim)):
            problems.append(
                f"dimension_inventory.{dim} is not dispositioned ({desc}). "
                "Set disposition (COVERED_BY_AC/OPEN_QUESTION/OUT_OF_SCOPE/NOT_APPLICABLE) "
                "and a reason of at least 8 characters."
            )
    return problems


def summarize(manifest, plan_text: str = "") -> str:
    problems = validate(manifest, plan_text)
    lines = [f"DimensionInventory: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.extend(f"  {p}" for p in problems)
    return "\n".join(lines)


def _full_inventory(**overrides) -> dict:
    inv = {d: {"disposition": "NOT_APPLICABLE", "reason": "not relevant to this change"} for d in CANONICAL_DIMENSIONS}
    inv.update(overrides)
    return inv


def run_self_tests() -> None:
    nl = chr(10)
    non_behavioural = nl.join(["**Understanding**", "Some context.", ""])
    assert validate({}, non_behavioural) == [], "no ACs -> not gated"

    behavioural = nl.join([
        "**Acceptance Criteria**",
        "- AC-01: the selected topic publishes.",
        ""])
    # Missing block -> fail closed.
    assert any("no dimension_inventory" in p for p in validate({}, behavioural)), "behavioural plan without inventory must fail"

    # Incomplete block -> fail on the missing dimension.
    partial = {"dimension_inventory": {"entry_points": {"disposition": "COVERED_BY_AC", "reason": "map dashboard + api + service"}}}
    probs = validate(partial, behavioural)
    assert any("regression_surface" in p for p in probs), "missing dimension must be flagged"

    # Complete block -> pass.
    complete = {"dimension_inventory": _full_inventory(
        entry_points={"disposition": "COVERED_BY_AC", "reason": "map dashboard, api, service all covered"},
        regression_surface={"disposition": "COVERED_BY_AC", "reason": "baseline path and full publish covered"},
    )}
    assert validate(complete, behavioural) == [], f"complete inventory must pass: {validate(complete, behavioural)}"

    # Opt-out -> pass.
    assert validate({"dimension_inventory_not_applicable": {"reason": "pure typo fix in a doc string, no behaviour"}}, behavioural) == [], "opt-out must pass"

    print("dimension_inventory self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
