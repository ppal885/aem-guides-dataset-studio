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


validate_mod = _load("validate_test_plan", "validate_test_plan.py")
verify_mod = _load("verify_evidence", "verify_evidence.py")


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
        any("Performance Then must define a measurable numeric oracle" in e for e in errs),
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
        == ["**Acceptance Criteria**", "**Regression Areas**", "**Past Jiras**", "**Open Questions**"],
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
                "Test Scenarios",
                "Automation Coverage & Gaps",
            )
        ),
    )
    check("compact view keeps validated past Jira", "GUIDES-100" in compact)
    check("compact view keeps Open Questions", "No open questions from current evidence" in compact)

    no_match_plan = _replace(
        GOOD_PLAN,
        "- GUIDES-100 — Some bug. Similarity: strongest match — same failure shape of wrong output. Status: Closed. Resolution: Fixed. Affected version: not available in current evidence. Fix version: 2609. RCA: not available in current evidence. Test evidence: not available in current evidence. Impact: reuse its oracle.\n",
        "",
    )
    no_match_compact, no_match_problems = compact_mod.project(no_match_plan)
    check(
        "compact view renders a deterministic no-Jira result",
        no_match_problems == [] and "No same-defect-class past Jira" in no_match_compact,
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
    ):
        check(f"UAC reference retains marker {marker}", marker in reference_text)
    check(
        "quality gate enforces accepted UAC fidelity",
        "Final accepted UAC exists but its fidelity audit is missing" in checklist_text,
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


def main() -> int:
    test_validator()
    test_verifier()
    test_attachment_manifest()
    test_run_gates()
    test_extract_acs()
    test_compact_view()
    test_uac_fidelity_reference()
    print("\nALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
