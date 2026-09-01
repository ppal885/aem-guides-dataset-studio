"""Temporal / version-aware evidence gate (UACFIX-01), backward-compatible.

WHY THIS EXISTS
---------------
The QE Reasoner must not mix old documentation, old implementation, old UI
behaviour, historical Jira expectations, and CURRENT product behaviour as if they
were equally applicable. Authority and recency are SEPARATE dimensions: normative
DITA 1.3 stays authoritative even when old; old product docs / old GitHub code do
NOT override current behaviour; historical Human UAC teaches reasoning patterns
but does not prove current product behaviour.

This gate extends (does not replace) the evidence model. It validates temporal
version fields on any evidence record that opts in, enforces the applicability
state machine, forbids treating UNKNOWN_VERSION as current, requires version
conflicts to be preserved (not overwritten), and blocks silent AC promotion when a
material claim rests on evidence whose version applicability is unresolved.

Backward-compatible: absent temporal metadata -> clean pass.

Generic only. Stdlib only.
"""
from __future__ import annotations

TEMPORAL_STATES = (
    "CURRENTLY_APPLICABLE",
    "LIKELY_APPLICABLE",
    "HISTORICAL_REFERENCE",
    "VERSION_MISMATCH",
    "SUPERSEDED",
    "FUTURE_BEHAVIOR",
    "UNKNOWN_VERSION",
)

# States that must NOT silently ground a current AC. A material claim resting on
# one of these must be dispositioned OPEN_QUESTION / NEEDS_CURRENT_VERIFICATION.
NON_CURRENT_TEMPORAL_STATES = frozenset({
    "HISTORICAL_REFERENCE", "VERSION_MISMATCH", "SUPERSEDED",
    "FUTURE_BEHAVIOR", "UNKNOWN_VERSION",
})

# Optional version fields; recorded where available, never all required.
VERSION_FIELDS = (
    "product", "product_version", "build_version", "deployment", "cloud_or_onprem",
    "repository", "branch", "commit", "pr",
    "document_version", "document_publish_date",
    "dita_version", "dita_ot_version",
    "valid_from", "valid_to",
    "customer_version", "current_jira_version",
    "observed_at",
)

# Dispositions that make an unresolved-applicability claim safe (not silently promoted).
SAFE_UNRESOLVED_DISPOSITIONS = frozenset({"OPEN_QUESTION", "NEEDS_CURRENT_VERIFICATION"})


def _temporal_records(manifest):
    """Yield (path, record) for evidence records that opt into temporal metadata.

    A record opts in by carrying a `temporal_applicability` key. We look in the
    known evidence locations plus an explicit top-level `temporal_evidence.items`.
    """
    out = []
    if not isinstance(manifest, dict):
        return out

    def scan(container, label):
        items = container.get("items") if isinstance(container, dict) else None
        if isinstance(items, list):
            for i, it in enumerate(items):
                if isinstance(it, dict) and "temporal_applicability" in it:
                    out.append((f"{label}[{i}]", it))

    ea = manifest.get("evidence_authority")
    if isinstance(ea, dict):
        scan(ea, "evidence_authority.items")
    te = manifest.get("temporal_evidence")
    if isinstance(te, dict):
        scan(te, "temporal_evidence.items")
    bm = manifest.get("behavior_model")
    if isinstance(bm, dict):
        facts = bm.get("facts")
        if isinstance(facts, list):
            for i, f in enumerate(facts):
                if isinstance(f, dict) and "temporal_applicability" in f:
                    out.append((f"behavior_model.facts[{i}]", f))
    return out


def is_present(manifest):
    return bool(_temporal_records(manifest)) or (
        isinstance(manifest, dict) and isinstance(manifest.get("temporal_evidence"), dict)
    )


def validate_record(path, rec):
    problems = []
    state = rec.get("temporal_applicability")
    if state not in TEMPORAL_STATES:
        problems.append(
            f"{path}: temporal_applicability '{state}' must be one of {', '.join(TEMPORAL_STATES)}"
        )
        return problems  # can't reason further without a valid state

    # Unknown/non-current evidence backing a material AC-supporting claim must be
    # dispositioned safely - never silently promoted to current truth.
    supports_ac = bool(rec.get("supports_ac"))
    material = rec.get("material", True)  # default: treat as material unless told otherwise
    disposition = (rec.get("disposition") or "").upper()
    if state in NON_CURRENT_TEMPORAL_STATES and material and supports_ac:
        if disposition not in SAFE_UNRESOLVED_DISPOSITIONS:
            problems.append(
                f"{path}: state '{state}' cannot silently support an AC - disposition "
                f"must be OPEN_QUESTION or NEEDS_CURRENT_VERIFICATION (got '{disposition or 'none'}')"
            )

    # VERSION_MISMATCH / SUPERSEDED must name what supersedes/mismatches (preserve conflict).
    if state in {"VERSION_MISMATCH", "SUPERSEDED"}:
        pointer = rec.get("superseded_by") or rec.get("conflict_with")
        has_pointer = bool(pointer.strip()) if isinstance(pointer, str) else bool(pointer)
        if not has_pointer:
            problems.append(
                f"{path}: state '{state}' must record superseded_by/conflict_with "
                f"(preserve both records; do not overwrite old evidence)"
            )

    # Recency must not be used to override authority: an authoritative-but-old
    # record (e.g. DITA 1.3 spec) may not be marked SUPERSEDED merely for age.
    if state == "SUPERSEDED" and rec.get("authority_is_normative") is True:
        problems.append(
            f"{path}: a normative-authority record must not be marked SUPERSEDED by "
            f"recency alone (authority and recency are separate dimensions)"
        )
    return problems


def validate_conflicts(manifest):
    """Version conflicts must be preserved and marked, not overwritten."""
    problems = []
    te = manifest.get("temporal_evidence") if isinstance(manifest, dict) else None
    conflicts = te.get("version_conflicts", []) if isinstance(te, dict) else []
    if not isinstance(conflicts, list):
        return ["temporal_evidence.version_conflicts must be a list"]
    ids = {rid for _, rec in _temporal_records(manifest)
           if isinstance(rec, dict) for rid in [rec.get("evidence_id")] if rid}
    for i, c in enumerate(conflicts):
        tag = f"temporal_evidence.version_conflicts[{i}]"
        if not isinstance(c, dict):
            problems.append(f"{tag}: each conflict must be an object")
            continue
        between = c.get("between", [])
        if not isinstance(between, list) or len(between) < 2:
            problems.append(f"{tag}: 'between' must list at least two evidence_ids (preserve both records)")
        if not (c.get("applicability") or c.get("disposition")):
            problems.append(f"{tag}: must mark applicability/disposition, not resolve by overwrite")
    return problems


def validate(manifest):
    problems = []
    for path, rec in _temporal_records(manifest):
        problems.extend(validate_record(path, rec))
    problems.extend(validate_conflicts(manifest))
    return problems


def summarize(manifest):
    problems = validate(manifest)
    if not is_present(manifest):
        return "TemporalEvidence: NOT_PRESENT (backward-compatible)"
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"TemporalEvidence: {status} ({len(_temporal_records(manifest))} versioned record(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Temporal / version-aware evidence gate (UACFIX-01)")
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
