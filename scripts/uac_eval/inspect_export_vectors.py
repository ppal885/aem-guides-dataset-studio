"""Read-only follow-up for the approved disposable-copy export.

Deliberately pinned to the completed maintenance export in EXPORT. Run with
Python -I -B and an external timeout. Reads JSON artifacts only; does not import
Chroma, open SQLite, load a model, call a network service, or write output files.
The completion marker/report/artifact hashes are checked before and after analysis.
Raw documents, IDs, and arbitrary configuration values are not printed.
Configuration hints and numerical differences are not proof of model provenance
and never authorize a merge, re-embedding, or production cutover.
"""

from pathlib import Path
import hashlib
import json
import math
import re

EXPORT = Path('/root/aem-chroma-export-gq96kj5g')
LABELS = ('app-storage', 'backend-storage')


def require(ok, code):
    if not ok:
        raise ValueError(code)


def signature(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def safe_file(root, name):
    require(isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_.-]+', name), 'BAD_FILENAME')
    path = root / name
    require(not path.is_symlink() and path.is_file() and path.resolve().parent == root, 'BAD_FILE_PATH')
    return path


def records(path):
    seen = set()
    with path.open('rb') as stream:
        for line in stream:
            r = json.loads(line)
            rid = r['id']
            require(isinstance(rid, str) and rid and rid not in seen, 'DUPLICATE_OR_BAD_ID')
            seen.add(rid)
            require(r['document'] is None or isinstance(r['document'], str), 'BAD_DOCUMENT')
            v = r['embedding']
            require(isinstance(v, list) and v and all(type(x) in (int, float) and math.isfinite(x) for x in v), 'BAD_VECTOR')
            yield rid, signature(r['document']), signature(v), v


def vector_difference(a, b):
    require(len(a) == len(b) and len(a) > 0, 'VECTOR_DIMENSION_MISMATCH')
    na, nb = math.hypot(*a), math.hypot(*b)
    cosine = math.fsum((x / na) * (y / nb) for x, y in zip(a, b)) if na and nb else None
    return {'numeric_unequal_components': sum(x != y for x, y in zip(a, b)),
            'max_absolute_difference': max(abs(x - y) for x, y in zip(a, b)),
            'l2_difference': math.dist(a, b), 'app_norm': na, 'backend_norm': nb,
            'cosine_similarity': cosine}


def configuration_hints(value):
    # Exact allowlists only: never print arbitrary stored values or secrets.
    models, spaces, normalizations = set(), set(), set()
    model_fields = {'model', 'model_name', 'model_id', 'embedding_model', 'embedding_model_name'}
    allowed_models = {'all-MiniLM-L6-v2', 'sentence-transformers/all-MiniLM-L6-v2',
                      'bge-small-en-v1.5', 'BAAI/bge-small-en-v1.5'}
    unrecognized = False
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if key in model_fields:
                    if isinstance(child, str) and child in allowed_models:
                        models.add(child)
                    elif child is not None:
                        unrecognized = True
                if key in ('space', 'hnsw:space') and isinstance(child, str) and child in ('cosine', 'l2', 'ip'):
                    spaces.add(child)
                if key == 'normalize_embeddings' and type(child) is bool:
                    normalizations.add(child)
                if key in ('sqlite_config_json_str', 'sqlite_schema_str') and isinstance(child, str):
                    try:
                        pending.append(json.loads(child))
                    except ValueError:
                        pass
                if isinstance(child, (dict, list)):
                    pending.append(child)
        elif isinstance(item, list):
            pending.extend(item)
    return {'recognized_declared_models': sorted(models), 'unrecognized_model_hint_present': unrecognized,
            'declared_distance_spaces': sorted(spaces), 'declared_normalize_embeddings': sorted(normalizations),
            'model_provenance_proven': False}


def inspect(root):
    require(root.resolve(strict=True) == root, 'EXPORT_ROOT_REDIRECTED')
    marker_path = safe_file(root, 'COMPLETE.json')
    marker_hash = digest(marker_path)
    marker = json.loads(marker_path.read_bytes())
    report_path = safe_file(root, 'export-report.json')
    require(marker['status'] == 'PASS_EXPORT_ONLY' and digest(report_path) == marker['report_sha256'], 'REPORT_NOT_VERIFIED')
    report = json.loads(report_path.read_bytes())
    artifacts = marker['artifacts']
    require(report['status'] == 'PASS_EXPORT_ONLY' and artifacts == report['artifacts'], 'MANIFEST_MISMATCH')

    def verify():
        require(digest(marker_path) == marker_hash and digest(report_path) == marker['report_sha256'], 'MANIFEST_CHANGED')
        for name, expected in artifacts.items():
            require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected), 'BAD_DIGEST')
            require(digest(safe_file(root, name)) == expected, 'ARTIFACT_HASH_MISMATCH')

    verify()
    hints, pairs = {}, []
    for label in LABELS:
        name = label + '--collection-configs.json'
        require(name in artifacts, 'CONFIG_NOT_IN_MANIFEST')
        configs = json.loads(safe_file(root, name).read_bytes())
        require(set(configs) == set(report['stores'][label]['collections']), 'CONFIG_COLLECTION_MISMATCH')
        hints[label] = {name: configuration_hints(cfg) for name, cfg in configs.items()}
    for row in report['comparison']:
        if not (row['app_collection_exists'] and row['backend_collection_exists']):
            continue
        name = row['collection']
        require(re.fullmatch(r'[A-Za-z0-9_-]+', name), 'BAD_COLLECTION_NAME')
        small, large = LABELS if row['app_records'] <= row['backend_records'] else LABELS[::-1]
        filenames = {label: label + '--' + name + '.jsonl' for label in LABELS}
        require(all(f in artifacts for f in filenames.values()), 'RECORDS_NOT_IN_MANIFEST')
        left = {rid: (doc, vec, values) for rid, doc, vec, values in records(safe_file(root, filenames[small]))}
        common = count = found = 0
        for rid, doc, vec, values in records(safe_file(root, filenames[large])):
            count += 1
            if rid not in left:
                continue
            common += 1
            old_doc, old_vec, old_values = left[rid]
            if old_doc == doc and old_vec != vec:
                found += 1
                require(len(pairs) < 100, 'TOO_MANY_PAIRS_FOR_SMALL_REPORT')
                a, b = (old_values, values) if small == LABELS[0] else (values, old_values)
                pairs.append({'collection': name, 'record_id_sha256': signature(rid),
                              'document_sha256': doc, 'app_vector_sha256': signature(a),
                              'backend_vector_sha256': signature(b), **vector_difference(a, b)})
        require(len(left) == report['stores'][small]['collections'][name]['records'] and
                count == report['stores'][large]['collections'][name]['records'] and
                common == row['common_ids'] and found == row['same_document_different_vector'], 'COUNT_MISMATCH')
    verify()
    return {'status': 'PASS_EXPORT_INSPECTION_ONLY', 'export_dir': str(root),
            'artifact_hashes_verified_before_and_after': True,
            'databases_opened': False, 'files_written': False, 'model_loaded': False,
            'embedding_model_parity_proven': False, 'merge_authorized': False,
            'configuration_hints_not_runtime_proof': hints, 'same_document_vector_pairs': pairs}


if __name__ == '__main__':
    try:
        result = inspect(EXPORT)
        print(json.dumps(result, indent=2, allow_nan=False))
    except Exception as error:
        print(json.dumps({'status': 'STOP', 'error_type': type(error).__name__}))
        raise SystemExit(1)
