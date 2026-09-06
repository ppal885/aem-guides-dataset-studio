#!/usr/bin/env bash
# Prepare an isolated interpreter only. Never changes packages, services or RAG data.
# Official source: https://www.python.org/downloads/release/python-31116/
set -Eeuo pipefail
umask 077
PATH=/usr/bin:/bin
export PATH
unset CDPATH ENV BASH_ENV PYTHONPATH PYTHONHOME

MODE=${1:---check}
if [[ $# -gt 1 || ( "$MODE" != --check && "$MODE" != --build ) ]]; then
  printf 'Usage: bash scripts/uac_eval/build_vm_python311.sh [--check|--build]\n' >&2
  exit 2
fi

readonly VERSION=3.11.16
readonly PREFIX=/opt/aem-python-3.11.16
readonly SOURCE_URL=https://www.python.org/ftp/python/3.11.16/Python-3.11.16.tar.xz
readonly SOURCE_SHA256=91bcdebfdde239a003ae93738a7fce0f9230fee5c4bc2b86f6e6e8c6f98aabe8
BUILD_ROOT=
STEP=PREREQUISITES

fail() { printf 'STOP: %s\n' "$1" >&2; exit 1; }
on_error() {
  local result=$?
  printf 'STOP: isolated Python preparation failed at %s. No service or package-manager action was requested.\n' "$STEP" >&2
  if [[ -n "$BUILD_ROOT" ]]; then
    printf 'PRESERVE_BUILD_DIR=%s\nPrivate build.log may contain local paths; do not publish it unreviewed.\n' "$BUILD_ROOT" >&2
  fi
  printf 'Preserve any partial %s installation; this helper never deletes or overwrites an existing prefix.\n' "$PREFIX" >&2
  exit "$result"
}
trap on_error ERR

# Child tools cannot inherit credentials, proxy credentials, compiler flags, Python
# paths, curl configuration, or an activated venv from the invoking session.
clean() {
  if [[ -n "$BUILD_ROOT" ]]; then
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C HOME="$BUILD_ROOT" TMPDIR="$BUILD_ROOT/tmp" "$@"
  else
    /usr/bin/env -i PATH=/usr/bin:/bin LC_ALL=C HOME=/nonexistent "$@"
  fi
}

for tool in python3 cc make curl sha256sum mktemp mkdir findmnt timeout cmp; do
  command -v "$tool" >/dev/null || fail "MISSING_REQUIRED_TOOL: $tool (install prerequisites separately; no automatic OS repair)"
done

# This block is read-only, including --check: no model/backend import, temporary
# directory, compiler output file, network request or service inspection.
clean python3 -I -B - "$PREFIX" <<'PY_PREFLIGHT'
import json
import lzma
import os
from pathlib import Path
import platform
import stat
import subprocess
import sys

def require(ok, reason):
    if not ok:
        raise SystemExit("STOP: " + reason)

require(os.geteuid() == 0, "ROOT_REQUIRED_FOR_REVIEWED_VM_PREFIX")
require(sys.platform == "linux" and platform.machine() == "x86_64", "LINUX_X86_64_REQUIRED")
prefix = Path(sys.argv[1])
require(str(prefix) == "/opt/aem-python-3.11.16", "UNEXPECTED_INSTALL_PREFIX")
for parent in (Path("/root"), Path("/opt")):
    info = parent.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
            and not info.st_mode & 0o022 and parent.resolve() == parent,
            "UNSAFE_PARENT_DIRECTORY")
    result = subprocess.run(["/usr/bin/findmnt", "-n", "-o", "FSTYPE,OPTIONS", "-T", str(parent)],
                            check=True, capture_output=True, text=True, timeout=10)
    fields = result.stdout.split()
    require(len(fields) == 2, "UNRECOGNIZED_MOUNT_INFORMATION")
    fs_type, options = fields[0], set(fields[1].split(","))
    require(fs_type in {"ext2", "ext3", "ext4", "xfs", "btrfs", "zfs"}
            and not {"ro", "noexec"} & options, "WRITABLE_EXECUTABLE_DISK_FILESYSTEM_REQUIRED")
    space = os.statvfs(parent)
    require(space.f_bavail * space.f_frsize >= 6 * 1024**3, "SIX_GIB_FREE_DISK_REQUIRED")
require(not os.path.lexists(prefix), "PREFIX_ALREADY_EXISTS_PRESERVE_AND_REVIEW")
print(json.dumps({"status": "READ_ONLY_PATH_CHECK_PASS", "prefix": str(prefix),
                  "package_changes": False, "service_changes": False}))
PY_PREFLIGHT

# GCC syntax-only mode checks real headers without linking or writing an object.
# All names are fixed. A missing dependency stops before download/build/install.
missing=0
for header in openssl/ssl.h zlib.h bzlib.h readline/readline.h sqlite3.h ffi.h lzma.h ncurses.h uuid/uuid.h; do
  if ! printf '#include <%s>\nint main(void) { return 0; }\n' "$header" | clean cc -x c -fsyntax-only - >/dev/null 2>&1; then
    printf 'MISSING_BUILD_HEADER=%s\n' "$header" >&2
    missing=1
  fi
done
if [[ "$missing" != 0 ]]; then
  fail 'BUILD_PREREQUISITES_MISSING. Resolve approved OS prerequisites separately, including any half-configured kernel; this helper never runs apt or dpkg.'
fi
if [[ "$MODE" == --check ]]; then
  printf 'CHECK_PASS_ONLY: headers and fresh on-disk prefix checked; no files created, download, install, service change or RAG repair performed.\n'
  exit 0
fi

STEP=PRIVATE_WORK_DIRECTORY
BUILD_ROOT=$(clean mktemp -d /root/aem-python-build-XXXXXXXX)
[[ "$BUILD_ROOT" == /root/aem-python-build-* && -d "$BUILD_ROOT" && ! -L "$BUILD_ROOT" ]] || fail INVALID_PRIVATE_BUILD_DIRECTORY
clean mkdir -m 700 "$BUILD_ROOT/tmp"
printf 'PYTHON_BUILD_DIR=%s\n' "$BUILD_ROOT"
printf 'Building only %s; existing Python, venvs, services and stores stay untouched.\n' "$PREFIX"
LOG="$BUILD_ROOT/build.log"

system_python_fingerprint() {
  clean python3 -I -B - <<'PY_SYSTEM_HASH'
import hashlib
import json
from pathlib import Path

records = []
for name in ("/usr/bin/python3", "/usr/bin/python3.11"):
    path = Path(name)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    records.append({"path": name, "resolved": str(path.resolve(strict=True)),
                    "sha256": digest.hexdigest()})
print(json.dumps(records, sort_keys=True))
PY_SYSTEM_HASH
}
STEP=ORIGINAL_INTERPRETER_FINGERPRINT
system_python_fingerprint >"$BUILD_ROOT/system-python-before.json"

STEP=SOURCE_DOWNLOAD
clean curl --disable --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --silent --show-error \
  --location --max-redirs 3 --connect-timeout 30 --max-time 300 --retry 2 --retry-delay 2 \
  --output "$BUILD_ROOT/Python.tar.xz" "$SOURCE_URL" >"$LOG" 2>&1
STEP=SOURCE_HASH
printf '%s  %s\n' "$SOURCE_SHA256" "$BUILD_ROOT/Python.tar.xz" | clean sha256sum --check --status

STEP=SAFE_SOURCE_EXTRACTION
# Hash-verified official archive only; additionally reject links, devices, traversal,
# duplicate names and oversized archives. No tarfile.extractall / ownership restore.
clean python3 -I -B - "$BUILD_ROOT/Python.tar.xz" "$BUILD_ROOT/source" <<'PY_EXTRACT' >>"$LOG" 2>&1
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile

archive, destination = map(Path, sys.argv[1:])
if os.path.lexists(destination):
    raise SystemExit("SOURCE_DESTINATION_EXISTS")
with tarfile.open(archive, "r:xz") as handle:
    members = handle.getmembers()
    if not members or len(members) > 100000 or sum(m.size for m in members) > 1024**3:
        raise SystemExit("SOURCE_ARCHIVE_LIMIT")
    names = set()
    for member in members:
        name = PurePosixPath(member.name)
        if (not member.name or "\\" in member.name or name.is_absolute() or ".." in name.parts
                or not name.parts or name.parts[0] != "Python-3.11.16"
                or str(name) in names or not (member.isfile() or member.isdir())
                or member.size < 0 or member.size > 64 * 1024**2):
            raise SystemExit("UNSAFE_SOURCE_ARCHIVE_MEMBER")
        names.add(str(name))
    destination.mkdir(mode=0o700)
    for member in members:
        target = destination.joinpath(*PurePosixPath(member.name).parts)
        if member.isdir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        else:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            stream = handle.extractfile(member)
            if stream is None:
                raise SystemExit("SOURCE_ARCHIVE_FILE_UNREADABLE")
            with stream, target.open("xb") as output:
                shutil.copyfileobj(stream, output, 1024 * 1024)
            target.chmod(0o700 if member.mode & 0o111 else 0o600)
print("VERIFIED_SOURCE_EXTRACTED")
PY_EXTRACT

cd "$BUILD_ROOT/source/Python-$VERSION"
STEP=CONFIGURE
clean timeout --kill-after=30s 300 ./configure --prefix="$PREFIX" --with-ensurepip=install >>"$LOG" 2>&1

STEP=BOUND_INSTALL_WORKERS
# CPython 3.11.16's generated Makefile has six compileall -j0 invocations.
# Alter only those exact lines to -j1; unknown source layout fails before install.
clean python3 -I -B - "$PWD/Makefile" <<'PY_MAKEFILE' >>"$LOG" 2>&1
import hashlib
import json
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
raw = path.read_bytes()
text = raw.decode("utf-8")
pattern = re.compile(r"(?m)^(\s*)-j0 (-d \$\(LIBDEST\)(?:/site-packages)? -f \\)$")
matches = list(pattern.finditer(text))
if (len(matches) != 6 or text.count("-j0") != 6
        or sum("/site-packages" in match.group(0) for match in matches) != 3):
    raise SystemExit("UNEXPECTED_COMPILEALL_LAYOUT_NO_INSTALL")
patched = pattern.sub(lambda match: match.group(1) + "-j1 " + match.group(2), text).encode("utf-8")
path.write_bytes(patched)
print(json.dumps({"scope": "GENERATED_MAKEFILE_COMPILEALL_ONLY", "replacements": 6,
                  "before_sha256": hashlib.sha256(raw).hexdigest(),
                  "after_sha256": hashlib.sha256(patched).hexdigest()}))
PY_MAKEFILE

STEP=COMPILE
clean timeout --kill-after=30s 2400 make -j2 >>"$LOG" 2>&1

STEP=BUILT_STDLIB_PROBE
clean timeout --kill-after=10s 120 ./python -I -B -c \
  'import sys, ssl, sqlite3, ctypes, bz2, lzma, zlib, venv, ensurepip; assert sys.version_info == (3, 11, 16, "final", 0); assert callable(sys.get_int_max_str_digits)' >>"$LOG" 2>&1

STEP=RESERVE_FRESH_PREFIX
# Atomic mkdir refuses concurrent installation or a newly introduced symlink.
clean mkdir -m 755 "$PREFIX"
STEP=ALTINSTALL
clean timeout --kill-after=30s 1200 make -j1 altinstall >>"$LOG" 2>&1

STEP=INSTALLED_STDLIB_PROBE
clean "$PREFIX/bin/python3.11" -I -B - "$PREFIX" <<'PY_STDLIB' >"$BUILD_ROOT/interpreter-result.json" 2>>"$LOG"
import bz2
import ctypes
import ensurepip
import hashlib
import json
import lzma
from pathlib import Path
import sqlite3
import ssl
import sys
import venv
import zlib

expected = Path(sys.argv[1])
if (sys.version_info != (3, 11, 16, "final", 0)
        or Path(sys.prefix).resolve() != expected.resolve()
        or not callable(getattr(sys, "get_int_max_str_digits", None))):
    raise SystemExit("FINAL_INTERPRETER_CONTRACT_FAILED")
assert sys.get_int_max_str_digits() >= 0
payload = b"isolated-python-stdlib-check"
for codec in (bz2, lzma, zlib):
    if codec.decompress(codec.compress(payload)) != payload:
        raise SystemExit("COMPRESSION_MODULE_CHECK_FAILED")
if not ssl.create_default_context().cert_store_stats().get("x509_ca", 0):
    raise SystemExit("SYSTEM_CA_STORE_UNAVAILABLE")
with sqlite3.connect(":memory:") as connection:
    if connection.execute("select 1").fetchone() != (1,):
        raise SystemExit("IN_MEMORY_SQLITE_CHECK_FAILED")
if ctypes.sizeof(ctypes.c_void_p) != 8:
    raise SystemExit("CTYPES_PLATFORM_CHECK_FAILED")
print(json.dumps({"status": "PASS_INTERPRETER_ONLY", "python": list(sys.version_info),
                  "prefix": str(expected), "source_hash_algorithm": "sha256",
                  "model_loaded": False, "backend_venv_created": False,
                  "service_changes": False, "rag_repaired": False}))
PY_STDLIB
STEP=ORIGINAL_INTERPRETER_RECHECK
system_python_fingerprint >"$BUILD_ROOT/system-python-after.json"
clean cmp "$BUILD_ROOT/system-python-before.json" "$BUILD_ROOT/system-python-after.json" >>"$LOG" 2>&1
printf 'PASS_INTERPRETER_ONLY\nPYTHON_EXECUTABLE=%s/bin/python3.11\nRESULT_FILE=%s/interpreter-result.json\n' "$PREFIX" "$BUILD_ROOT"
printf 'No backend venv or service was changed. Backend dependency recreation, model canary, and separately reviewed backend-only cutover remain required.\n'
