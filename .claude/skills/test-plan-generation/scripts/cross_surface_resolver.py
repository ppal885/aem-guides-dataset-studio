"""CrossSurfaceImpactResolver (Prompt 12) - stop a one-output change from blindly
testing every output/surface.

WHY THIS EXISTS
---------------
A New-AEM-Sites fix does not automatically impact Native PDF, HTML5, Legacy Sites,
and DITA-OT PDF. Using another output as a COMPARISON ORACLE (it shows the expected
semantics) is NOT the same as proving that output is IMPACTED by the change. This
module classifies each surface's relationship to the change and only lets a surface
be a regression target when there is evidence of shared impact.

Impact classes:
  SHARED_AFFECTED_PATH       - shares the exact changed code path.
  SHARED_UPSTREAM_MODEL      - shares a common intermediate model/state/transform.
  SEMANTIC_EQUIVALENCE_ONLY  - only shows the same DITA semantics (comparison only).
  HISTORICAL_REGRESSION_LINK - past evidence of co-regression.
  NO_EVIDENCE_OF_IMPACT      - no shared implementation/model/state/history.

Roles:
  REFERENCE_ORACLE  - used as a comparison baseline (any surface may be one).
  REGRESSION_TARGET - must be re-tested for regression (needs impact evidence).
  NOT_IN_SCOPE      - neither.

Generic only. Stdlib only.
"""

IMPACT_CLASSES = (
    "SHARED_AFFECTED_PATH",
    "SHARED_UPSTREAM_MODEL",
    "SEMANTIC_EQUIVALENCE_ONLY",
    "HISTORICAL_REGRESSION_LINK",
    "NO_EVIDENCE_OF_IMPACT",
)
ROLES = ("REFERENCE_ORACLE", "REGRESSION_TARGET", "NOT_IN_SCOPE")

# Impact classes that justify treating a surface as a regression target.
IMPACT_EVIDENCE_CLASSES = frozenset({"SHARED_AFFECTED_PATH", "SHARED_UPSTREAM_MODEL", "HISTORICAL_REGRESSION_LINK"})


def validate_surface(entry):
    problems = []
    surface = entry.get("surface", "?") if isinstance(entry, dict) else "?"
    tag = f"cross_surface '{surface}'"
    if not isinstance(entry, dict):
        return [f"{tag}: each cross_surface item must be an object"]
    if not (entry.get("surface") or "").strip():
        problems.append(f"{tag}: missing 'surface'")
    ic = entry.get("impact_class", "")
    role = entry.get("role", "")
    if ic not in IMPACT_CLASSES:
        problems.append(f"{tag}: impact_class '{ic}' must be one of {', '.join(IMPACT_CLASSES)}")
    if role not in ROLES:
        problems.append(f"{tag}: role '{role}' must be one of {', '.join(ROLES)}")
    evidence = entry.get("evidence", []) or []
    # The core rule: a REGRESSION_TARGET needs evidence of shared impact - a comparison
    # baseline or mere semantic equivalence is not proof of impact.
    if role == "REGRESSION_TARGET":
        if ic not in IMPACT_EVIDENCE_CLASSES:
            problems.append(
                f"{tag}: a REGRESSION_TARGET needs an impact class showing shared implementation/model/history "
                f"({', '.join(sorted(IMPACT_EVIDENCE_CLASSES))}); '{ic}' is not proof of impact - use "
                f"REFERENCE_ORACLE (comparison only) or NOT_IN_SCOPE"
            )
        if not evidence:
            problems.append(f"{tag}: a REGRESSION_TARGET must cite evidence of the shared path/model/history")
    return problems


def validate_cross_surface(block):
    if not isinstance(block, list):
        return ["cross_surface must be a JSON list"]
    problems = []
    for entry in block:
        problems.extend(validate_surface(entry))
    return problems


def multi_output_signal(manifest):
    """True when the behaviour model indicates more than one output/publishing surface."""
    bm = manifest.get("behavior_model") if isinstance(manifest, dict) else None
    if not isinstance(bm, dict):
        return False
    modes = [m for m in (bm.get("publishing_modes") or []) if str(m).strip()]
    return len(modes) >= 2


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("cross_surface"), list)


def summarize(manifest):
    problems = []
    if is_present(manifest):
        problems = validate_cross_surface(manifest["cross_surface"])
    lines = [f"CrossSurfaceImpactResolver: {'CLEAN' if not problems else 'ISSUES'} (multi_output_signal={multi_output_signal(manifest)})"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
