"""Synthetic-only exporter tests; main() and the VM copies are never opened.

Run: backend/venv/bin/python -I -B scripts/uac_eval/test_export_runtime_copies.py
The integration test requires the existing Chroma dependency, with no downloads.
"""

from pathlib import Path
from unittest.mock import Mock, patch
import importlib.util
import json
import sqlite3
import tempfile
import unittest

# Use the exact adjacent repository module, including under isolated Python (-I).
_spec = importlib.util.spec_from_file_location(
    "export_runtime_copies", Path(__file__).resolve().with_name("export_runtime_copies.py")
)
export = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export)


def record_batch(ids):
    return {"ids": list(ids), "documents": ["example" for _ in ids],
            "metadatas": [{"flag": True, "number": 1, "values": ["b", "a", "a"]} for _ in ids],
            "uris": [None for _ in ids], "embeddings": [[1.0, -0.0] for _ in ids]}


class Tests(unittest.TestCase):
    def test_snapshot_reads_wal_and_detects_metadata_change(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "synthetic.sqlite3"
            db = sqlite3.connect(path)
            try:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA wal_autocheckpoint=0")
                db.executescript('''
                    CREATE TABLE databases (id TEXT, tenant_id TEXT, name TEXT);
                    CREATE TABLE migrations (dir TEXT, version INTEGER, filename TEXT, sql TEXT, hash TEXT);
                    CREATE TABLE collections (id TEXT, name TEXT, dimension INTEGER, config_json_str TEXT, schema_str TEXT, database_id TEXT);
                    CREATE TABLE segments (id TEXT, collection TEXT, scope TEXT);
                    CREATE TABLE embeddings (segment_id TEXT, embedding_id TEXT);
                    CREATE TABLE embedding_metadata (id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL, bool_value INTEGER);
                    CREATE TABLE embedding_metadata_array (id INTEGER, key TEXT, string_value TEXT, int_value INTEGER, float_value REAL, bool_value INTEGER);
                ''')
                db.execute("INSERT INTO databases VALUES ('db', 'default_tenant', 'default_database')")
                db.execute("INSERT INTO migrations VALUES ('meta', 1, 'example.sql', 'example', ?)", ('a' * 32,))
                db.execute("INSERT INTO collections VALUES ('c', 'fixture', 2, '{}', '{}', 'db')")
                db.execute("INSERT INTO segments VALUES ('s', 'c', 'METADATA')")
                db.execute("INSERT INTO embeddings VALUES ('s', 'r1')")
                db.execute("INSERT INTO embedding_metadata VALUES (1, 'chroma:document', 'old', NULL, NULL, NULL)")
                db.commit()
                before = export.snapshot(path)
                self.assertEqual(before['catalog']['fixture']['ids'], ['r1'])
                self.assertEqual(before['hash_algorithm'], 'md5')
                self.assertEqual(before, export.snapshot(path))
                db.execute("UPDATE embedding_metadata SET string_value='new'")
                db.commit()
                after = export.snapshot(path)
                self.assertNotEqual(before['sql_payload_sha256'], after['sql_payload_sha256'])
                self.assertEqual(before['migrations_sha256'], after['migrations_sha256'])
            finally:
                db.close()

    def test_exact_types_preserved(self):
        record = list(export.checked_records(record_batch(["r1"]), ["r1"], 2))[0]
        actual = json.loads(export.encoded(record))
        self.assertIs(actual["metadata"]["flag"], True)
        self.assertIs(type(actual["metadata"]["number"]), int)
        self.assertEqual(actual["metadata"]["values"], ["b", "a", "a"])
        self.assertIsNone(actual["uri"])
        self.assertIn(b"-0.0", export.encoded(actual))

    def test_null_and_empty_distinct(self):
        for value in (None, ""):
            batch = record_batch(["r"])
            batch["documents"] = [value]
            self.assertEqual(list(export.checked_records(batch, ["r"], 2))[0]["document"], value)
        self.assertNotEqual(export.signature(None), export.signature(""))
        self.assertNotEqual(export.signature(None), export.signature({}))
        self.assertNotEqual(export.signature(True), export.signature(1))
        self.assertNotEqual(export.signature(1), export.signature(1.0))

    def test_bad_batch_membership(self):
        for ids in (["r2"], ["r1", "r1"], [], [1]):
            with self.assertRaisesRegex(RuntimeError, "BATCH_ID_MISMATCH"):
                list(export.checked_records(record_batch(ids), ["r1"], 2))

    def test_no_zip_truncation(self):
        for key in export.FIELDS:
            for value in (None, []):
                batch = record_batch(["r"])
                batch[key] = value
                with self.assertRaisesRegex(RuntimeError, "BATCH_FIELDS_MISMATCH|BATCH_CONTAINER_INVALID"):
                    list(export.checked_records(batch, ["r"], 2))

    def test_string_container_not_treated_as_rows(self):
        for key in ("documents", "metadatas", "uris"):
            batch = record_batch(["r"])
            batch[key] = "x"
            with self.assertRaisesRegex(RuntimeError, "BATCH_CONTAINER_INVALID"):
                list(export.checked_records(batch, ["r"], 2))

    def test_vector_errors(self):
        for value in (None, [], [1], [float("nan"), 0], [float("inf"), 0], [True, 0], ["1.0", 0]):
            batch = record_batch(["r"])
            batch["embeddings"] = [value]
            with self.assertRaises(RuntimeError):
                list(export.checked_records(batch, ["r"], 2))

    def test_bad_metadata(self):
        for value in ([], {1: "bad"}, {"x": object()}, {"x": float("nan")}):
            batch = record_batch(["r"])
            batch["metadatas"] = [value]
            with self.assertRaises((RuntimeError, ValueError, TypeError)):
                list(export.checked_records(batch, ["r"], 2))

    def test_batch_order_independent(self):
        self.assertEqual(len(list(export.checked_records(record_batch(["b", "a"]), ["a", "b"], 2))), 2)

    def test_multibatch_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "records.jsonl"
            ids = [str(i) for i in range(513)]
            c = Mock(id="cid")
            c.count.return_value = len(ids)
            c.get.side_effect = lambda ids, include: record_batch(list(reversed(ids)))
            ledger = {}
            result = export.export_collection(c, {"id": "cid", "ids": ids, "dimension": 2}, target, ledger)
            self.assertEqual(result["records"], 513)
            self.assertEqual(c.get.call_count, 3)
            self.assertEqual(len(ledger), 513)
            self.assertEqual(len(target.read_text().splitlines()), 513)
            self.assertEqual(export.file_hash(target), result["sha256"])
            for call in c.get.call_args_list:
                self.assertLessEqual(len(call.kwargs["ids"]), 256)
                self.assertEqual(call.kwargs["include"], list(export.FIELDS))

    def test_count_change_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            c = Mock(id="cid")
            c.count.side_effect = [1, 2]
            c.get.return_value = record_batch(["r"])
            ledger = {}
            with self.assertRaisesRegex(RuntimeError, "EXPORT_COUNT_OR_IDS_CHANGED"):
                export.export_collection(c, {"id": "cid", "ids": ["r"], "dimension": 2}, Path(td) / "records.jsonl", ledger)
            self.assertEqual(ledger, {})
            self.assertFalse((Path(td) / "COMPLETE.json").exists())

    def test_empty_collection_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            c = Mock(id="cid")
            c.count.return_value = 0
            result = export.export_collection(c, {"id": "cid", "ids": [], "dimension": None}, Path(td) / "empty.jsonl", {})
            self.assertEqual(result["records"], 0)
            self.assertEqual(result["vector_dimensions_and_finiteness"], "EMPTY")
            c.get.assert_not_called()

    def test_existing_output_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "report.json"
            export.write_json(path, {"original": True})
            with self.assertRaises(FileExistsError):
                export.write_json(path, {"original": False})
            self.assertEqual(json.loads(path.read_text()), {"original": True})

    def test_complete_not_visible_during_failed_write(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            def partial_write(path, value):
                path.write_bytes(b'{"status":')
                raise OSError("SYNTHETIC_DISK_FULL")
            with patch.object(export, "write_json", side_effect=partial_write):
                with self.assertRaises(OSError):
                    export.publish_complete(root, {"status": "PASS_EXPORT_ONLY"})
            self.assertFalse((root / "COMPLETE.json").exists())

    def test_atomic_complete_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            export.publish_complete(root, {"status": "PASS_EXPORT_ONLY"})
            self.assertEqual(json.loads((root / "COMPLETE.json").read_text()), {"status": "PASS_EXPORT_ONLY"})
            with self.assertRaises(FileExistsError):
                export.publish_complete(root, {"status": "changed"})

    def test_synthetic_actual_chroma_export(self):
        import chromadb
        from chromadb.config import Settings
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            client = chromadb.PersistentClient(path=str(root / "synthetic-db"), settings=Settings(anonymized_telemetry=False, _env_file=None))
            try:
                c = client.create_collection("synthetic_export", embedding_function=None)
                c.add(ids=["r1", "r2"], embeddings=[[1.0, 0.0], [0.0, 1.0]], documents=["alpha", "beta"],
                      metadatas=[{"flag": True}, {"value": 1}])
                read = client.get_collection("synthetic_export", embedding_function=None)
                ledger = {}
                result = export.export_collection(read, {"id": str(read.id), "ids": ["r1", "r2"], "dimension": 2}, root / "out.jsonl", ledger)
                self.assertEqual(result["records"], 2)
                self.assertEqual(set(ledger), {"r1", "r2"})
                self.assertEqual([json.loads(line)["uri"] for line in (root / "out.jsonl").read_text().splitlines()], [None, None])
            finally:
                client.close()

    def test_comparison_keeps_collisions_and_exclusives(self):
        a = {"shared": {"same": ("d", "m", "v", "u"), "vec": ("d", "m", "v", "u"), "doc": ("d", "m", "v", "u"), "only_a": ("x",)*4}, "only_app_collection": {"a": ("x",)*4}}
        b = {"shared": {"same": ("d", "m", "v", "u"), "vec": ("d", "m", "new", "u"), "doc": ("new", "m", "v", "u"), "only_b": ("x",)*4}, "only_backend_collection": {"a": ("y",)*4}}
        rows = {r["collection"]: r for r in export.compare(a, b)}
        shared = rows["shared"]
        self.assertEqual(shared["common_ids"], 3)
        self.assertEqual(shared["identical_api_values"], 1)
        self.assertEqual(shared["same_document_different_vector"], 1)
        self.assertEqual(shared["different_document_same_vector"], 1)
        self.assertEqual(shared["app_only_ids"], 1)
        self.assertEqual(shared["backend_only_ids"], 1)
        self.assertEqual(rows["only_app_collection"]["app_only_ids"], 1)
        self.assertEqual(rows["only_backend_collection"]["backend_only_ids"], 1)
        self.assertFalse(rows["only_backend_collection"]["app_collection_exists"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
