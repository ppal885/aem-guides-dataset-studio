"""Synthetic-only tests; no access to VM databases or maintenance exports.

Run: python -I -B scripts/uac_eval/test_inspect_export_vectors.py
All fixtures are temporary; the helper itself must leave their bytes unchanged.
"""

from pathlib import Path
import importlib.util
import json
import tempfile
import unittest

_spec = importlib.util.spec_from_file_location('inspect_export_vectors', Path(__file__).with_name('inspect_export_vectors.py'))
subject = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(subject)


def put(path, value):
    path.write_text(json.dumps(value, sort_keys=True), encoding='utf-8')


def fixture(root, app_rows=None, backend_rows=None):
    a = [dict(id='sample-id', document='private original text', embedding=[1.0, -0.0], metadata={})]
    b = [dict(id='sample-id', document='private original text', embedding=[1.0, 0.0], metadata={}),
         dict(id='other-id', document='private other text', embedding=[0.0, 1.0], metadata={})]
    a = a if app_rows is None else app_rows
    b = b if backend_rows is None else backend_rows
    artifacts, stores = {}, {}
    for label, rows in zip(subject.LABELS, (a, b)):
        filename = label + '--fixture.jsonl'
        (root / filename).write_text(''.join(json.dumps(r) + '\n' for r in rows), encoding='utf-8')
        artifacts[filename] = subject.digest(root / filename)
        filename = label + '--collection-configs.json'
        put(root / filename, {'fixture': {'metadata': {'password': 'not-for-output'},
                                        'configuration_json': {'space': 'cosine', 'model_name': 'all-MiniLM-L6-v2'}}})
        artifacts[filename] = subject.digest(root / filename)
        stores[label] = {'collections': {'fixture': {'records': len(rows)}}}
    report = {'status': 'PASS_EXPORT_ONLY', 'artifacts': artifacts, 'stores': stores,
              'comparison': [{'collection': 'fixture', 'app_collection_exists': True,
                              'backend_collection_exists': True, 'app_records': len(a), 'backend_records': len(b),
                              'common_ids': 1, 'same_document_different_vector': 1}]}
    put(root / 'export-report.json', report)
    put(root / 'COMPLETE.json', {'status': 'PASS_EXPORT_ONLY', 'artifacts': artifacts,
                               'report_sha256': subject.digest(root / 'export-report.json')})


class Tests(unittest.TestCase):
    def test_signed_zero_is_numerically_equal(self):
        self.assertNotEqual(subject.signature([-0.0, 1.0]), subject.signature([0.0, 1.0]))
        result = subject.vector_difference([-0.0, 1.0], [0.0, 1.0])
        self.assertEqual(result['numeric_unequal_components'], 0)
        self.assertEqual(result['l2_difference'], 0)
        self.assertEqual(result['cosine_similarity'], 1)

    def test_nonzero_numeric_difference(self):
        result = subject.vector_difference([1.0, 0.0], [1.0, 0.1])
        self.assertEqual(result['numeric_unequal_components'], 1)
        self.assertEqual(result['max_absolute_difference'], 0.1)
        self.assertAlmostEqual(result['l2_difference'], 0.1)

    def test_perpendicular(self):
        self.assertEqual(subject.vector_difference([1, 0], [0, 1])['cosine_similarity'], 0)

    def test_zero_norm(self):
        self.assertIsNone(subject.vector_difference([0, 0], [1, 0])['cosine_similarity'])

    def test_dimension_mismatch(self):
        with self.assertRaises(ValueError):
            subject.vector_difference([1, 2], [1])

    def test_allowlisted_hints_no_secret_leak(self):
        value = {'password': 'private-value', 'config': {'model_name': 'private-model', 'space': 'cosine',
                                                        'normalize_embeddings': True},
                 'sqlite_schema_str': json.dumps({'model': 'BAAI/bge-small-en-v1.5'})}
        hints = subject.configuration_hints(value)
        self.assertNotIn('private', json.dumps(hints))
        self.assertTrue(hints['unrecognized_model_hint_present'])
        self.assertEqual(hints['recognized_declared_models'], ['BAAI/bge-small-en-v1.5'])
        self.assertEqual(hints['declared_normalize_embeddings'], [True])
        self.assertFalse(hints['model_provenance_proven'])

    def test_full_fixture_read_only_and_redacted(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            fixture(root)
            before = {p.name: subject.digest(p) for p in root.iterdir()}
            result = subject.inspect(root)
            self.assertEqual(result['status'], 'PASS_EXPORT_INSPECTION_ONLY')
            self.assertEqual(len(result['same_document_vector_pairs']), 1)
            self.assertEqual(result['same_document_vector_pairs'][0]['numeric_unequal_components'], 0)
            self.assertFalse(result['files_written'])
            self.assertFalse(result['databases_opened'])
            self.assertNotIn('private', json.dumps(result))
            self.assertNotIn('sample-id', json.dumps(result))
            self.assertNotIn('not-for-output', json.dumps(result))
            self.assertEqual(before, {p.name: subject.digest(p) for p in root.iterdir()})

    def test_tampered_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            fixture(root)
            (root / 'app-storage--fixture.jsonl').write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'ARTIFACT_HASH_MISMATCH'):
                subject.inspect(root)

    def test_backend_smaller_preserves_app_backend_direction(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            a = [dict(id='shared', document='same private text', embedding=[2.0, 0.0]),
                 dict(id='app-only', document='different text', embedding=[1.0, 0.0])]
            b = [dict(id='shared', document='same private text', embedding=[0.0, 3.0])]
            fixture(root, app_rows=a, backend_rows=b)
            result = subject.inspect(root)
            self.assertEqual(len(result['same_document_vector_pairs']), 1)
            pair = result['same_document_vector_pairs'][0]
            self.assertEqual(pair['app_vector_sha256'], subject.signature([2.0, 0.0]))
            self.assertEqual(pair['backend_vector_sha256'], subject.signature([0.0, 3.0]))
            self.assertEqual(pair['app_norm'], 2.0)
            self.assertEqual(pair['backend_norm'], 3.0)
            self.assertEqual(pair['cosine_similarity'], 0.0)
            self.assertAlmostEqual(pair['l2_difference'], 13 ** 0.5)

    def test_tampered_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            fixture(root)
            (root / 'export-report.json').write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError, 'REPORT_NOT_VERIFIED'):
                subject.inspect(root)

    def test_no_marker(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(ValueError, 'BAD_FILE_PATH'):
                subject.inspect(Path(td).resolve())

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ('../private', '/etc/passwd', 'sub/file', '..', '.'):
                with self.assertRaises(ValueError):
                    subject.safe_file(Path(td).resolve(), name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
