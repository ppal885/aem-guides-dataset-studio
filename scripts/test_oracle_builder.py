"""TestOracleBuilder (Prompt 10) - make sure every functional scenario has an
observable PRODUCT oracle, not just an absence-of-exception signal.

WHY THIS EXISTS
---------------
"No NullPointerException" or "job completes SUCCESS" is necessary but NOT sufficient:
a generation may not throw yet still produce wrong output, and internal state can be
right while the UI/output is wrong. This module separates oracle types and enforces
that every P0/P1 functional scenario carries at least one observable product oracle.

Oracle types:
  PRIMARY_PRODUCT_ORACLE  - observable product outcome (output/UI/navigation/content/count).
  SECONDARY_STATE_ORACLE  - persisted/derived state (property/JCR value/collection).
  IMPLEMENTATION_ORACLE   - internal mechanism (method/param) - supporting only.
  DIAGNOSTIC_SIGNAL       - triage signal (no exception, no error, job success) - never sufficient alone.

Generic only (no domain rules). Conservative: a scenario is only flagged when it
asserts a diagnostic/success signal but names NO observable product or state outcome.
Stdlib only.
"""

import re

ORACLE_TYPES = ("PRIMARY_PRODUCT_ORACLE", "SECONDARY_STATE_ORACLE", "IMPLEMENTATION_ORACLE", "DIAGNOSTIC_SIGNAL")

# Absence-of-failure / job-status signals: necessary, never sufficient on their own.
_DIAGNOSTIC_TERMS = (
    "no nullpointerexception", "no npe", "no exception", "no error", "does not throw",
    "doesn't throw", "without a nullpointerexception", "without error", "without exception",
    "no failure", "job completes", "completes successfully", "terminal state success",
    "status success", "terminal success", "succeeds", "success", "no crash", "no stack trace",
)
# Observable PRODUCT outcomes (generous synonyms).
_PRODUCT_TERMS = (
    "shows", "show", "displays", "display", "displayed", "appears", "appear", "rendered",
    "renders", "render", "visible", "contains", "contain", "present", "listed", "label",
    "title", "navigation", "toc", "page", "pages", "count", "output", "outputs", "entry",
    "entries", "grouping", "reflects", "reflect", "updates", "updated", "produced",
    "produces", "generated site", "site navigation", "node", "nodes", "content", "link",
    "links", "matches", "matching", "value is", "equals", "correct output",
)
# Persisted/derived state outcomes.
_STATE_TERMS = (
    "property", "jcr", "guides-navigation", "persisted", "stored", "well-formed",
    "state is", "collection", "field is", "database", "repository property",
)


def classify_oracle(text):
    low = (text or "").lower()
    # State terms are more specific (property/jcr/guides-navigation) - check first so a
    # property name that contains a product-ish word (e.g. guides-navigation) is not
    # misread as a product oracle.
    if any(t in low for t in _STATE_TERMS):
        return "SECONDARY_STATE_ORACLE"
    if any(t in low for t in _PRODUCT_TERMS):
        return "PRIMARY_PRODUCT_ORACLE"
    # implementation mechanism (class.method / camelCase call)
    if re.search(r"\b[A-Z][A-Za-z0-9]*\.[a-z][A-Za-z0-9]*\b", text or "") or re.search(r"\b[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\(", text or ""):
        return "IMPLEMENTATION_ORACLE"
    if any(t in low for t in _DIAGNOSTIC_TERMS):
        return "DIAGNOSTIC_SIGNAL"
    return "DIAGNOSTIC_SIGNAL"


def _has(text, terms):
    low = (text or "").lower()
    return any(t in low for t in terms)


def is_diagnostic_only(outcome):
    """True when the outcome asserts a diagnostic/success signal but names no
    observable product or state outcome."""
    return _has(outcome, _DIAGNOSTIC_TERMS) and not _has(outcome, _PRODUCT_TERMS) and not _has(outcome, _STATE_TERMS)


def validate_scenario_oracles(block):
    """Validate a manifest `scenario_oracles` list: each P0/P1 functional scenario
    must declare at least one PRIMARY_PRODUCT_ORACLE."""
    if not isinstance(block, list):
        return ["scenario_oracles must be a JSON list"]
    problems = []
    for entry in block:
        if not isinstance(entry, dict):
            problems.append("each scenario_oracles item must be an object")
            continue
        sid = entry.get("scenario_id", "?")
        if entry.get("functional") is False:
            continue
        priority = str(entry.get("priority", "")).upper()
        if priority and priority not in ("P0", "P1", "P2"):
            problems.append(f"scenario {sid}: priority must be P0/P1/P2")
        oracles = entry.get("oracles", [])
        if not isinstance(oracles, list):
            problems.append(f"scenario {sid}: oracles must be a list")
            continue
        for o in oracles:
            if isinstance(o, dict) and o.get("type") and o["type"] not in ORACLE_TYPES:
                problems.append(f"scenario {sid}: oracle type '{o['type']}' must be one of {', '.join(ORACLE_TYPES)}")
        types = {o.get("type") for o in oracles if isinstance(o, dict)}
        if priority in ("P0", "P1") and "PRIMARY_PRODUCT_ORACLE" not in types:
            problems.append(
                f"scenario {sid}: a P0/P1 functional scenario needs a PRIMARY_PRODUCT_ORACLE - an observable "
                f"product outcome; a diagnostic signal (no exception / job success) is not sufficient"
            )
    return problems


# --- plan-body scan ----------------------------------------------------------

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_SCEN_RE = re.compile(r"^- (P[01])\b")


def _scenario_lines(plan_text):
    out, capture = [], False
    for line in (plan_text or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            capture = (m.group(1).strip() == "Test Scenarios")
            continue
        if capture and _SCEN_RE.match(line.strip()):
            out.append(line.strip())
    return out


def check_plan_scenarios(plan_text):
    """Flag P0/P1 scenarios whose expected outcome is diagnostic-only (no product/state oracle)."""
    problems = []
    for line in _scenario_lines(plan_text):
        outcome = line
        for sep in ("Expected:", "->", " - ", " then ", " Then "):
            if sep in line:
                outcome = line.split(sep, 1)[1]
                break
        if is_diagnostic_only(outcome):
            label = line.split("]", 1)[0] + "]" if "]" in line else line[:20]
            problems.append(
                f"{label}: expected result asserts only a diagnostic/success signal (no exception / job success) "
                f"with no observable product oracle - a run can succeed and still produce wrong output; add an "
                f"observable product outcome (what the navigation/output/content should show)"
            )
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("scenario_oracles"), list)


def summarize(manifest, plan_text=""):
    problems = []
    if is_present(manifest):
        problems += validate_scenario_oracles(manifest["scenario_oracles"])
    problems += check_plan_scenarios(plan_text)
    lines = [f"TestOracleBuilder: {'CLEAN' if not problems else 'ISSUES'}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
