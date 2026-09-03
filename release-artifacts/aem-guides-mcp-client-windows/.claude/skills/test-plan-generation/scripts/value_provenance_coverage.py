"""Value-provenance coverage gate (generic anti-miss), backward-compatible.

WHY THIS EXISTS
---------------
A recurring miss class: when a ticket is about a VALUE (a property, metadata,
attribute, config, or state) that is written to an output/artifact, the ACs cover only
ONE way the value is set (usually the authoring UI or a preset) and silently ignore the
other provenance channels the value can arrive through - most often the repository node
edited via CRX/DE (jcr:content/metadata), but also the source map/topic file, an
API/import, or migration. The product reads the value from the repository node, so a
value set through any channel must be handled; testing only the UI path under-covers the
contract.

Structural gates cannot force discovery of a dimension the author never considered, so
this is a HARD, signal-activated requirement (like publishing_scope_coverage): when the
plan's Acceptance Criteria are about a value written to an output, they must explicitly
address at least one value-provenance channel beyond the authoring UI - typically the
repository/source-node (CRX/DE) source. Non-value tickets are unaffected.

Generic only. Stdlib only.
"""
from __future__ import annotations

import re

# Activate when the ACs concern a value/metadata/property written to an output artifact.
VALUE_SIGNALS = (
    "metadata.xml", "sourceprops", "source props", "file (asset) propert",
    "file properties", "file property", "metadata value", "property value",
    "written to metadata", "metadata is written", "properties are written",
    "attribute value", "config value", "preset value",
)

# At least one explicit provenance channel beyond the authoring UI must be covered.
PROVENANCE_TERMS = (
    "crx", "crxde", "crx/de", "crx de", "jcr:content", "jcr content",
    "repository node", "repository value", "repository metadata", "source asset",
    "asset metadata node", "dam propert", "map file", "source file", "imported",
    "api", "migration", "provenance",
)

WRITTEN_RE = re.compile(r"\b(written|write|reads?|read from|set (?:in|on|via|through)|generated|contain)\b", re.IGNORECASE)


def _acceptance_block(plan_text):
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def is_value_ticket(plan_text):
    ac = _acceptance_block(plan_text).lower()
    if not any(sig in ac for sig in VALUE_SIGNALS):
        return False
    # Require that the value is actually read/written/generated, not merely named.
    return bool(WRITTEN_RE.search(ac))


def validate(manifest, plan_text=""):
    if not is_value_ticket(plan_text):
        return []
    # Honest disposition: the ACs may be phrased in value terms while the actual defect
    # is NOT about how the value is set (e.g. a rendering/merge defect where the value is
    # blank even for a normally authored value). Such a ticket may opt out with a concrete
    # value_provenance_not_applicable reason, rather than being forced to assert an
    # irrelevant write-channel provenance AC.
    na = manifest.get("value_provenance_not_applicable") if isinstance(manifest, dict) else None
    na_reason = ""
    if isinstance(na, dict):
        na_reason = str(na.get("reason", "")).strip()
    elif isinstance(na, str):
        na_reason = na.strip()
    if len(na_reason) >= 12:
        return []
    ac = _acceptance_block(plan_text).lower()
    if not any(term in ac for term in PROVENANCE_TERMS):
        return [
            "value ticket: an acceptance criterion must address the value's provenance - "
            "how the value can be set beyond the authoring UI (repository node via CRX/DE / "
            "jcr:content metadata, source map/topic file, API/import, or migration) and that "
            "the product uses the correct source value"
        ]
    return []


def summarize(manifest, plan_text=""):
    if not is_value_ticket(plan_text):
        return "ValueProvenanceCoverage: NOT_APPLICABLE (not a value/metadata ticket)"
    problems = validate(manifest, plan_text)
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"ValueProvenanceCoverage: {status}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Value-provenance coverage gate")
    ap.add_argument("--manifest")
    ap.add_argument("--plan")
    args = ap.parse_args()
    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    plan_text = ""
    if args.plan:
        with open(args.plan, "r", encoding="utf-8") as fh:
            plan_text = fh.read()
    print(summarize(manifest, plan_text))
    return 0 if not validate(manifest, plan_text) else 1


if __name__ == "__main__":
    raise SystemExit(main())
