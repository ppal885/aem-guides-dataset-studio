"""Synthetic tests only: no VM, systemd, network, backend or real Chroma imports."""
from contextlib import ExitStack, redirect_stdout
from pathlib import Path, PurePosixPath
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("routing_repair", Path(__file__).with_name("repair_vm_chroma_routing.py"))
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


def safe_fixture_path(path, **_kwargs):
    return Path(path)


class UnitTests(unittest.TestCase):
    def test_exec_start_requires_actual_executable_not_substring_wrapper(self):
        value = "{ path=/venv/bin/uvicorn ; argv[]=/venv/bin/uvicorn app.main:app --port 8001 ; ignore_errors=no ; start_time=[n/a] ; pid=0 ; status=0/0 }"
        self.assertEqual(subject.exec_start(value), ("/venv/bin/uvicorn", ["/venv/bin/uvicorn", "app.main:app", "--port", "8001"]))
        for bad in (value + " " + value, value.replace("ignore_errors=no", "ignore_errors=yes"), "anything"):
            with self.assertRaises(subject.RepairError):
                subject.exec_start(bad)

    def test_all_hooks_and_mount_redirections_rejected(self):
        for field in (*subject.SERVICE_HOOKS, "ReadWritePaths", "RootDirectory", "BindPaths"):
            with self.subTest(field=field):
                with self.assertRaises(subject.RepairError):
                    subject.supported_service({"DynamicUser": "no", field: "unexpected"})

    def test_effective_later_dropin_cannot_redirect_original_store(self):
        run = PurePosixPath("/app/storage/aem-chroma-routing-fixture")
        pre = {"repo": "/repo", "launcher": "/venv/bin/chroma", "originals": {"a": "/old/a", "b": "/old/b"}}
        def format_exec(executable, args):
            return "{ path=" + executable + " ; argv[]=" + " ".join(args) + " ; ignore_errors=no ; pid=0 ; status=0/0 }"
        a, args = subject.tuple_backend_command(Path("/repo"))
        rows = {
            "aem-backend.service": {"User": "root", "DynamicUser": "no", "ReadOnlyPaths": "/old/a /old/b",
                                    "ExecStart": format_exec(a, args)},
            "chroma.service": {"User": "root", "DynamicUser": "no", "ReadOnlyPaths": "/old/a /old/b", "WorkingDirectory": str(run),
                               "ExecStart": format_exec("/usr/bin/env", subject.chroma_command(run, pre["launcher"]))},
        }
        with patch.object(subject, "systemd_info", side_effect=lambda service: rows[service]):
            subject.verify_effective_units(run, pre)
            saved = rows["chroma.service"]["ExecStart"]
            rows["chroma.service"]["ExecStart"] = saved.replace(str(run / "chroma_db"), "/old/a")
            with self.assertRaisesRegex(subject.RepairError, "LAUNCH_OVERRIDDEN"):
                subject.verify_effective_units(run, pre)
            rows["chroma.service"]["ExecStart"] = saved
            rows["chroma.service"]["ReadOnlyPaths"] = "/old/a"
            with self.assertRaisesRegex(subject.RepairError, "PROTECTION_OVERRIDDEN"):
                subject.verify_effective_units(run, pre)

    def test_config_cannot_change_between_payload_and_journal_capture(self):
        with tempfile.TemporaryDirectory() as name, patch.object(subject, "safe_path", side_effect=safe_fixture_path):
            root = Path(name)
            path = root / "config"
            path.write_bytes(b"intervening edit")
            with self.assertRaisesRegex(subject.RepairError, "DURING_PLANNING"):
                subject.planned_file(root, path, b"old plus overlay", 0, b"old")
            self.assertEqual(path.read_bytes(), b"intervening edit")
            self.assertFalse((root / "0.before").exists())

    def test_append_preserves_original_bytes_and_has_raw_unquoted_settings(self):
        old = b"\xef\xbb\xbfSECRET=private\r\nKEEP=this value"
        new = subject.append_settings(old, {"CHROMA_HOST": "127.0.0.1", "WORKER": "false"})
        self.assertTrue(new.startswith(old + b"\n"))
        self.assertTrue(new.endswith(b"CHROMA_HOST=127.0.0.1\nWORKER=false\n"))
        with self.assertRaisesRegex(subject.RepairError, "PRIOR_ROUTING"):
            subject.append_settings(new, {})

    def test_invalid_encoding_not_silently_replaced(self):
        with self.assertRaises(UnicodeError):
            subject.append_settings(b"bad=\xff", {})

    def test_scope_and_auth_are_not_silently_overridden(self):
        subject.check_conflicting_scope("CHROMA_TENANT=default_tenant\nCHROMA_AUTH_TOKEN=\n")
        for text in ("CHROMA_DATABASE=custom", "CHROMA_TENANT=${TENANT}", "CHROMA_AUTH_TOKEN=private",
                     "CHROMA_SERVER_AUTHN_CREDENTIALS=private"):
            with self.subTest(text=text), self.assertRaises(subject.RepairError) as raised:
                subject.check_conflicting_scope(text)
            self.assertNotIn("private", str(raised.exception))
        with self.assertRaises(subject.RepairError):
            subject.check_conflicting_scope('CHROMA_DATABASE="default_database"', docker=True)

    @patch.object(subject, "proc_visibility_check", return_value={"processes_checked": 1})
    def test_no_open_files_fails_closed_on_lsof_error(self, _visibility):
        for code, out, err in ((0, b"123", b""), (1, b"", b"warning"), (0, b"", b"")):
            with patch.object(subject, "command", return_value=SimpleNamespace(returncode=code, stdout=out, stderr=err)):
                with self.assertRaises(subject.RepairError):
                    subject.no_open_files(Path("/synthetic"))
        with patch.object(subject, "command", return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"")):
            subject.no_open_files(Path("/synthetic"))

    def test_require_both_services_inactive_not_failed_or_restarting(self):
        good = dict(LoadState="loaded", ActiveState="inactive", SubState="dead", MainPID="0")
        with patch.object(subject, "systemd_info", return_value=good):
            subject.require_stopped()
        for key, value in (("MainPID", "123"), ("ActiveState", "failed"), ("SubState", "auto-restart")):
            with patch.object(subject, "systemd_info", return_value={**good, key: value}):
                with self.assertRaises(subject.RepairError):
                    subject.require_stopped()

    def test_subprocess_uses_clean_environment_and_never_leaks_output(self):
        result = subprocess.CompletedProcess(["tool"], 1, b"private output", b"secret token")
        with patch.object(subject.subprocess, "run", return_value=result) as run:
            with self.assertRaises(subject.RepairError) as error:
                subject.command(["/bin/tool", "literal;argument"])
            kwargs = run.call_args.kwargs
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["env"], {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
            self.assertNotIn("secret", str(error.exception))

    def test_cold_snapshot_detects_bytes_and_preserves_original(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "chroma.sqlite3").write_bytes(b"not a sqlite DB; ordinary byte hashing")
            before = subject.tree_snapshot(root)
            self.assertEqual(before, subject.tree_snapshot(root))
            (root / "chroma.sqlite3").write_bytes(b"changed")
            self.assertNotEqual(before, subject.tree_snapshot(root))

    def test_hardlinks_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "chroma.sqlite3").write_bytes(b"private")
            os.link(root / "chroma.sqlite3", root / "alias")
            with self.assertRaisesRegex(subject.RepairError, "LINK_OR_SPECIAL"):
                subject.tree_snapshot(root)

    def test_atomic_exclusive_publication_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "config"
            subject.atomic_write(path, b"original", absent=True)
            with self.assertRaises(FileExistsError):
                subject.atomic_write(path, b"replacement", absent=True)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_backup_requires_all_members_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            originals = {}
            for label in ("app-storage", "backend-storage"):
                db = root / label / "chroma_db"
                db.mkdir(parents=True)
                (db / "chroma.sqlite3").write_bytes(b"sqlite")
                (db / "hnsw.bin").write_bytes(b"vector bytes")
                originals[label] = db
                with tarfile.open(root / (label + ".tar"), "w") as archive:
                    archive.add(db, arcname="chroma_db")
            def checksum():
                (root / "SHA256SUMS").write_text("".join(subject.file_hash(root / (label + ".tar")) + "  " + label + ".tar\n" for label in originals))
            checksum()
            with patch.object(subject, "safe_path", side_effect=safe_fixture_path), patch.object(subject, "command") as command:
                subject.validated_archives(root, originals)
                self.assertEqual(command.call_count, 2)
                with tarfile.open(root / "app-storage.tar", "w") as archive:
                    archive.add(originals["app-storage"] / "chroma.sqlite3", arcname="chroma_db/chroma.sqlite3")
                with self.assertRaisesRegex(subject.RepairError, "HASH_MISMATCH"):
                    subject.validated_archives(root, originals)
                checksum()
                with self.assertRaisesRegex(subject.RepairError, "MEMBER_SET"):
                    subject.validated_archives(root, originals)

    def test_dropins_use_exact_copy_loopback_and_original_readonly_paths(self):
        a, b = subject.dropins(PurePosixPath("/app/storage/aem-chroma-routing-test"), "/venv/bin/chroma",
                               {"app": "/original/app", "backend": "/original/backend"})
        self.assertIn(b"Requires=chroma.service", a)
        self.assertIn(b"ExecStart=\nExecStart=/usr/bin/env -i", b)
        self.assertIn(b"--host 127.0.0.1 --port 8000 --path /app/storage/aem-chroma-routing-test/chroma_db", b)
        self.assertIn(b"ReadOnlyPaths=/original/app /original/backend", a)
        self.assertNotIn(b"0.0.0.0", b)
        self.assertNotIn(b"pip", b)


class FakeMachine:
    def __init__(self, root, fail=None):
        self.root, self.fail, self.failed = root, fail, False
        self.repo = root / "repo"
        (self.repo / "backend").mkdir(parents=True)
        self.original_env = b"PRIVATE_KEY=do-not-print\nCHROMA_HOST=old\n"
        (self.repo / "backend/.env").write_bytes(self.original_env)
        self.state = root / "state"
        self.state.mkdir()
        self.systemd = root / "systemd"
        self.systemd.mkdir()
        self.services = {service: "inactive" for service in subject.SERVICES}
        self.calls = []
        self.originals = {}
        for label in ("app-storage", "backend-storage"):
            original = root / label / "chroma_db"
            original.mkdir(parents=True)
            (original / "chroma.sqlite3").write_bytes(label.encode())
            self.originals[label] = str(original)
        self.pre = {"repo": str(self.repo), "originals": self.originals,
                    "original_snapshots": {label: subject.tree_snapshot(Path(path)) for label, path in self.originals.items()},
                    "launcher": "/venv/bin/chroma"}
        self.snapshot = {"hash_algorithm": "md5", "catalog": {"jira_qa": {"id": "uuid", "ids": ["1", "2"]}}}
        self.checks = SimpleNamespace(http_json=lambda *_: {}, inspect_inventory=lambda *_: {"match": True},
                                      smoke_vector_queries=lambda *_: {"smoke": True},
                                      verify_backend=lambda *_, **__: {"match": True}, RoutingCheckError=RuntimeError)

    def command(self, args, **_kwargs):
        self.calls.append(args)
        if args[0] == "cp":
            shutil.copytree(Path(args[-2]), Path(args[-1]), copy_function=shutil.copy2)
        if args[:2] == ["systemctl", "start"]:
            if self.fail == args[-1] and not self.failed:
                self.failed = True
                raise subject.RepairError("INJECTED_SERVICE_FAILURE")
            self.services[args[-1]] = "active"
        if args[:2] == ["systemctl", "stop"]:
            self.services[args[-1]] = "inactive"
        return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

    def systemd_info(self, name):
        active = self.services[name]
        return dict(LoadState="loaded", ActiveState=active, SubState="dead" if active == "inactive" else "running",
                    MainPID="0" if active == "inactive" else "321")

    def patches(self):
        stack = ExitStack()
        stack.enter_context(patch.object(subject, "STATE_ROOT", self.state))
        stack.enter_context(patch.object(subject, "SYSTEMD_ROOT", self.systemd))
        stack.enter_context(patch.object(subject, "safe_path", side_effect=safe_fixture_path))
        stack.enter_context(patch.object(subject, "command", side_effect=self.command))
        stack.enter_context(patch.object(subject, "systemd_info", side_effect=self.systemd_info))
        stack.enter_context(patch.object(subject, "no_open_files"))
        stack.enter_context(patch.object(subject, "verify_owner", return_value={"single_owner_pid": 321}))
        stack.enter_context(patch.object(subject, "verify_effective_units"))
        stack.enter_context(patch.object(subject.os, "chown", create=True))
        stack.enter_context(patch.object(subject, "sibling", side_effect=lambda name: self.checks if name == "vm_chroma_routing_checks" else
                                        SimpleNamespace(snapshot=lambda *_: self.snapshot, signature=lambda *_: "hash")))
        stack.enter_context(redirect_stdout(io.StringIO()))
        # Windows permissions are not Unix owner/mode semantics; metadata checks
        # are separately exercised using synthetic stat rows below.
        original_validate = subject.validate_journal
        def validate(run, journal):
            for row in journal["files"]:
                target = Path(row["target"])
                if target.exists():
                    row["mode"] = target.stat().st_mode & 0o777
            return original_validate(run, journal)
        stack.enter_context(patch.object(subject, "validate_journal", side_effect=validate))
        return stack

    def assert_originals(self, test):
        for label, path in self.originals.items():
            test.assertEqual(subject.tree_snapshot(Path(path)), self.pre["original_snapshots"][label])


class TransactionTests(unittest.TestCase):
    def test_ownership_failure_keeps_diagnostics_and_inventory_after_rollback(self):
        real_owner = subject.verify_owner
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            def failed_check(_run, diagnostic):
                diagnostic.update(step="GLOBAL_STORE_OWNERS", lsof={"returncode": 1, "pids": [], "stderr_bytes": 0})
                raise subject.RepairError("CHROMA_NOT_SOLE_STORE_OWNER")
            with machine.patches(), patch.object(subject, "verify_owner", real_owner), \
                    patch.object(subject, "verify_owner_details", side_effect=failed_check):
                with self.assertRaisesRegex(subject.RepairError, "NOT_SOLE_STORE_OWNER"):
                    subject.apply(machine.pre)
                run, = machine.state.iterdir()
                saved = json.loads((run / "journal.json").read_text())
                self.assertEqual(saved["state"], "ROLLED_BACK_SERVICES_STOPPED")
                self.assertEqual(saved["direct_inventory"], {"match": True})
                self.assertEqual(saved["nginx_inventory"], {"match": True})
                diagnostic = json.loads((run / "ownership-check.json").read_text())
                self.assertEqual(diagnostic["failure"], "CHROMA_NOT_SOLE_STORE_OWNER")
                self.assertEqual(diagnostic["lsof"]["returncode"], 1)
                self.assertNotIn(["systemctl", "start", "aem-backend.service"], machine.calls)
                self.assertTrue(all(s == "inactive" for s in machine.services.values()))
                self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)
                machine.assert_originals(self)

    def test_overridden_unit_rolls_back_before_starting_any_service(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches(), patch.object(subject, "verify_effective_units", side_effect=subject.RepairError("CHROMA_LAUNCH_OVERRIDDEN")):
                with self.assertRaisesRegex(subject.RepairError, "LAUNCH_OVERRIDDEN"):
                    subject.apply(machine.pre)
                self.assertFalse(any(args[:2] == ["systemctl", "start"] for args in machine.calls))
                self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)

    def test_interrupt_rolls_back_and_restores_stopped_state(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            machine.checks.inspect_inventory = lambda *_: (_ for _ in ()).throw(KeyboardInterrupt())
            with machine.patches():
                with self.assertRaises(KeyboardInterrupt):
                    subject.apply(machine.pre)
                self.assertTrue(all(s == "inactive" for s in machine.services.values()))
                self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)

    def test_changed_migration_algorithm_stops_before_config_or_service_changes(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            machine.snapshot["hash_algorithm"] = "sha256"
            with machine.patches():
                with self.assertRaisesRegex(subject.RepairError, "MIGRATION_HASH"):
                    subject.apply(machine.pre)
                self.assertFalse(any(args[0] == "systemctl" for args in machine.calls))

    def test_repeated_rollback_does_not_falsely_report_stopped_after_manual_start(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches():
                run, _ = subject.apply(machine.pre)
                subject.rollback(run)
                machine.services["chroma.service"] = "active"
                with self.assertRaisesRegex(subject.RepairError, "MUST_BE_STOPPED"):
                    subject.rollback(run)

    def test_success_then_rollback_preserves_copy_and_restores_exact_config(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches():
                run, journal = subject.apply(machine.pre)
                self.assertEqual(journal["state"], "PASS_ROUTING_ONLY_WRITERS_PAUSED")
                self.assertTrue(all(s == "active" for s in machine.services.values()))
                self.assertIn(b"CHROMA_HOST=127.0.0.1", (machine.repo / "backend/.env").read_bytes())
                machine.assert_originals(self)
                value = subject.rollback(run)
                self.assertEqual(value["state"], "ROLLED_BACK_SERVICES_STOPPED")
                self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)
                self.assertFalse((machine.repo / "backend/.env.docker").exists())
                self.assertTrue((run / "chroma_db/chroma.sqlite3").exists())
                self.assertTrue(all(s == "inactive" for s in machine.services.values()))
                before_calls = len(machine.calls)
                subject.rollback(run)
                self.assertEqual(before_calls, len(machine.calls))
                self.assertNotIn("do-not-print", json.dumps(subject.report(value)))

    def test_service_failures_restore_previous_configs_and_stop_services(self):
        for service in subject.SERVICES:
            with self.subTest(service=service), tempfile.TemporaryDirectory() as name:
                machine = FakeMachine(Path(name), fail=service)
                with machine.patches():
                    with self.assertRaisesRegex(subject.RepairError, "INJECTED"):
                        subject.apply(machine.pre)
                    self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)
                    self.assertFalse((machine.repo / "backend/.env.docker").exists())
                    self.assertTrue(all(s == "inactive" for s in machine.services.values()))
                    machine.assert_originals(self)

    def test_changed_config_blocks_rollback_without_overwrite(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches():
                run, _ = subject.apply(machine.pre)
                path = machine.repo / "backend/.env"
                path.write_bytes(b"another admin's new config")
                with self.assertRaisesRegex(subject.RepairError, "CONFIG_DRIFT"):
                    subject.rollback(run)
                self.assertEqual(path.read_bytes(), b"another admin's new config")

    def test_backup_tampering_blocks_rollback(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches():
                run, _ = subject.apply(machine.pre)
                (run / "0.before").write_bytes(b"tampered")
                with self.assertRaisesRegex(subject.RepairError, "BACKUP_CHANGED"):
                    subject.rollback(run)

    def test_copy_failure_never_changes_config_or_starts_service(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches(), patch.object(subject, "tree_snapshot", return_value={}):
                with self.assertRaisesRegex(subject.RepairError, "COPY_HASH"):
                    subject.apply(machine.pre)
                self.assertEqual((machine.repo / "backend/.env").read_bytes(), machine.original_env)
                self.assertFalse(any(args[:2] == ["systemctl", "start"] for args in machine.calls))

    def test_arbitrary_journal_target_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            machine = FakeMachine(Path(name))
            with machine.patches():
                run, journal = subject.apply(machine.pre)
                journal["files"][0]["target"] = str(Path(name) / "outside")
                with self.assertRaisesRegex(subject.RepairError, "JOURNAL_TARGETS"):
                    subject.validate_journal(run, journal)


class CliTests(unittest.TestCase):
    def test_default_preflight_does_not_acquire_lock_write_or_apply(self):
        with patch.object(subject.sys, "platform", "linux"), patch.object(subject.os, "geteuid", return_value=0, create=True), \
                patch.object(subject.os, "umask"), patch.object(subject, "maintenance_lock") as lock, \
                patch.object(subject, "preflight", return_value={"status": "PREFLIGHT_PASS_ONLY"}) as preflight, \
                patch.object(subject, "apply") as apply, redirect_stdout(io.StringIO()):
            self.assertEqual(subject.main(["--backup", "/backup"]), 0)
            preflight.assert_called_once()
            lock.assert_not_called()
            apply.assert_not_called()

    def test_apply_needs_both_explicit_confirmations(self):
        with patch.object(subject.sys, "platform", "linux"), patch.object(subject.os, "geteuid", return_value=0, create=True), \
                patch.object(subject.os, "umask"), patch.object(subject, "preflight") as preflight, \
                patch.object(subject.sys, "stderr", new=io.StringIO()):
            for flags in ([], ["--maintenance-confirmed"], ["--pause-background-writers"]):
                self.assertEqual(subject.main(["--apply", "--backup", "/backup", *flags]), 1)
            preflight.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
