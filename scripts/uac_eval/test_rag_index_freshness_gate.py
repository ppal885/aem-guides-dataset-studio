"""Tests for rag_index_freshness_gate: manifest freshness, staging isolation, dispositions and
the replay pass/fail rules. No Chroma, embeddings, LLM or network: index access is injected."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import rag_index_freshness_gate as gate  # noqa: E402


# --- code identity and manifest ---------------------------------------------------------------


def _manifest(**overrides):
    base = {
        "schema_version": gate.MANIFEST_SCHEMA,
        "environment": "staging",
        "rebuilt_at": "2026-11-10T10:00:00+00:00",
        "source": {"commit": "abc", "retrieval_code_dirty": False},
        "retrieval_code": {"sha256": "code-1", "last_changed_at": "2026-11-09T19:00:00+00:00"},
        "embedding": {"provider": "LOCAL", "model": "bge-small", "dimension": 384},
        "collections": {
            "jira_qa": {"chunk_count": 10, "stale_chunk_ids": []},
            "aem_guides": {"chunk_count": 5, "stale_chunk_ids": []},
        },
    }
    base.update(overrides)
    return base


def _check(manifest, *, code="code-1", changed="2026-11-09T19:00:00+00:00", embedding=None):
    return gate.check_manifest(
        manifest,
        current_code_sha256=code,
        code_changed_at=changed,
        current_embedding=embedding or {"provider": "LOCAL", "model": "bge-small"},
    )


def test_fresh_manifest_passes():
    assert _check(_manifest()) == []


def test_missing_or_foreign_manifest_is_refused():
    assert _check(None) == ["MANIFEST_MISSING"]
    assert _check({"schema_version": "other"}) == ["MANIFEST_SCHEMA_MISMATCH"]


def test_manifest_built_by_other_retrieval_code_is_refused():
    assert "RETRIEVAL_CODE_CHANGED_SINCE_REBUILD" in _check(_manifest(), code="code-2")


def test_manifest_predating_retrieval_code_change_is_refused():
    reasons = _check(_manifest(rebuilt_at="2026-11-08T00:00:00+00:00"), changed="2026-11-09T19:00:00+00:00")
    assert "MANIFEST_PREDATES_RETRIEVAL_CODE" in reasons


def test_embedding_model_change_is_refused():
    assert "EMBEDDING_MODEL_CHANGED" in _check(_manifest(), embedding={"provider": "LOCAL", "model": "other"})
    assert "EMBEDDING_MODEL_CHANGED" in _check(_manifest(), embedding={"provider": "AZURE", "model": "bge-small"})


def test_failed_source_rebuild_is_refused():
    manifest = _manifest(sources={"jira_qa": {"status": "OK"}, "github_dita": {"status": "FAILED", "error": "x"}})
    assert _check(manifest) == ["SOURCE_REBUILD_FAILED:github_dita"]


def test_production_or_dirty_or_stale_manifest_is_refused():
    assert "MANIFEST_NOT_STAGING" in _check(_manifest(environment="production"))
    assert "REBUILT_FROM_UNCOMMITTED_RETRIEVAL_CODE" in _check(
        _manifest(source={"commit": "abc", "retrieval_code_dirty": True})
    )
    stale = _manifest()
    stale["collections"]["jira_qa"]["stale_chunk_ids"] = ["G-1::problem_chunk::3"]
    assert "STALE_CHUNK_IDS:jira_qa" in _check(stale)
    empty = _manifest()
    empty["collections"]["aem_guides"]["chunk_count"] = 0
    assert "COLLECTION_MISSING_OR_EMPTY:aem_guides" in _check(empty)


def test_code_fingerprint_changes_with_retrieval_code(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = gate.code_fingerprint(tmp_path, ("a.py",))
    (tmp_path / "a.py").write_text("x = 2\n")
    assert gate.code_fingerprint(tmp_path, ("a.py",))["sha256"] != first["sha256"]


def test_repo_retrieval_code_paths_exist():
    missing = [p for p in gate.RETRIEVAL_CODE_PATHS if not (gate.REPO / p).exists()]
    assert missing == []


# --- corpus identity --------------------------------------------------------------------------


def test_corpus_digest_is_order_independent_and_content_sensitive():
    rows = [{"id": "b", "document": "two", "metadata": {"k": 1}}, {"id": "a", "document": "one", "metadata": {}}]
    assert gate.corpus_digest(rows) == gate.corpus_digest(list(reversed(rows)))
    changed = [dict(rows[0], document="TWO"), rows[1]]
    assert gate.corpus_digest(changed)["corpus_sha256"] != gate.corpus_digest(rows)["corpus_sha256"]
    assert gate.corpus_digest(rows)["chunk_count"] == 2


def test_stale_chunk_ids_are_stored_ids_the_rebuild_did_not_write():
    assert gate.stale_chunk_ids(["a", "b", "c"], ["a", "c"]) == ["b"]


# --- staging isolation ------------------------------------------------------------------------


def test_staging_dir_refuses_remote_chroma(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_HOST", "chroma.prod")
    with pytest.raises(gate.GateRefused) as err:
        gate.prepare_staging_dir(tmp_path / "s", production_dirs=[], create=True)
    assert err.value.code == "REMOTE_CHROMA_REFUSED"


def test_staging_dir_refuses_production_path(tmp_path, monkeypatch):
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    prod = tmp_path / "storage" / "chroma"
    prod.mkdir(parents=True)
    for target in (prod, prod / "inner", tmp_path / "storage"):
        with pytest.raises(gate.GateRefused) as err:
            gate.prepare_staging_dir(target, production_dirs=[prod], create=True)
        assert err.value.code == "PRODUCTION_PATH_REFUSED"


def test_staging_dir_refuses_unmarked_non_empty_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "chroma.sqlite3").write_text("x")
    with pytest.raises(gate.GateRefused) as err:
        gate.prepare_staging_dir(tmp_path / "s", production_dirs=[], create=True)
    assert err.value.code == "UNMARKED_DIRECTORY_REFUSED"


def test_staging_dir_is_created_marked_and_bound(tmp_path, monkeypatch):
    monkeypatch.delenv("CHROMA_HOST", raising=False)
    monkeypatch.delenv("CHROMA_PERSIST_DIR", raising=False)
    monkeypatch.delenv("STORAGE_PATH", raising=False)
    monkeypatch.delenv("JIRA_SQL_ENRICHMENT", raising=False)
    target = gate.prepare_staging_dir(tmp_path / "s", production_dirs=[], create=True)
    assert (target / gate.STAGING_MARKER).exists()
    assert gate.os.environ["CHROMA_PERSIST_DIR"] == str(target / "chroma")
    assert gate.os.environ["STORAGE_PATH"] == str(target / "storage")
    assert gate.os.environ["JIRA_SQL_ENRICHMENT"] == "false"
    # Re-opening the marked directory is allowed even without create.
    assert gate.prepare_staging_dir(tmp_path / "s", production_dirs=[], create=False) == target


# --- dispositions -------------------------------------------------------------------------------


def _disposition(did, claim, disposition, **extra):
    return {
        "disposition_id": did,
        "candidate": claim,
        "disposition": disposition,
        "evidence_ids": extra.pop("evidence_ids", ["ev-1"]),
        "source_fact_ids": extra.pop("source_fact_ids", ["fact-1"]),
        **extra,
    }


def test_final_dispositions_follow_writer_then_runtime_lane():
    payload = {
        "coverage_dispositions": [
            _disposition("d1", "Saves in New Editor", "ACCEPTANCE_CONTRACT"),
            _disposition("d2", "Legacy Editor parity", "ACCEPTANCE_CONTRACT"),
            _disposition("d3", "Is it on for folder profiles?", "ACCEPTANCE_TBD"),
            _disposition("d4", "Regression of map preview", "SEMANTIC_REGRESSION"),
            _disposition("d5", "Guessed customer flow", "UNSUPPORTED_INFERENCE"),
            _disposition("d6", "Dropped acceptance contract", "ACCEPTANCE_CONTRACT"),
        ],
        "written_acceptance_criteria": [
            {"outcome": "Saving keeps the map open.", "source_disposition_ids": ["d1"],
             "sub_points": [{"text": "Does the Legacy Editor match?", "kind": "TBD_QUESTION",
                             "source_disposition_ids": ["d2"]}]},
        ],
    }
    finals = {r["disposition_id"]: r["final_disposition"] for r in gate.disposition_rows(payload)}
    assert finals == {"d1": "UAC", "d2": "TBD", "d3": "TBD", "d4": "TEST_PLAN", "d5": "OUT_OF_SCOPE", "d6": "UNROUTED"}


def test_writer_projection_status_wins_over_lane_and_written_references():
    payload = {
        "coverage_dispositions": [
            _disposition("d1", "Research regression check", "SEMANTIC_REGRESSION"),
            _disposition("d2", "Contract kept only outside the UAC", "ACCEPTANCE_CONTRACT"),
            _disposition("d3", "Excluded contract", "ACCEPTANCE_CONTRACT"),
            _disposition("d4", "Variant of AC 1", "PROPOSED_ACCEPTANCE_CONTRACT"),
        ],
        "written_acceptance_criteria": [],
        "structured_plan": {"writer_projection_records": [
            {"coverage_disposition_id": "d1", "status": "TEST_PLAN_REGRESSION"},
            {"coverage_disposition_id": "d2", "status": "RETAINED_QE_REGRESSION"},
            {"coverage_disposition_id": "d3", "status": "EXPLICITLY_EXCLUDED"},
            {"coverage_disposition_id": "d4", "status": "ATTACHED_VARIANT"},
        ]},
    }
    finals = {r["disposition_id"]: r["final_disposition"] for r in gate.disposition_rows(payload)}
    assert finals == {"d1": "TEST_PLAN", "d2": "TEST_PLAN", "d3": "OUT_OF_SCOPE", "d4": "UAC"}


def test_every_writer_projection_status_is_mapped():
    sys.path.insert(0, str(gate.BACKEND))
    try:
        from app.core.schemas_canonical_test_plan_runtime import WriterProjectionStatus
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"backend schema not importable: {exc}")
    assert {s.value for s in WriterProjectionStatus} == set(gate._WRITER_PROJECTION)


def test_every_runtime_lane_maps_to_a_final_disposition_or_is_deliberately_unrouted():
    backend = gate.BACKEND
    sys.path.insert(0, str(backend))
    try:
        from app.core.schemas_canonical_test_plan_runtime import CoverageDisposition
    except Exception as exc:  # pragma: no cover - backend deps unavailable
        pytest.skip(f"backend schema not importable: {exc}")
    acceptance = {"ACCEPTANCE_CONTRACT", "PROPOSED_ACCEPTANCE_CONTRACT"}
    for value in CoverageDisposition:
        if value.value in acceptance:
            assert value.value not in gate._UNRENDERED_DISPOSITION
        else:
            assert gate._UNRENDERED_DISPOSITION.get(value.value) in gate.FINAL_DISPOSITIONS, value


def test_disposition_signature_ignores_run_specific_ids():
    a = gate.disposition_rows({"coverage_dispositions": [_disposition("run1-x", "Claim A", "OPEN_QUESTION")]})
    b = gate.disposition_rows({"coverage_dispositions": [_disposition("run2-y", "claim  a", "OPEN_QUESTION")]})
    assert gate.disposition_signature(a) == gate.disposition_signature(b)


# --- UAC style ---------------------------------------------------------------------------------


def _case(**overrides):
    base = dict(
        slot="blocked_action_negative",
        jira_key="GUIDES-1",
        tenant_id="kone",
        customer="Acme",
        components=("Editor",),
        decision_text="Check-in is blocked while the topic is locked",
        newest_verification_comment="Verified on 2026.11: lock blocks check-in",
        attachment_filename="lock.log",
        critical_branches=(
            gate.Branch("New Editor", ("New Editor",), "lock check-in New Editor", supported=True),
            gate.Branch("Legacy Editor", ("Legacy Editor",), "lock check-in Legacy Editor", supported=True),
        ),
        required_terms=("Check In",),
        requires_negative_contract=True,
    )
    base.update(overrides)
    return gate.ReplayCase(**base)


def test_style_rejects_given_when_then_and_requires_terms_branches_and_negative_contract():
    problems = gate.uac_style_problems(["Given a locked topic, then Check In works in New Editor."], _case())
    assert any(p.startswith("GIVEN_WHEN_THEN_PHRASING") for p in problems)
    assert "UNNAMED_BRANCH: Legacy Editor" in problems
    assert "MISSING_NEGATIVE_CONTRACT" in problems
    ok = gate.uac_style_problems(
        ["In the New Editor and the Legacy Editor, Check In is not available while another user holds the lock."],
        _case(),
    )
    assert ok == []


def test_style_allows_when_mid_sentence_and_checks_exact_terminology():
    texts = ["The map opens in the New Editor and Legacy Editor when Check In is not allowed."]
    assert gate.uac_style_problems(texts, _case()) == []
    assert "MISSING_EXACT_TERM: Check In" in gate.uac_style_problems([t.replace("Check In", "check in") for t in texts], _case())


# --- replay evaluation ------------------------------------------------------------------------


def _index(case, *, customer_leak=False, with_comment=True, docs_hit=True):
    chunks = [
        {"id": f"{case.jira_key}::acceptance_criteria_chunk::0", "document": f"Acceptance criteria:\n{case.decision_text}",
         "metadata": {"jira_key": case.jira_key, "chunk_type": "acceptance_criteria_chunk", "customer": "Acme"}},
        {"id": f"{case.jira_key}::attachment_signal_chunk::1", "document": "Attachment text:\nlock.log:\nERROR lock",
         "metadata": {"jira_key": case.jira_key, "chunk_type": "attachment_signal_chunk", "customer": "Acme"}},
    ]
    if with_comment:
        chunks.append({"id": f"{case.jira_key}::comment_chunk::0",
                       "document": f"Discussion:\n[2026-11-09] qa: {case.newest_verification_comment}",
                       "metadata": {"jira_key": case.jira_key, "chunk_type": "comment_chunk", "customer": "Acme"}})
    docs = [{"id": "aem_1", "document": "New Editor and Legacy Editor block Check In on locked topics.",
             "metadata": {"title": "Locking"}}] if docs_hit else []

    def chunks_for_key(key):
        return [c for c in chunks if c["metadata"]["jira_key"] == key]

    def search(corpus, query, k, where):
        if corpus == "jira_qa":
            rows = list(chunks)
            if where and "customer" in where:
                leak = {"id": "OTHER-1::summary_chunk::0", "document": "lock",
                        "metadata": {"customer": "Globex", "jira_key": "OTHER-1"}}
                rows = [leak] if customer_leak else rows
            elif where and "jira_key" in where:
                rows = [r for r in rows if r["metadata"]["jira_key"] == where["jira_key"]]
            return rows[:k]
        if corpus == "aem_guides":
            return docs[:k]
        return []

    return chunks_for_key, search


def _run(case, *, branches_in_uac=("New Editor", "Legacy Editor"), extra=()):
    texts = " and the ".join(branches_in_uac)
    outcome = f"In the {texts}, Check In is not available while another user holds the lock."
    payload = {
        "coverage_dispositions": [_disposition("d1", outcome, "ACCEPTANCE_CONTRACT"), *extra],
        "written_acceptance_criteria": [{"outcome": outcome, "source_disposition_ids": ["d1"], "sub_points": []}],
    }
    return gate.CaseRun(payload=payload)


def _evaluate(case, runs, **index_kw):
    chunks_for_key, search = _index(case, **index_kw)
    retrieval = gate.evaluate_retrieval(case, chunks_for_key=chunks_for_key, search=search)
    return gate.build_reports([case], [[retrieval] for _ in runs], [[r] for r in runs], manifest={"collections": {}})


def test_replay_passes_when_every_rule_holds():
    case = _case()
    _, disposition, passed = _evaluate(case, [_run(case), _run(case)])
    assert passed, disposition["failures"]
    assert disposition["cases"][0]["replays"][0]["disposition_counts"]["UAC"] == 1


def test_replay_fails_when_newest_verification_comment_is_not_indexed():
    case = _case()
    _, disposition, passed = _evaluate(case, [_run(case), _run(case)], with_comment=False)
    assert not passed
    assert "blocked_action_negative:NOT_INDEXED:newest_verification_comment" in disposition["failures"]


def test_replay_fails_on_cross_customer_evidence():
    case = _case()
    _, disposition, passed = _evaluate(case, [_run(case), _run(case)], customer_leak=True)
    assert not passed
    assert any("CROSS_CUSTOMER_EVIDENCE" in f for f in disposition["failures"])


def test_replay_fails_when_supported_branch_is_removed():
    case = _case()
    runs = [_run(case, branches_in_uac=("New Editor",)), _run(case, branches_in_uac=("New Editor",))]
    _, disposition, passed = _evaluate(case, runs)
    assert not passed
    assert any("SUPPORTED_BRANCH_REMOVED:Legacy Editor" in f for f in disposition["failures"])


def test_critical_branch_without_evidence_passes_only_when_marked_tbd():
    case = _case(critical_branches=(gate.Branch("Folder profile off", ("folder profile",), "folder profile off", supported=False),),
                 requires_negative_contract=False, required_terms=())
    no_tbd = _run(case, branches_in_uac=("New Editor",))
    _, disposition, passed = _evaluate(case, [no_tbd, no_tbd], docs_hit=False)
    assert any("CRITICAL_BRANCH_WITHOUT_EVIDENCE_OR_TBD:Folder profile off" in f for f in disposition["failures"])
    tbd = _run(case, branches_in_uac=("New Editor",),
               extra=[_disposition("d9", "Does the folder profile off state hide Check In?", "ACCEPTANCE_TBD")])
    _, disposition, passed = _evaluate(case, [tbd, tbd], docs_hit=False)
    assert passed, disposition["failures"]


def test_unsupported_research_finding_in_uac_fails():
    case = _case()
    bad = _run(case)
    bad.payload["coverage_dispositions"].append(
        _disposition("d7", "Guessed bulk check-in", "ACCEPTANCE_CONTRACT", research_derived=True, evidence_ids=[])
    )
    bad.payload["written_acceptance_criteria"].append(
        {"outcome": "Bulk Check In is not offered for locked topics in the New Editor and Legacy Editor.",
         "source_disposition_ids": ["d7"], "sub_points": []}
    )
    _, disposition, passed = _evaluate(case, [bad, bad])
    assert not passed
    assert any("UNSUPPORTED_FINDING_IN_UAC" in f for f in disposition["failures"])


def test_replays_with_different_dispositions_fail():
    case = _case()
    other = _run(case)
    other.payload["coverage_dispositions"].append(_disposition("d8", "Extra question?", "OPEN_QUESTION"))
    _, disposition, passed = _evaluate(case, [_run(case), other])
    assert not passed
    assert "blocked_action_negative:DISPOSITIONS_NOT_IDENTICAL_ACROSS_REPLAYS" in disposition["failures"]


def test_single_replay_never_passes():
    case = _case()
    _, disposition, passed = _evaluate(case, [_run(case)])
    assert not passed
    assert "FEWER_THAN_TWO_REPLAYS" in disposition["failures"]


def test_stale_ids_in_manifest_fail_the_replay():
    case = _case()
    chunks_for_key, search = _index(case)
    retrieval = gate.evaluate_retrieval(case, chunks_for_key=chunks_for_key, search=search)
    manifest = {"collections": {"jira_qa": {"stale_chunk_ids": ["GUIDES-1::problem_chunk::7"]}}}
    _, disposition, passed = gate.build_reports([case], [[retrieval], [retrieval]], [[_run(case)], [_run(case)]], manifest=manifest)
    assert not passed
    assert "STALE_CHUNK_IDS_AFTER_REBUILD" in disposition["failures"]


# --- case file --------------------------------------------------------------------------------


def test_checked_in_case_template_is_refused_until_qe_fills_it():
    with pytest.raises(gate.GateRefused) as err:
        gate.load_cases(gate.DEFAULT_CASES)
    assert err.value.code == "CASE_EXPECTATIONS_UNFILLED"


def test_case_file_must_hold_exactly_the_five_slots(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"schema_version": gate.CASES_SCHEMA, "cases": [{"slot": "save_reopen"}]}))
    with pytest.raises(gate.GateRefused) as err:
        gate.load_cases(path)
    assert err.value.code == "CASE_SET_NOT_FIXED"


# --- backend adapters (no Chroma: the write function is faked) ------------------------------


def test_write_recorder_catches_aliased_and_module_level_writers(monkeypatch):
    import types

    sys.path.insert(0, str(gate.BACKEND))
    try:
        from app.services import vector_store_service as vss
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"backend not importable: {exc}")

    def fake_add(collection_name, ids, *args, **kwargs):
        return True

    monkeypatch.setattr(vss, "add_documents", fake_add)
    writer = types.ModuleType("fake_aliased_writer")
    writer.chroma_add_documents = fake_add  # like crawl_service / dita_pdf_index_service
    monkeypatch.setitem(sys.modules, "fake_aliased_writer", writer)

    with gate.WriteRecorder() as recorder:
        writer.chroma_add_documents("aem_guides", ["aem_0", "aem_1"])
        vss.add_documents("jira_qa", ["G-1::summary_chunk::0"])  # function-local imports read this
    assert recorder.written == {"aem_guides": {"aem_0", "aem_1"}, "jira_qa": {"G-1::summary_chunk::0"}}
    assert writer.chroma_add_documents is fake_add and vss.add_documents is fake_add  # restored


def test_failed_writes_are_not_recorded(monkeypatch):
    sys.path.insert(0, str(gate.BACKEND))
    try:
        from app.services import vector_store_service as vss
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"backend not importable: {exc}")
    monkeypatch.setattr(vss, "add_documents", lambda collection_name, ids, *a, **k: False)
    with gate.WriteRecorder() as recorder:
        vss.add_documents("jira_qa", ["x"])
    assert recorder.written == {}


def test_staging_binding_drops_remote_host_added_later(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_HOST", "added-by-dotenv")
    for key in ("CHROMA_PERSIST_DIR", "STORAGE_PATH", "JIRA_SQL_ENRICHMENT"):
        monkeypatch.delenv(key, raising=False)
    gate.bind_staging_environment(tmp_path)
    assert "CHROMA_HOST" not in gate.os.environ
    assert gate.os.environ["STORAGE_PATH"] == str(tmp_path / "storage")


def test_open_staging_refuses_when_backend_already_imported(tmp_path, monkeypatch):
    import types

    for key in ("CHROMA_HOST", "CHROMA_PERSIST_DIR", "STORAGE_PATH", "JIRA_SQL_ENRICHMENT"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(sys.modules, "app", types.ModuleType("app"))
    with pytest.raises(gate.GateRefused) as err:
        gate.open_staging(tmp_path / "s", create=True)
    assert err.value.code == "BACKEND_IMPORTED_BEFORE_STAGING"


def test_check_command_refuses_without_manifest(tmp_path, capsys):
    code = gate.main(["check", "--manifest", str(tmp_path / "missing.json"), "--no-embedding-check"])
    assert code == 2
    assert "MANIFEST_MISSING" in capsys.readouterr().out


def test_replay_command_requires_two_replays(tmp_path):
    with pytest.raises(SystemExit):
        gate.main(["replay", "--staging-chroma-dir", str(tmp_path), "--replays", "1"])


_STAGING_SCRIPT = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
import rag_index_freshness_gate as gate
root = gate.open_staging(gate.Path(sys.argv[2]), create=True)
from app.services import vector_store_service as vss
vec = [[0.1, 0.2, 0.3]]
# A chunk left over from an earlier build: written outside this rebuild's recorder.
vss.add_documents("jira_qa", ["G-1::problem_chunk::1"], ["old"], [{"jira_key": "G-1"}], vec)
with gate.WriteRecorder() as recorder:
    vss.add_documents("jira_qa", ["G-1::problem_chunk::0"], ["new"], [{"jira_key": "G-1"}], vec)
    vss.add_documents("aem_guides", ["aem_0"], ["doc"], [{"url": "u"}], vec)
print(json.dumps({"collections": gate.scan_collections(recorder.written),
                  "persist": gate.os.environ["CHROMA_PERSIST_DIR"]}))
"""


def test_scan_collections_against_real_embedded_chroma(tmp_path):
    import subprocess

    pytest.importorskip("chromadb")
    env = {k: v for k, v in gate.os.environ.items() if k not in ("CHROMA_HOST", "CHROMA_PERSIST_DIR", "STORAGE_PATH")}
    staging = tmp_path / "staging"
    proc = subprocess.run(
        [sys.executable, "-c", _STAGING_SCRIPT, str(HERE), str(staging)],
        capture_output=True, text=True, timeout=300, env=env, cwd=str(tmp_path),
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["persist"] == str(staging.resolve() / "chroma")
    jira = result["collections"]["jira_qa"]
    assert jira["chunk_count"] == 2
    assert jira["stale_chunk_ids"] == ["G-1::problem_chunk::1"]
    assert result["collections"]["aem_guides"]["stale_chunk_ids"] == []
    assert (staging / "chroma").is_dir() and not (gate.BACKEND / "storage" / "chroma_db" / "staging").exists()


# --- runner integration -------------------------------------------------------------------------


def _fresh_manifest_file(tmp_path, **overrides):
    fields = {
        "retrieval_code": {"sha256": gate.code_fingerprint()["sha256"], "last_changed_at": gate.code_last_changed_at()},
        "rebuilt_at": gate.utc_now(),
        **overrides,
    }
    manifest = _manifest(**fields)
    path = tmp_path / gate.MANIFEST_FILE
    path.write_text(json.dumps(manifest))
    return path


def test_runner_refuses_without_manifest(capsys):
    import run

    assert run.check_index_freshness("") is False
    assert "no RAG index manifest" in capsys.readouterr().out


def test_runner_accepts_fresh_manifest_and_refuses_stale_one(tmp_path, capsys):
    import run

    assert run.check_index_freshness(str(_fresh_manifest_file(tmp_path))) is True
    stale = _fresh_manifest_file(tmp_path, rebuilt_at="2020-01-01T00:00:00+00:00")
    assert run.check_index_freshness(str(stale)) is False
    assert "MANIFEST_PREDATES_RETRIEVAL_CODE" in capsys.readouterr().out
