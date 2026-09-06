"""Export the two approved disposable VM copies; never merge or open live stores.

Maintenance-specific helper, deliberately pinned to the verified TRIAL below and
Chroma 1.5.9. Requires runtime-probe-report.json from the preceding copy-only smoke
test. Keep the original services stopped while this maintenance is in progress.

Run with the VM backend/venv interpreter using -I -B and an external timeout.
Outputs go to a new private /root/aem-chroma-export-* directory, not the checkout.
Only a valid COMPLETE.json plus matching artifact hashes denotes completion.
Raw exports/configuration/private.log may contain internal content: do not commit
or share them. The printed summary contains counts and hashes, not corpus values.
Chroma can internally write to the disposable copies even with migrations=validate.
PASS_EXPORT_ONLY is not merge approval, model parity, or full HNSW validation.
"""

from pathlib import Path
from importlib import metadata
from numbers import Real
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import stat
import sys
import tempfile
import time
import traceback

TRIAL = Path("/root/aem-chroma-runtime-hMTaHiiu")
LABELS = ("app-storage", "backend-storage")
FIELDS = ("documents", "metadatas", "embeddings", "uris")


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def signature(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def snapshot(path):
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=10)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")
        deadline = time.monotonic() + 120
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        require(db.execute("SELECT tenant_id,name FROM databases ORDER BY tenant_id,name").fetchall() ==
                [("default_tenant", "default_database")], "NAMESPACE_CHANGED")
        migrations = db.execute("SELECT dir,version,filename,sql,hash FROM migrations ORDER BY dir,version").fetchall()
        hashes = [r[4] for r in migrations]
        require(hashes and all(isinstance(h, str) and re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{64}", h) for h in hashes), "BAD_MIGRATION_HASH")
        lengths = {len(h) for h in hashes}
        require(len(lengths) == 1, "MIXED_MIGRATION_HASHES")
        rows = db.execute("SELECT c.id,c.name,c.dimension,c.config_json_str,c.schema_str FROM collections c JOIN databases d ON c.database_id=d.id ORDER BY c.name,c.id").fetchall()
        require(rows and len(rows) == db.execute("SELECT COUNT(*) FROM collections").fetchone()[0], "BAD_COLLECTION_SCOPE")
        catalog = {}
        for cid, name, dimension, config, schema in rows:
            require(isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", name) and name not in catalog, "BAD_COLLECTION_NAME")
            segments = db.execute("SELECT id FROM segments WHERE collection=? AND scope=?", (cid, "METADATA")).fetchall()
            require(len(segments) == 1, "AMBIGUOUS_SEGMENT")
            ids = [r[0] for r in db.execute("SELECT embedding_id FROM embeddings WHERE segment_id=? ORDER BY embedding_id", (segments[0][0],))]
            require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), "BAD_RECORD_IDS")
            catalog[name] = {"id": cid, "dimension": dimension, "ids": ids, "config_json_str": config, "schema_str": schema}
        # Also detect metadata/document changes during export; this is not API-vs-SQL reconciliation.
        content = hashlib.sha256()
        for table in ("embedding_metadata", "embedding_metadata_array"):
            content.update(table.encode())
            for row in db.execute("SELECT id,key,string_value,int_value,float_value,bool_value FROM " + table + " ORDER BY id,key,string_value,int_value,float_value,bool_value"):
                typed = [[type(v).__name__, v.hex() if isinstance(v, (float, bytes)) else v] for v in row]
                content.update(encoded(typed) + b"\n")
        # Legacy MD5 is solely Chroma's existing migration-validation format, not
        # a security digest or a new migration. All new artifact hashes use SHA-256.
        return {"catalog": catalog, "migrations_sha256": signature(migrations), "sql_payload_sha256": content.hexdigest(),
                "hash_algorithm": "sha256" if lengths == {64} else "md5"}
    finally:
        db.close()


def checked_records(batch, requested, dimension):
    ids = batch.get("ids")
    require(isinstance(ids, list) and all(isinstance(i, str) for i in ids) and
            len(ids) == len(set(ids)) and set(ids) == set(requested), "BATCH_ID_MISMATCH")
    require(all(isinstance(batch.get(key), list) for key in ("documents", "metadatas", "uris")), "BATCH_CONTAINER_INVALID")
    require(all(batch.get(key) is not None and len(batch[key]) == len(ids) for key in FIELDS), "BATCH_FIELDS_MISMATCH")
    for position, rid in enumerate(ids):
        document, meta = batch["documents"][position], batch["metadatas"][position]
        uri, raw = batch["uris"][position], batch["embeddings"][position]
        require(document is None or isinstance(document, str), "INVALID_DOCUMENT")
        require(uri is None or isinstance(uri, str), "INVALID_URI")
        require(meta is None or isinstance(meta, dict) and all(isinstance(k, str) for k in meta), "INVALID_METADATA")
        require(raw is not None and len(raw) == dimension and dimension > 0, "VECTOR_SHAPE_INVALID")
        require(all(isinstance(v, Real) and not isinstance(v, bool) for v in raw), "VECTOR_TYPE_INVALID")
        vector = [float(v) for v in raw]
        require(all(math.isfinite(v) for v in vector), "VECTOR_NONFINITE")
        record = {"id": rid, "document": document, "metadata": meta, "embedding": vector, "uri": uri}
        encoded(record)  # No default=str, NaN replacement, or unsupported-value coercion.
        yield record


def export_collection(collection, spec, target, ledger):
    require(str(collection.id) == spec["id"] and collection.count() == len(spec["ids"]), "COLLECTION_MISMATCH")
    entries = {}
    with target.open("xb") as stream:
        for offset in range(0, len(spec["ids"]), 256):
            requested = spec["ids"][offset:offset + 256]
            batch = collection.get(ids=requested, include=list(FIELDS))
            for record in checked_records(batch, requested, spec["dimension"]):
                rid = record["id"]
                require(rid not in entries, "DUPLICATE_EXPORT_ID")
                stream.write(encoded(record) + b"\n")
                entries[rid] = tuple(signature(record[key]) for key in ("document", "metadata", "embedding", "uri"))
        stream.flush()
        os.fsync(stream.fileno())
    require(set(entries) == set(spec["ids"]) and collection.count() == len(entries), "EXPORT_COUNT_OR_IDS_CHANGED")
    # Read the saved JSONL back: verify exported values against the fetch-time fingerprints.
    remaining = set(entries)
    with target.open("rb") as stream:
        for line in stream:
            record = json.loads(line)
            rid = record["id"]
            require(rid in remaining and entries[rid] == tuple(signature(record[key]) for key in ("document", "metadata", "embedding", "uri")), "EXPORT_READBACK_MISMATCH")
            remaining.remove(rid)
    require(not remaining, "EXPORT_READBACK_INCOMPLETE")
    ledger.update(entries)
    return {"records": len(entries), "sha256": file_hash(target), "vector_dimensions_and_finiteness": "PASS" if entries else "EMPTY"}


def compare(a, b):
    rows = []
    for name in sorted(a.keys() | b.keys()):
        left, right = a.get(name, {}), b.get(name, {})
        common = left.keys() & right.keys()
        row = {"collection": name, "app_collection_exists": name in a, "backend_collection_exists": name in b,
               "app_records": len(left), "backend_records": len(right), "common_ids": len(common),
               "app_only_ids": len(left.keys() - right.keys()), "backend_only_ids": len(right.keys() - left.keys()),
               "identical_api_values": 0, "different_documents": 0, "different_metadata": 0, "different_vectors": 0,
               "different_uris": 0, "same_document_different_vector": 0, "different_document_same_vector": 0}
        for rid in common:
            x, y = left[rid], right[rid]
            row["identical_api_values"] += int(x == y)
            for pos, field in enumerate(("documents", "metadata", "vectors", "uris")):
                row["different_" + field] += int(x[pos] != y[pos])
            row["same_document_different_vector"] += int(x[0] == y[0] and x[2] != y[2])
            row["different_document_same_vector"] += int(x[0] != y[0] and x[2] == y[2])
        rows.append(row)
    return rows


def write_json(path, value):
    with path.open("xb") as stream:
        stream.write(encoded(value) + b"\n")
        stream.flush()
        os.fsync(stream.fileno())


def publish_complete(output, value):
    pending = output / "COMPLETE.pending.json"
    write_json(pending, value)
    # Atomic, exclusive publication of already-written/fsynced contents. Keep the pending link.
    os.link(pending, output / "COMPLETE.json")


def main():
    os.umask(0o077)
    require(TRIAL.resolve(strict=True) == TRIAL, "TRIAL_REDIRECTED")
    for label in LABELS:
        directory = TRIAL / label / "chroma_db"
        require(directory.is_dir(), "COPY_MISSING")
        for path in (directory, *directory.rglob("*")):
            info = path.lstat()
            require(not path.is_symlink() and TRIAL in path.resolve(strict=True).parents and
                    (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1), "COPY_LINK_OR_SPECIAL_FILE")
        require((directory / "chroma.sqlite3").is_file(), "COPY_SQLITE_MISSING")
    require(not (TRIAL / "app-storage/chroma_db/chroma.sqlite3").samefile(TRIAL / "backend-storage/chroma_db/chroma.sqlite3"), "COPIES_SHARE_DB")
    prior_path = TRIAL / "runtime-probe-report.json"
    prior = json.loads(prior_path.read_bytes())
    require(prior.get("status") == "PASS_SMOKE_ONLY" and all(prior["stores"][label]["status"] == "PASS_SMOKE_ONLY" for label in LABELS), "SMOKE_REPORT_NOT_PASS")
    require(shutil.disk_usage("/root").free >= 4 * 1024**3, "NEED_4_GIB_FREE_ON_ROOT")
    output = Path(tempfile.mkdtemp(prefix="aem-chroma-export-", dir="/root"))
    console = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    print("EXPORT_DIR=" + str(output), file=console, flush=True)
    with (output / "private.log").open("x", encoding="utf-8") as log:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        report = {"scope": "COPIES_ONLY_FULL_API_EXPORT_AND_COMPARISON", "status": "INCOMPLETE", "source_trial": str(TRIAL),
                  "original_stores_opened": False, "merge_performed": False, "cutover_performed": False,
                  "embedding_model_parity_proven": False, "full_hnsw_query_validation": False,
                  "api_payload_vs_sqlite_values_reconciled": False, "stores": {}}
        artifacts, catalogs = {}, {}
        try:
            require(metadata.version("chromadb") == "1.5.9", "PACKAGE_VERSION_CHANGED")
            os.chdir(output)
            os.environ.clear()
            os.environ.update(PATH="/usr/bin:/bin", ANONYMIZED_TELEMETRY="False", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
            import chromadb
            from chromadb.config import Settings
            require(chromadb.__version__ == "1.5.9", "IMPORTED_VERSION_CHANGED")
            for label in LABELS:
                path = TRIAL / label / "chroma_db/chroma.sqlite3"
                before = snapshot(path)
                old = {c["name"]: c["runtime_count"] for c in prior["stores"][label]["collections"]}
                require(old == {name: len(s["ids"]) for name, s in before["catalog"].items()}, "COUNTS_CHANGED_SINCE_SMOKE")
                settings = Settings(_env_file=None, chroma_api_impl="chromadb.api.rust.RustBindingsAPI", migrations="validate",
                                    migrations_hash_algorithm=before["hash_algorithm"], anonymized_telemetry=False, allow_reset=False)
                client = chromadb.PersistentClient(path=str(path.parent), settings=settings, tenant="default_tenant", database="default_database")
                catalogs[label], summaries, configs = {}, {}, {}
                try:
                    names = [c.name for c in client.list_collections()]
                    require(sorted(names) == sorted(before["catalog"]), "RUNTIME_COLLECTIONS_CHANGED")
                    for name, spec in before["catalog"].items():
                        print("EXPORTING=" + label + "/" + name, file=console, flush=True)
                        collection = client.get_collection(name=name, embedding_function=None)
                        configs[name] = {"collection_id": spec["id"], "dimension": spec["dimension"], "metadata": collection.metadata,
                                         "configuration_json": collection.configuration_json, "sqlite_config_json_str": spec["config_json_str"], "sqlite_schema_str": spec["schema_str"]}
                        catalogs[label][name] = {}
                        filename = label + "--" + name + ".jsonl"
                        summaries[name] = export_collection(collection, spec, output / filename, catalogs[label][name])
                        artifacts[filename] = summaries[name]["sha256"]
                finally:
                    client.close()
                require(before == snapshot(path), "SQLITE_STATE_CHANGED_DURING_EXPORT")
                filename = label + "--collection-configs.json"
                write_json(output / filename, configs)
                artifacts[filename] = file_hash(output / filename)
                report["stores"][label] = {"collections": summaries, "sqlite_before_after_match": True,
                                            "source_snapshot_sha256": signature(before), "total_records": sum(s["records"] for s in summaries.values())}
            report["comparison"] = compare(catalogs[LABELS[0]], catalogs[LABELS[1]])
            require(all(file_hash(output / name) == value for name, value in artifacts.items()), "ARTIFACT_CHECKSUM_CHANGED")
            report["status"] = "PASS_EXPORT_ONLY"
            report["artifacts"] = artifacts
            write_json(output / "export-report.json", report)
            publish_complete(output, {"status": "PASS_EXPORT_ONLY", "report_sha256": file_hash(output / "export-report.json"),
                                      "artifacts": artifacts, "smoke_report_sha256": file_hash(prior_path)})
        except Exception as error:
            traceback.print_exc()
            report["status"], report["error_type"] = "INCOMPLETE", type(error).__name__
            write_json(output / "failure-report.json", report)
        summary = {k: v for k, v in report.items() if k != "artifacts"}
        print(json.dumps(summary, indent=2), file=console, flush=True)
        print("EXPORT_DIR=" + str(output), file=console, flush=True)
        return 0 if report["status"] == "PASS_EXPORT_ONLY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
