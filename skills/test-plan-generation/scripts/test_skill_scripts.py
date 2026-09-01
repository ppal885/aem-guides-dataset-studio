"""Self-tests for the test-plan-generation enforcement scripts.

Run: python scripts/test_skill_scripts.py
Exit 0 = all pass. No third-party deps; stdlib only.

These protect the validator and evidence auditor from silent regressions when
their rules are edited. Every rule that can fail a plan has a positive and a
negative fixture here.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_repo_root() -> Path:
    search_roots = [
        *Path(__file__).resolve().parents,
        Path.cwd().resolve(),
        *Path.cwd().resolve().parents,
    ]
    home = Path.home()
    try:
        home_children = [item for item in home.iterdir() if item.is_dir()]
    except OSError:
        home_children = []
    search_roots.extend(home_children)
    for container in home_children:
        try:
            search_roots.extend(
                item for item in container.iterdir() if item.is_dir()
            )
        except OSError:
            continue
    for candidate in dict.fromkeys(search_roots):
        if (
            (candidate / ".codex" / "skills" / "test-plan-generation").is_dir()
            and (candidate / ".claude" / "skills" / "test-plan-generation").is_dir()
            and (candidate / "skills" / "test-plan-generation").is_dir()
        ):
            return candidate
    raise RuntimeError("Could not locate the repository root for skill parity checks")


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")
authoring_state_mod = _load("authoring_state_contract", "authoring_state_contract.py")
component_router_mod = _load("component_reference_router", "component_reference_router.py")
explorer_mod = _load("semantic_relationship_explorer", "semantic_relationship_explorer.py")
audit_mod = _load("anti_hardcoding_audit", "anti_hardcoding_audit.py")
production_hardcoding_mod = _load(
    "audit_production_hardcoding", "audit_production_hardcoding.py"
)
behavior_mod = _load("behavior_model", "behavior_model.py")
coverage_mod = _load("coverage_hypotheses", "coverage_hypotheses.py")
mq_mod = _load("missing_questions", "missing_questions.py")
verifier_mod = _load("hypothesis_verifier", "hypothesis_verifier.py")
coverage_gate_mod = _load("coverage_gate", "coverage_gate.py")
integration_mod = _load("uac_integration", "uac_integration.py")
relevance_mod = _load("relevance_prioritizer", "relevance_prioritizer.py")
disposition_mod = _load("disposition_classifier", "disposition_classifier.py")
oracle_mod = _load("test_oracle_builder", "test_oracle_builder.py")
state_compat_mod = _load("state_compatibility_explorer", "state_compatibility_explorer.py")
cross_surface_mod = _load("cross_surface_resolver", "cross_surface_resolver.py")
struct_equiv_mod = _load("structural_equivalence_verifier", "structural_equivalence_verifier.py")
scenario_reducer_mod = _load("scenario_reducer", "scenario_reducer.py")
authority_mod = _load("evidence_authority_resolver", "evidence_authority_resolver.py")
change_impact_mod = _load("change_impact_explorer", "change_impact_explorer.py")
critic_mod = _load("pre_uac_critic", "pre_uac_critic.py")
impl_grounding_mod = _load("implementation_grounding", "implementation_grounding.py")
cap_elig_mod = _load("capability_eligibility_explorer", "capability_eligibility_explorer.py")
scope_conflict_mod = _load("scope_conflict_resolver", "scope_conflict_resolver.py")
affected_surface_mod = _load("affected_surface_explorer", "affected_surface_explorer.py")
comment_claim_mod = _load("comment_claim_verifier", "comment_claim_verifier.py")
pr_supersession_mod = _load("pr_supersession_check", "pr_supersession_check.py")
concurrency_race_mod = _load("concurrency_race_explorer", "concurrency_race_explorer.py")
enumerated_coverage_mod = _load("enumerated_coverage", "enumerated_coverage.py")
source_requirement_fidelity_mod = _load(
    "source_requirement_fidelity", "source_requirement_fidelity.py"
)
ac_decidability_mod = _load("ac_decidability", "ac_decidability.py")
operational_contract_mod = _load("operational_contract", "operational_contract.py")
feature_class_mod = _load("feature_class_registry", "feature_class_registry.py")
relationship_traversal_mod = _load(
    "relationship_traversal", "relationship_traversal.py"
)
configuration_enumeration_mod = _load(
    "configuration_enumeration_scope", "configuration_enumeration_scope.py"
)
ui_surface_scope_mod = _load("ui_surface_scope", "ui_surface_scope.py")
role_provisioning_mod = _load("role_provisioning", "role_provisioning.py")
fluffyjaws_evidence_mod = _load("fluffyjaws_evidence", "fluffyjaws_evidence.py")
temporal_evidence_mod = _load("temporal_evidence", "temporal_evidence.py")
evidence_conflict_resolver_mod = _load("evidence_conflict_resolver", "evidence_conflict_resolver.py")
scope_applicability_mod = _load("scope_applicability", "scope_applicability.py")
ac_language_policy_mod = _load("ac_language_policy", "ac_language_policy.py")
publishing_scope_coverage_mod = _load("publishing_scope_coverage", "publishing_scope_coverage.py")
repro_dimension_matrix_mod = _load("repro_dimension_matrix", "repro_dimension_matrix.py")
acceptance_synthesizer_mod = _load("acceptance_synthesizer", "acceptance_synthesizer.py")
uac_linter_mod = _load("uac_linter", "uac_linter.py")
human_feedback_delta_mod = _load("human_feedback_delta", "human_feedback_delta.py")
terminal_states_mod = _load("terminal_states", "terminal_states.py")
ac_contract_mod = _load("ac_contract_readability", "ac_contract.py")
ac_readability_mod = _load("ac_readability_review", "ac_readability.py")
ac_presentation_mod = _load("ac_presentation", "ac_presentation.py")
contract_fact_mod = _load("contract_fact_extractor", "contract_fact_extractor.py")
contract_integrity_mod = _load("contract_integrity_gate", "contract_integrity_gate.py")
domain_router_mod = _load("issue_domain_router", "issue_domain_router.py")
publishing_scope_mod = _load("publishing_scope", "publishing_scope.py")
behavior_graph_mod = _load("behavior_graph", "behavior_graph.py")
semantic_closure_mod = _load("semantic_closure", "semantic_closure.py")
generated_output_mod = _load("generated_output_contract", "generated_output_contract.py")
content_identity_mod = _load("content_identity_contract", "content_identity_contract.py")
acceptance_promotion_mod = _load("acceptance_promotion", "acceptance_promotion.py")
behavioral_completeness_mod = _load("behavioral_completeness", "behavioral_completeness.py")


GOOD_PLAN = """**Understanding From Jira**
- Issue understood: a thing is broken with a visible symptom.
- Why it matters: Customer context resolved from Jira: not identified; it hurts customers in a concrete way.
- Requested outcome: the thing should stop being broken.
- Lifecycle understood as: Pre-Development UAC with no PR yet.
- Evidence boundary: Evidence mode: full; facts are from live Jira and a backend clone.
**Acceptance Criteria**
- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.
- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.
**Expected Behaviour**
- Unknown from current evidence.
**Scope From Git**
- Lifecycle stage is Pre-Development UAC and readiness target is UAC-ready.
**Code Touched**
- No code changes yet — development has not started.
**Lines Changed**
- Not applicable — development has not started.
**Test Scenarios**
- Test data to prepare: create map M.ditamap and topic t.dita under /content/dam/sandbox; property foo on jcr:content holds value bar; config gate baz defaults to true; oracle is the observable correct output.
- P0 [AC-01]: Action: do the first thing. Expected: observe the correct output.
- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.
**Known Jira Bugs / Past Similar Tickets**
- GUIDES-100 — Some bug. Similarity: strongest match — same failure shape of wrong output. Status: Closed. Resolution: Fixed. Affected version: not available in current evidence. Fix version: 2609. RCA: not available in current evidence. Test evidence: not available in current evidence. Impact: reuse its oracle.
- Search status: JQL by exact error text and workflow terms across the project.
**Regression Areas**
- Nearby reporting workflow that reads the same output should be re-run after the change to confirm it still resolves correctly and the fix does not regress the shared read path.
**Automation Coverage & Gaps**
- Main feature coverage: Partially covered - AC-01 has direct integration coverage while AC-02 is missing.
- AC-01: Covered by an existing API test at the integration layer.
- AC-02: Not covered. Gap recipe at the API layer: setup prior state, poll the async helper with its configured timeout, assert state retained, tag with the suite, and cleanup created assets.
**Open Questions**
- No open questions from current evidence
"""

PERFORMANCE_SIGNAL_CATEGORIES = (
    "data_volume_or_cardinality_growth",
    "concurrency_or_contention",
    "repetition_or_long_duration",
    "latency_timeout_or_throughput",
    "cpu_memory_gc_or_storage",
    "queue_backlog_or_external_dependency",
    "persistence_cleanup_or_stale_state",
)

NOT_REQUIRED_PERFORMANCE = {
    "schema_version": "aem-guides-performance-assessment-v1",
    "decision": "not_required",
    "risk_rating": "low",
    "signal_review": {
        category: {
            "status": "absent",
            "finding": "The reviewed Jira, product evidence, and historical evidence contain no signal for this risk category.",
            "evidence_refs": ["Jira description GUIDES-100"],
        }
        for category in PERFORMANCE_SIGNAL_CATEGORIES
    },
    "workload_model": {
        "operation": "Not applicable after reviewing the functional operation.",
        "cardinality": "Not applicable because no scale or cardinality risk was found.",
        "concurrency": "Not applicable because no concurrent execution risk was found.",
        "repetition": "Not applicable because no repeated-operation risk was found.",
        "duration": "Not applicable because no long-running workflow risk was found.",
    },
    "metrics": [],
    "oracle": {
        "status": "not_applicable",
        "source_ref": "Jira description GUIDES-100",
        "thresholds": [],
    },
    "test_types": [],
    "performance_ac_ids": [],
    "rationale": "No evidence-backed performance mechanism exists, so dedicated performance testing would add noise rather than risk coverage.",
}



def _replace(plan: str, old: str, new: str) -> str:
    assert old in plan, f"fixture anchor not found: {old!r}"
    return plan.replace(old, new)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    print(f"ok: {name}")


def test_validator() -> None:
    check("good plan passes", validate_mod.validate(GOOD_PLAN) == [])

    no_main_feature_verdict = _replace(
        GOOD_PLAN,
        "- Main feature coverage: Partially covered - AC-01 has direct integration coverage while AC-02 is missing.\n",
        "",
    )
    errs = validate_mod.validate(no_main_feature_verdict)
    check(
        "automation requires one main feature coverage verdict",
        any("Main feature coverage" in error for error in errs),
    )

    ac_without_source = _replace(
        GOOD_PLAN,
        " | Evidence: Jira UAC GUIDES-100.",
        "",
    )
    errs = validate_mod.validate(ac_without_source)
    check("acceptance criterion without source is rejected", any("machine-readable format" in e for e in errs))

    compact_source_line = _replace(
        GOOD_PLAN,
        "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
        "- AC-01\n  - Starting point: an input is available.\n  - Action: the system runs.\n  - Expected result: it produces the correct observable output.",
    )
    errs = validate_mod.validate(compact_source_line)
    check(
        "compact renderer AC syntax is rejected as a durable source record",
        any("machine-readable format" in error for error in errs),
    )

    paste_unsafe_cases = (
        ("`observable output`", "backticks/code spans"),
        ("~observable output~", "strikethrough"),
        ("**observable output**", "bold/italic markers"),
        ("*observable output*", "bold/italic markers"),
        ("[observable output](https://example.com/result)", "Markdown link"),
    )
    for unsafe_outcome, expected_error in paste_unsafe_cases:
        unsafe_plan = _replace(
            GOOD_PLAN,
            "Then it produces the correct observable output | Evidence:",
            f"Then it produces the correct {unsafe_outcome} | Evidence:",
        )
        check(
            f"paste-unsafe AC markup is rejected: {expected_error}",
            any(expected_error in error for error in validate_mod.validate(unsafe_plan)),
        )

    long_then_plan = _replace(
        GOOD_PLAN,
        "Then it produces the correct observable output | Evidence:",
        "Then " + " ".join(f"result{index}" for index in range(46)) + " | Evidence:",
    )
    check(
        "grossly overlong Then clause is rejected with rewrite guidance",
        any(
            "grossly long" in error
            for error in ac_readability_mod.review_plan(long_then_plan)[0]
        ),
    )

    ac_with_only_graph_path = _replace(
        GOOD_PLAN,
        "Evidence: Jira UAC GUIDES-100.",
        "Evidence: graph path path-123.",
    )
    errs = validate_mod.validate(ac_with_only_graph_path)
    check("graph path alone cannot support P0 acceptance", any("never only a graph path" in e for e in errs))

    graph_path_with_jira_shaped_token = _replace(
        GOOD_PLAN,
        "Evidence: Jira UAC GUIDES-100.",
        "Evidence: path:GUIDES-100.",
    )
    errs = validate_mod.validate(graph_path_with_jira_shaped_token)
    check("graph path containing a Jira key is still rejected", any("never only a graph path" in e for e in errs))

    missing_strength = _replace(
        GOOD_PLAN,
        "Similarity: strongest match — same failure shape of wrong output.",
        "Similarity: same version purge area and cleanup theme.",
    )
    errs = validate_mod.validate(missing_strength)
    check("area-only similarity (no match strength) is rejected", any("match strength" in e for e in errs))

    ac_no_sphere = _replace(
        GOOD_PLAN,
        "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
        "- AC-01 [Proposed]: Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
    )
    errs = validate_mod.validate(ac_no_sphere)
    check("AC missing the sphere tag is rejected", any("machine-readable format" in e for e in errs))

    ac_invalid_sphere = _replace(
        GOOD_PLAN,
        "(Basic) Given an input",
        "(Security) Given an input",
    )
    errs = validate_mod.validate(ac_invalid_sphere)
    check("AC with an uncontrolled sphere is rejected", any("machine-readable format" in e for e in errs))

    ac_reordered = _replace(
        GOOD_PLAN,
        "Given a second input | When the system runs | Then it retains valid prior state",
        "When the system runs | Given a second input | Then it retains valid prior state",
    )
    errs = validate_mod.validate(ac_reordered)
    check("AC with reordered fields is rejected", any("machine-readable format" in e for e in errs))

    ac_embedded_label = _replace(
        GOOD_PLAN,
        "Given a second input | When the system runs",
        "Given a second input Then a hidden assertion | When the system runs",
    )
    errs = validate_mod.validate(ac_embedded_label)
    check("AC with an embedded field label is rejected", any("machine-readable format" in e for e in errs))

    ac_missing_period = _replace(
        GOOD_PLAN,
        "Evidence: Jira description GUIDES-100.",
        "Evidence: Jira description GUIDES-100",
    )
    errs = validate_mod.validate(ac_missing_period)
    check("AC without terminal punctuation is rejected", any("machine-readable format" in e for e in errs))

    ac_extra_field = _replace(
        GOOD_PLAN,
        " | Evidence: Jira description GUIDES-100.",
        " | Oracle: hidden | Evidence: Jira description GUIDES-100.",
    )
    errs = validate_mod.validate(ac_extra_field)
    check("AC with an extra field is rejected", any("machine-readable format" in e for e in errs))

    duplicate_id = _replace(GOOD_PLAN, "AC-02 [Proposed]", "AC-01 [Proposed]")
    errs = validate_mod.validate(duplicate_id)
    check("duplicate AC IDs are rejected", any("IDs must be unique" in e for e in errs))

    unquantified_performance = _replace(
        GOOD_PLAN,
        "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.",
        "- AC-02 [Proposed]: (Performance) Given a large dataset | When the system runs | Then it remains fast | Evidence: Jira comment GUIDES-100.",
    )
    errs = validate_mod.validate(unquantified_performance)
    check(
        "Performance AC without quantified workload is rejected",
        any("Performance Given must define a quantified workload" in e for e in errs),
    )
    check(
        "Performance AC without measurable oracle is rejected",
        any("Performance Then must define a measurable" in e for e in errs),
    )

    quantified_performance = _replace(
        GOOD_PLAN,
        "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.",
        "- AC-02 [Proposed]: (Performance) Given 10,000 topics with parent-map references | When the cleanup workflow runs | Then p95 cleanup latency remains at or below 2000 ms | Evidence: Jira comment GUIDES-100.",
    )
    quantified_performance = _replace(
        quantified_performance,
        "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
        "- P1 [AC-02]: Action: run the cleanup load benchmark for 10,000 topics. Expected: p95 latency is at or below 2000 ms.",
    )
    check(
        "quantified evidence-backed Performance AC passes",
        validate_mod.validate(quantified_performance) == [],
    )

    ac_no_scenario = _replace(
        GOOD_PLAN,
        "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
        "- P1 [AC-01]: Action: do a redundant first thing again. Expected: observe the first result.",
    )
    errs = validate_mod.validate(ac_no_scenario)
    check("AC with no scenario mapping is rejected", any("AC-02 has no Test Scenarios" in e for e in errs))

    ac_no_automation = _replace(
        GOOD_PLAN,
        "- AC-02: Not covered. Gap recipe at the API layer: setup prior state, poll the async helper with its configured timeout, assert state retained, tag with the suite, and cleanup created assets.",
        "- Note: nothing else to automate.",
    )
    errs = validate_mod.validate(ac_no_automation)
    check("AC with no automation verdict is rejected", any("AC-02 has no verdict" in e for e in errs))

    scenario_no_ac = _replace(
        GOOD_PLAN,
        "- P0 [AC-01]: Action: do the first thing. Expected: observe the correct output.",
        "- P0 Action: do the first thing. Expected: observe the correct output.",
    )
    errs = validate_mod.validate(scenario_no_ac)
    check("scenario without AC mapping is rejected", any("missing an AC mapping" in e for e in errs))

    no_test_data = _replace(
        GOOD_PLAN,
        "- Test data to prepare: create map M.ditamap and topic t.dita under /content/dam/sandbox; property foo on jcr:content holds value bar; config gate baz defaults to true; oracle is the observable correct output.\n",
        "",
    )
    errs = validate_mod.validate(no_test_data)
    check("Test Scenarios without a Test data to prepare bullet is rejected", any("Test data to prepare" in e for e in errs))

    no_customer_source = _replace(
        GOOD_PLAN,
        "- Why it matters: Customer context resolved from Jira: not identified; it hurts customers in a concrete way.",
        "- Why it matters: it hurts customers in a concrete way.",
    )
    errs = validate_mod.validate(no_customer_source)
    check("customer context source is required", any("Customer context resolved from Jira" in e for e in errs))

    no_action_expected = _replace(
        GOOD_PLAN,
        "- P0 [AC-01]: Action: do the first thing. Expected: observe the correct output.",
        "- P0 [AC-01]: do the first thing and observe the correct output.",
    )
    errs = validate_mod.validate(no_action_expected)
    check("scenario Action and Expected wording is required", any("Action:" in e and "Expected:" in e for e in errs))

    terse_regression = _replace(
        GOOD_PLAN,
        "- Nearby reporting workflow that reads the same output should be re-run after the change to confirm it still resolves correctly and the fix does not regress the shared read path.",
        "- Map Console reports.",
    )
    errs = validate_mod.validate(terse_regression)
    check("terse keyword-fragment Regression Areas bullet is rejected", any("too terse" in e for e in errs))

    oq_with_impact = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- OQ-01: Is the async path in scope? QA impact: if yes add a polling-oracle scenario, if no document the limitation and prove cleanup does not fire.",
    )
    check("open question stating QA impact passes", validate_mod.validate(oq_with_impact) == [])

    oq_no_impact = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- OQ-01: Is the fix synchronous or asynchronous on delete?",
    )
    errs = validate_mod.validate(oq_no_impact)
    check("open question without QA impact is rejected", any("Open Questions bullet must use" in e for e in errs))

    oq_duplicate = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- OQ-01: Is the async path in scope? QA impact: the answer changes async coverage.\n"
        "- OQ-01: Which timeout applies? QA impact: the answer changes the wait oracle.",
    )
    errs = validate_mod.validate(oq_duplicate)
    check("duplicate Open Question IDs are rejected", any("must be unique" in e for e in errs))

    oq_noncontiguous = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- OQ-02: Which timeout applies? QA impact: the answer changes the wait oracle.",
    )
    errs = validate_mod.validate(oq_noncontiguous)
    check(
        "non-contiguous Open Question IDs are rejected",
        any("contiguous and ordered starting at OQ-01" in e for e in errs),
    )

    no_questions_mixed = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- No open questions from current evidence\n"
        "- OQ-01: Which timeout applies? QA impact: the answer changes the wait oracle.",
    )
    errs = validate_mod.validate(no_questions_mixed)
    check(
        "no-open-questions declaration cannot coexist with a real question",
        any("cannot coexist" in e for e in errs),
    )

    stable_scenarios = _replace(
        GOOD_PLAN,
        "- P0 [AC-01]: Action: do the first thing. Expected: observe the correct output.\n"
        "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
        "- P0 [TS-01] [AC-01]: Action: do the first thing. Expected: observe the correct output.\n"
        "- P1 [TS-02] [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
    )
    check("stable contiguous Test Scenario IDs pass", validate_mod.validate(stable_scenarios) == [])

    duplicate_scenarios = stable_scenarios.replace("[TS-02]", "[TS-01]")
    errs = validate_mod.validate(duplicate_scenarios)
    check("duplicate Test Scenario IDs are rejected", any("must be unique" in e for e in errs))

    clone_no_sync = _replace(
        GOOD_PLAN,
        "- Lifecycle stage is Pre-Development UAC and readiness target is UAC-ready.",
        "- Backend clone C:/starling inspected for current implementation.",
    )
    errs = validate_mod.validate(clone_no_sync)
    check("Scope From Git citing a clone without sync/SHA state is rejected", any("sync/SHA state" in e for e in errs))

    clone_provisional = _replace(
        GOOD_PLAN,
        "- Lifecycle stage is Pre-Development UAC and readiness target is UAC-ready.",
        "- Backend clone C:/starling inspected; revision SHA was not captured this pass so claims are provisional.",
    )
    check("Scope From Git citing a clone with a provisional SHA acknowledgment passes", validate_mod.validate(clone_provisional) == [])

    unvetted_regression_key = _replace(
        GOOD_PLAN,
        "does not regress the shared read path.",
        "does not regress the shared read path. See GUIDES-777.",
    )
    errs = validate_mod.validate(unvetted_regression_key)
    check("Regression Areas citing a Jira key absent from Known Bugs is rejected", any("GUIDES-777" in e for e in errs))


def test_ac_readability() -> None:
    ac = ac_contract_mod
    review = ac_readability_mod

    def readability_plan(outcome: str, *, given: str = "a topic is open", evidence: str = "reviewer feedback") -> str:
        return (
            "**Acceptance Criteria**\n"
            f"- AC-01 [Proposed]: (Basic) Given {given} | When the author checks the result | "
            f"Then {outcome} | Evidence: {evidence}.\n"
            "**Expected Behaviour**\n- Known."
        )

    simple = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Basic) Given a DITA-OT publish returns a generation log | "
        "When the publish workflow completes | Then the logger records one generation-log payload | "
        "Evidence: Jira description GUIDES-44288."
    )
    check("short technical AC remains valid", simple is not None and ac.validate_ac_readability(simple) == [])

    technical_tokens = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Basic) Given largeFileTagCount is 100 for map.ditamap in v2.0 | "
        "When POST /bin/fmdita/import runs | Then the GUIDES-44288 fixture creates one DITA-OT output | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "technical identifiers remain readable tokens",
        technical_tokens is not None and ac.validate_ac_readability(technical_tokens) == [],
    )
    technical_projection = ac_presentation_mod.project_ac_for_people(
        technical_tokens,
        include_status=True,
        header_bullet=False,
    )
    check(
        "plain presentation preserves technical token text exactly",
        technical_projection
        == (
            "AC-01 [Proposed]\n"
            "- Starting point: largeFileTagCount is 100 for map.ditamap in v2.0.\n"
            "- Action: POST /bin/fmdita/import runs.\n"
            "- Expected result: the GUIDES-44288 fixture creates one DITA-OT output."
        ),
    )

    coupled_safety = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Negative) Given an API request has an invalid path | "
        "When the caller submits the request | Then the API returns HTTP 409 and writes no partial state | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "one coupled safety result remains allowed",
        coupled_safety is not None and ac.validate_ac_readability(coupled_safety) == [],
    )

    complex_phrase = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Negative) Given a publish job is active | "
        "When a failure occurs | Then in the event that metadata storage fails the logger records one payload | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "complex legal-style phrase is rejected with a simple replacement",
        complex_phrase is not None
        and any("use 'if' instead" in error for error in ac.validate_ac_readability(complex_phrase)),
    )

    stacked = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Integration) Given a map and a preset and a custom logger and a Splunk sink and an archive are configured | "
        "When the user publishes the map | Then the application log and custom log and Splunk each receive the payload | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "ordinary clause density is reviewed instead of hard-failed by the legacy contract",
        stacked is not None and ac.validate_ac_readability(stacked) == [],
    )

    double_negative = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Negative) Given a publish job has no generation log | "
        "When the job ends | Then the logger does not write an entry unless a payload exists | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "double-negative outcome is rejected",
        double_negative is not None
        and any("double negative" in error for error in ac.validate_ac_readability(double_negative)),
    )

    second_action = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Basic) Given a map is open | "
        "When the author selects a preset and then starts publishing | Then the publish job starts | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "When cannot hide a second action after and then",
        second_action is not None
        and any("second action" in error for error in ac.validate_ac_readability(second_action)),
    )

    ambiguous_choice = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Negative) Given a map and/or topic is selected | "
        "When publishing starts | Then one publish job starts | Evidence: Jira description GUIDES-44288."
    )
    check(
        "and/or is rejected in favor of an exact choice",
        ambiguous_choice is not None
        and any("and/or" in error for error in ac.validate_ac_readability(ambiguous_choice)),
    )

    semicolon = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Basic) Given a publish job succeeds | "
        "When the job ends | Then the output remains valid; the history remains unchanged | "
        "Evidence: Jira description GUIDES-44288."
    )
    check(
        "semicolon-separated outcomes are rejected",
        semicolon is not None
        and any("semicolon" in error for error in ac.validate_ac_readability(semicolon)),
    )

    cross_ac_reference = ac.parse_ac_line(
        "- AC-01 [Proposed]: (Basic) Given a custom attribute has no mapping | "
        "When the author opens the Right Panel | Then the label uses the AC-04 fallback | "
        "Evidence: human review."
    )
    check(
        "AC clauses cannot depend on another AC reference",
        cross_ac_reference is not None
        and any(
            "state the product outcome directly" in error
            for error in ac.validate_ac_readability(cross_ac_reference)
        ),
    )

    review_29 = readability_plan(" ".join(f"word{index}" for index in range(29)))
    check(
        "29-word outcome emits a loud readability review",
        not review.review_plan(review_29)[0]
        and any("too long" in note for note in review.review_plan(review_29)[1]),
    )
    three_sentences = readability_plan("First result appears. Second result remains. Third result is visible.")
    check(
        "three-sentence outcome emits review without hard failure",
        not review.review_plan(three_sentences)[0]
        and any("too long" in note for note in review.review_plan(three_sentences)[1]),
    )
    clause_heavy = readability_plan(
        "the label appears, and the value remains, while the panel stays open, but the view updates, and focus remains"
    )
    check(
        "clause-heavy outcome emits review without hard failure",
        not review.review_plan(clause_heavy)[0]
        and any("too long" in note for note in review.review_plan(clause_heavy)[1]),
    )
    for token in (
        "Widget.render",
        "loadCurrentValue()",
        "C:/repo/Widget.java:42",
        "baseline-relative",
        "materialization",
        "p95",
        "heap",
        "GC",
        "suffix path",
        "render condition",
        "non-asset resource",
        "per-asset gating",
    ):
        plan = readability_plan(f"the named result appears with {token}")
        check(
            f"tester jargon emits review: {token}",
            any("Note for developer" in note for note in review.review_plan(plan)[1]),
        )
    evidence_only = readability_plan(
        "the named result appears", evidence="C:/repo/Widget.java:42 p95"
    )
    check(
        "code and jargon in Evidence do not trigger tester-text review",
        not any("Note for developer" in note for note in review.review_plan(evidence_only)[1]),
    )
    developer_note = readability_plan("the named result appears") + "\n- Note for developer: Widget.render uses p95."
    check(
        "developer note outside the AC is not treated as tester text",
        not any("Note for developer" in note for note in review.review_plan(developer_note)[1]),
    )
    vague = readability_plan("the label appears in the panel")
    check(
        "generic surface emits exact-screen review",
        any("name the exact screen" in note for note in review.review_plan(vague)[1]),
    )
    named = readability_plan(
        "the label appears in the panel", given="Full Tags View is open"
    )
    check(
        "declared exact screen suppresses vague-surface review",
        not any(
            "name the exact screen" in note
            for note in review.review_plan(
                named, named_surfaces=["Full Tags View"]
            )[1]
        ),
    )
    long_given = readability_plan(
        "the named result appears",
        given=" ".join(f"setup{index}" for index in range(29)),
    )
    check(
        "long Given clause emits the same first-read review as a long outcome",
        any("too long in Given" in note for note in review.review_plan(long_given)[1]),
    )
    recap_plan = (
        "**Acceptance Criteria**\n"
        "- AC-01 [Proposed]: (Basic) Given one file is selected | When the menu opens | "
        "Then View source is hidden for a non-DITA file after menu refresh | Evidence: Jira description.\n"
        "- AC-02 [Proposed]: (Basic) Given one file is selected | When the menu opens | "
        "Then Edit topics is hidden for a non-DITA file after selection changes | Evidence: Jira description.\n"
        "- AC-03 [Proposed]: (Basic) Given one file is selected | When the menu opens | "
        "Then View source and Edit topics are hidden for a non-DITA file | Evidence: Jira description.\n"
        "**Expected Behaviour**\n- Known."
    )
    check(
        "combined recap of two earlier outcomes is reviewed",
        any("summarizes outcomes" in note for note in review.review_plan(recap_plan)[1]),
    )


def test_verifier() -> None:
    check(
        "POSIX absolute source path is recognized",
        verify_mod.ABS_PATH_RE.search("/tmp/evidence/Real.java") is not None,
    )

    with tempfile.TemporaryDirectory() as tmp:
        real = Path(tmp) / "Real.java"
        real.write_text("line1\nline2\nline3\n", encoding="utf-8")
        real_posix = real.as_posix()  # drive-absolute with forward slashes

        good = f"**Code Touched**\n- Current implementation in {real_posix} (L2) defines a thing.\n"
        failures, _ = verify_mod.verify(good)
        check("existing file + valid line passes", failures == [])

        bad_line = f"**Code Touched**\n- Current implementation in {real_posix} (L99) defines a thing.\n"
        failures, _ = verify_mod.verify(bad_line)
        check("out-of-range line is failed", any("beyond end" in f for f in failures))

        # symbol-level check: a real file cited with an invented method is failed
        symfile = Path(tmp) / "Svc.java"
        symfile.write_text("class Svc {\n  void processParentMaps() {}\n}\n", encoding="utf-8")
        good_sym = f"- {symfile.as_posix()} exposes processParentMaps (L2).\n"
        failures, _ = verify_mod.verify(good_sym)
        check("real symbol next to a single file passes", failures == [])
        bad_sym = f"- {symfile.as_posix()} exposes invokeGhostMethod (L2).\n"
        failures, _ = verify_mod.verify(bad_sym)
        check("invented symbol next to a single file is failed", any("invokeGhostMethod" in f for f in failures))

        missing = f"**Code Touched**\n- Cited {Path(tmp).as_posix()}/Ghost.java as evidence.\n"
        failures, _ = verify_mod.verify(missing)
        check("missing source file is failed", any("does not exist" in f for f in failures))

        # unverifiable-by-design paths must NOT fail
        skip = "- Runtime path /var/dxml/btree and repo root C:/api automation/dxml-it-tests and file tests/foo/Bar.java.\n"
        failures, _ = verify_mod.verify(skip)
        check("runtime/relative/space-root paths are skipped, not failed", failures == [])

        # backtick-delimited path WITH SPACES is verified against disk
        spaced_dir = Path(tmp) / "api automation"
        spaced_dir.mkdir()
        spaced_file = spaced_dir / "Foo.java"
        spaced_file.write_text("x\n", encoding="utf-8")
        good_spaced = f"- Evidence in `{spaced_file.as_posix()}` proves the thing.\n"
        failures, _ = verify_mod.verify(good_spaced)
        check("backtick path with spaces is verified when it exists", failures == [])

        bad_spaced = f"- Evidence in `{(spaced_dir / 'Ghost.java').as_posix()}` proves nothing.\n"
        failures, _ = verify_mod.verify(bad_spaced)
        check("backtick path with spaces is failed when missing", any("does not exist" in f for f in failures))

        # jira manifest cross-check
        text = "- GUIDES-100 and GUIDES-999 are cited.\n"
        failures, _ = verify_mod.verify(text, jira_keys={"GUIDES-100"})
        check("invented Jira key is flagged against manifest", any("GUIDES-999" in f for f in failures))

        # covered/partial automation without code evidence must fail
        no_code = "**Automation Coverage & Gaps**\n- AC-01: Partially covered by an existing test.\n"
        failures, _ = verify_mod.verify(no_code)
        check("Partially covered without code evidence is failed", any("no fenced code evidence" in f for f in failures))

        with_code = "**Automation Coverage & Gaps**\n- AC-01: Partially covered.\n\n# Appendix A\n```python\ndef t(): pass\n```\n"
        failures, _ = verify_mod.verify(with_code)
        check("Partially covered with code evidence passes", failures == [])

        only_not_covered = "**Automation Coverage & Gaps**\n- AC-01: Not covered. Gap recipe here.\n"
        failures, _ = verify_mod.verify(only_not_covered)
        check("only Not-covered needs no code evidence", failures == [])


def test_attachment_manifest() -> None:
    import json

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        downloaded = tmp_path / "shot.png"
        downloaded.write_bytes(b"\x89PNG\r\n")

        def _manifest(entries) -> str:
            path = tmp_path / "manifest.json"
            path.write_text(json.dumps({"issue": "GUIDES-1", "attachments": entries}), encoding="utf-8")
            return str(path)

        good = _manifest([{"id": "1", "filename": "shot.png", "downloaded_to": downloaded.as_posix(), "analyzed": True}])
        failures, _ = verify_mod.verify_attachments(good)
        check("manifest with real download + analyzed passes", failures == [])

        missing = _manifest([{"id": "2", "filename": "ghost.png", "downloaded_to": (tmp_path / "ghost.png").as_posix(), "analyzed": True}])
        failures, _ = verify_mod.verify_attachments(missing)
        check("manifest with missing download is failed", any("not found on disk" in f for f in failures))

        not_analyzed = _manifest([{"id": "3", "filename": "shot.png", "downloaded_to": downloaded.as_posix(), "analyzed": False}])
        failures, _ = verify_mod.verify_attachments(not_analyzed)
        check("manifest entry not attested analyzed is failed", any("analyzed" in f for f in failures))

        def _manifest_rag(probes, behaviour_matters=True):
            path = tmp_path / "manifest_rag.json"
            payload = {"issue": "GUIDES-1", "attachments": [], "rag_probes": probes}
            if not behaviour_matters:
                payload["behaviour_matters"] = False
            path.write_text(json.dumps(payload), encoding="utf-8")
            return str(path)

        few = _manifest_rag(["only one probe"])
        failures, _ = verify_mod.verify_attachments(few)
        check("fewer than three RAG probes is failed when behaviour matters", any("RAG probe" in f for f in failures))

        enough = _manifest_rag(["q1", "q2", "q3"])
        failures, _ = verify_mod.verify_attachments(enough)
        check("three RAG probes passes", failures == [])

        na = _manifest_rag(["q1"], behaviour_matters=False)
        failures, _ = verify_mod.verify_attachments(na)
        check("one probe passes when behaviour_matters is false", failures == [])


def _full_preflight() -> dict:
    return {
        "mode": "full",
        "checked_at": "2026-08-08T15:30:00+05:30",
        "sources": {
            "product_rag": {
                "status": "available",
                "checked_via": "check_rag_status call and ask_dita_expert probes succeeded",
                "reason": "",
            },
            "jira_history": {
                "status": "available",
                "checked_via": "search_jira_history queries succeeded",
                "reason": "",
            },
            "live_jira": {
                "status": "available",
                "checked_via": "Jira issue fetch succeeded",
                "reason": "",
            },
            "git": {
                "status": "available",
                "checked_via": "local backend clone inspected after sync",
                "reason": "",
            },
            "figma": {
                "status": "not_applicable",
                "checked_via": "input inspection",
                "reason": "No design evidence is supplied or required.",
            },
        },
        "readiness_impact": "none",
        "readiness_impact_reason": "",
        "claim_restrictions": [],
    }


def _canonical_semantic_fixture() -> dict:
    closure_records = [
        {
            "closure_id": f"SC-{index:02d}",
            "entity_ref": "BGN-01",
            "dimension": dimension,
            "subject": "PRODUCT_CONTRACT",
            "applicability": "NOT_APPLICABLE",
            "status": "INVESTIGATED_AND_REJECTED",
            "reason": "No evidence makes this dimension applicable to the generic fixture.",
            "disposition_ref": "CD-03",
        }
        for index, dimension in enumerate(semantic_closure_mod.CLOSURE_DIMENSIONS, 1)
    ]
    non_acceptance_sources = ["BGN-01", *[item["closure_id"] for item in closure_records]]
    return {
        "issue": {
            "key": "GUIDES-100",
            "description": "The requested behavior produces correct observable output and retains valid prior state.",
        },
        "contract_facts": {
            "schema_version": "aem-guides-contract-facts-v1",
            "contract_state": "EVIDENCE_BACKED_PROPOSED_CONTRACT",
            "source_refs": ["Jira description GUIDES-100"],
            "facts": [
                {
                    "fact_id": "CF-01",
                    "category": "DIRECT_EXPECTED_BEHAVIOR",
                    "literal": "correct observable output",
                    "normalized": "correct observable output",
                    "source_ref": "Jira description GUIDES-100",
                    "subject": "PRODUCT_CONTRACT",
                    "authority": "JIRA_EXPECTED_BEHAVIOR",
                    "material": True,
                    "protected_terms": ["correct observable output"],
                    "integrity": "NORMALIZED_WITHOUT_SEMANTIC_CHANGE",
                    "destination": "ACCEPTANCE_CRITERION",
                    "ac_ref": "AC-01",
                },
                {
                    "fact_id": "CF-02",
                    "category": "COMPATIBILITY_REQUIREMENTS",
                    "literal": "retains valid prior state",
                    "normalized": "retains valid prior state",
                    "source_ref": "Jira description GUIDES-100",
                    "subject": "PRODUCT_CONTRACT",
                    "authority": "JIRA_EXPECTED_BEHAVIOR",
                    "material": True,
                    "protected_terms": ["retains valid prior state"],
                    "integrity": "PRESERVED",
                    "destination": "ACCEPTANCE_CRITERION",
                    "ac_ref": "AC-02",
                },
            ],
        },
        "issue_domains": {
            "schema_version": "aem-guides-issue-domains-v1",
            "primary_domain": "OTHER",
            "routes": [
                {
                    "domain": "OTHER",
                    "status": "ACTIVE",
                    "reason": "The generic fixture intentionally has no specialized domain.",
                    "evidence": ["Jira description GUIDES-100"],
                }
            ],
        },
        "behavior_model": {
            "trigger": ["the system runs"],
            "operations": ["produce the requested result"],
            "outputs": ["correct observable output"],
            "affected_state": ["valid prior state"],
            "confidence": 0.8,
        },
        "behavior_graph": {
            "schema_version": "aem-guides-behavior-graph-v1",
            "nodes": [
                {
                    "node_id": "BGN-01",
                    "kind": "PRODUCT_BEHAVIOR",
                    "label": "Requested observable behavior",
                    "material": True,
                    "provenance": ["Jira description GUIDES-100"],
                }
            ],
            "edges": [],
            "traversal_paths": [],
        },
        "semantic_closure": {
            "schema_version": "aem-guides-semantic-closure-v1",
            "records": closure_records,
        },
        "coverage_hypotheses": [],
        "missing_questions": [],
        "evidence_lifecycle": [],
        "verifications": [],
        "dispositions": [
            {
                "finding_id": "CD-01",
                "statement": "The requested observable output is proposed acceptance behavior.",
                "disposition": "PROPOSED_ACCEPTANCE_CONTRACT",
                "source_refs": ["CF-01"],
                "maps_to_ac": "AC-01",
            },
            {
                "finding_id": "CD-02",
                "statement": "Valid prior state remains intact.",
                "disposition": "PROPOSED_ACCEPTANCE_CONTRACT",
                "source_refs": ["CF-02"],
                "maps_to_ac": "AC-02",
            },
            {
                "finding_id": "CD-03",
                "statement": "The remaining generic closure dimensions were explicitly investigated.",
                "disposition": "INVESTIGATED_AND_REJECTED",
                "source_refs": non_acceptance_sources,
            },
        ],
        "acceptance_promotions": {
            "schema_version": "aem-guides-acceptance-promotions-v1",
            "records": [
                {
                    "promotion_id": "AP-01",
                    "candidate_ref": "CF-01",
                    "decision": "PROMOTED_PROPOSED",
                    "ac_ref": "AC-01",
                    "subject": "PRODUCT_CONTRACT",
                    "intended_behavior_authorities": ["JIRA_EXPECTED_BEHAVIOR"],
                    "scope_established": True,
                    "observable": True,
                    "testable": True,
                    "regression_only": False,
                    "implementation_only": False,
                    "conflicts_accepted_uac": False,
                    "unresolved_decision_refs": [],
                    "exact_value_fact_refs": [],
                    "disposition": "PROPOSED_ACCEPTANCE_CONTRACT",
                    "disposition_ref": "CD-01",
                },
                {
                    "promotion_id": "AP-02",
                    "candidate_ref": "CF-02",
                    "decision": "PROMOTED_PROPOSED",
                    "ac_ref": "AC-02",
                    "subject": "PRODUCT_CONTRACT",
                    "intended_behavior_authorities": ["JIRA_EXPECTED_BEHAVIOR"],
                    "scope_established": True,
                    "observable": True,
                    "testable": True,
                    "regression_only": False,
                    "implementation_only": False,
                    "conflicts_accepted_uac": False,
                    "unresolved_decision_refs": [],
                    "exact_value_fact_refs": [],
                    "disposition": "PROPOSED_ACCEPTANCE_CONTRACT",
                    "disposition_ref": "CD-02",
                },
            ],
        },
    }


def _publishing_scope_fixture() -> dict:
    stages = (
        "SOURCE_CONTENT", "MAP_ROOT_CONTEXT", "PRESET", "PROFILE_CONFIG",
        "FILTER_KEY_REFERENCE_RESOLUTION", "SEMANTIC_PROCESSING", "INTERMEDIATE_REPRESENTATION",
        "TRANSFORMER", "OUTPUT_BUILDER", "POST_GENERATION", "GENERATED_ARTIFACT",
        "PERSISTED_REPOSITORY_STATE", "ACTIVATION_PUBLICATION", "STATUS_HISTORY_LOGGING",
    )
    return {
        "schema_version": "aem-guides-publishing-scope-v1",
        "primary_publishing_mode": "AEM_SITES",
        "primary_preset_type": "AEM Sites",
        "enable_dita_ot_processing": "OFF",
        "aem_sites_implementation": "NATIVE",
        "deployment_mode": "CLOUD",
        "in_scope": ["AEM Sites output"],
        "out_of_scope": ["other output presets"],
        "shared_path_outputs": [],
        "shared_path_reason": "No shared output path was found.",
        "open_question_refs": [],
        "transformation_stages": [
            {
                "stage": stage,
                "applicability": "APPLICABLE",
                "reason": "The publishing path was inspected for this stage.",
            }
            for stage in stages
        ],
    }


def _generated_output_fixture() -> dict:
    return {
        "schema_version": "aem-guides-generated-output-contract-v2",
        "artifact_kind": "ARCHIVE",
        "entry_surface": "Output history",
        "delivery_in_scope": True,
        "download_surface": "Download archive action",
        "output_identity": "archive for the selected generation",
        "payload_inventory": [
            {"item_id": "GOI-01", "item": "generated intermediate content", "role": "PRIMARY_CONTENT", "disposition": "INCLUDED"},
            {"item_id": "GOI-02", "item": "generation log", "role": "DIAGNOSTIC", "disposition": "INCLUDED"},
        ],
        "structure": {
            "root": "single generation root",
            "hierarchy": "source hierarchy is preserved",
            "relative_path_policy": "paths remain relative to the generation root",
        },
        "oracles": [
            {
                "oracle_id": f"GO-{index:02d}",
                "oracle_type": oracle_type,
                "applicability": "APPLICABLE" if oracle_type in {"ARTIFACT_EXISTS", "CONTENT_CORRECT", "HIERARCHY_CORRECT", "OUTPUT_PATH_CORRECT", "NO_STALE_OUTPUT", "STATUS_MATCHES_REAL_OUTPUT", "DELIVERY_AVAILABLE"} else "NOT_APPLICABLE",
                "status": "COVERED" if oracle_type in {"ARTIFACT_EXISTS", "CONTENT_CORRECT", "HIERARCHY_CORRECT", "OUTPUT_PATH_CORRECT", "NO_STALE_OUTPUT", "STATUS_MATCHES_REAL_OUTPUT", "DELIVERY_AVAILABLE"} else "INVESTIGATED_AND_REJECTED",
                "expected": f"Explicit applicability decision for {oracle_type}.",
                "disposition_ref": "CD-GO",
            }
            for index, oracle_type in enumerate(generated_output_mod.ORACLE_TYPES, 1)
        ],
    }


def _content_identity_fixture() -> dict:
    return {
        "schema_version": "aem-guides-content-identity-contract-v1",
        "identity_source": "current repository asset identity",
        "selection_policy": "CURRENT",
        "fallback_policy": "NO_FALLBACK",
        "migration_behavior": "UNCHANGED",
        "lifecycle": [
            {
                "state_id": f"CI-{index:02d}",
                "operation": operation,
                "applicability": "APPLICABLE",
                "status": "COVERED",
                "expected_identity": "The current source asset identity is used.",
                "disposition_ref": "CD-CI",
            }
            for index, operation in enumerate(content_identity_mod.OPERATIONS, 1)
        ],
    }


def test_run_gates() -> None:
    import json

    run_gates = _load("run_gates", "run_gates.py")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.json"

        check("run_gates requires a manifest", run_gates.check_manifest_completeness(None) != [])

        path.write_text(json.dumps({"issue": "X"}), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates flags missing manifest keys", any("clones" in f for f in failures) and any("rag_probes" in f for f in failures))

        dual_source = {
            **_canonical_semantic_fixture(),
            "schema_version": "aem-guides-evidence-manifest-v3",
            "issue": {
                "key": "GUIDES-100",
                "description": "The requested behavior produces correct observable output and retains valid prior state.",
            },
            "attachments": [],
            "evidence_preflight": _full_preflight(),
            "rag_tool": "ask_dita_expert",
            "rag_probes": ["a", "b", "c"],
            "jira_history_tool": "search_jira_history",
            "jira_history_queries": [
                {"scope": "same_customer", "query": "failure shape", "component": "Schematron", "customer": "Acme"},
                {"scope": "cross_customer", "query": "failure shape", "component": "Schematron"},
            ],
            "indexed_history_run": True,
            "evidence_graph": {
                "requested": True,
                "tool": "query_test_evidence_graph",
                "status": "ready",
                "influence_mode": "shadow",
                "used_for_plan": False,
                "generation_id": "generation-1",
                "queries": [
                    {
                        "query": "same error signature and output mechanism",
                        "duration_ms": 42,
                        "cache_hit": False,
                        "path_ids": ["path-1"],
                        "leaf_citations": [
                            {
                                "leaf_id": "jira_chroma:GUIDES-100:chunk-1:sha256:abc",
                                "source_type": "jira_chroma",
                                "source_ref": "GUIDES-100",
                                "trust_tier": "historical_verified",
                            }
                        ],
                    }
                ],
            },
            "performance_assessment": NOT_REQUIRED_PERFORMANCE,
            "accepted_uac_present": False,
            "open_questions": [],
            "enumerated_requirements": {
                "schema_version": "aem-guides-enumerated-requirements-v1",
                "active": False,
                "reason": "The issue contains no reporter-enumerated requirement list.",
            },
            "operational_contract": {
                "schema_version": "aem-guides-operational-contract-v1",
                "active": False,
                "reason": "The fixture is a synchronous non-operational behavior.",
            },
        }

        legacy_v2 = json.loads(json.dumps(dual_source))
        legacy_v2["schema_version"] = "aem-guides-evidence-manifest-v2"
        for key in run_gates.SEMANTIC_MANIFEST_KEYS:
            legacy_v2.pop(key, None)
        path.write_text(json.dumps(legacy_v2), encoding="utf-8")
        legacy_failures = run_gates.check_manifest_completeness(str(path))
        check(
            "legacy v2 manifests do not retroactively require v3 semantic blocks",
            not any(
                "missing required key" in failure
                and any(key in failure for key in run_gates.SEMANTIC_MANIFEST_KEYS)
                for failure in legacy_failures
            ),
        )

        non_behavior = json.loads(json.dumps(dual_source))
        non_behavior["behaviour_matters"] = False
        non_behavior["behaviour_not_applicable_reason"] = "This is a pure internal bookkeeping check."
        for key in run_gates.SEMANTIC_MANIFEST_KEYS:
            non_behavior.pop(key, None)
        path.write_text(json.dumps(non_behavior), encoding="utf-8")
        non_behavior_failures = run_gates.check_manifest_completeness(str(path))
        check(
            "behaviour_matters false waives v3 semantic manifest keys",
            not any(
                "missing required key" in failure
                and any(key in failure for key in run_gates.SEMANTIC_MANIFEST_KEYS)
                for failure in non_behavior_failures
            ),
        )

        proposed_enumerated = json.loads(json.dumps(dual_source))
        proposed_enumerated["enumerated_requirements"] = {
            "schema_version": "aem-guides-enumerated-requirements-v1",
            "active": True,
            "source_ref": "pasted numbered requirements",
            "source_item_count": 1,
            "source_complete": True,
            "items": [
                {
                    "id": "REQ-01",
                    "source_index": 1,
                    "text": "Preserve the named source behavior.",
                    "disposition": "COVERED_BY_AC",
                    "ac_refs": ["AC-01"],
                }
            ],
        }
        path.write_text(json.dumps(proposed_enumerated), encoding="utf-8")
        check(
            "run_gates requires source fidelity for Proposed enumerated requirements",
            any(
                "source_requirement_ledger" in failure
                for failure in run_gates.check_manifest_completeness(str(path))
            ),
        )

        check(
            "principal performance assessment accepts an evidence-backed not-required decision",
            run_gates.performance_mod.validate_performance_assessment(dual_source) == [],
        )
        check(
            "not-required performance assessment aligns with a plan containing no Performance AC",
            run_gates.performance_mod.validate_plan_alignment(dual_source, GOOD_PLAN) == [],
        )

        invalid_performance = json.loads(json.dumps(NOT_REQUIRED_PERFORMANCE))
        invalid_performance["signal_review"].pop("persistence_cleanup_or_stale_state")
        invalid_manifest = {
            **dual_source,
            "performance_assessment": invalid_performance,
            "clones": [],
        }
        path.write_text(json.dumps(invalid_manifest), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "run_gates rejects an incomplete principal performance risk review",
            any("seven canonical risk categories" in failure for failure in failures),
        )

        malformed_performance = json.loads(json.dumps(NOT_REQUIRED_PERFORMANCE))
        malformed_performance["metrics"] = [{}]
        malformed_performance["performance_ac_ids"] = [{}]
        malformed_performance["oracle"]["thresholds"] = [{}]
        malformed_failures = run_gates.performance_mod.validate_performance_assessment(
            {"performance_assessment": malformed_performance}
        )
        check(
            "malformed performance arrays fail closed without crashing",
            any("unsupported value" in failure for failure in malformed_failures)
            and any("invalid AC ID" in failure for failure in malformed_failures),
        )

        required_performance = json.loads(json.dumps(NOT_REQUIRED_PERFORMANCE))
        required_performance.update(
            {
                "decision": "required",
                "risk_rating": "high",
                "workload_model": {
                    "operation": "Delete maps and clean parent-map references from affected topics.",
                    "cardinality": "10,000 topics with accumulated parent-map references.",
                    "concurrency": "5 concurrent map-deletion jobs.",
                    "repetition": "10 cleanup iterations per dataset.",
                    "duration": "30 minutes of sustained cleanup activity.",
                },
                "metrics": ["latency_p95", "timeout_rate", "heap_usage", "reference_cardinality"],
                "oracle": {
                    "status": "quantified",
                    "source_ref": "Jira comment GUIDES-100",
                    "thresholds": [
                        "p95 cleanup latency <= 2000 ms",
                        "timeout error rate = 0%",
                    ],
                },
                "test_types": ["load", "soak", "concurrency"],
                "performance_ac_ids": ["AC-02"],
                "rationale": "The Jira reports unbounded parent-map reference growth and timeout risk on a cleanup path, creating a high-impact scalability and resource-retention mechanism.",
            }
        )
        required_performance["signal_review"]["persistence_cleanup_or_stale_state"] = {
            "status": "present",
            "finding": "Deleted maps leave stale parent-map references that increase reference cardinality over time.",
            "evidence_refs": ["Jira description GUIDES-100"],
        }
        required_performance["signal_review"]["latency_timeout_or_throughput"] = {
            "status": "present",
            "finding": "The Jira reports timeout risk on the cleanup and report-read paths.",
            "evidence_refs": ["Jira comment GUIDES-100"],
        }
        required_manifest = {
            **dual_source,
            "performance_assessment": required_performance,
        }
        check(
            "required principal performance assessment passes schema validation",
            run_gates.performance_mod.validate_performance_assessment(required_manifest) == [],
        )
        check(
            "required performance decision fails when the plan omits a Performance AC",
            any(
                "must exactly match visible Performance ACs" in failure
                or "must include a Performance AC" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(required_manifest, GOOD_PLAN)
            ),
        )

        performance_plan = _replace(
            GOOD_PLAN,
            "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.",
            "- AC-02 [Proposed]: (Performance) Given 10,000 topics with parent-map references | When the cleanup workflow runs | Then p95 cleanup latency remains at or below 2000 ms | Evidence: Jira comment GUIDES-100.",
        )
        performance_plan = _replace(
            performance_plan,
            "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
            "- P1 [AC-02]: Action: run a 30-minute cleanup load and concurrency benchmark for 10,000 topics. Expected: p95 latency remains at or below 2000 ms with a 0% timeout error rate.",
        )
        check(
            "required performance decision aligns with a quantitative Performance AC",
            run_gates.performance_mod.validate_plan_alignment(required_manifest, performance_plan) == [],
        )
        check(
            "not-required decision rejects an invented Performance AC",
            any(
                "no Performance AC may be emitted" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(dual_source, performance_plan)
            ),
        )

        passive_historical_performance = _replace(
            GOOD_PLAN,
            "- Nearby reporting workflow that reads the same output should be re-run after the change to confirm it still resolves correctly and the fix does not regress the shared read path.",
            "- GUIDES-37915's enumdefs API performance path on the shared SubjectScheme title-resolution file must not regress.",
        )
        check(
            "manager feedback fails when historical performance Jira is only a passive regression",
            any(
                "historical performance Jira GUIDES-37915" in failure
                and "historical_contracts" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(
                    dual_source, passive_historical_performance
                )
            ),
        )

        current_performance_issue = {
            **dual_source,
            "issue": "GUIDES-37915",
        }
        check(
            "current performance Jira is not misclassified as historical evidence",
            not any(
                "historical performance Jira GUIDES-37915" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(
                    current_performance_issue, passive_historical_performance
                )
            ),
        )

        subjectscheme_performance = json.loads(json.dumps(NOT_REQUIRED_PERFORMANCE))
        subjectscheme_performance.update(
            {
                "decision": "required",
                "risk_rating": "high",
                "workload_model": {
                    "operation": "Call GET /bin/aem/guides/xmleditor/subjectscheme/enumdefs through the inspected SubjectScheme title-resolution path.",
                    "cardinality": "1 production-equivalent SubjectScheme dataset with the recorded enumdefs cardinality.",
                    "concurrency": "200 concurrent users.",
                    "repetition": "Run controlled before-fix and after-fix benchmark iterations against the same dataset.",
                    "duration": "Use the GUIDES-37915 approved benchmark duration for each controlled run.",
                },
                "metrics": [
                    "latency_p50",
                    "latency_p90",
                    "latency_p95",
                    "latency_p99",
                    "throughput",
                    "error_rate",
                    "timeout_rate",
                    "cpu_utilization",
                    "memory_usage",
                    "gc_pause",
                ],
                "oracle": {
                    "status": "quantified",
                    "source_ref": "GUIDES-37915 comments dated 2026-01-27 and 2026-01-28",
                    "thresholds": [
                        "p95 response time improves by at least 2x versus the recorded before-fix same-dataset baseline"
                    ],
                },
                "test_types": ["load", "concurrency", "benchmark"],
                "performance_ac_ids": ["AC-02"],
                "historical_contracts": [
                    {
                        "jira_key": "GUIDES-37915",
                        "relationship": "shared_execution_path",
                        "retained": True,
                        "mechanism": "The current change and historical ticket execute the SubjectScheme enumdefs title-resolution request path.",
                        "workload": "200 concurrent users against the same production-equivalent SubjectScheme dataset.",
                        "oracle": "At least 2x p95 response-time improvement versus the recorded before-fix same-dataset baseline.",
                        "evidence_refs": [
                            "GUIDES-37915 comments dated 2026-01-27 and 2026-01-28",
                            "Inspected SubjectScheme enumdefs title-resolution path",
                        ],
                    }
                ],
                "rationale": "The current SubjectScheme title-resolution change uses the same enumdefs execution path as GUIDES-37915, whose comments define a controlled same-dataset benchmark, approximately 200 concurrent users, percentile metrics, and a 2x response-time improvement oracle.",
            }
        )
        subjectscheme_performance["signal_review"]["concurrency_or_contention"] = {
            "status": "present",
            "finding": "GUIDES-37915 defines an expected workload of approximately 200 concurrent users.",
            "evidence_refs": ["GUIDES-37915 comment dated 2026-01-28"],
        }
        subjectscheme_performance["signal_review"]["latency_timeout_or_throughput"] = {
            "status": "present",
            "finding": "GUIDES-37915 records before/after response-time percentiles and a claimed 2x gain.",
            "evidence_refs": ["GUIDES-37915 comment dated 2026-01-27"],
        }
        subjectscheme_manifest = {
            **dual_source,
            "performance_assessment": subjectscheme_performance,
        }
        check(
            "same-path historical SubjectScheme performance contract passes schema validation",
            run_gates.performance_mod.validate_performance_assessment(subjectscheme_manifest) == [],
        )

        subjectscheme_plan = _replace(
            GOOD_PLAN,
            "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.",
            "- AC-02 [Proposed]: (Performance) Given 200 concurrent users against the same production-equivalent SubjectScheme dataset | When clients call GET /bin/aem/guides/xmleditor/subjectscheme/enumdefs through the inspected title-resolution path | Then p95 response time improves by at least 2x versus the recorded before-fix same-dataset baseline | Evidence: GUIDES-37915 comments dated 2026-01-27 and 2026-01-28.",
        )
        subjectscheme_plan = _replace(
            subjectscheme_plan,
            "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
            "- P1 [AC-02]: Action: run the same-dataset load and concurrency benchmark with 200 concurrent users and capture p50, p90, p95, p99, throughput, error rate, timeout rate, CPU, memory, and GC. Expected: p95 response time improves by at least 2x versus the recorded before-fix baseline without added errors or timeouts.",
        )
        check(
            "retained historical SubjectScheme contract emits a mapped Performance AC",
            run_gates.performance_mod.validate_plan_alignment(
                subjectscheme_manifest, subjectscheme_plan
            )
            == [],
        )

        subjectscheme_without_scenario = _replace(
            subjectscheme_plan,
            "- P1 [AC-02]: Action: run the same-dataset load and concurrency benchmark with 200 concurrent users and capture p50, p90, p95, p99, throughput, error rate, timeout rate, CPU, memory, and GC. Expected: p95 response time improves by at least 2x versus the recorded before-fix baseline without added errors or timeouts.",
            "- P1 [AC-01]: Action: rerun the functional path. Expected: the functional result remains correct.",
        )
        check(
            "retained historical performance AC cannot omit its mapped benchmark scenario",
            any(
                "must map to a Test Scenarios bullet" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(
                    subjectscheme_manifest, subjectscheme_without_scenario
                )
            ),
        )

        wrong_historical_citation = _replace(
            subjectscheme_plan,
            "Evidence: GUIDES-37915 comments dated 2026-01-27 and 2026-01-28.",
            "Evidence: Jira comment GUIDES-100.",
        )
        check(
            "retained historical performance Jira must be cited by the Performance AC",
            any(
                "GUIDES-37915 must be cited" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(
                    subjectscheme_manifest, wrong_historical_citation
                )
            ),
        )

        area_only_history = json.loads(json.dumps(subjectscheme_performance))
        area_only_history["historical_contracts"][0]["relationship"] = "area_only"
        check(
            "area-only historical performance cannot be retained",
            any(
                "cannot retain area-only" in failure
                for failure in run_gates.performance_mod.validate_performance_assessment(
                    {"performance_assessment": area_only_history}
                )
            ),
        )

        not_required_with_retained_history = json.loads(json.dumps(subjectscheme_performance))
        not_required_with_retained_history.update(
            {
                "decision": "not_required",
                "risk_rating": "low",
                "metrics": [],
                "test_types": [],
                "performance_ac_ids": [],
                "oracle": {
                    "status": "not_applicable",
                    "source_ref": "GUIDES-37915 comments dated 2026-01-27 and 2026-01-28",
                    "thresholds": [],
                },
            }
        )
        for category in PERFORMANCE_SIGNAL_CATEGORIES:
            not_required_with_retained_history["signal_review"][category]["status"] = "absent"
        check(
            "retained same-path history cannot be classified not-required",
            any(
                "requires decision=required" in failure
                for failure in run_gates.performance_mod.validate_performance_assessment(
                    {"performance_assessment": not_required_with_retained_history}
                )
            ),
        )

        conditional_performance = json.loads(json.dumps(NOT_REQUIRED_PERFORMANCE))
        conditional_performance.update(
            {
                "decision": "conditional",
                "risk_rating": "medium",
                "workload_model": {
                    "operation": "Run the affected cleanup workflow.",
                    "cardinality": "Production-equivalent topic cardinality is not yet supplied.",
                    "concurrency": "Expected concurrent job count is not yet supplied.",
                    "repetition": "Expected repeated-operation count is not yet supplied.",
                    "duration": "Required soak duration is not yet supplied.",
                },
                "oracle": {
                    "status": "unresolved",
                    "source_ref": "Jira description GUIDES-100",
                    "thresholds": [],
                },
                "rationale": "A plausible scale-sensitive cleanup mechanism exists, but the production workload and approved pass-fail threshold are missing, so an AC would otherwise hallucinate its oracle.",
            }
        )
        conditional_performance["signal_review"]["persistence_cleanup_or_stale_state"] = {
            "status": "unknown",
            "finding": "The available evidence does not quantify whether stale-state growth is material at production scale.",
            "evidence_refs": ["Jira description GUIDES-100"],
        }
        conditional_manifest = {
            **dual_source,
            "performance_assessment": conditional_performance,
        }
        check(
            "conditional principal performance assessment passes schema validation",
            run_gates.performance_mod.validate_performance_assessment(conditional_manifest) == [],
        )
        check(
            "conditional performance decision requires a QA-impact Open Question",
            any(
                "requires an Open Questions bullet" in failure
                for failure in run_gates.performance_mod.validate_plan_alignment(conditional_manifest, GOOD_PLAN)
            ),
        )
        conditional_plan = _replace(
            GOOD_PLAN,
            "- No open questions from current evidence",
            "- OQ-01: Confirm production topic cardinality, concurrent cleanup jobs, and the approved p95 latency SLA. QA impact: without these values no Performance AC can be emitted safely; with them QA can define the load, soak, and pass-fail oracle.",
        )
        check(
            "conditional performance decision aligns after its QA-impact question is visible",
            run_gates.performance_mod.validate_plan_alignment(conditional_manifest, conditional_plan) == [],
        )

        path.write_text(json.dumps({**dual_source, "clones": [{"path": "C:/x"}]}), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates flags a clone with no sha and not provisional", any("captured sha" in f for f in failures))

        wrong_tool = {**dual_source, "rag_tool": "search_jira_history", "clones": []}
        path.write_text(json.dumps(wrong_tool), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates rejects Jira search as product-doc RAG", any("rag_tool" in f for f in failures))

        one_scope = {**dual_source, "jira_history_queries": dual_source["jira_history_queries"][:1], "clones": []}
        path.write_text(json.dumps(one_scope), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates requires same and cross-customer Jira searches", any("both same_customer" in f for f in failures))

        invalid_component = {
            **dual_source,
            "jira_history_queries": [
                {**query, "component": "Platform and Integration"}
                for query in dual_source["jira_history_queries"]
            ],
            "clones": [],
        }
        path.write_text(json.dumps(invalid_component), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "run_gates rejects noncanonical Jira components",
            any("component must be one of" in failure for failure in failures),
        )

        paths_without_leaves = {
            **dual_source,
            "evidence_graph": {
                **dual_source["evidence_graph"],
                "queries": [{"query": "same mechanism", "duration_ms": 42, "cache_hit": False, "path_ids": ["path-1"], "leaf_citations": []}],
            },
            "clones": [],
        }
        path.write_text(json.dumps(paths_without_leaves), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "run_gates rejects graph paths without leaf citations",
            any("without underlying leaf citations" in failure for failure in failures),
        )

        shadow_influence = {
            **dual_source,
            "evidence_graph": {**dual_source["evidence_graph"], "used_for_plan": True},
            "clones": [],
        }
        path.write_text(json.dumps(shadow_influence), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "run_gates rejects shadow graph influence",
            any("must be false in shadow mode" in failure for failure in failures),
        )

        degraded_graph = {
            **dual_source,
            "evidence_graph": {
                "requested": True,
                "tool": "query_test_evidence_graph",
                "status": "degraded",
                "influence_mode": "shadow",
                "used_for_plan": False,
                "generation_id": None,
                "queries": [],
                "degraded_reason": "graph service unavailable; direct evidence retained",
            },
            "clones": [],
        }
        path.write_text(json.dumps(degraded_graph), encoding="utf-8")
        check(
            "run_gates allows explicit graph degraded mode",
            run_gates.check_manifest_completeness(str(path)) == [],
        )

        path.write_text(json.dumps({
            **dual_source,
            "clones": [{"path": "C:/x", "provisional": True, "note": "SHA not captured"}],
        }), encoding="utf-8")
        check("run_gates passes a complete manifest", run_gates.check_manifest_completeness(str(path)) == [])

        confirmed_without_authority = _replace(GOOD_PLAN, "[Proposed]", "[Confirmed]")
        check(
            "Confirmed ACs are forbidden when no accepted UAC exists",
            any(
                "every AC must remain [Proposed]" in problem
                for problem in run_gates.check_uac_plan_alignment(
                    {"accepted_uac_present": False}, confirmed_without_authority
                )
            ),
        )
        check(
            "manifest and visible Open Question IDs must match exactly",
            bool(
                run_gates.check_open_question_alignment(
                    {
                        "open_questions": [
                            {"id": "OQ-01", "question": "Which limit?", "qa_impact": "Changes the bound."}
                        ]
                    },
                    GOOD_PLAN,
                )
            ),
        )
        check(
            "combined artifact accepts only the exact plan plus Appendix A",
            run_gates.check_combined_binding(
                GOOD_PLAN, GOOD_PLAN.rstrip("\n") + "\n\n# Appendix A - Automation Evidence\n- Evidence.\n"
            ) == [],
        )
        check(
            "combined artifact rejects a mutated plan body",
            bool(run_gates.check_combined_binding(GOOD_PLAN, GOOD_PLAN.replace("a thing", "another thing"))),
        )

        compact_source = _replace(
            GOOD_PLAN,
            "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
            "- AC-01\n  - Starting point: an input is available.\n  - Action: the system runs.\n  - Expected result: it produces the correct observable output.",
        )
        plan_path = Path(tmp) / "plan.md"
        combined_path = Path(tmp) / "combined.md"
        plan_path.write_text(compact_source, encoding="utf-8")
        combined_path.write_text(compact_source, encoding="utf-8")
        full_manifest = {
            **dual_source,
            "clones": [{"path": "C:/x", "provisional": True, "note": "SHA not captured"}],
        }
        path.write_text(json.dumps(full_manifest), encoding="utf-8")
        end_to_end_failures, _ = run_gates.run(
            str(plan_path), str(combined_path), str(path), None, True
        )
        check(
            "full run gate rejects compact source AC syntax",
            any("[validate]" in problem and "machine-readable" in problem for problem in end_to_end_failures),
        )

        base = {
            **dual_source,
            "clones": [{"path": "C:/x", "provisional": True, "note": "SHA not captured"}],
            "accepted_uac_present": True,
        }
        path.write_text(json.dumps(base), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("accepted UAC requires fidelity audit", any("uac_fidelity" in failure for failure in failures))

        contract = {
            "schema_version": "aem-guides-uac-fidelity-v1",
            "source_ref": "Jira GUIDES-38333 final accepted UAC",
            "accepted_clause_ids": ["UAC-01", "UAC-02"],
            "out_of_scope_clause_ids": ["OOS-01"],
            "clause_to_ac": {"UAC-01": ["AC-01"], "UAC-02": ["AC-02"]},
            "confirmed_ac_to_clause": {"AC-01": ["UAC-01"], "AC-02": ["UAC-02"]},
            "proposed_ac_ids": ["AC-03"],
            "unresolved_clause_ids": [],
            "contradictions": [],
            "scope_expansions": [],
            "status": "pass",
        }
        base["uac_fidelity"] = contract
        path.write_text(json.dumps(base), encoding="utf-8")
        check("complete UAC fidelity audit passes", run_gates.check_manifest_completeness(str(path)) == [])

        contract["clause_to_ac"].pop("UAC-02")
        path.write_text(json.dumps(base), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "unmapped accepted UAC clause is rejected",
            any("UAC-02" in failure and "no Confirmed AC" in failure for failure in failures),
        )
        contract["clause_to_ac"]["UAC-02"] = ["AC-02"]

        contract["scope_expansions"] = ["DITA-OT output added despite OOS-01"]
        path.write_text(json.dumps(base), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("passing audit cannot hide scope expansion", any("scope expansions" in failure for failure in failures))

        contract["scope_expansions"] = []
        contract["unresolved_clause_ids"] = ["UAC-02"]
        contract["status"] = "blocked"
        path.write_text(json.dumps(base), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("blocked UAC fidelity audit cannot pass final gate", any("status is blocked" in failure for failure in failures))

        configured_only = json.loads(json.dumps(dual_source))
        configured_only["clones"] = []
        configured_only["evidence_preflight"]["sources"]["live_jira"]["checked_via"] = "Jira MCP configured"
        path.write_text(json.dumps(configured_only), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "preflight rejects configuration as proof of availability",
            any("configuration alone" in failure for failure in failures),
        )

        failed_but_available = json.loads(json.dumps(dual_source))
        failed_but_available["clones"] = []
        failed_but_available["evidence_preflight"]["sources"]["live_jira"]["checked_via"] = (
            "Jira issue fetch returned HTTP 403"
        )
        path.write_text(json.dumps(failed_but_available), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "preflight rejects a failed call labelled available",
            any("records a failed check" in failure for failure in failures),
        )

        naive_timestamp = json.loads(json.dumps(dual_source))
        naive_timestamp["clones"] = []
        naive_timestamp["evidence_preflight"]["checked_at"] = "2026-08-08T15:30:00"
        path.write_text(json.dumps(naive_timestamp), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "preflight rejects a timestamp without timezone",
            any("timezone-aware" in failure for failure in failures),
        )

        missing_reason = json.loads(json.dumps(dual_source))
        missing_reason["clones"] = []
        missing_reason["evidence_preflight"]["sources"]["figma"]["reason"] = ""
        path.write_text(json.dumps(missing_reason), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "preflight requires a not-applicable reason",
            any("figma.reason" in failure for failure in failures),
        )

        false_full = json.loads(json.dumps(dual_source))
        false_full["clones"] = []
        false_full["evidence_preflight"]["sources"]["live_jira"] = {
            "status": "unavailable",
            "checked_via": "Jira issue fetch returned HTTP 403",
            "reason": "The authenticated user lacks Browse permission.",
        }
        false_full["evidence_preflight"]["claim_restrictions"] = [
            "Current Jira status, resolution, and fix version remain unverified."
        ]
        path.write_text(json.dumps(false_full), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "preflight rejects full mode when a source is unavailable",
            any("mode must be 'degraded'" in failure for failure in failures),
        )

        degraded = json.loads(json.dumps(false_full))
        degraded["evidence_preflight"]["mode"] = "degraded"
        path.write_text(json.dumps(degraded), encoding="utf-8")
        check(
            "preflight accepts a complete degraded manifest",
            run_gates.check_manifest_completeness(str(path)) == [],
        )

        no_restrictions = json.loads(json.dumps(degraded))
        no_restrictions["evidence_preflight"]["claim_restrictions"] = []
        path.write_text(json.dumps(no_restrictions), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check(
            "degraded preflight requires claim restrictions",
            any("requires at least one claim restriction" in failure for failure in failures),
        )

        check(
            "full preflight aligns with the visible evidence boundary",
            run_gates._validate_preflight_plan_alignment(dual_source, GOOD_PLAN) == [],
        )
        failures = run_gates._validate_preflight_plan_alignment(degraded, GOOD_PLAN)
        check(
            "degraded preflight rejects a falsely full evidence boundary",
            any("Evidence mode: degraded" in failure for failure in failures),
        )
        degraded_plan = _replace(
            GOOD_PLAN,
            "- Evidence boundary: Evidence mode: full; facts are from live Jira and a backend clone.",
            "- Evidence boundary: Evidence mode: degraded; live Jira is unavailable after HTTP 403, so current status and resolution remain unverified; indexed Jira and backend clone evidence were used.",
        )
        check(
            "degraded preflight aligns when unavailable sources and limits are visible",
            run_gates._validate_preflight_plan_alignment(degraded, degraded_plan) == [],
        )

        unnamed_source_plan = _replace(
            GOOD_PLAN,
            "- Evidence boundary: Evidence mode: full; facts are from live Jira and a backend clone.",
            "- Evidence boundary: Evidence mode: degraded; one source is unavailable, so current status remains unverified.",
        )
        failures = run_gates._validate_preflight_plan_alignment(degraded, unnamed_source_plan)
        check(
            "degraded evidence boundary must name each unavailable source",
            any("live_jira" in failure for failure in failures),
        )

        git_degraded = json.loads(json.dumps(dual_source))
        git_degraded["evidence_preflight"]["mode"] = "degraded"
        git_degraded["evidence_preflight"]["sources"]["git"] = {
            "status": "unavailable",
            "checked_via": "local clone inspection failed",
            "reason": "No clone, diff, branch, commit, or GitHub connection was available.",
        }
        git_degraded["evidence_preflight"]["claim_restrictions"] = [
            "Current implementation, changed files, changed lines, and fix impact remain unverified."
        ]
        implementation_plan = _replace(
            GOOD_PLAN,
            "- Lifecycle understood as: Pre-Development UAC with no PR yet.",
            "- Lifecycle understood as: Implementation Review with a claimed fix.",
        )
        implementation_plan = _replace(
            implementation_plan,
            "- Evidence boundary: Evidence mode: full; facts are from live Jira and a backend clone.",
            "- Evidence boundary: Evidence mode: degraded; Git is unavailable, so implementation and changed-code claims remain unverified.",
        )
        failures = run_gates._validate_preflight_plan_alignment(git_degraded, implementation_plan)
        check(
            "implementation review cannot stay ready when Git is unavailable",
            any("draft_only or blocked" in failure for failure in failures),
        )

        git_degraded["evidence_preflight"]["readiness_impact"] = "draft_only"
        git_degraded["evidence_preflight"]["readiness_impact_reason"] = "Implementation evidence is unavailable."
        check(
            "implementation review accepts explicit degraded readiness",
            run_gates._validate_preflight_plan_alignment(git_degraded, implementation_plan) == [],
        )

        post_fix_plan = implementation_plan.replace(
            "Lifecycle understood as: Implementation Review with a claimed fix.",
            "Lifecycle understood as: Post-Fix Validation for candidate sign-off.",
        )
        failures = run_gates._validate_preflight_plan_alignment(git_degraded, post_fix_plan)
        check(
            "post-fix validation is blocked when Git fix evidence is unavailable",
            any("blocked readiness impact" in failure for failure in failures),
        )



def test_extract_acs() -> None:
    extract_mod = _load("extract_acs", "extract_acs.py")
    criteria, problems = extract_mod.extract(GOOD_PLAN)
    check("extract_acs parses both canonical ACs", len(criteria) == 2 and problems == [])
    check(
        "extract_acs maps stable automation fields",
        criteria[0]["schema_version"] == "aem-guides-ac-v1"
        and criteria[0]["id"] == "AC-01"
        and criteria[0]["sphere"] == "Basic"
        and criteria[0]["given"]
        and criteria[0]["when"]
        and criteria[0]["then"]
        and criteria[0]["evidence"] == "Jira UAC GUIDES-100",
    )
    malformed = _replace(
        GOOD_PLAN,
        "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state | Evidence: Jira description GUIDES-100.",
        "- AC-02 [Proposed]: the system retains prior state | Evidence: Jira description GUIDES-100.",
    )
    _, malformed_problems = extract_mod.extract(malformed)
    check("extract_acs fails closed on malformed input", any("unparseable" in p for p in malformed_problems))
    compact_source = _replace(
        GOOD_PLAN,
        "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
        "- AC-01\n  - Starting point: an input is available.\n  - Action: the system runs.\n  - Expected result: it produces the correct observable output.",
    )
    compact_criteria, compact_problems = extract_mod.extract(compact_source)
    check(
        "extract_acs emits no partial payload for compact display syntax",
        compact_criteria == [] and any("unparseable" in problem for problem in compact_problems),
    )
    paste_unsafe = _replace(
        GOOD_PLAN,
        "Then it produces the correct observable output | Evidence:",
        "Then it produces the correct `observable output` | Evidence:",
    )
    unsafe_criteria, unsafe_problems = extract_mod.extract(paste_unsafe)
    check(
        "extract_acs emits no payload for paste-unsafe AC markup",
        unsafe_criteria == [] and any("backticks/code spans" in problem for problem in unsafe_problems),
    )
    unreadable = _replace(
        GOOD_PLAN,
        "Then it produces the correct observable output | Evidence:",
        "Then the system produces the correct output for every selected map and every linked topic while also preserving all metadata, references, permissions, versions, history entries, unrelated files, audit records, workflow states, and generated assets across every supported output preset after processing completes | Evidence:",
    )
    unreadable_criteria, unreadable_problems = extract_mod.extract(unreadable)
    readability_failures, readability_notes = ac_readability_mod.review_plan(unreadable)
    check(
        "extract_acs leaves non-gross clarity review to the readability gate",
        len(unreadable_criteria) == 2
        and unreadable_problems == []
        and readability_failures == []
        and any("too long" in note for note in readability_notes),
    )


def test_compact_view() -> None:
    compact_mod = _load("render_compact_view", "render_compact_view.py")
    compact, problems = compact_mod.project(GOOD_PLAN)
    check("compact view renders without problems", problems == [])
    check(
        "compact view exposes exactly the requested headings",
        [line for line in compact.splitlines() if line.startswith("**")]
        == [
            "**Acceptance Criteria**",
            "**Test Scenarios**",
            "**Jira Tickets Worth Checking**",
            "**Automation Coverage**",
        ],
    )
    check(
        "compact view keeps analysis in the durable artifact",
        "What I understood from Jira" not in compact and "Why it matters" not in compact,
    )
    check(
        "compact view does not leak hidden record sections",
        all(
            hidden not in compact
            for hidden in (
                "Understanding From Jira",
                "Expected Behaviour",
                "Scope From Git",
                "Code Touched",
                "Lines Changed",
                "Automation Coverage & Gaps",
                "**Regression Areas**",
            )
        ),
    )
    check(
        "compact view keeps validated Test Scenarios",
        "**Test Scenarios**" in compact
        and "Test data to prepare:" in compact
        and "P0 [AC-01]" in compact
        and "P3 [Regression]" in compact
        and "Action:" in compact
        and "Expected:" in compact,
    )
    acceptance_block = compact.split("**Test Scenarios**", 1)[0]
    check(
        "compact ACs use three simple lines and hide internal record labels",
        (
            "- AC-01\n"
            "  - Starting point: an input.\n"
            "  - Action: the system runs.\n"
            "  - Expected result: it produces the correct observable output."
        )
        in acceptance_block
        and "Given " not in acceptance_block
        and "When " not in acceptance_block
        and "Then " not in acceptance_block
        and " | " not in acceptance_block
        and "[Proposed]" not in acceptance_block
        and "Evidence:" not in acceptance_block,
    )
    check(
        "compact Jira list keeps only key and title",
        "- GUIDES-100 - Some bug." in compact
        and "Similarity:" not in compact
        and "Status:" not in compact
        and "Worth checking because" not in compact,
    )
    check(
        "compact automation states main coverage and high-level target",
        "Main feature coverage: Partially covered" in compact
        and "integration/API test automation" in compact,
    )
    check(
        "compact view hides Open Questions but durable record keeps them",
        "**Open Questions**" not in compact
        and "No open questions from current evidence" not in compact
        and "**Open Questions**" in GOOD_PLAN,
    )

    invalid_source = _replace(
        GOOD_PLAN,
        "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output | Evidence: Jira UAC GUIDES-100.",
        "- AC-01: the feature works",
    )
    invalid_compact, invalid_problems = compact_mod.project(invalid_source)
    check(
        "compact renderer emits nothing for a noncanonical source AC",
        invalid_compact == "" and bool(invalid_problems),
    )

    no_match_plan = _replace(
        GOOD_PLAN,
        "- GUIDES-100 — Some bug. Similarity: strongest match — same failure shape of wrong output. Status: Closed. Resolution: Fixed. Affected version: not available in current evidence. Fix version: 2609. RCA: not available in current evidence. Test evidence: not available in current evidence. Impact: reuse its oracle.\n",
        "",
    )
    no_match_compact, no_match_problems = compact_mod.project(no_match_plan)
    check(
        "compact view renders a deterministic no-Jira result",
        no_match_problems == []
        and "No same-mechanism Jira ticket is worth checking" in no_match_compact,
    )


def test_authoring_state_contract() -> None:
    authoring = authoring_state_mod.derive_contract(
        "In Author view, editing deep inside a large topic or inserting a reference link "
        "unexpectedly scrolls the editing screen to the top and hides the active cursor."
    )
    check(
        "large-topic authoring issue routes to viewport stability",
        authoring["route"] == "authoring_viewport_stability",
    )
    authoring_text = "\n".join(
        [*authoring["acceptance_criteria"], *authoring["test_scenarios"]]
    )
    for marker in (
        "active caret or selected element deep in the document",
        "cross-reference or reference link",
        "focus returns to the intended insertion location",
        "relative to the active element rather than to an exact prior pixel offset",
        "type, paste",
        "cancel it repeatedly",
        "no reference or duplicate content is inserted",
    ):
        check(f"authoring viewport contract contains {marker}", marker in authoring_text)
    for unsupported in (
        "left map tree",
        "save/reopen",
        "old editor",
        "milliseconds",
        "data loss",
    ):
        check(
            f"authoring viewport contract does not invent {unsupported}",
            unsupported.lower() not in authoring_text.lower(),
        )

    preview = authoring_state_mod.derive_contract(
        "Map Preview scroll position, selected topic, refresh, and condition panel state "
        "must survive Edit-return behavior."
    )
    check("map preview remains a separate route", preview["route"] == "map_preview_state")
    preview_text = "\n".join(
        [*preview["acceptance_criteria"], *preview["test_scenarios"]]
    )
    check("map preview retains condition state", "condition state" in preview_text)
    check("map preview does not inherit caret behavior", "caret" not in preview_text.lower())

    cals = authoring_state_mod.derive_contract(
        "Delete two selected columns from a 6 row and 5 column CALS table."
    )
    check("CALS deletion gets the structural route", cals["route"] == "cals_multi_column_delete")
    cals_text = "\n".join([*cals["acceptance_criteria"], *cals["test_scenarios"]])
    for marker in (
        "source-defined row and column count",
        "visible column count decreases by the number of distinct deleted columns",
        "ghost column",
        "span metadata",
    ):
        check(f"CALS deletion contract contains {marker}", marker in cals_text)

    large_file = authoring_state_mod.derive_contract(
        "Ctrl+Z changes after the configured boundary; largeFileTagCount controls the large-file safeguard."
    )
    check(
        "large-file safeguard is configuration-driven working-as-designed behavior",
        large_file["route"] == "large_file_configuration"
        and large_file["classification"] == "working_as_designed_configuration",
    )
    large_file_text = "\n".join(
        [*large_file["acceptance_criteria"], *large_file["test_scenarios"]]
    )
    check("large-file contract uses parsed tag threshold", "parsed-tag threshold" in large_file_text)
    check(
        "large-file contract does not create an observed-count AC",
        all("observed count" not in criterion for criterion in large_file["acceptance_criteria"]),
    )
    key_only = authoring_state_mod.derive_contract("Historical issue GUIDES-35437")
    check(
        "historical issue key alone cannot activate the large-file route",
        key_only["route"] is None,
    )


def test_uac_fidelity_reference() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    reference_path = skill_root / "references" / "uac-reference-examples.md"
    reference_text = reference_path.read_text(encoding="utf-8")
    checklist_text = (skill_root / "references" / "quality-gate-checklist.md").read_text(encoding="utf-8")

    for marker in (
        "#### Accepted UAC Fidelity Gate",
        "aem-guides-uac-fidelity-v1",
        "bidirectional traceability",
        "configuration truth table",
        "Do not convert a working-as-designed complaint into Confirmed AC",
        "Do not treat a configuration-gated control as removed or deprecated",
        "Respect investigation chronology",
        "Do not equate `Resolution: Fixed` with a verified product-code fix",
        "Never merge a mainline accepted UAC into a hotfix ticket",
        "Collapse repeated identical UAC blocks deterministically",
        "Incident workload observations are not performance SLAs",
        "Product-fix chronology without accepted UAC remains candidate regression evidence",
        "jira_comment_accepted_scope",
        "Preserve contradictory automation labels",
        "### Deterministic Authoring-State Routing",
        "scripts/authoring_state_contract.py",
        "references/authoring-state-uac.md",
        "references/component-routing.md",
        "scripts/component_reference_router.py",
        "references/component-authoring.md",
        "references/component-integration.md",
        "When a later accepted scope conflicts with an older description",
        "For map-Xref display labels, separate visible text from destination semantics",
        "For hierarchy-selection counts, derive the expected selected set and count from the current fixture",
        "For Explorer sorting, keep display label, sort key, sort direction",
        "For asset CRUD API requests",
    ):
        check(f"skill retains UAC fidelity marker {marker}", marker in skill_text)
    for marker in (
        "non-authoritative regression and evaluator catalog",
        "must never activate or authorize that rule for a new issue",
        "## What Good UAC Looks Like",
        "## Gold Reference:",
        "## Caution Reference:",
        "[Proposed]",
        "[Confirmed]",
        "Open Question",
    ):
        check(f"regression catalog retains generic fixture boundary {marker}", marker in reference_text)
    check(
        "quality gate enforces accepted UAC fidelity",
        "Final accepted UAC exists but its fidelity audit is missing" in checklist_text,
    )

    authoring_reference = (
        skill_root / "references" / "authoring-state-uac.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "## Route 1 - Authoring Viewport Stability",
        "## Route 2 - Map Preview State Restoration",
        "## Route 3 - CALS Multi-Column Deletion",
        "## Route 4 - Configuration-Driven Large-File Safeguard",
        "Derive the starting row/column count",
        "largeFileTagCount",
        "Screenshot-only and pasted examples",
    ):
        check(
            f"authoring-state reference retains marker {marker}",
            marker in authoring_reference,
        )

    repo_root = Path(__file__).resolve().parents[4]
    counterpart_root = (
        repo_root
        / (".claude" if skill_root.parts[-3] == ".codex" else ".codex")
        / "skills"
        / "test-plan-generation"
    )
    counterpart = counterpart_root / "references" / "uac-reference-examples.md"
    if counterpart.is_file():
        check("Codex and Claude UAC references stay identical", reference_path.read_bytes() == counterpart.read_bytes())


def test_component_reference_routing() -> None:
    thumbnail = component_router_mod.route_references(
        summary="Thumbnail display for multimedia on homepage repo and new search result panel",
        description=(
            "Multi-selection is not possible when applying an image to a topic. "
            "Multi-selection should only be possible within a specific folder."
        ),
        acceptance_criteria=(
            "Thumbnail should be shown for valid image files in Home Repository content view, "
            "Search panel, and Bottom search panel. PNG, JPG, and SVG thumbnails should match "
            "the latest image version and load with lazy-loading without layout jank."
        ),
        resolution="Fixed",
        labels=["UAC_Done", "Customer-A"],
    )
    check("thumbnail scope routes to Authoring", thumbnail["primary_component"] == "Authoring")
    check(
        "accepted thumbnail scope excludes stale multi-selection mechanism",
        thumbnail["mechanisms"] == ["asset_browser_thumbnail"],
    )
    check(
        "thumbnail scope pivot emits a deterministic warning",
        "stale_multi_selection_request_is_not_thumbnail_uac" in thumbnail["warnings"],
    )
    check(
        "Authoring route avoids the full UAC catalog",
        thumbnail["references"]
        == ["references/component-routing.md", "references/component-authoring.md"]
        and thumbnail["load_full_uac_reference"] is False,
    )

    map_xref = component_router_mod.route_references(
        summary="Display Title Instead of File Name for MAP References in Xref",
        description=(
            "Topics display the Title in Xref, but MAP files display the file name. "
            "MAP references should display the Title."
        ),
        resolution="Duplicate",
    )
    check("map Xref routes to Authoring", map_xref["primary_component"] == "Authoring")
    check(
        "map Xref receives the exact mechanism",
        map_xref["mechanisms"] == ["xref_map_display_label"],
    )
    check("duplicate without UAC is Proposed-only", map_xref["scope_mode"] == "proposed_only")
    check(
        "duplicate warning is explicit",
        "caution_resolution_without_uac_is_proposed_only" in map_xref["warnings"],
    )

    configured_conditional_attribute = component_router_mod.route_references(
        component="Editor",
        summary="Friendly names for conditional attributes in Full Tags and Right Panel",
        description=(
            "Discover attributes from /libs/fmdita/config/condAttrList.csv. A newly configured "
            "conditional attribute must use its friendly name or the approved fallback label."
        ),
        acceptance_criteria=(
            "Configured conditional attributes appear in Full Tags, Condition Attributes, and "
            "the Right Panel without freezing the current values into a hardcoded list."
        ),
        labels=["UAC_Done"],
    )
    check(
        "explicit Editor conditional-attribute scope preserves its Jira component",
        configured_conditional_attribute["primary_component"] == "Editor",
    )
    check(
        "conditional-attribute configuration receives the exact mechanism",
        configured_conditional_attribute["mechanisms"]
        == ["config_driven_conditional_attribute_labels"],
    )
    check(
        "conditional-attribute configuration uses the focused Authoring and enumeration packs",
        configured_conditional_attribute["references"]
        == [
            "references/component-routing.md",
            "references/component-authoring.md",
            "references/configuration-driven-enumerations.md",
        ]
        and configured_conditional_attribute["load_full_uac_reference"] is False,
    )
    check(
        "conditional-attribute matrix warning is required",
        "configuration_driven_conditional_attribute_matrix_required"
        in configured_conditional_attribute["warnings"],
    )

    semantic_conditional_attribute = component_router_mod.route_references(
        summary="Dynamically configured conditional attributes need friendly names",
        description=(
            "Use friendly display labels for configured conditional attributes and a raw fallback "
            "when a mapping is absent."
        ),
    )
    check(
        "semantic conditional-attribute wording activates the same route without a path",
        semantic_conditional_attribute["mechanisms"]
        == ["config_driven_conditional_attribute_labels"]
        and "references/configuration-driven-enumerations.md"
        in semantic_conditional_attribute["references"],
    )

    generic_ditaval_filter = component_router_mod.route_references(
        summary="Use DITAVAL conditional filtering for AEM Sites output",
        description="The output preset offers None and Using DITAVAL filtering modes.",
    )
    check(
        "generic DITAVAL filtering does not activate conditional-attribute label learning",
        "config_driven_conditional_attribute_labels"
        not in generic_ditaval_filter["mechanisms"],
    )

    generic_right_panel = component_router_mod.route_references(
        summary="Review task details in the Right Panel",
        description="The Right Panel shows the selected review task and its status.",
    )
    check(
        "generic Right Panel wording does not activate conditional-attribute label learning",
        "config_driven_conditional_attribute_labels" not in generic_right_panel["mechanisms"],
    )

    map_selection = component_router_mod.route_references(
        component="Authoring",
        summary="Incorrect selected items in Map View",
        acceptance_criteria=(
            "In a fresh Map View, selecting root-map for the first time must immediately "
            "display 9 selected rather than 2 selected. The selected set includes root-map "
            "and every child node named by this fixture; later correct selections cannot mask "
            "the first failure."
        ),
        resolution="Fixed",
        labels=["Authoring", "UAC_Done"],
    )
    check(
        "Map View hierarchy count routes to Authoring",
        map_selection["primary_component"] == "Authoring",
    )
    check(
        "Map View hierarchy count receives the exact mechanism",
        map_selection["mechanisms"] == ["map_view_hierarchy_selection_count"],
    )
    check(
        "accepted Map View count uses accepted scope",
        map_selection["scope_mode"] == "accepted_field_primary",
    )

    explorer_sorting = component_router_mod.route_references(
        summary="Enable filename-based or user-selectable sorting in Web Editor Explorer",
        description=(
            "User Preferences Display File name changes the Explorer label, but the folder-level "
            "Assets sort order remains unchanged. The requested outcome either honours the display "
            "preference as the default sort key or exposes explicit sort controls for Name or Title "
            "with ascending and descending direction plus a per-user session override."
        ),
        resolution="Working as Designed",
        labels=["Customer-B"],
    )
    check(
        "Explorer filename/title sorting routes to Authoring",
        explorer_sorting["primary_component"] == "Authoring",
    )
    check(
        "Explorer sorting receives the exact mechanism",
        explorer_sorting["mechanisms"] == ["explorer_filename_title_sorting"],
    )
    check(
        "working-as-designed Explorer request stays Proposed-only",
        explorer_sorting["scope_mode"] == "proposed_only",
    )
    for warning in (
        "accepted_uac_missing",
        "caution_resolution_without_uac_is_proposed_only",
        "explorer_sort_request_without_accepted_uac_is_proposed_only",
        "explorer_sort_interaction_model_is_unresolved",
    ):
        check(f"Explorer sorting warning is retained: {warning}", warning in explorer_sorting["warnings"])

    explorer_sorting_with_mockup = component_router_mod.route_references(
        summary="Enable filename-based or user-selectable sorting in Web Editor Explorer",
        description=(
            "The requested outcome either honours the display preference as the default sort key "
            "or exposes explicit sort controls for Name or Title with ascending and descending."
        ),
        design_evidence=(
            "The inspected mockup shows a dedicated sort action in the Explorer header to the right "
            "of Search and Add. Feature flag states must be tested with the flag OFF and ON, and the "
            "default state of the button must be validated. The flag key, configured default value, "
            "OFF-state presentation, menu, keys, direction behavior, and persistence are not shown."
        ),
        resolution="Working as Designed",
    )
    check(
        "Explorer mockup selects the explicit sort-control direction",
        explorer_sorting_with_mockup["design_resolution"] == "explicit_sort_control",
    )
    check(
        "Explorer mockup removes the unresolved interaction-model warning",
        "explorer_sort_interaction_model_is_unresolved"
        not in explorer_sorting_with_mockup["warnings"],
    )
    check(
        "Explorer mockup records its design-backed resolution",
        "explorer_sort_explicit_control_selected_by_design"
        in explorer_sorting_with_mockup["warnings"],
    )
    check(
        "Explorer feature flag requires an OFF/ON matrix",
        explorer_sorting_with_mockup["feature_flag_matrix_required"] is True,
    )
    check(
        "Explorer sort control requires default-state validation",
        explorer_sorting_with_mockup["default_control_state_required"] is True,
    )
    for warning in (
        "explorer_sort_feature_flag_state_matrix_required",
        "explorer_sort_feature_flag_key_unresolved",
        "explorer_sort_feature_flag_default_value_unresolved",
        "explorer_sort_flag_off_presentation_unresolved",
        "explorer_sort_button_default_state_required",
        "explorer_sort_button_default_state_unresolved",
    ):
        check(
            f"Explorer flag/default warning is retained: {warning}",
            warning in explorer_sorting_with_mockup["warnings"],
        )
    check(
        "Explorer OFF/ON evidence completes the requested state matrix",
        "explorer_sort_feature_flag_state_matrix_incomplete"
        not in explorer_sorting_with_mockup["warnings"],
    )

    explorer_label_only = component_router_mod.route_references(
        summary="Explorer displays file name instead of title",
        description="The visible Explorer label should follow the selected display preference.",
    )
    check(
        "generic Explorer label wording does not trigger sorting learning",
        "explorer_filename_title_sorting" not in explorer_label_only["mechanisms"],
    )

    folder_deletion = component_router_mod.route_references(
        summary="Request to add folder deletion feature in Guides",
        description=(
            "Guides has no folder delete action and users currently use Assets UI. "
            "The customer also asks for restore or trash behavior."
        ),
        labels=["Customer-C"],
    )
    check(
        "folder deletion routes to Authoring",
        folder_deletion["primary_component"] == "Authoring",
    )
    check(
        "folder deletion receives the exact mechanism",
        folder_deletion["mechanisms"] == ["folder_deletion"],
    )
    check(
        "folder deletion without accepted UAC stays Proposed-only",
        folder_deletion["scope_mode"] == "proposed_only",
    )
    for warning in (
        "folder_deletion_without_accepted_uac_is_proposed_only",
        "folder_deletion_surface_and_version_must_be_verified",
        "folder_restore_is_separate_from_delete_contract",
    ):
        check(
            f"folder deletion warning is retained: {warning}",
            warning in folder_deletion["warnings"],
        )

    generic_file_deletion = component_router_mod.route_references(
        summary="Delete a DITA file",
        description="An authorized user deletes one topic from the repository.",
    )
    check(
        "generic file deletion does not trigger folder-deletion learning",
        "folder_deletion" not in generic_file_deletion["mechanisms"],
    )

    crud_api = component_router_mod.route_references(
        summary="External-system asset CREATE and UPDATE CRUD APIs",
        description=(
            "The CREATE API must accept caller fileContent, metadata, a desired GUID independent "
            "of the human-readable filename, and the UPDATE call must work like UPSERT with an "
            "opt-in force creation control."
        ),
        resolution="",
        labels=["ABS", "CrownEquipment"],
    )
    check("asset CRUD API routes to Integration", crud_api["primary_component"] == "Integration")
    check(
        "asset CRUD API receives the exact mechanism",
        crud_api["mechanisms"] == ["asset_crud_api_contract"],
    )
    check(
        "asset CRUD API uses the focused Integration pack",
        crud_api["references"]
        == ["references/component-routing.md", "references/component-integration.md"]
        and crud_api["load_full_uac_reference"] is False,
    )
    check(
        "asset CRUD request without accepted UAC stays Proposed",
        crud_api["scope_mode"] == "description_candidate"
        and "crud_api_request_without_accepted_uac_is_proposed_only" in crud_api["warnings"],
    )

    generic_api = component_router_mod.route_references(
        summary="API returns an error",
        description="A generic API call fails without an asset CRUD payload contract.",
    )
    check(
        "generic API wording does not trigger asset CRUD learning",
        "asset_crud_api_contract" not in generic_api["mechanisms"]
        and generic_api["load_full_uac_reference"] is False
        and generic_api["references"] == ["references/component-routing.md"]
        and "no_focused_component_pack" in generic_api["warnings"],
    )

    bulk_overwrite = component_router_mod.route_references(
        summary="Abnormal behavior when overwriting a batch of assets",
        description=(
            "The initial bulk upload succeeds, but re-uploading the same-name asset batch "
            "through /bin/fmdita/import can remain stuck on a loader or show a generic error "
            "and redirect the authenticated author to login after repeated CSRF token requests."
        ),
        resolution="Cannot Reproduce",
        labels=["Customer-D"],
    )
    check(
        "bulk overwrite/session failure routes to Platform",
        bulk_overwrite["primary_component"] == "Platform",
    )
    check(
        "bulk overwrite/session failure receives the exact mechanism",
        bulk_overwrite["mechanisms"] == ["bulk_asset_overwrite_session"],
    )
    check(
        "bulk overwrite/session failure uses the focused Platform pack",
        bulk_overwrite["references"]
        == ["references/component-routing.md", "references/component-platform.md"]
        and bulk_overwrite["load_full_uac_reference"] is False,
    )
    for warning in (
        "accepted_uac_missing",
        "caution_resolution_without_uac_is_proposed_only",
        "bulk_overwrite_without_accepted_uac_is_proposed_only",
    ):
        check(
            f"bulk overwrite caution warning is retained: {warning}",
            warning in bulk_overwrite["warnings"],
        )

    generic_upload = component_router_mod.route_references(
        summary="Large asset upload is slow",
        description="A generic DAM upload takes a long time without overwrite or session evidence.",
    )
    check(
        "generic upload wording does not trigger bulk overwrite learning",
        "bulk_asset_overwrite_session" not in generic_upload["mechanisms"],
    )
    historical_count_only = component_router_mod.route_references(
        summary="Overwrite 200 with a stuck loader",
        description="A remembered count and symptom are provided without the required mechanism context.",
    )
    check(
        "historical count cannot replace mechanism context in routing",
        "bulk_asset_overwrite_session" not in historical_count_only["mechanisms"],
    )

    skill_root = Path(__file__).resolve().parents[1]
    authoring_reference = (skill_root / "references" / "component-authoring.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Asset-Browser Thumbnail Contract",
        "does not authorize new multi-selection behavior",
        "## Map-Xref Display Label Contract",
        "`href`, `format`, `scope`, `type`",
        '`scope="external"`',
        "## Map View Hierarchy Selection-Count Contract",
        "Derive the expected selected-node set",
        "cold first selection and a repeat selection separately",
        "Do not import a count, map name, file-type list, or version from another issue",
        "## SubjectScheme Title Resolution and Enumdefs Performance",
        "shared execution path",
        "Without all of those, performance is conditional",
        "## Explorer Filename/Title Sorting Contract",
        "display label, sort key, sort direction, folder default, per-user override",
        "A historical or static mockup cannot select the interaction",
        "## Folder Deletion Contract",
        "File deletion documentation does not prove folder deletion",
        "Historical feature requests are product-evolution context only",
        "## Configuration-Driven Conditional Attribute Discovery and Label Contract",
        "canary conditional attribute",
        "absent from inspected hardcoded allowlists",
        "raw XML attribute name or value",
        "added, renamed, and removed entries",
        "actual schema/DTD/specialization and profile gates",
        "Require live updates only when accepted evidence defines them",
    ):
        check(f"Authoring component pack retains marker {marker}", marker in authoring_reference)

    enumeration_reference = (
        skill_root / "references" / "configuration-driven-enumerations.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "## Minimum Coverage Matrix",
        "Newly added valid entry with a configured friendly/display name",
        "Newly added valid entry without a mapping",
        "active DTD/schema, element, profile, permission, or deployment scope",
        "hardcoded arrays, enums, switch branches, label maps",
        "supported configuration activation or reload boundary",
        "stored raw attribute/key/value",
    ):
        check(
            f"Configuration-driven enumeration reference retains marker {marker}",
            marker in enumeration_reference,
        )

    integration_reference = (skill_root / "references" / "component-integration.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Asset CRUD API Import Contract",
        "Historical tickets and supplied-document examples are regression fixtures only",
        "The word `API`, a historical issue key, or an old API document alone is insufficient",
        "Keep filename, repository path, product identity/GUID, version identity",
        "Keep CREATE, READ/download, UPDATE, DELETE, and UPSERT controls independent",
        "Discover and record each current endpoint, HTTP method, content type",
        "never copy an endpoint, parameter, default, or status from a historical example",
        "test existing and missing targets",
        "no duplicate identity appears",
        "Keep version/revision creation on an existing target separate from missing-target creation",
        "Keep delete reference-bypass/force behavior separate from UPDATE creation behavior",
        "Transport success alone is not a business-success oracle",
        "What identifies an UPDATE target",
        "Historical evidence may create a hypothesis only after same-mechanism verification",
    ):
        check(f"Integration component pack retains marker {marker}", marker in integration_reference)

    platform_reference = (skill_root / "references" / "component-platform.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Bulk Same-Name Asset Overwrite and Session Contract",
        "no historical-ticket authority",
        "A ticket key, customer name, old batch count, or old release cannot activate",
        "import endpoint traffic as failure signatures",
        "not a supported maximum, SLA, timeout, or resource ceiling",
        "observable terminal success, partial-success, or failure state",
        "verified by reading back every targeted asset",
        "Do not import counts from historical examples",
        "Historical evidence may propose a retrieval hypothesis",
        "Do not claim data loss",
    ):
        check(f"Platform component pack retains marker {marker}", marker in platform_reference)

    repo_root = _find_repo_root()
    codex_only_extensions = {
        "SKILL.md",
        "references/quality-gate-checklist.md",
        "scripts/test_skill_scripts.py",
    }
    for variant in (".codex", ".claude"):
        variant_root = repo_root / variant / "skills" / "test-plan-generation"
        for relative_path in (
            "SKILL.md",
            "references/chat-deliverable.md",
            "references/plain-language-ac-writing.md",
            "references/output-template.md",
            "references/quality-gate-checklist.md",
            "scripts/ac_presentation.py",
            "scripts/ac_contract.py",
            "scripts/extract_acs.py",
            "scripts/render_compact_view.py",
            "scripts/validate_test_plan.py",
            "scripts/test_skill_scripts.py",
        ):
            if variant == ".codex" and relative_path in codex_only_extensions:
                # The repository Codex skill may carry fail-closed gates that have
                # not yet been promoted to the canonical/Claude distribution.
                continue
            check(
                f"{variant} readability contract matches canonical: {relative_path}",
                (variant_root / relative_path).read_bytes()
                == (repo_root / "skills" / "test-plan-generation" / relative_path).read_bytes(),
            )
        check(
            f"{variant} component router matches canonical",
            (variant_root / "scripts" / "component_reference_router.py").read_bytes()
            == (repo_root / "skills" / "test-plan-generation" / "scripts" / "component_reference_router.py").read_bytes(),
        )
        check(
            f"{variant} Authoring pack matches canonical",
            (variant_root / "references" / "component-authoring.md").read_bytes()
            == (repo_root / "skills" / "test-plan-generation" / "references" / "component-authoring.md").read_bytes(),
        )
        check(
            f"{variant} configuration-driven enumeration pack matches canonical",
            (variant_root / "references" / "configuration-driven-enumerations.md").read_bytes()
            == (repo_root / "skills" / "test-plan-generation" / "references" / "configuration-driven-enumerations.md").read_bytes(),
        )
        check(
            f"{variant} Integration pack matches canonical",
            (variant_root / "references" / "component-integration.md").read_bytes()
            == (repo_root / "skills" / "test-plan-generation" / "references" / "component-integration.md").read_bytes(),
        )
        check(
            f"{variant} Platform pack matches canonical",
            (variant_root / "references" / "component-platform.md").read_bytes()
            == (repo_root / "skills" / "test-plan-generation" / "references" / "component-platform.md").read_bytes(),
        )


def _relation(**over):
    base = {
        "source_construct": "navtitle", "target_construct": "locktitle",
        "relation": "CONTROLS", "dita_version": "1.3", "authority": "DITA_SPEC",
        "evidence": ["ask_dita_expert spec probe"], "material": True,
        "states": ["locked", "unlocked", "absent"], "status": "CONFIRMED",
        "behavioral_branch": "locked map title vs unlocked href title",
    }
    base.update(over)
    return base


def _semantics(relations, **over):
    block = {
        "active": True, "primary_constructs": ["topicref", "navtitle"],
        "dita_versions": ["1.3"], "governing_spec_retrieved": True,
        "product_implementation_checked": True, "automation_semantic_paths_checked": True,
        "unresolved": [], "relations": relations,
    }
    block.update(over)
    return block


def test_semantic_explorer() -> None:
    ex = explorer_mod
    SR = ex.SemanticRelation

    # --- relation-level evidence discipline ---
    missing_ev = SR.from_dict(_relation(evidence=[]))
    check("material relation with no evidence is rejected",
          any("no evidence" in p for p in ex.validate_relation(missing_ev)))
    bad_rel = SR.from_dict(_relation(relation="MODIFIES"))
    check("unknown relation type is rejected",
          any("not in the supported vocabulary" in p for p in ex.validate_relation(bad_rel)))
    check("well-formed relation validates clean", ex.validate_relation(SR.from_dict(_relation())) == [])
    # immaterial relations need no evidence (they are not asserted dependencies)
    check("immaterial relation without evidence is allowed",
          ex.validate_relation(SR.from_dict(_relation(material=False, evidence=[]))) == [])

    # --- neighbourhood bucketing (by relation TYPE, not construct name) ---
    nb = ex.build_neighborhood("navtitle", "ATTRIBUTE", [SR.from_dict(_relation())])
    check("CONTROLS lands in controlling_constructs bucket",
          any(e["construct"] == "locktitle" for e in nb["controlling_constructs"]))

    # --- coverage hypotheses exclude rejected / immaterial ---
    hyps = ex.generate_coverage_hypotheses([
        SR.from_dict(_relation()),
        SR.from_dict(_relation(target_construct="href", relation="CHANGES_PROCESSING_OF", authority="DITA_OT")),
        SR.from_dict(_relation(target_construct="chunk", status="REJECTED")),
        SR.from_dict(_relation(target_construct="props", material=False, evidence=[])),
    ])
    deps = {h["dependent_construct"] for h in hyps}
    check("hypotheses include material non-rejected deps", {"locktitle", "href"} <= deps)
    check("hypotheses exclude rejected and immaterial", "chunk" not in deps and "props" not in deps)

    # --- Cartesian-explosion protection: equivalent branches collapse ---
    dup = [
        {"relationship": "CONTROLS", "behavioral_branch": "locked", "dependent_construct": "locktitle"},
        {"relationship": "CONTROLS", "behavioral_branch": "locked", "dependent_construct": "locktitle"},
        {"relationship": "CONTROLS", "behavioral_branch": "unlocked", "dependent_construct": "locktitle"},
    ]
    kept, collapsed = ex.collapse_equivalent_paths(dup)
    check("equivalent hypotheses collapse to representatives", len(kept) == 2 and len(collapsed) == 1)

    # --- regression fixture: the navtitle Jira, run WITHOUT a locktitle hint ---
    # The exploration procedure (LLM) discovers locktitle from spec evidence and
    # records it; the gate PROVES that discovery was investigated to a terminal
    # status. Here it is CONFIRMED + the no-href/locktitle-absent branch is exposed.
    navtitle_fixture = _semantics(
        [
            _relation(),  # navtitle CONTROLS locktitle
            _relation(target_construct="href", relation="CHANGES_PROCESSING_OF",
                      authority="DITA_OT", states=["present", "absent"],
                      behavioral_branch="href present vs absent title source"),
        ],
        unresolved=["no-href + locktitle=absent navigation-title source undocumented in New AEM Sites"],
    )
    overall, dims, fails = ex.evaluate_semantic_gate(navtitle_fixture)
    check("navtitle fixture passes the semantic gate", overall == "PASSED" and fails == [])
    check("navtitle fixture exposes unresolved semantics",
          dims["UNRESOLVED_SEMANTICS_EXPOSED"] == "UNRESOLVED_AND_EXPOSED")

    # governing dependency discovered but left uninvestigated -> NEEDS_REVIEW
    uninvestigated = _semantics([_relation(status="INVESTIGATION_CANDIDATE")])
    o2, _d2, f2 = ex.evaluate_semantic_gate(uninvestigated)
    check("uninvestigated governing dependency makes the gate NEEDS_REVIEW",
          o2 == "NEEDS_REVIEW" and any("CONTROLLING_DEPENDENCIES_EXPLORED" in x for x in f2))

    # --- generalization: works for OTHER constructs with no navtitle involved ---
    conref_fixture = _semantics(
        [_relation(source_construct="conref", target_construct="conkeyref",
                   relation="FALLS_BACK_TO", authority="DITA_SPEC",
                   states=["direct", "indirect"], behavioral_branch="href vs keyref resolution")],
        primary_constructs=["conref"],
    )
    oc, _dc, fc = ex.evaluate_semantic_gate(conref_fixture)
    check("conref fixture passes the gate (generalizes beyond navtitle)", oc == "PASSED" and fc == [])

    keyref_fixture = _semantics(
        [_relation(source_construct="keyref", target_construct="keyscope",
                   relation="SCOPED_BY", authority="DITA_SPEC",
                   states=["in-scope", "out-of-scope"], behavioral_branch="key scope resolution")],
        primary_constructs=["keyref"],
    )
    ok, _dk, fk = ex.evaluate_semantic_gate(keyref_fixture)
    check("keyref fixture passes the gate (generalizes beyond navtitle)", ok == "PASSED" and fk == [])

    # inactive block is skipped, not failed
    overall_off, _do, _fo = ex.evaluate_semantic_gate({"active": False})
    check("inactive DITA semantics gate is SKIPPED", overall_off == "SKIPPED")


def test_anti_hardcoding() -> None:
    import tempfile
    aud = audit_mod
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        def _py(name, body):
            p = tmp_path / name
            p.write_text(body, encoding="utf-8")
            return p

        clean = _py("clean.py", "def f(data):\n    if data:\n        return status_of(data)\n")
        failures, _ = aud.audit_paths([clean])
        check("clean production code passes the audit", failures == [])

        banned = _py("banned.py", "def run(node):\n    if navtitle:\n        add_locktitle_tests()\n")
        failures, _ = aud.audit_paths([banned])
        check("`if navtitle:` production guard is flagged", any("navtitle" in f for f in failures))

        exempt = _py("exempt.py", "# illustrative example only, not a production rule\ndef run():\n    if navtitle:\n        pass\n")
        failures, _ = aud.audit_paths([exempt])
        check("construct guard with an example/provenance marker is exempt", failures == [])

        pair = _py("pair.py", 'RULES = {"keyref": "keyscope"}\n')
        failures, _ = aud.audit_paths([pair])
        check("construct->construct pair literal is flagged", any("keyref" in f and "keyscope" in f for f in failures))

        # ambiguous-only pair must NOT fail (coincidental generic words)
        amb = _py("amb.py", 'CFG = {"type": "format"}\nif data:\n    pass\n')
        failures, _ = aud.audit_paths([amb])
        check("ambiguous-only literals / `if data:` are not flagged", failures == [])

        # markdown: bare rule-arrow is flagged, but an example-marked one is exempt
        bad_md = _py("bad.md", "The mapping is navtitle -> locktitle for all cases.\n")
        failures, _ = aud.audit_paths([bad_md])
        check("bare construct rule-arrow in a prompt is flagged", any("navtitle" in f for f in failures))

        ok_md = _py("ok.md", "Example only: navtitle -> locktitle is discovered from evidence.\n")
        failures, _ = aud.audit_paths([ok_md])
        check("example-marked rule-arrow in a prompt is exempt", failures == [])

        # test_ files are skipped (regression fixtures may hold the anti-pattern)
        tf = _py("test_x.py", "def t():\n    if navtitle:\n        add_locktitle()\n")
        failures, _ = aud.audit_paths([tf])
        check("test_*.py files are skipped by the audit", failures == [])

    # regression guard: the real skill dir must stay clean
    skill_root = Path(__file__).resolve().parent.parent
    failures, _ = aud.audit_paths([skill_root])
    check("the real skill directory passes the anti-hardcoding audit", failures == [])


def test_production_jira_hardcoding_audit() -> None:
    audit = production_hardcoding_mod
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "references").mkdir()
        (root / "scripts").mkdir()
        (root / "SKILL.md").write_text(
            "For GUIDES-99999, always require the remembered workload.", encoding="utf-8"
        )
        failures = audit.audit(root)
        check(
            "a concrete historical issue key in production instructions fails",
            any("concrete GUIDES issue key" in failure for failure in failures),
        )
        (root / "SKILL.md").write_text(
            "Route from current mechanism evidence; issue identity is not authority.",
            encoding="utf-8",
        )
        (root / "references" / "uac-reference-examples.md").write_text(
            "Regression fixture GUIDES-99999 with an old observed workload.",
            encoding="utf-8",
        )
        check(
            "explicit regression fixture catalog is excluded from production audit",
            audit.audit(root) == [],
        )

    skill_root = Path(__file__).resolve().parents[1]
    check(
        "active skill has no historical Jira identity or fixture threshold",
        audit.audit(skill_root) == [],
    )


def test_behavior_model() -> None:
    bm = behavior_mod
    F = lambda **k: dict(k)  # noqa: E731 - tiny fact builder for fixtures

    # A valid model for each ticket family the phase must support.
    ui = {"trigger": ["user clicks Generate in Map dashboard"], "operations": ["render toc"],
          "consumers": ["Map dashboard UI", "Editor toc panel"],
          "facts": [F(fact="both surfaces read the same toc model", evidence_ids=["E1"], authority="CURRENT_IMPLEMENTATION", confidence=0.7)]}
    backend = {"trigger": ["POST publish job"], "operations": ["build output"], "inputs": ["map path"],
               "outputs": ["site nodes"], "processors": ["PublishingJob"]}
    config = {"trigger": ["preset toggled"], "operations": ["branch on setting"],
              "configuration_branches": ["dita processing on", "dita processing off"], "outputs": ["toc"]}
    publishing = {"trigger": ["generate output"], "operations": ["transform"], "outputs": ["pdf"],
                  "publishing_modes": ["Native PDF", "DITA-OT PDF", "Native AEM Site"]}
    dita = {"trigger": ["publish map"], "operations": ["resolve toc"], "affected_state": ["navigation title"],
            "facts": [F(fact="no-href navtitle yields null path", evidence_ids=["E2"], authority="CURRENT_IMPLEMENTATION", confidence=0.8)]}
    # persistence model that CORRECTLY identifies the writer of the state it removes
    persistence_ok = {"trigger": ["delete topic"], "operations": ["cleanup parent-map property"],
                      "remove_paths": ["remove parentMaps entry"], "write_paths": ["writer adds parentMaps on add-to-map"],
                      "affected_state": ["parentMaps property"]}

    for name, m in (("ui", ui), ("backend", backend), ("config", config),
                    ("publishing", publishing), ("dita", dita), ("persistence_ok", persistence_ok)):
        check(f"behavior_model valid for {name} ticket", bm.validate_behavior_model(m) == [])

    # empty / shapeless model is rejected
    check("empty behavior_model is rejected", any("effectively empty" in p for p in bm.validate_behavior_model({})))

    # a fact without evidence is inference -> rejected
    no_ev = {"trigger": ["x"], "operations": ["y"], "facts": [F(fact="claim", evidence_ids=[], authority="JIRA")]}
    check("fact without evidence_ids is rejected", any("no evidence_ids" in p for p in bm.validate_behavior_model(no_ev)))

    # bad authority rejected
    bad_auth = {"trigger": ["x"], "operations": ["y"], "facts": [F(fact="c", evidence_ids=["E1"], authority="VIBES")]}
    check("fact with unknown authority is rejected", any("authority" in p for p in bm.validate_behavior_model(bad_auth)))

    # confidence out of range rejected
    bad_conf = {"trigger": ["x"], "operations": ["y"], "confidence": 1.7}
    check("confidence out of range is rejected", any("confidence" in p for p in bm.validate_behavior_model(bad_conf)))

    # list field given a non-list rejected
    bad_type = {"trigger": "click", "operations": ["y"]}
    check("non-list model field is rejected", any("must be a list" in p for p in bm.validate_behavior_model(bad_type)))

    # persistence rule: removes state but never identifies the writer -> rejected
    persistence_gap = {"trigger": ["delete topic"], "operations": ["cleanup"],
                       "remove_paths": ["remove parentMaps entry"], "affected_state": ["parentMaps"]}
    check("state removal without a writer path is rejected",
          any("what WRITES that state" in p for p in bm.validate_behavior_model(persistence_gap)))

    # same gap is acceptable if the missing writer is explicitly flagged unknown
    persistence_flagged = dict(persistence_gap, unknowns=["who writes parentMaps is not yet identified"])
    check("state removal passes when the missing writer is flagged in unknowns",
          bm.validate_behavior_model(persistence_flagged) == [])

    # run_gates skips the check when no block is present (backward compatible)
    check("behavior_model absent is not a failure", bm.is_present({"issue": "X"}) is False)


def test_coverage_hypotheses() -> None:
    cov = coverage_mod

    def H(**k):
        base = {"hypothesis_id": "H", "dimension": "CONSUMER", "candidate": "another surface reads the model",
                "reason": "shared model", "technical_basis": ["behavior_model.consumers has 2 surfaces"],
                "status": "INVESTIGATION_CANDIDATE", "requires_more_evidence": True, "confidence": 0.4}
        base.update(k)
        return base

    # a relevant, evidence-justified candidate validates
    check("valid coverage candidate passes", cov.validate_coverage_block([H()]) == [])

    # candidate defaults to INVESTIGATION_CANDIDATE (never an AC at this stage)
    check("candidate status is INVESTIGATION_CANDIDATE by default",
          coverage_mod.CoverageHypothesis().status == "INVESTIGATION_CANDIDATE")

    # speculation (no technical_basis) is rejected -> enforces "evidence -> candidate"
    check("candidate with no technical_basis is rejected",
          any("no technical_basis" in p for p in cov.validate_coverage_block([H(technical_basis=[])])))

    # unknown dimension rejected (irrelevant/invented dimension does not slip in)
    check("unknown dimension is rejected",
          any("is not one of" in p for p in cov.validate_coverage_block([H(dimension="VIBES")])))

    # bad status rejected
    check("invalid status is rejected",
          any("status" in p for p in cov.validate_coverage_block([H(status="MAYBE")])))

    # confidence range enforced
    check("confidence out of range is rejected",
          any("confidence" in p for p in cov.validate_coverage_block([H(confidence=2.0)])))

    # Cartesian-explosion guard: two equivalent candidates must collapse
    dup = [H(hypothesis_id="H1", candidate="type A reaches path", dimension="TYPE_ABSTRACTION", equivalence_key="reaches-path"),
           H(hypothesis_id="H2", candidate="type B reaches path", dimension="TYPE_ABSTRACTION", equivalence_key="reaches-path")]
    check("equivalent candidates are flagged for collapse",
          any("collapse" in p for p in cov.validate_coverage_block(dup)))
    kept, collapsed = cov.collapse_hypotheses([coverage_mod.CoverageHypothesis.from_dict(x) for x in dup])
    check("collapse keeps one representative of an equivalent family", len(kept) == 1 and len(collapsed) == 1)

    # distinct dimensions/candidates do NOT collapse (no false merging)
    distinct = [H(hypothesis_id="H1", dimension="CONSUMER", candidate="surface X"),
                H(hypothesis_id="H2", dimension="NFR_RISK", candidate="large hierarchy traversal",
                  technical_basis=["deep map traversal per reference"])]
    check("distinct candidates both pass and do not collapse", cov.validate_coverage_block(distinct) == [])

    # absent block is not a failure (backward compatible; irrelevant explorers just do not activate)
    check("coverage_hypotheses absent is not a failure", cov.is_present({"issue": "X"}) is False)


def test_missing_questions() -> None:
    mq = mq_mod

    def Q(**k):
        base = {"question_id": "Q-01", "question": "Who originally writes this state?",
                "why_it_matters": "a cleanup fix must not leave the writer producing bad state",
                "hypothesis_id": "H-01", "preferred_sources": ["current repository"],
                "search_concepts": ["what writes the parent-map property"], "blocking": True,
                "if_unresolved": "OPEN_QUESTION"}
        base.update(k)
        return base

    def E(p="initial", **k):
        base = {"evidence_id": "E1", "source": "current repository", "query": "initial jira keywords",
                "pass": p, "status": "RETRIEVED", "question_id": ""}
        base.update(k)
        return base

    # a well-formed question validates
    check("valid missing_question passes", mq.check_retrieval_discipline([Q()], [
        E(), E("second", evidence_id="E2", query="what writes the parent-map property", status="USED", question_id="Q-01")]) == [])

    # (1) second retrieval is required only when a material question exists
    check("material question requires a second pass", mq.requires_second_pass([mq.MissingQuestion.from_dict(Q(blocking=True))]) is True)
    check("no material question -> no second pass required", mq.requires_second_pass([mq.MissingQuestion.from_dict(Q(blocking=False))]) is False)
    # a blocking question with NO second-pass evidence is flagged
    check("material question without a second pass is rejected",
          any("no second-pass retrieval" in p for p in mq.check_retrieval_discipline([Q()], [E()])))

    # (2) second query must differ from the initial Jira keyword query
    same = [E("initial", query="native aem site navtitle"),
            E("second", evidence_id="E2", query="native aem site navtitle", question_id="Q-01")]
    check("second query identical to initial is rejected",
          any("must be derived from the missing question" in p for p in mq.check_retrieval_discipline([Q()], same)))
    diff_items = [mq.EvidenceItem.from_dict(E("initial", query="A")),
                  mq.EvidenceItem.from_dict(E("second", evidence_id="E2", query="B"))]
    check("a genuinely new second-pass query is detected", mq.new_second_pass_queries(diff_items) == ["b"])

    # (3) evidence can resolve a candidate (a USED item for its question)
    used = [mq.EvidenceItem.from_dict(E("second", evidence_id="E2", status="USED", question_id="Q-01"))]
    check("USED evidence resolves the question", mq.is_resolved("Q-01", used) is True)

    # (4) missing/rejected evidence leaves it unresolved, and it must stay an Open Question
    unresolved = [mq.EvidenceItem.from_dict(E("second", evidence_id="E2", status="REJECTED", question_id="Q-01"))]
    check("REJECTED-only evidence leaves the question unresolved", mq.is_resolved("Q-01", unresolved) is False)
    check("unresolved question must declare if_unresolved OPEN_QUESTION",
          any("OPEN_QUESTION" in p for p in mq.check_retrieval_discipline([Q(if_unresolved="GUESS")], [E(), E("second", evidence_id="E9", query="new q")])))

    # (5) duplicate retrieval loops are prevented
    dup = [E("second", evidence_id="E1", query="repeat", source="rag"),
           E("second", evidence_id="E2", query="repeat", source="rag")]
    check("duplicate (query,source) retrieval is flagged",
          any("duplicate retrieval" in p for p in mq.check_retrieval_discipline([Q()], dup)))

    # schema guards
    check("question without search_concepts is rejected",
          any("search_concepts" in p for p in mq.check_retrieval_discipline([Q(search_concepts=[])], [E(), E("second", evidence_id="E2", query="new")])))
    check("evidence with unknown status is rejected",
          any("status" in p for p in mq.check_retrieval_discipline([Q(blocking=False)], [E(status="MAYBE")])))
    check("evidence with out-of-bound pass is rejected",
          any("pass" in p for p in mq.check_retrieval_discipline([Q(blocking=False)], [E("fourth")])))

    # Adversarial referential integrity: a retrieved fact must be linked to a
    # declared reasoning object, and its source must be authoritative for the
    # missing question's subject.
    contract_q = Q(
        subject="PRODUCT_CONTRACT", material=True, source_ref="CF-01",
        open_question_ref="OQ-01", preferred_sources=["linked jira"],
    )
    wrong_source = [
        E(),
        E(
            "second", evidence_id="E2", query="approved intended behavior",
            source="current repository", status="USED", question_id="Q-01",
            subject="PRODUCT_CONTRACT",
        ),
    ]
    check(
        "implementation retrieval cannot resolve a product-contract question",
        any(
            "cannot resolve" in p
            for p in mq.check_retrieval_discipline(
                [contract_q], wrong_source, open_question_ids={"OQ-01"}
            )
        ),
    )
    unlinked_used = [E(status="USED", question_id="", hypothesis_id="")]
    check(
        "USED evidence must reference a question or hypothesis",
        any(
            "question_id or hypothesis_id" in p
            for p in mq.check_retrieval_discipline([], unlinked_used)
        ),
    )
    unknown_question = [E(status="USED", question_id="Q-GHOST")]
    check(
        "evidence cannot reference an undeclared question",
        any(
            "unknown question" in p
            for p in mq.check_retrieval_discipline([], unknown_question)
        ),
    )
    unknown_hypothesis = [E(status="USED", hypothesis_id="H-GHOST")]
    check(
        "evidence cannot reference an undeclared hypothesis",
        any(
            "unknown hypothesis" in p
            for p in mq.check_retrieval_discipline(
                [], unknown_hypothesis, hypothesis_ids=set()
            )
        ),
    )
    check(
        "a missing question cannot reference an undeclared hypothesis",
        any(
            "unknown hypothesis" in p
            for p in mq.check_retrieval_discipline(
                [Q(blocking=False)], [], hypothesis_ids=set()
            )
        ),
    )
    duplicate_ids = [E(), E(evidence_id="E1", query="different query")]
    check(
        "duplicate evidence ids are rejected",
        any(
            "evidence_id duplicates" in p
            for p in mq.check_retrieval_discipline([], duplicate_ids)
        ),
    )

    # absent blocks are backward-compatible
    check("missing_questions/evidence absent is not a failure", mq.is_present({"issue": "X"}) is False)


def test_hypothesis_verifier() -> None:
    hv = verifier_mod

    def V(**k):
        base = {"hypothesis_id": "H-01", "verdict": "CONFIRMED",
                "supporting_authorities": ["JIRA_EXPECTED_BEHAVIOR"], "supporting_evidence": ["E5"],
                "disposition": "ACCEPTANCE_CRITERION", "subject": "PRODUCT_CONTRACT"}
        base.update(k)
        return base

    # (1) a plausible hypothesis is CONFIRMED on authoritative evidence -> AC
    check("plausible hypothesis confirmed on authoritative evidence", hv.validate_verification(hv.Verification.from_dict(V())) == [])
    code_only_ac = V(supporting_authorities=["CURRENT_IMPLEMENTATION"])
    check(
        "current implementation alone cannot authorize an AC",
        any("cannot authorize" in p for p in hv.validate_verification(hv.Verification.from_dict(code_only_ac))),
    )

    # (2) a plausible hypothesis is REJECTED with disproving evidence -> excluded
    rej = V(verdict="REJECTED", disproving_evidence=["E7"], disposition="EXCLUDED", supporting_authorities=[])
    check("hypothesis rejected with disproving evidence", hv.validate_verification(hv.Verification.from_dict(rej)) == [])
    # REJECTED cannot be routed into an AC
    rej_ac = V(verdict="REJECTED", disproving_evidence=["E7"], disposition="ACCEPTANCE_CRITERION")
    check("REJECTED cannot enter an AC", any("cannot have disposition" in p for p in hv.validate_verification(hv.Verification.from_dict(rej_ac))))

    # (3) conflicting evidence becomes UNRESOLVED
    conf = V(verdict="CONFIRMED", conflict=True)
    check("conflicting evidence cannot be CONFIRMED", any("must be UNRESOLVED" in p for p in hv.validate_verification(hv.Verification.from_dict(conf))))
    unres = V(verdict="UNRESOLVED", conflict=True, disposition="OPEN_QUESTION", open_question_ref="OQ-1", supporting_authorities=[])
    check("conflict resolved as UNRESOLVED->Open Question passes", hv.validate_verification(hv.Verification.from_dict(unres)) == [])

    # (4) specification and implementation differ -> conflict -> UNRESOLVED (same rule as (3), spec/impl framing)
    spec_impl = V(verdict="INFERRED_HIGH_CONFIDENCE", conflict=True, supporting_evidence=["E1", "E2"], disposition="INFERRED_AC")
    check("spec-vs-impl divergence forces UNRESOLVED", any("must be UNRESOLVED" in p for p in hv.validate_verification(hv.Verification.from_dict(spec_impl))))

    # (5) an existing test alone is insufficient for CONFIRMED
    test_only = V(verdict="CONFIRMED", supporting_authorities=["EXISTING_AUTOMATION"])
    check("existing test alone cannot CONFIRM current contract",
          any("not the current product contract" in p or "authoritative source" in p for p in hv.validate_verification(hv.Verification.from_dict(test_only))))
    # similarity alone is not proof
    sim = V(verdict="CONFIRMED", similarity_only=True, supporting_authorities=[])
    check("embedding similarity alone cannot CONFIRM", any("similarity" in p for p in hv.validate_verification(hv.Verification.from_dict(sim))))

    # UNRESOLVED must be routed to an Open Question, never an AC
    unres_ac = V(verdict="UNRESOLVED", conflict=True, disposition="ACCEPTANCE_CRITERION", open_question_ref="OQ-2")
    check("UNRESOLVED cannot become an AC", any("cannot have disposition" in p for p in hv.validate_verification(hv.Verification.from_dict(unres_ac))))
    unres_no_oq = V(verdict="UNRESOLVED", insufficient=True, disposition="OPEN_QUESTION", supporting_authorities=[])
    check("UNRESOLVED without an open_question_ref is rejected", any("open_question_ref" in p for p in hv.validate_verification(hv.Verification.from_dict(unres_no_oq))))

    # INFERRED_HIGH_CONFIDENCE stays inferred (a product decision means it should be CONFIRMED)
    inferred_ok = V(verdict="INFERRED_HIGH_CONFIDENCE", supporting_evidence=["E1", "E2"], disposition="REGRESSION", supporting_authorities=["CURRENT_IMPLEMENTATION"], subject="ACTUAL_IMPLEMENTATION")
    check("inferred-high-confidence with 2+ facts and no product decision passes", hv.validate_verification(hv.Verification.from_dict(inferred_ok)) == [])
    inferred_pd = V(verdict="INFERRED_HIGH_CONFIDENCE", supporting_evidence=["E1", "E2"], product_decision=True, disposition="INFERRED_AC")
    check("inferred verdict with an explicit product decision is rejected", any("should be CONFIRMED" in p for p in hv.validate_verification(hv.Verification.from_dict(inferred_pd))))

    # (6) an unsupported candidate never reaches UAC: an unverified coverage hypothesis is flagged
    cov = [{"hypothesis_id": "H-01", "status": "INVESTIGATION_CANDIDATE"},
           {"hypothesis_id": "H-02", "status": "INVESTIGATION_CANDIDATE"}]
    verifs = [V(hypothesis_id="H-01")]
    problems = hv.verify_all(cov, verifs)
    check("every coverage hypothesis must be verified (unverified is flagged)",
          any("H-02" in p and "no verification" in p for p in problems))
    check("verified hypothesis is not flagged", not any("H-01" in p and "no verification" in p for p in problems))

    # Adversarial joins: a verdict cannot cite a globally known but
    # subject-ineligible authority, an unknown hypothesis, duplicate terminal
    # verdicts, or evidence owned by another hypothesis.
    wrong_subject_authority = V(
        verdict="CONFIRMED", disposition="REGRESSION",
        supporting_authorities=["CURRENT_IMPLEMENTATION"],
        subject="PRODUCT_CONTRACT",
    )
    check(
        "authority is validated against the hypothesis subject",
        any(
            "not valid for subject" in p
            for p in hv.validate_verification(
                hv.Verification.from_dict(wrong_subject_authority)
            )
        ),
    )
    no_evidence = V(supporting_evidence=[])
    check(
        "CONFIRMED requires a concrete evidence reference",
        any(
            "requires supporting_evidence" in p
            for p in hv.validate_verification(hv.Verification.from_dict(no_evidence))
        ),
    )
    check(
        "verification cannot target an undeclared hypothesis",
        any(
            "unknown hypothesis" in p
            for p in hv.verify_all([], [V(hypothesis_id="H-GHOST")])
        ),
    )
    check(
        "a hypothesis cannot have two terminal verifications",
        any(
            "more than one verification" in p
            for p in hv.verify_all(
                [{"hypothesis_id": "H-01", "status": "INVESTIGATION_CANDIDATE"}],
                [V(), V()],
            )
        ),
    )
    evidence = [{
        "evidence_id": "E5", "status": "USED", "subject": "PRODUCT_CONTRACT",
        "authority": "JIRA_EXPECTED_BEHAVIOR", "hypothesis_id": "H-01",
    }]
    check(
        "verification passes when evidence, authority, subject, and hypothesis agree",
        hv.verify_all(
            [{"hypothesis_id": "H-01", "status": "INVESTIGATION_CANDIDATE"}],
            [V()], evidence_lifecycle=evidence,
        ) == [],
    )
    wrong_owner = json.loads(json.dumps(evidence))
    wrong_owner[0]["hypothesis_id"] = "H-02"
    check(
        "verification rejects evidence owned by another hypothesis",
        any(
            "not bound to hypothesis" in p
            for p in hv.verify_all(
                [{"hypothesis_id": "H-01", "status": "INVESTIGATION_CANDIDATE"}],
                [V()], evidence_lifecycle=wrong_owner,
            )
        ),
    )

    # absent block is backward compatible
    check("verifications absent is not a failure", hv.is_present({"issue": "X"}) is False)


def test_coverage_gate() -> None:
    cg = coverage_gate_mod

    def hyp(dim, hid, status="INVESTIGATION_CANDIDATE"):
        return {"hypothesis_id": hid, "dimension": dim, "candidate": "c", "reason": "r",
                "technical_basis": ["t"], "status": status}

    def verif(hid, verdict, **k):
        base = {"hypothesis_id": hid, "verdict": verdict}
        base.update(k)
        return base

    # a fully-explored plan: covered + rejected + unresolved-but-exposed -> PASS
    good = {
        "coverage_hypotheses": [hyp("CONSUMER", "H1"), hyp("STATE_PARTITION", "H2"), hyp("NFR_RISK", "H3")],
        "verifications": [verif("H1", "CONFIRMED", disposition="ACCEPTANCE_CRITERION"),
                          verif("H2", "REJECTED", disposition="EXCLUDED"),
                          verif("H3", "UNRESOLVED", disposition="OPEN_QUESTION", open_question_ref="OQ-1")],
        "open_questions": ["OQ-1"],
    }
    r = cg.evaluate(good)
    check("fully explored plan passes the coverage gate", r["semantic_gate"] == "PASS")
    check("covered dimension marked COVERED", r["dimensions"]["CONSUMER_EXPLORATION"] == "COVERED")
    check("rejected candidate marked INVESTIGATED_AND_REJECTED", r["dimensions"]["STATE_PARTITIONS"] == "INVESTIGATED_AND_REJECTED")
    check("exposed unresolved marked UNRESOLVED_AND_EXPOSED", r["dimensions"]["NFR"] == "UNRESOLVED_AND_EXPOSED")

    # adversarial 1: discovered abstraction/consumer NOT explored (candidate, no verification) -> NEEDS_REVIEW
    a1 = {"coverage_hypotheses": [hyp("CONTRACT_BOUNDARY", "H1"), hyp("CONSUMER", "H2")], "verifications": []}
    r1 = cg.evaluate(a1)
    check("discovered-but-unexplored contract/consumer -> NEEDS_REVIEW", r1["semantic_gate"] == "NEEDS_REVIEW"
          and r1["dimensions"]["CONTRACT_BOUNDARY"] == "NEEDS_REVIEW")
    with tempfile.TemporaryDirectory() as tmp:
        manifest_path = Path(tmp) / "coverage.json"
        manifest_path.write_text(json.dumps(a1), encoding="utf-8")
        gate = _load("run_gates_for_coverage_test", "run_gates.py")
        gate_failures, _ = gate.check_coverage_gate(str(manifest_path))
        check(
            "NEEDS_REVIEW blocks final delivery",
            any("unresolved review" in problem for problem in gate_failures),
        )

    # adversarial 2: meaningful state hypothesis UNRESOLVED but HIDDEN from Open Questions -> FAIL
    a2 = {"coverage_hypotheses": [hyp("STATE_PARTITION", "H1")],
          "verifications": [verif("H1", "UNRESOLVED", disposition="OPEN_QUESTION", open_question_ref="OQ-9")],
          "open_questions": []}  # OQ-9 not present -> hidden
    r2 = cg.evaluate(a2)
    check("hidden unresolved hypothesis -> FAIL", r2["semantic_gate"] == "FAIL"
          and any("Open Question" in b for b in r2["blocking_reasons"]))

    # adversarial 3: strong large-data signal (NFR) discovered but never evaluated -> NEEDS_REVIEW
    a3 = {"coverage_hypotheses": [hyp("NFR_RISK", "H1")], "verifications": []}
    check("unevaluated NFR signal -> NEEDS_REVIEW", cg.evaluate(a3)["semantic_gate"] == "NEEDS_REVIEW")

    # adversarial 4: material question but no new second-pass query -> NEEDS_REVIEW
    a4 = {"behavior_model": {"trigger": ["t"], "operations": ["o"]},
          "missing_questions": [{"question_id": "Q1", "question": "q", "why_it_matters": "w",
                                 "preferred_sources": ["rag"], "search_concepts": ["s"], "blocking": True,
                                 "if_unresolved": "OPEN_QUESTION"}],
          "evidence_lifecycle": [{"evidence_id": "E1", "source": "rag", "query": "same", "pass": "initial", "status": "RETRIEVED"},
                                 {"evidence_id": "E2", "source": "rag", "query": "same", "pass": "second", "status": "RETRIEVED"}]}
    check("material question without a new second pass -> NEEDS_REVIEW", cg.evaluate(a4)["dimensions"]["SECOND_PASS_RETRIEVAL"] == "NEEDS_REVIEW")

    # candidate investigated and proven irrelevant -> PASS
    a5 = {"coverage_hypotheses": [hyp("LIFECYCLE", "H1")],
          "verifications": [verif("H1", "REJECTED", disposition="EXCLUDED")]}
    check("investigated-and-rejected candidate -> PASS", cg.evaluate(a5)["semantic_gate"] == "PASS")

    # DITA semantics folded in: active DITA gate with uninvestigated dep -> NEEDS_REVIEW
    a6 = {"behavior_model": {"trigger": ["t"], "operations": ["o"]},
          "dita_semantics": {"active": True, "primary_constructs": ["topicref"], "dita_versions": ["1.3"],
                             "governing_spec_retrieved": True, "product_implementation_checked": True,
                             "automation_semantic_paths_checked": True,
                             "relations": [{"source_construct": "href", "target_construct": "navtitle",
                                            "relation": "CONTROLS", "dita_version": "1.3", "authority": "DITA_SPEC",
                                            "evidence": ["x"], "material": True, "states": ["a"],
                                            "status": "INVESTIGATION_CANDIDATE"}]}}
    check("active DITA dep left uninvestigated folds into NEEDS_REVIEW", cg.evaluate(a6)["dimensions"]["DITA_SEMANTICS"] == "NEEDS_REVIEW")

    # backward compatibility: no reasoning blocks -> gate does not activate
    check("coverage gate not present without reasoning blocks", cg.is_present({"issue": "X", "dita_semantics": {"active": True}}) is False)
    check("coverage gate present with a reasoning block", cg.is_present({"coverage_hypotheses": [hyp("CONSUMER", "H1")]}) is True)


def test_uac_integration() -> None:
    ig = integration_mod

    plan_with_oq = (
        "**Acceptance Criteria**\n"
        "- AC-01 [Confirmed]: (Basic) Given x | When y | Then z.\n"
        "**Open Questions**\n"
        "- Cleanup timing decision: is it synchronous on delete or async via a job? QA impact: changes the oracle.\n"
    )

    # UNRESOLVED surfaced in the plan Open Questions -> passes
    m_ok = {
        "coverage_hypotheses": [{"hypothesis_id": "H1", "dimension": "STATE_PARTITION", "candidate": "c",
                                 "reason": "r", "technical_basis": ["t"], "status": "UNRESOLVED"}],
        "verifications": [{"hypothesis_id": "H1", "verdict": "UNRESOLVED", "disposition": "OPEN_QUESTION",
                           "open_question_ref": "OQ-1", "insufficient": True}],
        "open_questions": [{"id": "OQ-1", "question": "Cleanup timing decision: is it synchronous on delete"}],
    }
    f, _ = ig.check_integration(m_ok, plan_with_oq)
    check("unresolved surfaced in plan Open Questions passes integration", f == [])

    # UNRESOLVED NOT surfaced in the plan Open Questions -> fails
    plan_missing_oq = "**Acceptance Criteria**\n- AC-01 [Confirmed]: (Basic) Given x | When y | Then z.\n**Open Questions**\n- Something unrelated.\n"
    f2, _ = ig.check_integration(m_ok, plan_missing_oq)
    check("unresolved missing from plan Open Questions fails integration", any("not surfaced" in p for p in f2))

    # evidence_trace: happy path (AC present, confirmed, evidence, links to confirmed verification)
    m_trace = {
        "coverage_hypotheses": [{"hypothesis_id": "H1", "dimension": "CONSUMER", "candidate": "c", "reason": "r", "technical_basis": ["t"], "status": "CONFIRMED"}],
        "verifications": [{"hypothesis_id": "H1", "verdict": "CONFIRMED", "disposition": "ACCEPTANCE_CRITERION"}],
        "evidence_trace": [{"ac_id": "AC-01", "hypothesis_id": "H1", "evidence_ids": ["E1"], "status": "CONFIRMED",
                            "activated_pattern": "CONSUMER"}],
    }
    f3, _ = ig.check_integration(m_trace, plan_with_oq)
    check("valid evidence_trace passes integration", f3 == [])

    # evidence_trace: ac_id not in plan -> fails
    m_bad_ac = dict(m_trace, evidence_trace=[{"ac_id": "AC-99", "hypothesis_id": "H1", "evidence_ids": ["E1"], "status": "CONFIRMED"}])
    f4, _ = ig.check_integration(m_bad_ac, plan_with_oq)
    check("evidence_trace with unknown ac_id fails", any("not present in the plan" in p for p in f4))

    # evidence_trace: AC traces to a REJECTED hypothesis -> fails (rejected never becomes AC)
    m_rej = {
        "coverage_hypotheses": [{"hypothesis_id": "H1", "dimension": "CONSUMER", "candidate": "c", "reason": "r", "technical_basis": ["t"], "status": "REJECTED"}],
        "verifications": [{"hypothesis_id": "H1", "verdict": "REJECTED", "disposition": "EXCLUDED", "disproving_evidence": ["E2"]}],
        "evidence_trace": [{"ac_id": "AC-01", "hypothesis_id": "H1", "evidence_ids": ["E1"], "status": "CONFIRMED"}],
    }
    f5, _ = ig.check_integration(m_rej, plan_with_oq)
    check("AC tracing to a REJECTED hypothesis fails", any("never become an Acceptance Criterion" in p for p in f5))

    # evidence_trace with no evidence_ids -> fails
    m_noev = dict(m_trace, evidence_trace=[{"ac_id": "AC-01", "hypothesis_id": "H1", "evidence_ids": [], "status": "CONFIRMED"}])
    f6, _ = ig.check_integration(m_noev, plan_with_oq)
    check("evidence_trace without evidence_ids fails", any("cite evidence_ids" in p for p in f6))

    # backward-compat: no reasoning blocks -> integration skipped
    f7, notes7 = ig.check_integration({"issue": "X"}, plan_with_oq)
    check("integration skipped without reasoning blocks", f7 == [] and any("skipped" in n for n in notes7))


def test_reasoning_required() -> None:
    run_gates = _load("run_gates", "run_gates.py")

    def _write(tmp, payload):
        p = Path(tmp) / "m.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        return str(p)

    bm = {"trigger": ["t"], "operations": ["o"]}
    cov = [{"hypothesis_id": "H1", "dimension": "CONSUMER", "candidate": "c", "reason": "r", "technical_basis": ["t"], "status": "CONFIRMED"}]
    verif = [{"hypothesis_id": "H1", "verdict": "CONFIRMED", "supporting_authorities": ["CURRENT_IMPLEMENTATION"], "supporting_evidence": ["E1"], "disposition": "ACCEPTANCE_CRITERION"}]

    with tempfile.TemporaryDirectory() as tmp:
        # behaviour_matters true (default) but no behavior_model -> required failure
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X"}))[0]
        check("behavior_model mandatory when behaviour_matters", any("behavior_model block is mandatory" in x for x in f))

        # behaviour_matters false -> requirement waived
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behaviour_matters": False}))[0]
        check("behaviour_matters false waives the reasoning requirement", f == [])

        # behavior_model alone is no longer semantic completeness
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behavior_model": bm}))[0]
        check(
            "behavior_model alone cannot satisfy the canonical pipeline",
            any("contract_facts" in x for x in f) and any("semantic_closure" in x for x in f),
        )

        # coverage declared without verifications -> required failure
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behavior_model": bm, "coverage_hypotheses": cov}))[0]
        check("coverage hypotheses without verifications is rejected", any("no verifications block" in x for x in f))

        # full canonical reasoning set -> satisfied
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", **_canonical_semantic_fixture()}))[0]
        check("full reasoning set satisfies the requirement", f == [])


def test_relevance_prioritizer() -> None:
    rp = relevance_mod

    direct = {"hypothesis_id": "H1", "candidate": "controlling attribute governs the value",
              "behavioral_distance": "DIRECT", "priority_reason": "directly controls the affected value",
              "status": "INVESTIGATION_CANDIDATE"}
    generic = {"hypothesis_id": "H2", "candidate": "analogous construct in another output",
               "behavioral_distance": "GENERIC_REGRESSION", "status": "INVESTIGATION_CANDIDATE"}

    # ranking puts DIRECT before GENERIC (not keyword/confidence order)
    ordered = rp.prioritize([generic, direct])
    check("prioritizer ranks DIRECT before GENERIC", [h["hypothesis_id"] for h in ordered] == ["H1", "H2"])

    # distance inferred from boolean signals when not explicit
    check("direct_semantic_dependency infers DIRECT",
          rp.effective_distance({"direct_semantic_dependency": True}) == "DIRECT")
    check("same_code_path infers ONE_HOP", rp.effective_distance({"same_code_path": True}) == "ONE_HOP")
    check("no signal defaults to GENERIC_REGRESSION", rp.effective_distance({}) == "GENERIC_REGRESSION")
    check("DIRECT is high relevance", rp.is_high_relevance(direct) is True)
    check("GENERIC is not high relevance", rp.is_high_relevance(generic) is False)

    # the core rule: a HIGH-relevance dependency left unexplored is flagged...
    blocked = rp.high_relevance_unresolved([direct, generic], verifications=[])
    check("unexplored HIGH-relevance hypothesis is flagged", [h["hypothesis_id"] for h in blocked] == ["H1"])
    # ...and clears once it reaches a terminal verdict
    verifs = [{"hypothesis_id": "H1", "verdict": "CONFIRMED"}]
    check("verified HIGH-relevance hypothesis clears the flag", rp.high_relevance_unresolved([direct, generic], verifs) == [])

    # a HIGH-relevance hypothesis must justify its priority
    check("HIGH-relevance without priority_reason is flagged",
          any("priority_reason" in p for p in rp.validate_prioritization([{"hypothesis_id": "H3", "behavioral_distance": "DIRECT"}])))
    check("invalid behavioral_distance is flagged",
          any("invalid" in p for p in rp.validate_prioritization([{"hypothesis_id": "H4", "behavioral_distance": "SORTA"}])))

    # gate integration: a DIRECT candidate left unexplored -> RELEVANCE_PRIORITIZATION NEEDS_REVIEW
    # even though a GENERIC one is CONFIRMED (breadth cannot compensate for the direct miss)
    cov = [dict(direct), {"hypothesis_id": "H2", "dimension": "DOWNSTREAM_REGRESSION", "candidate": "c",
                          "reason": "r", "technical_basis": ["t"], "status": "CONFIRMED", "behavioral_distance": "GENERIC_REGRESSION"}]
    cov[0]["dimension"] = "DITA_SEMANTIC_DEPENDENCY"
    cov[0]["reason"] = "r"
    cov[0]["technical_basis"] = ["t"]
    r = coverage_gate_mod.evaluate({"coverage_hypotheses": cov,
                                    "verifications": [{"hypothesis_id": "H2", "verdict": "CONFIRMED", "disposition": "REGRESSION"}]})
    check("unexplored DIRECT dependency blocks the gate via RELEVANCE_PRIORITIZATION",
          r["dimensions"].get("RELEVANCE_PRIORITIZATION") == "NEEDS_REVIEW" and r["semantic_gate"] == "NEEDS_REVIEW")


def test_disposition_classifier() -> None:
    dc = disposition_mod

    # WHAT (observable) is not implementation-level; HOW (internal mechanism) is
    check("observable outcome is not implementation-level",
          dc.is_implementation_level("generation completes SUCCESS and the site navigation shows the grouping node") is False)
    check("class.method reference is implementation-level",
          dc.is_implementation_level("null must be guarded before PathUtils.appendUnixSlash") is True)
    check("camelCase method call is implementation-level",
          dc.is_implementation_level("the null path is not passed into appendUnixSlash()") is True)
    check("naming a property/output alone is not implementation-level",
          dc.is_implementation_level("the guides-navigation property is present and well-formed after each run") is False)

    # an implementation-level statement cannot be an ACCEPTANCE_CONTRACT
    bad = [{"finding_id": "F1", "statement": "null must be guarded before PathUtils.appendUnixSlash", "disposition": "ACCEPTANCE_CONTRACT"}]
    check("impl-level ACCEPTANCE_CONTRACT is rejected", any("describes WHAT" in p for p in dc.validate_dispositions(bad)))
    # ...unless the internal contract itself is the requirement
    ok = [dict(bad[0], internal_contract_is_requirement=True)]
    check("impl-level AC allowed when internal contract IS the requirement", dc.validate_dispositions(ok) == [])
    # the same statement is fine as an IMPLEMENTATION_ORACLE
    oracle = [{"finding_id": "F1", "statement": "null must be guarded before PathUtils.appendUnixSlash", "disposition": "IMPLEMENTATION_ORACLE"}]
    check("impl-level statement is fine as IMPLEMENTATION_ORACLE", dc.validate_dispositions(oracle) == [])
    # an IMPLEMENTATION_ORACLE must not map to an AC
    mapped = [dict(oracle[0], maps_to_ac="AC-03")]
    check("IMPLEMENTATION_ORACLE mapped to an AC is rejected", any("must not map" in p for p in dc.validate_dispositions(mapped)))
    # unknown disposition rejected
    check("unknown disposition rejected", any("must be one of" in p for p in dc.validate_dispositions([{"statement": "x", "disposition": "MAYBE"}])))

    # plan-body scan: an implementation-mechanism AC is flagged; an observable one is not
    bad_plan = ("**Acceptance Criteria**\n"
                "- AC-01 [Confirmed]: (Basic) Given a map | When published | Then the null path is guarded before PathUtils.appendUnixSlash.\n"
                "**Expected Behaviour**\n- x\n")
    check("implementation-mechanism AC in the plan is flagged", any("AC-01" in p for p in dc.check_plan_acceptance_criteria(bad_plan)))
    good_plan = ("**Acceptance Criteria**\n"
                 "- AC-01 [Confirmed]: (Basic) Given a map | When published | Then generation completes SUCCESS and the grouping node appears in the site navigation.\n"
                 "**Expected Behaviour**\n- x\n")
    check("observable AC in the plan is not flagged", dc.check_plan_acceptance_criteria(good_plan) == [])


def test_oracle_builder() -> None:
    ob = oracle_mod

    # classification
    check("observable outcome is a product oracle",
          ob.classify_oracle("the site navigation shows the grouping entry") == "PRIMARY_PRODUCT_ORACLE")
    check("property outcome is a state oracle",
          ob.classify_oracle("the guides-navigation property is well-formed") == "SECONDARY_STATE_ORACLE")
    check("no-exception is a diagnostic signal",
          ob.classify_oracle("no NullPointerException is thrown") == "DIAGNOSTIC_SIGNAL")

    # diagnostic-only detection: "no exception / job success" alone is insufficient
    check("no-exception-only is diagnostic-only", ob.is_diagnostic_only("the job completes successfully with no NullPointerException") is True)
    check("success + observable output is not diagnostic-only",
          ob.is_diagnostic_only("generation succeeds and the navigation shows the grouping entry") is False)
    check("state oracle counts as observable", ob.is_diagnostic_only("no error and the guides-navigation property is intact") is False)
    check(
        "delivery availability is a product-visible oracle when delivery is in scope",
        ob.classify_oracle("the download is available to the author") == "PRIMARY_PRODUCT_ORACLE"
        and ob.is_diagnostic_only("the download is available to the author") is False,
    )
    check(
        "bare internal archive existence remains diagnostic-only",
        ob.is_diagnostic_only("the archive exists") is True,
    )

    # manifest scenario_oracles: a P0/P1 needs a PRIMARY_PRODUCT_ORACLE
    bad = [{"scenario_id": "P0-1", "priority": "P0", "oracles": [{"type": "DIAGNOSTIC_SIGNAL", "statement": "no NPE"}]}]
    check("P0 with only a diagnostic oracle is rejected", any("PRIMARY_PRODUCT_ORACLE" in p for p in ob.validate_scenario_oracles(bad)))
    good = [{"scenario_id": "P0-1", "priority": "P0", "oracles": [
        {"type": "DIAGNOSTIC_SIGNAL", "statement": "no NPE"},
        {"type": "PRIMARY_PRODUCT_ORACLE", "statement": "navigation shows the grouping entry"}]}]
    check("P0 with a product oracle passes", ob.validate_scenario_oracles(good) == [])

    # plan-body scan: a diagnostic-only P0 scenario is flagged; an observable one is not
    bad_plan = ("**Test Scenarios**\n- P0 [AC-01]: publish the map -> the job completes SUCCESS with no NullPointerException.\n"
                "**Known Jira Bugs / Past Similar Tickets**\n- none\n")
    check("diagnostic-only P0 scenario is flagged", any("P0" in p for p in ob.check_plan_scenarios(bad_plan)))
    good_plan = ("**Test Scenarios**\n- P0 [AC-01]: publish the map -> the job succeeds and the site navigation shows the grouping entry with its two child topics.\n"
                 "**Known Jira Bugs / Past Similar Tickets**\n- none\n")
    check("observable P0 scenario is not flagged", ob.check_plan_scenarios(good_plan) == [])


def test_state_compatibility() -> None:
    sc = state_compat_mod

    # activation: a first-run/subsequent-run persisted-state ticket activates
    active_manifest = {"behavior_model": {"trigger": ["publish map"], "operations": ["generate"],
                       "update_paths": ["rewrite state"], "unknowns": ["fails until nodes deleted on subsequent run"]}}
    check("persisted/subsequent-run signals activate the explorer", sc.is_active(active_manifest) is True)
    # a plain stateless UI ticket does not activate
    check("stateless UI ticket does not activate", sc.is_active({"behavior_model": {"trigger": ["click"], "operations": ["open dialog"]}}) is False)
    # remove/recompute paths are a structural signal on their own
    check("remove_paths is a structural activation signal",
          sc.is_active({"behavior_model": {"trigger": ["delete"], "operations": ["x"], "remove_paths": ["remove entry"]}}) is True)

    def block(**over):
        base = {"active": True,
                "states": {o: {"behavior": "described"} for o in sc.STATE_ORIGINS},
                "recovery_of_old_state": {"required": "unknown", "evidence": [], "disposition": "OPEN_QUESTION"}}
        base.update(over)
        return base

    check("well-formed state_compatibility passes", sc.validate_state_compatibility(block()) == [])
    # missing one of the three state origins is flagged
    partial = block(states={"CLEAN_PRE_FIX_STATE": {}, "STATE_CREATED_BY_FIXED_CODE": {}})
    check("missing BUGGY-old state origin is flagged", any("STATE_CREATED_BY_BUGGY_OLD_CODE" in p for p in sc.validate_state_compatibility(partial)))
    # recovery-of-old-state as AC without evidence is rejected
    as_ac = block(recovery_of_old_state={"required": True, "evidence": [], "disposition": "ACCEPTANCE_CONTRACT"})
    check("recovery-of-old-state AC without evidence is rejected", any("without product/engineering evidence" in p for p in sc.validate_state_compatibility(as_ac)))
    # recovery-of-old-state as AC WITH evidence is allowed
    as_ac_ev = block(recovery_of_old_state={"required": True, "evidence": ["eng decision: fix self-heals"], "disposition": "ACCEPTANCE_CONTRACT"})
    check("recovery-of-old-state AC with evidence is allowed", sc.validate_state_compatibility(as_ac_ev) == [])
    # unknown recovery requirement must be an OPEN_QUESTION
    unknown_ac = block(recovery_of_old_state={"required": "unknown", "evidence": [], "disposition": "ACCEPTANCE_CONTRACT"})
    check("unknown recovery requirement forced to OPEN_QUESTION", any("must be OPEN_QUESTION" in p for p in sc.validate_state_compatibility(unknown_ac)))


def test_cross_surface_resolver() -> None:
    cs = cross_surface_mod

    # a comparison baseline (semantic equivalence) is fine as a REFERENCE_ORACLE
    ref = [{"surface": "Native PDF", "impact_class": "SEMANTIC_EQUIVALENCE_ONLY", "role": "REFERENCE_ORACLE"}]
    check("semantic-equivalence surface as REFERENCE_ORACLE passes", cs.validate_cross_surface(ref) == [])

    # ...but semantic equivalence alone cannot make it a REGRESSION_TARGET
    bad = [{"surface": "HTML5", "impact_class": "SEMANTIC_EQUIVALENCE_ONLY", "role": "REGRESSION_TARGET", "evidence": ["shows same semantics"]}]
    check("semantic-equivalence-only REGRESSION_TARGET is rejected", any("not proof of impact" in p for p in cs.validate_cross_surface(bad)))

    # no-evidence-of-impact cannot be a regression target
    none_ev = [{"surface": "DITA-OT PDF", "impact_class": "NO_EVIDENCE_OF_IMPACT", "role": "REGRESSION_TARGET", "evidence": ["x"]}]
    check("no-evidence-of-impact REGRESSION_TARGET is rejected", any("not proof of impact" in p for p in cs.validate_cross_surface(none_ev)))

    # a shared-path surface with evidence is a valid REGRESSION_TARGET
    good = [{"surface": "Legacy AEM Sites", "impact_class": "SHARED_AFFECTED_PATH", "role": "REGRESSION_TARGET", "evidence": ["shares TOC path helper"]}]
    check("shared-path REGRESSION_TARGET with evidence passes", cs.validate_cross_surface(good) == [])
    # ...but the same shared-path target with no evidence is rejected
    good_no_ev = [{"surface": "Legacy AEM Sites", "impact_class": "SHARED_AFFECTED_PATH", "role": "REGRESSION_TARGET", "evidence": []}]
    check("shared-path REGRESSION_TARGET without evidence is rejected", any("must cite evidence" in p for p in cs.validate_cross_surface(good_no_ev)))

    # vocab guards
    check("invalid impact_class rejected", any("impact_class" in p for p in cs.validate_cross_surface([{"surface": "X", "impact_class": "SORTA", "role": "REFERENCE_ORACLE"}])))
    check("invalid role rejected", any("role" in p for p in cs.validate_cross_surface([{"surface": "X", "impact_class": "NO_EVIDENCE_OF_IMPACT", "role": "MAYBE"}])))

    # multi-output signal detection
    check("two+ publishing modes is a multi-output signal",
          cs.multi_output_signal({"behavior_model": {"publishing_modes": ["Native PDF", "New AEM Site"]}}) is True)
    check("single publishing mode is not a multi-output signal",
          cs.multi_output_signal({"behavior_model": {"publishing_modes": ["New AEM Site"]}}) is False)


def test_structural_equivalence() -> None:
    se = struct_equiv_mod
    allchecks = {d: True for d in se.VERIFICATION_DIMENSIONS}

    # fully-verified equivalence may drive regression
    ok = [{"construct_a": "topichead", "construct_b": "topicref", "classification": "EQUIVALENT_PATH",
           "checks": allchecks, "evidence": ["same parser + nav model + transform, product-supported"],
           "disposition": "REGRESSION", "generates_regression": True}]
    check("fully-verified EQUIVALENT_PATH passes", se.validate_structural_equivalence(ok) == [])

    # EQUIVALENT_PATH missing a verified dimension is rejected
    partial_checks = dict(allchecks)
    partial_checks["transformation"] = False
    bad = [{"construct_a": "topichead", "construct_b": "topicref", "classification": "EQUIVALENT_PATH",
            "checks": partial_checks, "evidence": ["x"]}]
    check("EQUIVALENT_PATH with an unverified dimension is rejected", any("requires all verification dimensions" in p for p in se.validate_structural_equivalence(bad)))

    # asserting equivalence without evidence is rejected
    no_ev = [{"construct_a": "a", "construct_b": "b", "classification": "EQUIVALENT_PATH", "checks": allchecks, "evidence": []}]
    check("EQUIVALENT_PATH without evidence is rejected", any("must cite evidence" in p for p in se.validate_structural_equivalence(no_ev)))

    # the GUIDES-53707 case: unverified -> UNKNOWN -> Open Question, no regression
    unknown_ok = [{"construct_a": "topichead", "construct_b": "topicref", "classification": "UNKNOWN",
                   "disposition": "OPEN_QUESTION", "generates_regression": False}]
    check("UNKNOWN equivalence as Open Question passes", se.validate_structural_equivalence(unknown_ok) == [])
    unknown_bad = [{"construct_a": "topichead", "construct_b": "topicref", "classification": "UNKNOWN",
                    "disposition": "REGRESSION", "generates_regression": True}]
    check("UNKNOWN equivalence asserted as regression is rejected",
          any("must be an OPEN_QUESTION" in p or "must not generate regression" in p for p in se.validate_structural_equivalence(unknown_bad)))

    # PARTIALLY_EQUIVALENT needs a verified dimension, evidence, and a stated boundary
    part_ok = [{"construct_a": "a", "construct_b": "b", "classification": "PARTIALLY_EQUIVALENT",
                "checks": {"navigation_model": True}, "evidence": ["same nav model"], "boundary": "transformation differs",
                "generates_regression": True}]
    check("well-formed PARTIALLY_EQUIVALENT passes", se.validate_structural_equivalence(part_ok) == [])
    part_bad = [{"construct_a": "a", "construct_b": "b", "classification": "PARTIALLY_EQUIVALENT",
                 "checks": {"navigation_model": True}, "evidence": ["x"]}]
    check("PARTIALLY_EQUIVALENT without a boundary is rejected", any("must state the boundary" in p for p in se.validate_structural_equivalence(part_bad)))

    # DIFFERENT_PATH cannot generate regression
    diff = [{"construct_a": "a", "construct_b": "b", "classification": "DIFFERENT_PATH", "generates_regression": True}]
    check("DIFFERENT_PATH generating regression is rejected", any("only EQUIVALENT_PATH or a materially relevant" in p for p in se.validate_structural_equivalence(diff)))

    check("invalid classification rejected", any("classification" in p for p in se.validate_structural_equivalence([{"construct_a": "a", "construct_b": "b", "classification": "SAMEISH"}])))


def test_scenario_reducer() -> None:
    sr = scenario_reducer_mod

    def scn(sid, decision, branch, transition, contract, factors=None, representative=True, collapsed_into=None):
        e = {"scenario_id": sid,
             "signature": {"semantic_decision": decision, "implementation_branch": branch,
                           "state_transition": transition, "resulting_contract": contract},
             "distinguishing_factors": factors or [], "representative": representative}
        if collapsed_into:
            e["collapsed_into"] = collapsed_into
        return e

    # two scenarios with the same signature and no distinguishing factor: one rep, one collapsed
    rep = scn("S1", "publish grouping", "fallback branch", "state written", "navigation shows group")
    dup = scn("S2", "publish grouping", "fallback branch", "state written", "navigation shows group",
              representative=False, collapsed_into="S1")
    check("equivalent scenario collapses cleanly", sr.validate_reduction([rep, dup]) == [])
    reps, collapsed = sr.reduce([rep, dup])
    check("reduce keeps one representative", len(reps) == 1 and len(collapsed) == 1)

    # a collapsed scenario whose signature differs from its representative is rejected
    diff = scn("S3", "publish grouping", "LOCKED branch", "state written", "navigation shows group",
               representative=False, collapsed_into="S1")
    check("collapsing across different signatures is rejected", any("signatures differ" in p for p in sr.validate_reduction([rep, diff])))

    # a scenario carrying a distinguishing factor cannot be collapsed
    factored = scn("S4", "publish grouping", "fallback branch", "state written", "navigation shows group",
                   factors=["different_lifecycle_transition"], representative=False, collapsed_into="S1")
    check("scenario with a distinguishing factor cannot be collapsed", any("cannot be collapsed" in p for p in sr.validate_reduction([rep, factored])))
    # ...but it is fine as its own representative
    factored_rep = scn("S4", "publish grouping", "fallback branch", "remove then republish", "navigation updates",
                       factors=["different_lifecycle_transition"], representative=True)
    check("distinguishing scenario is fine as a representative", sr.validate_reduction([rep, factored_rep]) == [])

    # two representatives with identical signature and no distinguishing factor -> redundancy flag
    rep2 = scn("S5", "publish grouping", "fallback branch", "state written", "navigation shows group")
    check("redundant representatives are flagged", any("collapse them" in p for p in sr.validate_reduction([rep, rep2])))

    # signature completeness and factor vocab
    incomplete = {"scenario_id": "S6", "signature": {"semantic_decision": "x"}, "representative": True}
    check("incomplete signature is rejected", any("is required" in p for p in sr.validate_reduction([incomplete])))
    badf = scn("S7", "d", "b", "t", "c", factors=["random"], representative=True)
    check("invalid distinguishing factor is rejected", any("must be one of" in p for p in sr.validate_reduction([badf])))


def test_evidence_authority() -> None:
    ea = authority_mod

    items = [
        {"evidence_id": "E1", "statement": "spec requires X", "status": "CONFIRMED", "authority": "SPECIFICATION_AUTHORITY"},
        {"evidence_id": "E2", "statement": "current code does Y", "status": "IMPLEMENTED", "authority": "IMPLEMENTATION_AUTHORITY"},
        {"evidence_id": "E3", "statement": "old design proposed Z", "status": "SUPERSEDED", "authority": "PRODUCT_REQUIREMENT_AUTHORITY"},
    ]

    # a spec-vs-implementation conflict preserved as an Open Question passes
    oq = {"items": items, "conflicts": [{"between": ["E1", "E2"], "resolution_method": "NONE", "disposition": "OPEN_QUESTION"}]}
    check("spec-vs-impl conflict preserved as Open Question passes", ea.validate_evidence_authority(oq) == [])

    # resolving by recency / similarity is forbidden
    recency = {"items": items, "conflicts": [{"between": ["E1", "E2"], "resolution_method": "LATEST_COMMENT", "disposition": "RESOLVED", "resolved_by": "E2", "note": "newer"}]}
    check("latest-comment resolution is forbidden", any("must not be resolved by recency" in p for p in ea.validate_evidence_authority(recency)))
    sim = {"items": items, "conflicts": [{"between": ["E1", "E2"], "resolution_method": "HIGHEST_SIMILARITY", "disposition": "RESOLVED", "resolved_by": "E1", "note": "closer"}]}
    check("highest-similarity resolution is forbidden", any("forbidden" in p for p in ea.validate_evidence_authority(sim)))

    # a valid explicit resolution passes
    valid = {"items": items, "conflicts": [{"between": ["E1", "E2"], "resolution_method": "EXPLICIT_FINAL_DECISION", "disposition": "RESOLVED", "resolved_by": "E1", "note": "product decided to follow the spec"}]}
    check("explicit-decision resolution passes", ea.validate_evidence_authority(valid) == [])

    # cannot resolve in favour of superseded/rejected evidence
    stale = {"items": items, "conflicts": [{"between": ["E1", "E3"], "resolution_method": "AUTHORITY_ORDERING", "disposition": "RESOLVED", "resolved_by": "E3", "note": "old design"}]}
    check("resolving toward superseded evidence is rejected", any("cannot be the current truth" in p for p in ea.validate_evidence_authority(stale)))

    # a RESOLVED conflict without resolved_by is rejected
    noby = {"items": items, "conflicts": [{"between": ["E1", "E2"], "resolution_method": "AUTHORITY_ORDERING", "disposition": "RESOLVED", "note": "x"}]}
    check("RESOLVED without resolved_by is rejected", any("must state resolved_by" in p for p in ea.validate_evidence_authority(noby)))

    # vocab + reference guards
    check("bad status rejected", any("status" in p for p in ea.validate_evidence_authority({"items": [{"evidence_id": "E9", "statement": "x", "status": "MAYBE", "authority": "SPECIFICATION_AUTHORITY"}]})))
    check("bad authority rejected", any("authority" in p for p in ea.validate_evidence_authority({"items": [{"evidence_id": "E9", "statement": "x", "status": "CONFIRMED", "authority": "VIBES"}]})))
    check("conflict referencing unknown id rejected", any("unknown evidence_id" in p for p in ea.validate_evidence_authority({"items": items, "conflicts": [{"between": ["E1", "E99"], "resolution_method": "NONE", "disposition": "OPEN_QUESTION"}]})))


def test_change_impact() -> None:
    ci = change_impact_mod

    def block(**over):
        base = {"changed": ["PathUtils.appendUnixSlash"], "callers": ["getTocItemUsingMap"],
                "shared_models": ["MapTOCEntry"], "state_paths": {"written": ["guides-navigation"], "read": ["guides-navigation"]},
                "downstream_consumers": ["New AEM Site preset"], "outputs": ["site navigation"],
                "can_affect": ["New AEM Site TOC building"], "cannot_affect": ["Native PDF pipeline"],
                "regression_targets": [{"target": "New AEM Site TOC", "shared_path_evidence": ["shares appendPath helper"]}],
                "tests_exercising_change": ["AemSiteApiIT"],
                "product_contract_considered": True, "semantic_behavior_considered": True}
        base.update(over)
        return base

    check("well-formed change_impact passes", ci.validate_change_impact(block()) == [])
    check("missing changed is rejected", any("changed must list" in p for p in ci.validate_change_impact(block(changed=[]))))
    check("missing cannot_affect is rejected", any("cannot_affect" in p for p in ci.validate_change_impact(block(cannot_affect=[]))))
    check("missing can_affect is rejected", any("can_affect" in p for p in ci.validate_change_impact(block(can_affect=[]))))

    # a regression target without shared-path evidence is rejected
    no_ev = block(regression_targets=[{"target": "HTML5", "shared_path_evidence": []}])
    check("regression target without shared-path evidence is rejected", any("shared_path_evidence" in p for p in ci.validate_change_impact(no_ev)))
    # a regression target also in cannot_affect is a contradiction
    contra = block(cannot_affect=["Native PDF pipeline"], regression_targets=[{"target": "Native PDF pipeline", "shared_path_evidence": ["x"]}])
    check("regression target in cannot_affect is a contradiction", any("contradiction" in p for p in ci.validate_change_impact(contra)))

    # code impact must be combined with product contract + semantic behaviour, not replace them
    check("product_contract_considered false is rejected", any("does not replace the product contract" in p for p in ci.validate_change_impact(block(product_contract_considered=False))))
    check("semantic_behavior_considered false is rejected", any("semantic behaviour" in p for p in ci.validate_change_impact(block(semantic_behavior_considered=False))))

    # change signal detection
    check("change_impact block is a change signal", ci.has_change_signal({"change_impact": block()}) is True)
    check("fix_available flag is a change signal", ci.has_change_signal({"fix_available": True}) is True)
    check("no fix signal without a diff/PR/fix", ci.has_change_signal({"issue": "X"}) is False)


def test_implementation_grounding() -> None:
    ig = impl_grounding_mod

    # activation: a ticket naming a REST/servlet API artifact activates
    api_manifest = {"issue": {"summary": "API to track output generation status",
                    "description": "The /bin/publishlistener servlet operation returns no job id"}}
    check("named API/servlet artifact activates implementation grounding", ig.is_active(api_manifest) is True)
    # a plain UI/DITA ticket does not activate
    check("plain UI ticket does not activate", ig.is_active({"issue": {"summary": "Show a warning dialog on save"}}) is False)

    # asserts_current_behavior: Expected Behaviour claiming what the API does today
    plan_asserting = ("Acceptance Criteria\n- AC-01\nExpected Behaviour\n"
                      "- The /bin/publishlistener endpoint currently returns no job id in its response.")
    check("current-behaviour assertion about an API is detected", ig.asserts_current_behavior(plan_asserting) is True)
    check("no assertion when API not mentioned", ig.asserts_current_behavior("Expected Behaviour\n- The dialog shows a warning.") is False)

    # block validation
    def art(**over):
        base = {"artifact": "/bin/publishlistener GENERATEOUTPUT", "kind": "operation",
                "inspected": True, "evidence": ["PublishOutputService.java:182"], "material": True}
        base.update(over)
        return base

    def block(**over):
        base = {"active": True, "named_artifacts": [art()]}
        base.update(over)
        return base

    check("well-formed implementation_grounding passes", ig.validate_implementation_grounding(block()) == [])
    # a material artifact not inspected is rejected
    check("material artifact not inspected is rejected",
          any("not inspected" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[art(inspected=False)]))))
    # a material artifact without cited evidence is rejected
    check("material artifact without file:line evidence is rejected",
          any("file:line" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[art(evidence=[])]))))
    # a stated ticket premise not verified against code is rejected
    unverified = art(premise="the generate call returns no job id", premise_verified=False)
    check("unverified ticket premise is rejected",
          any("premise_verified" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[unverified]))))
    # a verified premise (recording that code contradicts the ticket) is allowed
    verified = art(premise="the generate call returns no job id", premise_verified=True, premise_holds=False)
    check("verified premise (code contradicts ticket) is allowed", ig.validate_implementation_grounding(block(named_artifacts=[verified])) == [])
    # empty artifact list is rejected
    check("empty named_artifacts is rejected", any("non-empty" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[]))))
    # bad kind is rejected
    check("invalid artifact kind is rejected", any("kind must be one of" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[art(kind="widget")]))))

    # config-key provenance: a reporter/ticket-supplied key must be verified or made an Open Question.
    # (Backported from the dev-copy suite - the validator already enforced this in both
    # copies, but this copy's self-tests never got matching coverage.)
    def cfg(**over):
        return art(artifact="duplicate.uuid.move.old.file", kind="config_key",
                   evidence=["ConfigManager.java:195"], **over)
    check("config_key with verified provenance passes",
          ig.validate_implementation_grounding(block(named_artifacts=[cfg(key_provenance="CODE")])) == [])
    check("config_key UNVERIFIED provenance without OQ is rejected",
          any("UNVERIFIED provenance" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[cfg(key_provenance="REPORTER")]))))
    check("config_key UNVERIFIED provenance with OQ ref passes",
          ig.validate_implementation_grounding(block(named_artifacts=[cfg(key_provenance="REPORTER", verification_open_question_ref="OQ-3")]), open_question_ids=["OQ-3"]) == [])
    check("empty known Open Question set rejects implementation-grounding reference",
          any("not in the plan's open_questions" in p for p in ig.validate_implementation_grounding(
              block(named_artifacts=[cfg(key_provenance="REPORTER", verification_open_question_ref="OQ-3")]),
              open_question_ids=[])))
    check("config_key invalid provenance rejected",
          any("key_provenance must be one of" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[cfg(key_provenance="RUMOR")]))))
    check("config_key missing provenance is review-only, not a validate failure",
          ig.validate_implementation_grounding(block(named_artifacts=[cfg()])) == []
          and ig.config_key_artifacts_missing_provenance(block(named_artifacts=[cfg()])) == ["duplicate.uuid.move.old.file"])

    # premise_holds tri-state: 'unresolved' is allowed only with a premise_note explaining the gap.
    unresolved_no_note = art(premise="friendly names update live", premise_verified=True, premise_holds="unresolved")
    check("premise_holds 'unresolved' without a note is rejected",
          any("premise_note is empty" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[unresolved_no_note]))))
    unresolved_with_note = art(premise="friendly names update live", premise_verified=True, premise_holds="unresolved",
                                premise_note="dependency package source not reachable; searched local clone and GitHub MCP, both absent")
    check("premise_holds 'unresolved' with a note passes",
          ig.validate_implementation_grounding(block(named_artifacts=[unresolved_with_note])) == [])
    bad_holds = art(premise="friendly names update live", premise_verified=True, premise_holds="maybe")
    check("premise_holds invalid string value is rejected",
          any("must be true, false, or 'unresolved'" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[bad_holds]))))

    # dependency_resolution: optional sub-field, validated only when declared.
    dep_ok = art(dependency_resolution={"status": "RESOLVED_LOCAL_CLONE", "external_package": "@rh/jui-app"})
    check("dependency_resolution with valid status passes", ig.validate_implementation_grounding(block(named_artifacts=[dep_ok])) == [])
    dep_bad_status = art(dependency_resolution={"status": "GUESSED"})
    check("dependency_resolution invalid status is rejected",
          any("dependency_resolution.status must be one of" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[dep_bad_status]))))
    dep_unresolved_no_note = art(dependency_resolution={"status": "UNRESOLVED_NO_ACCESS"})
    check("dependency_resolution UNRESOLVED_NO_ACCESS without a note is rejected",
          any("UNRESOLVED_NO_ACCESS but has no 'note'" in p for p in ig.validate_implementation_grounding(block(named_artifacts=[dep_unresolved_no_note]))))
    dep_unresolved_with_note = art(dependency_resolution={
        "status": "UNRESOLVED_NO_ACCESS", "external_package": "@rh/jui-app",
        "note": "no local clone and GitHub MCP unavailable"})
    check("dependency_resolution UNRESOLVED_NO_ACCESS with a note passes",
          ig.validate_implementation_grounding(block(named_artifacts=[dep_unresolved_with_note])) == [])


def test_capability_eligibility() -> None:
    ce = cap_elig_mod
    check("multi-action toolbar activates", ce.is_active({"issue": {"description": "the toolbar shows View source, Edit topics and Share buttons"}}) is True)
    check("single-action ticket does not activate (Case A)", ce.is_active({"issue": {"summary": "fix the export dialog title"}}) is False)

    def term(**o):
        b = {"dimension": "ENTITY_TYPE", "operator": "in", "expected_value": "dita", "evidence_ids": ["E1"], "material": True}
        b.update(o)
        return b

    def cap(name="Cap A", **o):
        b = {"capability": name, "predicate_terms": [term()]}
        b.update(o)
        return b

    def block(**o):
        b = {"active": True, "capabilities": [cap("Cap A"), cap("Cap B", predicate_terms=[term(dimension="METADATA", expected_value="uuid present")])]}
        b.update(o)
        return b

    check("distinct per-capability predicates pass (Case C)", ce.validate_capability_eligibility(block()) == [])
    check("material predicate without evidence rejected",
          any("evidence" in p for p in ce.validate_capability_eligibility(block(capabilities=[cap(predicate_terms=[term(evidence_ids=[])])]))))
    check("invalid predicate dimension rejected",
          any("dimension" in p for p in ce.validate_capability_eligibility(block(capabilities=[cap(predicate_terms=[term(dimension="VIBES")])]))))
    check("empty capabilities rejected", any("non-empty" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": []})))
    grouped_ok = block(shared_predicate_groups=[{"capabilities": ["Cap A", "Cap B"], "shared_predicate": "content type is dita", "evidence": ["E9"]}])
    check("shared predicate group with evidence passes (Case B)", ce.validate_capability_eligibility(grouped_ok) == [])
    grouped_no_ev = block(shared_predicate_groups=[{"capabilities": ["Cap A", "Cap B"], "shared_predicate": "same", "evidence": []}])
    check("shared group without evidence is flagged for review", ce.bundled_groups_without_evidence(grouped_no_ev) == ["Cap A, Cap B"])
    check("group with unknown capability rejected",
          any("not decomposed" in p for p in ce.validate_capability_eligibility(block(shared_predicate_groups=[{"capabilities": ["Cap A", "Cap Z"], "evidence": ["E1"]}]))))
    check("no multiselect -> no selection requirement (Case D)", ce.validate_capability_eligibility(block(), multiselect=False) == [])
    ms_unknown = block(capabilities=[cap(selection_policy="UNKNOWN")])
    check("multiselect UNKNOWN without open question rejected", any("selection_policy" in p for p in ce.validate_capability_eligibility(ms_unknown, multiselect=True)))
    ms_ref = block(capabilities=[cap(selection_policy="UNKNOWN", selection_open_question_ref="OQ-1")])
    check("multiselect UNKNOWN with open-question ref allowed", ce.validate_capability_eligibility(ms_ref, multiselect=True, open_question_ids=["OQ-1"]) == [])
    check("empty known Open Question set rejects capability reference",
          any("not in the plan's open_questions" in p for p in
              ce.validate_capability_eligibility(ms_ref, multiselect=True, open_question_ids=[])))
    coll = block(capabilities=[cap(eligibility_evidence=[{"capability_match": "SEMANTIC_COLLISION", "supports_predicate": True}])])
    check("semantic-collision evidence cannot support predicate", any("SEMANTIC_COLLISION" in p for p in ce.validate_capability_eligibility(coll)))

    # Item 17: behavior_model capabilities[] block validates (optional, per-capability).
    bm_caps = {"trigger": ["open toolbar"], "operations": ["render actions"],
               "capabilities": [{"name": "View source", "inputs": ["asset"], "surfaces": ["ASSET_DETAILS"]},
                                {"name": "Share UUID", "eligibility": ["has uuid"]}]}
    check("behavior_model with capabilities[] validates", behavior_mod.validate_behavior_model(bm_caps) == [])
    check("behavior_model capability missing name rejected",
          any("missing 'name'" in p for p in behavior_mod.validate_behavior_model({"trigger": ["x"], "operations": ["y"], "capabilities": [{"inputs": []}]})))

    # Item 18: a direct capability predicate outranks a historical-similarity item.
    ranked = relevance_mod.prioritize([
        {"relevance_kind": "HISTORICAL_SIMILARITY", "relevance_score": 0.99},
        {"relevance_kind": "CAPABILITY_PREDICATE", "relevance_score": 0.10},
    ])
    check("capability predicate outranks historical similarity (Item 18)", ranked[0]["relevance_kind"] == "CAPABILITY_PREDICATE")

    # Item 19: coverage_gate emits the named capability/scope dimensions and FAILs a hidden scope mismatch.
    gate_ok = coverage_gate_mod.evaluate({"open_questions": ["OQ-1"],
        "capability_eligibility": {"active": True, "capabilities": [{"capability": "A", "predicate_terms": [{"dimension": "ENTITY_TYPE", "evidence_ids": ["E1"], "material": True}]}]},
        "scope_conflict": {"active": True, "problem_threads": [{"thread_id": "T1", "problem_statement": "p", "status": "CONFIRMED"}], "alignment": "FULL_SCOPE_FIX"}})
    check("coverage_gate emits AFFECTED_CAPABILITIES_DECOMPOSED", gate_ok["dimensions"].get("AFFECTED_CAPABILITIES_DECOMPOSED") == "COVERED")
    check("coverage_gate emits JIRA_SCOPE_VS_FIX_RECONCILED", gate_ok["dimensions"].get("JIRA_SCOPE_VS_FIX_RECONCILED") == "COVERED")
    gate_fail = coverage_gate_mod.evaluate({
        "scope_conflict": {"active": True, "problem_threads": [{"thread_id": "T1", "problem_statement": "p", "status": "CONFIRMED"}], "alignment": "PARTIAL_SCOPE_FIX", "open_question_refs": []}})
    check("coverage_gate FAILs a hidden scope mismatch (Item 19)", gate_fail["semantic_gate"] == "FAIL")

    # Entry-point / render-form consistency (responsive direct-button vs overflow-menu).
    def ep_cap(**o):
        b = {"capability": "Insert Keyword", "predicate_terms": [term()],
             "entry_points": [
                 {"form": "DIRECT_BUTTON", "dispatch": "AUTHOR_INSERT_ELEMENT", "evidence_ids": ["E1"]},
                 {"form": "OVERFLOW_MENU", "dispatch": "AUTHOR_INSERT_KEYWORD", "evidence_ids": ["E2"]}],
             "entry_point_consistency": "VERIFIED_SAME", "entry_point_consistency_evidence": ["fix unifies dispatch"]}
        b.update(o)
        return b
    check("entry points with resolved consistency pass", ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap()]}) == [])
    check("multiple entry points without consistency rejected",
          any("entry_point_consistency" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_point_consistency="")]})))
    check("VERIFIED_SAME without evidence rejected",
          any("needs evidence" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_point_consistency_evidence=[])]})))
    ep_open = {"active": True, "capabilities": [ep_cap(
        entry_point_consistency="OPEN_QUESTION",
        entry_point_consistency_evidence=[],
        entry_point_open_question_ref="OQ-7",
    )]}
    check("entry-point Open Question reference passes when declared",
          ce.validate_capability_eligibility(ep_open, open_question_ids=["OQ-7"]) == [])
    check("empty known Open Question set rejects entry-point reference",
          any("not in the plan's open_questions" in p for p in
              ce.validate_capability_eligibility(ep_open, open_question_ids=[])))
    check("invalid entry-point form rejected",
          any("form must be one of" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_points=[{"form": "WIDGET", "evidence_ids": ["E1"]}, {"form": "OVERFLOW_MENU", "evidence_ids": ["E2"]}])]})))
    resp_manifest = {"issue": {"description": "the keyword shows as a direct button at 50% zoom; in the overflow menu it works"}}
    under = ce.entrypoint_underexplored({"capabilities": [{"capability": "Insert Keyword", "predicate_terms": [term()]}]}, resp_manifest)
    check("responsive signals + <2 entry points is under-explored", under == ["Insert Keyword"])
    check("no responsive signals -> not under-explored", ce.entrypoint_underexplored({"capabilities": [{"capability": "X"}]}, {"issue": {"summary": "plain dialog title fix"}}) == [])

    # CONFIG predicate must cite a real config key, not a paraphrased mode name.
    no_key = {"capabilities": [{"capability": "Save under lock", "predicate_terms": [
        {"dimension": "CONFIG", "expected_value": "explicit-lock mode enabled", "evidence_ids": ["Jira AC field"], "material": True}]}]}
    check("CONFIG term without a config key is flagged", ce.config_terms_missing_key(no_key) == ["Save under lock"])
    with_key = {"capabilities": [{"capability": "Save under lock", "predicate_terms": [
        {"dimension": "CONFIG", "expected_value": "xmleditor.autocheckout (Disable edit without locking the file) enabled", "evidence_ids": ["XmlEditorConfig"], "material": True}]}]}
    check("CONFIG term citing xmleditor.autocheckout is not flagged", ce.config_terms_missing_key(with_key) == [])

    # Config PREREQUISITE product decision must be surfaced as an Open Question.
    prereq_cap = {"active": True, "capabilities": [{"capability": "Save under lock", "predicate_terms": [
        {"dimension": "CONFIG", "config_key": "xmleditor.autocheckout", "expected_value": "xmleditor.autocheckout enabled", "evidence_ids": ["XmlEditorConfig"], "material": True, "prerequisite": True}]}]}
    check("CONFIG prerequisite without an open-question ref is rejected",
          any("prerequisite" in p for p in ce.validate_capability_eligibility(prereq_cap)))
    prereq_ok = {"active": True, "capabilities": [{"capability": "Save under lock", "predicate_terms": [
        {"dimension": "CONFIG", "config_key": "xmleditor.autocheckout", "expected_value": "xmleditor.autocheckout enabled", "evidence_ids": ["XmlEditorConfig"], "material": True, "prerequisite": True, "prerequisite_open_question_ref": "OQ-5"}]}]}
    check("CONFIG prerequisite surfaced as an open question passes",
          ce.validate_capability_eligibility(prereq_ok, open_question_ids=["OQ-5"]) == [])


def test_scope_conflict() -> None:
    sc = scope_conflict_mod
    check("fix + multi-problem activates", sc.is_active({"issue": {"description": "the PR fixes the button; also there is a separate font preview problem"}}) is True)
    check("no fix signal does not activate", sc.is_active({"issue": {"summary": "buttons show on wrong assets"}}) is False)
    check(
        "pre-development plan text does not create a false fix-scope conflict",
        sc.is_active(
            {"issue": {"description": "the future fix should cover the button and another problem"}},
            "Lifecycle is Pre-Development UAC; development has not started and no pull request exists.",
        ) is False,
    )

    def thread(**o):
        b = {"thread_id": "T1", "problem_statement": "buttons wrong", "status": "CONFIRMED"}
        b.update(o)
        return b

    def block(**o):
        b = {"active": True, "problem_threads": [thread()], "alignment": "FULL_SCOPE_FIX", "open_question_refs": []}
        b.update(o)
        return b

    check("full alignment passes with no open question (Case E)", sc.validate_scope_conflict(block()) == [])
    check("partial alignment without open question rejected",
          any("surfaced as an Open Question" in p for p in sc.validate_scope_conflict(block(alignment="PARTIAL_SCOPE_FIX"))))
    check("partial alignment with open question passes",
          sc.validate_scope_conflict(block(alignment="PARTIAL_SCOPE_FIX", open_question_refs=["OQ-2"]), open_question_ids=["OQ-2"]) == [])
    check("empty known Open Question set rejects scope-conflict reference",
          any("not present" in p for p in sc.validate_scope_conflict(
              block(alignment="PARTIAL_SCOPE_FIX", open_question_refs=["OQ-2"]),
              open_question_ids=[])))
    check("unresolved_scope_without_open_question detects hidden mismatch",
          sc.unresolved_scope_without_open_question(block(alignment="UNKNOWN_FIX_SCOPE")) is True)
    check("unresolved scope rejects undeclared Open Question reference",
          sc.unresolved_scope_without_open_question(
              block(alignment="PARTIAL_SCOPE_FIX", open_question_refs=["OQ-2"]),
              open_question_ids=[],
          ) is True)
    check("unresolved scope accepts declared Open Question reference",
          sc.unresolved_scope_without_open_question(
              block(alignment="PARTIAL_SCOPE_FIX", open_question_refs=["OQ-2"]),
              open_question_ids=["OQ-2"],
          ) is False)
    check("secondary-defect thread mapped to AC rejected (Case F)",
          any("must NOT map" in p for p in sc.validate_scope_conflict(block(problem_threads=[thread(status="SECONDARY_DEFECT", maps_to_ac=True)]))))
    check("invalid thread status rejected", any("status" in p for p in sc.validate_scope_conflict(block(problem_threads=[thread(status="MAYBE")]))))
    check("invalid alignment rejected", any("alignment" in p for p in sc.validate_scope_conflict(block(alignment="SORTA"))))

    implementation_only_plan = (
        "**Acceptance Criteria**\n"
        "- AC-01 [Proposed]: (Negative) Given a request lacks an identifier | "
        "When the action runs | Then a clear error is shown | "
        "Evidence: commit abcdef1 and implementation diff.\n"
        "**Expected Behaviour**\n- Known."
    )
    candidates = sc.implementation_scope_candidates(implementation_only_plan)
    check(
        "PR-only extra behavior is detected generically",
        [item["ac_ref"] for item in candidates] == ["AC-01"],
    )
    jira_authorized_plan = implementation_only_plan.replace(
        "commit abcdef1 and implementation diff",
        "Jira UAC and commit abcdef1",
    )
    check(
        "Jira-authorized behavior is not treated as implementation-only",
        sc.implementation_scope_candidates(jira_authorized_plan) == [],
    )
    authority_block = {
        "schema_version": sc.IMPLEMENTATION_SCOPE_SCHEMA,
        "items": [
            {
                "ac_ref": "AC-01",
                "decision": "OPEN_QUESTION",
                "open_question_ref": "OQ-01",
            }
        ],
    }
    check(
        "implementation-only AC requires a real scope Open Question",
        any(
            "real open_question_ref" in problem
            for problem in sc.validate_implementation_scope_authority(
                authority_block, candidates=candidates, open_question_ids=set()
            )
        ),
    )
    check(
        "implementation-only Proposed AC passes with a declared scope question",
        sc.validate_implementation_scope_authority(
            authority_block, candidates=candidates, open_question_ids={"OQ-01"}
        )
        == [],
    )
    approved_candidates = [dict(candidates[0], status="Confirmed")]
    approved_block = {
        "schema_version": sc.IMPLEMENTATION_SCOPE_SCHEMA,
        "items": [
            {
                "ac_ref": "AC-01",
                "decision": "PRODUCT_APPROVED",
                "authority_source": "accepted UAC approved by product",
            }
        ],
    }
    check(
        "named product authority can approve implementation-discovered scope",
        sc.validate_implementation_scope_authority(
            approved_block,
            candidates=approved_candidates,
            open_question_ids=set(),
        )
        == [],
    )


def test_pre_uac_critic() -> None:
    cr = critic_mod

    # a clean, fully-reasoned plan: primary + governing dep explored+verified, unresolved
    # surfaced, observable oracle -> PASS
    good_manifest = {
        "behaviour_matters": True,
        "coverage_hypotheses": [{"hypothesis_id": "H1", "dimension": "DITA_SEMANTIC_DEPENDENCY", "candidate": "locktitle governs navtitle",
                                  "reason": "r", "technical_basis": ["setTocItemTitle"], "status": "CONFIRMED",
                                  "behavioral_distance": "DIRECT", "priority_reason": "directly controls the title"}],
        "verifications": [{"hypothesis_id": "H1", "verdict": "CONFIRMED", "supporting_authorities": ["CURRENT_IMPLEMENTATION"],
                            "supporting_evidence": ["E1"], "disposition": "ACCEPTANCE_CRITERION"}],
        "dita_semantics": {"active": True, "relations": [{"source_construct": "locktitle", "target_construct": "navtitle",
                            "relation": "CONTROLS", "dita_version": "1.3", "authority": "DITA_SPEC", "evidence": ["x"],
                            "material": True, "states": ["yes"], "status": "CONFIRMED"}]},
    }
    good_plan = ("**Acceptance Criteria**\n- AC-01 [Confirmed]: (Basic) Given a map | When published | Then the navigation shows the grouping node.\n"
                 "**Test Scenarios**\n- P0 [AC-01]: publish -> the site navigation shows the grouping entry.\n"
                 "**Open Questions**\n- No open questions from current evidence\n")
    r = cr.critique(good_manifest, good_plan)
    check("clean reasoned plan passes the critic", r["verdict"] == "PASS")

    relationship_only = dict(good_manifest)
    relationship_only.pop("coverage_hypotheses", None)
    relationship_only.pop("verifications", None)
    relationship_only["construct_relationships"] = {
        "edges": [
            {
                "relation_type": "CONSUMER",
                "neighbor": "navigation renderer",
            }
        ]
    }
    check(
        "relationship umbrella satisfies breadth exploration in the critic",
        cr.critique(relationship_only, good_plan)["questions"]["only_the_noun"][0]
        == "CLEAN",
    )

    # an unexplored HIGH-relevance dependency (candidate, no verification) -> NEEDS_REFINEMENT (Q3)
    unexplored_cov = [dict(good_manifest["coverage_hypotheses"][0], status="INVESTIGATION_CANDIDATE")]
    nr = dict(good_manifest, coverage_hypotheses=unexplored_cov, verifications=[])
    check("unexplored direct dependency -> NEEDS_REFINEMENT", cr.critique(nr, good_plan)["verdict"] == "NEEDS_REFINEMENT")
    check("Q3 flags the unexplored direct dependency", cr.critique(nr, good_plan)["questions"]["prioritized_direct_first"][0] == "CONCERN")

    # an implementation-detail AC -> NEEDS_REFINEMENT (Q4)
    impl_plan = ("**Acceptance Criteria**\n- AC-01 [Confirmed]: (Basic) Given a map | When published | Then null is guarded before PathUtils.appendUnixSlash.\n"
                 "**Open Questions**\n- No open questions from current evidence\n")
    check("Q4 flags an implementation-detail AC", cr.critique(good_manifest, impl_plan)["questions"]["impl_detail_as_ac"][0] == "CONCERN")

    # a diagnostic-only scenario -> Q10 concern
    diag_plan = ("**Acceptance Criteria**\n- AC-01 [Confirmed]: (Basic) Given a map | When published | Then the navigation shows the group.\n"
                 "**Test Scenarios**\n- P0 [AC-01]: publish -> the job completes SUCCESS with no NullPointerException.\n"
                 "**Open Questions**\n- No open questions from current evidence\n")
    check("Q10 flags a diagnostic-only scenario", cr.critique(good_manifest, diag_plan)["questions"]["scenario_oracles"][0] == "CONCERN")

    # a hidden unresolved verdict -> FAIL (Q8 MISSING)
    hidden = dict(good_manifest, verifications=good_manifest["verifications"] + [
        {"hypothesis_id": "H2", "verdict": "UNRESOLVED", "disposition": "OPEN_QUESTION", "open_question_ref": "OQ-9", "insufficient": True}],
        open_questions=[{"id": "OQ-9", "question": "some unresolved item not written into the plan"}])
    check("hidden unresolved decision -> critic FAIL", cr.critique(hidden, good_plan)["verdict"] == "FAIL")

    # bounded repair: at most one repair pass
    check("first repair pass is allowed", cr.can_repair(0) is True)
    check("second repair pass is refused", cr.can_repair(1) is False)
    check("repair_passes over the limit is rejected", any("bounded limit" in p for p in cr.validate_repair_bound({"critic": {"repair_passes": 2}})))
    check("repair_passes within the limit passes", cr.validate_repair_bound({"critic": {"repair_passes": 1}}) == [])


def test_affected_surface() -> None:
    asf = affected_surface_mod

    def block(**o):
        b = {"active": True, "dimensions": [{
            "name": "uuid_conflict_op", "kind": "OPERATION_ENUM", "source": "ImportServlet.java:124",
            "values": ["OVERWRITE", "MOVE"],
            "coverage": {"OVERWRITE": {"disposition": "COVERED", "ac": "AC-02"},
                         "MOVE": {"disposition": "COVERED", "ac": "AC-05"}}}]}
        b.update(o)
        return b

    check("well-formed affected_surface passes",
          asf.validate_affected_surface(block(), ac_ids={"AC-02", "AC-05"}) == [])
    bad = block()
    bad["dimensions"][0]["coverage"].pop("MOVE")
    check("uncovered enum value is rejected",
          any("no coverage entry" in p for p in asf.validate_affected_surface(bad, ac_ids={"AC-02", "AC-05"})))
    noac = block()
    noac["dimensions"][0]["coverage"]["MOVE"] = {"disposition": "COVERED"}
    check("COVERED without an ac is rejected",
          any("names no acceptance criterion" in p for p in asf.validate_affected_surface(noac, ac_ids={"AC-02", "AC-05"})))
    check("ac not defined in the plan is rejected",
          any("not an AC defined" in p for p in asf.validate_affected_surface(block(), ac_ids={"AC-02"})))
    oos = block()
    oos["dimensions"][0]["coverage"]["MOVE"] = {"disposition": "OUT_OF_SCOPE"}
    check("OUT_OF_SCOPE without a reason is rejected",
          any("no reason" in p for p in asf.validate_affected_surface(oos, ac_ids={"AC-02", "AC-05"})))
    oos2 = block()
    oos2["dimensions"][0]["coverage"]["MOVE"] = {"disposition": "OUT_OF_SCOPE", "reason": "name-conflict only"}
    check("OUT_OF_SCOPE with a reason passes",
          asf.validate_affected_surface(oos2, ac_ids={"AC-02", "AC-05"}) == [])
    open_ref = block()
    open_ref["dimensions"][0]["coverage"]["MOVE"] = {
        "disposition": "OPEN_QUESTION", "open_question_ref": "OQ-01"
    }
    check("empty known Open Question set rejects affected-surface reference",
          any("not in the plan's open_questions" in p for p in asf.validate_affected_surface(
              open_ref, ac_ids={"AC-02", "AC-05"}, open_question_ids=[])))
    bk = block()
    bk["dimensions"][0]["kind"] = "STUFF"
    check("invalid dimension kind is rejected",
          any("kind must be one of" in p for p in asf.validate_affected_surface(bk, ac_ids={"AC-02", "AC-05"})))
    check("empty dimensions is rejected",
          any("non-empty list" in p for p in asf.validate_affected_surface({"active": True, "dimensions": []})))
    grounded = {"behaviour_matters": True, "implementation_grounding": {"active": True, "named_artifacts": [
        {"artifact": "k", "kind": "config_key", "inspected": True, "evidence": ["x"], "material": True}]}}
    check("grounded config_key activates affected-surface", asf.is_active(grounded) is True)
    check("no grounding does not activate affected-surface", asf.is_active({"behaviour_matters": True}) is False)


def test_comment_claims() -> None:
    cc = comment_claim_mod

    check("comment_claims absent is not a failure", cc.validate_comment_claims(None) == [])
    check("comment_claims wrong type is rejected", cc.validate_comment_claims({"a": 1}) == ["comment_claims must be a list"])

    def claim(**o):
        base = {"claim": "there is no DB-mode gate here", "comment_source": "author_rca",
                "verification_status": "VERIFIED_FALSE", "evidence_ids": ["E4"]}
        base.update(o)
        return base

    check("well-formed VERIFIED_FALSE claim passes", cc.validate_comment_claims([claim()]) == [])
    check("missing claim text is rejected",
          any("missing 'claim'" in p for p in cc.validate_comment_claims([claim(claim="")])))
    check("invalid comment_source is rejected",
          any("comment_source must be one of" in p for p in cc.validate_comment_claims([claim(comment_source="hearsay")])))
    check("invalid verification_status is rejected",
          any("verification_status must be one of" in p for p in cc.validate_comment_claims([claim(verification_status="PROBABLY")])))
    check("VERIFIED_TRUE without evidence_ids is rejected",
          any("must cite evidence_ids" in p for p in cc.validate_comment_claims([claim(verification_status="VERIFIED_TRUE", evidence_ids=[])])))
    check("UNVERIFIABLE without open_question_ref is rejected",
          any("open_question_ref" in p for p in cc.validate_comment_claims([claim(verification_status="UNVERIFIABLE", evidence_ids=[])])))
    check("UNVERIFIABLE with a known open_question_ref passes",
          cc.validate_comment_claims([claim(verification_status="UNVERIFIABLE", evidence_ids=[], open_question_ref="OQ-1")], open_question_ids=["OQ-1"]) == [])
    check("UNVERIFIABLE with an unknown open_question_ref is rejected",
          any("is not in the plan's open_questions" in p for p in cc.validate_comment_claims(
              [claim(verification_status="UNVERIFIABLE", evidence_ids=[], open_question_ref="OQ-9")], open_question_ids=["OQ-1"])))
    check("empty known Open Question set rejects comment-claim reference",
          any("is not in the plan's open_questions" in p for p in cc.validate_comment_claims(
              [claim(verification_status="UNVERIFIABLE", evidence_ids=[], open_question_ref="OQ-9")],
              open_question_ids=[])))

    hits = cc.likely_claims_in_comments({"issue": {"comments": [{"body": "there is no gate for this in the code today"}]}})
    check("current-behaviour phrasing is detected in comment text", len(hits) == 1)
    check("plain comment text has no hits", cc.likely_claims_in_comments({"issue": {"comments": [{"body": "looks good to me"}]}}) == [])


def test_pr_supersession() -> None:
    prs = pr_supersession_mod

    check("pr_references absent is not a failure", prs.validate_pr_references(None) == [])
    check("single PR needs no reconciliation",
          prs.validate_pr_references([{"pr_ref": "#8098", "status": "AUTHORITATIVE", "comparison_note": "only PR linked"}]) == [])

    two_prs_unreconciled = [
        {"pr_ref": "#8098", "status": "SUPERSEDED"},
        {"pr_ref": "#8135", "status": "SUPERSEDED"},
    ]
    check("two PRs with no AUTHORITATIVE entry is rejected",
          any("does not mark exactly one AUTHORITATIVE" in p for p in prs.validate_pr_references(two_prs_unreconciled)))

    two_prs_ok = [
        {"pr_ref": "#8098", "status": "SUPERSEDED"},
        {"pr_ref": "#8135", "status": "AUTHORITATIVE",
         "comparison_note": "8135 supersedes 8098 with a full V1+V2 fix; diff --stat shows 8098's files as a subset"},
    ]
    check("two PRs with exactly one AUTHORITATIVE + comparison_note passes", prs.validate_pr_references(two_prs_ok) == [])

    authoritative_no_note = [
        {"pr_ref": "#8098", "status": "SUPERSEDED"},
        {"pr_ref": "#8135", "status": "AUTHORITATIVE"},
    ]
    check("AUTHORITATIVE without comparison_note is rejected",
          any("comparison_note" in p for p in prs.validate_pr_references(authoritative_no_note)))

    unresolved_no_oq = [
        {"pr_ref": "#8098", "status": "UNRESOLVED"},
        {"pr_ref": "#8135", "status": "UNRESOLVED"},
    ]
    check("UNRESOLVED without open_question_ref is rejected",
          any("open_question_ref" in p for p in prs.validate_pr_references(unresolved_no_oq)))
    unresolved_with_oq = [
        {"pr_ref": "#8098", "status": "UNRESOLVED", "open_question_ref": "OQ-1"},
        {"pr_ref": "#8135", "status": "UNRESOLVED", "open_question_ref": "OQ-1"},
    ]
    check("all-UNRESOLVED with a known open_question_ref passes",
          prs.validate_pr_references(unresolved_with_oq, open_question_ids=["OQ-1"]) == [])
    check("empty known Open Question set rejects PR reference",
          any("is not in the plan's open_questions" in p for p in
              prs.validate_pr_references(unresolved_with_oq, open_question_ids=[])))
    check("invalid status is rejected",
          any("status must be one of" in p for p in prs.validate_pr_references([{"pr_ref": "#8098", "status": "MERGED"}])))
    check("missing pr_ref is rejected",
          any("missing 'pr_ref'" in p for p in prs.validate_pr_references([{"status": "AUTHORITATIVE", "comparison_note": "x"}])))


def test_concurrency_race() -> None:
    cr = concurrency_race_mod
    good = {
        "schema_version": cr.SCHEMA_VERSION,
        "active": True,
        "triggers": ["Sling job consumer"],
        "patterns": [
            {"pattern": "CREATE_THEN_DELETE_RACE", "disposition": "COVERED_BY_AC", "ac_ref": "AC-01"},
            {"pattern": "RESTART_MID_PROCESSING_RACE", "disposition": "OPEN_QUESTION", "open_question_ref": "OQ-01"},
            {"pattern": "DUPLICATE_EVENT_RACE", "disposition": "OUT_OF_SCOPE", "reason": "The evidence proves exactly-once dispatch."},
        ],
    }
    check(
        "versioned concurrency race contract passes with real references",
        cr.validate_concurrency_race_analysis(
            good, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}
        ) == [],
    )
    check(
        "empty known AC set rejects a concurrency AC reference",
        any(
            "valid ac_ref" in problem
            for problem in cr.validate_concurrency_race_analysis(
                good, ac_ids=set(), open_question_ids={"OQ-01"}
            )
        ),
    )
    check(
        "inactive concurrency contract requires a reason",
        any(
            "reason" in problem
            for problem in cr.validate_concurrency_race_analysis(
                {"schema_version": cr.SCHEMA_VERSION, "active": False}
            )
        ),
    )
    check(
        "event-driven behavior is detected",
        bool(
            cr.likely_event_driven(
                {"behavior_model": {"operations": ["A Sling job consumer updates content"]}}
            )
        ),
    )


def test_enumerated_coverage() -> None:
    ec = enumerated_coverage_mod
    block = {
        "schema_version": ec.SCHEMA_VERSION,
        "active": True,
        "source_ref": "Jira description GUIDES-100",
        "source_item_count": 3,
        "source_complete": True,
        "items": [
            {"id": "REQ-01", "source_index": 1, "text": "First", "disposition": "COVERED_BY_AC", "ac_refs": ["AC-01"]},
            {"id": "REQ-02", "source_index": 2, "text": "Second", "disposition": "OPEN_QUESTION", "open_question_ref": "OQ-01"},
            {"id": "REQ-03", "source_index": 3, "text": "Third", "disposition": "OUT_OF_SCOPE", "reason": "Explicitly excluded by the accepted scope."},
        ],
    }
    check(
        "complete enumerated source disposition passes",
        ec.validate_enumerated_requirements(
            block, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}, detected_count=3
        ) == [],
    )
    check(
        "empty known Open Question set rejects an enumerated reference",
        any(
            "not declared" in problem
            for problem in ec.validate_enumerated_requirements(
                block, ac_ids={"AC-01"}, open_question_ids=set(), detected_count=3
            )
        ),
    )
    incomplete = json.loads(json.dumps(block))
    incomplete["items"].pop()
    check(
        "missing enumerated source item is a hard failure",
        any(
            "source_item_count" in problem
            for problem in ec.validate_enumerated_requirements(
                incomplete, ac_ids={"AC-01"}, open_question_ids={"OQ-01"}, detected_count=3
            )
        ),
    )
    overloaded = json.loads(json.dumps(block))
    overloaded["items"][1] = {
        "id": "REQ-02", "source_index": 2, "text": "Second",
        "disposition": "COVERED_BY_AC", "ac_refs": ["AC-01"],
    }
    check(
        "independent enumerated items cannot silently overload one AC",
        any(
            "shared_contract_justification" in problem
            for problem in ec.validate_enumerated_requirements(
                overloaded, ac_ids={"AC-01"}, open_question_ids=set(), detected_count=3
            )
        ),
    )
    bullet_issue = {"issue": {"description": "- first\n- second\n- third\n- fourth"}}
    check("ordinary Markdown bullets activate enumerated coverage", ec.likely_enumerated(bullet_issue) == 4)
    inactive = {"schema_version": ec.SCHEMA_VERSION, "active": False, "reason": "No list."}
    check(
        "detected source list cannot be bypassed with active false",
        any(
            "cannot be inactive" in problem
            for problem in ec.validate_enumerated_requirements(inactive, detected_count=4)
        ),
    )


def test_source_requirement_fidelity() -> None:
    srf = source_requirement_fidelity_mod
    first = "Friendly names are a user-level setting for the logged-in user."
    second = (
        "The feature supports any valid conditional attribute added to "
        "/libs/fmdita/config/condAttrList.csv."
    )
    raw_text = f"- {first}\n- {second}"
    source_capture = tempfile.TemporaryDirectory()
    source_artifact = Path(source_capture.name).resolve() / "human-feedback.txt"
    source_artifact.write_bytes(raw_text.encode("utf-8"))
    enumerated = {
        "schema_version": "aem-guides-enumerated-requirements-v1",
        "active": True,
        "source_ref": "pasted human feedback",
        "source_item_count": 2,
        "source_complete": True,
        "items": [
            {
                "id": "REQ-01",
                "source_index": 1,
                "text": first,
                "disposition": "COVERED_BY_AC",
                "ac_refs": ["AC-01"],
            },
            {
                "id": "REQ-02",
                "source_index": 2,
                "text": second,
                "disposition": "COVERED_BY_AC",
                "ac_refs": ["AC-02"],
            },
        ],
    }
    source = {
        "id": "SRC-01",
        "type": "human_feedback",
        "locator": "pasted feedback, first list",
        "raw_text": raw_text,
        "sha256": srf.sha256_text(raw_text),
        "artifact_path": str(source_artifact),
        "artifact_sha256": srf.sha256_bytes(source_artifact.read_bytes()),
    }
    ledger = {
        "schema_version": srf.SCHEMA_VERSION,
        "sources": [source],
        "items": [
            {
                "id": "REQ-01",
                "source_id": "SRC-01",
                "source_index": 1,
                "verbatim_text": first,
                "text": first,
                "authority": "Proposed",
                "disposition": "AC",
                "ac_refs": ["AC-01"],
                "semantic_atoms": [
                    {
                        "id": "ATOM-01",
                        "text": first,
                        "required_terms_all": [
                            "Friendly names",
                            "user-level setting",
                            "logged-in user",
                        ],
                    }
                ],
            },
            {
                "id": "REQ-02",
                "source_id": "SRC-01",
                "source_index": 2,
                "verbatim_text": second,
                "text": second,
                "authority": "Proposed",
                "disposition": "AC",
                "ac_refs": ["AC-02"],
                "semantic_atoms": [
                    {
                        "id": "ATOM-02",
                        "text": second,
                        "required_terms_all": [
                            "any valid conditional attribute",
                            "added",
                            "/libs/fmdita/config/condAttrList.csv",
                        ],
                    }
                ],
            },
        ],
    }
    manifest = {
        "accepted_uac_present": False,
        "enumerated_requirements": enumerated,
        "source_requirement_ledger": ledger,
    }
    full_ac_text = {
        "AC-01": "AC-01 [Proposed]: Friendly names are a user-level setting for the logged-in user.",
        "AC-02": (
            "AC-02 [Proposed]: Any valid conditional attribute added to "
            "/libs/fmdita/config/condAttrList.csv is supported."
        ),
    }

    missing = {
        "accepted_uac_present": False,
        "enumerated_requirements": enumerated,
    }
    check(
        "Proposed-only enumerated source still requires the fidelity ledger",
        any(
            "accepted_uac_present is false" in problem
            for problem in srf.validate_manifest(missing)
        ),
    )

    rewritten = json.loads(json.dumps(manifest))
    rewritten_text = "Friendly names use the active folder-profile mapping."
    rewritten["enumerated_requirements"]["items"][0]["text"] = rewritten_text
    rewritten["source_requirement_ledger"]["items"][0]["text"] = rewritten_text
    check(
        "rewritten enumerated text cannot pass beside the original verbatim source",
        any(
            "must exactly equal verbatim_text" in problem
            for problem in srf.validate_manifest(rewritten)
        ),
    )

    invented_atom = json.loads(json.dumps(manifest))
    invented_atom["source_requirement_ledger"]["items"][0]["semantic_atoms"][0][
        "text"
    ] = "tenant-level setting"
    check(
        "invented semantic atom text is rejected",
        any(
            "atom" in problem and "exact substring" in problem
            for problem in srf.validate_manifest(invented_atom)
        ),
    )

    omitted_scope_atom = json.loads(json.dumps(manifest))
    omitted_scope_atom["source_requirement_ledger"]["items"][0]["semantic_atoms"] = [
        {
            "id": "ATOM-01",
            "text": "Friendly names",
            "required_terms_all": ["Friendly names"],
        }
    ]
    check(
        "automatic scope protection blocks user-level loss even when its atom is omitted",
        any(
            "user-level" in problem and "protected exact" in problem
            for problem in srf.validate_manifest(
                omitted_scope_atom,
                ac_text_by_id={
                    "AC-01": "Friendly names use the active folder-profile mapping.",
                    "AC-02": full_ac_text["AC-02"],
                },
                open_question_text_by_id={},
            )
        ),
    )
    protected_scope, protected_scope_problems = srf._protected_exact(
        "Keep the per-user value and workspace-level fallback.", None
    )
    check(
        "automatic scope protection recognizes per-user and hyphenated level terms",
        protected_scope_problems == []
        and "per-user" in protected_scope
        and "workspace-level" in protected_scope,
    )

    substitution_failures = srf.validate_manifest(
        manifest,
        ac_text_by_id={
            "AC-01": "Friendly names use the active folder-profile mapping.",
            "AC-02": full_ac_text["AC-02"],
        },
        open_question_text_by_id={},
    )
    check(
        "user-level to folder-profile substitution fails semantic fidelity",
        any("logged-in user" in problem for problem in substitution_failures),
    )

    conflict_manifest = json.loads(json.dumps(manifest))
    conflict_atom = conflict_manifest["source_requirement_ledger"]["items"][0][
        "semantic_atoms"
    ][0]
    conflict_atom["evidence_conflict"] = True
    conflict_atom["open_question_ref"] = "OQ-01"
    check(
        "an evidence conflict passes only when a real Open Question preserves the atom",
        srf.validate_manifest(
            conflict_manifest,
            ac_text_by_id=full_ac_text,
            open_question_text_by_id={
                "OQ-01": (
                    "Are friendly names a user-level setting for the logged-in user or the active "
                    "folder profile? QA impact: the answer changes user-isolation coverage."
                )
            },
        )
        == [],
    )

    path_failures = srf.validate_manifest(
        manifest,
        ac_text_by_id={
            "AC-01": full_ac_text["AC-01"],
            "AC-02": "Any valid conditional attribute is supported.",
        },
        open_question_text_by_id={},
    )
    check(
        "dropping an exact configuration path fails fidelity",
        any(
            "/libs/fmdita/config/condAttrList.csv" in problem
            for problem in path_failures
        ),
    )

    bad_hash = json.loads(json.dumps(manifest))
    bad_hash["source_requirement_ledger"]["sources"][0]["sha256"] = "0" * 64
    check(
        "source raw-text hash mismatch fails closed",
        any("does not match" in problem for problem in srf.validate_manifest(bad_hash)),
    )

    check(
        "complete Proposed source ledger passes independently of acceptance authority",
        srf.validate_manifest(
            manifest,
            ac_text_by_id=full_ac_text,
            open_question_text_by_id={},
        )
        == [],
    )

    skill_root = Path(__file__).resolve().parents[1]
    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    checklist_text = (
        skill_root / "references" / "quality-gate-checklist.md"
    ).read_text(encoding="utf-8")
    for marker in (
        "aem-guides-source-requirement-ledger-v1",
        "source_requirement_ledger",
        "accepted_uac_present=false",
    ):
        check(f"skill retains source-fidelity marker {marker}", marker in skill_text)
    check(
        "quality checklist requires source requirement fidelity",
        "Every active enumerated requirement list has a hash-bound source requirement ledger"
        in checklist_text,
    )


def test_ac_decidability() -> None:
    ad = ac_decidability_mod

    def plan(then: str, *, given: str = "an operational run", when: str = "the worker executes", evidence: str = "Jira description GUIDES-100") -> str:
        return (
            "**Acceptance Criteria**\n"
            f"- AC-01 [Proposed]: (Negative) Given {given} | When {when} | Then {then} | Evidence: {evidence}.\n"
            "**Expected Behaviour**\n- The criterion is deterministic.\n"
        )

    failures, notes = ad.evaluate_plan(plan("the limit is applied once agreed"))
    check("unresolved decision marker is a hard AC failure", bool(failures) and notes == [])
    failures, _ = ad.evaluate_plan(plan("after 2 retries the total logs remain bounded"))
    check("unrelated retry number does not make a vague log bound measurable", bool(failures))
    failures, _ = ad.evaluate_plan(plan("the total error log is bounded to 3 entries"))
    check("explicitly bound outcome is decidable", failures == [])
    failures, _ = ad.evaluate_plan(plan("the implementation uses an index, keyset paging, or a custom index"))
    check("implementation-choice menu is a hard AC failure", any("alternative mechanisms" in item for item in failures))
    failures, _ = ad.evaluate_plan(plan("the run reports a failed or aborted result"))
    check("ambiguous terminal result is a hard AC failure", any("ambiguous terminal" in item for item in failures))
    failures, _ = ad.evaluate_plan(plan("the worker does not continue forever"))
    check("non-finite negative is a hard AC failure", any("non-finite" in item for item in failures))
    failures, _ = ad.evaluate_plan(
        plan(
            "the run reports failure",
            evidence="Jira comment says the implementation choice is to be decided GUIDES-100",
        )
    )
    check("unresolved prose in Evidence does not poison parsed behavior fields", failures == [])


def test_operational_contract() -> None:
    oc = operational_contract_mod
    dimensions = [
        {
            "dimension": dimension,
            "disposition": "OUT_OF_SCOPE",
            "reason": f"Evidence-backed exclusion for {dimension}.",
        }
        for dimension in oc.REQUIRED_DIMENSIONS
    ]
    block = {
        "schema_version": oc.SCHEMA_VERSION,
        "active": True,
        "reason": "The issue concerns a restart-sensitive background job.",
        "dimensions": dimensions,
    }
    check(
        "complete operational contract passes",
        oc.validate_operational_contract(
            block, ac_ids=set(), open_question_ids=set(), scenario_ids=set()
        ) == [],
    )
    missing_shutdown = json.loads(json.dumps(block))
    missing_shutdown["dimensions"] = [
        item for item in missing_shutdown["dimensions"]
        if item["dimension"] != "SHUTDOWN_TERMINAL_OUTCOME"
    ]
    check(
        "shutdown must be dispositioned separately from cancellation",
        any(
            "SHUTDOWN_TERMINAL_OUTCOME" in problem
            for problem in oc.validate_operational_contract(
                missing_shutdown, ac_ids=set(), open_question_ids=set(), scenario_ids=set()
            )
        ),
    )
    referenced = json.loads(json.dumps(block))
    referenced["dimensions"][0] = {
        "dimension": "TRIGGER_AND_DEPLOYMENT_SCOPE",
        "disposition": "COVERED_BY_AC",
        "ac_refs": ["AC-99"],
    }
    check(
        "empty AC set rejects invented operational references",
        any(
            "AC-99" in problem
            for problem in oc.validate_operational_contract(
                referenced, ac_ids=set(), open_question_ids=set(), scenario_ids=set()
            )
        ),
    )
    signalled = {"issue": {"description": "A Sling job retries after a partial write."}}
    check(
        "strong operational signal requires the contract",
        any("required" in problem for problem in oc.validate_manifest(signalled)),
    )
    signalled["operational_contract"] = {
        "schema_version": oc.SCHEMA_VERSION,
        "active": False,
        "reason": "Claimed non-operational.",
    }
    check(
        "operational signal cannot be bypassed by active false",
        any("cannot be false" in problem for problem in oc.validate_manifest(signalled)),
    )
    config_activation = {
        "issue": {
            "description": (
                "The supported configuration activation boundary may require "
                "a profile reselect, cache refresh, or service restart."
            )
        },
        "operational_contract": {
            "schema_version": oc.SCHEMA_VERSION,
            "active": False,
            "reason": "This is synchronous configuration activation, not recurring work.",
        },
    }
    check(
        "configuration activation restart does not imply an async operational contract",
        oc.likely_operational(config_activation) == []
        and not any(
            "cannot be false" in problem
            for problem in oc.validate_manifest(config_activation)
        ),
    )
    restart_job = {
        "issue": {
            "description": "A background job must recover after a service restart."
        }
    }
    check(
        "restart remains operational when recurring job evidence is present",
        "restart" in oc.likely_operational(restart_job),
    )


def test_gate_receipt_and_adapter() -> None:
    gate = _load("run_gates_for_receipt_test", "run_gates.py")
    adapter = _load("canonical_runtime_adapter_for_test", "canonical_runtime_adapter.py")
    check(
        "readability REVIEW prevents a postable receipt",
        gate._postability_review_present(
            ["REVIEW ac-readability: AC-01 too long; split into short sentences"]
        ),
    )
    check(
        "scope-authority REVIEW prevents a postable receipt",
        gate._postability_review_present(
            ["REVIEW scope-authority: implementation-only evidence found for AC-01"]
        ),
    )
    check(
        "semantic advisory notes also block posting",
        gate._postability_review_present(["REVIEW feature-classification: inspect"]),
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plan = root / "plan.md"
        combined = root / "combined.md"
        manifest = root / "manifest.json"
        receipt = root / "gate-receipt.json"
        fake_skill = root / "skill"
        (fake_skill / "scripts").mkdir(parents=True)
        (fake_skill / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
        (fake_skill / "scripts" / "gate.py").write_text("PASS = True\n", encoding="utf-8")
        plan.write_text(GOOD_PLAN, encoding="utf-8")
        combined.write_text(GOOD_PLAN, encoding="utf-8")
        manifest.write_text(json.dumps({"issue": "GUIDES-100"}), encoding="utf-8")
        gate.write_gate_receipt(
            receipt_path=str(receipt),
            plan_path=str(plan),
            combined_path=str(combined),
            manifest_path=str(manifest),
            passed=True,
            postable=True,
            skill_root=fake_skill,
        )
        adapter.verify_receipt(
            receipt,
            jira_key="GUIDES-100",
            plan_path=plan,
            manifest_path=manifest,
            skill_root=fake_skill,
        )
        check("hash-bound receipt authorizes the exact current artifacts", True)

        plan.write_text(GOOD_PLAN + "\n", encoding="utf-8")
        try:
            adapter.verify_receipt(
                receipt,
                jira_key="GUIDES-100",
                plan_path=plan,
                manifest_path=manifest,
                skill_root=fake_skill,
            )
        except ValueError as exc:
            check("stale receipt is rejected after plan mutation", "hash mismatch" in str(exc))
        else:
            check("stale receipt is rejected after plan mutation", False)

        plan.write_text(GOOD_PLAN, encoding="utf-8")
        (fake_skill / "scripts" / "gate.py").write_text("PASS = False\n", encoding="utf-8")
        try:
            adapter.verify_receipt(
                receipt,
                jira_key="GUIDES-100",
                plan_path=plan,
                manifest_path=manifest,
                skill_root=fake_skill,
            )
        except ValueError as exc:
            check(
                "stale receipt is rejected after validator mutation",
                "validator fingerprint hash mismatch" in str(exc),
            )
        else:
            check("stale receipt is rejected after validator mutation", False)

        (fake_skill / "scripts" / "gate.py").write_text("PASS = True\n", encoding="utf-8")
        gate.write_gate_receipt(
            receipt_path=str(receipt),
            plan_path=str(plan),
            combined_path=str(combined),
            manifest_path=str(manifest),
            passed=True,
            postable=False,
            skill_root=fake_skill,
        )
        try:
            adapter.verify_receipt(
                receipt,
                jira_key="GUIDES-100",
                plan_path=plan,
                manifest_path=manifest,
                skill_root=fake_skill,
            )
        except ValueError as exc:
            check("skip-self-test style non-postable receipt is rejected", "postable" in str(exc))
        else:
            check("skip-self-test style non-postable receipt is rejected", False)


def _ui_scope_fixture():
    surfaces = [
        "Full Tags View",
        "Condition Attributes panel",
        "Right Panel",
        "condition presets",
        "DITAVAL attribute dropdown",
        "Preview",
    ]
    return {
        "schema_version": "aem-guides-ui-surface-scope-v1",
        "construct_type": "attribute-label",
        "render_surfaces": [
            {"surface": surface, "disposition": "COVERED_BY_AC", "ac_ref": "AC-01"}
            for surface in surfaces
        ],
        "config_scope": {
            "scope": "USER",
            "disposition": "COVERED_BY_AC",
            "ac_ref": "AC-01",
        },
        "upgrade_persistence": {
            "disposition": "COVERED_BY_AC",
            "ac_ref": "AC-01",
        },
        "sibling_regression": {
            "disposition": "COVERED_BY_AC",
            "sibling_construct": "element-label",
            "ac_ref": "AC-01",
        },
        "surfaces_grounding": ["C:/repo/rendering.ts:42"],
    }


def test_feature_class_registry() -> None:
    registry = feature_class_mod
    failures, notes = registry.validate_feature_classification(
        {"issue": {"summary": "ordinary content change"}},
        "ordinary content change",
        ac_ids={"AC-01"},
        open_question_ids=set(),
    )
    check("feature registry cleanly skips without signals", failures == [] and notes == [])

    failures, notes = registry.validate_feature_classification(
        {},
        "A friendly name is shown as a label in workspace settings.",
        ac_ids={"AC-01"},
        open_question_ids=set(),
    )
    check(
        "detected feature class without declaration is REVIEW only",
        failures == [] and any("REVIEW" in note for note in notes),
    )

    missing_dimension = {
        "feature_classification": {
            "schema_version": "aem-guides-feature-classification-v1",
            "classes": ["ui_display_label"],
            "rationale": "The change controls a rendered label.",
            "evidence": ["C:/repo/rendering.ts:42"],
        }
    }
    failures, _ = registry.validate_feature_classification(
        missing_dimension,
        "friendly name label",
        ac_ids={"AC-01"},
        open_question_ids=set(),
    )
    check(
        "declared feature class requires its dimension block",
        any("ui_surface_scope" in problem for problem in failures),
    )

    complete = dict(missing_dimension)
    complete["ui_surface_scope"] = _ui_scope_fixture()
    failures, _ = registry.validate_feature_classification(
        complete,
        "friendly name label",
        ac_ids={"AC-01"},
        open_question_ids=set(),
    )
    check("complete feature class contract passes", failures == [])
    check(
        "every registry dimension has a validator",
        all(
            dimension in registry.DIMENSION_VALIDATORS
            for config in registry.REGISTRY.values()
            for dimension in config["required_dimensions"]
        ),
    )
    check(
        "seeded class-to-dimension mappings stay exact",
        {
            name: config["required_dimensions"]
            for name, config in registry.REGISTRY.items()
        }
        == {
            "ui_display_label": ["ui_surface_scope"],
            "access_control": ["role_provisioning"],
            "async_job": ["concurrency_race_analysis", "terminal_states"],
            "configuration_driven_enumeration": [
                "configuration_enumeration_scope",
            ],
            "generated_artifact_delivery": ["generated_output_contract"],
            "content_identity_lifecycle": ["content_identity_contract"],
        },
    )
    for class_name, signal in (
        ("ui_display_label", "friendly name"),
        ("access_control", "authorization"),
        ("async_job", "sling job"),
        ("configuration_driven_enumeration", "configured attribute"),
        ("generated_artifact_delivery", "download archive"),
        ("content_identity_lifecycle", "latest asset"),
    ):
        check(
            f"registry detects {class_name} from a seeded signal",
            class_name in registry.classify({}, signal),
        )
    check(
        "registry detects plural and inflected UI display-label signals",
        "ui_display_label"
        in registry.classify({}, "Friendly Names are Displayed in the editor."),
    )
    check(
        "ordinary grouping language does not imply access control",
        "access_control"
        not in registry.classify({}, "Group captured log entries by job and map."),
    )
    self_describing_manifest = {
        "operational_contract": {
            "active": False,
            "reason": "This does not change a Sling job or queue.",
        },
        "construct_relationships": {
            "cross_dimensions": {
                "PERMISSIONS": {
                    "applicable": False,
                    "reason": "No authorization branch changes.",
                }
            }
        },
    }
    check(
        "validator decision text cannot self-activate a feature class",
        registry.classify(self_describing_manifest, "A duplicate log entry is removed.")
        == [],
    )


def test_configuration_enumeration_scope() -> None:
    failures = configuration_enumeration_mod.run_self_tests()
    check("configuration enumeration dimensions self-test", failures == [])


def test_relationship_traversal() -> None:
    relationship_traversal_mod.run_self_tests()
    check("relationship traversal umbrella self-test", True)


def test_ui_surface_scope() -> None:
    ui = ui_surface_scope_mod
    good = _ui_scope_fixture()
    failures, _ = ui.validate_ui_surface_scope(
        good, ac_ids={"AC-01"}, open_question_ids=set()
    )
    check("catalog-complete UI surface scope passes", failures == [])

    missing = dict(good)
    missing["render_surfaces"] = good["render_surfaces"][:-1]
    failures, _ = ui.validate_ui_surface_scope(
        missing, ac_ids={"AC-01"}, open_question_ids=set()
    )
    check(
        "missed catalog surface is a hard failure",
        any("Preview" in problem for problem in failures),
    )

    unknown = dict(good)
    unknown["construct_type"] = "new-construct"
    unknown["render_surfaces"] = [good["render_surfaces"][0]]
    failures, notes = ui.validate_ui_surface_scope(
        unknown, ac_ids={"AC-01"}, open_question_ids=set()
    )
    check(
        "unknown construct requests catalog review without failing",
        failures == [] and any("REVIEW" in note for note in notes),
    )

    bad_ref = _ui_scope_fixture()
    bad_ref["render_surfaces"] = [dict(item) for item in bad_ref["render_surfaces"]]
    bad_ref["render_surfaces"][0]["ac_ref"] = "AC-99"
    failures, _ = ui.validate_ui_surface_scope(
        bad_ref, ac_ids={"AC-01"}, open_question_ids=set()
    )
    check("UI surface scope rejects unknown AC references", bool(failures))

    jira_only_grounding = _ui_scope_fixture()
    jira_only_grounding["surfaces_grounding"] = ["Jira: GUIDES-49507"]
    failures, _ = ui.validate_ui_surface_scope(
        jira_only_grounding, ac_ids={"AC-01"}, open_question_ids=set()
    )
    check(
        "UI surface scope rejects Jira-only rendering grounding",
        any("surfaces_grounding" in problem for problem in failures),
    )

    with tempfile.TemporaryDirectory() as directory:
        catalog = Path(directory) / "catalog.json"
        catalog.write_text("{}\n", encoding="utf-8")
        added = ui.add_catalog_surface("topic-title", "Map Preview", catalog_path=catalog)
        repeated = ui.add_catalog_surface("topic-title", "map preview", catalog_path=catalog)
        check("catalog helper is append-only and idempotent", added is True and repeated is False)


def _role_fixture():
    return {
        "schema_version": "aem-guides-role-provisioning-v1",
        "actors": [
            {
                "actor_id": "delegated-admin",
                "label": "delegated admin user",
                "privilege_class": "DELEGATED",
                "grant_groups": ["profile-admins"],
                "withhold_groups": ["system-admins"],
                "auto_added_groups": ["profile-members"],
                "grounding": ["C:/repo/auth.java:20"],
                "maps_to_acs": ["AC-01"],
            },
            {
                "actor_id": "local-administrator",
                "label": "local administrator",
                "privilege_class": "FULL_ADMIN",
                "grant_groups": ["administrators"],
                "withhold_groups": [],
                "auto_added_groups": "none",
                "grounding": ["C:/repo/auth.java:21"],
                "maps_to_acs": ["AC-02"],
            },
            {
                "actor_id": "unauthorized-user",
                "label": "unauthorized user",
                "privilege_class": "NON_ADMIN",
                "grant_groups": ["authors"],
                "withhold_groups": ["profile-admins", "system-admins"],
                "auto_added_groups": "none",
                "grounding": ["C:/repo/auth.java:22"],
                "maps_to_acs": ["AC-03"],
            },
        ],
    }


def test_role_provisioning() -> None:
    roles = role_provisioning_mod
    plan = "\n".join(
        [
            "- AC-01 [Proposed]: (Basic) Given a delegated admin user | When access changes | Then the change persists | Evidence: code.",
            "- AC-02 [Proposed]: (Basic) Given a member of administrators group | When access changes | Then the change persists | Evidence: code.",
            "- AC-03 [Proposed]: (Negative) Given an unauthorized user | When access changes | Then access is denied | Evidence: code.",
        ]
    )
    good = _role_fixture()
    failures = roles.validate_role_provisioning(
        good, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check("grounded three-actor provisioning matrix passes", failures == [])

    missing_privilege = _role_fixture()
    missing_privilege["actors"] = [dict(actor) for actor in missing_privilege["actors"]]
    missing_privilege["actors"][0].pop("privilege_class")
    failures = roles.validate_role_provisioning(
        missing_privilege, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor requires an explicit privilege class",
        any("privilege_class" in problem for problem in failures),
    )

    invalid_privilege = _role_fixture()
    invalid_privilege["actors"] = [dict(actor) for actor in invalid_privilege["actors"]]
    invalid_privilege["actors"][0]["privilege_class"] = "SUPER_ADMIN"
    failures = roles.validate_role_provisioning(
        invalid_privilege, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor rejects an unknown privilege class",
        any("privilege_class" in problem for problem in failures),
    )

    bad_grounding = _role_fixture()
    bad_grounding["actors"] = [dict(actor) for actor in bad_grounding["actors"]]
    bad_grounding["actors"][0]["grounding"] = ["implementation says so"]
    failures = roles.validate_role_provisioning(
        bad_grounding, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor grounding requires a checkable citation",
        any("grounding" in problem for problem in failures),
    )

    jira_only_grounding = _role_fixture()
    jira_only_grounding["actors"] = [
        dict(actor) for actor in jira_only_grounding["actors"]
    ]
    jira_only_grounding["actors"][0]["grounding"] = ["Jira: GUIDES-50144"]
    failures = roles.validate_role_provisioning(
        jira_only_grounding, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor grounding rejects a Jira-only citation",
        any("grounding" in problem for problem in failures),
    )

    missing_withhold = _role_fixture()
    missing_withhold["actors"] = [dict(actor) for actor in missing_withhold["actors"]]
    missing_withhold["actors"][0]["withhold_groups"] = []
    failures = roles.validate_role_provisioning(
        missing_withhold, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "delegated actor requires withheld groups",
        any("withhold_groups" in problem for problem in failures),
    )

    non_admin_without_withhold = _role_fixture()
    non_admin_without_withhold["actors"] = [
        dict(actor) for actor in non_admin_without_withhold["actors"]
    ]
    non_admin_without_withhold["actors"][2]["withhold_groups"] = []
    failures = roles.validate_role_provisioning(
        non_admin_without_withhold,
        ac_ids={"AC-01", "AC-02", "AC-03"},
        plan_text=plan,
    )
    check(
        "non-admin actor requires withheld groups",
        any("withhold_groups" in problem for problem in failures),
    )

    missing_auto = _role_fixture()
    missing_auto["actors"] = [dict(actor) for actor in missing_auto["actors"]]
    missing_auto["actors"][2].pop("auto_added_groups")
    failures = roles.validate_role_provisioning(
        missing_auto, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor requires explicit auto-added group disposition",
        any("auto_added_groups" in problem for problem in failures),
    )

    empty_auto = _role_fixture()
    empty_auto["actors"] = [dict(actor) for actor in empty_auto["actors"]]
    empty_auto["actors"][1]["auto_added_groups"] = []
    failures = roles.validate_role_provisioning(
        empty_auto, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "no automatic group uses explicit none instead of an empty list",
        any("auto_added_groups" in problem for problem in failures),
    )

    unmapped = _role_fixture()
    unmapped["actors"] = [dict(actor) for actor in unmapped["actors"]]
    unmapped["actors"][0]["maps_to_acs"] = ["AC-02"]
    failures = roles.validate_role_provisioning(
        unmapped, ac_ids={"AC-01", "AC-02", "AC-03"}, plan_text=plan
    )
    check(
        "actor named by an AC must map back to that AC",
        any("AC-01" in problem for problem in failures),
    )

    contributor_plan = (
        "- AC-04 [Proposed]: (Negative) Given a contributor | When access changes | "
        "Then access is denied | Evidence: code."
    )
    failures = roles.validate_role_provisioning(
        _role_fixture(),
        ac_ids={"AC-01", "AC-02", "AC-03", "AC-04"},
        plan_text=contributor_plan,
    )
    check(
        "generic contributor actor cannot bypass the provisioning matrix",
        any("AC-04 has no role_provisioning actor" in problem for problem in failures),
    )


def test_terminal_states() -> None:
    terminal = terminal_states_mod
    good = {
        "schema_version": "aem-guides-terminal-states-v1",
        "states": [
            {"state": state, "disposition": "COVERED_BY_AC", "ac_ref": "AC-01"}
            for state in terminal.REQUIRED_STATES
        ],
    }
    check(
        "all terminal states with valid references pass",
        terminal.validate_terminal_states(good, ac_ids={"AC-01"}, open_question_ids=set()) == [],
    )
    missing = dict(good)
    missing["states"] = good["states"][:-1]
    check(
        "missing terminal state fails",
        any(
            "retry_exhausted" in problem
            for problem in terminal.validate_terminal_states(
                missing, ac_ids={"AC-01"}, open_question_ids=set()
            )
        ),
    )
    invalid = dict(good)
    invalid["states"] = [dict(item) for item in good["states"]]
    invalid["states"][0]["ac_ref"] = "AC-99"
    check(
        "terminal state rejects unknown AC reference",
        bool(
            terminal.validate_terminal_states(
                invalid, ac_ids={"AC-01"}, open_question_ids=set()
            )
        ),
    )


def _publishing_semantic_manifest() -> dict:
    manifest = _canonical_semantic_fixture()
    manifest["issue"] = {
        "key": "GUIDES-100",
        "description": (
            "Retain temporary files and provide a download archive after AEM Sites publishing. "
            "The requested behavior produces correct observable output and retains valid prior state."
        ),
    }
    manifest["issue_domains"] = {
        "schema_version": "aem-guides-issue-domains-v1",
        "primary_domain": "PUBLISHING",
        "routes": [
            {
                "domain": "PUBLISHING",
                "status": "ACTIVE",
                "reason": "The requested behavior creates a publishing artifact.",
                "evidence": ["Jira description GUIDES-100"],
            }
        ],
    }
    manifest["publishing_scope"] = _publishing_scope_fixture()
    manifest["generated_output_contract"] = _generated_output_fixture()
    output_ids = generated_output_mod.material_item_ids(manifest["generated_output_contract"])
    manifest["dispositions"].append(
        {
            "finding_id": "CD-GO",
            "statement": "Generated output inventory and output-fidelity oracles are validated.",
            "disposition": "GENERATED_OUTPUT_VALIDATION",
            "source_refs": output_ids,
        }
    )
    return manifest


def _asset_identity_semantic_manifest() -> dict:
    manifest = _canonical_semantic_fixture()
    manifest["issue"] = {
        "key": "GUIDES-100",
        "description": (
            "Publishing a referenced image asset must use the current asset version after update, move, or rename. "
            "The requested behavior produces correct observable output and retains valid prior state."
        ),
    }
    manifest["issue_domains"] = {
        "schema_version": "aem-guides-issue-domains-v1",
        "primary_domain": "ASSETS",
        "routes": [
            {
                "domain": "ASSETS",
                "status": "ACTIVE",
                "reason": "The behavior is controlled by DAM asset identity and lifecycle.",
                "evidence": ["Jira description GUIDES-100"],
            },
            {
                "domain": "PUBLISHING",
                "status": "ACTIVE",
                "reason": "The current asset identity must reach the generated publishing output.",
                "evidence": ["Jira description GUIDES-100"],
            }
        ],
    }
    manifest["publishing_scope"] = _publishing_scope_fixture()
    manifest["generated_output_contract"] = _generated_output_fixture()
    manifest["content_identity_contract"] = _content_identity_fixture()
    output_ids = generated_output_mod.material_item_ids(manifest["generated_output_contract"])
    manifest["dispositions"].append(
        {
            "finding_id": "CD-GO",
            "statement": "Generated output is compared with the current source asset identity.",
            "disposition": "GENERATED_OUTPUT_VALIDATION",
            "source_refs": output_ids,
        }
    )
    identity_ids = content_identity_mod.material_item_ids(manifest["content_identity_contract"])
    manifest["dispositions"].append(
        {
            "finding_id": "CD-CI",
            "statement": "Current content identity is validated across lifecycle operations.",
            "disposition": "LIFECYCLE_COVERAGE",
            "source_refs": identity_ids,
        }
    )
    return manifest


def test_contract_facts_and_integrity() -> None:
    block = _canonical_semantic_fixture()["contract_facts"]
    check(
        "source-bound contract facts validate",
        contract_fact_mod.validate_contract_facts(block, open_question_ids=set()) == [],
    )
    check(
        "contract facts must quote their canonical source exactly",
        any(
            "exact excerpt" in problem
            for problem in contract_fact_mod.validate_contract_facts(
                block,
                open_question_ids=set(),
                source_texts={"Jira description GUIDES-100": "different source text"},
            )
        ),
    )
    check(
        "protected exact source terms survive in their ACs",
        contract_integrity_mod.validate_integrity(block, GOOD_PLAN) == [],
    )
    lost = GOOD_PLAN.replace("correct observable output", "a result")
    check(
        "silently dropped contract wording fails integrity",
        any("silently lost" in p for p in contract_integrity_mod.validate_integrity(block, lost)),
    )
    ambiguous = json.loads(json.dumps(block))
    ambiguous["facts"][0]["integrity"] = "EXPLICITLY_FLAGGED_AS_AMBIGUOUS"
    check(
        "ambiguous contract fact cannot be routed directly to an AC",
        any("ambiguous facts" in p for p in contract_fact_mod.validate_contract_facts(ambiguous)),
    )


def test_issue_domain_routing_and_publishing_scope() -> None:
    manifest = _publishing_semantic_manifest()
    check(
        "publishing evidence activates the publishing domain",
        domain_router_mod.classify(manifest) == ["PUBLISHING"],
    )
    check(
        "inflected publishing, API delivery, and bulk scale activate independent routes",
        domain_router_mod.classify({
            "issue": {
                "description": "Users publish in bulk through APIs, with 2k or 3k documents in one action."
            }
        }) == ["PUBLISHING", "PERFORMANCE", "API"],
    )
    check(
        "published and singular API wording are recognized",
        domain_router_mod.classify({
            "issue": {"description": "Documents are published using an API."}
        }) == ["PUBLISHING", "API"],
    )
    check(
        "negated and explicitly unaffected domains do not self-activate",
        domain_router_mod.classify({
            "issue": {
                "description": "Publishing and performance are not in scope; the output preset is unaffected."
            }
        }) == [],
    )
    check(
        "a negative performance instruction does not activate a performance route",
        domain_router_mod.classify({
            "issue": {"description": "Output generation must not be tested for performance."}
        }) == [],
    )
    check(
        "structured out-of-scope values cannot activate a domain",
        domain_router_mod.classify({
            "issue": {
                "description": "The authoring label changes.",
                "out_of_scope": ["publishing", "API", "bulk performance"],
            }
        }) == ["AUTHORING"],
    )
    check(
        "a positive clause after a negated clause remains discoverable",
        domain_router_mod.classify({
            "issue": {
                "description": "Performance is not affected, but documents are published through APIs."
            }
        }) == ["PUBLISHING", "API"],
    )
    publishing_route = {
        "schema_version": "aem-guides-issue-domains-v1",
        "primary_domain": "PUBLISHING",
        "routes": [{
            "domain": "PUBLISHING", "status": "ACTIVE", "reason": "Publishing is explicit.",
            "evidence": ["ticket description"],
        }],
    }
    check(
        "publishing configuration does not imply a generated-download contract",
        domain_router_mod.required_blocks(publishing_route) == ["publishing_scope"]
        and "GENERATED_OUTPUT" not in domain_router_mod.required_dimensions(publishing_route),
    )
    check(
        "publishing domain and scope validate",
        domain_router_mod.validate_issue_domains(
            manifest["issue_domains"], manifest=manifest, open_question_ids=set()
        ) == []
        and publishing_scope_mod.validate_publishing_scope(
            manifest["publishing_scope"], open_question_ids=set()
        ) == [],
    )
    missing_scope = dict(manifest)
    missing_scope.pop("publishing_scope")
    check(
        "active publishing route requires its scope contract",
        any(
            "publishing_scope" in p
            for p in domain_router_mod.validate_issue_domains(
                missing_scope["issue_domains"], manifest=missing_scope
            )
        ),
    )
    unresolved = json.loads(json.dumps(manifest["publishing_scope"]))
    unresolved["enable_dita_ot_processing"] = "UNRESOLVED"
    check(
        "unresolved DITA-OT state requires an Open Question",
        any(
            "open_question_refs" in p
            for p in publishing_scope_mod.validate_publishing_scope(unresolved)
        ),
    )
    unresolved["open_question_refs"] = ["OQ-99"]
    check(
        "an empty Open Question registry rejects invented references",
        any(
            "undeclared Open Question" in p
            for p in publishing_scope_mod.validate_publishing_scope(
                unresolved, open_question_ids=set()
            )
        ),
    )


def test_behavior_graph_relation_ontology() -> None:
    def graph(relation):
        return {
            "schema_version": "aem-guides-behavior-graph-v1",
            "nodes": [
                {"node_id": "BGN-01", "kind": "PRODUCT_BEHAVIOR", "label": "source", "material": True, "provenance": ["source:1"]},
                {"node_id": "BGN-02", "kind": "PROCESSOR", "label": "target", "material": True, "provenance": ["source:2"]},
            ],
            "edges": [
                {
                    "edge_id": "BGE-01", "source": "BGN-01", "target": "BGN-02",
                    "relation_type": relation, "provenance": ["source:3"],
                    "subject": "ACTUAL_IMPLEMENTATION", "authority": "CURRENT_IMPLEMENTATION",
                    "currentness": "CURRENT", "applicability": "APPLICABLE", "confidence": 0.8,
                    "verification_state": "CONFIRMED", "material": True,
                }
            ],
            "traversal_paths": [{"path_id": "P-01", "edge_refs": ["BGE-01"]}],
        }

    check(
        "every canonical relation family is accepted",
        all(behavior_graph_mod.validate_behavior_graph(graph(rel)) == [] for rel in behavior_graph_mod.RELATION_TYPES),
    )
    inferred = graph("READ_BY")
    inferred["edges"][0]["authority"] = "INFERENCE"
    check(
        "graph inference cannot silently become confirmed",
        any("inference" in p for p in behavior_graph_mod.validate_behavior_graph(inferred)),
    )
    wrong_subject = graph("READ_BY")
    wrong_subject["edges"][0]["subject"] = "UNKNOWN_SUBJECT"
    wrong_subject["edges"][0]["authority"] = "CURRENT_IMPLEMENTATION"
    check(
        "graph authority is validated against a declared subject policy",
        any(
            ".subject must be one of" in p
            for p in behavior_graph_mod.validate_behavior_graph(wrong_subject)
        ),
    )
    fake_provenance = graph("READ_BY")
    check(
        "graph provenance must resolve in the canonical evidence registry",
        any(
            "unknown evidence reference" in p
            for p in behavior_graph_mod.validate_behavior_graph(
                fake_provenance, evidence_ids=set()
            )
        ),
    )
    unresolved_graph = graph("READ_BY")
    unresolved_graph["edges"][0].update({
        "verification_state": "UNRESOLVED", "open_question_ref": "OQ-GHOST",
    })
    check(
        "unresolved graph edges cannot invent Open Question references",
        any(
            "declared open_question_ref" in p
            for p in behavior_graph_mod.validate_behavior_graph(
                unresolved_graph, open_question_ids=set()
            )
        ),
    )
    too_deep = graph("READ_BY")
    too_deep["traversal_paths"][0]["edge_refs"] = ["BGE-01"] * 5
    check(
        "behavior traversal is bounded",
        any("four-hop" in p for p in behavior_graph_mod.validate_behavior_graph(too_deep)),
    )


def test_semantic_closure_required() -> None:
    manifest = _canonical_semantic_fixture()
    run_gates = _load("run_gates_semantic_closure", "run_gates.py")
    check(
        "complete canonical semantic pipeline passes",
        run_gates.validate_canonical_semantic_pipeline(
            manifest, plan_text=GOOD_PLAN, include_plan_checks=True
        ) == [],
    )
    check(
        "behavior model alone cannot pass semantic coverage",
        coverage_gate_mod.evaluate(
            {"behavior_model": {"trigger": ["publish"], "operations": ["generate"]}}
        )["semantic_gate"] == "NEEDS_REVIEW",
    )
    check(
        "complete applicability matrix passes",
        semantic_closure_mod.validate_semantic_closure(
            manifest["semantic_closure"],
            material_entity_ids=["BGN-01"],
            required_dimensions=["DIRECT_CONSUMERS", "NEGATIVE_STATE"],
        ) == [],
    )
    for key in ("contract_facts", "behavior_graph", "semantic_closure"):
        malformed = json.loads(json.dumps(manifest))
        malformed[key] = []
        check(
            f"wrong-typed {key} fails gracefully",
            isinstance(
                run_gates.validate_canonical_semantic_pipeline(malformed), list
            ),
        )
    incomplete = json.loads(json.dumps(manifest["semantic_closure"]))
    incomplete["records"] = incomplete["records"][:-1]
    check(
        "a silently omitted semantic dimension fails",
        any(
            "silently omits" in p
            for p in semantic_closure_mod.validate_semantic_closure(
                incomplete, material_entity_ids=["BGN-01"]
            )
        ),
    )
    wildcard = json.loads(json.dumps(manifest["semantic_closure"]))
    wildcard["records"][0]["entity_ref"] = "*"
    check(
        "wildcard closure cannot hide per-entity applicability gaps",
        any(
            "is not accepted" in p
            for p in semantic_closure_mod.validate_semantic_closure(
                wildcard, material_entity_ids=["BGN-01"]
            )
        ),
    )


def test_missing_question_directed_retrieval_by_subject() -> None:
    manifest = _canonical_semantic_fixture()
    record = manifest["semantic_closure"]["records"][0]
    record.update(
        {
            "applicability": "UNRESOLVED",
            "status": "UNRESOLVED_AND_EXPOSED",
            "open_question_ref": "OQ-01",
        }
    )
    record.pop("disposition_ref")
    manifest["open_questions"] = [
        {"id": "OQ-01", "question": "What is the intended product behavior?", "qa_impact": "Changes the expected result."}
    ]
    check(
        "unresolved closure automatically requires a question",
        any("did not generate" in p for p in mq_mod.validate_required_questions(manifest)),
    )
    stub = mq_mod.derive_missing_question_stubs(manifest)[0]
    check(
        "missing-question stub preserves subject, dimension, and visible Open Question",
        stub["subject"] == "PRODUCT_CONTRACT"
        and stub["dimension"] == record["dimension"]
        and stub["open_question_ref"] == "OQ-01",
    )
    manifest["missing_questions"] = [
        {
            "question_id": "MQ-01", "question": "What is the intended product behavior?",
            "why_it_matters": "It changes the acceptance oracle.", "preferred_sources": ["linked jira"],
            "search_concepts": ["approved intended behavior"], "blocking": True,
            "material": True, "source_ref": record["closure_id"], "subject": "PRODUCT_CONTRACT",
            "dimension": record["dimension"], "open_question_ref": "OQ-01",
            "if_unresolved": "OPEN_QUESTION",
        }
    ]
    manifest["evidence_lifecycle"] = [
        {"evidence_id": "E-01", "source": "linked jira", "query": "original ticket keywords", "pass": "initial", "status": "INSPECTED", "question_id": ""},
        {"evidence_id": "E-02", "source": "linked jira", "query": "approved intended behavior", "pass": "second", "status": "REJECTED", "question_id": "MQ-01"},
    ]
    check("generated material question is linked", mq_mod.validate_required_questions(manifest) == [])
    check(
        "directed subject-specific retrieval is recorded even when no answer is found",
        mq_mod.check_retrieval_discipline(
            manifest["missing_questions"], manifest["evidence_lifecycle"]
        ) == [],
    )


def test_coverage_disposition_completeness() -> None:
    base = {"dispositions": []}
    check(
        "undispositioned material candidate fails",
        any(
            "no coverage disposition" in p
            for p in behavioral_completeness_mod.validate_behavioral_completeness(
                base, material_item_ids=["CF-01"]
            )
        ),
    )
    one = {
        "dispositions": [
            {"finding_id": "CD-01", "statement": "covered", "disposition": "TECHNICAL_NOTE", "source_refs": ["CF-01"]}
        ]
    }
    check(
        "exactly-once disposition passes",
        behavioral_completeness_mod.validate_behavioral_completeness(
            one, material_item_ids=["CF-01"]
        ) == [],
    )
    duplicate = json.loads(json.dumps(one))
    duplicate["dispositions"].append(
        {"finding_id": "CD-02", "statement": "again", "disposition": "TECHNICAL_NOTE", "source_refs": ["CF-01"]}
    )
    check(
        "duplicate disposition fails",
        any(
            "more than once" in p
            for p in behavioral_completeness_mod.validate_behavioral_completeness(
                duplicate, material_item_ids=["CF-01"]
            )
        ),
    )


def test_acceptance_promotion_authority() -> None:
    manifest = _canonical_semantic_fixture()
    record = manifest["acceptance_promotions"]["records"][0]
    block = {"schema_version": "aem-guides-acceptance-promotions-v1", "records": [record]}
    kwargs = {
        "ac_ids": {"AC-01"}, "known_candidate_ids": {"CF-01"},
        "contract_fact_ids": {"CF-01"},
        "candidate_authorities": {"CF-01": {"JIRA_EXPECTED_BEHAVIOR"}},
        "candidate_subjects": {"CF-01": "PRODUCT_CONTRACT"},
        "dispositions": [manifest["dispositions"][0]],
        "ac_status_by_id": {"AC-01": "Proposed"},
        "accepted_uac_present": False,
    }
    check(
        "Jira expected behavior can support a Proposed AC",
        acceptance_promotion_mod.validate_acceptance_promotions(block, **kwargs) == [],
    )
    code_only = json.loads(json.dumps(block))
    code_only["records"][0]["intended_behavior_authorities"] = ["PR_IMPLEMENTATION"]
    check(
        "PR implementation alone cannot promote an AC",
        any("cannot authorize" in p for p in acceptance_promotion_mod.validate_acceptance_promotions(code_only, **kwargs)),
    )
    regression = json.loads(json.dumps(block))
    regression["records"][0]["regression_only"] = True
    check(
        "regression-only candidate cannot promote",
        any("regression-only" in p for p in acceptance_promotion_mod.validate_acceptance_promotions(regression, **kwargs)),
    )
    duplicate = json.loads(json.dumps(block))
    duplicate_record = json.loads(json.dumps(record))
    duplicate_record["promotion_id"] = "AP-02"
    duplicate["records"].append(duplicate_record)
    check(
        "a candidate and AC cannot be promoted more than once",
        any(
            "promoted more than once" in p
            for p in acceptance_promotion_mod.validate_acceptance_promotions(
                duplicate, **kwargs
            )
        ),
    )
    unbound_authority = json.loads(json.dumps(block))
    unbound_authority["records"][0]["intended_behavior_authorities"] = [
        "APPROVED_PRODUCT_DECISION"
    ]
    check(
        "a promotion cannot borrow authority from another candidate",
        any(
            "not bound to candidate" in p
            for p in acceptance_promotion_mod.validate_acceptance_promotions(
                unbound_authority, **kwargs
            )
        ),
    )
    wrong_candidate_subject_kwargs = dict(kwargs)
    wrong_candidate_subject_kwargs["candidate_subjects"] = {
        "CF-01": "ACTUAL_IMPLEMENTATION"
    }
    check(
        "product acceptance cannot relabel an implementation candidate",
        any(
            "does not match candidate" in p
            for p in acceptance_promotion_mod.validate_acceptance_promotions(
                block, **wrong_candidate_subject_kwargs
            )
        ),
    )
    wrong_disposition = json.loads(json.dumps(block))
    wrong_disposition["records"][0]["disposition_ref"] = "CD-02"
    wrong_disposition_kwargs = dict(kwargs)
    wrong_disposition_kwargs["dispositions"] = manifest["dispositions"][:2]
    check(
        "promotion disposition must cover the same candidate and AC",
        any(
            "does not cover candidate" in p or "different AC" in p
            for p in acceptance_promotion_mod.validate_acceptance_promotions(
                wrong_disposition, **wrong_disposition_kwargs
            )
        ),
    )
    unaccepted_confirmed = json.loads(json.dumps(block))
    unaccepted_confirmed["records"][0].update({
        "decision": "PROMOTED_CONFIRMED",
        "disposition": "ACCEPTANCE_CONTRACT",
        "intended_behavior_authorities": ["HUMAN_ACCEPTED_AC"],
    })
    confirmed_disposition = json.loads(json.dumps(manifest["dispositions"][0]))
    confirmed_disposition["disposition"] = "ACCEPTANCE_CONTRACT"
    confirmed_kwargs = dict(kwargs)
    confirmed_kwargs.update({
        "candidate_authorities": {"CF-01": {"HUMAN_ACCEPTED_AC"}},
        "dispositions": [confirmed_disposition],
        "ac_status_by_id": {"AC-01": "Confirmed"},
        "accepted_uac_present": False,
    })
    check(
        "Confirmed promotion requires an accepted UAC contract",
        any(
            "accepted_uac_present=true" in p
            for p in acceptance_promotion_mod.validate_acceptance_promotions(
                unaccepted_confirmed, **confirmed_kwargs
            )
        ),
    )


def test_generated_output_contract() -> None:
    good = _generated_output_fixture()
    check(
        "complete generated-output contract passes",
        generated_output_mod.validate_generated_output_contract(good) == [],
    )
    legacy = json.loads(json.dumps(good))
    legacy["schema_version"] = "aem-guides-generated-output-contract-v1"
    legacy.pop("delivery_in_scope")
    legacy["oracles"] = [
        oracle for oracle in legacy["oracles"]
        if oracle["oracle_type"] != "DELIVERY_AVAILABLE"
    ]
    check(
        "legacy v1 generated-output contracts remain readable",
        generated_output_mod.validate_generated_output_contract(legacy) == [],
    )
    delivery_out = json.loads(json.dumps(good))
    delivery_out["delivery_in_scope"] = False
    delivery_out.pop("download_surface")
    delivery_out_oracle = next(
        oracle for oracle in delivery_out["oracles"]
        if oracle["oracle_type"] == "DELIVERY_AVAILABLE"
    )
    delivery_out_oracle.update({
        "applicability": "NOT_APPLICABLE",
        "status": "INVESTIGATED_AND_REJECTED",
        "expected": "Delivery is outside the source-backed scope.",
    })
    check(
        "delivery availability is not required when delivery is out of scope",
        generated_output_mod.validate_generated_output_contract(delivery_out) == [],
    )
    mismatched_delivery = json.loads(json.dumps(good))
    mismatched_delivery["delivery_in_scope"] = False
    check(
        "an out-of-scope delivery cannot retain a covered availability oracle",
        any(
            "DELIVERY_AVAILABLE must follow" in p
            for p in generated_output_mod.validate_generated_output_contract(
                mismatched_delivery
            )
        ),
    )
    missing_delivery_surface = json.loads(json.dumps(good))
    missing_delivery_surface.pop("download_surface")
    check(
        "in-scope delivery requires its real delivery surface",
        any(
            "requires a download_surface" in p
            for p in generated_output_mod.validate_generated_output_contract(
                missing_delivery_surface
            )
        ),
    )
    unresolved_delivery = json.loads(json.dumps(good))
    unresolved_delivery["delivery_in_scope"] = "UNRESOLVED"
    unresolved_delivery["delivery_scope_open_question_ref"] = "OQ-GHOST"
    unresolved_delivery_oracle = next(
        oracle for oracle in unresolved_delivery["oracles"]
        if oracle["oracle_type"] == "DELIVERY_AVAILABLE"
    )
    unresolved_delivery_oracle.update({
        "applicability": "UNRESOLVED",
        "status": "UNRESOLVED_AND_EXPOSED",
        "open_question_ref": "OQ-GHOST",
    })
    check(
        "unresolved delivery cannot invent an Open Question",
        any(
            "declared" in p
            for p in generated_output_mod.validate_generated_output_contract(
                unresolved_delivery, open_question_ids=set()
            )
        ),
    )
    split_delivery_question = json.loads(json.dumps(unresolved_delivery))
    split_delivery_question["delivery_scope_open_question_ref"] = "OQ-01"
    split_delivery_question_oracle = next(
        oracle for oracle in split_delivery_question["oracles"]
        if oracle["oracle_type"] == "DELIVERY_AVAILABLE"
    )
    split_delivery_question_oracle["open_question_ref"] = "OQ-02"
    check(
        "delivery scope and availability cannot point to different questions",
        any(
            "same Open Question" in p
            for p in generated_output_mod.validate_generated_output_contract(
                split_delivery_question, open_question_ids={"OQ-01", "OQ-02"}
            )
        ),
    )
    logs_only = json.loads(json.dumps(good))
    logs_only["payload_inventory"] = [
        {"item_id": "GOI-01", "item": "generation log", "role": "DIAGNOSTIC", "disposition": "INCLUDED"}
    ]
    check(
        "logs-only archive is not accepted as generated output",
        any("PRIMARY_CONTENT" in p for p in generated_output_mod.validate_generated_output_contract(logs_only)),
    )
    existence_only = json.loads(json.dumps(good))
    existence_only["oracles"] = [existence_only["oracles"][0]]
    check(
        "artifact-existence-only coverage fails",
        any("CONTENT_CORRECT" in p for p in generated_output_mod.validate_generated_output_contract(existence_only)),
    )
    check("archive-exists text is not a sufficient product oracle", oracle_mod.is_diagnostic_only("the archive exists"))


def test_generated_artifact_delivery_regression() -> None:
    manifest = _publishing_semantic_manifest()
    manifest["generated_output_contract"]["payload_inventory"] = [
        {"item_id": "GOI-01", "item": "generation logs", "role": "DIAGNOSTIC", "disposition": "INCLUDED"}
    ]
    run_gates = _load("run_gates_generated_artifact", "run_gates.py")
    problems = run_gates.validate_canonical_semantic_pipeline(manifest)
    check(
        "generated-artifact contract rejects a logs-only downloadable archive",
        any("PRIMARY_CONTENT" in p for p in problems),
    )


def test_content_identity_lifecycle_regression() -> None:
    good = _asset_identity_semantic_manifest()
    check(
        "current-identity lifecycle contract passes",
        content_identity_mod.validate_content_identity_contract(good["content_identity_contract"]) == [],
    )
    stale_fallback = json.loads(json.dumps(good))
    stale_fallback["content_identity_contract"]["fallback_policy"] = "APPROVED_FALLBACK"
    stale_fallback["content_identity_contract"].pop("fallback_authority", None)
    run_gates = _load("run_gates_content_identity", "run_gates.py")
    problems = run_gates.validate_canonical_semantic_pipeline(stale_fallback)
    check(
        "content-identity contract rejects an unauthorized previous-version fallback",
        any("fallback_authority" in p for p in problems),
    )
    invented_migration = json.loads(json.dumps(good["content_identity_contract"]))
    invented_migration["migration_behavior"] = "MIGRATE"
    check(
        "legacy migration cannot be invented without authority",
        any("migration_authority" in p for p in content_identity_mod.validate_content_identity_contract(invented_migration)),
    )


def test_postability_semantic_reviews() -> None:
    run_gates = _load("run_gates_postability", "run_gates.py")
    check(
        "every semantic REVIEW blocks posting",
        run_gates._postability_review_present(
            ["REVIEW feature-classification: generated artifact class is undeclared"]
        ) is True,
    )


def test_fluffyjaws_evidence() -> None:
    fj = fluffyjaws_evidence_mod

    # Backward-compatible: absent block is a clean pass.
    check("absent fluffyjaws block passes", fj.validate_block({}) == [])

    # Flag-gated probe defaults to disabled + unavailable.
    default_probe = fj.probe(env={})
    check(
        "probe defaults to DISABLED/unavailable",
        default_probe == {"mode": "FLUFFYJAWS_DISABLED", "available": False},
    )
    shadow_probe = fj.probe(env={"SKILL_FLUFFYJAWS_MODE": "FLUFFYJAWS_SHADOW"})
    check(
        "probe never reports available without an injected transport",
        shadow_probe["mode"] == "FLUFFYJAWS_SHADOW" and shadow_probe["available"] is False,
    )

    # Disabled/unavailable with discoveries is rejected.
    disabled_with_ev = {
        "fluffyjaws": {
            "mode": "FLUFFYJAWS_DISABLED",
            "available": False,
            "discoveries": [
                {"query": "q", "authority": "SUPPORTING_DISCOVERY", "regrounded_evidence_id": "E1"}
            ],
        },
        "evidence_authority": {"items": [
            {"evidence_id": "E1", "statement": "s", "status": "CONFIRMED", "authority": "SPECIFICATION_AUTHORITY"}
        ]},
    }
    check(
        "discoveries while disabled are rejected",
        any("DISABLED/unavailable" in p for p in fj.validate_block(disabled_with_ev)),
    )

    # A grounded shadow discovery that re-grounds into a first-class source passes.
    good = {
        "fluffyjaws": {
            "mode": "FLUFFYJAWS_SHADOW",
            "available": True,
            "discoveries": [
                {"query": "native pdf file properties", "authority": "SUPPORTING_DISCOVERY", "regrounded_evidence_id": "E1"}
            ],
        },
        "evidence_authority": {"items": [
            {"evidence_id": "E1", "statement": "s", "status": "CONFIRMED", "authority": "PRODUCT_REQUIREMENT_AUTHORITY"}
        ]},
    }
    check("grounded shadow discovery passes", fj.validate_block(good) == [])

    # Non-supporting authority is rejected.
    bad_auth = {
        "fluffyjaws": {"mode": "FLUFFYJAWS_SHADOW", "available": True, "discoveries": [
            {"query": "q", "authority": "SPECIFICATION_AUTHORITY", "regrounded_evidence_id": "E1"}
        ]},
        "evidence_authority": {"items": [
            {"evidence_id": "E1", "statement": "s", "status": "CONFIRMED", "authority": "SPECIFICATION_AUTHORITY"}
        ]},
    }
    check(
        "FluffyJaws cannot claim a first-class authority",
        any("SUPPORTING_DISCOVERY" in p for p in fj.validate_block(bad_auth)),
    )

    # Missing / non-authoritative re-grounding is rejected.
    ungrounded = {
        "fluffyjaws": {"mode": "FLUFFYJAWS_SHADOW", "available": True, "discoveries": [
            {"query": "q", "authority": "SUPPORTING_DISCOVERY"}
        ]},
        "evidence_authority": {"items": []},
    }
    check(
        "discovery without re-grounding is rejected",
        any("regrounded_evidence_id" in p for p in fj.validate_block(ungrounded)),
    )

    # Direct AC promotion is rejected.
    promotes = {
        "fluffyjaws": {"mode": "FLUFFYJAWS_SHADOW", "available": True, "discoveries": [
            {"query": "q", "authority": "SUPPORTING_DISCOVERY", "regrounded_evidence_id": "E1", "promotes_ac": True}
        ]},
        "evidence_authority": {"items": [
            {"evidence_id": "E1", "statement": "s", "status": "CONFIRMED", "authority": "IMPLEMENTATION_AUTHORITY"}
        ]},
    }
    check(
        "no FluffyJaws -> AC promotion path",
        any("promotes_ac" in p for p in fj.validate_block(promotes)),
    )

    print("test_fluffyjaws_evidence: OK")


def test_temporal_evidence() -> None:
    te = temporal_evidence_mod

    # Backward-compatible: no temporal metadata -> clean pass.
    check("absent temporal metadata passes", te.validate({}) == [])
    check("empty manifest not flagged present", te.is_present({}) is False)

    # Invalid state rejected.
    bad_state = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "MAYBE"}
    ]}}
    check("invalid temporal state rejected",
          any("must be one of" in p for p in te.validate(bad_state)))

    # UNKNOWN_VERSION supporting an AC without safe disposition is rejected.
    unknown_ac = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "UNKNOWN_VERSION",
         "supports_ac": True}
    ]}}
    check("UNKNOWN_VERSION cannot silently support an AC",
          any("cannot silently support" in p for p in te.validate(unknown_ac)))

    # Same, but dispositioned as NEEDS_CURRENT_VERIFICATION -> passes.
    unknown_ok = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "UNKNOWN_VERSION",
         "supports_ac": True, "disposition": "NEEDS_CURRENT_VERIFICATION"}
    ]}}
    check("unknown-version claim is safe when dispositioned", te.validate(unknown_ok) == [])

    # CURRENTLY_APPLICABLE supporting an AC -> passes.
    current_ok = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "CURRENTLY_APPLICABLE",
         "supports_ac": True}
    ]}}
    check("currently-applicable evidence may support an AC", te.validate(current_ok) == [])

    # SUPERSEDED must name what supersedes it.
    superseded_bare = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "SUPERSEDED"}
    ]}}
    check("SUPERSEDED must record superseded_by/conflict_with",
          any("superseded_by/conflict_with" in p for p in te.validate(superseded_bare)))

    # Normative authority must not be marked SUPERSEDED by recency alone.
    normative_superseded = {"evidence_authority": {"items": [
        {"evidence_id": "E1", "temporal_applicability": "SUPERSEDED",
         "superseded_by": "E2", "authority_is_normative": True}
    ]}}
    check("normative record not superseded by recency alone",
          any("recency alone" in p for p in te.validate(normative_superseded)))

    # Version conflict must be preserved with two records + applicability.
    conflict_bad = {"temporal_evidence": {"version_conflicts": [{"between": ["E1"]}]}}
    check("version conflict must preserve both records",
          any("at least two evidence_ids" in p for p in te.validate(conflict_bad)))

    conflict_ok = {"temporal_evidence": {"version_conflicts": [
        {"between": ["E1", "E2"], "applicability": "VERSION_MISMATCH"}
    ]}}
    check("marked version conflict passes", te.validate(conflict_ok) == [])

    print("test_temporal_evidence: OK")


def test_evidence_conflict_resolver() -> None:
    cr = evidence_conflict_resolver_mod

    # Backward-compatible: absent block passes.
    check("absent conflict_resolution passes", cr.validate({}) == [])

    def wrap(conflict):
        return {"conflict_resolution": {"conflicts": [conflict]}}

    base = {
        "claim_id": "C1", "normalized_claim": "x",
        "supporting_evidence_ids": ["E1"], "conflicting_evidence_ids": ["E2"],
    }

    # Invalid conflict type / resolution rejected.
    bad_type = dict(base, conflict_type="NOPE", resolution="UNRESOLVED", question_type="GENERAL")
    check("invalid conflict_type rejected", any("conflict_type" in p for p in cr.validate(wrap(bad_type))))

    # INVARIANT 1: code-vs-doc resolving in favor of implementation is rejected.
    code_wins = dict(base, conflict_type="PRODUCT_DOC_VS_CODE",
                     resolution="RESOLVED_BY_HIGHER_AUTHORITY",
                     winning_authority="VERIFIED_CURRENT_IMPLEMENTATION",
                     question_type="PRODUCT_PROMISE", resolution_reason="code says so")
    check("implementation cannot win over the contract (defect, not rewrite)",
          any("DEFECT" in p or "IMPLEMENTATION_DEVIATES_FROM_CONTRACT" in p for p in cr.validate(wrap(code_wins))))

    # Correct: code differs -> IMPLEMENTATION_DEVIATES_FROM_CONTRACT with reason passes.
    defect = dict(base, conflict_type="PRODUCT_DOC_VS_CODE",
                  resolution="IMPLEMENTATION_DEVIATES_FROM_CONTRACT",
                  question_type="PRODUCT_PROMISE",
                  resolution_reason="doc promises A; code produces B -> defect")
    check("documented defect resolution passes", cr.validate(wrap(defect)) == [])

    # INVARIANT 2: FluffyJaws / SUPPORTING_DISCOVERY can never win.
    fj_wins = dict(base, conflict_type="HUMAN_DECISION_VS_DOC",
                   resolution="RESOLVED_BY_HIGHER_AUTHORITY",
                   winning_authority="SUPPORTING_DISCOVERY",
                   question_type="GENERAL", resolution_reason="fluffyjaws said so")
    check("SUPPORTING_DISCOVERY cannot be the winning authority",
          any("SUPPORTING_DISCOVERY" in p for p in cr.validate(wrap(fj_wins))))

    # Question-specific authority: code cannot settle a normative question.
    normative = dict(base, conflict_type="NORMATIVE_VS_IMPLEMENTATION",
                     resolution="RESOLVED_BY_HIGHER_AUTHORITY",
                     winning_authority="VERIFIED_CURRENT_IMPLEMENTATION",
                     question_type="NORMATIVE_SEMANTIC", resolution_reason="r")
    check("implementation cannot settle a normative question",
          any("not appropriate for question_type" in p or "DEFECT" in p for p in cr.validate(wrap(normative))))

    normative_ok = dict(base, conflict_type="NORMATIVE_VS_IMPLEMENTATION",
                        resolution="RESOLVED_BY_HIGHER_AUTHORITY",
                        winning_authority="NORMATIVE_SEMANTIC",
                        question_type="NORMATIVE_SEMANTIC",
                        resolution_reason="DITA 1.3 defines the meaning")
    check("normative authority settles a normative question", cr.validate(wrap(normative_ok)) == [])

    # Non-settling state supporting an AC without safe disposition is rejected.
    unresolved_ac = dict(base, conflict_type="SCOPE_CONFLICT", resolution="PRODUCT_DECISION_REQUIRED",
                         question_type="GENERAL", supports_ac=True)
    check("non-settling state cannot silently support an AC",
          any("must be dispositioned" in p for p in cr.validate(wrap(unresolved_ac))))

    unresolved_ok = dict(unresolved_ac, disposition="OPEN_QUESTION")
    check("dispositioned open conflict passes", cr.validate(wrap(unresolved_ok)) == [])

    # Missing competing evidence rejected.
    no_ev = {"claim_id": "C1", "normalized_claim": "x", "conflict_type": "VERSION_CONFLICT",
             "resolution": "REFERENCE_ONLY", "question_type": "GENERAL",
             "supporting_evidence_ids": [], "conflicting_evidence_ids": []}
    check("competing evidence must be preserved",
          any("non-empty list" in p for p in cr.validate(wrap(no_ev))))

    print("test_evidence_conflict_resolver: OK")


def test_scope_applicability() -> None:
    sa = scope_applicability_mod

    check("absent scope_applicability passes", sa.validate({}) == [])

    def wrap(*cands, outcome="Fix the purge cleanup job"):
        return {"scope_applicability": {"primary_customer_outcome": outcome, "candidates": list(cands)}}

    direct = {"candidate_ref": "CF-01", "scope_status": "DIRECT_SCOPE",
              "scope_basis": "CURRENT_JIRA_AFFECTED_SURFACE",
              "customer_contract_relation": "PRIMARY", "scope_evidence_ids": ["CF-01"]}

    check("grounded direct-scope candidate passes", sa.validate(wrap(direct)) == [])

    # Name-only expansion into scope is rejected.
    name_only = {"candidate_ref": "X1", "scope_status": "SHARED_PATH_REGRESSION",
                 "scope_basis": "SAME_FEATURE_NAME", "customer_contract_relation": "SECONDARY_SHARED",
                 "scope_evidence_ids": ["E1"], "shared_path_evidence": ["E1"]}
    check("name-only scope expansion is rejected",
          any("name-only basis" in p for p in sa.validate(wrap(direct, name_only))))

    # In-scope candidate without evidence is rejected.
    no_ev = {"candidate_ref": "X2", "scope_status": "DIRECT_SCOPE",
             "scope_basis": "IMPLEMENTATION_APPLICABILITY", "customer_contract_relation": "PRIMARY",
             "scope_evidence_ids": []}
    check("in-scope candidate needs evidence",
          any("scope_evidence_ids" in p for p in sa.validate(wrap(no_ev))))

    # SHARED_PATH_REGRESSION must be evidenced and not PRIMARY.
    shared_primary = {"candidate_ref": "X3", "scope_status": "SHARED_PATH_REGRESSION",
                      "scope_basis": "SHARED_IMPLEMENTATION_PATH", "customer_contract_relation": "PRIMARY",
                      "scope_evidence_ids": ["E1"], "shared_path_evidence": ["E1"]}
    check("shared-path regression must stay distinct from primary",
          any("must not be PRIMARY" in p for p in sa.validate(wrap(direct, shared_primary))))

    shared_ok = {"candidate_ref": "X3", "scope_status": "SHARED_PATH_REGRESSION",
                 "scope_basis": "SHARED_IMPLEMENTATION_PATH", "customer_contract_relation": "SECONDARY_SHARED",
                 "scope_evidence_ids": ["E1"], "shared_path_evidence": ["shared job executor path E1"]}
    check("evidenced shared-path regression passes", sa.validate(wrap(direct, shared_ok)) == [])

    # REFERENCE_ONLY cannot promote an AC.
    ref_promote = {"candidate_ref": "X4", "scope_status": "REFERENCE_ONLY",
                   "scope_basis": "SEMANTIC_APPLICABILITY", "customer_contract_relation": "NOT_CONTRACT",
                   "promotes_ac": True}
    check("reference-only cannot promote an AC",
          any("must not promote an AC" in p for p in sa.validate(wrap(direct, ref_promote))))

    # UNRESOLVED_SCOPE must map to an Open Question.
    unresolved = {"candidate_ref": "X5", "scope_status": "UNRESOLVED_SCOPE",
                  "scope_basis": "SHARED_SEMANTIC_PATH", "customer_contract_relation": "SECONDARY_SHARED"}
    check("unresolved scope must become an Open Question",
          any("open_question_ref" in p for p in sa.validate(wrap(direct, unresolved))))

    unresolved_ok = dict(unresolved, open_question_ref="OQ-09")
    check("unresolved scope with Open Question passes", sa.validate(wrap(direct, unresolved_ok)) == [])

    # Target-surface-first: candidates without a primary DIRECT_SCOPE anchor are rejected.
    check("scope must anchor on the primary outcome",
          any("must begin from a DIRECT_SCOPE" in p for p in sa.validate(wrap(shared_ok))))

    print("test_scope_applicability: OK")


def test_ac_language_policy() -> None:
    lp = ac_language_policy_mod

    check("absent ac_synthesis passes", lp.validate({}) == [])

    def wrap(final_acs, source=None):
        b = {"ac_synthesis": {"final_acs": final_acs}}
        if source is not None:
            b["ac_synthesis"]["source_candidate_ids"] = source
        return b

    good = {"ac_ref": "AC-01", "title": "Deleted-preset data is removed on cleanup",
            "body": "When cleanup completes, deleted-preset execution data must be absent and valid data must remain.",
            "candidate_ids": ["CF-09"]}
    check("clear final AC passes", lp.validate(wrap([good])) == [])

    vague = dict(good, ac_ref="AC-02", body="The job should work correctly after the fix.")
    check("vague expectation flagged",
          any("VAGUE_EXPECTATION" in p for p in lp.validate(wrap([vague]))))

    bad_title = dict(good, ac_ref="AC-03", title="Regression behavior")
    check("unclear title flagged",
          any("UNCLEAR_AC_TITLE" in p for p in lp.validate(wrap([bad_title]))))

    leak = dict(good, ac_ref="AC-04",
                body="PurgePresetExecutionDataJob.process() must break the loop on error.")
    check("implementation leak flagged",
          any("IMPLEMENTATION_DETAIL_LEAK" in p for p in lp.validate(wrap([leak]))))

    leak_ok = dict(leak, technical_artifact_is_requirement=True)
    check("declared technical-artifact AC is allowed", lp.validate(wrap([leak_ok])) == [])

    multi = dict(good, ac_ref="AC-05", distinct_contract_count=2)
    check("multiple contracts flagged",
          any("MULTIPLE_UNRELATED_CONTRACTS" in p for p in lp.validate(wrap([multi]))))

    # MATERIAL_CANDIDATE_LOSS: a dropped source candidate is caught.
    lossy = {"ac_ref": "AC-01", "title": "Merged cleanup contract",
             "body": "Deleted-preset data must be removed while valid data remains.",
             "candidate_ids": ["CF-09"], "merged_candidate_ids": ["CF-09"]}
    check("material candidate loss flagged",
          any("MATERIAL_CANDIDATE_LOSS" in p for p in lp.validate(wrap([lossy], source=["CF-09", "CF-03"]))))
    check("full retention passes",
          lp.validate(wrap([dict(lossy, merged_candidate_ids=["CF-09", "CF-03"])], source=["CF-09", "CF-03"])) == [])

    # HIDDEN_MATERIAL_SCENARIO: merge hiding a distinct material dimension.
    hidden = {"ac_ref": "AC-01", "title": "Combined failure and success behavior",
              "body": "Cleanup reports failures and returns succeeded when done.",
              "candidate_ids": ["CF-02", "CF-04"], "merged_candidate_ids": ["CF-02", "CF-04"],
              "distinct_material_dimensions": ["failure"]}
    check("hidden material dimension flagged",
          any("HIDDEN_MATERIAL_SCENARIO" in p for p in lp.validate(wrap([hidden]))))

    # REDUNDANT_AC: duplicate bodies.
    dup = [good, dict(good, ac_ref="AC-09")]
    check("redundant AC flagged",
          any("REDUNDANT_AC" in p for p in lp.validate(wrap(dup))))

    print("test_ac_language_policy: OK")


def test_publishing_scope_coverage() -> None:
    ps = publishing_scope_coverage_mod

    # Non-publishing ticket: not applicable, always clean.
    non_pub = {"issue": {"components": ["Authoring"]}}
    check("non-publishing ticket is not applicable", ps.validate(non_pub, "some plan text") == [])

    pub = {"issue": {"components": ["Publishing"]}}
    bare_plan = "**Acceptance Criteria**\n- AC-01 [Proposed]: (Basic) Given a preset | When output is generated | Then metadata is written | Evidence: Jira.\n"
    probs = ps.validate(pub, bare_plan)
    check("publishing plan without DITA-OT coverage is flagged",
          any("DITA-OT processing" in p for p in probs))
    check("publishing plan without preset scope is flagged",
          any("preset IN-scope" in p for p in probs))

    good_plan = (
        "**Acceptance Criteria**\n"
        "- AC-14 [Proposed]: (Integration) Given a PDF preset that uses the DITA-OT processing engine rather than the native engine | When output is generated | Then existing DITA-OT behaviour is unchanged | Evidence: Jira.\n"
        "- AC-15 [Proposed]: (Integration) Given the change | When output is generated for a non-Native-PDF preset | Then it is out of scope unless shared-code analysis proves the path is shared | Evidence: Jira.\n"
    )
    check("publishing plan covering DITA-OT mode and preset scope passes",
          ps.validate(pub, good_plan) == [])

    # Text-signal activation (no component) also triggers.
    text_pub = {"issue": {"components": []}}
    check("output-preset text signal activates the check",
          ps.validate(text_pub, "**Acceptance Criteria**\n- AC-01: native pdf output preset metadata\n") != [])

    print("test_publishing_scope_coverage: OK")


def test_repro_dimension_matrix() -> None:
    rm = repro_dimension_matrix_mod

    check("absent repro_matrix passes", rm.validate({}) == [])

    def wrap(cells, oqs=None):
        m = {"repro_matrix": {"cells": cells}}
        if oqs is not None:
            m["open_questions"] = oqs
        return m

    ok = {"dimension": "CUSTOM_CONFIGURATION", "materiality": "MATERIAL",
          "repro_status": "CUSTOMER_ONLY", "coverage_status": "OPEN_QUESTION",
          "evidence": ["customer template differs"], "open_question_ref": "OQ-01"}
    check("customer-only material diff with an Open Question passes",
          rm.validate(wrap([ok], oqs=[{"id": "OQ-01"}])) == [])

    # Concluding a material customer-only diff invalid is rejected.
    rejected = dict(ok, coverage_status="REJECTED")
    check("material customer-only diff cannot be REJECTED",
          any("cannot be REJECTED" in p for p in rm.validate(wrap([rejected], oqs=[{"id": "OQ-01"}]))))

    # Material unresolved diff without an Open Question is rejected.
    no_oq = {"dimension": "PRODUCT_VERSION", "materiality": "MATERIAL",
             "repro_status": "NOT_REPRODUCED", "coverage_status": "OPEN_QUESTION",
             "evidence": ["repro only on 4.6"]}
    check("material unresolved diff must reference an Open Question",
          any("must reference an Open Question" in p for p in rm.validate(wrap([no_oq]))))

    # Immaterial dimension in the matrix is overexpansion.
    immat = {"dimension": "BROWSER", "materiality": "IMMATERIAL",
             "repro_status": "NOT_APPLICABLE", "coverage_status": "NOT_TESTED",
             "evidence": ["not relevant"]}
    check("immaterial dimension is flagged as overexpansion",
          any("must not be in the matrix" in p for p in rm.validate(wrap([immat]))))

    # Confirmed repro covered by an AC passes with no Open Question needed.
    confirmed = {"dimension": "PRESET", "materiality": "MATERIAL",
                 "repro_status": "REPRO_CONFIRMED", "coverage_status": "COVERED_BY_AC",
                 "evidence": ["reproduced on Native PDF preset"]}
    check("confirmed repro covered by an AC passes", rm.validate(wrap([confirmed])) == [])

    # Invalid enums rejected.
    bad = {"dimension": "NOPE", "materiality": "MATERIAL", "repro_status": "X",
           "coverage_status": "Y", "evidence": ["e"]}
    check("invalid dimension/state enums rejected", len(rm.validate(wrap([bad]))) >= 2)

    # Duplicate dimension rejected.
    check("duplicate dimension rejected",
          any("duplicate dimension" in p for p in rm.validate(wrap([confirmed, dict(confirmed)]))))

    print("test_repro_dimension_matrix: OK")


def test_acceptance_synthesizer() -> None:
    syn = acceptance_synthesizer_mod

    check("absent ac_synthesis passes", syn.validate({}) == [])
    # ac_synthesis present but no synthesis_group -> not activated -> pass
    check("ac_synthesis without synthesis_group is not activated",
          syn.validate({"ac_synthesis": {"final_acs": [{"ac_ref": "AC-01", "body": "x"}]}}) == [])

    def wrap(ac):
        return {"ac_synthesis": {"final_acs": [ac]}}

    good = {"ac_ref": "AC-01", "title": "Deleted-preset data removed on cleanup",
            "synthesis_group": "CORE_CUSTOMER_CONTRACT",
            "candidate_ids": ["CF-09", "CF-03"], "merged_candidate_ids": ["CF-09", "CF-03"],
            "evidence_ids": ["E1"], "scope_basis": "CURRENT_JIRA_AFFECTED_SURFACE",
            "oracle": "deleted-preset data absent; valid data remains"}
    check("fully-traced grouped AC passes", syn.validate(wrap(good)) == [])

    bad_group = dict(good, synthesis_group="RANDOM_BUCKET")
    check("unknown synthesis_group rejected",
          any("synthesis_group" in p for p in syn.validate(wrap(bad_group))))

    no_trace = {"ac_ref": "AC-02", "synthesis_group": "DIRECT_FIX_BEHAVIOR",
                "candidate_ids": ["CF-01"]}
    probs = syn.validate(wrap(no_trace))
    check("missing evidence_ids trace flagged", any("evidence_ids" in p for p in probs))
    check("missing scope_basis trace flagged", any("scope_basis" in p for p in probs))
    check("missing oracle trace flagged", any("oracle" in p for p in probs))

    merged_not_in_cand = dict(good, merged_candidate_ids=["CF-09", "CF-99"])
    check("merged candidate not in candidate_ids is flagged",
          any("not in candidate_ids" in p for p in syn.validate(wrap(merged_not_in_cand))))

    print("test_acceptance_synthesizer: OK")


def test_uac_linter() -> None:
    ul = uac_linter_mod

    # No plan, no block -> clean.
    check("empty inputs pass", ul.validate({}, "") == [])

    good_plan = (
        "**Acceptance Criteria**\n"
        "- AC-01 [Proposed]: (Basic) Given a preset | When output is generated | Then metadata.xml contains the map properties | Evidence: Jira.\n"
        "- AC-02 [Proposed]: (Basic) Given a topic | When output is generated | Then metadata.xml contains the topic properties | Evidence: Jira.\n"
        "**Expected Behaviour**\n- x\n"
    )
    check("distinct ACs pass", ul.validate({}, good_plan) == [])

    dup_plan = (
        "**Acceptance Criteria**\n"
        "- AC-01 [Proposed]: (Basic) Given a preset | When output is generated | Then metadata.xml contains the map properties | Evidence: Jira.\n"
        "- AC-02 [Proposed]: (Basic) Given a preset | When output is generated | Then metadata.xml contains the map properties | Evidence: Jira.\n"
    )
    check("duplicate AC outcome is flagged",
          any("DUPLICATE_AC" in p for p in ul.validate({}, dup_plan)))

    # Opt-in testability block: complete record passes.
    good_block = {"uac_linter": {"testability": [
        {"ac_ref": "AC-01", "condition_or_state": "preset set", "expected_behavior": "properties written",
         "observable_oracle": "metadata.xml", "scope": "Native PDF", "evidence": ["Jira"]}
    ]}}
    check("complete testability record passes", ul.validate(good_block, good_plan) == [])

    missing = {"uac_linter": {"testability": [{"ac_ref": "AC-01", "condition_or_state": "x"}]}}
    probs = ul.validate(missing, good_plan)
    check("missing oracle in testability flagged", any("observable_oracle" in p for p in probs))

    unknown_ac = {"uac_linter": {"testability": [
        {"ac_ref": "AC-99", "condition_or_state": "a", "expected_behavior": "b",
         "observable_oracle": "c", "scope": "d", "evidence": ["e"]}
    ]}}
    check("testability ac_ref not in plan flagged",
          any("not an AC in the plan" in p for p in ul.validate(unknown_ac, good_plan)))

    contra = {"uac_linter": {"testability": [], "oq_ac_contradictions": ["AC-01 vs OQ-02"]}}
    check("AC/OQ contradiction flagged",
          any("OQ_CONTRADICTS_AC" in p for p in ul.validate(contra, good_plan)))

    scope_mm = {"uac_linter": {"testability": [], "scope_mismatch_acs": ["AC-05"]}}
    check("scope mismatch flagged",
          any("SCOPE_MISMATCH" in p for p in ul.validate(scope_mm, good_plan)))

    print("test_uac_linter: OK")


def test_human_feedback_delta() -> None:
    hf = human_feedback_delta_mod

    check("absent human_feedback_delta passes", hf.validate({}) == [])

    def wrap(*deltas):
        return {"human_feedback_delta": {"deltas": list(deltas)}}

    approved = {"delta_type": "COVERAGE_ADDED", "pattern_class": "DISCOVERY_PATTERN",
                "source": "HUMAN", "promotion_state": "APPROVED", "first_failed_stage": "DISCOVERY",
                "human_cases": ["GUIDES-A", "GUIDES-B"], "counterexample_search_done": True}
    check("multi-case human approved delta passes", hf.validate(wrap(approved)) == [])

    # FluffyJaws cannot be promoted.
    fj = dict(approved, source="FLUFFYJAWS")
    check("FluffyJaws delta cannot be VALIDATING/APPROVED",
          any("only Human feedback" in p for p in hf.validate(wrap(fj))))

    # AI review cannot be promoted.
    ai = dict(approved, source="AI_REVIEW", promotion_state="VALIDATING")
    check("AI review delta cannot be promoted",
          any("only Human feedback" in p for p in hf.validate(wrap(ai))))

    # Language delta cannot be a discovery pattern.
    lang = {"delta_type": "LANGUAGE_SIMPLIFIED", "pattern_class": "DISCOVERY_PATTERN",
            "source": "HUMAN", "promotion_state": "CANDIDATE"}
    check("language delta cannot be DISCOVERY_PATTERN",
          any("must not be a DISCOVERY_PATTERN" in p for p in hf.validate(wrap(lang))))

    lang_ok = dict(lang, pattern_class="RENDERING_LANGUAGE_PATTERN")
    check("language delta as rendering pattern passes", hf.validate(wrap(lang_ok)) == [])

    # Coverage miss must record first_failed_stage.
    no_stage = {"delta_type": "COVERAGE_ADDED", "pattern_class": "DISCOVERY_PATTERN",
                "source": "HUMAN", "promotion_state": "CANDIDATE"}
    check("coverage add without first_failed_stage flagged",
          any("first_failed_stage" in p for p in hf.validate(wrap(no_stage))))

    # Single-case approval without normative/severe is rejected.
    single = {"delta_type": "SCOPE_NARROWED", "pattern_class": "SCOPE_PATTERN",
              "source": "HUMAN", "promotion_state": "APPROVED",
              "human_cases": ["GUIDES-A"], "counterexample_search_done": True}
    check("single-case approval without invariant/severe flagged",
          any(">=2 independent Human cases" in p for p in hf.validate(wrap(single))))

    # Approval without counterexample mining is rejected.
    no_ce = dict(approved, counterexample_search_done=False)
    check("approval without counterexample search flagged",
          any("counterexample_search_done" in p for p in hf.validate(wrap(no_ce))))

    print("test_human_feedback_delta: OK")


def main() -> int:
    test_validator()
    test_ac_readability()
    test_verifier()
    test_attachment_manifest()
    test_run_gates()
    test_extract_acs()
    test_compact_view()
    test_semantic_explorer()
    test_anti_hardcoding()
    test_production_jira_hardcoding_audit()
    test_behavior_model()
    test_coverage_hypotheses()
    test_missing_questions()
    test_hypothesis_verifier()
    test_coverage_gate()
    test_uac_integration()
    test_reasoning_required()
    test_authoring_state_contract()
    test_uac_fidelity_reference()
    test_component_reference_routing()
    test_relevance_prioritizer()
    test_disposition_classifier()
    test_oracle_builder()
    test_state_compatibility()
    test_cross_surface_resolver()
    test_structural_equivalence()
    test_scenario_reducer()
    test_evidence_authority()
    test_change_impact()
    test_pre_uac_critic()
    test_implementation_grounding()
    test_capability_eligibility()
    test_scope_conflict()
    test_affected_surface()
    test_comment_claims()
    test_pr_supersession()
    test_feature_class_registry()
    test_relationship_traversal()
    test_configuration_enumeration_scope()
    test_ui_surface_scope()
    test_role_provisioning()
    test_fluffyjaws_evidence()
    test_temporal_evidence()
    test_evidence_conflict_resolver()
    test_scope_applicability()
    test_ac_language_policy()
    test_publishing_scope_coverage()
    test_repro_dimension_matrix()
    test_acceptance_synthesizer()
    test_uac_linter()
    test_human_feedback_delta()
    test_terminal_states()
    test_concurrency_race()
    test_enumerated_coverage()
    test_source_requirement_fidelity()
    test_ac_decidability()
    test_operational_contract()
    test_gate_receipt_and_adapter()
    test_contract_facts_and_integrity()
    test_issue_domain_routing_and_publishing_scope()
    test_behavior_graph_relation_ontology()
    test_semantic_closure_required()
    test_missing_question_directed_retrieval_by_subject()
    test_coverage_disposition_completeness()
    test_acceptance_promotion_authority()
    test_generated_output_contract()
    test_generated_artifact_delivery_regression()
    test_content_identity_lifecycle_regression()
    test_postability_semantic_reviews()
    print("\nALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
