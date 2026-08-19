"""Self-tests for the test-plan-generation enforcement scripts.

Run: python scripts/test_skill_scripts.py
Exit 0 = all pass. No third-party deps; stdlib only.

These protect the validator and evidence auditor from silent regressions when
their rules are edited. Every rule that can fail a plan has a positive and a
negative fixture here.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path


def _load(module_name: str, filename: str):
    spec = importlib.util.spec_from_file_location(module_name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _find_repo_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
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
        "- AC-02 [Proposed]: (Performance) Given 10,000 topics with parent-map references | When the cleanup workflow runs | Then p95 cleanup latency remains at or below 2000 ms and timeout error rate remains at 0% | Evidence: Jira comment GUIDES-100.",
    )
    quantified_performance = _replace(
        quantified_performance,
        "- P1 [AC-02]: Action: do the second thing. Expected: observe prior state retained.",
        "- P1 [AC-02]: Action: run the cleanup load benchmark for 10,000 topics. Expected: p95 latency is at or below 2000 ms with a 0% timeout error rate.",
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
        "- Scope decision: is the async path in scope? QA impact: if yes add a polling-oracle scenario, if no document the limitation and prove cleanup does not fire.",
    )
    check("open question stating QA impact passes", validate_mod.validate(oq_with_impact) == [])

    oq_no_impact = _replace(
        GOOD_PLAN,
        "- No open questions from current evidence",
        "- Is the fix synchronous or asynchronous on delete?",
    )
    errs = validate_mod.validate(oq_no_impact)
    check("open question without QA impact is rejected", any("QA impact of the answer" in e for e in errs))

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
            "issue": "X",
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
        }

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
            "- AC-02 [Proposed]: (Performance) Given 10,000 topics with parent-map references | When the cleanup workflow runs | Then p95 cleanup latency remains at or below 2000 ms and timeout error rate remains at 0% | Evidence: Jira comment GUIDES-100.",
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
            "- Performance sign-off: confirm production topic cardinality, concurrent cleanup jobs, and the approved p95 latency SLA. QA impact: without these values no Performance AC can be emitted safely; with them QA can define the load, soak, and pass-fail oracle.",
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
    check(
        "compact ACs are straightforward and hide evidence analysis",
        "- AC-01: Given an input | When the system runs | Then it produces the correct observable output." in compact
        and "[Proposed]" not in compact
        and "Evidence:" not in compact,
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
    for marker in ("6 rows and 5 columns", "6 rows and 3 visible columns", "ghost column", "span metadata"):
        check(f"CALS deletion contract contains {marker}", marker in cals_text)

    large_file = authoring_state_mod.derive_contract(
        "GUIDES-35437: Ctrl+Z changed after 411 cells; largeFileTagCount controls the large-file safeguard."
    )
    check(
        "GUIDES-35437 is configuration-driven working-as-designed behavior",
        large_file["route"] == "large_file_configuration"
        and large_file["classification"] == "working_as_designed_configuration",
    )
    large_file_text = "\n".join(
        [*large_file["acceptance_criteria"], *large_file["test_scenarios"]]
    )
    check("large-file contract uses parsed tag threshold", "parsed-tag threshold" in large_file_text)
    check(
        "large-file contract does not create a 411-cell AC",
        all("411" not in criterion for criterion in large_file["acceptance_criteria"]),
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
        "For GUIDES-34915-style scope pivots",
        "For GUIDES-34580-style Closed/Duplicate history",
        "For Map View hierarchy-selection counts",
        "For GUIDES-41093-style Explorer sorting enhancements",
        "For asset CRUD API requests",
    ):
        check(f"skill retains UAC fidelity marker {marker}", marker in skill_text)
    for marker in (
        "## Gold Reference: GUIDES-38333 Native PDF Reltable Parity",
        "ENABLE_RELATED_LINKS_FOR_NATIVE_PDF",
        "-Dargs.rellinks=nofamily",
        "OOS-03",
        "AC-06 [Confirmed]",
        "## Gold Reference: GUIDES-49325 Native AEM Site Baseline Metadata",
        "NATIVE_AEMSITE",
        "Baseline_v2.0",
        "metadatalist",
        "GUIDES-53306",
        "AC-12 [Confirmed]",
        "## Gold Reference: GUIDES-10878 Baseline-Aware Map Preview",
        "UAC-16",
        "AC-10 [Proposed]",
        "dynamic/static loader behavior while OOS-01 excludes dynamic baselines",
        "## Caution Reference: GUIDES-31711 DITAVAL Taxonomy Complaint Closed as Working as Designed",
        "The DITA standard does not prescribe AEM Guides UI taxonomy",
        "No Confirmed AC is justified by GUIDES-31711",
        "## Caution Reference: GUIDES-30001 Configuration-Gated Navtitle Button",
        '"required": {"navtitle": true}',
        "No Confirmed AC is justified by GUIDES-30001",
        "## Caution Reference: GUIDES-28847 Metadata Filter Index Incident",
        "damAssetLucene",
        "No Confirmed AC is justified by GUIDES-28847",
        "## Caution Reference: GUIDES-28667 Custom Preview Button Configuration Migration",
        "jira_comment_configuration_migration",
        "No Confirmed AC is justified by GUIDES-28667",
        "## Accepted Reference: GUIDES-28443 Bulk Metadata Manage Recovery",
        "bin/guides/v1/map/reports/metadata/tags/common",
        "allAssets=true",
        "GUIDES-29778",
        "performance_contract_complete=false",
        "release_scope_source=jira_comment_release_scope",
        "The supplied screenshot shows a service-outage banner only",
        "## Product-Fix Reference: GUIDES-25769 Author-View Image Move Data Loss",
        "No Confirmed AC is justified by GUIDES-25769",
        "jira_comment_version_validation",
        "behavior_contract_complete=false",
        "both `Automated` and `Won't_Automate`",
        "## Accepted Comment-Scope Reference: GUIDES-23526 Folder-Profile Condition Preservation",
        "uac_source_origin=jira_comment_accepted_scope",
        "Existing-condition boundary",
        "group removal and yellow color reset",
        "AC-04 [Proposed]: (Reports)",
        "cross_touchpoint_taxonomy",
        "## Deterministic Performance Reference: GUIDES-37722 With GUIDES-37915",
        "A qualifying historical performance Jira must not remain only under Regression Areas",
        "approximately 200 concurrent users",
        "p95 response time improves by at least 2x",
    ):
        check(f"UAC reference retains marker {marker}", marker in reference_text)
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
        "## Route 4 - GUIDES-35437 Large-File Safeguard",
        "6-row by 5-column CALS table",
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
        labels=["UAC_Done", "Hyundai"],
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

    map_selection = component_router_mod.route_references(
        component="Authoring",
        summary="Incorrect selected items in Map View",
        acceptance_criteria=(
            "In a fresh Guides 4.6 Map View, selecting map2 for the first time must immediately "
            "display 7 selected rather than 1 selected. The seven-node selected set includes map2 "
            "and all selected child nodes; later correct selections cannot mask the first failure. "
            "The hierarchy can contain DITA files, Markdown files, and DITAVAL files."
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
        labels=["Red Hat"],
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
        labels=["Hyundai"],
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
        and generic_api["load_full_uac_reference"] is True,
    )

    bulk_overwrite = component_router_mod.route_references(
        summary="Abnormal behavior when overwriting 200+ assets",
        description=(
            "The initial upload of 200 assets succeeds, but re-uploading the same-name assets "
            "through /bin/fmdita/import can remain stuck on a loader or show a generic error "
            "and redirect the authenticated author to login after repeated CSRF token requests."
        ),
        resolution="Cannot Reproduce",
        labels=["Hyundai"],
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

    skill_root = Path(__file__).resolve().parents[1]
    authoring_reference = (skill_root / "references" / "component-authoring.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Asset-Browser Thumbnail Contract — GUIDES-34915",
        "does not prove multi-selection",
        "## Map-Xref Display Label Contract — GUIDES-34580",
        "Closed as Duplicate",
        "`href`, `format`, `scope`, and `type`",
        '`scope="external"`',
        "no repository map-title lookup is applied",
        "## Map View Hierarchy Selection-Count Contract",
        "selected map node itself and every descendant node",
        "visible node occurrences or unique asset identity",
        "DITA, Markdown, and DITAVAL",
        "selecting `map2` initially shows `1 selected`",
        "first selection must immediately show `7 selected`",
        "warm second selection cannot validate this defect",
        "## Explorer Filename/Title Sorting Contract — GUIDES-41093",
        "display label, sort key, sort direction, folder default, and per-user override",
        "dedicated sort affordance in the Explorer header",
        "static mockup does not show the opened control",
        "## Feature-Flag and Default-State Matrix",
        "feature flag is OFF",
        "feature flag is ON",
        "upward arrow in a static mockup is not proof of ascending order",
        "configured default value separate from the sort button's first-render default state",
        "do not retain implicit display-preference coupling",
        "documented workaround and comparison surface",
        "folder-level Assets configuration only the initial default",
        "Reject generic repository ordering",
        "## Folder Deletion Release-Evolution Contract - GUIDES-19345",
        "not proof of an implemented Guides folder-delete workflow",
        "governed **file deletion**",
        "does not, by itself, prove",
        "Do not infer restore, trash",
        "Assets UI file deletion as boundary/comparison evidence",
    ):
        check(f"Authoring component pack retains marker {marker}", marker in authoring_reference)

    integration_reference = (skill_root / "references" / "component-integration.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Asset CRUD API Import Contract",
        "### Documented Current API Baseline",
        "POST /bin/fmdita/xmleditor/create",
        "operation=getdita",
        "operation=postDita",
        "`createrev` controls revision creation",
        "POST /bin/guides/assets/delete",
        "delete-only `force` parameter",
        "template-only CREATE request with `parent`, `name`, `title`, and `template`",
        "`operation=postDita` with `editorData`, `path`, and `createrev=false` or `true`",
        "`operation=getdita`, `path`, and `type=UUID`",
        "no partial new asset, duplicate identity, or partially updated metadata/content remains",
        "filename, repository path, and GUID",
        "target `exists` and `missing`",
        "force-create `omitted`, `false`, and `true`",
        "every generated criterion remains `[Proposed]`",
        "a successful HTTP response alone is insufficient",
        "must not be confused with UPDATE `createrev` or DELETE `force`",
        "Reject editor CRUD",
    ):
        check(f"Integration component pack retains marker {marker}", marker in integration_reference)

    platform_reference = (skill_root / "references" / "component-platform.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "## Bulk Same-Name Asset Overwrite and Session Contract - GUIDES-30459",
        "candidate historical learning only",
        "SP21 versus SP22",
        "POST /bin/fmdita/import",
        "never as a supported product threshold or SLA",
        "observable terminal success or failure state",
        "verified by reading back every targeted asset",
        "Product Assets Upload Process",
        "GUIDES-14743",
        "Do not claim data loss",
    ):
        check(f"Platform component pack retains marker {marker}", marker in platform_reference)

    repo_root = _find_repo_root()
    for variant in (".codex", ".claude"):
        variant_root = repo_root / variant / "skills" / "test-plan-generation"
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

    # absent blocks are backward-compatible
    check("missing_questions/evidence absent is not a failure", mq.is_present({"issue": "X"}) is False)


def test_hypothesis_verifier() -> None:
    hv = verifier_mod

    def V(**k):
        base = {"hypothesis_id": "H-01", "verdict": "CONFIRMED",
                "supporting_authorities": ["CURRENT_IMPLEMENTATION"], "supporting_evidence": ["E5"],
                "disposition": "ACCEPTANCE_CRITERION"}
        base.update(k)
        return base

    # (1) a plausible hypothesis is CONFIRMED on authoritative evidence -> AC
    check("plausible hypothesis confirmed on authoritative evidence", hv.validate_verification(hv.Verification.from_dict(V())) == [])

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
    inferred_ok = V(verdict="INFERRED_HIGH_CONFIDENCE", supporting_evidence=["E1", "E2"], disposition="INFERRED_AC", supporting_authorities=["CURRENT_IMPLEMENTATION"])
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
    import json, tempfile
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

        # behavior_model present, no coverage -> satisfied
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behavior_model": bm}))[0]
        check("behavior_model present satisfies the requirement", f == [])

        # coverage declared without verifications -> required failure
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behavior_model": bm, "coverage_hypotheses": cov}))[0]
        check("coverage hypotheses without verifications is rejected", any("no verifications block" in x for x in f))

        # full reasoning set -> satisfied
        f = run_gates.check_reasoning_required(_write(tmp, {"issue": "X", "behavior_model": bm, "coverage_hypotheses": cov, "verifications": verif}))[0]
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
    cov[0]["dimension"] = "DITA_SEMANTIC_DEPENDENCY"; cov[0]["reason"] = "r"; cov[0]["technical_basis"] = ["t"]
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
    partial_checks = dict(allchecks); partial_checks["transformation"] = False
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


def test_capability_eligibility() -> None:
    ce = cap_elig_mod
    check("multi-action toolbar activates", ce.is_active({"issue": {"description": "the toolbar shows View source, Edit topics and Share buttons"}}) is True)
    check("single-action ticket does not activate (Case A)", ce.is_active({"issue": {"summary": "fix the export dialog title"}}) is False)

    def term(**o):
        b = {"dimension": "ENTITY_TYPE", "operator": "in", "expected_value": "dita", "evidence_ids": ["E1"], "material": True}
        b.update(o); return b

    def cap(name="Cap A", **o):
        b = {"capability": name, "predicate_terms": [term()]}
        b.update(o); return b

    def block(**o):
        b = {"active": True, "capabilities": [cap("Cap A"), cap("Cap B", predicate_terms=[term(dimension="METADATA", expected_value="uuid present")])]}
        b.update(o); return b

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
        b.update(o); return b
    check("entry points with resolved consistency pass", ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap()]}) == [])
    check("multiple entry points without consistency rejected",
          any("entry_point_consistency" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_point_consistency="")]})))
    check("VERIFIED_SAME without evidence rejected",
          any("needs evidence" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_point_consistency_evidence=[])]})))
    check("invalid entry-point form rejected",
          any("form must be one of" in p for p in ce.validate_capability_eligibility({"active": True, "capabilities": [ep_cap(entry_points=[{"form": "WIDGET", "evidence_ids": ["E1"]}, {"form": "OVERFLOW_MENU", "evidence_ids": ["E2"]}])]})))
    resp_manifest = {"issue": {"description": "the keyword shows as a direct button at 50% zoom; in the overflow menu it works"}}
    under = ce.entrypoint_underexplored({"capabilities": [{"capability": "Insert Keyword", "predicate_terms": [term()]}]}, resp_manifest)
    check("responsive signals + <2 entry points is under-explored", under == ["Insert Keyword"])
    check("no responsive signals -> not under-explored", ce.entrypoint_underexplored({"capabilities": [{"capability": "X"}]}, {"issue": {"summary": "plain dialog title fix"}}) == [])


def test_scope_conflict() -> None:
    sc = scope_conflict_mod
    check("fix + multi-problem activates", sc.is_active({"issue": {"description": "the PR fixes the button; also there is a separate font preview problem"}}) is True)
    check("no fix signal does not activate", sc.is_active({"issue": {"summary": "buttons show on wrong assets"}}) is False)

    def thread(**o):
        b = {"thread_id": "T1", "problem_statement": "buttons wrong", "status": "CONFIRMED"}
        b.update(o); return b

    def block(**o):
        b = {"active": True, "problem_threads": [thread()], "alignment": "FULL_SCOPE_FIX", "open_question_refs": []}
        b.update(o); return b

    check("full alignment passes with no open question (Case E)", sc.validate_scope_conflict(block()) == [])
    check("partial alignment without open question rejected",
          any("surfaced as an Open Question" in p for p in sc.validate_scope_conflict(block(alignment="PARTIAL_SCOPE_FIX"))))
    check("partial alignment with open question passes",
          sc.validate_scope_conflict(block(alignment="PARTIAL_SCOPE_FIX", open_question_refs=["OQ-2"]), open_question_ids=["OQ-2"]) == [])
    check("unresolved_scope_without_open_question detects hidden mismatch",
          sc.unresolved_scope_without_open_question(block(alignment="UNKNOWN_FIX_SCOPE")) is True)
    check("secondary-defect thread mapped to AC rejected (Case F)",
          any("must NOT map" in p for p in sc.validate_scope_conflict(block(problem_threads=[thread(status="SECONDARY_DEFECT", maps_to_ac=True)]))))
    check("invalid thread status rejected", any("status" in p for p in sc.validate_scope_conflict(block(problem_threads=[thread(status="MAYBE")]))))
    check("invalid alignment rejected", any("alignment" in p for p in sc.validate_scope_conflict(block(alignment="SORTA"))))


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


def main() -> int:
    test_validator()
    test_verifier()
    test_attachment_manifest()
    test_run_gates()
    test_extract_acs()
    test_compact_view()
    test_semantic_explorer()
    test_anti_hardcoding()
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
    print("\nALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
