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
explorer_mod = _load("semantic_relationship_explorer", "semantic_relationship_explorer.py")
audit_mod = _load("anti_hardcoding_audit", "anti_hardcoding_audit.py")
behavior_mod = _load("behavior_model", "behavior_model.py")
coverage_mod = _load("coverage_hypotheses", "coverage_hypotheses.py")
mq_mod = _load("missing_questions", "missing_questions.py")
verifier_mod = _load("hypothesis_verifier", "hypothesis_verifier.py")
coverage_gate_mod = _load("coverage_gate", "coverage_gate.py")
integration_mod = _load("uac_integration", "uac_integration.py")
relevance_mod = _load("relevance_prioritizer", "relevance_prioritizer.py")


GOOD_PLAN = """**Understanding From Jira**
- Issue understood: a thing is broken with a visible symptom.
- Why it matters: it hurts customers in a concrete way.
- Requested outcome: the thing should stop being broken.
- Lifecycle understood as: Pre-Development UAC with no PR yet.
- Evidence boundary: facts are from live Jira and a backend clone.
**Acceptance Criteria**
- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output.
- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state.
**Expected Behaviour**
- Unknown from current evidence.
**Scope From Git**
- Lifecycle stage is Pre-Development UAC and readiness target is UAC-ready.
**Code Touched**
- No code changes yet — development has not started.
**Lines Changed**
- Not applicable — development has not started.
**Test Scenarios**
- Setup and test data: create map M.ditamap and topic t.dita under /content/dam/sandbox; property foo on jcr:content holds value bar; config gate baz defaults to true; oracle is the observable correct output.
- P0 [AC-01]: do the first thing and observe the correct output.
- P1 [AC-02]: do the second thing and observe prior state retained.
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


def _replace(plan: str, old: str, new: str) -> str:
    assert old in plan, f"fixture anchor not found: {old!r}"
    return plan.replace(old, new)


def check(name: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    print(f"ok: {name}")


def test_validator() -> None:
    check("good plan passes", validate_mod.validate(GOOD_PLAN) == [])

    missing_strength = _replace(
        GOOD_PLAN,
        "Similarity: strongest match — same failure shape of wrong output.",
        "Similarity: same version purge area and cleanup theme.",
    )
    errs = validate_mod.validate(missing_strength)
    check("area-only similarity (no match strength) is rejected", any("match strength" in e for e in errs))

    ac_no_sphere = _replace(
        GOOD_PLAN,
        "- AC-01 [Proposed]: (Basic) Given an input | When the system runs | Then it produces the correct observable output.",
        "- AC-01 [Proposed]: Given an input | When the system runs | Then it produces the correct observable output.",
    )
    errs = validate_mod.validate(ac_no_sphere)
    check("AC missing the sphere tag is rejected", any("sphere-tagged Given|When|Then" in e for e in errs))

    ac_no_gwt = _replace(
        GOOD_PLAN,
        "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state.",
        "- AC-02 [Proposed]: (Negative) the system should retain valid prior state.",
    )
    errs = validate_mod.validate(ac_no_gwt)
    check("AC missing Given|When|Then is rejected", any("sphere-tagged Given|When|Then" in e for e in errs))

    ac_no_scenario = _replace(
        GOOD_PLAN,
        "- P1 [AC-02]: do the second thing and observe prior state retained.",
        "- P1 [AC-01]: do a redundant first thing again.",
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
        "- P0 [AC-01]: do the first thing and observe the correct output.",
        "- P0 do the first thing and observe the correct output.",
    )
    errs = validate_mod.validate(scenario_no_ac)
    check("scenario without AC mapping is rejected", any("missing an AC mapping" in e for e in errs))

    no_test_data = _replace(
        GOOD_PLAN,
        "- Setup and test data: create map M.ditamap and topic t.dita under /content/dam/sandbox; property foo on jcr:content holds value bar; config gate baz defaults to true; oracle is the observable correct output.\n",
        "",
    )
    errs = validate_mod.validate(no_test_data)
    check("Test Scenarios without a Setup and test data bullet is rejected", any("Setup and test data" in e for e in errs))

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

    # absolute path WITH SPACES in a body section must NOT be flagged when backtick-quoted
    spaced_abs_ok = _replace(
        GOOD_PLAN,
        "- No code changes yet — development has not started.",
        "- No code changes yet — development has not started.\n- Current implementation in `C:\\\\api automation\\\\dxml-it-tests\\\\Foo.java` is implicated.",
    )
    check("backtick absolute path with spaces is accepted in a body section", validate_mod.validate(spaced_abs_ok) == [])

    rel_path_flagged = _replace(
        GOOD_PLAN,
        "- No code changes yet — development has not started.",
        "- No code changes yet — development has not started.\n- Current implementation in `api automation\\\\dxml-it-tests\\\\Foo.java` is implicated.",
    )
    errs = validate_mod.validate(rel_path_flagged)
    check("non-absolute backtick path is still flagged in a body section", any("not absolute" in e for e in errs))


def test_verifier() -> None:
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


def test_git_ref_citations() -> None:
    import subprocess

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        def git(*args):
            subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True)
        try:
            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
        except (OSError, subprocess.CalledProcessError):
            print("ok: git-ref self-test skipped (git unavailable)")
            return
        (root / "pages").mkdir()
        (root / "pages" / "editor.py").write_text("x = 1\n", encoding="utf-8")
        git("add", "-A")
        git("commit", "-qm", "seed")

        # a real ref:path resolves -> no failure (HEAD is branch-name-agnostic).
        # Avoid the word "Covered" so the unrelated fenced-code rule is not triggered.
        good = "- Exercised by `HEAD:pages/editor.py` in the automation clone.\n"
        failures, notes = verify_mod.verify(good, git_ref_roots=[str(root)])
        check("valid git-ref citation verifies against repo root", failures == []
              and any("git-ref citations" in n and "1 verified" in n for n in notes))

        # a wrong ref:path is now caught (previously silently skipped)
        bad = "- Exercised by `HEAD:pages/ghost.py` in the automation clone.\n"
        failures, _ = verify_mod.verify(bad, git_ref_roots=[str(root)])
        check("wrong git-ref citation is failed", any("does not resolve" in f for f in failures))

        # with no repo root, it is reported as unverified (a note), not silently ignored
        failures, notes = verify_mod.verify(good, git_ref_roots=[])
        check("git-ref with no repo root is surfaced as unverified", failures == []
              and any("NOT verified" in n for n in notes))


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


def test_run_gates() -> None:
    import json

    run_gates = _load("run_gates", "run_gates.py")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "m.json"

        check("run_gates requires a manifest", run_gates.check_manifest_completeness(None) != [])

        path.write_text(json.dumps({"issue": "X"}), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates flags missing manifest keys", any("clones" in f for f in failures) and any("rag_probes" in f for f in failures))

        path.write_text(json.dumps({"issue": "X", "attachments": [], "rag_probes": ["a", "b", "c"],
                                    "indexed_history_run": True, "clones": [{"path": "C:/x"}]}), encoding="utf-8")
        failures = run_gates.check_manifest_completeness(str(path))
        check("run_gates flags a clone with no sha and not provisional", any("captured sha" in f for f in failures))

        path.write_text(json.dumps({"issue": "X", "attachments": [], "rag_probes": ["a", "b", "c"],
                                    "indexed_history_run": True,
                                    "clones": [{"path": "C:/x", "provisional": True, "note": "SHA not captured"}]}), encoding="utf-8")
        check("run_gates passes a complete manifest", run_gates.check_manifest_completeness(str(path)) == [])


def test_extract_acs() -> None:
    extract_mod = _load("extract_acs", "extract_acs.py")
    acs, problems = extract_mod.extract(GOOD_PLAN)
    check("extract_acs parses both good ACs", len(acs) == 2 and problems == [])
    check("extract_acs maps sphere/given/when/then", acs[0]["sphere"] == "Basic"
          and acs[0]["id"] == "AC-01" and acs[0]["given"] and acs[0]["when"] and acs[0]["then"])
    check("extract_acs second AC sphere is Negative", acs[1]["sphere"] == "Negative")
    malformed = _replace(
        GOOD_PLAN,
        "- AC-02 [Proposed]: (Negative) Given a second input | When the system runs | Then it retains valid prior state.",
        "- AC-02 [Proposed]: the system retains prior state.",
    )
    acs2, problems2 = extract_mod.extract(malformed)
    check("extract_acs reports a malformed AC line", len(acs2) == 1 and any("unparseable" in p for p in problems2))


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


def main() -> int:
    test_validator()
    test_verifier()
    test_git_ref_citations()
    test_attachment_manifest()
    test_run_gates()
    test_extract_acs()
    test_semantic_explorer()
    test_anti_hardcoding()
    test_behavior_model()
    test_coverage_hypotheses()
    test_missing_questions()
    test_hypothesis_verifier()
    test_coverage_gate()
    test_uac_integration()
    test_reasoning_required()
    test_relevance_prioritizer()
    print("\nALL SELF-TESTS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
