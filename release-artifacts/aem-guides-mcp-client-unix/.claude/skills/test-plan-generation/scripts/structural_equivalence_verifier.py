"""StructuralEquivalenceVerifier (Prompt 13) - similar-looking DITA constructs must
be VERIFIED equivalent before they generate regression coverage.

WHY THIS EXISTS
---------------
"topichead behaves like a no-href topicref because both reach the same TOC path" is a
hypothesis, not a fact. Two grouping-oriented constructs may parse differently, build
different navigation models, transform differently, or lack product-supported
equivalent output. This module requires verification across those dimensions and only
lets a proven equivalence drive regression coverage; an unproven one stays an
Investigation Candidate / Open Question.

Classifications:
  EQUIVALENT_PATH       - proven same across all verification dimensions.
  PARTIALLY_EQUIVALENT  - proven same on some dimensions, with a stated boundary.
  DIFFERENT_PATH        - proven different (no regression coverage needed).
  UNKNOWN               - not verified -> Investigation Candidate / Open Question.

Generic only. Stdlib only.
"""

EQUIVALENCE_CLASSES = ("EQUIVALENT_PATH", "PARTIALLY_EQUIVALENT", "DIFFERENT_PATH", "UNKNOWN")
VERIFICATION_DIMENSIONS = (
    "parser_representation",
    "navigation_model",
    "transformation",
    "product_supported_equivalent_output",
)
DISPOSITIONS = ("REGRESSION", "OPEN_QUESTION", "INVESTIGATION_CANDIDATE", "OUT_OF_SCOPE")
_REGRESSION_CLASSES = frozenset({"EQUIVALENT_PATH", "PARTIALLY_EQUIVALENT"})


def validate_equivalence(entry):
    problems = []
    if not isinstance(entry, dict):
        return ["each structural_equivalence item must be an object"]
    a, b = entry.get("construct_a", ""), entry.get("construct_b", "")
    tag = f"equivalence '{a or '?'}~{b or '?'}'"
    if not a or not b:
        problems.append(f"{tag}: construct_a and construct_b are both required")
    cls = entry.get("classification", "")
    if cls not in EQUIVALENCE_CLASSES:
        problems.append(f"{tag}: classification '{cls}' must be one of {', '.join(EQUIVALENCE_CLASSES)}")
    disposition = entry.get("disposition", "")
    if disposition and disposition not in DISPOSITIONS:
        problems.append(f"{tag}: disposition '{disposition}' must be one of {', '.join(DISPOSITIONS)}")

    checks = entry.get("checks", {})
    if not isinstance(checks, dict):
        problems.append(f"{tag}: checks must be an object of verification dimensions")
        checks = {}
    confirmed = [d for d in VERIFICATION_DIMENSIONS if checks.get(d) is True]
    evidence = entry.get("evidence", []) or []
    generates_regression = bool(entry.get("generates_regression"))

    if cls == "EQUIVALENT_PATH":
        missing = [d for d in VERIFICATION_DIMENSIONS if d not in confirmed]
        if missing:
            problems.append(
                f"{tag}: EQUIVALENT_PATH requires all verification dimensions confirmed with evidence; unconfirmed: "
                f"{', '.join(missing)} - do not assert equivalence 'because both reach the same path' without proof"
            )
        if not evidence:
            problems.append(f"{tag}: EQUIVALENT_PATH must cite evidence")
    elif cls == "PARTIALLY_EQUIVALENT":
        if not confirmed:
            problems.append(f"{tag}: PARTIALLY_EQUIVALENT needs at least one verified dimension")
        if not evidence:
            problems.append(f"{tag}: PARTIALLY_EQUIVALENT must cite evidence")
        if not (entry.get("boundary") or "").strip():
            problems.append(f"{tag}: PARTIALLY_EQUIVALENT must state the boundary (which dimensions differ)")
    elif cls == "UNKNOWN":
        if disposition not in ("OPEN_QUESTION", "INVESTIGATION_CANDIDATE"):
            problems.append(f"{tag}: UNKNOWN equivalence must be an OPEN_QUESTION or INVESTIGATION_CANDIDATE, not asserted")
        if generates_regression:
            problems.append(f"{tag}: UNKNOWN equivalence must not generate regression coverage")

    # Only a proven (partial/full) equivalence may drive regression coverage.
    if generates_regression and cls not in _REGRESSION_CLASSES:
        problems.append(
            f"{tag}: generates_regression is true but classification is {cls} - only EQUIVALENT_PATH or a materially "
            f"relevant PARTIALLY_EQUIVALENT may generate regression coverage"
        )
    return problems


def validate_structural_equivalence(block):
    if not isinstance(block, list):
        return ["structural_equivalence must be a JSON list"]
    problems = []
    for entry in block:
        problems.extend(validate_equivalence(entry))
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("structural_equivalence"), list)


def summarize(manifest):
    problems = []
    if is_present(manifest):
        problems = validate_structural_equivalence(manifest["structural_equivalence"])
    lines = [f"StructuralEquivalenceVerifier: {'CLEAN' if not problems else 'ISSUES'}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
