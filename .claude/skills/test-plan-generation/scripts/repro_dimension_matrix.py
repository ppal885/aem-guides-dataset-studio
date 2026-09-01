"""Reproduction-dimension matrix gate (UACFIX-05), backward-compatible.

WHY THIS EXISTS
---------------
Customer-only or configuration-dependent defects must be investigated systematically
across the dimensions that actually differ (version, deployment, preset, engine,
DITA-OT mode, locale, role, feature flag, dataset size, concurrency, ...), NOT through
random regression expansion. A matrix is built only for materially relevant
dimensions. When a customer reproduces but the internal environment does not, the
defect is not concluded invalid: the differing dimensions are identified and material
unresolved differences become Missing Questions / Open Questions. Matrix findings turn
into an AC, a configuration regression, an Open Question, or Rejected per verified
applicability. The whole matrix is never rendered into the customer-facing UAC.

Backward-compatible: absent `repro_matrix` -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

# Extensible dimension vocabulary.
DIMENSIONS = (
    "PRODUCT_VERSION", "DEPLOYMENT", "OUTPUT_TYPE", "PRESET", "ENGINE", "TEMPLATE",
    "PAGE_LAYOUT", "DITA_OT_MODE", "DITA_VERSION", "MAP_VS_BOOKMAP", "LOCALE", "ROLE",
    "FEATURE_FLAG", "CUSTOM_CONFIGURATION", "INPUT_REPRESENTATION", "EDITOR_MODE",
    "ENTRY_POINT", "DATASET_SIZE", "CONCURRENCY", "BROWSER", "PERSISTED_STATE",
    "EXISTING_OUTPUT_STATE",
)

REPRO_STATES = (
    "REPRO_CONFIRMED", "NOT_REPRODUCED", "NOT_TESTED", "NOT_APPLICABLE",
    "CUSTOMER_ONLY", "CONFIGURATION_DEPENDENT", "VERSION_DEPENDENT", "UNRESOLVED",
)

MATERIALITY = ("MATERIAL", "IMMATERIAL")

COVERAGE_STATES = (
    "COVERED_BY_AC", "CONFIGURATION_REGRESSION", "OPEN_QUESTION", "REJECTED", "NOT_TESTED",
)

# States where the customer's reproduction is not matched or not settled internally.
UNSETTLED_STATES = frozenset({"CUSTOMER_ONLY", "UNRESOLVED", "NOT_REPRODUCED"})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("repro_matrix"), dict)


def _nonempty(v):
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, list):
        return any(isinstance(x, str) and x.strip() for x in v)
    return bool(v)


def validate_cell(i, c, open_question_ids):
    problems = []
    tag = f"repro_matrix.cells[{i}]"
    if not isinstance(c, dict):
        return [f"{tag}: each cell must be an object"]

    dim = c.get("dimension")
    if dim not in DIMENSIONS:
        problems.append(f"{tag}: dimension '{dim}' must be one of {', '.join(DIMENSIONS)}")

    materiality = c.get("materiality")
    if materiality not in MATERIALITY:
        problems.append(f"{tag}: materiality must be one of {', '.join(MATERIALITY)}")
    # Overexpansion guard: only materially relevant dimensions belong in the matrix.
    if materiality == "IMMATERIAL":
        problems.append(
            f"{tag}: an IMMATERIAL dimension must not be in the matrix - build the matrix "
            f"only for materially relevant dimensions (avoid random regression expansion)"
        )

    repro = c.get("repro_status")
    if repro not in REPRO_STATES:
        problems.append(f"{tag}: repro_status must be one of {', '.join(REPRO_STATES)}")

    coverage = c.get("coverage_status")
    if coverage not in COVERAGE_STATES:
        problems.append(f"{tag}: coverage_status must be one of {', '.join(COVERAGE_STATES)}")

    if not _nonempty(c.get("evidence")):
        problems.append(f"{tag}: evidence is required")

    # A material customer-vs-internal difference must not be concluded invalid; it must
    # become an Open Question, never REJECTED without resolution.
    if materiality == "MATERIAL" and repro in UNSETTLED_STATES:
        if coverage == "REJECTED":
            problems.append(
                f"{tag}: a MATERIAL '{repro}' difference cannot be REJECTED - a customer "
                f"reproduction that is not matched internally must become an Open Question, "
                f"not concluded invalid"
            )
        oq = str(c.get("open_question_ref", "")).strip()
        if not oq:
            problems.append(
                f"{tag}: a MATERIAL '{repro}' difference must reference an Open Question "
                f"(open_question_ref) for the unresolved differing dimension"
            )
        elif open_question_ids is not None and oq not in open_question_ids:
            problems.append(f"{tag}: open_question_ref '{oq}' is not a declared Open Question")
    return problems


def _open_question_ids(manifest):
    oqs = manifest.get("open_questions") if isinstance(manifest, dict) else None
    if not isinstance(oqs, list):
        return None
    return {str(o.get("id")).strip() for o in oqs if isinstance(o, dict) and o.get("id")}


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["repro_matrix"]
    cells = block.get("cells", [])
    if not isinstance(cells, list):
        return ["repro_matrix.cells must be a list"]
    oq_ids = _open_question_ids(manifest)
    problems = []
    seen = set()
    for i, c in enumerate(cells):
        problems.extend(validate_cell(i, c, oq_ids))
        if isinstance(c, dict) and c.get("dimension"):
            if c["dimension"] in seen:
                problems.append(f"repro_matrix.cells[{i}]: duplicate dimension '{c['dimension']}'")
            seen.add(c["dimension"])
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "ReproDimensionMatrix: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["repro_matrix"].get("cells", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"ReproDimensionMatrix: {status} ({n} dimension(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Reproduction-dimension matrix gate (UACFIX-05)")
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
