"""Synthetic dependency/recovery checks; no VM, systemd, database, or network."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import switch_vm_backend_candidate as cutover


def dependency_fixture():
    return {**{key: 'alpha.service beta.service' for key in cutover.DEPENDENCY_LISTS},
            'RefuseManualStop': 'no'}


class DependencyShapeTests(unittest.TestCase):
    def test_each_list_accepts_order_and_whitespace_changes(self):
        original = dependency_fixture()
        for key in cutover.DEPENDENCY_LISTS:
            with self.subTest(key=key):
                reordered = {**original, key: ' beta.service\talpha.service  beta.service\n'}
                self.assertEqual(cutover.dependency_shape(original),
                                 cutover.dependency_shape(reordered))
        self.assertEqual(original, dependency_fixture())

    def test_each_list_rejects_added_or_removed_dependency_as_different(self):
        original = dependency_fixture()
        for key in cutover.DEPENDENCY_LISTS:
            for value in ('alpha.service', 'alpha.service beta.service new.service'):
                with self.subTest(key=key, value=value):
                    self.assertNotEqual(cutover.dependency_shape(original),
                                        cutover.dependency_shape({**original, key: value}))

    def test_empty_lists_are_valid_but_scalar_remains_exact(self):
        original = {**{key: '' for key in cutover.DEPENDENCY_LISTS}, 'RefuseManualStop': 'no'}
        self.assertEqual(cutover.dependency_shape(original)['Requires'], frozenset())
        self.assertNotEqual(cutover.dependency_shape(original),
                            cutover.dependency_shape({**original, 'RefuseManualStop': 'yes'}))

    def test_invalid_missing_extra_and_nonstring_properties_fail_closed(self):
        original = dependency_fixture()
        invalid = [None, [], {**original, 'Unexpected': ''}]
        invalid.extend({k: v for k, v in original.items() if k != missing}
                       for missing in original)
        invalid.extend({**original, key: None} for key in original)
        invalid.extend({**original, 'RefuseManualStop': value}
                       for value in (False, 0, '', 'NO', ' no ', 'unknown'))
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'INVALID_DEPENDENCY_PROPERTIES'):
                    cutover.dependency_shape(value)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='synthetic-cutover-')
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.candidate = root / 'candidate'
        self.candidate.mkdir()
        self.work = self.candidate / 'cutover-abcdefgh'
        self.work.mkdir()
        self.target = root / '95-uac-python311.conf'
        self.payload = b'[Service]\nExecStart=synthetic-candidate\n'
        self.witness = self.work / 'override.conf'
        self.witness.write_bytes(self.payload)
        self.witness.chmod(0o600)
        os.link(self.witness, self.target)
        self.config = root / 'preserved.conf'
        self.config.write_bytes(b'synthetic preserved configuration')
        self.argv = ['/usr/bin/env', 'synthetic-candidate']
        self.ids = {service: {'pid': str(index + 100), 'invocation': str(index) * 32}
                    for index, service in enumerate((cutover.BACKEND, cutover.CHROMA), 1)}
        self.units = {service: {
            'MainPID': self.ids[service]['pid'], 'ActiveState': 'active',
            'SubState': 'running', 'ExecStart': 'original-' + service,
            'DropInPaths': '', 'WorkingDirectory': '/synthetic/backend',
            'ReadOnlyPaths': '/synthetic/original-store', 'Environment': 'PAUSED=true',
        } for service in self.ids}
        self.base = {
            'services': copy.deepcopy(self.units),
            'extra': {service: {**dependency_fixture(), 'InvocationID': self.ids[service]['invocation']}
                      for service in self.ids},
            'inspected_file_hashes': {str(self.config): self.file_hash(self.config)},
        }
        self.receipt = {'services': copy.deepcopy(self.ids)}
        self.snapshot = {'units': copy.deepcopy(self.units), 'identities': copy.deepcopy(self.ids),
                         'files': dict(self.base['inspected_file_hashes'])}
        self.write_json('private-before.json', self.snapshot)
        self.write_json('state.json', {'state': 'OVERRIDE_INSTALLED', 'target': str(self.target)})
        self.write_json('report.json', {'status': 'STOP', 'phase': 'CUTOVER',
                                        'reason': 'STOP_DEPENDENCIES_CHANGED'})
        self.current_units = copy.deepcopy(self.units)
        self.current_units[cutover.BACKEND].update({
            'ExecStart': 'candidate', 'DropInPaths': shlex.quote(str(self.target))})
        self.current_dependencies = {service: dependency_fixture() for service in self.ids}
        self.writes = []

        def require(condition, reason):
            if not condition:
                raise RuntimeError(reason)

        def safe_path(path, exists=True):
            path = Path(path)
            require(path.is_relative_to(root) and not path.is_symlink(), 'UNSAFE_TEST_PATH')
            require(not exists or path.exists(), 'MISSING_TEST_PATH')
            return path

        def atomic_write(path, data):
            self.writes.append((Path(path).name, json.loads(data)))
            Path(path).write_bytes(data)

        def command(arguments):
            self.assertEqual(arguments, ['systemctl', 'daemon-reload'])
            self.current_units = copy.deepcopy(self.units)

        self.r = SimpleNamespace(
            SERVICES=tuple(self.ids), require=require, safe_path=safe_path,
            bounded=lambda path: Path(path).read_bytes(),
            file_hash=self.file_hash, encoded=lambda data: json.dumps(data).encode(),
            exec_start=lambda value: ('/usr/bin/env', self.argv) if value == 'candidate'
            else (value, [value]),
            systemd_info=lambda service: copy.deepcopy(self.current_units[service]),
            atomic_write=Mock(side_effect=atomic_write), command=Mock(side_effect=command),
        )
        self.identity = lambda service: copy.deepcopy(self.ids[service])
        self.dependencies = lambda service: cutover.dependency_shape(self.current_dependencies[service])
        self.addCleanup(patch.stopall)
        patch.object(cutover, 'CANDIDATE', self.candidate).start()
        patch.object(cutover, 'TARGET', self.target).start()
        self.real_lstat = Path.lstat

        def fixture_lstat(path):
            actual = self.real_lstat(path)
            if path == self.target and not stat.S_ISLNK(actual.st_mode):
                # Windows cannot represent Linux root/0600 semantics. Preserve the
                # real hard-link count, inode checks, and symlink mode; fake only
                # the reviewed Linux ownership/permission attributes.
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0,
                                       st_nlink=actual.st_nlink)
            return actual

        patch.object(Path, 'lstat', fixture_lstat).start()
        # Directory fsync is Linux-only; the file removal itself remains real in
        # this fresh temporary directory. Do not mock file identity or contents.
        patch.object(cutover.os, 'O_DIRECTORY', getattr(os, 'O_DIRECTORY', 0), create=True).start()
        self.directory_open = patch.object(cutover.os, 'open', return_value=456).start()
        self.directory_fsync = patch.object(cutover.os, 'fsync').start()
        self.directory_close = patch.object(cutover.os, 'close').start()

    @staticmethod
    def file_hash(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def write_json(self, name, data):
        (self.work / name).write_text(json.dumps(data), encoding='utf-8')

    def recover(self):
        return cutover.recover_not_restarted(
            self.r, self.base, self.receipt, self.payload, self.argv,
            self.identity, self.dependencies)

    def assert_stops_without_mutation(self, reason):
        original_target = self.target.read_bytes()
        original_state = (self.work / 'state.json').read_bytes()
        with self.assertRaisesRegex(RuntimeError, reason):
            self.recover()
        self.assertTrue(self.target.exists())
        self.assertEqual(self.target.read_bytes(), original_target)
        self.assertEqual((self.work / 'state.json').read_bytes(), original_state)
        self.assertEqual(self.writes, [])
        self.r.command.assert_not_called()
        self.directory_open.assert_not_called()

    def test_order_only_change_recovers_override_without_service_restart(self):
        for dependencies in self.current_dependencies.values():
            for key in cutover.DEPENDENCY_LISTS:
                dependencies[key] = 'beta.service alpha.service'
        previous_ids = copy.deepcopy(self.ids)
        self.assertEqual(self.recover(), self.work)
        self.assertFalse(self.target.exists())
        self.assertEqual(self.witness.read_bytes(), self.payload)
        self.assertEqual(self.ids, previous_ids)
        self.r.command.assert_called_once_with(['systemctl', 'daemon-reload'])
        self.assertEqual([state['state'] for _, state in self.writes],
                         ['RECOVERING_NOT_RESTARTED', 'RECOVERED_WITHOUT_RESTART'])
        self.directory_fsync.assert_called_once_with(456)

    def test_changed_process_id_prevents_recovery(self):
        self.ids[cutover.BACKEND]['pid'] = '999'
        self.assert_stops_without_mutation('RECOVERY_PROCESS_CHANGED')

    def test_changed_chroma_invocation_prevents_recovery(self):
        self.ids[cutover.CHROMA]['invocation'] = 'f' * 32
        self.assert_stops_without_mutation('RECOVERY_PROCESS_CHANGED')

    def test_changed_config_prevents_recovery(self):
        self.config.write_bytes(b'external edit')
        self.assert_stops_without_mutation('RECOVERY_CONFIG_CHANGED')

    def test_changed_backend_unit_prevents_recovery(self):
        self.current_units[cutover.BACKEND]['WorkingDirectory'] = '/unexpected'
        self.assert_stops_without_mutation('RECOVERY_UNIT_CHANGED')

    def test_added_dependency_prevents_recovery(self):
        self.current_dependencies[cutover.CHROMA]['Requires'] += ' unexpected.service'
        self.assert_stops_without_mutation('STOP_DEPENDENCIES_CHANGED')

    def test_removed_dependency_prevents_recovery(self):
        self.current_dependencies[cutover.BACKEND]['PartOf'] = 'alpha.service'
        self.assert_stops_without_mutation('STOP_DEPENDENCIES_CHANGED')

    def test_changed_refuse_manual_stop_prevents_recovery(self):
        self.current_dependencies[cutover.BACKEND]['RefuseManualStop'] = 'yes'
        self.assert_stops_without_mutation('STOP_DEPENDENCIES_CHANGED')

    def test_restart_requested_state_prevents_recovery(self):
        self.write_json('state.json', {'state': 'BACKEND_RESTART_REQUESTED', 'target': str(self.target)})
        self.assert_stops_without_mutation('RECOVERY_STATE_NOT_ELIGIBLE')

    def test_different_failure_reason_prevents_recovery(self):
        self.write_json('report.json', {'status': 'STOP', 'phase': 'CUTOVER', 'reason': 'OTHER_FAILURE'})
        self.assert_stops_without_mutation('RECOVERY_STATE_NOT_ELIGIBLE')

    def test_foreign_identical_file_prevents_recovery(self):
        self.target.unlink()
        self.target.write_bytes(self.payload)
        self.assert_stops_without_mutation('RECOVERY_OWNERSHIP_AMBIGUOUS')

    def test_changed_owned_override_prevents_recovery(self):
        self.target.write_bytes(b'externally modified override')
        self.assert_stops_without_mutation('RECOVERY_OVERRIDE_CHANGED')

    def test_extra_hard_link_prevents_recovery(self):
        os.link(self.target, self.candidate / 'unexpected-link')
        self.assert_stops_without_mutation('RECOVERY_OVERRIDE_CHANGED')

    def test_target_symlink_prevents_recovery(self):
        self.target.unlink()
        try:
            self.target.symlink_to(self.witness)
        except OSError as error:
            self.skipTest('Test host does not permit symlinks: ' + type(error).__name__)
        self.assert_stops_without_mutation('UNSAFE_TEST_PATH')


if __name__ == '__main__':
    unittest.main()
