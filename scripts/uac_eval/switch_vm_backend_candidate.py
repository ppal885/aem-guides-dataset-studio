#!/usr/bin/env python3
"""One maintenance cutover, backend only. No Chroma restart or corpus writes.

Fixed paths bind this command to the operator-reviewed candidate and preflight.
All journal/config records are private; public failures expose reason codes only.
"""
import importlib.util
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import signal
import stat
import sys
import tempfile
import time

REPO = Path('/root/aem-guides-dataset-studio')
CANDIDATE = Path('/opt/aem-backend-candidate-sPxFr6YU')
PREFLIGHT = CANDIDATE / 'cutover-preflight-INuC0rzo'
ROUTING_RUN = Path('/app/storage/aem-chroma-routing-6pe9ghfg')
TARGET = Path('/etc/systemd/system/aem-backend.service.d/95-uac-python311.conf')
BACKEND, CHROMA = 'aem-backend.service', 'chroma.service'
MODEL = REPO / 'backend/models/all-MiniLM-L6-v2'
MODEL_HASH = '056b49a923ab30123c99a4e06daf0bd4875f894fa75f53c3d68f84df1411e61a'
DEPENDENCY_LISTS = ('Requires', 'BindsTo', 'PartOf', 'PropagatesStopTo', 'ConsistsOf')


def dependency_shape(values):
    """Unit dependencies are sets, not an ordered startup command line."""
    expected = {*DEPENDENCY_LISTS, 'RefuseManualStop'}
    if (not isinstance(values, dict) or set(values) != expected
            or any(not isinstance(v, str) for v in values.values())
            or values['RefuseManualStop'] not in ('yes', 'no')):
        raise ValueError('INVALID_DEPENDENCY_PROPERTIES')
    return {k: frozenset(v.split()) if k in DEPENDENCY_LISTS else v
            for k, v in values.items()}


def candidate_spec(base, routing, writers):
    settings = base['proposed_environment']
    expected = {
        'USE_AZURE_EMBEDDING': 'false', 'DITA_EMBEDDING_MODEL_PATH': str(MODEL),
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
        'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
        'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt',
        'REQUESTS_CA_BUNDLE': '/etc/ssl/certs/ca-certificates.crt'}
    if settings != expected:
        raise ValueError('UNREVIEWED_CANDIDATE_SETTINGS')
    settings = {**settings, **routing, **{k: 'false' for k in writers}}
    argv = ['/usr/bin/env', *[k + '=' + v for k, v in settings.items()],
            str(CANDIDATE / 'venv/bin/python'), '-I', '-B', '-m', 'uvicorn',
            '--app-dir', str(REPO / 'backend'), 'app.main:app',
            '--host', '0.0.0.0', '--port', '8001', '--workers', '1']
    return settings, argv, ('[Service]\nExecStart=\nExecStart=' + ' '.join(argv) + '\n').encode()


def rolled_back_baseline(r, previous, base, receipt, before, ids, payload, process_check):
    """Explicit retry takes a NEW baseline; the original preflight is never edited.

    A successful rollback necessarily starts a new backend invocation. Only the
    operator-selected completed rollback plus unchanged unit/config/Chroma state
    permits rebinding that one identity. This does not prove uninterrupted uptime
    between rollback and retry; the current old-runtime process is checked again.
    """
    require = r.require
    previous = Path(previous)
    require(previous.parent == CANDIDATE and re.fullmatch(r'cutover-[a-z0-9_]{8}', previous.name),
            'RETRY_PATH_NOT_ALLOWLISTED')
    r.safe_path(previous)
    require(not TARGET.exists() and not TARGET.is_symlink(), 'RETRY_OVERRIDE_STILL_PRESENT')
    captured = {}

    def read(name):
        path = r.safe_path(previous / name)
        raw = r.bounded(path)
        captured[str(path)] = r.digest(raw)
        return json.loads(raw)

    state, report, snapshot = read('state.json'), read('report.json'), read('private-before.json')
    require(state == {'state': 'ROLLED_BACK_BACKEND_ONLY', 'target': str(TARGET)}
            and report.get('status') == 'STOP' and report.get('phase') == 'CUTOVER'
            and report.get('reason') == 'LIVE_SEARCH_SMOKE_FAILED'
            and report.get('last_completed_state') == 'ROLLED_BACK_BACKEND_ONLY'
            and report.get('cutover_dir') == str(previous), 'RETRY_ROLLBACK_NOT_PROVEN')
    require(snapshot['identities'] == receipt['services'], 'RETRY_BASELINE_IDENTITY_MISMATCH')
    require(ids[CHROMA] == receipt['services'][CHROMA]
            and ids[BACKEND]['invocation'] != receipt['services'][BACKEND]['invocation'],
            'RETRY_SERVICE_IDENTITY_MISMATCH')
    for service in r.SERVICES:
        wanted = unit_shape(base['services'][service], r.exec_start)
        require(unit_shape(snapshot['units'][service], r.exec_start) == wanted
                and unit_shape(before[service], r.exec_start) == wanted, 'RETRY_UNIT_DRIFT')
    require(all(snapshot['files'].get(name) == hashed and name in snapshot['files']
                for name, hashed in base['inspected_file_hashes'].items()), 'RETRY_BASELINE_FILE_MISMATCH')
    for name, hashed in snapshot['files'].items():
        path = r.safe_path(Path(name), exists=hashed is not None)
        require((r.file_hash(path) if path.exists() else None) == hashed, 'RETRY_CONFIG_DRIFT')
        captured[name] = hashed
    witness = r.safe_path(previous / 'override.conf')
    require(r.bounded(witness) == payload and witness.stat().st_nlink == 1, 'RETRY_PAYLOAD_DRIFT')
    captured[str(witness)] = r.digest(payload)
    process_check(ids[BACKEND])
    return {'retry_of': str(previous), 'services': ids, 'files': captured,
            'scope': 'NEW_CURRENT_IDENTITY_BASELINE_AFTER_VALIDATED_ROLLBACK'}


def checked_search_outcome(result):
    """Semantic qualification is not an infrastructure liveness requirement."""
    def check(condition):
        if not condition:
            raise ValueError('LIVE_SEARCH_SMOKE_FAILED')

    check(isinstance(result, dict))
    status = result.get('status')
    allowed = {'PASS_QUERY_SMOKE_ONLY', 'PASS_FILTERED_QUERY_SMOKE_ONLY'}
    check(isinstance(status, str) and status in allowed
          and result.get('routing_identity_and_counts_stable') is True)
    queries = result.get('queries')
    check(isinstance(queries, list) and len(queries) == 3
          and all(isinstance(q, dict) and isinstance(q.get('probe_id'), str) for q in queries))
    check({q['probe_id'] for q in queries} == {'table_editing', 'map_title', 'publishing'})
    filtered = False
    for query in queries:
        routes = query.get('routes')
        check(isinstance(routes, dict) and set(routes) == {'backend_8001', 'gateway_4502'})
        for route in routes.values():
            check(isinstance(route, dict) and route.get('searched_jira_qa_reported') is True)
            count, rejected = route.get('result_count'), route.get('rejected_candidate_count')
            rows, rejects = route.get('results'), route.get('rejected_candidates')
            check(type(count) is int and 0 <= count <= 3 and isinstance(rows, list) and len(rows) == count)
            check(type(rejected) is int and 0 <= rejected <= 9
                  and isinstance(rejects, list) and len(rejects) == rejected)
            references = []
            for row in [*rows, *rejects]:
                check(isinstance(row, dict) and isinstance(row.get('reference_sha256'), str)
                      and re.fullmatch(r'[0-9a-f]{64}', row['reference_sha256']))
                references.append(row['reference_sha256'])
            check(len(references) == len(set(references)))
            for row in rejects:
                match = row.get('historical_match')
                check(isinstance(match, dict) and match.get('qualified') is False
                      and match.get('strength') == 'unproven')
            if route.get('status') == 'CANDIDATES_REJECTED_BY_POLICY':
                check(count == 0 and rejected > 0 and route.get('qualified_history_match_returned') is False)
                filtered = True
            else:
                check(route.get('status') == 'RETURNED_RESULTS' and count > 0
                      and route.get('qualified_history_match_returned') is True)
    check(filtered == (status == 'PASS_FILTERED_QUERY_SMOKE_ONLY')
          and result.get('qualified_history_search_smoke_passed') is (not filtered))
    return 'CANDIDATES_RETRIEVED_SOME_FILTERED' if filtered else 'QUALIFIED_MATCHES_RETURNED'


def recover_not_restarted(r, base, receipt, payload, argv, identity, dependencies):
    """Recover only an owned, pre-restart failed installation. No stop/start."""
    require = r.require
    r.safe_path(TARGET)
    require(TARGET.is_file() and not TARGET.is_symlink(), 'RECOVERY_TARGET_INVALID')
    matches = []
    for folder in CANDIDATE.iterdir():
        if re.fullmatch(r'cutover-[a-z0-9_]{8}', folder.name) and not folder.is_symlink() and folder.is_dir():
            witness = folder / 'override.conf'
            if witness.is_file() and not witness.is_symlink() and TARGET.samefile(witness):
                matches.append(folder)
    require(len(matches) == 1, 'RECOVERY_OWNERSHIP_AMBIGUOUS')
    work = r.safe_path(matches[0])
    read = lambda name: json.loads(r.bounded(r.safe_path(work / name)))
    state, report, snapshot = read('state.json'), read('report.json'), read('private-before.json')
    require(state == {'state': 'OVERRIDE_INSTALLED', 'target': str(TARGET)}
            and report.get('status') == 'STOP' and report.get('phase') == 'CUTOVER'
            and report.get('reason') == 'STOP_DEPENDENCIES_CHANGED', 'RECOVERY_STATE_NOT_ELIGIBLE')
    require(snapshot['identities'] == receipt['services'], 'RECOVERY_BASELINE_IDENTITY_CHANGED')
    deps = {s: dependency_shape({k: v for k, v in base['extra'][s].items() if k != 'InvocationID'})
            for s in r.SERVICES}
    before = {s: unit_shape(base['services'][s], r.exec_start) for s in r.SERVICES}
    require(all(unit_shape(snapshot['units'][s], r.exec_start) == before[s] for s in r.SERVICES),
            'RECOVERY_BASELINE_UNIT_CHANGED')
    require(all(k in snapshot['files'] and snapshot['files'][k] == v
                for k, v in base['inspected_file_hashes'].items()),
            'RECOVERY_BASELINE_FILES_CHANGED')

    def validate(installed):
        require(all(identity(s) == receipt['services'][s] for s in r.SERVICES), 'RECOVERY_PROCESS_CHANGED')
        require(all(dependencies(s) == deps[s] for s in r.SERVICES), 'STOP_DEPENDENCIES_CHANGED')
        for name, hashed in snapshot['files'].items():
            path = r.safe_path(Path(name), exists=hashed is not None)
            require((r.file_hash(path) if path.exists() else None) == hashed, 'RECOVERY_CONFIG_CHANGED')
        for service in r.SERVICES:
            wanted = dict(before[service])
            if installed and service == BACKEND:
                wanted['ExecStart'] = ('/usr/bin/env', argv)
                wanted['DropInPaths'] = sorted([*wanted['DropInPaths'], str(TARGET)])
            require(unit_shape(r.systemd_info(service), r.exec_start) == wanted, 'RECOVERY_UNIT_CHANGED')
        if installed:
            info = TARGET.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 2
                    and stat.S_IMODE(info.st_mode) == 0o600 and not TARGET.is_symlink()
                    and TARGET.samefile(work / 'override.conf')
                    and r.bounded(TARGET) == payload, 'RECOVERY_OVERRIDE_CHANGED')

    validate(True)
    r.atomic_write(work / 'state.json', r.encoded({'state': 'RECOVERING_NOT_RESTARTED', 'target': str(TARGET)}))
    validate(True)
    TARGET.unlink()  # Only the exact owned hard link, never a directory or glob.
    descriptor = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    r.command(['systemctl', 'daemon-reload'])
    validate(False)
    r.atomic_write(work / 'state.json', r.encoded({'state': 'RECOVERED_WITHOUT_RESTART', 'target': str(TARGET)}))
    print('RECOVERED_OWN_OVERRIDE; BOTH_SERVICE_IDENTITIES_UNCHANGED', flush=True)
    return work


def load(name):
    if name not in {'repair_vm_chroma_routing', 'vm_chroma_routing_checks',
                    'verify_local_embedding_canaries', 'verify_vm_search_embeddings'}:
        raise ValueError('UNSUPPORTED_HELPER')
    spec = importlib.util.spec_from_file_location(name, REPO / 'scripts/uac_eval' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def unit_shape(info, parse_exec):
    return {k: (parse_exec(v) if k == 'ExecStart' else sorted(shlex.split(v)) if k == 'DropInPaths' else v)
            for k, v in info.items()
            if k not in {'MainPID', 'ActiveState', 'SubState'}}


def transition(install, reload_units, verify_units, restart, verify_live, rollback):
    # install may publish successfully and then fail fsync: rollback must inspect
    # ownership even when install itself raises. SIGKILL/power loss need the journal.
    try:
        install()
        reload_units()
        verify_units()
        restart()
        return verify_live()
    except BaseException:
        rollback()
        raise


def embedding_status(port):
    """Optional authenticated read contract; no credential substitution/bypass."""
    if port not in (8001, 4502):
        raise ValueError('INVALID_PORT')
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=15)
    try:
        connection.request('GET', '/api/v1/mcp/health', headers={'Accept': 'application/json'})
        response = connection.getresponse()
        if response.status != 200:
            return {'status': 'NOT_VERIFIED', 'http_status': response.status}
        raw = response.read(1024**2 + 1)
        if len(raw) > 1024**2 or response.getheader('Content-Encoding', 'identity') != 'identity':
            return {'status': 'NOT_VERIFIED'}
        value = json.loads(raw).get('rag', {}).get('embedding', {})
        if not isinstance(value, dict) or 'last_request_status' not in value:
            return {'status': 'NOT_VERIFIED'}
        passed = (value.get('provider') == 'LOCAL' and value.get('ready') is True
                  and value.get('available') is True and value.get('availability_verified') is True
                  and value.get('last_request_status') == 'SUCCESS'
                  and type(value.get('last_vector_dimension')) is int
                  and value['last_vector_dimension'] == 384 and not value.get('error'))
        return {'status': 'PASS' if passed else 'FAILED'}
    except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException):
        return {'status': 'NOT_VERIFIED'}
    finally:
        connection.close()


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    retry_path = None
    if len(arguments) == 2 and arguments[0] == '--retry-after-rollback':
        retry_path = arguments[1]
    elif arguments not in ([], ['--recover-not-restarted']):
        raise SystemExit('Usage: switch_vm_backend_candidate.py [--recover-not-restarted | --retry-after-rollback <cutover-dir>]')
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise SystemExit('STOP: ROOT_ON_REVIEWED_VM_REQUIRED')
    os.umask(0o077)
    r = load('repair_vm_chroma_routing')
    c = load('vm_chroma_routing_checks')
    model_helper = load('verify_local_embedding_canaries')
    search = load('verify_vm_search_embeddings')
    require = r.require
    work = None
    outcome = {'status': 'STOP_BEFORE_CHANGE'}
    phase = 'PREPARATION'
    dependency_order_changes = {}
    retry = None

    def identity(service):
        info = r.systemd_info(service)
        invocation = r.command(['systemctl', 'show', service, '-p', 'InvocationID', '--value']).stdout.decode().strip()
        require(info['ActiveState'] == 'active' and info['SubState'] == 'running', 'SERVICE_NOT_RUNNING')
        require(int(info['MainPID']) > 0 and re.fullmatch('[0-9a-f]{32}', invocation), 'INVALID_SERVICE_IDENTITY')
        return {'pid': info['MainPID'], 'invocation': invocation}

    def save(state):
        r.atomic_write(work / 'state.json', r.encoded({'state': state, 'target': str(TARGET)}))

    def dependency_properties(service):
        fields = ('Requires', 'BindsTo', 'PartOf', 'PropagatesStopTo', 'ConsistsOf', 'RefuseManualStop')
        data = r.command(['systemctl', 'show', service, '--no-pager',
                          *['--property=' + k for k in fields]]).stdout.decode()
        return dict(line.split('=', 1) for line in data.splitlines() if '=' in line)

    def dependencies(service):
        return dependency_shape(dependency_properties(service))

    try:
        with r.maintenance_lock():
            require(sys.version_info == (3, 11, 16, 'final', 0)
                    and Path(sys.prefix) == CANDIDATE / 'venv', 'WRONG_CANDIDATE')
            r.safe_path(PREFLIGHT)
            base = json.loads(r.bounded(PREFLIGHT / 'private-baseline.json'))
            receipt = json.loads(r.bounded(PREFLIGHT / 'report.json'))
            require(receipt['status'] == 'PASS_BACKEND_CUTOVER_PREFLIGHT_ONLY', 'PREFLIGHT_NOT_PASSED')
            require(model_helper.model_hash(MODEL) == MODEL_HASH == receipt['model_sha256'], 'MODEL_CHANGED')
            journal = json.loads(r.bounded(ROUTING_RUN / 'journal.json', 32 * 1024**2))
            require(journal['state'] == 'PASS_ROUTING_ONLY_WRITERS_PAUSED'
                    and journal['background_writers_paused'] is True, 'WRITERS_NOT_PAUSED')
            rows = r.validate_journal(ROUTING_RUN, journal)
            require(rows == base['routing_files'], 'ROUTING_JOURNAL_CHANGED')
            settings, argv, payload = candidate_spec(base, r.ROUTING, r.WRITERS)
            if arguments == ['--recover-not-restarted']:
                require(all(r.file_hash(Path(row['target'])) == row['after'] for row in rows), 'ROUTING_CONFIG_DRIFT')
                for service in r.SERVICES:
                    old = {k: v for k, v in base['extra'][service].items() if k != 'InvocationID'}
                    current = dependency_properties(service)
                    require(dependency_shape(old) == dependency_shape(current), 'STOP_DEPENDENCIES_CHANGED')
                    dependency_order_changes[service] = [k for k in DEPENDENCY_LISTS if old[k] != current[k]]
                recover_not_restarted(r, base, receipt, payload, argv, identity, dependencies)
            r.verify_effective_units(ROUTING_RUN, journal['preflight'])
            before = {s: r.systemd_info(s) for s in r.SERVICES}
            ids = {s: identity(s) for s in r.SERVICES}
            if retry_path:
                def old_process_checked(backend_id):
                    process = Path('/proc') / backend_id['pid']
                    binary = (process / 'exe').resolve()
                    command = r.bounded(process / 'cmdline').split(b'\0')
                    expected_command = r.tuple_backend_command(REPO)[1]
                    interpreters = [str(REPO / 'backend/venv/bin' / name).encode()
                                    for name in ('python', 'python3', 'python3.11')]
                    require(binary == Path('/usr/bin/python3.11').resolve()
                            and command[-1:] == [b''] and command[0] in interpreters
                            and command[1:-1] == [a.encode() for a in expected_command],
                            'RETRY_RUNNING_BACKEND_NOT_ORIGINAL')
                    require(identity(BACKEND) == backend_id, 'RETRY_PROCESS_CHANGED')
                retry = rolled_back_baseline(r, retry_path, base, receipt, before, ids, payload,
                                             old_process_checked)
            else:
                require(ids == receipt['services'], 'SERVICE_CHANGED_SINCE_PREFLIGHT')
            require(all(unit_shape(before[s], r.exec_start) == unit_shape(base['services'][s], r.exec_start)
                        for s in r.SERVICES), 'UNIT_CHANGED_SINCE_PREFLIGHT')
            deps = {s: dependency_shape({k: v for k, v in base['extra'][s].items() if k != 'InvocationID'}) for s in r.SERVICES}
            require(all(dependencies(s) == deps[s] for s in r.SERVICES), 'STOP_DEPENDENCIES_CHANGED')
            watched = dict(base['inspected_file_hashes'])
            watched.update({row['target']: row['after'] for row in rows})
            if retry:
                watched.update(retry['files'])
            for info in before.values():
                files = [info['FragmentPath'], *shlex.split(info['DropInPaths'])]
                envfiles = info.get('EnvironmentFiles', '')
                pattern = r'(/[A-Za-z0-9_./-]+) \(ignore_errors=(?:yes|no)\)'
                require(not re.sub(pattern, '', envfiles).strip(), 'UNSUPPORTED_ENVIRONMENT_FILES')
                files.extend(re.findall(pattern, envfiles))
                for name in files:
                    path = r.safe_path(Path(name))
                    hashed = r.file_hash(path)
                    require(name not in watched or watched[name] == hashed, 'CONFIG_CHANGED_SINCE_PREFLIGHT')
                    watched[name] = hashed

            def stable_files():
                for name, hashed in watched.items():
                    path = r.safe_path(Path(name), exists=hashed is not None)
                    require((r.file_hash(path) if path.exists() else None) == hashed, 'PRESERVED_FILE_CHANGED')

            def chroma_unchanged():
                require(identity(CHROMA) == ids[CHROMA], 'CHROMA_IDENTITY_CHANGED')
                require(unit_shape(r.systemd_info(CHROMA), r.exec_start) == unit_shape(before[CHROMA], r.exec_start), 'CHROMA_UNIT_CHANGED')
                require(all(dependencies(s) == deps[s] for s in r.SERVICES), 'STOP_DEPENDENCIES_CHANGED')

            stable_files()
            r.safe_path(TARGET, exists=False)
            require(not TARGET.exists(), 'CANDIDATE_OVERRIDE_ALREADY_EXISTS')
            # env applies these after systemd EnvironmentFiles, before the unchanged
            # application dotenv loaders checked by the saved preflight.
            work = Path(tempfile.mkdtemp(prefix='cutover-', dir=CANDIDATE))
            r.atomic_write(work / 'override.conf', payload, absent=True)
            r.atomic_write(work / 'private-before.json', r.encoded({'units': before, 'identities': ids, 'files': watched}), absent=True)
            if retry:
                r.atomic_write(work / 'retry-baseline.json', r.encoded(retry), absent=True)
            save('PREPARED_NOT_INSTALLED')
            print('CUTOVER_DIR=' + str(work), flush=True)
            expected = journal['expected_collections']
            for port in (8000, 4502):
                c.inspect_inventory(port, expected)

            def verify_units(candidate=True):
                stable_files()
                chroma_unchanged()
                current = unit_shape(r.systemd_info(BACKEND), r.exec_start)
                wanted = unit_shape(before[BACKEND], r.exec_start)
                if candidate:
                    wanted['ExecStart'] = ('/usr/bin/env', argv)
                    wanted['DropInPaths'] = sorted([*wanted['DropInPaths'], str(TARGET)])
                require(current == wanted, 'MERGED_BACKEND_UNIT_MISMATCH')

            def install():
                stable_files()
                chroma_unchanged()
                require(identity(BACKEND) == ids[BACKEND], 'BACKEND_CHANGED_BEFORE_SWITCH')
                # Retain a hard-link ownership witness. A racing pre-existing file,
                # even with identical bytes, can never be mistaken for our change.
                os.link(work / 'override.conf', TARGET)
                descriptor = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                save('OVERRIDE_INSTALLED')

            def reload_units():
                r.command(['systemctl', 'daemon-reload'])

            def restart():
                verify_units()
                save('BACKEND_RESTART_REQUESTED')
                print('Restarting backend only; Chroma and paused writers stay unchanged...', flush=True)
                r.command(['systemctl', 'restart', BACKEND], timeout=120)

            def verify_live():
                r.wait_running(BACKEND, seconds=90)
                new = identity(BACKEND)
                require(new['invocation'] != ids[BACKEND]['invocation'], 'BACKEND_NOT_RESTARTED')
                process = Path('/proc') / new['pid']
                require((process / 'exe').resolve() == Path('/opt/aem-python-3.11.16/bin/python3.11'), 'WRONG_RUNNING_PYTHON')
                cmdline = r.bounded(process / 'cmdline').split(b'\0')
                require(cmdline[:-1] == [a.encode() for a in argv[1 + len(settings):]], 'WRONG_RUNNING_COMMAND')
                deadline = time.monotonic() + 90
                while True:
                    try:
                        c.verify_backend(expected)
                        break
                    except c.RoutingCheckError:
                        require(time.monotonic() < deadline, 'BACKEND_READINESS_TIMEOUT')
                        time.sleep(2)
                verify_units()
                result = search.run_diagnostic()
                r.atomic_write(work / 'search-report.json', r.encoded(result), absent=True)
                embedding = {str(port): embedding_status(port) for port in (8001, 4502)}
                r.atomic_write(work / 'embedding-report.json', r.encoded(embedding), absent=True)
                # Save both independent diagnostics before deciding to roll back.
                try:
                    search_outcome = checked_search_outcome(result)
                except (ValueError, TypeError, AttributeError):
                    require(False, 'LIVE_SEARCH_SMOKE_FAILED')
                require(all(item['status'] != 'FAILED' for item in embedding.values()), 'LIVE_ENCODING_FAILED')
                require(identity(BACKEND) == new, 'BACKEND_CHANGED_DURING_VERIFY')
                verify_units()
                for port in (8000, 4502):
                    c.inspect_inventory(port, expected)
                require(model_helper.model_hash(MODEL) == MODEL_HASH, 'MODEL_CHANGED_DURING_VERIFY')
                status = ('PASS_BACKEND_LOCAL_EMBEDDING_AND_JIRA_SEARCH'
                          if all(item['status'] == 'PASS' for item in embedding.values())
                          else 'PASS_BACKEND_SWITCH_AND_SEARCH_SMOKE_ONLY')
                if result['status'] == 'PASS_FILTERED_QUERY_SMOKE_ONLY':
                    status = ('PASS_BACKEND_LOCAL_EMBEDDING_AND_FILTERED_RETRIEVAL'
                              if all(item['status'] == 'PASS' for item in embedding.values())
                              else 'PASS_BACKEND_SWITCH_AND_FILTERED_RETRIEVAL_ONLY')
                save(status)
                return {'status': status, 'live_embedding': embedding,
                        'backend': new, 'chroma': ids[CHROMA], 'chroma_restarted': False,
                        'writer_pauses_preserved': True, 'routing_counts_and_ids': 'MATCH',
                        'jira_history_backend_and_gateway': search_outcome,
                        'qualified_matches_for_every_probe': result['status'] == 'PASS_QUERY_SMOKE_ONLY',
                        'full_rag_repair_proven': False,
                        'resume_writers_authorized': False, 'index_write_requests': False}

            def rollback():
                for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                    signal.signal(sig, signal.SIG_IGN)
                if not TARGET.exists() or TARGET.is_symlink() or not TARGET.samefile(work / 'override.conf'):
                    return
                # Never use routing.rollback(): it would stop BOTH services.
                info = TARGET.lstat()
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 2 and info.st_uid == 0
                        and r.file_hash(TARGET) == r.digest(payload), 'ROLLBACK_OVERRIDE_DRIFT')
                stable_files()
                chroma_unchanged()
                save('BACKEND_ONLY_ROLLBACK_REQUESTED')
                r.command(['systemctl', 'stop', BACKEND], timeout=120)
                # Recheck immediately before removing only our newly created file.
                require(r.file_hash(TARGET) == r.digest(payload) and not TARGET.is_symlink()
                        and TARGET.samefile(work / 'override.conf'), 'ROLLBACK_OVERRIDE_DRIFT')
                TARGET.unlink()
                descriptor = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                reload_units()
                verify_units(candidate=False)
                r.command(['systemctl', 'start', BACKEND], timeout=120)
                r.wait_running(BACKEND)
                chroma_unchanged()
                save('ROLLED_BACK_BACKEND_ONLY')

            def interrupted(_number, _frame):
                raise KeyboardInterrupt()

            for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
                signal.signal(sig, interrupted)
            phase = 'CUTOVER'
            outcome = transition(install, reload_units, verify_units, restart, verify_live, rollback)
    except BaseException as error:
        reason = str(error) if isinstance(error, (r.RepairError, c.RoutingCheckError)) else type(error).__name__
        outcome = {'status': 'STOP', 'phase': phase, 'reason': reason,
                   'resume_writers_authorized': False, 'index_write_requests': False}
    if dependency_order_changes:
        outcome['dependency_order_only_changes'] = dependency_order_changes
    if retry:
        outcome['retry_of'] = retry['retry_of']
    if work:
        outcome['cutover_dir'] = str(work)
        try:
            outcome['last_completed_state'] = json.loads(r.bounded(work / 'state.json'))['state']
        except (OSError, ValueError, KeyError):
            outcome['last_completed_state'] = 'NOT_RECORDED'
        r.atomic_write(work / 'report.json', r.encoded(outcome))
    print(json.dumps(outcome, indent=2))
    return 0 if outcome['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
