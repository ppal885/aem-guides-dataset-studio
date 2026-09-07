"""Portable ownership regressions; no Chroma, services, VM, or network access.

The optional Linux cases inspect kernel TCP tables or open temporary ordinary
files and invoke lsof. They never open a real database or start a service.
"""
from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
from itertools import repeat
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import socket
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
            "/proc/self/ns/net": self.file_info(device=4, inode=4026531840),
            str(self.process / "ns/net"): self.file_info(device=4, inode=4026531840),
        }
        self.links = {str(self.fds[0]): str(self.sqlite), str(self.fds[1]): "socket:[4001]"}
        self.content = {
            str(self.process / "stat"): self.process_stat(),
            str(self.process / "cgroup"): b"0::/system.slice/chroma.service\n",
            str(self.process / "cmdline"): b"\0".join(
                [b"chroma", b"run", b"--path", str(self.run / "chroma_db").encode(),
                 b"--host", b"127.0.0.1", b""]),
            "/proc/net/tcp": self.listener_table(),
            "/proc/net/tcp6": self.listener_header(remote="remote_address"),
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
    def listener_header(remote="rem_address"):
        return ("  sl  local_address " + remote + " st tx_queue rx_queue tr tm->when "
                "retrnsmt uid timeout inode\n").encode()

    @classmethod
    def listener_table(cls, address="0100007F:1F40", inode="4001", state="0A"):
        remote = "0" * len(address.split(":")[0]) + ":0000"
        return cls.listener_header() + ("0: " + address + " " + remote + " " + state
                + " 00000000:00000000 00:00000000 00000000 0 0 " + inode + "\n").encode()

    def disable_ipv6(self):
        self.content["/proc/net/tcp6"] = FileNotFoundError("private missing IPv6 table")
        self.content["/sys/module/ipv6/parameters/disable"] = b"1\n"

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
        if str(value).startswith(("/proc", "/sys")):
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
        self.assertTrue(result["network_namespace_matches"])
        self.assertEqual(json.loads(self.fixture.report.read_text()), result)

    def test_ipv4_only_owner_passes_all_proofs_with_explicit_kernel_evidence(self):
        self.fixture.disable_ipv6()
        with self.fixture.patches():
            result = subject.verify_owner(self.fixture.run)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["single_owner_pid"], 321)
        self.assertEqual(result["lsof"]["pids"], [321])
        self.assertTrue(result["copy_sqlite_fd_proven"])
        self.assertTrue(result["process_view_sqlite_matches"])
        self.assertTrue(result["loopback_listener_owned"])
        self.assertTrue(result["network_namespace_matches"])
        self.assertTrue(result["process_identity_stable"])
        self.assertEqual(result["listener_inventory"]["tables"]["tcp6"], {
            "status": "ABSENT_KERNEL_IPV6_DISABLED", "proof": "ipv6_module_disable=1"})
        self.assertEqual(result["listener_inventory"]["port_8000_listener_count"], 1)
        self.assertEqual(json.loads(self.fixture.report.read_text()), result)

    def test_ipv4_only_does_not_bypass_other_owner_checks(self):
        for stage, failure in (
                ("pid", "CHROMA_NOT_SOLE_STORE_OWNER"),
                ("cgroup", "CHROMA_CGROUP_MISMATCH"),
                ("target", "CHROMA_PROCESS_TARGET_MISMATCH"),
                ("sqlite_view", "CHROMA_PROCESS_VIEW_SQLITE_MISMATCH"),
                ("sqlite_fd", "CHROMA_COPY_FD_NOT_PROVEN"),
                ("socket_fd", "CHROMA_PORT_OWNED_BY_OTHER_PROCESS"),
                ("pid_change", "CHROMA_PROCESS_CHANGED_DURING_CHECK")):
            with self.subTest(stage=stage):
                self.fixture = ProcFixture(Path(self.directory.name))
                self.fixture.disable_ipv6()
                if stage == "pid":
                    self.fixture.result.stdout = b"321\n654\n"
                elif stage == "cgroup":
                    self.fixture.content[str(self.fixture.process / "cgroup")] = b"0::/other.service\n"
                elif stage == "target":
                    self.fixture.content[str(self.fixture.process / "cmdline")] = b"chroma\0/other/store\0"
                elif stage == "sqlite_view":
                    self.fixture.stats[str(self.fixture.process_sqlite)] = self.fixture.file_info(inode=43)
                elif stage == "sqlite_fd":
                    self.fixture.stats[str(self.fixture.fds[0])] = self.fixture.file_info(inode=43)
                elif stage == "socket_fd":
                    self.fixture.links[str(self.fixture.fds[1])] = "socket:[9999]"
                else:
                    self.fixture.wait_values[-1] = 654
                self.verify_failure(failure)

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
        self.fixture.content["/proc/net/tcp"] = self.fixture.listener_header()
        self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")

    def test_additional_ipv6_listener_is_rejected(self):
        self.fixture.content["/proc/net/tcp6"] = self.fixture.listener_table(
            address="00000000000000000000000000000000:1F40", inode="4002")
        self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")

    def test_ipv6_competitor_is_rejected_even_when_module_parameter_says_disabled(self):
        self.fixture.content["/sys/module/ipv6/parameters/disable"] = b"1\n"
        self.fixture.content["/proc/net/tcp6"] = self.fixture.listener_table(
            address="00000000000000000000000000000000:1F40", inode="4002")
        report = self.verify_failure("CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")
        self.assertEqual(report["listener_inventory"]["port_8000_listener_count"], 2)
        self.assertEqual(report["listener_inventory"]["tables"]["tcp6"]["status"], "READABLE")

    def test_missing_ipv6_without_proof_persists_redacted_failure(self):
        self.fixture.disable_ipv6()
        self.fixture.content["/sys/module/ipv6/parameters/disable"] = PermissionError("private proof detail")
        report = self.verify_failure("IPV6_ABSENCE_NOT_PROVEN")
        self.assertEqual(report["step"], "LOOPBACK_LISTENER")
        self.assertEqual(report["listener_inventory"]["tables"]["tcp6"]["status"], "MISSING")
        self.assertNotIn("private", self.fixture.report.read_text() + self.fixture.stdout.getvalue())

    def test_network_namespace_device_or_inode_mismatch_fails(self):
        for device, inode in ((5, 4026531840), (4, 4026531841)):
            with self.subTest(device=device, inode=inode):
                self.fixture = ProcFixture(Path(self.directory.name))
                self.fixture.stats[str(self.fixture.process / "ns/net")] = self.fixture.file_info(
                    device=device, inode=inode)
                self.verify_failure("CHROMA_NETWORK_NAMESPACE_MISMATCH")

    def test_network_namespace_unreadable_or_missing_at_either_phase_fails(self):
        for path in ("/proc/self/ns/net", "/proc/321/ns/net"):
            for failure in (PermissionError, FileNotFoundError, OSError):
                for phase in ("initial", "revalidation"):
                    with self.subTest(path=path, failure=failure, phase=phase):
                        self.fixture = ProcFixture(Path(self.directory.name))
                        error = failure("private namespace detail")
                        self.fixture.stats[path] = error if phase == "initial" else [
                            self.fixture.stats[path], error]
                        self.verify_failure("CHROMA_NETWORK_NAMESPACE_UNREADABLE")
                        self.assertNotIn("private", self.fixture.report.read_text()
                                         + self.fixture.stdout.getvalue())

    def test_matching_network_namespaces_changing_together_are_rejected(self):
        for device, inode in ((5, 4026531840), (4, 4026531841)):
            with self.subTest(device=device, inode=inode):
                self.fixture = ProcFixture(Path(self.directory.name))
                for path in ("/proc/self/ns/net", "/proc/321/ns/net"):
                    self.fixture.stats[path] = [self.fixture.stats[path], self.fixture.file_info(
                        device=device, inode=inode)]
                self.verify_failure("CHROMA_NETWORK_NAMESPACE_CHANGED")

    def test_service_network_namespace_changing_alone_is_rejected(self):
        path = str(self.fixture.process / "ns/net")
        self.fixture.stats[path] = [self.fixture.stats[path], self.fixture.file_info(
            device=4, inode=4026531841)]
        self.verify_failure("CHROMA_NETWORK_NAMESPACE_MISMATCH")

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


class ListenerInventoryTests(unittest.TestCase):
    def setUp(self):
        self.content = {
            "/proc/net/tcp": ProcFixture.listener_table(),
            "/proc/net/tcp6": ProcFixture.listener_header(remote="remote_address"),
        }
        self.reads = []
        self.diagnostic = {}

    def bounded(self, path, *args, **kwargs):
        self.reads.append(str(path))
        value = self.content[str(path)]
        if isinstance(value, BaseException):
            raise value
        return value

    def inventory(self):
        with patch.object(subject, "Path", PurePosixPath), \
                patch.object(subject, "bounded", side_effect=self.bounded), \
                patch.object(subject, "command") as command, \
                patch.object(socket, "socket") as create_socket:
            result = subject.read_listener_inventory(self.diagnostic)
        command.assert_not_called()
        create_socket.assert_not_called()
        return result

    def verify_failure(self, code):
        with self.assertRaisesRegex(subject.RepairError, "^" + code + "$") as raised:
            self.inventory()
        self.assertNotIn("private", str(raised.exception) + json.dumps(self.diagnostic))

    def test_dual_stack_inventory_reports_counts_without_raw_rows(self):
        self.content["/proc/net/tcp6"] = ProcFixture.listener_table(
            address="00000000000000000000000001000000:1F40", inode="987654321")
        self.assertEqual(self.inventory(), [
            ("0100007F:1F40", "4001"), ("00000000000000000000000001000000:1F40", "987654321")])
        self.assertEqual(self.reads, ["/proc/net/tcp", "/proc/net/tcp6"])
        self.assertEqual(self.diagnostic, {"tables": {
            "tcp": {"status": "READABLE", "rows_checked": 1},
            "tcp6": {"status": "READABLE", "rows_checked": 1}}, "port_8000_listener_count": 2})
        self.assertNotIn("987654321", json.dumps(self.diagnostic))
        self.assertNotIn("0100007F", json.dumps(self.diagnostic))

    def test_missing_ipv6_is_accepted_only_with_exact_stripped_disable_one(self):
        self.content["/proc/net/tcp6"] = FileNotFoundError("private absent table")
        for proof in (b"1", b"1\n", b" \t1\r\n"):
            with self.subTest(proof=proof):
                self.content["/sys/module/ipv6/parameters/disable"] = proof
                self.assertEqual(self.inventory(), [("0100007F:1F40", "4001")])
                self.assertEqual(self.diagnostic["tables"]["tcp6"], {
                    "status": "ABSENT_KERNEL_IPV6_DISABLED", "proof": "ipv6_module_disable=1"})

    def test_missing_ipv6_with_invalid_or_unreadable_proof_fails_closed(self):
        self.content["/proc/net/tcp6"] = FileNotFoundError("private absent table")
        for proof in (b"", b"0\n", b"01\n", b"true\n", b"Y\n", b"1\n0\n", b"1\x00", b"\xff",
                      FileNotFoundError("private missing proof"), PermissionError("private denied proof"),
                      OSError("private unreadable proof"), subject.RepairError("CONFIG_OR_REPORT_TOO_LARGE")):
            with self.subTest(proof=type(proof).__name__ if isinstance(proof, BaseException) else proof):
                self.content["/sys/module/ipv6/parameters/disable"] = proof
                self.verify_failure("IPV6_ABSENCE_NOT_PROVEN")
                self.assertEqual(self.diagnostic["tables"]["tcp6"]["status"], "MISSING")

    def test_interface_ipv6_sysctl_is_not_evidence_of_module_absence(self):
        self.content["/proc/net/tcp6"] = FileNotFoundError("private absent table")
        self.content["/sys/module/ipv6/parameters/disable"] = FileNotFoundError("private missing proof")
        self.content["/proc/sys/net/ipv6/conf/all/disable_ipv6"] = b"1\n"
        self.verify_failure("IPV6_ABSENCE_NOT_PROVEN")
        self.assertNotIn("/proc/sys/net/ipv6/conf/all/disable_ipv6", self.reads)

    def test_missing_ipv4_is_never_accepted(self):
        self.content["/proc/net/tcp"] = FileNotFoundError("private absent IPv4 table")
        self.content["/sys/module/ipv6/parameters/disable"] = b"1\n"
        self.verify_failure("IPV4_TCP_TABLE_MISSING")
        self.assertEqual(self.diagnostic["tables"]["tcp"]["status"], "MISSING")
        self.assertNotIn("/sys/module/ipv6/parameters/disable", self.reads)

    def test_table_permission_and_other_read_errors_cannot_use_disabled_ipv6_exception(self):
        for path in ("/proc/net/tcp", "/proc/net/tcp6"):
            for error_type in (PermissionError, IsADirectoryError, OSError):
                with self.subTest(path=path, error=error_type.__name__):
                    self.setUp()
                    self.content[path] = error_type("private table read detail")
                    self.content["/sys/module/ipv6/parameters/disable"] = b"1\n"
                    self.verify_failure("TCP_TABLE_UNREADABLE")
                    self.assertEqual(self.diagnostic["tables"][PurePosixPath(path).name]["status"], "UNREADABLE")
                    self.assertNotIn("/sys/module/ipv6/parameters/disable", self.reads)

    def test_existing_ipv6_table_is_read_without_consulting_disable_parameter(self):
        self.content["/sys/module/ipv6/parameters/disable"] = b"1\n"
        self.content["/proc/net/tcp6"] = ProcFixture.listener_table(
            address="00000000000000000000000000000000:1F40", inode="4002")
        self.assertEqual(len(self.inventory()), 2)
        self.assertNotIn("/sys/module/ipv6/parameters/disable", self.reads)

    def test_empty_readable_tables_and_both_kernel_header_spellings_are_valid(self):
        for remote in ("rem_address", "remote_address"):
            with self.subTest(remote=remote):
                self.content = {"/proc/net/tcp": ProcFixture.listener_header(remote),
                                "/proc/net/tcp6": ProcFixture.listener_header(remote)}
                self.assertEqual(self.inventory(), [])
                self.assertEqual(self.diagnostic["port_8000_listener_count"], 0)
                self.assertEqual(self.diagnostic["tables"]["tcp"]["rows_checked"], 0)

    def test_only_listen_state_and_port_8000_are_returned(self):
        for table, address in (("tcp", "0100007F"), ("tcp6", "00000000000000000000000001000000")):
            with self.subTest(table=table):
                self.setUp()
                self.content["/proc/net/tcp"] = ProcFixture.listener_header()
                matching = ProcFixture.listener_table(address=address + ":1f40", state="0a")
                established = ProcFixture.listener_table(address=address + ":1F40", state="01", inode="0")
                other_port = ProcFixture.listener_table(address=address + ":1F41", inode="4003")
                self.content["/proc/net/" + table] = matching + b"\n" + b"\n".join(
                    data.splitlines()[1] for data in (established, other_port)) + b"\n"
                self.assertEqual(self.inventory(), [(address.upper() + ":1F40", "4001")])
                self.assertEqual(self.diagnostic["tables"][table]["rows_checked"], 3)

    def test_corrupt_headers_fail_in_either_family(self):
        headers = (b"", b"\n", b"header\n", b"sl local_address rem_address st\n",
                   b"sl local_address rem_address inode st\n", b"sl local_address peer st inode\n",
                   b"local_address sl rem_address st inode\n", b"sl local_address rem_address st inode\xff\n")
        for table in ("tcp", "tcp6"):
            for header in headers:
                with self.subTest(table=table, header=header):
                    self.setUp()
                    self.content["/proc/net/" + table] = header
                    self.verify_failure("TCP_TABLE_MALFORMED")

    def test_corrupt_rows_fail_even_if_they_do_not_describe_port_8000(self):
        for table, address in (("tcp", "0100007F"), ("tcp6", "00000000000000000000000001000000")):
            valid = ProcFixture.listener_table(address=address + ":1F41").splitlines()[1].split()
            corruptions = [(0, b"slot:"), (1, b"private-address:1F41"), (1, b"0100007F:XYZ1"),
                           (1, address.encode() + b":1F4"), (2, b"private-remote:0000"),
                           (3, b"GG"), (3, b"A"), (9, b"-1"), (9, b"+1"), (9, b"private-inode")]
            wrong_width = b"00000000000000000000000001000000:1F41" if table == "tcp" else b"0100007F:1F41"
            corruptions.append((1, wrong_width))
            for index, replacement in corruptions:
                with self.subTest(table=table, index=index, replacement=replacement):
                    self.setUp()
                    fields = valid.copy()
                    fields[index] = replacement
                    self.content["/proc/net/" + table] = ProcFixture.listener_header() + b" ".join(fields) + b"\n"
                    self.verify_failure("TCP_TABLE_MALFORMED")
            with self.subTest(table=table, row="truncated"):
                self.setUp()
                self.content["/proc/net/" + table] = ProcFixture.listener_header() + b" ".join(valid[:9]) + b"\n"
                self.verify_failure("TCP_TABLE_MALFORMED")

    def test_listening_sockets_require_positive_inode_even_on_other_ports(self):
        for table, address in (("tcp", "0100007F"), ("tcp6", "00000000000000000000000001000000")):
            for port in ("1F40", "1F41"):
                with self.subTest(table=table, port=port):
                    self.setUp()
                    self.content["/proc/net/" + table] = ProcFixture.listener_table(
                        address=address + ":" + port, inode="0")
                    self.verify_failure("TCP_LISTENER_INODE_INVALID")

    def test_bounded_table_read_failure_is_fatal(self):
        for table in ("tcp", "tcp6"):
            with self.subTest(table=table):
                self.setUp()
                self.content["/proc/net/" + table] = subject.RepairError("CONFIG_OR_REPORT_TOO_LARGE")
                self.verify_failure("CONFIG_OR_REPORT_TOO_LARGE")


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


@unittest.skipUnless(sys.platform == "linux", "native TCP inventory regression requires Linux")
class NativeListenerInventoryTests(unittest.TestCase):
    def test_actual_kernel_tables_are_supported_without_network_or_service_operations(self):
        diagnostic = {}
        with patch.object(subject, "command") as command, patch.object(socket, "socket") as create_socket:
            listeners = subject.read_listener_inventory(diagnostic)
        command.assert_not_called()
        create_socket.assert_not_called()
        self.assertEqual(diagnostic["tables"]["tcp"]["status"], "READABLE")
        self.assertIn(diagnostic["tables"]["tcp6"]["status"],
                      {"READABLE", "ABSENT_KERNEL_IPV6_DISABLED"})
        self.assertEqual(diagnostic["port_8000_listener_count"], len(listeners))


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
