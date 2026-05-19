"""Canonical JSON + SHA-256 fingerprints for dataset artifact reuse."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

# Stripped before fingerprinting and validation (tenant hints, debug meta).
ARTIFACT_META_KEYS = frozenset({"__artifact_tenant_id__", "__artifact_meta__"})


def strip_artifact_meta(config_dict: dict[str, Any]) -> dict[str, Any]:
    """Return config without internal artifact-registry keys."""
    return {k: v for k, v in config_dict.items() if k not in ARTIFACT_META_KEYS}


def canonicalize_json(value: Any) -> Any:
    """Recursively sort dict keys for stable serialization."""
    if isinstance(value, dict):
        return {k: canonicalize_json(value[k]) for k in sorted(value.keys())}
    if isinstance(value, list):
        return [canonicalize_json(item) for item in value]
    if isinstance(value, tuple):
        return [canonicalize_json(item) for item in value]
    if isinstance(value, BaseModel):
        return canonicalize_json(value.model_dump(mode="json"))
    return value


def json_blob_sha256(payload: Any) -> str:
    """Return hex SHA-256 of canonical JSON (deterministic, UTF-8)."""
    canon = canonicalize_json(payload)
    raw = json.dumps(canon, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def fingerprint_dataset_config_dict(config: dict[str, Any]) -> str:
    """Fingerprint a normalized dataset job config (JSON-safe, no meta keys)."""
    stripped = strip_artifact_meta(dict(config))
    return json_blob_sha256(stripped)
