"""ChangeImpactExplorer (Prompt 16) - when a diff/PR/candidate fix exists, trace its
real blast radius for regression selection, without letting code impact replace
product semantics.

WHY THIS EXISTS
---------------
Inspecting only the changed method under-selects regression. The change must be
traced outward: changed code -> inputs -> callers -> shared models -> state
written/read -> downstream consumers -> outputs. Two questions matter equally: what
CAN this change affect, and what CANNOT it. A regression target must share the
modified path (with evidence). And code impact is combined WITH product contract and
semantic behaviour - never used as a replacement for them.

Generic only. Stdlib only.
"""

LIST_FIELDS = (
    "changed", "inputs", "callers", "shared_models",
    "downstream_consumers", "outputs", "can_affect", "cannot_affect",
    "tests_exercising_change",
)


def validate_change_impact(block):
    if not isinstance(block, dict):
        return ["change_impact must be a JSON object"]
    problems = []

    for f in LIST_FIELDS:
        if f in block and not isinstance(block[f], list):
            problems.append(f"change_impact.{f} must be a list")

    if not block.get("changed"):
        problems.append("change_impact.changed must list the changed files/methods (the fix under review)")

    # Both directions must be addressed - "what it cannot affect" bounds the regression.
    if not block.get("can_affect"):
        problems.append("change_impact.can_affect must state what behaviour this change can affect")
    if not block.get("cannot_affect"):
        problems.append("change_impact.cannot_affect must state what this change cannot affect (bounds the regression scope)")

    sp = block.get("state_paths")
    if sp is not None:
        if not isinstance(sp, dict):
            problems.append("change_impact.state_paths must be an object with 'written' and 'read' lists")
        else:
            for k in ("written", "read"):
                if k in sp and not isinstance(sp[k], list):
                    problems.append(f"change_impact.state_paths.{k} must be a list")

    cannot = {str(x).strip().lower() for x in (block.get("cannot_affect") or [])}
    targets = block.get("regression_targets", [])
    if targets is not None and not isinstance(targets, list):
        problems.append("change_impact.regression_targets must be a list")
        targets = []
    for i, tgt in enumerate(targets or []):
        tag = f"regression_target[{i}]"
        if not isinstance(tgt, dict):
            problems.append(f"{tag}: must be an object {{target, shared_path_evidence}}")
            continue
        name = (tgt.get("target") or "").strip()
        if not name:
            problems.append(f"{tag}: missing 'target'")
        if not (tgt.get("shared_path_evidence") or []):
            problems.append(f"{tag} '{name}': a regression target must cite shared_path_evidence tying it to the modified path")
        if name and name.lower() in cannot:
            problems.append(f"{tag} '{name}': listed as a regression target but also in cannot_affect - contradiction")

    # Code impact must be combined with product contract + semantic behaviour, not replace them.
    if block.get("product_contract_considered") is not True:
        problems.append("change_impact.product_contract_considered must be true - code impact does not replace the product contract")
    if block.get("semantic_behavior_considered") is not True:
        problems.append("change_impact.semantic_behavior_considered must be true - combine code impact with semantic behaviour")
    return problems


def has_change_signal(manifest):
    """A fix/diff/PR is available (post-fix / implementation-review)."""
    if not isinstance(manifest, dict):
        return False
    if is_present(manifest):
        return True
    return bool(manifest.get("fix_available") or manifest.get("pr") or manifest.get("diff"))


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("change_impact"), dict)


def summarize(manifest):
    problems = []
    if is_present(manifest):
        problems = validate_change_impact(manifest["change_impact"])
    lines = [f"ChangeImpactExplorer: {'CLEAN' if not problems else 'ISSUES'} (change_signal={has_change_signal(manifest)})"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
