"""Portable ownership regressions; no Chroma, services, VM, or network access.

The optional Linux case opens only temporary ordinary files in this Python
process and invokes lsof. It never opens a real database or starts a service.
"""
from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
from itertools import repeat
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "routing_ownership_subject", Path(__file__).with_name("repair_vm_chroma_routing.py"))
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def scan_result(code=1, stdout=b"321\n", stderr=b""):
    return subprocess.CompletedProcess(["lsof"], code, stdout, stderr)


def visible_proc_summary():
    return {"scope": "VISIBLE_PROC_PROCESSES", "processes_checked": 1,
            "fds_checked": 2, "exited_processes": 0, "vanished_fds": 0}


class LsofScanTests(unittest.TestCase):
    def setUp(self):
        visibility = patch.object(subject, "proc_visibility_check", side_effect=visible_proc_summary)
        visibility.start()
        self.addCleanup(visibility.stop)

    def test_pid_output_is_accepted_with_either_supported_exit_code(self):
        for code in (0, 1):
            with self.subTest(code=code), patch.object(subject, "command", return_value=scan_result(code)):
                diagnostic = {}
                self.assertIs(subject.lsof_scan(PurePosixPath("/fixture"), diagnostic), diagnostic)
                self.assertEqual(diagnostic["pids"], [321])
                self.assertEqual(diagnostic["returncode"], code)
                self.assertTrue(diagnostic["pid_output_valid"])
                self.assertEqual(diagnostic["proc_visibility"], visible_proc_summary())

    def test_repeated_pids_are_deduplicated_and_sorted(self):
        with patch.object(subject, "command", return_value=scan_result(stdout=b"987\n321\n987\n")):
            self.assertEqual(subject.lsof_scan(PurePosixPath("/fixture"))["pids"], [321, 987])

    def test_warning_enable_flag_follows_terse_flag(self):
        path = PurePosixPath("/fixture")
        with patch.object(subject, "command", return_value=scan_result()) as command:
            subject.lsof_scan(path)
        command.assert_called_once_with(
            ["lsof", "-nP", "-t", "+w", "+D", str(path)], timeout=120, allow=None)

    def test_empty_exit_one_is_a_valid_empty_scan(self):
        with patch.object(subject, "command", return_value=scan_result(stdout=b"")):
            self.assertEqual(subject.lsof_scan(PurePosixPath("/fixture"))["pids"], [])

    def test_empty_exit_zero_is_inconclusive(self):
        with patch.object(subject, "command", return_value=scan_result(0, b"")):
            with self.assertRaisesRegex(subject.RepairError, "^LSOF_EMPTY_SUCCESS_INCONCLUSIVE$"):
                subject.lsof_scan(PurePosixPath("/fixture"))

    def test_all_stderr_warnings_block_even_with_expected_pid(self):
        for warning in (b"WARNING: private fixture path", b"Permission denied",
                        b"cannot stat private fixture", b"unrecognized diagnostic"):
            for code in (0, 1):
                with self.subTest(warning=warning, code=code):
                    with patch.object(subject, "command", return_value=scan_result(code, stderr=warning)):
                        with self.assertRaisesRegex(subject.RepairError, "^LSOF_WARNING_OR_ERROR$"):
                            subject.lsof_scan(PurePosixPath("/fixture"))

    def test_non_numeric_and_mixed_pid_output_is_rejected(self):
        for output in (b"not-a-pid\n", b"321\nnot-a-pid\n", b"0\n", b"-321\n",
                       b"+321\n", b"0321\n", b" 321\n", b"321 \n", b"321\n\n",
                       b"321 654\n", b"12345678901\n", b"\xff\n"):
            with self.subTest(output=output):
                diagnostic = {}
                with patch.object(subject, "command", return_value=scan_result(stdout=output)):
                    with self.assertRaisesRegex(subject.RepairError, "^LSOF_INVALID_PID_OUTPUT$"):
                        subject.lsof_scan(PurePosixPath("/fixture"), diagnostic)
                self.assertEqual(diagnostic["pids"], [])
                self.assertFalse(diagnostic["pid_output_valid"])

    def test_unexpected_exit_codes_and_signals_are_rejected_with_pid_output(self):
        for code in (2, 127, 255, -9, -15):
            with self.subTest(code=code), patch.object(subject, "command", return_value=scan_result(code)):
                with self.assertRaisesRegex(subject.RepairError, "^LSOF_UNEXPECTED_EXIT$"):
                    subject.lsof_scan(PurePosixPath("/fixture"))

    def test_timeout_is_redacted_and_recorded(self):
        diagnostic = {}
        error = subprocess.TimeoutExpired(
            ["lsof", "/fixture-private-target"], 120,
            output=b"private output", stderr=b"private warning")
        with patch.object(subject, "command", side_effect=error):
            with self.assertRaisesRegex(subject.RepairError, "^LSOF_TIMEOUT$") as raised:
                subject.lsof_scan(PurePosixPath("/fixture"), diagnostic)
        self.assertEqual(diagnostic["failure"], "LSOF_TIMEOUT")
        self.assertIsNone(diagnostic["returncode"])
        self.assertNotIn("private", str(raised.exception) + json.dumps(diagnostic))

    def test_execution_error_is_redacted_and_recorded(self):
        diagnostic = {}
        with patch.object(subject, "command", side_effect=OSError("private OS detail")):
            with self.assertRaisesRegex(subject.RepairError, "^LSOF_EXECUTION_FAILED$") as raised:
                subject.lsof_scan(PurePosixPath("/fixture"), diagnostic)
        self.assertEqual(diagnostic["failure"], "LSOF_EXECUTION_FAILED")
        self.assertNotIn("private", str(raised.exception) + json.dumps(diagnostic))

    def test_cold_store_still_rejects_exit_one_with_an_owner(self):
        output = io.StringIO()
        with patch.object(subject, "command", return_value=scan_result()), redirect_stdout(output):
            with self.assertRaisesRegex(subject.RepairError, "^STORE_OPEN_OR_LSOF_INCONCLUSIVE$"):
                subject.no_open_files(PurePosixPath("/fixture-private-target"))
        self.assertIn('"pids": [321]', output.getvalue())
        self.assertNotIn("fixture-private-target", output.getvalue())


class ProcFixture:
    """Model /proc without creating symlinks or depending on Windows inode rules."""

    def __init__(self, report_directory):
        fixture = self

        class FixturePath(PurePosixPath):
            def stat(self):
                value = fixture.stats[str(self)]
                if isinstance(value, list):
                    value = value.pop(0)
                if isinstance(value, BaseException):
                    raise value
                return value

            def iterdir(self):
                if self != fixture.process / "fd":
                    raise AssertionError("Unexpected fake directory enumeration")
                return iter(fixture.fds)

        self.path_type = FixturePath
        self.run = FixturePath("/app/storage/aem-chroma-routing-fixture")
        self.pid = 321
        self.process = FixturePath("/proc/321")
        self.sqlite = self.run / "chroma_db/chroma.sqlite3"
        self.process_sqlite = self.process / "root" / str(self.sqlite).lstrip("/")
        self.fds = [self.process / "fd/5", self.process / "fd/6"]
        self.stats = {
            str(self.sqlite): self.file_info(),
            str(self.process_sqlite): self.file_info(),
            str(self.fds[0]): self.file_info(),
            str(self.fds[1]): SimpleNamespace(st_mode=stat.S_IFSOCK, st_dev=0, st_ino=4001),
        }
        self.links = {str(self.fds[0]): str(self.sqlite), str(self.fds[1]): "socket:[4001]"}
        self.content = {
            str(self.process / "stat"): self.process_stat(),
            str(self.process / "cgroup"): b"0::/system.slice/chroma.service\n",
            str(self.process / "cmdline"): b"\0".join(
                [b"chroma", b"run", b"--path", str(self.run / "chroma_db").encode(),
                 b"--host", b"127.0.0.1", b""]),
            "/proc/net/tcp": self.listener_table(),
            "/proc/net/tcp6": b"header\n",
        }
        self.result = scan_result()
        self.wait_values = [self.pid, self.pid]
        self.report = report_directory / "ownership-check.json"
        self.stdout = io.StringIO()
        self.real_atomic_write = subject.atomic_write

    @staticmethod
    def file_info(device=17, inode=42, mode=stat.S_IFREG | 0o600):
        return SimpleNamespace(st_mode=mode, st_dev=device, st_ino=inode)

    @staticmethod
    def process_stat(start=9001):
        # comm includes both spaces and parentheses, as permitted by /proc/stat.
        return ("321 (chroma (worker) name) " + " ".join(["S"] + ["0"] * 18 + [str(start)])).encode()

    @staticmethod
    def listener_table(address="0100007F:1F40", inode="4001"):
        return ("header\n0: " + address + " 00000000:0000 0A 00000000:00000000 "
                "00:00000000 00000000 0 0 " + inode + "\n").encode()

    def bounded(self, path, *_args, **_kwargs):
        value = self.content[str(path)]
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def save_report(self, path, data):
        if path != self.run / "ownership-check.json":
            raise AssertionError("Unexpected write outside the ownership report")
        self.real_atomic_write(self.report, data)

    def path(self, value):
        if str(value) in ("/proc", "/proc/net"):
            return self.path_type(value)
        return Path(value)

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(subject, "Path", side_effect=self.path))
        stack.enter_context(patch.object(subject, "bounded", side_effect=self.bounded))
        stack.enter_context(patch.object(subject, "wait_running", side_effect=self.wait_values))
        stack.enter_context(patch.object(subject, "proc_visibility_check", side_effect=visible_proc_summary))
        stack.enter_context(patch.object(subject, "command", side_effect=lambda *_a, **_kw: self.result))
        stack.enter_context(patch.object(subject.os, "readlink", side_effect=lambda path: self.links[str(path)]))
        stack.enter_context(patch.object(subject, "atomic_write", side_effect=self.save_report))
        stack.enter_context(redirect_stdout(self.stdout))
        return stack


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.fixture = ProcFixture(Path(self.directory.name))

    def verify_failure(self, code):
        with self.fixture.patches():
            with self.assertRaisesRegex(subject.RepairError, "^" + code + "$"):
                subject.verify_owner(self.fixture.run)
        report = json.loads(self.fixture.report.read_text())
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["failure"], code)
        self.assertNotIn("single_owner_pid", report)
        self.assertIn("OWNERSHIP_CHECK=", self.fixture.stdout.getvalue())
        self.assertNotIn(str(self.fixture.sqlite), self.fixture.stdout.getvalue())
        return report

    def test_exit_one_owner_passes_all_proofs_and_persists_report(self):
        with self.fixture.patches():
            result = subject.verify_owner(self.fixture.run)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["single_owner_pid"], 321)
        self.assertEqual(result["lsof"]["returncode"], 1)
        self.assertTrue(result["copy_sqlite_fd_proven"])
        self.assertTrue(result["loopback_listener_owned"])
        self.assertTrue(result["process_identity_stable"])
        self.assertEqual(json.loads(self.fixture.report.read_text()), result)

    def test_exit_zero_owner_also_passes_all_proofs(self):
        self.fixture.result.returncode = 0
        with self.fixture.patches():
            self.assertEqual(subject.verify_owner(self.fixture.run)["status"], "PASS")

    def test_no_pid_is_not_ownership_proof(self):
        self.fixture.result.stdout = b""
        self.verify_failure("CHROMA_NOT_SOLE_STORE_OWNER")

    def test_other_pid_is_not_ownership_proof(self):
        self.fixture.result.stdout = b"654\n"
        self.verify_failure("CHROMA_NOT_SOLE_STORE_OWNER")

    def test_expected_pid_plus_other_pid_is_not_exclusive(self):
        self.fixture.result.stdout = b"321\n654\n"
        self.verify_failure("CHROMA_NOT_SOLE_STORE_OWNER")

    def test_same_sqlite_path_with_wrong_fd_inode_fails(self):
        self.fixture.stats[str(self.fixture.fds[0])] = self.fixture.file_info(inode=43)
        self.verify_failure("CHROMA_COPY_FD_NOT_PROVEN")

    def test_same_inode_on_wrong_fd_device_fails(self):
        self.fixture.stats[str(self.fixture.fds[0])] = self.fixture.file_info(device=18)
        self.verify_failure("CHROMA_COPY_FD_NOT_PROVEN")

    def test_process_root_namespace_with_wrong_sqlite_inode_fails(self):
        self.fixture.stats[str(self.fixture.process_sqlite)] = self.fixture.file_info(inode=43)
        report = self.verify_failure("CHROMA_PROCESS_VIEW_SQLITE_MISMATCH")
        self.assertFalse(report["process_view_sqlite_matches"])

    def test_process_root_namespace_with_wrong_sqlite_device_fails(self):
        self.fixture.stats[str(self.fixture.process_sqlite)] = self.fixture.file_info(device=18)
        self.verify_failure("CHROMA_PROCESS_VIEW_SQLITE_MISMATCH")

    def test_non_regular_sqlite_target_is_rejected(self):
        self.fixture.stats[str(self.fixture.sqlite)] = self.fixture.file_info(mode=stat.S_IFDIR | 0o700)
        self.verify_failure("CHROMA_SQLITE_NOT_REGULAR")

    def test_sqlite_inode_changed_during_check_fails(self):
        self.fixture.stats[str(self.fixture.sqlite)] = [
            self.fixture.file_info(), self.fixture.file_info(inode=43)]
        self.verify_failure("CHROMA_SQLITE_CHANGED_DURING_CHECK")

    def test_sqlite_device_changed_during_check_fails(self):
        self.fixture.stats[str(self.fixture.sqlite)] = [
            self.fixture.file_info(), self.fixture.file_info(device=18)]
        self.verify_failure("CHROMA_SQLITE_CHANGED_DURING_CHECK")

    def test_changed_service_pid_fails(self):
        self.fixture.wait_values[-1] = 654
        self.verify_failure("CHROMA_PROCESS_CHANGED_DURING_CHECK")

    def test_reused_pid_with_changed_start_time_fails(self):
        self.fixture.content[str(self.fixture.process / "stat")] = [
            self.fixture.process_stat(9001), self.fixture.process_stat(9002)]
        self.verify_failure("CHROMA_PROCESS_CHANGED_DURING_CHECK")

    def test_malformed_process_start_time_fails(self):
        self.fixture.content[str(self.fixture.process / "stat")] = b"321 (chroma) S 0"
        self.verify_failure("CHROMA_PROCESS_STAT_INVALID")

    def test_wrong_service_cgroup_fails(self):
        self.fixture.content[str(self.fixture.process / "cgroup")] = b"0::/system.slice/other.service\n"
        self.verify_failure("CHROMA_CGROUP_MISMATCH")

    def test_wrong_process_store_target_fails(self):
        self.fixture.content[str(self.fixture.process / "cmdline")] = b"chroma\0/other/store\0" + b"127.0.0.1\0"
        self.verify_failure("CHROMA_PROCESS_TARGET_MISMATCH")

    def test_listener_socket_owned_by_other_process_fails(self):
        self.fixture.links[str(self.fixture.fds[1])] = "socket:[9999]"
        self.verify_failure("CHROMA_PORT_OWNED_BY_OTHER_PROCESS")

    def test_public_listener_is_rejected(self):
        self.fixture.content["/proc/net/tcp"] = self.fixture.listener_table(address="00000000:1F40")
        self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")

    def test_no_listener_is_rejected(self):
        self.fixture.content["/proc/net/tcp"] = b"header\n"
        self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")

    def test_additional_ipv6_listener_is_rejected(self):
        self.fixture.content["/proc/net/tcp6"] = self.fixture.listener_table(
            address="00000000000000000000000000000000:1F40", inode="4002")
        self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")

    def test_disappearing_sqlite_fd_is_not_accepted(self):
        self.fixture.stats[str(self.fixture.fds[0])] = FileNotFoundError("private fd detail")
        self.verify_failure("CHROMA_COPY_FD_NOT_PROVEN")

    def test_warning_evidence_is_redacted_in_persisted_report_and_console(self):
        raw_warning = b"lsof: WARNING: cannot stat /fixture-private-path: Permission denied\n"
        self.fixture.result.stderr = raw_warning
        report = self.verify_failure("LSOF_WARNING_OR_ERROR")
        self.assertEqual(report["lsof"]["stderr_sha256"], subject.digest(raw_warning))
        self.assertEqual(report["lsof"]["stderr_bytes"], len(raw_warning))
        self.assertIn("PERMISSION_DENIED", report["lsof"]["stderr_categories"])
        self.assertIn("STAT_FAILED", report["lsof"]["stderr_categories"])
        self.assertIn("WARNING", report["lsof"]["stderr_categories"])
        self.assertNotIn("fixture-private-path", self.fixture.report.read_text() + self.fixture.stdout.getvalue())

    def test_timeout_diagnostic_is_persisted_without_raw_output(self):
        error = subprocess.TimeoutExpired(["lsof", "/fixture-private-target"], 120,
                                          output=b"private output", stderr=b"private warning")
        with self.fixture.patches(), patch.object(subject, "command", side_effect=error):
            with self.assertRaisesRegex(subject.RepairError, "^LSOF_TIMEOUT$"):
                subject.verify_owner(self.fixture.run)
        report = json.loads(self.fixture.report.read_text())
        self.assertEqual(report["failure"], "LSOF_TIMEOUT")
        self.assertEqual(report["lsof"]["failure"], "LSOF_TIMEOUT")
        self.assertNotIn("private", self.fixture.report.read_text() + self.fixture.stdout.getvalue())

    def test_proc_read_error_is_persisted_without_raw_exception_message(self):
        self.fixture.content[str(self.fixture.process / "stat")] = PermissionError("private process detail")
        with self.fixture.patches():
            with self.assertRaises(PermissionError):
                subject.verify_owner(self.fixture.run)
        report = json.loads(self.fixture.report.read_text())
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["failure"], "PermissionError")
        self.assertNotIn("private", self.fixture.report.read_text() + self.fixture.stdout.getvalue())

    def test_visibility_failure_is_persisted_before_lsof_can_run(self):
        with self.fixture.patches(), patch.object(
                subject, "proc_visibility_check",
                side_effect=subject.RepairError("PROC_INSPECTION_PERMISSION_DENIED")), \
                patch.object(subject, "command") as command:
            with self.assertRaisesRegex(subject.RepairError, "^PROC_INSPECTION_PERMISSION_DENIED$"):
                subject.verify_owner(self.fixture.run)
        command.assert_not_called()
        report = json.loads(self.fixture.report.read_text())
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["failure"], "PROC_INSPECTION_PERMISSION_DENIED")
        self.assertIsNone(report["lsof"]["returncode"])
        self.assertEqual(report["lsof"]["pids"], [])
        self.assertNotIn(str(self.fixture.sqlite), self.fixture.report.read_text())


class VisibilityFixture:
    """Synthetic process visibility, including bounded process/FD populations."""

    def __init__(self):
        fixture = self

        class FixturePath(PurePosixPath):
            def iterdir(self):
                value = fixture.directories[str(self)]
                if isinstance(value, BaseException):
                    raise value
                return iter(value)

            def stat(self):
                error = fixture.stat_errors.get(str(self))
                if error is not None:
                    raise type(error)(*error.args) from None
                return SimpleNamespace(st_mode=stat.S_IFREG)

            def exists(self):
                return str(self) not in fixture.exited

        self.path_type = FixturePath
        self.process = FixturePath("/proc/321")
        self.fd = self.process / "fd/5"
        self.directories = {"/proc": [self.process, FixturePath("/proc/self"), FixturePath("/proc/net")],
                            str(self.process / "fd"): [self.fd]}
        self.content = {"/proc/mounts": b"proc /proc proc rw,nosuid,nodev,noexec,relatime 0 0\n",
                        str(self.process / "maps"): b"fixture mapping metadata\n"}
        self.stat_errors = {}
        self.start_values = {}
        self.exited = set()
        self.reads = []
        self.monotonic = lambda: 0

    def bounded(self, path, limit=None):
        self.reads.append((str(path), limit))
        value = self.content[str(path)]
        if isinstance(value, BaseException):
            raise value
        return value

    def start_time(self, path):
        value = self.start_values.get(str(path), 9001)
        if isinstance(value, list):
            value = value.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(subject, "Path", self.path_type))
        stack.enter_context(patch.object(subject, "bounded", side_effect=self.bounded))
        stack.enter_context(patch.object(subject, "process_start_time", side_effect=self.start_time))
        stack.enter_context(patch.object(subject.time, "monotonic", self.monotonic))
        return stack


class ProcVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = VisibilityFixture()

    def verify_failure(self, code):
        with self.fixture.patches():
            with self.assertRaisesRegex(subject.RepairError, "^" + code + "$") as raised:
                subject.proc_visibility_check()
        self.assertNotIn("private", str(raised.exception))

    def test_visible_process_checks_maps_and_fds_and_returns_counts(self):
        with self.fixture.patches():
            result = subject.proc_visibility_check()
        self.assertEqual(result, {"scope": "VISIBLE_PROC_PROCESSES", "processes_checked": 1,
                                  "fds_checked": 1, "exited_processes": 0, "vanished_fds": 0})
        self.assertEqual(self.fixture.reads, [("/proc/mounts", None), ("/proc/321/maps", 8 * 1024 * 1024)])

    def test_hidepid_zero_remains_supported(self):
        self.fixture.content["/proc/mounts"] = b"proc /proc proc rw,hidepid=0 0 0\n"
        with self.fixture.patches():
            self.assertEqual(subject.proc_visibility_check()["processes_checked"], 1)

    def test_hidepid_restrictions_and_ambiguous_mounts_fail_closed(self):
        for mounts in (b"proc /proc proc rw,hidepid=1 0 0\n", b"proc /proc proc rw,hidepid=2 0 0\n",
                       b"proc /proc proc rw,hidepid=invisible 0 0\n", b"root / ext4 rw 0 0\n",
                       b"proc /proc proc rw 0 0\nproc /proc proc ro 0 0\n"):
            with self.subTest(mounts=mounts):
                self.fixture.content["/proc/mounts"] = mounts
                self.verify_failure("PROC_VISIBILITY_RESTRICTED")

    def test_permission_failure_at_each_inspection_stage_is_redacted(self):
        for stage in ("mounts", "processes", "start", "maps", "fds", "fd_stat"):
            with self.subTest(stage=stage):
                self.fixture = VisibilityFixture()
                error = PermissionError("private inaccessible process detail")
                if stage == "mounts":
                    self.fixture.content["/proc/mounts"] = error
                elif stage == "processes":
                    self.fixture.directories["/proc"] = error
                elif stage == "start":
                    self.fixture.start_values[str(self.fixture.process)] = error
                elif stage == "maps":
                    self.fixture.content[str(self.fixture.process / "maps")] = error
                elif stage == "fds":
                    self.fixture.directories[str(self.fixture.process / "fd")] = error
                else:
                    self.fixture.stat_errors[str(self.fixture.fd)] = error
                self.verify_failure("PROC_INSPECTION_PERMISSION_DENIED")

    def test_real_visibility_permission_failure_prevents_lsof_invocation(self):
        self.fixture.stat_errors[str(self.fixture.fd)] = PermissionError("private fd detail")
        with self.fixture.patches(), patch.object(subject, "command") as command:
            with self.assertRaisesRegex(subject.RepairError, "^PROC_INSPECTION_PERMISSION_DENIED$"):
                subject.lsof_scan(PurePosixPath("/fixture"))
        command.assert_not_called()

    def test_other_os_error_is_redacted_and_rejected(self):
        self.fixture.content[str(self.fixture.process / "maps")] = OSError("private OS error")
        self.verify_failure("PROC_INSPECTION_FAILED")

    def test_vanished_fd_is_counted_without_accepting_other_errors(self):
        self.fixture.stat_errors[str(self.fixture.fd)] = FileNotFoundError("vanished")
        with self.fixture.patches():
            result = subject.proc_visibility_check()
        self.assertEqual(result["processes_checked"], 1)
        self.assertEqual(result["vanished_fds"], 1)
        self.assertEqual(result["fds_checked"], 0)

    def test_exited_process_is_counted_if_another_process_is_visible(self):
        exited = self.fixture.path_type("/proc/654")
        self.fixture.directories["/proc"].append(exited)
        self.fixture.start_values[str(exited)] = FileNotFoundError("exited")
        self.fixture.exited.add(str(exited))
        with self.fixture.patches():
            result = subject.proc_visibility_check()
        self.assertEqual(result["processes_checked"], 1)
        self.assertEqual(result["exited_processes"], 1)

    def test_missing_maps_for_a_live_process_is_inconclusive(self):
        self.fixture.content[str(self.fixture.process / "maps")] = FileNotFoundError("private missing maps")
        self.verify_failure("PROC_INSPECTION_INCONCLUSIVE")

    def test_pid_reuse_during_visibility_check_is_rejected(self):
        self.fixture.start_values[str(self.fixture.process)] = [9001, 9002]
        self.verify_failure("PROC_IDENTITY_CHANGED_DURING_CHECK")

    def test_no_visible_processes_fail_closed(self):
        self.fixture.directories["/proc"] = [self.fixture.path_type("/proc/self")]
        self.verify_failure("PROC_VISIBILITY_EMPTY")

    def test_process_count_limit_fails_closed(self):
        self.fixture.directories["/proc"] = repeat(self.fixture.process, 65537)
        self.verify_failure("PROC_VISIBILITY_LIMIT_EXCEEDED")

    def test_fd_count_limit_fails_closed(self):
        self.fixture.directories[str(self.fixture.process / "fd")] = repeat(self.fixture.fd, 262145)
        self.verify_failure("PROC_VISIBILITY_LIMIT_EXCEEDED")

    def test_vanished_fds_also_count_toward_visibility_limit(self):
        self.fixture.directories[str(self.fixture.process / "fd")] = repeat(self.fixture.fd, 262145)
        self.fixture.stat_errors[str(self.fixture.fd)] = FileNotFoundError("vanished")
        self.verify_failure("PROC_VISIBILITY_LIMIT_EXCEEDED")

    def test_deadline_is_enforced_before_process_and_fd_inspection(self):
        for times in ((0, 31), (0, 0, 31)):
            with self.subTest(times=times):
                ticks = iter(times)
                self.fixture.monotonic = lambda: next(ticks)
                self.verify_failure("PROC_VISIBILITY_TIMEOUT")


@unittest.skipUnless(sys.platform == "linux", "native lsof regression requires Linux")
class NativeLsofTests(unittest.TestCase):
    def test_open_file_with_unopened_sibling_reports_pid_at_exit_one(self):
        if os.geteuid() != 0:
            self.skipTest("native lsof regression requires root for all-process visibility")
        lsof = shutil.which("lsof", path="/usr/sbin:/usr/bin:/sbin:/bin")
        if lsof is None:
            self.skipTest("native lsof regression requires lsof in the sanitized system PATH")
        real_command = subject.command
        observed = []

        def native_command(args, **kwargs):
            self.assertEqual(args[0], "lsof")
            result = real_command([lsof, *args[1:]], **kwargs)
            observed.append(result)
            return result

        with tempfile.TemporaryDirectory(prefix="uac-lsof-test-") as directory:
            root = Path(directory)
            held = root / "held-ordinary-file.txt"
            unopened = root / "unopened-sibling.txt"
            held.write_bytes(b"ordinary fixture bytes; not a database")
            unopened.write_bytes(b"unopened ordinary fixture bytes")
            with held.open("rb"), patch.object(subject, "command", side_effect=native_command):
                diagnostic = subject.lsof_scan(root)
            self.assertEqual(len(observed), 1)
            self.assertEqual(diagnostic["returncode"], 1,
                             "This native lsof must exercise +D's exit-one-with-owner behavior")
            self.assertEqual(diagnostic["pids"], [os.getpid()])
            self.assertEqual(diagnostic["stderr_bytes"], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
