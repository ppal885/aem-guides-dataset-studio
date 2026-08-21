"""Final Pre-UAC integration checks - make the plan CONSUME the reasoning outputs.

WHY THIS EXISTS
---------------
Prompts 1-5 build a BehaviorModel, coverage hypotheses, directed retrieval,
verdicts, and a coverage gate in the manifest. This module enforces that the FINAL
plan is actually derived from them rather than from raw chunks, by cross-checking
the manifest reasoning blocks against the plan BODY (which the manifest-only gates
cannot see):

- every UNRESOLVED verdict routed to OPEN_QUESTION must actually appear in the
  plan's Open Questions section (nothing hidden);
- an optional evidence_trace links each derived AC to a verified (CONFIRMED /
  INFERRED_HIGH_CONFIDENCE) hypothesis with evidence - so no AC traces to a
  REJECTED or UNRESOLVED hypothesis (formal UAC != complete test plan, and unproven
  behavior never becomes an AC).

Activates only when the plan carries reasoning blocks, so pre-architecture plans
are unaffected. Generic only. Stdlib only.
"""

import importlib.util
import re
from pathlib import Path


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_coverage_gate = _load("coverage_gate", "coverage_gate.py")

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*\s*$")
_AC_ID_RE = re.compile(r"\bAC-\d{2,}\b")


def _norm(s):
    return " ".join(str(s or "").lower().split())


def _section_text(plan_text, name):
    """Return the body text of a `**Name**` section, up to the next heading."""
    lines = plan_text.splitlines()
    out, capture = [], False
    for line in lines:
        m = _HEADING_RE.match(line.strip())
        if m:
            capture = (m.group(1).strip() == name)
            continue
        if capture:
            out.append(line)
    return "\n".join(out)


def _open_questions_index(manifest):
    idx = {}
    for oq in (manifest.get("open_questions", []) or []):
        if isinstance(oq, dict):
            idx[oq.get("id") or oq.get("ref") or ""] = oq.get("question", "")
    idx.pop("", None)
    return idx


def check_open_questions_surfaced(manifest, plan_text):
    """Every UNRESOLVED verdict must be written into the plan's Open Questions."""
    problems = []
    verifs = [v for v in (manifest.get("verifications", []) or []) if isinstance(v, dict)]
    unresolved = [v for v in verifs if v.get("verdict") == "UNRESOLVED"]
    if not unresolved:
        return problems
    oq_section = _norm(_section_text(plan_text, "Open Questions"))
    oq_index = _open_questions_index(manifest)
    for v in unresolved:
        ref = v.get("open_question_ref", "")
        question = oq_index.get(ref, "")
        if not question:
            problems.append(
                f"UNRESOLVED hypothesis '{v.get('hypothesis_id')}' references open question '{ref}' that has no "
                f"question text in the manifest open_questions - cannot confirm it was surfaced"
            )
            continue
        fragment = _norm(question)[:30]
        if len(fragment) >= 12 and fragment not in oq_section:
            problems.append(
                f"UNRESOLVED hypothesis '{v.get('hypothesis_id')}' (open question '{ref}') is not surfaced in the "
                f"plan's Open Questions section - an unresolved item must be exposed, never dropped"
            )
    return problems


def validate_evidence_trace(manifest, plan_text):
    """Validate the optional evidence_trace block against the plan and verifications."""
    problems = []
    trace = manifest.get("evidence_trace")
    if not isinstance(trace, list):
        return problems
    ac_ids_in_plan = set(_AC_ID_RE.findall(_section_text(plan_text, "Acceptance Criteria")))
    verifs = {v.get("hypothesis_id"): v for v in (manifest.get("verifications", []) or []) if isinstance(v, dict)}
    for i, t in enumerate(trace):
        if not isinstance(t, dict):
            problems.append(f"evidence_trace[{i}] must be an object")
            continue
        ac_id = t.get("ac_id", "")
        tag = f"evidence_trace '{ac_id or i}'"
        if not ac_id:
            problems.append(f"{tag}: missing ac_id")
        elif ac_id not in ac_ids_in_plan:
            problems.append(f"{tag}: ac_id is not present in the plan's Acceptance Criteria section")
        if not (t.get("evidence_ids") or []):
            problems.append(f"{tag}: an AC's evidence trace must cite evidence_ids")
        status = t.get("status", "")
        if status not in ("CONFIRMED", "INFERRED_HIGH_CONFIDENCE"):
            problems.append(
                f"{tag}: an AC may only trace to a CONFIRMED or INFERRED_HIGH_CONFIDENCE hypothesis, not '{status}'"
            )
        hid = t.get("hypothesis_id", "")
        if hid and hid in verifs:
            verdict = verifs[hid].get("verdict")
            if verdict in ("REJECTED", "UNRESOLVED"):
                problems.append(
                    f"{tag}: AC traces to hypothesis '{hid}' whose verdict is {verdict} - a "
                    f"{verdict} hypothesis must never become an Acceptance Criterion"
                )
    return problems


def check_integration(manifest, plan_text):
    """Return (failures, notes). Cross-checks the plan body against reasoning blocks."""
    failures, notes = [], []
    if not is_present(manifest):
        return failures, ["uac-integration check skipped (no reasoning blocks declared)"]

    # The coverage-gate verdict is owned/blocked by check_coverage_gate; here we only
    # surface it for context and add the plan-BODY cross-checks it cannot perform.
    verdict = _coverage_gate.evaluate(manifest)["semantic_gate"]
    notes.append(f"uac-integration: coverage gate is {verdict}")

    failures += [f"[uac-integration] {p}" for p in check_open_questions_surfaced(manifest, plan_text)]
    failures += [f"[uac-integration] {p}" for p in validate_evidence_trace(manifest, plan_text)]
    if not failures:
        notes.append("final plan consumes the reasoning outputs (open questions surfaced; evidence trace valid)")
    return failures, notes


def is_present(manifest):
    if not isinstance(manifest, dict):
        return False
    if isinstance(manifest.get("evidence_trace"), list) and manifest["evidence_trace"]:
        return True
    return _coverage_gate.is_present(manifest)
