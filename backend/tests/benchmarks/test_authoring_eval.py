"""Benchmark harness smoke tests (deterministic: vision + LLM stubbed)."""

from pathlib import Path

import pytest

from app.benchmarks.authoring_eval.models import BenchmarkManifest
from app.benchmarks.authoring_eval.runner import evaluate_manifest
from app.services.chat_dita_authoring_service import ChatDitaAuthoringService


def _dataset_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "benchmarks" / "authoring_eval" / "dataset"


@pytest.mark.asyncio
async def test_manifest_smoke_all_cases_pass():
    root = _dataset_dir()
    manifest = BenchmarkManifest.load_yaml(root / "manifest.yaml")
    service = ChatDitaAuthoringService()
    report = await evaluate_manifest(service, manifest, dataset_root=root, mock_aem_save=True)
    assert report.aggregates["n_cases"] == len(manifest.cases)
    assert report.aggregates["all_assertions_passed"] is True, report.aggregates.get("failed_case_ids")
    assert report.aggregates["xml_validity_rate"] == 1.0
    assert report.aggregates["structural_correctness_rate"] == 1.0
    assert report.aggregates["mean_over_copying_risk"] == 0.0
    assert report.aggregates["insertion_success_rate"] == 1.0


@pytest.mark.asyncio
async def test_over_copying_detects_reference_id():
    from app.benchmarks.authoring_eval.fingerprints import extract_reference_fingerprints, over_copying_score

    ref = '<task id="SECRET_REF_ID"><title>T</title><taskbody><steps><step><cmd>x</cmd></step></steps></taskbody></task>'
    gen_ok = '<task id="new1"><title>T</title><taskbody><steps><step><cmd>x</cmd></step></steps></taskbody></task>'
    gen_bad = '<task id="SECRET_REF_ID"><title>T</title><taskbody><steps><step><cmd>x</cmd></step></steps></taskbody></task>'
    fp = extract_reference_fingerprints(ref)
    assert over_copying_score(gen_ok, ref_ids=fp["ids"], ref_hrefs=fp["hrefs"], ref_conrefs=fp["conrefs"])[0] == 0.0
    assert over_copying_score(gen_bad, ref_ids=fp["ids"], ref_hrefs=fp["hrefs"], ref_conrefs=fp["conrefs"])[0] == 1.0
