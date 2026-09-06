#!/usr/bin/env python3
"""Maintenance-only routing repair. Default: read-only preflight, NOT a cutover.

Preserves both original Chroma directories. --apply copies the current MCP store,
installs reversible routing overrides and validates one loopback Chroma owner.
No ingestion/merge/re-embedding, package installation, or Nginx edits. See the
adjacent vm_chroma_routing_runbook.md before use. Requires exclusive maintenance.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time

BASELINE = "551e475280c36f8d9f4014d16d235454885db39a"
SERVICES = ("aem-backend.service", "chroma.service")
SERVICE_HOOKS = ("ExecStartPre", "ExecStartPost", "ExecStop", "ExecStopPost", "ExecCondition")
DROP_NAME = "90-uac-chroma-routing.conf"
ROUTING = {"CHROMA_HOST": "127.0.0.1", "CHROMA_PORT": "8000", "CHROMA_SSL": "false"}
WRITERS = (
    "LEARNED_QA_AUTO_SYNC_ON_STARTUP", "JIRA_INDEXING_ENABLED",
    "JIRA_INDEXING_BOOTSTRAP_ON_STARTUP", "JIRA_INDEXING_SCHEDULE_ENABLED",
    "JIRA_QA_RAG_BOOTSTRAP_ON_STARTUP", "DITA_SPEC_INDEX_ENABLED",
    "DITA_SPEC_INDEX_ON_STARTUP", "AEM_DOCS_CRAWL_ENABLED", "DITA_PDF_INDEX_ENABLED",
    "EVIDENCE_GRAPH_SYNC_ENABLED", "EVIDENCE_GRAPH_RECONCILE_ENABLED",
    "CLEANUP_ENABLED", "SHARED_UAC_LEARNING_WORKER_ENABLED",
)
CONTRACT_FILES = ("backend/app/main.py", "backend/app/services/vector_store_service.py")
PREFIX = "aem-chroma-routing-"
STATE_ROOT = Path("/app/storage")
SYSTEMD_ROOT = Path("/etc/systemd/system")
MARKER = "# UAC CHROMA ROUTING MAINTENANCE (see private journal)"


class RepairError(RuntimeError):
    """Only fixed, redacted diagnostic codes are raised to the console."""


def require(condition, code):
    if not condition:
        raise RepairError(code)


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode() + b"\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def bounded(path, limit=4 * 1024 * 1024):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    require(len(data) <= limit, "CONFIG_OR_REPORT_TOO_LARGE")
    return data


def safe_path(path, *, exists=True):
    path = Path(path)
    require(path.is_absolute() and re.fullmatch(r"/[A-Za-z0-9_./-]+", str(path)), "UNSAFE_PATH")
    require(".." not in path.parts and path != Path("/"), "UNSAFE_PATH")
    require(path.resolve(strict=exists) == path, "SYMLINK_OR_REDIRECTED_PATH")
    for parent in (path, *path.parents):
        if parent.exists():
            info = parent.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not info.st_mode & 0o022, "PATH_WRITABLE_BY_OTHERS")
            require(info.st_uid == 0, "PATH_NOT_ROOT_OWNED")
    return path


def sibling(name):
    """Load only a fixed adjacent, reviewed helper; no cwd/sys.path injection."""
    require(name in {"export_runtime_copies", "vm_chroma_routing_checks"}, "BAD_HELPER")
    path = Path(__file__).resolve().with_name(name + ".py")
    spec = importlib.util.spec_from_file_location("_routing_" + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def command(args, *, timeout=30, allow=(0,)):
    """No shell, no ambient proxy/Python injection, no raw subprocess output logs."""
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=False,
                            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8"})
    require(result.returncode in allow, "COMMAND_FAILED_" + Path(args[0]).name.upper().replace("-", "_"))
    require(len(result.stdout) <= 8 * 1024 * 1024 and len(result.stderr) <= 8 * 1024 * 1024,
            "COMMAND_OUTPUT_TOO_LARGE")
    return result


@contextmanager
def maintenance_lock():
    import fcntl  # Linux only; importing this module for portable tests stays safe.
    path = Path("/run/lock/aem-chroma-routing.lock")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(descriptor)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                and not info.st_mode & 0o077, "UNSAFE_MAINTENANCE_LOCK")
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RepairError("OTHER_ROUTING_OPERATION_RUNNING") from None
        yield
    finally:
        os.close(descriptor)  # Preserve lock inode so concurrent callers cannot bypass it.


def systemd_info(service):
    fields = ("LoadState", "ActiveState", "SubState", "MainPID", "User", "DynamicUser",
              "WorkingDirectory", "ExecStart", *SERVICE_HOOKS, "ReadOnlyPaths", "ReadWritePaths",
              "RootDirectory", "RootImage", "BindPaths", "BindReadOnlyPaths", "TemporaryFileSystem",
              "Environment", "EnvironmentFiles", "FragmentPath", "DropInPaths")
    raw = command(["systemctl", "show", service, "--no-pager", *["--property=" + f for f in fields]]).stdout
    return dict(line.split("=", 1) for line in raw.decode().splitlines() if "=" in line)


def exec_start(value):
    match = re.fullmatch(r"\{ path=([^ ;{}]+) ; argv\[\]=([^{}\r\n]*?) ; ignore_errors=no ; [^{}]* \}", value)
    require(match is not None, "UNSUPPORTED_EXECSTART_FORMAT")
    return match[1], shlex.split(match[2])


def supported_service(info):
    require(info.get("User", "") in {"", "root", "0"} and info.get("DynamicUser") == "no", "SERVICE_IDENTITY_NEEDS_REVIEW")
    require(not any(info.get(f) for f in SERVICE_HOOKS), "CUSTOM_SERVICE_HOOKS_NEED_REVIEW")
    require(not any(info.get(f) for f in ("ReadWritePaths", "RootDirectory", "RootImage", "BindPaths",
                                        "BindReadOnlyPaths", "TemporaryFileSystem")), "CUSTOM_SERVICE_MOUNTS_NEED_REVIEW")


def chroma_command(run, launcher):
    return ["/usr/bin/env", "-i", "PATH=/usr/bin:/bin", "ANONYMIZED_TELEMETRY=False", str(launcher),
            "run", "--host", "127.0.0.1", "--port", "8000", "--path", str(run / "chroma_db")]


def verify_effective_units(run, pre):
    """Check merged systemd settings before starting anything, not just our file."""
    for service in SERVICES:
        info = systemd_info(service)
        supported_service(info)
        protected = set(shlex.split(info.get("ReadOnlyPaths", "")))
        require(set(pre["originals"].values()) <= protected, "ORIGINAL_PROTECTION_OVERRIDDEN")
        actual = exec_start(info.get("ExecStart", ""))
        if service == "chroma.service":
            require(actual == ("/usr/bin/env", chroma_command(run, pre["launcher"]))
                    and info.get("WorkingDirectory") == str(run), "CHROMA_LAUNCH_OVERRIDDEN")
        else:
            require(actual == tuple_backend_command(Path(pre["repo"])), "BACKEND_LAUNCH_OVERRIDDEN")


def tuple_backend_command(repo):
    executable = (repo / "backend/venv/bin/uvicorn").as_posix()
    return executable, [executable, "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]


def require_stopped():
    for service in SERVICES:
        info = systemd_info(service)
        require(info.get("LoadState") == "loaded", "SERVICE_NOT_LOADED")
        require(info.get("ActiveState") == "inactive" and info.get("SubState") == "dead"
                and info.get("MainPID") == "0", "BOTH_SERVICES_MUST_BE_STOPPED")


def no_open_files(path):
    result = command(["lsof", "-nP", "-t", "+D", str(path)], timeout=120, allow=(0, 1))
    require(result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip(),
            "STORE_OPEN_OR_LSOF_INCONCLUSIVE")


def tree_snapshot(path):
    """Cold ordinary-file hashing only: no SQLite/Chroma opens on original stores."""
    rows = {}
    for item in sorted((path, *path.rglob("*"))):
        info = item.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1,
                "STORE_LINK_OR_SPECIAL_FILE")
        key = item.relative_to(path).as_posix()
        rows[key] = {"mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}
        if item.is_file():
            rows[key].update(size=info.st_size, sha256=file_hash(item))
    require("chroma.sqlite3" in rows, "STORE_SQLITE_MISSING")
    return rows


def validated_archives(backup, originals):
    checksums = {}
    for line in bounded(backup / "SHA256SUMS").decode("ascii").splitlines():
        match = re.fullmatch(r"([a-fA-F0-9]{64}) [ *](app-storage\.tar|backend-storage\.tar)", line)
        require(match is not None and match[2] not in checksums, "INVALID_BACKUP_MANIFEST")
        checksums[match[2]] = match[1].lower()
    require(set(checksums) == {"app-storage.tar", "backend-storage.tar"}, "BACKUP_INCOMPLETE")
    for label, original in originals.items():
        archive = safe_path(backup / (label + ".tar"))
        require(archive.is_file() and archive.stat().st_nlink == 1, "INVALID_ARCHIVE")
        require(file_hash(archive) == checksums[archive.name], "BACKUP_HASH_MISMATCH")
        with tarfile.open(archive, "r:") as stream:
            names = set()
            for member in stream:
                parts = Path(member.name).parts
                name = Path(member.name).as_posix()
                require(parts and parts[0] == "chroma_db" and ".." not in parts
                        and (member.isfile() or member.isdir()) and name not in names,
                        "UNSAFE_BACKUP_MEMBER")
                names.add(name)
            require("chroma_db/chroma.sqlite3" in names, "BACKUP_SQLITE_MISSING")
            current_names = {"chroma_db", *["chroma_db/" + p.relative_to(original).as_posix() for p in original.rglob("*")]}
            require(names == current_names, "BACKUP_MEMBER_SET_MISMATCH")
        command(["tar", "--compare", "--file", str(archive), "--directory", str(original.parent)], timeout=1800)
    return checksums


def append_settings(original, settings):
    require(MARKER.encode() not in original, "PRIOR_ROUTING_OVERRIDE_EXISTS")
    original.decode("utf-8-sig")  # Fail on bad encoding; never replace bytes silently.
    suffix = MARKER + "\n" + "\n".join(k + "=" + v for k, v in settings.items()) + "\n"
    return original + (b"\n" if original and not original.endswith(b"\n") else b"") + suffix.encode()


def check_conflicting_scope(text, *, docker=False):
    for line in text.splitlines():
        value = line.strip()
        if not value or value.startswith("#") or "=" not in value:
            continue
        key, raw = value.removeprefix("export ").split("=", 1)
        key, raw = key.strip(), raw.strip()
        if not docker:
            raw = raw.split(" #", 1)[0].strip().strip("\"'")
        if key in {"CHROMA_TENANT", "CHROMA_DATABASE"}:
            require(raw in {"", "default_tenant" if key.endswith("TENANT") else "default_database"},
                    "CUSTOM_CHROMA_SCOPE_REQUIRES_SEPARATE_AUDIT")
        if key.startswith("CHROMA_") and ("AUTH" in key or "TOKEN" in key or "CREDENTIAL" in key):
            require(not raw, "CHROMA_AUTH_CONFIG_REQUIRES_SEPARATE_AUDIT")


def free_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            raise RepairError("PORT_NOT_FREE") from None


def preflight(repo, backup):
    require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
    repo, backup = safe_path(repo), safe_path(backup)
    originals = {"app-storage": safe_path(Path("/app/storage/chroma_db")),
                 "backend-storage": safe_path(repo / "backend/storage/chroma_db")}
    require(not originals["app-storage"].samefile(originals["backend-storage"]), "ORIGINALS_NOT_DISTINCT")
    require_stopped()
    for path in originals.values():
        no_open_files(path)
    for port in (8000, 8001):
        free_port(port)
    command(["nginx", "-t"])
    for relative in CONTRACT_FILES:
        expected = command(["git", "-C", str(repo), "show", BASELINE + ":" + relative]).stdout
        require(bounded(safe_path(repo / relative)).replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n"),
                "RUNTIME_CONTRACT_CHANGED_NEEDS_REVIEW")
    python = repo / "backend/venv/bin/python"
    launcher = safe_path(repo / "backend/venv/bin/chroma")
    require(python.exists() and launcher.is_file(), "REVIEWED_VENV_MISSING")
    probe = command([str(python), "-I", "-B", "-c",
                     "import sys,json,importlib.metadata as m; print(json.dumps({'prefix':sys.prefix,'chroma':m.version('chromadb')}))"])
    runtime = json.loads(probe.stdout)
    require(runtime == {"prefix": str(repo / "backend/venv"), "chroma": "1.5.9"}, "VENV_OR_CHROMA_VERSION_CHANGED")
    launch_text = bounded(launcher, 16384).decode()
    first = launch_text.splitlines()[0]
    require(first.startswith("#!"), "CUSTOM_CHROMA_LAUNCHER")
    interpreter = Path(first[2:])
    require(interpreter.parent == python.parent and interpreter.exists() and interpreter.samefile(python)
            and "from chromadb.cli.cli import app" in launch_text, "CUSTOM_CHROMA_LAUNCHER")
    for service in SERVICES:
        info = systemd_info(service)
        supported_service(info)
        check_conflicting_scope("\n".join(shlex.split(info.get("Environment", ""))))
        # Env files could silently change service auth/writers. This maintenance helper
        # supports plain env files only; unsupported systemd quoting/specifiers stop it.
        env_files = info.get("EnvironmentFiles", "")
        if env_files:
            for item in re.findall(r"(/[A-Za-z0-9_./-]+) \(ignore_errors=(?:yes|no)\)", env_files):
                check_conflicting_scope(bounded(safe_path(Path(item))).decode("utf-8-sig"))
            require(re.sub(r"(/[A-Za-z0-9_./-]+) \(ignore_errors=(?:yes|no)\)", "", env_files).strip() == "",
                    "COMPLEX_ENVIRONMENT_FILES_NEED_REVIEW")
        if service == SERVICES[0]:
            require(info.get("WorkingDirectory") == str(repo / "backend")
                    and exec_start(info.get("ExecStart", "")) == tuple_backend_command(repo),
                    "BACKEND_LAUNCH_CONTRACT_CHANGED")
        require(not (SYSTEMD_ROOT / (service + ".d") / DROP_NAME).exists(), "PRIOR_DROPIN_EXISTS")
    for relative in (".env", "backend/.env", "backend/.env.docker"):
        path = safe_path(repo / relative, exists=False)
        if path.exists():
            require(path.is_file() and path.stat().st_nlink == 1, "CONFIG_NOT_PRIVATE_REGULAR_FILE")
            check_conflicting_scope(bounded(path).decode("utf-8-sig"), docker=relative.endswith(".docker"))
            require(MARKER.encode() not in bounded(path), "PRIOR_ROUTING_OVERRIDE_EXISTS")
    print("Checking cold archives and original store hashes...", flush=True)
    archives = validated_archives(backup, originals)
    snapshots = {label: tree_snapshot(path) for label, path in originals.items()}
    size = sum(row.get("size", 0) for row in snapshots["app-storage"].values())
    require(shutil.disk_usage("/app/storage").free >= size * 2 + 1024**3, "INSUFFICIENT_FREE_SPACE")
    require_stopped()
    for path in originals.values():
        no_open_files(path)
    return {"status": "PREFLIGHT_PASS_ONLY", "repo": str(repo), "backup": str(backup),
            "archives": archives, "originals": {k: str(v) for k, v in originals.items()},
            "original_snapshots": snapshots, "launcher": str(launcher),
            "automatic_writers_to_pause": list(WRITERS), "backend_contract_baseline": BASELINE}


def atomic_write(path, data, *, mode=0o600, owner=None, absent=False):
    descriptor, name = tempfile.mkstemp(prefix=".uac-routing-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        if owner is not None:
            os.chown(temporary, *owner)
        if absent:
            os.link(temporary, path)  # Exclusive publication; never overwrite a raced-in file.
        else:
            os.replace(temporary, path)
        if sys.platform == "linux":
            fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def journal_save(run, journal):
    atomic_write(run / "journal.json", encoded(journal))


def planned_file(run, target, data, number, expected_before):
    target = safe_path(target, exists=False)
    previous = bounded(target) if target.exists() else None
    require(previous == expected_before, "CONFIG_CHANGED_DURING_PLANNING")
    row = {"target": str(target), "before": None, "after": digest(data), "backup": str(number) + ".before"}
    if previous is not None:
        info = target.stat()
        require(target.is_file() and info.st_nlink == 1, "MANAGED_FILE_NOT_REGULAR")
        row.update(before=digest(previous), mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)
        atomic_write(run / row["backup"], previous, absent=True)
    else:
        row.update(mode=0o600, uid=0, gid=0)
    atomic_write(run / (str(number) + ".after"), data, absent=True)
    row["payload"] = str(number) + ".after"
    return row


def managed_paths(repo):
    return {str(repo / "backend/.env"), str(repo / "backend/.env.docker"),
            *[str(SYSTEMD_ROOT / (s + ".d") / DROP_NAME) for s in SERVICES]}


def validate_journal(run, journal):
    require(journal.get("schema") == "vm-chroma-routing-v1", "INVALID_JOURNAL")
    repo = safe_path(Path(journal["repo"]))
    require(run.parent == STATE_ROOT and run.name.startswith(PREFIX), "INVALID_RUN_DIRECTORY")
    rows = journal.get("files", [])
    require(len(rows) == 4 and {r.get("target") for r in rows} == managed_paths(repo), "INVALID_JOURNAL_TARGETS")
    for i, row in enumerate(rows):
        require(row["backup"] == str(i) + ".before" and row["payload"] == str(i) + ".after", "INVALID_BACKUP_PATH")
        require(file_hash(safe_path(run / row["payload"])) == row["after"], "JOURNAL_PAYLOAD_CHANGED")
        if row["before"] is not None:
            require(file_hash(safe_path(run / row["backup"])) == row["before"], "CONFIG_BACKUP_CHANGED")
        target = safe_path(Path(row["target"]), exists=False)
        if target.exists():
            info = target.stat()
            require(target.is_file() and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == row["mode"]
                    and (info.st_uid, info.st_gid) == (row["uid"], row["gid"]), "CONFIG_METADATA_DRIFT")
        actual = file_hash(target) if target.exists() else None
        require(actual in (row["before"], row["after"]), "CONFIG_DRIFT_ROLLBACK_REFUSED")
    return rows


def restore_files(run, rows):
    for row in reversed(rows):
        path = Path(row["target"])
        actual = file_hash(path) if path.exists() else None
        require(actual in (row["before"], row["after"]), "CONFIG_DRIFT_ROLLBACK_REFUSED")
        if actual == row["before"]:
            continue
        if row["before"] is None:
            # Only this exact, hash-verified script-created config is removed.
            path.unlink()
        else:
            atomic_write(path, bounded(run / row["backup"]), mode=row["mode"], owner=(row["uid"], row["gid"]))


def rollback(run):
    run = safe_path(run)
    journal = json.loads(bounded(run / "journal.json", 32 * 1024 * 1024))
    rows = validate_journal(run, journal)
    if journal.get("state") == "ROLLED_BACK_SERVICES_STOPPED":
        require_stopped()
        return journal
    for service in SERVICES:
        command(["systemctl", "stop", service], timeout=120)
    require_stopped()
    restore_files(run, rows)
    command(["systemctl", "daemon-reload"])
    journal["state"] = "ROLLED_BACK_SERVICES_STOPPED"
    journal["background_writers_paused"] = False  # Previous config restored; services remain stopped.
    journal_save(run, journal)
    return journal


def dropins(run, launcher, originals):
    protected = " ".join(originals.values())
    backend = ("[Unit]\nAfter=chroma.service\nRequires=chroma.service\n[Service]\n"
               + "ReadOnlyPaths=" + protected + "\n")
    chroma = ("[Service]\nExecStart=\nExecStart=" + " ".join(chroma_command(run, launcher)) + "\nWorkingDirectory=" + str(run)
              + "\nReadOnlyPaths=" + protected + "\nUMask=0077\nNoNewPrivileges=true\n")
    return backend.encode(), chroma.encode()


def wait_running(service, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        info = systemd_info(service)
        if info.get("ActiveState") == "active" and int(info.get("MainPID", "0")) > 0:
            return int(info["MainPID"])
        require(info.get("ActiveState") != "failed", "SERVICE_START_FAILED")
        time.sleep(1)
    raise RepairError("SERVICE_START_TIMEOUT")


def verify_owner(run):
    pid = wait_running("chroma.service", seconds=5)
    process = Path("/proc") / str(pid)
    require("/chroma.service" in bounded(process / "cgroup").decode(), "CHROMA_CGROUP_MISMATCH")
    cmdline = bounded(process / "cmdline").split(b"\0")
    require(str(run / "chroma_db").encode() in cmdline and b"127.0.0.1" in cmdline, "CHROMA_PROCESS_TARGET_MISMATCH")
    result = command(["lsof", "-nP", "-t", "+D", str(run / "chroma_db")], timeout=120)
    require(set(result.stdout.decode().split()) == {str(pid)} and not result.stderr.strip(), "CHROMA_NOT_SOLE_STORE_OWNER")
    listeners = []
    for filename in ("tcp", "tcp6"):
        for line in bounded(Path("/proc/net") / filename).decode().splitlines()[1:]:
            fields = line.split()
            if fields[3] == "0A" and fields[1].endswith(":1F40"):
                listeners.append((fields[1], fields[9]))
    require(len(listeners) == 1 and listeners[0][0] == "0100007F:1F40", "CHROMA_LISTENER_NOT_EXCLUSIVE_LOOPBACK")
    links = []
    for fd in (process / "fd").iterdir():
        try:
            links.append(os.readlink(fd))
        except FileNotFoundError:
            pass
    require("socket:[" + listeners[0][1] + "]" in links, "CHROMA_PORT_OWNED_BY_OTHER_PROCESS")
    require(str(run / "chroma_db/chroma.sqlite3") in links, "CHROMA_COPY_FD_NOT_PROVEN")
    return {"single_owner_pid": pid, "loopback_listener_owned": True, "copy_sqlite_fd_proven": True}


def apply(pre, token=""):
    require_stopped()
    run = Path(tempfile.mkdtemp(prefix=PREFIX, dir=STATE_ROOT))
    print("ROUTING_RUN_DIR=" + str(run), flush=True)
    journal = {"schema": "vm-chroma-routing-v1", "state": "COPYING", "repo": pre["repo"], "files": [],
               "preflight": pre, "background_writers_paused": True, "merge_performed": False}
    journal_save(run, journal)
    installed = False
    try:
        print("Copying the cold MCP store; original stores are not opened by Chroma...", flush=True)
        source = Path(pre["originals"]["app-storage"])
        command(["cp", "-a", "--reflink=never", "--", str(source), str(run / "chroma_db")], timeout=1800)
        require(tree_snapshot(run / "chroma_db") == pre["original_snapshots"]["app-storage"], "FRESH_COPY_HASH_MISMATCH")
        for label, original in pre["originals"].items():
            no_open_files(Path(original))
            require(tree_snapshot(Path(original)) == pre["original_snapshots"][label], "ORIGINAL_CHANGED")
        snapshots = sibling("export_runtime_copies")
        before = snapshots.snapshot(run / "chroma_db/chroma.sqlite3")
        # The reviewed flag-based 1.5.9 CLI uses the default legacy MD5 migration
        # validation convention. This is not a security digest or a new migration.
        require(before["hash_algorithm"] == "md5", "NONDEFAULT_MIGRATION_HASH_REQUIRES_REVIEW")
        expected = {name: {"id": row["id"], "count": len(row["ids"])} for name, row in before["catalog"].items()}
        journal["expected_collections"] = expected
        journal["copied_sql_snapshot_sha256"] = snapshots.signature(before)
        repo = Path(pre["repo"])
        settings = {**ROUTING, **{name: "false" for name in WRITERS}}
        files = []
        for relative in ("backend/.env", "backend/.env.docker"):
            target = repo / relative
            original = bounded(target) if target.exists() else None
            files.append((target, append_settings(original or b"", settings), original))
        for service, data in zip(SERVICES, dropins(run, pre["launcher"], pre["originals"])):
            parent = safe_path(SYSTEMD_ROOT / (service + ".d"), exists=False)
            parent.mkdir(mode=0o755, exist_ok=True)
            files.append((parent / DROP_NAME, data, None))
        journal["files"] = [planned_file(run, target, data, i, original) for i, (target, data, original) in enumerate(files)]
        journal["state"] = "PREPARED"
        journal_save(run, journal)  # Durable recovery point BEFORE any config replacement.
        require_stopped()
        validate_journal(run, journal)
        installed = True
        for row in journal["files"]:
            target = Path(row["target"])
            actual = file_hash(target) if target.exists() else None
            require(actual == row["before"], "CONFIG_CHANGED_BEFORE_INSTALL")
            atomic_write(target, bounded(run / row["payload"]), mode=row["mode"],
                         owner=(row["uid"], row["gid"]), absent=row["before"] is None)
        journal["state"] = "CONFIGURED"
        journal_save(run, journal)
        command(["systemctl", "daemon-reload"])
        verify_effective_units(run, pre)
        command(["systemctl", "start", "chroma.service"], timeout=120)
        checks = sibling("vm_chroma_routing_checks")
        wait_running("chroma.service")
        print("Checking shared-server inventory before starting the backend...", flush=True)
        # Wait for HTTP readiness, not CLI's unreliable exit/version string.
        deadline = time.monotonic() + 60
        while True:
            try:
                checks.http_json(8000, "GET", "/api/v2/heartbeat")
                break
            except checks.RoutingCheckError:
                require(time.monotonic() < deadline, "CHROMA_HTTP_START_TIMEOUT")
                time.sleep(1)
        journal["direct_inventory"] = checks.inspect_inventory(8000, expected)
        journal["nginx_inventory"] = checks.inspect_inventory(4502, expected)
        journal["ownership"] = verify_owner(run)
        journal["vector_smoke"] = checks.smoke_vector_queries(expected)
        print("Starting backend with background writers paused; verifying MCP identity...", flush=True)
        verify_effective_units(run, pre)
        command(["systemctl", "start", "aem-backend.service"], timeout=120)
        wait_running("aem-backend.service")
        deadline = time.monotonic() + 120
        while True:
            try:
                journal["backend_parity"] = checks.verify_backend(expected, token=token)
                break
            except checks.RoutingCheckError:
                require(time.monotonic() < deadline, "BACKEND_PARITY_NOT_CONFIRMED")
                time.sleep(2)
        journal["direct_inventory"] = checks.inspect_inventory(8000, expected)
        journal["nginx_inventory"] = checks.inspect_inventory(4502, expected)
        journal["ownership"] = verify_owner(run)
        for label, original in pre["originals"].items():
            no_open_files(Path(original))
            require(tree_snapshot(Path(original)) == pre["original_snapshots"][label], "ORIGINAL_CHANGED")
        # No live SQLite read: this proves cold-copy equivalence and live routing,
        # inventory and sample queries, not full post-start payload equality.
        journal["full_live_payload_equality_verified"] = False
        journal["embedding_model_parity_proven"] = False
        journal["original_bytes_unchanged"] = True
        journal["state"] = "PASS_ROUTING_ONLY_WRITERS_PAUSED"
        journal_save(run, journal)
        return run, journal
    except BaseException:
        # SIGKILL/power loss cannot execute this: use persisted --rollback RUN_DIR.
        if installed:
            try:
                for service in SERVICES:
                    command(["systemctl", "stop", service], timeout=120)
                rollback(run)
                print("Rollback complete: previous configs restored; both services left stopped.", flush=True)
            except Exception:
                print("ROLLBACK_NEEDS_ATTENTION: preserve run directory; inspect config drift before restarting.", flush=True)
        else:
            journal["state"] = "FAILED_BEFORE_CONFIG_CHANGES"
            journal_save(run, journal)
        raise


def report(journal):
    return {"status": journal["state"], "collections": journal.get("expected_collections"),
            "background_writers_paused": journal.get("background_writers_paused"),
            "original_bytes_unchanged": journal.get("original_bytes_unchanged", False),
            "merge_performed": False, "import_authorized": False,
            "full_live_payload_equality_verified": False, "embedding_model_parity_proven": False,
            "next_step": "Share this redacted report. Do not import or resume writers yet."}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/root/aem-guides-dataset-studio"))
    parser.add_argument("--backup", type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", type=Path)
    parser.add_argument("--maintenance-confirmed", action="store_true", help="No team/API/direct writers during cutover")
    parser.add_argument("--pause-background-writers", action="store_true", help="Keep automatic writer jobs disabled until reviewed")
    args = parser.parse_args(argv)
    os.umask(0o077)
    try:
        require(sys.platform == "linux" and os.geteuid() == 0, "LINUX_ROOT_REQUIRED")
        if args.rollback:
            require(args.maintenance_confirmed, "ROLLBACK_REQUIRES_MAINTENANCE_CONFIRMATION")
            with maintenance_lock():
                value = rollback(args.rollback)
            print(json.dumps(report(value), indent=2))
            return 0
        require(args.backup is not None, "VERIFIED_BACKUP_DIRECTORY_REQUIRED")
        if args.apply:
            require(args.maintenance_confirmed and args.pause_background_writers,
                    "APPLY_REQUIRES_MAINTENANCE_AND_WRITER_PAUSE_CONFIRMATIONS")
        if not args.apply:
            pre = preflight(args.repo, args.backup)
            print(json.dumps({k: v for k, v in pre.items() if k != "original_snapshots"}, indent=2))
            print("PREFLIGHT ONLY: no files, service state, or configuration changed.")
            return 0
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        with maintenance_lock():
            pre = preflight(args.repo, args.backup)
            run, value = apply(pre, os.environ.get("AEM_STUDIO_TOKEN", ""))
        print(json.dumps(report(value), indent=2))
        print("ROUTING_RUN_DIR=" + str(run))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        code = str(error) if isinstance(error, RepairError) else getattr(error, "code", type(error).__name__)
        print("STOP: " + code + ". No merge or import performed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
