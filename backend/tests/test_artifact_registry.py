"""Tests for content-addressed dataset ZIP reuse (artifact registry)."""

from uuid import uuid4

import pytest

from app.services.artifact_fingerprint_service import (
    fingerprint_dataset_config_dict,
    json_blob_sha256,
)


def test_fingerprint_stable_across_dict_key_order():
    a = {"z": 1, "a": {"y": 2, "b": 3}}
    b = {"a": {"b": 3, "y": 2}, "z": 1}
    assert json_blob_sha256(a) == json_blob_sha256(b)


def test_fingerprint_differs_when_seed_changes():
    base = {
        "name": "X",
        "seed": "s1",
        "root_folder": "/c",
        "windows_safe_filenames": True,
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True}],
    }
    other = {**base, "seed": "s2"}
    assert fingerprint_dataset_config_dict(base) != fingerprint_dataset_config_dict(other)


def test_meta_keys_do_not_affect_fingerprint():
    cfg = {
        "name": "X",
        "seed": "s1",
        "root_folder": "/c",
        "windows_safe_filenames": True,
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "t", "pretty_print": True}],
    }
    with_meta = {**cfg, "__artifact_tenant_id__": "tenant-a", "__artifact_meta__": {"x": 1}}
    assert fingerprint_dataset_config_dict(cfg) == fingerprint_dataset_config_dict(with_meta)


_AUTH_HEADERS = {"Authorization": "Bearer test-token"}

_BUILDER_LIKE = {
    "name": "Artifact reuse dataset",
    "seed": "artifact-reuse-seed",
    "root_folder": "/content/dam/dataset-studio",
    "windows_safe_filenames": True,
    "doctype_topic": '<!DOCTYPE topic PUBLIC "-//OASIS//DTD DITA Topic//EN" "technicalContent/dtd/topic.dtd">',
    "doctype_map": '<!DOCTYPE map PUBLIC "-//OASIS//DTD DITA Map//EN" "technicalContent/dtd/map.dtd">',
}


def test_post_jobs_second_identical_config_reuses_zip(client, monkeypatch):
    monkeypatch.setenv("ARTIFACT_REUSE_ENABLED", "true")
    import app.services.dataset_job_service as djs

    monkeypatch.setattr(djs, "is_artifact_reuse_enabled", lambda: True)

    uid = uuid4().hex[:10]
    config = {
        **_BUILDER_LIKE,
        "name": f"Artifact reuse dataset {uid}",
        "seed": f"artifact-reuse-seed-{uid}",
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "treuse", "pretty_print": True}],
    }
    r1 = client.post("/api/v1/jobs", json={"config": config}, headers=_AUTH_HEADERS)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    assert d1.get("status") == "completed"
    assert d1.get("cache_hit") is not True

    r2 = client.post("/api/v1/jobs", json={"config": config}, headers=_AUTH_HEADERS)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2.get("cache_hit") is True
    assert d2.get("reused_from_job_id") == d1["id"]
    assert d2["id"] != d1["id"]
    assert d2.get("status") == "completed"


def test_post_jobs_no_reuse_when_disabled(client, monkeypatch):
    monkeypatch.setenv("ARTIFACT_REUSE_ENABLED", "false")
    import app.services.dataset_job_service as djs

    monkeypatch.setattr(djs, "is_artifact_reuse_enabled", lambda: False)

    uid = uuid4().hex[:10]
    config = {
        **_BUILDER_LIKE,
        "name": f"No reuse {uid}",
        "seed": f"no-reuse-seed-{uid}",
        "recipes": [{"type": "inline_formatting_nested", "id_prefix": "tnoreuse", "pretty_print": True}],
    }
    r1 = client.post("/api/v1/jobs", json={"config": config}, headers=_AUTH_HEADERS)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    r2 = client.post("/api/v1/jobs", json={"config": config}, headers=_AUTH_HEADERS)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert not d2.get("cache_hit")
    assert d2["id"] != d1["id"]
