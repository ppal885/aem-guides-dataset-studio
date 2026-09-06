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


def main():
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

    def identity(service):
        info = r.systemd_info(service)
        invocation = r.command(['systemctl', 'show', service, '-p', 'InvocationID', '--value']).stdout.decode().strip()
        require(info['ActiveState'] == 'active' and info['SubState'] == 'running', 'SERVICE_NOT_RUNNING')
        require(int(info['MainPID']) > 0 and re.fullmatch('[0-9a-f]{32}', invocation), 'INVALID_SERVICE_IDENTITY')
        return {'pid': info['MainPID'], 'invocation': invocation}

    def save(state):
        r.atomic_write(work / 'state.json', r.encoded({'state': state, 'target': str(TARGET)}))

    def dependencies(service):
        fields = ('Requires', 'BindsTo', 'PartOf', 'PropagatesStopTo', 'ConsistsOf', 'RefuseManualStop')
        data = r.command(['systemctl', 'show', service, '--no-pager',
                          *['--property=' + k for k in fields]]).stdout.decode()
        return dict(line.split('=', 1) for line in data.splitlines() if '=' in line)

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
            r.verify_effective_units(ROUTING_RUN, journal['preflight'])
            before = {s: r.systemd_info(s) for s in r.SERVICES}
            ids = {s: identity(s) for s in r.SERVICES}
            require(ids == receipt['services'], 'SERVICE_CHANGED_SINCE_PREFLIGHT')
            require(all(unit_shape(before[s], r.exec_start) == unit_shape(base['services'][s], r.exec_start)
                        for s in r.SERVICES), 'UNIT_CHANGED_SINCE_PREFLIGHT')
            deps = {s: {k: v for k, v in base['extra'][s].items() if k != 'InvocationID'} for s in r.SERVICES}
            require(all(dependencies(s) == deps[s] for s in r.SERVICES), 'STOP_DEPENDENCIES_CHANGED')
            watched = dict(base['inspected_file_hashes'])
            watched.update({row['target']: row['after'] for row in rows})
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
            settings = base['proposed_environment']
            require(settings == {
                'USE_AZURE_EMBEDDING': 'false', 'DITA_EMBEDDING_MODEL_PATH': str(MODEL),
                'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'HF_HUB_DISABLE_TELEMETRY': '1',
                'CUDA_VISIBLE_DEVICES': '', 'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2',
                'SSL_CERT_FILE': '/etc/ssl/certs/ca-certificates.crt',
                'REQUESTS_CA_BUNDLE': '/etc/ssl/certs/ca-certificates.crt'}, 'UNREVIEWED_CANDIDATE_SETTINGS')
            # env applies these after systemd EnvironmentFiles, before the unchanged
            # application dotenv loaders checked by the saved preflight.
            settings = {**settings, **r.ROUTING, **{k: 'false' for k in r.WRITERS}}
            argv = ['/usr/bin/env', *[k + '=' + v for k, v in settings.items()],
                    str(CANDIDATE / 'venv/bin/python'), '-I', '-B', '-m', 'uvicorn',
                    '--app-dir', str(REPO / 'backend'), 'app.main:app',
                    '--host', '0.0.0.0', '--port', '8001', '--workers', '1']
            payload = ('[Service]\nExecStart=\nExecStart=' + ' '.join(argv) + '\n').encode()
            work = Path(tempfile.mkdtemp(prefix='cutover-', dir=CANDIDATE))
            r.atomic_write(work / 'override.conf', payload, absent=True)
            r.atomic_write(work / 'private-before.json', r.encoded({'units': before, 'identities': ids, 'files': watched}), absent=True)
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
                require(result['status'] == 'PASS_QUERY_SMOKE_ONLY', 'LIVE_SEARCH_SMOKE_FAILED')
                embedding = {str(port): embedding_status(port) for port in (8001, 4502)}
                require(all(item['status'] != 'FAILED' for item in embedding.values()), 'LIVE_ENCODING_FAILED')
                require(identity(BACKEND) == new, 'BACKEND_CHANGED_DURING_VERIFY')
                verify_units()
                for port in (8000, 4502):
                    c.inspect_inventory(port, expected)
                require(model_helper.model_hash(MODEL) == MODEL_HASH, 'MODEL_CHANGED_DURING_VERIFY')
                status = ('PASS_BACKEND_LOCAL_EMBEDDING_AND_JIRA_SEARCH'
                          if all(item['status'] == 'PASS' for item in embedding.values())
                          else 'PASS_BACKEND_SWITCH_AND_SEARCH_SMOKE_ONLY')
                save(status)
                return {'status': status, 'live_embedding': embedding,
                        'backend': new, 'chroma': ids[CHROMA], 'chroma_restarted': False,
                        'writer_pauses_preserved': True, 'routing_counts_and_ids': 'MATCH',
                        'jira_history_backend_and_gateway': 'PASS', 'full_rag_repair_proven': False,
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
