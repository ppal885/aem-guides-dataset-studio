"""AffectedSurfaceDimensionExplorer - force ACs to cover the FULL dimension space
of the affected code surface, not only the ticket's reported symptom.

WHY THIS EXISTS
---------------
A whole class of missing acceptance criteria comes from deriving ACs off the
ticket's REPORTED surface plus the entities the ticket happens to name. But the
affected handler usually branches over an OPERATION ENUM (e.g. an OVERWRITE /
MOVE / KEEP_BOTH set) and its behaviour is gated by a SET of co-located CONFIG
keys (several properties under one OSGi PID). If the plan asserts the contract
only for the reported operation and the one config key the ticket named, it
silently omits the other operations and the adjacent config surface the fix
interacts with. That is exactly how GUIDES-46111 shipped without an
Overwrite-vs-Move isolation AC and without a version-on-overwrite AC.

This module makes the discipline mandatory and generic: when the plan grounds a
handler / operation / config artifact, it must ENUMERATE each dimension of that
surface (discovered from the inspected code, NOT hardcoded here) and map every
value to a covering AC, an explicit OUT_OF_SCOPE disposition with a reason, or an
OPEN_QUESTION. The gate enforces completeness of that mapping; it hardcodes no
operation, key, or branch. Stdlib only.
"""

import re

# Kinds of dimension a code surface can expose. Generic - no product specifics.
DIMENSION_KINDS = ("OPERATION_ENUM", "CONFIG_SURFACE", "BRANCH_SET", "CALLER_SET", "OUTPUT_SET", "STATE_SET")
# How each enumerated value is accounted for.
DISPOSITIONS = ("COVERED", "OUT_OF_SCOPE", "OPEN_QUESTION")

_AC_ID_RE = re.compile(r"\bAC-\d{2}\b")


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("affected_surface_dimensions"), dict)


def is_active(manifest, plan_text=""):
    """Expected when the plan grounds a handler/operation/config artifact - those
    are exactly the surfaces that carry an operation enum or a config key set."""
    if not isinstance(manifest, dict):
        return False
    if manifest.get("behaviour_matters", True) is False:
        return False
    ig = manifest.get("implementation_grounding")
    if not isinstance(ig, dict):
        return False
    for art in (ig.get("named_artifacts") or []):
        if isinstance(art, dict) and art.get("material", True) and art.get("kind") in (
            "handler", "operation", "service_class", "config_key", "api"
        ):
            return True
    return False


def _validate_dimension(dim, i, *, ac_ids, open_ids):
    problems = []
    tag = f"affected_surface_dimensions.dimensions[{i}]"
    if not isinstance(dim, dict):
        return [f"{tag} must be an object"]
    if not str(dim.get("name", "")).strip():
        problems.append(f"{tag} is missing 'name'")
    kind = str(dim.get("kind", "")).strip()
    if kind not in DIMENSION_KINDS:
        problems.append(f"{tag}.kind must be one of {', '.join(DIMENSION_KINDS)}")
    if not str(dim.get("source", "")).strip():
        problems.append(f"{tag} must cite a 'source' (the code/evidence the enumeration was read from, e.g. a file:line or PID)")
    values = dim.get("values")
    if not isinstance(values, list) or not any(str(v).strip() for v in values):
        problems.append(f"{tag}.values must be a non-empty list of the enumerated dimension values (operations/keys/branches)")
        values = []
    coverage = dim.get("coverage")
    if not isinstance(coverage, dict):
        problems.append(f"{tag}.coverage must be an object mapping each value to a disposition")
        coverage = {}
    # Every enumerated value must be accounted for.
    for v in values:
        v = str(v).strip()
        if not v:
            continue
        entry = coverage.get(v)
        if not isinstance(entry, dict):
            problems.append(f"{tag} value '{v}' has no coverage entry - map it to a covering AC, OUT_OF_SCOPE (with a "
                            "reason), or OPEN_QUESTION; every operation/config value on the affected surface must be "
                            "consciously covered or dispositioned, not silently omitted")
            continue
        disp = str(entry.get("disposition", "")).strip()
        if disp not in DISPOSITIONS:
            problems.append(f"{tag} value '{v}' disposition must be one of {', '.join(DISPOSITIONS)}")
            continue
        if disp == "COVERED":
            ac = str(entry.get("ac", "") or "").strip()
            if not ac:
                problems.append(f"{tag} value '{v}' is COVERED but names no acceptance criterion ('ac')")
            elif ac_ids is not None and not set(_AC_ID_RE.findall(ac)).issubset(ac_ids):
                problems.append(f"{tag} value '{v}' maps to '{ac}' which is not an AC defined in the plan")
        elif disp == "OUT_OF_SCOPE":
            if not str(entry.get("reason", "") or "").strip():
                problems.append(f"{tag} value '{v}' is OUT_OF_SCOPE but gives no reason - state why this operation/key "
                                "is not part of the affected contract")
        elif disp == "OPEN_QUESTION":
            ref = str(entry.get("open_question_ref", "") or "").strip()
            if not ref:
                problems.append(f"{tag} value '{v}' is OPEN_QUESTION but names no open_question_ref")
            elif open_ids and ref not in open_ids:
                problems.append(f"{tag} value '{v}' open_question_ref '{ref}' is not in the plan's open_questions")
    return problems


def validate_affected_surface(block, *, ac_ids=None, open_question_ids=None):
    if not isinstance(block, dict):
        return ["affected_surface_dimensions must be a JSON object"]
    if not isinstance(block.get("active", True), bool):
        return ["affected_surface_dimensions.active must be a boolean"]
    if not block.get("active", True):
        return []
    dims = block.get("dimensions")
    if not isinstance(dims, list) or not dims:
        return ["affected_surface_dimensions.dimensions must be a non-empty list (enumerate the affected surface's "
                "operation enum and config-key set, discovered from the inspected code)"]
    open_ids = set(open_question_ids or [])
    problems = []
    for i, dim in enumerate(dims):
        problems += _validate_dimension(dim, i, ac_ids=ac_ids, open_ids=open_ids)
    return problems


def summarize(manifest, plan_text=""):
    lines = [f"AffectedSurfaceDimensionExplorer: active={is_active(manifest, plan_text)} present={is_present(manifest)}"]
    if is_present(manifest):
        for p in validate_affected_surface(manifest["affected_surface_dimensions"]):
            lines.append(f"  {p}")
    return "\n".join(lines)
