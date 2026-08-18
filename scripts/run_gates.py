"""Single mandatory gate for a test plan.

One command, one green/red result. It exists so a partial run cannot pass by
simply not invoking a check: the evidence manifest is REQUIRED, and the manifest
plus the combined plan+appendix are audited together.

It runs, in order:
  1. Manifest presence + completeness (issue, attachments, rag_probes,
     indexed_history_run must all be declared).
  2. Structural validation of the eleven-section bullet-only body
     (validate_test_plan.py).
  3. Evidence audit of the combined plan+appendix deliverable and the manifest
     (verify_evidence.py): source paths on disk, cited line numbers in range,
     attachments downloaded + attested, >=3 RAG probes when behaviour matters,
     and fenced code evidence present when anything is Covered / Partially covered.
  4. The script self-tests (protect the gates from silent regression).

Usage:
  python scripts/run_gates.py --plan <body.md> --combined <plan+appendix.md> --manifest <manifest.json>

Exit 0 only when everything passes; any failure prints FAIL lines and exits 1.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")
explorer_mod = _load("semantic_relationship_explorer", "semantic_relationship_explorer.py")
audit_mod = _load("anti_hardcoding_audit", "anti_hardcoding_audit.py")
behavior_mod = _load("behavior_model", "behavior_model.py")
coverage_mod = _load("coverage_hypotheses", "coverage_hypotheses.py")
mq_mod = _load("missing_questions", "missing_questions.py")
verifier_mod = _load("hypothesis_verifier", "hypothesis_verifier.py")
coverage_gate_mod = _load("coverage_gate", "coverage_gate.py")
integration_mod = _load("uac_integration", "uac_integration.py")
disposition_mod = _load("disposition_classifier", "disposition_classifier.py")
oracle_mod = _load("test_oracle_builder", "test_oracle_builder.py")
state_compat_mod = _load("state_compatibility_explorer", "state_compatibility_explorer.py")

REQUIRED_MANIFEST_KEYS = ("issue", "attachments", "rag_probes", "indexed_history_run", "clones")


def check_reasoning_required(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Make the reasoning pipeline MANDATORY for behavioral tickets.

    When `behaviour_matters` is not explicitly false, a structured `behavior_model`
    block is required (the plan must model "what is happening" before "what to test",
    rather than going Jira -> RAG -> UAC). When coverage hypotheses are declared,
    every one must be verified (a `verifications` block is required). Pure internal
    code-bug tickets opt out with `behaviour_matters: false` (with a reason), the
    same escape used for RAG. This is the policy flip that turns the opt-in
    architecture into an enforced pipeline.
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if data.get("behaviour_matters", True) is False:
        return [], ["reasoning pipeline not required (behaviour_matters is false)"]
    failures = []
    if not behavior_mod.is_present(data):
        failures.append(
            "[reasoning-required] a behavior_model block is mandatory when behaviour_matters is true - model the "
            "trigger/operations/state/consumers (unknowns allowed) before writing coverage; set behaviour_matters "
            "false with a reason only for a pure internal code bug with no product-visible contract"
        )
    if coverage_mod.is_present(data) and data.get("coverage_hypotheses") and not verifier_mod.is_present(data):
        failures.append(
            "[reasoning-required] coverage_hypotheses are declared but no verifications block exists - every "
            "candidate must be driven to a terminal verdict (CONFIRMED / INFERRED_HIGH_CONFIDENCE / REJECTED / "
            "UNRESOLVED) before the plan is delivered"
        )
    return failures, ["reasoning pipeline requirements satisfied"] if not failures else []


def check_coverage_gate(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Run the generalized SemanticCoverageGate when the plan participates.

    FAIL is blocking (a material hypothesis is UNRESOLVED but hidden). NEEDS_REVIEW
    is a prominent non-blocking note (the plan may be produced but must flag the
    missing exploration - per the integration contract). Backward-compatible:
    plans without any reasoning block do not activate this gate.
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not coverage_gate_mod.is_present(data):
        return [], ["semantic coverage gate skipped (no reasoning blocks declared)"]
    result = coverage_gate_mod.evaluate(data)
    verdict = result["semantic_gate"]
    notes = [f"semantic coverage gate: {verdict}"]
    for rr in result["review_reasons"]:
        notes.append(f"REVIEW {rr}")
    if verdict == "FAIL":
        return [f"[coverage-gate] {b}" for b in result["blocking_reasons"]], notes
    return [], notes


def check_verifications(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest `verifications` block when present.

    Backward-compatible: absent block is not a failure. When present, every
    coverage hypothesis must reach a terminal verdict and every verdict must be
    justified and routed to an allowed disposition (UNRESOLVED->OPEN_QUESTION only,
    REJECTED excluded from ACs, CONFIRMED not resting on similarity/test alone).
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not verifier_mod.is_present(data):
        return [], ["hypothesis-verification check skipped (no verifications block declared)"]
    failures = [f"[verify-hyp] {p}" for p in verifier_mod.verify_all(
        data.get("coverage_hypotheses", []), data.get("verifications", []))]
    return failures, ["hypothesis verifications validated"] if not failures else []


def check_retrieval(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest missing_questions + evidence_lifecycle blocks when present.

    Backward-compatible: absent blocks are not a failure. When present, enforces the
    MissingQuestion schema, the evidence lifecycle, and the directed-second-pass
    discipline (material question -> a genuinely new second retrieval; no loops).
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not mq_mod.is_present(data):
        return [], ["retrieval-discipline check skipped (no missing_questions/evidence_lifecycle block)"]
    failures = [f"[retrieval] {p}" for p in mq_mod.check_retrieval_discipline(
        data.get("missing_questions", []), data.get("evidence_lifecycle", []))]
    return failures, ["retrieval discipline validated"] if not failures else []


def check_coverage_hypotheses(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest `coverage_hypotheses` block when present.

    Backward-compatible: absent block is not a failure. When present, every
    hypothesis must be evidence-justified (technical_basis) with a known dimension
    and status, and the set must already be collapsed (no Cartesian explosion).
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    if not coverage_mod.is_present(data):
        return [], ["coverage-hypotheses check skipped (no coverage_hypotheses block declared)"]
    failures = [f"[coverage] {p}" for p in coverage_mod.validate_coverage_block(data["coverage_hypotheses"])]
    return failures, ["coverage hypotheses validated"] if not failures else []


def check_behavior_model(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Validate the manifest `behavior_model` block when present.

    Backward-compatible: a manifest without a `behavior_model` block is not a
    failure (the structured model is being adopted incrementally). When present,
    it must be structurally valid, evidence-anchored, and state-lifecycle complete.
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []  # manifest-completeness check already reports this
    if not behavior_mod.is_present(data):
        return [], ["behavior model check skipped (no behavior_model block declared)"]
    failures = [f"[behavior-model] {p}" for p in behavior_mod.validate_behavior_model(data["behavior_model"])]
    return failures, ["behavior model validated"] if not failures else []


def check_semantic_coverage(manifest_path: str | None) -> tuple[list[str], list[str]]:
    """Run the Semantic Coverage Gate when the manifest declares DITA semantics.

    A skipped gate (no dita_semantics / active:false) is not a failure — most
    tickets are not DITA-semantic. When active, every applicable dimension must
    end COVERED / INVESTIGATED_AND_REJECTED / UNRESOLVED_AND_EXPOSED.
    """
    if not manifest_path or not Path(manifest_path).is_file():
        return [], []
    try:
        data = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []  # manifest-completeness check already reports this
    semantics = data.get("dita_semantics")
    if not isinstance(semantics, dict) or not semantics.get("active"):
        return [], ["semantic coverage gate skipped (no active DITA semantics declared)"]
    overall, dims, failures = explorer_mod.evaluate_semantic_gate(semantics)
    notes = [f"semantic coverage gate: {overall}"]
    return failures, notes


def check_manifest_completeness(path: str | None) -> list[str]:
    if not path:
        return ["evidence manifest is required but was not supplied (--manifest)"]
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"evidence manifest missing or invalid JSON: {exc}"]
    failures: list[str] = []
    for key in REQUIRED_MANIFEST_KEYS:
        if key not in data:
            failures.append(
                f"manifest is missing required key '{key}' - every plan must declare "
                f"attachments, rag_probes, and indexed_history_run even if empty/false with a reason"
            )
    if "indexed_history_run" in data and not data["indexed_history_run"]:
        failures.append(
            "indexed_history_run must be truthy (record that the jira_qa history was queried) or a reason string"
        )
    clones = data.get("clones")
    if isinstance(clones, list):
        for entry in clones:
            ident = entry.get("path", "?")
            synced_with_sha = bool(entry.get("synced")) and bool(entry.get("sha"))
            provisional = bool(entry.get("provisional")) and bool(entry.get("note"))
            if not (synced_with_sha or provisional):
                failures.append(
                    f"clone {ident}: must be either synced with a captured sha, or provisional:true with a note "
                    f"explaining the SHA was not captured - a clone cannot be cited as current evidence unproven"
                )
    elif clones is not None:
        failures.append("manifest 'clones' must be a list")
    return failures


def run(plan_path: str, combined_path: str, manifest_path: str | None, jira_keys_path: str | None,
        skip_self_tests: bool) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []

    failures += [f"[manifest] {f}" for f in check_manifest_completeness(manifest_path)]

    body = Path(plan_path).read_text(encoding="utf-8")
    failures += [f"[validate] {e}" for e in validate_mod.validate(body)]

    combined = Path(combined_path).read_text(encoding="utf-8")
    jira_keys = verify_mod._load_manifest(jira_keys_path)
    # Pass the manifest's clone roots so git-ref citations (main:<path>, etc.) are
    # disk-checked against the actual repos instead of being trusted blindly.
    git_ref_roots: list[str] = []
    if manifest_path and Path(manifest_path).is_file():
        try:
            _mdata = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            git_ref_roots = [c.get("path") for c in (_mdata.get("clones") or []) if isinstance(c, dict) and c.get("path")]
        except (OSError, json.JSONDecodeError):
            git_ref_roots = []
    v_fail, v_notes = verify_mod.verify(combined, jira_keys, git_ref_roots=git_ref_roots)
    failures += [f"[verify] {f}" for f in v_fail]
    notes += v_notes
    if manifest_path and Path(manifest_path).is_file():
        a_fail, a_notes = verify_mod.verify_attachments(manifest_path)
        failures += [f"[verify] {f}" for f in a_fail]
        notes += a_notes

    # Anti-hardcoding audit of the skill's own scripts/prompts — protects against a
    # future regression that bakes in an `if navtitle: test_locktitle()` rule.
    skill_root = Path(__file__).resolve().parent.parent
    hc_fail, hc_notes = audit_mod.audit_paths([skill_root])
    failures += [f"[anti-hardcoding] {f}" for f in hc_fail]
    notes += hc_notes

    # Mandatory reasoning pipeline for behavioral tickets (policy flip to READY).
    rq_fail, rq_notes = check_reasoning_required(manifest_path)
    failures += rq_fail
    notes += rq_notes

    # BehaviorModel validation (only when the manifest declares a behavior_model block).
    bm_fail, bm_notes = check_behavior_model(manifest_path)
    failures += bm_fail
    notes += bm_notes

    # CoverageHypotheses validation (only when the manifest declares the block).
    cv_fail, cv_notes = check_coverage_hypotheses(manifest_path)
    failures += cv_fail
    notes += cv_notes

    # MissingQuestions + directed-retrieval discipline (only when declared).
    rt_fail, rt_notes = check_retrieval(manifest_path)
    failures += rt_fail
    notes += rt_notes

    # HypothesisVerifier + hallucination control (only when declared).
    hv_fail, hv_notes = check_verifications(manifest_path)
    failures += hv_fail
    notes += hv_notes

    # Generalized SemanticCoverageGate over all activated dimensions (only when the
    # plan carries reasoning blocks). FAIL blocks; NEEDS_REVIEW is a loud note.
    cg_fail, cg_notes = check_coverage_gate(manifest_path)
    failures += cg_fail
    notes += cg_notes

    # Final Pre-UAC integration: cross-check the plan BODY against the reasoning
    # blocks (open questions surfaced; evidence trace valid). Only when participating.
    if manifest_path and Path(manifest_path).is_file():
        try:
            _idata = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _idata = {}
        i_fail, i_notes = integration_mod.check_integration(_idata, body)
        failures += i_fail
        notes += i_notes
        # CoverageDispositionClassifier: validate any dispositions block, and (for
        # reasoning-driven plans) flag implementation-level statements posing as ACs.
        if disposition_mod.is_present(_idata):
            failures += [f"[disposition] {p}" for p in disposition_mod.validate_dispositions(_idata["dispositions"])]
        if coverage_gate_mod.is_present(_idata):
            failures += [f"[disposition] {p}" for p in disposition_mod.check_plan_acceptance_criteria(body)]
        # TestOracleBuilder: validate any scenario_oracles block, and (for reasoning-
        # driven plans) require an observable product oracle on P0/P1 scenarios.
        if oracle_mod.is_present(_idata):
            failures += [f"[oracle] {p}" for p in oracle_mod.validate_scenario_oracles(_idata["scenario_oracles"])]
        if coverage_gate_mod.is_present(_idata):
            failures += [f"[oracle] {p}" for p in oracle_mod.check_plan_scenarios(body)]
        # ExistingStateCompatibilityExplorer: validate a state_compatibility block, and
        # (for reasoning-driven plans) require it when persisted/stale-state signals exist.
        if state_compat_mod.is_present(_idata):
            failures += [f"[state-compat] {p}" for p in state_compat_mod.validate_state_compatibility(_idata["state_compatibility"])]
        elif coverage_gate_mod.is_present(_idata) and state_compat_mod.is_active(_idata):
            failures.append(
                "[state-compat] state-lifecycle signals detected "
                f"({', '.join(state_compat_mod.detect_signals(_idata))}) but no state_compatibility exploration "
                "recorded - address CLEAN/FIXED/BUGGY-old state and whether old-state recovery is required"
            )

    # Semantic Coverage Gate (only when the manifest declares active DITA semantics).
    sc_fail, sc_notes = check_semantic_coverage(manifest_path)
    failures += sc_fail  # already tagged [semantic-gate]/[relation] by the evaluator
    notes += sc_notes

    if not skip_self_tests:
        try:
            self_tests = _load("test_skill_scripts", "test_skill_scripts.py")
            self_tests.test_validator()
            self_tests.test_verifier()
            self_tests.test_attachment_manifest()
            self_tests.test_behavior_model()
            self_tests.test_coverage_hypotheses()
            self_tests.test_missing_questions()
            self_tests.test_hypothesis_verifier()
            self_tests.test_coverage_gate()
            self_tests.test_uac_integration()
            self_tests.test_reasoning_required()
            self_tests.test_relevance_prioritizer()
            self_tests.test_disposition_classifier()
            self_tests.test_oracle_builder()
            self_tests.test_state_compatibility()
            notes.append("self-tests green")
        except AssertionError as exc:
            failures.append(f"[self-tests] {exc}")
        except Exception as exc:  # noqa: BLE001 - surface any self-test breakage as a gate failure
            failures.append(f"[self-tests] error: {exc}")

    return failures, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Single mandatory gate for an AEM Guides test plan.")
    parser.add_argument("--plan", required=True, help="the eleven-section bullet-only plan body")
    parser.add_argument("--combined", required=True, help="plan body + Appendix A (the delivered file)")
    parser.add_argument("--manifest", required=True, help="evidence manifest JSON")
    parser.add_argument("--jira-keys", dest="jira_keys", default=None)
    parser.add_argument("--skip-self-tests", action="store_true")
    args = parser.parse_args()

    failures, notes = run(args.plan, args.combined, args.manifest, args.jira_keys, args.skip_self_tests)

    for note in notes:
        print(f"NOTE: {note}")
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        print(f"\nGATE FAILED ({len(failures)} issue(s)) - do not deliver this plan as validated.")
        return 1
    print("\nGATE PASSED - manifest complete, structure valid, evidence verified"
          + ("." if args.skip_self_tests else ", self-tests green."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
