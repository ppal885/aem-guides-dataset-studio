"""Proactive Native-PDF entry-point / surface / temp-files coverage gate.

WHY THIS EXISTS
---------------
On a FRESH Native PDF ticket (no reviewer comment yet), the recurring miss is the
set of Native-PDF dimensions a senior reviewer always asks about but that a first
draft omits (a human reviewer routinely has to add them):
  1. GENERATION ENTRY POINTS beyond a full-map publish - the single-topic
     "Download PDF" / Download-as-PDF path (a change can behave differently there).
  2. The MAP PREVIEW surface - the behaviour must also be checked in Preview, not
     only in the final PDF.
  3. The retained TEMPORARY FILES artifact (merged HTML) - the concrete place the
     sub-element markup/class is verifiable.

The reviewer-request gate only catches these AFTER a human comments. This gate is
PROACTIVE and fail-closed: when the ACs concern Native PDF output, each dimension
must be dispositioned (covered in an AC, raised as an Open Question, or explicitly
out of scope) before any reviewer sees the plan. Grounded in MP-004 (output-
generation entry points) and the temp-files artifact dimension.

Generic only. Standard library only.
"""
from __future__ import annotations

import re

# Activate when the acceptance criteria concern Native PDF output.
NATIVE_PDF_SIGNALS = ("native pdf", "native-pdf", "nativepdf")

# Each dimension: friendly label + the phrases that show it is addressed anywhere
# in the plan (an AC, an Open Question, a scope/regression note).
DIMENSIONS = {
    "entry_points": {
        "label": "generation entry points (single-topic Download PDF / Download-as-PDF, not only a full-map publish)",
        "terms": ("download pdf", "download as pdf", "download-as-pdf", "download-pdf",
                  "single topic", "single-topic", "per-topic pdf", "topic-level pdf",
                  "download the pdf", "generate pdf for a topic"),
    },
    "map_preview": {
        "label": "the Map Preview surface (behaviour in Preview, not only the final PDF)",
        "terms": ("map preview", "preview"),
    },
    "temp_files": {
        "label": "the retained temporary files / merged HTML artifact",
        "terms": ("temporary file", "temp file", "retain temporary", "retained temporary",
                  "merged html", "mergedhtml", "merged-html"),
    },
}


def _acceptance_block(plan_text: str) -> str:
    if not plan_text:
        return ""
    m = re.search(r"\*\*Acceptance Criteria\*\*(.*?)(?:\n\*\*|\Z)", plan_text, re.S)
    return m.group(1) if m else plan_text


def is_native_pdf_ticket(plan_text: str) -> bool:
    ac = _acceptance_block(plan_text).lower()
    return any(sig in ac for sig in NATIVE_PDF_SIGNALS)


def _dim_dispositioned(manifest, dim: str) -> bool:
    if not isinstance(manifest, dict):
        return False
    cov = manifest.get("native_pdf_coverage")
    if not isinstance(cov, dict):
        return False
    entry = cov.get(dim)
    if isinstance(entry, dict):
        return len(str(entry.get("reason", "")).strip()) >= 8 and bool(str(entry.get("disposition", "")).strip())
    return False


def _global_opt_out(manifest) -> str:
    if not isinstance(manifest, dict):
        return ""
    na = manifest.get("native_pdf_coverage_not_applicable")
    if isinstance(na, dict):
        return str(na.get("reason", "")).strip()
    if isinstance(na, str):
        return na.strip()
    return ""


def validate(manifest, plan_text: str = "") -> list[str]:
    if not is_native_pdf_ticket(plan_text):
        return []
    if len(_global_opt_out(manifest)) >= 12:
        return []
    text = (plan_text or "").lower()
    problems: list[str] = []
    for dim, spec in DIMENSIONS.items():
        if any(term in text for term in spec["terms"]):
            continue
        if _dim_dispositioned(manifest, dim):
            continue
        problems.append(
            f"Native PDF ticket: {spec['label']} is not addressed. Cover it in an AC, "
            f"raise it as an Open Question, or disposition it in native_pdf_coverage.{dim} "
            f"with a reason (or set native_pdf_coverage_not_applicable for the whole gate)."
        )
    return problems


def summarize(manifest, plan_text: str = "") -> str:
    if not is_native_pdf_ticket(plan_text):
        return "NativePdfCoverage: NOT_APPLICABLE (not a Native PDF ticket)"
    problems = validate(manifest, plan_text)
    lines = [f"NativePdfCoverage: {'CLEAN' if not problems else 'ISSUES'}"]
    lines.extend(f"  {p}" for p in problems)
    return "\n".join(lines)


def run_self_tests() -> None:
    nl = chr(10)
    non_npdf = nl.join(["**Acceptance Criteria**", "- AC-01: the panel shows the value.", ""])
    assert validate({}, non_npdf) == []

    base_ac = "- AC-01: a Native PDF output shows the metadata."
    missing = nl.join(["**Acceptance Criteria**", base_ac, "**Expected**", ""])
    probs = validate({}, missing)
    assert any("entry points" in p for p in probs), "entry points must be required"
    assert any("Map Preview" in p for p in probs), "map preview must be required"
    assert any("temporary files" in p for p in probs), "temp files must be required"

    covered = nl.join([
        "**Acceptance Criteria**",
        base_ac,
        "- AC-02: the same values render when a single topic is generated via Download PDF.",
        "- AC-03: the values also render in Map Preview.",
        "- AC-04: the retained temporary files carry the correct merged HTML for the sub-elements.",
        "", ])
    assert validate({}, covered) == [], "all three dimensions covered in ACs must pass"

    manifest_disp = {
        "native_pdf_coverage": {
            "entry_points": {"disposition": "OUT_OF_SCOPE", "reason": "The change is in the shared render path; download-pdf uses the same path, retested under regression."},
            "map_preview": {"disposition": "OPEN_QUESTION", "reason": "Preview parity is an unresolved product decision, raised as OQ-02."},
            "temp_files": {"disposition": "COVERED_BY_AC", "reason": "Covered by the merged-HTML class assertion in AC-05."},
        }
    }
    assert validate(manifest_disp, missing) == [], "per-dimension manifest dispositions must pass"

    assert validate({"native_pdf_coverage_not_applicable": {"reason": "This Native PDF ticket is a pure backend metadata-assembly change with no output-surface behaviour."}}, missing) == [], "global opt-out with a concrete reason must pass"
    print("native_pdf_coverage self-tests: PASS")


if __name__ == "__main__":
    run_self_tests()
