"""FluffyJaws supporting-discovery evidence gate (flag-gated, backward-compatible).

WHY THIS EXISTS
---------------
FluffyJaws can query the whole Experience League + AEM Guides product-doc surface
on demand, which strengthens *discovery* of relevant behaviour. But FluffyJaws
synthesis is NOT an authority: it can hallucinate, and its answer is generated
prose, not a citable normative source. So this gate enforces the same invariant
the backend provider enforces:

  * FluffyJaws evidence is ALWAYS `SUPPORTING_DISCOVERY` only.
  * It can never be the SOLE basis for a Covered / Partially covered claim.
  * Anything FluffyJaws surfaces must be RE-GROUNDED in a first-class source
    (spec / DITA-OT / product doc / current code / historical Jira) that keeps
    its own authority, before it can raise an AC's coverage.
  * There is no FluffyJaws -> AC path.

FLAG-GATED / NO-OP TODAY
------------------------
Live FluffyJaws access is auth-gated (Adobe Okta OAuth + human-registered service
app; see docs/fluffyjaws_setup.md). Until a human configures it, `probe()` reports
DISABLED and the skill must fall back to the existing RAG path (ask_dita_expert +
lookup_aem_guides + local corpus). When unavailable, the manifest block must carry
no discoveries. The gate activates only when a `fluffyjaws` block is present, so
absence is always a clean PASS and existing plans are unaffected.

Generic only. Stdlib only.
"""
from __future__ import annotations

import os
import re

MODES = ("FLUFFYJAWS_DISABLED", "FLUFFYJAWS_SHADOW", "FLUFFYJAWS_SECOND_PASS")
MODE_ENV = "SKILL_FLUFFYJAWS_MODE"
SUPPORTING_AUTHORITY = "SUPPORTING_DISCOVERY"

# First-class authorities a FluffyJaws discovery must re-ground into. Mirrors
# evidence_authority_resolver.AUTHORITY_DIMENSIONS (SUPPORTING_DISCOVERY is
# deliberately excluded - discovery cannot re-ground into more discovery).
FIRST_CLASS_AUTHORITIES = frozenset({
    "PRODUCT_REQUIREMENT_AUTHORITY", "SPECIFICATION_AUTHORITY",
    "IMPLEMENTATION_AUTHORITY", "HISTORICAL_BEHAVIOR", "TEST_EVIDENCE",
})

# Never allow anything token/secret-shaped inside the manifest block.
_SECRET_KEY_RE = re.compile(
    r"(?i)(authorization|cookie|token|secret|password|api[_-]?key|bearer|x-user-token)"
)


def probe(env=None):
    """Report the flag-gated availability of live FluffyJaws for the skill.

    Returns {mode, available}. Default-off: absent/blank/unknown -> DISABLED.
    Even when a non-DISABLED mode is requested, `available` stays False here
    because this skill process has no injected authenticated transport; a real
    availability signal must come from the configured backend, not this probe.
    """
    source = os.environ if env is None else env
    raw = str(source.get(MODE_ENV, "") or "").strip().upper()
    mode = raw if raw in MODES else "FLUFFYJAWS_DISABLED"
    return {"mode": mode, "available": False}


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("fluffyjaws"), dict)


def _collect_authoritative_ids(manifest):
    """evidence_ids in evidence_authority.items that carry a first-class authority."""
    ok = set()
    ea = manifest.get("evidence_authority") if isinstance(manifest, dict) else None
    items = ea.get("items", []) if isinstance(ea, dict) else []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        eid = (it.get("evidence_id") or "").strip()
        if eid and it.get("authority") in FIRST_CLASS_AUTHORITIES:
            ok.add(eid)
    return ok


def validate_block(manifest):
    problems = []
    if not is_present(manifest):
        return problems
    block = manifest["fluffyjaws"]

    mode = block.get("mode")
    if mode not in MODES:
        problems.append(f"fluffyjaws.mode '{mode}' must be one of {', '.join(MODES)}")

    available = block.get("available")
    if not isinstance(available, bool):
        problems.append("fluffyjaws.available must be a boolean")

    discoveries = block.get("discoveries", [])
    if not isinstance(discoveries, list):
        problems.append("fluffyjaws.discoveries must be a list")
        discoveries = []

    # Disabled or unavailable => no discoveries may be claimed.
    if (mode == "FLUFFYJAWS_DISABLED" or available is False) and discoveries:
        problems.append(
            "fluffyjaws: discoveries present while DISABLED/unavailable - a "
            "flag-off or auth-blocked FluffyJaws makes no calls, so it can carry "
            "no evidence; fall back to ask_dita_expert + lookup_aem_guides + corpus"
        )

    authoritative_ids = _collect_authoritative_ids(manifest)
    for i, d in enumerate(discoveries):
        tag = f"fluffyjaws.discoveries[{i}]"
        if not isinstance(d, dict):
            problems.append(f"{tag}: each discovery must be an object")
            continue
        if (d.get("authority") or "") != SUPPORTING_AUTHORITY:
            problems.append(
                f"{tag}: authority must be '{SUPPORTING_AUTHORITY}' - FluffyJaws "
                f"synthesis is never a first-class authority"
            )
        if not (d.get("query") or "").strip():
            problems.append(f"{tag}: missing query")
        regrounded = d.get("regrounded_evidence_id")
        regrounded_list = (
            regrounded if isinstance(regrounded, list)
            else [regrounded] if isinstance(regrounded, str) and regrounded.strip()
            else []
        )
        if not regrounded_list:
            problems.append(
                f"{tag}: missing regrounded_evidence_id - a FluffyJaws discovery "
                f"cannot stand alone; it must be re-grounded in a first-class source"
            )
        for rid in regrounded_list:
            if rid not in authoritative_ids:
                problems.append(
                    f"{tag}: regrounded_evidence_id '{rid}' is not a first-class "
                    f"authoritative evidence item (spec/impl/product-doc/history/test)"
                )
        # If a discovery claims to ground an AC, re-grounding is mandatory (already
        # enforced above) - restate the no-direct-promotion invariant explicitly.
        if d.get("promotes_ac") is True:
            problems.append(
                f"{tag}: promotes_ac must not be true - there is no FluffyJaws -> AC "
                f"path; only the re-grounded first-class source may support an AC"
            )
        # No secrets anywhere in the discovery record.
        for key in d.keys():
            if _SECRET_KEY_RE.search(str(key)):
                problems.append(f"{tag}: secret-shaped key '{key}' is forbidden in the manifest")

    return problems


def summarize(manifest):
    problems = validate_block(manifest)
    status = "CLEAN" if not problems else "ISSUES"
    if not is_present(manifest):
        status = "NOT_PRESENT (backward-compatible)"
    lines = [f"FluffyJawsEvidence: {status}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="FluffyJaws supporting-discovery evidence gate")
    ap.add_argument("--manifest")
    ap.add_argument("--probe", action="store_true", help="print flag-gated availability")
    args = ap.parse_args()

    if args.probe:
        print(json.dumps(probe(), indent=2))
        return 0

    manifest = {}
    if args.manifest:
        with open(args.manifest, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    print(summarize(manifest))
    return 0 if not validate_block(manifest) else 1


if __name__ == "__main__":
    raise SystemExit(main())
