"""Pre-UAC Quality Critic (Prompt 17) - an independent, read-only critique of a
generated plan across every reasoning dimension, with a bounded repair pass.

WHY THIS EXISTS
---------------
After generation, a strong-QE critic should ask the obvious questions before the plan
ships. This critic does NOT rewrite the plan; it aggregates the signals from Prompts
8-16 (and the core gates) into a per-question verdict and an overall
PASS / NEEDS_REFINEMENT / FAIL. Only after the critique may the generator perform ONE
bounded repair pass - never an infinite self-review loop.

Generic only. Stdlib only.
"""

import importlib.util
import re
from pathlib import Path


def _load(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_relevance = _load("relevance_prioritizer", "relevance_prioritizer.py")
_disp = _load("disposition_classifier", "disposition_classifier.py")
_cross = _load("cross_surface_resolver", "cross_surface_resolver.py")
_equiv = _load("structural_equivalence_verifier", "structural_equivalence_verifier.py")
_state = _load("state_compatibility_explorer", "state_compatibility_explorer.py")
_oracle = _load("test_oracle_builder", "test_oracle_builder.py")
_integration = _load("uac_integration", "uac_integration.py")
_reducer = _load("scenario_reducer", "scenario_reducer.py")
_coverage = _load("coverage_hypotheses", "coverage_hypotheses.py")

MAX_REPAIR_PASSES = 1

CLEAN, CONCERN, MISSING = "CLEAN", "CONCERN", "MISSING"

# The eleven critic questions (ids -> prompt).
QUESTIONS = (
    ("only_the_noun", "Did we test only the noun mentioned in Jira?"),
    ("governing_semantic_deps", "Did we find governing semantic dependencies?"),
    ("prioritized_direct_first", "Did we prioritize direct dependencies before distant regressions?"),
    ("impl_detail_as_ac", "Did we confuse implementation details with AC?"),
    ("outputs_without_evidence", "Did we test outputs without evidence of shared impact?"),
    ("equivalence_unverified", "Did we assume structural equivalence without verification?"),
    ("lifecycle_covered", "Did we cover first-run vs persisted-state lifecycle?"),
    ("unresolved_exposed", "Did we expose unresolved product decisions?"),
    ("cartesian", "Did we generate Cartesian combinations?"),
    ("scenario_oracles", "Did every important scenario have a valid oracle?"),
    ("obvious_open_question", "Could a strong QE reviewer ask an obvious unanswered question?"),
)


def _section_empty(plan_text, name):
    lines, capture, body = (plan_text or "").splitlines(), False, []
    for line in lines:
        m = re.match(r"^\*\*(.+?)\*\*\s*$", line.strip())
        if m:
            capture = (m.group(1).strip() == name)
            continue
        if capture and line.strip():
            body.append(line.strip())
    joined = " ".join(body).lower()
    return (not body) or ("no open questions" in joined)


def critique(manifest, plan_text=""):
    manifest = manifest if isinstance(manifest, dict) else {}
    cov = manifest.get("coverage_hypotheses", []) or []
    verifs = manifest.get("verifications", []) or []
    dita = manifest.get("dita_semantics") or {}
    bm = manifest.get("behavior_model") or {}
    behaviour_matters = manifest.get("behaviour_matters", True) is not False
    q = {}

    relationship_block = manifest.get("construct_relationships") or {}
    relationship_edges = (
        relationship_block.get("edges", [])
        if isinstance(relationship_block, dict)
        else []
    )
    explored = bool(cov) or bool(dita.get("relations")) or bool(relationship_edges)
    q["only_the_noun"] = (CONCERN, "no dependency/coverage exploration recorded beyond the primary construct") \
        if behaviour_matters and not explored else (CLEAN, "")

    if dita.get("active"):
        q["governing_semantic_deps"] = (CLEAN, "") if dita.get("relations") else (CONCERN, "DITA semantics active but no governing relations explored")
    else:
        q["governing_semantic_deps"] = (CLEAN, "not a DITA-semantic ticket")

    blocked = _relevance.high_relevance_unresolved(cov, verifs) if cov else []
    q["prioritized_direct_first"] = (CONCERN, "a HIGH-relevance direct/one-hop dependency is unexplored while lower-value ones are done") if blocked else (CLEAN, "")

    disp_problems = _disp.check_plan_acceptance_criteria(plan_text)
    q["impl_detail_as_ac"] = (CONCERN, disp_problems[0]) if disp_problems else (CLEAN, "")

    if _cross.is_present(manifest):
        cp = _cross.validate_cross_surface(manifest["cross_surface"])
        q["outputs_without_evidence"] = (CONCERN, cp[0]) if cp else (CLEAN, "")
    elif _cross.multi_output_signal(manifest):
        q["outputs_without_evidence"] = (CONCERN, "multiple output surfaces in scope but none classified as REFERENCE_ORACLE vs evidence-backed REGRESSION_TARGET")
    else:
        q["outputs_without_evidence"] = (CLEAN, "")

    if _equiv.is_present(manifest):
        ep = _equiv.validate_structural_equivalence(manifest["structural_equivalence"])
        q["equivalence_unverified"] = (CONCERN, ep[0]) if ep else (CLEAN, "")
    else:
        q["equivalence_unverified"] = (CLEAN, "")

    if _state.is_active(manifest):
        if _state.is_present(manifest):
            sp = _state.validate_state_compatibility(manifest["state_compatibility"])
            q["lifecycle_covered"] = (CONCERN, sp[0]) if sp else (CLEAN, "")
        else:
            q["lifecycle_covered"] = (CONCERN, "state-lifecycle signals present but first-run vs persisted-state not explored")
    else:
        q["lifecycle_covered"] = (CLEAN, "")

    oq_problems = _integration.check_open_questions_surfaced(manifest, plan_text)
    q["unresolved_exposed"] = (MISSING, oq_problems[0]) if oq_problems else (CLEAN, "")

    cartesian = []
    if cov:
        _, collapsed = _coverage.collapse_hypotheses([_coverage.CoverageHypothesis.from_dict(h) for h in cov])
        if collapsed:
            cartesian.append("un-collapsed equivalent coverage candidates")
    if _reducer.is_present(manifest):
        if _reducer.validate_reduction(manifest["scenario_reduction"]):
            cartesian.append("scenario_reduction redundancy")
    q["cartesian"] = (CONCERN, "; ".join(cartesian)) if cartesian else (CLEAN, "")

    op = _oracle.check_plan_scenarios(plan_text)
    q["scenario_oracles"] = (CONCERN, op[0]) if op else (CLEAN, "")

    if (bm.get("unknowns")) and _section_empty(plan_text, "Open Questions"):
        q["obvious_open_question"] = (CONCERN, "the behavior model records unknowns but the plan's Open Questions section is empty")
    else:
        q["obvious_open_question"] = (CLEAN, "")

    verdicts = [v for v, _ in q.values()]
    if MISSING in verdicts:
        overall = "FAIL"
    elif CONCERN in verdicts:
        overall = "NEEDS_REFINEMENT"
    else:
        overall = "PASS"
    return {"verdict": overall, "questions": q}


def can_repair(repair_passes):
    """One bounded repair pass only - never an infinite self-review loop."""
    try:
        return int(repair_passes) < MAX_REPAIR_PASSES
    except (TypeError, ValueError):
        return True


def validate_repair_bound(manifest):
    problems = []
    critic = manifest.get("critic") if isinstance(manifest, dict) else None
    if isinstance(critic, dict) and "repair_passes" in critic:
        rp = critic["repair_passes"]
        if not isinstance(rp, int) or rp < 0:
            problems.append("critic.repair_passes must be a non-negative integer")
        elif rp > MAX_REPAIR_PASSES:
            problems.append(f"critic.repair_passes {rp} exceeds the bounded limit of {MAX_REPAIR_PASSES} - no infinite self-review loops")
    return problems


def summarize(manifest, plan_text=""):
    r = critique(manifest, plan_text)
    lines = [f"Pre-UAC Quality Critic: {r['verdict']}"]
    for qid, prompt in QUESTIONS:
        v, reason = r["questions"].get(qid, (CLEAN, ""))
        lines.append(f"  [{v}] {prompt}" + (f" -> {reason}" if reason else ""))
    return "\n".join(lines)
