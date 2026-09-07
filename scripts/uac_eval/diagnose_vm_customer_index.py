#!/usr/bin/env python3
"""Standalone VM diagnosis; no imports, repairs, service restarts or Chroma writes.

Uses Python's standard library only. Reads systemd/proc and allowlisted config
hints, and calls existing loopback status/count APIs. Never loads backend Python
or opens SQLite/Chroma storage. The only local write is a private redacted report.
Existing status APIs may lazily initialize their own caches; this script does not
request ingestion, enrichment, reindexing or configuration changes.

Run on the VM: sudo python3 diagnose_vm_customer_index.py
Tests anywhere: python3 diagnose_vm_customer_index.py --self-test
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

MAX_BYTES = 1024 * 1024
KEYS = frozenset({
    "STORAGE_PATH", "CHROMA_HOST", "CHROMA_PORT", "CHROMA_SSL",
    "DITA_EMBEDDING_MODEL", "DITA_EMBEDDING_MODEL_PATH", "USE_AZURE_EMBEDDING",
    "EVIDENCE_GRAPH_ENABLED", "EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED", "DATABASE_URL",
})
BOOL_KEYS = frozenset({"CHROMA_SSL", "USE_AZURE_EMBEDDING", "EVIDENCE_GRAPH_ENABLED",
                       "EVIDENCE_GRAPH_EVENT_CAPTURE_ENABLED"})
CHROMA_PREFIX = "/api/v2/tenants/default_tenant/databases/default_database/collections/"
UUID = r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
MCP_REQUEST = {"jsonrpc": "2.0", "id": "customer-index-diagnostic", "method": "tools/call",
               "params": {"name": "check_rag_status", "arguments": {}}}


def bounded_read(path, limit=MAX_BYTES):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("INPUT_TOO_LARGE")
    return data


def safe_path(value):
    text = str(value)
    if len(text) > 512 or re.search(r"[\x00-\x1f\x7f@?=]", text) or "://" in text:
        return "[REDACTED_NON_SIMPLE_PATH]"
    return text


def safe_value(key, value):
    value = str(value).strip()
    if key not in KEYS:
        raise ValueError("NON_ALLOWLISTED_CONFIG")
    if not value:
        return "UNSET_OR_EMPTY"
    if key == "DATABASE_URL":
        kind = value.split(":", 1)[0].split("+", 1)[0].lower()
        return {"kind": kind if kind in {"sqlite", "postgres", "postgresql", "mysql"} else "OTHER",
                "connection_details": "REDACTED"}
    if "$" in value or "\n" in value or "\r" in value:
        return "UNRESOLVED_OR_NON_SIMPLE"
    if key in BOOL_KEYS:
        return value.lower() if value.lower() in {"1", "0", "true", "false", "yes", "no", "on", "off"} else "INVALID_BOOLEAN"
    if key == "CHROMA_PORT":
        return int(value) if value.isdigit() and 1 <= int(value) <= 65535 else "INVALID_PORT"
    if key == "CHROMA_HOST":
        return value if re.fullmatch(r"[A-Za-z0-9.-]{1,253}", value) else "[REDACTED_NON_SIMPLE_HOST]"
    return safe_path(value)


def config_hints(text, *, docker=False):
    """Not a dotenv replacement: ambiguous/interpolated values stay unresolved."""
    values = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if not docker and line.startswith("export "):
            line = line[7:]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if key not in KEYS:
            continue
        if not docker:
            if value[:1] in {"'", '"'}:
                quote = value[0]
                if len(value) < 2 or not value.endswith(quote):
                    values[key] = "UNRESOLVED_OR_NON_SIMPLE"
                    continue
                value = value[1:-1]
            else:
                value = value.split(" #", 1)[0].strip()
        values[key] = safe_value(key, value)
    return values


def command(args):
    try:
        result = subprocess.run(args, shell=False, capture_output=True, timeout=8,
                                check=False, env={**os.environ, "LC_ALL": "C", "GIT_OPTIONAL_LOCKS": "0"})
        if result.returncode != 0:
            return None
        if len(result.stdout) > MAX_BYTES:
            return None
        return result.stdout.decode("utf-8", errors="replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def chroma_command_options(argv):
    """Expose only recognised Chroma listener/storage options, never full argv."""
    if not any(Path(item).name in {"chroma", "chroma.exe"} or
               item in {"chromadb", "chromadb.cli", "chromadb.cli.cli"} for item in argv[:4]):
        return {}
    options = {}
    for index, item in enumerate(argv[:256]):
        option, separator, value = item.partition("=")
        if option not in {"--path", "--host", "--port"}:
            continue
        if not separator:
            value = argv[index + 1] if index + 1 < len(argv) else ""
            if value.startswith("--"):
                value = ""
        key = {"--path": "STORAGE_PATH", "--host": "CHROMA_HOST", "--port": "CHROMA_PORT"}[option]
        options.setdefault(option, []).append(safe_value(key, value))
    return options


def process_info(pid, proc_root=Path("/proc")):
    base = Path(proc_root) / str(pid)
    result = {"pid": pid}
    for field, leaf in (("executable", "exe"), ("cwd", "cwd")):
        try:
            result[field] = safe_path(os.readlink(base / leaf))
        except OSError:
            result[field] = "UNAVAILABLE"
    try:
        argv = bounded_read(base / "cmdline").decode("utf-8", errors="replace").split("\0")
        # Arguments can include credentials. Show only launcher paths, never argv.
        result["launchers"] = [safe_path(item) for item in argv[:2]
                               if item.startswith("/") and re.fullmatch(r"(?:python(?:\d+(?:\.\d+)*)?|uvicorn|gunicorn|chroma)", Path(item).name)]
        result["chroma_command_options"] = chroma_command_options(argv)
    except (OSError, ValueError):
        result["launchers"] = []
        result["chroma_command_options"] = {}
    try:
        env = bounded_read(base / "environ", 2 * MAX_BYTES).decode("utf-8", errors="replace")
        pairs = [item.split("=", 1) for item in env.split("\0") if "=" in item]
        result["launch_environment_hints"] = {key: safe_value(key, value) for key, value in pairs if key in KEYS}
    except (OSError, ValueError):
        result["launch_environment_hints"] = "UNAVAILABLE"
    db_files = set()
    try:
        for index, fd in enumerate((base / "fd").iterdir()):
            if index >= 8192:
                result["fd_scan_truncated"] = True
                break
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if re.search(r"(?:^|/)chroma\.sqlite3(?:-wal|-shm)?(?: \(deleted\))?$", target):
                db_files.add(safe_path(target))
        result["open_chroma_sqlite_files"] = sorted(db_files)
    except OSError:
        result["open_chroma_sqlite_files"] = "UNAVAILABLE"
    return result


def service_info(name):
    info = {"name": name}
    for prop in ("ActiveState", "SubState", "MainPID", "WorkingDirectory"):
        value = command(["systemctl", "show", name, "--property=" + prop, "--value"])
        if prop == "MainPID":
            info[prop] = int(value) if value and value.isdigit() else None
        elif prop == "WorkingDirectory":
            info[prop] = safe_path(value) if value else "UNAVAILABLE"
        else:
            info[prop] = value if value and re.fullmatch(r"[a-z-]{1,40}", value) else "UNAVAILABLE"
    processes, queue, seen = [], [info.get("MainPID")], set()
    while queue and len(seen) < 32:
        pid = queue.pop(0)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        processes.append(process_info(pid))
        try:
            children = bounded_read(Path("/proc") / str(pid) / "task" / str(pid) / "children", 16384).decode("ascii")
            queue.extend(int(item) for item in children.split() if item.isdigit())
        except (OSError, ValueError):
            pass
    info["processes"] = processes
    info["process_scan_truncated"] = bool(queue)
    return info


def package_versions(repo, services):
    """Inspect installed metadata, without importing Chroma or executing a venv."""
    roots = [repo / "backend" / ".venv", repo / "backend" / "venv"]
    for service in services:
        for process in service.get("processes", []):
            for launcher in process.get("launchers", []):
                path = Path(launcher)
                if path.is_absolute() and path.parent.name in {"bin", "Scripts"}:
                    roots.append(path.parent.parent)
    results = []
    for root in list(dict.fromkeys(roots))[:12]:
        row = {"environment_candidate": safe_path(root), "evidence_type": "INSTALLED_METADATA_NOT_RUNTIME_VERSION",
               "packages": []}
        try:
            for pattern in ("lib/python*/site-packages/chromadb-*.dist-info/METADATA",
                            "lib64/python*/site-packages/chromadb-*.dist-info/METADATA",
                            "Lib/site-packages/chromadb-*.dist-info/METADATA"):
                for metadata in islice(root.glob(pattern), 33):
                    if len(row["packages"]) >= 32:
                        row["scan_truncated"] = True
                        break
                    entry = {"file": safe_path(metadata)}
                    try:
                        text = bounded_read(metadata, 128 * 1024).decode("utf-8").replace("\r\n", "\n")
                        name = re.search(r"^Name: ([^\r\n]+)$", text, re.MULTILINE)
                        version = re.search(r"^Version: ([^\r\n]+)$", text, re.MULTILINE)
                        if not name or name.group(1).casefold() != "chromadb":
                            entry["status"] = "PACKAGE_NAME_NOT_CONFIRMED"
                        elif not version or not re.fullmatch(r"[0-9][A-Za-z0-9.!+_-]{0,79}", version.group(1)):
                            entry["status"] = "VERSION_NOT_CONFIRMED"
                        else:
                            entry.update(status="OBSERVED", version=version.group(1))
                    except (OSError, UnicodeError, ValueError):
                        entry["status"] = "UNREADABLE_OR_TOO_LARGE"
                    if entry not in row["packages"]:
                        row["packages"].append(entry)
            row["status"] = "OBSERVED" if row["packages"] else "NO_METADATA_OBSERVED"
        except OSError:
            row["status"] = "UNAVAILABLE"
        results.append(row)
    return results


def sqlite_file_evidence(repo, services, config_files):
    """Stat-only path evidence: no SQLite connection or storage creation."""
    candidates = {str(repo / "backend" / "storage" / "chroma_db" / "chroma.sqlite3"): ["backend_default_candidate"]}

    def add(raw, reason, *, base=None):
        if not isinstance(raw, str) or not raw or safe_path(raw) != raw or raw.startswith("[") or "$" in raw:
            return
        path = Path(raw)
        if not path.is_absolute():
            if base is None or not Path(base).is_absolute() or safe_path(base) != str(base):
                return
            path = Path(base) / path
        candidates.setdefault(str(path), []).append(reason)

    for service in services:
        for process in service.get("processes", []):
            launch_hints = process.get("launch_environment_hints")
            raw_storage = launch_hints.get("STORAGE_PATH") if isinstance(launch_hints, dict) else None
            if isinstance(raw_storage, str) and raw_storage not in {"UNSET_OR_EMPTY", "UNRESOLVED_OR_NON_SIMPLE"}:
                # Launch environment can be overridden in Python. This is only a
                # candidate; relative paths use this checkout's backend contract.
                add(str(Path(raw_storage) / "chroma_db" / "chroma.sqlite3"),
                    "process_launch_environment_hint_candidate", base=repo / "backend")
            files = process.get("open_chroma_sqlite_files")
            if isinstance(files, list):
                for filename in files:
                    if not filename.endswith(" (deleted)"):
                        add(filename, "observed_process_fd")
            options = process.get("chroma_command_options", {})
            for value in options.get("--path", []):
                if isinstance(value, str) and value not in {"UNSET_OR_EMPTY", "UNRESOLVED_OR_NON_SIMPLE"}:
                    add(str(Path(value) / "chroma.sqlite3"), "chroma_cli_path_candidate", base=process.get("cwd"))
    for config in config_files:
        raw = config.get("allowlisted_hints", {}).get("STORAGE_PATH")
        if isinstance(raw, str) and raw not in {"UNSET_OR_EMPTY", "UNRESOLVED_OR_NON_SIMPLE"}:
            add(str(Path(raw) / "chroma_db" / "chroma.sqlite3"), "config_hint_candidate:" + config["file"], base=repo / "backend")
    results = []
    for filename, reasons in list(candidates.items())[:128]:
        row = {"path": safe_path(filename), "reasons": sorted(set(reasons)), "evidence_type": "FILE_STAT_ONLY_NOT_ACTIVE_STORE_PROOF"}
        try:
            info = Path(filename).stat()
            row.update(exists=True, regular_file=stat.S_ISREG(info.st_mode), size_bytes=info.st_size,
                       inode=info.st_ino, device=info.st_dev)
        except FileNotFoundError:
            row["exists"] = False
        except OSError:
            row.update(exists=None, status="UNAVAILABLE")
        results.append(row)
    return results


def http_json(port, method, path, body=None, token="", connection_factory=http.client.HTTPConnection):
    # Fixed VM-loopback targets are intentional: no external hosts, proxies,
    # redirects, TLS bypass, inherited admin keys, or token reuse for Chroma.
    allowed = method == "GET" and (
        path in {"/health", "/mcp/health", "/api/v2/heartbeat", "/api/v2/version", CHROMA_PREFIX + "jira_qa"}
        or re.fullmatch(re.escape(CHROMA_PREFIX) + UUID + r"/count", path))
    allowed = allowed or (method == "POST" and path == "/mcp" and body == MCP_REQUEST)
    if port not in {4502, 8001} or not allowed:
        raise ValueError("REQUEST_NOT_ALLOWLISTED")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token and path.startswith("/api/v2/"):
        raise ValueError("BACKEND_TOKEN_NOT_ALLOWED_FOR_CHROMA")
    if token:
        if len(token) > 8192 or re.search(r"[\x00-\x20\x7f]", token):
            raise ValueError("INVALID_AUTH_TOKEN")
        headers["Authorization"] = "Bearer " + token
    connection = connection_factory("127.0.0.1", port, timeout=8)
    try:
        connection.request(method, path, body=json.dumps(body).encode() if body is not None else None, headers=headers)
        response = connection.getresponse()
        status = response.status
        if status != 200:
            return {"http_status": status, "status": "HTTP_ERROR"}, None
        raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return {"http_status": status, "status": "RESPONSE_TOO_LARGE"}, None
        data = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NON_FINITE_JSON")))
        return {"http_status": status, "status": "OK"}, data
    except (OSError, ValueError, http.client.HTTPException):
        return {"status": "UNAVAILABLE_OR_INVALID_JSON"}, None
    finally:
        connection.close()


def count(value):
    return value if type(value) is int and value >= 0 else None


def index_identity(value):
    """Strictly copy the public identity schema; never echo arbitrary fields."""
    if not isinstance(value, dict) or value.get("schema_version") != "chroma-index-identity-v1":
        return None
    if value.get("status") not in {"OK", "PARTIAL", "UNAVAILABLE"} or value.get("mode") not in {"EMBEDDED", "REMOTE", "UNKNOWN"}:
        return None
    result = {"schema_version": value["schema_version"], "status": value["status"], "mode": value["mode"]}
    for key, pattern in (("target_fingerprint", r"[a-f0-9]{64}"),
                         ("tenant", r"[A-Za-z0-9_.-]{1,128}"), ("database", r"[A-Za-z0-9_.-]{1,128}"),
                         ("client_version", r"[0-9][A-Za-z0-9.!+_-]{0,79}")):
        item = value.get(key)
        if item is not None and (not isinstance(item, str) or not re.fullmatch(pattern, item)):
            return None
        result[key] = item
    collections = value.get("collections")
    if not isinstance(collections, dict):
        return None
    result["collections"] = {}
    for name in ("jira_qa", "aem_guides", "dita_spec"):
        row = collections.get(name)
        if row is None:
            result["collections"][name] = {"id": None, "count": None, "status": "UNAVAILABLE"}
            continue
        if not isinstance(row, dict) or row.get("status") not in {"OK", "PARTIAL", "UNAVAILABLE"}:
            return None
        identifier, total = row.get("id"), row.get("count")
        if identifier is not None and (not isinstance(identifier, str) or not re.fullmatch(UUID, identifier)):
            return None
        if total is not None and count(total) is None:
            return None
        result["collections"][name] = {"id": identifier.lower() if identifier else None, "count": total, "status": row["status"]}
    return result


def mcp_status(packet):
    if not isinstance(packet, dict) or packet.get("error"):
        return {"status": "INVALID_MCP_RESPONSE"}
    result = packet.get("result")
    if not isinstance(result, dict) or result.get("isError") is True:
        return {"status": "MCP_TOOL_ERROR"}
    for item in result.get("content", []) if isinstance(result.get("content"), list) else []:
        if not isinstance(item, dict) or item.get("type") != "text":
            continue
        try:
            data = json.loads(item.get("text", ""))
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and isinstance(data.get("collections"), dict):
            chroma_available = data.get("chroma_available")
            embedding_available = data.get("embedding_available")
            if data.get("status") != "ok" or chroma_available is not True:
                return {"status": "CHROMA_AVAILABILITY_NOT_CONFIRMED",
                        "chroma_available": chroma_available if type(chroma_available) is bool else None,
                        "collections": {key: None for key in ("jira_qa", "aem_guides", "dita_spec")}}
            graph = data.get("evidence_graph", {})
            return {"status": "OK", "collections": {key: count(data["collections"].get(key))
                    for key in ("jira_qa", "aem_guides", "dita_spec")},
                    "index_identity": index_identity(data.get("index_identity")),
                    "chroma_available": True,
                    "embedding_available": embedding_available if type(embedding_available) is bool else None,
                    "evidence_graph_enabled": graph.get("enabled") if isinstance(graph, dict) and type(graph.get("enabled")) is bool else None}
    return {"status": "COLLECTION_COUNTS_UNAVAILABLE"}


def check_backend(port, token):
    result, data = http_json(port, "GET", "/mcp/health", token=token)
    health = isinstance(data, dict) and data.get("status") == "alive"
    result["alive"] = health
    if not health:
        return {"health": result, "rag_status": {"status": "SKIPPED_HEALTH_NOT_CONFIRMED"}}
    wire, packet = http_json(port, "POST", "/mcp", MCP_REQUEST, token)
    return {"health": result, "rag_status": mcp_status(packet) if packet is not None else wire}


def check_direct_chroma():
    wire, packet = http_json(4502, "GET", "/api/v2/heartbeat")
    result = {"heartbeat": wire, "scope": "default_tenant/default_database", "jira_qa_count": None}
    if not isinstance(packet, dict) or count(packet.get("nanosecond heartbeat")) is None:
        result["status"] = "CHROMA_HEARTBEAT_NOT_CONFIRMED"
        return result
    version_wire, version = http_json(4502, "GET", "/api/v2/version")
    result["version_response"] = version_wire
    result["server_version"] = version if isinstance(version, str) and re.fullmatch(r"[0-9][A-Za-z0-9.!+_-]{0,79}", version) else None
    wire, collection = http_json(4502, "GET", CHROMA_PREFIX + "jira_qa")
    result["collection_response"] = wire
    if not isinstance(collection, dict) or collection.get("name") != "jira_qa" or not re.fullmatch(UUID, str(collection.get("id", ""))):
        result["status"] = "COLLECTION_NOT_CONFIRMED"
        return result
    collection_id = collection["id"]
    result["collection_id"] = collection_id
    wire, value = http_json(4502, "GET", CHROMA_PREFIX + collection_id + "/count")
    result["count_response"] = wire
    result["jira_qa_count"] = count(value)
    result["status"] = "COUNT_OBSERVED" if count(value) is not None else "COUNT_UNAVAILABLE"
    return result


def conclusions(gateway, backend, direct):
    def observed(endpoint):
        return endpoint.get("rag_status", {}).get("collections", {}).get("jira_qa")
    a, b, c = observed(gateway), observed(backend), direct.get("jira_qa_count")
    notes = []
    if a is not None and b is not None and a != b:
        notes.append("GATEWAY_BACKEND_COUNT_MISMATCH: inspect Nginx upstream and runtime configuration.")
    if a is not None and c is not None:
        notes.append("BACKEND_DIRECT_CHROMA_COUNT_MISMATCH: do not import through the direct endpoint."
                     if a != c else "COUNTS_EQUAL_ONLY: matching counts do not prove storage identity or safe import readiness.")
    if any(value is None for value in (a, b, c)):
        notes.append("SOME_COUNTS_UNAVAILABLE: do not infer missing counts are zero.")
    notes.append("NO_IMPORT_AUTHORIZED_BY_THIS_REPORT: verify actual storage, embedding model, backup and writer maintenance first.")
    return notes


def diagnose(repo, service, token, chroma_service="chroma.service"):
    report = {"schema_version": "uac-vm-index-diagnostic-v2", "mode": "DIAGNOSTIC_ONLY",
              "observed_at_utc": datetime.now(timezone.utc).isoformat(),
              "actions": {"import": False, "index_write": False, "service_restart": False, "config_change": False},
              "diagnostic_python": sys.version.split()[0], "backend_token_supplied": bool(token),
              "repo": safe_path(repo), "service": service_info(service), "chroma_service": service_info(chroma_service),
              "notes": ["Proc environ is launch-time evidence, not guaranteed current Python environment.",
                        "Config fields are hints only; interpolation and custom loaders are not emulated.",
                        "Known loader order: launch environment, repo .env, backend .env, backend .env.docker.",
                        "Open file descriptors provide stronger evidence of embedded Chroma actually in use.",
                        "Root .env.docker is a launcher configuration hint; app.main does not automatically load that file.",
                        "Package METADATA and candidate file stats are disk observations, not proof of the running store or version.",
                        "No backend module, Chroma client, SQLite connection or embedding model is loaded by this script.",
                        "Checkout commit and file hashes describe files on disk, not the code already loaded by a running service.",
                        "Existing MCP status may initialize its own caches; no ingest/reindex operation is requested."]}
    commit = command(["git", "-C", str(repo), "rev-parse", "HEAD"])
    report["checkout_commit"] = commit if commit and re.fullmatch(r"[a-f0-9]{40,64}", commit) else None
    report["config_files"] = []
    for relative in (".env", "backend/.env", "backend/.env.docker", ".env.docker"):
        path = repo / relative
        entry = {"file": relative, "exists": path.is_file(),
                 "role": "LAUNCHER_CONFIG_ONLY_NOT_APP_AUTOLOAD" if relative == ".env.docker" else "APP_AUTOLOAD_CONFIG_HINT"}
        if entry["exists"]:
            try:
                entry["allowlisted_hints"] = config_hints(bounded_read(path).decode("utf-8-sig"), docker=relative.endswith(".env.docker"))
            except (OSError, UnicodeError, ValueError):
                entry["status"] = "UNREADABLE_OR_TOO_LARGE"
        report["config_files"].append(entry)
    report["implementation_files"] = []
    for relative in ("backend/app/main.py", "backend/app/services/vector_store_service.py",
                     "backend/app/storage/local_storage.py", "scripts/uac_eval/ingest_customer_csv.py",
                     "scripts/uac_eval/customer_profiles.json"):
        path = repo / relative
        entry = {"file": relative, "exists": path.is_file()}
        if entry["exists"]:
            try:
                entry["sha256"] = hashlib.sha256(bounded_read(path, 4 * MAX_BYTES)).hexdigest()
            except (OSError, ValueError):
                entry["status"] = "UNREADABLE_OR_TOO_LARGE"
        report["implementation_files"].append(entry)
    report["gateway_4502"] = check_backend(4502, token)
    report["backend_8001"] = check_backend(8001, token)
    report["direct_chroma_4502"] = check_direct_chroma()
    # Status calls may lazily initialise the live service's store. Inspect again;
    # an empty pre-call FD list must not be mistaken for proof of remote mode.
    report["service_after_status"] = service_info(service)
    report["chroma_service_after_status"] = service_info(chroma_service)
    services = [report["service"], report["chroma_service"], report["service_after_status"], report["chroma_service_after_status"]]
    report["installed_chroma_versions"] = package_versions(repo, services)
    report["candidate_sqlite_files"] = sqlite_file_evidence(repo, services, report["config_files"])
    report["findings"] = conclusions(report["gateway_4502"], report["backend_8001"], report["direct_chroma_4502"])
    report["next_step"] = "Share this redacted report; do not run the import yet."
    return report


def write_report(path, report):
    payload = (json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(str(path), flags, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def run_self_tests():
    secret = "not-for-reporting"
    hints = config_hints("CHROMA_HOST=localhost\nCHROMA_PORT=8000\nSECRET=" + secret +
                         "\nDATABASE_URL=postgresql://user:" + secret + "@server/db\nSTORAGE_PATH='data folder'\nCHROMA_SSL=false")
    assert secret not in json.dumps(hints)
    assert hints["DATABASE_URL"]["kind"] == "postgresql" and hints["CHROMA_PORT"] == 8000
    assert hints["STORAGE_PATH"] == "data folder"
    assert config_hints("CHROMA_HOST=${UNKNOWN}")["CHROMA_HOST"] == "UNRESOLVED_OR_NON_SIMPLE"
    assert safe_value("CHROMA_HOST", "https://user:pass@host") == "[REDACTED_NON_SIMPLE_HOST]"
    assert safe_value("CHROMA_PORT", "99999") == "INVALID_PORT"
    assert config_hints('CHROMA_HOST="localhost"', docker=True)["CHROMA_HOST"] != "localhost"
    assert safe_path("/path\nSECRET") == "[REDACTED_NON_SIMPLE_PATH]"
    assert chroma_command_options(["/venv/bin/chroma", "run", "--path", "/store/chroma", "--host=127.0.0.1", "--port", "8000", "--auth-token", secret]) == {
        "--path": ["/store/chroma"], "--host": ["127.0.0.1"], "--port": [8000]}
    assert not chroma_command_options(["/venv/bin/python", "unrelated.py", "--path", secret])
    assert secret not in json.dumps(chroma_command_options(["chroma", "run", "--host", "user:" + secret + "@host", "--port", "bad", "--password", secret]))
    assert count(0) == 0 and count(True) is None and count("0") is None and count(-1) is None
    inner = {"status": "ok", "chroma_available": True, "collections": {"jira_qa": 0}, "private": secret}
    packet = {"result": {"content": [{"type": "text", "text": json.dumps(inner)}]}}
    clean = mcp_status(packet)
    assert clean["collections"]["jira_qa"] == 0 and clean["collections"]["dita_spec"] is None
    assert secret not in json.dumps(clean)
    assert clean["index_identity"] is None  # Old backends cannot prove identity.
    identity = {"schema_version": "chroma-index-identity-v1", "status": "OK", "mode": "REMOTE",
                "target_fingerprint": "a" * 64, "tenant": "default_tenant", "database": "default_database",
                "client_version": "1.0.0", "collections": {"jira_qa": {
                    "id": "00000000-0000-0000-0000-000000000001", "count": 123, "status": "OK"}}, "secret": secret}
    assert index_identity(identity)["collections"]["jira_qa"]["count"] == 123
    assert secret not in json.dumps(index_identity(identity))
    identity_packet = {"result": {"content": [{"type": "text", "text": json.dumps({**inner, "index_identity": identity})}]}}
    assert mcp_status(identity_packet)["index_identity"] == index_identity(identity)
    for field, bad in (("mode", "OTHER"), ("tenant", "user:" + secret), ("target_fingerprint", "a"),
                       ("client_version", secret), ("status", "ok")):
        assert index_identity({**identity, field: bad}) is None
    for bad in (True, -1, "123"):
        assert index_identity({**identity, "collections": {"jira_qa": {"id": None, "count": bad, "status": "OK"}}}) is None
    assert mcp_status({"error": {"message": secret}})["status"] == "INVALID_MCP_RESPONSE"
    assert mcp_status({"result": {"isError": True}})["status"] == "MCP_TOOL_ERROR"
    for status, available in (("error", True), ("ok", False), ("ok", None), ("ok", "true"), ("ok", 1)):
        payload = {"status": status, "chroma_available": available, "collections": {"jira_qa": 0}}
        rejected = mcp_status({"result": {"content": [{"type": "text", "text": json.dumps(payload)}]}})
        assert rejected["collections"]["jira_qa"] is None
        assert rejected["status"] != "OK"
    a = {"rag_status": {"collections": {"jira_qa": 35927}}}
    assert any("BACKEND_DIRECT_CHROMA_COUNT_MISMATCH" in line for line in conclusions(a, a, {"jira_qa_count": 2847}))
    assert any("COUNTS_EQUAL_ONLY" in line for line in conclusions(a, a, {"jira_qa_count": 35927}))
    assert any("UNAVAILABLE" in line for line in conclusions({}, {}, {}))
    for port, method, path, body, token in (
        (4502, "POST", "/api/v1/admin/jira-rag/import-csv", {}, ""),
        (4502, "GET", "/api/v1/ai/rag-status", None, ""),
        (4502, "GET", "/api/v2/heartbeat", None, secret),
        (443, "GET", "/health", None, ""),
        (8001, "POST", "/mcp", {"params": {"name": "reindex"}}, ""),
    ):
        try:
            http_json(port, method, path, body, token)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe request accepted")
    class Response:
        status = 200
        def read(self, size): return b'{"status":"alive"}'
    class Connection:
        def __init__(self, host, port, timeout): assert host == "127.0.0.1" and timeout == 8
        def request(self, method, path, body, headers): assert method == "GET" and "Authorization" not in headers
        def getresponse(self): return Response()
        def close(self): pass
    assert http_json(4502, "GET", "/mcp/health", connection_factory=Connection)[1] == {"status": "alive"}
    with tempfile.TemporaryDirectory(prefix="uac-vm-diagnostic-selftest-") as folder:
        repo = Path(folder) / "repo"
        (repo / "backend" / "app").mkdir(parents=True)
        (repo / "backend" / "app" / "main.py").write_text("# harmless fixture\n")
        (repo / ".env").write_text("API_SECRET=" + secret + "\nCHROMA_HOST=localhost\n")
        (repo / ".env.docker").write_text("CHROMA_HOST=launcher-only\nSECRET=" + secret + "\n")
        metadata = repo / "backend" / ".venv" / "lib" / "python3.11" / "site-packages" / "chromadb-1.2.3.dist-info" / "METADATA"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("Name: chromadb\nVersion: 1.2.3\nPrivate: " + secret + "\n")
        sqlite_file = repo / "backend" / "storage" / "chroma_db" / "chroma.sqlite3"
        sqlite_file.parent.mkdir(parents=True)
        sqlite_file.write_bytes(b"not a database; stat-only fixture")
        versions = package_versions(repo, [])
        assert versions[0]["packages"][0]["version"] == "1.2.3" and secret not in json.dumps(versions)
        evidence = sqlite_file_evidence(repo, [], [])
        assert evidence[0]["exists"] is True and evidence[0]["size_bytes"] == sqlite_file.stat().st_size
        assert evidence[0]["inode"] == sqlite_file.stat().st_ino
        launch_path = Path(folder) / "launch-only-storage"
        launch_evidence = sqlite_file_evidence(repo, [{"processes": [{
            "launch_environment_hints": {"STORAGE_PATH": str(launch_path)}, "open_chroma_sqlite_files": []}]}], [])
        launch_row = next(row for row in launch_evidence if "process_launch_environment_hint_candidate" in row["reasons"])
        assert launch_row["exists"] is False and not launch_path.exists()
        assert launch_row["path"] == str(launch_path / "chroma_db" / "chroma.sqlite3")
        rejected_hints = sqlite_file_evidence(repo, [{"processes": [{
            "launch_environment_hints": {"STORAGE_PATH": "UNRESOLVED_OR_NON_SIMPLE"}}]}], [])
        assert len(rejected_hints) == 1
        original_http, original_command, original_service = http_json, command, service_info
        calls, service_calls = [], []
        collection_id = "00000000-0000-0000-0000-000000000001"
        def fake_http(port, method, path, body=None, token=""):
            calls.append((port, method, path))
            if path == "/mcp/health":
                payload = {"status": "alive"}
            elif path == "/mcp":
                assert body == MCP_REQUEST
                payload = {"result": {"content": [{"type": "text", "text": json.dumps({
                    "status": "ok", "chroma_available": True, "embedding_available": True,
                    "collections": {"jira_qa": 35927}, "unrequested_secret": secret})}]}}
            elif path == "/api/v2/heartbeat":
                payload = {"nanosecond heartbeat": 123}
            elif path == "/api/v2/version":
                payload = "1.2.3"
            elif path == CHROMA_PREFIX + "jira_qa":
                payload = {"id": collection_id, "name": "jira_qa", "metadata": {"secret": secret}}
            else:
                assert path == CHROMA_PREFIX + collection_id + "/count"
                payload = 2847
            return {"status": "OK", "http_status": 200}, payload
        def fake_service(name):
            service_calls.append((name, len(calls)))
            return {"name": name, "processes": []}
        before_files = sorted(str(p.relative_to(repo)) for p in repo.rglob("*"))
        try:
            globals()["http_json"] = fake_http
            globals()["command"] = lambda args: "a" * 40
            globals()["service_info"] = fake_service
            report = diagnose(repo, "aem-backend.service", "")
        finally:
            globals()["http_json"] = original_http
            globals()["command"] = original_command
            globals()["service_info"] = original_service
        assert len(calls) == 8
        assert service_calls == [("aem-backend.service", 0), ("chroma.service", 0), ("aem-backend.service", 8), ("chroma.service", 8)]
        assert report["direct_chroma_4502"]["server_version"] == "1.2.3"
        assert report["config_files"][-1]["role"] == "LAUNCHER_CONFIG_ONLY_NOT_APP_AUTOLOAD"
        assert report["gateway_4502"]["rag_status"]["collections"]["jira_qa"] == 35927
        assert report["direct_chroma_4502"]["jira_qa_count"] == 2847
        assert any("BACKEND_DIRECT_CHROMA_COUNT_MISMATCH" in row for row in report["findings"])
        assert not any(report["actions"].values()) and secret not in json.dumps(report)
        assert report["checkout_commit"] == "a" * 40 and "runtime_commit" not in report
        assert before_files == sorted(str(p.relative_to(repo)) for p in repo.rglob("*"))
        path = Path(folder) / "report.json"
        write_report(path, {"safe": True})
        assert json.loads(path.read_text()) == {"safe": True}
        try:
            write_report(path, {"safe": False})
        except FileExistsError:
            pass
        else:
            raise AssertionError("Existing output was overwritten")
        assert json.loads(path.read_text()) == {"safe": True}
    print("PASS: VM diagnostic self-tests; redaction, strict schemas, no write endpoints, fixed loopback, count honesty, output preservation")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("/root/aem-guides-dataset-studio"))
    parser.add_argument("--service", default="aem-backend.service")
    parser.add_argument("--chroma-service", default="chroma.service", help="Chroma systemd unit to inspect, if installed")
    parser.add_argument("--output", type=Path, help="New private report file; never overwrites an existing file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        run_self_tests()
        return 0
    if sys.platform != "linux":
        parser.error("Run diagnostics on the Linux VM; --self-test works on this machine.")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}\.service", name) for name in (args.service, args.chroma_service)):
        parser.error("Invalid service name")
    repo = args.repo.expanduser().resolve()
    if not (repo / "backend" / "app" / "main.py").is_file():
        parser.error("Repo not found; supply --repo /absolute/path/to/aem-guides-dataset-studio")
    try:
        report = diagnose(repo, args.service, os.environ.get("AEM_STUDIO_TOKEN", ""), args.chroma_service)
        if args.output:
            output = args.output.expanduser().absolute()
        else:
            parent = tempfile.mkdtemp(prefix="uac-vm-check-", dir="/var/tmp" if Path("/var/tmp").is_dir() else None)
            output = Path(parent) / "report.json"
        write_report(output, report)
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
        print("\nREPORT_FILE=" + safe_path(output))
        print("DONE: diagnostic only. Share report.json; do not run the import yet.")
        return 0
    except (OSError, ValueError, http.client.HTTPException):
        print("STOP: diagnostic could not finish or report already exists. No import/restart/config change was requested.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
