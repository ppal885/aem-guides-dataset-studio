"""Existing-vs-New behavior classification gate (backward-compatible).

WHY THIS EXISTS
---------------
Documentation may establish current product behavior while the current ticket
proposes new behavior.  "Documented today" must never be confused with
"required after this fix".  This gate validates the optional
``behavior_classification`` manifest block: every resolved behavior is
classified so coverage, promotion, and the Writer keep evidence roles honest.

Behavior classes:

- ``EXISTING_CONFIRMED`` - current behavior established by existing
  documentation / current implementation evidence only.
- ``NEW_REQUIREMENT`` - desired behavior established by the current ticket
  (or its change set) only; no existing documentation claims it.
- ``MODIFIED_EXISTING_BEHAVIOR`` - documented/current behavior the ticket
  explicitly changes.
- ``PRESERVED_EXISTING_BEHAVIOR`` - documented/current behavior that must
  remain compatible after the change.
- ``UNKNOWN`` - insufficient evidence to classify; stays unresolved.
- ``CONFLICTED`` - sources disagree.

Rules enforced (all generic):

1. Existing documentation may establish baseline/current behavior
   (``EXISTING_CONFIRMED`` requires existing-behavior evidence).
2. The current ticket may establish desired new behavior (``NEW_REQUIREMENT``
   requires requested-behavior evidence).
3. Existing documentation must not be used to claim a new feature is already
   documented: ``NEW_REQUIREMENT`` cannot cite existing-behavior evidence, and
   its source line cannot credit a documentation source.
4. New implementation/configuration must not be retroactively described as
   historical documented behavior: a change-set-only behavior is
   ``NEW_REQUIREMENT``, never ``EXISTING_CONFIRMED``.
5. Coverage explicitly identifies preserved behavior:
   ``PRESERVED_EXISTING_BEHAVIOR`` requires existing-behavior evidence.
6. The Writer may combine sources only when each genuinely supports part of the
   final AC: a source line that credits a documentation source requires
   existing-behavior evidence on the record.
7. ``UNKNOWN`` / ``CONFLICTED`` behaviors stay open until resolved.

Backward-compatible: absent ``behavior_classification`` -> clean pass.
Generic only. Stdlib only.
"""
from __future__ import annotations

BEHAVIOR_CLASSES = (
    "EXISTING_CONFIRMED",
    "NEW_REQUIREMENT",
    "MODIFIED_EXISTING_BEHAVIOR",
    "PRESERVED_EXISTING_BEHAVIOR",
    "UNKNOWN",
    "CONFLICTED",
)

# Dispositions that keep a behavior visibly open instead of finalizing it.
OPEN_DISPOSITIONS = frozenset({
    "OPEN_QUESTION",
    "PRODUCT_SCOPE_QUESTION",
    "ENGINEERING_DESIGN_DECISION",
    "PRODUCT_DECISION",
    "NEEDS_CURRENT_VERIFICATION",
})

# Source-line labels that credit documentation/current-behavior sources.  A
# source line may name them only when the record actually carries
# existing-behavior evidence (rules 3, 6 and 7).
DOCUMENTATION_SOURCE_LABELS = (
    "experience league",
    "official documentation",
    "official product documentation",
    "product documentation",
    "documentation",
    "documented behavior",
    "documented behaviour",
    "dita specification",
    "dita spec",
    "dita-ot documentation",
)

# Classes that assert an established current behavior and therefore require
# existing-behavior evidence.
_EXISTING_EVIDENCE_CLASSES = frozenset({
    "EXISTING_CONFIRMED",
    "MODIFIED_EXISTING_BEHAVIOR",
    "PRESERVED_EXISTING_BEHAVIOR",
})


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(
        manifest.get("behavior_classification"), dict
    )


def _nonempty(v):
    return bool(v.strip()) if isinstance(v, str) else bool(v)


def _cites_documentation(source_line):
    lowered = source_line.casefold()
    return any(label in lowered for label in DOCUMENTATION_SOURCE_LABELS)


def _validate_item(i, item):
    problems = []
    tag = f"behavior_classification.items[{i}]"
    if not isinstance(item, dict):
        return [f"{tag}: each item must be an object"]

    if not _nonempty(item.get("target_ref")):
        problems.append(f"{tag}: missing target_ref")
    behavior_class = item.get("behavior_class")
    if behavior_class not in BEHAVIOR_CLASSES:
        problems.append(
            f"{tag}: behavior_class '{behavior_class}' must be one of "
            f"{', '.join(BEHAVIOR_CLASSES)}"
        )
        return problems

    existing = item.get("existing_evidence_ids") or []
    requested = item.get("requested_evidence_ids") or []
    change = item.get("change_evidence_ids") or []
    source_line = item.get("source_line") or ""
    disposition = (item.get("coverage_disposition") or "").upper() or None
    open_ref = item.get("open_question_ref") or ""

    if behavior_class in _EXISTING_EVIDENCE_CLASSES and not existing:
        problems.append(
            f"{tag}: {behavior_class} requires existing-behavior evidence - "
            "existing documentation/implementation establishes the baseline"
        )
    if behavior_class == "MODIFIED_EXISTING_BEHAVIOR" and not requested and not change:
        problems.append(
            f"{tag}: MODIFIED_EXISTING_BEHAVIOR requires the current-ticket or "
            "change-set evidence that changes the documented behavior"
        )
    if behavior_class == "NEW_REQUIREMENT":
        if existing:
            problems.append(
                f"{tag}: NEW_REQUIREMENT cannot cite existing-behavior evidence - "
                "existing documentation must not claim a new feature is already "
                "documented"
            )
        if not requested and not change:
            problems.append(
                f"{tag}: NEW_REQUIREMENT requires current-ticket or change-set "
                "evidence that requests the new behavior"
            )
    if behavior_class in {"UNKNOWN", "CONFLICTED"}:
        if disposition and disposition not in OPEN_DISPOSITIONS:
            problems.append(
                f"{tag}: {behavior_class} behavior cannot finalize coverage - "
                f"disposition must be one of {', '.join(sorted(OPEN_DISPOSITIONS))}"
            )
        if not disposition and not open_ref:
            problems.append(
                f"{tag}: {behavior_class} behavior must stay visible as an open "
                "question until resolved"
            )
    if source_line:
        if behavior_class == "NEW_REQUIREMENT" and _cites_documentation(source_line):
            problems.append(
                f"{tag}: source line must not credit a documentation source for "
                "behavior that documentation does not establish"
            )
        if (
            _cites_documentation(source_line)
            and behavior_class != "NEW_REQUIREMENT"
            and not existing
        ):
            problems.append(
                f"{tag}: source line credits a documentation source the record "
                "does not carry as existing-behavior evidence - combine sources "
                "only when each genuinely supports part of the final AC"
            )
    return problems


def validate(manifest):
    if not is_present(manifest):
        return []
    block = manifest["behavior_classification"]
    items = block.get("items", [])
    if not isinstance(items, list):
        return ["behavior_classification.items must be a list"]
    problems = []
    seen_refs = set()
    for i, item in enumerate(items):
        problems.extend(_validate_item(i, item))
        ref = item.get("target_ref") if isinstance(item, dict) else None
        if ref:
            if ref in seen_refs:
                problems.append(
                    f"behavior_classification.items[{i}]: duplicate target_ref "
                    f"'{ref}'"
                )
            seen_refs.add(ref)
    return problems


def summarize(manifest):
    if not is_present(manifest):
        return "BehaviorClassification: NOT_PRESENT (backward-compatible)"
    problems = validate(manifest)
    n = len(manifest["behavior_classification"].get("items", []) or [])
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"BehaviorClassification: {status} ({n} classified behavior(s))"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(
        description="Existing-vs-New behavior classification gate"
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
