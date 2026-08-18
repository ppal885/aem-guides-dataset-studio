"""CoverageDispositionClassifier (Prompt 9) - classify every verified finding BEFORE
final generation so implementation detail never becomes formal UAC.

WHY THIS EXISTS
---------------
A plan mixes product acceptance behaviour, implementation checks, regression, and
diagnostics. Formal UAC must describe WHAT the product does (externally observable),
not HOW it is implemented. This classifier enforces that: a finding that is really
an implementation oracle (e.g. "null must be guarded before PathUtils.appendUnixSlash",
"internal JSON structure correct", "exception absent from an internal method",
"JCR property written") must NOT be dispositioned as an ACCEPTANCE_CONTRACT, and an
implementation-level statement must not appear as an Acceptance Criterion.

Dispositions:
  ACCEPTANCE_CONTRACT   - externally observable behaviour required for the feature/fix.
  REGRESSION_COVERAGE   - must-not-break behaviour, broader than the acceptance contract.
  IMPLEMENTATION_ORACLE - internal verification (method/param/property/JSON/exception);
                          testable, but not a formal AC unless the internal contract
                          itself is the requirement.
  DIAGNOSTIC_CHECK      - a signal that aids triage (e.g. "no exception in the log").
  AUTOMATION_GAP        - a coverage gap to fill in automation.
  NFR_RISK              - performance/scale/resource risk.
  OPEN_QUESTION         - unresolved product decision.
  OUT_OF_SCOPE          - proven not in scope.

Generic only (no domain/construct rules). Stdlib only.
"""

import re

DISPOSITIONS = (
    "ACCEPTANCE_CONTRACT",
    "REGRESSION_COVERAGE",
    "IMPLEMENTATION_ORACLE",
    "DIAGNOSTIC_CHECK",
    "AUTOMATION_GAP",
    "NFR_RISK",
    "OPEN_QUESTION",
    "OUT_OF_SCOPE",
)

# Strong "HOW / internal mechanism" signals. A statement is implementation-level when
# it asserts an internal mechanism rather than an observable product outcome. Kept
# conservative so ordinary ACs that merely name a property/output are NOT flagged.
_CLASS_METHOD_RE = re.compile(r"\b[A-Z][A-Za-z0-9]*\.[a-z][A-Za-z0-9]*\b")   # PathUtils.appendUnixSlash
_METHOD_CALL_RE = re.compile(r"\b[a-z][A-Za-z0-9]*[A-Z][A-Za-z0-9]*\(")       # appendUnixSlash(
_HOW_PHRASES = (
    "must be guarded", "must be null-checked", "null-guard", "guard the null",
    "not called with null", "not invoked with null", "not passed into", "passed into",
    "internal method", "private method", "internal json", "in-memory collection",
    "must be null", "null check before", "guarded before", "before path-joining",
    "does not throw in", "exception absent from", "field is set to", "sentinel value",
)


def is_implementation_level(text):
    """True when the statement asserts an internal mechanism (HOW), not an observable
    product outcome (WHAT). Conservative: needs a class.method / camelCase method call,
    or an explicit internal-mechanism phrase."""
    low = (text or "").lower()
    if any(p in low for p in _HOW_PHRASES):
        return True
    if _CLASS_METHOD_RE.search(text or ""):
        return True
    if _METHOD_CALL_RE.search(text or ""):
        return True
    return False


def validate_disposition(entry):
    problems = []
    fid = (entry.get("finding_id") or entry.get("statement", "")[:30] or "?") if isinstance(entry, dict) else "?"
    tag = f"disposition '{fid}'"
    if not isinstance(entry, dict):
        return [f"{tag}: each disposition must be an object"]
    disp = entry.get("disposition", "")
    if disp not in DISPOSITIONS:
        problems.append(f"{tag}: disposition '{disp}' must be one of {', '.join(DISPOSITIONS)}")
    if not (entry.get("statement") or "").strip():
        problems.append(f"{tag}: missing 'statement'")
    # The core rule: an implementation-level statement cannot be an acceptance contract
    # unless the internal contract itself is explicitly the requirement.
    if disp == "ACCEPTANCE_CONTRACT" and is_implementation_level(entry.get("statement", "")) \
            and not entry.get("internal_contract_is_requirement"):
        problems.append(
            f"{tag}: an implementation-level statement (HOW) is dispositioned ACCEPTANCE_CONTRACT - formal UAC "
            f"describes WHAT the product does; reclassify as IMPLEMENTATION_ORACLE (or set "
            f"internal_contract_is_requirement:true if the internal contract IS the requirement)"
        )
    # An implementation oracle must not be routed to an AC.
    if disp == "IMPLEMENTATION_ORACLE" and entry.get("maps_to_ac"):
        problems.append(f"{tag}: an IMPLEMENTATION_ORACLE must not map to an Acceptance Criterion")
    return problems


def validate_dispositions(block):
    if not isinstance(block, list):
        return ["dispositions must be a JSON list"]
    problems = []
    for e in block:
        problems.extend(validate_disposition(e))
    return problems


# --- plan-body scan (only runs for reasoning-driven plans) -------------------

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_AC_LINE_RE = re.compile(r"^- AC-\d{2,}\b")


def _acceptance_section(plan_text):
    out, capture = [], False
    for line in (plan_text or "").splitlines():
        m = _HEADING_RE.match(line.strip())
        if m:
            capture = (m.group(1).strip() == "Acceptance Criteria")
            continue
        if capture:
            out.append(line)
    return out


def check_plan_acceptance_criteria(plan_text):
    """Flag any Acceptance Criterion whose OUTCOME is implementation-level (HOW)."""
    problems = []
    for line in _acceptance_section(plan_text):
        if not _AC_LINE_RE.match(line.strip()):
            continue
        # Look only at the Then OUTCOME - after 'Then' and before the '| Evidence:' field.
        # The Evidence field legitimately cites source files (e.g. Foo.java), which must
        # not be misread as an implementation-mechanism AC.
        outcome = line.split("Then", 1)[1] if "Then" in line else line
        outcome = outcome.split("| Evidence:", 1)[0]
        if is_implementation_level(outcome):
            ac_id = line.strip().split()[1] if len(line.strip().split()) > 1 else "AC"
            problems.append(
                f"{ac_id} states an implementation mechanism (HOW) as an acceptance criterion - formal UAC "
                f"describes observable product behaviour (WHAT); move the internal check to Test Scenarios as an "
                f"implementation oracle, or restate the AC as an observable outcome"
            )
    return problems


def is_present(manifest):
    return isinstance(manifest, dict) and isinstance(manifest.get("dispositions"), list)


def summarize(manifest, plan_text=""):
    problems = []
    if is_present(manifest):
        problems += validate_dispositions(manifest["dispositions"])
    problems += check_plan_acceptance_criteria(plan_text)
    lines = [f"CoverageDispositionClassifier: {'CLEAN' if not problems else 'ISSUES'}"]
    for p in problems:
        lines.append(f"  {p}")
    return "\n".join(lines)
