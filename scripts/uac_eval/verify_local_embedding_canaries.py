"""Offline candidate-interpreter/model check against frozen export vectors.

No backend import, live database, model download, indexing or service operation.
Run with the candidate backend venv under `unshare --net` on the VM. Success is
sampled compatibility only, NOT permission to merge corpora or resume writers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys


class CheckFailed(Exception):
    pass


def require(condition, reason):
    if not condition:
        raise CheckFailed(reason)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_hash(directory):
    require(directory.is_absolute() and directory.is_dir() and not directory.is_symlink(), "MODEL_DIRECTORY_REQUIRED")
    entries = []
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "MODEL_SYMLINK_REQUIRES_REVIEW")
        if path.is_file():
            entries.append((path.relative_to(directory).as_posix(), file_hash(path)))
        else:
            require(path.is_dir(), "MODEL_SPECIAL_FILE_REJECTED")
    require(bool(entries), "MODEL_EMPTY")
    return hashlib.sha256(json.dumps(entries).encode()).hexdigest()


def finite_vector(value):
    require(isinstance(value, list) and bool(value), "INVALID_VECTOR")
    require(all(type(x) in (int, float) and math.isfinite(x) for x in value) and any(value), "INVALID_VECTOR")
    return value


def read_canaries(path, expected_hash):
    require(re.fullmatch(r"[0-9a-f]{64}", expected_hash) is not None, "INVALID_EXPORT_HASH")
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), "EXPORT_FILE_REQUIRED")
    require(file_hash(path) == expected_hash, "EXPORT_HASH_MISMATCH")
    rows, ids, documents = [], set(), set()
    with path.open("rb") as stream:
        for _ in range(100):
            line = stream.readline(16 * 1024 * 1024 + 1)
            if not line:
                break
            require(len(line) <= 16 * 1024 * 1024, "EXPORT_ROW_TOO_LARGE")
            row = json.loads(line)
            require(isinstance(row, dict), "INVALID_EXPORT_ROW")
            identifier, text = row.get("id"), row.get("document")
            if not isinstance(text, str) or not text.strip():
                continue
            require(isinstance(identifier, str) and bool(identifier) and len(text) <= 1_000_000, "INVALID_EXPORT_ROW")
            if identifier in ids or text in documents:
                continue
            vector = finite_vector(row.get("embedding"))
            ids.add(identifier)
            documents.add(text)
            rows.append((text, vector))
            if len(rows) == 3:
                break
    require(len(rows) == 3, "THREE_DISTINCT_CANARIES_REQUIRED")
    return rows


def compare_canaries(rows, encode, expected_dimension):
    # Same fixed tolerance as ingest_customer_csv.embed_with_stored_canaries.
    # No configurable tolerance or dimension coercion.
    actual = encode([row[0] for row in rows])
    actual = actual.tolist() if hasattr(actual, "tolist") else actual
    require(isinstance(actual, list) and len(actual) == len(rows), "ENCODING_INCOMPLETE")
    for (_, stored), encoded in zip(rows, actual):
        finite_vector(encoded)
        require(len(stored) == len(encoded) == expected_dimension, "DIMENSION_MISMATCH")
        require(all(math.isclose(a, b, rel_tol=1e-4, abs_tol=1e-6) for a, b in zip(stored, encoded)),
                "STORED_VECTOR_MISMATCH")
    return {"status": "SAMPLED_STORED_VECTORS_MATCH", "samples": len(rows), "dimension": expected_dimension}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", required=True, type=Path)
    parser.add_argument("--export", required=True, nargs=2, action="append", metavar=("JSONL_PATH", "SHA256"))
    parser.add_argument("--expected-dimension", type=int, default=384)
    args = parser.parse_args(argv)
    report = {"schema_version": "offline-embedding-canary-v1", "status": "BLOCKED",
              "database_opened": False, "services_changed": False, "index_writes": False,
              "whole_corpus_model_identity_verified": False, "live_backend_verified": False,
              "resume_writers_authorized": False, "samples": []}
    try:
        require(sys.version_info >= (3, 11) and sys.version_info.releaselevel == "final"
                and hasattr(sys, "get_int_max_str_digits"), "FINAL_PYTHON_311_OR_NEWER_REQUIRED")
        require(1 <= args.expected_dimension <= 65536, "INVALID_EXPECTED_DIMENSION")
        before = model_hash(args.model_path)
        exports = [(Path(path), digest, read_canaries(Path(path), digest)) for path, digest in args.export]
        os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1",
                          TOKENIZERS_PARALLELISM="false")
        sys.dont_write_bytecode = True
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(str(args.model_path), device="cpu", local_files_only=True, trust_remote_code=False)
        for path, digest, rows in exports:
            receipt = compare_canaries(rows, lambda texts: model.encode(texts, convert_to_numpy=True), args.expected_dimension)
            require(file_hash(path) == digest, "EXPORT_CHANGED_DURING_PROBE")
            report["samples"].append({"export_sha256": digest, **receipt})
        require(model_hash(args.model_path) == before, "MODEL_CHANGED_DURING_PROBE")
        report.update(status="PASS_OFFLINE_SAMPLES_ONLY", model_sha256=before,
                      python=list(sys.version_info), provider="LOCAL")
    except CheckFailed as error:
        report["reason"] = str(error)  # only fixed, locally defined categories
    except Exception:
        report["reason"] = "IMPORT_ENCODE_OR_FILE_FAILED"  # no raw exception/documents/auth
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS_OFFLINE_SAMPLES_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
