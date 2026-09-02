"""Publishing DITA-OT + preset scope coverage gate (backward-compatible).

WHY THIS EXISTS
---------------
On a PUBLISHING ticket (component Publishing, or an output preset / output generation
is in scope), the acceptance criteria must explicitly address (1) DITA-OT processing
ON and OFF - i.e. the DITA-OT engine mode versus the native engine, which mode is in
scope and what stays unchanged in the other - and (2) preset IN-scope / OUT-of-scope,
i.e. which output preset the change applies to and which presets are out of scope
unless shared-code analysis proves the path is shared. Publishing behaviour diverges
sharply by engine and by preset, so an AC set that ignores either silently under- or
over-scopes the fix. This is a required product policy for publishing UACs.

Only fires for publishing tickets, so non-publishing plans are unaffected.

Generic only. Stdlib only.
"""
from __future__ import annotations

import re

# The check activates for these signals.
PUBLISHING_COMPONENT = "publishing"
PUBLISHING_TEXT_SIGNALS = (
    "output preset", "native pdf", "dita-ot", "dita ot", "publish", "html5",
    "aem site", "output generation", "generated output",
)

DITA_OT_RE = re.compile(r"dita[\s-]?ot", re.IGNORECASE)
PRESET_SCOPE_RE = re.compile(
    r"\b(out of scope|out-of-scope|in scope|in-scope|scoped to|preset only|"
    r"unless shared[\s-]?code|shared[\s-]?code analysis|other preset)\b",
    re.IGNORECASE,
)
ENGINE_MODE_RE = re.compile(
    r"\b(dita[\s-]?ot (engine|mode|processing|preset)|native engine|"
    r"native pdf|nativeoutput|engine mode|processing engine)\b",
    re.IGNORECASE,
)


def _components(manifest):
    issue = manifest.get("issue") if isinstance(manifest, dict) else None
    comps = issue.get("components") if isinstance(issue, dict) else []
    return [str(c).strip().lower() for c in comps] if isinstance(comps, list) else []


# Sections that describe OTHER tickets (historical neighbours), not this ticket's
# own scope. A neighbour's title mentioning "native pdf" must not misclassify the
# ticket - the strong-signal scan runs only over the ticket's own sections.
_NEIGHBOUR_SECTIONS = ("Known Jira Bugs", "Past Similar Tickets")


def _own_scope_text(plan_text):
    """Return the plan text with the historical-neighbours section removed, so a
    neighbouring ticket's title cannot trigger the publishing classification."""
    if not plan_text:
        return ""
    text = plan_text
    for name in _NEIGHBOUR_SECTIONS:
        # Drop from a header containing the neighbour-section name to the next header.
        text = re.sub(
            rf"\*\*[^*\n]*{re.escape(name)}[^*\n]*\*\*.*?(?=\n\*\*|\Z)",
            "",
            text,
            flags=re.S,
        )
    return text


def is_publishing_ticket(manifest, plan_text=""):
    if PUBLISHING_COMPONENT in _components(manifest):
        return True
    hay = _own_scope_text(plan_text).lower()
    # Require a preset/output-generation signal, not merely the word "publish".
    strong = ("output preset", "native pdf", "dita-ot", "dita ot", "output generation")
    return any(sig in hay for sig in strong)


def _acceptance_block(plan_text):
    """Return only the Acceptance Criteria section text (where the contract lives)."""
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def validate(manifest, plan_text=""):
    if not is_publishing_ticket(manifest, plan_text):
        return []
    problems = []
    ac_text = _acceptance_block(plan_text)

    if not DITA_OT_RE.search(ac_text) or not ENGINE_MODE_RE.search(ac_text):
        problems.append(
            "publishing ticket: an acceptance criterion must address DITA-OT processing "
            "ON and OFF (the DITA-OT engine mode versus the native engine, which mode is "
            "in scope and what stays unchanged in the other)"
        )
    if not PRESET_SCOPE_RE.search(ac_text):
        problems.append(
            "publishing ticket: an acceptance criterion must state preset IN-scope / "
            "OUT-of-scope (which output preset the change applies to, and which presets "
            "are out of scope unless shared-code analysis proves the path is shared)"
        )
    return problems


def summarize(manifest, plan_text=""):
    if not is_publishing_ticket(manifest, plan_text):
        return "PublishingScopeCoverage: NOT_APPLICABLE (not a publishing ticket)"
    problems = validate(manifest, plan_text)
    status = "CLEAN" if not problems else "ISSUES"
    lines = [f"PublishingScopeCoverage: {status}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)


def main():
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Publishing DITA-OT + preset scope coverage gate")
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
